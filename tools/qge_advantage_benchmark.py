#!/usr/bin/env python3
"""Run a QGE light-transport mean-estimation benchmark.

This is a lab-mode benchmark over a deterministic scene-oracle sidecar. It does
not claim hardware speedup or full-frame quantum rendering; it creates the
artifact contract needed to compare classical sampling with an amplitude-
estimation query model under explicit input/readout assumptions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from pathlib import Path
from typing import Any


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


def stable_u64(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8],
                          "little")


def stable_unit(seed: str, index: int) -> float:
    raw = stable_u64(f"{seed}:{index}")
    return raw / float(1 << 64)


def clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def ceil_log2(value: int) -> int:
    if value <= 1:
        return 0
    return (value - 1).bit_length()


def scene_seed_material(oracle_scene: dict[str, Any], seed: int) -> str:
    scene = oracle_scene.get("scene", {})
    source = oracle_scene.get("source_capture", {})
    observable = oracle_scene.get("observable", {})
    parts = [
        str(seed),
        str(scene.get("scene_id")),
        str(scene.get("trace_run_id")),
        str(source.get("trace_sha256")),
        str(source.get("frame_sha256")),
        str(observable.get("observable_id")),
    ]
    return "|".join(parts)


def render_stat(oracle_scene: dict[str, Any], name: str, default: float = 0.0) -> float:
    render = oracle_scene.get("snapshot", {}).get("render", {})
    value = render.get(name, default)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and "/" in value:
        try:
            return float(value.split("/", 1)[0])
        except ValueError:
            return default
    return default


def build_contributions(oracle_scene: dict[str, Any],
                        seed: int,
                        contribution_bits: int) -> list[float]:
    sample_space = oracle_scene.get("sample_space", {})
    candidate_count = int(sample_space.get("candidate_count") or 0)
    if candidate_count <= 0:
        raise ValueError("oracle_scene sample_space.candidate_count must be > 0")

    seed_material = scene_seed_material(oracle_scene, seed)
    coeffs = max(render_stat(oracle_scene, "coeffs", 1.0), 1.0)
    edgefills = render_stat(oracle_scene, "edgefills", 0.0)
    material = render_stat(oracle_scene, "material", 0.0)
    edge_phase = (edgefills % 997.0) / 997.0
    material_phase = (material % 389.0) / 389.0
    coeff_bias = clamp01(math.log2(coeffs + 1.0) / 24.0)

    levels = (1 << contribution_bits) - 1
    values: list[float] = []
    for i in range(candidate_count):
        x = (i + 0.5) / candidate_count
        hashed = stable_unit(seed_material, i)
        low_band = 0.5 + 0.5 * math.sin(2.0 * math.pi * (3.0 * x + edge_phase))
        material_band = 0.5 + 0.5 * math.cos(2.0 * math.pi * (7.0 * x + material_phase))
        visibility = (
            0.12 +
            0.48 * hashed +
            0.24 * low_band +
            0.12 * material_band +
            0.04 * coeff_bias
        )
        quantized = round(clamp01(visibility) * levels) / levels
        values.append(quantized)
    return values


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def rmse(errors: list[float]) -> float:
    return math.sqrt(sum(error * error for error in errors) / len(errors)) if errors else 0.0


def mc_estimate(values: list[float], samples: int, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    n = len(values)
    total = 0.0
    for _ in range(samples):
        total += values[rng.randrange(n)]
    estimate = total / samples if samples else 0.0
    return {
        "algorithm": "classical_mc",
        "estimate": estimate,
        "oracle_eval_count": samples,
        "samples": samples,
        "seed": seed,
    }


def van_der_corput(index: int, base: int = 2) -> float:
    denom = 1.0
    result = 0.0
    while index:
        index, remainder = divmod(index, base)
        denom *= base
        result += remainder / denom
    return result


def stratified_vdc_estimate(values: list[float], samples: int) -> dict[str, Any]:
    n = len(values)
    total = 0.0
    for j in range(samples):
        u = (j + van_der_corput(j + 1)) / samples
        index = min(int(u * n), n - 1)
        total += values[index]
    estimate = total / samples if samples else 0.0
    return {
        "algorithm": "stratified_vdc",
        "estimate": estimate,
        "oracle_eval_count": samples,
        "samples": samples,
        "seed": None,
    }


def binomial(rng: random.Random, shots: int, probability: float) -> int:
    hits = 0
    for _ in range(shots):
        if rng.random() < probability:
            hits += 1
    return hits


def qae_observations(amplitude: float,
                     powers: list[int],
                     shots_per_power: int,
                     seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    theta = math.asin(math.sqrt(clamp01(amplitude)))
    observations = []
    for power in powers:
        grover_factor = 2 * power + 1
        probability = math.sin(grover_factor * theta) ** 2
        successes = binomial(rng, shots_per_power, probability)
        observations.append({
            "grover_power": power,
            "grover_factor": grover_factor,
            "shots": shots_per_power,
            "successes": successes,
            "success_probability": probability,
        })
    return observations


def mle_amplitude(observations: list[dict[str, Any]], grid_steps: int) -> float:
    best_a = 0.0
    best_ll = -float("inf")
    eps = 1.0e-12
    for step in range(grid_steps + 1):
        amplitude = step / grid_steps
        theta = math.asin(math.sqrt(clamp01(amplitude)))
        ll = 0.0
        for obs in observations:
            shots = int(obs["shots"])
            successes = int(obs["successes"])
            p = math.sin(int(obs["grover_factor"]) * theta) ** 2
            p = min(max(p, eps), 1.0 - eps)
            ll += successes * math.log(p) + (shots - successes) * math.log(1.0 - p)
        if ll > best_ll:
            best_ll = ll
            best_a = amplitude
    return best_a


def qae_schedule(level: int) -> list[int]:
    powers = [0]
    power = 1
    while len(powers) < level:
        powers.append(power)
        power *= 2
    return powers


def qae_estimate(amplitude: float,
                 level: int,
                 shots_per_power: int,
                 seed: int,
                 grid_steps: int) -> dict[str, Any]:
    powers = qae_schedule(level)
    observations = qae_observations(amplitude, powers, shots_per_power, seed)
    estimate = mle_amplitude(observations, grid_steps)
    oracle_calls = sum(int(obs["shots"]) * int(obs["grover_factor"])
                       for obs in observations)
    return {
        "algorithm": "mlae_simulator",
        "estimate": estimate,
        "grid_steps": grid_steps,
        "grover_powers": powers,
        "observations": observations,
        "oracle_eval_count": oracle_calls,
        "controlled_oracle_calls": oracle_calls,
        "shots": shots_per_power * len(powers),
        "shots_per_power": shots_per_power,
        "seed": seed,
    }


def resource_estimate(candidate_bits: int,
                      contribution_bits: int,
                      qae_results: list[dict[str, Any]]) -> dict[str, Any]:
    threshold_bits = contribution_bits
    logical_qubits = candidate_bits + threshold_bits + 3
    max_factor = max(
        (max(result["observations"], key=lambda obs: obs["grover_factor"])["grover_factor"]
         for result in qae_results),
        default=1,
    )
    controlled_calls = max((result["controlled_oracle_calls"] for result in qae_results),
                           default=0)
    one_qubit = controlled_calls * (candidate_bits + threshold_bits + 4)
    two_qubit = controlled_calls * max(candidate_bits + threshold_bits, 1)
    oracle_depth = 4 * max(candidate_bits + threshold_bits, 1) + 8
    circuit_depth = max_factor * (2 * oracle_depth + 6)
    return {
        "model": "abstract_bernoulli_lift_resource_model_v0",
        "logical_qubits": logical_qubits,
        "candidate_index_bits": candidate_bits,
        "contribution_threshold_bits": threshold_bits,
        "ancilla_qubits": 3,
        "one_qubit_gates": one_qubit,
        "two_qubit_gates": two_qubit,
        "controlled_oracle_calls": controlled_calls,
        "circuit_depth": circuit_depth,
        "gate_set": [
            "H",
            "X",
            "CNOT",
            "RY",
            "MCX",
            "Q_f",
            "S_chi",
            "S_0",
            "A",
            "A_dagger",
            "MEASURE",
        ],
    }


def fit_slope(points: list[dict[str, Any]]) -> float | None:
    pairs = [
        (math.log(float(point["oracle_eval_count"])),
         math.log(float(point["absolute_error"])))
        for point in points
        if point.get("oracle_eval_count", 0) > 0 and point.get("absolute_error", 0.0) > 0.0
    ]
    if len(pairs) < 2:
        return None
    mean_x = sum(x for x, _ in pairs) / len(pairs)
    mean_y = sum(y for _, y in pairs) / len(pairs)
    denom = sum((x - mean_x) ** 2 for x, _ in pairs)
    if denom <= 0.0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in pairs) / denom


def add_error(record: dict[str, Any], reference: float) -> dict[str, Any]:
    out = dict(record)
    out["absolute_error"] = abs(float(out["estimate"]) - reference)
    out["rmse"] = out["absolute_error"]
    return out


def write_curve_csv(path: Path, metrics: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for section in ("classical_baselines", "quantum_estimators"):
        for record in metrics.get(section, []):
            rows.append({
                "algorithm": record.get("algorithm"),
                "samples": record.get("samples"),
                "shots": record.get("shots"),
                "oracle_eval_count": record.get("oracle_eval_count"),
                "estimate": record.get("estimate"),
                "reference_value": metrics["reference"]["value"],
                "absolute_error": record.get("absolute_error"),
                "rmse": record.get("rmse"),
                "seed": record.get("seed"),
            })
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "algorithm",
            "samples",
            "shots",
            "oracle_eval_count",
            "estimate",
            "reference_value",
            "absolute_error",
            "rmse",
            "seed",
        ])
        writer.writeheader()
        writer.writerows(rows)


def write_circuit_text(path: Path, metrics: dict[str, Any]) -> None:
    resource = metrics["resource_estimate"]
    oracle = metrics["oracle"]
    lines = [
        "QGE QAE abstract circuit v0",
        f"problem: {metrics['advantage_problem_id']}",
        f"candidate_index_qubits: {resource['candidate_index_bits']}",
        f"threshold_qubits: {resource['contribution_threshold_bits']}",
        f"logical_qubits: {resource['logical_qubits']}",
        "",
        "A:",
        "  H candidate_index_register",
        "  H threshold_register",
        f"  Q_f candidate_index,threshold -> good_bit  # {oracle['oracle_kind']}",
        "",
        "Q = -A S_0 A_dagger S_chi:",
        "  S_chi: phase flip on good_bit",
        "  A_dagger",
        "  S_0: multi-controlled phase on all-zero work state",
        "  A",
        "",
        "Measurement schedule:",
    ]
    for result in metrics["quantum_estimators"]:
        lines.append(
            "  "
            f"powers={result['grover_powers']} "
            f"shots_per_power={result['shots_per_power']} "
            f"oracle_calls={result['controlled_oracle_calls']}"
        )
    lines.extend([
        "",
        "Resource estimate:",
        f"  one_qubit_gates={resource['one_qubit_gates']}",
        f"  two_qubit_gates={resource['two_qubit_gates']}",
        f"  circuit_depth={resource['circuit_depth']}",
        "",
        "Assumption: abstract simulator resource model, not hardware execution.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_icc_evidence(metrics: dict[str, Any],
                       metrics_path: Path,
                       curve_path: Path,
                       circuit_path: Path) -> dict[str, Any]:
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_advantage_benchmark",
        "completion_reason": "qge_advantage_benchmark_complete",
        "advantage_metrics_file": str(metrics_path),
        "qae_curve_file": str(curve_path),
        "circuit_artifact_file": str(circuit_path),
        "advantage_problem_id": metrics["advantage_problem_id"],
        "oracle_eval_count": metrics["comparison"]["best_qae"]["oracle_eval_count"],
        "classical_eval_count": metrics["comparison"]["best_classical"]["oracle_eval_count"],
        "state_prep_cost": metrics["oracle"]["state_prep_cost"],
        "readout_model": metrics["oracle"]["readout_model"],
        "shots": metrics["comparison"]["best_qae"]["shots"],
        "reference_value": metrics["reference"]["value"],
        "rmse": metrics["comparison"]["best_qae"]["rmse"],
        "status": "success",
    }


def build_metrics(args: argparse.Namespace, oracle_scene: dict[str, Any]) -> dict[str, Any]:
    contributions = build_contributions(oracle_scene, args.seed,
                                        args.contribution_bits)
    reference = mean(contributions)
    candidate_count = len(contributions)
    candidate_bits = int(
        oracle_scene.get("oracle_contract", {})
        .get("input_register", {})
        .get("candidate_index_bits") or ceil_log2(candidate_count)
    )

    classical = []
    qae = []
    sample_counts = args.samples or [16, 32, 64, 128, 256]
    for samples in sample_counts:
        classical.append(add_error(mc_estimate(contributions, samples,
                                               args.seed + samples),
                                   reference))
        classical.append(add_error(stratified_vdc_estimate(contributions, samples),
                                   reference))
    for level in range(1, args.qae_levels + 1):
        qae.append(add_error(qae_estimate(reference, level, args.qae_shots,
                                          args.seed + 1000 + level,
                                          args.qae_grid_steps),
                             reference))

    resource = resource_estimate(candidate_bits, args.contribution_bits, qae)
    best_classical = min(classical, key=lambda item: item["absolute_error"])
    best_qae = min(qae, key=lambda item: item["absolute_error"])
    scene = oracle_scene.get("scene", {})
    observable = oracle_scene.get("observable", {})
    cost_model = oracle_scene.get("cost_model", {})
    problem_id = (
        "advantage.light_transport_qae_query_scaling:"
        f"{scene.get('scene_id', 'unknown')}:"
        f"{observable.get('observable_id', 'unknown')}"
    )

    return {
        "schema": "qge.advantage_metrics.v0",
        "advantage_problem_id": problem_id,
        "source_oracle_scene": str(args.oracle_scene),
        "scene": {
            "scene_id": scene.get("scene_id"),
            "map": scene.get("map"),
            "selected_frame": scene.get("selected_frame"),
            "trace_run_id": scene.get("trace_run_id"),
        },
        "observable": {
            "observable_id": observable.get("observable_id"),
            "kind": observable.get("kind"),
            "range": observable.get("range"),
            "model": "deterministic_quake_scene_sidecar_v0",
            "candidate_count": candidate_count,
            "contribution_bits": args.contribution_bits,
        },
        "oracle": {
            "oracle_kind": "bernoulli_lifted_bounded_contribution",
            "implementation_status": "simulator_model",
            "input_model": oracle_scene.get("oracle_contract", {}).get("reversibility"),
            "readout_model": "finite_shot_mlae",
            "qram_assumption": cost_model.get("qram_assumption"),
            "state_prep_cost": cost_model.get("state_prep_cost"),
            "candidate_count": candidate_count,
            "candidate_index_bits": candidate_bits,
            "contribution_threshold_bits": args.contribution_bits,
            "fallback_count": cost_model.get("fallback_count"),
        },
        "reference": {
            "mode": "exact_finite_sidecar_mean",
            "value": reference,
            "candidate_evals": candidate_count,
        },
        "classical_baselines": classical,
        "quantum_estimators": qae,
        "resource_estimate": resource,
        "comparison": {
            "best_classical": best_classical,
            "best_qae": best_qae,
            "mc_loglog_error_slope": fit_slope([
                item for item in classical if item["algorithm"] == "classical_mc"
            ]),
            "stratified_loglog_error_slope": fit_slope([
                item for item in classical if item["algorithm"] == "stratified_vdc"
            ]),
            "qae_loglog_error_slope": fit_slope(qae),
        },
        "claim_posture": {
            "claim_id": "advantage.light_transport_qae_query_scaling",
            "allowed_wording": (
                "This artifact evaluates a Quake-derived bounded mean "
                "observable with classical baselines and an amplitude-"
                "estimation simulator under an explicit oracle model."
            ),
            "disallowed_wording": (
                "This artifact proves practical rendering speedup, hardware "
                "advantage, or full-frame quantum rendering."
            ),
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("oracle_scene", type=Path, help="oracle_scene.json")
    parser.add_argument("--outdir", type=Path, required=True,
                        help="Directory for benchmark artifacts")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--samples", type=int, action="append",
                        help="Classical sample count; repeatable.")
    parser.add_argument("--qae-levels", type=int, default=5)
    parser.add_argument("--qae-shots", type=int, default=128)
    parser.add_argument("--qae-grid-steps", type=int, default=4096)
    parser.add_argument("--contribution-bits", type=int, default=8)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.qae_levels <= 0:
        print("qge_advantage_benchmark: --qae-levels must be > 0", file=sys.stderr)
        return 1
    if args.qae_shots <= 0:
        print("qge_advantage_benchmark: --qae-shots must be > 0", file=sys.stderr)
        return 1
    if args.contribution_bits <= 0 or args.contribution_bits > 16:
        print("qge_advantage_benchmark: --contribution-bits must be in 1..16",
              file=sys.stderr)
        return 1

    try:
        oracle_scene = load_json(args.oracle_scene)
        metrics = build_metrics(args, oracle_scene)
        metrics_path = args.outdir / "advantage_metrics.json"
        curve_path = args.outdir / "qae_curve.csv"
        circuit_path = args.outdir / "qae_circuit.txt"
        icc_path = args.outdir / "qge_advantage_icc_evidence.json"
        write_json(metrics_path, metrics)
        write_curve_csv(curve_path, metrics)
        write_circuit_text(circuit_path, metrics)
        write_json(icc_path, build_icc_evidence(metrics, metrics_path,
                                                curve_path, circuit_path))
    except (OSError, ValueError, KeyError) as exc:
        print(f"qge_advantage_benchmark: {exc}", file=sys.stderr)
        return 1

    print(f"QGE_ADVANTAGE_METRICS {metrics_path}")
    print(f"QGE_QAE_CURVE {curve_path}")
    print(f"QGE_QAE_CIRCUIT {circuit_path}")
    print(f"QGE_ADVANTAGE_ICC_EVIDENCE {icc_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
