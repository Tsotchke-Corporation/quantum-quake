#!/usr/bin/env python3
"""Audit Moonlab hardware submission scope against source ledgers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_moonlab_submission_bundle


SUBMISSION_BUNDLE_SCHEMA = "qge.moonlab_submission_bundle.v0"
HARDWARE_SCOPE_SCHEMA = "qge.moonlab_hardware_submission_scope.v0"


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def path_or_none(value: str | None) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    return Path(value)


def compare_fields(
    expected: dict[str, Any],
    recorded: dict[str, Any],
    fields: tuple[str, ...],
) -> list[str]:
    return [
        field for field in fields
        if recorded.get(field) != expected.get(field)
    ]


def hardware_submission_scope_audit(
    submission_packet: dict[str, Any],
    submission_bundle: dict[str, Any],
    hardware_record_template: dict[str, Any],
    hardware_submission_scope: dict[str, Any],
    *,
    packet_path: str | None = None,
    bundle_path: str | None = None,
    hardware_template_path: str | None = None,
) -> dict[str, Any]:
    packet = dict_or_empty(submission_packet)
    recorded_bundle = dict_or_empty(submission_bundle)
    template = dict_or_empty(hardware_record_template)
    recorded_scope = dict_or_empty(hardware_submission_scope)

    expected_bundle = qge_moonlab_submission_bundle.build_submission_bundle(
        packet,
        packet_path=path_or_none(packet_path),
    )
    expected_scope = qge_moonlab_submission_bundle.build_hardware_submission_scope(
        packet,
        expected_bundle,
        template,
        packet_path=path_or_none(packet_path),
        bundle_path=path_or_none(bundle_path),
        hardware_template_path=path_or_none(hardware_template_path),
    )

    bundle_fields = (
        "schema",
        "source_schema",
        "submission_packet",
        "status",
        "hardware_candidate_job_count",
        "ready_for_control_plane_submission_count",
        "calibration_payload_ready_count",
        "oracle_kernel_ready_count",
        "qae_observation_ready_count",
        "grover_schedule_ready_count",
        "transpilation_required_count",
        "missing_artifact_candidate_count",
        "hardware_submission_directly_executable",
        "control_plane_payload_directly_executable",
        "oracle_kernel_directly_executable",
        "qae_observation_directly_executable",
        "grover_schedule_directly_executable",
        "moonlab_control_plane_requirements",
        "candidate_jobs",
        "claim_posture",
        "limits",
    )
    scope_fields = (
        "schema",
        "status",
        "scope",
        "source_submission_packet",
        "source_submission_bundle",
        "source_hardware_record_template",
        "hardware_submission_scope_ready",
        "hardware_candidate_job_count",
        "ready_for_control_plane_submission_count",
        "hardware_submission_directly_executable",
        "grover_schedule_directly_executable",
        "candidate_job_ids",
        "candidate_digests",
        "hardware_record_template_job_id",
        "hardware_record_template_candidate_digest",
        "hardware_record_schema",
        "hardware_record_validation_contract",
        "readiness_checks",
        "passing_check_count",
        "attention_check_count",
        "out_of_scope",
        "claim_posture",
        "limits",
    )

    bundle_mismatches = compare_fields(
        expected_bundle,
        recorded_bundle,
        bundle_fields,
    )
    scope_mismatches = compare_fields(
        expected_scope,
        recorded_scope,
        scope_fields,
    )
    schema_mismatches = []
    if recorded_bundle.get("schema") != SUBMISSION_BUNDLE_SCHEMA:
        schema_mismatches.append("submission_bundle_schema")
    if recorded_scope.get("schema") != HARDWARE_SCOPE_SCHEMA:
        schema_mismatches.append("hardware_submission_scope_schema")

    mismatch_count = (
        len(bundle_mismatches) +
        len(scope_mismatches) +
        len(schema_mismatches)
    )
    recorded = (
        recorded_bundle.get("schema") == SUBMISSION_BUNDLE_SCHEMA and
        recorded_scope.get("schema") == HARDWARE_SCOPE_SCHEMA
    )
    return {
        "recorded": recorded,
        "expected_bundle_status": expected_bundle.get("status"),
        "recorded_bundle_status": recorded_bundle.get("status"),
        "expected_scope_status": expected_scope.get("status"),
        "recorded_scope_status": recorded_scope.get("status"),
        "expected_scope_ready": expected_scope.get(
            "hardware_submission_scope_ready"),
        "recorded_scope_ready": recorded_scope.get(
            "hardware_submission_scope_ready"),
        "expected_candidate_job_count": expected_scope.get(
            "hardware_candidate_job_count"),
        "recorded_candidate_job_count": recorded_scope.get(
            "hardware_candidate_job_count"),
        "expected_passing_check_count": expected_scope.get(
            "passing_check_count"),
        "recorded_passing_check_count": recorded_scope.get(
            "passing_check_count"),
        "expected_attention_check_count": expected_scope.get(
            "attention_check_count"),
        "recorded_attention_check_count": recorded_scope.get(
            "attention_check_count"),
        "expected_candidate_job_ids": expected_scope.get(
            "candidate_job_ids"),
        "recorded_candidate_job_ids": recorded_scope.get(
            "candidate_job_ids"),
        "schema_mismatches": schema_mismatches,
        "submission_bundle_mismatches": bundle_mismatches,
        "hardware_submission_scope_mismatches": scope_mismatches,
        "mismatch_count": mismatch_count,
        "passed": recorded and mismatch_count == 0,
    }
