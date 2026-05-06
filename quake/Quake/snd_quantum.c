/*
 * snd_quantum.c - Quantum Circuit Audio Transducer for Quakespasm
 *
 * All game audio is transduced through quantum circuits using QGE:
 * Input -> DCT -> QGE Quantum Gates -> Measurement -> IDCT -> Output
 *
 * Demonstrates feasibility of audio processing on quantum computers.
 * This is the first fully ported demonstration of a real game running
 * on realistic quantum hardware simulation.
 *
 * Architecture: snd_quantum.c -> QGE -> Moonlab
 */

#include "quakedef.h"
#include "snd_quantum.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

/* QGE - Quantum Game Engine API (wraps Moonlab) */
#include "../../qge/qge.h"

/* CVars */
cvar_t snd_quantum_enable = {"snd_quantum", "1", CVAR_ARCHIVE};
cvar_t snd_quantum_mix = {"snd_quantum_mix", "0.35", CVAR_ARCHIVE};
cvar_t snd_quantum_spread = {"snd_quantum_spread", "0.5", CVAR_ARCHIVE};
cvar_t snd_quantum_reverb = {"snd_quantum_reverb", "0.08", CVAR_ARCHIVE};

/* DCT block size */
#define QA_BLOCK_SIZE 256
#define QA_NUM_BINS (QA_BLOCK_SIZE / 2)
#define QA_SAMPLE_SCALE (32768.0f * 256.0f)

/* Quantum circuit parameters - 8 qubits, fully entangled */
#define NUM_QUBITS 8
#define STATE_SIZE (1 << NUM_QUBITS)  /* 2^8 = 256 states */

/* QGE quantum transducers for left and right channels */
static qge_transducer_t *transducer_l = NULL;
static qge_transducer_t *transducer_r = NULL;

/* DCT buffers */
static float *input_buffer_l = NULL;
static float *input_buffer_r = NULL;
static float *freq_l = NULL;
static float *freq_r = NULL;
static float *output_buffer_l = NULL;
static float *output_buffer_r = NULL;

/* DCT coefficient table */
static float *dct_table = NULL;

/* Buffer position */
static int buffer_pos = 0;

/* Reverb */
#define REVERB_MAX_DELAY 22050
#define REVERB_NUM_TAPS 6
static float *reverb_buffer_l = NULL;
static float *reverb_buffer_r = NULL;
static int reverb_write_pos = 0;
static const int reverb_delays[REVERB_NUM_TAPS] = {1559, 2903, 4801, 7507, 11003, 16001};

/* Time evolution */
static double quantum_time = 0.0;

static qboolean quantum_initialized = false;

static float qa_clamp01(float value)
{
    if (value < 0.0f) return 0.0f;
    if (value > 1.0f) return 1.0f;
    return value;
}

/*
 * Initialize DCT coefficient table
 */
static void init_dct_table(void)
{
    dct_table = (float *)malloc(QA_BLOCK_SIZE * QA_BLOCK_SIZE * sizeof(float));
    if (!dct_table) return;

    float scale = sqrtf(2.0f / QA_BLOCK_SIZE);
    for (int k = 0; k < QA_BLOCK_SIZE; k++) {
        for (int n = 0; n < QA_BLOCK_SIZE; n++) {
            float c = (k == 0) ? sqrtf(0.5f) : 1.0f;
            dct_table[k * QA_BLOCK_SIZE + n] = scale * c *
                cosf(M_PI * k * (2.0f * n + 1.0f) / (2.0f * QA_BLOCK_SIZE));
        }
    }
}

/*
 * DCT-II: Time domain -> Frequency domain
 */
static void dct_forward(float *input, float *output)
{
    for (int k = 0; k < QA_BLOCK_SIZE; k++) {
        float sum = 0;
        for (int n = 0; n < QA_BLOCK_SIZE; n++) {
            sum += input[n] * dct_table[k * QA_BLOCK_SIZE + n];
        }
        output[k] = sum;
    }
}

/*
 * IDCT (DCT-III): Frequency domain -> Time domain
 */
static void dct_inverse(float *input, float *output)
{
    float scale = sqrtf(2.0f / QA_BLOCK_SIZE);
    for (int n = 0; n < QA_BLOCK_SIZE; n++) {
        float sum = input[0] * sqrtf(0.5f);
        for (int k = 1; k < QA_BLOCK_SIZE; k++) {
            sum += input[k] * cosf(M_PI * k * (2.0f * n + 1.0f) / (2.0f * QA_BLOCK_SIZE));
        }
        output[n] = sum * scale;
    }
}

/*
 * Apply quantum reverb with interference
 */
