// Ported from: WinQuake/gl_mesh.c -- triangle model functions (alias models)

import * as THREE from 'three';
import { Con_Printf, Con_DPrintf } from './common.js';
import { cl } from './client.js';
import { R_GetPlayerSkinTexture } from './gl_rmisc.js';
import { gl_nocolors } from './glquake.js';
import { r_avertexnormals } from './anorm_dots.js';

/*
=================================================================

ALIAS MODEL DISPLAY LIST GENERATION

=================================================================
*/

let aliasmodel = null; // model_t *
let paliashdr = null; // aliashdr_t *

const used = new Uint8Array( 8192 );

// the command list holds counts and s/t values that are valid for
// every frame
const commands = new Int32Array( 8192 );
let numcommands = 0;

// all frames will have their vertexes rearranged and expanded
// so they are in the order expected by the command list
const vertexorder = new Int32Array( 8192 );
let numorder = 0;

let allverts = 0;
let alltris = 0;

const stripverts = new Int32Array( 128 );
const striptris = new Int32Array( 128 );
let stripcount = 0;

// References to model data set during BuildTris
let triangles = null; // mtriangle_t[]
let stverts = null; // stvert_t[]
let pheader = null; // aliashdr_t (same as paliashdr)
let poseverts = null; // trivertx_t[][]

// r_avertexnormals is imported from anorm_dots.js to avoid circular dependency

/*
================
StripLength
================
*/
function StripLength( starttri, startv ) {

	used[ starttri ] = 2;

	const last = triangles[ starttri ];

	stripverts[ 0 ] = last.vertindex[ ( startv ) % 3 ];
	stripverts[ 1 ] = last.vertindex[ ( startv + 1 ) % 3 ];
	stripverts[ 2 ] = last.vertindex[ ( startv + 2 ) % 3 ];

	striptris[ 0 ] = starttri;
	stripcount = 1;

	let m1 = last.vertindex[ ( startv + 2 ) % 3 ];
	let m2 = last.vertindex[ ( startv + 1 ) % 3 ];

	// look for a matching triangle
	let found = true;
	while ( found ) {

		found = false;
		for ( let j = starttri + 1; j < pheader.numtris; j ++ ) {

			const check = triangles[ j ];

			if ( check.facesfront !== last.facesfront )
				continue;
			for ( let k = 0; k < 3; k ++ ) {

				if ( check.vertindex[ k ] !== m1 )
					continue;
				if ( check.vertindex[ ( k + 1 ) % 3 ] !== m2 )
					continue;

				// this is the next part of the fan

				// if we can't use this triangle, this tristrip is done
				if ( used[ j ] )
					break;

				// the new edge
				if ( stripcount & 1 )
					m2 = check.vertindex[ ( k + 2 ) % 3 ];
				else
					m1 = check.vertindex[ ( k + 2 ) % 3 ];

				stripverts[ stripcount + 2 ] = check.vertindex[ ( k + 2 ) % 3 ];
				striptris[ stripcount ] = j;
				stripcount ++;

				used[ j ] = 2;
				found = true;
				break;

			}

			if ( found ) break;

		}

	}

	// clear the temp used flags
	for ( let j = starttri + 1; j < pheader.numtris; j ++ )
		if ( used[ j ] === 2 )
			used[ j ] = 0;

	return stripcount;

}

/*
===========
FanLength
===========
*/
function FanLength( starttri, startv ) {

	used[ starttri ] = 2;

	const last = triangles[ starttri ];

	stripverts[ 0 ] = last.vertindex[ ( startv ) % 3 ];
	stripverts[ 1 ] = last.vertindex[ ( startv + 1 ) % 3 ];
	stripverts[ 2 ] = last.vertindex[ ( startv + 2 ) % 3 ];

	striptris[ 0 ] = starttri;
	stripcount = 1;

	const m1 = last.vertindex[ ( startv + 0 ) % 3 ];
	let m2 = last.vertindex[ ( startv + 2 ) % 3 ];

	// look for a matching triangle
	let found = true;
	while ( found ) {

		found = false;
		for ( let j = starttri + 1; j < pheader.numtris; j ++ ) {

			const check = triangles[ j ];

			if ( check.facesfront !== last.facesfront )
				continue;
			for ( let k = 0; k < 3; k ++ ) {

				if ( check.vertindex[ k ] !== m1 )
					continue;
				if ( check.vertindex[ ( k + 1 ) % 3 ] !== m2 )
					continue;

				// this is the next part of the fan

				// if we can't use this triangle, this tristrip is done
				if ( used[ j ] )
					break;

				// the new edge
				m2 = check.vertindex[ ( k + 2 ) % 3 ];

				stripverts[ stripcount + 2 ] = m2;
				striptris[ stripcount ] = j;
				stripcount ++;

				used[ j ] = 2;
				found = true;
				break;

			}

			if ( found ) break;

		}

	}

	// clear the temp used flags
	for ( let j = starttri + 1; j < pheader.numtris; j ++ )
		if ( used[ j ] === 2 )
			used[ j ] = 0;

	return stripcount;

}

