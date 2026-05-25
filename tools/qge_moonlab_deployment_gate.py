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
import qge_full_game_route_contracts  # noqa: E402
import qge_moonlab_hardware_result_audit  # noqa: E402
import qge_moonlab_hardware_scope_audit  # noqa: E402
import qge_moonlab_hardware_template_audit  # noqa: E402
import qge_moonlab_full_game_plan_audit  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402
import qge_moonlab_overclaim_audit  # noqa: E402
import qge_moonlab_submission_packet_audit  # noqa: E402
import qge_registered_asset_intake  # noqa: E402


PASS = "pass"
BLOCKED = "blocked"
NON_SUBMITTED_HARDWARE_STATUSES = {
    None,
    "not_submitted",
    "not_a_quantum_hardware_job",
    "not_applicable_full_frame_hardware_execution_not_claimed",
}


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


def resource_artifact_manifest_path(
    manifest: dict[str, Any],
    name: str,
) -> str | None:
    resource = dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(
        "resource"))
    path = dict_or_empty(resource.get(name)).get("path")
    return path if isinstance(path, str) and path else None


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def string_list(value: Any) -> list[str]:
    return [item for item in list_or_empty(value) if isinstance(item, str)]


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
        "actionable_copy_plan_count": data.get(
            "actionable_copy_plan_count"),
        "copy_plan_unblocked_map_count": data.get(
            "copy_plan_unblocked_map_count"),
        "copy_plan_unblocked_maps": data.get(
            "copy_plan_unblocked_maps"),
        "copy_plan_blocked_map_count": data.get(
            "copy_plan_blocked_map_count"),
        "copy_plan_blocked_maps": data.get("copy_plan_blocked_maps"),
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
        "status": PASS if passed else BLOCKED,
        "blocker": None if passed else blocker,
        **summary,
    }


def failed_criteria(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in criteria
        if isinstance(item, dict) and item.get("status") != PASS
    ]


