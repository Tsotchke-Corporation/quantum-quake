#!/usr/bin/env python3
"""Audit packed Moonlab job plan artifacts against the manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_moonlab_full_game_plan  # noqa: E402
import qge_moonlab_job_runner  # noqa: E402
import qge_moonlab_overclaim_audit  # noqa: E402
import qge_publication_pack  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402


RESOURCE_ARTIFACTS = (
    "envelope",
    "moonlab_job_specs",
    "moonlab_job_results",
    "moonlab_replay_plan",
    "moonlab_submission_packet",
)
JOB_PLAN_FORBIDDEN_CLAIMS = (
    "whole_game_hardware_execution_claimed",
    "hardware_result_claimed",
    "hardware_quantum_advantage_claimed",
    "dense_70000_qubit_state_claimed",
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def artifact_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    base_dir: Path | None = None,
) -> Path | None:
    entry = dict_or_empty(
        dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(section))
        .get(name)
    )
    raw_path = entry.get("path")
    if not raw_path:
        raw_path = dict_or_empty(entry.get("packed")).get("path")
    return qge_moonlab_full_game_plan.resolve_path(
        raw_path,
        base_dir=base_dir,
    )


def artifact_path_string(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> str | None:
    entry = dict_or_empty(
        dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(section))
        .get(name)
    )
    raw_path = entry.get("path")
    if not raw_path:
        raw_path = dict_or_empty(entry.get("packed")).get("path")
    return raw_path if isinstance(raw_path, str) and raw_path else None


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


def artifact_paths_for_job_specs(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "oracle_scene": artifact_path_string(
            manifest, "oracle", "oracle_scene"),
        "advantage_metrics": artifact_path_string(
            manifest, "advantage", "metrics"),
        "qae_circuit": artifact_path_string(
            manifest, "advantage", "qae_circuit"),
        "moonlab_qae_payload": artifact_path_string(
            manifest, "advantage", "qae_moonlab_payload"),
        "moonlab_qae_oracle_kernel": artifact_path_string(
            manifest, "advantage", "qae_moonlab_oracle_kernel"),
        "moonlab_qae_observation_zero": artifact_path_string(
            manifest, "advantage", "qae_moonlab_observation_zero"),
        "moonlab_qae_grover_schedule_plan": artifact_path_string(
            manifest, "advantage", "qae_moonlab_grover_schedule_plan"),
        "moonlab_qae_grover_circuits": artifact_path_string(
            manifest, "advantage", "qae_moonlab_grover_circuits"),
        "trace": artifact_path_string(manifest, "capture", "trace"),
        "frame": artifact_path_string(manifest, "capture", "frame"),
        "vanilla_matrix": artifact_path_string(
            manifest, "vanilla", "matrix"),
        "performance_summary": artifact_path_string(
            manifest, "capture", "performance_summary"),
        "breadth_evidence": artifact_path_string(
            manifest, "breadth", "evidence"),
        "full_game_map_coverage": artifact_path_string(
            manifest, "resource", "full_game_map_coverage"),
        "asset_inventory": artifact_path_string(
            manifest, "resource", "asset_inventory"),
        "asset_requirements": artifact_path_string(
            manifest, "resource", "asset_requirements"),
        "registered_asset_intake": artifact_path_string(
            manifest, "resource", "registered_asset_intake"),
        "registered_full_game_progress": artifact_path_string(
            manifest, "resource", "registered_full_game_progress"),
    }


def path_or_none(value: Path | None) -> Path | None:
    return value if value is not None else None


def expected_job_plan_artifacts(
    manifest: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    resource_envelope = load_artifact_json(
        manifest,
        "resource",
        "envelope",
        base_dir=base_dir,
    )
    job_specs_raw = artifact_path_string(
        manifest,
        "resource",
        "moonlab_job_specs",
    )
    job_results_raw = artifact_path_string(
        manifest,
        "resource",
        "moonlab_job_results",
    )
    job_specs_path = Path(job_specs_raw) if job_specs_raw else None
    job_results_path = Path(job_results_raw) if job_results_raw else None
    job_specs = qge_publication_pack.build_moonlab_job_specs(
        resource_envelope,
        artifact_paths_for_job_specs(manifest),
    )
    job_results = qge_moonlab_job_runner.build_moonlab_job_results(job_specs)
    replay_plan = qge_moonlab_job_runner.build_moonlab_replay_plan(
        job_specs,
        job_results,
        job_specs_path=path_or_none(job_specs_path),
        job_results_path=path_or_none(job_results_path),
    )
    submission_packet = qge_moonlab_job_runner.build_moonlab_submission_packet(
        job_specs,
        job_results,
        job_specs_path=path_or_none(job_specs_path),
        job_results_path=path_or_none(job_results_path),
    )
    return {
        "moonlab_job_specs": job_specs,
        "moonlab_job_results": job_results,
        "moonlab_replay_plan": replay_plan,
        "moonlab_submission_packet": submission_packet,
    }


def empty_audit(required: bool) -> dict[str, Any]:
    return {
        "required": required,
        "recorded": False,
        "expected_artifact_count": 4,
        "recorded_artifact_count": 0,
        "missing_artifacts": [],
        "build_errors": [],
        "job_specs_mismatches": [],
        "job_results_mismatches": [],
        "replay_plan_mismatches": [],
        "submission_packet_mismatches": [],
        "overclaim_flags": [],
        "mismatch_count": 0,
        "passed": not required,
    }


def moonlab_job_plan_audit(
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
        name: artifact_path(manifest_data, "resource", name, base_dir=base_dir)
        for name in RESOURCE_ARTIFACTS
    }
    missing_artifacts = [
        {
            "artifact": f"resource.{name}",
            "path": str(path) if path is not None else None,
        }
        for name, path in paths.items()
        if path is None or not path.is_file()
    ]
    recorded = {
        name: load_json(path)
        for name, path in paths.items()
        if name != "envelope" and path is not None and path.is_file()
    }

    build_errors: list[dict[str, str]] = []
    try:
        expected = expected_job_plan_artifacts(
            manifest_data,
            base_dir=base_dir,
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        build_errors.append({
            "artifact": "resource.moonlab_job_specs",
            "error": str(exc),
        })
        expected = {}

    job_specs_mismatches = qge_resource_boundary_audit.mismatch_paths(
        dict_or_empty(expected.get("moonlab_job_specs")),
        dict_or_empty(recorded.get("moonlab_job_specs")),
    ) if recorded.get("moonlab_job_specs") else []
    job_results_mismatches = qge_resource_boundary_audit.mismatch_paths(
        dict_or_empty(expected.get("moonlab_job_results")),
        dict_or_empty(recorded.get("moonlab_job_results")),
    ) if recorded.get("moonlab_job_results") else []
    replay_plan_mismatches = qge_resource_boundary_audit.mismatch_paths(
        dict_or_empty(expected.get("moonlab_replay_plan")),
        dict_or_empty(recorded.get("moonlab_replay_plan")),
    ) if recorded.get("moonlab_replay_plan") else []
    submission_packet_mismatches = qge_resource_boundary_audit.mismatch_paths(
        dict_or_empty(expected.get("moonlab_submission_packet")),
        dict_or_empty(recorded.get("moonlab_submission_packet")),
    ) if recorded.get("moonlab_submission_packet") else []

    overclaim_flags = []
    for name, artifact in recorded.items():
        overclaim_flags.extend(
            qge_moonlab_overclaim_audit.recursive_overclaim_flags(
                name,
                artifact,
                forbidden=JOB_PLAN_FORBIDDEN_CLAIMS,
            )
        )

    mismatch_count = (
        len(missing_artifacts) +
        len(build_errors) +
        len(job_specs_mismatches) +
        len(job_results_mismatches) +
        len(replay_plan_mismatches) +
        len(submission_packet_mismatches) +
        len(overclaim_flags)
    )
    recorded_count = sum(
        1 for name in RESOURCE_ARTIFACTS
        if name != "envelope" and dict_or_empty(recorded.get(name))
    )
    recorded_all = (
        recorded_count == 4 and
        paths.get("envelope") is not None and
        paths["envelope"].is_file()
    )
    return {
        "required": required,
        "recorded": recorded_all,
        "expected_artifact_count": 4,
        "recorded_artifact_count": recorded_count,
        "missing_artifacts": missing_artifacts,
        "build_errors": build_errors,
        "job_specs_mismatches": job_specs_mismatches,
        "job_results_mismatches": job_results_mismatches,
        "replay_plan_mismatches": replay_plan_mismatches,
        "submission_packet_mismatches": submission_packet_mismatches,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (recorded_all or not required),
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
        help="Exit nonzero when Moonlab job plan artifacts are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        manifest_path = qge_moonlab_full_game_plan.resolve_publication_manifest(
            args.pack_or_manifest)
        audit = moonlab_job_plan_audit(
            load_json(manifest_path),
            manifest_path=manifest_path,
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_MOONLAB_JOB_PLAN_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_moonlab_job_plan_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
