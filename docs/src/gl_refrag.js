// Ported from: WinQuake/gl_refrag.c -- entity fragment functions

import { Con_Printf } from './console.js';
import { CONTENTS_SOLID } from './bspfile.js';

/*
===============================================================================

					ENTITY FRAGMENT FUNCTIONS

===============================================================================
*/

let r_pefragtopnode = null;
let lastlink = null;
const r_emins = new Float32Array( 3 );
const r_emaxs = new Float32Array( 3 );
let r_addent = null;

// External references (set via setters)
let _cl = null;

export function R_Efrag_SetExternals( externals ) {

	if ( externals.cl ) _cl = externals.cl;

}

/*
================
BOX_ON_PLANE_SIDE

Returns 1 if box is entirely on front side of plane,
2 if entirely on back side, or 3 if crossing the plane
================
*/
function BOX_ON_PLANE_SIDE( emins, emaxs, p ) {

	const normal = p.normal;
	const dist = p.dist;

	// Fast axial cases
	if ( p.type < 3 ) {

		if ( dist <= emins[ p.type ] )
			return 1;
		if ( dist >= emaxs[ p.type ] )
			return 2;
		return 3;

	}

	// General case
	let dist1, dist2;

	switch ( p.signbits ) {

		case 0:
			dist1 = normal[ 0 ] * emaxs[ 0 ] + normal[ 1 ] * emaxs[ 1 ] + normal[ 2 ] * emaxs[ 2 ];
			dist2 = normal[ 0 ] * emins[ 0 ] + normal[ 1 ] * emins[ 1 ] + normal[ 2 ] * emins[ 2 ];
			break;
		case 1:
			dist1 = normal[ 0 ] * emins[ 0 ] + normal[ 1 ] * emaxs[ 1 ] + normal[ 2 ] * emaxs[ 2 ];
			dist2 = normal[ 0 ] * emaxs[ 0 ] + normal[ 1 ] * emins[ 1 ] + normal[ 2 ] * emins[ 2 ];
			break;
		case 2:
			dist1 = normal[ 0 ] * emaxs[ 0 ] + normal[ 1 ] * emins[ 1 ] + normal[ 2 ] * emaxs[ 2 ];
			dist2 = normal[ 0 ] * emins[ 0 ] + normal[ 1 ] * emaxs[ 1 ] + normal[ 2 ] * emins[ 2 ];
			break;
		case 3:
			dist1 = normal[ 0 ] * emins[ 0 ] + normal[ 1 ] * emins[ 1 ] + normal[ 2 ] * emaxs[ 2 ];
			dist2 = normal[ 0 ] * emaxs[ 0 ] + normal[ 1 ] * emaxs[ 1 ] + normal[ 2 ] * emins[ 2 ];
			break;
		case 4:
			dist1 = normal[ 0 ] * emaxs[ 0 ] + normal[ 1 ] * emaxs[ 1 ] + normal[ 2 ] * emins[ 2 ];
			dist2 = normal[ 0 ] * emins[ 0 ] + normal[ 1 ] * emins[ 1 ] + normal[ 2 ] * emaxs[ 2 ];
			break;
		case 5:
			dist1 = normal[ 0 ] * emins[ 0 ] + normal[ 1 ] * emaxs[ 1 ] + normal[ 2 ] * emins[ 2 ];
			dist2 = normal[ 0 ] * emaxs[ 0 ] + normal[ 1 ] * emins[ 1 ] + normal[ 2 ] * emaxs[ 2 ];
			break;
		case 6:
			dist1 = normal[ 0 ] * emaxs[ 0 ] + normal[ 1 ] * emins[ 1 ] + normal[ 2 ] * emins[ 2 ];
			dist2 = normal[ 0 ] * emins[ 0 ] + normal[ 1 ] * emaxs[ 1 ] + normal[ 2 ] * emaxs[ 2 ];
			break;
		case 7:
			dist1 = normal[ 0 ] * emins[ 0 ] + normal[ 1 ] * emins[ 1 ] + normal[ 2 ] * emins[ 2 ];
			dist2 = normal[ 0 ] * emaxs[ 0 ] + normal[ 1 ] * emaxs[ 1 ] + normal[ 2 ] * emaxs[ 2 ];
			break;
		default:
			dist1 = dist2 = 0; // shut up compiler
			break;

	}

	let sides = 0;
	if ( dist1 >= dist ) sides = 1;
	if ( dist2 < dist ) sides |= 2;

	return sides;

}

