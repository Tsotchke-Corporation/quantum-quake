/**
 * @file qge_ai.c
 * @brief Quantum AI for Enemy Decision-Making
 *
 * Uses genuine quantum superposition and measurement for enemy AI decisions.
 * Enemy metadata lives in a shared state; hot per-think action selection uses a
 * reusable 3-qubit decision state so busy maps do not reset a 24-qubit state
 * for every monster.
 *
 * Architecture:
 * - Each enemy gets 8 qubits for decision space
 * - Actions exist in superposition until "observed" (decision point)
 * - Measurement collapses to chosen action based on probability amplitudes
 * - Entanglement enables coordinated swarm behavior
 *
 * Qubit layout per enemy (8 qubits):
 * - Bits 0-2: Action selection (8 primary actions)
 * - Bits 3-4: Action intensity/variant
 * - Bits 5-7: Behavioral state (memory of past actions)
 */

#include "qge.h"
#include "../deps/moonlab/src/quantum/state.h"
#include "../deps/moonlab/src/quantum/gates.h"
#include "../deps/moonlab/src/quantum/measurement.h"
#include "../deps/moonlab/src/quantum/entanglement.h"
#include "../deps/moonlab/src/utils/quantum_entropy.h"
#include "../deps/moonlab/src/applications/hardware_entropy.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>

/* ============================================================================
 * Constants
 * ============================================================================ */

#define MAX_ENEMIES 64
#define QUBITS_PER_ENEMY 8
#define ACTION_QUBITS 3
#define INTENSITY_QUBITS 2
#define BEHAVIOR_QUBITS 3

/* Enemy type base aggression values */
static const float BASE_AGGRESSION[QGE_AI_ENEMY_TYPE_COUNT] = {
    0.3f,   /* monster_army */
    0.5f,   /* monster_knight */
    0.7f,   /* monster_ogre */
    0.9f,   /* monster_demon1 */
    0.6f,   /* monster_shambler */
    0.4f,   /* monster_zombie */
    0.5f,   /* monster_dog */
    0.8f,   /* monster_wizard */
    1.0f,   /* monster_boss */
    0.5f    /* unknown/default monster */
};

/* ============================================================================
 * State
 * ============================================================================ */

typedef struct {
    bool active;
    int enemy_type;
    int qubit_offset;       /* Starting qubit in shared state */
    float base_aggression;
    int decision_count;     /* Track number of decisions for behavioral drift */
    ai_action_t last_action;
} enemy_quantum_info_t;

static quantum_state_t* ai_state = NULL;
static quantum_state_t* ai_decision_state = NULL;
static quantum_entropy_ctx_t* ai_entropy = NULL;
static entropy_ctx_t* hw_entropy = NULL;
static enemy_quantum_info_t enemies[MAX_ENEMIES];
static int active_enemy_count = 0;
static uint64_t ai_entropy_offset = 0;
static qge_quantum_runtime_t* ai_runtime_override = NULL;
static bool ai_initialized = false;

/**
 * @brief Callback wrapper for hardware entropy
 *
 * Adapts hardware_entropy API to quantum_entropy callback signature.
 */
static int ai_entropy_callback(void *user_data, uint8_t *buffer, size_t size) {
    entropy_ctx_t *ctx = (entropy_ctx_t *)user_data;
    return entropy_get_bytes(ctx, buffer, size);
}

/* ============================================================================
 * Internal Functions
 * ============================================================================ */

/**
 * @brief Initialize the AI quantum system
 */
