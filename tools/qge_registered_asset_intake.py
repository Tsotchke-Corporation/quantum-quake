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
import re
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

STEAM_QUAKE_APP_ID = "2310"
STEAM_LIBRARYFOLDERS = [
    Path("~/Library/Application Support/Steam/steamapps/libraryfolders.vdf"),
    Path("~/.steam/steam/steamapps/libraryfolders.vdf"),
    Path("~/.local/share/Steam/steamapps/libraryfolders.vdf"),
]
COMMON_DISCOVERY_PATHS = [
    Path("~/Library/Application Support/Steam/steamapps/common/Quake"),
    Path("~/Library/Application Support/Steam/steamapps/common/Quake/id1"),
    Path("~/Library/Application Support/Steam/steamapps/common/Quake/rerelease/id1"),
    Path("~/Library/Application Support/GOG.com"),
    Path("~/GOG Games/Quake"),
    Path("~/Library/Application Support/Heroic"),
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


def vdf_value(value: str) -> str:
    return value.replace("\\\\", "\\")


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


def vdf_pairs(path: Path) -> dict[str, list[str]]:
    try:
        text = path.expanduser().read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    pairs: dict[str, list[str]] = {}
    for key, value in re.findall(r'"([^"]+)"\s+"([^"]*)"', text):
        pairs.setdefault(key.casefold(), []).append(vdf_value(value))
    return pairs


def unique_paths(paths: Sequence[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for raw_path in paths:
        path = raw_path.expanduser()
        key = str(path)
        try:
            key = str(path.resolve())
        except OSError:
            pass
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def steam_library_roots(
    libraryfolders_files: Sequence[Path] | None = None,
) -> list[Path]:
    roots: list[Path] = []
    for raw_file in libraryfolders_files or STEAM_LIBRARYFOLDERS:
        library_file = raw_file.expanduser()
        if library_file.is_file():
            roots.append(library_file.parent.parent)
        for value in vdf_pairs(library_file).get("path", []):
            if value:
                roots.append(Path(value))
    return unique_paths(roots)


def steamapps_dir(library_root: Path) -> Path:
    if library_root.name.casefold() == "steamapps":
        return library_root
    return library_root / "steamapps"


def steam_quake_install_dirs(library_root: Path) -> list[str]:
    install_dirs = ["Quake"]
    manifest = (
        steamapps_dir(library_root) /
        f"appmanifest_{STEAM_QUAKE_APP_ID}.acf"
    )
    for value in vdf_pairs(manifest).get("installdir", []):
        if value and value not in install_dirs:
            install_dirs.append(value)
    return install_dirs


def steam_quake_discovery_paths(
    libraryfolders_files: Sequence[Path] | None = None,
) -> list[Path]:
    paths: list[Path] = []
    for library_root in steam_library_roots(libraryfolders_files):
        common = steamapps_dir(library_root) / "common"
        for install_dir in steam_quake_install_dirs(library_root):
            root = common / install_dir
            paths.extend([
                root,
                root / "id1",
                root / "rerelease" / "id1",
            ])
    return unique_paths(paths)


def common_discovery_roots() -> list[Path]:
    return unique_paths(
        env_candidate_paths() +
        COMMON_DISCOVERY_PATHS +
        steam_quake_discovery_paths()
    )


def common_discovery_roots_summary(
    libraryfolders_files: Sequence[Path] | None = None,
) -> dict[str, Any]:
    steam_roots = steam_library_roots(libraryfolders_files)
    steam_paths = steam_quake_discovery_paths(libraryfolders_files)
    return {
        "env_candidate_count": len(env_candidate_paths()),
        "static_common_path_count": len(COMMON_DISCOVERY_PATHS),
        "steam_library_root_count": len(steam_roots),
        "steam_library_roots": [str(path) for path in steam_roots],
        "steam_quake_path_count": len(steam_paths),
        "steam_quake_paths": [str(path) for path in steam_paths],
    }


def discovery_metadata(discovery: dict[str, Any] | None) -> dict[str, Any]:
    metadata = common_discovery_roots_summary()
    if discovery is not None:
        metadata["roots_scanned_count"] = len(discovery.get("roots", []))
        metadata["found_candidate_count"] = discovery.get(
            "found_candidate_count")
    return metadata


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
            for child in candidate_asset_root_children(path):
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


def candidate_asset_root_children(path: Path) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    for parts in (
        ("id1",),
        ("Id1",),
        ("ID1",),
        ("rerelease", "id1"),
        ("rerelease", "Id1"),
        ("rerelease", "ID1"),
    ):
        child = path.joinpath(*parts)
        if not child.is_dir():
            continue
        try:
            key = str(child.resolve())
        except OSError:
            key = str(child)
        key = key.casefold()
        if key not in seen:
            seen.add(key)
            roots.append(child)
    return roots


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


def build_post_install_verification(
    current_root: Path,
    *,
    publication_pack_dir: Path | None = None,
) -> dict[str, Any]:
    inventory_json = Path("/tmp/qge_asset_inventory.after_intake.json")
    inventory_markdown = Path("/tmp/qge_asset_inventory.after_intake.md")
    commands: list[dict[str, Any]] = [
        {
            "kind": "asset_inventory",
            "shell_command": (
                "python3 tools/qge_asset_inventory.py "
                f"--asset-root {shell_quote(current_root)} "
                f"--json {shell_quote(inventory_json)} "
                f"--markdown {shell_quote(inventory_markdown)}"
            ),
            "json": str(inventory_json),
            "markdown": str(inventory_markdown),
        },
    ]
    if publication_pack_dir is not None:
        queue_json = Path("/tmp/qge_full_game_capture_queue.after_intake.json")
        queue_script = Path("/tmp/run_missing_maps.after_intake.sh")
        queue_markdown = Path("/tmp/qge_full_game_capture_queue.after_intake.md")
        commands.append({
            "kind": "capture_queue",
            "shell_command": (
                "python3 tools/qge_full_game_capture_queue.py "
                f"{shell_quote(publication_pack_dir)} "
                f"--asset-root {shell_quote(current_root)} "
                f"--out {shell_quote(queue_json)} "
                f"--script-out {shell_quote(queue_script)} "
                f"--markdown {shell_quote(queue_markdown)}"
            ),
            "json": str(queue_json),
            "script": str(queue_script),
            "markdown": str(queue_markdown),
        })
    return {
        "publication_pack": (
            str(publication_pack_dir) if publication_pack_dir is not None
            else None
        ),
        "command_count": len(commands),
        "commands": commands,
    }


def build_candidate_discovery_command(
    current_root: Path,
    *,
    publication_pack_dir: Path | None = None,
    discover_max_depth: int = 5,
) -> dict[str, Any]:
    intake_json = Path("/tmp/qge_registered_asset_intake.after_discovery.json")
    intake_markdown = Path("/tmp/qge_registered_asset_intake.after_discovery.md")
    install_script = Path("/tmp/install_registered_assets.after_discovery.sh")
    icc_json = Path(
        "/tmp/qge_registered_asset_intake.after_discovery.icc.json")
    command = (
        "python3 tools/qge_registered_asset_intake.py "
        f"--current-root {shell_quote(current_root)} "
        "--discover-common "
        f"--discover-max-depth {discover_max_depth} "
    )
    if publication_pack_dir is not None:
        command += f"--publication-pack {shell_quote(publication_pack_dir)} "
    command += (
        f"--json {shell_quote(intake_json)} "
        f"--markdown {shell_quote(intake_markdown)} "
        f"--script-out {shell_quote(install_script)} "
        f"--icc-json {shell_quote(icc_json)}"
    )
    return {
        "kind": "registered_asset_discovery",
        "shell_command": command,
        "discover_common": True,
        "discover_max_depth": discover_max_depth,
        "publication_pack": (
            str(publication_pack_dir) if publication_pack_dir is not None
            else None
        ),
        "json": str(intake_json),
        "markdown": str(intake_markdown),
        "script": str(install_script),
        "icc_json": str(icc_json),
    }


def registered_asset_blocker_reason(
    status: str,
    *,
    missing_map_count_after_plan: int,
    copy_plan_count: int,
    actionable_copy_plan_count: int | None = None,
) -> str | None:
    if missing_map_count_after_plan <= 0:
        return None
    if status == "blocked_no_candidate_assets" or copy_plan_count == 0:
        return "no_candidate_assets_found"
    if status == "blocked_candidate_copy_plan":
        return "candidate_copy_plan_blocked"
    if status == "partial_candidate_assets_found":
        return "partial_plan_remaining_registered_assets_missing"
    if actionable_copy_plan_count is not None and actionable_copy_plan_count <= 0:
        return "candidate_copy_plan_blocked"
    return "registered_assets_missing_after_plan"


def copy_script_mode(
    *,
    missing_map_count_after_plan: int,
    copy_plan_count: int,
    actionable_copy_plan_count: int | None = None,
) -> str:
    if actionable_copy_plan_count is None:
        actionable_copy_plan_count = copy_plan_count
    if missing_map_count_after_plan > 0 and copy_plan_count == 0:
        return "no_op_blocked"
    if missing_map_count_after_plan > 0 and actionable_copy_plan_count <= 0:
        return "blocked_copy_plan"
    if missing_map_count_after_plan > 0:
        return "partial_copy_plan"
    if actionable_copy_plan_count > 0:
        return "complete_copy_plan"
    return "verification_only"


def copy_plan_actionable_entries(copy_plan: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        entry for entry in copy_plan
        if entry.get("status") in {"planned", "already_present"}
    ]


def copy_plan_maps(
    copy_plan: Sequence[dict[str, Any]],
    *,
    statuses: set[str],
) -> set[str]:
    maps: set[str] = set()
    for entry in copy_plan:
        if entry.get("status") not in statuses:
            continue
        for map_name in list_or_empty(entry.get("maps_unblocked")):
            if isinstance(map_name, str):
                maps.add(map_name)
    return maps


def build_intake(
    current_root: Path,
    candidates: Sequence[Path],
    *,
    map_set: str = qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET,
    discovery: dict[str, Any] | None = None,
    publication_pack_dir: Path | None = None,
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
    scan_targets = candidate_scan_targets(candidates)
    candidate_reports = [scan_target(target) for target in scan_targets]
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
    actionable_copy_plan = copy_plan_actionable_entries(copy_plan)
    copy_plan_unblocked = copy_plan_maps(
        copy_plan,
        statuses={"planned", "already_present"},
    )
    post_install_verification = build_post_install_verification(
        current_root,
        publication_pack_dir=publication_pack_dir,
    )
    candidate_discovery = build_candidate_discovery_command(
        current_root,
        publication_pack_dir=publication_pack_dir,
    )
    newly_available_maps = [
        map_name for map_name in missing_maps
        if map_name in chosen_sources
    ]
    copy_plan_unblocked_maps = [
        map_name for map_name in missing_maps
        if map_name in copy_plan_unblocked
    ]
    copy_plan_blocked_maps = [
        map_name for map_name in newly_available_maps
        if map_name not in copy_plan_unblocked
    ]
    candidate_extra_maps = sorted(
        map_name for map_name in candidate_sources
        if map_name not in target_set
    )
    missing_after_plan = [
        map_name for map_name in missing_maps
        if map_name not in set(copy_plan_unblocked_maps)
    ]
    status = (
        "complete_after_plan" if not missing_after_plan else
        "partial_candidate_assets_found" if copy_plan_unblocked_maps else
        "blocked_candidate_copy_plan" if newly_available_maps else
        "blocked_no_candidate_assets"
    )
    blocker_reason = registered_asset_blocker_reason(
        status,
        missing_map_count_after_plan=len(missing_after_plan),
        copy_plan_count=len(copy_plan),
        actionable_copy_plan_count=len(actionable_copy_plan),
    )
    script_mode = copy_script_mode(
        missing_map_count_after_plan=len(missing_after_plan),
        copy_plan_count=len(copy_plan),
        actionable_copy_plan_count=len(actionable_copy_plan),
    )
    intake = {
        "schema": "qge.registered_asset_intake.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "current_asset_root": str(current_root),
        "map_set": map_set,
        "status": status,
        "target_map_count": len(target_maps),
        "current_available_map_count": current_inventory.get(
            "available_map_count"),
        "current_missing_map_count": len(missing_maps),
        "current_missing_maps": missing_maps,
        "candidate_inputs": [str(path) for path in candidates],
        "candidate_scan_target_count": len(scan_targets),
        "candidate_scan_targets": [
            {
                "kind": target.get("kind"),
                "path": str(target.get("path")),
            }
            for target in scan_targets
        ],
        "candidate_reports": candidate_reports,
        "discovered_candidate_count": 0,
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
        "actionable_copy_plan_count": len(actionable_copy_plan),
        "copy_plan_unblocked_map_count": len(copy_plan_unblocked_maps),
        "copy_plan_unblocked_maps": copy_plan_unblocked_maps,
        "copy_plan_blocked_map_count": len(copy_plan_blocked_maps),
        "copy_plan_blocked_maps": copy_plan_blocked_maps,
        "candidate_discovery": candidate_discovery,
        "candidate_discovery_command": (
            candidate_discovery["shell_command"]),
        "post_install_verification": post_install_verification,
        "post_install_verification_command_count": (
            post_install_verification["command_count"]),
        "missing_map_count_after_plan": len(missing_after_plan),
        "missing_maps_after_plan": missing_after_plan,
        "manual_registered_asset_required": bool(missing_after_plan),
        "registered_asset_blocker_reason": blocker_reason,
        "copy_script_mode": script_mode,
        "no_candidate_asset_copy_plan": (
            bool(missing_after_plan) and not copy_plan
        ),
        "registered_asset_blocker": {
            "blocked": bool(missing_after_plan),
            "reason": blocker_reason,
            "missing_map_count_after_plan": len(missing_after_plan),
            "missing_maps_after_plan": missing_after_plan,
            "candidate_new_map_count": len(newly_available_maps),
            "copy_plan_unblocked_map_count": len(copy_plan_unblocked_maps),
            "copy_plan_blocked_map_count": len(copy_plan_blocked_maps),
            "copy_plan_count": len(copy_plan),
            "actionable_copy_plan_count": len(actionable_copy_plan),
            "candidate_discovery_command": (
                candidate_discovery["shell_command"]),
        },
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
        intake["discovery_metadata"] = discovery_metadata(discovery)
    return intake


def script_lines(intake: dict[str, Any]) -> list[str]:
    plan = [
        item for item in list_or_empty(intake.get("copy_plan"))
        if isinstance(item, dict)
    ]
    missing_after_plan = [
        item for item in list_or_empty(intake.get("missing_maps_after_plan"))
        if isinstance(item, str)
    ]
    mode = intake.get("copy_script_mode")
    if not isinstance(mode, str):
        actionable_count = len(copy_plan_actionable_entries(plan))
        mode = copy_script_mode(
            missing_map_count_after_plan=len(missing_after_plan),
            copy_plan_count=len(plan),
            actionable_copy_plan_count=actionable_count,
        )
    blocker_reason = intake.get("registered_asset_blocker_reason")
    if not isinstance(blocker_reason, str):
        actionable_count = len(copy_plan_actionable_entries(plan))
        blocker_reason = registered_asset_blocker_reason(
            str(intake.get("status") or ""),
            missing_map_count_after_plan=len(missing_after_plan),
            copy_plan_count=len(plan),
            actionable_copy_plan_count=actionable_count,
        )
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        f"repo_root={shell_quote(REPO_ROOT)}",
        'cd "$repo_root"',
        "",
        "verify_sha256() {",
        "  local path=\"$1\"",
        "  local expected=\"$2\"",
        "  [[ -n \"$expected\" ]] || return 0",
        "  python3 - \"$path\" \"$expected\" <<'PY'",
        "import hashlib",
        "import pathlib",
        "import sys",
        "path = pathlib.Path(sys.argv[1])",
        "expected = sys.argv[2].lower()",
        "actual = hashlib.sha256(path.read_bytes()).hexdigest()",
        "if actual != expected:",
        "    raise SystemExit(f\"sha256 mismatch for {path}: {actual} != {expected}\")",
        "PY",
        "}",
        "",
        "copy_registered_asset() {",
        "  local source=\"$1\"",
        "  local destination=\"$2\"",
        "  local expected_sha=\"$3\"",
        "  mkdir -p \"$(dirname \"$destination\")\"",
        "  if [[ -e \"$destination\" ]]; then",
        "    echo \"QGE_REGISTERED_ASSET_DESTINATION_EXISTS $destination\"",
        "    verify_sha256 \"$destination\" \"$expected_sha\"",
        "    return 0",
        "  fi",
        "  cp -n \"$source\" \"$destination\"",
        "  verify_sha256 \"$destination\" \"$expected_sha\"",
        "}",
        "",
        "echo QGE_REGISTERED_ASSET_INTAKE_LICENSE_CHECK",
        "echo 'Only run this script for registered Quake assets you may install locally.'",
        f"echo QGE_REGISTERED_ASSET_COPY_SCRIPT_MODE {shell_quote(mode)}",
        "",
    ]
    if missing_after_plan:
        lines.extend([
            (
                "echo QGE_REGISTERED_ASSET_MISSING_MAP_COUNT "
                f"{len(missing_after_plan)}"
            ),
            (
                "echo QGE_REGISTERED_ASSET_MISSING_MAPS "
                f"{shell_quote(' '.join(missing_after_plan))}"
            ),
        ])
        if blocker_reason:
            lines.append(
                "echo QGE_REGISTERED_ASSET_BLOCKER_REASON "
                f"{shell_quote(blocker_reason)}"
            )
        actionable_plan = copy_plan_actionable_entries(plan)
        if not plan:
            lines.extend([
                "echo QGE_REGISTERED_ASSET_NO_CANDIDATES",
                (
                    "echo 'No registered asset copy plan was generated; "
                    "place licensed registered Quake assets in a scanned "
                    "root and rerun qge_registered_asset_intake.py.'"
                ),
            ])
        elif not actionable_plan:
            lines.extend([
                "echo QGE_REGISTERED_ASSET_BLOCKED_COPY_PLAN",
                (
                    "echo 'Registered asset candidates were found, but the "
                    "copy plan has no actionable copy operations; inspect "
                    "blocked copy-plan entries before rerunning.'"
                ),
            ])
        else:
            lines.append("echo QGE_REGISTERED_ASSET_PARTIAL_COPY_PLAN")
        lines.append("")
    else:
        lines.extend([
            "echo QGE_REGISTERED_ASSET_COPY_PLAN_COMPLETE",
            "",
        ])
    for entry in plan:
        if entry.get("status") != "planned":
            lines.append(
                f"# skipped {entry.get('kind')} {entry.get('source')}: {entry.get('status')}"
            )
            continue
        lines.append(
            "copy_registered_asset "
            f"{shell_quote(entry.get('source', ''))} "
            f"{shell_quote(entry.get('destination', ''))} "
            f"{shell_quote(entry.get('source_sha256') or '')}"
        )
    post_install = dict_or_empty(intake.get("post_install_verification"))
    for command in list_or_empty(post_install.get("commands")):
        if not isinstance(command, dict):
            continue
        lines.extend([
            "",
            f"echo QGE_REGISTERED_ASSET_POST_INSTALL {command.get('kind')}",
            str(command.get("shell_command")),
        ])
    lines.append("")
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
    discovery_meta = dict_or_empty(intake.get("discovery_metadata"))
    if discovery:
        lines.extend([
            "## Discovery",
            "",
            f"Roots scanned: {len(discovery.get('roots', []))}",
            f"Candidate paths found: {discovery.get('found_candidate_count')}",
            "",
        ])
        if discovery_meta:
            lines.extend([
                "| Common Discovery Signal | Count |",
                "| --- | ---: |",
                (
                    "| Env candidate paths | "
                    f"{discovery_meta.get('env_candidate_count', 0)} |"
                ),
                (
                    "| Static common paths | "
                    f"{discovery_meta.get('static_common_path_count', 0)} |"
                ),
                (
                    "| Steam library roots | "
                    f"{discovery_meta.get('steam_library_root_count', 0)} |"
                ),
                (
                    "| Steam Quake candidate paths | "
                    f"{discovery_meta.get('steam_quake_path_count', 0)} |"
                ),
                "",
            ])
    if intake.get("manual_registered_asset_required"):
        lines.extend([
            "## Blocker Summary",
            "",
            "Manual licensed registered assets required: yes",
            (
                "Reason: `"
                f"{intake.get('registered_asset_blocker_reason')}`"
            ),
            f"Copy script mode: `{intake.get('copy_script_mode')}`",
            (
                "No copy operations are planned yet; rerun discovery after "
                "placing licensed registered Quake assets in a scanned root."
                if intake.get("no_candidate_asset_copy_plan")
                else (
                    "Candidate assets were found, but the copy plan has no "
                    "actionable operations; inspect blocked copy-plan entries."
                    if intake.get("copy_script_mode") == "blocked_copy_plan"
                    else (
                        "The copy plan is partial; remaining missing maps still "
                        "require licensed registered assets."
                    )
                )
            ),
            (
                "The whole-game Moonlab deployment claim remains blocked "
                "until every remaining registered BSP is present and capture "
                "evidence is regenerated."
            ),
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
    discovery_command = dict_or_empty(intake.get("candidate_discovery"))
    if discovery_command:
        lines.extend([
            "",
            "## Candidate Discovery Refresh",
            "",
            (
                "`"
                f"{discovery_command.get('shell_command')}"
                "`"
            ),
        ])
    lines.extend([
        "",
        "## Post-Install Verification",
        "",
        "| Kind | Command |",
        "| --- | --- |",
    ])
    post_install = dict_or_empty(intake.get("post_install_verification"))
    wrote_command = False
    for command in list_or_empty(post_install.get("commands")):
        if not isinstance(command, dict):
            continue
        wrote_command = True
        lines.append(
            f"| {command.get('kind')} | `{command.get('shell_command')}` |"
        )
    if not wrote_command:
        lines.append("| none |  |")
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
    discovery_meta = dict_or_empty(intake.get("discovery_metadata"))
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
        "candidate_scan_target_count": intake.get(
            "candidate_scan_target_count"),
        "candidate_scan_targets": intake.get("candidate_scan_targets"),
        "discovered_candidate_count": intake.get(
            "discovered_candidate_count", 0),
        "discovery_roots_scanned_count": discovery_meta.get(
            "roots_scanned_count", 0),
        "discovery_metadata": discovery_meta,
        "env_candidate_count": discovery_meta.get("env_candidate_count", 0),
        "static_common_path_count": discovery_meta.get(
            "static_common_path_count", 0),
        "steam_library_root_count": discovery_meta.get(
            "steam_library_root_count", 0),
        "steam_quake_path_count": discovery_meta.get(
            "steam_quake_path_count", 0),
        "missing_map_count_after_plan": intake.get(
            "missing_map_count_after_plan"),
        "missing_maps_after_plan": intake.get("missing_maps_after_plan"),
        "manual_registered_asset_required": bool(
            intake.get("manual_registered_asset_required")),
        "registered_asset_blocker_reason": intake.get(
            "registered_asset_blocker_reason"),
        "copy_script_mode": intake.get("copy_script_mode"),
        "no_candidate_asset_copy_plan": bool(
            intake.get("no_candidate_asset_copy_plan")),
        "actionable_copy_plan_count": intake.get("actionable_copy_plan_count"),
        "copy_plan_unblocked_map_count": intake.get(
            "copy_plan_unblocked_map_count"),
        "copy_plan_unblocked_maps": intake.get("copy_plan_unblocked_maps"),
        "copy_plan_blocked_map_count": intake.get(
            "copy_plan_blocked_map_count"),
        "copy_plan_blocked_maps": intake.get("copy_plan_blocked_maps"),
        "invalid_candidate_source_count": intake.get(
            "invalid_candidate_source_count"),
        "copy_plan_count": intake.get("copy_plan_count"),
        "candidate_discovery_command": intake.get(
            "candidate_discovery_command"),
        "candidate_discovery_script": dict_or_empty(
            intake.get("candidate_discovery")).get("script"),
        "post_install_verification_command_count": intake.get(
            "post_install_verification_command_count"),
        "post_install_capture_queue_command_present": any(
            isinstance(command, dict) and command.get("kind") == "capture_queue"
            for command in list_or_empty(dict_or_empty(
                intake.get("post_install_verification")).get("commands"))
        ),
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
    parser.add_argument("--publication-pack", type=Path,
                        help="Optional publication pack used to generate a post-install capture queue command")
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
        if not candidates and not discovery_roots:
            raise ValueError(
                "provide --candidate, --discover-root, or --discover-common")
        intake = build_intake(
            args.current_root,
            candidates,
            map_set=args.map_set,
            discovery=discovery,
            publication_pack_dir=args.publication_pack,
        )
        write_json(args.json, intake)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(intake), encoding="utf-8")
        if args.script_out:
            args.script_out.parent.mkdir(parents=True, exist_ok=True)
            args.script_out.write_text("\n".join(script_lines(intake)),
                                       encoding="utf-8")
            args.script_out.chmod(args.script_out.stat().st_mode | 0o111)
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
