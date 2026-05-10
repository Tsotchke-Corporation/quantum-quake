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

typedef enum {
    AI_IDLE,
    AI_PATROL,
    AI_CHASE,
    AI_ATTACK,
    AI_FLEE,
    AI_PAIN,
    AI_DEAD
} ai_action_t;

/**
 * Make a quantum AI decision for an enemy.
 *
 * @param enemy_id Unique enemy identifier
 * @param aggression Enemy aggression factor (0.0-1.0)
 * @param player_distance Distance to player
 * @param player_visible Whether player is in line of sight
 * @return Chosen action via measurement collapse
 */
ai_action_t qge_ai_decide(int enemy_id,
                          float aggression,
                          float player_distance,
                          bool player_visible);

/**
 * Entangle two enemies for coordinated behavior.
 * When one enemy makes a decision, it influences the other.
 */
void qge_ai_entangle(int enemy_a, int enemy_b);

/**
 * Initialize quantum state for a new enemy.
 */
void qge_ai_init_enemy(int enemy_id, int enemy_type);

/**
 * Free quantum state for a destroyed enemy.
 */
void qge_ai_destroy_enemy(int enemy_id);

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
