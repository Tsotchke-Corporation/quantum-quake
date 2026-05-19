#!/usr/bin/env python3
"""Validate QGE source-audio authority evidence from an agent stream run."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


AUDIO_LINE = "QGE audio source owner=audio_source "
REQUIRED_AUTHORITY_KEYS = (
    "attenuation_pan_sources",
    "attenuation_pan_requested",
    "attenuation_pan_selected",
    "attenuation_pan_fallback",
    "attenuation_pan_avg_abs_error",
    "attenuation_pan_max_error",
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return default
    return default


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ok", "complete"}
    return False


def resolve_manifest_path(manifest_path: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return (manifest_path.parent / path).resolve()


def find_trace_summary(manifest_path: Path, manifest: dict[str, Any]) -> Path | None:
    trace_summary = manifest.get("trace_summary")
    candidates: list[Path] = []
    if isinstance(trace_summary, dict):
        for key in ("agent_file", "file"):
            path = resolve_manifest_path(manifest_path, trace_summary.get(key))
            if path is not None:
                candidates.append(path)
    candidates.append(manifest_path.parent / "trace" / "qge_trace_summary.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0] if candidates else None


def find_runtime_log(manifest_path: Path, manifest: dict[str, Any]) -> Path | None:
    logs = manifest.get("logs")
    candidates: list[Path] = []
    if isinstance(logs, dict):
        path = resolve_manifest_path(manifest_path, logs.get("runtime_log"))
        if path is not None:
            candidates.append(path)
    candidates.append(manifest_path.parent / "logs" / "quantum_quake.log")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0] if candidates else None


def parse_audio_line(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=([^ \n]+)", line):
        values[key] = value
    return values


def read_audio_lines(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [
        parse_audio_line(line)
        for line in text.splitlines()
        if AUDIO_LINE in line
    ]


def max_int(lines: list[dict[str, str]], key: str) -> int:
    return max((as_int(line.get(key)) for line in lines), default=0)


def validate(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.manifest
    if args.agent_stream_dir is not None:
        manifest_path = args.agent_stream_dir / "manifest.json"
    if manifest_path is None:
        raise ValueError("provide --agent-stream-dir or --manifest")

    manifest = load_json(manifest_path)
    errors: list[str] = []

    audio = manifest.get("audio", {})
    if not isinstance(audio, dict):
        audio = {}
        errors.append("manifest.audio must be an object")

    trace_summary = manifest.get("trace_summary", {})
    if not isinstance(trace_summary, dict):
        trace_summary = {}
        errors.append("manifest.trace_summary must be an object")

    if audio.get("status") != "complete":
        errors.append("manifest.audio.status must be complete")
    if as_int(audio.get("snd_quantum")) < 2:
        errors.append("manifest.audio.snd_quantum must be 2 or higher")
    if as_int(audio.get("snd_quantum_source_authority")) != 1:
        errors.append("manifest.audio.snd_quantum_source_authority must be 1")
    if as_int(audio.get("bytes")) <= 0:
        errors.append("manifest.audio.bytes must be nonzero")
    if trace_summary.get("status") != "complete":
        errors.append("manifest.trace_summary.status must be complete")
    if not as_bool(trace_summary.get("runtime_evidence_ready")):
        errors.append("manifest.trace_summary.runtime_evidence_ready must be true")

    summary_path = find_trace_summary(manifest_path, manifest)
    runtime_audio: dict[str, Any] = {}
    if summary_path is None or not summary_path.is_file():
        errors.append("trace summary JSON is missing")
    else:
        summary = load_json(summary_path)
        runtime_evidence = summary.get("runtime_evidence", {})
        if isinstance(runtime_evidence, dict):
            audio_evidence = runtime_evidence.get("audio", {})
            if isinstance(audio_evidence, dict):
                runtime_audio = audio_evidence
        if not as_bool(runtime_audio.get("ready")):
            errors.append("trace runtime_evidence.audio.ready must be true")
        if as_int(runtime_audio.get("source_spatial_count")) <= 0:
            errors.append("trace must contain audio source-spatial probes")
        if as_int(runtime_audio.get("source_frame_count")) <= 0:
            errors.append("trace must contain audio source-frame probes")
        flags = runtime_audio.get("flags", {})
        if not isinstance(flags, dict) or not as_bool(flags.get("processed")):
            errors.append("trace audio flags must show processed source audio")
        if not isinstance(flags, dict) or not as_bool(flags.get("spatial")):
            errors.append("trace audio flags must show spatial source metadata")

    log_path = args.log or find_runtime_log(manifest_path, manifest)
    audio_lines: list[dict[str, str]] = []
    if log_path is None or not log_path.is_file():
        errors.append("runtime log is missing")
    else:
        audio_lines = read_audio_lines(log_path)
        if not audio_lines:
            errors.append("runtime log has no QGE audio source telemetry")
        if max_int(audio_lines, "processed_blocks") <= 0:
            errors.append("runtime log must show processed source blocks")
        if max_int(audio_lines, "processed_samples") <= 0:
            errors.append("runtime log must show processed source samples")
        if max_int(audio_lines, "spatial_sources") <= 0:
            errors.append("runtime log must show spatial source count")
        for key in REQUIRED_AUTHORITY_KEYS:
            if not any(key in line for line in audio_lines):
                errors.append(f"runtime log missing {key} telemetry")
        if max_int(audio_lines, "attenuation_pan_sources") <= 0:
            errors.append("runtime log must exercise attenuation/pan authority inputs")
        if max_int(audio_lines, "attenuation_pan_requested") <= 0:
            errors.append("runtime log must show source authority requested")
        if (max_int(audio_lines, "attenuation_pan_selected") +
                max_int(audio_lines, "attenuation_pan_fallback")) <= 0:
            errors.append(
                "runtime log must show QGE source-volume selection or gated fallback")

    result = {
        "status": "pass" if not errors else "fail",
        "manifest": str(manifest_path),
        "trace_summary": str(summary_path) if summary_path else None,
        "runtime_log": str(log_path) if log_path else None,
        "audio_bytes": as_int(audio.get("bytes")),
        "source_spatial_count": as_int(runtime_audio.get("source_spatial_count")),
        "source_frame_count": as_int(runtime_audio.get("source_frame_count")),
        "log_audio_source_lines": len(audio_lines),
        "attenuation_pan_sources_max": max_int(
            audio_lines, "attenuation_pan_sources"),
        "attenuation_pan_requested_max": max_int(
            audio_lines, "attenuation_pan_requested"),
        "attenuation_pan_selected_max": max_int(
            audio_lines, "attenuation_pan_selected"),
        "attenuation_pan_fallback_max": max_int(
            audio_lines, "attenuation_pan_fallback"),
        "errors": errors,
    }
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__)
    parser.add_argument("--agent-stream-dir", type=Path,
                        help="Agent stream directory containing manifest.json")
    parser.add_argument("--manifest", type=Path,
                        help="Path to an agent stream manifest.json")
    parser.add_argument("--log", type=Path,
                        help="Override runtime log path")
    parser.add_argument("--json", action="store_true",
                        help="Print machine-readable JSON")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    result = validate(args)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "pass":
        print(
            "QGE audio authority smoke: PASSED "
            f"audio_bytes={result['audio_bytes']} "
            f"source_spatial={result['source_spatial_count']} "
            f"source_frames={result['source_frame_count']} "
            f"attenuation_pan_sources={result['attenuation_pan_sources_max']} "
            f"selected={result['attenuation_pan_selected_max']} "
            f"fallback={result['attenuation_pan_fallback_max']}")
    else:
        print("QGE audio authority smoke: FAILED", file=sys.stderr)
        for error in result["errors"]:
            print(f"- {error}", file=sys.stderr)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
