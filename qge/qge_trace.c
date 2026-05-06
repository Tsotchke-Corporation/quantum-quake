/**
 * @file qge_trace.c
 * @brief Binary trace writer/reader for shared QGE quantum events.
 */

#include "qge_trace.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct qge_trace_writer_s {
    FILE *file;
    qge_trace_header_t header;
    uint64_t next_sequence;
};

struct qge_trace_reader_s {
    FILE *file;
    qge_trace_header_t header;
};

static int trace_write_record(qge_trace_writer_t *writer,
                              qge_trace_record_kind_t kind,
                              const void *payload,
                              uint32_t payload_size)
{
    qge_trace_record_header_t record;

    if (!writer || !writer->file || (!payload && payload_size != 0)) {
        return -1;
    }

    record.kind = (uint16_t)kind;
    record.version = QGE_TRACE_VERSION;
    record.payload_size = payload_size;
    record.sequence = writer->next_sequence++;

    if (fwrite(&record, sizeof(record), 1, writer->file) != 1) {
        return -1;
    }
    if (payload_size > 0 && fwrite(payload, payload_size, 1, writer->file) != 1) {
        return -1;
    }
    return 0;
}

qge_trace_writer_t *qge_trace_writer_open(const char *path,
                                          uint64_t run_id,
                                          uint32_t flags)
{
    qge_trace_writer_t *writer;

    if (!path || !path[0]) {
        return NULL;
    }

    writer = (qge_trace_writer_t *)calloc(1, sizeof(*writer));
    if (!writer) {
        return NULL;
    }

    writer->file = fopen(path, "wb");
    if (!writer->file) {
        free(writer);
        return NULL;
    }

    writer->header.magic = QGE_TRACE_MAGIC;
    writer->header.version = QGE_TRACE_VERSION;
    writer->header.header_size = (uint16_t)sizeof(writer->header);
    writer->header.flags = flags;
    writer->header.run_id = run_id;

    if (fwrite(&writer->header, sizeof(writer->header), 1, writer->file) != 1) {
        fclose(writer->file);
        free(writer);
        return NULL;
    }

    return writer;
}

void qge_trace_writer_close(qge_trace_writer_t *writer)
{
    if (!writer) {
        return;
    }
    if (writer->file) {
        fflush(writer->file);
        fclose(writer->file);
    }
    free(writer);
}

int qge_trace_write_frame_begin(qge_trace_writer_t *writer,
                                int frame,
                                int server_time_msec)
{
    qge_trace_frame_event_t event;
    event.frame = frame;
    event.server_time_msec = server_time_msec;
    return trace_write_record(writer, QGE_TRACE_RECORD_FRAME_BEGIN,
                              &event, (uint32_t)sizeof(event));
}

int qge_trace_write_frame_end(qge_trace_writer_t *writer,
                              int frame,
                              int server_time_msec)
{
    qge_trace_frame_event_t event;
    event.frame = frame;
    event.server_time_msec = server_time_msec;
    return trace_write_record(writer, QGE_TRACE_RECORD_FRAME_END,
                              &event, (uint32_t)sizeof(event));
}

int qge_trace_write_entropy(qge_trace_writer_t *writer,
                            const qge_entropy_event_t *event)
{
    return trace_write_record(writer, QGE_TRACE_RECORD_ENTROPY,
                              event, (uint32_t)sizeof(*event));
}

int qge_trace_write_measurement(qge_trace_writer_t *writer,
                                const qge_measurement_event_t *event)
{
    return trace_write_record(writer, QGE_TRACE_RECORD_MEASUREMENT,
                              event, (uint32_t)sizeof(*event));
}

int qge_trace_write_probe(qge_trace_writer_t *writer,
                          const qge_state_probe_t *probe)
{
    return trace_write_record(writer, QGE_TRACE_RECORD_STATE_PROBE,
                              probe, (uint32_t)sizeof(*probe));
}

int qge_trace_write_fallback(qge_trace_writer_t *writer,
                             const qge_fallback_event_t *event)
{
    return trace_write_record(writer, QGE_TRACE_RECORD_FALLBACK,
                              event, (uint32_t)sizeof(*event));
}

int qge_trace_write_entanglement(qge_trace_writer_t *writer,
                                 const qge_entanglement_edge_t *edge)
{
    return trace_write_record(writer, QGE_TRACE_RECORD_ENTANGLEMENT,
                              edge, (uint32_t)sizeof(*edge));
}

qge_trace_reader_t *qge_trace_reader_open(const char *path)
{
    qge_trace_reader_t *reader;

    if (!path || !path[0]) {
        return NULL;
    }

    reader = (qge_trace_reader_t *)calloc(1, sizeof(*reader));
    if (!reader) {
        return NULL;
    }

    reader->file = fopen(path, "rb");
    if (!reader->file) {
        free(reader);
        return NULL;
    }

    if (fread(&reader->header, sizeof(reader->header), 1, reader->file) != 1 ||
        reader->header.magic != QGE_TRACE_MAGIC ||
        reader->header.version != QGE_TRACE_VERSION) {
        fclose(reader->file);
        free(reader);
        return NULL;
    }

    return reader;
}

void qge_trace_reader_close(qge_trace_reader_t *reader)
{
    if (!reader) {
        return;
    }
    if (reader->file) {
        fclose(reader->file);
    }
    free(reader);
}

int qge_trace_reader_get_header(const qge_trace_reader_t *reader,
                                qge_trace_header_t *header)
{
    if (!reader || !header) {
        return -1;
    }
    memcpy(header, &reader->header, sizeof(*header));
    return 0;
}

int qge_trace_reader_next(qge_trace_reader_t *reader,
                          qge_trace_record_header_t *record,
                          void *payload,
                          size_t payload_capacity)
{
    if (!reader || !reader->file || !record) {
        return -1;
    }

    if (fread(record, sizeof(*record), 1, reader->file) != 1) {
        return feof(reader->file) ? 0 : -1;
    }
    if (record->version != QGE_TRACE_VERSION) {
        return -1;
    }
    if (record->payload_size > payload_capacity) {
        if (fseek(reader->file, (long)record->payload_size, SEEK_CUR) != 0) {
            return -1;
        }
        return -2;
    }
    if (record->payload_size > 0 &&
        fread(payload, record->payload_size, 1, reader->file) != 1) {
        return -1;
    }
    return 1;
}
