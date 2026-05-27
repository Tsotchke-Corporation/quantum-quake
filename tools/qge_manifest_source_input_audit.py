#!/usr/bin/env python3
"""Audit publication manifest source inputs against artifact source paths."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXACT_SOURCE_CHECKS = (
    ("vanilla_matrix", "vanilla", "matrix"),
    ("vanilla_icc_evidence", "vanilla", "icc_evidence"),
    ("publication_performance_summary", "capture", "performance_summary"),
    ("claims_ledger", "source_docs", "claims_ledger"),
    ("scene_oracle_ir_doc", "source_docs", "scene_oracle_ir"),
    ("architecture_doc", "source_docs", "architecture"),
    ("advantage_roadmap_doc", "source_docs", "advantage_roadmap"),
    ("agent_stream_dir", "agent_stream", "stream_directory"),
    ("breadth_evidence", "breadth", "evidence"),
)
PARENT_SOURCE_CHECKS = (
    ("capture_dir", "capture", "trace"),
    ("capture_dir", "capture", "frame"),
    ("capture_dir", "capture", "log"),
    ("capture_dir", "capture", "readme"),
    ("graphics_capture_dir", "vanilla", "classic_frame"),
    ("graphics_capture_dir", "vanilla", "qge_frame"),
    ("agent_stream_dir", "agent_stream", "manifest"),
    ("agent_stream_dir", "agent_stream", "events"),
    ("agent_stream_dir", "agent_stream", "icc_evidence"),
)
SIBLING_SOURCE_CHECKS = (
    ("publication_performance_summary", "capture", "performance_icc_evidence"),
    ("breadth_evidence", "breadth", "icc_evidence"),
)
OPTIONAL_MISSING_SOURCE_INPUTS = frozenset({
    "breadth_evidence",
})


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


def normalize_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return str(Path(value).expanduser().resolve())
    except OSError:
        return str(Path(value).expanduser())


def normalized_parent(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return str(Path(value).expanduser().resolve().parent)
    except OSError:
        return str(Path(value).expanduser().parent)


def artifact_source_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> Any:
    artifacts = dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(
        section))
    return dict_or_empty(artifacts.get(name)).get("source_path")


def source_input_value(manifest: dict[str, Any], name: str) -> Any:
    return dict_or_empty(manifest.get("source_inputs")).get(name)


def compare_source(
    manifest: dict[str, Any],
    input_name: str,
    section: str,
    artifact_name: str,
    *,
    relation: str,
) -> dict[str, Any] | None:
    source_value = source_input_value(manifest, input_name)
    artifact_value = artifact_source_path(manifest, section, artifact_name)
    source_norm = normalize_path(source_value)
    artifact_norm = normalize_path(artifact_value)
    if relation == "parent":
        artifact_compare = normalized_parent(artifact_value)
    elif relation == "sibling":
        artifact_compare = normalized_parent(artifact_value)
        source_norm = normalized_parent(source_value)
    else:
        artifact_compare = artifact_norm
    if (
        source_norm is None and
        artifact_compare is None and
        input_name in OPTIONAL_MISSING_SOURCE_INPUTS
    ):
        return None
    if source_norm is None and artifact_compare is None:
        return {
            "source_input": input_name,
            "artifact": f"{section}.{artifact_name}",
            "relation": relation,
            "reason": "missing_source_input_and_artifact_source_path",
            "source_input_path": source_value,
            "artifact_source_path": artifact_value,
            "source_input_normalized": source_norm,
            "artifact_compare_normalized": artifact_compare,
        }
    if source_norm == artifact_compare:
        return None
    reason = "value_mismatch"
    if source_norm is None:
        reason = "missing_source_input"
    elif artifact_norm is None:
        reason = "missing_artifact_source_path"
    return {
        "source_input": input_name,
        "artifact": f"{section}.{artifact_name}",
        "relation": relation,
        "reason": reason,
        "source_input_path": source_value,
        "artifact_source_path": artifact_value,
        "source_input_normalized": source_norm,
        "artifact_compare_normalized": artifact_compare,
    }


def manifest_source_input_audit(
    manifest: dict[str, Any] | None,
    *,
    required: bool = True,
) -> dict[str, Any]:
    manifest_data = dict_or_empty(manifest)
    recorded = bool(dict_or_empty(manifest_data.get("source_inputs")))
    if not recorded and not required:
        return {
            "required": required,
            "recorded": False,
            "check_count": 0,
            "mismatch_count": 0,
            "mismatches": [],
            "passed": True,
        }
    mismatches = []
    check_count = 0
    for input_name, section, artifact_name in EXACT_SOURCE_CHECKS:
        check_count += 1
        mismatch = compare_source(
            manifest_data,
            input_name,
            section,
            artifact_name,
            relation="exact",
        )
        if mismatch:
            mismatches.append(mismatch)
    for input_name, section, artifact_name in PARENT_SOURCE_CHECKS:
        check_count += 1
        mismatch = compare_source(
            manifest_data,
            input_name,
            section,
            artifact_name,
            relation="parent",
        )
        if mismatch:
            mismatches.append(mismatch)
    for input_name, section, artifact_name in SIBLING_SOURCE_CHECKS:
        check_count += 1
        mismatch = compare_source(
            manifest_data,
            input_name,
            section,
            artifact_name,
            relation="sibling",
        )
        if mismatch:
            mismatches.append(mismatch)
    passed = not mismatches and (recorded or not required)
    return {
        "required": required,
        "recorded": recorded,
        "check_count": check_count,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "passed": passed,
    }


def manifest_source_input_icc_summary(
    manifest: dict[str, Any] | None,
    *,
    required: bool = True,
) -> dict[str, Any]:
    audit = manifest_source_input_audit(manifest, required=required)
    return {
        "manifest_source_input_audit_passed": audit.get("passed"),
        "manifest_source_input_recorded": audit.get("recorded"),
        "manifest_source_input_check_count": audit.get("check_count"),
        "manifest_source_input_mismatch_count": audit.get("mismatch_count"),
    }


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
        help="Exit nonzero when manifest source inputs are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        audit = manifest_source_input_audit(
            load_json(resolve_manifest(args.pack_or_manifest)),
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_MANIFEST_SOURCE_INPUT_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_manifest_source_input_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
