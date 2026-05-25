#!/usr/bin/env python3
"""Audit oracle claims evidence against the claims ledger and oracle scene."""

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
import qge_oracle_export  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402


CLAIMS_EVIDENCE_SCHEMA = "qge.claims_evidence.v0"
ORACLE_CLAIMS_FORBIDDEN_FLAGS = (
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


def expected_claims_evidence(
    oracle_scene: dict[str, Any],
    claims_ledger: dict[str, Any],
) -> dict[str, Any]:
    scene = dict_or_empty(oracle_scene)
    return qge_oracle_export.build_claims_evidence(
        scene,
        dict_or_empty(scene.get("trace_summary")),
        dict_or_empty(dict_or_empty(scene.get("snapshot")).get("render")),
        dict_or_empty(claims_ledger),
    )


def empty_audit(required: bool) -> dict[str, Any]:
    return {
        "required": required,
        "recorded": False,
        "schema_mismatch": False,
        "field_mismatches": [],
        "build_errors": [],
        "overclaim_flags": [],
        "mismatch_count": 0,
        "passed": not required,
    }


def oracle_claims_evidence_audit(
    oracle_scene: dict[str, Any] | None,
    claims_ledger: dict[str, Any] | None,
    claims_evidence: dict[str, Any] | None,
    *,
    required: bool = False,
) -> dict[str, Any]:
    recorded = dict_or_empty(claims_evidence)
    active = required or bool(recorded)
    if not active:
        return empty_audit(required)

    build_errors: list[dict[str, str]] = []
    try:
        expected = expected_claims_evidence(
            dict_or_empty(oracle_scene),
            dict_or_empty(claims_ledger),
        )
    except (KeyError, TypeError, ValueError) as exc:
        build_errors.append({
            "artifact": "claims_evidence",
            "error": str(exc),
        })
        expected = {}

    field_mismatches = qge_resource_boundary_audit.mismatch_paths(
        expected,
        recorded,
    ) if recorded else ["<missing>"]
    schema_mismatch = bool(
        recorded and recorded.get("schema") != CLAIMS_EVIDENCE_SCHEMA)
    if schema_mismatch and "schema" not in field_mismatches:
        field_mismatches.append("schema")
    overclaim_flags = (
        qge_moonlab_overclaim_audit.recursive_overclaim_flags(
            "claims_evidence",
            recorded,
            forbidden=ORACLE_CLAIMS_FORBIDDEN_FLAGS,
        )
        if recorded else []
    )
    mismatch_count = (
        len(field_mismatches) +
        len(build_errors) +
        len(overclaim_flags)
    )
    passed = mismatch_count == 0 and (bool(recorded) or not required)
    return {
        "required": required,
        "recorded": bool(recorded),
        "schema_mismatch": schema_mismatch,
        "field_mismatches": field_mismatches,
        "build_errors": build_errors,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": passed,
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
    packed: bool = False,
) -> str | None:
    entry = artifact_entry(manifest, section, name)
    if packed:
        path = dict_or_empty(entry.get("packed")).get("path")
    else:
        path = entry.get("path")
        if not path:
            path = dict_or_empty(entry.get("packed")).get("path")
    return path if isinstance(path, str) and path else None


def load_artifact(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    packed: bool = False,
) -> dict[str, Any]:
    path = artifact_path(manifest, section, name, packed=packed)
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    return load_json(file_path)


def oracle_claims_evidence_audit_from_manifest(
    manifest: dict[str, Any],
    *,
    required: bool = True,
) -> dict[str, Any]:
    return oracle_claims_evidence_audit(
        load_artifact(manifest, "oracle", "oracle_scene"),
        load_artifact(manifest, "source_docs", "claims_ledger", packed=True),
        load_artifact(manifest, "oracle", "claims_evidence"),
        required=required,
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
        help="Exit nonzero when claims evidence is stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        audit = oracle_claims_evidence_audit_from_manifest(
            load_json(resolve_manifest(args.pack_or_manifest)),
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_ORACLE_CLAIMS_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_oracle_claims_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
