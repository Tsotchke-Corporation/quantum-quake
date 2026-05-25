#!/usr/bin/env python3
"""Consistency audit for Moonlab hardware record templates."""

from __future__ import annotations

from typing import Any


SUBMISSION_PACKET_SCHEMA = "qge.moonlab_submission_packet.v0"
HARDWARE_TEMPLATE_SCHEMA = "qge.moonlab_hardware_record_template.v0"
HARDWARE_RECORD_SCHEMA = "qge.moonlab_hardware_record.v0"


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def candidate_jobs_by_id(
    submission_packet: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for job in list_or_empty(submission_packet.get("candidate_jobs")):
        if not isinstance(job, dict):
            continue
        job_id = job.get("job_id")
        if isinstance(job_id, str) and job_id:
            indexed[job_id] = job
    return indexed


def expected_record_for_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    resource = dict_or_empty(candidate.get("resource"))
    shots = resource.get("shots")
    return {
        "schema": HARDWARE_RECORD_SCHEMA,
        "job_id": candidate.get("job_id"),
        "candidate_digest": candidate.get("candidate_digest"),
        "backend_kind": "moonlab_hardware",
        "status": "completed",
        "shot_schedule.shots": shots,
        "observations.shots": shots,
        "hardware_quantum_advantage_claimed": False,
        "whole_game_hardware_execution_claimed": False,
        "dense_70000_qubit_state_claimed": False,
    }


def observed_record_fields(record: dict[str, Any]) -> dict[str, Any]:
    shot_schedule = dict_or_empty(record.get("shot_schedule"))
    observations = dict_or_empty(record.get("observations"))
    return {
        "schema": record.get("schema"),
        "job_id": record.get("job_id"),
        "candidate_digest": record.get("candidate_digest"),
        "backend_kind": record.get("backend_kind"),
        "status": record.get("status"),
        "shot_schedule.shots": shot_schedule.get("shots"),
        "observations.shots": observations.get("shots"),
        "hardware_quantum_advantage_claimed": record.get(
            "hardware_quantum_advantage_claimed"),
        "whole_game_hardware_execution_claimed": record.get(
            "whole_game_hardware_execution_claimed"),
        "dense_70000_qubit_state_claimed": record.get(
            "dense_70000_qubit_state_claimed"),
    }


def hardware_record_template_audit(
    submission_packet: dict[str, Any],
    hardware_record_template: dict[str, Any],
) -> dict[str, Any]:
    template = dict_or_empty(hardware_record_template)
    packet = dict_or_empty(submission_packet)
    template_job_id = template.get("job_id")
    candidates = candidate_jobs_by_id(packet)
    candidate = (
        candidates.get(template_job_id)
        if isinstance(template_job_id, str)
        else None
    )

    schema_mismatches = []
    if packet.get("schema") != SUBMISSION_PACKET_SCHEMA:
        schema_mismatches.append("submission_packet_schema")
    if template.get("schema") != HARDWARE_TEMPLATE_SCHEMA:
        schema_mismatches.append("hardware_record_template_schema")
    if template.get("record_schema") != HARDWARE_RECORD_SCHEMA:
        schema_mismatches.append("hardware_record_schema")

    source = dict_or_empty(template.get("source_submission_packet"))
    source_mismatches = []
    source_comparisons = (
        ("candidate_count", packet.get("hardware_candidate_job_count")),
        ("job_specs", packet.get("job_specs")),
        ("job_results", packet.get("job_results")),
    )
    for field, expected in source_comparisons:
        if source.get(field) != expected:
            source_mismatches.append(field)

    row_mismatches = []
    if candidate is None:
        if template_job_id is None:
            row_mismatches.append({
                "field": "job_id",
                "expected": sorted(candidates.keys()),
                "recorded": None,
            })
        else:
            row_mismatches.append({
                "field": "job_id",
                "expected": sorted(candidates.keys()),
                "recorded": template_job_id,
            })
    else:
        comparisons = (
            ("candidate_digest", candidate.get("candidate_digest"),
             template.get("candidate_digest")),
            ("domain", candidate.get("domain"), template.get("domain")),
            ("kind", candidate.get("kind"), template.get("kind")),
            ("backend_kind", "moonlab_hardware", template.get("backend_kind")),
            (
                "required_artifacts",
                dict_or_empty(candidate.get("required_artifacts")),
                dict_or_empty(template.get("required_artifacts")),
            ),
            (
                "artifact_evidence",
                artifact_evidence_summary(candidate.get("artifact_evidence")),
                artifact_evidence_summary(template.get("artifact_evidence")),
            ),
            (
                "resource",
                dict_or_empty(candidate.get("resource")),
                dict_or_empty(template.get("resource")),
            ),
        )
        for field, expected, recorded in comparisons:
            if recorded != expected:
                row_mismatches.append({
                    "field": field,
                    "expected": expected,
                    "recorded": recorded,
                })
        expected_record = expected_record_for_candidate(candidate)
        observed_record = observed_record_fields(dict_or_empty(
            template.get("record")))
        for field, expected in expected_record.items():
            recorded = observed_record.get(field)
            if recorded != expected:
                row_mismatches.append({
                    "field": f"record.{field}",
                    "expected": expected,
                    "recorded": recorded,
                })

    validation_contract = dict_or_empty(template.get("validation_contract"))
    validation_contract_present = bool(validation_contract)
    mismatch_count = (
        len(schema_mismatches) +
        len(source_mismatches) +
        len(row_mismatches) +
        (0 if validation_contract_present else 1)
    )
    recorded = (
        not schema_mismatches and
        isinstance(template_job_id, str) and
        bool(template_job_id) and
        bool(candidates)
    )
    return {
        "recorded": recorded,
        "template_job_id": template_job_id,
        "template_candidate_digest": template.get("candidate_digest"),
        "candidate_job_count": len(candidates),
        "candidate_job_ids": sorted(candidates.keys()),
        "candidate_found": candidate is not None,
        "schema_mismatches": schema_mismatches,
        "source_mismatches": source_mismatches,
        "row_mismatches": row_mismatches,
        "row_mismatch_count": len(row_mismatches),
        "validation_contract_present": validation_contract_present,
        "validation_contract_keys": sorted(validation_contract.keys()),
        "mismatch_count": mismatch_count,
        "passed": recorded and mismatch_count == 0,
    }
