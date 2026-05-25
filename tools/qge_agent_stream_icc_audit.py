#!/usr/bin/env python3
"""Audit agent-stream ICC JSONL evidence against its manifest."""

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


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = []
    malformed = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            raw = line.rstrip("\n")
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as exc:
                malformed.append({
                    "line": line_number,
                    "error": str(exc),
                })
                continue
            if isinstance(item, dict):
                records.append(item)
            else:
                malformed.append({
                    "line": line_number,
                    "error": "record is not a JSON object",
                })
    return records, malformed


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def value_at(data: dict[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        value = dict_or_empty(value).get(key)
    return value


def as_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def path_join(root: Any, relative: str) -> str:
    root_string = as_string(root)
    if not root_string:
        return ""
    return str(Path(root_string) / relative)


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
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def expected_last_frame(manifest: dict[str, Any]) -> str:
    frames_captured = int_value(manifest.get("frames_captured"))
    if frames_captured <= 0:
        return ""
    frames_dir = value_at(manifest, "video", "frames_dir")
    return path_join(frames_dir, f"frame_{frames_captured:03d}.png")


def agent_icc_path(manifest: dict[str, Any]) -> str:
    explicit = manifest.get("icc_evidence")
    if isinstance(explicit, str) and explicit:
        return explicit
    return path_join(manifest.get("stream_dir"), "qge_agent_stream_icc_evidence.jsonl")


def entry(kind: str, name: str, value: Any, path: str) -> dict[str, str]:
    return {
        "kind": kind,
        "name": name,
        "value": as_string(value),
        "path": path,
    }


def expected_agent_stream_icc_entries(
    manifest: dict[str, Any],
) -> list[dict[str, str]]:
    icc_path = agent_icc_path(manifest)
    startup_issue = as_string(value_at(manifest, "run", "startup_issue"))
    run_status = "failed" if startup_issue else "ok"
    run_success = "0" if startup_issue else "1"
    trace_requested = truthy(manifest.get("trace_requested"))
    trace_file = as_string(manifest.get("trace")) if trace_requested else ""
    trace_status = (
        as_string(manifest.get("trace_status"))
        if trace_requested else "not_requested"
    )
    trace_bytes = as_string(manifest.get("trace_bytes")) if trace_requested else "0"
    trace_summary_file = (
        as_string(value_at(manifest, "trace_summary", "file"))
        if trace_requested else ""
    )
    audio_bytes = int_value(value_at(manifest, "audio", "bytes"))
    audio_raw = as_string(value_at(manifest, "audio", "raw_file")) if audio_bytes else ""
    audio_meta = (
        as_string(value_at(manifest, "audio", "metadata_file"))
        if audio_bytes else ""
    )
    stream_dir = manifest.get("stream_dir")
    return [
        entry("runtime_backend", "runtime_backend",
              "qge_agent_media_stream", icc_path),
        entry("completion_condition", "completion_reason",
              "qge_agent_media_stream_complete", icc_path),
        entry("runtime_state", "agent_stream_run_status",
              run_status, icc_path),
        entry("runtime_state", "agent_stream_run_success",
              run_success, icc_path),
        entry("runtime_state", "agent_stream_startup_issue",
              startup_issue, icc_path),
        entry("runtime_state", "agent_stream_process_status",
              value_at(manifest, "run", "process_status"), icc_path),
        entry("runtime_state", "agent_stream_timed_out",
              value_at(manifest, "run", "timed_out"), icc_path),
        entry("runtime_state", "agent_stream_frames_captured",
              manifest.get("frames_captured"), icc_path),
        entry("runtime_state", "agent_stream_trace_status",
              trace_status, icc_path),
        entry("runtime_state", "agent_stream_trace_bytes",
              trace_bytes, icc_path),
        entry("runtime_state", "agent_stream_trace_summary_status",
              value_at(manifest, "trace_summary", "status"), icc_path),
        entry("runtime_state", "agent_stream_runtime_evidence_ready",
              value_at(manifest, "trace_summary", "runtime_evidence_ready"),
              icc_path),
        entry("runtime_state", "agent_stream_perf_status",
              value_at(manifest, "performance", "status"), icc_path),
        entry("runtime_state", "agent_stream_noesis_status",
              value_at(manifest, "noesis", "status"), icc_path),
        entry("artifact", "agent_stream_manifest_file",
              path_join(stream_dir, "manifest.json"), icc_path),
        entry("artifact", "agent_events_file",
              value_at(manifest, "logs", "events"), icc_path),
        entry("artifact", "agent_trace_file", trace_file, icc_path),
        entry("artifact", "agent_trace_summary_file",
              trace_summary_file, icc_path),
        entry("artifact", "agent_perf_summary_file",
              value_at(manifest, "performance", "summary_file"), icc_path),
        entry("artifact", "agent_perf_icc_evidence_file",
              value_at(manifest, "performance", "icc_evidence_file"), icc_path),
        entry("artifact", "agent_noesis_summary_file",
              value_at(manifest, "noesis", "summary_file"), icc_path),
        entry("artifact", "agent_noesis_icc_evidence_file",
              value_at(manifest, "noesis", "icc_evidence_file"), icc_path),
        entry("artifact", "agent_noesis_gameplay_outcomes_file",
              value_at(manifest, "noesis", "gameplay_outcomes_file"), icc_path),
        entry("artifact", "agent_input_actions_file",
              value_at(manifest, "input", "action_trace_file"), icc_path),
        entry("artifact", "agent_input_commands_file",
              value_at(manifest, "input", "command_trace_file"), icc_path),
        entry("artifact", "agent_video_frame_file",
              expected_last_frame(manifest), icc_path),
        entry("artifact", "agent_audio_raw_file", audio_raw, icc_path),
        entry("artifact", "agent_audio_metadata_file", audio_meta, icc_path),
    ]


def mismatch_fields(
    expected: dict[str, Any],
    recorded: dict[str, Any],
) -> list[str]:
    return [
        field for field in ("kind", "name", "value", "path")
        if recorded.get(field) != expected.get(field)
    ]


def overclaim_flags(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags = []
    for index, record in enumerate(records):
        name = record.get("name")
        if name in AGENT_STREAM_FORBIDDEN_CLAIMS and truthy(record.get("value")):
            flags.append({
                "index": index,
                "flag": name,
                "value": record.get("value"),
            })
    return flags


def agent_stream_icc_audit(
    manifest: dict[str, Any] | None,
    recorded_entries: list[dict[str, Any]] | None,
    *,
    malformed_records: list[dict[str, Any]] | None = None,
    required: bool = True,
) -> dict[str, Any]:
    manifest_data = dict_or_empty(manifest)
    entries = recorded_entries if isinstance(recorded_entries, list) else []
    malformed = (
        malformed_records if isinstance(malformed_records, list) else []
    )
    if not manifest_data and not required and not entries:
        return {
            "required": required,
            "recorded": False,
            "expected_entry_count": 0,
            "recorded_entry_count": 0,
            "malformed_records": [],
            "missing_entries": [],
            "extra_entries": [],
            "entry_mismatches": [],
            "overclaim_flags": [],
            "mismatch_count": 0,
            "passed": True,
        }

    expected_entries = expected_agent_stream_icc_entries(manifest_data)
    missing_entries = [
        {
            "index": index,
            "name": expected.get("name"),
        }
        for index, expected in enumerate(expected_entries)
        if index >= len(entries)
    ]
    extra_entries = [
        {
            "index": index,
            "name": record.get("name"),
        }
        for index, record in enumerate(entries)
        if index >= len(expected_entries)
    ]
    entry_mismatches = []
    for index, expected in enumerate(expected_entries[:len(entries)]):
        fields = mismatch_fields(expected, entries[index])
        if fields:
            entry_mismatches.append({
                "index": index,
                "name": expected.get("name"),
                "fields": fields,
            })
    flags = overclaim_flags(entries)
    mismatch_count = (
        len(malformed) +
        len(missing_entries) +
        len(extra_entries) +
        len(flags) +
        sum(len(item["fields"]) for item in entry_mismatches)
    )
    recorded = (
        bool(entries) and
        not malformed and
        len(entries) == len(expected_entries)
    )
    return {
        "required": required,
        "recorded": recorded,
        "expected_entry_count": len(expected_entries),
        "recorded_entry_count": len(entries),
        "malformed_records": malformed,
        "missing_entries": missing_entries,
        "extra_entries": extra_entries,
        "entry_mismatches": entry_mismatches,
        "overclaim_flags": flags,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (recorded or not required),
    }


def artifact_stream_directory(manifest: dict[str, Any]) -> str | None:
    entry_value = dict_or_empty(
        dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(
            "agent_stream")).get("stream_directory")
    )
    packed = dict_or_empty(entry_value.get("packed"))
    path = packed.get("path") or entry_value.get("path")
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
    if stream_dir is None:
        return agent_stream_icc_audit({}, [], required=True)
    agent_manifest_path = stream_dir / "manifest.json"
    agent_icc_path = stream_dir / "qge_agent_stream_icc_evidence.jsonl"
    agent_manifest = (
        load_json(agent_manifest_path) if agent_manifest_path.is_file() else {}
    )
    entries, malformed = (
        load_jsonl(agent_icc_path) if agent_icc_path.is_file() else ([], [])
    )
    return agent_stream_icc_audit(
        agent_manifest,
        entries,
        malformed_records=malformed,
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
        help="Exit nonzero when agent-stream ICC JSONL is stale.",
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
            print(f"QGE_AGENT_STREAM_ICC_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_agent_stream_icc_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
