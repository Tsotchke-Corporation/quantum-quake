#!/usr/bin/env python3
"""Audit publication artifact copies against their recorded source paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


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


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def is_artifact_source_copy_prefix(prefix: str) -> bool:
    return prefix == "artifacts" or prefix.startswith("artifacts.")


def iter_source_copy_records(
    value: Any,
    prefix: str = "",
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        packed = dict_or_empty(value.get("packed"))
        if isinstance(value.get("source_path"), str):
            if is_file_record(packed):
                records.append({
                    "kind": "file",
                    "source": prefix,
                    "source_path": value.get("source_path"),
                    "packed": packed,
                })
            elif is_directory_record(packed):
                records.append({
                    "kind": "directory",
                    "source": prefix,
                    "source_path": value.get("source_path"),
                    "packed": packed,
                })
            elif is_artifact_source_copy_prefix(prefix):
                records.append({
                    "kind": "malformed",
                    "source": prefix,
                    "source_path": value.get("source_path"),
                    "packed": packed,
                })
        for key, child in value.items():
            records.extend(iter_source_copy_records(
                child,
                path_label(prefix, str(key)),
            ))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            records.extend(iter_source_copy_records(
                child,
                path_label(prefix, index),
            ))
    return records


def path_from_record(value: Any) -> Path | None:
    return Path(value) if isinstance(value, str) and value else None


def is_relative_to_path(path: Path, root: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(root.expanduser().resolve())
        return True
    except (OSError, ValueError):
        return False


def packed_membership_mismatch(
    record: dict[str, Any],
    pack_root: Path | None,
) -> dict[str, Any] | None:
    if pack_root is None:
        return None
    packed_record = dict_or_empty(record.get("packed"))
    packed_path = path_from_record(packed_record.get("path"))
    if packed_path is None:
        return None
    if is_relative_to_path(packed_path, pack_root):
        return None
    return {
        "source": record.get("source"),
        "source_path": record.get("source_path"),
        "packed_path": str(packed_path),
        "pack_dir": str(pack_root),
        "fields": ["packed_path_membership"],
    }


def file_copy_mismatch(record: dict[str, Any]) -> dict[str, Any] | None:
    packed_record = dict_or_empty(record.get("packed"))
    source_path = path_from_record(record.get("source_path"))
    packed_path = path_from_record(packed_record.get("path"))
    missing = []
    if source_path is None or not source_path.is_file():
        missing.append("source_path")
    if packed_path is None or not packed_path.is_file():
        missing.append("packed_path")
    if missing:
        return {
            "source": record.get("source"),
            "source_path": str(source_path) if source_path else None,
            "packed_path": str(packed_path) if packed_path else None,
            "fields": missing,
        }

    assert source_path is not None
    assert packed_path is not None
    fields = []
    source_size = source_path.stat().st_size
    packed_size = packed_path.stat().st_size
    if source_size != packed_size:
        fields.append("size_bytes")
    source_sha = sha256_file(source_path)
    packed_sha = sha256_file(packed_path)
    if source_sha != packed_sha:
        fields.append("sha256")
    if not fields:
        return None
    return {
        "source": record.get("source"),
        "source_path": str(source_path),
        "packed_path": str(packed_path),
        "fields": fields,
        "source_size_bytes": source_size,
        "packed_size_bytes": packed_size,
        "source_sha256": source_sha,
        "packed_sha256": packed_sha,
    }


def directory_file_index(path: Path) -> dict[str, dict[str, Any]]:
    files = [child for child in sorted(path.rglob("*")) if child.is_file()]
    return {
        str(child.relative_to(path)): {
            "path": child,
            "size_bytes": child.stat().st_size,
            "sha256": sha256_file(child),
        }
        for child in files
    }


def directory_copy_mismatch(record: dict[str, Any]) -> dict[str, Any] | None:
    packed_record = dict_or_empty(record.get("packed"))
    source_path = path_from_record(record.get("source_path"))
    packed_path = path_from_record(packed_record.get("path"))
    missing = []
    if source_path is None or not source_path.is_dir():
        missing.append("source_path")
    if packed_path is None or not packed_path.is_dir():
        missing.append("packed_path")
    if missing:
        return {
            "source": record.get("source"),
            "source_path": str(source_path) if source_path else None,
            "packed_path": str(packed_path) if packed_path else None,
            "fields": missing,
            "content_mismatches": [],
        }

    assert source_path is not None
    assert packed_path is not None
    source_files = directory_file_index(source_path)
    packed_files = directory_file_index(packed_path)
    source_names = set(source_files)
    packed_names = set(packed_files)
    missing_files = sorted(source_names - packed_names)
    extra_files = sorted(packed_names - source_names)
    content_mismatches = []
    for relative_path in sorted(source_names & packed_names):
        source_file = source_files[relative_path]
        packed_file = packed_files[relative_path]
        fields = []
        if source_file.get("size_bytes") != packed_file.get("size_bytes"):
            fields.append("size_bytes")
        if source_file.get("sha256") != packed_file.get("sha256"):
            fields.append("sha256")
        if fields:
            content_mismatches.append({
                "relative_path": relative_path,
                "fields": fields,
                "source_size_bytes": source_file.get("size_bytes"),
                "packed_size_bytes": packed_file.get("size_bytes"),
                "source_sha256": source_file.get("sha256"),
                "packed_sha256": packed_file.get("sha256"),
            })

    fields = []
    if missing_files:
        fields.append("missing_files")
    if extra_files:
        fields.append("extra_files")
    if content_mismatches:
        fields.append("sha256")
    if not fields:
        return None
    return {
        "source": record.get("source"),
        "source_path": str(source_path),
        "packed_path": str(packed_path),
        "fields": fields,
        "missing_files": missing_files,
        "extra_files": extra_files,
        "content_mismatches": content_mismatches,
    }


def manifest_source_copy_audit(
    manifest: dict[str, Any] | None,
    *,
    required: bool = True,
) -> dict[str, Any]:
    manifest_data = dict_or_empty(manifest)
    records = iter_source_copy_records(manifest_data)
    if not records and not required:
        return {
            "required": required,
            "recorded": False,
            "source_copy_record_count": 0,
            "file_copy_record_count": 0,
            "directory_copy_record_count": 0,
            "missing_pack_dir": False,
            "malformed_source_copy_record_count": 0,
            "malformed_source_copy_records": [],
            "packed_path_membership_mismatches": [],
            "missing_source_paths": [],
            "missing_packed_paths": [],
            "file_mismatches": [],
            "directory_mismatches": [],
            "mismatch_count": 0,
            "passed": True,
        }

    missing_source_paths = []
    missing_packed_paths = []
    malformed_source_copy_records = []
    packed_path_membership_mismatches = []
    file_mismatches = []
    directory_mismatches = []
    pack_root = path_from_record(manifest_data.get("pack_dir"))
    missing_pack_dir = required and bool(records) and pack_root is None
    for record in records:
        if record.get("kind") == "malformed":
            malformed_source_copy_records.append({
                "source": record.get("source"),
                "source_path": record.get("source_path"),
                "fields": ["packed"],
            })
            continue
        membership_mismatch = packed_membership_mismatch(record, pack_root)
        if membership_mismatch:
            packed_path_membership_mismatches.append(membership_mismatch)
        mismatch = (
            file_copy_mismatch(record)
            if record.get("kind") == "file"
            else directory_copy_mismatch(record)
        )
        if not mismatch:
            continue
        fields = set(mismatch.get("fields", []))
        if "source_path" in fields:
            missing_source_paths.append(mismatch)
        elif "packed_path" in fields:
            missing_packed_paths.append(mismatch)
        elif record.get("kind") == "file":
            file_mismatches.append(mismatch)
        else:
            directory_mismatches.append(mismatch)

    mismatch_count = (
        int(missing_pack_dir) +
        len(malformed_source_copy_records) +
        len(packed_path_membership_mismatches) +
        len(missing_source_paths) +
        len(missing_packed_paths) +
        len(file_mismatches) +
        len(directory_mismatches)
    )
    valid_records = [
        record for record in records
        if record.get("kind") in {"file", "directory"}
    ]
    return {
        "required": required,
        "recorded": bool(valid_records),
        "source_copy_record_count": len(valid_records),
        "file_copy_record_count": sum(
            1 for record in valid_records if record.get("kind") == "file"),
        "directory_copy_record_count": sum(
            1 for record in valid_records
            if record.get("kind") == "directory"),
        "missing_pack_dir": missing_pack_dir,
        "malformed_source_copy_record_count": len(
            malformed_source_copy_records),
        "malformed_source_copy_records": malformed_source_copy_records,
        "packed_path_membership_mismatches": (
            packed_path_membership_mismatches),
        "missing_source_paths": missing_source_paths,
        "missing_packed_paths": missing_packed_paths,
        "file_mismatches": file_mismatches,
        "directory_mismatches": directory_mismatches,
        "mismatch_count": mismatch_count,
        "passed": (
            mismatch_count == 0 and (bool(valid_records) or not required)),
    }


def manifest_source_copy_icc_summary(
    manifest: dict[str, Any],
    manifest_path: Path,
) -> dict[str, Any]:
    if not manifest_path.exists():
        return {
            "manifest_source_copy_audit_available": False,
            "manifest_source_copy_audit_passed": None,
            "manifest_source_copy_recorded": None,
            "manifest_source_copy_record_count": 0,
            "manifest_source_copy_file_record_count": 0,
            "manifest_source_copy_directory_record_count": 0,
            "manifest_source_copy_missing_pack_dir": None,
            "manifest_source_copy_malformed_record_count": 0,
            "manifest_source_copy_packed_path_membership_mismatch_count": 0,
            "manifest_source_copy_missing_source_path_count": 0,
            "manifest_source_copy_missing_packed_path_count": 0,
            "manifest_source_copy_file_mismatch_count": 0,
            "manifest_source_copy_directory_mismatch_count": 0,
            "manifest_source_copy_mismatch_count": 0,
        }

    audit = manifest_source_copy_audit(manifest, required=True)
    return {
        "manifest_source_copy_audit_available": True,
        "manifest_source_copy_audit_passed": audit.get("passed"),
        "manifest_source_copy_recorded": audit.get("recorded"),
        "manifest_source_copy_record_count": audit.get(
            "source_copy_record_count"),
        "manifest_source_copy_file_record_count": audit.get(
            "file_copy_record_count"),
        "manifest_source_copy_directory_record_count": audit.get(
            "directory_copy_record_count"),
        "manifest_source_copy_missing_pack_dir": audit.get(
            "missing_pack_dir"),
        "manifest_source_copy_malformed_record_count": audit.get(
            "malformed_source_copy_record_count"),
        "manifest_source_copy_packed_path_membership_mismatch_count": len(
            audit.get("packed_path_membership_mismatches", [])),
        "manifest_source_copy_missing_source_path_count": len(
            audit.get("missing_source_paths", [])),
        "manifest_source_copy_missing_packed_path_count": len(
            audit.get("missing_packed_paths", [])),
        "manifest_source_copy_file_mismatch_count": len(
            audit.get("file_mismatches", [])),
        "manifest_source_copy_directory_mismatch_count": len(
            audit.get("directory_mismatches", [])),
        "manifest_source_copy_mismatch_count": audit.get("mismatch_count"),
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
        help="Exit nonzero when packed artifact copies differ from sources.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        audit = manifest_source_copy_audit(
            load_json(resolve_manifest(args.pack_or_manifest)),
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_MANIFEST_SOURCE_COPY_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_manifest_source_copy_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
