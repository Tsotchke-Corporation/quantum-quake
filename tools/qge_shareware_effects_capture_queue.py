#!/usr/bin/env python3
"""Build runnable capture jobs for missing shareware effect-matrix cells."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_map_sets  # noqa: E402


QUEUE_SCHEMA = "qge.shareware_effects_capture_queue.v0"
ICC_SCHEMA = "qge.icc_evidence.v0"
DEFAULT_EFFECTS_ROOT = REPO_ROOT / "diagnostics" / "shareware_effects"
DEFAULT_STREAM_SCRIPT = "tools/quake_graphics_stream.sh"
DEFAULT_ENV = {
    "QGE_STREAM_LAUNCH": "direct",
    "QGE_STREAM_MOUSE": "0",
    "QGE_STREAM_PLAYER": "noesis",
    "QGE_STREAM_TRACE": "1",
    "QGE_STREAM_SOUND": "1",
    "QGE_STREAM_SND_QUANTUM": "2",
    "QGE_STREAM_SND_QUANTUM_SOURCE_AUTHORITY": "1",
    "QGE_STREAM_ENGINE_CAPTURE": "1",
    "QGE_STREAM_SPRITE_TEST": "0",
    "QGE_PARTICLES": "1",
    "QGE_PHYSICS": "1",
    "QGE_PROJECTILES": "1",
    "QGE_PHYSICS_AUTHORITATIVE": "1",
    "QGE_RENDER": "1",
    "QGE_RENDER_RES": "1024",
    "QGE_RENDER_THRESHOLD": "0.001",
    "QGE_RENDER_EDGE_GAIN": "0",
    "QGE_RENDER_MATERIAL_GAIN": "0.18",
}
PROFILE_ENV = {
    "slipgate_material": {
        "QGE_NOESIS_PLAN": "map-scout",
        "QGE_NOESIS_SCRIPTED": "1",
        "QGE_NOESIS_REQUIRE_COMBAT": "0",
        "QGE_NOESIS_MIN_ROUTE_DISTANCE": "16",
        "QGE_NOESIS_MIN_LOG_PHASES": "1",
    },
    "start_slipgate_material": {
        "QGE_NOESIS_PLAN": "start-hub-route",
        "QGE_NOESIS_SCRIPTED": "1",
        "QGE_NOESIS_REQUIRE_COMBAT": "0",
        "QGE_NOESIS_MIN_ROUTE_DISTANCE": "16",
        "QGE_NOESIS_MIN_LOG_PHASES": "2",
        "QGE_NOESIS_START_WAIT": "24",
        "QGE_NOESIS_ASSIST": "0",
    },
    "enemy_class": {
        "QGE_NOESIS_PLAN": "combat-explore",
        "QGE_NOESIS_SCRIPTED": "1",
        "QGE_NOESIS_REQUIRE_COMBAT": "1",
        "QGE_STREAM_FIRE_TEST": "1",
        "QGE_NOESIS_MIN_GAMEPLAY_SAMPLES": "4",
        "QGE_NOESIS_MIN_ROUTE_DISTANCE": "32",
        "QGE_NOESIS_MIN_CAPTURE_WAIT": "120",
    },
    "material_class": {
        "QGE_NOESIS_PLAN": "map-scout",
        "QGE_NOESIS_SCRIPTED": "1",
        "QGE_NOESIS_REQUIRE_COMBAT": "0",
        "QGE_NOESIS_MIN_ROUTE_DISTANCE": "32",
    },
    "weapon_projectile_class": {
        "QGE_NOESIS_PLAN": "weapon-cycle-smoke",
        "QGE_NOESIS_SCRIPTED": "1",
        "QGE_STREAM_FIRE_TEST": "1",
        "QGE_NOESIS_REQUIRE_COMBAT": "0",
        "QGE_NOESIS_MIN_GAMEPLAY_SAMPLES": "2",
        "QGE_NOESIS_START_WAIT": "0",
    },
    "particles_sprites": {
        "QGE_NOESIS_PLAN": "combat-explore",
        "QGE_NOESIS_SCRIPTED": "1",
        "QGE_STREAM_FIRE_TEST": "1",
        "QGE_STREAM_SPRITE_TEST": "1",
        "QGE_PARTICLES": "1",
        "QGE_NOESIS_REQUIRE_COMBAT": "1",
    },
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


def latest_file(root: Path, name: str) -> Path | None:
    candidates = sorted(root.glob(f"*/{name}"))
    return candidates[-1] if candidates else None


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def criteria_by_id(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in list_or_empty(matrix.get("criteria"))
        if isinstance(item, dict)
    }


def criterion_blocked(criteria: dict[str, dict[str, Any]], criterion_id: str) -> bool:
    criterion = criteria.get(criterion_id)
    return bool(criterion) and criterion.get("status") != "pass"


def inventory_maps(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item for item in list_or_empty(inventory.get("maps"))
        if isinstance(item, dict) and item.get("map")
    ]


def aggregate_counts(inventory: dict[str, Any], key: str) -> dict[str, int]:
    counts = dict_or_empty(dict_or_empty(inventory.get("aggregate")).get(key))
    return {
        str(name): int(value)
        for name, value in counts.items()
        if isinstance(value, int) and value > 0
    }


def first_map_with_count(
    maps: list[dict[str, Any]],
    section: str,
    count_key: str,
    class_name: str,
) -> str | None:
    for map_row in maps:
        section_data = dict_or_empty(map_row.get(section))
        counts = dict_or_empty(section_data.get(count_key))
        if int(counts.get(class_name) or 0) > 0:
            return str(map_row["map"]).lower()
    return None


def first_map_with_material(
    maps: list[dict[str, Any]],
    material_name: str,
) -> str | None:
    for map_row in maps:
        materials = dict_or_empty(map_row.get("materials"))
        counts = dict_or_empty(materials.get("surface_counts"))
        if int(counts.get(material_name) or 0) > 0:
            return str(map_row["map"]).lower()
    return None


def shell_env(env: dict[str, str]) -> str:
    return " ".join(
        f"{key}={shlex.quote(value)}" for key, value in sorted(env.items()))


def capture_env(
    *,
    map_name: str,
    profile: str,
    frames: int,
    wait_frames: int,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    env = dict(DEFAULT_ENV)
    env.update(PROFILE_ENV.get(profile, {}))
    if map_name == "start" and profile == "slipgate_material":
        env.update(PROFILE_ENV["start_slipgate_material"])
    env.update({
        "QGE_STREAM_MAP": map_name,
        "QGE_STREAM_FRAMES": str(frames),
        "QGE_STREAM_WAIT_FRAMES": str(wait_frames),
    })
    if extra_env:
        env.update(extra_env)
    return env


def capture_command(env: dict[str, str]) -> str:
    return f"{shell_env(env)} bash {DEFAULT_STREAM_SCRIPT}"


def add_capture_job(
    jobs: list[dict[str, Any]],
    *,
    job_id: str,
    effect_domain: str,
    map_name: str,
    profile: str,
    frames: int,
    wait_frames: int,
    required_evidence: str,
    reason: str,
    target: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> None:
    env = capture_env(
        map_name=map_name,
        profile=profile,
        frames=frames,
        wait_frames=wait_frames,
        extra_env=extra_env,
    )
    jobs.append({
        "id": job_id,
        "kind": "runtime_capture",
        "effect_domain": effect_domain,
        "target": target,
        "map": map_name,
        "profile": profile,
        "required_evidence": required_evidence,
        "reason": reason,
        "env": env,
        "command": capture_command(env),
    })


def build_queue(
    *,
    matrix: dict[str, Any],
    inventory: dict[str, Any],
    frames: int,
    wait_frames: int,
) -> dict[str, Any]:
    map_set = str(
        matrix.get("map_set") or inventory.get("map_set") or
        qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET
    )
    target_maps = qge_map_sets.map_targets_for_set(map_set)
    criteria = criteria_by_id(matrix)
    maps = inventory_maps(inventory)
    jobs: list[dict[str, Any]] = []

    slipgate = criteria.get("slipgate_material", {})
    for map_name in list_or_empty(slipgate.get("missing_maps")):
        if not isinstance(map_name, str):
            continue
        add_capture_job(
            jobs,
            job_id=f"slipgate_material_{map_name}",
            effect_domain="slipgate_material",
            map_name=map_name,
            profile="slipgate_material",
            frames=frames,
            wait_frames=wait_frames,
            required_evidence="material_slipgate_phase_count > 0",
            reason="inventory map has teleport/slipgate surfaces without map-matched runtime slipgate phase evidence",
        )

    if criterion_blocked(criteria, "enemy_classes"):
        enemy_targets = [
            str(name) for name in list_or_empty(
                criteria.get("enemy_classes", {}).get("missing_classes"))
            if isinstance(name, str)
        ]
        if not enemy_targets:
            enemy_targets = sorted(aggregate_counts(
                inventory, "monster_class_counts"))
        for class_name in sorted(enemy_targets):
            map_name = first_map_with_count(
                maps, "entity", "monster_class_counts", class_name)
            if not map_name:
                continue
            add_capture_job(
                jobs,
                job_id=f"enemy_class_{class_name}_{map_name}",
                effect_domain="enemy_class",
                target=class_name,
                map_name=map_name,
                profile="enemy_class",
                frames=max(frames, 8),
                wait_frames=max(wait_frames, 45),
                extra_env={
                    "QGE_NOESIS_ASSIST": "2",
                    "QGE_NOESIS_AUTONOMOUS": "1",
                    "QGE_NOESIS_TARGET_CLASS": class_name,
                    "QGE_STREAM_SKILL": "2",
                },
                required_evidence=f"class-tied AI/combat evidence for {class_name}",
                reason="discovered monster class lacks class-tied runtime or Noesis evidence",
            )

    if criterion_blocked(criteria, "material_classes"):
        material_counts = aggregate_counts(inventory, "material_surface_counts")
        material_targets = [
            str(name) for name in list_or_empty(
                criteria.get("material_classes", {}).get(
                    "missing_material_classes"))
            if isinstance(name, str)
        ]
        if not material_targets:
            material_targets = sorted(
                key for key in material_counts
                if key not in {"total"} and material_counts[key] > 0
            )
        for material_name in sorted(material_targets):
            map_name = first_map_with_material(maps, material_name)
            if not map_name:
                continue
            add_capture_job(
                jobs,
                job_id=f"material_class_{material_name}_{map_name}",
                effect_domain="material_class",
                target=material_name,
                map_name=map_name,
                profile="material_class",
                frames=frames,
                wait_frames=wait_frames,
                required_evidence=f"runtime material evidence for {material_name}",
                reason="discovered material class lacks complete runtime material evidence",
            )

    if criterion_blocked(criteria, "weapon_projectile_classes"):
        weapon_targets = [
            str(name) for name in list_or_empty(
                criteria.get("weapon_projectile_classes", {}).get(
                    "missing_weapon_classes"))
            if isinstance(name, str)
        ]
        if not weapon_targets:
            weapon_targets = sorted(aggregate_counts(
                inventory, "weapon_pickup_counts"))
        for class_name in sorted(weapon_targets):
            map_name = first_map_with_count(
                maps, "entity", "weapon_pickup_counts", class_name)
            if not map_name:
                continue
            add_capture_job(
                jobs,
                job_id=f"weapon_projectile_{class_name}_{map_name}",
                effect_domain="weapon_projectile_class",
                target=class_name,
                map_name=map_name,
                profile="weapon_projectile_class",
                frames=max(frames, 72),
                wait_frames=max(wait_frames, 90),
                extra_env={"QGE_NOESIS_WEAPON_TARGET": class_name},
                required_evidence=f"weapon/projectile authority and replay evidence for {class_name}",
                reason="discovered weapon pickup class lacks class-tied projectile/weapon evidence",
            )

    if criterion_blocked(criteria, "particles_sprites"):
        add_capture_job(
            jobs,
            job_id="particles_sprites_e1m1",
            effect_domain="particles_sprites",
            target="sprites_particles_explosions_gibs_pickups",
            map_name="e1m1" if "e1m1" in target_maps else target_maps[0],
            profile="particles_sprites",
            frames=max(frames, 8),
            wait_frames=max(wait_frames, 45),
            required_evidence="sprite/particle/explosion/gib ownership counters",
            reason="sprite particle explosion gib and pickup runtime effect coverage is missing",
        )

    if criterion_blocked(criteria, "noesis_replay"):
        jobs.append({
            "id": "noesis_replay_matrix_join",
            "kind": "postprocess_join",
            "effect_domain": "noesis_replay",
            "required_evidence": "per-map Noesis route/combat plus replay joins",
            "reason": "Noesis/replay evidence is not joined to every map and effect class",
            "command": (
                "python3 tools/qge_shareware_effects_matrix.py "
                "--map-set quake_shareware_episode1"
            ),
        })

    if criterion_blocked(criteria, "footage"):
        jobs.append({
            "id": "shareware_effects_footage_manifest",
            "kind": "postprocess_manifest",
            "effect_domain": "footage",
            "required_evidence": "matrix-backed real-frame footage manifest",
            "reason": "release footage manifest is missing",
            "command": (
                "echo QGE_SHAREWARE_EFFECTS_FOOTAGE_MANIFEST_PENDING "
                "build_matrix_backed_real_frame_manifest"
            ),
        })

    status = "pending" if jobs else "complete"
    return {
        "schema": QUEUE_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "map_set": map_set,
        "target_maps": target_maps,
        "source_matrix_status": matrix.get("status"),
        "source_matrix_failed_criterion_count": matrix.get(
            "failed_criterion_count"),
        "job_count": len(jobs),
        "runtime_capture_job_count": sum(
            1 for job in jobs if job.get("kind") == "runtime_capture"),
        "jobs": jobs,
        "completion_note": (
            "Run queued captures, regenerate qge_trace_summary outputs, "
            "then rerun qge_shareware_effects_matrix.py."
        ),
    }


def build_icc_evidence(queue: dict[str, Any], path: Path) -> dict[str, Any]:
    ready = queue.get("status") == "complete"
    return {
        "schema": ICC_SCHEMA,
        "runtime_backend": "qge_shareware_effects_capture_queue",
        "completion_reason": (
            "qge_shareware_effects_capture_queue_complete"
            if ready else "qge_shareware_effects_capture_queue_pending"
        ),
        "runtime_backend_scope_map_set": queue.get("map_set"),
        "shareware_effects_capture_queue_file": str(path),
        "qge_shareware_effects_capture_queue.json": str(path),
        "shareware_effects_capture_queue_status": queue.get("status"),
        "shareware_effects_capture_queue_job_count": queue.get("job_count"),
        "shareware_effects_runtime_capture_job_count": queue.get(
            "runtime_capture_job_count"),
    }


def markdown_report(queue: dict[str, Any]) -> str:
    lines = [
        "# QGE Shareware Effects Capture Queue",
        "",
        f"- `status`: `{queue.get('status')}`",
        f"- `map_set`: `{queue.get('map_set')}`",
        f"- `jobs`: `{queue.get('job_count')}`",
        "",
        "| Job | Kind | Map | Effect | Target |",
        "|---|---|---|---|---|",
    ]
    for job in queue.get("jobs", []):
        lines.append(
            f"| `{job.get('id')}` | `{job.get('kind')}` | "
            f"`{job.get('map') or ''}` | `{job.get('effect_domain')}` | "
            f"`{job.get('target') or ''}` |"
        )
    lines.append("")
    return "\n".join(lines)


def script_lines(queue: dict[str, Any]) -> list[str]:
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        'repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"',
        'cd "$repo_root"',
        f"echo QGE_SHAREWARE_EFFECTS_CAPTURE_QUEUE jobs={queue.get('job_count')}",
    ]
    for job in queue.get("jobs", []):
        command = job.get("command")
        if not isinstance(command, str) or not command:
            continue
        lines.extend([
            f"echo QGE_SHAREWARE_EFFECTS_CAPTURE_JOB {shlex.quote(str(job.get('id')))}",
            'sleep "${QGE_SHAREWARE_EFFECTS_QUEUE_SLEEP_SECONDS:-8}"',
            command,
        ])
    return lines


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_EFFECTS_ROOT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--script", type=Path)
    parser.add_argument("--icc-json", type=Path)
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--wait-frames", type=int, default=35)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    matrix_path = (
        args.matrix or
        latest_file(args.out_root, "qge_shareware_effects_matrix.json")
    )
    inventory_path = (
        args.inventory or
        latest_file(args.out_root, "qge_shareware_effects_inventory.json")
    )
    if matrix_path is None:
        raise SystemExit("no shareware effects matrix found")
    if inventory_path is None:
        raise SystemExit("no shareware effects inventory found")
    run_dir = args.out_root / datetime.now(timezone.utc).strftime(
        "%Y%m%d-%H%M%S")
    out_path = args.out or run_dir / "qge_shareware_effects_capture_queue.json"
    markdown_path = args.markdown or out_path.with_name(
        "qge_shareware_effects_capture_queue.md")
    script_path = args.script or out_path.with_name(
        "run_qge_shareware_effects_capture_queue.sh")
    icc_path = args.icc_json or out_path.with_name(
        "qge_shareware_effects_capture_queue_icc_evidence.json")

    queue = build_queue(
        matrix=load_json(matrix_path),
        inventory=load_json(inventory_path),
        frames=max(1, args.frames),
        wait_frames=max(1, args.wait_frames),
    )
    queue["source_matrix_file"] = str(matrix_path)
    queue["source_inventory_file"] = str(inventory_path)
    write_json(out_path, queue)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown_report(queue), encoding="utf-8")
    script_path.write_text("\n".join(script_lines(queue)) + "\n",
                           encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | 0o111)
    write_json(icc_path, build_icc_evidence(queue, out_path))
    print(f"QGE_SHAREWARE_EFFECTS_CAPTURE_QUEUE {out_path}")
    print(f"QGE_SHAREWARE_EFFECTS_CAPTURE_QUEUE_MARKDOWN {markdown_path}")
    print(f"QGE_SHAREWARE_EFFECTS_CAPTURE_QUEUE_SCRIPT {script_path}")
    print(f"QGE_SHAREWARE_EFFECTS_CAPTURE_QUEUE_ICC {icc_path}")
    return 0 if queue.get("status") == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
