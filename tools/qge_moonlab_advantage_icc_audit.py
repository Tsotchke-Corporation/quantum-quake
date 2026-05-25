#!/usr/bin/env python3
"""Audit Moonlab advantage ICC sidecars against source artifacts."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_advantage_benchmark  # noqa: E402
import qge_moonlab_overclaim_audit  # noqa: E402
import qge_moonlab_oracle_transpile  # noqa: E402
import qge_moonlab_qae_grover_plan  # noqa: E402
import qge_moonlab_qae_observation_transpile  # noqa: E402
import qge_moonlab_qae_transpile  # noqa: E402


ICC_EVIDENCE_SCHEMA = "qge.icc_evidence.v0"
ADVANTAGE_ICC_SIDECARS = (
    "advantage_icc_evidence",
    "qae_moonlab_payload_icc_evidence",
    "qae_moonlab_oracle_kernel_icc_evidence",
    "qae_moonlab_observation_zero_icc_evidence",
    "qae_moonlab_grover_schedule_plan_icc_evidence",
)
ADVANTAGE_SIDECAR_FORBIDDEN_CLAIMS = (
    "whole_game_moonlab_deployment_claimed",
    "whole_game_hardware_execution_claimed",
    "hardware_result_claimed",
    "hardware_quantum_advantage_claimed",
    "dense_70000_qubit_state_claimed",
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def path_or_none(value: str | None) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    return Path(value)


def path_or_empty(value: str | None) -> Path:
    return path_or_none(value) or Path("")


def compare_fields(
    expected: dict[str, Any],
    recorded: dict[str, Any],
) -> list[str]:
    return [
        field for field in expected
        if recorded.get(field) != expected.get(field)
    ]


def expected_advantage_icc_sidecars(
    advantage_artifacts: dict[str, Any],
    *,
    artifact_paths: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    artifacts = dict_or_empty(advantage_artifacts)
    paths = dict_or_empty(artifact_paths)
    return {
        "advantage_icc_evidence": (
            qge_advantage_benchmark.build_icc_evidence(
                dict_or_empty(artifacts.get("advantage_metrics")),
                path_or_empty(paths.get("advantage_metrics")),
                path_or_empty(paths.get("qae_curve")),
                path_or_empty(paths.get("qae_circuit")),
                path_or_empty(paths.get("scaling_summary")),
            )
        ),
        "qae_moonlab_payload_icc_evidence": (
            qge_moonlab_qae_transpile.build_icc_evidence(
                dict_or_empty(artifacts.get("qae_moonlab_payload")),
                out_path=path_or_none(paths.get("qae_moonlab_payload")),
            )
        ),
        "qae_moonlab_oracle_kernel_icc_evidence": (
            qge_moonlab_oracle_transpile.build_icc_evidence(
                dict_or_empty(artifacts.get("qae_moonlab_oracle_kernel")),
                out_path=path_or_none(paths.get("qae_moonlab_oracle_kernel")),
            )
        ),
        "qae_moonlab_observation_zero_icc_evidence": (
            qge_moonlab_qae_observation_transpile.build_icc_evidence(
                dict_or_empty(artifacts.get("qae_moonlab_observation_zero")),
                out_path=path_or_none(
                    paths.get("qae_moonlab_observation_zero")),
            )
        ),
        "qae_moonlab_grover_schedule_plan_icc_evidence": (
            qge_moonlab_qae_grover_plan.build_icc_evidence(
                dict_or_empty(
                    artifacts.get("qae_moonlab_grover_schedule_plan")),
                out_path=path_or_none(
                    paths.get("qae_moonlab_grover_schedule_plan")),
            )
        ),
    }


def empty_audit(required: bool) -> dict[str, Any]:
    return {
        "required": required,
        "recorded": False,
        "expected_sidecar_count": len(ADVANTAGE_ICC_SIDECARS),
        "recorded_sidecar_count": 0,
        "missing_sidecars": [],
        "schema_mismatches": [],
        "sidecar_mismatches": [],
        "sidecar_build_errors": [],
        "overclaim_flags": [],
        "mismatch_count": 0,
        "passed": not required,
    }


def advantage_icc_evidence_audit(
    advantage_artifacts: dict[str, Any] | None = None,
    advantage_icc_evidence: dict[str, Any] | None = None,
    *,
    artifact_paths: dict[str, str] | None = None,
    required: bool = False,
) -> dict[str, Any]:
    recorded_sidecars = dict_or_empty(advantage_icc_evidence)
    active = required or bool(recorded_sidecars)
    if not active:
        return empty_audit(required)

    missing_sidecars = [
        name for name in ADVANTAGE_ICC_SIDECARS
        if not dict_or_empty(recorded_sidecars.get(name))
    ]
    build_errors: list[dict[str, str]] = []
    try:
        expected_sidecars = expected_advantage_icc_sidecars(
            dict_or_empty(advantage_artifacts),
            artifact_paths=artifact_paths,
        )
    except (KeyError, TypeError, ValueError) as exc:
        build_errors.append({
            "sidecar": "advantage_icc_evidence",
            "error": str(exc),
        })
        expected_sidecars = {}

    schema_mismatches = []
    sidecar_mismatches = []
    overclaim_flags = []
    for name in ADVANTAGE_ICC_SIDECARS:
        recorded = dict_or_empty(recorded_sidecars.get(name))
        if not recorded:
            continue
        expected = dict_or_empty(expected_sidecars.get(name))
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
                forbidden=ADVANTAGE_SIDECAR_FORBIDDEN_CLAIMS,
            )
        )

    mismatch_count = (
        len(missing_sidecars) +
        len(build_errors) +
        len(overclaim_flags) +
        sum(len(item["fields"]) for item in sidecar_mismatches)
    )
    recorded_count = sum(
        1 for name in ADVANTAGE_ICC_SIDECARS
        if dict_or_empty(recorded_sidecars.get(name))
    )
    recorded = recorded_count == len(ADVANTAGE_ICC_SIDECARS)
    passed = mismatch_count == 0 and (recorded or not required)
    return {
        "required": required,
        "recorded": recorded,
        "expected_sidecar_count": len(ADVANTAGE_ICC_SIDECARS),
        "recorded_sidecar_count": recorded_count,
        "missing_sidecars": missing_sidecars,
        "schema_mismatches": schema_mismatches,
        "sidecar_mismatches": sidecar_mismatches,
        "sidecar_build_errors": build_errors,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": passed,
    }
