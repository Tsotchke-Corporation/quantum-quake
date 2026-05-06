/**
 * @file qge_audio.c
 * @brief Quantum Audio - Sound synthesis using quantum harmonic oscillators
 *
 * Uses quantum harmonic oscillators for sound synthesis:
 * - Energy levels correspond to harmonics (E_n = ℏω(n + 1/2))
 * - Superposition of levels creates complex timbres
 * - Measurement collapses to specific frequencies
 * - Quantum interference for reverb and phase effects
 *
 * Physics background:
 * The quantum harmonic oscillator is one of the most fundamental quantum systems.
 * Its energy levels are equally spaced: E_n = ℏω(n + 1/2)
 * For sound synthesis, we map energy levels to harmonics of the base frequency:
 *   f_n = f_base * (n + 1)
 *
 * This gives us a natural harmonic series matching musical instruments.
 */

#include "qge.h"
#include "../deps/moonlab/src/quantum/state.h"
#include "../deps/moonlab/src/quantum/gates.h"
#include "../deps/moonlab/src/quantum/measurement.h"
#include "../deps/moonlab/src/utils/quantum_entropy.h"
#include "../deps/moonlab/src/applications/hardware_entropy.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>

/* ============================================================================
 * Constants
 * ============================================================================ */

#define AUDIO_MAX_LEVELS 32      /* Maximum energy levels per oscillator */
#define AUDIO_SAMPLE_RATE 44100  /* Standard sample rate */
#define AUDIO_QUBITS 5           /* 2^5 = 32 levels per oscillator */

/* ============================================================================
 * Quantum Oscillator Structure
 * ============================================================================ */

struct qge_oscillator_s {
    quantum_state_t* state;      /* Quantum state (superposition of energy levels) */
    int num_levels;              /* Number of energy levels */
    float base_frequency;        /* Ground state frequency (Hz) */
    float phase;                 /* Current phase for continuous synthesis */
    float last_frequency;        /* Last sampled frequency (for smooth transitions) */
    float amplitude;             /* Current amplitude */
    int id;                      /* Unique oscillator ID */
};

/* ============================================================================
 * Module State
 * ============================================================================ */

static bool audio_initialized = false;
static quantum_entropy_ctx_t* audio_entropy = NULL;
static entropy_ctx_t* audio_hw_entropy = NULL;
static int oscillator_count = 0;

/* ============================================================================
 * Entropy Callback
 * ============================================================================ */

static int audio_entropy_callback(void *user_data, uint8_t *buffer, size_t size) {
    entropy_ctx_t *ctx = (entropy_ctx_t *)user_data;
    return entropy_get_bytes(ctx, buffer, size);
}

/* ============================================================================
 * Initialization
 * ============================================================================ */

void qge_audio_init(void) {
    if (audio_initialized) return;

    /* Initialize hardware entropy */
    audio_hw_entropy = malloc(sizeof(entropy_ctx_t));
    if (!audio_hw_entropy || entropy_init(audio_hw_entropy) != ENTROPY_SUCCESS) {
        fprintf(stderr, "QGE AUDIO: Failed to init hardware entropy\n");
        free(audio_hw_entropy);
        audio_hw_entropy = NULL;
        return;
    }

    /* Initialize quantum entropy context */
    audio_entropy = malloc(sizeof(quantum_entropy_ctx_t));
    if (!audio_entropy) {
        fprintf(stderr, "QGE AUDIO: Failed to allocate entropy context\n");
        entropy_free(audio_hw_entropy);
        free(audio_hw_entropy);
        audio_hw_entropy = NULL;
        return;
    }
    quantum_entropy_init(audio_entropy, audio_entropy_callback, audio_hw_entropy);

    oscillator_count = 0;
    audio_initialized = true;
}

void qge_audio_shutdown(void) {
    if (!audio_initialized) return;

    if (audio_entropy) {
        free(audio_entropy);
        audio_entropy = NULL;
    }

    if (audio_hw_entropy) {
        entropy_free(audio_hw_entropy);
        free(audio_hw_entropy);
        audio_hw_entropy = NULL;
    }

    audio_initialized = false;
}

/* ============================================================================
 * Quantum Oscillator
 * ============================================================================ */

