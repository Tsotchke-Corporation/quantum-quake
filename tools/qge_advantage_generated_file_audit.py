#!/usr/bin/env python3
"""Audit generated advantage artifacts against advantage metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_advantage_benchmark  # noqa: E402


GENERATED_ADVANTAGE_ARTIFACTS = (
    "qae_curve",
    "qae_circuit",
    "scaling_summary",
    "scaling_summary_csv",
)
GENERATED_FILENAMES = {
    "qae_curve": "qae_curve.csv",
    "qae_circuit": "qae_circuit.txt",
    "scaling_summary": "scaling_summary.json",
    "scaling_summary_csv": "scaling_summary.csv",
}


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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def resolve_path(raw_path: str | Path | None,
                 *,
                 base_dir: Path | None = None) -> Path | None:
    if isinstance(raw_path, Path):
        path = raw_path
    elif isinstance(raw_path, str) and raw_path:
        path = Path(raw_path)
    else:
        return None
    if path.exists() or path.is_absolute() or base_dir is None:
        return path
    candidate = base_dir / path
    return candidate if candidate.exists() else path


def write_expected_generated_artifacts(
    metrics: dict[str, Any],
    artifact_paths: dict[str, Path],
) -> None:
    qge_advantage_benchmark.write_curve_csv(
        artifact_paths["qae_curve"], metrics)
    qge_advantage_benchmark.write_circuit_text(
        artifact_paths["qae_circuit"], metrics)
    qge_advantage_benchmark.write_json(
        artifact_paths["scaling_summary"], metrics["scaling_summary"])
    qge_advantage_benchmark.write_scaling_csv(
        artifact_paths["scaling_summary_csv"], metrics)


def expected_generated_artifact_bytes(
    metrics: dict[str, Any],
) -> dict[str, bytes]:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        paths = {
            name: tmpdir / filename
            for name, filename in GENERATED_FILENAMES.items()
        }
        write_expected_generated_artifacts(metrics, paths)
        return {
            name: path.read_bytes()
            for name, path in paths.items()
        }


def advantage_generated_file_audit(
    metrics: dict[str, Any] | None,
    artifact_paths: dict[str, str | Path | None] | None,
    *,
    base_dir: Path | None = None,
    required: bool = True,
) -> dict[str, Any]:
    metrics_data = dict_or_empty(metrics)
    paths = dict_or_empty(artifact_paths)
    active = (
        required or
        bool(metrics_data) or
        any(paths.get(name) for name in GENERATED_ADVANTAGE_ARTIFACTS)
    )
    if not active:
        return {
            "required": required,
            "metrics_recorded": False,
            "recorded": False,
            "expected_artifact_count": len(GENERATED_ADVANTAGE_ARTIFACTS),
            "recorded_artifact_count": 0,
            "missing_metrics": False,
            "missing_artifacts": [],
            "generation_errors": [],
            "content_mismatches": [],
            "mismatch_count": 0,
            "passed": True,
        }
    missing_metrics = not bool(metrics_data)
    generation_errors = []
    expected: dict[str, bytes] = {}
    if metrics_data:
        try:
            expected = expected_generated_artifact_bytes(metrics_data)
        except (KeyError, TypeError, ValueError) as exc:
            generation_errors.append({
                "artifact": "advantage_generated_files",
                "error": str(exc),
            })

    missing_artifacts = []
    content_mismatches = []
    recorded_count = 0
    for name in GENERATED_ADVANTAGE_ARTIFACTS:
        raw_path = paths.get(name)
        path = resolve_path(raw_path, base_dir=base_dir)
        if path is None or not path.is_file():
            missing_artifacts.append({
                "artifact": name,
                "path": str(raw_path) if raw_path is not None else None,
            })
            continue
        recorded_count += 1
        expected_bytes = expected.get(name)
        if expected_bytes is None:
            continue
        actual_bytes = path.read_bytes()
        fields = []
        if len(actual_bytes) != len(expected_bytes):
            fields.append("size_bytes")
        if sha256_bytes(actual_bytes) != sha256_bytes(expected_bytes):
            fields.append("sha256")
        if fields:
            content_mismatches.append({
                "artifact": name,
                "path": str(path),
                "fields": fields,
                "expected_size_bytes": len(expected_bytes),
                "actual_size_bytes": len(actual_bytes),
                "expected_sha256": sha256_bytes(expected_bytes),
                "actual_sha256": sha256_bytes(actual_bytes),
            })

    mismatch_count = (
        (1 if missing_metrics and required else 0) +
        len(generation_errors) +
        len(missing_artifacts) +
        len(content_mismatches)
    )
    return {
        "required": required,
        "metrics_recorded": bool(metrics_data),
        "recorded": recorded_count == len(GENERATED_ADVANTAGE_ARTIFACTS),
        "expected_artifact_count": len(GENERATED_ADVANTAGE_ARTIFACTS),
        "recorded_artifact_count": recorded_count,
        "missing_metrics": missing_metrics,
        "missing_artifacts": missing_artifacts,
        "generation_errors": generation_errors,
        "content_mismatches": content_mismatches,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (bool(metrics_data) or not required),
    }


def artifact_paths_from_manifest(manifest: dict[str, Any]) -> dict[str, str | None]:
    return {
        name: artifact_path(manifest, "advantage", name)
        for name in GENERATED_ADVANTAGE_ARTIFACTS
    }


def audit_from_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    base_dir = manifest_path.parent if manifest_path is not None else None
    metrics_path = resolve_path(
        artifact_path(manifest, "advantage", "metrics"),
        base_dir=base_dir,
    )
    metrics = load_json(metrics_path) if metrics_path and metrics_path.is_file() else {}
    return advantage_generated_file_audit(
        metrics,
        artifact_paths_from_manifest(manifest),
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
        help="Exit nonzero when generated advantage artifacts are stale.",
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
            print(f"QGE_ADVANTAGE_GENERATED_FILE_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_advantage_generated_file_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
