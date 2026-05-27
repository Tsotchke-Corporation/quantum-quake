#!/usr/bin/env python3
"""Build a runnable capture queue from QGE full-game map coverage."""

from __future__ import annotations

import argparse
import json
import shlex
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_breadth_evidence  # noqa: E402
import qge_full_game_route_contracts  # noqa: E402
import qge_map_sets  # noqa: E402

DEFAULT_ENV = {
    "QGE_HARNESS_FRAMES": "4",
    "QGE_HARNESS_WAIT_FRAMES": "35",
    "QGE_STREAM_LAUNCH": "direct",
    "QGE_STREAM_MOUSE": "0",
    "QGE_STREAM_PLAYER": "noesis",
    "QGE_STREAM_ACTIVATE": "0",
    "QGE_STREAM_TRACE": "1",
    "QGE_STREAM_FIRE_MIN_FRAMES": "4",
    "QGE_NOESIS_MIN_CAPTURE_WAIT": "100",
    "QGE_HARNESS_SOUND": "1",
    "QGE_HARNESS_FIRE_TEST": "1",
    "QGE_HARNESS_SPRITE_TEST": "1",
    "QGE_HARNESS_PARTICLES": "1",
    "QGE_HARNESS_SND_QUANTUM": "2",
    "QGE_HARNESS_SND_QUANTUM_SOURCE_AUTHORITY": "1",
    "QGE_HARNESS_PHYSICS_AUTHORITATIVE": "1",
    "QGE_HARNESS_FORCE_WORLD_METRICS": "1",
    "QGE_RENDER_RES": "1024",
    "QGE_RENDER_THRESHOLD": "0.001",
    "QGE_RENDER_EDGE_GAIN": "0",
    "QGE_RENDER_MATERIAL_GAIN": "0.18",
    "QGE_RENDER_EDGE_SAMPLES": "0",
}
SPECIAL_ROUTE_MAPS = qge_full_game_route_contracts.SPECIAL_ROUTE_MAPS
START_HUB_ROUTE_MAPS = qge_full_game_route_contracts.START_HUB_ROUTE_MAPS
DEFERRED_ROUTE_MAPS = qge_full_game_route_contracts.DEFERRED_ROUTE_MAPS
START_HUB_ROUTE_ENV = {
    "QGE_NOESIS_PLAN": "start-hub-route",
    "QGE_NOESIS_SCRIPTED": "1",
    "QGE_NOESIS_REQUIRE_COMBAT": "0",
    "QGE_NOESIS_MIN_LOG_PHASES": "2",
    "QGE_NOESIS_MIN_ROUTE_DISTANCE": "16",
    "QGE_NOESIS_START_WAIT": "24",
    "QGE_NOESIS_ASSIST": "0",
    "QGE_STREAM_FIRE_MIN_START_WAIT": "0",
}
BASE_AUTHORITY_DOMAINS = qge_full_game_route_contracts.BASE_AUTHORITY_DOMAINS
ROUTE_CONTRACT_SCHEMA = qge_full_game_route_contracts.ROUTE_CONTRACT_SCHEMA
DEFAULT_ASSET_ROOT = REPO_ROOT / "assets" / "id1"
REGISTERED_FULL_GAME_PROGRESS_SCHEMA = "qge.registered_full_game_progress.v0"
QUAKE_BSP_VERSION = 29
BSP_LUMP_COUNT = 15
BSP_HEADER_SIZE = 4 + BSP_LUMP_COUNT * 8
BSP_LUMP_ENTITIES = 0
BSP_LUMP_MODELS = 14
BSP_DMODEL_SIZE = 64


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


