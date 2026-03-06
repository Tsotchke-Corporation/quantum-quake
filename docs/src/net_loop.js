// Ported from: WinQuake/net_loop.c + net_loop.h -- loopback network driver

import { Con_Printf, SZ_Clear, SZ_Write } from './common.js';
import { Sys_Error } from './sys.js';
import {
	NET_MAXMESSAGE,
	net_message,
	qsocket_t,
	net_activeconnections,
	net_driverlevel,
	hostCacheCount, set_hostCacheCount,
	hostcache
} from './net.js';
import { NET_NewQSocket, hostname } from './net_main.js';
import { sv } from './server.js';
import { svs } from './server.js';

let localconnectpending = false;
let loop_client = null;
let loop_server = null;

/*
=============
Loop_Init
=============
*/
export function Loop_Init() {

	// In browser, we always support loopback (not dedicated)
	return 0;

}

/*
=============
Loop_Shutdown
=============
*/
export function Loop_Shutdown() {

}

/*
=============
Loop_Listen
=============
*/
export function Loop_Listen( state ) {

}

/*
=============
Loop_SearchForHosts
=============
*/
export function Loop_SearchForHosts( xmit ) {

	if ( ! sv.active )
		return;

	set_hostCacheCount( 1 );
	if ( hostname.string === 'UNNAMED' )
		hostcache[ 0 ].name = 'local';
	else
		hostcache[ 0 ].name = hostname.string;
	hostcache[ 0 ].map = sv.name;
	hostcache[ 0 ].users = net_activeconnections;
	hostcache[ 0 ].maxusers = svs.maxclients;
	hostcache[ 0 ].driver = net_driverlevel;
	hostcache[ 0 ].cname = 'local';

}

/*
=============
Loop_Connect
=============
*/
export function Loop_Connect( host ) {

	if ( host !== 'local' )
		return null;

	localconnectpending = true;

	if ( ! loop_client ) {

		loop_client = NET_NewQSocket();
		if ( loop_client === null ) {

			Con_Printf( 'Loop_Connect: no qsocket available\n' );
			return null;

		}

		loop_client.address = 'localhost';

	}

	loop_client.receiveMessageLength = 0;
	loop_client.sendMessageLength = 0;
	loop_client.canSend = true;

	if ( ! loop_server ) {

		loop_server = NET_NewQSocket();
		if ( loop_server === null ) {

			Con_Printf( 'Loop_Connect: no qsocket available\n' );
			return null;

		}

		loop_server.address = 'LOCAL';

	}

	loop_server.receiveMessageLength = 0;
	loop_server.sendMessageLength = 0;
	loop_server.canSend = true;

	loop_client.driverdata = loop_server;
	loop_server.driverdata = loop_client;

	return loop_client;

}

/*
=============
Loop_CheckNewConnections
=============
*/
export function Loop_CheckNewConnections() {

	if ( ! localconnectpending )
		return null;

	localconnectpending = false;
	loop_server.sendMessageLength = 0;
	loop_server.receiveMessageLength = 0;
	loop_server.canSend = true;
	loop_client.sendMessageLength = 0;
	loop_client.receiveMessageLength = 0;
	loop_client.canSend = true;
	return loop_server;

}

/*
=============
IntAlign
=============
*/
function IntAlign( value ) {

	return ( value + ( 4 - 1 ) ) & ( ~ ( 4 - 1 ) ); // sizeof(int) = 4

}

/*
=============
Loop_GetMessage
=============
*/
export function Loop_GetMessage( sock ) {

	if ( sock.receiveMessageLength === 0 )
		return 0;

	const ret = sock.receiveMessage[ 0 ];
	const length = sock.receiveMessage[ 1 ] + ( sock.receiveMessage[ 2 ] << 8 );
	// alignment byte skipped here
	SZ_Clear( net_message );
	SZ_Write( net_message, sock.receiveMessage.subarray( 4, 4 + length ), length );

	const alignedLength = IntAlign( length + 4 );
	sock.receiveMessageLength -= alignedLength;

	if ( sock.receiveMessageLength > 0 ) {

		// shift remaining data down
		sock.receiveMessage.copyWithin( 0, alignedLength, alignedLength + sock.receiveMessageLength );

	}

	if ( sock.driverdata != null && ret === 1 )
		sock.driverdata.canSend = true;

	return ret;

}

/*
=============
Loop_SendMessage
=============
*/
export function Loop_SendMessage( sock, data ) {

	if ( ! sock.driverdata )
		return - 1;

	const peer = sock.driverdata;
	const bufferLength = peer.receiveMessageLength;

	if ( ( bufferLength + data.cursize + 4 ) > NET_MAXMESSAGE )
		Sys_Error( 'Loop_SendMessage: overflow\n' );

	const offset = bufferLength;

	// message type
	peer.receiveMessage[ offset ] = 1;

	// length
	peer.receiveMessage[ offset + 1 ] = data.cursize & 0xff;
	peer.receiveMessage[ offset + 2 ] = data.cursize >> 8;

	// align
	// peer.receiveMessage[ offset + 3 ] is alignment padding

	// message
	for ( let i = 0; i < data.cursize; i ++ )
		peer.receiveMessage[ offset + 4 + i ] = data.data[ i ];

	peer.receiveMessageLength = IntAlign( bufferLength + data.cursize + 4 );

	sock.canSend = false;
	return 1;

}

/*
=============
Loop_SendUnreliableMessage
=============
*/
export function Loop_SendUnreliableMessage( sock, data ) {

	if ( ! sock.driverdata )
		return - 1;

	const peer = sock.driverdata;
	const bufferLength = peer.receiveMessageLength;

	if ( ( bufferLength + data.cursize + 4 ) > NET_MAXMESSAGE )
		return 0;

	const offset = bufferLength;

	// message type
	peer.receiveMessage[ offset ] = 2;

	// length
	peer.receiveMessage[ offset + 1 ] = data.cursize & 0xff;
	peer.receiveMessage[ offset + 2 ] = data.cursize >> 8;

	// align
	// peer.receiveMessage[ offset + 3 ] is alignment padding

	// message
	for ( let i = 0; i < data.cursize; i ++ )
		peer.receiveMessage[ offset + 4 + i ] = data.data[ i ];

	peer.receiveMessageLength = IntAlign( bufferLength + data.cursize + 4 );
	return 1;

}

/*
=============
Loop_CanSendMessage
=============
*/
export function Loop_CanSendMessage( sock ) {

	if ( ! sock.driverdata )
		return false;
	return sock.canSend;

}

/*
=============
Loop_CanSendUnreliableMessage
=============
*/
export function Loop_CanSendUnreliableMessage( sock ) {

	return true;

}

/*
=============
Loop_Close
=============
*/
export function Loop_Close( sock ) {

	if ( sock.driverdata != null )
		sock.driverdata.driverdata = null;

	sock.receiveMessageLength = 0;
	sock.sendMessageLength = 0;
	sock.canSend = true;
	if ( sock === loop_client )
		loop_client = null;
	else
		loop_server = null;

}
