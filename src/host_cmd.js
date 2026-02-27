// Ported from: WinQuake/host_cmd.c

import { Sys_Printf, Sys_Error, Sys_FloatTime } from './sys.js';
import { Con_Printf, SZ_Write, SZ_Clear,
	MSG_WriteByte, MSG_WriteShort, MSG_WriteLong, MSG_WriteFloat,
	MSG_WriteString, MSG_WriteAngle, COM_Parse, com_token } from './common.js';
import { svc_signonnum, svc_time, svc_updatename, svc_updatefrags,
	svc_updatecolors, svc_lightstyle, svc_updatestat, svc_setangle,
	svc_setpause } from './protocol.js';
import { STAT_TOTALSECRETS, STAT_TOTALMONSTERS, STAT_SECRETS, STAT_MONSTERS,
	MAX_LIGHTSTYLES, SAVEGAME_COMMENT_LENGTH } from './quakedef.js';
import { NUM_FOR_EDICT, EDICT_NUM, EDICT_TO_PROG, PR_GetString, pr_global_struct } from './progs.js';
import { PR_ExecuteProgram } from './pr_exec.js';
import { ED_NewString, ED_Write, ED_WriteGlobals, ED_ParseGlobals, ED_ParseEdict } from './pr_edict.js';
import { sv_player } from './sv_phys.js';
import { FL_GODMODE, FL_NOTARGET,
	MOVETYPE_WALK, MOVETYPE_FLY, MOVETYPE_NOCLIP } from './sv_phys.js';
import { Cvar_Set, Cvar_SetValue, Cvar_VariableValue } from './cvar.js';
import { Cmd_AddCommand, Cmd_Argc, Cmd_Argv, Cmd_Args, Cmd_ExecuteString,
	Cmd_ForwardToServer, cmd_source, src_command, src_client, Cbuf_AddText } from './cmd.js';
import { SV_SpawnServer, SV_SaveSpawnparms, SV_DropClient,
	SV_WriteClientdataToMessage, current_skill } from './sv_main.js';
import { sv, svs, host_client, set_host_client,
	NUM_SPAWN_PARMS, NUM_PING_TIMES } from './server.js';
import { cls, cl, ca_connected, ca_dedicated, MAX_DEMOS } from './client.js';
import { key_game, set_key_dest } from './keys.js';
import { CL_Disconnect, CL_EstablishConnection, CL_NextDemo,
	cl_name, cl_color } from './cl_main.js';
import { CL_StopPlayback } from './cl_demo.js';
import { SCR_BeginLoadingPlaque } from './gl_screen.js';
import { hostname } from './net_main.js';
import { SV_LinkEdict } from './world.js';
import { SV_ClientPrintf, SV_BroadcastPrintf,
	Host_ShutdownServer, Host_Shutdown } from './host.js';
import { COM_FindFile, COM_EnsureFile } from './pak.js';

export let noclip_anglehack = false;

export function set_noclip_anglehack( v ) {

	noclip_anglehack = v;

}

/*
======================
Host_InitCommands
======================
*/
export function Host_InitCommands() {

	Cmd_AddCommand( 'status', Host_Status_f );
	Cmd_AddCommand( 'quit', Host_Quit_f );
	Cmd_AddCommand( 'map', Host_Map_f );
	Cmd_AddCommand( 'changelevel', Host_Changelevel_f );
	Cmd_AddCommand( 'restart', Host_Restart_f );
	Cmd_AddCommand( 'reconnect', Host_Reconnect_f );
	Cmd_AddCommand( 'connect', Host_Connect_f );
	Cmd_AddCommand( 'name', Host_Name_f );
	Cmd_AddCommand( 'pause', Host_Pause_f );
	Cmd_AddCommand( 'say', Host_Say_f );
	Cmd_AddCommand( 'say_team', Host_Say_Team_f );
	Cmd_AddCommand( 'tell', Host_Tell_f );
	Cmd_AddCommand( 'color', Host_Color_f );
	Cmd_AddCommand( 'kill', Host_Kill_f );
	Cmd_AddCommand( 'god', Host_God_f );
	Cmd_AddCommand( 'notarget', Host_Notarget_f );
	Cmd_AddCommand( 'fly', Host_Fly_f );
	Cmd_AddCommand( 'noclip', Host_Noclip_f );
	Cmd_AddCommand( 'give', Host_Give_f );
	Cmd_AddCommand( 'ping', Host_Ping_f );
	Cmd_AddCommand( 'kick', Host_Kick_f );
	Cmd_AddCommand( 'save', Host_Savegame_f );
	Cmd_AddCommand( 'load', Host_Loadgame_f );
	Cmd_AddCommand( 'savegame', Host_Savegame_f );
	Cmd_AddCommand( 'loadgame', Host_Loadgame_f );
	Cmd_AddCommand( 'startdemos', Host_Startdemos_f );
	Cmd_AddCommand( 'demos', Host_Demos_f );
	Cmd_AddCommand( 'stopdemo', Host_Stopdemo_f );
	Cmd_AddCommand( 'spawn', Host_Spawn_f );
	Cmd_AddCommand( 'begin', Host_Begin_f );
	Cmd_AddCommand( 'prespawn', Host_PreSpawn_f );

}

