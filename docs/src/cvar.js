// Ported from: WinQuake/cvar.c -- dynamic variable tracking

/*

cvar_t variables are used to hold scalar or string variables that can be
changed or displayed at the console or prog code as well as accessed directly
in C code.

it is sufficient to initialize a cvar_t with just the first two fields, or
you can add a ,true flag for variables that you want saved to the configuration
file when the game is quit:

Cvars must be registered before use, or they will have a 0 value instead of
the float interpretation of the string. Generally, all cvar_t declarations
should be registered in the appropriate init function before any console
commands are executed:
Cvar_RegisterVariable(host_framerate);

*/

import { Con_Printf, Q_atof } from './common.js';
import { Cmd_Exists, Cmd_Argc, Cmd_Argv } from './cmd.js';

// Callback for broadcasting server cvar changes (injected to avoid circular deps)
let _serverBroadcast = null;

export function Cvar_SetServerBroadcast( fn ) {

	_serverBroadcast = fn;

}

// localStorage key prefix for saved cvars
const CVAR_STORAGE_PREFIX = 'quake_cvar_';

// Save a cvar to localStorage
function Cvar_SaveToStorage( _var ) {

	if ( typeof localStorage === 'undefined' ) return;

	try {

		localStorage.setItem( CVAR_STORAGE_PREFIX + _var.name, _var.string );

	} catch ( e ) {

		// localStorage might be full or disabled
		Con_Printf( 'Warning: Could not save cvar ' + _var.name + ' to localStorage\n' );

	}

}

// Load a cvar from localStorage (returns null if not found)
function Cvar_LoadFromStorage( name ) {

	if ( typeof localStorage === 'undefined' ) return null;

	try {

		return localStorage.getItem( CVAR_STORAGE_PREFIX + name );

	} catch ( e ) {

		return null;

	}

}

export class cvar_t {

	constructor( name, string, archive, server ) {

		this.name = name;
		this.string = string || '';
		this.archive = archive || false; // set to true to cause it to be saved to vars.rc
		this.server = server || false; // notifies players when changed
		this.value = Q_atof( this.string );
		this.next = null;

	}

}

let cvar_vars = null;

/*
============
Cvar_FindVar
============
*/
export function Cvar_FindVar( var_name ) {

	let _var = cvar_vars;
	while ( _var ) {

		if ( _var.name === var_name )
			return _var;
		_var = _var.next;

	}

	return null;

}

/*
============
Cvar_VariableValue
============
*/
export function Cvar_VariableValue( var_name ) {

	const _var = Cvar_FindVar( var_name );
	if ( ! _var )
		return 0;
	return Q_atof( _var.string );

}

/*
============
Cvar_VariableString
============
*/
export function Cvar_VariableString( var_name ) {

	const _var = Cvar_FindVar( var_name );
	if ( ! _var )
		return '';
	return _var.string;

}

/*
============
Cvar_CompleteVariable
============
*/
export function Cvar_CompleteVariable( partial ) {

	const len = partial.length;

	if ( len === 0 )
		return null;

	// check functions
	let _var = cvar_vars;
	while ( _var ) {

		if ( _var.name.substring( 0, len ) === partial )
			return _var.name;
		_var = _var.next;

	}

	return null;

}

/*
============
Cvar_Set
============
*/
export function Cvar_Set( var_name, value ) {

	const _var = Cvar_FindVar( var_name );
	if ( ! _var ) {

		// there is an error in C code if this happens
		Con_Printf( 'Cvar_Set: variable ' + var_name + ' not found\n' );
		return;

	}

	const changed = ( _var.string !== value );

	_var.string = value;
	_var.value = Q_atof( _var.string );

	if ( _var.server && changed ) {

		if ( _serverBroadcast != null ) {

			_serverBroadcast( '"' + _var.name + '" changed to "' + _var.string + '"\n' );

		}

	}

	// Save to localStorage if this cvar should be archived
	if ( _var.archive && changed ) {

		Cvar_SaveToStorage( _var );

	}

}

/*
============
Cvar_SetValue
============
*/
export function Cvar_SetValue( var_name, value ) {

	// Match original Quake behavior (va("%f", value)) and avoid scientific
	// notation strings that Q_atof cannot parse correctly.
	if ( Number.isFinite( value ) === true ) {

		Cvar_Set( var_name, value.toFixed( 6 ) );
		return;

	}

	Cvar_Set( var_name, String( value ) );

}

/*
============
Cvar_RegisterVariable

Adds a freestanding variable to the variable list.
============
*/
export function Cvar_RegisterVariable( variable ) {

	// first check to see if it has already been defined
	if ( Cvar_FindVar( variable.name ) ) {

		Con_Printf( 'Can\'t register variable ' + variable.name + ', already defined\n' );
		return;

	}

	// check for overlap with a command
	if ( Cmd_Exists( variable.name ) ) {

		Con_Printf( 'Cvar_RegisterVariable: ' + variable.name + ' is a command\n' );
		return;

	}

	// Check for saved value in localStorage (for archived cvars)
	if ( variable.archive ) {

		const savedValue = Cvar_LoadFromStorage( variable.name );
		if ( savedValue !== null ) {

			variable.string = savedValue;

		}

	}

	// parse the value
	variable.value = Q_atof( variable.string );

	// link the variable in
	variable.next = cvar_vars;
	cvar_vars = variable;

}

/*
============
Cvar_Command

Handles variable inspection and changing from the console
============
*/
export function Cvar_Command() {

	const v = Cvar_FindVar( Cmd_Argv( 0 ) );
	if ( ! v )
		return false;

	// perform a variable print or set
	if ( Cmd_Argc() === 1 ) {

		Con_Printf( '"' + v.name + '" is "' + v.string + '"\n' );
		return true;

	}

	Cvar_Set( v.name, Cmd_Argv( 1 ) );
	return true;

}

/*
============
Cvar_WriteVariables

Writes lines containing "set variable value" for all variables
with the archive flag set to true.
============
*/
export function Cvar_WriteVariables() {

	const lines = [];
	let _var = cvar_vars;
	while ( _var ) {

		if ( _var.archive )
			lines.push( _var.name + ' "' + _var.string + '"\n' );
		_var = _var.next;

	}

	return lines.join( '' );

}
