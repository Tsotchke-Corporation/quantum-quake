// Ported from: WinQuake/cd_audio.c -- CD audio playback
// In browser port: uses Web Audio API (HTML5 Audio element) for music tracks

import { Con_Printf, Con_DPrintf } from './console.js';
import { Cmd_AddCommand, Cmd_Argc, Cmd_Argv } from './cmd.js';
import { Cvar_SetValue } from './cvar.js';
import { COM_CheckParm } from './common.js';
import { bgmvolume } from './sound.js';
import { S_GetAudioContext, S_GetMasterGain } from './snd_dma.js';

/*
==============================================================================

			CD AUDIO STATE

==============================================================================
*/

const MAXIMUM_TRACKS = 100;

let playing = false;
let wasPlaying = false;
let initialized = false;
let enabled = true;
let playLooping = false;
let playTrack = 0;
let cdvolume = 0;

const remap = new Uint8Array( 256 );

// Web Audio / HTML5 Audio for music
let musicElement = null; // HTMLAudioElement for music playback
let musicGainNode = null;
let musicSource = null; // MediaElementAudioSourceNode

// Track URL provider (set externally)
let _getTrackURL = null;

/*
==============================================================================

			EXTERNAL INTERFACE

==============================================================================
*/

/*
================
CDAudio_SetTrackURLProvider

Set a function that maps track number -> URL for music files.
e.g., (track) => `music/track${track.toString().padStart(2,'0')}.ogg`
================
*/
export function CDAudio_SetTrackURLProvider( fn ) {

	_getTrackURL = fn;

}

/*
================
CDAudio_Play
================
*/
export function CDAudio_Play( track, looping ) {

	if ( ! initialized || ! enabled )
		return;

	track = remap[ track ];

	if ( playing ) {

		if ( playTrack === track )
			return;
		CDAudio_Stop();

	}

	playLooping = looping;

	if ( track < 1 || track >= MAXIMUM_TRACKS ) {

		Con_DPrintf( 'CDAudio_Play: Bad track number %d.\n', track );
		return;

	}

	playTrack = track;

	let vol = Math.floor( bgmvolume.value * 255.0 );
	if ( vol < 0 ) {

		Cvar_SetValue( 'bgmvolume', 0.0 );
		vol = 0;

	} else if ( vol > 255 ) {

		Cvar_SetValue( 'bgmvolume', 1.0 );
		vol = 255;

	}

	cdvolume = vol;

	// Get track URL
	let url = null;
	if ( _getTrackURL ) {

		url = _getTrackURL( track );

	}

	if ( ! url ) {

		Con_DPrintf( 'CDAudio_Play: no URL for track %d\n', track );
		return;

	}

	try {

		// Create or reuse HTMLAudioElement
		if ( ! musicElement ) {

			musicElement = new Audio();

		}

		musicElement.src = url;
		musicElement.loop = looping;
		musicElement.volume = bgmvolume.value;

		// Try to connect through Web Audio for unified volume control
		const audioContext = S_GetAudioContext();
		const masterGain = S_GetMasterGain();

		if ( audioContext && masterGain && ! musicSource ) {

			try {

				musicSource = audioContext.createMediaElementSource( musicElement );
				musicGainNode = audioContext.createGain();
				musicGainNode.gain.value = bgmvolume.value;
				musicSource.connect( musicGainNode );
				musicGainNode.connect( audioContext.destination );

			} catch ( e ) {

				// Fallback: direct playback without Web Audio routing
				Con_DPrintf( 'CDAudio: Web Audio routing failed, using direct playback\n' );

			}

		}

		if ( musicGainNode ) {

			musicGainNode.gain.value = bgmvolume.value;

		}

		musicElement.play().catch( function ( e ) {

			Con_DPrintf( 'CDAudio_Play: playback failed: %s\n', e.message );

		} );

		// Handle looping via ended event for non-loop mode
		musicElement.onended = function () {

			if ( ! playLooping ) {

				playing = false;

			}

		};

		playing = true;

	} catch ( e ) {

		Con_DPrintf( 'CDAudio_Play: track %d failed: %s\n', track, e.message );
		playing = false;

	}

}

/*
================
CDAudio_Stop
================
*/
export function CDAudio_Stop() {

	if ( ! initialized || ! enabled )
		return;

	if ( musicElement ) {

		try {

			musicElement.pause();
			musicElement.currentTime = 0;

		} catch ( e ) { /* ignore */ }

	}

	wasPlaying = playing;
	playing = false;

}

