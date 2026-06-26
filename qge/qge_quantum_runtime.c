/**
 * @file qge_quantum_runtime.c
 * @brief Shared runtime spine for QGE quantum events.
 */

#include "qge_quantum_runtime.h"
#include "qge_trace.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

struct qge_quantum_runtime_s {
    int frame;
    int server_time_msec;
    uint64_t run_id;
    uint64_t entropy_state;
    uint64_t entropy_offset;
    uint32_t request_id;
    qge_entropy_source_t entropy_source;
    qge_quantum_entropy_source_func_t entropy_func;
    void *entropy_user_data;
    qge_entropy_event_t *replay_events;
    size_t replay_count;
    size_t replay_capacity;
    size_t replay_index;
    qge_ai_decision_event_t *replay_ai_decisions;
    size_t replay_ai_decision_count;
    size_t replay_ai_decision_capacity;
    size_t replay_ai_decision_index;
    qge_measurement_event_t *replay_measurements;
    size_t replay_measurement_count;
    size_t replay_measurement_capacity;
    size_t replay_measurement_index;
    bool replay_strict;
    qge_trace_writer_t *trace;
    qge_quantum_runtime_stats_t stats;
};

enum {
    QGE_REPLAY_FALLBACK_METADATA_MISMATCH = 1,
    QGE_REPLAY_FALLBACK_EXHAUSTED = 2,
    QGE_REPLAY_FALLBACK_AI_DECISION_MISMATCH = 3,
    QGE_REPLAY_FALLBACK_AI_DECISION_EXHAUSTED = 4,
    QGE_REPLAY_FALLBACK_MEASUREMENT_MISMATCH = 5,
    QGE_REPLAY_FALLBACK_MEASUREMENT_EXHAUSTED = 6
};

static uint64_t splitmix64_next(uint64_t *state)
{
    uint64_t z;

    *state += 0x9e3779b97f4a7c15ULL;
    z = *state;
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}

static uint64_t domain_salt(qge_quantum_domain_t domain, int subject_id)
{
    uint64_t d = (uint64_t)(uint32_t)domain;
    uint64_t s = (uint64_t)(uint32_t)subject_id;
    return (d << 56) ^ (s * 0x100000001b3ULL);
}

static void note_trace_result(qge_quantum_runtime_t *rt, int result)
{
    if (rt && result != 0) {
        rt->stats.trace_write_errors++;
    }
}

static bool qge_semantic_text_present(const char *value)
{
    return value && value[0] != '\0';
}

static bool qge_domain_is_valid(qge_quantum_domain_t domain)
{
    return domain >= 0 && domain < QGE_DOMAIN_MAX;
}

static bool qge_representation_is_valid(qge_quantum_representation_t rep)
{
    return rep > QGE_REP_NONE && rep < QGE_REP_MAX;
}

static bool qge_measurement_kind_is_valid(qge_measurement_kind_t kind)
{
    return kind > QGE_MEASURE_NONE && kind < QGE_MEASURE_MAX;
}

static bool qge_observation_boundary_is_valid(
    qge_observation_boundary_t boundary)
{
    return boundary > QGE_OBSERVE_NONE && boundary < QGE_OBSERVE_MAX;
}

static bool qge_material_operator_kind_is_valid(
    qge_material_operator_kind_t kind)
{
    return kind > QGE_MATERIAL_OPERATOR_NONE &&
           kind < QGE_MATERIAL_OPERATOR_MAX;
}

static bool qge_weapon_operator_kind_is_valid(
    qge_weapon_operator_kind_t kind)
{
    return kind > QGE_WEAPON_OPERATOR_NONE &&
           kind < QGE_WEAPON_OPERATOR_MAX;
}

static bool qge_probability_is_valid(double probability)
{
    return isfinite(probability) &&
           probability >= 0.0 &&
           probability <= 1.0;
}

static bool qge_amplification_is_valid(double amplification)
{
    return isfinite(amplification) &&
           amplification >= 0.0 &&
           amplification <= 16.0;
}

static double qge_clamp01(double value)
{
    if (value < 0.0) {
        return 0.0;
    }
    if (value > 1.0) {
        return 1.0;
    }
    return value;
}

static const char *qge_material_operator_probe_label(
    qge_material_operator_kind_t kind)
{
    switch (kind) {
        case QGE_MATERIAL_OPERATOR_WATER_DECOHERENCE:
            return "material_water";
        case QGE_MATERIAL_OPERATOR_LAVA_PHASE:
            return "material_lava";
        case QGE_MATERIAL_OPERATOR_SLIPGATE_PHASE:
            return "material_slipgate";
        case QGE_MATERIAL_OPERATOR_QUAD_AMPLIFICATION:
            return "material_quad";
        case QGE_MATERIAL_OPERATOR_RING_PROTECTION:
            return "material_ring";
        case QGE_MATERIAL_OPERATOR_PENTAGRAM_PROTECTION:
            return "material_pentagram";
        case QGE_MATERIAL_OPERATOR_RUNE_PHASE:
            return "material_rune";
        default:
            return "material_unknown";
    }
}