qge_oscillator_t* qge_oscillator_create(int num_levels, float base_frequency) {
    if (!audio_initialized) {
        qge_audio_init();
    }

    if (num_levels <= 0) num_levels = 8;
    if (num_levels > AUDIO_MAX_LEVELS) num_levels = AUDIO_MAX_LEVELS;
    if (base_frequency <= 0) base_frequency = 440.0f;  /* Default A4 */

    qge_oscillator_t* osc = malloc(sizeof(qge_oscillator_t));
    if (!osc) return NULL;

    /* Calculate qubits needed to represent num_levels */
    int qubits_needed = 1;
    while ((1 << qubits_needed) < num_levels) {
        qubits_needed++;
    }
    if (qubits_needed > AUDIO_QUBITS) qubits_needed = AUDIO_QUBITS;

    /* Allocate quantum state */
    osc->state = malloc(sizeof(quantum_state_t));
    if (!osc->state) {
        free(osc);
        return NULL;
    }

    qs_error_t err = quantum_state_init(osc->state, qubits_needed);
    if (err != QS_SUCCESS) {
        free(osc->state);
        free(osc);
        return NULL;
    }

    /* Initialize to ground state |0⟩ */
    quantum_state_reset(osc->state);

    osc->num_levels = num_levels;
    osc->base_frequency = base_frequency;
    osc->phase = 0.0f;
    osc->last_frequency = base_frequency;
    osc->amplitude = 1.0f;
    osc->id = oscillator_count++;

    return osc;
}

void qge_oscillator_free(qge_oscillator_t* osc) {
    if (!osc) return;

    if (osc->state) {
        quantum_state_free(osc->state);
        free(osc->state);
    }
    free(osc);
}

/**
 * @brief Excite the oscillator to a target energy level
 *
 * Uses quantum gates to create a superposition peaked at the target level.
 * This mimics exciting a physical quantum oscillator with a photon.
 *
 * Implementation: We use controlled rotations to concentrate amplitude
 * around the target level while maintaining some spread (quantum uncertainty).
 */
void qge_oscillator_excite(qge_oscillator_t* osc, int target_level) {
    if (!osc || !osc->state) return;
    if (target_level < 0) target_level = 0;
    if (target_level >= osc->num_levels) target_level = osc->num_levels - 1;

    /* Reset to ground state */
    quantum_state_reset(osc->state);

    int qubits = osc->state->num_qubits;
    uint64_t state_dim = osc->state->state_dim;

    /* Create superposition with Gaussian distribution centered at target_level
     *
     * The quantum harmonic oscillator naturally has Gaussian wave functions.
     * We emulate this by setting amplitudes according to:
     *   a_n ∝ exp(-(n - target)² / (2σ²))
     *
     * where σ controls the "spread" of excitation (quantum uncertainty).
     */
    double sigma = 1.5;  /* Spread parameter */
    double norm_sq = 0.0;

    /* Calculate unnormalized amplitudes */
    for (int n = 0; n < osc->num_levels && n < (int)state_dim; n++) {
        double delta = (double)(n - target_level);
        double amp = exp(-delta * delta / (2.0 * sigma * sigma));
        osc->state->amplitudes[n] = amp;
        norm_sq += amp * amp;
    }

    /* Normalize */
    if (norm_sq > 0) {
        double norm = sqrt(norm_sq);
        for (int n = 0; n < osc->num_levels && n < (int)state_dim; n++) {
            osc->state->amplitudes[n] /= norm;
        }
    }

    /* Add quantum phase based on level (mimics time evolution) */
    for (int n = 0; n < osc->num_levels && n < (int)state_dim; n++) {
        /* Phase accumulates with energy level: φ_n = n * ω * t
         * We use a small initial phase offset */
        double phase = (double)n * 0.1;
        osc->state->amplitudes[n] *= cexp(I * phase);
    }
}

/**
 * @brief Sample the oscillator (quantum measurement)
 *
 * Measures the quantum state, collapsing to a specific energy level.
 * Returns the corresponding frequency of that level.
 *
 * After measurement, the oscillator is in an eigenstate of the measured level,
 * but we re-excite it to maintain ongoing sound synthesis.
 */
