// Ported from: WinQuake/cl_parse.c -- parse a message received from the server

import { MAX_MODELS, MAX_SOUNDS, MAX_EDICTS, MAX_LIGHTSTYLES,
	MAX_CL_STATS, MAX_SCOREBOARD,
	STAT_HEALTH, STAT_FRAGS, STAT_WEAPON, STAT_AMMO, STAT_ARMOR,
	STAT_WEAPONFRAME, STAT_SHELLS, STAT_ACTIVEWEAPON, STAT_MONSTERS,
	STAT_SECRETS, entity_state_t } from './quakedef.js';
import { Con_Printf, Con_DPrintf, SZ_Clear,
	MSG_BeginReading, MSG_ReadByte, MSG_ReadChar, MSG_ReadShort, MSG_ReadLong,
	MSG_ReadFloat, MSG_ReadString, MSG_ReadCoord, MSG_ReadAngle,
	MSG_ReadAngle16,
	MSG_WriteByte,
	msg_readcount, msg_badread,
	net_message, standard_quake } from './common.js';
import { Sys_Error, Sys_FloatTime } from './sys.js';
import { COM_FindFile, COM_EnsureFile } from './pak.js';
import { Cbuf_AddText } from './cmd.js';
import { Cmd_ExecuteString } from './cmd.js';
import { src_command } from './cmd.js';
import {
	PROTOCOL_VERSION,
	svc_bad, svc_nop, svc_disconnect, svc_updatestat, svc_version,
	svc_setview, svc_sound, svc_time, svc_print, svc_stufftext,
	svc_setangle, svc_serverinfo, svc_lightstyle, svc_updatename,
	svc_updatefrags, svc_clientdata, svc_stopsound, svc_updatecolors,
	svc_particle, svc_damage, svc_spawnstatic, svc_spawnbaseline,
	svc_temp_entity, svc_setpause, svc_signonnum, svc_centerprint,
	svc_killedmonster, svc_foundsecret, svc_spawnstaticsound,
	svc_intermission, svc_finale, svc_cdtrack, svc_sellscreen,
	svc_cutscene,
	svc_playerinfo, PF_MSEC, PF_COMMAND, PF_VELOCITY1, PF_VELOCITY2, PF_VELOCITY3,
	PF_MODEL, PF_SKINNUM, PF_EFFECTS, PF_WEAPONFRAME, PF_DEAD, PF_GIB,
	CM_ANGLE1, CM_ANGLE2, CM_ANGLE3, CM_FORWARD, CM_SIDE, CM_UP, CM_BUTTONS, CM_IMPULSE,
	clc_nop,
	SND_VOLUME, SND_ATTENUATION,
	DEFAULT_VIEWHEIGHT,
	SU_VIEWHEIGHT, SU_IDEALPITCH, SU_PUNCH1, SU_VELOCITY1,
	SU_ITEMS, SU_ONGROUND, SU_INWATER, SU_WEAPONFRAME,
	SU_ARMOR, SU_WEAPON,
	U_MOREBITS, U_ORIGIN1, U_ORIGIN2, U_ORIGIN3,
	U_ANGLE1, U_ANGLE2, U_ANGLE3,
	U_MODEL, U_FRAME, U_COLORMAP, U_SKIN, U_EFFECTS,
	U_LONGENTITY, U_NOLERP,
	DEFAULT_SOUND_PACKET_VOLUME, DEFAULT_SOUND_PACKET_ATTENUATION,
	svc_packetentities, svc_deltapacketentities, svc_serversequence,
	PE_ENT_BITS, PE_ENT_MASK, PE_ORIGIN1, PE_ORIGIN2, PE_ORIGIN3,
	PE_ANGLE2, PE_REMOVE, PE_MOREBITS,
	PE_FRAME, PE_ANGLE1, PE_ANGLE3, PE_MODEL, PE_COLORMAP, PE_SKIN, PE_EFFECTS, PE_SOLID,
	MAX_PACKET_ENTITIES, PE_UPDATE_BACKUP, PE_UPDATE_MASK
} from './protocol.js';
import {
	SIGNONS, MAX_STATIC_ENTITIES, MAX_DLIGHTS,
	ca_connected,
	cl, cls, cl_entities, cl_static_entities, cl_lightstyle,
	entity_t, scoreboard_t, lightstyle_t, packet_entities_t } from './client.js';
import { VectorCopy } from './mathlib.js';
import { V_ParseDamage } from './view.js';
import { Mod_ForName } from './gl_model.js';
import { CL_SetServerState, CL_AcknowledgeCommand, CL_AcknowledgeTransportSequence,
	CL_FindAcknowledgedSequence,
	CL_SetValidSequence, CL_SetPlayerInfo,
	CL_GetServerSequence, CL_SetServerSequence, CL_GetFrame, CL_GetEntityFrame,
	CL_GetValidSequence } from './cl_pred.js';
import { R_TranslatePlayerSkin } from './gl_rmisc.js';

// QuakeWorld model precache indices (set during CL_ParseServerInfo)
export let cl_playerindex = -1;
import { R_NewMap } from './gl_rmisc.js';
import { R_ParseParticleEffect, R_AddEfrags } from './render.js';
import { Host_Error, Host_EndGame, realtime } from './host.js';
import { set_noclip_anglehack } from './host_cmd.js';
import { CL_SignonReply, CL_ClearState, cl_shownet } from './cl_main.js';
import { CL_ParseTEnt } from './cl_tent.js';
import { S_PrecacheSound, S_StartSound, S_StopSound, S_StaticSound } from './snd_dma.js';
import { CDAudio_Play, CDAudio_Pause, CDAudio_Resume } from './cd_audio.js';
import { SCR_CenterPrint } from './gl_screen.js';

