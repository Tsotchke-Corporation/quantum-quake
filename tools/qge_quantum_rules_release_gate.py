#!/usr/bin/env python3
"""Build the Quantum Rules v0 release evidence gate.

This is narrower than the shareware release-candidate gate.  It does not claim
registered full-game coverage, hardware execution, hardware advantage, or a
general Noesis play result.  It proves that the deep quantum ruleset evidence is
complete and that the shareware encounter trace contains an explicitly tagged
gameplay-affecting quantum projectile path.
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

import qge_trace_summary  # noqa: E402


PASS = "pass"
BLOCKED = "blocked"
READY_STATUS = "ready_for_quantum_rules_v0_release_claim"
SHAREWARE_MAP_SET = "quake_shareware_episode1"
REQUIRED_RULE_ITEMS = (
    "semantics_contract",
    "measurement_bus",
    "material_operators",
    "projectile_vertical_slice",
    "observer_visibility",
    "weapon_measurements",
    "lab_overlay",
    "replay_trace",
    "shareware_encounter",
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def bool_true(value: Any) -> bool:
    return value is True or value == 1


def load_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def load_trace(path: Path) -> dict[str, Any]:
    if path.suffix == ".bin":
        return qge_trace_summary.parse_trace(str(path))
    data = load_json_object(path)
    if "runtime_evidence" in data:
        return data
    raise ValueError(f"{path} is not a qge_trace_summary JSON or trace bin")


def default_noesis_summary_path(trace_path: Path) -> Path | None:
    if trace_path.name in {"qge_trace.bin", "qge_trace_summary.json"}:
        candidate = trace_path.parent / "qge_noesis_summary.json"
        if candidate.is_file():
            return candidate
    return None


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
    return [item for item in criteria if item.get("status") != PASS]


def task_plan_status(task_plan: dict[str, Any]) -> dict[str, Any]:
    items = {
        str(item.get("id") or ""): item
        for item in list_or_empty(task_plan.get("items"))
        if isinstance(item, dict)
    }
    completed = []
    gate_passed = []
    missing = []
    non_completed = []
    gate_failures = []
    for item_id in REQUIRED_RULE_ITEMS:
        item = dict_or_empty(items.get(item_id))
        if not item:
            missing.append(item_id)
            continue
        if item.get("status") not in {"completed", "verified"}:
            non_completed.append(item_id)
        else:
            completed.append(item_id)
        gates = list_or_empty(item.get("evidence_gates"))
        if not gates:
            gate_failures.append(f"{item_id}:missing_gate")
            continue
        for gate in gates:
            gate_data = dict_or_empty(gate)
            gate_id = str(gate_data.get("id") or "<unknown>")
            if gate_data.get("status") == "pass":
                gate_passed.append(f"{item_id}:{gate_id}")
            else:
                gate_failures.append(f"{item_id}:{gate_id}")
    ready = not missing and not non_completed and not gate_failures
    return {
        "ready": ready,
        "task_id": task_plan.get("task_id"),
        "completed_count": len(completed),
        "required_count": len(REQUIRED_RULE_ITEMS),
        "passed_gate_count": len(gate_passed),
        "missing_items": missing,
        "non_completed_items": non_completed,
        "gate_failures": gate_failures,
    }


def build_gate(
    trace: dict[str, Any],
    *,
    noesis_summary: dict[str, Any] | None = None,
    task_plan: dict[str, Any] | None = None,
    source_trace: Path | None = None,
    source_noesis: Path | None = None,
    source_task_plan: Path | None = None,
) -> dict[str, Any]:
    evidence = dict_or_empty(trace.get("runtime_evidence"))
    shareware = dict_or_empty(evidence.get("shareware_encounter"))
    projectile = dict_or_empty(evidence.get("projectile"))
    projectile_flags = dict_or_empty(projectile.get("flags"))
    material = dict_or_empty(evidence.get("material"))
    material_flags = dict_or_empty(material.get("flags"))
    replay = dict_or_empty(evidence.get("replay_trace"))
    noesis = dict_or_empty(noesis_summary)
    actions = dict_or_empty(noesis.get("actions"))
    commands = dict_or_empty(noesis.get("commands"))
    task_status = task_plan_status(task_plan or {})

    shareware_ready = shareware.get("ready") is True
    kick_count = int_value(shareware.get("shareware_projectile_kick_count"))
    branch_count = int_value(shareware.get("projectile_branch_count"))
    preimpact_count = int_value(
        shareware.get("projectile_preimpact_selection_count"))
    writeback_count = int_value(
        shareware.get("projectile_writeback_apply_count"))
    projectile_correlation_ready = shareware.get(
        "projectile_correlation_ready") is True
    player_visible_material_count = int_value(
        shareware.get("player_visible_material_phase_measurement_count"))
    projectile_gameplay_authority = bool_true(
        projectile_flags.get("gameplay_authority_measurement"))
    replay_ready = replay.get("ready") is True
    replay_save_demo_ready = replay.get("save_demo_ready") is True
    replay_branch_count = int_value(replay.get("projectile_branch_replay_count"))
    replay_writeback_count = int_value(
        replay.get("projectile_writeback_replay_count"))
    replay_collision_oracle_count = int_value(
        replay.get("projectile_collision_oracle_replay_count"))
    replay_trace_id_xor = int_value(replay.get("trace_id_xor"))
    noesis_pass = noesis.get("status") == "pass"
    noesis_phase_count = int_value(actions.get("phase_count"))
    noesis_attack_presses = int_value(
        dict_or_empty(commands.get("press_counts")).get("attack"))
    material_slipgate_count = int_value(material.get("slipgate_phase_count"))
    material_world_surface = bool_true(material_flags.get("world_surface"))
    material_slipgate_scope_honest = (
        material_slipgate_count == 0 or material_world_surface
    )

    criteria = [
        criterion(
            "icc_deep_quantum_ruleset_completed",
            "ICC task plan has all Quantum Rules v0 items complete and gated",
            task_status["ready"],
            "run_and_complete_qge_deep_quantum_ruleset_task_plan",
            **task_status,
        ),
        criterion(
            "shareware_encounter_ready",
            "Shareware encounter runtime evidence is ready",
            shareware_ready,
            "rerun_e1m1_shareware_quantum_fire_trace",
            shareware_ready=shareware_ready,
        ),
        criterion(
            "shareware_projectile_kick_correlated",
            "Encounter records same-projectile quantum kick correlation",
            kick_count > 0 and projectile_correlation_ready,
            "record_correlated_shareware_projectile_kick_probe",
            shareware_projectile_kick_count=kick_count,
            projectile_correlation_ready=projectile_correlation_ready,
            projectile_correlation_subject_id=shareware.get(
                "projectile_correlation_subject_id"),
            projectile_correlation_first_frame=shareware.get(
                "projectile_correlation_first_frame"),
            projectile_correlation_last_frame=shareware.get(
                "projectile_correlation_last_frame"),
        ),
        criterion(
            "projectile_gameplay_writeback",
            "Kicked encounter trace has branch, preimpact, and writeback apply",
            branch_count > 0 and preimpact_count > 0 and writeback_count > 0,
            "capture_branch_preimpact_and_writeback_evidence",
            projectile_branch_count=branch_count,
            projectile_preimpact_selection_count=preimpact_count,
            projectile_writeback_apply_count=writeback_count,
        ),
        criterion(
            "projectile_gameplay_authority_replay",
            "Projectile authority and save/demo replay evidence are present",
            (
                projectile_gameplay_authority and
                replay_ready and
                replay_save_demo_ready and
                replay_branch_count > 0 and
                replay_writeback_count > 0 and
                replay_collision_oracle_count > 0 and
                replay_trace_id_xor != 0
            ),
            "capture_authority_and_replayable_projectile_evidence",
            projectile_gameplay_authority_measurement=(
                projectile_gameplay_authority
            ),
            replay_trace_ready=replay_ready,
            replay_save_demo_ready=replay_save_demo_ready,
            replay_projectile_branch_count=replay_branch_count,
            replay_projectile_writeback_count=replay_writeback_count,
            replay_projectile_collision_oracle_count=(
                replay_collision_oracle_count
            ),
            replay_trace_id_xor=replay_trace_id_xor,
        ),
        criterion(
            "player_visible_material_phase",
            "Player-visible material phase measurement is present",
            player_visible_material_count > 0,
            "capture_player_visible_material_phase_measurement",
            player_visible_material_phase_measurement_count=(
                player_visible_material_count
            ),
        ),
        criterion(
            "material_operator_evidence",
            "Material operator evidence does not overclaim slipgate surfaces",
            material_slipgate_scope_honest,
            "tie_slipgate_operator_to_observed_world_surface",
            slipgate_phase_count=material_slipgate_count,
            material_world_surface=material_world_surface,
            material_slipgate_scope_honest=material_slipgate_scope_honest,
        ),
        criterion(
            "noesis_fire_trace_passed",
            "Noesis fire trace passes with phases and attack presses",
            noesis_pass and noesis_phase_count >= 4 and noesis_attack_presses >= 2,
            "rerun_phase_marked_noesis_fire_trace",
            noesis_status=noesis.get("status"),
            noesis_phase_count=noesis_phase_count,
            noesis_attack_press_count=noesis_attack_presses,
        ),
        criterion(
            "no_overclaim_scope",
            "Gate is scoped to shareware Quantum Rules v0, not full game or hardware",
            True,
            "scope_quantum_rules_claim_to_shareware_simulator_evidence",
            registered_full_game_claim_allowed=False,
            hardware_execution_claim_allowed=False,
            hardware_advantage_claim_allowed=False,
            noesis_learned_play_claim_allowed=False,
        ),
    ]
    failed = failed_criteria(criteria)
    status = PASS if not failed else BLOCKED
    summary = {
        "status": status,
        "ready_status": READY_STATUS if status == PASS else None,
        "map_set": SHAREWARE_MAP_SET,
        "trace_file": str(source_trace) if source_trace is not None else None,
        "noesis_summary_file": (
            str(source_noesis) if source_noesis is not None else None
        ),
        "task_plan_file": (
            str(source_task_plan) if source_task_plan is not None else None
        ),
        "task_plan_ready": task_status["ready"],
        "task_plan_completed_count": task_status["completed_count"],
        "task_plan_passed_gate_count": task_status["passed_gate_count"],
        "shareware_encounter_ready": shareware_ready,
        "shareware_projectile_kick_count": kick_count,
        "projectile_correlation_ready": projectile_correlation_ready,
        "projectile_correlation_subject_id": shareware.get(
            "projectile_correlation_subject_id"),
        "projectile_correlation_first_frame": shareware.get(
            "projectile_correlation_first_frame"),
        "projectile_correlation_last_frame": shareware.get(
            "projectile_correlation_last_frame"),
        "projectile_branch_count": branch_count,
        "projectile_preimpact_selection_count": preimpact_count,
        "projectile_writeback_apply_count": writeback_count,
        "player_visible_material_phase_measurement_count": (
            player_visible_material_count
        ),
        "slipgate_phase_count": material_slipgate_count,
        "material_world_surface": material_world_surface,
        "material_slipgate_scope_honest": material_slipgate_scope_honest,
        "projectile_gameplay_authority_measurement": (
            projectile_gameplay_authority
        ),
        "replay_trace_ready": replay_ready,
        "replay_save_demo_ready": replay_save_demo_ready,
        "replay_projectile_branch_count": replay_branch_count,
        "replay_projectile_writeback_count": replay_writeback_count,
        "replay_projectile_collision_oracle_count": (
            replay_collision_oracle_count
        ),
        "replay_trace_id_xor": replay_trace_id_xor,
        "noesis_status": noesis.get("status"),
        "noesis_phase_count": noesis_phase_count,
        "noesis_attack_press_count": noesis_attack_presses,
    }
    return {
        "schema": "qge.quantum_rules_release_gate.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "ready": status == PASS,
        "ready_status": summary["ready_status"],
        "map_set": SHAREWARE_MAP_SET,
        "criteria": criteria,
        "failed_criteria": failed,
        "failed_criterion_count": len(failed),
        "blocker_count": len(failed),
        "summary": summary,
        "claim_allowed_wording": (
            "Quantum Rules v0 evidence is ready for Quake shareware Episode 1: "
            "QGE state evolves, measurement chooses outcomes, and the selected "
            "outcomes write back into gameplay with replayable evidence."
        ),
        "claim_disallowed_wording": (
            "This is not a registered full-game release, not hardware execution, "
            "not hardware quantum advantage, not a dense state-vector claim, and "
            "not evidence that Noesis learned to play Quake generally."
        ),
        "quantum_rules_v0_claim_allowed": status == PASS,
        "registered_full_game_claim_allowed": False,
        "hardware_execution_claim_allowed": False,
        "hardware_quantum_advantage_claim_allowed": False,
        "noesis_learned_play_claim_allowed": False,
    }


def build_icc_evidence(
    gate: dict[str, Any],
    *,
    out_path: Path | None = None,
    icc_path: Path | None = None,
) -> dict[str, Any]:
    summary = dict_or_empty(gate.get("summary"))
    ready = gate.get("status") == PASS
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_quantum_rules_v0",
        "completion_reason": (
            "qge_quantum_rules_v0_ready"
            if ready else "qge_quantum_rules_v0_blocked"
        ),
        "status": "success",
        "runtime_backend_scope_map_set": SHAREWARE_MAP_SET,
        "qge_quantum_rules_v0_gate_file": str(out_path) if out_path else None,
        "qge_quantum_rules_v0_icc_evidence_file": (
            str(icc_path) if icc_path else None
        ),
        "quantum_rules_v0_claim_allowed": ready,
        "registered_full_game_claim_allowed": False,
        "hardware_execution_claim_allowed": False,
        "hardware_quantum_advantage_claim_allowed": False,
        "noesis_learned_play_claim_allowed": False,
        "gate_status": gate.get("status"),
        "failed_criterion_count": gate.get("failed_criterion_count"),
        "blocker_count": gate.get("blocker_count"),
        "task_plan_completed_count": summary.get("task_plan_completed_count"),
        "task_plan_passed_gate_count": summary.get("task_plan_passed_gate_count"),
        "shareware_encounter_ready": summary.get("shareware_encounter_ready"),
        "shareware_projectile_kick_evidence": (
            "present"
            if int_value(summary.get("shareware_projectile_kick_count")) > 0
            else "missing"
        ),
        "shareware_projectile_kick_evidence_completion": (
            "present"
            if int_value(summary.get("shareware_projectile_kick_count")) > 0
            else "missing"
        ),
        "shareware_projectile_correlation_evidence": (
            "present"
            if summary.get("projectile_correlation_ready") is True
            else "missing"
        ),
        "shareware_projectile_correlation_evidence_completion": (
            "present"
            if summary.get("projectile_correlation_ready") is True
            else "missing"
        ),
        "shareware_projectile_kick_evidence_file": (
            str(out_path) if out_path else None
        ),
        "shareware_projectile_kick_count": summary.get(
            "shareware_projectile_kick_count"),
        "projectile_correlation_ready": summary.get(
            "projectile_correlation_ready"),
        "projectile_correlation_subject_id": summary.get(
            "projectile_correlation_subject_id"),
        "projectile_correlation_first_frame": summary.get(
            "projectile_correlation_first_frame"),
        "projectile_correlation_last_frame": summary.get(
            "projectile_correlation_last_frame"),
        "projectile_branch_count": summary.get("projectile_branch_count"),
        "projectile_preimpact_selection_count": summary.get(
            "projectile_preimpact_selection_count"),
        "projectile_writeback_apply_count": summary.get(
            "projectile_writeback_apply_count"),
        "projectile_gameplay_authority_evidence": (
            "present"
            if summary.get("projectile_gameplay_authority_measurement") is True
            else "missing"
        ),
        "projectile_gameplay_authority_evidence_completion": (
            "present"
            if summary.get("projectile_gameplay_authority_measurement") is True
            else "missing"
        ),
        "projectile_gameplay_authority_measurement": summary.get(
            "projectile_gameplay_authority_measurement"),
        "replay_trace_evidence": (
            "present"
            if summary.get("replay_trace_ready") is True
            else "missing"
        ),
        "replay_trace_evidence_completion": (
            "present"
            if summary.get("replay_trace_ready") is True
            else "missing"
        ),
        "replay_trace_ready": summary.get("replay_trace_ready"),
        "replay_save_demo_ready": summary.get("replay_save_demo_ready"),
        "replay_projectile_branch_count": summary.get(
            "replay_projectile_branch_count"),
        "replay_projectile_writeback_count": summary.get(
            "replay_projectile_writeback_count"),
        "replay_projectile_collision_oracle_count": summary.get(
            "replay_projectile_collision_oracle_count"),
        "replay_trace_id_xor": summary.get("replay_trace_id_xor"),
        "player_visible_material_phase_measurement_count": summary.get(
            "player_visible_material_phase_measurement_count"),
        "slipgate_phase_count": summary.get("slipgate_phase_count"),
        "material_slipgate_world_surface_evidence": (
            "present"
            if (
                int_value(summary.get("slipgate_phase_count")) > 0 and
                summary.get("material_world_surface") is True
            )
            else "missing"
        ),
        "material_operator_scope_evidence": (
            "honest"
            if summary.get("material_slipgate_scope_honest") is True
            else "overclaim"
        ),
        "material_operator_scope_evidence_completion": (
            "honest"
            if summary.get("material_slipgate_scope_honest") is True
            else "overclaim"
        ),
        "material_world_surface": summary.get("material_world_surface"),
        "material_slipgate_scope_honest": summary.get(
            "material_slipgate_scope_honest"),
        "noesis_status": summary.get("noesis_status"),
        "noesis_phase_count": summary.get("noesis_phase_count"),
        "noesis_attack_press_count": summary.get("noesis_attack_press_count"),
    }


def markdown(gate: dict[str, Any]) -> str:
    lines = [
        "# QGE Quantum Rules v0 Release Gate",
        "",
        f"Status: `{gate.get('status')}`",
        f"Map set: `{gate.get('map_set')}`",
        "",
        "| Status | Criterion | Blocker |",
        "|---|---|---|",
    ]
    for item in list_or_empty(gate.get("criteria")):
        data = dict_or_empty(item)
        lines.append(
            f"| `{data.get('status')}` | {data.get('label')} | "
            f"{data.get('blocker') or ''} |"
        )
    lines.append("")
    lines.append("## Summary")
    for key, value in sorted(dict_or_empty(gate.get("summary")).items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Quantum Rules v0 release-gate evidence.")
    parser.add_argument("--trace", required=True,
                        help="qge_trace.bin or qge_trace_summary.json path")
    parser.add_argument("--noesis-summary",
                        help="qge_noesis_summary.json path")
    parser.add_argument("--task-plan", required=True,
                        help="ICC qge_deep_quantum_ruleset session_plan.json")
    parser.add_argument("--out", help="Gate JSON output path")
    parser.add_argument("--markdown", help="Markdown output path")
    parser.add_argument("--icc-json", help="ICC evidence JSON output path")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    trace_path = Path(args.trace)
    noesis_path = (
        Path(args.noesis_summary)
        if args.noesis_summary else default_noesis_summary_path(trace_path)
    )
    task_plan_path = Path(args.task_plan)
    gate_path = Path(args.out) if args.out else None
    icc_path = Path(args.icc_json) if args.icc_json else None
    markdown_path = Path(args.markdown) if args.markdown else None

    trace = load_trace(trace_path)
    noesis_summary = load_json_object(noesis_path) if noesis_path else {}
    task_plan = load_json_object(task_plan_path)
    gate = build_gate(
        trace,
        noesis_summary=noesis_summary,
        task_plan=task_plan,
        source_trace=trace_path,
        source_noesis=noesis_path,
        source_task_plan=task_plan_path,
    )

    if gate_path:
        write_json(gate_path, gate)
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown(gate), encoding="utf-8")
    if icc_path:
        write_json(
            icc_path,
            build_icc_evidence(gate, out_path=gate_path, icc_path=icc_path),
        )

    if not gate_path:
        print(json.dumps(gate, indent=2, sort_keys=True))
    return 0 if gate.get("status") == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