static const char *qge_weapon_operator_probe_label(
    qge_weapon_operator_kind_t kind)
{
    switch (kind) {
        case QGE_WEAPON_OPERATOR_SHOTGUN_SPREAD_MEASUREMENT:
            return "weapon_shotgun";
        case QGE_WEAPON_OPERATOR_NAIL_PAULI_NOISE:
            return "weapon_nailgun";
        case QGE_WEAPON_OPERATOR_ROCKET_SPLASH_WAVEFRONT:
            return "weapon_rocket";
        case QGE_WEAPON_OPERATOR_GRENADE_FUSE_BRANCH:
            return "weapon_grenade";
        case QGE_WEAPON_OPERATOR_LIGHTNING_CONTINUOUS_MEASUREMENT:
            return "weapon_lightning";
        case QGE_WEAPON_OPERATOR_AXE_CONTACT_MEASUREMENT:
            return "weapon_axe";
        default:
            return "weapon_unknown";
    }
}

static qge_quantum_representation_t qge_weapon_operator_representation(
    qge_weapon_operator_kind_t kind)
{
    switch (kind) {
        case QGE_WEAPON_OPERATOR_SHOTGUN_SPREAD_MEASUREMENT:
        case QGE_WEAPON_OPERATOR_AXE_CONTACT_MEASUREMENT:
            return QGE_REP_DENSE_STATE;
        case QGE_WEAPON_OPERATOR_NAIL_PAULI_NOISE:
            return QGE_REP_PAULI_FRAME;
        case QGE_WEAPON_OPERATOR_ROCKET_SPLASH_WAVEFRONT:
            return QGE_REP_MPS;
        case QGE_WEAPON_OPERATOR_GRENADE_FUSE_BRANCH:
            return QGE_REP_CA_MPS;
        case QGE_WEAPON_OPERATOR_LIGHTNING_CONTINUOUS_MEASUREMENT:
            return QGE_REP_CLIFFORD_TABLEAU;
        default:
            return QGE_REP_HYBRID;
    }
}

static void clear_replay_entropy(qge_quantum_runtime_t *rt)
{
    if (!rt) {
        return;
    }
    free(rt->replay_events);
    rt->replay_events = NULL;
    rt->replay_count = 0;
    rt->replay_capacity = 0;
    rt->replay_index = 0;
    rt->stats.replay_events_loaded = 0;
    rt->stats.replay_events_consumed = 0;
    rt->stats.replay_mismatches = 0;
    rt->stats.replay_exhaustions = 0;
}

static void clear_replay_ai_decisions(qge_quantum_runtime_t *rt)
{
    if (!rt) {
        return;
    }
    free(rt->replay_ai_decisions);
    rt->replay_ai_decisions = NULL;
    rt->replay_ai_decision_count = 0;
    rt->replay_ai_decision_capacity = 0;
    rt->replay_ai_decision_index = 0;
    rt->stats.replay_ai_decisions_loaded = 0;
    rt->stats.replay_ai_decisions_consumed = 0;
    rt->stats.replay_ai_decision_mismatches = 0;
    rt->stats.replay_ai_decision_exhaustions = 0;
}

static void clear_replay_measurements(qge_quantum_runtime_t *rt)
{
    if (!rt) {
        return;
    }
    free(rt->replay_measurements);
    rt->replay_measurements = NULL;
    rt->replay_measurement_count = 0;
    rt->replay_measurement_capacity = 0;
    rt->replay_measurement_index = 0;
    rt->stats.replay_measurements_loaded = 0;
    rt->stats.replay_measurements_consumed = 0;
    rt->stats.replay_measurement_mismatches = 0;
    rt->stats.replay_measurement_exhaustions = 0;
}

static int append_replay_entropy(qge_quantum_runtime_t *rt,
                                 const qge_entropy_event_t *event)
{
    qge_entropy_event_t *events;
    size_t new_capacity;

    if (!rt || !event) {
        return -1;
    }
    if (rt->replay_count == rt->replay_capacity) {
        new_capacity = rt->replay_capacity ? rt->replay_capacity * 2 : 256;
        events = (qge_entropy_event_t *)realloc(rt->replay_events,
                                                new_capacity * sizeof(*events));
        if (!events) {
            return -1;
        }
        rt->replay_events = events;
        rt->replay_capacity = new_capacity;
    }
    rt->replay_events[rt->replay_count++] = *event;
    return 0;
}

static int append_replay_ai_decision(qge_quantum_runtime_t *rt,
                                     const qge_ai_decision_event_t *event)
{
    qge_ai_decision_event_t *events;
    size_t new_capacity;

    if (!rt || !event) {
        return -1;
    }
    if (rt->replay_ai_decision_count == rt->replay_ai_decision_capacity) {
        new_capacity = rt->replay_ai_decision_capacity ?
            rt->replay_ai_decision_capacity * 2 : 64;
        events = (qge_ai_decision_event_t *)realloc(
            rt->replay_ai_decisions, new_capacity * sizeof(*events));
        if (!events) {
            return -1;
        }
        rt->replay_ai_decisions = events;
        rt->replay_ai_decision_capacity = new_capacity;
    }
    rt->replay_ai_decisions[rt->replay_ai_decision_count++] = *event;
    return 0;
}

static int append_replay_measurement(qge_quantum_runtime_t *rt,
                                     const qge_measurement_event_t *event)
{
    qge_measurement_event_t *events;
    size_t new_capacity;

    if (!rt || !event) {
        return -1;
    }
    if (rt->replay_measurement_count == rt->replay_measurement_capacity) {
        new_capacity = rt->replay_measurement_capacity ?
            rt->replay_measurement_capacity * 2 : 128;
        events = (qge_measurement_event_t *)realloc(
            rt->replay_measurements, new_capacity * sizeof(*events));
        if (!events) {
            return -1;
        }
        rt->replay_measurements = events;
        rt->replay_measurement_capacity = new_capacity;
    }
    rt->replay_measurements[rt->replay_measurement_count++] = *event;
    return 0;
}

