#!/usr/bin/env python3
"""Build a Moonlab deployment gate for the Quake shareware episode.

This gate is intentionally narrower than qge_moonlab_deployment_gate.py.  It
allows a simulator/native Moonlab deployment claim only for the shareware
Episode 1 map set, while keeping registered full-game, hardware execution,
hardware advantage, and dense-state claims false.
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
import qge_map_sets  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402


PASS = "pass"
BLOCKED = "blocked"
READY_STATUS = "ready_for_shareware_moonlab_simulator_deployment_claim"
SHAREWARE_MAP_SET = qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET
SHAREWARE_MAPS = qge_map_sets.QUAKE_SHAREWARE_EPISODE_ONE_MAPS
REQUIRED_NATIVE_TARGETS = {
    "qge_context_get_or_create_render_acceleration",
    "qge_dwt_render",
    "qge_metal_init_common",
}
ALLOWED_JOB_RESULT_STATUSES = {
    "completed",
    "simulator_completed_hardware_not_submitted",
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


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def bool_true(value: Any) -> bool:
    return value is True


def int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default


def string_list(value: Any) -> list[str]:
    return [item for item in list_or_empty(value) if isinstance(item, str)]


def artifact_manifest_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> str | None:
    artifacts = dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(
        section))
    artifact = dict_or_empty(artifacts.get(name))
    path = artifact.get("path")
    if not isinstance(path, str) or not path:
        path = dict_or_empty(artifact.get("packed")).get("path")
    return path if isinstance(path, str) and path else None


def load_artifact_json(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any] | None:
    raw_path = artifact_manifest_path(manifest, section, name)
    base_dir = manifest_path.parent if manifest_path is not None else None
    path = qge_moonlab_full_game_plan.resolve_path(raw_path, base_dir=base_dir)
    if path is None or not path.is_file():
        return None
    return load_json(path)


def criterion(
    criterion_id: str,
    label: str,
    passed: bool,
    blocker: str,
    **fields: Any,
) -> dict[str, Any]:
    item = {
        "id": criterion_id,
        "label": label,
        "status": PASS if passed else BLOCKED,
        "blocker": None if passed else blocker,
    }
    item.update(fields)
    return item


def failed_criteria(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in criteria
        if dict_or_empty(item).get("status") != PASS
    ]


def breadth_aggregate(breadth_evidence: dict[str, Any]) -> dict[str, Any]:
    return dict_or_empty(breadth_evidence.get("aggregate"))


def coverage_from_breadth_or_coverage(
    coverage: dict[str, Any],
    breadth_evidence: dict[str, Any],
) -> dict[str, Any]:
    if coverage:
        return coverage
    aggregate = breadth_aggregate(breadth_evidence)
    return dict_or_empty(
        aggregate.get("full_game_coverage") or
        breadth_evidence.get("full_game_coverage")
    )


def matrix_runs_ready(runs: list[Any]) -> bool:
    if len(runs) < len(SHAREWARE_MAPS):
        return False
    for run in runs:
        run_data = dict_or_empty(run)
        if not bool_true(run_data.get("ready_for_complete_claim")):
            return False
        if not bool_true(run_data.get("route_contract_authority_ready")):
            return False
    return True


def backend_result_completed(job: dict[str, Any], backend_kind: str) -> bool:
    for result in list_or_empty(job.get("backend_results")):
        result_data = dict_or_empty(result)
        if result_data.get("backend_kind") != backend_kind:
            continue
        if result_data.get("status") == "completed":
            return True
    return False


def count_jobs_with_backend(
    job_results: dict[str, Any],
    backend_kind: str,
) -> int:
    return sum(
        1 for job in list_or_empty(job_results.get("jobs"))
        if backend_result_completed(dict_or_empty(job), backend_kind)
    )


def missing_or_blocked_jobs(job_results: dict[str, Any]) -> list[str]:
    blocked = []
    for job in list_or_empty(job_results.get("jobs")):
        job_data = dict_or_empty(job)
        job_id = str(job_data.get("job_id") or "<unknown>")
        if job_data.get("result_status") not in ALLOWED_JOB_RESULT_STATUSES:
            blocked.append(job_id)
            continue
        if list_or_empty(job_data.get("missing_required_artifacts")):
            blocked.append(job_id)
    return blocked


def no_overclaim_flags(
    deployment_gate: dict[str, Any],
    requirements: dict[str, Any],
    job_results: dict[str, Any],
) -> tuple[bool, list[str]]:
    flags = []
    for flag in (
        "whole_game_moonlab_deployment_claim_allowed",
        "whole_game_hardware_execution_claim_allowed",
        "hardware_quantum_advantage_claim_allowed",
        "dense_70000_qubit_state_claim_allowed",
    ):
        if deployment_gate.get(flag) is True:
            flags.append(f"full_gate.{flag}")
    claim_posture = dict_or_empty(requirements.get("claim_posture"))
    for flag in (
        "whole_game_moonlab_deployment_claimed",
        "whole_game_hardware_execution_claimed",
        "hardware_quantum_advantage_claimed",
        "dense_70000_qubit_state_claimed",
    ):
        if claim_posture.get(flag) is True:
            flags.append(f"asset_requirements.{flag}")
    for job in list_or_empty(job_results.get("jobs")):
        job_data = dict_or_empty(job)
        posture = dict_or_empty(job_data.get("claim_posture"))
        for flag in (
            "whole_game_hardware_execution_claimed",
            "hardware_quantum_advantage_claimed",
            "hardware_result_claimed",
        ):
            if posture.get(flag) is True:
                flags.append(f"{job_data.get('job_id')}.{flag}")
    return not flags, flags


def gate_summary(
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    requirements: dict[str, Any],
    breadth_evidence: dict[str, Any],
    vanilla_matrix: dict[str, Any],
    performance_summary: dict[str, Any],
    job_results: dict[str, Any],
    submission_bundle: dict[str, Any],
    hardware_submission_scope: dict[str, Any],
    native_backend_boundary: dict[str, Any],
    deployment_gate: dict[str, Any],
) -> dict[str, Any]:
    aggregate = breadth_aggregate(breadth_evidence)
    conformance = dict_or_empty(vanilla_matrix.get("conformance_summary"))
    performance_aggregate = dict_or_empty(performance_summary.get("aggregate"))
    return {
        "map_set": coverage.get("map_set"),
        "target_map_count": coverage.get("target_map_count"),
        "covered_map_count": coverage.get("covered_map_count"),
        "coverage_missing_map_count": coverage.get("missing_map_count"),
        "shareware_episode_one_scope": coverage.get(
            "shareware_episode_one_scope"),
        "registered_full_game_scope": coverage.get("registered_full_game_scope"),
        "asset_inventory_status": inventory.get("status"),
        "asset_inventory_available_map_count": inventory.get(
            "available_map_count"),
        "asset_inventory_missing_map_count": inventory.get(
            "missing_map_count"),
        "asset_inventory_invalid_bsp_count": inventory.get(
            "invalid_bsp_count"),
        "asset_requirements_status": requirements.get("status"),
        "asset_requirements_present_map_count": requirements.get(
            "present_map_count"),
        "asset_requirements_missing_map_count": requirements.get(
            "missing_map_count"),
        "asset_requirements_satisfied": dict_or_empty(
            requirements.get("claim_posture")).get(
                "asset_requirements_satisfied"),
        "breadth_ready_for_complete_claim": aggregate.get(
            "breadth_ready_for_complete_claim"),
        "breadth_matrix_run_count": aggregate.get("matrix_run_count"),
        "breadth_ready_matrix_run_count": aggregate.get(
            "ready_matrix_run_count"),
        "route_contract_authority_ready_run_count": aggregate.get(
            "route_contract_authority_ready_run_count"),
        "route_contract_authority_blocker_count": aggregate.get(
            "route_contract_authority_blocker_count"),
        "runtime_backend_probe_missing_targets": aggregate.get(
            "runtime_backend_probe_missing_targets"),
        "runtime_backend_probe_native_targets": aggregate.get(
            "runtime_backend_probe_native_targets"),
        "runtime_backend_probe_paths": aggregate.get(
            "runtime_backend_probe_paths"),
        "total_native_bridge_count": aggregate.get("total_native_bridge_count"),
        "total_fallback_count": aggregate.get("total_fallback_count"),
        "total_surrogate_count": aggregate.get("total_surrogate_count"),
        "total_cpu_idwt_count": aggregate.get("total_cpu_idwt_count"),
        "vanilla_ready_for_complete_claim": conformance.get(
            "ready_for_complete_claim"),
        "qge_asset_ownership_complete": conformance.get(
            "qge_asset_ownership_complete"),
        "moonlab_authority_ready": conformance.get("moonlab_authority_ready"),
        "qge_performance_status": conformance.get("qge_performance_status"),
        "performance_status": performance_summary.get("status"),
        "performance_metric_evidence_present": performance_aggregate.get(
            "metric_evidence_present"),
        "native_backend_boundary_status": native_backend_boundary.get("status"),
        "native_backend_boundary_passed_target_count": (
            native_backend_boundary.get("passed_target_count")),
        "native_backend_boundary_required_target_count": (
            native_backend_boundary.get("required_target_count")),
        "moonlab_job_results_status": job_results.get("overall_status"),
        "moonlab_selected_job_count": job_results.get("selected_job_count"),
        "moonlab_completed_simulator_job_count": job_results.get(
            "completed_simulator_job_count"),
        "moonlab_completed_native_replay_job_count": job_results.get(
            "completed_native_replay_job_count"),
        "moonlab_hardware_candidate_job_count": job_results.get(
            "hardware_candidate_job_count"),
        "moonlab_hardware_submitted_job_count": job_results.get(
            "hardware_submitted_job_count"),
        "moonlab_blocked_job_count": job_results.get("blocked_job_count"),
        "moonlab_submission_bundle_status": submission_bundle.get("status"),
        "moonlab_submission_ready_for_control_plane_submission_count": (
            submission_bundle.get(
                "ready_for_control_plane_submission_count")),
        "moonlab_hardware_submission_scope_status": (
            hardware_submission_scope.get("status")),
        "moonlab_hardware_submission_scope_ready": (
            hardware_submission_scope.get("hardware_submission_scope_ready")),
        "moonlab_hardware_submission_scope_passing_check_count": (
            hardware_submission_scope.get("passing_check_count")),
        "full_game_deployment_gate_status": deployment_gate.get("status"),
        "full_game_deployment_gate_blocker_count": deployment_gate.get(
            "blocker_count"),
    }


def build_criteria(
    *,
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    requirements: dict[str, Any],
    breadth_evidence: dict[str, Any],
    vanilla_matrix: dict[str, Any],
    performance_summary: dict[str, Any],
    job_results: dict[str, Any],
    submission_bundle: dict[str, Any],
    hardware_submission_scope: dict[str, Any],
    native_backend_boundary: dict[str, Any],
    deployment_gate: dict[str, Any],
) -> list[dict[str, Any]]:
    aggregate = breadth_aggregate(breadth_evidence)
    conformance = dict_or_empty(vanilla_matrix.get("conformance_summary"))
    matrix_runs = list_or_empty(breadth_evidence.get("matrix_runs"))
    expected_count = len(SHAREWARE_MAPS)
    coverage_map_set = coverage.get("map_set")
    inventory_map_set = inventory.get("map_set")
    requirements_map_set = requirements.get("map_set")
    shareware_scope = (
        coverage_map_set == SHAREWARE_MAP_SET and
        inventory_map_set == SHAREWARE_MAP_SET and
        requirements_map_set == SHAREWARE_MAP_SET and
        bool_true(coverage.get("shareware_episode_one_scope")) and
        not bool_true(coverage.get("registered_full_game_scope")) and
        not bool_true(inventory.get("registered_full_game_scope"))
    )
    inventory_ready = (
        inventory.get("status") == "complete" and
        int_value(inventory.get("target_map_count")) == expected_count and
        int_value(inventory.get("available_map_count")) == expected_count and
        int_value(inventory.get("missing_map_count")) == 0 and
        int_value(inventory.get("invalid_bsp_count")) == 0 and
        bool_true(inventory.get("shareware_episode_one_asset_ready"))
    )
    requirements_ready = (
        requirements.get("status") == "complete" and
        int_value(requirements.get("target_map_count")) == expected_count and
        int_value(requirements.get("present_map_count")) == expected_count and
        int_value(requirements.get("missing_map_count")) == 0 and
        bool_true(dict_or_empty(requirements.get("claim_posture")).get(
            "shareware_episode_one_requirements_satisfied"))
    )
    coverage_ready = (
        coverage.get("status") == "complete" and
        int_value(coverage.get("target_map_count")) == expected_count and
        int_value(coverage.get("covered_map_count")) == expected_count and
        int_value(coverage.get("missing_map_count")) == 0 and
        aggregate.get("full_game_map_set") == SHAREWARE_MAP_SET and
        aggregate.get("full_game_map_coverage_status") == "complete" and
        int_value(aggregate.get("matrix_run_count")) >= expected_count and
        int_value(aggregate.get("ready_matrix_run_count")) >= expected_count and
        bool_true(aggregate.get("breadth_ready_for_complete_claim"))
    )
    native_targets = set(string_list(aggregate.get(
        "runtime_backend_probe_native_targets")))
    required_targets = set(string_list(aggregate.get(
        "required_runtime_backend_probe_targets"))) or REQUIRED_NATIVE_TARGETS
    native_backend_ready = (
        not list_or_empty(aggregate.get("runtime_backend_probe_missing_targets"))
        and required_targets.issubset(native_targets)
        and int_value(aggregate.get("total_native_bridge_count")) > 0
        and int_value(aggregate.get("total_fallback_count")) == 0
        and int_value(aggregate.get("total_surrogate_count")) == 0
        and int_value(aggregate.get("total_cpu_idwt_count")) == 0
    )
    route_authority_ready = (
        int_value(aggregate.get("route_contract_authority_blocker_count")) == 0
        and int_value(aggregate.get(
            "route_contract_authority_ready_run_count")) >= expected_count
        and matrix_runs_ready(matrix_runs)
    )
    performance_aggregate = dict_or_empty(performance_summary.get("aggregate"))
    vanilla_ready = (
        bool_true(conformance.get("ready_for_complete_claim")) and
        bool_true(conformance.get("qge_asset_ownership_complete")) and
        bool_true(conformance.get("moonlab_authority_ready")) and
        conformance.get("qge_performance_status") == "pass" and
        native_backend_boundary.get("status") == "pass" and
        performance_summary.get("status") == "pass" and
        bool_true(performance_aggregate.get("metric_evidence_present"))
    )
    simulator_backend_jobs = count_jobs_with_backend(
        job_results, "moonlab_simulator")
    native_replay_jobs = count_jobs_with_backend(
        job_results, "native_backend_replay")
    blocked_jobs = missing_or_blocked_jobs(job_results)
    jobs_replayable = (
        job_results.get("overall_status") ==
        "simulator_complete_hardware_not_submitted" and
        int_value(job_results.get("selected_job_count")) == 4 and
        int_value(job_results.get("completed_simulator_job_count")) == 4 and
        int_value(job_results.get("completed_native_replay_job_count")) == 2 and
        simulator_backend_jobs >= 4 and
        native_replay_jobs >= 1 and
        int_value(job_results.get("blocked_job_count")) == 0 and
        not blocked_jobs
    )
    hardware_handoff_ready = (
        submission_bundle.get("status") == "ready_for_control_plane_submission"
        and hardware_submission_scope.get("status") ==
        "ready_for_control_plane_submission"
        and bool_true(hardware_submission_scope.get(
            "hardware_submission_scope_ready"))
        and int_value(submission_bundle.get(
            "ready_for_control_plane_submission_count")) >= 1
        and int_value(hardware_submission_scope.get(
            "passing_check_count")) >= 1
        and int_value(job_results.get("hardware_submitted_job_count")) == 0
    )
    overclaim_ready, overclaim_flags = no_overclaim_flags(
        deployment_gate, requirements, job_results)
    return [
        criterion(
            "shareware_scope_explicit",
            "Evidence is scoped to Quake shareware Episode 1",
            shareware_scope,
            "coverage, inventory, or requirements are not shareware scoped",
            coverage_map_set=coverage_map_set,
            inventory_map_set=inventory_map_set,
            requirements_map_set=requirements_map_set,
            required_map_set=SHAREWARE_MAP_SET,
            registered_full_game_scope=coverage.get("registered_full_game_scope"),
        ),
        criterion(
            "shareware_assets_ready",
            "Shareware BSP assets and requirements are complete",
            inventory_ready and requirements_ready,
            "shareware asset inventory or requirements are incomplete",
            inventory_ready=inventory_ready,
            requirements_ready=requirements_ready,
            asset_missing_map_count=inventory.get("missing_map_count"),
            requirements_missing_map_count=requirements.get(
                "missing_map_count"),
        ),
        criterion(
            "shareware_map_coverage_complete",
            "All shareware Episode 1 maps are covered by breadth evidence",
            coverage_ready,
            "shareware breadth coverage is incomplete",
            target_map_count=coverage.get("target_map_count"),
            covered_map_count=coverage.get("covered_map_count"),
            matrix_run_count=aggregate.get("matrix_run_count"),
            ready_matrix_run_count=aggregate.get("ready_matrix_run_count"),
        ),
        criterion(
            "shareware_route_authority_complete",
            "Route authority is ready for every shareware map run",
            route_authority_ready,
            "one or more shareware map runs lack route authority",
            route_contract_authority_ready_run_count=aggregate.get(
                "route_contract_authority_ready_run_count"),
            route_contract_authority_blocker_count=aggregate.get(
                "route_contract_authority_blocker_count"),
        ),
        criterion(
            "shareware_native_backend_evidence",
            "Native backend probes resolve without fallback or surrogates",
            native_backend_ready,
            "runtime backend probe evidence is missing or has fallback paths",
            required_runtime_backend_probe_targets=sorted(required_targets),
            runtime_backend_probe_native_targets=sorted(native_targets),
            runtime_backend_probe_missing_targets=aggregate.get(
                "runtime_backend_probe_missing_targets"),
            total_native_bridge_count=aggregate.get("total_native_bridge_count"),
            total_fallback_count=aggregate.get("total_fallback_count"),
            total_surrogate_count=aggregate.get("total_surrogate_count"),
            total_cpu_idwt_count=aggregate.get("total_cpu_idwt_count"),
        ),
        criterion(
            "shareware_vanilla_conformance_ready",
            "Vanilla/QGE conformance and runtime performance are ready",
            vanilla_ready,
            "vanilla/QGE conformance, performance, or native boundary failed",
            vanilla_ready_for_complete_claim=conformance.get(
                "ready_for_complete_claim"),
            qge_asset_ownership_complete=conformance.get(
                "qge_asset_ownership_complete"),
            moonlab_authority_ready=conformance.get("moonlab_authority_ready"),
            qge_performance_status=conformance.get("qge_performance_status"),
            native_backend_boundary_status=native_backend_boundary.get(
                "status"),
            performance_status=performance_summary.get("status"),
        ),
        criterion(
            "shareware_moonlab_jobs_replayable",
            "Moonlab simulator and native replay jobs are complete",
            jobs_replayable,
            "Moonlab simulator/native replay job results are incomplete",
            selected_job_count=job_results.get("selected_job_count"),
            completed_simulator_job_count=job_results.get(
                "completed_simulator_job_count"),
            completed_native_replay_job_count=job_results.get(
                "completed_native_replay_job_count"),
            simulator_backend_job_count=simulator_backend_jobs,
            native_replay_job_count=native_replay_jobs,
            blocked_job_count=job_results.get("blocked_job_count"),
            blocked_jobs=blocked_jobs,
        ),
        criterion(
            "bounded_hardware_handoff_ready",
            "Bounded Moonlab control-plane handoff is ready but unsubmitted",
            hardware_handoff_ready,
            "Moonlab control-plane handoff bundle or scope is not ready",
            submission_bundle_status=submission_bundle.get("status"),
            hardware_submission_scope_status=hardware_submission_scope.get(
                "status"),
            ready_for_control_plane_submission_count=submission_bundle.get(
                "ready_for_control_plane_submission_count"),
            hardware_submitted_job_count=job_results.get(
                "hardware_submitted_job_count"),
        ),
        criterion(
            "no_shareware_overclaim",
            "Shareware deployment does not assert full-game or hardware claims",
            overclaim_ready,
            "forbidden full-game, hardware, advantage, or dense-state flag set",
            overclaim_flags=overclaim_flags,
            full_game_deployment_gate_status=deployment_gate.get("status"),
            full_game_deployment_gate_blocker_count=deployment_gate.get(
                "blocker_count"),
        ),
    ]


def next_actions_for_blockers(blockers: list[dict[str, Any]]) -> list[str]:
    if not blockers:
        return [
            "Publish the shareware-scoped pack with the gate JSON, Markdown, and ICC sidecar.",
            "Keep the registered full-game deployment gate blocked until pak1/registered scope is complete.",
        ]
    actions = []
    for blocker in blockers:
        blocker_id = blocker.get("id")
        if blocker_id == "shareware_scope_explicit":
            actions.append(
                "Regenerate the pack with --map-set quake_shareware_episode1.")
        elif blocker_id == "shareware_assets_ready":
            actions.append(
                "Repair the shareware pak0/id1 asset inventory and rerun asset requirements.")
        elif blocker_id == "shareware_map_coverage_complete":
            actions.append(
                "Rebuild breadth evidence for start and e1m1 through e1m8.")
        elif blocker_id == "shareware_route_authority_complete":
            actions.append(
                "Rerun the failing shareware matrix captures until route authority is ready.")
        elif blocker_id == "shareware_native_backend_evidence":
            actions.append(
                "Restore native sparse-DWT backend probe evidence with no fallback or surrogate path.")
        elif blocker_id == "shareware_vanilla_conformance_ready":
            actions.append(
                "Refresh vanilla/QGE conformance, performance, and native boundary evidence.")
        elif blocker_id == "shareware_moonlab_jobs_replayable":
            actions.append(
                "Rerun qge_moonlab_job_runner for simulator and native replay jobs.")
        elif blocker_id == "bounded_hardware_handoff_ready":
            actions.append(
                "Rebuild the Moonlab submission bundle and hardware submission scope.")
        elif blocker_id == "no_shareware_overclaim":
            actions.append(
                "Clear forbidden full-game, hardware, advantage, or dense-state claim flags.")
    return actions


def build_gate(
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    requirements: dict[str, Any],
    breadth_evidence: dict[str, Any],
    vanilla_matrix: dict[str, Any],
    performance_summary: dict[str, Any],
    job_results: dict[str, Any],
    submission_bundle: dict[str, Any],
    hardware_submission_scope: dict[str, Any],
    native_backend_boundary: dict[str, Any],
    deployment_gate: dict[str, Any],
    *,
    source_path: Path | str | None = None,
) -> dict[str, Any]:
    coverage_data = coverage_from_breadth_or_coverage(coverage, breadth_evidence)
    criteria = build_criteria(
        coverage=coverage_data,
        inventory=inventory,
        requirements=requirements,
        breadth_evidence=breadth_evidence,
        vanilla_matrix=vanilla_matrix,
        performance_summary=performance_summary,
        job_results=job_results,
        submission_bundle=submission_bundle,
        hardware_submission_scope=hardware_submission_scope,
        native_backend_boundary=native_backend_boundary,
        deployment_gate=deployment_gate,
    )
    blockers = failed_criteria(criteria)
    claim_allowed = not blockers
    return {
        "schema": "qge.moonlab_shareware_deployment_gate.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path) if source_path is not None else None,
        "status": READY_STATUS if claim_allowed else "blocked",
        "map_set": coverage_data.get("map_set"),
        "shareware_moonlab_deployment_claim_allowed": claim_allowed,
        "whole_game_moonlab_deployment_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "hardware_quantum_advantage_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "failed_criterion_count": len(blockers),
        "blocker_count": len(blockers),
        "criteria": criteria,
        "blockers": blockers,
        "summary": gate_summary(
            coverage_data,
            inventory,
            requirements,
            breadth_evidence,
            vanilla_matrix,
            performance_summary,
            job_results,
            submission_bundle,
            hardware_submission_scope,
            native_backend_boundary,
            deployment_gate,
        ),
        "next_actions": next_actions_for_blockers(blockers),
        "limits": [
            "This gate authorizes only the shareware Episode 1 simulator/native Moonlab deployment claim.",
            "It is not a registered full-game Moonlab deployment claim.",
            "It is not a hardware execution or hardware quantum advantage claim.",
            "Dense 70,000-qubit state-vector claims remain forbidden.",
        ],
    }


def build_gate_from_manifest(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
    asset_root: Path = qge_asset_inventory.DEFAULT_ASSET_ROOT,
) -> dict[str, Any]:
    coverage = (
        qge_moonlab_full_game_plan.load_resource_json(
            manifest,
            "full_game_map_coverage",
            manifest_path=manifest_path,
        ) or {}
    )
    breadth = load_artifact_json(
        manifest, "breadth", "evidence", manifest_path=manifest_path) or {}
    if not coverage:
        coverage = coverage_from_breadth_or_coverage({}, breadth)
    inventory = (
        qge_moonlab_full_game_plan.load_resource_json(
            manifest,
            "asset_inventory",
            manifest_path=manifest_path,
        )
        or qge_asset_inventory.build_inventory(asset_root, map_set=SHAREWARE_MAP_SET)
    )
    requirements = (
        qge_moonlab_full_game_plan.load_resource_json(
            manifest,
            "asset_requirements",
            manifest_path=manifest_path,
        )
        or qge_asset_requirements.build_requirements(
            inventory, map_set=SHAREWARE_MAP_SET)
    )
    return build_gate(
        coverage,
        inventory,
        requirements,
        breadth,
        load_artifact_json(
            manifest, "vanilla", "matrix", manifest_path=manifest_path) or {},
        load_artifact_json(
            manifest,
            "capture",
            "performance_summary",
            manifest_path=manifest_path,
        ) or {},
        qge_moonlab_full_game_plan.load_resource_json(
            manifest,
            "moonlab_job_results",
            manifest_path=manifest_path,
        ) or {},
        qge_moonlab_full_game_plan.load_resource_json(
            manifest,
            "moonlab_submission_bundle",
            manifest_path=manifest_path,
        ) or {},
        qge_moonlab_full_game_plan.load_resource_json(
            manifest,
            "moonlab_hardware_submission_scope",
            manifest_path=manifest_path,
        ) or {},
        qge_moonlab_full_game_plan.load_resource_json(
            manifest,
            "native_backend_boundary",
            manifest_path=manifest_path,
        ) or {},
        qge_moonlab_full_game_plan.load_resource_json(
            manifest,
            "moonlab_deployment_gate",
            manifest_path=manifest_path,
        ) or {},
        source_path=manifest_path,
    )


def build_icc_evidence(
    gate: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    summary = dict_or_empty(gate.get("summary"))
    claim_allowed = gate.get("shareware_moonlab_deployment_claim_allowed")
    completion_reason = "qge_moonlab_shareware_deployment_gate_blocked"
    if claim_allowed is True:
        completion_reason = "qge_moonlab_shareware_deployment_gate_ready"
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_moonlab_shareware_deployment_gate",
        "completion_reason": completion_reason,
        "moonlab_shareware_deployment_gate_file": (
            str(out_path) if out_path else None),
        "status": "success",
        "gate_status": gate.get("status"),
        "failed_criterion_count": gate.get("failed_criterion_count"),
        "blocker_count": gate.get("blocker_count"),
        "map_set": summary.get("map_set"),
        "runtime_backend_scope_map_set": summary.get("map_set"),
        "target_map_count": summary.get("target_map_count"),
        "covered_map_count": summary.get("covered_map_count"),
        "coverage_missing_map_count": summary.get(
            "coverage_missing_map_count"),
        "shareware_moonlab_deployment_claim_allowed": claim_allowed,
        "whole_game_moonlab_deployment_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "hardware_quantum_advantage_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "asset_inventory_status": summary.get("asset_inventory_status"),
        "asset_inventory_available_map_count": summary.get(
            "asset_inventory_available_map_count"),
        "asset_inventory_missing_map_count": summary.get(
            "asset_inventory_missing_map_count"),
        "asset_requirements_status": summary.get("asset_requirements_status"),
        "asset_requirements_present_map_count": summary.get(
            "asset_requirements_present_map_count"),
        "breadth_ready_for_complete_claim": summary.get(
            "breadth_ready_for_complete_claim"),
        "breadth_matrix_run_count": summary.get("breadth_matrix_run_count"),
        "breadth_ready_matrix_run_count": summary.get(
            "breadth_ready_matrix_run_count"),
        "route_contract_authority_ready_run_count": summary.get(
            "route_contract_authority_ready_run_count"),
        "route_contract_authority_blocker_count": summary.get(
            "route_contract_authority_blocker_count"),
        "runtime_backend_probe_missing_targets": summary.get(
            "runtime_backend_probe_missing_targets"),
        "runtime_backend_probe_native_targets": summary.get(
            "runtime_backend_probe_native_targets"),
        "total_native_bridge_count": summary.get("total_native_bridge_count"),
        "total_fallback_count": summary.get("total_fallback_count"),
        "total_surrogate_count": summary.get("total_surrogate_count"),
        "total_cpu_idwt_count": summary.get("total_cpu_idwt_count"),
        "vanilla_ready_for_complete_claim": summary.get(
            "vanilla_ready_for_complete_claim"),
        "qge_asset_ownership_complete": summary.get(
            "qge_asset_ownership_complete"),
        "moonlab_authority_ready": summary.get("moonlab_authority_ready"),
        "qge_performance_status": summary.get("qge_performance_status"),
        "performance_status": summary.get("performance_status"),
        "native_backend_boundary_status": summary.get(
            "native_backend_boundary_status"),
        "moonlab_job_results_status": summary.get(
            "moonlab_job_results_status"),
        "moonlab_selected_job_count": summary.get("moonlab_selected_job_count"),
        "moonlab_completed_simulator_job_count": summary.get(
            "moonlab_completed_simulator_job_count"),
        "moonlab_completed_native_replay_job_count": summary.get(
            "moonlab_completed_native_replay_job_count"),
        "moonlab_hardware_submitted_job_count": summary.get(
            "moonlab_hardware_submitted_job_count"),
        "moonlab_submission_bundle_status": summary.get(
            "moonlab_submission_bundle_status"),
        "moonlab_hardware_submission_scope_status": summary.get(
            "moonlab_hardware_submission_scope_status"),
        "full_game_deployment_gate_status": summary.get(
            "full_game_deployment_gate_status"),
        "full_game_deployment_gate_blocker_count": summary.get(
            "full_game_deployment_gate_blocker_count"),
    }


def markdown_report(gate: dict[str, Any]) -> str:
    summary = dict_or_empty(gate.get("summary"))
    lines = [
        "# QGE Moonlab Shareware Deployment Gate",
        "",
        f"Status: {gate.get('status')}",
        "",
        "| Claim | Allowed |",
        "| --- | ---: |",
        (
            "| shareware Episode 1 Moonlab simulator/native deployment | "
            f"{str(gate.get('shareware_moonlab_deployment_claim_allowed')).lower()} |"
        ),
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
        "",
        "| Map Set | Covered | Missing | Asset Missing | Native Bridges |",
        "| --- | ---: | ---: | ---: | ---: |",
        (
            f"| {summary.get('map_set')} | "
            f"{summary.get('covered_map_count')} / {summary.get('target_map_count')} | "
            f"{summary.get('coverage_missing_map_count')} | "
            f"{summary.get('asset_inventory_missing_map_count')} | "
            f"{summary.get('total_native_bridge_count')} |"
        ),
        "",
        (
            "Route authority: "
            f"{summary.get('route_contract_authority_ready_run_count')} ready, "
            f"{summary.get('route_contract_authority_blocker_count')} blockers"
        ),
        (
            "Moonlab jobs: "
            f"{summary.get('moonlab_completed_simulator_job_count')} simulator, "
            f"{summary.get('moonlab_completed_native_replay_job_count')} native replay, "
            f"{summary.get('moonlab_hardware_submitted_job_count')} hardware submitted"
        ),
        (
            "Hardware handoff: "
            f"{summary.get('moonlab_submission_bundle_status')} / "
            f"{summary.get('moonlab_hardware_submission_scope_status')}"
        ),
        (
            "Full-game gate remains: "
            f"{summary.get('full_game_deployment_gate_status')} "
            f"({summary.get('full_game_deployment_gate_blocker_count')} blockers)"
        ),
        "",
        "| Criterion | Status | Blocker |",
        "| --- | --- | --- |",
    ]
    for item in list_or_empty(gate.get("criteria")):
        item_data = dict_or_empty(item)
        lines.append(
            f"| {item_data.get('id')} | {item_data.get('status')} | "
            f"{item_data.get('blocker') or ''} |"
        )
    lines.extend(["", "## Next Actions", ""])
    for action in list_or_empty(gate.get("next_actions")):
        lines.append(f"- {action}")
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
        print(f"qge_moonlab_shareware_deployment_gate: {exc}", file=sys.stderr)
        return 1

    print(f"QGE_MOONLAB_SHAREWARE_DEPLOYMENT_GATE {args.out}")
    if args.markdown:
        print(f"QGE_MOONLAB_SHAREWARE_DEPLOYMENT_GATE_MARKDOWN {args.markdown}")
    if args.icc_json:
        print(
            "QGE_MOONLAB_SHAREWARE_DEPLOYMENT_GATE_ICC_EVIDENCE "
            f"{args.icc_json}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
