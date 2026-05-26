#!/usr/bin/env python3
"""Audit packed advantage metrics against the oracle scene."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_advantage_benchmark  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402
import qge_moonlab_overclaim_audit  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402


ADVANTAGE_METRICS_FORBIDDEN_CLAIMS = (
    "whole_game_moonlab_deployment_claimed",
    "whole_game_hardware_execution_claimed",
    "hardware_result_claimed",
    "hardware_quantum_advantage_claimed",
    "dense_70000_qubit_state_claimed",
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def unique_ints(values: list[Any], *, label: str) -> list[int]:
    ints = sorted({
        value for value in (int_or_none(item) for item in values)
        if value is not None
    })
    if not ints:
        raise ValueError(f"could not infer {label}")
    return ints


def single_int(values: list[Any], *, label: str) -> int:
    ints = unique_ints(values, label=label)
    if len(ints) != 1:
        raise ValueError(f"ambiguous {label}: {ints}")
    return ints[0]


def artifact_entry(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> dict[str, Any]:
    return dict_or_empty(
        dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(section))
        .get(name)
    )


def artifact_path_string(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> str | None:
    entry = artifact_entry(manifest, section, name)
    raw_path = entry.get("path")
    if not raw_path:
        raw_path = dict_or_empty(entry.get("packed")).get("path")
    return raw_path if isinstance(raw_path, str) and raw_path else None


def artifact_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    base_dir: Path | None = None,
) -> Path | None:
    return qge_moonlab_full_game_plan.resolve_path(
        artifact_path_string(manifest, section, name),
        base_dir=base_dir,
    )


def infer_seed(metrics: dict[str, Any]) -> int:
    bases = []
    for item in list_or_empty(metrics.get("trials")):
        if not isinstance(item, dict):
            continue
        trial = int_or_none(item.get("trial"))
        trial_seed = int_or_none(item.get("trial_seed"))
        if trial is None or trial_seed is None:
            continue
        bases.append(trial_seed - qge_advantage_benchmark.trial_seed(0, trial))
    return single_int(bases, label="seed")


def infer_qae_shots(records: list[Any]) -> int:
    shots = []
    for item in records:
        if not isinstance(item, dict):
            continue
        shots.append(item.get("shots_per_power"))
        for observation in list_or_empty(item.get("observations")):
            if isinstance(observation, dict):
                shots.append(observation.get("shots"))
    return single_int(shots, label="qae_shots")


def infer_benchmark_args(
    metrics: dict[str, Any],
    *,
    oracle_scene_path: Path,
) -> SimpleNamespace:
    trial_count = (
        int_or_none(dict_or_empty(metrics.get("scaling_summary")).get(
            "trial_count"))
        or len(list_or_empty(metrics.get("trials")))
    )
    if trial_count <= 0:
        raise ValueError("could not infer trial count")

    trial_records = dict_or_empty(metrics.get("trial_records"))
    classical_records = (
        list_or_empty(trial_records.get("classical_baselines")) or
        list_or_empty(metrics.get("classical_baselines"))
    )
    qae_records = (
        list_or_empty(trial_records.get("quantum_estimators")) or
        list_or_empty(metrics.get("quantum_estimators"))
    )
    qae_levels = max(
        len(list_or_empty(record.get("grover_powers")))
        for record in qae_records
        if isinstance(record, dict)
    )
    if qae_levels <= 0:
        raise ValueError("could not infer qae_levels")

    return SimpleNamespace(
        oracle_scene=oracle_scene_path,
        outdir=Path("."),
        seed=infer_seed(metrics),
        trials=trial_count,
        samples=unique_ints(
            [
                record.get("samples")
                for record in classical_records
                if isinstance(record, dict)
            ],
            label="samples",
        ),
        qae_levels=qae_levels,
        qae_shots=infer_qae_shots(qae_records),
        qae_grid_steps=single_int(
            [
                record.get("grid_steps")
                for record in qae_records
                if isinstance(record, dict)
            ],
            label="qae_grid_steps",
        ),
        contribution_bits=single_int(
            [
                dict_or_empty(metrics.get("oracle")).get(
                    "contribution_threshold_bits"),
                dict_or_empty(metrics.get("observable")).get(
                    "contribution_bits"),
                dict_or_empty(metrics.get("resource_estimate")).get(
                    "contribution_threshold_bits"),
            ],
            label="contribution_bits",
        ),
    )


def build_expected(
    manifest: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    oracle_raw = artifact_path_string(manifest, "oracle", "oracle_scene")
    oracle_path = artifact_path(
        manifest, "oracle", "oracle_scene", base_dir=base_dir)
    metrics_path = artifact_path(
        manifest, "advantage", "metrics", base_dir=base_dir)
    if oracle_path is None or not oracle_path.is_file():
        raise ValueError("oracle.oracle_scene is missing")
    if metrics_path is None or not metrics_path.is_file():
        raise ValueError("advantage.metrics is missing")

    recorded_metrics = load_json(metrics_path)
    oracle_scene = load_json(oracle_path)
    args = infer_benchmark_args(
        recorded_metrics,
        oracle_scene_path=Path(oracle_raw) if oracle_raw else oracle_path,
    )
    expected_metrics = qge_advantage_benchmark.build_metrics(
        args,
        oracle_scene,
    )
    expected_icc = qge_advantage_benchmark.build_icc_evidence(
        expected_metrics,
        Path(artifact_path_string(manifest, "advantage", "metrics") or ""),
        Path(artifact_path_string(manifest, "advantage", "qae_curve") or ""),
        Path(artifact_path_string(manifest, "advantage", "qae_circuit") or ""),
        Path(artifact_path_string(
            manifest, "advantage", "scaling_summary") or ""),
    )
    inferred = {
        "seed": args.seed,
        "trials": args.trials,
        "samples": args.samples,
        "qae_levels": args.qae_levels,
        "qae_shots": args.qae_shots,
        "qae_grid_steps": args.qae_grid_steps,
        "contribution_bits": args.contribution_bits,
    }
    return expected_metrics, expected_icc, inferred


def empty_audit(required: bool) -> dict[str, Any]:
    return {
        "required": required,
        "recorded": False,
        "expected_artifact_count": 2,
        "recorded_artifact_count": 0,
        "missing_artifacts": [],
        "build_errors": [],
        "inferred_parameters": {},
        "metrics_mismatches": [],
        "icc_mismatches": [],
        "overclaim_flags": [],
        "mismatch_count": 0,
        "passed": not required,
    }


def advantage_metrics_audit(
    manifest: dict[str, Any] | None,
    *,
    manifest_path: Path,
    required: bool = True,
) -> dict[str, Any]:
    manifest_data = dict_or_empty(manifest)
    base_dir = manifest_path.parent
    active = required or bool(manifest_data)
    if not active:
        return empty_audit(required)

    paths = {
        "oracle.oracle_scene": artifact_path(
            manifest_data, "oracle", "oracle_scene", base_dir=base_dir),
        "advantage.metrics": artifact_path(
            manifest_data, "advantage", "metrics", base_dir=base_dir),
        "advantage.icc_evidence": artifact_path(
            manifest_data, "advantage", "icc_evidence", base_dir=base_dir),
    }
    missing_artifacts = [
        {"artifact": name, "path": str(path) if path is not None else None}
        for name, path in paths.items()
        if path is None or not path.is_file()
    ]
    metrics_path = paths["advantage.metrics"]
    icc_path = paths["advantage.icc_evidence"]
    recorded_metrics = (
        load_json(metrics_path) if metrics_path is not None and
        metrics_path.is_file() else {}
    )
    recorded_icc = (
        load_json(icc_path) if icc_path is not None and icc_path.is_file()
        else {}
    )

    build_errors: list[dict[str, str]] = []
    inferred: dict[str, Any] = {}
    try:
        expected_metrics, expected_icc, inferred = build_expected(
            manifest_data,
            base_dir=base_dir,
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        build_errors.append({
            "artifact": "advantage.metrics",
            "error": str(exc),
        })
        expected_metrics = {}
        expected_icc = {}

    metrics_mismatches = (
        qge_resource_boundary_audit.mismatch_paths(
            expected_metrics,
            recorded_metrics,
        )
        if recorded_metrics else []
    )
    icc_mismatches = (
        qge_resource_boundary_audit.mismatch_paths(
            expected_icc,
            recorded_icc,
        )
        if recorded_icc else []
    )
    overclaim_flags = (
        qge_moonlab_overclaim_audit.recursive_overclaim_flags(
            "advantage.metrics",
            recorded_metrics,
            forbidden=ADVANTAGE_METRICS_FORBIDDEN_CLAIMS,
        ) +
        qge_moonlab_overclaim_audit.recursive_overclaim_flags(
            "advantage.icc_evidence",
            recorded_icc,
            forbidden=ADVANTAGE_METRICS_FORBIDDEN_CLAIMS,
        )
    )
    recorded_count = int(bool(recorded_metrics)) + int(bool(recorded_icc))
    mismatch_count = (
        len(missing_artifacts) +
        len(build_errors) +
        len(metrics_mismatches) +
        len(icc_mismatches) +
        len(overclaim_flags)
    )
    return {
        "required": required,
        "recorded": recorded_count == 2,
        "expected_artifact_count": 2,
        "recorded_artifact_count": recorded_count,
        "missing_artifacts": missing_artifacts,
        "build_errors": build_errors,
        "inferred_parameters": inferred,
        "metrics_mismatches": metrics_mismatches,
        "icc_mismatches": icc_mismatches,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (recorded_count == 2 or not required),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pack_or_manifest",
        type=Path,
        help="Publication pack directory or publication_manifest.json path.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional audit JSON output path.",
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit nonzero when advantage metrics are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        manifest_path = qge_moonlab_full_game_plan.resolve_publication_manifest(
            args.pack_or_manifest)
        audit = advantage_metrics_audit(
            load_json(manifest_path),
            manifest_path=manifest_path,
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_ADVANTAGE_METRICS_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_advantage_metrics_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
