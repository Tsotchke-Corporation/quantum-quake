// Touch controls for mobile devices
// Provides virtual joystick on left, look area on right with tap-to-jump

import { K_ESCAPE, Key_Event } from './keys.js';
import { in_attack, in_jump } from './cl_input.js';
import { S_UnlockAudio } from './snd_dma.js';

// Touch state
let enabled = false;
let initialized = false;
let menuOverlay = null;
let menuTouchCallback = null;
let fullscreenActivated = false;
let wakeLock = null;

// Movement joystick (left side)
let moveTouch = null;
let joystickOrigin = { x: 0, y: 0 };
let joystickCurrent = { x: 0, y: 0 };

// Look area (right side)
let lookTouch = null;
let lastLookPos = { x: 0, y: 0 };
let lookTouchOrigin = { x: 0, y: 0 };
let lookTouchDist = 0;

// Accumulated values for IN_Move
let moveForward = 0;
let moveRight = 0;
let lookDeltaX = 0;
let lookDeltaY = 0;
let jumpImpulse = false;

// Gyroscope state
let gyroEnabled = false;
let gyroPermissionRequested = false;
let prevBeta = null;
let prevGamma = null;
const GYRO_SENSITIVITY = 8.0;
const LOOK_SENSITIVITY = 3.0;

// UI elements
let overlay = null;
let joystickArea = null;
let joystickBase = null;
let joystickKnob = null;
let lookArea = null;
let fireButton = null;
let jumpButton = null;
let pauseButton = null;

/*
=================
Touch_IsMobile

Detect if we're on a mobile device
=================
*/
export function Touch_IsMobile() {

	return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test( navigator.userAgent ) ||
		( navigator.maxTouchPoints && navigator.maxTouchPoints > 2 );

}

/*
=================
Touch_CreateUI

Create the touch control UI elements
=================
*/
function Touch_CreateUI( container ) {

	// Main overlay
	overlay = document.createElement( 'div' );
	overlay.id = 'touch-controls';
	overlay.style.cssText = `
		position: fixed;
		top: 0;
		left: 0;
		width: 100%;
		height: 100%;
		pointer-events: none;
		z-index: 200;
		display: none;
		touch-action: none;
	`;

	// Left side - movement joystick area
	joystickArea = document.createElement( 'div' );
	joystickArea.style.cssText = `
		position: absolute;
		left: 0;
		top: 0;
		width: 40%;
		height: 100%;
		pointer-events: auto;
		touch-action: none;
	`;

	// Joystick base (appears when touching)
	joystickBase = document.createElement( 'div' );
	joystickBase.style.cssText = `
		position: fixed;
		width: 120px;
		height: 120px;
		border-radius: 50%;
		background: rgba(255, 255, 255, 0.15);
		border: 2px solid rgba(255, 255, 255, 0.3);
		display: none;
		transform: translate(-50%, -50%);
		pointer-events: none;
	`;

	// Joystick knob
	joystickKnob = document.createElement( 'div' );
	joystickKnob.style.cssText = `
		position: absolute;
		width: 50px;
		height: 50px;
		border-radius: 50%;
		background: rgba(255, 255, 255, 0.4);
		border: 2px solid rgba(255, 255, 255, 0.6);
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
	`;
	joystickBase.appendChild( joystickKnob );
	joystickArea.appendChild( joystickBase );

	// Right side - look area (tap to jump, drag to look)
	lookArea = document.createElement( 'div' );
	lookArea.style.cssText = `
		position: absolute;
		right: 0;
		top: 0;
		width: 60%;
		height: 100%;
		pointer-events: auto;
		touch-action: none;
	`;

	// Fire button (top right)
	fireButton = document.createElement( 'div' );
	fireButton.style.cssText = `
		position: absolute;
		right: 60px;
		top: 50px;
		width: 100px;
		height: 100px;
		border-radius: 50%;
		background: transparent;
		border: 2px solid rgba(255, 100, 100, 0.5);
		pointer-events: auto;
		touch-action: none;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: sans-serif;
		font-size: 14px;
		color: rgba(255, 255, 255, 0.7);
	`;
	fireButton.textContent = 'FIRE';

	// Jump button (below fire button)
	jumpButton = document.createElement( 'div' );
	jumpButton.style.cssText = `
		position: absolute;
		right: 60px;
		top: 170px;
		width: 100px;
		height: 100px;
		border-radius: 50%;
		background: transparent;
		border: 2px solid rgba(100, 150, 255, 0.5);
		pointer-events: auto;
		touch-action: none;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: sans-serif;
		font-size: 14px;
		color: rgba(255, 255, 255, 0.7);
	`;
	jumpButton.textContent = 'JUMP';

	// Pause button (bottom right corner)
	pauseButton = document.createElement( 'div' );
	pauseButton.style.cssText = `
		position: absolute;
		right: 20px;
		bottom: 20px;
		width: 40px;
		height: 40px;
		border-radius: 5px;
		background: rgba(255, 255, 255, 0.15);
		border: 1px solid rgba(255, 255, 255, 0.3);
		pointer-events: auto;
		touch-action: none;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: sans-serif;
		font-size: 16px;
		color: rgba(255, 255, 255, 0.7);
	`;
	pauseButton.textContent = '| |';

	// Assemble UI
	overlay.appendChild( joystickArea );
	overlay.appendChild( lookArea );
	overlay.appendChild( fireButton );
	overlay.appendChild( jumpButton );
	overlay.appendChild( pauseButton );

	container.appendChild( overlay );

	// Create menu navigation overlay
	Touch_CreateMenuUI( container );

}

