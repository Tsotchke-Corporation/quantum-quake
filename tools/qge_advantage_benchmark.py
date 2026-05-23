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


def sample_stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) /
                     (len(values) - 1))


def ci95_half_width(values: list[float]) -> float:
    if not values:
        return 0.0
    return 1.96 * sample_stdev(values) / math.sqrt(len(values))


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


def fit_slope(points: list[dict[str, Any]],
              delta_key: str = "absolute_delta") -> float | None:
    pairs = [
        (math.log(float(point["oracle_eval_count"])),
         math.log(float(point.get(
             delta_key, point.get("absolute_error", 0.0)))))
        for point in points
        if point.get("oracle_eval_count", 0) > 0 and
        point.get(delta_key, point.get("absolute_error", 0.0)) > 0.0
    ]
    if len(pairs) < 2:
        return None
    mean_x = sum(x for x, _ in pairs) / len(pairs)
    mean_y = sum(y for _, y in pairs) / len(pairs)
    denom = sum((x - mean_x) ** 2 for x, _ in pairs)
    if denom <= 0.0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in pairs) / denom


def add_delta(record: dict[str, Any], reference: float) -> dict[str, Any]:
    out = dict(record)
    out["absolute_delta"] = abs(float(out["estimate"]) - reference)
    out["rmse"] = out["absolute_delta"]
    return out


def trial_seed(base_seed: int, trial: int) -> int:
    return base_seed + trial * 104729


def sample_counts(args: argparse.Namespace) -> list[int]:
    return sorted(dict.fromkeys(args.samples or [16, 32, 64, 128, 256]))


def annotate_trial_record(record: dict[str, Any],
                          reference: float,
                          trial: int,
                          seed: int) -> dict[str, Any]:
    out = add_delta(record, reference)
    out["trial"] = trial
    out["trial_seed"] = seed
    out["reference_value"] = reference
    return out


def aggregate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in records:
        key = (
            record.get("algorithm"),
            record.get("oracle_eval_count"),
            record.get("samples"),
            record.get("shots"),
        )
        groups.setdefault(key, []).append(record)

    rows = []
    for key, group in groups.items():
        algorithm, oracle_evals, samples, shots = key
        signed_deltas = [
            float(record["estimate"]) - float(record["reference_value"])
            for record in group
        ]
        abs_deltas = [abs(delta) for delta in signed_deltas]
        estimates = [float(record["estimate"]) for record in group]
        references = [float(record["reference_value"]) for record in group]
        mean_abs = mean(abs_deltas)
        row = {
            "algorithm": algorithm,
            "oracle_eval_count": oracle_evals,
            "samples": samples,
            "shots": shots,
            "trial_count": len(group),
            "mean_estimate": mean(estimates),
            "mean_reference_value": mean(references),
            "mean_absolute_delta": mean_abs,
            "absolute_delta": mean_abs,
            "rmse": rmse(signed_deltas),
            "std_absolute_delta": sample_stdev(abs_deltas),
            "stderr_absolute_delta": (
                sample_stdev(abs_deltas) / math.sqrt(len(abs_deltas))
                if abs_deltas else 0.0
            ),
            "ci95_absolute_delta": ci95_half_width(abs_deltas),
            "min_absolute_delta": min(abs_deltas) if abs_deltas else 0.0,
            "max_absolute_delta": max(abs_deltas) if abs_deltas else 0.0,
            "trial_seeds": [record.get("trial_seed") for record in group],
        }
        rows.append(row)

    return sorted(rows, key=lambda row: (
        str(row.get("algorithm")),
        int(row.get("oracle_eval_count") or 0),
        int(row.get("samples") or 0),
        int(row.get("shots") or 0),
    ))


def write_curve_csv(path: Path, metrics: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for section in ("classical_baselines", "quantum_estimators"):
        for record in metrics.get("trial_records", {}).get(section, []):
            rows.append({
                "trial": record.get("trial"),
                "algorithm": record.get("algorithm"),
                "samples": record.get("samples"),
                "shots": record.get("shots"),
                "oracle_eval_count": record.get("oracle_eval_count"),
                "estimate": record.get("estimate"),
                "reference_value": record.get("reference_value"),
                "absolute_delta": record.get("absolute_delta"),
                "rmse": record.get("rmse"),
                "seed": record.get("seed"),
                "trial_seed": record.get("trial_seed"),
            })
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "trial",
            "algorithm",
            "samples",
            "shots",
            "oracle_eval_count",
            "estimate",
            "reference_value",
            "absolute_delta",
            "rmse",
            "seed",
            "trial_seed",
        ])
        writer.writeheader()
        writer.writerows(rows)


