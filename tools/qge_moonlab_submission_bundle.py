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
    artifacts, missing = artifact_checks(job)
    qae_check = classify_qae_circuit(qae_path)
    blockers = list(missing)
    blockers.extend(qae_check.get("blockers", []))
    direct = bool(qae_check.get("moonlab_control_plane_executable")) and not missing
    if missing:
        status = "blocked_missing_required_artifact"
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
        "moonlab_control_plane_request": control_plane_request_contract(job),
        "blockers": blockers,
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
        "transpilation_required_count": transpilation_required,
        "missing_artifact_candidate_count": missing,
        "hardware_submission_directly_executable": direct,
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
            "This bundle records submission readiness, not a hardware result.",
        ],
    }


def markdown_report(bundle: dict[str, Any]) -> str:
    lines = [
        "# QGE Moonlab Submission Bundle",
        "",
        f"Status: `{bundle['status']}`",
        "",
        "| Jobs | Ready | Transpilation Required | Missing Artifacts | Directly Executable |",
        "| ---: | ---: | ---: | ---: | --- |",
        (
            f"| {bundle['hardware_candidate_job_count']} | "
            f"{bundle['ready_for_control_plane_submission_count']} | "
            f"{bundle['transpilation_required_count']} | "
            f"{bundle['missing_artifact_candidate_count']} | "
            f"{bundle['hardware_submission_directly_executable']} |"
        ),
        "",
        "| Job | Control-Plane Status | Circuit Format | Qubits | Blockers |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for job in bundle["candidate_jobs"]:
        qae_check = dict_or_empty(job.get("qae_circuit_check"))
        blockers = job.get("blockers", [])
        if isinstance(blockers, list):
            blocker_text = "; ".join(str(item) for item in blockers) or "none"
        else:
            blocker_text = "none"
        lines.append(
            f"| {job.get('job_id')} | "
            f"{job.get('control_plane_submission_status')} | "
            f"{qae_check.get('format')} | "
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
        "transpilation_required_count": bundle.get(
            "transpilation_required_count"),
        "missing_artifact_candidate_count": bundle.get(
            "missing_artifact_candidate_count"),
        "hardware_submission_directly_executable": bundle.get(
            "hardware_submission_directly_executable"),
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
