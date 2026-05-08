/**
 * @file qge_render.c
 * @brief Quantum Rendering with Discrete Wavelet Transform (DWT)
 *
 * The core quantum rendering module. Scene geometry is encoded as wavelet
 * coefficients in quantum amplitude space, then extracted and transformed
 * back to spatial pixels.
 *
 * Key insight: Quake scenes are SPARSE in wavelet domain (~8-10% non-zero).
 * Walls create localized edge coefficients, flat areas have zero detail.
 *
 * Qubit layout for 32-qubit sparse DWT state:
 * - Bits 0-2:   Level selector (8 decomposition levels)
 * - Bits 3-4:   Subband selector (LL, HL, LH, HH)
 * - Bits 5-14:  Coefficient X (1024 positions)
 * - Bits 15-24: Coefficient Y (1024 positions)
 * - Bits 25-29: Coefficient value (32 amplitude levels)
 * - Bits 30-31: Color channel (Y, Cb, Cr, alpha)
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
 * Constants and Bit Layout
 * ============================================================================ */

/* Qubit allocation for DWT rendering */
#define LEVEL_BITS      3   /* 8 decomposition levels max */
#define SUBBAND_BITS    2   /* 4 subbands: LL, HL, LH, HH */
#define COEFF_X_BITS    10  /* 1024 coefficient X positions */
#define COEFF_Y_BITS    10  /* 1024 coefficient Y positions */
#define VALUE_BITS      5   /* 32 amplitude levels */
#define COLOR_BITS      2   /* 4 channels: Y, Cb, Cr, alpha */

#define LEVEL_MASK      ((1u << LEVEL_BITS) - 1u)
#define SUBBAND_MASK    ((1u << SUBBAND_BITS) - 1u)
#define COEFF_X_MASK    ((1u << COEFF_X_BITS) - 1u)
#define COEFF_Y_MASK    ((1u << COEFF_Y_BITS) - 1u)
#define VALUE_MASK      ((1u << VALUE_BITS) - 1u)
#define COLOR_MASK      ((1u << COLOR_BITS) - 1u)

/* Bit offsets */
#define LEVEL_OFFSET    0
#define SUBBAND_OFFSET  (LEVEL_OFFSET + LEVEL_BITS)
#define COEFF_X_OFFSET  (SUBBAND_OFFSET + SUBBAND_BITS)
#define COEFF_Y_OFFSET  (COEFF_X_OFFSET + COEFF_X_BITS)
#define VALUE_OFFSET    (COEFF_Y_OFFSET + COEFF_Y_BITS)
#define COLOR_OFFSET    (VALUE_OFFSET + VALUE_BITS)

/* Total qubits needed */
#define DWT_TOTAL_QUBITS (LEVEL_BITS + SUBBAND_BITS + COEFF_X_BITS + \
                          COEFF_Y_BITS + VALUE_BITS + COLOR_BITS)

/* Maximum coefficient tracking */
#define MAX_ACTIVE_COEFFS 1048576
#define DWT_MAX_DENSE_QUBITS 28

/* ============================================================================
 * Framebuffer Structures
 * ============================================================================ */

struct qge_framebuffer_s {
    quantum_state_t* state;
    quantum_entropy_ctx_t* entropy;
    entropy_ctx_t* hw_entropy;
    int width;
    int height;
    int num_qubits;
    float* probability_cache;   /* Cached probabilities for display */
    bool initialized;
};

struct dwt_framebuffer_s {
    quantum_state_t* state;
    quantum_entropy_ctx_t* entropy;
    entropy_ctx_t* hw_entropy;
    dwt_config_t config;
    int num_qubits;

    /* Coefficient tracking for sparse encoding */
    int active_coeff_count;
    uint64_t* active_indices;   /* State indices with non-zero amplitude */
    float* active_values;       /* Corresponding values */
    int* active_offsets;        /* DWT coefficient-buffer offsets */

    /* Reconstruction buffers */
    float* coeff_buffer;        /* Extracted coefficients */
    float* transform_scratch;   /* Row/column scratch for DWT passes */
    int coeff_size;             /* Size of coefficient buffer */
    int transform_scratch_size;  /* Number of floats in transform_scratch */

    bool initialized;
};

/* ============================================================================
 * Entropy Callback
 * ============================================================================ */

static int render_entropy_callback(void *user_data, uint8_t *buffer, size_t size) {
    entropy_ctx_t *ctx = (entropy_ctx_t *)user_data;
    return entropy_get_bytes(ctx, buffer, size);
}

/* ============================================================================
 * State Index Encoding
 * ============================================================================ */

/**
 * @brief Encode DWT coefficient location into state index
 */
