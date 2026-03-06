// Ported from: WinQuake/sbar.c, WinQuake/sbar.h -- status bar / HUD code

import { Cmd_AddCommand } from './cmd.js';
import { realtime } from './host.js';
import { Con_Printf } from './console.js';
import { Draw_GetVirtualWidth, Draw_GetVirtualHeight } from './gl_draw.js';
import {
	IT_SHOTGUN, IT_SUPER_SHOTGUN, IT_NAILGUN, IT_SUPER_NAILGUN,
	IT_GRENADE_LAUNCHER, IT_ROCKET_LAUNCHER, IT_LIGHTNING, IT_SUPER_LIGHTNING,
	IT_SHELLS, IT_NAILS, IT_ROCKETS, IT_CELLS, IT_AXE,
	IT_ARMOR1, IT_ARMOR2, IT_ARMOR3, IT_SUPERHEALTH,
	IT_KEY1, IT_KEY2, IT_INVISIBILITY, IT_INVULNERABILITY, IT_SUIT, IT_QUAD,
	IT_SIGIL1, IT_SIGIL2, IT_SIGIL3, IT_SIGIL4,
	STAT_HEALTH, STAT_FRAGS, STAT_WEAPON, STAT_AMMO, STAT_ARMOR,
	STAT_SHELLS, STAT_NAILS, STAT_ROCKETS, STAT_CELLS,
	STAT_ACTIVEWEAPON, STAT_TOTALSECRETS, STAT_TOTALMONSTERS,
	STAT_SECRETS, STAT_MONSTERS, STAT_PING,
	MAX_SCOREBOARD,
	HIT_PROXIMITY_GUN_BIT, HIT_MJOLNIR_BIT, HIT_LASER_CANNON_BIT,
	HIT_PROXIMITY_GUN, HIT_MJOLNIR, HIT_LASER_CANNON, HIT_WETSUIT, HIT_EMPATHY_SHIELDS,
	RIT_SHELLS, RIT_NAILS, RIT_ROCKETS, RIT_CELLS, RIT_AXE,
	RIT_LAVA_NAILGUN, RIT_LAVA_SUPER_NAILGUN, RIT_MULTI_GRENADE,
	RIT_MULTI_ROCKET, RIT_PLASMA_GUN,
	RIT_ARMOR1, RIT_ARMOR2, RIT_ARMOR3,
	RIT_LAVA_NAILS, RIT_PLASMA_AMMO, RIT_MULTI_ROCKETS,
	RIT_SHIELD, RIT_ANTIGRAV, RIT_SUPERHEALTH,
} from './quakedef.js';

/*
==============================================================================

			STATUS BAR CONSTANTS

==============================================================================
*/

export const SBAR_HEIGHT = 24;
const STAT_MINUS = 10; // num frame for '-' stats digit

const GAME_DEATHMATCH = 1;

/*
==============================================================================

			STATUS BAR STATE

==============================================================================
*/

let sb_updates = 0; // if >= vid.numpages, no update needed

// Pic references (loaded in Sbar_Init)
const sb_nums = [ new Array( 11 ).fill( null ), new Array( 11 ).fill( null ) ];
let sb_colon = null;
let sb_slash = null;
let sb_ibar = null;
let sb_sbar = null;
let sb_scorebar = null;

const sb_weapons = [];
for ( let i = 0; i < 7; i ++ ) sb_weapons[ i ] = new Array( 8 ).fill( null );

const sb_ammo = new Array( 4 ).fill( null );
const sb_sigil = new Array( 4 ).fill( null );
const sb_armor = new Array( 3 ).fill( null );
const sb_items = new Array( 32 ).fill( null );

const sb_faces = [];
for ( let i = 0; i < 7; i ++ ) sb_faces[ i ] = new Array( 2 ).fill( null );

let sb_face_invis = null;
let sb_face_quad = null;
let sb_face_invuln = null;
let sb_face_invis_invuln = null;

let sb_showscores = false;
export let sb_lines = 0; // scan lines to draw
export function set_sb_lines( v ) { sb_lines = v; }

// Rogue mission pack
const rsb_invbar = new Array( 2 ).fill( null );
const rsb_weapons = new Array( 5 ).fill( null );
const rsb_items = new Array( 2 ).fill( null );
const rsb_ammo = new Array( 3 ).fill( null );
let rsb_teambord = null;

// Hipnotic mission pack
const hsb_weapons = [];
for ( let i = 0; i < 7; i ++ ) hsb_weapons[ i ] = new Array( 5 ).fill( null );
const hipweapons = [ HIT_LASER_CANNON_BIT, HIT_MJOLNIR_BIT, 4, HIT_PROXIMITY_GUN_BIT ];
const hsb_items = new Array( 2 ).fill( null );