float qge_oscillator_sample(qge_oscillator_t* osc) {
    if (!osc || !osc->state) return 440.0f;

    /* Calculate probability distribution over energy levels */
    float probabilities[AUDIO_MAX_LEVELS];
    float total_prob = 0.0f;

    for (int n = 0; n < osc->num_levels; n++) {
        double amp_r = creal(osc->state->amplitudes[n]);
        double amp_i = cimag(osc->state->amplitudes[n]);
        probabilities[n] = (float)(amp_r * amp_r + amp_i * amp_i);
        total_prob += probabilities[n];
    }

    /* Normalize if needed */
    if (total_prob > 0.001f && fabsf(total_prob - 1.0f) > 0.001f) {
        for (int n = 0; n < osc->num_levels; n++) {
            probabilities[n] /= total_prob;
        }
    }

    /* Sample from distribution using quantum entropy */
    float random_val = 0.0f;
    if (audio_entropy) {
        uint32_t rand_bits;
        uint8_t bytes[4];
        quantum_entropy_get_bytes(audio_entropy, bytes, 4);
        memcpy(&rand_bits, bytes, 4);
        random_val = (float)(rand_bits & 0xFFFFFF) / (float)0xFFFFFF;
    } else {
        random_val = (float)rand() / (float)RAND_MAX;
    }

    /* Select energy level based on probability */
    float cumulative = 0.0f;
    int measured_level = 0;
    for (int n = 0; n < osc->num_levels; n++) {
        cumulative += probabilities[n];
        if (random_val <= cumulative) {
            measured_level = n;
            break;
        }
    }

    /* Calculate frequency for this energy level
     * Harmonic series: f_n = f_base * (n + 1) */
    float frequency = osc->base_frequency * (float)(measured_level + 1);

    /* Smooth transition to avoid clicks */
    osc->last_frequency = 0.9f * osc->last_frequency + 0.1f * frequency;

    /* Collapse state to measured level (eigenstate), then re-excite
     * This gives continuous sound with quantum variations */
    quantum_state_reset(osc->state);
    osc->state->amplitudes[measured_level] = 1.0;

    /* Re-excite with some spread to maintain quantum character */
    qge_oscillator_excite(osc, measured_level);

    return osc->last_frequency;
}

/**
 * @brief Synthesize audio samples from quantum oscillator
 *
 * Generates audio samples by evolving the quantum state and sampling.
 * Uses superposition to create rich harmonic content.
 */
void qge_audio_synthesize(float* buffer, int samples, qge_oscillator_t* osc) {
    if (!buffer || samples <= 0 || !osc) return;

    float dt = 1.0f / (float)AUDIO_SAMPLE_RATE;
    float two_pi = 2.0f * M_PI;

    /* Sample the oscillator periodically for frequency variations */
    int sample_interval = AUDIO_SAMPLE_RATE / 60;  /* Sample 60 times per second */
    if (sample_interval < 1) sample_interval = 1;

    for (int i = 0; i < samples; i++) {
        /* Periodically measure for frequency update */
        if (i % sample_interval == 0) {
            qge_oscillator_sample(osc);
        }

        /* Generate sample using current frequency */
        float sample = osc->amplitude * sinf(osc->phase);

        /* Add harmonics from quantum superposition (probability-weighted) */
        float harmonic_sum = sample;
        for (int h = 1; h < osc->num_levels && h < 8; h++) {
            double amp_r = creal(osc->state->amplitudes[h]);
            double amp_i = cimag(osc->state->amplitudes[h]);
            float prob = (float)(amp_r * amp_r + amp_i * amp_i);
            if (prob > 0.01f) {
                float harmonic_freq = osc->last_frequency * (float)(h + 1);
                float harmonic_phase = osc->phase * (float)(h + 1);
                harmonic_sum += sqrtf(prob) * sinf(harmonic_phase) * 0.5f;
            }
        }

        buffer[i] = harmonic_sum;

        /* Advance phase */
        osc->phase += two_pi * osc->last_frequency * dt;
        if (osc->phase >= two_pi) {
            osc->phase -= two_pi;
        }
    }
}

