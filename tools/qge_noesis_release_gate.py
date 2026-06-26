#!/usr/bin/env python3
"""Build a release gate for bounded Noesis autonomous diagnostics.

This gate is scoped to the claim in docs/claims/qge_claims.json:
Noesis can run bounded no-script autonomous diagnostics with reactive
server-side exploration and combat telemetry.  It does not authorize claims
that Noesis has learned to play Quake or owns a robust map-level world model.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


PASS = "pass"
BLOCKED = "blocked"
READY_STATUS = "ready_for_noesis_autonomous_diagnostics_claim"
MIN_QUALITY_SCORE = 35.0
MIN_SAMPLE_COUNT = 2
MIN_ROUTE_DISTANCE = 64.0
CLAIM_ID = "ai.noesis_autonomous_diagnostics"
ALLOWED_WORDING = (
    "Noesis can run bounded no-script autonomous diagnostics with reactive "
    "server-side exploration and combat telemetry."
)
DISALLOWED_WORDING = (
    "Noesis has learned to play Quake or has a robust map-level world model."
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def bool_true(value: Any) -> bool:
    return value is True or value == 1


def number_value(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_json_object(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def load_json_list(path: Path) -> list[Any]:
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError(f"{path} did not contain a JSON array")
    return data


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def count_nonempty_lines(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 0
    return sum(1 for line in path.read_text(
        encoding="utf-8", errors="replace").splitlines() if line.strip())


def read_jsonl_shape(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "exists": False,
            "line_count": 0,
            "sample_count": 0,
            "parse_error_count": 0,
        }
    line_count = 0
    sample_count = 0
    parse_error_count = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            line_count += 1
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                parse_error_count += 1
                continue
            if isinstance(item, dict) and item.get("type") == "sample":
                sample_count += 1
    return {
        "exists": True,
        "line_count": line_count,
        "sample_count": sample_count,
        "parse_error_count": parse_error_count,
    }


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


def resolve_existing_path(raw: Any, *, base_dir: Path | None = None) -> Path | None:
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    if path.is_absolute() or path.exists() or base_dir is None:
        return path
    candidate = base_dir / path
    return candidate if candidate.exists() else path


def publication_manifest_path(path: Path) -> Path | None:
    if path.is_file() and path.name == "publication_manifest.json":
        return path
    candidate = path / "publication_manifest.json"
    return candidate if candidate.is_file() else None


def agent_stream_dir_from_path(path: Path) -> Path | None:
    manifest_path = publication_manifest_path(path)
    if manifest_path is not None:
        pack_dir = manifest_path.parent
        candidate = pack_dir / "agent_stream"
        if candidate.is_dir():
            return candidate
        manifest = load_json_object(manifest_path)
        artifact = dict_or_empty(
            dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(
                "agent_stream")).get("stream_directory"))
        packed_path = dict_or_empty(artifact.get("packed")).get("path")
        resolved = resolve_existing_path(packed_path, base_dir=pack_dir)
        return resolved if resolved is not None and resolved.is_dir() else None
    if (path / "manifest.json").is_file():
        return path
    if (path / "agent_stream" / "manifest.json").is_file():
        return path / "agent_stream"
    return None


def claims_path_from_path(path: Path) -> Path | None:
    manifest_path = publication_manifest_path(path)
    if manifest_path is not None:
        candidate = manifest_path.parent / "source" / "docs" / "qge_claims.json"
        if candidate.is_file():
            return candidate
    candidate = path / "source" / "docs" / "qge_claims.json"
    if candidate.is_file():
        return candidate
    repo_candidate = Path(__file__).resolve().parents[1] / "docs" / "claims" / "qge_claims.json"
    return repo_candidate if repo_candidate.is_file() else None


def noesis_paths(agent_stream_dir: Path | None) -> dict[str, Path | None]:
    if agent_stream_dir is None:
        return {
            "manifest": None,
            "summary": None,
            "icc_evidence": None,
            "gameplay_outcomes": None,
            "actions": None,
            "commands": None,
        }
    return {
        "manifest": agent_stream_dir / "manifest.json",
        "summary": agent_stream_dir / "noesis" / "qge_noesis_summary.json",
        "icc_evidence": (
            agent_stream_dir / "noesis" / "qge_noesis_icc_evidence.json"),
        "gameplay_outcomes": (
            agent_stream_dir / "noesis" / "gameplay_outcomes.ndjson"),
        "actions": agent_stream_dir / "input" / "noesis_actions.txt",
        "commands": agent_stream_dir / "input" / "noesis_commands.cfg",
    }


def load_optional_json_object(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    return load_json_object(path)


def load_optional_icc_list(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    return [
        item for item in load_json_list(path)
        if isinstance(item, dict)
    ]


def icc_values(entries: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for entry in entries:
        name = entry.get("name")
        if isinstance(name, str):
            values[name] = entry.get("value")
    return values


def claim_policy_summary(claims: dict[str, Any]) -> dict[str, Any]:
    claims_list = list_or_empty(claims.get("claims"))
    for item in claims_list:
        claim = dict_or_empty(item)
        if claim.get("claim_id") == CLAIM_ID:
            return {
                "claim_found": True,
                "claim_id": CLAIM_ID,
                "allowed_wording": claim.get("allowed_wording"),
                "disallowed_wording": claim.get("disallowed_wording"),
                "required_trace_fields": claim.get("required_trace_fields"),
            }
    return {
        "claim_found": False,
        "claim_id": CLAIM_ID,
        "allowed_wording": None,
        "disallowed_wording": None,
        "required_trace_fields": None,
    }


def action_trace_metadata_only(actions: dict[str, Any],
                               actions_path: Path | None) -> bool:
    if not bool_true(actions.get("exists")) and actions_path is not None:
        return False
    if int_value(actions.get("line_count")) == 0:
        return True
    if count_nonempty_lines(actions_path) == 0:
        return True
    return (
        int_value(actions.get("movement_action_count")) == 0 and
        int_value(actions.get("combat_action_count")) == 0 and
        int_value(actions.get("route_action_count")) == 0 and
        int_value(actions.get("policy_marker_count")) == 0 and
        not dict_or_empty(actions.get("verb_counts"))
    )


def gate_summary(
    summary: dict[str, Any],
    icc: list[dict[str, Any]],
    gameplay_shape: dict[str, Any],
    claim_policy: dict[str, Any],
) -> dict[str, Any]:
    inputs = dict_or_empty(summary.get("inputs"))
    actions = dict_or_empty(summary.get("actions"))
    commands = dict_or_empty(summary.get("commands"))
    gameplay = dict_or_empty(summary.get("gameplay"))
    route = dict_or_empty(gameplay.get("route"))
    combat = dict_or_empty(gameplay.get("combat"))
    assist = dict_or_empty(gameplay.get("assist"))
    player = dict_or_empty(gameplay.get("player"))
    score = dict_or_empty(summary.get("gameplay_score"))
    trace = dict_or_empty(summary.get("trace"))
    return {
        "agent_stream_noesis_status": summary.get("status"),
        "map": summary.get("map"),
        "player": summary.get("player"),
        "plan": summary.get("plan"),
        "claim_scope": inputs.get("claim_scope"),
        "noesis_scripted": bool(inputs.get("noesis_scripted", 0)),
        "noesis_autonomous": bool(inputs.get("noesis_autonomous", 0)),
        "noesis_autonomous_control": bool(inputs.get("autonomous_control")),
        "action_trace_line_count": actions.get("line_count"),
        "command_line_count": commands.get("line_count"),
        "frame_count": dict_or_empty(summary.get("frames")).get(
            "frame_count"),
        "gameplay_quality_score": score.get("score"),
        "gameplay_quality_grade": score.get("grade"),
        "gameplay_outcome_sample_count": gameplay.get("sample_count"),
        "gameplay_outcome_line_count": gameplay_shape.get("line_count"),
        "gameplay_outcome_parse_error_count": (
            gameplay_shape.get("parse_error_count")),
        "total_distance": route.get("total_distance"),
        "max_displacement": route.get("max_displacement_from_start"),
        "terminal_stall": route.get("terminal_stall"),
        "survived": player.get("survived"),
        "visible_enemy_frames": combat.get("visible_enemy_frames"),
        "attack_active_frames": combat.get("attack_active_frames"),
        "damage_dealt_inferred": combat.get("damage_dealt_inferred"),
        "kills": combat.get("kills"),
        "assist_telemetry_sample_count": assist.get("telemetry_sample_count"),
        "assist_active_sample_count": assist.get("active_sample_count"),
        "assist_target_locked_sample_count": (
            assist.get("target_locked_sample_count")),
        "assist_target_visible_sample_count": (
            assist.get("target_visible_sample_count")),
        "assist_movement_injected_sample_count": (
            assist.get("movement_injected_sample_count")),
        "assist_view_injected_sample_count": (
            assist.get("view_injected_sample_count")),
        "ai_decision_count": trace.get("ai_decision_count"),
        "icc_evidence_entry_count": len(icc),
        "claim_policy_found": claim_policy.get("claim_found"),
        "claim_allowed_wording": claim_policy.get("allowed_wording"),
        "claim_disallowed_wording": claim_policy.get("disallowed_wording"),
    }


def build_criteria(
    *,
    summary: dict[str, Any],
    icc: list[dict[str, Any]],
    gameplay_shape: dict[str, Any],
    claims: dict[str, Any],
    paths: dict[str, Path | None],
) -> list[dict[str, Any]]:
    inputs = dict_or_empty(summary.get("inputs"))
    actions = dict_or_empty(summary.get("actions"))
    commands = dict_or_empty(summary.get("commands"))
    frames = dict_or_empty(summary.get("frames"))
    gameplay = dict_or_empty(summary.get("gameplay"))
    route = dict_or_empty(gameplay.get("route"))
    combat = dict_or_empty(gameplay.get("combat"))
    assist = dict_or_empty(gameplay.get("assist"))
    player = dict_or_empty(gameplay.get("player"))
    score = dict_or_empty(summary.get("gameplay_score"))
    run = dict_or_empty(summary.get("run"))
    icc_by_name = icc_values(icc)
    policy = claim_policy_summary(claims)
    artifact_statuses = {
        name: bool(path and path.is_file())
        for name, path in paths.items()
    }
    artifacts_present = all(artifact_statuses.values())
    claim_policy_ready = (
        policy.get("claim_found") is True and
        policy.get("allowed_wording") == ALLOWED_WORDING and
        policy.get("disallowed_wording") == DISALLOWED_WORDING
    )
    no_script_ready = (
        summary.get("player") == "noesis" and
        not bool(inputs.get("noesis_scripted", 0)) and
        bool(inputs.get("noesis_autonomous", 0)) and
        bool(inputs.get("autonomous_control", False)) and
        action_trace_metadata_only(actions, paths.get("actions")) and
        int_value(actions.get("policy_marker_count")) == 0 and
        int_value(commands.get("policy_marker_count")) == 0
    )
    summary_ready = (
        summary.get("schema") == "qge.noesis_summary.v0" and
        summary.get("status") == PASS and
        not list_or_empty(summary.get("failures")) and
        run.get("status") == "ok" and
        int_value(frames.get("frame_count")) > 0 and
        bool_true(commands.get("player_start_present")) and
        bool_true(commands.get("player_done_present"))
    )
    route_ready = (
        bool_true(gameplay.get("exists")) and
        int_value(gameplay.get("sample_count")) >= MIN_SAMPLE_COUNT and
        int_value(gameplay.get("parse_error_count")) == 0 and
        gameplay_shape.get("exists") is True and
        int_value(gameplay_shape.get("sample_count")) >= MIN_SAMPLE_COUNT and
        int_value(gameplay_shape.get("parse_error_count")) == 0 and
        number_value(route.get("total_distance")) >= MIN_ROUTE_DISTANCE and
        number_value(route.get("max_displacement_from_start")) > 0.0 and
        route.get("terminal_stall") is False and
        player.get("survived") is True
    )
    combat_ready = (
        number_value(combat.get("visible_enemy_frames")) > 0.0 and
        number_value(combat.get("attack_active_frames")) > 0.0 and
        (
            number_value(combat.get("damage_dealt_inferred")) > 0.0 or
            number_value(combat.get("kills")) > 0.0
        ) and
        number_value(assist.get("telemetry_sample_count")) > 0.0 and
        number_value(assist.get("active_sample_count")) > 0.0 and
        (
            number_value(assist.get("target_locked_sample_count")) > 0.0 or
            number_value(assist.get("target_visible_sample_count")) > 0.0
        ) and
        (
            number_value(assist.get("movement_injected_sample_count")) > 0.0 or
            number_value(assist.get("view_injected_sample_count")) > 0.0
        )
    )
    score_ready = (
        number_value(score.get("score")) >= MIN_QUALITY_SCORE and
        score.get("grade") != "blocked_by_gates" and
        not list_or_empty(score.get("blocking_gates")) and
        score.get("outcome_telemetry_present") is True and
        score.get("assist_telemetry_present") is True
    )
    icc_ready = (
        len(icc) > 0 and
        icc_by_name.get("runtime_backend") == "qge_noesis_summary" and
        icc_by_name.get("completion_reason") == "qge_noesis_summary_complete" and
        icc_by_name.get("noesis_summary_status") == PASS and
        icc_by_name.get("noesis_failure_free") is True and
        icc_by_name.get("noesis_scripted") is False and
        icc_by_name.get("noesis_autonomous") is True and
        icc_by_name.get("noesis_autonomous_control") is True and
        int_value(icc_by_name.get("noesis_gameplay_outcome_sample_count")) >=
        MIN_SAMPLE_COUNT and
        number_value(icc_by_name.get("noesis_gameplay_total_distance")) >=
        MIN_ROUTE_DISTANCE and
        icc_by_name.get("noesis_gameplay_terminal_stall") is False
    )
    guardrail_ready = (
        dict_or_empty(summary.get("claim_gates")).get(
            "unassisted_claim_supported") is False and
        inputs.get("claim_scope") in {"server_autonomous", "server_assisted"} and
        not bool(inputs.get("learned_policy_claimed", False)) and
        not bool(inputs.get("map_level_world_model_claimed", False))
    )
    return [
        criterion(
            "noesis_artifacts_present",
            "Packed Noesis summary, ICC, actions, commands, and outcomes exist",
            artifacts_present,
            "one or more Noesis artifacts are missing",
            artifacts=artifact_statuses,
        ),
        criterion(
            "noesis_claim_policy_bound",
            "Noesis release claim matches the bounded diagnostics policy",
            claim_policy_ready,
            "Noesis claim policy is missing or has unexpected wording",
            claim_id=policy.get("claim_id"),
            claim_found=policy.get("claim_found"),
            allowed_wording=policy.get("allowed_wording"),
            disallowed_wording=policy.get("disallowed_wording"),
        ),
        criterion(
            "noesis_no_script_autonomous_scope",
            "Noesis run is no-script, autonomous, and server controlled",
            no_script_ready,
            "Noesis run is scripted or lacks autonomous-control evidence",
            player=summary.get("player"),
            noesis_scripted=inputs.get("noesis_scripted"),
            noesis_autonomous=inputs.get("noesis_autonomous"),
            autonomous_control=inputs.get("autonomous_control"),
            action_trace_line_count=actions.get("line_count"),
            action_trace_metadata_only=action_trace_metadata_only(
                actions, paths.get("actions")),
            action_policy_marker_count=actions.get("policy_marker_count"),
            command_policy_marker_count=commands.get("policy_marker_count"),
        ),
        criterion(
            "noesis_summary_passed",
            "Noesis reducer passed with a completed player run",
            summary_ready,
            "Noesis summary is blocked, incomplete, or missing player markers",
            schema=summary.get("schema"),
            status=summary.get("status"),
            failures=summary.get("failures"),
            run_status=run.get("status"),
            frame_count=frames.get("frame_count"),
            player_start_present=commands.get("player_start_present"),
            player_done_present=commands.get("player_done_present"),
        ),
        criterion(
            "noesis_route_and_survival_telemetry",
            "Noesis gameplay outcomes show route movement without terminal stall",
            route_ready,
            "Noesis route/survival telemetry is missing or stalled",
            sample_count=gameplay.get("sample_count"),
            jsonl_sample_count=gameplay_shape.get("sample_count"),
            parse_error_count=gameplay.get("parse_error_count"),
            jsonl_parse_error_count=gameplay_shape.get("parse_error_count"),
            total_distance=route.get("total_distance"),
            max_displacement=route.get("max_displacement_from_start"),
            terminal_stall=route.get("terminal_stall"),
            survived=player.get("survived"),
        ),
        criterion(
            "noesis_combat_and_assist_telemetry",
            "Noesis outcomes include combat and assist telemetry",
            combat_ready,
            "Noesis combat or assist telemetry is insufficient",
            visible_enemy_frames=combat.get("visible_enemy_frames"),
            attack_active_frames=combat.get("attack_active_frames"),
            damage_dealt_inferred=combat.get("damage_dealt_inferred"),
            kills=combat.get("kills"),
            assist_telemetry_sample_count=assist.get(
                "telemetry_sample_count"),
            assist_active_sample_count=assist.get("active_sample_count"),
            assist_target_locked_sample_count=assist.get(
                "target_locked_sample_count"),
            assist_target_visible_sample_count=assist.get(
                "target_visible_sample_count"),
            assist_movement_injected_sample_count=assist.get(
                "movement_injected_sample_count"),
            assist_view_injected_sample_count=assist.get(
                "view_injected_sample_count"),
        ),
        criterion(
            "noesis_quality_score_ready",
            "Noesis gameplay quality score clears the release threshold",
            score_ready,
            "Noesis gameplay quality score or telemetry gates are insufficient",
            min_quality_score=MIN_QUALITY_SCORE,
            gameplay_quality_score=score.get("score"),
            gameplay_quality_grade=score.get("grade"),
            blocking_gates=score.get("blocking_gates"),
            outcome_telemetry_present=score.get("outcome_telemetry_present"),
            assist_telemetry_present=score.get("assist_telemetry_present"),
        ),
        criterion(
            "noesis_icc_evidence_consistent",
            "Noesis ICC sidecar mirrors autonomous gameplay evidence",
            icc_ready,
            "Noesis ICC sidecar is missing or inconsistent",
            icc_evidence_entry_count=len(icc),
            runtime_backend=icc_by_name.get("runtime_backend"),
            completion_reason=icc_by_name.get("completion_reason"),
            noesis_summary_status=icc_by_name.get("noesis_summary_status"),
            noesis_scripted=icc_by_name.get("noesis_scripted"),
            noesis_autonomous=icc_by_name.get("noesis_autonomous"),
            noesis_autonomous_control=icc_by_name.get(
                "noesis_autonomous_control"),
            noesis_gameplay_outcome_sample_count=icc_by_name.get(
                "noesis_gameplay_outcome_sample_count"),
            noesis_gameplay_total_distance=icc_by_name.get(
                "noesis_gameplay_total_distance"),
        ),
        criterion(
            "noesis_no_learning_overclaim",
            "Noesis gate forbids learned-play and world-model claims",
            guardrail_ready,
            "Noesis inputs or claim gates imply an unapproved overclaim",
            claim_scope=inputs.get("claim_scope"),
            unassisted_claim_supported=dict_or_empty(
                summary.get("claim_gates")).get(
                    "unassisted_claim_supported"),
            learned_policy_claimed=inputs.get("learned_policy_claimed"),
            map_level_world_model_claimed=inputs.get(
                "map_level_world_model_claimed"),
        ),
    ]


def next_actions_for_blockers(blockers: list[dict[str, Any]]) -> list[str]:
    if not blockers:
        return [
            "Publish the Noesis gate JSON, Markdown, and ICC sidecar with the release pack.",
            "Use only the bounded autonomous diagnostics wording from the claims ledger.",
        ]
    actions = []
    for blocker in blockers:
        blocker_id = blocker.get("id")
        if blocker_id == "noesis_artifacts_present":
            actions.append(
                "Regenerate the agent stream with Noesis summary, ICC, action, command, and gameplay outcome sidecars.")
        elif blocker_id == "noesis_claim_policy_bound":
            actions.append(
                "Restore the ai.noesis_autonomous_diagnostics claim ledger entry.")
        elif blocker_id == "noesis_no_script_autonomous_scope":
            actions.append(
                "Rerun Noesis with QGE_NOESIS_SCRIPTED=0 and autonomous server assist enabled.")
        elif blocker_id == "noesis_summary_passed":
            actions.append(
                "Rerun tools/qge_noesis_summary.py until the reducer status is pass.")
        elif blocker_id == "noesis_route_and_survival_telemetry":
            actions.append(
                "Capture a longer Noesis run with gameplay_outcomes.ndjson route samples and no terminal stall.")
        elif blocker_id == "noesis_combat_and_assist_telemetry":
            actions.append(
                "Capture a Noesis run with visible target engagement and assist telemetry.")
        elif blocker_id == "noesis_quality_score_ready":
            actions.append(
                "Improve route/combat/assist evidence until the Noesis quality score clears the release threshold.")
        elif blocker_id == "noesis_icc_evidence_consistent":
            actions.append(
                "Regenerate qge_noesis_icc_evidence.json from the current Noesis summary.")
        elif blocker_id == "noesis_no_learning_overclaim":
            actions.append(
                "Remove any learned-play or robust world-model claim from Noesis release wording.")
    return actions


def build_gate(
    summary: dict[str, Any],
    icc: list[dict[str, Any]],
    claims: dict[str, Any],
    gameplay_shape: dict[str, Any],
    paths: dict[str, Path | None],
    *,
    source_path: Path | str | None = None,
) -> dict[str, Any]:
    policy = claim_policy_summary(claims)
    criteria = build_criteria(
        summary=summary,
        icc=icc,
        gameplay_shape=gameplay_shape,
        claims=claims,
        paths=paths,
    )
    blockers = failed_criteria(criteria)
    claim_allowed = not blockers
    return {
        "schema": "qge.noesis_release_gate.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path) if source_path is not None else None,
        "status": READY_STATUS if claim_allowed else "blocked",
        "claim_id": CLAIM_ID,
        "noesis_autonomous_diagnostics_claim_allowed": claim_allowed,
        "learned_play_claim_allowed": False,
        "robust_map_level_world_model_claim_allowed": False,
        "unassisted_general_play_claim_allowed": False,
        "failed_criterion_count": len(blockers),
        "blocker_count": len(blockers),
        "criteria": criteria,
        "blockers": blockers,
        "summary": gate_summary(summary, icc, gameplay_shape, policy),
        "next_actions": next_actions_for_blockers(blockers),
        "limits": [
            ALLOWED_WORDING,
            "This gate is not evidence that Noesis learned to play Quake.",
            "This gate is not evidence of a robust map-level world model.",
            "This gate is not a quantum hardware or Moonlab deployment claim.",
        ],
    }


def build_gate_from_agent_stream(
    agent_stream_dir: Path | None,
    *,
    claims_path: Path | None = None,
    source_path: Path | str | None = None,
) -> dict[str, Any]:
    paths = noesis_paths(agent_stream_dir)
    summary = load_optional_json_object(paths.get("summary"))
    icc = load_optional_icc_list(paths.get("icc_evidence"))
    claims = load_optional_json_object(claims_path)
    gameplay_shape = read_jsonl_shape(paths.get("gameplay_outcomes"))
    return build_gate(
        summary,
        icc,
        claims,
        gameplay_shape,
        paths,
        source_path=source_path if source_path is not None else agent_stream_dir,
    )


def build_gate_from_path(
    path: Path,
    *,
    claims_path: Path | None = None,
) -> dict[str, Any]:
    agent_stream_dir = agent_stream_dir_from_path(path)
    resolved_claims = claims_path or claims_path_from_path(path)
    return build_gate_from_agent_stream(
        agent_stream_dir,
        claims_path=resolved_claims,
        source_path=path,
    )


def build_icc_evidence(
    gate: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    summary = dict_or_empty(gate.get("summary"))
    claim_allowed = gate.get("noesis_autonomous_diagnostics_claim_allowed")
    completion_reason = "qge_noesis_release_gate_blocked"
    if claim_allowed is True:
        completion_reason = "qge_noesis_release_gate_ready"
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_noesis_release_gate",
        "completion_reason": completion_reason,
        "status": "success",
        "noesis_release_gate_file": str(out_path) if out_path else None,
        "gate_status": gate.get("status"),
        "failed_criterion_count": gate.get("failed_criterion_count"),
        "blocker_count": gate.get("blocker_count"),
        "claim_id": gate.get("claim_id"),
        "agent_stream_noesis_status": summary.get(
            "agent_stream_noesis_status"),
        "noesis_release_claim_allowed": claim_allowed,
        "noesis_autonomous_diagnostics_claim_allowed": claim_allowed,
        "noesis_learned_play_claim_allowed": False,
        "noesis_robust_map_level_world_model_claim_allowed": False,
        "noesis_unassisted_general_play_claim_allowed": False,
        "noesis_map": summary.get("map"),
        "noesis_player": summary.get("player"),
        "noesis_plan": summary.get("plan"),
        "noesis_claim_scope": summary.get("claim_scope"),
        "noesis_scripted": summary.get("noesis_scripted"),
        "noesis_autonomous": summary.get("noesis_autonomous"),
        "noesis_autonomous_control": summary.get(
            "noesis_autonomous_control"),
        "noesis_action_trace_line_count": summary.get(
            "action_trace_line_count"),
        "noesis_command_line_count": summary.get("command_line_count"),
        "noesis_frame_count": summary.get("frame_count"),
        "noesis_gameplay_quality_score": summary.get(
            "gameplay_quality_score"),
        "noesis_gameplay_quality_grade": summary.get(
            "gameplay_quality_grade"),
        "noesis_gameplay_outcome_sample_count": summary.get(
            "gameplay_outcome_sample_count"),
        "noesis_gameplay_total_distance": summary.get("total_distance"),
        "noesis_gameplay_max_displacement": summary.get(
            "max_displacement"),
        "noesis_gameplay_terminal_stall": summary.get("terminal_stall"),
        "noesis_gameplay_survived": summary.get("survived"),
        "noesis_gameplay_visible_enemy_frames": summary.get(
            "visible_enemy_frames"),
        "noesis_gameplay_attack_active_frames": summary.get(
            "attack_active_frames"),
        "noesis_gameplay_damage_dealt_inferred": summary.get(
            "damage_dealt_inferred"),
        "noesis_gameplay_kills": summary.get("kills"),
        "noesis_assist_telemetry_sample_count": summary.get(
            "assist_telemetry_sample_count"),
        "noesis_assist_active_sample_count": summary.get(
            "assist_active_sample_count"),
        "noesis_assist_target_locked_sample_count": summary.get(
            "assist_target_locked_sample_count"),
        "noesis_ai_decision_count": summary.get("ai_decision_count"),
        "noesis_claim_allowed_wording": summary.get(
            "claim_allowed_wording"),
        "noesis_claim_disallowed_wording": summary.get(
            "claim_disallowed_wording"),
    }


def markdown_report(gate: dict[str, Any]) -> str:
    summary = dict_or_empty(gate.get("summary"))
    lines = [
        "# QGE Noesis Release Gate",
        "",
        f"Status: {gate.get('status')}",
        "",
        "| Claim | Allowed |",
        "| --- | ---: |",
        (
            "| bounded no-script autonomous diagnostics | "
            f"{str(gate.get('noesis_autonomous_diagnostics_claim_allowed')).lower()} |"
        ),
        (
            "| learned Quake play | "
            f"{str(gate.get('learned_play_claim_allowed')).lower()} |"
        ),
        (
            "| robust map-level world model | "
            f"{str(gate.get('robust_map_level_world_model_claim_allowed')).lower()} |"
        ),
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| map | {summary.get('map')} |",
        f"| quality score | {summary.get('gameplay_quality_score')} |",
        f"| quality grade | {summary.get('gameplay_quality_grade')} |",
        f"| outcome samples | {summary.get('gameplay_outcome_sample_count')} |",
        f"| route distance | {summary.get('total_distance')} |",
        f"| kills | {summary.get('kills')} |",
        f"| assist telemetry samples | {summary.get('assist_telemetry_sample_count')} |",
        "",
        (
            "Allowed wording: "
            f"{summary.get('claim_allowed_wording') or ALLOWED_WORDING}"
        ),
        (
            "Disallowed wording: "
            f"{summary.get('claim_disallowed_wording') or DISALLOWED_WORDING}"
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
    parser = argparse.ArgumentParser(
        description="Build the QGE Noesis release diagnostics gate")
    parser.add_argument(
        "path",
        type=Path,
        help="publication pack directory, publication manifest, or agent stream directory",
    )
    parser.add_argument(
        "--claims",
        type=Path,
        default=None,
        help="claims ledger override")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--icc-json", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        gate = build_gate_from_path(args.path, claims_path=args.claims)
        write_json(args.out, gate)
        if args.markdown is not None:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(gate), encoding="utf-8")
        if args.icc_json is not None:
            write_json(
                args.icc_json,
                build_icc_evidence(gate, out_path=args.out),
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"qge_noesis_release_gate: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_NOESIS_RELEASE_GATE {args.out}")
    if args.markdown is not None:
        print(f"QGE_NOESIS_RELEASE_GATE_MARKDOWN {args.markdown}")
    if args.icc_json is not None:
        print(f"QGE_NOESIS_RELEASE_GATE_ICC {args.icc_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
