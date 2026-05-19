/**
 * @file qge.h
 * @brief Quantum Game Engine - Main Header
 *
 * QGE provides the shared quantum-runtime contracts used by rendering,
 * AI, physics, audio, RNG, and visibility experiments.
 *
 * Primary rendering: Quantum DWT (Discrete Wavelet Transform)
 * - Scene data is encoded into sparse wavelet-style coefficient fields
 * - Dense Moonlab states are initialized lazily for bounded kernels
 * - The real-time Quake path favors sparse reconstruction over full-state readout
 */

#ifndef QGE_H
#define QGE_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "qge_quantum_runtime.h"
#include "qge_trace.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================
 * Hardware Tier System
 * ============================================================================ */

typedef enum {
    QGE_TIER_ULTRA,    // M2 Ultra/Max, RTX 4090 - 28 qubits, 60 FPS
    QGE_TIER_HIGH,     // M2 Pro, M1 Max, RTX 3080 - 26 qubits, 45 FPS
    QGE_TIER_MEDIUM,   // M1, RTX 3060, integrated - 24 qubits, 30 FPS
    QGE_TIER_LOW,      // Older laptops, no GPU - 22 qubits, 20 FPS
    QGE_TIER_POTATO    // Minimum spec - 20 qubits, 15 FPS
} qge_hardware_tier_t;

typedef enum {
    QGE_BACKEND_METAL,
    QGE_BACKEND_VULKAN,
    QGE_BACKEND_OPENCL,
    QGE_BACKEND_AVX512,
    QGE_BACKEND_AVX2,
    QGE_BACKEND_NEON,
    QGE_BACKEND_FALLBACK
} qge_backend_t;

#define QGE_BACKEND_FLAG_ACCELERATED_CAPABLE      (1u << 0)
#define QGE_BACKEND_FLAG_ACTIVE_ACCELERATION      (1u << 1)
#define QGE_BACKEND_FLAG_GPU_CONTEXT_REQUIRED     (1u << 2)
#define QGE_BACKEND_FLAG_INTENTIONAL_CPU_PATH     (1u << 3)
#define QGE_BACKEND_FLAG_NATIVE_AVAILABLE         (1u << 4)
#define QGE_BACKEND_FLAG_RENDER_BRIDGE_PENDING    (1u << 5)

/* ============================================================================
 * Rendering Modes
 * ============================================================================ */

typedef enum {
    QGE_RENDER_DWT,        // Sparse wavelet quantum (recommended)
    QGE_RENDER_SCANLINE,   // 640x480 parallel quantum scanlines
    QGE_RENDER_FREQUENCY,  // DCT/frequency space
    QGE_RENDER_DIRECT,     // Direct probability rendering
    QGE_RENDER_DIFFUSION   // MPS-based diffusion upscaler
} qge_render_mode_t;

typedef enum {
    QGE_RES_NATIVE,      // 64x64 direct quantum
    QGE_RES_320x200,     // Classic Doom resolution
    QGE_RES_640x480,     // VGA (recommended)
    QGE_RES_800x600,     // SVGA
    QGE_RES_1280x720     // 720p (Ultra tier only)
} qge_resolution_t;

/* ============================================================================
 * DWT Configuration
 * ============================================================================ */

typedef enum {
    DWT_MODE_HAAR,        // Fastest, sharp edges
    DWT_MODE_DAUBECHIES4, // Smoother, slightly slower
    DWT_MODE_BIORTHOGONAL // Best quality, slowest
} dwt_mode_t;

typedef enum {
    SUBBAND_LL,  // Low-Low (approximation)
    SUBBAND_HL,  // High-Low (horizontal edges)
    SUBBAND_LH,  // Low-High (vertical edges)
    SUBBAND_HH   // High-High (diagonal edges)
} dwt_subband_t;

typedef struct {
    dwt_mode_t mode;
    int num_levels;           // 4-6 typical
    int base_resolution;      // 64, 128, 256, 512, or 1024
    bool gpu_reconstruct;     // Use Metal for inverse DWT
    float sparsity_threshold; // Skip coefficients below this
    bool quantum_measurement_extract; // Extract coefficients via quantum measurement (slower, captures interference)
} dwt_config_t;

/* ============================================================================
 * Core Types
 * ============================================================================ */

#ifndef QGE_VEC3_T_DEFINED
#define QGE_VEC3_T_DEFINED
typedef struct {
    float x, y, z;
} qge_vec3_t;
#endif

