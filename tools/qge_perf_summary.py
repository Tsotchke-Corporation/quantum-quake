#!/usr/bin/env python3
"""Summarize QGE render timing from Quantum Quake runtime logs."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RENDER_PREFIX = "QGE render "
AVG_RE = re.compile(
    r"^QGE: Average quantum render time: "
    r"(?P<ms>[0-9]+(?:\.[0-9]+)?) ms "
    r"\((?P<frames>[0-9]+) frames\)"
)
BACKEND_GATE_RE = re.compile(
    r"^QGE(?::)? [Bb]ackend gate "
    r"phase=(?P<phase>\S+) "
    r"backend=(?P<backend>\S+) "
    r"status=(?P<status>.+?) "
    r"native=(?P<native>[0-9]+) "
    r"active=(?P<active>[0-9]+) "
    r"flags=(?P<flags>0x[0-9a-fA-F]+|[0-9]+) "
    r"path=(?P<path>\S+) "
    r"reason=(?P<reason>\S+) "
    r"probe=(?P<probe>\S+)"
)
RUNTIME_BACKEND_PROBE_RE = re.compile(
    r"^QGE: Runtime backend probe "
    r"target=(?P<target>\S+) "
    r"phase=(?P<phase>\S+) "
    r"backend=(?P<backend>\S+) "
    r"path=(?P<path>\S+) "
    r"result=(?P<result>\S+)"
    r"(?: (?P<rest>.*))?$"
)
NUMBER_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")
REQUIRED_RUNTIME_BACKEND_PROBE_TARGETS = (
    "qge_context_get_or_create_render_acceleration",
    "qge_dwt_render",
    "qge_metal_init_common",
)
RUNTIME_BACKEND_BOUNDARY_SOURCES = {
    "qge_context_get_or_create_render_acceleration": {
        "source_path": "qge/qge_init.c",
        "source_symbol": "qge_context_get_or_create_render_acceleration",
        "required_path": "native_sparse_dwt_render_bridge",
        "required_results": ["created", "cached"],
    },
    "qge_dwt_render": {
        "source_path": "qge/qge_render.c",
        "source_symbol": "qge_dwt_render",
        "required_path": "native_sparse_dwt_render_bridge",
        "required_results": ["native"],
    },
    "qge_metal_init_common": {
        "source_path": "qge/qge_metal.mm",
        "source_symbol": "qge_metal_init_common",
        "required_path": "native_sparse_dwt_render_bridge",
        "required_results": ["active"],
    },
}
NATIVE_RUNTIME_PROBE_RESULTS = {
    "active",
    "cached",
    "created",
    "native",
}


def numeric_value(value: str) -> int | float | str:
    if not NUMBER_RE.match(value):
        return value
    if "." in value:
        return float(value)
    return int(value)


def resolve_log_path(path: Path) -> Path:
    if path.is_dir():
        return path / "quantum_quake.log"
    return path


def parse_render_line(line: str) -> dict[str, Any] | None:
    if not line.startswith(RENDER_PREFIX):
        return None
    fields: dict[str, Any] = {}
    for token in line[len(RENDER_PREFIX):].split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = numeric_value(value)
    return fields if fields else None


def parse_backend_gate_line(line: str) -> dict[str, Any] | None:
    match = BACKEND_GATE_RE.match(line)
    if not match:
        return None
    fields: dict[str, Any] = dict(match.groupdict())
    fields["native"] = int(fields["native"])
    fields["active"] = int(fields["active"])
    fields["flags_int"] = int(str(fields["flags"]), 0)
    return fields


def parse_key_values(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for token in text.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = numeric_value(value)
    return fields


def parse_runtime_backend_probe_line(line: str) -> dict[str, Any] | None:
    match = RUNTIME_BACKEND_PROBE_RE.match(line)
    if not match:
        return None
    fields: dict[str, Any] = {
        key: value
        for key, value in match.groupdict().items()
        if key != "rest" and value is not None
    }
    rest = match.group("rest")
    if rest:
        fields.update(parse_key_values(rest))
    return fields


def int_field(event: dict[str, Any], key: str) -> int | None:
    value = event.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return None


def unique_sorted(values: list[Any]) -> list[str]:
    return sorted({
        str(value)
        for value in values
        if value is not None and str(value) != ""
    })


def runtime_backend_probe_proofs(
    events: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    proofs: dict[str, dict[str, Any]] = {}
    targets = unique_sorted([event.get("target") for event in events])
    for target in targets:
        target_events = [
            event for event in events
            if event.get("target") == target
        ]
        active_values = [
            value for value in (
                int_field(event, "active") for event in target_events
            )
            if value is not None
        ]
        native_values = [
            value for value in (
                int_field(event, "native") for event in target_events
            )
            if value is not None
        ]
        native_bridge_evidence = any(
            event.get("path") == "native_sparse_dwt_render_bridge" and
            str(event.get("result")) in NATIVE_RUNTIME_PROBE_RESULTS
            for event in target_events
        )
        active_evidence = (
            any(value > 0 for value in active_values) or
            any(
                event.get("path") == "native_sparse_dwt_render_bridge" and
                event.get("result") == "active"
                for event in target_events
            )
        )
        proofs[target] = {
            "event_count": len(target_events),
            "backends": unique_sorted([
                event.get("backend") for event in target_events
            ]),
            "paths": unique_sorted([
                event.get("path") for event in target_events
            ]),
            "results": unique_sorted([
                event.get("result") for event in target_events
            ]),
            "phases": unique_sorted([
                event.get("phase") for event in target_events
            ]),
            "native_values": sorted(set(native_values)),
            "active_values": sorted(set(active_values)),
            "native_bridge_evidence": native_bridge_evidence,
            "active_evidence": active_evidence,
            "latest_event": target_events[-1] if target_events else None,
        }
    return proofs


def runtime_backend_probe_rollup(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    proofs = runtime_backend_probe_proofs(events)
    missing_targets = [
        target for target in REQUIRED_RUNTIME_BACKEND_PROBE_TARGETS
        if target not in proofs
    ]
    native_targets = [
        target for target in REQUIRED_RUNTIME_BACKEND_PROBE_TARGETS
        if proofs.get(target, {}).get("native_bridge_evidence")
    ]
    return {
        "required_runtime_backend_probe_targets": list(
            REQUIRED_RUNTIME_BACKEND_PROBE_TARGETS),
        "runtime_backend_probe_proofs": proofs,
        "runtime_backend_probe_missing_targets": missing_targets,
        "runtime_backend_probe_native_targets": native_targets,
        "runtime_backend_probe_resolved": (
            not missing_targets and
            len(native_targets) == len(REQUIRED_RUNTIME_BACKEND_PROBE_TARGETS)
        ),
    }


def merge_runtime_backend_probe_proofs(
    logs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_target: dict[str, list[dict[str, Any]]] = {}
    for log in logs:
        proofs = log.get("runtime_backend_probe_proofs", {})
        if not isinstance(proofs, dict):
            continue
        for target, proof in proofs.items():
            if isinstance(proof, dict):
                by_target.setdefault(str(target), []).append(proof)

    merged: dict[str, dict[str, Any]] = {}
    for target, proofs in by_target.items():
        merged[target] = {
            "event_count": sum(
                int(proof.get("event_count") or 0) for proof in proofs),
            "backends": unique_sorted([
                backend
                for proof in proofs
                for backend in proof.get("backends", [])
            ]),
            "paths": unique_sorted([
                path
                for proof in proofs
                for path in proof.get("paths", [])
            ]),
            "results": unique_sorted([
                result
                for proof in proofs
                for result in proof.get("results", [])
            ]),
            "phases": unique_sorted([
                phase
                for proof in proofs
                for phase in proof.get("phases", [])
            ]),
            "native_values": sorted({
                int(value)
                for proof in proofs
                for value in proof.get("native_values", [])
                if isinstance(value, int)
            }),
            "active_values": sorted({
                int(value)
                for proof in proofs
                for value in proof.get("active_values", [])
                if isinstance(value, int)
            }),
            "native_bridge_evidence": any(
                bool(proof.get("native_bridge_evidence"))
                for proof in proofs
            ),
            "active_evidence": any(
                bool(proof.get("active_evidence"))
                for proof in proofs
            ),
            "latest_event": next(
                (
                    proof.get("latest_event")
                    for proof in reversed(proofs)
                    if proof.get("latest_event") is not None
                ),
                None,
            ),
        }
    return merged


def runtime_backend_probe_rollup_from_proofs(
    proofs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    missing_targets = [
        target for target in REQUIRED_RUNTIME_BACKEND_PROBE_TARGETS
        if target not in proofs
    ]
    native_targets = [
        target for target in REQUIRED_RUNTIME_BACKEND_PROBE_TARGETS
        if proofs.get(target, {}).get("native_bridge_evidence")
    ]
    return {
        "required_runtime_backend_probe_targets": list(
            REQUIRED_RUNTIME_BACKEND_PROBE_TARGETS),
        "runtime_backend_probe_proofs": proofs,
        "runtime_backend_probe_missing_targets": missing_targets,
        "runtime_backend_probe_native_targets": native_targets,
        "runtime_backend_probe_resolved": (
            not missing_targets and
            len(native_targets) == len(REQUIRED_RUNTIME_BACKEND_PROBE_TARGETS)
        ),
    }


def runtime_backend_boundary_from_proofs(
    proofs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    targets = []
    for target in REQUIRED_RUNTIME_BACKEND_PROBE_TARGETS:
        proof = proofs.get(target, {})
        if not isinstance(proof, dict):
            proof = {}
        source = RUNTIME_BACKEND_BOUNDARY_SOURCES[target]
        observed_results = proof.get("results", [])
        if not isinstance(observed_results, list):
            observed_results = []
        observed_paths = proof.get("paths", [])
        if not isinstance(observed_paths, list):
            observed_paths = []
        required_results = source["required_results"]
        required_result_seen = any(
            result in observed_results for result in required_results)
        native_bridge_evidence = bool(proof.get("native_bridge_evidence"))
        active_evidence = bool(proof.get("active_evidence"))
        status = (
            "pass"
            if native_bridge_evidence and active_evidence and required_result_seen
            else "blocked"
        )
        targets.append({
            "target": target,
            **source,
            "status": status,
            "event_count": int(proof.get("event_count") or 0),
            "observed_backends": proof.get("backends", [])
            if isinstance(proof.get("backends"), list) else [],
            "observed_paths": observed_paths,
            "observed_results": observed_results,
            "observed_phases": proof.get("phases", [])
            if isinstance(proof.get("phases"), list) else [],
            "native_bridge_evidence": native_bridge_evidence,
            "active_evidence": active_evidence,
            "required_result_seen": required_result_seen,
            "latest_event": proof.get("latest_event"),
        })
    passed = sum(1 for target in targets if target["status"] == "pass")
    return {
        "schema": "qge.native_backend_boundary.v0",
        "status": "pass" if passed == len(targets) else "blocked",
        "required_target_count": len(targets),
        "passed_target_count": passed,
        "blocked_target_count": len(targets) - passed,
        "targets": targets,
        "limits": [
            "Native backend boundary proof is runtime evidence, not a hardware result.",
            "Every required target must show native bridge path, active evidence, and a target-specific success result.",
            "CPU or unavailable paths remain explicit blocked boundary evidence.",
        ],
    }


def parse_log(path: Path) -> dict[str, Any]:
    log_path = resolve_log_path(path)
    render_frames: list[dict[str, Any]] = []
    average_ms: float | None = None
    average_frames: int | None = None
    backend_gate_lines: list[str] = []
    backend_gate_events: list[dict[str, Any]] = []
    runtime_backend_probe_lines: list[str] = []
    runtime_backend_probe_events: list[dict[str, Any]] = []
    exists = log_path.is_file()
    if exists:
        with log_path.open("r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.strip()
                render = parse_render_line(line)
                if render is not None:
                    render_frames.append(render)
                    continue
                average = AVG_RE.match(line)
                if average:
                    average_ms = float(average.group("ms"))
                    average_frames = int(average.group("frames"))
                    continue
                if line.startswith(("QGE: Backend gate ",
                                    "QGE backend gate ",
                                    "QGE: backend gate ")):
                    backend_gate_lines.append(line)
                    backend_gate = parse_backend_gate_line(line)
                    if backend_gate is not None:
                        backend_gate_events.append(backend_gate)
                    continue
                if line.startswith("QGE: Runtime backend probe "):
                    runtime_backend_probe_lines.append(line)
                    probe = parse_runtime_backend_probe_line(line)
                    if probe is not None:
                        runtime_backend_probe_events.append(probe)

    render_times = [
        float(frame["time"])
        for frame in render_frames
        if isinstance(frame.get("time"), (int, float))
    ]
    component_names = [
        "setup", "encode", "raster", "fdwt", "dwt", "convert", "blit"
    ]
    components: dict[str, dict[str, float | None]] = {}
    for name in component_names:
        values = [
            float(frame[name])
            for frame in render_frames
            if isinstance(frame.get(name), (int, float))
        ]
        components[name] = {
            "max_ms": max(values) if values else None,
            "mean_ms": statistics.fmean(values) if values else None,
        }
    native_idwt_values = [
        int(frame["native_idwt"])
        for frame in render_frames
        if isinstance(frame.get("native_idwt"), int)
    ]
    idwt_fallback_values = [
        int(frame["idwt_fallback"])
        for frame in render_frames
        if isinstance(frame.get("idwt_fallback"), int)
    ]
    cpu_idwt_values = [
        int(frame["cpu_idwt"])
        for frame in render_frames
        if isinstance(frame.get("cpu_idwt"), int)
    ]
    idwt_backend_values = [
        str(frame["idwt_backend"])
        for frame in render_frames
        if isinstance(frame.get("idwt_backend"), str)
    ]
    idwt_backend_counts = {
        backend: idwt_backend_values.count(backend)
        for backend in sorted(set(idwt_backend_values))
    }
    render_bridge_events = [
        event for event in backend_gate_events
        if event.get("phase") == "render_bridge"
    ]
    backend_gate_paths = sorted({
        str(event["path"])
        for event in backend_gate_events
        if isinstance(event.get("path"), str)
    })
    backend_gate_backends = sorted({
        str(event["backend"])
        for event in backend_gate_events
        if isinstance(event.get("backend"), str)
    })
    backend_gate_render_bridge_paths = sorted({
        str(event["path"])
        for event in render_bridge_events
        if isinstance(event.get("path"), str)
    })
    backend_gate_render_bridge_active = any(
        int(event.get("active") or 0) > 0
        for event in render_bridge_events
    )
    runtime_backend_probe_targets = sorted({
        str(event["target"])
        for event in runtime_backend_probe_events
        if isinstance(event.get("target"), str)
    })
    runtime_backend_probe_backends = sorted({
        str(event["backend"])
        for event in runtime_backend_probe_events
        if isinstance(event.get("backend"), str)
    })
    runtime_backend_probe_paths = sorted({
        str(event["path"])
        for event in runtime_backend_probe_events
        if isinstance(event.get("path"), str)
    })
    runtime_backend_probe_results = sorted({
        str(event["result"])
        for event in runtime_backend_probe_events
        if isinstance(event.get("result"), str)
    })
    runtime_backend_probe_evidence = runtime_backend_probe_rollup(
        runtime_backend_probe_events)
    runtime_backend_boundary = runtime_backend_boundary_from_proofs(
        runtime_backend_probe_evidence["runtime_backend_probe_proofs"])

    return {
        "input_path": str(path),
        "log_path": str(log_path),
        "exists": exists,
        "render_frame_count": len(render_frames),
        "engine_average_quantum_ms": average_ms,
        "engine_average_frame_count": average_frames,
        "render_time_ms": {
            "min": min(render_times) if render_times else None,
            "max": max(render_times) if render_times else None,
            "mean": statistics.fmean(render_times) if render_times else None,
        },
        "components": components,
        "native_idwt": {
            "max": max(native_idwt_values) if native_idwt_values else None,
            "sum": sum(native_idwt_values) if native_idwt_values else 0,
        },
        "idwt_fallback": {
            "max": (
                max(idwt_fallback_values)
                if idwt_fallback_values else None
            ),
            "sum": sum(idwt_fallback_values) if idwt_fallback_values else 0,
        },
        "cpu_idwt": {
            "max": max(cpu_idwt_values) if cpu_idwt_values else None,
            "sum": sum(cpu_idwt_values) if cpu_idwt_values else 0,
        },
        "idwt_backend": {
            "last": idwt_backend_values[-1] if idwt_backend_values else None,
            "values": sorted(set(idwt_backend_values)),
            "counts": idwt_backend_counts,
        },
        "last_render_frame": render_frames[-1] if render_frames else None,
        "backend_gate_count": len(backend_gate_lines),
        "backend_gate_event_count": len(backend_gate_events),
        "backend_gate_paths": backend_gate_paths,
        "backend_gate_backends": backend_gate_backends,
        "backend_gate_render_bridge_paths": backend_gate_render_bridge_paths,
        "backend_gate_render_bridge_active": backend_gate_render_bridge_active,
        "backend_gate_init": backend_gate_lines[0] if backend_gate_lines else None,
        "backend_gate_shutdown": (
            backend_gate_lines[-1] if len(backend_gate_lines) > 1 else None
        ),
        "backend_gate_events": backend_gate_events,
        "backend_gate_init_event": (
            backend_gate_events[0] if backend_gate_events else None
        ),
        "backend_gate_render_bridge_event": (
            render_bridge_events[0] if render_bridge_events else None
        ),
        "backend_gate_shutdown_event": (
            backend_gate_events[-1] if len(backend_gate_events) > 1 else None
        ),
        "runtime_backend_probe_count": len(runtime_backend_probe_lines),
        "runtime_backend_probe_event_count": len(
            runtime_backend_probe_events),
        "runtime_backend_probe_targets": runtime_backend_probe_targets,
        "runtime_backend_probe_backends": runtime_backend_probe_backends,
        "runtime_backend_probe_paths": runtime_backend_probe_paths,
        "runtime_backend_probe_results": runtime_backend_probe_results,
        "runtime_backend_probe_events": runtime_backend_probe_events,
        "runtime_backend_boundary": runtime_backend_boundary,
        **runtime_backend_probe_evidence,
    }


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    logs = [parse_log(path) for path in args.paths]
    average_values = [
        float(log["engine_average_quantum_ms"])
        for log in logs
        if isinstance(log.get("engine_average_quantum_ms"), (int, float))
    ]
    render_max_values = [
        float(log["render_time_ms"]["max"])
        for log in logs
        if isinstance(log.get("render_time_ms"), dict) and
        isinstance(log["render_time_ms"].get("max"), (int, float))
    ]
    native_idwt_sums = [
        int((log.get("native_idwt") or {}).get("sum") or 0)
        for log in logs
    ]
    idwt_fallback_sums = [
        int((log.get("idwt_fallback") or {}).get("sum") or 0)
        for log in logs
    ]
    cpu_idwt_sums = [
        int((log.get("cpu_idwt") or {}).get("sum") or 0)
        for log in logs
    ]
    idwt_backend_values = sorted({
        value
        for log in logs
        for value in (log.get("idwt_backend") or {}).get("values", [])
    })
    backend_gate_event_count = sum(
        int(log.get("backend_gate_event_count") or 0)
        for log in logs
    )
    backend_gate_paths = sorted({
        path
        for log in logs
        for path in log.get("backend_gate_paths", [])
    })
    backend_gate_backends = sorted({
        backend
        for log in logs
        for backend in log.get("backend_gate_backends", [])
    })
    backend_gate_render_bridge_paths = sorted({
        path
        for log in logs
        for path in log.get("backend_gate_render_bridge_paths", [])
    })
    backend_gate_render_bridge_active = any(
        bool(log.get("backend_gate_render_bridge_active"))
        for log in logs
    )
    runtime_backend_probe_event_count = sum(
        int(log.get("runtime_backend_probe_event_count") or 0)
        for log in logs
    )
    runtime_backend_probe_targets = sorted({
        target
        for log in logs
        for target in log.get("runtime_backend_probe_targets", [])
    })
    runtime_backend_probe_backends = sorted({
        backend
        for log in logs
        for backend in log.get("runtime_backend_probe_backends", [])
    })
    runtime_backend_probe_paths = sorted({
        path
        for log in logs
        for path in log.get("runtime_backend_probe_paths", [])
    })
    runtime_backend_probe_results = sorted({
        result
        for log in logs
        for result in log.get("runtime_backend_probe_results", [])
    })
    runtime_backend_probe_proofs = merge_runtime_backend_probe_proofs(logs)
    runtime_backend_probe_evidence = runtime_backend_probe_rollup_from_proofs(
        runtime_backend_probe_proofs)
    runtime_backend_boundary = runtime_backend_boundary_from_proofs(
        runtime_backend_probe_proofs)
    missing_logs = [log["log_path"] for log in logs if not log["exists"]]
    metric_evidence_present = bool(average_values or render_max_values)
    threshold_failures: list[dict[str, Any]] = []
    if args.max_average_ms is not None and average_values:
        observed = max(average_values)
        if observed > args.max_average_ms:
            threshold_failures.append({
                "metric": "engine_average_quantum_ms",
                "observed": observed,
                "limit": args.max_average_ms,
            })
    if args.max_render_ms is not None and render_max_values:
        observed = max(render_max_values)
        if observed > args.max_render_ms:
            threshold_failures.append({
                "metric": "render_time_ms.max",
                "observed": observed,
                "limit": args.max_render_ms,
            })

    status = "pass"
    if missing_logs or threshold_failures or not metric_evidence_present:
        status = "blocked"
    return {
        "schema": "qge.performance_summary.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "logs": logs,
        "aggregate": {
            "log_count": len(logs),
            "missing_logs": missing_logs,
            "metric_evidence_present": metric_evidence_present,
            "engine_average_quantum_ms_max": (
                max(average_values) if average_values else None
            ),
            "render_time_ms_max": (
                max(render_max_values) if render_max_values else None
            ),
            "native_idwt_sum": sum(native_idwt_sums),
            "idwt_fallback_sum": sum(idwt_fallback_sums),
            "cpu_idwt_sum": sum(cpu_idwt_sums),
            "idwt_backend_values": idwt_backend_values,
            "backend_gate_event_count": backend_gate_event_count,
            "backend_gate_paths": backend_gate_paths,
            "backend_gate_backends": backend_gate_backends,
            "backend_gate_render_bridge_paths": backend_gate_render_bridge_paths,
            "backend_gate_render_bridge_active": backend_gate_render_bridge_active,
            "runtime_backend_probe_event_count": (
                runtime_backend_probe_event_count),
            "runtime_backend_probe_targets": runtime_backend_probe_targets,
            "runtime_backend_probe_backends": runtime_backend_probe_backends,
            "runtime_backend_probe_paths": runtime_backend_probe_paths,
            "runtime_backend_probe_results": runtime_backend_probe_results,
            **runtime_backend_probe_evidence,
            "runtime_backend_boundary": runtime_backend_boundary,
            "threshold_failures": threshold_failures,
            "max_average_ms": args.max_average_ms,
            "max_render_ms": args.max_render_ms,
        },
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def build_icc_evidence(summary: dict[str, Any],
                       summary_path: Path | None,
                       icc_path: Path) -> dict[str, Any]:
    aggregate = summary["aggregate"]
    ready = summary["status"] == "pass"
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_perf_summary",
        "completion_reason": (
            "qge_runtime_performance_complete"
            if ready else "qge_runtime_performance_evidence_only"
        ),
        "performance_summary_file": str(summary_path) if summary_path else None,
        "performance_icc_evidence_file": str(icc_path),
        "log_count": aggregate["log_count"],
        "missing_logs": aggregate["missing_logs"],
        "engine_average_quantum_ms_max": aggregate[
            "engine_average_quantum_ms_max"],
        "render_time_ms_max": aggregate["render_time_ms_max"],
        "native_idwt_sum": aggregate["native_idwt_sum"],
        "idwt_fallback_sum": aggregate["idwt_fallback_sum"],
        "cpu_idwt_sum": aggregate["cpu_idwt_sum"],
        "idwt_backend_values": aggregate["idwt_backend_values"],
        "backend_gate_event_count": aggregate["backend_gate_event_count"],
        "backend_gate_paths": aggregate["backend_gate_paths"],
        "backend_gate_backends": aggregate["backend_gate_backends"],
        "backend_gate_render_bridge_paths": aggregate[
            "backend_gate_render_bridge_paths"],
        "backend_gate_render_bridge_active": aggregate[
            "backend_gate_render_bridge_active"],
        "runtime_backend_probe_event_count": aggregate[
            "runtime_backend_probe_event_count"],
        "runtime_backend_probe_targets": aggregate[
            "runtime_backend_probe_targets"],
        "runtime_backend_probe_backends": aggregate[
            "runtime_backend_probe_backends"],
        "runtime_backend_probe_paths": aggregate[
            "runtime_backend_probe_paths"],
        "runtime_backend_probe_results": aggregate[
            "runtime_backend_probe_results"],
        "required_runtime_backend_probe_targets": aggregate[
            "required_runtime_backend_probe_targets"],
        "runtime_backend_probe_proofs": aggregate[
            "runtime_backend_probe_proofs"],
        "runtime_backend_probe_missing_targets": aggregate[
            "runtime_backend_probe_missing_targets"],
        "runtime_backend_probe_native_targets": aggregate[
            "runtime_backend_probe_native_targets"],
        "runtime_backend_probe_resolved": aggregate[
            "runtime_backend_probe_resolved"],
        "runtime_backend_boundary_status": aggregate[
            "runtime_backend_boundary"]["status"],
        "runtime_backend_boundary_passed_target_count": aggregate[
            "runtime_backend_boundary"]["passed_target_count"],
        "runtime_backend_boundary_required_target_count": aggregate[
            "runtime_backend_boundary"]["required_target_count"],
        "runtime_backend_boundary_targets": [
            target["target"]
            for target in aggregate["runtime_backend_boundary"]["targets"]
        ],
        "max_average_ms": aggregate["max_average_ms"],
        "max_render_ms": aggregate["max_render_ms"],
        "threshold_failures": aggregate["threshold_failures"],
        "runtime_evidence_present": aggregate["metric_evidence_present"],
        "failure_free": (
            not aggregate["missing_logs"] and
            not aggregate["threshold_failures"] and
            aggregate["metric_evidence_present"]
        ),
        "status": "success" if ready else "blocked",
    }


def print_text(summary: dict[str, Any]) -> None:
    aggregate = summary["aggregate"]
    print(
        "QGE_PERF_SUMMARY "
        f"status={summary['status']} "
        f"logs={aggregate['log_count']} "
        f"avg_max={aggregate['engine_average_quantum_ms_max']} "
        f"render_max={aggregate['render_time_ms_max']}"
    )
    for log in summary["logs"]:
        print(
            "log "
            f"path={log['log_path']} "
            f"exists={int(bool(log['exists']))} "
            f"avg={log['engine_average_quantum_ms']} "
            f"avg_frames={log['engine_average_frame_count']} "
            f"render_frames={log['render_frame_count']} "
            f"render_max={log['render_time_ms']['max']} "
            f"native_idwt={log['native_idwt']['sum']} "
            f"idwt_fallback={log['idwt_fallback']['sum']} "
            f"cpu_idwt={log['cpu_idwt']['sum']} "
            f"idwt_backend={log['idwt_backend']['last']}"
        )
    for failure in aggregate["threshold_failures"]:
        print(
            "threshold_failure "
            f"metric={failure['metric']} "
            f"observed={failure['observed']} "
            f"limit={failure['limit']}"
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path,
                        help="quantum_quake.log file or capture directory")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON summary to stdout")
    parser.add_argument("--out", type=Path,
                        help="Write JSON summary to this path")
    parser.add_argument("--icc-out", type=Path,
                        help="Write ICC evidence JSON to this path")
    parser.add_argument("--max-average-ms", type=float,
                        help="Fail if any engine average exceeds this value")
    parser.add_argument("--max-render-ms", type=float,
                        help="Fail if any QGE render frame time exceeds this value")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    summary = build_summary(args)
    if args.out:
        write_json(args.out, summary)
    if args.icc_out:
        write_json(args.icc_out, build_icc_evidence(summary, args.out,
                                                    args.icc_out))
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print_text(summary)
    return 0 if summary["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
