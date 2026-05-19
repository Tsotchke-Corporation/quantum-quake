/**
 * @file qge_rng.c
 * @brief Quantum Random Number Generator for QGE
 *
 * Replaces Quake's M_Random() with genuine quantum randomness.
 * Uses Moonlab's QRNG v3.0 with proper entropy layering:
 *
 * Architecture:
 * - Layer 1: Hardware entropy pool (NIST SP 800-90B health tested)
 * - Layer 2: Quantum state evolution and measurement
 * - Layer 3: Output buffer for efficient batch generation
 *
 * This is the PRODUCTION implementation using Bell-verified quantum engine.
 */

#include "qge.h"
#include "../deps/moonlab/src/applications/qrng.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>

/* ============================================================================
 * State
 * ============================================================================ */

static qrng_v3_ctx_t *rng_ctx = NULL;
static volatile bool rng_initialized = false;
static volatile bool rng_failed = false;
static qge_quantum_runtime_t *rng_runtime = NULL;

/* Thread safety - mutex protects ALL RNG state access */
static pthread_mutex_t rng_mutex = PTHREAD_MUTEX_INITIALIZER;

/* Batch buffer for efficient generation (matches QGE API expectations) */
#define RNG_BATCH_SIZE 256
static uint16_t rng_batch[RNG_BATCH_SIZE];
static int rng_batch_index = RNG_BATCH_SIZE; /* Start empty to force first fill */
static uint64_t rng_fallback_state = 0x5151455f524e4731ULL;

/* ============================================================================
 * Internal Functions
 * ============================================================================ */

static uint64_t qge_rng_fallback_u64(void) {
    uint64_t z = (rng_fallback_state += 0x9e3779b97f4a7c15ULL);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}

static void fill_rng_batch_fallback(void) {
    for (int i = 0; i < RNG_BATCH_SIZE; i++) {
        rng_batch[i] = (uint16_t)(qge_rng_fallback_u64() >> 16);
    }
    rng_batch_index = 0;
}

/**
 * @brief Initialize the quantum RNG.
 *
 * Called with rng_mutex held.
 */
static int ensure_rng_initialized(void) {
    if (rng_failed) return -1;
    if (rng_initialized) return 0;

    /* Initialize QRNG v3 with custom configuration for game use */
    qrng_v3_config_t config;
    qrng_v3_get_default_config(&config);

    /* Customize for game RNG:
     * - 8 qubits gives us 256-dimensional state space
     * - DIRECT mode for maximum speed (games need low latency)
     * - Disable Bell monitoring during gameplay (run on init only)
     * - Enable SIMD optimizations
     */
    config.num_qubits = 8;
    config.mode = QRNG_V3_MODE_DIRECT;
    config.enable_bell_monitoring = 0;  /* We'll verify once at init */
    config.bell_test_interval = 0;       /* Disabled during gameplay */
    config.enable_simd = 1;
    config.output_buffer_size = 4096;    /* 4KB buffer for batch efficiency */
    config.enable_background_entropy = 1;

    qrng_v3_error_t err = qrng_v3_init_with_config(&rng_ctx, &config);
    if (err != QRNG_V3_SUCCESS) {
        fprintf(stderr, "QGE RNG: Failed to initialize QRNG v3: %s\n",
                qrng_v3_error_string(err));
        rng_failed = true;
        return -1;
    }

    /* Run initial Bell test to verify quantum behavior */
    bell_test_result_t bell_result = qrng_v3_verify_quantum(rng_ctx, 1000);
    if (bell_result.chsh_value < 2.4) {
        fprintf(stderr, "QGE RNG: Warning - Bell test CHSH=%.3f (expected >2.4)\n",
                bell_result.chsh_value);
    }

    /* Memory barrier before publishing initialized flag */
    __sync_synchronize();
    rng_initialized = true;
    return 0;
}

/**
 * @brief Fill the batch buffer with quantum random values
 */
