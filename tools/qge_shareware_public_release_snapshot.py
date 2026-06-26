#!/usr/bin/env python3
"""Build a fail-closed public release snapshot for Quantum Quake shareware."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_map_sets  # noqa: E402
import qge_shareware_user_package  # noqa: E402


READY_STATUS = "ready_for_shareware_public_release"
BLOCKED = "blocked"
PASS = "pass"
SHAREWARE_MAP_SET = qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET
PLAYABILITY_READY = "ready_for_shareware_user_playable_release"
PACKAGE_READY = "ready_for_shareware_user_package"
EFFECTS_READY = "ready_for_shareware_complete_effects_claim"
DEFAULT_PUBLICATION_RELEASE_TRACE = Path(
    "diagnostics/publication_pack/20260624-shareware-v8/release/"
    "qge_shareware_current_release_icc_trace.jsonl")
DEFAULT_HARDWARE_SUBMISSION_SCOPE_ICC = Path(
    "diagnostics/publication_pack/20260624-shareware-v8/resource/"
    "qge_moonlab_hardware_submission_scope_icc_evidence.json")
DEFAULT_HARDWARE_ADVANTAGE_GATE_ICC = Path(
    "diagnostics/hardware_advantage/20260626-shareware-v8-current/"
    "qge_hardware_advantage_gate_icc.json")
DEFAULT_HARDWARE_RESULT_AUDIT_ICC = Path(
    "diagnostics/hardware_advantage/20260626-shareware-v8-current/"
    "qge_moonlab_hardware_result_audit.strict_icc.json")
DEFAULT_HARDWARE_RETURN_HANDOFF_ICC = Path(
    "diagnostics/hardware_advantage/20260626-shareware-v8-current/"
    "qge_moonlab_hardware_return_handoff_icc.json")
DEFAULT_HARDWARE_CAMPAIGN_ICC = Path(
    "docs/qge_hardware_advantage_campaign_icc_evidence.json")
README_REQUIRED_PHRASES = [
    "What makes this Quantum Quake:",
    "QGE runtime systems are enabled by default",
    "simulator branch and",
    "measurement events that write back into gameplay state",
    "release_evidence directory",
    "does not claim hardware quantum advantage",
    "whole-game hardware execution",
    "registered/full-game data",
]


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


def load_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def resolve_path(repo_root: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        "blocker": "" if passed else blocker,
    }
    item.update(fields)
    return item


def failed_criteria(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in criteria
        if dict_or_empty(item).get("status") != PASS
    ]


def package_ready(package: dict[str, Any]) -> bool:
    return (
        package.get("schema") == "qge.shareware_user_package.v0"
        and package.get("status") == PACKAGE_READY
        and package.get("shareware_user_package_ready") is True
        and int_value(package.get("blocker_count")) == 0
    )


def playability_ready(gate: dict[str, Any]) -> bool:
    summary = dict_or_empty(gate.get("summary"))
    return (
        gate.get("schema") == "qge.shareware_playability_gate.v0"
        and gate.get("status") == PLAYABILITY_READY
        and gate.get("shareware_user_playable_release_ready") is True
        and int_value(gate.get("blocker_count")) == 0
        and int_value(summary.get("runtime_covered_map_count")) == 9
        and int_value(summary.get("runtime_target_map_count")) == 9
        and int_value(summary.get("pak_entry_count")) >= 339
        and summary.get("effects_gate_status") == EFFECTS_READY
    )


def effects_ready(gate: dict[str, Any]) -> bool:
    summary = dict_or_empty(gate.get("summary"))
    matrix = dict_or_empty(summary.get("matrix_summary"))
    return (
        gate.get("schema") == "qge.shareware_complete_effects_gate.v0"
        and gate.get("status") == EFFECTS_READY
        and summary.get("ready_for_complete_effects_claim") is True
        and int_value(matrix.get("missing_enemy_class_count")) == 0
        and int_value(matrix.get("missing_material_class_count")) == 0
        and int_value(matrix.get("missing_weapon_class_count")) == 0
        and int_value(matrix.get("missing_noesis_evidence_map_count")) == 0
        and int_value(matrix.get("runtime_footage_capture_count")) > 0
    )


def archive_verified(
    repo_root: Path,
    package: dict[str, Any],
    checksum: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    archive = dict_or_empty(package.get("archive"))
    archive_path = resolve_path(repo_root, archive.get("path"))
    checksum_path = resolve_path(repo_root, checksum.get("archive_file"))
    expected_sha = archive.get("sha256")
    checksum_sha = checksum.get("archive_sha256")
    expected_size = int_value(archive.get("size_bytes"))
    checksum_size = int_value(checksum.get("archive_size_bytes"))
    actual_sha = None
    actual_size = 0
    exists = bool(archive_path and archive_path.is_file())
    if archive_path and archive_path.is_file():
        actual_sha = sha256_file(archive_path)
        actual_size = archive_path.stat().st_size
    same_path = archive_path == checksum_path and archive_path is not None
    passed = (
        exists and
        same_path and
        isinstance(expected_sha, str) and
        expected_sha == checksum_sha == actual_sha and
        expected_size > 0 and
        expected_size == checksum_size == actual_size and
        checksum.get("package_status") == PACKAGE_READY and
        checksum.get("shareware_user_package_ready") is True
    )
    return passed, {
        "archive_path": str(archive_path) if archive_path else None,
        "checksum_archive_path": str(checksum_path) if checksum_path else None,
        "archive_exists": exists,
        "manifest_sha256": expected_sha,
        "checksum_sha256": checksum_sha,
        "actual_sha256": actual_sha,
        "manifest_size_bytes": expected_size,
        "checksum_size_bytes": checksum_size,
        "actual_size_bytes": actual_size,
    }


def required_payload_present(repo_root: Path, package: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    summary = dict_or_empty(package.get("summary"))
    paths = {
        "app_binary": resolve_path(repo_root, summary.get("app_binary")),
        "shareware_pak": resolve_path(repo_root, summary.get("shareware_pak")),
        "playability_gate_evidence": resolve_path(
            repo_root, summary.get("playability_gate_evidence")),
        "complete_effects_gate_evidence": resolve_path(
            repo_root, summary.get("complete_effects_gate_evidence")),
    }
    exists = {name: bool(path and path.is_file()) for name, path in paths.items()}
    passed = all(exists.values())
    return passed, {
        "paths": {
            name: str(path) if path else None
            for name, path in paths.items()
        },
        "exists": exists,
    }


def package_readme_explains_quantum(
    repo_root: Path,
    package: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    archive = dict_or_empty(package.get("archive"))
    package_dir = resolve_path(repo_root, package.get("package_dir"))
    archive_path = resolve_path(repo_root, archive.get("path"))
    readme_path = package_dir / "README.txt" if package_dir else None
    archive_readme_name = (
        f"{package_dir.name}/README.txt"
        if package_dir else "QuantumQuake-shareware-macos/README.txt"
    )

    dir_text = ""
    if readme_path and readme_path.is_file():
        dir_text = readme_path.read_text(encoding="utf-8", errors="replace")

    archive_text = ""
    archive_error = ""
    if archive_path and archive_path.is_file():
        try:
            with zipfile.ZipFile(archive_path) as zip_file:
                with zip_file.open(archive_readme_name) as readme:
                    archive_text = readme.read().decode(
                        "utf-8", errors="replace")
        except (KeyError, OSError, zipfile.BadZipFile) as exc:
            archive_error = str(exc)

    missing_dir = [
        phrase for phrase in README_REQUIRED_PHRASES
        if phrase not in dir_text
    ]
    missing_archive = [
        phrase for phrase in README_REQUIRED_PHRASES
        if phrase not in archive_text
    ]
    passed = (
        bool(dir_text)
        and bool(archive_text)
        and not missing_dir
        and not missing_archive
    )
    return passed, {
        "readme_path": str(readme_path) if readme_path else None,
        "readme_exists": bool(readme_path and readme_path.is_file()),
        "archive_readme": archive_readme_name,
        "archive_readme_exists": bool(archive_text),
        "archive_readme_error": archive_error,
        "required_phrase_count": len(README_REQUIRED_PHRASES),
        "missing_readme_phrases": missing_dir,
        "missing_archive_readme_phrases": missing_archive,
    }


def hardware_claims_blocked(
    hardware_gate: dict[str, Any],
    handoff: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    gate_summary = dict_or_empty(hardware_gate.get("summary"))
    handoff_claims = dict_or_empty(handoff.get("claim_posture"))
    hardware_result_count = int_value(
        gate_summary.get("completed_hardware_result_count"))
    hardware_rows = int_value(gate_summary.get("hardware_result_job_count"))
    forbidden_false = (
        hardware_gate.get("hardware_advantage_claim_allowed") is not True
        and hardware_gate.get("whole_game_hardware_execution_claim_allowed") is False
        and hardware_gate.get("dense_70000_qubit_state_claim_allowed") is False
        and handoff_claims.get("hardware_quantum_advantage_claimed") is False
        and handoff_claims.get("whole_game_hardware_execution_claimed") is False
        and handoff_claims.get("dense_70000_qubit_state_claimed") is False
        and handoff_claims.get("bounded_qae_query_scaling_claim_allowed") is False
    )
    waiting_for_record = (
        handoff.get("schema") == "qge.moonlab_hardware_return_handoff.v0"
        and handoff.get("ready") is False
        and handoff.get("ready_for_hardware_advantage_gate") is False
        and handoff.get("ready_for_hardware_ingest") is False
        and bool(list_or_empty(handoff.get("missing_record_fields")))
        and not list_or_empty(handoff.get("overclaim_flags"))
    )
    gate_blocked = (
        hardware_gate.get("schema") == "qge.hardware_advantage_gate.v0"
        and hardware_gate.get("status") == BLOCKED
        and int_value(hardware_gate.get("failed_criterion_count")) > 0
        and hardware_result_count == 0
        and hardware_rows == 0
    )
    return gate_blocked and waiting_for_record and forbidden_false, {
        "hardware_gate_status": hardware_gate.get("status"),
        "hardware_advantage_claim_allowed": hardware_gate.get(
            "hardware_advantage_claim_allowed"),
        "whole_game_hardware_execution_claim_allowed": hardware_gate.get(
            "whole_game_hardware_execution_claim_allowed"),
        "dense_70000_qubit_state_claim_allowed": hardware_gate.get(
            "dense_70000_qubit_state_claim_allowed"),
        "completed_hardware_result_count": hardware_result_count,
        "hardware_result_job_count": hardware_rows,
        "handoff_status": handoff.get("status"),
        "handoff_ready": handoff.get("ready"),
        "ready_for_hardware_ingest": handoff.get("ready_for_hardware_ingest"),
        "ready_for_hardware_advantage_gate": handoff.get(
            "ready_for_hardware_advantage_gate"),
        "missing_record_field_count": len(list_or_empty(
            handoff.get("missing_record_fields"))),
        "overclaim_flags": list_or_empty(handoff.get("overclaim_flags")),
        "claim_posture": handoff_claims,
    }


def swarm_summary(swarm: dict[str, Any]) -> dict[str, Any]:
    queue = dict_or_empty(swarm.get("tsotchke_queue"))
    explicit = list_or_empty(queue.get("explicit_backend_audits"))
    advisory_done = [
        item for item in explicit
        if isinstance(item, dict) and item.get("status") == "done"
    ]
    unusable = [
        item for item in explicit
        if isinstance(item, dict) and item.get("result") == "unusable"
    ]
    return {
        "forwarding_status": queue.get("forwarding_status"),
        "repo_probe_issue": dict_or_empty(queue.get("repo_probe_issue")).get(
            "error"),
        "write_allowed": dict_or_empty(queue.get("write_policy")).get(
            "allow_write"),
        "explicit_backend_audit_count": len(explicit),
        "explicit_backend_done_count": len(advisory_done),
        "explicit_backend_unusable_count": len(unusable),
        "pending_backends": [
            item.get("backend")
            for item in explicit
            if isinstance(item, dict) and item.get("status") == "pending"
        ],
    }


def build_snapshot(
    *,
    repo_root: Path,
    package: dict[str, Any],
    checksum: dict[str, Any],
    playability_gate: dict[str, Any],
    effects_gate: dict[str, Any],
    hardware_gate: dict[str, Any],
    handoff: dict[str, Any],
    swarm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    archive_ok, archive_evidence = archive_verified(repo_root, package, checksum)
    payload_ok, payload_evidence = required_payload_present(repo_root, package)
    readme_ok, readme_evidence = package_readme_explains_quantum(
        repo_root, package)
    hardware_ok, hardware_evidence = hardware_claims_blocked(
        hardware_gate, handoff)
    criteria = [
        criterion(
            "shareware_user_package_ready",
            "Player package manifest is ready and unblocked",
            package_ready(package),
            "player package manifest is blocked or malformed",
            package_status=package.get("status"),
            blocker_count=package.get("blocker_count"),
        ),
        criterion(
            "shareware_archive_checksum_verified",
            "Player archive exists and matches manifest/checksum SHA-256",
            archive_ok,
            "archive is missing or checksum/size evidence does not match",
            **archive_evidence,
        ),
        criterion(
            "shareware_required_payload_present",
            "Package contains QuantumQuake.app, pak0.pak, and final gate evidence",
            payload_ok,
            "package payload or release evidence files are missing",
            **payload_evidence,
        ),
        criterion(
            "shareware_readme_quantum_distinction_present",
            "Package README explains QGE runtime distinctions and claim boundary",
            readme_ok,
            "package README is missing quantum-specific or no-overclaim wording",
            **readme_evidence,
        ),
        criterion(
            "shareware_playability_gate_ready",
            "Final no-exceptions shareware playability gate is ready",
            playability_ready(playability_gate),
            "shareware playability gate is blocked or incomplete",
            playability_gate_status=playability_gate.get("status"),
            summary=dict_or_empty(playability_gate.get("summary")),
        ),
        criterion(
            "shareware_complete_effects_gate_ready",
            "Complete-effects gate covers shareware enemies, weapons, maps, and slipgates",
            effects_ready(effects_gate),
            "complete-effects gate is blocked or incomplete",
            complete_effects_gate_status=effects_gate.get("status"),
            summary=dict_or_empty(effects_gate.get("summary")),
        ),
        criterion(
            "hardware_advantage_claims_forbidden",
            "Hardware and quantum-advantage claims remain fail-closed",
            hardware_ok,
            "hardware/advantage claim boundary is open or missing returned-record blockers",
            **hardware_evidence,
        ),
    ]
    blockers = failed_criteria(criteria)
    ready = not blockers
    archive = dict_or_empty(package.get("archive"))
    summary = dict_or_empty(package.get("summary"))
    return {
        "schema": "qge.shareware_public_release_snapshot.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": READY_STATUS if ready else BLOCKED,
        "map_set": SHAREWARE_MAP_SET,
        "shareware_public_release_ready": ready,
        "shareware_user_playable_release_ready": ready,
        "hardware_quantum_advantage_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "registered_full_game_release_claim_allowed": False,
        "criteria": criteria,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "summary": {
            "archive": archive.get("path"),
            "archive_sha256": archive.get("sha256"),
            "archive_size_bytes": archive.get("size_bytes"),
            "package_dir": package.get("package_dir"),
            "app_binary": summary.get("app_binary"),
            "shareware_pak": summary.get("shareware_pak"),
            "shareware_pak_sha256": summary.get("shareware_pak_sha256"),
            "readme_quantum_distinction_ready": readme_ok,
            "playability_gate_status": playability_gate.get("status"),
            "complete_effects_gate_status": effects_gate.get("status"),
            "hardware_gate_status": hardware_gate.get("status"),
            "hardware_handoff_status": handoff.get("status"),
            "hardware_missing_record_field_count": len(list_or_empty(
                handoff.get("missing_record_fields"))),
        },
        "source_status": {
            "package": package.get("status"),
            "playability_gate": playability_gate.get("status"),
            "complete_effects_gate": effects_gate.get("status"),
            "hardware_advantage_gate": hardware_gate.get("status"),
            "hardware_return_handoff": handoff.get("status"),
            "tsotchke_swarm": swarm_summary(swarm or {}),
        },
        "allowed_release_wording": (
            "Quantum Quake shareware simulator release for Quake Episode 1, "
            "with packaged QGE evidence and final playability/effects gates."),
        "forbidden_release_wording": [
            "hardware quantum advantage",
            "true quantum hardware acceleration",
            "quantum supremacy",
            "exponential speedup",
            "whole-game hardware execution",
            "registered/full-game release",
            "dense 70,000-qubit state execution",
        ],
    }


def build_icc_evidence(
    snapshot: dict[str, Any],
    *,
    out_path: Path,
) -> dict[str, Any]:
    ready = snapshot.get("shareware_public_release_ready") is True
    summary = dict_or_empty(snapshot.get("summary"))
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_shareware_public_release_snapshot",
        "completion_reason": (
            "qge_shareware_public_release_snapshot_ready"
            if ready else "qge_shareware_public_release_snapshot_blocked"),
        "status": "success",
        "runtime_backend_scope_map_set": SHAREWARE_MAP_SET,
        "release_scope": SHAREWARE_MAP_SET,
        "map_set": SHAREWARE_MAP_SET,
        "qge_shareware_public_release_snapshot.json": str(out_path),
        "shareware_public_release_snapshot_file": str(out_path),
        "shareware_public_release_ready": ready,
        "shareware_user_playable_release_ready": ready,
        "shareware_public_release_archive_file": summary.get("archive"),
        "shareware_public_release_archive_sha256": summary.get(
            "archive_sha256"),
        "shareware_public_release_archive_completion": (
            "present" if ready else "blocked"),
        "shareware_public_release_readme_completion": (
            "present" if ready else "blocked"),
        "shareware_public_release_no_hardware_overclaim": (
            "present" if ready else "blocked"),
        "shareware_public_release_no_hardware_overclaim_completion": (
            "present" if ready else "blocked"),
        "hardware_quantum_advantage_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "registered_full_game_release_claim_allowed": False,
    }


def icc_trace_event_kind(name: str) -> str:
    if name == "runtime_backend":
        return "runtime_backend"
    if name == "completion_reason" or name.endswith("_completion"):
        return "completion_condition"
    if name in {"runtime_backend_scope_map_set", "release_scope", "map_set"}:
        return "runtime_state"
    if (
        name.endswith("_file")
        or name.endswith("_sha256")
        or name.endswith("_archive")
        or "." in name
    ):
        return "artifact"
    return "runtime_state"


def scalar_icc_value(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def publication_release_trace_events(
    evidence_records: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for evidence in evidence_records:
        source_schema = evidence.get("schema")
        source_backend = evidence.get("runtime_backend")
        for name, value in sorted(evidence.items()):
            if name == "schema" or not scalar_icc_value(value):
                continue
            events.append({
                "kind": icc_trace_event_kind(name),
                "name": name,
                "value": value,
                "snippet": (
                    f"{source_backend or source_schema}: {name}={value}"),
                "confidence": 0.99,
            })
            if name.endswith("_file") and isinstance(value, str) and value:
                alias = Path(value).name
                if alias and alias != name and "." in alias:
                    events.append({
                        "kind": "artifact",
                        "name": alias,
                        "value": value,
                        "snippet": (
                            f"{source_backend or source_schema}: "
                            f"{name}={value}"),
                        "confidence": 0.98,
                    })
    return events


def write_publication_release_trace(
    path: Path,
    evidence_records: Sequence[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    events = publication_release_trace_events(evidence_records)
    path.write_text(
        "".join(
            json.dumps(event, sort_keys=True) + "\n"
            for event in events
        ),
        encoding="utf-8",
    )


def load_existing_icc_evidence(paths: Sequence[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        if path.is_file():
            records.append(load_json_object(path))
    return records


def markdown_report(snapshot: dict[str, Any]) -> str:
    summary = dict_or_empty(snapshot.get("summary"))
    lines = [
        "# QGE Shareware Public Release Snapshot",
        "",
        f"Status: `{snapshot.get('status')}`",
        f"Map set: `{snapshot.get('map_set')}`",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| archive | {summary.get('archive')} |",
        f"| archive sha256 | {summary.get('archive_sha256')} |",
        f"| package dir | {summary.get('package_dir')} |",
        f"| README explains QGE release | {summary.get('readme_quantum_distinction_ready')} |",
        f"| playability gate | {summary.get('playability_gate_status')} |",
        f"| complete effects gate | {summary.get('complete_effects_gate_status')} |",
        f"| hardware gate | {summary.get('hardware_gate_status')} |",
        f"| hardware handoff | {summary.get('hardware_handoff_status')} |",
        "",
        "| Claim Boundary | Allowed |",
        "| --- | --- |",
        "| shareware Episode 1 simulator release | true |",
        "| registered/full-game release | false |",
        "| hardware quantum advantage | false |",
        "| whole-game hardware execution | false |",
        "| dense 70,000-qubit state execution | false |",
        "",
        "| Criterion | Status | Blocker |",
        "| --- | --- | --- |",
    ]
    for item in list_or_empty(snapshot.get("criteria")):
        item_data = dict_or_empty(item)
        lines.append(
            f"| {item_data.get('id')} | {item_data.get('status')} | "
            f"{item_data.get('blocker') or ''} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--package",
        type=Path,
        default=Path(
            "diagnostics/user_release/20260626-shareware-playable/"
            "qge_shareware_user_package.json"),
    )
    parser.add_argument(
        "--archive-checksum",
        type=Path,
        default=Path(
            "diagnostics/user_release/20260626-shareware-playable/"
            "qge_shareware_user_package_archive_checksum.json"),
    )
    parser.add_argument(
        "--playability-gate",
        type=Path,
        default=Path(
            "diagnostics/publication_pack/20260624-shareware-v8/release/"
            "qge_shareware_playability_gate.json"),
    )
    parser.add_argument(
        "--effects-gate",
        type=Path,
        default=Path(
            "diagnostics/shareware_effects/20260625-050156/"
            "qge_shareware_complete_effects_gate.json"),
    )
    parser.add_argument(
        "--hardware-advantage-gate",
        type=Path,
        default=Path(
            "diagnostics/hardware_advantage/20260626-shareware-v8-current/"
            "qge_hardware_advantage_gate.json"),
    )
    parser.add_argument(
        "--hardware-return-handoff",
        type=Path,
        default=Path(
            "diagnostics/hardware_advantage/20260626-shareware-v8-current/"
            "qge_moonlab_hardware_return_handoff.json"),
    )
    parser.add_argument(
        "--swarm-execution",
        type=Path,
        default=Path("docs/qge_tsotchke_swarm_execution.json"),
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    parser.add_argument(
        "--publication-release-trace",
        type=Path,
        default=DEFAULT_PUBLICATION_RELEASE_TRACE,
        help=(
            "JSONL ICC trace mirror written into the default publication-pack "
            "release directory so plain ICC next-action/readiness commands "
            "see the current package, public snapshot, and hardware-boundary "
            "evidence."),
    )
    parser.add_argument(
        "--hardware-submission-scope-icc",
        type=Path,
        default=DEFAULT_HARDWARE_SUBMISSION_SCOPE_ICC,
    )
    parser.add_argument(
        "--hardware-advantage-gate-icc",
        type=Path,
        default=DEFAULT_HARDWARE_ADVANTAGE_GATE_ICC,
    )
    parser.add_argument(
        "--hardware-result-audit-icc",
        type=Path,
        default=DEFAULT_HARDWARE_RESULT_AUDIT_ICC,
    )
    parser.add_argument(
        "--hardware-return-handoff-icc",
        type=Path,
        default=DEFAULT_HARDWARE_RETURN_HANDOFF_ICC,
    )
    parser.add_argument(
        "--hardware-campaign-icc",
        type=Path,
        default=DEFAULT_HARDWARE_CAMPAIGN_ICC,
    )
    parser.add_argument("--fail-on-blocked", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    try:
        swarm = {}
        if args.swarm_execution.is_file():
            swarm = load_json_object(args.swarm_execution)
        package = load_json_object(args.package)
        snapshot = build_snapshot(
            repo_root=repo_root,
            package=package,
            checksum=load_json_object(args.archive_checksum),
            playability_gate=load_json_object(args.playability_gate),
            effects_gate=load_json_object(args.effects_gate),
            hardware_gate=load_json_object(args.hardware_advantage_gate),
            handoff=load_json_object(args.hardware_return_handoff),
            swarm=swarm,
        )
        write_json(args.out, snapshot)
        markdown_path = args.markdown or args.out.with_suffix(".md")
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown_report(snapshot), encoding="utf-8")
        icc_path = args.icc_json or args.out.with_name(
            f"{args.out.stem}_icc_evidence.json")
        snapshot_icc = build_icc_evidence(snapshot, out_path=args.out)
        package_icc = qge_shareware_user_package.build_icc_evidence(
            package,
            manifest_path=args.package,
            archive_checksum_path=args.archive_checksum,
        )
        hardware_icc_records = load_existing_icc_evidence([
            args.hardware_submission_scope_icc,
            args.hardware_advantage_gate_icc,
            args.hardware_result_audit_icc,
            args.hardware_return_handoff_icc,
            args.hardware_campaign_icc,
        ])
        write_json(icc_path, snapshot_icc)
        write_publication_release_trace(
            args.publication_release_trace,
            [package_icc, snapshot_icc, *hardware_icc_records],
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"qge_shareware_public_release_snapshot: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_SHAREWARE_PUBLIC_RELEASE_SNAPSHOT {args.out}")
    print(f"QGE_SHAREWARE_PUBLIC_RELEASE_SNAPSHOT_MARKDOWN {markdown_path}")
    print(f"QGE_SHAREWARE_PUBLIC_RELEASE_SNAPSHOT_ICC {icc_path}")
    print(
        "QGE_SHAREWARE_PUBLIC_RELEASE_TRACE "
        f"{args.publication_release_trace}")
    if args.fail_on_blocked and snapshot.get("status") != READY_STATUS:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