static bool replay_entropy_matches_request(const qge_quantum_runtime_t *rt,
                                           const qge_entropy_event_t *event,
                                           qge_quantum_domain_t domain,
                                           int subject_id)
{
    if (!rt || !event) {
        return false;
    }
    return event->frame == rt->frame &&
           event->server_time_msec == rt->server_time_msec &&
           event->domain == domain &&
           event->subject_id == subject_id &&
           event->request_id == rt->request_id &&
           event->entropy_offset == rt->entropy_offset;
}

static bool replay_ai_decision_matches_request(
    const qge_ai_decision_event_t *event,
    const qge_ai_decision_event_t *request)
{
    if (!event || !request) {
        return false;
    }
    return event->frame == request->frame &&
           event->server_time_msec == request->server_time_msec &&
           event->enemy_id == request->enemy_id &&
           event->enemy_type == request->enemy_type &&
           event->target_entnum == request->target_entnum &&
           event->input_flags == request->input_flags &&
           event->legal_action_mask == request->legal_action_mask &&
           event->input_hash == request->input_hash &&
           event->entropy_offset == request->entropy_offset;
}

static bool replay_double_matches(double event_value, double request_value)
{
    return fabs(event_value - request_value) <= 1e-12;
}

static bool replay_measurement_matches_request(
    const qge_measurement_event_t *event,
    const qge_measurement_event_t *request)
{
    if (!event || !request) {
        return false;
    }
    if (event->frame != request->frame ||
        event->server_time_msec != request->server_time_msec ||
        event->domain != request->domain ||
        event->kind != request->kind ||
        event->boundary != request->boundary ||
        event->subject_id != request->subject_id ||
        event->flags != request->flags ||
        event->basis_index != request->basis_index ||
        !replay_double_matches(event->probability, request->probability) ||
        !replay_double_matches(event->phase, request->phase)) {
        return false;
    }
    if (request->trace_id != 0 && event->trace_id != request->trace_id) {
        return false;
    }
    if (request->entropy_offset != 0 &&
        event->entropy_offset != request->entropy_offset) {
        return false;
    }
    return true;
}

static uint64_t deterministic_fallback_entropy(qge_quantum_runtime_t *rt,
                                               qge_quantum_domain_t domain,
                                               int subject_id)
{
    rt->entropy_state ^= domain_salt(domain, subject_id);
    return splitmix64_next(&rt->entropy_state);
}

static void record_replay_fallback(qge_quantum_runtime_t *rt,
                                   qge_quantum_domain_t domain,
                                   int subject_id,
                                   int reason_code,
                                   const char *message)
{
    qge_fallback_event_t fallback;

    if (!rt) {
        return;
    }

    memset(&fallback, 0, sizeof(fallback));
    fallback.frame = rt->frame;
    fallback.server_time_msec = rt->server_time_msec;
    fallback.domain = domain;
    fallback.representation = QGE_REP_NONE;
    fallback.subject_id = subject_id;
    fallback.reason_code = reason_code;
    if (message) {
        strncpy(fallback.message, message, sizeof(fallback.message) - 1);
    }
    qge_quantum_record_fallback(rt, &fallback);
}

qge_quantum_runtime_t *qge_quantum_runtime_create(void)
{
    qge_quantum_runtime_t *rt;

    rt = (qge_quantum_runtime_t *)calloc(1, sizeof(*rt));
    if (!rt) {
        return NULL;
    }

    rt->run_id = 0x5151455f52554e31ULL;
    rt->entropy_state = rt->run_id ^ 0x6d6f6f6e6c616231ULL;
    rt->entropy_source = QGE_ENTROPY_SOURCE_DETERMINISTIC;
    rt->replay_strict = true;
    return rt;
}

void qge_quantum_runtime_free(qge_quantum_runtime_t *rt)
{
    if (!rt) {
        return;
    }
    qge_quantum_trace_close(rt);
    clear_replay_entropy(rt);
    clear_replay_ai_decisions(rt);
    clear_replay_measurements(rt);
    free(rt);
}

void qge_quantum_runtime_set_seed(qge_quantum_runtime_t *rt, uint64_t seed)
{
    if (!rt) {
        return;
    }
    rt->run_id = seed ? seed : 0x5151455f52554e31ULL;
    rt->entropy_state = rt->run_id ^ 0x6d6f6f6e6c616231ULL;
    rt->entropy_offset = 0;
    rt->request_id = 0;
    rt->replay_index = 0;
    rt->replay_ai_decision_index = 0;
    rt->replay_measurement_index = 0;
    if (rt->entropy_source != QGE_ENTROPY_SOURCE_REPLAY) {
        rt->entropy_source = QGE_ENTROPY_SOURCE_DETERMINISTIC;
    }
}

void qge_quantum_runtime_set_entropy_source(qge_quantum_runtime_t *rt,
                                            qge_entropy_source_t source,
                                            qge_quantum_entropy_source_func_t func,
                                            void *user_data)
{
    if (!rt) {
        return;
    }
    if (source < 0 || source >= QGE_ENTROPY_SOURCE_MAX) {
        source = QGE_ENTROPY_SOURCE_DETERMINISTIC;
    }
    rt->entropy_source = source;
    rt->entropy_func = func;
    rt->entropy_user_data = user_data;
    if (source != QGE_ENTROPY_SOURCE_REPLAY) {
        rt->replay_index = 0;
        rt->replay_ai_decision_index = 0;
        rt->replay_measurement_index = 0;
    }
}

