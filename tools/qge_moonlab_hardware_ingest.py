#!/usr/bin/env python3
"""Ingest a real Moonlab hardware result into QGE job evidence.

This tool intentionally updates only bounded hardware-candidate jobs. It does
not turn simulator/native replay evidence into a full-game hardware claim.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence


NO_SUBMISSION_STATUSES = {
    None,
    "not_submitted",
    "not_a_quantum_hardware_job",
    "not_applicable_full_frame_hardware_execution_not_claimed",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def stable_json_digest(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode(
        "utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def require_schema(data: dict[str, Any], schema: str, label: str) -> None:
    if data.get("schema") != schema:
        raise ValueError(f"{label} is not {schema}")


def require_nonempty_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"hardware record is missing {key}")
    return value


def hardware_claim_flag_enabled(data: dict[str, Any]) -> bool:
    for key in (
        "hardware_quantum_advantage_claimed",
        "whole_game_hardware_execution_claimed",
        "dense_70000_qubit_state_claimed",
    ):
        if bool(data.get(key)):
            return True
    return False


def candidate_jobs_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for job in list_or_empty(packet.get("candidate_jobs")):
        if not isinstance(job, dict):
            continue
        job_id = job.get("job_id")
        if isinstance(job_id, str):
            indexed[job_id] = job
    return indexed


def result_jobs_by_id(results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for job in list_or_empty(results.get("jobs")):
        if not isinstance(job, dict):
            continue
        job_id = job.get("job_id")
        if isinstance(job_id, str):
            indexed[job_id] = job
    return indexed


def validate_hardware_record(
    submission_packet: dict[str, Any],
    job_results: dict[str, Any],
    hardware_record: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    require_schema(
        submission_packet, "qge.moonlab_submission_packet.v0",
        "submission packet")
    require_schema(job_results, "qge.moonlab_job_results.v0", "job results")
    require_schema(
        hardware_record, "qge.moonlab_hardware_record.v0", "hardware record")
    if hardware_claim_flag_enabled(hardware_record):
        raise ValueError(
            "hardware record may not claim advantage, dense-state execution, "
            "or whole-game hardware execution")

    job_id = require_nonempty_string(hardware_record, "job_id")
    backend_id = require_nonempty_string(hardware_record, "backend_id")
    backend_kind = hardware_record.get("backend_kind")
    if backend_kind != "moonlab_hardware":
        raise ValueError("hardware record backend_kind must be moonlab_hardware")
    if hardware_record.get("status") != "completed":
        raise ValueError("hardware record status must be completed")

    candidate = candidate_jobs_by_id(submission_packet).get(job_id)
    if candidate is None:
        raise ValueError(f"hardware record job_id {job_id!r} is not in packet")
    result_job = result_jobs_by_id(job_results).get(job_id)
    if result_job is None:
        raise ValueError(f"hardware record job_id {job_id!r} is not in results")

    missing = list_or_empty(candidate.get("missing_required_artifacts"))
    if missing:
        raise ValueError(
            f"hardware candidate has missing required artifacts: {missing}")
    if candidate.get("submission_status") not in (
        "ready_for_hardware_submission_metadata",
        "hardware_submission_recorded",
    ):
        raise ValueError("hardware candidate is not ready for ingestion")

    candidate_digest = require_nonempty_string(hardware_record,
                                               "candidate_digest")
    if candidate_digest != candidate.get("candidate_digest"):
        raise ValueError("hardware record candidate_digest does not match packet")

    if not dict_or_empty(hardware_record.get("shot_schedule")):
        raise ValueError("hardware record is missing shot_schedule")
    if not dict_or_empty(hardware_record.get("readout_metadata")):
        raise ValueError("hardware record is missing readout_metadata")
    if not dict_or_empty(hardware_record.get("observations")):
        raise ValueError("hardware record is missing observations")
    if not backend_id:
        raise ValueError("hardware record backend_id is empty")
    return candidate, result_job


def hardware_backend_result(
    hardware_record: dict[str, Any],
    record_digest: str,
) -> dict[str, Any]:
    return {
        "backend_id": hardware_record["backend_id"],
        "backend_kind": "moonlab_hardware",
        "status": hardware_record["status"],
        "run_id": hardware_record.get("run_id"),
        "candidate_digest": hardware_record["candidate_digest"],
        "hardware_record_sha256": record_digest,
        "submitted_utc": hardware_record.get("submitted_utc"),
        "completed_utc": hardware_record.get("completed_utc"),
        "shot_schedule": dict_or_empty(hardware_record.get("shot_schedule")),
        "readout_metadata": dict_or_empty(
            hardware_record.get("readout_metadata")),
        "observations": dict_or_empty(hardware_record.get("observations")),
    }


def recompute_submission_counts(results: dict[str, Any]) -> None:
    submitted = 0
    completed = 0
    for job in list_or_empty(results.get("jobs")):
        if not isinstance(job, dict):
            continue
        if job.get("hardware_submission_status") not in NO_SUBMISSION_STATUSES:
            submitted += 1
        if any(
            isinstance(item, dict) and
            item.get("backend_kind") == "moonlab_hardware" and
            item.get("status") == "completed"
            for item in list_or_empty(job.get("backend_results"))
        ):
            completed += 1
    results["hardware_submitted_job_count"] = submitted
    results["completed_hardware_job_count"] = completed
    if results.get("blocked_job_count") == 0 and submitted:
        results["overall_status"] = "simulator_complete_hardware_recorded"


def numeric_delta(left: Any, right: Any) -> float | None:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(right) - float(left)
    return None


def build_hardware_comparison(
    candidate: dict[str, Any],
    result_job: dict[str, Any],
    hardware_record: dict[str, Any],
    record_digest: str,
) -> dict[str, Any]:
    simulator = dict_or_empty(result_job.get("observations"))
    hardware = dict_or_empty(hardware_record.get("observations"))
    simulator_value = simulator.get("reference_value")
    hardware_value = hardware.get("mean_value", hardware.get("observed_value"))
    return {
        "schema": "qge.moonlab_hardware_comparison.v0",
        "job_id": hardware_record.get("job_id"),
        "domain": candidate.get("domain"),
        "kind": candidate.get("kind"),
        "candidate_digest": candidate.get("candidate_digest"),
        "hardware_record_sha256": record_digest,
        "backend_id": hardware_record.get("backend_id"),
        "backend_kind": hardware_record.get("backend_kind"),
        "status": "hardware_result_recorded",
        "simulator_observations": simulator,
        "hardware_observations": hardware,
        "value_delta": numeric_delta(simulator_value, hardware_value),
        "shot_delta": numeric_delta(simulator.get("shots"),
                                    hardware.get("shots")),
        "claim_posture": {
            "bounded_hardware_job_result_recorded": True,
            "hardware_quantum_advantage_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "dense_70000_qubit_state_claimed": False,
        },
        "limits": [
            "This comparison records one bounded Moonlab hardware job result.",
            "It is not a whole-game hardware execution claim.",
            "It is not a hardware quantum advantage claim.",
        ],
    }


def build_icc_evidence(
    updated_results: dict[str, Any],
    comparison: dict[str, Any],
    *,
    out_path: Path | None = None,
    comparison_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_moonlab_hardware_ingest",
        "completion_reason": "qge_moonlab_hardware_result_recorded",
        "moonlab_job_results_file": str(out_path) if out_path else None,
        "moonlab_hardware_comparison_file": (
            str(comparison_path) if comparison_path else None),
        "job_id": comparison.get("job_id"),
        "backend_id": comparison.get("backend_id"),
        "candidate_digest": comparison.get("candidate_digest"),
        "hardware_record_sha256": comparison.get("hardware_record_sha256"),
        "hardware_submitted_job_count": updated_results.get(
            "hardware_submitted_job_count"),
        "completed_hardware_job_count": updated_results.get(
            "completed_hardware_job_count"),
        "hardware_result_recorded": True,
        "hardware_quantum_advantage_claimed": False,
        "whole_game_hardware_execution_claimed": False,
        "dense_70000_qubit_state_claimed": False,
        "status": "success",
    }


def ingest_hardware_record(
    submission_packet: dict[str, Any],
    job_results: dict[str, Any],
    hardware_record: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate, result_job = validate_hardware_record(
        submission_packet, job_results, hardware_record)
    updated = copy.deepcopy(job_results)
    updated_job = result_jobs_by_id(updated)[hardware_record["job_id"]]
    record_digest = stable_json_digest(hardware_record)
    backend_results = [
        item for item in list_or_empty(updated_job.get("backend_results"))
        if not (
            isinstance(item, dict) and
            item.get("backend_kind") == "moonlab_hardware_candidate"
        )
    ]
    backend_results.append(hardware_backend_result(hardware_record,
                                                   record_digest))
    updated_job["backend_results"] = backend_results
    updated_job["hardware_submission_status"] = "completed"
    updated_job["result_status"] = "hardware_completed_simulator_retained"
    updated_job["hardware_result_record"] = {
        "backend_id": hardware_record.get("backend_id"),
        "candidate_digest": hardware_record.get("candidate_digest"),
        "hardware_record_sha256": record_digest,
    }
    updated_job["claim_posture"] = {
        "hardware_result_claimed": True,
        "hardware_quantum_advantage_claimed": False,
        "whole_game_hardware_execution_claimed": False,
    }
    recompute_submission_counts(updated)
    comparison = build_hardware_comparison(
        candidate, result_job, hardware_record, record_digest)
    return updated, comparison


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission_packet", type=Path)
    parser.add_argument("--job-results", required=True, type=Path)
    parser.add_argument("--hardware-record", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--comparison-out", type=Path)
    parser.add_argument("--icc-out", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        submission_packet = load_json(args.submission_packet)
        job_results = load_json(args.job_results)
        hardware_record = load_json(args.hardware_record)
        updated_results, comparison = ingest_hardware_record(
            submission_packet, job_results, hardware_record)
        write_json(args.out, updated_results)
        if args.comparison_out:
            write_json(args.comparison_out, comparison)
        if args.icc_out:
            icc = build_icc_evidence(
                updated_results,
                comparison,
                out_path=args.out,
                comparison_path=args.comparison_out,
            )
            write_json(args.icc_out, icc)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_moonlab_hardware_ingest: {exc}", file=sys.stderr)
        return 1

    print(f"QGE_MOONLAB_HARDWARE_RESULTS {args.out}")
    if args.comparison_out:
        print(f"QGE_MOONLAB_HARDWARE_COMPARISON {args.comparison_out}")
    if args.icc_out:
        print(f"QGE_MOONLAB_HARDWARE_ICC_EVIDENCE {args.icc_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
