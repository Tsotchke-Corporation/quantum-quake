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
NUMBER_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")


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


def parse_log(path: Path) -> dict[str, Any]:
    log_path = resolve_log_path(path)
    render_frames: list[dict[str, Any]] = []
    average_ms: float | None = None
    average_frames: int | None = None
    backend_gate_lines: list[str] = []
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
                if line.startswith("QGE: Backend gate "):
                    backend_gate_lines.append(line)

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
        "last_render_frame": render_frames[-1] if render_frames else None,
        "backend_gate_count": len(backend_gate_lines),
        "backend_gate_init": backend_gate_lines[0] if backend_gate_lines else None,
        "backend_gate_shutdown": (
            backend_gate_lines[-1] if len(backend_gate_lines) > 1 else None
        ),
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
            f"cpu_idwt={log['cpu_idwt']['sum']}"
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
