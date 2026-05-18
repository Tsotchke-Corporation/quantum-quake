/**
 * @file qge_physics.c
 * @brief Quantum Physics - Particle system using quantum time evolution
 *
 * Uses quantum mechanics to simulate particle systems:
 * - Particle positions encoded in quantum state superposition
 * - Time evolution via Schrödinger equation (e^(-iHt/ℏ))
 * - Measurement collapses to specific positions
 * - Quantum interference creates natural wave-like behavior
 *
 * Physics background:
 * In quantum mechanics, a particle's position is described by a wave function
 * ψ(x,y,z). The probability of finding the particle at position (x,y,z) is |ψ|².
 *
 * For game particles (explosions, smoke, sparks), we encode:
 * - Position register: 3D spatial coordinates
 * - Velocity encoded as phase evolution
 * - Lifetime as amplitude decay (decoherence)
 *
 * This creates physically-inspired particle dynamics with quantum characteristics:
 * - Particles can be in superposition of positions (fuzzy clouds)
 * - Interference creates ripple patterns
 * - Measurement reveals specific positions for rendering
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

#define PHYSICS_QUBITS_PER_AXIS 6   /* 2^6 = 64 positions per axis */
#define PHYSICS_TOTAL_QUBITS 18     /* 6 qubits × 3 axes = 18 qubits */
#define PHYSICS_GRID_SIZE 64        /* 64×64×64 spatial grid */
#define MAX_PARTICLES_PER_SYSTEM 64

/* ============================================================================
 * Particle Structure
 * ============================================================================ */

typedef struct {
    qge_vec3_t position;        /* Current center position */
    qge_vec3_t velocity;        /* Velocity vector */
    float lifetime;         /* Remaining lifetime (seconds) */
    float max_lifetime;     /* Initial lifetime */
    float spread;           /* Spatial spread (quantum uncertainty) */
    bool active;            /* Is this particle slot in use? */
    int id;                 /* Unique particle ID */
} particle_t;

struct qge_particle_system_s {
    quantum_state_t* state;     /* Quantum state for particle superposition */
    particle_t* particles;      /* Array of particles */
    int max_particles;          /* Capacity */
    int active_count;           /* Current active particle count */
    float gravity;              /* Gravity strength */
    float drag;                 /* Air drag coefficient */
    int next_id;                /* Next particle ID */
};

/* ============================================================================
 * Module State
 * ============================================================================ */

static bool physics_initialized = false;
static quantum_entropy_ctx_t* physics_entropy = NULL;
static entropy_ctx_t* physics_hw_entropy = NULL;

/* ============================================================================
 * Projectile Authority Gate
 * ============================================================================ */

qge_projectile_authority_gate_t qge_projectile_authority_default_gate(void) {
    qge_projectile_authority_gate_t gate;

    gate.warmup_frames_required =
        QGE_PROJECTILE_AUTHORITY_DEFAULT_WARMUP_FRAMES;
    gate.min_shadow_samples =
        QGE_PROJECTILE_AUTHORITY_DEFAULT_MIN_SHADOW_SAMPLES;
    gate.avg_shadow_error_max =
        QGE_PROJECTILE_AUTHORITY_DEFAULT_AVG_SHADOW_ERROR_MAX;
    gate.max_shadow_error_max =
        QGE_PROJECTILE_AUTHORITY_DEFAULT_MAX_SHADOW_ERROR_MAX;
    return gate;
}

