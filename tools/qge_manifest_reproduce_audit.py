#!/usr/bin/env python3
"""Audit publication manifest reproduction command integrity."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any


REQUIRED_REPRODUCE_COMMAND_PREFIXES = (
    "tools/qge_oracle_export.py ",
    "tools/qge_advantage_benchmark.py ",
    "tools/qge_moonlab_qae_transpile.py ",
    "tools/qge_moonlab_oracle_transpile.py ",
    "tools/qge_moonlab_qae_observation_transpile.py ",
    "tools/qge_moonlab_qae_grover_plan.py ",
    "tools/qge_vanilla_capture_matrix.py ",
    "tools/qge_breadth_evidence.py ",
    "tools/qge_publication_pack.py ",
    "tools/qge_registered_asset_intake.py ",
    "tools/qge_asset_requirements.py ",
    "tools/qge_moonlab_job_runner.py ",
    "tools/qge_moonlab_submission_bundle.py ",
    "tools/qge_moonlab_hardware_ingest.py ",
    "tools/qge_moonlab_full_game_plan.py ",
    "tools/qge_moonlab_deployment_gate.py ",
)
OPTIONAL_POSTPACK_REPRODUCE_COMMAND_PREFIXES = (
    "tools/qge_oracle_scene_audit.py ",
    "tools/qge_oracle_claims_audit.py ",
    "tools/qge_oracle_icc_audit.py ",
    "tools/qge_runtime_icc_audit.py ",
    "tools/qge_publication_icc_audit.py ",
    "tools/qge_agent_stream_manifest_audit.py ",
    "tools/qge_agent_stream_icc_audit.py ",
    "tools/qge_trace_summary_audit.py ",
    "tools/qge_registered_asset_script_audit.py ",
    "tools/qge_moonlab_circuit_file_audit.py ",
    "tools/qge_advantage_generated_file_audit.py ",
    "tools/qge_manifest_file_audit.py ",
    "tools/qge_manifest_summary_audit.py ",
    "tools/qge_manifest_source_input_audit.py ",
    "tools/qge_manifest_claim_policy_audit.py ",
    "tools/qge_manifest_reproduce_audit.py ",
    "tools/qge_manifest_markdown_audit.py ",
)
FORBIDDEN_SHELL_FRAGMENTS = (";", "&&", "||", "|", "`", "$(")


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


def command_matches(commands: list[str], prefix: str) -> bool:
    return any(command.startswith(prefix) for command in commands)


def duplicate_commands(commands: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for command in commands:
        if command in seen and command not in duplicates:
            duplicates.append(command)
        seen.add(command)
    return duplicates


def unsafe_command_reasons(command: str) -> list[str]:
    reasons = [
        f"shell_fragment:{fragment}"
        for fragment in FORBIDDEN_SHELL_FRAGMENTS
        if fragment in command
    ]
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return reasons + [f"parse_error:{exc}"]
    if not tokens:
        return reasons + ["empty_command"]
    if not tokens[0].startswith("tools/"):
        reasons.append("non_tools_command")
    return reasons


def manifest_reproduce_audit(
    manifest: dict[str, Any] | None,
    *,
    required: bool = True,
) -> dict[str, Any]:
    manifest_data = dict_or_empty(manifest)
    raw_commands = manifest_data.get("reproduce_commands")
    commands = raw_commands if isinstance(raw_commands, list) else []
    string_commands = [
        command for command in commands
        if isinstance(command, str) and command
    ]
    malformed_commands = [
        {"index": index, "value": command}
        for index, command in enumerate(commands)
        if not isinstance(command, str) or not command
    ]
    recorded = bool(string_commands)
    if not recorded and not required:
        return {
            "required": required,
            "recorded": False,
            "command_count": 0,
            "required_command_count": len(REQUIRED_REPRODUCE_COMMAND_PREFIXES),
            "missing_required_commands": [],
            "missing_optional_postpack_commands": [],
            "duplicate_commands": [],
            "unsafe_commands": [],
            "malformed_commands": [],
            "mismatch_count": 0,
            "passed": True,
        }

    missing_required = [
        prefix for prefix in REQUIRED_REPRODUCE_COMMAND_PREFIXES
        if not command_matches(string_commands, prefix)
    ]
    missing_optional = [
        prefix for prefix in OPTIONAL_POSTPACK_REPRODUCE_COMMAND_PREFIXES
        if not command_matches(string_commands, prefix)
    ]
    duplicates = duplicate_commands(string_commands)
    unsafe_commands = [
        {
            "command": command,
            "reasons": reasons,
        }
        for command in string_commands
        for reasons in [unsafe_command_reasons(command)]
        if reasons
    ]
    mismatch_count = (
        len(missing_required) +
        len(duplicates) +
        len(unsafe_commands) +
        len(malformed_commands)
    )
    passed = mismatch_count == 0 and (recorded or not required)
    return {
        "required": required,
        "recorded": recorded,
        "command_count": len(string_commands),
        "required_command_count": len(REQUIRED_REPRODUCE_COMMAND_PREFIXES),
        "optional_postpack_command_count": (
            len(OPTIONAL_POSTPACK_REPRODUCE_COMMAND_PREFIXES)),
        "missing_required_commands": missing_required,
        "missing_optional_postpack_commands": missing_optional,
        "duplicate_commands": duplicates,
        "unsafe_commands": unsafe_commands,
        "malformed_commands": malformed_commands,
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
        help="Exit nonzero when manifest reproduction commands are unsafe.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        audit = manifest_reproduce_audit(
            load_json(resolve_manifest(args.pack_or_manifest)),
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_MANIFEST_REPRODUCE_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_manifest_reproduce_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