static void ensure_ai_initialized(void) {
    if (ai_initialized) return;

    /* Allocate shared bookkeeping/batch state for three simultaneous enemies. */
    ai_state = malloc(sizeof(quantum_state_t));
    if (!ai_state) {
        fprintf(stderr, "QGE AI: Failed to allocate state\n");
        return;
    }

    /* Use 24 qubits (3 enemies × 8 qubits each for active decisions) */
    qs_error_t err = quantum_state_init(ai_state, 24);
    if (err != QS_SUCCESS) {
        fprintf(stderr, "QGE AI: Failed to init quantum state\n");
        free(ai_state);
        ai_state = NULL;
        return;
    }

    ai_decision_state = malloc(sizeof(quantum_state_t));
    if (!ai_decision_state) {
        fprintf(stderr, "QGE AI: Failed to allocate decision state\n");
        quantum_state_free(ai_state);
        free(ai_state);
        ai_state = NULL;
        return;
    }

    err = quantum_state_init(ai_decision_state, ACTION_QUBITS);
    if (err != QS_SUCCESS) {
        fprintf(stderr, "QGE AI: Failed to init decision state\n");
        free(ai_decision_state);
        ai_decision_state = NULL;
        quantum_state_free(ai_state);
        free(ai_state);
        ai_state = NULL;
        return;
    }

    /* Initialize hardware entropy context */
    hw_entropy = malloc(sizeof(entropy_ctx_t));
    if (!hw_entropy) {
        fprintf(stderr, "QGE AI: Failed to allocate hardware entropy context\n");
        quantum_state_free(ai_decision_state);
        free(ai_decision_state);
        ai_decision_state = NULL;
        quantum_state_free(ai_state);
        free(ai_state);
        ai_state = NULL;
        return;
    }

    if (entropy_init(hw_entropy) != ENTROPY_SUCCESS) {
        fprintf(stderr, "QGE AI: Failed to init hardware entropy\n");
        quantum_state_free(ai_decision_state);
        free(ai_decision_state);
        quantum_state_free(ai_state);
        free(ai_state);
        free(hw_entropy);
        ai_decision_state = NULL;
        ai_state = NULL;
        hw_entropy = NULL;
        return;
    }

    /* Initialize quantum entropy context with hardware entropy callback */
    ai_entropy = malloc(sizeof(quantum_entropy_ctx_t));
    if (!ai_entropy) {
        fprintf(stderr, "QGE AI: Failed to allocate entropy context\n");
        entropy_free(hw_entropy);
        free(hw_entropy);
        quantum_state_free(ai_decision_state);
        free(ai_decision_state);
        quantum_state_free(ai_state);
        free(ai_state);
        ai_decision_state = NULL;
        ai_state = NULL;
        hw_entropy = NULL;
        return;
    }

    quantum_entropy_init(ai_entropy, ai_entropy_callback, hw_entropy);

    memset(enemies, 0, sizeof(enemies));
    ai_initialized = true;
}

static uint64_t hash_step(uint64_t hash, uint8_t byte) {
    hash ^= byte;
    hash *= 1099511628211ULL;
    return hash;
}

static uint64_t hash_u32(uint64_t hash, uint32_t value) {
    for (int i = 0; i < 4; i++) {
        hash = hash_step(hash, (uint8_t)((value >> (i * 8)) & 0xffu));
    }
    return hash;
}

static uint64_t hash_i32(uint64_t hash, int32_t value) {
    return hash_u32(hash, (uint32_t)value);
}

static uint64_t hash_float(uint64_t hash, float value) {
    uint32_t bits;
    memcpy(&bits, &value, sizeof(bits));
    return hash_u32(hash, bits);
}

uint64_t qge_ai_decision_input_hash(const qge_ai_decision_input_t* input) {
    uint64_t hash = 1469598103934665603ULL;

    if (!input) {
        return 0;
    }

    hash = hash_u32(hash, input->version);
    hash = hash_i32(hash, input->frame);
    hash = hash_i32(hash, input->server_time_msec);
    hash = hash_i32(hash, input->enemy_id);
    hash = hash_i32(hash, input->enemy_type);
    hash = hash_float(hash, input->health);
    hash = hash_u32(hash, input->flags);
    hash = hash_i32(hash, input->target_entnum);
    hash = hash_float(hash, input->aggression);
    hash = hash_float(hash, input->player_distance);
    hash = hash_u32(hash, input->player_visible ? 1u : 0u);
    hash = hash_u32(hash, input->legal_action_mask);
    hash = hash_u32(hash, (uint32_t)input->authority);

    return hash;
}

static int normalize_enemy_type(int enemy_type) {
    if (enemy_type >= 0 && enemy_type < QGE_AI_ENEMY_TYPE_COUNT) {
        return enemy_type;
    }
    return QGE_AI_ENEMY_DEFAULT;
}

static uint32_t normalize_legal_mask(uint32_t legal_action_mask) {
    return legal_action_mask ? legal_action_mask : QGE_AI_ACTION_LIVE_MASK;
}

