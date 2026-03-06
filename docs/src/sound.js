// Ported from: WinQuake/sound.h -- client sound i/o definitions

import { MAX_QPATH } from './quakedef.js';

/*
==============================================================================

			SOUND CONSTANTS

==============================================================================
*/

export const DEFAULT_SOUND_PACKET_VOLUME = 255;
export const DEFAULT_SOUND_PACKET_ATTENUATION = 1.0;

export const MAX_CHANNELS = 128;
export const MAX_DYNAMIC_CHANNELS = 32;
export const NUM_AMBIENTS = 4;

// Ambient sound types (from bspfile.h)
export const AMBIENT_WATER = 0;
export const AMBIENT_SKY = 1;
export const AMBIENT_SLIME = 2;
export const AMBIENT_LAVA = 3;

/*
==============================================================================

			SOUND STRUCTURES

==============================================================================
*/

// portable_samplepair_t
export class portable_samplepair_t {

	constructor() {

		this.left = 0;
		this.right = 0;

	}

}

// sfx_t
export class sfx_t {

	constructor() {

		this.name = ''; // char name[MAX_QPATH]
		this.cache = null; // cache_user_t -- will hold sfxcache_t

	}

}

// sfxcache_t
export class sfxcache_t {

	constructor() {

		this.length = 0;
		this.loopstart = 0;
		this.speed = 0;
		this.width = 0;
		this.stereo = 0;
		this.data = null; // variable sized byte array

	}

}

// dma_t
export class dma_t {

	constructor() {

		this.gamealive = false;
		this.soundalive = false;
		this.splitbuffer = false;
		this.channels = 0;
		this.samples = 0; // mono samples in buffer
		this.submission_chunk = 0; // don't mix less than this #
		this.samplepos = 0; // in mono samples
		this.samplebits = 0;
		this.speed = 0;
		this.buffer = null; // unsigned char *

	}

}

// channel_t
export class channel_t {

	constructor() {

		this.sfx = null; // sfx_t *
		this.leftvol = 0; // 0-255 volume
		this.rightvol = 0; // 0-255 volume
		this.end = 0; // end time in global paintsamples
		this.pos = 0; // sample position in sfx
		this.looping = 0; // where to loop, -1 = no looping
		this.entnum = 0; // to allow overriding a specific sound
		this.entchannel = 0;
		this.origin = new Float32Array( 3 ); // origin of sound effect
		this.dist_mult = 0; // distance multiplier (attenuation/clipK)
		this.master_vol = 0; // 0-255 master volume

	}

}

// wavinfo_t
export class wavinfo_t {

	constructor() {

		this.rate = 0;
		this.width = 0;
		this.channels = 0;
		this.loopstart = 0;
		this.samples = 0;
		this.dataofs = 0; // chunk starts this many bytes from file start

	}

}

/*
==============================================================================

			SOUND GLOBALS

==============================================================================
*/

export const channels = [];
for ( let i = 0; i < MAX_CHANNELS; i ++ )
	channels[ i ] = new channel_t();

export let total_channels = 0;

export let fakedma = false;
export let fakedma_updates = 0;
export let paintedtime = 0;

export const listener_origin = new Float32Array( 3 );
export const listener_forward = new Float32Array( 3 );
export const listener_right = new Float32Array( 3 );
export const listener_up = new Float32Array( 3 );

export const sn = new dma_t();
export let shm = null; // volatile dma_t * -- points to sn when initialized

export const sound_nominal_clip_dist = 1000.0;

// cvars
export const loadas8bit = { name: 'loadas8bit', string: '0', value: 0 };
export const bgmvolume = { name: 'bgmvolume', string: '1', value: 1, archive: true };
export const volume = { name: 'volume', string: '0.4', value: 0.4, archive: true };

export let snd_initialized = false;
export let snd_blocked = 0;

// Setters for mutable globals
export function Sound_SetTotalChannels( val ) { total_channels = val; }
export function Sound_SetPaintedtime( val ) { paintedtime = val; }
export function Sound_SetShm( val ) { shm = val; }
export function Sound_SetInitialized( val ) { snd_initialized = val; }
export function Sound_SetBlocked( val ) { snd_blocked = val; }