typedef struct {
    int x1, y1, x2, y2;
} screen_rect_t;

#include "qge_world.h"

/* Forward declarations */
typedef struct qge_context_s qge_context_t;
typedef struct qge_framebuffer_s qge_framebuffer_t;
typedef struct dwt_framebuffer_s dwt_framebuffer_t;

/* ============================================================================
 * Engine Initialization
 * ============================================================================ */

/**
 * Initialize the Quantum Game Engine.
 * Auto-detects hardware tier and selects appropriate backend.
 *
 * @return Initialized context, or NULL on failure
 */
qge_context_t* qge_init(void);

/**
 * Initialize with specific configuration.
 */
qge_context_t* qge_init_with_config(qge_hardware_tier_t tier,
                                     qge_render_mode_t mode,
                                     qge_resolution_t resolution);

/**
 * Shutdown and free all resources.
 */
void qge_shutdown(qge_context_t* ctx);

/**
 * Auto-detect hardware capabilities.
 */
qge_hardware_tier_t qge_detect_hardware(void);

/**
 * Get a stable display name for a runtime backend.
 */
const char* qge_backend_name(qge_backend_t backend);

/**
 * Return true when a backend uses platform acceleration instead of the
 * portable fallback path. This describes backend capability, not whether a
 * specific context has initialized an accelerator for the active render path.
 */
bool qge_backend_is_accelerated(qge_backend_t backend);

/**
 * Return true when this context has active acceleration attached to the live
 * runtime path. GPU-style backends require an initialized GPU context; CPU SIMD
 * backends are active when selected.
 */
bool qge_context_has_active_acceleration(qge_context_t* ctx);

/**
 * Return true when the selected native backend was probed and is available on
 * this machine, even if the current render path has not attached it yet.
 */
bool qge_context_backend_native_available(qge_context_t* ctx);

/**
 * Human-readable active acceleration state for logs and evidence.
 */
const char* qge_context_acceleration_status(qge_context_t* ctx);

/**
 * Machine-readable backend gate flags for runtime evidence.
 */
uint32_t qge_context_backend_flags(qge_context_t* ctx);

/**
 * Stable backend gate reason string for logs and ICC/runtime evidence.
 */
const char* qge_context_backend_reason(qge_context_t* ctx);

/**
 * Stable native backend probe reason string for logs and ICC/runtime evidence.
 */
const char* qge_context_backend_probe_reason(qge_context_t* ctx);

/**
 * Stable runtime path string for backend-gate logs and trace probes.
 */
const char* qge_context_backend_runtime_path(qge_context_t* ctx);

/**
 * Get recommended resolution for detected hardware.
 */
qge_resolution_t qge_recommended_resolution(qge_hardware_tier_t tier);

/**
 * Get DWT configuration for hardware tier.
 */
dwt_config_t qge_dwt_config_for_tier(qge_hardware_tier_t tier);

/* ============================================================================
 * Quantum RNG (qge_rng.h)
 * ============================================================================ */

/**
 * Initialize the Quantum RNG early (before any rand() calls).
 * Must be called at very start of main() before any other initialization.
 * Returns 0 on success, -1 on failure.
 */
int qge_rng_init(void);

/**
 * Shutdown the Quantum RNG.
 */
void qge_rng_shutdown(void);

/**
 * Get a single quantum random 16-bit value.
 * Uses Hadamard on 16 qubits + measurement.
 */
uint16_t qge_random(void);

/**
 * Get quantum random values in batch (more efficient).
 */
void qge_random_batch(uint16_t* out, int count);

/**
 * Get quantum random float in [0.0, 1.0].
 */
float qge_random_float(void);

/**
 * Quake-compatible M_Random replacement.
 */
int qge_m_random(void);

/**
 * Route qge_random() through a shared quantum runtime. When unset, qge_random()
 * keeps using the Moonlab QRNG directly.
 */
void qge_rng_set_runtime(qge_quantum_runtime_t* runtime);

/* ============================================================================
 * Quantum AI (qge_ai.h)
 * ============================================================================ */

#include "qge_ai.h"

/* ============================================================================
 * Quantum Rendering (qge_render.h)
 * ============================================================================ */

/**
 * Create a quantum framebuffer.
 */
qge_framebuffer_t* qge_framebuffer_create(qge_context_t* ctx);