static qge_projectile_authority_gate_t normalize_projectile_authority_gate(
    const qge_projectile_authority_gate_t* gate) {
    qge_projectile_authority_gate_t out =
        qge_projectile_authority_default_gate();

    if (!gate) {
        return out;
    }

    out = *gate;
    if (out.warmup_frames_required < 0) {
        out.warmup_frames_required =
            QGE_PROJECTILE_AUTHORITY_DEFAULT_WARMUP_FRAMES;
    }
    if (out.min_shadow_samples < 0) {
        out.min_shadow_samples =
            QGE_PROJECTILE_AUTHORITY_DEFAULT_MIN_SHADOW_SAMPLES;
    }
    if (!isfinite(out.avg_shadow_error_max) ||
        out.avg_shadow_error_max < 0.0f) {
        out.avg_shadow_error_max =
            QGE_PROJECTILE_AUTHORITY_DEFAULT_AVG_SHADOW_ERROR_MAX;
    }
    if (!isfinite(out.max_shadow_error_max) ||
        out.max_shadow_error_max < 0.0f) {
        out.max_shadow_error_max =
            QGE_PROJECTILE_AUTHORITY_DEFAULT_MAX_SHADOW_ERROR_MAX;
    }
    return out;
}

const char* qge_projectile_authority_off_reason_name(
    qge_projectile_authority_off_reason_t reason) {
    switch (reason) {
    case QGE_PROJECTILE_AUTHORITY_OFF_NONE:
        return "none";
    case QGE_PROJECTILE_AUTHORITY_OFF_DISABLED:
        return "disabled";
    case QGE_PROJECTILE_AUTHORITY_OFF_NO_PROJECTILES:
        return "no_projectiles";
    case QGE_PROJECTILE_AUTHORITY_OFF_WARMUP:
        return "warmup";
    case QGE_PROJECTILE_AUTHORITY_OFF_SHADOW_MAX:
        return "shadow_max";
    case QGE_PROJECTILE_AUTHORITY_OFF_SHADOW_AVG:
        return "shadow_avg";
    default:
        return "unknown";
    }
}

qge_projectile_authority_state_t qge_projectile_authority_evaluate(
    const qge_projectile_authority_gate_t* gate,
    const qge_projectile_authority_telemetry_t* telemetry) {
    qge_projectile_authority_gate_t g =
        normalize_projectile_authority_gate(gate);
    qge_projectile_authority_state_t state;
    float avg_error;
    float max_error;

    memset(&state, 0, sizeof(state));
    state.off_reason = QGE_PROJECTILE_AUTHORITY_OFF_DISABLED;
    state.warmup_frames_remaining = g.warmup_frames_required;
    state.shadow_samples_remaining = g.min_shadow_samples;
    state.avg_shadow_error_margin = g.avg_shadow_error_max;
    state.max_shadow_error_margin = g.max_shadow_error_max;

    if (!telemetry || !telemetry->requested) {
        return state;
    }

    state.off_reason = QGE_PROJECTILE_AUTHORITY_OFF_NO_PROJECTILES;
    if (telemetry->active_projectiles <= 0 &&
        telemetry->frame_projectiles <= 0) {
        return state;
    }

    state.off_reason = QGE_PROJECTILE_AUTHORITY_OFF_WARMUP;
    state.warmup_frames_remaining =
        g.warmup_frames_required - telemetry->warmup_frames;
    state.shadow_samples_remaining =
        g.min_shadow_samples - telemetry->shadow_samples;
    if (state.warmup_frames_remaining < 0) {
        state.warmup_frames_remaining = 0;
    }
    if (state.shadow_samples_remaining < 0) {
        state.shadow_samples_remaining = 0;
    }
    if (telemetry->warmup_frames < g.warmup_frames_required ||
        telemetry->shadow_samples < g.min_shadow_samples) {
        return state;
    }

    avg_error = telemetry->avg_shadow_error;
    max_error = telemetry->max_shadow_error;
    if (!isfinite(avg_error) || avg_error < 0.0f) {
        avg_error = g.avg_shadow_error_max + 1.0f;
    }
    if (!isfinite(max_error) || max_error < 0.0f) {
        max_error = g.max_shadow_error_max + 1.0f;
    }
    state.avg_shadow_error_margin = g.avg_shadow_error_max - avg_error;
    state.max_shadow_error_margin = g.max_shadow_error_max - max_error;

    if (max_error > g.max_shadow_error_max) {
        state.off_reason = QGE_PROJECTILE_AUTHORITY_OFF_SHADOW_MAX;
        return state;
    }
    if (avg_error > g.avg_shadow_error_max) {
        state.off_reason = QGE_PROJECTILE_AUTHORITY_OFF_SHADOW_AVG;
        return state;
    }

    state.ready = true;
    state.off_reason = QGE_PROJECTILE_AUTHORITY_OFF_NONE;
    return state;
}

