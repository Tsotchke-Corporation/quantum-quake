#!/usr/bin/env python3
"""Audit packed breadth evidence against its source matrix ledgers."""

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

import qge_breadth_evidence  # noqa: E402
import qge_map_sets  # noqa: E402
import qge_moonlab_overclaim_audit  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402


BREADTH_EVIDENCE_FORBIDDEN_CLAIMS = (
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


def normalized_breadth_evidence(value: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(json.dumps(dict_or_empty(value)))
    data.pop("created_utc", None)
    return data


def matrix_source_paths(breadth_evidence: dict[str, Any]) -> list[Path]:
    paths = []
    for run in breadth_evidence.get("matrix_runs") or []:
        if not isinstance(run, dict):
            continue
        raw_path = run.get("source_path") or run.get("matrix_file")
        if isinstance(raw_path, str) and raw_path:
            paths.append(Path(raw_path))
    return paths


def recorded_map_set(recorded_breadth_evidence: dict[str, Any]) -> str:
    recorded = dict_or_empty(recorded_breadth_evidence)
    aggregate = dict_or_empty(recorded.get("aggregate"))
    coverage = (
        dict_or_empty(recorded.get("full_game_coverage"))
        or dict_or_empty(aggregate.get("full_game_coverage"))
    )
    map_set = (
        recorded.get("full_game_map_set")
        or aggregate.get("full_game_map_set")
        or coverage.get("map_set")
    )
    return (
        map_set if isinstance(map_set, str) and map_set
        else qge_map_sets.DEFAULT_FULL_GAME_MAP_SET
    )


def expected_breadth_evidence(
    recorded_breadth_evidence: dict[str, Any],
) -> dict[str, Any]:
    recorded = dict_or_empty(recorded_breadth_evidence)
    args = SimpleNamespace(
        inputs=[],
        matrix=matrix_source_paths(recorded),
        publication_pack=[],
        min_runs=int(recorded.get("min_matrix_runs") or 1),
        min_maps=int(recorded.get("min_maps") or 1),
        map_set=recorded_map_set(recorded),
    )
    return qge_breadth_evidence.build_manifest(args)


def breadth_evidence_audit(
    recorded_breadth_evidence: dict[str, Any] | None,
    *,
    required: bool = True,
) -> dict[str, Any]:
    recorded = dict_or_empty(recorded_breadth_evidence)
    active = required or bool(recorded)
    if not active:
        return {
            "required": required,
            "recorded": False,
            "matrix_source_count": 0,
            "ignored_fields": ["created_utc"],
            "field_mismatches": [],
            "overclaim_flags": [],
            "build_errors": [],
            "mismatch_count": 0,
            "passed": True,
        }

    build_errors = []
    try:
        expected = expected_breadth_evidence(recorded)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        build_errors.append(str(exc))
        expected = {}

    field_mismatches = (
        qge_resource_boundary_audit.mismatch_paths(
            normalized_breadth_evidence(expected),
            normalized_breadth_evidence(recorded),
        )
        if recorded and not build_errors else []
    )
    overclaim_flags = (
        qge_moonlab_overclaim_audit.recursive_overclaim_flags(
            "breadth_evidence",
            recorded,
            forbidden=BREADTH_EVIDENCE_FORBIDDEN_CLAIMS,
        )
        if recorded else []
    )
    mismatch_count = (
        len(field_mismatches) + len(overclaim_flags) + len(build_errors)
    )
    return {
        "required": required,
        "recorded": bool(recorded),
        "matrix_source_count": len(matrix_source_paths(recorded)),
        "ignored_fields": ["created_utc"],
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
    breadth_path = resolve_path(
        artifact_path(manifest, "breadth", "evidence"),
        base_dir=base_dir,
    )
    recorded = (
        load_json(breadth_path)
        if breadth_path is not None and breadth_path.is_file() else {}
    )
    audit = breadth_evidence_audit(recorded, required=True)
    audit["breadth_evidence_file"] = (
        str(breadth_path) if breadth_path is not None else None)
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
        help="Exit nonzero when packed breadth evidence is stale.",
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
            print(f"QGE_BREADTH_EVIDENCE_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_breadth_evidence_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
