// Ported from: WinQuake/server.h -- server structures and constants

import { MAX_MODELS, MAX_SOUNDS, MAX_LIGHTSTYLES, MAX_DATAGRAM, MAX_MSGLEN, entity_state_t } from './quakedef.js';
import { sizebuf_t } from './common.js';
import { MAX_PACKET_ENTITIES, PE_UPDATE_BACKUP } from './protocol.js';

//============================================================================
// Server state enum
//============================================================================

export const ss_loading = 0;
export const ss_active = 1;

//============================================================================
// server_static_t -- persistant server info
//============================================================================

export class server_static_t {

	constructor() {

		this.maxclients = 0;
		this.maxclientslimit = 0;
		this.clients = null; // Array of client_t [maxclients]
		this.serverflags = 0; // episode completion information
		this.changelevel_issued = false; // cleared when at SV_SpawnServer

	}

}

//============================================================================
// server_t -- local server state
//============================================================================

export class server_t {

	constructor() {

		this.active = false; // false if only a net client

		this.paused = false;
		this.loadgame = false; // handle connections specially

		this.time = 0;

		this.lastcheck = 0; // used by PF_checkclient
		this.lastchecktime = 0;

		this.name = ''; // map name (max 64)
		this.modelname = ''; // maps/<name>.bsp, for model_precache[0]
		this.worldmodel = null; // struct model_s *
		this.model_precache = new Array( MAX_MODELS ).fill( null ); // NULL terminated
		this.models = new Array( MAX_MODELS ).fill( null );
		this.sound_precache = new Array( MAX_SOUNDS ).fill( null ); // NULL terminated
		this.lightstyles = new Array( MAX_LIGHTSTYLES ).fill( null );
		this.num_edicts = 0;
		this.max_edicts = 0;
		this.edicts = null; // edict_t * -- can NOT be array indexed (variable sized)
		this.state = ss_loading; // some actions are only valid during load

		this.datagram = new sizebuf_t();
		this.datagram_buf = new Uint8Array( MAX_DATAGRAM );

		this.reliable_datagram = new sizebuf_t(); // copied to all clients at end of frame
		this.reliable_datagram_buf = new Uint8Array( MAX_DATAGRAM );

		this.signon = new sizebuf_t();
		this.signon_buf = new Uint8Array( 8192 );

	}

}

//============================================================================
// client_frame_t -- per-frame entity snapshot for delta compression
// Ported from: QW/server/server.h
//============================================================================

export class client_frame_t {

	constructor() {

		this.senttime = 0;
		this.entities = { num_entities: 0, entities: [] };
		for ( let i = 0; i < MAX_PACKET_ENTITIES; i ++ ) {

			this.entities.entities.push( new entity_state_t() );

		}

	}

}

//============================================================================
// client_t -- per-client state on the server
//============================================================================

export const NUM_PING_TIMES = 16;
export const NUM_SPAWN_PARMS = 16;

export class client_t {

	constructor() {

		this.active = false; // false = client is free
		this.spawned = false; // false = don't send datagrams
		this.dropasap = false; // has been told to go to another level
		this.privileged = false; // can execute any host command
		this.sendsignon = false; // only valid before spawned

		this.last_message = 0; // reliable messages must be sent periodically

		this.netconnection = null; // struct qsocket_s * -- communications handle

		this.cmd = null; // usercmd_t -- movement
		this.wishdir = new Float32Array( 3 ); // intended motion calced from cmd

		this.message = new sizebuf_t(); // can be added to at any time, copied and clear once per frame
		this.msgbuf = new Uint8Array( MAX_MSGLEN );
		this.edict = null; // edict_t * -- EDICT_NUM(clientnum+1)
		this.name = ''; // for printing to other people (max 32)
		this.colors = 0;

		this.ping_times = new Float32Array( NUM_PING_TIMES );
		this.num_pings = 0; // ping_times[num_pings%NUM_PING_TIMES]
		this.localtime = 0; // server time of last message (for PF_MSEC)

		// spawn parms are carried from level to level
		this.spawn_parms = new Float32Array( NUM_SPAWN_PARMS );

		// client known data for deltas
		this.old_frags = 0;
		this.old_ping = 0;

		// QW-style delta compression
		this.delta_sequence = - 1; // -1 = no compression
		this.outgoing_sequence = 0; // incremented each frame we send to this client
		this.frames = [];
		for ( let i = 0; i < PE_UPDATE_BACKUP; i ++ ) {

			this.frames.push( new client_frame_t() );

		}

	}

}