static qge_vec3_t qge_vec3_delta(qge_vec3_t to, qge_vec3_t from) {
    qge_vec3_t delta;

    delta.x = to.x - from.x;
    delta.y = to.y - from.y;
    delta.z = to.z - from.z;
    return delta;
}

static float qge_vec3_length(qge_vec3_t v) {
    return sqrtf(v.x * v.x + v.y * v.y + v.z * v.z);
}

qge_projectile_writeback_decision_t qge_projectile_writeback_evaluate(
    const qge_projectile_authority_gate_t* gate,
    const qge_projectile_writeback_request_t* request) {
    qge_projectile_writeback_decision_t decision;
    qge_projectile_authority_telemetry_t telemetry;

    memset(&decision, 0, sizeof(decision));
    decision.source = QGE_PROJECTILE_WRITEBACK_CLASSIC;
    decision.off_reason = QGE_PROJECTILE_AUTHORITY_OFF_DISABLED;
    decision.fallback_reason = QGE_PROJECTILE_AUTHORITY_OFF_DISABLED;
    decision.rollback_reason = QGE_PROJECTILE_AUTHORITY_OFF_NONE;

    memset(&telemetry, 0, sizeof(telemetry));
    if (request) {
        telemetry = request->telemetry;
        decision.entity_id = request->entity_id;
        decision.authority_requested = telemetry.requested;
        decision.origin_delta =
            qge_vec3_delta(request->qge_origin, request->classic_origin);
        decision.velocity_delta =
            qge_vec3_delta(request->qge_velocity, request->classic_velocity);
        decision.origin_delta_length =
            qge_vec3_length(decision.origin_delta);
        decision.velocity_delta_length =
            qge_vec3_length(decision.velocity_delta);
    }

    decision.gate_state =
        qge_projectile_authority_evaluate(gate, request ? &telemetry : NULL);
    decision.authority_ready = decision.gate_state.ready;
    decision.off_reason = decision.gate_state.off_reason;

    if (decision.gate_state.ready) {
        decision.writeback_allowed = true;
        decision.fallback_selected = false;
        decision.rollback_required = false;
        decision.source = QGE_PROJECTILE_WRITEBACK_QGE;
        decision.fallback_reason = QGE_PROJECTILE_AUTHORITY_OFF_NONE;
        decision.rollback_reason = QGE_PROJECTILE_AUTHORITY_OFF_NONE;
        return decision;
    }

    decision.writeback_allowed = false;
    decision.fallback_selected = true;
    decision.source = QGE_PROJECTILE_WRITEBACK_CLASSIC;
    decision.fallback_reason = decision.gate_state.off_reason;
    if (decision.authority_requested &&
        (decision.gate_state.off_reason ==
             QGE_PROJECTILE_AUTHORITY_OFF_SHADOW_MAX ||
         decision.gate_state.off_reason ==
             QGE_PROJECTILE_AUTHORITY_OFF_SHADOW_AVG)) {
        decision.rollback_required = true;
        decision.rollback_reason = decision.gate_state.off_reason;
    }

    return decision;
}

/* ============================================================================
 * Entropy Callback
 * ============================================================================ */

static int physics_entropy_callback(void *user_data, uint8_t *buffer, size_t size) {
    entropy_ctx_t *ctx = (entropy_ctx_t *)user_data;
    return entropy_get_bytes(ctx, buffer, size);
}

