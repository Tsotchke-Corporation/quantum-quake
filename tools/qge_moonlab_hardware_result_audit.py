#!/usr/bin/env python3
"""Audit bounded Moonlab hardware result rows in job results."""

from __future__ import annotations

import math
from typing import Any


SUBMISSION_PACKET_SCHEMA = "qge.moonlab_submission_packet.v0"
JOB_RESULTS_SCHEMA = "qge.moonlab_job_results.v0"
HARDWARE_SCOPE_SCHEMA = "qge.moonlab_hardware_submission_scope.v0"
HARDWARE_BACKEND_KIND = "moonlab_hardware"
FORBIDDEN_CLAIM_FLAGS = (
    "whole_game_hardware_execution_claimed",
    "hardware_quantum_advantage_claimed",
    "dense_70000_qubit_state_claimed",
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float)) and
        not isinstance(value, bool) and
        math.isfinite(float(value))
    )


def nonnegative_finite_number(value: Any) -> bool:
    return finite_number(value) and float(value) >= 0.0


def hex_digest(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(char in "0123456789abcdef" for char in value.lower())


def job_id(job: dict[str, Any]) -> str | None:
    value = job.get("job_id")
    return value if nonempty_string(value) else None


def duplicate_strings(values: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted(value for value, count in counts.items() if count > 1)


def candidate_jobs_by_id(
    submission_packet: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for job in list_or_empty(submission_packet.get("candidate_jobs")):
        if not isinstance(job, dict):
            continue
        item_id = job_id(job)
        if item_id:
            indexed[item_id] = job
    return indexed


def hardware_backend_results(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in list_or_empty(job.get("backend_results"))
        if isinstance(item, dict) and
        item.get("backend_kind") == HARDWARE_BACKEND_KIND
    ]


def scope_candidate_digests(
    hardware_submission_scope: dict[str, Any],
) -> dict[str, Any]:
    return dict_or_empty(hardware_submission_scope.get("candidate_digests"))


def append_if(condition: bool, mismatches: list[str], field: str) -> None:
    if condition:
        mismatches.append(field)


def audit_hardware_result_row(
    job: dict[str, Any],
    result: dict[str, Any],
    candidate: dict[str, Any] | None,
    scope_digests: dict[str, Any],
) -> list[str]:
    mismatches: list[str] = []
    item_id = job_id(job)
    append_if(candidate is None, mismatches, "job_id")
    append_if(job.get("hardware_submission_status") != "completed",
              mismatches, "hardware_submission_status")
    append_if(job.get("result_status") !=
              "hardware_completed_simulator_retained",
              mismatches, "result_status")

    claim_posture = dict_or_empty(job.get("claim_posture"))
    append_if(claim_posture.get("hardware_result_claimed") is not True,
              mismatches, "claim_posture.hardware_result_claimed")
    for flag in FORBIDDEN_CLAIM_FLAGS:
        append_if(result.get(flag) is True, mismatches, flag)
        append_if(claim_posture.get(flag) is True, mismatches,
                  f"claim_posture.{flag}")

    pointer = dict_or_empty(job.get("hardware_result_record"))
    append_if(pointer.get("backend_id") != result.get("backend_id"),
              mismatches, "hardware_result_record.backend_id")
    append_if(pointer.get("candidate_digest") != result.get("candidate_digest"),
              mismatches, "hardware_result_record.candidate_digest")
    append_if(
        pointer.get("hardware_record_sha256") !=
        result.get("hardware_record_sha256"),
        mismatches,
        "hardware_result_record.hardware_record_sha256",
    )

    append_if(not nonempty_string(result.get("backend_id")),
              mismatches, "backend_id")
    append_if(result.get("backend_kind") != HARDWARE_BACKEND_KIND,
              mismatches, "backend_kind")
    append_if(result.get("status") != "completed", mismatches, "status")
    append_if(not nonempty_string(result.get("run_id")), mismatches, "run_id")
    append_if(not nonempty_string(result.get("submitted_utc")),
              mismatches, "submitted_utc")
    append_if(not nonempty_string(result.get("completed_utc")),
              mismatches, "completed_utc")
    append_if(not hex_digest(result.get("hardware_record_sha256")),
              mismatches, "hardware_record_sha256")

    if candidate is not None:
        append_if(
            list_or_empty(candidate.get("missing_required_artifacts")) != [],
            mismatches,
            "candidate.missing_required_artifacts",
        )
        append_if(
            result.get("candidate_digest") != candidate.get("candidate_digest"),
            mismatches,
            "candidate_digest",
        )
        append_if(
            nonempty_string(item_id) and
            scope_digests.get(item_id) != candidate.get("candidate_digest"),
            mismatches,
            "scope.candidate_digests",
        )

    shot_schedule = dict_or_empty(result.get("shot_schedule"))
    readout_metadata = dict_or_empty(result.get("readout_metadata"))
    observations = dict_or_empty(result.get("observations"))
    scheduled_shots = shot_schedule.get("shots")
    completed_shots = readout_metadata.get("shots_completed")
    observed_shots = observations.get("shots")
    append_if(not positive_int(scheduled_shots), mismatches,
              "shot_schedule.shots")
    append_if(not positive_int(shot_schedule.get("batches")), mismatches,
              "shot_schedule.batches")
    append_if(not nonempty_string(shot_schedule.get("schedule_id")),
              mismatches, "shot_schedule.schedule_id")
    append_if(not positive_int(completed_shots), mismatches,
              "readout_metadata.shots_completed")
    append_if(
        positive_int(scheduled_shots) and
        positive_int(completed_shots) and
        completed_shots != scheduled_shots,
        mismatches,
        "readout_metadata.shots_completed_matches_schedule",
    )
    append_if(not nonempty_string(readout_metadata.get("readout_format")),
              mismatches, "readout_metadata.readout_format")
    append_if(not nonempty_string(readout_metadata.get("mitigation")),
              mismatches, "readout_metadata.mitigation")
    append_if(not positive_int(observed_shots), mismatches,
              "observations.shots")
    append_if(
        positive_int(observed_shots) and
        positive_int(completed_shots) and
        observed_shots != completed_shots,
        mismatches,
        "observations.shots_matches_completed",
    )
    append_if(
        not (
            finite_number(observations.get("mean_value")) or
            finite_number(observations.get("observed_value"))
        ),
        mismatches,
        "observations.mean_value_or_observed_value",
    )
    append_if(
        not nonnegative_finite_number(observations.get("readout_error")),
        mismatches,
        "observations.readout_error",
    )
    if candidate is not None and positive_int(scheduled_shots):
        expected_shots = dict_or_empty(candidate.get("resource")).get("shots")
        append_if(
            positive_int(expected_shots) and scheduled_shots != expected_shots,
            mismatches,
            "shot_schedule.shots_matches_candidate",
        )
    return sorted(set(mismatches))


def hardware_result_ledger_audit(
    submission_packet: dict[str, Any],
    job_results: dict[str, Any],
    hardware_submission_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet = dict_or_empty(submission_packet)
    results = dict_or_empty(job_results)
    scope = dict_or_empty(hardware_submission_scope)
    candidates = candidate_jobs_by_id(packet)
    scope_digests = scope_candidate_digests(scope)
    schema_mismatches = []
    if packet.get("schema") != SUBMISSION_PACKET_SCHEMA:
        schema_mismatches.append("submission_packet_schema")
    if results.get("schema") != JOB_RESULTS_SCHEMA:
        schema_mismatches.append("job_results_schema")
    if scope and scope.get("schema") != HARDWARE_SCOPE_SCHEMA:
        schema_mismatches.append("hardware_submission_scope_schema")

    row_mismatches = []
    hardware_result_job_ids = []
    hardware_result_row_count = 0
    invalid_result_job_count = 0
    for job in list_or_empty(results.get("jobs")):
        if not isinstance(job, dict):
            continue
        item_id = job_id(job)
        rows = hardware_backend_results(job)
        if rows and item_id:
            hardware_result_job_ids.append(item_id)
        if rows and not item_id:
            invalid_result_job_count += 1
        hardware_result_row_count += len(rows)
        for index, row in enumerate(rows):
            candidate = candidates.get(item_id or "")
            mismatches = audit_hardware_result_row(
                job,
                row,
                candidate,
                scope_digests,
            )
            if mismatches:
                row_mismatches.append({
                    "job_id": item_id,
                    "backend_result_index": index,
                    "mismatches": mismatches,
                })

    duplicate_hardware_result_job_ids = duplicate_strings(
        hardware_result_job_ids)
    hardware_result_job_count = len(set(hardware_result_job_ids))
    completed_hardware_result_count = sum(
        1 for job in list_or_empty(results.get("jobs"))
        if isinstance(job, dict)
        for row in hardware_backend_results(job)
        if row.get("status") == "completed"
    )
    count_mismatches = []
    reported_completed = int_or_none(results.get("completed_hardware_job_count"))
    reported_submitted = int_or_none(results.get("hardware_submitted_job_count"))
    if reported_completed not in (None, hardware_result_job_count):
        count_mismatches.append("completed_hardware_job_count")
    if hardware_result_job_count and reported_submitted != hardware_result_job_count:
        count_mismatches.append("hardware_submitted_job_count")
    if hardware_result_row_count != hardware_result_job_count:
        count_mismatches.append("one_hardware_result_per_job")
    if (
        hardware_result_job_count and
        results.get("overall_status") != "simulator_complete_hardware_recorded"
    ):
        count_mismatches.append("overall_status")

    mismatch_count = (
        len(schema_mismatches) +
        len(count_mismatches) +
        invalid_result_job_count +
        len(duplicate_hardware_result_job_ids) +
        sum(len(row["mismatches"]) for row in row_mismatches)
    )
    recorded = (
        packet.get("schema") == SUBMISSION_PACKET_SCHEMA and
        results.get("schema") == JOB_RESULTS_SCHEMA
    )
    return {
        "recorded": recorded,
        "hardware_result_job_count": hardware_result_job_count,
        "hardware_result_row_count": hardware_result_row_count,
        "completed_hardware_result_count": completed_hardware_result_count,
        "reported_completed_hardware_job_count": reported_completed,
        "reported_hardware_submitted_job_count": reported_submitted,
        "hardware_result_job_ids": sorted(set(hardware_result_job_ids)),
        "duplicate_hardware_result_job_ids": duplicate_hardware_result_job_ids,
        "invalid_result_job_count": invalid_result_job_count,
        "schema_mismatches": schema_mismatches,
        "count_mismatches": count_mismatches,
        "row_mismatch_job_ids": sorted({
            row["job_id"] for row in row_mismatches if row.get("job_id")
        }),
        "row_mismatches": row_mismatches,
        "mismatch_count": mismatch_count,
        "passed": recorded and mismatch_count == 0,
    }
