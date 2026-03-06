// Ported from: WinQuake/sys.h + sys_win.c -- system interface (browser)

/*
===============================================================================

SYSTEM IO

===============================================================================
*/

export function Sys_Init() {

	console.log( 'Three-Quake initializing...' );

}

export function Sys_Error( error ) {

	console.error( 'Sys_Error: ' + error );

	// Display error on screen (browser only)
	if ( typeof document !== 'undefined' ) {

		document.body.innerHTML = '<pre style="color:red;padding:20px;font-size:16px;">Sys_Error: ' + error + '</pre>';

	}

	throw new Error( error );

}

const _quietLogAllowPatterns = [
	/^Connection from /,
	/^Connection closed:/,
	/^Client .*(connected|removed)\b/,
	/^Spawning server for map:/,
	/^SpawnServer:/,
	/^Server initialized!/,
	/^Room .* idle for /,
	/^Host_ServerFrame error:/,
	/^SV_ReadClientMessage:/,
	/^Unhandled promise rejection:/,
	/^WebTransport server listening /,
	/^WebTransport server driver initialized/,
	/^NET_Init complete/
];

function _isDenoRuntime() {

	return typeof Deno !== 'undefined' && Deno.version != null;

}

function _formatPrintf( fmt, args ) {

	if ( args.length === 0 ) return String( fmt );

	let result = String( fmt );
	let index = 0;
	result = result.replace( /%[sdif]/g, () => {

		if ( index >= args.length ) return '';
		return String( args[ index ++ ] );

	} );

	if ( index < args.length ) {

		result += ' ' + args.slice( index ).map( String ).join( ' ' );

	}

	return result;

}

function _shouldPrintLine( line ) {

	if ( _isDenoRuntime() !== true ) return true;

	const quietLogs = globalThis.__THREE_QUAKE_QUIET_LOGS === true;
	if ( quietLogs !== true ) return true;

	const trimmed = line.trim();
	if ( trimmed.length === 0 ) return false;

	for ( const pattern of _quietLogAllowPatterns ) {

		if ( pattern.test( trimmed ) ) return true;

	}

	return false;

}

export function Sys_Printf( fmt, ...args ) {

	const line = _formatPrintf( fmt, args );
	if ( _shouldPrintLine( line ) !== true ) return;
	console.log( line );

}

export function Sys_Quit() {

	console.log( 'Sys_Quit' );

}

export function Sys_FloatTime() {

	return performance.now() / 1000.0;

}

export function Sys_DoubleTime() {

	return performance.now() / 1000.0;

}
