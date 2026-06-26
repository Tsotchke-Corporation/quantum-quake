#!/usr/bin/env python3
"""Join shareware effect inventory to runtime evidence and report gaps."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_map_sets  # noqa: E402
import qge_shareware_effects_inventory  # noqa: E402


MATRIX_SCHEMA = "qge.shareware_effects_matrix.v0"
ICC_SCHEMA = "qge.icc_evidence.v0"
MATRIX_ICC_EVIDENCE_NAME = "qge_shareware_effects_icc_evidence.json"
DEFAULT_EFFECTS_ROOT = REPO_ROOT / "diagnostics" / "shareware_effects"
DEFAULT_STREAM_ROOT = REPO_ROOT / "diagnostics" / "quake_stream"
DEFAULT_BREADTH_ICC = (
    REPO_ROOT / "diagnostics" / "breadth_evidence" /
    "shareware_episode1" / "qge_breadth_icc_evidence.json"
)
DEFAULT_AGENT_STREAM_ROOT = REPO_ROOT / "diagnostics" / "agent_stream"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def latest_file(root: Path, name: str) -> Path | None:
    candidates = sorted(root.glob(f"*/{name}"))
    return candidates[-1] if candidates else None


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


def float_value(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (float, int)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def bool_true(value: Any) -> bool:
    return value is True or value == 1


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def map_from_readme(path: Path) -> str | None:
    readme = path.parent / "README.txt"
    if not readme.is_file():
        return None
    text = readme.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"^Map:\s*(\S+)", text, flags=re.MULTILINE)
    return match.group(1).lower() if match else None


def read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return [line.rstrip("\n") for line in f]


def log_int(line: str, key: str) -> int:
    match = re.search(rf"\b{re.escape(key)}=(-?\d+)", line)
    return int_value(match.group(1)) if match else 0


def collect_run_log_effects(run_dir: Path) -> dict[str, int]:
    log_path = run_dir / "quantum_quake.log"
    counters = {
        "render_sprite_frame_count": 0,
        "render_sprite_billboard_frame_count": 0,
        "render_own_sprite_frame_count": 0,
        "render_snapshot_particle_frame_count": 0,
        "render_encoded_particle_frame_count": 0,
        "render_own_particle_frame_count": 0,
        "physics_qparticle_spawn_frame_count": 0,
        "physics_impact_frame_count": 0,
    }
    if not log_path.is_file():
        return counters
    for line in read_lines(log_path):
        if "QGE render frame=" in line:
            if log_int(line, "sprites") > 0:
                counters["render_sprite_frame_count"] += 1
            if (
                log_int(line, "sprite_billboards") > 0 or
                log_int(line, "sbill") > 0
            ):
                counters["render_sprite_billboard_frame_count"] += 1
            if log_int(line, "own_sprites") > 0:
                counters["render_own_sprite_frame_count"] += 1
            if log_int(line, "snapshot_particles") > 0:
                counters["render_snapshot_particle_frame_count"] += 1
            if log_int(line, "encoded_particles") > 0:
                counters["render_encoded_particle_frame_count"] += 1
            if log_int(line, "own_particles") > 0:
                counters["render_own_particle_frame_count"] += 1
        elif "QGE physics frame=" in line:
            if log_int(line, "qparticle_spawns") > 0:
                counters["physics_qparticle_spawn_frame_count"] += 1
            if log_int(line, "impacts") > 0:
                counters["physics_impact_frame_count"] += 1
    return counters


def collect_footage_evidence(run_dir: Path) -> dict[str, Any]:
    run_id = run_dir.name
    stream_frames = sorted(run_dir.glob("frame_*.png"))
    agent_manifest = DEFAULT_AGENT_STREAM_ROOT / run_id / "manifest.json"
    manifest: dict[str, Any] = {}
    if agent_manifest.is_file():
        try:
            manifest = load_json(agent_manifest)
        except (OSError, ValueError, json.JSONDecodeError):
            manifest = {}
    manifest_run = dict_or_empty(manifest.get("run"))
    manifest_frames = int_value(manifest.get("frames_captured"))
    frame_count = max(len(stream_frames), manifest_frames)
    return {
        "run_id": run_id,
        "stream_frame_count": len(stream_frames),
        "agent_manifest_path": str(agent_manifest) if agent_manifest.is_file() else None,
        "agent_frames_captured": manifest_frames,
        "run_success": manifest_run.get("success") is True,
        "frame_count": frame_count,
    }


def collect_runtime_evidence(stream_root: Path) -> dict[str, Any]:
    trace_index: list[dict[str, Any]] = []
    material_totals = {
        "operator_count": 0,
        "water_decoherence_count": 0,
        "lava_phase_count": 0,
        "slipgate_phase_count": 0,
        "world_surface": 0,
    }
    totals = {
        "ai_decision_count": 0,
        "audio_ready_count": 0,
        "projectile_ready_count": 0,
        "projectile_save_demo_boundary_count": 0,
        "render_native_bridge_count": 0,
        "visibility_ready_count": 0,
        "weapon_operation_count": 0,
        "noesis_pass_count": 0,
        "noesis_evidence_count": 0,
        "noesis_route_sample_count": 0,
        "noesis_combat_sample_count": 0,
        "noesis_pickup_count": 0,
        "footage_capture_count": 0,
    }
    effect_log_totals = {
        "render_sprite_frame_count": 0,
        "render_sprite_billboard_frame_count": 0,
        "render_own_sprite_frame_count": 0,
        "render_snapshot_particle_frame_count": 0,
        "render_encoded_particle_frame_count": 0,
        "render_own_particle_frame_count": 0,
        "physics_qparticle_spawn_frame_count": 0,
        "physics_impact_frame_count": 0,
    }
    enemy_class_counts: dict[str, int] = {}
    enemy_type_counts: dict[str, int] = {}
    material_class_counts: dict[str, int] = {}
    weapon_class_counts: dict[str, int] = {}
    maps_with_trace: set[str] = set()
    maps_with_noesis: set[str] = set()
    maps_with_noesis_evidence: set[str] = set()
    maps_with_footage: set[str] = set()
    footage_index: list[dict[str, Any]] = []
    for trace_path in sorted(stream_root.glob("*/qge_trace_summary.json")):
        try:
            trace = load_json(trace_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        runtime = dict_or_empty(trace.get("runtime_evidence"))
        map_name = map_from_readme(trace_path)
        if map_name:
            maps_with_trace.add(map_name)
        run_log_effects = collect_run_log_effects(trace_path.parent)
        for name, count in run_log_effects.items():
            effect_log_totals[name] += count
        footage = collect_footage_evidence(trace_path.parent)
        if int_value(footage.get("frame_count")) > 0 and map_name:
            maps_with_footage.add(map_name)
            totals["footage_capture_count"] += 1
            footage_index.append({
                "map": map_name,
                "run_id": footage.get("run_id"),
                "trace_path": str(trace_path),
                "frame_count": footage.get("frame_count"),
                "stream_frame_count": footage.get("stream_frame_count"),
                "agent_frames_captured": footage.get("agent_frames_captured"),
                "agent_manifest_path": footage.get("agent_manifest_path"),
                "run_success": footage.get("run_success"),
            })
        material = dict_or_empty(runtime.get("material"))
        projectile = dict_or_empty(runtime.get("projectile"))
        ai = dict_or_empty(runtime.get("ai"))
        audio = dict_or_empty(runtime.get("audio"))
        render = dict_or_empty(runtime.get("render"))
        visibility = dict_or_empty(runtime.get("visibility"))
        weapon = dict_or_empty(runtime.get("weapon"))
        trace_enemy_class_counts = {
            str(name): int_value(count)
            for name, count in dict_or_empty(
                ai.get("enemy_class_counts")).items()
        }
        trace_enemy_type_counts = {
            str(name): int_value(count)
            for name, count in dict_or_empty(
                ai.get("enemy_type_counts")).items()
        }
        for name, count in trace_enemy_class_counts.items():
            enemy_class_counts[name] = enemy_class_counts.get(name, 0) + count
        for name, count in trace_enemy_type_counts.items():
            enemy_type_counts[name] = enemy_type_counts.get(name, 0) + count
        material_operator_count = int_value(material.get("operator_count"))
        material_water_count = int_value(material.get("water_decoherence_count"))
        material_lava_count = int_value(material.get("lava_phase_count"))
        material_slipgate_count = int_value(material.get("slipgate_phase_count"))
        trace_material_class_counts = {
            str(name): int_value(count)
            for name, count in dict_or_empty(
                material.get("class_counts")).items()
        }
        for name, count in trace_material_class_counts.items():
            material_class_counts[name] = max(
                material_class_counts.get(name, 0), count)
        material_totals["operator_count"] += material_operator_count
        material_totals["water_decoherence_count"] += material_water_count
        material_totals["lava_phase_count"] += material_lava_count
        material_totals["slipgate_phase_count"] += material_slipgate_count
        if dict_or_empty(material.get("flags")).get("world_surface"):
            material_totals["world_surface"] += 1
        ai_decision_count = int_value(ai.get("decision_count"))
        audio_ready = bool_true(audio.get("ready"))
        projectile_ready = bool_true(projectile.get("ready"))
        projectile_save_demo_boundary_count = int_value(
            projectile.get("save_demo_boundary_count"))
        render_native_bridge_count = int_value(render.get("native_bridge_count"))
        visibility_ready = bool_true(visibility.get("ready"))
        weapon_operation_count = int_value(
            weapon.get("operation_measurement_count") or
            weapon.get("weapon_operation_measurement_count"))
        trace_weapon_class_counts = {
            str(name): int_value(count)
            for name, count in dict_or_empty(
                weapon.get("class_counts")).items()
        }
        for name, count in trace_weapon_class_counts.items():
            weapon_class_counts[name] = (
                weapon_class_counts.get(name, 0) + count)
        totals["ai_decision_count"] += ai_decision_count
        if audio_ready:
            totals["audio_ready_count"] += 1
        if projectile_ready:
            totals["projectile_ready_count"] += 1
        totals["projectile_save_demo_boundary_count"] += int_value(
            projectile.get("save_demo_boundary_count"))
        totals["render_native_bridge_count"] += render_native_bridge_count
        if visibility_ready:
            totals["visibility_ready_count"] += 1
        totals["weapon_operation_count"] += weapon_operation_count
        trace_index.append({
            "path": str(trace_path),
            "map": map_name,
            "ai_decision_count": ai_decision_count,
            "ai_enemy_class_counts": trace_enemy_class_counts,
            "audio_ready": audio_ready,
            "material_lava_phase_count": material_lava_count,
            "material_class_counts": trace_material_class_counts,
            "material_operator_count": material_operator_count,
            "material_slipgate_phase_count": material_slipgate_count,
            "material_water_decoherence_count": material_water_count,
            "projectile_ready": projectile_ready,
            "projectile_save_demo_boundary_count": (
                projectile_save_demo_boundary_count
            ),
            "render_native_bridge_count": render_native_bridge_count,
            "visibility_ready": visibility_ready,
            "weapon_class_counts": trace_weapon_class_counts,
            "weapon_operation_count": weapon_operation_count,
            "effect_log_counts": run_log_effects,
            "footage_frame_count": footage.get("frame_count"),
        })
    for noesis_path in sorted(stream_root.glob("*/qge_noesis_summary.json")):
        try:
            noesis = load_json(noesis_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        map_name = map_from_readme(noesis_path)
        gameplay = dict_or_empty(noesis.get("gameplay"))
        route = dict_or_empty(gameplay.get("route"))
        combat = dict_or_empty(gameplay.get("combat"))
        pickup = dict_or_empty(gameplay.get("pickup"))
        quality_gates = dict_or_empty(noesis.get("quality_gates"))
        noesis_evidence_ready = (
            bool_true(quality_gates.get("run_completed")) and
            bool_true(gameplay.get("exists")) and
            int_value(gameplay.get("sample_count")) > 0
        )
        if map_name and noesis_evidence_ready:
            maps_with_noesis_evidence.add(map_name)
            totals["noesis_evidence_count"] += 1
            if float_value(route.get("total_distance")) > 0.0:
                totals["noesis_route_sample_count"] += 1
            if int_value(combat.get("enemy_contact_frames")) > 0:
                totals["noesis_combat_sample_count"] += 1
            totals["noesis_pickup_count"] += int_value(
                pickup.get("pickup_count"))
        if map_name and noesis.get("status") == "pass":
            maps_with_noesis.add(map_name)
            totals["noesis_pass_count"] += 1
    return {
        "trace_count": len(trace_index),
        "trace_index": trace_index,
        "maps_with_trace": sorted(maps_with_trace),
        "maps_with_noesis_pass": sorted(maps_with_noesis),
        "maps_with_noesis_evidence": sorted(maps_with_noesis_evidence),
        "maps_with_footage": sorted(maps_with_footage),
        "footage_index": footage_index,
        "enemy_class_counts": dict(sorted(enemy_class_counts.items())),
        "enemy_type_counts": dict(sorted(enemy_type_counts.items())),
        "material_class_counts": dict(sorted(material_class_counts.items())),
        "weapon_class_counts": dict(sorted(weapon_class_counts.items())),
        "material_totals": material_totals,
        "effect_log_totals": effect_log_totals,
        "totals": totals,
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
        "status": "pass" if passed else "blocked",
        "blocker": None if passed else blocker,
    }
    item.update(fields)
    return item


def build_matrix(
    *,
    inventory: dict[str, Any],
    breadth_icc: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    target_maps = qge_map_sets.map_targets_for_set(
        str(inventory.get("map_set") or qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET)
    )
    aggregate = dict_or_empty(inventory.get("aggregate"))
    material_totals = dict_or_empty(runtime.get("material_totals"))
    effect_log_totals = dict_or_empty(runtime.get("effect_log_totals"))
    runtime_material_class_counts = dict_or_empty(
        runtime.get("material_class_counts"))
    runtime_totals = dict_or_empty(runtime.get("totals"))
    map_coverage_ready = (
        inventory.get("status") == "complete" and
        int_value(inventory.get("target_map_count")) == len(target_maps) and
        int_value(inventory.get("inventoried_map_count")) == len(target_maps) and
        breadth_icc.get("runtime_backend_scope_map_set") ==
        qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET and
        breadth_icc.get("runtime_backend_scope_coverage_status") == "complete" and
        int_value(breadth_icc.get("runtime_backend_scope_covered_map_count")) ==
        len(target_maps)
    )
    slipgate_maps = list(aggregate.get("maps_with_slipgate_surfaces") or [])
    enemy_classes = dict_or_empty(aggregate.get("monster_class_counts"))
    runtime_enemy_class_counts = dict_or_empty(runtime.get("enemy_class_counts"))
    weapon_classes = dict_or_empty(aggregate.get("weapon_pickup_counts"))
    runtime_weapon_class_counts = dict_or_empty(runtime.get("weapon_class_counts"))
    material_counts = dict_or_empty(aggregate.get("material_surface_counts"))
    trace_index = [
        item for item in runtime.get("trace_index", [])
        if isinstance(item, dict)
    ]
    slipgate_evidence_maps = sorted({
        str(item.get("map")).lower()
        for item in trace_index
        if item.get("map") and
        int_value(item.get("material_slipgate_phase_count")) > 0
    })
    missing_slipgate_maps = sorted(
        set(str(name).lower() for name in slipgate_maps) -
        set(slipgate_evidence_maps)
    )
    observed_enemy_classes = sorted(
        name for name, count in runtime_enemy_class_counts.items()
        if int_value(count) > 0
    )
    missing_enemy_classes = sorted(
        set(str(name) for name in enemy_classes) -
        set(observed_enemy_classes)
    )
    material_classes = [
        key for key in [
            "ordinary", "water", "lava", "slime", "teleport", "sky",
            "fullbright", "warp",
        ]
        if int_value(material_counts.get(key)) > 0
    ]
    observed_material_classes = sorted(
        name for name, count in runtime_material_class_counts.items()
        if int_value(count) > 0
    )
    missing_material_classes = sorted(
        set(material_classes) - set(observed_material_classes)
    )
    observed_weapon_classes = sorted(
        name for name, count in runtime_weapon_class_counts.items()
        if int_value(count) > 0
    )
    missing_weapon_classes = sorted(
        set(str(name) for name in weapon_classes) - set(observed_weapon_classes)
    )
    projectile_core_ready = (
        int_value(runtime_totals.get("projectile_ready_count")) > 0 and
        int_value(runtime_totals.get("projectile_save_demo_boundary_count")) > 0
    )
    sprite_particle_ready = (
        int_value(effect_log_totals.get("render_sprite_billboard_frame_count")) > 0 and
        int_value(effect_log_totals.get("render_own_sprite_frame_count")) > 0 and
        (
            int_value(effect_log_totals.get(
                "render_snapshot_particle_frame_count")) > 0 or
            int_value(effect_log_totals.get(
                "render_encoded_particle_frame_count")) > 0
        ) and
        int_value(effect_log_totals.get(
            "physics_qparticle_spawn_frame_count")) > 0 and
        int_value(effect_log_totals.get("physics_impact_frame_count")) > 0 and
        int_value(runtime_totals.get("noesis_pickup_count")) > 0
    )
    noesis_evidence_maps = sorted(
        str(name).lower()
        for name in runtime.get("maps_with_noesis_evidence", [])
    )
    missing_noesis_evidence_maps = sorted(
        set(str(name).lower() for name in target_maps) -
        set(noesis_evidence_maps)
    )
    noesis_replay_ready = (
        not missing_noesis_evidence_maps and
        int_value(runtime_totals.get("noesis_route_sample_count")) > 0 and
        int_value(runtime_totals.get("noesis_combat_sample_count")) > 0 and
        int_value(runtime_totals.get("noesis_pass_count")) > 0 and
        int_value(runtime_totals.get("projectile_save_demo_boundary_count")) > 0
    )
    footage_ready = int_value(runtime_totals.get("footage_capture_count")) > 0
    criteria = [
        criterion(
            "map_coverage",
            "All shareware maps are represented by inventory and breadth evidence",
            map_coverage_ready,
            "inventory or breadth evidence is incomplete",
            target_map_count=len(target_maps),
            inventoried_map_count=inventory.get("inventoried_map_count"),
            breadth_covered_map_count=breadth_icc.get(
                "runtime_backend_scope_covered_map_count"),
        ),
        criterion(
            "slipgate_material",
            "Every map with inventory teleport surfaces has slipgate material operator evidence",
            not missing_slipgate_maps,
            "inventory finds maps with teleport/slipgate surfaces that lack matching runtime slipgate phase evidence",
            required_maps=slipgate_maps,
            observed_maps=slipgate_evidence_maps,
            missing_maps=missing_slipgate_maps,
            observed_slipgate_phase_count=material_totals.get(
                "slipgate_phase_count"),
        ),
        criterion(
            "enemy_classes",
            "Every discovered monster class has class-tied QGE/Noesis evidence",
            not missing_enemy_classes,
            "inventory monster classes lack matching runtime AI class evidence",
            discovered_classes=enemy_classes,
            observed_classes=observed_enemy_classes,
            missing_classes=missing_enemy_classes,
            runtime_enemy_class_counts=runtime_enemy_class_counts,
            aggregate_ai_decision_count=runtime_totals.get(
                "ai_decision_count"),
        ),
        criterion(
            "material_classes",
            "Every discovered material class has runtime material evidence",
            not missing_material_classes,
            "inventory material classes lack matching runtime material class evidence",
            discovered_material_classes=material_classes,
            observed_material_classes=observed_material_classes,
            missing_material_classes=missing_material_classes,
            runtime_material_class_counts=runtime_material_class_counts,
            runtime_material_totals=material_totals,
        ),
        criterion(
            "weapon_projectile_classes",
            "Discovered weapons and projectile behaviors are covered",
            projectile_core_ready and not missing_weapon_classes,
            "projectile core evidence exists only for a subset and is not tied to all discovered weapon classes",
            discovered_weapon_classes=weapon_classes,
            observed_weapon_classes=observed_weapon_classes,
            missing_weapon_classes=missing_weapon_classes,
            runtime_weapon_class_counts=runtime_weapon_class_counts,
            projectile_core_ready=projectile_core_ready,
        ),
        criterion(
            "particles_sprites",
            "Sprites, particles, explosions, gibs, and pickup effects are covered",
            sprite_particle_ready,
            "sprite/particle/explosion/gib/pickup runtime effect coverage is missing from matrix evidence",
            effect_log_totals=effect_log_totals,
            noesis_pickup_count=runtime_totals.get("noesis_pickup_count"),
        ),
        criterion(
            "audio_classes",
            "Weapon, monster, pickup, ambient, and teleport audio are covered",
            int_value(runtime_totals.get("audio_ready_count")) > 0,
            "source-audio authority evidence is missing from the current matrix",
            audio_ready_count=runtime_totals.get("audio_ready_count"),
        ),
        criterion(
            "noesis_replay",
            "Noesis route/combat and replay evidence cover the shareware effects matrix",
            noesis_replay_ready,
            "Noesis/replay evidence is not yet joined to every shareware map",
            noesis_pass_count=runtime_totals.get("noesis_pass_count"),
            noesis_evidence_count=runtime_totals.get("noesis_evidence_count"),
            noesis_route_sample_count=runtime_totals.get(
                "noesis_route_sample_count"),
            noesis_combat_sample_count=runtime_totals.get(
                "noesis_combat_sample_count"),
            noesis_evidence_maps=noesis_evidence_maps,
            missing_noesis_evidence_maps=missing_noesis_evidence_maps,
            projectile_save_demo_boundary_count=runtime_totals.get(
                "projectile_save_demo_boundary_count"),
        ),
        criterion(
            "footage",
            "Release footage is tied to matrix-backed real captures",
            footage_ready,
            "matrix-backed footage captures are missing",
            footage_capture_count=runtime_totals.get("footage_capture_count"),
            maps_with_footage=runtime.get("maps_with_footage", []),
            footage_index=runtime.get("footage_index", []),
        ),
    ]
    failed = [item for item in criteria if item["status"] != "pass"]
    status = "complete" if not failed else "blocked"
    return {
        "schema": MATRIX_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "map_set": inventory.get("map_set"),
        "target_maps": target_maps,
        "inventory_status": inventory.get("status"),
        "breadth_status": breadth_icc.get(
            "runtime_backend_scope_coverage_status"),
        "runtime": runtime,
        "criteria": criteria,
        "failed_criteria": failed,
        "failed_criterion_count": len(failed),
        "summary": {
            "map_coverage_ready": map_coverage_ready,
            "inventory_monster_class_count": len(enemy_classes),
            "inventory_weapon_class_count": len(weapon_classes),
            "runtime_weapon_class_count": len(observed_weapon_classes),
            "missing_weapon_class_count": len(missing_weapon_classes),
            "inventory_slipgate_map_count": len(slipgate_maps),
            "inventory_material_classes": material_classes,
            "runtime_material_class_count": len(observed_material_classes),
            "missing_material_class_count": len(missing_material_classes),
            "runtime_trace_count": runtime.get("trace_count"),
            "runtime_ai_decision_count": runtime_totals.get(
                "ai_decision_count"),
            "runtime_enemy_class_count": len(observed_enemy_classes),
            "missing_enemy_class_count": len(missing_enemy_classes),
            "runtime_projectile_save_demo_boundary_count": (
                runtime_totals.get("projectile_save_demo_boundary_count")
            ),
            "runtime_slipgate_phase_count": material_totals.get(
                "slipgate_phase_count"),
            "runtime_slipgate_map_count": len(slipgate_evidence_maps),
            "runtime_sprite_billboard_frame_count": effect_log_totals.get(
                "render_sprite_billboard_frame_count"),
            "runtime_snapshot_particle_frame_count": effect_log_totals.get(
                "render_snapshot_particle_frame_count"),
            "runtime_encoded_particle_frame_count": effect_log_totals.get(
                "render_encoded_particle_frame_count"),
            "runtime_qparticle_spawn_frame_count": effect_log_totals.get(
                "physics_qparticle_spawn_frame_count"),
            "runtime_noesis_evidence_map_count": len(noesis_evidence_maps),
            "missing_noesis_evidence_map_count": len(
                missing_noesis_evidence_maps),
            "runtime_footage_capture_count": runtime_totals.get(
                "footage_capture_count"),
            "ready_for_complete_effects_claim": status == "complete",
        },
    }


def build_icc_evidence(matrix: dict[str, Any], path: Path) -> dict[str, Any]:
    summary = dict_or_empty(matrix.get("summary"))
    ready = matrix.get("status") == "complete"
    criteria_status = {
        str(item.get("id")): item.get("status")
        for item in matrix.get("criteria", [])
        if isinstance(item, dict)
    }
    evidence: dict[str, Any] = {
        "schema": ICC_SCHEMA,
        "runtime_backend": "qge_shareware_effects_matrix",
        "completion_reason": (
            "qge_shareware_effects_matrix_complete"
            if ready else "qge_shareware_effects_matrix_blocked"
        ),
        "shareware_effects_matrix_file": str(path),
        "qge_shareware_effects_matrix.json": str(path),
        "runtime_backend_scope_map_set": matrix.get("map_set"),
        "shareware_effects_matrix_status": matrix.get("status"),
        "shareware_effects_matrix_failed_criterion_count": matrix.get(
            "failed_criterion_count"),
    }
    if summary.get("map_coverage_ready"):
        evidence["shareware_effects_map_coverage_completion"] = "complete"
    if criteria_status.get("slipgate_material") == "pass":
        evidence["shareware_slipgate_effect_evidence_completion"] = "present"
    if criteria_status.get("enemy_classes") == "pass":
        evidence["shareware_enemy_effect_evidence_completion"] = "complete"
    if criteria_status.get("material_classes") == "pass":
        evidence["shareware_material_effect_evidence_completion"] = "complete"
    if criteria_status.get("weapon_projectile_classes") == "pass":
        evidence["shareware_projectile_effect_evidence_completion"] = "complete"
    if criteria_status.get("particles_sprites") == "pass":
        evidence[
            "shareware_particle_sprite_effect_evidence_completion"
        ] = "complete"
    if criteria_status.get("audio_classes") == "pass":
        evidence["shareware_audio_effect_evidence_completion"] = "complete"
    if criteria_status.get("noesis_replay") == "pass":
        evidence[
            "shareware_noesis_replay_effect_evidence_completion"
        ] = "complete"
    if ready:
        evidence.update({
            "qge_shareware_complete_effects_ready": True,
        })
    return evidence


def markdown_report(matrix: dict[str, Any]) -> str:
    lines = [
        "# QGE Shareware Effects Matrix",
        "",
        f"- `status`: `{matrix.get('status')}`",
        f"- `map_set`: `{matrix.get('map_set')}`",
        f"- `failed_criteria`: `{matrix.get('failed_criterion_count')}`",
        "",
        "| Status | Criterion | Blocker |",
        "|---|---|---|",
    ]
    for item in matrix.get("criteria", []):
        lines.append(
            f"| `{item.get('status')}` | {item.get('label')} | "
            f"{item.get('blocker') or ''} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--breadth-icc", type=Path, default=DEFAULT_BREADTH_ICC)
    parser.add_argument("--stream-root", type=Path, default=DEFAULT_STREAM_ROOT)
    parser.add_argument("--map-set",
                        default=qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_EFFECTS_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    inventory_path = (
        args.inventory or
        latest_file(args.out_root, "qge_shareware_effects_inventory.json")
    )
    if inventory_path is None:
        raise SystemExit("no shareware effects inventory found")
    run_dir = args.out_root / datetime.now(timezone.utc).strftime(
        "%Y%m%d-%H%M%S")
    out_path = args.out or run_dir / "qge_shareware_effects_matrix.json"
    markdown_path = args.markdown or out_path.with_name(
        "qge_shareware_effects_matrix.md")
    icc_path = args.icc_json or out_path.with_name(MATRIX_ICC_EVIDENCE_NAME)
    inventory = load_json(inventory_path)
    if inventory.get("map_set") != args.map_set:
        raise SystemExit(
            f"inventory map_set {inventory.get('map_set')!r} does not match "
            f"{args.map_set!r}")
    breadth = load_json(args.breadth_icc)
    runtime = collect_runtime_evidence(args.stream_root)
    matrix = build_matrix(
        inventory=inventory,
        breadth_icc=breadth,
        runtime=runtime,
    )
    matrix["source_inventory_file"] = str(inventory_path)
    matrix["source_breadth_icc_file"] = str(args.breadth_icc)
    write_json(out_path, matrix)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown_report(matrix), encoding="utf-8")
    write_json(icc_path, build_icc_evidence(matrix, out_path))
    print(f"QGE_SHAREWARE_EFFECTS_MATRIX {out_path}")
    print(f"QGE_SHAREWARE_EFFECTS_MATRIX_MARKDOWN {markdown_path}")
    print(f"QGE_SHAREWARE_EFFECTS_MATRIX_ICC {icc_path}")
    return 0 if matrix.get("status") == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
