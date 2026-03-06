// Debug overlay — renders entity labels in 3D space using CSS3DRenderer

import * as THREE from 'three';
import { CSS3DRenderer, CSS3DObject } from 'three/addons/renderers/CSS3DRenderer.js';
import { Cmd_AddCommand, Cmd_Argc, Cmd_Argv } from './cmd.js';
import { Con_Printf } from './common.js';
import { cl, cl_entities } from './client.js';
import { mod_brush } from './gl_rmain.js';
import { sv } from './server.js';
import { PR_GetString } from './progs.js';
import { camera } from './gl_rmain.js';
import { renderer } from './vid.js';

//============================================================================
// State
//============================================================================

let debugEnabled = false;
let css3dRenderer = null;
let css3dScene = null;

// Label pool — reuse CSS3DObject instances across frames
const labelPool = [];
let activeCount = 0;

// Fixed scale: each CSS pixel = LABEL_SCALE world units.
// At 1.0, a 12px font = 12 world units tall (~1/5 player height).
// Perspective handles depth scaling naturally.
const LABEL_SCALE = 0.5;

// Color categories for entity types
const COLOR_DOOR = 'rgb(200, 160, 40)'; // gold
const COLOR_BUTTON = 'rgb(220, 120, 20)'; // orange
const COLOR_PLAT = 'rgb(60, 140, 200)'; // blue
const COLOR_MONSTER = 'rgb(200, 50, 50)'; // red
const COLOR_ITEM = 'rgb(50, 180, 50)'; // green
const COLOR_LIGHT = 'rgb(200, 200, 80)'; // yellow
const COLOR_DEFAULT = 'rgb(180, 180, 180)'; // light gray

function getColorForClass( classname ) {

	if ( classname.indexOf( 'door' ) >= 0 ) return COLOR_DOOR;
	if ( classname.indexOf( 'button' ) >= 0 ) return COLOR_BUTTON;
	if ( classname.indexOf( 'plat' ) >= 0 ) return COLOR_PLAT;
	if ( classname.indexOf( 'train' ) >= 0 ) return COLOR_PLAT;
	if ( classname.indexOf( 'monster' ) >= 0 ) return COLOR_MONSTER;
	if ( classname.indexOf( 'item_' ) >= 0 ) return COLOR_ITEM;
	if ( classname.indexOf( 'weapon_' ) >= 0 ) return COLOR_ITEM;
	if ( classname.indexOf( 'item_artifact' ) >= 0 ) return COLOR_ITEM;
	if ( classname.indexOf( 'light' ) >= 0 ) return COLOR_LIGHT;
	return COLOR_DEFAULT;

}

//============================================================================
// Debug_Init
//============================================================================

export function Debug_Init() {

	Cmd_AddCommand( 'debug', Debug_f );

}

//============================================================================
// Debug_f — console command handler
//============================================================================

function Debug_f() {

	if ( Cmd_Argc() >= 2 ) {

		const val = Cmd_Argv( 1 );
		debugEnabled = val !== '0';

	} else {

		debugEnabled = ! debugEnabled;

	}

	Con_Printf( 'Debug overlay: ' + ( debugEnabled ? 'ON' : 'OFF' ) + '\n' );

	// Hide all labels when turning off
	if ( debugEnabled === false ) {

		for ( let i = 0; i < activeCount; i ++ ) {

			labelPool[ i ].visible = false;

		}

		if ( css3dRenderer !== null ) {

			css3dRenderer.domElement.style.display = 'none';

		}

	} else if ( css3dRenderer !== null ) {

		css3dRenderer.domElement.style.display = '';

	}

}

//============================================================================
// ensureRenderer — lazily create the CSS3DRenderer
//============================================================================

function ensureRenderer() {

	if ( css3dRenderer !== null ) return;
	if ( renderer === null ) return;

	css3dScene = new THREE.Scene();

	css3dRenderer = new CSS3DRenderer();
	css3dRenderer.setSize( window.innerWidth, window.innerHeight );

	const dom = css3dRenderer.domElement;
	dom.style.position = 'absolute';
	dom.style.top = '0';
	dom.style.left = '0';
	dom.style.pointerEvents = 'none';

	document.body.appendChild( dom );

	window.addEventListener( 'resize', function () {

		if ( css3dRenderer !== null ) {

			css3dRenderer.setSize( window.innerWidth, window.innerHeight );

		}

	} );

}

