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
#include <stdint.h>
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

#define QA_SOURCE_FLAG_DRY_FALLBACK 0x1u
#define QA_SOURCE_FLAG_PROCESSED 0x2u
#define QA_SOURCE_FLAG_CLIPPED 0x4u
#define QA_SOURCE_FLAG_SPATIAL 0x8u
#define QA_SOURCE_FLAG_VIEW_ENTITY 0x10u

#define QA_SOURCE_FALLBACK_RUNTIME 1
#define QA_SOURCE_FALLBACK_SHORT_BLOCK 2
#define QA_SOURCE_FALLBACK_INVALID_BLOCK 3
#define QA_SOURCE_FALLBACK_REMAINDER 4

typedef struct {
    int source_count;
    int spatial_sources;
    int processed_sources;
    int processed_blocks;
    int processed_samples;
    int skipped_blocks;
    int dry_fallback_blocks;
    int fallback_runtime_blocks;
    int fallback_short_blocks;
    int fallback_invalid_blocks;
    int fallback_remainder_blocks;
    int clipped_samples;
    double transducer_ms;
    double spatial_distance_sum;
    double spatial_abs_pan_sum;
    double spatial_attenuation_sum;
    int last_subject_id;
    int last_fallback_reason_code;
    char last_source_name[QGE_PROBE_LABEL_MAX];
    char last_fallback_reason[QGE_TRACE_MESSAGE_MAX];
    snd_quantum_source_spatial_t last_spatial;
} qa_source_stats_t;

static qa_source_stats_t qa_source_stats;
static qboolean qa_source_frame_active = false;

static float qa_clamp01(float value)
{
    if (value < 0.0f) return 0.0f;
    if (value > 1.0f) return 1.0f;
    return value;
}

static float qa_clamp11(float value)
{
    if (!isfinite(value))
        return 0.0f;
    if (value < -1.0f) return -1.0f;
    if (value > 1.0f) return 1.0f;
    return value;
}

static qboolean qa_source_spatial_valid(const snd_quantum_source_spatial_t *spatial)
{
    return spatial && spatial->valid;
}

static uint32_t qa_source_spatial_flags(const snd_quantum_source_spatial_t *spatial)
{
    uint32_t flags = 0;

    if (qa_source_spatial_valid(spatial)) {
        flags |= QA_SOURCE_FLAG_SPATIAL;
        if (spatial->view_entity)
            flags |= QA_SOURCE_FLAG_VIEW_ENTITY;
    }
    return flags;
}

static uint64_t qa_hash_step64(uint64_t hash, uint64_t value)
{
    hash ^= value + 0x9e3779b97f4a7c15ULL + (hash << 6) + (hash >> 2);
    return hash;
}

static int32_t qa_quantize_float(float value, float scale)
{
    if (!isfinite(value))
        return 0;
    if (value > 1048576.0f)
        value = 1048576.0f;
    else if (value < -1048576.0f)
        value = -1048576.0f;
    return (int32_t)(value * scale);
}

static uint64_t qa_source_spatial_hash(const snd_quantum_source_spatial_t *spatial)
{
    uint64_t hash = 1469598103934665603ULL;

    if (!qa_source_spatial_valid(spatial))
        return 0;

    for (int i = 0; i < 3; i++)
        hash = qa_hash_step64(hash,
                              (uint32_t)qa_quantize_float(spatial->source_origin[i], 16.0f));
    for (int i = 0; i < 3; i++)
        hash = qa_hash_step64(hash,
                              (uint32_t)qa_quantize_float(spatial->listener_origin[i], 16.0f));
    for (int i = 0; i < 3; i++)
        hash = qa_hash_step64(hash,
                              (uint32_t)qa_quantize_float(spatial->listener_forward[i], 4096.0f));
    for (int i = 0; i < 3; i++)
        hash = qa_hash_step64(hash,
                              (uint32_t)qa_quantize_float(spatial->listener_right[i], 4096.0f));
    hash = qa_hash_step64(hash,
                          (uint32_t)qa_quantize_float(spatial->distance, 16.0f));
    hash = qa_hash_step64(hash,
                          (uint32_t)qa_quantize_float(spatial->distance_attenuation, 4096.0f));
    hash = qa_hash_step64(hash,
                          (uint32_t)qa_quantize_float(spatial->pan_dot, 4096.0f));
    hash = qa_hash_step64(hash,
                          (uint32_t)qa_quantize_float(spatial->dist_mult, 1048576.0f));
    hash = qa_hash_step64(hash, (uint32_t)spatial->master_vol);
    hash = qa_hash_step64(hash, (uint32_t)spatial->leftvol);
    hash = qa_hash_step64(hash, (uint32_t)spatial->rightvol);
    hash = qa_hash_step64(hash, (uint32_t)spatial->output_channels);
    hash = qa_hash_step64(hash, spatial->view_entity ? 1u : 0u);
    return hash;
}

