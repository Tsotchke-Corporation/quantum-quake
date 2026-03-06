// Ported from: WinQuake/net.h -- quake's interface to the networking layer

import { MAX_DATAGRAM } from './quakedef.js';
import { sizebuf_t } from './common.js';

//============================================================================
// Network constants
//============================================================================

export const NET_NAMELEN = 64;

export const NET_MAXMESSAGE = 8192;
export const NET_HEADERSIZE = ( 2 * 4 ); // 2 * sizeof(unsigned int)
export const NET_DATAGRAMSIZE = ( MAX_DATAGRAM + NET_HEADERSIZE );

// NetHeader flags
export const NETFLAG_LENGTH_MASK = 0x0000ffff;
export const NETFLAG_DATA = 0x00010000;
export const NETFLAG_ACK = 0x00020000;
export const NETFLAG_NAK = 0x00040000;
export const NETFLAG_EOM = 0x00080000;
export const NETFLAG_UNRELIABLE = 0x00100000;
export const NETFLAG_CTL = 0x80000000;

export const NET_PROTOCOL_VERSION = 3;

// Connection request types
export const CCREQ_CONNECT = 0x01;
export const CCREQ_SERVER_INFO = 0x02;
export const CCREQ_PLAYER_INFO = 0x03;
export const CCREQ_RULE_INFO = 0x04;

// Connection reply types
export const CCREP_ACCEPT = 0x81;
export const CCREP_REJECT = 0x82;
export const CCREP_SERVER_INFO = 0x83;
export const CCREP_PLAYER_INFO = 0x84;
export const CCREP_RULE_INFO = 0x85;

export const HOSTCACHESIZE = 8;

export const MAX_NET_DRIVERS = 8;

//============================================================================
// qsocket_t - network socket structure
//============================================================================

export class qsocket_t {

	constructor() {

		this.next = null;
		this.connecttime = 0;
		this.lastMessageTime = 0;
		this.lastSendTime = 0;

		this.disconnected = false;
		this.canSend = false;
		this.sendNext = false;

		this.driver = 0;
		this.landriver = 0;
		this.socket = 0;
		this.driverdata = null;

		this.ackSequence = 0;
		this.sendSequence = 0;
		this.unreliableSendSequence = 0;
		this.sendMessageLength = 0;
		this.sendMessage = new Uint8Array( NET_MAXMESSAGE );

		this.receiveSequence = 0;
		this.unreliableReceiveSequence = 0;
		this.receiveMessageLength = 0;
		this.receiveMessage = new Uint8Array( NET_MAXMESSAGE );

		this.addr = null;
		this.address = '';

	}

}

//============================================================================
// net_landriver_t - low-level network driver interface
//============================================================================

export class net_landriver_t {

	constructor() {

		this.name = '';
		this.initialized = false;
		this.controlSock = 0;
		this.Init = null;
		this.Shutdown = null;
		this.Listen = null;
		this.OpenSocket = null;
		this.CloseSocket = null;
		this.Connect = null;
		this.CheckNewConnections = null;
		this.Read = null;
		this.Write = null;
		this.Broadcast = null;
		this.AddrToString = null;
		this.StringToAddr = null;
		this.GetSocketAddr = null;
		this.GetNameFromAddr = null;
		this.GetAddrFromName = null;
		this.AddrCompare = null;
		this.GetSocketPort = null;
		this.SetSocketPort = null;

	}

}

//============================================================================
// net_driver_t - high-level network driver interface
//============================================================================

export class net_driver_t {

	constructor() {

		this.name = '';
		this.initialized = false;
		this.Init = null;
		this.Listen = null;
		this.SearchForHosts = null;
		this.Connect = null;
		this.CheckNewConnections = null;
		this.QGetMessage = null;
		this.QSendMessage = null;
		this.SendUnreliableMessage = null;
		this.CanSendMessage = null;
		this.CanSendUnreliableMessage = null;
		this.Close = null;
		this.Shutdown = null;
		this.controlSock = 0;

	}

}

//============================================================================
// hostcache_t - server browser cache entry
//============================================================================

export class hostcache_t {

	constructor() {

		this.name = '';
		this.map = '';
		this.cname = '';
		this.users = 0;
		this.maxusers = 0;
		this.driver = 0;
		this.ldriver = 0;
		this.addr = null;

	}

}

//============================================================================
// PollProcedure - for scheduled network polling
//============================================================================

export class PollProcedure {

	constructor( next, nextTime, procedure, arg ) {

		this.next = next || null;
		this.nextTime = nextTime || 0;
		this.procedure = procedure || null;
		this.arg = arg || null;

	}

}

//============================================================================
// Network globals
//============================================================================

export let net_activeSockets = null;
export let net_freeSockets = null;
export let net_numsockets = 0;

export function set_net_activeSockets( v ) { net_activeSockets = v; }
export function set_net_freeSockets( v ) { net_freeSockets = v; }
export function set_net_numsockets( v ) { net_numsockets = v; }

export let net_numdrivers = 0;
export const net_drivers = new Array( MAX_NET_DRIVERS );
for ( let i = 0; i < MAX_NET_DRIVERS; i ++ )
	net_drivers[ i ] = new net_driver_t();

export let net_numlandrivers = 0;
export const net_landrivers = new Array( MAX_NET_DRIVERS );
for ( let i = 0; i < MAX_NET_DRIVERS; i ++ )
	net_landrivers[ i ] = new net_landriver_t();

export let DEFAULTnet_hostport = 26000;
export let net_hostport = 26000;

export function set_DEFAULTnet_hostport( v ) { DEFAULTnet_hostport = v; }
export function set_net_hostport( v ) { net_hostport = v; }

export let net_driverlevel = 0;
export function set_net_driverlevel( v ) { net_driverlevel = v; }

export function set_net_numdrivers( v ) { net_numdrivers = v; }

export let serialAvailable = false;
export let ipxAvailable = false;
export let tcpipAvailable = false;

export let my_ipx_address = '';
export let my_tcpip_address = '';

export let net_time = 0;
export function set_net_time( v ) { net_time = v; }

export const net_message = new sizebuf_t();
export let net_activeconnections = 0;
export function set_net_activeconnections( v ) { net_activeconnections = v; }

export let messagesSent = 0;
export let messagesReceived = 0;
export let unreliableMessagesSent = 0;
export let unreliableMessagesReceived = 0;

export let hostCacheCount = 0;
export function set_hostCacheCount( v ) { hostCacheCount = v; }

export const hostcache = new Array( HOSTCACHESIZE );
for ( let i = 0; i < HOSTCACHESIZE; i ++ )
	hostcache[ i ] = new hostcache_t();

export let slistInProgress = false;
export let slistSilent = false;
export let slistLocal = true;

export function set_slistInProgress( v ) { slistInProgress = v; }
export function set_slistSilent( v ) { slistSilent = v; }
export function set_slistLocal( v ) { slistLocal = v; }
