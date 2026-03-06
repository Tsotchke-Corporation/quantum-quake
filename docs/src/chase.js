// Ported from: WinQuake/chase.c -- chase camera code

import { PITCH } from './quakedef.js';
import { cvar_t, Cvar_RegisterVariable } from './cvar.js';
import { VectorCopy, VectorSubtract, VectorMA, DotProduct,
	AngleVectors, M_PI } from './mathlib.js';
import { cl } from './client.js';
import { r_refdef } from './render.js';

export const chase_back = new cvar_t( 'chase_back', '100' );
export const chase_up = new cvar_t( 'chase_up', '16' );
export const chase_right = new cvar_t( 'chase_right', '0' );
export const chase_active = new cvar_t( 'chase_active', '0' );

const chase_dest = new Float32Array( 3 );

// Cached vectors for Chase_Update (Golden Rule #4 - no allocations in render loop)
const _chase_forward = new Float32Array( 3 );
const _chase_up = new Float32Array( 3 );
const _chase_right = new Float32Array( 3 );
const _chase_dest = new Float32Array( 3 );
const _chase_stop = new Float32Array( 3 );

// Lazy-loaded collision imports (avoids circular dependency through world.js -> server.js -> menu.js -> keys.js)
let _SV_RecursiveHullCheck = null;
let _trace_t = null;
let _chase_trace = null;

export function Chase_Init() {

	Cvar_RegisterVariable( chase_back );
	Cvar_RegisterVariable( chase_up );
	Cvar_RegisterVariable( chase_right );
	Cvar_RegisterVariable( chase_active );

	// Lazy-load collision detection to avoid circular dependency
	import( './world.js' ).then( ( world ) => {

		_SV_RecursiveHullCheck = world.SV_RecursiveHullCheck;
		_trace_t = world.trace_t;
		_chase_trace = new world.trace_t();

	} );

}

export function Chase_Reset() {

	// for respawning and teleporting
	// start position 12 units behind head

}

function TraceLine( start, end, impact ) {

	// Use BSP collision if available (ported from chase.c)
	if ( _SV_RecursiveHullCheck != null && _chase_trace != null
		&& cl.worldmodel != null && cl.worldmodel.hulls != null ) {

		// Reset trace
		_chase_trace.allsolid = false;
		_chase_trace.startsolid = false;
		_chase_trace.inopen = false;
		_chase_trace.inwater = false;
		_chase_trace.fraction = 1.0;
		_chase_trace.endpos[ 0 ] = end[ 0 ];
		_chase_trace.endpos[ 1 ] = end[ 1 ];
		_chase_trace.endpos[ 2 ] = end[ 2 ];
		_chase_trace.ent = null;

		_SV_RecursiveHullCheck( cl.worldmodel.hulls[ 0 ], 0, 0, 1, start, end, _chase_trace );

		VectorCopy( _chase_trace.endpos, impact );

	} else {

		// Fallback: just copy end to impact
		VectorCopy( end, impact );

	}

}

export function Chase_Update() {

	// Use cached vectors (Golden Rule #4)
	const forward = _chase_forward;
	const up = _chase_up;
	const right = _chase_right;
	const dest = _chase_dest;
	const stop = _chase_stop;

	// if can't see player, reset
	AngleVectors( cl.viewangles, forward, right, up );

	// calc exact destination
	for ( let i = 0; i < 3; i ++ )
		chase_dest[ i ] = r_refdef.vieworg[ i ]
		- forward[ i ] * chase_back.value
		- right[ i ] * chase_right.value;
	chase_dest[ 2 ] = r_refdef.vieworg[ 2 ] + chase_up.value;

	// find the spot the player is looking at
	VectorMA( r_refdef.vieworg, 4096, forward, dest );
	TraceLine( r_refdef.vieworg, dest, stop );

	// calculate pitch to look at the same spot from camera
	VectorSubtract( stop, r_refdef.vieworg, stop );
	let dist = DotProduct( stop, forward );
	if ( dist < 1 )
		dist = 1;
	r_refdef.viewangles[ PITCH ] = - Math.atan( stop[ 2 ] / dist ) / M_PI * 180;

	// move towards destination
	VectorCopy( chase_dest, r_refdef.vieworg );

}
