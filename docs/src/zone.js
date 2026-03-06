// Ported from: WinQuake/zone.c + zone.h -- memory allocation
//
// In JavaScript we have garbage collection, so the complex hunk/zone/cache
// memory management from C is simplified. We keep the API surface for
// compatibility with the rest of the port but let JS handle actual allocation.

import { Sys_Error } from './sys.js';
import { Con_Printf, Con_DPrintf } from './common.js';

/*
Memory layout in original Quake (for reference):

------ Top of Memory -------
high hunk allocations
video buffer / z buffer / surface cache
cachable memory
client and server low hunk allocations
startup hunk allocations
Zone block
----- Bottom of Memory -----

In JS, we simplify:
- Zone = general small allocations (just use JS objects)
- Hunk = level-load allocations (just use JS objects, track for clearing)
- Cache = persistable data across levels (Map with LRU eviction)
- Temp = temporary allocations (just use JS objects)
*/

// cache_user_t equivalent
export class cache_user_t {

	constructor() {

		this.data = null;

	}

}

// Track hunk marks for level transitions
let hunk_low_mark = 0;
let hunk_high_mark = 0;
let hunk_temp_active = false;
let hunk_temp_mark = 0;

// Zone allocations - in JS just track for debugging
let zone_allocated = 0;

// Cache system - simple Map-based LRU
const cache_entries = new Map(); // name -> { data, user, size }
const cache_lru = []; // ordered from most recent to least recent

/*
========================
Memory_Init
========================
*/
export function Memory_Init() {

	Cache_Init();
	Con_Printf( 'Memory initialized (JavaScript GC mode)\\n' );

}

/*
=============================================================================

						ZONE MEMORY ALLOCATION

Zone memory in JS is just regular allocations tracked for debugging.
=============================================================================
*/

/*
========================
Z_Malloc

Returns zero-filled memory. In JS, returns an ArrayBuffer or object.
========================
*/
export function Z_Malloc( size ) {

	zone_allocated += size;
	return new ArrayBuffer( size );

}

/*
========================
Z_Free
========================
*/
export function Z_Free( ptr ) {

	// In JS, just let GC handle it
	// We could track and subtract from zone_allocated but it's not critical

}

/*
========================
Z_FreeMemory
========================
*/
export function Z_FreeMemory() {

	return 0x100000 - zone_allocated; // approximate

}

/*
=============================================================================

						HUNK MEMORY ALLOCATION

In JS, hunk allocations are regular allocations. We track marks so
level transitions can conceptually "free" old data.
=============================================================================
*/

/*
===================
Hunk_AllocName
===================
*/
export function Hunk_AllocName( size, name ) {

	// In JS, just allocate. The name is for debugging.
	const buf = new ArrayBuffer( size );
	hunk_low_mark += size;
	return buf;

}

/*
===================
Hunk_Alloc
===================
*/
export function Hunk_Alloc( size ) {

	return Hunk_AllocName( size, 'unknown' );

}

export function Hunk_LowMark() {

	return hunk_low_mark;

}

export function Hunk_FreeToLowMark( mark ) {

	hunk_low_mark = mark;
	// In JS, actual memory freed by GC when references dropped

}

export function Hunk_HighMark() {

	if ( hunk_temp_active ) {

		hunk_temp_active = false;
		Hunk_FreeToHighMark( hunk_temp_mark );

	}

	return hunk_high_mark;

}

export function Hunk_FreeToHighMark( mark ) {

	if ( hunk_temp_active ) {

		hunk_temp_active = false;
		Hunk_FreeToHighMark( hunk_temp_mark );

	}

	hunk_high_mark = mark;

}

/*
===================
Hunk_HighAllocName
===================
*/
export function Hunk_HighAllocName( size, name ) {

	if ( hunk_temp_active ) {

		Hunk_FreeToHighMark( hunk_temp_mark );
		hunk_temp_active = false;

	}

	hunk_high_mark += size;
	return new ArrayBuffer( size );

}

/*
=================
Hunk_TempAlloc

Return space from the top of the hunk
=================
*/
export function Hunk_TempAlloc( size ) {

	if ( hunk_temp_active ) {

		Hunk_FreeToHighMark( hunk_temp_mark );
		hunk_temp_active = false;

	}

	hunk_temp_mark = Hunk_HighMark();
	const buf = Hunk_HighAllocName( size, 'temp' );
	hunk_temp_active = true;

	return buf;

}

export function Hunk_Check() {

	// No-op in JS

}

/*
=============================================================================

						CACHE MEMORY

In JS we use a simple Map with LRU tracking.
=============================================================================
*/

/*
============
Cache_Init
============
*/
function Cache_Init() {

	cache_entries.clear();
	cache_lru.length = 0;

}

/*
============
Cache_Flush

Throw everything out, so new data will be demand cached
============
*/
export function Cache_Flush() {

	for ( const [ name, entry ] of cache_entries ) {

		if ( entry.user ) {

			entry.user.data = null;

		}

	}

	cache_entries.clear();
	cache_lru.length = 0;

}

/*
==============
Cache_Free

Frees the memory and removes it from the LRU list
==============
*/
export function Cache_Free( c ) {

	if ( ! c.data )
		Sys_Error( 'Cache_Free: not allocated' );

	// Find and remove from cache
	for ( const [ name, entry ] of cache_entries ) {

		if ( entry.user === c ) {

			cache_entries.delete( name );
			const idx = cache_lru.indexOf( name );
			if ( idx !== - 1 ) cache_lru.splice( idx, 1 );
			break;

		}

	}

	c.data = null;

}

/*
==============
Cache_Check

Returns the cached data, and moves to the head of the LRU list
if present, otherwise returns null
==============
*/
export function Cache_Check( c ) {

	if ( ! c.data )
		return null;

	// Move to front of LRU
	for ( const [ name, entry ] of cache_entries ) {

		if ( entry.user === c ) {

			const idx = cache_lru.indexOf( name );
			if ( idx !== - 1 ) {

				cache_lru.splice( idx, 1 );
				cache_lru.unshift( name );

			}

			break;

		}

	}

	return c.data;

}

/*
==============
Cache_Alloc
==============
*/
export function Cache_Alloc( c, size, name ) {

	if ( c.data )
		Sys_Error( 'Cache_Alloc: already allocated' );

	if ( size <= 0 )
		Sys_Error( 'Cache_Alloc: size ' + size );

	const data = new ArrayBuffer( size );
	c.data = data;

	cache_entries.set( name, { data: data, user: c, size: size } );
	cache_lru.unshift( name );

	return data;

}

/*
============
Cache_Report
============
*/
export function Cache_Report() {

	let total = 0;
	for ( const [ name, entry ] of cache_entries ) {

		total += entry.size;

	}

	Con_DPrintf( ( total / ( 1024 * 1024 ) ).toFixed( 1 ) + ' megabyte data cache\\n' );

}
