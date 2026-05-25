#!/usr/bin/env python3
"""Audit publication manifest summary mirrors against their source artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_publication_pack  # noqa: E402


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def resolve_path(value: Any, *, base_dir: Path | None = None) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or path.exists():
        return path
    if base_dir is not None:
        candidate = base_dir / path
        if candidate.exists():
            return candidate
    return path


def source_input_path(
    manifest: dict[str, Any],
    name: str,
    *,
    manifest_path: Path | None = None,
) -> Path | None:
    source_inputs = dict_or_empty(manifest.get("source_inputs"))
    base_dir = manifest_path.parent if manifest_path is not None else None
    return resolve_path(source_inputs.get(name), base_dir=base_dir)


def artifact_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    packed: bool = False,
    manifest_path: Path | None = None,
) -> Path | None:
    artifacts = dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(
        section))
    record = dict_or_empty(artifacts.get(name))
    path_value = None
    if packed:
        path_value = dict_or_empty(record.get("packed")).get("path")
    if path_value is None:
        path_value = record.get("path")
    if path_value is None:
        path_value = dict_or_empty(record.get("packed")).get("path")
    base_dir = manifest_path.parent if manifest_path is not None else None
    return resolve_path(path_value, base_dir=base_dir)


def load_artifact_json(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    packed: bool = False,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    path = artifact_path(
        manifest,
        section,
        name,
        packed=packed,
        manifest_path=manifest_path,
    )
    if path is None:
        raise ValueError(f"missing artifact path for {section}.{name}")
    return load_json(path)


def path_join(prefix: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{prefix}[{key}]" if prefix else f"[{key}]"
    return f"{prefix}.{key}" if prefix else key


def compare_values(
    expected: Any,
    recorded: Any,
    *,
    prefix: str = "",
) -> list[dict[str, Any]]:
    if isinstance(expected, dict) and isinstance(recorded, dict):
        mismatches: list[dict[str, Any]] = []
        for key in sorted(set(expected) | set(recorded)):
            child_prefix = path_join(prefix, str(key))
            if key not in expected:
                mismatches.append({
                    "path": child_prefix,
                    "reason": "unexpected_field",
                })
            elif key not in recorded:
                mismatches.append({
                    "path": child_prefix,
                    "reason": "missing_field",
                })
            else:
                mismatches.extend(compare_values(
                    expected[key],
                    recorded[key],
                    prefix=child_prefix,
                ))
        return mismatches
    if isinstance(expected, list) and isinstance(recorded, list):
        mismatches = []
        if len(expected) != len(recorded):
            mismatches.append({
                "path": prefix,
                "reason": "list_length",
                "expected": len(expected),
                "recorded": len(recorded),
            })
        for index, expected_item in enumerate(expected[:len(recorded)]):
            mismatches.extend(compare_values(
                expected_item,
                recorded[index],
                prefix=path_join(prefix, index),
            ))
        return mismatches
    if expected != recorded:
        mismatch: dict[str, Any] = {
            "path": prefix,
            "reason": "value_mismatch",
        }
        if not isinstance(expected, (dict, list)):
            mismatch["expected"] = expected
        if not isinstance(recorded, (dict, list)):
            mismatch["recorded"] = recorded
        return [mismatch]
    return []


def expected_runtime_summary(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    vanilla_path = source_input_path(
        manifest, "vanilla_matrix", manifest_path=manifest_path)
    vanilla = load_json(vanilla_path) if vanilla_path is not None else {}
    conformance = dict_or_empty(vanilla.get("conformance_summary"))
    agent_stream_dir = source_input_path(
        manifest, "agent_stream_dir", manifest_path=manifest_path)
    agent_manifest = (
        agent_stream_dir / "manifest.json"
        if agent_stream_dir is not None else None
    )
    perf_summary_path = source_input_path(
        manifest, "publication_performance_summary",
        manifest_path=manifest_path,
    )
    perf_source = dict_or_empty(manifest.get("source_inputs")).get(
        "publication_performance_source")
    breadth_path = source_input_path(
        manifest, "breadth_evidence", manifest_path=manifest_path)
    agent_stream_summary = qge_publication_pack.agent_manifest_summary(
        agent_manifest)
    capture_perf_summary = qge_publication_pack.performance_summary(
        perf_summary_path)
    breadth_summary = qge_publication_pack.breadth_evidence_summary(
        breadth_path)
    full_game_map_coverage = load_artifact_json(
        manifest,
        "resource",
        "full_game_map_coverage",
        manifest_path=manifest_path,
    )
    asset_inventory = load_artifact_json(
        manifest,
        "resource",
        "asset_inventory",
        manifest_path=manifest_path,
    )
    registered_asset_intake = load_artifact_json(
        manifest,
        "resource",
        "registered_asset_intake",
        manifest_path=manifest_path,
    )
    vanilla_performance_ok = (
        conformance.get("performance_sidecars_success") is not False
    )
    agent_stream_manifest_ok = not (
        qge_publication_pack.explicit_agent_run_failure(agent_stream_summary))
    performance_ok = not qge_publication_pack.explicit_performance_failure(
        capture_perf_summary)
    breadth_evidence_ok = not (
        qge_publication_pack.explicit_breadth_evidence_failure(
            breadth_summary))
    publication_ready = (
        bool(conformance.get("ready_for_complete_claim")) and
        conformance.get("agent_stream_runs_success") is not False and
        agent_stream_manifest_ok and
        vanilla_performance_ok and
        performance_ok and
        breadth_evidence_ok
    )
    return {
        "vanilla_ready_for_complete_claim": conformance.get(
            "ready_for_complete_claim"),
        "fallback_count": conformance.get("fallback_count"),
        "surrogate_count": conformance.get("qge_surface_surrogates"),
        "classic3d_count": conformance.get("classic3d_count"),
        "classic2d_count": conformance.get("classic2d_count"),
        "viewmodel_encoded": conformance.get("viewmodel_encoded"),
        "qge_classic_output_hidden": conformance.get(
            "qge_classic_output_hidden"),
        "qge_asset_ownership": conformance.get("qge_asset_ownership"),
        "qge_asset_ownership_fields_present": conformance.get(
            "qge_asset_ownership_fields_present"),
        "qge_asset_ownership_missing_fields": conformance.get(
            "qge_asset_ownership_missing_fields"),
        "qge_asset_ownership_incomplete_fields": conformance.get(
            "qge_asset_ownership_incomplete_fields"),
        "qge_asset_ownership_complete": conformance.get(
            "qge_asset_ownership_complete"),
        "agent_stream_runs_success": conformance.get(
            "agent_stream_runs_success"),
        "classic_agent_run_status": conformance.get(
            "classic_agent_run_status"),
        "qge_agent_run_status": conformance.get("qge_agent_run_status"),
        "classic_agent_startup_issue": conformance.get(
            "classic_agent_startup_issue"),
        "qge_agent_startup_issue": conformance.get(
            "qge_agent_startup_issue"),
        "vanilla_performance_sidecars_success": conformance.get(
            "performance_sidecars_success"),
        "classic_performance_status": conformance.get(
            "classic_performance_status"),
        "qge_performance_status": conformance.get("qge_performance_status"),
        "classic_performance_engine_average_quantum_ms_max": (
            conformance.get(
                "classic_performance_engine_average_quantum_ms_max")),
        "qge_performance_engine_average_quantum_ms_max": conformance.get(
            "qge_performance_engine_average_quantum_ms_max"),
        "classic_performance_render_time_ms_max": conformance.get(
            "classic_performance_render_time_ms_max"),
        "qge_performance_render_time_ms_max": conformance.get(
            "qge_performance_render_time_ms_max"),
        "classic_performance_threshold_failures": conformance.get(
            "classic_performance_threshold_failures"),
        "qge_performance_threshold_failures": conformance.get(
            "qge_performance_threshold_failures"),
        "vanilla_performance_ok": vanilla_performance_ok,
        "agent_stream_manifest_run": agent_stream_summary,
        "agent_stream_run_status": agent_stream_summary.get("run_status"),
        "agent_stream_run_success": agent_stream_summary.get("run_success"),
        "agent_stream_startup_issue": agent_stream_summary.get(
            "startup_issue"),
        "agent_stream_frames_captured": agent_stream_summary.get(
            "frames_captured"),
        "agent_stream_trace_status": agent_stream_summary.get("trace_status"),
        "agent_stream_trace_bytes": agent_stream_summary.get("trace_bytes"),
        "agent_stream_performance_status": agent_stream_summary.get(
            "performance_status"),
        "performance_summary": capture_perf_summary,
        "performance_source": perf_source,
        "performance_status": capture_perf_summary.get("status"),
        "performance_engine_average_quantum_ms_max": (
            capture_perf_summary.get("engine_average_quantum_ms_max")),
        "performance_render_time_ms_max": capture_perf_summary.get(
            "render_time_ms_max"),
        "performance_threshold_failures": capture_perf_summary.get(
            "threshold_failures"),
        "performance_metric_evidence_present": capture_perf_summary.get(
            "metric_evidence_present"),
        "performance_required_runtime_backend_probe_targets": (
            capture_perf_summary.get(
                "required_runtime_backend_probe_targets")),
        "performance_runtime_backend_probe_proofs": (
            capture_perf_summary.get("runtime_backend_probe_proofs")),
        "performance_runtime_backend_probe_missing_targets": (
            capture_perf_summary.get("runtime_backend_probe_missing_targets")),
        "performance_runtime_backend_probe_native_targets": (
            capture_perf_summary.get("runtime_backend_probe_native_targets")),
        "performance_runtime_backend_probe_resolved": (
            capture_perf_summary.get("runtime_backend_probe_resolved")),
        "performance_runtime_backend_boundary_status": (
            capture_perf_summary.get("runtime_backend_boundary_status")),
        "performance_ok": performance_ok,
        "breadth_evidence": breadth_summary,
        "breadth_ready_for_complete_claim": breadth_summary.get(
            "breadth_ready_for_complete_claim"),
        "breadth_matrix_run_count": breadth_summary.get("matrix_run_count"),
        "breadth_ready_matrix_run_count": breadth_summary.get(
            "ready_matrix_run_count"),
        "breadth_map_count": breadth_summary.get("map_count"),
        "breadth_maps": breadth_summary.get("maps"),
        "full_game_map_coverage": full_game_map_coverage,
        "full_game_map_set": full_game_map_coverage.get("map_set"),
        "full_game_map_coverage_status": full_game_map_coverage.get("status"),
        "full_game_map_target_count": (
            full_game_map_coverage.get("target_map_count")),
        "full_game_map_covered_count": (
            full_game_map_coverage.get("covered_map_count")),
        "full_game_map_missing_count": (
            full_game_map_coverage.get("missing_map_count")),
        "full_game_map_missing_maps": (
            full_game_map_coverage.get("missing_maps")),
        "asset_inventory": asset_inventory,
        "asset_inventory_status": asset_inventory.get("status"),
        "asset_inventory_available_map_count": (
            asset_inventory.get("available_map_count")),
        "asset_inventory_missing_map_count": (
            asset_inventory.get("missing_map_count")),
        "asset_inventory_invalid_bsp_count": (
            asset_inventory.get("invalid_bsp_count")),
        "full_game_asset_ready": asset_inventory.get("full_game_asset_ready"),
        "registered_asset_intake": registered_asset_intake,
        "registered_asset_intake_status": (
            registered_asset_intake.get("status")),
        "registered_asset_intake_candidate_new_map_count": (
            registered_asset_intake.get("candidate_new_map_count")),
        "registered_asset_intake_missing_map_count_after_plan": (
            registered_asset_intake.get("missing_map_count_after_plan")),
        "registered_asset_intake_discovered_candidate_count": (
            registered_asset_intake.get("discovered_candidate_count", 0)),
        "breadth_total_fallback_count": breadth_summary.get(
            "total_fallback_count"),
        "breadth_total_surrogate_count": breadth_summary.get(
            "total_surrogate_count"),
        "breadth_total_cpu_idwt_count": breadth_summary.get(
            "total_cpu_idwt_count"),
        "breadth_total_native_bridge_count": breadth_summary.get(
            "total_native_bridge_count"),
        "breadth_total_backend_gate_event_count": breadth_summary.get(
            "total_backend_gate_event_count"),
        "breadth_total_runtime_backend_probe_event_count": (
            breadth_summary.get("total_runtime_backend_probe_event_count")),
        "breadth_runtime_backend_probe_targets": breadth_summary.get(
            "runtime_backend_probe_targets"),
        "breadth_runtime_backend_probe_paths": breadth_summary.get(
            "runtime_backend_probe_paths"),
        "breadth_required_runtime_backend_probe_targets": (
            breadth_summary.get("required_runtime_backend_probe_targets")),
        "breadth_runtime_backend_probe_proofs": breadth_summary.get(
            "runtime_backend_probe_proofs"),
        "breadth_runtime_backend_probe_missing_targets": (
            breadth_summary.get("runtime_backend_probe_missing_targets")),
        "breadth_runtime_backend_probe_native_targets": (
            breadth_summary.get("runtime_backend_probe_native_targets")),
        "breadth_runtime_backend_probe_resolved_run_count": (
            breadth_summary.get("runtime_backend_probe_resolved_run_count")),
        "breadth_evidence_ok": breadth_evidence_ok,
        "agent_stream_manifest_ok": agent_stream_manifest_ok,
        "publication_ready_for_complete_claim": publication_ready,
    }


def expected_advantage_summary(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    metrics = load_artifact_json(
        manifest, "advantage", "metrics", manifest_path=manifest_path)
    qae_payload = load_artifact_json(
        manifest, "advantage", "qae_moonlab_payload",
        manifest_path=manifest_path)
    qae_kernel = load_artifact_json(
        manifest, "advantage", "qae_moonlab_oracle_kernel",
        manifest_path=manifest_path)
    qae_observation = load_artifact_json(
        manifest, "advantage", "qae_moonlab_observation_zero",
        manifest_path=manifest_path)
    qae_grover = load_artifact_json(
        manifest, "advantage", "qae_moonlab_grover_schedule_plan",
        manifest_path=manifest_path)
    resource_envelope = load_artifact_json(
        manifest, "resource", "envelope", manifest_path=manifest_path)
    full_game_map_coverage = load_artifact_json(
        manifest, "resource", "full_game_map_coverage",
        manifest_path=manifest_path)
    asset_inventory = load_artifact_json(
        manifest, "resource", "asset_inventory", manifest_path=manifest_path)
    asset_requirements = load_artifact_json(
        manifest, "resource", "asset_requirements",
        manifest_path=manifest_path)
    registered_asset_intake = load_artifact_json(
        manifest, "resource", "registered_asset_intake",
        manifest_path=manifest_path)
    native_backend_boundary = load_artifact_json(
        manifest, "resource", "native_backend_boundary",
        manifest_path=manifest_path)
    moonlab_job_specs = load_artifact_json(
        manifest, "resource", "moonlab_job_specs",
        manifest_path=manifest_path)
    moonlab_job_results = load_artifact_json(
        manifest, "resource", "moonlab_job_results",
        manifest_path=manifest_path)
    moonlab_replay_plan = load_artifact_json(
        manifest, "resource", "moonlab_replay_plan",
        manifest_path=manifest_path)
    moonlab_submission_packet = load_artifact_json(
        manifest, "resource", "moonlab_submission_packet",
        manifest_path=manifest_path)
    moonlab_submission_bundle = load_artifact_json(
        manifest, "resource", "moonlab_submission_bundle",
        manifest_path=manifest_path)
    moonlab_hardware_template = load_artifact_json(
        manifest, "resource", "moonlab_hardware_record_template",
        manifest_path=manifest_path)
    moonlab_hardware_scope = load_artifact_json(
        manifest, "resource", "moonlab_hardware_submission_scope",
        manifest_path=manifest_path)
    moonlab_full_game_plan = load_artifact_json(
        manifest, "resource", "moonlab_full_game_plan",
        manifest_path=manifest_path)
    moonlab_deployment_gate = load_artifact_json(
        manifest, "resource", "moonlab_deployment_gate",
        manifest_path=manifest_path)
    comparison = dict_or_empty(metrics.get("comparison"))
    return {
        "advantage_problem_id": metrics.get("advantage_problem_id"),
        "trial_count": dict_or_empty(metrics.get("scaling_summary")).get(
            "trial_count"),
        "best_classical": comparison.get("best_classical"),
        "best_qae": comparison.get("best_qae"),
        "resource_estimate": metrics.get("resource_estimate"),
        "moonlab_qae_payload_summary": {
            "schema": qae_payload.get("schema"),
            "status": qae_payload.get("status"),
            "semantic_scope": qae_payload.get("semantic_scope"),
            "payload_resource_estimate": qae_payload.get(
                "payload_resource_estimate"),
            "full_qae_oracle_transpiled": dict_or_empty(
                qae_payload.get("claim_posture")).get(
                    "full_qae_oracle_transpiled"),
        },
        "moonlab_qae_oracle_kernel_summary": {
            "schema": qae_kernel.get("schema"),
            "status": qae_kernel.get("status"),
            "semantic_scope": qae_kernel.get("semantic_scope"),
            "resource_estimate": qae_kernel.get("resource_estimate"),
            "control_plane_executable": dict_or_empty(
                qae_kernel.get("moonlab_control_plane")).get(
                    "control_plane_executable"),
            "qf_oracle_kernel_transpiled": dict_or_empty(
                qae_kernel.get("claim_posture")).get(
                    "qf_oracle_kernel_transpiled"),
            "full_qae_oracle_transpiled": dict_or_empty(
                qae_kernel.get("claim_posture")).get(
                    "full_qae_oracle_transpiled"),
        },
        "moonlab_qae_observation_zero_summary": {
            "schema": qae_observation.get("schema"),
            "status": qae_observation.get("status"),
            "semantic_scope": qae_observation.get("semantic_scope"),
            "resource_estimate": qae_observation.get("resource_estimate"),
            "state_preparation": qae_observation.get("state_preparation"),
            "control_plane_executable": dict_or_empty(
                qae_observation.get("moonlab_control_plane")).get(
                    "control_plane_executable"),
            "candidate_state_preparation_transpiled": dict_or_empty(
                qae_observation.get("claim_posture")).get(
                    "candidate_state_preparation_transpiled"),
            "power_zero_observation_transpiled": dict_or_empty(
                qae_observation.get("claim_posture")).get(
                    "power_zero_observation_transpiled"),
            "full_qae_oracle_transpiled": dict_or_empty(
                qae_observation.get("claim_posture")).get(
                    "full_qae_oracle_transpiled"),
        },
        "moonlab_qae_grover_schedule_plan_summary": {
            "schema": qae_grover.get("schema"),
            "status": qae_grover.get("status"),
            "semantic_scope": qae_grover.get("semantic_scope"),
            "resource_estimate": qae_grover.get("resource_estimate"),
            "ready_observation_count": dict_or_empty(
                qae_grover.get("moonlab_control_plane")).get(
                    "ready_observation_count"),
            "blocked_observation_count": dict_or_empty(
                qae_grover.get("moonlab_control_plane")).get(
                    "blocked_observation_count"),
            "first_blocked_power": dict_or_empty(
                qae_grover.get("moonlab_control_plane")).get(
                    "first_blocked_power"),
            "grover_schedule_transpiled": dict_or_empty(
                qae_grover.get("claim_posture")).get(
                    "full_mlae_schedule_transpiled"),
            "full_qae_oracle_transpiled": dict_or_empty(
                qae_grover.get("claim_posture")).get(
                    "full_qae_oracle_transpiled"),
        },
        "resource_envelope_summary": resource_envelope.get("posture"),
        "full_game_map_coverage_summary": {
            "status": full_game_map_coverage.get("status"),
            "map_set": full_game_map_coverage.get("map_set"),
            "target_map_count": full_game_map_coverage.get("target_map_count"),
            "covered_map_count": full_game_map_coverage.get(
                "covered_map_count"),
            "missing_map_count": full_game_map_coverage.get(
                "missing_map_count"),
        },
        "asset_inventory_summary": {
            "status": asset_inventory.get("status"),
            "asset_root_status": asset_inventory.get("asset_root_status"),
            "available_map_count": asset_inventory.get("available_map_count"),
            "missing_map_count": asset_inventory.get("missing_map_count"),
            "pak_count": asset_inventory.get("pak_count"),
            "invalid_pak_count": asset_inventory.get("invalid_pak_count"),
            "invalid_bsp_count": asset_inventory.get("invalid_bsp_count"),
            "full_game_asset_ready": asset_inventory.get(
                "full_game_asset_ready"),
        },
        "asset_requirements_summary": {
            "schema": asset_requirements.get("schema"),
            "status": asset_requirements.get("status"),
            "target_map_count": asset_requirements.get("target_map_count"),
            "present_map_count": asset_requirements.get("present_map_count"),
            "missing_map_count": asset_requirements.get("missing_map_count"),
            "asset_requirements_satisfied": dict_or_empty(
                asset_requirements.get("claim_posture")).get(
                    "asset_requirements_satisfied"),
        },
        "registered_asset_intake_summary": {
            "schema": registered_asset_intake.get("schema"),
            "status": registered_asset_intake.get("status"),
            "candidate_new_map_count": registered_asset_intake.get(
                "candidate_new_map_count"),
            "missing_map_count_after_plan": registered_asset_intake.get(
                "missing_map_count_after_plan"),
            "copy_plan_count": registered_asset_intake.get("copy_plan_count"),
            "post_install_verification_command_count": (
                registered_asset_intake.get(
                    "post_install_verification_command_count")),
            "post_install_capture_queue_command_present": any(
                isinstance(command, dict) and
                command.get("kind") == "capture_queue"
                for command in list_or_empty(dict_or_empty(
                    registered_asset_intake.get(
                        "post_install_verification")).get("commands"))
            ),
            "discovered_candidate_count": registered_asset_intake.get(
                "discovered_candidate_count", 0),
            "asset_intake_copies_game_data": dict_or_empty(
                registered_asset_intake.get("claim_posture")).get(
                    "asset_intake_copies_game_data"),
        },
        "native_backend_boundary_summary": {
            "status": native_backend_boundary.get("status"),
            "required_target_count": native_backend_boundary.get(
                "required_target_count"),
            "passed_target_count": native_backend_boundary.get(
                "passed_target_count"),
            "blocked_target_count": native_backend_boundary.get(
                "blocked_target_count"),
        },
        "moonlab_job_specs_summary": {
            "selected_job_count": moonlab_job_specs.get("selected_job_count"),
            "hardware_candidate_job_count": moonlab_job_specs.get(
                "hardware_candidate_job_count"),
            "submission_scope": moonlab_job_specs.get("submission_scope"),
        },
        "moonlab_job_results_summary": {
            "overall_status": moonlab_job_results.get("overall_status"),
            "completed_simulator_job_count": moonlab_job_results.get(
                "completed_simulator_job_count"),
            "completed_native_replay_job_count": moonlab_job_results.get(
                "completed_native_replay_job_count"),
            "hardware_submitted_job_count": moonlab_job_results.get(
                "hardware_submitted_job_count"),
            "blocked_job_count": moonlab_job_results.get("blocked_job_count"),
        },
        "moonlab_replay_plan_summary": {
            "schema": moonlab_replay_plan.get("schema"),
            "selected_job_count": moonlab_replay_plan.get(
                "selected_job_count"),
            "hardware_candidate_job_count": moonlab_replay_plan.get(
                "hardware_candidate_job_count"),
            "hardware_submitted_job_count": moonlab_replay_plan.get(
                "hardware_submitted_job_count"),
            "blocked_job_count": moonlab_replay_plan.get("blocked_job_count"),
        },
        "moonlab_submission_packet_summary": {
            "schema": moonlab_submission_packet.get("schema"),
            "hardware_candidate_job_count": moonlab_submission_packet.get(
                "hardware_candidate_job_count"),
            "ready_candidate_count": moonlab_submission_packet.get(
                "ready_candidate_count"),
            "blocked_candidate_count": moonlab_submission_packet.get(
                "blocked_candidate_count"),
            "submitted_candidate_count": moonlab_submission_packet.get(
                "submitted_candidate_count"),
        },
        "moonlab_submission_bundle_summary": {
            "schema": moonlab_submission_bundle.get("schema"),
            "status": moonlab_submission_bundle.get("status"),
            "hardware_candidate_job_count": moonlab_submission_bundle.get(
                "hardware_candidate_job_count"),
            "ready_for_control_plane_submission_count": (
                moonlab_submission_bundle.get(
                    "ready_for_control_plane_submission_count")),
            "calibration_payload_ready_count": moonlab_submission_bundle.get(
                "calibration_payload_ready_count"),
            "oracle_kernel_ready_count": moonlab_submission_bundle.get(
                "oracle_kernel_ready_count"),
            "qae_observation_ready_count": moonlab_submission_bundle.get(
                "qae_observation_ready_count"),
            "grover_schedule_ready_count": moonlab_submission_bundle.get(
                "grover_schedule_ready_count"),
            "transpilation_required_count": moonlab_submission_bundle.get(
                "transpilation_required_count"),
            "missing_artifact_candidate_count": moonlab_submission_bundle.get(
                "missing_artifact_candidate_count"),
            "hardware_submission_directly_executable": (
                moonlab_submission_bundle.get(
                    "hardware_submission_directly_executable")),
            "control_plane_payload_directly_executable": (
                moonlab_submission_bundle.get(
                    "control_plane_payload_directly_executable")),
            "oracle_kernel_directly_executable": moonlab_submission_bundle.get(
                "oracle_kernel_directly_executable"),
            "qae_observation_directly_executable": (
                moonlab_submission_bundle.get(
                    "qae_observation_directly_executable")),
            "grover_schedule_directly_executable": moonlab_submission_bundle.get(
                "grover_schedule_directly_executable"),
        },
        "moonlab_hardware_record_template_summary": {
            "schema": moonlab_hardware_template.get("schema"),
            "record_schema": moonlab_hardware_template.get("record_schema"),
            "job_id": moonlab_hardware_template.get("job_id"),
            "candidate_digest": moonlab_hardware_template.get(
                "candidate_digest"),
        },
        "moonlab_hardware_submission_scope_summary": {
            "schema": moonlab_hardware_scope.get("schema"),
            "status": moonlab_hardware_scope.get("status"),
            "hardware_submission_scope_ready": moonlab_hardware_scope.get(
                "hardware_submission_scope_ready"),
            "hardware_candidate_job_count": moonlab_hardware_scope.get(
                "hardware_candidate_job_count"),
            "ready_for_control_plane_submission_count": (
                moonlab_hardware_scope.get(
                    "ready_for_control_plane_submission_count")),
            "passing_check_count": moonlab_hardware_scope.get(
                "passing_check_count"),
            "attention_check_count": moonlab_hardware_scope.get(
                "attention_check_count"),
            "out_of_scope": moonlab_hardware_scope.get("out_of_scope"),
        },
        "moonlab_full_game_plan_summary": {
            "schema": moonlab_full_game_plan.get("schema"),
            "status": moonlab_full_game_plan.get("status"),
            "target_map_count": moonlab_full_game_plan.get("target_map_count"),
            "covered_map_count": moonlab_full_game_plan.get(
                "covered_map_count"),
            "missing_map_count": moonlab_full_game_plan.get(
                "missing_map_count"),
            "asset_unavailable_map_count": moonlab_full_game_plan.get(
                "asset_unavailable_map_count"),
            "whole_game_moonlab_deployment_claimed": dict_or_empty(
                moonlab_full_game_plan.get("claim_posture")).get(
                    "whole_game_moonlab_deployment_claimed"),
        },
        "moonlab_deployment_gate_summary": {
            "schema": moonlab_deployment_gate.get("schema"),
            "status": moonlab_deployment_gate.get("status"),
            "failed_criterion_count": moonlab_deployment_gate.get(
                "failed_criterion_count"),
            "blocker_count": moonlab_deployment_gate.get("blocker_count"),
            "whole_game_moonlab_deployment_claim_allowed": (
                moonlab_deployment_gate.get(
                    "whole_game_moonlab_deployment_claim_allowed")),
            "whole_game_hardware_execution_claim_allowed": (
                moonlab_deployment_gate.get(
                    "whole_game_hardware_execution_claim_allowed")),
            "hardware_quantum_advantage_claim_allowed": (
                moonlab_deployment_gate.get(
                    "hardware_quantum_advantage_claim_allowed")),
            "dense_70000_qubit_state_claim_allowed": (
                moonlab_deployment_gate.get(
                    "dense_70000_qubit_state_claim_allowed")),
            "target_map_count": dict_or_empty(
                moonlab_deployment_gate.get("summary")).get(
                    "target_map_count"),
            "covered_map_count": dict_or_empty(
                moonlab_deployment_gate.get("summary")).get(
                    "covered_map_count"),
            "coverage_missing_map_count": dict_or_empty(
                moonlab_deployment_gate.get("summary")).get(
                    "coverage_missing_map_count"),
            "asset_missing_map_count": dict_or_empty(
                moonlab_deployment_gate.get("summary")).get(
                    "asset_missing_map_count"),
            "invalid_bsp_count": dict_or_empty(
                moonlab_deployment_gate.get("summary")).get(
                    "invalid_bsp_count"),
            "registered_asset_install_script": dict_or_empty(
                moonlab_deployment_gate.get("summary")).get(
                    "registered_asset_install_script"),
            "registered_asset_intake_file": dict_or_empty(
                moonlab_deployment_gate.get("summary")).get(
                    "registered_asset_intake_file"),
            "post_install_verification_command_count": dict_or_empty(
                moonlab_deployment_gate.get("summary")).get(
                    "post_install_verification_command_count"),
            "post_install_capture_queue_command_present": dict_or_empty(
                moonlab_deployment_gate.get("summary")).get(
                    "post_install_capture_queue_command_present"),
            "post_install_capture_queue_command": dict_or_empty(
                moonlab_deployment_gate.get("summary")).get(
                    "post_install_capture_queue_command"),
            "post_install_capture_queue_script": dict_or_empty(
                moonlab_deployment_gate.get("summary")).get(
                    "post_install_capture_queue_script"),
        },
    }


def manifest_summary_audit(
    manifest: dict[str, Any] | None,
    *,
    manifest_path: Path | None = None,
    required: bool = True,
) -> dict[str, Any]:
    manifest_data = dict_or_empty(manifest)
    recorded_runtime = dict_or_empty(manifest_data.get("runtime_summary"))
    recorded_advantage = dict_or_empty(manifest_data.get("advantage_summary"))
    recorded = bool(recorded_runtime or recorded_advantage)
    if not recorded and not required:
        return {
            "required": required,
            "recorded": False,
            "runtime_summary_recorded": False,
            "advantage_summary_recorded": False,
            "runtime_summary_mismatch_count": 0,
            "advantage_summary_mismatch_count": 0,
            "load_errors": [],
            "mismatch_count": 0,
            "mismatches": {
                "runtime_summary": [],
                "advantage_summary": [],
            },
            "passed": True,
        }

    load_errors: list[dict[str, str]] = []
    runtime_mismatches: list[dict[str, Any]] = []
    advantage_mismatches: list[dict[str, Any]] = []
    try:
        runtime_mismatches = compare_values(
            expected_runtime_summary(manifest_data, manifest_path=manifest_path),
            recorded_runtime,
            prefix="runtime_summary",
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        load_errors.append({"summary": "runtime_summary", "error": str(exc)})
    try:
        advantage_mismatches = compare_values(
            expected_advantage_summary(
                manifest_data,
                manifest_path=manifest_path,
            ),
            recorded_advantage,
            prefix="advantage_summary",
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        load_errors.append({"summary": "advantage_summary", "error": str(exc)})
    mismatch_count = (
        len(runtime_mismatches) +
        len(advantage_mismatches) +
        len(load_errors)
    )
    passed = mismatch_count == 0 and (recorded or not required)
    return {
        "required": required,
        "recorded": recorded,
        "runtime_summary_recorded": bool(recorded_runtime),
        "advantage_summary_recorded": bool(recorded_advantage),
        "runtime_summary_mismatch_count": len(runtime_mismatches),
        "advantage_summary_mismatch_count": len(advantage_mismatches),
        "load_errors": load_errors,
        "mismatch_count": mismatch_count,
        "mismatches": {
            "runtime_summary": runtime_mismatches,
            "advantage_summary": advantage_mismatches,
        },
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
        help="Exit nonzero when manifest summary mirrors are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest_path = resolve_manifest(args.pack_or_manifest)
    try:
        audit = manifest_summary_audit(
            load_json(manifest_path),
            manifest_path=manifest_path,
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_MANIFEST_SUMMARY_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_manifest_summary_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
