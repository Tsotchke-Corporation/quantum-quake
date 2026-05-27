#!/usr/bin/env python3
"""Report registered full-game progress from assets plus map evidence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_asset_inventory  # noqa: E402
import qge_map_set_evidence  # noqa: E402
import qge_map_sets  # noqa: E402


SCHEMA = "qge.registered_full_game_progress.v0"
ICC_SCHEMA = "qge.icc_evidence.v0"
PROGRESS_FILENAME = "qge_registered_full_game_progress.json"
MARKDOWN_FILENAME = "qge_registered_full_game_progress.md"
ICC_FILENAME = "qge_registered_full_game_progress_icc_evidence.json"
DEFAULT_OUTDIR = (
    REPO_ROOT / "diagnostics" / "full_game_progress" /
    "registered_single_player"
)
DEFAULT_SELECTION = (
    REPO_ROOT / "diagnostics" / "breadth_evidence" /
    "registered_single_player_status" /
    qge_map_set_evidence.SELECTION_FILENAME
)


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


def resolve_existing_path(path: Path) -> Path:
    if path.exists() or path.is_absolute():
        return path
    return REPO_ROOT / path


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def selection_from_inputs(
    *,
    selection_path: Path | None,
    matrix_root: Path,
    map_set: str,
) -> tuple[dict[str, Any], Path | None]:
    if selection_path is not None:
        resolved = resolve_existing_path(selection_path)
        if resolved.is_file():
            selection = load_json(resolved)
            if selection.get("map_set") != map_set:
                raise ValueError(
                    f"{resolved} map_set {selection.get('map_set')!r} "
                    f"does not match {map_set!r}"
                )
            return selection, resolved
    selection = qge_map_set_evidence.scan_ready_map_set_runs(
        matrix_root,
        map_set=map_set,
    )
    return selection, None


def progress_status_for_map(
    *,
    evidence_status: str,
    asset_available: bool,
) -> tuple[str, str]:
    if not asset_available:
        return "blocked_asset_missing", "install_registered_bsp_asset"
    if evidence_status == "ready":
        return "ready", "keep_ready_capture_evidence"
    if evidence_status == "blocked_not_ready":
        return "blocked_capture_not_ready", "rerun_strict_capture"
    return "pending_capture", "run_strict_capture"


def next_blocker(progress_rows: list[dict[str, Any]]) -> str:
    statuses = {str(row.get("status")) for row in progress_rows}
    if "blocked_asset_missing" in statuses:
        return "registered_assets_missing"
    if "blocked_capture_not_ready" in statuses:
        return "capture_attempts_not_ready"
    if "pending_capture" in statuses:
        return "capture_evidence_missing"
    return "complete"


def build_progress(
    *,
    selection_path: Path | None = DEFAULT_SELECTION,
    matrix_root: Path = qge_map_set_evidence.DEFAULT_MATRIX_ROOT,
    asset_root: Path = qge_asset_inventory.DEFAULT_ASSET_ROOT,
    map_set: str = qge_map_sets.DEFAULT_FULL_GAME_MAP_SET,
) -> dict[str, Any]:
    if not qge_map_sets.is_registered_full_game_map_set(map_set):
        raise ValueError(
            "registered full-game progress requires "
            f"{qge_map_sets.DEFAULT_FULL_GAME_MAP_SET}"
        )
    selection, resolved_selection_path = selection_from_inputs(
        selection_path=selection_path,
        matrix_root=matrix_root,
        map_set=map_set,
    )
    inventory = qge_asset_inventory.build_inventory(
        asset_root,
        map_set=map_set,
    )
    target_maps = qge_map_sets.map_targets_for_set(map_set)
    status_by_map = {
        str(item.get("map")): dict_or_empty(item)
        for item in list_or_empty(selection.get("target_map_status"))
        if isinstance(item, dict) and item.get("map")
    }
    available_maps = set(str(name) for name in inventory.get(
        "available_maps", []))
    available_sources = dict_or_empty(inventory.get("available_map_sources"))
    rows: list[dict[str, Any]] = []
    for map_name in target_maps:
        evidence = status_by_map.get(map_name, {})
        evidence_status = str(evidence.get("status") or "missing_matrix")
        asset_available = map_name in available_maps
        status, action = progress_status_for_map(
            evidence_status=evidence_status,
            asset_available=asset_available,
        )
        rows.append({
            "map": map_name,
            "status": status,
            "next_action": action,
            "asset_available": asset_available,
            "asset_source_count": len(list_or_empty(
                available_sources.get(map_name))),
            "evidence_status": evidence_status,
            "selected_matrix_file": evidence.get("selected_matrix_file"),
            "ready_candidate_count": evidence.get(
                "ready_candidate_count", 0),
            "rejected_candidate_count": evidence.get(
                "rejected_candidate_count", 0),
            "rejected_reasons": evidence.get("rejected_reasons", []),
        })

    ready_maps = [
        row["map"] for row in rows if row["status"] == "ready"
    ]
    asset_blocked_maps = [
        row["map"] for row in rows
        if row["status"] == "blocked_asset_missing"
    ]
    capture_blocked_maps = [
        row["map"] for row in rows
        if row["status"] == "blocked_capture_not_ready"
    ]
    pending_capture_maps = [
        row["map"] for row in rows if row["status"] == "pending_capture"
    ]
    capture_needed_maps = capture_blocked_maps + pending_capture_maps
    blocker = next_blocker(rows)
    return {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if blocker == "complete" else "partial",
        "next_blocker": blocker,
        "map_set": map_set,
        "map_scope": qge_map_sets.map_set_scope_label(map_set),
        "registered_full_game_scope": True,
        "selection_file": (
            str(resolved_selection_path) if resolved_selection_path else None
        ),
        "matrix_root": str(matrix_root),
        "asset_root": str(asset_root),
        "asset_root_status": inventory.get("asset_root_status"),
        "target_map_count": len(target_maps),
        "ready_map_count": len(ready_maps),
        "blocked_map_count": len(rows) - len(ready_maps),
        "asset_available_map_count": len(available_maps),
        "asset_missing_map_count": len(asset_blocked_maps),
        "capture_needed_map_count": len(capture_needed_maps),
        "capture_blocked_not_ready_count": len(capture_blocked_maps),
        "capture_missing_matrix_count": len(pending_capture_maps),
        "ready_maps": ready_maps,
        "asset_blocked_maps": asset_blocked_maps,
        "capture_blocked_maps": capture_blocked_maps,
        "pending_capture_maps": pending_capture_maps,
        "capture_needed_maps": capture_needed_maps,
        "target_map_progress": rows,
        "source_selection_status": selection.get("status"),
        "source_selection_ready_target_map_count": selection.get(
            "ready_target_map_count"),
        "source_selection_blocked_not_ready_map_count": selection.get(
            "blocked_not_ready_map_count"),
        "source_selection_missing_matrix_map_count": selection.get(
            "missing_matrix_map_count"),
        "source_inventory_status": inventory.get("status"),
        "source_inventory_missing_maps": inventory.get("missing_maps"),
        "source_inventory_invalid_bsp_count": inventory.get(
            "invalid_bsp_count"),
        "whole_game_moonlab_deployment_claimed": False,
        "claim_limits": [
            "This report joins live asset availability with map-set evidence; "
            "it does not contain Quake asset payloads.",
            "A ready map still remains within the registered full-game gate "
            "until every target map is ready.",
            "Do not claim whole-game Moonlab deployment until this report, "
            "the breadth ledger, and the deployment gate are complete.",
        ],
    }


def build_icc_evidence(progress: dict[str, Any]) -> dict[str, Any]:
    complete = progress.get("status") == "complete"
    return {
        "schema": ICC_SCHEMA,
        "runtime_backend": "qge_registered_full_game_progress",
        "status": "success",
        "completion_reason": (
            "qge_registered_full_game_progress_complete"
            if complete else "qge_registered_full_game_progress_partial"
        ),
        "registered_full_game_progress_file": None,
        "map_set": progress.get("map_set"),
        "next_blocker": progress.get("next_blocker"),
        "target_map_count": progress.get("target_map_count"),
        "ready_map_count": progress.get("ready_map_count"),
        "asset_missing_map_count": progress.get("asset_missing_map_count"),
        "capture_needed_map_count": progress.get("capture_needed_map_count"),
        "whole_game_moonlab_deployment_claimed": False,
    }


def markdown_report(progress: dict[str, Any]) -> str:
    lines = [
        "# QGE Registered Full-Game Progress",
        "",
        f"Status: `{progress['status']}`",
        f"Next blocker: `{progress['next_blocker']}`",
        f"Map set: `{progress['map_set']}`",
        "",
        "| Ready | Asset Missing | Capture Needed | Not-Ready Captures | Missing Matrices |",
        "| ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {progress['ready_map_count']} / "
            f"{progress['target_map_count']} | "
            f"{progress['asset_missing_map_count']} | "
            f"{progress['capture_needed_map_count']} | "
            f"{progress['capture_blocked_not_ready_count']} | "
            f"{progress['capture_missing_matrix_count']} |"
        ),
        "",
        "## Per-Map Progress",
        "",
        "| Map | Status | Asset | Evidence | Next Action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in list_or_empty(progress.get("target_map_progress")):
        if not isinstance(row, dict):
            continue
        asset = "available" if row.get("asset_available") else "missing"
        lines.append(
            f"| {row.get('map')} | {row.get('status')} | {asset} | "
            f"{row.get('evidence_status')} | {row.get('next_action')} |"
        )
    lines.extend([
        "",
        "## Claim Limits",
        "",
    ])
    for limit in list_or_empty(progress.get("claim_limits")):
        lines.append(f"- {limit}")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--matrix-root",
                        type=Path,
                        default=qge_map_set_evidence.DEFAULT_MATRIX_ROOT)
    parser.add_argument("--asset-root",
                        type=Path,
                        default=qge_asset_inventory.DEFAULT_ASSET_ROOT)
    parser.add_argument("--map-set",
                        default=qge_map_sets.DEFAULT_FULL_GAME_MAP_SET,
                        choices=sorted(qge_map_sets.MAP_SETS))
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        progress = build_progress(
            selection_path=args.selection,
            matrix_root=args.matrix_root,
            asset_root=args.asset_root,
            map_set=args.map_set,
        )
        icc = build_icc_evidence(progress)
        if args.json:
            write_json(args.json, progress)
            icc["registered_full_game_progress_file"] = str(args.json)
            print(f"QGE_REGISTERED_FULL_GAME_PROGRESS {args.json}")
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(progress),
                                     encoding="utf-8")
            print(
                "QGE_REGISTERED_FULL_GAME_PROGRESS_MARKDOWN "
                f"{args.markdown}"
            )
        if args.icc_json:
            write_json(args.icc_json, icc)
            print(
                "QGE_REGISTERED_FULL_GAME_PROGRESS_ICC_EVIDENCE "
                f"{args.icc_json}"
            )
        if not args.json and not args.markdown and not args.icc_json:
            print(json.dumps(progress, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_registered_full_game_progress: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