// Scoreboard state
const fragsort = new Array( MAX_SCOREBOARD ).fill( 0 );
const scoreboardtext = [];
for ( let i = 0; i < MAX_SCOREBOARD; i ++ ) scoreboardtext[ i ] = '';
const scoreboardtop = new Array( MAX_SCOREBOARD ).fill( 0 );
const scoreboardbottom = new Array( MAX_SCOREBOARD ).fill( 0 );
const scoreboardcount = new Array( MAX_SCOREBOARD ).fill( 0 );
let scoreboardlines = 0;

/*
==============================================================================

			EXTERNAL REFERENCES

==============================================================================
*/

let _cl = { stats: new Int32Array( 32 ), items: 0, gametype: 0, scores: [], time: 0, faceanimtime: 0, maxclients: 16, levelname: '', item_gettime: new Float32Array( 32 ), viewentity: 0 };
let _realVid = { width: 640, height: 480, numpages: 1 };
const _vid = {
	get width() { return Draw_GetVirtualWidth(); },
	get height() { return Draw_GetVirtualHeight(); },
	get numpages() { return _realVid.numpages; }
};
let _Draw_Pic = null;
let _Draw_TransPic = null;
let _Draw_Character = null;
let _Draw_String = null;
let _Draw_Fill = null;
let _Draw_PicFromWad = null;
let _Draw_CachePic = null;
let _hipnotic = false;
let _rogue = false;
// realtime is imported live from host.js via the 'realtime' binding

export function Sbar_SetExternals( externals ) {

	if ( externals.cl ) _cl = externals.cl;
	if ( externals.vid ) _realVid = externals.vid;
	if ( externals.Draw_Pic ) _Draw_Pic = externals.Draw_Pic;
	if ( externals.Draw_TransPic ) _Draw_TransPic = externals.Draw_TransPic;
	if ( externals.Draw_Character ) _Draw_Character = externals.Draw_Character;
	if ( externals.Draw_String ) _Draw_String = externals.Draw_String;
	if ( externals.Draw_Fill ) _Draw_Fill = externals.Draw_Fill;
	if ( externals.Draw_PicFromWad ) _Draw_PicFromWad = externals.Draw_PicFromWad;
	if ( externals.Draw_CachePic ) _Draw_CachePic = externals.Draw_CachePic;
	if ( externals.hipnotic !== undefined ) _hipnotic = externals.hipnotic;
	if ( externals.rogue !== undefined ) _rogue = externals.rogue;

}

/*
===============
Sbar_ShowScores / Sbar_DontShowScores

Tab key down/up
===============
*/
export function Sbar_ShowScores() {

	if ( sb_showscores ) return;
	sb_showscores = true;
	sb_updates = 0;

}

export function Sbar_DontShowScores() {

	sb_showscores = false;
	sb_updates = 0;

}

/*
===============
Sbar_Changed
===============
*/
export function Sbar_Changed() {

	sb_updates = 0; // update next frame

}