static ai_action_t first_legal_action(uint32_t legal_action_mask) {
    legal_action_mask = normalize_legal_mask(legal_action_mask);
    if (legal_action_mask & QGE_AI_ACTION_IDLE_MASK) {
        return AI_IDLE;
    }
    for (int action = AI_IDLE; action <= AI_DEAD; action++) {
        if (legal_action_mask & QGE_AI_ACTION_MASK(action)) {
            return (ai_action_t)action;
        }
    }
    return AI_IDLE;
}

static ai_action_t clamp_legal_action(ai_action_t action,
                                      uint32_t legal_action_mask,
                                      uint32_t* flags) {
    legal_action_mask = normalize_legal_mask(legal_action_mask);
    if (action >= AI_IDLE && action <= AI_DEAD &&
        (legal_action_mask & QGE_AI_ACTION_MASK(action))) {
        return action;
    }
    if (flags) {
        *flags |= QGE_AI_DECISION_FLAG_CLAMPED;
    }
    return first_legal_action(legal_action_mask);
}

/**
 * @brief Map action index to ai_action_t
 */
static ai_action_t index_to_action(int index, float aggression, bool player_visible) {
    /* Actions are weighted by game situation:
     * - If player not visible: prefer IDLE, PATROL
     * - If player visible but far: prefer CHASE
     * - If player visible and close: prefer ATTACK (high aggression) or FLEE (low)
     */

    /* Map 3-bit value (0-7) to action */
    switch (index & 0x7) {
        case 0: return AI_IDLE;
        case 1: return AI_PATROL;
        case 2: return AI_CHASE;
        case 3: return AI_ATTACK;
        case 4: return player_visible ? AI_CHASE : AI_PATROL;
        case 5: return aggression > 0.5f ? AI_ATTACK : AI_FLEE;
        case 6: return AI_PAIN;  /* Rare, used for flinch states */
        case 7: return aggression > 0.7f ? AI_ATTACK : AI_IDLE;
        default: return AI_IDLE;
    }
}

static ai_action_t basis_to_action(uint64_t measurement,
                                   float aggression,
                                   bool player_visible) {
    ai_action_t action = index_to_action((int)measurement, aggression,
                                         player_visible);

    if (!player_visible && action == AI_ATTACK) {
        /* Can't attack what you can't see - switch to chase or patrol */
        action = (measurement & 0x4) ? AI_CHASE : AI_PATROL;
    }

    return action;
}

static void collect_action_probabilities(const quantum_state_t* state,
                                         int qubit_offset,
                                         double probabilities[1 << ACTION_QUBITS],
                                         double* total_probability,
                                         double* max_probability) {
    double total = 0.0;
    double max_prob = 0.0;

    memset(probabilities, 0, sizeof(double) * (1 << ACTION_QUBITS));

    if (!state || !state->amplitudes || state->state_dim == 0 ||
        state->state_dim > 4096) {
        if (total_probability) *total_probability = 0.0;
        if (max_probability) *max_probability = 0.0;
        return;
    }

    for (size_t basis = 0; basis < state->state_dim; basis++) {
        uint64_t action_basis =
            ((uint64_t)basis >> qubit_offset) & ((1ULL << ACTION_QUBITS) - 1ULL);
        complex_t amp = state->amplitudes[basis];
        double prob = creal(amp) * creal(amp) + cimag(amp) * cimag(amp);
        probabilities[action_basis] += prob;
        total += prob;
    }

    for (int i = 0; i < (1 << ACTION_QUBITS); i++) {
        if (probabilities[i] > max_prob) {
            max_prob = probabilities[i];
        }
    }

    if (total_probability) *total_probability = total;
    if (max_probability) *max_probability = max_prob;
}

static double action_probability_from_basis(const double probabilities[1 << ACTION_QUBITS],
                                            float aggression,
                                            bool player_visible,
                                            uint32_t legal_action_mask,
                                            ai_action_t action) {
    double probability = 0.0;

    for (int basis = 0; basis < (1 << ACTION_QUBITS); basis++) {
        uint32_t flags = 0;
        ai_action_t mapped = basis_to_action((uint64_t)basis, aggression,
                                             player_visible);
        mapped = clamp_legal_action(mapped, legal_action_mask, &flags);
        (void)flags;
        if (mapped == action) {
            probability += probabilities[basis];
        }
    }

    return probability;
}

