#!/usr/bin/env python3
"""Summarize Noesis gameplay evidence from a QGE stream run."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import qge_image_metrics


COMBAT_VERBS = {
    "attack",
    "fire",
    "shoot",
    "advance-fire",
    "fire-forward",
    "push-fire",
    "attack-move",
    "retreat-fire",
    "kite-back",
    "strafe-fire-left",
    "fire-strafe-left",
    "strafe-fire-right",
    "fire-strafe-right",
    "circle-fire-left",
    "circle-strafe-left",
    "circle-fire-right",
    "circle-strafe-right",
}
MOVEMENT_VERBS = {
    "forward",
    "back",
    "backward",
    "turn-left",
    "turn-right",
    "strafe-left",
    "strafe-right",
    "move-left",
    "move-right",
    "jump",
    "hop",
    "jump-forward",
    "hop-forward",
    "speed-jump-forward",
    "run-jump-forward",
    "jump-run-forward",
    "door-bump",
    "door-push",
    "bump-door",
    "run-forward",
    "sprint-forward",
    "charge",
    "wall-slide-left",
    "wall-slide-right",
    "route-left",
    "route-right",
    "corridor-left",
    "corridor-right",
    "circle-left",
    "circle-right",
    "circle-fire-left",
    "circle-fire-right",
    "swim-up",
    "swim-down",
    "move-up",
    "move-down",
}
ROUTE_VERBS = {
    "run-forward",
    "sprint-forward",
    "charge",
    "jump-forward",
    "hop-forward",
    "speed-jump-forward",
    "run-jump-forward",
    "jump-run-forward",
    "door-bump",
    "door-push",
    "bump-door",
    "wall-slide-left",
    "wall-slide-right",
    "route-left",
    "route-right",
    "corridor-left",
    "corridor-right",
    "circle-left",
    "circle-right",
}
BUTTON_COMMANDS = {
    "attack",
    "forward",
    "back",
    "left",
    "right",
    "moveleft",
    "moveright",
    "jump",
    "use",
    "speed",
    "strafe",
    "moveup",
    "movedown",
    "lookup",
    "lookdown",
    "klook",
    "mlook",
}


def read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return [line.rstrip("\n") for line in f]


def action_verb(line: str) -> str:
    stripped = line.split("#", 1)[0].strip()
    if not stripped:
        return ""
    return stripped.split(None, 1)[0].lower()


def command_token(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    return stripped.split(None, 1)[0]


def summarize_actions(path: Path) -> dict[str, Any]:
    raw_lines = read_lines(path)
    lines = [line.strip() for line in raw_lines if line.strip()]
    verbs = [action_verb(line) for line in lines]
    verb_counts = Counter(verb for verb in verbs if verb)
    phases = [
        line.split("QGE_NOESIS_PHASE", 1)[1].strip()
        for line in lines
        if "QGE_NOESIS_PHASE" in line
    ]
    policy_markers = [
        line for line in lines if "QGE_NOESIS_POLICY" in line
    ]
    combat_count = sum(verb_counts[verb] for verb in COMBAT_VERBS)
    movement_count = sum(verb_counts[verb] for verb in MOVEMENT_VERBS)
    route_count = sum(verb_counts[verb] for verb in ROUTE_VERBS)
    return {
        "path": str(path),
        "exists": path.is_file(),
        "line_count": len(lines),
        "policy_marker_count": len(policy_markers),
        "phase_count": len(phases),
        "phases": phases,
        "verb_counts": dict(sorted(verb_counts.items())),
        "combat_action_count": combat_count,
        "movement_action_count": movement_count,
        "route_action_count": route_count,
    }


def summarize_commands(path: Path) -> dict[str, Any]:
    raw_lines = read_lines(path)
    lines = [line.strip() for line in raw_lines if line.strip()]
    command_counts = Counter(command_token(line) for line in lines)
    press_counts: Counter[str] = Counter()
    release_counts: Counter[str] = Counter()
    max_consecutive_waits = 0
    consecutive_waits = 0
    for line in lines:
        token = command_token(line)
        if token == "wait":
            consecutive_waits += 1
            max_consecutive_waits = max(max_consecutive_waits, consecutive_waits)
        else:
            consecutive_waits = 0
        if token.startswith("+") and token[1:] in BUTTON_COMMANDS:
            press_counts[token[1:]] += 1
        elif token.startswith("-") and token[1:] in BUTTON_COMMANDS:
            release_counts[token[1:]] += 1

    skipped_unknown = [
        line for line in lines if "skipped_unknown_action=" in line
    ]
    wait_clamped = [
        line for line in lines if "QGE_NOESIS_PLAYER wait_clamped" in line
    ]
    policy_markers = [
        line for line in lines if "QGE_NOESIS_POLICY" in line
    ]
    phase_markers = [
        line for line in lines if "QGE_NOESIS_PHASE" in line
    ]
    return {
        "path": str(path),
        "exists": path.is_file(),
        "line_count": len(lines),
        "wait_count": command_counts.get("wait", 0),
        "max_consecutive_waits": max_consecutive_waits,
        "press_counts": dict(sorted(press_counts.items())),
        "release_counts": dict(sorted(release_counts.items())),
        "pressed_button_variety": len(press_counts),
        "policy_marker_count": len(policy_markers),
        "phase_marker_count": len(phase_markers),
        "player_start_present": any("QGE_NOESIS_PLAYER start" in line for line in lines),
        "player_done_present": any("QGE_NOESIS_PLAYER done" in line for line in lines),
        "wait_clamped_count": len(wait_clamped),
        "wait_clamped_lines": wait_clamped,
        "skipped_unknown_count": len(skipped_unknown),
        "skipped_unknown_lines": skipped_unknown,
    }


def summarize_log(path: Path) -> dict[str, Any]:
    lines = read_lines(path)
    unknown_commands = [
        line.strip() for line in lines if "Unknown command" in line
    ]
    noesis_lines = [
        line.strip() for line in lines if "QGE_NOESIS_" in line
    ]
    phases = [
        line.split("QGE_NOESIS_PHASE", 1)[1].strip()
        for line in noesis_lines
        if "QGE_NOESIS_PHASE" in line
    ]
    return {
        "path": str(path),
        "exists": path.is_file(),
        "unknown_command_count": len(unknown_commands),
        "unknown_command_lines": unknown_commands,
        "noesis_log_line_count": len(noesis_lines),
        "phase_count": len(phases),
        "phases": phases,
        "policy_start_present": any("QGE_NOESIS_POLICY" in line for line in noesis_lines),
        "policy_done_present": any("QGE_NOESIS_POLICY done" in line for line in noesis_lines),
        "player_start_present": any("QGE_NOESIS_PLAYER start" in line for line in noesis_lines),
        "player_done_present": any("QGE_NOESIS_PLAYER done" in line for line in noesis_lines),
    }


def summarize_trace(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
        }
    with path.open("r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    runtime = data.get("runtime_evidence") or {}
    ai = runtime.get("ai") or {}
    render = runtime.get("render") or {}
    visibility = runtime.get("visibility") or {}
    projectile = runtime.get("projectile") or {}
    return {
        "path": str(path),
        "exists": True,
        "single_trace_ready": bool(runtime.get("single_trace_ready", False)),
        "ai_decision_count": int(ai.get("decision_count") or 0),
        "render_sparse_dwt_count": int(render.get("sparse_dwt_count") or 0),
        "render_native_bridge_count": int(render.get("native_bridge_count") or 0),
        "render_native_fallback_count": int(render.get("native_fallback_count") or 0),
        "visibility_authority_apply_count": int(
            visibility.get("authority_apply_count") or 0
        ),
        "projectile_branch_state_count": int(
            projectile.get("branch_state_count") or 0
        ),
    }


def frame_paths(frames_dir: Path) -> list[Path]:
    if not frames_dir.is_dir():
        return []
    return sorted(
        path for path in frames_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".png"
    )


def summarize_frames(frames_dir: Path) -> dict[str, Any]:
    frames = frame_paths(frames_dir)
    summary: dict[str, Any] = {
        "frames_dir": str(frames_dir),
        "exists": frames_dir.is_dir(),
        "frame_count": len(frames),
        "first_frame": str(frames[0]) if frames else "",
        "last_frame": str(frames[-1]) if frames else "",
        "delta_status": "not_enough_frames",
        "delta": None,
    }
    if len(frames) < 2:
        return summary
    try:
        metrics = qge_image_metrics.compute_metrics(frames[0], frames[-1], [16, 32, 64])
    except RuntimeError as exc:
        summary["delta_status"] = "dependency_missing"
        summary["delta_error"] = str(exc)
        return summary
    except Exception as exc:  # pragma: no cover - defensive artifact path
        summary["delta_status"] = "failed"
        summary["delta_error"] = str(exc)
        return summary
    summary["delta_status"] = "complete"
    summary["delta"] = {
        "mae_rgb": metrics.get("mae_rgb"),
        "mae_rgb_normalized": metrics.get("mae_rgb_normalized"),
        "luma_mae": metrics.get("luma_mae"),
        "luma_ssim_global": metrics.get("luma_ssim_global"),
        "histogram_intersection_rgb": metrics.get("histogram_intersection_rgb"),
    }
    return summary


def score_component(value: float, maximum: float, weight: float) -> float:
    if maximum <= 0.0:
        return 0.0
    bounded = max(0.0, min(float(value), maximum))
    return round((bounded / maximum) * weight, 3)


def build_gameplay_score(
    actions: dict[str, Any],
    commands: dict[str, Any],
    log: dict[str, Any],
    frames: dict[str, Any],
    trace: dict[str, Any],
    gates: dict[str, bool],
) -> dict[str, Any]:
    press_counts = commands.get("press_counts") or {}
    delta = frames.get("delta") or {}
    mae_norm = delta.get("mae_rgb_normalized")
    if not isinstance(mae_norm, (int, float)):
        mae_norm = 0.0

    runtime_score = 0.0
    if trace.get("ai_decision_count", 0) > 0:
        runtime_score += 5.0
    if (
        trace.get("render_sparse_dwt_count", 0) > 0 or
        trace.get("render_native_bridge_count", 0) > 0
    ):
        runtime_score += 5.0
    if trace.get("exists") and trace.get("render_native_fallback_count", 0) == 0:
        runtime_score += 5.0
    if trace.get("visibility_authority_apply_count", 0) > 0:
        runtime_score += 5.0

    route_button_count = sum(
        1 for button in ("speed", "forward", "moveleft", "moveright", "jump")
        if int(press_counts.get(button) or 0) > 0
    )
    wait_ratio = 0.0
    if commands.get("line_count", 0) > 0:
        wait_ratio = float(commands.get("wait_count", 0)) / float(commands["line_count"])
    wait_ratio_ok = 0.30 <= wait_ratio <= 0.85
    generated_phase_count = int(actions.get("phase_count") or 0)
    executed_phase_count = int(log.get("phase_count") or 0)
    if generated_phase_count > 0:
        phase_ratio = min(1.0, executed_phase_count / generated_phase_count)
    else:
        phase_ratio = 1.0 if log.get("policy_done_present") else 0.0

    breakdown = {
        "harness_validity": (
            20.0 if (
                gates.get("required_inputs_present", False) and
                gates.get("run_completed", True) and
                gates.get("frames_present", True) and
                gates.get("no_unknown_actions", False) and
                gates.get("no_unknown_commands", False) and
                commands.get("wait_clamped_count", 0) == 0
            ) else 0.0
        ),
        "intent_richness": round(
            score_component(actions.get("line_count", 0), 24.0, 4.0) +
            score_component(actions.get("movement_action_count", 0), 10.0, 4.0) +
            score_component(actions.get("combat_action_count", 0), 8.0, 4.0) +
            score_component(commands.get("pressed_button_variety", 0), 8.0, 4.0) +
            (4.0 if wait_ratio_ok else 0.0),
            3,
        ),
        "observable_world_change": round(
            score_component(frames.get("frame_count", 0), 12.0, 5.0) +
            score_component(mae_norm, 0.12, 15.0),
            3,
        ),
        "runtime_engagement": runtime_score,
        "route_control": round(
            score_component(actions.get("route_action_count", 0), 5.0, 6.0) +
            score_component(route_button_count, 5.0, 4.0),
            3,
        ),
        "runtime_plan_progress": round(
            score_component(phase_ratio, 1.0, 7.0) +
            (3.0 if log.get("policy_done_present") else 0.0),
            3,
        ),
    }
    raw_score = round(sum(breakdown.values()), 3)
    blocking_gates = sorted(key for key, value in gates.items() if not value)
    score = min(raw_score, 39.0) if blocking_gates else raw_score
    if blocking_gates:
        grade = "blocked_by_gates"
    elif score >= 90.0:
        grade = "excellent_smoke"
    elif score >= 75.0:
        grade = "strong_smoke"
    elif score >= 60.0:
        grade = "fair_smoke"
    elif score >= 40.0:
        grade = "weak_smoke"
    else:
        grade = "blocked_or_idle"
    return {
        "score": score,
        "raw_score": raw_score,
        "max_score": 100,
        "grade": grade,
        "blocking_gates": blocking_gates,
        "breakdown": breakdown,
        "wait_ratio": round(wait_ratio, 4),
        "route_button_count": route_button_count,
        "executed_phase_count": executed_phase_count,
        "generated_phase_count": generated_phase_count,
        "phase_execution_ratio": round(phase_ratio, 4),
        "outcome_telemetry_present": False,
        "outcome_telemetry_missing": [
            "kills",
            "damage_dealt",
            "damage_taken",
            "health",
            "armor",
            "pickups",
            "position",
            "map_progress",
        ],
    }


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.manifest) if args.manifest else {}
    input_manifest = manifest.get("input") or {}
    run_manifest = manifest.get("run") or {}
    plan = args.plan or str(input_manifest.get("noesis_plan") or "")
    player = args.player or str(input_manifest.get("player") or "noesis")
    actions = summarize_actions(args.actions)
    commands = summarize_commands(args.commands)
    log = summarize_log(args.log)
    trace = summarize_trace(args.trace_summary) if args.trace_summary else {
        "path": "",
        "exists": False,
    }
    frames = summarize_frames(args.frames_dir) if args.frames_dir else {
        "frames_dir": "",
        "exists": False,
        "frame_count": 0,
        "delta_status": "not_requested",
        "delta": None,
    }
    missing_inputs = []
    if args.manifest and not args.manifest.is_file():
        missing_inputs.append(str(args.manifest))
    for input_path in (args.actions, args.commands, args.log):
        if not input_path.is_file():
            missing_inputs.append(str(input_path))
    if args.trace_summary and not args.trace_summary.is_file():
        missing_inputs.append(str(args.trace_summary))
    if args.frames_dir and not args.frames_dir.is_dir():
        missing_inputs.append(str(args.frames_dir))

    gates = {
        "player_is_noesis": player == "noesis",
        "required_inputs_present": not missing_inputs,
        "actions_present": actions["line_count"] >= args.min_actions,
        "commands_present": commands["line_count"] >= args.min_commands,
        "no_unknown_actions": commands["skipped_unknown_count"] == 0,
        "no_unknown_commands": log["unknown_command_count"] == 0,
        "movement_actions_present": actions["movement_action_count"] > 0,
        "combat_actions_present": actions["combat_action_count"] > 0,
        "phase_markers_present": actions["phase_count"] > 0,
        "frames_present": frames["frame_count"] >= args.min_frames,
    }
    if args.manifest:
        gates["manifest_present"] = bool(manifest)
        gates["run_completed"] = (
            (run_manifest.get("success") in (1, True)) and
            int(run_manifest.get("timed_out") or 0) == 0 and
            not str(run_manifest.get("startup_issue") or "")
        )
    if args.require_phase_markers:
        gates["phase_markers_required"] = gates["phase_markers_present"]
    if args.require_combat:
        gates["combat_required"] = gates["combat_actions_present"]
    if args.min_frame_mae is not None:
        delta = frames.get("delta") or {}
        mae = delta.get("mae_rgb")
        gates["frame_delta_required"] = (
            isinstance(mae, (int, float)) and mae >= args.min_frame_mae
        )
    if args.min_log_phases > 0:
        gates["log_phase_markers_required"] = (
            log["phase_count"] >= args.min_log_phases
        )
    gameplay_score = build_gameplay_score(actions, commands, log, frames, trace, gates)

    failures = [key for key, value in gates.items() if not value]
    status = "pass" if not failures else "blocked"
    if player != "noesis":
        status = "not_requested"

    return {
        "schema": "qge.noesis_summary.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "plan": plan,
        "player": player,
        "map": manifest.get("map", ""),
        "run": {
            "status": run_manifest.get("status", ""),
            "success": run_manifest.get("success", 0),
            "timed_out": run_manifest.get("timed_out", 0),
            "startup_issue": run_manifest.get("startup_issue", ""),
            "frames_requested": manifest.get("frames_requested", 0),
            "frames_captured": manifest.get("frames_captured", 0),
        },
        "inputs": {
            "manifest": str(args.manifest) if args.manifest else "",
            "actions": str(args.actions),
            "commands": str(args.commands),
            "log": str(args.log),
            "trace_summary": str(args.trace_summary) if args.trace_summary else "",
            "frames_dir": str(args.frames_dir) if args.frames_dir else "",
            "missing_inputs": missing_inputs,
        },
        "actions": actions,
        "commands": commands,
        "log": log,
        "trace": trace,
        "frames": frames,
        "gameplay_score": gameplay_score,
        "quality_gates": gates,
        "failures": failures,
    }


def build_icc_evidence(summary: dict[str, Any], summary_path: Path) -> list[dict[str, Any]]:
    actions = summary.get("actions") or {}
    commands = summary.get("commands") or {}
    frames = summary.get("frames") or {}
    trace = summary.get("trace") or {}
    run = summary.get("run") or {}
    log = summary.get("log") or {}
    return [
        {
            "kind": "runtime_backend",
            "name": "runtime_backend",
            "value": "qge_noesis_summary",
            "path": str(summary_path),
        },
        {
            "kind": "completion_condition",
            "name": "completion_reason",
            "value": "qge_noesis_summary_complete",
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_summary_status",
            "value": summary.get("status"),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_failure_free",
            "value": not summary.get("failures"),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_plan",
            "value": summary.get("plan", ""),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_player",
            "value": summary.get("player", ""),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_run_status",
            "value": run.get("status", ""),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_action_count",
            "value": actions.get("line_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_command_count",
            "value": commands.get("line_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_frame_count",
            "value": frames.get("frame_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_ai_decision_count",
            "value": trace.get("ai_decision_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_route_action_count",
            "value": actions.get("route_action_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_quality_score",
            "value": (summary.get("gameplay_score") or {}).get("score", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_quality_grade",
            "value": (summary.get("gameplay_score") or {}).get("grade", ""),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_log_phase_count",
            "value": log.get("phase_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_log_policy_done",
            "value": log.get("policy_done_present", False),
            "path": str(summary_path),
        },
        {
            "kind": "artifact",
            "name": "noesis_actions_file",
            "value": (summary.get("inputs") or {}).get("actions", ""),
            "path": str(summary_path),
        },
        {
            "kind": "artifact",
            "name": "noesis_commands_file",
            "value": (summary.get("inputs") or {}).get("commands", ""),
            "path": str(summary_path),
        },
        {
            "kind": "artifact",
            "name": "noesis_summary_file",
            "value": str(summary_path),
            "path": str(summary_path),
        },
    ]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--actions", type=Path, required=True)
    parser.add_argument("--commands", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--trace-summary", type=Path)
    parser.add_argument("--frames-dir", type=Path)
    parser.add_argument("--plan", default="")
    parser.add_argument("--player", default="")
    parser.add_argument("--min-actions", type=int, default=1)
    parser.add_argument("--min-commands", type=int, default=1)
    parser.add_argument("--min-frames", type=int, default=0)
    parser.add_argument("--min-frame-mae", type=float)
    parser.add_argument("--min-log-phases", type=int, default=0)
    parser.add_argument("--require-phase-markers", action="store_true")
    parser.add_argument("--require-combat", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--icc-out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    summary = build_summary(args)
    if args.out:
        write_json(args.out, summary)
    else:
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    if args.icc_out:
        summary_path = args.out or args.icc_out
        write_json(args.icc_out, build_icc_evidence(summary, summary_path))
    return 0 if summary["status"] in {"pass", "not_requested"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