/*
=================
Touch_CreateMenuUI

Create fullscreen touch area for menu tap-to-select
=================
*/
function Touch_CreateMenuUI( container ) {

	menuOverlay = document.createElement( 'div' );
	menuOverlay.id = 'touch-menu-controls';
	menuOverlay.style.cssText = `
		position: fixed;
		top: 0;
		left: 0;
		width: 100%;
		height: 100%;
		display: none;
		z-index: 199;
		pointer-events: auto;
		touch-action: none;
	`;

	menuOverlay.addEventListener( 'touchstart', ( e ) => {

		e.preventDefault();

		// Unlock audio on first user gesture
		S_UnlockAudio();

		if ( e.touches.length > 0 ) {

			const touch = e.touches[ 0 ];
			const x = touch.clientX;
			const y = touch.clientY;

			// Call the menu touch handler if set
			if ( menuTouchCallback ) {

				menuTouchCallback( x, y, window.innerWidth, window.innerHeight );

			}

		}

	}, { passive: false } );

	container.appendChild( menuOverlay );

}

/*
=================
Touch event handlers
=================
*/

function onTouchStart( e ) {

	e.preventDefault();

	// Unlock audio on first user gesture
	S_UnlockAudio();

	// Request gyroscope permission on first touch (needs user gesture)
	if ( ! gyroPermissionRequested ) {

		Gyro_RequestPermission();

	}

	for ( const touch of e.changedTouches ) {

		const target = e.currentTarget;

		if ( target === joystickArea && moveTouch === null ) {

			// Start joystick
			moveTouch = touch.identifier;
			joystickOrigin.x = touch.clientX;
			joystickOrigin.y = touch.clientY;
			joystickCurrent.x = touch.clientX;
			joystickCurrent.y = touch.clientY;

			// Show joystick at touch position
			joystickBase.style.display = 'block';
			joystickBase.style.left = touch.clientX + 'px';
			joystickBase.style.top = touch.clientY + 'px';

		} else if ( target === lookArea && lookTouch === null ) {

			// Start look (also tracks tap for jump)
			lookTouch = touch.identifier;
			lastLookPos.x = touch.clientX;
			lastLookPos.y = touch.clientY;
			lookTouchOrigin.x = touch.clientX;
			lookTouchOrigin.y = touch.clientY;
			lookTouchDist = 0;

		} else if ( target === fireButton ) {

			in_attack.state |= 1 + 2; // down + impulse down
			fireButton.style.background = 'rgba(255, 100, 100, 0.2)';
			if ( typeof navigator.vibrate === 'function' ) navigator.vibrate( 100 );

		} else if ( target === jumpButton ) {

			in_jump.state |= 1 + 2; // down + impulse down
			jumpButton.style.background = 'rgba(100, 150, 255, 0.2)';
			if ( typeof navigator.vibrate === 'function' ) navigator.vibrate( 100 );

		} else if ( target === pauseButton ) {

			// Trigger escape key
			Key_Event( K_ESCAPE, true );
			Key_Event( K_ESCAPE, false );

		}

	}

}

