#!/usr/bin/env python3
"""Audit top-level publication ICC evidence against the packed manifest."""

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
import qge_publication_pack  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402


ICC_EVIDENCE_SCHEMA = "qge.icc_evidence.v0"
PUBLICATION_ICC_FORBIDDEN_CLAIMS = (
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


def expected_publication_icc_evidence(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    icc_path: Path,
) -> dict[str, Any]:
    return qge_publication_pack.build_icc_evidence(
        dict_or_empty(manifest),
        manifest_path,
        icc_path,
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


def publication_icc_evidence_audit(
    manifest: dict[str, Any] | None,
    publication_icc_evidence: dict[str, Any] | None,
    *,
    manifest_path: Path,
    icc_path: Path,
    required: bool = False,
) -> dict[str, Any]:
    recorded = dict_or_empty(publication_icc_evidence)
    active = required or bool(recorded)
    if not active:
        return empty_audit(required)

    build_errors: list[dict[str, str]] = []
    try:
        expected = expected_publication_icc_evidence(
            dict_or_empty(manifest),
            manifest_path=manifest_path,
            icc_path=icc_path,
        )
    except (KeyError, TypeError, ValueError) as exc:
        build_errors.append({
            "artifact": "qge_publication_icc_evidence",
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
            "qge_publication_icc_evidence",
            recorded,
            forbidden=PUBLICATION_ICC_FORBIDDEN_CLAIMS,
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


def resolve_manifest_and_icc(
    pack_or_manifest: Path,
    icc_path: Path | None,
) -> tuple[Path, Path]:
    if pack_or_manifest.is_dir():
        manifest_path = pack_or_manifest / "publication_manifest.json"
        resolved_icc_path = pack_or_manifest / "qge_publication_icc_evidence.json"
    else:
        manifest_path = pack_or_manifest
        if icc_path is None:
            resolved_icc_path = (
                manifest_path.parent / "qge_publication_icc_evidence.json")
        else:
            resolved_icc_path = icc_path
    return manifest_path, resolved_icc_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pack_or_manifest",
        type=Path,
        help="Publication pack directory or publication_manifest.json path.",
    )
    parser.add_argument(
        "--icc",
        type=Path,
        help="qge_publication_icc_evidence.json path when a manifest is used.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional audit JSON output path.",
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit nonzero when the recorded ICC evidence is stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        manifest_path, icc_path = resolve_manifest_and_icc(
            args.pack_or_manifest,
            args.icc,
        )
        audit = publication_icc_evidence_audit(
            load_json(manifest_path),
            load_json(icc_path),
            manifest_path=manifest_path,
            icc_path=icc_path,
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_PUBLICATION_ICC_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_publication_icc_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
