/**
 * @file qge_ai.h
 * @brief Typed advisory protocol for quantum AI decisions.
 */

#ifndef QGE_AI_H
#define QGE_AI_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define QGE_AI_TRACE_VERSION 1u
#define QGE_AI_ACTION_MASK(action) (1u << (unsigned int)(action))

typedef enum {
    AI_IDLE,
    AI_PATROL,
    AI_CHASE,
    AI_ATTACK,
    AI_FLEE,
    AI_PAIN,
    AI_DEAD
} ai_action_t;

enum {
    QGE_AI_ACTION_IDLE_MASK = QGE_AI_ACTION_MASK(AI_IDLE),
    QGE_AI_ACTION_PATROL_MASK = QGE_AI_ACTION_MASK(AI_PATROL),
    QGE_AI_ACTION_CHASE_MASK = QGE_AI_ACTION_MASK(AI_CHASE),
    QGE_AI_ACTION_ATTACK_MASK = QGE_AI_ACTION_MASK(AI_ATTACK),
    QGE_AI_ACTION_FLEE_MASK = QGE_AI_ACTION_MASK(AI_FLEE),
    QGE_AI_ACTION_PAIN_MASK = QGE_AI_ACTION_MASK(AI_PAIN),
    QGE_AI_ACTION_DEAD_MASK = QGE_AI_ACTION_MASK(AI_DEAD),
    QGE_AI_ACTION_ALL_MASK =
        QGE_AI_ACTION_IDLE_MASK |
        QGE_AI_ACTION_PATROL_MASK |
        QGE_AI_ACTION_CHASE_MASK |
        QGE_AI_ACTION_ATTACK_MASK |
        QGE_AI_ACTION_FLEE_MASK |
        QGE_AI_ACTION_PAIN_MASK |
        QGE_AI_ACTION_DEAD_MASK,
    QGE_AI_ACTION_LIVE_MASK =
        QGE_AI_ACTION_IDLE_MASK |
        QGE_AI_ACTION_PATROL_MASK |
        QGE_AI_ACTION_CHASE_MASK |
        QGE_AI_ACTION_ATTACK_MASK |
        QGE_AI_ACTION_FLEE_MASK |
        QGE_AI_ACTION_PAIN_MASK
};

typedef enum {
    QGE_AI_AUTHORITY_DISABLED = 0,
    QGE_AI_AUTHORITY_ADVISORY = 1,
    QGE_AI_AUTHORITY_EXPLICIT = 2
} qge_ai_authority_t;

enum {
    QGE_AI_DECISION_FLAG_ADVISORY = 1u << 0,
    QGE_AI_DECISION_FLAG_AUTHORITY = 1u << 1,
    QGE_AI_DECISION_FLAG_CLAMPED = 1u << 2,
    QGE_AI_DECISION_FLAG_PLAYER_VISIBLE = 1u << 3
};

typedef struct {
    uint32_t version;
    int32_t frame;
    int32_t server_time_msec;
    int32_t enemy_id;
    int32_t enemy_type;
    float health;
    uint32_t flags;
    int32_t target_entnum;
    float aggression;
    float player_distance;
    bool player_visible;
    uint32_t legal_action_mask;
    qge_ai_authority_t authority;
} qge_ai_decision_input_t;

typedef struct {
    uint32_t version;
    uint32_t flags;
    uint32_t legal_action_mask;
    uint64_t input_hash;
    uint64_t raw_basis;
    uint64_t action_basis;
    uint64_t entropy_offset;
    ai_action_t mapped_action;
    ai_action_t action;
    double selected_probability;
    double action_probability;
    double max_probability;
    double total_probability;
    double confidence;
} qge_ai_decision_output_t;

typedef struct {
    qge_ai_decision_input_t input;
    qge_ai_decision_output_t output;
} qge_ai_decision_trace_t;

/**
 * Hash the typed AI decision input. The hash is stable across platforms for
 * the byte-level field encodings used by this protocol.
 */
uint64_t qge_ai_decision_input_hash(const qge_ai_decision_input_t* input);

/**
 * Make a quantum AI decision and return the typed trace contract.
 *
 * The returned action is advisory unless the caller's authority mode is
 * QGE_AI_AUTHORITY_EXPLICIT and the caller chooses to apply it.
 */
ai_action_t qge_ai_decide_traced(const qge_ai_decision_input_t* input,
                                 qge_ai_decision_trace_t* trace);

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

void qge_ai_decide_batch(int* enemy_ids, int count,
                         float* aggressions,
                         float* distances,
                         bool* visibilities,
                         ai_action_t* results);

void qge_ai_get_stats(int enemy_id, int* decision_count,
                      ai_action_t* last_action);
void qge_ai_shutdown(void);

#ifdef __cplusplus
}
#endif

#endif /* QGE_AI_H */
