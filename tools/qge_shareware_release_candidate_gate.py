#!/usr/bin/env python3
"""Build the final shareware release-candidate gate for QGE.

This gate composes the generated publication pack, the postpack audit, the
shareware Moonlab deployment gate, the bounded Noesis diagnostics gate, and the
registered full-game deployment guardrail.  It is deliberately a postpack tool:
requiring qge_postpack_audit.py inside qge_publication_pack.py would create a
cycle because postpack output only exists after the pack has been generated.
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

import qge_manifest_claim_policy_audit  # noqa: E402
import qge_map_sets  # noqa: E402
import qge_moonlab_deployment_gate  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402
import qge_moonlab_shareware_deployment_gate  # noqa: E402
import qge_noesis_release_gate  # noqa: E402


PASS = "pass"
BLOCKED = "blocked"
READY_STATUS = "ready_for_shareware_release_candidate"
SHAREWARE_MAP_SET = qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET
CLAIM_ALLOWED_WORDING = (
    "Shareware release candidate evidence is ready for Quake shareware "
    "Episode 1 in the Moonlab simulator/native path, with bounded Noesis "
    "no-script autonomous diagnostics evidence."
)
CLAIM_DISALLOWED_WORDING = (
    "This is not a registered full-game release claim, not hardware execution, "
    "not hardware quantum advantage, not a dense state-vector claim, and not a "
    "claim that Noesis learned to play Quake."
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def bool_true(value: Any) -> bool:
    return value is True or value == 1


def int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def number_value(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


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


def artifact_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    manifest_path: Path | None = None,
) -> Path | None:
    section_data = dict_or_empty(
        dict_or_empty(manifest.get("artifacts")).get(section))
    artifact = dict_or_empty(section_data.get(name))
    raw_path = artifact.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raw_path = dict_or_empty(artifact.get("packed")).get("path")
    base_dir = manifest_path.parent if manifest_path is not None else None
    return qge_moonlab_full_game_plan.resolve_path(raw_path, base_dir=base_dir)


def load_artifact_json(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    path = artifact_path(
        manifest, section, name, manifest_path=manifest_path)
    if path is None or not path.is_file():
        return {}
    return load_json_object(path)


def publication_icc_path(manifest_path: Path) -> Path:
    return manifest_path.parent / "qge_publication_icc_evidence.json"


def postpack_audit_path(manifest_path: Path) -> Path:
    return manifest_path.parent / "qge_postpack_audit.json"


def load_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    return load_json_object(path)


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


def publication_summary(
    manifest: dict[str, Any],
    publication_icc: dict[str, Any],
    postpack_audit: dict[str, Any],
    shareware_gate: dict[str, Any],
    noesis_gate: dict[str, Any],
    full_game_gate: dict[str, Any],
    claim_policy_audit: dict[str, Any],
) -> dict[str, Any]:
    runtime = dict_or_empty(manifest.get("runtime_summary"))
    shareware_summary = dict_or_empty(shareware_gate.get("summary"))
    noesis_summary = dict_or_empty(noesis_gate.get("summary"))
    full_summary = dict_or_empty(full_game_gate.get("summary"))
    return {
        "publication_status": manifest.get("status"),
        "publication_ready_for_complete_claim": runtime.get(
            "publication_ready_for_complete_claim"),
        "publication_icc_completion_reason": publication_icc.get(
            "completion_reason"),
        "postpack_passed": postpack_audit.get("passed"),
        "postpack_failed_count": postpack_audit.get("failed_count"),
        "postpack_mismatch_count_total": postpack_audit.get(
            "mismatch_count_total"),
        "postpack_manifest_command_count": postpack_audit.get(
            "manifest_postpack_command_count"),
        "shareware_gate_status": shareware_gate.get("status"),
        "shareware_map_set": shareware_gate.get("map_set"),
        "shareware_target_map_count": shareware_summary.get(
            "target_map_count"),
        "shareware_covered_map_count": shareware_summary.get(
            "covered_map_count"),
        "shareware_native_bridge_count": shareware_summary.get(
            "total_native_bridge_count"),
        "shareware_fallback_count": shareware_summary.get(
            "total_fallback_count"),
        "shareware_surrogate_count": shareware_summary.get(
            "total_surrogate_count"),
        "shareware_cpu_idwt_count": shareware_summary.get(
            "total_cpu_idwt_count"),
        "noesis_gate_status": noesis_gate.get("status"),
        "noesis_claim_scope": noesis_summary.get("claim_scope"),
        "noesis_quality_score": noesis_summary.get(
            "gameplay_quality_score"),
        "noesis_quality_grade": noesis_summary.get(
            "gameplay_quality_grade"),
        "noesis_outcome_sample_count": noesis_summary.get(
            "gameplay_outcome_sample_count"),
        "noesis_total_distance": noesis_summary.get("total_distance"),
        "noesis_kills": noesis_summary.get("kills"),
        "registered_full_game_gate_status": full_game_gate.get("status"),
        "registered_full_game_gate_blocker_count": full_game_gate.get(
            "blocker_count"),
        "registered_full_game_asset_missing_map_count": full_summary.get(
            "asset_inventory_missing_map_count"),
        "manifest_claim_policy_passed": claim_policy_audit.get("passed"),
        "manifest_claim_policy_mismatch_count": claim_policy_audit.get(
            "mismatch_count"),
    }


def full_game_overclaim_flags(full_game_gate: dict[str, Any]) -> list[str]:
    flags = []
    for name in (
        "whole_game_moonlab_deployment_claim_allowed",
        "whole_game_hardware_execution_claim_allowed",
        "hardware_quantum_advantage_claim_allowed",
        "dense_70000_qubit_state_claim_allowed",
    ):
        if full_game_gate.get(name) is True:
            flags.append(name)
    return flags


def noesis_overclaim_flags(noesis_gate: dict[str, Any]) -> list[str]:
    flags = []
    for name in (
        "learned_play_claim_allowed",
        "robust_map_level_world_model_claim_allowed",
        "unassisted_general_play_claim_allowed",
    ):
        if noesis_gate.get(name) is True:
            flags.append(name)
    return flags


def build_criteria(
    *,
    manifest: dict[str, Any],
    publication_icc: dict[str, Any],
    postpack_audit: dict[str, Any],
    shareware_gate: dict[str, Any],
    noesis_gate: dict[str, Any],
    full_game_gate: dict[str, Any],
    claim_policy_audit: dict[str, Any],
) -> list[dict[str, Any]]:
    runtime = dict_or_empty(manifest.get("runtime_summary"))
    manifest_schema_ready = manifest.get("schema") == "qge.publication_pack.v0"
    publication_icc_ready = (
        publication_icc.get("schema") == "qge.icc_evidence.v0" and
        publication_icc.get("runtime_backend") == "qge_publication_pack" and
        publication_icc.get("completion_reason") ==
        "qge_publication_artifact_pack_complete"
    )
    publication_ready = (
        manifest_schema_ready and
        manifest.get("status") == "success" and
        bool_true(runtime.get("publication_ready_for_complete_claim")) and
        publication_icc_ready
    )

    postpack_ready = (
        postpack_audit.get("schema") == "qge.postpack_audit.v0" and
        postpack_audit.get("passed") is True and
        int_value(postpack_audit.get("failed_count")) == 0 and
        int_value(postpack_audit.get("mismatch_count_total")) == 0 and
        int_value(postpack_audit.get("load_error_count")) == 0 and
        int_value(postpack_audit.get("stale_output_error_count")) == 0 and
        int_value(postpack_audit.get("manifest_postpack_command_count")) >=
        int_value(postpack_audit.get("default_child_audit_count"), 1)
    )

    shareware_overclaim_ready = all(
        shareware_gate.get(name) is False
        for name in (
            "whole_game_moonlab_deployment_claim_allowed",
            "whole_game_hardware_execution_claim_allowed",
            "hardware_quantum_advantage_claim_allowed",
            "dense_70000_qubit_state_claim_allowed",
        )
    )
    shareware_ready = (
        shareware_gate.get("schema") ==
        "qge.moonlab_shareware_deployment_gate.v0" and
        shareware_gate.get("status") ==
        qge_moonlab_shareware_deployment_gate.READY_STATUS and
        shareware_gate.get("shareware_moonlab_deployment_claim_allowed")
        is True and
        shareware_gate.get("map_set") == SHAREWARE_MAP_SET and
        int_value(shareware_gate.get("blocker_count")) == 0 and
        shareware_overclaim_ready
    )

    noesis_summary = dict_or_empty(noesis_gate.get("summary"))
    noesis_wording_ready = (
        noesis_summary.get("claim_allowed_wording") ==
        qge_noesis_release_gate.ALLOWED_WORDING and
        noesis_summary.get("claim_disallowed_wording") ==
        qge_noesis_release_gate.DISALLOWED_WORDING
    )
    noesis_flags = noesis_overclaim_flags(noesis_gate)
    noesis_ready = (
        noesis_gate.get("schema") == "qge.noesis_release_gate.v0" and
        noesis_gate.get("status") == qge_noesis_release_gate.READY_STATUS and
        noesis_gate.get("noesis_autonomous_diagnostics_claim_allowed")
        is True and
        int_value(noesis_gate.get("blocker_count")) == 0 and
        noesis_wording_ready and
        not noesis_flags
    )

    full_game_flags = full_game_overclaim_flags(full_game_gate)
    full_game_guardrail_ready = (
        full_game_gate.get("schema") == "qge.moonlab_deployment_gate.v0" and
        full_game_gate.get("status") == BLOCKED and
        int_value(full_game_gate.get("blocker_count")) > 0 and
        not full_game_flags
    )

    manifest_claim_policy_ready = (
        claim_policy_audit.get("passed") is True and
        int_value(claim_policy_audit.get("mismatch_count")) == 0
    )

    return [
        criterion(
            "publication_artifact_pack_complete",
            "Publication pack completed with matching ICC evidence",
            publication_ready,
            "publication manifest or ICC sidecar is incomplete",
            manifest_schema=manifest.get("schema"),
            manifest_status=manifest.get("status"),
            publication_ready_for_complete_claim=runtime.get(
                "publication_ready_for_complete_claim"),
            publication_icc_runtime_backend=publication_icc.get(
                "runtime_backend"),
            publication_icc_completion_reason=publication_icc.get(
                "completion_reason"),
        ),
        criterion(
            "postpack_audit_passed",
            "Postpack audit suite passed after pack generation",
            postpack_ready,
            "postpack audit is missing, stale, or failed",
            postpack_schema=postpack_audit.get("schema"),
            postpack_passed=postpack_audit.get("passed"),
            failed_count=postpack_audit.get("failed_count"),
            mismatch_count_total=postpack_audit.get("mismatch_count_total"),
            manifest_postpack_command_count=postpack_audit.get(
                "manifest_postpack_command_count"),
            default_child_audit_count=postpack_audit.get(
                "default_child_audit_count"),
        ),
        criterion(
            "shareware_moonlab_gate_ready",
            "Shareware Moonlab deployment gate is ready and scoped to Episode 1",
            shareware_ready,
            "shareware Moonlab deployment gate is blocked or overclaims scope",
            schema=shareware_gate.get("schema"),
            gate_status=shareware_gate.get("status"),
            map_set=shareware_gate.get("map_set"),
            blocker_count=shareware_gate.get("blocker_count"),
            shareware_moonlab_deployment_claim_allowed=shareware_gate.get(
                "shareware_moonlab_deployment_claim_allowed"),
            shareware_overclaim_ready=shareware_overclaim_ready,
        ),
        criterion(
            "noesis_bounded_diagnostics_ready",
            "Noesis release gate allows only bounded autonomous diagnostics",
            noesis_ready,
            "Noesis diagnostics gate is blocked or exceeds bounded wording",
            schema=noesis_gate.get("schema"),
            gate_status=noesis_gate.get("status"),
            blocker_count=noesis_gate.get("blocker_count"),
            noesis_autonomous_diagnostics_claim_allowed=noesis_gate.get(
                "noesis_autonomous_diagnostics_claim_allowed"),
            noesis_wording_ready=noesis_wording_ready,
            noesis_overclaim_flags=noesis_flags,
            quality_score=noesis_summary.get("gameplay_quality_score"),
            quality_grade=noesis_summary.get("gameplay_quality_grade"),
        ),
        criterion(
            "registered_full_game_not_claimed",
            "Registered full-game Moonlab deployment remains blocked",
            full_game_guardrail_ready,
            "registered full-game or hardware claim is enabled",
            schema=full_game_gate.get("schema"),
            gate_status=full_game_gate.get("status"),
            blocker_count=full_game_gate.get("blocker_count"),
            full_game_overclaim_flags=full_game_flags,
        ),
        criterion(
            "manifest_claim_policy_safe",
            "Manifest claim posture keeps hardware and advantage claims disallowed",
            manifest_claim_policy_ready,
            "manifest claim posture is missing or unsafe",
            recorded=claim_policy_audit.get("recorded"),
            mismatch_count=claim_policy_audit.get("mismatch_count"),
            missing_fields=claim_policy_audit.get("missing_fields"),
            forbidden_allowed_phrases=claim_policy_audit.get(
                "forbidden_allowed_phrases"),
        ),
    ]


def next_actions_for_blockers(blockers: list[dict[str, Any]]) -> list[str]:
    if not blockers:
        return [
            "Publish the shareware release candidate evidence pack with this gate, postpack audit, and ICC sidecar.",
            "Keep the registered full-game release blocked until registered assets and full-game capture evidence are complete.",
        ]
    actions = []
    for blocker in blockers:
        blocker_id = blocker.get("id")
        if blocker_id == "publication_artifact_pack_complete":
            actions.append(
                "Regenerate the publication pack until qge_publication_icc_evidence reports qge_publication_artifact_pack_complete.")
        elif blocker_id == "postpack_audit_passed":
            actions.append(
                "Run tools/qge_postpack_audit.py on the generated pack and fix any child audit failures.")
        elif blocker_id == "shareware_moonlab_gate_ready":
            actions.append(
                "Regenerate the shareware Moonlab deployment gate for quake_shareware_episode1.")
        elif blocker_id == "noesis_bounded_diagnostics_ready":
            actions.append(
                "Regenerate the Noesis release gate with bounded no-script autonomous diagnostics wording only.")
        elif blocker_id == "registered_full_game_not_claimed":
            actions.append(
                "Clear registered full-game, hardware, advantage, or dense-state claim flags.")
        elif blocker_id == "manifest_claim_policy_safe":
            actions.append(
                "Restore manifest claim posture allowed/disallowed wording before release.")
    return actions


def build_gate(
    manifest: dict[str, Any],
    publication_icc: dict[str, Any],
    postpack_audit: dict[str, Any],
    shareware_gate: dict[str, Any],
    noesis_gate: dict[str, Any],
    full_game_gate: dict[str, Any],
    *,
    source_path: Path | str | None = None,
) -> dict[str, Any]:
    claim_policy_audit = qge_manifest_claim_policy_audit.manifest_claim_policy_audit(
        manifest,
        required=True,
    )
    criteria = build_criteria(
        manifest=manifest,
        publication_icc=publication_icc,
        postpack_audit=postpack_audit,
        shareware_gate=shareware_gate,
        noesis_gate=noesis_gate,
        full_game_gate=full_game_gate,
        claim_policy_audit=claim_policy_audit,
    )
    blockers = failed_criteria(criteria)
    release_allowed = not blockers
    return {
        "schema": "qge.shareware_release_candidate_gate.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path) if source_path is not None else None,
        "status": READY_STATUS if release_allowed else BLOCKED,
        "shareware_release_candidate_claim_allowed": release_allowed,
        "shareware_moonlab_deployment_claim_allowed": release_allowed,
        "noesis_autonomous_diagnostics_claim_allowed": (
            noesis_gate.get("noesis_autonomous_diagnostics_claim_allowed")
            is True and release_allowed),
        "whole_game_moonlab_deployment_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "hardware_quantum_advantage_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "learned_play_claim_allowed": False,
        "robust_map_level_world_model_claim_allowed": False,
        "unassisted_general_play_claim_allowed": False,
        "claim_allowed_wording": CLAIM_ALLOWED_WORDING,
        "claim_disallowed_wording": CLAIM_DISALLOWED_WORDING,
        "failed_criterion_count": len(blockers),
        "blocker_count": len(blockers),
        "criteria": criteria,
        "blockers": blockers,
        "summary": publication_summary(
            manifest,
            publication_icc,
            postpack_audit,
            shareware_gate,
            noesis_gate,
            full_game_gate,
            claim_policy_audit,
        ),
        "next_actions": next_actions_for_blockers(blockers),
        "limits": [
            CLAIM_ALLOWED_WORDING,
            CLAIM_DISALLOWED_WORDING,
            "This gate composes already-generated artifacts; it does not replace the pack postpack audit.",
            "The registered full-game release remains blocked until pak1/registered scope and full-game evidence are complete.",
        ],
    }


def build_gate_from_pack(
    pack_or_manifest: Path,
    *,
    postpack_path: Path | None = None,
) -> dict[str, Any]:
    manifest_path = qge_moonlab_full_game_plan.resolve_publication_manifest(
        pack_or_manifest)
    manifest = load_json_object(manifest_path)
    resolved_postpack_path = postpack_path or postpack_audit_path(
        manifest_path)
    return build_gate(
        manifest,
        load_optional_json(publication_icc_path(manifest_path)),
        load_optional_json(resolved_postpack_path),
        load_artifact_json(
            manifest,
            "resource",
            "moonlab_shareware_deployment_gate",
            manifest_path=manifest_path,
        ),
        load_artifact_json(
            manifest,
            "agent_stream",
            "noesis_release_gate",
            manifest_path=manifest_path,
        ),
        load_artifact_json(
            manifest,
            "resource",
            "moonlab_deployment_gate",
            manifest_path=manifest_path,
        ),
        source_path=manifest_path,
    )


def build_icc_evidence(
    gate: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    summary = dict_or_empty(gate.get("summary"))
    release_allowed = gate.get("shareware_release_candidate_claim_allowed")
    completion_reason = "qge_shareware_release_candidate_gate_blocked"
    if release_allowed is True:
        completion_reason = "qge_shareware_release_candidate_gate_ready"
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_shareware_release_candidate_gate",
        "completion_reason": completion_reason,
        "status": "success",
        "shareware_release_candidate_gate_file": (
            str(out_path) if out_path else None),
        "gate_status": gate.get("status"),
        "failed_criterion_count": gate.get("failed_criterion_count"),
        "blocker_count": gate.get("blocker_count"),
        "release_scope": SHAREWARE_MAP_SET,
        "runtime_backend_scope_map_set": SHAREWARE_MAP_SET,
        "map_set": summary.get("shareware_map_set"),
        "shareware_release_candidate_map_set": summary.get(
            "shareware_map_set"),
        "shareware_release_candidate_claim_allowed": release_allowed,
        "shareware_moonlab_deployment_claim_allowed": gate.get(
            "shareware_moonlab_deployment_claim_allowed"),
        "publication_ready_for_complete_claim": summary.get(
            "publication_ready_for_complete_claim"),
        "publication_icc_completion_reason": summary.get(
            "publication_icc_completion_reason"),
        "postpack_audit_passed": summary.get("postpack_passed"),
        "shareware_gate_status": summary.get("shareware_gate_status"),
        "shareware_target_map_count": summary.get(
            "shareware_target_map_count"),
        "shareware_covered_map_count": summary.get(
            "shareware_covered_map_count"),
        "shareware_native_bridge_count": summary.get(
            "shareware_native_bridge_count"),
        "shareware_fallback_count": summary.get("shareware_fallback_count"),
        "shareware_surrogate_count": summary.get("shareware_surrogate_count"),
        "shareware_cpu_idwt_count": summary.get("shareware_cpu_idwt_count"),
        "noesis_autonomous_diagnostics_claim_allowed": gate.get(
            "noesis_autonomous_diagnostics_claim_allowed"),
        "noesis_gate_status": summary.get("noesis_gate_status"),
        "noesis_claim_scope": summary.get("noesis_claim_scope"),
        "noesis_quality_score": summary.get("noesis_quality_score"),
        "noesis_quality_grade": summary.get("noesis_quality_grade"),
        "noesis_outcome_sample_count": summary.get(
            "noesis_outcome_sample_count"),
        "noesis_total_distance": summary.get("noesis_total_distance"),
        "noesis_kills": summary.get("noesis_kills"),
        "registered_full_game_deployment_gate_status": summary.get(
            "registered_full_game_gate_status"),
        "registered_full_game_deployment_gate_blocker_count": summary.get(
            "registered_full_game_gate_blocker_count"),
        "whole_game_moonlab_deployment_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "hardware_quantum_advantage_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "noesis_learned_play_claim_allowed": False,
        "noesis_robust_map_level_world_model_claim_allowed": False,
        "noesis_unassisted_general_play_claim_allowed": False,
        "claim_allowed_wording": gate.get("claim_allowed_wording"),
        "claim_disallowed_wording": gate.get("claim_disallowed_wording"),
    }


def markdown_report(gate: dict[str, Any]) -> str:
    summary = dict_or_empty(gate.get("summary"))
    lines = [
        "# QGE Shareware Release Candidate Gate",
        "",
        f"Status: {gate.get('status')}",
        "",
        "| Claim | Allowed |",
        "| --- | ---: |",
        (
            "| shareware release candidate | "
            f"{str(gate.get('shareware_release_candidate_claim_allowed')).lower()} |"
        ),
        (
            "| shareware Moonlab simulator/native deployment | "
            f"{str(gate.get('shareware_moonlab_deployment_claim_allowed')).lower()} |"
        ),
        (
            "| Noesis bounded autonomous diagnostics | "
            f"{str(gate.get('noesis_autonomous_diagnostics_claim_allowed')).lower()} |"
        ),
        (
            "| registered full-game Moonlab deployment | "
            f"{str(gate.get('whole_game_moonlab_deployment_claim_allowed')).lower()} |"
        ),
        (
            "| hardware quantum advantage | "
            f"{str(gate.get('hardware_quantum_advantage_claim_allowed')).lower()} |"
        ),
        (
            "| Noesis learned-play claim | "
            f"{str(gate.get('learned_play_claim_allowed')).lower()} |"
        ),
        "",
        "| Evidence | Value |",
        "| --- | ---: |",
        f"| publication ready | {summary.get('publication_ready_for_complete_claim')} |",
        f"| postpack passed | {summary.get('postpack_passed')} |",
        f"| shareware map set | {summary.get('shareware_map_set')} |",
        (
            f"| shareware covered maps | {summary.get('shareware_covered_map_count')} / "
            f"{summary.get('shareware_target_map_count')} |"
        ),
        f"| native bridge count | {summary.get('shareware_native_bridge_count')} |",
        f"| Noesis quality score | {summary.get('noesis_quality_score')} |",
        f"| Noesis quality grade | {summary.get('noesis_quality_grade')} |",
        f"| Noesis route distance | {summary.get('noesis_total_distance')} |",
        (
            "| registered full-game gate | "
            f"{summary.get('registered_full_game_gate_status')} |"
        ),
        "",
        f"Allowed wording: {gate.get('claim_allowed_wording')}",
        f"Disallowed wording: {gate.get('claim_disallowed_wording')}",
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
        description="Build the QGE shareware release-candidate gate")
    parser.add_argument(
        "pack_dir",
        type=Path,
        help="Publication pack directory or publication_manifest.json path.",
    )
    parser.add_argument(
        "--postpack",
        type=Path,
        default=None,
        help="Optional qge_postpack_audit.json override.",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--icc-json", type=Path, default=None)
    parser.add_argument(
        "--fail-on-blocked",
        action="store_true",
        help="Exit nonzero if the release-candidate gate is blocked.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        gate = build_gate_from_pack(args.pack_dir, postpack_path=args.postpack)
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
        print(f"qge_shareware_release_candidate_gate: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_SHAREWARE_RELEASE_CANDIDATE_GATE {args.out}")
    if args.markdown is not None:
        print(f"QGE_SHAREWARE_RELEASE_CANDIDATE_GATE_MARKDOWN {args.markdown}")
    if args.icc_json is not None:
        print(f"QGE_SHAREWARE_RELEASE_CANDIDATE_GATE_ICC {args.icc_json}")
    if args.fail_on_blocked and gate.get("status") != READY_STATUS:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
