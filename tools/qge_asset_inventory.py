#!/usr/bin/env python3
"""Inventory Quake BSP assets for QGE full-game coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_breadth_evidence  # noqa: E402
import qge_full_game_capture_queue  # noqa: E402

DEFAULT_ASSET_ROOT = REPO_ROOT / "assets" / "id1"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_map_name(path_or_entry: str) -> str | None:
    name = path_or_entry.replace("\\", "/").lower()
    if name.startswith("maps/"):
        name = name[5:]
    if not name.endswith(".bsp"):
        return None
    stem = Path(name).stem.lower()
    return stem or None


def add_source(
    sources_by_map: dict[str, list[dict[str, Any]]],
    map_name: str,
    source: dict[str, Any],
) -> None:
    sources_by_map.setdefault(map_name, []).append(source)


def invalid_bsp_record(
    *,
    kind: str,
    map_name: str,
    validation: dict[str, Any],
    path: str | None = None,
    pak: str | None = None,
    entry: str | None = None,
    bytes_count: int | None = None,
    file_offset: int | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "kind": kind,
        "map": map_name,
        "path": path,
        "pak": pak,
        "entry": entry,
        "bytes": bytes_count,
        "file_offset": file_offset,
        "bsp_valid": False,
        "bsp_validation_reason": validation.get("reason"),
        "bsp_version": validation.get("version"),
    }
    return {key: value for key, value in record.items() if value is not None}


def loose_bsp_sources(
    asset_root: Path,
    invalid_bsp_sources: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    sources: dict[str, list[dict[str, Any]]] = {}
    maps_dir = asset_root / "maps"
    if not maps_dir.is_dir():
        return sources
    for path in sorted(maps_dir.glob("*.bsp")):
        map_name = canonical_map_name(path.name)
        if not map_name:
            continue
        data = path.read_bytes()
        validation = qge_full_game_capture_queue.bsp_validation_report(data)
        if not validation.get("valid"):
            invalid_bsp_sources.append(invalid_bsp_record(
                kind="loose_bsp",
                map_name=map_name,
                validation=validation,
                path=str(path),
                bytes_count=len(data),
            ))
            continue
        add_source(sources, map_name, {
            "kind": "loose_bsp",
            "path": str(path),
            "bytes": len(data),
            "sha256": sha256_file(path),
            "bsp_valid": True,
            "bsp_version": validation.get("version"),
            "bsp_model_count": validation.get("model_count"),
        })
    return sources


def pak_file_reports(
    asset_root: Path,
    sources_by_map: dict[str, list[dict[str, Any]]],
    invalid_bsp_sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    if not asset_root.is_dir():
        return reports
    for path in sorted(asset_root.glob("pak*.pak")):
        report: dict[str, Any] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "status": "ok",
            "entry_count": 0,
            "bsp_maps": [],
        }
        try:
            pak_data = path.read_bytes()
            records = qge_full_game_capture_queue.pak_directory_records(path)
        except ValueError as exc:
            report["status"] = "invalid"
            report["error"] = str(exc)
            reports.append(report)
            continue
        bsp_maps: list[str] = []
        invalid_bsp_entries: list[dict[str, Any]] = []
        for record in records:
            entry = record["name"]
            map_name = canonical_map_name(entry)
            if not map_name:
                continue
            start = int(record["file_offset"])
            end = start + int(record["file_size"])
            validation = qge_full_game_capture_queue.bsp_validation_report(
                pak_data[start:end])
            if not validation.get("valid"):
                invalid = invalid_bsp_record(
                    kind="pak_entry",
                    map_name=map_name,
                    validation=validation,
                    pak=str(path),
                    entry=entry,
                    bytes_count=int(record["file_size"]),
                    file_offset=start,
                )
                invalid_bsp_entries.append(invalid)
                invalid_bsp_sources.append(invalid)
                continue
            bsp_maps.append(map_name)
            add_source(sources_by_map, map_name, {
                "kind": "pak_entry",
                "pak": str(path),
                "entry": entry,
                "file_offset": start,
                "bytes": int(record["file_size"]),
                "bsp_valid": True,
                "bsp_version": validation.get("version"),
                "bsp_model_count": validation.get("model_count"),
            })
        report["entry_count"] = len(records)
        report["bsp_maps"] = sorted(set(bsp_maps))
        report["invalid_bsp_entries"] = invalid_bsp_entries
        report["invalid_bsp_entry_count"] = len(invalid_bsp_entries)
        reports.append(report)
    return reports


def build_inventory(
    asset_root: Path = DEFAULT_ASSET_ROOT,
    *,
    map_set: str = qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET,
) -> dict[str, Any]:
    target_maps = qge_breadth_evidence.map_targets_for_set(map_set)
    target_set = set(target_maps)
    invalid_bsp_sources: list[dict[str, Any]] = []
    sources_by_map = loose_bsp_sources(asset_root, invalid_bsp_sources)
    pak_files = pak_file_reports(asset_root, sources_by_map, invalid_bsp_sources)
    available_target_maps = [
        name for name in target_maps
        if name in sources_by_map
    ]
    missing_maps = [
        name for name in target_maps
        if name not in sources_by_map
    ]
    extra_maps = sorted(
        name for name in sources_by_map
        if name not in target_set
    )
    loose_sources = [
        source
        for sources in sources_by_map.values()
        for source in sources
        if source.get("kind") == "loose_bsp"
    ]
    invalid_paks = [
        report for report in pak_files
        if report.get("status") != "ok"
    ]
    return {
        "schema": "qge.asset_inventory.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "asset_root": str(asset_root),
        "asset_root_status": (
            "present" if asset_root.is_dir() else "missing_asset_root"
        ),
        "map_set": map_set,
        "status": "complete" if not missing_maps and not invalid_paks else "partial",
        "target_map_count": len(target_maps),
        "available_map_count": len(available_target_maps),
        "missing_map_count": len(missing_maps),
        "extra_map_count": len(extra_maps),
        "pak_count": len(pak_files),
        "invalid_pak_count": len(invalid_paks),
        "invalid_bsp_count": len(invalid_bsp_sources),
        "loose_bsp_count": len(loose_sources),
        "available_maps": available_target_maps,
        "missing_maps": missing_maps,
        "extra_maps": extra_maps,
        "available_map_sources": {
            name: sources_by_map[name]
            for name in available_target_maps
        },
        "extra_map_sources": {
            name: sources_by_map[name]
            for name in extra_maps
        },
        "pak_files": pak_files,
        "invalid_bsp_sources": invalid_bsp_sources,
        "full_game_asset_ready": not missing_maps and not invalid_paks,
        "claim_limits": [
            "This inventory proves asset availability only, not QGE runtime coverage.",
            "Do not claim full-game Moonlab coverage until every target map has a capture matrix and breadth evidence is complete.",
        ],
    }


def build_icc_evidence(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_asset_inventory",
        "status": "success",
        "completion_reason": "qge_registered_asset_inventory_complete",
        "asset_inventory_file": None,
        "asset_root": inventory.get("asset_root"),
        "asset_root_status": inventory.get("asset_root_status"),
        "map_set": inventory.get("map_set"),
        "target_map_count": inventory.get("target_map_count"),
        "available_map_count": inventory.get("available_map_count"),
        "missing_map_count": inventory.get("missing_map_count"),
        "missing_maps": inventory.get("missing_maps"),
        "pak_count": inventory.get("pak_count"),
        "invalid_pak_count": inventory.get("invalid_pak_count"),
        "invalid_bsp_count": inventory.get("invalid_bsp_count"),
        "loose_bsp_count": inventory.get("loose_bsp_count"),
        "full_game_asset_ready": inventory.get("full_game_asset_ready"),
        "whole_game_moonlab_coverage_claimed": False,
    }


def markdown_report(inventory: dict[str, Any]) -> str:
    lines = [
        "# QGE Asset Inventory",
        "",
        f"Asset root: `{inventory['asset_root']}` "
        f"({inventory['asset_root_status']})",
        "",
        "| Map Set | Available | Missing | PAK Files | Invalid BSPs | Loose BSPs | Ready |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        (
            f"| {inventory['map_set']} | "
            f"{inventory['available_map_count']} / "
            f"{inventory['target_map_count']} | "
            f"{inventory['missing_map_count']} | "
            f"{inventory['pak_count']} | "
            f"{inventory['invalid_bsp_count']} | "
            f"{inventory['loose_bsp_count']} | "
            f"{inventory['full_game_asset_ready']} |"
        ),
        "",
        "## PAK Files",
        "",
        "| Path | Status | Entries | Valid BSP Maps | Invalid BSP Entries | SHA-256 |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for pak in inventory["pak_files"]:
        lines.append(
            f"| `{pak['path']}` | {pak['status']} | "
            f"{pak.get('entry_count', 0)} | "
            f"{len(pak.get('bsp_maps', []))} | "
            f"{pak.get('invalid_bsp_entry_count', 0)} | "
            f"`{pak['sha256']}` |"
        )
    if not inventory["pak_files"]:
        lines.append("| none | missing | 0 | 0 | 0 |  |")
    lines.extend([
        "",
        "## Available Maps",
        "",
        ", ".join(inventory["available_maps"]) or "none",
        "",
        "## Missing Maps",
        "",
        ", ".join(inventory["missing_maps"]) or "none",
        "",
    ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ASSET_ROOT)
    parser.add_argument("--map-set",
                        default=qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = build_inventory(args.asset_root, map_set=args.map_set)
    icc = build_icc_evidence(inventory)
    if args.json:
        write_json(args.json, inventory)
        icc["asset_inventory_file"] = str(args.json)
        print(f"QGE_ASSET_INVENTORY {args.json}")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_report(inventory), encoding="utf-8")
        print(f"QGE_ASSET_INVENTORY_MARKDOWN {args.markdown}")
    if args.icc_json:
        write_json(args.icc_json, icc)
        print(f"QGE_ASSET_INVENTORY_ICC_EVIDENCE {args.icc_json}")
    if not args.json and not args.markdown and not args.icc_json:
        print(json.dumps(inventory, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
