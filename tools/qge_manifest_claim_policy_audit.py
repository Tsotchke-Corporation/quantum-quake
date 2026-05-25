#!/usr/bin/env python3
"""Audit publication manifest claim posture against gate claim flags."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_DISALLOWED_PHRASES = (
    "hardware speedup",
    "full-frame quantum rendering",
    "unrestricted quantum advantage",
)
ALWAYS_FORBIDDEN_ALLOWED_PHRASES = (
    "hardware speedup",
    "practical hardware speedup",
    "full-frame quantum rendering",
    "unrestricted quantum advantage",
    "dense 70000",
    "70,000-qubit",
)
GATE_FORBIDDEN_ALLOWED_PHRASES = {
    "whole_game_moonlab_deployment_claim_allowed": (
        "whole game runs in moonlab",
        "entire game runs in moonlab",
        "full game runs in moonlab",
        "whole-game moonlab deployment",
    ),
    "whole_game_hardware_execution_claim_allowed": (
        "whole game hardware execution",
        "whole-game hardware execution",
        "entire game hardware execution",
    ),
    "hardware_quantum_advantage_claim_allowed": (
        "hardware quantum advantage",
        "hardware advantage",
        "practical rendering advantage",
    ),
    "dense_70000_qubit_state_claim_allowed": (
        "dense 70000-qubit",
        "dense 70,000-qubit",
        "70000-qubit state",
        "70,000-qubit state",
    ),
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


def normalize_text(value: Any) -> str:
    return value.lower() if isinstance(value, str) else ""


def deployment_gate_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return dict_or_empty(
        dict_or_empty(manifest.get("advantage_summary")).get(
            "moonlab_deployment_gate_summary")
    )


def missing_required_disallowed(disallowed: str) -> list[str]:
    return [
        phrase for phrase in REQUIRED_DISALLOWED_PHRASES
        if phrase not in disallowed
    ]


def forbidden_allowed_hits(
    allowed: str,
    gate_summary: dict[str, Any],
) -> list[dict[str, str]]:
    hits = [
        {
            "claim_flag": "always_forbidden",
            "phrase": phrase,
        }
        for phrase in ALWAYS_FORBIDDEN_ALLOWED_PHRASES
        if phrase in allowed
    ]
    for gate_flag, phrases in GATE_FORBIDDEN_ALLOWED_PHRASES.items():
        if gate_summary.get(gate_flag) is True:
            continue
        hits.extend(
            {
                "claim_flag": gate_flag,
                "phrase": phrase,
            }
            for phrase in phrases
            if phrase in allowed
        )
    return hits


def manifest_claim_policy_audit(
    manifest: dict[str, Any] | None,
    *,
    required: bool = True,
) -> dict[str, Any]:
    manifest_data = dict_or_empty(manifest)
    claim_posture = dict_or_empty(manifest_data.get("claim_posture"))
    allowed = normalize_text(claim_posture.get("allowed_wording"))
    disallowed = normalize_text(claim_posture.get("disallowed_wording"))
    recorded = bool(claim_posture)
    if not recorded and not required:
        return {
            "required": required,
            "recorded": False,
            "missing_fields": [],
            "missing_disallowed_phrases": [],
            "forbidden_allowed_phrases": [],
            "mismatch_count": 0,
            "passed": True,
        }

    missing_fields = [
        field for field in ("allowed_wording", "disallowed_wording")
        if not isinstance(claim_posture.get(field), str)
        or not claim_posture.get(field)
    ]
    missing_disallowed = missing_required_disallowed(disallowed)
    forbidden_allowed = forbidden_allowed_hits(
        allowed,
        deployment_gate_summary(manifest_data),
    )
    mismatch_count = (
        len(missing_fields) +
        len(missing_disallowed) +
        len(forbidden_allowed)
    )
    passed = mismatch_count == 0 and (recorded or not required)
    return {
        "required": required,
        "recorded": recorded,
        "missing_fields": missing_fields,
        "missing_disallowed_phrases": missing_disallowed,
        "forbidden_allowed_phrases": forbidden_allowed,
        "mismatch_count": mismatch_count,
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
        help="Exit nonzero when manifest claim posture is unsafe.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        audit = manifest_claim_policy_audit(
            load_json(resolve_manifest(args.pack_or_manifest)),
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_MANIFEST_CLAIM_POLICY_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_manifest_claim_policy_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
