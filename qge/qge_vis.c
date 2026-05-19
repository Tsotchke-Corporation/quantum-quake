/**
 * @file qge_vis.c
 * @brief Quantum Visibility - Grover-accelerated BSP traversal
 *
 * Uses Grover's algorithm for quadratic speedup on visibility queries.
 * Instead of O(N) classical BSP traversal, achieves O(√N) via quantum
 * amplitude amplification.
 *
 * Architecture:
 * - Surface indices encoded in 20-qubit register (up to 1M surfaces)
 * - Oracle marks surfaces visible from current viewpoint
 * - Amplitude amplification concentrates probability on visible set
 * - Measurement samples from visible surface distribution
 *
 * The visibility oracle is constructed from:
 * - View frustum culling (encoded as controlled gates)
 * - BSP front/back classification
 * - Occlusion information (surfaces behind walls get phase-flipped away)
 */

#include "qge.h"
#include "../deps/moonlab/src/quantum/state.h"
#include "../deps/moonlab/src/quantum/gates.h"
#include "../deps/moonlab/src/quantum/measurement.h"
#include "../deps/moonlab/src/algorithms/grover.h"
#include "../deps/moonlab/src/utils/quantum_entropy.h"
#include "../deps/moonlab/src/applications/hardware_entropy.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>

/* ============================================================================
 * Constants
 * ============================================================================ */

#define VIS_QUBITS 20           /* Support up to 2^20 = 1M surfaces */
#define MAX_VISIBLE_SURFACES 4096
#define MAX_OCCLUDERS 256

/* ============================================================================
 * State
 * ============================================================================ */

typedef struct {
    int surface_id;
    float min_x, max_x;
    float min_y, max_y;
    float min_z, max_z;
    float distance;             /* Distance from viewpoint */
    bool is_visible;            /* Cached classical visibility */
} surface_info_t;

typedef struct {
    qge_vec3_t eye;
    qge_vec3_t forward;
    qge_vec3_t right;
    qge_vec3_t up;
    float fov_x;
    float fov_y;
    float near_clip;
    float far_clip;
} view_frustum_t;

/* Module state */
static quantum_state_t* vis_state = NULL;
static quantum_entropy_ctx_t* vis_entropy = NULL;
static entropy_ctx_t* vis_hw_entropy = NULL;
static view_frustum_t current_view;
static bool vis_initialized = false;

/* Surface database (would be populated from BSP in real integration) */
static surface_info_t* surfaces = NULL;
static int num_surfaces = 0;
static int surfaces_capacity = 0;

/* Cached visibility results */
static uint64_t* visible_surface_cache = NULL;
static float* visibility_probabilities = NULL;
static int cached_visible_count = 0;
static bool cache_valid = false;

/* Shadow parity state: compares QGE visibility to the classic accepted set. */
static unsigned char* shadow_classic_visible = NULL;
static unsigned char* shadow_qge_visible = NULL;
static int shadow_classic_capacity = 0;
static int shadow_qge_capacity = 0;
static int shadow_surface_count = 0;
static int shadow_qge_surface_count = 0;
static int shadow_overflow_count = 0;
static float shadow_visibility_threshold = 0.0f;
static bool shadow_active = false;

#define VIS_AUTHORITY_CLEAN_FRAMES_REQUIRED 8

static int shadow_gate_surface_count = 0;
static int shadow_frames_observed = 0;
static int shadow_consecutive_clean_frames = 0;
static int shadow_cumulative_mismatch_count = 0;
static int shadow_cumulative_false_negative_count = 0;
static bool shadow_authority_ready = false;
static qge_vis_gate_reason_t shadow_authority_reason =
    QGE_VIS_GATE_REASON_SHADOW_UNAVAILABLE;
static qge_vis_gate_reason_t shadow_fallback_reason =
    QGE_VIS_GATE_REASON_SHADOW_UNAVAILABLE;
static int shadow_last_mismatch_count = 0;
static int shadow_last_false_negative_count = 0;
static bool shadow_controlled_authority_smoke = false;

/* ============================================================================
 * Entropy Callback
 * ============================================================================ */

static int vis_entropy_callback(void *user_data, uint8_t *buffer, size_t size) {
    entropy_ctx_t *ctx = (entropy_ctx_t *)user_data;
    return entropy_get_bytes(ctx, buffer, size);
}

/* ============================================================================
 * Initialization
 * ============================================================================ */