//============================================================================
// getLabel — get or create a pooled label at the given index
//============================================================================

function getLabel( index ) {

	if ( index < labelPool.length ) {

		return labelPool[ index ];

	}

	// Create a new CSS3DObject with a div element
	const div = document.createElement( 'div' );
	div.style.fontFamily = 'sans-serif';
	div.style.fontSize = '12px';
	div.style.color = 'rgb(180, 180, 180)';
	div.style.background = 'transparent';
	div.style.padding = '2px 4px';
	div.style.whiteSpace = 'nowrap';
	div.style.pointerEvents = 'none';
	div.style.borderRadius = '2px';
	div.style.border = '1px solid rgb(180, 180, 180)';

	const obj = new CSS3DObject( div );
	css3dScene.add( obj );
	labelPool.push( obj );

	return obj;

}

//============================================================================
// Debug_UpdateOverlay — called per frame from R_RenderScene
//============================================================================

export function Debug_UpdateOverlay() {

	if ( debugEnabled === false ) return;
	if ( camera === null ) return;

	ensureRenderer();
	if ( css3dRenderer === null ) return;

	let count = 0;

	// Iterate all client entities (not just visedicts, so we include doors/buttons/plats)
	if ( cl_entities === null || sv === null || sv.edicts === null ) {

		// No entities loaded yet
		for ( let i = 0; i < activeCount; i ++ ) labelPool[ i ].visible = false;
		activeCount = 0;
		return;

	}

	const numEdicts = sv.num_edicts;

	for ( let i = 1; i < numEdicts; i ++ ) {

		const ent = cl_entities[ i ];
		if ( ent === null || ent === undefined ) continue;
		if ( ent.model === null || ent.model === undefined ) continue;

		// Skip the world entity
		if ( i === 0 ) continue;

		// Get classname from server edict
		const sved = sv.edicts[ i ];
		if ( sved === null || sved === undefined || sved.free === true ) continue;
		if ( sved.v === null || sved.v === undefined ) continue;

		const classname = PR_GetString( sved.v.classname );
		const modelName = ent.model.name || '';

		// Skip entities without useful info
		if ( classname === '' && modelName === '' ) continue;

		// Compute label position
		let px = ent.origin[ 0 ];
		let py = ent.origin[ 1 ];
		let pz = ent.origin[ 2 ];

		// Brush entities: origin is often [0,0,0], use model bounds center instead
		if ( ent.model.type === mod_brush && ent.model.mins !== null && ent.model.mins !== undefined ) {

			px += ( ent.model.mins[ 0 ] + ent.model.maxs[ 0 ] ) * 0.5;
			py += ( ent.model.mins[ 1 ] + ent.model.maxs[ 1 ] ) * 0.5;
			pz += ( ent.model.mins[ 2 ] + ent.model.maxs[ 2 ] ) * 0.5;

		}

		const label = getLabel( count );
		count ++;

		// Position at entity center
		label.position.set( px, py, pz );
		label.scale.set( LABEL_SCALE, LABEL_SCALE, LABEL_SCALE );

		// Billboard: face the camera by copying its quaternion
		label.quaternion.copy( camera.quaternion );

		// Build label text
		let text;
		if ( classname !== '' ) {

			if ( modelName.charAt( 0 ) === '*' ) {

				text = '#' + i + ' ' + classname + ' ' + modelName;

			} else {

				text = '#' + i + ' ' + classname;

			}

		} else {

			text = '#' + i + ' ' + modelName;

		}

		// Update div text and color only when changed (avoid DOM thrashing)
		const div = label.element;
		if ( div.textContent !== text ) {

			div.textContent = text;

		}

		const color = getColorForClass( classname );
		if ( label._debugColor !== color ) {

			div.style.color = color;
			div.style.borderColor = color;
			label._debugColor = color;

		}

		label.visible = true;

	}

	// Hide unused labels from the pool
	for ( let i = count; i < activeCount; i ++ ) {

		labelPool[ i ].visible = false;

	}

	activeCount = count;

	// Render the CSS3D scene with the same camera
	css3dRenderer.render( css3dScene, camera );

}

//============================================================================
// Debug_ClearLabels — called on map change to reset all labels
//============================================================================

export function Debug_ClearLabels() {

	for ( let i = 0; i < labelPool.length; i ++ ) {

		labelPool[ i ].visible = false;

	}

	activeCount = 0;

}
