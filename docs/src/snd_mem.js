// Ported from: WinQuake/snd_mem.c -- sound caching and WAV loading

import { Con_Printf } from './console.js';
import { COM_LoadFile } from './pak.js';
import { Sys_Error } from './sys.js';
import {
	sfxcache_t, wavinfo_t,
	shm, loadas8bit
} from './sound.js';

/*
==============================================================================

			WAV LOADING

==============================================================================
*/

// IFF parser state (module-level, mirrors C globals)
let data_p = 0; // offset into wav data
let iff_end = 0;
let last_chunk = 0;
let iff_data = 0;
let iff_chunk_len = 0;
let _wav = null; // Uint8Array reference for current parse

/*
================
GetLittleShort
================
*/
function GetLittleShort() {

	let val = _wav[ data_p ];
	val = val + ( _wav[ data_p + 1 ] << 8 );
	data_p += 2;

	// sign extend
	if ( val >= 0x8000 ) val -= 0x10000;
	return val;

}

/*
================
GetLittleLong
================
*/
function GetLittleLong() {

	let val = _wav[ data_p ];
	val = val + ( _wav[ data_p + 1 ] << 8 );
	val = val + ( _wav[ data_p + 2 ] << 16 );
	val = val + ( _wav[ data_p + 3 ] << 24 );
	data_p += 4;
	return val;

}

/*
================
FindNextChunk
================
*/
function FindNextChunk( name ) {

	while ( true ) {

		data_p = last_chunk;

		if ( data_p >= iff_end ) {

			// didn't find the chunk
			data_p = - 1;
			return;

		}

		data_p += 4;
		iff_chunk_len = GetLittleLong();
		if ( iff_chunk_len < 0 ) {

			data_p = - 1;
			return;

		}

		data_p -= 8;
		last_chunk = data_p + 8 + ( ( iff_chunk_len + 1 ) & ~1 );

		// Compare 4-byte chunk name
		const n0 = name.charCodeAt( 0 );
		const n1 = name.charCodeAt( 1 );
		const n2 = name.charCodeAt( 2 );
		const n3 = name.charCodeAt( 3 );

		if ( _wav[ data_p ] === n0 &&
			_wav[ data_p + 1 ] === n1 &&
			_wav[ data_p + 2 ] === n2 &&
			_wav[ data_p + 3 ] === n3 ) {

			return;

		}

	}

}

/*
================
FindChunk
================
*/
function FindChunk( name ) {

	last_chunk = iff_data;
	FindNextChunk( name );

}

/*
============
GetWavinfo
============
*/
export function GetWavinfo( name, wav, wavlength ) {

	const info = new wavinfo_t();

	if ( ! wav )
		return info;

	_wav = wav;
	iff_data = 0;
	iff_end = wavlength;

	// find "RIFF" chunk
	FindChunk( 'RIFF' );
	if ( data_p < 0 || data_p + 12 > iff_end ) {

		Con_Printf( 'Missing RIFF/WAVE chunks\n' );
		return info;

	}

	// Check for "WAVE" at data_p + 8
	if ( _wav[ data_p + 8 ] !== 0x57 || // 'W'
		_wav[ data_p + 9 ] !== 0x41 || // 'A'
		_wav[ data_p + 10 ] !== 0x56 || // 'V'
		_wav[ data_p + 11 ] !== 0x45 ) { // 'E'

		Con_Printf( 'Missing RIFF/WAVE chunks\n' );
		return info;

	}

	// get "fmt " chunk
	iff_data = data_p + 12;

	FindChunk( 'fmt ' );
	if ( data_p < 0 ) {

		Con_Printf( 'Missing fmt chunk\n' );
		return info;

	}

	data_p += 8;
	const format = GetLittleShort();
	if ( format !== 1 ) {

		Con_Printf( 'Microsoft PCM format only\n' );
		return info;

	}

	info.channels = GetLittleShort();
	info.rate = GetLittleLong();
	data_p += 4 + 2; // skip avgBytesPerSec and blockAlign
	info.width = GetLittleShort() / 8;

	// get cue chunk
	FindChunk( 'cue ' );
	if ( data_p >= 0 ) {

		data_p += 32;
		info.loopstart = GetLittleLong();

		// if the next chunk is a LIST chunk, look for a cue length marker
		FindNextChunk( 'LIST' );
		if ( data_p >= 0 ) {

			if ( data_p + 32 <= iff_end &&
				_wav[ data_p + 28 ] === 0x6D && // 'm'
				_wav[ data_p + 29 ] === 0x61 && // 'a'
				_wav[ data_p + 30 ] === 0x72 && // 'r'
				_wav[ data_p + 31 ] === 0x6B ) { // 'k'

				// this is not a proper parse, but it works with cooledit...
				data_p += 24;
				const i = GetLittleLong(); // samples in loop
				info.samples = info.loopstart + i;

			}

		}

	} else {

		info.loopstart = - 1;

	}

	// find data chunk
	FindChunk( 'data' );
	if ( data_p < 0 ) {

		Con_Printf( 'Missing data chunk\n' );
		return info;

	}

	data_p += 4;
	const samples = GetLittleLong() / info.width;

	if ( info.samples ) {

		if ( samples < info.samples )
			Sys_Error( 'Sound ' + name + ' has a bad loop length' );

	} else {

		info.samples = samples;

	}

	info.dataofs = data_p;

	return info;

}

