// Ported from: WinQuake/console.c, WinQuake/console.h -- developer console

import { Cmd_AddCommand } from './cmd.js';
import { Cvar_RegisterVariable } from './cvar.js';
import { key_dest, set_key_dest, key_game, key_console, key_message,
	key_lines, edit_line, key_linepos, chat_buffer } from './keys.js';
import { Draw_GetVirtualWidth, Draw_GetVirtualHeight } from './gl_draw.js';

/*
==============================================================================

			CONSOLE CONSTANTS

==============================================================================
*/

const CON_TEXTSIZE = 16384;
const NUM_CON_TIMES = 4;
const MAXPRINTMSG = 4096;
const MAXCMDLINE = 256;

/*
==============================================================================

			CONSOLE STATE

==============================================================================
*/

export let con_linewidth = 0;

const con_cursorspeed = 4;

export let con_forcedup = false; // because no entities to refresh

export let con_totallines = 0; // total lines in console scrollback
export let con_backscroll = 0; // lines up from bottom to display
let con_current = 0; // where next message will be printed
let con_x = 0; // offset in current line for next print
let con_text = null;

const con_notifytime = { name: 'con_notifytime', string: '3', value: 3 }; // seconds

const con_times = new Float32Array( NUM_CON_TIMES ); // realtime time the line was generated

export let con_vislines = 0;

let con_debuglog = false;

export let con_initialized = false;

export let con_notifylines = 0; // scan lines to clear for notify lines

// Cross-reference to other systems (set via Con_SetExternals to avoid circular imports)
let _cls = { state: 0, signon: 0 };
let _realVid = { width: 640, height: 480 };
const _vid = {
	get width() { return Draw_GetVirtualWidth(); },
	get height() { return Draw_GetVirtualHeight(); }
};
let _getRealtime = () => 0;
let _scr_disabled_for_loading = false;
let _developer = { value: 0 };
let _Draw_Character = null;
let _Draw_String = null;
let _Draw_ConsoleBackground = null;
let _SCR_UpdateScreen = null;
let _SCR_EndLoadingPlaque = null;
let _M_Menu_Main_f = null;
let _S_LocalSound = null;

// Static variable for Con_Print
let cr = false;

export function Con_SetExternals( externals ) {

	if ( externals.cls ) _cls = externals.cls;
	if ( externals.vid ) _realVid = externals.vid;
	if ( externals.getRealtime ) _getRealtime = externals.getRealtime;
	if ( externals.developer ) _developer = externals.developer;
	if ( externals.Draw_Character ) _Draw_Character = externals.Draw_Character;
	if ( externals.Draw_String ) _Draw_String = externals.Draw_String;
	if ( externals.Draw_ConsoleBackground ) _Draw_ConsoleBackground = externals.Draw_ConsoleBackground;
	if ( externals.SCR_UpdateScreen ) _SCR_UpdateScreen = externals.SCR_UpdateScreen;
	if ( externals.SCR_EndLoadingPlaque ) _SCR_EndLoadingPlaque = externals.SCR_EndLoadingPlaque;
	if ( externals.M_Menu_Main_f ) _M_Menu_Main_f = externals.M_Menu_Main_f;
	if ( externals.S_LocalSound ) _S_LocalSound = externals.S_LocalSound;
	if ( externals.scr_disabled_for_loading !== undefined ) _scr_disabled_for_loading = externals.scr_disabled_for_loading;

}

// Accessor functions for mutable exports
export function Con_SetBackscroll( val ) { con_backscroll = val; }
export function Con_GetBackscroll() { return con_backscroll; }
export function Con_SetForcedup( val ) { con_forcedup = val; }

/*
================
Con_ToggleConsole_f
================
*/
export function Con_ToggleConsole_f() {

	if ( key_dest === key_console ) {

		if ( _cls.state === 2 ) { // ca_connected

			set_key_dest( key_game );

			key_lines[ edit_line ][ 1 ] = 0; // clear any typing

		} else {

			if ( _M_Menu_Main_f ) _M_Menu_Main_f();

		}

	} else {

		set_key_dest( key_console );

	}

	if ( _SCR_EndLoadingPlaque ) _SCR_EndLoadingPlaque();
	con_times.fill( 0 );

}

/*
================
Con_Clear_f
================
*/
export function Con_Clear_f() {

	if ( con_text ) {

		for ( let i = 0; i < CON_TEXTSIZE; i ++ )
			con_text[ i ] = 32; // ' '

	}

}

/*
================
Con_ClearNotify
================
*/
export function Con_ClearNotify() {

	for ( let i = 0; i < NUM_CON_TIMES; i ++ )
		con_times[ i ] = 0;

}

/*
================
Con_MessageMode_f
================
*/
function Con_MessageMode_f() {

	set_key_dest( key_message );

}

