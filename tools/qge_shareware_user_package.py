#!/usr/bin/env python3
"""Build a player-facing Quantum Quake shareware package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_map_sets  # noqa: E402


READY_STATUS = "ready_for_shareware_user_package"
BLOCKED = "blocked"
PASS = "pass"
SHAREWARE_MAP_SET = qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ROOT_NAME = "QuantumQuake-shareware-macos"
EVIDENCE_DIR = "release_evidence"
PLAYABILITY_GATE_EVIDENCE = (
    f"{EVIDENCE_DIR}/qge_shareware_playability_gate.json")
COMPLETE_EFFECTS_GATE_EVIDENCE = (
    f"{EVIDENCE_DIR}/qge_shareware_complete_effects_gate.json")
COMPLETE_EFFECTS_READY_STATUS = "ready_for_shareware_complete_effects_claim"

RELEASE_CFG = """\
cl_startdemos 0
developer 0
con_notifytime 3
quantum_debug 0
quantum_render 1
quantum_render_res 768
quantum_render_threshold 0.001
quantum_render_edge_gain 0.03
quantum_render_material_gain 0.18
quantum_render_bilinear_samples 1
quantum_render_edge_samples 0
quantum_render_display_filter 0
quantum_render_update_interval 1
quantum_rng 1
quantum_ai 1
quantum_physics 1
quantum_projectiles 1
quantum_shareware_encounter 1
snd_quantum 1
"""

DEEP_CFG = """\
exec quantum_quake_release.cfg
quantum_render 2
quantum_render_res 768
quantum_overlay_alpha 0.10
"""


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
        return default


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def load_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_mode(path: Path) -> int:
    mode = stat.S_IMODE(path.lstat().st_mode)
    if mode & 0o111:
        return 0o755
    return 0o644


def relative_manifest_path(path: Path, package_dir: Path) -> str:
    return path.relative_to(package_dir).as_posix()


def launch_script(config_name: str) -> str:
    return f"""\