/* ============================================================================
 * Initialization
 * ============================================================================ */

static void ensure_physics_initialized(void) {
    if (physics_initialized) return;

    /* Initialize hardware entropy */
    physics_hw_entropy = malloc(sizeof(entropy_ctx_t));
    if (!physics_hw_entropy || entropy_init(physics_hw_entropy) != ENTROPY_SUCCESS) {
        fprintf(stderr, "QGE PHYSICS: Failed to init hardware entropy\n");
        free(physics_hw_entropy);
        physics_hw_entropy = NULL;
        return;
    }

    /* Initialize quantum entropy context */
    physics_entropy = malloc(sizeof(quantum_entropy_ctx_t));
    if (!physics_entropy) {
        fprintf(stderr, "QGE PHYSICS: Failed to allocate entropy context\n");
        entropy_free(physics_hw_entropy);
        free(physics_hw_entropy);
        physics_hw_entropy = NULL;
        return;
    }
    quantum_entropy_init(physics_entropy, physics_entropy_callback, physics_hw_entropy);

    physics_initialized = true;
}

/* ============================================================================
 * Particle System
 * ============================================================================ */

qge_particle_system_t* qge_particle_system_create(int max_particles) {
    ensure_physics_initialized();

    if (max_particles <= 0) max_particles = 32;
    if (max_particles > MAX_PARTICLES_PER_SYSTEM) max_particles = MAX_PARTICLES_PER_SYSTEM;

    qge_particle_system_t* sys = malloc(sizeof(qge_particle_system_t));
    if (!sys) return NULL;

    /* Allocate quantum state
     * We use a shared quantum state where each particle occupies a region
     * of the Hilbert space. For efficiency, we use 18 qubits (64³ grid). */
    sys->state = malloc(sizeof(quantum_state_t));
    if (!sys->state) {
        free(sys);
        return NULL;
    }

    qs_error_t err = quantum_state_init(sys->state, PHYSICS_TOTAL_QUBITS);
    if (err != QS_SUCCESS) {
        free(sys->state);
        free(sys);
        return NULL;
    }

    /* Initialize to ground state */
    quantum_state_reset(sys->state);

    /* Allocate particle array */
    sys->particles = calloc(max_particles, sizeof(particle_t));
    if (!sys->particles) {
        quantum_state_free(sys->state);
        free(sys->state);
        free(sys);
        return NULL;
    }

    sys->max_particles = max_particles;
    sys->active_count = 0;
    sys->gravity = 9.8f;   /* m/s² */
    sys->drag = 0.1f;      /* Drag coefficient */
    sys->next_id = 0;

    return sys;
}

void qge_particle_system_free(qge_particle_system_t* sys) {
    if (!sys) return;

    if (sys->state) {
        quantum_state_free(sys->state);
        free(sys->state);
    }
    free(sys->particles);
    free(sys);
}

/**
 * @brief Convert world position to quantum grid index
 */
static uint64_t position_to_index(qge_vec3_t pos, float scale) {
    /* Map position to [0, GRID_SIZE-1] range */
    int ix = (int)((pos.x / scale + 0.5f) * (PHYSICS_GRID_SIZE - 1));
    int iy = (int)((pos.y / scale + 0.5f) * (PHYSICS_GRID_SIZE - 1));
    int iz = (int)((pos.z / scale + 0.5f) * (PHYSICS_GRID_SIZE - 1));

    /* Clamp to valid range */
    if (ix < 0) ix = 0;
    if (iy < 0) iy = 0;
    if (iz < 0) iz = 0;
    if (ix >= PHYSICS_GRID_SIZE) ix = PHYSICS_GRID_SIZE - 1;
    if (iy >= PHYSICS_GRID_SIZE) iy = PHYSICS_GRID_SIZE - 1;
    if (iz >= PHYSICS_GRID_SIZE) iz = PHYSICS_GRID_SIZE - 1;

    /* Pack into single index: z*64² + y*64 + x */
    return (uint64_t)iz * PHYSICS_GRID_SIZE * PHYSICS_GRID_SIZE +
           (uint64_t)iy * PHYSICS_GRID_SIZE +
           (uint64_t)ix;
}

