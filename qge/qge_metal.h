/**
 * @file qge_metal.h
 * @brief Metal GPU acceleration for Quantum Game Engine
 *
 * Provides GPU-accelerated quantum rendering operations:
 * - Screen probability marginalization (2^28 → 64×64)
 * - Inverse DWT reconstruction
 * - Sparse coefficient extraction
 *
 * PERFORMANCE TARGET: 60+ FPS on M2 Mac Studio
 */

#ifndef QGE_METAL_H
#define QGE_METAL_H

#include <complex.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Forward declarations to avoid circular includes */
struct dwt_framebuffer_s;
typedef struct dwt_framebuffer_s dwt_framebuffer_t;

/* Metal compute context from Moonlab */
typedef struct metal_compute_ctx metal_compute_ctx_t;
typedef struct metal_buffer metal_buffer_t;

/* External Metal functions we need */
extern metal_compute_ctx_t* metal_compute_init(void);
extern void metal_compute_free(metal_compute_ctx_t* ctx);
extern int metal_is_available(void);
extern metal_buffer_t* metal_buffer_create(metal_compute_ctx_t* ctx, size_t size);
extern void* metal_buffer_contents(metal_buffer_t* buffer);
extern void metal_buffer_free(metal_buffer_t* buffer);

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================
 * GPU CONTEXT FOR QGE
 * ============================================================================ */

typedef struct {
    metal_compute_ctx_t* metal_ctx;     /* Moonlab Metal context */
    metal_buffer_t* amplitude_buffer;    /* Quantum state on GPU */
    metal_buffer_t* probability_buffer;  /* Screen probabilities (64×64) */
    metal_buffer_t* dwt_coeff_buffer;    /* DWT coefficients */
    metal_buffer_t* output_buffer;       /* Final rendered output */

    /* Configuration */
    int screen_res;                      /* Screen resolution (64) */
    int num_qubits;                      /* Total qubits (28) */
    int position_qubits;                 /* Position qubits (12 for 64×64) */

    /* Performance tracking */
    double last_marginalize_time_ms;
    double last_idwt_time_ms;
    double last_total_time_ms;

    /* Internal Objective-C++ state (pipeline states, command queue, etc.) */
    void* internal_ptr;

    bool initialized;
} qge_metal_ctx_t;

/**
 * @brief Initialize QGE Metal acceleration
 *
 * @param num_qubits Total qubits in quantum state (typically 28)
 * @param screen_res Screen resolution (typically 64)
 * @return QGE Metal context or NULL on failure
 */
qge_metal_ctx_t* qge_metal_init(int num_qubits, int screen_res);

/**
 * @brief Initialize QGE Metal sparse-DWT render bridge
 *
 * This compiles the Metal render kernels and attaches the Moonlab Metal
 * context without allocating the dense amplitude buffer used by full-state
 * marginalization. It is the safe real-time path for sparse DWT framebuffers.
 *
 * @param num_qubits Context qubit budget for evidence and optional dense paths
 * @param screen_res Sparse DWT reconstruction resolution
 * @return QGE Metal context or NULL on failure
 */
qge_metal_ctx_t* qge_metal_init_render_bridge(int num_qubits, int screen_res);

/**
 * @brief Free QGE Metal context
 */
void qge_metal_free(qge_metal_ctx_t* ctx);

/**
 * @brief Check if Metal acceleration is available
 */
bool qge_metal_available(void);

/* ============================================================================
 * PROBABILITY MARGINALIZATION (The key operation!)
 * ============================================================================
 *
 * Extracts screen probabilities from full quantum state.
 *
 * For 28 qubits with 12 position qubits (64×64 screen):
 * - Input: 2^28 = 268M complex amplitudes
 * - Output: 64×64 = 4096 probabilities
 * - Each output pixel = sum of |amp|² over 2^16 = 65536 states
 *
 * GPU APPROACH:
 * - One threadgroup per output pixel
 * - Each threadgroup sums 65536 amplitudes
 * - Parallel reduction within threadgroup
 *
 * EXPECTED PERFORMANCE: 5-10ms (vs 200ms+ on CPU)
 */

/**
 * @brief Extract screen probabilities from quantum state (GPU)
 *
 * Marginalizes over all non-position qubits to get P(x,y) grid.
 *
 * @param ctx QGE Metal context
 * @param amplitudes Input quantum state (2^num_qubits complex values)
 * @param probabilities Output screen grid (screen_res × screen_res floats)
 * @return 0 on success, -1 on error
 */