/*
================
R_RemoveEfrags

Call when removing an object from the world or moving it to another position
================
*/
export function R_RemoveEfrags( ent ) {

	if ( _cl == null ) return;

	let ef = ent.efrag;

	while ( ef != null ) {

		// Remove from leaf's efrag list
		const leaf = ef.leaf;
		if ( leaf != null && leaf.efrags != null ) {

			if ( leaf.efrags === ef ) {

				leaf.efrags = ef.leafnext;

			} else {

				let prev = leaf.efrags;
				while ( prev != null && prev.leafnext !== ef ) {

					prev = prev.leafnext;

				}

				if ( prev != null ) {

					prev.leafnext = ef.leafnext;

				}

			}

		}

		const old = ef;
		ef = ef.entnext;

		// Put it on the free list
		old.entnext = _cl.free_efrags;
		_cl.free_efrags = old;

	}

	ent.efrag = null;

}

/*
===================
R_SplitEntityOnNode
===================
*/
function R_SplitEntityOnNode( node ) {

	if ( node == null ) return;
	if ( node.contents === CONTENTS_SOLID ) return;

	// Add an efrag if the node is a leaf
	if ( node.contents < 0 ) {

		if ( r_pefragtopnode == null )
			r_pefragtopnode = node;

		const leaf = node;

		// Grab an efrag off the free list
		const ef = _cl.free_efrags;
		if ( ef == null ) {

			Con_Printf( 'Too many efrags!\n' );
			return;

		}

		_cl.free_efrags = _cl.free_efrags.entnext;

		ef.entity = r_addent;

		// Add the entity link
		if ( lastlink != null ) {

			lastlink.entnext = ef;

		} else {

			r_addent.efrag = ef;

		}

		lastlink = ef;
		ef.entnext = null;

		// Set the leaf links
		ef.leaf = leaf;
		ef.leafnext = leaf.efrags;
		leaf.efrags = ef;

		return;

	}

	// NODE_MIXED - recurse down the contacted sides
	const splitplane = node.plane;
	const sides = BOX_ON_PLANE_SIDE( r_emins, r_emaxs, splitplane );

	if ( sides === 3 ) {

		// Split on this plane
		if ( r_pefragtopnode == null )
			r_pefragtopnode = node;

	}

	// Recurse down the contacted sides
	if ( sides & 1 )
		R_SplitEntityOnNode( node.children[ 0 ] );

	if ( sides & 2 )
		R_SplitEntityOnNode( node.children[ 1 ] );

}

/*
===========
R_AddEfrags
===========
*/
export function R_AddEfrags( ent ) {

	if ( _cl == null ) return;
	if ( ent.model == null ) return;

	r_addent = ent;

	// Initialize the entity's efrag chain
	lastlink = null;
	r_pefragtopnode = null;

	const entmodel = ent.model;

	for ( let i = 0; i < 3; i ++ ) {

		r_emins[ i ] = ent.origin[ i ] + entmodel.mins[ i ];
		r_emaxs[ i ] = ent.origin[ i ] + entmodel.maxs[ i ];

	}

	if ( _cl.worldmodel != null && _cl.worldmodel.nodes != null ) {

		R_SplitEntityOnNode( _cl.worldmodel.nodes[ 0 ] );

	}

	ent.topnode = r_pefragtopnode;

}

/*
================
R_StoreEfrags

Add efrags to the visible entity list
================
*/
export function R_StoreEfrags( ppefrag, cl_visedicts, cl_numvisedicts, MAX_VISEDICTS, r_framecount ) {

	let pefrag = ppefrag;

	while ( pefrag != null ) {

		const pent = pefrag.entity;
		const clmodel = pent.model;

		if ( clmodel != null && pent.visframe !== r_framecount && cl_numvisedicts < MAX_VISEDICTS ) {

			cl_visedicts[ cl_numvisedicts ] = pent;
			cl_numvisedicts ++;

			// Mark that we've recorded this entity for this frame
			pent.visframe = r_framecount;

		}

		pefrag = pefrag.leafnext;

	}

	return cl_numvisedicts;

}