static uint64_t encode_dwt_index(int level, dwt_subband_t subband,
                                  int cx, int cy, int value, int color) {
    uint64_t index = 0;
    index |= ((uint64_t)(level & LEVEL_MASK)) << LEVEL_OFFSET;
    index |= ((uint64_t)(subband & SUBBAND_MASK)) << SUBBAND_OFFSET;
    index |= ((uint64_t)(cx & COEFF_X_MASK)) << COEFF_X_OFFSET;
    index |= ((uint64_t)(cy & COEFF_Y_MASK)) << COEFF_Y_OFFSET;
    index |= ((uint64_t)(value & VALUE_MASK)) << VALUE_OFFSET;
    index |= ((uint64_t)(color & COLOR_MASK)) << COLOR_OFFSET;
    return index;
}

/* ============================================================================
 * Basic Framebuffer (Direct Probability Rendering)
 * ============================================================================ */

qge_framebuffer_t* qge_framebuffer_create(qge_context_t* ctx) {
    if (!ctx) return NULL;

    qge_framebuffer_t* fb = calloc(1, sizeof(qge_framebuffer_t));
    if (!fb) return NULL;

    /* Use context's render state directly */
    extern quantum_state_t* qge_get_render_state(qge_context_t* ctx);
    fb->state = qge_get_render_state(ctx);
    if (!fb->state) {
        free(fb);
        return NULL;
    }
    fb->num_qubits = 24;  /* 64x64 = 12 position qubits + 12 game state */
    fb->width = 64;
    fb->height = 64;

    /* Initialize entropy */
    fb->hw_entropy = malloc(sizeof(entropy_ctx_t));
    if (!fb->hw_entropy || entropy_init(fb->hw_entropy) != ENTROPY_SUCCESS) {
        free(fb->hw_entropy);
        free(fb);
        return NULL;
    }

    fb->entropy = malloc(sizeof(quantum_entropy_ctx_t));
    if (!fb->entropy) {
        entropy_free(fb->hw_entropy);
        free(fb->hw_entropy);
        free(fb);
        return NULL;
    }
    quantum_entropy_init(fb->entropy, render_entropy_callback, fb->hw_entropy);

    /* Allocate probability cache */
    fb->probability_cache = calloc(fb->width * fb->height, sizeof(float));
    if (!fb->probability_cache) {
        free(fb->entropy);
        entropy_free(fb->hw_entropy);
        free(fb->hw_entropy);
        free(fb);
        return NULL;
    }

    fb->initialized = true;
    return fb;
}

void qge_framebuffer_reset(qge_framebuffer_t* fb) {
    if (!fb || !fb->state) return;
    quantum_state_reset(fb->state);
    memset(fb->probability_cache, 0, fb->width * fb->height * sizeof(float));
}

void qge_framebuffer_free(qge_framebuffer_t* fb) {
    if (!fb) return;

    free(fb->probability_cache);
    free(fb->entropy);
    if (fb->hw_entropy) {
        entropy_free(fb->hw_entropy);
        free(fb->hw_entropy);
    }
    free(fb);
}

/* ============================================================================
 * DWT Framebuffer
 * ============================================================================ */