function Host_Status_f() {

	Con_Printf( 'host:    Three-Quake\n' );
	Con_Printf( 'map:     ' + ( sv.name || 'none' ) + '\n' );
	Con_Printf( 'players: ' + svs.maxclients + ' max\n' );

}

function Host_Quit_f() {

	Host_Shutdown();

}

function Host_Map_f() {

	if ( cmd_source !== src_command )
		return;

	const name = Cmd_Argv( 1 );
	const filename = 'maps/' + name + '.bsp';

	// If the map file isn't loaded yet, fetch it on demand
	if ( COM_FindFile( filename ) === null ) {

		Con_Printf( 'Fetching %s...\n', filename );
		COM_EnsureFile( filename ).then( ( success ) => {

			if ( success ) {

				// Re-issue the map command now that the file is cached
				Cbuf_AddText( 'map ' + name + '\n' );

			} else {

				Con_Printf( 'Couldn\'t find map: %s\n', name );

			}

		} );
		return;

	}

	cls.demonum = - 1; // stop demo loop in case this fails

	CL_Disconnect();
	Host_ShutdownServer( false );

	set_key_dest( key_game ); // remove console or menu
	SCR_BeginLoadingPlaque();

	cls.mapstring = '';
	for ( let i = 0; i < Cmd_Argc(); i ++ ) {

		cls.mapstring += Cmd_Argv( i ) + ' ';

	}

	cls.mapstring += '\n';

	svs.serverflags = 0; // haven't completed an episode yet

	SV_SpawnServer( name );

	if ( ! sv.active )
		return;

	if ( cls.state !== ca_dedicated ) {

		cls.spawnparms = '';

		for ( let i = 2; i < Cmd_Argc(); i ++ ) {

			cls.spawnparms += Cmd_Argv( i ) + ' ';

		}

		Cmd_ExecuteString( 'connect local', src_command );

	}

}

function Host_Changelevel_f() {

	if ( Cmd_Argc() !== 2 ) {

		Con_Printf( 'changelevel <levelname> : continue game on a new level\n' );
		return;

	}

	if ( ! sv.active || cls.demoplayback ) {

		Con_Printf( 'Only the server may changelevel\n' );
		return;

	}

	const level = Cmd_Argv( 1 );
	const filename = 'maps/' + level + '.bsp';

	// If the map file isn't loaded yet, fetch it on demand
	if ( COM_FindFile( filename ) === null ) {

		Con_Printf( 'Fetching %s...\n', filename );
		COM_EnsureFile( filename ).then( ( success ) => {

			if ( success ) {

				Cbuf_AddText( 'changelevel ' + level + '\n' );

			} else {

				Con_Printf( 'Couldn\'t find map: %s\n', level );

			}

		} );
		return;

	}

	SV_SaveSpawnparms();
	SV_SpawnServer( level );
	// Note: SV_SpawnServer handles client reconnection internally via SV_SendReconnect
	// which calls Host_Reconnect_f to reset cls.signon. We do NOT call CL_EstablishConnection
	// here because the client is already connected - it just needs new signon messages.

}

function Host_Restart_f() {

	if ( ! sv.active )
		return;

	const mapname = sv.name;
	if ( mapname ) {

		Cbuf_AddText( 'map ' + mapname + '\n' );

	}

}

function Host_Reconnect_f() {

	SCR_BeginLoadingPlaque();
	cls.signon = 0; // need new connection messages

}

function Host_Connect_f() {

	cls.demonum = - 1; // stop demo loop in case this fails
	if ( cls.demoplayback ) {

		CL_StopPlayback();
		CL_Disconnect();

	}

	// Use Cmd_Argv(1) to get the server address
	// When quoted (e.g., connect "wts://host:port"), Cmd_Argv(1) properly returns the unquoted URL
	// Cmd_Args() would include the quotes which breaks URL parsing
	const name = Cmd_Argv( 1 );
	if ( ! name || name.length === 0 ) {

		Con_Printf( 'usage: connect <server>\n' );
		return;

	}

	Con_Printf( 'Connecting to %s...\n', name );

	// CL_EstablishConnection is async (WebTransport handshake)
	// Use .then() to call Host_Reconnect_f when connection succeeds
	CL_EstablishConnection( name ).then( () => {

		Host_Reconnect_f();

	} ).catch( ( e ) => {

		Con_Printf( 'connect: %s\n', e.message );

	} );

}