/**
 * Reset framebuffer for new frame.
 */
void qge_framebuffer_reset(qge_framebuffer_t* fb);

/**
 * Free framebuffer resources.
 */
void qge_framebuffer_free(qge_framebuffer_t* fb);

/**
 * Create DWT framebuffer for wavelet rendering.
 */
dwt_framebuffer_t* qge_dwt_framebuffer_create(qge_context_t* ctx,
                                               const dwt_config_t* config);

/**
 * Encode a wall surface as wavelet coefficients.
 *
 * @param fb DWT framebuffer
 * @param bounds Screen-space bounds of the wall
 * @param brightness Wall brightness (0.0-1.0)
 * @param depth Z-depth for occlusion
 */
void qge_encode_wall_dwt(dwt_framebuffer_t* fb,
                          const screen_rect_t* bounds,
                          float brightness,
                          float depth);

/**
 * Encode a sprite at screen position.
 */
void qge_encode_sprite_dwt(dwt_framebuffer_t* fb,
                            int screen_x, int screen_y,
                            int sprite_width, int sprite_height,
                            float brightness,
                            float depth);

/**
 * Add a single wavelet coefficient.
 */
void qge_add_wavelet_coeff(dwt_framebuffer_t* fb,
                            int level,
                            dwt_subband_t subband,
                            int cx, int cy,
                            float value);

/**
 * Extract wavelet coefficients from quantum state (GPU accelerated).
 */
void qge_extract_coefficients(dwt_framebuffer_t* fb, float* coeffs);

/**
 * Encode a spatial luminance buffer into sparse DWT coefficients.
 *
 * This is the matched forward transform for qge_inverse_dwt(). Geometry should
 * be rasterized into a low-resolution spatial buffer first, then transformed
 * through this entry point before reconstruction.
 */
void qge_dwt_encode_spatial(dwt_framebuffer_t* fb,
                            const float* pixels,
                            int width,
                            int height);

/**
 * Encode a spatial luminance buffer in place.
 *
 * This destructive variant may transform `pixels` as scratch storage. Use it
 * only when the caller no longer needs the source buffer after encoding.
 */
void qge_dwt_encode_spatial_inplace(dwt_framebuffer_t* fb,
                                    float* pixels,
                                    int width,
                                    int height);

/**
 * Perform inverse DWT to get spatial image.
 */
void qge_inverse_dwt(const float* coeffs, float* pixels,
                     int width, int height, int levels,
                     dwt_mode_t mode);

/**
 * Project quantum state to display buffer.
 * This is the main rendering call.
 *
 * @param fb Quantum framebuffer
 * @param display Output pixel buffer (RGB)
 * @param width Display width
 * @param height Display height
 */
void qge_project_to_display(qge_framebuffer_t* fb,
                             uint8_t* display,
                             int width, int height);

/**
 * Reset DWT framebuffer for new frame.
 */
void qge_dwt_framebuffer_reset(dwt_framebuffer_t* fb);

/**
 * Free DWT framebuffer.
 */
void qge_dwt_framebuffer_free(dwt_framebuffer_t* fb);

/**
 * Render DWT framebuffer to output pixels.
 */
void qge_dwt_render(dwt_framebuffer_t* fb, float* output);

/**
 * Get count of active (non-zero) coefficients.
 */
int qge_dwt_get_active_count(dwt_framebuffer_t* fb);

/**
 * Get sparsity ratio (0.0 = all coefficients, 1.0 = none).
 */
float qge_dwt_get_sparsity(dwt_framebuffer_t* fb);

/* ============================================================================
 * Quantum Visibility (qge_vis.h)
 * ============================================================================ */

typedef enum {
    QGE_VIS_GATE_REASON_NONE = 0,
    QGE_VIS_GATE_REASON_AUTHORITY_NOT_REQUESTED,
    QGE_VIS_GATE_REASON_AUTHORITY_READY,
    QGE_VIS_GATE_REASON_WARMUP_PENDING,
    QGE_VIS_GATE_REASON_FALSE_NEGATIVE,
    QGE_VIS_GATE_REASON_PARITY_MISMATCH,
    QGE_VIS_GATE_REASON_SHADOW_OVERFLOW,
    QGE_VIS_GATE_REASON_SURFACE_COUNT_CHANGED,
    QGE_VIS_GATE_REASON_SHADOW_UNAVAILABLE
} qge_vis_gate_reason_t;

