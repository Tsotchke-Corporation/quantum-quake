#!/usr/bin/env python3
"""Transpile a power-zero QGE QAE observation circuit to moonlab-circuit v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_moonlab_oracle_transpile as qf_transpile  # noqa: E402
import qge_moonlab_qae_transpile as qae_transpile  # noqa: E402


MOONLAB_HEADER = qf_transpile.MOONLAB_HEADER
MOONLAB_CONTROL_MAX_BODY_BYTES = qf_transpile.MOONLAB_CONTROL_MAX_BODY_BYTES
OBSERVATION_ZERO_STATUS_READY = (
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | None) -> str | None:
    if path is None or not path.is_file():
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


def angle_text(theta: float) -> str:
    return f"{theta:.15g}"


def emit_ry(circuit: qf_transpile.MoonlabCircuitBuilder,
            target: int,
            theta: float) -> None:
    if abs(theta) < 1.0e-15:
        return
    circuit.add(f"RY {target} {angle_text(theta)}")


def emit_cry(circuit: qf_transpile.MoonlabCircuitBuilder,
             control: int,
             target: int,
             theta: float) -> None:
    emit_ry(circuit, target, theta / 2.0)
    circuit.cnot(target, control)
    emit_ry(circuit, target, -theta / 2.0)
    circuit.cnot(target, control)


def emit_prefix_mcx(circuit: qf_transpile.MoonlabCircuitBuilder,
                    controls: list[tuple[int, int]],
                    flag_qubit: int,
                    mcx_ancilla: list[int]) -> None:
    control_qubits = [qubit for qubit, _ in controls]
    zero_controls = [
        qubit for qubit, expected in controls
        if expected == 0
    ]
    for qubit in zero_controls:
        circuit.x(qubit)
    qf_transpile.emit_mcx(circuit, control_qubits, flag_qubit, mcx_ancilla)
    for qubit in reversed(zero_controls):
        circuit.x(qubit)


def emit_controlled_ry(circuit: qf_transpile.MoonlabCircuitBuilder,
                       controls: list[tuple[int, int]],
                       target: int,
                       theta: float,
                       flag_qubit: int,
                       mcx_ancilla: list[int]) -> None:
    if abs(theta) < 1.0e-15:
        return
    if not controls:
        emit_ry(circuit, target, theta)
        return
    if len(controls) == 1:
        control, expected = controls[0]
        if expected == 0:
            circuit.x(control)
        emit_cry(circuit, control, target, theta)
        if expected == 0:
            circuit.x(control)
        return

    emit_prefix_mcx(circuit, controls, flag_qubit, mcx_ancilla)
    emit_cry(circuit, flag_qubit, target, theta)
    emit_prefix_mcx(circuit, controls, flag_qubit, mcx_ancilla)


def record_rotation(stats: dict[str, Any],
                    controls: list[tuple[int, int]]) -> None:
    stats["rotation_count"] += 1
    stats["controlled_rotation_count"] += 1 if controls else 0
    stats["max_control_count"] = max(
        int(stats["max_control_count"]), len(controls))


def emit_uniform_range_state_preparation(
    circuit: qf_transpile.MoonlabCircuitBuilder,
    candidate_qubits: list[int],
    candidate_count: int,
    flag_qubit: int,
    mcx_ancilla: list[int],
) -> dict[str, Any]:
    capacity = 1 << len(candidate_qubits)
    if candidate_count <= 0 or candidate_count > capacity:
        raise ValueError("candidate_count is outside the candidate register")
    stats: dict[str, Any] = {
        "algorithm": "recursive_uniform_range_state_preparation_v0",
        "candidate_count": candidate_count,
        "candidate_register_capacity": capacity,
        "candidate_index_bits": len(candidate_qubits),
        "target_probability_per_valid_candidate": 1.0 / candidate_count,
        "invalid_candidate_probability": 0.0,
        "rotation_count": 0,
        "controlled_rotation_count": 0,
        "full_subtree_count": 0,
        "partial_subtree_count": 0,
        "max_control_count": 0,
    }

    def emit_range(qubits: list[int],
                   count: int,
                   controls: list[tuple[int, int]]) -> None:
        if not qubits or count <= 1:
            return
        node_capacity = 1 << len(qubits)
        if count == node_capacity:
            stats["full_subtree_count"] += 1
            for qubit in reversed(qubits):
                record_rotation(stats, controls)
                emit_controlled_ry(
                    circuit,
                    controls,
                    qubit,
                    math.pi / 2.0,
                    flag_qubit,
                    mcx_ancilla,
                )
            return

        stats["partial_subtree_count"] += 1
        split_qubit = qubits[-1]
        half_capacity = node_capacity // 2
        left_count = min(count, half_capacity)
        right_count = max(count - half_capacity, 0)
        if left_count == 0:
            theta = math.pi
        elif right_count == 0:
            theta = 0.0
        else:
            theta = 2.0 * math.asin(math.sqrt(right_count / count))
        if abs(theta) >= 1.0e-15:
            record_rotation(stats, controls)
            emit_controlled_ry(
                circuit,
                controls,
                split_qubit,
                theta,
                flag_qubit,
                mcx_ancilla,
            )
        lower_qubits = qubits[:-1]
        if left_count:
            emit_range(lower_qubits, left_count, controls + [(split_qubit, 0)])
        if right_count:
            emit_range(lower_qubits, right_count, controls + [(split_qubit, 1)])

    emit_range(candidate_qubits, candidate_count, [])
    return stats


def power_zero_observation(metrics: dict[str, Any]) -> dict[str, Any]:
    estimator = qae_transpile.selected_estimator(metrics)
    for observation in list_or_empty(estimator.get("observations")):
        if not isinstance(observation, dict):
            continue
        if int(observation.get("grover_power") or 0) == 0:
            return {
                "algorithm": estimator.get("algorithm"),
                "oracle_eval_count": estimator.get("oracle_eval_count"),
                "selected_estimator_grover_powers": estimator.get(
                    "grover_powers"),
                "observation_index": list_or_empty(
                    estimator.get("observations")).index(observation),
                "grover_power": observation.get("grover_power"),
                "grover_factor": observation.get("grover_factor"),
                "shots": observation.get("shots"),
                "simulator_success_probability": observation.get(
                    "success_probability"),
                "simulator_successes": observation.get("successes"),
            }
    raise ValueError("selected estimator has no grover_power=0 observation")


def build_observation_circuit(
    metrics: dict[str, Any],
    oracle_scene: dict[str, Any],
    *,
    metrics_path: Path | None = None,
    oracle_scene_path: Path | None = None,
    circuit_path: Path | None = None,
) -> dict[str, Any]:
    resource = dict_or_empty(metrics.get("resource_estimate"))
    candidate_bits = int(resource.get("candidate_index_bits") or 0)
    threshold_bits = int(resource.get("contribution_threshold_bits") or 0)
    if candidate_bits <= 0 or threshold_bits <= 0:
        raise ValueError("metrics resource_estimate is missing register widths")

    success_counts, quantization = qf_transpile.contribution_success_counts(
        oracle_scene, metrics)
    layout = qf_transpile.build_qubit_layout(candidate_bits, threshold_bits)
    if layout["num_qubits"] > 32:
        raise ValueError(
            f"observation circuit requires {layout['num_qubits']} qubits; "
            "Moonlab text control plane accepts at most 32 for this path")

    circuit = qf_transpile.MoonlabCircuitBuilder(layout["num_qubits"])
    state_prep = emit_uniform_range_state_preparation(
        circuit,
        layout["candidate"],
        int(quantization["candidate_count"]),
        layout["flag"],
        layout["mcx_ancilla"],
    )
    state_prep_gate_count = circuit.gate_count()
    for threshold_qubit in layout["threshold"]:
        circuit.h(threshold_qubit)
    threshold_prep_gate_count = circuit.gate_count() - state_prep_gate_count
    qf_start_gate = circuit.gate_count()
    qf_transpile.emit_qrom_value_load(
        circuit,
        layout["candidate"],
        layout["value"],
        layout["flag"],
        layout["mcx_ancilla"],
        success_counts,
    )
    qf_transpile.emit_less_than_comparator(
        circuit,
        layout["threshold"],
        layout["value"],
        layout["good"],
        layout["comparator_scratch"],
    )
    qf_transpile.emit_qrom_value_load(
        circuit,
        layout["candidate"],
        layout["value"],
        layout["flag"],
        layout["mcx_ancilla"],
        success_counts,
    )
    qf_gate_count = circuit.gate_count() - qf_start_gate
    circuit_text = circuit.text()
    circuit_bytes = circuit_text.encode("utf-8")
    if circuit_path is not None:
        circuit_path.parent.mkdir(parents=True, exist_ok=True)
        circuit_path.write_text(circuit_text, encoding="utf-8")

    body_bytes = len(circuit_bytes)
    control_plane_ready = body_bytes <= MOONLAB_CONTROL_MAX_BODY_BYTES
    status = OBSERVATION_ZERO_STATUS_READY if control_plane_ready else (
        "blocked_control_plane_body_limit")
    observation = power_zero_observation(metrics)
    return {
        "schema": "qge.moonlab_qae_observation_circuit.v0",
        "status": status,
        "semantic_scope": "bernoulli_lift_qae_power_zero_observation",
        "source_metrics": str(metrics_path) if metrics_path is not None else None,
        "source_metrics_sha256": sha256_file(metrics_path),
        "source_oracle_scene": (
            str(oracle_scene_path) if oracle_scene_path is not None else None),
        "source_oracle_scene_sha256": sha256_file(oracle_scene_path),
        "moonlab_circuit_file": (
            str(circuit_path) if circuit_path is not None else None),
        "moonlab_circuit_sha256": sha256_bytes(circuit_bytes),
        "moonlab_control_plane": {
            "payload_header": MOONLAB_HEADER,
            "verb": "SHOTS",
            "body_bytes": body_bytes,
            "body_limit_bytes": MOONLAB_CONTROL_MAX_BODY_BYTES,
            "control_plane_executable": control_plane_ready,
        },
        "qubit_layout": layout,
        "state_preparation": state_prep,
        "threshold_preparation": {
            "algorithm": "uniform_hadamard_threshold_register",
            "threshold_count": 1 << threshold_bits,
            "threshold_bits": threshold_bits,
            "gate_count": threshold_prep_gate_count,
        },
        "predicate": {
            "meaning": (
                "good ^= (candidate < candidate_count and threshold < "
                "success_count[candidate])"
            ),
            "candidate_count": int(quantization["candidate_count"]),
            "invalid_candidate_probability": 0.0,
            "threshold_register_denominator": quantization[
                "bernoulli_denominator"],
        },
        "selected_observation": observation,
        "quantization": {
            **quantization,
            "power_zero_circuit_success_probability": quantization[
                "kernel_amplitude"],
            "selected_simulator_probability_delta": (
                quantization["kernel_amplitude"] -
                float(observation.get("simulator_success_probability") or 0.0)
            ),
        },
        "resource_estimate": {
            "logical_qubits": layout["num_qubits"],
            "gate_count": circuit.gate_count(),
            "candidate_state_preparation_gates": state_prep_gate_count,
            "threshold_preparation_gates": threshold_prep_gate_count,
            "qf_kernel_gates": qf_gate_count,
            "body_bytes": body_bytes,
            "candidate_entries": int(quantization["candidate_count"]),
            "gate_set": ["H", "X", "RY", "RZ", "CNOT"],
        },
        "claim_posture": {
            "candidate_state_preparation_transpiled": control_plane_ready,
            "qf_oracle_kernel_transpiled": control_plane_ready,
            "power_zero_observation_transpiled": control_plane_ready,
            "grover_operator_transpiled": False,
            "full_mlae_schedule_transpiled": False,
            "full_qae_oracle_transpiled": False,
            "hardware_result_claimed": False,
            "hardware_quantum_advantage_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "dense_70000_qubit_state_claimed": False,
        },
        "limits": [
            "This is a directly executable Moonlab circuit for the grover_power=0 QAE observation.",
            "It includes exact non-power-of-two candidate state preparation, uniform threshold preparation, and the reversible Q_f kernel.",
            "It does not include Grover diffusion, nonzero Grover powers, the full MLAE schedule, hardware result metadata, or a hardware advantage claim.",
        ],
    }


def markdown_report(observation: dict[str, Any]) -> str:
    resource = dict_or_empty(observation.get("resource_estimate"))
    control = dict_or_empty(observation.get("moonlab_control_plane"))
    state_prep = dict_or_empty(observation.get("state_preparation"))
    quantization = dict_or_empty(observation.get("quantization"))
    posture = dict_or_empty(observation.get("claim_posture"))
    lines = [
        "# QGE Moonlab QAE Power-Zero Observation",
        "",
        f"Status: `{observation['status']}`",
        f"Semantic scope: `{observation['semantic_scope']}`",
        "",
        "| Qubits | Gates | Body Bytes | Body Limit | Candidate Prep | Q_f | Full MLAE |",
        "| ---: | ---: | ---: | ---: | --- | --- | --- |",
        (
            f"| {resource.get('logical_qubits')} | "
            f"{resource.get('gate_count')} | "
            f"{control.get('body_bytes')} | "
            f"{control.get('body_limit_bytes')} | "
            f"{posture.get('candidate_state_preparation_transpiled')} | "
            f"{posture.get('qf_oracle_kernel_transpiled')} | "
            f"{posture.get('full_mlae_schedule_transpiled')} |"
        ),
        "",
        "| Candidates | Invalid Candidate Probability | Kernel Probability | Benchmark Ref | Delta |",
        "| ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {state_prep.get('candidate_count')} | "
            f"{state_prep.get('invalid_candidate_probability'):.9f} | "
            f"{quantization.get('power_zero_circuit_success_probability'):.9f} | "
            f"{quantization.get('benchmark_reference_value'):.9f} | "
            f"{quantization.get('kernel_reference_delta'):+.9f} |"
        ),
        "",
        "Claims: the power-zero observation circuit is emitted as Moonlab text; Grover diffusion, the full MLAE schedule, hardware execution, hardware advantage, whole-game hardware execution, and dense 70,000-qubit state claims remain false.",
        "",
    ]
    return "\n".join(lines)


def build_icc_evidence(
    observation: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    resource = dict_or_empty(observation.get("resource_estimate"))
    control = dict_or_empty(observation.get("moonlab_control_plane"))
    posture = dict_or_empty(observation.get("claim_posture"))
    state_prep = dict_or_empty(observation.get("state_preparation"))
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_moonlab_qae_observation_transpile",
        "completion_reason": "qge_moonlab_qae_power_zero_observation_recorded",
        "moonlab_qae_observation_file": str(out_path) if out_path else None,
        "moonlab_qae_observation_schema": observation.get("schema"),
        "moonlab_qae_observation_status": observation.get("status"),
        "semantic_scope": observation.get("semantic_scope"),
        "moonlab_circuit_file": observation.get("moonlab_circuit_file"),
        "control_plane_executable": control.get("control_plane_executable"),
        "body_bytes": control.get("body_bytes"),
        "body_limit_bytes": control.get("body_limit_bytes"),
        "logical_qubits": resource.get("logical_qubits"),
        "gate_count": resource.get("gate_count"),
        "candidate_count": state_prep.get("candidate_count"),
        "invalid_candidate_probability": state_prep.get(
            "invalid_candidate_probability"),
        "candidate_state_preparation_transpiled": (
            posture.get("candidate_state_preparation_transpiled")),
        "qf_oracle_kernel_transpiled": (
            posture.get("qf_oracle_kernel_transpiled")),
        "power_zero_observation_transpiled": (
            posture.get("power_zero_observation_transpiled")),
        "grover_operator_transpiled": (
            posture.get("grover_operator_transpiled")),
        "full_mlae_schedule_transpiled": (
            posture.get("full_mlae_schedule_transpiled")),
        "full_qae_oracle_transpiled": (
            posture.get("full_qae_oracle_transpiled")),
        "hardware_result_claimed": False,
        "hardware_quantum_advantage_claimed": False,
        "whole_game_hardware_execution_claimed": False,
        "dense_70000_qubit_state_claimed": False,
        "status": "success",
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--oracle-scene", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--circuit", required=True, type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        metrics = load_json(args.metrics)
        oracle_scene_path = args.oracle_scene
        if oracle_scene_path is None:
            source = metrics.get("source_oracle_scene")
            if not isinstance(source, str) or not source:
                raise ValueError(
                    "--oracle-scene is required when metrics omit source_oracle_scene")
            oracle_scene_path = Path(source)
        oracle_scene = load_json(oracle_scene_path)
        observation = build_observation_circuit(
            metrics,
            oracle_scene,
            metrics_path=args.metrics,
            oracle_scene_path=oracle_scene_path,
            circuit_path=args.circuit,
        )
        write_json(args.out, observation)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(observation),
                                     encoding="utf-8")
        if args.icc_json:
            write_json(args.icc_json, build_icc_evidence(
                observation,
                out_path=args.out,
            ))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_moonlab_qae_observation_transpile: {exc}",
              file=sys.stderr)
        return 1
    print(f"QGE_MOONLAB_QAE_OBSERVATION {args.out}")
    print(f"QGE_MOONLAB_QAE_OBSERVATION_CIRCUIT {args.circuit}")
    if args.markdown:
        print(f"QGE_MOONLAB_QAE_OBSERVATION_MARKDOWN {args.markdown}")
    if args.icc_json:
        print(f"QGE_MOONLAB_QAE_OBSERVATION_ICC_EVIDENCE {args.icc_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