static void qa_source_update_last_spatial(const snd_quantum_source_spatial_t *spatial)
{
    if (qa_source_spatial_valid(spatial))
        qa_source_stats.last_spatial = *spatial;
}

static void qa_source_note_spatial(const snd_quantum_source_spatial_t *spatial)
{
    if (!qa_source_spatial_valid(spatial))
        return;

    qa_source_stats.spatial_sources++;
    qa_source_stats.spatial_distance_sum += spatial->distance;
    qa_source_stats.spatial_abs_pan_sum += fabsf(qa_clamp11(spatial->pan_dot));
    qa_source_stats.spatial_attenuation_sum += qa_clamp01(spatial->distance_attenuation);
    qa_source_update_last_spatial(spatial);
}

static void qa_source_note_fallback(int reason_code, int blocks,
                                    const char *reason)
{
    if (blocks < 1)
        blocks = 1;

    qa_source_stats.dry_fallback_blocks += blocks;
    qa_source_stats.last_fallback_reason_code = reason_code;
    q_strlcpy(qa_source_stats.last_fallback_reason,
              reason && reason[0] ? reason : "audio_source_dry_unknown",
              sizeof(qa_source_stats.last_fallback_reason));

    switch (reason_code) {
    case QA_SOURCE_FALLBACK_RUNTIME:
        qa_source_stats.fallback_runtime_blocks += blocks;
        break;
    case QA_SOURCE_FALLBACK_SHORT_BLOCK:
        qa_source_stats.fallback_short_blocks += blocks;
        break;
    case QA_SOURCE_FALLBACK_INVALID_BLOCK:
        qa_source_stats.fallback_invalid_blocks += blocks;
        break;
    case QA_SOURCE_FALLBACK_REMAINDER:
        qa_source_stats.fallback_remainder_blocks += blocks;
        break;
    default:
        break;
    }
}

static const char *qa_source_runtime_fallback_reason(float mix)
{
    if (!quantum_initialized)
        return "audio_source_dry_fallback_uninitialized";
    if (!transducer_l || !transducer_r)
        return "audio_source_dry_fallback_transducer";
    if (!dct_table)
        return "audio_source_dry_fallback_dct";
    if (mix <= 0.0f)
        return "audio_source_dry_fallback_mix_zero";
    return "audio_source_dry_fallback";
}

qboolean S_QuantumPostMixMode(void)
{
    return snd_quantum_enable.value >= 0.5f &&
           snd_quantum_enable.value < 1.5f;
}

qboolean S_QuantumSourceMode(void)
{
    return snd_quantum_enable.value >= 1.5f;
}

static int qa_block_count_for_samples(int count)
{
    if (count <= 0)
        return 0;
    return (count + QA_BLOCK_SIZE - 1) / QA_BLOCK_SIZE;
}

static int qa_source_subject_id(int entnum, int entchannel)
{
    uint32_t hash = 2166136261u;

    hash = (hash ^ (uint32_t)entnum) * 16777619u;
    hash = (hash ^ (uint32_t)entchannel) * 16777619u;
    return (int)(hash & 0x7fffffffu);
}