function Host_Name_f() {

	let newName;

	if ( Cmd_Argc() === 1 ) {

		Con_Printf( '"name" is "%s"\n', cl_name.string );
		return;

	}

	if ( Cmd_Argc() === 2 )
		newName = Cmd_Argv( 1 );
	else
		newName = Cmd_Args();

	// Sanitize name: only printable ASCII, max 15 chars
	newName = newName.replace( /[^\x20-\x7E]/g, '' ); // Remove non-printable chars
	if ( newName.length > 15 )
		newName = newName.substring( 0, 15 );
	if ( newName.length === 0 )
		newName = 'player'; // Fallback for empty names

	if ( cmd_source === src_command ) {

		// Client-side: update cvar and forward to server
		if ( cl_name.string === newName )
			return;

		Cvar_Set( '_cl_name', newName );

		if ( cls.state === ca_connected )
			Cmd_ForwardToServer();

		return;

	}

	// Server-side: update the client's name (only if changed)
	if ( host_client.name === newName )
		return; // No change, skip update

	if ( host_client.name !== '' && host_client.name !== 'unconnected' ) {

		Con_Printf( '%s renamed to %s\n', host_client.name, newName );

	}

	host_client.name = newName;

	// Set the netname on the edict
	if ( host_client.edict != null ) {

		host_client.edict.v.netname = ED_NewString( newName );

	}

	// Send notification to all clients
	MSG_WriteByte( sv.reliable_datagram, svc_updatename );
	MSG_WriteByte( sv.reliable_datagram, svs.clients.indexOf( host_client ) );
	MSG_WriteString( sv.reliable_datagram, host_client.name );

}

function Host_Pause_f() {

	if ( cmd_source === src_command ) {

		Cmd_ForwardToServer();
		return;

	}

	if ( Cvar_VariableValue( 'pausable' ) === 0 ) {

		SV_ClientPrintf( 'Pause not allowed.\n' );

	} else {

		sv.paused = sv.paused ^ 1;

		if ( sv.paused ) {

			SV_BroadcastPrintf( '%s paused the game\n', PR_GetString( sv_player.v.netname ) );

		} else {

			SV_BroadcastPrintf( '%s unpaused the game\n', PR_GetString( sv_player.v.netname ) );

		}

		// send notification to all clients
		MSG_WriteByte( sv.reliable_datagram, svc_setpause );
		MSG_WriteByte( sv.reliable_datagram, sv.paused );

	}

}

function Host_Say( teamonly ) {

	let fromServer = false;

	if ( cmd_source === src_command ) {

		if ( cls.state === ca_dedicated ) {

			fromServer = true;
			teamonly = false;

		} else {

			Cmd_ForwardToServer();
			return;

		}

	}

	if ( Cmd_Argc() < 2 ) return;

	const save = host_client;

	let p = Cmd_Args();

	// remove quotes if present
	if ( p.charAt( 0 ) === '"' ) {

		p = p.substring( 1, p.length - 1 );

	}

	// turn on color set 1
	let text;
	if ( fromServer === false ) {

		text = '\x01' + save.name + ': ';

	} else {

		text = '\x01<' + hostname.string + '> ';

	}

	// truncate if too long
	const maxLen = 62 - text.length; // 64 - 2 for \n and safety
	if ( p.length > maxLen ) {

		p = p.substring( 0, maxLen );

	}

	text += p + '\n';

	const teamplayValue = Cvar_VariableValue( 'teamplay' );

	for ( let j = 0; j < svs.maxclients; j ++ ) {

		const client = svs.clients[ j ];
		if ( client == null || client.active === false || client.spawned === false ) continue;
		if ( teamplayValue !== 0 && teamonly && client.edict.v.team !== save.edict.v.team ) continue;
		set_host_client( client );
		SV_ClientPrintf( '%s', text );

	}

	set_host_client( save );

	Sys_Printf( '%s', text.substring( 1 ) );

}

function Host_Say_f() {

	Host_Say( false );

}

function Host_Say_Team_f() {

	Host_Say( true );

}