/*
================
BuildTris

Generate a list of trifans or strips
for the model, which holds for all frames
================
*/
export function BuildTris() {

	const bestverts = new Int32Array( 1024 );
	const besttris = new Int32Array( 1024 );

	//
	// build tristrips
	//
	numorder = 0;
	numcommands = 0;
	used.fill( 0 );

	for ( let i = 0; i < pheader.numtris; i ++ ) {

		// pick an unused triangle and start the trifan
		if ( used[ i ] )
			continue;

		let bestlen = 0;
		let besttype = 0;

		for ( let type = 0; type < 2; type ++ ) {

			for ( let startv = 0; startv < 3; startv ++ ) {

				let len;
				if ( type === 1 )
					len = StripLength( i, startv );
				else
					len = FanLength( i, startv );
				if ( len > bestlen ) {

					besttype = type;
					bestlen = len;
					for ( let j = 0; j < bestlen + 2; j ++ )
						bestverts[ j ] = stripverts[ j ];
					for ( let j = 0; j < bestlen; j ++ )
						besttris[ j ] = striptris[ j ];

				}

			}

		}

		// mark the tris on the best strip as used
		for ( let j = 0; j < bestlen; j ++ )
			used[ besttris[ j ] ] = 1;

		if ( besttype === 1 )
			commands[ numcommands ++ ] = ( bestlen + 2 );
		else
			commands[ numcommands ++ ] = - ( bestlen + 2 );

		for ( let j = 0; j < bestlen + 2; j ++ ) {

			// emit a vertex into the reorder buffer
			const k = bestverts[ j ];
			vertexorder[ numorder ++ ] = k;

			// emit s/t coords into the commands stream
			let s = stverts[ k ].s;
			let t = stverts[ k ].t;
			if ( ! triangles[ besttris[ 0 ] ].facesfront && stverts[ k ].onseam )
				s += pheader.skinwidth / 2; // on back side
			s = ( s + 0.5 ) / pheader.skinwidth;
			t = ( t + 0.5 ) / pheader.skinheight;

			// Store float as int bits (mimicking *(float *)&commands)
			const floatBuf = new Float32Array( 1 );
			floatBuf[ 0 ] = s;
			const intView = new Int32Array( floatBuf.buffer );
			commands[ numcommands ++ ] = intView[ 0 ];
			floatBuf[ 0 ] = t;
			commands[ numcommands ++ ] = intView[ 0 ];

		}

	}

	commands[ numcommands ++ ] = 0; // end of list marker

	Con_DPrintf( '%d tri %d vert %d cmd\n', pheader.numtris, numorder, numcommands );

	allverts += numorder;
	alltris += pheader.numtris;

}

/*
================
GL_MakeAliasModelDisplayLists

In Three.js, we build a BufferGeometry from the alias model vertex/triangle data.
The original code generates GL command lists (triangle strips/fans);
we instead build indexed triangle geometry.
================
*/
export function GL_MakeAliasModelDisplayLists( m, hdr ) {

	aliasmodel = m;
	paliashdr = hdr;
	pheader = hdr;
	triangles = hdr.triangles;
	stverts = hdr.stverts;
	poseverts = hdr.poseverts;

	// Build command lists from scratch
	Con_Printf( 'meshing %s...\n', m.name );
	BuildTris();

	// save the data out
	paliashdr.poseverts_count = numorder;

	// Copy commands
	paliashdr.commands = new Int32Array( numcommands );
	paliashdr.commands.set( commands.subarray( 0, numcommands ) );

	// Copy reordered pose vertices
	paliashdr.posedata = [];
	for ( let i = 0; i < paliashdr.numposes; i ++ ) {

		const frameVerts = [];
		for ( let j = 0; j < numorder; j ++ ) {

			frameVerts.push( poseverts[ i ][ vertexorder[ j ] ] );

		}

		paliashdr.posedata.push( frameVerts );

	}

}