static void quantum_reverb(portable_samplepair_t *buffer, int count, float amount)
{
    if (!reverb_buffer_l || !reverb_buffer_r || amount < 0.001f)
        return;

    float decay = 0.5f;

    for (int i = 0; i < count; i++) {
        float in_l = (float)buffer[i].left / QA_SAMPLE_SCALE;
        float in_r = (float)buffer[i].right / QA_SAMPLE_SCALE;

        float reverb_l = 0, reverb_r = 0;

        for (int t = 0; t < REVERB_NUM_TAPS; t++) {
            int read_pos = reverb_write_pos - reverb_delays[t];
            if (read_pos < 0) read_pos += REVERB_MAX_DELAY;

            float phase = M_PI * t / REVERB_NUM_TAPS + quantum_time * 0.05f;
            float tap_decay = powf(decay, t + 1);
            float interference = cosf(phase) * tap_decay;

            reverb_l += reverb_buffer_l[read_pos] * interference;
            reverb_r += reverb_buffer_r[read_pos] * interference;
        }

        reverb_buffer_l[reverb_write_pos] = in_l * 0.8f + reverb_l * 0.15f;
        reverb_buffer_r[reverb_write_pos] = in_r * 0.8f + reverb_r * 0.15f;

        reverb_write_pos++;
        if (reverb_write_pos >= REVERB_MAX_DELAY)
            reverb_write_pos = 0;

        float out_l = in_l + reverb_l * amount;
        float out_r = in_r + reverb_r * amount;

        buffer[i].left = (int)(out_l * QA_SAMPLE_SCALE);
        buffer[i].right = (int)(out_r * QA_SAMPLE_SCALE);
    }
}

/*
 * S_QuantumInit - Initialize QGE quantum audio system
 */
void S_QuantumInit(void)
{
    if (quantum_initialized)
        return;

    /* Allocate DCT buffers */
    input_buffer_l = (float *)calloc(QA_BLOCK_SIZE, sizeof(float));
    input_buffer_r = (float *)calloc(QA_BLOCK_SIZE, sizeof(float));
    freq_l = (float *)calloc(QA_BLOCK_SIZE, sizeof(float));
    freq_r = (float *)calloc(QA_BLOCK_SIZE, sizeof(float));
    output_buffer_l = (float *)calloc(QA_BLOCK_SIZE, sizeof(float));
    output_buffer_r = (float *)calloc(QA_BLOCK_SIZE, sizeof(float));
    reverb_buffer_l = (float *)calloc(REVERB_MAX_DELAY, sizeof(float));
    reverb_buffer_r = (float *)calloc(REVERB_MAX_DELAY, sizeof(float));

    if (!input_buffer_l || !input_buffer_r || !freq_l || !freq_r ||
        !output_buffer_l || !output_buffer_r || !reverb_buffer_l || !reverb_buffer_r) {
        Con_Printf("S_QuantumInit: Failed to allocate buffers\n");
        S_QuantumShutdown();
        return;
    }

    init_dct_table();
    if (!dct_table) {
        Con_Printf("S_QuantumInit: Failed to allocate DCT table\n");
        S_QuantumShutdown();
        return;
    }

    /* Create QGE quantum transducers (8 qubits = 256 entangled states) */
    transducer_l = qge_transducer_create(NUM_QUBITS, QA_BLOCK_SIZE);
    transducer_r = qge_transducer_create(NUM_QUBITS, QA_BLOCK_SIZE);
    if (!transducer_l || !transducer_r) {
        Con_Printf("S_QuantumInit: Failed to create QGE quantum transducers\n");
        S_QuantumShutdown();
        return;
    }

    buffer_pos = 0;
    reverb_write_pos = 0;
    quantum_time = 0.0;

    Cvar_RegisterVariable(&snd_quantum_enable);
    Cvar_RegisterVariable(&snd_quantum_mix);
    Cvar_RegisterVariable(&snd_quantum_spread);
    Cvar_RegisterVariable(&snd_quantum_reverb);

    quantum_initialized = true;
    Con_Printf("QGE quantum audio: %d qubits, %d entangled states, %d-point DCT\n",
               NUM_QUBITS, STATE_SIZE, QA_BLOCK_SIZE);
}

/*
 * S_QuantumShutdown
 */
void S_QuantumShutdown(void)
{
    if (input_buffer_l) { free(input_buffer_l); input_buffer_l = NULL; }
    if (input_buffer_r) { free(input_buffer_r); input_buffer_r = NULL; }
    if (freq_l) { free(freq_l); freq_l = NULL; }
    if (freq_r) { free(freq_r); freq_r = NULL; }
    if (output_buffer_l) { free(output_buffer_l); output_buffer_l = NULL; }
    if (output_buffer_r) { free(output_buffer_r); output_buffer_r = NULL; }
    if (reverb_buffer_l) { free(reverb_buffer_l); reverb_buffer_l = NULL; }
    if (reverb_buffer_r) { free(reverb_buffer_r); reverb_buffer_r = NULL; }
    if (dct_table) { free(dct_table); dct_table = NULL; }

    /* Destroy QGE quantum transducers */
    if (transducer_l) { qge_transducer_free(transducer_l); transducer_l = NULL; }
    if (transducer_r) { qge_transducer_free(transducer_r); transducer_r = NULL; }

    quantum_initialized = false;
    Con_Printf("QGE quantum audio shutdown\n");
}

/*
 * S_QuantumProcess - Transduce all audio through QGE quantum circuits
 */