function Host_Tell_f() {

	if ( cmd_source === src_command ) {

		Cmd_ForwardToServer();
		return;

	}

	if ( Cmd_Argc() < 3 ) return;

	let text = host_client.name + ': ';

	let p = Cmd_Args();

	// remove quotes if present
	if ( p.charAt( 0 ) === '"' ) {

		p = p.substring( 1, p.length - 1 );

	}

	// truncate if too long
	const maxLen = 62 - text.length;
	if ( p.length > maxLen ) {

		p = p.substring( 0, maxLen );

	}

	text += p + '\n';

	const save = host_client;

	for ( let j = 0; j < svs.maxclients; j ++ ) {

		const client = svs.clients[ j ];
		if ( client == null || client.active === false || client.spawned === false ) continue;
		if ( client.name.toLowerCase() !== Cmd_Argv( 1 ).toLowerCase() ) continue;
		set_host_client( client );
		SV_ClientPrintf( '%s', text );
		break;

	}

	set_host_client( save );

}

function Host_Color_f() {

	if ( Cmd_Argc() === 1 ) {

		Con_Printf( '"color" is "' + ( ( cl_color.value | 0 ) >> 4 ) + ' ' + ( ( cl_color.value | 0 ) & 0x0f ) + '"\n' );
		Con_Printf( 'color <0-13> [0-13]\n' );
		return;

	}

	let top, bottom;

	if ( Cmd_Argc() === 2 ) {

		top = bottom = parseInt( Cmd_Argv( 1 ) ) || 0;

	} else {

		top = parseInt( Cmd_Argv( 1 ) ) || 0;
		bottom = parseInt( Cmd_Argv( 2 ) ) || 0;

	}

	top &= 15;
	if ( top > 13 ) top = 13;
	bottom &= 15;
	if ( bottom > 13 ) bottom = 13;

	const playercolor = top * 16 + bottom;

	if ( cmd_source === src_command ) {

		Cvar_SetValue( '_cl_color', playercolor );
		if ( cls.state === ca_connected ) {

			Cmd_ForwardToServer();

		}

		return;

	}

	host_client.colors = playercolor;
	host_client.edict.v.team = bottom + 1;

	// send notification to all clients
	MSG_WriteByte( sv.reliable_datagram, svc_updatecolors );
	MSG_WriteByte( sv.reliable_datagram, svs.clients.indexOf( host_client ) );
	MSG_WriteByte( sv.reliable_datagram, host_client.colors );

}

function Host_Kill_f() {

	if ( cmd_source === src_command ) {

		// If not running a local server, forward the command to the remote server
		if ( ! sv.active ) {

			Cmd_ForwardToServer();
			return;

		}

		Cmd_ExecuteString( 'kill', src_client );
		return;

	}

	if ( sv_player == null || sv_player.v.health <= 0 ) {

		SV_ClientPrintf( 'Can\'t suicide -- allready dead!\n' );
		return;

	}

	pr_global_struct.time = sv.time;
	pr_global_struct.self = EDICT_TO_PROG( sv_player );
	PR_ExecuteProgram( pr_global_struct.ClientKill );

}

function Host_God_f() {

	if ( cmd_source === src_command ) {

		Cmd_ForwardToServer();
		return;

	}

	if ( pr_global_struct.deathmatch && ! host_client.privileged )
		return;

	sv_player.v.flags = ( sv_player.v.flags | 0 ) ^ FL_GODMODE;
	if ( ! ( ( sv_player.v.flags | 0 ) & FL_GODMODE ) )
		SV_ClientPrintf( 'godmode OFF\n' );
	else
		SV_ClientPrintf( 'godmode ON\n' );

}

function Host_Notarget_f() {

	if ( cmd_source === src_command ) {

		Cmd_ForwardToServer();
		return;

	}

	if ( pr_global_struct.deathmatch && ! host_client.privileged )
		return;

	sv_player.v.flags = ( sv_player.v.flags | 0 ) ^ FL_NOTARGET;
	if ( ! ( ( sv_player.v.flags | 0 ) & FL_NOTARGET ) )
		SV_ClientPrintf( 'notarget OFF\n' );
	else
		SV_ClientPrintf( 'notarget ON\n' );

}

function Host_Fly_f() {

	if ( cmd_source === src_command ) {

		Cmd_ForwardToServer();
		return;

	}

	if ( pr_global_struct.deathmatch && ! host_client.privileged )
		return;

	if ( sv_player.v.movetype !== MOVETYPE_FLY ) {

		sv_player.v.movetype = MOVETYPE_FLY;
		SV_ClientPrintf( 'flymode ON\n' );

	} else {

		sv_player.v.movetype = MOVETYPE_WALK;
		SV_ClientPrintf( 'flymode OFF\n' );

	}

}

function Host_Noclip_f() {

	if ( cmd_source === src_command ) {

		Cmd_ForwardToServer();
		return;

	}

	if ( pr_global_struct.deathmatch && ! host_client.privileged )
		return;

	if ( sv_player.v.movetype !== MOVETYPE_NOCLIP ) {

		noclip_anglehack = true;
		sv_player.v.movetype = MOVETYPE_NOCLIP;
		SV_ClientPrintf( 'noclip ON\n' );

	} else {

		noclip_anglehack = false;
		sv_player.v.movetype = MOVETYPE_WALK;
		SV_ClientPrintf( 'noclip OFF\n' );

	}

}