/*
===============
Sbar_Init
===============
*/
export function Sbar_Init() {

	if ( ! _Draw_PicFromWad ) {

		Con_Printf( 'Sbar_Init: Draw_PicFromWad not available yet\n' );
		return;

	}

	for ( let i = 0; i < 10; i ++ ) {

		sb_nums[ 0 ][ i ] = _Draw_PicFromWad( 'num_' + i );
		sb_nums[ 1 ][ i ] = _Draw_PicFromWad( 'anum_' + i );

	}

	sb_nums[ 0 ][ 10 ] = _Draw_PicFromWad( 'num_minus' );
	sb_nums[ 1 ][ 10 ] = _Draw_PicFromWad( 'anum_minus' );

	sb_colon = _Draw_PicFromWad( 'num_colon' );
	sb_slash = _Draw_PicFromWad( 'num_slash' );

	sb_weapons[ 0 ][ 0 ] = _Draw_PicFromWad( 'inv_shotgun' );
	sb_weapons[ 0 ][ 1 ] = _Draw_PicFromWad( 'inv_sshotgun' );
	sb_weapons[ 0 ][ 2 ] = _Draw_PicFromWad( 'inv_nailgun' );
	sb_weapons[ 0 ][ 3 ] = _Draw_PicFromWad( 'inv_snailgun' );
	sb_weapons[ 0 ][ 4 ] = _Draw_PicFromWad( 'inv_rlaunch' );
	sb_weapons[ 0 ][ 5 ] = _Draw_PicFromWad( 'inv_srlaunch' );
	sb_weapons[ 0 ][ 6 ] = _Draw_PicFromWad( 'inv_lightng' );

	sb_weapons[ 1 ][ 0 ] = _Draw_PicFromWad( 'inv2_shotgun' );
	sb_weapons[ 1 ][ 1 ] = _Draw_PicFromWad( 'inv2_sshotgun' );
	sb_weapons[ 1 ][ 2 ] = _Draw_PicFromWad( 'inv2_nailgun' );
	sb_weapons[ 1 ][ 3 ] = _Draw_PicFromWad( 'inv2_snailgun' );
	sb_weapons[ 1 ][ 4 ] = _Draw_PicFromWad( 'inv2_rlaunch' );
	sb_weapons[ 1 ][ 5 ] = _Draw_PicFromWad( 'inv2_srlaunch' );
	sb_weapons[ 1 ][ 6 ] = _Draw_PicFromWad( 'inv2_lightng' );

	for ( let i = 0; i < 5; i ++ ) {

		sb_weapons[ 2 + i ][ 0 ] = _Draw_PicFromWad( 'inva' + ( i + 1 ) + '_shotgun' );
		sb_weapons[ 2 + i ][ 1 ] = _Draw_PicFromWad( 'inva' + ( i + 1 ) + '_sshotgun' );
		sb_weapons[ 2 + i ][ 2 ] = _Draw_PicFromWad( 'inva' + ( i + 1 ) + '_nailgun' );
		sb_weapons[ 2 + i ][ 3 ] = _Draw_PicFromWad( 'inva' + ( i + 1 ) + '_snailgun' );
		sb_weapons[ 2 + i ][ 4 ] = _Draw_PicFromWad( 'inva' + ( i + 1 ) + '_rlaunch' );
		sb_weapons[ 2 + i ][ 5 ] = _Draw_PicFromWad( 'inva' + ( i + 1 ) + '_srlaunch' );
		sb_weapons[ 2 + i ][ 6 ] = _Draw_PicFromWad( 'inva' + ( i + 1 ) + '_lightng' );

	}

	sb_ammo[ 0 ] = _Draw_PicFromWad( 'sb_shells' );
	sb_ammo[ 1 ] = _Draw_PicFromWad( 'sb_nails' );
	sb_ammo[ 2 ] = _Draw_PicFromWad( 'sb_rocket' );
	sb_ammo[ 3 ] = _Draw_PicFromWad( 'sb_cells' );

	sb_armor[ 0 ] = _Draw_PicFromWad( 'sb_armor1' );
	sb_armor[ 1 ] = _Draw_PicFromWad( 'sb_armor2' );
	sb_armor[ 2 ] = _Draw_PicFromWad( 'sb_armor3' );

	sb_items[ 0 ] = _Draw_PicFromWad( 'sb_key1' );
	sb_items[ 1 ] = _Draw_PicFromWad( 'sb_key2' );
	sb_items[ 2 ] = _Draw_PicFromWad( 'sb_invis' );
	sb_items[ 3 ] = _Draw_PicFromWad( 'sb_invuln' );
	sb_items[ 4 ] = _Draw_PicFromWad( 'sb_suit' );
	sb_items[ 5 ] = _Draw_PicFromWad( 'sb_quad' );

	sb_sigil[ 0 ] = _Draw_PicFromWad( 'sb_sigil1' );
	sb_sigil[ 1 ] = _Draw_PicFromWad( 'sb_sigil2' );
	sb_sigil[ 2 ] = _Draw_PicFromWad( 'sb_sigil3' );
	sb_sigil[ 3 ] = _Draw_PicFromWad( 'sb_sigil4' );

	sb_faces[ 4 ][ 0 ] = _Draw_PicFromWad( 'face1' );
	sb_faces[ 4 ][ 1 ] = _Draw_PicFromWad( 'face_p1' );
	sb_faces[ 3 ][ 0 ] = _Draw_PicFromWad( 'face2' );
	sb_faces[ 3 ][ 1 ] = _Draw_PicFromWad( 'face_p2' );
	sb_faces[ 2 ][ 0 ] = _Draw_PicFromWad( 'face3' );
	sb_faces[ 2 ][ 1 ] = _Draw_PicFromWad( 'face_p3' );
	sb_faces[ 1 ][ 0 ] = _Draw_PicFromWad( 'face4' );
	sb_faces[ 1 ][ 1 ] = _Draw_PicFromWad( 'face_p4' );
	sb_faces[ 0 ][ 0 ] = _Draw_PicFromWad( 'face5' );
	sb_faces[ 0 ][ 1 ] = _Draw_PicFromWad( 'face_p5' );

	sb_face_invis = _Draw_PicFromWad( 'face_invis' );
	sb_face_invuln = _Draw_PicFromWad( 'face_invul2' );
	sb_face_invis_invuln = _Draw_PicFromWad( 'face_inv2' );
	sb_face_quad = _Draw_PicFromWad( 'face_quad' );

	Cmd_AddCommand( '+showscores', Sbar_ShowScores );
	Cmd_AddCommand( '-showscores', Sbar_DontShowScores );

	sb_sbar = _Draw_PicFromWad( 'sbar' );
	sb_ibar = _Draw_PicFromWad( 'ibar' );
	sb_scorebar = _Draw_PicFromWad( 'scorebar' );

}

/*
=============================================================================

			DRAWING ROUTINES

drawing routines are relative to the status bar location

=============================================================================
*/