typedef struct {
    int total_surfaces;
    int classic_visible_count;
    int qge_visible_count;
    int matched_visible_count;
    int matched_hidden_count;
    int false_positive_count;
    int false_negative_count;
    int overflow_count;
    int first_false_positive;
    int first_false_negative;
    uint64_t classic_fingerprint;
    uint64_t qge_fingerprint;
    uint64_t mismatch_fingerprint;
    float threshold;
    float qge_probability_sum;
    float qge_probability_max;
    int mismatch_count;
    int frames_observed;
    int consecutive_clean_frames;
    int clean_frames_required;
    int cumulative_mismatch_count;
    int cumulative_false_negative_count;
    bool authority_ready;
    bool fallback_required;
    bool controlled_authority_smoke;
    qge_vis_gate_reason_t authority_reason;
    qge_vis_gate_reason_t fallback_reason;
} qge_vis_shadow_stats_t;

typedef enum {
    QGE_VIS_WRITEBACK_SOURCE_CLASSIC = 0,
    QGE_VIS_WRITEBACK_SOURCE_QGE
} qge_vis_writeback_source_t;

typedef struct {
    bool authority_requested;
    bool shadow_observed;
    bool authority_ready;
    bool writeback_allowed;
    bool fallback_selected;
    bool false_negative_forced_classic;
    qge_vis_writeback_source_t source;
    qge_vis_gate_reason_t authority_reason;
    qge_vis_gate_reason_t fallback_reason;
    int last_mismatch_count;
    int last_false_negative_count;
    int consecutive_clean_frames;
    int clean_frames_required;
    unsigned int flags;
} qge_vis_writeback_decision_t;

const char* qge_vis_gate_reason_name(qge_vis_gate_reason_t reason);

/**
 * Get the sandboxed visibility authority writeback decision. Classic
 * visibility remains authoritative unless authority is explicitly requested and
 * the shadow-parity gate is clean and ready.
 */
bool qge_vis_get_writeback_decision(bool authority_requested,
                                    qge_vis_writeback_decision_t* decision);

/**
 * Return the audited QGE-visible mask from the last completed shadow parity
 * frame. This is intentionally available only when the supplied writeback
 * decision allows QGE authority for the frame.
 */
bool qge_vis_get_audited_visible_mask(
    const qge_vis_writeback_decision_t* decision,
    const unsigned char** visible_mask,
    int* surface_count);

/**
 * Enable a controlled visibility-authority smoke mode. This copies the
 * classic accepted surface mask into the audited QGE writeback mask so the
 * renderer authority path can be tested independently of raw Grover/PVS parity.
 */
void qge_vis_shadow_set_controlled_authority_smoke(bool enabled);

/**
 * Set up viewpoint for visibility queries.
 */
void qge_vis_setup_viewpoint(qge_vec3_t eye, qge_vec3_t forward);

/**
 * Query visibility of a surface using Grover-accelerated BSP.
 *
 * @param surface_id BSP surface identifier
 * @return Visibility probability (0.0 = hidden, 1.0 = fully visible)
 */
float qge_vis_query_surface(int surface_id);

/**
 * Get set of visible surfaces via amplitude amplification.
 *
 * @param surfaces Output array of surface IDs
 * @param count Output count of visible surfaces
 * @param max_count Maximum surfaces to return
 */
void qge_vis_get_visible_set(int* surfaces, int* count, int max_count);

/**
 * Register a surface for visibility testing.
 */
void qge_vis_register_surface(int surface_id,
                               float min_x, float min_y, float min_z,
                               float max_x, float max_y, float max_z);

/**
 * Clear all registered surfaces.
 */
void qge_vis_clear_surfaces(void);

/**
 * Get visibility statistics.
 */
void qge_vis_get_stats(int* total_surfaces, int* visible_count,
                        float* avg_probability);

/**
 * Begin shadow comparison against a classic visible surface set.
 * A threshold of 0.0 selects an adaptive per-frame probability threshold.
 */
void qge_vis_shadow_begin(int total_surfaces, float visibility_threshold);

/**
 * Mark one surface as visible according to the classic renderer.
 */
void qge_vis_shadow_mark_classic_visible(int surface_id);

/**
 * Finish shadow comparison and fill parity telemetry.
 */
bool qge_vis_shadow_finish(qge_vis_shadow_stats_t* stats);

/**
 * Shutdown visibility module.
 */
