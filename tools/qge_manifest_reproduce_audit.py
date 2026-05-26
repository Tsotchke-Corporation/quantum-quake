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
POSTPACK_REPRODUCE_COMMAND_PREFIXES = (
    "tools/qge_oracle_scene_audit.py ",
    "tools/qge_oracle_claims_audit.py ",
    "tools/qge_oracle_icc_audit.py ",
    "tools/qge_advantage_metrics_audit.py ",
    "tools/qge_runtime_icc_audit.py ",
    "tools/qge_publication_icc_audit.py ",
    "tools/qge_vanilla_matrix_audit.py ",
    "tools/qge_agent_stream_manifest_audit.py ",
    "tools/qge_agent_stream_icc_audit.py ",
    "tools/qge_trace_summary_audit.py ",
    "tools/qge_breadth_evidence_audit.py ",
    "tools/qge_asset_resource_audit.py ",
    "tools/qge_registered_asset_script_audit.py ",
    "tools/qge_resource_boundary_audit.py ",
    "tools/qge_moonlab_full_game_plan_audit.py ",
    "tools/qge_moonlab_deployment_gate_audit.py ",
    "tools/qge_moonlab_job_plan_audit.py ",
    "tools/qge_moonlab_handoff_audit.py ",
    "tools/qge_moonlab_advantage_artifact_audit.py ",
    "tools/qge_moonlab_circuit_file_audit.py ",
    "tools/qge_advantage_generated_file_audit.py ",
    "tools/qge_manifest_file_audit.py ",
    "tools/qge_manifest_summary_audit.py ",
    "tools/qge_manifest_source_input_audit.py ",
    "tools/qge_manifest_source_copy_audit.py ",
    "tools/qge_manifest_claim_policy_audit.py ",
    "tools/qge_manifest_reproduce_audit.py ",
    "tools/qge_manifest_markdown_audit.py ",
    "tools/qge_postpack_audit.py ",
)
OPTIONAL_POSTPACK_REPRODUCE_COMMAND_PREFIXES = (
    POSTPACK_REPRODUCE_COMMAND_PREFIXES)
FORBIDDEN_SHELL_FRAGMENTS = (";", "&&", "||", "|", "`", "$(")
PACK_DIR_PLACEHOLDER = "<pack_dir>"
POSTPACK_AUDIT_OUTDIR = "/tmp/qge_postpack_audits"


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


def expected_reproduce_command_prefixes() -> tuple[str, ...]:
    return (
        REQUIRED_REPRODUCE_COMMAND_PREFIXES +
        POSTPACK_REPRODUCE_COMMAND_PREFIXES
    )


def commands_with_prefix(commands: list[str], prefix: str) -> list[str]:
    return [command for command in commands if command.startswith(prefix)]


def unexpected_reproduce_commands(commands: list[str]) -> list[str]:
    expected_prefixes = expected_reproduce_command_prefixes()
    return [
        command for command in commands
        if not any(command.startswith(prefix) for prefix in expected_prefixes)
    ]


