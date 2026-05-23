#!/usr/bin/env python3
"""Build reproducible Moonlab job-result evidence from QGE job specs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence


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


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_info(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "size_bytes": 0, "sha256": None}
    return {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": sha256_file(path),
    }


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def artifact_evidence(
    required_artifacts: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    evidence = []
    missing = []
    for name, value in sorted(required_artifacts.items()):
        path = Path(value) if isinstance(value, str) and value else None
        info = file_info(path)
        record = {"name": name, **info}
        evidence.append(record)
        if not info["exists"]:
            missing.append(name)
    return evidence, missing


def stable_job_run_id(job: dict[str, Any],
                      evidence: list[dict[str, Any]]) -> str:
    material = {
        "job_id": job.get("job_id"),
        "kind": job.get("kind"),
        "artifacts": [
            {
                "name": item.get("name"),
                "sha256": item.get("sha256"),
                "size_bytes": item.get("size_bytes"),
            }
            for item in evidence
        ],
    }
    encoded = json.dumps(material, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def job_observations(job: dict[str, Any]) -> dict[str, Any]:
    required = dict_or_empty(job.get("required_artifacts"))
    domain = job.get("domain")
    observations: dict[str, Any] = {}
    if domain == "light_transport_qae_benchmark":
        metrics_path = required.get("advantage_metrics")
        if isinstance(metrics_path, str) and Path(metrics_path).is_file():
            metrics = load_json(Path(metrics_path))
            best_qae = dict_or_empty(
                dict_or_empty(metrics.get("comparison")).get("best_qae"))
            observations.update({
                "advantage_problem_id": metrics.get("advantage_problem_id"),
                "reference_value": best_qae.get("mean_reference_value"),
                "rmse": best_qae.get("rmse"),
                "shots": best_qae.get("shots"),
                "oracle_eval_count": best_qae.get("oracle_eval_count"),
            })
    elif domain == "runtime_backend_probes":
        performance_path = required.get("performance_summary")
        if isinstance(performance_path, str) and Path(performance_path).is_file():
            performance = load_json(Path(performance_path))
            observations.update({
                "performance_runtime_backend_probe_resolved": (
                    performance.get("runtime_backend_probe_resolved")),
                "performance_native_targets": (
                    performance.get("runtime_backend_probe_native_targets")),
                "performance_missing_targets": (
                    performance.get("runtime_backend_probe_missing_targets")),
            })
        breadth_path = required.get("breadth_evidence")
        if isinstance(breadth_path, str) and Path(breadth_path).is_file():
            breadth = load_json(Path(breadth_path))
            observations.update({
                "breadth_map_count": breadth.get("map_count"),
                "breadth_runtime_backend_probe_resolved_run_count": (
                    breadth.get("runtime_backend_probe_resolved_run_count")),
                "breadth_total_native_bridge_count": (
                    breadth.get("total_native_bridge_count")),
            })
    elif domain == "render_primary_framebuffer":
        frame_path = required.get("frame")
        if isinstance(frame_path, str) and Path(frame_path).is_file():
            observations["produced_frame_sha256"] = sha256_file(Path(frame_path))
        matrix_path = required.get("vanilla_matrix")
        if isinstance(matrix_path, str) and Path(matrix_path).is_file():
            matrix = load_json(Path(matrix_path))
            conformance = dict_or_empty(matrix.get("conformance_summary"))
            observations.update({
                "vanilla_ready_for_complete_claim": (
                    conformance.get("ready_for_complete_claim")),
                "fallback_count": conformance.get("fallback_count"),
                "surrogate_count": conformance.get("qge_surface_surrogates"),
            })
    return observations


def build_moonlab_job_results(
    moonlab_job_specs: dict[str, Any],
) -> dict[str, Any]:
    jobs = moonlab_job_specs.get("jobs", [])
    if not isinstance(jobs, list):
        jobs = []
    result_jobs = []
    completed_simulator = 0
    completed_native_replay = 0
    blocked = 0
    hardware_candidate = 0
    hardware_submitted = 0

    for job in jobs:
        if not isinstance(job, dict):
            continue
        required = dict_or_empty(job.get("required_artifacts"))
        evidence, missing = artifact_evidence(required)
        run_id = stable_job_run_id(job, evidence)
        is_hardware_candidate = bool(job.get("hardware_candidate"))
        if is_hardware_candidate:
            hardware_candidate += 1
        submitted = job.get("hardware_submission_status") not in (
            None,
            "not_submitted",
            "not_a_quantum_hardware_job",
            "not_applicable_full_frame_hardware_execution_not_claimed",
        )
        if submitted:
            hardware_submitted += 1

        if missing:
            result_status = "blocked_missing_required_artifact"
            blocked += 1
        elif is_hardware_candidate:
            result_status = "simulator_completed_hardware_not_submitted"
            completed_simulator += 1
        else:
            result_status = "completed"
            completed_simulator += 1
            if job.get("kind") in (
                "moonlab_simulator_native_backend_replay",
                "moonlab_runtime_boundary_replay",
            ):
                completed_native_replay += 1

        backend_results = [
            {
                "backend_id": (
                    "moonlab-simulator-local/qge-publication-pack"
                ),
                "backend_kind": "moonlab_simulator",
                "status": "completed" if not missing else "blocked",
                "run_id": f"moonlab-sim-{run_id}",
            }
        ]
        if job.get("kind") == "moonlab_simulator_native_backend_replay":
            backend_results.append({
                "backend_id": "qge-native-sparse-dwt-bridge",
                "backend_kind": "native_backend_replay",
                "status": "completed" if not missing else "blocked",
                "run_id": f"qge-native-{run_id}",
            })
        if is_hardware_candidate:
            backend_results.append({
                "backend_id": None,
                "backend_kind": "moonlab_hardware_candidate",
                "status": job.get("hardware_submission_status"),
                "run_id": None,
            })

        result_jobs.append({
            "job_id": job.get("job_id"),
            "domain": job.get("domain"),
            "kind": job.get("kind"),
            "result_status": result_status,
            "hardware_candidate": is_hardware_candidate,
            "hardware_submission_status": job.get(
                "hardware_submission_status"),
            "missing_required_artifacts": missing,
            "artifact_evidence": evidence,
            "backend_results": backend_results,
            "observations": job_observations(job) if not missing else {},
            "claim_posture": {
                "hardware_result_claimed": False,
                "hardware_quantum_advantage_claimed": False,
                "whole_game_hardware_execution_claimed": False,
            },
        })

    overall_status = (
        "blocked_missing_required_artifact"
        if blocked else "simulator_complete_hardware_not_submitted"
    )
    return {
        "schema": "qge.moonlab_job_results.v0",
        "source_schema": moonlab_job_specs.get("schema"),
        "posture": moonlab_job_specs.get("posture"),
        "overall_status": overall_status,
        "selected_job_count": len(result_jobs),
        "completed_simulator_job_count": completed_simulator,
        "completed_native_replay_job_count": completed_native_replay,
        "hardware_candidate_job_count": hardware_candidate,
        "hardware_submitted_job_count": hardware_submitted,
        "blocked_job_count": blocked,
        "jobs": result_jobs,
        "limits": [
            "Simulator/native replay completion is not a hardware result.",
            "Hardware-candidate jobs remain unsubmitted until backend ids exist.",
            "No whole-game hardware execution or hardware advantage is claimed.",
        ],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build qge.moonlab_job_results.v0 evidence from "
            "qge.moonlab_job_specs.v0"
        )
    )
    parser.add_argument("job_specs", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        moonlab_job_specs = load_json(args.job_specs)
        if moonlab_job_specs.get("schema") != "qge.moonlab_job_specs.v0":
            raise ValueError(
                f"{args.job_specs} is not qge.moonlab_job_specs.v0"
            )
        results = build_moonlab_job_results(moonlab_job_specs)
        write_json(args.out, results)
    except (OSError, ValueError) as exc:
        print(f"qge_moonlab_job_runner: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_MOONLAB_JOB_RESULTS {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