int qge_metal_marginalize_screen(
    qge_metal_ctx_t* ctx,
    const double _Complex* amplitudes,
    float* probabilities
);

/**
 * @brief Extract screen probabilities using GPU buffers directly
 *
 * Zero-copy version for when amplitudes are already on GPU.
 *
 * @param ctx QGE Metal context
 * @return 0 on success, -1 on error
 */
int qge_metal_marginalize_screen_gpu(qge_metal_ctx_t* ctx);

/* ============================================================================
 * DWT OPERATIONS (GPU-ACCELERATED)
 * ============================================================================ */

/**
 * @brief GPU-accelerated inverse DWT reconstruction
 *
 * Transforms wavelet coefficients back to spatial domain.
 *
 * @param ctx QGE Metal context
 * @param coefficients DWT coefficients (pyramid layout)
 * @param output Spatial output (screen_res × screen_res)
 * @param num_levels DWT decomposition levels
 * @return 0 on success, -1 on error
 */
int qge_metal_inverse_dwt(
    qge_metal_ctx_t* ctx,
    const float* coefficients,
    float* output,
    int num_levels
);

/**
 * @brief GPU-accelerated Haar inverse DWT (single level)
 *
 * @param ctx QGE Metal context
 * @param input Current level coefficients
 * @param output Next level output
 * @param width Current width
 * @param height Current height
 * @return 0 on success, -1 on error
 */
int qge_metal_haar_inverse_level(
    qge_metal_ctx_t* ctx,
    metal_buffer_t* input,
    metal_buffer_t* output,
    int width,
    int height
);

/* ============================================================================
 * SPARSE COEFFICIENT OPERATIONS
 * ============================================================================ */

/**
 * @brief Extract non-zero DWT coefficients from quantum amplitudes (GPU)
 *
 * Scans quantum state and extracts significant wavelet coefficients.
 * Exploits ~8-10% sparsity for efficiency.
 *
 * @param ctx QGE Metal context
 * @param amplitudes Quantum state
 * @param indices Output array of non-zero coefficient indices
 * @param values Output array of coefficient values
 * @param max_coeffs Maximum coefficients to extract
 * @param threshold Minimum coefficient magnitude
 * @param num_extracted Output: actual number extracted
 * @return 0 on success, -1 on error
 */
int qge_metal_extract_sparse_coeffs(
    qge_metal_ctx_t* ctx,
    const double _Complex* amplitudes,
    uint64_t* indices,
    float* values,
    int max_coeffs,
    float threshold,
    int* num_extracted
);

/* ============================================================================
 * COMPLETE RENDER PIPELINE (GPU)
 * ============================================================================
 *
 * Full quantum rendering pipeline on GPU:
 * 1. Copy amplitudes to GPU (if needed)
 * 2. Marginalize to screen probabilities
 * 3. Apply inverse DWT (if using DWT encoding)
 * 4. Convert to RGB output
 */

/**
 * @brief Complete GPU render pipeline
 *
 * @param ctx QGE Metal context
 * @param dwt_fb DWT framebuffer with quantum state
 * @param output RGB output buffer (width × height × 3)
 * @param width Output width
 * @param height Output height
 * @return 0 on success, -1 on error
 */
int qge_metal_render_frame(
    qge_metal_ctx_t* ctx,
    dwt_framebuffer_t* dwt_fb,
    uint8_t* output,
    int width,
    int height
);

/* ============================================================================
 * PERFORMANCE MONITORING
 * ============================================================================ */

typedef struct {
    double marginalize_ms;    /* Time for probability extraction */
    double idwt_ms;           /* Time for inverse DWT */
    double copy_ms;           /* Time for CPU↔GPU transfers */
    double total_ms;          /* Total frame time */
    int coefficients_active;  /* Number of active DWT coefficients */
    float gpu_utilization;    /* GPU utilization percentage */
} qge_metal_stats_t;

/**
 * @brief Get performance statistics
 */
qge_metal_stats_t qge_metal_get_stats(qge_metal_ctx_t* ctx);

/**
 * @brief Print performance summary
 */
void qge_metal_print_stats(qge_metal_ctx_t* ctx);

#ifdef __cplusplus
}
#endif

#endif /* QGE_METAL_H */
