// Ported from: WinQuake/protocol.h -- communications protocols

export const PROTOCOL_VERSION = 15;

// if the high bit of the servercmd is set, the low bits are fast update flags:
export const U_MOREBITS = ( 1 << 0 );
export const U_ORIGIN1 = ( 1 << 1 );
export const U_ORIGIN2 = ( 1 << 2 );
export const U_ORIGIN3 = ( 1 << 3 );
export const U_ANGLE2 = ( 1 << 4 );
export const U_NOLERP = ( 1 << 5 ); // don't interpolate movement
export const U_FRAME = ( 1 << 6 );
export const U_SIGNAL = ( 1 << 7 ); // just differentiates from other updates

// svc_update can pass all of the fast update bits, plus more
export const U_ANGLE1 = ( 1 << 8 );
export const U_ANGLE3 = ( 1 << 9 );
export const U_MODEL = ( 1 << 10 );
export const U_COLORMAP = ( 1 << 11 );
export const U_SKIN = ( 1 << 12 );
export const U_EFFECTS = ( 1 << 13 );
export const U_LONGENTITY = ( 1 << 14 );

export const SU_VIEWHEIGHT = ( 1 << 0 );
export const SU_IDEALPITCH = ( 1 << 1 );
export const SU_PUNCH1 = ( 1 << 2 );
export const SU_PUNCH2 = ( 1 << 3 );
export const SU_PUNCH3 = ( 1 << 4 );
export const SU_VELOCITY1 = ( 1 << 5 );
export const SU_VELOCITY2 = ( 1 << 6 );
export const SU_VELOCITY3 = ( 1 << 7 );
// SU_AIMENT (1<<8) AVAILABLE BIT
export const SU_ITEMS = ( 1 << 9 );
export const SU_ONGROUND = ( 1 << 10 ); // no data follows, the bit is it
export const SU_INWATER = ( 1 << 11 ); // no data follows, the bit is it
export const SU_WEAPONFRAME = ( 1 << 12 );
export const SU_ARMOR = ( 1 << 13 );
export const SU_WEAPON = ( 1 << 14 );

// a sound with no channel is a local only sound
export const SND_VOLUME = ( 1 << 0 ); // a byte
export const SND_ATTENUATION = ( 1 << 1 ); // a byte
export const SND_LOOPING = ( 1 << 2 ); // a long

// defaults for clientinfo messages
export const DEFAULT_VIEWHEIGHT = 22;

export const DEFAULT_SOUND_PACKET_VOLUME = 255;
export const DEFAULT_SOUND_PACKET_ATTENUATION = 1.0;

// game types sent by serverinfo
// these determine which intermission screen plays
export const GAME_COOP = 0;
export const GAME_DEATHMATCH = 1;

//==================
// note that there are some defs.qc that mirror to these numbers
// also related to svc_strings[] in cl_parse
//==================

//
// server to client
//
export const svc_bad = 0;
export const svc_nop = 1;
export const svc_disconnect = 2;
export const svc_updatestat = 3; // [byte] [long]
export const svc_version = 4; // [long] server version
export const svc_setview = 5; // [short] entity number
export const svc_sound = 6; // <see code>
export const svc_time = 7; // [float] server time
export const svc_print = 8; // [string] null terminated string
export const svc_stufftext = 9; // [string] stuffed into client's console buffer
export const svc_setangle = 10; // [angle3] set the view angle to this absolute value
export const svc_serverinfo = 11; // [long] version ... [string]..[0]model cache [string]...[0]sounds cache
export const svc_lightstyle = 12; // [byte] [string]
export const svc_updatename = 13; // [byte] [string]
export const svc_updatefrags = 14; // [byte] [short]
export const svc_clientdata = 15; // <shortbits + data>
export const svc_stopsound = 16; // <see code>
export const svc_updatecolors = 17; // [byte] [byte]
export const svc_particle = 18; // [vec3] <variable>
export const svc_damage = 19;
export const svc_spawnstatic = 20;
// svc_spawnbinary = 21
export const svc_spawnbaseline = 22;
export const svc_temp_entity = 23;
export const svc_setpause = 24; // [byte] on / off
export const svc_signonnum = 25; // [byte] used for the signon sequence
export const svc_centerprint = 26; // [string] to put in center of the screen
export const svc_killedmonster = 27;
export const svc_foundsecret = 28;
export const svc_spawnstaticsound = 29; // [coord3] [byte] samp [byte] vol [byte] aten
export const svc_intermission = 30; // [string] music
export const svc_finale = 31; // [string] music [string] text
export const svc_cdtrack = 32; // [byte] track [byte] looptrack
export const svc_sellscreen = 33;
export const svc_cutscene = 34;

