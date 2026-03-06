// Ported from: WinQuake/gl_warp.c -- sky and water polygons

import * as THREE from 'three';
import { Sys_Error } from './sys.js';
import { DotProduct, VectorCopy, VectorAdd, VectorSubtract, M_PI,
	vec3_origin } from './mathlib.js';
import { VERTEXSIZE, glpoly_t, gl_subdivide_size, r_origin,
	GL_Bind, GL_DisableMultitexture, d_lightstylevalue } from './glquake.js';

export let skytexturenum = 0;

export let solidskytexture = 0;
export let alphaskytexture = 0;
let speedscale = 0; // for top sky and bottom sky

let warpface = null; // msurface_t *

// external reference
let loadmodel = null;

export function GL_Warp_SetLoadmodel( m ) {

	loadmodel = m;

}

// speed up sin calculations - Ed
// Ported from gl_warp_sin.h
export const turbsin = new Float32Array( [
	0, 0.19633, 0.392541, 0.588517, 0.784137, 0.979285, 1.17384, 1.3677,
	1.56072, 1.75281, 1.94384, 2.1337, 2.32228, 2.50945, 2.69512, 2.87916,
	3.06147, 3.24193, 3.42044, 3.59689, 3.77117, 3.94319, 4.11282, 4.27998,
	4.44456, 4.60647, 4.76559, 4.92185, 5.07515, 5.22538, 5.37247, 5.51632,
	5.65685, 5.79398, 5.92761, 6.05767, 6.18408, 6.30677, 6.42566, 6.54068,
	6.65176, 6.75883, 6.86183, 6.9607, 7.05537, 7.14579, 7.23191, 7.31368,
	7.39104, 7.46394, 7.53235, 7.59623, 7.65552, 7.71021, 7.76025, 7.80562,
	7.84628, 7.88222, 7.91341, 7.93984, 7.96148, 7.97832, 7.99036, 7.99759,
	8, 7.99759, 7.99036, 7.97832, 7.96148, 7.93984, 7.91341, 7.88222,
	7.84628, 7.80562, 7.76025, 7.71021, 7.65552, 7.59623, 7.53235, 7.46394,
	7.39104, 7.31368, 7.23191, 7.14579, 7.05537, 6.9607, 6.86183, 6.75883,
	6.65176, 6.54068, 6.42566, 6.30677, 6.18408, 6.05767, 5.92761, 5.79398,
	5.65685, 5.51632, 5.37247, 5.22538, 5.07515, 4.92185, 4.76559, 4.60647,
	4.44456, 4.27998, 4.11282, 3.94319, 3.77117, 3.59689, 3.42044, 3.24193,
	3.06147, 2.87916, 2.69512, 2.50945, 2.32228, 2.1337, 1.94384, 1.75281,
	1.56072, 1.3677, 1.17384, 0.979285, 0.784137, 0.588517, 0.392541, 0.19633,
	0, - 0.19633, - 0.392541, - 0.588517, - 0.784137, - 0.979285, - 1.17384, - 1.3677,
	- 1.56072, - 1.75281, - 1.94384, - 2.1337, - 2.32228, - 2.50945, - 2.69512, - 2.87916,
	- 3.06147, - 3.24193, - 3.42044, - 3.59689, - 3.77117, - 3.94319, - 4.11282, - 4.27998,
	- 4.44456, - 4.60647, - 4.76559, - 4.92185, - 5.07515, - 5.22538, - 5.37247, - 5.51632,
	- 5.65685, - 5.79398, - 5.92761, - 6.05767, - 6.18408, - 6.30677, - 6.42566, - 6.54068,
	- 6.65176, - 6.75883, - 6.86183, - 6.9607, - 7.05537, - 7.14579, - 7.23191, - 7.31368,
	- 7.39104, - 7.46394, - 7.53235, - 7.59623, - 7.65552, - 7.71021, - 7.76025, - 7.80562,
	- 7.84628, - 7.88222, - 7.91341, - 7.93984, - 7.96148, - 7.97832, - 7.99036, - 7.99759,
	- 8, - 7.99759, - 7.99036, - 7.97832, - 7.96148, - 7.93984, - 7.91341, - 7.88222,
	- 7.84628, - 7.80562, - 7.76025, - 7.71021, - 7.65552, - 7.59623, - 7.53235, - 7.46394,
	- 7.39104, - 7.31368, - 7.23191, - 7.14579, - 7.05537, - 6.9607, - 6.86183, - 6.75883,
	- 6.65176, - 6.54068, - 6.42566, - 6.30677, - 6.18408, - 6.05767, - 5.92761, - 5.79398,
	- 5.65685, - 5.51632, - 5.37247, - 5.22538, - 5.07515, - 4.92185, - 4.76559, - 4.60647,
	- 4.44456, - 4.27998, - 4.11282, - 3.94319, - 3.77117, - 3.59689, - 3.42044, - 3.24193,
	- 3.06147, - 2.87916, - 2.69512, - 2.50945, - 2.32228, - 2.1337, - 1.94384, - 1.75281,
	- 1.56072, - 1.3677, - 1.17384, - 0.979285, - 0.784137, - 0.588517, - 0.392541, - 0.19633,
] );

