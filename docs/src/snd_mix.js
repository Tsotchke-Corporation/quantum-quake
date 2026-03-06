// Ported from: WinQuake/snd_mix.c -- portable code to mix sounds for snd_dma.c

import {
	portable_samplepair_t,
	channels, total_channels,
	paintedtime, shm,
	volume,
	Sound_SetPaintedtime
} from './sound.js';
import { S_LoadSound } from './snd_mem.js';

/*
==============================================================================

			PAINT BUFFER

==============================================================================
*/

const PAINTBUFFER_SIZE = 512;
const paintbuffer = [];
for ( let i = 0; i < PAINTBUFFER_SIZE; i ++ )
	paintbuffer[ i ] = new portable_samplepair_t();

/*
==============================================================================

			SCALE TABLE

==============================================================================
*/

const snd_scaletable = [];
for ( let i = 0; i < 32; i ++ ) {

	snd_scaletable[ i ] = new Int32Array( 256 );

}

/*
================
SND_InitScaletable
================
*/
export function SND_InitScaletable() {

	for ( let i = 0; i < 32; i ++ ) {

		for ( let j = 0; j < 256; j ++ ) {

			// (signed char)j * i * 8
			let sj = j;
			if ( sj >= 128 ) sj -= 256; // sign extend to signed char
			snd_scaletable[ i ][ j ] = sj * i * 8;

		}

	}

}

/*
===============================================================================

CHANNEL MIXING

===============================================================================
*/

/*
================
SND_PaintChannelFrom8
================
*/
function SND_PaintChannelFrom8( ch, sc, count ) {

	let leftvol = ch.leftvol;
	let rightvol = ch.rightvol;

	if ( leftvol > 255 ) leftvol = 255;
	if ( rightvol > 255 ) rightvol = 255;

	const lscale = snd_scaletable[ leftvol >> 3 ];
	const rscale = snd_scaletable[ rightvol >> 3 ];
	const sfx = sc.data;
	const pos = ch.pos;

	for ( let i = 0; i < count; i ++ ) {

		// data is signed 8-bit stored as unsigned byte
		let data = sfx[ pos + i ];
		if ( data === undefined ) data = 0;
		// Convert to unsigned for table lookup (the table handles sign internally)
		const idx = data & 0xff;
		paintbuffer[ i ].left += lscale[ idx ];
		paintbuffer[ i ].right += rscale[ idx ];

	}

	ch.pos += count;

}

/*
================
SND_PaintChannelFrom16
================
*/
function SND_PaintChannelFrom16( ch, sc, count ) {

	const leftvol = ch.leftvol;
	const rightvol = ch.rightvol;
	const sfx = sc.data;
	const pos = ch.pos;

	for ( let i = 0; i < count; i ++ ) {

		// 16-bit signed little-endian
		const byteOfs = ( pos + i ) * 2;
		let data = sfx[ byteOfs ] | ( sfx[ byteOfs + 1 ] << 8 );
		if ( data >= 0x8000 ) data -= 0x10000; // sign extend

		const left = ( data * leftvol ) >> 8;
		const right = ( data * rightvol ) >> 8;
		paintbuffer[ i ].left += left;
		paintbuffer[ i ].right += right;

	}

	ch.pos += count;

}

/*
================
S_PaintChannels
================
*/
export function S_PaintChannels( endtime ) {

	let pt = paintedtime;

	while ( pt < endtime ) {

		// if paintbuffer is smaller than DMA buffer
		let end = endtime;
		if ( endtime - pt > PAINTBUFFER_SIZE )
			end = pt + PAINTBUFFER_SIZE;

		// clear the paint buffer
		const clearCount = end - pt;
		for ( let i = 0; i < clearCount; i ++ ) {

			paintbuffer[ i ].left = 0;
			paintbuffer[ i ].right = 0;

		}

		// paint in the channels
		for ( let i = 0; i < total_channels; i ++ ) {

			const ch = channels[ i ];

			if ( ch.sfx == null )
				continue;
			if ( ch.leftvol === 0 && ch.rightvol === 0 )
				continue;

			const sc = S_LoadSound( ch.sfx );
			if ( sc == null )
				continue;

			let ltime = pt;

			while ( ltime < end ) {

				// paint up to end
				let count;
				if ( ch.end < end )
					count = ch.end - ltime;
				else
					count = end - ltime;

				if ( count > 0 ) {

					if ( sc.width === 1 )
						SND_PaintChannelFrom8( ch, sc, count );
					else
						SND_PaintChannelFrom16( ch, sc, count );

					ltime += count;

				}

				// if at end of loop, restart
				if ( ltime >= ch.end ) {

					if ( sc.loopstart >= 0 ) {

						ch.pos = sc.loopstart;
						ch.end = ltime + sc.length - ch.pos;

					} else {

						// channel just stopped
						ch.sfx = null;
						break;

					}

				}

			}

		}

		// transfer out according to DMA format
		S_TransferPaintBuffer( end );
		pt = end;
		Sound_SetPaintedtime( pt );

	}

}