qge_entropy_source_t qge_quantum_runtime_get_entropy_source(
    const qge_quantum_runtime_t *rt)
{
    if (!rt) {
        return QGE_ENTROPY_SOURCE_CLASSICAL_FALLBACK;
    }
    return rt->entropy_source;
}

int qge_quantum_runtime_get_frame(const qge_quantum_runtime_t *rt)
{
    return rt ? rt->frame : 0;
}

int qge_quantum_runtime_get_server_time_msec(const qge_quantum_runtime_t *rt)
{
    return rt ? rt->server_time_msec : 0;
}

int qge_quantum_runtime_load_replay_entropy(qge_quantum_runtime_t *rt,
                                            const char *trace_path)
{
    if (qge_quantum_runtime_load_replay_trace(rt, trace_path) != 0 || !rt) {
        return -1;
    }
    if (rt->replay_count == 0) {
        clear_replay_entropy(rt);
        clear_replay_ai_decisions(rt);
        clear_replay_measurements(rt);
        return -1;
    }
    return 0;
}

int qge_quantum_runtime_load_replay_trace(qge_quantum_runtime_t *rt,
                                          const char *trace_path)
{
    qge_trace_reader_t *reader;
    qge_trace_record_header_t record;
    unsigned char payload[256];
    int result;

    if (!rt || !trace_path) {
        return -1;
    }

    reader = qge_trace_reader_open(trace_path);
    if (!reader) {
        return -1;
    }

    clear_replay_entropy(rt);
    clear_replay_ai_decisions(rt);
    clear_replay_measurements(rt);
    for (;;) {
        memset(payload, 0, sizeof(payload));
        result = qge_trace_reader_next(reader, &record, payload,
                                       sizeof(payload));
        if (result == 0) {
            break;
        }
        if (result == -2) {
            continue;
        }
        if (result < 0) {
            qge_trace_reader_close(reader);
            clear_replay_entropy(rt);
            clear_replay_ai_decisions(rt);
            clear_replay_measurements(rt);
            return -1;
        }
        if (record.kind == QGE_TRACE_RECORD_ENTROPY &&
            record.payload_size == sizeof(qge_entropy_event_t)) {
            qge_entropy_event_t event;
            memcpy(&event, payload, sizeof(event));
            if (append_replay_entropy(rt, &event) != 0) {
                qge_trace_reader_close(reader);
                clear_replay_entropy(rt);
                clear_replay_ai_decisions(rt);
                clear_replay_measurements(rt);
                return -1;
            }
        } else if (record.kind == QGE_TRACE_RECORD_AI_DECISION &&
                   record.payload_size == sizeof(qge_ai_decision_event_t)) {
            qge_ai_decision_event_t event;
            memcpy(&event, payload, sizeof(event));
            if (append_replay_ai_decision(rt, &event) != 0) {
                qge_trace_reader_close(reader);
                clear_replay_entropy(rt);
                clear_replay_ai_decisions(rt);
                clear_replay_measurements(rt);
                return -1;
            }
        } else if (record.kind == QGE_TRACE_RECORD_MEASUREMENT &&
                   record.payload_size == sizeof(qge_measurement_event_t)) {
            qge_measurement_event_t event;
            memcpy(&event, payload, sizeof(event));
            if (append_replay_measurement(rt, &event) != 0) {
                qge_trace_reader_close(reader);
                clear_replay_entropy(rt);
                clear_replay_ai_decisions(rt);
                clear_replay_measurements(rt);
                return -1;
            }
        }
    }

    qge_trace_reader_close(reader);
    if (rt->replay_count == 0 &&
        rt->replay_ai_decision_count == 0 &&
        rt->replay_measurement_count == 0) {
        return -1;
    }

    if (rt->replay_count > 0) {
        rt->entropy_source = QGE_ENTROPY_SOURCE_REPLAY;
        rt->entropy_func = NULL;
        rt->entropy_user_data = NULL;
    }
    rt->replay_index = 0;
    rt->replay_ai_decision_index = 0;
    rt->replay_measurement_index = 0;
    rt->entropy_offset = 0;
    rt->request_id = 0;
    rt->stats.replay_events_loaded = (uint64_t)rt->replay_count;
    rt->stats.replay_ai_decisions_loaded =
        (uint64_t)rt->replay_ai_decision_count;
    rt->stats.replay_measurements_loaded =
        (uint64_t)rt->replay_measurement_count;
    return 0;
}

void qge_quantum_runtime_set_replay_strict(qge_quantum_runtime_t *rt,
                                           bool strict)
{
    if (!rt) {
        return;
    }
    rt->replay_strict = strict;
}

bool qge_quantum_runtime_get_replay_strict(const qge_quantum_runtime_t *rt)
{
    return rt ? rt->replay_strict : false;
}

void qge_quantum_runtime_get_stats(const qge_quantum_runtime_t *rt,
                                   qge_quantum_runtime_stats_t *stats)
{
    if (!rt || !stats) {
        return;
    }
    memcpy(stats, &rt->stats, sizeof(*stats));
}

int qge_quantum_qubits_for_basis_count(uint64_t basis_count)
{
    int qubits;

    if (basis_count <= 1) {
        return 0;
    }

    qubits = 0;
    basis_count--;
    while (basis_count > 0) {
        qubits++;
        basis_count >>= 1;
    }
    return qubits;
}