static void fill_rng_batch(void) {
    if (rng_failed) {
        fill_rng_batch_fallback();
        return;
    }
    if (ensure_rng_initialized() != 0) {
        fill_rng_batch_fallback();
        return;
    }

    /* Generate bytes using QRNG v3 */
    uint8_t buffer[RNG_BATCH_SIZE * 2];
    qrng_v3_error_t err = qrng_v3_bytes(rng_ctx, buffer, sizeof(buffer));
    if (err != QRNG_V3_SUCCESS) {
        fprintf(stderr, "QGE RNG: Failed to generate bytes: %s\n",
                qrng_v3_error_string(err));
        rng_failed = true;
        fill_rng_batch_fallback();
        return;
    }

    /* Convert to 16-bit values */
    for (int i = 0; i < RNG_BATCH_SIZE; i++) {
        rng_batch[i] = (uint16_t)(buffer[i * 2] | (buffer[i * 2 + 1] << 8));
    }

    rng_batch_index = 0;
}

static uint16_t qge_random_raw(void) {
    uint16_t result;

    pthread_mutex_lock(&rng_mutex);
    if (rng_batch_index >= RNG_BATCH_SIZE) {
        fill_rng_batch();
    }
    result = rng_batch[rng_batch_index++];
    pthread_mutex_unlock(&rng_mutex);
    return result;
}

static uint64_t qge_rng_entropy_callback(void *user_data,
                                         qge_quantum_domain_t domain,
                                         int subject_id) {
    uint64_t value = 0;

    (void)user_data;
    (void)domain;
    (void)subject_id;

    for (int i = 0; i < 4; i++) {
        value |= (uint64_t)qge_random_raw() << (i * 16);
    }
    return value;
}

/* ============================================================================
 * Public API
 * ============================================================================ */

int qge_rng_init(void) {
    /* Quick check without mutex */
    if (rng_failed) {
        return -1;
    }
    if (rng_initialized) {
        return 0; /* Already initialized */
    }

    pthread_mutex_lock(&rng_mutex);

    /* Double-check under mutex */
    if (rng_failed) {
        pthread_mutex_unlock(&rng_mutex);
        return -1;
    }
    if (rng_initialized) {
        pthread_mutex_unlock(&rng_mutex);
        return 0;
    }

    fprintf(stderr, "QGE RNG: Initializing Quantum RNG (Moonlab QRNG v3)...\n");

    /* Initialize QRNG v3 with custom configuration for game use */
    qrng_v3_config_t config;
    qrng_v3_get_default_config(&config);

    /* Customize for game RNG:
     * - 8 qubits gives us 256-dimensional state space
     * - DIRECT mode for maximum speed (games need low latency)
     * - Disable Bell monitoring during gameplay (run on init only)
     * - Enable SIMD optimizations
     */
    config.num_qubits = 8;
    config.mode = QRNG_V3_MODE_DIRECT;
    config.enable_bell_monitoring = 0;  /* We'll verify once at init */
    config.bell_test_interval = 0;       /* Disabled during gameplay */
    config.enable_simd = 1;
    config.output_buffer_size = 4096;    /* 4KB buffer for batch efficiency */
    config.enable_background_entropy = 1;

    qrng_v3_error_t err = qrng_v3_init_with_config(&rng_ctx, &config);
    if (err != QRNG_V3_SUCCESS) {
        fprintf(stderr, "QGE RNG: Failed to initialize QRNG v3: %s\n",
                qrng_v3_error_string(err));
        rng_failed = true;
        pthread_mutex_unlock(&rng_mutex);
        return -1;
    }

    /* Run initial Bell test to verify quantum behavior */
    bell_test_result_t bell_result = qrng_v3_verify_quantum(rng_ctx, 1000);
    if (bell_result.chsh_value < 2.4) {
        fprintf(stderr, "QGE RNG: Warning - Bell test CHSH=%.3f (expected >2.4)\n",
                bell_result.chsh_value);
    } else {
        fprintf(stderr, "QGE RNG: Bell test passed - CHSH=%.3f (quantum verified!)\n",
                bell_result.chsh_value);
    }

    /* Pre-fill the batch buffer so first rand() call is fast */
    /* Note: We already hold the mutex, so fill directly (don't call fill_rng_batch
     * which would call ensure_rng_initialized and cause double init) */

    /* Generate bytes using QRNG v3 */
    uint8_t buffer[RNG_BATCH_SIZE * 2];
    err = qrng_v3_bytes(rng_ctx, buffer, sizeof(buffer));
    if (err == QRNG_V3_SUCCESS) {
        for (int i = 0; i < RNG_BATCH_SIZE; i++) {
            rng_batch[i] = (uint16_t)(buffer[i * 2] | (buffer[i * 2 + 1] << 8));
        }
        rng_batch_index = 0;
    } else {
        fprintf(stderr, "QGE RNG: Failed to prefill QRNG batch: %s\n",
                qrng_v3_error_string(err));
        fill_rng_batch_fallback();
    }

    /* Memory barrier before publishing initialized flag */
    __sync_synchronize();
    rng_initialized = true;

    pthread_mutex_unlock(&rng_mutex);

    fprintf(stderr, "QGE RNG: Quantum RNG ready\n");
    return 0;
}