export const svc_strings = [
	'svc_bad',
	'svc_nop',
	'svc_disconnect',
	'svc_updatestat',
	'svc_version', // [long] server version
	'svc_setview', // [short] entity number
	'svc_sound', // <see code>
	'svc_time', // [float] server time
	'svc_print', // [string] null terminated string
	'svc_stufftext', // [string] stuffed into client\'s console buffer
	'svc_setangle', // [vec3] set the view angle to this absolute value

	'svc_serverinfo', // [long] version ...
	'svc_lightstyle', // [byte] [string]
	'svc_updatename', // [byte] [string]
	'svc_updatefrags', // [byte] [short]
	'svc_clientdata', // <shortbits + data>
	'svc_stopsound', // <see code>
	'svc_updatecolors', // [byte] [byte]
	'svc_particle', // [vec3] <variable>
	'svc_damage', // [byte] impact [byte] blood [vec3] from

	'svc_spawnstatic',
	'OBSOLETE svc_spawnbinary',
	'svc_spawnbaseline',

	'svc_temp_entity', // <variable>
	'svc_setpause',
	'svc_signonnum',
	'svc_centerprint',
	'svc_killedmonster',
	'svc_foundsecret',
	'svc_spawnstaticsound',
	'svc_intermission',
	'svc_finale', // [string] music [string] text
	'svc_cdtrack', // [byte] track [byte] looptrack
	'svc_sellscreen',
	'svc_cutscene'
];

//=============================================================================

/*
===============
CL_EntityNum

This error checks and tracks the total number of entities
===============
*/
export function CL_EntityNum( num ) {

	if ( num >= cl.num_entities ) {

		if ( num >= MAX_EDICTS )
			Host_Error( 'CL_EntityNum: %i is an invalid number', num );
		while ( cl.num_entities <= num ) {

			cl_entities[ cl.num_entities ].colormap = null; // vid.colormap
			cl.num_entities ++;

		}

	}

	return cl_entities[ num ];

}

/*
==================
CL_ParseStartSoundPacket
==================
*/
export function CL_ParseStartSoundPacket() {

	const pos = _soundPos;

	const field_mask = MSG_ReadByte();

	let volume;
	if ( field_mask & SND_VOLUME )
		volume = MSG_ReadByte();
	else
		volume = DEFAULT_SOUND_PACKET_VOLUME;

	let attenuation;
	if ( field_mask & SND_ATTENUATION )
		attenuation = MSG_ReadByte() / 64.0;
	else
		attenuation = DEFAULT_SOUND_PACKET_ATTENUATION;

	const channel = MSG_ReadShort();
	const sound_num = MSG_ReadByte();

	const ent = channel >> 3;
	const ch = channel & 7;

	if ( ent > MAX_EDICTS )
		Host_Error( 'CL_ParseStartSoundPacket: ent = %i', ent );

	for ( let i = 0; i < 3; i ++ )
		pos[ i ] = MSG_ReadCoord();

	const sfx = cl.sound_precache[ sound_num ];
	if ( ! sfx ) {

		Con_Printf( 'CL_ParseStartSoundPacket: sound_num %d not precached\n', sound_num );
		return;

	}

	// Debug: log parsed sound packet
	if ( cl_shownet.value >= 2 ) {

		Con_Printf( 'svc_sound: %s (num=%d ent=%d ch=%d)\n', sfx.name, sound_num, ent, ch );

	}

	S_StartSound( ent, ch, sfx, pos, volume / 255.0, attenuation );

}

/*
==================
CL_KeepaliveMessage

When the client is taking a long time to load stuff, send keepalive messages
so the server doesn't disconnect.
==================
*/
let _keepalive_lastmsg = 0;

export function CL_KeepaliveMessage() {

	// if ( sv.active )
	//     return;  // no need if server is local
	if ( cls.demoplayback )
		return;

	// check time
	const time = Sys_FloatTime();
	if ( time - _keepalive_lastmsg < 5 )
		return;
	_keepalive_lastmsg = time;

	// write out a nop
	Con_Printf( '--> client to server keepalive\n' );

	MSG_WriteByte( cls.message, clc_nop );
	// NET_SendMessage( cls.netcon, cls.message );
	SZ_Clear( cls.message );

}

