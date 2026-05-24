#!/usr/bin/env python3
"""Emit Moonlab control-plane payloads for QGE QAE observation schedules."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Sequence


MOONLAB_HEADER = "# moonlab-circuit v1"
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def theta_for_success_probability(probability: float) -> float:
    return 2.0 * math.asin(math.sqrt(clamp01(probability)))


def moonlab_observation_circuit(probability: float) -> str:
    theta = theta_for_success_probability(probability)
    return (
        f"{MOONLAB_HEADER}\n"
        "NUM_QUBITS 1\n"
        f"RY 0 {theta:.17g}\n"
    )


def read_abstract_circuit_status(path: Path | None) -> dict[str, Any]:
    status: dict[str, Any] = {
        "path": str(path) if path is not None else None,
        "exists": bool(path is not None and path.is_file()),
        "sha256": sha256_file(path) if path is not None else None,
        "format": "missing",
    }
    if path is None or not path.is_file():
        return status
    text = path.read_text(encoding="utf-8", errors="replace")
    first_line = next((line.strip() for line in text.splitlines()
                       if line.strip()), "")
    status["first_line"] = first_line
    status["format"] = (
        "qge_abstract_qae_circuit_v0"
        if ABSTRACT_QGE_QAE_HEADER in text[:1024]
        else "unknown_text_circuit"
    )
    return status


def selected_estimator(metrics: dict[str, Any]) -> dict[str, Any]:
    estimators = [
        item for item in list_or_empty(metrics.get("quantum_estimators"))
        if isinstance(item, dict)
    ]
    if not estimators:
        raise ValueError("metrics contain no quantum_estimators")
    best_qae = dict_or_empty(dict_or_empty(
        metrics.get("comparison")).get("best_qae"))
    target_calls = best_qae.get("oracle_eval_count")
    if isinstance(target_calls, int):
        for estimator in estimators:
            if estimator.get("oracle_eval_count") == target_calls:
                return estimator
    return max(estimators, key=lambda item: int(item.get("oracle_eval_count")
                                               or 0))


def build_payload(
    metrics: dict[str, Any],
    *,
    metrics_path: Path | None = None,
    abstract_circuit_path: Path | None = None,
    circuit_dir: Path | None = None,
) -> dict[str, Any]:
    estimator = selected_estimator(metrics)
    observations = [
        item for item in list_or_empty(estimator.get("observations"))
        if isinstance(item, dict)
    ]
    if not observations:
        raise ValueError("selected estimator contains no observations")
    if circuit_dir is not None:
        circuit_dir.mkdir(parents=True, exist_ok=True)

    circuits = []
    total_shots = 0
    for index, observation in enumerate(observations):
        probability = float(observation.get("success_probability"))
        shots = int(observation.get("shots") or 0)
        if shots <= 0:
            raise ValueError("observation shots must be > 0")
        circuit_text = moonlab_observation_circuit(probability)
        encoded = circuit_text.encode("utf-8")
        circuit_path = None
        if circuit_dir is not None:
            circuit_path = circuit_dir / f"observation_{index:03d}.moonlab"
            circuit_path.write_text(circuit_text, encoding="utf-8")
        total_shots += shots
        circuits.append({
            "observation_index": index,
            "grover_power": observation.get("grover_power"),
            "grover_factor": observation.get("grover_factor"),
            "success_probability": probability,
            "theta": theta_for_success_probability(probability),
            "shots": shots,
            "moonlab_circuit_file": str(circuit_path)
            if circuit_path is not None else None,
            "moonlab_circuit_sha256": sha256_bytes(encoded),
            "moonlab_payload_bytes": len(encoded),
            "control_plane_verb": "SHOTS",
        })

    resource = dict_or_empty(metrics.get("resource_estimate"))
    return {
        "schema": "qge.moonlab_qae_payload.v0",
        "status": "calibration_payload_ready_oracle_transpilation_required",
        "semantic_scope": "mlae_observation_distribution_payload",
        "source_metrics": str(metrics_path) if metrics_path is not None else None,
        "source_abstract_circuit": read_abstract_circuit_status(
            abstract_circuit_path),
        "advantage_problem_id": metrics.get("advantage_problem_id"),
        "observable": metrics.get("observable"),
        "selected_estimator": {
            "algorithm": estimator.get("algorithm"),
            "oracle_eval_count": estimator.get("oracle_eval_count"),
            "shots": estimator.get("shots"),
            "shots_per_power": estimator.get("shots_per_power"),
            "grover_powers": estimator.get("grover_powers"),
            "seed": estimator.get("seed"),
        },
        "abstract_resource_estimate": resource,
        "payload_resource_estimate": {
            "logical_qubits": 1,
            "circuit_count": len(circuits),
            "one_qubit_gates": len(circuits),
            "two_qubit_gates": 0,
            "total_shots": total_shots,
            "gate_set": ["RY", "MEASURE"],
        },
        "moonlab_control_plane": {
            "payload_header": MOONLAB_HEADER,
            "required_declaration": "NUM_QUBITS 1",
            "verb": "SHOTS",
            "shots_per_circuit": [
                {
                    "observation_index": item["observation_index"],
                    "shots": item["shots"],
                }
                for item in circuits
            ],
        },
        "observation_circuits": circuits,
        "claim_posture": {
            "full_qae_oracle_transpiled": False,
            "hardware_result_claimed": False,
            "hardware_quantum_advantage_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "dense_70000_qubit_state_claimed": False,
        },
        "limits": [
            "This payload is directly executable Moonlab control-plane text for the MLAE observation distribution.",
            "It does not decompose Q_f, S_chi, S_0, A, or A_dagger into a reversible QAE oracle.",
            "It can validate hardware shot plumbing and readout behavior, not hardware quantum advantage.",
        ],
    }


def markdown_report(payload: dict[str, Any]) -> str:
    resource = dict_or_empty(payload.get("payload_resource_estimate"))
    lines = [
        "# QGE Moonlab QAE Payload",
        "",
        f"Status: `{payload['status']}`",
        f"Semantic scope: `{payload['semantic_scope']}`",
        "",
        "| Circuits | Total Shots | Payload Qubits | Full Oracle Transpiled |",
        "| ---: | ---: | ---: | --- |",
        (
            f"| {resource.get('circuit_count')} | "
            f"{resource.get('total_shots')} | "
            f"{resource.get('logical_qubits')} | "
            f"{payload['claim_posture']['full_qae_oracle_transpiled']} |"
        ),
        "",
        "| Observation | Grover Power | Probability | Theta | Shots |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["observation_circuits"]:
        lines.append(
            f"| {item['observation_index']} | "
            f"{item.get('grover_power')} | "
            f"{item['success_probability']:.9f} | "
            f"{item['theta']:.9f} | "
            f"{item['shots']} |"
        )
    lines.extend([
        "",
        "Claims: no hardware result, hardware quantum advantage, whole-game hardware execution, dense 70,000-qubit state, or full QAE oracle transpilation is claimed.",
        "",
    ])
    return "\n".join(lines)


def build_icc_evidence(
    payload: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    resource = dict_or_empty(payload.get("payload_resource_estimate"))
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_moonlab_qae_transpile",
        "completion_reason": "qge_moonlab_qae_payload_recorded",
        "moonlab_qae_payload_file": str(out_path) if out_path else None,
        "moonlab_qae_payload_schema": payload.get("schema"),
        "moonlab_qae_payload_status": payload.get("status"),
        "semantic_scope": payload.get("semantic_scope"),
        "payload_circuit_count": resource.get("circuit_count"),
        "payload_total_shots": resource.get("total_shots"),
        "payload_logical_qubits": resource.get("logical_qubits"),
        "full_qae_oracle_transpiled": False,
        "hardware_result_claimed": False,
        "hardware_quantum_advantage_claimed": False,
        "whole_game_hardware_execution_claimed": False,
        "dense_70000_qubit_state_claimed": False,
        "status": "success",
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--abstract-circuit", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--circuit-dir", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        metrics = load_json(args.metrics)
        payload = build_payload(
            metrics,
            metrics_path=args.metrics,
            abstract_circuit_path=args.abstract_circuit,
            circuit_dir=args.circuit_dir,
        )
        write_json(args.out, payload)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(payload),
                                     encoding="utf-8")
        if args.icc_json:
            write_json(args.icc_json, build_icc_evidence(
                payload,
                out_path=args.out,
            ))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_moonlab_qae_transpile: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_MOONLAB_QAE_PAYLOAD {args.out}")
    if args.circuit_dir:
        print(f"QGE_MOONLAB_QAE_CIRCUITS {args.circuit_dir}")
    if args.markdown:
        print(f"QGE_MOONLAB_QAE_PAYLOAD_MARKDOWN {args.markdown}")
    if args.icc_json:
        print(f"QGE_MOONLAB_QAE_PAYLOAD_ICC_EVIDENCE {args.icc_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