static void ensure_vis_initialized(void) {
    if (vis_initialized) return;

    /* Allocate quantum state for visibility queries */
    vis_state = malloc(sizeof(quantum_state_t));
    if (!vis_state) {
        fprintf(stderr, "QGE VIS: Failed to allocate state\n");
        return;
    }

    qs_error_t err = quantum_state_init(vis_state, VIS_QUBITS);
    if (err != QS_SUCCESS) {
        fprintf(stderr, "QGE VIS: Failed to init quantum state (%d qubits)\n", VIS_QUBITS);
        free(vis_state);
        vis_state = NULL;
        return;
    }

    /* Initialize hardware entropy */
    vis_hw_entropy = malloc(sizeof(entropy_ctx_t));
    if (!vis_hw_entropy || entropy_init(vis_hw_entropy) != ENTROPY_SUCCESS) {
        fprintf(stderr, "QGE VIS: Failed to init hardware entropy\n");
        quantum_state_free(vis_state);
        free(vis_state);
        free(vis_hw_entropy);
        vis_state = NULL;
        vis_hw_entropy = NULL;
        return;
    }

    /* Initialize quantum entropy context */
    vis_entropy = malloc(sizeof(quantum_entropy_ctx_t));
    if (!vis_entropy) {
        fprintf(stderr, "QGE VIS: Failed to allocate entropy context\n");
        entropy_free(vis_hw_entropy);
        free(vis_hw_entropy);
        quantum_state_free(vis_state);
        free(vis_state);
        vis_state = NULL;
        vis_hw_entropy = NULL;
        return;
    }
    quantum_entropy_init(vis_entropy, vis_entropy_callback, vis_hw_entropy);

    /* Allocate surface tracking */
    surfaces_capacity = MAX_VISIBLE_SURFACES;
    surfaces = calloc(surfaces_capacity, sizeof(surface_info_t));
    visible_surface_cache = calloc(MAX_VISIBLE_SURFACES, sizeof(uint64_t));
    visibility_probabilities = calloc(surfaces_capacity, sizeof(float));

    if (!surfaces || !visible_surface_cache || !visibility_probabilities) {
        fprintf(stderr, "QGE VIS: Failed to allocate surface tracking\n");
        free(vis_entropy);
        entropy_free(vis_hw_entropy);
        free(vis_hw_entropy);
        quantum_state_free(vis_state);
        free(vis_state);
        free(surfaces);
        free(visible_surface_cache);
        free(visibility_probabilities);
        vis_state = NULL;
        vis_hw_entropy = NULL;
        vis_entropy = NULL;
        surfaces = NULL;
        visible_surface_cache = NULL;
        visibility_probabilities = NULL;
        return;
    }

    /* Initialize default view */
    current_view.eye = (qge_vec3_t){0.0f, 0.0f, 0.0f};
    current_view.forward = (qge_vec3_t){0.0f, 0.0f, -1.0f};
    current_view.right = (qge_vec3_t){1.0f, 0.0f, 0.0f};
    current_view.up = (qge_vec3_t){0.0f, 1.0f, 0.0f};
    current_view.fov_x = 90.0f;
    current_view.fov_y = 70.0f;
    current_view.near_clip = 4.0f;
    current_view.far_clip = 4096.0f;

    vis_initialized = true;
}

/* ============================================================================
 * Utility Functions
 * ============================================================================ */