function Host_Give_f() {

	if ( cmd_source === src_command ) {

		Cmd_ForwardToServer();
		return;

	}

	if ( pr_global_struct.deathmatch !== 0 && host_client.privileged === false )
		return;

	const t = Cmd_Argv( 1 );
	const v = parseInt( Cmd_Argv( 2 ) ) || 0;

	if ( t.length === 0 ) return;

	switch ( t[ 0 ] ) {

		case '2': case '3': case '4': case '5':
		case '6': case '7': case '8': {

			const IT_SHOTGUN = 1;
			if ( t.charCodeAt( 0 ) >= 50 ) // '2'
				sv_player.v.items = ( sv_player.v.items | 0 ) | ( IT_SHOTGUN << ( t.charCodeAt( 0 ) - 50 ) );
			break;

		}

		case 's':
			sv_player.v.ammo_shells = v;
			break;

		case 'n':
			sv_player.v.ammo_nails = v;
			break;

		case 'r':
			sv_player.v.ammo_rockets = v;
			break;

		case 'h':
			sv_player.v.health = v;
			break;

		case 'c':
			sv_player.v.ammo_cells = v;
			break;

	}

}

function Host_Ping_f() {

	if ( cmd_source === src_command ) {

		Cmd_ForwardToServer();
		return;

	}

	SV_ClientPrintf( 'Client ping times:\n' );

	for ( let i = 0; i < svs.maxclients; i ++ ) {

		const client = svs.clients[ i ];
		if ( client == null || client.active === false ) continue;

		let total = 0;
		for ( let j = 0; j < NUM_PING_TIMES; j ++ ) {

			total += client.ping_times[ j ];

		}

		total /= NUM_PING_TIMES;
		SV_ClientPrintf( '  ' + ( ( total * 1000 ) | 0 ) + ' ' + client.name + '\n' );

	}

}

function Host_Kick_f() {

	if ( cmd_source === src_command ) {

		if ( sv.active === false ) {

			Cmd_ForwardToServer();
			return;

		}

	} else if ( pr_global_struct.deathmatch !== 0 && host_client.privileged === false ) {

		return;

	}

	const save = host_client;

	let i;
	let byNumber = false;

	if ( Cmd_Argc() > 2 && Cmd_Argv( 1 ) === '#' ) {

		i = ( parseFloat( Cmd_Argv( 2 ) ) | 0 ) - 1;
		if ( i < 0 || i >= svs.maxclients ) return;
		if ( svs.clients[ i ] == null || svs.clients[ i ].active === false ) return;
		set_host_client( svs.clients[ i ] );
		byNumber = true;

	} else {

		for ( i = 0; i < svs.maxclients; i ++ ) {

			set_host_client( svs.clients[ i ] );
			if ( host_client == null || host_client.active === false ) continue;
			if ( host_client.name.toLowerCase() === Cmd_Argv( 1 ).toLowerCase() ) break;

		}

	}

	if ( i < svs.maxclients ) {

		let who;
		if ( cmd_source === src_command ) {

			if ( cls.state === ca_dedicated ) {

				who = 'Console';

			} else {

				who = cl_name.string;

			}

		} else {

			who = save.name;

		}

		// can't kick yourself!
		if ( host_client === save ) {

			set_host_client( save );
			return;

		}

		let message = null;
		if ( Cmd_Argc() > 2 ) {

			let args = Cmd_Args();
			if ( byNumber ) {

				// skip the # and number
				const numStr = Cmd_Argv( 2 );
				const hashIdx = args.indexOf( '#' );
				if ( hashIdx >= 0 ) {

					args = args.substring( hashIdx + 1 ).trim();
					args = args.substring( numStr.length ).trim();

				}

			}

			if ( args.length > 0 ) {

				message = args;

			}

		}

		if ( message != null ) {

			SV_ClientPrintf( 'Kicked by ' + who + ': ' + message + '\n' );

		} else {

			SV_ClientPrintf( 'Kicked by ' + who + '\n' );

		}

		SV_DropClient( false );

	}

	set_host_client( save );

}

const SAVEGAME_VERSION = 5;
const SAVE_STORAGE_PREFIX = 'quake_save_';

