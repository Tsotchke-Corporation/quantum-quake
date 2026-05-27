#!/usr/bin/env python3
"""Audit Moonlab full-game deployment plan rows against source ledgers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_full_game_route_contracts  # noqa: E402
import qge_map_sets  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402
import qge_moonlab_overclaim_audit  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402


FULL_GAME_PLAN_SCHEMA = "qge.moonlab_full_game_deployment_plan.v0"
ICC_EVIDENCE_SCHEMA = "qge.icc_evidence.v0"
IGNORED_PLAN_FIELDS = ("created_utc", "source_path")
SOURCE_ARTIFACTS = (
    ("breadth", "evidence"),
    ("resource", "full_game_map_coverage"),
    ("resource", "asset_inventory"),
    ("resource", "moonlab_job_results"),
    ("resource", "moonlab_submission_packet"),
    ("resource", "moonlab_hardware_record_template"),
    ("resource", "registered_asset_intake"),
)
PLAN_OUTPUTS = (
    "moonlab_full_game_plan",
    "moonlab_full_game_plan_icc_evidence",
)
FULL_GAME_PLAN_FORBIDDEN_CLAIMS = (
    "whole_game_moonlab_deployment_claimed",
    "whole_game_hardware_execution_claimed",
    "hardware_quantum_advantage_claimed",
    "dense_70000_qubit_state_claimed",
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def string_list(value: Any) -> list[str]:
    return [item for item in list_or_empty(value) if isinstance(item, str)]


def int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


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


def comparable_plan(plan: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(plan)
    for field in IGNORED_PLAN_FIELDS:
        normalized.pop(field, None)
    return normalized


def expected_full_game_plan_artifacts(
    manifest: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    coverage = load_artifact_json(
        manifest,
        "resource",
        "full_game_map_coverage",
        base_dir=base_dir,
    )
    inventory = load_artifact_json(
        manifest,
        "resource",
        "asset_inventory",
        base_dir=base_dir,
    )
    plan = qge_moonlab_full_game_plan.build_plan(
        coverage,
        inventory,
        source_path=artifact_path_string(
            manifest, "resource", "moonlab_full_game_plan"),
        breadth_evidence=load_artifact_json(
            manifest, "breadth", "evidence", base_dir=base_dir),
        moonlab_job_results=load_artifact_json(
            manifest, "resource", "moonlab_job_results", base_dir=base_dir),
        submission_packet=load_artifact_json(
            manifest,
            "resource",
            "moonlab_submission_packet",
            base_dir=base_dir,
        ),
        hardware_record_template=load_artifact_json(
            manifest,
            "resource",
            "moonlab_hardware_record_template",
            base_dir=base_dir,
        ),
        registered_asset_intake=load_artifact_json(
            manifest,
            "resource",
            "registered_asset_intake",
            base_dir=base_dir,
        ),
    )
    plan_icc = qge_moonlab_full_game_plan.build_icc_evidence(
        plan,
        out_path=raw_path_or_none(artifact_path_string(
            manifest,
            "resource",
            "moonlab_full_game_plan",
        )),
    )
    return {
        "moonlab_full_game_plan": plan,
        "moonlab_full_game_plan_icc_evidence": plan_icc,
    }


def duplicate_strings(values: Sequence[str]) -> list[str]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted(value for value, count in counts.items() if count > 1)


def expected_plan_status(
    coverage: dict[str, Any],
    expected_capture_required_maps: Sequence[str],
    expected_asset_unavailable_maps: Sequence[str],
) -> str:
    if not qge_map_sets.is_registered_full_game_map_set(
        coverage.get("map_set")
    ):
        return "blocked_non_registered_map_set"
    if coverage.get("status") == "complete":
        return "map_coverage_complete"
    if expected_asset_unavailable_maps:
        return "blocked_asset_unavailable"
    if expected_capture_required_maps:
        return "captures_required"
    return "partial_unknown"


def indexed_plan_rows(
    full_game_plan: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[str], int]:
    rows = [
        item for item in list_or_empty(full_game_plan.get(
            "map_deployment_rows"))
        if isinstance(item, dict)
    ]
    row_maps = [
        item.get("map") for item in rows
        if isinstance(item.get("map"), str) and item.get("map")
    ]
    row_index = {
        map_name: row
        for map_name, row in (
            (row.get("map"), row) for row in rows
        )
        if isinstance(map_name, str) and map_name
    }
    invalid_row_count = len(rows) - len(row_maps)
    return rows, row_index, row_maps, invalid_row_count


def full_game_plan_ledger_audit(
    coverage: dict[str, Any],
    inventory: dict[str, Any],
    full_game_plan: dict[str, Any],
) -> dict[str, Any]:
    map_set = (
        coverage.get("map_set") or
        inventory.get("map_set") or
        full_game_plan.get("map_set") or
        qge_map_sets.DEFAULT_FULL_GAME_MAP_SET
    )
    if not isinstance(map_set, str) or not map_set:
        map_set = qge_map_sets.DEFAULT_FULL_GAME_MAP_SET
    target_maps = qge_map_sets.map_targets_for_set(map_set)
    target_set = set(target_maps)
    covered_maps = set(string_list(coverage.get("covered_maps")))
    available_maps = set(string_list(inventory.get("available_maps")))
    rows, row_index, row_maps, invalid_row_count = indexed_plan_rows(
        full_game_plan)
    duplicate_row_maps = duplicate_strings(row_maps)
    row_set = set(row_maps)
    missing_row_maps = sorted(target_set - row_set)
    unexpected_row_maps = sorted(row_set - target_set)
    expected_capture_required_maps = [
        map_name for map_name in target_maps
        if map_name not in covered_maps and map_name in available_maps
    ]
    expected_asset_unavailable_maps = [
        map_name for map_name in target_maps
        if map_name not in covered_maps and map_name not in available_maps
    ]
    expected_status = expected_plan_status(
        coverage,
        expected_capture_required_maps,
        expected_asset_unavailable_maps,
    )

    top_level_mismatches = []
    scalar_pairs = [
        ("status", full_game_plan.get("status"), expected_status),
        ("map_set", full_game_plan.get("map_set"), map_set),
        (
            "target_map_count",
            full_game_plan.get("target_map_count"),
            coverage.get("target_map_count"),
        ),
        (
            "covered_map_count",
            full_game_plan.get("covered_map_count"),
            coverage.get("covered_map_count"),
        ),
        (
            "missing_map_count",
            full_game_plan.get("missing_map_count"),
            coverage.get("missing_map_count"),
        ),
        (
            "asset_available_map_count",
            full_game_plan.get("asset_available_map_count"),
            inventory.get("available_map_count"),
        ),
        (
            "asset_missing_map_count",
            full_game_plan.get("asset_missing_map_count"),
            inventory.get("missing_map_count"),
        ),
        (
            "capture_required_map_count",
            full_game_plan.get("capture_required_map_count"),
            len(expected_capture_required_maps),
        ),
        (
            "asset_unavailable_map_count",
            full_game_plan.get("asset_unavailable_map_count"),
            len(expected_asset_unavailable_maps),
        ),
    ]
    for label, recorded, expected in scalar_pairs:
        if expected is not None and recorded != expected:
            top_level_mismatches.append(label)
    list_pairs = [
        (
            "capture_required_maps",
            full_game_plan.get("capture_required_maps"),
            expected_capture_required_maps,
        ),
        (
            "asset_unavailable_maps",
            full_game_plan.get("asset_unavailable_maps"),
            expected_asset_unavailable_maps,
        ),
    ]
    for label, recorded, expected in list_pairs:
        if string_list(recorded) != list(expected):
            top_level_mismatches.append(label)

    row_mismatches = []
    route_contract_mismatch_maps = []
    for map_name in target_maps:
        row = row_index.get(map_name)
        if not row:
            continue
        expected_coverage_status = (
            "covered" if map_name in covered_maps else "missing")
        expected_asset_status = (
            "available" if map_name in available_maps
            else "asset_unavailable"
        )
        if map_name in covered_maps:
            expected_deployment_status = (
                "simulator_native_evidence_present")
        elif map_name in available_maps:
            expected_deployment_status = "capture_required"
        else:
            expected_deployment_status = "blocked_asset_unavailable"
        expected_contract = qge_full_game_route_contracts.route_contract_for_map(
            map_name,
            map_set=map_set,
        )
        expected_pairs = [
            ("coverage_status", expected_coverage_status),
            ("asset_status", expected_asset_status),
            ("deployment_status", expected_deployment_status),
            ("route_profile", expected_contract.get("route_profile")),
        ]
        for label, expected in expected_pairs:
            if row.get(label) != expected:
                row_mismatches.append(f"{map_name}:{label}")
        if dict_or_empty(row.get("route_contract")) != expected_contract:
            route_contract_mismatch_maps.append(map_name)

    route_contracts = dict_or_empty(full_game_plan.get("route_contracts"))
    route_contract_entry_maps = {
        key for key in route_contracts.keys() if isinstance(key, str) and key
    }
    missing_route_contract_entry_maps = sorted(
        target_set - route_contract_entry_maps)
    unexpected_route_contract_entry_maps = sorted(
        route_contract_entry_maps - target_set)
    route_contract_entry_mismatch_maps = []
    for map_name in target_maps:
        if (
            map_name in route_contracts and
            dict_or_empty(route_contracts.get(map_name)) !=
            qge_full_game_route_contracts.route_contract_for_map(
                map_name,
                map_set=map_set,
            )
        ):
            route_contract_entry_mismatch_maps.append(map_name)
    route_contract_mismatch_maps = sorted(set(
        route_contract_mismatch_maps +
        route_contract_entry_mismatch_maps
    ))
    route_contract_count = int_or_none(full_game_plan.get(
        "route_contract_map_count"))
    if route_contract_count != len(target_maps):
        top_level_mismatches.append("route_contract_map_count")
    if full_game_plan.get("route_contracts_complete") is not True:
        top_level_mismatches.append("route_contracts_complete")
    if string_list(full_game_plan.get("missing_route_contract_maps")) != []:
        top_level_mismatches.append("missing_route_contract_maps")

    mismatch_count = (
        len(top_level_mismatches) +
        len(missing_row_maps) +
        len(unexpected_row_maps) +
        len(duplicate_row_maps) +
        invalid_row_count +
        len(row_mismatches) +
        len(route_contract_mismatch_maps) +
        len(missing_route_contract_entry_maps) +
        len(unexpected_route_contract_entry_maps)
    )
    recorded = (
        full_game_plan.get("schema") ==
        "qge.moonlab_full_game_deployment_plan.v0" and
        bool(rows)
    )
    return {
        "recorded": recorded,
        "map_set": map_set,
        "expected_row_count": len(target_maps),
        "row_count": len(rows),
        "invalid_row_count": invalid_row_count,
        "duplicate_row_maps": duplicate_row_maps,
        "missing_row_maps": missing_row_maps,
        "unexpected_row_maps": unexpected_row_maps,
        "expected_status": expected_status,
        "recorded_status": full_game_plan.get("status"),
        "expected_capture_required_maps": expected_capture_required_maps,
        "expected_asset_unavailable_maps": expected_asset_unavailable_maps,
        "top_level_mismatches": sorted(set(top_level_mismatches)),
        "row_mismatches": sorted(row_mismatches),
        "route_contract_mismatch_maps": route_contract_mismatch_maps,
        "missing_route_contract_entry_maps": (
            missing_route_contract_entry_maps),
        "unexpected_route_contract_entry_maps": (
            unexpected_route_contract_entry_maps),
        "mismatch_count": mismatch_count,
        "passed": recorded and mismatch_count == 0,
    }


def empty_artifact_audit(required: bool) -> dict[str, Any]:
    return {
        "required": required,
        "recorded": False,
        "expected_artifact_count": len(PLAN_OUTPUTS),
        "recorded_artifact_count": 0,
        "missing_artifacts": [],
        "build_errors": [],
        "plan_schema_mismatch": False,
        "icc_schema_mismatch": False,
        "plan_mismatches": [],
        "icc_mismatches": [],
        "overclaim_flags": [],
        "mismatch_count": 0,
        "passed": not required,
    }


def full_game_plan_artifact_audit(
    manifest: dict[str, Any] | None,
    *,
    manifest_path: Path,
    required: bool = True,
) -> dict[str, Any]:
    manifest_data = dict_or_empty(manifest)
    base_dir = manifest_path.parent
    active = required or bool(manifest_data)
    if not active:
        return empty_artifact_audit(required)

    source_paths = {
        f"{section}.{name}": artifact_path(
            manifest_data,
            section,
            name,
            base_dir=base_dir,
        )
        for section, name in SOURCE_ARTIFACTS
    }
    output_paths = {
        name: artifact_path(
            manifest_data,
            "resource",
            name,
            base_dir=base_dir,
        )
        for name in PLAN_OUTPUTS
    }
    missing_artifacts = [
        {
            "artifact": label,
            "path": str(path) if path is not None else None,
        }
        for label, path in source_paths.items()
        if path is None or not path.is_file()
    ]
    missing_artifacts.extend([
        {
            "artifact": f"resource.{name}",
            "path": str(path) if path is not None else None,
        }
        for name, path in output_paths.items()
        if path is None or not path.is_file()
    ])

    recorded_plan = (
        load_json(output_paths["moonlab_full_game_plan"])
        if output_paths["moonlab_full_game_plan"] is not None and
        output_paths["moonlab_full_game_plan"].is_file()
        else {}
    )
    recorded_icc = (
        load_json(output_paths["moonlab_full_game_plan_icc_evidence"])
        if output_paths["moonlab_full_game_plan_icc_evidence"] is not None and
        output_paths["moonlab_full_game_plan_icc_evidence"].is_file()
        else {}
    )
    recorded = {
        "moonlab_full_game_plan": recorded_plan,
        "moonlab_full_game_plan_icc_evidence": recorded_icc,
    }

    build_errors: list[dict[str, str]] = []
    try:
        expected = expected_full_game_plan_artifacts(
            manifest_data,
            base_dir=base_dir,
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        build_errors.append({
            "artifact": "resource.moonlab_full_game_plan",
            "error": str(exc),
        })
        expected = {}

    plan_mismatches = (
        qge_resource_boundary_audit.mismatch_paths(
            comparable_plan(dict_or_empty(
                expected.get("moonlab_full_game_plan"))),
            comparable_plan(recorded_plan),
        )
        if recorded_plan else []
    )
    icc_mismatches = (
        qge_resource_boundary_audit.mismatch_paths(
            dict_or_empty(
                expected.get("moonlab_full_game_plan_icc_evidence")),
            recorded_icc,
        )
        if recorded_icc else []
    )
    overclaim_flags = []
    for name, artifact in recorded.items():
        overclaim_flags.extend(
            qge_moonlab_overclaim_audit.recursive_overclaim_flags(
                name,
                artifact,
                forbidden=FULL_GAME_PLAN_FORBIDDEN_CLAIMS,
            )
        )

    recorded_count = sum(
        1 for name in PLAN_OUTPUTS if dict_or_empty(recorded.get(name))
    )
    mismatch_count = (
        len(missing_artifacts) +
        len(build_errors) +
        len(plan_mismatches) +
        len(icc_mismatches) +
        len(overclaim_flags)
    )
    return {
        "required": required,
        "recorded": recorded_count == len(PLAN_OUTPUTS),
        "expected_artifact_count": len(PLAN_OUTPUTS),
        "recorded_artifact_count": recorded_count,
        "missing_artifacts": missing_artifacts,
        "build_errors": build_errors,
        "plan_schema_mismatch": (
            bool(recorded_plan) and
            recorded_plan.get("schema") != FULL_GAME_PLAN_SCHEMA),
        "icc_schema_mismatch": (
            bool(recorded_icc) and
            recorded_icc.get("schema") != ICC_EVIDENCE_SCHEMA),
        "ignored_plan_fields": list(IGNORED_PLAN_FIELDS),
        "plan_mismatches": plan_mismatches,
        "icc_mismatches": icc_mismatches,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": (
            mismatch_count == 0 and
            (recorded_count == len(PLAN_OUTPUTS) or not required)
        ),
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
        help="Exit nonzero when Moonlab full-game plan artifacts are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        manifest_path = qge_moonlab_full_game_plan.resolve_publication_manifest(
            args.pack_or_manifest)
        audit = full_game_plan_artifact_audit(
            load_json(manifest_path),
            manifest_path=manifest_path,
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_MOONLAB_FULL_GAME_PLAN_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_moonlab_full_game_plan_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