/*
==================
CL_ParseServerInfo
==================
*/
export function CL_ParseServerInfo() {

	Con_DPrintf( 'Serverinfo packet received.\n' );

	//
	// wipe the client_state_t struct
	//
	CL_ClearState();

	// parse protocol version number
	let i = MSG_ReadLong();
	if ( i !== PROTOCOL_VERSION ) {

		Con_Printf( 'Server returned version %i, not %i', i, PROTOCOL_VERSION );
		return;

	}

	// parse maxclients
	cl.maxclients = MSG_ReadByte();
	if ( cl.maxclients < 1 || cl.maxclients > MAX_SCOREBOARD ) {

		Con_Printf( 'Bad maxclients (%u) from server\n', cl.maxclients );
		return;

	}

	cl.scores = [];
	for ( let j = 0; j < cl.maxclients; j ++ )
		cl.scores.push( new scoreboard_t() );

	// parse gametype
	cl.gametype = MSG_ReadByte();

	// parse signon message
	const str = MSG_ReadString();
	cl.levelname = str.substring( 0, 39 );

	// seperate the printfs so the server message can have a color
	Con_Printf( '\n\n\x1d\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1f\n\n' );
	Con_Printf( '%s\n', str );

	//
	// precache models
	//
	cl.model_precache.fill( null );
	const model_precache = [];
	model_precache[ 0 ] = '';
	cl_playerindex = -1;
	let nummodels;
	for ( nummodels = 1; ; nummodels ++ ) {

		const s = MSG_ReadString();
		if ( s.length === 0 )
			break;
		if ( nummodels === MAX_MODELS ) {

			Con_Printf( 'Server sent too many model precaches\n' );
			return;

		}

		model_precache[ nummodels ] = s;

		if ( s === 'progs/player.mdl' )
			cl_playerindex = nummodels;

	}

	// precache sounds
	cl.sound_precache.fill( null );
	const sound_precache = [];
	sound_precache[ 0 ] = '';
	let numsounds;
	for ( numsounds = 1; ; numsounds ++ ) {

		const s = MSG_ReadString();
		if ( ! s.length )
			break;
		if ( numsounds === MAX_SOUNDS ) {

			Con_Printf( 'Server sent too many sound precaches\n' );
			return;

		}

		sound_precache[ numsounds ] = s;
		// S_TouchSound( s );

	}

	//
	// now we try to load everything else until a cache allocation fails
	//

	// Lazy-load: if the world BSP isn't cached yet, fetch it on demand and reconnect
	if ( nummodels > 1 && COM_FindFile( model_precache[ 1 ] ) === null ) {

		const addr = cls.netcon != null ? cls.netcon.address : null;
		Con_Printf( 'Fetching %s...\n', model_precache[ 1 ] );
		COM_EnsureFile( model_precache[ 1 ] ).then( ( success ) => {

			if ( success && addr != null ) {

				Cbuf_AddText( 'connect "' + addr + '"\n' );

			} else {

				Con_Printf( 'Couldn\'t fetch %s\n', model_precache[ 1 ] );

			}

		} );
		return;

	}

	for ( i = 1; i < nummodels; i ++ ) {

		cl.model_precache[ i ] = Mod_ForName( model_precache[ i ], false );
		if ( cl.model_precache[ i ] === null ) {

			Con_Printf( 'Model %s not found\n', model_precache[ i ] );
			return;

		}

		CL_KeepaliveMessage();

	}

	// S_BeginPrecaching();
	Con_DPrintf( 'Sound precache list:\n' );
	for ( i = 1; i < numsounds; i ++ ) {

		cl.sound_precache[ i ] = S_PrecacheSound( sound_precache[ i ] );
		Con_DPrintf( '  %d: %s\n', i, sound_precache[ i ] );
		CL_KeepaliveMessage();

	}
	// S_EndPrecaching();

	// local state
	cl_entities[ 0 ].model = cl.worldmodel = cl.model_precache[ 1 ];

	R_NewMap( cl );

	// Hunk_Check();

	set_noclip_anglehack( false );

}

/*
==================
CL_ParseDelta

Parse a QW-style delta-compressed entity state.
Can delta from either a baseline or a previous packet_entity.
Ported from: QW/client/cl_ents.c
==================
*/
function CL_ParseDelta( from, to, bits ) {

	// set everything to the state we are delta'ing from
	to.copyFrom( from );

	to.number = bits & PE_ENT_MASK;
	bits &= ~PE_ENT_MASK;

	if ( bits & PE_MOREBITS ) {

		// read in the low order bits
		const i = MSG_ReadByte();
		bits |= i;

	}

	to.flags = bits;

	if ( bits & PE_MODEL )
		to.modelindex = MSG_ReadByte();

	if ( bits & PE_FRAME )
		to.frame = MSG_ReadByte();

	if ( bits & PE_COLORMAP )
		to.colormap = MSG_ReadByte();

	if ( bits & PE_SKIN )
		to.skin = MSG_ReadByte();

	if ( bits & PE_EFFECTS )
		to.effects = MSG_ReadByte();

	if ( bits & PE_ORIGIN1 )
		to.origin[ 0 ] = MSG_ReadCoord();

	if ( bits & PE_ANGLE1 )
		to.angles[ 0 ] = MSG_ReadAngle();

	if ( bits & PE_ORIGIN2 )
		to.origin[ 1 ] = MSG_ReadCoord();

	if ( bits & PE_ANGLE2 )
		to.angles[ 1 ] = MSG_ReadAngle();

	if ( bits & PE_ORIGIN3 )
		to.origin[ 2 ] = MSG_ReadCoord();

	if ( bits & PE_ANGLE3 )
		to.angles[ 2 ] = MSG_ReadAngle();

}

/*
=================
FlushEntityPacket

Read and discard all entity data in the packet (on parse error).
Ported from: QW/client/cl_ents.c
=================
*/
const _flushOlde = new entity_state_t();
const _flushNewe = new entity_state_t();

function FlushEntityPacket() {

	Con_DPrintf( 'FlushEntityPacket\n' );

	CL_SetValidSequence( 0 ); // can't render a frame

	const seq = CL_GetServerSequence();
	CL_GetEntityFrame( seq ).invalid = true;

	// read it all, but ignore it
	while ( true ) {

		const word = MSG_ReadShort() & 0xFFFF;
		if ( msg_badread ) {

			Host_EndGame( 'msg_badread in packetentities' );
			return;

		}

		if ( word === 0 )
			break; // done

		CL_ParseDelta( _flushOlde, _flushNewe, word );

	}

}