/* ============================================================================
 * Quantum Audio Effects
 * ============================================================================ */

/**
 * @brief Apply quantum interference reverb
 *
 * Uses quantum interference pattern to create reverb:
 * - Delayed copies of signal interfere with original
 * - Phase differences create constructive/destructive patterns
 * - Decay controlled by quantum amplitude reduction
 *
 * This mimics how sound reflects in physical spaces,
 * but uses quantum interference math instead of ray tracing.
 */
void qge_audio_reverb(float* samples, int count, float decay) {
    if (!samples || count <= 0) return;
    if (decay < 0.0f) decay = 0.0f;
    if (decay > 0.99f) decay = 0.99f;

    /* Create quantum state for interference pattern */
    int num_taps = 8;  /* Number of delay taps (echoes) */
    int delays[8] = {441, 1323, 2205, 3528, 5292, 7056, 8820, 11025};  /* 10-250ms */
    float tap_gains[8];

    /* Initialize tap gains with quantum decay */
    for (int t = 0; t < num_taps; t++) {
        /* Amplitude decreases with quantum decay: A_n = A_0 * decay^n */
        tap_gains[t] = powf(decay, (float)(t + 1));
    }

    /* Create interference buffer */
    float* reverb_buffer = calloc(count, sizeof(float));
    if (!reverb_buffer) return;

    /* Apply each delay tap with quantum interference */
    for (int t = 0; t < num_taps; t++) {
        int delay = delays[t];
        float gain = tap_gains[t];

        /* Add phase shift for quantum interference
         * Phase varies with tap number to create complex interference */
        float phase_shift = M_PI * (float)t / (float)num_taps;

        for (int i = delay; i < count; i++) {
            /* Original sample and delayed sample interfere */
            float delayed = samples[i - delay];

            /* Quantum interference: a + b*e^(iφ) in amplitude
             * For real signals, this manifests as amplitude modulation */
            float interference = delayed * gain * cosf(phase_shift);

            reverb_buffer[i] += interference;
        }
    }

    /* Mix reverb with original (wet/dry) */
    float wet = 0.4f;  /* 40% reverb, 60% dry */
    for (int i = 0; i < count; i++) {
        samples[i] = (1.0f - wet) * samples[i] + wet * reverb_buffer[i];
    }

    free(reverb_buffer);
}

/**
 * @brief Apply quantum phase modulation effect
 *
 * Uses quantum phase to modulate the audio signal.
 * Creates phaser/chorus-like effects using quantum oscillation.
 *
 * Physics: In quantum mechanics, phase evolves as e^(-iωt).
 * We apply this phase modulation to create sweeping effects.
 */
void qge_audio_phase(float* samples, int count, float depth) {
    if (!samples || count <= 0) return;
    if (depth < 0.0f) depth = 0.0f;
    if (depth > 1.0f) depth = 1.0f;

    float dt = 1.0f / (float)AUDIO_SAMPLE_RATE;
    float two_pi = 2.0f * M_PI;

    /* LFO for phase modulation (low frequency oscillator)
     * Mimics quantum state precession */
    float lfo_freq = 0.5f;  /* 0.5 Hz sweep rate */
    float lfo_phase = 0.0f;

    /* All-pass filter delays for phase shifting */
    int num_stages = 4;
    float delay_samples[4] = {0, 0, 0, 0};
    float feedback = 0.7f;

    for (int i = 0; i < count; i++) {
        /* Calculate LFO modulation (quantum precession) */
        float lfo = sinf(lfo_phase);
        lfo_phase += two_pi * lfo_freq * dt;
        if (lfo_phase >= two_pi) lfo_phase -= two_pi;

        /* Variable delay based on LFO (1-10ms range) */
        float delay_ms = 1.0f + 4.5f * (1.0f + lfo);
        float delay_time = delay_ms * 0.001f * (float)AUDIO_SAMPLE_RATE;

        /* Apply all-pass stages for phase shift */
        float input = samples[i];
        float output = input;

        for (int s = 0; s < num_stages; s++) {
            float delayed = delay_samples[s];
            float new_delay = input + feedback * delayed;
            output = delayed - feedback * new_delay;
            delay_samples[s] = new_delay;
            input = output;
        }

        /* Mix with original based on depth (quantum interference) */
        samples[i] = (1.0f - depth) * samples[i] + depth * output;
    }
}

