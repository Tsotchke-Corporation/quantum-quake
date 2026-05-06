/**
 * @file qge_init.c
 * @brief Quantum Game Engine - Initialization and Context Management
 */

#include "qge.h"
#include "../deps/moonlab/src/quantum/state.h"
#include "../deps/moonlab/src/quantum/gates.h"
#include "../deps/moonlab/src/quantum/measurement.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#if defined(__APPLE__)
#include <sys/sysctl.h>
#endif

/* ============================================================================
 * Context Structure
 * ============================================================================ */

struct qge_context_s {
    qge_hardware_tier_t tier;
    qge_backend_t backend;
    qge_render_mode_t render_mode;
    qge_resolution_t resolution;
    dwt_config_t dwt_config;

    int num_qubits;
    bool adaptive_quality;

    /* Profiling */
    qge_profile_t profile;

    /* Shared quantum runtime contract and trace spine */
    qge_quantum_runtime_t* quantum_runtime;

    /* Stable map/resource registry and immutable frame snapshot */
    qge_world_t* world;
    qge_frame_snapshot_t frame_snapshot;

    /* Moonlab quantum states */
    quantum_state_t render_state;   /* For rendering (main state) */
    quantum_state_t ai_state;       /* For AI decisions */
    bool render_state_initialized;
    bool ai_state_initialized;

    /* GPU context */
    void* gpu_context;  /* Metal/Vulkan context */
};

/* Global context for convenience functions */
static qge_context_t* g_qge_ctx = NULL;

/* ============================================================================
 * Hardware Detection
 * ============================================================================ */

qge_hardware_tier_t qge_detect_hardware(void) {
    /* Get system memory */
    size_t total_memory = 0;

#if defined(__APPLE__)
    size_t len = sizeof(total_memory);
    sysctlbyname("hw.memsize", &total_memory, &len, NULL, 0);
#elif defined(__linux__)
    FILE* f = fopen("/proc/meminfo", "r");
    if (f) {
        char line[128];
        while (fgets(line, sizeof(line), f)) {
            if (strncmp(line, "MemTotal:", 9) == 0) {
                sscanf(line + 9, "%zu", &total_memory);
                total_memory *= 1024; /* Convert from KB to bytes */
                break;
            }
        }
        fclose(f);
    }
#endif

    size_t gb = total_memory / (1024ULL * 1024ULL * 1024ULL);

    /* Determine tier based on memory */
    /* 28 qubits = 4.3GB state vector */
    if (gb >= 64) {
        return QGE_TIER_ULTRA;   /* Can handle 28 qubits easily */
    } else if (gb >= 32) {
        return QGE_TIER_HIGH;    /* 26 qubits = 1.1GB */
    } else if (gb >= 16) {
        return QGE_TIER_MEDIUM;  /* 24 qubits = 268MB */
    } else if (gb >= 8) {
        return QGE_TIER_LOW;     /* 22 qubits = 67MB */
    } else {
        return QGE_TIER_POTATO;  /* 20 qubits = 16MB */
    }
}

static qge_backend_t detect_backend(void) {
#if defined(__APPLE__)
    /* Metal on macOS */
    return QGE_BACKEND_METAL;
#elif defined(__linux__)
    /* Check for AVX-512/AVX2 */
    #if defined(__AVX512F__)
        return QGE_BACKEND_AVX512;
    #elif defined(__AVX2__)
        return QGE_BACKEND_AVX2;
    #else
        return QGE_BACKEND_FALLBACK;
    #endif
#else
    return QGE_BACKEND_FALLBACK;
#endif
}

static int qubits_for_tier(qge_hardware_tier_t tier) {
    switch (tier) {
        case QGE_TIER_ULTRA:  return 28;
        case QGE_TIER_HIGH:   return 26;
        case QGE_TIER_MEDIUM: return 24;
        case QGE_TIER_LOW:    return 22;
        case QGE_TIER_POTATO: return 20;
        default:              return 20;
    }
}