function onTouchMove( e ) {

	e.preventDefault();

	for ( const touch of e.changedTouches ) {

		if ( touch.identifier === moveTouch ) {

			// Update joystick
			joystickCurrent.x = touch.clientX;
			joystickCurrent.y = touch.clientY;

			// Calculate offset from origin
			const dx = joystickCurrent.x - joystickOrigin.x;
			const dy = joystickCurrent.y - joystickOrigin.y;

			// Clamp to max radius
			const maxRadius = 50;
			const dist = Math.sqrt( dx * dx + dy * dy );
			let clampedX = dx;
			let clampedY = dy;

			if ( dist > maxRadius ) {

				clampedX = ( dx / dist ) * maxRadius;
				clampedY = ( dy / dist ) * maxRadius;

			}

			// Update knob position
			joystickKnob.style.left = `calc(50% + ${clampedX}px)`;
			joystickKnob.style.top = `calc(50% + ${clampedY}px)`;

			// Convert to normalized input (-1 to 1)
			// Note: Y is inverted (up = forward = positive)
			moveRight = clampedX / maxRadius;
			moveForward = - clampedY / maxRadius;

		} else if ( touch.identifier === lookTouch ) {

			// Calculate look delta
			const dx = touch.clientX - lastLookPos.x;
			const dy = touch.clientY - lastLookPos.y;

			lookDeltaX += dx * LOOK_SENSITIVITY;
			lookDeltaY += dy * LOOK_SENSITIVITY;

			lastLookPos.x = touch.clientX;
			lastLookPos.y = touch.clientY;

			// Track total distance from origin (for tap detection)
			const totalDx = touch.clientX - lookTouchOrigin.x;
			const totalDy = touch.clientY - lookTouchOrigin.y;
			lookTouchDist = Math.sqrt( totalDx * totalDx + totalDy * totalDy );

		}

	}

}

function onTouchEnd( e ) {

	e.preventDefault();

	for ( const touch of e.changedTouches ) {

		const target = e.currentTarget;

		if ( touch.identifier === moveTouch ) {

			// Reset joystick
			moveTouch = null;
			moveForward = 0;
			moveRight = 0;
			joystickBase.style.display = 'none';
			joystickKnob.style.left = '50%';
			joystickKnob.style.top = '50%';

		} else if ( touch.identifier === lookTouch ) {

			lookTouch = null;

		} else if ( target === fireButton ) {

			in_attack.state &= ~1; // up
			in_attack.state |= 4; // impulse up
			fireButton.style.background = 'transparent';

		} else if ( target === jumpButton ) {

			in_jump.state &= ~1; // up
			in_jump.state |= 4; // impulse up
			jumpButton.style.background = 'transparent';

		}

	}

}

/*
=================
Gyroscope support

Uses deviceorientation with delta tracking. In fullscreen landscape:
- beta changes when tilting left/right = yaw
- gamma changes when tilting up/down = pitch
=================
*/

function onDeviceOrientation( e ) {

	if ( ! enabled ) return;

	const beta = e.beta;   // X-axis tilt: -180 to 180
	const gamma = e.gamma; // Y-axis tilt: -90 to 90

	if ( beta === null || gamma === null ) return;

	if ( prevBeta !== null && prevGamma !== null ) {

		let dBeta = beta - prevBeta;
		let dGamma = gamma - prevGamma;

		// Clamp deltas - ignore large jumps from gimbal lock or axis flips
		if ( dBeta > 10 || dBeta < - 10 ) dBeta = 0;
		if ( dGamma > 10 || dGamma < - 10 ) dGamma = 0;

		// deviceorientation reports values relative to the device's physical
		// axes, NOT the screen orientation. We must check the actual screen
		// angle and remap accordingly.
		const angle = ( screen.orientation && screen.orientation.angle !== undefined )
			? screen.orientation.angle
			: ( window.orientation || 0 );

		let dYaw, dPitch;

		if ( angle === 90 ) {

			// Landscape: top of phone is on the left
			dYaw = dBeta;
			dPitch = - dGamma;

		} else if ( angle === - 90 || angle === 270 ) {

			// Landscape: top of phone is on the right
			dYaw = - dBeta;
			dPitch = dGamma;

		} else {

			// Portrait (0) or upside-down (180)
			dYaw = dGamma;
			dPitch = dBeta;

		}

		lookDeltaX -= dYaw * GYRO_SENSITIVITY;
		lookDeltaY -= dPitch * GYRO_SENSITIVITY;

	}

	prevBeta = beta;
	prevGamma = gamma;

}

