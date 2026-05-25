#!/usr/bin/env python3
"""Audit Moonlab full-game deployment plan rows against source ledgers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_breadth_evidence  # noqa: E402
import qge_full_game_route_contracts  # noqa: E402


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
        qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET
    )
    if not isinstance(map_set, str) or not map_set:
        map_set = qge_breadth_evidence.DEFAULT_FULL_GAME_MAP_SET
    target_maps = qge_breadth_evidence.map_targets_for_set(map_set)
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
            map_name)
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
            qge_full_game_route_contracts.route_contract_for_map(map_name)
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
