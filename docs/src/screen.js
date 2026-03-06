// Ported from: WinQuake/screen.c, WinQuake/screen.h -- screen management (software renderer definitions)
// Note: The GL path is in gl_screen.js. This provides shared screen state and cvars.

import { Cvar_RegisterVariable } from './cvar.js';
import { Cmd_AddCommand } from './cmd.js';
import { Con_Printf } from './console.js';
import { Draw_GetVirtualWidth, Draw_GetVirtualHeight } from './gl_draw.js';
import { renderer } from './vid.js';

/*
==============================================================================

			SCREEN CVARS

==============================================================================
*/

export const scr_fov = { name: 'fov', string: '90', value: 90 };
export const scr_viewsize = { name: 'viewsize', string: '100', value: 100 };
export const scr_conspeed = { name: 'scr_conspeed', string: '300', value: 300 };
export const scr_showram = { name: 'showram', string: '1', value: 1 };
export const scr_showturtle = { name: 'showturtle', string: '0', value: 0 };
export const scr_showpause = { name: 'showpause', string: '1', value: 1 };
export const scr_centertime = { name: 'scr_centertime', string: '2', value: 2 };
export const scr_printspeed = { name: 'scr_printspeed', string: '8', value: 8 };

/*
==============================================================================

			SCREEN STATE

==============================================================================
*/

export let scr_initialized = false;
export let scr_disabled_for_loading = false;
export let scr_drawloading = false;

export let scr_con_current = 0;
export let scr_conlines = 0; // lines of console to display
export let scr_fullupdate = 0;

let scr_centerstring = '';
export let scr_centertime_start = 0; // for slow center printing
export let scr_centertime_off = 0;
let scr_center_lines = 0;
let scr_erase_lines = 0;
let scr_erase_center = 0;

let scr_copytop = 0;

// vrect_t for refdef calculation
export const scr_vrect = {
	x: 0, y: 0, width: 0, height: 0,
};

let scr_ram = null; // ram pic
let scr_net = null; // net pic
let scr_turtle = null; // turtle pic

// FPS counter
let lastfpstime = 0;
let fpscount = 0;
export let scr_fps = 0;

// External references
let _realVid = { width: 640, height: 480 };
const _vid = {
	get width() { return Draw_GetVirtualWidth(); },
	get height() { return Draw_GetVirtualHeight(); }
};
let _cls = { state: 0, signon: 0 };
let _cl = { paused: false, time: 0, intermission: 0 };
let _realtime = 0;
let _Draw_Pic = null;
let _Draw_CachePic = null;
let _Draw_Character = null;
let _Draw_String = null;
let _Draw_FadeScreen = null;
let _Draw_ConsoleBackground = null;

export function SCR_SetExternals( externals ) {

	if ( externals.vid ) _realVid = externals.vid;
	if ( externals.cls ) _cls = externals.cls;
	if ( externals.cl ) _cl = externals.cl;
	if ( externals.Draw_Pic ) _Draw_Pic = externals.Draw_Pic;
	if ( externals.Draw_CachePic ) _Draw_CachePic = externals.Draw_CachePic;
	if ( externals.Draw_Character ) _Draw_Character = externals.Draw_Character;
	if ( externals.Draw_String ) _Draw_String = externals.Draw_String;
	if ( externals.Draw_FadeScreen ) _Draw_FadeScreen = externals.Draw_FadeScreen;
	if ( externals.Draw_ConsoleBackground ) _Draw_ConsoleBackground = externals.Draw_ConsoleBackground;

}

/*
===============
SCR_CenterPrint

Called for important messages that should stay in the center of the screen
for a few moments
===============
*/
export function SCR_CenterPrint( str ) {

	scr_centerstring = str;
	scr_centertime_off = scr_centertime.value;
	scr_centertime_start = _cl.time;

	// count the number of lines for centering
	scr_center_lines = 1;
	for ( let i = 0; i < str.length; i ++ ) {

		if ( str[ i ] === '\n' )
			scr_center_lines ++;

	}

}

/*
==============
SCR_DrawCenterString
==============
*/
export function SCR_DrawCenterString() {

	if ( ! _Draw_Character ) return;

	scr_erase_center ++;

	if ( scr_center_lines <= 4 )
		var start = _vid.height * 0.35;
	else
		var start = 48;

	const lines = scr_centerstring.split( '\n' );

	for ( let i = 0; i < lines.length; i ++ ) {

		const l = lines[ i ].length;
		const x = ( _vid.width - l * 8 ) / 2;
		const y = start + i * 8;

		for ( let j = 0; j < l; j ++ ) {

			_Draw_Character( x + j * 8, y, lines[ i ].charCodeAt( j ) );

		}

	}

}

/*
==============
SCR_DrawNet
==============
*/
export function SCR_DrawNet() {

	// If network connection is lagging, draw the net icon
	// Stub for browser

}