/*
================
GL_DrawAliasFrame

Build a Three.js BufferGeometry from a single pose of an alias model.
Uses the command list to reconstruct triangle strips/fans into indexed triangles.

Caches geometry template (positions, UVs, indices, normals, lightnormalindices)
per (paliashdr, posenum) to avoid recomputation every frame. Vertex colors
are updated in place from a pre-allocated buffer.
================
*/

// Shared buffers for int-to-float bit casting
const _castIntBuf = new Int32Array( 1 );
const _castFloatView = new Float32Array( _castIntBuf.buffer );

export function GL_DrawAliasFrame( paliashdr, posenum ) {

	const verts = paliashdr.posedata[ posenum ];
	if ( ! verts ) return null;

	// Check geometry template cache
	if ( ! paliashdr._geoCache ) paliashdr._geoCache = new Map();

	let cached = paliashdr._geoCache.get( posenum );

	if ( cached == null ) {

		// Build geometry template for this pose (done once, cached)
		const cmds = paliashdr.commands;
		const positions = [];
		const normals = [];
		const uvs = [];
		const indices = [];
		const lightnormalindices = [];

		let cmdIndex = 0;
		let vertexCount = 0;

		while ( true ) {

			let count = cmds[ cmdIndex ++ ];
			if ( count === 0 )
				break;

			const isStrip = count > 0;
			if ( count < 0 )
				count = - count;

			const firstVertex = vertexCount;

			// Read all vertices for this strip/fan
			for ( let i = 0; i < count; i ++ ) {

				// Read s/t from command stream (stored as int bits of float)
				_castIntBuf[ 0 ] = cmds[ cmdIndex ++ ];
				const s = _castFloatView[ 0 ];
				_castIntBuf[ 0 ] = cmds[ cmdIndex ++ ];
				const t = _castFloatView[ 0 ];

				const vert = verts[ vertexCount - firstVertex + firstVertex ];
				if ( vert ) {

					const x = vert.v[ 0 ] * paliashdr.scale[ 0 ] + paliashdr.scale_origin[ 0 ];
					const y = vert.v[ 1 ] * paliashdr.scale[ 1 ] + paliashdr.scale_origin[ 1 ];
					const z = vert.v[ 2 ] * paliashdr.scale[ 2 ] + paliashdr.scale_origin[ 2 ];

					positions.push( x, y, z );
					uvs.push( s, t );
					lightnormalindices.push( vert.lightnormalindex );

					// Look up pre-baked normal from MDL file's normal table
					const normalIndex = vert.lightnormalindex;
					const n = r_avertexnormals[ normalIndex ] || r_avertexnormals[ 0 ];
					normals.push( n[ 0 ], n[ 1 ], n[ 2 ] );

				} else {

					positions.push( 0, 0, 0 );
					uvs.push( s, t );
					lightnormalindices.push( 0 );
					normals.push( 0, 0, 1 ); // Default normal

				}

				vertexCount ++;

			}

			// Generate triangle indices from strip or fan (inverted winding for correct backface culling)
			if ( isStrip ) {

				for ( let i = 2; i < count; i ++ ) {

					if ( i & 1 ) {

						indices.push( firstVertex + i - 1, firstVertex + i, firstVertex + i - 2 );

					} else {

						indices.push( firstVertex + i - 2, firstVertex + i, firstVertex + i - 1 );

					}

				}

			} else {

				for ( let i = 2; i < count; i ++ ) {

					indices.push( firstVertex, firstVertex + i, firstVertex + i - 1 );

				}

			}

		}

		// Build shared BufferAttributes for the template (no color — color is per-entity)
		const posAttr = new THREE.BufferAttribute( new Float32Array( positions ), 3 );
		const normalAttr = new THREE.BufferAttribute( new Float32Array( normals ), 3 );
		const uvAttr = new THREE.BufferAttribute( new Float32Array( uvs ), 2 );

		cached = {
			posAttr,
			normalAttr,
			uvAttr,
			indices,
			lightnormalindices,
			vertexCount
		};
		paliashdr._geoCache.set( posenum, cached );

	}

	return cached;

}

