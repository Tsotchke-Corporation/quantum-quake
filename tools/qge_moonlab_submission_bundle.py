#!/usr/bin/env python3
"""Build a Moonlab control-plane submission-readiness bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence


MOONLAB_CIRCUIT_HEADER = "# moonlab-circuit v1"
ABSTRACT_QGE_QAE_HEADER = "QGE QAE abstract circuit v0"


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


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def file_info(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "size_bytes": 0, "sha256": None}
    return {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": sha256_file(path),
    }


def read_text_prefix(path: Path, limit: int = 65536) -> str:
    with path.open("rb") as f:
        raw = f.read(limit)
    return raw.decode("utf-8", errors="replace")


def parse_num_qubits(text: str) -> int | None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 2 and parts[0] == "NUM_QUBITS":
            try:
                value = int(parts[1])
            except ValueError:
                return None
            return value if value > 0 else None
    return None


def classify_qae_circuit(path: Path | None) -> dict[str, Any]:
    info = file_info(path)
    check: dict[str, Any] = {
        "artifact": info,
        "format": "missing",
        "status": "blocked_missing_qae_circuit",
        "moonlab_control_plane_executable": False,
        "transpilation_required": True,
        "logical_qubits_declared": None,
        "blockers": ["qae_circuit artifact is missing"],
    }
    if path is None or not path.is_file():
        return check

    text = read_text_prefix(path)
    stripped = text.lstrip()
    first_line = next((line.strip() for line in text.splitlines()
                       if line.strip()), "")
    check["first_line"] = first_line
    if stripped.startswith(MOONLAB_CIRCUIT_HEADER):
        logical_qubits = parse_num_qubits(text)
        check.update({
            "format": "moonlab_control_plane_circuit_v1",
            "logical_qubits_declared": logical_qubits,
            "transpilation_required": False,
        })
        if logical_qubits is None:
            check.update({
                "status": "blocked_invalid_moonlab_circuit",
                "moonlab_control_plane_executable": False,
                "transpilation_required": True,
                "blockers": [
                    "moonlab-circuit v1 payload is missing NUM_QUBITS",
                ],
            })
        else:
            check.update({
                "status": "ready_for_control_plane_submission",
                "moonlab_control_plane_executable": True,
                "blockers": [],
            })
        return check

    if ABSTRACT_QGE_QAE_HEADER in stripped[:1024]:
        check.update({
            "format": "qge_abstract_qae_circuit_v0",
            "status": "blocked_transpilation_required",
            "moonlab_control_plane_executable": False,
            "transpilation_required": True,
            "blockers": [
                "qge_abstract_qae_circuit_v0 must be transpiled to "
                "moonlab-circuit v1 before control-plane submission",
            ],
        })
        return check

    check.update({
        "format": "unknown_text_circuit",
        "status": "blocked_unknown_circuit_format",
        "moonlab_control_plane_executable": False,
        "transpilation_required": True,
        "blockers": [
            "qae_circuit artifact is not a moonlab-circuit v1 payload",
        ],
    })
    return check


def classify_moonlab_qae_payload(path: Path | None) -> dict[str, Any]:
    info = file_info(path)
    check: dict[str, Any] = {
        "artifact": info,
        "schema": None,
        "status": "missing",
        "semantic_scope": None,
        "control_plane_payload_directly_executable": False,
        "full_qae_oracle_transpiled": False,
        "circuit_count": 0,
        "total_shots": 0,
        "blockers": ["moonlab_qae_payload artifact is missing"],
    }
    if path is None or not path.is_file():
        return check

    try:
        payload = load_json(path)
    except (OSError, ValueError) as exc:
        check.update({
            "status": "blocked_invalid_payload",
            "blockers": [f"moonlab_qae_payload could not be read: {exc}"],
        })
        return check

    resource = dict_or_empty(payload.get("payload_resource_estimate"))
    claim_posture = dict_or_empty(payload.get("claim_posture"))
    circuits = [
        item for item in list_or_empty(payload.get("observation_circuits"))
        if isinstance(item, dict)
    ]
    blockers = []
    if payload.get("schema") != "qge.moonlab_qae_payload.v0":
        blockers.append("moonlab_qae_payload schema is not qge.moonlab_qae_payload.v0")
    if not circuits:
        blockers.append("moonlab_qae_payload contains no observation circuits")
    circuit_checks = []
    for item in circuits:
        raw_path = item.get("moonlab_circuit_file")
        circuit_path = Path(raw_path) if isinstance(raw_path, str) and raw_path else None
        circuit_check = classify_qae_circuit(circuit_path)
        circuit_checks.append({
            "observation_index": item.get("observation_index"),
            "moonlab_circuit_file": str(circuit_path)
            if circuit_path is not None else None,
            "status": circuit_check.get("status"),
            "format": circuit_check.get("format"),
            "blockers": circuit_check.get("blockers"),
        })
        if circuit_check.get("status") != "ready_for_control_plane_submission":
            blockers.append(
                "observation circuit is not moonlab-circuit v1: "
                f"{raw_path}"
            )
    executable = not blockers
    check.update({
        "schema": payload.get("schema"),
        "status": payload.get("status"),
        "semantic_scope": payload.get("semantic_scope"),
        "control_plane_payload_directly_executable": executable,
        "full_qae_oracle_transpiled": bool(
            claim_posture.get("full_qae_oracle_transpiled")),
        "circuit_count": resource.get("circuit_count"),
        "total_shots": resource.get("total_shots"),
        "circuit_checks": circuit_checks,
        "blockers": blockers,
    })
    return check


def artifact_checks(job: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    required = dict_or_empty(job.get("required_artifacts"))
    evidence_by_name = {
        item.get("name"): item
        for item in list_or_empty(job.get("artifact_evidence"))
        if isinstance(item, dict)
    }
    checks = []
    missing = []
    for name, raw_path in sorted(required.items()):
        path = Path(raw_path) if isinstance(raw_path, str) and raw_path else None
        info = file_info(path)
        prior = dict_or_empty(evidence_by_name.get(name))
        check = {
            "name": name,
            **info,
            "packet_reported_exists": prior.get("exists"),
            "packet_reported_sha256": prior.get("sha256"),
        }
        checks.append(check)
        if not check["exists"]:
            missing.append(name)
    return checks, missing


def control_plane_request_contract(job: dict[str, Any]) -> dict[str, Any]:
    resource = dict_or_empty(job.get("resource"))
    shots = resource.get("shots")
    return {
        "payload_header": MOONLAB_CIRCUIT_HEADER,
        "required_declaration": "NUM_QUBITS <positive integer>",
        "preferred_verb": "SHOTS" if isinstance(shots, int) and shots > 0
        else "CIRCUIT",
        "shots": shots if isinstance(shots, int) and shots > 0 else None,
        "raw_tcp_protocol": {
            "circuit": "CIRCUIT <body_len>\\n<body bytes>",
            "shots": "SHOTS <shots> <body_len>\\n<body bytes>",
        },
        "websocket_gateway_fields": {
            "verb": "CIRCUIT or SHOTS",
            "circuit": "moonlab-circuit v1 text",
            "shots": "positive int for SHOTS",
        },
        "required_return_metadata": [
            "backend_id",
            "backend_kind",
            "shot_schedule",
            "readout_metadata",
            "hardware observations",
        ],
    }


def build_candidate_bundle(job: dict[str, Any]) -> dict[str, Any]:
    required = dict_or_empty(job.get("required_artifacts"))
    qae_path = (
        Path(required["qae_circuit"])
        if isinstance(required.get("qae_circuit"), str) and
        required.get("qae_circuit")
        else None
    )
    payload_path = (
        Path(required["moonlab_qae_payload"])
        if isinstance(required.get("moonlab_qae_payload"), str) and
        required.get("moonlab_qae_payload")
        else None
    )
    artifacts, missing = artifact_checks(job)
    qae_check = classify_qae_circuit(qae_path)
    payload_check = classify_moonlab_qae_payload(payload_path)
    blockers = list(missing)
    blockers.extend(qae_check.get("blockers", []))
    payload_blockers = list_or_empty(payload_check.get("blockers"))
    if payload_path is not None:
        blockers.extend(payload_blockers)
    direct = bool(qae_check.get("moonlab_control_plane_executable")) and not missing
    payload_direct = bool(
        payload_check.get("control_plane_payload_directly_executable")) and (
            "moonlab_qae_payload" not in missing)
    if missing:
        status = "blocked_missing_required_artifact"
    elif payload_direct and qae_check.get("status") == (
        "blocked_transpilation_required"
    ):
        status = "calibration_payload_ready_oracle_transpilation_required"
    else:
        status = str(qae_check.get("status"))
    return {
        "job_id": job.get("job_id"),
        "domain": job.get("domain"),
        "kind": job.get("kind"),
        "packet_submission_status": job.get("submission_status"),
        "hardware_submission_status": job.get("hardware_submission_status"),
        "control_plane_submission_status": status,
        "hardware_submission_directly_executable": direct,
        "candidate_digest": job.get("candidate_digest"),
        "resource": dict_or_empty(job.get("resource")),
        "required_artifacts": required,
        "artifact_checks": artifacts,
        "missing_required_artifacts": missing,
        "qae_circuit_check": qae_check,
        "moonlab_qae_payload_check": payload_check,
        "moonlab_control_plane_request": control_plane_request_contract(job),
        "blockers": blockers,
        "control_plane_payload_directly_executable": payload_direct,
        "full_qae_oracle_transpiled": bool(
            payload_check.get("full_qae_oracle_transpiled")),
        "claim_posture": {
            "hardware_result_claimed": False,
            "hardware_quantum_advantage_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "dense_70000_qubit_state_claimed": False,
        },
    }


def overall_status(
    candidates: list[dict[str, Any]],
) -> str:
    if not candidates:
        return "no_hardware_candidates"
    statuses = [
        candidate.get("control_plane_submission_status")
        for candidate in candidates
    ]
    if any(status == "blocked_missing_required_artifact"
           for status in statuses):
        return "blocked_missing_required_artifact"
    if any(status == "blocked_transpilation_required" for status in statuses):
        return "blocked_transpilation_required"
    if any(status == "calibration_payload_ready_oracle_transpilation_required"
           for status in statuses):
        return "calibration_payload_ready_oracle_transpilation_required"
    if all(status == "ready_for_control_plane_submission"
           for status in statuses):
        return "ready_for_control_plane_submission"
    return "blocked_control_plane_submission"


def build_submission_bundle(
    submission_packet: dict[str, Any],
    *,
    packet_path: Path | None = None,
) -> dict[str, Any]:
    raw_candidates = [
        item for item in list_or_empty(submission_packet.get("candidate_jobs"))
        if isinstance(item, dict)
    ]
    candidates = [build_candidate_bundle(job) for job in raw_candidates]
    ready = sum(
        1 for candidate in candidates
        if candidate.get("control_plane_submission_status") ==
        "ready_for_control_plane_submission"
    )
    transpilation_required = sum(
        1 for candidate in candidates
        if candidate.get("qae_circuit_check", {}).get(
            "transpilation_required")
    )
    missing = sum(
        1 for candidate in candidates
        if candidate.get("control_plane_submission_status") ==
        "blocked_missing_required_artifact"
    )
    calibration_ready = sum(
        1 for candidate in candidates
        if candidate.get("control_plane_submission_status") ==
        "calibration_payload_ready_oracle_transpilation_required"
    )
    payload_direct = bool(candidates) and all(
        bool(candidate.get("control_plane_payload_directly_executable"))
        for candidate in candidates
    )
    direct = bool(candidates) and all(
        bool(candidate.get("hardware_submission_directly_executable"))
        for candidate in candidates
    )
    return {
        "schema": "qge.moonlab_submission_bundle.v0",
        "source_schema": submission_packet.get("schema"),
        "submission_packet": str(packet_path) if packet_path else None,
        "status": overall_status(candidates),
        "hardware_candidate_job_count": len(candidates),
        "ready_for_control_plane_submission_count": ready,
        "calibration_payload_ready_count": calibration_ready,
        "transpilation_required_count": transpilation_required,
        "missing_artifact_candidate_count": missing,
        "hardware_submission_directly_executable": direct,
        "control_plane_payload_directly_executable": payload_direct,
        "moonlab_control_plane_requirements": {
            "payload_header": MOONLAB_CIRCUIT_HEADER,
            "required_payload_fields": ["NUM_QUBITS"],
            "raw_tcp_verbs": ["CIRCUIT", "SHOTS"],
            "websocket_gateway_verbs": ["CIRCUIT", "SHOTS"],
            "hardware_record_schema": "qge.moonlab_hardware_record.v0",
        },
        "candidate_jobs": candidates,
        "claim_posture": {
            "hardware_result_claimed": False,
            "hardware_quantum_advantage_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "dense_70000_qubit_state_claimed": False,
        },
        "limits": [
            "A Moonlab hardware candidate is not directly executable until its circuit artifact is moonlab-circuit v1.",
            "Abstract QGE QAE circuit text requires a transpilation step before control-plane submission.",
            "Readout-equivalent Moonlab payloads can validate shot plumbing without proving the full QAE oracle is transpiled.",
            "This bundle records submission readiness, not a hardware result.",
        ],
    }


def markdown_report(bundle: dict[str, Any]) -> str:
    lines = [
        "# QGE Moonlab Submission Bundle",
        "",
        f"Status: `{bundle['status']}`",
        "",
        "| Jobs | Ready | Calibration Ready | Transpilation Required | Missing Artifacts | Directly Executable |",
        "| ---: | ---: | ---: | ---: | ---: | --- |",
        (
            f"| {bundle['hardware_candidate_job_count']} | "
            f"{bundle['ready_for_control_plane_submission_count']} | "
            f"{bundle['calibration_payload_ready_count']} | "
            f"{bundle['transpilation_required_count']} | "
            f"{bundle['missing_artifact_candidate_count']} | "
            f"{bundle['control_plane_payload_directly_executable']} |"
        ),
        "",
        "| Job | Control-Plane Status | Circuit Format | Payload Scope | Qubits | Blockers |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for job in bundle["candidate_jobs"]:
        qae_check = dict_or_empty(job.get("qae_circuit_check"))
        payload_check = dict_or_empty(job.get("moonlab_qae_payload_check"))
        blockers = job.get("blockers", [])
        if isinstance(blockers, list):
            blocker_text = "; ".join(str(item) for item in blockers) or "none"
        else:
            blocker_text = "none"
        lines.append(
            f"| {job.get('job_id')} | "
            f"{job.get('control_plane_submission_status')} | "
            f"{qae_check.get('format')} | "
            f"{payload_check.get('semantic_scope')} | "
            f"{qae_check.get('logical_qubits_declared')} | "
            f"{blocker_text} |"
        )
    lines.extend([
        "",
        "Claims: no hardware result, hardware quantum advantage, whole-game hardware execution, or dense 70,000-qubit state is claimed.",
        "",
    ])
    return "\n".join(lines)


def build_icc_evidence(
    bundle: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_moonlab_submission_bundle",
        "completion_reason": "qge_moonlab_submission_bundle_recorded",
        "submission_bundle_file": str(out_path) if out_path else None,
        "submission_bundle_schema": bundle.get("schema"),
        "submission_bundle_status": bundle.get("status"),
        "hardware_candidate_job_count": bundle.get(
            "hardware_candidate_job_count"),
        "ready_for_control_plane_submission_count": bundle.get(
            "ready_for_control_plane_submission_count"),
        "calibration_payload_ready_count": bundle.get(
            "calibration_payload_ready_count"),
        "transpilation_required_count": bundle.get(
            "transpilation_required_count"),
        "missing_artifact_candidate_count": bundle.get(
            "missing_artifact_candidate_count"),
        "hardware_submission_directly_executable": bundle.get(
            "hardware_submission_directly_executable"),
        "control_plane_payload_directly_executable": bundle.get(
            "control_plane_payload_directly_executable"),
        "hardware_quantum_advantage_claimed": False,
        "whole_game_hardware_execution_claimed": False,
        "dense_70000_qubit_state_claimed": False,
        "status": "success",
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission_packet", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        packet = load_json(args.submission_packet)
        bundle = build_submission_bundle(
            packet,
            packet_path=args.submission_packet,
        )
        write_json(args.out, bundle)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(bundle),
                                     encoding="utf-8")
        if args.icc_json:
            write_json(args.icc_json, build_icc_evidence(
                bundle,
                out_path=args.out,
            ))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_moonlab_submission_bundle: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_MOONLAB_SUBMISSION_BUNDLE {args.out}")
    if args.markdown:
        print(f"QGE_MOONLAB_SUBMISSION_BUNDLE_MARKDOWN {args.markdown}")
    if args.icc_json:
        print(f"QGE_MOONLAB_SUBMISSION_BUNDLE_ICC_EVIDENCE {args.icc_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
