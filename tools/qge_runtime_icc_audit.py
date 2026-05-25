#!/usr/bin/env python3
"""Audit runtime ICC sidecars copied into a publication pack."""

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
import qge_resource_boundary_audit  # noqa: E402
import qge_vanilla_capture_matrix  # noqa: E402


ICC_EVIDENCE_SCHEMA = "qge.icc_evidence.v0"
RUNTIME_ICC_SIDECARS = (
    "vanilla_icc_evidence",
    "breadth_icc_evidence",
    "performance_icc_evidence",
    "agent_stream_performance_icc_evidence",
)
RUNTIME_SIDECAR_FORBIDDEN_CLAIMS = (
    "whole_game_moonlab_deployment_claimed",
    "whole_game_hardware_execution_claimed",
    "hardware_quantum_advantage_claimed",
    "dense_70000_qubit_state_claimed",
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def path_or_empty(value: str | None) -> Path:
    if not isinstance(value, str) or not value:
        return Path("")
    return Path(value)


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


def expected_runtime_icc_sidecars(
    source_artifacts: dict[str, Any],
    *,
    artifact_paths: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    sources = dict_or_empty(source_artifacts)
    paths = dict_or_empty(artifact_paths)
    return {
        "vanilla_icc_evidence": (
            qge_vanilla_capture_matrix.build_icc_evidence(
                dict_or_empty(sources.get("vanilla_matrix")),
                path_or_empty(paths.get("vanilla_matrix")),
                path_or_empty(paths.get("vanilla_icc_evidence")),
            )
        ),
        "breadth_icc_evidence": (
            qge_breadth_evidence.build_icc_evidence(
                dict_or_empty(sources.get("breadth_evidence")),
                path_or_empty(paths.get("breadth_evidence")),
                path_or_empty(paths.get("breadth_icc_evidence")),
            )
        ),
        "performance_icc_evidence": (
            expected_performance_icc_evidence(
                dict_or_empty(sources.get("performance_summary")),
                path_or_empty(paths.get("performance_summary")),
                path_or_empty(paths.get("performance_icc_evidence")),
            )
        ),
        "agent_stream_performance_icc_evidence": (
            expected_performance_icc_evidence(
                dict_or_empty(sources.get(
                    "agent_stream_performance_summary")),
                path_or_empty(paths.get("agent_stream_performance_summary")),
                path_or_empty(paths.get(
                    "agent_stream_performance_icc_evidence")),
            )
        ),
    }


def expected_performance_icc_evidence(
    summary: dict[str, Any],
    summary_path: Path | None,
    icc_path: Path,
) -> dict[str, Any]:
    aggregate = dict_or_empty(summary.get("aggregate"))
    if isinstance(aggregate.get("runtime_backend_boundary"), dict):
        return qge_perf_summary.build_icc_evidence(
            summary,
            summary_path,
            icc_path,
        )
    ready = summary.get("status") == "pass"
    return {
        "schema": ICC_EVIDENCE_SCHEMA,
        "runtime_backend": "qge_perf_summary",
        "completion_reason": (
            "qge_runtime_performance_complete"
            if ready else "qge_runtime_performance_evidence_only"
        ),
        "performance_summary_file": str(summary_path) if summary_path else None,
        "performance_icc_evidence_file": str(icc_path),
        "log_count": aggregate.get("log_count"),
        "missing_logs": aggregate.get("missing_logs"),
        "engine_average_quantum_ms_max": aggregate.get(
            "engine_average_quantum_ms_max"),
        "render_time_ms_max": aggregate.get("render_time_ms_max"),
        "native_idwt_sum": aggregate.get("native_idwt_sum"),
        "idwt_fallback_sum": aggregate.get("idwt_fallback_sum"),
        "cpu_idwt_sum": aggregate.get("cpu_idwt_sum"),
        "idwt_backend_values": aggregate.get("idwt_backend_values"),
        "backend_gate_event_count": aggregate.get("backend_gate_event_count"),
        "backend_gate_paths": aggregate.get("backend_gate_paths"),
        "backend_gate_backends": aggregate.get("backend_gate_backends"),
        "backend_gate_render_bridge_paths": aggregate.get(
            "backend_gate_render_bridge_paths"),
        "backend_gate_render_bridge_active": aggregate.get(
            "backend_gate_render_bridge_active"),
        "runtime_backend_probe_event_count": aggregate.get(
            "runtime_backend_probe_event_count"),
        "runtime_backend_probe_targets": aggregate.get(
            "runtime_backend_probe_targets"),
        "runtime_backend_probe_backends": aggregate.get(
            "runtime_backend_probe_backends"),
        "runtime_backend_probe_paths": aggregate.get(
            "runtime_backend_probe_paths"),
        "runtime_backend_probe_results": aggregate.get(
            "runtime_backend_probe_results"),
        "required_runtime_backend_probe_targets": aggregate.get(
            "required_runtime_backend_probe_targets"),
        "runtime_backend_probe_proofs": aggregate.get(
            "runtime_backend_probe_proofs"),
        "runtime_backend_probe_missing_targets": aggregate.get(
            "runtime_backend_probe_missing_targets"),
        "runtime_backend_probe_native_targets": aggregate.get(
            "runtime_backend_probe_native_targets"),
        "runtime_backend_probe_resolved": aggregate.get(
            "runtime_backend_probe_resolved"),
        "max_average_ms": aggregate.get("max_average_ms"),
        "max_render_ms": aggregate.get("max_render_ms"),
        "threshold_failures": aggregate.get("threshold_failures"),
        "runtime_evidence_present": aggregate.get("metric_evidence_present"),
        "failure_free": (
            not aggregate.get("missing_logs") and
            not aggregate.get("threshold_failures") and
            aggregate.get("metric_evidence_present")
        ),
        "status": "success" if ready else "blocked",
    }


def empty_audit(required: bool) -> dict[str, Any]:
    return {
        "required": required,
        "recorded": False,
        "expected_sidecar_count": len(RUNTIME_ICC_SIDECARS),
        "recorded_sidecar_count": 0,
        "missing_sidecars": [],
        "schema_mismatches": [],
        "sidecar_mismatches": [],
        "sidecar_build_errors": [],
        "overclaim_flags": [],
        "mismatch_count": 0,
        "passed": not required,
    }


def runtime_icc_sidecar_audit(
    source_artifacts: dict[str, Any] | None,
    runtime_icc_evidence: dict[str, Any] | None,
    *,
    artifact_paths: dict[str, str] | None = None,
    required: bool = False,
) -> dict[str, Any]:
    recorded_sidecars = dict_or_empty(runtime_icc_evidence)
    active = required or bool(recorded_sidecars)
    if not active:
        return empty_audit(required)

    missing_sidecars = [
        name for name in RUNTIME_ICC_SIDECARS
        if not dict_or_empty(recorded_sidecars.get(name))
    ]
    build_errors: list[dict[str, str]] = []
    try:
        expected_sidecars = expected_runtime_icc_sidecars(
            dict_or_empty(source_artifacts),
            artifact_paths=artifact_paths,
        )
    except (KeyError, TypeError, ValueError) as exc:
        build_errors.append({
            "sidecar": "runtime_icc_evidence",
            "error": str(exc),
        })
        expected_sidecars = {}

    schema_mismatches = []
    sidecar_mismatches = []
    overclaim_flags = []
    for name in RUNTIME_ICC_SIDECARS:
        recorded = dict_or_empty(recorded_sidecars.get(name))
        if not recorded:
            continue
        if recorded.get("schema") != ICC_EVIDENCE_SCHEMA:
            schema_mismatches.append(name)
        expected = dict_or_empty(expected_sidecars.get(name))
        fields = qge_resource_boundary_audit.mismatch_paths(
            expected,
            recorded,
        )
        if fields:
            sidecar_mismatches.append({
                "sidecar": name,
                "fields": fields,
            })
        overclaim_flags.extend(
            qge_moonlab_overclaim_audit.recursive_overclaim_flags(
                name,
                recorded,
                forbidden=RUNTIME_SIDECAR_FORBIDDEN_CLAIMS,
            )
        )

    mismatch_count = (
        len(missing_sidecars) +
        len(build_errors) +
        len(overclaim_flags) +
        sum(len(item["fields"]) for item in sidecar_mismatches)
    )
    recorded_count = sum(
        1 for name in RUNTIME_ICC_SIDECARS
        if dict_or_empty(recorded_sidecars.get(name))
    )
    recorded = recorded_count == len(RUNTIME_ICC_SIDECARS)
    passed = mismatch_count == 0 and (recorded or not required)
    return {
        "required": required,
        "recorded": recorded,
        "expected_sidecar_count": len(RUNTIME_ICC_SIDECARS),
        "recorded_sidecar_count": recorded_count,
        "missing_sidecars": missing_sidecars,
        "schema_mismatches": schema_mismatches,
        "sidecar_mismatches": sidecar_mismatches,
        "sidecar_build_errors": build_errors,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": passed,
    }


def artifact_entry(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> dict[str, Any]:
    return dict_or_empty(
        dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(section))
        .get(name)
    )


def artifact_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    packed: bool = False,
) -> str | None:
    entry = artifact_entry(manifest, section, name)
    if packed:
        path = dict_or_empty(entry.get("packed")).get("path")
    else:
        path = entry.get("source_path")
        if not path:
            path = dict_or_empty(entry.get("packed")).get("path")
            if not path:
                path = entry.get("path")
    return path if isinstance(path, str) and path else None


def load_artifact(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> dict[str, Any]:
    path = artifact_path(manifest, section, name, packed=True)
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    return load_json(file_path)


def load_json_file(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    return load_json(path)


def agent_stream_directory(manifest: dict[str, Any]) -> Path | None:
    path = artifact_path(
        manifest,
        "agent_stream",
        "stream_directory",
        packed=True,
    )
    return Path(path) if path else None


def agent_stream_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    stream_dir = agent_stream_directory(manifest)
    return load_json_file(
        stream_dir / "manifest.json" if stream_dir is not None else None)


def agent_stream_performance_paths(
    agent_manifest: dict[str, Any],
) -> tuple[str | None, str | None]:
    performance = dict_or_empty(agent_manifest.get("performance"))
    summary = performance.get("capture_summary_file") or performance.get(
        "summary_file")
    icc = performance.get("capture_icc_evidence_file") or performance.get(
        "icc_evidence_file")
    return (
        summary if isinstance(summary, str) and summary else None,
        icc if isinstance(icc, str) and icc else None,
    )


def load_agent_stream_performance_summary(
    manifest: dict[str, Any],
) -> dict[str, Any]:
    stream_dir = agent_stream_directory(manifest)
    return load_json_file(
        stream_dir / "performance" / "qge_perf_summary.json"
        if stream_dir is not None else None)


def load_agent_stream_performance_icc(
    manifest: dict[str, Any],
) -> dict[str, Any]:
    stream_dir = agent_stream_directory(manifest)
    return load_json_file(
        stream_dir / "performance" / "qge_perf_icc_evidence.json"
        if stream_dir is not None else None)


def runtime_icc_sidecar_audit_from_manifest(
    manifest: dict[str, Any],
    *,
    required: bool = True,
) -> dict[str, Any]:
    agent_manifest = agent_stream_manifest(manifest)
    agent_perf_summary_path, agent_perf_icc_path = (
        agent_stream_performance_paths(agent_manifest)
    )
    source_artifacts = {
        "vanilla_matrix": load_artifact(manifest, "vanilla", "matrix"),
        "breadth_evidence": load_artifact(manifest, "breadth", "evidence"),
        "performance_summary": load_artifact(
            manifest,
            "capture",
            "performance_summary",
        ),
        "agent_stream_performance_summary": (
            load_agent_stream_performance_summary(manifest)),
    }
    runtime_icc_evidence = {
        "vanilla_icc_evidence": load_artifact(
            manifest,
            "vanilla",
            "icc_evidence",
        ),
        "breadth_icc_evidence": load_artifact(
            manifest,
            "breadth",
            "icc_evidence",
        ),
        "performance_icc_evidence": load_artifact(
            manifest,
            "capture",
            "performance_icc_evidence",
        ),
        "agent_stream_performance_icc_evidence": (
            load_agent_stream_performance_icc(manifest)),
    }
    artifact_paths = {
        "vanilla_matrix": artifact_path(manifest, "vanilla", "matrix"),
        "vanilla_icc_evidence": artifact_path(
            manifest,
            "vanilla",
            "icc_evidence",
        ),
        "breadth_evidence": artifact_path(manifest, "breadth", "evidence"),
        "breadth_icc_evidence": artifact_path(
            manifest,
            "breadth",
            "icc_evidence",
        ),
        "performance_summary": artifact_path(
            manifest,
            "capture",
            "performance_summary",
        ),
        "performance_icc_evidence": artifact_path(
            manifest,
            "capture",
            "performance_icc_evidence",
        ),
        "agent_stream_performance_summary": agent_perf_summary_path,
        "agent_stream_performance_icc_evidence": agent_perf_icc_path,
    }
    return runtime_icc_sidecar_audit(
        source_artifacts,
        runtime_icc_evidence,
        artifact_paths=artifact_paths,
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
        help="Exit nonzero when any runtime ICC sidecar is stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        audit = runtime_icc_sidecar_audit_from_manifest(
            load_json(resolve_manifest(args.pack_or_manifest)),
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_RUNTIME_ICC_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_runtime_icc_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