/*
================
Con_MessageMode2_f
================
*/
function Con_MessageMode2_f() {

	set_key_dest( key_message );

}

/*
================
Con_CheckResize

If the line width has changed, reformat the buffer.
================
*/
export function Con_CheckResize() {

	let width = ( _vid.width >> 3 ) - 2;

	if ( width === con_linewidth )
		return;

	if ( width < 1 ) {

		// video hasn't been initialized yet
		width = 38;
		con_linewidth = width;
		con_totallines = Math.floor( CON_TEXTSIZE / con_linewidth );

		if ( con_text ) {

			for ( let i = 0; i < CON_TEXTSIZE; i ++ )
				con_text[ i ] = 32; // ' '

		}

	} else {

		const oldwidth = con_linewidth;
		con_linewidth = width;
		const oldtotallines = con_totallines;
		con_totallines = Math.floor( CON_TEXTSIZE / con_linewidth );
		let numlines = oldtotallines;

		if ( con_totallines < numlines )
			numlines = con_totallines;

		let numchars = oldwidth;

		if ( con_linewidth < numchars )
			numchars = con_linewidth;

		const tbuf = new Array( CON_TEXTSIZE );
		for ( let i = 0; i < CON_TEXTSIZE; i ++ )
			tbuf[ i ] = con_text[ i ];

		for ( let i = 0; i < CON_TEXTSIZE; i ++ )
			con_text[ i ] = 32; // ' '

		for ( let i = 0; i < numlines; i ++ ) {

			for ( let j = 0; j < numchars; j ++ ) {

				con_text[ ( con_totallines - 1 - i ) * con_linewidth + j ] =
						tbuf[ ( ( con_current - i + oldtotallines ) %
							  oldtotallines ) * oldwidth + j ];

			}

		}

		Con_ClearNotify();

	}

	con_backscroll = 0;
	con_current = con_totallines - 1;

}

/*
================
Con_Init
================
*/
export function Con_Init() {

	con_text = new Array( CON_TEXTSIZE );
	for ( let i = 0; i < CON_TEXTSIZE; i ++ )
		con_text[ i ] = 32; // ' '

	con_linewidth = - 1;
	Con_CheckResize();

	Con_Printf( 'Console initialized.\n' );

	//
	// register our commands
	//
	Cvar_RegisterVariable( con_notifytime );

	Cmd_AddCommand( 'toggleconsole', Con_ToggleConsole_f );
	Cmd_AddCommand( 'messagemode', Con_MessageMode_f );
	Cmd_AddCommand( 'messagemode2', Con_MessageMode2_f );
	Cmd_AddCommand( 'clear', Con_Clear_f );
	con_initialized = true;

}

/*
===============
Con_Linefeed
===============
*/
function Con_Linefeed() {

	con_x = 0;
	con_current ++;

	const start = ( con_current % con_totallines ) * con_linewidth;
	for ( let i = 0; i < con_linewidth; i ++ )
		con_text[ start + i ] = 32; // ' '

}

/*
================
Con_Print

Handles cursor positioning, line wrapping, etc
All console printing must go through this in order to be logged to disk
If no console is visible, the notify window will pop up.
================
*/
export function Con_Print( txt ) {

	con_backscroll = 0;

	let pos = 0;
	let mask = 0;

	if ( txt.charCodeAt( 0 ) === 1 ) {

		mask = 128; // go to colored text
		// play talk wav
		if ( _S_LocalSound ) _S_LocalSound( 'misc/talk.wav' );
		pos ++;

	} else if ( txt.charCodeAt( 0 ) === 2 ) {

		mask = 128; // go to colored text
		pos ++;

	}

	while ( pos < txt.length ) {

		const c = txt.charCodeAt( pos );

		// count word length
		let l;
		for ( l = 0; l < con_linewidth; l ++ ) {

			if ( pos + l >= txt.length || txt.charCodeAt( pos + l ) <= 32 )
				break;

		}

		// word wrap
		if ( l !== con_linewidth && ( con_x + l > con_linewidth ) )
			con_x = 0;

		pos ++;

		if ( cr ) {

			con_current --;
			cr = false;

		}

		if ( con_x === 0 ) {

			Con_Linefeed();
			// mark time for transparent overlay
			if ( con_current >= 0 ) {
				const rt = _getRealtime();
				con_times[ con_current % NUM_CON_TIMES ] = rt;
			}

		}

		if ( c === 10 ) { // '\n'

			// Also set timestamp when newline is processed (ensures notify works even with unusual message flow)
			if ( con_current >= 0 ) {
				const rt = _getRealtime();
				if ( rt > 0 ) {
					con_times[ con_current % NUM_CON_TIMES ] = rt;
				}
			}
			con_x = 0;

		} else if ( c === 13 ) { // '\r'

			con_x = 0;
			cr = true;

		} else {

			// display character and advance
			const y = con_current % con_totallines;
			con_text[ y * con_linewidth + con_x ] = c | mask;
			con_x ++;
			if ( con_x >= con_linewidth )
				con_x = 0;

		}

	}

}

