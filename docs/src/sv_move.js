// Ported from: WinQuake/sv_move.c -- monster movement

import { vec3_origin, DotProduct, VectorCopy, VectorAdd, VectorSubtract,
	VectorNormalize, M_PI, anglemod } from './mathlib.js';
import { YAW } from './quakedef.js';
import { MOVETYPE_FLY, MOVETYPE_WALK, FL_FLY, FL_SWIM, FL_ONGROUND,
	FL_PARTIALGROUND, CONTENTS_EMPTY, CONTENTS_SOLID,
	sv, svs, pr_global_struct, sv_player,
	SV_Move, SV_TestEntityPosition, SV_LinkEdict, SV_PointContents,
	PR_ExecuteProgram, EDICT_TO_PROG, PROG_TO_EDICT } from './sv_phys.js';

const STEPSIZE = 18;

const DI_NODIR = - 1;

// Cached buffers for SV_CheckBottom (Golden Rule #4)
const _checkbottom_mins = new Float32Array( 3 );
const _checkbottom_maxs = new Float32Array( 3 );
const _checkbottom_start = new Float32Array( 3 );
const _checkbottom_stop = new Float32Array( 3 );

// Cached buffers for SV_movestep (Golden Rule #4)
const _movestep_oldorg = new Float32Array( 3 );
const _movestep_neworg = new Float32Array( 3 );
const _movestep_end = new Float32Array( 3 );

// Cached buffers for SV_StepDirection (Golden Rule #4)
const _stepdir_move = new Float32Array( 3 );
const _stepdir_oldorigin = new Float32Array( 3 );

// Cached buffer for SV_NewChaseDir (Golden Rule #4)
const _chasedir_d = new Float32Array( 3 );

// Debug counters
let c_yes = 0;
let c_no = 0;

// External callback stubs (set by engine)
export let PF_changeyaw = null;
export let G_FLOAT = null;
export let G_FLOAT_SET = null;

export function SV_Move_SetCallbacks( callbacks ) {

	if ( callbacks.PF_changeyaw ) PF_changeyaw = callbacks.PF_changeyaw;
	if ( callbacks.G_FLOAT ) G_FLOAT = callbacks.G_FLOAT;
	if ( callbacks.G_FLOAT_SET ) G_FLOAT_SET = callbacks.G_FLOAT_SET;

}

/*
=============
SV_CheckBottom

Returns false if any part of the bottom of the entity is off an edge that
is not a staircase.
=============
*/
export function SV_CheckBottom( ent ) {

	const mins = _checkbottom_mins;
	const maxs = _checkbottom_maxs;
	const start = _checkbottom_start;
	const stop = _checkbottom_stop;

	VectorAdd( ent.v.origin, ent.v.mins, mins );
	VectorAdd( ent.v.origin, ent.v.maxs, maxs );

	// if all of the points under the corners are solid world, don't bother
	// with the tougher checks
	// the corners must be within 16 of the midpoint
	start[ 2 ] = mins[ 2 ] - 1;
	let doRealCheck = false;
	for ( let x = 0; x <= 1; x ++ ) {

		for ( let y = 0; y <= 1; y ++ ) {

			start[ 0 ] = x ? maxs[ 0 ] : mins[ 0 ];
			start[ 1 ] = y ? maxs[ 1 ] : mins[ 1 ];
			if ( SV_PointContents( start ) !== CONTENTS_SOLID ) {

				doRealCheck = true;
				break;

			}

		}

		if ( doRealCheck ) break;

	}

	if ( ! doRealCheck ) {

		c_yes ++;
		return true; // we got out easy

	}

	c_no ++;
	//
	// check it for real...
	//
	start[ 2 ] = mins[ 2 ];

	// the midpoint must be within 16 of the bottom
	start[ 0 ] = stop[ 0 ] = ( mins[ 0 ] + maxs[ 0 ] ) * 0.5;
	start[ 1 ] = stop[ 1 ] = ( mins[ 1 ] + maxs[ 1 ] ) * 0.5;
	stop[ 2 ] = start[ 2 ] - 2 * STEPSIZE;
	let trace = SV_Move( start, vec3_origin, vec3_origin, stop, true, ent );

	if ( trace.fraction === 1.0 )
		return false;
	const mid = trace.endpos[ 2 ];
	let bottom = mid;

	// the corners must be within 16 of the midpoint
	for ( let x = 0; x <= 1; x ++ ) {

		for ( let y = 0; y <= 1; y ++ ) {

			start[ 0 ] = stop[ 0 ] = x ? maxs[ 0 ] : mins[ 0 ];
			start[ 1 ] = stop[ 1 ] = y ? maxs[ 1 ] : mins[ 1 ];

			trace = SV_Move( start, vec3_origin, vec3_origin, stop, true, ent );

			if ( trace.fraction !== 1.0 && trace.endpos[ 2 ] > bottom )
				bottom = trace.endpos[ 2 ];
			if ( trace.fraction === 1.0 || mid - trace.endpos[ 2 ] > STEPSIZE )
				return false;

		}

	}

	c_yes ++;
	return true;

}