/*
==================
CL_ParsePacketEntities

An svc_packetentities has just been parsed, deal with the
rest of the data stream.
Ported from: QW/client/cl_ents.c
==================
*/
function CL_ParsePacketEntities( delta ) {

	// First entity update completes the signon process
	// (same as CL_ParseUpdate does for NQ-style updates)
	if ( cls.signon === SIGNONS - 1 ) {

		cls.signon = SIGNONS;
		CL_SignonReply();

	}

	const seq = CL_GetServerSequence();
	const eframe = CL_GetEntityFrame( seq );
	const newp = eframe.packet_entities;
	eframe.invalid = false;

	let oldpacket;
	if ( delta ) {

		const from = MSG_ReadByte();
		oldpacket = from;

	} else {

		oldpacket = - 1;

	}

	let full = false;
	let oldp;
	if ( oldpacket !== - 1 ) {

		let frameDiff = ( seq & 255 ) - oldpacket;
		if ( frameDiff < 0 ) frameDiff += 256;
		if ( frameDiff >= PE_UPDATE_BACKUP - 1 ) {

			// we can't use this, it is too old
			FlushEntityPacket();
			return;

		}

		CL_SetValidSequence( seq );
		oldp = CL_GetEntityFrame( oldpacket ).packet_entities;

	} else {

		// this is a full update that we can start delta compressing from now
		oldp = _emptyPacket;
		CL_SetValidSequence( seq );
		full = true;

	}

	let oldindex = 0;
	let newindex = 0;
	newp.num_entities = 0;

	while ( true ) {

		const word = MSG_ReadShort() & 0xFFFF;
		if ( msg_badread ) {

			Host_EndGame( 'msg_badread in packetentities' );
			return;

		}

		if ( word === 0 ) {

			// copy all the rest of the entities from the old packet
			while ( oldindex < oldp.num_entities ) {

				if ( newindex >= MAX_PACKET_ENTITIES ) {

					Host_EndGame( 'CL_ParsePacketEntities: newindex == MAX_PACKET_ENTITIES' );
					return;

				}

				newp.entities[ newindex ].copyFrom( oldp.entities[ oldindex ] );
				newindex ++;
				oldindex ++;

			}

			break;

		}

		const newnum = word & PE_ENT_MASK;
		let oldnum = oldindex >= oldp.num_entities ? 9999 : oldp.entities[ oldindex ].number;

		// copy unchanged old entities that sort before this new entry
		while ( newnum > oldnum ) {

			if ( full ) {

				Con_Printf( 'WARNING: oldcopy on full update' );
				FlushEntityPacket();
				return;

			}

			// copy one of the old entities over to the new packet unchanged
			if ( newindex >= MAX_PACKET_ENTITIES ) {

				Host_EndGame( 'CL_ParsePacketEntities: newindex == MAX_PACKET_ENTITIES' );
				return;

			}

			newp.entities[ newindex ].copyFrom( oldp.entities[ oldindex ] );
			newindex ++;
			oldindex ++;
			oldnum = oldindex >= oldp.num_entities ? 9999 : oldp.entities[ oldindex ].number;

		}

		if ( newnum < oldnum ) {

			// new from baseline
			if ( word & PE_REMOVE ) {

				if ( full ) {

					CL_SetValidSequence( 0 );
					Con_Printf( 'WARNING: U_REMOVE on full update\n' );
					FlushEntityPacket();
					return;

				}

				continue;

			}

			if ( newindex >= MAX_PACKET_ENTITIES ) {

				Host_EndGame( 'CL_ParsePacketEntities: newindex == MAX_PACKET_ENTITIES' );
				return;

			}

			CL_ParseDelta( cl_entities[ newnum ].baseline, newp.entities[ newindex ], word );
			newindex ++;
			continue;

		}

		if ( newnum === oldnum ) {

			// delta from previous
			if ( full ) {

				CL_SetValidSequence( 0 );
				Con_Printf( 'WARNING: delta on full update' );

			}

			if ( word & PE_REMOVE ) {

				oldindex ++;
				continue;

			}

			if ( newindex >= MAX_PACKET_ENTITIES ) {

				Host_EndGame( 'CL_ParsePacketEntities: newindex == MAX_PACKET_ENTITIES' );
				return;

			}

			CL_ParseDelta( oldp.entities[ oldindex ], newp.entities[ newindex ], word );
			newindex ++;
			oldindex ++;

		}

	}

	newp.num_entities = newindex;

}

// Empty packet for full updates (no old data)
const _emptyPacket = { num_entities: 0, entities: [] };

/*
==================
CL_ParseUpdate

Parse an entity update message from the server
If an entities model or origin changes from frame to frame, it must be
relinked. Other attributes can change without relinking.
==================
*/
const bitcounts = new Int32Array( 16 );

// Reusable vectors for per-frame parsing (avoid per-call allocations)
const _soundPos = new Float32Array( 3 );
const _staticSoundOrg = new Float32Array( 3 );

// Cached buffers for CL_ParsePlayerInfo (Golden Rule #4)
const _playerinfo_origin = new Float32Array( 3 );
const _playerinfo_velocity = new Float32Array( 3 );
const _playerinfo_cmd_angles = new Float32Array( 3 );
const _playerinfo_cmd = {
	msec: 0,
	angles: _playerinfo_cmd_angles,
	forwardmove: 0,
	sidemove: 0,
	upmove: 0,
	buttons: 0,
	impulse: 0
};

