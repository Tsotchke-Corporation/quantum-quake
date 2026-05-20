#!/usr/bin/env python3
"""Summarize Noesis gameplay evidence from a QGE stream run."""

from __future__ import annotations

import argparse
import json
import math
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
    "scan-fire-left",
    "sweep-fire-left",
    "turn-fire-left",
    "scan-fire-right",
    "sweep-fire-right",
    "turn-fire-right",
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
    "door-open",
    "use-bump",
    "open-door",
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
    "scan-fire-left",
    "scan-fire-right",
    "sweep-fire-left",
    "sweep-fire-right",
    "turn-fire-left",
    "turn-fire-right",
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
    "door-open",
    "use-bump",
    "open-door",
    "wall-slide-left",
    "wall-slide-right",
    "route-left",
    "route-right",
    "corridor-left",
    "corridor-right",
    "circle-left",
    "circle-right",
}
ROUTE_PHASE_HINTS = {
    "route",
    "bridge",
    "door",
    "exit",
    "probe",
    "push",
    "slide",
    "recovery",
}
COMBAT_PHASE_HINTS = {
    "clear",
    "combat",
    "fire",
    "spawn",
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
MOVEMENT_BUTTONS = {
    "forward",
    "back",
    "left",
    "right",
    "moveleft",
    "moveright",
    "jump",
    "speed",
    "moveup",
    "movedown",
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


def normalize_phase_name(phase: Any) -> str:
    text = str(phase or "").strip()
    if text.startswith("phase="):
        text = text.split("=", 1)[1].strip()
    return text


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
        "normalized_phases": [normalize_phase_name(phase) for phase in phases],
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


def movement_intent_present(
    actions: dict[str, Any],
    commands: dict[str, Any],
) -> bool:
    press_counts = commands.get("press_counts") or {}
    return (
        int(actions.get("movement_action_count") or 0) > 0 or
        any(int(press_counts.get(button) or 0) > 0
            for button in MOVEMENT_BUTTONS)
    )


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
        "normalized_phases": [normalize_phase_name(phase) for phase in phases],
        "policy_start_present": any("QGE_NOESIS_POLICY" in line for line in noesis_lines),
        "policy_done_present": any("QGE_NOESIS_POLICY done" in line for line in noesis_lines),
        "player_start_present": any("QGE_NOESIS_PLAYER start" in line for line in noesis_lines),
        "player_done_present": any("QGE_NOESIS_PLAYER done" in line for line in noesis_lines),
    }


def value_at(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def as_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def vector_distance(a: Any, b: Any) -> float:
    if not isinstance(a, list) or not isinstance(b, list):
        return 0.0
    if len(a) < 3 or len(b) < 3:
        return 0.0
    return math.sqrt(sum(
        (as_number(a[i], 0.0) - as_number(b[i], 0.0)) ** 2
        for i in range(3)
    ))


def metric_delta(end: dict[str, Any], start: dict[str, Any], *keys: str) -> float:
    return max(0.0, as_number(snapshot_value_at(end, *keys), 0.0) -
               as_number(snapshot_value_at(start, *keys), 0.0))


def snapshot_value_at(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    state = data.get("state") if isinstance(data, dict) else None
    if isinstance(state, dict):
        value = value_at(state, *keys, default=None)
        if value is not None:
            return value
    return value_at(data, *keys, default=default)


def phase_requires(phase: str, hints: set[str]) -> bool:
    lowered = phase.lower()
    return any(hint in lowered for hint in hints)


def summarize_phase_progress(
    phase_events: list[dict[str, Any]],
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_events = sorted(
        phase_events,
        key=lambda event: int(as_number(event.get("frame"), 0.0)),
    )
    normalized_phases = [
        normalize_phase_name(event.get("phase")) for event in ordered_events
    ]
    intervals: list[dict[str, Any]] = []
    blocked_phases: list[str] = []
    route_blocked = 0
    combat_blocked = 0
    stuck_windows = 0

    for index, event in enumerate(ordered_events):
        phase = normalize_phase_name(event.get("phase"))
        start_frame = int(as_number(event.get("frame"), 0.0))
        if index + 1 < len(ordered_events):
            end_state = ordered_events[index + 1]
            end_frame = int(as_number(end_state.get("frame"), start_frame))
        elif samples:
            end_state = samples[-1]
            end_frame = int(as_number(end_state.get("frame"), start_frame))
        else:
            end_state = event
            end_frame = start_frame

        interval_samples = [
            sample for sample in samples
            if start_frame < int(as_number(sample.get("frame"), 0.0)) <= end_frame
        ]
        visible_enemy_samples = sum(
            1 for sample in interval_samples
            if as_number(value_at(sample, "combat", "visible_enemy_count"), 0.0) > 0
            or bool(value_at(sample, "combat", "nearest_enemy_visible", default=False))
        )
        enemy_contact_samples = sum(
            1 for sample in interval_samples
            if (
                as_number(value_at(sample, "combat", "visible_enemy_count"), 0.0) > 0
                or 0.0 <= as_number(
                    value_at(sample, "combat", "nearest_enemy_distance"), -1.0
                ) <= 768.0
            )
        )
        attack_active_samples = sum(
            1 for sample in interval_samples
            if bool(value_at(sample, "player", "attack_active", default=False))
        )
        attack_visible_samples = sum(
            1 for sample in interval_samples
            if bool(value_at(sample, "player", "attack_active", default=False))
            and (
                as_number(
                    value_at(sample, "combat", "visible_enemy_count"), 0.0
                ) > 0
                or bool(value_at(
                    sample, "combat", "nearest_enemy_visible", default=False
                ))
            )
        )
        attack_aligned_samples = sum(
            1 for sample in interval_samples
            if bool(value_at(sample, "player", "attack_active", default=False))
            and (
                as_number(
                    value_at(
                        sample, "combat", "aligned_visible_enemy_count"
                    ),
                    0.0,
                ) > 0
                or bool(value_at(
                    sample, "combat", "nearest_enemy_aligned", default=False
                ))
            )
        )
        stationary_samples = sum(
            1 for sample in interval_samples
            if as_number(value_at(sample, "route", "frame_distance"), 0.0) < 1.0
        )
        distance_delta = metric_delta(
            end_state, event, "route", "total_distance")
        displacement_delta = metric_delta(
            end_state, event, "route", "max_displacement_from_start")
        leaf_delta = metric_delta(
            end_state, event, "route", "leaf_transition_count")
        attack_delta = metric_delta(
            end_state, event, "combat", "attack_presses_total")
        attack_visible_delta = metric_delta(
            end_state, event, "combat", "attack_visible_total")
        attack_aligned_delta = metric_delta(
            end_state, event, "combat", "attack_aligned_total")
        damage_delta = metric_delta(
            end_state, event, "combat", "damage_dealt_inferred_total")
        kill_delta = metric_delta(end_state, event, "combat", "kills_total")
        pickup_delta = metric_delta(end_state, event, "pickup", "pickups_total")
        route_required = phase_requires(phase, ROUTE_PHASE_HINTS)
        combat_required = phase_requires(phase, COMBAT_PHASE_HINTS)
        route_progress = (
            distance_delta >= 8.0 or displacement_delta >= 8.0 or
            leaf_delta > 0.0 or pickup_delta > 0.0
        )
        combat_progress = (
            damage_delta > 0.0 or kill_delta > 0.0 or
            attack_aligned_delta > 0.0 or attack_aligned_samples > 0
        )
        route_pass = not route_required or route_progress
        combat_pass = not combat_required or combat_progress
        stationary_fraction = (
            stationary_samples / len(interval_samples)
            if interval_samples else 0.0
        )
        stuck_window = (
            route_required and len(interval_samples) >= 6 and
            stationary_fraction >= 0.75 and not route_progress and
            damage_delta <= 0.0 and kill_delta <= 0.0
        )

        if not route_pass:
            route_blocked += 1
        if not combat_pass:
            combat_blocked += 1
        if stuck_window:
            stuck_windows += 1
        if not route_pass or not combat_pass or stuck_window:
            blocked_phases.append(phase)

        intervals.append({
            "phase": phase,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "sample_count": len(interval_samples),
            "route_required": route_required,
            "combat_required": combat_required,
            "distance_delta": round(distance_delta, 3),
            "displacement_delta": round(displacement_delta, 3),
            "leaf_transition_delta": int(leaf_delta),
            "attack_press_delta": int(attack_delta),
            "attack_visible_delta": int(attack_visible_delta),
            "attack_aligned_delta": int(attack_aligned_delta),
            "damage_dealt_delta": int(damage_delta),
            "kill_delta": int(kill_delta),
            "pickup_delta": int(pickup_delta),
            "visible_enemy_sample_count": visible_enemy_samples,
            "enemy_contact_sample_count": enemy_contact_samples,
            "attack_active_sample_count": attack_active_samples,
            "attack_visible_sample_count": attack_visible_samples,
            "attack_aligned_sample_count": attack_aligned_samples,
            "stationary_fraction": round(stationary_fraction, 4),
            "route_progress_pass": route_pass,
            "combat_progress_pass": combat_pass,
            "stuck_window": stuck_window,
        })

    return {
        "outcome_event_count": len(ordered_events),
        "phases": [str(event.get("phase") or "") for event in ordered_events],
        "normalized_phases": normalized_phases,
        "progress_interval_count": len(intervals),
        "progress_pass_count": sum(
            1 for interval in intervals
            if interval["route_progress_pass"] and
            interval["combat_progress_pass"] and
            not interval["stuck_window"]
        ),
        "progress_blocked_count": len(set(blocked_phases)),
        "route_blocked_count": route_blocked,
        "combat_blocked_count": combat_blocked,
        "stuck_window_count": stuck_windows,
        "blocked_phases": sorted(set(blocked_phases)),
        "intervals": intervals,
    }


def summarize_gameplay(path: Path | None) -> dict[str, Any]:
    if not path:
        return {
            "path": "",
            "exists": False,
            "sample_count": 0,
            "event_count": 0,
        }
    lines = read_lines(path)
    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
            "sample_count": 0,
            "event_count": 0,
        }

    samples: list[dict[str, Any]] = []
    phase_events: list[dict[str, Any]] = []
    event_counts: Counter[str] = Counter()
    parse_error_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError:
            parse_error_count += 1
            continue
        if not isinstance(item, dict):
            continue
        if item.get("type") == "sample":
            samples.append(item)
        elif item.get("type") == "event":
            kind = str(item.get("kind") or "unknown")
            event_counts[kind] += 1
            if kind == "noesis_phase":
                phase_events.append(item)

    if not samples:
        return {
            "path": str(path),
            "exists": True,
            "line_count": len([line for line in lines if line.strip()]),
            "parse_error_count": parse_error_count,
            "sample_count": 0,
            "event_count": sum(event_counts.values()),
            "event_counts": dict(sorted(event_counts.items())),
            "phase": summarize_phase_progress(phase_events, []),
        }

    playable_samples = [
        sample for sample in samples
        if as_number(value_at(sample, "player", "health"), 0.0) > 0.0
        or as_number(value_at(sample, "player", "weapon"), 0.0) != 0.0
        or as_number(value_at(sample, "player", "items"), 0.0) != 0.0
    ]
    if not playable_samples:
        playable_samples = samples
    first = playable_samples[0]
    last = playable_samples[-1]
    health_values = [
        as_number(value_at(sample, "player", "health"), 0.0)
        for sample in playable_samples
    ]
    armor_values = [
        as_number(value_at(sample, "player", "armor"), 0.0)
        for sample in playable_samples
    ]
    damage_taken = max(
        as_number(value_at(sample, "combat", "damage_taken_total"), 0.0)
        for sample in playable_samples
    )
    damage_dealt = max(
        as_number(value_at(
            sample, "combat", "damage_dealt_inferred_total"), 0.0)
        for sample in playable_samples
    )
    kills = max(
        as_number(value_at(sample, "combat", "kills_total"), 0.0)
        for sample in playable_samples
    )
    pickups = max(
        as_number(value_at(sample, "pickup", "pickups_total"), 0.0)
        for sample in playable_samples
    )
    attack_presses = max(
        as_number(value_at(sample, "combat", "attack_presses_total"), 0.0)
        for sample in playable_samples
    )
    attack_visible_total = max(
        as_number(value_at(sample, "combat", "attack_visible_total"), -1.0)
        for sample in playable_samples
    )
    attack_aligned_total = max(
        as_number(value_at(sample, "combat", "attack_aligned_total"), -1.0)
        for sample in playable_samples
    )
    weapon_changes = max(
        as_number(value_at(sample, "pickup", "weapon_changes_total"), 0.0)
        for sample in playable_samples
    )
    total_distance = max(
        as_number(value_at(sample, "route", "total_distance"), 0.0)
        for sample in playable_samples
    )
    max_displacement = max(
        as_number(value_at(
            sample, "route", "max_displacement_from_start"), 0.0)
        for sample in playable_samples
    )
    leaf_transitions = max(
        as_number(value_at(sample, "route", "leaf_transition_count"), 0.0)
        for sample in playable_samples
    )
    end_displacement = as_number(
        value_at(last, "route", "displacement_from_start"), 0.0)
    route_frame_distances: list[float] = []
    route_progress_sample_count = 0
    route_stationary_frame_count = 0
    route_stationary_run = 0
    route_stationary_run_max = 0
    route_terminal_stationary_run = 0
    route_progress_best = as_number(
        value_at(first, "route", "displacement_from_start"), 0.0)
    for index, sample in enumerate(playable_samples):
        frame_distance = as_number(
            value_at(sample, "route", "frame_distance"), -1.0)
        origin_delta = 0.0
        total_distance_delta = 0.0
        displacement_delta = 0.0
        displacement_now = as_number(
            value_at(sample, "route", "displacement_from_start"), 0.0)
        if index > 0:
            prev_sample = playable_samples[index - 1]
            origin_delta = vector_distance(
                value_at(prev_sample, "player", "origin"),
                value_at(sample, "player", "origin"),
            )
            total_distance_delta = max(0.0, as_number(
                value_at(sample, "route", "total_distance"), 0.0) -
                as_number(value_at(prev_sample, "route", "total_distance"), 0.0))
            displacement_delta = abs(displacement_now - as_number(
                value_at(prev_sample, "route", "displacement_from_start"), 0.0))
        if frame_distance < 0.0:
            frame_distance = total_distance_delta if total_distance_delta > 0.0 else origin_delta
        elif (
            index > 0 and frame_distance >= 1.0 and
            total_distance_delta < 1.0 and origin_delta < 1.0 and
            displacement_delta < 1.0
        ):
            frame_distance = 0.0
        route_frame_distances.append(frame_distance)
        if index == 0:
            continue
        if displacement_now >= route_progress_best + 8.0:
            route_progress_sample_count += 1
            route_progress_best = displacement_now
        if frame_distance < 1.0:
            route_stationary_frame_count += 1
            route_stationary_run += 1
            route_stationary_run_max = max(
                route_stationary_run_max, route_stationary_run)
        else:
            route_stationary_run = 0
    for frame_distance in reversed(route_frame_distances[1:]):
        if frame_distance < 1.0:
            route_terminal_stationary_run += 1
        else:
            break
    route_interval_count = max(len(playable_samples) - 1, 1)
    route_movement_efficiency = (
        max_displacement / total_distance if total_distance > 0.0 else 0.0
    )
    route_end_progress_ratio = (
        end_displacement / max_displacement if max_displacement > 0.0 else 0.0
    )
    terminal_start_index = max(
        0, len(playable_samples) - route_terminal_stationary_run - 1)
    terminal_base = playable_samples[terminal_start_index]
    terminal_samples = playable_samples[terminal_start_index + 1:]
    terminal_leaf_delta = max(0.0, max(
        [as_number(value_at(sample, "route", "leaf_transition_count"), 0.0)
         for sample in terminal_samples] +
        [as_number(value_at(terminal_base, "route", "leaf_transition_count"), 0.0)]
    ) - as_number(
        value_at(terminal_base, "route", "leaf_transition_count"), 0.0))
    terminal_damage_delta = max(0.0, max(
        [as_number(value_at(sample, "combat", "damage_dealt_inferred_total"), 0.0)
         for sample in terminal_samples] +
        [as_number(value_at(terminal_base, "combat", "damage_dealt_inferred_total"), 0.0)]
    ) - as_number(value_at(
        terminal_base, "combat", "damage_dealt_inferred_total"), 0.0))
    terminal_kill_delta = max(0.0, max(
        [as_number(value_at(sample, "combat", "kills_total"), 0.0)
         for sample in terminal_samples] +
        [as_number(value_at(terminal_base, "combat", "kills_total"), 0.0)]
    ) - as_number(value_at(terminal_base, "combat", "kills_total"), 0.0))
    terminal_pickup_delta = max(0.0, max(
        [as_number(value_at(sample, "pickup", "pickups_total"), 0.0)
         for sample in terminal_samples] +
        [as_number(value_at(terminal_base, "pickup", "pickups_total"), 0.0)]
    ) - as_number(value_at(terminal_base, "pickup", "pickups_total"), 0.0))
    terminal_attack_delta = max(0.0, max(
        [as_number(value_at(sample, "combat", "attack_presses_total"), 0.0)
         for sample in terminal_samples] +
        [as_number(value_at(terminal_base, "combat", "attack_presses_total"), 0.0)]
    ) - as_number(value_at(
        terminal_base, "combat", "attack_presses_total"), 0.0))
    terminal_visible_enemy_samples = sum(
        1 for sample in terminal_samples
        if as_number(value_at(sample, "combat", "visible_enemy_count"), 0.0) > 0
        or bool(value_at(sample, "combat", "nearest_enemy_visible", default=False))
    )
    terminal_combat_activity = (
        terminal_damage_delta > 0.0 or terminal_kill_delta > 0.0 or
        (terminal_attack_delta > 0.0 and terminal_visible_enemy_samples > 0)
    )
    route_terminal_activity = terminal_leaf_delta > 0.0 or terminal_pickup_delta > 0.0
    route_terminal_stall_threshold = max(12, math.ceil(route_interval_count * 0.10))
    route_terminal_stall = (
        route_terminal_stationary_run >= route_terminal_stall_threshold and
        not route_terminal_activity and not terminal_combat_activity
    )
    route_recovered_after_stall = (
        route_stationary_run_max >= 6 and not route_terminal_stall and
        route_terminal_stationary_run < route_stationary_run_max
    )
    visible_enemy_frames = sum(
        1 for sample in playable_samples
        if as_number(value_at(sample, "combat", "visible_enemy_count"), 0.0) > 0
        or bool(value_at(sample, "combat", "nearest_enemy_visible", default=False))
    )
    aligned_visible_enemy_frames = sum(
        1 for sample in playable_samples
        if as_number(
            value_at(sample, "combat", "aligned_visible_enemy_count"), 0.0
        ) > 0
        or bool(value_at(sample, "combat", "nearest_enemy_aligned", default=False))
    )
    attack_visible_frames_fallback = sum(
        1 for sample in playable_samples
        if bool(value_at(sample, "player", "attack_active", default=False))
        and (
            as_number(value_at(sample, "combat", "visible_enemy_count"), 0.0) > 0
            or bool(value_at(
                sample, "combat", "nearest_enemy_visible", default=False
            ))
        )
    )
    attack_aligned_frames_fallback = sum(
        1 for sample in playable_samples
        if bool(value_at(sample, "player", "attack_active", default=False))
        and (
            as_number(
                value_at(sample, "combat", "aligned_visible_enemy_count"), 0.0
            ) > 0
            or bool(value_at(
                sample, "combat", "nearest_enemy_aligned", default=False
            ))
        )
    )
    attack_visible_frames = (
        attack_visible_total
        if attack_visible_total >= 0.0 else attack_visible_frames_fallback
    )
    attack_aligned_frames = (
        attack_aligned_total
        if attack_aligned_total >= 0.0 else attack_aligned_frames_fallback
    )
    attack_active_frames = sum(
        1 for sample in playable_samples
        if bool(value_at(sample, "player", "attack_active", default=False))
    )
    blind_attack_frames = sum(
        1 for sample in playable_samples
        if bool(value_at(sample, "player", "attack_active", default=False))
        and not (
            as_number(value_at(sample, "combat", "visible_enemy_count"), 0.0) > 0
            or bool(value_at(
                sample, "combat", "nearest_enemy_visible", default=False
            ))
        )
    )
    visible_unaligned_attack_frames = max(
        0.0, attack_visible_frames - attack_aligned_frames
    )
    unproductive_attack_frames = max(
        0.0, attack_active_frames - attack_aligned_frames
    )
    aim_errors = [
        as_number(
            value_at(sample, "combat", "nearest_enemy_angle_error_deg"), -1.0
        )
        for sample in playable_samples
    ]
    aim_errors = [value for value in aim_errors if value >= 0.0]
    attack_alignment_fraction = (
        attack_aligned_frames / attack_visible_frames
        if attack_visible_frames > 0.0 else 0.0
    )
    attack_visibility_fraction = (
        attack_visible_frames / attack_active_frames
        if attack_active_frames > 0.0 else 0.0
    )
    blind_attack_fraction = (
        blind_attack_frames / attack_active_frames
        if attack_active_frames > 0.0 else 0.0
    )
    unproductive_attack_fraction = (
        unproductive_attack_frames / attack_active_frames
        if attack_active_frames > 0.0 else 0.0
    )
    damage_per_attack_press = (
        damage_dealt / attack_presses if attack_presses > 0.0 else 0.0
    )
    net_damage_per_attack_press = (
        (damage_dealt - damage_taken) / attack_presses
        if attack_presses > 0.0 else 0.0
    )
    enemy_contact_frames = sum(
        1 for sample in playable_samples
        if (
            as_number(value_at(sample, "combat", "visible_enemy_count"), 0.0) > 0
            or 0.0 <= as_number(
                value_at(sample, "combat", "nearest_enemy_distance"), -1.0
            ) <= 768.0
        )
    )
    nearest_distances = [
        as_number(value_at(sample, "combat", "nearest_enemy_distance"), -1.0)
        for sample in playable_samples
    ]
    nearest_distances = [value for value in nearest_distances if value >= 0.0]
    assist_active_frames = sum(
        1 for sample in playable_samples
        if bool(value_at(sample, "assist", "active", default=False))
    )
    assist_telemetry_samples = sum(
        1 for sample in playable_samples
        if isinstance(value_at(sample, "assist", default=None), dict)
    )
    assist_visible_target_frames = sum(
        1 for sample in playable_samples
        if bool(value_at(sample, "assist", "target_visible", default=False))
    )
    assist_modes = [
        as_number(value_at(sample, "assist", "mode"), 0.0)
        for sample in playable_samples
    ]
    assist_target_distances = [
        as_number(value_at(sample, "assist", "target_distance"), -1.0)
        for sample in playable_samples
    ]
    assist_target_distances = [
        value for value in assist_target_distances if value >= 0.0
    ]
    assist_target_ids = {
        int(as_number(value_at(sample, "assist", "target_id"), 0.0))
        for sample in playable_samples
        if int(as_number(value_at(sample, "assist", "target_id"), 0.0)) > 0
    }
    assist_steering_frames = sum(
        1 for sample in playable_samples
        if abs(as_number(value_at(sample, "assist", "forwardmove"), 0.0)) > 0.0
        or abs(as_number(value_at(sample, "assist", "sidemove"), 0.0)) > 0.0
    )
    assist_wall_probe_frames = sum(
        1 for sample in playable_samples
        if as_number(value_at(sample, "assist", "forward_clear"), -1.0) >= 0.0
        or as_number(value_at(sample, "assist", "left_clear"), -1.0) >= 0.0
        or as_number(value_at(sample, "assist", "right_clear"), -1.0) >= 0.0
    )
    assist_attack_visible_frames = sum(
        1 for sample in playable_samples
        if bool(value_at(sample, "assist", "active", default=False))
        and bool(value_at(sample, "assist", "target_visible", default=False))
        and bool(value_at(sample, "player", "attack_active", default=False))
    )
    death_count = 0
    prev_health = health_values[0]
    for health in health_values[1:]:
        if prev_health > 0.0 and health <= 0.0:
            death_count += 1
        prev_health = health

    return {
        "path": str(path),
        "exists": True,
        "line_count": len([line for line in lines if line.strip()]),
        "parse_error_count": parse_error_count,
        "sample_count": len(samples),
        "playable_sample_count": len(playable_samples),
        "event_count": sum(event_counts.values()),
        "event_counts": dict(sorted(event_counts.items())),
        "first_frame": int(as_number(first.get("frame"), 0.0)),
        "last_frame": int(as_number(last.get("frame"), 0.0)),
        "player": {
            "health_start": health_values[0],
            "health_end": health_values[-1],
            "health_min": min(health_values),
            "armor_start": armor_values[0],
            "armor_end": armor_values[-1],
            "armor_max": max(armor_values),
            "death_count": death_count,
            "survived": death_count == 0 and health_values[-1] > 0.0,
            "start_origin": value_at(first, "player", "origin", default=[]),
            "end_origin": value_at(last, "player", "origin", default=[]),
        },
        "route": {
            "total_distance": total_distance,
            "max_displacement_from_start": max_displacement,
            "end_displacement_from_start": end_displacement,
            "leaf_transition_count": leaf_transitions,
            "progress_sample_count": route_progress_sample_count,
            "progress_fraction": round(
                route_progress_sample_count / route_interval_count, 4),
            "stationary_frame_count": route_stationary_frame_count,
            "stationary_fraction": round(
                route_stationary_frame_count / route_interval_count, 4),
            "stationary_run_max": route_stationary_run_max,
            "terminal_stationary_run": route_terminal_stationary_run,
            "terminal_stall_threshold": route_terminal_stall_threshold,
            "terminal_stall": route_terminal_stall,
            "terminal_visible_enemy_samples": terminal_visible_enemy_samples,
            "recovered_after_stall": route_recovered_after_stall,
            "movement_efficiency": round(route_movement_efficiency, 4),
            "end_progress_ratio": round(route_end_progress_ratio, 4),
            "backtrack_distance": round(
                max(0.0, max_displacement - end_displacement), 3),
        },
        "combat": {
            "damage_taken": damage_taken,
            "damage_dealt_inferred": damage_dealt,
            "kills": kills,
            "attack_press_count": attack_presses,
            "attack_active_frames": attack_active_frames,
            "attack_visible_frames": attack_visible_frames,
            "attack_aligned_frames": attack_aligned_frames,
            "blind_attack_frames": blind_attack_frames,
            "visible_unaligned_attack_frames": visible_unaligned_attack_frames,
            "unproductive_attack_frames": unproductive_attack_frames,
            "attack_visibility_fraction": round(
                attack_visibility_fraction, 4),
            "blind_attack_fraction": round(blind_attack_fraction, 4),
            "unproductive_attack_fraction": round(
                unproductive_attack_fraction, 4),
            "attack_alignment_fraction": round(attack_alignment_fraction, 4),
            "visible_enemy_frames": visible_enemy_frames,
            "aligned_visible_enemy_frames": aligned_visible_enemy_frames,
            "enemy_contact_frames": enemy_contact_frames,
            "nearest_enemy_distance_min": (
                min(nearest_distances) if nearest_distances else None
            ),
            "nearest_enemy_angle_error_min": (
                min(aim_errors) if aim_errors else None
            ),
            "nearest_enemy_angle_error_avg": (
                round(sum(aim_errors) / len(aim_errors), 4)
                if aim_errors else None
            ),
            "damage_per_attack_press": round(damage_per_attack_press, 4),
            "net_damage_per_attack_press": round(
                net_damage_per_attack_press, 4),
        },
        "pickup": {
            "pickup_count": pickups,
            "weapon_change_count": weapon_changes,
        },
        "assist": {
            "telemetry_sample_count": assist_telemetry_samples,
            "active_frames": assist_active_frames,
            "active_sample_count": assist_active_frames,
            "active_fraction": round(
                assist_active_frames / len(playable_samples), 4
            ),
            "visible_target_frames": assist_visible_target_frames,
            "target_visible_sample_count": assist_visible_target_frames,
            "mode_max": max(assist_modes) if assist_modes else 0.0,
            "target_count": len(assist_target_ids),
            "target_distance_min": (
                min(assist_target_distances)
                if assist_target_distances else None
            ),
            "target_distance_max": (
                max(assist_target_distances)
                if assist_target_distances else None
            ),
            "steering_frames": assist_steering_frames,
            "steering_sample_count": assist_steering_frames,
            "wall_probe_sample_count": assist_wall_probe_frames,
            "attack_visible_frames": assist_attack_visible_frames,
        },
        "phase": summarize_phase_progress(phase_events, playable_samples),
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
    header = data.get("header") or {}
    replay_health = data.get("replay_health") or {}
    ai = runtime.get("ai") or {}
    render = runtime.get("render") or {}
    visibility = runtime.get("visibility") or {}
    projectile = runtime.get("projectile") or {}
    return {
        "path": str(path),
        "exists": True,
        "run_id": header.get("run_id", 0),
        "moonlab_abi_hash": header.get("moonlab_abi_hash", 0),
        "qge_build_hash": header.get("qge_build_hash", 0),
        "quake_content_hash": header.get("quake_content_hash", 0),
        "single_trace_ready": bool(runtime.get("single_trace_ready", False)),
        "ai_decision_count": int(ai.get("decision_count") or 0),
        "entropy_replay_events": int(
            replay_health.get("entropy_replay_events") or 0
        ),
        "replay_metadata_mismatches": int(
            replay_health.get("replay_metadata_mismatches") or 0
        ),
        "replay_exhaustions": int(
            replay_health.get("replay_exhaustions") or 0
        ),
        "ai_decision_replay_metadata_mismatches": int(
            replay_health.get("ai_decision_replay_metadata_mismatches") or 0
        ),
        "ai_decision_replay_exhaustions": int(
            replay_health.get("ai_decision_replay_exhaustions") or 0
        ),
        "render_sparse_dwt_count": int(render.get("sparse_dwt_count") or 0),
        "render_native_bridge_count": int(render.get("native_bridge_count") or 0),
        "render_native_fallback_count": int(render.get("native_fallback_count") or 0),
        "visibility_authority_apply_count": int(
            visibility.get("authority_apply_count") or 0
        ),
        "projectile_branch_state_count": int(
            projectile.get("branch_state_count") or 0
        ),
        "projectile_save_demo_boundary_count": int(
            projectile.get("save_demo_boundary_count") or 0
        ),
        "projectile_save_demo_writeback_count": int(
            projectile.get("save_demo_writeback_count") or 0
        ),
        "projectile_save_demo_branch_count": int(
            projectile.get("save_demo_branch_count") or 0
        ),
        "projectile_save_demo_collision_oracle_count": int(
            projectile.get("save_demo_collision_oracle_count") or 0
        ),
        "projectile_save_demo_trace_id_xor": int(
            projectile.get("save_demo_trace_id_xor") or 0
        ),
        "projectile_flags_or": int(projectile.get("flags_or") or 0),
        "projectile_off_reason": projectile.get("off_reason", ""),
        "projectile_branch_selected_probability_max": float(
            projectile.get("branch_selected_probability_max") or 0.0
        ),
        "projectile_preimpact_selected_probability_max": float(
            projectile.get("preimpact_selected_probability_max") or 0.0
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
    gameplay: dict[str, Any],
    gates: dict[str, bool],
    min_route_distance: float = 64.0,
) -> dict[str, Any]:
    press_counts = commands.get("press_counts") or {}
    delta = frames.get("delta") or {}
    gameplay_present = int(gameplay.get("sample_count") or 0) >= 2
    assist_state = gameplay.get("assist") or {}
    assist_telemetry_present = (
        int(assist_state.get("active_frames") or 0) > 0 or
        int(assist_state.get("mode_max") or 0) > 0
    )
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
    has_movement_intent = movement_intent_present(actions, commands)
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

    if gameplay_present:
        player = gameplay.get("player") or {}
        route = gameplay.get("route") or {}
        combat = gameplay.get("combat") or {}
        pickup = gameplay.get("pickup") or {}
        total_distance = float(route.get("total_distance") or 0.0)
        max_displacement = float(route.get("max_displacement_from_start") or 0.0)
        terminal_stall = bool(route.get("terminal_stall", False))
        leaf_transitions = float(route.get("leaf_transition_count") or 0.0)
        damage_dealt = float(combat.get("damage_dealt_inferred") or 0.0)
        damage_taken = float(combat.get("damage_taken") or 0.0)
        kills = float(combat.get("kills") or 0.0)
        attack_presses = float(combat.get("attack_press_count") or 0.0)
        attack_visible_frames = float(combat.get("attack_visible_frames") or 0.0)
        attack_aligned_frames = float(combat.get("attack_aligned_frames") or 0.0)
        unproductive_attack_fraction = max(
            0.0,
            min(float(combat.get("unproductive_attack_fraction") or 0.0), 1.0),
        )
        productive_attack_fraction = max(0.0, 1.0 - unproductive_attack_fraction)
        visible_enemy_frames = float(combat.get("visible_enemy_frames") or 0.0)
        contact_frames = float(combat.get("enemy_contact_frames") or 0.0)
        pickups = float(pickup.get("pickup_count") or 0.0)
        survived = bool(player.get("survived", False))
        min_distance = max(float(min_route_distance), 1.0)
        not_stuck = (
            not has_movement_intent or
            not terminal_stall and (
                total_distance >= min(48.0, min_distance) or
                max_displacement >= min(32.0, min_distance)
            )
        )

        breakdown = {
            "harness_validity": (
                15.0 if (
                    gates.get("required_inputs_present", False) and
                    gates.get("run_completed", True) and
                    gates.get("frames_present", True) and
                    gates.get("no_unknown_actions", False) and
                    gates.get("no_unknown_commands", False) and
                    commands.get("wait_clamped_count", 0) == 0
                ) else 0.0
            ),
            "intent_richness": round(
                score_component(actions.get("line_count", 0), 24.0, 2.0) +
                score_component(actions.get("movement_action_count", 0), 10.0, 2.0) +
                score_component(actions.get("combat_action_count", 0), 8.0, 2.0) +
                score_component(commands.get("pressed_button_variety", 0), 8.0, 2.0) +
                (2.0 if wait_ratio_ok else 0.0),
                3,
            ),
            "observable_world_change": round(
                score_component(frames.get("frame_count", 0), 12.0, 4.0) +
                score_component(mae_norm, 0.12, 6.0),
                3,
            ),
            "runtime_engagement": round(runtime_score * 0.75, 3),
            "route_progress": round(
                score_component(total_distance, min_distance * 2.5, 7.0) +
                score_component(max_displacement, min_distance, 7.0) +
                score_component(leaf_transitions, 2.0, 3.0) +
                score_component(pickups, 1.0, 3.0),
                3,
            ),
            "combat_effectiveness": round(
                score_component(attack_presses, 2.0, 3.0) *
                productive_attack_fraction +
                score_component(visible_enemy_frames, 4.0, 2.0) +
                score_component(attack_visible_frames, 4.0, 2.0) +
                score_component(attack_aligned_frames, 3.0, 3.0) +
                score_component(contact_frames, 8.0, 1.0) +
                score_component(damage_dealt, 40.0, 6.0) +
                score_component(kills, 1.0, 3.0),
                3,
            ),
            "survival_no_stuck": round(
                (6.0 if survived else 0.0) +
                (2.0 if not_stuck else 0.0) +
                (2.0 if damage_taken <= 75.0 else 0.0),
                3,
            ),
        }
    else:
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
        "outcome_telemetry_present": gameplay_present,
        "assist_telemetry_present": assist_telemetry_present,
        "outcome_telemetry_missing": [] if gameplay_present else [
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
    noesis_manifest = manifest.get("noesis") or {}
    plan = args.plan or str(input_manifest.get("noesis_plan") or "")
    player = args.player or str(input_manifest.get("player") or "noesis")
    noesis_assist_requested = int(as_number(
        input_manifest.get("noesis_assist"), 0.0))
    gameplay_path = args.gameplay_outcomes
    if gameplay_path is None:
        manifest_gameplay = noesis_manifest.get("gameplay_outcomes_file") or ""
        if manifest_gameplay:
            gameplay_path = Path(str(manifest_gameplay))
    actions = summarize_actions(args.actions)
    commands = summarize_commands(args.commands)
    log = summarize_log(args.log)
    gameplay = summarize_gameplay(gameplay_path)
    min_phase_outcomes = int(getattr(args, "min_phase_outcomes", 0) or 0)
    movement_intent = movement_intent_present(actions, commands)
    assist_state = gameplay.get("assist") or {}
    assist_active = int(assist_state.get("active_frames") or 0) > 0
    unassisted_claim_supported = (
        noesis_assist_requested <= 0 and not assist_active
    )
    claim_scope = (
        "unassisted" if unassisted_claim_supported else "server_assisted"
    )
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
    if args.gameplay_outcomes and not args.gameplay_outcomes.is_file():
        missing_inputs.append(str(args.gameplay_outcomes))
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
        "movement_actions_present": movement_intent,
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
    if args.min_gameplay_samples > 0:
        gates["gameplay_outcomes_required"] = (
            gameplay.get("sample_count", 0) >= args.min_gameplay_samples
        )
    phase_state = gameplay.get("phase") or {}
    if min_phase_outcomes > 0:
        phase_event_count = int(phase_state.get("outcome_event_count") or 0)
        phase_names = set(phase_state.get("normalized_phases") or [])
        logged_names = [
            phase for phase in (log.get("normalized_phases") or [])
            if phase
        ]
        gates["phase_outcome_events_required"] = (
            phase_event_count >= min_phase_outcomes
        )
        gates["phase_outcome_state_required"] = (
            phase_event_count >= min_phase_outcomes and
            int(phase_state.get("progress_interval_count") or 0) >=
            min_phase_outcomes
        )
        gates["phase_outcome_markers_match"] = all(
            phase in phase_names for phase in logged_names
        )
        gates["phase_stuck_windows_absent"] = (
            int(phase_state.get("stuck_window_count") or 0) == 0
        )
        gates["phase_route_progress_required"] = (
            int(phase_state.get("route_blocked_count") or 0) == 0
        )
        if args.require_combat:
            gates["phase_combat_progress_required"] = (
                int(phase_state.get("combat_blocked_count") or 0) == 0
            )
    if gameplay.get("sample_count", 0) >= 2:
        player_state = gameplay.get("player") or {}
        route_state = gameplay.get("route") or {}
        combat_state = gameplay.get("combat") or {}
        total_distance = float(route_state.get("total_distance") or 0.0)
        max_displacement = float(
            route_state.get("max_displacement_from_start") or 0.0)
        terminal_stall = bool(route_state.get("terminal_stall", False))
        damage_dealt = float(
            combat_state.get("damage_dealt_inferred") or 0.0)
        kills = float(combat_state.get("kills") or 0.0)
        attack_aligned_frames = float(
            combat_state.get("attack_aligned_frames") or 0.0)
        gates["survived"] = bool(player_state.get("survived", False))
        if args.require_combat:
            gates["combat_effectiveness_required"] = (
                damage_dealt > 0.0 or kills > 0.0 or
                attack_aligned_frames > 0.0
            )
        if actions.get("route_action_count", 0) > 0 and args.min_route_distance > 0:
            gates["route_progress_required"] = (
                total_distance >= args.min_route_distance or
                max_displacement >= args.min_route_distance
            )
        if movement_intent:
            gates["not_stuck"] = (
                not terminal_stall and (
                    total_distance >= min(48.0, args.min_route_distance) or
                    max_displacement >= min(32.0, args.min_route_distance)
                )
            )
            gates["terminal_stall_absent"] = not terminal_stall
    gameplay_score = build_gameplay_score(
        actions,
        commands,
        log,
        frames,
        trace,
        gameplay,
        gates,
        args.min_route_distance,
    )

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
            "gameplay_outcomes": str(gameplay_path) if gameplay_path else "",
            "trace_summary": str(args.trace_summary) if args.trace_summary else "",
            "frames_dir": str(args.frames_dir) if args.frames_dir else "",
            "missing_inputs": missing_inputs,
            "noesis_assist_requested": noesis_assist_requested,
            "claim_scope": claim_scope,
        },
        "actions": actions,
        "commands": commands,
        "log": log,
        "gameplay": gameplay,
        "trace": trace,
        "frames": frames,
        "gameplay_score": gameplay_score,
        "quality_gates": gates,
        "claim_gates": {
            "unassisted_claim_supported": unassisted_claim_supported,
        },
        "failures": failures,
    }


def build_icc_evidence(summary: dict[str, Any], summary_path: Path) -> list[dict[str, Any]]:
    actions = summary.get("actions") or {}
    commands = summary.get("commands") or {}
    frames = summary.get("frames") or {}
    trace = summary.get("trace") or {}
    run = summary.get("run") or {}
    log = summary.get("log") or {}
    gameplay = summary.get("gameplay") or {}
    gameplay_player = gameplay.get("player") or {}
    gameplay_route = gameplay.get("route") or {}
    gameplay_combat = gameplay.get("combat") or {}
    gameplay_pickup = gameplay.get("pickup") or {}
    gameplay_assist = gameplay.get("assist") or {}
    gameplay_phase = gameplay.get("phase") or {}
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
            "name": "noesis_claim_scope",
            "value": (summary.get("inputs") or {}).get(
                "claim_scope", "unassisted"),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_unassisted_claim_supported",
            "value": (summary.get("claim_gates") or {}).get(
                "unassisted_claim_supported", False),
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
            "name": "noesis_trace_run_id",
            "value": trace.get("run_id", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_trace_qge_build_hash",
            "value": trace.get("qge_build_hash", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_trace_quake_content_hash",
            "value": trace.get("quake_content_hash", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_replay_metadata_mismatches",
            "value": trace.get("replay_metadata_mismatches", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_replay_exhaustions",
            "value": trace.get("replay_exhaustions", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_ai_decision_replay_metadata_mismatches",
            "value": trace.get("ai_decision_replay_metadata_mismatches", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_ai_decision_replay_exhaustions",
            "value": trace.get("ai_decision_replay_exhaustions", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_projectile_save_demo_boundary_count",
            "value": trace.get("projectile_save_demo_boundary_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_projectile_save_demo_writeback_count",
            "value": trace.get("projectile_save_demo_writeback_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_projectile_save_demo_branch_count",
            "value": trace.get("projectile_save_demo_branch_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_projectile_save_demo_collision_oracle_count",
            "value": trace.get("projectile_save_demo_collision_oracle_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_projectile_save_demo_trace_id_xor",
            "value": trace.get("projectile_save_demo_trace_id_xor", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_projectile_off_reason",
            "value": trace.get("projectile_off_reason", ""),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_projectile_branch_selected_probability_max",
            "value": trace.get("projectile_branch_selected_probability_max", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_projectile_preimpact_selected_probability_max",
            "value": trace.get("projectile_preimpact_selected_probability_max", 0),
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
            "name": "noesis_gameplay_phase_event_count",
            "value": gameplay_phase.get("outcome_event_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_phase_state_count",
            "value": gameplay_phase.get("progress_interval_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_phase_progress_pass_count",
            "value": gameplay_phase.get("progress_pass_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_phase_progress_blocked_count",
            "value": gameplay_phase.get("progress_blocked_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_phase_stuck_window_count",
            "value": gameplay_phase.get("stuck_window_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_phase_blocked_phases",
            "value": ",".join(gameplay_phase.get("blocked_phases") or []),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_log_policy_done",
            "value": log.get("policy_done_present", False),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_assist_requested_mode",
            "value": (summary.get("inputs") or {}).get(
                "noesis_assist_requested", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_outcome_sample_count",
            "value": gameplay.get("sample_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_total_distance",
            "value": gameplay_route.get("total_distance", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_max_displacement",
            "value": gameplay_route.get("max_displacement_from_start", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_terminal_stall",
            "value": gameplay_route.get("terminal_stall", False),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_max_stationary_run",
            "value": gameplay_route.get("stationary_run_max", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_stationary_fraction",
            "value": gameplay_route.get("stationary_fraction", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_movement_efficiency",
            "value": gameplay_route.get("movement_efficiency", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_end_progress_ratio",
            "value": gameplay_route.get("end_progress_ratio", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_survived",
            "value": gameplay_player.get("survived", False),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_damage_dealt_inferred",
            "value": gameplay_combat.get("damage_dealt_inferred", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_damage_taken",
            "value": gameplay_combat.get("damage_taken", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_kills",
            "value": gameplay_combat.get("kills", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_visible_enemy_frames",
            "value": gameplay_combat.get("visible_enemy_frames", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_aligned_visible_enemy_frames",
            "value": gameplay_combat.get("aligned_visible_enemy_frames", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_attack_visible_frames",
            "value": gameplay_combat.get("attack_visible_frames", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_attack_active_frames",
            "value": gameplay_combat.get("attack_active_frames", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_blind_attack_frames",
            "value": gameplay_combat.get("blind_attack_frames", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_visible_unaligned_attack_frames",
            "value": gameplay_combat.get("visible_unaligned_attack_frames", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_unproductive_attack_frames",
            "value": gameplay_combat.get("unproductive_attack_frames", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_attack_visibility_fraction",
            "value": gameplay_combat.get("attack_visibility_fraction", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_blind_attack_fraction",
            "value": gameplay_combat.get("blind_attack_fraction", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_unproductive_attack_fraction",
            "value": gameplay_combat.get("unproductive_attack_fraction", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_attack_aligned_frames",
            "value": gameplay_combat.get("attack_aligned_frames", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_attack_alignment_fraction",
            "value": gameplay_combat.get("attack_alignment_fraction", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_nearest_enemy_angle_error_min",
            "value": gameplay_combat.get("nearest_enemy_angle_error_min"),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_damage_per_attack_press",
            "value": gameplay_combat.get("damage_per_attack_press", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_net_damage_per_attack_press",
            "value": gameplay_combat.get("net_damage_per_attack_press", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_gameplay_pickups",
            "value": gameplay_pickup.get("pickup_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_assist_active_frames",
            "value": gameplay_assist.get("active_frames", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_assist_telemetry_sample_count",
            "value": gameplay_assist.get("telemetry_sample_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_assist_active_sample_count",
            "value": gameplay_assist.get("active_sample_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_assist_active_fraction",
            "value": gameplay_assist.get("active_fraction", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_assist_visible_target_frames",
            "value": gameplay_assist.get("visible_target_frames", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_assist_target_visible_sample_count",
            "value": gameplay_assist.get("target_visible_sample_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_assist_steering_frames",
            "value": gameplay_assist.get("steering_frames", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_assist_steering_sample_count",
            "value": gameplay_assist.get("steering_sample_count", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_assist_attack_visible_frames",
            "value": gameplay_assist.get("attack_visible_frames", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_assist_mode_max",
            "value": gameplay_assist.get("mode_max", 0),
            "path": str(summary_path),
        },
        {
            "kind": "runtime_state",
            "name": "noesis_assist_target_distance_min",
            "value": gameplay_assist.get("target_distance_min"),
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
            "name": "noesis_gameplay_outcomes_file",
            "value": (summary.get("inputs") or {}).get("gameplay_outcomes", ""),
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
    parser.add_argument("--gameplay-outcomes", type=Path)
    parser.add_argument("--trace-summary", type=Path)
    parser.add_argument("--frames-dir", type=Path)
    parser.add_argument("--plan", default="")
    parser.add_argument("--player", default="")
    parser.add_argument("--min-actions", type=int, default=1)
    parser.add_argument("--min-commands", type=int, default=1)
    parser.add_argument("--min-frames", type=int, default=0)
    parser.add_argument("--min-frame-mae", type=float)
    parser.add_argument("--min-log-phases", type=int, default=0)
    parser.add_argument("--min-phase-outcomes", type=int, default=0)
    parser.add_argument("--min-gameplay-samples", type=int, default=0)
    parser.add_argument("--min-route-distance", type=float, default=64.0)
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