const TURBSCALE = ( 256.0 / ( 2 * M_PI ) );

/*
=============
BoundPoly
=============
*/
export function BoundPoly( numverts, verts, mins, maxs ) {

	mins[ 0 ] = mins[ 1 ] = mins[ 2 ] = 9999;
	maxs[ 0 ] = maxs[ 1 ] = maxs[ 2 ] = - 9999;

	let vIdx = 0;
	for ( let i = 0; i < numverts; i ++ ) {

		for ( let j = 0; j < 3; j ++, vIdx ++ ) {

			if ( verts[ vIdx ] < mins[ j ] )
				mins[ j ] = verts[ vIdx ];
			if ( verts[ vIdx ] > maxs[ j ] )
				maxs[ j ] = verts[ vIdx ];

		}

	}

}

/*
=============
SubdividePolygon
=============
*/
export function SubdividePolygon( numverts, verts ) {

	if ( numverts > 60 )
		Sys_Error( 'numverts = ' + numverts );

	const mins = new Float32Array( 3 );
	const maxs = new Float32Array( 3 );
	BoundPoly( numverts, verts, mins, maxs );

	for ( let i = 0; i < 3; i ++ ) {

		let m = ( mins[ i ] + maxs[ i ] ) * 0.5;
		m = gl_subdivide_size.value * Math.floor( m / gl_subdivide_size.value + 0.5 );
		if ( maxs[ i ] - m < 8 )
			continue;
		if ( m - mins[ i ] < 8 )
			continue;

		// cut it
		const dist = new Float32Array( 65 );
		for ( let j = 0; j < numverts; j ++ )
			dist[ j ] = verts[ j * 3 + i ] - m;

		// wrap cases
		dist[ numverts ] = dist[ 0 ];
		// copy first vert to end
		const wrapIdx = numverts * 3;
		verts[ wrapIdx ] = verts[ 0 ];
		verts[ wrapIdx + 1 ] = verts[ 1 ];
		verts[ wrapIdx + 2 ] = verts[ 2 ];

		const front = []; // flat array of vec3
		const back = [];
		let f = 0, b = 0;

		for ( let j = 0; j < numverts; j ++ ) {

			const vOff = j * 3;
			if ( dist[ j ] >= 0 ) {

				front.push( verts[ vOff ], verts[ vOff + 1 ], verts[ vOff + 2 ] );
				f ++;

			}

			if ( dist[ j ] <= 0 ) {

				back.push( verts[ vOff ], verts[ vOff + 1 ], verts[ vOff + 2 ] );
				b ++;

			}

			if ( dist[ j ] === 0 || dist[ j + 1 ] === 0 )
				continue;
			if ( ( dist[ j ] > 0 ) !== ( dist[ j + 1 ] > 0 ) ) {

				// clip point
				const frac = dist[ j ] / ( dist[ j ] - dist[ j + 1 ] );
				for ( let k = 0; k < 3; k ++ ) {

					const clipVal = verts[ vOff + k ] + frac * ( verts[ vOff + 3 + k ] - verts[ vOff + k ] );
					front.push( clipVal );
					back.push( clipVal );

				}

				f ++;
				b ++;

			}

		}

		// Allocate extra room for the wrap vertex
		const frontArr = new Float32Array( ( f + 1 ) * 3 );
		for ( let fi = 0; fi < f * 3; fi ++ ) frontArr[ fi ] = front[ fi ];
		const backArr = new Float32Array( ( b + 1 ) * 3 );
		for ( let bi = 0; bi < b * 3; bi ++ ) backArr[ bi ] = back[ bi ];
		SubdividePolygon( f, frontArr );
		SubdividePolygon( b, backArr );
		return;

	}

	// No more subdivision needed - create a polygon
	const poly = new glpoly_t();
	poly.next = warpface.polys;
	warpface.polys = poly;
	poly.numverts = numverts;
	for ( let i = 0; i < numverts; i ++ ) {

		const vOff = i * 3;
		const vert = new Float32Array( VERTEXSIZE );
		vert[ 0 ] = verts[ vOff ];
		vert[ 1 ] = verts[ vOff + 1 ];
		vert[ 2 ] = verts[ vOff + 2 ];
		const s = DotProduct(
			[ verts[ vOff ], verts[ vOff + 1 ], verts[ vOff + 2 ] ],
			warpface.texinfo.vecs[ 0 ]
		);
		const t = DotProduct(
			[ verts[ vOff ], verts[ vOff + 1 ], verts[ vOff + 2 ] ],
			warpface.texinfo.vecs[ 1 ]
		);
		vert[ 3 ] = s;
		vert[ 4 ] = t;
		poly.verts.push( vert );

	}

}