//
// client to server
//
export const clc_bad = 0;
export const clc_nop = 1;
export const clc_disconnect = 2;
export const clc_move = 3; // [usercmd_t]
export const clc_stringcmd = 4; // [string] message

//
// temp entity events
//
export const TE_SPIKE = 0;
export const TE_SUPERSPIKE = 1;
export const TE_GUNSHOT = 2;
export const TE_EXPLOSION = 3;
export const TE_TAREXPLOSION = 4;
export const TE_LIGHTNING1 = 5;
export const TE_LIGHTNING2 = 6;
export const TE_WIZSPIKE = 7;
export const TE_KNIGHTSPIKE = 8;
export const TE_LIGHTNING3 = 9;
export const TE_LAVASPLASH = 10;
export const TE_TELEPORT = 11;
export const TE_EXPLOSION2 = 12;
export const TE_BEAM = 13;

//
// QuakeWorld-style player info (svc_playerinfo)
// Used for client-side prediction of other players
//
export const svc_playerinfo = 42;

// playerinfo flags from server
// playerinfo always sends: playernum, flags, origin[] and frame
export const PF_MSEC = ( 1 << 0 );
export const PF_COMMAND = ( 1 << 1 );
export const PF_VELOCITY1 = ( 1 << 2 );
export const PF_VELOCITY2 = ( 1 << 3 );
export const PF_VELOCITY3 = ( 1 << 4 );
export const PF_MODEL = ( 1 << 5 );
export const PF_SKINNUM = ( 1 << 6 );
export const PF_EFFECTS = ( 1 << 7 );
export const PF_WEAPONFRAME = ( 1 << 8 ); // only sent for view player
export const PF_DEAD = ( 1 << 9 ); // don't block movement any more
export const PF_GIB = ( 1 << 10 ); // offset the view height differently

// command move bits (for delta compression of usercmd_t)
export const CM_ANGLE1 = ( 1 << 0 );
export const CM_ANGLE3 = ( 1 << 1 );
export const CM_FORWARD = ( 1 << 2 );
export const CM_SIDE = ( 1 << 3 );
export const CM_UP = ( 1 << 4 );
export const CM_BUTTONS = ( 1 << 5 );
export const CM_IMPULSE = ( 1 << 6 );
export const CM_ANGLE2 = ( 1 << 7 );

//==============================================
// QW-style delta compression for packet entities
// Ported from: QW/client/protocol.h
//
// The first 16 bits of a packetentities update holds 10 bits
// of entity number (max 1024, to support MAX_EDICTS=600) and
// 6 bits of flags.
//==============================================

export const svc_packetentities = 47; // [...]
export const svc_deltapacketentities = 48; // [...]
export const svc_serversequence = 49; // [long] server frame sequence number

export const clc_delta = 5; // [byte] sequence number, requests delta compression

// Entity number mask: 10 bits for entity number (0-1023)
export const PE_ENT_BITS = 10;
export const PE_ENT_MASK = ( 1 << PE_ENT_BITS ) - 1; // 0x3FF

// Packet entity U_* flags (upper 6 bits of the short, plus morebits byte)
// Bits 10-15 of the first short:
export const PE_ORIGIN1 = ( 1 << 10 );
export const PE_ORIGIN2 = ( 1 << 11 );
export const PE_ORIGIN3 = ( 1 << 12 );
export const PE_ANGLE2 = ( 1 << 13 );
export const PE_REMOVE = ( 1 << 14 ); // REMOVE this entity, don't add it
export const PE_MOREBITS = ( 1 << 15 );

// If PE_MOREBITS is set, these additional flags are read in the next byte:
export const PE_FRAME = ( 1 << 0 );
export const PE_ANGLE1 = ( 1 << 1 );
export const PE_ANGLE3 = ( 1 << 2 );
export const PE_MODEL = ( 1 << 3 );
export const PE_COLORMAP = ( 1 << 4 );
export const PE_SKIN = ( 1 << 5 );
export const PE_EFFECTS = ( 1 << 6 );
export const PE_SOLID = ( 1 << 7 ); // entity should be solid for prediction

// Packet entities constants
export const MAX_PACKET_ENTITIES = 64; // max entities in a single packet
export const PE_UPDATE_BACKUP = 64; // must be power of 2
export const PE_UPDATE_MASK = PE_UPDATE_BACKUP - 1;