dwt_framebuffer_t* qge_dwt_framebuffer_create(qge_context_t* ctx,
                                               const dwt_config_t* config) {
    /* ctx is optional - we create our own quantum state */
    (void)ctx;

    dwt_framebuffer_t* fb = calloc(1, sizeof(dwt_framebuffer_t));
    if (!fb) return NULL;

    /* Copy configuration */
    if (config) {
        fb->config = *config;
    } else {
        /* Use default config for medium tier */
        extern dwt_config_t qge_dwt_config_for_tier(qge_hardware_tier_t tier);
        fb->config = qge_dwt_config_for_tier(QGE_TIER_MEDIUM);
    }

    /* Calculate qubit requirements */
    fb->num_qubits = DWT_TOTAL_QUBITS;

    /* Allocate the dense quantum state only for the measurement path. The
     * real-time Quake renderer uses the sparse active_indices/active_values
     * representation by default. A 32-qubit dense DWT state is not viable for
     * live Quake rendering, so high-resolution sparse framebuffers force the
     * sparse extraction path. */
    if (fb->config.quantum_measurement_extract &&
        fb->num_qubits > DWT_MAX_DENSE_QUBITS) {
        fb->config.quantum_measurement_extract = false;
    }
    if (fb->config.quantum_measurement_extract) {
        fb->state = malloc(sizeof(quantum_state_t));
        if (!fb->state) {
            free(fb);
            return NULL;
        }

        qs_error_t err = quantum_state_init(fb->state, fb->num_qubits);
        if (err != QS_SUCCESS) {
            free(fb->state);
            free(fb);
            return NULL;
        }

        fb->hw_entropy = malloc(sizeof(entropy_ctx_t));
        if (!fb->hw_entropy || entropy_init(fb->hw_entropy) != ENTROPY_SUCCESS) {
            quantum_state_free(fb->state);
            free(fb->state);
            free(fb->hw_entropy);
            free(fb);
            return NULL;
        }

        fb->entropy = malloc(sizeof(quantum_entropy_ctx_t));
        if (!fb->entropy) {
            quantum_state_free(fb->state);
            free(fb->state);
            entropy_free(fb->hw_entropy);
            free(fb->hw_entropy);
            free(fb);
            return NULL;
        }
        quantum_entropy_init(fb->entropy, render_entropy_callback, fb->hw_entropy);
    }

    /* Allocate coefficient tracking */
    fb->active_indices = calloc(MAX_ACTIVE_COEFFS, sizeof(uint64_t));
    fb->active_values = calloc(MAX_ACTIVE_COEFFS, sizeof(float));
    fb->active_offsets = calloc(MAX_ACTIVE_COEFFS, sizeof(int));
    if (!fb->active_indices || !fb->active_values || !fb->active_offsets) {
        if (fb->state) {
            quantum_state_free(fb->state);
            free(fb->state);
        }
        free(fb->entropy);
        if (fb->hw_entropy) {
            entropy_free(fb->hw_entropy);
            free(fb->hw_entropy);
        }
        free(fb->active_indices);
        free(fb->active_values);
        free(fb->active_offsets);
        free(fb);
        return NULL;
    }
    fb->active_coeff_count = 0;

    /* Allocate reconstruction buffers */
    int base_res = fb->config.base_resolution;
    fb->coeff_size = base_res * base_res;

    fb->coeff_buffer = calloc(fb->coeff_size, sizeof(float));
    fb->transform_scratch_size = base_res;
    fb->transform_scratch = calloc(fb->transform_scratch_size, sizeof(float));
    if (!fb->coeff_buffer || !fb->transform_scratch) {
        if (fb->state) {
            quantum_state_free(fb->state);
            free(fb->state);
        }
        free(fb->entropy);
        if (fb->hw_entropy) {
            entropy_free(fb->hw_entropy);
            free(fb->hw_entropy);
        }
        free(fb->active_indices);
        free(fb->active_values);
        free(fb->active_offsets);
        free(fb->coeff_buffer);
        free(fb->transform_scratch);
        free(fb);
        return NULL;
    }

    fb->initialized = true;
    return fb;
}

void qge_dwt_framebuffer_reset(dwt_framebuffer_t* fb) {
    if (!fb) return;

    /* Only clear sparse coefficient tracking and work buffers for the default
     * path. A dense state exists only when quantum_measurement_extract is
     * enabled; resetting 2^28 amplitudes every frame is not viable otherwise. */
    if (fb->state && fb->config.quantum_measurement_extract) {
        quantum_state_reset(fb->state);
    } else if (fb->state) {
        /* Zero only the previously-written amplitudes (sparse clear) */
        for (int i = 0; i < fb->active_coeff_count; i++) {
            uint64_t idx = fb->active_indices[i];
            if (idx < fb->state->state_dim) {
                fb->state->amplitudes[idx] = 0.0 + 0.0*I;
            }
        }
        fb->state->amplitudes[0] = 1.0 + 0.0*I;
    }
    fb->active_coeff_count = 0;
}

void qge_dwt_framebuffer_free(dwt_framebuffer_t* fb) {
    if (!fb) return;

    if (fb->state) {
        quantum_state_free(fb->state);
        free(fb->state);
    }
    free(fb->entropy);
    if (fb->hw_entropy) {
        entropy_free(fb->hw_entropy);
        free(fb->hw_entropy);
    }
    free(fb->active_indices);
    free(fb->active_values);
    free(fb->active_offsets);
    free(fb->coeff_buffer);
    free(fb->transform_scratch);
    free(fb);
}

/* ============================================================================
 * Wavelet Coefficient Encoding
 * ============================================================================ */

static int qge_dwt_coeff_offset(const dwt_framebuffer_t* fb,
                                int level,
                                dwt_subband_t subband,
                                int cx,
                                int cy) {
    int base_res, level_size, half;
    int out_x, out_y;

    if (!fb) return -1;
    base_res = fb->config.base_resolution;
    if (base_res <= 0 || level < 0) return -1;

    level_size = base_res >> level;
    half = level_size / 2;
    if (half <= 0) return -1;

    if (cx >= half) cx = half - 1;
    if (cy >= half) cy = half - 1;
    if (cx < 0) cx = 0;
    if (cy < 0) cy = 0;

    switch (subband) {
        case SUBBAND_LL:
            out_x = cx;
            out_y = cy;
            break;
        case SUBBAND_HL:
            out_x = half + cx;
            out_y = cy;
            break;
        case SUBBAND_LH:
            out_x = cx;
            out_y = half + cy;
            break;
        case SUBBAND_HH:
            out_x = half + cx;
            out_y = half + cy;
            break;
        default:
            return -1;
    }

    if (out_x < 0 || out_x >= base_res || out_y < 0 || out_y >= base_res)
        return -1;
    return out_y * base_res + out_x;
}