/*
================
GL_SubdivideSurface

Breaks a polygon up along axial 64 unit
boundaries so that turbulent and sky warps
can be done reasonably.
================
*/
export function GL_SubdivideSurface( fa ) {

	warpface = fa;

	//
	// convert edges back to a normal polygon
	//
	const verts = [];
	let numverts = 0;
	for ( let i = 0; i < fa.numedges; i ++ ) {

		const lindex = loadmodel.surfedges[ fa.firstedge + i ];

		let vec;
		if ( lindex > 0 )
			vec = loadmodel.vertexes[ loadmodel.edges[ lindex ].v[ 0 ] ].position;
		else
			vec = loadmodel.vertexes[ loadmodel.edges[ - lindex ].v[ 1 ] ].position;

		verts.push( vec[ 0 ], vec[ 1 ], vec[ 2 ] );
		numverts ++;

	}

	// Allocate extra room for the wrap vertex (numverts+1) * 3
	const arr = new Float32Array( ( numverts + 1 ) * 3 );
	for ( let i = 0; i < numverts * 3; i ++ ) arr[ i ] = verts[ i ];
	SubdividePolygon( numverts, arr );

}

/*
=============
EmitWaterPolys

Does a water warp on the pre-fragmented glpoly_t chain.
For Three.js, builds geometry with warped UVs.
=============
*/
// NOTE: Dead code — the cached version EmitWaterPolysQuake in gl_rsurf.js is used instead.
function EmitWaterPolys( fa, realtime ) {

	const positions = [];
	const uvs = [];
	const indices = [];
	let vertexCount = 0;

	for ( let p = fa.polys; p; p = p.next ) {

		const startVert = vertexCount;

		for ( let i = 0; i < p.numverts; i ++ ) {

			const v = p.verts[ i ];
			const os = v[ 3 ];
			const ot = v[ 4 ];

			let s = os + turbsin[ ( ( ot * 0.125 + realtime ) * TURBSCALE | 0 ) & 255 ];
			s *= ( 1.0 / 64 );

			let t = ot + turbsin[ ( ( os * 0.125 + realtime ) * TURBSCALE | 0 ) & 255 ];
			t *= ( 1.0 / 64 );

			// Quake -> Three.js coordinate conversion
			positions.push( v[ 0 ], v[ 2 ], - v[ 1 ] );
			uvs.push( s, t );
			vertexCount ++;

		}

		// Fan triangulation
		for ( let i = 2; i < p.numverts; i ++ ) {

			indices.push( startVert, startVert + i - 1, startVert + i );

		}

	}

	if ( positions.length === 0 )
		return null;

	const geometry = new THREE.BufferGeometry();
	geometry.setAttribute( 'position', new THREE.Float32BufferAttribute( positions, 3 ) );
	geometry.setAttribute( 'uv', new THREE.Float32BufferAttribute( uvs, 2 ) );
	geometry.setIndex( indices );
	geometry.computeVertexNormals();

	return geometry;

}