/*
===============
Host_SavegameComment

Writes a SAVEGAME_COMMENT_LENGTH character comment describing the current game
===============
*/
function Host_SavegameComment() {

	// Build comment: levelname padded to 22 chars, then kills:xxx/xxx
	let text = cl.levelname || '';
	while ( text.length < 22 ) text += ' ';
	text = text.substring( 0, 22 );

	const kills = 'kills:' + String( cl.stats[ STAT_MONSTERS ] ).padStart( 3, ' ' ) + '/' + String( cl.stats[ STAT_TOTALMONSTERS ] ).padStart( 3, ' ' );
	text += kills;

	// Pad to SAVEGAME_COMMENT_LENGTH
	while ( text.length < SAVEGAME_COMMENT_LENGTH ) text += ' ';
	text = text.substring( 0, SAVEGAME_COMMENT_LENGTH );

	// convert spaces to _ (original C format)
	return text.replace( / /g, '_' );

}

/*
===============
Host_Savegame_f
===============
*/
function Host_Savegame_f() {

	if ( cmd_source !== src_command ) return;

	if ( sv.active === false ) {

		Con_Printf( 'Not playing a local game.\n' );
		return;

	}

	if ( cl.intermission !== 0 ) {

		Con_Printf( 'Can\'t save in intermission.\n' );
		return;

	}

	if ( svs.maxclients !== 1 ) {

		Con_Printf( 'Can\'t save multiplayer games.\n' );
		return;

	}

	if ( Cmd_Argc() !== 2 ) {

		Con_Printf( 'save <savename> : save a game\n' );
		return;

	}

	if ( Cmd_Argv( 1 ).indexOf( '..' ) !== - 1 ) {

		Con_Printf( 'Relative pathnames are not allowed.\n' );
		return;

	}

	for ( let i = 0; i < svs.maxclients; i ++ ) {

		if ( svs.clients[ i ] != null && svs.clients[ i ].active && svs.clients[ i ].edict.v.health <= 0 ) {

			Con_Printf( 'Can\'t savegame with a dead player\n' );
			return;

		}

	}

	const name = Cmd_Argv( 1 );

	Con_Printf( 'Saving game to %s...\n', name );

	const lines = [];

	lines.push( String( SAVEGAME_VERSION ) );
	lines.push( Host_SavegameComment() );

	for ( let i = 0; i < NUM_SPAWN_PARMS; i ++ ) {

		lines.push( String( svs.clients[ 0 ].spawn_parms[ i ] ) );

	}

	lines.push( String( current_skill ) );
	lines.push( sv.name );
	lines.push( String( sv.time ) );

	// write the light styles
	for ( let i = 0; i < MAX_LIGHTSTYLES; i ++ ) {

		if ( sv.lightstyles[ i ] != null ) {

			lines.push( sv.lightstyles[ i ] );

		} else {

			lines.push( 'm' );

		}

	}

	// write globals
	ED_WriteGlobals( lines );

	// write all edicts
	for ( let i = 0; i < sv.num_edicts; i ++ ) {

		ED_Write( lines, EDICT_NUM( i ) );

	}

	// Store in localStorage
	const saveData = lines.join( '\n' ) + '\n';

	try {

		localStorage.setItem( SAVE_STORAGE_PREFIX + name, saveData );

	} catch ( e ) {

		Con_Printf( 'ERROR: couldn\'t save (localStorage full?).\n' );
		return;

	}

	Con_Printf( 'done.\n' );

}

