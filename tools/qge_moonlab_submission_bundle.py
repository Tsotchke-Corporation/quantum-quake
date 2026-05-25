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
MOONLAB_CONTROL_MAX_BODY_BYTES = 1 << 22
ABSTRACT_QGE_QAE_HEADER = "QGE QAE abstract circuit v0"
QF_KERNEL_READY_STATUS = "qf_oracle_kernel_ready_qae_transpilation_required"
QAE_OBSERVATION_ZERO_READY_STATUS = (
    "qae_observation_zero_ready_grover_schedule_required"
)


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


def path_info(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "size_bytes": 0, "sha256": None}
    if path.is_dir():
        files = [item for item in path.iterdir() if item.is_file()]
        return {
            "path": str(path),
            "exists": True,
            "is_dir": True,
            "file_count": len(files),
            "size_bytes": sum(item.stat().st_size for item in files),
            "sha256": None,
        }
    return file_info(path)


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
        "body_limit_bytes": MOONLAB_CONTROL_MAX_BODY_BYTES,
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
        elif info.get("size_bytes", 0) > MOONLAB_CONTROL_MAX_BODY_BYTES:
            check.update({
                "status": "blocked_control_plane_body_limit",
                "moonlab_control_plane_executable": False,
                "transpilation_required": True,
                "blockers": [
                    "moonlab-circuit v1 payload exceeds the Moonlab "
                    "control-plane body limit",
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


def classify_moonlab_qae_oracle_kernel(path: Path | None) -> dict[str, Any]:
    info = file_info(path)
    check: dict[str, Any] = {
        "artifact": info,
        "schema": None,
        "status": "missing",
        "semantic_scope": None,
        "oracle_kernel_directly_executable": False,
        "qf_oracle_kernel_transpiled": False,
        "full_qae_oracle_transpiled": False,
        "logical_qubits": None,
        "gate_count": None,
        "body_bytes": None,
        "blockers": ["moonlab_qae_oracle_kernel artifact is missing"],
    }
    if path is None or not path.is_file():
        return check

    try:
        kernel = load_json(path)
    except (OSError, ValueError) as exc:
        check.update({
            "status": "blocked_invalid_oracle_kernel",
            "blockers": [
                f"moonlab_qae_oracle_kernel could not be read: {exc}",
            ],
        })
        return check

    resource = dict_or_empty(kernel.get("resource_estimate"))
    control = dict_or_empty(kernel.get("moonlab_control_plane"))
    claim_posture = dict_or_empty(kernel.get("claim_posture"))
    circuit_path_raw = kernel.get("moonlab_circuit_file")
    circuit_path = (
        Path(circuit_path_raw)
        if isinstance(circuit_path_raw, str) and circuit_path_raw
        else None
    )
    circuit_check = classify_qae_circuit(circuit_path)
    blockers = []
    if kernel.get("schema") != "qge.moonlab_qae_oracle_kernel.v0":
        blockers.append(
            "moonlab_qae_oracle_kernel schema is not "
            "qge.moonlab_qae_oracle_kernel.v0")
    if circuit_check.get("status") != "ready_for_control_plane_submission":
        blockers.append(
            "oracle kernel circuit is not ready Moonlab control-plane text")
    if not claim_posture.get("qf_oracle_kernel_transpiled"):
        blockers.append("Q_f oracle kernel is not marked transpiled")
    executable = not blockers and bool(
        control.get("control_plane_executable"))
    check.update({
        "schema": kernel.get("schema"),
        "status": kernel.get("status"),
        "semantic_scope": kernel.get("semantic_scope"),
        "oracle_kernel_directly_executable": executable,
        "qf_oracle_kernel_transpiled": bool(
            claim_posture.get("qf_oracle_kernel_transpiled")),
        "full_qae_oracle_transpiled": bool(
            claim_posture.get("full_qae_oracle_transpiled")),
        "logical_qubits": resource.get("logical_qubits"),
        "gate_count": resource.get("gate_count"),
        "body_bytes": control.get("body_bytes"),
        "circuit_check": circuit_check,
        "blockers": blockers,
    })
    return check


def classify_moonlab_qae_observation_zero(path: Path | None) -> dict[str, Any]:
    info = file_info(path)
    check: dict[str, Any] = {
        "artifact": info,
        "schema": None,
        "status": "missing",
        "semantic_scope": None,
        "qae_observation_directly_executable": False,
        "candidate_state_preparation_transpiled": False,
        "power_zero_observation_transpiled": False,
        "qf_oracle_kernel_transpiled": False,
        "full_qae_oracle_transpiled": False,
        "logical_qubits": None,
        "gate_count": None,
        "body_bytes": None,
        "blockers": ["moonlab_qae_observation_zero artifact is missing"],
    }
    if path is None or not path.is_file():
        return check

    try:
        observation = load_json(path)
    except (OSError, ValueError) as exc:
        check.update({
            "status": "blocked_invalid_qae_observation",
            "blockers": [
                f"moonlab_qae_observation_zero could not be read: {exc}",
            ],
        })
        return check

    resource = dict_or_empty(observation.get("resource_estimate"))
    control = dict_or_empty(observation.get("moonlab_control_plane"))
    claim_posture = dict_or_empty(observation.get("claim_posture"))
    circuit_path_raw = observation.get("moonlab_circuit_file")
    circuit_path = (
        Path(circuit_path_raw)
        if isinstance(circuit_path_raw, str) and circuit_path_raw
        else None
    )
    circuit_check = classify_qae_circuit(circuit_path)
    blockers = []
    if observation.get("schema") != "qge.moonlab_qae_observation_circuit.v0":
        blockers.append(
            "moonlab_qae_observation_zero schema is not "
            "qge.moonlab_qae_observation_circuit.v0")
    if circuit_check.get("status") != "ready_for_control_plane_submission":
        blockers.append(
            "power-zero observation circuit is not ready Moonlab text")
    if not claim_posture.get("candidate_state_preparation_transpiled"):
        blockers.append("candidate state preparation is not marked transpiled")
    if not claim_posture.get("qf_oracle_kernel_transpiled"):
        blockers.append("Q_f kernel is not marked transpiled in observation")
    if not claim_posture.get("power_zero_observation_transpiled"):
        blockers.append("power-zero observation is not marked transpiled")
    executable = not blockers and bool(
        control.get("control_plane_executable"))
    check.update({
        "schema": observation.get("schema"),
        "status": observation.get("status"),
        "semantic_scope": observation.get("semantic_scope"),
        "qae_observation_directly_executable": executable,
        "candidate_state_preparation_transpiled": bool(
            claim_posture.get("candidate_state_preparation_transpiled")),
        "power_zero_observation_transpiled": bool(
            claim_posture.get("power_zero_observation_transpiled")),
        "qf_oracle_kernel_transpiled": bool(
            claim_posture.get("qf_oracle_kernel_transpiled")),
        "full_qae_oracle_transpiled": bool(
            claim_posture.get("full_qae_oracle_transpiled")),
        "logical_qubits": resource.get("logical_qubits"),
        "gate_count": resource.get("gate_count"),
        "body_bytes": control.get("body_bytes"),
        "circuit_check": circuit_check,
        "blockers": blockers,
    })
    return check


def classify_moonlab_qae_grover_schedule(path: Path | None) -> dict[str, Any]:
    info = file_info(path)
    check: dict[str, Any] = {
        "artifact": info,
        "schema": None,
        "status": "missing",
        "semantic_scope": None,
        "grover_schedule_directly_executable": False,
        "full_mlae_schedule_transpiled": False,
        "full_qae_oracle_transpiled": False,
        "logical_qubits": None,
        "observation_count": 0,
        "ready_observation_count": 0,
        "blocked_observation_count": 0,
        "max_body_bytes": None,
        "max_gate_count": None,
        "circuit_checks": [],
        "blockers": ["moonlab_qae_grover_schedule_plan artifact is missing"],
    }
    if path is None or not path.is_file():
        return check

    try:
        plan = load_json(path)
    except (OSError, ValueError) as exc:
        check.update({
            "status": "blocked_invalid_grover_schedule_plan",
            "blockers": [
                f"moonlab_qae_grover_schedule_plan could not be read: {exc}",
            ],
        })
        return check

    resource = dict_or_empty(plan.get("resource_estimate"))
    claim_posture = dict_or_empty(plan.get("claim_posture"))
    observations = [
        item for item in list_or_empty(plan.get("observations"))
        if isinstance(item, dict)
    ]
    blockers = []
    if plan.get("schema") != "qge.moonlab_qae_grover_schedule_plan.v0":
        blockers.append(
            "moonlab_qae_grover_schedule_plan schema is not "
            "qge.moonlab_qae_grover_schedule_plan.v0")
    if not observations:
        blockers.append("Grover schedule contains no observations")
    if resource.get("blocked_observation_count") not in (0, None):
        blockers.append("Grover schedule still has blocked observations")
    if not claim_posture.get("full_mlae_schedule_transpiled"):
        blockers.append("full MLAE Grover schedule is not marked transpiled")
    if not claim_posture.get("full_qae_oracle_transpiled"):
        blockers.append("full QAE oracle is not marked transpiled")

    circuit_checks = []
    for observation in observations:
        raw_path = observation.get("moonlab_circuit_file")
        circuit_path = Path(raw_path) if isinstance(raw_path, str) and raw_path else None
        circuit_check = classify_qae_circuit(circuit_path)
        expected_sha = observation.get("moonlab_circuit_sha256")
        actual_sha = dict_or_empty(circuit_check.get("artifact")).get("sha256")
        check_entry = {
            "observation_index": observation.get("observation_index"),
            "grover_power": observation.get("grover_power"),
            "moonlab_circuit_file": str(circuit_path)
            if circuit_path is not None else None,
            "status": circuit_check.get("status"),
            "format": circuit_check.get("format"),
            "body_bytes": observation.get("body_bytes"),
            "expected_sha256": expected_sha,
            "sha256": actual_sha,
            "blockers": list_or_empty(circuit_check.get("blockers")),
        }
        if circuit_check.get("status") != "ready_for_control_plane_submission":
            blockers.append(
                "Grover observation circuit is not ready Moonlab text: "
                f"{raw_path}"
            )
        if expected_sha and actual_sha != expected_sha:
            blockers.append(
                "Grover observation circuit sha256 does not match plan: "
                f"{raw_path}"
            )
            check_entry["blockers"].append("sha256_mismatch")
        if observation.get("status") != "ready_for_control_plane_submission":
            blockers.append(
                "Grover observation is not ready for control-plane submission: "
                f"power={observation.get('grover_power')}"
            )
        circuit_checks.append(check_entry)

    executable = not blockers and plan.get("status") == (
        "qae_grover_schedule_ready_for_control_plane_submission")
    check.update({
        "schema": plan.get("schema"),
        "status": plan.get("status"),
        "semantic_scope": plan.get("semantic_scope"),
        "grover_schedule_directly_executable": executable,
        "full_mlae_schedule_transpiled": bool(
            claim_posture.get("full_mlae_schedule_transpiled")),
        "full_qae_oracle_transpiled": bool(
            claim_posture.get("full_qae_oracle_transpiled")),
        "logical_qubits": resource.get("logical_qubits"),
        "observation_count": resource.get("observation_count"),
        "ready_observation_count": resource.get("ready_observation_count"),
        "blocked_observation_count": resource.get("blocked_observation_count"),
        "max_body_bytes": resource.get("max_body_bytes"),
        "max_gate_count": resource.get("max_gate_count"),
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
        info = path_info(path)
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
    oracle_kernel_path = (
        Path(required["moonlab_qae_oracle_kernel"])
        if isinstance(required.get("moonlab_qae_oracle_kernel"), str) and
        required.get("moonlab_qae_oracle_kernel")
        else None
    )
    observation_path = (
        Path(required["moonlab_qae_observation_zero"])
        if isinstance(required.get("moonlab_qae_observation_zero"), str) and
        required.get("moonlab_qae_observation_zero")
        else None
    )
    grover_schedule_path = (
        Path(required["moonlab_qae_grover_schedule_plan"])
        if isinstance(required.get("moonlab_qae_grover_schedule_plan"), str) and
        required.get("moonlab_qae_grover_schedule_plan")
        else None
    )
    artifacts, missing = artifact_checks(job)
    qae_check = classify_qae_circuit(qae_path)
    payload_check = classify_moonlab_qae_payload(payload_path)
    oracle_kernel_check = classify_moonlab_qae_oracle_kernel(
        oracle_kernel_path)
    observation_check = classify_moonlab_qae_observation_zero(
        observation_path)
    grover_schedule_check = classify_moonlab_qae_grover_schedule(
        grover_schedule_path)
    blockers = list(missing)
    grover_schedule_blockers = list_or_empty(
        grover_schedule_check.get("blockers"))
    if grover_schedule_path is not None:
        blockers.extend(grover_schedule_blockers)
    payload_blockers = list_or_empty(payload_check.get("blockers"))
    if payload_path is not None:
        blockers.extend(payload_blockers)
    oracle_kernel_blockers = list_or_empty(
        oracle_kernel_check.get("blockers"))
    if oracle_kernel_path is not None:
        blockers.extend(oracle_kernel_blockers)
    observation_blockers = list_or_empty(observation_check.get("blockers"))
    if observation_path is not None:
        blockers.extend(observation_blockers)
    grover_schedule_direct = bool(
        grover_schedule_check.get("grover_schedule_directly_executable")) and (
            "moonlab_qae_grover_schedule_plan" not in missing)
    if not grover_schedule_direct:
        blockers.extend(qae_check.get("blockers", []))
    direct = (
        grover_schedule_direct or
        bool(qae_check.get("moonlab_control_plane_executable"))
    ) and not missing
    payload_direct = bool(
        payload_check.get("control_plane_payload_directly_executable")) and (
            "moonlab_qae_payload" not in missing)
    oracle_kernel_direct = bool(
        oracle_kernel_check.get("oracle_kernel_directly_executable")) and (
            "moonlab_qae_oracle_kernel" not in missing)
    observation_direct = bool(
        observation_check.get("qae_observation_directly_executable")) and (
            "moonlab_qae_observation_zero" not in missing)
    if missing:
        status = "blocked_missing_required_artifact"
    elif grover_schedule_direct:
        status = "ready_for_control_plane_submission"
    elif observation_direct and qae_check.get("status") == (
        "blocked_transpilation_required"
    ):
        status = QAE_OBSERVATION_ZERO_READY_STATUS
    elif oracle_kernel_direct and payload_direct and qae_check.get("status") == (
        "blocked_transpilation_required"
    ):
        status = QF_KERNEL_READY_STATUS
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
        "moonlab_qae_oracle_kernel_check": oracle_kernel_check,
        "moonlab_qae_observation_zero_check": observation_check,
        "moonlab_qae_grover_schedule_plan_check": grover_schedule_check,
        "moonlab_control_plane_request": control_plane_request_contract(job),
        "blockers": blockers,
        "control_plane_payload_directly_executable": payload_direct,
        "oracle_kernel_directly_executable": oracle_kernel_direct,
        "qae_observation_directly_executable": observation_direct,
        "grover_schedule_directly_executable": grover_schedule_direct,
        "qf_oracle_kernel_transpiled": bool(
            oracle_kernel_check.get("qf_oracle_kernel_transpiled")),
        "candidate_state_preparation_transpiled": bool(
            observation_check.get("candidate_state_preparation_transpiled")),
        "power_zero_observation_transpiled": bool(
            observation_check.get("power_zero_observation_transpiled")),
        "full_mlae_schedule_transpiled": bool(
            grover_schedule_check.get("full_mlae_schedule_transpiled")),
        "full_qae_oracle_transpiled": bool(
            payload_check.get("full_qae_oracle_transpiled")) or bool(
                oracle_kernel_check.get("full_qae_oracle_transpiled")) or bool(
                    observation_check.get("full_qae_oracle_transpiled")) or bool(
                        grover_schedule_check.get("full_qae_oracle_transpiled")),
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
    if any(status == QAE_OBSERVATION_ZERO_READY_STATUS
           for status in statuses):
        return QAE_OBSERVATION_ZERO_READY_STATUS
    if any(status == QF_KERNEL_READY_STATUS for status in statuses):
        return QF_KERNEL_READY_STATUS
    if any(status == "calibration_payload_ready_oracle_transpilation_required"
           for status in statuses):
        return "calibration_payload_ready_oracle_transpilation_required"
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
        if not candidate.get("grover_schedule_directly_executable") and
        candidate.get("qae_circuit_check", {}).get("transpilation_required")
    )
    missing = sum(
        1 for candidate in candidates
        if candidate.get("control_plane_submission_status") ==
        "blocked_missing_required_artifact"
    )
    calibration_ready = sum(
        1 for candidate in candidates
        if candidate.get("control_plane_payload_directly_executable")
    )
    oracle_kernel_ready = sum(
        1 for candidate in candidates
        if candidate.get("oracle_kernel_directly_executable")
    )
    qae_observation_ready = sum(
        1 for candidate in candidates
        if candidate.get("qae_observation_directly_executable")
    )
    grover_schedule_ready = sum(
        1 for candidate in candidates
        if candidate.get("grover_schedule_directly_executable")
    )
    payload_direct = bool(candidates) and all(
        bool(candidate.get("control_plane_payload_directly_executable"))
        for candidate in candidates
    )
    oracle_kernel_direct = bool(candidates) and all(
        bool(candidate.get("oracle_kernel_directly_executable"))
        for candidate in candidates
    )
    observation_direct = bool(candidates) and all(
        bool(candidate.get("qae_observation_directly_executable"))
        for candidate in candidates
    )
    grover_schedule_direct = bool(candidates) and all(
        bool(candidate.get("grover_schedule_directly_executable"))
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
        "oracle_kernel_ready_count": oracle_kernel_ready,
        "qae_observation_ready_count": qae_observation_ready,
        "grover_schedule_ready_count": grover_schedule_ready,
        "transpilation_required_count": transpilation_required,
        "missing_artifact_candidate_count": missing,
        "hardware_submission_directly_executable": direct,
        "control_plane_payload_directly_executable": payload_direct,
        "oracle_kernel_directly_executable": oracle_kernel_direct,
        "qae_observation_directly_executable": observation_direct,
        "grover_schedule_directly_executable": grover_schedule_direct,
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
            "A Moonlab hardware candidate is not directly executable until every selected circuit artifact is moonlab-circuit v1.",
            "Abstract QGE QAE circuit text requires a transpilation step before control-plane submission.",
            "Readout-equivalent Moonlab payloads can validate shot plumbing without proving the full QAE oracle is transpiled.",
            "Q_f and power-zero observations are intermediate artifacts; the selected Grover schedule is the full MLAE control-plane payload set.",
            "This bundle records submission readiness, not a hardware result.",
        ],
    }


def markdown_report(bundle: dict[str, Any]) -> str:
    lines = [
        "# QGE Moonlab Submission Bundle",
        "",
        f"Status: `{bundle['status']}`",
        "",
        "| Jobs | Ready | Calibration Ready | Q_f Kernel Ready | Observation Ready | Grover Ready | Transpilation Required | Missing Artifacts | Directly Executable |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        (
            f"| {bundle['hardware_candidate_job_count']} | "
            f"{bundle['ready_for_control_plane_submission_count']} | "
            f"{bundle['calibration_payload_ready_count']} | "
            f"{bundle['oracle_kernel_ready_count']} | "
            f"{bundle['qae_observation_ready_count']} | "
            f"{bundle['grover_schedule_ready_count']} | "
            f"{bundle['transpilation_required_count']} | "
            f"{bundle['missing_artifact_candidate_count']} | "
            f"{bundle['control_plane_payload_directly_executable']} |"
        ),
        "",
        "| Job | Control-Plane Status | Circuit Format | Payload Scope | Kernel Scope | Observation Scope | Grover Scope | Qubits | Blockers |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for job in bundle["candidate_jobs"]:
        qae_check = dict_or_empty(job.get("qae_circuit_check"))
        payload_check = dict_or_empty(job.get("moonlab_qae_payload_check"))
        kernel_check = dict_or_empty(
            job.get("moonlab_qae_oracle_kernel_check"))
        observation_check = dict_or_empty(
            job.get("moonlab_qae_observation_zero_check"))
        grover_check = dict_or_empty(
            job.get("moonlab_qae_grover_schedule_plan_check"))
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
            f"{kernel_check.get('semantic_scope')} | "
            f"{observation_check.get('semantic_scope')} | "
            f"{grover_check.get('semantic_scope')} | "
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
        "oracle_kernel_ready_count": bundle.get(
            "oracle_kernel_ready_count"),
        "qae_observation_ready_count": bundle.get(
            "qae_observation_ready_count"),
        "grover_schedule_ready_count": bundle.get(
            "grover_schedule_ready_count"),
        "transpilation_required_count": bundle.get(
            "transpilation_required_count"),
        "missing_artifact_candidate_count": bundle.get(
            "missing_artifact_candidate_count"),
        "hardware_submission_directly_executable": bundle.get(
            "hardware_submission_directly_executable"),
        "control_plane_payload_directly_executable": bundle.get(
            "control_plane_payload_directly_executable"),
        "oracle_kernel_directly_executable": bundle.get(
            "oracle_kernel_directly_executable"),
        "qae_observation_directly_executable": bundle.get(
            "qae_observation_directly_executable"),
        "grover_schedule_directly_executable": bundle.get(
            "grover_schedule_directly_executable"),
        "hardware_quantum_advantage_claimed": False,
        "whole_game_hardware_execution_claimed": False,
        "dense_70000_qubit_state_claimed": False,
        "status": "success",
    }


def candidate_digest_index(bundle: dict[str, Any]) -> dict[str, str]:
    indexed: dict[str, str] = {}
    for candidate in list_or_empty(bundle.get("candidate_jobs")):
        if not isinstance(candidate, dict):
            continue
        job_id = candidate.get("job_id")
        digest = candidate.get("candidate_digest")
        if isinstance(job_id, str) and isinstance(digest, str):
            indexed[job_id] = digest
    return indexed


def scoped_check(name: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {
        "check": name,
        "status": "pass" if passed else "attention_required",
        "evidence": evidence,
    }


def build_hardware_submission_scope(
    submission_packet: dict[str, Any],
    submission_bundle: dict[str, Any],
    hardware_record_template: dict[str, Any],
    *,
    packet_path: Path | None = None,
    bundle_path: Path | None = None,
    hardware_template_path: Path | None = None,
) -> dict[str, Any]:
    digests = candidate_digest_index(submission_bundle)
    template_record = dict_or_empty(hardware_record_template.get("record"))
    validation_contract = dict_or_empty(
        hardware_record_template.get("validation_contract"))
    template_job_id = hardware_record_template.get("job_id")
    template_digest = hardware_record_template.get("candidate_digest")
    expected_digest = (
        digests.get(template_job_id)
        if isinstance(template_job_id, str)
        else None
    )
    checks = [
        scoped_check(
            "submission_packet_schema",
            submission_packet.get("schema") == "qge.moonlab_submission_packet.v0",
            submission_packet.get("schema"),
        ),
        scoped_check(
            "submission_bundle_schema",
            submission_bundle.get("schema") == "qge.moonlab_submission_bundle.v0",
            submission_bundle.get("schema"),
        ),
        scoped_check(
            "hardware_record_template_schema",
            hardware_record_template.get("schema") ==
            "qge.moonlab_hardware_record_template.v0",
            hardware_record_template.get("schema"),
        ),
        scoped_check(
            "control_plane_payloads_ready",
            submission_bundle.get("status") ==
            "ready_for_control_plane_submission",
            submission_bundle.get("status"),
        ),
        scoped_check(
            "hardware_submission_directly_executable",
            bool(submission_bundle.get("hardware_submission_directly_executable")),
            submission_bundle.get("hardware_submission_directly_executable"),
        ),
        scoped_check(
            "ready_candidate_count_positive",
            isinstance(submission_bundle.get("ready_for_control_plane_submission_count"), int) and
            submission_bundle.get("ready_for_control_plane_submission_count") > 0,
            submission_bundle.get("ready_for_control_plane_submission_count"),
        ),
        scoped_check(
            "hardware_template_candidate_digest_matches_bundle",
            isinstance(template_digest, str) and template_digest == expected_digest,
            {
                "template_job_id": template_job_id,
                "template_candidate_digest": template_digest,
                "bundle_candidate_digest": expected_digest,
            },
        ),
        scoped_check(
            "hardware_record_validation_contract_present",
            bool(validation_contract),
            sorted(validation_contract.keys()),
        ),
        scoped_check(
            "hardware_record_no_overclaim_template",
            not bool(template_record.get("hardware_quantum_advantage_claimed")) and
            not bool(template_record.get("whole_game_hardware_execution_claimed")) and
            not bool(template_record.get("dense_70000_qubit_state_claimed")),
            {
                "hardware_quantum_advantage_claimed": template_record.get(
                    "hardware_quantum_advantage_claimed"),
                "whole_game_hardware_execution_claimed": template_record.get(
                    "whole_game_hardware_execution_claimed"),
                "dense_70000_qubit_state_claimed": template_record.get(
                    "dense_70000_qubit_state_claimed"),
            },
        ),
    ]
    ready = all(check["status"] == "pass" for check in checks)
    return {
        "schema": "qge.moonlab_hardware_submission_scope.v0",
        "status": "ready_for_control_plane_submission"
        if ready else "attention_required_for_control_plane_submission",
        "scope": "bounded_qae_hardware_candidate",
        "source_submission_packet": str(packet_path) if packet_path else None,
        "source_submission_bundle": str(bundle_path) if bundle_path else None,
        "source_hardware_record_template": (
            str(hardware_template_path) if hardware_template_path else None),
        "hardware_submission_scope_ready": ready,
        "hardware_candidate_job_count": submission_bundle.get(
            "hardware_candidate_job_count"),
        "ready_for_control_plane_submission_count": submission_bundle.get(
            "ready_for_control_plane_submission_count"),
        "hardware_submission_directly_executable": submission_bundle.get(
            "hardware_submission_directly_executable"),
        "grover_schedule_directly_executable": submission_bundle.get(
            "grover_schedule_directly_executable"),
        "candidate_job_ids": sorted(digests.keys()),
        "candidate_digests": digests,
        "hardware_record_template_job_id": template_job_id,
        "hardware_record_template_candidate_digest": template_digest,
        "hardware_record_schema": hardware_record_template.get("record_schema"),
        "hardware_record_validation_contract": validation_contract,
        "readiness_checks": checks,
        "passing_check_count": sum(
            1 for check in checks if check["status"] == "pass"),
        "attention_check_count": sum(
            1 for check in checks if check["status"] != "pass"),
        "out_of_scope": [
            "full_game_moonlab_deployment_gate",
            "registered_bsp_asset_availability",
            "whole_game_hardware_execution",
            "hardware_quantum_advantage",
            "dense_70000_qubit_state_execution",
        ],
        "claim_posture": {
            "bounded_hardware_submission_ready_claimed": ready,
            "hardware_result_claimed": False,
            "hardware_quantum_advantage_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "dense_70000_qubit_state_claimed": False,
        },
        "limits": [
            "This scoped artifact covers only the bounded QAE hardware-candidate handoff.",
            "Full-game Moonlab deployment remains governed by qge_moonlab_deployment_gate.json.",
            "A ready submission scope is not a returned hardware result.",
        ],
    }


def build_scope_icc_evidence(
    scope: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    ready = bool(scope.get("hardware_submission_scope_ready"))
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_moonlab_hardware_submission_scope",
        "completion_reason": (
            "qge_moonlab_hardware_submission_scope_ready"
            if ready else
            "qge_moonlab_hardware_submission_scope_attention_required"
        ),
        "moonlab_hardware_submission_scope_file": (
            str(out_path) if out_path else None),
        "moonlab_hardware_submission_scope_schema": scope.get("schema"),
        "moonlab_hardware_submission_scope_status": scope.get("status"),
        "moonlab_hardware_submission_scope_ready": ready,
        "hardware_candidate_job_count": scope.get(
            "hardware_candidate_job_count"),
        "ready_for_control_plane_submission_count": scope.get(
            "ready_for_control_plane_submission_count"),
        "hardware_submission_directly_executable": scope.get(
            "hardware_submission_directly_executable"),
        "grover_schedule_directly_executable": scope.get(
            "grover_schedule_directly_executable"),
        "passing_check_count": scope.get("passing_check_count"),
        "attention_check_count": scope.get("attention_check_count"),
        "candidate_job_ids": scope.get("candidate_job_ids"),
        "hardware_record_schema": scope.get("hardware_record_schema"),
        "hardware_record_template_job_id": scope.get(
            "hardware_record_template_job_id"),
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
    parser.add_argument("--hardware-template", type=Path)
    parser.add_argument("--scope-out", type=Path)
    parser.add_argument("--scope-icc-json", type=Path)
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
        if args.scope_out or args.scope_icc_json:
            if not args.hardware_template:
                raise ValueError(
                    "--hardware-template is required with --scope-out or "
                    "--scope-icc-json")
            template = load_json(args.hardware_template)
            scope = build_hardware_submission_scope(
                packet,
                bundle,
                template,
                packet_path=args.submission_packet,
                bundle_path=args.out,
                hardware_template_path=args.hardware_template,
            )
            if args.scope_out:
                write_json(args.scope_out, scope)
            if args.scope_icc_json:
                write_json(
                    args.scope_icc_json,
                    build_scope_icc_evidence(scope, out_path=args.scope_out),
                )
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_moonlab_submission_bundle: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_MOONLAB_SUBMISSION_BUNDLE {args.out}")
    if args.markdown:
        print(f"QGE_MOONLAB_SUBMISSION_BUNDLE_MARKDOWN {args.markdown}")
    if args.icc_json:
        print(f"QGE_MOONLAB_SUBMISSION_BUNDLE_ICC_EVIDENCE {args.icc_json}")
    if args.scope_out:
        print(f"QGE_MOONLAB_HARDWARE_SUBMISSION_SCOPE {args.scope_out}")
    if args.scope_icc_json:
        print(
            "QGE_MOONLAB_HARDWARE_SUBMISSION_SCOPE_ICC_EVIDENCE "
            f"{args.scope_icc_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