def write_scaling_csv(path: Path, metrics: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    scaling = metrics.get("scaling_summary", {})
    for estimator_family in ("classical_baselines", "quantum_estimators"):
        for record in scaling.get(estimator_family, []):
            row = dict(record)
            row["estimator_family"] = estimator_family
            row.pop("trial_seeds", None)
            rows.append(row)

    fieldnames = [
        "estimator_family",
        "algorithm",
        "samples",
        "shots",
        "oracle_eval_count",
        "trial_count",
        "mean_estimate",
        "mean_reference_value",
        "mean_absolute_delta",
        "rmse",
        "std_absolute_delta",
        "stderr_absolute_delta",
        "ci95_absolute_delta",
        "min_absolute_delta",
        "max_absolute_delta",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})


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
                       circuit_path: Path,
                       scaling_path: Path) -> dict[str, Any]:
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_advantage_benchmark",
        "completion_reason": "qge_advantage_benchmark_complete",
        "advantage_metrics_file": str(metrics_path),
        "qae_curve_file": str(curve_path),
        "circuit_artifact_file": str(circuit_path),
        "scaling_summary_file": str(scaling_path),
        "advantage_problem_id": metrics["advantage_problem_id"],
        "oracle_eval_count": metrics["comparison"]["best_qae"]["oracle_eval_count"],
        "classical_eval_count": metrics["comparison"]["best_classical"]["oracle_eval_count"],
        "state_prep_cost": metrics["oracle"]["state_prep_cost"],
        "readout_model": metrics["oracle"]["readout_model"],
        "shots": metrics["comparison"]["best_qae"]["shots"],
        "trial_count": metrics["scaling_summary"]["trial_count"],
        "confidence_level": metrics["scaling_summary"]["confidence_level"],
        "reference_value": metrics["comparison"]["best_qae"]["mean_reference_value"],
        "rmse": metrics["comparison"]["best_qae"]["rmse"],
        "ci95_absolute_delta": metrics["comparison"]["best_qae"]["ci95_absolute_delta"],
        "status": "success",
    }


def build_trial_metrics(args: argparse.Namespace,
                        oracle_scene: dict[str, Any],
                        trial: int) -> dict[str, Any]:
    seed = trial_seed(args.seed, trial)
    contributions = build_contributions(oracle_scene, seed,
                                        args.contribution_bits)
    reference = mean(contributions)
    candidate_count = len(contributions)

    classical = []
    qae = []
    for samples in sample_counts(args):
        classical.append(annotate_trial_record(
            mc_estimate(contributions, samples, seed + samples),
            reference, trial, seed))
        classical.append(annotate_trial_record(
            stratified_vdc_estimate(contributions, samples),
            reference, trial, seed))
    for level in range(1, args.qae_levels + 1):
        qae.append(annotate_trial_record(
            qae_estimate(reference, level, args.qae_shots,
                         seed + 1000 + level, args.qae_grid_steps),
            reference, trial, seed))

    return {
        "trial": trial,
        "trial_seed": seed,
        "reference": {
            "value": reference,
            "candidate_evals": candidate_count,
        },
        "classical_baselines": classical,
        "quantum_estimators": qae,
    }


