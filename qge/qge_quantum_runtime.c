/**
 * @file qge_quantum_runtime.c
 * @brief Shared runtime spine for QGE quantum events.
 */

#include "qge_quantum_runtime.h"
#include "qge_trace.h"
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
    bool replay_strict;
    qge_trace_writer_t *trace;
    qge_quantum_runtime_stats_t stats;
};

enum {
    QGE_REPLAY_FALLBACK_METADATA_MISMATCH = 1,
    QGE_REPLAY_FALLBACK_EXHAUSTED = 2
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
    qge_trace_reader_t *reader;
    qge_trace_record_header_t record;
    qge_entropy_event_t event;
    int result;

    if (!rt || !trace_path) {
        return -1;
    }

    reader = qge_trace_reader_open(trace_path);
    if (!reader) {
        return -1;
    }

    clear_replay_entropy(rt);
    for (;;) {
        memset(&event, 0, sizeof(event));
        result = qge_trace_reader_next(reader, &record, &event, sizeof(event));
        if (result == 0) {
            break;
        }
        if (result == -2) {
            continue;
        }
        if (result < 0) {
            qge_trace_reader_close(reader);
            clear_replay_entropy(rt);
            return -1;
        }
        if (record.kind == QGE_TRACE_RECORD_ENTROPY &&
            record.payload_size == sizeof(event) &&
            append_replay_entropy(rt, &event) != 0) {
            qge_trace_reader_close(reader);
            clear_replay_entropy(rt);
            return -1;
        }
    }

    qge_trace_reader_close(reader);
    if (rt->replay_count == 0) {
        return -1;
    }

    rt->entropy_source = QGE_ENTROPY_SOURCE_REPLAY;
    rt->entropy_func = NULL;
    rt->entropy_user_data = NULL;
    rt->replay_index = 0;
    rt->entropy_offset = 0;
    rt->request_id = 0;
    rt->stats.replay_events_loaded = (uint64_t)rt->replay_count;
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
        "ui"
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
        "entanglement_collapse"
    };
    if (kind < 0 || kind >= QGE_MEASURE_MAX) {
        return "unknown";
    }
    return names[kind];
}