//============================================================================
// edict->movetype values
//============================================================================

export const MOVETYPE_NONE = 0; // never moves
export const MOVETYPE_ANGLENOCLIP = 1;
export const MOVETYPE_ANGLECLIP = 2;
export const MOVETYPE_WALK = 3; // gravity
export const MOVETYPE_STEP = 4; // gravity, special edge handling
export const MOVETYPE_FLY = 5;
export const MOVETYPE_TOSS = 6; // gravity
export const MOVETYPE_PUSH = 7; // no clip to world, push and crush
export const MOVETYPE_NOCLIP = 8;
export const MOVETYPE_FLYMISSILE = 9; // extra size to monsters
export const MOVETYPE_BOUNCE = 10;

//============================================================================
// edict->solid values
//============================================================================

export const SOLID_NOT = 0; // no interaction with other objects
export const SOLID_TRIGGER = 1; // touch on edge, but not blocking
export const SOLID_BBOX = 2; // touch on edge, block
export const SOLID_SLIDEBOX = 3; // touch on edge, but not an onground
export const SOLID_BSP = 4; // bsp clip, touch on edge, block

//============================================================================
// edict->deadflag values
//============================================================================

export const DEAD_NO = 0;
export const DEAD_DYING = 1;
export const DEAD_DEAD = 2;

export const DAMAGE_NO = 0;
export const DAMAGE_YES = 1;
export const DAMAGE_AIM = 2;

//============================================================================
// edict->flags
//============================================================================

export const FL_FLY = 1;
export const FL_SWIM = 2;
export const FL_CONVEYOR = 4;
export const FL_CLIENT = 8;
export const FL_INWATER = 16;
export const FL_MONSTER = 32;
export const FL_GODMODE = 64;
export const FL_NOTARGET = 128;
export const FL_ITEM = 256;
export const FL_ONGROUND = 512;
export const FL_PARTIALGROUND = 1024; // not all corners are valid
export const FL_WATERJUMP = 2048; // player jumping out of water
export const FL_JUMPRELEASED = 4096; // for jump debouncing

//============================================================================
// entity effects
//============================================================================

export const EF_BRIGHTFIELD = 1;
export const EF_MUZZLEFLASH = 2;
export const EF_BRIGHTLIGHT = 4;
export const EF_DIMLIGHT = 8;

//============================================================================
// spawn flags
//============================================================================

export const SPAWNFLAG_NOT_EASY = 256;
export const SPAWNFLAG_NOT_MEDIUM = 512;
export const SPAWNFLAG_NOT_HARD = 1024;
export const SPAWNFLAG_NOT_DEATHMATCH = 2048;

//============================================================================
// Extern cvars - defined in host.js, re-exported here for compatibility
//============================================================================

// Note: These are re-exported from host.js where they are defined and registered.
// This matches original Quake where cvars were defined in host.c and extern'd in server.h.
export { skill, deathmatch, coop, teamplay, fraglimit, timelimit } from './host.js';

//============================================================================
// Global server state
//============================================================================

export const svs = new server_static_t(); // persistant server info
export const sv = new server_t(); // local server

export let host_client = null; // current client being processed
export function set_host_client( v ) { host_client = v; }

export let host_time = 0;
export function set_host_time( v ) { host_time = v; }

export let sv_player = null;
export function set_sv_player( v ) { sv_player = v; }