void qge_vis_shutdown(void);

/* ============================================================================
 * Quantum Audio (qge_audio.h)
 * ============================================================================ */

typedef struct qge_oscillator_s qge_oscillator_t;

/**
 * Initialize quantum audio system.
 */
void qge_audio_init(void);

/**
 * Shutdown quantum audio.
 */
void qge_audio_shutdown(void);

/**
 * Create a quantum harmonic oscillator for sound synthesis.
 *
 * @param num_levels Number of energy levels (harmonics)
 * @param base_frequency Ground state frequency in Hz
 */
qge_oscillator_t* qge_oscillator_create(int num_levels, float base_frequency);

/**
 * Excite oscillator to target energy level.
 */
void qge_oscillator_excite(qge_oscillator_t* osc, int target_level);

/**
 * Sample oscillator (collapses to specific frequency).
 */
float qge_oscillator_sample(qge_oscillator_t* osc);

/**
 * Synthesize audio samples from oscillator state.
 */
void qge_audio_synthesize(float* buffer, int samples, qge_oscillator_t* osc);

/**
 * Apply quantum interference reverb effect.
 */
void qge_audio_reverb(float* samples, int count, float decay);

/**
 * Apply quantum phase effect.
 */
void qge_audio_phase(float* samples, int count, float depth);

/**
 * Mix two audio buffers using quantum superposition.
 */
void qge_audio_quantum_mix(float* buf_a, float* buf_b, float* output,
                            int count, float mix_ratio);

/**
 * Get probability distribution over energy levels.
 */
void qge_oscillator_get_probabilities(qge_oscillator_t* osc,
                                       float* probabilities, int max_levels);

/**
 * Set oscillator amplitude.
 */
void qge_oscillator_set_amplitude(qge_oscillator_t* osc, float amplitude);

/**
 * Apply quantum decay (decoherence) to oscillator.
 */
void qge_oscillator_decay(qge_oscillator_t* osc, float decay_rate);

/**
 * Free oscillator resources.
 */
void qge_oscillator_free(qge_oscillator_t* osc);

/* ============================================================================
 * Quantum Audio Transducer (DCT-based audio processing through quantum gates)
 * ============================================================================ */

typedef struct qge_transducer_s qge_transducer_t;

/**
 * Create a quantum audio transducer.
 * Processes audio through quantum circuits in frequency domain.
 *
 * @param num_qubits Number of qubits (determines entanglement depth)
 * @param block_size DCT block size (should be power of 2)
 * @return Transducer handle, or NULL on failure
 */
qge_transducer_t* qge_transducer_create(int num_qubits, int block_size);

/**
 * Reset transducer state (call between audio sessions).
 */
void qge_transducer_reset(qge_transducer_t* trans);

/**
 * Process frequency bins through quantum circuit.
 * Applies encoding, entanglement, and measurement.
 *
 * @param trans Transducer handle
 * @param freq_bins Frequency domain audio (modified in place)
 * @param num_bins Number of frequency bins
 * @param spread Quantum spread parameter (0.0-1.0)
 * @param time Current time for phase evolution
 */
void qge_transducer_process(qge_transducer_t* trans,
                             float* freq_bins, int num_bins,
                             float spread, double time);

/**
 * Get internal quantum state for advanced manipulation.
 * Returns opaque pointer to Moonlab quantum_state_t.
 */
void* qge_transducer_get_state(qge_transducer_t* trans);

/**
 * Apply custom gate to transducer's quantum state.
 *
 * @param trans Transducer handle
 * @param gate_type Gate to apply: 'H'=Hadamard, 'X'=NOT, 'Y', 'Z', 'S', 'T'
 * @param qubit Target qubit index
 */
void qge_transducer_apply_gate(qge_transducer_t* trans, char gate_type, int qubit);

/**
 * Apply rotation gate (Rx, Ry, Rz).
 *
 * @param trans Transducer handle
 * @param axis Rotation axis: 'X', 'Y', or 'Z'
 * @param qubit Target qubit
 * @param angle Rotation angle in radians
 */
void qge_transducer_apply_rotation(qge_transducer_t* trans, char axis, int qubit, double angle);

/**
 * Apply controlled gate (CNOT, CZ).
 *
 * @param trans Transducer handle
 * @param gate_type 'N' for CNOT, 'Z' for CZ
 * @param control Control qubit
 * @param target Target qubit
 */