/**
 * @brief Convert quantum grid index to world position
 */
static qge_vec3_t index_to_position(uint64_t idx, float scale) {
    int ix = idx % PHYSICS_GRID_SIZE;
    int iy = (idx / PHYSICS_GRID_SIZE) % PHYSICS_GRID_SIZE;
    int iz = idx / (PHYSICS_GRID_SIZE * PHYSICS_GRID_SIZE);

    qge_vec3_t pos;
    pos.x = ((float)ix / (PHYSICS_GRID_SIZE - 1) - 0.5f) * scale;
    pos.y = ((float)iy / (PHYSICS_GRID_SIZE - 1) - 0.5f) * scale;
    pos.z = ((float)iz / (PHYSICS_GRID_SIZE - 1) - 0.5f) * scale;

    return pos;
}

/**
 * @brief Spawn a new particle
 *
 * Creates a quantum wave packet centered at the given position.
 * The wave packet represents the particle's probability distribution.
 */
void qge_particle_spawn(qge_particle_system_t* sys,
                        qge_vec3_t position, qge_vec3_t velocity,
                        float lifetime) {
    if (!sys || sys->active_count >= sys->max_particles) return;

    /* Find an inactive slot */
    int slot = -1;
    for (int i = 0; i < sys->max_particles; i++) {
        if (!sys->particles[i].active) {
            slot = i;
            break;
        }
    }
    if (slot < 0) return;

    particle_t* p = &sys->particles[slot];
    p->position = position;
    p->velocity = velocity;
    p->lifetime = lifetime;
    p->max_lifetime = lifetime;
    p->spread = 1.0f;  /* Initial spatial spread */
    p->active = true;
    p->id = sys->next_id++;

    sys->active_count++;

    /* Add quantum amplitude for this particle
     *
     * We create a Gaussian wave packet centered at the particle's position.
     * This represents quantum uncertainty in the particle's location.
     *
     * ψ(r) ∝ exp(-(r-r₀)²/(2σ²)) × exp(i k·r)
     *
     * where:
     * - r₀ is the center position
     * - σ is the spread (uncertainty)
     * - k is the wave vector (momentum/ℏ)
     */
    float scale = 100.0f;  /* World scale for mapping */
    float sigma = p->spread * (float)PHYSICS_GRID_SIZE / scale;

    /* Calculate wave packet amplitudes */
    double norm_sq = 0.0;
    uint64_t center_idx = position_to_index(position, scale);
    int cx = center_idx % PHYSICS_GRID_SIZE;
    int cy = (center_idx / PHYSICS_GRID_SIZE) % PHYSICS_GRID_SIZE;
    int cz = center_idx / (PHYSICS_GRID_SIZE * PHYSICS_GRID_SIZE);

    /* Sample around the center position */
    int range = (int)(3.0f * sigma);
    if (range < 2) range = 2;
    if (range > 10) range = 10;

    for (int dz = -range; dz <= range; dz++) {
        for (int dy = -range; dy <= range; dy++) {
            for (int dx = -range; dx <= range; dx++) {
                int ix = cx + dx;
                int iy = cy + dy;
                int iz = cz + dz;

                if (ix < 0 || ix >= PHYSICS_GRID_SIZE ||
                    iy < 0 || iy >= PHYSICS_GRID_SIZE ||
                    iz < 0 || iz >= PHYSICS_GRID_SIZE) continue;

                uint64_t idx = (uint64_t)iz * PHYSICS_GRID_SIZE * PHYSICS_GRID_SIZE +
                              (uint64_t)iy * PHYSICS_GRID_SIZE +
                              (uint64_t)ix;

                if (idx >= sys->state->state_dim) continue;

                /* Gaussian amplitude */
                float r_sq = (float)(dx*dx + dy*dy + dz*dz);
                double amp = exp(-r_sq / (2.0 * sigma * sigma));

                /* Add phase from velocity (momentum) */
                /* k = m*v/ℏ, phase = k·r */
                float phase = (velocity.x * dx + velocity.y * dy + velocity.z * dz) * 0.1f;

                /* Add to quantum state (coherent superposition) */
                sys->state->amplitudes[idx] += amp * cexp(I * phase);
                norm_sq += amp * amp;
            }
        }
    }

    /* Normalize the state */
    if (norm_sq > 0) {
        double total = 0.0;
        for (uint64_t i = 0; i < sys->state->state_dim; i++) {
            double ar = creal(sys->state->amplitudes[i]);
            double ai = cimag(sys->state->amplitudes[i]);
            total += ar * ar + ai * ai;
        }
        if (total > 0) {
            double norm = sqrt(total);
            for (uint64_t i = 0; i < sys->state->state_dim; i++) {
                sys->state->amplitudes[i] /= norm;
            }
        }
    }
}

