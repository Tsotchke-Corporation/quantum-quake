#!/usr/bin/env python3
"""Audit packed vanilla capture matrix claims against source capture files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_moonlab_overclaim_audit  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402
import qge_vanilla_capture_matrix  # noqa: E402


VANILLA_MATRIX_FORBIDDEN_CLAIMS = (
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


def first_mode(
    matrix: dict[str, Any],
    *,
    metrics_key: str,
    fallback: str,
) -> dict[str, Any]:
    for mode in matrix.get("modes") or []:
        if isinstance(mode, dict) and mode.get("metrics_key") == metrics_key:
            return mode
    for mode in matrix.get("modes") or []:
        if isinstance(mode, dict) and mode.get("mode") == fallback:
            return mode
    return {}


def expected_vanilla_matrix(
    recorded_matrix: dict[str, Any],
) -> dict[str, Any]:
    recorded = dict_or_empty(recorded_matrix)
    capture_dir = recorded.get("capture_dir")
    if not isinstance(capture_dir, str) or not capture_dir:
        raise ValueError("recorded vanilla matrix is missing capture_dir")
    classic = first_mode(recorded, metrics_key="reference", fallback="classic")
    qge = first_mode(recorded, metrics_key="candidate", fallback="quantum")
    args = SimpleNamespace(
        capture_dir=Path(capture_dir),
        metrics=None,
        classic_mode=classic.get("mode") or "classic",
        qge_mode=qge.get("mode") or "quantum",
        classic_render=int(classic.get("quantum_render") or 0),
        qge_render=int(qge.get("quantum_render") or 2),
    )
    return qge_vanilla_capture_matrix.build_matrix(args)


def project_expected_to_recorded_shape(expected: Any, recorded: Any) -> Any:
    if isinstance(recorded, dict):
        expected_dict = expected if isinstance(expected, dict) else {}
        return {
            key: project_expected_to_recorded_shape(
                expected_dict.get(key),
                value,
            )
            for key, value in recorded.items()
        }
    if isinstance(recorded, list):
        expected_list = expected if isinstance(expected, list) else []
        return [
            project_expected_to_recorded_shape(
                expected_list[index] if index < len(expected_list) else None,
                value,
            )
            for index, value in enumerate(recorded)
        ]
    return expected


def additive_expected_fields(
    expected: Any,
    recorded: Any,
    *,
    prefix: str = "",
) -> list[str]:
    fields: list[str] = []
    if isinstance(expected, dict) and isinstance(recorded, dict):
        for key, value in expected.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in recorded:
                fields.append(path)
                continue
            fields.extend(additive_expected_fields(
                value,
                recorded.get(key),
                prefix=path,
            ))
    elif isinstance(expected, list) and isinstance(recorded, list):
        for index, value in enumerate(expected):
            if index >= len(recorded):
                fields.append(f"{prefix}[{index}]")
                continue
            fields.extend(additive_expected_fields(
                value,
                recorded[index],
                prefix=f"{prefix}[{index}]",
            ))
    return fields


def vanilla_matrix_audit(
    recorded_matrix: dict[str, Any] | None,
    *,
    required: bool = True,
) -> dict[str, Any]:
    recorded = dict_or_empty(recorded_matrix)
    active = required or bool(recorded)
    if not active:
        return {
            "required": required,
            "recorded": False,
            "capture_dir": None,
            "additive_expected_fields": [],
            "additive_expected_field_count": 0,
            "field_mismatches": [],
            "overclaim_flags": [],
            "build_errors": [],
            "mismatch_count": 0,
            "passed": True,
        }

    build_errors = []
    try:
        expected = expected_vanilla_matrix(recorded)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        build_errors.append(str(exc))
        expected = {}

    projected_expected = project_expected_to_recorded_shape(expected, recorded)
    field_mismatches = (
        qge_resource_boundary_audit.mismatch_paths(
            projected_expected,
            recorded,
        )
        if recorded and not build_errors else []
    )
    overclaim_flags = (
        qge_moonlab_overclaim_audit.recursive_overclaim_flags(
            "vanilla_capture_matrix",
            recorded,
            forbidden=VANILLA_MATRIX_FORBIDDEN_CLAIMS,
        )
        if recorded else []
    )
    additive_fields = (
        additive_expected_fields(expected, recorded)
        if recorded and not build_errors else []
    )
    mismatch_count = (
        len(field_mismatches) + len(overclaim_flags) + len(build_errors)
    )
    return {
        "required": required,
        "recorded": bool(recorded),
        "capture_dir": recorded.get("capture_dir"),
        "additive_expected_fields": additive_fields,
        "additive_expected_field_count": len(additive_fields),
        "field_mismatches": field_mismatches,
        "overclaim_flags": overclaim_flags,
        "build_errors": build_errors,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (bool(recorded) or not required),
    }


def artifact_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> str | None:
    artifact = (
        dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(section))
        .get(name)
    )
    path = dict_or_empty(dict_or_empty(artifact).get("packed")).get("path")
    return path if isinstance(path, str) and path else None


def resolve_path(
    raw_path: str | None,
    *,
    base_dir: Path | None = None,
) -> Path | None:
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
    matrix_path = resolve_path(
        artifact_path(manifest, "vanilla", "matrix"),
        base_dir=base_dir,
    )
    recorded = (
        load_json(matrix_path)
        if matrix_path is not None and matrix_path.is_file() else {}
    )
    audit = vanilla_matrix_audit(recorded, required=True)
    audit["vanilla_matrix_file"] = (
        str(matrix_path) if matrix_path is not None else None)
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
        help="Exit nonzero when the packed vanilla matrix is stale.",
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
            print(f"QGE_VANILLA_MATRIX_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_vanilla_matrix_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
