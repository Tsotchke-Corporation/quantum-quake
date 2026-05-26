#!/usr/bin/env python3
"""Audit packed Moonlab advantage artifacts against source inputs."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_moonlab_advantage_icc_audit  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402
import qge_moonlab_oracle_transpile  # noqa: E402
import qge_moonlab_overclaim_audit  # noqa: E402
import qge_moonlab_qae_grover_plan  # noqa: E402
import qge_moonlab_qae_observation_transpile  # noqa: E402
import qge_moonlab_qae_transpile  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402


ADVANTAGE_SOURCE_ARTIFACTS = (
    ("advantage", "metrics"),
    ("advantage", "qae_circuit"),
    ("advantage", "qae_curve"),
    ("advantage", "scaling_summary"),
    ("oracle", "oracle_scene"),
)
ADVANTAGE_JSON_OUTPUTS = (
    "qae_moonlab_payload",
    "qae_moonlab_oracle_kernel",
    "qae_moonlab_observation_zero",
    "qae_moonlab_grover_schedule_plan",
)
ADVANTAGE_ICC_OUTPUTS = (
    "icc_evidence",
    "qae_moonlab_payload_icc_evidence",
    "qae_moonlab_oracle_kernel_icc_evidence",
    "qae_moonlab_observation_zero_icc_evidence",
    "qae_moonlab_grover_schedule_plan_icc_evidence",
)
ADVANTAGE_PATH_ARTIFACTS = (
    "qae_moonlab_circuits",
    "qae_moonlab_oracle_kernel_circuit",
    "qae_moonlab_observation_zero_circuit",
    "qae_moonlab_grover_circuits",
)
ADVANTAGE_ARTIFACT_FORBIDDEN_CLAIMS = (
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


def load_artifact_json(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    path = artifact_path(manifest, section, name, base_dir=base_dir)
    if path is None or not path.is_file():
        return {}
    return load_json(path)


def join_raw_path(raw_dir: str | None, filename: str) -> str | None:
    if not isinstance(raw_dir, str) or not raw_dir:
        return None
    return str(Path(raw_dir) / filename)


def raw_paths(manifest: dict[str, Any]) -> dict[str, str | None]:
    return {
        "advantage_metrics": artifact_path_string(
            manifest, "advantage", "metrics"),
        "qae_curve": artifact_path_string(
            manifest, "advantage", "qae_curve"),
        "qae_circuit": artifact_path_string(
            manifest, "advantage", "qae_circuit"),
        "scaling_summary": artifact_path_string(
            manifest, "advantage", "scaling_summary"),
        "oracle_scene": artifact_path_string(
            manifest, "oracle", "oracle_scene"),
        "qae_moonlab_payload": artifact_path_string(
            manifest, "advantage", "qae_moonlab_payload"),
        "qae_moonlab_payload_circuits": artifact_path_string(
            manifest, "advantage", "qae_moonlab_circuits"),
        "qae_moonlab_oracle_kernel": artifact_path_string(
            manifest, "advantage", "qae_moonlab_oracle_kernel"),
        "qae_moonlab_oracle_kernel_circuit": artifact_path_string(
            manifest, "advantage", "qae_moonlab_oracle_kernel_circuit"),
        "qae_moonlab_observation_zero": artifact_path_string(
            manifest, "advantage", "qae_moonlab_observation_zero"),
        "qae_moonlab_observation_zero_circuit": artifact_path_string(
            manifest, "advantage", "qae_moonlab_observation_zero_circuit"),
        "qae_moonlab_grover_schedule_plan": artifact_path_string(
            manifest, "advantage", "qae_moonlab_grover_schedule_plan"),
        "qae_moonlab_grover_circuits": artifact_path_string(
            manifest, "advantage", "qae_moonlab_grover_circuits"),
    }


def normalize_payload_paths(
    payload: dict[str, Any],
    paths: dict[str, str | None],
) -> None:
    payload["source_metrics"] = paths.get("advantage_metrics")
    source_circuit = dict_or_empty(payload.get("source_abstract_circuit"))
    if source_circuit:
        source_circuit["path"] = paths.get("qae_circuit")
        payload["source_abstract_circuit"] = source_circuit
    circuit_dir = paths.get("qae_moonlab_payload_circuits")
    for index, record in enumerate(
        list_or_empty(payload.get("observation_circuits"))
    ):
        if isinstance(record, dict):
            record["moonlab_circuit_file"] = join_raw_path(
                circuit_dir,
                f"observation_{index:03d}.moonlab",
            )


def normalize_kernel_paths(
    kernel: dict[str, Any],
    paths: dict[str, str | None],
) -> None:
    kernel["source_metrics"] = paths.get("advantage_metrics")
    kernel["source_oracle_scene"] = paths.get("oracle_scene")
    kernel["moonlab_circuit_file"] = paths.get(
        "qae_moonlab_oracle_kernel_circuit")


def normalize_observation_paths(
    observation: dict[str, Any],
    paths: dict[str, str | None],
) -> None:
    observation["source_metrics"] = paths.get("advantage_metrics")
    observation["source_oracle_scene"] = paths.get("oracle_scene")
    observation["moonlab_circuit_file"] = paths.get(
        "qae_moonlab_observation_zero_circuit")


def normalize_grover_paths(
    plan: dict[str, Any],
    paths: dict[str, str | None],
) -> None:
    plan["source_metrics"] = paths.get("advantage_metrics")
    plan["source_oracle_scene"] = paths.get("oracle_scene")
    circuit_dir = paths.get("qae_moonlab_grover_circuits")
    for index, record in enumerate(list_or_empty(plan.get("observations"))):
        if not isinstance(record, dict):
            continue
        power = int(record.get("grover_power") or 0)
        record["moonlab_circuit_file"] = join_raw_path(
            circuit_dir,
            f"observation_{index:03d}_power_{power:03d}.moonlab",
        )


def expected_advantage_artifacts(
    manifest: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    paths = raw_paths(manifest)
    metrics_path = artifact_path(
        manifest, "advantage", "metrics", base_dir=base_dir)
    qae_circuit_path = artifact_path(
        manifest, "advantage", "qae_circuit", base_dir=base_dir)
    oracle_scene_path = artifact_path(
        manifest, "oracle", "oracle_scene", base_dir=base_dir)
    if metrics_path is None or not metrics_path.is_file():
        raise ValueError("advantage.metrics is missing")
    if qae_circuit_path is None or not qae_circuit_path.is_file():
        raise ValueError("advantage.qae_circuit is missing")
    if oracle_scene_path is None or not oracle_scene_path.is_file():
        raise ValueError("oracle.oracle_scene is missing")

    metrics = load_json(metrics_path)
    oracle_scene = load_json(oracle_scene_path)
    with tempfile.TemporaryDirectory(prefix="qge_advantage_audit_") as tmp:
        scratch = Path(tmp)
        payload = qge_moonlab_qae_transpile.build_payload(
            metrics,
            metrics_path=metrics_path,
            abstract_circuit_path=qae_circuit_path,
            circuit_dir=scratch / "moonlab_qae_circuits",
        )
        kernel = qge_moonlab_oracle_transpile.build_kernel(
            metrics,
            oracle_scene,
            metrics_path=metrics_path,
            oracle_scene_path=oracle_scene_path,
            circuit_path=scratch / "qae_moonlab_oracle_kernel.moonlab",
        )
        observation = (
            qge_moonlab_qae_observation_transpile
            .build_observation_circuit(
                metrics,
                oracle_scene,
                metrics_path=metrics_path,
                oracle_scene_path=oracle_scene_path,
                circuit_path=(
                    scratch / "qae_moonlab_observation_zero.moonlab"),
            )
        )
        grover_plan = qge_moonlab_qae_grover_plan.build_schedule_plan(
            metrics,
            oracle_scene,
            metrics_path=metrics_path,
            oracle_scene_path=oracle_scene_path,
            circuit_dir=scratch / "qae_moonlab_grover_circuits",
        )

    normalize_payload_paths(payload, paths)
    normalize_kernel_paths(kernel, paths)
    normalize_observation_paths(observation, paths)
    normalize_grover_paths(grover_plan, paths)
    artifacts = {
        "qae_moonlab_payload": payload,
        "qae_moonlab_oracle_kernel": kernel,
        "qae_moonlab_observation_zero": observation,
        "qae_moonlab_grover_schedule_plan": grover_plan,
    }
    sidecars = qge_moonlab_advantage_icc_audit.expected_advantage_icc_sidecars(
        {
            "advantage_metrics": metrics,
            **artifacts,
        },
        artifact_paths={
            key: value for key, value in paths.items()
            if isinstance(value, str)
        },
    )
    return {**artifacts, **sidecars}


def empty_audit(required: bool) -> dict[str, Any]:
    return {
        "required": required,
        "recorded": False,
        "expected_json_artifact_count": len(ADVANTAGE_JSON_OUTPUTS),
        "recorded_json_artifact_count": 0,
        "expected_icc_sidecar_count": len(ADVANTAGE_ICC_OUTPUTS),
        "recorded_icc_sidecar_count": 0,
        "missing_artifacts": [],
        "build_errors": [],
        "json_mismatches": [],
        "icc_mismatches": [],
        "overclaim_flags": [],
        "mismatch_count": 0,
        "passed": not required,
    }


def moonlab_advantage_artifact_audit(
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

    source_paths = {
        f"{section}.{name}": artifact_path(
            manifest_data, section, name, base_dir=base_dir)
        for section, name in ADVANTAGE_SOURCE_ARTIFACTS
    }
    output_names = ADVANTAGE_JSON_OUTPUTS + ADVANTAGE_ICC_OUTPUTS
    output_paths = {
        name: artifact_path(
            manifest_data, "advantage", name, base_dir=base_dir)
        for name in output_names
    }
    path_artifacts = {
        f"advantage.{name}": artifact_path(
            manifest_data, "advantage", name, base_dir=base_dir)
        for name in ADVANTAGE_PATH_ARTIFACTS
    }
    missing_artifacts = [
        {
            "artifact": label,
            "path": str(path) if path is not None else None,
        }
        for label, path in {**source_paths, **path_artifacts}.items()
        if path is None or not path.exists()
    ]
    missing_artifacts.extend([
        {
            "artifact": f"advantage.{name}",
            "path": str(path) if path is not None else None,
        }
        for name, path in output_paths.items()
        if path is None or not path.is_file()
    ])

    recorded_json = {
        name: load_json(path)
        for name, path in output_paths.items()
        if name in ADVANTAGE_JSON_OUTPUTS and
        path is not None and path.is_file()
    }
    recorded_icc = {
        name: load_json(path)
        for name, path in output_paths.items()
        if name in ADVANTAGE_ICC_OUTPUTS and
        path is not None and path.is_file()
    }

    build_errors: list[dict[str, str]] = []
    try:
        expected = expected_advantage_artifacts(
            manifest_data,
            base_dir=base_dir,
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        build_errors.append({
            "artifact": "advantage.qae_moonlab_payload",
            "error": str(exc),
        })
        expected = {}

    json_mismatches = []
    for name in ADVANTAGE_JSON_OUTPUTS:
        recorded = dict_or_empty(recorded_json.get(name))
        if not recorded:
            continue
        fields = qge_resource_boundary_audit.mismatch_paths(
            dict_or_empty(expected.get(name)),
            recorded,
        )
        if fields:
            json_mismatches.append({
                "artifact": f"advantage.{name}",
                "fields": fields,
            })

    icc_mismatches = []
    for name in ADVANTAGE_ICC_OUTPUTS:
        recorded = dict_or_empty(recorded_icc.get(name))
        if not recorded:
            continue
        expected_name = (
            "advantage_icc_evidence" if name == "icc_evidence" else name
        )
        fields = qge_resource_boundary_audit.mismatch_paths(
            dict_or_empty(expected.get(expected_name)),
            recorded,
        )
        if fields:
            icc_mismatches.append({
                "artifact": f"advantage.{name}",
                "fields": fields,
            })

    overclaim_flags = []
    for name, artifact in {**recorded_json, **recorded_icc}.items():
        overclaim_flags.extend(
            qge_moonlab_overclaim_audit.recursive_overclaim_flags(
                name,
                artifact,
                forbidden=ADVANTAGE_ARTIFACT_FORBIDDEN_CLAIMS,
            )
        )

    recorded_json_count = sum(
        1 for name in ADVANTAGE_JSON_OUTPUTS
        if dict_or_empty(recorded_json.get(name))
    )
    recorded_icc_count = sum(
        1 for name in ADVANTAGE_ICC_OUTPUTS
        if dict_or_empty(recorded_icc.get(name))
    )
    mismatch_count = (
        len(missing_artifacts) +
        len(build_errors) +
        sum(len(item["fields"]) for item in json_mismatches) +
        sum(len(item["fields"]) for item in icc_mismatches) +
        len(overclaim_flags)
    )
    recorded = (
        recorded_json_count == len(ADVANTAGE_JSON_OUTPUTS) and
        recorded_icc_count == len(ADVANTAGE_ICC_OUTPUTS)
    )
    return {
        "required": required,
        "recorded": recorded,
        "expected_json_artifact_count": len(ADVANTAGE_JSON_OUTPUTS),
        "recorded_json_artifact_count": recorded_json_count,
        "expected_icc_sidecar_count": len(ADVANTAGE_ICC_OUTPUTS),
        "recorded_icc_sidecar_count": recorded_icc_count,
        "missing_artifacts": missing_artifacts,
        "build_errors": build_errors,
        "json_mismatches": json_mismatches,
        "icc_mismatches": icc_mismatches,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (recorded or not required),
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
        help="Exit nonzero when Moonlab advantage artifacts are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        manifest_path = qge_moonlab_full_game_plan.resolve_publication_manifest(
            args.pack_or_manifest)
        audit = moonlab_advantage_artifact_audit(
            load_json(manifest_path),
            manifest_path=manifest_path,
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_MOONLAB_ADVANTAGE_ARTIFACT_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_moonlab_advantage_artifact_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
