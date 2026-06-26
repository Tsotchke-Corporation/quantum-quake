#!/usr/bin/env python3
"""Operator handoff checklist for returned Moonlab hardware results.

The report is deliberately observational: it reads the submission packet,
job-results ledger, hardware-record template, and optional returned/downstream
artifacts, then reports the next missing fields or artifacts. It does not
ingest a result and never turns missing hardware evidence into a claim.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_moonlab_hardware_ingest  # noqa: E402
import qge_moonlab_hardware_result_audit  # noqa: E402


PACKET_SCHEMA = "qge.moonlab_submission_packet.v0"
JOB_RESULTS_SCHEMA = "qge.moonlab_job_results.v0"
TEMPLATE_SCHEMA = "qge.moonlab_hardware_record_template.v0"
RECORD_SCHEMA = "qge.moonlab_hardware_record.v0"
SCOPE_SCHEMA = "qge.moonlab_hardware_submission_scope.v0"
COMPARISON_SCHEMA = "qge.moonlab_hardware_comparison.v0"
ADVANTAGE_GATE_BACKEND = "qge_hardware_advantage_gate"
READY_CANDIDATE_STATUSES = {
    "ready_for_hardware_submission_metadata",
    "hardware_submission_recorded",
}
FORBIDDEN_CLAIM_FLAGS = (
    "hardware_quantum_advantage_claimed",
    "whole_game_hardware_execution_claimed",
    "dense_70000_qubit_state_claimed",
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def load_reported_json(
    path: Path | None,
    *,
    label: str,
    expected_schema: str | None = None,
    required: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    info = {
        "label": label,
        "path": str(path) if path else None,
        "required": required,
        "exists": bool(path and path.is_file()),
        "schema": None,
        "expected_schema": expected_schema,
        "schema_ok": False if expected_schema else None,
        "load_error": None,
    }
    if path is None:
        if required:
            info["load_error"] = "path not provided"
        return {}, info
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        info["load_error"] = str(exc)
        return {}, info
    except json.JSONDecodeError as exc:
        info["load_error"] = str(exc)
        return {}, info
    if not isinstance(data, dict):
        info["load_error"] = "JSON root is not an object"
        return {}, info
    schema = data.get("schema")
    info["schema"] = schema
    if expected_schema:
        info["schema_ok"] = schema == expected_schema
    return data, info


def check(
    check_id: str,
    passed: bool,
    evidence: Any,
    blocker: str,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "pass" if passed else "blocked",
        "passed": bool(passed),
        "evidence": evidence,
        "blocker": "" if passed else blocker,
    }


def candidate_jobs_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for job in list_or_empty(packet.get("candidate_jobs")):
        if not isinstance(job, dict):
            continue
        job_id = job.get("job_id")
        if nonempty_string(job_id):
            indexed[str(job_id)] = job
    return indexed


def template_job_id(template: dict[str, Any]) -> str | None:
    value = template.get("job_id")
    if nonempty_string(value):
        return str(value)
    value = dict_or_empty(template.get("record")).get("job_id")
    return str(value) if nonempty_string(value) else None


def selected_candidate(
    packet: dict[str, Any],
    template: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    candidates = candidate_jobs_by_id(packet)
    wanted = template_job_id(template)
    mismatches = []
    if wanted:
        candidate = candidates.get(wanted, {})
        if not candidate:
            mismatches.append("template.job_id_not_in_submission_packet")
        return candidate, mismatches
    if len(candidates) == 1:
        return next(iter(candidates.values())), mismatches
    mismatches.append("template.job_id_missing")
    return {}, mismatches


def missing_template_record_fields(template: dict[str, Any]) -> list[str]:
    record = dict_or_empty(template.get("record"))
    shot_schedule = dict_or_empty(record.get("shot_schedule"))
    readout_metadata = dict_or_empty(record.get("readout_metadata"))
    observations = dict_or_empty(record.get("observations"))
    fields = []
    for field, value in (
        ("hardware_record.backend_id", record.get("backend_id")),
        ("hardware_record.run_id", record.get("run_id")),
        ("hardware_record.submitted_utc", record.get("submitted_utc")),
        ("hardware_record.completed_utc", record.get("completed_utc")),
        (
            "hardware_record.shot_schedule.batches",
            shot_schedule.get("batches"),
        ),
        (
            "hardware_record.shot_schedule.schedule_id",
            shot_schedule.get("schedule_id"),
        ),
        (
            "hardware_record.readout_metadata.shots_completed",
            readout_metadata.get("shots_completed"),
        ),
        (
            "hardware_record.readout_metadata.readout_format",
            readout_metadata.get("readout_format"),
        ),
        (
            "hardware_record.readout_metadata.mitigation",
            readout_metadata.get("mitigation"),
        ),
        (
            "hardware_record.observations.readout_error",
            observations.get("readout_error"),
        ),
    ):
        if value in (None, ""):
            fields.append(field)
    if not (
        finite_number(observations.get("mean_value")) or
        finite_number(observations.get("observed_value"))
    ):
        fields.append("hardware_record.observations.mean_value_or_observed_value")
    return sorted(fields)


def record_field_issues(
    packet: dict[str, Any],
    job_results: dict[str, Any],
    template: dict[str, Any],
    hardware_record: dict[str, Any],
) -> dict[str, Any]:
    missing: list[str] = []
    mismatches: list[str] = []
    overclaim_flags: list[str] = []
    candidate, candidate_mismatches = selected_candidate(packet, template)
    mismatches.extend(candidate_mismatches)

    def require_string(field: str, value: Any) -> None:
        if not nonempty_string(value):
            missing.append(field)

    def require_positive(field: str, value: Any) -> None:
        if not positive_int(value):
            missing.append(field)

    def require_nonnegative(field: str, value: Any) -> None:
        if not nonnegative_finite_number(value):
            missing.append(field)

    require_string("hardware_record.schema", hardware_record.get("schema"))
    if (
        nonempty_string(hardware_record.get("schema")) and
        hardware_record.get("schema") != RECORD_SCHEMA
    ):
        mismatches.append("hardware_record.schema")
    require_string("hardware_record.job_id", hardware_record.get("job_id"))
    require_string(
        "hardware_record.candidate_digest",
        hardware_record.get("candidate_digest"),
    )
    require_string("hardware_record.backend_id", hardware_record.get("backend_id"))
    require_string("hardware_record.run_id", hardware_record.get("run_id"))
    require_string(
        "hardware_record.submitted_utc",
        hardware_record.get("submitted_utc"),
    )
    require_string(
        "hardware_record.completed_utc",
        hardware_record.get("completed_utc"),
    )
    if hardware_record.get("backend_kind") != "moonlab_hardware":
        mismatches.append("hardware_record.backend_kind")
    if hardware_record.get("status") != "completed":
        mismatches.append("hardware_record.status")

    if candidate:
        if hardware_record.get("job_id") != candidate.get("job_id"):
            mismatches.append("hardware_record.job_id")
        if hardware_record.get("candidate_digest") != candidate.get(
            "candidate_digest"
        ):
            mismatches.append("hardware_record.candidate_digest")
        if list_or_empty(candidate.get("missing_required_artifacts")):
            mismatches.append(
                "submission_packet.candidate.missing_required_artifacts"
            )
        if candidate.get("submission_status") not in READY_CANDIDATE_STATUSES:
            mismatches.append("submission_packet.candidate.submission_status")

    shot_schedule = dict_or_empty(hardware_record.get("shot_schedule"))
    readout_metadata = dict_or_empty(hardware_record.get("readout_metadata"))
    observations = dict_or_empty(hardware_record.get("observations"))
    if not shot_schedule:
        missing.append("hardware_record.shot_schedule")
    if not readout_metadata:
        missing.append("hardware_record.readout_metadata")
    if not observations:
        missing.append("hardware_record.observations")

    scheduled_shots = shot_schedule.get("shots")
    completed_shots = readout_metadata.get("shots_completed")
    observed_shots = observations.get("shots")
    require_positive("hardware_record.shot_schedule.shots", scheduled_shots)
    require_positive("hardware_record.shot_schedule.batches",
                     shot_schedule.get("batches"))
    require_string("hardware_record.shot_schedule.schedule_id",
                   shot_schedule.get("schedule_id"))
    require_positive("hardware_record.readout_metadata.shots_completed",
                     completed_shots)
    require_string("hardware_record.readout_metadata.readout_format",
                   readout_metadata.get("readout_format"))
    require_string("hardware_record.readout_metadata.mitigation",
                   readout_metadata.get("mitigation"))
    require_positive("hardware_record.observations.shots", observed_shots)
    if not (
        finite_number(observations.get("mean_value")) or
        finite_number(observations.get("observed_value"))
    ):
        missing.append("hardware_record.observations.mean_value_or_observed_value")
    require_nonnegative(
        "hardware_record.observations.readout_error",
        observations.get("readout_error"),
    )

    if positive_int(scheduled_shots):
        resource_shots = dict_or_empty(candidate.get("resource")).get("shots")
        if positive_int(resource_shots) and scheduled_shots != resource_shots:
            mismatches.append("hardware_record.shot_schedule.shots")
    if (
        positive_int(scheduled_shots) and
        positive_int(completed_shots) and
        scheduled_shots != completed_shots
    ):
        mismatches.append("hardware_record.readout_metadata.shots_completed")
    if (
        positive_int(completed_shots) and
        positive_int(observed_shots) and
        completed_shots != observed_shots
    ):
        mismatches.append("hardware_record.observations.shots")

    for flag in FORBIDDEN_CLAIM_FLAGS:
        if hardware_record.get(flag) is True:
            overclaim_flags.append(f"hardware_record.{flag}")

    validation_error = None
    if not missing and not mismatches and not overclaim_flags:
        try:
            qge_moonlab_hardware_ingest.validate_hardware_record(
                packet,
                job_results,
                hardware_record,
            )
        except (ValueError, KeyError, IndexError) as exc:
            validation_error = str(exc)
            mismatches.append("hardware_record.ingest_validation")

    return {
        "missing_record_fields": sorted(set(missing)),
        "record_mismatches": sorted(set(mismatches)),
        "overclaim_flags": sorted(overclaim_flags),
        "validation_error": validation_error,
    }


def comparison_ok(
    comparison: dict[str, Any],
    *,
    candidate: dict[str, Any],
    hardware_record: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    record_digest = None
    if hardware_record.get("schema") == RECORD_SCHEMA:
        record_digest = qge_moonlab_hardware_ingest.stable_json_digest(
            hardware_record
        )
    claim_posture = dict_or_empty(comparison.get("claim_posture"))
    forbidden = [
        flag for flag in FORBIDDEN_CLAIM_FLAGS if claim_posture.get(flag) is True
    ]
    mismatches = []
    if comparison.get("schema") != COMPARISON_SCHEMA:
        mismatches.append("schema")
    if comparison.get("status") != "hardware_result_recorded":
        mismatches.append("status")
    if comparison.get("backend_kind") != "moonlab_hardware":
        mismatches.append("backend_kind")
    if candidate and comparison.get("job_id") != candidate.get("job_id"):
        mismatches.append("job_id")
    if candidate and comparison.get("candidate_digest") != candidate.get(
        "candidate_digest"
    ):
        mismatches.append("candidate_digest")
    if record_digest and comparison.get("hardware_record_sha256") != record_digest:
        mismatches.append("hardware_record_sha256")
    return not mismatches and not forbidden, {
        "mismatches": sorted(mismatches),
        "overclaim_flags": forbidden,
        "hardware_record_sha256": comparison.get("hardware_record_sha256"),
        "expected_hardware_record_sha256": record_digest,
    }


def artifact(label: str, reason: str) -> dict[str, str]:
    return {"artifact": label, "reason": reason}


def build_next_commands(
    *,
    packet_path: Path,
    job_results_path: Path,
    hardware_record_path: Path | None,
    hardware_scope_path: Path | None,
    ready_for_hardware_ingest: bool,
    ready_for_strict_audit: bool,
    ready_for_advantage_gate: bool,
) -> list[str]:
    commands = []
    if ready_for_hardware_ingest and hardware_record_path:
        commands.append(
            "tools/qge_moonlab_hardware_ingest.py "
            f"{packet_path} --job-results {job_results_path} "
            f"--hardware-record {hardware_record_path} "
            "--out <qge_moonlab_job_results.hardware.json> "
            "--comparison-out <qge_moonlab_hardware_comparison.json> "
            "--icc-out <qge_moonlab_hardware_icc_evidence.json>"
        )
    if ready_for_strict_audit:
        scope_flag = (
            f" --hardware-scope {hardware_scope_path}"
            if hardware_scope_path else ""
        )
        commands.append(
            "tools/qge_moonlab_hardware_result_audit.py "
            f"{packet_path} {job_results_path}{scope_flag} "
            "--out <qge_moonlab_hardware_result_audit.json> "
            "--icc-out <qge_moonlab_hardware_result_audit_icc.json> "
            "--strict-real-campaign --fail-on-mismatch"
        )
    if ready_for_advantage_gate:
        commands.append(
            "tools/qge_hardware_advantage_gate.py "
            "--advantage-metrics <qge_advantage_metrics.json> "
            f"--job-results {job_results_path} "
            "--hardware-comparison <qge_moonlab_hardware_comparison.json> "
            "--hardware-result-audit <qge_moonlab_hardware_result_audit.json> "
            "--advantage-metrics-audit <qge_advantage_metrics_audit.json> "
            "--claims <qge_claims.json> "
            "--out <qge_hardware_advantage_gate.json> "
            "--icc-out <qge_hardware_advantage_gate_icc.json>"
        )
    return commands


def build_handoff(
    submission_packet: dict[str, Any],
    job_results: dict[str, Any],
    hardware_template: dict[str, Any],
    *,
    hardware_record: dict[str, Any] | None = None,
    hardware_scope: dict[str, Any] | None = None,
    hardware_comparison: dict[str, Any] | None = None,
    hardware_result_audit: dict[str, Any] | None = None,
    advantage_gate: dict[str, Any] | None = None,
    input_reports: list[dict[str, Any]] | None = None,
    packet_path: Path | None = None,
    job_results_path: Path | None = None,
    hardware_record_path: Path | None = None,
    hardware_scope_path: Path | None = None,
) -> dict[str, Any]:
    packet = dict_or_empty(submission_packet)
    results = dict_or_empty(job_results)
    template = dict_or_empty(hardware_template)
    record = dict_or_empty(hardware_record)
    scope = dict_or_empty(hardware_scope)
    comparison = dict_or_empty(hardware_comparison)
    audit_file = dict_or_empty(hardware_result_audit)
    gate = dict_or_empty(advantage_gate)
    inputs = input_reports or []
    missing_required_inputs = [
        item for item in inputs
        if item.get("required") and
        (item.get("load_error") or item.get("schema_ok") is False)
    ]

    candidate, candidate_mismatches = selected_candidate(packet, template)
    candidate_missing_artifacts = list_or_empty(
        candidate.get("missing_required_artifacts"))
    candidate_ready = (
        bool(candidate) and
        not candidate_mismatches and
        not candidate_missing_artifacts and
        candidate.get("submission_status") in READY_CANDIDATE_STATUSES
    )
    record_present = bool(record)
    if record_present:
        record_issues = record_field_issues(packet, results, template, record)
    else:
        record_issues = {
            "missing_record_fields": missing_template_record_fields(template),
            "record_mismatches": [],
            "overclaim_flags": [],
            "validation_error": None,
        }
    record_complete = (
        record_present and
        not record_issues["missing_record_fields"] and
        not record_issues["record_mismatches"] and
        not record_issues["overclaim_flags"]
    )

    result_audit = {}
    if (
        packet.get("schema") == PACKET_SCHEMA and
        results.get("schema") == JOB_RESULTS_SCHEMA
    ):
        result_audit = (
            qge_moonlab_hardware_result_audit.hardware_result_ledger_audit(
                packet,
                results,
                scope if scope else None,
                strict_real_campaign=True,
            )
        )
    hardware_result_recorded = result_audit.get("passed") is True
    comparison_passed, comparison_evidence = comparison_ok(
        comparison,
        candidate=candidate,
        hardware_record=record,
    ) if comparison else (False, {"mismatches": ["missing"]})
    audit_file_passed = (
        audit_file.get("passed") is True and
        audit_file.get("strict_real_campaign") is True and
        int(audit_file.get("hardware_result_job_count", 0) or 0) > 0 and
        int(audit_file.get("completed_hardware_result_count", 0) or 0) > 0 and
        list_or_empty(audit_file.get("strict_real_campaign_mismatches")) == []
    )
    gate_ready = (
        gate.get("runtime_backend") == ADVANTAGE_GATE_BACKEND and
        gate.get("ready") is True and
        gate.get("bounded_qae_query_scaling_claim_allowed") is True and
        gate.get("hardware_quantum_advantage_claim_allowed") is False and
        gate.get("whole_game_hardware_execution_claim_allowed") is False
    )
    ready_for_hardware_ingest = (
        not missing_required_inputs and candidate_ready and record_complete and
        not hardware_result_recorded
    )
    ready_for_strict_audit = (
        not missing_required_inputs and candidate_ready and record_complete and
        hardware_result_recorded and not audit_file_passed
    )
    ready_for_advantage_gate = (
        not missing_required_inputs and candidate_ready and record_complete and
        hardware_result_recorded and comparison_passed and audit_file_passed and
        not gate_ready
    )

    if missing_required_inputs:
        status = "blocked_missing_required_inputs"
    elif not candidate_ready:
        status = "blocked_submission_candidate_not_ready"
    elif not record_present:
        status = "blocked_waiting_for_real_moonlab_hardware_record"
    elif not record_complete:
        status = "blocked_hardware_record_incomplete"
    elif ready_for_hardware_ingest:
        status = "ready_for_hardware_ingest"
    elif not hardware_result_recorded:
        status = "blocked_hardware_result_not_recorded"
    elif not comparison_passed:
        status = "blocked_missing_hardware_comparison"
    elif ready_for_strict_audit:
        status = "ready_for_strict_hardware_result_audit"
    elif ready_for_advantage_gate:
        status = "ready_for_hardware_advantage_gate"
    elif gate_ready:
        status = "handoff_complete_gate_ready"
    else:
        status = "blocked_hardware_advantage_gate_not_ready"

    needed = []
    for item in missing_required_inputs:
        needed.append(artifact(item["label"], "required input is missing or stale"))
    for missing in candidate_missing_artifacts:
        needed.append(artifact(str(missing), "candidate required artifact missing"))
    if not record_present:
        needed.append(artifact(
            "qge.moonlab_hardware_record.v0",
            "fill from returned Moonlab backend output before ingest",
        ))
    if record_present and not record_complete:
        for field in record_issues["missing_record_fields"]:
            needed.append(artifact(field, "hardware record field is required"))
        for field in record_issues["record_mismatches"]:
            needed.append(artifact(field, "hardware record does not match packet"))
        for flag in record_issues["overclaim_flags"]:
            needed.append(artifact(flag, "forbidden claim flag must stay false"))
    if ready_for_hardware_ingest:
        needed.extend([
            artifact("qge_moonlab_job_results.hardware.json",
                     "write ingested job results from the real record"),
            artifact("qge_moonlab_hardware_comparison.json",
                     "write hardware-vs-simulator comparison during ingest"),
            artifact("qge_moonlab_hardware_icc_evidence.json",
                     "write ingest ICC evidence during ingest"),
        ])
    if hardware_result_recorded and not audit_file_passed:
        needed.append(artifact(
            "qge_moonlab_hardware_result_audit.json",
            "strict real-campaign audit must pass on ingested results",
        ))
    if hardware_result_recorded and not comparison_passed:
        needed.append(artifact(
            "qge_moonlab_hardware_comparison.json",
            "comparison must match the audited hardware row",
        ))
    if ready_for_advantage_gate:
        needed.append(artifact(
            "qge_hardware_advantage_gate.json",
            "run fail-closed bounded QAE advantage gate",
        ))

    packet_path = packet_path or Path("<qge_moonlab_submission_packet.json>")
    job_results_path = job_results_path or Path("<qge_moonlab_job_results.json>")
    checks = [
        check(
            "submission_packet_loaded",
            packet.get("schema") == PACKET_SCHEMA,
            {"schema": packet.get("schema")},
            "submission packet is missing or has the wrong schema",
        ),
        check(
            "job_results_loaded",
            results.get("schema") == JOB_RESULTS_SCHEMA,
            {"schema": results.get("schema")},
            "job results are missing or have the wrong schema",
        ),
        check(
            "hardware_template_loaded",
            template.get("schema") == TEMPLATE_SCHEMA,
            {"schema": template.get("schema")},
            "hardware record template is missing or has the wrong schema",
        ),
        check(
            "candidate_ready_for_hardware_return",
            candidate_ready,
            {
                "job_id": candidate.get("job_id"),
                "submission_status": candidate.get("submission_status"),
                "missing_required_artifacts": candidate_missing_artifacts,
                "mismatches": candidate_mismatches,
            },
            "submission packet candidate is not ready for a returned record",
        ),
        check(
            "hardware_record_present",
            record_present,
            {"path": str(hardware_record_path) if hardware_record_path else None},
            "real returned Moonlab hardware record has not been provided",
        ),
        check(
            "hardware_record_fields_complete",
            record_complete,
            record_issues,
            "hardware record is incomplete, mismatched, or overclaiming",
        ),
        check(
            "hardware_result_recorded_in_job_results",
            hardware_result_recorded,
            result_audit,
            "job results do not contain a strict audited Moonlab hardware row",
        ),
        check(
            "hardware_comparison_available",
            comparison_passed,
            comparison_evidence,
            "hardware comparison is missing or does not match the record",
        ),
        check(
            "strict_hardware_result_audit_artifact_passed",
            audit_file_passed,
            {
                "runtime_backend": audit_file.get("runtime_backend"),
                "passed": audit_file.get("passed"),
                "strict_real_campaign": audit_file.get(
                    "strict_real_campaign"),
                "hardware_result_job_count": audit_file.get(
                    "hardware_result_job_count"),
                "completed_hardware_result_count": audit_file.get(
                    "completed_hardware_result_count"),
            },
            "strict hardware-result audit artifact has not passed",
        ),
        check(
            "hardware_advantage_gate_ready",
            gate_ready,
            {
                "runtime_backend": gate.get("runtime_backend"),
                "ready": gate.get("ready"),
                "bounded_qae_query_scaling_claim_allowed": gate.get(
                    "bounded_qae_query_scaling_claim_allowed"),
            },
            "bounded advantage gate is not ready",
        ),
    ]
    ready = status == "handoff_complete_gate_ready"
    return {
        "schema": "qge.moonlab_hardware_return_handoff.v0",
        "runtime_backend": "qge_moonlab_hardware_return_handoff",
        "status": status,
        "ready": ready,
        "ready_for_hardware_ingest": ready_for_hardware_ingest,
        "ready_for_strict_hardware_result_audit": ready_for_strict_audit,
        "ready_for_hardware_advantage_gate": ready_for_advantage_gate,
        "input_artifacts": inputs,
        "candidate": {
            "job_id": candidate.get("job_id"),
            "candidate_digest": candidate.get("candidate_digest"),
            "submission_status": candidate.get("submission_status"),
            "missing_required_artifacts": candidate_missing_artifacts,
            "ready_for_hardware_return": candidate_ready,
        },
        "missing_record_fields": record_issues["missing_record_fields"],
        "record_mismatches": record_issues["record_mismatches"],
        "overclaim_flags": record_issues["overclaim_flags"],
        "validation_error": record_issues["validation_error"],
        "artifacts_needed_next": needed,
        "next_commands": build_next_commands(
            packet_path=packet_path,
            job_results_path=job_results_path,
            hardware_record_path=hardware_record_path,
            hardware_scope_path=hardware_scope_path,
            ready_for_hardware_ingest=ready_for_hardware_ingest,
            ready_for_strict_audit=ready_for_strict_audit,
            ready_for_advantage_gate=ready_for_advantage_gate,
        ),
        "hardware_result_audit_preview": result_audit,
        "checks": checks,
        "failed_checks": [item for item in checks if not item["passed"]],
        "claim_posture": {
            "hardware_result_recorded": hardware_result_recorded,
            "bounded_qae_query_scaling_claim_allowed": gate_ready,
            "hardware_quantum_advantage_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "dense_70000_qubit_state_claimed": False,
        },
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# QGE Moonlab Hardware Return Handoff",
        "",
        f"- status: {report.get('status')}",
        f"- ready: {str(report.get('ready')).lower()}",
        "- hardware quantum advantage claimed: false",
        "- whole-game hardware execution claimed: false",
        "",
        "## Candidate",
        "",
        f"- job_id: {dict_or_empty(report.get('candidate')).get('job_id')}",
        "- ready_for_hardware_return: "
        f"{str(dict_or_empty(report.get('candidate')).get('ready_for_hardware_return')).lower()}",
        "",
        "## Missing Record Fields",
        "",
    ]
    missing = list_or_empty(report.get("missing_record_fields"))
    lines.extend(f"- {field}" for field in missing) if missing else lines.append("- none")
    lines.extend(["", "## Artifacts Needed Next", ""])
    needed = list_or_empty(report.get("artifacts_needed_next"))
    if needed:
        lines.extend(
            f"- {item.get('artifact')}: {item.get('reason')}"
            for item in needed
            if isinstance(item, dict)
        )
    else:
        lines.append("- none")
    lines.extend(["", "## Next Commands", ""])
    commands = list_or_empty(report.get("next_commands"))
    if commands:
        lines.extend(f"- `{command}`" for command in commands)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def build_icc_evidence(
    report: dict[str, Any],
    *,
    out_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    ready = report.get("ready") is True
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_moonlab_hardware_return_handoff",
        "completion_reason": (
            "qge_moonlab_hardware_return_handoff_ready"
            if ready else
            "qge_moonlab_hardware_return_handoff_blocked"
        ),
        "status": "success" if ready else "blocked",
        "moonlab_hardware_return_handoff_file": (
            str(out_path) if out_path else None),
        "moonlab_hardware_return_handoff_markdown_file": (
            str(markdown_path) if markdown_path else None),
        "handoff_status": report.get("status"),
        "ready_for_hardware_ingest": report.get("ready_for_hardware_ingest"),
        "ready_for_strict_hardware_result_audit": report.get(
            "ready_for_strict_hardware_result_audit"),
        "ready_for_hardware_advantage_gate": report.get(
            "ready_for_hardware_advantage_gate"),
        "missing_record_field_count": len(list_or_empty(
            report.get("missing_record_fields"))),
        "artifact_needed_count": len(list_or_empty(
            report.get("artifacts_needed_next"))),
        "failed_check_count": len(list_or_empty(report.get("failed_checks"))),
        "hardware_quantum_advantage_claimed": False,
        "whole_game_hardware_execution_claimed": False,
        "dense_70000_qubit_state_claimed": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission-packet", type=Path, required=True)
    parser.add_argument("--job-results", type=Path, required=True)
    parser.add_argument("--hardware-template", type=Path, required=True)
    parser.add_argument("--hardware-record", type=Path)
    parser.add_argument("--hardware-scope", type=Path)
    parser.add_argument("--hardware-comparison", type=Path)
    parser.add_argument("--hardware-result-audit", type=Path)
    parser.add_argument("--advantage-gate", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-out", type=Path)
    parser.add_argument("--fail-on-blocked", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    packet, packet_info = load_reported_json(
        args.submission_packet,
        label="moonlab_submission_packet",
        expected_schema=PACKET_SCHEMA,
        required=True,
    )
    results, results_info = load_reported_json(
        args.job_results,
        label="moonlab_job_results",
        expected_schema=JOB_RESULTS_SCHEMA,
        required=True,
    )
    template, template_info = load_reported_json(
        args.hardware_template,
        label="moonlab_hardware_record_template",
        expected_schema=TEMPLATE_SCHEMA,
        required=True,
    )
    record, record_info = load_reported_json(
        args.hardware_record,
        label="moonlab_hardware_record",
        expected_schema=RECORD_SCHEMA,
    )
    scope, scope_info = load_reported_json(
        args.hardware_scope,
        label="moonlab_hardware_submission_scope",
        expected_schema=SCOPE_SCHEMA,
    )
    comparison, comparison_info = load_reported_json(
        args.hardware_comparison,
        label="moonlab_hardware_comparison",
        expected_schema=COMPARISON_SCHEMA,
    )
    audit, audit_info = load_reported_json(
        args.hardware_result_audit,
        label="moonlab_hardware_result_audit",
    )
    gate, gate_info = load_reported_json(
        args.advantage_gate,
        label="qge_hardware_advantage_gate",
    )
    report = build_handoff(
        packet,
        results,
        template,
        hardware_record=record,
        hardware_scope=scope,
        hardware_comparison=comparison,
        hardware_result_audit=audit,
        advantage_gate=gate,
        input_reports=[
            packet_info,
            results_info,
            template_info,
            record_info,
            scope_info,
            comparison_info,
            audit_info,
            gate_info,
        ],
        packet_path=args.submission_packet,
        job_results_path=args.job_results,
        hardware_record_path=args.hardware_record,
        hardware_scope_path=args.hardware_scope,
    )
    try:
        write_json(args.out, report)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(report), encoding="utf-8")
        if args.icc_out:
            write_json(
                args.icc_out,
                build_icc_evidence(
                    report,
                    out_path=args.out,
                    markdown_path=args.markdown,
                ),
            )
    except OSError as exc:
        print(f"qge_moonlab_hardware_return_handoff: {exc}", file=sys.stderr)
        return 1

    print(f"QGE_MOONLAB_HARDWARE_RETURN_HANDOFF {args.out}")
    if args.markdown:
        print(f"QGE_MOONLAB_HARDWARE_RETURN_HANDOFF_MARKDOWN {args.markdown}")
    if args.icc_out:
        print(f"QGE_MOONLAB_HARDWARE_RETURN_HANDOFF_ICC {args.icc_out}")
    if args.fail_on_blocked and not report.get("ready"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