/**
 * @brief Evolve the particle system using quantum time evolution
 *
 * Applies the quantum time evolution operator U(t) = e^(-iHt/ℏ).
 *
 * For our particle system, the Hamiltonian includes:
 * 1. Kinetic term: causes wave packet spreading
 * 2. Potential term (gravity): shifts the wave packet downward
 * 3. Decoherence: reduces amplitude of distant positions (lifetime decay)
 *
 * This is a simplified version of TDVP (Time-Dependent Variational Principle).
 */
void qge_particle_evolve(qge_particle_system_t* sys, float dt) {
    if (!sys || sys->active_count == 0) return;

    /* Evolve each particle classically (position update) */
    for (int p = 0; p < sys->max_particles; p++) {
        if (!sys->particles[p].active) continue;

        particle_t* part = &sys->particles[p];

        /* Apply gravity */
        part->velocity.y -= sys->gravity * dt;

        /* Apply drag */
        part->velocity.x *= (1.0f - sys->drag * dt);
        part->velocity.y *= (1.0f - sys->drag * dt);
        part->velocity.z *= (1.0f - sys->drag * dt);

        /* Update position */
        part->position.x += part->velocity.x * dt;
        part->position.y += part->velocity.y * dt;
        part->position.z += part->velocity.z * dt;

        /* Increase spread over time (quantum diffusion) */
        part->spread += 0.5f * dt;

        /* Decay lifetime */
        part->lifetime -= dt;
        if (part->lifetime <= 0) {
            part->active = false;
            sys->active_count--;
        }
    }

    /* Quantum evolution of the wave function
     *
     * We apply phase rotations based on the Hamiltonian:
     * - Kinetic: higher momentum states get faster phase evolution
     * - Potential (gravity): position-dependent phase shift
     */

    /* Apply phase shift for gravity (potential energy) */
    for (uint64_t idx = 0; idx < sys->state->state_dim; idx++) {
        if (cabs(sys->state->amplitudes[idx]) < 1e-10) continue;

        /* Get y coordinate (height) */
        int iy = (idx / PHYSICS_GRID_SIZE) % PHYSICS_GRID_SIZE;
        float y = (float)iy / (PHYSICS_GRID_SIZE - 1);  /* 0 to 1 */

        /* Gravitational phase: φ = -mgy*t/ℏ (simplified) */
        float grav_phase = -sys->gravity * y * dt * 0.1f;

        /* Apply phase rotation */
        sys->state->amplitudes[idx] *= cexp(I * grav_phase);
    }

    /* Apply momentum-dependent phase (kinetic energy) via Hadamard mixing
     * This is a simplified discrete approximation of the kinetic term */
    for (int q = 0; q < PHYSICS_QUBITS_PER_AXIS; q++) {
        /* Apply small rotation to create spreading effect */
        float theta = 0.02f * dt;  /* Small rotation angle */

        /* Apply Ry rotation to position qubits */
        gate_ry(sys->state, q, theta);
        gate_ry(sys->state, q + PHYSICS_QUBITS_PER_AXIS, theta);
        gate_ry(sys->state, q + 2 * PHYSICS_QUBITS_PER_AXIS, theta);
    }

    /* Apply amplitude decay (decoherence / lifetime decay)
     * Particles lose amplitude over their lifetime */
    float decay_rate = 0.0f;
    for (int p = 0; p < sys->max_particles; p++) {
        if (sys->particles[p].active) {
            decay_rate += (1.0f - sys->particles[p].lifetime / sys->particles[p].max_lifetime);
        }
    }
    if (sys->active_count > 0) {
        decay_rate /= sys->active_count;
    }

    /* Apply uniform decay to all amplitudes */
    if (decay_rate > 0.01f) {
        double keep_rate = 1.0 - decay_rate * dt * 0.5;
        for (uint64_t i = 0; i < sys->state->state_dim; i++) {
            sys->state->amplitudes[i] *= keep_rate;
        }

        /* Re-normalize */
        double total = 0.0;
        for (uint64_t i = 0; i < sys->state->state_dim; i++) {
            total += cabs(sys->state->amplitudes[i]) * cabs(sys->state->amplitudes[i]);
        }
        if (total > 0) {
            double norm = sqrt(total);
            for (uint64_t i = 0; i < sys->state->state_dim; i++) {
                sys->state->amplitudes[i] /= norm;
            }
        }
    }
}