/*
================
GL_ClearAliasCache

Clears all cached alias model geometries. Called on map change.
================
*/
export function GL_ClearAliasCache() {

	// Caches are stored on paliashdr objects which are replaced on map load,
	// so they are garbage collected automatically. This function exists
	// as a hook if explicit cleanup is ever needed.

}

/*
=================
R_SetupAliasFrame

Determine which pose to render for the given entity and alias model header.
=================
*/
function R_SetupAliasFrame( entity, paliashdr ) {

	let posenum = 0;
	if ( entity && entity.frame !== undefined ) {

		let frame = entity.frame;
		if ( frame >= paliashdr.numframes || frame < 0 ) {

			Con_DPrintf( 'R_AliasSetupFrame: no such frame ' + frame + '\n' );
			frame = 0;

		}

		if ( paliashdr.frames && paliashdr.frames[ frame ] ) {

			const frameInfo = paliashdr.frames[ frame ];
			posenum = frameInfo.firstpose;
			const numposes = frameInfo.numposes;

			if ( numposes > 1 ) {

				const interval = frameInfo.interval;
				const time = cl ? cl.time : 0;
				posenum += ( ( time / interval ) | 0 ) % numposes;

			}

		} else {

			posenum = frame;

		}

		if ( posenum >= paliashdr.numposes )
			posenum = 0;

	}

	return posenum;

}

/*
=================
R_GetAliasMaterial

Get or create a cached material for the given alias model skin.
Materials are cached per (paliashdr, skinnum, hasLighting) to avoid
per-frame material creation and shader compilation.
=================
*/
function R_GetAliasMaterial( paliashdr, entity, hasLighting, playerSkinTexture ) {

	// Player skin textures are per-entity, not cached on the model
	if ( playerSkinTexture != null ) {

		// Cache the player material on the entity to avoid per-frame creation
		if ( entity._playerMaterial == null || entity._playerSkinTexture !== playerSkinTexture ) {

			if ( entity._playerMaterial != null ) {

				entity._playerMaterial.dispose();

			}

			entity._playerMaterial = new THREE.MeshBasicMaterial( {
				map: playerSkinTexture,
				vertexColors: hasLighting
			} );
			entity._playerSkinTexture = playerSkinTexture;

		}

		return entity._playerMaterial;

	}

	if ( ! paliashdr._materialCache ) paliashdr._materialCache = new Map();

	const skinnum = entity && entity.skinnum ? entity.skinnum : 0;

	// Animated skins cycle through frames 0-3 every 0.1 seconds
	// Original: anim = (int)(cl.time*10) & 3
	const anim = cl && cl.time ? ( Math.floor( cl.time * 10 ) & 3 ) : 0;

	// Cache key includes animation frame for animated skins
	const cacheKey = skinnum * 8 + anim * 2 + ( hasLighting ? 1 : 0 );

	let material = paliashdr._materialCache.get( cacheKey );
	if ( material ) return material;

	let texture = null;
	if ( paliashdr.gl_texturenum ) {

		const skinGroup = paliashdr.gl_texturenum[ skinnum ] || paliashdr.gl_texturenum[ 0 ];
		if ( skinGroup ) {

			// Select animated frame if skin group is an array
			texture = Array.isArray( skinGroup ) ? ( skinGroup[ anim ] || skinGroup[ 0 ] ) : skinGroup;

		}

	}

	if ( texture ) {

		material = new THREE.MeshBasicMaterial( {
			map: texture,
			vertexColors: hasLighting
		} );

	} else {

		material = new THREE.MeshBasicMaterial( {
			color: 0xcccccc,
			vertexColors: hasLighting
		} );

	}

	paliashdr._materialCache.set( cacheKey, material );
	return material;

}

// Reusable matrix objects for R_DrawAliasModel transform computation
const _aliasMat = new THREE.Matrix4();
const _aliasRZ = new THREE.Matrix4();
const _aliasRY = new THREE.Matrix4();
const _aliasRX = new THREE.Matrix4();
const _DEG2RAD = Math.PI / 180;