void qge_quantum_frame_begin(qge_quantum_runtime_t *rt,
                             int frame,
                             int server_time_msec)
{
    if (!rt) {
        return;
    }
    rt->frame = frame;
    rt->server_time_msec = server_time_msec;
    rt->stats.frames_started++;
    if (rt->trace) {
        note_trace_result(rt, qge_trace_write_frame_begin(rt->trace, frame,
                                                          server_time_msec));
    }
}

void qge_quantum_frame_end(qge_quantum_runtime_t *rt)
{
    if (!rt) {
        return;
    }
    rt->stats.frames_ended++;
    if (rt->trace) {
        note_trace_result(rt, qge_trace_write_frame_end(rt->trace, rt->frame,
                                                        rt->server_time_msec));
    }
}

uint64_t qge_quantum_entropy_u64(qge_quantum_runtime_t *rt,
                                 qge_quantum_domain_t domain,
                                 int subject_id)
{
    uint64_t value;
    qge_entropy_event_t event;
    qge_entropy_source_t source;

    if (!rt) {
        static uint64_t fallback_state = 0x5151455f46424c31ULL;
        fallback_state ^= domain_salt(domain, subject_id);
        return splitmix64_next(&fallback_state);
    }

    source = rt->entropy_source;
    if (source == QGE_ENTROPY_SOURCE_REPLAY) {
        if (rt->replay_index < rt->replay_count) {
            const qge_entropy_event_t *replay =
                &rt->replay_events[rt->replay_index++];
            rt->stats.replay_events_consumed++;
            if (!rt->replay_strict ||
                replay_entropy_matches_request(rt, replay, domain, subject_id)) {
                value = replay->value;
            } else {
                source = QGE_ENTROPY_SOURCE_CLASSICAL_FALLBACK;
                rt->stats.replay_mismatches++;
                value = deterministic_fallback_entropy(rt, domain, subject_id);
                record_replay_fallback(rt, domain, subject_id,
                                       QGE_REPLAY_FALLBACK_METADATA_MISMATCH,
                                       "replay entropy metadata mismatch");
            }
        } else {
            source = QGE_ENTROPY_SOURCE_CLASSICAL_FALLBACK;
            rt->stats.replay_exhaustions++;
            value = deterministic_fallback_entropy(rt, domain, subject_id);
            record_replay_fallback(rt, domain, subject_id,
                                   QGE_REPLAY_FALLBACK_EXHAUSTED,
                                   "replay entropy exhausted");
        }
    } else if (source == QGE_ENTROPY_SOURCE_QRNG && rt->entropy_func) {
        value = rt->entropy_func(rt->entropy_user_data, domain, subject_id);
    } else {
        if (source != QGE_ENTROPY_SOURCE_DETERMINISTIC) {
            source = QGE_ENTROPY_SOURCE_DETERMINISTIC;
        }
        value = deterministic_fallback_entropy(rt, domain, subject_id);
    }

    memset(&event, 0, sizeof(event));
    event.frame = rt->frame;
    event.server_time_msec = rt->server_time_msec;
    event.domain = domain;
    event.source = source;
    event.subject_id = subject_id;
    event.request_id = rt->request_id++;
    event.value = value;
    event.entropy_offset = rt->entropy_offset++;

    rt->stats.entropy_events++;
    if (rt->trace) {
        note_trace_result(rt, qge_trace_write_entropy(rt->trace, &event));
    }

    return value;
}

void qge_quantum_record_measurement(qge_quantum_runtime_t *rt,
                                    const qge_measurement_event_t *event)
{
    if (!rt || !event) {
        return;
    }
    rt->stats.measurement_events++;
    if (rt->trace) {
        note_trace_result(rt, qge_trace_write_measurement(rt->trace, event));
    }
}

bool qge_quantum_measurement_event_is_replayable(
    const qge_measurement_event_t *event)
{
    if (!event) {
        return false;
    }
    return event->trace_id != 0;
}

bool qge_quantum_measurement_event_matches_contract(
    const qge_measurement_event_t *event,
    const qge_quantum_semantics_contract_t *contract)
{
    if (!event || !contract) {
        return false;
    }
    if (!qge_domain_is_valid(event->domain) ||
        !qge_measurement_kind_is_valid(event->kind) ||
        !qge_observation_boundary_is_valid(event->boundary)) {
        return false;
    }
    return event->domain == contract->domain &&
           event->kind == contract->measurement_kind &&
           event->boundary == contract->observation_boundary;
}

bool qge_quantum_gameplay_measurement_is_valid(
    const qge_measurement_event_t *event,
    const qge_quantum_semantics_contract_t *contract)
{
    if (!event || !contract) {
        return false;
    }
    if (!qge_quantum_semantics_contract_is_gameplay_authoritative(contract) ||
        !qge_quantum_measurement_event_matches_contract(event, contract)) {
        return false;
    }
    if ((event->flags & QGE_MEASUREMENT_FLAG_GAMEPLAY_AUTHORITY) == 0u ||
        !qge_quantum_measurement_event_is_replayable(event)) {
        return false;
    }
    return qge_probability_is_valid(event->probability) &&
           isfinite(event->phase);
}