static void qge_add_wavelet_coeff_with_threshold(dwt_framebuffer_t* fb,
                                                  int level,
                                                  dwt_subband_t subband,
                                                  int cx, int cy,
                                                  float value,
                                                  float threshold) {
    int coeff_offset;
    uint64_t state_index = 0;

    if (!fb || !fb->active_indices || !fb->active_values || !fb->active_offsets) return;
    if (fb->active_coeff_count >= MAX_ACTIVE_COEFFS) return;

    /* Skip if below sparsity threshold */
    if (threshold < 0.0f) threshold = 0.0f;
    if (fabsf(value) < threshold) return;

    coeff_offset = qge_dwt_coeff_offset(fb, level, subband, cx, cy);
    if (coeff_offset < 0) return;

    if (fb->state) {
        int quantized_value = (int)(fabsf(value) * 31.0f);
        if (quantized_value > 31) quantized_value = 31;
        state_index = encode_dwt_index(level, subband, cx, cy,
                                       quantized_value, 0);
        if (state_index < fb->state->state_dim) {
            fb->state->amplitudes[state_index] += (double)value;
        }
    }

    /* Track active coefficient */
    fb->active_indices[fb->active_coeff_count] = state_index;
    fb->active_values[fb->active_coeff_count] = value;
    fb->active_offsets[fb->active_coeff_count] = coeff_offset;
    fb->active_coeff_count++;
}

void qge_add_wavelet_coeff(dwt_framebuffer_t* fb,
                            int level,
                            dwt_subband_t subband,
                            int cx, int cy,
                            float value) {
    if (!fb) return;
    qge_add_wavelet_coeff_with_threshold(fb, level, subband, cx, cy, value,
                                          fb->config.sparsity_threshold);
}

void qge_encode_wall_dwt(dwt_framebuffer_t* fb,
                          const screen_rect_t* bounds,
                          float brightness,
                          float depth) {
    if (!fb || !bounds) return;

    int x1 = bounds->x1;
    int y1 = bounds->y1;
    int x2 = bounds->x2;
    int y2 = bounds->y2;

    /* Clamp to valid range */
    int max_res = fb->config.base_resolution;
    if (x1 < 0) x1 = 0;
    if (y1 < 0) y1 = 0;
    if (x2 >= max_res) x2 = max_res - 1;
    if (y2 >= max_res) y2 = max_res - 1;

    /* Walls create edge coefficients in wavelet domain:
     * - Vertical edges (left/right): LH subband coefficients
     * - Horizontal edges (top/bottom): HL subband coefficients
     * - Interior: LL (approximation) coefficients at coarser levels
     */

    float edge_strength = brightness * (1.0f - depth * 0.1f);

    for (int level = 0; level < fb->config.num_levels; level++) {
        /* Each detail subband at DWT level L has half the width/height of the
         * region being reconstructed at that level. Convert from pixel-space
         * bounds into subband-local coordinates with 2^(L+1), not 2^L; using
         * full-resolution coordinates here clamps right/bottom-half geometry
         * onto the subband edge and creates artificial scan-line bands. */
        int scale = 1 << (level + 1);

        float level_strength = edge_strength;
        if (level == 0) {
            level_strength *= 0.08f;
        } else if (level == 1) {
            level_strength *= 0.45f;
        }

        /* Left vertical edge: LH coefficients */
        for (int y = y1 / scale; y <= y2 / scale; y++) {
            qge_add_wavelet_coeff(fb, level, SUBBAND_LH,
                                   x1 / scale, y, level_strength);
        }

        /* Right vertical edge: LH coefficients */
        for (int y = y1 / scale; y <= y2 / scale; y++) {
            qge_add_wavelet_coeff(fb, level, SUBBAND_LH,
                                   x2 / scale, y, level_strength);
        }

        /* Top horizontal edge: HL coefficients */
        for (int x = x1 / scale; x <= x2 / scale; x++) {
            qge_add_wavelet_coeff(fb, level, SUBBAND_HL,
                                   x, y1 / scale, level_strength);
        }

        /* Bottom horizontal edge: HL coefficients */
        for (int x = x1 / scale; x <= x2 / scale; x++) {
            qge_add_wavelet_coeff(fb, level, SUBBAND_HL,
                                   x, y2 / scale, level_strength);
        }

        /* Corners: HH coefficients */
        qge_add_wavelet_coeff(fb, level, SUBBAND_HH,
                               x1 / scale, y1 / scale, level_strength * 0.5f);
        qge_add_wavelet_coeff(fb, level, SUBBAND_HH,
                               x2 / scale, y1 / scale, level_strength * 0.5f);
        qge_add_wavelet_coeff(fb, level, SUBBAND_HH,
                               x1 / scale, y2 / scale, level_strength * 0.5f);
        qge_add_wavelet_coeff(fb, level, SUBBAND_HH,
                               x2 / scale, y2 / scale, level_strength * 0.5f);

        /* Reduce edge strength for higher levels */
        edge_strength *= 0.7f;
    }

    /* Interior fill: LL coefficients at coarsest level
     *
     * The LL (approximation) subband carries the DC component — the average
     * pixel brightness. For proper Haar inverse DWT reconstruction, the LL
     * coefficient must represent the actual desired brightness, not a scaled-
     * down version. The Haar inverse formula:
     *   even[i] = low[i] + high[i] * 0.5
     *   odd[i]  = low[i] - high[i] * 0.5
     * So the LL coefficient propagates directly as the base brightness.
     */
    int coarse_level = fb->config.num_levels - 1;
    int coarse_scale = 1 << fb->config.num_levels;
    float fill = brightness * (1.0f - depth * 0.1f) * 1.35f;  /* Depth-attenuated field */

    for (int y = y1 / coarse_scale; y <= y2 / coarse_scale; y++) {
        for (int x = x1 / coarse_scale; x <= x2 / coarse_scale; x++) {
            qge_add_wavelet_coeff(fb, coarse_level, SUBBAND_LL, x, y, fill);
        }
    }
}