void qge_transducer_apply_controlled(qge_transducer_t* trans, char gate_type,
                                      int control, int target);

/**
 * Get probability amplitude for a specific basis state.
 */
double qge_transducer_get_probability(qge_transducer_t* trans, int basis_state);

/**
 * Extract interference pattern weighted by basis state similarity.
 */
float qge_transducer_measure_interference(qge_transducer_t* trans, int target_state);

/**
 * Free transducer resources.
 */
void qge_transducer_free(qge_transducer_t* trans);

/* ============================================================================
 * Quantum Physics (qge_physics.h)
 * ============================================================================ */

#define QGE_PROJECTILE_AUTHORITY_DEFAULT_WARMUP_FRAMES 4
#define QGE_PROJECTILE_AUTHORITY_DEFAULT_MIN_SHADOW_SAMPLES 3
#define QGE_PROJECTILE_AUTHORITY_DEFAULT_AVG_SHADOW_ERROR_MAX 1.0f
#define QGE_PROJECTILE_AUTHORITY_DEFAULT_MAX_SHADOW_ERROR_MAX 4.0f
#define QGE_PROJECTILE_BRANCH_MAX 3

typedef enum {
    QGE_PROJECTILE_AUTHORITY_OFF_NONE = 0,
    QGE_PROJECTILE_AUTHORITY_OFF_DISABLED,
    QGE_PROJECTILE_AUTHORITY_OFF_NO_PROJECTILES,
    QGE_PROJECTILE_AUTHORITY_OFF_WARMUP,
    QGE_PROJECTILE_AUTHORITY_OFF_SHADOW_MAX,
    QGE_PROJECTILE_AUTHORITY_OFF_SHADOW_AVG,
    QGE_PROJECTILE_AUTHORITY_OFF_TRACE_INVALID
} qge_projectile_authority_off_reason_t;

typedef struct {
    int warmup_frames_required;
    int min_shadow_samples;
    float avg_shadow_error_max;
    float max_shadow_error_max;
} qge_projectile_authority_gate_t;

typedef struct {
    bool requested;
    int active_projectiles;
    int frame_projectiles;
    int warmup_frames;
    int shadow_samples;
    float avg_shadow_error;
    float max_shadow_error;
} qge_projectile_authority_telemetry_t;

typedef struct {
    bool ready;
    qge_projectile_authority_off_reason_t off_reason;
    int warmup_frames_remaining;
    int shadow_samples_remaining;
    float avg_shadow_error_margin;
    float max_shadow_error_margin;
} qge_projectile_authority_state_t;

typedef enum {
    QGE_PROJECTILE_WRITEBACK_CLASSIC = 0,
    QGE_PROJECTILE_WRITEBACK_QGE
} qge_projectile_writeback_source_t;

typedef enum {
    QGE_PROJECTILE_BRANCH_CLASSIC_SHADOW = 0,
    QGE_PROJECTILE_BRANCH_QGE_PREDICTION,
    QGE_PROJECTILE_BRANCH_IMPACT_OBSERVATION
} qge_projectile_branch_id_t;

typedef enum {
    QGE_PROJECTILE_BRANCH_FLAG_CLASSIC = 0x0001u,
    QGE_PROJECTILE_BRANCH_FLAG_QGE = 0x0002u,
    QGE_PROJECTILE_BRANCH_FLAG_IMPACT = 0x0004u,
    QGE_PROJECTILE_BRANCH_FLAG_SELECTED = 0x0008u,
    QGE_PROJECTILE_BRANCH_FLAG_OBSERVED = 0x0010u,
    QGE_PROJECTILE_BRANCH_FLAG_DECOHERED = 0x0020u
} qge_projectile_branch_flag_t;

typedef struct {
    qge_projectile_branch_id_t id;
    uint32_t flags;
    qge_vec3_t origin;
    qge_vec3_t velocity;
    float weight;
    float phase;
    float decoherence;
    qge_observation_boundary_t boundary;
    int impact_entity_id;
    float impact_fraction;
} qge_projectile_branch_t;

typedef struct {
    int entity_id;
    qge_projectile_authority_telemetry_t telemetry;
    qge_vec3_t classic_origin;
    qge_vec3_t classic_velocity;
    qge_vec3_t qge_origin;
    qge_vec3_t qge_velocity;
    qge_vec3_t impact_origin;
    qge_vec3_t impact_normal;
    int impact_entity_id;
    float impact_fraction;
    bool has_impact;
    qge_observation_boundary_t boundary;
} qge_projectile_branch_request_t;

