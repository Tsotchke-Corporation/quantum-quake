#!/usr/bin/env python3
"""Fail-closed gate for bounded QAE query-scaling advantage evidence.

This gate does not claim whole-game hardware execution or practical hardware
speedup. It only allows the bounded
``advantage.light_transport_qae_query_scaling`` claim after a real Moonlab
hardware result has been ingested, compared with simulator evidence, and
checked against the declared classical baselines.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_moonlab_hardware_result_audit  # noqa: E402


CLAIM_ID = "advantage.light_transport_qae_query_scaling"
CLAIM_SCOPE_MARKER_NAME = (
    "qge_hardware_advantage_claim_scope_"
    "advantage.light_transport_qae_query_scaling.json"
)
FORBIDDEN_CLAIM_FLAGS = (
    "hardware_quantum_advantage_claimed",
    "whole_game_hardware_execution_claimed",
    "dense_70000_qubit_state_claimed",
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def load_optional_gate_json(path: Path, label: str) -> dict[str, Any]:
    try:
        return load_json(path)
    except (OSError, ValueError) as exc:
        return {
            "schema": "qge.missing_gate_input.v0",
            "artifact": label,
            "path": str(path),
            "load_error": str(exc),
        }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float)) and
        not isinstance(value, bool) and
        math.isfinite(float(value))
    )


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def hex_digest(value: Any) -> bool:
    return (
        isinstance(value, str) and
        len(value) == 64 and
        all(char in "0123456789abcdef" for char in value.lower())
    )


def check(
    check_id: str,
    passed: bool,
    evidence: Any,
    blocker: str,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "pass" if passed else "blocked",
        "passed": bool(passed),
        "evidence": evidence,
        "blocker": "" if passed else blocker,
    }


def algorithms(records: list[Any]) -> set[str]:
    return {
        str(item.get("algorithm"))
        for item in records
        if isinstance(item, dict) and item.get("algorithm")
    }


def best_record(metrics: dict[str, Any], name: str) -> dict[str, Any]:
    return dict_or_empty(dict_or_empty(metrics.get("comparison")).get(name))


def slope(metrics: dict[str, Any], name: str) -> float | None:
    value = dict_or_empty(metrics.get("comparison")).get(name)
    return float(value) if finite_number(value) else None


def no_forbidden_claims(record: dict[str, Any]) -> bool:
    return not any(bool(record.get(flag)) for flag in FORBIDDEN_CLAIM_FLAGS)


def claim_policy_status(claims: dict[str, Any]) -> dict[str, Any]:
    for claim in list_or_empty(claims.get("claims")):
        if not isinstance(claim, dict) or claim.get("claim_id") != CLAIM_ID:
            continue
        return {
            "found": True,
            "claim_type": claim.get("claim_type"),
            "status": claim.get("status"),
            "disallowed_wording": claim.get("disallowed_wording"),
        }
    return {"found": False}


def job_by_id(job_results: dict[str, Any], job_id: str | None) -> dict[str, Any]:
    for job in list_or_empty(job_results.get("jobs")):
        if isinstance(job, dict) and job.get("job_id") == job_id:
            return job
    return {}


def hardware_audit_passed(audit: dict[str, Any]) -> bool:
    return (
        audit.get("passed") is True and
        audit.get("strict_real_campaign") is True and
        positive_int(audit.get("hardware_result_job_count")) and
        positive_int(audit.get("completed_hardware_result_count")) and
        list_or_empty(audit.get("strict_real_campaign_mismatches")) == []
    )


def build_gate(
    advantage_metrics: dict[str, Any],
    job_results: dict[str, Any],
    hardware_comparison: dict[str, Any],
    hardware_result_audit: dict[str, Any],
    advantage_metrics_audit: dict[str, Any] | None = None,
    claims: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = dict_or_empty(advantage_metrics)
    results = dict_or_empty(job_results)
    comparison = dict_or_empty(hardware_comparison)
    audit = dict_or_empty(hardware_result_audit)
    metrics_audit = dict_or_empty(advantage_metrics_audit)
    policy = claim_policy_status(dict_or_empty(claims))

    claim_posture = dict_or_empty(metrics.get("claim_posture"))
    oracle = dict_or_empty(metrics.get("oracle"))
    comparison_summary = dict_or_empty(metrics.get("comparison"))
    best_classical = best_record(metrics, "best_classical")
    best_qae = best_record(metrics, "best_qae")
    qae_slope = slope(metrics, "qae_loglog_delta_slope")
    mc_slope = slope(metrics, "mc_loglog_delta_slope")
    stratified_slope = slope(metrics, "stratified_loglog_delta_slope")
    baseline_algorithms = algorithms(list_or_empty(
        metrics.get("classical_baselines")))
    comparison_job = job_by_id(results, comparison.get("job_id"))
    comparison_claim_posture = dict_or_empty(comparison.get("claim_posture"))
    job_observations = dict_or_empty(comparison_job.get("observations"))
    hardware_rows = [
        row for row in list_or_empty(comparison_job.get("backend_results"))
        if isinstance(row, dict) and
        row.get("backend_kind") == "moonlab_hardware"
    ]
    comparison_row = next(
        (
            row for row in hardware_rows
            if row.get("hardware_record_sha256") ==
            comparison.get("hardware_record_sha256")
        ),
        {},
    )

    criteria = [
        check(
            "claim_policy_present",
            policy.get("found") is True,
            policy,
            "claims ledger does not contain the bounded QAE query-scaling claim",
        ),
        check(
            "claim_scope",
            claim_posture.get("claim_id") == CLAIM_ID and
            str(metrics.get("advantage_problem_id", "")).startswith(CLAIM_ID),
            {
                "claim_posture_claim_id": claim_posture.get("claim_id"),
                "advantage_problem_id": metrics.get("advantage_problem_id"),
            },
            "advantage metrics are not scoped to the bounded QAE claim",
        ),
        check(
            "explicit_oracle_model",
            nonempty_string(oracle.get("implementation_status")) and
            nonempty_string(oracle.get("readout_model")) and
            nonempty_string(oracle.get("qram_assumption")) and
            positive_int(oracle.get("state_prep_cost")),
            {
                "implementation_status": oracle.get("implementation_status"),
                "readout_model": oracle.get("readout_model"),
                "qram_assumption": oracle.get("qram_assumption"),
                "state_prep_cost": oracle.get("state_prep_cost"),
            },
            "advantage metrics omit oracle/readout/state-prep assumptions",
        ),
        check(
            "advantage_metrics_audit",
            metrics_audit.get("passed") is True and
            metrics_audit.get("recorded") is True and
            metrics_audit.get("mismatch_count") == 0 and
            list_or_empty(metrics_audit.get("missing_artifacts")) == [] and
            list_or_empty(metrics_audit.get("build_errors")) == [] and
            list_or_empty(metrics_audit.get("overclaim_flags")) == [],
            {
                "passed": metrics_audit.get("passed"),
                "recorded": metrics_audit.get("recorded"),
                "mismatch_count": metrics_audit.get("mismatch_count"),
                "missing_artifacts": metrics_audit.get("missing_artifacts"),
                "build_errors": metrics_audit.get("build_errors"),
                "overclaim_flags": metrics_audit.get("overclaim_flags"),
            },
            "advantage metrics reproducibility/ICC/overclaim audit has not passed",
        ),
        check(
            "strong_classical_baselines",
            {"classical_mc", "stratified_vdc"}.issubset(
                baseline_algorithms) and
            positive_int(best_classical.get("trial_count")) and
            int(best_classical.get("trial_count")) >= 3 and
            finite_number(best_classical.get("rmse")),
            {
                "algorithms": sorted(baseline_algorithms),
                "best_classical": best_classical,
            },
            "classical baseline evidence is missing MC/stratified coverage",
        ),
        check(
            "qae_scaling_evidence",
            positive_int(best_qae.get("trial_count")) and
            int(best_qae.get("trial_count")) >= 3 and
            finite_number(best_qae.get("rmse")) and
            qae_slope is not None and
            mc_slope is not None and
            stratified_slope is not None and
            qae_slope < mc_slope and
            qae_slope < stratified_slope,
            {
                "best_qae": best_qae,
                "qae_loglog_delta_slope": qae_slope,
                "mc_loglog_delta_slope": mc_slope,
                "stratified_loglog_delta_slope": stratified_slope,
            },
            "QAE query-scaling evidence is not stronger than the baselines",
        ),
        check(
            "strict_hardware_result_audit",
            hardware_audit_passed(audit),
            {
                "passed": audit.get("passed"),
                "strict_real_campaign": audit.get("strict_real_campaign"),
                "hardware_result_job_count": audit.get(
                    "hardware_result_job_count"),
                "completed_hardware_result_count": audit.get(
                    "completed_hardware_result_count"),
                "strict_real_campaign_mismatches": audit.get(
                    "strict_real_campaign_mismatches"),
            },
            "strict hardware-result audit has not passed",
        ),
        check(
            "hardware_comparison_recorded",
            comparison.get("schema") == "qge.moonlab_hardware_comparison.v0" and
            comparison.get("status") == "hardware_result_recorded" and
            comparison.get("backend_kind") == "moonlab_hardware" and
            hex_digest(comparison.get("hardware_record_sha256")) and
            comparison_claim_posture.get(
                "bounded_hardware_job_result_recorded") is True and
            no_forbidden_claims(comparison_claim_posture),
            {
                "schema": comparison.get("schema"),
                "status": comparison.get("status"),
                "backend_kind": comparison.get("backend_kind"),
                "hardware_record_sha256": comparison.get(
                    "hardware_record_sha256"),
                "claim_posture": comparison_claim_posture,
            },
            "hardware-vs-simulator comparison is missing or overclaiming",
        ),
        check(
            "hardware_comparison_matches_audited_row",
            comparison.get("job_id") in set(list_or_empty(
                audit.get("hardware_result_job_ids"))) and
            comparison_row.get("candidate_digest") ==
            comparison.get("candidate_digest") and
            comparison_row.get("backend_id") == comparison.get("backend_id") and
            comparison_row.get("hardware_record_sha256") ==
            comparison.get("hardware_record_sha256") and
            dict_or_empty(comparison_row.get("observations")) ==
            dict_or_empty(comparison.get("hardware_observations")),
            {
                "comparison_job_id": comparison.get("job_id"),
                "audited_job_ids": audit.get("hardware_result_job_ids"),
                "comparison_candidate_digest": comparison.get(
                    "candidate_digest"),
                "row_candidate_digest": comparison_row.get(
                    "candidate_digest"),
                "comparison_backend_id": comparison.get("backend_id"),
                "row_backend_id": comparison_row.get("backend_id"),
                "comparison_hardware_record_sha256": comparison.get(
                    "hardware_record_sha256"),
                "row_hardware_record_sha256": comparison_row.get(
                    "hardware_record_sha256"),
            },
            "hardware comparison does not match the audited Moonlab backend row",
        ),
        check(
            "job_results_hardware_counts",
            positive_int(results.get("hardware_submitted_job_count")) and
            positive_int(results.get("completed_hardware_job_count")) and
            results.get("overall_status") ==
            "simulator_complete_hardware_recorded",
            {
                "overall_status": results.get("overall_status"),
                "hardware_submitted_job_count": results.get(
                    "hardware_submitted_job_count"),
                "completed_hardware_job_count": results.get(
                    "completed_hardware_job_count"),
            },
            "job results do not record completed Moonlab hardware output",
        ),
        check(
            "hardware_job_matches_advantage_problem",
            comparison_job.get("domain") == "light_transport_qae_benchmark" and
            job_observations.get("advantage_problem_id") ==
            metrics.get("advantage_problem_id") and
            best_qae.get("oracle_eval_count") ==
            job_observations.get("oracle_eval_count") and
            best_qae.get("shots") == job_observations.get("shots"),
            {
                "comparison_job_id": comparison.get("job_id"),
                "comparison_job_domain": comparison_job.get("domain"),
                "job_advantage_problem_id": job_observations.get(
                    "advantage_problem_id"),
                "metrics_advantage_problem_id": metrics.get(
                    "advantage_problem_id"),
                "job_oracle_eval_count": job_observations.get(
                    "oracle_eval_count"),
                "best_qae_oracle_eval_count": best_qae.get(
                    "oracle_eval_count"),
                "job_shots": job_observations.get("shots"),
                "best_qae_shots": best_qae.get("shots"),
            },
            "hardware comparison is not tied to the QAE benchmark job",
        ),
    ]

    failed = [item for item in criteria if not item["passed"]]
    ready = not failed
    return {
        "schema": "qge.hardware_advantage_gate.v0",
        "runtime_backend": "qge_hardware_advantage_gate",
        "status": "pass" if ready else "blocked",
        "ready": ready,
        "claim_id": CLAIM_ID,
        "advantage_claim_id": CLAIM_ID,
        "bounded_qae_query_scaling_claim_allowed": ready,
        "hardware_quantum_advantage_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "failed_criterion_count": len(failed),
        "criteria": criteria,
        "failed_criteria": failed,
        "summary": {
            "claim_id": CLAIM_ID,
            "advantage_problem_id": metrics.get("advantage_problem_id"),
            "best_classical_algorithm": best_classical.get("algorithm"),
            "best_classical_rmse": best_classical.get("rmse"),
            "best_qae_algorithm": best_qae.get("algorithm"),
            "best_qae_rmse": best_qae.get("rmse"),
            "qae_loglog_delta_slope": comparison_summary.get(
                "qae_loglog_delta_slope"),
            "mc_loglog_delta_slope": comparison_summary.get(
                "mc_loglog_delta_slope"),
            "stratified_loglog_delta_slope": comparison_summary.get(
                "stratified_loglog_delta_slope"),
            "hardware_result_job_count": audit.get("hardware_result_job_count"),
            "completed_hardware_result_count": audit.get(
                "completed_hardware_result_count"),
            "hardware_record_sha256": comparison.get("hardware_record_sha256"),
            "advantage_metrics_audit_passed": metrics_audit.get("passed"),
        },
        "limits": [
            "This gate supports only bounded QAE query-scaling wording.",
            "It is not a practical hardware speedup claim.",
            "It is not a whole-game hardware execution claim.",
            "It is not a full-frame quantum rendering claim.",
        ],
    }


def build_claim_scope_marker(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "qge.hardware_advantage_claim_scope.v0",
        "claim_id": CLAIM_ID,
        "advantage_claim_id": CLAIM_ID,
        "gate_status": gate.get("status"),
        "bounded_qae_query_scaling_claim_allowed": gate.get(
            "bounded_qae_query_scaling_claim_allowed"),
        "hardware_quantum_advantage_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
    }


def build_icc_evidence(
    gate: dict[str, Any],
    *,
    gate_path: Path | None = None,
    claim_scope_path: Path | None = None,
) -> dict[str, Any]:
    ready = gate.get("ready") is True
    completion_reason = (
        "qge_hardware_advantage_claim_ready"
        if ready else
        "qge_hardware_advantage_claim_blocked"
    )
    summary = dict_or_empty(gate.get("summary"))
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_hardware_advantage_gate",
        "completion_reason": completion_reason,
        "status": "success" if ready else "blocked",
        "hardware_advantage_gate_file": str(gate_path) if gate_path else None,
        "hardware_advantage_claim_scope_file": (
            str(claim_scope_path) if claim_scope_path else None),
        "claim_id": gate.get("claim_id"),
        "advantage_claim_id": gate.get("advantage_claim_id"),
        "bounded_qae_query_scaling_claim_allowed": gate.get(
            "bounded_qae_query_scaling_claim_allowed"),
        "hardware_quantum_advantage_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "failed_criterion_count": gate.get("failed_criterion_count"),
        "hardware_result_job_count": summary.get("hardware_result_job_count"),
        "completed_hardware_result_count": summary.get(
            "completed_hardware_result_count"),
        "hardware_record_sha256": summary.get("hardware_record_sha256"),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advantage-metrics", type=Path, required=True)
    parser.add_argument("--job-results", type=Path, required=True)
    parser.add_argument("--hardware-comparison", type=Path, required=True)
    parser.add_argument("--hardware-result-audit", type=Path, required=True)
    parser.add_argument("--advantage-metrics-audit", type=Path, required=True)
    parser.add_argument("--claims", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--icc-out", type=Path)
    parser.add_argument(
        "--claim-scope-out",
        type=Path,
        help=(
            "Scope marker path. Defaults to "
            "qge_hardware_advantage_claim_scope_advantage.light_transport_"
            "qae_query_scaling.json next to --out."
        ),
    )
    parser.add_argument("--fail-on-blocked", action="store_true")
    return parser.parse_args(argv)


def default_claim_scope_path(out_path: Path) -> Path:
    return out_path.parent / CLAIM_SCOPE_MARKER_NAME


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        claims = load_json(args.claims) if args.claims else {}
        gate = build_gate(
            load_json(args.advantage_metrics),
            load_json(args.job_results),
            load_optional_gate_json(
                args.hardware_comparison,
                "hardware_comparison",
            ),
            load_json(args.hardware_result_audit),
            load_json(args.advantage_metrics_audit),
            claims,
        )
        claim_scope_path = args.claim_scope_out or default_claim_scope_path(
            args.out)
        write_json(args.out, gate)
        write_json(claim_scope_path, build_claim_scope_marker(gate))
        if args.icc_out:
            write_json(
                args.icc_out,
                build_icc_evidence(
                    gate,
                    gate_path=args.out,
                    claim_scope_path=claim_scope_path,
                ),
            )
    except (OSError, ValueError) as exc:
        print(f"qge_hardware_advantage_gate: {exc}", file=sys.stderr)
        return 1

    print(f"QGE_HARDWARE_ADVANTAGE_GATE {args.out}")
    print(f"QGE_HARDWARE_ADVANTAGE_CLAIM_SCOPE {claim_scope_path}")
    if args.icc_out:
        print(f"QGE_HARDWARE_ADVANTAGE_GATE_ICC {args.icc_out}")
    if args.fail_on_blocked and not gate.get("ready"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
