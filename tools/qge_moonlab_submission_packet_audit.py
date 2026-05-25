#!/usr/bin/env python3
"""Consistency audit for Moonlab hardware submission packets."""

from __future__ import annotations

from typing import Any


SUBMISSION_PACKET_SCHEMA = "qge.moonlab_submission_packet.v0"
JOB_SPECS_SCHEMA = "qge.moonlab_job_specs.v0"
JOB_RESULTS_SCHEMA = "qge.moonlab_job_results.v0"
READY_STATUS = "ready_for_hardware_submission_metadata"
SUBMITTED_STATUS = "hardware_submission_recorded"


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def job_id(job: dict[str, Any]) -> str | None:
    value = job.get("job_id")
    return value if isinstance(value, str) and value else None


def duplicate_strings(values: list[str]) -> list[str]:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def result_jobs_by_id(job_results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for job in list_or_empty(job_results.get("jobs")):
        if not isinstance(job, dict):
            continue
        item_id = job_id(job)
        if item_id:
            indexed[item_id] = job
    return indexed


def expected_submission_status(
    spec_job: dict[str, Any],
    result_job: dict[str, Any],
) -> str:
    if list_or_empty(result_job.get("missing_required_artifacts")):
        return "blocked_missing_required_artifact"
    hardware_status = spec_job.get("hardware_submission_status")
    if hardware_status not in (None, "not_submitted"):
        return SUBMITTED_STATUS
    return READY_STATUS


def simulator_backend_results(result_job: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in list_or_empty(result_job.get("backend_results"))
        if isinstance(item, dict) and
        item.get("backend_kind") in ("moonlab_simulator",
                                     "native_backend_replay")
    ]


def artifact_evidence_summary(items: Any) -> list[dict[str, Any]]:
    evidence = []
    for item in list_or_empty(items):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        evidence.append({
            "name": name,
            "path": item.get("path"),
            "sha256": item.get("sha256"),
            "size_bytes": item.get("size_bytes"),
            "exists": item.get("exists"),
        })
    return sorted(evidence, key=lambda item: item["name"])


def expected_candidate_jobs(
    job_specs: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        item for item in list_or_empty(job_specs.get("jobs"))
        if isinstance(item, dict) and item.get("hardware_candidate") is True
    ]


def submission_packet_ledger_audit(
    job_specs: dict[str, Any],
    job_results: dict[str, Any],
    submission_packet: dict[str, Any],
) -> dict[str, Any]:
    spec_jobs = expected_candidate_jobs(job_specs)
    candidate_jobs = [
        item for item in list_or_empty(submission_packet.get("candidate_jobs"))
        if isinstance(item, dict)
    ]
    spec_ids = [item for item in (job_id(job) for job in spec_jobs) if item]
    candidate_ids = [
        item for item in (job_id(job) for job in candidate_jobs) if item
    ]
    duplicate_spec_ids = duplicate_strings(spec_ids)
    duplicate_candidate_ids = duplicate_strings(candidate_ids)
    invalid_spec_count = len(spec_jobs) - len(spec_ids)
    invalid_candidate_count = len(candidate_jobs) - len(candidate_ids)
    missing_candidate_ids = sorted(set(spec_ids) - set(candidate_ids))
    unexpected_candidate_ids = sorted(set(candidate_ids) - set(spec_ids))
    result_index = result_jobs_by_id(job_results)
    candidate_index = {
        item_id: job
        for item_id, job in (
            (job_id(job), job) for job in candidate_jobs
        )
        if item_id
    }

    row_mismatches = []
    for spec_job in spec_jobs:
        item_id = job_id(spec_job)
        if not item_id or item_id not in candidate_index:
            continue
        candidate = candidate_index[item_id]
        result_job = result_index.get(item_id, {})
        mismatches = []
        required = dict_or_empty(spec_job.get("required_artifacts"))
        expected_artifact_names = sorted(required.keys())
        expected_artifact_evidence = artifact_evidence_summary(
            result_job.get("artifact_evidence"))
        expected_backend_results = simulator_backend_results(result_job)
        comparisons = (
            ("domain", spec_job.get("domain"), candidate.get("domain")),
            ("kind", spec_job.get("kind"), candidate.get("kind")),
            (
                "backend_targets",
                list_or_empty(spec_job.get("backend_targets")),
                list_or_empty(candidate.get("backend_targets")),
            ),
            (
                "resource",
                dict_or_empty(spec_job.get("resource")),
                dict_or_empty(candidate.get("resource")),
            ),
            (
                "required_artifacts",
                required,
                dict_or_empty(candidate.get("required_artifacts")),
            ),
            (
                "required_artifact_names",
                expected_artifact_names,
                list_or_empty(candidate.get("required_artifact_names")),
            ),
            (
                "missing_required_artifacts",
                list_or_empty(result_job.get("missing_required_artifacts")),
                list_or_empty(candidate.get("missing_required_artifacts")),
            ),
            (
                "simulator_result_status",
                result_job.get("result_status"),
                candidate.get("simulator_result_status"),
            ),
            (
                "submission_status",
                expected_submission_status(spec_job, result_job),
                candidate.get("submission_status"),
            ),
            (
                "hardware_submission_status",
                spec_job.get("hardware_submission_status"),
                candidate.get("hardware_submission_status"),
            ),
            (
                "artifact_evidence",
                expected_artifact_evidence,
                artifact_evidence_summary(candidate.get("artifact_evidence")),
            ),
            (
                "simulator_backend_results",
                expected_backend_results,
                list_or_empty(candidate.get("simulator_backend_results")),
            ),
        )
        for field, expected, recorded in comparisons:
            if recorded != expected:
                mismatches.append({
                    "field": field,
                    "expected": expected,
                    "recorded": recorded,
                })
        if mismatches:
            row_mismatches.append({
                "job_id": item_id,
                "mismatches": mismatches,
            })

    ready_count = sum(
        1 for job in candidate_jobs if job.get("submission_status") == READY_STATUS
    )
    submitted_count = sum(
        1 for job in candidate_jobs
        if job.get("submission_status") == SUBMITTED_STATUS
    )
    blocked_count = len(candidate_jobs) - ready_count - submitted_count
    packet_candidate_count = submission_packet.get("hardware_candidate_job_count")
    packet_ready_count = submission_packet.get("ready_candidate_count")
    packet_blocked_count = submission_packet.get("blocked_candidate_count")
    packet_submitted_count = submission_packet.get("submitted_candidate_count")
    packet_hardware_submitted = submission_packet.get(
        "hardware_submitted_job_count")
    result_hardware_submitted = job_results.get("hardware_submitted_job_count")

    count_mismatches = []
    if packet_candidate_count != len(spec_ids):
        count_mismatches.append("hardware_candidate_job_count")
    if packet_ready_count != ready_count:
        count_mismatches.append("ready_candidate_count")
    if packet_blocked_count != blocked_count:
        count_mismatches.append("blocked_candidate_count")
    if packet_submitted_count != submitted_count:
        count_mismatches.append("submitted_candidate_count")
    if packet_hardware_submitted != result_hardware_submitted:
        count_mismatches.append("hardware_submitted_job_count")

    schema_mismatches = []
    if submission_packet.get("schema") != SUBMISSION_PACKET_SCHEMA:
        schema_mismatches.append("schema")
    if submission_packet.get("source_schema") != JOB_SPECS_SCHEMA:
        schema_mismatches.append("source_schema")
    if submission_packet.get("results_schema") != JOB_RESULTS_SCHEMA:
        schema_mismatches.append("results_schema")
    if job_specs.get("schema") != JOB_SPECS_SCHEMA:
        schema_mismatches.append("job_specs_schema")
    if job_results.get("schema") != JOB_RESULTS_SCHEMA:
        schema_mismatches.append("job_results_schema")

    mismatch_count = (
        len(schema_mismatches) +
        len(count_mismatches) +
        len(missing_candidate_ids) +
        len(unexpected_candidate_ids) +
        len(duplicate_spec_ids) +
        len(duplicate_candidate_ids) +
        invalid_spec_count +
        invalid_candidate_count +
        sum(len(row["mismatches"]) for row in row_mismatches)
    )
    recorded = (
        not schema_mismatches and
        bool(spec_ids) and
        isinstance(submission_packet.get("candidate_jobs"), list)
    )
    return {
        "recorded": recorded,
        "spec_hardware_candidate_count": len(spec_ids),
        "packet_hardware_candidate_count": packet_candidate_count,
        "packet_candidate_job_count": len(candidate_jobs),
        "ready_candidate_count": packet_ready_count,
        "actual_ready_candidate_count": ready_count,
        "blocked_candidate_count": packet_blocked_count,
        "actual_blocked_candidate_count": blocked_count,
        "submitted_candidate_count": packet_submitted_count,
        "actual_submitted_candidate_count": submitted_count,
        "hardware_submitted_job_count": packet_hardware_submitted,
        "result_hardware_submitted_job_count": result_hardware_submitted,
        "invalid_spec_candidate_count": invalid_spec_count,
        "invalid_packet_candidate_count": invalid_candidate_count,
        "duplicate_spec_candidate_ids": duplicate_spec_ids,
        "duplicate_packet_candidate_ids": duplicate_candidate_ids,
        "missing_candidate_job_ids": missing_candidate_ids,
        "unexpected_candidate_job_ids": unexpected_candidate_ids,
        "schema_mismatches": schema_mismatches,
        "count_mismatches": count_mismatches,
        "row_mismatches": row_mismatches,
        "row_mismatch_job_ids": sorted(
            row["job_id"] for row in row_mismatches),
        "mismatch_count": mismatch_count,
        "passed": recorded and mismatch_count == 0,
    }