bool qge_quantum_record_gameplay_measurement(
    qge_quantum_runtime_t *rt,
    const qge_measurement_event_t *event,
    const qge_quantum_semantics_contract_t *contract)
{
    qge_measurement_event_t replay;
    const qge_measurement_event_t *record_event = event;

    if (!rt ||
        !qge_quantum_gameplay_measurement_is_valid(event, contract)) {
        return false;
    }
    if (rt->replay_measurement_count > 0) {
        if (qge_quantum_replay_measurement(rt, event, &replay) <= 0) {
            return false;
        }
        record_event = &replay;
    }
    rt->stats.gameplay_measurement_events++;
    qge_quantum_record_measurement(rt, record_event);
    return true;
}

bool qge_quantum_material_operator_is_valid(
    const qge_material_operator_event_t *event)
{
    if (!event) {
        return false;
    }
    if (!qge_material_operator_kind_is_valid(event->kind) ||
        !qge_observation_boundary_is_valid(event->observation_boundary)) {
        return false;
    }
    if (event->material_id == 0 || event->trace_id == 0) {
        return false;
    }
    return isfinite(event->phase_shift) &&
           qge_probability_is_valid(event->decoherence) &&
           qge_amplification_is_valid(event->amplification) &&
           qge_probability_is_valid(event->protection);
}

bool qge_quantum_record_material_operator(
    qge_quantum_runtime_t *rt,
    const qge_material_operator_event_t *event)
{
    qge_state_probe_t probe;
    qge_measurement_event_t measurement;

    if (!rt || !qge_quantum_material_operator_is_valid(event)) {
        return false;
    }

    memset(&probe, 0, sizeof(probe));
    probe.frame = event->frame;
    probe.server_time_msec = event->server_time_msec;
    probe.domain = QGE_DOMAIN_MATERIAL;
    probe.representation = QGE_REP_MATERIAL_PHASE_FIELD;
    probe.subject_id = event->subject_id;
    probe.flags = event->flags | ((uint32_t)event->kind << 24);
    probe.state_hash = event->trace_id;
    probe.entropy = event->decoherence;
    probe.coherence = 1.0 - qge_clamp01(event->decoherence);
    probe.max_probability = event->amplification;
    probe.total_probability = event->protection;
    probe.active_basis_count = (int32_t)event->kind;
    probe.qubit_count =
        qge_quantum_qubits_for_basis_count(QGE_MATERIAL_OPERATOR_MAX - 1);
    probe.memory_bytes = sizeof(*event);
    strncpy(probe.label, qge_material_operator_probe_label(event->kind),
            sizeof(probe.label) - 1);

    rt->stats.material_operator_events++;
    qge_quantum_record_probe(rt, &probe);
    memset(&measurement, 0, sizeof(measurement));
    measurement.domain = QGE_DOMAIN_MATERIAL;
    measurement.kind = QGE_MEASURE_MATERIAL_PHASE;
    measurement.boundary = event->observation_boundary;
    measurement.frame = event->frame;
    measurement.server_time_msec = event->server_time_msec;
    measurement.subject_id = event->subject_id;
    measurement.flags = probe.flags;
    measurement.basis_index =
        ((uint64_t)(uint32_t)event->kind << 32) | event->material_id;
    measurement.probability = 1.0 - qge_clamp01(event->decoherence);
    measurement.phase = event->phase_shift;
    measurement.entropy_offset = event->trace_id;
    measurement.trace_id = event->trace_id;
    qge_quantum_record_measurement(rt, &measurement);
    return true;
}

bool qge_quantum_weapon_operator_is_valid(
    const qge_weapon_operator_event_t *event)
{
    if (!event) {
        return false;
    }
    if (!qge_weapon_operator_kind_is_valid(event->kind) ||
        !qge_observation_boundary_is_valid(event->observation_boundary)) {
        return false;
    }
    if (event->weapon_id == 0 || event->trace_id == 0) {
        return false;
    }
    if (event->ammo_delta < 0 || event->damage_delta < 0) {
        return false;
    }
    return isfinite(event->phase_shift) &&
           qge_probability_is_valid(event->decoherence) &&
           qge_probability_is_valid(event->spread) &&
           qge_amplification_is_valid(event->amplification);
}

bool qge_quantum_record_weapon_operator(
    qge_quantum_runtime_t *rt,
    const qge_weapon_operator_event_t *event)
{
    qge_state_probe_t probe;
    qge_measurement_event_t measurement;

    if (!rt || !qge_quantum_weapon_operator_is_valid(event)) {
        return false;
    }

    memset(&probe, 0, sizeof(probe));
    probe.frame = event->frame;
    probe.server_time_msec = event->server_time_msec;
    probe.domain = QGE_DOMAIN_WEAPON;
    probe.representation = qge_weapon_operator_representation(event->kind);
    probe.subject_id = event->subject_id;
    probe.flags = event->flags | ((uint32_t)event->kind << 24);
    probe.state_hash = event->trace_id;
    probe.entropy = event->decoherence;
    probe.coherence = 1.0 - qge_clamp01(event->decoherence);
    probe.max_probability = event->spread;
    probe.total_probability = event->amplification;
    probe.active_basis_count = (int32_t)event->kind;
    probe.qubit_count =
        qge_quantum_qubits_for_basis_count(QGE_WEAPON_OPERATOR_MAX - 1);
    probe.memory_bytes = sizeof(*event);
    strncpy(probe.label, qge_weapon_operator_probe_label(event->kind),
            sizeof(probe.label) - 1);

    memset(&measurement, 0, sizeof(measurement));
    measurement.domain = QGE_DOMAIN_WEAPON;
    measurement.kind = QGE_MEASURE_WEAPON_OPERATION;
    measurement.boundary = event->observation_boundary;
    measurement.frame = event->frame;
    measurement.server_time_msec = event->server_time_msec;
    measurement.subject_id = event->subject_id;
    measurement.flags = probe.flags;
    measurement.basis_index =
        ((uint64_t)(uint32_t)event->kind << 32) | event->weapon_id;
    measurement.probability = 1.0 - qge_clamp01(event->decoherence);
    measurement.phase = event->phase_shift;
    measurement.entropy_offset = event->trace_id;
    measurement.trace_id = event->trace_id;

    rt->stats.weapon_operator_events++;
    qge_quantum_record_probe(rt, &probe);
    qge_quantum_record_measurement(rt, &measurement);
    return true;
}

