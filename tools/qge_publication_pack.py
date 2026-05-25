#!/usr/bin/env python3
"""Build a QGE publication artifact pack.

The pack is a reproducibility manifest over the current research artifacts:
trace-backed scene-oracle IR, claims evidence, finite-shot advantage benchmark
outputs, paired vanilla/QGE render matrix, and agent media-stream evidence.
It does not claim hardware advantage; it makes the evidence and caveats
auditable from one directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_advantage_benchmark  # noqa: E402
import qge_asset_inventory  # noqa: E402
import qge_asset_requirements  # noqa: E402
import qge_breadth_evidence  # noqa: E402
import qge_moonlab_deployment_gate  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402
import qge_moonlab_hardware_ingest  # noqa: E402
import qge_moonlab_job_runner  # noqa: E402
import qge_moonlab_oracle_transpile  # noqa: E402
import qge_moonlab_qae_grover_plan  # noqa: E402
import qge_moonlab_qae_observation_transpile  # noqa: E402
import qge_moonlab_qae_transpile  # noqa: E402
import qge_moonlab_submission_bundle  # noqa: E402
import qge_oracle_export  # noqa: E402
import qge_perf_summary  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402
import qge_registered_asset_intake  # noqa: E402

DEFAULT_SAMPLE_COUNTS = [16, 32, 64, 128]


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


def directory_info(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_dir():
        return {
            "path": str(path) if path else None,
            "exists": False,
            "file_count": 0,
            "size_bytes": 0,
            "files": [],
        }
    files = []
    size_bytes = 0
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        info = file_info(child)
        info["relative_path"] = str(child.relative_to(path))
        files.append(info)
        size_bytes += int(info["size_bytes"])
    return {
        "path": str(path),
        "exists": True,
        "file_count": len(files),
        "size_bytes": size_bytes,
        "files": files,
    }


def agent_manifest_summary(path: Path | None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": str(path) if path else None,
        "exists": bool(path and path.is_file()),
        "manifest_status": None,
        "frames_requested": None,
        "frames_captured": None,
        "trace_requested": None,
        "trace_status": None,
        "trace_bytes": None,
        "run_status": None,
        "run_success": None,
        "startup_issue": None,
        "process_status": None,
        "timed_out": None,
        "performance_status": None,
        "performance_summary_file": None,
        "performance_icc_evidence_file": None,
    }
    if path is None or not path.is_file():
        return summary
    try:
        manifest = load_json(path)
    except (OSError, ValueError) as exc:
        summary["error"] = str(exc)
        return summary
    run = manifest.get("run", {})
    if not isinstance(run, dict):
        run = {}
    summary.update({
        "manifest_status": manifest.get("status"),
        "frames_requested": manifest.get("frames_requested"),
        "frames_captured": manifest.get("frames_captured"),
        "trace_requested": manifest.get("trace_requested"),
        "trace_status": manifest.get("trace_status"),
        "trace_bytes": manifest.get("trace_bytes"),
        "run_status": run.get("status"),
        "run_success": run.get("success"),
        "startup_issue": run.get("startup_issue"),
        "process_status": run.get("process_status"),
        "timed_out": run.get("timed_out"),
    })
    performance = manifest.get("performance", {})
    if isinstance(performance, dict):
        summary.update({
            "performance_status": performance.get("status"),
            "performance_summary_file": performance.get("summary_file"),
            "performance_icc_evidence_file": performance.get(
                "icc_evidence_file"),
        })
    return summary


def explicit_agent_run_failure(summary: dict[str, Any]) -> bool:
    run_status = summary.get("run_status")
    if isinstance(run_status, str) and run_status and run_status != "ok":
        return True
    run_success = summary.get("run_success")
    if run_success is not None and not bool(run_success):
        return True
    startup_issue = summary.get("startup_issue")
    if isinstance(startup_issue, str) and startup_issue:
        return True
    return False


def performance_summary(path: Path | None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": str(path) if path else None,
        "exists": bool(path and path.is_file()),
        "status": None,
        "engine_average_quantum_ms_max": None,
        "render_time_ms_max": None,
        "threshold_failures": [],
        "metric_evidence_present": None,
        "required_runtime_backend_probe_targets": [],
        "runtime_backend_probe_proofs": {},
        "runtime_backend_probe_missing_targets": [],
        "runtime_backend_probe_native_targets": [],
        "runtime_backend_probe_resolved": None,
        "runtime_backend_boundary": None,
        "runtime_backend_boundary_status": None,
    }
    if path is None or not path.is_file():
        return summary
    try:
        data = load_json(path)
    except (OSError, ValueError) as exc:
        summary["error"] = str(exc)
        return summary
    aggregate = data.get("aggregate", {})
    if not isinstance(aggregate, dict):
        aggregate = {}
    failures = aggregate.get("threshold_failures", [])
    runtime_backend_probe_proofs = aggregate.get(
        "runtime_backend_probe_proofs", {})
    if not isinstance(runtime_backend_probe_proofs, dict):
        runtime_backend_probe_proofs = {}
    runtime_backend_boundary = aggregate.get("runtime_backend_boundary")
    if not isinstance(runtime_backend_boundary, dict):
        runtime_backend_boundary = (
            qge_perf_summary.runtime_backend_boundary_from_proofs(
                runtime_backend_probe_proofs)
        )
    summary.update({
        "status": data.get("status"),
        "engine_average_quantum_ms_max": aggregate.get(
            "engine_average_quantum_ms_max"),
        "render_time_ms_max": aggregate.get("render_time_ms_max"),
        "threshold_failures": failures if isinstance(failures, list) else [],
        "metric_evidence_present": aggregate.get("metric_evidence_present"),
        "required_runtime_backend_probe_targets": aggregate.get(
            "required_runtime_backend_probe_targets", []),
        "runtime_backend_probe_proofs": runtime_backend_probe_proofs,
        "runtime_backend_probe_missing_targets": aggregate.get(
            "runtime_backend_probe_missing_targets", []),
        "runtime_backend_probe_native_targets": aggregate.get(
            "runtime_backend_probe_native_targets", []),
        "runtime_backend_probe_resolved": aggregate.get(
            "runtime_backend_probe_resolved"),
        "runtime_backend_boundary": runtime_backend_boundary,
        "runtime_backend_boundary_status": runtime_backend_boundary.get(
            "status"),
    })
    return summary


def resolve_breadth_evidence_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_dir():
        candidate = path / "breadth_evidence.json"
        if candidate.is_file():
            return candidate
        candidate = path / "qge_breadth_icc_evidence.json"
        if candidate.is_file():
            return candidate
    return path


def breadth_evidence_summary(path: Path | None) -> dict[str, Any]:
    path = resolve_breadth_evidence_path(path)
    default_full_game_coverage = (
        qge_breadth_evidence.build_full_game_map_coverage([])
    )
    summary: dict[str, Any] = {
        "path": str(path) if path else None,
        "exists": bool(path and path.is_file()),
        "status": None,
        "breadth_ready_for_complete_claim": None,
        "matrix_run_count": None,
        "ready_matrix_run_count": None,
        "map_count": None,
        "maps": [],
        "full_game_coverage": default_full_game_coverage,
        "full_game_map_set": default_full_game_coverage["map_set"],
        "full_game_map_coverage_status": default_full_game_coverage["status"],
        "full_game_map_target_count": (
            default_full_game_coverage["target_map_count"]),
        "full_game_map_covered_count": (
            default_full_game_coverage["covered_map_count"]),
        "full_game_map_missing_count": (
            default_full_game_coverage["missing_map_count"]),
        "full_game_map_missing_maps": (
            default_full_game_coverage["missing_maps"]),
        "full_game_map_extra_maps": default_full_game_coverage["extra_maps"],
        "total_fallback_count": None,
        "total_surrogate_count": None,
        "total_cpu_idwt_count": None,
        "total_native_bridge_count": None,
        "total_backend_gate_event_count": None,
        "backend_gate_render_bridge_run_count": None,
        "total_runtime_backend_probe_event_count": None,
        "runtime_backend_probe_run_count": None,
        "runtime_backend_probe_targets": [],
        "runtime_backend_probe_paths": [],
        "runtime_backend_probe_results": [],
        "required_runtime_backend_probe_targets": [],
        "runtime_backend_probe_proofs": {},
        "runtime_backend_probe_missing_targets": [],
        "runtime_backend_probe_native_targets": [],
        "runtime_backend_probe_resolved_run_count": None,
        "issue_count": None,
        "issues": [],
    }
    if path is None or not path.is_file():
        return summary
    try:
        data = load_json(path)
    except (OSError, ValueError) as exc:
        summary["error"] = str(exc)
        return summary
    aggregate = data.get("aggregate")
    if not isinstance(aggregate, dict):
        aggregate = data
    for key in (
        "breadth_ready_for_complete_claim",
        "matrix_run_count",
        "ready_matrix_run_count",
        "map_count",
        "maps",
        "full_game_map_set",
        "full_game_map_coverage_status",
        "full_game_map_target_count",
        "full_game_map_covered_count",
        "full_game_map_missing_count",
        "full_game_map_missing_maps",
        "full_game_map_extra_maps",
        "total_fallback_count",
        "total_surrogate_count",
        "total_cpu_idwt_count",
        "total_native_bridge_count",
        "total_backend_gate_event_count",
        "backend_gate_render_bridge_run_count",
        "total_runtime_backend_probe_event_count",
        "runtime_backend_probe_run_count",
        "runtime_backend_probe_targets",
        "runtime_backend_probe_paths",
        "runtime_backend_probe_results",
        "required_runtime_backend_probe_targets",
        "runtime_backend_probe_proofs",
        "runtime_backend_probe_missing_targets",
        "runtime_backend_probe_native_targets",
        "runtime_backend_probe_resolved_run_count",
        "issue_count",
        "issues",
    ):
        if key in aggregate:
            summary[key] = aggregate.get(key)
    maps = summary.get("maps")
    if not isinstance(maps, list):
        maps = []
        summary["maps"] = maps
    full_game_coverage = full_game_coverage_from_summary(
        aggregate.get("full_game_coverage"),
        maps,
    )
    summary["full_game_coverage"] = full_game_coverage
    summary["full_game_map_set"] = full_game_coverage.get("map_set")
    summary["full_game_map_coverage_status"] = full_game_coverage.get("status")
    summary["full_game_map_target_count"] = full_game_coverage.get(
        "target_map_count")
    summary["full_game_map_covered_count"] = full_game_coverage.get(
        "covered_map_count")
    summary["full_game_map_missing_count"] = full_game_coverage.get(
        "missing_map_count")
    summary["full_game_map_missing_maps"] = full_game_coverage.get(
        "missing_maps")
    summary["full_game_map_extra_maps"] = full_game_coverage.get("extra_maps")
    summary["status"] = data.get("status")
    return summary


def explicit_breadth_evidence_failure(summary: dict[str, Any]) -> bool:
    if not summary.get("exists"):
        return False
    if summary.get("error"):
        return True
    ready = summary.get("breadth_ready_for_complete_claim")
    return ready is not None and not bool(ready)


def explicit_performance_failure(summary: dict[str, Any]) -> bool:
    if not summary.get("exists"):
        return False
    if summary.get("error"):
        return True
    status = summary.get("status")
    if isinstance(status, str) and status and status not in ("pass", "success"):
        return True
    failures = summary.get("threshold_failures")
    if isinstance(failures, list) and failures:
        return True
    return False


def int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.split("/", 1)[0]))
        except ValueError:
            return None
    return None


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def full_game_coverage_from_summary(
    value: Any,
    maps: list[Any],
) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("schema") == (
        "qge.full_game_map_coverage.v0"
    ):
        return value
    return qge_breadth_evidence.build_full_game_map_coverage(maps)


def build_resource_envelope(
    oracle_scene: dict[str, Any],
    advantage_metrics: dict[str, Any],
    conformance: dict[str, Any],
    performance: dict[str, Any],
    breadth: dict[str, Any],
) -> dict[str, Any]:
    return qge_resource_boundary_audit.build_resource_envelope(
        oracle_scene,
        advantage_metrics,
        conformance,
        performance,
        breadth,
    )


def build_moonlab_job_specs(
    resource_envelope: dict[str, Any],
    artifact_paths: dict[str, Any],
) -> dict[str, Any]:
    posture = dict_or_empty(resource_envelope.get("posture"))
    domains = dict_or_empty(resource_envelope.get("domains"))
    render = dict_or_empty(domains.get("render_primary_framebuffer"))
    qae = dict_or_empty(domains.get("light_transport_qae_benchmark"))
    runtime = dict_or_empty(domains.get("runtime_backend_probes"))
    breadth = dict_or_empty(domains.get("breadth_capture_matrix"))
    full_game = dict_or_empty(domains.get("full_game_map_coverage"))
    jobs = [
        {
            "job_id": "qge.render_primary_framebuffer.sparse_dwt_replay.v0",
            "domain": "render_primary_framebuffer",
            "kind": "moonlab_simulator_native_backend_replay",
            "status": render.get("status"),
            "backend_targets": [
                "moonlab_simulator",
                "qge_native_sparse_dwt_bridge",
            ],
            "hardware_candidate": False,
            "hardware_submission_status": (
                "not_applicable_full_frame_hardware_execution_not_claimed"
            ),
            "resource": {
                "candidate_count": render.get("candidate_count"),
                "register_bits": render.get("register_bits"),
                "shots_per_frame": render.get("shots_per_frame"),
                "gate_count_per_frame": render.get("gate_count_per_frame"),
                "native_backend_path": render.get("native_backend_path"),
                "native_backend_result": render.get("native_backend_result"),
            },
            "required_artifacts": {
                "oracle_scene": artifact_paths.get("oracle_scene"),
                "trace": artifact_paths.get("trace"),
                "frame": artifact_paths.get("frame"),
                "vanilla_matrix": artifact_paths.get("vanilla_matrix"),
            },
            "fallback_policy": (
                "fail closed if fallback, surrogate, or cpu_idwt counters are nonzero"
            ),
            "success_criteria": [
                "QGE primary framebuffer is produced without hidden classic fallback.",
                "Native sparse-DWT bridge is active where captured evidence claims it.",
                "Classic frame remains a reference oracle, not production output.",
            ],
        },
        {
            "job_id": "qge.light_transport_qae_benchmark.mlae.v0",
            "domain": "light_transport_qae_benchmark",
            "kind": "moonlab_qae_kernel",
            "status": qae.get("status"),
            "backend_targets": [
                "moonlab_simulator",
                "moonlab_hardware_candidate",
            ],
            "hardware_candidate": True,
            "hardware_submission_status": "not_submitted",
            "resource": {
                "logical_qubits": qae.get("logical_qubits"),
                "candidate_index_bits": qae.get("candidate_index_bits"),
                "contribution_threshold_bits": (
                    qae.get("contribution_threshold_bits")),
                "controlled_oracle_calls": qae.get("controlled_oracle_calls"),
                "one_qubit_gates": qae.get("one_qubit_gates"),
                "two_qubit_gates": qae.get("two_qubit_gates"),
                "circuit_depth": qae.get("circuit_depth"),
                "shots": qae.get("shots"),
            },
            "required_artifacts": {
                "oracle_scene": artifact_paths.get("oracle_scene"),
                "advantage_metrics": artifact_paths.get("advantage_metrics"),
                "qae_circuit": artifact_paths.get("qae_circuit"),
                "moonlab_qae_payload": artifact_paths.get(
                    "moonlab_qae_payload"),
                "moonlab_qae_oracle_kernel": artifact_paths.get(
                    "moonlab_qae_oracle_kernel"),
                "moonlab_qae_observation_zero": artifact_paths.get(
                    "moonlab_qae_observation_zero"),
                "moonlab_qae_grover_schedule_plan": artifact_paths.get(
                    "moonlab_qae_grover_schedule_plan"),
            },
            "fallback_policy": (
                "simulator result is publishable; hardware result requires backend id, "
                "shot schedule, and observed readout metadata"
            ),
            "success_criteria": [
                "Execute the bounded mean-estimation circuit against the scene oracle.",
                "Record backend identifier and shot schedule for every submitted run.",
                "Report simulator and hardware results separately.",
            ],
        },
        {
            "job_id": "qge.runtime_backend_probe.replay.v0",
            "domain": "runtime_backend_probes",
            "kind": "moonlab_runtime_boundary_replay",
            "status": runtime.get("status"),
            "backend_targets": ["qge_native_runtime_boundaries"],
            "hardware_candidate": False,
            "hardware_submission_status": "not_a_quantum_hardware_job",
            "resource": {
                "required_targets": runtime.get("required_targets"),
                "native_targets": runtime.get("native_targets"),
                "missing_targets": runtime.get("missing_targets"),
                "performance_resolved": runtime.get("performance_resolved"),
                "breadth_resolved_run_count": (
                    runtime.get("breadth_resolved_run_count")),
            },
            "required_artifacts": {
                "performance_summary": artifact_paths.get("performance_summary"),
                "breadth_evidence": artifact_paths.get("breadth_evidence"),
            },
            "fallback_policy": (
                "fail closed if required native runtime boundary targets are missing"
            ),
            "success_criteria": [
                "Every required native runtime target resolves in the captured run.",
                "Breadth evidence preserves the same target resolution across maps.",
            ],
        },
        {
            "job_id": "qge.full_game_map_coverage.ledger.v0",
            "domain": "full_game_map_coverage",
            "kind": "moonlab_coverage_ledger_replay",
            "status": full_game.get("status"),
            "backend_targets": ["qge_coverage_ledger"],
            "hardware_candidate": False,
            "hardware_submission_status": "not_a_quantum_hardware_job",
            "resource": {
                "map_set": full_game.get("map_set"),
                "target_map_count": full_game.get("target_map_count"),
                "covered_map_count": full_game.get("covered_map_count"),
                "missing_map_count": full_game.get("missing_map_count"),
                "coverage_ratio": full_game.get("coverage_ratio"),
                "missing_maps": full_game.get("missing_maps"),
            },
            "required_artifacts": {
                "full_game_map_coverage": artifact_paths.get(
                    "full_game_map_coverage"),
                "asset_inventory": artifact_paths.get("asset_inventory"),
                "asset_requirements": artifact_paths.get("asset_requirements"),
                "registered_asset_intake": artifact_paths.get(
                    "registered_asset_intake"),
            },
            "fallback_policy": (
                "ledger remains partial until every target map has a ready "
                "QGE/Moonlab evidence run"
            ),
            "success_criteria": [
                "Every canonical registered single-player map is enumerated.",
                "Covered and missing maps are recorded without implication.",
                "A whole-game claim is allowed only when missing_map_count is zero.",
            ],
        },
    ]
    hardware_candidate_count = sum(
        1 for job in jobs if bool(job.get("hardware_candidate")))
    return {
        "schema": "qge.moonlab_job_specs.v0",
        "posture": {
            "whole_game_hardware_execution_claimed": bool(
                posture.get("whole_game_hardware_execution_claimed")),
            "hardware_quantum_advantage_claimed": bool(
                posture.get("hardware_quantum_advantage_claimed")),
            "dense_70000_qubit_state_claimed": bool(
                posture.get("dense_70000_qubit_state_claimed")),
            "moonlab_simulator_path_claimed": bool(
                posture.get("moonlab_simulator_path_claimed")),
        },
        "submission_scope": (
            "selected Moonlab simulator/native-backend jobs with one "
            "hardware-candidate benchmark kernel; no whole-game hardware run"
        ),
        "selected_job_count": len(jobs),
        "hardware_candidate_job_count": hardware_candidate_count,
        "breadth_map_count": breadth.get("map_count"),
        "full_game_map_coverage_status": full_game.get("status"),
        "full_game_map_covered_count": full_game.get("covered_map_count"),
        "full_game_map_target_count": full_game.get("target_map_count"),
        "jobs": jobs,
        "limits": [
            "Hardware-candidate jobs are not hardware results until submitted.",
            "Full-frame render replay is a simulator/native-backend evidence job.",
            "No unrestricted dense all-game state is submitted or claimed.",
        ],
    }


def resolve_vanilla_icc_evidence_path(
    vanilla_matrix: Path,
    graphics_capture_dir: Path | None,
) -> Path | None:
    candidates: list[Path] = []
    if graphics_capture_dir is not None:
        candidates.append(graphics_capture_dir / "qge_vanilla_icc_evidence.json")
    candidates.append(vanilla_matrix.parent / "qge_vanilla_icc_evidence.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def latest_file(pattern: str) -> Path | None:
    matches = sorted(REPO_ROOT.glob(pattern),
                     key=lambda path: path.stat().st_mtime if path.exists() else 0)
    return matches[-1] if matches else None


def latest_capture_dir() -> Path | None:
    candidates = [
        path.parent for path in REPO_ROOT.glob("diagnostics/quake_stream/*/qge_trace.bin")
    ]
    candidates = [path for path in candidates if (path / "quantum_quake.log").is_file()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.stat().st_mtime)[-1]


def read_readme_value(path: Path, label: str) -> str | None:
    if not path.is_file():
        return None
    prefix = f"{label}:"
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(prefix):
                return line.split(":", 1)[1].strip()
    return None


def pack_file(src: Path | None, outdir: Path, rel: str) -> dict[str, Any]:
    if src is None or not src.is_file():
        return {
            "source_path": str(src) if src else None,
            "packed": file_info(None),
        }
    dest = outdir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return {
        "source_path": str(src),
        "packed": file_info(dest),
    }


def pack_directory(src: Path | None, outdir: Path, rel: str) -> dict[str, Any]:
    if src is None or not src.is_dir():
        return {
            "source_path": str(src) if src else None,
            "packed": directory_info(None),
        }
    dest = outdir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, dirs_exist_ok=True)
    return {
        "source_path": str(src),
        "packed": directory_info(dest),
    }


def build_oracle_artifacts(capture_dir: Path,
                           claims_path: Path,
                           outdir: Path) -> dict[str, Any]:
    oracle_scene, claims_evidence = qge_oracle_export.build_oracle_scene(
        capture_dir, claims_path)
    oracle_path = outdir / "oracle_scene.json"
    claims_path_out = outdir / "claims_evidence.json"
    icc_path = outdir / "qge_icc_evidence.json"
    qge_oracle_export.write_json(oracle_path, oracle_scene)
    qge_oracle_export.write_json(claims_path_out, claims_evidence)
    qge_oracle_export.write_json(
        icc_path,
        qge_oracle_export.build_icc_evidence(
            oracle_scene, claims_evidence, oracle_path, claims_path_out),
    )
    return {
        "oracle_scene": file_info(oracle_path),
        "claims_evidence": file_info(claims_path_out),
        "icc_evidence": file_info(icc_path),
        "oracle_scene_data": oracle_scene,
        "claims_evidence_data": claims_evidence,
    }


def build_advantage_artifacts(oracle_scene_path: Path,
                              oracle_scene: dict[str, Any],
                              outdir: Path,
                              args: argparse.Namespace) -> dict[str, Any]:
    bench_args = SimpleNamespace(
        oracle_scene=oracle_scene_path,
        outdir=outdir,
        seed=args.seed,
        trials=args.trials,
        samples=args.samples,
        qae_levels=args.qae_levels,
        qae_shots=args.qae_shots,
        qae_grid_steps=args.qae_grid_steps,
        contribution_bits=args.contribution_bits,
    )
    metrics = qge_advantage_benchmark.build_metrics(bench_args, oracle_scene)
    metrics_path = outdir / "advantage_metrics.json"
    curve_path = outdir / "qae_curve.csv"
    circuit_path = outdir / "qae_circuit.txt"
    moonlab_payload_path = outdir / "qae_moonlab_payload.json"
    moonlab_payload_markdown_path = outdir / "qae_moonlab_payload.md"
    moonlab_payload_icc_path = outdir / "qae_moonlab_payload_icc_evidence.json"
    moonlab_circuit_dir = outdir / "moonlab_qae_circuits"
    moonlab_oracle_kernel_path = outdir / "qae_moonlab_oracle_kernel.json"
    moonlab_oracle_kernel_circuit_path = (
        outdir / "qae_moonlab_oracle_kernel.moonlab")
    moonlab_oracle_kernel_markdown_path = (
        outdir / "qae_moonlab_oracle_kernel.md")
    moonlab_oracle_kernel_icc_path = (
        outdir / "qae_moonlab_oracle_kernel_icc_evidence.json")
    moonlab_observation_path = outdir / "qae_moonlab_observation_zero.json"
    moonlab_observation_circuit_path = (
        outdir / "qae_moonlab_observation_zero.moonlab")
    moonlab_observation_markdown_path = (
        outdir / "qae_moonlab_observation_zero.md")
    moonlab_observation_icc_path = (
        outdir / "qae_moonlab_observation_zero_icc_evidence.json")
    moonlab_grover_plan_path = (
        outdir / "qae_moonlab_grover_schedule_plan.json")
    moonlab_grover_plan_markdown_path = (
        outdir / "qae_moonlab_grover_schedule_plan.md")
    moonlab_grover_plan_icc_path = (
        outdir / "qae_moonlab_grover_schedule_plan_icc_evidence.json")
    moonlab_grover_circuit_dir = outdir / "qae_moonlab_grover_circuits"
    scaling_path = outdir / "scaling_summary.json"
    scaling_csv_path = outdir / "scaling_summary.csv"
    icc_path = outdir / "qge_advantage_icc_evidence.json"
    qge_advantage_benchmark.write_json(metrics_path, metrics)
    qge_advantage_benchmark.write_curve_csv(curve_path, metrics)
    qge_advantage_benchmark.write_json(scaling_path,
                                       metrics["scaling_summary"])
    qge_advantage_benchmark.write_scaling_csv(scaling_csv_path, metrics)
    qge_advantage_benchmark.write_circuit_text(circuit_path, metrics)
    moonlab_payload = qge_moonlab_qae_transpile.build_payload(
        metrics,
        metrics_path=metrics_path,
        abstract_circuit_path=circuit_path,
        circuit_dir=moonlab_circuit_dir,
    )
    write_json(moonlab_payload_path, moonlab_payload)
    moonlab_payload_markdown_path.write_text(
        qge_moonlab_qae_transpile.markdown_report(moonlab_payload),
        encoding="utf-8",
    )
    moonlab_payload_icc = qge_moonlab_qae_transpile.build_icc_evidence(
        moonlab_payload,
        out_path=moonlab_payload_path,
    )
    write_json(moonlab_payload_icc_path, moonlab_payload_icc)
    moonlab_oracle_kernel = qge_moonlab_oracle_transpile.build_kernel(
        metrics,
        oracle_scene,
        metrics_path=metrics_path,
        oracle_scene_path=oracle_scene_path,
        circuit_path=moonlab_oracle_kernel_circuit_path,
    )
    write_json(moonlab_oracle_kernel_path, moonlab_oracle_kernel)
    moonlab_oracle_kernel_markdown_path.write_text(
        qge_moonlab_oracle_transpile.markdown_report(
            moonlab_oracle_kernel),
        encoding="utf-8",
    )
    moonlab_oracle_kernel_icc = (
        qge_moonlab_oracle_transpile.build_icc_evidence(
            moonlab_oracle_kernel,
            out_path=moonlab_oracle_kernel_path,
        )
    )
    write_json(moonlab_oracle_kernel_icc_path, moonlab_oracle_kernel_icc)
    moonlab_observation = (
        qge_moonlab_qae_observation_transpile.build_observation_circuit(
            metrics,
            oracle_scene,
            metrics_path=metrics_path,
            oracle_scene_path=oracle_scene_path,
            circuit_path=moonlab_observation_circuit_path,
        )
    )
    write_json(moonlab_observation_path, moonlab_observation)
    moonlab_observation_markdown_path.write_text(
        qge_moonlab_qae_observation_transpile.markdown_report(
            moonlab_observation),
        encoding="utf-8",
    )
    moonlab_observation_icc = (
        qge_moonlab_qae_observation_transpile.build_icc_evidence(
            moonlab_observation,
            out_path=moonlab_observation_path,
        )
    )
    write_json(moonlab_observation_icc_path, moonlab_observation_icc)
    moonlab_grover_plan = qge_moonlab_qae_grover_plan.build_schedule_plan(
        metrics,
        oracle_scene,
        metrics_path=metrics_path,
        oracle_scene_path=oracle_scene_path,
        circuit_dir=moonlab_grover_circuit_dir,
    )
    write_json(moonlab_grover_plan_path, moonlab_grover_plan)
    moonlab_grover_plan_markdown_path.write_text(
        qge_moonlab_qae_grover_plan.markdown_report(moonlab_grover_plan),
        encoding="utf-8",
    )
    moonlab_grover_plan_icc = qge_moonlab_qae_grover_plan.build_icc_evidence(
        moonlab_grover_plan,
        out_path=moonlab_grover_plan_path,
    )
    write_json(moonlab_grover_plan_icc_path, moonlab_grover_plan_icc)
    advantage_icc = qge_advantage_benchmark.build_icc_evidence(
        metrics, metrics_path, curve_path, circuit_path, scaling_path)
    qge_advantage_benchmark.write_json(
        icc_path,
        advantage_icc,
    )
    return {
        "metrics": file_info(metrics_path),
        "qae_curve": file_info(curve_path),
        "qae_circuit": file_info(circuit_path),
        "qae_moonlab_payload": file_info(moonlab_payload_path),
        "qae_moonlab_payload_markdown": file_info(
            moonlab_payload_markdown_path),
        "qae_moonlab_payload_icc_evidence": file_info(
            moonlab_payload_icc_path),
        "qae_moonlab_payload_icc_evidence_data": moonlab_payload_icc,
        "qae_moonlab_circuits": directory_info(moonlab_circuit_dir),
        "qae_moonlab_payload_data": moonlab_payload,
        "qae_moonlab_oracle_kernel": file_info(moonlab_oracle_kernel_path),
        "qae_moonlab_oracle_kernel_circuit": file_info(
            moonlab_oracle_kernel_circuit_path),
        "qae_moonlab_oracle_kernel_markdown": file_info(
            moonlab_oracle_kernel_markdown_path),
        "qae_moonlab_oracle_kernel_icc_evidence": file_info(
            moonlab_oracle_kernel_icc_path),
        "qae_moonlab_oracle_kernel_icc_evidence_data": (
            moonlab_oracle_kernel_icc),
        "qae_moonlab_oracle_kernel_data": moonlab_oracle_kernel,
        "qae_moonlab_observation_zero": file_info(moonlab_observation_path),
        "qae_moonlab_observation_zero_circuit": file_info(
            moonlab_observation_circuit_path),
        "qae_moonlab_observation_zero_markdown": file_info(
            moonlab_observation_markdown_path),
        "qae_moonlab_observation_zero_icc_evidence": file_info(
            moonlab_observation_icc_path),
        "qae_moonlab_observation_zero_icc_evidence_data": (
            moonlab_observation_icc),
        "qae_moonlab_observation_zero_data": moonlab_observation,
        "qae_moonlab_grover_schedule_plan": file_info(
            moonlab_grover_plan_path),
        "qae_moonlab_grover_schedule_plan_markdown": file_info(
            moonlab_grover_plan_markdown_path),
        "qae_moonlab_grover_schedule_plan_icc_evidence": file_info(
            moonlab_grover_plan_icc_path),
        "qae_moonlab_grover_schedule_plan_icc_evidence_data": (
            moonlab_grover_plan_icc),
        "qae_moonlab_grover_circuits": directory_info(
            moonlab_grover_circuit_dir),
        "qae_moonlab_grover_schedule_plan_data": moonlab_grover_plan,
        "scaling_summary": file_info(scaling_path),
        "scaling_summary_csv": file_info(scaling_csv_path),
        "icc_evidence": file_info(icc_path),
        "icc_evidence_data": advantage_icc,
        "metrics_data": metrics,
    }


def resolve_inputs(args: argparse.Namespace) -> dict[str, Path | None]:
    capture_dir = args.capture_dir or latest_capture_dir()
    vanilla_matrix = args.vanilla_matrix or latest_file(
        "diagnostics/quake_graphics/*/vanilla_capture_matrix.json")
    graphics_capture_dir = args.graphics_capture_dir
    if graphics_capture_dir is None and vanilla_matrix is not None:
        candidate = vanilla_matrix.parent
        if (candidate / "quantum.qge_perf_summary.json").is_file():
            graphics_capture_dir = candidate
    agent_stream = args.agent_stream_dir
    if agent_stream is None and capture_dir is not None:
        value = read_readme_value(capture_dir / "README.txt", "Agent stream")
        if value:
            candidate = Path(value)
            agent_stream = candidate if candidate.is_dir() else None
    return {
        "capture_dir": capture_dir,
        "vanilla_matrix": vanilla_matrix,
        "graphics_capture_dir": graphics_capture_dir,
        "agent_stream_dir": agent_stream,
        "breadth_evidence": resolve_breadth_evidence_path(
            getattr(args, "breadth_evidence", None)),
    }


def publication_performance_paths(
    capture_dir: Path,
    graphics_capture_dir: Path | None,
) -> tuple[Path, Path, str]:
    if graphics_capture_dir is not None:
        summary = graphics_capture_dir / "quantum.qge_perf_summary.json"
        evidence = graphics_capture_dir / "quantum.qge_perf_icc_evidence.json"
        if summary.is_file():
            return summary, evidence, "graphics_qge_candidate"
    return (
        capture_dir / "qge_perf_summary.json",
        capture_dir / "qge_perf_icc_evidence.json",
        "stream_capture",
    )


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    inputs = resolve_inputs(args)
    capture_dir = inputs["capture_dir"]
    vanilla_matrix = inputs["vanilla_matrix"]
    graphics_capture_dir = inputs["graphics_capture_dir"]
    agent_stream_dir = inputs["agent_stream_dir"]
    breadth_evidence = inputs["breadth_evidence"]
    claims_path = args.claims
    if capture_dir is None or not capture_dir.is_dir():
        raise ValueError("no capture directory with qge_trace.bin was found")
    if not (capture_dir / "qge_trace.bin").is_file():
        raise ValueError(f"capture is missing qge_trace.bin: {capture_dir}")
    if vanilla_matrix is None or not vanilla_matrix.is_file():
        raise ValueError("no vanilla_capture_matrix.json was found")
    if not claims_path.is_file():
        raise ValueError(f"claims ledger not found: {claims_path}")

    args.outdir.mkdir(parents=True, exist_ok=True)
    oracle = build_oracle_artifacts(capture_dir, claims_path,
                                    args.outdir / "oracle")
    oracle_scene_path = args.outdir / "oracle" / "oracle_scene.json"
    advantage = build_advantage_artifacts(oracle_scene_path,
                                          oracle["oracle_scene_data"],
                                          args.outdir / "advantage",
                                          args)
    vanilla = load_json(vanilla_matrix)
    vanilla_icc_evidence = resolve_vanilla_icc_evidence_path(
        vanilla_matrix, graphics_capture_dir)
    conformance = vanilla.get("conformance_summary", {})
    perf_summary_path, perf_icc_path, perf_source = publication_performance_paths(
        capture_dir, graphics_capture_dir)
    agent_manifest = (
        agent_stream_dir / "manifest.json"
        if agent_stream_dir is not None else None
    )
    agent_stream_summary = agent_manifest_summary(agent_manifest)
    capture_perf_summary = performance_summary(perf_summary_path)
    breadth_summary = breadth_evidence_summary(breadth_evidence)
    breadth_icc_evidence = (
        breadth_evidence.parent / "qge_breadth_icc_evidence.json"
        if breadth_evidence is not None else None
    )
    agent_icc = (
        agent_stream_dir / "qge_agent_stream_icc_evidence.jsonl"
        if agent_stream_dir is not None else None
    )
    source_docs = {
        "claims_ledger": pack_file(claims_path, args.outdir,
                                   "source/docs/qge_claims.json"),
        "scene_oracle_ir": pack_file(REPO_ROOT / "docs/qge_scene_oracle_ir.md",
                                     args.outdir,
                                     "source/docs/qge_scene_oracle_ir.md"),
        "architecture": pack_file(REPO_ROOT / "docs/qge_engine_architecture.md",
                                  args.outdir,
                                  "source/docs/qge_engine_architecture.md"),
        "advantage_roadmap": pack_file(
            REPO_ROOT / "docs/qge_quantum_advantage_research_roadmap.md",
            args.outdir,
            "source/docs/qge_quantum_advantage_research_roadmap.md"),
    }
    capture_artifacts = {
        "trace": pack_file(capture_dir / "qge_trace.bin", args.outdir,
                           "capture/qge_trace.bin"),
        "frame": pack_file(capture_dir / "frame_001.png", args.outdir,
                           "capture/frame_001.png"),
        "log": pack_file(capture_dir / "quantum_quake.log", args.outdir,
                         "capture/quantum_quake.log"),
        "performance_summary": pack_file(
            perf_summary_path, args.outdir,
            "capture/qge_perf_summary.json"),
        "performance_icc_evidence": pack_file(
            perf_icc_path, args.outdir,
            "capture/qge_perf_icc_evidence.json"),
        "readme": pack_file(capture_dir / "README.txt", args.outdir,
                            "capture/README.txt"),
    }
    vanilla_artifacts = {
        "matrix": pack_file(vanilla_matrix, args.outdir,
                            "vanilla/vanilla_capture_matrix.json"),
        "icc_evidence": pack_file(
            vanilla_icc_evidence, args.outdir,
            "vanilla/qge_vanilla_icc_evidence.json"),
        "classic_frame": pack_file(
            Path(vanilla.get("modes", [{}])[0].get("frame", {}).get("path", "")),
            args.outdir,
            "vanilla/classic.png"),
        "qge_frame": pack_file(
            Path(vanilla.get("modes", [{}, {}])[-1].get("frame", {}).get("path", "")),
            args.outdir,
            "vanilla/quantum.png"),
    }
    agent_artifacts = {
        "stream_directory": pack_directory(agent_stream_dir, args.outdir,
                                           "agent_stream"),
        "manifest": pack_file(agent_manifest, args.outdir,
                              "agent_stream/manifest.json"),
        "events": pack_file(
            agent_stream_dir / "events.ndjson"
            if agent_stream_dir is not None else None,
            args.outdir,
            "agent_stream/events.ndjson"),
        "icc_evidence": pack_file(agent_icc, args.outdir,
                                  "agent_stream/qge_agent_stream_icc_evidence.jsonl"),
    }
    breadth_artifacts = {
        "evidence": pack_file(breadth_evidence, args.outdir,
                              "breadth/breadth_evidence.json"),
        "icc_evidence": pack_file(breadth_icc_evidence, args.outdir,
                                  "breadth/qge_breadth_icc_evidence.json"),
    }
    metrics = advantage["metrics_data"]
    agent_stream_manifest_ok = not explicit_agent_run_failure(
        agent_stream_summary)
    performance_ok = not explicit_performance_failure(capture_perf_summary)
    breadth_evidence_ok = not explicit_breadth_evidence_failure(
        breadth_summary)
    vanilla_performance_ok = (
        conformance.get("performance_sidecars_success") is not False
    )
    publication_ready = (
        bool(conformance.get("ready_for_complete_claim")) and
        conformance.get("agent_stream_runs_success") is not False and
        agent_stream_manifest_ok and
        vanilla_performance_ok and
        performance_ok and
        breadth_evidence_ok
    )
    resource_envelope = build_resource_envelope(
        oracle["oracle_scene_data"],
        metrics,
        conformance,
        capture_perf_summary,
        breadth_summary,
    )
    resource_path = args.outdir / "resource" / "qge_resource_envelope.json"
    write_json(resource_path, resource_envelope)
    full_game_map_coverage = full_game_coverage_from_summary(
        breadth_summary.get("full_game_coverage"),
        breadth_summary.get("maps")
        if isinstance(breadth_summary.get("maps"), list) else [],
    )
    full_game_map_coverage_path = (
        args.outdir / "resource" / "qge_full_game_map_coverage.json"
    )
    write_json(full_game_map_coverage_path, full_game_map_coverage)
    asset_inventory = qge_asset_inventory.build_inventory(
        Path(getattr(args, "asset_root", qge_asset_inventory.DEFAULT_ASSET_ROOT)),
        map_set=str(
            full_game_map_coverage.get("map_set") or
            qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET
        ),
    )
    asset_inventory_path = (
        args.outdir / "resource" / "qge_asset_inventory.json"
    )
    write_json(asset_inventory_path, asset_inventory)
    asset_inventory_icc = qge_asset_inventory.build_icc_evidence(
        asset_inventory)
    asset_inventory_icc["asset_inventory_file"] = str(asset_inventory_path)
    asset_inventory_icc_path = (
        args.outdir / "resource" / "qge_asset_inventory_icc_evidence.json"
    )
    write_json(asset_inventory_icc_path, asset_inventory_icc)
    asset_requirements = qge_asset_requirements.build_requirements(
        asset_inventory,
        map_set=str(
            full_game_map_coverage.get("map_set") or
            qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET
        ),
    )
    asset_requirements_path = (
        args.outdir / "resource" / "qge_asset_requirements.json"
    )
    write_json(asset_requirements_path, asset_requirements)
    asset_requirements_markdown_path = (
        args.outdir / "resource" / "qge_asset_requirements.md"
    )
    asset_requirements_markdown_path.write_text(
        qge_asset_requirements.markdown_report(asset_requirements),
        encoding="utf-8",
    )
    asset_requirements_icc = qge_asset_requirements.build_icc_evidence(
        asset_requirements,
        out_path=asset_requirements_path,
    )
    asset_requirements_icc_path = (
        args.outdir / "resource" / "qge_asset_requirements_icc_evidence.json"
    )
    write_json(asset_requirements_icc_path, asset_requirements_icc)
    registered_asset_candidates = list(
        getattr(args, "registered_asset_candidate", []) or [])
    registered_asset_discovery_roots = list(
        getattr(args, "registered_asset_discover_root", []) or [])
    if getattr(args, "registered_asset_discover_common", False):
        registered_asset_discovery_roots.extend(
            qge_registered_asset_intake.common_discovery_roots())
    registered_asset_discovery = None
    if registered_asset_discovery_roots:
        registered_asset_discovery = (
            qge_registered_asset_intake.discover_candidate_paths(
                registered_asset_discovery_roots,
                max_depth=getattr(
                    args, "registered_asset_discover_max_depth", 5),
            )
        )
        registered_asset_candidates.extend(
            Path(entry["path"])
            for entry in list_or_empty(
                registered_asset_discovery.get("found_candidates"))
            if isinstance(entry, dict) and isinstance(entry.get("path"), str)
        )
    registered_asset_intake = qge_registered_asset_intake.build_intake(
        Path(getattr(args, "asset_root", qge_asset_inventory.DEFAULT_ASSET_ROOT)),
        registered_asset_candidates,
        map_set=str(
            full_game_map_coverage.get("map_set") or
            qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET
        ),
        discovery=registered_asset_discovery,
        publication_pack_dir=args.outdir,
    )
    registered_asset_intake_path = (
        args.outdir / "resource" / "qge_registered_asset_intake.json"
    )
    write_json(registered_asset_intake_path, registered_asset_intake)
    registered_asset_intake_markdown_path = (
        args.outdir / "resource" / "qge_registered_asset_intake.md"
    )
    registered_asset_intake_markdown_path.write_text(
        qge_registered_asset_intake.markdown_report(registered_asset_intake),
        encoding="utf-8",
    )
    registered_asset_intake_script_path = (
        args.outdir / "resource" / "install_registered_assets.sh"
    )
    registered_asset_intake_script_path.write_text(
        "\n".join(qge_registered_asset_intake.script_lines(
            registered_asset_intake)),
        encoding="utf-8",
    )
    registered_asset_intake_script_path.chmod(
        registered_asset_intake_script_path.stat().st_mode | 0o111)
    registered_asset_intake_icc = (
        qge_registered_asset_intake.build_icc_evidence(
            registered_asset_intake,
            out_path=registered_asset_intake_path,
        )
    )
    registered_asset_intake_icc_path = (
        args.outdir / "resource" /
        "qge_registered_asset_intake_icc_evidence.json"
    )
    write_json(registered_asset_intake_icc_path, registered_asset_intake_icc)
    native_backend_boundary = (
        qge_resource_boundary_audit.expected_native_backend_boundary(
            capture_perf_summary)
    )
    native_backend_boundary_path = (
        args.outdir / "resource" / "qge_native_backend_boundary.json"
    )
    write_json(native_backend_boundary_path, native_backend_boundary)
    moonlab_job_specs = build_moonlab_job_specs(
        resource_envelope,
        {
            "oracle_scene": oracle["oracle_scene"]["path"],
            "advantage_metrics": advantage["metrics"]["path"],
            "qae_circuit": advantage["qae_circuit"]["path"],
            "moonlab_qae_payload": advantage["qae_moonlab_payload"]["path"],
            "moonlab_qae_oracle_kernel": (
                advantage["qae_moonlab_oracle_kernel"]["path"]),
            "moonlab_qae_observation_zero": (
                advantage["qae_moonlab_observation_zero"]["path"]),
            "moonlab_qae_grover_schedule_plan": (
                advantage["qae_moonlab_grover_schedule_plan"]["path"]),
            "moonlab_qae_grover_circuits": (
                advantage["qae_moonlab_grover_circuits"]["path"]),
            "trace": capture_artifacts["trace"]["packed"]["path"],
            "frame": capture_artifacts["frame"]["packed"]["path"],
            "vanilla_matrix": vanilla_artifacts["matrix"]["packed"]["path"],
            "performance_summary": (
                capture_artifacts["performance_summary"]["packed"]["path"]),
            "breadth_evidence": (
                breadth_artifacts["evidence"]["packed"]["path"]),
            "full_game_map_coverage": str(full_game_map_coverage_path),
            "asset_inventory": str(asset_inventory_path),
            "asset_requirements": str(asset_requirements_path),
            "registered_asset_intake": str(registered_asset_intake_path),
        },
    )
    moonlab_job_specs_path = (
        args.outdir / "resource" / "qge_moonlab_job_specs.json"
    )
    write_json(moonlab_job_specs_path, moonlab_job_specs)
    moonlab_job_results = (
        qge_moonlab_job_runner.build_moonlab_job_results(moonlab_job_specs)
    )
    moonlab_job_results_path = (
        args.outdir / "resource" / "qge_moonlab_job_results.json"
    )
    write_json(moonlab_job_results_path, moonlab_job_results)
    moonlab_replay_plan = qge_moonlab_job_runner.build_moonlab_replay_plan(
        moonlab_job_specs,
        moonlab_job_results,
        job_specs_path=moonlab_job_specs_path,
        job_results_path=moonlab_job_results_path,
    )
    moonlab_replay_plan_path = (
        args.outdir / "resource" / "qge_moonlab_replay_plan.json"
    )
    write_json(moonlab_replay_plan_path, moonlab_replay_plan)
    moonlab_submission_packet = (
        qge_moonlab_job_runner.build_moonlab_submission_packet(
            moonlab_job_specs,
            moonlab_job_results,
            job_specs_path=moonlab_job_specs_path,
            job_results_path=moonlab_job_results_path,
        )
    )
    moonlab_submission_packet_path = (
        args.outdir / "resource" / "qge_moonlab_submission_packet.json"
    )
    write_json(moonlab_submission_packet_path, moonlab_submission_packet)
    moonlab_submission_bundle = (
        qge_moonlab_submission_bundle.build_submission_bundle(
            moonlab_submission_packet,
            packet_path=moonlab_submission_packet_path,
        )
    )
    moonlab_submission_bundle_path = (
        args.outdir / "resource" / "qge_moonlab_submission_bundle.json"
    )
    write_json(moonlab_submission_bundle_path, moonlab_submission_bundle)
    moonlab_submission_bundle_markdown_path = (
        args.outdir / "resource" / "qge_moonlab_submission_bundle.md"
    )
    moonlab_submission_bundle_markdown_path.write_text(
        qge_moonlab_submission_bundle.markdown_report(
            moonlab_submission_bundle),
        encoding="utf-8",
    )
    moonlab_submission_bundle_icc = (
        qge_moonlab_submission_bundle.build_icc_evidence(
            moonlab_submission_bundle,
            out_path=moonlab_submission_bundle_path,
        )
    )
    moonlab_submission_bundle_icc_path = (
        args.outdir / "resource" /
        "qge_moonlab_submission_bundle_icc_evidence.json"
    )
    write_json(
        moonlab_submission_bundle_icc_path,
        moonlab_submission_bundle_icc,
    )
    moonlab_hardware_record_template = (
        qge_moonlab_hardware_ingest.build_hardware_record_template(
            moonlab_submission_packet)
    )
    moonlab_hardware_record_template_path = (
        args.outdir / "resource" / "qge_moonlab_hardware_record_template.json"
    )
    write_json(
        moonlab_hardware_record_template_path,
        moonlab_hardware_record_template,
    )
    moonlab_hardware_submission_scope = (
        qge_moonlab_submission_bundle.build_hardware_submission_scope(
            moonlab_submission_packet,
            moonlab_submission_bundle,
            moonlab_hardware_record_template,
            packet_path=moonlab_submission_packet_path,
            bundle_path=moonlab_submission_bundle_path,
            hardware_template_path=moonlab_hardware_record_template_path,
        )
    )
    moonlab_hardware_submission_scope_path = (
        args.outdir / "resource" / "qge_moonlab_hardware_submission_scope.json"
    )
    write_json(
        moonlab_hardware_submission_scope_path,
        moonlab_hardware_submission_scope,
    )
    moonlab_hardware_submission_scope_icc = (
        qge_moonlab_submission_bundle.build_scope_icc_evidence(
            moonlab_hardware_submission_scope,
            out_path=moonlab_hardware_submission_scope_path,
        )
    )
    moonlab_hardware_submission_scope_icc_path = (
        args.outdir / "resource" /
        "qge_moonlab_hardware_submission_scope_icc_evidence.json"
    )
    write_json(
        moonlab_hardware_submission_scope_icc_path,
        moonlab_hardware_submission_scope_icc,
    )
    moonlab_full_game_plan = qge_moonlab_full_game_plan.build_plan(
        full_game_map_coverage,
        asset_inventory,
        source_path=args.outdir,
        breadth_evidence=load_json(breadth_evidence)
        if breadth_evidence is not None and breadth_evidence.is_file()
        else None,
        moonlab_job_results=moonlab_job_results,
        submission_packet=moonlab_submission_packet,
        hardware_record_template=moonlab_hardware_record_template,
        registered_asset_intake=registered_asset_intake,
    )
    moonlab_full_game_plan_path = (
        args.outdir / "resource" / "qge_moonlab_full_game_plan.json"
    )
    write_json(moonlab_full_game_plan_path, moonlab_full_game_plan)
    moonlab_full_game_plan_markdown_path = (
        args.outdir / "resource" / "qge_moonlab_full_game_plan.md"
    )
    moonlab_full_game_plan_markdown_path.write_text(
        qge_moonlab_full_game_plan.markdown_report(moonlab_full_game_plan),
        encoding="utf-8",
    )
    moonlab_full_game_plan_icc = (
        qge_moonlab_full_game_plan.build_icc_evidence(
            moonlab_full_game_plan,
            out_path=moonlab_full_game_plan_path,
        )
    )
    moonlab_full_game_plan_icc_path = (
        args.outdir / "resource" /
        "qge_moonlab_full_game_plan_icc_evidence.json"
    )
    write_json(moonlab_full_game_plan_icc_path, moonlab_full_game_plan_icc)
    moonlab_deployment_gate = qge_moonlab_deployment_gate.build_gate(
        full_game_map_coverage,
        asset_inventory,
        asset_requirements,
        moonlab_full_game_plan,
        moonlab_job_specs,
        moonlab_job_results,
        moonlab_submission_packet,
        moonlab_hardware_record_template,
        submission_bundle=moonlab_submission_bundle,
        hardware_submission_scope=moonlab_hardware_submission_scope,
        artifact_paths={
            "asset_inventory": str(asset_inventory_path),
            "asset_requirements": str(asset_requirements_path),
            "registered_asset_intake": str(registered_asset_intake_path),
            "moonlab_full_game_plan": str(moonlab_full_game_plan_path),
            "moonlab_submission_packet": str(moonlab_submission_packet_path),
            "moonlab_submission_bundle": str(moonlab_submission_bundle_path),
            "moonlab_hardware_record_template": str(
                moonlab_hardware_record_template_path),
            "moonlab_hardware_submission_scope": str(
                moonlab_hardware_submission_scope_path),
            "advantage_metrics": str(args.outdir / "advantage" /
                                     "advantage_metrics.json"),
            "qae_curve": str(args.outdir / "advantage" / "qae_curve.csv"),
            "qae_circuit": str(args.outdir / "advantage" / "qae_circuit.txt"),
            "scaling_summary": str(args.outdir / "advantage" /
                                   "scaling_summary.json"),
            "qae_moonlab_payload": str(args.outdir / "advantage" /
                                       "qae_moonlab_payload.json"),
            "qae_moonlab_oracle_kernel": str(
                args.outdir / "advantage" /
                "qae_moonlab_oracle_kernel.json"),
            "qae_moonlab_observation_zero": str(
                args.outdir / "advantage" /
                "qae_moonlab_observation_zero.json"),
            "qae_moonlab_grover_schedule_plan": str(
                args.outdir / "advantage" /
                "qae_moonlab_grover_schedule_plan.json"),
        },
        registered_asset_intake=registered_asset_intake,
        resource_icc_evidence={
            "asset_inventory_icc_evidence": asset_inventory_icc,
            "asset_requirements_icc_evidence": asset_requirements_icc,
            "registered_asset_intake_icc_evidence": (
                registered_asset_intake_icc),
        },
        resource_icc_evidence_required=True,
        source_icc_evidence={
            "moonlab_submission_bundle_icc_evidence": (
                moonlab_submission_bundle_icc),
            "moonlab_hardware_submission_scope_icc_evidence": (
                moonlab_hardware_submission_scope_icc),
            "moonlab_full_game_plan_icc_evidence": (
                moonlab_full_game_plan_icc),
        },
        source_icc_evidence_required=True,
        advantage_artifacts={
            "advantage_metrics": advantage["metrics_data"],
            "qae_moonlab_payload": advantage["qae_moonlab_payload_data"],
            "qae_moonlab_oracle_kernel": (
                advantage["qae_moonlab_oracle_kernel_data"]),
            "qae_moonlab_observation_zero": (
                advantage["qae_moonlab_observation_zero_data"]),
            "qae_moonlab_grover_schedule_plan": (
                advantage["qae_moonlab_grover_schedule_plan_data"]),
        },
        advantage_icc_evidence={
            "advantage_icc_evidence": advantage["icc_evidence_data"],
            "qae_moonlab_payload_icc_evidence": (
                advantage["qae_moonlab_payload_icc_evidence_data"]),
            "qae_moonlab_oracle_kernel_icc_evidence": (
                advantage["qae_moonlab_oracle_kernel_icc_evidence_data"]),
            "qae_moonlab_observation_zero_icc_evidence": (
                advantage["qae_moonlab_observation_zero_icc_evidence_data"]),
            "qae_moonlab_grover_schedule_plan_icc_evidence": (
                advantage[
                    "qae_moonlab_grover_schedule_plan_icc_evidence_data"]),
        },
        advantage_icc_evidence_required=True,
        resource_envelope=resource_envelope,
        native_backend_boundary=native_backend_boundary,
        resource_boundary_sources={
            "oracle_scene": oracle["oracle_scene_data"],
            "advantage_metrics": metrics,
            "vanilla_matrix": vanilla,
            "conformance_summary": conformance,
            "performance_summary": load_json(perf_summary_path)
            if perf_summary_path is not None and perf_summary_path.is_file()
            else {},
            "breadth_evidence": load_json(breadth_evidence)
            if breadth_evidence is not None and breadth_evidence.is_file()
            else {},
        },
        resource_boundary_required=True,
        asset_remediation=(
            qge_moonlab_deployment_gate.asset_remediation_from_intake(
                registered_asset_intake,
                intake_path=registered_asset_intake_path,
                markdown_path=registered_asset_intake_markdown_path,
                script_path=registered_asset_intake_script_path,
                icc_evidence_path=registered_asset_intake_icc_path,
            )
        ),
        source_path=args.outdir,
    )
    moonlab_deployment_gate_path = (
        args.outdir / "resource" / "qge_moonlab_deployment_gate.json"
    )
    write_json(moonlab_deployment_gate_path, moonlab_deployment_gate)
    moonlab_deployment_gate_markdown_path = (
        args.outdir / "resource" / "qge_moonlab_deployment_gate.md"
    )
    moonlab_deployment_gate_markdown_path.write_text(
        qge_moonlab_deployment_gate.markdown_report(moonlab_deployment_gate),
        encoding="utf-8",
    )
    moonlab_deployment_gate_icc = (
        qge_moonlab_deployment_gate.build_icc_evidence(
            moonlab_deployment_gate,
            out_path=moonlab_deployment_gate_path,
        )
    )
    moonlab_deployment_gate_icc_path = (
        args.outdir / "resource" /
        "qge_moonlab_deployment_gate_icc_evidence.json"
    )
    write_json(moonlab_deployment_gate_icc_path, moonlab_deployment_gate_icc)
    resource_artifacts = {
        "envelope": file_info(resource_path),
        "full_game_map_coverage": file_info(full_game_map_coverage_path),
        "asset_inventory": file_info(asset_inventory_path),
        "asset_inventory_icc_evidence": file_info(asset_inventory_icc_path),
        "asset_requirements": file_info(asset_requirements_path),
        "asset_requirements_markdown": file_info(
            asset_requirements_markdown_path),
        "asset_requirements_icc_evidence": file_info(
            asset_requirements_icc_path),
        "registered_asset_intake": file_info(registered_asset_intake_path),
        "registered_asset_intake_markdown": file_info(
            registered_asset_intake_markdown_path),
        "registered_asset_intake_script": file_info(
            registered_asset_intake_script_path),
        "registered_asset_intake_icc_evidence": file_info(
            registered_asset_intake_icc_path),
        "native_backend_boundary": file_info(native_backend_boundary_path),
        "moonlab_job_specs": file_info(moonlab_job_specs_path),
        "moonlab_job_results": file_info(moonlab_job_results_path),
        "moonlab_replay_plan": file_info(moonlab_replay_plan_path),
        "moonlab_submission_packet": file_info(moonlab_submission_packet_path),
        "moonlab_submission_bundle": file_info(moonlab_submission_bundle_path),
        "moonlab_submission_bundle_markdown": file_info(
            moonlab_submission_bundle_markdown_path),
        "moonlab_submission_bundle_icc_evidence": file_info(
            moonlab_submission_bundle_icc_path),
        "moonlab_hardware_record_template": file_info(
            moonlab_hardware_record_template_path),
        "moonlab_hardware_submission_scope": file_info(
            moonlab_hardware_submission_scope_path),
        "moonlab_hardware_submission_scope_icc_evidence": file_info(
            moonlab_hardware_submission_scope_icc_path),
        "moonlab_full_game_plan": file_info(moonlab_full_game_plan_path),
        "moonlab_full_game_plan_markdown": file_info(
            moonlab_full_game_plan_markdown_path),
        "moonlab_full_game_plan_icc_evidence": file_info(
            moonlab_full_game_plan_icc_path),
        "moonlab_deployment_gate": file_info(moonlab_deployment_gate_path),
        "moonlab_deployment_gate_markdown": file_info(
            moonlab_deployment_gate_markdown_path),
        "moonlab_deployment_gate_icc_evidence": file_info(
            moonlab_deployment_gate_icc_path),
    }
    return {
        "schema": "qge.publication_pack.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "pack_dir": str(args.outdir),
        "source_inputs": {
            "capture_dir": str(capture_dir),
            "vanilla_matrix": str(vanilla_matrix),
            "vanilla_icc_evidence": (
                str(vanilla_icc_evidence) if vanilla_icc_evidence else None),
            "graphics_capture_dir": (
                str(graphics_capture_dir) if graphics_capture_dir else None),
            "publication_performance_source": perf_source,
            "publication_performance_summary": str(perf_summary_path),
            "agent_stream_dir": str(agent_stream_dir) if agent_stream_dir else None,
            "breadth_evidence": str(breadth_evidence)
            if breadth_evidence is not None else None,
            "claims_ledger": str(claims_path),
        },
        "artifacts": {
            "source_docs": source_docs,
            "capture": capture_artifacts,
            "vanilla": vanilla_artifacts,
            "agent_stream": agent_artifacts,
            "breadth": breadth_artifacts,
            "resource": resource_artifacts,
            "oracle": {
                "oracle_scene": oracle["oracle_scene"],
                "claims_evidence": oracle["claims_evidence"],
                "icc_evidence": oracle["icc_evidence"],
            },
            "advantage": {
                "metrics": advantage["metrics"],
                "qae_curve": advantage["qae_curve"],
                "qae_circuit": advantage["qae_circuit"],
                "qae_moonlab_payload": advantage["qae_moonlab_payload"],
                "qae_moonlab_payload_markdown": (
                    advantage["qae_moonlab_payload_markdown"]),
                "qae_moonlab_payload_icc_evidence": (
                    advantage["qae_moonlab_payload_icc_evidence"]),
                "qae_moonlab_circuits": advantage["qae_moonlab_circuits"],
                "qae_moonlab_oracle_kernel": (
                    advantage["qae_moonlab_oracle_kernel"]),
                "qae_moonlab_oracle_kernel_circuit": (
                    advantage["qae_moonlab_oracle_kernel_circuit"]),
                "qae_moonlab_oracle_kernel_markdown": (
                    advantage["qae_moonlab_oracle_kernel_markdown"]),
                "qae_moonlab_oracle_kernel_icc_evidence": (
                    advantage["qae_moonlab_oracle_kernel_icc_evidence"]),
                "qae_moonlab_observation_zero": (
                    advantage["qae_moonlab_observation_zero"]),
                "qae_moonlab_observation_zero_circuit": (
                    advantage["qae_moonlab_observation_zero_circuit"]),
                "qae_moonlab_observation_zero_markdown": (
                    advantage["qae_moonlab_observation_zero_markdown"]),
                "qae_moonlab_observation_zero_icc_evidence": (
                    advantage["qae_moonlab_observation_zero_icc_evidence"]),
                "qae_moonlab_grover_schedule_plan": (
                    advantage["qae_moonlab_grover_schedule_plan"]),
                "qae_moonlab_grover_schedule_plan_markdown": (
                    advantage[
                        "qae_moonlab_grover_schedule_plan_markdown"]),
                "qae_moonlab_grover_schedule_plan_icc_evidence": (
                    advantage[
                        "qae_moonlab_grover_schedule_plan_icc_evidence"]),
                "qae_moonlab_grover_circuits": (
                    advantage["qae_moonlab_grover_circuits"]),
                "scaling_summary": advantage["scaling_summary"],
                "scaling_summary_csv": advantage["scaling_summary_csv"],
                "icc_evidence": advantage["icc_evidence"],
            },
        },
        "runtime_summary": {
            "vanilla_ready_for_complete_claim": conformance.get(
                "ready_for_complete_claim"),
            "fallback_count": conformance.get("fallback_count"),
            "surrogate_count": conformance.get("qge_surface_surrogates"),
            "classic3d_count": conformance.get("classic3d_count"),
            "classic2d_count": conformance.get("classic2d_count"),
            "viewmodel_encoded": conformance.get("viewmodel_encoded"),
            "qge_classic_output_hidden": conformance.get(
                "qge_classic_output_hidden"),
            "qge_asset_ownership": conformance.get("qge_asset_ownership"),
            "qge_asset_ownership_fields_present": conformance.get(
                "qge_asset_ownership_fields_present"),
            "qge_asset_ownership_missing_fields": conformance.get(
                "qge_asset_ownership_missing_fields"),
            "qge_asset_ownership_incomplete_fields": conformance.get(
                "qge_asset_ownership_incomplete_fields"),
            "qge_asset_ownership_complete": conformance.get(
                "qge_asset_ownership_complete"),
            "agent_stream_runs_success": conformance.get(
                "agent_stream_runs_success"),
            "classic_agent_run_status": conformance.get(
                "classic_agent_run_status"),
            "qge_agent_run_status": conformance.get("qge_agent_run_status"),
            "classic_agent_startup_issue": conformance.get(
                "classic_agent_startup_issue"),
            "qge_agent_startup_issue": conformance.get(
                "qge_agent_startup_issue"),
            "vanilla_performance_sidecars_success": conformance.get(
                "performance_sidecars_success"),
            "classic_performance_status": conformance.get(
                "classic_performance_status"),
            "qge_performance_status": conformance.get(
                "qge_performance_status"),
            "classic_performance_engine_average_quantum_ms_max": (
                conformance.get(
                    "classic_performance_engine_average_quantum_ms_max")),
            "qge_performance_engine_average_quantum_ms_max": (
                conformance.get(
                    "qge_performance_engine_average_quantum_ms_max")),
            "classic_performance_render_time_ms_max": conformance.get(
                "classic_performance_render_time_ms_max"),
            "qge_performance_render_time_ms_max": conformance.get(
                "qge_performance_render_time_ms_max"),
            "classic_performance_threshold_failures": conformance.get(
                "classic_performance_threshold_failures"),
            "qge_performance_threshold_failures": conformance.get(
                "qge_performance_threshold_failures"),
            "vanilla_performance_ok": vanilla_performance_ok,
            "agent_stream_manifest_run": agent_stream_summary,
            "agent_stream_run_status": agent_stream_summary.get("run_status"),
            "agent_stream_run_success": agent_stream_summary.get("run_success"),
            "agent_stream_startup_issue": agent_stream_summary.get(
                "startup_issue"),
            "agent_stream_frames_captured": agent_stream_summary.get(
                "frames_captured"),
            "agent_stream_trace_status": agent_stream_summary.get(
                "trace_status"),
            "agent_stream_trace_bytes": agent_stream_summary.get("trace_bytes"),
            "agent_stream_performance_status": agent_stream_summary.get(
                "performance_status"),
            "performance_summary": capture_perf_summary,
            "performance_source": perf_source,
            "performance_status": capture_perf_summary.get("status"),
            "performance_engine_average_quantum_ms_max": (
                capture_perf_summary.get("engine_average_quantum_ms_max")),
            "performance_render_time_ms_max": capture_perf_summary.get(
                "render_time_ms_max"),
            "performance_threshold_failures": capture_perf_summary.get(
                "threshold_failures"),
            "performance_metric_evidence_present": capture_perf_summary.get(
                "metric_evidence_present"),
            "performance_required_runtime_backend_probe_targets": (
                capture_perf_summary.get(
                    "required_runtime_backend_probe_targets")),
            "performance_runtime_backend_probe_proofs": (
                capture_perf_summary.get("runtime_backend_probe_proofs")),
            "performance_runtime_backend_probe_missing_targets": (
                capture_perf_summary.get(
                    "runtime_backend_probe_missing_targets")),
            "performance_runtime_backend_probe_native_targets": (
                capture_perf_summary.get(
                    "runtime_backend_probe_native_targets")),
            "performance_runtime_backend_probe_resolved": (
                capture_perf_summary.get("runtime_backend_probe_resolved")),
            "performance_runtime_backend_boundary_status": (
                capture_perf_summary.get("runtime_backend_boundary_status")),
            "performance_ok": performance_ok,
            "breadth_evidence": breadth_summary,
            "breadth_ready_for_complete_claim": breadth_summary.get(
                "breadth_ready_for_complete_claim"),
            "breadth_matrix_run_count": breadth_summary.get(
                "matrix_run_count"),
            "breadth_ready_matrix_run_count": breadth_summary.get(
                "ready_matrix_run_count"),
            "breadth_map_count": breadth_summary.get("map_count"),
            "breadth_maps": breadth_summary.get("maps"),
            "full_game_map_coverage": full_game_map_coverage,
            "full_game_map_set": full_game_map_coverage.get("map_set"),
            "full_game_map_coverage_status": (
                full_game_map_coverage.get("status")),
            "full_game_map_target_count": (
                full_game_map_coverage.get("target_map_count")),
            "full_game_map_covered_count": (
                full_game_map_coverage.get("covered_map_count")),
            "full_game_map_missing_count": (
                full_game_map_coverage.get("missing_map_count")),
            "full_game_map_missing_maps": (
                full_game_map_coverage.get("missing_maps")),
            "asset_inventory": asset_inventory,
            "asset_inventory_status": asset_inventory.get("status"),
            "asset_inventory_available_map_count": (
                asset_inventory.get("available_map_count")),
            "asset_inventory_missing_map_count": (
                asset_inventory.get("missing_map_count")),
            "asset_inventory_invalid_bsp_count": (
                asset_inventory.get("invalid_bsp_count")),
            "full_game_asset_ready": (
                asset_inventory.get("full_game_asset_ready")),
            "registered_asset_intake": registered_asset_intake,
            "registered_asset_intake_status": (
                registered_asset_intake.get("status")),
            "registered_asset_intake_candidate_new_map_count": (
                registered_asset_intake.get("candidate_new_map_count")),
            "registered_asset_intake_missing_map_count_after_plan": (
                registered_asset_intake.get("missing_map_count_after_plan")),
            "registered_asset_intake_discovered_candidate_count": (
                registered_asset_intake.get("discovered_candidate_count", 0)),
            "breadth_total_fallback_count": breadth_summary.get(
                "total_fallback_count"),
            "breadth_total_surrogate_count": breadth_summary.get(
                "total_surrogate_count"),
            "breadth_total_cpu_idwt_count": breadth_summary.get(
                "total_cpu_idwt_count"),
            "breadth_total_native_bridge_count": breadth_summary.get(
                "total_native_bridge_count"),
            "breadth_total_backend_gate_event_count": breadth_summary.get(
                "total_backend_gate_event_count"),
            "breadth_total_runtime_backend_probe_event_count": (
                breadth_summary.get(
                    "total_runtime_backend_probe_event_count")),
            "breadth_runtime_backend_probe_targets": breadth_summary.get(
                "runtime_backend_probe_targets"),
            "breadth_runtime_backend_probe_paths": breadth_summary.get(
                "runtime_backend_probe_paths"),
            "breadth_required_runtime_backend_probe_targets": (
                breadth_summary.get("required_runtime_backend_probe_targets")),
            "breadth_runtime_backend_probe_proofs": breadth_summary.get(
                "runtime_backend_probe_proofs"),
            "breadth_runtime_backend_probe_missing_targets": (
                breadth_summary.get("runtime_backend_probe_missing_targets")),
            "breadth_runtime_backend_probe_native_targets": (
                breadth_summary.get("runtime_backend_probe_native_targets")),
            "breadth_runtime_backend_probe_resolved_run_count": (
                breadth_summary.get(
                    "runtime_backend_probe_resolved_run_count")),
            "breadth_evidence_ok": breadth_evidence_ok,
            "agent_stream_manifest_ok": agent_stream_manifest_ok,
            "publication_ready_for_complete_claim": publication_ready,
        },
        "advantage_summary": {
            "advantage_problem_id": metrics.get("advantage_problem_id"),
            "trial_count": metrics.get("scaling_summary", {}).get("trial_count"),
            "best_classical": metrics.get("comparison", {}).get("best_classical"),
            "best_qae": metrics.get("comparison", {}).get("best_qae"),
            "resource_estimate": metrics.get("resource_estimate"),
            "moonlab_qae_payload_summary": {
                "schema": advantage["qae_moonlab_payload_data"].get("schema"),
                "status": advantage["qae_moonlab_payload_data"].get("status"),
                "semantic_scope": (
                    advantage["qae_moonlab_payload_data"].get(
                        "semantic_scope")),
                "payload_resource_estimate": (
                    advantage["qae_moonlab_payload_data"].get(
                        "payload_resource_estimate")),
                "full_qae_oracle_transpiled": (
                    advantage["qae_moonlab_payload_data"].get(
                        "claim_posture", {}).get(
                            "full_qae_oracle_transpiled")),
            },
            "moonlab_qae_oracle_kernel_summary": {
                "schema": (
                    advantage["qae_moonlab_oracle_kernel_data"].get(
                        "schema")),
                "status": (
                    advantage["qae_moonlab_oracle_kernel_data"].get(
                        "status")),
                "semantic_scope": (
                    advantage["qae_moonlab_oracle_kernel_data"].get(
                        "semantic_scope")),
                "resource_estimate": (
                    advantage["qae_moonlab_oracle_kernel_data"].get(
                        "resource_estimate")),
                "control_plane_executable": (
                    advantage["qae_moonlab_oracle_kernel_data"].get(
                        "moonlab_control_plane", {}).get(
                            "control_plane_executable")),
                "qf_oracle_kernel_transpiled": (
                    advantage["qae_moonlab_oracle_kernel_data"].get(
                        "claim_posture", {}).get(
                            "qf_oracle_kernel_transpiled")),
                "full_qae_oracle_transpiled": (
                    advantage["qae_moonlab_oracle_kernel_data"].get(
                        "claim_posture", {}).get(
                            "full_qae_oracle_transpiled")),
            },
            "moonlab_qae_observation_zero_summary": {
                "schema": (
                    advantage["qae_moonlab_observation_zero_data"].get(
                        "schema")),
                "status": (
                    advantage["qae_moonlab_observation_zero_data"].get(
                        "status")),
                "semantic_scope": (
                    advantage["qae_moonlab_observation_zero_data"].get(
                        "semantic_scope")),
                "resource_estimate": (
                    advantage["qae_moonlab_observation_zero_data"].get(
                        "resource_estimate")),
                "state_preparation": (
                    advantage["qae_moonlab_observation_zero_data"].get(
                        "state_preparation")),
                "control_plane_executable": (
                    advantage["qae_moonlab_observation_zero_data"].get(
                        "moonlab_control_plane", {}).get(
                            "control_plane_executable")),
                "candidate_state_preparation_transpiled": (
                    advantage["qae_moonlab_observation_zero_data"].get(
                        "claim_posture", {}).get(
                            "candidate_state_preparation_transpiled")),
                "power_zero_observation_transpiled": (
                    advantage["qae_moonlab_observation_zero_data"].get(
                        "claim_posture", {}).get(
                            "power_zero_observation_transpiled")),
                "full_qae_oracle_transpiled": (
                    advantage["qae_moonlab_observation_zero_data"].get(
                        "claim_posture", {}).get(
                            "full_qae_oracle_transpiled")),
            },
            "moonlab_qae_grover_schedule_plan_summary": {
                "schema": (
                    advantage["qae_moonlab_grover_schedule_plan_data"].get(
                        "schema")),
                "status": (
                    advantage["qae_moonlab_grover_schedule_plan_data"].get(
                        "status")),
                "semantic_scope": (
                    advantage["qae_moonlab_grover_schedule_plan_data"].get(
                        "semantic_scope")),
                "resource_estimate": (
                    advantage["qae_moonlab_grover_schedule_plan_data"].get(
                        "resource_estimate")),
                "ready_observation_count": (
                    advantage["qae_moonlab_grover_schedule_plan_data"].get(
                        "moonlab_control_plane", {}).get(
                            "ready_observation_count")),
                "blocked_observation_count": (
                    advantage["qae_moonlab_grover_schedule_plan_data"].get(
                        "moonlab_control_plane", {}).get(
                            "blocked_observation_count")),
                "first_blocked_power": (
                    advantage["qae_moonlab_grover_schedule_plan_data"].get(
                        "moonlab_control_plane", {}).get(
                            "first_blocked_power")),
                "grover_schedule_transpiled": (
                    advantage["qae_moonlab_grover_schedule_plan_data"].get(
                        "claim_posture", {}).get(
                            "full_mlae_schedule_transpiled")),
                "full_qae_oracle_transpiled": (
                    advantage["qae_moonlab_grover_schedule_plan_data"].get(
                        "claim_posture", {}).get(
                            "full_qae_oracle_transpiled")),
            },
            "resource_envelope_summary": resource_envelope.get("posture"),
            "full_game_map_coverage_summary": {
                "status": full_game_map_coverage.get("status"),
                "map_set": full_game_map_coverage.get("map_set"),
                "target_map_count": full_game_map_coverage.get(
                    "target_map_count"),
                "covered_map_count": full_game_map_coverage.get(
                    "covered_map_count"),
                "missing_map_count": full_game_map_coverage.get(
                    "missing_map_count"),
            },
            "asset_inventory_summary": {
                "status": asset_inventory.get("status"),
                "asset_root_status": asset_inventory.get("asset_root_status"),
                "available_map_count": asset_inventory.get(
                    "available_map_count"),
                "missing_map_count": asset_inventory.get("missing_map_count"),
                "pak_count": asset_inventory.get("pak_count"),
                "invalid_pak_count": asset_inventory.get("invalid_pak_count"),
                "invalid_bsp_count": asset_inventory.get("invalid_bsp_count"),
                "full_game_asset_ready": asset_inventory.get(
                    "full_game_asset_ready"),
            },
            "asset_requirements_summary": {
                "schema": asset_requirements.get("schema"),
                "status": asset_requirements.get("status"),
                "target_map_count": asset_requirements.get(
                    "target_map_count"),
                "present_map_count": asset_requirements.get(
                    "present_map_count"),
                "missing_map_count": asset_requirements.get(
                    "missing_map_count"),
                "asset_requirements_satisfied": (
                    asset_requirements.get("claim_posture", {}).get(
                        "asset_requirements_satisfied")),
            },
            "registered_asset_intake_summary": {
                "schema": registered_asset_intake.get("schema"),
                "status": registered_asset_intake.get("status"),
                "candidate_new_map_count": registered_asset_intake.get(
                    "candidate_new_map_count"),
                "missing_map_count_after_plan": registered_asset_intake.get(
                    "missing_map_count_after_plan"),
                "copy_plan_count": registered_asset_intake.get(
                    "copy_plan_count"),
                "post_install_verification_command_count": (
                    registered_asset_intake.get(
                        "post_install_verification_command_count")),
                "post_install_capture_queue_command_present": any(
                    isinstance(command, dict) and
                    command.get("kind") == "capture_queue"
                    for command in list_or_empty(dict_or_empty(
                        registered_asset_intake.get(
                            "post_install_verification")).get("commands"))
                ),
                "discovered_candidate_count": registered_asset_intake.get(
                    "discovered_candidate_count", 0),
                "asset_intake_copies_game_data": (
                    registered_asset_intake.get("claim_posture", {}).get(
                        "asset_intake_copies_game_data")),
            },
            "native_backend_boundary_summary": {
                "status": native_backend_boundary.get("status"),
                "required_target_count": native_backend_boundary.get(
                    "required_target_count"),
                "passed_target_count": native_backend_boundary.get(
                    "passed_target_count"),
                "blocked_target_count": native_backend_boundary.get(
                    "blocked_target_count"),
            },
            "moonlab_job_specs_summary": {
                "selected_job_count": moonlab_job_specs.get(
                    "selected_job_count"),
                "hardware_candidate_job_count": moonlab_job_specs.get(
                    "hardware_candidate_job_count"),
                "submission_scope": moonlab_job_specs.get("submission_scope"),
            },
            "moonlab_job_results_summary": {
                "overall_status": moonlab_job_results.get("overall_status"),
                "completed_simulator_job_count": moonlab_job_results.get(
                    "completed_simulator_job_count"),
                "completed_native_replay_job_count": moonlab_job_results.get(
                    "completed_native_replay_job_count"),
                "hardware_submitted_job_count": moonlab_job_results.get(
                    "hardware_submitted_job_count"),
                "blocked_job_count": moonlab_job_results.get(
                    "blocked_job_count"),
            },
            "moonlab_replay_plan_summary": {
                "schema": moonlab_replay_plan.get("schema"),
                "selected_job_count": moonlab_replay_plan.get(
                    "selected_job_count"),
                "hardware_candidate_job_count": moonlab_replay_plan.get(
                    "hardware_candidate_job_count"),
                "hardware_submitted_job_count": moonlab_replay_plan.get(
                    "hardware_submitted_job_count"),
                "blocked_job_count": moonlab_replay_plan.get(
                    "blocked_job_count"),
            },
            "moonlab_submission_packet_summary": {
                "schema": moonlab_submission_packet.get("schema"),
                "hardware_candidate_job_count": (
                    moonlab_submission_packet.get(
                        "hardware_candidate_job_count")),
                "ready_candidate_count": moonlab_submission_packet.get(
                    "ready_candidate_count"),
                "blocked_candidate_count": moonlab_submission_packet.get(
                    "blocked_candidate_count"),
                "submitted_candidate_count": moonlab_submission_packet.get(
                    "submitted_candidate_count"),
            },
            "moonlab_submission_bundle_summary": {
                "schema": moonlab_submission_bundle.get("schema"),
                "status": moonlab_submission_bundle.get("status"),
                "hardware_candidate_job_count": (
                    moonlab_submission_bundle.get(
                        "hardware_candidate_job_count")),
                "ready_for_control_plane_submission_count": (
                    moonlab_submission_bundle.get(
                        "ready_for_control_plane_submission_count")),
                "calibration_payload_ready_count": (
                    moonlab_submission_bundle.get(
                        "calibration_payload_ready_count")),
                "oracle_kernel_ready_count": (
                    moonlab_submission_bundle.get(
                        "oracle_kernel_ready_count")),
                "qae_observation_ready_count": (
                    moonlab_submission_bundle.get(
                        "qae_observation_ready_count")),
                "grover_schedule_ready_count": (
                    moonlab_submission_bundle.get(
                        "grover_schedule_ready_count")),
                "transpilation_required_count": (
                    moonlab_submission_bundle.get(
                        "transpilation_required_count")),
                "missing_artifact_candidate_count": (
                    moonlab_submission_bundle.get(
                        "missing_artifact_candidate_count")),
                "hardware_submission_directly_executable": (
                    moonlab_submission_bundle.get(
                        "hardware_submission_directly_executable")),
                "control_plane_payload_directly_executable": (
                    moonlab_submission_bundle.get(
                        "control_plane_payload_directly_executable")),
                "oracle_kernel_directly_executable": (
                    moonlab_submission_bundle.get(
                        "oracle_kernel_directly_executable")),
                "qae_observation_directly_executable": (
                    moonlab_submission_bundle.get(
                        "qae_observation_directly_executable")),
                "grover_schedule_directly_executable": (
                    moonlab_submission_bundle.get(
                        "grover_schedule_directly_executable")),
            },
            "moonlab_hardware_record_template_summary": {
                "schema": moonlab_hardware_record_template.get("schema"),
                "record_schema": moonlab_hardware_record_template.get(
                    "record_schema"),
                "job_id": moonlab_hardware_record_template.get("job_id"),
                "candidate_digest": moonlab_hardware_record_template.get(
                    "candidate_digest"),
            },
            "moonlab_hardware_submission_scope_summary": {
                "schema": moonlab_hardware_submission_scope.get("schema"),
                "status": moonlab_hardware_submission_scope.get("status"),
                "hardware_submission_scope_ready": (
                    moonlab_hardware_submission_scope.get(
                        "hardware_submission_scope_ready")),
                "hardware_candidate_job_count": (
                    moonlab_hardware_submission_scope.get(
                        "hardware_candidate_job_count")),
                "ready_for_control_plane_submission_count": (
                    moonlab_hardware_submission_scope.get(
                        "ready_for_control_plane_submission_count")),
                "passing_check_count": (
                    moonlab_hardware_submission_scope.get(
                        "passing_check_count")),
                "attention_check_count": (
                    moonlab_hardware_submission_scope.get(
                        "attention_check_count")),
                "out_of_scope": moonlab_hardware_submission_scope.get(
                    "out_of_scope"),
            },
            "moonlab_full_game_plan_summary": {
                "schema": moonlab_full_game_plan.get("schema"),
                "status": moonlab_full_game_plan.get("status"),
                "target_map_count": moonlab_full_game_plan.get(
                    "target_map_count"),
                "covered_map_count": moonlab_full_game_plan.get(
                    "covered_map_count"),
                "missing_map_count": moonlab_full_game_plan.get(
                    "missing_map_count"),
                "asset_unavailable_map_count": (
                    moonlab_full_game_plan.get(
                        "asset_unavailable_map_count")),
                "whole_game_moonlab_deployment_claimed": (
                    moonlab_full_game_plan.get("claim_posture", {}).get(
                        "whole_game_moonlab_deployment_claimed")),
            },
            "moonlab_deployment_gate_summary": {
                "schema": moonlab_deployment_gate.get("schema"),
                "status": moonlab_deployment_gate.get("status"),
                "failed_criterion_count": moonlab_deployment_gate.get(
                    "failed_criterion_count"),
                "blocker_count": moonlab_deployment_gate.get("blocker_count"),
                "whole_game_moonlab_deployment_claim_allowed": (
                    moonlab_deployment_gate.get(
                        "whole_game_moonlab_deployment_claim_allowed")),
                "whole_game_hardware_execution_claim_allowed": (
                    moonlab_deployment_gate.get(
                        "whole_game_hardware_execution_claim_allowed")),
                "hardware_quantum_advantage_claim_allowed": (
                    moonlab_deployment_gate.get(
                        "hardware_quantum_advantage_claim_allowed")),
                "dense_70000_qubit_state_claim_allowed": (
                    moonlab_deployment_gate.get(
                        "dense_70000_qubit_state_claim_allowed")),
                "target_map_count": (
                    moonlab_deployment_gate.get("summary", {}).get(
                        "target_map_count")),
                "covered_map_count": (
                    moonlab_deployment_gate.get("summary", {}).get(
                        "covered_map_count")),
                "coverage_missing_map_count": (
                    moonlab_deployment_gate.get("summary", {}).get(
                        "coverage_missing_map_count")),
                "asset_missing_map_count": (
                    moonlab_deployment_gate.get("summary", {}).get(
                        "asset_missing_map_count")),
                "invalid_bsp_count": (
                    moonlab_deployment_gate.get("summary", {}).get(
                        "invalid_bsp_count")),
                "registered_asset_install_script": (
                    moonlab_deployment_gate.get("summary", {}).get(
                        "registered_asset_install_script")),
                "registered_asset_intake_file": (
                    moonlab_deployment_gate.get("summary", {}).get(
                        "registered_asset_intake_file")),
                "post_install_verification_command_count": (
                    moonlab_deployment_gate.get("summary", {}).get(
                        "post_install_verification_command_count")),
                "post_install_capture_queue_command_present": (
                    moonlab_deployment_gate.get("summary", {}).get(
                        "post_install_capture_queue_command_present")),
                "post_install_capture_queue_command": (
                    moonlab_deployment_gate.get("summary", {}).get(
                        "post_install_capture_queue_command")),
                "post_install_capture_queue_script": (
                    moonlab_deployment_gate.get("summary", {}).get(
                        "post_install_capture_queue_script")),
            },
        },
        "claim_posture": {
            "allowed_wording": (
                "This pack contains reproducible Quantum Quake artifact "
                "evidence for a QGE-owned vanilla capture, scene-oracle IR, "
                "and a finite-shot amplitude-estimation benchmark under an "
                "explicit oracle model."
            ),
            "disallowed_wording": (
                "This pack proves practical hardware speedup, full-frame "
                "quantum rendering, or unrestricted quantum advantage."
            ),
        },
        "reproduce_commands": [
            "tools/qge_oracle_export.py <capture_dir>",
            "tools/qge_advantage_benchmark.py <oracle_scene.json> --outdir <outdir>",
            "tools/qge_moonlab_qae_transpile.py --metrics <pack_dir>/advantage/advantage_metrics.json --abstract-circuit <pack_dir>/advantage/qae_circuit.txt --out /tmp/qae_moonlab_payload.json --circuit-dir /tmp/moonlab_qae_circuits --markdown /tmp/qae_moonlab_payload.md --icc-json /tmp/qae_moonlab_payload_icc_evidence.json",
            "tools/qge_moonlab_oracle_transpile.py --metrics <pack_dir>/advantage/advantage_metrics.json --oracle-scene <pack_dir>/oracle/oracle_scene.json --out /tmp/qae_moonlab_oracle_kernel.json --circuit /tmp/qae_moonlab_oracle_kernel.moonlab --markdown /tmp/qae_moonlab_oracle_kernel.md --icc-json /tmp/qae_moonlab_oracle_kernel_icc_evidence.json",
            "tools/qge_moonlab_qae_observation_transpile.py --metrics <pack_dir>/advantage/advantage_metrics.json --oracle-scene <pack_dir>/oracle/oracle_scene.json --out /tmp/qae_moonlab_observation_zero.json --circuit /tmp/qae_moonlab_observation_zero.moonlab --markdown /tmp/qae_moonlab_observation_zero.md --icc-json /tmp/qae_moonlab_observation_zero_icc_evidence.json",
            "tools/qge_moonlab_qae_grover_plan.py --metrics <pack_dir>/advantage/advantage_metrics.json --oracle-scene <pack_dir>/oracle/oracle_scene.json --out /tmp/qae_moonlab_grover_schedule_plan.json --markdown /tmp/qae_moonlab_grover_schedule_plan.md --icc-json /tmp/qae_moonlab_grover_schedule_plan_icc_evidence.json",
            "tools/qge_vanilla_capture_matrix.py <graphics_capture_dir>",
            "tools/qge_breadth_evidence.py --matrix <graphics_capture_dir> --min-maps N",
            "tools/qge_publication_pack.py --capture-dir <trace_capture_dir> --vanilla-matrix <graphics_capture_dir>/vanilla_capture_matrix.json --graphics-capture-dir <graphics_capture_dir> --breadth-evidence <breadth_dir>",
            "tools/qge_registered_asset_intake.py --current-root <asset_root> --candidate <quake_install_or_pak> --discover-common --json /tmp/qge_registered_asset_intake.json --markdown /tmp/qge_registered_asset_intake.md --script-out /tmp/install_registered_assets.sh --icc-json /tmp/qge_registered_asset_intake_icc_evidence.json",
            "tools/qge_asset_requirements.py --asset-root <asset_root> --json /tmp/qge_asset_requirements.json --markdown /tmp/qge_asset_requirements.md --icc-json /tmp/qge_asset_requirements_icc_evidence.json",
            "tools/qge_moonlab_job_runner.py <pack_dir>/resource/qge_moonlab_job_specs.json --out /tmp/qge_moonlab_job_results.verify.json --expect <pack_dir>/resource/qge_moonlab_job_results.json --plan-out /tmp/qge_moonlab_replay_plan.verify.json --submission-out /tmp/qge_moonlab_submission_packet.verify.json",
            "tools/qge_moonlab_submission_bundle.py <pack_dir>/resource/qge_moonlab_submission_packet.json --out /tmp/qge_moonlab_submission_bundle.json --markdown /tmp/qge_moonlab_submission_bundle.md --icc-json /tmp/qge_moonlab_submission_bundle_icc_evidence.json",
            "tools/qge_moonlab_hardware_ingest.py <pack_dir>/resource/qge_moonlab_submission_packet.json --template-out /tmp/qge_moonlab_hardware_record.template.json",
            "tools/qge_moonlab_full_game_plan.py <pack_dir> --out /tmp/qge_moonlab_full_game_plan.json --markdown /tmp/qge_moonlab_full_game_plan.md --icc-json /tmp/qge_moonlab_full_game_plan_icc_evidence.json",
            "tools/qge_moonlab_deployment_gate.py <pack_dir> --out /tmp/qge_moonlab_deployment_gate.json --markdown /tmp/qge_moonlab_deployment_gate.md --icc-json /tmp/qge_moonlab_deployment_gate_icc_evidence.json",
            "tools/qge_publication_icc_audit.py <pack_dir> --out /tmp/qge_publication_icc_audit.json --fail-on-mismatch",
        ],
    }


def build_icc_evidence(manifest: dict[str, Any],
                       manifest_path: Path,
                       icc_path: Path) -> dict[str, Any]:
    artifacts = manifest["artifacts"]
    runtime = manifest["runtime_summary"]
    advantage_summary = manifest.get("advantage_summary", {})
    if not isinstance(advantage_summary, dict):
        advantage_summary = {}
    qae_payload_summary = dict_or_empty(
        advantage_summary.get("moonlab_qae_payload_summary"))
    qae_oracle_kernel_summary = dict_or_empty(
        advantage_summary.get("moonlab_qae_oracle_kernel_summary"))
    qae_observation_summary = dict_or_empty(
        advantage_summary.get("moonlab_qae_observation_zero_summary"))
    qae_grover_plan_summary = dict_or_empty(
        advantage_summary.get("moonlab_qae_grover_schedule_plan_summary"))
    job_specs_summary = dict_or_empty(
        advantage_summary.get("moonlab_job_specs_summary"))
    job_results_summary = dict_or_empty(
        advantage_summary.get("moonlab_job_results_summary"))
    replay_plan_summary = dict_or_empty(
        advantage_summary.get("moonlab_replay_plan_summary"))
    submission_packet_summary = dict_or_empty(
        advantage_summary.get("moonlab_submission_packet_summary"))
    submission_bundle_summary = dict_or_empty(
        advantage_summary.get("moonlab_submission_bundle_summary"))
    hardware_record_template_summary = dict_or_empty(
        advantage_summary.get("moonlab_hardware_record_template_summary"))
    hardware_submission_scope_summary = dict_or_empty(
        advantage_summary.get("moonlab_hardware_submission_scope_summary"))
    full_game_plan_summary = dict_or_empty(
        advantage_summary.get("moonlab_full_game_plan_summary"))
    deployment_gate_summary = dict_or_empty(
        advantage_summary.get("moonlab_deployment_gate_summary"))
    native_boundary_summary = dict_or_empty(
        advantage_summary.get("native_backend_boundary_summary"))
    full_game_summary = dict_or_empty(
        advantage_summary.get("full_game_map_coverage_summary"))
    asset_inventory_summary = dict_or_empty(
        advantage_summary.get("asset_inventory_summary"))
    asset_requirements_summary = dict_or_empty(
        advantage_summary.get("asset_requirements_summary"))
    registered_asset_intake_summary = dict_or_empty(
        advantage_summary.get("registered_asset_intake_summary"))
    ready = bool(runtime.get("publication_ready_for_complete_claim"))
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_publication_pack",
        "completion_reason": (
            "qge_publication_artifact_pack_complete"
            if ready else "qge_publication_artifact_pack_evidence_only"
        ),
        "publication_manifest_file": str(manifest_path),
        "publication_icc_evidence_file": str(icc_path),
        "publication_pack_dir": manifest["pack_dir"],
        "oracle_scene_file": artifacts["oracle"]["oracle_scene"]["path"],
        "claims_evidence_file": artifacts["oracle"]["claims_evidence"]["path"],
        "advantage_metrics_file": artifacts["advantage"]["metrics"]["path"],
        "moonlab_qae_payload_file": (
            artifacts["advantage"].get("qae_moonlab_payload", {}).get(
                "path")),
        "moonlab_qae_payload_markdown_file": (
            artifacts["advantage"].get(
                "qae_moonlab_payload_markdown", {}).get("path")),
        "moonlab_qae_payload_icc_evidence_file": (
            artifacts["advantage"].get(
                "qae_moonlab_payload_icc_evidence", {}).get("path")),
        "moonlab_qae_payload_circuit_file_count": (
            artifacts["advantage"].get("qae_moonlab_circuits", {}).get(
                "file_count")),
        "moonlab_qae_payload_schema": qae_payload_summary.get("schema"),
        "moonlab_qae_payload_status": qae_payload_summary.get("status"),
        "moonlab_qae_payload_semantic_scope": (
            qae_payload_summary.get("semantic_scope")),
        "moonlab_qae_payload_full_qae_oracle_transpiled": (
            qae_payload_summary.get("full_qae_oracle_transpiled")),
        "moonlab_qae_oracle_kernel_file": (
            artifacts["advantage"].get(
                "qae_moonlab_oracle_kernel", {}).get("path")),
        "moonlab_qae_oracle_kernel_circuit_file": (
            artifacts["advantage"].get(
                "qae_moonlab_oracle_kernel_circuit", {}).get("path")),
        "moonlab_qae_oracle_kernel_markdown_file": (
            artifacts["advantage"].get(
                "qae_moonlab_oracle_kernel_markdown", {}).get("path")),
        "moonlab_qae_oracle_kernel_icc_evidence_file": (
            artifacts["advantage"].get(
                "qae_moonlab_oracle_kernel_icc_evidence", {}).get("path")),
        "moonlab_qae_oracle_kernel_schema": (
            qae_oracle_kernel_summary.get("schema")),
        "moonlab_qae_oracle_kernel_status": (
            qae_oracle_kernel_summary.get("status")),
        "moonlab_qae_oracle_kernel_semantic_scope": (
            qae_oracle_kernel_summary.get("semantic_scope")),
        "moonlab_qae_oracle_kernel_control_plane_executable": (
            qae_oracle_kernel_summary.get("control_plane_executable")),
        "moonlab_qae_qf_oracle_kernel_transpiled": (
            qae_oracle_kernel_summary.get("qf_oracle_kernel_transpiled")),
        "moonlab_qae_oracle_kernel_full_qae_oracle_transpiled": (
            qae_oracle_kernel_summary.get("full_qae_oracle_transpiled")),
        "moonlab_qae_observation_zero_file": (
            artifacts["advantage"].get(
                "qae_moonlab_observation_zero", {}).get("path")),
        "moonlab_qae_observation_zero_circuit_file": (
            artifacts["advantage"].get(
                "qae_moonlab_observation_zero_circuit", {}).get("path")),
        "moonlab_qae_observation_zero_markdown_file": (
            artifacts["advantage"].get(
                "qae_moonlab_observation_zero_markdown", {}).get("path")),
        "moonlab_qae_observation_zero_icc_evidence_file": (
            artifacts["advantage"].get(
                "qae_moonlab_observation_zero_icc_evidence", {}).get("path")),
        "moonlab_qae_observation_zero_schema": (
            qae_observation_summary.get("schema")),
        "moonlab_qae_observation_zero_status": (
            qae_observation_summary.get("status")),
        "moonlab_qae_observation_zero_semantic_scope": (
            qae_observation_summary.get("semantic_scope")),
        "moonlab_qae_observation_zero_control_plane_executable": (
            qae_observation_summary.get("control_plane_executable")),
        "moonlab_qae_candidate_state_preparation_transpiled": (
            qae_observation_summary.get(
                "candidate_state_preparation_transpiled")),
        "moonlab_qae_power_zero_observation_transpiled": (
            qae_observation_summary.get(
                "power_zero_observation_transpiled")),
        "moonlab_qae_observation_zero_full_qae_oracle_transpiled": (
            qae_observation_summary.get("full_qae_oracle_transpiled")),
        "moonlab_qae_grover_schedule_plan_file": (
            artifacts["advantage"].get(
                "qae_moonlab_grover_schedule_plan", {}).get("path")),
        "moonlab_qae_grover_schedule_plan_markdown_file": (
            artifacts["advantage"].get(
                "qae_moonlab_grover_schedule_plan_markdown", {}).get("path")),
        "moonlab_qae_grover_schedule_plan_icc_evidence_file": (
            artifacts["advantage"].get(
                "qae_moonlab_grover_schedule_plan_icc_evidence", {}).get(
                    "path")),
        "moonlab_qae_grover_schedule_plan_schema": (
            qae_grover_plan_summary.get("schema")),
        "moonlab_qae_grover_schedule_plan_status": (
            qae_grover_plan_summary.get("status")),
        "moonlab_qae_grover_schedule_plan_semantic_scope": (
            qae_grover_plan_summary.get("semantic_scope")),
        "moonlab_qae_grover_schedule_ready_observation_count": (
            qae_grover_plan_summary.get("ready_observation_count")),
        "moonlab_qae_grover_schedule_blocked_observation_count": (
            qae_grover_plan_summary.get("blocked_observation_count")),
        "moonlab_qae_grover_schedule_first_blocked_power": (
            qae_grover_plan_summary.get("first_blocked_power")),
        "moonlab_qae_grover_schedule_transpiled": (
            qae_grover_plan_summary.get("grover_schedule_transpiled")),
        "moonlab_qae_grover_schedule_full_qae_oracle_transpiled": (
            qae_grover_plan_summary.get("full_qae_oracle_transpiled")),
        "scaling_summary_file": artifacts["advantage"]["scaling_summary"]["path"],
        "resource_envelope_file": artifacts.get("resource", {}).get(
            "envelope", {}).get("path"),
        "full_game_map_coverage_file": artifacts.get("resource", {}).get(
            "full_game_map_coverage", {}).get("path"),
        "full_game_map_coverage_status": full_game_summary.get("status"),
        "full_game_map_target_count": full_game_summary.get(
            "target_map_count"),
        "full_game_map_covered_count": full_game_summary.get(
            "covered_map_count"),
        "full_game_map_missing_count": full_game_summary.get(
            "missing_map_count"),
        "asset_inventory_file": artifacts.get("resource", {}).get(
            "asset_inventory", {}).get("path"),
        "asset_requirements_file": artifacts.get("resource", {}).get(
            "asset_requirements", {}).get("path"),
        "asset_requirements_markdown_file": artifacts.get("resource", {}).get(
            "asset_requirements_markdown", {}).get("path"),
        "asset_requirements_icc_evidence_file": (
            artifacts.get("resource", {}).get(
                "asset_requirements_icc_evidence", {}).get("path")),
        "asset_inventory_status": asset_inventory_summary.get("status"),
        "asset_inventory_available_map_count": (
            asset_inventory_summary.get("available_map_count")),
        "asset_inventory_missing_map_count": (
            asset_inventory_summary.get("missing_map_count")),
        "asset_inventory_invalid_bsp_count": (
            asset_inventory_summary.get("invalid_bsp_count")),
        "full_game_asset_ready": asset_inventory_summary.get(
            "full_game_asset_ready"),
        "asset_requirements_schema": asset_requirements_summary.get("schema"),
        "asset_requirement_status": asset_requirements_summary.get("status"),
        "asset_requirements_present_map_count": (
            asset_requirements_summary.get("present_map_count")),
        "asset_requirements_missing_map_count": (
            asset_requirements_summary.get("missing_map_count")),
        "asset_requirements_satisfied": (
            asset_requirements_summary.get("asset_requirements_satisfied")),
        "registered_asset_intake_file": (
            artifacts.get("resource", {}).get(
                "registered_asset_intake", {}).get("path")),
        "registered_asset_intake_markdown_file": (
            artifacts.get("resource", {}).get(
                "registered_asset_intake_markdown", {}).get("path")),
        "registered_asset_intake_script_file": (
            artifacts.get("resource", {}).get(
                "registered_asset_intake_script", {}).get("path")),
        "registered_asset_intake_icc_evidence_file": (
            artifacts.get("resource", {}).get(
                "registered_asset_intake_icc_evidence", {}).get("path")),
        "registered_asset_intake_schema": (
            registered_asset_intake_summary.get("schema")),
        "registered_asset_intake_status": (
            registered_asset_intake_summary.get("status")),
        "registered_asset_intake_candidate_new_map_count": (
            registered_asset_intake_summary.get("candidate_new_map_count")),
        "registered_asset_intake_missing_map_count_after_plan": (
            registered_asset_intake_summary.get(
                "missing_map_count_after_plan")),
        "registered_asset_intake_copy_plan_count": (
            registered_asset_intake_summary.get("copy_plan_count")),
        "registered_asset_intake_post_install_verification_command_count": (
            registered_asset_intake_summary.get(
                "post_install_verification_command_count")),
        "registered_asset_intake_post_install_capture_queue_command_present": (
            registered_asset_intake_summary.get(
                "post_install_capture_queue_command_present")),
        "registered_asset_intake_discovered_candidate_count": (
            registered_asset_intake_summary.get("discovered_candidate_count")),
        "asset_intake_copies_game_data": (
            registered_asset_intake_summary.get(
                "asset_intake_copies_game_data")),
        "native_backend_boundary_file": artifacts.get("resource", {}).get(
            "native_backend_boundary", {}).get("path"),
        "native_backend_boundary_status": native_boundary_summary.get(
            "status"),
        "native_backend_boundary_passed_target_count": (
            native_boundary_summary.get("passed_target_count")),
        "native_backend_boundary_required_target_count": (
            native_boundary_summary.get("required_target_count")),
        "moonlab_job_specs_file": artifacts.get("resource", {}).get(
            "moonlab_job_specs", {}).get("path"),
        "moonlab_job_results_file": artifacts.get("resource", {}).get(
            "moonlab_job_results", {}).get("path"),
        "moonlab_replay_plan_file": artifacts.get("resource", {}).get(
            "moonlab_replay_plan", {}).get("path"),
        "moonlab_submission_packet_file": artifacts.get("resource", {}).get(
            "moonlab_submission_packet", {}).get("path"),
        "moonlab_submission_bundle_file": artifacts.get("resource", {}).get(
            "moonlab_submission_bundle", {}).get("path"),
        "moonlab_submission_bundle_markdown_file": (
            artifacts.get("resource", {}).get(
                "moonlab_submission_bundle_markdown", {}).get("path")),
        "moonlab_submission_bundle_icc_evidence_file": (
            artifacts.get("resource", {}).get(
                "moonlab_submission_bundle_icc_evidence", {}).get("path")),
        "moonlab_hardware_record_template_file": (
            artifacts.get("resource", {}).get(
                "moonlab_hardware_record_template", {}).get("path")),
        "moonlab_hardware_submission_scope_file": (
            artifacts.get("resource", {}).get(
                "moonlab_hardware_submission_scope", {}).get("path")),
        "moonlab_hardware_submission_scope_icc_evidence_file": (
            artifacts.get("resource", {}).get(
                "moonlab_hardware_submission_scope_icc_evidence", {}).get(
                    "path")),
        "moonlab_full_game_plan_file": artifacts.get("resource", {}).get(
            "moonlab_full_game_plan", {}).get("path"),
        "moonlab_full_game_plan_markdown_file": (
            artifacts.get("resource", {}).get(
                "moonlab_full_game_plan_markdown", {}).get("path")),
        "moonlab_full_game_plan_icc_evidence_file": (
            artifacts.get("resource", {}).get(
                "moonlab_full_game_plan_icc_evidence", {}).get("path")),
        "moonlab_deployment_gate_file": artifacts.get("resource", {}).get(
            "moonlab_deployment_gate", {}).get("path"),
        "moonlab_deployment_gate_markdown_file": (
            artifacts.get("resource", {}).get(
                "moonlab_deployment_gate_markdown", {}).get("path")),
        "moonlab_deployment_gate_icc_evidence_file": (
            artifacts.get("resource", {}).get(
                "moonlab_deployment_gate_icc_evidence", {}).get("path")),
        "moonlab_selected_job_count": job_specs_summary.get(
            "selected_job_count"),
        "moonlab_hardware_candidate_job_count": job_specs_summary.get(
            "hardware_candidate_job_count"),
        "moonlab_completed_simulator_job_count": job_results_summary.get(
            "completed_simulator_job_count"),
        "moonlab_completed_native_replay_job_count": job_results_summary.get(
            "completed_native_replay_job_count"),
        "moonlab_hardware_submitted_job_count": job_results_summary.get(
            "hardware_submitted_job_count"),
        "moonlab_job_results_status": job_results_summary.get(
            "overall_status"),
        "moonlab_replay_plan_schema": replay_plan_summary.get("schema"),
        "moonlab_submission_packet_schema": (
            submission_packet_summary.get("schema")),
        "moonlab_submission_ready_candidate_count": (
            submission_packet_summary.get("ready_candidate_count")),
        "moonlab_submission_blocked_candidate_count": (
            submission_packet_summary.get("blocked_candidate_count")),
        "moonlab_submission_submitted_candidate_count": (
            submission_packet_summary.get("submitted_candidate_count")),
        "moonlab_submission_bundle_schema": (
            submission_bundle_summary.get("schema")),
        "moonlab_submission_bundle_status": (
            submission_bundle_summary.get("status")),
        "moonlab_submission_ready_for_control_plane_submission_count": (
            submission_bundle_summary.get(
                "ready_for_control_plane_submission_count")),
        "moonlab_submission_calibration_payload_ready_count": (
            submission_bundle_summary.get(
                "calibration_payload_ready_count")),
        "moonlab_submission_oracle_kernel_ready_count": (
            submission_bundle_summary.get("oracle_kernel_ready_count")),
        "moonlab_submission_qae_observation_ready_count": (
            submission_bundle_summary.get("qae_observation_ready_count")),
        "moonlab_submission_grover_schedule_ready_count": (
            submission_bundle_summary.get("grover_schedule_ready_count")),
        "moonlab_submission_transpilation_required_count": (
            submission_bundle_summary.get("transpilation_required_count")),
        "moonlab_submission_missing_artifact_candidate_count": (
            submission_bundle_summary.get(
                "missing_artifact_candidate_count")),
        "moonlab_hardware_submission_directly_executable": (
            submission_bundle_summary.get(
                "hardware_submission_directly_executable")),
        "moonlab_control_plane_payload_directly_executable": (
            submission_bundle_summary.get(
                "control_plane_payload_directly_executable")),
        "moonlab_oracle_kernel_directly_executable": (
            submission_bundle_summary.get(
                "oracle_kernel_directly_executable")),
        "moonlab_qae_observation_directly_executable": (
            submission_bundle_summary.get(
                "qae_observation_directly_executable")),
        "moonlab_qae_grover_schedule_directly_executable": (
            submission_bundle_summary.get(
                "grover_schedule_directly_executable")),
        "moonlab_hardware_record_template_schema": (
            hardware_record_template_summary.get("schema")),
        "moonlab_hardware_record_schema": (
            hardware_record_template_summary.get("record_schema")),
        "moonlab_hardware_record_template_job_id": (
            hardware_record_template_summary.get("job_id")),
        "moonlab_hardware_submission_scope_schema": (
            hardware_submission_scope_summary.get("schema")),
        "moonlab_hardware_submission_scope_status": (
            hardware_submission_scope_summary.get("status")),
        "moonlab_hardware_submission_scope_ready": (
            hardware_submission_scope_summary.get(
                "hardware_submission_scope_ready")),
        "moonlab_hardware_submission_scope_passing_check_count": (
            hardware_submission_scope_summary.get("passing_check_count")),
        "moonlab_hardware_submission_scope_attention_check_count": (
            hardware_submission_scope_summary.get("attention_check_count")),
        "moonlab_full_game_plan_schema": full_game_plan_summary.get("schema"),
        "moonlab_full_game_deployment_status": (
            full_game_plan_summary.get("status")),
        "moonlab_full_game_asset_unavailable_map_count": (
            full_game_plan_summary.get("asset_unavailable_map_count")),
        "whole_game_moonlab_deployment_claimed": (
            full_game_plan_summary.get(
                "whole_game_moonlab_deployment_claimed")),
        "moonlab_deployment_gate_schema": deployment_gate_summary.get(
            "schema"),
        "moonlab_deployment_gate_status": deployment_gate_summary.get(
            "status"),
        "moonlab_deployment_gate_failed_criterion_count": (
            deployment_gate_summary.get("failed_criterion_count")),
        "moonlab_deployment_gate_blocker_count": (
            deployment_gate_summary.get("blocker_count")),
        "moonlab_deployment_gate_registered_asset_install_script": (
            deployment_gate_summary.get("registered_asset_install_script")),
        "moonlab_deployment_gate_registered_asset_intake_file": (
            deployment_gate_summary.get("registered_asset_intake_file")),
        "moonlab_deployment_gate_post_install_verification_command_count": (
            deployment_gate_summary.get(
                "post_install_verification_command_count")),
        "moonlab_deployment_gate_post_install_capture_queue_command_present": (
            deployment_gate_summary.get(
                "post_install_capture_queue_command_present")),
        "moonlab_deployment_gate_post_install_capture_queue_command": (
            deployment_gate_summary.get(
                "post_install_capture_queue_command")),
        "moonlab_deployment_gate_post_install_capture_queue_script": (
            deployment_gate_summary.get(
                "post_install_capture_queue_script")),
        "whole_game_moonlab_deployment_claim_allowed": (
            deployment_gate_summary.get(
                "whole_game_moonlab_deployment_claim_allowed")),
        "whole_game_hardware_execution_claim_allowed": (
            deployment_gate_summary.get(
                "whole_game_hardware_execution_claim_allowed")),
        "hardware_quantum_advantage_claim_allowed": (
            deployment_gate_summary.get(
                "hardware_quantum_advantage_claim_allowed")),
        "dense_70000_qubit_state_claim_allowed": (
            deployment_gate_summary.get(
                "dense_70000_qubit_state_claim_allowed")),
        "vanilla_capture_matrix_file": artifacts["vanilla"]["matrix"]["packed"]["path"],
        "vanilla_icc_evidence_file": artifacts["vanilla"]["icc_evidence"]["packed"]["path"],
        "breadth_evidence_file": artifacts.get("breadth", {}).get(
            "evidence", {}).get("packed", {}).get("path"),
        "breadth_icc_evidence_file": artifacts.get("breadth", {}).get(
            "icc_evidence", {}).get("packed", {}).get("path"),
        "performance_summary_file": artifacts["capture"]["performance_summary"]["packed"]["path"],
        "performance_icc_evidence_file": artifacts["capture"]["performance_icc_evidence"]["packed"]["path"],
        "performance_source": runtime.get("performance_source"),
        "agent_stream_manifest_file": artifacts["agent_stream"]["manifest"]["packed"]["path"],
        "agent_stream_events_file": artifacts["agent_stream"]["events"]["packed"]["path"],
        "agent_stream_file_count": artifacts["agent_stream"]["stream_directory"]["packed"]["file_count"],
        "fallback_count": runtime.get("fallback_count"),
        "surrogate_count": runtime.get("surrogate_count"),
        "classic3d_count": runtime.get("classic3d_count"),
        "classic2d_count": runtime.get("classic2d_count"),
        "qge_classic_output_hidden": runtime.get(
            "qge_classic_output_hidden"),
        "qge_asset_ownership": runtime.get("qge_asset_ownership"),
        "qge_asset_ownership_fields_present": runtime.get(
            "qge_asset_ownership_fields_present"),
        "qge_asset_ownership_missing_fields": runtime.get(
            "qge_asset_ownership_missing_fields"),
        "qge_asset_ownership_incomplete_fields": runtime.get(
            "qge_asset_ownership_incomplete_fields"),
        "qge_asset_ownership_complete": runtime.get(
            "qge_asset_ownership_complete"),
        "vanilla_ready_for_complete_claim": runtime.get(
            "vanilla_ready_for_complete_claim"),
        "agent_stream_runs_success": runtime.get(
            "agent_stream_runs_success"),
        "classic_agent_run_status": runtime.get(
            "classic_agent_run_status"),
        "qge_agent_run_status": runtime.get(
            "qge_agent_run_status"),
        "classic_agent_startup_issue": runtime.get(
            "classic_agent_startup_issue"),
        "qge_agent_startup_issue": runtime.get(
            "qge_agent_startup_issue"),
        "vanilla_performance_sidecars_success": runtime.get(
            "vanilla_performance_sidecars_success"),
        "classic_performance_status": runtime.get(
            "classic_performance_status"),
        "qge_performance_status": runtime.get(
            "qge_performance_status"),
        "classic_performance_engine_average_quantum_ms_max": runtime.get(
            "classic_performance_engine_average_quantum_ms_max"),
        "qge_performance_engine_average_quantum_ms_max": runtime.get(
            "qge_performance_engine_average_quantum_ms_max"),
        "classic_performance_render_time_ms_max": runtime.get(
            "classic_performance_render_time_ms_max"),
        "qge_performance_render_time_ms_max": runtime.get(
            "qge_performance_render_time_ms_max"),
        "classic_performance_threshold_failures": runtime.get(
            "classic_performance_threshold_failures"),
        "qge_performance_threshold_failures": runtime.get(
            "qge_performance_threshold_failures"),
        "vanilla_performance_ok": runtime.get("vanilla_performance_ok"),
        "agent_stream_run_status": runtime.get(
            "agent_stream_run_status"),
        "agent_stream_run_success": runtime.get(
            "agent_stream_run_success"),
        "agent_stream_startup_issue": runtime.get(
            "agent_stream_startup_issue"),
        "agent_stream_frames_captured": runtime.get(
            "agent_stream_frames_captured"),
        "agent_stream_trace_status": runtime.get(
            "agent_stream_trace_status"),
        "agent_stream_trace_bytes": runtime.get(
            "agent_stream_trace_bytes"),
        "agent_stream_performance_status": runtime.get(
            "agent_stream_performance_status"),
        "performance_status": runtime.get("performance_status"),
        "performance_engine_average_quantum_ms_max": runtime.get(
            "performance_engine_average_quantum_ms_max"),
        "performance_render_time_ms_max": runtime.get(
            "performance_render_time_ms_max"),
        "performance_threshold_failures": runtime.get(
            "performance_threshold_failures"),
        "performance_metric_evidence_present": runtime.get(
            "performance_metric_evidence_present"),
        "performance_ok": runtime.get("performance_ok"),
        "breadth_ready_for_complete_claim": runtime.get(
            "breadth_ready_for_complete_claim"),
        "breadth_matrix_run_count": runtime.get("breadth_matrix_run_count"),
        "breadth_ready_matrix_run_count": runtime.get(
            "breadth_ready_matrix_run_count"),
        "breadth_map_count": runtime.get("breadth_map_count"),
        "breadth_maps": runtime.get("breadth_maps"),
        "runtime_full_game_map_coverage_status": runtime.get(
            "full_game_map_coverage_status"),
        "runtime_full_game_map_target_count": runtime.get(
            "full_game_map_target_count"),
        "runtime_full_game_map_covered_count": runtime.get(
            "full_game_map_covered_count"),
        "runtime_full_game_map_missing_count": runtime.get(
            "full_game_map_missing_count"),
        "runtime_full_game_map_missing_maps": runtime.get(
            "full_game_map_missing_maps"),
        "breadth_total_fallback_count": runtime.get(
            "breadth_total_fallback_count"),
        "breadth_total_surrogate_count": runtime.get(
            "breadth_total_surrogate_count"),
        "breadth_total_cpu_idwt_count": runtime.get(
            "breadth_total_cpu_idwt_count"),
        "breadth_total_native_bridge_count": runtime.get(
            "breadth_total_native_bridge_count"),
        "breadth_total_backend_gate_event_count": runtime.get(
            "breadth_total_backend_gate_event_count"),
        "breadth_total_runtime_backend_probe_event_count": runtime.get(
            "breadth_total_runtime_backend_probe_event_count"),
        "breadth_runtime_backend_probe_targets": runtime.get(
            "breadth_runtime_backend_probe_targets"),
        "breadth_runtime_backend_probe_paths": runtime.get(
            "breadth_runtime_backend_probe_paths"),
        "breadth_required_runtime_backend_probe_targets": runtime.get(
            "breadth_required_runtime_backend_probe_targets"),
        "breadth_runtime_backend_probe_proofs": runtime.get(
            "breadth_runtime_backend_probe_proofs"),
        "breadth_runtime_backend_probe_missing_targets": runtime.get(
            "breadth_runtime_backend_probe_missing_targets"),
        "breadth_runtime_backend_probe_native_targets": runtime.get(
            "breadth_runtime_backend_probe_native_targets"),
        "breadth_runtime_backend_probe_resolved_run_count": runtime.get(
            "breadth_runtime_backend_probe_resolved_run_count"),
        "performance_runtime_backend_probe_resolved": runtime.get(
            "performance_runtime_backend_probe_resolved"),
        "performance_required_runtime_backend_probe_targets": runtime.get(
            "performance_required_runtime_backend_probe_targets"),
        "performance_runtime_backend_probe_proofs": runtime.get(
            "performance_runtime_backend_probe_proofs"),
        "performance_runtime_backend_probe_missing_targets": runtime.get(
            "performance_runtime_backend_probe_missing_targets"),
        "performance_runtime_backend_probe_native_targets": runtime.get(
            "performance_runtime_backend_probe_native_targets"),
        "breadth_evidence_ok": runtime.get("breadth_evidence_ok"),
        "agent_stream_manifest_ok": runtime.get("agent_stream_manifest_ok"),
        "publication_ready_for_complete_claim": ready,
        "whole_game_hardware_execution_claimed": False,
        "hardware_quantum_advantage_claimed": False,
        "dense_70000_qubit_state_claimed": False,
        "status": "success" if ready else "blocked",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path,
                        default=REPO_ROOT / "diagnostics" /
                        "publication_pack" / stamp)
    parser.add_argument("--capture-dir", type=Path)
    parser.add_argument("--vanilla-matrix", type=Path)
    parser.add_argument("--graphics-capture-dir", type=Path,
                        help="Optional quake_graphics harness directory for paired performance sidecars")
    parser.add_argument("--agent-stream-dir", type=Path)
    parser.add_argument("--breadth-evidence", type=Path,
                        help="Optional breadth_evidence.json or breadth evidence directory")
    parser.add_argument("--asset-root", type=Path,
                        default=qge_asset_inventory.DEFAULT_ASSET_ROOT,
                        help="Directory containing loose maps/ and pak*.pak assets")
    parser.add_argument("--registered-asset-candidate", action="append",
                        type=Path, default=[],
                        help="Optional registered PAK/BSP/install path to validate in the packed intake ledger")
    parser.add_argument("--registered-asset-discover-root", action="append",
                        type=Path, default=[],
                        help="Optional root to scan for registered PAK/BSP/id1 candidates")
    parser.add_argument("--registered-asset-discover-common",
                        action=argparse.BooleanOptionalAction,
                        default=False,
                        help="Scan bounded common Quake install locations for the packed intake ledger")
    parser.add_argument("--registered-asset-discover-max-depth",
                        type=int, default=5)
    parser.add_argument("--claims", type=Path,
                        default=REPO_ROOT / "docs/claims/qge_claims.json")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--samples", type=int, action="append",
                        help="Classical sample count; repeatable.")
    parser.add_argument("--qae-levels", type=int, default=4)
    parser.add_argument("--qae-shots", type=int, default=96)
    parser.add_argument("--qae-grid-steps", type=int, default=2048)
    parser.add_argument("--contribution-bits", type=int, default=8)
    args = parser.parse_args(argv)
    if args.samples is None:
        args.samples = list(DEFAULT_SAMPLE_COUNTS)
    return args


def validate_args(args: argparse.Namespace) -> None:
    if args.trials <= 0:
        raise ValueError("--trials must be > 0")
    if any(samples <= 0 for samples in args.samples):
        raise ValueError("--samples values must be > 0")
    if args.qae_levels <= 0:
        raise ValueError("--qae-levels must be > 0")
    if args.qae_shots <= 0:
        raise ValueError("--qae-shots must be > 0")
    if args.qae_grid_steps <= 0:
        raise ValueError("--qae-grid-steps must be > 0")
    if args.contribution_bits <= 0 or args.contribution_bits > 16:
        raise ValueError("--contribution-bits must be in 1..16")
    if args.registered_asset_discover_max_depth < 0:
        raise ValueError("--registered-asset-discover-max-depth must be >= 0")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        validate_args(args)
        manifest = build_manifest(args)
        manifest_path = args.outdir / "publication_manifest.json"
        icc_path = args.outdir / "qge_publication_icc_evidence.json"
        write_json(manifest_path, manifest)
        write_json(icc_path, build_icc_evidence(manifest, manifest_path,
                                                icc_path))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_publication_pack: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_PUBLICATION_MANIFEST {manifest_path}")
    print(f"QGE_PUBLICATION_ICC_EVIDENCE {icc_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
