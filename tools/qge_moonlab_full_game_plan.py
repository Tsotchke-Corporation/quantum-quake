#!/usr/bin/env python3
"""Build an explicit Moonlab full-game deployment plan.

The plan is a deployment ledger, not a completion claim. It joins canonical map
coverage, local asset availability, breadth evidence, and Moonlab job status so
the remaining work for "the entire game runs in Moonlab" is visible in one
artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_asset_inventory  # noqa: E402
import qge_breadth_evidence  # noqa: E402
import qge_full_game_route_contracts  # noqa: E402
import qge_map_sets  # noqa: E402


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


def string_list(value: Any) -> list[str]:
    return [item for item in list_or_empty(value) if isinstance(item, str)]


def resolve_publication_manifest(path: Path) -> Path:
    if path.is_dir():
        path = path / "publication_manifest.json"
    return path


def resolve_path(value: Any, *, base_dir: Path | None = None) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    if base_dir is not None and (base_dir / path).exists():
        return base_dir / path
    return REPO_ROOT / path


def resource_artifact_path(
    manifest: dict[str, Any],
    name: str,
    *,
    manifest_path: Path | None = None,
) -> Path | None:
    resource = dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(
        "resource"))
    artifact = dict_or_empty(resource.get(name))
    base_dir = manifest_path.parent if manifest_path is not None else None
    return resolve_path(artifact.get("path"), base_dir=base_dir)


def load_resource_json(
    manifest: dict[str, Any],
    name: str,
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any] | None:
    path = resource_artifact_path(manifest, name, manifest_path=manifest_path)
    if path is None or not path.is_file():
        return None
    return load_json(path)


def load_breadth_evidence_for_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any] | None:
    source_inputs = dict_or_empty(manifest.get("source_inputs"))
    base_dir = manifest_path.parent if manifest_path is not None else None
    path = resolve_path(source_inputs.get("breadth_evidence"), base_dir=base_dir)
    if path is None:
        return None
    if path.is_dir():
        for candidate in (
            path / "breadth_evidence.json",
            path / "qge_breadth_icc_evidence.json",
        ):
            if candidate.is_file():
                path = candidate
                break
    if not path.is_file():
        return None
    return load_json(path)


def coverage_from_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    resource = load_resource_json(
        manifest, "full_game_map_coverage", manifest_path=manifest_path)
    if resource is not None:
        return resource
    runtime = dict_or_empty(manifest.get("runtime_summary"))
    coverage = runtime.get("full_game_map_coverage")
    if isinstance(coverage, dict):
        return coverage
    return qge_breadth_evidence.build_full_game_map_coverage(
        list_or_empty(runtime.get("breadth_maps")))


def asset_inventory_from_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
    asset_root: Path = qge_asset_inventory.DEFAULT_ASSET_ROOT,
    map_set: str = qge_map_sets.DEFAULT_FULL_GAME_MAP_SET,
) -> dict[str, Any]:
    resource = load_resource_json(
        manifest, "asset_inventory", manifest_path=manifest_path)
    if resource is not None:
        return resource
    return qge_asset_inventory.build_inventory(asset_root, map_set=map_set)


def breadth_runs_by_map(breadth_evidence: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    runs_by_map: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(breadth_evidence, dict):
        return runs_by_map
    for run in list_or_empty(breadth_evidence.get("matrix_runs")):
        if not isinstance(run, dict):
            continue
        map_name = qge_breadth_evidence.canonical_map_name(run.get("map"))
        if map_name is None:
            continue
        runs_by_map.setdefault(map_name, []).append(run)
    return runs_by_map


def map_evidence_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "matrix_file": run.get("matrix_file"),
        "capture_dir": run.get("capture_dir") or run.get("source_path"),
        "ready": run.get("ready"),
        "ready_for_complete_claim": run.get("ready_for_complete_claim"),
        "moonlab_authority_ready": run.get("moonlab_authority_ready"),
        "fallback_count": run.get("fallback_count"),
        "surrogate_count": run.get("surrogate_count"),
        "cpu_idwt_count": run.get("cpu_idwt_count"),
        "native_bridge_count": run.get("native_bridge_count"),
        "runtime_backend_probe_resolved": run.get(
            "runtime_backend_probe_resolved"),
        "runtime_backend_probe_missing_targets": run.get(
            "runtime_backend_probe_missing_targets"),
        "route_contract_authority_ready": run.get(
            "route_contract_authority_ready"),
        "route_contract_authority_blockers": run.get(
            "route_contract_authority_blockers"),
        "route_contract_authority": run.get("route_contract_authority"),
    }


def post_install_command(
    registered_asset_intake: dict[str, Any],
    command_kind: str,
) -> str | None:
    verification = dict_or_empty(
        registered_asset_intake.get("post_install_verification"))
    for command in list_or_empty(verification.get("commands")):
        if not isinstance(command, dict):
            continue
        if command.get("kind") == command_kind:
            shell_command = command.get("shell_command")
            if isinstance(shell_command, str) and shell_command:
                return shell_command
    return None


def registered_asset_handoff_summary(
    registered_asset_intake: dict[str, Any] | None,
) -> dict[str, Any]:
    intake = dict_or_empty(registered_asset_intake)
    if not intake:
        return {
            "schema": "qge.moonlab_registered_asset_handoff.v0",
            "present": False,
            "registered_asset_intake_status": None,
        }
    discovery = dict_or_empty(intake.get("candidate_discovery"))
    discovery_command = intake.get("candidate_discovery_command")
    if not isinstance(discovery_command, str) or not discovery_command:
        discovery_command = discovery.get("shell_command")
    return {
        "schema": "qge.moonlab_registered_asset_handoff.v0",
        "present": True,
        "registered_asset_intake_status": intake.get("status"),
        "manual_registered_asset_required": bool(
            intake.get("manual_registered_asset_required")),
        "registered_asset_blocker_reason": intake.get(
            "registered_asset_blocker_reason"),
        "copy_script_mode": intake.get("copy_script_mode"),
        "no_candidate_asset_copy_plan": bool(
            intake.get("no_candidate_asset_copy_plan")),
        "missing_map_count_after_plan": intake.get(
            "missing_map_count_after_plan"),
        "missing_maps_after_plan": string_list(
            intake.get("missing_maps_after_plan")),
        "actionable_copy_plan_count": intake.get(
            "actionable_copy_plan_count"),
        "copy_plan_unblocked_map_count": intake.get(
            "copy_plan_unblocked_map_count"),
        "copy_plan_unblocked_maps": string_list(
            intake.get("copy_plan_unblocked_maps")),
        "copy_plan_blocked_map_count": intake.get(
            "copy_plan_blocked_map_count"),
        "copy_plan_blocked_maps": string_list(
            intake.get("copy_plan_blocked_maps")),
        "registered_asset_discovery_command": discovery_command,
        "post_install_asset_inventory_command": post_install_command(
            intake, "asset_inventory"),
        "post_install_capture_queue_command": post_install_command(
            intake, "capture_queue"),
    }


def asset_handoff_status_for_map(
    map_name: str,
    *,
    has_asset: bool,
    handoff: dict[str, Any],
) -> str:
    if has_asset:
        return "asset_present"
    if not handoff.get("present"):
        return "not_recorded"
    if map_name in set(string_list(handoff.get("copy_plan_unblocked_maps"))):
        return "copy_plan_unblocked"
    if map_name in set(string_list(handoff.get("copy_plan_blocked_maps"))):
        return "copy_plan_blocked"
    if map_name in set(string_list(handoff.get("missing_maps_after_plan"))):
        if handoff.get("no_candidate_asset_copy_plan") is True:
            return "licensed_asset_required"
        return "missing_after_copy_plan"
    return "not_blocked"


def next_action_for_map(
    *,
    is_covered: bool,
    has_asset: bool,
    asset_handoff_status: str,
) -> str:
    if is_covered:
        return "keep_breadth_evidence"
    if has_asset:
        return "run_full_game_capture_queue_job"
    if asset_handoff_status == "copy_plan_unblocked":
        return "run_registered_asset_copy_plan"
    if asset_handoff_status == "copy_plan_blocked":
        return "resolve_blocked_registered_asset_copy_plan"
    if asset_handoff_status == "licensed_asset_required":
        return "provide_licensed_registered_asset"
    return "install_registered_bsp_asset"


def map_deployment_rows(
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    breadth_evidence: dict[str, Any] | None,
    registered_asset_intake: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    map_set = coverage.get("map_set") or inventory.get("map_set")
    if not isinstance(map_set, str) or not map_set:
        map_set = qge_map_sets.DEFAULT_FULL_GAME_MAP_SET
    target_maps = qge_map_sets.map_targets_for_set(map_set)
    covered = {
        item for item in list_or_empty(coverage.get("covered_maps"))
        if isinstance(item, str)
    }
    available = {
        item for item in list_or_empty(inventory.get("available_maps"))
        if isinstance(item, str)
    }
    runs_by_map = breadth_runs_by_map(breadth_evidence)
    handoff = registered_asset_handoff_summary(registered_asset_intake)
    rows = []
    for map_name in target_maps:
        evidence = [map_evidence_summary(run)
                    for run in runs_by_map.get(map_name, [])]
        route_contract = qge_full_game_route_contracts.route_contract_for_map(
            map_name,
            map_set=map_set,
        )
        is_covered = map_name in covered
        has_asset = map_name in available
        asset_handoff_status = asset_handoff_status_for_map(
            map_name,
            has_asset=has_asset,
            handoff=handoff,
        )
        if is_covered:
            deployment_status = "simulator_native_evidence_present"
        elif has_asset:
            deployment_status = "capture_required"
        else:
            deployment_status = "blocked_asset_unavailable"
        next_action = next_action_for_map(
            is_covered=is_covered,
            has_asset=has_asset,
            asset_handoff_status=asset_handoff_status,
        )
        rows.append({
            "map": map_name,
            "coverage_status": "covered" if is_covered else "missing",
            "asset_status": "available" if has_asset else "asset_unavailable",
            "asset_handoff_status": asset_handoff_status,
            "route_profile": route_contract["route_profile"],
            "route_contract": route_contract,
            "deployment_status": deployment_status,
            "evidence": evidence,
            "next_action": next_action,
        })
    return rows


def deployment_status(
    map_rows: list[dict[str, Any]],
    coverage: dict[str, Any],
) -> str:
    if not qge_map_sets.is_registered_full_game_map_set(
        coverage.get("map_set")
    ):
        return "blocked_non_registered_map_set"
    if coverage.get("status") == "complete":
        return "map_coverage_complete"
    if any(row.get("deployment_status") == "blocked_asset_unavailable"
           for row in map_rows):
        return "blocked_asset_unavailable"
    if any(row.get("deployment_status") == "capture_required"
           for row in map_rows):
        return "captures_required"
    return "partial_unknown"


def build_deployment_requirements(
    *,
    status: str,
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    map_rows: list[dict[str, Any]],
    moonlab_job_results: dict[str, Any] | None = None,
    submission_packet: dict[str, Any] | None = None,
    hardware_record_template: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    capture_required = [
        row["map"] for row in map_rows
        if row.get("deployment_status") == "capture_required"
    ]
    asset_unavailable = [
        row["map"] for row in map_rows
        if row.get("deployment_status") == "blocked_asset_unavailable"
    ]
    missing_route_contracts = [
        row["map"] for row in map_rows
        if not dict_or_empty(row.get("route_contract"))
    ]
    route_contract_count = len(map_rows) - len(missing_route_contracts)
    route_contracts_complete = (
        route_contract_count == len(map_rows) and
        not missing_route_contracts
    )
    covered_route_authority_blocked_maps = [
        row["map"] for row in map_rows
        if row.get("coverage_status") == "covered" and
        not any(
            dict_or_empty(evidence).get(
                "route_contract_authority_ready") is True
            for evidence in list_or_empty(row.get("evidence"))
        )
    ]
    covered_route_authority_complete = (
        not covered_route_authority_blocked_maps
    )
    job_results = dict_or_empty(moonlab_job_results)
    packet = dict_or_empty(submission_packet)
    template = dict_or_empty(hardware_record_template)
    return [
        {
            "id": "registered_bsp_assets",
            "status": (
                "pass" if bool(inventory.get("full_game_asset_ready"))
                else "blocked"
            ),
            "available_map_count": inventory.get("available_map_count"),
            "missing_map_count": inventory.get("missing_map_count"),
            "blocked_maps": asset_unavailable,
        },
        {
            "id": "strict_capture_matrix_all_maps",
            "status": (
                "pass" if coverage.get("status") == "complete"
                else "partial"
            ),
            "covered_map_count": coverage.get("covered_map_count"),
            "target_map_count": coverage.get("target_map_count"),
            "capture_required_maps": capture_required,
        },
        {
            "id": "full_game_route_contracts",
            "status": "pass" if route_contracts_complete else "blocked",
            "route_contract_schema": (
                qge_full_game_route_contracts.ROUTE_CONTRACT_SCHEMA),
            "route_contract_map_count": route_contract_count,
            "target_map_count": len(map_rows),
            "missing_route_contract_maps": missing_route_contracts,
        },
        {
            "id": "covered_route_contract_authority",
            "status": (
                "pass" if covered_route_authority_complete else "blocked"
            ),
            "blocked_maps": covered_route_authority_blocked_maps,
        },
        {
            "id": "moonlab_selected_jobs_replayable",
            "status": job_results.get("overall_status"),
            "completed_simulator_job_count": job_results.get(
                "completed_simulator_job_count"),
            "completed_native_replay_job_count": job_results.get(
                "completed_native_replay_job_count"),
            "hardware_submitted_job_count": job_results.get(
                "hardware_submitted_job_count"),
        },
        {
            "id": "moonlab_hardware_return_record",
            "status": (
                "template_ready"
                if template.get("record_schema") == "qge.moonlab_hardware_record.v0"
                else "missing_template"
            ),
            "candidate_job_count": packet.get("hardware_candidate_job_count"),
            "ready_candidate_count": packet.get("ready_candidate_count"),
            "submitted_candidate_count": packet.get("submitted_candidate_count"),
            "hardware_record_template_schema": template.get("schema"),
        },
        {
            "id": "full_game_moonlab_claim",
            "status": "not_claimed" if status != "map_coverage_complete"
            else "map_coverage_complete_hardware_still_unclaimed",
            "whole_game_moonlab_deployment_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "hardware_quantum_advantage_claimed": False,
        },
    ]


def build_plan(
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    *,
    source_path: Path | str | None = None,
    breadth_evidence: dict[str, Any] | None = None,
    moonlab_job_results: dict[str, Any] | None = None,
    submission_packet: dict[str, Any] | None = None,
    hardware_record_template: dict[str, Any] | None = None,
    registered_asset_intake: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = map_deployment_rows(
        coverage,
        inventory,
        breadth_evidence,
        registered_asset_intake,
    )
    status = deployment_status(rows, coverage)
    handoff = registered_asset_handoff_summary(registered_asset_intake)
    capture_required = [
        row["map"] for row in rows
        if row.get("deployment_status") == "capture_required"
    ]
    asset_unavailable = [
        row["map"] for row in rows
        if row.get("deployment_status") == "blocked_asset_unavailable"
    ]
    route_contracts = {
        row["map"]: row["route_contract"]
        for row in rows
        if isinstance(row.get("map"), str) and
        dict_or_empty(row.get("route_contract"))
    }
    missing_route_contract_maps = [
        row["map"] for row in rows
        if isinstance(row.get("map"), str) and
        not dict_or_empty(row.get("route_contract"))
    ]
    route_contracts_complete = (
        len(route_contracts) == len(rows) and
        not missing_route_contract_maps
    )
    covered_route_authority_blocked_maps = [
        row["map"] for row in rows
        if row.get("coverage_status") == "covered" and
        not any(
            dict_or_empty(evidence).get(
                "route_contract_authority_ready") is True
            for evidence in list_or_empty(row.get("evidence"))
        )
    ]
    covered_route_authority_ready_count = (
        len([
            row for row in rows
            if row.get("coverage_status") == "covered"
        ]) - len(covered_route_authority_blocked_maps)
    )
    covered_route_authority_complete = (
        not covered_route_authority_blocked_maps
    )
    return {
        "schema": "qge.moonlab_full_game_deployment_plan.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path) if source_path is not None else None,
        "status": status,
        "map_set": coverage.get("map_set") or inventory.get("map_set"),
        "target_map_count": coverage.get("target_map_count"),
        "covered_map_count": coverage.get("covered_map_count"),
        "missing_map_count": coverage.get("missing_map_count"),
        "asset_available_map_count": inventory.get("available_map_count"),
        "asset_missing_map_count": inventory.get("missing_map_count"),
        "capture_required_map_count": len(capture_required),
        "capture_required_maps": capture_required,
        "asset_unavailable_map_count": len(asset_unavailable),
        "asset_unavailable_maps": asset_unavailable,
        "registered_asset_handoff": handoff,
        "route_contract_schema": (
            qge_full_game_route_contracts.ROUTE_CONTRACT_SCHEMA),
        "route_contract_map_count": len(route_contracts),
        "route_contracts_complete": route_contracts_complete,
        "missing_route_contract_maps": missing_route_contract_maps,
        "covered_route_contract_authority_ready_count": (
            covered_route_authority_ready_count),
        "covered_route_contract_authority_complete": (
            covered_route_authority_complete),
        "covered_route_contract_authority_blocked_maps": (
            covered_route_authority_blocked_maps),
        "route_contracts": route_contracts,
        "map_deployment_rows": rows,
        "deployment_requirements": build_deployment_requirements(
            status=status,
            coverage=coverage,
            inventory=inventory,
            map_rows=rows,
            moonlab_job_results=moonlab_job_results,
            submission_packet=submission_packet,
            hardware_record_template=hardware_record_template,
        ),
        "claim_posture": {
            "whole_game_moonlab_deployment_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "hardware_quantum_advantage_claimed": False,
            "dense_70000_qubit_state_claimed": False,
        },
        "next_actions": [
            (
                "Use registered_asset_handoff and per-map "
                "asset_handoff_status before treating asset_unavailable_maps "
                "as copyable."
            ),
            "Install registered BSP assets for asset_unavailable_maps.",
            "Run strict capture queue jobs for every capture_required map.",
            "Rebuild breadth evidence and publication pack after each successful map batch.",
            "Submit bounded Moonlab hardware candidates only through the submission packet and hardware record template.",
        ],
        "limits": [
            "This plan is a full-game deployment ledger, not proof that the whole game currently runs in Moonlab.",
            "Covered maps are simulator/native capture evidence, not whole-game hardware execution.",
            "Hardware advantage remains unclaimed until real hardware-return records and comparisons exist.",
        ],
    }


def build_plan_from_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
    asset_root: Path = qge_asset_inventory.DEFAULT_ASSET_ROOT,
) -> dict[str, Any]:
    coverage = coverage_from_manifest(manifest, manifest_path=manifest_path)
    inventory = asset_inventory_from_manifest(
        manifest,
        manifest_path=manifest_path,
        asset_root=asset_root,
        map_set=coverage.get("map_set")
        or qge_map_sets.DEFAULT_FULL_GAME_MAP_SET,
    )
    breadth = load_breadth_evidence_for_manifest(
        manifest, manifest_path=manifest_path)
    return build_plan(
        coverage,
        inventory,
        source_path=manifest_path,
        breadth_evidence=breadth,
        moonlab_job_results=load_resource_json(
            manifest, "moonlab_job_results", manifest_path=manifest_path),
        submission_packet=load_resource_json(
            manifest, "moonlab_submission_packet", manifest_path=manifest_path),
        hardware_record_template=load_resource_json(
            manifest,
            "moonlab_hardware_record_template",
            manifest_path=manifest_path,
        ),
        registered_asset_intake=load_resource_json(
            manifest, "registered_asset_intake", manifest_path=manifest_path),
    )


def build_icc_evidence(
    plan: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_moonlab_full_game_plan",
        "completion_reason": "qge_moonlab_full_game_deployment_plan_recorded",
        "moonlab_full_game_plan_file": str(out_path) if out_path else None,
        "status": "success",
        "deployment_status": plan.get("status"),
        "map_set": plan.get("map_set"),
        "target_map_count": plan.get("target_map_count"),
        "covered_map_count": plan.get("covered_map_count"),
        "missing_map_count": plan.get("missing_map_count"),
        "asset_unavailable_map_count": plan.get(
            "asset_unavailable_map_count"),
        "capture_required_map_count": plan.get("capture_required_map_count"),
        "registered_asset_handoff_present": dict_or_empty(
            plan.get("registered_asset_handoff")).get("present"),
        "registered_asset_handoff_status": dict_or_empty(
            plan.get("registered_asset_handoff")).get(
                "registered_asset_intake_status"),
        "registered_asset_handoff_blocker_reason": dict_or_empty(
            plan.get("registered_asset_handoff")).get(
                "registered_asset_blocker_reason"),
        "registered_asset_handoff_copy_script_mode": dict_or_empty(
            plan.get("registered_asset_handoff")).get("copy_script_mode"),
        "registered_asset_handoff_missing_map_count_after_plan": (
            dict_or_empty(plan.get("registered_asset_handoff")).get(
                "missing_map_count_after_plan")),
        "registered_asset_handoff_actionable_copy_plan_count": (
            dict_or_empty(plan.get("registered_asset_handoff")).get(
                "actionable_copy_plan_count")),
        "registered_asset_handoff_copy_plan_unblocked_map_count": (
            dict_or_empty(plan.get("registered_asset_handoff")).get(
                "copy_plan_unblocked_map_count")),
        "registered_asset_handoff_copy_plan_blocked_map_count": (
            dict_or_empty(plan.get("registered_asset_handoff")).get(
                "copy_plan_blocked_map_count")),
        "route_contract_schema": plan.get("route_contract_schema"),
        "route_contract_map_count": plan.get("route_contract_map_count"),
        "route_contracts_complete": plan.get("route_contracts_complete"),
        "missing_route_contract_maps": plan.get(
            "missing_route_contract_maps"),
        "covered_route_contract_authority_ready_count": plan.get(
            "covered_route_contract_authority_ready_count"),
        "covered_route_contract_authority_complete": plan.get(
            "covered_route_contract_authority_complete"),
        "covered_route_contract_authority_blocked_maps": plan.get(
            "covered_route_contract_authority_blocked_maps"),
        "whole_game_moonlab_deployment_claimed": False,
        "whole_game_hardware_execution_claimed": False,
        "hardware_quantum_advantage_claimed": False,
        "dense_70000_qubit_state_claimed": False,
    }


def markdown_report(plan: dict[str, Any]) -> str:
    lines = [
        "# QGE Moonlab Full-Game Deployment Plan",
        "",
        f"Status: {plan['status']}",
        "",
        "| Map Set | Covered | Missing | Capture Required | Asset Unavailable |",
        "| --- | ---: | ---: | ---: | ---: |",
        (
            f"| {plan.get('map_set')} | "
            f"{plan.get('covered_map_count')} / {plan.get('target_map_count')} | "
            f"{plan.get('missing_map_count')} | "
            f"{plan.get('capture_required_map_count')} | "
            f"{plan.get('asset_unavailable_map_count')} |"
        ),
        "",
        (
            f"Route contracts: {plan.get('route_contract_map_count')} "
            f"(complete={plan.get('route_contracts_complete')})"
        ),
        (
            "Covered route authority: "
            f"{plan.get('covered_route_contract_authority_ready_count')} / "
            f"{plan.get('covered_map_count')} "
            f"(complete={plan.get('covered_route_contract_authority_complete')})"
        ),
        "",
        "## Registered Asset Handoff",
        "",
    ]
    handoff = dict_or_empty(plan.get("registered_asset_handoff"))
    lines.extend([
        f"Recorded: {handoff.get('present')}",
        f"Intake status: {handoff.get('registered_asset_intake_status')}",
        f"Blocker reason: {handoff.get('registered_asset_blocker_reason')}",
        f"Copy script mode: {handoff.get('copy_script_mode')}",
        (
            "Copy plan maps: "
            f"unblocked={handoff.get('copy_plan_unblocked_map_count')} "
            f"blocked={handoff.get('copy_plan_blocked_map_count')} "
            f"missing_after_plan={handoff.get('missing_map_count_after_plan')}"
        ),
        "",
        "| Map | Coverage | Asset | Asset Handoff | Route Class | Deployment Status | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for row in list_or_empty(plan.get("map_deployment_rows")):
        if not isinstance(row, dict):
            continue
        route_contract = dict_or_empty(row.get("route_contract"))
        lines.append(
            f"| {row.get('map')} | {row.get('coverage_status')} | "
            f"{row.get('asset_status')} | "
            f"{row.get('asset_handoff_status')} | "
            f"{route_contract.get('map_class') or ''} | "
            f"{row.get('deployment_status')} | "
            f"{row.get('next_action')} |"
        )
    lines.extend([
        "",
        "## Claim Posture",
        "",
        "- whole-game Moonlab deployment claimed: false",
        "- whole-game hardware execution claimed: false",
        "- hardware quantum advantage claimed: false",
        "- dense 70,000-qubit state claimed: false",
        "",
    ])
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
        manifest_path = resolve_publication_manifest(args.publication_pack)
        manifest = load_json(manifest_path)
        if manifest.get("schema") != "qge.publication_pack.v0":
            raise ValueError("input is not qge.publication_pack.v0")
        plan = build_plan_from_manifest(
            manifest,
            manifest_path=manifest_path,
            asset_root=args.asset_root,
        )
        write_json(args.out, plan)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(plan), encoding="utf-8")
        if args.icc_json:
            icc = build_icc_evidence(plan, out_path=args.out)
            write_json(args.icc_json, icc)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_moonlab_full_game_plan: {exc}", file=sys.stderr)
        return 1

    print(f"QGE_MOONLAB_FULL_GAME_PLAN {args.out}")
    if args.markdown:
        print(f"QGE_MOONLAB_FULL_GAME_PLAN_MARKDOWN {args.markdown}")
    if args.icc_json:
        print(f"QGE_MOONLAB_FULL_GAME_PLAN_ICC_EVIDENCE {args.icc_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