static size_t qge_state_memory_bytes(int num_qubits) {
    if (num_qubits < 0 || num_qubits >= 63) {
        return 0;
    }
    return (1ULL << num_qubits) * sizeof(double) * 2;
}

static quantum_state_t* qge_lazy_state_init(qge_context_t* ctx,
                                             quantum_state_t* state,
                                             bool* initialized,
                                             int num_qubits,
                                             const char* label) {
    if (!ctx || !state || !initialized) {
        return NULL;
    }
    if (*initialized) {
        return state;
    }

    qs_error_t err = quantum_state_init(state, num_qubits);
    if (err != QS_SUCCESS) {
        fprintf(stderr, "QGE: Failed to init %s (%d qubits)\n",
                label ? label : "quantum state", num_qubits);
        return NULL;
    }

    *initialized = true;
    ctx->profile.memory_used_bytes += qge_state_memory_bytes(num_qubits);
    return state;
}

qge_resolution_t qge_recommended_resolution(qge_hardware_tier_t tier) {
    switch (tier) {
        case QGE_TIER_ULTRA:  return QGE_RES_1280x720;
        case QGE_TIER_HIGH:   return QGE_RES_800x600;
        case QGE_TIER_MEDIUM: return QGE_RES_640x480;
        case QGE_TIER_LOW:    return QGE_RES_320x200;
        case QGE_TIER_POTATO: return QGE_RES_NATIVE;
        default:              return QGE_RES_640x480;
    }
}

dwt_config_t qge_dwt_config_for_tier(qge_hardware_tier_t tier) {
    dwt_config_t config;

    switch (tier) {
        case QGE_TIER_ULTRA:
            config.mode = DWT_MODE_DAUBECHIES4;
            config.num_levels = 5;
            config.base_resolution = 640;
            config.gpu_reconstruct = true;
            config.sparsity_threshold = 0.001f;
            break;

        case QGE_TIER_HIGH:
            config.mode = DWT_MODE_HAAR;
            config.num_levels = 5;
            config.base_resolution = 512;
            config.gpu_reconstruct = true;
            config.sparsity_threshold = 0.005f;
            break;

        case QGE_TIER_MEDIUM:
            config.mode = DWT_MODE_HAAR;
            config.num_levels = 4;
            config.base_resolution = 256;
            config.gpu_reconstruct = true;
            config.sparsity_threshold = 0.01f;
            break;

        default:
            config.mode = DWT_MODE_HAAR;
            config.num_levels = 4;
            config.base_resolution = 256;
            config.gpu_reconstruct = false;
            config.sparsity_threshold = 0.02f;
            break;
    }

    return config;
}

/* ============================================================================
 * Initialization
 * ============================================================================ */

qge_context_t* qge_init(void) {
    qge_hardware_tier_t tier = qge_detect_hardware();
    qge_resolution_t res = qge_recommended_resolution(tier);

    return qge_init_with_config(tier, QGE_RENDER_DWT, res);
}