void qge_encode_sprite_dwt(dwt_framebuffer_t* fb,
                            int screen_x, int screen_y,
                            int sprite_width, int sprite_height,
                            float brightness,
                            float depth) {
    if (!fb) return;

    /* Sprites are treated as rectangular objects with edges */
    screen_rect_t bounds = {
        .x1 = screen_x,
        .y1 = screen_y,
        .x2 = screen_x + sprite_width,
        .y2 = screen_y + sprite_height
    };

    /* Sprites have higher contrast edges than walls */
    qge_encode_wall_dwt(fb, &bounds, brightness * 1.2f, depth);
}

/* ============================================================================
 * Coefficient Extraction
 * ============================================================================ */

void qge_extract_coefficients(dwt_framebuffer_t* fb, float* coeffs) {
    if (!fb || !fb->active_indices || !fb->active_values || !coeffs) return;

    int base_res = fb->config.base_resolution;
    memset(coeffs, 0, base_res * base_res * sizeof(float));

    /* Extract from tracked active coefficients (sparse representation)
     *
     * Standard 2D DWT pyramid layout:
     * For 256x256 with 4 levels:
     *
     * +--------+--------+----------------+--------------------------------+
     * | LL3    | HL3    |                |                                |
     * | 16x16  | 16x16  |     HL2        |                                |
     * +--------+--------+    32x32       |           HL1                  |
     * | LH3    | HH3    |                |          64x64                 |
     * | 16x16  | 16x16  |                |                                |
     * +--------+--------+----------------+                                |
     * |                 |                |                                |
     * |      LH2        |      HH2       |                                |
     * |     32x32       |     32x32      |                                |
     * +--------+--------+----------------+--------------------------------+
     * |                                  |                                |
     * |              LH1                 |              HH1               |
     * |             64x64                |             64x64              |
     * +----------------------------------+--------------------------------+
     *
     * Level N operates on region of size (base_res >> N)
     * The HL, LH, HH subbands are stored in the "detail" regions
     */

    for (int i = 0; i < fb->active_coeff_count; i++) {
        float value = fb->active_values[i];
        int offset = fb->active_offsets[i];

        if ((unsigned)offset < (unsigned)(base_res * base_res))
            coeffs[offset] += value;
    }
}

/* ============================================================================
 * Inverse DWT (Haar Lifting Scheme)
 * ============================================================================ */

/**
 * @brief 1D Haar inverse wavelet transform (lifting scheme)
 */
static void haar_inverse_1d_scratch(float* data, int n, float* temp) {
    if (n < 2) return;

    bool free_temp = false;
    if (!temp) {
        temp = malloc(n * sizeof(float));
        free_temp = true;
    }
    if (!temp) return;

    int half = n / 2;

    /* Haar inverse: even[i] = low[i] + high[i]/2, odd[i] = low[i] - high[i]/2 */
    for (int i = 0; i < half; i++) {
        float low = data[i];
        float high = data[half + i];
        temp[2 * i] = low + high * 0.5f;
        temp[2 * i + 1] = low - high * 0.5f;
    }

    memcpy(data, temp, n * sizeof(float));
    if (free_temp) free(temp);
}

static void haar_inverse_1d(float* data, int n) {
    haar_inverse_1d_scratch(data, n, NULL);
}

/**
 * @brief 1D Haar inverse with stride (for vertical transform)
 */