def build_metrics(args: argparse.Namespace, oracle_scene: dict[str, Any]) -> dict[str, Any]:
    trials = [
        build_trial_metrics(args, oracle_scene, trial)
        for trial in range(args.trials)
    ]
    first_trial = trials[0]
    first_reference = float(first_trial["reference"]["value"])
    first_classical = first_trial["classical_baselines"]
    first_qae = first_trial["quantum_estimators"]
    all_classical = [
        record for trial in trials for record in trial["classical_baselines"]
    ]
    all_qae = [
        record for trial in trials for record in trial["quantum_estimators"]
    ]
    classical_summary = aggregate_records(all_classical)
    qae_summary = aggregate_records(all_qae)
    candidate_count = int(first_trial["reference"]["candidate_evals"])
    candidate_bits = int(
        oracle_scene.get("oracle_contract", {})
        .get("input_register", {})
        .get("candidate_index_bits") or ceil_log2(candidate_count)
    )

    resource = resource_estimate(candidate_bits, args.contribution_bits, all_qae)
    best_classical = min(classical_summary, key=lambda item: item["rmse"])
    best_qae = min(qae_summary, key=lambda item: item["rmse"])
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
            "value": first_reference,
            "trial_mean_value": mean([
                float(trial["reference"]["value"]) for trial in trials
            ]),
            "candidate_evals": candidate_count,
        },
        "classical_baselines": first_classical,
        "quantum_estimators": first_qae,
        "trial_records": {
            "classical_baselines": all_classical,
            "quantum_estimators": all_qae,
        },
        "trials": [
            {
                "trial": trial["trial"],
                "trial_seed": trial["trial_seed"],
                "reference_value": trial["reference"]["value"],
            }
            for trial in trials
        ],
        "scaling_summary": {
            "trial_count": args.trials,
            "confidence_level": 0.95,
            "classical_baselines": classical_summary,
            "quantum_estimators": qae_summary,
        },
        "resource_estimate": resource,
        "comparison": {
            "best_classical": best_classical,
            "best_qae": best_qae,
            "mc_loglog_delta_slope": fit_slope([
                item for item in classical_summary
                if item["algorithm"] == "classical_mc"
            ], "rmse"),
            "stratified_loglog_delta_slope": fit_slope([
                item for item in classical_summary
                if item["algorithm"] == "stratified_vdc"
            ], "rmse"),
            "qae_loglog_delta_slope": fit_slope(qae_summary, "rmse"),
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
    parser.add_argument("--trials", type=int, default=1,
                        help="Independent deterministic trials for scaling aggregation.")
    parser.add_argument("--samples", type=int, action="append",
                        help="Classical sample count; repeatable.")
    parser.add_argument("--qae-levels", type=int, default=5)
    parser.add_argument("--qae-shots", type=int, default=128)
    parser.add_argument("--qae-grid-steps", type=int, default=4096)
    parser.add_argument("--contribution-bits", type=int, default=8)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.trials <= 0:
        print("qge_advantage_benchmark: --trials must be > 0", file=sys.stderr)
        return 1
    if any(samples <= 0 for samples in sample_counts(args)):
        print("qge_advantage_benchmark: --samples values must be > 0", file=sys.stderr)
        return 1
    if args.qae_levels <= 0:
        print("qge_advantage_benchmark: --qae-levels must be > 0", file=sys.stderr)
        return 1
    if args.qae_shots <= 0:
        print("qge_advantage_benchmark: --qae-shots must be > 0", file=sys.stderr)
        return 1
    if args.qae_grid_steps <= 0:
        print("qge_advantage_benchmark: --qae-grid-steps must be > 0", file=sys.stderr)
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
        scaling_path = args.outdir / "scaling_summary.json"
        scaling_csv_path = args.outdir / "scaling_summary.csv"
        icc_path = args.outdir / "qge_advantage_icc_evidence.json"
        write_json(metrics_path, metrics)
        write_curve_csv(curve_path, metrics)
        write_json(scaling_path, metrics["scaling_summary"])
        write_scaling_csv(scaling_csv_path, metrics)
        write_circuit_text(circuit_path, metrics)
        write_json(icc_path, build_icc_evidence(metrics, metrics_path,
                                                curve_path, circuit_path,
                                                scaling_path))
    except (OSError, ValueError, KeyError) as exc:
        print(f"qge_advantage_benchmark: {exc}", file=sys.stderr)
        return 1

    print(f"QGE_ADVANTAGE_METRICS {metrics_path}")
    print(f"QGE_QAE_CURVE {curve_path}")
    print(f"QGE_QAE_CIRCUIT {circuit_path}")
    print(f"QGE_SCALING_SUMMARY {scaling_path}")
    print(f"QGE_SCALING_SUMMARY_CSV {scaling_csv_path}")
    print(f"QGE_ADVANTAGE_ICC_EVIDENCE {icc_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
