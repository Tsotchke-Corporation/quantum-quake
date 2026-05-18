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

/* Mode helpers */
qboolean S_QuantumPostMixMode(void);
qboolean S_QuantumSourceMode(void);

typedef struct {
    qboolean valid;
    qboolean view_entity;
    vec3_t source_origin;
    vec3_t listener_origin;
    vec3_t listener_forward;
    vec3_t listener_right;
    float distance;
    float distance_attenuation;
    float pan_dot;
    float dist_mult;
    int master_vol;
    int leftvol;
    int rightvol;
    int output_channels;
} snd_quantum_source_spatial_t;

/* Apply quantum effects to paint buffer.
 * Called from S_PaintChannels after mixing for snd_quantum 1. */
void S_QuantumProcess(portable_samplepair_t *paintbuffer, int count);

/* Source-mode processing for snd_quantum 2. Dry source data is preserved on
 * skipped or failed quantum blocks. */
void S_QuantumSourceBeginFrame(void);
void S_QuantumSourceNote(int entnum, int entchannel, const char *name,
                         const snd_quantum_source_spatial_t *spatial);
void S_QuantumProcessSource(portable_samplepair_t *sourcebuffer, int count,
                            int entnum, int entchannel, const char *name,
                            const snd_quantum_source_spatial_t *spatial);
void S_QuantumSourceEndFrame(void);

/* Console commands */
void S_QuantumReverb_f(void);
void S_QuantumPhase_f(void);

/* CVars - declared extern so they can be registered elsewhere */
extern cvar_t snd_quantum_enable;
extern cvar_t snd_quantum_mix;
extern cvar_t snd_quantum_spread;
extern cvar_t snd_quantum_reverb;

#endif /* SND_QUANTUM_H */
