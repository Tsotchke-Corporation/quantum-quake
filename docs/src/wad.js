// Ported from: WinQuake/wad.c + wad.h -- WAD file loading

import { Sys_Error } from './sys.js';

//===============
//   TYPES
//===============

export const CMP_NONE = 0;
export const CMP_LZSS = 1;

export const TYP_NONE = 0;
export const TYP_LABEL = 1;

export const TYP_LUMPY = 64; // 64 + grab command number
export const TYP_PALETTE = 64;
export const TYP_QTEX = 65;
export const TYP_QPIC = 66;
export const TYP_SOUND = 67;
export const TYP_MIPTEX = 68;

export let wad_numlumps = 0;
export let wad_lumps = null;
export let wad_base = null;

/*
==================
W_CleanupName

Lowercases name and pads with spaces and a terminating 0 to the length of
lumpinfo_t->name.
Used so lumpname lookups can proceed rapidly by comparing 4 chars at a time
Space padding is so names can be printed nicely in tables.
Can safely be performed in place.
==================
*/
export function W_CleanupName( inStr ) {

	let out = '';
	for ( let i = 0; i < 16; i ++ ) {

		if ( i >= inStr.length ) break;
		let c = inStr.charCodeAt( i );
		if ( c === 0 ) break;

		if ( c >= 65 && c <= 90 ) // 'A' to 'Z'
			c += 32; // to lowercase
		out += String.fromCharCode( c );

	}

	return out;

}

/*
====================
W_LoadWadFile
====================
*/
export function W_LoadWadFile( data ) {

	// data is an ArrayBuffer
	wad_base = new Uint8Array( data );
	const view = new DataView( data );

	// check identification
	const id0 = wad_base[ 0 ];
	const id1 = wad_base[ 1 ];
	const id2 = wad_base[ 2 ];
	const id3 = wad_base[ 3 ];

	if ( id0 !== 0x57 || id1 !== 0x41 || id2 !== 0x44 || id3 !== 0x32 ) // 'WAD2'
		Sys_Error( 'W_LoadWadFile: not a WAD2 file' );

	wad_numlumps = view.getInt32( 4, true );
	const infotableofs = view.getInt32( 8, true );

	// parse lump info table
	wad_lumps = [];
	for ( let i = 0; i < wad_numlumps; i ++ ) {

		const offset = infotableofs + i * 32; // sizeof(lumpinfo_t) = 32
		const lump = {
			filepos: view.getInt32( offset, true ),
			disksize: view.getInt32( offset + 4, true ),
			size: view.getInt32( offset + 8, true ),
			type: wad_base[ offset + 12 ],
			compression: wad_base[ offset + 13 ],
			name: ''
		};

		// read name (16 bytes at offset + 16)
		let name = '';
		for ( let j = 0; j < 16; j ++ ) {

			const c = wad_base[ offset + 16 + j ];
			if ( c === 0 ) break;
			name += String.fromCharCode( c );

		}

		lump.name = W_CleanupName( name );

		// swap qpic if needed
		if ( lump.type === TYP_QPIC ) {

			// SwapPic - width and height are already little-endian on browser
			// (DataView handles byte order)

		}

		wad_lumps.push( lump );

	}

}

/*
=============
W_GetLumpinfo
=============
*/
export function W_GetLumpinfo( name ) {

	const clean = W_CleanupName( name );

	for ( let i = 0; i < wad_numlumps; i ++ ) {

		if ( wad_lumps[ i ].name === clean )
			return wad_lumps[ i ];

	}

	Sys_Error( 'W_GetLumpinfo: ' + name + ' not found' );
	return null;

}

/*
=============
W_GetLumpName

Returns a DataView into the wad data at the lump's position
=============
*/
export function W_GetLumpName( name ) {

	const lump = W_GetLumpinfo( name );
	return {
		data: wad_base,
		offset: lump.filepos,
		size: lump.size
	};

}

/*
=============
W_GetLumpNum
=============
*/
export function W_GetLumpNum( num ) {

	if ( num < 0 || num >= wad_numlumps )
		Sys_Error( 'W_GetLumpNum: bad number: ' + num );

	const lump = wad_lumps[ num ];
	return {
		data: wad_base,
		offset: lump.filepos,
		size: lump.size
	};

}

/*
=============
SwapPic
=============
*/
export function SwapPic( data, offset ) {

	// In the original C, this byte-swaps width/height from little-endian.
	// JavaScript DataView handles this, so this is a no-op on little-endian systems.
	// We keep it for API compatibility.
	const view = new DataView( data.buffer, offset );
	return {
		width: view.getInt32( 0, true ),
		height: view.getInt32( 4, true ),
		data: data.subarray( offset + 8 )
	};

}