static int qa_paint_sample_from_float(float value, int *clipped)
{
    double scaled = (double)value * QA_SAMPLE_SCALE;
    const double min_sample = (double)(-32768 * 256);
    const double max_sample = (double)(32767 * 256);

    if (!isfinite(scaled)) {
        if (clipped)
            (*clipped)++;
        return 0;
    }
    if (scaled > max_sample) {
        if (clipped)
            (*clipped)++;
        scaled = max_sample;
    } else if (scaled < min_sample) {
        if (clipped)
            (*clipped)++;
        scaled = min_sample;
    }
    return (int)scaled;
}

static qge_quantum_runtime_t *qa_runtime(void)
{
    qge_context_t *ctx = qge_get_context();

    if (!ctx)
        return NULL;
    return qge_get_quantum_runtime(ctx);
}

static void qa_runtime_stamp(qge_quantum_runtime_t *rt,
                             int *frame, int *server_time_msec)
{
    if (!rt) {
        *frame = 0;
        *server_time_msec = 0;
        return;
    }

    *frame = qge_quantum_runtime_get_frame(rt);
    *server_time_msec = qge_quantum_runtime_get_server_time_msec(rt);
}

static void qa_record_source_probe(int subject_id, const char *label,
                                   uint32_t flags, int basis_count,
                                   int samples, int blocks,
                                   int clipped_samples, double elapsed_ms,
                                   const snd_quantum_source_spatial_t *spatial)
{
    qge_quantum_runtime_t *rt = qa_runtime();
    qge_state_probe_t probe;
    uint64_t elapsed_ticks;
    uint64_t spatial_hash;
    int frame, server_time_msec;

    if (!rt)
        return;

    qa_runtime_stamp(rt, &frame, &server_time_msec);
    memset(&probe, 0, sizeof(probe));
    probe.frame = frame;
    probe.server_time_msec = server_time_msec;
    probe.domain = QGE_DOMAIN_AUDIO;
    probe.representation = QGE_REP_DCT_TRANSDUCER;
    probe.subject_id = subject_id;
    probe.flags = flags | qa_source_spatial_flags(spatial);
    elapsed_ticks = elapsed_ms > 0.0 ? (uint64_t)(elapsed_ms * 1000.0) : 0u;
    spatial_hash = qa_source_spatial_hash(spatial);
    probe.state_hash = ((uint64_t)(uint32_t)subject_id << 32) ^
                       ((uint64_t)(uint32_t)samples << 8) ^
                       ((uint64_t)(uint32_t)clipped_samples << 48) ^
                       (uint64_t)(uint32_t)blocks ^
                       elapsed_ticks ^
                       spatial_hash;
    probe.entropy = qa_clamp01(snd_quantum_spread.value);
    probe.coherence = 1.0 - qa_clamp01(snd_quantum_mix.value);
    probe.max_probability = qa_clamp01(snd_quantum_mix.value);
    probe.total_probability = (double)samples;
    probe.active_basis_count = basis_count;
    probe.qubit_count = NUM_QUBITS * 2;
    probe.memory_bytes = (uint64_t)QA_BLOCK_SIZE * sizeof(float) * 6u;
    q_strlcpy(probe.label, label, sizeof(probe.label));
    qge_quantum_record_probe(rt, &probe);
}

static void qa_record_source_spatial_probe(int subject_id,
                                           const snd_quantum_source_spatial_t *spatial)
{
    qge_quantum_runtime_t *rt = qa_runtime();
    qge_state_probe_t probe;
    int frame, server_time_msec;

    if (!rt || !qa_source_spatial_valid(spatial))
        return;

    qa_runtime_stamp(rt, &frame, &server_time_msec);
    memset(&probe, 0, sizeof(probe));
    probe.frame = frame;
    probe.server_time_msec = server_time_msec;
    probe.domain = QGE_DOMAIN_AUDIO;
    probe.representation = QGE_REP_DCT_TRANSDUCER;
    probe.subject_id = subject_id;
    probe.flags = qa_source_spatial_flags(spatial);
    probe.state_hash = qa_source_spatial_hash(spatial);
    probe.entropy = (double)((qa_clamp11(spatial->pan_dot) + 1.0f) * 0.5f);
    probe.coherence = qa_clamp01(spatial->distance_attenuation);
    probe.max_probability = qa_clamp01((float)q_max(spatial->leftvol,
                                                   spatial->rightvol) / 255.0f);
    probe.total_probability = spatial->distance;
    probe.active_basis_count = spatial->leftvol + spatial->rightvol;
    probe.qubit_count = spatial->output_channels;
    probe.memory_bytes = sizeof(*spatial);
    q_strlcpy(probe.label, "audio_source_spatial", sizeof(probe.label));
    qge_quantum_record_probe(rt, &probe);
}