/*
================
Con_Printf

Handles cursor positioning, line wrapping, etc
================
*/
let inupdate = false;

export function Con_Printf( ...args ) {

	// Format the message - simple concatenation since JS doesn't have vsprintf
	let msg = '';
	if ( args.length === 1 ) {

		msg = String( args[ 0 ] );

	} else {

		// Simple printf-style formatting
		msg = _sprintf( args[ 0 ], ...args.slice( 1 ) );

	}

	if ( ! con_initialized )
		return;

	// write it to the scrollable buffer
	Con_Print( msg );

	// update the screen if the console is displayed
	if ( _cls.signon !== 4 && ! _scr_disabled_for_loading ) { // SIGNONS = 4

		// protect against infinite loop if something in SCR_UpdateScreen calls Con_Printf
		if ( ! inupdate ) {

			inupdate = true;
			if ( _SCR_UpdateScreen ) _SCR_UpdateScreen();
			inupdate = false;

		}

	}

}

/*
================
Con_DPrintf

A Con_Printf that only shows up if the "developer" cvar is set
================
*/
export function Con_DPrintf( ...args ) {

	if ( ! _developer.value )
		return; // don't confuse non-developers with techie stuff...

	Con_Printf( ...args );

}

/*
==================
Con_SafePrintf

Okay to call even when the screen can't be updated
==================
*/
export function Con_SafePrintf( ...args ) {

	const temp = _scr_disabled_for_loading;
	_scr_disabled_for_loading = true;
	Con_Printf( ...args );
	_scr_disabled_for_loading = temp;

}

/*
==============================================================================

DRAWING

==============================================================================
*/

/*
================
Con_DrawInput

The input line scrolls horizontally if typing goes beyond the right edge
================
*/
function Con_DrawInput() {

	if ( key_dest !== key_console && ! con_forcedup )
		return; // don't draw anything

	if ( ! _Draw_Character ) return;

	const text = key_lines[ edit_line ];

	// add the cursor frame
	text[ key_linepos ] = 10 + ( ( Math.floor( _getRealtime() * con_cursorspeed ) ) & 1 );

	// fill out remainder with spaces
	for ( let i = key_linepos + 1; i < con_linewidth; i ++ )
		text[ i ] = 32; // ' '

	// prestep if horizontally scrolling
	let start = 0;
	if ( key_linepos >= con_linewidth )
		start = 1 + key_linepos - con_linewidth;

	// draw it
	for ( let i = 0; i < con_linewidth; i ++ )
		_Draw_Character( ( i + 1 ) << 3, con_vislines - 16, text[ start + i ] );

	// remove cursor
	key_lines[ edit_line ][ key_linepos ] = 0;

}

/*
================
Con_DrawNotify

Draws the last few lines of output transparently over the game top
================
*/
export function Con_DrawNotify() {

	if ( ! _Draw_Character ) return;

	let v = 0;
	const realtime = _getRealtime();

	for ( let i = con_current - NUM_CON_TIMES + 1; i <= con_current; i ++ ) {

		if ( i < 0 )
			continue;

		const time = con_times[ i % NUM_CON_TIMES ];
		if ( time === 0 )
			continue;

		const age = realtime - time;
		if ( age > con_notifytime.value )
			continue;

		const textStart = ( i % con_totallines ) * con_linewidth;

		for ( let x = 0; x < con_linewidth; x ++ )
			_Draw_Character( ( x + 1 ) << 3, v, con_text[ textStart + x ] );

		v += 8;

	}

	if ( key_dest === key_message ) {

		if ( _Draw_String ) _Draw_String( 8, v, 'say:' );

		if ( _Draw_Character ) {

			for ( let x = 0; x < chat_buffer.length; x ++ ) {

				_Draw_Character( ( x + 5 ) << 3, v, chat_buffer.charCodeAt( x ) );

			}

		}

		v += 8;

	}

	if ( v > con_notifylines )
		con_notifylines = v;

}