/**
 * @brief Apply quantum superposition mixing
 *
 * Mix two audio buffers using quantum superposition principle.
 * The interference pattern creates unique mixing characteristics.
 */
void qge_audio_quantum_mix(float* buf_a, float* buf_b, float* output,
                            int count, float mix_ratio) {
    if (!buf_a || !buf_b || !output || count <= 0) return;
    if (mix_ratio < 0.0f) mix_ratio = 0.0f;
    if (mix_ratio > 1.0f) mix_ratio = 1.0f;

    /* Quantum mixing: |ψ⟩ = α|a⟩ + β|b⟩ where |α|² + |β|² = 1
     * For audio: output = α*a + β*b with probability normalization */

    float alpha = sqrtf(1.0f - mix_ratio);
    float beta = sqrtf(mix_ratio);

    /* Phase difference for interference */
    float phase_diff = 0.0f;
    float phase_rate = 0.001f;  /* Slow phase rotation */

    for (int i = 0; i < count; i++) {
        /* Quantum superposition with phase */
        float a_component = alpha * buf_a[i];
        float b_component = beta * buf_b[i] * cosf(phase_diff);

        /* Constructive/destructive interference */
        output[i] = a_component + b_component;

        /* Evolve phase (quantum time evolution) */
        phase_diff += phase_rate;
        if (phase_diff >= 2.0f * M_PI) phase_diff -= 2.0f * M_PI;
    }
}

/* ============================================================================
 * Additional Quantum Audio Utilities
 * ============================================================================ */

/**
 * @brief Get the current probability distribution over energy levels
 */
void qge_oscillator_get_probabilities(qge_oscillator_t* osc,
                                       float* probabilities, int max_levels) {
    if (!osc || !probabilities || max_levels <= 0) return;

    int levels = (max_levels < osc->num_levels) ? max_levels : osc->num_levels;

    for (int n = 0; n < levels; n++) {
        double amp_r = creal(osc->state->amplitudes[n]);
        double amp_i = cimag(osc->state->amplitudes[n]);
        probabilities[n] = (float)(amp_r * amp_r + amp_i * amp_i);
    }
}

/**
 * @brief Set oscillator amplitude
 */
void qge_oscillator_set_amplitude(qge_oscillator_t* osc, float amplitude) {
    if (!osc) return;
    osc->amplitude = amplitude;
}

/**
 * @brief Apply quantum decay to oscillator (decoherence)
 *
 * Simulates environmental interaction that causes quantum decoherence.
 * Used for natural sound decay (like damped oscillations).
 */
void qge_oscillator_decay(qge_oscillator_t* osc, float decay_rate) {
    if (!osc || !osc->state) return;
    if (decay_rate <= 0.0f) return;
    if (decay_rate > 1.0f) decay_rate = 1.0f;

    /* Amplitude damping: reduces all amplitudes toward ground state */
    double keep_rate = 1.0 - (double)decay_rate;

    for (int n = 1; n < osc->num_levels; n++) {
        /* Higher energy states decay faster (T1 relaxation) */
        double level_decay = pow(keep_rate, (double)n);
        osc->state->amplitudes[n] *= level_decay;
    }

    /* Transfer lost amplitude to ground state (energy conservation) */
    double total = 0.0;
    for (int n = 0; n < osc->num_levels; n++) {
        double amp_r = creal(osc->state->amplitudes[n]);
        double amp_i = cimag(osc->state->amplitudes[n]);
        total += amp_r * amp_r + amp_i * amp_i;
    }

    /* Re-normalize */
    if (total > 0 && fabs(total - 1.0) > 0.001) {
        double norm = sqrt(total);
        for (int n = 0; n < osc->num_levels; n++) {
            osc->state->amplitudes[n] /= norm;
        }
    }

    /* Also decay classical amplitude */
    osc->amplitude *= (1.0f - decay_rate * 0.1f);
}