void qge_quantum_record_probe(qge_quantum_runtime_t *rt,
                              const qge_state_probe_t *probe)
{
    if (!rt || !probe) {
        return;
    }
    rt->stats.probe_events++;
    if (rt->trace) {
        note_trace_result(rt, qge_trace_write_probe(rt->trace, probe));
    }
}

void qge_quantum_record_fallback(qge_quantum_runtime_t *rt,
                                 const qge_fallback_event_t *event)
{
    if (!rt || !event) {
        return;
    }
    rt->stats.fallback_events++;
    if (rt->trace) {
        note_trace_result(rt, qge_trace_write_fallback(rt->trace, event));
    }
}

void qge_quantum_record_entanglement(qge_quantum_runtime_t *rt,
                                     const qge_entanglement_edge_t *edge)
{
    if (!rt || !edge) {
        return;
    }
    rt->stats.entanglement_edges++;
    if (rt->trace) {
        note_trace_result(rt, qge_trace_write_entanglement(rt->trace, edge));
    }
}

void qge_quantum_record_ai_decision(qge_quantum_runtime_t *rt,
                                    const qge_ai_decision_event_t *event)
{
    if (!rt || !event) {
        return;
    }
    rt->stats.ai_decision_events++;
    if (rt->trace) {
        note_trace_result(rt, qge_trace_write_ai_decision(rt->trace, event));
    }
}

int qge_quantum_replay_ai_decision(qge_quantum_runtime_t *rt,
                                   const qge_ai_decision_event_t *request,
                                   qge_ai_decision_event_t *replay)
{
    const qge_ai_decision_event_t *event;

    if (!rt || !request || !replay || rt->replay_ai_decision_count == 0) {
        return 0;
    }
    if (rt->replay_ai_decision_index >= rt->replay_ai_decision_count) {
        rt->stats.replay_ai_decision_exhaustions++;
        record_replay_fallback(rt, QGE_DOMAIN_AI, request->enemy_id,
                               QGE_REPLAY_FALLBACK_AI_DECISION_EXHAUSTED,
                               "replay ai decision exhausted");
        return -1;
    }

    event = &rt->replay_ai_decisions[rt->replay_ai_decision_index++];
    rt->stats.replay_ai_decisions_consumed++;
    if (!rt->replay_strict ||
        replay_ai_decision_matches_request(event, request)) {
        *replay = *event;
        return 1;
    }

    rt->stats.replay_ai_decision_mismatches++;
    record_replay_fallback(rt, QGE_DOMAIN_AI, request->enemy_id,
                           QGE_REPLAY_FALLBACK_AI_DECISION_MISMATCH,
                           "replay ai decision metadata mismatch");
    return -1;
}

int qge_quantum_replay_measurement(qge_quantum_runtime_t *rt,
                                   const qge_measurement_event_t *request,
                                   qge_measurement_event_t *replay)
{
    const qge_measurement_event_t *event;

    if (!rt || !request || !replay || rt->replay_measurement_count == 0) {
        return 0;
    }
    if (rt->replay_measurement_index >= rt->replay_measurement_count) {
        rt->stats.replay_measurement_exhaustions++;
        record_replay_fallback(rt, request->domain, request->subject_id,
                               QGE_REPLAY_FALLBACK_MEASUREMENT_EXHAUSTED,
                               "replay measurement exhausted");
        return -1;
    }

    event = &rt->replay_measurements[rt->replay_measurement_index++];
    rt->stats.replay_measurements_consumed++;
    if (!rt->replay_strict ||
        replay_measurement_matches_request(event, request)) {
        *replay = *event;
        return 1;
    }

    rt->stats.replay_measurement_mismatches++;
    record_replay_fallback(rt, request->domain, request->subject_id,
                           QGE_REPLAY_FALLBACK_MEASUREMENT_MISMATCH,
                           "replay measurement metadata mismatch");
    return -1;
}

int qge_quantum_trace_open(qge_quantum_runtime_t *rt, const char *path)
{
    if (!rt || !path) {
        return -1;
    }
    qge_quantum_trace_close(rt);
    rt->trace = qge_trace_writer_open(path, rt->run_id, 0);
    return rt->trace ? 0 : -1;
}

void qge_quantum_trace_close(qge_quantum_runtime_t *rt)
{
    if (!rt || !rt->trace) {
        return;
    }
    qge_trace_writer_close(rt->trace);
    rt->trace = NULL;
}

const char *qge_quantum_domain_name(qge_quantum_domain_t domain)
{
    static const char *names[] = {
        "render",
        "visibility",
        "projectile",
        "particle",
        "audio",
        "ai",
        "rng",
        "material",
        "physics",
        "ui",
        "weapon"
    };
    if (domain < 0 || domain >= QGE_DOMAIN_MAX) {
        return "unknown";
    }
    return names[domain];
}

