#!/usr/bin/env python3
"""Audit packed trace summary JSON against packed qge_trace.bin."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_moonlab_overclaim_audit  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402
import qge_trace_summary  # noqa: E402


TRACE_SUMMARY_FORBIDDEN_CLAIMS = (
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


def normalized_trace_summary(
    summary: dict[str, Any],
    *,
    path_value: Any = None,
) -> dict[str, Any]:
    data = json.loads(json.dumps(dict_or_empty(summary)))
    if path_value is None:
        data.pop("path", None)
    else:
        data["path"] = path_value
    return data


def trace_summary_audit(
    expected_summary: dict[str, Any] | None,
    recorded_summary: dict[str, Any] | None,
    *,
    required: bool = True,
) -> dict[str, Any]:
    expected = dict_or_empty(expected_summary)
    recorded = dict_or_empty(recorded_summary)
    active = required or bool(expected) or bool(recorded)
    if not active:
        return {
            "required": required,
            "recorded": False,
            "ignored_fields": ["path"],
            "field_mismatches": [],
            "overclaim_flags": [],
            "mismatch_count": 0,
            "passed": True,
        }
    recorded_path = recorded.get("path") if recorded else None
    field_mismatches = (
        qge_resource_boundary_audit.mismatch_paths(
            normalized_trace_summary(expected, path_value=recorded_path),
            normalized_trace_summary(recorded, path_value=recorded_path),
        )
        if recorded else ["<missing>"]
    )
    overclaim_flags = (
        qge_moonlab_overclaim_audit.recursive_overclaim_flags(
            "trace_summary",
            recorded,
            forbidden=TRACE_SUMMARY_FORBIDDEN_CLAIMS,
        )
        if recorded else []
    )
    mismatch_count = len(field_mismatches) + len(overclaim_flags)
    return {
        "required": required,
        "recorded": bool(recorded),
        "ignored_fields": ["path"],
        "field_mismatches": field_mismatches,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (bool(recorded) or not required),
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
    packed: bool = True,
) -> str | None:
    entry = artifact_entry(manifest, section, name)
    if packed:
        path = dict_or_empty(entry.get("packed")).get("path")
    else:
        path = entry.get("source_path") or dict_or_empty(
            entry.get("packed")).get("path")
    return path if isinstance(path, str) and path else None


def resolve_path(raw_path: str | None, *, base_dir: Path | None = None) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    path = Path(raw_path)
    if path.exists() or path.is_absolute() or base_dir is None:
        return path
    candidate = base_dir / path
    return candidate if candidate.exists() else path


def agent_stream_directory(manifest: dict[str, Any]) -> str | None:
    return artifact_path(manifest, "agent_stream", "stream_directory")


def audit_from_publication_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    base_dir = manifest_path.parent if manifest_path is not None else None
    trace_path = resolve_path(
        artifact_path(manifest, "capture", "trace"),
        base_dir=base_dir,
    )
    stream_dir = resolve_path(
        agent_stream_directory(manifest),
        base_dir=base_dir,
    )
    recorded_path = (
        stream_dir / "trace" / "qge_trace_summary.json"
        if stream_dir is not None else None
    )
    expected = (
        qge_trace_summary.parse_trace(str(trace_path))
        if trace_path is not None and trace_path.is_file() else {}
    )
    recorded = (
        load_json(recorded_path)
        if recorded_path is not None and recorded_path.is_file() else {}
    )
    audit = trace_summary_audit(expected, recorded, required=True)
    audit["trace_file"] = str(trace_path) if trace_path is not None else None
    audit["trace_summary_file"] = (
        str(recorded_path) if recorded_path is not None else None)
    return audit


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
        help="Exit nonzero when the packed trace summary is stale.",
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
            print(f"QGE_TRACE_SUMMARY_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_trace_summary_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