export function CL_ParseUpdate( bits ) {

	if ( cls.signon === SIGNONS - 1 ) {

		// first update is the final signon stage
		cls.signon = SIGNONS;
		CL_SignonReply();

	}

	if ( bits & U_MOREBITS ) {

		const i = MSG_ReadByte();
		bits |= ( i << 8 );

	}

	let num;
	if ( bits & U_LONGENTITY )
		num = MSG_ReadShort();
	else
		num = MSG_ReadByte();

	const ent = CL_EntityNum( num );

	for ( let i = 0; i < 16; i ++ )
		if ( bits & ( 1 << i ) )
			bitcounts[ i ] ++;

	let forcelink;
	if ( ent.msgtime !== cl.mtime[ 1 ] )
		forcelink = true; // no previous frame to lerp from
	else
		forcelink = false;

	ent.msgtime = cl.mtime[ 0 ];

	let modnum;
	if ( bits & U_MODEL ) {

		modnum = MSG_ReadByte();
		if ( modnum >= MAX_MODELS )
			Host_Error( 'CL_ParseModel: bad modnum' );

	} else
		modnum = ent.baseline.modelindex;

	const model = cl.model_precache[ modnum ];
	if ( model !== ent.model ) {

		ent.model = model;
		// automatic animation (torches, etc) can be either all together
		// or randomized
		if ( model != null ) {

			if ( model.synctype === 1 ) // ST_RAND
				ent.syncbase = ( Math.random() * 0x7fff | 0 ) / 0x7fff;
			else
				ent.syncbase = 0.0;

		} else
			forcelink = true; // hack to make null model players work

		if ( num > 0 && num <= cl.maxclients )
			R_TranslatePlayerSkin( num - 1 );

	}

	if ( bits & U_FRAME )
		ent.frame = MSG_ReadByte();
	else
		ent.frame = ent.baseline.frame;

	let i;
	if ( bits & U_COLORMAP )
		i = MSG_ReadByte();
	else
		i = ent.baseline.colormap;
	if ( i === 0 )
		ent.colormap = null; // vid.colormap
	else {

		if ( i > cl.maxclients ) {

			console.error( 'colormap error: i=' + i + ', cl.maxclients=' + cl.maxclients + ', entity=' + num + ', bits=' + bits.toString( 16 ) );
			Sys_Error( 'i >= cl.maxclients' );

		}

		ent.colormap = cl.scores[ i - 1 ].translations;

	}

	let skin;
	if ( bits & U_SKIN )
		skin = MSG_ReadByte();
	else
		skin = ent.baseline.skin;
	if ( skin !== ent.skinnum ) {

		ent.skinnum = skin;
		if ( num > 0 && num <= cl.maxclients )
			R_TranslatePlayerSkin( num - 1 );

	}

	if ( bits & U_EFFECTS )
		ent.effects = MSG_ReadByte();
	else
		ent.effects = ent.baseline.effects;

	// shift the known values for interpolation
	VectorCopy( ent.msg_origins[ 0 ], ent.msg_origins[ 1 ] );
	VectorCopy( ent.msg_angles[ 0 ], ent.msg_angles[ 1 ] );

	if ( bits & U_ORIGIN1 )
		ent.msg_origins[ 0 ][ 0 ] = MSG_ReadCoord();
	else
		ent.msg_origins[ 0 ][ 0 ] = ent.baseline.origin[ 0 ];
	if ( bits & U_ANGLE1 )
		ent.msg_angles[ 0 ][ 0 ] = MSG_ReadAngle();
	else
		ent.msg_angles[ 0 ][ 0 ] = ent.baseline.angles[ 0 ];

	if ( bits & U_ORIGIN2 )
		ent.msg_origins[ 0 ][ 1 ] = MSG_ReadCoord();
	else
		ent.msg_origins[ 0 ][ 1 ] = ent.baseline.origin[ 1 ];
	if ( bits & U_ANGLE2 )
		ent.msg_angles[ 0 ][ 1 ] = MSG_ReadAngle();
	else
		ent.msg_angles[ 0 ][ 1 ] = ent.baseline.angles[ 1 ];

	if ( bits & U_ORIGIN3 )
		ent.msg_origins[ 0 ][ 2 ] = MSG_ReadCoord();
	else
		ent.msg_origins[ 0 ][ 2 ] = ent.baseline.origin[ 2 ];
	if ( bits & U_ANGLE3 )
		ent.msg_angles[ 0 ][ 2 ] = MSG_ReadAngle();
	else
		ent.msg_angles[ 0 ][ 2 ] = ent.baseline.angles[ 2 ];

	if ( bits & U_NOLERP )
		ent.forcelink = true;

	if ( forcelink ) {

		// didn't have an update last message
		VectorCopy( ent.msg_origins[ 0 ], ent.msg_origins[ 1 ] );
		VectorCopy( ent.msg_origins[ 0 ], ent.origin );
		VectorCopy( ent.msg_angles[ 0 ], ent.msg_angles[ 1 ] );
		VectorCopy( ent.msg_angles[ 0 ], ent.angles );
		ent.forcelink = true;

	}

}

/*
==================
CL_ParseBaseline
==================
*/
export function CL_ParseBaseline( ent ) {

	ent.baseline.modelindex = MSG_ReadByte();
	ent.baseline.frame = MSG_ReadByte();
	ent.baseline.colormap = MSG_ReadByte();
	ent.baseline.skin = MSG_ReadByte();
	for ( let i = 0; i < 3; i ++ ) {

		ent.baseline.origin[ i ] = MSG_ReadCoord();
		ent.baseline.angles[ i ] = MSG_ReadAngle();

	}

}