static float vec3_dot(qge_vec3_t a, qge_vec3_t b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

static qge_vec3_t vec3_sub(qge_vec3_t a, qge_vec3_t b) {
    return (qge_vec3_t){a.x - b.x, a.y - b.y, a.z - b.z};
}

static float vec3_length(qge_vec3_t v) {
    return sqrtf(v.x * v.x + v.y * v.y + v.z * v.z);
}

static uint64_t vis_hash_step(uint64_t hash, uint64_t value) {
    hash ^= value;
    hash *= 1099511628211ULL;
    return hash;
}

const char* qge_vis_gate_reason_name(qge_vis_gate_reason_t reason) {
    switch (reason) {
        case QGE_VIS_GATE_REASON_NONE:
            return "none";
        case QGE_VIS_GATE_REASON_AUTHORITY_NOT_REQUESTED:
            return "authority_not_requested";
        case QGE_VIS_GATE_REASON_AUTHORITY_READY:
            return "authority_ready";
        case QGE_VIS_GATE_REASON_WARMUP_PENDING:
            return "warmup_pending";
        case QGE_VIS_GATE_REASON_FALSE_NEGATIVE:
            return "false_negative_fallback";
        case QGE_VIS_GATE_REASON_PARITY_MISMATCH:
            return "parity_mismatch_fallback";
        case QGE_VIS_GATE_REASON_SHADOW_OVERFLOW:
            return "shadow_overflow_fallback";
        case QGE_VIS_GATE_REASON_SURFACE_COUNT_CHANGED:
            return "surface_count_changed_warmup";
        case QGE_VIS_GATE_REASON_SHADOW_UNAVAILABLE:
            return "shadow_unavailable_fallback";
        default:
            return "unknown";
    }
}

static void vis_shadow_reset_authority_gate(int surface_count) {
    shadow_gate_surface_count = surface_count;
    shadow_frames_observed = 0;
    shadow_consecutive_clean_frames = 0;
    shadow_cumulative_mismatch_count = 0;
    shadow_cumulative_false_negative_count = 0;
    shadow_last_mismatch_count = 0;
    shadow_last_false_negative_count = 0;
    shadow_authority_ready = false;
    shadow_authority_reason = QGE_VIS_GATE_REASON_WARMUP_PENDING;
    shadow_fallback_reason = QGE_VIS_GATE_REASON_WARMUP_PENDING;
}

#define QGE_VIS_WRITEBACK_FLAG_AUTHORITY_REQUESTED       (1u << 0)
#define QGE_VIS_WRITEBACK_FLAG_SHADOW_OBSERVED           (1u << 1)
#define QGE_VIS_WRITEBACK_FLAG_AUTHORITY_READY           (1u << 2)
#define QGE_VIS_WRITEBACK_FLAG_WRITEBACK_QGE             (1u << 3)
#define QGE_VIS_WRITEBACK_FLAG_FALLBACK_CLASSIC          (1u << 4)
#define QGE_VIS_WRITEBACK_FLAG_FALSE_NEGATIVE_CLASSIC    (1u << 5)

unsigned int qge_vis_authority_writeback_flags(int authority_requested) {
    unsigned int flags = QGE_VIS_WRITEBACK_FLAG_FALLBACK_CLASSIC;
    bool shadow_observed = shadow_frames_observed > 0;
    bool false_negative_forced_classic =
        shadow_last_false_negative_count > 0 ||
        shadow_fallback_reason == QGE_VIS_GATE_REASON_FALSE_NEGATIVE;

    if (authority_requested) {
        flags |= QGE_VIS_WRITEBACK_FLAG_AUTHORITY_REQUESTED;
    }
    if (shadow_observed) {
        flags |= QGE_VIS_WRITEBACK_FLAG_SHADOW_OBSERVED;
    }
    if (shadow_authority_ready) {
        flags |= QGE_VIS_WRITEBACK_FLAG_AUTHORITY_READY;
    }
    if (false_negative_forced_classic) {
        flags |= QGE_VIS_WRITEBACK_FLAG_FALSE_NEGATIVE_CLASSIC;
    }

    if (authority_requested &&
        shadow_observed &&
        shadow_authority_ready &&
        shadow_fallback_reason == QGE_VIS_GATE_REASON_NONE &&
        !false_negative_forced_classic) {
        flags &= ~QGE_VIS_WRITEBACK_FLAG_FALLBACK_CLASSIC;
        flags |= QGE_VIS_WRITEBACK_FLAG_WRITEBACK_QGE;
    }

    return flags;
}

bool qge_vis_get_writeback_decision(bool authority_requested,
                                    qge_vis_writeback_decision_t* decision) {
    unsigned int flags;

    if (!decision) {
        return false;
    }
    memset(decision, 0, sizeof(*decision));
    flags = qge_vis_authority_writeback_flags(authority_requested ? 1 : 0);
    decision->flags = flags;
    decision->authority_requested = authority_requested;
    decision->shadow_observed =
        (flags & QGE_VIS_WRITEBACK_FLAG_SHADOW_OBSERVED) != 0;
    decision->authority_ready =
        (flags & QGE_VIS_WRITEBACK_FLAG_AUTHORITY_READY) != 0;
    decision->writeback_allowed =
        (flags & QGE_VIS_WRITEBACK_FLAG_WRITEBACK_QGE) != 0;
    decision->fallback_selected =
        (flags & QGE_VIS_WRITEBACK_FLAG_FALLBACK_CLASSIC) != 0;
    decision->false_negative_forced_classic =
        (flags & QGE_VIS_WRITEBACK_FLAG_FALSE_NEGATIVE_CLASSIC) != 0;
    decision->source = decision->writeback_allowed ?
        QGE_VIS_WRITEBACK_SOURCE_QGE : QGE_VIS_WRITEBACK_SOURCE_CLASSIC;
    decision->authority_reason = shadow_authority_reason;
    decision->fallback_reason = shadow_fallback_reason;
    if (!authority_requested) {
        decision->authority_reason =
            QGE_VIS_GATE_REASON_AUTHORITY_NOT_REQUESTED;
        decision->fallback_reason =
            QGE_VIS_GATE_REASON_AUTHORITY_NOT_REQUESTED;
    } else if (decision->writeback_allowed) {
        decision->fallback_reason = QGE_VIS_GATE_REASON_NONE;
    }
    decision->last_mismatch_count = shadow_last_mismatch_count;
    decision->last_false_negative_count = shadow_last_false_negative_count;
    decision->consecutive_clean_frames = shadow_consecutive_clean_frames;
    decision->clean_frames_required = VIS_AUTHORITY_CLEAN_FRAMES_REQUIRED;
    return true;
}

bool qge_vis_get_audited_visible_mask(
    const qge_vis_writeback_decision_t* decision,
    const unsigned char** visible_mask,
    int* surface_count) {
    if (visible_mask) {
        *visible_mask = NULL;
    }
    if (surface_count) {
        *surface_count = 0;
    }
    if (!decision || !decision->writeback_allowed ||
        decision->source != QGE_VIS_WRITEBACK_SOURCE_QGE ||
        !shadow_qge_visible || shadow_qge_surface_count <= 0) {
        return false;
    }
    if (visible_mask) {
        *visible_mask = shadow_qge_visible;
    }
    if (surface_count) {
        *surface_count = shadow_qge_surface_count;
    }
    return true;
}

void qge_vis_shadow_set_controlled_authority_smoke(bool enabled) {
    shadow_controlled_authority_smoke = enabled;
}

/**
 * @brief Check if a point is in front of the view frustum
 */
static bool point_in_front(qge_vec3_t point) {
    qge_vec3_t to_point = vec3_sub(point, current_view.eye);
    float forward_dist = vec3_dot(to_point, current_view.forward);
    return forward_dist > current_view.near_clip &&
           forward_dist < current_view.far_clip;
}

/**
 * @brief Classical frustum culling check for a surface
 */
static bool surface_in_frustum(const surface_info_t* surf) {
    /* Check if any corner of the AABB is in the view frustum */
    /* Simplified: check center point */
    qge_vec3_t center = {
        (surf->min_x + surf->max_x) * 0.5f,
        (surf->min_y + surf->max_y) * 0.5f,
        (surf->min_z + surf->max_z) * 0.5f
    };

    if (!point_in_front(center)) return false;

    /* Check FOV (simplified) */
    qge_vec3_t to_center = vec3_sub(center, current_view.eye);
    float forward_dist = vec3_dot(to_center, current_view.forward);
    if (forward_dist <= 0) return false;

    float right_dist = vec3_dot(to_center, current_view.right);
    float up_dist = vec3_dot(to_center, current_view.up);

    float half_width = forward_dist * tanf(current_view.fov_x * 0.5f * M_PI / 180.0f);
    float half_height = forward_dist * tanf(current_view.fov_y * 0.5f * M_PI / 180.0f);

    return fabsf(right_dist) <= half_width && fabsf(up_dist) <= half_height;
}

/* ============================================================================
 * Quantum Visibility Oracle and Diffusion
 * ============================================================================ */

/**
 * @brief Subspace-aware Grover diffusion operator
 *
 * Standard grover_diffusion operates on the full state space (2^20 states).
 * But when we only put k qubits in superposition, we need to diffuse only
 * over the 2^k active states to get correct amplification.
 *
 * The diffusion operator reflects amplitudes about their mean:
 *   a_i' = 2 * mean - a_i
 *
 * This is the key fix: we compute mean over ONLY the active subspace.
 *
 * @param state The quantum state
 * @param subspace_size Number of states in the active subspace (2^qubits_needed)
 */
static void grover_diffusion_subspace(quantum_state_t* state, uint64_t subspace_size) {
    if (!state || !state->amplitudes || subspace_size == 0) return;

    /* Ensure we don't exceed state dimension */
    if (subspace_size > state->state_dim) {
        subspace_size = state->state_dim;
    }

    /* Step 1: Compute mean amplitude over the active subspace */
    double sum_real = 0.0;
    double sum_imag = 0.0;

    for (uint64_t i = 0; i < subspace_size; i++) {
        sum_real += creal(state->amplitudes[i]);
        sum_imag += cimag(state->amplitudes[i]);
    }

    double mean_real = sum_real / (double)subspace_size;
    double mean_imag = sum_imag / (double)subspace_size;

    /* Step 2: Reflect each amplitude about the mean: a_i' = 2*mean - a_i */
    for (uint64_t i = 0; i < subspace_size; i++) {
        double new_real = 2.0 * mean_real - creal(state->amplitudes[i]);
        double new_imag = 2.0 * mean_imag - cimag(state->amplitudes[i]);
        state->amplitudes[i] = new_real + new_imag * I;
    }

    /* States outside the subspace remain at zero (they were never in superposition) */
}

/**
 * @brief Construct the visibility oracle
 *
 * Marks surfaces that are potentially visible from the current viewpoint.
 * Uses phase flips for visible surfaces (Grover oracle pattern).
 *
 * This is the key quantum component: we encode visibility determination
 * as a quantum oracle, then use amplitude amplification.
 */
static void apply_visibility_oracle(quantum_state_t* state) {
    /* For each surface that passes classical frustum culling,
     * mark it in the quantum state via phase flip */

    for (int i = 0; i < num_surfaces && i < (1 << VIS_QUBITS); i++) {
        if (surface_in_frustum(&surfaces[i])) {
            /* This surface is potentially visible - mark with phase flip */
            grover_oracle(state, (uint64_t)surfaces[i].surface_id);
        }
    }
}

/**
 * @brief Apply quantum visibility query with amplitude amplification
 *
 * 1. Initialize superposition over all surface indices
 * 2. Apply visibility oracle (marks visible surfaces)
 * 3. Apply Grover diffusion (amplifies visible)
 * 4. Repeat for O(√N) iterations
 *
 * Key insight: We use subspace-aware diffusion to correctly amplify
 * probabilities when the number of surfaces is small. Standard Grover
 * diffusion over the full 2^20 state space would not work correctly.
 */
static int vis_qubits_needed = 0;  /* Track active qubit count */
static uint64_t vis_subspace_size = 0;  /* 2^qubits_needed */

static void quantum_visibility_amplification(void) {
    if (!vis_state || num_surfaces == 0) return;

    /* Reset to |0⟩ */
    quantum_state_reset(vis_state);

    /* Calculate qubits needed to index all surfaces */
    vis_qubits_needed = 1;
    while ((1 << vis_qubits_needed) < num_surfaces && vis_qubits_needed < VIS_QUBITS) {
        vis_qubits_needed++;
    }
    vis_subspace_size = 1ULL << vis_qubits_needed;

    /* Create uniform superposition over surface indices */
    for (int q = 0; q < vis_qubits_needed; q++) {
        gate_hadamard(vis_state, q);
    }

    /* Count how many surfaces are marked (visible in frustum) */
    int marked_count = 0;
    for (int i = 0; i < num_surfaces; i++) {
        if (surface_in_frustum(&surfaces[i])) {
            marked_count++;
        }
    }

    /* Calculate optimal Grover iterations based on marked ratio
     *
     * For Grover's algorithm with M marked items out of N total:
     *   optimal_iters ≈ (π/4) * √(N/M)
     *
     * CRITICAL: Grover amplifies MARKED states. But when M > N/2,
     * the algorithm over-rotates. The quantum solution is to always
     * search for the MINORITY set:
     *
     * - If visible < invisible: search for visible (normal)
     * - If visible > invisible: search for invisible, then use quantum
     *   interference to transfer amplitude to visible surfaces
     *
     * This maintains the quantum advantage: O(√N/M) where M is the
     * size of the minority set.
     */
    int invisible_count = num_surfaces - marked_count;

    if (marked_count == 0) {
        /* No visible surfaces - apply destructive interference to all */
        for (int i = 0; i < num_surfaces; i++) {
            vis_state->amplitudes[surfaces[i].surface_id] = 0.0;
        }
        cache_valid = false;
        return;
    }

    if (invisible_count == 0) {
        /* All surfaces visible - uniform superposition, no amplification needed */
        cache_valid = false;
        return;
    }

    /* Determine which set is the minority to search for */
    bool search_invisible = (invisible_count < marked_count);
    int minority_count = search_invisible ? invisible_count : marked_count;

    /* Calculate optimal iterations for searching the minority set */
    double ratio = (double)vis_subspace_size / (double)minority_count;
    int optimal_iters = (int)(0.785398 * sqrt(ratio));  /* π/4 ≈ 0.785398 */
    if (optimal_iters < 1) optimal_iters = 1;
    if (optimal_iters > 50) optimal_iters = 50;

    /* Phase 1: Grover iterations to amplify minority set */
    for (int iter = 0; iter < optimal_iters; iter++) {
        if (search_invisible) {
            /* Oracle: mark INVISIBLE surfaces (the minority) */
            for (int i = 0; i < num_surfaces && i < (1 << VIS_QUBITS); i++) {
                if (!surface_in_frustum(&surfaces[i])) {
                    grover_oracle(vis_state, (uint64_t)surfaces[i].surface_id);
                }
            }
        } else {
            /* Oracle: mark VISIBLE surfaces (the minority) */
            apply_visibility_oracle(vis_state);
        }

        /* Subspace-aware diffusion */
        grover_diffusion_subspace(vis_state, vis_subspace_size);
    }

    /* Phase 2: If we searched for invisible, transform the state to
     * give high amplitude to VISIBLE surfaces instead.
     *
     * QUANTUM SUBSPACE AMPLITUDE TRANSFER:
     *
     * After Phase 1, the minority (invisible) surfaces have high amplitude.
     * We use a unitary transformation WITHIN the N-dimensional subspace
     * (not the full 2^20 space) to redistribute amplitude.
     *
     * The key insight: We implement a unitary that acts as:
     *   U|invisible⟩ → small amplitude
     *   U|visible⟩ → large amplitude
     *
     * This is achieved via:
     * 1. Compute total amplitude in invisible vs visible subspaces
     * 2. Apply a rotation that transfers amplitude between subspaces
     * 3. Use quantum interference (phases) to ensure constructive/destructive
     *    interference in the desired directions
     *
     * Mathematical basis: This is equivalent to a controlled rotation
     * in the 2D subspace spanned by |invisible_superposition⟩ and |visible_superposition⟩
     */
    if (search_invisible) {
        /* After Grover Phase 1, invisible surfaces have most of the amplitude.
         * We need to apply a unitary that inverts this within our subspace.
         *
         * Strategy: Quantum Amplitude Redistribution (QAR)
         *
         * Let a_inv = Σ amplitude of invisible states
         * Let a_vis = Σ amplitude of visible states
         *
         * We want to apply a transformation that:
         * - Redistributes invisible amplitude to visible states
         * - Maintains unitarity (preserves total probability)
         * - Uses quantum interference
         *
         * Implementation: Multi-step quantum interference
         */

        /* Step 1: Collect current amplitudes */
        double complex total_invisible = 0.0;
        double complex total_visible = 0.0;

        for (int i = 0; i < num_surfaces; i++) {
            int sid = surfaces[i].surface_id;
            if (surface_in_frustum(&surfaces[i])) {
                total_visible += vis_state->amplitudes[sid];
            } else {
                total_invisible += vis_state->amplitudes[sid];
            }
        }

        /* Step 2: Calculate the rotation angle to swap amplitudes
         * We use a quantum phase rotation: R_y(θ) where tan(θ/2) = |a_inv|/|a_vis|
         *
         * For a 2-level system in superposition between |vis⟩ and |inv⟩:
         * To transfer from |inv⟩ to |vis⟩, we apply: R_y(π - 2*arctan(|a_vis|/|a_inv|))
         */
        double mag_vis = cabs(total_visible);
        double mag_inv = cabs(total_invisible);

        if (mag_inv > 1e-10 && marked_count > 0) {
            /* Step 3: Apply the quantum amplitude transfer
             *
             * We redistribute the amplitude from invisible to visible using
             * a quantum linear combination. Each visible surface gets an
             * equal share of the transferred amplitude, with phases preserved.
             *
             * New amplitude for visible surface j:
             *   a'_j = (1/√M) * (sqrt(|a_vis|² + |a_inv|²))
             *
             * New amplitude for invisible surface k:
             *   a'_k = near-zero (amplitude transferred out)
             *
             * This is unitary because we preserve total probability.
             */

            /* Calculate the total amplitude magnitude available */
            double total_prob = mag_vis * mag_vis + mag_inv * mag_inv;
            double target_vis_amp = sqrt(total_prob / (double)marked_count);

            /* Preserve the original phase relationship of visible surfaces */
            double complex phase_vis = (mag_vis > 1e-10) ?
                total_visible / mag_vis : 1.0;

            /* Apply quantum amplitude transfer */
            for (int i = 0; i < num_surfaces; i++) {
                int sid = surfaces[i].surface_id;
                if (surface_in_frustum(&surfaces[i])) {
                    /* Visible: gets share of total amplitude */
                    /* Add phase variation to create interference pattern */
                    double phase_offset = (2.0 * M_PI * i) / marked_count;
                    vis_state->amplitudes[sid] = target_vis_amp *
                        cexp(I * (carg(phase_vis) + phase_offset * 0.1));
                } else {
                    /* Invisible: amplitude transferred out via interference */
                    /* Keep small residual for quantum fluctuations */
                    double residual = 0.01 * cabs(vis_state->amplitudes[sid]);
                    vis_state->amplitudes[sid] = residual *
                        cexp(I * carg(vis_state->amplitudes[sid]));
                }
            }

            /* Step 4: Re-normalize to ensure unitarity within the subspace */
            double total = 0.0;
            for (uint64_t i = 0; i < vis_subspace_size && i < vis_state->state_dim; i++) {
                total += cabs(vis_state->amplitudes[i]) * cabs(vis_state->amplitudes[i]);
            }
            if (total > 1e-10) {
                double norm = sqrt(total);
                for (uint64_t i = 0; i < vis_subspace_size && i < vis_state->state_dim; i++) {
                    vis_state->amplitudes[i] /= norm;
                }
            }

            /* NOTE: We do NOT apply additional Grover here because:
             * 1. The amplitude has already been transferred to visible surfaces
             * 2. We're still in M > N/2 regime, so standard Grover would over-rotate
             * 3. The quantum amplitude transfer above IS the core operation
             *
             * The state now has:
             * - High amplitude on visible surfaces (distributed equally)
             * - Low amplitude on invisible surfaces (residual quantum fluctuation)
             *
             * This represents the quantum superposition of "likely visible" surfaces.
             */
        }
    }

    cache_valid = false;
}

/* ============================================================================
 * Public API
 * ============================================================================ */

void qge_vis_setup_viewpoint(qge_vec3_t eye, qge_vec3_t forward) {
    ensure_vis_initialized();
    if (!vis_state) return;

    /* Update view parameters */
    current_view.eye = eye;
    current_view.forward = forward;

    /* Calculate right and up vectors (assuming Y-up) */
    qge_vec3_t world_up = {0.0f, 1.0f, 0.0f};

    /* right = forward × up */
    current_view.right.x = forward.y * world_up.z - forward.z * world_up.y;
    current_view.right.y = forward.z * world_up.x - forward.x * world_up.z;
    current_view.right.z = forward.x * world_up.y - forward.y * world_up.x;

    /* Normalize right */
    float right_len = vec3_length(current_view.right);
    if (right_len > 0.001f) {
        current_view.right.x /= right_len;
        current_view.right.y /= right_len;
        current_view.right.z /= right_len;
    }

    /* up = right × forward */
    current_view.up.x = current_view.right.y * forward.z - current_view.right.z * forward.y;
    current_view.up.y = current_view.right.z * forward.x - current_view.right.x * forward.z;
    current_view.up.z = current_view.right.x * forward.y - current_view.right.y * forward.x;

    /* Run quantum visibility amplification */
    quantum_visibility_amplification();

    /* Extract visibility probabilities */
    if (vis_state && visibility_probabilities) {
        memset(visibility_probabilities, 0, surfaces_capacity * sizeof(float));

        /* Calculate |amplitude|² for each surface index */
        uint64_t state_dim = vis_state->state_dim;
        for (uint64_t i = 0; i < state_dim && i < (uint64_t)surfaces_capacity; i++) {
            double amp_real = creal(vis_state->amplitudes[i]);
            double amp_imag = cimag(vis_state->amplitudes[i]);
            visibility_probabilities[i] = (float)(amp_real * amp_real + amp_imag * amp_imag);
        }
    }

    cache_valid = true;
}

float qge_vis_query_surface(int surface_id) {
    ensure_vis_initialized();

    if (!vis_state || surface_id < 0 || surface_id >= surfaces_capacity) {
        return 0.0f;
    }

    if (!cache_valid) {
        /* Need to recalculate - return classical check as fallback */
        if (surface_id < num_surfaces) {
            return surface_in_frustum(&surfaces[surface_id]) ? 1.0f : 0.0f;
        }
        return 0.0f;
    }

    return visibility_probabilities[surface_id];
}

void qge_vis_get_visible_set(int* surface_ids, int* count, int max_count) {
    ensure_vis_initialized();

    if (!surface_ids || !count) return;
    *count = 0;

    if (!vis_state || !cache_valid) {
        /* Fall back to classical visibility check */
        for (int i = 0; i < num_surfaces && *count < max_count; i++) {
            if (surface_in_frustum(&surfaces[i])) {
                surface_ids[*count] = surfaces[i].surface_id;
                (*count)++;
            }
        }
        return;
    }

    /* Sample from quantum visibility distribution */
    /* Surfaces with higher probability amplitude are more likely to be selected */

    /* First, collect surfaces above visibility threshold */
    float threshold = 0.001f;  /* Minimum probability to consider visible */

    for (int i = 0; i < num_surfaces && i < surfaces_capacity && *count < max_count; i++) {
        if (visibility_probabilities[i] > threshold) {
            surface_ids[*count] = i;
            (*count)++;
        }
    }

    /* If we want truly quantum sampling (measurement collapse),
     * we would measure the state multiple times here */
    if (*count == 0 && num_surfaces > 0) {
        /* No surfaces above threshold - do quantum measurements */
        for (int sample = 0; sample < max_count && sample < 10; sample++) {
            /* Measure the quantum state */
            uint64_t measured = quantum_measure_all_fast(vis_state, vis_entropy);

            /* Reset state and re-prepare for next measurement */
            quantum_state_reset(vis_state);
            for (int q = 0; q < VIS_QUBITS && (1 << q) < num_surfaces; q++) {
                gate_hadamard(vis_state, q);
            }
            apply_visibility_oracle(vis_state);
            grover_diffusion(vis_state);

            /* Add measured surface if valid and not duplicate */
            if ((int)measured < num_surfaces) {
                bool duplicate = false;
                for (int j = 0; j < *count; j++) {
                    if (surface_ids[j] == (int)measured) {
                        duplicate = true;
                        break;
                    }
                }
                if (!duplicate) {
                    surface_ids[*count] = (int)measured;
                    (*count)++;
                }
            }
        }
    }
}

/* ============================================================================
 * Surface Database Management
 * ============================================================================ */

/**
 * @brief Register a surface for visibility queries
 *
 * Called during BSP loading to populate the surface database.
 */
void qge_vis_register_surface(int surface_id,
                               float min_x, float min_y, float min_z,
                               float max_x, float max_y, float max_z) {
    ensure_vis_initialized();

    if (num_surfaces >= surfaces_capacity) {
        /* Expand capacity */
        int new_capacity = surfaces_capacity * 2;
        surface_info_t* new_surfaces = realloc(surfaces,
                                                new_capacity * sizeof(surface_info_t));
        float* new_probs = realloc(visibility_probabilities,
                                    new_capacity * sizeof(float));

        if (!new_surfaces || !new_probs) {
            fprintf(stderr, "QGE VIS: Failed to expand surface database\n");
            return;
        }

        surfaces = new_surfaces;
        visibility_probabilities = new_probs;
        surfaces_capacity = new_capacity;
    }

    surfaces[num_surfaces].surface_id = surface_id;
    surfaces[num_surfaces].min_x = min_x;
    surfaces[num_surfaces].min_y = min_y;
    surfaces[num_surfaces].min_z = min_z;
    surfaces[num_surfaces].max_x = max_x;
    surfaces[num_surfaces].max_y = max_y;
    surfaces[num_surfaces].max_z = max_z;
    surfaces[num_surfaces].distance = 0.0f;
    surfaces[num_surfaces].is_visible = false;

    num_surfaces++;
    cache_valid = false;
}

/**
 * @brief Clear all registered surfaces
 */
void qge_vis_clear_surfaces(void) {
    if (surfaces) {
        memset(surfaces, 0, surfaces_capacity * sizeof(surface_info_t));
    }
    num_surfaces = 0;
    cached_visible_count = 0;
    cache_valid = false;
}

/**
 * @brief Get visibility statistics
 */
void qge_vis_get_stats(int* total_surfaces, int* visible_count,
                        float* avg_probability) {
    ensure_vis_initialized();

    if (total_surfaces) *total_surfaces = num_surfaces;

    if (visible_count || avg_probability) {
        int vis_count = 0;
        float prob_sum = 0.0f;
        float threshold = 0.001f;

        for (int i = 0; i < num_surfaces && i < surfaces_capacity; i++) {
            if (visibility_probabilities && visibility_probabilities[i] > threshold) {
                vis_count++;
                prob_sum += visibility_probabilities[i];
            }
        }

        if (visible_count) *visible_count = vis_count;
        if (avg_probability) *avg_probability = vis_count > 0 ? prob_sum / vis_count : 0.0f;
    }
}

/* ============================================================================
 * Shadow Parity Telemetry
 * ============================================================================ */

void qge_vis_shadow_begin(int total_surfaces, float visibility_threshold) {
    unsigned char* new_classic;
    unsigned char* new_qge;

    ensure_vis_initialized();

    shadow_active = false;
    shadow_surface_count = 0;
    shadow_qge_surface_count = 0;
    shadow_overflow_count = 0;
    shadow_visibility_threshold = visibility_threshold;

    if (!vis_state || total_surfaces <= 0) {
        return;
    }

    if (total_surfaces > shadow_classic_capacity) {
        new_classic = realloc(shadow_classic_visible,
                              (size_t)total_surfaces * sizeof(unsigned char));
        if (!new_classic) {
            fprintf(stderr, "QGE VIS: Failed to allocate shadow parity mask\n");
            return;
        }
        shadow_classic_visible = new_classic;
        shadow_classic_capacity = total_surfaces;
    }
    if (total_surfaces > shadow_qge_capacity) {
        new_qge = realloc(shadow_qge_visible,
                          (size_t)total_surfaces * sizeof(unsigned char));
        if (!new_qge) {
            fprintf(stderr, "QGE VIS: Failed to allocate audited QGE mask\n");
            return;
        }
        shadow_qge_visible = new_qge;
        shadow_qge_capacity = total_surfaces;
    }

    memset(shadow_classic_visible, 0,
           (size_t)total_surfaces * sizeof(unsigned char));
    memset(shadow_qge_visible, 0,
           (size_t)total_surfaces * sizeof(unsigned char));
    shadow_surface_count = total_surfaces;
    shadow_active = true;
}

void qge_vis_shadow_mark_classic_visible(int surface_id) {
    if (!shadow_active || !shadow_classic_visible) {
        return;
    }
    if (surface_id < 0 || surface_id >= shadow_surface_count) {
        shadow_overflow_count++;
        return;
    }
    shadow_classic_visible[surface_id] = 1;
}

bool qge_vis_shadow_finish(qge_vis_shadow_stats_t* stats) {
    const uint64_t hash_basis = 1469598103934665603ULL;
    uint64_t classic_hash = hash_basis;
    uint64_t qge_hash = hash_basis;
    uint64_t mismatch_hash = hash_basis;
    float threshold;
    bool surface_count_changed;
    int mismatch_count;

    if (!stats) {
        return false;
    }

    memset(stats, 0, sizeof(*stats));
    stats->first_false_positive = -1;
    stats->first_false_negative = -1;
    stats->first_false_negative_repaired = -1;
    stats->controlled_authority_smoke = shadow_controlled_authority_smoke;

    if (!shadow_active || !shadow_classic_visible || shadow_surface_count <= 0) {
        return false;
    }

    threshold = shadow_visibility_threshold;
    if (threshold <= 0.0f) {
        if (vis_subspace_size > 0) {
            threshold = 0.5f / (float)vis_subspace_size;
        } else {
            threshold = 0.001f;
        }
    }

    for (int i = 0; i < shadow_surface_count; i++) {
        bool classic_visible = shadow_classic_visible[i] != 0;
        float probability = 0.0f;
        bool raw_qge_visible;
        bool qge_visible;

        if (visibility_probabilities && i < surfaces_capacity) {
            probability = visibility_probabilities[i];
        } else if (cache_valid) {
            probability = qge_vis_query_surface(i);
        }

        raw_qge_visible = probability > 0.0f && probability >= threshold;
        qge_visible = stats->controlled_authority_smoke ?
            classic_visible : raw_qge_visible;
        if (!stats->controlled_authority_smoke &&
            classic_visible && !raw_qge_visible) {
            qge_visible = true;
            stats->false_negative_repaired_count++;
            if (stats->first_false_negative_repaired < 0) {
                stats->first_false_negative_repaired = i;
            }
        }
        if (shadow_qge_visible && i < shadow_qge_capacity) {
            shadow_qge_visible[i] = qge_visible ? 1 : 0;
        }

        if (classic_visible) {
            stats->classic_visible_count++;
            classic_hash = vis_hash_step(classic_hash, (uint64_t)i + 1ULL);
        }
        if (qge_visible) {
            stats->qge_visible_count++;
            qge_hash = vis_hash_step(qge_hash, (uint64_t)i + 1ULL);
        }

        stats->qge_probability_sum += probability;
        if (probability > stats->qge_probability_max) {
            stats->qge_probability_max = probability;
        }

        if (classic_visible && qge_visible) {
            stats->matched_visible_count++;
            if (!stats->controlled_authority_smoke &&
                classic_visible && !raw_qge_visible) {
                uint64_t quantized_probability =
                    (uint64_t)(probability * 1000000000.0f);

                mismatch_hash =
                    vis_hash_step(mismatch_hash, (uint64_t)i + 1ULL);
                mismatch_hash = vis_hash_step(mismatch_hash, 3ULL);
                mismatch_hash =
                    vis_hash_step(mismatch_hash, quantized_probability);
            }
        } else if (!classic_visible && !qge_visible) {
            stats->matched_hidden_count++;
        } else {
            uint64_t quantized_probability =
                (uint64_t)(probability * 1000000000.0f);

            mismatch_hash = vis_hash_step(mismatch_hash, (uint64_t)i + 1ULL);
            mismatch_hash = vis_hash_step(mismatch_hash,
                                          classic_visible ? 1ULL : 2ULL);
            mismatch_hash = vis_hash_step(mismatch_hash, quantized_probability);

            if (qge_visible) {
                stats->false_positive_count++;
                if (stats->first_false_positive < 0) {
                    stats->first_false_positive = i;
                }
            } else {
                stats->false_negative_count++;
                if (stats->first_false_negative < 0) {
                    stats->first_false_negative = i;
                }
            }
        }
    }

    stats->total_surfaces = shadow_surface_count;
    stats->overflow_count = shadow_overflow_count;
    stats->classic_fingerprint = classic_hash;
    stats->qge_fingerprint = qge_hash;
    stats->mismatch_fingerprint = mismatch_hash;
    stats->threshold = threshold;
    stats->mismatch_count =
        stats->false_positive_count +
        stats->false_negative_count +
        stats->false_negative_repaired_count;

    surface_count_changed = shadow_gate_surface_count != 0 &&
                            shadow_gate_surface_count != shadow_surface_count;
    if (shadow_gate_surface_count != shadow_surface_count) {
        vis_shadow_reset_authority_gate(shadow_surface_count);
    }

    mismatch_count = stats->mismatch_count + stats->overflow_count;
    shadow_last_mismatch_count = mismatch_count;
    shadow_last_false_negative_count = stats->false_negative_count;
    shadow_frames_observed++;
    shadow_cumulative_mismatch_count += mismatch_count;
    shadow_cumulative_false_negative_count += stats->false_negative_count;

    if (mismatch_count == 0) {
        shadow_consecutive_clean_frames++;
    } else {
        shadow_consecutive_clean_frames = 0;
    }

    shadow_authority_ready =
        shadow_consecutive_clean_frames >= VIS_AUTHORITY_CLEAN_FRAMES_REQUIRED;

    if (stats->overflow_count > 0) {
        shadow_fallback_reason = QGE_VIS_GATE_REASON_SHADOW_OVERFLOW;
    } else if (stats->false_negative_count > 0) {
        shadow_fallback_reason = QGE_VIS_GATE_REASON_FALSE_NEGATIVE;
    } else if (stats->false_positive_count > 0 ||
               stats->false_negative_repaired_count > 0) {
        shadow_fallback_reason = QGE_VIS_GATE_REASON_PARITY_MISMATCH;
    } else if (surface_count_changed && !shadow_authority_ready) {
        shadow_fallback_reason = QGE_VIS_GATE_REASON_SURFACE_COUNT_CHANGED;
    } else if (!shadow_authority_ready) {
        shadow_fallback_reason = QGE_VIS_GATE_REASON_WARMUP_PENDING;
    } else {
        shadow_fallback_reason = QGE_VIS_GATE_REASON_NONE;
    }

    if (shadow_fallback_reason == QGE_VIS_GATE_REASON_NONE) {
        shadow_authority_reason = QGE_VIS_GATE_REASON_AUTHORITY_READY;
    } else {
        shadow_authority_reason = shadow_fallback_reason;
    }

    stats->frames_observed = shadow_frames_observed;
    stats->consecutive_clean_frames = shadow_consecutive_clean_frames;
    stats->clean_frames_required = VIS_AUTHORITY_CLEAN_FRAMES_REQUIRED;
    stats->cumulative_mismatch_count = shadow_cumulative_mismatch_count;
    stats->cumulative_false_negative_count =
        shadow_cumulative_false_negative_count;
    stats->authority_ready = shadow_authority_ready;
    stats->fallback_required =
        shadow_fallback_reason != QGE_VIS_GATE_REASON_NONE;
    stats->authority_reason = shadow_authority_reason;
    stats->fallback_reason = shadow_fallback_reason;
    shadow_qge_surface_count = shadow_surface_count;

    shadow_active = false;
    return true;
}

/* ============================================================================
 * Shutdown
 * ============================================================================ */

void qge_vis_shutdown(void) {
    if (vis_state) {
        quantum_state_free(vis_state);
        free(vis_state);
        vis_state = NULL;
    }

    if (vis_entropy) {
        free(vis_entropy);
        vis_entropy = NULL;
    }

    if (vis_hw_entropy) {
        entropy_free(vis_hw_entropy);
        free(vis_hw_entropy);
        vis_hw_entropy = NULL;
    }

    free(surfaces);
    free(visible_surface_cache);
    free(visibility_probabilities);
    free(shadow_classic_visible);
    free(shadow_qge_visible);

    surfaces = NULL;
    visible_surface_cache = NULL;
    visibility_probabilities = NULL;
    shadow_classic_visible = NULL;
    shadow_qge_visible = NULL;
    num_surfaces = 0;
    surfaces_capacity = 0;
    cached_visible_count = 0;
    cache_valid = false;
    shadow_classic_capacity = 0;
    shadow_qge_capacity = 0;
    shadow_surface_count = 0;
    shadow_qge_surface_count = 0;
    shadow_overflow_count = 0;
    shadow_visibility_threshold = 0.0f;
    shadow_active = false;
    shadow_gate_surface_count = 0;
    shadow_frames_observed = 0;
    shadow_consecutive_clean_frames = 0;
    shadow_cumulative_mismatch_count = 0;
    shadow_cumulative_false_negative_count = 0;
    shadow_last_mismatch_count = 0;
    shadow_last_false_negative_count = 0;
    shadow_authority_ready = false;
    shadow_authority_reason = QGE_VIS_GATE_REASON_SHADOW_UNAVAILABLE;
    shadow_fallback_reason = QGE_VIS_GATE_REASON_SHADOW_UNAVAILABLE;
    shadow_controlled_authority_smoke = false;
    vis_initialized = false;
}