/*
================
ResampleSfx
================
*/
function ResampleSfx( sfx, inrate, inwidth, data ) {

	const sc = sfx.cache;
	if ( ! sc )
		return;

	const stepscale = inrate / shm.speed; // this is usually 0.5, 1, or 2

	let outcount = Math.floor( sc.length / stepscale );
	sc.length = outcount;
	if ( sc.loopstart !== - 1 )
		sc.loopstart = Math.floor( sc.loopstart / stepscale );

	sc.speed = shm.speed;
	if ( loadas8bit.value )
		sc.width = 1;
	else
		sc.width = inwidth;
	sc.stereo = 0;

	// resample / decimate to the current source rate

	if ( stepscale === 1 && inwidth === 1 && sc.width === 1 ) {

		// fast special case - keep as unsigned 8-bit
		for ( let i = 0; i < outcount; i ++ )
			sc.data[ i ] = data[ i ];

	} else {

		// general case
		let samplefrac = 0;
		const fracstep = Math.floor( stepscale * 256 );

		for ( let i = 0; i < outcount; i ++ ) {

			const srcsample = samplefrac >> 8;
			samplefrac += fracstep;

			let sample;
			if ( inwidth === 2 ) {

				// 16-bit little-endian signed
				sample = data[ srcsample * 2 ] | ( data[ srcsample * 2 + 1 ] << 8 );
				if ( sample >= 0x8000 ) sample -= 0x10000; // sign extend

			} else {

				// 8-bit unsigned to 16-bit signed
				sample = ( data[ srcsample ] - 128 ) << 8;

			}

			if ( sc.width === 2 ) {

				// store as 16-bit signed
				sc.data[ i * 2 ] = sample & 0xff;
				sc.data[ i * 2 + 1 ] = ( sample >> 8 ) & 0xff;

			} else {

				// store as 8-bit unsigned (convert from signed)
				sc.data[ i ] = ( sample >> 8 ) + 128;

			}

		}

	}

}

/*
==============
S_LoadSound
==============
*/
export function S_LoadSound( s ) {

	if ( ! s )
		return null;

	// see if still in memory
	if ( s.cache )
		return s.cache;

	// load it in
	const namebuffer = 'sound/' + s.name;

	const data = COM_LoadFile( namebuffer );

	if ( ! data ) {

		Con_Printf( 'Couldn\'t load %s\n', namebuffer );
		return null;

	}

	const wav = new Uint8Array( data );
	const info = GetWavinfo( s.name, wav, wav.length );

	if ( info.channels !== 1 ) {

		Con_Printf( '%s is a stereo sample\n', s.name );
		return null;

	}

	if ( ! shm ) {

		Con_Printf( 'S_LoadSound: sound system not initialized\n' );
		return null;

	}

	const stepscale = info.rate / shm.speed;
	let len = Math.floor( info.samples / stepscale );
	len = len * info.width * info.channels;

	const sc = new sfxcache_t();
	sc.length = info.samples;
	sc.loopstart = info.loopstart;
	sc.speed = info.rate;
	sc.width = info.width;
	sc.stereo = info.channels;
	sc.data = new Uint8Array( len );

	s.cache = sc;

	ResampleSfx( s, sc.speed, sc.width, wav.subarray( info.dataofs ) );

	return sc;

}