#!/bin/sh
set -eu
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$DIR/QuantumQuake.app/Contents/MacOS/quantum_quake" -basedir "$DIR/assets" +cl_startdemos 0 +exec {config_name}
"""


def readme_text(playability_gate: dict[str, Any]) -> str:
    summary = dict_or_empty(playability_gate.get("summary"))
    return "\n".join([
        "Quantum Quake Shareware Release",
        "",
        "Run Play Quantum Quake.command to play the shareware episode.",
        "Run Play Quantum Quake Deep Mode.command for the primary QGE renderer.",
        "",
        "This package contains QuantumQuake.app and the Quake shareware",
        "Episode 1 data in assets/id1/pak0.pak.",
        "",
        "What makes this Quantum Quake:",
        "- QGE runtime systems are enabled by default: quantum RNG, AI,",
        "  physics, projectiles, shareware encounter logic, rendering, and",
        "  spatial audio hooks.",
        "- Projectile and weapon outcomes are driven by simulator branch and",
        "  measurement events that write back into gameplay state; they are",
        "  not only a post-process visual overlay.",
        "- Deep Mode enables the primary QGE renderer for stronger phase,",
        "  interference, material, and branch-feedback visibility.",
        "- The release_evidence directory contains the playability and",
        "  complete-effects gates used to sign off this exact package.",
        "",
        "Coverage evidence:",
        f"- map set: {SHAREWARE_MAP_SET}",
        (
            "- runtime maps: "
            f"{summary.get('runtime_covered_map_count')} / "
            f"{summary.get('runtime_target_map_count')}"
        ),
        f"- PAK entries: {summary.get('pak_entry_count')}",
        f"- effects gate: {summary.get('effects_gate_status')}",
        "",
        "This package does not include or authorize registered/full-game data.",
        "It also does not claim hardware quantum advantage, quantum supremacy,",
        "exponential speedup, whole-game hardware execution, or dense",
        "70,000-qubit hardware execution.",
        "",
    ])


def remove_generated_package(package_dir: Path, outdir: Path) -> None:
    if not package_dir.exists():
        return
    resolved_outdir = outdir.resolve()
    resolved_package = package_dir.resolve()
    if resolved_package == resolved_outdir:
        raise ValueError(f"refusing to replace output root: {package_dir}")
    if resolved_outdir not in resolved_package.parents:
        raise ValueError(f"refusing to replace package outside outdir: {package_dir}")
    shutil.rmtree(package_dir)


def copy_payload(
    *,
    app: Path,
    pak: Path,
    package_dir: Path,
    playability_gate: dict[str, Any],
    playability_gate_path: Path,
    effects_gate_path: Path | None,
    replace: bool,
) -> None:
    if not app.is_dir():
        raise ValueError(f"QuantumQuake.app not found: {app}")
    app_binary = app / "Contents" / "MacOS" / "quantum_quake"
    if not app_binary.is_file():
        raise ValueError(f"QuantumQuake executable not found: {app_binary}")
    if not pak.is_file():
        raise ValueError(f"shareware pak0.pak not found: {pak}")
    if package_dir.exists() and not replace:
        raise ValueError(f"package directory already exists: {package_dir}")
    remove_generated_package(package_dir, package_dir.parent)
    package_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(
        app,
        package_dir / "QuantumQuake.app",
        symlinks=True,
        copy_function=shutil.copy2,
    )
    id1_dir = package_dir / "assets" / "id1"
    id1_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pak, id1_dir / "pak0.pak")
    (id1_dir / "quantum_quake_release.cfg").write_text(
        RELEASE_CFG,
        encoding="utf-8",
    )
    (id1_dir / "quantum_quake_deep.cfg").write_text(
        DEEP_CFG,
        encoding="utf-8",
    )

    launchers = {
        "Play Quantum Quake.command": "quantum_quake_release.cfg",
        "Play Quantum Quake Deep Mode.command": "quantum_quake_deep.cfg",
    }
    for launcher, config_name in launchers.items():
        path = package_dir / launcher
        path.write_text(launch_script(config_name), encoding="utf-8")
        path.chmod(0o755)
    (package_dir / "README.txt").write_text(
        readme_text(playability_gate),
        encoding="utf-8",
    )
    evidence_dir = package_dir / EVIDENCE_DIR
    evidence_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        playability_gate_path,
        evidence_dir / "qge_shareware_playability_gate.json",
    )
    if effects_gate_path is not None:
        shutil.copy2(
            effects_gate_path,
            evidence_dir / "qge_shareware_complete_effects_gate.json",
        )


def package_manifest(package_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(package_dir.rglob("*"),
                       key=lambda item: item.relative_to(package_dir).as_posix()):
        rel = relative_manifest_path(path, package_dir)
        st = path.lstat()
        if stat.S_ISDIR(st.st_mode):
            entries.append({
                "path": rel,
                "type": "directory",
                "archive_mode": f"{stat.S_IMODE(st.st_mode):04o}",
            })
        elif stat.S_ISLNK(st.st_mode):
            entries.append({
                "path": rel,
                "type": "symlink",
                "target": os.readlink(path),
                "archive_mode": "0777",
            })
        elif stat.S_ISREG(st.st_mode):
            entries.append({
                "path": rel,
                "type": "file",
                "size_bytes": path.stat().st_size,
                "archive_mode": f"{archive_mode(path):04o}",
                "sha256": sha256_file(path),
            })
    return entries


def zipinfo_for(name: str, mode: int, file_type: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=name, date_time=ZIP_TIMESTAMP)
    info.create_system = 3
    info.external_attr = (file_type | mode) << 16
    if file_type == stat.S_IFDIR:
        info.external_attr |= 0x10
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def archive_package(package_dir: Path, archive_path: Path, *,
                    root_name: str) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()
    paths = [package_dir] + sorted(
        package_dir.rglob("*"),
        key=lambda item: item.relative_to(package_dir).as_posix(),
    )
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in paths:
            if path == package_dir:
                rel = ""
            else:
                rel = path.relative_to(package_dir).as_posix()
            name = f"{root_name}/{rel}".rstrip("/")
            st = path.lstat()
            if stat.S_ISDIR(st.st_mode):
                info = zipinfo_for(name + "/", stat.S_IMODE(st.st_mode),
                                   stat.S_IFDIR)
                archive.writestr(info, b"")
            elif stat.S_ISLNK(st.st_mode):
                info = zipinfo_for(name, 0o777, stat.S_IFLNK)
                archive.writestr(info, os.readlink(path).encode("utf-8"))
            elif stat.S_ISREG(st.st_mode):
                info = zipinfo_for(name, archive_mode(path), stat.S_IFREG)
                archive.writestr(info, path.read_bytes())


def zip_entry_report(archive_path: Path) -> dict[str, Any]:
    if not archive_path.is_file():
        return {
            "entry_count": 0,
            "symlink_entry_count": 0,
            "names": [],
        }
    names: list[str] = []
    symlink_count = 0
    executable_entries: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            names.append(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            permissions = (info.external_attr >> 16) & 0o777
            if mode == stat.S_IFLNK:
                symlink_count += 1
            if permissions & 0o111 and mode == stat.S_IFREG:
                executable_entries.append(info.filename)
    return {
        "entry_count": len(names),
        "symlink_entry_count": symlink_count,
        "names": names,
        "executable_entries": executable_entries,
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


def criterion_passed(report: dict[str, Any], criterion_id: str) -> bool:
    return any(
        dict_or_empty(item).get("id") == criterion_id and
        dict_or_empty(item).get("status") == PASS
        for item in list_or_empty(report.get("criteria"))
    )


def playability_gate_ready(playability_gate: dict[str, Any]) -> bool:
    summary = dict_or_empty(playability_gate.get("summary"))
    return (
        playability_gate.get("schema") == "qge.shareware_playability_gate.v0"
        and playability_gate.get("status") ==
        "ready_for_shareware_user_playable_release" and
        playability_gate.get("shareware_user_playable_release_ready") is True
        and int_value(playability_gate.get("blocker_count")) == 0 and
        int_value(summary.get("runtime_covered_map_count")) == 9 and
        int_value(summary.get("runtime_target_map_count")) == 9 and
        int_value(summary.get("pak_entry_count")) >= 339 and
        summary.get("effects_gate_status") == COMPLETE_EFFECTS_READY_STATUS and
        int_value(summary.get("effects_footage_capture_count")) > 0 and
        criterion_passed(playability_gate, "complete_effects_and_content_runtime")
    )


def complete_effects_gate_ready(effects_gate: dict[str, Any]) -> bool:
    summary = dict_or_empty(effects_gate.get("summary"))
    matrix_summary = dict_or_empty(summary.get("matrix_summary"))
    return (
        effects_gate.get("schema") == "qge.shareware_complete_effects_gate.v0"
        and effects_gate.get("status") == COMPLETE_EFFECTS_READY_STATUS and
        summary.get("ready_for_complete_effects_claim") is True and
        int_value(matrix_summary.get("missing_enemy_class_count")) == 0 and
        int_value(matrix_summary.get("missing_material_class_count")) == 0 and
        int_value(matrix_summary.get("missing_weapon_class_count")) == 0 and
        int_value(matrix_summary.get("missing_noesis_evidence_map_count")) == 0
        and int_value(matrix_summary.get("runtime_footage_capture_count")) > 0
    )


def build_criteria(
    *,
    package_dir: Path,
    archive_path: Path,
    entries: list[dict[str, Any]],
    zip_report: dict[str, Any],
    playability_gate: dict[str, Any],
    effects_gate: dict[str, Any],
) -> list[dict[str, Any]]:
    entry_paths = {str(item.get("path")) for item in entries}
    symlink_count = sum(1 for item in entries if item.get("type") == "symlink")
    launcher_paths = {
        "Play Quantum Quake.command",
        "Play Quantum Quake Deep Mode.command",
    }
    config_paths = {
        "assets/id1/quantum_quake_release.cfg",
        "assets/id1/quantum_quake_deep.cfg",
    }
    zip_names = set(dict_or_empty(zip_report).get("names") or [])
    root = package_dir.name
    launcher_modes = {
        item.get("path"): item.get("archive_mode")
        for item in entries
        if item.get("path") in launcher_paths
    }
    package_has_app = (
        "QuantumQuake.app/Contents/MacOS/quantum_quake" in entry_paths and
        "QuantumQuake.app/Contents/Info.plist" in entry_paths and
        symlink_count >= 1
    )
    package_has_shareware_payload = (
        "assets/id1/pak0.pak" in entry_paths and
        "assets/id1/autoexec.cfg" not in entry_paths and
        "assets/id1/qge_harness_classic.cfg" not in entry_paths
    )
    package_has_gate_evidence = (
        PLAYABILITY_GATE_EVIDENCE in entry_paths and
        COMPLETE_EFFECTS_GATE_EVIDENCE in entry_paths and
        playability_gate_ready(playability_gate) and
        complete_effects_gate_ready(effects_gate)
    )
    package_has_launchers = (
        launcher_paths <= entry_paths and
        config_paths <= entry_paths and
        all(str(launcher_modes.get(path)) == "0755"
            for path in launcher_paths)
    )
    archive_ready = (
        archive_path.is_file() and
        archive_path.stat().st_size > 0 and
        dict_or_empty(zip_report).get("symlink_entry_count", 0) >= 1 and
        f"{root}/QuantumQuake.app/Contents/MacOS/quantum_quake" in zip_names and
        f"{root}/assets/id1/pak0.pak" in zip_names and
        f"{root}/Play Quantum Quake.command" in zip_names and
        f"{root}/{PLAYABILITY_GATE_EVIDENCE}" in zip_names and
        f"{root}/{COMPLETE_EFFECTS_GATE_EVIDENCE}" in zip_names
    )
    return [
        criterion(
            "shareware_player_app_bundle_present",
            "QuantumQuake.app is copied with executable and framework symlinks",
            package_has_app,
            "QuantumQuake.app or required app symlinks are missing",
            symlink_count=symlink_count,
        ),
        criterion(
            "shareware_player_pak_present",
            "The package includes pak0.pak and excludes capture automation configs",
            package_has_shareware_payload,
            "shareware pak0.pak is missing or automation configs were included",
            has_pak="assets/id1/pak0.pak" in entry_paths,
            has_autoexec="assets/id1/autoexec.cfg" in entry_paths,
            has_harness="assets/id1/qge_harness_classic.cfg" in entry_paths,
        ),
        criterion(
            "shareware_player_launchers_present",
            "Player launchers and release QGE configs are present and executable",
            package_has_launchers,
            "launchers or release configs are missing or not executable",
            launcher_modes=launcher_modes,
        ),
        criterion(
            "shareware_player_playability_gate_ready",
            "The package is backed by the no-exceptions shareware playability gate",
            playability_gate_ready(playability_gate),
            "shareware playability gate is blocked or incomplete",
            playability_gate_status=playability_gate.get("status"),
            playability_gate_summary=dict_or_empty(
                playability_gate.get("summary")),
        ),
        criterion(
            "shareware_player_final_gate_evidence_present",
            "The package includes final playability and complete-effects gate evidence",
            package_has_gate_evidence,
            "final playability or complete-effects gate evidence is missing or blocked",
            has_playability_gate=PLAYABILITY_GATE_EVIDENCE in entry_paths,
            has_complete_effects_gate=(
                COMPLETE_EFFECTS_GATE_EVIDENCE in entry_paths),
            playability_gate_status=playability_gate.get("status"),
            complete_effects_gate_status=effects_gate.get("status"),
        ),
        criterion(
            "shareware_player_archive_ready",
            "The player-facing archive exists and preserves app, pak, and final gate evidence",
            archive_ready,
            "player archive is missing, empty, or lacks expected entries",
            archive=str(archive_path),
            zip_entry_count=dict_or_empty(zip_report).get("entry_count"),
            zip_symlink_entry_count=dict_or_empty(zip_report).get(
                "symlink_entry_count"),
        ),
    ]


def build_package(
    *,
    app: Path,
    pak: Path,
    playability_gate_path: Path,
    effects_gate_path: Path | None = None,
    outdir: Path,
    name: str = ROOT_NAME,
    replace: bool = True,
) -> dict[str, Any]:
    playability_gate = load_json_object(playability_gate_path)
    effects_gate: dict[str, Any] = {}
    if effects_gate_path is not None:
        if not effects_gate_path.is_file():
            raise ValueError(
                f"shareware complete-effects gate not found: {effects_gate_path}"
            )
        effects_gate = load_json_object(effects_gate_path)
    package_dir = outdir / name
    archive_path = outdir / f"{name}.zip"
    copy_payload(
        app=app,
        pak=pak,
        package_dir=package_dir,
        playability_gate=playability_gate,
        playability_gate_path=playability_gate_path,
        effects_gate_path=effects_gate_path,
        replace=replace,
    )
    entries = package_manifest(package_dir)
    archive_package(package_dir, archive_path, root_name=name)
    zip_report = zip_entry_report(archive_path)
    criteria = build_criteria(
        package_dir=package_dir,
        archive_path=archive_path,
        entries=entries,
        zip_report=zip_report,
        playability_gate=playability_gate,
        effects_gate=effects_gate,
    )
    blockers = failed_criteria(criteria)
    ready = not blockers
    app_binary = package_dir / "QuantumQuake.app" / "Contents" / "MacOS" / "quantum_quake"
    pak_path = package_dir / "assets" / "id1" / "pak0.pak"
    return {
        "schema": "qge.shareware_user_package.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": READY_STATUS if ready else BLOCKED,
        "map_set": SHAREWARE_MAP_SET,
        "shareware_user_package_ready": ready,
        "shareware_user_playable_release_ready": ready,
        "package_dir": str(package_dir),
        "criteria": criteria,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "failed_criterion_count": len(blockers),
        "archive": {
            "path": str(archive_path),
            "sha256": sha256_file(archive_path) if archive_path.is_file() else None,
            "size_bytes": archive_path.stat().st_size
            if archive_path.is_file() else 0,
            "root_name": name,
        },
        "summary": {
            "app_binary": str(app_binary),
            "app_binary_size_bytes": app_binary.stat().st_size
            if app_binary.is_file() else 0,
            "shareware_pak": str(pak_path),
            "shareware_pak_sha256": sha256_file(pak_path)
            if pak_path.is_file() else None,
            "file_count": sum(1 for item in entries
                              if item.get("type") == "file"),
            "symlink_count": sum(1 for item in entries
                                 if item.get("type") == "symlink"),
            "zip_entry_count": zip_report.get("entry_count"),
            "zip_symlink_entry_count": zip_report.get(
                "symlink_entry_count"),
            "playability_gate": str(playability_gate_path),
            "playability_gate_status": playability_gate.get("status"),
            "playability_gate_evidence": str(
                package_dir / PLAYABILITY_GATE_EVIDENCE),
            "complete_effects_gate": (
                str(effects_gate_path) if effects_gate_path else None),
            "complete_effects_gate_status": effects_gate.get("status"),
            "complete_effects_gate_evidence": str(
                package_dir / COMPLETE_EFFECTS_GATE_EVIDENCE),
        },
        "file_manifest": entries,
        "limits": [
            "This player package covers the Quake shareware Episode 1 release only.",
            "It does not include or authorize registered/full-game assets.",
        ],
    }


def archive_checksum_record(package: dict[str, Any]) -> dict[str, Any]:
    archive = dict_or_empty(package.get("archive"))
    return {
        "schema": "qge.shareware_user_package_archive_checksum.v0",
        "kind": "artifact",
        "name": "shareware_user_package_archive_checksum_file",
        "archive_file": archive.get("path"),
        "archive_sha256": archive.get("sha256"),
        "archive_size_bytes": archive.get("size_bytes"),
        "map_set": package.get("map_set"),
        "package_status": package.get("status"),
        "shareware_user_package_ready": package.get(
            "shareware_user_package_ready"),
    }


def build_icc_evidence(
    package: dict[str, Any],
    *,
    manifest_path: Path,
    archive_checksum_path: Path,
) -> dict[str, Any]:
    archive = dict_or_empty(package.get("archive"))
    summary = dict_or_empty(package.get("summary"))
    ready = package.get("shareware_user_package_ready") is True
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_shareware_user_package",
        "completion_reason": (
            "qge_shareware_user_package_ready"
            if ready else "qge_shareware_user_package_blocked"),
        "status": "success",
        "runtime_backend_scope_map_set": SHAREWARE_MAP_SET,
        "release_scope": SHAREWARE_MAP_SET,
        "map_set": SHAREWARE_MAP_SET,
        "shareware_user_package_ready": ready,
        "shareware_user_playable_release_ready": ready,
        "shareware_user_package_manifest_file": str(manifest_path),
        "qge_shareware_user_package.json": str(manifest_path),
        "shareware_user_package_app_bundle": summary.get("app_binary"),
        "shareware_user_package_app_bundle_completion": (
            "present" if ready else "missing"),
        "shareware_user_package_pak_file": summary.get("shareware_pak"),
        "shareware_user_package_pak_completion": (
            "present" if ready else "missing"),
        "shareware_user_package_playability_gate_file": summary.get(
            "playability_gate_evidence"),
        "shareware_user_package_complete_effects_gate_file": summary.get(
            "complete_effects_gate_evidence"),
        "shareware_playability_gate_file": summary.get(
            "playability_gate_evidence"),
        "qge_shareware_playability_gate.json": summary.get(
            "playability_gate_evidence"),
        "shareware_complete_effects_gate_file": summary.get(
            "complete_effects_gate_evidence"),
        "qge_shareware_complete_effects_gate.json": summary.get(
            "complete_effects_gate_evidence"),
        "shareware_complete_effects_gate_status": summary.get(
            "complete_effects_gate_status"),
        "shareware_user_package_archive_checksum_file": str(
            archive_checksum_path),
        "qge_shareware_user_package_archive_checksum.json": str(
            archive_checksum_path),
        "shareware_user_package_archive_file": archive.get("path"),
        "shareware_user_package_archive_sha256": archive.get("sha256"),
        "shareware_user_package_archive_size_bytes": archive.get(
            "size_bytes"),
    }


def markdown_report(package: dict[str, Any]) -> str:
    archive = dict_or_empty(package.get("archive"))
    summary = dict_or_empty(package.get("summary"))
    lines = [
        "# QGE Shareware User Package",
        "",
        f"Status: `{package.get('status')}`",
        f"Map set: `{package.get('map_set')}`",
        "",
        "| Field | Value |",
        "| --- | ---: |",
        f"| package dir | {package.get('package_dir')} |",
        f"| archive | {archive.get('path')} |",
        f"| archive sha256 | {archive.get('sha256')} |",
        f"| archive bytes | {archive.get('size_bytes')} |",
        f"| files | {summary.get('file_count')} |",
        f"| symlinks | {summary.get('symlink_count')} |",
        f"| zip entries | {summary.get('zip_entry_count')} |",
        "",
        "| Criterion | Status | Blocker |",
        "| --- | --- | --- |",
    ]
    for item in package.get("criteria", []):
        item_data = dict_or_empty(item)
        lines.append(
            f"| {item_data.get('id')} | {item_data.get('status')} | "
            f"{item_data.get('blocker') or ''} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=Path("QuantumQuake.app"))
    parser.add_argument("--pak", type=Path, default=Path("assets/id1/pak0.pak"))
    parser.add_argument("--playability-gate", type=Path, required=True)
    parser.add_argument("--effects-gate", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--name", default=ROOT_NAME)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    parser.add_argument("--archive-checksum", type=Path)
    parser.add_argument("--no-replace", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        package = build_package(
            app=args.app,
            pak=args.pak,
            playability_gate_path=args.playability_gate,
            effects_gate_path=args.effects_gate,
            outdir=args.outdir,
            name=args.name,
            replace=not args.no_replace,
        )
        manifest_path = args.out or (
            args.outdir / "qge_shareware_user_package.json")
        markdown_path = args.markdown or manifest_path.with_suffix(".md")
        icc_path = args.icc_json or manifest_path.with_name(
            "qge_shareware_user_package_icc_evidence.json")
        checksum_path = args.archive_checksum or manifest_path.with_name(
            "qge_shareware_user_package_archive_checksum.json")
        write_json(manifest_path, package)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown_report(package), encoding="utf-8")
        write_json(checksum_path, archive_checksum_record(package))
        write_json(
            icc_path,
            build_icc_evidence(
                package,
                manifest_path=manifest_path,
                archive_checksum_path=checksum_path,
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"qge_shareware_user_package: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_SHAREWARE_USER_PACKAGE {manifest_path}")
    print(f"QGE_SHAREWARE_USER_PACKAGE_MARKDOWN {markdown_path}")
    print(f"QGE_SHAREWARE_USER_PACKAGE_ARCHIVE {package['archive']['path']}")
    print(f"QGE_SHAREWARE_USER_PACKAGE_ARCHIVE_CHECKSUM {checksum_path}")
    print(f"QGE_SHAREWARE_USER_PACKAGE_ICC {icc_path}")
    if args.fail_on_blocked and package.get("status") != READY_STATUS:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