/*
=============
Sbar_DrawPic
=============
*/
function Sbar_DrawPic( x, y, pic ) {

	if ( ! _Draw_Pic || ! pic ) return;

	if ( _cl.gametype === GAME_DEATHMATCH )
		_Draw_Pic( x, y + ( _vid.height - SBAR_HEIGHT ), pic );
	else
		_Draw_Pic( x + ( ( _vid.width - 320 ) >> 1 ), y + ( _vid.height - SBAR_HEIGHT ), pic );

}

/*
=============
Sbar_DrawTransPic
=============
*/
function Sbar_DrawTransPic( x, y, pic ) {

	if ( ! _Draw_TransPic || ! pic ) return;

	if ( _cl.gametype === GAME_DEATHMATCH )
		_Draw_TransPic( x, y + ( _vid.height - SBAR_HEIGHT ), pic );
	else
		_Draw_TransPic( x + ( ( _vid.width - 320 ) >> 1 ), y + ( _vid.height - SBAR_HEIGHT ), pic );

}

/*
================
Sbar_DrawCharacter

Draws one solid graphics character
================
*/
function Sbar_DrawCharacter( x, y, num ) {

	if ( ! _Draw_Character ) return;

	if ( _cl.gametype === GAME_DEATHMATCH )
		_Draw_Character( x + 4, y + _vid.height - SBAR_HEIGHT, num );
	else
		_Draw_Character( x + ( ( _vid.width - 320 ) >> 1 ) + 4, y + _vid.height - SBAR_HEIGHT, num );

}

/*
================
Sbar_DrawString
================
*/
function Sbar_DrawString( x, y, str ) {

	if ( ! _Draw_Character ) return;

	if ( _cl.gametype === GAME_DEATHMATCH ) {

		for ( let i = 0; i < str.length; i ++ )
			_Draw_Character( x + i * 8, y + _vid.height - SBAR_HEIGHT, str.charCodeAt( i ) );

	} else {

		for ( let i = 0; i < str.length; i ++ )
			_Draw_Character( x + ( ( _vid.width - 320 ) >> 1 ) + i * 8, y + _vid.height - SBAR_HEIGHT, str.charCodeAt( i ) );

	}

}

/*
=============
Sbar_DrawNum

Draws a number with the large status bar font
=============
*/
function Sbar_DrawNum( x, y, num, digits, color ) {

	const str = String( num );
	let ptr = 0;
	let l = str.length;

	if ( l > digits )
		l = digits;

	let frame;

	if ( num < 0 ) {

		// draw minus sign
		frame = sb_nums[ color ] ? sb_nums[ color ][ STAT_MINUS ] : null;
		Sbar_DrawPic( x - 24, y, frame );
		ptr = 1; // skip the minus in string

	}

	x += ( digits - l ) * 24;

	while ( ptr < str.length && l > 0 ) {

		const c = str.charCodeAt( ptr );
		if ( c >= 48 && c <= 57 ) { // '0' to '9'

			frame = sb_nums[ color ] ? sb_nums[ color ][ c - 48 ] : null;

		} else if ( c === 45 ) { // '-'

			frame = sb_nums[ color ] ? sb_nums[ color ][ STAT_MINUS ] : null;

		} else {

			frame = null;

		}

		Sbar_DrawPic( x, y, frame );
		x += 24;
		ptr ++;
		l --;

	}

}

/*
===============
Sbar_DrawInventory
===============
*/
function Sbar_DrawInventory() {

	Sbar_DrawPic( 0, - 24, sb_ibar );

	// weapons
	for ( let i = 0; i < 7; i ++ ) {

		if ( _cl.items & ( IT_SHOTGUN << i ) ) {

			const time = _cl.item_gettime[ i ];
			let flashon = Math.floor( ( _cl.time - time ) * 10 );
			if ( flashon >= 10 ) {

				if ( _cl.stats[ STAT_ACTIVEWEAPON ] === ( IT_SHOTGUN << i ) )
					flashon = 1;
				else
					flashon = 0;

			} else {

				flashon = ( flashon % 5 ) + 2;

			}

			Sbar_DrawPic( i * 24, - 16, sb_weapons[ flashon ][ i ] );

			if ( flashon > 1 )
				sb_updates = 0; // force update to remove flash

		}

	}

	// ammo counts
	for ( let i = 0; i < 4; i ++ ) {

		const num = String( _cl.stats[ STAT_SHELLS + i ] ).padStart( 3, ' ' );
		if ( num[ 0 ] !== ' ' )
			Sbar_DrawCharacter( ( 6 * i + 1 ) * 8 - 2, - 24, 18 + num.charCodeAt( 0 ) - 48 );
		if ( num[ 1 ] !== ' ' )
			Sbar_DrawCharacter( ( 6 * i + 2 ) * 8 - 2, - 24, 18 + num.charCodeAt( 1 ) - 48 );
		if ( num[ 2 ] !== ' ' )
			Sbar_DrawCharacter( ( 6 * i + 3 ) * 8 - 2, - 24, 18 + num.charCodeAt( 2 ) - 48 );

	}

	// items
	let flashon = 0;
	for ( let i = 0; i < 6; i ++ ) {

		if ( _cl.items & ( 1 << ( 17 + i ) ) ) {

			const time = _cl.item_gettime[ 17 + i ];
			if ( time !== 0 && time > _cl.time - 2 && flashon ) {

				// flash frame
				sb_updates = 0;

			} else {

				Sbar_DrawPic( 192 + i * 16, - 16, sb_items[ i ] );

			}

			if ( time !== 0 && time > _cl.time - 2 )
				sb_updates = 0;

		}

	}

	// sigils
	for ( let i = 0; i < 4; i ++ ) {

		if ( _cl.items & ( 1 << ( 28 + i ) ) ) {

			const time = _cl.item_gettime[ 28 + i ];
			if ( time !== 0 && time > _cl.time - 2 && flashon ) {

				// flash frame
				sb_updates = 0;

			} else {

				Sbar_DrawPic( 320 - 32 + i * 8, - 16, sb_sigil[ i ] );

			}

			if ( time !== 0 && time > _cl.time - 2 )
				sb_updates = 0;

		}

	}

}

