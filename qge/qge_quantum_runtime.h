/**
 * @file qge_quantum_runtime.h
 * @brief Shared quantum runtime contracts for QGE subsystems.
 *
 * This header is the common vocabulary for gameplay-affecting quantum state:
 * domains, representations, measurement events, probes, fallbacks, entropy,
 * and entanglement edges. Subsystems should report through this layer instead
 * of inventing renderer/audio/physics-specific trace shapes.
 */

#ifndef QGE_QUANTUM_RUNTIME_H
#define QGE_QUANTUM_RUNTIME_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define QGE_TRACE_MESSAGE_MAX 96
#define QGE_PROBE_LABEL_MAX 32

typedef enum {
    QGE_DOMAIN_RENDER = 0,
    QGE_DOMAIN_VISIBILITY,
    QGE_DOMAIN_PROJECTILE,
    QGE_DOMAIN_PARTICLE,
    QGE_DOMAIN_AUDIO,
    QGE_DOMAIN_AI,
    QGE_DOMAIN_RNG,
    QGE_DOMAIN_MATERIAL,
    QGE_DOMAIN_PHYSICS,
    QGE_DOMAIN_UI,
    QGE_DOMAIN_MAX
} qge_quantum_domain_t;

typedef enum {
    QGE_REP_NONE = 0,
    QGE_REP_DENSE_STATE,
    QGE_REP_SPARSE_DWT,
    QGE_REP_MPS,
    QGE_REP_CA_MPS,
    QGE_REP_CLIFFORD_TABLEAU,
    QGE_REP_PAULI_FRAME,
    QGE_REP_CLASSICAL_ORACLE,
    QGE_REP_GROVER_SEARCH,
    QGE_REP_DCT_TRANSDUCER,
    QGE_REP_MATERIAL_PHASE_FIELD,
    QGE_REP_HYBRID,
    QGE_REP_MAX
} qge_quantum_representation_t;

typedef enum {
    QGE_MEASURE_NONE = 0,
    QGE_MEASURE_RENDER_SAMPLE,
    QGE_MEASURE_VIS_SURFACE_SET,
    QGE_MEASURE_PROJECTILE_IMPACT,
    QGE_MEASURE_PARTICLE_POSITION,
    QGE_MEASURE_AUDIO_BLOCK,
    QGE_MEASURE_AI_ACTION,
    QGE_MEASURE_RNG_BATCH,
    QGE_MEASURE_MATERIAL_PHASE,
    QGE_MEASURE_PHYSICS_COLLISION,
    QGE_MEASURE_ENTANGLEMENT_COLLAPSE,
    QGE_MEASURE_MAX
} qge_measurement_kind_t;

typedef enum {
    QGE_OBSERVE_NONE = 0,
    QGE_OBSERVE_PLAYER_VISIBLE,
    QGE_OBSERVE_COLLISION,
    QGE_OBSERVE_DAMAGE,
    QGE_OBSERVE_AUDIO_MIX,
    QGE_OBSERVE_AI_DECISION,
    QGE_OBSERVE_NETWORK_SERIALIZE,
    QGE_OBSERVE_SAVE_OR_DEMO,
    QGE_OBSERVE_DEBUG_MEASURE,
    QGE_OBSERVE_FRAME_BOUNDARY,
    QGE_OBSERVE_MAX
} qge_observation_boundary_t;

typedef enum {
    QGE_ENTROPY_SOURCE_QRNG = 0,
    QGE_ENTROPY_SOURCE_REPLAY,
    QGE_ENTROPY_SOURCE_DETERMINISTIC,
    QGE_ENTROPY_SOURCE_CLASSICAL_FALLBACK,
    QGE_ENTROPY_SOURCE_MAX
} qge_entropy_source_t;

typedef struct {
    qge_quantum_domain_t domain;
    qge_measurement_kind_t kind;
    qge_observation_boundary_t boundary;
    int32_t frame;
    int32_t server_time_msec;
    int32_t subject_id;
    uint32_t flags;
    uint64_t basis_index;
    double probability;
    double phase;
    uint64_t entropy_offset;
    uint64_t trace_id;
} qge_measurement_event_t;