const char *qge_quantum_representation_name(qge_quantum_representation_t rep)
{
    static const char *names[] = {
        "none",
        "dense_state",
        "sparse_dwt",
        "mps",
        "ca_mps",
        "clifford_tableau",
        "pauli_frame",
        "classical_oracle",
        "grover_search",
        "dct_transducer",
        "material_phase_field",
        "hybrid"
    };
    if (rep < 0 || rep >= QGE_REP_MAX) {
        return "unknown";
    }
    return names[rep];
}

const char *qge_measurement_kind_name(qge_measurement_kind_t kind)
{
    static const char *names[] = {
        "none",
        "render_sample",
        "vis_surface_set",
        "projectile_impact",
        "particle_position",
        "audio_block",
        "ai_action",
        "rng_batch",
        "material_phase",
        "physics_collision",
        "entanglement_collapse",
        "projectile_writeback",
        "projectile_branch",
        "projectile_collision_oracle",
        "weapon_operation"
    };
    if (kind < 0 || kind >= QGE_MEASURE_MAX) {
        return "unknown";
    }
    return names[kind];
}

const char *qge_observation_boundary_name(qge_observation_boundary_t boundary)
{
    static const char *names[] = {
        "none",
        "player_visible",
        "collision",
        "damage",
        "audio_mix",
        "ai_decision",
        "network_serialize",
        "save_or_demo",
        "debug_measure",
        "frame_boundary"
    };
    if (boundary < 0 || boundary >= QGE_OBSERVE_MAX) {
        return "unknown";
    }
    return names[boundary];
}

const char *qge_material_operator_name(qge_material_operator_kind_t kind)
{
    static const char *names[] = {
        "none",
        "water_decoherence",
        "lava_phase",
        "slipgate_phase",
        "quad_amplification",
        "ring_protection",
        "pentagram_protection",
        "rune_phase"
    };
    if (kind < 0 || kind >= QGE_MATERIAL_OPERATOR_MAX) {
        return "unknown";
    }
    return names[kind];
}

const char *qge_weapon_operator_name(qge_weapon_operator_kind_t kind)
{
    static const char *names[] = {
        "none",
        "shotgun_spread_measurement",
        "nail_pauli_noise",
        "rocket_splash_wavefront",
        "grenade_fuse_branch",
        "lightning_continuous_measurement",
        "axe_contact_measurement"
    };
    if (kind < 0 || kind >= QGE_WEAPON_OPERATOR_MAX) {
        return "unknown";
    }
    return names[kind];
}

uint32_t qge_quantum_semantics_contract_coverage(
    const qge_quantum_semantics_contract_t *contract)
{
    uint32_t coverage = 0u;

    if (!contract) {
        return 0u;
    }
    if (qge_domain_is_valid(contract->domain)) {
        coverage |= QGE_SEMANTICS_HAS_DOMAIN;
    }
    if (qge_representation_is_valid(contract->representation)) {
        coverage |= QGE_SEMANTICS_HAS_REPRESENTATION;
    }
    if (qge_semantic_text_present(contract->basis_semantics)) {
        coverage |= QGE_SEMANTICS_HAS_BASIS;
    }
    if (qge_semantic_text_present(contract->amplitude_semantics)) {
        coverage |= QGE_SEMANTICS_HAS_AMPLITUDES;
    }
    if (qge_semantic_text_present(contract->phase_semantics)) {
        coverage |= QGE_SEMANTICS_HAS_PHASE;
    }
    if (qge_semantic_text_present(contract->evolution_semantics)) {
        coverage |= QGE_SEMANTICS_HAS_EVOLUTION;
    }
    if (qge_measurement_kind_is_valid(contract->measurement_kind) &&
        qge_semantic_text_present(contract->measurement_semantics)) {
        coverage |= QGE_SEMANTICS_HAS_MEASUREMENT;
    }
    if (qge_observation_boundary_is_valid(contract->observation_boundary)) {
        coverage |= QGE_SEMANTICS_HAS_OBSERVATION_BOUNDARY;
    }
    if (qge_semantic_text_present(contract->decoherence_semantics)) {
        coverage |= QGE_SEMANTICS_HAS_DECOHERENCE;
    }
    if (qge_semantic_text_present(contract->replay_semantics)) {
        coverage |= QGE_SEMANTICS_HAS_REPLAY;
    }
    if (qge_semantic_text_present(contract->fallback_semantics)) {
        coverage |= QGE_SEMANTICS_HAS_FALLBACK;
    }
    if (qge_semantic_text_present(contract->writeback_semantics)) {
        coverage |= QGE_SEMANTICS_HAS_WRITEBACK;
    }
    return coverage;
}

bool qge_quantum_semantics_contract_is_complete(
    const qge_quantum_semantics_contract_t *contract)
{
    return (qge_quantum_semantics_contract_coverage(contract) &
            QGE_SEMANTICS_REQUIRED_COMPLETE) ==
           QGE_SEMANTICS_REQUIRED_COMPLETE;
}

bool qge_quantum_semantics_contract_is_gameplay_authoritative(
    const qge_quantum_semantics_contract_t *contract)
{
    if (!contract ||
        !qge_quantum_semantics_contract_is_complete(contract)) {
        return false;
    }
    return contract->gameplay_affecting &&
           contract->authoritative_writeback;
}