/*
===============
Sbar_DrawFrags
===============
*/
function Sbar_DrawFrags() {

	if ( _cl.scores == null ) return;

	Sbar_SortFrags();

	// draw the text
	const l = scoreboardlines <= 4 ? scoreboardlines : 4;

	let x = 23;
	let xofs;
	if ( _cl.gametype === GAME_DEATHMATCH )
		xofs = 0;
	else
		xofs = ( _vid.width - 320 ) >> 1;
	const y = _vid.height - SBAR_HEIGHT - 23;

	for ( let i = 0; i < l; i ++ ) {

		const k = fragsort[ i ];
		const s = _cl.scores[ k ];
		if ( s == null || s.name == null || s.name.length === 0 )
			continue;

		// draw background
		let top = s.colors & 0xf0;
		let bottom = ( s.colors & 15 ) << 4;
		top = Sbar_ColorForMap( top );
		bottom = Sbar_ColorForMap( bottom );

		if ( _Draw_Fill != null ) {

			_Draw_Fill( xofs + x * 8 + 10, y, 28, 4, top );
			_Draw_Fill( xofs + x * 8 + 10, y + 4, 28, 3, bottom );

		}

		// draw number
		const f = s.frags;
		const num = String( f ).padStart( 3, ' ' );

		Sbar_DrawCharacter( ( x + 1 ) * 8, - 24, num.charCodeAt( 0 ) );
		Sbar_DrawCharacter( ( x + 2 ) * 8, - 24, num.charCodeAt( 1 ) );
		Sbar_DrawCharacter( ( x + 3 ) * 8, - 24, num.charCodeAt( 2 ) );

		if ( k === _cl.viewentity - 1 ) {

			Sbar_DrawCharacter( x * 8 + 2, - 24, 16 );
			Sbar_DrawCharacter( ( x + 4 ) * 8 - 4, - 24, 17 );

		}

		x += 4;

	}

}

/*
===============
Sbar_SortFrags
===============
*/
function Sbar_SortFrags() {

	// sort by frags
	scoreboardlines = 0;
	const maxclients = _cl.maxclients || 16;

	for ( let i = 0; i < maxclients; i ++ ) {

		if ( _cl.scores && _cl.scores[ i ] && _cl.scores[ i ].name && _cl.scores[ i ].name.length > 0 ) {

			fragsort[ scoreboardlines ] = i;
			scoreboardlines ++;

		}

	}

	// bubble sort by frags (descending)
	for ( let i = 0; i < scoreboardlines; i ++ ) {

		for ( let j = 0; j < scoreboardlines - 1 - i; j ++ ) {

			if ( _cl.scores[ fragsort[ j ] ].frags < _cl.scores[ fragsort[ j + 1 ] ].frags ) {

				const k = fragsort[ j ];
				fragsort[ j ] = fragsort[ j + 1 ];
				fragsort[ j + 1 ] = k;

			}

		}

	}

}

/*
===============
Sbar_ColorForMap
===============
*/
function Sbar_ColorForMap( m ) {

	return m < 128 ? m + 8 : m + 8;

}

/*
===============
Sbar_UpdateScoreboard
===============
*/
function Sbar_UpdateScoreboard() {

	Sbar_SortFrags();

	// draw the text
	for ( let i = 0; i < MAX_SCOREBOARD; i ++ ) {

		scoreboardtext[ i ] = '';

	}

	for ( let i = 0; i < scoreboardlines; i ++ ) {

		const k = fragsort[ i ];
		const s = _cl.scores[ k ];

		// format: " %3i %s" (frags + name)
		const fragStr = String( s.frags ).padStart( 3, ' ' );
		scoreboardtext[ i ] = ' ' + fragStr + ' ' + ( s.name || '' );

		const top = s.colors & 0xf0;
		const bottom = ( s.colors & 15 ) << 4;
		scoreboardtop[ i ] = Sbar_ColorForMap( top );
		scoreboardbottom[ i ] = Sbar_ColorForMap( bottom );

	}

}