/*
=================
R_DrawAliasModel

Builds and returns a Three.js Mesh for the given alias model entity.
Caches geometry per (model, pose), materials per (model, skin),
and reuses mesh objects per entity to minimize per-frame allocations.
=================
*/
export function R_DrawAliasModel( entity, paliashdr, shadedots, shadelight ) {

	if ( ! paliashdr || ! paliashdr.posedata )
		return null;

	const posenum = R_SetupAliasFrame( entity, paliashdr );
	const hasLighting = shadedots && shadelight !== undefined;

	// Get cached template (shared positions/normals/uvs/indices per model+pose)
	const template = GL_DrawAliasFrame( paliashdr, posenum );
	if ( ! template )
		return null;

	// Build or update per-entity geometry (shares template attributes, owns color buffer)
	let geometry = entity ? entity._aliasGeo : null;
	if ( geometry == null ) {

		geometry = new THREE.BufferGeometry();
		// Allocate per-entity color buffer (will be resized if needed)
		entity._aliasColorArray = new Float32Array( template.vertexCount * 3 );
		geometry.setAttribute( 'color', new THREE.BufferAttribute( entity._aliasColorArray, 3 ) );
		if ( entity != null ) entity._aliasGeo = geometry;

	}

	// When pose or model changes, swap to the new template's shared attributes
	if ( entity._aliasPosenum !== posenum || entity._aliasPaliashdr !== paliashdr ) {

		geometry.setAttribute( 'position', template.posAttr );
		geometry.setAttribute( 'normal', template.normalAttr );
		geometry.setAttribute( 'uv', template.uvAttr );
		geometry.setIndex( template.indices );

		// Resize color buffer if vertex count changed between poses
		if ( entity._aliasColorArray.length < template.vertexCount * 3 ) {

			entity._aliasColorArray = new Float32Array( template.vertexCount * 3 );
			geometry.setAttribute( 'color', new THREE.BufferAttribute( entity._aliasColorArray, 3 ) );

		}

		entity._aliasPosenum = posenum;
		entity._aliasPaliashdr = paliashdr;

	}

	// Update per-entity vertex colors from lighting data
	if ( hasLighting ) {

		const colorArr = entity._aliasColorArray;
		const lni = template.lightnormalindices;
		for ( let i = 0; i < template.vertexCount; i ++ ) {

			const l = shadedots[ lni[ i ] ] * shadelight;
			colorArr[ i * 3 ] = l;
			colorArr[ i * 3 + 1 ] = l;
			colorArr[ i * 3 + 2 ] = l;

		}

		geometry.attributes.color.needsUpdate = true;

	}

	// Check if this is a player entity with custom colors
	let playerSkinTexture = null;
	if ( entity != null && entity.colormap != null && gl_nocolors.value === 0 ) {

		// Use stored entity index (equivalent to C pointer arithmetic: i = currententity - cl_entities)
		const entIdx = entity._entityIndex;
		if ( entIdx !== undefined && entIdx >= 1 && cl != null && entIdx <= cl.maxclients ) {

			playerSkinTexture = R_GetPlayerSkinTexture( entIdx - 1 );

		}

	}

	// Get cached material
	const material = R_GetAliasMaterial( paliashdr, entity, hasLighting, playerSkinTexture );

	// Get or create mesh for this entity
	let mesh = entity ? entity._aliasMesh : null;
	if ( mesh == null ) {

		mesh = new THREE.Mesh( geometry, material );
		if ( entity != null ) entity._aliasMesh = mesh;

	} else {

		// Reuse existing mesh, update geometry and material if changed
		if ( mesh.geometry !== geometry ) mesh.geometry = geometry;
		if ( mesh.material !== material ) mesh.material = material;

	}

	// Apply entity transform — R_RotateForEntity equivalent
	if ( entity ) {

		if ( entity.origin ) {

			mesh.position.set(
				entity.origin[ 0 ],
				entity.origin[ 1 ],
				entity.origin[ 2 ]
			);

		}

		if ( entity.angles ) {

			const yaw = entity.angles[ 1 ] * _DEG2RAD;
			const pitch = - entity.angles[ 0 ] * _DEG2RAD;
			const roll = entity.angles[ 2 ] * _DEG2RAD;

			_aliasMat.identity();
			_aliasRZ.makeRotationZ( yaw );
			_aliasRY.makeRotationY( pitch );
			_aliasRX.makeRotationX( roll );
			_aliasMat.multiply( _aliasRZ ).multiply( _aliasRY ).multiply( _aliasRX );
			mesh.setRotationFromMatrix( _aliasMat );

		}

	}

	// Reset render overrides (viewmodel sets these)
	mesh.renderOrder = 0;
	if ( mesh.material.depthTest === false ) {

		// Clone material for weapon so it doesn't affect shared material
		// (Only needed when transitioning away from weapon rendering)
		mesh.material.depthTest = true;

	}

	return mesh;

}