/*
=============
EmitSkyPolys

For Three.js, builds sky geometry with computed UVs.
=============
*/
// NOTE: Dead code — the cached version EmitSkyPolysQuake in gl_rsurf.js is used instead.
function EmitSkyPolys( fa, realtime ) {

	const positions = [];
	const uvs = [];
	const indices = [];
	let vertexCount = 0;
	const dir = new Float32Array( 3 );

	for ( let p = fa.polys; p; p = p.next ) {

		const startVert = vertexCount;

		for ( let i = 0; i < p.numverts; i ++ ) {

			const v = p.verts[ i ];

			VectorSubtract( v, r_origin, dir );
			dir[ 2 ] *= 3; // flatten the sphere

			let length = dir[ 0 ] * dir[ 0 ] + dir[ 1 ] * dir[ 1 ] + dir[ 2 ] * dir[ 2 ];
			length = Math.sqrt( length );
			length = 6 * 63 / length;

			dir[ 0 ] *= length;
			dir[ 1 ] *= length;

			const s = ( speedscale + dir[ 0 ] ) * ( 1.0 / 128 );
			const t = ( speedscale + dir[ 1 ] ) * ( 1.0 / 128 );

			// Quake -> Three.js coordinate conversion
			positions.push( v[ 0 ], v[ 2 ], - v[ 1 ] );
			uvs.push( s, t );
			vertexCount ++;

		}

		// Fan triangulation
		for ( let i = 2; i < p.numverts; i ++ ) {

			indices.push( startVert, startVert + i - 1, startVert + i );

		}

	}

	if ( positions.length === 0 )
		return null;

	const geometry = new THREE.BufferGeometry();
	geometry.setAttribute( 'position', new THREE.Float32BufferAttribute( positions, 3 ) );
	geometry.setAttribute( 'uv', new THREE.Float32BufferAttribute( uvs, 2 ) );
	geometry.setIndex( indices );
	geometry.computeVertexNormals();

	return geometry;

}

/*
===============
EmitBothSkyLayers

Does a sky warp on the pre-fragmented glpoly_t chain
This will be called for brushmodels, the world
will have them chained together.
===============
*/
// NOTE: Dead code — R_DrawSkyChain in gl_rsurf.js handles sky rendering.
function EmitBothSkyLayers( fa, realtime ) {

	GL_DisableMultitexture();

	GL_Bind( solidskytexture );
	speedscale = realtime * 8;
	speedscale -= ( speedscale | 0 ) & ~127;

	const solidGeo = EmitSkyPolys( fa, realtime );

	GL_Bind( alphaskytexture );
	speedscale = realtime * 16;
	speedscale -= ( speedscale | 0 ) & ~127;

	const alphaGeo = EmitSkyPolys( fa, realtime );

	return { solidGeometry: solidGeo, alphaGeometry: alphaGeo };

}

/*
=================
R_DrawSkyChain
=================
*/
// NOTE: Dead code — R_DrawSkyChain in gl_rsurf.js is used instead.
function R_DrawSkyChain( s, realtime ) {

	GL_DisableMultitexture();

	// used when gl_texsort is on
	GL_Bind( solidskytexture );
	speedscale = realtime * 8;
	speedscale -= ( speedscale | 0 ) & ~127;

	const solidGeometries = [];
	for ( let fa = s; fa; fa = fa.texturechain ) {

		const geo = EmitSkyPolys( fa, realtime );
		if ( geo ) solidGeometries.push( geo );

	}

	GL_Bind( alphaskytexture );
	speedscale = realtime * 16;
	speedscale -= ( speedscale | 0 ) & ~127;

	const alphaGeometries = [];
	for ( let fa = s; fa; fa = fa.texturechain ) {

		const geo = EmitSkyPolys( fa, realtime );
		if ( geo ) alphaGeometries.push( geo );

	}

	return { solidGeometries, alphaGeometries };

}