static void haar_inverse_1d_strided_scratch(float* data, int n, int stride, float* temp) {
    if (n < 2) return;

    bool free_temp = false;
    if (!temp) {
        temp = malloc(n * sizeof(float));
        free_temp = true;
    }
    if (!temp) return;

    /* Copy strided data to temp */
    for (int i = 0; i < n; i++) {
        temp[i] = data[i * stride];
    }

    int half = n / 2;
    for (int i = 0; i < half; i++) {
        float low = temp[i];
        float high = temp[half + i];
        data[(2 * i) * stride] = low + high * 0.5f;
        data[(2 * i + 1) * stride] = low - high * 0.5f;
    }

    if (free_temp) free(temp);
}

static void haar_inverse_1d_strided(float* data, int n, int stride) {
    haar_inverse_1d_strided_scratch(data, n, stride, NULL);
}

/**
 * @brief 1D Haar forward wavelet transform matching haar_inverse_1d().
 */
static void haar_forward_1d_scratch(float* data, int n, float* temp) {
    if (n < 2) return;

    bool free_temp = false;
    if (!temp) {
        temp = malloc(n * sizeof(float));
        free_temp = true;
    }
    if (!temp) return;

    int half = n / 2;
    for (int i = 0; i < half; i++) {
        float even = data[2 * i];
        float odd = data[2 * i + 1];
        temp[i] = (even + odd) * 0.5f;
        temp[half + i] = even - odd;
    }

    memcpy(data, temp, n * sizeof(float));
    if (free_temp) free(temp);
}

/**
 * @brief 1D Haar forward transform with stride for vertical passes.
 */
static void haar_forward_1d_strided_scratch(float* data, int n, int stride, float* temp) {
    if (n < 2) return;

    bool free_temp = false;
    if (!temp) {
        temp = malloc(n * sizeof(float));
        free_temp = true;
    }
    if (!temp) return;

    for (int i = 0; i < n; i++) {
        temp[i] = data[i * stride];
    }

    int half = n / 2;
    for (int i = 0; i < half; i++) {
        float even = temp[2 * i];
        float odd = temp[2 * i + 1];
        data[i * stride] = (even + odd) * 0.5f;
        data[(half + i) * stride] = even - odd;
    }

    if (free_temp) free(temp);
}

static void qge_forward_haar_dwt(float* pixels,
                                  int width,
                                  int height,
                                  int levels,
                                  float* scratch) {
    if (!pixels || width <= 0 || height <= 0 || width != height) return;

    for (int level = 0; level < levels; level++) {
        int size = width >> level;
        if (size < 2) break;

        /* qge_inverse_dwt() applies row inverse then column inverse. The
         * matching forward transform must reverse that order at each level. */
        for (int x = 0; x < size; x++) {
            haar_forward_1d_strided_scratch(&pixels[x], size, width, scratch);
        }
        for (int y = 0; y < size; y++) {
            haar_forward_1d_scratch(&pixels[y * width], size, scratch);
        }
    }
}

/* ============================================================================
 * Daubechies-4 Inverse DWT (Lifting Scheme)
 * ============================================================================ */

/* Daubechies-4 inverse wavelet coefficients */
static const float D4_H0 =  0.4829629131445341f;
static const float D4_H1 =  0.8365163037378079f;
static const float D4_H2 =  0.2241438680420134f;
static const float D4_H3 = -0.1294095225512604f;

/**
 * @brief 1D Daubechies-4 inverse wavelet transform
 */
static void daub4_inverse_1d(float* data, int n) {
    if (n < 4) {
        haar_inverse_1d(data, n);  /* Fall back to Haar for tiny sizes */
        return;
    }

    float* temp = malloc(n * sizeof(float));
    if (!temp) return;

    int half = n / 2;

    for (int i = 0; i < n; i++) temp[i] = 0.0f;

    for (int i = 0; i < half; i++) {
        float low  = data[i];
        float high = data[half + i];

        /* D4 synthesis filter bank */
        int k = 2 * i;
        temp[k % n]       += D4_H0 * low + D4_H3 * high;
        temp[(k + 1) % n] += D4_H1 * low - D4_H2 * high;
        temp[(k + 2) % n] += D4_H2 * low + D4_H1 * high;
        temp[(k + 3) % n] += D4_H3 * low - D4_H0 * high;
    }

    memcpy(data, temp, n * sizeof(float));
    free(temp);
}

/**
 * @brief 1D Daubechies-4 inverse with stride (for vertical transform)
 */
static void daub4_inverse_1d_strided(float* data, int n, int stride) {
    if (n < 4) {
        haar_inverse_1d_strided(data, n, stride);
        return;
    }

    float* temp = malloc(n * sizeof(float));
    if (!temp) return;

    /* Copy strided data to temp */
    for (int i = 0; i < n; i++) {
        temp[i] = data[i * stride];
    }

    /* Apply inverse transform */
    daub4_inverse_1d(temp, n);

    /* Copy back to strided positions */
    for (int i = 0; i < n; i++) {
        data[i * stride] = temp[i];
    }

    free(temp);
}

