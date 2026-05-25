#!/usr/bin/env python3
"""Audit oracle ICC evidence against oracle and claims artifacts."""

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


ICC_EVIDENCE_SCHEMA = "qge.icc_evidence.v0"
ORACLE_SIDECAR_FORBIDDEN_CLAIMS = (
    "whole_game_moonlab_deployment_claimed",
    "whole_game_hardware_execution_claimed",
    "hardware_quantum_advantage_claimed",
    "dense_70000_qubit_state_claimed",
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def path_or_empty(value: str | None) -> Path:
    if not isinstance(value, str) or not value:
        return Path("")
    return Path(value)


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


def expected_oracle_icc_evidence(
    oracle_scene: dict[str, Any],
    claims_evidence: dict[str, Any],
    *,
    artifact_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    paths = dict_or_empty(artifact_paths)
    return qge_oracle_export.build_icc_evidence(
        dict_or_empty(oracle_scene),
        dict_or_empty(claims_evidence),
        path_or_empty(paths.get("oracle_scene")),
        path_or_empty(paths.get("claims_evidence")),
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


def oracle_icc_evidence_audit(
    oracle_scene: dict[str, Any] | None,
    claims_evidence: dict[str, Any] | None,
    oracle_icc_evidence: dict[str, Any] | None,
    *,
    artifact_paths: dict[str, str] | None = None,
    required: bool = False,
) -> dict[str, Any]:
    recorded = dict_or_empty(oracle_icc_evidence)
    active = required or bool(recorded)
    if not active:
        return empty_audit(required)

    build_errors: list[dict[str, str]] = []
    try:
        expected = expected_oracle_icc_evidence(
            dict_or_empty(oracle_scene),
            dict_or_empty(claims_evidence),
            artifact_paths=artifact_paths,
        )
    except (KeyError, TypeError, ValueError) as exc:
        build_errors.append({
            "sidecar": "oracle_icc_evidence",
            "error": str(exc),
        })
        expected = {}

    field_mismatches = qge_resource_boundary_audit.mismatch_paths(
        expected,
        recorded,
    ) if recorded else ["<missing>"]
    schema_mismatch = bool(
        recorded and recorded.get("schema") != ICC_EVIDENCE_SCHEMA)
    overclaim_flags = (
        qge_moonlab_overclaim_audit.recursive_overclaim_flags(
            "oracle_icc_evidence",
            recorded,
            forbidden=ORACLE_SIDECAR_FORBIDDEN_CLAIMS,
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


def artifact_path(manifest: dict[str, Any], name: str) -> str | None:
    oracle = dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(
        "oracle"))
    path = dict_or_empty(oracle.get(name)).get("path")
    return path if isinstance(path, str) and path else None


def load_artifact(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    path = artifact_path(manifest, name)
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    return load_json(file_path)


def oracle_icc_evidence_audit_from_manifest(
    manifest: dict[str, Any],
    *,
    required: bool = True,
) -> dict[str, Any]:
    return oracle_icc_evidence_audit(
        load_artifact(manifest, "oracle_scene"),
        load_artifact(manifest, "claims_evidence"),
        load_artifact(manifest, "icc_evidence"),
        artifact_paths={
            "oracle_scene": artifact_path(manifest, "oracle_scene"),
            "claims_evidence": artifact_path(manifest, "claims_evidence"),
        },
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
        help="Exit nonzero when the oracle ICC evidence is stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        audit = oracle_icc_evidence_audit_from_manifest(
            load_json(resolve_manifest(args.pack_or_manifest)),
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_ORACLE_ICC_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_oracle_icc_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
