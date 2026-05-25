#!/usr/bin/env python3
"""Audit resource ICC sidecars against their source ledgers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_asset_inventory  # noqa: E402
import qge_asset_requirements  # noqa: E402
import qge_moonlab_overclaim_audit  # noqa: E402
import qge_registered_asset_intake  # noqa: E402


ICC_EVIDENCE_SCHEMA = "qge.icc_evidence.v0"
RESOURCE_ICC_SIDECARS = (
    "asset_inventory_icc_evidence",
    "asset_requirements_icc_evidence",
    "registered_asset_intake_icc_evidence",
)
RESOURCE_SIDECAR_FORBIDDEN_CLAIMS = (
    "whole_game_moonlab_coverage_claimed",
    "whole_game_moonlab_deployment_claimed",
    "whole_game_hardware_execution_claimed",
    "hardware_quantum_advantage_claimed",
    "dense_70000_qubit_state_claimed",
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def path_or_none(value: str | None) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    return Path(value)


def compare_fields(
    expected: dict[str, Any],
    recorded: dict[str, Any],
) -> list[str]:
    return [
        field for field in expected
        if recorded.get(field) != expected.get(field)
    ]


def expected_resource_icc_sidecars(
    inventory: dict[str, Any],
    requirements: dict[str, Any],
    registered_asset_intake: dict[str, Any],
    *,
    artifact_paths: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    paths = dict_or_empty(artifact_paths)
    inventory_icc = qge_asset_inventory.build_icc_evidence(
        dict_or_empty(inventory))
    inventory_path = paths.get("asset_inventory")
    if inventory_path:
        inventory_icc["asset_inventory_file"] = inventory_path
    return {
        "asset_inventory_icc_evidence": inventory_icc,
        "asset_requirements_icc_evidence": (
            qge_asset_requirements.build_icc_evidence(
                dict_or_empty(requirements),
                out_path=path_or_none(paths.get("asset_requirements")),
            )
        ),
        "registered_asset_intake_icc_evidence": (
            qge_registered_asset_intake.build_icc_evidence(
                dict_or_empty(registered_asset_intake),
                out_path=path_or_none(paths.get("registered_asset_intake")),
            )
        ),
    }


def resource_icc_evidence_audit(
    inventory: dict[str, Any],
    requirements: dict[str, Any],
    registered_asset_intake: dict[str, Any] | None = None,
    resource_icc_evidence: dict[str, Any] | None = None,
    *,
    artifact_paths: dict[str, str] | None = None,
    required: bool = False,
) -> dict[str, Any]:
    recorded_sidecars = dict_or_empty(resource_icc_evidence)
    expected_sidecars = expected_resource_icc_sidecars(
        inventory,
        requirements,
        dict_or_empty(registered_asset_intake),
        artifact_paths=artifact_paths,
    )
    active = required or bool(recorded_sidecars)
    missing_sidecars = [
        name for name in RESOURCE_ICC_SIDECARS
        if not dict_or_empty(recorded_sidecars.get(name))
    ] if active else []
    schema_mismatches = []
    sidecar_mismatches = []
    overclaim_flags = []
    for name in RESOURCE_ICC_SIDECARS:
        recorded = dict_or_empty(recorded_sidecars.get(name))
        if not recorded:
            continue
        expected = expected_sidecars[name]
        if recorded.get("schema") != ICC_EVIDENCE_SCHEMA:
            schema_mismatches.append(name)
        fields = compare_fields(expected, recorded)
        if fields:
            sidecar_mismatches.append({
                "sidecar": name,
                "fields": fields,
            })
        overclaim_flags.extend(
            qge_moonlab_overclaim_audit.recursive_overclaim_flags(
                name,
                recorded,
                forbidden=RESOURCE_SIDECAR_FORBIDDEN_CLAIMS,
            )
        )

    mismatch_count = (
        len(missing_sidecars) +
        len(overclaim_flags) +
        sum(len(item["fields"]) for item in sidecar_mismatches)
    )
    recorded_count = sum(
        1 for name in RESOURCE_ICC_SIDECARS
        if dict_or_empty(recorded_sidecars.get(name))
    )
    recorded = recorded_count == len(RESOURCE_ICC_SIDECARS)
    passed = mismatch_count == 0 and (recorded or not required)
    return {
        "required": required,
        "recorded": recorded,
        "expected_sidecar_count": len(RESOURCE_ICC_SIDECARS),
        "recorded_sidecar_count": recorded_count,
        "missing_sidecars": missing_sidecars,
        "schema_mismatches": schema_mismatches,
        "sidecar_mismatches": sidecar_mismatches,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": passed,
    }
