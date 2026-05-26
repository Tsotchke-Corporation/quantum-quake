#!/usr/bin/env python3
"""Audit resource boundary ledgers against source evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_breadth_evidence  # noqa: E402
import qge_moonlab_overclaim_audit  # noqa: E402
import qge_perf_summary  # noqa: E402


RESOURCE_BOUNDARY_LEDGERS = (
    "resource_envelope",
    "native_backend_boundary",
)
RESOURCE_BOUNDARY_SCHEMAS = {
    "resource_envelope": "qge.resource_envelope.v0",
    "native_backend_boundary": "qge.native_backend_boundary.v0",
}
RESOURCE_BOUNDARY_FORBIDDEN_CLAIMS = (
    "whole_game_moonlab_deployment_claimed",
    "whole_game_hardware_execution_claimed",
    "hardware_quantum_advantage_claimed",
    "dense_70000_qubit_state_claimed",
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def full_game_coverage_from_summary(
    value: Any,
    maps: list[Any],
) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("schema") == (
        "qge.full_game_map_coverage.v0"
    ):
        return value
    return qge_breadth_evidence.build_full_game_map_coverage(maps)


def performance_summary_from_artifact(data: dict[str, Any] | None) -> dict[str, Any]:
    artifact = dict_or_empty(data)
    aggregate = artifact.get("aggregate")
    if not isinstance(aggregate, dict):
        aggregate = artifact
    proofs = dict_or_empty(aggregate.get("runtime_backend_probe_proofs"))
    native_boundary = aggregate.get("runtime_backend_boundary")
    if not isinstance(native_boundary, dict):
        native_boundary = qge_perf_summary.runtime_backend_boundary_from_proofs(
            proofs)
    failures = aggregate.get("threshold_failures")
    return {
        "status": artifact.get("status") or aggregate.get("status"),
        "engine_average_quantum_ms_max": aggregate.get(
            "engine_average_quantum_ms_max"),
        "render_time_ms_max": aggregate.get("render_time_ms_max"),
        "threshold_failures": failures if isinstance(failures, list) else [],
        "metric_evidence_present": aggregate.get("metric_evidence_present"),
        "required_runtime_backend_probe_targets": aggregate.get(
            "required_runtime_backend_probe_targets", []),
        "runtime_backend_probe_proofs": proofs,
        "runtime_backend_probe_missing_targets": aggregate.get(
            "runtime_backend_probe_missing_targets", []),
        "runtime_backend_probe_native_targets": aggregate.get(
            "runtime_backend_probe_native_targets", []),
        "runtime_backend_probe_resolved": aggregate.get(
            "runtime_backend_probe_resolved"),
        "runtime_backend_boundary": native_boundary,
        "runtime_backend_boundary_status": native_boundary.get("status"),
    }


def breadth_summary_from_artifact(data: dict[str, Any] | None) -> dict[str, Any]:
    artifact = dict_or_empty(data)
    aggregate = artifact.get("aggregate")
    if not isinstance(aggregate, dict):
        aggregate = artifact
    default_coverage = qge_breadth_evidence.build_full_game_map_coverage([])
    summary = {
        "status": artifact.get("status") or aggregate.get("status"),
        "breadth_ready_for_complete_claim": aggregate.get(
            "breadth_ready_for_complete_claim"),
        "matrix_run_count": aggregate.get("matrix_run_count"),
        "ready_matrix_run_count": aggregate.get("ready_matrix_run_count"),
        "map_count": aggregate.get("map_count"),
        "maps": aggregate.get("maps", []),
        "full_game_coverage": default_coverage,
        "full_game_map_set": default_coverage["map_set"],
        "full_game_map_coverage_status": default_coverage["status"],
        "full_game_map_target_count": default_coverage["target_map_count"],
        "full_game_map_covered_count": default_coverage["covered_map_count"],
        "full_game_map_missing_count": default_coverage["missing_map_count"],
        "full_game_map_missing_maps": default_coverage["missing_maps"],
        "full_game_map_extra_maps": default_coverage["extra_maps"],
        "total_fallback_count": aggregate.get("total_fallback_count"),
        "total_surrogate_count": aggregate.get("total_surrogate_count"),
        "total_cpu_idwt_count": aggregate.get("total_cpu_idwt_count"),
        "total_native_bridge_count": aggregate.get(
            "total_native_bridge_count"),
        "total_backend_gate_event_count": aggregate.get(
            "total_backend_gate_event_count"),
        "backend_gate_render_bridge_run_count": aggregate.get(
            "backend_gate_render_bridge_run_count"),
        "total_runtime_backend_probe_event_count": aggregate.get(
            "total_runtime_backend_probe_event_count"),
        "runtime_backend_probe_run_count": aggregate.get(
            "runtime_backend_probe_run_count"),
        "runtime_backend_probe_targets": aggregate.get(
            "runtime_backend_probe_targets", []),
        "runtime_backend_probe_paths": aggregate.get(
            "runtime_backend_probe_paths", []),
        "runtime_backend_probe_results": aggregate.get(
            "runtime_backend_probe_results", []),
        "required_runtime_backend_probe_targets": aggregate.get(
            "required_runtime_backend_probe_targets", []),
        "runtime_backend_probe_proofs": aggregate.get(
            "runtime_backend_probe_proofs", {}),
        "runtime_backend_probe_missing_targets": aggregate.get(
            "runtime_backend_probe_missing_targets", []),
        "runtime_backend_probe_native_targets": aggregate.get(
            "runtime_backend_probe_native_targets", []),
        "runtime_backend_probe_resolved_run_count": aggregate.get(
            "runtime_backend_probe_resolved_run_count"),
        "issue_count": aggregate.get("issue_count"),
        "issues": aggregate.get("issues", []),
    }
    maps = summary["maps"] if isinstance(summary["maps"], list) else []
    summary["maps"] = maps
    full_game_coverage = full_game_coverage_from_summary(
        aggregate.get("full_game_coverage"),
        maps,
    )
    summary["full_game_coverage"] = full_game_coverage
    summary["full_game_map_set"] = full_game_coverage.get("map_set")
    summary["full_game_map_coverage_status"] = full_game_coverage.get(
        "status")
    summary["full_game_map_target_count"] = full_game_coverage.get(
        "target_map_count")
    summary["full_game_map_covered_count"] = full_game_coverage.get(
        "covered_map_count")
    summary["full_game_map_missing_count"] = full_game_coverage.get(
        "missing_map_count")
    summary["full_game_map_missing_maps"] = full_game_coverage.get(
        "missing_maps")
    summary["full_game_map_extra_maps"] = full_game_coverage.get("extra_maps")
    return summary


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
    return {
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


def expected_native_backend_boundary(
    performance: dict[str, Any],
) -> dict[str, Any]:
    return qge_perf_summary.runtime_backend_boundary_from_proofs(
        dict_or_empty(performance.get("runtime_backend_probe_proofs")))


def expected_resource_boundary_ledgers(
    source_artifacts: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    sources = dict_or_empty(source_artifacts)
    vanilla = dict_or_empty(sources.get("vanilla_matrix"))
    conformance = dict_or_empty(sources.get("conformance_summary"))
    if not conformance:
        conformance = dict_or_empty(vanilla.get("conformance_summary"))
    performance = performance_summary_from_artifact(
        dict_or_empty(sources.get("performance_summary")))
    breadth = breadth_summary_from_artifact(
        dict_or_empty(sources.get("breadth_evidence")))
    return {
        "resource_envelope": build_resource_envelope(
            dict_or_empty(sources.get("oracle_scene")),
            dict_or_empty(sources.get("advantage_metrics")),
            conformance,
            performance,
            breadth,
        ),
        "native_backend_boundary": expected_native_backend_boundary(
            performance),
    }


def mismatch_paths(expected: Any, recorded: Any, prefix: str = "") -> list[str]:
    if expected == recorded:
        return []
    label = prefix or "<root>"
    if isinstance(expected, dict) and isinstance(recorded, dict):
        paths = []
        for key in sorted(set(expected) | set(recorded)):
            child_prefix = f"{label}.{key}" if prefix else str(key)
            if key not in expected or key not in recorded:
                paths.append(child_prefix)
                continue
            paths.extend(mismatch_paths(
                expected[key],
                recorded[key],
                child_prefix,
            ))
        return paths
    if isinstance(expected, list) and isinstance(recorded, list):
        paths = []
        length = max(len(expected), len(recorded))
        for index in range(length):
            child_prefix = f"{label}[{index}]"
            if index >= len(expected) or index >= len(recorded):
                paths.append(child_prefix)
                continue
            paths.extend(mismatch_paths(
                expected[index],
                recorded[index],
                child_prefix,
            ))
        return paths
    return [label]


def empty_audit(required: bool) -> dict[str, Any]:
    return {
        "required": required,
        "recorded": False,
        "expected_ledger_count": len(RESOURCE_BOUNDARY_LEDGERS),
        "recorded_ledger_count": 0,
        "missing_ledgers": [],
        "schema_mismatches": [],
        "ledger_mismatches": [],
        "ledger_build_errors": [],
        "overclaim_flags": [],
        "mismatch_count": 0,
        "passed": not required,
    }


def resource_boundary_audit(
    source_artifacts: dict[str, Any] | None = None,
    *,
    resource_envelope: dict[str, Any] | None = None,
    native_backend_boundary: dict[str, Any] | None = None,
    required: bool = False,
) -> dict[str, Any]:
    recorded_ledgers = {
        "resource_envelope": dict_or_empty(resource_envelope),
        "native_backend_boundary": dict_or_empty(native_backend_boundary),
    }
    sources_recorded = bool(dict_or_empty(source_artifacts))
    active = (
        required or
        (sources_recorded and any(recorded_ledgers.values())) or
        bool(recorded_ledgers["native_backend_boundary"])
    )
    if not active:
        return empty_audit(required)

    missing_ledgers = [
        name for name in RESOURCE_BOUNDARY_LEDGERS
        if not recorded_ledgers.get(name)
    ]
    build_errors: list[dict[str, str]] = []
    try:
        expected_ledgers = expected_resource_boundary_ledgers(
            dict_or_empty(source_artifacts))
    except (KeyError, TypeError, ValueError) as exc:
        build_errors.append({
            "ledger": "resource_boundary",
            "error": str(exc),
        })
        expected_ledgers = {}

    schema_mismatches = []
    ledger_mismatches = []
    overclaim_flags = []
    for name in RESOURCE_BOUNDARY_LEDGERS:
        recorded = dict_or_empty(recorded_ledgers.get(name))
        if not recorded:
            continue
        if recorded.get("schema") != RESOURCE_BOUNDARY_SCHEMAS[name]:
            schema_mismatches.append(name)
        expected = dict_or_empty(expected_ledgers.get(name))
        fields = mismatch_paths(expected, recorded)
        if fields:
            ledger_mismatches.append({
                "ledger": name,
                "fields": fields,
            })
        overclaim_flags.extend(
            qge_moonlab_overclaim_audit.recursive_overclaim_flags(
                name,
                recorded,
                forbidden=RESOURCE_BOUNDARY_FORBIDDEN_CLAIMS,
            )
        )

    mismatch_count = (
        len(missing_ledgers) +
        len(build_errors) +
        len(overclaim_flags) +
        sum(len(item["fields"]) for item in ledger_mismatches)
    )
    recorded_count = sum(
        1 for name in RESOURCE_BOUNDARY_LEDGERS
        if dict_or_empty(recorded_ledgers.get(name))
    )
    recorded = recorded_count == len(RESOURCE_BOUNDARY_LEDGERS)
    passed = mismatch_count == 0 and (recorded or not required)
    return {
        "required": required,
        "recorded": recorded,
        "expected_ledger_count": len(RESOURCE_BOUNDARY_LEDGERS),
        "recorded_ledger_count": recorded_count,
        "missing_ledgers": missing_ledgers,
        "schema_mismatches": schema_mismatches,
        "ledger_mismatches": ledger_mismatches,
        "ledger_build_errors": build_errors,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": passed,
    }


def artifact_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> str | None:
    entry = dict_or_empty(
        dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(section))
        .get(name)
    )
    path = entry.get("path")
    if not path:
        path = dict_or_empty(entry.get("packed")).get("path")
    if not path:
        path = entry.get("source_path")
    return path if isinstance(path, str) and path else None


def resolve_path(
    raw_path: str | None,
    *,
    base_dir: Path | None = None,
) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    path = Path(raw_path)
    if path.exists() or path.is_absolute() or base_dir is None:
        return path
    candidate = base_dir / path
    return candidate if candidate.exists() else path


def load_artifact_json(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    path = resolve_path(
        artifact_path(manifest, section, name),
        base_dir=base_dir,
    )
    if path is None or not path.is_file():
        return {}
    return load_json(path)


def resource_boundary_audit_from_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
    required: bool = True,
) -> dict[str, Any]:
    base_dir = manifest_path.parent if manifest_path is not None else None
    source_artifacts = {
        "oracle_scene": load_artifact_json(
            manifest, "oracle", "oracle_scene", base_dir=base_dir),
        "advantage_metrics": load_artifact_json(
            manifest, "advantage", "metrics", base_dir=base_dir),
        "vanilla_matrix": load_artifact_json(
            manifest, "vanilla", "matrix", base_dir=base_dir),
        "performance_summary": load_artifact_json(
            manifest, "capture", "performance_summary", base_dir=base_dir),
        "breadth_evidence": load_artifact_json(
            manifest, "breadth", "evidence", base_dir=base_dir),
    }
    return resource_boundary_audit(
        source_artifacts,
        resource_envelope=load_artifact_json(
            manifest, "resource", "envelope", base_dir=base_dir),
        native_backend_boundary=load_artifact_json(
            manifest, "resource", "native_backend_boundary",
            base_dir=base_dir),
        required=required,
    )


def resolve_manifest(pack_or_manifest: Path) -> Path:
    if pack_or_manifest.is_dir():
        return pack_or_manifest / "publication_manifest.json"
    return pack_or_manifest


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pack_or_manifest",
        type=Path,
        help="Publication pack directory or publication_manifest.json path.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional audit JSON output path.",
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit nonzero when resource boundary ledgers are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        manifest_path = resolve_manifest(args.pack_or_manifest)
        audit = resource_boundary_audit_from_manifest(
            load_json(manifest_path),
            manifest_path=manifest_path,
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_RESOURCE_BOUNDARY_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_resource_boundary_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
