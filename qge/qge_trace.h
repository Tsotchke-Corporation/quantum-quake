/**
 * @file qge_trace.h
 * @brief Binary experiment trace records for Quantum Quake.
 */

#ifndef QGE_TRACE_H
#define QGE_TRACE_H

#include "qge_quantum_runtime.h"

#ifdef __cplusplus
extern "C" {
#endif

#define QGE_TRACE_MAGIC 0x52544751u  /* QGTR */
#define QGE_TRACE_VERSION 1u

typedef enum {
    QGE_TRACE_RECORD_FRAME_BEGIN = 1,
    QGE_TRACE_RECORD_FRAME_END,
    QGE_TRACE_RECORD_ENTROPY,
    QGE_TRACE_RECORD_MEASUREMENT,
    QGE_TRACE_RECORD_STATE_PROBE,
    QGE_TRACE_RECORD_FALLBACK,
    QGE_TRACE_RECORD_ENTANGLEMENT
} qge_trace_record_kind_t;

typedef struct {
    uint32_t magic;
    uint16_t version;
    uint16_t header_size;
    uint32_t flags;
    uint32_t reserved;
    uint64_t run_id;
    uint64_t moonlab_abi_hash;
    uint64_t qge_build_hash;
    uint64_t quake_content_hash;
} qge_trace_header_t;

typedef struct {
    uint16_t kind;
    uint16_t version;
    uint32_t payload_size;
    uint64_t sequence;
} qge_trace_record_header_t;

typedef struct {
    int32_t frame;
    int32_t server_time_msec;
} qge_trace_frame_event_t;

typedef struct qge_trace_writer_s qge_trace_writer_t;
typedef struct qge_trace_reader_s qge_trace_reader_t;

qge_trace_writer_t *qge_trace_writer_open(const char *path,
                                          uint64_t run_id,
                                          uint32_t flags);
void qge_trace_writer_close(qge_trace_writer_t *writer);

int qge_trace_write_frame_begin(qge_trace_writer_t *writer,
                                int frame,
                                int server_time_msec);
int qge_trace_write_frame_end(qge_trace_writer_t *writer,
                              int frame,
                              int server_time_msec);
int qge_trace_write_entropy(qge_trace_writer_t *writer,
                            const qge_entropy_event_t *event);
int qge_trace_write_measurement(qge_trace_writer_t *writer,
                                const qge_measurement_event_t *event);
int qge_trace_write_probe(qge_trace_writer_t *writer,
                          const qge_state_probe_t *probe);
int qge_trace_write_fallback(qge_trace_writer_t *writer,
                             const qge_fallback_event_t *event);
int qge_trace_write_entanglement(qge_trace_writer_t *writer,
                                 const qge_entanglement_edge_t *edge);

qge_trace_reader_t *qge_trace_reader_open(const char *path);
void qge_trace_reader_close(qge_trace_reader_t *reader);
int qge_trace_reader_get_header(const qge_trace_reader_t *reader,
                                qge_trace_header_t *header);
int qge_trace_reader_next(qge_trace_reader_t *reader,
                          qge_trace_record_header_t *record,
                          void *payload,
                          size_t payload_capacity);

#ifdef __cplusplus
}
#endif

#endif /* QGE_TRACE_H */
