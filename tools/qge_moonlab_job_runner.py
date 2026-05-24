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
    elif domain == "full_game_map_coverage":
        coverage_path = required.get("full_game_map_coverage")
        if isinstance(coverage_path, str) and Path(coverage_path).is_file():
            coverage = load_json(Path(coverage_path))
            observations.update({
                "coverage_status": coverage.get("status"),
                "map_set": coverage.get("map_set"),
                "target_map_count": coverage.get("target_map_count"),
                "covered_map_count": coverage.get("covered_map_count"),
                "missing_map_count": coverage.get("missing_map_count"),
                "missing_maps": coverage.get("missing_maps"),
            })
        asset_inventory_path = required.get("asset_inventory")
        if (
            isinstance(asset_inventory_path, str) and
            Path(asset_inventory_path).is_file()
        ):
            inventory = load_json(Path(asset_inventory_path))
            observations.update({
                "asset_inventory_status": inventory.get("status"),
                "asset_available_map_count": (
                    inventory.get("available_map_count")),
                "asset_missing_map_count": inventory.get("missing_map_count"),
                "asset_invalid_bsp_count": inventory.get("invalid_bsp_count"),
                "full_game_asset_ready": (
                    inventory.get("full_game_asset_ready")),
            })
        asset_requirements_path = required.get("asset_requirements")
        if (
            isinstance(asset_requirements_path, str) and
            Path(asset_requirements_path).is_file()
        ):
            requirements = load_json(Path(asset_requirements_path))
            claim_posture = dict_or_empty(requirements.get("claim_posture"))
            observations.update({
                "asset_requirement_status": requirements.get("status"),
                "asset_requirements_present_map_count": (
                    requirements.get("present_map_count")),
                "asset_requirements_missing_map_count": (
                    requirements.get("missing_map_count")),
                "asset_requirements_satisfied": claim_posture.get(
                    "asset_requirements_satisfied"),
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


def replay_scope_for_job(job: dict[str, Any]) -> str:
    domain = job.get("domain")
    if domain == "render_primary_framebuffer":
        return (
            "replay captured sparse-DWT framebuffer/native-backend evidence; "
            "not a full-frame hardware job"
        )
    if domain == "light_transport_qae_benchmark":
        return (
            "replay bounded Moonlab simulator benchmark; hardware candidate "
            "remains unsubmitted until backend metadata exists"
        )
    if domain == "runtime_backend_probes":
        return (
            "replay native runtime-boundary evidence from performance and "
            "breadth artifacts"
        )
    if domain == "full_game_map_coverage":
        return (
            "replay canonical map coverage ledger; partial status means the "
            "whole-game Moonlab claim is still pending"
        )
    return "replay selected Moonlab job evidence from required artifacts"


def result_jobs_by_id(
    moonlab_job_results: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result_jobs = moonlab_job_results.get("jobs", [])
    if not isinstance(result_jobs, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for job in result_jobs:
        if not isinstance(job, dict):
            continue
        job_id = job.get("job_id")
        if isinstance(job_id, str):
            indexed[job_id] = job
    return indexed


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def candidate_submission_status(
    spec_job: dict[str, Any],
    result_job: dict[str, Any],
) -> str:
    missing = list_or_empty(result_job.get("missing_required_artifacts"))
    if missing:
        return "blocked_missing_required_artifact"
    hardware_status = spec_job.get("hardware_submission_status")
    if hardware_status not in (None, "not_submitted"):
        return "hardware_submission_recorded"
    return "ready_for_hardware_submission_metadata"


def simulator_backend_results(result_job: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in list_or_empty(result_job.get("backend_results"))
        if isinstance(item, dict) and
        item.get("backend_kind") in ("moonlab_simulator", "native_backend_replay")
    ]


def build_moonlab_submission_packet(
    moonlab_job_specs: dict[str, Any],
    moonlab_job_results: dict[str, Any],
    *,
    job_specs_path: Path | None = None,
    job_results_path: Path | None = None,
) -> dict[str, Any]:
    spec_jobs = list_or_empty(moonlab_job_specs.get("jobs"))
    result_index = result_jobs_by_id(moonlab_job_results)
    candidate_jobs = []
    ready = 0
    blocked = 0
    submitted = 0
    default_results = (
        job_results_path or Path("resource/qge_moonlab_job_results.json")
    )

    for job in spec_jobs:
        if not isinstance(job, dict) or not bool(job.get("hardware_candidate")):
            continue
        job_id = job.get("job_id")
        result_job = (
            result_index.get(job_id, {}) if isinstance(job_id, str) else {}
        )
        artifact_evidence = [
            item for item in list_or_empty(result_job.get("artifact_evidence"))
            if isinstance(item, dict)
        ]
        missing = list_or_empty(result_job.get("missing_required_artifacts"))
        status = candidate_submission_status(job, result_job)
        if status == "ready_for_hardware_submission_metadata":
            ready += 1
        elif status == "hardware_submission_recorded":
            submitted += 1
        else:
            blocked += 1
        required = dict_or_empty(job.get("required_artifacts"))
        candidate_jobs.append({
            "job_id": job_id,
            "domain": job.get("domain"),
            "kind": job.get("kind"),
            "submission_status": status,
            "hardware_submission_status": job.get("hardware_submission_status"),
            "backend_targets": list_or_empty(job.get("backend_targets")),
            "resource": dict_or_empty(job.get("resource")),
            "required_artifacts": required,
            "required_artifact_names": sorted(required.keys()),
            "artifact_evidence": artifact_evidence,
            "missing_required_artifacts": missing,
            "simulator_result_status": result_job.get("result_status"),
            "simulator_backend_results": simulator_backend_results(result_job),
            "candidate_digest": stable_job_run_id(job, artifact_evidence),
            "moonlab_submission_contract": {
                "submission_mode": "moonlab_hardware_backend_handoff",
                "backend_id_required": True,
                "shot_schedule_required": True,
                "readout_metadata_required": True,
                "result_update_target": str(default_results),
                "submit_only_if": [
                    "submission_status is ready_for_hardware_submission_metadata",
                    "backend id is known",
                    "shot schedule and readout metadata are recorded",
                    "simulator and hardware results remain separate",
                ],
            },
            "claim_posture": {
                "hardware_result_claimed": False,
                "hardware_quantum_advantage_claimed": False,
                "whole_game_hardware_execution_claimed": False,
            },
        })

    return {
        "schema": "qge.moonlab_submission_packet.v0",
        "source_schema": moonlab_job_specs.get("schema"),
        "results_schema": moonlab_job_results.get("schema"),
        "posture": moonlab_job_specs.get("posture"),
        "job_specs": str(job_specs_path) if job_specs_path else None,
        "job_results": str(job_results_path) if job_results_path else None,
        "hardware_candidate_job_count": len(candidate_jobs),
        "ready_candidate_count": ready,
        "blocked_candidate_count": blocked,
        "submitted_candidate_count": submitted,
        "hardware_submitted_job_count": moonlab_job_results.get(
            "hardware_submitted_job_count"),
        "whole_game_hardware_execution_claimed": False,
        "hardware_quantum_advantage_claimed": False,
        "dense_70000_qubit_state_claimed": False,
        "candidate_jobs": candidate_jobs,
        "limits": [
            "This packet is a hardware handoff contract, not a hardware result.",
            "A backend id, shot schedule, and readout metadata are required before a hardware submission can be claimed.",
            "Simulator and hardware results must remain separate in qge_moonlab_job_results.json.",
        ],
    }


def validation_checks_for_job(
    spec_job: dict[str, Any],
    result_job: dict[str, Any],
) -> list[dict[str, Any]]:
    missing = result_job.get("missing_required_artifacts", [])
    if not isinstance(missing, list):
        missing = []
    result_status = result_job.get("result_status")
    backend_results = result_job.get("backend_results", [])
    if not isinstance(backend_results, list):
        backend_results = []
    native_backend_completed = any(
        isinstance(item, dict) and
        item.get("backend_kind") == "native_backend_replay" and
        item.get("status") == "completed"
        for item in backend_results
    )
    checks = [
        {
            "check": "required_artifacts_present",
            "status": "pass" if not missing else "fail",
            "missing_required_artifacts": missing,
        },
        {
            "check": "job_result_not_blocked",
            "status": "pass"
            if result_status != "blocked_missing_required_artifact"
            else "fail",
            "result_status": result_status,
        },
    ]
    if spec_job.get("kind") == "moonlab_simulator_native_backend_replay":
        checks.append({
            "check": "native_backend_replay_recorded",
            "status": "pass" if native_backend_completed else "fail",
        })
    if bool(spec_job.get("hardware_candidate")):
        checks.append({
            "check": "hardware_submission_separated_from_simulator_result",
            "status": "pass"
            if result_job.get("hardware_submission_status") == "not_submitted"
            else "fail",
            "hardware_submission_status": result_job.get(
                "hardware_submission_status"),
        })
    return checks


def build_moonlab_replay_plan(
    moonlab_job_specs: dict[str, Any],
    moonlab_job_results: dict[str, Any],
    *,
    job_specs_path: Path | None = None,
    job_results_path: Path | None = None,
) -> dict[str, Any]:
    spec_jobs = moonlab_job_specs.get("jobs", [])
    if not isinstance(spec_jobs, list):
        spec_jobs = []
    result_index = result_jobs_by_id(moonlab_job_results)
    replay_jobs = []
    for job in spec_jobs:
        if not isinstance(job, dict):
            continue
        job_id = job.get("job_id")
        result_job = result_index.get(job_id, {}) if isinstance(job_id, str) else {}
        required = dict_or_empty(job.get("required_artifacts"))
        backend_targets = job.get("backend_targets", [])
        if not isinstance(backend_targets, list):
            backend_targets = []
        replay_jobs.append({
            "job_id": job_id,
            "domain": job.get("domain"),
            "kind": job.get("kind"),
            "result_status": result_job.get("result_status"),
            "hardware_candidate": bool(job.get("hardware_candidate")),
            "hardware_submission_status": job.get("hardware_submission_status"),
            "backend_targets": backend_targets,
            "required_artifacts": required,
            "required_artifact_names": sorted(required.keys()),
            "required_artifact_count": len(required),
            "missing_required_artifacts": result_job.get(
                "missing_required_artifacts", []),
            "replay_scope": replay_scope_for_job(job),
            "validation_checks": validation_checks_for_job(job, result_job),
        })

    default_specs = job_specs_path or Path("resource/qge_moonlab_job_specs.json")
    default_results = (
        job_results_path or Path("resource/qge_moonlab_job_results.json")
    )
    return {
        "schema": "qge.moonlab_replay_plan.v0",
        "source_schema": moonlab_job_specs.get("schema"),
        "results_schema": moonlab_job_results.get("schema"),
        "posture": moonlab_job_specs.get("posture"),
        "selected_job_count": len(replay_jobs),
        "hardware_candidate_job_count": moonlab_job_specs.get(
            "hardware_candidate_job_count"),
        "hardware_submitted_job_count": moonlab_job_results.get(
            "hardware_submitted_job_count"),
        "blocked_job_count": moonlab_job_results.get("blocked_job_count"),
        "pack_validation": {
            "job_specs": str(job_specs_path) if job_specs_path else None,
            "job_results": str(job_results_path) if job_results_path else None,
            "regenerate_results_command": [
                "python3",
                "tools/qge_moonlab_job_runner.py",
                str(default_specs),
                "--out",
                str(default_results),
            ],
            "verify_results_command": [
                "python3",
                "tools/qge_moonlab_job_runner.py",
                str(default_specs),
                "--out",
                "/tmp/qge_moonlab_job_results.verify.json",
                "--expect",
                str(default_results),
            ],
        },
        "jobs": replay_jobs,
        "limits": [
            "Replay validation proves artifact reproducibility, not hardware execution.",
            "Hardware-candidate jobs remain unsubmitted until backend ids and shot metadata exist.",
            "Whole-game Moonlab hardware execution is outside this replay plan.",
        ],
    }


def compare_expected_results(
    results: dict[str, Any],
    expected_path: Path,
) -> None:
    expected = load_json(expected_path)
    if results != expected:
        raise ValueError(
            f"regenerated Moonlab job results differ from {expected_path}"
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build qge.moonlab_job_results.v0 evidence from "
            "qge.moonlab_job_specs.v0"
        )
    )
    parser.add_argument("job_specs", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--expect",
        type=Path,
        help="Optional qge.moonlab_job_results.v0 artifact to compare against",
    )
    parser.add_argument(
        "--plan-out",
        type=Path,
        help="Optional qge.moonlab_replay_plan.v0 output path",
    )
    parser.add_argument(
        "--submission-out",
        type=Path,
        help="Optional qge.moonlab_submission_packet.v0 output path",
    )
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
        if args.expect:
            compare_expected_results(results, args.expect)
        write_json(args.out, results)
        if args.plan_out:
            replay_plan = build_moonlab_replay_plan(
                moonlab_job_specs,
                results,
                job_specs_path=args.job_specs,
                job_results_path=args.expect or args.out,
            )
            write_json(args.plan_out, replay_plan)
        if args.submission_out:
            submission_packet = build_moonlab_submission_packet(
                moonlab_job_specs,
                results,
                job_specs_path=args.job_specs,
                job_results_path=args.expect or args.out,
            )
            write_json(args.submission_out, submission_packet)
    except (OSError, ValueError) as exc:
        print(f"qge_moonlab_job_runner: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_MOONLAB_JOB_RESULTS {args.out}")
    if args.expect:
        print(f"QGE_MOONLAB_EXPECTED_RESULTS_MATCH {args.expect}")
    if args.plan_out:
        print(f"QGE_MOONLAB_REPLAY_PLAN {args.plan_out}")
    if args.submission_out:
        print(f"QGE_MOONLAB_SUBMISSION_PACKET {args.submission_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