/*
================
CDAudio_Pause
================
*/
export function CDAudio_Pause() {

	if ( ! initialized || ! enabled )
		return;

	if ( ! playing )
		return;

	if ( musicElement ) {

		try {

			musicElement.pause();

		} catch ( e ) { /* ignore */ }

	}

	wasPlaying = playing;
	playing = false;

}

/*
================
CDAudio_Resume
================
*/
export function CDAudio_Resume() {

	if ( ! initialized || ! enabled )
		return;

	if ( ! wasPlaying )
		return;

	if ( musicElement ) {

		try {

			musicElement.play().catch( function () {} );

		} catch ( e ) { /* ignore */ }

	}

	playing = true;

}

/*
================
CDAudio_Update
================
*/
export function CDAudio_Update() {

	if ( ! initialized || ! enabled )
		return;

	let newVolume = Math.floor( bgmvolume.value * 255.0 );
	if ( newVolume !== cdvolume ) {

		if ( newVolume < 0 ) {

			Cvar_SetValue( 'bgmvolume', 0.0 );
			newVolume = 0;

		} else if ( newVolume > 255 ) {

			Cvar_SetValue( 'bgmvolume', 1.0 );
			newVolume = 255;

		}

		cdvolume = newVolume;

		if ( musicGainNode ) {

			musicGainNode.gain.value = bgmvolume.value;

		} else if ( musicElement ) {

			musicElement.volume = bgmvolume.value;

		}

	}

}

/*
================
CDAudio_Init
================
*/
export function CDAudio_Init() {

	if ( COM_CheckParm( '-nocdaudio' ) )
		return - 1;

	for ( let n = 0; n < 256; n ++ )
		remap[ n ] = n;

	initialized = true;
	enabled = true;

	Cmd_AddCommand( 'cd', CD_f );

	Con_Printf( 'CD Audio Initialized (Web Audio)\n' );

	return 0;

}

/*
================
CDAudio_Shutdown
================
*/
export function CDAudio_Shutdown() {

	if ( ! initialized )
		return;

	CDAudio_Stop();

	if ( musicSource ) {

		try {

			musicSource.disconnect();

		} catch ( e ) { /* ignore */ }

		musicSource = null;

	}

	if ( musicGainNode ) {

		try {

			musicGainNode.disconnect();

		} catch ( e ) { /* ignore */ }

		musicGainNode = null;

	}

	musicElement = null;
	initialized = false;

}

/*
================
CD_f

Console command handler for "cd" command
================
*/
function CD_f() {

	if ( Cmd_Argc() < 2 )
		return;

	const command = Cmd_Argv( 1 );

	if ( command === 'on' ) {

		enabled = true;
		return;

	}

	if ( command === 'off' ) {

		if ( playing )
			CDAudio_Stop();
		enabled = false;
		return;

	}

	if ( command === 'reset' ) {

		enabled = true;
		if ( playing )
			CDAudio_Stop();
		for ( let n = 0; n < 256; n ++ )
			remap[ n ] = n;
		return;

	}

	if ( command === 'remap' ) {

		const ret = Cmd_Argc() - 2;
		if ( ret <= 0 ) {

			for ( let n = 1; n < 256; n ++ ) {

				if ( remap[ n ] !== n )
					Con_Printf( '  %d -> %d\n', n, remap[ n ] );

			}

			return;

		}

		for ( let n = 1; n <= ret; n ++ )
			remap[ n ] = parseInt( Cmd_Argv( n + 1 ) ) || 0;

		return;

	}

	if ( command === 'play' ) {

		CDAudio_Play( parseInt( Cmd_Argv( 2 ) ) || 0, false );
		return;

	}

	if ( command === 'loop' ) {

		CDAudio_Play( parseInt( Cmd_Argv( 2 ) ) || 0, true );
		return;

	}

	if ( command === 'stop' ) {

		CDAudio_Stop();
		return;

	}

	if ( command === 'pause' ) {

		CDAudio_Pause();
		return;

	}

	if ( command === 'resume' ) {

		CDAudio_Resume();
		return;

	}

	if ( command === 'info' ) {

		if ( playing )
			Con_Printf( 'Currently %s track %d\n', playLooping ? 'looping' : 'playing', playTrack );
		else
			Con_Printf( 'Not playing\n' );

		Con_Printf( 'Volume is %d\n', cdvolume );
		return;

	}

}