/*
===============
Host_Loadgame_f
===============
*/
function Host_Loadgame_f() {

	if ( cmd_source !== src_command ) return;

	if ( Cmd_Argc() !== 2 ) {

		Con_Printf( 'load <savename> : load a game\n' );
		return;

	}

	cls.demonum = - 1; // stop demo loop in case this fails

	const name = Cmd_Argv( 1 );

	Con_Printf( 'Loading game from %s...\n', name );

	let saveData;

	try {

		saveData = localStorage.getItem( SAVE_STORAGE_PREFIX + name );

	} catch ( e ) {

		// ignore
	}

	if ( saveData == null ) {

		Con_Printf( 'ERROR: couldn\'t open.\n' );
		return;

	}

	// Parse the save file line by line
	const allLines = saveData.split( '\n' );
	let lineIdx = 0;

	function nextLine() {

		if ( lineIdx < allLines.length ) return allLines[ lineIdx ++ ];
		return '';

	}

	const version = parseInt( nextLine() );
	if ( version !== SAVEGAME_VERSION ) {

		Con_Printf( 'Savegame is version %i, not %i\n', version, SAVEGAME_VERSION );
		return;

	}

	nextLine(); // skip comment

	const spawn_parms = new Float32Array( NUM_SPAWN_PARMS );
	for ( let i = 0; i < NUM_SPAWN_PARMS; i ++ ) {

		spawn_parms[ i ] = parseFloat( nextLine() ) || 0;

	}

	// this silliness is so we can load 1.06 save files, which have float skill values
	const tfloat = parseFloat( nextLine() ) || 0;
	const loadSkill = ( tfloat + 0.1 ) | 0;
	Cvar_SetValue( 'skill', loadSkill );

	const mapname = nextLine();
	const time = parseFloat( nextLine() ) || 0;

	// If the map file isn't loaded yet, fetch it on demand
	const mapfilename = 'maps/' + mapname + '.bsp';
	if ( COM_FindFile( mapfilename ) === null ) {

		Con_Printf( 'Fetching %s...\n', mapfilename );
		COM_EnsureFile( mapfilename ).then( ( success ) => {

			if ( success ) {

				// Re-issue the load command (will re-parse save data from localStorage)
				Cbuf_AddText( 'load ' + name + '\n' );

			} else {

				Con_Printf( 'Couldn\'t find map: %s\n', mapname );

			}

		} );
		return;

	}

	CL_Disconnect();

	SV_SpawnServer( mapname );

	if ( sv.active === false ) {

		Con_Printf( 'Couldn\'t load map\n' );
		return;

	}

	sv.paused = true; // pause until all clients connect
	sv.loadgame = true;

	// load the light styles
	for ( let i = 0; i < MAX_LIGHTSTYLES; i ++ ) {

		sv.lightstyles[ i ] = nextLine();

	}

	// load the edicts out of the savegame file
	// Remaining lines form brace-delimited blocks: first is globals, then edicts
	let remaining = allLines.slice( lineIdx ).join( '\n' );
	let entnum = - 1; // -1 is the globals

	while ( remaining.length > 0 ) {

		// Find the next { ... } block
		const braceStart = remaining.indexOf( '{' );
		if ( braceStart === - 1 ) break;

		let braceEnd = remaining.indexOf( '}', braceStart );
		if ( braceEnd === - 1 ) break;

		const block = remaining.substring( braceStart, braceEnd + 1 );
		remaining = remaining.substring( braceEnd + 1 );

		// Parse the content inside braces
		let data = block;
		data = COM_Parse( data );
		if ( com_token.length === 0 ) break; // end of file
		if ( com_token !== '{' ) {

			Sys_Error( 'First token isn\'t a brace' );

		}

		if ( entnum === - 1 ) {

			// parse the global vars
			ED_ParseGlobals( data );

		} else {

			// parse an edict
			const ent = EDICT_NUM( entnum );
			ent.free = false;
			ED_ParseEdict( data, ent );

			// link it into the bsp tree
			if ( ent.free === false ) {

				SV_LinkEdict( ent, false );

			}

		}

		entnum ++;

	}

	sv.num_edicts = entnum;
	sv.time = time;

	for ( let i = 0; i < NUM_SPAWN_PARMS; i ++ ) {

		svs.clients[ 0 ].spawn_parms[ i ] = spawn_parms[ i ];

	}

	if ( cls.state !== ca_dedicated ) {

		CL_EstablishConnection( 'local' );
		Host_Reconnect_f();

	}

}

function Host_Startdemos_f() {

	if ( cls.state === ca_dedicated ) {

		if ( ! sv.active )
			Cbuf_AddText( 'map start\n' );
		return;

	}

	let c = Cmd_Argc() - 1;
	if ( c > MAX_DEMOS ) {

		Con_Printf( 'Max %i demos in demoloop\n', MAX_DEMOS );
		c = MAX_DEMOS;

	}

	Con_Printf( '%i demo(s) in loop\n', c );

	for ( let i = 1; i < c + 1; i ++ )
		cls.demos[ i - 1 ] = Cmd_Argv( i );

	if ( ! sv.active && cls.demonum !== - 1 && ! cls.demoplayback ) {

		cls.demonum = 0;
		CL_NextDemo();

	} else {

		cls.demonum = - 1;

	}

}

function Host_Demos_f() {

	if ( cls.state === ca_dedicated )
		return;
	if ( cls.demonum === - 1 )
		cls.demonum = 1;
	CL_Disconnect();
	CL_NextDemo();

}

function Host_Stopdemo_f() {

	if ( cls.state === ca_dedicated )
		return;
	if ( ! cls.demoplayback )
		return;
	CL_StopPlayback();
	CL_Disconnect();

}

/*
==================
Host_PreSpawn_f
==================
*/
function Host_PreSpawn_f() {

	if ( cmd_source === src_command ) {

		Con_Printf( 'prespawn is not valid from the console\n' );
		return;

	}

	if ( host_client.spawned ) {

		Con_Printf( 'prespawn not valid -- allready spawned\n' );
		return;

	}

	SZ_Write( host_client.message, sv.signon.data, sv.signon.cursize );
	MSG_WriteByte( host_client.message, svc_signonnum );
	MSG_WriteByte( host_client.message, 2 );
	host_client.sendsignon = true;

}