typedef struct {
    int32_t frame;
    int32_t server_time_msec;
    qge_quantum_domain_t domain;
    qge_quantum_representation_t representation;
    int32_t subject_id;
    uint32_t flags;
    uint64_t state_hash;
    double entropy;
    double coherence;
    double max_probability;
    double total_probability;
    int32_t active_basis_count;
    int32_t qubit_count;
    uint64_t memory_bytes;
    char label[QGE_PROBE_LABEL_MAX];
} qge_state_probe_t;

typedef struct {
    int32_t frame;
    int32_t server_time_msec;
    qge_quantum_domain_t domain;
    qge_quantum_representation_t representation;
    int32_t subject_id;
    int32_t reason_code;
    double metric_value;
    char message[QGE_TRACE_MESSAGE_MAX];
} qge_fallback_event_t;

typedef struct {
    int32_t frame;
    int32_t server_time_msec;
    qge_quantum_domain_t domain;
    qge_quantum_representation_t representation;
    int32_t subject_a;
    int32_t subject_b;
    float strength;
    float coherence;
    int32_t created_frame;
    int32_t last_observed_frame;
    uint64_t edge_id;
} qge_entanglement_edge_t;

typedef struct {
    int32_t frame;
    int32_t server_time_msec;
    qge_quantum_domain_t domain;
    qge_entropy_source_t source;
    int32_t subject_id;
    uint32_t request_id;
    uint64_t value;
    uint64_t entropy_offset;
} qge_entropy_event_t;

typedef struct {
    uint64_t frames_started;
    uint64_t frames_ended;
    uint64_t entropy_events;
    uint64_t measurement_events;
    uint64_t probe_events;
    uint64_t fallback_events;
    uint64_t entanglement_edges;
    uint64_t trace_write_errors;
} qge_quantum_runtime_stats_t;

typedef struct qge_quantum_runtime_s qge_quantum_runtime_t;

typedef uint64_t (*qge_quantum_entropy_source_func_t)(void *user_data,
                                                       qge_quantum_domain_t domain,
                                                       int subject_id);

qge_quantum_runtime_t *qge_quantum_runtime_create(void);
void qge_quantum_runtime_free(qge_quantum_runtime_t *rt);

void qge_quantum_runtime_set_seed(qge_quantum_runtime_t *rt, uint64_t seed);
void qge_quantum_runtime_set_entropy_source(qge_quantum_runtime_t *rt,
                                            qge_entropy_source_t source,
                                            qge_quantum_entropy_source_func_t func,
                                            void *user_data);
qge_entropy_source_t qge_quantum_runtime_get_entropy_source(
    const qge_quantum_runtime_t *rt);
int qge_quantum_runtime_get_frame(const qge_quantum_runtime_t *rt);
int qge_quantum_runtime_get_server_time_msec(const qge_quantum_runtime_t *rt);
int qge_quantum_runtime_load_replay_entropy(qge_quantum_runtime_t *rt,
                                            const char *trace_path);
void qge_quantum_runtime_get_stats(const qge_quantum_runtime_t *rt,
                                   qge_quantum_runtime_stats_t *stats);

void qge_quantum_frame_begin(qge_quantum_runtime_t *rt,
                             int frame,
                             int server_time_msec);
void qge_quantum_frame_end(qge_quantum_runtime_t *rt);

uint64_t qge_quantum_entropy_u64(qge_quantum_runtime_t *rt,
                                 qge_quantum_domain_t domain,
                                 int subject_id);

void qge_quantum_record_measurement(qge_quantum_runtime_t *rt,
                                    const qge_measurement_event_t *event);
void qge_quantum_record_probe(qge_quantum_runtime_t *rt,
                              const qge_state_probe_t *probe);
void qge_quantum_record_fallback(qge_quantum_runtime_t *rt,
                                 const qge_fallback_event_t *event);
void qge_quantum_record_entanglement(qge_quantum_runtime_t *rt,
                                     const qge_entanglement_edge_t *edge);

int qge_quantum_trace_open(qge_quantum_runtime_t *rt, const char *path);
void qge_quantum_trace_close(qge_quantum_runtime_t *rt);

const char *qge_quantum_domain_name(qge_quantum_domain_t domain);
const char *qge_quantum_representation_name(qge_quantum_representation_t rep);
const char *qge_measurement_kind_name(qge_measurement_kind_t kind);

#ifdef __cplusplus
}
#endif

#endif /* QGE_QUANTUM_RUNTIME_H */
