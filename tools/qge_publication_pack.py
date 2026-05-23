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
import qge_breadth_evidence  # noqa: E402
import qge_moonlab_job_runner  # noqa: E402
import qge_oracle_export  # noqa: E402
import qge_perf_summary  # noqa: E402

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
    cost_model = dict_or_empty(oracle_scene.get("cost_model"))
    sample_space = dict_or_empty(oracle_scene.get("sample_space"))
    snapshot = dict_or_empty(oracle_scene.get("snapshot"))
    render = dict_or_empty(snapshot.get("render"))
    comparison = dict_or_empty(advantage_metrics.get("comparison"))
    best_qae = dict_or_empty(comparison.get("best_qae"))
    qae_resource = dict_or_empty(advantage_metrics.get("resource_estimate"))
    native_targets = (
        performance.get("runtime_backend_probe_native_targets")
        or breadth.get("runtime_backend_probe_native_targets")
        or []
    )
    missing_targets = (
        performance.get("runtime_backend_probe_missing_targets")
        or breadth.get("runtime_backend_probe_missing_targets")
        or []
    )
    required_targets = (
        performance.get("required_runtime_backend_probe_targets")
        or breadth.get("required_runtime_backend_probe_targets")
        or []
    )

    render_ready = (
        bool(conformance.get("ready_for_complete_claim"))
        and int_or_none(conformance.get("fallback_count")) == 0
        and int_or_none(conformance.get("qge_surface_surrogates")) == 0
        and int_or_none(render.get("cpu_idwt")) == 0
    )
    breadth_ready = bool(breadth.get("breadth_ready_for_complete_claim"))
    full_game_coverage = full_game_coverage_from_summary(
        breadth.get("full_game_coverage"),
        breadth.get("maps") if isinstance(breadth.get("maps"), list) else [],
    )
    resource_envelope = {
        "schema": "qge.resource_envelope.v0",
        "posture": {
            "whole_game_hardware_execution_claimed": False,
            "hardware_quantum_advantage_claimed": False,
            "dense_70000_qubit_state_claimed": False,
            "moonlab_simulator_path_claimed": True,
            "hardware_deployment_scope": (
                "selected kernels only; full-game authority remains a "
                "Moonlab/QGE simulator and native-backend integration claim"
            ),
        },
        "domains": {
            "render_primary_framebuffer": {
                "status": (
                    "captured_workload_ready" if render_ready
                    else "evidence_only"
                ),
                "moonlab_representation": (
                    "sparse_dwt_coefficients_plus_finite_shot_render_gate"
                ),
                "candidate_count": int_or_none(
                    cost_model.get("candidate_count"))
                or int_or_none(sample_space.get("candidate_count")),
                "register_bits": int_or_none(sample_space.get("register_bits")),
                "shots_per_frame": (
                    int_or_none(render.get("shots"))
                    or int_or_none(cost_model.get("shots"))
                ),
                "gate_count_per_frame": int_or_none(render.get("gates")),
                "native_backend_path": render.get("idwt_path"),
                "native_backend_result": render.get("idwt_backend"),
                "fallback_count": int_or_none(conformance.get("fallback_count")),
                "surrogate_count": int_or_none(
                    conformance.get("qge_surface_surrogates")),
                "cpu_idwt_count": int_or_none(render.get("cpu_idwt")),
                "hardware_deployment": (
                    "not a full-frame hardware claim; render evidence uses "
                    "Moonlab/QGE sparse state and the native sparse-DWT bridge"
                ),
            },
            "light_transport_qae_benchmark": {
                "status": "simulator_benchmark",
                "moonlab_representation": "finite_shot_mlae_oracle_model",
                "logical_qubits": int_or_none(
                    qae_resource.get("logical_qubits")),
                "candidate_index_bits": int_or_none(
                    qae_resource.get("candidate_index_bits")),
                "contribution_threshold_bits": int_or_none(
                    qae_resource.get("contribution_threshold_bits")),
                "controlled_oracle_calls": int_or_none(
                    qae_resource.get("controlled_oracle_calls")),
                "one_qubit_gates": int_or_none(
                    qae_resource.get("one_qubit_gates")),
                "two_qubit_gates": int_or_none(
                    qae_resource.get("two_qubit_gates")),
                "circuit_depth": int_or_none(
                    qae_resource.get("circuit_depth")),
                "shots": int_or_none(best_qae.get("shots")),
                "hardware_deployment": (
                    "logical benchmark circuit shape only; no practical "
                    "hardware speedup claim"
                ),
            },
            "runtime_backend_probes": {
                "status": (
                    "resolved" if not missing_targets and native_targets
                    else "incomplete"
                ),
                "required_targets": required_targets,
                "native_targets": native_targets,
                "missing_targets": missing_targets,
                "performance_resolved": performance.get(
                    "runtime_backend_probe_resolved"),
                "breadth_resolved_run_count": breadth.get(
                    "runtime_backend_probe_resolved_run_count"),
            },
            "breadth_capture_matrix": {
                "status": (
                    "ready" if breadth_ready else "evidence_only"
                ),
                "map_count": breadth.get("map_count"),
                "maps": breadth.get("maps"),
                "total_fallback_count": breadth.get("total_fallback_count"),
                "total_surrogate_count": breadth.get("total_surrogate_count"),
                "total_cpu_idwt_count": breadth.get("total_cpu_idwt_count"),
                "total_native_bridge_count": breadth.get(
                    "total_native_bridge_count"),
            },
            "full_game_map_coverage": {
                "status": full_game_coverage.get("status"),
                "map_set": full_game_coverage.get("map_set"),
                "target_map_count": full_game_coverage.get(
                    "target_map_count"),
                "covered_map_count": full_game_coverage.get(
                    "covered_map_count"),
                "missing_map_count": full_game_coverage.get(
                    "missing_map_count"),
                "coverage_ratio": full_game_coverage.get("coverage_ratio"),
                "covered_maps": full_game_coverage.get("covered_maps"),
                "missing_maps": full_game_coverage.get("missing_maps"),
                "hardware_deployment": (
                    "not a hardware job; this is the explicit coverage ledger "
                    "for canonical single-player map evidence"
                ),
            },
        },
        "limits": [
            "No unrestricted dense all-game state is claimed.",
            "Whole-game hardware execution is not claimed.",
            "Renderer ownership and renderer visual fidelity are separate claims.",
            "Classic Quake remains a host/reference oracle where not explicitly owned.",
        ],
    }
    return resource_envelope


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
    scaling_path = outdir / "scaling_summary.json"
    scaling_csv_path = outdir / "scaling_summary.csv"
    icc_path = outdir / "qge_advantage_icc_evidence.json"
    qge_advantage_benchmark.write_json(metrics_path, metrics)
    qge_advantage_benchmark.write_curve_csv(curve_path, metrics)
    qge_advantage_benchmark.write_json(scaling_path,
                                       metrics["scaling_summary"])
    qge_advantage_benchmark.write_scaling_csv(scaling_csv_path, metrics)
    qge_advantage_benchmark.write_circuit_text(circuit_path, metrics)
    qge_advantage_benchmark.write_json(
        icc_path,
        qge_advantage_benchmark.build_icc_evidence(
            metrics, metrics_path, curve_path, circuit_path, scaling_path),
    )
    return {
        "metrics": file_info(metrics_path),
        "qae_curve": file_info(curve_path),
        "qae_circuit": file_info(circuit_path),
        "scaling_summary": file_info(scaling_path),
        "scaling_summary_csv": file_info(scaling_csv_path),
        "icc_evidence": file_info(icc_path),
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
    native_backend_boundary = capture_perf_summary.get(
        "runtime_backend_boundary")
    if not isinstance(native_backend_boundary, dict):
        native_backend_boundary = (
            qge_perf_summary.runtime_backend_boundary_from_proofs({})
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
            "trace": capture_artifacts["trace"]["packed"]["path"],
            "frame": capture_artifacts["frame"]["packed"]["path"],
            "vanilla_matrix": vanilla_artifacts["matrix"]["packed"]["path"],
            "performance_summary": (
                capture_artifacts["performance_summary"]["packed"]["path"]),
            "breadth_evidence": (
                breadth_artifacts["evidence"]["packed"]["path"]),
            "full_game_map_coverage": str(full_game_map_coverage_path),
            "asset_inventory": str(asset_inventory_path),
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
    resource_artifacts = {
        "envelope": file_info(resource_path),
        "full_game_map_coverage": file_info(full_game_map_coverage_path),
        "asset_inventory": file_info(asset_inventory_path),
        "asset_inventory_icc_evidence": file_info(asset_inventory_icc_path),
        "native_backend_boundary": file_info(native_backend_boundary_path),
        "moonlab_job_specs": file_info(moonlab_job_specs_path),
        "moonlab_job_results": file_info(moonlab_job_results_path),
        "moonlab_replay_plan": file_info(moonlab_replay_plan_path),
        "moonlab_submission_packet": file_info(moonlab_submission_packet_path),
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
            "full_game_asset_ready": (
                asset_inventory.get("full_game_asset_ready")),
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
                "full_game_asset_ready": asset_inventory.get(
                    "full_game_asset_ready"),
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
            "tools/qge_vanilla_capture_matrix.py <graphics_capture_dir>",
            "tools/qge_breadth_evidence.py --matrix <graphics_capture_dir> --min-maps N",
            "tools/qge_publication_pack.py --capture-dir <trace_capture_dir> --vanilla-matrix <graphics_capture_dir>/vanilla_capture_matrix.json --graphics-capture-dir <graphics_capture_dir> --breadth-evidence <breadth_dir>",
            "tools/qge_moonlab_job_runner.py <pack_dir>/resource/qge_moonlab_job_specs.json --out /tmp/qge_moonlab_job_results.verify.json --expect <pack_dir>/resource/qge_moonlab_job_results.json --plan-out /tmp/qge_moonlab_replay_plan.verify.json --submission-out /tmp/qge_moonlab_submission_packet.verify.json",
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
    job_specs_summary = dict_or_empty(
        advantage_summary.get("moonlab_job_specs_summary"))
    job_results_summary = dict_or_empty(
        advantage_summary.get("moonlab_job_results_summary"))
    replay_plan_summary = dict_or_empty(
        advantage_summary.get("moonlab_replay_plan_summary"))
    submission_packet_summary = dict_or_empty(
        advantage_summary.get("moonlab_submission_packet_summary"))
    native_boundary_summary = dict_or_empty(
        advantage_summary.get("native_backend_boundary_summary"))
    full_game_summary = dict_or_empty(
        advantage_summary.get("full_game_map_coverage_summary"))
    asset_inventory_summary = dict_or_empty(
        advantage_summary.get("asset_inventory_summary"))
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
        "asset_inventory_status": asset_inventory_summary.get("status"),
        "asset_inventory_available_map_count": (
            asset_inventory_summary.get("available_map_count")),
        "asset_inventory_missing_map_count": (
            asset_inventory_summary.get("missing_map_count")),
        "full_game_asset_ready": asset_inventory_summary.get(
            "full_game_asset_ready"),
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
