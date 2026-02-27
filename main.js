// Three-Quake entry point
// Equivalent to WinQuake/sys_win.c WinMain() + main()

import { Sys_Init, Sys_Printf, Sys_Error } from './src/sys.js';
import { COM_InitArgv } from './src/common.js';
import { Host_Init, Host_Frame, Host_Shutdown } from './src/host.js';
import { COM_FetchPak, COM_AddPack } from './src/pak.js';
import { Cbuf_AddText } from './src/cmd.js';
import { cls, cl } from './src/client.js';
import { sv } from './src/server.js';
import { scene, camera } from './src/gl_rmain.js';
import { renderer } from './src/vid.js';
import { Draw_CachePicFromPNG } from './src/gl_draw.js';
import { XR_Init } from './src/webxr.js';

const parms = {
	basedir: '.',
	argc: 0,
	argv: []
};

async function main() {

	try {

		Sys_Init();

		COM_InitArgv( parms.argv );

		// Loading bar
		const loadingProgress = document.getElementById( 'loading-progress' );
		const loadingOverlay = document.getElementById( 'loading' );

		function setProgress( value ) {

			if ( loadingProgress ) {

				loadingProgress.style.width = ( value * 100 ) + '%';

			}

		}

		// Load pak0.pak from the same directory
		Sys_Printf( 'Loading pak0.pak...\\n' );
		const pak0 = await COM_FetchPak( 'pak0.pak', 'pak0.pak', setProgress );
		if ( pak0 ) {

			COM_AddPack( pak0 );
			Sys_Printf( 'pak0.pak loaded successfully\\n' );

		} else {

			Sys_Printf( 'Warning: pak0.pak not found - game data will be missing\\n' );

		}

		await Host_Init( parms );

		// Remove loading overlay
		if ( loadingOverlay ) {

			loadingOverlay.remove();

		}

		// Preload custom menu images
		try {

			await Draw_CachePicFromPNG( 'gfx/mainmenu_ext.lmp', 'mainmenu.png' );
			Sys_Printf( 'Loaded custom menu images\\n' );

		} catch ( e ) {

			Sys_Printf( 'Warning: Could not load custom menu images\\n' );

		}

		// Check URL parameters for auto-join
		const urlParams = new URLSearchParams( window.location.search );
		const roomId = urlParams.get( 'room' );

		if ( roomId ) {

			const serverUrl = urlParams.get( 'server' ) || 'https://wts.mrdoob.com:4433';
			const connectUrl = serverUrl + '?room=' + encodeURIComponent( roomId );
			Sys_Printf( 'Auto-joining room: %s\\n', roomId );
			Cbuf_AddText( 'connect "' + connectUrl + '"\n' );

		}

		// Initialize WebXR (creates rig, offers VR session — must be after Host_Init)
		XR_Init( scene );

		// Expose for debugging
		window.Cbuf_AddText = Cbuf_AddText;
		window.cls = cls;
		window.cl = cl;
		window.sv = sv;
		window.scene = scene;
		Object.defineProperty( window, 'camera', { get: () => camera } );
		Object.defineProperty( window, 'renderer', { get: () => renderer } );

		let oldtime = performance.now() / 1000;

		// Use renderer.setAnimationLoop instead of requestAnimationFrame.
		// This is required for WebXR — Three.js automatically switches to
		// xrSession.requestAnimationFrame when a VR session is active.
		// In non-XR mode, behavior is identical to regular rAF.
		renderer.setAnimationLoop( function ( timestamp ) {

			const newtime = timestamp / 1000;
			const time = newtime - oldtime;
			oldtime = newtime;

			Host_Frame( time );

		} );

	} catch ( e ) {

		console.error( 'Three-Quake Fatal Error:', e );
		Sys_Error( e.message );

	}

}

main();
