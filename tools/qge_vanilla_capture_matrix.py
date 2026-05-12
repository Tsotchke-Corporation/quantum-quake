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
    render_line = latest_matching_line(log, "QGE render frame=")
    scene_line = latest_matching_line(log, "QGE scene frame=")
    render_max = matching_key_value_max(
        log,
        "QGE render frame=",
        ["fallback", "surrogate", "micro", "clipped", "invalid",
         "microfill", "culled", "classic3d", "viewmodel"],
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
    agent_stream_runs_success = (
        not explicit_agent_run_failure(classic_agent_run) and
        not explicit_agent_run_failure(qge_agent_run)
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
            "fallback_count": fallback_count,
            "classic3d_count": classic3d,
            "viewmodel_encoded": viewmodel,
            "qge_primary_owner": qge_render.get("owner"),
            "qge_suppressed_classic3d": qge_render.get("suppressed3d"),
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
                fallback_count == 0 and surrogate_count == 0 and
                classic3d == 0 and viewmodel > 0
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