/*
==================
CL_ParseClientdata

Server information pertaining to this client only
==================
*/
export function CL_ParseClientdata( bits ) {

	if ( bits & SU_VIEWHEIGHT )
		cl.viewheight = MSG_ReadChar();
	else
		cl.viewheight = DEFAULT_VIEWHEIGHT;

	if ( bits & SU_IDEALPITCH )
		cl.idealpitch = MSG_ReadChar();
	else
		cl.idealpitch = 0;

	VectorCopy( cl.mvelocity[ 0 ], cl.mvelocity[ 1 ] );
	for ( let i = 0; i < 3; i ++ ) {

		if ( bits & ( SU_PUNCH1 << i ) )
			cl.punchangle[ i ] = MSG_ReadChar();
		else
			cl.punchangle[ i ] = 0;
		if ( bits & ( SU_VELOCITY1 << i ) )
			cl.mvelocity[ 0 ][ i ] = MSG_ReadChar() * 16;
		else
			cl.mvelocity[ 0 ][ i ] = 0;

	}

	// [always sent]  if (bits & SU_ITEMS)
	let i = MSG_ReadLong();

	if ( cl.items !== i ) {

		// set flash times
		// Sbar_Changed();
		for ( let j = 0; j < 32; j ++ )
			if ( ( i & ( 1 << j ) ) && ! ( cl.items & ( 1 << j ) ) )
				cl.item_gettime[ j ] = cl.time;
		cl.items = i;

	}

	cl.onground = ( bits & SU_ONGROUND ) !== 0;
	cl.inwater = ( bits & SU_INWATER ) !== 0;

	if ( bits & SU_WEAPONFRAME )
		cl.stats[ STAT_WEAPONFRAME ] = MSG_ReadByte();
	else
		cl.stats[ STAT_WEAPONFRAME ] = 0;

	if ( bits & SU_ARMOR )
		i = MSG_ReadByte();
	else
		i = 0;
	if ( cl.stats[ STAT_ARMOR ] !== i ) {

		cl.stats[ STAT_ARMOR ] = i;
		// Sbar_Changed();

	}

	if ( bits & SU_WEAPON )
		i = MSG_ReadByte();
	else
		i = 0;
	if ( cl.stats[ STAT_WEAPON ] !== i ) {

		cl.stats[ STAT_WEAPON ] = i;
		// Sbar_Changed();

	}

	i = MSG_ReadShort();
	if ( cl.stats[ STAT_HEALTH ] !== i ) {

		cl.stats[ STAT_HEALTH ] = i;
		// Sbar_Changed();

	}

	i = MSG_ReadByte();
	if ( cl.stats[ STAT_AMMO ] !== i ) {

		cl.stats[ STAT_AMMO ] = i;
		// Sbar_Changed();

	}

	for ( i = 0; i < 4; i ++ ) {

		const j = MSG_ReadByte();
		if ( cl.stats[ STAT_SHELLS + i ] !== j ) {

			cl.stats[ STAT_SHELLS + i ] = j;
			// Sbar_Changed();

		}

	}

	i = MSG_ReadByte();

	if ( standard_quake ) {

		if ( cl.stats[ STAT_ACTIVEWEAPON ] !== i ) {

			cl.stats[ STAT_ACTIVEWEAPON ] = i;
			// Sbar_Changed();

		}

	} else {

		if ( cl.stats[ STAT_ACTIVEWEAPON ] !== ( 1 << i ) ) {

			cl.stats[ STAT_ACTIVEWEAPON ] = ( 1 << i );
			// Sbar_Changed();

		}

	}

	//
	// Update client-side prediction with authoritative server state
	// This provides the base position/velocity for prediction to build on
	//
	if ( cl.viewentity >= 1 && cl.viewentity < cl_entities.length ) {

		// QuakeWorld-style reconciliation baseline:
		// use the latest transport-level ack from server.
		if ( cls.netcon != null ) {

			const ackSeq = cls.netcon.ackSequence | 0;
			if ( ackSeq >= 0 ) {

				CL_AcknowledgeTransportSequence( ackSeq );

			} else {

				const fallbackAckSeq = CL_FindAcknowledgedSequence( realtime );
				if ( fallbackAckSeq >= 0 )
					CL_AcknowledgeCommand( fallbackAckSeq );

			}

		}

		// Then set the server state on the newly acknowledged frame
		// This provides the base position/velocity for prediction replay
		const ent = cl_entities[ cl.viewentity ];
		CL_SetServerState( ent.msg_origins[ 0 ], cl.mvelocity[ 0 ], cl.onground );

	}

}

