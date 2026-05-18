#!/usr/bin/env python3
"""Build a vanilla-vs-QGE capture matrix artifact.

The graphics harness produces paired screenshots and metrics. This tool turns
that directory into a claims/ICC-friendly conformance sidecar without claiming
the port is complete before fallback and media coverage gates pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


KEY_VALUE_RE = re.compile(r"([A-Za-z0-9_]+)=([^ \n]+)")

ASSET_OWNERSHIP_KEYS = [
    "own_world",
    "own_textures",
    "own_lightmaps",
    "own_entities",
    "own_sprites",
    "own_particles",
    "own_viewmodel",
    "own_hud",
    "own_console",
]


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


def file_info(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": sha256_file(path),
    }


def parse_key_values(line: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in KEY_VALUE_RE.findall(line):
        if "/" in value:
            left, right = value.split("/", 1)
            if left.isdigit() and right.isdigit():
                out[key] = {"active": int(left), "total": int(right)}
                continue
        try:
            out[key] = int(value)
            continue
        except ValueError:
            pass
        try:
            out[key] = float(value)
            continue
        except ValueError:
            out[key] = value
    return out


def latest_matching_line(path: Path, needle: str) -> str | None:
    if not path.is_file():
        return None
    latest = None
    latest_frame = -1
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if needle in line:
                stripped = line.strip()
                values = parse_key_values(stripped)
                frame = values.get("frame")
                if isinstance(frame, int) and frame >= latest_frame:
                    latest = stripped
                    latest_frame = frame
                elif latest_frame < 0:
                    latest = stripped
    return latest


def matching_key_value_max(path: Path,
                           needle: str,
                           keys: list[str]) -> dict[str, int]:
    out = {key: 0 for key in keys}
    if not path.is_file():
        return out
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if needle not in line:
                continue
            values = parse_key_values(line)
            for key in keys:
                try:
                    out[key] = max(out[key], int(values.get(key, 0) or 0))
                except (TypeError, ValueError):
                    pass
    return out


def counter_max(values: dict[str, Any], max_values: dict[str, Any],
                key: str) -> int:
    try:
        return max(int(values.get(key, 0) or 0),
                   int(max_values.get(key, 0) or 0))
    except (TypeError, ValueError):
        return 0


def asset_ownership_summary(render: dict[str, Any],
                            render_max: dict[str, Any]) -> dict[str, Any]:
    counters = {
        key: counter_max(render, render_max, key)
        for key in ASSET_OWNERSHIP_KEYS
    }
    present = [key for key in ASSET_OWNERSHIP_KEYS if key in render]
    missing = [key for key in ASSET_OWNERSHIP_KEYS if key not in render]
    incomplete = [key for key, value in counters.items() if value <= 0]
    return {
        "counters": counters,
        "fields_present": len(missing) == 0,
        "present_fields": present,
        "missing_fields": missing,
        "incomplete_fields": incomplete,
        "complete": len(missing) == 0 and len(incomplete) == 0,
    }


def read_readme_value(path: Path, label: str) -> str | None:
    if not path.is_file():
        return None
    prefix = f"{label}:"
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(prefix):
                return line.split(":", 1)[1].strip()
    return None


def agent_manifest_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {"exists": path.is_file()}
    if not path.is_file():
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
        "status": manifest.get("status"),
        "frames_requested": manifest.get("frames_requested"),
        "frames_captured": manifest.get("frames_captured"),
        "trace_requested": manifest.get("trace_requested"),
        "trace": manifest.get("trace"),
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


def false_like(value: Any) -> bool:
    if value is False or value == 0:
        return True
    if isinstance(value, str) and value.lower() in {"0", "false", "no"}:
        return True
    return False


def explicit_agent_run_failure(agent_run: dict[str, Any]) -> bool:
    return (
        agent_run.get("run_status") == "failed" or
        false_like(agent_run.get("run_success")) or
        bool(agent_run.get("startup_issue"))
    )


def performance_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "exists": path.is_file(),
        "status": None,
        "engine_average_quantum_ms_max": None,
        "render_time_ms_max": None,
        "threshold_failures": [],
        "metric_evidence_present": None,
    }
    if not path.is_file():
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
    summary.update({
        "status": data.get("status"),
        "engine_average_quantum_ms_max": aggregate.get(
            "engine_average_quantum_ms_max"),
        "render_time_ms_max": aggregate.get("render_time_ms_max"),
        "threshold_failures": failures if isinstance(failures, list) else [],
        "metric_evidence_present": aggregate.get("metric_evidence_present"),
    })
    return summary


def performance_status(performance: dict[str, Any],
                       agent_run: dict[str, Any]) -> Any:
    if performance.get("status") is not None:
        return performance.get("status")
    return agent_run.get("performance_status")


def explicit_performance_failure(performance: dict[str, Any],
                                 agent_run: dict[str, Any]) -> bool:
    if performance.get("error"):
        return True
    status = performance_status(performance, agent_run)
    if isinstance(status, str) and status and status not in (
            "pass", "success", "complete"):
        return True
    failures = performance.get("threshold_failures")
    if isinstance(failures, list) and failures:
        return True
    return False


def mode_entry(capture_dir: Path,
               mode: str,
               render_value: int,
               metrics_key: str | None = None) -> dict[str, Any]:
    frame = capture_dir / f"{mode}.png"
    log = capture_dir / f"{mode}.log"
    readme = capture_dir / f"{mode}.README.txt"
    agent_manifest = capture_dir / f"{mode}.agent_stream.json"
    agent_events = capture_dir / f"{mode}.agent_events.ndjson"
    agent_icc = capture_dir / f"{mode}.agent_icc_evidence.jsonl"
    perf_summary = capture_dir / f"{mode}.qge_perf_summary.json"
    perf_icc = capture_dir / f"{mode}.qge_perf_icc_evidence.json"
    render_line = latest_matching_line(log, "QGE render frame=")
    scene_line = latest_matching_line(log, "QGE scene frame=")
    render_max = matching_key_value_max(
        log,
        "QGE render frame=",
        ["fallback", "surrogate", "micro", "clipped", "invalid",
         "microfill", "culled", "classic3d", "classic2d",
         "suppressed2d", "viewmodel", *ASSET_OWNERSHIP_KEYS],
    )
    scene_max = matching_key_value_max(
        log,
        "QGE scene frame=",
        ["fallback", "surrogate", "micro", "clipped", "invalid", "culled"],
    )
    entry = {
        "mode": mode,
        "quantum_render": render_value,
        "frame": file_info(frame),
        "log": file_info(log),
        "readme": file_info(readme),
        "agent_stream_manifest": file_info(agent_manifest),
        "agent_stream_events": file_info(agent_events),
        "agent_stream_icc_evidence": file_info(agent_icc),
        "agent_stream_run": agent_manifest_summary(agent_manifest),
        "performance_summary": file_info(perf_summary),
        "performance_icc_evidence": file_info(perf_icc),
        "performance": performance_summary(perf_summary),
        "frames_captured": read_readme_value(readme, "Frames captured"),
        "map": read_readme_value(readme, "Map"),
        "runtime": {},
    }
    if metrics_key:
        entry["metrics_key"] = metrics_key
    if render_line:
        entry["runtime"]["qge_render_line"] = render_line
        entry["runtime"]["qge_render"] = parse_key_values(render_line)
        entry["runtime"]["qge_render_max"] = render_max
    if scene_line:
        entry["runtime"]["qge_scene_line"] = scene_line
        entry["runtime"]["qge_scene"] = parse_key_values(scene_line)
        entry["runtime"]["qge_scene_max"] = scene_max
    return entry


def summarize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    edge = metrics.get("edge", {})
    return {
        "mae_rgb_normalized": metrics.get("mae_rgb_normalized"),
        "rmse_rgb": metrics.get("rmse_rgb"),
        "psnr_db": metrics.get("psnr_db"),
        "luma_ssim_global": metrics.get("luma_ssim_global"),
        "histogram_intersection_rgb": metrics.get("histogram_intersection_rgb"),
        "edge_precision": edge.get("edge_precision"),
        "edge_recall": edge.get("edge_recall"),
        "edge_f1": edge.get("edge_f1"),
        "edge_jaccard": edge.get("edge_jaccard"),
    }


def build_matrix(args: argparse.Namespace) -> dict[str, Any]:
    capture_dir = args.capture_dir.resolve()
    metrics_path = args.metrics or capture_dir / "metrics.json"
    metrics = load_json(metrics_path)
    classic = mode_entry(capture_dir, args.classic_mode,
                         args.classic_render, "reference")
    qge = mode_entry(capture_dir, args.qge_mode, args.qge_render, "candidate")
    classic_agent_run = classic.get("agent_stream_run", {})
    qge_agent_run = qge.get("agent_stream_run", {})
    classic_perf = classic.get("performance", {})
    qge_perf = qge.get("performance", {})
    agent_stream_runs_success = (
        not explicit_agent_run_failure(classic_agent_run) and
        not explicit_agent_run_failure(qge_agent_run)
    )
    performance_sidecars_success = (
        not explicit_performance_failure(classic_perf, classic_agent_run) and
        not explicit_performance_failure(qge_perf, qge_agent_run)
    )
    qge_render = qge.get("runtime", {}).get("qge_render", {})
    qge_render_max = qge.get("runtime", {}).get("qge_render_max", {})
    fallback_count = max(int(qge_render.get("fallback", 0) or 0),
                         int(qge_render_max.get("fallback", 0) or 0))
    surrogate_count = max(int(qge_render.get("surrogate", 0) or 0),
                          int(qge_render_max.get("surrogate", 0) or 0))
    classic3d = max(int(qge_render.get("classic3d", 0) or 0),
                    int(qge_render_max.get("classic3d", 0) or 0))
    viewmodel = max(int(qge_render.get("viewmodel", 0) or 0),
                    int(qge_render_max.get("viewmodel", 0) or 0))
    classic2d = counter_max(qge_render, qge_render_max, "classic2d")
    suppressed3d = counter_max(qge_render, qge_render_max, "suppressed3d")
    suppressed2d = counter_max(qge_render, qge_render_max, "suppressed2d")
    ownership = asset_ownership_summary(qge_render, qge_render_max)
    classic_output_hidden = (
        classic3d == 0 and classic2d == 0 and
        suppressed3d > 0 and suppressed2d > 0
    )

    return {
        "schema": "qge.vanilla_capture_matrix.v0",
        "capture_dir": str(capture_dir),
        "metrics_file": str(metrics_path.resolve()),
        "claim_id": "engine.vanilla_quake_conformance",
        "modes": [classic, qge],
        "image_metrics": summarize_metrics(metrics),
        "conformance_summary": {
            "status": "evidence_only",
            "classic_frame_exists": classic["frame"]["exists"],
            "qge_frame_exists": qge["frame"]["exists"],
            "classic_agent_run_status": classic_agent_run.get("run_status"),
            "qge_agent_run_status": qge_agent_run.get("run_status"),
            "classic_agent_startup_issue": classic_agent_run.get("startup_issue"),
            "qge_agent_startup_issue": qge_agent_run.get("startup_issue"),
            "agent_stream_runs_success": agent_stream_runs_success,
            "classic_performance_status": performance_status(
                classic_perf, classic_agent_run),
            "qge_performance_status": performance_status(
                qge_perf, qge_agent_run),
            "classic_performance_engine_average_quantum_ms_max": (
                classic_perf.get("engine_average_quantum_ms_max")),
            "qge_performance_engine_average_quantum_ms_max": (
                qge_perf.get("engine_average_quantum_ms_max")),
            "classic_performance_render_time_ms_max": classic_perf.get(
                "render_time_ms_max"),
            "qge_performance_render_time_ms_max": qge_perf.get(
                "render_time_ms_max"),
            "classic_performance_threshold_failures": classic_perf.get(
                "threshold_failures"),
            "qge_performance_threshold_failures": qge_perf.get(
                "threshold_failures"),
            "performance_sidecars_success": performance_sidecars_success,
            "fallback_count": fallback_count,
            "classic3d_count": classic3d,
            "classic2d_count": classic2d,
            "viewmodel_encoded": viewmodel,
            "qge_primary_owner": qge_render.get("owner"),
            "qge_suppressed_classic3d": suppressed3d,
            "qge_suppressed_classic2d": suppressed2d,
            "qge_classic_output_hidden": classic_output_hidden,
            "qge_asset_ownership": ownership["counters"],
            "qge_asset_ownership_fields_present": (
                ownership["fields_present"]),
            "qge_asset_ownership_missing_fields": (
                ownership["missing_fields"]),
            "qge_asset_ownership_incomplete_fields": (
                ownership["incomplete_fields"]),
            "qge_asset_ownership_complete": ownership["complete"],
            "qge_surface_polygons": qge_render.get("poly"),
            "qge_surface_triangles": qge_render.get("tris"),
            "qge_surface_surrogates": surrogate_count,
            "qge_surface_culled": max(
                int(qge_render.get("culled", 0) or 0),
                int(qge_render_max.get("culled", 0) or 0),
            ),
            "qge_surface_micro_surrogates": max(
                int(qge_render.get("micro", 0) or 0),
                int(qge_render_max.get("micro", 0) or 0),
            ),
            "qge_surface_micro_fills": max(
                int(qge_render.get("microfill", 0) or 0),
                int(qge_render_max.get("microfill", 0) or 0),
            ),
            "qge_surface_clipped_surrogates": max(
                int(qge_render.get("clipped", 0) or 0),
                int(qge_render_max.get("clipped", 0) or 0),
            ),
            "qge_edge_fills": qge_render.get("edgefills"),
            "ready_for_complete_claim": (
                classic["frame"]["exists"] and qge["frame"]["exists"] and
                agent_stream_runs_success and
                performance_sidecars_success and
                fallback_count == 0 and surrogate_count == 0 and
                classic_output_hidden and viewmodel > 0 and
                ownership["complete"]
            ),
        },
        "claim_posture": {
            "allowed_wording": (
                "This capture matrix compares a classic reference frame with a "
                "QGE primary-render frame and reports explicit media ownership "
                "and visual parity counters."
            ),
            "disallowed_wording": (
                "This artifact alone proves the entire vanilla Quake port is "
                "complete."
            ),
        },
    }


def build_icc_evidence(matrix: dict[str, Any],
                       matrix_path: Path,
                       icc_path: Path) -> dict[str, Any]:
    summary = matrix["conformance_summary"]
    modes = {mode["mode"]: mode for mode in matrix["modes"]}
    classic = modes.get("classic", matrix["modes"][0])
    qge = modes.get("quantum", matrix["modes"][-1])
    ready = bool(summary["ready_for_complete_claim"])
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_vanilla_capture_matrix",
        "completion_reason": (
            "qge_vanilla_capture_matrix_complete"
            if ready else "qge_vanilla_capture_matrix_evidence_only"
        ),
        "vanilla_capture_matrix_file": str(matrix_path),
        "icc_evidence_file": str(icc_path),
        "capture_dir": matrix["capture_dir"],
        "metrics_file": matrix["metrics_file"],
        "classic_frame_file": classic["frame"]["path"],
        "qge_frame_file": qge["frame"]["path"],
        "fallback_count": summary["fallback_count"],
        "surrogate_count": summary["qge_surface_surrogates"],
        "culled_count": summary["qge_surface_culled"],
        "classic3d_count": summary["classic3d_count"],
        "classic_agent_run_status": summary.get("classic_agent_run_status"),
        "qge_agent_run_status": summary.get("qge_agent_run_status"),
        "classic_agent_startup_issue": summary.get("classic_agent_startup_issue"),
        "qge_agent_startup_issue": summary.get("qge_agent_startup_issue"),
        "agent_stream_runs_success": summary.get("agent_stream_runs_success"),
        "classic_performance_status": summary.get("classic_performance_status"),
        "qge_performance_status": summary.get("qge_performance_status"),
        "classic_performance_engine_average_quantum_ms_max": summary.get(
            "classic_performance_engine_average_quantum_ms_max"),
        "qge_performance_engine_average_quantum_ms_max": summary.get(
            "qge_performance_engine_average_quantum_ms_max"),
        "classic_performance_render_time_ms_max": summary.get(
            "classic_performance_render_time_ms_max"),
        "qge_performance_render_time_ms_max": summary.get(
            "qge_performance_render_time_ms_max"),
        "classic_performance_threshold_failures": summary.get(
            "classic_performance_threshold_failures"),
        "qge_performance_threshold_failures": summary.get(
            "qge_performance_threshold_failures"),
        "performance_sidecars_success": summary.get(
            "performance_sidecars_success"),
        "viewmodel_encoded": summary["viewmodel_encoded"],
        "ready_for_complete_claim": ready,
        "status": "success" if ready else "blocked",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--icc-out", type=Path)
    parser.add_argument("--classic-mode", default="classic")
    parser.add_argument("--qge-mode", default="quantum")
    parser.add_argument("--classic-render", type=int, default=0)
    parser.add_argument("--qge-render", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    out_path = args.out or args.capture_dir / "vanilla_capture_matrix.json"
    icc_path = args.icc_out or args.capture_dir / "qge_vanilla_icc_evidence.json"
    try:
        matrix = build_matrix(args)
        write_json(out_path, matrix)
        write_json(icc_path, build_icc_evidence(matrix, out_path, icc_path))
    except (OSError, ValueError, KeyError) as exc:
        print(f"qge_vanilla_capture_matrix: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_VANILLA_CAPTURE_MATRIX {out_path}")
    print(f"QGE_VANILLA_ICC_EVIDENCE {icc_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