void qge_ai_set_runtime(qge_quantum_runtime_t* runtime) {
    ai_runtime_override = runtime;
}

static qge_quantum_runtime_t* qge_ai_get_runtime(void) {
    qge_context_t* ctx;

    if (ai_runtime_override) {
        return ai_runtime_override;
    }
    ctx = qge_get_context();
    return ctx ? qge_get_quantum_runtime(ctx) : NULL;
}

static void fill_ai_decision_event(const qge_ai_decision_input_t* input,
                                   const qge_ai_decision_output_t* output,
                                   qge_ai_decision_event_t* event) {
    if (!input || !output || !event) {
        return;
    }
    memset(event, 0, sizeof(*event));
    event->frame = input->frame;
    event->server_time_msec = input->server_time_msec;
    event->enemy_id = input->enemy_id;
    event->enemy_type = input->enemy_type;
    event->target_entnum = input->target_entnum;
    event->input_flags = input->flags;
    event->output_flags = output->flags;
    event->legal_action_mask = output->legal_action_mask;
    event->input_hash = output->input_hash;
    event->raw_basis = output->raw_basis;
    event->action_basis = output->action_basis;
    event->entropy_offset = output->entropy_offset;
    event->mapped_action = (int32_t)output->mapped_action;
    event->action = (int32_t)output->action;
    event->selected_probability = output->selected_probability;
    event->action_probability = output->action_probability;
    event->max_probability = output->max_probability;
    event->total_probability = output->total_probability;
    event->confidence = output->confidence;
}

static void apply_replay_ai_decision(qge_ai_decision_output_t* output,
                                     const qge_ai_decision_event_t* event) {
    if (!output || !event) {
        return;
    }
    output->flags = event->output_flags;
    output->legal_action_mask = event->legal_action_mask;
    output->input_hash = event->input_hash;
    output->raw_basis = event->raw_basis;
    output->action_basis = event->action_basis;
    output->entropy_offset = event->entropy_offset;
    output->mapped_action = (ai_action_t)event->mapped_action;
    output->action = (ai_action_t)event->action;
    output->selected_probability = event->selected_probability;
    output->action_probability = event->action_probability;
    output->max_probability = event->max_probability;
    output->total_probability = event->total_probability;
    output->confidence = event->confidence;
}

static bool replay_ai_decision_if_available(const qge_ai_decision_input_t* input,
                                            qge_ai_decision_output_t* output) {
    qge_quantum_runtime_t* rt;
    qge_ai_decision_event_t request;
    qge_ai_decision_event_t replay;
    int result;

    rt = qge_ai_get_runtime();
    if (!rt || !input || !output) {
        return false;
    }
    fill_ai_decision_event(input, output, &request);
    memset(&replay, 0, sizeof(replay));
    result = qge_quantum_replay_ai_decision(rt, &request, &replay);
    if (result != 1) {
        return false;
    }
    apply_replay_ai_decision(output, &replay);
    return true;
}

static void record_ai_decision(const qge_ai_decision_input_t* input,
                               const qge_ai_decision_output_t* output) {
    qge_quantum_runtime_t* rt;
    qge_ai_decision_event_t event;

    if (!input || !output) {
        return;
    }
    rt = qge_ai_get_runtime();
    if (!rt) {
        return;
    }
    fill_ai_decision_event(input, output, &event);
    qge_quantum_record_ai_decision(rt, &event);
}

/**
 * @brief Apply situation-dependent phase rotations to bias decision
 */
static void apply_situation_bias(quantum_state_t* state,
                                  int qubit_offset,
                                  float aggression,
                                  float distance, bool player_visible) {
    /* Bias the quantum state based on game situation */

    /* Distance factor: closer = more likely to attack/flee */
    float distance_factor = 1.0f - fminf(1.0f, distance / 1000.0f);

    /* Visibility factor */
    float vis_factor = player_visible ? 1.0f : 0.3f;

    /* Apply RY rotations to bias action selection */
    /* Qubit 0: bias toward action vs idle */
    double theta0 = (aggression * vis_factor * distance_factor) * M_PI / 4.0;
    gate_ry(state, qubit_offset + 0, theta0);

    /* Qubit 1: bias toward aggressive actions */
    double theta1 = aggression * M_PI / 6.0;
    gate_ry(state, qubit_offset + 1, theta1);

    /* Qubit 2: randomization/variety */
    if (distance_factor > 0.5f) {
        gate_hadamard(state, qubit_offset + 2);
    }
}

