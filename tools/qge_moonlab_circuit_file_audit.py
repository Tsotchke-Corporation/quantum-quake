#!/usr/bin/env python3
"""Audit Moonlab circuit files against packed advantage JSON records."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable


ADVANTAGE_CIRCUIT_SOURCES = (
    "qae_moonlab_payload",
    "qae_moonlab_oracle_kernel",
    "qae_moonlab_observation_zero",
    "qae_moonlab_grover_schedule_plan",
)
MOONLAB_CIRCUIT_HEADER = "# moonlab-circuit v1"


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def circuit_record(
    source_artifact: str,
    record_path: str,
    record: dict[str, Any],
    *,
    path_field: str = "moonlab_circuit_file",
    sha_field: str = "moonlab_circuit_sha256",
    size_field: str = "body_bytes",
) -> dict[str, Any]:
    return {
        "source_artifact": source_artifact,
        "record_path": record_path,
        "path": record.get(path_field),
        "expected_sha256": record.get(sha_field),
        "expected_size_bytes": int_or_none(record.get(size_field)),
    }


def expected_circuit_records(
    advantage_artifacts: dict[str, Any],
) -> list[dict[str, Any]]:
    payload = dict_or_empty(advantage_artifacts.get("qae_moonlab_payload"))
    records = [
        circuit_record(
            "qae_moonlab_payload",
            f"observation_circuits[{index}]",
            dict_or_empty(item),
            size_field="moonlab_payload_bytes",
        )
        for index, item in enumerate(
            list_or_empty(payload.get("observation_circuits")))
    ]

    kernel = dict_or_empty(
        advantage_artifacts.get("qae_moonlab_oracle_kernel"))
    if kernel:
        records.append(circuit_record(
            "qae_moonlab_oracle_kernel",
            "moonlab_circuit_file",
            {
                **kernel,
                "body_bytes": dict_or_empty(
                    kernel.get("moonlab_control_plane")).get("body_bytes"),
            },
        ))

    observation = dict_or_empty(
        advantage_artifacts.get("qae_moonlab_observation_zero"))
    if observation:
        records.append(circuit_record(
            "qae_moonlab_observation_zero",
            "moonlab_circuit_file",
            {
                **observation,
                "body_bytes": dict_or_empty(
                    observation.get("moonlab_control_plane")).get(
                        "body_bytes"),
            },
        ))

    grover_plan = dict_or_empty(
        advantage_artifacts.get("qae_moonlab_grover_schedule_plan"))
    records.extend(
        circuit_record(
            "qae_moonlab_grover_schedule_plan",
            f"observations[{index}]",
            dict_or_empty(item),
        )
        for index, item in enumerate(
            list_or_empty(grover_plan.get("observations")))
    )
    return records


def first_line(path: Path) -> str | None:
    with path.open("r", encoding="utf-8") as f:
        return f.readline().rstrip("\n")


def moonlab_circuit_file_audit(
    advantage_artifacts: dict[str, Any] | None,
    *,
    base_dir: Path | None = None,
    required: bool = True,
    required_sources: Iterable[str] = ADVANTAGE_CIRCUIT_SOURCES,
) -> dict[str, Any]:
    artifacts = dict_or_empty(advantage_artifacts)
    missing_sources = [
        name for name in required_sources
        if not dict_or_empty(artifacts.get(name))
    ]
    malformed_records = []
    missing_circuit_files = []
    circuit_mismatches = []
    header_mismatches = []
    records = expected_circuit_records(artifacts)

    for record in records:
        source = record.get("source_artifact")
        record_path = record.get("record_path")
        raw_path = record.get("path")
        expected_sha = record.get("expected_sha256")
        expected_size = record.get("expected_size_bytes")
        if not isinstance(raw_path, str) or not raw_path:
            malformed_records.append({
                "source_artifact": source,
                "record_path": record_path,
                "field": "moonlab_circuit_file",
            })
            continue
        if not isinstance(expected_sha, str) or not expected_sha:
            malformed_records.append({
                "source_artifact": source,
                "record_path": record_path,
                "field": "moonlab_circuit_sha256",
            })
            continue
        if expected_size is None:
            malformed_records.append({
                "source_artifact": source,
                "record_path": record_path,
                "field": "body_bytes",
            })
            continue

        path = resolve_path(raw_path, base_dir=base_dir)
        if path is None or not path.is_file():
            missing_circuit_files.append({
                "source_artifact": source,
                "record_path": record_path,
                "path": raw_path,
            })
            continue
        actual_size = path.stat().st_size
        actual_sha = sha256_file(path)
        mismatched_fields = []
        if actual_size != expected_size:
            mismatched_fields.append("size_bytes")
        if actual_sha != expected_sha:
            mismatched_fields.append("sha256")
        if mismatched_fields:
            circuit_mismatches.append({
                "source_artifact": source,
                "record_path": record_path,
                "path": str(path),
                "fields": mismatched_fields,
                "expected_size_bytes": expected_size,
                "actual_size_bytes": actual_size,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
            })
        header = first_line(path)
        if header != MOONLAB_CIRCUIT_HEADER:
            header_mismatches.append({
                "source_artifact": source,
                "record_path": record_path,
                "path": str(path),
                "expected_header": MOONLAB_CIRCUIT_HEADER,
                "actual_header": header,
            })

    mismatch_count = (
        len(missing_sources) +
        len(malformed_records) +
        len(missing_circuit_files) +
        len(circuit_mismatches) +
        len(header_mismatches)
    )
    expected_count = len(records)
    recorded_count = expected_count - len(missing_circuit_files)
    return {
        "required": required,
        "recorded": expected_count > 0 and recorded_count == expected_count,
        "required_sources": list(required_sources),
        "missing_sources": missing_sources,
        "expected_circuit_count": expected_count,
        "recorded_circuit_count": recorded_count,
        "malformed_records": malformed_records,
        "missing_circuit_files": missing_circuit_files,
        "circuit_mismatches": circuit_mismatches,
        "header_mismatches": header_mismatches,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (
            expected_count > 0 or not required),
    }


def load_advantage_artifacts(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    base_dir = manifest_path.parent if manifest_path is not None else None
    artifacts = {}
    for name in ADVANTAGE_CIRCUIT_SOURCES:
        path = resolve_path(
            artifact_path(manifest, "advantage", name),
            base_dir=base_dir,
        )
        artifacts[name] = load_json(path) if path and path.is_file() else {}
    return artifacts


def audit_from_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    base_dir = manifest_path.parent if manifest_path is not None else None
    return moonlab_circuit_file_audit(
        load_advantage_artifacts(manifest, manifest_path=manifest_path),
        base_dir=base_dir,
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
        help="Exit nonzero when Moonlab circuit files are stale.",
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
            print(f"QGE_MOONLAB_CIRCUIT_FILE_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_moonlab_circuit_file_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