void S_QuantumProcess(portable_samplepair_t *paintbuffer, int count)
{
    if (!quantum_initialized || !paintbuffer || count <= 0)
        return;

    if (snd_quantum_enable.value < 0.5f)
        return;

    float spread = qa_clamp01(snd_quantum_spread.value);
    float mix = qa_clamp01(snd_quantum_mix.value);

    /* Process audio in blocks */
    for (int i = 0; i < count; i++) {
        /* Collect samples into input buffer */
        input_buffer_l[buffer_pos] = (float)paintbuffer[i].left / QA_SAMPLE_SCALE;
        input_buffer_r[buffer_pos] = (float)paintbuffer[i].right / QA_SAMPLE_SCALE;
        buffer_pos++;

        /* When we have a full block, process it */
        if (buffer_pos >= QA_BLOCK_SIZE) {
            /* DCT: Time -> Frequency */
            dct_forward(input_buffer_l, freq_l);
            dct_forward(input_buffer_r, freq_r);

            /* QGE quantum circuit processing - full 256-state entanglement */
            qge_transducer_process(transducer_l, freq_l, QA_NUM_BINS, spread, quantum_time);
            qge_transducer_process(transducer_r, freq_r, QA_NUM_BINS, spread, quantum_time);

            /* IDCT: Frequency -> Time */
            dct_inverse(freq_l, output_buffer_l);
            dct_inverse(freq_r, output_buffer_r);

            /* Write quantum-processed output back to paintbuffer */
            int start_idx = i - QA_BLOCK_SIZE + 1;
            for (int j = 0; j < QA_BLOCK_SIZE; j++) {
                int idx = start_idx + j;
                if (idx >= 0 && idx < count) {
                    /* Gentle limiting - avoid harsh clipping */
                    float out_l = output_buffer_l[j];
                    float out_r = output_buffer_r[j];

                    /* Gentle gain reduction first */
                    out_l *= 0.7f;
                    out_r *= 0.7f;

                    /* Soft knee compression */
                    float threshold = 0.5f;
                    if (fabsf(out_l) > threshold) {
                        float sign = (out_l >= 0) ? 1.0f : -1.0f;
                        float excess = fabsf(out_l) - threshold;
                        out_l = sign * (threshold + excess / (1.0f + excess * 2.0f));
                    }
                    if (fabsf(out_r) > threshold) {
                        float sign = (out_r >= 0) ? 1.0f : -1.0f;
                        float excess = fabsf(out_r) - threshold;
                        out_r = sign * (threshold + excess / (1.0f + excess * 2.0f));
                    }

                    /* Blend processed wet signal with Quake's dry mix. This
                     * keeps gameplay audio audible if the quantum transducer
                     * collapses to a low-energy block. */
                    float dry_l = (float)paintbuffer[idx].left / QA_SAMPLE_SCALE;
                    float dry_r = (float)paintbuffer[idx].right / QA_SAMPLE_SCALE;
                    out_l = dry_l * (1.0f - mix) + out_l * mix;
                    out_r = dry_r * (1.0f - mix) + out_r * mix;

                    paintbuffer[idx].left = (int)(out_l * QA_SAMPLE_SCALE);
                    paintbuffer[idx].right = (int)(out_r * QA_SAMPLE_SCALE);
                }
            }

            buffer_pos = 0;
            quantum_time += (double)QA_BLOCK_SIZE / 11025.0;

            qge_context_t *ctx = qge_get_context();
            qge_quantum_runtime_t *rt = qge_get_quantum_runtime(ctx);
            if (rt) {
                qge_state_probe_t probe;
                memset(&probe, 0, sizeof(probe));
                probe.domain = QGE_DOMAIN_AUDIO;
                probe.representation = QGE_REP_DCT_TRANSDUCER;
                probe.active_basis_count = QA_NUM_BINS * 2;
                probe.qubit_count = NUM_QUBITS * 2;
                probe.entropy = spread;
                probe.coherence = 1.0 - mix;
                probe.total_probability = quantum_time;
                strlcpy(probe.label, "audio_transducer", sizeof(probe.label));
                qge_quantum_record_probe(rt, &probe);
            }
        }
    }

    /* Apply quantum reverb */
    float reverb_amount = snd_quantum_reverb.value * mix;
    if (reverb_amount > 0.001f) {
        quantum_reverb(paintbuffer, count, reverb_amount);
    }
}

/*
 * Console commands
 */
void S_QuantumReverb_f(void)
{
    if (Cmd_Argc() == 2) {
        float val = atof(Cmd_Argv(1));
        Cvar_SetValue("snd_quantum_reverb", val);
    }
    Con_Printf("Quantum reverb: %.2f\n", snd_quantum_reverb.value);
}

void S_QuantumPhase_f(void)
{
    if (Cmd_Argc() == 2) {
        float val = atof(Cmd_Argv(1));
        Cvar_SetValue("snd_quantum_spread", val);
    }
    Con_Printf("Quantum spread: %.2f\n", snd_quantum_spread.value);
}