def resolve_source_path(path: Path) -> Path:
    if path.is_dir():
        candidates = [
            path / "publication_manifest.json",
            path / "breadth_evidence.json",
            path / "resource" / "qge_full_game_map_coverage.json",
            path / "full_game_map_coverage.json",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    return path


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def pak_directory_records(path: Path) -> list[dict[str, Any]]:
    data = path.read_bytes()
    if len(data) < 12:
        raise ValueError(f"{path} is too short to be a PAK file")
    magic, directory_offset, directory_size = struct.unpack("<4sII", data[:12])
    if magic != b"PACK":
        raise ValueError(f"{path} is not a Quake PAK file")
    if directory_size % 64 != 0:
        raise ValueError(f"{path} has an invalid PAK directory size")
    directory_end = directory_offset + directory_size
    if directory_offset > len(data) or directory_end > len(data):
        raise ValueError(f"{path} has an out-of-bounds PAK directory")
    records = []
    for offset in range(directory_offset, directory_end, 64):
        raw_name = data[offset:offset + 56].split(b"\0", 1)[0]
        name = raw_name.decode("ascii", "ignore").replace("\\", "/").lower()
        file_offset, file_size = struct.unpack("<II", data[offset + 56:offset + 64])
        if name:
            if file_offset > len(data) or file_offset + file_size > len(data):
                raise ValueError(f"{path}:{name} has an out-of-bounds PAK entry")
            records.append({
                "name": name,
                "file_offset": file_offset,
                "file_size": file_size,
            })
    return records


def pak_directory_entries(path: Path) -> list[str]:
    return [record["name"] for record in pak_directory_records(path)]


def bsp_validation_report(data: bytes) -> dict[str, Any]:
    if len(data) < 4:
        return {
            "valid": False,
            "format": "quake_bsp",
            "version": None,
            "reason": "bsp_too_short",
        }
    version = struct.unpack("<i", data[:4])[0]
    if version != QUAKE_BSP_VERSION:
        return {
            "valid": False,
            "format": "quake_bsp",
            "version": version,
            "reason": "unsupported_bsp_version",
        }
    if len(data) < BSP_HEADER_SIZE:
        return {
            "valid": False,
            "format": "quake_bsp",
            "version": version,
            "reason": "bsp_header_truncated",
        }
    lumps = []
    for index in range(BSP_LUMP_COUNT):
        offset = 4 + index * 8
        file_offset, file_length = struct.unpack("<ii", data[offset:offset + 8])
        lumps.append((file_offset, file_length))
        if file_offset < 0 or file_length < 0:
            return {
                "valid": False,
                "format": "quake_bsp",
                "version": version,
                "reason": "negative_lump_bounds",
                "lump": index,
            }
        if file_offset > len(data) or file_offset + file_length > len(data):
            return {
                "valid": False,
                "format": "quake_bsp",
                "version": version,
                "reason": "lump_out_of_bounds",
                "lump": index,
            }
    entities_length = lumps[BSP_LUMP_ENTITIES][1]
    models_length = lumps[BSP_LUMP_MODELS][1]
    if entities_length <= 0:
        return {
            "valid": False,
            "format": "quake_bsp",
            "version": version,
            "reason": "missing_entities_lump",
        }
    if models_length < BSP_DMODEL_SIZE or models_length % BSP_DMODEL_SIZE != 0:
        return {
            "valid": False,
            "format": "quake_bsp",
            "version": version,
            "reason": "invalid_models_lump_size",
        }
    return {
        "valid": True,
        "format": "quake_bsp",
        "version": version,
        "reason": "valid_quake_bsp29",
        "lump_count": BSP_LUMP_COUNT,
        "model_count": models_length // BSP_DMODEL_SIZE,
    }


def is_valid_bsp_payload(data: bytes) -> bool:
    return bool(bsp_validation_report(data).get("valid"))


def available_bsp_maps(asset_root: Path) -> set[str]:
    maps: set[str] = set()
    if not asset_root.is_dir():
        return maps
    loose_maps = asset_root / "maps"
    if loose_maps.is_dir():
        for path in loose_maps.glob("*.bsp"):
            if is_valid_bsp_payload(path.read_bytes()):
                maps.add(path.stem.lower())
    for pak_path in sorted(asset_root.glob("pak*.pak")):
        data = pak_path.read_bytes()
        for record in pak_directory_records(pak_path):
            entry = record["name"]
            if entry.startswith("maps/") and entry.endswith(".bsp"):
                start = int(record["file_offset"])
                end = start + int(record["file_size"])
                if is_valid_bsp_payload(data[start:end]):
                    maps.add(Path(entry).stem.lower())
    return maps


def existing_matrix_sources(data: dict[str, Any]) -> list[str]:
    schema = data.get("schema")
    if schema == REGISTERED_FULL_GAME_PROGRESS_SCHEMA:
        sources = []
        for row in list_or_empty(data.get("target_map_progress")):
            if not isinstance(row, dict):
                continue
            if row.get("status") != "ready":
                continue
            source = row.get("selected_matrix_file")
            if isinstance(source, str) and source:
                sources.append(source)
        return sources
    if schema == "qge.breadth_evidence.v0":
        sources = []
        for run in list_or_empty(data.get("matrix_runs")):
            if not isinstance(run, dict):
                continue
            source = run.get("source_path") or run.get("matrix_file")
            if isinstance(source, str) and source:
                sources.append(source)
        return sources
    if schema == "qge.publication_pack.v0":
        source_inputs = dict_or_empty(data.get("source_inputs"))
        breadth_path = source_inputs.get("breadth_evidence")
        if not isinstance(breadth_path, str) or not breadth_path:
            return []
        path = Path(breadth_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            return []
        try:
            return existing_matrix_sources(load_json(path))
        except (OSError, ValueError):
            return []
    return []


def coverage_from_registered_progress(data: dict[str, Any]) -> dict[str, Any]:
    map_set = str(
        data.get("map_set") or qge_map_sets.DEFAULT_FULL_GAME_MAP_SET
    )
    rows = [
        row for row in list_or_empty(data.get("target_map_progress"))
        if isinstance(row, dict) and row.get("map")
    ]
    ready_maps = [
        str(row["map"]) for row in rows if row.get("status") == "ready"
    ]
    missing_rows = [row for row in rows if row.get("status") != "ready"]
    missing_maps = [str(row["map"]) for row in missing_rows]
    target_maps = qge_map_sets.map_targets_for_set(map_set)
    target_map_count = int(
        data.get("target_map_count") or len(target_maps)
    )
    return {
        "schema": "qge.full_game_map_coverage.v0",
        "status": "complete" if not missing_maps else "partial",
        "map_set": map_set,
        "map_scope": (
            data.get("map_scope") or qge_map_sets.map_set_scope_label(map_set)
        ),
        "registered_full_game_scope": (
            qge_map_sets.is_registered_full_game_map_set(map_set)
        ),
        "shareware_episode_one_scope": (
            qge_map_sets.is_shareware_episode_one_map_set(map_set)
        ),
        "target_map_count": target_map_count,
        "covered_map_count": len(ready_maps),
        "missing_map_count": len(missing_maps),
        "covered_maps": ready_maps,
        "missing_maps": missing_maps,
        "source_progress_schema": data.get("schema"),
        "source_progress_status": data.get("status"),
        "source_progress_next_blocker": data.get("next_blocker"),
        "source_progress_ready_map_count": data.get("ready_map_count"),
        "source_progress_asset_missing_map_count": (
            data.get("asset_missing_map_count")),
        "source_progress_capture_needed_map_count": (
            data.get("capture_needed_map_count")),
        "source_progress_asset_blocked_maps": (
            data.get("asset_blocked_maps", [])),
        "source_progress_capture_needed_maps": (
            data.get("capture_needed_maps", [])),
    }


def coverage_from_data(data: dict[str, Any]) -> dict[str, Any]:
    schema = data.get("schema")
    if schema == "qge.full_game_map_coverage.v0":
        return data
    if schema == REGISTERED_FULL_GAME_PROGRESS_SCHEMA:
        return coverage_from_registered_progress(data)
    if schema == "qge.breadth_evidence.v0":
        coverage = data.get("full_game_coverage")
        if not isinstance(coverage, dict):
            aggregate = dict_or_empty(data.get("aggregate"))
            coverage = aggregate.get("full_game_coverage")
        if isinstance(coverage, dict):
            return coverage
        aggregate = dict_or_empty(data.get("aggregate"))
        return qge_breadth_evidence.build_full_game_map_coverage(
            list_or_empty(aggregate.get("maps")))
    if schema == "qge.publication_pack.v0":
        runtime = dict_or_empty(data.get("runtime_summary"))
        coverage = runtime.get("full_game_map_coverage")
        if isinstance(coverage, dict):
            return coverage
        return qge_breadth_evidence.build_full_game_map_coverage(
            list_or_empty(runtime.get("breadth_maps")))
    raise ValueError(f"unsupported source schema: {schema!r}")


def shell_env(env: dict[str, str]) -> str:
    return " ".join(
        f"{key}={shlex.quote(value)}" for key, value in sorted(env.items()))


def harness_command(env: dict[str, str]) -> str:
    return f"{shell_env(env)} bash tools/quake_graphics_harness.sh"


def queue_environment(args: argparse.Namespace, map_name: str) -> dict[str, str]:
    env = dict(DEFAULT_ENV)
    env.update({
        "QGE_HARNESS_MAP": map_name,
        "QGE_HARNESS_FRAMES": str(args.frames),
        "QGE_HARNESS_WAIT_FRAMES": str(args.wait_frames),
        "QGE_STREAM_TRACE": "1" if args.trace else "0",
    })
    if not getattr(args, "authority_smoke", True):
        env.update({
            "QGE_HARNESS_SOUND": "0",
            "QGE_HARNESS_FIRE_TEST": "0",
            "QGE_HARNESS_SPRITE_TEST": "0",
            "QGE_HARNESS_PARTICLES": "0",
            "QGE_HARNESS_SND_QUANTUM": "1",
            "QGE_HARNESS_SND_QUANTUM_SOURCE_AUTHORITY": "0",
            "QGE_HARNESS_PHYSICS_AUTHORITATIVE": "0",
        })
    env["QGE_HARNESS_FORCE_WORLD_METRICS"] = (
        "1" if args.force_world_metrics else "0"
    )
    if map_name in START_HUB_ROUTE_MAPS:
        env.update(START_HUB_ROUTE_ENV)
    for item in args.env or []:
        key, value = item.split("=", 1)
        env[key] = value
    return env


def route_profile_for_map(map_name: str) -> str:
    return qge_full_game_route_contracts.route_profile_for_map(map_name)


def map_episode_and_slot(map_name: str) -> tuple[str, int | None]:
    return qge_full_game_route_contracts.map_episode_and_slot(map_name)


def route_contract_for_map(
    map_name: str,
    *,
    map_set: str | None = None,
) -> dict[str, Any]:
    return qge_full_game_route_contracts.route_contract_for_map(
        map_name,
        map_set=map_set,
    )


def route_contracts_for_map_set(map_set: str) -> dict[str, dict[str, Any]]:
    return {
        map_name: route_contract_for_map(map_name, map_set=map_set)
        for map_name in qge_map_sets.map_targets_for_set(map_set)
    }


def selected_missing_maps(
    coverage: dict[str, Any],
    limit: int | None,
    special_maps_last: bool = True,
) -> list[str]:
    missing = [
        item for item in list_or_empty(coverage.get("missing_maps"))
        if isinstance(item, str)
    ]
    if special_maps_last:
        missing = (
            [name for name in missing if name not in DEFERRED_ROUTE_MAPS] +
            [name for name in missing if name in DEFERRED_ROUTE_MAPS]
        )
    if limit is not None:
        missing = missing[:limit]
    return missing


def ordered_missing_maps(
    coverage: dict[str, Any],
    special_maps_last: bool = True,
) -> list[str]:
    return selected_missing_maps(coverage, None, special_maps_last)


def queue_status(
    *,
    missing_maps: list[str],
    jobs: list[dict[str, Any]],
    asset_unavailable_missing_maps: list[str],
    include_unavailable_assets: bool,
) -> str:
    if not missing_maps:
        return "complete"
    if jobs:
        if asset_unavailable_missing_maps and not include_unavailable_assets:
            return "pending_partial_asset_blocked"
        return "pending"
    if asset_unavailable_missing_maps:
        return "blocked_asset_unavailable"
    return "blocked_no_queueable_maps"


def reproduction_inputs(
    args: argparse.Namespace,
    *,
    source_path: Path,
    asset_root: Path,
    include_unavailable_assets: bool,
    special_maps_last: bool,
) -> dict[str, Any]:
    return {
        "source": str(source_path),
        "asset_root": str(asset_root),
        "limit": getattr(args, "limit", None),
        "frames": int(getattr(args, "frames", 4)),
        "wait_frames": int(getattr(args, "wait_frames", 35)),
        "trace": bool(getattr(args, "trace", True)),
        "special_maps_last": special_maps_last,
        "authority_smoke": bool(getattr(args, "authority_smoke", True)),
        "force_world_metrics": bool(
            getattr(args, "force_world_metrics", True)),
        "include_unavailable_assets": include_unavailable_assets,
        "env": list(getattr(args, "env", None) or []),
    }


def build_queue(args: argparse.Namespace) -> dict[str, Any]:
    source_path = resolve_source_path(args.source)
    data = load_json(source_path)
    coverage = coverage_from_data(data)
    special_maps_last = getattr(args, "special_maps_last", True)
    missing_maps = ordered_missing_maps(coverage, special_maps_last)
    asset_root = Path(getattr(args, "asset_root", DEFAULT_ASSET_ROOT))
    include_unavailable_assets = bool(
        getattr(args, "include_unavailable_assets", False)
    )
    available_maps = available_bsp_maps(asset_root)
    if include_unavailable_assets:
        queueable_missing_maps = list(missing_maps)
        asset_available_missing_maps = [
            name for name in missing_maps
            if name.lower() in available_maps
        ]
        asset_unavailable_missing_maps = [
            name for name in missing_maps
            if name.lower() not in available_maps
        ]
    else:
        asset_available_missing_maps = [
            name for name in missing_maps
            if name.lower() in available_maps
        ]
        queueable_missing_maps = list(asset_available_missing_maps)
        asset_unavailable_missing_maps = [
            name for name in missing_maps
            if name.lower() not in available_maps
        ]
    if args.limit is not None:
        queueable_missing_maps = queueable_missing_maps[:args.limit]
    existing_sources = existing_matrix_sources(data)
    map_set = str(
        coverage.get("map_set") or
        qge_map_sets.DEFAULT_FULL_GAME_MAP_SET
    )
    route_contracts = route_contracts_for_map_set(map_set)
    target_maps = qge_map_sets.map_targets_for_set(map_set)
    missing_route_contract_maps = sorted(set(
        [name for name in target_maps if name not in route_contracts] +
        [name for name in missing_maps if name not in route_contracts]
    ))
    jobs = []
    for index, map_name in enumerate(queueable_missing_maps, start=1):
        env = queue_environment(args, map_name)
        route_contract = route_contracts.get(map_name)
        if not route_contract:
            route_contract = route_contract_for_map(
                map_name,
                map_set=map_set,
            )
        jobs.append({
            "index": index,
            "map": map_name,
            "route_profile": route_contract["route_profile"],
            "route_contract": route_contract,
            "status": "pending_capture",
            "environment": env,
            "command": ["bash", "tools/quake_graphics_harness.sh"],
            "shell_command": harness_command(env),
        })
    target_after_queue = int(coverage.get("covered_map_count", 0) or 0) + len(jobs)
    target_map_count = int(coverage.get("target_map_count", 0) or 0)
    status = queue_status(
        missing_maps=missing_maps,
        jobs=jobs,
        asset_unavailable_missing_maps=asset_unavailable_missing_maps,
        include_unavailable_assets=include_unavailable_assets,
    )
    return {
        "schema": "qge.full_game_capture_queue.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path),
        "source_schema": data.get("schema"),
        "status": status,
        "map_set": map_set,
        "map_scope": qge_map_sets.map_set_scope_label(map_set),
        "special_maps_last": special_maps_last,
        "special_route_maps": sorted(SPECIAL_ROUTE_MAPS),
        "start_hub_route_maps": sorted(START_HUB_ROUTE_MAPS),
        "route_contract_schema": ROUTE_CONTRACT_SCHEMA,
        "reproduction": reproduction_inputs(
            args,
            source_path=source_path,
            asset_root=asset_root,
            include_unavailable_assets=include_unavailable_assets,
            special_maps_last=special_maps_last,
        ),
        "route_contract_map_count": len(route_contracts),
        "route_contracts_complete": not missing_route_contract_maps,
        "missing_route_contract_maps": missing_route_contract_maps,
        "route_contracts": route_contracts,
        "asset_root": str(asset_root),
        "asset_filter_enabled": not include_unavailable_assets,
        "asset_inventory_status": (
            "present" if asset_root.is_dir() else "missing_asset_root"
        ),
        "available_asset_maps": sorted(
            name for name in available_maps
            if name in target_maps
        ),
        "asset_available_missing_maps": asset_available_missing_maps,
        "asset_available_missing_count": len(asset_available_missing_maps),
        "asset_unavailable_missing_maps": asset_unavailable_missing_maps,
        "asset_unavailable_missing_count": len(asset_unavailable_missing_maps),
        "coverage_before": coverage,
        "source_progress_status": coverage.get("source_progress_status"),
        "source_progress_next_blocker": coverage.get(
            "source_progress_next_blocker"),
        "source_progress_capture_needed_maps": coverage.get(
            "source_progress_capture_needed_maps", []),
        "source_progress_asset_blocked_maps": coverage.get(
            "source_progress_asset_blocked_maps", []),
        "existing_matrix_sources": existing_sources,
        "queue_job_count": len(jobs),
        "target_map_count": target_map_count,
        "covered_map_count_before": coverage.get("covered_map_count"),
        "covered_map_count_after_queue": target_after_queue,
        "remaining_map_count_after_queue": max(
            target_map_count - target_after_queue, 0),
        "jobs": jobs,
        "post_capture": {
            "map_set": map_set,
            "breadth_min_runs": len(existing_sources) + len(jobs),
            "breadth_min_maps": target_after_queue,
            "command": (
                "tools/qge_breadth_evidence.py with every existing matrix "
                "plus every successful queued capture directory"
            ),
        },
        "limits": [
            "This queue does not prove coverage until the generated captures run.",
            "Every queued harness output must still pass the strict breadth gates.",
            "Maps with route_profile=start_hub_route_authority_smoke are ordered last but keep projectile authority required.",
            "Maps with route_profile=special_route_required are ordered last because they need noncombat/endgame-specific evidence, not a weakened Moonlab claim.",
            "Maps absent from the local asset PAK/loose BSP inventory are not queued unless --include-unavailable-assets is set.",
            "Do not claim full-game map coverage until remaining_map_count_after_queue is zero and the rebuilt breadth artifact is complete.",
        ],
    }


def script_lines(queue: dict[str, Any]) -> list[str]:
    existing = [
        item for item in list_or_empty(queue.get("existing_matrix_sources"))
        if isinstance(item, str)
    ]
    jobs = [
        item for item in list_or_empty(queue.get("jobs"))
        if isinstance(item, dict)
    ]
    post_capture = dict_or_empty(queue.get("post_capture"))
    map_set = str(
        post_capture.get("map_set") or
        queue.get("map_set") or
        qge_map_sets.DEFAULT_FULL_GAME_MAP_SET
    )
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        f"repo_root={shlex.quote(str(REPO_ROOT))}",
        'cd "$repo_root"',
        "",
        "capture_dirs=()",
        "",
    ]
    for job in jobs:
        map_name = str(job.get("map"))
        route_contract = dict_or_empty(job.get("route_contract"))
        route_profile = str(job.get("route_profile") or "")
        route_class = str(route_contract.get("map_class") or "")
        env = {
            key: str(value)
            for key, value in dict_or_empty(job.get("environment")).items()
        }
        lines.extend([
            f"echo QGE_FULL_GAME_CAPTURE_QUEUE_MAP {shlex.quote(map_name)}",
            (
                "echo QGE_FULL_GAME_CAPTURE_ROUTE_PROFILE "
                f"{shlex.quote(route_profile)}"
            ),
            (
                "echo QGE_FULL_GAME_CAPTURE_ROUTE_CLASS "
                f"{shlex.quote(route_class)}"
            ),
            "capture_output=\"$(",
            f"  {harness_command(env)}",
            ")\"",
            'printf "%s\\n" "$capture_output"',
            "capture_dir=\"$(",
            '  printf "%s\\n" "$capture_output" |',
            "  awk '/QGE_GRAPHICS_HARNESS_DONE / {print $2}' |",
            "  tail -n 1",
            ")\"",
            'if [[ -z "$capture_dir" || ! -d "$capture_dir" ]]; then',
            f"  echo \"capture failed for {map_name}\" >&2",
            "  exit 1",
            "fi",
            'capture_dirs+=("$capture_dir")',
            "",
        ])
    lines.extend([
        "breadth_args=()",
    ])
    for source in existing:
        lines.append(f"breadth_args+=(--matrix {shlex.quote(source)})")
    lines.extend([
        'for capture_dir in "${capture_dirs[@]}"; do',
        '  breadth_args+=(--matrix "$capture_dir")',
        "done",
        "",
        'if (( ${#breadth_args[@]} > 0 )); then',
        "  python3 tools/qge_breadth_evidence.py \\",
        '    "${breadth_args[@]}" \\',
        f"    --map-set {shlex.quote(map_set)} \\",
        f"    --min-runs {int(post_capture.get('breadth_min_runs', 1) or 1)} \\",
        f"    --min-maps {int(post_capture.get('breadth_min_maps', 1) or 1)}",
        "fi",
        "",
    ])
    return lines


def markdown_report(queue: dict[str, Any]) -> str:
    coverage = dict_or_empty(queue.get("coverage_before"))
    map_set = str(queue.get("map_set") or coverage.get("map_set") or "")
    map_scope = str(queue.get("map_scope") or coverage.get("map_scope") or "")
    if qge_map_sets.is_shareware_episode_one_map_set(map_set):
        title = "# QGE Shareware Episode 1 Capture Queue"
    else:
        title = "# QGE Full Game Capture Queue"
    lines = [
        title,
        "",
        f"Status: {queue['status']}",
        f"Scope: `{map_scope or qge_map_sets.map_set_scope_label(map_set)}`",
        f"Source: `{queue['source_path']}`",
        "",
        "| Map Set | Covered Before | Jobs | Covered After Queue | Remaining |",
        "| --- | ---: | ---: | ---: | ---: |",
        (
            f"| {coverage.get('map_set')} | "
            f"{queue.get('covered_map_count_before')} / "
            f"{queue.get('target_map_count')} | "
            f"{queue.get('queue_job_count')} | "
            f"{queue.get('covered_map_count_after_queue')} / "
            f"{queue.get('target_map_count')} | "
            f"{queue.get('remaining_map_count_after_queue')} |"
        ),
        "",
        (
            f"Asset root: `{queue.get('asset_root')}` "
            f"({queue.get('asset_inventory_status')}, "
            f"filter={'on' if queue.get('asset_filter_enabled') else 'off'})"
        ),
        (
            f"Asset-unavailable missing maps: "
            f"{queue.get('asset_unavailable_missing_count')}"
        ),
        (
            f"Route contracts: {queue.get('route_contract_map_count')} "
            f"(complete={queue.get('route_contracts_complete')})"
        ),
    ]
    if queue.get("source_progress_status") is not None:
        lines.extend([
            (
                f"Registered progress source: "
                f"{queue.get('source_progress_status')} "
                f"(next={queue.get('source_progress_next_blocker')})"
            ),
        ])
    lines.extend([
        "",
        "| # | Map | Route Profile | Route Class | Command |",
        "| ---: | --- | --- | --- | --- |",
    ])
    for job in list_or_empty(queue.get("jobs")):
        if not isinstance(job, dict):
            continue
        route_contract = dict_or_empty(job.get("route_contract"))
        lines.append(
            f"| {job.get('index')} | {job.get('map')} | "
            f"{job.get('route_profile')} | "
            f"{route_contract.get('map_class')} | "
            f"`{job.get('shell_command')}` |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_env(value: str) -> str:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--env values must be KEY=VALUE")
    key, _value = value.split("=", 1)
    if not key or any(ch in key for ch in " \t\n="):
        raise argparse.ArgumentTypeError("--env key is invalid")
    return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_out = (
        REPO_ROOT / "diagnostics" / "full_game_capture_queue" /
        stamp / "capture_queue.json"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path,
                        help=(
                            "Coverage JSON, breadth evidence, registered "
                            "full-game progress JSON, or publication pack"
                        ))
    parser.add_argument("--out", type=Path, default=default_out)
    parser.add_argument("--script-out", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--limit", type=int,
                        help="Only queue the first N missing maps")
    parser.add_argument("--frames", type=int, default=4)
    parser.add_argument("--wait-frames", type=int, default=35)
    parser.add_argument("--trace", action=argparse.BooleanOptionalAction,
                        default=True)
    parser.add_argument("--special-maps-last",
                        action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Queue start/end after combat maps because they require special route evidence")
    parser.add_argument("--authority-smoke",
                        action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Enable fire, sprite, particles, sound-source, and projectile authority smoke")
    parser.add_argument("--force-world-metrics",
                        action=argparse.BooleanOptionalAction,
                        default=True)
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSET_ROOT,
                        help="Directory containing loose maps/ and pak*.pak assets")
    parser.add_argument("--include-unavailable-assets",
                        action=argparse.BooleanOptionalAction,
                        default=False,
                        help="Queue maps even when their BSP is absent locally")
    parser.add_argument("--env", action="append", type=parse_env,
                        help="Extra KEY=VALUE environment override")
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if args.limit is not None and args.limit < 0:
        raise ValueError("--limit must be >= 0")
    if args.frames <= 0:
        raise ValueError("--frames must be > 0")
    if args.wait_frames <= 0:
        raise ValueError("--wait-frames must be > 0")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        validate_args(args)
        queue = build_queue(args)
        script_out = (
            args.script_out or args.out.parent / "run_missing_maps.sh"
        )
        write_json(args.out, queue)
        script_out.parent.mkdir(parents=True, exist_ok=True)
        script_out.write_text("\n".join(script_lines(queue)), encoding="utf-8")
        script_out.chmod(script_out.stat().st_mode | 0o111)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(queue), encoding="utf-8")
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_full_game_capture_queue: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_FULL_GAME_CAPTURE_QUEUE {args.out}")
    print(f"QGE_FULL_GAME_CAPTURE_SCRIPT {script_out}")
    if args.markdown:
        print(f"QGE_FULL_GAME_CAPTURE_QUEUE_MARKDOWN {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