static void qa_record_source_measurement(int subject_id, int samples,
                                         int blocks, uint32_t flags,
                                         const snd_quantum_source_spatial_t *spatial)
{
    qge_quantum_runtime_t *rt = qa_runtime();
    qge_measurement_event_t measurement;
    uint64_t spatial_hash;
    int frame, server_time_msec;

    if (!rt)
        return;

    spatial_hash = qa_source_spatial_hash(spatial);
    qa_runtime_stamp(rt, &frame, &server_time_msec);
    memset(&measurement, 0, sizeof(measurement));
    measurement.domain = QGE_DOMAIN_AUDIO;
    measurement.kind = QGE_MEASURE_AUDIO_BLOCK;
    measurement.boundary = QGE_OBSERVE_AUDIO_MIX;
    measurement.frame = frame;
    measurement.server_time_msec = server_time_msec;
    measurement.subject_id = subject_id;
    measurement.flags = flags | qa_source_spatial_flags(spatial);
    measurement.basis_index = (uint64_t)blocks;
    measurement.probability = qa_clamp01(snd_quantum_mix.value);
    measurement.phase = quantum_time;
    measurement.entropy_offset = spatial_hash;
    measurement.trace_id = ((uint64_t)(uint32_t)samples << 32) ^
                           (spatial_hash & 0xffffffffu);
    qge_quantum_record_measurement(rt, &measurement);
}