/*
==================
CL_ParsePlayerInfo

QuakeWorld-style player info for client-side prediction.
Parses svc_playerinfo message containing player state for other players.
==================
*/
function CL_ParsePlayerInfo() {

	const playernum = MSG_ReadByte();
	const flags = MSG_ReadShort();

	// Always read origin and frame
	const origin = _playerinfo_origin;
	origin[ 0 ] = MSG_ReadCoord();
	origin[ 1 ] = MSG_ReadCoord();
	origin[ 2 ] = MSG_ReadCoord();

	const frame = MSG_ReadByte();

	// Read optional msec
	let msec = 0;
	if ( flags & PF_MSEC )
		msec = MSG_ReadByte();

	// Read optional usercmd_t (delta compressed)
	let cmd = null;
	if ( flags & PF_COMMAND ) {

		const cmdbits = MSG_ReadByte();
		cmd = _playerinfo_cmd;
		cmd.msec = 0;
		_playerinfo_cmd_angles.fill( 0 );
		cmd.forwardmove = 0;
		cmd.sidemove = 0;
		cmd.upmove = 0;
		cmd.buttons = 0;
		cmd.impulse = 0;

		if ( cmdbits & CM_ANGLE1 )
			cmd.angles[ 0 ] = MSG_ReadAngle16();
		if ( cmdbits & CM_ANGLE2 )
			cmd.angles[ 1 ] = MSG_ReadAngle16();
		if ( cmdbits & CM_ANGLE3 )
			cmd.angles[ 2 ] = MSG_ReadAngle16();
		if ( cmdbits & CM_FORWARD )
			cmd.forwardmove = MSG_ReadShort();
		if ( cmdbits & CM_SIDE )
			cmd.sidemove = MSG_ReadShort();
		if ( cmdbits & CM_UP )
			cmd.upmove = MSG_ReadShort();
		if ( cmdbits & CM_BUTTONS )
			cmd.buttons = MSG_ReadByte();
		if ( cmdbits & CM_IMPULSE )
			cmd.impulse = MSG_ReadByte();

	}

	// Read optional velocity
	const velocity = _playerinfo_velocity;
	velocity[ 0 ] = 0;
	velocity[ 1 ] = 0;
	velocity[ 2 ] = 0;
	if ( flags & PF_VELOCITY1 )
		velocity[ 0 ] = MSG_ReadShort();
	if ( flags & PF_VELOCITY2 )
		velocity[ 1 ] = MSG_ReadShort();
	if ( flags & PF_VELOCITY3 )
		velocity[ 2 ] = MSG_ReadShort();

	// Read optional model (default to player model if not specified)
	let modelindex = cl_playerindex;
	if ( flags & PF_MODEL )
		modelindex = MSG_ReadByte();

	// Read optional skin
	let skin = 0;
	if ( flags & PF_SKINNUM )
		skin = MSG_ReadByte();

	// Read optional effects
	let effects = 0;
	if ( flags & PF_EFFECTS )
		effects = MSG_ReadByte();

	// Read optional weaponframe
	let weaponframe = 0;
	if ( flags & PF_WEAPONFRAME )
		weaponframe = MSG_ReadByte();

	// Store the player info for prediction and rendering
	CL_SetPlayerInfo( playernum, origin, velocity, frame, flags, skin, effects, weaponframe, msec, cmd, modelindex );

}

/*
=====================
CL_NewTranslation
=====================
*/
export function CL_NewTranslation( slot ) {

	if ( slot > cl.maxclients )
		Sys_Error( 'CL_NewTranslation: slot > cl.maxclients' );

	R_TranslatePlayerSkin( slot );

}

/*
=====================
CL_ParseStatic
=====================
*/
export function CL_ParseStatic() {

	const i = cl.num_statics;
	if ( i >= MAX_STATIC_ENTITIES )
		Host_Error( 'Too many static entities' );
	const ent = cl_static_entities[ i ];
	cl.num_statics ++;
	CL_ParseBaseline( ent );

	// copy it to the current state
	ent.model = cl.model_precache[ ent.baseline.modelindex ];
	ent.frame = ent.baseline.frame;
	ent.colormap = null; // vid.colormap
	ent.skinnum = ent.baseline.skin;
	ent.effects = ent.baseline.effects;

	VectorCopy( ent.baseline.origin, ent.origin );
	VectorCopy( ent.baseline.angles, ent.angles );
	R_AddEfrags( ent );

}

/*
===================
CL_ParseStaticSound
===================
*/
export function CL_ParseStaticSound() {

	const org = _staticSoundOrg;
	for ( let i = 0; i < 3; i ++ )
		org[ i ] = MSG_ReadCoord();
	const sound_num = MSG_ReadByte();
	const vol = MSG_ReadByte();
	const atten = MSG_ReadByte();

	S_StaticSound( cl.sound_precache[ sound_num ], org, vol, atten );

}

