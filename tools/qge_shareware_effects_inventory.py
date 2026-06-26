#!/usr/bin/env python3
"""Inventory shareware Episode 1 effects from real Quake assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_full_game_capture_queue  # noqa: E402
import qge_map_sets  # noqa: E402


DEFAULT_ASSET_ROOT = REPO_ROOT / "assets" / "id1"
DEFAULT_OUT_ROOT = REPO_ROOT / "diagnostics" / "shareware_effects"
INVENTORY_SCHEMA = "qge.shareware_effects_inventory.v0"
ICC_SCHEMA = "qge.icc_evidence.v0"
BSP_LUMP_ENTITIES = 0
BSP_LUMP_MIPTEX = 2
BSP_LUMP_TEXINFO = 6
BSP_LUMP_FACES = 7
BSP_HEADER_SIZE = 4 + 15 * 8
TEXINFO_SIZE = 40
FACE_SIZE = 20


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def bsp_lumps(data: bytes) -> list[tuple[int, int]]:
    validation = qge_full_game_capture_queue.bsp_validation_report(data)
    if not validation.get("valid"):
        raise ValueError(f"invalid BSP payload: {validation.get('reason')}")
    if len(data) < BSP_HEADER_SIZE:
        raise ValueError("BSP header is truncated")
    lumps: list[tuple[int, int]] = []
    for index in range(15):
        offset = 4 + index * 8
        file_offset, file_length = struct.unpack("<ii", data[offset:offset + 8])
        if file_offset < 0 or file_length < 0:
            raise ValueError(f"BSP lump {index} has negative bounds")
        if file_offset > len(data) or file_offset + file_length > len(data):
            raise ValueError(f"BSP lump {index} is out of bounds")
        lumps.append((file_offset, file_length))
    return lumps


def lump_payload(data: bytes, lumps: list[tuple[int, int]], index: int) -> bytes:
    file_offset, file_length = lumps[index]
    return data[file_offset:file_offset + file_length]


def decode_c_string(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii", "ignore")


def parse_entities(payload: bytes) -> list[dict[str, str]]:
    text = payload.split(b"\0", 1)[0].decode("latin-1", "ignore")
    entities: list[dict[str, str]] = []
    for block in re.findall(r"\{([^}]*)\}", text, flags=re.DOTALL):
        pairs = re.findall(r'"([^"]*)"\s*"([^"]*)"', block)
        if not pairs:
            continue
        entity: dict[str, str] = {}
        for key, value in pairs:
            entity[key] = value
        entities.append(entity)
    return entities


def texture_flags(name: str, *, has_fullbright: bool = False) -> dict[str, bool]:
    lower = name.lower()
    warp_prefix = lower.startswith("*") or lower.startswith("!")
    flags = {
        "sky": lower.startswith("sky"),
        "warp": warp_prefix,
        "water": False,
        "lava": False,
        "slime": False,
        "teleport": False,
        "fence": lower.startswith("{"),
        "fullbright": has_fullbright,
        "ordinary": False,
    }
    if warp_prefix:
        if lower.startswith("*lava") or lower.startswith("!lava"):
            flags["lava"] = True
        elif lower.startswith("*slime") or lower.startswith("!slime"):
            flags["slime"] = True
        elif lower.startswith("*tele") or lower.startswith("!tele"):
            flags["teleport"] = True
        else:
            flags["water"] = True
    flags["ordinary"] = not any(
        flags[key]
        for key in ("sky", "warp", "fence")
    )
    return flags


def parse_miptex(payload: bytes) -> list[dict[str, Any]]:
    if len(payload) < 4:
        return []
    count = struct.unpack("<i", payload[:4])[0]
    if count < 0 or 4 + count * 4 > len(payload):
        return []
    textures: list[dict[str, Any]] = []
    for index in range(count):
        texture_offset = struct.unpack(
            "<i", payload[4 + index * 4:8 + index * 4])[0]
        if texture_offset < 0:
            continue
        if texture_offset + 40 > len(payload):
            continue
        raw = payload[texture_offset:texture_offset + 40]
        name = decode_c_string(raw[:16])
        if not name:
            continue
        width, height = struct.unpack("<ii", raw[16:24])
        mip_offsets = list(struct.unpack("<iiii", raw[24:40]))
        has_fullbright = False
        if width > 0 and height > 0 and mip_offsets[0] > 0:
            pixel_start = texture_offset + mip_offsets[0]
            pixel_end = pixel_start + width * height
            if 0 <= pixel_start <= pixel_end <= len(payload):
                has_fullbright = any(byte >= 224
                                     for byte in payload[pixel_start:pixel_end])
        flags = texture_flags(name, has_fullbright=has_fullbright)
        textures.append({
            "index": index,
            "name": name,
            "width": width,
            "height": height,
            "flags": flags,
        })
    return textures


def parse_texinfos(payload: bytes) -> list[dict[str, int]]:
    texinfos: list[dict[str, int]] = []
    for offset in range(0, len(payload) - TEXINFO_SIZE + 1, TEXINFO_SIZE):
        miptex, flags = struct.unpack("<ii", payload[offset + 32:offset + 40])
        texinfos.append({"miptex": miptex, "flags": flags})
    return texinfos


def parse_faces(payload: bytes) -> list[dict[str, int]]:
    faces: list[dict[str, int]] = []
    for offset in range(0, len(payload) - FACE_SIZE + 1, FACE_SIZE):
        texinfo = struct.unpack("<H", payload[offset + 10:offset + 12])[0]
        faces.append({"texinfo": texinfo})
    return faces


def material_counts_from_bsp(
    textures: list[dict[str, Any]],
    texinfos: list[dict[str, int]],
    faces: list[dict[str, int]],
) -> dict[str, Any]:
    by_index = {int(texture["index"]): texture for texture in textures}
    surface_counts = Counter()
    texture_surface_counts: Counter[str] = Counter()
    for face in faces:
        texinfo_index = int(face.get("texinfo", -1))
        if texinfo_index < 0 or texinfo_index >= len(texinfos):
            surface_counts["unknown"] += 1
            continue
        miptex = texinfos[texinfo_index].get("miptex", -1)
        texture = by_index.get(int(miptex))
        if not texture:
            surface_counts["unknown"] += 1
            continue
        texture_surface_counts[str(texture["name"])] += 1
        flags = dict(texture.get("flags") or {})
        surface_counts["total"] += 1
        if flags.get("sky"):
            surface_counts["sky"] += 1
        if flags.get("warp"):
            surface_counts["warp"] += 1
        if flags.get("water"):
            surface_counts["water"] += 1
        if flags.get("lava"):
            surface_counts["lava"] += 1
        if flags.get("slime"):
            surface_counts["slime"] += 1
        if flags.get("teleport"):
            surface_counts["teleport"] += 1
        if flags.get("fence"):
            surface_counts["fence"] += 1
        if flags.get("fullbright"):
            surface_counts["fullbright"] += 1
        if flags.get("ordinary"):
            surface_counts["ordinary"] += 1
    texture_counts = Counter()
    for texture in textures:
        flags = dict(texture.get("flags") or {})
        for key, value in flags.items():
            if value:
                texture_counts[key] += 1
    return {
        "surface_counts": dict(sorted(surface_counts.items())),
        "texture_counts": dict(sorted(texture_counts.items())),
        "texture_surface_counts": dict(sorted(texture_surface_counts.items())),
        "textures": textures,
    }


def count_by_classname(entities: list[dict[str, str]]) -> dict[str, int]:
    counts = Counter(
        entity.get("classname", "")
        for entity in entities
        if entity.get("classname")
    )
    return dict(sorted(counts.items()))


def filter_counts(
    counts: dict[str, int],
    predicate: Any,
) -> dict[str, int]:
    return {
        key: value
        for key, value in counts.items()
        if predicate(key)
    }


def entity_summary(entities: list[dict[str, str]]) -> dict[str, Any]:
    class_counts = count_by_classname(entities)
    trigger_counts = filter_counts(
        class_counts, lambda name: name.startswith("trigger_"))
    route_counts = {
        key: value
        for key, value in class_counts.items()
        if key in {
            "info_player_start",
            "info_player_deathmatch",
            "trigger_changelevel",
            "trigger_teleport",
        }
    }
    referenced_sounds = sorted({
        value
        for entity in entities
        for key, value in entity.items()
        if key.startswith("noise") and value
    })
    return {
        "entity_count": len(entities),
        "classname_counts": class_counts,
        "monster_class_counts": filter_counts(
            class_counts, lambda name: name.startswith("monster_")),
        "weapon_pickup_counts": filter_counts(
            class_counts, lambda name: name.startswith("weapon_")),
        "ammo_pickup_counts": filter_counts(
            class_counts, lambda name: name.startswith("item_") and (
                "shell" in name or "nail" in name or
                "rocket" in name or "cell" in name
            )),
        "item_counts": filter_counts(
            class_counts, lambda name: name.startswith("item_")),
        "trigger_counts": trigger_counts,
        "route_critical_counts": route_counts,
        "ambient_counts": filter_counts(
            class_counts, lambda name: name.startswith("ambient_")),
        "light_counts": filter_counts(
            class_counts, lambda name: name.startswith("light")),
        "referenced_sounds": referenced_sounds,
    }


def parse_bsp_map(data: bytes) -> dict[str, Any]:
    lumps = bsp_lumps(data)
    entities = parse_entities(lump_payload(data, lumps, BSP_LUMP_ENTITIES))
    textures = parse_miptex(lump_payload(data, lumps, BSP_LUMP_MIPTEX))
    texinfos = parse_texinfos(lump_payload(data, lumps, BSP_LUMP_TEXINFO))
    faces = parse_faces(lump_payload(data, lumps, BSP_LUMP_FACES))
    materials = material_counts_from_bsp(textures, texinfos, faces)
    entity_data = entity_summary(entities)
    surface_counts = dict(materials.get("surface_counts") or {})
    texture_counts = dict(materials.get("texture_counts") or {})
    return {
        "bsp_sha256": sha256_bytes(data),
        "bsp_bytes": len(data),
        "entity": entity_data,
        "materials": materials,
        "flags": {
            "has_monsters": bool(entity_data["monster_class_counts"]),
            "has_weapons": bool(entity_data["weapon_pickup_counts"]),
            "has_liquids": any(
                int(surface_counts.get(key, 0)) > 0 or
                int(texture_counts.get(key, 0)) > 0
                for key in ("water", "lava", "slime")
            ),
            "has_warp_surfaces": (
                int(surface_counts.get("warp", 0)) > 0 or
                int(texture_counts.get("warp", 0)) > 0
            ),
            "has_slipgate_surfaces": (
                int(surface_counts.get("teleport", 0)) > 0 or
                int(texture_counts.get("teleport", 0)) > 0
            ),
            "has_sky": (
                int(surface_counts.get("sky", 0)) > 0 or
                int(texture_counts.get("sky", 0)) > 0
            ),
            "has_fullbright_textures": (
                int(surface_counts.get("fullbright", 0)) > 0 or
                int(texture_counts.get("fullbright", 0)) > 0
            ),
            "has_teleport_triggers": (
                int(entity_data["trigger_counts"].get(
                    "trigger_teleport", 0)) > 0
            ),
            "has_changelevel_triggers": (
                int(entity_data["trigger_counts"].get(
                    "trigger_changelevel", 0)) > 0
            ),
        },
    }


def pak_entry_payload(pak_data: bytes, record: dict[str, Any]) -> bytes:
    start = int(record["file_offset"])
    end = start + int(record["file_size"])
    return pak_data[start:end]


def collect_asset_records(asset_root: Path) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, Any],
]:
    map_sources: dict[str, list[dict[str, Any]]] = {}
    asset_counts: Counter[str] = Counter()
    sound_assets: list[str] = []
    sprite_assets: list[str] = []
    model_assets: list[str] = []
    pak_files: list[dict[str, Any]] = []
    loose_maps_dir = asset_root / "maps"
    if loose_maps_dir.is_dir():
        for path in sorted(loose_maps_dir.glob("*.bsp")):
            map_name = path.stem.lower()
            data = path.read_bytes()
            validation = qge_full_game_capture_queue.bsp_validation_report(data)
            map_sources.setdefault(map_name, []).append({
                "kind": "loose_bsp",
                "path": str(path),
                "bytes": len(data),
                "sha256": sha256_bytes(data),
                "bsp_valid": bool(validation.get("valid")),
                "bsp_validation_reason": validation.get("reason"),
            })
    for pak_path in sorted(asset_root.glob("pak*.pak")):
        pak_data = pak_path.read_bytes()
        records = qge_full_game_capture_queue.pak_directory_records(pak_path)
        pak_report = {
            "path": str(pak_path),
            "bytes": len(pak_data),
            "sha256": sha256_bytes(pak_data),
            "entry_count": len(records),
        }
        pak_files.append(pak_report)
        for record in records:
            name = str(record["name"])
            ext = Path(name).suffix.lower().lstrip(".") or "none"
            asset_counts[ext] += 1
            if name.startswith("sound/"):
                sound_assets.append(name)
            if name.endswith(".spr"):
                sprite_assets.append(name)
            if name.endswith(".mdl"):
                model_assets.append(name)
            if not name.startswith("maps/") or not name.endswith(".bsp"):
                continue
            map_name = Path(name).stem.lower()
            data = pak_entry_payload(pak_data, record)
            validation = qge_full_game_capture_queue.bsp_validation_report(data)
            map_sources.setdefault(map_name, []).append({
                "kind": "pak_entry",
                "pak": str(pak_path),
                "entry": name,
                "file_offset": int(record["file_offset"]),
                "bytes": int(record["file_size"]),
                "sha256": sha256_bytes(data),
                "bsp_valid": bool(validation.get("valid")),
                "bsp_validation_reason": validation.get("reason"),
            })
    assets = {
        "pak_files": pak_files,
        "entry_extension_counts": dict(sorted(asset_counts.items())),
        "sound_assets": sorted(set(sound_assets)),
        "sound_asset_count": len(set(sound_assets)),
        "sprite_assets": sorted(set(sprite_assets)),
        "sprite_asset_count": len(set(sprite_assets)),
        "model_assets": sorted(set(model_assets)),
        "model_asset_count": len(set(model_assets)),
    }
    return map_sources, assets


def load_map_payload(asset_root: Path, source: dict[str, Any]) -> bytes:
    if source.get("kind") == "loose_bsp":
        return Path(str(source["path"])).read_bytes()
    pak_path = Path(str(source["pak"]))
    pak_data = pak_path.read_bytes()
    start = int(source["file_offset"])
    end = start + int(source["bytes"])
    return pak_data[start:end]


def merge_counts(rows: list[dict[str, int]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter.update(row)
    return dict(sorted(counter.items()))


def build_inventory(
    *,
    asset_root: Path = DEFAULT_ASSET_ROOT,
    map_set: str = qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET,
) -> dict[str, Any]:
    target_maps = qge_map_sets.map_targets_for_set(map_set)
    map_sources, assets = collect_asset_records(asset_root)
    maps: list[dict[str, Any]] = []
    missing_maps: list[str] = []
    invalid_maps: list[str] = []
    for map_name in target_maps:
        valid_sources = [
            source for source in map_sources.get(map_name, [])
            if source.get("bsp_valid") is True
        ]
        if not valid_sources:
            if map_name not in map_sources:
                missing_maps.append(map_name)
            else:
                invalid_maps.append(map_name)
            continue
        source = valid_sources[0]
        payload = load_map_payload(asset_root, source)
        parsed = parse_bsp_map(payload)
        maps.append({
            "map": map_name,
            "source": source,
            **parsed,
        })
    monster_counts = merge_counts([
        dict(row["entity"]["monster_class_counts"]) for row in maps
    ])
    weapon_counts = merge_counts([
        dict(row["entity"]["weapon_pickup_counts"]) for row in maps
    ])
    item_counts = merge_counts([
        dict(row["entity"]["item_counts"]) for row in maps
    ])
    trigger_counts = merge_counts([
        dict(row["entity"]["trigger_counts"]) for row in maps
    ])
    material_surface_counts = merge_counts([
        dict(row["materials"]["surface_counts"]) for row in maps
    ])
    material_texture_counts = merge_counts([
        dict(row["materials"]["texture_counts"]) for row in maps
    ])
    status = (
        "complete" if not missing_maps and not invalid_maps else "blocked"
    )
    return {
        "schema": INVENTORY_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "map_set": map_set,
        "map_scope": qge_map_sets.map_set_scope_label(map_set),
        "shareware_episode_one_scope": (
            qge_map_sets.is_shareware_episode_one_map_set(map_set)
        ),
        "registered_full_game_scope": (
            qge_map_sets.is_registered_full_game_map_set(map_set)
        ),
        "asset_root": str(asset_root),
        "target_map_count": len(target_maps),
        "inventoried_map_count": len(maps),
        "missing_map_count": len(missing_maps),
        "missing_maps": missing_maps,
        "invalid_map_count": len(invalid_maps),
        "invalid_maps": invalid_maps,
        "target_maps": target_maps,
        "maps": maps,
        "assets": assets,
        "aggregate": {
            "monster_class_counts": monster_counts,
            "weapon_pickup_counts": weapon_counts,
            "item_counts": item_counts,
            "trigger_counts": trigger_counts,
            "material_surface_counts": material_surface_counts,
            "material_texture_counts": material_texture_counts,
            "maps_with_slipgate_surfaces": [
                row["map"] for row in maps
                if row["flags"]["has_slipgate_surfaces"]
            ],
            "maps_with_teleport_triggers": [
                row["map"] for row in maps
                if row["flags"]["has_teleport_triggers"]
            ],
            "maps_with_liquids": [
                row["map"] for row in maps
                if row["flags"]["has_liquids"]
            ],
            "maps_with_monsters": [
                row["map"] for row in maps
                if row["flags"]["has_monsters"]
            ],
            "maps_with_weapons": [
                row["map"] for row in maps
                if row["flags"]["has_weapons"]
            ],
        },
        "claim_posture": {
            "allowed_wording": (
                "This inventory lists effects found in the local Quake "
                "shareware Episode 1 assets."
            ),
            "disallowed_wording": (
                "This inventory alone does not prove runtime QGE/Moonlab "
                "coverage, release readiness, or registered/full-game coverage."
            ),
        },
    }


def build_icc_evidence(inventory: dict[str, Any], path: Path) -> dict[str, Any]:
    aggregate = dict(inventory.get("aggregate") or {})
    return {
        "schema": ICC_SCHEMA,
        "runtime_backend": "qge_shareware_effects_inventory",
        "completion_reason": (
            "qge_shareware_effects_inventory_complete"
            if inventory.get("status") == "complete"
            else "qge_shareware_effects_inventory_blocked"
        ),
        "shareware_effects_inventory_file": str(path),
        "qge_shareware_effects_inventory.json": str(path),
        "runtime_backend_scope_map_set": inventory.get("map_set"),
        "runtime_backend_scope_target_map_count": inventory.get(
            "target_map_count"),
        "runtime_backend_scope_inventoried_map_count": inventory.get(
            "inventoried_map_count"),
        "runtime_backend_scope_missing_map_count": inventory.get(
            "missing_map_count"),
        "shareware_effects_inventory_status": inventory.get("status"),
        "shareware_effects_inventory_monster_class_count": len(
            aggregate.get("monster_class_counts") or {}),
        "shareware_effects_inventory_weapon_class_count": len(
            aggregate.get("weapon_pickup_counts") or {}),
        "shareware_effects_inventory_slipgate_map_count": len(
            aggregate.get("maps_with_slipgate_surfaces") or []),
        "shareware_effects_inventory_liquid_map_count": len(
            aggregate.get("maps_with_liquids") or []),
    }


def markdown_report(inventory: dict[str, Any]) -> str:
    aggregate = dict(inventory.get("aggregate") or {})
    lines = [
        "# QGE Shareware Effects Inventory",
        "",
        f"- `status`: `{inventory.get('status')}`",
        f"- `map_set`: `{inventory.get('map_set')}`",
        f"- `maps`: `{inventory.get('inventoried_map_count')}` / "
        f"`{inventory.get('target_map_count')}`",
        f"- `missing_maps`: `{inventory.get('missing_map_count')}`",
        f"- `monster_classes`: `{len(aggregate.get('monster_class_counts') or {})}`",
        f"- `weapon_pickups`: `{len(aggregate.get('weapon_pickup_counts') or {})}`",
        f"- `slipgate_surface_maps`: "
        f"`{', '.join(aggregate.get('maps_with_slipgate_surfaces') or []) or 'none'}`",
        f"- `liquid_maps`: "
        f"`{', '.join(aggregate.get('maps_with_liquids') or []) or 'none'}`",
        "",
        "| Map | Entities | Monsters | Weapons | Liquids | Slipgate | Teleport Trigger | Materials |",
        "|---|---:|---:|---:|---|---|---|---:|",
    ]
    for row in inventory.get("maps", []):
        entity = dict(row.get("entity") or {})
        flags = dict(row.get("flags") or {})
        materials = dict(row.get("materials") or {})
        surface_counts = dict(materials.get("surface_counts") or {})
        lines.append(
            "| {map} | {entities} | {monsters} | {weapons} | {liquids} | "
            "{slipgate} | {teleport} | {materials} |".format(
                map=row.get("map"),
                entities=entity.get("entity_count", 0),
                monsters=sum(dict(entity.get(
                    "monster_class_counts") or {}).values()),
                weapons=sum(dict(entity.get(
                    "weapon_pickup_counts") or {}).values()),
                liquids="yes" if flags.get("has_liquids") else "no",
                slipgate="yes" if flags.get(
                    "has_slipgate_surfaces") else "no",
                teleport="yes" if flags.get(
                    "has_teleport_triggers") else "no",
                materials=surface_counts.get("total", 0),
            )
        )
    lines.extend([
        "",
        "## Discovered Monster Classes",
        "",
    ])
    monster_counts = dict(aggregate.get("monster_class_counts") or {})
    if monster_counts:
        for name, count in monster_counts.items():
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Discovered Weapon Pickups",
        "",
    ])
    weapon_counts = dict(aggregate.get("weapon_pickup_counts") or {})
    if weapon_counts:
        for name, count in weapon_counts.items():
            lines.append(f"- `{name}`: `{count}`")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSET_ROOT)
    parser.add_argument("--map-set",
                        default=qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    run_dir = args.out_root / stamp()
    out_path = args.out or run_dir / "qge_shareware_effects_inventory.json"
    markdown_path = (
        args.markdown or
        out_path.with_name("qge_shareware_effects_inventory.md")
    )
    icc_path = (
        args.icc_json or
        out_path.with_name("qge_shareware_effects_inventory_icc_evidence.json")
    )
    inventory = build_inventory(
        asset_root=args.asset_root,
        map_set=args.map_set,
    )
    write_json(out_path, inventory)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown_report(inventory), encoding="utf-8")
    write_json(icc_path, build_icc_evidence(inventory, out_path))
    print(f"QGE_SHAREWARE_EFFECTS_INVENTORY {out_path}")
    print(f"QGE_SHAREWARE_EFFECTS_INVENTORY_MARKDOWN {markdown_path}")
    print(f"QGE_SHAREWARE_EFFECTS_INVENTORY_ICC {icc_path}")
    return 0 if inventory.get("status") == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