/*
===============
Sbar_SoloScoreboard
===============
*/
function Sbar_SoloScoreboard() {

	// Monsters
	const monstersStr = 'Monsters:' + String( _cl.stats[ STAT_MONSTERS ] ).padStart( 3, ' ' ) + ' /' +
		String( _cl.stats[ STAT_TOTALMONSTERS ] ).padStart( 3, ' ' );
	Sbar_DrawString( 8, 4, monstersStr );

	// Secrets
	const secretsStr = 'Secrets :' + String( _cl.stats[ STAT_SECRETS ] ).padStart( 3, ' ' ) + ' /' +
		String( _cl.stats[ STAT_TOTALSECRETS ] ).padStart( 3, ' ' );
	Sbar_DrawString( 8, 12, secretsStr );

	// Time
	const minutes = Math.floor( _cl.time / 60 );
	const seconds = Math.floor( _cl.time ) - 60 * minutes;
	const tens = Math.floor( seconds / 10 );
	const units = seconds - 10 * tens;
	const timeStr = 'Time :' + String( minutes ).padStart( 3, ' ' ) + ':' + tens + units;
	Sbar_DrawString( 184, 4, timeStr );

	// Level name
	const levelname = _cl.levelname || '';
	const l = levelname.length;
	Sbar_DrawString( 232 - l * 4, 12, levelname );

}

/*
===============
Sbar_DrawScoreboard
===============
*/
function Sbar_DrawScoreboard() {

	Sbar_SoloScoreboard();
	if ( _cl.gametype === GAME_DEATHMATCH )
		Sbar_DeathmatchOverlay();

}

/*
===============
Sbar_DrawFace

Returns the health face to display
===============
*/
function Sbar_DrawFace() {

	// PGM 01/19/97 - team color drawing (rogue only) is not ported

	let f;
	let anim;

	if ( ( _cl.items & ( IT_INVISIBILITY | IT_INVULNERABILITY ) ) === ( IT_INVISIBILITY | IT_INVULNERABILITY ) ) {

		Sbar_DrawPic( 112, 0, sb_face_invis_invuln );
		return;

	}

	if ( _cl.items & IT_QUAD ) {

		Sbar_DrawPic( 112, 0, sb_face_quad );
		return;

	}

	if ( _cl.items & IT_INVISIBILITY ) {

		Sbar_DrawPic( 112, 0, sb_face_invis );
		return;

	}

	if ( _cl.items & IT_INVULNERABILITY ) {

		Sbar_DrawPic( 112, 0, sb_face_invuln );
		return;

	}

	const health = _cl.stats[ STAT_HEALTH ];

	if ( health >= 100 )
		f = 4;
	else
		f = Math.floor( health / 20 );

	if ( f < 0 ) f = 0;
	if ( f > 4 ) f = 4;

	// pain animation
	anim = 0;
	if ( _cl.time <= _cl.faceanimtime ) {

		anim = 1;
		sb_updates = 0; // make sure the anim gets drawn over

	}

	Sbar_DrawPic( 112, 0, sb_faces[ f ][ anim ] );

}

/*
===============
Sbar_DrawAmmo
===============
*/
function Sbar_DrawAmmo() {

	Sbar_DrawNum( 248, 0, _cl.stats[ STAT_AMMO ], 3, _cl.stats[ STAT_AMMO ] <= 10 ? 1 : 0 );

}

