/**
 * @file qge_ai.c
 * @brief Quantum AI for Enemy Decision-Making
 *
 * Uses genuine quantum superposition and measurement for enemy AI decisions.
 * Each enemy maintains a quantum state representing their behavioral tendencies.
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
static const float BASE_AGGRESSION[] = {
    0.3f,   /* Type 0: Grunt - low aggression */
    0.5f,   /* Type 1: Knight - medium */
    0.7f,   /* Type 2: Ogre - high */
    0.9f,   /* Type 3: Demon - very high */
    0.6f,   /* Type 4: Shambler - medium-high */
    0.4f,   /* Type 5: Zombie - low-medium */
    0.8f,   /* Type 6: Fiend - high */
    0.5f    /* Type 7: Default */
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
static quantum_entropy_ctx_t* ai_entropy = NULL;
static entropy_ctx_t* hw_entropy = NULL;
static enemy_quantum_info_t enemies[MAX_ENEMIES];
static int active_enemy_count = 0;
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

    /* Allocate quantum state for up to 8 simultaneous enemies (64 qubits) */
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

    /* Initialize hardware entropy context */
    hw_entropy = malloc(sizeof(entropy_ctx_t));
    if (!hw_entropy) {
        fprintf(stderr, "QGE AI: Failed to allocate hardware entropy context\n");
        quantum_state_free(ai_state);
        free(ai_state);
        ai_state = NULL;
        return;
    }

    if (entropy_init(hw_entropy) != ENTROPY_SUCCESS) {
        fprintf(stderr, "QGE AI: Failed to init hardware entropy\n");
        quantum_state_free(ai_state);
        free(ai_state);
        free(hw_entropy);
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
        quantum_state_free(ai_state);
        free(ai_state);
        ai_state = NULL;
        hw_entropy = NULL;
        return;
    }

    quantum_entropy_init(ai_entropy, ai_entropy_callback, hw_entropy);

    memset(enemies, 0, sizeof(enemies));
    ai_initialized = true;
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

/**
 * @brief Apply situation-dependent phase rotations to bias decision
 */
static void apply_situation_bias(int qubit_offset, float aggression,
                                  float distance, bool player_visible) {
    /* Bias the quantum state based on game situation */

    /* Distance factor: closer = more likely to attack/flee */
    float distance_factor = 1.0f - fminf(1.0f, distance / 1000.0f);

    /* Visibility factor */
    float vis_factor = player_visible ? 1.0f : 0.3f;

    /* Apply RY rotations to bias action selection */
    /* Qubit 0: bias toward action vs idle */
    double theta0 = (aggression * vis_factor * distance_factor) * M_PI / 4.0;
    gate_ry(ai_state, qubit_offset + 0, theta0);

    /* Qubit 1: bias toward aggressive actions */
    double theta1 = aggression * M_PI / 6.0;
    gate_ry(ai_state, qubit_offset + 1, theta1);

    /* Qubit 2: randomization/variety */
    if (distance_factor > 0.5f) {
        gate_hadamard(ai_state, qubit_offset + 2);
    }
}

/**
 * @brief Find slot for enemy, allocating if needed
 */
static int find_enemy_slot(int enemy_id) {
    /* First check if enemy already has a slot */
    for (int i = 0; i < MAX_ENEMIES; i++) {
        if (enemies[i].active && i == enemy_id % MAX_ENEMIES) {
            return i;
        }
    }
    return -1;
}

/* ============================================================================
 * Public API
 * ============================================================================ */

void qge_ai_init_enemy(int enemy_id, int enemy_type) {
    ensure_ai_initialized();
    if (!ai_state) return;

    int slot = enemy_id % MAX_ENEMIES;

    enemies[slot].active = true;
    enemies[slot].enemy_type = enemy_type;
    enemies[slot].qubit_offset = (slot % 3) * QUBITS_PER_ENEMY;  /* 3 simultaneous */
    enemies[slot].base_aggression = BASE_AGGRESSION[enemy_type % 8];
    enemies[slot].decision_count = 0;
    enemies[slot].last_action = AI_IDLE;

    active_enemy_count++;

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

ai_action_t qge_ai_decide(int enemy_id,
                          float aggression,
                          float player_distance,
                          bool player_visible) {
    ensure_ai_initialized();
    if (!ai_state) return AI_IDLE;

    int slot = enemy_id % MAX_ENEMIES;

    /* Auto-initialize if not done */
    if (!enemies[slot].active) {
        qge_ai_init_enemy(enemy_id, 0);
    }

    enemy_quantum_info_t* info = &enemies[slot];
    int offset = info->qubit_offset;

    /* Reset the quantum state to |0⟩ before creating new superposition.
     * This is needed because quantum_measure_all_fast collapses the state. */
    quantum_state_reset(ai_state);

    /* Create superposition in action qubits for this enemy */
    for (int q = 0; q < ACTION_QUBITS; q++) {
        gate_hadamard(ai_state, offset + q);
    }

    /* Combine base aggression with parameter */
    float effective_aggression = (info->base_aggression + aggression) / 2.0f;

    /* Apply situation-dependent bias using quantum gates */
    apply_situation_bias(offset, effective_aggression, player_distance, player_visible);

    /* Apply behavioral memory: past actions influence current */
    if (info->decision_count > 0) {
        /* If last action was aggressive, slightly bias toward continuing */
        if (info->last_action == AI_ATTACK || info->last_action == AI_CHASE) {
            gate_rz(ai_state, offset + 1, M_PI / 8.0);
        }
    }

    /* Measure all qubits and extract just the action bits for this enemy */
    uint64_t full_measurement = quantum_measure_all_fast(ai_state, ai_entropy);

    /* Extract the action bits at the enemy's qubit offset */
    uint64_t action_mask = (1ULL << ACTION_QUBITS) - 1;  /* 0x7 for 3 bits */
    uint64_t measurement = (full_measurement >> offset) & action_mask;

    /* Map measurement to action, considering game state */
    ai_action_t action = index_to_action((int)measurement, effective_aggression, player_visible);

    /* Additional logic: override impossible actions */
    if (!player_visible && action == AI_ATTACK) {
        /* Can't attack what you can't see - switch to chase or patrol */
        action = (measurement & 0x4) ? AI_CHASE : AI_PATROL;
    }

    /* Update behavioral state */
    info->last_action = action;
    info->decision_count++;

    return action;
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
            apply_situation_bias(offset, aggressions[idx], distances[idx], visibilities[idx]);
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
    if (ai_state) {
        quantum_state_free(ai_state);
        free(ai_state);
        ai_state = NULL;
    }
    memset(enemies, 0, sizeof(enemies));
    active_enemy_count = 0;
    ai_initialized = false;
}