static void qge_inverse_dwt_scratch(const float* coeffs, float* pixels,
                                    int width, int height, int levels,
                                    dwt_mode_t mode, float* scratch) {
    if (!coeffs || !pixels) return;

    /* Copy coefficients to output when callers do not already provide an
     * in-place reconstruction buffer. */
    if (pixels != coeffs)
        memcpy(pixels, coeffs, width * height * sizeof(float));

    /* Reconstruct from coarsest to finest level */
    for (int level = levels - 1; level >= 0; level--) {
        int size = width >> level;

        if (mode == DWT_MODE_DAUBECHIES4) {
            /* Daubechies-4: smoother reconstruction */
            for (int y = 0; y < size; y++) {
                daub4_inverse_1d(&pixels[y * width], size);
            }
            for (int x = 0; x < size; x++) {
                daub4_inverse_1d_strided(&pixels[x], size, width);
            }
        } else {
            /* Haar (default): fastest, sharp edges */
            for (int y = 0; y < size; y++) {
                haar_inverse_1d_scratch(&pixels[y * width], size, scratch);
            }
            for (int x = 0; x < size; x++) {
                haar_inverse_1d_strided_scratch(&pixels[x], size, width, scratch);
            }
        }
    }
}

void qge_inverse_dwt(const float* coeffs, float* pixels,
                     int width, int height, int levels,
                     dwt_mode_t mode) {
    qge_inverse_dwt_scratch(coeffs, pixels, width, height, levels, mode, NULL);
}

static void qge_dwt_encode_spatial_work(dwt_framebuffer_t* fb, float* work) {
    int base_res;
    int levels;

    if (!fb || !work) return;
    base_res = fb->config.base_resolution;
    levels = fb->config.num_levels;
    if (base_res <= 0 || levels <= 0) return;

    qge_forward_haar_dwt(work, base_res, base_res, levels,
                         fb->transform_scratch);

    for (int level = 0; level < levels; level++) {
        int size = base_res >> level;
        int half = size / 2;
        float threshold = fb->config.sparsity_threshold;
        if (half <= 0) break;

        /* Coarser subbands carry the large-area structure of walls, floors,
         * and lighting gradients. Keep them at a lower threshold than fine
         * texture detail so sparse reconstruction does not collapse broad
         * surfaces into visible block bands. */
        if (level >= levels - 2)
            threshold *= 0.20f;
        else if (level >= levels - 4)
            threshold *= 0.50f;

        for (int y = 0; y < half; y++) {
            for (int x = 0; x < half; x++) {
                qge_add_wavelet_coeff_with_threshold(fb, level, SUBBAND_HL, x, y,
                    work[y * base_res + half + x], threshold);
                qge_add_wavelet_coeff_with_threshold(fb, level, SUBBAND_LH, x, y,
                    work[(half + y) * base_res + x], threshold);
                qge_add_wavelet_coeff_with_threshold(fb, level, SUBBAND_HH, x, y,
                    work[(half + y) * base_res + half + x], threshold);
            }
        }
    }

    /* Only the coarsest LL block is a stable part of the final pyramid. */
    int coarse_level = levels - 1;
    int coarse_ll = base_res >> levels;
    if (coarse_ll < 1) coarse_ll = 1;
    for (int y = 0; y < coarse_ll; y++) {
        for (int x = 0; x < coarse_ll; x++) {
            qge_add_wavelet_coeff_with_threshold(fb, coarse_level, SUBBAND_LL, x, y,
                work[y * base_res + x],
                fb->config.sparsity_threshold * 0.10f);
        }
    }
}

void qge_dwt_encode_spatial(dwt_framebuffer_t* fb,
                            const float* pixels,
                            int width,
                            int height) {
    if (!fb || !pixels || !fb->coeff_buffer) return;

    int base_res = fb->config.base_resolution;
    if (base_res <= 0) return;

    /* Copy or nearest-resample the caller's spatial buffer into coeff_buffer.
     * The buffer then becomes an in-place forward-DWT work area. */
    if (width == base_res && height == base_res) {
        memcpy(fb->coeff_buffer, pixels, base_res * base_res * sizeof(float));
    } else {
        if (width <= 0 || height <= 0) return;
        for (int y = 0; y < base_res; y++) {
            int src_y = (y * height) / base_res;
            if (src_y >= height) src_y = height - 1;
            for (int x = 0; x < base_res; x++) {
                int src_x = (x * width) / base_res;
                if (src_x >= width) src_x = width - 1;
                fb->coeff_buffer[y * base_res + x] =
                    pixels[src_y * width + src_x];
            }
        }
    }

    qge_dwt_encode_spatial_work(fb, fb->coeff_buffer);
}