/*
===============
Sbar_Draw
===============
*/
export function Sbar_Draw() {

	// Force redraw every frame — canvas overlay is cleared each frame
	sb_updates = 0;

	if ( sb_lines > 24 ) {

		Sbar_DrawInventory();
		if ( _cl.maxclients !== 1 )
			Sbar_DrawFrags();

	}

	if ( sb_showscores || _cl.stats[ STAT_HEALTH ] <= 0 ) {

		Sbar_DrawPic( 0, 0, sb_scorebar );
		Sbar_DrawScoreboard();
		sb_updates = 0;

	} else if ( sb_lines > 0 ) {

		Sbar_DrawPic( 0, 0, sb_sbar );

		// armor
		if ( ( _cl.items & IT_INVULNERABILITY ) !== 0 ) {

			Sbar_DrawNum( 24, 0, 666, 3, 1 );
			// draw_disc would go here (invulnerability icon)

		} else {

			Sbar_DrawNum( 24, 0, _cl.stats[ STAT_ARMOR ], 3, _cl.stats[ STAT_ARMOR ] <= 25 ? 1 : 0 );
			if ( ( _cl.items & IT_ARMOR3 ) !== 0 )
				Sbar_DrawPic( 0, 0, sb_armor[ 2 ] );
			else if ( ( _cl.items & IT_ARMOR2 ) !== 0 )
				Sbar_DrawPic( 0, 0, sb_armor[ 1 ] );
			else if ( ( _cl.items & IT_ARMOR1 ) !== 0 )
				Sbar_DrawPic( 0, 0, sb_armor[ 0 ] );

		}

		// face
		Sbar_DrawFace();

		// health
		Sbar_DrawNum( 136, 0, _cl.stats[ STAT_HEALTH ], 3, _cl.stats[ STAT_HEALTH ] <= 25 ? 1 : 0 );

		// ammo icon
		if ( ( _cl.items & IT_SHELLS ) !== 0 )
			Sbar_DrawPic( 224, 0, sb_ammo[ 0 ] );
		else if ( ( _cl.items & IT_NAILS ) !== 0 )
			Sbar_DrawPic( 224, 0, sb_ammo[ 1 ] );
		else if ( ( _cl.items & IT_ROCKETS ) !== 0 )
			Sbar_DrawPic( 224, 0, sb_ammo[ 2 ] );
		else if ( ( _cl.items & IT_CELLS ) !== 0 )
			Sbar_DrawPic( 224, 0, sb_ammo[ 3 ] );

		// ammo count
		Sbar_DrawNum( 248, 0, _cl.stats[ STAT_AMMO ], 3, _cl.stats[ STAT_AMMO ] <= 10 ? 1 : 0 );

	}

	if ( _vid.width > 320 ) {

		if ( _cl.gametype === GAME_DEATHMATCH )
			Sbar_MiniDeathmatchOverlay();

	}

	// Draw ping in deathmatch
	if ( _cl.gametype === GAME_DEATHMATCH ) {

		Sbar_DrawPing();

	}

}

/*
==================
Sbar_DrawPing

Draw ping (latency) in the top-right corner during deathmatch
==================
*/
function Sbar_DrawPing() {

	if ( _Draw_Character == null ) return;

	const pingMs = _cl.stats[ STAT_PING ];
	const str = pingMs + 'ms';

	// Draw in top-right corner
	const x = _vid.width - str.length * 8 - 8;
	const y = 8;

	for ( let i = 0; i < str.length; i ++ )
		_Draw_Character( x + i * 8, y, str.charCodeAt( i ) );

}

/*
==================
Sbar_DeathmatchOverlay
==================
*/
function Sbar_DeathmatchOverlay() {

	if ( _Draw_Character == null || _Draw_Fill == null ) return;

	const pic = _Draw_CachePic != null ? _Draw_CachePic( 'gfx/ranking.lmp' ) : null;
	if ( pic != null ) {

		// M_DrawPic centers on 320x200
		_Draw_Pic( ( ( 320 - pic.width ) / 2 ) + ( ( _vid.width - 320 ) >> 1 ),
			8 + ( ( _vid.height - 200 ) >> 1 ), pic );

	}

	// scores
	Sbar_SortFrags();

	// draw the text
	const l = scoreboardlines;

	const x = 80 + ( ( _vid.width - 320 ) >> 1 );
	let y = 40;
	for ( let i = 0; i < l; i ++ ) {

		const k = fragsort[ i ];
		const s = _cl.scores[ k ];
		if ( s == null || s.name == null || s.name.length === 0 )
			continue;

		// draw background
		let top = s.colors & 0xf0;
		let bottom = ( s.colors & 15 ) << 4;
		top = Sbar_ColorForMap( top );
		bottom = Sbar_ColorForMap( bottom );

		_Draw_Fill( x, y, 40, 4, top );
		_Draw_Fill( x, y + 4, 40, 4, bottom );

		// draw number
		const f = s.frags;
		const num = String( f ).padStart( 3, ' ' );

		_Draw_Character( x + 8, y, num.charCodeAt( 0 ) );
		_Draw_Character( x + 16, y, num.charCodeAt( 1 ) );
		_Draw_Character( x + 24, y, num.charCodeAt( 2 ) );

		if ( k === _cl.viewentity - 1 )
			_Draw_Character( x - 8, y, 12 );

		// draw name
		for ( let j = 0; j < s.name.length; j ++ )
			_Draw_Character( x + 64 + j * 8, y, s.name.charCodeAt( j ) );

		y += 10;

	}

}