/* ============================================================================
 * Quantum Audio Transducer Implementation
 *
 * Processes audio through quantum circuits in frequency domain.
 * This enables "quantum audio transduction" - passing all audio through
 * real quantum gate sequences for interference and entanglement effects.
 * ============================================================================ */

struct qge_transducer_s {
    quantum_state_t* state;    /* Moonlab quantum state */
    int num_qubits;            /* Number of qubits */
    size_t state_dim;          /* 2^num_qubits */
    int block_size;            /* DCT block size */
    uint32_t rng_state;        /* PRNG for spread variation */
};

/* Internal PRNG for spread variation */
static float transducer_rng_float(qge_transducer_t* trans) {
    trans->rng_state = trans->rng_state * 1103515245 + 12345;
    return (float)(trans->rng_state >> 16) / 65536.0f;
}

qge_transducer_t* qge_transducer_create(int num_qubits, int block_size) {
    if (!audio_initialized) {
        qge_audio_init();
    }

    if (num_qubits <= 0) num_qubits = 8;
    if (num_qubits > 16) num_qubits = 16;  /* Limit for performance */
    if (block_size <= 0) block_size = 256;

    qge_transducer_t* trans = malloc(sizeof(qge_transducer_t));
    if (!trans) return NULL;

    trans->state = malloc(sizeof(quantum_state_t));
    if (!trans->state) {
        free(trans);
        return NULL;
    }

    qs_error_t err = quantum_state_init(trans->state, num_qubits);
    if (err != QS_SUCCESS) {
        free(trans->state);
        free(trans);
        return NULL;
    }

    trans->num_qubits = num_qubits;
    trans->state_dim = trans->state->state_dim;
    trans->block_size = block_size;
    trans->rng_state = 31337;

    return trans;
}

void qge_transducer_reset(qge_transducer_t* trans) {
    if (!trans || !trans->state) return;
    quantum_state_reset(trans->state);
}

void qge_transducer_free(qge_transducer_t* trans) {
    if (!trans) return;
    if (trans->state) {
        quantum_state_free(trans->state);
        free(trans->state);
    }
    free(trans);
}

void* qge_transducer_get_state(qge_transducer_t* trans) {
    if (!trans) return NULL;
    return trans->state;
}

void qge_transducer_apply_gate(qge_transducer_t* trans, char gate_type, int qubit) {
    if (!trans || !trans->state) return;
    if (qubit < 0 || qubit >= trans->num_qubits) return;

    switch (gate_type) {
        case 'H': case 'h':
            gate_hadamard(trans->state, qubit);
            break;
        case 'X': case 'x':
            gate_pauli_x(trans->state, qubit);
            break;
        case 'Y': case 'y':
            gate_pauli_y(trans->state, qubit);
            break;
        case 'Z': case 'z':
            gate_pauli_z(trans->state, qubit);
            break;
        case 'S': case 's':
            gate_s(trans->state, qubit);
            break;
        case 'T': case 't':
            gate_t(trans->state, qubit);
            break;
        default:
            break;
    }
}

void qge_transducer_apply_rotation(qge_transducer_t* trans, char axis, int qubit, double angle) {
    if (!trans || !trans->state) return;
    if (qubit < 0 || qubit >= trans->num_qubits) return;

    switch (axis) {
        case 'X': case 'x':
            gate_rx(trans->state, qubit, angle);
            break;
        case 'Y': case 'y':
            gate_ry(trans->state, qubit, angle);
            break;
        case 'Z': case 'z':
            gate_rz(trans->state, qubit, angle);
            break;
        default:
            break;
    }
}

void qge_transducer_apply_controlled(qge_transducer_t* trans, char gate_type,
                                      int control, int target) {
    if (!trans || !trans->state) return;
    if (control < 0 || control >= trans->num_qubits) return;
    if (target < 0 || target >= trans->num_qubits) return;
    if (control == target) return;

    switch (gate_type) {
        case 'N': case 'n':  /* CNOT */
            gate_cnot(trans->state, control, target);
            break;
        case 'Z': case 'z':  /* CZ */
            gate_cz(trans->state, control, target);
            break;
        default:
            break;
    }
}