/*
================
Con_DrawConsole

Draws the console with the solid background
The typing input line at the bottom should only be drawn if typing is allowed
================
*/
export function Con_DrawConsole( lines, drawinput ) {

	if ( lines <= 0 )
		return;

	// draw the background
	if ( _Draw_ConsoleBackground ) _Draw_ConsoleBackground( lines );

	// draw the text
	con_vislines = lines;

	const rows = ( lines - 16 ) >> 3; // rows of text to draw
	let y = lines - 16 - ( rows << 3 ); // may start slightly negative

	for ( let i = con_current - rows + 1; i <= con_current; i ++, y += 8 ) {

		let j = i - con_backscroll;
		if ( j < 0 )
			j = 0;

		const textStart = ( j % con_totallines ) * con_linewidth;

		if ( _Draw_Character ) {

			for ( let x = 0; x < con_linewidth; x ++ )
				_Draw_Character( ( x + 1 ) << 3, y, con_text[ textStart + x ] );

		}

	}

	// draw the input prompt, user text, and cursor if desired
	if ( drawinput )
		Con_DrawInput();

}

/*
==================
Con_NotifyBox
==================
*/
export function Con_NotifyBox( text ) {

	// during startup for sound / cd warnings
	Con_Printf( '\n\n\x1d\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1f\n' );
	Con_Printf( text );
	Con_Printf( 'Press a key.\n' );
	Con_Printf( '\x1d\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1e\x1f\n' );

	// In browser, we can't block. This would need to be async.
	// For now, just print the notification.

}

/*
==============================================================================

			INTERNAL HELPERS

==============================================================================
*/

// sprintf implementation supporting width, precision, and flags for Quake format strings
function _sprintf( fmt, ...args ) {

	if ( typeof fmt !== 'string' ) return String( fmt );

	let result = '';
	let argIdx = 0;
	let i = 0;

	while ( i < fmt.length ) {

		if ( fmt[ i ] === '%' && i + 1 < fmt.length ) {

			i ++;

			// Parse flags: -, +, 0, space, #
			let leftAlign = false;
			let zeroPad = false;
			let plusSign = false;
			let spaceSign = false;

			let parsing = true;
			while ( i < fmt.length && parsing ) {

				switch ( fmt[ i ] ) {

					case '-': leftAlign = true; i ++; break;
					case '0': zeroPad = true; i ++; break;
					case '+': plusSign = true; i ++; break;
					case ' ': spaceSign = true; i ++; break;
					case '#': i ++; break; // ignore # flag
					default: parsing = false; break;

				}

			}

			// Parse width
			let width = 0;
			while ( i < fmt.length && fmt[ i ] >= '0' && fmt[ i ] <= '9' ) {

				width = width * 10 + ( fmt.charCodeAt( i ) - 48 );
				i ++;

			}

			// Parse precision
			let precision = - 1;
			if ( i < fmt.length && fmt[ i ] === '.' ) {

				i ++;
				precision = 0;
				while ( i < fmt.length && fmt[ i ] >= '0' && fmt[ i ] <= '9' ) {

					precision = precision * 10 + ( fmt.charCodeAt( i ) - 48 );
					i ++;

				}

			}

			// Parse conversion specifier
			let str = '';
			if ( i < fmt.length ) {

				switch ( fmt[ i ] ) {

					case 's': {

						const val = args[ argIdx ++ ];
						str = val != null ? String( val ) : '';
						if ( precision >= 0 && str.length > precision )
							str = str.substring( 0, precision );
						break;

					}
					case 'd':
					case 'i': {

						const val = args[ argIdx ++ ];
						const num = Math.floor( Number( val ) );
						const n = isNaN( num ) ? 0 : num;
						str = String( Math.abs( n ) );
						if ( n < 0 ) str = '-' + str;
						else if ( plusSign ) str = '+' + str;
						else if ( spaceSign ) str = ' ' + str;
						break;

					}
					case 'f': {

						const val = args[ argIdx ++ ];
						const num = Number( val );
						const n = isNaN( num ) ? 0.0 : num;
						const prec = precision >= 0 ? precision : 6;
						str = n.toFixed( prec );
						if ( plusSign && n >= 0 ) str = '+' + str;
						else if ( spaceSign && n >= 0 ) str = ' ' + str;
						break;

					}
					case 'c': {

						const val = args[ argIdx ++ ];
						str = String.fromCharCode( val != null ? val : 0 );
						break;

					}
					case '%':
						str = '%';
						break;
					default:
						str = fmt[ i ];
						break;

				}

			}

			// Apply width padding
			if ( width > 0 && str.length < width ) {

				const padChar = ( zeroPad && ! leftAlign ) ? '0' : ' ';
				const padLen = width - str.length;
				const padding = padChar.repeat( padLen );
				if ( leftAlign ) {

					str = str + padding;

				} else {

					// For zero-padded negative numbers, put '-' before zeros
					if ( zeroPad && str.length > 0 && str[ 0 ] === '-' ) {

						str = '-' + padding + str.substring( 1 );

					} else {

						str = padding + str;

					}

				}

			}

			result += str;
			i ++;

		} else {

			result += fmt[ i ];
			i ++;

		}

	}

	return result;

}