/**
 * @brief Get particle positions for rendering
 *
 * Measures the quantum state to collapse particles to specific positions.
 * For rendering, we sample multiple positions from the probability distribution.
 */
int qge_particle_get_positions(qge_particle_system_t* sys,
                                qge_vec3_t* positions, int max_count) {
    if (!sys || !positions || max_count <= 0) return 0;
    if (sys->active_count == 0) return 0;

    float scale = 100.0f;
    int count = 0;

    /* Sample positions from quantum probability distribution
     *
     * We measure the state multiple times to get a distribution of positions.
     * Each measurement reveals a position according to |ψ|².
     */

    /* Calculate probability distribution */
    float* probabilities = calloc(sys->state->state_dim, sizeof(float));
    if (!probabilities) return 0;

    float total_prob = 0.0f;
    for (uint64_t i = 0; i < sys->state->state_dim; i++) {
        double ar = creal(sys->state->amplitudes[i]);
        double ai = cimag(sys->state->amplitudes[i]);
        probabilities[i] = (float)(ar * ar + ai * ai);
        total_prob += probabilities[i];
    }

    /* Normalize probabilities */
    if (total_prob > 0.001f) {
        for (uint64_t i = 0; i < sys->state->state_dim; i++) {
            probabilities[i] /= total_prob;
        }
    }

    /* Sample positions based on probability */
    int samples_per_particle = max_count / (sys->active_count > 0 ? sys->active_count : 1);
    if (samples_per_particle < 1) samples_per_particle = 1;

    for (int s = 0; s < max_count && count < max_count; s++) {
        /* Generate random value using quantum entropy */
        float random_val = 0.0f;
        if (physics_entropy) {
            uint32_t rand_bits;
            uint8_t bytes[4];
            quantum_entropy_get_bytes(physics_entropy, bytes, 4);
            memcpy(&rand_bits, bytes, 4);
            random_val = (float)(rand_bits & 0xFFFFFF) / (float)0xFFFFFF;
        } else {
            random_val = (float)rand() / (float)RAND_MAX;
        }

        /* Select position based on cumulative probability */
        float cumulative = 0.0f;
        uint64_t selected_idx = 0;
        for (uint64_t i = 0; i < sys->state->state_dim; i++) {
            cumulative += probabilities[i];
            if (random_val <= cumulative) {
                selected_idx = i;
                break;
            }
        }

        /* Convert index to world position */
        qge_vec3_t base_pos = index_to_position(selected_idx, scale);

        /* Find nearest active particle to offset the base position */
        float min_dist = 1e30f;
        int nearest_p = -1;
        for (int p = 0; p < sys->max_particles; p++) {
            if (sys->particles[p].active) {
                float dx = base_pos.x;  /* Base pos is relative */
                float dy = base_pos.y;
                float dz = base_pos.z;
                float dist = dx*dx + dy*dy + dz*dz;
                if (dist < min_dist) {
                    min_dist = dist;
                    nearest_p = p;
                }
            }
        }

        /* Output position is particle center + quantum offset */
        if (nearest_p >= 0) {
            positions[count].x = sys->particles[nearest_p].position.x + base_pos.x;
            positions[count].y = sys->particles[nearest_p].position.y + base_pos.y;
            positions[count].z = sys->particles[nearest_p].position.z + base_pos.z;
        } else {
            positions[count] = base_pos;
        }
        count++;
    }

    free(probabilities);
    return count;
}