/*
=============
R_InitSky

A sky texture is 256*128, with the right side being a masked overlay.
For Three.js, creates two textures (solid sky and alpha sky) from the
sky texture data.
==============
*/
export function R_InitSky( mt, d_8to24table ) {

	const src = mt.data;
	const srcOffset = mt.offsets[ 0 ];

	// make an average value for the back to avoid
	// a fringe on the top level
	const trans = new Uint32Array( 128 * 128 );
	let r = 0, g = 0, b = 0;

	for ( let i = 0; i < 128; i ++ ) {

		for ( let j = 0; j < 128; j ++ ) {

			const p = src[ srcOffset + i * 256 + j + 128 ];
			const rgba = d_8to24table[ p ];
			trans[ ( i * 128 ) + j ] = rgba;
			r += ( rgba ) & 0xff;
			g += ( rgba >> 8 ) & 0xff;
			b += ( rgba >> 16 ) & 0xff;

		}

	}

	const transpix = ( ( r / ( 128 * 128 ) ) | 0 )
		| ( ( ( g / ( 128 * 128 ) ) | 0 ) << 8 )
		| ( ( ( b / ( 128 * 128 ) ) | 0 ) << 16 )
		| 0; // alpha = 0

	// Create solid sky texture data (RGBA)
	const solidData = new Uint8Array( 128 * 128 * 4 );
	for ( let i = 0; i < 128 * 128; i ++ ) {

		const rgba = trans[ i ];
		solidData[ i * 4 ] = rgba & 0xff;
		solidData[ i * 4 + 1 ] = ( rgba >> 8 ) & 0xff;
		solidData[ i * 4 + 2 ] = ( rgba >> 16 ) & 0xff;
		solidData[ i * 4 + 3 ] = 255;

	}

	const solidTexture = new THREE.DataTexture( solidData, 128, 128, THREE.RGBAFormat );
	solidTexture.magFilter = THREE.LinearFilter;
	solidTexture.minFilter = THREE.LinearFilter;
	solidTexture.wrapS = THREE.RepeatWrapping;
	solidTexture.wrapT = THREE.RepeatWrapping;
	solidTexture.colorSpace = THREE.SRGBColorSpace;
	solidTexture.needsUpdate = true;

	// Build alpha sky layer
	for ( let i = 0; i < 128; i ++ ) {

		for ( let j = 0; j < 128; j ++ ) {

			const p = src[ srcOffset + i * 256 + j ];
			if ( p === 0 )
				trans[ ( i * 128 ) + j ] = transpix;
			else
				trans[ ( i * 128 ) + j ] = d_8to24table[ p ];

		}

	}

	const alphaData = new Uint8Array( 128 * 128 * 4 );
	for ( let i = 0; i < 128 * 128; i ++ ) {

		const rgba = trans[ i ];
		alphaData[ i * 4 ] = rgba & 0xff;
		alphaData[ i * 4 + 1 ] = ( rgba >> 8 ) & 0xff;
		alphaData[ i * 4 + 2 ] = ( rgba >> 16 ) & 0xff;
		alphaData[ i * 4 + 3 ] = ( rgba >> 24 ) & 0xff;

	}

	const alphaTexture = new THREE.DataTexture( alphaData, 128, 128, THREE.RGBAFormat );
	alphaTexture.magFilter = THREE.LinearFilter;
	alphaTexture.minFilter = THREE.LinearFilter;
	alphaTexture.wrapS = THREE.RepeatWrapping;
	alphaTexture.wrapT = THREE.RepeatWrapping;
	alphaTexture.colorSpace = THREE.SRGBColorSpace;
	alphaTexture.needsUpdate = true;

	return { solidTexture, alphaTexture };

}