/*
==================
Sbar_MiniDeathmatchOverlay
==================
*/
export function Sbar_MiniDeathmatchOverlay() {

	if ( _vid.width < 512 || sb_lines === 0 )
		return;

	if ( _Draw_Character == null || _Draw_Fill == null ) return;

	// scores
	Sbar_SortFrags();

	// draw the text
	const l = scoreboardlines;
	let y = _vid.height - sb_lines;
	const numlines = Math.floor( sb_lines / 8 );
	if ( numlines < 3 )
		return;

	// find us
	let i;
	for ( i = 0; i < scoreboardlines; i ++ ) {

		if ( fragsort[ i ] === _cl.viewentity - 1 )
			break;

	}

	if ( i === scoreboardlines ) // we're not there
		i = 0;
	else // figure out start
		i = i - Math.floor( numlines / 2 );

	if ( i > scoreboardlines - numlines )
		i = scoreboardlines - numlines;
	if ( i < 0 )
		i = 0;

	const x = 324;
	for ( ; i < scoreboardlines && y < _vid.height - 8; i ++ ) {

		const k = fragsort[ i ];
		const s = _cl.scores[ k ];
		if ( s == null || s.name == null || s.name.length === 0 )
			continue;

		// draw background
		let top = s.colors & 0xf0;
		let bottom = ( s.colors & 15 ) << 4;
		top = Sbar_ColorForMap( top );
		bottom = Sbar_ColorForMap( bottom );

		_Draw_Fill( x, y + 1, 40, 3, top );
		_Draw_Fill( x, y + 4, 40, 4, bottom );

		// draw number
		const f = s.frags;
		const num = String( f ).padStart( 3, ' ' );

		_Draw_Character( x + 8, y, num.charCodeAt( 0 ) );
		_Draw_Character( x + 16, y, num.charCodeAt( 1 ) );
		_Draw_Character( x + 24, y, num.charCodeAt( 2 ) );

		if ( k === _cl.viewentity - 1 ) {

			_Draw_Character( x, y, 16 );
			_Draw_Character( x + 32, y, 17 );

		}

		// draw name
		for ( let j = 0; j < s.name.length; j ++ )
			_Draw_Character( x + 48 + j * 8, y, s.name.charCodeAt( j ) );

		y += 8;

	}

}

/*
==================
Sbar_IntermissionNumber

Draw large numbers for intermission screen
==================
*/
function Sbar_IntermissionNumber( x, y, num, digits, color ) {

	if ( ! _Draw_TransPic ) return;

	const str = String( Math.abs( num ) );
	let ptr = 0;

	if ( str.length > digits )
		ptr = str.length - digits;
	if ( str.length < digits )
		x += ( digits - str.length ) * 24;

	for ( let i = ptr; i < str.length; i ++ ) {

		const c = str.charCodeAt( i );
		let frame;
		if ( c === 45 ) // '-'
			frame = STAT_MINUS;
		else
			frame = c - 48; // '0' is 48

		if ( sb_nums[ color ] && sb_nums[ color ][ frame ] )
			_Draw_TransPic( x, y, sb_nums[ color ][ frame ] );
		x += 24;

	}

}

/*
==================
Sbar_IntermissionOverlay
==================
*/
export function Sbar_IntermissionOverlay() {

	if ( ! _Draw_TransPic || ! _Draw_CachePic ) return;

	if ( _cl.gametype === GAME_DEATHMATCH ) {

		Sbar_DeathmatchOverlay();
		return;

	}

	const pic_complete = _Draw_CachePic( 'gfx/complete.lmp' );
	if ( pic_complete )
		_Draw_Pic( 64, 24, pic_complete );

	const pic_inter = _Draw_CachePic( 'gfx/inter.lmp' );
	if ( pic_inter )
		_Draw_TransPic( 0, 56, pic_inter );

	// time
	const dig = Math.floor( _cl.completed_time / 60 );
	Sbar_IntermissionNumber( 160, 64, dig, 3, 0 );
	const num = Math.floor( _cl.completed_time ) - dig * 60;
	if ( sb_colon )
		_Draw_TransPic( 234, 64, sb_colon );
	if ( sb_nums[ 0 ][ Math.floor( num / 10 ) ] )
		_Draw_TransPic( 246, 64, sb_nums[ 0 ][ Math.floor( num / 10 ) ] );
	if ( sb_nums[ 0 ][ num % 10 ] )
		_Draw_TransPic( 266, 64, sb_nums[ 0 ][ num % 10 ] );

	// secrets
	Sbar_IntermissionNumber( 160, 104, _cl.stats[ STAT_SECRETS ], 3, 0 );
	if ( sb_slash )
		_Draw_TransPic( 232, 104, sb_slash );
	Sbar_IntermissionNumber( 240, 104, _cl.stats[ STAT_TOTALSECRETS ], 3, 0 );

	// kills
	Sbar_IntermissionNumber( 160, 144, _cl.stats[ STAT_MONSTERS ], 3, 0 );
	if ( sb_slash )
		_Draw_TransPic( 232, 144, sb_slash );
	Sbar_IntermissionNumber( 240, 144, _cl.stats[ STAT_TOTALMONSTERS ], 3, 0 );

}

/*
==================
Sbar_FinaleOverlay
==================
*/
export function Sbar_FinaleOverlay() {

	if ( ! _Draw_TransPic || ! _Draw_CachePic ) return;

	const pic = _Draw_CachePic( 'gfx/finale.lmp' );
	if ( pic )
		_Draw_TransPic( ( _vid.width - pic.width ) / 2, 16, pic );

}