/*
================
Snd_WriteLinearBlastStereo16
================
*/
function Snd_WriteLinearBlastStereo16( snd_out, snd_out_idx, snd_p, snd_p_idx, snd_linear_count, snd_vol ) {

	for ( let i = 0; i < snd_linear_count; i += 2 ) {

		let val = ( snd_p[ snd_p_idx + i ] * snd_vol ) >> 8;
		if ( val > 0x7fff )
			snd_out[ snd_out_idx + i ] = 0x7fff;
		else if ( val < - 32768 )
			snd_out[ snd_out_idx + i ] = - 32768;
		else
			snd_out[ snd_out_idx + i ] = val;

		val = ( snd_p[ snd_p_idx + i + 1 ] * snd_vol ) >> 8;
		if ( val > 0x7fff )
			snd_out[ snd_out_idx + i + 1 ] = 0x7fff;
		else if ( val < - 32768 )
			snd_out[ snd_out_idx + i + 1 ] = - 32768;
		else
			snd_out[ snd_out_idx + i + 1 ] = val;

	}

}

/*
================
S_TransferStereo16
================
*/
function S_TransferStereo16( endtime ) {

	const snd_vol = Math.floor( volume.value * 256 );

	// Flatten paintbuffer to interleaved array
	const snd_p = [];
	const count = endtime - paintedtime;
	for ( let i = 0; i < count; i ++ ) {

		snd_p[ i * 2 ] = paintbuffer[ i ].left;
		snd_p[ i * 2 + 1 ] = paintbuffer[ i ].right;

	}

	let lpaintedtime = paintedtime;
	let snd_p_idx = 0;

	const pbuf = new Int16Array( shm.buffer.buffer );

	while ( lpaintedtime < endtime ) {

		// handle recirculating buffer issues
		const lpos = lpaintedtime & ( ( shm.samples >> 1 ) - 1 );
		const snd_out_idx = lpos << 1;

		let snd_linear_count = ( shm.samples >> 1 ) - lpos;
		if ( lpaintedtime + snd_linear_count > endtime )
			snd_linear_count = endtime - lpaintedtime;

		snd_linear_count <<= 1;

		// write a linear blast of samples
		Snd_WriteLinearBlastStereo16( pbuf, snd_out_idx, snd_p, snd_p_idx, snd_linear_count, snd_vol );

		snd_p_idx += snd_linear_count;
		lpaintedtime += ( snd_linear_count >> 1 );

	}

}

/*
================
S_TransferPaintBuffer
================
*/
function S_TransferPaintBuffer( endtime ) {

	if ( ! shm )
		return;

	if ( shm.samplebits === 16 && shm.channels === 2 ) {

		S_TransferStereo16( endtime );
		return;

	}

	const count = ( endtime - paintedtime ) * shm.channels;
	const out_mask = shm.samples - 1;
	let out_idx = paintedtime * shm.channels & out_mask;
	const step = 3 - shm.channels;
	const snd_vol = Math.floor( volume.value * 256 );

	let p_idx = 0;

	if ( shm.samplebits === 16 ) {

		const out = new Int16Array( shm.buffer.buffer );
		let remaining = count;
		while ( remaining -- ) {

			// Access paintbuffer as interleaved left/right
			const pb_idx = Math.floor( p_idx / 2 );
			const is_right = p_idx % 2;
			const sample = is_right ? paintbuffer[ pb_idx ].right : paintbuffer[ pb_idx ].left;

			let val = ( sample * snd_vol ) >> 8;
			p_idx += step;

			if ( val > 0x7fff )
				val = 0x7fff;
			else if ( val < - 32768 )
				val = - 32768;

			out[ out_idx ] = val;
			out_idx = ( out_idx + 1 ) & out_mask;

		}

	} else if ( shm.samplebits === 8 ) {

		const out = shm.buffer;
		let remaining = count;
		while ( remaining -- ) {

			const pb_idx = Math.floor( p_idx / 2 );
			const is_right = p_idx % 2;
			const sample = is_right ? paintbuffer[ pb_idx ].right : paintbuffer[ pb_idx ].left;

			let val = ( sample * snd_vol ) >> 8;
			p_idx += step;

			if ( val > 0x7fff )
				val = 0x7fff;
			else if ( val < - 32768 )
				val = - 32768;

			out[ out_idx ] = ( val >> 8 ) + 128;
			out_idx = ( out_idx + 1 ) & out_mask;

		}

	}

}