/*
=============
GL_DrawAliasShadow

Projects alias model vertices onto the ground plane to create a shadow.
Ported from WinQuake/gl_rmain.c:347-405
=============
*/

// Shared shadow material (Golden Rule #4 — one for all entities)
const _shadowMaterial = new THREE.MeshBasicMaterial( {
	color: 0x000000,
	transparent: true,
	opacity: 0.5,
	depthWrite: false,
	side: THREE.DoubleSide
} );

// Cached matrix objects for shadow transform (Golden Rule #4)
const _shadowMat = new THREE.Matrix4();
const _shadowRZ = new THREE.Matrix4();
const _shadowRY = new THREE.Matrix4();
const _shadowRX = new THREE.Matrix4();

export function GL_DrawAliasShadow( entity, paliashdr, posenum, lightspot, shadevector ) {

	if ( paliashdr == null || paliashdr.posedata == null ) return null;

	const template = GL_DrawAliasFrame( paliashdr, posenum );
	if ( template == null ) return null;

	const lheight = entity.origin[ 2 ] - lightspot[ 2 ];
	const height = - lheight + 1.0;

	// Get or create shadow geometry for this entity
	let shadowGeo = entity._aliasShadowGeo;
	let shadowPosArray = entity._aliasShadowPosArray;

	if ( shadowGeo == null || entity._aliasShadowVertCount !== template.vertexCount ) {

		shadowPosArray = new Float32Array( template.vertexCount * 3 );
		shadowGeo = new THREE.BufferGeometry();
		shadowGeo.setAttribute( 'position', new THREE.BufferAttribute( shadowPosArray, 3 ) );
		shadowGeo.setIndex( template.indices );
		entity._aliasShadowGeo = shadowGeo;
		entity._aliasShadowPosArray = shadowPosArray;
		entity._aliasShadowVertCount = template.vertexCount;

	}

	// Project vertices onto ground plane (same as C code)
	const srcPos = template.posAttr.array;
	for ( let i = 0; i < template.vertexCount; i ++ ) {

		const px = srcPos[ i * 3 ];
		const py = srcPos[ i * 3 + 1 ];
		const pz = srcPos[ i * 3 + 2 ];

		shadowPosArray[ i * 3 ] = px - shadevector[ 0 ] * ( pz + lheight );
		shadowPosArray[ i * 3 + 1 ] = py - shadevector[ 1 ] * ( pz + lheight );
		shadowPosArray[ i * 3 + 2 ] = height;

	}

	shadowGeo.attributes.position.needsUpdate = true;

	// Get or create shadow mesh
	let shadowMesh = entity._aliasShadowMesh;
	if ( shadowMesh == null ) {

		shadowMesh = new THREE.Mesh( shadowGeo, _shadowMaterial );
		entity._aliasShadowMesh = shadowMesh;

	} else {

		if ( shadowMesh.geometry !== shadowGeo ) shadowMesh.geometry = shadowGeo;

	}

	// Apply same transform as entity (R_RotateForEntity equivalent)
	if ( entity.origin != null ) {

		shadowMesh.position.set(
			entity.origin[ 0 ],
			entity.origin[ 1 ],
			entity.origin[ 2 ]
		);

	}

	if ( entity.angles != null ) {

		const yaw = entity.angles[ 1 ] * _DEG2RAD;
		const pitch = - entity.angles[ 0 ] * _DEG2RAD;
		const roll = entity.angles[ 2 ] * _DEG2RAD;

		_shadowMat.identity();
		_shadowRZ.makeRotationZ( yaw );
		_shadowRY.makeRotationY( pitch );
		_shadowRX.makeRotationX( roll );
		_shadowMat.multiply( _shadowRZ ).multiply( _shadowRY ).multiply( _shadowRX );
		shadowMesh.setRotationFromMatrix( _shadowMat );

	}

	return shadowMesh;

}
