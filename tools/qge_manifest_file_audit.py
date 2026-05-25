#!/usr/bin/env python3
"""Audit publication manifest file records against files on disk."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def path_label(prefix: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{prefix}[{key}]" if prefix else f"[{key}]"
    return f"{prefix}.{key}" if prefix else key


def is_file_record(value: dict[str, Any]) -> bool:
    return (
        "path" in value and
        "exists" in value and
        "size_bytes" in value and
        "sha256" in value
    )


def is_directory_record(value: dict[str, Any]) -> bool:
    return (
        "path" in value and
        "exists" in value and
        "file_count" in value and
        "size_bytes" in value and
        isinstance(value.get("files"), list)
    )


def iter_records(value: Any, prefix: str = "") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if is_file_record(value):
            records.append({
                "kind": "file",
                "source": prefix,
                "record": value,
            })
            return records
        if is_directory_record(value):
            records.append({
                "kind": "directory",
                "source": prefix,
                "record": value,
            })
        for key, child in value.items():
            records.extend(iter_records(child, path_label(prefix, str(key))))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            records.extend(iter_records(child, path_label(prefix, index)))
    return records


def file_record_mismatches(record: dict[str, Any]) -> list[str]:
    path_value = record.get("path")
    path = Path(path_value) if isinstance(path_value, str) else None
    exists = bool(path and path.is_file())
    mismatches = []
    if record.get("exists") != exists:
        mismatches.append("exists")
    expected_size = path.stat().st_size if exists and path is not None else 0
    if record.get("size_bytes") != expected_size:
        mismatches.append("size_bytes")
    expected_sha = sha256_file(path) if exists and path is not None else None
    if record.get("sha256") != expected_sha:
        mismatches.append("sha256")
    return mismatches


def normalized_relative_paths(files: list[Path], root: Path) -> list[str]:
    return [child.relative_to(root).as_posix() for child in files]


def recorded_relative_paths(record: dict[str, Any]) -> tuple[list[str], bool]:
    files = record.get("files")
    if not isinstance(files, list):
        return [], bool(files)
    paths = []
    malformed = False
    for item in files:
        if not isinstance(item, dict):
            malformed = True
            continue
        relative_path = item.get("relative_path")
        if not isinstance(relative_path, str) or not relative_path:
            malformed = True
            continue
        paths.append(Path(relative_path).as_posix())
    return paths, malformed


def directory_record_mismatches(record: dict[str, Any]) -> list[str]:
    path_value = record.get("path")
    path = Path(path_value) if isinstance(path_value, str) else None
    exists = bool(path and path.is_dir())
    mismatches = []
    if record.get("exists") != exists:
        mismatches.append("exists")
    files = []
    size_bytes = 0
    if exists and path is not None:
        files = [child for child in sorted(path.rglob("*")) if child.is_file()]
        size_bytes = sum(child.stat().st_size for child in files)
    if record.get("file_count") != len(files):
        mismatches.append("file_count")
    if record.get("size_bytes") != size_bytes:
        mismatches.append("size_bytes")
    recorded_paths, malformed_paths = recorded_relative_paths(record)
    actual_paths = (
        normalized_relative_paths(files, path) if exists and path else []
    )
    if malformed_paths or recorded_paths != actual_paths:
        mismatches.append("files")
    return mismatches


def manifest_file_record_audit(
    manifest: dict[str, Any] | None,
    *,
    required: bool = True,
) -> dict[str, Any]:
    manifest_data = dict_or_empty(manifest)
    records = iter_records(manifest_data)
    file_records = [item for item in records if item["kind"] == "file"]
    directory_records = [
        item for item in records if item["kind"] == "directory"]
    mismatches = []
    for item in file_records:
        fields = file_record_mismatches(dict_or_empty(item["record"]))
        if fields:
            mismatches.append({
                "kind": "file",
                "source": item["source"],
                "path": item["record"].get("path"),
                "fields": fields,
            })
    for item in directory_records:
        fields = directory_record_mismatches(dict_or_empty(item["record"]))
        if fields:
            mismatches.append({
                "kind": "directory",
                "source": item["source"],
                "path": item["record"].get("path"),
                "fields": fields,
            })
    recorded = bool(records)
    passed = not mismatches and (recorded or not required)
    return {
        "required": required,
        "recorded": recorded,
        "file_record_count": len(file_records),
        "directory_record_count": len(directory_records),
        "mismatch_count": sum(len(item["fields"]) for item in mismatches),
        "mismatches": mismatches,
        "passed": passed,
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
        help="Exit nonzero when manifest file records are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        audit = manifest_file_record_audit(
            load_json(resolve_manifest(args.pack_or_manifest)),
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_MANIFEST_FILE_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_manifest_file_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