def duplicate_commands(commands: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for command in commands:
        if command in seen and command not in duplicates:
            duplicates.append(command)
        seen.add(command)
    return duplicates


def duplicate_command_prefixes(commands: list[str]) -> list[dict[str, Any]]:
    duplicates = []
    for prefix in expected_reproduce_command_prefixes():
        matching_commands = commands_with_prefix(commands, prefix)
        if len(matching_commands) > 1:
            duplicates.append({
                "prefix": prefix,
                "commands": matching_commands,
            })
    return duplicates


def duplicate_command_prefix_extra_count(
    duplicate_prefixes: list[dict[str, Any]],
) -> int:
    extra_count = 0
    for duplicate_prefix in duplicate_prefixes:
        commands = duplicate_prefix.get("commands", [])
        if isinstance(commands, list):
            extra_count += max(0, len(commands) - 1)
    return extra_count


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


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def option_values(tokens: list[str], option: str) -> list[str]:
    values = []
    for index, token in enumerate(tokens):
        if token != option:
            continue
        if index + 1 < len(tokens):
            values.append(tokens[index + 1])
        else:
            values.append("")
    return values


def expected_command_token_indexes(
    tokens: list[str],
    checks: list[dict[str, Any]],
) -> set[int]:
    indexes = {0}
    for check in checks:
        if "position" in check:
            position = int(check["position"])
            if position < len(tokens):
                indexes.add(position)
            continue
        option = check["option"]
        for index, token in enumerate(tokens):
            if token != option:
                continue
            indexes.add(index)
            if not check.get("boolean") and index + 1 < len(tokens):
                indexes.add(index + 1)
    return indexes


def unexpected_command_token_mismatches(
    tokens: list[str],
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    expected_indexes = expected_command_token_indexes(tokens, checks)
    return [
        {
            "position": index,
            "reason": "unexpected_token",
            "expected_values": [],
            "actual_values": [token],
        }
        for index, token in enumerate(tokens)
        if index not in expected_indexes
    ]


def add_scalar_option_check(
    checks: list[dict[str, Any]],
    option: str,
    expected: Any,
    *,
    required: bool,
) -> None:
    if expected is None and not required:
        checks.append({
            "option": option,
            "expected_values": [],
            "required": False,
        })
        return
    if expected is None:
        checks.append({
            "option": option,
            "expected_values": [],
            "required": True,
            "expected_missing": True,
        })
        return
    checks.append({
        "option": option,
        "expected_values": [str(expected)],
        "required": required,
    })


def position_check(position: int, expected: Any) -> dict[str, Any]:
    return {
        "position": position,
        "expected_values": [str(expected)],
    }


def boolean_option_check(
    option: str,
    *,
    expected_present: bool = True,
) -> dict[str, Any]:
    return {
        "option": option,
        "expected_present": expected_present,
        "boolean": True,
    }


def postpack_audit_output_for_prefix(prefix: str) -> str:
    return f"/tmp/{Path(prefix.strip()).stem}.json"


def publication_pack_option_checks(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    source_inputs = dict_or_empty(manifest.get("source_inputs"))
    if not source_inputs:
        return []
    checks: list[dict[str, Any]] = []
    pack_reproduction = dict_or_empty(
        source_inputs.get("publication_pack_reproduction"))
    add_scalar_option_check(
        checks, "--outdir", pack_reproduction.get("outdir"), required=True)
    add_scalar_option_check(
        checks, "--capture-dir", source_inputs.get("capture_dir"),
        required=True)
    add_scalar_option_check(
        checks, "--vanilla-matrix", source_inputs.get("vanilla_matrix"),
        required=True)
    add_scalar_option_check(
        checks, "--graphics-capture-dir",
        source_inputs.get("graphics_capture_dir"), required=False)
    add_scalar_option_check(
        checks, "--agent-stream-dir", source_inputs.get("agent_stream_dir"),
        required=False)
    add_scalar_option_check(
        checks, "--breadth-evidence", source_inputs.get("breadth_evidence"),
        required=False)
    add_scalar_option_check(
        checks, "--asset-root", source_inputs.get("asset_root"),
        required=True)
    for option, field in (
        ("--registered-asset-candidate", "registered_asset_candidates"),
        ("--registered-asset-discover-root", "registered_asset_discover_roots"),
    ):
        checks.append({
            "option": option,
            "expected_values": [
                str(value) for value in list_or_empty(source_inputs.get(field))
            ],
            "required": False,
        })
    checks.append({
        "option": "--registered-asset-discover-common",
        "expected_present": bool(
            source_inputs.get("registered_asset_discover_common")),
        "boolean": True,
    })
    add_scalar_option_check(
        checks,
        "--registered-asset-discover-max-depth",
        source_inputs.get("registered_asset_discover_max_depth"),
        required=True,
    )
    add_scalar_option_check(
        checks, "--claims", source_inputs.get("claims_ledger"),
        required=True)
    benchmark = dict_or_empty(source_inputs.get("advantage_benchmark"))
    for option, field in (
        ("--seed", "seed"),
        ("--trials", "trials"),
        ("--qae-levels", "qae_levels"),
        ("--qae-shots", "qae_shots"),
        ("--qae-grid-steps", "qae_grid_steps"),
        ("--contribution-bits", "contribution_bits"),
    ):
        add_scalar_option_check(
            checks, option, benchmark.get(field), required=True)
    checks.append({
        "option": "--samples",
        "expected_values": [
            str(value) for value in list_or_empty(benchmark.get("samples"))
        ],
        "required": True,
    })
    return checks


def publication_pack_command_field_mismatches(
    command: str,
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return [{
            "option": None,
            "reason": f"parse_error:{exc}",
            "expected_values": [],
            "actual_values": [],
        }]
    mismatches = []
    for check in checks:
        if "position" in check:
            expected_values = [
                str(value)
                for value in list_or_empty(check.get("expected_values"))
            ]
            position = int(check["position"])
            actual_values = (
                [tokens[position]] if len(tokens) > position else []
            )
            if expected_values == actual_values:
                continue
            reason = "value_mismatch"
            if expected_values and not actual_values:
                reason = "missing_argument"
            elif not expected_values and actual_values:
                reason = "unexpected_argument"
            mismatches.append({
                "position": position,
                "reason": reason,
                "expected_values": expected_values,
                "actual_values": actual_values,
            })
            continue
        option = check["option"]
        if check.get("boolean"):
            expected_present = bool(check.get("expected_present"))
            actual_present = option in tokens
            if expected_present != actual_present:
                mismatches.append({
                    "option": option,
                    "reason": "presence_mismatch",
                    "expected_present": expected_present,
                    "actual_present": actual_present,
                })
            continue
        expected_values = [
            str(value) for value in list_or_empty(check.get("expected_values"))
        ]
        actual_values = option_values(tokens, option)
        if check.get("required") and check.get("expected_missing"):
            mismatches.append({
                "option": option,
                "reason": "missing_expected_value",
                "expected_values": expected_values,
                "actual_values": actual_values,
            })
            continue
        if check.get("required") and not expected_values:
            mismatches.append({
                "option": option,
                "reason": "missing_expected_values",
                "expected_values": expected_values,
                "actual_values": actual_values,
            })
            continue
        if expected_values == actual_values:
            continue
        reason = "value_mismatch"
        if expected_values and not actual_values:
            reason = "missing_option"
        elif not expected_values and actual_values:
            reason = "unexpected_option"
        mismatches.append({
            "option": option,
            "reason": reason,
            "expected_values": expected_values,
            "actual_values": actual_values,
        })
    mismatches.extend(unexpected_command_token_mismatches(tokens, checks))
    return mismatches


def core_command_option_checks(
    manifest: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    source_inputs = dict_or_empty(manifest.get("source_inputs"))
    if not source_inputs:
        return {}
    checks: dict[str, list[dict[str, Any]]] = {}
    claims_ledger = source_inputs.get("claims_ledger")
    capture_dir = source_inputs.get("capture_dir")
    if capture_dir is not None or claims_ledger is not None:
        command_checks: list[dict[str, Any]] = []
        if capture_dir is not None:
            command_checks.append({
                "position": 1,
                "expected_values": [str(capture_dir)],
            })
        add_scalar_option_check(
            command_checks, "--claims", claims_ledger, required=True)
        add_scalar_option_check(
            command_checks, "--oracle-out", "/tmp/oracle_scene.json",
            required=True)
        add_scalar_option_check(
            command_checks, "--claims-out", "/tmp/claims_evidence.json",
            required=True)
        add_scalar_option_check(
            command_checks, "--icc-out", "/tmp/qge_icc_evidence.json",
            required=True)
        checks["tools/qge_oracle_export.py "] = command_checks

    benchmark = dict_or_empty(source_inputs.get("advantage_benchmark"))
    if benchmark:
        benchmark_checks: list[dict[str, Any]] = []
        if benchmark.get("oracle_scene") is not None:
            benchmark_checks.append({
                "position": 1,
                "expected_values": [str(benchmark.get("oracle_scene"))],
            })
        add_scalar_option_check(
            benchmark_checks, "--outdir", benchmark.get("outdir"),
            required=True)
        for option, field in (
            ("--seed", "seed"),
            ("--trials", "trials"),
            ("--qae-levels", "qae_levels"),
            ("--qae-shots", "qae_shots"),
            ("--qae-grid-steps", "qae_grid_steps"),
            ("--contribution-bits", "contribution_bits"),
        ):
            add_scalar_option_check(
                benchmark_checks, option, benchmark.get(field), required=True)
        benchmark_checks.append({
            "option": "--samples",
            "expected_values": [
                str(value) for value in list_or_empty(
                    benchmark.get("samples"))
            ],
            "required": True,
        })
        checks["tools/qge_advantage_benchmark.py "] = benchmark_checks

    vanilla_source = source_inputs.get("graphics_capture_dir")
    if vanilla_source is None and source_inputs.get("vanilla_matrix"):
        vanilla_source = str(Path(str(source_inputs["vanilla_matrix"])).parent)
    if vanilla_source is not None:
        vanilla_checks = [{
            "position": 1,
            "expected_values": [str(vanilla_source)],
        }]
        add_scalar_option_check(
            vanilla_checks, "--out", "/tmp/vanilla_capture_matrix.json",
            required=True)
        add_scalar_option_check(
            vanilla_checks, "--icc-out",
            "/tmp/qge_vanilla_icc_evidence.json", required=True)
        checks["tools/qge_vanilla_capture_matrix.py "] = vanilla_checks

    breadth_plan = dict_or_empty(
        source_inputs.get("breadth_evidence_reproduction"))
    breadth_matrices = [
        str(value) for value in list_or_empty(breadth_plan.get("matrices"))
    ]
    if breadth_plan:
        breadth_checks: list[dict[str, Any]] = []
        breadth_checks.append({
            "option": "--matrix",
            "expected_values": breadth_matrices,
            "required": True,
        })
        add_scalar_option_check(
            breadth_checks, "--min-runs",
            breadth_plan.get("min_runs"), required=True)
        add_scalar_option_check(
            breadth_checks, "--min-maps",
            breadth_plan.get("min_maps"), required=True)
        add_scalar_option_check(
            breadth_checks, "--map-set",
            breadth_plan.get("map_set"), required=True)
        add_scalar_option_check(
            breadth_checks, "--out", "/tmp/breadth_evidence.json",
            required=True)
        add_scalar_option_check(
            breadth_checks, "--icc-out", "/tmp/qge_breadth_icc_evidence.json",
            required=True)
        checks["tools/qge_breadth_evidence.py "] = breadth_checks

    intake_plan = dict_or_empty(
        source_inputs.get("registered_asset_intake_reproduction"))
    if intake_plan:
        intake_checks: list[dict[str, Any]] = []
        add_scalar_option_check(
            intake_checks, "--current-root",
            intake_plan.get("current_root"), required=True)
        intake_checks.append({
            "option": "--candidate",
            "expected_values": [
                str(value)
                for value in list_or_empty(intake_plan.get("candidates"))
            ],
            "required": False,
        })
        intake_checks.append({
            "option": "--discover-root",
            "expected_values": [
                str(value)
                for value in list_or_empty(intake_plan.get("discover_roots"))
            ],
            "required": False,
        })
        intake_checks.append({
            "option": "--discover-common",
            "expected_present": bool(intake_plan.get("discover_common")),
            "boolean": True,
        })
        intake_checks.append({
            "option": "--allow-empty-candidates",
            "expected_present": bool(
                intake_plan.get("allow_empty_candidates")),
            "boolean": True,
        })
        add_scalar_option_check(
            intake_checks, "--discover-max-depth",
            intake_plan.get("discover_max_depth"), required=True)
        add_scalar_option_check(
            intake_checks, "--publication-pack",
            intake_plan.get("publication_pack"), required=True)
        add_scalar_option_check(
            intake_checks, "--map-set",
            intake_plan.get("map_set"), required=True)
        add_scalar_option_check(
            intake_checks, "--json",
            "/tmp/qge_registered_asset_intake.json", required=True)
        add_scalar_option_check(
            intake_checks, "--markdown",
            "/tmp/qge_registered_asset_intake.md", required=True)
        add_scalar_option_check(
            intake_checks, "--script-out",
            "/tmp/install_registered_assets.sh", required=True)
        add_scalar_option_check(
            intake_checks, "--icc-json",
            "/tmp/qge_registered_asset_intake_icc_evidence.json",
            required=True)
        checks["tools/qge_registered_asset_intake.py "] = intake_checks

    asset_root = source_inputs.get("asset_root")
    if asset_root is not None:
        checks["tools/qge_asset_requirements.py "] = []
        add_scalar_option_check(
            checks["tools/qge_asset_requirements.py "],
            "--asset-root",
            asset_root,
            required=True,
        )
        add_scalar_option_check(
            checks["tools/qge_asset_requirements.py "],
            "--json",
            "/tmp/qge_asset_requirements.json",
            required=True,
        )
        add_scalar_option_check(
            checks["tools/qge_asset_requirements.py "],
            "--markdown",
            "/tmp/qge_asset_requirements.md",
            required=True,
        )
        add_scalar_option_check(
            checks["tools/qge_asset_requirements.py "],
            "--icc-json",
            "/tmp/qge_asset_requirements_icc_evidence.json",
            required=True,
        )
    checks.update({
        "tools/qge_moonlab_qae_transpile.py ": [
            {
                "option": "--metrics",
                "expected_values": [
                    "<pack_dir>/advantage/advantage_metrics.json"],
                "required": True,
            },
            {
                "option": "--abstract-circuit",
                "expected_values": ["<pack_dir>/advantage/qae_circuit.txt"],
                "required": True,
            },
            {
                "option": "--out",
                "expected_values": ["/tmp/qae_moonlab_payload.json"],
                "required": True,
            },
            {
                "option": "--circuit-dir",
                "expected_values": ["/tmp/moonlab_qae_circuits"],
                "required": True,
            },
            {
                "option": "--markdown",
                "expected_values": ["/tmp/qae_moonlab_payload.md"],
                "required": True,
            },
            {
                "option": "--icc-json",
                "expected_values": [
                    "/tmp/qae_moonlab_payload_icc_evidence.json"],
                "required": True,
            },
        ],
        "tools/qge_moonlab_oracle_transpile.py ": [
            {
                "option": "--metrics",
                "expected_values": [
                    "<pack_dir>/advantage/advantage_metrics.json"],
                "required": True,
            },
            {
                "option": "--oracle-scene",
                "expected_values": ["<pack_dir>/oracle/oracle_scene.json"],
                "required": True,
            },
            {
                "option": "--out",
                "expected_values": ["/tmp/qae_moonlab_oracle_kernel.json"],
                "required": True,
            },
            {
                "option": "--circuit",
                "expected_values": ["/tmp/qae_moonlab_oracle_kernel.moonlab"],
                "required": True,
            },
            {
                "option": "--markdown",
                "expected_values": ["/tmp/qae_moonlab_oracle_kernel.md"],
                "required": True,
            },
            {
                "option": "--icc-json",
                "expected_values": [
                    "/tmp/qae_moonlab_oracle_kernel_icc_evidence.json"],
                "required": True,
            },
        ],
        "tools/qge_moonlab_qae_observation_transpile.py ": [
            {
                "option": "--metrics",
                "expected_values": [
                    "<pack_dir>/advantage/advantage_metrics.json"],
                "required": True,
            },
            {
                "option": "--oracle-scene",
                "expected_values": ["<pack_dir>/oracle/oracle_scene.json"],
                "required": True,
            },
            {
                "option": "--out",
                "expected_values": [
                    "/tmp/qae_moonlab_observation_zero.json"],
                "required": True,
            },
            {
                "option": "--circuit",
                "expected_values": [
                    "/tmp/qae_moonlab_observation_zero.moonlab"],
                "required": True,
            },
            {
                "option": "--markdown",
                "expected_values": ["/tmp/qae_moonlab_observation_zero.md"],
                "required": True,
            },
            {
                "option": "--icc-json",
                "expected_values": [
                    "/tmp/qae_moonlab_observation_zero_icc_evidence.json"],
                "required": True,
            },
        ],
        "tools/qge_moonlab_qae_grover_plan.py ": [
            {
                "option": "--metrics",
                "expected_values": [
                    "<pack_dir>/advantage/advantage_metrics.json"],
                "required": True,
            },
            {
                "option": "--oracle-scene",
                "expected_values": ["<pack_dir>/oracle/oracle_scene.json"],
                "required": True,
            },
            {
                "option": "--out",
                "expected_values": [
                    "/tmp/qae_moonlab_grover_schedule_plan.json"],
                "required": True,
            },
            {
                "option": "--markdown",
                "expected_values": [
                    "/tmp/qae_moonlab_grover_schedule_plan.md"],
                "required": True,
            },
            {
                "option": "--icc-json",
                "expected_values": [
                    "/tmp/qae_moonlab_grover_schedule_plan_icc_evidence.json"],
                "required": True,
            },
        ],
        "tools/qge_moonlab_job_runner.py ": [
            position_check(
                1, "<pack_dir>/resource/qge_moonlab_job_specs.json"),
            {
                "option": "--out",
                "expected_values": [
                    "/tmp/qge_moonlab_job_results.verify.json"],
                "required": True,
            },
            {
                "option": "--expect",
                "expected_values": [
                    "<pack_dir>/resource/qge_moonlab_job_results.json"],
                "required": True,
            },
            {
                "option": "--plan-out",
                "expected_values": [
                    "/tmp/qge_moonlab_replay_plan.verify.json"],
                "required": True,
            },
            {
                "option": "--submission-out",
                "expected_values": [
                    "/tmp/qge_moonlab_submission_packet.verify.json"],
                "required": True,
            },
        ],
        "tools/qge_moonlab_submission_bundle.py ": [
            position_check(
                1, "<pack_dir>/resource/qge_moonlab_submission_packet.json"),
            {
                "option": "--out",
                "expected_values": ["/tmp/qge_moonlab_submission_bundle.json"],
                "required": True,
            },
            {
                "option": "--markdown",
                "expected_values": ["/tmp/qge_moonlab_submission_bundle.md"],
                "required": True,
            },
            {
                "option": "--icc-json",
                "expected_values": [
                    "/tmp/qge_moonlab_submission_bundle_icc_evidence.json"],
                "required": True,
            },
        ],
        "tools/qge_moonlab_hardware_ingest.py ": [
            position_check(
                1, "<pack_dir>/resource/qge_moonlab_submission_packet.json"),
            {
                "option": "--template-out",
                "expected_values": [
                    "/tmp/qge_moonlab_hardware_record.template.json"],
                "required": True,
            },
        ],
        "tools/qge_moonlab_full_game_plan.py ": [
            position_check(1, "<pack_dir>"),
            {
                "option": "--out",
                "expected_values": ["/tmp/qge_moonlab_full_game_plan.json"],
                "required": True,
            },
            {
                "option": "--markdown",
                "expected_values": ["/tmp/qge_moonlab_full_game_plan.md"],
                "required": True,
            },
            {
                "option": "--icc-json",
                "expected_values": [
                    "/tmp/qge_moonlab_full_game_plan_icc_evidence.json"],
                "required": True,
            },
        ],
        "tools/qge_moonlab_deployment_gate.py ": [
            position_check(1, "<pack_dir>"),
            {
                "option": "--out",
                "expected_values": ["/tmp/qge_moonlab_deployment_gate.json"],
                "required": True,
            },
            {
                "option": "--markdown",
                "expected_values": ["/tmp/qge_moonlab_deployment_gate.md"],
                "required": True,
            },
            {
                "option": "--icc-json",
                "expected_values": [
                    "/tmp/qge_moonlab_deployment_gate_icc_evidence.json"],
                "required": True,
            },
        ],
    })
    return checks


def core_command_source_mismatches(
    manifest: dict[str, Any],
    commands: list[str],
) -> list[dict[str, Any]]:
    mismatches = []
    for prefix, checks in core_command_option_checks(manifest).items():
        for command in commands_with_prefix(commands, prefix):
            field_mismatches = publication_pack_command_field_mismatches(
                command, checks)
            if field_mismatches:
                mismatches.append({
                    "prefix": prefix,
                    "command": command,
                    "field_mismatches": field_mismatches,
                })
    return mismatches


def postpack_command_option_checks() -> dict[str, list[dict[str, Any]]]:
    checks: dict[str, list[dict[str, Any]]] = {}
    for prefix in POSTPACK_REPRODUCE_COMMAND_PREFIXES:
        command_checks = [
            position_check(1, PACK_DIR_PLACEHOLDER),
            {
                "option": "--out",
                "expected_values": [postpack_audit_output_for_prefix(prefix)],
                "required": True,
            },
            boolean_option_check("--fail-on-mismatch"),
        ]
        if prefix == "tools/qge_postpack_audit.py ":
            command_checks.insert(2, {
                "option": "--outdir",
                "expected_values": [POSTPACK_AUDIT_OUTDIR],
                "required": True,
            })
        checks[prefix] = command_checks
    return checks


def postpack_command_source_mismatches(
    commands: list[str],
) -> list[dict[str, Any]]:
    mismatches = []
    for prefix, checks in postpack_command_option_checks().items():
        for command in commands_with_prefix(commands, prefix):
            field_mismatches = publication_pack_command_field_mismatches(
                command, checks)
            if field_mismatches:
                mismatches.append({
                    "prefix": prefix,
                    "command": command,
                    "field_mismatches": field_mismatches,
                })
    return mismatches


def publication_pack_source_mismatches(
    manifest: dict[str, Any],
    commands: list[str],
) -> list[dict[str, Any]]:
    checks = publication_pack_option_checks(manifest)
    if not checks:
        return []
    pack_commands = commands_with_prefix(
        commands, "tools/qge_publication_pack.py ")
    if not pack_commands:
        return []
    per_command = [
        {
            "command": command,
            "field_mismatches": publication_pack_command_field_mismatches(
                command, checks),
        }
        for command in pack_commands
    ]
    return [
        item for item in per_command
        if item["field_mismatches"]
    ]


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
            "postpack_command_count": len(POSTPACK_REPRODUCE_COMMAND_PREFIXES),
            "missing_required_commands": [],
            "missing_postpack_commands": [],
            "missing_optional_postpack_commands": [],
            "unexpected_commands": [],
            "duplicate_commands": [],
            "duplicate_command_prefixes": [],
            "duplicate_command_prefix_extra_count": 0,
            "unsafe_commands": [],
            "malformed_commands": [],
            "core_command_source_mismatches": [],
            "postpack_command_source_mismatches": [],
            "publication_pack_command_count": 0,
            "publication_pack_source_mismatches": [],
            "mismatch_count": 0,
            "passed": True,
        }

    missing_required = [
        prefix for prefix in REQUIRED_REPRODUCE_COMMAND_PREFIXES
        if not command_matches(string_commands, prefix)
    ]
    missing_postpack = [
        prefix for prefix in POSTPACK_REPRODUCE_COMMAND_PREFIXES
        if not command_matches(string_commands, prefix)
    ]
    unexpected_commands = unexpected_reproduce_commands(string_commands)
    duplicates = duplicate_commands(string_commands)
    duplicate_prefixes = duplicate_command_prefixes(string_commands)
    duplicate_prefix_extra_count = duplicate_command_prefix_extra_count(
        duplicate_prefixes)
    unsafe_commands = [
        {
            "command": command,
            "reasons": reasons,
        }
        for command in string_commands
        for reasons in [unsafe_command_reasons(command)]
        if reasons
    ]
    pack_source_mismatches = publication_pack_source_mismatches(
        manifest_data, string_commands)
    core_source_mismatches = core_command_source_mismatches(
        manifest_data, string_commands)
    postpack_source_mismatches = postpack_command_source_mismatches(
        string_commands)
    pack_source_mismatch_count = sum(
        len(item.get("field_mismatches", []))
        for item in pack_source_mismatches
    )
    core_source_mismatch_count = sum(
        len(item.get("field_mismatches", []))
        for item in core_source_mismatches
    )
    postpack_source_mismatch_count = sum(
        len(item.get("field_mismatches", []))
        for item in postpack_source_mismatches
    )
    mismatch_count = (
        len(missing_required) +
        len(missing_postpack) +
        len(unexpected_commands) +
        len(duplicates) +
        len(duplicate_prefixes) +
        len(unsafe_commands) +
        len(malformed_commands) +
        pack_source_mismatch_count +
        core_source_mismatch_count +
        postpack_source_mismatch_count
    )
    passed = mismatch_count == 0 and (recorded or not required)
    return {
        "required": required,
        "recorded": recorded,
        "command_count": len(string_commands),
        "required_command_count": len(REQUIRED_REPRODUCE_COMMAND_PREFIXES),
        "postpack_command_count": len(POSTPACK_REPRODUCE_COMMAND_PREFIXES),
        "optional_postpack_command_count": (
            len(POSTPACK_REPRODUCE_COMMAND_PREFIXES)),
        "missing_required_commands": missing_required,
        "missing_postpack_commands": missing_postpack,
        "missing_optional_postpack_commands": missing_postpack,
        "unexpected_commands": unexpected_commands,
        "duplicate_commands": duplicates,
        "duplicate_command_prefixes": duplicate_prefixes,
        "duplicate_command_prefix_extra_count": duplicate_prefix_extra_count,
        "unsafe_commands": unsafe_commands,
        "malformed_commands": malformed_commands,
        "core_command_source_mismatches": core_source_mismatches,
        "postpack_command_source_mismatches": postpack_source_mismatches,
        "publication_pack_command_count": len(commands_with_prefix(
            string_commands, "tools/qge_publication_pack.py ")),
        "publication_pack_source_mismatches": pack_source_mismatches,
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