/*
=============
SV_movestep

Called by monster program code.
The move will be adjusted for slopes and stairs, but if the move isn't
possible, no move is done, false is returned, and
pr_global_struct.trace_normal is set to the normal of the blocking wall
=============
*/
export function SV_movestep( ent, move, relink ) {

	const oldorg = _movestep_oldorg;
	const neworg = _movestep_neworg;
	const end = _movestep_end;

	// try the move
	VectorCopy( ent.v.origin, oldorg );
	VectorAdd( ent.v.origin, move, neworg );

	// flying monsters don't step up
	if ( ( ent.v.flags | 0 ) & ( FL_SWIM | FL_FLY ) ) {

		// try one move with vertical motion, then one without
		for ( let i = 0; i < 2; i ++ ) {

			VectorAdd( ent.v.origin, move, neworg );
			const enemy = PROG_TO_EDICT( ent.v.enemy );
			if ( i === 0 && enemy !== sv.edicts[ 0 ] ) {

				const dz = ent.v.origin[ 2 ] - PROG_TO_EDICT( ent.v.enemy ).v.origin[ 2 ];
				if ( dz > 40 )
					neworg[ 2 ] -= 8;
				if ( dz < 30 )
					neworg[ 2 ] += 8;

			}

			const trace = SV_Move( ent.v.origin, ent.v.mins, ent.v.maxs, neworg, false, ent );

			if ( trace.fraction === 1 ) {

				if ( ( ( ent.v.flags | 0 ) & FL_SWIM ) && SV_PointContents( trace.endpos ) === CONTENTS_EMPTY )
					return false; // swim monster left water

				VectorCopy( trace.endpos, ent.v.origin );
				if ( relink )
					SV_LinkEdict( ent, true );
				return true;

			}

			if ( enemy === sv.edicts[ 0 ] )
				break;

		}

		return false;

	}

	// push down from a step height above the wished position
	neworg[ 2 ] += STEPSIZE;
	VectorCopy( neworg, end );
	end[ 2 ] -= STEPSIZE * 2;

	let trace = SV_Move( neworg, ent.v.mins, ent.v.maxs, end, false, ent );

	if ( trace.allsolid )
		return false;

	if ( trace.startsolid ) {

		neworg[ 2 ] -= STEPSIZE;
		trace = SV_Move( neworg, ent.v.mins, ent.v.maxs, end, false, ent );
		if ( trace.allsolid || trace.startsolid )
			return false;

	}

	if ( trace.fraction === 1 ) {

		// if monster had the ground pulled out, go ahead and fall
		if ( ( ent.v.flags | 0 ) & FL_PARTIALGROUND ) {

			VectorAdd( ent.v.origin, move, ent.v.origin );
			if ( relink )
				SV_LinkEdict( ent, true );
			ent.v.flags = ( ent.v.flags | 0 ) & ~FL_ONGROUND;
			return true;

		}

		return false; // walked off an edge

	}

	// check point traces down for dangling corners
	VectorCopy( trace.endpos, ent.v.origin );

	if ( ! SV_CheckBottom( ent ) ) {

		if ( ( ent.v.flags | 0 ) & FL_PARTIALGROUND ) {

			// entity had floor mostly pulled out from underneath it
			// and is trying to correct
			if ( relink )
				SV_LinkEdict( ent, true );
			return true;

		}

		VectorCopy( oldorg, ent.v.origin );
		return false;

	}

	if ( ( ent.v.flags | 0 ) & FL_PARTIALGROUND ) {

		ent.v.flags = ( ent.v.flags | 0 ) & ~FL_PARTIALGROUND;

	}

	ent.v.groundentity = EDICT_TO_PROG( trace.ent );

	// the move is ok
	if ( relink )
		SV_LinkEdict( ent, true );
	return true;

}

//============================================================================

/*
======================
SV_StepDirection

Turns to the movement direction, and walks the current distance if
facing it.
======================
*/
export function SV_StepDirection( ent, yaw, dist ) {

	const move = _stepdir_move;
	const oldorigin = _stepdir_oldorigin;

	ent.v.ideal_yaw = yaw;
	PF_changeyaw();

	const yawRad = yaw * M_PI * 2 / 360;
	move[ 0 ] = Math.cos( yawRad ) * dist;
	move[ 1 ] = Math.sin( yawRad ) * dist;
	move[ 2 ] = 0;

	VectorCopy( ent.v.origin, oldorigin );
	if ( SV_movestep( ent, move, false ) ) {

		const delta = ent.v.angles[ YAW ] - ent.v.ideal_yaw;
		if ( delta > 45 && delta < 315 ) {

			// not turned far enough, so don't take the step
			VectorCopy( oldorigin, ent.v.origin );

		}

		SV_LinkEdict( ent, true );
		return true;

	}

	SV_LinkEdict( ent, true );

	return false;

}