void qge_dwt_encode_spatial_inplace(dwt_framebuffer_t* fb,
                                    float* pixels,
                                    int width,
                                    int height) {
    if (!fb || !pixels) return;

    int base_res = fb->config.base_resolution;
    if (width == base_res && height == base_res) {
        qge_dwt_encode_spatial_work(fb, pixels);
        return;
    }
    qge_dwt_encode_spatial(fb, pixels, width, height);
}

/* ============================================================================
 * Full DWT Rendering Pipeline
 * ============================================================================ */

/**
 * @brief Render DWT framebuffer to output pixels
 *
 * Full quantum signal processing pipeline:
 * 1. Normalize quantum state (probability conservation)
 * 2. Extract wavelet coefficients from tracked or measured state
 * 3. Inverse DWT reconstruction (Haar or Daubechies-4)
 * 4. Output spatial pixel buffer
 */
void qge_dwt_render(dwt_framebuffer_t* fb, float* output) {
    if (!fb || !output) return;

    int base_res = fb->config.base_resolution;

    /* Step 0: Normalize quantum state only when using full measurement extraction.
     * quantum_state_normalize iterates all 2^28 = 268M amplitudes (4.3GB read),
     * which is too slow for real-time. The sparse coefficient path doesn't need it
     * since we read directly from active_indices/values. */
    if (fb->config.quantum_measurement_extract && fb->state && fb->active_coeff_count > 0) {
        quantum_state_normalize(fb->state);
    }

    /* Step 1: Extract coefficients directly into the caller's output buffer. */
    qge_extract_coefficients(fb, output);

    /* Step 2: Inverse DWT in place. */
    qge_inverse_dwt_scratch(output, output,
                            base_res, base_res, fb->config.num_levels,
                            fb->config.mode, fb->transform_scratch);
}

/* ============================================================================
 * Direct Probability Rendering (Fallback)
 * ============================================================================ */

void qge_project_to_display(qge_framebuffer_t* fb,
                             uint8_t* display,
                             int width, int height) {
    if (!fb || !fb->state || !display) return;

    /* Extract probabilities from quantum state */
    /* For 24-qubit state: 12 bits for position (64x64), 12 bits for color/depth */

    uint64_t state_dim = fb->state->state_dim;
    int fb_width = fb->width;
    int fb_height = fb->height;

    /* Reset probability cache */
    memset(fb->probability_cache, 0, fb_width * fb_height * sizeof(float));

    /* Marginalize over non-position qubits */
    for (uint64_t i = 0; i < state_dim; i++) {
        int x = i & 0x3F;           /* Bits 0-5: X position */
        int y = (i >> 6) & 0x3F;    /* Bits 6-11: Y position */

        double amp_real = creal(fb->state->amplitudes[i]);
        double amp_imag = cimag(fb->state->amplitudes[i]);
        float prob = (float)(amp_real * amp_real + amp_imag * amp_imag);

        if (x < fb_width && y < fb_height) {
            fb->probability_cache[y * fb_width + x] += prob;
        }
    }

    /* Scale probabilities and copy to display buffer */
    float max_prob = 0.0f;
    for (int i = 0; i < fb_width * fb_height; i++) {
        if (fb->probability_cache[i] > max_prob) {
            max_prob = fb->probability_cache[i];
        }
    }

    if (max_prob < 1e-10f) max_prob = 1.0f;  /* Avoid division by zero */

    /* Upscale from fb_width×fb_height to width×height */
    float scale_x = (float)fb_width / width;
    float scale_y = (float)fb_height / height;

    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int src_x = (int)(x * scale_x);
            int src_y = (int)(y * scale_y);

            if (src_x >= fb_width) src_x = fb_width - 1;
            if (src_y >= fb_height) src_y = fb_height - 1;

            float prob = fb->probability_cache[src_y * fb_width + src_x];
            uint8_t gray = (uint8_t)(255.0f * prob / max_prob);

            /* RGB output (grayscale for now) */
            int out_idx = (y * width + x) * 3;
            display[out_idx + 0] = gray;  /* R */
            display[out_idx + 1] = gray;  /* G */
            display[out_idx + 2] = gray;  /* B */
        }
    }
}

/* ============================================================================
 * Utility Functions
 * ============================================================================ */

/**
 * @brief Get number of active coefficients (sparsity measure)
 */
int qge_dwt_get_active_count(dwt_framebuffer_t* fb) {
    return fb ? fb->active_coeff_count : 0;
}

/**
 * @brief Get sparsity ratio (active / total possible)
 */
float qge_dwt_get_sparsity(dwt_framebuffer_t* fb) {
    if (!fb) return 0.0f;
    int total = fb->config.base_resolution * fb->config.base_resolution;
    return (float)fb->active_coeff_count / (float)total;
}