/**
 * @brief Find slot for enemy, allocating if needed
 */
static int find_enemy_slot(int enemy_id) {
    int slot = enemy_id % MAX_ENEMIES;
    if (slot < 0) slot += MAX_ENEMIES;
    return enemies[slot].active ? slot : -1;
}

/* ============================================================================
 * Public API
 * ============================================================================ */

void qge_ai_init_enemy(int enemy_id, int enemy_type) {
    ensure_ai_initialized();
    if (!ai_state) return;

    enemy_type = normalize_enemy_type(enemy_type);

    int slot = find_enemy_slot(enemy_id);
    if (slot < 0) {
        slot = enemy_id % MAX_ENEMIES;
        if (slot < 0) slot += MAX_ENEMIES;
    }
    bool was_active = enemies[slot].active;

    enemies[slot].active = true;
    enemies[slot].enemy_type = enemy_type;
    enemies[slot].qubit_offset = (slot % 3) * QUBITS_PER_ENEMY;  /* 3 simultaneous */
    enemies[slot].base_aggression = BASE_AGGRESSION[enemy_type];
    enemies[slot].decision_count = 0;
    enemies[slot].last_action = AI_IDLE;

    if (!was_active) active_enemy_count++;

    /* Initialize this enemy's qubits to superposition */
    for (int q = 0; q < ACTION_QUBITS; q++) {
        gate_hadamard(ai_state, enemies[slot].qubit_offset + q);
    }
}

void qge_ai_destroy_enemy(int enemy_id) {
    if (!ai_initialized) return;

    int slot = enemy_id % MAX_ENEMIES;
    if (enemies[slot].active) {
        enemies[slot].active = false;
        active_enemy_count--;
    }
}