async function Gyro_RequestPermission() {

	if ( gyroPermissionRequested ) return;
	gyroPermissionRequested = true;

	// iOS 13+ requires explicit permission request from a user gesture
	if ( typeof DeviceOrientationEvent !== 'undefined' &&
		typeof DeviceOrientationEvent.requestPermission === 'function' ) {

		try {

			const permission = await DeviceOrientationEvent.requestPermission();
			if ( permission === 'granted' ) {

				Gyro_Enable();

			} else {

				console.log( 'Gyroscope permission denied' );

			}

		} catch ( err ) {

			console.log( 'Gyroscope permission error:', err.message );

		}

	} else {

		// Android and older iOS - no permission needed
		Gyro_Enable();

	}

}

function Gyro_Enable() {

	if ( gyroEnabled ) return;
	gyroEnabled = true;
	prevBeta = null;
	prevGamma = null;
	window.addEventListener( 'deviceorientation', onDeviceOrientation );

}

function Gyro_Disable() {

	if ( ! gyroEnabled ) return;
	gyroEnabled = false;
	prevBeta = null;
	prevGamma = null;
	window.removeEventListener( 'deviceorientation', onDeviceOrientation );

}

/*
=================
Wake Lock - prevents screen from dimming while playing
=================
*/

async function Touch_RequestWakeLock() {

	if ( wakeLock !== null ) return;

	if ( 'wakeLock' in navigator ) {

		try {

			wakeLock = await navigator.wakeLock.request( 'screen' );

			wakeLock.addEventListener( 'release', () => {

				wakeLock = null;

			} );

		} catch ( err ) {

			console.log( 'Wake Lock request failed:', err.message );

		}

	}

}

function Touch_ReleaseWakeLock() {

	if ( wakeLock !== null ) {

		wakeLock.release();
		wakeLock = null;

	}

}

/*
=================
Touch_RequestFullscreen

Request fullscreen and lock to landscape orientation on mobile
=================
*/
export async function Touch_RequestFullscreen() {

	if ( fullscreenActivated ) return;

	try {

		// Request fullscreen
		const container = document.documentElement;
		if ( container.requestFullscreen ) {

			await container.requestFullscreen();

		} else if ( container.webkitRequestFullscreen ) {

			await container.webkitRequestFullscreen();

		}

		// Lock to landscape orientation
		if ( screen.orientation && screen.orientation.lock ) {

			try {

				await screen.orientation.lock( 'landscape' );

			} catch ( e ) {

				// Orientation lock may not be supported or allowed
				console.log( 'Could not lock orientation:', e.message );

			}

		}

		fullscreenActivated = true;

	} catch ( e ) {

		console.log( 'Could not enter fullscreen:', e.message );

	}

}

/*
=================
Touch_ExitFullscreen

Exit fullscreen mode
=================
*/
export async function Touch_ExitFullscreen() {

	if ( ! document.fullscreenElement && ! document.webkitFullscreenElement ) return;

	try {

		if ( document.exitFullscreen ) {

			await document.exitFullscreen();

		} else if ( document.webkitExitFullscreen ) {

			await document.webkitExitFullscreen();

		}

		// Unlock orientation
		if ( screen.orientation && screen.orientation.unlock ) {

			screen.orientation.unlock();

		}

		fullscreenActivated = false;

	} catch ( e ) {

		console.log( 'Could not exit fullscreen:', e.message );

	}

}

/*
=================
Touch_Init

Initialize touch controls
=================
*/
export function Touch_Init( container ) {

	if ( initialized ) return;

	Touch_CreateUI( container || document.body );

	initialized = true;

}

