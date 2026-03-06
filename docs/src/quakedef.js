// Ported from: WinQuake/quakedef.h -- primary header for client

export const VERSION = 1.09;
export const GLQUAKE_VERSION = 1.00;

export const GAMENAME = 'id1'; // directory to look in by default

//
// angles
//
export const PITCH = 0; // up / down
export const YAW = 1; // left / right
export const ROLL = 2; // fall over

export const MAX_QPATH = 64; // max length of a quake game pathname
export const MAX_OSPATH = 128; // max length of a filesystem pathname

export const ON_EPSILON = 0.1; // point on plane side epsilon

export const MAX_MSGLEN = 8000; // max length of a reliable message
export const MAX_DATAGRAM = 1024; // max length of unreliable message

//
// per-level limits
//
export const MAX_EDICTS = 600; // FIXME: ouch! ouch! ouch!
export const MAX_LIGHTSTYLES = 64;
export const MAX_MODELS = 256; // these are sent over the net as bytes
export const MAX_SOUNDS = 256; // so they cannot be blindly increased

export const SAVEGAME_COMMENT_LENGTH = 39;

export const MAX_STYLESTRING = 64;

//
// stats are integers communicated to the client by the server
//
export const MAX_CL_STATS = 32;
export const STAT_HEALTH = 0;
export const STAT_FRAGS = 1;
export const STAT_WEAPON = 2;
export const STAT_AMMO = 3;
export const STAT_ARMOR = 4;
export const STAT_WEAPONFRAME = 5;
export const STAT_SHELLS = 6;
export const STAT_NAILS = 7;
export const STAT_ROCKETS = 8;
export const STAT_CELLS = 9;
export const STAT_ACTIVEWEAPON = 10;
export const STAT_TOTALSECRETS = 11;
export const STAT_TOTALMONSTERS = 12;
export const STAT_SECRETS = 13; // bumped on client side by svc_foundsecret
export const STAT_MONSTERS = 14; // bumped by svc_killedmonster
export const STAT_PING = 15; // client round-trip time in milliseconds

// stock defines

export const IT_SHOTGUN = 1;
export const IT_SUPER_SHOTGUN = 2;
export const IT_NAILGUN = 4;
export const IT_SUPER_NAILGUN = 8;
export const IT_GRENADE_LAUNCHER = 16;
export const IT_ROCKET_LAUNCHER = 32;
export const IT_LIGHTNING = 64;
export const IT_SUPER_LIGHTNING = 128;
export const IT_SHELLS = 256;
export const IT_NAILS = 512;
export const IT_ROCKETS = 1024;
export const IT_CELLS = 2048;
export const IT_AXE = 4096;
export const IT_ARMOR1 = 8192;
export const IT_ARMOR2 = 16384;
export const IT_ARMOR3 = 32768;
export const IT_SUPERHEALTH = 65536;
export const IT_KEY1 = 131072;
export const IT_KEY2 = 262144;
export const IT_INVISIBILITY = 524288;
export const IT_INVULNERABILITY = 1048576;
export const IT_SUIT = 2097152;
export const IT_QUAD = 4194304;
export const IT_SIGIL1 = ( 1 << 28 );
export const IT_SIGIL2 = ( 1 << 29 );
export const IT_SIGIL3 = ( 1 << 30 );
export const IT_SIGIL4 = ( 1 << 31 );

//===========================================
//rogue changed and added defines

export const RIT_SHELLS = 128;
export const RIT_NAILS = 256;
export const RIT_ROCKETS = 512;
export const RIT_CELLS = 1024;
export const RIT_AXE = 2048;
export const RIT_LAVA_NAILGUN = 4096;
export const RIT_LAVA_SUPER_NAILGUN = 8192;
export const RIT_MULTI_GRENADE = 16384;
export const RIT_MULTI_ROCKET = 32768;
export const RIT_PLASMA_GUN = 65536;
export const RIT_ARMOR1 = 8388608;
export const RIT_ARMOR2 = 16777216;
export const RIT_ARMOR3 = 33554432;
export const RIT_LAVA_NAILS = 67108864;
export const RIT_PLASMA_AMMO = 134217728;
export const RIT_MULTI_ROCKETS = 268435456;
export const RIT_SHIELD = 536870912;
export const RIT_ANTIGRAV = 1073741824;
export const RIT_SUPERHEALTH = 2147483648;

//MED 01/04/97 added hipnotic defines
//===========================================
//hipnotic added defines
export const HIT_PROXIMITY_GUN_BIT = 16;
export const HIT_MJOLNIR_BIT = 7;
export const HIT_LASER_CANNON_BIT = 23;
export const HIT_PROXIMITY_GUN = ( 1 << HIT_PROXIMITY_GUN_BIT );
export const HIT_MJOLNIR = ( 1 << HIT_MJOLNIR_BIT );
export const HIT_LASER_CANNON = ( 1 << HIT_LASER_CANNON_BIT );
export const HIT_WETSUIT = ( 1 << ( 23 + 2 ) );
export const HIT_EMPATHY_SHIELDS = ( 1 << ( 23 + 3 ) );

//===========================================

export const MAX_SCOREBOARD = 16;
export const MAX_SCOREBOARDNAME = 32;

export const SOUND_CHANNELS = 8;

// entity_state_t - baseline state for entity
export class entity_state_t {

	constructor() {

		this.number = 0; // entity number (QW delta compression)
		this.flags = 0; // PE_SOLID etc. (QW delta compression)
		this.origin = new Float32Array( 3 );
		this.angles = new Float32Array( 3 );
		this.modelindex = 0;
		this.frame = 0;
		this.colormap = 0;
		this.skin = 0;
		this.effects = 0;

	}

	copyFrom( other ) {

		this.number = other.number;
		this.flags = other.flags;
		this.origin[ 0 ] = other.origin[ 0 ];
		this.origin[ 1 ] = other.origin[ 1 ];
		this.origin[ 2 ] = other.origin[ 2 ];
		this.angles[ 0 ] = other.angles[ 0 ];
		this.angles[ 1 ] = other.angles[ 1 ];
		this.angles[ 2 ] = other.angles[ 2 ];
		this.modelindex = other.modelindex;
		this.frame = other.frame;
		this.colormap = other.colormap;
		this.skin = other.skin;
		this.effects = other.effects;

	}

}

//=============================================================================

// the host system specifies the base of the directory tree, the
// command line parms passed to the program, and the amount of memory
// available for the program to use

export class quakeparms_t {

	constructor() {

		this.basedir = '';
		this.cachedir = '';
		this.argc = 0;
		this.argv = [];

	}

}
