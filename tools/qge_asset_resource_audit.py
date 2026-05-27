#!/usr/bin/env python3
"""Audit packed asset resource ledgers against the manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_asset_inventory  # noqa: E402
import qge_asset_requirements  # noqa: E402
import qge_map_sets  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402
import qge_moonlab_overclaim_audit  # noqa: E402
import qge_registered_asset_intake  # noqa: E402
import qge_registered_full_game_progress  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402
import qge_resource_icc_audit  # noqa: E402


ASSET_RESOURCE_OUTPUTS = (
    "asset_inventory",
    "asset_requirements",
    "registered_asset_intake",
    "registered_full_game_progress",
    "asset_inventory_icc_evidence",
    "asset_requirements_icc_evidence",
    "registered_asset_intake_icc_evidence",
    "registered_full_game_progress_icc_evidence",
)
LEDGER_OUTPUTS = (
    "asset_inventory",
    "asset_requirements",
    "registered_asset_intake",
    "registered_full_game_progress",
)
ICC_OUTPUTS = (
    "asset_inventory_icc_evidence",
    "asset_requirements_icc_evidence",
    "registered_asset_intake_icc_evidence",
    "registered_full_game_progress_icc_evidence",
)
IGNORED_LEDGER_FIELDS = ("created_utc",)
ASSET_RESOURCE_FORBIDDEN_CLAIMS = (
    "asset_intake_copies_game_data",
    "registered_asset_payload_bundled",
    "whole_game_moonlab_deployment_claimed",
    "whole_game_hardware_execution_claimed",
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


def raw_path_or_none(value: str | None) -> Path | None:
    return Path(value) if isinstance(value, str) and value else None


def map_set_for_asset_ledgers(
    full_game_map_coverage: dict[str, Any],
    inventory: dict[str, Any],
    requirements: dict[str, Any],
    intake: dict[str, Any],
) -> str:
    for candidate in (
        full_game_map_coverage.get("map_set"),
        inventory.get("map_set"),
        requirements.get("map_set"),
        intake.get("map_set"),
    ):
        if isinstance(candidate, str) and candidate:
            return candidate
    return qge_map_sets.DEFAULT_FULL_GAME_MAP_SET


def asset_ledger_map_sets(
    full_game_map_coverage: dict[str, Any],
    inventory: dict[str, Any],
    requirements: dict[str, Any],
    intake: dict[str, Any],
) -> dict[str, str]:
    ledgers = {
        "resource.full_game_map_coverage": full_game_map_coverage,
        "resource.asset_inventory": inventory,
        "resource.asset_requirements": requirements,
        "resource.registered_asset_intake": intake,
    }
    result = {}
    for name, artifact in ledgers.items():
        value = dict_or_empty(artifact).get("map_set")
        if isinstance(value, str) and value:
            result[name] = value
    return result


def map_set_mismatches(ledger_map_sets: dict[str, str]) -> list[dict[str, str]]:
    observed = sorted(set(ledger_map_sets.values()))
    if len(observed) <= 1:
        return []
    expected = (
        ledger_map_sets.get("resource.full_game_map_coverage")
        or observed[0]
    )
    return [
        {
            "artifact": name,
            "map_set": value,
            "expected_map_set": expected,
        }
        for name, value in sorted(ledger_map_sets.items())
        if value != expected
    ]


def candidate_paths_from_intake(intake: dict[str, Any]) -> list[Path]:
    return [
        Path(value)
        for value in list_or_empty(intake.get("candidate_inputs"))
        if isinstance(value, str) and value
    ]


def expected_asset_resource_artifacts(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
) -> dict[str, dict[str, Any]]:
    base_dir = manifest_path.parent
    recorded_inventory = load_artifact_json(
        manifest, "resource", "asset_inventory", base_dir=base_dir)
    recorded_requirements = load_artifact_json(
        manifest, "resource", "asset_requirements", base_dir=base_dir)
    recorded_intake = load_artifact_json(
        manifest, "resource", "registered_asset_intake", base_dir=base_dir)
    recorded_progress = load_artifact_json(
        manifest,
        "resource",
        "registered_full_game_progress",
        base_dir=base_dir,
    )
    full_game_map_coverage = load_artifact_json(
        manifest, "resource", "full_game_map_coverage", base_dir=base_dir)
    map_set = map_set_for_asset_ledgers(
        full_game_map_coverage,
        recorded_inventory,
        recorded_requirements,
        recorded_intake,
    )
    asset_root_raw = (
        recorded_inventory.get("asset_root") or
        recorded_intake.get("current_asset_root")
    )
    asset_root = (
        Path(asset_root_raw)
        if isinstance(asset_root_raw, str) and asset_root_raw else
        qge_asset_inventory.DEFAULT_ASSET_ROOT
    )
    current_root_raw = recorded_intake.get("current_asset_root")
    current_root = (
        Path(current_root_raw)
        if isinstance(current_root_raw, str) and current_root_raw else
        asset_root
    )
    inventory = qge_asset_inventory.build_inventory(asset_root, map_set=map_set)
    requirements = qge_asset_requirements.build_requirements(
        inventory,
        map_set=map_set,
    )
    discovery = dict_or_empty(recorded_intake.get("discovery")) or None
    intake = qge_registered_asset_intake.build_intake(
        current_root,
        candidate_paths_from_intake(recorded_intake),
        map_set=map_set,
        discovery=discovery,
        publication_pack_dir=manifest_path.parent,
    )
    progress_selection_raw = recorded_progress.get("selection_file")
    progress_selection = (
        Path(progress_selection_raw)
        if isinstance(progress_selection_raw, str) and progress_selection_raw
        else qge_registered_full_game_progress.DEFAULT_SELECTION
    )
    progress_matrix_root_raw = recorded_progress.get("matrix_root")
    progress_matrix_root = (
        Path(progress_matrix_root_raw)
        if isinstance(progress_matrix_root_raw, str) and
        progress_matrix_root_raw else
        qge_registered_full_game_progress
        .qge_map_set_evidence.DEFAULT_MATRIX_ROOT
    )
    progress_asset_root_raw = recorded_progress.get("asset_root")
    progress_asset_root = (
        Path(progress_asset_root_raw)
        if isinstance(progress_asset_root_raw, str) and
        progress_asset_root_raw else
        asset_root
    )
    progress_map_set = str(
        recorded_progress.get("map_set") or
        qge_registered_full_game_progress
        .qge_map_sets.DEFAULT_FULL_GAME_MAP_SET
    )
    progress = qge_registered_full_game_progress.build_progress(
        selection_path=progress_selection,
        matrix_root=progress_matrix_root,
        asset_root=progress_asset_root,
        map_set=progress_map_set,
    )
    artifact_paths = {
        "asset_inventory": artifact_path_string(
            manifest, "resource", "asset_inventory"),
        "asset_requirements": artifact_path_string(
            manifest, "resource", "asset_requirements"),
        "registered_asset_intake": artifact_path_string(
            manifest, "resource", "registered_asset_intake"),
        "registered_full_game_progress": artifact_path_string(
            manifest, "resource", "registered_full_game_progress"),
    }
    progress_icc = qge_registered_full_game_progress.build_icc_evidence(
        progress)
    progress_path = artifact_paths.get("registered_full_game_progress")
    if isinstance(progress_path, str) and progress_path:
        progress_icc["registered_full_game_progress_file"] = progress_path
    sidecars = qge_resource_icc_audit.expected_resource_icc_sidecars(
        inventory,
        requirements,
        intake,
        artifact_paths={
            key: value
            for key, value in artifact_paths.items()
            if isinstance(value, str) and value
        },
    )
    return {
        "asset_inventory": inventory,
        "asset_requirements": requirements,
        "registered_asset_intake": intake,
        "registered_full_game_progress": progress,
        "registered_full_game_progress_icc_evidence": progress_icc,
        **sidecars,
    }


def filter_ignored_ledger_fields(fields: list[str]) -> list[str]:
    ignored = set(IGNORED_LEDGER_FIELDS)
    return [
        field for field in fields
        if field not in ignored
        and not any(field.endswith(f".{name}") for name in ignored)
    ]


def empty_audit(required: bool) -> dict[str, Any]:
    return {
        "required": required,
        "recorded": False,
        "expected_artifact_count": len(ASSET_RESOURCE_OUTPUTS),
        "recorded_artifact_count": 0,
        "missing_artifacts": [],
        "build_errors": [],
        "artifact_mismatches": [],
        "ledger_map_sets": {},
        "map_set_mismatches": [],
        "overclaim_flags": [],
        "ignored_ledger_fields": list(IGNORED_LEDGER_FIELDS),
        "mismatch_count": 0,
        "passed": not required,
    }


def asset_resource_audit(
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
        for name in ASSET_RESOURCE_OUTPUTS
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
        if path is not None and path.is_file()
    }
    full_game_map_coverage = load_artifact_json(
        manifest_data, "resource", "full_game_map_coverage", base_dir=base_dir)
    ledger_map_sets = asset_ledger_map_sets(
        full_game_map_coverage,
        dict_or_empty(recorded.get("asset_inventory")),
        dict_or_empty(recorded.get("asset_requirements")),
        dict_or_empty(recorded.get("registered_asset_intake")),
    )
    map_set_mismatch_rows = map_set_mismatches(ledger_map_sets)

    build_errors: list[dict[str, str]] = []
    try:
        expected = expected_asset_resource_artifacts(
            manifest_data,
            manifest_path=manifest_path,
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        build_errors.append({
            "artifact": "resource.asset_inventory",
            "error": str(exc),
        })
        expected = {}

    artifact_mismatches = []
    for name in ASSET_RESOURCE_OUTPUTS:
        recorded_artifact = dict_or_empty(recorded.get(name))
        if not recorded_artifact:
            continue
        fields = qge_resource_boundary_audit.mismatch_paths(
            dict_or_empty(expected.get(name)),
            recorded_artifact,
        )
        if name in LEDGER_OUTPUTS:
            fields = filter_ignored_ledger_fields(fields)
        if fields:
            artifact_mismatches.append({
                "artifact": f"resource.{name}",
                "fields": fields,
            })

    overclaim_flags = []
    for name, artifact in recorded.items():
        overclaim_flags.extend(
            qge_moonlab_overclaim_audit.recursive_overclaim_flags(
                name,
                artifact,
                forbidden=ASSET_RESOURCE_FORBIDDEN_CLAIMS,
            )
        )

    mismatch_count = (
        len(missing_artifacts) +
        len(build_errors) +
        sum(len(item["fields"]) for item in artifact_mismatches) +
        len(map_set_mismatch_rows) +
        len(overclaim_flags)
    )
    recorded_count = sum(
        1 for name in ASSET_RESOURCE_OUTPUTS
        if dict_or_empty(recorded.get(name))
    )
    recorded_all = recorded_count == len(ASSET_RESOURCE_OUTPUTS)
    return {
        "required": required,
        "recorded": recorded_all,
        "expected_artifact_count": len(ASSET_RESOURCE_OUTPUTS),
        "recorded_artifact_count": recorded_count,
        "missing_artifacts": missing_artifacts,
        "build_errors": build_errors,
        "artifact_mismatches": artifact_mismatches,
        "ledger_map_sets": ledger_map_sets,
        "map_set_mismatches": map_set_mismatch_rows,
        "overclaim_flags": overclaim_flags,
        "ignored_ledger_fields": list(IGNORED_LEDGER_FIELDS),
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
        help="Exit nonzero when asset resource ledgers are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        manifest_path = qge_moonlab_full_game_plan.resolve_publication_manifest(
            args.pack_or_manifest)
        audit = asset_resource_audit(
            load_json(manifest_path),
            manifest_path=manifest_path,
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_ASSET_RESOURCE_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_asset_resource_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
