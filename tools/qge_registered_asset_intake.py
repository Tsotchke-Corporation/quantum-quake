#!/usr/bin/env python3
"""Scan registered Quake asset candidates and build a safe intake plan.

This tool never copies game data by default. It validates candidate PAK/BSP
payloads, reports which missing canonical maps they would unblock, and emits a
copy script that a human can run only after confirming they may install those
registered assets locally.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_asset_inventory  # noqa: E402
import qge_breadth_evidence  # noqa: E402
import qge_full_game_capture_queue  # noqa: E402

COMMON_DISCOVERY_PATHS = [
    Path("~/Library/Application Support/Steam/steamapps/common/Quake"),
    Path("~/Library/Application Support/Steam/steamapps/common/Quake/id1"),
    Path("~/Library/Application Support/Steam/steamapps/common/Quake/rerelease/id1"),
    Path("~/Library/Application Support/GOG.com"),
    Path("~/Games/Quake"),
    Path("~/Desktop/Quake"),
    Path("~/Documents/Quake"),
    Path("~/Downloads/Quake"),
    Path("/Applications/Quake.app/Contents/Resources/id1"),
]


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def shell_quote(path: Path | str) -> str:
    return shlex.quote(str(path))


def safe_iterdir(path: Path) -> list[Path]:
    try:
        return list(path.iterdir())
    except OSError:
        return []


def safe_sha256_file(path: Path) -> str | None:
    try:
        return qge_asset_inventory.sha256_file(path)
    except OSError:
        return None


def files_matching(path: Path, suffix: str, *, prefix: str = "") -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(
        [
            child for child in safe_iterdir(path)
            if child.is_file()
            and child.name.lower().startswith(prefix)
            and child.suffix.lower() == suffix
        ],
        key=lambda child: child.name.lower(),
    )


def pak_files(path: Path) -> list[Path]:
    return files_matching(path, ".pak", prefix="pak")


def maps_directory(path: Path) -> Path | None:
    if not path.is_dir():
        return None
    for child in safe_iterdir(path):
        if child.is_dir() and child.name.lower() == "maps":
            return child
    return None


def bsp_files(path: Path) -> list[Path]:
    return files_matching(path, ".bsp")


def env_candidate_paths() -> list[Path]:
    paths: list[Path] = []
    for key in ("QGE_REGISTERED_ASSET_CANDIDATE", "QUAKE_ID1", "QUAKE_ROOT"):
        value = os.environ.get(key)
        if value:
            paths.append(Path(value))
    return paths


def common_discovery_roots() -> list[Path]:
    return env_candidate_paths() + COMMON_DISCOVERY_PATHS


def discovery_candidate_reason(path: Path) -> str | None:
    if path.is_file():
        suffix = path.suffix.lower()
        if suffix == ".pak":
            return "pak_file"
        if suffix == ".bsp":
            return "bsp_file"
        return None
    if not path.is_dir():
        return None
    if pak_files(path):
        return "contains_pak_files"
    if maps_directory(path):
        return "contains_maps_directory"
    return None


def discover_candidate_paths(
    roots: Sequence[Path],
    *,
    max_depth: int,
) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_dirs: set[str] = set()
    seen_candidates: set[str] = set()

    for raw_root in roots:
        root = raw_root.expanduser()
        if not root.exists():
            skipped.append({
                "path": str(root),
                "reason": "missing_path",
            })
            continue
        reason = discovery_candidate_reason(root)
        if reason:
            key = str(root.resolve())
            if key not in seen_candidates:
                seen_candidates.add(key)
                found.append({
                    "path": str(root),
                    "reason": reason,
                    "depth": 0,
                })
            continue
        if not root.is_dir():
            skipped.append({
                "path": str(root),
                "reason": "unsupported_file",
            })
            continue

        queue: deque[tuple[Path, int]] = deque([(root, 0)])
        while queue:
            path, depth = queue.popleft()
            try:
                directory_key = str(path.resolve())
            except OSError:
                skipped.append({
                    "path": str(path),
                    "reason": "resolve_error",
                })
                continue
            if directory_key in seen_dirs:
                continue
            seen_dirs.add(directory_key)
            reason = discovery_candidate_reason(path)
            if reason:
                if directory_key not in seen_candidates:
                    seen_candidates.add(directory_key)
                    found.append({
                        "path": str(path),
                        "reason": reason,
                        "depth": depth,
                    })
                continue
            if depth >= max_depth:
                continue
            for child in safe_iterdir(path):
                if not child.is_dir():
                    continue
                if child.name.startswith("."):
                    continue
                if child.name in {
                    "__pycache__",
                    "build",
                    "diagnostics",
                    "node_modules",
                    "target",
                }:
                    continue
                queue.append((child, depth + 1))

    return {
        "roots": [str(path.expanduser()) for path in roots],
        "max_depth": max_depth,
        "found_candidate_count": len(found),
        "found_candidates": found,
        "skipped_root_count": len(skipped),
        "skipped_roots": skipped,
    }


def candidate_scan_targets(inputs: Sequence[Path]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw_path in inputs:
        path = raw_path.expanduser()
        candidates: list[tuple[str, Path]] = []
        if path.is_file():
            suffix = path.suffix.lower()
            if suffix == ".pak":
                candidates.append(("pak_file", path))
            elif suffix == ".bsp":
                candidates.append(("bsp_file", path))
            else:
                candidates.append(("unsupported_file", path))
        elif path.is_dir():
            if pak_files(path) or maps_directory(path):
                candidates.append(("asset_root", path))
            for name in ("id1", "Id1", "ID1"):
                child = path / name
                if child.is_dir():
                    candidates.append(("asset_root", child))
            if not candidates:
                candidates.append(("empty_directory", path))
        else:
            candidates.append(("missing_path", path))
        for kind, candidate in candidates:
            key = (kind, str(candidate.resolve() if candidate.exists() else candidate))
            if key in seen:
                continue
            seen.add(key)
            targets.append({"kind": kind, "path": candidate})
    return targets


def source_record(
    *,
    source_kind: str,
    map_name: str,
    path: Path,
    entry: str | None = None,
    bytes_count: int | None = None,
    file_offset: int | None = None,
    sha256: str | None = None,
    bsp_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation = dict_or_empty(bsp_validation)
    record: dict[str, Any] = {
        "source_kind": source_kind,
        "map": map_name,
        "path": str(path),
        "entry": entry,
        "bytes": bytes_count,
        "file_offset": file_offset,
        "sha256": sha256,
        "bsp_valid": validation.get("valid"),
        "bsp_version": validation.get("version"),
        "bsp_model_count": validation.get("model_count"),
        "bsp_validation_reason": validation.get("reason"),
    }
    return {key: value for key, value in record.items() if value is not None}


def invalid_record(
    *,
    source_kind: str,
    map_name: str | None,
    path: Path,
    validation: dict[str, Any] | None = None,
    entry: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    validation = dict_or_empty(validation)
    record: dict[str, Any] = {
        "source_kind": source_kind,
        "map": map_name,
        "path": str(path),
        "entry": entry,
        "bsp_valid": False if validation else None,
        "bsp_version": validation.get("version"),
        "bsp_validation_reason": validation.get("reason"),
        "error": error,
    }
    return {key: value for key, value in record.items() if value is not None}


def scan_pak_file(path: Path) -> dict[str, Any]:
    sources: dict[str, list[dict[str, Any]]] = {}
    invalid: list[dict[str, Any]] = []
    try:
        data = path.read_bytes()
        records = qge_full_game_capture_queue.pak_directory_records(path)
    except (OSError, ValueError) as exc:
        return {
            "kind": "pak_file",
            "path": str(path),
            "status": "invalid_pak",
            "valid_maps": [],
            "valid_map_count": 0,
            "invalid_bsp_count": 0,
            "error": str(exc),
            "sources_by_map": {},
            "invalid_sources": [],
            "sha256": safe_sha256_file(path) if path.is_file() else None,
        }
    sha256 = qge_asset_inventory.sha256_file(path)
    for record in records:
        entry = record["name"]
        map_name = qge_asset_inventory.canonical_map_name(entry)
        if not map_name:
            continue
        start = int(record["file_offset"])
        end = start + int(record["file_size"])
        validation = qge_full_game_capture_queue.bsp_validation_report(
            data[start:end])
        if not validation.get("valid"):
            invalid.append(invalid_record(
                source_kind="pak_entry",
                map_name=map_name,
                path=path,
                entry=entry,
                validation=validation,
            ))
            continue
        sources.setdefault(map_name, []).append(source_record(
            source_kind="pak_entry",
            map_name=map_name,
            path=path,
            entry=entry,
            bytes_count=int(record["file_size"]),
            file_offset=start,
            sha256=sha256,
            bsp_validation=validation,
        ))
    return {
        "kind": "pak_file",
        "path": str(path),
        "status": "ok",
        "sha256": sha256,
        "entry_count": len(records),
        "valid_maps": sorted(sources),
        "valid_map_count": len(sources),
        "invalid_bsp_count": len(invalid),
        "sources_by_map": sources,
        "invalid_sources": invalid,
    }


def scan_bsp_file(path: Path) -> dict[str, Any]:
    map_name = qge_asset_inventory.canonical_map_name(path.name)
    sources: dict[str, list[dict[str, Any]]] = {}
    invalid: list[dict[str, Any]] = []
    if not map_name:
        return {
            "kind": "bsp_file",
            "path": str(path),
            "status": "unsupported_bsp_name",
            "valid_maps": [],
            "valid_map_count": 0,
            "invalid_bsp_count": 0,
            "sources_by_map": {},
            "invalid_sources": [],
        }
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {
            "kind": "bsp_file",
            "path": str(path),
            "status": "read_error",
            "valid_maps": [],
            "valid_map_count": 0,
            "invalid_bsp_count": 0,
            "error": str(exc),
            "sources_by_map": {},
            "invalid_sources": [],
        }
    validation = qge_full_game_capture_queue.bsp_validation_report(data)
    if validation.get("valid"):
        sources.setdefault(map_name, []).append(source_record(
            source_kind="loose_bsp",
            map_name=map_name,
            path=path,
            bytes_count=len(data),
            sha256=qge_asset_inventory.sha256_file(path),
            bsp_validation=validation,
        ))
    else:
        invalid.append(invalid_record(
            source_kind="loose_bsp",
            map_name=map_name,
            path=path,
            validation=validation,
        ))
    return {
        "kind": "bsp_file",
        "path": str(path),
        "status": "ok" if not invalid else "invalid_bsp",
        "valid_maps": sorted(sources),
        "valid_map_count": len(sources),
        "invalid_bsp_count": len(invalid),
        "sources_by_map": sources,
        "invalid_sources": invalid,
    }


def merge_sources(
    target: dict[str, list[dict[str, Any]]],
    source: dict[str, Any],
) -> None:
    for map_name, entries in dict_or_empty(source).items():
        if not isinstance(map_name, str):
            continue
        for entry in list_or_empty(entries):
            if isinstance(entry, dict):
                target.setdefault(map_name, []).append(entry)


def scan_asset_root(path: Path) -> dict[str, Any]:
    sources: dict[str, list[dict[str, Any]]] = {}
    invalid: list[dict[str, Any]] = []
    pak_reports = []
    loose_reports = []
    maps_dir = maps_directory(path)
    if maps_dir:
        for bsp_path in bsp_files(maps_dir):
            report = scan_bsp_file(bsp_path)
            loose_reports.append(report)
            merge_sources(sources, report.get("sources_by_map"))
            invalid.extend(list_or_empty(report.get("invalid_sources")))
    for pak_path in pak_files(path):
        report = scan_pak_file(pak_path)
        pak_reports.append(report)
        merge_sources(sources, report.get("sources_by_map"))
        invalid.extend(list_or_empty(report.get("invalid_sources")))
    return {
        "kind": "asset_root",
        "path": str(path),
        "status": "ok" if path.is_dir() else "missing_path",
        "valid_maps": sorted(sources),
        "valid_map_count": len(sources),
        "invalid_bsp_count": len(invalid),
        "pak_reports": pak_reports,
        "loose_bsp_reports": loose_reports,
        "sources_by_map": sources,
        "invalid_sources": invalid,
    }


def scan_target(target: dict[str, Any]) -> dict[str, Any]:
    kind = target["kind"]
    path = Path(target["path"])
    if kind == "asset_root":
        return scan_asset_root(path)
    if kind == "pak_file":
        return scan_pak_file(path)
    if kind == "bsp_file":
        return scan_bsp_file(path)
    return {
        "kind": kind,
        "path": str(path),
        "status": kind,
        "valid_maps": [],
        "valid_map_count": 0,
        "invalid_bsp_count": 0,
        "sources_by_map": {},
        "invalid_sources": [invalid_record(
            source_kind=kind,
            map_name=None,
            path=path,
            error=f"unsupported candidate target: {kind}",
        )],
    }


def current_pak_fingerprints(inventory: dict[str, Any]) -> dict[str, str]:
    result = {}
    for pak in list_or_empty(inventory.get("pak_files")):
        if not isinstance(pak, dict):
            continue
        path = pak.get("path")
        sha = pak.get("sha256")
        if isinstance(path, str) and isinstance(sha, str):
            result[path] = sha
    return result


def choose_pak_destination(
    source_path: Path,
    source_sha: str | None,
    current_root: Path,
    used_destinations: set[str],
    existing_paks: dict[str, str],
) -> tuple[Path, str, str]:
    for existing_path, existing_sha in existing_paks.items():
        if source_sha and source_sha == existing_sha:
            return Path(existing_path), "already_present", "matching_sha256"
    requested = current_root / source_path.name.lower()
    if not requested.exists() and str(requested) not in used_destinations:
        used_destinations.add(str(requested))
        return requested, "planned", "basename_available"
    for index in range(0, 100):
        candidate = current_root / f"pak{index}.pak"
        if not candidate.exists() and str(candidate) not in used_destinations:
            used_destinations.add(str(candidate))
            return candidate, "planned", "avoid_overwrite"
    return requested, "blocked_no_free_pak_slot", "no_free_pak_slot"


def build_copy_plan(
    chosen_sources: dict[str, dict[str, Any]],
    current_root: Path,
    current_inventory: dict[str, Any],
) -> list[dict[str, Any]]:
    existing_paks = current_pak_fingerprints(current_inventory)
    used_destinations: set[str] = set()
    pak_groups: dict[str, dict[str, Any]] = {}
    loose_entries: list[dict[str, Any]] = []
    for map_name, source in sorted(chosen_sources.items()):
        if source.get("source_kind") == "pak_entry":
            path = str(source.get("path"))
            if path not in pak_groups:
                destination, status, reason = choose_pak_destination(
                    Path(path),
                    source.get("sha256") if isinstance(source.get("sha256"), str)
                    else None,
                    current_root,
                    used_destinations,
                    existing_paks,
                )
                pak_groups[path] = {
                    "kind": "copy_pak",
                    "status": status,
                    "source": path,
                    "source_sha256": source.get("sha256"),
                    "destination": str(destination),
                    "destination_reason": reason,
                    "maps_unblocked": [],
                }
            pak_groups[path]["maps_unblocked"].append(map_name)
        elif source.get("source_kind") == "loose_bsp":
            destination = current_root / "maps" / f"{map_name}.bsp"
            status = "blocked_destination_exists" if destination.exists() else "planned"
            loose_entries.append({
                "kind": "copy_loose_bsp",
                "status": status,
                "source": source.get("path"),
                "source_sha256": source.get("sha256"),
                "destination": str(destination),
                "maps_unblocked": [map_name],
            })
    plan = list(pak_groups.values()) + loose_entries
    for entry in plan:
        if entry.get("status") == "planned":
            source = entry.get("source")
            destination = entry.get("destination")
            entry["command"] = (
                f"cp -n {shell_quote(source)} {shell_quote(destination)}"
            )
        elif entry.get("status") == "already_present":
            entry["command"] = None
        else:
            entry["command"] = None
    return plan


def build_intake(
    current_root: Path,
    candidates: Sequence[Path],
    *,
    map_set: str = qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET,
    discovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_inventory = qge_asset_inventory.build_inventory(
        current_root,
        map_set=map_set,
    )
    missing_maps = [
        item for item in list_or_empty(current_inventory.get("missing_maps"))
        if isinstance(item, str)
    ]
    target_maps = qge_breadth_evidence.map_targets_for_set(map_set)
    target_set = set(target_maps)
    candidate_reports = [
        scan_target(target) for target in candidate_scan_targets(candidates)
    ]
    candidate_sources: dict[str, list[dict[str, Any]]] = {}
    invalid_sources: list[dict[str, Any]] = []
    for report in candidate_reports:
        merge_sources(candidate_sources, report.get("sources_by_map"))
        invalid_sources.extend(list_or_empty(report.get("invalid_sources")))
    chosen_sources = {
        map_name: candidate_sources[map_name][0]
        for map_name in missing_maps
        if map_name in candidate_sources
    }
    copy_plan = build_copy_plan(chosen_sources, current_root, current_inventory)
    newly_available_maps = [
        map_name for map_name in missing_maps
        if map_name in chosen_sources
    ]
    candidate_extra_maps = sorted(
        map_name for map_name in candidate_sources
        if map_name not in target_set
    )
    missing_after_plan = [
        map_name for map_name in missing_maps
        if map_name not in set(newly_available_maps)
    ]
    intake = {
        "schema": "qge.registered_asset_intake.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "current_asset_root": str(current_root),
        "map_set": map_set,
        "status": (
            "complete_after_plan" if not missing_after_plan else
            "partial_candidate_assets_found" if newly_available_maps else
            "blocked_no_candidate_assets"
        ),
        "target_map_count": len(target_maps),
        "current_available_map_count": current_inventory.get(
            "available_map_count"),
        "current_missing_map_count": len(missing_maps),
        "current_missing_maps": missing_maps,
        "candidate_inputs": [str(path) for path in candidates],
        "candidate_reports": candidate_reports,
        "candidate_valid_map_count": len([
            name for name in candidate_sources if name in target_set
        ]),
        "candidate_new_map_count": len(newly_available_maps),
        "candidate_new_maps": newly_available_maps,
        "candidate_extra_maps": candidate_extra_maps,
        "invalid_candidate_source_count": len(invalid_sources),
        "invalid_candidate_sources": invalid_sources,
        "copy_plan": copy_plan,
        "copy_plan_count": len(copy_plan),
        "missing_map_count_after_plan": len(missing_after_plan),
        "missing_maps_after_plan": missing_after_plan,
        "claim_posture": {
            "asset_intake_copies_game_data": False,
            "registered_asset_payload_bundled": False,
            "whole_game_moonlab_deployment_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "hardware_quantum_advantage_claimed": False,
        },
        "limits": [
            "This intake plan validates candidate registered BSP payloads but does not copy or bundle game data by default.",
            "Run the generated copy script only for assets you are licensed to install locally.",
            "A complete asset intake only unblocks capture jobs; it is not a whole-game Moonlab deployment claim.",
        ],
    }
    if discovery is not None:
        intake["discovery"] = discovery
        intake["discovered_candidate_count"] = discovery.get(
            "found_candidate_count", 0)
    return intake


def script_lines(intake: dict[str, Any]) -> list[str]:
    plan = [
        item for item in list_or_empty(intake.get("copy_plan"))
        if isinstance(item, dict)
    ]
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        f"repo_root={shell_quote(REPO_ROOT)}",
        'cd "$repo_root"',
        "",
        "echo QGE_REGISTERED_ASSET_INTAKE_LICENSE_CHECK",
        "echo 'Only run this script for registered Quake assets you may install locally.'",
        "",
        f"mkdir -p {shell_quote(Path(intake['current_asset_root']) / 'maps')}",
        "",
    ]
    for entry in plan:
        if entry.get("status") != "planned":
            lines.append(
                f"# skipped {entry.get('kind')} {entry.get('source')}: {entry.get('status')}"
            )
            continue
        lines.append(str(entry["command"]))
    lines.extend([
        "",
        "python3 tools/qge_asset_inventory.py \\",
        f"  --asset-root {shell_quote(intake['current_asset_root'])} \\",
        "  --json /tmp/qge_asset_inventory.after_intake.json \\",
        "  --markdown /tmp/qge_asset_inventory.after_intake.md",
        "",
    ])
    return lines


def markdown_report(intake: dict[str, Any]) -> str:
    lines = [
        "# QGE Registered Asset Intake",
        "",
        f"Status: {intake['status']}",
        f"Current asset root: `{intake['current_asset_root']}`",
        "",
        "| Map Set | Current Available | Current Missing | New Candidate Maps | Missing After Plan | Invalid Candidate Sources |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {intake.get('map_set')} | "
            f"{intake.get('current_available_map_count')} / "
            f"{intake.get('target_map_count')} | "
            f"{intake.get('current_missing_map_count')} | "
            f"{intake.get('candidate_new_map_count')} | "
            f"{intake.get('missing_map_count_after_plan')} | "
            f"{intake.get('invalid_candidate_source_count')} |"
        ),
        "",
    ]
    discovery = dict_or_empty(intake.get("discovery"))
    if discovery:
        lines.extend([
            "## Discovery",
            "",
            f"Roots scanned: {len(discovery.get('roots', []))}",
            f"Candidate paths found: {discovery.get('found_candidate_count')}",
            "",
        ])
    lines.extend([
        "## Candidate New Maps",
        "",
        ", ".join(intake.get("candidate_new_maps", [])) or "none",
        "",
        "## Copy Plan",
        "",
        "| Kind | Status | Source | Destination | Maps |",
        "| --- | --- | --- | --- | --- |",
    ])
    for entry in list_or_empty(intake.get("copy_plan")):
        if not isinstance(entry, dict):
            continue
        lines.append(
            f"| {entry.get('kind')} | {entry.get('status')} | "
            f"`{entry.get('source')}` | `{entry.get('destination')}` | "
            f"{', '.join(entry.get('maps_unblocked', []))} |"
        )
    if not intake.get("copy_plan"):
        lines.append("| none | blocked |  |  |  |")
    lines.extend([
        "",
        "## Remaining Missing Maps",
        "",
        ", ".join(intake.get("missing_maps_after_plan", [])) or "none",
        "",
    ])
    return "\n".join(lines)


def build_icc_evidence(
    intake: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_registered_asset_intake",
        "completion_reason": "qge_registered_asset_intake_plan_recorded",
        "status": "success",
        "asset_intake_file": str(out_path) if out_path else None,
        "intake_status": intake.get("status"),
        "map_set": intake.get("map_set"),
        "target_map_count": intake.get("target_map_count"),
        "current_available_map_count": intake.get("current_available_map_count"),
        "current_missing_map_count": intake.get("current_missing_map_count"),
        "candidate_new_map_count": intake.get("candidate_new_map_count"),
        "discovered_candidate_count": intake.get(
            "discovered_candidate_count", 0),
        "missing_map_count_after_plan": intake.get(
            "missing_map_count_after_plan"),
        "invalid_candidate_source_count": intake.get(
            "invalid_candidate_source_count"),
        "copy_plan_count": intake.get("copy_plan_count"),
        "asset_intake_copies_game_data": False,
        "registered_asset_payload_bundled": False,
        "whole_game_moonlab_deployment_claimed": False,
        "whole_game_hardware_execution_claimed": False,
        "hardware_quantum_advantage_claimed": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-root", type=Path,
                        default=qge_asset_inventory.DEFAULT_ASSET_ROOT)
    parser.add_argument("--candidate", action="append", type=Path,
                        default=[],
                        help="Candidate PAK/BSP file or directory to scan")
    parser.add_argument("--discover-root", action="append", type=Path,
                        default=[],
                        help="Root to scan for candidate PAK/BSP/id1 paths")
    parser.add_argument("--discover-common",
                        action=argparse.BooleanOptionalAction,
                        default=False,
                        help="Scan bounded common Quake install locations")
    parser.add_argument("--discover-max-depth", type=int, default=5)
    parser.add_argument("--map-set",
                        default=qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--script-out", type=Path)
    parser.add_argument("--icc-json", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.discover_max_depth < 0:
            raise ValueError("--discover-max-depth must be non-negative")
        discovery_roots: list[Path] = list(args.discover_root)
        if args.discover_common:
            discovery_roots.extend(common_discovery_roots())
        discovery = None
        candidates = list(args.candidate)
        if discovery_roots:
            discovery = discover_candidate_paths(
                discovery_roots,
                max_depth=args.discover_max_depth,
            )
            candidates.extend(
                Path(entry["path"])
                for entry in list_or_empty(discovery.get("found_candidates"))
                if isinstance(entry, dict) and isinstance(entry.get("path"), str)
            )
        if not candidates:
            raise ValueError(
                "provide --candidate, --discover-root, or --discover-common")
        intake = build_intake(
            args.current_root,
            candidates,
            map_set=args.map_set,
            discovery=discovery,
        )
        write_json(args.json, intake)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(intake), encoding="utf-8")
        if args.script_out:
            args.script_out.parent.mkdir(parents=True, exist_ok=True)
            args.script_out.write_text("\n".join(script_lines(intake)),
                                       encoding="utf-8")
        if args.icc_json:
            write_json(args.icc_json, build_icc_evidence(
                intake,
                out_path=args.json,
            ))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_registered_asset_intake: {exc}", file=sys.stderr)
        return 1

    print(f"QGE_REGISTERED_ASSET_INTAKE {args.json}")
    if args.markdown:
        print(f"QGE_REGISTERED_ASSET_INTAKE_MARKDOWN {args.markdown}")
    if args.script_out:
        print(f"QGE_REGISTERED_ASSET_INTAKE_SCRIPT {args.script_out}")
    if args.icc_json:
        print(f"QGE_REGISTERED_ASSET_INTAKE_ICC_EVIDENCE {args.icc_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