/*
==============
SCR_DrawFPS
==============
*/
export function SCR_DrawFPS() {

	if ( ! _Draw_Character ) return;

	fpscount ++;
	if ( _realtime - lastfpstime >= 1.0 ) {

		scr_fps = fpscount;
		fpscount = 0;
		lastfpstime = _realtime;

	}

	const str = scr_fps + ' fps';
	const x = _vid.width - str.length * 8 - 8;

	for ( let i = 0; i < str.length; i ++ )
		_Draw_Character( x + i * 8, 0, str.charCodeAt( i ) );

}

/*
==============
SCR_DrawTurtle
==============
*/
export function SCR_DrawTurtle() {

	// Draw turtle icon when frame rate is low
	// Stub for browser

}

/*
==============
SCR_DrawPause
==============
*/
export function SCR_DrawPause() {

	if ( ! scr_showpause.value )
		return;

	if ( ! _cl.paused )
		return;

	if ( ! _Draw_CachePic ) return;

	const pic = _Draw_CachePic( 'gfx/pause.lmp' );
	if ( pic ) {

		if ( _Draw_Pic )
			_Draw_Pic( ( _vid.width - ( pic.width || 0 ) ) / 2,
				( _vid.height - 48 - ( pic.height || 0 ) ) / 2, pic );

	}

}

/*
==================
SCR_CalcRefdef

Must be called whenever vid changes
Internal use.
==================
*/
export function SCR_CalcRefdef() {

	let size = scr_viewsize.value;
	if ( size < 30 ) size = 30;
	if ( size > 120 ) size = 120;

	// bound viewsize
	if ( size >= 120 ) {

		// full screen - no sbar
		scr_vrect.width = _vid.width;
		scr_vrect.height = _vid.height;
		scr_vrect.x = 0;
		scr_vrect.y = 0;

	} else {

		scr_vrect.width = Math.floor( _vid.width * size / 100 );
		scr_vrect.height = Math.floor( _vid.height * size / 100 );

		if ( scr_vrect.width < 96 ) scr_vrect.width = 96;

		scr_vrect.x = Math.floor( ( _vid.width - scr_vrect.width ) / 2 );
		scr_vrect.y = Math.floor( ( _vid.height - scr_vrect.height ) / 2 );

	}

}

/*
==================
SCR_Init
==================
*/
export function SCR_Init() {

	Cvar_RegisterVariable( scr_fov );
	Cvar_RegisterVariable( scr_viewsize );
	Cvar_RegisterVariable( scr_conspeed );
	Cvar_RegisterVariable( scr_showram );
	Cvar_RegisterVariable( scr_showturtle );
	Cvar_RegisterVariable( scr_showpause );
	Cvar_RegisterVariable( scr_centertime );
	Cvar_RegisterVariable( scr_printspeed );

	Cmd_AddCommand( 'screenshot', SCR_ScreenShot_f );
	Cmd_AddCommand( 'sizeup', SCR_SizeUp_f );
	Cmd_AddCommand( 'sizedown', SCR_SizeDown_f );

	scr_initialized = true;

}

/*
==================
SCR_SizeUp_f

Keybinding command
==================
*/
function SCR_SizeUp_f() {

	scr_viewsize.value += 10;
	if ( scr_viewsize.value > 120 )
		scr_viewsize.value = 120;

	SCR_CalcRefdef();

}

/*
==================
SCR_SizeDown_f

Keybinding command
==================
*/
function SCR_SizeDown_f() {

	scr_viewsize.value -= 10;
	if ( scr_viewsize.value < 30 )
		scr_viewsize.value = 30;

	SCR_CalcRefdef();

}

/*
==================
SCR_ScreenShot_f
==================
*/
function SCR_ScreenShot_f() {

	if ( renderer == null ) {

		Con_Printf( 'Screenshot: renderer not initialized\n' );
		return;

	}

	const canvas = renderer.domElement;
	canvas.toBlob( function ( blob ) {

		if ( blob == null ) {

			Con_Printf( 'Screenshot: failed to create image\n' );
			return;

		}

		const url = URL.createObjectURL( blob );
		const a = document.createElement( 'a' );
		a.href = url;
		a.download = 'quake' + String( Date.now() ) + '.png';
		a.click();
		URL.revokeObjectURL( url );
		Con_Printf( 'Wrote ' + a.download + '\n' );

	}, 'image/png' );

}

/*
==================
SCR_UpdateScreen

This is called every frame, and can also be called explicitly to flush
text to the screen.

WARNING: be very careful calling this from elsewhere, because the refresh
needs almost the entire 256k of stack space!
==================
*/
export function SCR_UpdateScreen() {

	// This is the software renderer path -- see gl_screen.js for GL path
	// In Three.js port, gl_screen.js SCR_UpdateScreen is used instead

}