ai_action_t qge_ai_decide_traced(const qge_ai_decision_input_t* input,
                                 qge_ai_decision_trace_t* trace) {
    qge_ai_decision_input_t in;
    qge_ai_decision_output_t out;
    double probabilities[1 << ACTION_QUBITS];
    double total_probability = 0.0;
    double max_probability = 0.0;
    enemy_quantum_info_t* info = NULL;
    quantum_state_t* decision_state = NULL;
    int offset = 0;
    int slot;

    if (trace) {
        memset(trace, 0, sizeof(*trace));
    }

    memset(&out, 0, sizeof(out));
    memset(probabilities, 0, sizeof(probabilities));
    out.version = QGE_AI_TRACE_VERSION;
    out.action = AI_IDLE;
    out.mapped_action = AI_IDLE;

    if (!input) {
        if (trace) {
            trace->output = out;
        }
        return AI_IDLE;
    }

    in = *input;
    in.version = QGE_AI_TRACE_VERSION;
    in.legal_action_mask = normalize_legal_mask(in.legal_action_mask);
    in.enemy_type = normalize_enemy_type(in.enemy_type);

    out.legal_action_mask = in.legal_action_mask;
    out.input_hash = qge_ai_decision_input_hash(&in);
    if (in.authority >= QGE_AI_AUTHORITY_EXPLICIT) {
        out.flags |= QGE_AI_DECISION_FLAG_AUTHORITY;
    } else if (in.authority == QGE_AI_AUTHORITY_ADVISORY) {
        out.flags |= QGE_AI_DECISION_FLAG_ADVISORY;
    }
    if (in.player_visible) {
        out.flags |= QGE_AI_DECISION_FLAG_PLAYER_VISIBLE;
    }
    out.entropy_offset = ai_entropy_offset++;

    ensure_ai_initialized();
    slot = in.enemy_id % MAX_ENEMIES;
    if (slot < 0) slot += MAX_ENEMIES;
    if (ai_state) {
        /* Auto-initialize if not done */
        if (!enemies[slot].active) {
            qge_ai_init_enemy(in.enemy_id, in.enemy_type);
        }
        info = &enemies[slot];
    }

    if (replay_ai_decision_if_available(&in, &out)) {
        if (info) {
            info->last_action = out.action;
            info->decision_count++;
        }
        if (trace) {
            trace->input = in;
            trace->output = out;
        }
        record_ai_decision(&in, &out);
        return out.action;
    }

    if (!ai_state) {
        out.action = clamp_legal_action(AI_IDLE, in.legal_action_mask,
                                        &out.flags);
        record_ai_decision(&in, &out);
        if (trace) {
            trace->input = in;
            trace->output = out;
        }
        return out.action;
    }

    decision_state = ai_decision_state ? ai_decision_state : ai_state;
    offset = ai_decision_state ? 0 : info->qubit_offset;

    /* Per-think decisions only need the 3 action qubits. Keep the wider
     * 24-qubit state for enemy registration/entanglement bookkeeping. */
    quantum_state_reset(decision_state);

    /* Create superposition in action qubits for this enemy */
    for (int q = 0; q < ACTION_QUBITS; q++) {
        gate_hadamard(decision_state, offset + q);
    }

    /* Combine base aggression with parameter */
    float effective_aggression = (info->base_aggression + in.aggression) / 2.0f;

    /* Apply situation-dependent bias using quantum gates */
    apply_situation_bias(decision_state, offset, effective_aggression,
                         in.player_distance, in.player_visible);

    /* Apply behavioral memory: past actions influence current */
    if (info->decision_count > 0) {
        /* If last action was aggressive, slightly bias toward continuing */
        if (info->last_action == AI_ATTACK || info->last_action == AI_CHASE) {
            gate_rz(decision_state, offset + 1, M_PI / 8.0);
        }
    }

    collect_action_probabilities(decision_state, offset, probabilities,
                                 &total_probability, &max_probability);

    /* Measure all qubits and extract just the action bits for this enemy */
    uint64_t full_measurement = quantum_measure_all_fast(decision_state, ai_entropy);

    /* Extract the action bits at the enemy's qubit offset */
    uint64_t action_mask = (1ULL << ACTION_QUBITS) - 1;  /* 0x7 for 3 bits */
    uint64_t measurement = (full_measurement >> offset) & action_mask;

    /* Map measurement to action, considering game state and legal mask. */
    ai_action_t mapped_action = basis_to_action(measurement, effective_aggression,
                                                in.player_visible);
    ai_action_t action = clamp_legal_action(mapped_action, in.legal_action_mask,
                                            &out.flags);

    out.raw_basis = full_measurement;
    out.action_basis = measurement;
    out.mapped_action = mapped_action;
    out.action = action;
    out.selected_probability = probabilities[measurement];
    out.action_probability =
        action_probability_from_basis(probabilities, effective_aggression,
                                      in.player_visible, in.legal_action_mask,
                                      action);
    out.max_probability = max_probability;
    out.total_probability = total_probability;
    out.confidence = max_probability > 0.0 ?
        out.selected_probability / max_probability : 0.0;
    if (out.confidence > 1.0) {
        out.confidence = 1.0;
    }

    /* Update behavioral state */
    info->last_action = action;
    info->decision_count++;

    if (trace) {
        trace->input = in;
        trace->output = out;
    }
    record_ai_decision(&in, &out);

    return action;
}

ai_action_t qge_ai_decide(int enemy_id,
                          float aggression,
                          float player_distance,
                          bool player_visible) {
    qge_ai_decision_input_t input;

    memset(&input, 0, sizeof(input));
    input.version = QGE_AI_TRACE_VERSION;
    input.enemy_id = enemy_id;
    input.health = aggression * 100.0f;
    input.aggression = aggression;
    input.player_distance = player_distance;
    input.player_visible = player_visible;
    input.legal_action_mask = QGE_AI_ACTION_LIVE_MASK;
    input.authority = QGE_AI_AUTHORITY_ADVISORY;

    return qge_ai_decide_traced(&input, NULL);
}