uint16_t qge_random(void) {
    qge_quantum_runtime_t *runtime = rng_runtime;

    if (runtime) {
        uint64_t value = qge_quantum_entropy_u64(runtime, QGE_DOMAIN_RNG, 0);
        qge_measurement_event_t event;

        memset(&event, 0, sizeof(event));
        event.domain = QGE_DOMAIN_RNG;
        event.kind = QGE_MEASURE_RNG_BATCH;
        event.boundary = QGE_OBSERVE_FRAME_BOUNDARY;
        event.frame = qge_quantum_runtime_get_frame(runtime);
        event.server_time_msec = qge_quantum_runtime_get_server_time_msec(runtime);
        event.basis_index = value;
        event.probability = 1.0;
        qge_quantum_record_measurement(runtime, &event);
        return (uint16_t)value;
    }
    return qge_random_raw();
}

void qge_random_batch(uint16_t* out, int count) {
    if (!out || count <= 0) return;

    if (rng_runtime) {
        for (int i = 0; i < count; i++) {
            out[i] = qge_random();
        }
        return;
    }

    pthread_mutex_lock(&rng_mutex);
    int filled = 0;
    while (filled < count) {
        if (rng_batch_index >= RNG_BATCH_SIZE) {
            fill_rng_batch();
        }

        int available = RNG_BATCH_SIZE - rng_batch_index;
        int to_copy = (count - filled < available) ? (count - filled) : available;

        memcpy(out + filled, rng_batch + rng_batch_index, to_copy * sizeof(uint16_t));
        rng_batch_index += to_copy;
        filled += to_copy;
    }
    pthread_mutex_unlock(&rng_mutex);
}

float qge_random_float(void) {
    return (float)qge_random() / 65536.0f;
}

int qge_m_random(void) {
    /* Quake's M_Random returns 0-255 */
    return qge_random() & 0xFF;
}

void qge_rng_set_runtime(qge_quantum_runtime_t* runtime) {
    rng_runtime = runtime;
    if (rng_runtime) {
        if (qge_quantum_runtime_get_entropy_source(rng_runtime) !=
            QGE_ENTROPY_SOURCE_REPLAY) {
            qge_quantum_runtime_set_entropy_source(rng_runtime,
                                                   QGE_ENTROPY_SOURCE_QRNG,
                                                   qge_rng_entropy_callback,
                                                   NULL);
        }
    }
}

/* ============================================================================
 * Cleanup
 * ============================================================================ */

void qge_rng_shutdown(void) {
    pthread_mutex_lock(&rng_mutex);
    rng_runtime = NULL;
    if (rng_ctx) {
        qrng_v3_free(rng_ctx);
        rng_ctx = NULL;
    }
    rng_initialized = false;
    rng_batch_index = RNG_BATCH_SIZE;
    rng_failed = false;
    pthread_mutex_unlock(&rng_mutex);
}
