#!/usr/bin/env python3
"""Build a hard Moonlab full-game deployment claim gate.

The gate is an eligibility check, not a claim by itself. It joins the
publication pack's full-game map coverage, BSP asset audit, registered asset
requirements, Moonlab job results, and no-overclaim posture into one
machine-readable verdict for whether "the full game runs in Moonlab" may be
claimed for the simulator/native deployment surface.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_asset_inventory  # noqa: E402
import qge_asset_requirements  # noqa: E402
import qge_breadth_evidence  # noqa: E402
import qge_full_game_capture_queue  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402
import qge_registered_asset_intake  # noqa: E402


PASS = "pass"
FAIL = "fail"


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


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def bool_true(value: Any) -> bool:
    return value is True


def artifact_path(
    artifacts: dict[str, Any],
    key: str,
) -> str | None:
    entry = artifacts.get(key)
    if not isinstance(entry, dict):
        return None
    path = entry.get("path")
    return path if isinstance(path, str) else None


def asset_remediation_from_intake(
    intake: dict[str, Any] | None,
    *,
    intake_path: Path | str | None = None,
    markdown_path: Path | str | None = None,
    script_path: Path | str | None = None,
    icc_evidence_path: Path | str | None = None,
) -> dict[str, Any]:
    data = dict_or_empty(intake)
    if not data and all(
        value is None
        for value in (intake_path, markdown_path, script_path, icc_evidence_path)
    ):
        return {}
    post_install = dict_or_empty(data.get("post_install_verification"))
    commands = [
        command for command in list_or_empty(post_install.get("commands"))
        if isinstance(command, dict)
    ]
    capture_queue_commands = [
        command for command in commands
        if command.get("kind") == "capture_queue"
    ]
    capture_queue = capture_queue_commands[0] if capture_queue_commands else {}
    discovery_meta = dict_or_empty(data.get("discovery_metadata"))
    candidate_discovery = dict_or_empty(data.get("candidate_discovery"))
    if not candidate_discovery.get("shell_command"):
        current_root = data.get("current_asset_root")
        publication_pack = post_install.get("publication_pack")
        if isinstance(current_root, str) and current_root:
            candidate_discovery = (
                qge_registered_asset_intake.build_candidate_discovery_command(
                    Path(current_root),
                    publication_pack_dir=(
                        Path(publication_pack)
                        if isinstance(publication_pack, str) and publication_pack
                        else None
                    ),
                )
            )
    return {
        "registered_asset_intake_status": data.get("status"),
        "registered_asset_intake_file": (
            str(intake_path) if intake_path is not None else None),
        "registered_asset_intake_markdown_file": (
            str(markdown_path) if markdown_path is not None else None),
        "registered_asset_install_script": (
            str(script_path) if script_path is not None else None),
        "registered_asset_intake_icc_evidence_file": (
            str(icc_evidence_path) if icc_evidence_path is not None else None),
        "candidate_new_map_count": data.get("candidate_new_map_count"),
        "candidate_new_maps": data.get("candidate_new_maps"),
        "missing_map_count_after_plan": data.get(
            "missing_map_count_after_plan"),
        "missing_maps_after_plan": data.get("missing_maps_after_plan"),
        "manual_registered_asset_required": data.get(
            "manual_registered_asset_required"),
        "registered_asset_blocker_reason": data.get(
            "registered_asset_blocker_reason"),
        "copy_script_mode": data.get("copy_script_mode"),
        "no_candidate_asset_copy_plan": data.get(
            "no_candidate_asset_copy_plan"),
        "copy_plan_count": data.get("copy_plan_count"),
        "discovered_candidate_count": data.get(
            "discovered_candidate_count", 0),
        "discovery_roots_scanned_count": discovery_meta.get(
            "roots_scanned_count", 0),
        "steam_library_root_count": discovery_meta.get(
            "steam_library_root_count", 0),
        "steam_quake_path_count": discovery_meta.get(
            "steam_quake_path_count", 0),
        "registered_asset_discovery_command_present": bool(
            candidate_discovery.get("shell_command")),
        "registered_asset_discovery_command": candidate_discovery.get(
            "shell_command"),
        "registered_asset_discovery_json": candidate_discovery.get("json"),
        "registered_asset_discovery_markdown": candidate_discovery.get(
            "markdown"),
        "registered_asset_discovery_script": candidate_discovery.get("script"),
        "registered_asset_discovery_icc_evidence": candidate_discovery.get(
            "icc_json"),
        "post_install_verification_command_count": data.get(
            "post_install_verification_command_count",
            post_install.get("command_count"),
        ),
        "post_install_capture_queue_command_present": bool(
            capture_queue_commands),
        "post_install_capture_queue_command": capture_queue.get(
            "shell_command"),
        "post_install_capture_queue_json": capture_queue.get("json"),
        "post_install_capture_queue_script": capture_queue.get("script"),
        "post_install_capture_queue_markdown": capture_queue.get("markdown"),
        "asset_intake_copies_game_data": (
            dict_or_empty(data.get("claim_posture")).get(
                "asset_intake_copies_game_data", False)
        ),
    }


def asset_remediation_from_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    resource_artifacts = dict_or_empty(
        dict_or_empty(manifest.get("artifacts")).get("resource"))
    intake = qge_moonlab_full_game_plan.load_resource_json(
        manifest,
        "registered_asset_intake",
        manifest_path=manifest_path,
    )
    return asset_remediation_from_intake(
        intake,
        intake_path=artifact_path(resource_artifacts, "registered_asset_intake"),
        markdown_path=artifact_path(
            resource_artifacts, "registered_asset_intake_markdown"),
        script_path=artifact_path(
            resource_artifacts, "registered_asset_intake_script"),
        icc_evidence_path=artifact_path(
            resource_artifacts, "registered_asset_intake_icc_evidence"),
    )


def criterion(
    criterion_id: str,
    passed: bool,
    summary: dict[str, Any],
    blocker: str,
) -> dict[str, Any]:
    return {
        "id": criterion_id,
        "status": PASS if passed else FAIL,
        "blocker": None if passed else blocker,
        **summary,
    }


def failed_criteria(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in criteria
        if isinstance(item, dict) and item.get("status") != PASS
    ]


def overclaim_flags_from_mapping(
    prefix: str,
    data: dict[str, Any],
    keys: Sequence[str],
) -> list[dict[str, Any]]:
    flags = []
    for key in keys:
        if data.get(key) is True:
            flags.append({"source": prefix, "flag": key, "value": True})
    posture = dict_or_empty(data.get("claim_posture"))
    for key in keys:
        if posture.get(key) is True:
            flags.append({
                "source": f"{prefix}.claim_posture",
                "flag": key,
                "value": True,
            })
    posture = dict_or_empty(data.get("posture"))
    for key in keys:
        if posture.get(key) is True:
            flags.append({
                "source": f"{prefix}.posture",
                "flag": key,
                "value": True,
            })
    return flags


def overclaim_flags(
    *,
    resource_envelope: dict[str, Any] | None = None,
    asset_requirements: dict[str, Any] | None = None,
    full_game_plan: dict[str, Any] | None = None,
    job_specs: dict[str, Any] | None = None,
    job_results: dict[str, Any] | None = None,
    submission_packet: dict[str, Any] | None = None,
    hardware_record_template: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    forbidden = (
        "whole_game_hardware_execution_claimed",
        "hardware_quantum_advantage_claimed",
        "dense_70000_qubit_state_claimed",
    )
    sources = (
        ("resource_envelope", dict_or_empty(resource_envelope)),
        ("asset_requirements", dict_or_empty(asset_requirements)),
        ("moonlab_full_game_plan", dict_or_empty(full_game_plan)),
        ("moonlab_job_specs", dict_or_empty(job_specs)),
        ("moonlab_job_results", dict_or_empty(job_results)),
        ("moonlab_submission_packet", dict_or_empty(submission_packet)),
        ("moonlab_hardware_record_template", dict_or_empty(hardware_record_template)),
        (
            "moonlab_hardware_record_template.record",
            dict_or_empty(dict_or_empty(hardware_record_template).get("record")),
        ),
    )
    flags: list[dict[str, Any]] = []
    for prefix, source in sources:
        flags.extend(overclaim_flags_from_mapping(prefix, source, forbidden))
    for index, job in enumerate(list_or_empty(dict_or_empty(job_results).get("jobs"))):
        if isinstance(job, dict):
            flags.extend(overclaim_flags_from_mapping(
                f"moonlab_job_results.jobs[{index}]", job, forbidden))
    for index, job in enumerate(list_or_empty(
        dict_or_empty(submission_packet).get("candidate_jobs"))):
        if isinstance(job, dict):
            flags.extend(overclaim_flags_from_mapping(
                f"moonlab_submission_packet.candidate_jobs[{index}]",
                job,
                forbidden,
            ))
    return flags


def gate_summary(
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    requirements: dict[str, Any],
    full_game_plan: dict[str, Any],
    job_specs: dict[str, Any],
    job_results: dict[str, Any],
    submission_packet: dict[str, Any],
    asset_remediation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    remediation = dict_or_empty(asset_remediation)
    return {
        "map_set": coverage.get("map_set") or inventory.get("map_set"),
        "coverage_status": coverage.get("status"),
        "target_map_count": coverage.get("target_map_count"),
        "covered_map_count": coverage.get("covered_map_count"),
        "coverage_missing_map_count": coverage.get("missing_map_count"),
        "coverage_missing_maps": coverage.get("missing_maps"),
        "asset_inventory_status": inventory.get("status"),
        "asset_available_map_count": inventory.get("available_map_count"),
        "asset_missing_map_count": inventory.get("missing_map_count"),
        "asset_missing_maps": inventory.get("missing_maps"),
        "invalid_pak_count": inventory.get("invalid_pak_count"),
        "invalid_bsp_count": inventory.get("invalid_bsp_count"),
        "asset_requirements_status": requirements.get("status"),
        "asset_requirements_missing_map_count": requirements.get(
            "missing_map_count"),
        "asset_requirements_missing_maps": requirements.get("missing_maps"),
        "moonlab_full_game_plan_status": full_game_plan.get("status"),
        "route_contract_schema": full_game_plan.get("route_contract_schema"),
        "route_contract_map_count": full_game_plan.get(
            "route_contract_map_count"),
        "route_contracts_complete": full_game_plan.get(
            "route_contracts_complete"),
        "missing_route_contract_maps": full_game_plan.get(
            "missing_route_contract_maps"),
        "capture_required_map_count": full_game_plan.get(
            "capture_required_map_count"),
        "capture_required_maps": full_game_plan.get("capture_required_maps"),
        "asset_unavailable_map_count": full_game_plan.get(
            "asset_unavailable_map_count"),
        "asset_unavailable_maps": full_game_plan.get("asset_unavailable_maps"),
        "selected_job_count": job_specs.get("selected_job_count"),
        "result_selected_job_count": job_results.get("selected_job_count"),
        "completed_simulator_job_count": job_results.get(
            "completed_simulator_job_count"),
        "completed_native_replay_job_count": job_results.get(
            "completed_native_replay_job_count"),
        "blocked_job_count": job_results.get("blocked_job_count"),
        "hardware_candidate_job_count": job_results.get(
            "hardware_candidate_job_count",
            job_specs.get("hardware_candidate_job_count"),
        ),
        "hardware_submitted_job_count": job_results.get(
            "hardware_submitted_job_count"),
        "ready_hardware_candidate_count": submission_packet.get(
            "ready_candidate_count"),
        "registered_asset_intake_status": remediation.get(
            "registered_asset_intake_status"),
        "registered_asset_install_script": remediation.get(
            "registered_asset_install_script"),
        "registered_asset_intake_file": remediation.get(
            "registered_asset_intake_file"),
        "registered_asset_intake_markdown_file": remediation.get(
            "registered_asset_intake_markdown_file"),
        "registered_asset_intake_icc_evidence_file": remediation.get(
            "registered_asset_intake_icc_evidence_file"),
        "registered_asset_intake_missing_map_count_after_plan": (
            remediation.get("missing_map_count_after_plan")),
        "registered_asset_intake_manual_asset_required": remediation.get(
            "manual_registered_asset_required"),
        "registered_asset_intake_blocker_reason": remediation.get(
            "registered_asset_blocker_reason"),
        "registered_asset_intake_copy_script_mode": remediation.get(
            "copy_script_mode"),
        "registered_asset_intake_no_candidate_asset_copy_plan": (
            remediation.get("no_candidate_asset_copy_plan")),
        "registered_asset_intake_copy_plan_count": remediation.get(
            "copy_plan_count"),
        "registered_asset_intake_candidate_new_map_count": remediation.get(
            "candidate_new_map_count"),
        "registered_asset_intake_discovered_candidate_count": remediation.get(
            "discovered_candidate_count"),
        "registered_asset_intake_discovery_roots_scanned_count": (
            remediation.get("discovery_roots_scanned_count")),
        "registered_asset_intake_steam_library_root_count": remediation.get(
            "steam_library_root_count"),
        "registered_asset_intake_steam_quake_path_count": remediation.get(
            "steam_quake_path_count"),
        "registered_asset_discovery_command_present": remediation.get(
            "registered_asset_discovery_command_present"),
        "registered_asset_discovery_command": remediation.get(
            "registered_asset_discovery_command"),
        "registered_asset_discovery_script": remediation.get(
            "registered_asset_discovery_script"),
        "post_install_verification_command_count": remediation.get(
            "post_install_verification_command_count"),
        "post_install_capture_queue_command_present": remediation.get(
            "post_install_capture_queue_command_present"),
        "post_install_capture_queue_command": remediation.get(
            "post_install_capture_queue_command"),
        "post_install_capture_queue_script": remediation.get(
            "post_install_capture_queue_script"),
    }


def build_criteria(
    *,
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    requirements: dict[str, Any],
    full_game_plan: dict[str, Any],
    job_specs: dict[str, Any],
    job_results: dict[str, Any],
    resource_envelope: dict[str, Any] | None = None,
    submission_packet: dict[str, Any] | None = None,
    hardware_record_template: dict[str, Any] | None = None,
    asset_remediation: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    target_count = int_or_none(coverage.get("target_map_count"))
    covered_count = int_or_none(coverage.get("covered_map_count"))
    coverage_missing = int_or_none(coverage.get("missing_map_count"))
    coverage_passed = (
        coverage.get("schema") == "qge.full_game_map_coverage.v0" and
        coverage.get("status") == "complete" and
        target_count is not None and
        covered_count == target_count and
        coverage_missing == 0
    )

    inventory_missing = int_or_none(inventory.get("missing_map_count"))
    invalid_pak_count = int_or_none(inventory.get("invalid_pak_count"))
    invalid_bsp_count = int_or_none(inventory.get("invalid_bsp_count"))
    inventory_passed = (
        inventory.get("schema") == "qge.asset_inventory.v0" and
        bool_true(inventory.get("full_game_asset_ready")) and
        inventory_missing == 0 and
        invalid_pak_count == 0 and
        invalid_bsp_count == 0
    )

    requirement_missing = int_or_none(requirements.get("missing_map_count"))
    requirement_posture = dict_or_empty(requirements.get("claim_posture"))
    requirements_passed = (
        requirements.get("schema") == "qge.asset_requirements.v0" and
        requirements.get("status") == "complete" and
        requirement_missing == 0 and
        requirement_posture.get("asset_requirements_satisfied") is True
    )

    capture_required = int_or_none(full_game_plan.get(
        "capture_required_map_count"))
    asset_unavailable = int_or_none(full_game_plan.get(
        "asset_unavailable_map_count"))
    plan_target_count = int_or_none(full_game_plan.get("target_map_count"))
    expected_route_contract_count = (
        target_count if target_count is not None else plan_target_count
    )
    route_contract_count = int_or_none(full_game_plan.get(
        "route_contract_map_count"))
    missing_route_contract_maps = list_or_empty(full_game_plan.get(
        "missing_route_contract_maps"))
    route_contracts_passed = (
        full_game_plan.get("route_contract_schema") ==
        qge_full_game_capture_queue.ROUTE_CONTRACT_SCHEMA and
        bool_true(full_game_plan.get("route_contracts_complete")) and
        expected_route_contract_count is not None and
        route_contract_count == expected_route_contract_count and
        not missing_route_contract_maps
    )
    plan_passed = (
        full_game_plan.get("schema") ==
        "qge.moonlab_full_game_deployment_plan.v0" and
        full_game_plan.get("status") == "map_coverage_complete" and
        route_contracts_passed and
        capture_required == 0 and
        asset_unavailable == 0
    )

    selected_count = int_or_none(job_specs.get("selected_job_count"))
    result_selected_count = int_or_none(job_results.get("selected_job_count"))
    completed_simulator = int_or_none(job_results.get(
        "completed_simulator_job_count"))
    blocked_jobs = int_or_none(job_results.get("blocked_job_count"))
    jobs_passed = (
        job_specs.get("schema") == "qge.moonlab_job_specs.v0" and
        job_results.get("schema") == "qge.moonlab_job_results.v0" and
        selected_count is not None and selected_count > 0 and
        result_selected_count == selected_count and
        completed_simulator is not None and
        completed_simulator >= selected_count and
        blocked_jobs == 0 and
        job_results.get("overall_status") in (
            "completed",
            "simulator_complete_hardware_not_submitted",
        )
    )

    overclaims = overclaim_flags(
        resource_envelope=resource_envelope,
        asset_requirements=requirements,
        full_game_plan=full_game_plan,
        job_specs=job_specs,
        job_results=job_results,
        submission_packet=submission_packet,
        hardware_record_template=hardware_record_template,
    )
    remediation = dict_or_empty(asset_remediation)

    return [
        criterion(
            "full_game_map_coverage_complete",
            coverage_passed,
            {
                "coverage_status": coverage.get("status"),
                "target_map_count": target_count,
                "covered_map_count": covered_count,
                "missing_map_count": coverage_missing,
                "missing_maps": coverage.get("missing_maps"),
            },
            "canonical map coverage is not complete",
        ),
        criterion(
            "registered_bsp_assets_ready",
            inventory_passed,
            {
                "asset_inventory_status": inventory.get("status"),
                "full_game_asset_ready": inventory.get("full_game_asset_ready"),
                "missing_map_count": inventory_missing,
                "missing_maps": inventory.get("missing_maps"),
                "invalid_pak_count": invalid_pak_count,
                "invalid_bsp_count": invalid_bsp_count,
                "registered_asset_install_script": remediation.get(
                    "registered_asset_install_script"),
                "registered_asset_intake_file": remediation.get(
                    "registered_asset_intake_file"),
                "post_install_capture_queue_command": remediation.get(
                    "post_install_capture_queue_command"),
            },
            "registered BSP assets are missing or invalid",
        ),
        criterion(
            "asset_requirements_satisfied",
            requirements_passed,
            {
                "asset_requirements_status": requirements.get("status"),
                "missing_map_count": requirement_missing,
                "missing_maps": requirements.get("missing_maps"),
                "asset_requirements_satisfied": requirement_posture.get(
                    "asset_requirements_satisfied"),
                "registered_asset_intake_status": remediation.get(
                    "registered_asset_intake_status"),
                "registered_asset_intake_missing_map_count_after_plan": (
                    remediation.get("missing_map_count_after_plan")),
                "registered_asset_install_script": remediation.get(
                    "registered_asset_install_script"),
            },
            "registered asset requirements are not satisfied",
        ),
        criterion(
            "full_game_route_contracts_complete",
            route_contracts_passed,
            {
                "route_contract_schema": full_game_plan.get(
                    "route_contract_schema"),
                "route_contract_map_count": route_contract_count,
                "target_map_count": expected_route_contract_count,
                "route_contracts_complete": full_game_plan.get(
                    "route_contracts_complete"),
                "missing_route_contract_maps": missing_route_contract_maps,
            },
            "full-game route contract ledger is missing or incomplete",
        ),
        criterion(
            "full_game_deployment_plan_complete",
            plan_passed,
            {
                "deployment_plan_status": full_game_plan.get("status"),
                "capture_required_map_count": capture_required,
                "capture_required_maps": full_game_plan.get(
                    "capture_required_maps"),
                "asset_unavailable_map_count": asset_unavailable,
                "asset_unavailable_maps": full_game_plan.get(
                    "asset_unavailable_maps"),
                "post_install_capture_queue_command": remediation.get(
                    "post_install_capture_queue_command"),
                "post_install_capture_queue_script": remediation.get(
                    "post_install_capture_queue_script"),
            },
            "full-game deployment plan still has capture or asset blockers",
        ),
        criterion(
            "moonlab_selected_jobs_unblocked",
            jobs_passed,
            {
                "selected_job_count": selected_count,
                "result_selected_job_count": result_selected_count,
                "completed_simulator_job_count": completed_simulator,
                "blocked_job_count": blocked_jobs,
                "overall_status": job_results.get("overall_status"),
            },
            "selected Moonlab simulator/native jobs are not fully replayable",
        ),
        criterion(
            "no_forbidden_hardware_or_advantage_overclaim",
            not overclaims,
            {"overclaim_flags": overclaims},
            "a source artifact contains a forbidden hardware, advantage, or dense-state claim flag",
        ),
    ]


def next_actions_for_blockers(
    blockers: list[dict[str, Any]],
    *,
    asset_remediation: dict[str, Any] | None = None,
) -> list[str]:
    actions: list[str] = []
    failed_ids = {
        blocker.get("id")
        for blocker in blockers
        if isinstance(blocker.get("id"), str)
    }
    remediation = dict_or_empty(asset_remediation)
    install_script = remediation.get("registered_asset_install_script")
    discovery_command = remediation.get("registered_asset_discovery_command")
    queue_command = remediation.get("post_install_capture_queue_command")
    if "registered_bsp_assets_ready" in failed_ids:
        if remediation.get("no_candidate_asset_copy_plan") is True:
            actions.append(
                "No registered asset copy plan exists yet; install or link "
                "licensed registered Quake PAK/BSP assets, then rerun the "
                "discovery refresh command."
            )
        if discovery_command:
            actions.append(
                "Run the registered asset discovery refresh command after installing or linking licensed Quake assets: "
                f"{discovery_command}"
            )
        if install_script:
            actions.append(
                f"Run {install_script} after placing licensed registered Quake assets where the intake ledger expects them."
            )
        else:
            actions.append(
                "Install registered Quake BSP assets and rerun qge_asset_inventory.py plus qge_asset_requirements.py."
            )
    if "full_game_map_coverage_complete" in failed_ids:
        actions.append(
            "Capture every missing canonical map with the strict QGE/vanilla harness and rebuild breadth evidence."
        )
    if "asset_requirements_satisfied" in failed_ids:
        actions.append(
            "Resolve every missing maps/*.bsp entry listed by qge_asset_requirements.json before weakening no-claim posture."
        )
    if "full_game_route_contracts_complete" in failed_ids:
        actions.append(
            "Regenerate qge_moonlab_full_game_plan.json so every canonical map has a full-game route contract before claiming Moonlab deployment readiness."
        )
    if "full_game_deployment_plan_complete" in failed_ids:
        if queue_command:
            actions.append(
                f"After asset installation, run the post-install capture queue command: {queue_command}"
            )
        else:
            actions.append(
                "Regenerate qge_moonlab_full_game_plan.json after assets and captures are complete."
            )
    if "moonlab_selected_jobs_unblocked" in failed_ids:
        actions.append(
            "Rerun qge_moonlab_job_runner.py with --expect so selected simulator/native jobs match the packed evidence."
        )
    if "no_forbidden_hardware_or_advantage_overclaim" in failed_ids:
        actions.append(
            "Remove hardware, advantage, or dense-state claim flags from source artifacts and ingest hardware results only through qge_moonlab_hardware_ingest.py."
        )
    return actions or [
        "The simulator/native full-game deployment claim gate is ready; hardware and advantage claims still require separate Moonlab hardware records."
    ]


def build_gate(
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    requirements: dict[str, Any],
    full_game_plan: dict[str, Any],
    job_specs: dict[str, Any],
    job_results: dict[str, Any],
    submission_packet: dict[str, Any],
    hardware_record_template: dict[str, Any],
    *,
    resource_envelope: dict[str, Any] | None = None,
    asset_remediation: dict[str, Any] | None = None,
    source_path: Path | str | None = None,
) -> dict[str, Any]:
    criteria = build_criteria(
        coverage=coverage,
        inventory=inventory,
        requirements=requirements,
        full_game_plan=full_game_plan,
        job_specs=job_specs,
        job_results=job_results,
        resource_envelope=resource_envelope,
        submission_packet=submission_packet,
        hardware_record_template=hardware_record_template,
        asset_remediation=asset_remediation,
    )
    blockers = failed_criteria(criteria)
    simulator_claim_allowed = not blockers
    hardware_submitted = int_or_none(job_results.get(
        "hardware_submitted_job_count")) or 0
    return {
        "schema": "qge.moonlab_deployment_gate.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path) if source_path is not None else None,
        "status": (
            "ready_for_moonlab_simulator_deployment_claim"
            if simulator_claim_allowed else "blocked"
        ),
        "hardware_status": (
            "hardware_records_present_no_full_game_hardware_claim"
            if hardware_submitted > 0 else "not_submitted"
        ),
        "whole_game_moonlab_deployment_claim_allowed": (
            simulator_claim_allowed),
        "whole_game_hardware_execution_claim_allowed": False,
        "hardware_quantum_advantage_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "failed_criterion_count": len(blockers),
        "blocker_count": len(blockers),
        "criteria": criteria,
        "blockers": blockers,
        "asset_remediation": dict_or_empty(asset_remediation),
        "summary": gate_summary(
            coverage,
            inventory,
            requirements,
            full_game_plan,
            job_specs,
            job_results,
            submission_packet,
            asset_remediation,
        ),
        "next_actions": next_actions_for_blockers(
            blockers,
            asset_remediation=asset_remediation,
        ),
        "limits": [
            "This gate is an eligibility verdict; it is not proof by itself that the whole game runs in Moonlab.",
            "A simulator/native deployment claim requires this gate to be ready and the cited artifacts to be published with it.",
            "Whole-game hardware execution and hardware quantum advantage remain false until separate Moonlab hardware records satisfy their own gates.",
            "Dense 70,000-qubit state-vector claims are forbidden for this project posture.",
        ],
    }


def build_gate_from_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
    asset_root: Path = qge_asset_inventory.DEFAULT_ASSET_ROOT,
) -> dict[str, Any]:
    coverage = qge_moonlab_full_game_plan.coverage_from_manifest(
        manifest, manifest_path=manifest_path)
    inventory = qge_moonlab_full_game_plan.asset_inventory_from_manifest(
        manifest,
        manifest_path=manifest_path,
        asset_root=asset_root,
        map_set=coverage.get("map_set")
        or qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET,
    )
    requirements = qge_moonlab_full_game_plan.load_resource_json(
        manifest, "asset_requirements", manifest_path=manifest_path)
    if requirements is None:
        requirements = qge_asset_requirements.build_requirements(
            inventory,
            map_set=str(
                coverage.get("map_set")
                or qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET
            ),
        )
    full_game_plan = qge_moonlab_full_game_plan.load_resource_json(
        manifest, "moonlab_full_game_plan", manifest_path=manifest_path)
    if full_game_plan is None:
        full_game_plan = qge_moonlab_full_game_plan.build_plan_from_manifest(
            manifest,
            manifest_path=manifest_path,
            asset_root=asset_root,
        )
    job_specs = qge_moonlab_full_game_plan.load_resource_json(
        manifest, "moonlab_job_specs", manifest_path=manifest_path) or {}
    job_results = qge_moonlab_full_game_plan.load_resource_json(
        manifest, "moonlab_job_results", manifest_path=manifest_path) or {}
    submission_packet = qge_moonlab_full_game_plan.load_resource_json(
        manifest, "moonlab_submission_packet", manifest_path=manifest_path) or {}
    hardware_record_template = qge_moonlab_full_game_plan.load_resource_json(
        manifest,
        "moonlab_hardware_record_template",
        manifest_path=manifest_path,
    ) or {}
    resource_envelope = qge_moonlab_full_game_plan.load_resource_json(
        manifest, "envelope", manifest_path=manifest_path) or {}
    asset_remediation = asset_remediation_from_manifest(
        manifest,
        manifest_path=manifest_path,
    )
    return build_gate(
        coverage,
        inventory,
        requirements,
        full_game_plan,
        job_specs,
        job_results,
        submission_packet,
        hardware_record_template,
        resource_envelope=resource_envelope,
        asset_remediation=asset_remediation,
        source_path=manifest_path,
    )


def build_icc_evidence(
    gate: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    summary = dict_or_empty(gate.get("summary"))
    claim_allowed = gate.get("whole_game_moonlab_deployment_claim_allowed")
    completion_reason = "qge_moonlab_deployment_gate_blocked"
    if claim_allowed is True:
        completion_reason = "qge_moonlab_deployment_gate_ready"
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_moonlab_deployment_gate",
        "completion_reason": completion_reason,
        "moonlab_deployment_gate_file": str(out_path) if out_path else None,
        "status": "success",
        "gate_status": gate.get("status"),
        "failed_criterion_count": gate.get("failed_criterion_count"),
        "blocker_count": gate.get("blocker_count"),
        "map_set": summary.get("map_set"),
        "target_map_count": summary.get("target_map_count"),
        "covered_map_count": summary.get("covered_map_count"),
        "coverage_missing_map_count": summary.get("coverage_missing_map_count"),
        "asset_missing_map_count": summary.get("asset_missing_map_count"),
        "invalid_pak_count": summary.get("invalid_pak_count"),
        "invalid_bsp_count": summary.get("invalid_bsp_count"),
        "asset_requirements_missing_map_count": summary.get(
            "asset_requirements_missing_map_count"),
        "registered_asset_intake_status": summary.get(
            "registered_asset_intake_status"),
        "registered_asset_intake_file": summary.get(
            "registered_asset_intake_file"),
        "registered_asset_intake_markdown_file": summary.get(
            "registered_asset_intake_markdown_file"),
        "registered_asset_install_script": summary.get(
            "registered_asset_install_script"),
        "registered_asset_intake_icc_evidence_file": summary.get(
            "registered_asset_intake_icc_evidence_file"),
        "registered_asset_intake_missing_map_count_after_plan": summary.get(
            "registered_asset_intake_missing_map_count_after_plan"),
        "registered_asset_intake_manual_asset_required": summary.get(
            "registered_asset_intake_manual_asset_required"),
        "registered_asset_intake_blocker_reason": summary.get(
            "registered_asset_intake_blocker_reason"),
        "registered_asset_intake_copy_script_mode": summary.get(
            "registered_asset_intake_copy_script_mode"),
        "registered_asset_intake_no_candidate_asset_copy_plan": summary.get(
            "registered_asset_intake_no_candidate_asset_copy_plan"),
        "registered_asset_intake_copy_plan_count": summary.get(
            "registered_asset_intake_copy_plan_count"),
        "registered_asset_intake_candidate_new_map_count": summary.get(
            "registered_asset_intake_candidate_new_map_count"),
        "registered_asset_intake_discovered_candidate_count": summary.get(
            "registered_asset_intake_discovered_candidate_count"),
        "registered_asset_intake_discovery_roots_scanned_count": summary.get(
            "registered_asset_intake_discovery_roots_scanned_count"),
        "registered_asset_intake_steam_library_root_count": summary.get(
            "registered_asset_intake_steam_library_root_count"),
        "registered_asset_intake_steam_quake_path_count": summary.get(
            "registered_asset_intake_steam_quake_path_count"),
        "registered_asset_discovery_command_present": summary.get(
            "registered_asset_discovery_command_present"),
        "registered_asset_discovery_command": summary.get(
            "registered_asset_discovery_command"),
        "registered_asset_discovery_script": summary.get(
            "registered_asset_discovery_script"),
        "post_install_verification_command_count": summary.get(
            "post_install_verification_command_count"),
        "post_install_capture_queue_command_present": summary.get(
            "post_install_capture_queue_command_present"),
        "post_install_capture_queue_command": summary.get(
            "post_install_capture_queue_command"),
        "post_install_capture_queue_script": summary.get(
            "post_install_capture_queue_script"),
        "capture_required_map_count": summary.get(
            "capture_required_map_count"),
        "asset_unavailable_map_count": summary.get(
            "asset_unavailable_map_count"),
        "full_game_route_contract_schema": summary.get(
            "route_contract_schema"),
        "full_game_route_contract_map_count": summary.get(
            "route_contract_map_count"),
        "full_game_route_contracts_complete": summary.get(
            "route_contracts_complete"),
        "full_game_missing_route_contract_maps": summary.get(
            "missing_route_contract_maps"),
        "selected_job_count": summary.get("selected_job_count"),
        "completed_simulator_job_count": summary.get(
            "completed_simulator_job_count"),
        "blocked_job_count": summary.get("blocked_job_count"),
        "hardware_submitted_job_count": summary.get(
            "hardware_submitted_job_count"),
        "whole_game_moonlab_deployment_claim_allowed": gate.get(
            "whole_game_moonlab_deployment_claim_allowed"),
        "whole_game_hardware_execution_claim_allowed": gate.get(
            "whole_game_hardware_execution_claim_allowed"),
        "hardware_quantum_advantage_claim_allowed": gate.get(
            "hardware_quantum_advantage_claim_allowed"),
        "dense_70000_qubit_state_claim_allowed": gate.get(
            "dense_70000_qubit_state_claim_allowed"),
    }


def markdown_report(gate: dict[str, Any]) -> str:
    summary = dict_or_empty(gate.get("summary"))
    lines = [
        "# QGE Moonlab Deployment Gate",
        "",
        f"Status: {gate.get('status')}",
        "",
        "| Claim | Allowed |",
        "| --- | ---: |",
        (
            "| whole-game Moonlab simulator/native deployment | "
            f"{str(gate.get('whole_game_moonlab_deployment_claim_allowed')).lower()} |"
        ),
        (
            "| whole-game hardware execution | "
            f"{str(gate.get('whole_game_hardware_execution_claim_allowed')).lower()} |"
        ),
        (
            "| hardware quantum advantage | "
            f"{str(gate.get('hardware_quantum_advantage_claim_allowed')).lower()} |"
        ),
        (
            "| dense 70,000-qubit state | "
            f"{str(gate.get('dense_70000_qubit_state_claim_allowed')).lower()} |"
        ),
        "",
        "| Map Set | Covered | Missing | Asset Missing | Invalid BSP |",
        "| --- | ---: | ---: | ---: | ---: |",
        (
            f"| {summary.get('map_set')} | "
            f"{summary.get('covered_map_count')} / {summary.get('target_map_count')} | "
            f"{summary.get('coverage_missing_map_count')} | "
            f"{summary.get('asset_missing_map_count')} | "
            f"{summary.get('invalid_bsp_count')} |"
        ),
        "",
        (
            f"Route contracts: {summary.get('route_contract_map_count')} "
            f"(complete={summary.get('route_contracts_complete')})"
        ),
        "",
        "| Criterion | Status | Blocker |",
        "| --- | --- | --- |",
    ]
    for item in list_or_empty(gate.get("criteria")):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| {item.get('id')} | {item.get('status')} | "
            f"{item.get('blocker') or ''} |"
        )
    lines.extend(["", "## Next Actions", ""])
    for action in list_or_empty(gate.get("next_actions")):
        lines.append(f"- {action}")
    remediation = dict_or_empty(gate.get("asset_remediation"))
    if remediation:
        lines.extend([
            "",
            "## Asset Remediation",
            "",
            "| Artifact | Path / Command |",
            "| --- | --- |",
            (
                "| intake JSON | "
                f"`{remediation.get('registered_asset_intake_file') or ''}` |"
            ),
            (
                "| intake Markdown | "
                f"`{remediation.get('registered_asset_intake_markdown_file') or ''}` |"
            ),
            (
                "| install script | "
                f"`{remediation.get('registered_asset_install_script') or ''}` |"
            ),
            (
                "| copy script mode | "
                f"`{remediation.get('copy_script_mode') or ''}` |"
            ),
            (
                "| manual assets required | "
                f"`{remediation.get('manual_registered_asset_required')}` |"
            ),
            (
                "| blocker reason | "
                f"`{remediation.get('registered_asset_blocker_reason') or ''}` |"
            ),
            (
                "| discovery roots scanned | "
                f"`{remediation.get('discovery_roots_scanned_count', 0)}` |"
            ),
            (
                "| Steam Quake candidate paths | "
                f"`{remediation.get('steam_quake_path_count', 0)}` |"
            ),
            (
                "| discovery refresh | "
                f"`{remediation.get('registered_asset_discovery_command') or ''}` |"
            ),
            (
                "| post-install queue | "
                f"`{remediation.get('post_install_capture_queue_command') or ''}` |"
            ),
        ])
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("publication_pack", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    parser.add_argument("--asset-root", type=Path,
                        default=qge_asset_inventory.DEFAULT_ASSET_ROOT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest_path = qge_moonlab_full_game_plan.resolve_publication_manifest(
            args.publication_pack)
        manifest = load_json(manifest_path)
        if manifest.get("schema") != "qge.publication_pack.v0":
            raise ValueError("input is not qge.publication_pack.v0")
        gate = build_gate_from_manifest(
            manifest,
            manifest_path=manifest_path,
            asset_root=args.asset_root,
        )
        write_json(args.out, gate)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(gate), encoding="utf-8")
        if args.icc_json:
            icc = build_icc_evidence(gate, out_path=args.out)
            write_json(args.icc_json, icc)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_moonlab_deployment_gate: {exc}", file=sys.stderr)
        return 1

    print(f"QGE_MOONLAB_DEPLOYMENT_GATE {args.out}")
    if args.markdown:
        print(f"QGE_MOONLAB_DEPLOYMENT_GATE_MARKDOWN {args.markdown}")
    if args.icc_json:
        print(f"QGE_MOONLAB_DEPLOYMENT_GATE_ICC_EVIDENCE {args.icc_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
