#!/usr/bin/env python3
"""Audit registered-asset install script against the intake ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_registered_asset_intake  # noqa: E402


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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def first_line_mismatch(expected: str, actual: str) -> dict[str, Any] | None:
    expected_lines = expected.splitlines()
    actual_lines = actual.splitlines()
    max_len = max(len(expected_lines), len(actual_lines))
    for index in range(max_len):
        expected_line = (
            expected_lines[index] if index < len(expected_lines) else None)
        actual_line = actual_lines[index] if index < len(actual_lines) else None
        if expected_line != actual_line:
            return {
                "line": index + 1,
                "expected": expected_line,
                "actual": actual_line,
            }
    return None


def registered_asset_script_audit(
    intake: dict[str, Any] | None,
    script_text: str | None,
    *,
    script_path: str | None = None,
    required: bool = True,
) -> dict[str, Any]:
    intake_data = dict_or_empty(intake)
    recorded = bool(intake_data) and isinstance(script_text, str)
    if not recorded and not required:
        return {
            "required": required,
            "recorded": False,
            "script_path": script_path,
            "expected_line_count": 0,
            "actual_line_count": 0,
            "mismatches": [],
            "mismatch_count": 0,
            "passed": True,
        }
    mismatches: list[dict[str, Any]] = []
    expected = "\n".join(qge_registered_asset_intake.script_lines(intake_data))
    actual = script_text if isinstance(script_text, str) else ""
    if not intake_data:
        mismatches.append({"kind": "missing_intake"})
    if not isinstance(script_text, str):
        mismatches.append({"kind": "missing_script"})
    elif actual != expected:
        mismatches.append({
            "kind": "script_content_mismatch",
            "expected_sha256": sha256_text(expected),
            "actual_sha256": sha256_text(actual),
            "first_line_mismatch": first_line_mismatch(expected, actual),
        })
    mismatch_count = len(mismatches)
    return {
        "required": required,
        "recorded": recorded,
        "script_path": script_path,
        "expected_line_count": len(expected.splitlines()),
        "actual_line_count": len(actual.splitlines()),
        "mismatches": mismatches,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (recorded or not required),
    }


def artifact_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> str | None:
    entry = dict_or_empty(
        dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(section))
        .get(name)
    )
    path = entry.get("path")
    return path if isinstance(path, str) and path else None


def resolve_path(raw_path: str | None, *, base_dir: Path | None = None) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    path = Path(raw_path)
    if path.exists() or path.is_absolute() or base_dir is None:
        return path
    candidate = base_dir / path
    return candidate if candidate.exists() else path


def resolve_manifest(pack_or_manifest: Path) -> Path:
    if pack_or_manifest.is_dir():
        return pack_or_manifest / "publication_manifest.json"
    return pack_or_manifest


def audit_from_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    base_dir = manifest_path.parent if manifest_path is not None else None
    intake_path = resolve_path(
        artifact_path(manifest, "resource", "registered_asset_intake"),
        base_dir=base_dir,
    )
    script_path = resolve_path(
        artifact_path(manifest, "resource", "registered_asset_intake_script"),
        base_dir=base_dir,
    )
    intake = load_json(intake_path) if intake_path and intake_path.is_file() else {}
    script_text = (
        script_path.read_text(encoding="utf-8")
        if script_path and script_path.is_file() else None
    )
    return registered_asset_script_audit(
        intake,
        script_text,
        script_path=str(script_path) if script_path is not None else None,
        required=True,
    )


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
        help="Exit nonzero when the install script does not match intake.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest_path = resolve_manifest(args.pack_or_manifest)
    try:
        audit = audit_from_manifest(
            load_json(manifest_path),
            manifest_path=manifest_path,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_REGISTERED_ASSET_SCRIPT_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_registered_asset_script_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
