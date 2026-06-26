#!/usr/bin/env python3
"""Audit packed Moonlab deployment gate artifacts against the manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_moonlab_deployment_gate  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402
import qge_moonlab_overclaim_audit  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402


GATE_SCHEMA = "qge.moonlab_deployment_gate.v0"
ICC_EVIDENCE_SCHEMA = "qge.icc_evidence.v0"
IGNORED_GATE_FIELDS = ("created_utc", "source_path")
IGNORED_GATE_ICC_FIELDS = ("moonlab_deployment_gate_file",)
DEPLOYMENT_GATE_FORBIDDEN_CLAIMS = (
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


def artifact_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    base_dir: Path | None = None,
) -> Path | None:
    entry = dict_or_empty(
        dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(section))
        .get(name)
    )
    raw_path = entry.get("path")
    if not raw_path:
        raw_path = dict_or_empty(entry.get("packed")).get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    return qge_moonlab_full_game_plan.resolve_path(raw_path, base_dir=base_dir)


def load_artifact_json(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    path = artifact_path(manifest, section, name, base_dir=base_dir)
    if path is None or not path.is_file():
        return {}
    return load_json(path)


def filter_ignored_fields(fields: list[str]) -> list[str]:
    ignored = set(IGNORED_GATE_FIELDS)
    return [field for field in fields if field not in ignored]


def filter_ignored_icc_fields(fields: list[str]) -> list[str]:
    ignored = set(IGNORED_GATE_ICC_FIELDS)
    return [field for field in fields if field not in ignored]


def empty_audit(required: bool) -> dict[str, Any]:
    return {
        "required": required,
        "recorded": False,
        "gate_recorded": False,
        "gate_icc_recorded": False,
        "missing_artifacts": [],
        "gate_schema_mismatch": False,
        "gate_icc_schema_mismatch": False,
        "gate_mismatches": [],
        "gate_icc_mismatches": [],
        "build_errors": [],
        "overclaim_flags": [],
        "mismatch_count": 0,
        "passed": not required,
    }


def deployment_gate_artifact_audit(
    manifest: dict[str, Any] | None,
    *,
    manifest_path: Path,
    required: bool = True,
) -> dict[str, Any]:
    manifest_data = dict_or_empty(manifest)
    base_dir = manifest_path.parent
    gate_path = artifact_path(
        manifest_data,
        "resource",
        "moonlab_deployment_gate",
        base_dir=base_dir,
    )
    gate_icc_path = artifact_path(
        manifest_data,
        "resource",
        "moonlab_deployment_gate_icc_evidence",
        base_dir=base_dir,
    )
    gate_recorded = gate_path is not None and gate_path.is_file()
    gate_icc_recorded = gate_icc_path is not None and gate_icc_path.is_file()
    active = required or gate_recorded or gate_icc_recorded
    if not active:
        return empty_audit(required)

    missing_artifacts = []
    if not gate_recorded:
        missing_artifacts.append({
            "artifact": "resource.moonlab_deployment_gate",
            "path": str(gate_path) if gate_path is not None else None,
        })
    if not gate_icc_recorded:
        missing_artifacts.append({
            "artifact": "resource.moonlab_deployment_gate_icc_evidence",
            "path": str(gate_icc_path) if gate_icc_path is not None else None,
        })

    recorded_gate = load_json(gate_path) if gate_recorded else {}
    recorded_icc = load_json(gate_icc_path) if gate_icc_recorded else {}
    build_errors: list[dict[str, str]] = []
    try:
        expected_gate = qge_moonlab_deployment_gate.build_gate_from_manifest(
            manifest_data,
            manifest_path=manifest_path,
        )
        expected_icc = qge_moonlab_deployment_gate.build_icc_evidence(
            expected_gate,
            out_path=gate_path or Path("resource/qge_moonlab_deployment_gate.json"),
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        build_errors.append({
            "artifact": "resource.moonlab_deployment_gate",
            "error": str(exc),
        })
        expected_gate = {}
        expected_icc = {}

    gate_mismatches = filter_ignored_fields(
        qge_resource_boundary_audit.mismatch_paths(
            expected_gate,
            recorded_gate,
        )
    ) if recorded_gate else []
    gate_icc_mismatches = filter_ignored_icc_fields(
        qge_resource_boundary_audit.mismatch_paths(
            expected_icc,
            recorded_icc,
        )
    ) if recorded_icc else []
    overclaim_flags = (
        qge_moonlab_overclaim_audit.recursive_overclaim_flags(
            "moonlab_deployment_gate",
            recorded_gate,
            forbidden=DEPLOYMENT_GATE_FORBIDDEN_CLAIMS,
        ) +
        qge_moonlab_overclaim_audit.recursive_overclaim_flags(
            "moonlab_deployment_gate_icc_evidence",
            recorded_icc,
            forbidden=DEPLOYMENT_GATE_FORBIDDEN_CLAIMS,
        )
    )
    mismatch_count = (
        len(missing_artifacts) +
        len(gate_mismatches) +
        len(gate_icc_mismatches) +
        len(build_errors) +
        len(overclaim_flags)
    )
    recorded = gate_recorded and gate_icc_recorded
    return {
        "required": required,
        "recorded": recorded,
        "gate_recorded": gate_recorded,
        "gate_icc_recorded": gate_icc_recorded,
        "missing_artifacts": missing_artifacts,
        "gate_schema_mismatch": (
            bool(recorded_gate) and recorded_gate.get("schema") != GATE_SCHEMA),
        "gate_icc_schema_mismatch": (
            bool(recorded_icc) and
            recorded_icc.get("schema") != ICC_EVIDENCE_SCHEMA),
        "gate_mismatches": gate_mismatches,
        "gate_icc_mismatches": gate_icc_mismatches,
        "ignored_gate_fields": list(IGNORED_GATE_FIELDS),
        "ignored_gate_icc_fields": list(IGNORED_GATE_ICC_FIELDS),
        "build_errors": build_errors,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (recorded or not required),
    }


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
        help="Exit nonzero when deployment gate artifacts are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        manifest_path = qge_moonlab_full_game_plan.resolve_publication_manifest(
            args.pack_or_manifest)
        audit = deployment_gate_artifact_audit(
            load_json(manifest_path),
            manifest_path=manifest_path,
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_MOONLAB_DEPLOYMENT_GATE_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_moonlab_deployment_gate_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
