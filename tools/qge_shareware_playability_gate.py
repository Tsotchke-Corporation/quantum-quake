#!/usr/bin/env python3
"""Final user-playability gate for the complete Quake shareware release."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_full_game_capture_queue  # noqa: E402
import qge_map_sets  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402
import qge_moonlab_shareware_deployment_gate  # noqa: E402
import qge_noesis_release_gate  # noqa: E402
import qge_shareware_release_bundle  # noqa: E402
import qge_shareware_release_candidate_gate  # noqa: E402


READY_STATUS = "ready_for_shareware_user_playable_release"
BLOCKED = "blocked"
PASS = "pass"
SHAREWARE_MAP_SET = qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET
EXPECTED_SHAREWARE_MAP_COUNT = 9
EXPECTED_SHAREWARE_PAK_ENTRIES = 339
EXPECTED_SHAREWARE_EXTRA_BSP_COUNT = 12
EXPECTED_PAK_EXTENSIONS = {
    "bin",
    "bsp",
    "cfg",
    "dat",
    "dem",
    "lmp",
    "mdl",
    "rc",
    "spr",
    "wad",
    "wav",
}
REQUIRED_PAK_ENTRIES = {
    "gfx.wad",
    "gfx/finale.lmp",
    "gfx/mainmenu.lmp",
    "gfx/sp_menu.lmp",
    "maps/start.bsp",
    "maps/e1m1.bsp",
    "maps/e1m2.bsp",
    "maps/e1m3.bsp",
    "maps/e1m4.bsp",
    "maps/e1m5.bsp",
    "maps/e1m6.bsp",
    "maps/e1m7.bsp",
    "maps/e1m8.bsp",
    "progs.dat",
    "sound/misc/menu1.wav",
    "sound/misc/menu2.wav",
    "sound/misc/menu3.wav",
}
REQUIRED_OWNERSHIP_FIELDS = {
    "own_world",
    "own_textures",
    "own_lightmaps",
    "own_entities",
    "own_sprites",
    "own_particles",
    "own_viewmodel",
    "own_hud",
    "own_console",
}


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
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        try:
            return int(float(str(value)))
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


def resolve_pack_dir(pack_or_manifest: Path) -> Path:
    manifest = qge_moonlab_full_game_plan.resolve_publication_manifest(
        pack_or_manifest)
    if not manifest.is_file():
        raise ValueError(f"publication manifest not found: {manifest}")
    return manifest.parent


def resolve_path(raw: Any, *, base_dir: Path | None = None) -> Path | None:
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    if base_dir is not None:
        candidate = base_dir / path
        if candidate.exists():
            return candidate
    return path


def latest_effects_gate(root: Path) -> Path | None:
    candidates = sorted(root.glob("*/qge_shareware_complete_effects_gate.json"))
    return candidates[-1] if candidates else None


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


def pak_entry_report(
    asset_inventory: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    pak_entries: set[str] = set()
    extension_counts: Counter[str] = Counter()
    pak_files = [
        item for item in asset_inventory.get("pak_files", [])
        if isinstance(item, dict)
    ]
    read_errors: list[str] = []
    for pak_file in pak_files:
        path = resolve_path(pak_file.get("path"), base_dir=repo_root)
        if path is None:
            continue
        try:
            records = qge_full_game_capture_queue.pak_directory_records(path)
        except (OSError, ValueError) as exc:
            read_errors.append(f"{path}: {exc}")
            continue
        for record in records:
            name = str(record.get("name") or "")
            if not name:
                continue
            pak_entries.add(name)
            extension = Path(name).suffix.lower().lstrip(".") or "none"
            extension_counts[extension] += 1
    missing_required = sorted(REQUIRED_PAK_ENTRIES - pak_entries)
    unknown_extensions = sorted(set(extension_counts) - EXPECTED_PAK_EXTENSIONS)
    return {
        "entry_count": len(pak_entries),
        "extension_counts": dict(sorted(extension_counts.items())),
        "missing_required_entries": missing_required,
        "unknown_extensions": unknown_extensions,
        "read_errors": read_errors,
        "required_entry_count": len(REQUIRED_PAK_ENTRIES),
    }


def matrix_for_effects_gate(effects_gate: dict[str, Any],
                            effects_gate_path: Path) -> dict[str, Any]:
    matrix_path = resolve_path(
        effects_gate.get("source_matrix_file"),
        base_dir=effects_gate_path.parent,
    )
    if matrix_path is None or not matrix_path.is_file():
        return {}
    return load_json_object(matrix_path)


def inventory_for_effects_gate(effects_gate: dict[str, Any],
                               effects_gate_path: Path) -> dict[str, Any]:
    inventory_path = resolve_path(
        effects_gate.get("source_inventory_file"),
        base_dir=effects_gate_path.parent,
    )
    if inventory_path is None or not inventory_path.is_file():
        return {}
    return load_json_object(inventory_path)


def matrix_criteria_pass(matrix: dict[str, Any]) -> bool:
    criteria = [
        item for item in matrix.get("criteria", [])
        if isinstance(item, dict)
    ]
    return bool(criteria) and all(item.get("status") == PASS
                                  for item in criteria)


def ownership_ready(vanilla_matrix: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    conformance = dict_or_empty(vanilla_matrix.get("conformance_summary"))
    ownership = dict_or_empty(conformance.get("qge_asset_ownership"))
    missing_fields = sorted(
        field for field in REQUIRED_OWNERSHIP_FIELDS
        if int_value(ownership.get(field)) <= 0
    )
    domain = dict_or_empty(conformance.get("moonlab_domain_readiness"))
    required_domain_blockers = {
        name: entry
        for name, entry in domain.items()
        if isinstance(entry, dict) and
        entry.get("required") is not False and
        entry.get("ready") is not True
    }
    ready = (
        bool_true(conformance.get("ready_for_complete_claim")) and
        bool_true(conformance.get("qge_asset_ownership_complete")) and
        not missing_fields and
        not required_domain_blockers and
        int_value(conformance.get("classic3d_latest")) == 0 and
        int_value(conformance.get("classic2d_latest")) == 0 and
        int_value(conformance.get("fallback_count")) == 0 and
        int_value(conformance.get("viewmodel_encoded")) > 0
    )
    return ready, {
        "ready_for_complete_claim": conformance.get("ready_for_complete_claim"),
        "qge_asset_ownership_complete": conformance.get(
            "qge_asset_ownership_complete"),
        "ownership": ownership,
        "missing_ownership_fields": missing_fields,
        "required_domain_blockers": required_domain_blockers,
        "classic3d_latest": conformance.get("classic3d_latest"),
        "classic2d_latest": conformance.get("classic2d_latest"),
        "fallback_count": conformance.get("fallback_count"),
        "viewmodel_encoded": conformance.get("viewmodel_encoded"),
    }


def release_bundle_ready(bundle: dict[str, Any]) -> bool:
    archive = dict_or_empty(bundle.get("archive"))
    return (
        bundle.get("schema") == "qge.shareware_release_bundle.v0" and
        bundle.get("status") == qge_shareware_release_bundle.READY_STATUS and
        bundle.get("shareware_release_bundle_ready") is True and
        int_value(bundle.get("blocker_count")) == 0 and
        isinstance(archive.get("sha256"), str) and
        len(str(archive.get("sha256"))) == 64 and
        int_value(archive.get("size_bytes")) > 0
    )


def build_criteria(
    *,
    pack_dir: Path,
    asset_inventory: dict[str, Any],
    pak_report: dict[str, Any],
    release_candidate: dict[str, Any],
    release_bundle: dict[str, Any],
    shareware_gate: dict[str, Any],
    effects_gate: dict[str, Any],
    effects_matrix: dict[str, Any],
    effects_inventory: dict[str, Any],
    vanilla_matrix: dict[str, Any],
) -> list[dict[str, Any]]:
    asset_ready = (
        asset_inventory.get("schema") == "qge.asset_inventory.v0" and
        asset_inventory.get("status") == "complete" and
        bool_true(asset_inventory.get("shareware_episode_one_scope")) and
        bool_true(asset_inventory.get("shareware_episode_one_asset_ready")) and
        int_value(asset_inventory.get("available_map_count")) ==
        EXPECTED_SHAREWARE_MAP_COUNT and
        int_value(asset_inventory.get("target_map_count")) ==
        EXPECTED_SHAREWARE_MAP_COUNT and
        int_value(asset_inventory.get("missing_map_count")) == 0 and
        int_value(asset_inventory.get("invalid_bsp_count")) == 0 and
        int_value(asset_inventory.get("extra_map_count")) ==
        EXPECTED_SHAREWARE_EXTRA_BSP_COUNT and
        int_value(asset_inventory.get("pak_count")) >= 1 and
        int_value(pak_report.get("entry_count")) >=
        EXPECTED_SHAREWARE_PAK_ENTRIES and
        not pak_report.get("missing_required_entries") and
        not pak_report.get("unknown_extensions") and
        not pak_report.get("read_errors")
    )
    shareware_summary = dict_or_empty(shareware_gate.get("summary"))
    shareware_criteria = [
        item for item in shareware_gate.get("criteria", [])
        if isinstance(item, dict)
    ]
    map_runtime_ready = (
        shareware_gate.get("schema") ==
        "qge.moonlab_shareware_deployment_gate.v0" and
        shareware_gate.get("status") ==
        qge_moonlab_shareware_deployment_gate.READY_STATUS and
        shareware_gate.get("shareware_moonlab_deployment_claim_allowed")
        is True and
        int_value(shareware_gate.get("blocker_count")) == 0 and
        all(item.get("status") == PASS for item in shareware_criteria) and
        int_value(shareware_summary.get("covered_map_count")) ==
        EXPECTED_SHAREWARE_MAP_COUNT and
        int_value(shareware_summary.get("target_map_count")) ==
        EXPECTED_SHAREWARE_MAP_COUNT and
        int_value(shareware_summary.get("total_fallback_count")) == 0 and
        int_value(shareware_summary.get("total_surrogate_count")) == 0 and
        int_value(shareware_summary.get("total_cpu_idwt_count")) == 0
    )
    matrix_summary = dict_or_empty(
        dict_or_empty(effects_gate.get("summary")).get("matrix_summary"))
    effects_ready = (
        effects_gate.get("schema") == "qge.shareware_complete_effects_gate.v0"
        and effects_gate.get("status") ==
        "ready_for_shareware_complete_effects_claim" and
        bool_true(dict_or_empty(effects_gate.get("summary")).get(
            "ready_for_complete_effects_claim")) and
        effects_matrix.get("status") == "complete" and
        matrix_criteria_pass(effects_matrix) and
        effects_inventory.get("status") == "complete" and
        int_value(matrix_summary.get("missing_enemy_class_count")) == 0 and
        int_value(matrix_summary.get("missing_material_class_count")) == 0 and
        int_value(matrix_summary.get("missing_weapon_class_count")) == 0 and
        int_value(matrix_summary.get("missing_noesis_evidence_map_count")) == 0
        and int_value(matrix_summary.get("runtime_footage_capture_count")) > 0
    )
    ownership_is_ready, ownership_evidence = ownership_ready(vanilla_matrix)
    release_candidate_ready = (
        release_candidate.get("schema") ==
        "qge.shareware_release_candidate_gate.v0" and
        release_candidate.get("status") ==
        qge_shareware_release_candidate_gate.READY_STATUS and
        release_candidate.get("shareware_release_candidate_claim_allowed")
        is True and
        int_value(release_candidate.get("blocker_count")) == 0 and
        release_candidate.get("whole_game_moonlab_deployment_claim_allowed")
        is False and
        release_candidate.get("hardware_quantum_advantage_claim_allowed")
        is False and
        release_candidate.get("learned_play_claim_allowed") is False
    )
    bundle_ready = release_bundle_ready(release_bundle)
    aggregate = dict_or_empty(effects_inventory.get("aggregate"))
    trigger_counts = dict_or_empty(aggregate.get("trigger_counts"))
    item_counts = dict_or_empty(aggregate.get("item_counts"))
    frontend_ready = (
        ownership_is_ready and
        int_value(ownership_evidence["ownership"].get("own_hud")) > 0 and
        int_value(ownership_evidence["ownership"].get("own_console")) > 0 and
        int_value(trigger_counts.get("trigger_changelevel")) > 0 and
        int_value(trigger_counts.get("trigger_teleport")) > 0 and
        int_value(item_counts.get("item_sigil")) > 0 and
        not pak_report.get("missing_required_entries")
    )
    return [
        criterion(
            "shareware_pak_content_complete",
            "The local shareware PAK contains all expected maps, UI, model, sprite, sound, and program asset classes",
            asset_ready,
            "shareware PAK content is missing, invalid, or not fully inventoried",
            asset_inventory_status=asset_inventory.get("status"),
            available_map_count=asset_inventory.get("available_map_count"),
            target_map_count=asset_inventory.get("target_map_count"),
            extra_map_count=asset_inventory.get("extra_map_count"),
            pak_entry_count=pak_report.get("entry_count"),
            pak_extension_counts=pak_report.get("extension_counts"),
            missing_required_entries=pak_report.get(
                "missing_required_entries"),
            unknown_extensions=pak_report.get("unknown_extensions"),
            read_errors=pak_report.get("read_errors"),
        ),
        criterion(
            "all_shareware_maps_runtime_playable",
            "All nine shareware maps have ready runtime, route, backend, and deployment evidence",
            map_runtime_ready,
            "one or more shareware maps lacks ready runtime/deployment evidence",
            gate_status=shareware_gate.get("status"),
            covered_map_count=shareware_summary.get("covered_map_count"),
            target_map_count=shareware_summary.get("target_map_count"),
            total_native_bridge_count=shareware_summary.get(
                "total_native_bridge_count"),
            total_fallback_count=shareware_summary.get("total_fallback_count"),
            total_surrogate_count=shareware_summary.get(
                "total_surrogate_count"),
            total_cpu_idwt_count=shareware_summary.get("total_cpu_idwt_count"),
            failing_shareware_criteria=[
                item for item in shareware_criteria
                if item.get("status") != PASS
            ],
        ),
        criterion(
            "complete_effects_and_content_runtime",
            "Inventory-discovered shareware enemies, weapons, materials, particles, audio, Noesis, and footage are covered",
            effects_ready,
            "complete-effects gate or matrix is missing runtime evidence",
            effects_gate_status=effects_gate.get("status"),
            effects_matrix_status=effects_matrix.get("status"),
            effects_inventory_status=effects_inventory.get("status"),
            matrix_failed_criterion_count=effects_matrix.get(
                "failed_criterion_count"),
            matrix_summary=matrix_summary,
        ),
        criterion(
            "qge_ownership_and_frontend_ready",
            "QGE owns runtime rendering, HUD/status, console, viewmodel, sprites, particles, audio, visibility, and frontend-critical assets",
            frontend_ready,
            "QGE ownership or frontend/status/intermission asset evidence is incomplete",
            ownership_evidence=ownership_evidence,
            trigger_changelevel_count=trigger_counts.get(
                "trigger_changelevel"),
            trigger_teleport_count=trigger_counts.get("trigger_teleport"),
            sigil_count=item_counts.get("item_sigil"),
        ),
        criterion(
            "release_candidate_and_bundle_ready",
            "The ready release-candidate gate is packaged in a persistent shareware ZIP with checksum",
            release_candidate_ready and bundle_ready,
            "release candidate or release bundle is blocked or missing",
            release_candidate_status=release_candidate.get("status"),
            release_candidate_blocker_count=release_candidate.get(
                "blocker_count"),
            release_bundle_status=release_bundle.get("status"),
            release_bundle_blocker_count=release_bundle.get("blocker_count"),
            release_archive=dict_or_empty(release_bundle.get("archive")),
            pack_dir=str(pack_dir),
        ),
    ]


def next_actions_for_blockers(blockers: list[dict[str, Any]]) -> list[str]:
    if not blockers:
        return [
            "Ship the shareware release bundle ZIP with the playability gate, complete-effects gate, release-candidate gate, and checksums.",
            "Keep the registered/full-game release separate until registered assets and registered-map evidence are complete.",
        ]
    actions = []
    for blocker in blockers:
        blocker_id = blocker.get("id")
        if blocker_id == "shareware_pak_content_complete":
            actions.append(
                "Repair assets/id1/pak0.pak or regenerate the asset/effects inventories from a complete Quake shareware PAK.")
        elif blocker_id == "all_shareware_maps_runtime_playable":
            actions.append(
                "Rerun shareware breadth/deployment captures until all nine maps pass without fallback, surrogate, or CPU-IDWT counts.")
        elif blocker_id == "complete_effects_and_content_runtime":
            actions.append(
                "Regenerate targeted effects captures and the complete-effects gate until every matrix criterion passes.")
        elif blocker_id == "qge_ownership_and_frontend_ready":
            actions.append(
                "Regenerate vanilla/QGE conformance evidence with owned HUD, console, viewmodel, sprites, particles, audio, and hidden classic output.")
        elif blocker_id == "release_candidate_and_bundle_ready":
            actions.append(
                "Rerun the release-candidate gate and shareware release-bundle tool, then mirror their ICC sidecars into the publication pack release directory.")
    return actions


def build_gate(
    *,
    pack_dir: Path,
    asset_inventory: dict[str, Any],
    pak_report: dict[str, Any],
    release_candidate: dict[str, Any],
    release_bundle: dict[str, Any],
    shareware_gate: dict[str, Any],
    effects_gate: dict[str, Any],
    effects_matrix: dict[str, Any],
    effects_inventory: dict[str, Any],
    vanilla_matrix: dict[str, Any],
) -> dict[str, Any]:
    criteria = build_criteria(
        pack_dir=pack_dir,
        asset_inventory=asset_inventory,
        pak_report=pak_report,
        release_candidate=release_candidate,
        release_bundle=release_bundle,
        shareware_gate=shareware_gate,
        effects_gate=effects_gate,
        effects_matrix=effects_matrix,
        effects_inventory=effects_inventory,
        vanilla_matrix=vanilla_matrix,
    )
    blockers = failed_criteria(criteria)
    ready = not blockers
    bundle_summary = dict_or_empty(release_bundle.get("summary"))
    matrix_summary = dict_or_empty(
        dict_or_empty(effects_gate.get("summary")).get("matrix_summary"))
    return {
        "schema": "qge.shareware_playability_gate.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": READY_STATUS if ready else BLOCKED,
        "map_set": SHAREWARE_MAP_SET,
        "shareware_user_playable_release_ready": ready,
        "shareware_release_candidate_claim_allowed": ready,
        "whole_game_moonlab_deployment_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "hardware_quantum_advantage_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "learned_play_claim_allowed": False,
        "criteria": criteria,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "failed_criterion_count": len(blockers),
        "summary": {
            "map_set": SHAREWARE_MAP_SET,
            "pack_dir": str(pack_dir),
            "pak_entry_count": pak_report.get("entry_count"),
            "pak_extension_counts": pak_report.get("extension_counts"),
            "shareware_maps": (
                asset_inventory.get("available_map_count"),
                asset_inventory.get("target_map_count"),
            ),
            "shareware_extra_bsp_count": asset_inventory.get(
                "extra_map_count"),
            "runtime_covered_map_count": bundle_summary.get(
                "shareware_covered_map_count"),
            "runtime_target_map_count": bundle_summary.get(
                "shareware_target_map_count"),
            "effects_gate_status": effects_gate.get("status"),
            "effects_runtime_enemy_class_count": matrix_summary.get(
                "runtime_enemy_class_count"),
            "effects_runtime_material_class_count": matrix_summary.get(
                "runtime_material_class_count"),
            "effects_footage_capture_count": matrix_summary.get(
                "runtime_footage_capture_count"),
            "release_bundle_status": release_bundle.get("status"),
            "release_archive": dict_or_empty(release_bundle.get("archive")),
            "release_archive_checksum_file": dict_or_empty(
                release_bundle.get("sidecars")).get("archive_checksum_file"),
        },
        "next_actions": next_actions_for_blockers(blockers),
        "limits": [
            "This gate is a complete Quake shareware Episode 1 user-playable release signoff.",
            "It does not authorize registered/full-game assets or registered-map coverage.",
            "It does not claim hardware execution, hardware quantum advantage, dense state-vector execution, or learned Noesis play.",
        ],
    }


def build_icc_evidence(gate: dict[str, Any],
                       *,
                       out_path: Path | None = None) -> dict[str, Any]:
    summary = dict_or_empty(gate.get("summary"))
    archive = dict_or_empty(summary.get("release_archive"))
    checksum_file = summary.get("release_archive_checksum_file")
    ready = gate.get("shareware_user_playable_release_ready") is True
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_shareware_playability_gate",
        "completion_reason": (
            "qge_shareware_user_playable_release_ready"
            if ready else "qge_shareware_user_playable_release_blocked"),
        "status": "success",
        "shareware_playability_gate_file": str(out_path) if out_path else None,
        "qge_shareware_playability_gate.json": (
            str(out_path) if out_path else None),
        "runtime_backend_scope_map_set": SHAREWARE_MAP_SET,
        "release_scope": SHAREWARE_MAP_SET,
        "map_set": SHAREWARE_MAP_SET,
        "shareware_playability_gate_status": gate.get("status"),
        "shareware_user_playable_release_ready": ready,
        "shareware_release_candidate_claim_allowed": gate.get(
            "shareware_release_candidate_claim_allowed"),
        "shareware_pak_entry_count": summary.get("pak_entry_count"),
        "shareware_covered_map_count": summary.get("runtime_covered_map_count"),
        "shareware_target_map_count": summary.get("runtime_target_map_count"),
        "shareware_release_bundle_status": summary.get(
            "release_bundle_status"),
        "shareware_release_bundle_archive_checksum_file": checksum_file,
        "qge_shareware_release_bundle_archive_checksum.json": checksum_file,
        "shareware_release_bundle_archive_file": archive.get("path"),
        "shareware_release_bundle_archive_sha256": archive.get("sha256"),
        "whole_game_moonlab_deployment_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "hardware_quantum_advantage_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "noesis_learned_play_claim_allowed": False,
    }


def markdown_report(gate: dict[str, Any]) -> str:
    summary = dict_or_empty(gate.get("summary"))
    archive = dict_or_empty(summary.get("release_archive"))
    lines = [
        "# QGE Shareware Playability Gate",
        "",
        f"Status: `{gate.get('status')}`",
        f"Map set: `{gate.get('map_set')}`",
        "",
        "| Field | Value |",
        "| --- | ---: |",
        f"| PAK entries | {summary.get('pak_entry_count')} |",
        f"| shareware maps | {summary.get('shareware_maps')} |",
        f"| extra BSP models | {summary.get('shareware_extra_bsp_count')} |",
        (
            "| runtime maps | "
            f"{summary.get('runtime_covered_map_count')} / "
            f"{summary.get('runtime_target_map_count')} |"
        ),
        f"| effects gate | {summary.get('effects_gate_status')} |",
        f"| release bundle | {summary.get('release_bundle_status')} |",
        f"| archive | {archive.get('path')} |",
        f"| archive sha256 | {archive.get('sha256')} |",
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


def load_inputs(
    *,
    pack_dir: Path,
    repo_root: Path,
    effects_gate_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any],
           dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    release_dir = pack_dir / "release"
    effects_path = effects_gate_path or latest_effects_gate(
        repo_root / "diagnostics" / "shareware_effects")
    if effects_path is None:
        raise ValueError("no qge_shareware_complete_effects_gate.json found")
    effects_gate = load_json_object(effects_path)
    effects_matrix = matrix_for_effects_gate(effects_gate, effects_path)
    effects_inventory = inventory_for_effects_gate(effects_gate, effects_path)
    return (
        load_json_object(pack_dir / "resource" / "qge_asset_inventory.json"),
        load_json_object(
            release_dir / "qge_shareware_release_candidate_gate.json"),
        load_json_object(
            release_dir / "qge_shareware_release_bundle.json"),
        load_json_object(
            pack_dir / "resource" /
            "qge_moonlab_shareware_deployment_gate.json"),
        effects_gate,
        effects_matrix,
        effects_inventory,
        load_json_object(pack_dir / "vanilla" / "vanilla_capture_matrix.json"),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pack_dir",
        type=Path,
        help="Publication pack directory or publication_manifest.json path.",
    )
    parser.add_argument("--effects-gate", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    parser.add_argument("--fail-on-blocked", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo_root = SCRIPT_DIR.parent
        pack_dir = resolve_pack_dir(args.pack_dir)
        (
            asset_inventory,
            release_candidate,
            release_bundle,
            shareware_gate,
            effects_gate,
            effects_matrix,
            effects_inventory,
            vanilla_matrix,
        ) = load_inputs(
            pack_dir=pack_dir,
            repo_root=repo_root,
            effects_gate_path=args.effects_gate,
        )
        pak_report = pak_entry_report(asset_inventory, repo_root=repo_root)
        gate = build_gate(
            pack_dir=pack_dir,
            asset_inventory=asset_inventory,
            pak_report=pak_report,
            release_candidate=release_candidate,
            release_bundle=release_bundle,
            shareware_gate=shareware_gate,
            effects_gate=effects_gate,
            effects_matrix=effects_matrix,
            effects_inventory=effects_inventory,
            vanilla_matrix=vanilla_matrix,
        )
        out_path = args.out or (
            pack_dir / "release" / "qge_shareware_playability_gate.json")
        markdown_path = args.markdown or out_path.with_suffix(".md")
        icc_path = args.icc_json or out_path.with_name(
            "qge_shareware_playability_gate_icc_evidence.json")
        write_json(out_path, gate)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown_report(gate), encoding="utf-8")
        write_json(icc_path, build_icc_evidence(gate, out_path=out_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"qge_shareware_playability_gate: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_SHAREWARE_PLAYABILITY_GATE {out_path}")
    print(f"QGE_SHAREWARE_PLAYABILITY_GATE_MARKDOWN {markdown_path}")
    print(f"QGE_SHAREWARE_PLAYABILITY_GATE_ICC {icc_path}")
    if args.fail_on_blocked and gate.get("status") != READY_STATUS:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