qge_context_t* qge_init_with_config(qge_hardware_tier_t tier,
                                     qge_render_mode_t mode,
                                     qge_resolution_t resolution) {
    qge_context_t* ctx = calloc(1, sizeof(qge_context_t));
    if (!ctx) {
        fprintf(stderr, "QGE: Failed to allocate context\n");
        return NULL;
    }

    ctx->tier = tier;
    ctx->backend = detect_backend();
    ctx->render_mode = mode;
    ctx->resolution = resolution;
    ctx->num_qubits = qubits_for_tier(tier);
    ctx->dwt_config = qge_dwt_config_for_tier(tier);
    ctx->adaptive_quality = true;

    /* Initialize profiling */
    memset(&ctx->profile, 0, sizeof(qge_profile_t));
    ctx->profile.current_qubits = ctx->num_qubits;

    ctx->quantum_runtime = qge_quantum_runtime_create();
    if (!ctx->quantum_runtime) {
        fprintf(stderr, "QGE: Failed to allocate quantum runtime\n");
        free(ctx);
        return NULL;
    }

    ctx->world = qge_world_create();
    if (!ctx->world) {
        fprintf(stderr, "QGE: Failed to allocate world registry\n");
        qge_quantum_runtime_free(ctx->quantum_runtime);
        free(ctx);
        return NULL;
    }
    qge_frame_snapshot_reset(&ctx->frame_snapshot);

    /* Full dense state vectors are initialized lazily. The Quake DWT path uses
     * sparse coefficient arrays by default, so reserving 28-qubit dense states
     * here wastes several GB before a frame is rendered. */
    ctx->profile.memory_used_bytes = 0;

    /* Set global context */
    g_qge_ctx = ctx;

    /* Print initialization info */
    const char* tier_names[] = {"Ultra", "High", "Medium", "Low", "Potato"};
    const char* backend_names[] = {"Metal", "Vulkan", "OpenCL", "AVX-512",
                                    "AVX2", "NEON", "Fallback"};
    const char* mode_names[] = {"DWT", "Scanline", "Frequency", "Direct", "Diffusion"};

    printf("\n");
    printf("==================================================================\n");
    printf("           QUANTUM GAME ENGINE INITIALIZED\n");
    printf("==================================================================\n");
    printf("  Hardware Tier: %-10s  Backend: %-10s\n",
           tier_names[ctx->tier], backend_names[ctx->backend]);
    printf("  Qubits: %-2d               Render Mode: %-10s\n",
           ctx->num_qubits, mode_names[ctx->render_mode]);
    printf("  State Memory: lazy sparse (%.1f GB dense cap)\n",
           qge_state_memory_bytes(ctx->num_qubits) / (1024.0 * 1024.0 * 1024.0));
    printf("==================================================================\n");
    printf("\n");

    return ctx;
}

void qge_shutdown(qge_context_t* ctx) {
    if (!ctx) return;

    if (ctx->render_state_initialized) {
        quantum_state_free(&ctx->render_state);
    }
    if (ctx->ai_state_initialized) {
        quantum_state_free(&ctx->ai_state);
    }

    /* Shutdown RNG */
    extern void qge_rng_shutdown(void);
    qge_rng_shutdown();

    qge_quantum_runtime_free(ctx->quantum_runtime);
    ctx->quantum_runtime = NULL;

    qge_world_free(ctx->world);
    ctx->world = NULL;

    if (g_qge_ctx == ctx) {
        g_qge_ctx = NULL;
    }

    free(ctx);

    printf("QGE: Shutdown complete\n");
}

/* ============================================================================
 * Profiling
 * ============================================================================ */

void qge_get_profile(qge_context_t* ctx, qge_profile_t* profile) {
    if (!ctx || !profile) return;
    memcpy(profile, &ctx->profile, sizeof(qge_profile_t));
}

void qge_set_adaptive_quality(qge_context_t* ctx, bool enabled) {
    if (!ctx) return;
    ctx->adaptive_quality = enabled;
}

qge_quantum_runtime_t* qge_get_quantum_runtime(qge_context_t* ctx) {
    return ctx ? ctx->quantum_runtime : NULL;
}

/* ============================================================================
 * Global Context Accessors (for convenience functions)
 * ============================================================================ */

qge_context_t* qge_get_context(void) {
    return g_qge_ctx;
}

qge_world_t* qge_get_world(qge_context_t* ctx) {
    return ctx ? ctx->world : NULL;
}

qge_frame_snapshot_t* qge_get_frame_snapshot(qge_context_t* ctx) {
    return ctx ? &ctx->frame_snapshot : NULL;
}

const qge_frame_snapshot_t* qge_get_frame_snapshot_const(qge_context_t* ctx) {
    return ctx ? &ctx->frame_snapshot : NULL;
}

quantum_state_t* qge_get_render_state(qge_context_t* ctx) {
    return qge_lazy_state_init(ctx, &ctx->render_state,
                               &ctx->render_state_initialized,
                               24, "render state");
}

quantum_state_t* qge_get_ai_state(qge_context_t* ctx) {
    return qge_lazy_state_init(ctx, &ctx->ai_state,
                               &ctx->ai_state_initialized,
                               24, "AI state");
}
