#!/usr/bin/env python3
"""Focused tests for the Moonlab hardware return handoff checklist."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import qge_moonlab_hardware_ingest as moonlab_hardware_ingest  # noqa: E402
import qge_moonlab_hardware_result_audit as hardware_result_audit  # noqa: E402
import qge_moonlab_hardware_return_handoff as handoff  # noqa: E402


def fixture() -> tuple[str, dict, dict, dict, dict]:
    job_id = "qge.light_transport_qae_benchmark.mlae.v0"
    packet = {
        "schema": "qge.moonlab_submission_packet.v0",
        "candidate_jobs": [
            {
                "job_id": job_id,
                "domain": "light_transport_qae_benchmark",
                "kind": "moonlab_qae_kernel",
                "submission_status": "ready_for_hardware_submission_metadata",
                "candidate_digest": "candidate-digest",
                "missing_required_artifacts": [],
                "resource": {"shots": 384},
                "required_artifacts": {
                    "qae_circuit": "advantage/qae_circuit.txt",
                },
                "artifact_evidence": [
                    {"name": "qae_circuit", "exists": True},
                ],
            },
        ],
    }
    results = {
        "schema": "qge.moonlab_job_results.v0",
        "blocked_job_count": 0,
        "hardware_submitted_job_count": 0,
        "completed_hardware_job_count": 0,
        "jobs": [
            {
                "job_id": job_id,
                "domain": "light_transport_qae_benchmark",
                "kind": "moonlab_qae_kernel",
                "result_status": "simulator_completed_hardware_not_submitted",
                "hardware_submission_status": "not_submitted",
                "backend_results": [
                    {
                        "backend_id": "moonlab-simulator-local/qge-test",
                        "backend_kind": "moonlab_simulator",
                        "status": "completed",
                    },
                    {
                        "backend_kind": "moonlab_hardware_candidate",
                        "status": "not_submitted",
                    },
                ],
                "observations": {
                    "reference_value": 0.5,
                    "shots": 384,
                    "oracle_eval_count": 864,
                },
                "claim_posture": {
                    "hardware_result_claimed": False,
                    "hardware_quantum_advantage_claimed": False,
                    "whole_game_hardware_execution_claimed": False,
                },
            },
        ],
    }
    template = moonlab_hardware_ingest.build_hardware_record_template(packet)
    record = {
        "schema": "qge.moonlab_hardware_record.v0",
        "job_id": job_id,
        "candidate_digest": "candidate-digest",
        "backend_id": "moonlab-hardware/test-qpu",
        "backend_kind": "moonlab_hardware",
        "status": "completed",
        "run_id": "moonlab-hw-run-handoff-001",
        "submitted_utc": "2026-06-26T04:00:00Z",
        "completed_utc": "2026-06-26T04:01:00Z",
        "shot_schedule": {
            "shots": 384,
            "batches": 4,
            "schedule_id": "qge-mlae-384-handoff",
        },
        "readout_metadata": {
            "shots_completed": 384,
            "readout_format": "expectation_value",
            "mitigation": "none",
        },
        "observations": {
            "mean_value": 0.503,
            "shots": 384,
            "readout_error": 0.004,
        },
        "hardware_quantum_advantage_claimed": False,
        "whole_game_hardware_execution_claimed": False,
        "dense_70000_qubit_state_claimed": False,
    }
    return job_id, packet, results, template, record


class MoonlabHardwareReturnHandoffTests(unittest.TestCase):
    def test_handoff_reports_template_fields_before_hardware_returns(self) -> None:
        _, packet, results, template, _ = fixture()

        report = handoff.build_handoff(packet, results, template)

        self.assertEqual(
            report["status"],
            "blocked_waiting_for_real_moonlab_hardware_record",
        )
        self.assertFalse(report["ready"])
        self.assertIn(
            "hardware_record.backend_id",
            report["missing_record_fields"],
        )
        self.assertIn(
            "hardware_record.observations.readout_error",
            report["missing_record_fields"],
        )
        self.assertTrue(any(
            item["artifact"] == "qge.moonlab_hardware_record.v0"
            for item in report["artifacts_needed_next"]
        ))
        self.assertFalse(
            report["claim_posture"]["hardware_quantum_advantage_claimed"])

    def test_handoff_marks_complete_record_ready_for_ingest_only(self) -> None:
        _, packet, results, template, record = fixture()

        report = handoff.build_handoff(
            packet,
            results,
            template,
            hardware_record=record,
            packet_path=Path("packet.json"),
            job_results_path=Path("results.json"),
            hardware_record_path=Path("record.json"),
        )

        self.assertEqual(report["status"], "ready_for_hardware_ingest")
        self.assertTrue(report["ready_for_hardware_ingest"])
        self.assertFalse(report["ready"])
        self.assertEqual(report["missing_record_fields"], [])
        self.assertEqual(report["record_mismatches"], [])
        self.assertTrue(any(
            "qge_moonlab_hardware_ingest.py" in command
            for command in report["next_commands"]
        ))

    def test_handoff_blocks_overclaiming_hardware_record(self) -> None:
        _, packet, results, template, record = fixture()
        record = json.loads(json.dumps(record))
        record["hardware_quantum_advantage_claimed"] = True

        report = handoff.build_handoff(
            packet,
            results,
            template,
            hardware_record=record,
        )

        self.assertEqual(report["status"], "blocked_hardware_record_incomplete")
        self.assertFalse(report["ready_for_hardware_ingest"])
        self.assertIn(
            "hardware_record.hardware_quantum_advantage_claimed",
            report["overclaim_flags"],
        )

    def test_handoff_reaches_advantage_gate_step_after_strict_audit(self) -> None:
        job_id, packet, results, template, record = fixture()
        updated, comparison = moonlab_hardware_ingest.ingest_hardware_record(
            packet,
            results,
            record,
        )
        scope = {
            "schema": "qge.moonlab_hardware_submission_scope.v0",
            "candidate_digests": {job_id: "candidate-digest"},
        }
        audit = hardware_result_audit.hardware_result_ledger_audit(
            packet,
            updated,
            scope,
            strict_real_campaign=True,
        )
        self.assertTrue(audit["passed"], audit)

        report = handoff.build_handoff(
            packet,
            updated,
            template,
            hardware_record=record,
            hardware_scope=scope,
            hardware_comparison=comparison,
            hardware_result_audit=audit,
        )

        self.assertEqual(report["status"], "ready_for_hardware_advantage_gate")
        self.assertTrue(report["ready_for_hardware_advantage_gate"])
        self.assertFalse(report["ready"])
        self.assertTrue(any(
            "qge_hardware_advantage_gate.py" in command
            for command in report["next_commands"]
        ))

    def test_handoff_cli_writes_blocked_report_fail_closed(self) -> None:
        _, packet, results, template, _ = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            packet_path = tmpdir / "packet.json"
            results_path = tmpdir / "results.json"
            template_path = tmpdir / "template.json"
            out_path = tmpdir / "handoff.json"
            markdown_path = tmpdir / "handoff.md"
            icc_path = tmpdir / "handoff_icc.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            results_path.write_text(json.dumps(results), encoding="utf-8")
            template_path.write_text(json.dumps(template), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = handoff.main([
                    "--submission-packet",
                    str(packet_path),
                    "--job-results",
                    str(results_path),
                    "--hardware-template",
                    str(template_path),
                    "--out",
                    str(out_path),
                    "--markdown",
                    str(markdown_path),
                    "--icc-out",
                    str(icc_path),
                    "--fail-on-blocked",
                ])

            self.assertEqual(code, 1)
            self.assertIn(
                "QGE_MOONLAB_HARDWARE_RETURN_HANDOFF",
                stdout.getvalue(),
            )
            report = json.loads(out_path.read_text(encoding="utf-8"))
            icc = json.loads(icc_path.read_text(encoding="utf-8"))
            self.assertEqual(
                report["status"],
                "blocked_waiting_for_real_moonlab_hardware_record",
            )
            self.assertIn(
                "hardware_record.backend_id",
                markdown_path.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                icc["completion_reason"],
                "qge_moonlab_hardware_return_handoff_blocked",
            )


if __name__ == "__main__":
    raise SystemExit(unittest.main())
