#!/usr/bin/env python3
"""Audit packed agent-stream manifest references against packed files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


AGENT_STREAM_FORBIDDEN_CLAIMS = (
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


def value_at(data: dict[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        value = dict_or_empty(value).get(key)
    return value


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "claimed"}


def int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def read_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def stream_relative_path(
    manifest: dict[str, Any],
    raw_path: Any,
) -> Path | None:
    raw = optional_str(raw_path)
    stream_root = optional_str(manifest.get("stream_dir"))
    if raw is None or stream_root is None:
        return None
    try:
        return Path(raw).relative_to(Path(stream_root))
    except ValueError:
        return None


def packed_stream_path(
    manifest: dict[str, Any],
    packed_stream_dir: Path,
    raw_path: Any,
) -> Path | None:
    relative = stream_relative_path(manifest, raw_path)
    if relative is None:
        return None
    return packed_stream_dir / relative


def recursive_forbidden_flags(
    prefix: str,
    value: Any,
) -> list[dict[str, Any]]:
    flags = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in AGENT_STREAM_FORBIDDEN_CLAIMS and truthy(child):
                flags.append({
                    "path": path,
                    "flag": key,
                    "value": child,
                })
            flags.extend(recursive_forbidden_flags(path, child))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            flags.extend(recursive_forbidden_flags(path, child))
    return flags


def file_record(name: str, path: Path | None) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path) if path is not None else None,
        "exists": bool(path is not None and path.is_file()),
    }


def add_missing_file(
    missing_files: list[dict[str, Any]],
    name: str,
    path: Path | None,
) -> None:
    record = file_record(name, path)
    if not record["exists"]:
        missing_files.append(record)


def add_value_mismatch(
    value_mismatches: list[dict[str, Any]],
    name: str,
    expected: Any,
    recorded: Any,
) -> None:
    if recorded != expected:
        value_mismatches.append({
            "name": name,
            "expected": expected,
            "recorded": recorded,
        })


def expected_frame_names(frames_captured: int) -> list[str]:
    return [
        f"frame_{index:03d}.png"
        for index in range(1, frames_captured + 1)
    ]


def audit_video_files(
    manifest: dict[str, Any],
    packed_stream_dir: Path,
    missing_files: list[dict[str, Any]],
    value_mismatches: list[dict[str, Any]],
) -> int:
    frames_captured = int_value(manifest.get("frames_captured"))
    frames_dir = packed_stream_path(
        manifest,
        packed_stream_dir,
        value_at(manifest, "video", "frames_dir"),
    )
    if frames_dir is None or not frames_dir.is_dir():
        missing_files.append({
            "name": "video_frames_dir",
            "path": str(frames_dir) if frames_dir is not None else None,
            "exists": False,
        })
        actual_frame_count = 0
        actual_frame_names: list[str] = []
    else:
        actual_frame_names = sorted(
            path.name for path in frames_dir.glob("frame_*.png")
            if path.is_file()
        )
        actual_frame_count = len(actual_frame_names)
    add_value_mismatch(
        value_mismatches,
        "video_frame_file_count",
        frames_captured,
        actual_frame_count,
    )
    add_value_mismatch(
        value_mismatches,
        "video_frame_sequence",
        expected_frame_names(frames_captured),
        actual_frame_names,
    )

    frame_count_path = packed_stream_path(
        manifest,
        packed_stream_dir,
        value_at(manifest, "video", "frame_count_file"),
    )
    add_missing_file(missing_files, "video_frame_count_file", frame_count_path)
    if frame_count_path is not None and frame_count_path.is_file():
        add_value_mismatch(
            value_mismatches,
            "video_frame_count_file_value",
            frames_captured,
            int_value(read_text(frame_count_path)),
        )

    latest_frame_file = packed_stream_path(
        manifest,
        packed_stream_dir,
        value_at(manifest, "video", "latest_frame_file"),
    )
    if frames_captured > 0:
        add_missing_file(
            missing_files,
            "video_latest_frame_file",
            latest_frame_file,
        )
        expected_name = f"frame_{frames_captured:03d}.png"
        latest_raw = read_text(latest_frame_file)
        latest_path = packed_stream_path(
            manifest,
            packed_stream_dir,
            latest_raw,
        )
        add_value_mismatch(
            value_mismatches,
            "video_latest_frame_name",
            expected_name,
            latest_path.name if latest_path is not None else "",
        )
        add_missing_file(missing_files, "video_latest_frame_target", latest_path)
    return actual_frame_count


def audit_audio_files(
    manifest: dict[str, Any],
    packed_stream_dir: Path,
    missing_files: list[dict[str, Any]],
    value_mismatches: list[dict[str, Any]],
) -> None:
    audio_bytes = int_value(value_at(manifest, "audio", "bytes"))
    bytes_path = packed_stream_path(
        manifest,
        packed_stream_dir,
        value_at(manifest, "audio", "bytes_file"),
    )
    add_missing_file(missing_files, "audio_bytes_file", bytes_path)
    if bytes_path is not None and bytes_path.is_file():
        add_value_mismatch(
            value_mismatches,
            "audio_bytes_file_value",
            audio_bytes,
            int_value(read_text(bytes_path)),
        )
    if audio_bytes > 0:
        add_missing_file(
            missing_files,
            "audio_raw_file",
            packed_stream_path(
                manifest,
                packed_stream_dir,
                value_at(manifest, "audio", "raw_file"),
            ),
        )
        add_missing_file(
            missing_files,
            "audio_metadata_file",
            packed_stream_path(
                manifest,
                packed_stream_dir,
                value_at(manifest, "audio", "metadata_file"),
            ),
        )


def audit_agent_stream_manifest(
    agent_manifest: dict[str, Any] | None,
    packed_stream_dir: Path | None,
    *,
    required: bool = True,
) -> dict[str, Any]:
    manifest = dict_or_empty(agent_manifest)
    active = required or bool(manifest)
    if not active:
        return {
            "required": required,
            "recorded": False,
            "missing_files": [],
            "value_mismatches": [],
            "overclaim_flags": [],
            "mismatch_count": 0,
            "passed": True,
        }
    if packed_stream_dir is None:
        return {
            "required": required,
            "recorded": bool(manifest),
            "missing_files": [{
                "name": "agent_stream_directory",
                "path": None,
                "exists": False,
            }],
            "value_mismatches": [],
            "overclaim_flags": [],
            "mismatch_count": 1,
            "passed": False,
        }

    missing_files: list[dict[str, Any]] = []
    value_mismatches: list[dict[str, Any]] = []
    add_value_mismatch(
        value_mismatches,
        "schema",
        "qge.agent_stream.v0",
        manifest.get("schema"),
    )
    add_missing_file(
        missing_files,
        "agent_stream_manifest_file",
        packed_stream_dir / "manifest.json",
    )
    add_missing_file(
        missing_files,
        "agent_stream_icc_evidence_file",
        packed_stream_path(manifest, packed_stream_dir,
                           manifest.get("icc_evidence")),
    )
    add_missing_file(
        missing_files,
        "agent_events_file",
        packed_stream_path(manifest, packed_stream_dir,
                           value_at(manifest, "logs", "events")),
    )
    add_missing_file(
        missing_files,
        "agent_runtime_log_file",
        packed_stream_path(manifest, packed_stream_dir,
                           value_at(manifest, "logs", "runtime_log")),
    )
    add_missing_file(
        missing_files,
        "agent_open_log_file",
        packed_stream_path(manifest, packed_stream_dir,
                           value_at(manifest, "logs", "open_log")),
    )
    add_missing_file(
        missing_files,
        "agent_input_actions_file",
        packed_stream_path(manifest, packed_stream_dir,
                           value_at(manifest, "input", "action_trace_file")),
    )
    add_missing_file(
        missing_files,
        "agent_input_commands_file",
        packed_stream_path(manifest, packed_stream_dir,
                           value_at(manifest, "input", "command_trace_file")),
    )
    audit_video_files(manifest, packed_stream_dir, missing_files,
                      value_mismatches)
    audit_audio_files(manifest, packed_stream_dir, missing_files,
                      value_mismatches)

    if value_at(manifest, "performance", "status") == "complete":
        add_missing_file(
            missing_files,
            "agent_performance_summary_file",
            packed_stream_path(
                manifest,
                packed_stream_dir,
                value_at(manifest, "performance", "summary_file"),
            ),
        )
        add_missing_file(
            missing_files,
            "agent_performance_icc_evidence_file",
            packed_stream_path(
                manifest,
                packed_stream_dir,
                value_at(manifest, "performance", "icc_evidence_file"),
            ),
        )

    if truthy(manifest.get("trace_requested")):
        add_missing_file(
            missing_files,
            "agent_trace_summary_file",
            packed_stream_path(
                manifest,
                packed_stream_dir,
                value_at(manifest, "trace_summary", "agent_file"),
            ),
        )
        add_missing_file(
            missing_files,
            "agent_trace_summary_stderr_file",
            packed_stream_dir / "trace" / "qge_trace_summary.err",
        )

    noesis_status = value_at(manifest, "noesis", "status")
    add_missing_file(
        missing_files,
        "agent_noesis_gameplay_outcomes_file",
        packed_stream_path(
            manifest,
            packed_stream_dir,
            value_at(manifest, "noesis", "gameplay_outcomes_file"),
        ),
    )
    if noesis_status == "complete":
        add_missing_file(
            missing_files,
            "agent_noesis_summary_file",
            packed_stream_path(
                manifest,
                packed_stream_dir,
                value_at(manifest, "noesis", "summary_file"),
            ),
        )
        add_missing_file(
            missing_files,
            "agent_noesis_icc_evidence_file",
            packed_stream_path(
                manifest,
                packed_stream_dir,
                value_at(manifest, "noesis", "icc_evidence_file"),
            ),
        )

    overclaim_flags = recursive_forbidden_flags("agent_stream_manifest",
                                                manifest)
    mismatch_count = (
        len(missing_files) +
        len(value_mismatches) +
        len(overclaim_flags)
    )
    return {
        "required": required,
        "recorded": bool(manifest),
        "missing_file_count": len(missing_files),
        "value_mismatch_count": len(value_mismatches),
        "missing_files": missing_files,
        "value_mismatches": value_mismatches,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (bool(manifest) or not required),
    }


def artifact_stream_directory(manifest: dict[str, Any]) -> str | None:
    entry = dict_or_empty(
        dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(
            "agent_stream")).get("stream_directory")
    )
    packed = dict_or_empty(entry.get("packed"))
    path = packed.get("path") or entry.get("path")
    return path if isinstance(path, str) and path else None


def resolve_path(raw_path: str | None, *, base_dir: Path | None = None) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    path = Path(raw_path)
    if path.exists() or path.is_absolute() or base_dir is None:
        return path
    candidate = base_dir / path
    return candidate if candidate.exists() else path


def audit_from_publication_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    base_dir = manifest_path.parent if manifest_path is not None else None
    stream_dir = resolve_path(
        artifact_stream_directory(manifest),
        base_dir=base_dir,
    )
    agent_manifest_path = (
        stream_dir / "manifest.json" if stream_dir is not None else None
    )
    agent_manifest = (
        load_json(agent_manifest_path)
        if agent_manifest_path is not None and agent_manifest_path.is_file()
        else {}
    )
    return audit_agent_stream_manifest(
        agent_manifest,
        stream_dir,
        required=True,
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
        help="Exit nonzero when packed agent-stream manifest files drift.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest_path = resolve_manifest(args.pack_or_manifest)
    try:
        audit = audit_from_publication_manifest(
            load_json(manifest_path),
            manifest_path=manifest_path,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_AGENT_STREAM_MANIFEST_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_agent_stream_manifest_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
