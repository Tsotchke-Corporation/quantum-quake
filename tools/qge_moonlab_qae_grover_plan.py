#!/usr/bin/env python3
"""Plan exact Moonlab control-plane bodies for QGE QAE Grover powers."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_moonlab_oracle_transpile as qf_transpile  # noqa: E402
import qge_moonlab_qae_observation_transpile as observation_transpile  # noqa: E402
import qge_moonlab_qae_transpile as qae_transpile  # noqa: E402


MOONLAB_HEADER = qf_transpile.MOONLAB_HEADER
MOONLAB_CONTROL_MAX_BODY_BYTES = qf_transpile.MOONLAB_CONTROL_MAX_BODY_BYTES
STATUS_READY = "qae_grover_schedule_ready_for_control_plane_submission"
STATUS_BLOCKED = "qae_grover_schedule_blocked_control_plane_body_limit"
STATUS_POWER_ZERO_BLOCKED = "blocked_power_zero_observation"


@dataclass(frozen=True)
class CircuitBlock:
    name: str
    lines: list[str]

    @property
    def gate_count(self) -> int:
        return len(self.lines)

    @property
    def payload_bytes(self) -> int:
        return sum(len(line.encode("utf-8")) + 1 for line in self.lines)


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


def circuit_prefix(num_qubits: int) -> str:
    return f"{MOONLAB_HEADER}\nNUM_QUBITS {num_qubits}\n"


def circuit_body_bytes(num_qubits: int, blocks: Sequence[CircuitBlock]) -> int:
    return len(circuit_prefix(num_qubits).encode("utf-8")) + sum(
        block.payload_bytes for block in blocks)


def circuit_gate_count(blocks: Sequence[CircuitBlock]) -> int:
    return sum(block.gate_count for block in blocks)


def circuit_sha256(num_qubits: int, blocks: Sequence[CircuitBlock]) -> str:
    digest = hashlib.sha256()
    digest.update(circuit_prefix(num_qubits).encode("utf-8"))
    for block in blocks:
        for line in block.lines:
            digest.update(line.encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def parse_power_list(value: str) -> list[int]:
    powers = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        power = int(item)
        if power < 0:
            raise argparse.ArgumentTypeError("Grover powers must be >= 0")
        powers.append(power)
    if not powers:
        raise argparse.ArgumentTypeError("power list is empty")
    return powers


def selected_observations(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    estimator = qae_transpile.selected_estimator(metrics)
    observations = [
        item for item in list_or_empty(estimator.get("observations"))
        if isinstance(item, dict)
    ]
    if not observations:
        raise ValueError("selected estimator contains no observations")
    return observations


def selected_estimator_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    estimator = qae_transpile.selected_estimator(metrics)
    return {
        "algorithm": estimator.get("algorithm"),
        "oracle_eval_count": estimator.get("oracle_eval_count"),
        "shots": estimator.get("shots"),
        "shots_per_power": estimator.get("shots_per_power"),
        "grover_powers": estimator.get("grover_powers"),
        "seed": estimator.get("seed"),
    }


def emit_a_block(
    metrics: dict[str, Any],
    oracle_scene: dict[str, Any],
) -> tuple[CircuitBlock, dict[str, Any], dict[str, Any], dict[str, Any]]:
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
            f"Grover schedule requires {layout['num_qubits']} qubits; "
            "Moonlab text control plane accepts at most 32 for this path")

    circuit = qf_transpile.MoonlabCircuitBuilder(layout["num_qubits"])
    state_prep = observation_transpile.emit_uniform_range_state_preparation(
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
    block = CircuitBlock("A", circuit.lines[2:])
    resources = {
        "logical_qubits": layout["num_qubits"],
        "candidate_state_preparation_gates": state_prep_gate_count,
        "threshold_preparation_gates": threshold_prep_gate_count,
        "qf_kernel_gates": qf_gate_count,
        "candidate_entries": int(quantization["candidate_count"]),
        "gate_set": ["H", "X", "RY", "RZ", "CNOT"],
    }
    return block, layout, state_prep, {**quantization, **resources}


def negate_angle_text(value: str) -> str:
    if value.startswith("-"):
        return value[1:]
    if value.startswith("+"):
        return "-" + value[1:]
    return "-" + value


def invert_gate_line(line: str) -> str:
    parts = line.split()
    if not parts:
        raise ValueError("empty gate line cannot be inverted")
    gate = parts[0]
    if gate in ("H", "X"):
        if len(parts) != 2:
            raise ValueError(f"invalid {gate} line: {line}")
        return line
    if gate == "CNOT":
        if len(parts) != 3:
            raise ValueError(f"invalid CNOT line: {line}")
        return line
    if gate in ("RY", "RZ"):
        if len(parts) != 3:
            raise ValueError(f"invalid {gate} line: {line}")
        return f"{gate} {parts[1]} {negate_angle_text(parts[2])}"
    raise ValueError(f"unsupported Moonlab gate for inversion: {gate}")


def inverse_block(block: CircuitBlock) -> CircuitBlock:
    return CircuitBlock(
        f"{block.name}_dagger",
        [invert_gate_line(line) for line in reversed(block.lines)],
    )


def s_chi_block(layout: dict[str, Any]) -> CircuitBlock:
    return CircuitBlock("S_chi", [f"RZ {layout['good']} {math.pi:.17g}"])


def s0_block(layout: dict[str, Any]) -> CircuitBlock:
    """Reflect the active QAE registers after A_dagger has cleaned scratch."""

    circuit = qf_transpile.MoonlabCircuitBuilder(layout["num_qubits"])
    active = list(layout["candidate"]) + list(layout["threshold"]) + [
        int(layout["good"])
    ]
    controls = list(layout["candidate"]) + list(layout["threshold"])
    target = int(layout["good"])
    ancilla = list(layout["value"]) + [int(layout["flag"])] + list(
        layout["mcx_ancilla"])
    for qubit in active:
        circuit.x(int(qubit))
    circuit.h(target)
    qf_transpile.emit_mcx(circuit, [int(qubit) for qubit in controls],
                          target, [int(qubit) for qubit in ancilla])
    circuit.h(target)
    for qubit in reversed(active):
        circuit.x(int(qubit))
    return CircuitBlock("S_0_active_register", circuit.lines[2:])


def observation_blocks(
    power: int,
    a_block: CircuitBlock,
    a_dagger_block: CircuitBlock,
    chi_block: CircuitBlock,
    zero_block: CircuitBlock,
) -> list[CircuitBlock]:
    blocks = [a_block]
    for _ in range(power):
        blocks.extend([chi_block, a_dagger_block, zero_block, a_block])
    return blocks


def observation_metadata_by_power(
    observations: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    by_power = {}
    for index, observation in enumerate(observations):
        power = int(observation.get("grover_power") or 0)
        by_power[power] = {
            "observation_index": index,
            "grover_power": power,
            "grover_factor": observation.get("grover_factor"),
            "shots": observation.get("shots"),
            "simulator_success_probability": observation.get(
                "success_probability"),
            "simulator_successes": observation.get("successes"),
        }
    return by_power


def build_schedule_plan(
    metrics: dict[str, Any],
    oracle_scene: dict[str, Any],
    *,
    metrics_path: Path | None = None,
    oracle_scene_path: Path | None = None,
    powers: list[int] | None = None,
) -> dict[str, Any]:
    observations = selected_observations(metrics)
    observation_by_power = observation_metadata_by_power(observations)
    scheduled_powers = (
        powers if powers is not None else
        [int(item.get("grover_power") or 0) for item in observations]
    )
    if not scheduled_powers:
        raise ValueError("Grover schedule contains no powers")

    a_block, layout, state_prep, quantization = emit_a_block(
        metrics, oracle_scene)
    a_dagger_block = inverse_block(a_block)
    chi_block = s_chi_block(layout)
    zero_block = s0_block(layout)
    block_resources = {
        "a": {
            "gate_count": a_block.gate_count,
            "payload_bytes": a_block.payload_bytes,
        },
        "a_dagger": {
            "gate_count": a_dagger_block.gate_count,
            "payload_bytes": a_dagger_block.payload_bytes,
        },
        "s_chi": {
            "gate_count": chi_block.gate_count,
            "payload_bytes": chi_block.payload_bytes,
        },
        "s0_active_register": {
            "gate_count": zero_block.gate_count,
            "payload_bytes": zero_block.payload_bytes,
            "active_register_qubits": (
                len(layout["candidate"]) + len(layout["threshold"]) + 1),
        },
    }

    schedule = []
    ready_count = 0
    blocked_count = 0
    first_blocked_power = None
    for index, power in enumerate(scheduled_powers):
        if power < 0:
            raise ValueError("Grover powers must be >= 0")
        blocks = observation_blocks(
            power, a_block, a_dagger_block, chi_block, zero_block)
        body_bytes = circuit_body_bytes(layout["num_qubits"], blocks)
        gate_count = circuit_gate_count(blocks)
        control_ready = body_bytes <= MOONLAB_CONTROL_MAX_BODY_BYTES
        if control_ready:
            ready_count += 1
        else:
            blocked_count += 1
            if first_blocked_power is None:
                first_blocked_power = power
        metadata = observation_by_power.get(power, {
            "observation_index": index,
            "grover_power": power,
            "grover_factor": 2 * power + 1,
            "shots": None,
            "simulator_success_probability": None,
            "simulator_successes": None,
        })
        schedule.append({
            **metadata,
            "schedule_block_sequence": (
                ["A"] +
                ["S_chi", "A_dagger", "S_0_active_register", "A"] * power
            ),
            "logical_qubits": layout["num_qubits"],
            "gate_count": gate_count,
            "body_bytes": body_bytes,
            "body_limit_bytes": MOONLAB_CONTROL_MAX_BODY_BYTES,
            "moonlab_circuit_sha256": circuit_sha256(
                layout["num_qubits"], blocks),
            "control_plane_executable": control_ready,
            "status": (
                "ready_for_control_plane_submission"
                if control_ready else "blocked_control_plane_body_limit"
            ),
        })

    power_zero = next(
        (item for item in schedule if int(item["grover_power"]) == 0), None)
    if power_zero is not None and not power_zero["control_plane_executable"]:
        status = STATUS_POWER_ZERO_BLOCKED
    elif blocked_count:
        status = STATUS_BLOCKED
    else:
        status = STATUS_READY

    return {
        "schema": "qge.moonlab_qae_grover_schedule_plan.v0",
        "status": status,
        "semantic_scope": (
            "bernoulli_lift_qae_grover_schedule_control_plane_plan"),
        "source_metrics": str(metrics_path) if metrics_path is not None else None,
        "source_metrics_sha256": sha256_file(metrics_path),
        "source_oracle_scene": (
            str(oracle_scene_path) if oracle_scene_path is not None else None),
        "source_oracle_scene_sha256": sha256_file(oracle_scene_path),
        "advantage_problem_id": metrics.get("advantage_problem_id"),
        "observable": metrics.get("observable"),
        "selected_estimator": selected_estimator_summary(metrics),
        "qubit_layout": layout,
        "state_preparation": state_prep,
        "quantization": quantization,
        "moonlab_control_plane": {
            "payload_header": MOONLAB_HEADER,
            "verb": "SHOTS",
            "body_limit_bytes": MOONLAB_CONTROL_MAX_BODY_BYTES,
            "ready_observation_count": ready_count,
            "blocked_observation_count": blocked_count,
            "first_blocked_power": first_blocked_power,
        },
        "block_resources": block_resources,
        "observations": schedule,
        "resource_estimate": {
            "logical_qubits": layout["num_qubits"],
            "observation_count": len(schedule),
            "ready_observation_count": ready_count,
            "blocked_observation_count": blocked_count,
            "first_blocked_power": first_blocked_power,
            "power_zero_body_bytes": (
                power_zero.get("body_bytes") if power_zero else None),
            "max_body_bytes": max(item["body_bytes"] for item in schedule),
            "max_gate_count": max(item["gate_count"] for item in schedule),
            "candidate_entries": quantization.get("candidate_entries"),
            "gate_set": ["H", "X", "RY", "RZ", "CNOT"],
        },
        "claim_posture": {
            "candidate_state_preparation_transpiled": bool(
                power_zero and power_zero["control_plane_executable"]),
            "qf_oracle_kernel_transpiled": bool(
                power_zero and power_zero["control_plane_executable"]),
            "power_zero_observation_transpiled": bool(
                power_zero and power_zero["control_plane_executable"]),
            "nonzero_grover_powers_transpiled": blocked_count == 0,
            "grover_operator_transpiled": blocked_count == 0,
            "full_mlae_schedule_transpiled": blocked_count == 0,
            "full_qae_oracle_transpiled": blocked_count == 0,
            "hardware_result_claimed": False,
            "hardware_quantum_advantage_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "dense_70000_qubit_state_claimed": False,
        },
        "limits": [
            "This is an exact Moonlab text body-size plan for the selected MLAE Grover powers.",
            "Oversized nonzero-power observations are not written as circuit files.",
            "S_0 is emitted as an active-register reflection after A_dagger returns scratch registers to zero.",
            "Hardware execution, hardware advantage, whole-game hardware execution, and dense 70,000-qubit state claims remain false.",
        ],
    }


def markdown_report(plan: dict[str, Any]) -> str:
    control = dict_or_empty(plan.get("moonlab_control_plane"))
    resource = dict_or_empty(plan.get("resource_estimate"))
    posture = dict_or_empty(plan.get("claim_posture"))
    lines = [
        "# QGE Moonlab QAE Grover Schedule Plan",
        "",
        f"Status: `{plan['status']}`",
        f"Semantic scope: `{plan['semantic_scope']}`",
        "",
        "| Observations | Ready | Blocked | First Blocked Power | Body Limit | Full MLAE |",
        "| ---: | ---: | ---: | ---: | ---: | --- |",
        (
            f"| {resource.get('observation_count')} | "
            f"{control.get('ready_observation_count')} | "
            f"{control.get('blocked_observation_count')} | "
            f"{control.get('first_blocked_power')} | "
            f"{control.get('body_limit_bytes')} | "
            f"{posture.get('full_mlae_schedule_transpiled')} |"
        ),
        "",
        "| Power | Factor | Gates | Body Bytes | Limit | Status |",
        "| ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in list_or_empty(plan.get("observations")):
        lines.append(
            f"| {item.get('grover_power')} | "
            f"{item.get('grover_factor')} | "
            f"{item.get('gate_count')} | "
            f"{item.get('body_bytes')} | "
            f"{item.get('body_limit_bytes')} | "
            f"{item.get('status')} |"
        )
    lines.extend([
        "",
        "Claims: this records exact Moonlab body-size readiness for the selected Grover powers; blocked oversized observations are not hardware results or hardware advantage evidence.",
        "",
    ])
    return "\n".join(lines)


def build_icc_evidence(
    plan: dict[str, Any],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    resource = dict_or_empty(plan.get("resource_estimate"))
    control = dict_or_empty(plan.get("moonlab_control_plane"))
    posture = dict_or_empty(plan.get("claim_posture"))
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_moonlab_qae_grover_plan",
        "completion_reason": "qge_moonlab_qae_grover_schedule_plan_recorded",
        "moonlab_qae_grover_schedule_plan_file": (
            str(out_path) if out_path else None),
        "moonlab_qae_grover_schedule_plan_schema": plan.get("schema"),
        "moonlab_qae_grover_schedule_plan_status": plan.get("status"),
        "semantic_scope": plan.get("semantic_scope"),
        "observation_count": resource.get("observation_count"),
        "ready_observation_count": control.get("ready_observation_count"),
        "blocked_observation_count": control.get("blocked_observation_count"),
        "power_zero_body_bytes": resource.get("power_zero_body_bytes"),
        "first_blocked_power": control.get("first_blocked_power"),
        "body_limit_bytes": control.get("body_limit_bytes"),
        "logical_qubits": resource.get("logical_qubits"),
        "max_gate_count": resource.get("max_gate_count"),
        "max_body_bytes": resource.get("max_body_bytes"),
        "candidate_state_preparation_transpiled": (
            posture.get("candidate_state_preparation_transpiled")),
        "qf_oracle_kernel_transpiled": (
            posture.get("qf_oracle_kernel_transpiled")),
        "power_zero_observation_transpiled": (
            posture.get("power_zero_observation_transpiled")),
        "nonzero_grover_powers_transpiled": (
            posture.get("nonzero_grover_powers_transpiled")),
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
    parser.add_argument("--powers", type=parse_power_list,
                        help="Optional comma-separated Grover powers")
    parser.add_argument("--out", required=True, type=Path)
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
        plan = build_schedule_plan(
            metrics,
            oracle_scene,
            metrics_path=args.metrics,
            oracle_scene_path=oracle_scene_path,
            powers=args.powers,
        )
        write_json(args.out, plan)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(plan), encoding="utf-8")
        if args.icc_json:
            write_json(args.icc_json, build_icc_evidence(
                plan,
                out_path=args.out,
            ))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_moonlab_qae_grover_plan: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_MOONLAB_QAE_GROVER_PLAN {args.out}")
    if args.markdown:
        print(f"QGE_MOONLAB_QAE_GROVER_PLAN_MARKDOWN {args.markdown}")
    if args.icc_json:
        print(f"QGE_MOONLAB_QAE_GROVER_PLAN_ICC_EVIDENCE {args.icc_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