void qge_ai_entangle(int enemy_a, int enemy_b) {
    ensure_ai_initialized();
    if (!ai_state) return;

    int slot_a = enemy_a % MAX_ENEMIES;
    int slot_b = enemy_b % MAX_ENEMIES;

    if (!enemies[slot_a].active || !enemies[slot_b].active) {
        return;  /* Both must be active */
    }

    /* Get qubit offsets */
    int offset_a = enemies[slot_a].qubit_offset;
    int offset_b = enemies[slot_b].qubit_offset;

    /* Can only entangle enemies using different qubit regions */
    if (offset_a == offset_b) {
        return;
    }

    /* Apply CNOT to create entanglement:
     * When enemy A decides to attack, enemy B is biased toward same */
    gate_cnot(ai_state, offset_a + 0, offset_b + 0);

    /* Apply CZ for phase correlation (more subtle coordination) */
    gate_cz(ai_state, offset_a + 1, offset_b + 1);
}

/* ============================================================================
 * Batch Operations (for efficiency)
 * ============================================================================ */

/**
 * @brief Make decisions for multiple enemies at once
 *
 * More efficient than individual calls when many enemies need decisions.
 */
void qge_ai_decide_batch(int* enemy_ids, int count,
                          float* aggressions,
                          float* distances,
                          bool* visibilities,
                          ai_action_t* results) {
    ensure_ai_initialized();
    if (!ai_state || count <= 0) return;

    /* Process up to 3 enemies simultaneously (our qubit budget) */
    for (int batch_start = 0; batch_start < count; batch_start += 3) {
        int batch_size = (count - batch_start < 3) ? (count - batch_start) : 3;

        /* Reset state before each batch */
        quantum_state_reset(ai_state);

        /* Prepare all qubits in batch */
        for (int i = 0; i < batch_size; i++) {
            int idx = batch_start + i;
            int slot = enemy_ids[idx] % MAX_ENEMIES;

            if (!enemies[slot].active) {
                qge_ai_init_enemy(enemy_ids[idx], 0);
            }

            int offset = enemies[slot].qubit_offset;

            /* Apply Hadamard to action qubits */
            for (int q = 0; q < ACTION_QUBITS; q++) {
                gate_hadamard(ai_state, offset + q);
            }

            /* Apply situation bias */
            apply_situation_bias(ai_state, offset, aggressions[idx],
                                 distances[idx], visibilities[idx]);
        }

        /* Measure all qubits once and extract results for each enemy */
        uint64_t full_measurement = quantum_measure_all_fast(ai_state, NULL);
        uint64_t action_mask = (1ULL << ACTION_QUBITS) - 1;

        for (int i = 0; i < batch_size; i++) {
            int idx = batch_start + i;
            int slot = enemy_ids[idx] % MAX_ENEMIES;
            int offset = enemies[slot].qubit_offset;

            uint64_t measurement = (full_measurement >> offset) & action_mask;
            results[idx] = index_to_action((int)measurement, aggressions[idx], visibilities[idx]);

            enemies[slot].last_action = results[idx];
            enemies[slot].decision_count++;
        }
    }
}

/* ============================================================================
 * Debug/Statistics
 * ============================================================================ */

/**
 * @brief Get decision statistics for an enemy
 */
void qge_ai_get_stats(int enemy_id, int* decision_count, ai_action_t* last_action) {
    int slot = enemy_id % MAX_ENEMIES;

    if (enemies[slot].active) {
        if (decision_count) *decision_count = enemies[slot].decision_count;
        if (last_action) *last_action = enemies[slot].last_action;
    } else {
        if (decision_count) *decision_count = 0;
        if (last_action) *last_action = AI_IDLE;
    }
}

/**
 * @brief Shutdown AI system
 */
void qge_ai_shutdown(void) {
    if (ai_entropy) {
        free(ai_entropy);
        ai_entropy = NULL;
    }
    if (hw_entropy) {
        entropy_free(hw_entropy);
        free(hw_entropy);
        hw_entropy = NULL;
    }
    if (ai_decision_state) {
        quantum_state_free(ai_decision_state);
        free(ai_decision_state);
        ai_decision_state = NULL;
    }
    if (ai_state) {
        quantum_state_free(ai_state);
        free(ai_state);
        ai_state = NULL;
    }
    memset(enemies, 0, sizeof(enemies));
    active_enemy_count = 0;
    ai_entropy_offset = 0;
    ai_runtime_override = NULL;
    ai_initialized = false;
}