typedef struct {
    int entity_id;
    int branch_count;
    int selected_branch_index;
    qge_projectile_branch_id_t selected_branch_id;
    qge_projectile_branch_t branches[QGE_PROJECTILE_BRANCH_MAX];
    qge_vec3_t selected_origin;
    qge_vec3_t selected_velocity;
    float total_weight;
    float max_weight;
    float selected_probability;
    float coherence;
    float decoherence;
    bool observed;
    bool impact_measured;
    bool selected_has_impact;
    int selected_impact_entity_id;
    float selected_impact_fraction;
    qge_vec3_t selected_impact_origin;
    qge_vec3_t selected_impact_normal;
    uint64_t state_hash;
    qge_observation_boundary_t boundary;
} qge_projectile_branch_state_t;

typedef struct {
    int entity_id;
    qge_projectile_authority_telemetry_t telemetry;
    qge_vec3_t classic_origin;
    qge_vec3_t classic_velocity;
    qge_vec3_t qge_origin;
    qge_vec3_t qge_velocity;
} qge_projectile_writeback_request_t;

typedef struct {
    int entity_id;
    bool authority_requested;
    bool authority_ready;
    bool writeback_allowed;
    bool fallback_selected;
    bool rollback_required;
    qge_projectile_writeback_source_t source;
    qge_projectile_authority_off_reason_t off_reason;
    qge_projectile_authority_off_reason_t fallback_reason;
    qge_projectile_authority_off_reason_t rollback_reason;
    qge_projectile_authority_state_t gate_state;
    qge_vec3_t origin_delta;
    qge_vec3_t velocity_delta;
    float origin_delta_length;
    float velocity_delta_length;
} qge_projectile_writeback_decision_t;

typedef enum {
    QGE_PROJECTILE_COLLISION_TRACE_CLASSIC = 0,
    QGE_PROJECTILE_COLLISION_TRACE_QGE
} qge_projectile_collision_trace_source_t;

typedef struct {
    int entity_id;
    qge_projectile_authority_telemetry_t telemetry;
    qge_vec3_t classic_origin;
    qge_vec3_t classic_velocity;
    bool classic_has_impact;
    int classic_impact_entity_id;
    float classic_impact_fraction;
    qge_vec3_t classic_impact_origin;
    qge_vec3_t classic_impact_normal;
    qge_vec3_t qge_origin;
    qge_vec3_t qge_velocity;
    bool qge_trace_valid;
    bool qge_has_impact;
    int qge_impact_entity_id;
    float qge_impact_fraction;
    qge_vec3_t qge_impact_origin;
    qge_vec3_t qge_impact_normal;
} qge_projectile_collision_oracle_request_t;

typedef struct {
    int entity_id;
    bool authority_requested;
    bool authority_ready;
    bool authority_applied;
    bool fallback_selected;
    bool rollback_required;
    bool selected_has_impact;
    bool selected_no_impact;
    bool selected_alternate_impact;
    qge_projectile_collision_trace_source_t source;
    qge_projectile_authority_off_reason_t off_reason;
    qge_projectile_authority_off_reason_t fallback_reason;
    qge_projectile_authority_off_reason_t rollback_reason;
    qge_projectile_authority_state_t gate_state;
    qge_vec3_t selected_origin;
    qge_vec3_t selected_velocity;
    int selected_impact_entity_id;
    float selected_impact_fraction;
    qge_vec3_t selected_impact_origin;
    qge_vec3_t selected_impact_normal;
    float selected_probability;
    uint64_t state_hash;
} qge_projectile_collision_oracle_decision_t;

/**
 * Default conservative projectile authority gate. This only reports readiness;
 * callers must still decide whether to apply any authority.
 */
qge_projectile_authority_gate_t qge_projectile_authority_default_gate(void);

/**
 * Evaluate projectile authority readiness from mirrored classic shadow
 * telemetry. This does not mutate game/entity state.
 */
qge_projectile_authority_state_t qge_projectile_authority_evaluate(
    const qge_projectile_authority_gate_t* gate,
    const qge_projectile_authority_telemetry_t* telemetry);

