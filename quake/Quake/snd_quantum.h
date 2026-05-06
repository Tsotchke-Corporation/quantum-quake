/*
 * snd_quantum.h - Quantum audio effects for Quakespasm
 * Uses quantum harmonic oscillators for sound synthesis and effects
 */

#ifndef SND_QUANTUM_H
#define SND_QUANTUM_H

#include "quakedef.h"

/* Initialize quantum audio system */
void S_QuantumInit(void);

/* Shutdown quantum audio system */
void S_QuantumShutdown(void);

/* Apply quantum effects to paint buffer
 * Called from S_PaintChannels after mixing */
void S_QuantumProcess(portable_samplepair_t *paintbuffer, int count);

/* Console commands */
void S_QuantumReverb_f(void);
void S_QuantumPhase_f(void);

/* CVars - declared extern so they can be registered elsewhere */
extern cvar_t snd_quantum_enable;
extern cvar_t snd_quantum_reverb;
extern cvar_t snd_quantum_phase;

#endif /* SND_QUANTUM_H */