/*
=================
Touch_Enable

Enable touch controls (show UI, add listeners)
=================
*/
export function Touch_Enable() {

	if ( ! initialized ) return;
	if ( enabled ) return;

	enabled = true;
	overlay.style.display = 'block';

	// Add touch listeners
	joystickArea.addEventListener( 'touchstart', onTouchStart, { passive: false } );
	joystickArea.addEventListener( 'touchmove', onTouchMove, { passive: false } );
	joystickArea.addEventListener( 'touchend', onTouchEnd, { passive: false } );
	joystickArea.addEventListener( 'touchcancel', onTouchEnd, { passive: false } );

	lookArea.addEventListener( 'touchstart', onTouchStart, { passive: false } );
	lookArea.addEventListener( 'touchmove', onTouchMove, { passive: false } );
	lookArea.addEventListener( 'touchend', onTouchEnd, { passive: false } );
	lookArea.addEventListener( 'touchcancel', onTouchEnd, { passive: false } );

	fireButton.addEventListener( 'touchstart', onTouchStart, { passive: false } );
	fireButton.addEventListener( 'touchend', onTouchEnd, { passive: false } );
	fireButton.addEventListener( 'touchcancel', onTouchEnd, { passive: false } );

	jumpButton.addEventListener( 'touchstart', onTouchStart, { passive: false } );
	jumpButton.addEventListener( 'touchend', onTouchEnd, { passive: false } );
	jumpButton.addEventListener( 'touchcancel', onTouchEnd, { passive: false } );

	pauseButton.addEventListener( 'touchstart', onTouchStart, { passive: false } );

	// Enable gyroscope if permission was already granted
	if ( gyroPermissionRequested ) {

		Gyro_Enable();

	}

	// Keep screen on while playing
	Touch_RequestWakeLock();

}

/*
=================
Touch_Disable

Disable touch controls (hide UI, remove listeners)
=================
*/
export function Touch_Disable() {

	if ( ! initialized || ! enabled ) return;

	enabled = false;
	overlay.style.display = 'none';

	// Remove touch listeners
	joystickArea.removeEventListener( 'touchstart', onTouchStart );
	joystickArea.removeEventListener( 'touchmove', onTouchMove );
	joystickArea.removeEventListener( 'touchend', onTouchEnd );
	joystickArea.removeEventListener( 'touchcancel', onTouchEnd );

	lookArea.removeEventListener( 'touchstart', onTouchStart );
	lookArea.removeEventListener( 'touchmove', onTouchMove );
	lookArea.removeEventListener( 'touchend', onTouchEnd );
	lookArea.removeEventListener( 'touchcancel', onTouchEnd );

	fireButton.removeEventListener( 'touchstart', onTouchStart );
	fireButton.removeEventListener( 'touchend', onTouchEnd );
	fireButton.removeEventListener( 'touchcancel', onTouchEnd );

	jumpButton.removeEventListener( 'touchstart', onTouchStart );
	jumpButton.removeEventListener( 'touchend', onTouchEnd );
	jumpButton.removeEventListener( 'touchcancel', onTouchEnd );

	pauseButton.removeEventListener( 'touchstart', onTouchStart );

	// Disable gyroscope while controls are off
	Gyro_Disable();

	// Release wake lock when not playing
	Touch_ReleaseWakeLock();

	// Reset state
	moveTouch = null;
	lookTouch = null;
	moveForward = 0;
	moveRight = 0;
	lookDeltaX = 0;
	lookDeltaY = 0;
	jumpImpulse = false;

}

/*
=================
Touch_IsEnabled
=================
*/
export function Touch_IsEnabled() {

	return enabled;

}

/*
=================
Touch_GetMoveInput

Returns normalized movement input from joystick
=================
*/
export function Touch_GetMoveInput() {

	return { forward: moveForward, right: moveRight };

}

/*
=================
Touch_GetLookDelta

Returns accumulated look delta and clears it
=================
*/
export function Touch_GetLookDelta() {

	const delta = { x: lookDeltaX, y: lookDeltaY };
	lookDeltaX = 0;
	lookDeltaY = 0;
	return delta;

}

/*
=================
Touch_CheckJump

Returns true if jump was triggered (tap on right side)
=================
*/
export function Touch_CheckJump() {

	if ( jumpImpulse ) {

		jumpImpulse = false;
		return true;

	}

	return false;

}

/*
=================
Touch_ShowMenu

Show menu touch overlay
=================
*/
export function Touch_ShowMenu() {

	if ( ! initialized || ! menuOverlay ) return;

	menuOverlay.style.display = 'block';

}

/*
=================
Touch_HideMenu

Hide menu touch overlay
=================
*/
export function Touch_HideMenu() {

	if ( ! initialized || ! menuOverlay ) return;

	menuOverlay.style.display = 'none';

}

/*
=================
Touch_SetMenuCallback

Set the callback function for menu touch events
Callback receives (touchX, touchY, screenWidth, screenHeight)
=================
*/
export function Touch_SetMenuCallback( callback ) {

	menuTouchCallback = callback;

}