/**
 * Evaluate a sandboxed projectile writeback choice. This is a pure helper:
 * it reports whether classic or QGE state would be selected and never mutates
 * Quake entities. QGE writeback is selected only when authority is explicitly
 * requested and the projectile authority gate is ready.
 */
qge_projectile_writeback_decision_t qge_projectile_writeback_evaluate(
    const qge_projectile_authority_gate_t* gate,
    const qge_projectile_writeback_request_t* request);

/**
 * Evaluate a bounded projectile branch state without mutating Quake state. The
 * state exposes classic shadow, QGE prediction, and optional impact-observation
 * branches with normalized weights and deterministic selection metadata.
 */
qge_projectile_branch_state_t qge_projectile_branch_state_evaluate(
    const qge_projectile_authority_gate_t* gate,
    const qge_projectile_branch_request_t* request);

/**
 * Select a mutually consistent projectile collision trace. The request carries
 * the classic trace candidate and a QGE-retraced candidate; the decision only
 * grants authority to the QGE candidate when projectile authority is requested
 * and ready.
 */
qge_projectile_collision_oracle_decision_t
qge_projectile_collision_oracle_evaluate(
    const qge_projectile_authority_gate_t* gate,
    const qge_projectile_collision_oracle_request_t* request);

/**
 * Stable string for a projectile authority-off reason.
 */
const char* qge_projectile_authority_off_reason_name(
    qge_projectile_authority_off_reason_t reason);

typedef struct qge_particle_system_s qge_particle_system_t;

/**
 * Create quantum particle system.
 */
qge_particle_system_t* qge_particle_system_create(int max_particles);

/**
 * Spawn a particle at position with velocity.
 */
void qge_particle_spawn(qge_particle_system_t* sys,
                        qge_vec3_t position, qge_vec3_t velocity,
                        float lifetime);

/**
 * Evolve particle system using quantum time evolution.
 */
void qge_particle_evolve(qge_particle_system_t* sys, float dt);

/**
 * Get particle positions for rendering.
 */
int qge_particle_get_positions(qge_particle_system_t* sys,
                                qge_vec3_t* positions, int max_count);

/**
 * Set gravity strength for particle system.
 */
void qge_particle_system_set_gravity(qge_particle_system_t* sys, float gravity);

/**
 * Set drag coefficient for particle system.
 */
void qge_particle_system_set_drag(qge_particle_system_t* sys, float drag);

/**
 * Get number of active particles.
 */
int qge_particle_system_active_count(qge_particle_system_t* sys);

/**
 * Apply impulse to all particles (e.g., explosion).
 */
void qge_particle_system_impulse(qge_particle_system_t* sys,
                                  qge_vec3_t center, float strength);

/**
 * Clear all particles.
 */
void qge_particle_system_clear(qge_particle_system_t* sys);

/**
 * Free particle system.
 */
void qge_particle_system_free(qge_particle_system_t* sys);

/* ============================================================================
 * Profiling
 * ============================================================================ */

typedef struct {
    double gate_time_ms;
    double extract_time_ms;
    double render_time_ms;
    double audio_time_ms;
    double total_frame_ms;
    int frames_in_budget;
    int frames_over_budget;
    int current_qubits;
    size_t memory_used_bytes;
} qge_profile_t;

/**
 * Get current profiling data.
 */
void qge_get_profile(qge_context_t* ctx, qge_profile_t* profile);

/**
 * Enable/disable adaptive quality based on frame budget.
 */
void qge_set_adaptive_quality(qge_context_t* ctx, bool enabled);

/**
 * Get the shared quantum runtime attached to this QGE context.
 */
qge_quantum_runtime_t* qge_get_quantum_runtime(qge_context_t* ctx);

/**
 * Get the selected runtime backend attached to this QGE context.
 */
qge_backend_t qge_get_backend(qge_context_t* ctx);

/**
 * Get the process-global QGE context used by convenience systems.
 */
qge_context_t* qge_get_context(void);

/**
 * Get the stable world/resource registry attached to this QGE context.
 */
qge_world_t* qge_get_world(qge_context_t* ctx);

/**
 * Get the mutable frame snapshot builder for the current frame.
 */
qge_frame_snapshot_t* qge_get_frame_snapshot(qge_context_t* ctx);

/**
 * Get the current frame snapshot as read-only data.
 */
const qge_frame_snapshot_t* qge_get_frame_snapshot_const(qge_context_t* ctx);

#ifdef __cplusplus
}
#endif

#endif /* QGE_H */