def asset_handoff_status_counts(full_game_plan: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in list_or_empty(full_game_plan.get("map_deployment_rows")):
        if not isinstance(row, dict):
            continue
        status = row.get("asset_handoff_status")
        if not isinstance(status, str) or not status:
            status = "not_recorded"
        counts[status] = counts.get(status, 0) + 1
    return counts


def handoff_consistency_mismatches(
    handoff: dict[str, Any],
    remediation: dict[str, Any],
) -> list[str]:
    pairs = [
        (
            "registered_asset_intake_status",
            "registered_asset_intake_status",
            "registered_asset_intake_status",
        ),
        (
            "registered_asset_blocker_reason",
            "registered_asset_blocker_reason",
            "registered_asset_blocker_reason",
        ),
        ("copy_script_mode", "copy_script_mode", "copy_script_mode"),
        (
            "missing_map_count_after_plan",
            "missing_map_count_after_plan",
            "missing_map_count_after_plan",
        ),
        (
            "actionable_copy_plan_count",
            "actionable_copy_plan_count",
            "actionable_copy_plan_count",
        ),
        (
            "copy_plan_unblocked_map_count",
            "copy_plan_unblocked_map_count",
            "copy_plan_unblocked_map_count",
        ),
        (
            "copy_plan_blocked_map_count",
            "copy_plan_blocked_map_count",
            "copy_plan_blocked_map_count",
        ),
    ]
    mismatches = []
    for label, handoff_key, remediation_key in pairs:
        remediation_value = remediation.get(remediation_key)
        if remediation_value is None:
            continue
        if handoff.get(handoff_key) != remediation_value:
            mismatches.append(label)
    list_pairs = [
        (
            "missing_maps_after_plan",
            "missing_maps_after_plan",
            "missing_maps_after_plan",
        ),
        (
            "copy_plan_unblocked_maps",
            "copy_plan_unblocked_maps",
            "copy_plan_unblocked_maps",
        ),
        (
            "copy_plan_blocked_maps",
            "copy_plan_blocked_maps",
            "copy_plan_blocked_maps",
        ),
    ]
    for label, handoff_key, remediation_key in list_pairs:
        remediation_values = remediation.get(remediation_key)
        if remediation_values is None:
            continue
        if string_list(handoff.get(handoff_key)) != string_list(
            remediation_values
        ):
            mismatches.append(label)
    return mismatches


def registered_asset_handoff_audit(
    full_game_plan: dict[str, Any],
    remediation: dict[str, Any],
    *,
    asset_unavailable: int | None,
) -> dict[str, Any]:
    handoff = dict_or_empty(full_game_plan.get("registered_asset_handoff"))
    remediation_present = bool(
        remediation.get("registered_asset_intake_status") or
        remediation.get("registered_asset_intake_file")
    )
    handoff_expected = (
        remediation_present or
        (asset_unavailable is not None and asset_unavailable > 0)
    )
    handoff_recorded = (
        handoff.get("schema") == "qge.moonlab_registered_asset_handoff.v0" and
        handoff.get("present") is True
    )
    mismatches = (
        handoff_consistency_mismatches(handoff, remediation)
        if handoff_recorded and remediation_present else
        []
    )
    status_counts = asset_handoff_status_counts(full_game_plan)
    return {
        "expected": handoff_expected,
        "recorded": handoff_recorded,
        "mismatches": mismatches,
        "passed": (
            not handoff_expected or
            (handoff_recorded and not mismatches)
        ),
        "status_counts": status_counts,
        "not_recorded_count": status_counts.get("not_recorded", 0),
        "licensed_asset_required_count": status_counts.get(
            "licensed_asset_required", 0),
        "copy_plan_unblocked_count": status_counts.get(
            "copy_plan_unblocked", 0),
        "copy_plan_blocked_count": status_counts.get(
            "copy_plan_blocked", 0),
    }


def first_job_by_domain(
    job_results: dict[str, Any],
    domain: str,
) -> dict[str, Any]:
    for job in list_or_empty(job_results.get("jobs")):
        if isinstance(job, dict) and job.get("domain") == domain:
            return job
    return {}


def backend_completed(job: dict[str, Any], backend_kind: str) -> bool:
    return any(
        isinstance(item, dict) and
        item.get("backend_kind") == backend_kind and
        item.get("status") == "completed"
        for item in list_or_empty(job.get("backend_results"))
    )


def job_id(job: dict[str, Any]) -> str | None:
    value = job.get("job_id")
    return value if isinstance(value, str) and value else None


def duplicate_strings(values: Sequence[str]) -> list[str]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted(value for value, count in counts.items() if count > 1)


def hardware_submission_recorded(status: Any) -> bool:
    if status is None:
        return False
    if isinstance(status, str):
        return status not in NON_SUBMITTED_HARDWARE_STATUSES
    return True


def result_job_blocked(job: dict[str, Any]) -> bool:
    status = job.get("result_status")
    return (
        bool(list_or_empty(job.get("missing_required_artifacts"))) or
        (isinstance(status, str) and status.startswith("blocked"))
    )


def artifact_evidence_by_name(
    result_job: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    indexed = {}
    for item in list_or_empty(result_job.get("artifact_evidence")):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name:
            indexed[name] = item
    return indexed


def job_artifact_evidence_audit(
    spec_job: dict[str, Any],
    result_job: dict[str, Any],
) -> dict[str, Any]:
    required = dict_or_empty(spec_job.get("required_artifacts"))
    evidence = artifact_evidence_by_name(result_job)
    expected_names = sorted(required.keys())
    evidence_names = sorted(evidence.keys())
    missing_names = sorted(set(expected_names) - set(evidence_names))
    unexpected_names = sorted(set(evidence_names) - set(expected_names))
    false_exists_names = []
    missing_digest_names = []
    zero_size_names = []
    path_mismatch_names = []
    for name in expected_names:
        item = evidence.get(name)
        if not item:
            continue
        expected_path = required.get(name)
        if item.get("exists") is not True:
            false_exists_names.append(name)
        if not isinstance(item.get("sha256"), str) or not item.get("sha256"):
            missing_digest_names.append(name)
        size_bytes = int_or_none(item.get("size_bytes"))
        if size_bytes is None or size_bytes <= 0:
            zero_size_names.append(name)
        if isinstance(expected_path, str) and item.get("path") != expected_path:
            path_mismatch_names.append(name)
    mismatch_names = sorted(set(
        missing_names +
        unexpected_names +
        false_exists_names +
        missing_digest_names +
        zero_size_names +
        path_mismatch_names
    ))
    return {
        "required_artifact_count": len(expected_names),
        "artifact_evidence_count": len(evidence_names),
        "missing_artifact_evidence_names": missing_names,
        "unexpected_artifact_evidence_names": unexpected_names,
        "artifact_exists_false_names": sorted(false_exists_names),
        "artifact_missing_digest_names": sorted(missing_digest_names),
        "artifact_zero_size_names": sorted(zero_size_names),
        "artifact_path_mismatch_names": sorted(path_mismatch_names),
        "artifact_evidence_mismatch_names": mismatch_names,
        "artifact_evidence_mismatch_count": len(mismatch_names),
        "passed": len(mismatch_names) == 0,
    }


def selected_job_result_ledger_audit(
    job_specs: dict[str, Any],
    job_results: dict[str, Any],
) -> dict[str, Any]:
    spec_jobs = [
        item for item in list_or_empty(job_specs.get("jobs"))
        if isinstance(item, dict)
    ]
    result_jobs = [
        item for item in list_or_empty(job_results.get("jobs"))
        if isinstance(item, dict)
    ]
    spec_ids = [item for item in (job_id(job) for job in spec_jobs) if item]
    result_ids = [
        item for item in (job_id(job) for job in result_jobs) if item
    ]
    duplicate_spec_ids = duplicate_strings(spec_ids)
    duplicate_result_ids = duplicate_strings(result_ids)
    missing_result_ids = sorted(set(spec_ids) - set(result_ids))
    unexpected_result_ids = sorted(set(result_ids) - set(spec_ids))
    invalid_spec_job_count = len(spec_jobs) - len(spec_ids)
    invalid_result_job_count = len(result_jobs) - len(result_ids)
    result_index = {
        item_id: job
        for item_id, job in (
            (job_id(job), job) for job in result_jobs
        )
        if item_id
    }

    completed_simulator_ids = [
        item for item in (
            job_id(job) for job in result_jobs
            if backend_completed(job, "moonlab_simulator")
        )
        if item
    ]
    non_completed_simulator_ids = [
        item for item in result_ids
        if item not in set(completed_simulator_ids)
    ]
    missing_artifact_ids = [
        item for item in (
            job_id(job) for job in result_jobs
            if list_or_empty(job.get("missing_required_artifacts"))
        )
        if item
    ]
    blocked_result_ids = [
        item for item in (
            job_id(job) for job in result_jobs
            if result_job_blocked(job)
        )
        if item
    ]

    spec_selected_count = int_or_none(job_specs.get("selected_job_count"))
    result_selected_count = int_or_none(job_results.get("selected_job_count"))
    reported_completed_simulator = int_or_none(
        job_results.get("completed_simulator_job_count"))
    reported_blocked = int_or_none(job_results.get("blocked_job_count"))
    reported_hardware_candidate = int_or_none(
        job_results.get("hardware_candidate_job_count"))
    reported_hardware_submitted = int_or_none(
        job_results.get("hardware_submitted_job_count"))

    spec_hardware_candidate_count = sum(
        1 for job in spec_jobs if job.get("hardware_candidate") is True
    )
    result_hardware_candidate_count = sum(
        1 for job in result_jobs if job.get("hardware_candidate") is True
    )
    spec_hardware_submitted_count = sum(
        1 for job in spec_jobs
        if hardware_submission_recorded(job.get("hardware_submission_status"))
    )
    result_hardware_submitted_count = sum(
        1 for job in result_jobs
        if hardware_submission_recorded(job.get("hardware_submission_status"))
    )

    count_mismatches = []
    if spec_selected_count != len(spec_jobs):
        count_mismatches.append("spec_selected_job_count")
    if result_selected_count != len(result_jobs):
        count_mismatches.append("result_selected_job_count")
    if result_selected_count != len(spec_jobs):
        count_mismatches.append("result_selected_matches_specs")
    if reported_completed_simulator != len(completed_simulator_ids):
        count_mismatches.append("completed_simulator_job_count")
    if reported_blocked != len(blocked_result_ids):
        count_mismatches.append("blocked_job_count")
    if reported_hardware_candidate != spec_hardware_candidate_count:
        count_mismatches.append("hardware_candidate_job_count")
    if result_hardware_candidate_count != spec_hardware_candidate_count:
        count_mismatches.append("result_hardware_candidate_count")
    if reported_hardware_submitted != spec_hardware_submitted_count:
        count_mismatches.append("hardware_submitted_job_count")
    if result_hardware_submitted_count != spec_hardware_submitted_count:
        count_mismatches.append("result_hardware_submitted_count")

    artifact_audits = []
    artifact_mismatch_job_ids = []
    artifact_missing_evidence_job_ids = []
    artifact_path_mismatch_job_ids = []
    artifact_not_existing_job_ids = []
    total_required_artifact_count = 0
    total_artifact_evidence_count = 0
    artifact_evidence_mismatch_count = 0
    for spec_job in spec_jobs:
        item_id = job_id(spec_job)
        if not item_id or item_id not in result_index:
            continue
        audit = job_artifact_evidence_audit(spec_job, result_index[item_id])
        total_required_artifact_count += int(
            audit.get("required_artifact_count") or 0)
        total_artifact_evidence_count += int(
            audit.get("artifact_evidence_count") or 0)
        artifact_evidence_mismatch_count += int(
            audit.get("artifact_evidence_mismatch_count") or 0)
        if not audit.get("passed"):
            artifact_mismatch_job_ids.append(item_id)
            artifact_audits.append({"job_id": item_id, **audit})
        if audit.get("missing_artifact_evidence_names"):
            artifact_missing_evidence_job_ids.append(item_id)
        if audit.get("artifact_path_mismatch_names"):
            artifact_path_mismatch_job_ids.append(item_id)
        if audit.get("artifact_exists_false_names"):
            artifact_not_existing_job_ids.append(item_id)

    mismatch_count = (
        len(count_mismatches) +
        len(missing_result_ids) +
        len(unexpected_result_ids) +
        len(duplicate_spec_ids) +
        len(duplicate_result_ids) +
        invalid_spec_job_count +
        invalid_result_job_count +
        len(non_completed_simulator_ids) +
        len(blocked_result_ids) +
        artifact_evidence_mismatch_count
    )
    recorded = (
        job_specs.get("schema") == "qge.moonlab_job_specs.v0" and
        job_results.get("schema") == "qge.moonlab_job_results.v0" and
        bool(spec_jobs) and
        bool(result_jobs)
    )
    return {
        "recorded": recorded,
        "spec_job_count": len(spec_jobs),
        "result_job_count": len(result_jobs),
        "spec_selected_job_count": spec_selected_count,
        "result_selected_job_count": result_selected_count,
        "completed_simulator_job_count": reported_completed_simulator,
        "actual_completed_simulator_job_count": len(completed_simulator_ids),
        "blocked_job_count": reported_blocked,
        "actual_blocked_job_count": len(blocked_result_ids),
        "hardware_candidate_job_count": reported_hardware_candidate,
        "actual_hardware_candidate_job_count": spec_hardware_candidate_count,
        "hardware_submitted_job_count": reported_hardware_submitted,
        "actual_hardware_submitted_job_count": spec_hardware_submitted_count,
        "invalid_spec_job_count": invalid_spec_job_count,
        "invalid_result_job_count": invalid_result_job_count,
        "duplicate_spec_job_ids": duplicate_spec_ids,
        "duplicate_result_job_ids": duplicate_result_ids,
        "missing_result_job_ids": missing_result_ids,
        "unexpected_result_job_ids": unexpected_result_ids,
        "missing_required_artifact_job_ids": sorted(set(missing_artifact_ids)),
        "required_artifact_count": total_required_artifact_count,
        "artifact_evidence_count": total_artifact_evidence_count,
        "artifact_evidence_mismatch_count": artifact_evidence_mismatch_count,
        "artifact_evidence_mismatch_job_ids": sorted(
            set(artifact_mismatch_job_ids)),
        "artifact_missing_evidence_job_ids": sorted(
            set(artifact_missing_evidence_job_ids)),
        "artifact_path_mismatch_job_ids": sorted(
            set(artifact_path_mismatch_job_ids)),
        "artifact_not_existing_job_ids": sorted(
            set(artifact_not_existing_job_ids)),
        "artifact_evidence_mismatches": artifact_audits,
        "blocked_result_job_ids": sorted(set(blocked_result_ids)),
        "non_completed_simulator_job_ids": sorted(
            set(non_completed_simulator_ids)),
        "count_mismatches": count_mismatches,
        "mismatch_count": mismatch_count,
        "passed": recorded and mismatch_count == 0,
    }


def coverage_ledger_mismatches(
    observations: dict[str, Any],
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    requirements: dict[str, Any],
) -> list[str]:
    pairs = [
        ("coverage_status", "coverage_status", coverage.get("status")),
        ("map_set", "map_set", coverage.get("map_set")),
        (
            "target_map_count",
            "target_map_count",
            coverage.get("target_map_count"),
        ),
        (
            "covered_map_count",
            "covered_map_count",
            coverage.get("covered_map_count"),
        ),
        (
            "missing_map_count",
            "missing_map_count",
            coverage.get("missing_map_count"),
        ),
        (
            "asset_inventory_status",
            "asset_inventory_status",
            inventory.get("status"),
        ),
        (
            "asset_available_map_count",
            "asset_available_map_count",
            inventory.get("available_map_count"),
        ),
        (
            "asset_missing_map_count",
            "asset_missing_map_count",
            inventory.get("missing_map_count"),
        ),
        (
            "asset_invalid_bsp_count",
            "asset_invalid_bsp_count",
            inventory.get("invalid_bsp_count"),
        ),
        (
            "full_game_asset_ready",
            "full_game_asset_ready",
            inventory.get("full_game_asset_ready"),
        ),
        (
            "asset_requirement_status",
            "asset_requirement_status",
            requirements.get("status"),
        ),
        (
            "asset_requirements_present_map_count",
            "asset_requirements_present_map_count",
            requirements.get("present_map_count"),
        ),
        (
            "asset_requirements_missing_map_count",
            "asset_requirements_missing_map_count",
            requirements.get("missing_map_count"),
        ),
        (
            "asset_requirements_satisfied",
            "asset_requirements_satisfied",
            dict_or_empty(requirements.get("claim_posture")).get(
                "asset_requirements_satisfied"),
        ),
    ]
    mismatches = []
    for label, observation_key, expected in pairs:
        if expected is None:
            continue
        if observations.get(observation_key) != expected:
            mismatches.append(label)
    expected_missing = coverage.get("missing_maps")
    if expected_missing is not None and string_list(
        observations.get("missing_maps")
    ) != string_list(expected_missing):
        mismatches.append("missing_maps")
    return mismatches


def moonlab_coverage_ledger_audit(
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    requirements: dict[str, Any],
    job_results: dict[str, Any],
) -> dict[str, Any]:
    job = first_job_by_domain(job_results, "full_game_map_coverage")
    observations = dict_or_empty(job.get("observations"))
    missing_required_artifacts = [
        item for item in list_or_empty(job.get("missing_required_artifacts"))
        if isinstance(item, str)
    ]
    mismatches = (
        coverage_ledger_mismatches(
            observations,
            coverage,
            inventory,
            requirements,
        )
        if job else
        []
    )
    recorded = bool(job)
    simulator_completed = backend_completed(job, "moonlab_simulator")
    result_status = job.get("result_status")
    return {
        "recorded": recorded,
        "result_status": result_status,
        "simulator_backend_completed": simulator_completed,
        "missing_required_artifact_count": len(missing_required_artifacts),
        "missing_required_artifacts": missing_required_artifacts,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "observed_coverage_status": observations.get("coverage_status"),
        "observed_missing_map_count": observations.get("missing_map_count"),
        "observed_asset_requirement_status": observations.get(
            "asset_requirement_status"),
        "observed_asset_requirements_satisfied": observations.get(
            "asset_requirements_satisfied"),
        "passed": (
            recorded and
            result_status == "completed" and
            simulator_completed and
            not missing_required_artifacts and
            not mismatches
        ),
    }


def gate_summary(
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    requirements: dict[str, Any],
    full_game_plan: dict[str, Any],
    job_specs: dict[str, Any],
    job_results: dict[str, Any],
    submission_packet: dict[str, Any],
    hardware_record_template: dict[str, Any],
    asset_remediation: dict[str, Any] | None = None,
    submission_bundle: dict[str, Any] | None = None,
    hardware_submission_scope: dict[str, Any] | None = None,
    artifact_paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    remediation = dict_or_empty(asset_remediation)
    paths = dict_or_empty(artifact_paths)
    handoff = dict_or_empty(full_game_plan.get("registered_asset_handoff"))
    handoff_counts = asset_handoff_status_counts(full_game_plan)
    plan_ledger = qge_moonlab_full_game_plan_audit.full_game_plan_ledger_audit(
        coverage,
        inventory,
        full_game_plan,
    )
    coverage_ledger = moonlab_coverage_ledger_audit(
        coverage,
        inventory,
        requirements,
        job_results,
    )
    selected_job_ledger = selected_job_result_ledger_audit(
        job_specs,
        job_results,
    )
    submission_packet_ledger = (
        qge_moonlab_submission_packet_audit.submission_packet_ledger_audit
    )(
        job_specs,
        job_results,
        submission_packet,
    )
    hardware_template_ledger = (
        qge_moonlab_hardware_template_audit.hardware_record_template_audit
    )(
        submission_packet,
        hardware_record_template,
    )
    hardware_scope_ledger = (
        qge_moonlab_hardware_scope_audit.hardware_submission_scope_audit
    )(
        submission_packet,
        dict_or_empty(submission_bundle),
        hardware_record_template,
        dict_or_empty(hardware_submission_scope),
        packet_path=paths.get("moonlab_submission_packet"),
        bundle_path=paths.get("moonlab_submission_bundle"),
        hardware_template_path=paths.get("moonlab_hardware_record_template"),
    )
    hardware_result_ledger = (
        qge_moonlab_hardware_result_audit.hardware_result_ledger_audit
    )(
        submission_packet,
        job_results,
        dict_or_empty(hardware_submission_scope),
    )
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
        "covered_route_contract_authority_ready_count": full_game_plan.get(
            "covered_route_contract_authority_ready_count"),
        "covered_route_contract_authority_complete": full_game_plan.get(
            "covered_route_contract_authority_complete"),
        "covered_route_contract_authority_blocked_maps": full_game_plan.get(
            "covered_route_contract_authority_blocked_maps"),
        "capture_required_map_count": full_game_plan.get(
            "capture_required_map_count"),
        "capture_required_maps": full_game_plan.get("capture_required_maps"),
        "asset_unavailable_map_count": full_game_plan.get(
            "asset_unavailable_map_count"),
        "asset_unavailable_maps": full_game_plan.get("asset_unavailable_maps"),
        "registered_asset_handoff_present": handoff.get("present"),
        "registered_asset_handoff_status": handoff.get(
            "registered_asset_intake_status"),
        "registered_asset_handoff_blocker_reason": handoff.get(
            "registered_asset_blocker_reason"),
        "registered_asset_handoff_copy_script_mode": handoff.get(
            "copy_script_mode"),
        "registered_asset_handoff_missing_map_count_after_plan": (
            handoff.get("missing_map_count_after_plan")),
        "registered_asset_handoff_actionable_copy_plan_count": (
            handoff.get("actionable_copy_plan_count")),
        "registered_asset_handoff_copy_plan_unblocked_map_count": (
            handoff.get("copy_plan_unblocked_map_count")),
        "registered_asset_handoff_copy_plan_blocked_map_count": (
            handoff.get("copy_plan_blocked_map_count")),
        "registered_asset_handoff_status_counts": handoff_counts,
        "registered_asset_handoff_not_recorded_count": (
            handoff_counts.get("not_recorded", 0)),
        "registered_asset_handoff_licensed_asset_required_count": (
            handoff_counts.get("licensed_asset_required", 0)),
        "registered_asset_handoff_copy_plan_unblocked_count": (
            handoff_counts.get("copy_plan_unblocked", 0)),
        "registered_asset_handoff_copy_plan_blocked_count": (
            handoff_counts.get("copy_plan_blocked", 0)),
        "moonlab_full_game_plan_ledger_recorded": plan_ledger.get(
            "recorded"),
        "moonlab_full_game_plan_ledger_mismatch_count": (
            plan_ledger.get("mismatch_count")),
        "moonlab_full_game_plan_ledger_top_level_mismatches": (
            plan_ledger.get("top_level_mismatches")),
        "moonlab_full_game_plan_ledger_row_count": (
            plan_ledger.get("row_count")),
        "moonlab_full_game_plan_ledger_expected_row_count": (
            plan_ledger.get("expected_row_count")),
        "moonlab_full_game_plan_ledger_invalid_row_count": (
            plan_ledger.get("invalid_row_count")),
        "moonlab_full_game_plan_ledger_duplicate_row_maps": (
            plan_ledger.get("duplicate_row_maps")),
        "moonlab_full_game_plan_ledger_missing_row_maps": (
            plan_ledger.get("missing_row_maps")),
        "moonlab_full_game_plan_ledger_unexpected_row_maps": (
            plan_ledger.get("unexpected_row_maps")),
        "moonlab_full_game_plan_ledger_row_mismatches": (
            plan_ledger.get("row_mismatches")),
        "moonlab_full_game_plan_ledger_route_contract_mismatch_maps": (
            plan_ledger.get("route_contract_mismatch_maps")),
        "moonlab_full_game_plan_ledger_expected_status": (
            plan_ledger.get("expected_status")),
        "moonlab_full_game_plan_ledger_recorded_status": (
            plan_ledger.get("recorded_status")),
        "moonlab_coverage_ledger_recorded": coverage_ledger.get("recorded"),
        "moonlab_coverage_ledger_result_status": coverage_ledger.get(
            "result_status"),
        "moonlab_coverage_ledger_simulator_backend_completed": (
            coverage_ledger.get("simulator_backend_completed")),
        "moonlab_coverage_ledger_mismatch_count": coverage_ledger.get(
            "mismatch_count"),
        "moonlab_coverage_ledger_mismatches": coverage_ledger.get(
            "mismatches"),
        "moonlab_coverage_ledger_missing_required_artifact_count": (
            coverage_ledger.get("missing_required_artifact_count")),
        "moonlab_coverage_ledger_observed_coverage_status": (
            coverage_ledger.get("observed_coverage_status")),
        "moonlab_coverage_ledger_observed_missing_map_count": (
            coverage_ledger.get("observed_missing_map_count")),
        "moonlab_coverage_ledger_observed_asset_requirement_status": (
            coverage_ledger.get("observed_asset_requirement_status")),
        "moonlab_coverage_ledger_observed_asset_requirements_satisfied": (
            coverage_ledger.get("observed_asset_requirements_satisfied")),
        "moonlab_selected_job_result_ledger_recorded": (
            selected_job_ledger.get("recorded")),
        "moonlab_selected_job_result_ledger_mismatch_count": (
            selected_job_ledger.get("mismatch_count")),
        "moonlab_selected_job_result_ledger_count_mismatches": (
            selected_job_ledger.get("count_mismatches")),
        "moonlab_selected_job_spec_job_count": selected_job_ledger.get(
            "spec_job_count"),
        "moonlab_selected_job_result_job_count": selected_job_ledger.get(
            "result_job_count"),
        "moonlab_selected_job_missing_result_count": len(
            list_or_empty(selected_job_ledger.get("missing_result_job_ids"))),
        "moonlab_selected_job_missing_result_ids": (
            selected_job_ledger.get("missing_result_job_ids")),
        "moonlab_selected_job_unexpected_result_count": len(
            list_or_empty(
                selected_job_ledger.get("unexpected_result_job_ids"))),
        "moonlab_selected_job_unexpected_result_ids": (
            selected_job_ledger.get("unexpected_result_job_ids")),
        "moonlab_selected_job_duplicate_spec_ids": (
            selected_job_ledger.get("duplicate_spec_job_ids")),
        "moonlab_selected_job_duplicate_result_ids": (
            selected_job_ledger.get("duplicate_result_job_ids")),
        "moonlab_selected_job_invalid_spec_job_count": (
            selected_job_ledger.get("invalid_spec_job_count")),
        "moonlab_selected_job_invalid_result_job_count": (
            selected_job_ledger.get("invalid_result_job_count")),
        "moonlab_selected_job_non_completed_simulator_count": len(
            list_or_empty(
                selected_job_ledger.get("non_completed_simulator_job_ids"))),
        "moonlab_selected_job_non_completed_simulator_ids": (
            selected_job_ledger.get("non_completed_simulator_job_ids")),
        "moonlab_selected_job_missing_required_artifact_count": len(
            list_or_empty(
                selected_job_ledger.get(
                    "missing_required_artifact_job_ids"))),
        "moonlab_selected_job_missing_required_artifact_ids": (
            selected_job_ledger.get("missing_required_artifact_job_ids")),
        "moonlab_selected_job_required_artifact_count": (
            selected_job_ledger.get("required_artifact_count")),
        "moonlab_selected_job_artifact_evidence_count": (
            selected_job_ledger.get("artifact_evidence_count")),
        "moonlab_selected_job_artifact_evidence_mismatch_count": (
            selected_job_ledger.get("artifact_evidence_mismatch_count")),
        "moonlab_selected_job_artifact_evidence_mismatch_job_ids": (
            selected_job_ledger.get("artifact_evidence_mismatch_job_ids")),
        "moonlab_selected_job_artifact_missing_evidence_job_ids": (
            selected_job_ledger.get("artifact_missing_evidence_job_ids")),
        "moonlab_selected_job_artifact_path_mismatch_job_ids": (
            selected_job_ledger.get("artifact_path_mismatch_job_ids")),
        "moonlab_selected_job_artifact_not_existing_job_ids": (
            selected_job_ledger.get("artifact_not_existing_job_ids")),
        "moonlab_selected_job_artifact_evidence_mismatches": (
            selected_job_ledger.get("artifact_evidence_mismatches")),
        "moonlab_submission_packet_ledger_recorded": (
            submission_packet_ledger.get("recorded")),
        "moonlab_submission_packet_ledger_mismatch_count": (
            submission_packet_ledger.get("mismatch_count")),
        "moonlab_submission_packet_ledger_schema_mismatches": (
            submission_packet_ledger.get("schema_mismatches")),
        "moonlab_submission_packet_ledger_count_mismatches": (
            submission_packet_ledger.get("count_mismatches")),
        "moonlab_submission_packet_spec_candidate_count": (
            submission_packet_ledger.get("spec_hardware_candidate_count")),
        "moonlab_submission_packet_candidate_count": (
            submission_packet_ledger.get("packet_candidate_job_count")),
        "moonlab_submission_packet_missing_candidate_ids": (
            submission_packet_ledger.get("missing_candidate_job_ids")),
        "moonlab_submission_packet_unexpected_candidate_ids": (
            submission_packet_ledger.get("unexpected_candidate_job_ids")),
        "moonlab_submission_packet_duplicate_candidate_ids": (
            submission_packet_ledger.get("duplicate_packet_candidate_ids")),
        "moonlab_submission_packet_invalid_candidate_count": (
            submission_packet_ledger.get("invalid_packet_candidate_count")),
        "moonlab_submission_packet_row_mismatch_job_ids": (
            submission_packet_ledger.get("row_mismatch_job_ids")),
        "moonlab_submission_packet_row_mismatches": (
            submission_packet_ledger.get("row_mismatches")),
        "moonlab_hardware_record_template_ledger_recorded": (
            hardware_template_ledger.get("recorded")),
        "moonlab_hardware_record_template_ledger_mismatch_count": (
            hardware_template_ledger.get("mismatch_count")),
        "moonlab_hardware_record_template_schema_mismatches": (
            hardware_template_ledger.get("schema_mismatches")),
        "moonlab_hardware_record_template_source_mismatches": (
            hardware_template_ledger.get("source_mismatches")),
        "moonlab_hardware_record_template_row_mismatch_count": (
            hardware_template_ledger.get("row_mismatch_count")),
        "moonlab_hardware_record_template_row_mismatches": (
            hardware_template_ledger.get("row_mismatches")),
        "moonlab_hardware_record_template_job_id": (
            hardware_template_ledger.get("template_job_id")),
        "moonlab_hardware_record_template_candidate_digest": (
            hardware_template_ledger.get("template_candidate_digest")),
        "moonlab_hardware_record_template_candidate_found": (
            hardware_template_ledger.get("candidate_found")),
        "moonlab_hardware_record_template_candidate_job_count": (
            hardware_template_ledger.get("candidate_job_count")),
        "moonlab_hardware_record_template_validation_contract_present": (
            hardware_template_ledger.get("validation_contract_present")),
        "moonlab_hardware_submission_scope_ledger_recorded": (
            hardware_scope_ledger.get("recorded")),
        "moonlab_hardware_submission_scope_ledger_mismatch_count": (
            hardware_scope_ledger.get("mismatch_count")),
        "moonlab_hardware_submission_scope_schema_mismatches": (
            hardware_scope_ledger.get("schema_mismatches")),
        "moonlab_submission_bundle_mismatches": (
            hardware_scope_ledger.get("submission_bundle_mismatches")),
        "moonlab_hardware_submission_scope_mismatches": (
            hardware_scope_ledger.get(
                "hardware_submission_scope_mismatches")),
        "moonlab_hardware_submission_scope_expected_status": (
            hardware_scope_ledger.get("expected_scope_status")),
        "moonlab_hardware_submission_scope_recorded_status": (
            hardware_scope_ledger.get("recorded_scope_status")),
        "moonlab_hardware_submission_scope_expected_ready": (
            hardware_scope_ledger.get("expected_scope_ready")),
        "moonlab_hardware_submission_scope_recorded_ready": (
            hardware_scope_ledger.get("recorded_scope_ready")),
        "moonlab_hardware_submission_scope_expected_candidate_count": (
            hardware_scope_ledger.get("expected_candidate_job_count")),
        "moonlab_hardware_submission_scope_recorded_candidate_count": (
            hardware_scope_ledger.get("recorded_candidate_job_count")),
        "moonlab_hardware_result_ledger_recorded": (
            hardware_result_ledger.get("recorded")),
        "moonlab_hardware_result_ledger_mismatch_count": (
            hardware_result_ledger.get("mismatch_count")),
        "moonlab_hardware_result_ledger_schema_mismatches": (
            hardware_result_ledger.get("schema_mismatches")),
        "moonlab_hardware_result_ledger_count_mismatches": (
            hardware_result_ledger.get("count_mismatches")),
        "moonlab_hardware_result_job_count": (
            hardware_result_ledger.get("hardware_result_job_count")),
        "moonlab_hardware_result_row_count": (
            hardware_result_ledger.get("hardware_result_row_count")),
        "moonlab_hardware_result_completed_row_count": (
            hardware_result_ledger.get("completed_hardware_result_count")),
        "moonlab_hardware_result_reported_completed_job_count": (
            hardware_result_ledger.get(
                "reported_completed_hardware_job_count")),
        "moonlab_hardware_result_row_mismatch_job_ids": (
            hardware_result_ledger.get("row_mismatch_job_ids")),
        "moonlab_hardware_result_row_mismatches": (
            hardware_result_ledger.get("row_mismatches")),
        "moonlab_hardware_result_duplicate_job_ids": (
            hardware_result_ledger.get("duplicate_hardware_result_job_ids")),
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
        "registered_asset_intake_actionable_copy_plan_count": remediation.get(
            "actionable_copy_plan_count"),
        "registered_asset_intake_copy_plan_unblocked_map_count": (
            remediation.get("copy_plan_unblocked_map_count")),
        "registered_asset_intake_copy_plan_blocked_map_count": (
            remediation.get("copy_plan_blocked_map_count")),
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
    submission_bundle: dict[str, Any] | None = None,
    hardware_submission_scope: dict[str, Any] | None = None,
    artifact_paths: dict[str, str] | None = None,
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
        qge_full_game_route_contracts.ROUTE_CONTRACT_SCHEMA and
        bool_true(full_game_plan.get("route_contracts_complete")) and
        expected_route_contract_count is not None and
        route_contract_count == expected_route_contract_count and
        not missing_route_contract_maps
    )
    covered_route_authority_blocked_maps = list_or_empty(
        full_game_plan.get("covered_route_contract_authority_blocked_maps"))
    route_authority_ready_count = int_or_none(full_game_plan.get(
        "covered_route_contract_authority_ready_count"))
    route_authority_passed = (
        bool_true(full_game_plan.get(
            "covered_route_contract_authority_complete")) and
        covered_count is not None and
        route_authority_ready_count == covered_count and
        not covered_route_authority_blocked_maps
    )
    plan_ledger_audit = (
        qge_moonlab_full_game_plan_audit.full_game_plan_ledger_audit
    )(
        coverage,
        inventory,
        full_game_plan,
    )
    plan_passed = (
        full_game_plan.get("schema") ==
        "qge.moonlab_full_game_deployment_plan.v0" and
        full_game_plan.get("status") == "map_coverage_complete" and
        route_contracts_passed and
        route_authority_passed and
        bool_true(plan_ledger_audit.get("passed")) and
        capture_required == 0 and
        asset_unavailable == 0
    )
    remediation = dict_or_empty(asset_remediation)
    handoff_audit = registered_asset_handoff_audit(
        full_game_plan,
        remediation,
        asset_unavailable=asset_unavailable,
    )
    coverage_ledger_audit = moonlab_coverage_ledger_audit(
        coverage,
        inventory,
        requirements,
        job_results,
    )
    selected_job_ledger_audit = selected_job_result_ledger_audit(
        job_specs,
        job_results,
    )
    submission_packet_ledger_audit = (
        qge_moonlab_submission_packet_audit.submission_packet_ledger_audit
    )(
        job_specs,
        job_results,
        dict_or_empty(submission_packet),
    )
    hardware_template_ledger_audit = (
        qge_moonlab_hardware_template_audit.hardware_record_template_audit
    )(
        dict_or_empty(submission_packet),
        dict_or_empty(hardware_record_template),
    )
    paths = dict_or_empty(artifact_paths)
    hardware_scope_ledger_audit = (
        qge_moonlab_hardware_scope_audit.hardware_submission_scope_audit
    )(
        dict_or_empty(submission_packet),
        dict_or_empty(submission_bundle),
        dict_or_empty(hardware_record_template),
        dict_or_empty(hardware_submission_scope),
        packet_path=paths.get("moonlab_submission_packet"),
        bundle_path=paths.get("moonlab_submission_bundle"),
        hardware_template_path=paths.get("moonlab_hardware_record_template"),
    )
    hardware_result_ledger_audit = (
        qge_moonlab_hardware_result_audit.hardware_result_ledger_audit
    )(
        dict_or_empty(submission_packet),
        dict_or_empty(job_results),
        dict_or_empty(hardware_submission_scope),
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

    overclaims = qge_moonlab_overclaim_audit.overclaim_flags(
        resource_envelope=resource_envelope,
        asset_requirements=requirements,
        full_game_plan=full_game_plan,
        job_specs=job_specs,
        job_results=job_results,
        submission_packet=submission_packet,
        submission_bundle=submission_bundle,
        hardware_record_template=hardware_record_template,
        hardware_submission_scope=hardware_submission_scope,
    )
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
            "covered_route_contract_authority_complete",
            route_authority_passed,
            {
                "covered_map_count": covered_count,
                "route_contract_authority_ready_count": (
                    route_authority_ready_count),
                "covered_route_contract_authority_complete": (
                    full_game_plan.get(
                        "covered_route_contract_authority_complete")),
                "covered_route_contract_authority_blocked_maps": (
                    covered_route_authority_blocked_maps),
            },
            "covered maps are missing route-contract authority evidence",
        ),
        criterion(
            "registered_asset_handoff_consistent",
            bool_true(handoff_audit.get("passed")),
            {
                "registered_asset_handoff_expected": handoff_audit.get(
                    "expected"),
                "registered_asset_handoff_recorded": handoff_audit.get(
                    "recorded"),
                "registered_asset_handoff_mismatches": handoff_audit.get(
                    "mismatches"),
                "registered_asset_handoff_not_recorded_count": (
                    handoff_audit.get("not_recorded_count")),
                "registered_asset_handoff_licensed_asset_required_count": (
                    handoff_audit.get("licensed_asset_required_count")),
                "registered_asset_handoff_copy_plan_unblocked_count": (
                    handoff_audit.get("copy_plan_unblocked_count")),
                "registered_asset_handoff_copy_plan_blocked_count": (
                    handoff_audit.get("copy_plan_blocked_count")),
                "registered_asset_handoff_status_counts": (
                    handoff_audit.get("status_counts")),
            },
            "full-game plan is missing or inconsistent with registered asset intake handoff evidence",
        ),
        criterion(
            "moonlab_full_game_plan_ledger_consistent",
            bool_true(plan_ledger_audit.get("passed")),
            {
                "moonlab_full_game_plan_ledger_recorded": (
                    plan_ledger_audit.get("recorded")),
                "moonlab_full_game_plan_ledger_mismatch_count": (
                    plan_ledger_audit.get("mismatch_count")),
                "moonlab_full_game_plan_ledger_top_level_mismatches": (
                    plan_ledger_audit.get("top_level_mismatches")),
                "moonlab_full_game_plan_ledger_row_count": (
                    plan_ledger_audit.get("row_count")),
                "moonlab_full_game_plan_ledger_expected_row_count": (
                    plan_ledger_audit.get("expected_row_count")),
                "moonlab_full_game_plan_ledger_invalid_row_count": (
                    plan_ledger_audit.get("invalid_row_count")),
                "moonlab_full_game_plan_ledger_duplicate_row_maps": (
                    plan_ledger_audit.get("duplicate_row_maps")),
                "moonlab_full_game_plan_ledger_missing_row_maps": (
                    plan_ledger_audit.get("missing_row_maps")),
                "moonlab_full_game_plan_ledger_unexpected_row_maps": (
                    plan_ledger_audit.get("unexpected_row_maps")),
                "moonlab_full_game_plan_ledger_row_mismatches": (
                    plan_ledger_audit.get("row_mismatches")),
                "moonlab_full_game_plan_ledger_route_contract_mismatch_maps": (
                    plan_ledger_audit.get("route_contract_mismatch_maps")),
                "moonlab_full_game_plan_ledger_expected_status": (
                    plan_ledger_audit.get("expected_status")),
                "moonlab_full_game_plan_ledger_recorded_status": (
                    plan_ledger_audit.get("recorded_status")),
            },
            (
                "Moonlab full-game deployment plan rows are stale or "
                "inconsistent with coverage, asset inventory, or route "
                "contracts"
            ),
        ),
        criterion(
            "moonlab_coverage_ledger_consistent",
            bool_true(coverage_ledger_audit.get("passed")),
            {
                "moonlab_coverage_ledger_recorded": (
                    coverage_ledger_audit.get("recorded")),
                "moonlab_coverage_ledger_result_status": (
                    coverage_ledger_audit.get("result_status")),
                "moonlab_coverage_ledger_simulator_backend_completed": (
                    coverage_ledger_audit.get(
                        "simulator_backend_completed")),
                "moonlab_coverage_ledger_missing_required_artifact_count": (
                    coverage_ledger_audit.get(
                        "missing_required_artifact_count")),
                "moonlab_coverage_ledger_mismatch_count": (
                    coverage_ledger_audit.get("mismatch_count")),
                "moonlab_coverage_ledger_mismatches": (
                    coverage_ledger_audit.get("mismatches")),
                "moonlab_coverage_ledger_observed_coverage_status": (
                    coverage_ledger_audit.get("observed_coverage_status")),
                "moonlab_coverage_ledger_observed_missing_map_count": (
                    coverage_ledger_audit.get("observed_missing_map_count")),
                "moonlab_coverage_ledger_observed_asset_requirement_status": (
                    coverage_ledger_audit.get(
                        "observed_asset_requirement_status")),
                "moonlab_coverage_ledger_observed_asset_requirements_satisfied": (
                    coverage_ledger_audit.get(
                        "observed_asset_requirements_satisfied")),
            },
            (
                "Moonlab coverage-ledger replay is missing, stale, or "
                "inconsistent with coverage and asset evidence"
            ),
        ),
        criterion(
            "moonlab_selected_job_result_ledger_consistent",
            bool_true(selected_job_ledger_audit.get("passed")),
            {
                "moonlab_selected_job_result_ledger_recorded": (
                    selected_job_ledger_audit.get("recorded")),
                "moonlab_selected_job_result_ledger_mismatch_count": (
                    selected_job_ledger_audit.get("mismatch_count")),
                "moonlab_selected_job_result_ledger_count_mismatches": (
                    selected_job_ledger_audit.get("count_mismatches")),
                "moonlab_selected_job_spec_job_count": (
                    selected_job_ledger_audit.get("spec_job_count")),
                "moonlab_selected_job_result_job_count": (
                    selected_job_ledger_audit.get("result_job_count")),
                "moonlab_selected_job_missing_result_ids": (
                    selected_job_ledger_audit.get("missing_result_job_ids")),
                "moonlab_selected_job_unexpected_result_ids": (
                    selected_job_ledger_audit.get(
                        "unexpected_result_job_ids")),
                "moonlab_selected_job_duplicate_spec_ids": (
                    selected_job_ledger_audit.get(
                        "duplicate_spec_job_ids")),
                "moonlab_selected_job_duplicate_result_ids": (
                    selected_job_ledger_audit.get(
                        "duplicate_result_job_ids")),
                "moonlab_selected_job_invalid_spec_job_count": (
                    selected_job_ledger_audit.get(
                        "invalid_spec_job_count")),
                "moonlab_selected_job_invalid_result_job_count": (
                    selected_job_ledger_audit.get(
                        "invalid_result_job_count")),
                "moonlab_selected_job_non_completed_simulator_ids": (
                    selected_job_ledger_audit.get(
                        "non_completed_simulator_job_ids")),
                "moonlab_selected_job_missing_required_artifact_ids": (
                    selected_job_ledger_audit.get(
                        "missing_required_artifact_job_ids")),
                "moonlab_selected_job_required_artifact_count": (
                    selected_job_ledger_audit.get(
                        "required_artifact_count")),
                "moonlab_selected_job_artifact_evidence_count": (
                    selected_job_ledger_audit.get(
                        "artifact_evidence_count")),
                "moonlab_selected_job_artifact_evidence_mismatch_count": (
                    selected_job_ledger_audit.get(
                        "artifact_evidence_mismatch_count")),
                "moonlab_selected_job_artifact_evidence_mismatch_job_ids": (
                    selected_job_ledger_audit.get(
                        "artifact_evidence_mismatch_job_ids")),
                "moonlab_selected_job_artifact_missing_evidence_job_ids": (
                    selected_job_ledger_audit.get(
                        "artifact_missing_evidence_job_ids")),
                "moonlab_selected_job_artifact_path_mismatch_job_ids": (
                    selected_job_ledger_audit.get(
                        "artifact_path_mismatch_job_ids")),
                "moonlab_selected_job_artifact_not_existing_job_ids": (
                    selected_job_ledger_audit.get(
                        "artifact_not_existing_job_ids")),
            },
            (
                "selected Moonlab job result ledger is missing, stale, or "
                "inconsistent with job specs"
            ),
        ),
        criterion(
            "moonlab_submission_packet_ledger_consistent",
            bool_true(submission_packet_ledger_audit.get("passed")),
            {
                "moonlab_submission_packet_ledger_recorded": (
                    submission_packet_ledger_audit.get("recorded")),
                "moonlab_submission_packet_ledger_mismatch_count": (
                    submission_packet_ledger_audit.get("mismatch_count")),
                "moonlab_submission_packet_ledger_schema_mismatches": (
                    submission_packet_ledger_audit.get("schema_mismatches")),
                "moonlab_submission_packet_ledger_count_mismatches": (
                    submission_packet_ledger_audit.get("count_mismatches")),
                "moonlab_submission_packet_spec_candidate_count": (
                    submission_packet_ledger_audit.get(
                        "spec_hardware_candidate_count")),
                "moonlab_submission_packet_candidate_count": (
                    submission_packet_ledger_audit.get(
                        "packet_candidate_job_count")),
                "moonlab_submission_packet_missing_candidate_ids": (
                    submission_packet_ledger_audit.get(
                        "missing_candidate_job_ids")),
                "moonlab_submission_packet_unexpected_candidate_ids": (
                    submission_packet_ledger_audit.get(
                        "unexpected_candidate_job_ids")),
                "moonlab_submission_packet_duplicate_candidate_ids": (
                    submission_packet_ledger_audit.get(
                        "duplicate_packet_candidate_ids")),
                "moonlab_submission_packet_invalid_candidate_count": (
                    submission_packet_ledger_audit.get(
                        "invalid_packet_candidate_count")),
                "moonlab_submission_packet_row_mismatch_job_ids": (
                    submission_packet_ledger_audit.get(
                        "row_mismatch_job_ids")),
                "moonlab_submission_packet_row_mismatches": (
                    submission_packet_ledger_audit.get("row_mismatches")),
            },
            (
                "Moonlab hardware submission packet is missing, stale, or "
                "inconsistent with selected job specs/results"
            ),
        ),
        criterion(
            "moonlab_hardware_record_template_consistent",
            bool_true(hardware_template_ledger_audit.get("passed")),
            {
                "moonlab_hardware_record_template_ledger_recorded": (
                    hardware_template_ledger_audit.get("recorded")),
                "moonlab_hardware_record_template_ledger_mismatch_count": (
                    hardware_template_ledger_audit.get("mismatch_count")),
                "moonlab_hardware_record_template_schema_mismatches": (
                    hardware_template_ledger_audit.get("schema_mismatches")),
                "moonlab_hardware_record_template_source_mismatches": (
                    hardware_template_ledger_audit.get("source_mismatches")),
                "moonlab_hardware_record_template_row_mismatch_count": (
                    hardware_template_ledger_audit.get(
                        "row_mismatch_count")),
                "moonlab_hardware_record_template_row_mismatches": (
                    hardware_template_ledger_audit.get("row_mismatches")),
                "moonlab_hardware_record_template_job_id": (
                    hardware_template_ledger_audit.get("template_job_id")),
                "moonlab_hardware_record_template_candidate_digest": (
                    hardware_template_ledger_audit.get(
                        "template_candidate_digest")),
                "moonlab_hardware_record_template_candidate_found": (
                    hardware_template_ledger_audit.get("candidate_found")),
                "moonlab_hardware_record_template_candidate_job_count": (
                    hardware_template_ledger_audit.get(
                        "candidate_job_count")),
                "moonlab_hardware_record_template_validation_contract_present": (
                    hardware_template_ledger_audit.get(
                        "validation_contract_present")),
            },
            (
                "Moonlab hardware record template is missing, stale, or "
                "inconsistent with the hardware submission packet"
            ),
        ),
        criterion(
            "moonlab_hardware_submission_scope_consistent",
            bool_true(hardware_scope_ledger_audit.get("passed")),
            {
                "moonlab_hardware_submission_scope_ledger_recorded": (
                    hardware_scope_ledger_audit.get("recorded")),
                "moonlab_hardware_submission_scope_ledger_mismatch_count": (
                    hardware_scope_ledger_audit.get("mismatch_count")),
                "moonlab_hardware_submission_scope_schema_mismatches": (
                    hardware_scope_ledger_audit.get("schema_mismatches")),
                "moonlab_submission_bundle_mismatches": (
                    hardware_scope_ledger_audit.get(
                        "submission_bundle_mismatches")),
                "moonlab_hardware_submission_scope_mismatches": (
                    hardware_scope_ledger_audit.get(
                        "hardware_submission_scope_mismatches")),
                "moonlab_hardware_submission_scope_expected_status": (
                    hardware_scope_ledger_audit.get("expected_scope_status")),
                "moonlab_hardware_submission_scope_recorded_status": (
                    hardware_scope_ledger_audit.get("recorded_scope_status")),
                "moonlab_hardware_submission_scope_expected_ready": (
                    hardware_scope_ledger_audit.get("expected_scope_ready")),
                "moonlab_hardware_submission_scope_recorded_ready": (
                    hardware_scope_ledger_audit.get("recorded_scope_ready")),
                "moonlab_hardware_submission_scope_expected_candidate_count": (
                    hardware_scope_ledger_audit.get(
                        "expected_candidate_job_count")),
                "moonlab_hardware_submission_scope_recorded_candidate_count": (
                    hardware_scope_ledger_audit.get(
                        "recorded_candidate_job_count")),
            },
            (
                "Moonlab hardware submission scope is missing, stale, or "
                "inconsistent with the packet, bundle, or record template"
            ),
        ),
        criterion(
            "moonlab_hardware_result_ledger_consistent",
            bool_true(hardware_result_ledger_audit.get("passed")),
            {
                "moonlab_hardware_result_ledger_recorded": (
                    hardware_result_ledger_audit.get("recorded")),
                "moonlab_hardware_result_ledger_mismatch_count": (
                    hardware_result_ledger_audit.get("mismatch_count")),
                "moonlab_hardware_result_ledger_schema_mismatches": (
                    hardware_result_ledger_audit.get("schema_mismatches")),
                "moonlab_hardware_result_ledger_count_mismatches": (
                    hardware_result_ledger_audit.get("count_mismatches")),
                "moonlab_hardware_result_job_count": (
                    hardware_result_ledger_audit.get(
                        "hardware_result_job_count")),
                "moonlab_hardware_result_row_count": (
                    hardware_result_ledger_audit.get(
                        "hardware_result_row_count")),
                "moonlab_hardware_result_completed_row_count": (
                    hardware_result_ledger_audit.get(
                        "completed_hardware_result_count")),
                "moonlab_hardware_result_reported_completed_job_count": (
                    hardware_result_ledger_audit.get(
                        "reported_completed_hardware_job_count")),
                "moonlab_hardware_result_row_mismatch_job_ids": (
                    hardware_result_ledger_audit.get(
                        "row_mismatch_job_ids")),
                "moonlab_hardware_result_row_mismatches": (
                    hardware_result_ledger_audit.get("row_mismatches")),
                "moonlab_hardware_result_duplicate_job_ids": (
                    hardware_result_ledger_audit.get(
                        "duplicate_hardware_result_job_ids")),
            },
            (
                "Moonlab hardware result rows are missing, stale, or "
                "inconsistent with the bounded submission packet"
            ),
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
    if "covered_route_contract_authority_complete" in failed_ids:
        actions.append(
            "Rebuild breadth evidence and the Moonlab full-game plan from route-contract-aware capture matrices so every covered map proves its required authority domains."
        )
    if "registered_asset_handoff_consistent" in failed_ids:
        actions.append(
            "Regenerate qge_moonlab_full_game_plan.json from the current registered-asset intake so per-map asset_handoff_status matches the copy-plan ledger."
        )
    if "moonlab_full_game_plan_ledger_consistent" in failed_ids:
        actions.append(
            "Regenerate qge_moonlab_full_game_plan.json from current coverage, asset inventory, and route contracts so every per-map deployment row matches the source ledgers."
        )
    if "moonlab_coverage_ledger_consistent" in failed_ids:
        actions.append(
            "Regenerate qge_moonlab_job_results.json from the current pack so "
            "the full_game_map_coverage Moonlab replay observations match "
            "coverage, inventory, and asset requirements."
        )
    if "moonlab_selected_job_result_ledger_consistent" in failed_ids:
        actions.append(
            "Regenerate qge_moonlab_job_results.json from "
            "qge_moonlab_job_specs.json so every selected Moonlab job has a "
            "matching completed simulator result row and artifact evidence."
        )
    if "moonlab_submission_packet_ledger_consistent" in failed_ids:
        actions.append(
            "Regenerate qge_moonlab_submission_packet.json from current "
            "qge_moonlab_job_specs.json and qge_moonlab_job_results.json so "
            "hardware candidate rows match selected simulator evidence."
        )
    if "moonlab_hardware_record_template_consistent" in failed_ids:
        actions.append(
            "Regenerate qge_moonlab_hardware_record_template.json from the "
            "current qge_moonlab_submission_packet.json so returned hardware "
            "records update the correct bounded candidate."
        )
    if "moonlab_hardware_submission_scope_consistent" in failed_ids:
        actions.append(
            "Regenerate qge_moonlab_submission_bundle.json and "
            "qge_moonlab_hardware_submission_scope.json from the current "
            "submission packet and hardware record template so bounded "
            "hardware handoff readiness matches the source ledgers."
        )
    if "moonlab_hardware_result_ledger_consistent" in failed_ids:
        actions.append(
            "Re-ingest returned Moonlab hardware records with "
            "qge_moonlab_hardware_ingest.py so bounded hardware backend rows "
            "match the submission packet, scope, and retained simulator "
            "evidence."
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
    submission_bundle: dict[str, Any] | None = None,
    hardware_submission_scope: dict[str, Any] | None = None,
    artifact_paths: dict[str, str] | None = None,
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
        submission_bundle=submission_bundle,
        hardware_submission_scope=hardware_submission_scope,
        artifact_paths=artifact_paths,
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
            hardware_record_template,
            asset_remediation=asset_remediation,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            artifact_paths=artifact_paths,
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
    submission_bundle = qge_moonlab_full_game_plan.load_resource_json(
        manifest, "moonlab_submission_bundle", manifest_path=manifest_path) or {}
    hardware_record_template = qge_moonlab_full_game_plan.load_resource_json(
        manifest,
        "moonlab_hardware_record_template",
        manifest_path=manifest_path,
    ) or {}
    hardware_submission_scope = qge_moonlab_full_game_plan.load_resource_json(
        manifest,
        "moonlab_hardware_submission_scope",
        manifest_path=manifest_path,
    ) or {}
    artifact_paths = {
        "moonlab_submission_packet": resource_artifact_manifest_path(
            manifest, "moonlab_submission_packet"),
        "moonlab_submission_bundle": resource_artifact_manifest_path(
            manifest, "moonlab_submission_bundle"),
        "moonlab_hardware_record_template": resource_artifact_manifest_path(
            manifest, "moonlab_hardware_record_template"),
    }
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
        submission_bundle=submission_bundle,
        hardware_submission_scope=hardware_submission_scope,
        artifact_paths=artifact_paths,
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
        "registered_asset_intake_actionable_copy_plan_count": summary.get(
            "registered_asset_intake_actionable_copy_plan_count"),
        "registered_asset_intake_copy_plan_unblocked_map_count": summary.get(
            "registered_asset_intake_copy_plan_unblocked_map_count"),
        "registered_asset_intake_copy_plan_blocked_map_count": summary.get(
            "registered_asset_intake_copy_plan_blocked_map_count"),
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
        "registered_asset_handoff_present": summary.get(
            "registered_asset_handoff_present"),
        "registered_asset_handoff_status": summary.get(
            "registered_asset_handoff_status"),
        "registered_asset_handoff_blocker_reason": summary.get(
            "registered_asset_handoff_blocker_reason"),
        "registered_asset_handoff_copy_script_mode": summary.get(
            "registered_asset_handoff_copy_script_mode"),
        "registered_asset_handoff_missing_map_count_after_plan": (
            summary.get(
                "registered_asset_handoff_missing_map_count_after_plan")),
        "registered_asset_handoff_actionable_copy_plan_count": summary.get(
            "registered_asset_handoff_actionable_copy_plan_count"),
        "registered_asset_handoff_copy_plan_unblocked_map_count": summary.get(
            "registered_asset_handoff_copy_plan_unblocked_map_count"),
        "registered_asset_handoff_copy_plan_blocked_map_count": summary.get(
            "registered_asset_handoff_copy_plan_blocked_map_count"),
        "registered_asset_handoff_status_counts": summary.get(
            "registered_asset_handoff_status_counts"),
        "registered_asset_handoff_not_recorded_count": summary.get(
            "registered_asset_handoff_not_recorded_count"),
        "registered_asset_handoff_licensed_asset_required_count": summary.get(
            "registered_asset_handoff_licensed_asset_required_count"),
        "registered_asset_handoff_copy_plan_unblocked_count": summary.get(
            "registered_asset_handoff_copy_plan_unblocked_count"),
        "registered_asset_handoff_copy_plan_blocked_count": summary.get(
            "registered_asset_handoff_copy_plan_blocked_count"),
        "moonlab_full_game_plan_ledger_recorded": summary.get(
            "moonlab_full_game_plan_ledger_recorded"),
        "moonlab_full_game_plan_ledger_mismatch_count": summary.get(
            "moonlab_full_game_plan_ledger_mismatch_count"),
        "moonlab_full_game_plan_ledger_top_level_mismatches": summary.get(
            "moonlab_full_game_plan_ledger_top_level_mismatches"),
        "moonlab_full_game_plan_ledger_row_count": summary.get(
            "moonlab_full_game_plan_ledger_row_count"),
        "moonlab_full_game_plan_ledger_expected_row_count": summary.get(
            "moonlab_full_game_plan_ledger_expected_row_count"),
        "moonlab_full_game_plan_ledger_invalid_row_count": summary.get(
            "moonlab_full_game_plan_ledger_invalid_row_count"),
        "moonlab_full_game_plan_ledger_duplicate_row_maps": summary.get(
            "moonlab_full_game_plan_ledger_duplicate_row_maps"),
        "moonlab_full_game_plan_ledger_missing_row_maps": summary.get(
            "moonlab_full_game_plan_ledger_missing_row_maps"),
        "moonlab_full_game_plan_ledger_unexpected_row_maps": summary.get(
            "moonlab_full_game_plan_ledger_unexpected_row_maps"),
        "moonlab_full_game_plan_ledger_row_mismatches": summary.get(
            "moonlab_full_game_plan_ledger_row_mismatches"),
        "moonlab_full_game_plan_ledger_route_contract_mismatch_maps": (
            summary.get(
                "moonlab_full_game_plan_ledger_route_contract_mismatch_maps")),
        "moonlab_full_game_plan_ledger_expected_status": summary.get(
            "moonlab_full_game_plan_ledger_expected_status"),
        "moonlab_full_game_plan_ledger_recorded_status": summary.get(
            "moonlab_full_game_plan_ledger_recorded_status"),
        "moonlab_coverage_ledger_recorded": summary.get(
            "moonlab_coverage_ledger_recorded"),
        "moonlab_coverage_ledger_result_status": summary.get(
            "moonlab_coverage_ledger_result_status"),
        "moonlab_coverage_ledger_simulator_backend_completed": summary.get(
            "moonlab_coverage_ledger_simulator_backend_completed"),
        "moonlab_coverage_ledger_mismatch_count": summary.get(
            "moonlab_coverage_ledger_mismatch_count"),
        "moonlab_coverage_ledger_mismatches": summary.get(
            "moonlab_coverage_ledger_mismatches"),
        "moonlab_coverage_ledger_missing_required_artifact_count": (
            summary.get(
                "moonlab_coverage_ledger_missing_required_artifact_count")),
        "moonlab_coverage_ledger_observed_coverage_status": summary.get(
            "moonlab_coverage_ledger_observed_coverage_status"),
        "moonlab_coverage_ledger_observed_missing_map_count": summary.get(
            "moonlab_coverage_ledger_observed_missing_map_count"),
        "moonlab_coverage_ledger_observed_asset_requirement_status": (
            summary.get(
                "moonlab_coverage_ledger_observed_asset_requirement_status")),
        "moonlab_coverage_ledger_observed_asset_requirements_satisfied": (
            summary.get(
                "moonlab_coverage_ledger_observed_asset_requirements_satisfied")),
        "moonlab_selected_job_result_ledger_recorded": summary.get(
            "moonlab_selected_job_result_ledger_recorded"),
        "moonlab_selected_job_result_ledger_mismatch_count": summary.get(
            "moonlab_selected_job_result_ledger_mismatch_count"),
        "moonlab_selected_job_result_ledger_count_mismatches": summary.get(
            "moonlab_selected_job_result_ledger_count_mismatches"),
        "moonlab_selected_job_spec_job_count": summary.get(
            "moonlab_selected_job_spec_job_count"),
        "moonlab_selected_job_result_job_count": summary.get(
            "moonlab_selected_job_result_job_count"),
        "moonlab_selected_job_missing_result_count": summary.get(
            "moonlab_selected_job_missing_result_count"),
        "moonlab_selected_job_missing_result_ids": summary.get(
            "moonlab_selected_job_missing_result_ids"),
        "moonlab_selected_job_unexpected_result_count": summary.get(
            "moonlab_selected_job_unexpected_result_count"),
        "moonlab_selected_job_unexpected_result_ids": summary.get(
            "moonlab_selected_job_unexpected_result_ids"),
        "moonlab_selected_job_duplicate_spec_ids": summary.get(
            "moonlab_selected_job_duplicate_spec_ids"),
        "moonlab_selected_job_duplicate_result_ids": summary.get(
            "moonlab_selected_job_duplicate_result_ids"),
        "moonlab_selected_job_invalid_spec_job_count": summary.get(
            "moonlab_selected_job_invalid_spec_job_count"),
        "moonlab_selected_job_invalid_result_job_count": summary.get(
            "moonlab_selected_job_invalid_result_job_count"),
        "moonlab_selected_job_non_completed_simulator_count": summary.get(
            "moonlab_selected_job_non_completed_simulator_count"),
        "moonlab_selected_job_non_completed_simulator_ids": summary.get(
            "moonlab_selected_job_non_completed_simulator_ids"),
        "moonlab_selected_job_missing_required_artifact_count": summary.get(
            "moonlab_selected_job_missing_required_artifact_count"),
        "moonlab_selected_job_missing_required_artifact_ids": summary.get(
            "moonlab_selected_job_missing_required_artifact_ids"),
        "moonlab_selected_job_required_artifact_count": summary.get(
            "moonlab_selected_job_required_artifact_count"),
        "moonlab_selected_job_artifact_evidence_count": summary.get(
            "moonlab_selected_job_artifact_evidence_count"),
        "moonlab_selected_job_artifact_evidence_mismatch_count": summary.get(
            "moonlab_selected_job_artifact_evidence_mismatch_count"),
        "moonlab_selected_job_artifact_evidence_mismatch_job_ids": summary.get(
            "moonlab_selected_job_artifact_evidence_mismatch_job_ids"),
        "moonlab_selected_job_artifact_missing_evidence_job_ids": summary.get(
            "moonlab_selected_job_artifact_missing_evidence_job_ids"),
        "moonlab_selected_job_artifact_path_mismatch_job_ids": summary.get(
            "moonlab_selected_job_artifact_path_mismatch_job_ids"),
        "moonlab_selected_job_artifact_not_existing_job_ids": summary.get(
            "moonlab_selected_job_artifact_not_existing_job_ids"),
        "moonlab_selected_job_artifact_evidence_mismatches": summary.get(
            "moonlab_selected_job_artifact_evidence_mismatches"),
        "moonlab_submission_packet_ledger_recorded": summary.get(
            "moonlab_submission_packet_ledger_recorded"),
        "moonlab_submission_packet_ledger_mismatch_count": summary.get(
            "moonlab_submission_packet_ledger_mismatch_count"),
        "moonlab_submission_packet_ledger_schema_mismatches": summary.get(
            "moonlab_submission_packet_ledger_schema_mismatches"),
        "moonlab_submission_packet_ledger_count_mismatches": summary.get(
            "moonlab_submission_packet_ledger_count_mismatches"),
        "moonlab_submission_packet_spec_candidate_count": summary.get(
            "moonlab_submission_packet_spec_candidate_count"),
        "moonlab_submission_packet_candidate_count": summary.get(
            "moonlab_submission_packet_candidate_count"),
        "moonlab_submission_packet_missing_candidate_ids": summary.get(
            "moonlab_submission_packet_missing_candidate_ids"),
        "moonlab_submission_packet_unexpected_candidate_ids": summary.get(
            "moonlab_submission_packet_unexpected_candidate_ids"),
        "moonlab_submission_packet_duplicate_candidate_ids": summary.get(
            "moonlab_submission_packet_duplicate_candidate_ids"),
        "moonlab_submission_packet_invalid_candidate_count": summary.get(
            "moonlab_submission_packet_invalid_candidate_count"),
        "moonlab_submission_packet_row_mismatch_job_ids": summary.get(
            "moonlab_submission_packet_row_mismatch_job_ids"),
        "moonlab_submission_packet_row_mismatches": summary.get(
            "moonlab_submission_packet_row_mismatches"),
        "moonlab_hardware_record_template_ledger_recorded": summary.get(
            "moonlab_hardware_record_template_ledger_recorded"),
        "moonlab_hardware_record_template_ledger_mismatch_count": summary.get(
            "moonlab_hardware_record_template_ledger_mismatch_count"),
        "moonlab_hardware_record_template_schema_mismatches": summary.get(
            "moonlab_hardware_record_template_schema_mismatches"),
        "moonlab_hardware_record_template_source_mismatches": summary.get(
            "moonlab_hardware_record_template_source_mismatches"),
        "moonlab_hardware_record_template_row_mismatch_count": summary.get(
            "moonlab_hardware_record_template_row_mismatch_count"),
        "moonlab_hardware_record_template_row_mismatches": summary.get(
            "moonlab_hardware_record_template_row_mismatches"),
        "moonlab_hardware_record_template_job_id": summary.get(
            "moonlab_hardware_record_template_job_id"),
        "moonlab_hardware_record_template_candidate_digest": summary.get(
            "moonlab_hardware_record_template_candidate_digest"),
        "moonlab_hardware_record_template_candidate_found": summary.get(
            "moonlab_hardware_record_template_candidate_found"),
        "moonlab_hardware_record_template_candidate_job_count": summary.get(
            "moonlab_hardware_record_template_candidate_job_count"),
        "moonlab_hardware_record_template_validation_contract_present": (
            summary.get(
                "moonlab_hardware_record_template_validation_contract_present")),
        "moonlab_hardware_submission_scope_ledger_recorded": summary.get(
            "moonlab_hardware_submission_scope_ledger_recorded"),
        "moonlab_hardware_submission_scope_ledger_mismatch_count": summary.get(
            "moonlab_hardware_submission_scope_ledger_mismatch_count"),
        "moonlab_hardware_submission_scope_schema_mismatches": summary.get(
            "moonlab_hardware_submission_scope_schema_mismatches"),
        "moonlab_submission_bundle_mismatches": summary.get(
            "moonlab_submission_bundle_mismatches"),
        "moonlab_hardware_submission_scope_mismatches": summary.get(
            "moonlab_hardware_submission_scope_mismatches"),
        "moonlab_hardware_submission_scope_expected_status": summary.get(
            "moonlab_hardware_submission_scope_expected_status"),
        "moonlab_hardware_submission_scope_recorded_status": summary.get(
            "moonlab_hardware_submission_scope_recorded_status"),
        "moonlab_hardware_submission_scope_expected_ready": summary.get(
            "moonlab_hardware_submission_scope_expected_ready"),
        "moonlab_hardware_submission_scope_recorded_ready": summary.get(
            "moonlab_hardware_submission_scope_recorded_ready"),
        "moonlab_hardware_submission_scope_expected_candidate_count": (
            summary.get(
                "moonlab_hardware_submission_scope_expected_candidate_count")),
        "moonlab_hardware_submission_scope_recorded_candidate_count": (
            summary.get(
                "moonlab_hardware_submission_scope_recorded_candidate_count")),
        "moonlab_hardware_result_ledger_recorded": summary.get(
            "moonlab_hardware_result_ledger_recorded"),
        "moonlab_hardware_result_ledger_mismatch_count": summary.get(
            "moonlab_hardware_result_ledger_mismatch_count"),
        "moonlab_hardware_result_ledger_schema_mismatches": summary.get(
            "moonlab_hardware_result_ledger_schema_mismatches"),
        "moonlab_hardware_result_ledger_count_mismatches": summary.get(
            "moonlab_hardware_result_ledger_count_mismatches"),
        "moonlab_hardware_result_job_count": summary.get(
            "moonlab_hardware_result_job_count"),
        "moonlab_hardware_result_row_count": summary.get(
            "moonlab_hardware_result_row_count"),
        "moonlab_hardware_result_completed_row_count": summary.get(
            "moonlab_hardware_result_completed_row_count"),
        "moonlab_hardware_result_reported_completed_job_count": summary.get(
            "moonlab_hardware_result_reported_completed_job_count"),
        "moonlab_hardware_result_row_mismatch_job_ids": summary.get(
            "moonlab_hardware_result_row_mismatch_job_ids"),
        "moonlab_hardware_result_row_mismatches": summary.get(
            "moonlab_hardware_result_row_mismatches"),
        "moonlab_hardware_result_duplicate_job_ids": summary.get(
            "moonlab_hardware_result_duplicate_job_ids"),
        "full_game_route_contract_schema": summary.get(
            "route_contract_schema"),
        "full_game_route_contract_map_count": summary.get(
            "route_contract_map_count"),
        "full_game_route_contracts_complete": summary.get(
            "route_contracts_complete"),
        "full_game_missing_route_contract_maps": summary.get(
            "missing_route_contract_maps"),
        "covered_route_contract_authority_ready_count": summary.get(
            "covered_route_contract_authority_ready_count"),
        "covered_route_contract_authority_complete": summary.get(
            "covered_route_contract_authority_complete"),
        "covered_route_contract_authority_blocked_maps": summary.get(
            "covered_route_contract_authority_blocked_maps"),
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
        (
            "Covered route authority: "
            f"{summary.get('covered_route_contract_authority_ready_count')} "
            f"/ {summary.get('covered_map_count')} "
            f"(complete={summary.get('covered_route_contract_authority_complete')})"
        ),
        (
            "Registered asset handoff: "
            f"present={summary.get('registered_asset_handoff_present')} "
            f"not_recorded={summary.get('registered_asset_handoff_not_recorded_count')} "
            f"licensed_required={summary.get('registered_asset_handoff_licensed_asset_required_count')} "
            f"copy_unblocked={summary.get('registered_asset_handoff_copy_plan_unblocked_count')} "
            f"copy_blocked={summary.get('registered_asset_handoff_copy_plan_blocked_count')}"
        ),
        (
            "Full-game plan ledger: "
            f"recorded={summary.get('moonlab_full_game_plan_ledger_recorded')} "
            f"rows={summary.get('moonlab_full_game_plan_ledger_row_count')} "
            f"/ {summary.get('moonlab_full_game_plan_ledger_expected_row_count')} "
            "mismatches="
            f"{summary.get('moonlab_full_game_plan_ledger_mismatch_count')}"
        ),
        (
            "Moonlab coverage ledger: "
            f"recorded={summary.get('moonlab_coverage_ledger_recorded')} "
            f"status={summary.get('moonlab_coverage_ledger_result_status')} "
            "backend_completed="
            f"{summary.get('moonlab_coverage_ledger_simulator_backend_completed')} "
            f"mismatches={summary.get('moonlab_coverage_ledger_mismatch_count')}"
        ),
        (
            "Moonlab selected job ledger: "
            "recorded="
            f"{summary.get('moonlab_selected_job_result_ledger_recorded')} "
            f"specs={summary.get('moonlab_selected_job_spec_job_count')} "
            f"results={summary.get('moonlab_selected_job_result_job_count')} "
            "missing_results="
            f"{summary.get('moonlab_selected_job_missing_result_count')} "
            "artifact_mismatches="
            f"{summary.get('moonlab_selected_job_artifact_evidence_mismatch_count')} "
            "mismatches="
            f"{summary.get('moonlab_selected_job_result_ledger_mismatch_count')}"
        ),
        (
            "Moonlab submission packet ledger: "
            "recorded="
            f"{summary.get('moonlab_submission_packet_ledger_recorded')} "
            f"candidates={summary.get('moonlab_submission_packet_candidate_count')} "
            f"/ {summary.get('moonlab_submission_packet_spec_candidate_count')} "
            "mismatches="
            f"{summary.get('moonlab_submission_packet_ledger_mismatch_count')}"
        ),
        (
            "Moonlab hardware record template ledger: "
            "recorded="
            f"{summary.get('moonlab_hardware_record_template_ledger_recorded')} "
            "job="
            f"{summary.get('moonlab_hardware_record_template_job_id')} "
            "mismatches="
            f"{summary.get('moonlab_hardware_record_template_ledger_mismatch_count')}"
        ),
        (
            "Moonlab hardware submission scope ledger: "
            "recorded="
            f"{summary.get('moonlab_hardware_submission_scope_ledger_recorded')} "
            "ready="
            f"{summary.get('moonlab_hardware_submission_scope_recorded_ready')} "
            "mismatches="
            f"{summary.get('moonlab_hardware_submission_scope_ledger_mismatch_count')}"
        ),
        (
            "Moonlab hardware result ledger: "
            "recorded="
            f"{summary.get('moonlab_hardware_result_ledger_recorded')} "
            "rows="
            f"{summary.get('moonlab_hardware_result_row_count')} "
            "mismatches="
            f"{summary.get('moonlab_hardware_result_ledger_mismatch_count')}"
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