/*
=====================
CL_ParseServerMessage
=====================
*/
export function CL_ParseServerMessage() {

	let cmd;
	let i;

	//
	// if recording demos, copy the message out
	//
	if ( cl_shownet.value === 1 )
		Con_Printf( '%i ', net_message.cursize );
	else if ( cl_shownet.value === 2 )
		Con_Printf( '------------------\n' );

	cl.onground = false; // unless the server says otherwise

	//
	// parse the message
	//
	MSG_BeginReading();

	while ( true ) {

		if ( msg_badread ) {

			Host_Error( 'CL_ParseServerMessage: Bad server message' );

		}

		cmd = MSG_ReadByte();

		if ( cmd === - 1 ) {

			if ( cl_shownet.value === 2 )
				Con_Printf( '%3i:%s\n', msg_readcount - 1, 'END OF MESSAGE' );
			return; // end of message

		}

		// if the high bit of the command byte is set, it is a fast update
		if ( cmd & 128 ) {

			if ( cl_shownet.value === 2 )
				Con_Printf( '%3i:%s\n', msg_readcount - 1, 'fast update' );
			CL_ParseUpdate( cmd & 127 );
			continue;

		}

		if ( cl_shownet.value === 2 )
			Con_Printf( '%3i:%s\n', msg_readcount - 1, svc_strings[ cmd ] || 'unknown' );

		// other commands
		switch ( cmd ) {

			default:
				Host_Error( 'CL_ParseServerMessage: Illegible server message\n' );
				break;

			case svc_nop:
				// Con_Printf( 'svc_nop\n' );
				break;

			case svc_time:
				cl.mtime[ 1 ] = cl.mtime[ 0 ];
				cl.mtime[ 0 ] = MSG_ReadFloat();
				break;

			case svc_clientdata:
				i = MSG_ReadShort();
				CL_ParseClientdata( i );
				break;

			case svc_version:
				i = MSG_ReadLong();
				if ( i !== PROTOCOL_VERSION )
					Host_Error( 'CL_ParseServerMessage: Server is protocol %i instead of %i\n', i, PROTOCOL_VERSION );
				break;

			case svc_disconnect:
				Host_EndGame( 'Server disconnected\n' );
				break;

			case svc_print:
				Con_Printf( '%s', MSG_ReadString() );
				break;

			case svc_centerprint:
				SCR_CenterPrint( MSG_ReadString() );
				break;

			case svc_stufftext:
				Cbuf_AddText( MSG_ReadString() );
				break;

			case svc_damage:
				V_ParseDamage();
				break;

			case svc_serverinfo:
				CL_ParseServerInfo();
				// vid.recalc_refdef = true; // leave intermission full screen
				break;

			case svc_setangle:
				for ( i = 0; i < 3; i ++ )
					cl.viewangles[ i ] = MSG_ReadAngle();
				break;

			case svc_setview:
				cl.viewentity = MSG_ReadShort();
				break;

			case svc_lightstyle:
				i = MSG_ReadByte();
				if ( i >= MAX_LIGHTSTYLES )
					Sys_Error( 'svc_lightstyle > MAX_LIGHTSTYLES' );
				cl_lightstyle[ i ].map = MSG_ReadString();
				cl_lightstyle[ i ].length = cl_lightstyle[ i ].map.length;
				break;

			case svc_sound:
				CL_ParseStartSoundPacket();
				break;

			case svc_stopsound:
				i = MSG_ReadShort();
				S_StopSound( i >> 3, i & 7 );
				break;

			case svc_updatename:
				// Sbar_Changed();
				i = MSG_ReadByte();
				if ( i >= cl.maxclients )
					Host_Error( 'CL_ParseServerMessage: svc_updatename > MAX_SCOREBOARD' );
				cl.scores[ i ].name = MSG_ReadString();
				break;

			case svc_updatefrags:
				// Sbar_Changed();
				i = MSG_ReadByte();
				if ( i >= cl.maxclients )
					Host_Error( 'CL_ParseServerMessage: svc_updatefrags > MAX_SCOREBOARD' );
				cl.scores[ i ].frags = MSG_ReadShort();
				break;

			case svc_updatecolors:
				// Sbar_Changed();
				i = MSG_ReadByte();
				if ( i >= cl.maxclients )
					Host_Error( 'CL_ParseServerMessage: svc_updatecolors > MAX_SCOREBOARD' );
				cl.scores[ i ].colors = MSG_ReadByte();
				CL_NewTranslation( i );
				break;

			case svc_particle:
				R_ParseParticleEffect();
				break;

			case svc_spawnbaseline:
				i = MSG_ReadShort();
				// must use CL_EntityNum() to force cl.num_entities up
				CL_ParseBaseline( CL_EntityNum( i ) );
				break;

			case svc_spawnstatic:
				CL_ParseStatic();
				break;

			case svc_temp_entity:
				CL_ParseTEnt();
				break;

			case svc_setpause:
				cl.paused = MSG_ReadByte();
				if ( cl.paused ) {
					CDAudio_Pause();
				} else {
					CDAudio_Resume();
				}
				break;

			case svc_signonnum:
				i = MSG_ReadByte();
				if ( i <= cls.signon )
					Host_Error( 'Received signon %i when at %i', i, cls.signon );
				cls.signon = i;
				CL_SignonReply();
				break;

			case svc_killedmonster:
				cl.stats[ STAT_MONSTERS ] ++;
				break;

			case svc_foundsecret:
				cl.stats[ STAT_SECRETS ] ++;
				break;

			case svc_updatestat:
				i = MSG_ReadByte();
				if ( i < 0 || i >= MAX_CL_STATS )
					Sys_Error( 'svc_updatestat: %i is invalid', i );
				cl.stats[ i ] = MSG_ReadLong();
				break;

			case svc_spawnstaticsound:
				CL_ParseStaticSound();
				break;

			case svc_cdtrack:
				cl.cdtrack = MSG_ReadByte();
				cl.looptrack = MSG_ReadByte();
				if ( ( cls.demoplayback || cls.demorecording ) && ( cls.forcetrack !== - 1 ) )
					CDAudio_Play( cls.forcetrack, true );
				else
					CDAudio_Play( cl.cdtrack, true );
				break;

			case svc_intermission:
				cl.intermission = 1;
				cl.completed_time = cl.time;
				// vid.recalc_refdef = true; // go to full screen
				break;

			case svc_finale:
				cl.intermission = 2;
				cl.completed_time = cl.time;
				// vid.recalc_refdef = true; // go to full screen
				SCR_CenterPrint( MSG_ReadString() );
				break;

			case svc_cutscene:
				cl.intermission = 3;
				cl.completed_time = cl.time;
				// vid.recalc_refdef = true; // go to full screen
				SCR_CenterPrint( MSG_ReadString() );
				break;

			case svc_sellscreen:
				Cmd_ExecuteString( 'help', src_command );
				break;

			case svc_playerinfo:
				CL_ParsePlayerInfo();
				break;

			case svc_serversequence:
				CL_SetServerSequence( MSG_ReadLong() );
				break;

			case svc_packetentities:
				CL_ParsePacketEntities( false );
				break;

			case svc_deltapacketentities:
				CL_ParsePacketEntities( true );
				break;

		}

	}

}
