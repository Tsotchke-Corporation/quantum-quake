#!/usr/bin/env python3
"""Build a registered Quake BSP asset requirements packet for QGE."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_asset_inventory  # noqa: E402
import qge_breadth_evidence  # noqa: E402


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


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def source_summary(sources: list[Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        if source.get("kind") == "loose_bsp":
            summaries.append({
                "kind": "loose_bsp",
                "path": source.get("path"),
                "bytes": source.get("bytes"),
                "sha256": source.get("sha256"),
            })
        elif source.get("kind") == "pak_entry":
            summaries.append({
                "kind": "pak_entry",
                "pak": source.get("pak"),
                "entry": source.get("entry"),
            })
        else:
            summaries.append(dict(source))
    return summaries


def map_requirement(
    map_name: str,
    inventory: dict[str, Any],
) -> dict[str, Any]:
    available_sources = dict_or_empty(inventory.get("available_map_sources"))
    sources = list_or_empty(available_sources.get(map_name))
    present = bool(sources)
    required_entry = f"maps/{map_name}.bsp"
    return {
        "map": map_name,
        "required_entry": required_entry,
        "status": "present" if present else "missing",
        "asset_sources": source_summary(sources),
        "accepted_locations": [
            f"<asset_root>/{required_entry}",
            f"<asset_root>/pak*.pak:{required_entry}",
        ],
        "next_action": (
            "keep_existing_registered_asset"
            if present else "provide_registered_bsp_asset"
        ),
    }


def build_requirements(
    inventory: dict[str, Any],
    *,
    map_set: str | None = None,
) -> dict[str, Any]:
    if inventory.get("schema") != "qge.asset_inventory.v0":
        raise ValueError("inventory is not qge.asset_inventory.v0")
    map_set = map_set or inventory.get("map_set")
    if not isinstance(map_set, str) or not map_set:
        map_set = qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET
    target_maps = qge_breadth_evidence.map_targets_for_set(map_set)
    requirements = [
        map_requirement(map_name, inventory)
        for map_name in target_maps
    ]
    missing = [
        item for item in requirements
        if item.get("status") == "missing"
    ]
    present = [
        item for item in requirements
        if item.get("status") == "present"
    ]
    return {
        "schema": "qge.asset_requirements.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "asset_root": inventory.get("asset_root"),
        "asset_root_status": inventory.get("asset_root_status"),
        "map_set": map_set,
        "target_map_count": len(target_maps),
        "present_map_count": len(present),
        "missing_map_count": len(missing),
        "status": (
            "complete" if not missing else "blocked_missing_registered_assets"
        ),
        "requirements": requirements,
        "missing_required_entries": [
            item["required_entry"] for item in missing
        ],
        "missing_maps": [item["map"] for item in missing],
        "present_maps": [item["map"] for item in present],
        "claim_posture": {
            "asset_requirements_satisfied": not missing,
            "whole_game_moonlab_deployment_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "hardware_quantum_advantage_claimed": False,
        },
        "limits": [
            "This packet lists required registered BSP assets only; it contains no game asset payload.",
            "Supplying these assets enables capture attempts, not a whole-game Moonlab completion claim by itself.",
            "Every newly available map still needs strict QGE/vanilla capture and breadth evidence.",
        ],
    }


def build_icc_evidence(
    requirements: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_asset_requirements",
        "completion_reason": "qge_registered_asset_requirements_recorded",
        "asset_requirements_file": str(out_path) if out_path else None,
        "status": "success",
        "asset_requirement_status": requirements.get("status"),
        "map_set": requirements.get("map_set"),
        "target_map_count": requirements.get("target_map_count"),
        "present_map_count": requirements.get("present_map_count"),
        "missing_map_count": requirements.get("missing_map_count"),
        "missing_maps": requirements.get("missing_maps"),
        "whole_game_moonlab_deployment_claimed": False,
        "whole_game_hardware_execution_claimed": False,
        "hardware_quantum_advantage_claimed": False,
    }


def markdown_report(requirements: dict[str, Any]) -> str:
    lines = [
        "# QGE Registered Asset Requirements",
        "",
        f"Status: {requirements['status']}",
        f"Asset root: `{requirements.get('asset_root')}`",
        "",
        "| Map Set | Present | Missing |",
        "| --- | ---: | ---: |",
        (
            f"| {requirements.get('map_set')} | "
            f"{requirements.get('present_map_count')} / "
            f"{requirements.get('target_map_count')} | "
            f"{requirements.get('missing_map_count')} |"
        ),
        "",
        "| Map | Required Entry | Status | Next Action |",
        "| --- | --- | --- | --- |",
    ]
    for item in list_or_empty(requirements.get("requirements")):
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| {item.get('map')} | `{item.get('required_entry')}` | "
            f"{item.get('status')} | {item.get('next_action')} |"
        )
    lines.extend([
        "",
        "## Missing Entries",
        "",
        ", ".join(requirements.get("missing_required_entries", [])) or "none",
        "",
    ])
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-root", type=Path,
                        default=qge_asset_inventory.DEFAULT_ASSET_ROOT)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--map-set",
                        default=qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.inventory:
            inventory = load_json(args.inventory)
        else:
            inventory = qge_asset_inventory.build_inventory(
                args.asset_root, map_set=args.map_set)
        requirements = build_requirements(inventory, map_set=args.map_set)
        write_json(args.json, requirements)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(
                markdown_report(requirements), encoding="utf-8")
        if args.icc_json:
            icc = build_icc_evidence(requirements, out_path=args.json)
            write_json(args.icc_json, icc)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_asset_requirements: {exc}", file=sys.stderr)
        return 1

    print(f"QGE_ASSET_REQUIREMENTS {args.json}")
    if args.markdown:
        print(f"QGE_ASSET_REQUIREMENTS_MARKDOWN {args.markdown}")
    if args.icc_json:
        print(f"QGE_ASSET_REQUIREMENTS_ICC_EVIDENCE {args.icc_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