/*
==================
Host_Spawn_f
==================
*/
function Host_Spawn_f() {

	if ( cmd_source === src_command ) {

		Con_Printf( 'spawn is not valid from the console\n' );
		return;

	}

	if ( host_client.spawned ) {

		Con_Printf( 'Spawn not valid -- allready spawned\n' );
		return;

	}

	// run the entrance script
	if ( sv.loadgame ) {

		// loaded games are fully inited allready
		// if this is the last client to be connected, unpause
		sv.paused = false;

	} else {

		// set up the edict
		const ent = host_client.edict;

		// clear entity fields (C does: memset(&ent->v, 0, progs->entityfields * 4))
		ent.clearFields();

		// set key fields after clearing
		const colormap = NUM_FOR_EDICT( ent );
		const team = ( host_client.colors & 15 ) + 1;
		ent.v.colormap = colormap;
		ent.v.team = team;
		ent.v.netname = ED_NewString( host_client.name );

		// copy spawn parms out of the client_t
		if ( pr_global_struct ) {

			for ( let i = 0; i < NUM_SPAWN_PARMS; i ++ )
				pr_global_struct[ 'parm' + ( i + 1 ) ] = host_client.spawn_parms[ i ];

			// call the spawn function
			pr_global_struct.time = sv.time;
			pr_global_struct.self = EDICT_TO_PROG( sv_player );
			PR_ExecuteProgram( pr_global_struct.ClientConnect );

			if ( ( Sys_FloatTime() - host_client.netconnection.connecttime ) <= sv.time )
				Sys_Printf( '%s entered the game\n', host_client.name );

			PR_ExecuteProgram( pr_global_struct.PutClientInServer );

		}

	}

	// send all current names, colors, and frag counts
	SZ_Clear( host_client.message );

	// send time of update
	MSG_WriteByte( host_client.message, svc_time );
	MSG_WriteFloat( host_client.message, sv.time );

	for ( let i = 0; i < svs.maxclients; i ++ ) {

		const client = svs.clients[ i ];
		MSG_WriteByte( host_client.message, svc_updatename );
		MSG_WriteByte( host_client.message, i );
		MSG_WriteString( host_client.message, client.name );
		MSG_WriteByte( host_client.message, svc_updatefrags );
		MSG_WriteByte( host_client.message, i );
		MSG_WriteShort( host_client.message, client.old_frags );
		MSG_WriteByte( host_client.message, svc_updatecolors );
		MSG_WriteByte( host_client.message, i );
		MSG_WriteByte( host_client.message, client.colors );

	}

	// send all current light styles
	for ( let i = 0; i < MAX_LIGHTSTYLES; i ++ ) {

		MSG_WriteByte( host_client.message, svc_lightstyle );
		MSG_WriteByte( host_client.message, i );
		MSG_WriteString( host_client.message, sv.lightstyles[ i ] || '' );

	}

	// send some stats
	MSG_WriteByte( host_client.message, svc_updatestat );
	MSG_WriteByte( host_client.message, STAT_TOTALSECRETS );
	MSG_WriteLong( host_client.message, pr_global_struct ? pr_global_struct.total_secrets : 0 );

	MSG_WriteByte( host_client.message, svc_updatestat );
	MSG_WriteByte( host_client.message, STAT_TOTALMONSTERS );
	MSG_WriteLong( host_client.message, pr_global_struct ? pr_global_struct.total_monsters : 0 );

	MSG_WriteByte( host_client.message, svc_updatestat );
	MSG_WriteByte( host_client.message, STAT_SECRETS );
	MSG_WriteLong( host_client.message, pr_global_struct ? pr_global_struct.found_secrets : 0 );

	MSG_WriteByte( host_client.message, svc_updatestat );
	MSG_WriteByte( host_client.message, STAT_MONSTERS );
	MSG_WriteLong( host_client.message, pr_global_struct ? pr_global_struct.killed_monsters : 0 );

	// send a fixangle
	const ent = EDICT_NUM( 1 + svs.clients.indexOf( host_client ) );
	MSG_WriteByte( host_client.message, svc_setangle );
	for ( let i = 0; i < 2; i ++ )
		MSG_WriteAngle( host_client.message, ent.v.angles[ i ] );
	MSG_WriteAngle( host_client.message, 0 );

	SV_WriteClientdataToMessage( sv_player, host_client.message );

	MSG_WriteByte( host_client.message, svc_signonnum );
	MSG_WriteByte( host_client.message, 3 );
	host_client.sendsignon = true;

}

/*
==================
Host_Begin_f
==================
*/
function Host_Begin_f() {

	if ( cmd_source === src_command ) {

		Con_Printf( 'begin is not valid from the console\n' );
		return;

	}

	host_client.spawned = true;

}