/* ============================================================================
 * Additional Physics Utilities
 * ============================================================================ */

/**
 * @brief Set gravity for the particle system
 */
void qge_particle_system_set_gravity(qge_particle_system_t* sys, float gravity) {
    if (!sys) return;
    sys->gravity = gravity;
}

/**
 * @brief Set drag coefficient
 */
void qge_particle_system_set_drag(qge_particle_system_t* sys, float drag) {
    if (!sys) return;
    sys->drag = drag;
}

/**
 * @brief Get active particle count
 */
int qge_particle_system_active_count(qge_particle_system_t* sys) {
    if (!sys) return 0;
    return sys->active_count;
}

/**
 * @brief Apply an impulse to all particles (e.g., explosion)
 *
 * Uses quantum interference to create radial impulse pattern.
 */
void qge_particle_system_impulse(qge_particle_system_t* sys,
                                  qge_vec3_t center, float strength) {
    if (!sys) return;

    for (int p = 0; p < sys->max_particles; p++) {
        if (!sys->particles[p].active) continue;

        /* Calculate direction from center to particle */
        float dx = sys->particles[p].position.x - center.x;
        float dy = sys->particles[p].position.y - center.y;
        float dz = sys->particles[p].position.z - center.z;

        float dist = sqrtf(dx*dx + dy*dy + dz*dz);
        if (dist < 0.001f) dist = 0.001f;

        /* Apply inverse-square impulse (like explosion) */
        float impulse = strength / (dist * dist + 1.0f);

        sys->particles[p].velocity.x += (dx / dist) * impulse;
        sys->particles[p].velocity.y += (dy / dist) * impulse;
        sys->particles[p].velocity.z += (dz / dist) * impulse;
    }

    /* Apply quantum phase kick to create interference pattern */
    float phase_scale = strength * 0.1f;
    for (uint64_t idx = 0; idx < sys->state->state_dim; idx++) {
        if (cabs(sys->state->amplitudes[idx]) < 1e-10) continue;

        qge_vec3_t pos = index_to_position(idx, 100.0f);
        float dx = pos.x - center.x;
        float dy = pos.y - center.y;
        float dz = pos.z - center.z;
        float dist = sqrtf(dx*dx + dy*dy + dz*dz);

        /* Radial phase pattern (like ripples) */
        float phase = dist * phase_scale;
        sys->state->amplitudes[idx] *= cexp(I * phase);
    }
}

/**
 * @brief Clear all particles
 */
void qge_particle_system_clear(qge_particle_system_t* sys) {
    if (!sys) return;

    for (int p = 0; p < sys->max_particles; p++) {
        sys->particles[p].active = false;
    }
    sys->active_count = 0;

    /* Reset quantum state */
    quantum_state_reset(sys->state);
}