/*
======================
SV_FixCheckBottom
======================
*/
export function SV_FixCheckBottom( ent ) {

	ent.v.flags = ( ent.v.flags | 0 ) | FL_PARTIALGROUND;

}

/*
================
SV_NewChaseDir
================
*/
export function SV_NewChaseDir( actor, enemy, dist ) {

	const d = _chasedir_d;

	const olddir = anglemod( ( ( actor.v.ideal_yaw / 45 ) | 0 ) * 45 );
	const turnaround = anglemod( olddir - 180 );

	const deltax = enemy.v.origin[ 0 ] - actor.v.origin[ 0 ];
	const deltay = enemy.v.origin[ 1 ] - actor.v.origin[ 1 ];
	if ( deltax > 10 )
		d[ 1 ] = 0;
	else if ( deltax < - 10 )
		d[ 1 ] = 180;
	else
		d[ 1 ] = DI_NODIR;
	if ( deltay < - 10 )
		d[ 2 ] = 270;
	else if ( deltay > 10 )
		d[ 2 ] = 90;
	else
		d[ 2 ] = DI_NODIR;

	// try direct route
	let tdir;
	if ( d[ 1 ] !== DI_NODIR && d[ 2 ] !== DI_NODIR ) {

		if ( d[ 1 ] === 0 )
			tdir = d[ 2 ] === 90 ? 45 : 315;
		else
			tdir = d[ 2 ] === 90 ? 135 : 215;

		if ( tdir !== turnaround && SV_StepDirection( actor, tdir, dist ) )
			return;

	}

	// try other directions
	if ( ( ( Math.random() * 4 | 0 ) & 1 ) || Math.abs( deltay ) > Math.abs( deltax ) ) {

		tdir = d[ 1 ];
		d[ 1 ] = d[ 2 ];
		d[ 2 ] = tdir;

	}

	if ( d[ 1 ] !== DI_NODIR && d[ 1 ] !== turnaround
		&& SV_StepDirection( actor, d[ 1 ], dist ) )
		return;

	if ( d[ 2 ] !== DI_NODIR && d[ 2 ] !== turnaround
		&& SV_StepDirection( actor, d[ 2 ], dist ) )
		return;

	/* there is no direct path to the player, so pick another direction */

	if ( olddir !== DI_NODIR && SV_StepDirection( actor, olddir, dist ) )
		return;

	if ( Math.random() > 0.5 ) {

		/* randomly determine direction of search */
		for ( tdir = 0; tdir <= 315; tdir += 45 )
			if ( tdir !== turnaround && SV_StepDirection( actor, tdir, dist ) )
				return;

	} else {

		for ( tdir = 315; tdir >= 0; tdir -= 45 )
			if ( tdir !== turnaround && SV_StepDirection( actor, tdir, dist ) )
				return;

	}

	if ( turnaround !== DI_NODIR && SV_StepDirection( actor, turnaround, dist ) )
		return;

	actor.v.ideal_yaw = olddir; // can't move

	// if a bridge was pulled out from underneath a monster, it may not have
	// a valid standing position at all

	if ( ! SV_CheckBottom( actor ) )
		SV_FixCheckBottom( actor );

}

/*
======================
SV_CloseEnough
======================
*/
export function SV_CloseEnough( ent, goal, dist ) {

	for ( let i = 0; i < 3; i ++ ) {

		if ( goal.v.absmin[ i ] > ent.v.absmax[ i ] + dist )
			return false;
		if ( goal.v.absmax[ i ] < ent.v.absmin[ i ] - dist )
			return false;

	}

	return true;

}

/*
======================
SV_MoveToGoal
======================
*/
export function SV_MoveToGoal() {

	const ent = PROG_TO_EDICT( pr_global_struct.self );
	const goal = PROG_TO_EDICT( ent.v.goalentity );
	const dist = G_FLOAT( 4 ); // OFS_PARM0

	if ( ! ( ( ent.v.flags | 0 ) & ( FL_ONGROUND | FL_FLY | FL_SWIM ) ) ) {

		G_FLOAT_SET( 1, 0 ); // OFS_RETURN = 0
		return;

	}

	// if the next step hits the enemy, return immediately
	if ( PROG_TO_EDICT( ent.v.enemy ) !== sv.edicts[ 0 ] && SV_CloseEnough( ent, goal, dist ) )
		return;

	// bump around...
	if ( ( ( Math.random() * 4 | 0 ) & 3 ) === 1
		|| ! SV_StepDirection( ent, ent.v.ideal_yaw, dist ) ) {

		SV_NewChaseDir( ent, goal, dist );

	}

}