double qge_transducer_get_probability(qge_transducer_t* trans, int basis_state) {
    if (!trans || !trans->state) return 0.0;
    if (basis_state < 0 || basis_state >= (int)trans->state_dim) return 0.0;

    complex_t amp = trans->state->amplitudes[basis_state];
    return creal(amp) * creal(amp) + cimag(amp) * cimag(amp);
}

float qge_transducer_measure_interference(qge_transducer_t* trans, int target_state) {
    if (!trans || !trans->state) return 0.0f;

    double sum_real = 0, sum_imag = 0;
    size_t dim = trans->state_dim;
    int num_qubits = trans->num_qubits;

    for (size_t i = 0; i < dim; i++) {
        /* Weight by how many bits match the target pattern */
        int match = ~((int)i ^ target_state) & ((int)dim - 1);
        int popcount = 0;
        int m = match;
        while (m) { popcount += m & 1; m >>= 1; }

        double weight = (double)popcount / num_qubits;
        sum_real += creal(trans->state->amplitudes[i]) * weight;
        sum_imag += cimag(trans->state->amplitudes[i]) * weight;
    }

    return (float)sqrt(sum_real * sum_real + sum_imag * sum_imag);
}

/**
 * @brief Process frequency bins through the standard quantum circuit
 *
 * This implements the full audio transduction pipeline:
 * 1. Reset quantum state to |0...0⟩
 * 2. Encode frequency amplitudes via Ry rotations
 * 3. Create superposition with Hadamard layer
 * 4. Full entanglement using CNOT ladder + circular connection
 * 5. Time-evolving phase gates with spread variation
 * 6. Additional CZ entanglement
 * 7. Final Hadamard layer for interference
 * 8. Measure interference patterns and modulate frequency bins
 */
void qge_transducer_process(qge_transducer_t* trans,
                             float* freq_bins, int num_bins,
                             float spread, double time) {
    if (!trans || !trans->state || !freq_bins || num_bins <= 0) return;

    int nq = trans->num_qubits;
    int bins_per_qubit = num_bins / nq;
    if (bins_per_qubit < 1) bins_per_qubit = 1;

    /* Stage 1: Reset to |0...0⟩ */
    quantum_state_reset(trans->state);

    /* Stage 2: Encode frequency amplitudes using Ry rotations */
    for (int q = 0; q < nq; q++) {
        /* Compute average amplitude for this qubit's frequency band */
        float avg = 0;
        for (int j = 0; j < bins_per_qubit; j++) {
            int bin = q * bins_per_qubit + j;
            if (bin < num_bins) {
                avg += fabsf(freq_bins[bin]);
            }
        }
        avg /= bins_per_qubit;

        double theta = avg * M_PI;
        gate_ry(trans->state, q, theta);
    }

    /* Stage 3: Hadamard layer for superposition */
    for (int q = 0; q < nq; q++) {
        gate_hadamard(trans->state, q);
    }

    /* Stage 4: Full CNOT ladder entanglement */
    for (int q = 0; q < nq - 1; q++) {
        gate_cnot(trans->state, q, q + 1);
    }
    /* Circular entanglement */
    gate_cnot(trans->state, nq - 1, 0);

    /* Stage 5: Time-evolving phase gates */
    for (int q = 0; q < nq; q++) {
        double phase = time * (0.1 + 0.03 * q);
        if (spread > 0) {
            phase += spread * (transducer_rng_float(trans) - 0.5f);
        }
        gate_phase(trans->state, q, phase);
    }

    /* Stage 6: CZ entanglement pairs */
    for (int q = 0; q < nq - 1; q += 2) {
        gate_cz(trans->state, q, q + 1);
    }

    /* Stage 7: Final Hadamard layer for interference */
    for (int q = 0; q < nq; q++) {
        gate_hadamard(trans->state, q);
    }

    /* Stage 8: Measure interference and modulate frequency bins */
    for (int bin = 0; bin < num_bins; bin++) {
        int state_idx = bin % (int)trans->state_dim;
        float interference = qge_transducer_measure_interference(trans, state_idx);
        float modulation = 0.8f + interference * 0.4f;
        freq_bins[bin] *= modulation;
    }

    /* Preserve DC component */
    if (num_bins > 0) {
        freq_bins[0] *= 0.95f;
    }
}