static void qa_record_source_fallback(int subject_id, int reason_code,
                                      int samples, const char *reason,
                                      const snd_quantum_source_spatial_t *spatial)
{
    qge_quantum_runtime_t *rt = qa_runtime();
    qge_fallback_event_t fallback;
    char message[QGE_TRACE_MESSAGE_MAX];
    int frame, server_time_msec;

    if (!rt)
        return;

    if (qa_source_spatial_valid(spatial)) {
        q_snprintf(message, sizeof(message),
                   "%s dist=%.1f pan=%.2f att=%.2f l=%d r=%d",
                   reason, spatial->distance, qa_clamp11(spatial->pan_dot),
                   qa_clamp01(spatial->distance_attenuation),
                   spatial->leftvol, spatial->rightvol);
    } else {
        q_strlcpy(message, reason, sizeof(message));
    }

    qa_runtime_stamp(rt, &frame, &server_time_msec);
    memset(&fallback, 0, sizeof(fallback));
    fallback.frame = frame;
    fallback.server_time_msec = server_time_msec;
    fallback.domain = QGE_DOMAIN_AUDIO;
    fallback.representation = QGE_REP_DCT_TRANSDUCER;
    fallback.subject_id = subject_id;
    fallback.reason_code = reason_code;
    fallback.metric_value = (double)samples;
    q_strlcpy(fallback.message, message, sizeof(fallback.message));
    qge_quantum_record_fallback(rt, &fallback);
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

    if (!S_QuantumPostMixMode())
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
                q_strlcpy(probe.label, "audio_transducer", sizeof(probe.label));
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

void S_QuantumSourceBeginFrame(void)
{
    if (!S_QuantumSourceMode())
        return;

    memset(&qa_source_stats, 0, sizeof(qa_source_stats));
    q_strlcpy(qa_source_stats.last_source_name, "none",
              sizeof(qa_source_stats.last_source_name));
    q_strlcpy(qa_source_stats.last_fallback_reason, "none",
              sizeof(qa_source_stats.last_fallback_reason));
    qa_source_frame_active = true;
}

void S_QuantumSourceNote(int entnum, int entchannel, const char *name,
                         const snd_quantum_source_spatial_t *spatial)
{
    if (!S_QuantumSourceMode())
        return;
    if (!qa_source_frame_active)
        S_QuantumSourceBeginFrame();

    qa_source_stats.source_count++;
    qa_source_stats.last_subject_id = qa_source_subject_id(entnum, entchannel);
    q_strlcpy(qa_source_stats.last_source_name,
              (name && name[0]) ? name : "unknown",
              sizeof(qa_source_stats.last_source_name));
    qa_source_note_spatial(spatial);
    qa_record_source_spatial_probe(qa_source_stats.last_subject_id, spatial);
}

void S_QuantumProcessSource(portable_samplepair_t *sourcebuffer, int count,
                            int entnum, int entchannel, const char *name,
                            const snd_quantum_source_spatial_t *spatial)
{
    const int subject_id = qa_source_subject_id(entnum, entchannel);
    const float spread = qa_clamp01(snd_quantum_spread.value);
    const float mix = qa_clamp01(snd_quantum_mix.value);
    const int full_blocks = count / QA_BLOCK_SIZE;
    const int remainder = count % QA_BLOCK_SIZE;
    int processed_blocks = 0;
    int processed_samples = 0;
    int clipped_samples = 0;
    uint32_t flags = 0;
    double start_time;

    if (!S_QuantumSourceMode() || !sourcebuffer || count <= 0)
        return;
    if (!qa_source_frame_active)
        S_QuantumSourceBeginFrame();

    qa_source_stats.last_subject_id = subject_id;
    if (name && name[0]) {
        q_strlcpy(qa_source_stats.last_source_name, name,
                  sizeof(qa_source_stats.last_source_name));
    }
    qa_source_update_last_spatial(spatial);

    if (!quantum_initialized || !transducer_l || !transducer_r ||
        !dct_table || mix <= 0.0f) {
        int blocks = qa_block_count_for_samples(count);
        const char *reason = qa_source_runtime_fallback_reason(mix);
        qa_source_stats.skipped_blocks += blocks;
        qa_source_note_fallback(QA_SOURCE_FALLBACK_RUNTIME, blocks,
                                reason);
        qa_record_source_fallback(subject_id, QA_SOURCE_FALLBACK_RUNTIME,
                                  count, reason, spatial);
        return;
    }

    if (full_blocks <= 0) {
        qa_source_stats.skipped_blocks++;
        qa_source_note_fallback(QA_SOURCE_FALLBACK_SHORT_BLOCK, 1,
                                "audio_source_short_block");
        qa_record_source_fallback(subject_id, QA_SOURCE_FALLBACK_SHORT_BLOCK,
                                  count, "audio_source_short_block",
                                  spatial);
        return;
    }

    start_time = Sys_DoubleTime();
    for (int block = 0; block < full_blocks; block++) {
        portable_samplepair_t dry[QA_BLOCK_SIZE];
        portable_samplepair_t *out = sourcebuffer + block * QA_BLOCK_SIZE;
        qboolean invalid_block = false;
        int block_clipped = 0;

        memcpy(dry, out, sizeof(dry));

        for (int i = 0; i < QA_BLOCK_SIZE; i++) {
            input_buffer_l[i] = (float)out[i].left / QA_SAMPLE_SCALE;
            input_buffer_r[i] = (float)out[i].right / QA_SAMPLE_SCALE;
        }

        dct_forward(input_buffer_l, freq_l);
        dct_forward(input_buffer_r, freq_r);
        qge_transducer_process(transducer_l, freq_l, QA_NUM_BINS, spread,
                               quantum_time);
        qge_transducer_process(transducer_r, freq_r, QA_NUM_BINS, spread,
                               quantum_time);
        dct_inverse(freq_l, output_buffer_l);
        dct_inverse(freq_r, output_buffer_r);

        for (int i = 0; i < QA_BLOCK_SIZE; i++) {
            float wet_l = output_buffer_l[i] * 0.7f;
            float wet_r = output_buffer_r[i] * 0.7f;
            const float threshold = 0.5f;
            float dry_l = (float)dry[i].left / QA_SAMPLE_SCALE;
            float dry_r = (float)dry[i].right / QA_SAMPLE_SCALE;

            if (fabsf(wet_l) > threshold) {
                float sign = (wet_l >= 0.0f) ? 1.0f : -1.0f;
                float excess = fabsf(wet_l) - threshold;
                wet_l = sign * (threshold + excess / (1.0f + excess * 2.0f));
            }
            if (fabsf(wet_r) > threshold) {
                float sign = (wet_r >= 0.0f) ? 1.0f : -1.0f;
                float excess = fabsf(wet_r) - threshold;
                wet_r = sign * (threshold + excess / (1.0f + excess * 2.0f));
            }

            wet_l = dry_l * (1.0f - mix) + wet_l * mix;
            wet_r = dry_r * (1.0f - mix) + wet_r * mix;

            if (!isfinite(wet_l) || !isfinite(wet_r)) {
                invalid_block = true;
                break;
            }

            out[i].left = qa_paint_sample_from_float(wet_l, &block_clipped);
            out[i].right = qa_paint_sample_from_float(wet_r, &block_clipped);
        }

        if (invalid_block) {
            memcpy(out, dry, sizeof(dry));
            qa_source_note_fallback(QA_SOURCE_FALLBACK_INVALID_BLOCK, 1,
                                    "audio_source_invalid_block");
            qa_record_source_fallback(subject_id,
                                      QA_SOURCE_FALLBACK_INVALID_BLOCK,
                                      QA_BLOCK_SIZE,
                                      "audio_source_invalid_block",
                                      spatial);
            continue;
        }

        processed_blocks++;
        processed_samples += QA_BLOCK_SIZE;
        clipped_samples += block_clipped;
        quantum_time += (double)QA_BLOCK_SIZE / 11025.0;
    }

    qa_source_stats.transducer_ms += (Sys_DoubleTime() - start_time) * 1000.0;

    if (remainder > 0) {
        qa_source_stats.skipped_blocks++;
        qa_source_note_fallback(QA_SOURCE_FALLBACK_REMAINDER, 1,
                                "audio_source_remainder_block");
        qa_record_source_fallback(subject_id, QA_SOURCE_FALLBACK_REMAINDER,
                                  remainder, "audio_source_remainder_block",
                                  spatial);
    }

    if (processed_blocks > 0) {
        flags |= QA_SOURCE_FLAG_PROCESSED;
        if (clipped_samples > 0)
            flags |= QA_SOURCE_FLAG_CLIPPED;
        qa_source_stats.processed_sources++;
        qa_source_stats.processed_blocks += processed_blocks;
        qa_source_stats.processed_samples += processed_samples;
        qa_source_stats.clipped_samples += clipped_samples;
        qa_record_source_probe(subject_id, "audio_source", flags,
                               QA_NUM_BINS * 2, processed_samples,
                               processed_blocks, clipped_samples,
                               qa_source_stats.transducer_ms, spatial);
        qa_record_source_measurement(subject_id, processed_samples,
                                     processed_blocks, flags, spatial);
    }
}

void S_QuantumSourceEndFrame(void)
{
    snd_quantum_source_spatial_t empty_spatial;
    const snd_quantum_source_spatial_t *last_spatial;
    int spatial_valid;
    double avg_distance = 0.0;
    double avg_abs_pan = 0.0;
    double avg_attenuation = 0.0;
    uint32_t flags = 0;

    if (!qa_source_frame_active)
        return;

    memset(&empty_spatial, 0, sizeof(empty_spatial));
    spatial_valid = qa_source_spatial_valid(&qa_source_stats.last_spatial);
    last_spatial = spatial_valid ? &qa_source_stats.last_spatial : &empty_spatial;
    if (qa_source_stats.spatial_sources > 0) {
        avg_distance = qa_source_stats.spatial_distance_sum /
                       qa_source_stats.spatial_sources;
        avg_abs_pan = qa_source_stats.spatial_abs_pan_sum /
                      qa_source_stats.spatial_sources;
        avg_attenuation = qa_source_stats.spatial_attenuation_sum /
                          qa_source_stats.spatial_sources;
    }

    if (qa_source_stats.dry_fallback_blocks > 0)
        flags |= QA_SOURCE_FLAG_DRY_FALLBACK;
    if (qa_source_stats.processed_blocks > 0)
        flags |= QA_SOURCE_FLAG_PROCESSED;
    if (qa_source_stats.clipped_samples > 0)
        flags |= QA_SOURCE_FLAG_CLIPPED;
    flags |= qa_source_spatial_flags(last_spatial);

    if (qa_source_stats.source_count > 0 ||
        qa_source_stats.processed_blocks > 0 ||
        qa_source_stats.dry_fallback_blocks > 0) {
        Con_DPrintf("QGE audio source owner=audio_source "
                    "source_count=%d processed_sources=%d "
                    "processed_blocks=%d processed_samples=%d "
                    "skipped_blocks=%d dry_fallback_blocks=%d "
                    "clipping=%d transducer_ms=%.3f last_subject=%d "
                    "last_source=%s fallback_runtime=%d "
                    "fallback_short=%d fallback_invalid=%d "
                    "fallback_remainder=%d last_fallback=%s "
                    "spatial_sources=%d avg_distance=%.1f "
                    "avg_abs_pan=%.3f avg_atten=%.3f "
                    "source_origin=(%.1f,%.1f,%.1f) "
                    "listener_origin=(%.1f,%.1f,%.1f) "
                    "listener_forward=(%.2f,%.2f,%.2f) "
                    "listener_right=(%.2f,%.2f,%.2f) "
                    "distance=%.1f pan=%.3f attenuation=%.3f "
                    "spatial_volumes=%d/%d/%d spatial_channels=%d "
                    "spatial_valid=%d\n",
                    qa_source_stats.source_count,
                    qa_source_stats.processed_sources,
                    qa_source_stats.processed_blocks,
                    qa_source_stats.processed_samples,
                    qa_source_stats.skipped_blocks,
                    qa_source_stats.dry_fallback_blocks,
                    qa_source_stats.clipped_samples,
                    qa_source_stats.transducer_ms,
                    qa_source_stats.last_subject_id,
                    qa_source_stats.last_source_name,
                    qa_source_stats.fallback_runtime_blocks,
                    qa_source_stats.fallback_short_blocks,
                    qa_source_stats.fallback_invalid_blocks,
                    qa_source_stats.fallback_remainder_blocks,
                    qa_source_stats.last_fallback_reason,
                    qa_source_stats.spatial_sources,
                    avg_distance,
                    avg_abs_pan,
                    avg_attenuation,
                    last_spatial->source_origin[0],
                    last_spatial->source_origin[1],
                    last_spatial->source_origin[2],
                    last_spatial->listener_origin[0],
                    last_spatial->listener_origin[1],
                    last_spatial->listener_origin[2],
                    last_spatial->listener_forward[0],
                    last_spatial->listener_forward[1],
                    last_spatial->listener_forward[2],
                    last_spatial->listener_right[0],
                    last_spatial->listener_right[1],
                    last_spatial->listener_right[2],
                    last_spatial->distance,
                    qa_clamp11(last_spatial->pan_dot),
                    qa_clamp01(last_spatial->distance_attenuation),
                    last_spatial->leftvol,
                    last_spatial->rightvol,
                    last_spatial->master_vol,
                    last_spatial->output_channels,
                    spatial_valid);

        qa_record_source_probe(qa_source_stats.source_count,
                               "audio_source_frame", flags,
                               qa_source_stats.processed_blocks > 0 ?
                                   QA_NUM_BINS * 2 : 0,
                               qa_source_stats.processed_samples,
                               qa_source_stats.processed_blocks,
                               qa_source_stats.clipped_samples,
                               qa_source_stats.transducer_ms,
                               last_spatial);
    }

    qa_source_frame_active = false;
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
