#!/usr/bin/env python3
"""Transpile a QGE Bernoulli-lift Q_f kernel to moonlab-circuit v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_advantage_benchmark  # noqa: E402


MOONLAB_HEADER = "# moonlab-circuit v1"
MOONLAB_CONTROL_MAX_BODY_BYTES = 1 << 22
QF_STATUS_READY = "qf_oracle_kernel_ready_qae_transpilation_required"


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


def stable_success_count_order(counts: list[int]) -> list[int]:
    return sorted(range(len(counts)), key=lambda index: (counts[index], index))


def sha256_int_list(values: list[int]) -> str:
    payload = ",".join(str(value) for value in values).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def ceil_log2(value: int) -> int:
    if value <= 1:
        return 0
    return (value - 1).bit_length()


class MoonlabCircuitBuilder:
    def __init__(self, num_qubits: int) -> None:
        self.num_qubits = num_qubits
        self.lines = [MOONLAB_HEADER, f"NUM_QUBITS {num_qubits}"]

    def add(self, line: str) -> None:
        self.lines.append(line)

    def h(self, qubit: int) -> None:
        self.add(f"H {qubit}")

    def x(self, qubit: int) -> None:
        self.add(f"X {qubit}")

    def z(self, qubit: int) -> None:
        self.add(f"Z {qubit}")

    def s(self, qubit: int) -> None:
        self.add(f"S {qubit}")

    def t(self, qubit: int) -> None:
        self.add(f"T {qubit}")

    def rz(self, qubit: int, theta: float) -> None:
        self.add(f"RZ {qubit} {theta:.17g}")

    def cnot(self, target: int, control: int) -> None:
        self.add(f"CNOT {target} {control}")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"

    def gate_count(self) -> int:
        return max(len(self.lines) - 2, 0)


def emit_toffoli(circuit: MoonlabCircuitBuilder,
                 control_a: int,
                 control_b: int,
                 target: int) -> None:
    """Emit an exact CCX using Moonlab's supported Clifford+T text gates.

    The sequence is the standard seven-T Toffoli decomposition. `Tdg` is
    represented as `Z S T`, which is equivalent up to the same global phase
    already present when spelling the decomposition with RZ(-pi/4).
    """

    def tdg(qubit: int) -> None:
        circuit.z(qubit)
        circuit.s(qubit)
        circuit.t(qubit)

    circuit.h(target)
    circuit.cnot(target, control_b)
    tdg(target)
    circuit.cnot(target, control_a)
    circuit.t(target)
    circuit.cnot(target, control_b)
    tdg(target)
    circuit.cnot(target, control_a)
    circuit.t(control_b)
    circuit.t(target)
    circuit.h(target)
    circuit.cnot(control_b, control_a)
    circuit.t(control_a)
    tdg(control_b)
    circuit.cnot(control_b, control_a)


def emit_mcx(circuit: MoonlabCircuitBuilder,
             controls: list[int],
             target: int,
             ancilla: list[int]) -> None:
    if not controls:
        circuit.x(target)
        return
    if len(controls) == 1:
        circuit.cnot(target, controls[0])
        return
    if len(controls) == 2:
        emit_toffoli(circuit, controls[0], controls[1], target)
        return
    required = len(controls) - 2
    if len(ancilla) < required:
        raise ValueError(
            f"MCX with {len(controls)} controls requires {required} ancilla")

    emit_toffoli(circuit, controls[0], controls[1], ancilla[0])
    for index in range(2, len(controls) - 1):
        emit_toffoli(
            circuit,
            ancilla[index - 2],
            controls[index],
            ancilla[index - 1],
        )
    emit_toffoli(circuit, ancilla[len(controls) - 3],
                 controls[-1], target)
    for index in range(len(controls) - 2, 1, -1):
        emit_toffoli(
            circuit,
            ancilla[index - 2],
            controls[index],
            ancilla[index - 1],
        )
    emit_toffoli(circuit, controls[0], controls[1], ancilla[0])


def emit_negative_control_toffoli(circuit: MoonlabCircuitBuilder,
                                  negative_control: int,
                                  positive_control: int,
                                  target: int) -> None:
    circuit.x(negative_control)
    emit_toffoli(circuit, negative_control, positive_control, target)
    circuit.x(negative_control)


def emit_borrow_xor(circuit: MoonlabCircuitBuilder,
                    threshold_bit: int,
                    value_bit: int,
                    borrow_in: int | None,
                    target: int) -> None:
    emit_negative_control_toffoli(circuit, threshold_bit, value_bit, target)
    if borrow_in is not None:
        emit_negative_control_toffoli(
            circuit, threshold_bit, borrow_in, target)
        emit_toffoli(circuit, value_bit, borrow_in, target)


def emit_less_than_comparator(circuit: MoonlabCircuitBuilder,
                              threshold_qubits: list[int],
                              value_qubits: list[int],
                              good_qubit: int,
                              scratch: list[int]) -> None:
    """Toggle good_qubit when threshold < value, preserving inputs."""

    if len(threshold_qubits) != len(value_qubits):
        raise ValueError("threshold/value register widths differ")
    bits = len(threshold_qubits)
    if len(scratch) < max(bits - 1, 0):
        raise ValueError(f"comparator requires {bits - 1} scratch qubits")
    borrow_targets = scratch[:max(bits - 1, 0)] + [good_qubit]

    for index in range(bits):
        borrow_in = None if index == 0 else borrow_targets[index - 1]
        emit_borrow_xor(
            circuit,
            threshold_qubits[index],
            value_qubits[index],
            borrow_in,
            borrow_targets[index],
        )
    for index in range(bits - 2, -1, -1):
        borrow_in = None if index == 0 else borrow_targets[index - 1]
        emit_borrow_xor(
            circuit,
            threshold_qubits[index],
            value_qubits[index],
            borrow_in,
            borrow_targets[index],
        )


def emit_qrom_value_load(circuit: MoonlabCircuitBuilder,
                         candidate_qubits: list[int],
                         value_qubits: list[int],
                         flag_qubit: int,
                         mcx_ancilla: list[int],
                         success_counts: list[int]) -> None:
    cover = qrom_value_load_cover(success_counts, len(candidate_qubits))
    for bit_index, bit_cubes in enumerate(cover):
        target = value_qubits[bit_index]
        for cube in bit_cubes:
            specified = int(cube["specified_mask"])
            value = int(cube["specified_value"])
            controls = []
            zero_controls = []
            for offset, qubit in enumerate(candidate_qubits):
                if ((specified >> offset) & 1) == 0:
                    continue
                controls.append(qubit)
                if ((value >> offset) & 1) == 0:
                    zero_controls.append(qubit)
            for qubit in zero_controls:
                circuit.x(qubit)
            emit_mcx(circuit, controls, target, mcx_ancilla)
            for qubit in reversed(zero_controls):
                circuit.x(qubit)


def qrom_value_load_cover(success_counts: list[int],
                          candidate_bits: int) -> list[list[dict[str, int]]]:
    if candidate_bits <= 0:
        raise ValueError("candidate_bits must be > 0")
    capacity = 1 << candidate_bits
    if not success_counts or len(success_counts) > capacity:
        raise ValueError("success_counts length is outside candidate register")
    max_count = max(success_counts)
    value_bits = max(max_count.bit_length(), 1)
    return [
        qrom_value_bit_cover(success_counts, candidate_bits, bit)
        for bit in range(value_bits)
    ]


def qrom_value_bit_cover(success_counts: list[int],
                         candidate_bits: int,
                         bit: int) -> list[dict[str, int]]:
    """Build a disjoint exact cover for one QROM value bit.

    Invalid candidate basis states are treated as zero-valued, matching the
    Bernoulli-lift predicate contract. Cubes are therefore accepted only when
    they cover valid one-valued addresses and no valid or invalid zero-valued
    address.
    """

    capacity = 1 << candidate_bits
    ones = {
        address for address, count in enumerate(success_counts)
        if (count >> bit) & 1
    }
    if not ones:
        return []
    if candidate_bits > 10:
        full_mask = capacity - 1
        return [
            {
                "covered_count": 1,
                "control_count": candidate_bits,
                "specified_mask": full_mask,
                "specified_value": int(address),
            }
            for address in sorted(ones)
        ]
    zeros = set(range(capacity)) - ones
    candidates = []
    for specified_mask in range(capacity):
        for specified_value in range(capacity):
            if specified_value & ~specified_mask:
                continue
            covered = {
                address for address in ones
                if (address & specified_mask) == specified_value
            }
            if not covered:
                continue
            if any((address & specified_mask) == specified_value
                   for address in zeros):
                continue
            candidates.append({
                "covered": covered,
                "covered_count": len(covered),
                "control_count": specified_mask.bit_count(),
                "specified_mask": specified_mask,
                "specified_value": specified_value,
            })

    covered: set[int] = set()
    selected = []
    while covered != ones:
        remaining = ones - covered
        usable = [
            cube for cube in candidates
            if cube["covered"] <= remaining and
            not (cube["covered"] & covered)
        ]
        if usable:
            cube = max(
                usable,
                key=lambda item: (
                    item["covered_count"],
                    -item["control_count"],
                    -item["specified_mask"],
                    -item["specified_value"],
                ),
            )
        else:
            address = min(remaining)
            cube = {
                "covered": {address},
                "covered_count": 1,
                "control_count": candidate_bits,
                "specified_mask": capacity - 1,
                "specified_value": address,
            }
        selected.append({
            "covered_count": int(cube["covered_count"]),
            "control_count": int(cube["control_count"]),
            "specified_mask": int(cube["specified_mask"]),
            "specified_value": int(cube["specified_value"]),
        })
        covered.update(cube["covered"])
    return selected


def contribution_success_counts(oracle_scene: dict[str, Any],
                                metrics: dict[str, Any]) -> tuple[list[int], dict[str, Any]]:
    observable = dict_or_empty(metrics.get("observable"))
    contribution_bits = int(observable.get("contribution_bits") or 0)
    if contribution_bits <= 0:
        raise ValueError("metrics observable.contribution_bits must be > 0")
    trials = [
        trial for trial in list_or_empty(metrics.get("trials"))
        if isinstance(trial, dict)
    ]
    seed = int(trials[0].get("trial_seed") if trials else 1337)
    contributions = qge_advantage_benchmark.build_contributions(
        oracle_scene,
        seed,
        contribution_bits,
    )
    denominator = 1 << contribution_bits
    max_count = denominator - 1
    source_counts = [
        int(round(value * denominator)) for value in contributions
    ]
    if any(count < 0 or count > max_count for count in source_counts):
        raise ValueError(
            "contribution success count overflow requires an extra value bit")
    permutation = stable_success_count_order(source_counts)
    counts = [source_counts[index] for index in permutation]
    amplitude = sum(counts) / float(len(counts) * denominator)
    reference = float(dict_or_empty(metrics.get("reference")).get("value") or 0.0)
    return counts, {
        "trial_seed": seed,
        "candidate_count": len(counts),
        "contribution_bits": contribution_bits,
        "bernoulli_denominator": denominator,
        "success_count_ordering": "success_count_ascending_stable",
        "success_count_ordering_semantics": (
            "candidate addresses are a bijective uniform-sample permutation; "
            "sorting preserves Bernoulli probability while reducing exact QROM "
            "cover size"),
        "candidate_address_permutation": permutation,
        "candidate_address_permutation_sha256": sha256_int_list(permutation),
        "success_count_min": min(counts) if counts else None,
        "success_count_max": max(counts) if counts else None,
        "success_count_sum": sum(counts),
        "kernel_amplitude": amplitude,
        "benchmark_reference_value": reference,
        "kernel_reference_delta": amplitude - reference,
    }


def build_qubit_layout(candidate_bits: int,
                       threshold_bits: int) -> dict[str, Any]:
    candidate = list(range(candidate_bits))
    threshold_start = candidate_bits
    threshold = list(range(threshold_start, threshold_start + threshold_bits))
    value_start = threshold_start + threshold_bits
    value = list(range(value_start, value_start + threshold_bits))
    good = value_start + threshold_bits
    flag = good + 1
    mcx_ancilla_count = max(candidate_bits - 2, threshold_bits - 2, 0)
    ancilla = list(range(flag + 1, flag + 1 + mcx_ancilla_count))
    comparator_scratch = [flag] + ancilla
    num_qubits = flag + 1 + mcx_ancilla_count
    return {
        "num_qubits": num_qubits,
        "candidate": candidate,
        "threshold": threshold,
        "value": value,
        "good": good,
        "flag": flag,
        "mcx_ancilla": ancilla,
        "comparator_scratch": comparator_scratch,
    }


def build_kernel(metrics: dict[str, Any],
                 oracle_scene: dict[str, Any],
                 *,
                 metrics_path: Path | None = None,
                 oracle_scene_path: Path | None = None,
                 circuit_path: Path | None = None) -> dict[str, Any]:
    resource = dict_or_empty(metrics.get("resource_estimate"))
    candidate_bits = int(resource.get("candidate_index_bits") or 0)
    threshold_bits = int(resource.get("contribution_threshold_bits") or 0)
    if candidate_bits <= 0 or threshold_bits <= 0:
        raise ValueError("metrics resource_estimate is missing register widths")
    success_counts, quantization = contribution_success_counts(
        oracle_scene, metrics)
    candidate_count = int(quantization["candidate_count"])
    layout = build_qubit_layout(candidate_bits, threshold_bits)
    if layout["num_qubits"] > 32:
        raise ValueError(
            f"kernel requires {layout['num_qubits']} qubits; Moonlab text "
            "control plane accepts at most 32 for this path")

    circuit = MoonlabCircuitBuilder(layout["num_qubits"])
    emit_qrom_value_load(
        circuit,
        layout["candidate"],
        layout["value"],
        layout["flag"],
        layout["mcx_ancilla"],
        success_counts,
    )
    emit_less_than_comparator(
        circuit,
        layout["threshold"],
        layout["value"],
        layout["good"],
        layout["comparator_scratch"],
    )
    emit_qrom_value_load(
        circuit,
        layout["candidate"],
        layout["value"],
        layout["flag"],
        layout["mcx_ancilla"],
        success_counts,
    )

    circuit_text = circuit.text()
    circuit_bytes = circuit_text.encode("utf-8")
    if circuit_path is not None:
        circuit_path.parent.mkdir(parents=True, exist_ok=True)
        circuit_path.write_text(circuit_text, encoding="utf-8")
    body_bytes = len(circuit_bytes)
    control_plane_ready = body_bytes <= MOONLAB_CONTROL_MAX_BODY_BYTES
    status = QF_STATUS_READY if control_plane_ready else (
        "blocked_control_plane_body_limit")
    return {
        "schema": "qge.moonlab_qae_oracle_kernel.v0",
        "status": status,
        "semantic_scope": "bernoulli_lift_qf_oracle_kernel",
        "source_metrics": str(metrics_path) if metrics_path is not None else None,
        "source_metrics_sha256": sha256_file(metrics_path)
        if metrics_path is not None else None,
        "source_oracle_scene": (
            str(oracle_scene_path) if oracle_scene_path is not None else None),
        "source_oracle_scene_sha256": sha256_file(oracle_scene_path)
        if oracle_scene_path is not None else None,
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
        "predicate": {
            "meaning": "good ^= (candidate < candidate_count and threshold < success_count[candidate])",
            "candidate_count": candidate_count,
            "invalid_candidate_success_count": 0,
            "threshold_register_denominator": quantization[
                "bernoulli_denominator"],
        },
        "quantization": quantization,
        "resource_estimate": {
            "logical_qubits": layout["num_qubits"],
            "gate_count": circuit.gate_count(),
            "body_bytes": body_bytes,
            "candidate_entries": candidate_count,
            "gate_set": ["H", "S", "T", "X", "Z", "CNOT"],
        },
        "claim_posture": {
            "qf_oracle_kernel_transpiled": control_plane_ready,
            "candidate_state_preparation_transpiled": False,
            "grover_operator_transpiled": False,
            "full_qae_oracle_transpiled": False,
            "hardware_result_claimed": False,
            "hardware_quantum_advantage_claimed": False,
            "whole_game_hardware_execution_claimed": False,
            "dense_70000_qubit_state_claimed": False,
        },
        "limits": [
            "This circuit is the reversible Q_f predicate kernel for the current Bernoulli-lift benchmark oracle.",
            "It does not include non-power-of-two candidate state preparation, Grover diffusion, MLAE schedule assembly, or hardware result metadata.",
            "Invalid candidate basis states outside the captured scene range map to success_count=0 and require state-preparation handling before a full QAE claim.",
        ],
    }


def markdown_report(kernel: dict[str, Any]) -> str:
    resource = dict_or_empty(kernel.get("resource_estimate"))
    quantization = dict_or_empty(kernel.get("quantization"))
    control = dict_or_empty(kernel.get("moonlab_control_plane"))
    posture = dict_or_empty(kernel.get("claim_posture"))
    lines = [
        "# QGE Moonlab QAE Oracle Kernel",
        "",
        f"Status: `{kernel['status']}`",
        f"Semantic scope: `{kernel['semantic_scope']}`",
        "",
        "| Qubits | Gates | Body Bytes | Body Limit | Q_f Kernel | Full QAE |",
        "| ---: | ---: | ---: | ---: | --- | --- |",
        (
            f"| {resource.get('logical_qubits')} | "
            f"{resource.get('gate_count')} | "
            f"{control.get('body_bytes')} | "
            f"{control.get('body_limit_bytes')} | "
            f"{posture.get('qf_oracle_kernel_transpiled')} | "
            f"{posture.get('full_qae_oracle_transpiled')} |"
        ),
        "",
        "| Candidates | Success Sum | Kernel Amplitude | Benchmark Ref | Delta |",
        "| ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {quantization.get('candidate_count')} | "
            f"{quantization.get('success_count_sum')} | "
            f"{quantization.get('kernel_amplitude'):.9f} | "
            f"{quantization.get('benchmark_reference_value'):.9f} | "
            f"{quantization.get('kernel_reference_delta'):+.9f} |"
        ),
        "",
        "Claims: the reversible `Q_f` kernel is emitted as Moonlab text; state preparation, Grover/QAE assembly, hardware execution, hardware advantage, whole-game hardware execution, and dense 70,000-qubit state claims remain false.",
        "",
    ]
    return "\n".join(lines)


def build_icc_evidence(kernel: dict[str, Any],
                       *,
                       out_path: Path | None = None) -> dict[str, Any]:
    resource = dict_or_empty(kernel.get("resource_estimate"))
    posture = dict_or_empty(kernel.get("claim_posture"))
    control = dict_or_empty(kernel.get("moonlab_control_plane"))
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_moonlab_oracle_transpile",
        "completion_reason": "qge_moonlab_qf_oracle_kernel_recorded",
        "moonlab_qae_oracle_kernel_file": str(out_path) if out_path else None,
        "moonlab_qae_oracle_kernel_schema": kernel.get("schema"),
        "moonlab_qae_oracle_kernel_status": kernel.get("status"),
        "semantic_scope": kernel.get("semantic_scope"),
        "moonlab_circuit_file": kernel.get("moonlab_circuit_file"),
        "control_plane_executable": control.get("control_plane_executable"),
        "body_bytes": control.get("body_bytes"),
        "body_limit_bytes": control.get("body_limit_bytes"),
        "logical_qubits": resource.get("logical_qubits"),
        "gate_count": resource.get("gate_count"),
        "qf_oracle_kernel_transpiled": (
            posture.get("qf_oracle_kernel_transpiled")),
        "candidate_state_preparation_transpiled": (
            posture.get("candidate_state_preparation_transpiled")),
        "grover_operator_transpiled": (
            posture.get("grover_operator_transpiled")),
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
        kernel = build_kernel(
            metrics,
            oracle_scene,
            metrics_path=args.metrics,
            oracle_scene_path=oracle_scene_path,
            circuit_path=args.circuit,
        )
        write_json(args.out, kernel)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(kernel),
                                     encoding="utf-8")
        if args.icc_json:
            write_json(args.icc_json, build_icc_evidence(
                kernel,
                out_path=args.out,
            ))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_moonlab_oracle_transpile: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_MOONLAB_QAE_ORACLE_KERNEL {args.out}")
    print(f"QGE_MOONLAB_QAE_ORACLE_CIRCUIT {args.circuit}")
    if args.markdown:
        print(f"QGE_MOONLAB_QAE_ORACLE_KERNEL_MARKDOWN {args.markdown}")
    if args.icc_json:
        print(f"QGE_MOONLAB_QAE_ORACLE_KERNEL_ICC_EVIDENCE {args.icc_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
