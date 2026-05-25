#!/usr/bin/env python3
"""Direct unit coverage for QGE Python publication/research tools."""

from __future__ import annotations

import contextlib
import io
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import qge_advantage_benchmark as advantage  # noqa: E402
import qge_asset_inventory as asset_inventory  # noqa: E402
import qge_asset_requirements as asset_requirements  # noqa: E402
import qge_breadth_evidence as breadth_evidence  # noqa: E402
import qge_full_game_capture_queue as full_game_capture_queue  # noqa: E402
import qge_image_metrics as image_metrics  # noqa: E402
import qge_moonlab_advantage_icc_audit as moonlab_advantage_icc_audit  # noqa: E402
import qge_moonlab_deployment_gate as moonlab_deployment_gate  # noqa: E402
import qge_moonlab_full_game_plan as moonlab_full_game_plan  # noqa: E402
import qge_moonlab_hardware_ingest as moonlab_hardware_ingest  # noqa: E402
import qge_moonlab_hardware_result_audit as moonlab_hardware_result_audit  # noqa: E402
import qge_moonlab_job_runner as moonlab_job_runner  # noqa: E402
import qge_moonlab_oracle_transpile as moonlab_oracle_transpile  # noqa: E402
import qge_moonlab_qae_grover_plan as moonlab_grover_plan  # noqa: E402
import qge_moonlab_qae_observation_transpile as moonlab_observation_transpile  # noqa: E402
import qge_moonlab_qae_transpile as moonlab_qae_transpile  # noqa: E402
import qge_moonlab_submission_bundle as moonlab_submission_bundle  # noqa: E402
import qge_noesis_summary as noesis_summary  # noqa: E402
import qge_manifest_file_audit as manifest_file_audit  # noqa: E402
import qge_manifest_summary_audit as manifest_summary_audit  # noqa: E402
import qge_oracle_claims_audit as oracle_claims_audit  # noqa: E402
import qge_oracle_icc_audit as oracle_icc_audit  # noqa: E402
import qge_oracle_export as oracle_export  # noqa: E402
import qge_oracle_scene_audit as oracle_scene_audit  # noqa: E402
import qge_perf_summary as perf_summary  # noqa: E402
import qge_publication_icc_audit as publication_icc_audit  # noqa: E402
import qge_publication_pack as publication_pack  # noqa: E402
import qge_resource_boundary_audit as resource_boundary_audit  # noqa: E402
import qge_registered_asset_intake as registered_asset_intake  # noqa: E402
import qge_runtime_icc_audit as runtime_icc_audit  # noqa: E402
import qge_trace_summary as trace_summary  # noqa: E402
import qge_vanilla_capture_matrix as vanilla_matrix  # noqa: E402
import qge_world_frame_metrics as world_frame_metrics  # noqa: E402


def write_rgb_png(path: Path, rows: list[list[tuple[int, int, int]]]) -> None:
    height = len(rows)
    width = len(rows[0]) if rows else 0
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for red, green, blue in row:
            raw.extend((red, green, blue))

    def chunk(name: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload)) +
            name +
            payload +
            struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" +
        chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
        chunk(b"IDAT", zlib.compress(bytes(raw))) +
        chunk(b"IEND", b"")
    )


def minimal_bsp_bytes() -> bytes:
    entities = b'{"classname" "worldspawn"}\n\0'
    model = b"\0" * 64
    lumps = [(0, 0)] * 15
    body = bytearray()
    offset = 4 + 15 * 8
    for lump_index, payload in ((0, entities), (14, model)):
        lumps[lump_index] = (offset, len(payload))
        body.extend(payload)
        offset += len(payload)
    header = bytearray(struct.pack("<i", 29))
    for lump_offset, lump_length in lumps:
        header.extend(struct.pack("<ii", lump_offset, lump_length))
    return bytes(header + body)


def write_pak(
    path: Path,
    names: list[str],
    payloads: dict[str, bytes] | None = None,
) -> None:
    payloads = payloads or {}
    file_data = bytearray()
    entries = []
    directory = bytearray()
    for name in names:
        raw_name = name.encode("ascii")
        if len(raw_name) > 55:
            raise ValueError("PAK entry name is too long")
        payload = payloads.get(
            name,
            minimal_bsp_bytes() if name.lower().endswith(".bsp") else b"",
        )
        file_offset = 12 + len(file_data)
        entries.append((raw_name, file_offset, len(payload)))
        file_data.extend(payload)
    for raw_name, file_offset, file_size in entries:
        directory.extend(raw_name + b"\0" * (56 - len(raw_name)))
        directory.extend(struct.pack("<II", file_offset, file_size))
    directory_offset = 12 + len(file_data)
    path.write_bytes(
        struct.pack("<4sII", b"PACK", directory_offset, len(directory)) +
        file_data +
        directory
    )


def moonlab_coverage_ledger_result_job(
    coverage: dict,
    inventory: dict,
    requirements: dict,
    *,
    observations_override: dict | None = None,
) -> dict:
    observations = {
        "coverage_status": coverage.get("status"),
        "map_set": coverage.get("map_set"),
        "target_map_count": coverage.get("target_map_count"),
        "covered_map_count": coverage.get("covered_map_count"),
        "missing_map_count": coverage.get("missing_map_count"),
        "missing_maps": coverage.get("missing_maps"),
        "asset_inventory_status": inventory.get("status"),
        "asset_available_map_count": inventory.get("available_map_count"),
        "asset_missing_map_count": inventory.get("missing_map_count"),
        "asset_invalid_bsp_count": inventory.get("invalid_bsp_count"),
        "full_game_asset_ready": inventory.get("full_game_asset_ready"),
        "asset_requirement_status": requirements.get("status"),
        "asset_requirements_present_map_count": (
            requirements.get("present_map_count")),
        "asset_requirements_missing_map_count": (
            requirements.get("missing_map_count")),
        "asset_requirements_satisfied": (
            moonlab_deployment_gate.dict_or_empty(
                requirements.get("claim_posture")
            ).get("asset_requirements_satisfied")),
    }
    if observations_override:
        observations.update(observations_override)
    return {
        "job_id": "qge.full_game_map_coverage.ledger.v0",
        "domain": "full_game_map_coverage",
        "kind": "moonlab_coverage_ledger_replay",
        "result_status": "completed",
        "missing_required_artifacts": [],
        "backend_results": [
            {
                "backend_id": "moonlab-simulator-local/qge-publication-pack",
                "backend_kind": "moonlab_simulator",
                "status": "completed",
                "run_id": "moonlab-sim-test-ledger",
            },
        ],
        "artifact_evidence": [
            {
                "name": "asset_inventory",
                "path": "resource/qge_asset_inventory.json",
                "exists": True,
                "size_bytes": 128,
                "sha256": "asset-inventory-sha",
            },
            {
                "name": "asset_requirements",
                "path": "resource/qge_asset_requirements.json",
                "exists": True,
                "size_bytes": 128,
                "sha256": "asset-requirements-sha",
            },
            {
                "name": "full_game_map_coverage",
                "path": "resource/qge_full_game_map_coverage.json",
                "exists": True,
                "size_bytes": 128,
                "sha256": "coverage-sha",
            },
            {
                "name": "registered_asset_intake",
                "path": "resource/qge_registered_asset_intake.json",
                "exists": True,
                "size_bytes": 128,
                "sha256": "asset-intake-sha",
            },
        ],
        "observations": observations,
    }


def moonlab_selected_job_spec_jobs() -> list[dict]:
    return [
        {
            "job_id": "qge.render_primary_framebuffer.sparse_dwt_replay.v0",
            "domain": "render_primary_framebuffer",
            "kind": "moonlab_simulator_native_backend_replay",
            "hardware_candidate": False,
            "hardware_submission_status": (
                "not_applicable_full_frame_hardware_execution_not_claimed"),
            "required_artifacts": {
                "frame": "capture/frame_001.png",
                "oracle_scene": "oracle/oracle_scene.json",
                "trace": "capture/qge_trace.bin",
            },
        },
        {
            "job_id": "qge.light_transport_qae_benchmark.mlae.v0",
            "domain": "light_transport_qae_benchmark",
            "kind": "moonlab_qae_kernel",
            "hardware_candidate": True,
            "hardware_submission_status": "not_submitted",
            "required_artifacts": {
                "advantage_metrics": "advantage/advantage_metrics.json",
                "qae_circuit": "advantage/qae_circuit.txt",
            },
        },
        {
            "job_id": "qge.runtime_backend_probe.replay.v0",
            "domain": "runtime_backend_probes",
            "kind": "moonlab_runtime_boundary_replay",
            "hardware_candidate": False,
            "hardware_submission_status": "not_a_quantum_hardware_job",
            "required_artifacts": {
                "breadth_evidence": "breadth/breadth_evidence.json",
                "performance_summary": "capture/qge_perf_summary.json",
            },
        },
        {
            "job_id": "qge.full_game_map_coverage.ledger.v0",
            "domain": "full_game_map_coverage",
            "kind": "moonlab_coverage_ledger_replay",
            "hardware_candidate": False,
            "hardware_submission_status": "not_a_quantum_hardware_job",
            "required_artifacts": {
                "asset_inventory": "resource/qge_asset_inventory.json",
                "asset_requirements": "resource/qge_asset_requirements.json",
                "full_game_map_coverage": (
                    "resource/qge_full_game_map_coverage.json"),
                "registered_asset_intake": (
                    "resource/qge_registered_asset_intake.json"),
            },
        },
    ]


def moonlab_completed_result_job(
    job_id: str,
    domain: str,
    kind: str,
    *,
    hardware_candidate: bool = False,
    hardware_submission_status: str = "not_a_quantum_hardware_job",
) -> dict:
    result_status = (
        "simulator_completed_hardware_not_submitted"
        if hardware_candidate else "completed"
    )
    backend_results = [
        {
            "backend_id": "moonlab-simulator-local/qge-publication-pack",
            "backend_kind": "moonlab_simulator",
            "status": "completed",
            "run_id": f"moonlab-sim-test-{domain}",
        }
    ]
    if kind == "moonlab_simulator_native_backend_replay":
        backend_results.append({
            "backend_id": "qge-native-sparse-dwt-bridge",
            "backend_kind": "native_backend_replay",
            "status": "completed",
            "run_id": f"qge-native-test-{domain}",
        })
    if hardware_candidate:
        backend_results.append({
            "backend_id": None,
            "backend_kind": "moonlab_hardware_candidate",
            "status": hardware_submission_status,
            "run_id": None,
        })
    return {
        "job_id": job_id,
        "domain": domain,
        "kind": kind,
        "result_status": result_status,
        "hardware_candidate": hardware_candidate,
        "hardware_submission_status": hardware_submission_status,
        "missing_required_artifacts": [],
        "artifact_evidence": [
            {
                "name": name,
                "path": path,
                "exists": True,
                "size_bytes": 128,
                "sha256": f"{domain}-{name}-sha",
            }
            for name, path in {
                "render_primary_framebuffer": {
                    "frame": "capture/frame_001.png",
                    "oracle_scene": "oracle/oracle_scene.json",
                    "trace": "capture/qge_trace.bin",
                },
                "light_transport_qae_benchmark": {
                    "advantage_metrics": (
                        "advantage/advantage_metrics.json"),
                    "qae_circuit": "advantage/qae_circuit.txt",
                },
                "runtime_backend_probes": {
                    "breadth_evidence": "breadth/breadth_evidence.json",
                    "performance_summary": "capture/qge_perf_summary.json",
                },
            }.get(domain, {}).items()
        ],
        "backend_results": backend_results,
        "observations": {},
    }


def moonlab_selected_job_result_jobs(
    coverage: dict,
    inventory: dict,
    requirements: dict,
    *,
    observations_override: dict | None = None,
) -> list[dict]:
    return [
        moonlab_completed_result_job(
            "qge.render_primary_framebuffer.sparse_dwt_replay.v0",
            "render_primary_framebuffer",
            "moonlab_simulator_native_backend_replay",
            hardware_submission_status=(
                "not_applicable_full_frame_hardware_execution_not_claimed"),
        ),
        moonlab_completed_result_job(
            "qge.light_transport_qae_benchmark.mlae.v0",
            "light_transport_qae_benchmark",
            "moonlab_qae_kernel",
            hardware_candidate=True,
            hardware_submission_status="not_submitted",
        ),
        moonlab_completed_result_job(
            "qge.runtime_backend_probe.replay.v0",
            "runtime_backend_probes",
            "moonlab_runtime_boundary_replay",
        ),
        moonlab_coverage_ledger_result_job(
            coverage,
            inventory,
            requirements,
            observations_override=observations_override,
        ),
    ]


def minimal_oracle_scene() -> dict:
    return {
        "scene": {
            "scene_id": "e1m1:7",
            "map": "e1m1",
            "selected_frame": 7,
            "trace_run_id": "0x5151455f52554e31",
        },
        "source_capture": {
            "trace_sha256": "trace-sha",
            "frame_sha256": "frame-sha",
        },
        "observable": {
            "observable_id": "light_transport.soft_shadow_visibility",
            "kind": "mean_estimation",
            "range": [0.0, 1.0],
        },
        "sample_space": {
            "candidate_count": 8,
        },
        "oracle_contract": {
            "input_register": {
                "candidate_index_bits": 3,
            },
            "reversibility": "classical_model",
        },
        "cost_model": {
            "state_prep_cost": 8,
            "qram_assumption": "none",
            "fallback_count": 0,
        },
        "snapshot": {
            "render": {
                "coeffs": 128,
                "edgefills": 2,
                "material": 8,
            },
        },
    }


class ICCProfileTests(unittest.TestCase):
    def test_moonlab_hardware_submission_oracle_is_scoped(self) -> None:
        profile = json.loads(
            (REPO_ROOT / ".icc" / "completion-oracles.json")
            .read_text(encoding="utf-8")
        )
        oracle = next(
            item for item in profile["oracles"]
            if item["name"] == "qge_moonlab_hardware_submission_scope"
        )
        self.assertEqual(
            oracle["target"],
            "Moonlab hardware submission packet with replayable circuit "
            "and backend proof evidence",
        )
        self.assertEqual(
            oracle["suppressed_runtime_checks"],
            ["failure_free"],
        )
        self.assertNotIn("hardware-deployment evidence", oracle["aliases"])

        requirements = {item["id"]: item for item in oracle["requires"]}
        backend_requirement = requirements["qge_moonlab_hardware_scope_backend"]
        completion_requirement = (
            requirements["qge_moonlab_hardware_scope_completion"])
        artifact_requirement = requirements["qge_moonlab_hardware_scope_artifact"]
        self.assertEqual(
            backend_requirement["event_values"],
            ["qge_moonlab_hardware_submission_scope"],
        )
        self.assertEqual(
            completion_requirement["event_values"],
            ["qge_moonlab_hardware_submission_scope_ready"],
        )
        self.assertIn(
            "moonlab_hardware_submission_scope_file",
            artifact_requirement["event_names"],
        )
        self.assertIn(
            "qge_moonlab_hardware_submission_scope.json",
            artifact_requirement["event_names"],
        )

    def test_moonlab_full_game_deployment_oracle_requires_ready_gate(self) -> None:
        profile = json.loads(
            (REPO_ROOT / ".icc" / "completion-oracles.json")
            .read_text(encoding="utf-8")
        )
        oracle = next(
            item for item in profile["oracles"]
            if item["name"] == "qge_moonlab_full_game_deployment"
        )
        self.assertEqual(
            oracle["target"],
            "Full Quake running in Moonlab with publishable "
            "hardware-deployment evidence",
        )
        self.assertNotIn("suppressed_runtime_checks", oracle)

        requirements = {item["id"]: item for item in oracle["requires"]}
        backend_requirement = (
            requirements["qge_moonlab_full_game_deployment_backend"])
        ready_requirement = (
            requirements["qge_moonlab_full_game_deployment_ready"])
        artifact_requirement = (
            requirements["qge_moonlab_full_game_deployment_artifact"])
        self.assertEqual(
            backend_requirement["event_values"],
            ["qge_moonlab_deployment_gate"],
        )
        self.assertEqual(
            ready_requirement["event_values"],
            ["qge_moonlab_deployment_gate_ready"],
        )
        self.assertIn(
            "moonlab_deployment_gate_file",
            artifact_requirement["event_names"],
        )
        self.assertIn(
            "qge_moonlab_deployment_gate.json",
            artifact_requirement["event_names"],
        )


class OracleExportTests(unittest.TestCase):
    def test_parse_helpers_and_icc_evidence(self) -> None:
        fields = oracle_export.parse_kv_body(
            "flags=0x3d time=12.5 texcache=8/0 owner=qge_3d"
        )
        self.assertEqual(fields["flags"], 0x3D)
        self.assertEqual(fields["time"], 12.5)
        self.assertEqual(fields["owner"], "qge_3d")
        self.assertEqual(oracle_export.parse_cache_hit_count("8/0"), 8)
        self.assertIsNone(oracle_export.parse_cache_hit_count("not/count"))

        trace = {
            "records": {"state_probe": 1},
            "state_probes": [{"label": "render_gate_kernel"}],
        }
        render = {"shots": 16}
        oracle_scene = {
            "schema": "qge.scene_oracle_ir.v0",
            "scene": {"scene_id": "e1m1:7", "trace_run_id": "0x1"},
            "observable": {"observable_id": "light_transport"},
            "sample_space": {"candidate_count": 8},
            "cost_model": {
                "state_prep_cost": 8,
                "readout_model": "sidecar_model",
                "shots": 16,
                "fallback_count": 0,
            },
            "trace_summary": {
                "records": trace["records"],
                "state_probes": trace["state_probes"],
                "sequence_errors": 0,
            },
            "snapshot": {"render": render},
        }
        scene_audit = oracle_scene_audit.oracle_scene_source_audit(
            oracle_scene,
            expected_oracle_scene=oracle_scene,
            required=True,
        )
        self.assertTrue(scene_audit["passed"])
        self.assertEqual(scene_audit["mismatch_count"], 0)

        stale_scene = json.loads(json.dumps(oracle_scene))
        stale_scene["sample_space"]["candidate_count"] = 0
        stale_scene["hardware_quantum_advantage_claimed"] = True
        stale_scene_audit = oracle_scene_audit.oracle_scene_source_audit(
            stale_scene,
            expected_oracle_scene=oracle_scene,
            required=True,
        )
        self.assertFalse(stale_scene_audit["passed"])
        self.assertIn(
            "sample_space.candidate_count",
            stale_scene_audit["field_mismatches"],
        )
        self.assertTrue(any(
            flag.get("flag") == "hardware_quantum_advantage_claimed"
            for flag in stale_scene_audit["overclaim_flags"]
        ))
        ledger = {
            "claims": [
                {
                    "claim_id": "compiler.scene_oracle_ir",
                    "status": "planned",
                    "required_trace_fields": ["records", "candidate_count"],
                    "allowed_wording": "supported",
                    "disallowed_wording": "unsupported",
                },
                {
                    "claim_id": "future.claim",
                    "status": "planned",
                    "required_trace_fields": ["baseline_id"],
                },
            ]
        }

        claims = oracle_export.build_claims_evidence(
            oracle_scene, trace, render, ledger
        )
        self.assertEqual(claims["claims"][0]["evidence_status"], "supported")
        self.assertEqual(claims["claims"][1]["evidence_status"], "planned")
        self.assertEqual(claims["claims"][1]["missing_fields"], ["baseline_id"])
        claims_audit = oracle_claims_audit.oracle_claims_evidence_audit(
            oracle_scene,
            ledger,
            claims,
            required=True,
        )
        self.assertTrue(claims_audit["passed"])
        self.assertEqual(claims_audit["mismatch_count"], 0)

        stale_claims = json.loads(json.dumps(claims))
        stale_claims["claims"][0]["evidence_status"] = "blocked"
        stale_claims["whole_game_hardware_execution_claimed"] = True
        stale_claims_audit = (
            oracle_claims_audit.oracle_claims_evidence_audit(
                oracle_scene,
                ledger,
                stale_claims,
                required=True,
            )
        )
        self.assertFalse(stale_claims_audit["passed"])
        self.assertIn(
            "claims[0].evidence_status",
            stale_claims_audit["field_mismatches"],
        )
        self.assertTrue(any(
            flag.get("flag") == "whole_game_hardware_execution_claimed"
            for flag in stale_claims_audit["overclaim_flags"]
        ))

        icc = oracle_export.build_icc_evidence(
            oracle_scene,
            claims,
            Path("oracle_scene.json"),
            Path("claims_evidence.json"),
        )
        self.assertEqual(icc["runtime_backend"], "qge_oracle_export")
        self.assertEqual(icc["completion_reason"], "qge_scene_oracle_ir_exported")
        self.assertEqual(icc["candidate_count"], 8)
        self.assertIn("compiler.scene_oracle_ir", icc["supported_claim_ids"])
        self.assertIn("future.claim", icc["blocked_claim_ids"])
        icc_audit = oracle_icc_audit.oracle_icc_evidence_audit(
            oracle_scene,
            claims,
            icc,
            artifact_paths={
                "oracle_scene": "oracle_scene.json",
                "claims_evidence": "claims_evidence.json",
            },
            required=True,
        )
        self.assertTrue(icc_audit["passed"])
        self.assertEqual(icc_audit["mismatch_count"], 0)

        stale_icc = json.loads(json.dumps(icc))
        stale_icc["candidate_count"] = 0
        stale_icc["hardware_quantum_advantage_claimed"] = True
        stale_audit = oracle_icc_audit.oracle_icc_evidence_audit(
            oracle_scene,
            claims,
            stale_icc,
            artifact_paths={
                "oracle_scene": "oracle_scene.json",
                "claims_evidence": "claims_evidence.json",
            },
            required=True,
        )
        self.assertFalse(stale_audit["passed"])
        self.assertIn("candidate_count", stale_audit["field_mismatches"])
        self.assertTrue(any(
            flag.get("flag") == "hardware_quantum_advantage_claimed"
            for flag in stale_audit["overclaim_flags"]
        ))


class AdvantageBenchmarkTests(unittest.TestCase):
    def test_qrom_value_load_cover_preserves_invalid_candidates(self) -> None:
        success_counts = [0, 1, 2, 3, 4, 5]
        candidate_bits = 3
        cover = moonlab_oracle_transpile.qrom_value_load_cover(
            success_counts, candidate_bits)

        def covered_value(address: int) -> int:
            value = 0
            for bit, cubes in enumerate(cover):
                for cube in cubes:
                    mask = int(cube["specified_mask"])
                    expected = int(cube["specified_value"])
                    if (address & mask) == expected:
                        value ^= 1 << bit
            return value

        for address, expected in enumerate(success_counts):
            self.assertEqual(covered_value(address), expected)
        for invalid_address in range(len(success_counts), 1 << candidate_bits):
            self.assertEqual(covered_value(invalid_address), 0)

    def test_build_metrics_and_artifact_helpers(self) -> None:
        oracle_scene = minimal_oracle_scene()
        args = SimpleNamespace(
            oracle_scene=Path("oracle_scene.json"),
            seed=123,
            trials=2,
            samples=[4, 8, 4],
            qae_levels=2,
            qae_shots=4,
            qae_grid_steps=64,
            contribution_bits=4,
        )

        self.assertEqual(advantage.sample_counts(args), [4, 8])
        contributions = advantage.build_contributions(oracle_scene, 123, 4)
        self.assertEqual(len(contributions), 8)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in contributions))
        self.assertEqual(contributions, advantage.build_contributions(oracle_scene, 123, 4))

        metrics = advantage.build_metrics(args, oracle_scene)
        self.assertEqual(metrics["schema"], "qge.advantage_metrics.v0")
        self.assertEqual(metrics["observable"]["candidate_count"], 8)
        self.assertEqual(metrics["scaling_summary"]["trial_count"], 2)
        self.assertGreater(metrics["resource_estimate"]["logical_qubits"], 0)
        self.assertIn("absolute_delta", metrics["comparison"]["best_qae"])
        self.assertNotIn("absolute_error", metrics["comparison"]["best_qae"])

        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp)
            metrics_path = outdir / "advantage_metrics.json"
            curve_path = outdir / "qae_curve.csv"
            circuit_path = outdir / "qae_circuit.txt"
            scaling_path = outdir / "scaling_summary.json"
            scaling_csv_path = outdir / "scaling_summary.csv"
            advantage.write_json(metrics_path, metrics)
            advantage.write_curve_csv(curve_path, metrics)
            advantage.write_json(scaling_path, metrics["scaling_summary"])
            advantage.write_scaling_csv(scaling_csv_path, metrics)
            advantage.write_circuit_text(circuit_path, metrics)
            icc = advantage.build_icc_evidence(
                metrics, metrics_path, curve_path, circuit_path, scaling_path
            )

            self.assertTrue(metrics_path.is_file())
            self.assertIn("algorithm", curve_path.read_text(encoding="utf-8"))
            self.assertIn("QGE QAE abstract circuit v0", circuit_path.read_text(encoding="utf-8"))
            self.assertEqual(icc["runtime_backend"], "qge_advantage_benchmark")
            self.assertEqual(icc["completion_reason"], "qge_advantage_benchmark_complete")
            self.assertEqual(icc["trial_count"], 2)
            self.assertIn("absolute_delta", curve_path.read_text(encoding="utf-8"))
            self.assertIn("ci95_absolute_delta", icc)
            self.assertNotIn("ci95_absolute_error", icc)

            payload_path = outdir / "qae_moonlab_payload.json"
            payload_md = outdir / "qae_moonlab_payload.md"
            payload_icc_path = outdir / "qae_moonlab_payload_icc.json"
            circuit_dir = outdir / "moonlab_qae_circuits"
            payload = moonlab_qae_transpile.build_payload(
                metrics,
                metrics_path=metrics_path,
                abstract_circuit_path=circuit_path,
                circuit_dir=circuit_dir,
            )
            moonlab_qae_transpile.write_json(payload_path, payload)
            payload_md.write_text(
                moonlab_qae_transpile.markdown_report(payload),
                encoding="utf-8",
            )
            moonlab_qae_transpile.write_json(
                payload_icc_path,
                moonlab_qae_transpile.build_icc_evidence(
                    payload,
                    out_path=payload_path,
                ),
            )
            self.assertEqual(
                payload["schema"], "qge.moonlab_qae_payload.v0")
            self.assertEqual(
                payload["status"],
                "calibration_payload_ready_oracle_transpilation_required")
            self.assertFalse(
                payload["claim_posture"]["full_qae_oracle_transpiled"])
            self.assertGreater(
                payload["payload_resource_estimate"]["circuit_count"], 0)
            first_circuit = next(circuit_dir.glob("*.moonlab"))
            self.assertIn(
                "# moonlab-circuit v1",
                first_circuit.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "calibration_payload_ready",
                payload_md.read_text(encoding="utf-8"),
            )
            payload_icc = publication_pack.load_json(payload_icc_path)
            self.assertEqual(
                payload_icc["runtime_backend"],
                "qge_moonlab_qae_transpile")

            oracle_kernel_path = outdir / "qae_moonlab_oracle_kernel.json"
            oracle_kernel_circuit = (
                outdir / "qae_moonlab_oracle_kernel.moonlab")
            oracle_kernel_md = outdir / "qae_moonlab_oracle_kernel.md"
            oracle_kernel_icc_path = (
                outdir / "qae_moonlab_oracle_kernel_icc.json")
            oracle_kernel = moonlab_oracle_transpile.build_kernel(
                metrics,
                oracle_scene,
                metrics_path=metrics_path,
                oracle_scene_path=Path("oracle_scene.json"),
                circuit_path=oracle_kernel_circuit,
            )
            moonlab_oracle_transpile.write_json(
                oracle_kernel_path, oracle_kernel)
            oracle_kernel_md.write_text(
                moonlab_oracle_transpile.markdown_report(oracle_kernel),
                encoding="utf-8",
            )
            moonlab_oracle_transpile.write_json(
                oracle_kernel_icc_path,
                moonlab_oracle_transpile.build_icc_evidence(
                    oracle_kernel,
                    out_path=oracle_kernel_path,
                ),
            )
            self.assertEqual(
                oracle_kernel["schema"],
                "qge.moonlab_qae_oracle_kernel.v0")
            self.assertEqual(
                oracle_kernel["status"],
                "qf_oracle_kernel_ready_qae_transpilation_required")
            self.assertTrue(
                oracle_kernel["claim_posture"]
                ["qf_oracle_kernel_transpiled"])
            self.assertFalse(
                oracle_kernel["claim_posture"]
                ["full_qae_oracle_transpiled"])
            self.assertTrue(
                oracle_kernel["moonlab_control_plane"]
                ["control_plane_executable"])
            self.assertLess(
                oracle_kernel["moonlab_control_plane"]["body_bytes"],
                moonlab_oracle_transpile.MOONLAB_CONTROL_MAX_BODY_BYTES)
            self.assertIn(
                "# moonlab-circuit v1",
                oracle_kernel_circuit.read_text(encoding="utf-8")[:128],
            )
            oracle_kernel_icc = publication_pack.load_json(
                oracle_kernel_icc_path)
            self.assertEqual(
                oracle_kernel_icc["runtime_backend"],
                "qge_moonlab_oracle_transpile")

            observation_path = (
                outdir / "qae_moonlab_observation_zero.json")
            observation_circuit = (
                outdir / "qae_moonlab_observation_zero.moonlab")
            observation_md = (
                outdir / "qae_moonlab_observation_zero.md")
            observation_icc_path = (
                outdir / "qae_moonlab_observation_zero_icc.json")
            observation = moonlab_observation_transpile.build_observation_circuit(
                metrics,
                oracle_scene,
                metrics_path=metrics_path,
                oracle_scene_path=Path("oracle_scene.json"),
                circuit_path=observation_circuit,
            )
            moonlab_observation_transpile.write_json(
                observation_path, observation)
            observation_md.write_text(
                moonlab_observation_transpile.markdown_report(observation),
                encoding="utf-8",
            )
            moonlab_observation_transpile.write_json(
                observation_icc_path,
                moonlab_observation_transpile.build_icc_evidence(
                    observation,
                    out_path=observation_path,
                ),
            )
            self.assertEqual(
                observation["schema"],
                "qge.moonlab_qae_observation_circuit.v0")
            self.assertEqual(
                observation["status"],
                "qae_observation_zero_ready_grover_schedule_required")
            self.assertEqual(
                observation["semantic_scope"],
                "bernoulli_lift_qae_power_zero_observation")
            self.assertTrue(
                observation["claim_posture"]
                ["candidate_state_preparation_transpiled"])
            self.assertTrue(
                observation["claim_posture"]
                ["power_zero_observation_transpiled"])
            self.assertFalse(
                observation["claim_posture"]
                ["full_qae_oracle_transpiled"])
            self.assertEqual(
                observation["state_preparation"]
                ["invalid_candidate_probability"],
                0.0)
            self.assertLess(
                observation["moonlab_control_plane"]["body_bytes"],
                moonlab_observation_transpile.MOONLAB_CONTROL_MAX_BODY_BYTES)
            self.assertIn(
                "# moonlab-circuit v1",
                observation_circuit.read_text(encoding="utf-8")[:128],
            )
            observation_icc = publication_pack.load_json(
                observation_icc_path)
            self.assertEqual(
                observation_icc["runtime_backend"],
                "qge_moonlab_qae_observation_transpile")
            self.assertTrue(
                observation_icc[
                    "candidate_state_preparation_transpiled"])

            grover_plan_path = (
                outdir / "qae_moonlab_grover_schedule_plan.json")
            grover_plan_md = (
                outdir / "qae_moonlab_grover_schedule_plan.md")
            grover_plan_icc_path = (
                outdir / "qae_moonlab_grover_schedule_plan_icc.json")
            grover_plan = moonlab_grover_plan.build_schedule_plan(
                metrics,
                oracle_scene,
                metrics_path=metrics_path,
                oracle_scene_path=Path("oracle_scene.json"),
            )
            moonlab_grover_plan.write_json(grover_plan_path, grover_plan)
            grover_plan_md.write_text(
                moonlab_grover_plan.markdown_report(grover_plan),
                encoding="utf-8",
            )
            moonlab_grover_plan.write_json(
                grover_plan_icc_path,
                moonlab_grover_plan.build_icc_evidence(
                    grover_plan,
                    out_path=grover_plan_path,
                ),
            )
            self.assertEqual(
                grover_plan["schema"],
                "qge.moonlab_qae_grover_schedule_plan.v0")
            self.assertEqual(
                grover_plan["semantic_scope"],
                "bernoulli_lift_qae_grover_schedule_control_plane_plan")
            self.assertIn(
                grover_plan["status"],
                {
                    "qae_grover_schedule_ready_for_control_plane_submission",
                    "qae_grover_schedule_blocked_control_plane_body_limit",
                })
            self.assertGreater(
                grover_plan["block_resources"]["a"]["gate_count"], 0)
            self.assertGreaterEqual(
                grover_plan["moonlab_control_plane"]
                ["ready_observation_count"],
                1)
            self.assertFalse(
                grover_plan["claim_posture"]
                ["hardware_result_claimed"])
            self.assertIn(
                "Grover Schedule Plan",
                grover_plan_md.read_text(encoding="utf-8"))
            grover_plan_icc = publication_pack.load_json(
                grover_plan_icc_path)
            self.assertEqual(
                grover_plan_icc["runtime_backend"],
                "qge_moonlab_qae_grover_plan")


class PublicationPackTests(unittest.TestCase):
    def test_graphics_sidecar_supplies_publication_performance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            stream = tmpdir / "quake_stream"
            graphics = tmpdir / "quake_graphics"
            stream.mkdir()
            graphics.mkdir()
            vanilla_matrix = graphics / "vanilla_capture_matrix.json"
            vanilla_matrix.write_text("{}\n", encoding="utf-8")
            publication_pack.write_json(
                graphics / "quantum.qge_perf_summary.json",
                {
                    "status": "pass",
                    "aggregate": {
                        "engine_average_quantum_ms_max": 12.5,
                        "render_time_ms_max": 22.0,
                        "threshold_failures": [],
                        "metric_evidence_present": True,
                    },
                },
            )
            publication_pack.write_json(
                stream / "qge_perf_summary.json",
                {
                    "status": "blocked",
                    "aggregate": {
                        "threshold_failures": [],
                        "metric_evidence_present": False,
                    },
                },
            )

            args = SimpleNamespace(
                capture_dir=stream,
                vanilla_matrix=vanilla_matrix,
                graphics_capture_dir=None,
                agent_stream_dir=None,
            )
            inputs = publication_pack.resolve_inputs(args)
            self.assertEqual(inputs["graphics_capture_dir"], graphics)
            summary, _icc, source = publication_pack.publication_performance_paths(
                stream, inputs["graphics_capture_dir"])
            self.assertEqual(summary, graphics / "quantum.qge_perf_summary.json")
            self.assertEqual(source, "graphics_qge_candidate")
            perf = publication_pack.performance_summary(summary)
            self.assertFalse(publication_pack.explicit_performance_failure(perf))
            self.assertEqual(perf["render_time_ms_max"], 22.0)

    def test_manifest_file_record_audit_detects_stale_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            artifact = tmpdir / "artifact.txt"
            artifact.write_text("manifest-bound artifact\n", encoding="utf-8")
            bundle = tmpdir / "bundle"
            bundle.mkdir()
            nested = bundle / "nested.txt"
            nested.write_text("nested artifact\n", encoding="utf-8")
            manifest = {
                "artifacts": {
                    "sample": {
                        "file": publication_pack.file_info(artifact),
                        "directory": publication_pack.directory_info(bundle),
                    }
                }
            }

            audit = manifest_file_audit.manifest_file_record_audit(
                manifest,
                required=True,
            )
            self.assertTrue(audit["passed"])
            self.assertEqual(audit["file_record_count"], 2)
            self.assertEqual(audit["directory_record_count"], 1)
            self.assertEqual(audit["mismatch_count"], 0)

            stale_manifest = json.loads(json.dumps(manifest))
            stale_manifest["artifacts"]["sample"]["file"]["sha256"] = "0" * 64
            stale_directory = stale_manifest["artifacts"]["sample"]["directory"]
            stale_directory["file_count"] = 0
            stale_audit = manifest_file_audit.manifest_file_record_audit(
                stale_manifest,
                required=True,
            )
            self.assertFalse(stale_audit["passed"])
            self.assertTrue(any(
                item.get("source") == "artifacts.sample.file" and
                "sha256" in item.get("fields", [])
                for item in stale_audit["mismatches"]
            ))
            self.assertTrue(any(
                item.get("source") == "artifacts.sample.directory" and
                "file_count" in item.get("fields", [])
                for item in stale_audit["mismatches"]
            ))

    def test_manifest_summary_audit_detects_stale_mirrors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            source = tmpdir / "source"
            source.mkdir()
            agent_stream = source / "agent_stream"
            agent_stream.mkdir()
            vanilla_matrix = source / "vanilla_capture_matrix.json"
            performance = source / "qge_perf_summary.json"
            breadth = source / "breadth_evidence.json"
            coverage = {
                "schema": "qge.full_game_map_coverage.v0",
                "map_set": "unit",
                "status": "complete",
                "target_map_count": 1,
                "covered_map_count": 1,
                "missing_map_count": 0,
                "missing_maps": [],
                "extra_maps": [],
            }
            publication_pack.write_json(
                vanilla_matrix,
                {
                    "conformance_summary": {
                        "ready_for_complete_claim": True,
                        "fallback_count": 0,
                        "qge_surface_surrogates": 0,
                        "agent_stream_runs_success": True,
                        "performance_sidecars_success": True,
                    }
                },
            )
            publication_pack.write_json(
                agent_stream / "manifest.json",
                {
                    "status": "complete",
                    "frames_requested": 1,
                    "frames_captured": 1,
                    "trace_requested": 1,
                    "trace_status": "copied",
                    "trace_bytes": 64,
                    "run": {
                        "status": "ok",
                        "success": 1,
                        "startup_issue": "",
                        "process_status": 0,
                        "timed_out": 0,
                    },
                    "performance": {"status": "pass"},
                },
            )
            publication_pack.write_json(
                performance,
                {
                    "status": "pass",
                    "aggregate": {
                        "threshold_failures": [],
                        "metric_evidence_present": True,
                    },
                },
            )
            publication_pack.write_json(
                breadth,
                {
                    "status": "success",
                    "aggregate": {
                        "breadth_ready_for_complete_claim": True,
                        "matrix_run_count": 1,
                        "ready_matrix_run_count": 1,
                        "map_count": 1,
                        "maps": ["start"],
                        "full_game_coverage": coverage,
                    },
                },
            )
            manifest: dict[str, Any] = {
                "source_inputs": {
                    "vanilla_matrix": str(vanilla_matrix),
                    "publication_performance_source": "unit_test",
                    "publication_performance_summary": str(performance),
                    "agent_stream_dir": str(agent_stream),
                    "breadth_evidence": str(breadth),
                },
                "artifacts": {
                    "advantage": {},
                    "resource": {},
                },
            }

            def add_artifact(
                section: str,
                name: str,
                data: dict[str, Any],
            ) -> None:
                path = tmpdir / section / f"{name}.json"
                publication_pack.write_json(path, data)
                artifacts = manifest["artifacts"]
                section_artifacts = artifacts[section]
                section_artifacts[name] = {"path": str(path)}

            add_artifact("resource", "full_game_map_coverage", coverage)
            add_artifact(
                "resource",
                "asset_inventory",
                {
                    "status": "complete",
                    "asset_root_status": "present",
                    "available_map_count": 1,
                    "missing_map_count": 0,
                    "pak_count": 1,
                    "invalid_pak_count": 0,
                    "invalid_bsp_count": 0,
                    "full_game_asset_ready": True,
                },
            )
            add_artifact(
                "resource",
                "asset_requirements",
                {
                    "schema": "qge.asset_requirements.v0",
                    "status": "satisfied",
                    "target_map_count": 1,
                    "present_map_count": 1,
                    "missing_map_count": 0,
                    "claim_posture": {
                        "asset_requirements_satisfied": True,
                    },
                },
            )
            add_artifact(
                "resource",
                "registered_asset_intake",
                {
                    "schema": "qge.registered_asset_intake.v0",
                    "status": "complete",
                    "candidate_new_map_count": 0,
                    "missing_map_count_after_plan": 0,
                    "copy_plan_count": 0,
                    "post_install_verification_command_count": 1,
                    "post_install_verification": {
                        "commands": [{"kind": "capture_queue"}],
                    },
                    "discovered_candidate_count": 0,
                    "claim_posture": {
                        "asset_intake_copies_game_data": False,
                    },
                },
            )
            add_artifact(
                "resource",
                "envelope",
                {
                    "posture": {
                        "moonlab_simulator_path_claimed": True,
                        "whole_game_hardware_execution_claimed": False,
                    },
                },
            )
            add_artifact(
                "resource",
                "native_backend_boundary",
                {
                    "status": "pass",
                    "required_target_count": 3,
                    "passed_target_count": 3,
                    "blocked_target_count": 0,
                },
            )
            add_artifact(
                "resource",
                "moonlab_job_specs",
                {
                    "selected_job_count": 1,
                    "hardware_candidate_job_count": 1,
                    "submission_scope": "unit",
                },
            )
            add_artifact(
                "resource",
                "moonlab_job_results",
                {
                    "overall_status": "simulator_complete_hardware_not_submitted",
                    "completed_simulator_job_count": 1,
                    "completed_native_replay_job_count": 1,
                    "hardware_submitted_job_count": 0,
                    "blocked_job_count": 0,
                },
            )
            add_artifact(
                "resource",
                "moonlab_replay_plan",
                {
                    "schema": "qge.moonlab_replay_plan.v0",
                    "selected_job_count": 1,
                    "hardware_candidate_job_count": 1,
                    "hardware_submitted_job_count": 0,
                    "blocked_job_count": 0,
                },
            )
            add_artifact(
                "resource",
                "moonlab_submission_packet",
                {
                    "schema": "qge.moonlab_submission_packet.v0",
                    "hardware_candidate_job_count": 1,
                    "ready_candidate_count": 1,
                    "blocked_candidate_count": 0,
                    "submitted_candidate_count": 0,
                },
            )
            add_artifact(
                "resource",
                "moonlab_submission_bundle",
                {
                    "schema": "qge.moonlab_submission_bundle.v0",
                    "status": "ready_for_control_plane_submission",
                    "hardware_candidate_job_count": 1,
                    "ready_for_control_plane_submission_count": 1,
                    "calibration_payload_ready_count": 1,
                    "oracle_kernel_ready_count": 1,
                    "qae_observation_ready_count": 1,
                    "grover_schedule_ready_count": 1,
                    "transpilation_required_count": 0,
                    "missing_artifact_candidate_count": 0,
                    "hardware_submission_directly_executable": True,
                    "control_plane_payload_directly_executable": True,
                    "oracle_kernel_directly_executable": True,
                    "qae_observation_directly_executable": True,
                    "grover_schedule_directly_executable": True,
                },
            )
            add_artifact(
                "resource",
                "moonlab_hardware_record_template",
                {
                    "schema": "qge.moonlab_hardware_record_template.v0",
                    "record_schema": "qge.moonlab_hardware_record.v0",
                    "job_id": "unit.job",
                    "candidate_digest": "abc123",
                },
            )
            add_artifact(
                "resource",
                "moonlab_hardware_submission_scope",
                {
                    "schema": "qge.moonlab_hardware_submission_scope.v0",
                    "status": "ready_for_control_plane_submission",
                    "hardware_submission_scope_ready": True,
                    "hardware_candidate_job_count": 1,
                    "ready_for_control_plane_submission_count": 1,
                    "passing_check_count": 1,
                    "attention_check_count": 0,
                    "out_of_scope": ["whole_game_hardware_execution"],
                },
            )
            add_artifact(
                "resource",
                "moonlab_full_game_plan",
                {
                    "schema": "qge.moonlab_full_game_deployment_plan.v0",
                    "status": "blocked_asset_unavailable",
                    "target_map_count": 1,
                    "covered_map_count": 1,
                    "missing_map_count": 0,
                    "asset_unavailable_map_count": 0,
                    "claim_posture": {
                        "whole_game_moonlab_deployment_claimed": False,
                    },
                },
            )
            add_artifact(
                "resource",
                "moonlab_deployment_gate",
                {
                    "schema": "qge.moonlab_deployment_gate.v0",
                    "status": "blocked",
                    "failed_criterion_count": 4,
                    "blocker_count": 4,
                    "whole_game_moonlab_deployment_claim_allowed": False,
                    "whole_game_hardware_execution_claim_allowed": False,
                    "hardware_quantum_advantage_claim_allowed": False,
                    "dense_70000_qubit_state_claim_allowed": False,
                    "summary": {
                        "target_map_count": 1,
                        "covered_map_count": 1,
                        "coverage_missing_map_count": 0,
                        "asset_missing_map_count": 0,
                        "invalid_bsp_count": 0,
                        "registered_asset_install_script": "install.sh",
                        "registered_asset_intake_file": "intake.json",
                        "post_install_verification_command_count": 1,
                        "post_install_capture_queue_command_present": True,
                        "post_install_capture_queue_command": "capture",
                        "post_install_capture_queue_script": "capture.sh",
                    },
                },
            )
            add_artifact(
                "advantage",
                "metrics",
                {
                    "advantage_problem_id": "unit.advantage",
                    "scaling_summary": {"trial_count": 1},
                    "comparison": {
                        "best_classical": {"algorithm": "classical"},
                        "best_qae": {"algorithm": "qae"},
                    },
                    "resource_estimate": {"logical_qubits": 3},
                },
            )
            add_artifact(
                "advantage",
                "qae_moonlab_payload",
                {
                    "schema": "qge.moonlab_qae_payload.v0",
                    "status": "payload_ready",
                    "semantic_scope": "unit_payload",
                    "payload_resource_estimate": {"circuit_count": 1},
                    "claim_posture": {
                        "full_qae_oracle_transpiled": False,
                    },
                },
            )
            add_artifact(
                "advantage",
                "qae_moonlab_oracle_kernel",
                {
                    "schema": "qge.moonlab_qae_oracle_kernel.v0",
                    "status": "kernel_ready",
                    "semantic_scope": "unit_kernel",
                    "resource_estimate": {"gate_count": 7},
                    "moonlab_control_plane": {
                        "control_plane_executable": True,
                    },
                    "claim_posture": {
                        "qf_oracle_kernel_transpiled": True,
                        "full_qae_oracle_transpiled": False,
                    },
                },
            )
            add_artifact(
                "advantage",
                "qae_moonlab_observation_zero",
                {
                    "schema": "qge.moonlab_qae_observation_circuit.v0",
                    "status": "observation_ready",
                    "semantic_scope": "unit_observation",
                    "resource_estimate": {"gate_count": 9},
                    "state_preparation": {"candidate_count": 1},
                    "moonlab_control_plane": {
                        "control_plane_executable": True,
                    },
                    "claim_posture": {
                        "candidate_state_preparation_transpiled": True,
                        "power_zero_observation_transpiled": True,
                        "full_qae_oracle_transpiled": False,
                    },
                },
            )
            add_artifact(
                "advantage",
                "qae_moonlab_grover_schedule_plan",
                {
                    "schema": "qge.moonlab_qae_grover_schedule_plan.v0",
                    "status": "schedule_ready",
                    "semantic_scope": "unit_schedule",
                    "resource_estimate": {"observation_count": 1},
                    "moonlab_control_plane": {
                        "ready_observation_count": 1,
                        "blocked_observation_count": 0,
                        "first_blocked_power": None,
                    },
                    "claim_posture": {
                        "full_mlae_schedule_transpiled": True,
                        "full_qae_oracle_transpiled": True,
                    },
                },
            )
            manifest["runtime_summary"] = (
                manifest_summary_audit.expected_runtime_summary(manifest))
            manifest["advantage_summary"] = (
                manifest_summary_audit.expected_advantage_summary(manifest))
            self.assertEqual(
                manifest["runtime_summary"]["performance_status"], "pass")
            self.assertEqual(
                manifest["advantage_summary"][
                    "moonlab_deployment_gate_summary"]["blocker_count"],
                4,
            )

            audit = manifest_summary_audit.manifest_summary_audit(manifest)
            self.assertTrue(audit["passed"])
            self.assertEqual(audit["mismatch_count"], 0)

            stale_manifest = json.loads(json.dumps(manifest))
            stale_manifest["runtime_summary"]["performance_status"] = "blocked"
            stale_manifest[
                "advantage_summary"
            ]["moonlab_deployment_gate_summary"]["blocker_count"] = 0
            stale_audit = manifest_summary_audit.manifest_summary_audit(
                stale_manifest)
            self.assertFalse(stale_audit["passed"])
            self.assertTrue(any(
                item.get("path") == "runtime_summary.performance_status"
                for item in stale_audit["mismatches"]["runtime_summary"]
            ))
            self.assertTrue(any(
                item.get("path") == (
                    "advantage_summary."
                    "moonlab_deployment_gate_summary.blocker_count")
                for item in stale_audit["mismatches"]["advantage_summary"]
            ))

    def test_manifest_summaries_and_icc_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            manifest_path = tmpdir / "manifest.json"
            publication_pack.write_json(
                manifest_path,
                {
                    "status": "complete",
                    "frames_requested": 1,
                    "frames_captured": 1,
                    "trace_requested": 1,
                    "trace_status": "copied",
                    "trace_bytes": 128,
                    "run": {
                        "status": "ok",
                        "success": 1,
                        "startup_issue": "",
                        "process_status": 0,
                        "timed_out": 0,
                    },
                    "performance": {
                        "status": "pass",
                        "summary_file": "performance/qge_perf_summary.json",
                        "icc_evidence_file": "performance/qge_perf_icc_evidence.json",
                    },
                },
            )
            summary = publication_pack.agent_manifest_summary(manifest_path)
            self.assertEqual(summary["run_status"], "ok")
            self.assertEqual(summary["frames_captured"], 1)
            self.assertFalse(publication_pack.explicit_agent_run_failure(summary))

            summary["startup_issue"] = "process_exit_1"
            self.assertTrue(publication_pack.explicit_agent_run_failure(summary))

            perf_path = tmpdir / "qge_perf_summary.json"
            publication_pack.write_json(
                perf_path,
                {
                    "status": "blocked",
                    "aggregate": {
                        "engine_average_quantum_ms_max": 33.0,
                        "render_time_ms_max": 44.0,
                        "threshold_failures": [{"metric": "render_time_ms"}],
                        "metric_evidence_present": True,
                    },
                },
            )
            perf = publication_pack.performance_summary(perf_path)
            self.assertTrue(publication_pack.explicit_performance_failure(perf))
            self.assertEqual(perf["render_time_ms_max"], 44.0)

            breadth_path = tmpdir / "breadth_evidence.json"
            publication_pack.write_json(
                breadth_path,
                {
                    "status": "success",
                    "aggregate": {
                        "breadth_ready_for_complete_claim": True,
                        "matrix_run_count": 4,
                        "ready_matrix_run_count": 4,
                        "map_count": 4,
                        "maps": ["e1m1", "e1m2", "e1m3", "e1m4"],
                        "total_fallback_count": 0,
                        "total_surrogate_count": 0,
                        "total_cpu_idwt_count": 0,
                        "total_native_bridge_count": 420,
                        "total_backend_gate_event_count": 12,
                        "total_runtime_backend_probe_event_count": 16,
                        "runtime_backend_probe_resolved_run_count": 4,
                        "runtime_backend_probe_targets": [
                            "qge_context_get_or_create_render_acceleration",
                            "qge_dwt_render",
                            "qge_metal_init_common",
                        ],
                        "required_runtime_backend_probe_targets": [
                            "qge_context_get_or_create_render_acceleration",
                            "qge_dwt_render",
                            "qge_metal_init_common",
                        ],
                        "runtime_backend_probe_missing_targets": [],
                        "runtime_backend_probe_native_targets": [
                            "qge_context_get_or_create_render_acceleration",
                            "qge_dwt_render",
                            "qge_metal_init_common",
                        ],
                    },
                },
            )
            breadth = publication_pack.breadth_evidence_summary(breadth_path)
            self.assertFalse(
                publication_pack.explicit_breadth_evidence_failure(breadth))
            self.assertEqual(breadth["map_count"], 4)
            self.assertEqual(
                breadth["full_game_map_coverage_status"], "partial")
            self.assertEqual(breadth["full_game_map_target_count"], 32)
            self.assertEqual(breadth["full_game_map_covered_count"], 4)
            self.assertEqual(
                breadth["total_runtime_backend_probe_event_count"], 16)

        resource_envelope = publication_pack.build_resource_envelope(
            {
                "cost_model": {"candidate_count": 8, "shots": 64},
                "sample_space": {"candidate_count": 8, "register_bits": 3},
                "snapshot": {
                    "render": {
                        "shots": 64,
                        "gates": 26,
                        "idwt_path": "native_sparse_dwt_render_bridge",
                        "idwt_backend": "native",
                        "cpu_idwt": 0,
                    }
                },
            },
            {
                "comparison": {"best_qae": {"shots": 8}},
                "resource_estimate": {
                    "logical_qubits": 11,
                    "candidate_index_bits": 3,
                    "contribution_threshold_bits": 5,
                    "controlled_oracle_calls": 96,
                    "one_qubit_gates": 1152,
                    "two_qubit_gates": 768,
                    "circuit_depth": 140,
                },
            },
            {
                "ready_for_complete_claim": True,
                "fallback_count": 0,
                "qge_surface_surrogates": 0,
            },
            {
                "runtime_backend_probe_resolved": True,
                "required_runtime_backend_probe_targets": [
                    "qge_dwt_render",
                ],
                "runtime_backend_probe_native_targets": [
                    "qge_dwt_render",
                ],
                "runtime_backend_probe_missing_targets": [],
            },
            {
                "breadth_ready_for_complete_claim": True,
                "map_count": 4,
                "maps": ["e1m1", "e1m2", "e1m3", "e1m4"],
                "total_fallback_count": 0,
                "total_surrogate_count": 0,
                "total_cpu_idwt_count": 0,
                "total_native_bridge_count": 420,
            },
        )
        self.assertFalse(
            resource_envelope["posture"]["whole_game_hardware_execution_claimed"])
        self.assertEqual(
            resource_envelope["domains"]["render_primary_framebuffer"]
            ["status"],
            "captured_workload_ready")
        self.assertEqual(
            resource_envelope["domains"]["light_transport_qae_benchmark"]
            ["logical_qubits"],
            11)
        self.assertEqual(
            resource_envelope["domains"]["full_game_map_coverage"]["status"],
            "partial")
        self.assertEqual(
            resource_envelope["domains"]["full_game_map_coverage"]
            ["covered_map_count"],
            4)
        with tempfile.TemporaryDirectory() as tmp:
            jobs_tmp = Path(tmp)
            oracle_scene_path = jobs_tmp / "oracle_scene.json"
            advantage_metrics_path = jobs_tmp / "advantage_metrics.json"
            qae_circuit_path = jobs_tmp / "qae_circuit.txt"
            qae_moonlab_payload_path = jobs_tmp / "qae_moonlab_payload.json"
            qae_oracle_kernel_path = (
                jobs_tmp / "qae_moonlab_oracle_kernel.json")
            qae_oracle_kernel_circuit_path = (
                jobs_tmp / "qae_moonlab_oracle_kernel.moonlab")
            qae_observation_path = (
                jobs_tmp / "qae_moonlab_observation_zero.json")
            qae_observation_circuit_path = (
                jobs_tmp / "qae_moonlab_observation_zero.moonlab")
            qae_grover_plan_path = (
                jobs_tmp / "qae_moonlab_grover_schedule_plan.json")
            moonlab_circuit_path = jobs_tmp / "observation_000.moonlab"
            trace_path = jobs_tmp / "qge_trace.bin"
            frame_path = jobs_tmp / "frame_001.png"
            vanilla_matrix_path = jobs_tmp / "vanilla_capture_matrix.json"
            performance_path = jobs_tmp / "qge_perf_summary.json"
            breadth_path = jobs_tmp / "breadth_evidence.json"
            full_game_path = jobs_tmp / "qge_full_game_map_coverage.json"
            asset_inventory_path = jobs_tmp / "qge_asset_inventory.json"
            asset_requirements_path = (
                jobs_tmp / "qge_asset_requirements.json")
            registered_asset_intake_path = (
                jobs_tmp / "qge_registered_asset_intake.json")
            publication_pack.write_json(oracle_scene_path, {"scene": {}})
            publication_pack.write_json(
                advantage_metrics_path,
                {
                    "advantage_problem_id": "advantage.test",
                    "comparison": {
                        "best_qae": {
                            "mean_reference_value": 0.5,
                            "rmse": 0.01,
                            "shots": 8,
                            "oracle_eval_count": 24,
                        },
                    },
                },
            )
            qae_circuit_path.write_text(
                "QGE QAE abstract circuit v0\n"
                "logical_qubits: 19\n",
                encoding="utf-8",
            )
            moonlab_circuit_path.write_text(
                "# moonlab-circuit v1\nNUM_QUBITS 1\nRY 0 1.5707963267948966\n",
                encoding="utf-8",
            )
            qae_oracle_kernel_circuit_path.write_text(
                "# moonlab-circuit v1\nNUM_QUBITS 4\nX 0\nCNOT 1 0\n",
                encoding="utf-8",
            )
            qae_observation_circuit_path.write_text(
                "# moonlab-circuit v1\nNUM_QUBITS 4\nRY 0 1.0\nCNOT 1 0\n",
                encoding="utf-8",
            )
            publication_pack.write_json(
                qae_moonlab_payload_path,
                {
                    "schema": "qge.moonlab_qae_payload.v0",
                    "status": (
                        "calibration_payload_ready_"
                        "oracle_transpilation_required"),
                    "semantic_scope": "mlae_observation_distribution_payload",
                    "payload_resource_estimate": {
                        "logical_qubits": 1,
                        "circuit_count": 1,
                        "total_shots": 8,
                    },
                    "observation_circuits": [
                        {
                            "observation_index": 0,
                            "moonlab_circuit_file": str(moonlab_circuit_path),
                            "shots": 8,
                        },
                    ],
                    "claim_posture": {
                        "full_qae_oracle_transpiled": False,
                    },
                },
            )
            publication_pack.write_json(
                qae_oracle_kernel_path,
                {
                    "schema": "qge.moonlab_qae_oracle_kernel.v0",
                    "status": (
                        "qf_oracle_kernel_ready_"
                        "qae_transpilation_required"),
                    "semantic_scope": "bernoulli_lift_qf_oracle_kernel",
                    "moonlab_circuit_file": str(
                        qae_oracle_kernel_circuit_path),
                    "moonlab_control_plane": {
                        "control_plane_executable": True,
                        "body_bytes": (
                            qae_oracle_kernel_circuit_path.stat().st_size),
                    },
                    "resource_estimate": {
                        "logical_qubits": 4,
                        "gate_count": 2,
                    },
                    "claim_posture": {
                        "qf_oracle_kernel_transpiled": True,
                        "full_qae_oracle_transpiled": False,
                    },
                },
            )
            publication_pack.write_json(
                qae_observation_path,
                {
                    "schema": "qge.moonlab_qae_observation_circuit.v0",
                    "status": (
                        "qae_observation_zero_ready_"
                        "grover_schedule_required"),
                    "semantic_scope": (
                        "bernoulli_lift_qae_power_zero_observation"),
                    "moonlab_circuit_file": str(
                        qae_observation_circuit_path),
                    "moonlab_control_plane": {
                        "control_plane_executable": True,
                        "body_bytes": (
                            qae_observation_circuit_path.stat().st_size),
                    },
                    "resource_estimate": {
                        "logical_qubits": 4,
                        "gate_count": 2,
                    },
                    "claim_posture": {
                        "candidate_state_preparation_transpiled": True,
                        "qf_oracle_kernel_transpiled": True,
                        "power_zero_observation_transpiled": True,
                        "full_qae_oracle_transpiled": False,
                    },
                },
            )
            publication_pack.write_json(
                qae_grover_plan_path,
                {
                    "schema": "qge.moonlab_qae_grover_schedule_plan.v0",
                    "status": (
                        "qae_grover_schedule_blocked_"
                        "control_plane_body_limit"),
                    "semantic_scope": (
                        "bernoulli_lift_qae_grover_schedule_"
                        "control_plane_plan"),
                    "moonlab_control_plane": {
                        "body_limit_bytes": 4194304,
                        "ready_observation_count": 1,
                        "blocked_observation_count": 1,
                        "first_blocked_power": 1,
                    },
                    "resource_estimate": {
                        "logical_qubits": 4,
                        "observation_count": 2,
                        "power_zero_body_bytes": 128,
                    },
                    "claim_posture": {
                        "full_mlae_schedule_transpiled": False,
                        "full_qae_oracle_transpiled": False,
                        "hardware_result_claimed": False,
                    },
                },
            )
            trace_path.write_bytes(b"trace")
            frame_path.write_bytes(b"png")
            publication_pack.write_json(
                vanilla_matrix_path,
                {
                    "conformance_summary": {
                        "ready_for_complete_claim": True,
                        "fallback_count": 0,
                        "qge_surface_surrogates": 0,
                    },
                },
            )
            publication_pack.write_json(
                performance_path,
                {
                    "aggregate": {
                        "runtime_backend_probe_resolved": True,
                        "runtime_backend_probe_event_count": 3,
                        "required_runtime_backend_probe_targets": [
                            "qge_dwt_render",
                        ],
                        "runtime_backend_probe_native_targets": [
                            "qge_dwt_render",
                        ],
                        "runtime_backend_probe_missing_targets": [],
                        "runtime_backend_probe_proofs": {
                            "qge_dwt_render": {
                                "native_bridge_evidence": True,
                            },
                        },
                    },
                },
            )
            publication_pack.write_json(
                breadth_path,
                {
                    "aggregate": {
                        "map_count": 4,
                        "runtime_backend_probe_run_count": 4,
                        "runtime_backend_probe_resolved_run_count": 4,
                        "total_runtime_backend_probe_event_count": 16,
                        "runtime_backend_probe_targets": ["qge_dwt_render"],
                        "runtime_backend_probe_paths": [
                            "native_sparse_dwt_render_bridge",
                        ],
                        "runtime_backend_probe_missing_targets": [],
                        "runtime_backend_probe_native_targets": [
                            "qge_dwt_render",
                        ],
                        "runtime_backend_probe_proofs": {
                            "qge_dwt_render": {
                                "native_bridge_run_count": 4,
                            },
                        },
                        "total_native_bridge_count": 420,
                    },
                },
            )
            publication_pack.write_json(
                full_game_path,
                resource_envelope["domains"]["full_game_map_coverage"],
            )
            publication_pack.write_json(
                asset_inventory_path,
                {
                    "schema": "qge.asset_inventory.v0",
                    "available_map_count": 4,
                    "missing_map_count": 28,
                    "full_game_asset_ready": False,
                },
            )
            publication_pack.write_json(
                asset_requirements_path,
                {
                    "schema": "qge.asset_requirements.v0",
                    "status": "blocked_missing_registered_assets",
                    "present_map_count": 4,
                    "missing_map_count": 28,
                    "claim_posture": {
                        "asset_requirements_satisfied": False,
                    },
                },
            )
            publication_pack.write_json(
                registered_asset_intake_path,
                {
                    "schema": "qge.registered_asset_intake.v0",
                    "status": "blocked_no_candidate_assets",
                    "candidate_new_map_count": 0,
                    "missing_map_count_after_plan": 28,
                    "claim_posture": {
                        "asset_intake_copies_game_data": False,
                    },
                },
            )
            moonlab_job_specs = publication_pack.build_moonlab_job_specs(
                resource_envelope,
                {
                    "oracle_scene": str(oracle_scene_path),
                    "advantage_metrics": str(advantage_metrics_path),
                    "qae_circuit": str(qae_circuit_path),
                    "moonlab_qae_payload": str(qae_moonlab_payload_path),
                    "moonlab_qae_oracle_kernel": str(
                        qae_oracle_kernel_path),
                    "moonlab_qae_observation_zero": str(
                        qae_observation_path),
                    "moonlab_qae_grover_schedule_plan": str(
                        qae_grover_plan_path),
                    "trace": str(trace_path),
                    "frame": str(frame_path),
                    "vanilla_matrix": str(vanilla_matrix_path),
                    "performance_summary": str(performance_path),
                    "breadth_evidence": str(breadth_path),
                    "full_game_map_coverage": str(full_game_path),
                    "asset_inventory": str(asset_inventory_path),
                    "asset_requirements": str(asset_requirements_path),
                    "registered_asset_intake": str(
                        registered_asset_intake_path),
                },
            )
            moonlab_job_results = (
                moonlab_job_runner.build_moonlab_job_results(
                    moonlab_job_specs)
            )
            self.assertEqual(
                moonlab_job_specs["schema"], "qge.moonlab_job_specs.v0")
            self.assertEqual(moonlab_job_specs["selected_job_count"], 4)
            self.assertEqual(
                moonlab_job_specs["hardware_candidate_job_count"], 1)
            self.assertEqual(
                moonlab_job_specs["full_game_map_coverage_status"],
                "partial")
            self.assertFalse(
                moonlab_job_specs["posture"]
                ["whole_game_hardware_execution_claimed"])
            self.assertEqual(
                moonlab_job_specs["jobs"][1]["hardware_submission_status"],
                "not_submitted")
            self.assertEqual(
                moonlab_job_specs["jobs"][1]["required_artifacts"]
                ["moonlab_qae_grover_schedule_plan"],
                str(qae_grover_plan_path))
            self.assertEqual(
                moonlab_job_results["schema"], "qge.moonlab_job_results.v0")
            self.assertEqual(
                moonlab_job_results["completed_simulator_job_count"], 4)
            self.assertEqual(
                moonlab_job_results["completed_native_replay_job_count"], 2)
            self.assertEqual(
                moonlab_job_results["hardware_submitted_job_count"], 0)
            self.assertEqual(moonlab_job_results["blocked_job_count"], 0)
            runtime_job = next(
                job for job in moonlab_job_results["jobs"]
                if job["domain"] == "runtime_backend_probes")
            self.assertEqual(
                runtime_job["observations"]["performance_native_targets"],
                ["qge_dwt_render"])
            self.assertEqual(
                runtime_job["observations"]
                ["performance_runtime_backend_probe_event_count"],
                3)
            self.assertTrue(
                runtime_job["observations"]
                ["performance_runtime_backend_probe_resolved"])
            self.assertEqual(
                runtime_job["observations"]["breadth_map_count"], 4)
            self.assertEqual(
                runtime_job["observations"]
                ["breadth_total_runtime_backend_probe_event_count"],
                16)
            self.assertEqual(
                runtime_job["observations"]
                ["breadth_runtime_backend_probe_resolved_run_count"],
                4)
            self.assertEqual(
                runtime_job["observations"]
                ["breadth_total_native_bridge_count"],
                420)
            full_game_job = next(
                job for job in moonlab_job_results["jobs"]
                if job["domain"] == "full_game_map_coverage")
            self.assertEqual(
                full_game_job["observations"]["asset_requirement_status"],
                "blocked_missing_registered_assets")
            self.assertEqual(
                full_game_job["observations"]
                ["asset_requirements_missing_map_count"],
                28)
            self.assertFalse(
                full_game_job["observations"]["asset_requirements_satisfied"])
            moonlab_specs_path = jobs_tmp / "qge_moonlab_job_specs.json"
            moonlab_results_path = jobs_tmp / "qge_moonlab_job_results.json"
            moonlab_verify_path = (
                jobs_tmp / "qge_moonlab_job_results.verify.json"
            )
            moonlab_replay_plan_path = (
                jobs_tmp / "qge_moonlab_replay_plan.json"
            )
            moonlab_submission_packet_path = (
                jobs_tmp / "qge_moonlab_submission_packet.json"
            )
            publication_pack.write_json(moonlab_specs_path, moonlab_job_specs)
            moonlab_stdout = io.StringIO()
            with contextlib.redirect_stdout(moonlab_stdout):
                self.assertEqual(
                    moonlab_job_runner.main([
                        str(moonlab_specs_path),
                        "--out",
                        str(moonlab_results_path),
                    ]),
                    0,
                )
            self.assertIn(
                "QGE_MOONLAB_JOB_RESULTS",
                moonlab_stdout.getvalue(),
            )
            moonlab_cli_results = publication_pack.load_json(
                moonlab_results_path)
            self.assertEqual(
                moonlab_cli_results["schema"], "qge.moonlab_job_results.v0")
            self.assertEqual(
                moonlab_cli_results["completed_simulator_job_count"], 4)
            moonlab_replay_plan = (
                moonlab_job_runner.build_moonlab_replay_plan(
                    moonlab_job_specs,
                    moonlab_cli_results,
                    job_specs_path=moonlab_specs_path,
                    job_results_path=moonlab_results_path,
                )
            )
            self.assertEqual(
                moonlab_replay_plan["schema"],
                "qge.moonlab_replay_plan.v0")
            self.assertEqual(
                moonlab_replay_plan["selected_job_count"], 4)
            self.assertEqual(
                moonlab_replay_plan["hardware_submitted_job_count"], 0)
            self.assertIn(
                "--expect",
                moonlab_replay_plan["pack_validation"]
                ["verify_results_command"],
            )
            moonlab_submission_packet = (
                moonlab_job_runner.build_moonlab_submission_packet(
                    moonlab_job_specs,
                    moonlab_cli_results,
                    job_specs_path=moonlab_specs_path,
                    job_results_path=moonlab_results_path,
                )
            )
            self.assertEqual(
                moonlab_submission_packet["schema"],
                "qge.moonlab_submission_packet.v0")
            self.assertEqual(
                moonlab_submission_packet["hardware_candidate_job_count"], 1)
            self.assertEqual(
                moonlab_submission_packet["ready_candidate_count"], 1)
            self.assertEqual(
                moonlab_submission_packet["submitted_candidate_count"], 0)
            self.assertEqual(
                moonlab_submission_packet["candidate_jobs"][0]
                ["submission_status"],
                "ready_for_hardware_submission_metadata")
            submission_bundle = (
                moonlab_submission_bundle.build_submission_bundle(
                    moonlab_submission_packet,
                    packet_path=moonlab_submission_packet_path,
                )
            )
            self.assertEqual(
                submission_bundle["schema"],
                "qge.moonlab_submission_bundle.v0")
            self.assertEqual(
                submission_bundle["status"],
                "qae_observation_zero_ready_grover_schedule_required")
            self.assertEqual(
                submission_bundle["transpilation_required_count"], 1)
            self.assertEqual(
                submission_bundle[
                    "ready_for_control_plane_submission_count"],
                0)
            self.assertEqual(
                submission_bundle["calibration_payload_ready_count"], 1)
            self.assertEqual(
                submission_bundle["oracle_kernel_ready_count"], 1)
            self.assertEqual(
                submission_bundle["qae_observation_ready_count"], 1)
            self.assertFalse(
                submission_bundle[
                    "hardware_submission_directly_executable"])
            self.assertTrue(
                submission_bundle[
                    "control_plane_payload_directly_executable"])
            self.assertTrue(
                submission_bundle["oracle_kernel_directly_executable"])
            self.assertTrue(
                submission_bundle[
                    "qae_observation_directly_executable"])
            self.assertEqual(
                submission_bundle["candidate_jobs"][0]
                ["qae_circuit_check"]["format"],
                "qge_abstract_qae_circuit_v0")
            self.assertEqual(
                submission_bundle["candidate_jobs"][0]
                ["moonlab_qae_payload_check"]["semantic_scope"],
                "mlae_observation_distribution_payload")
            self.assertEqual(
                submission_bundle["candidate_jobs"][0]
                ["moonlab_qae_oracle_kernel_check"]["semantic_scope"],
                "bernoulli_lift_qf_oracle_kernel")
            self.assertEqual(
                submission_bundle["candidate_jobs"][0]
                ["moonlab_qae_observation_zero_check"]["semantic_scope"],
                "bernoulli_lift_qae_power_zero_observation")
            moonlab_verify_stdout = io.StringIO()
            with contextlib.redirect_stdout(moonlab_verify_stdout):
                self.assertEqual(
                    moonlab_job_runner.main([
                        str(moonlab_specs_path),
                        "--out",
                        str(moonlab_verify_path),
                        "--expect",
                        str(moonlab_results_path),
                        "--plan-out",
                        str(moonlab_replay_plan_path),
                        "--submission-out",
                        str(moonlab_submission_packet_path),
                    ]),
                    0,
                )
            self.assertIn(
                "QGE_MOONLAB_EXPECTED_RESULTS_MATCH",
                moonlab_verify_stdout.getvalue(),
            )
            self.assertIn(
                "QGE_MOONLAB_REPLAY_PLAN",
                moonlab_verify_stdout.getvalue(),
            )
            self.assertIn(
                "QGE_MOONLAB_SUBMISSION_PACKET",
                moonlab_verify_stdout.getvalue(),
            )
            replay_plan_json = publication_pack.load_json(
                moonlab_replay_plan_path)
            self.assertEqual(
                replay_plan_json["schema"], "qge.moonlab_replay_plan.v0")
            self.assertEqual(replay_plan_json["selected_job_count"], 4)
            self.assertEqual(
                replay_plan_json["jobs"][0]["validation_checks"][0]
                ["status"],
                "pass",
            )
            submission_packet_json = publication_pack.load_json(
                moonlab_submission_packet_path)
            self.assertEqual(
                submission_packet_json["schema"],
                "qge.moonlab_submission_packet.v0")
            self.assertEqual(
                submission_packet_json["candidate_jobs"][0]
                ["moonlab_submission_contract"]
                ["submission_mode"],
                "moonlab_hardware_backend_handoff")

        manifest = {
            "pack_dir": "pack",
            "artifacts": {
                "oracle": {
                    "oracle_scene": {"path": "oracle_scene.json"},
                    "claims_evidence": {"path": "claims_evidence.json"},
                },
                "advantage": {
                    "metrics": {"path": "advantage_metrics.json"},
                    "qae_moonlab_payload": {
                        "path": "advantage/qae_moonlab_payload.json"
                    },
                    "qae_moonlab_payload_markdown": {
                        "path": "advantage/qae_moonlab_payload.md"
                    },
                    "qae_moonlab_payload_icc_evidence": {
                        "path": (
                            "advantage/"
                            "qae_moonlab_payload_icc_evidence.json")
                    },
                    "qae_moonlab_circuits": {"file_count": 4},
                    "qae_moonlab_oracle_kernel": {
                        "path": "advantage/qae_moonlab_oracle_kernel.json",
                    },
                    "qae_moonlab_oracle_kernel_circuit": {
                        "path": (
                            "advantage/"
                            "qae_moonlab_oracle_kernel.moonlab"),
                    },
                    "qae_moonlab_oracle_kernel_markdown": {
                        "path": "advantage/qae_moonlab_oracle_kernel.md",
                    },
                    "qae_moonlab_oracle_kernel_icc_evidence": {
                        "path": (
                            "advantage/"
                            "qae_moonlab_oracle_kernel_icc_evidence.json"),
                    },
                    "qae_moonlab_observation_zero": {
                        "path": (
                            "advantage/"
                            "qae_moonlab_observation_zero.json"),
                    },
                    "qae_moonlab_observation_zero_circuit": {
                        "path": (
                            "advantage/"
                            "qae_moonlab_observation_zero.moonlab"),
                    },
                    "qae_moonlab_observation_zero_markdown": {
                        "path": (
                            "advantage/"
                            "qae_moonlab_observation_zero.md"),
                    },
                    "qae_moonlab_observation_zero_icc_evidence": {
                        "path": (
                            "advantage/"
                            "qae_moonlab_observation_zero_icc_evidence.json"),
                    },
                    "qae_moonlab_grover_schedule_plan": {
                        "path": (
                            "advantage/"
                            "qae_moonlab_grover_schedule_plan.json"),
                    },
                    "qae_moonlab_grover_schedule_plan_markdown": {
                        "path": (
                            "advantage/"
                            "qae_moonlab_grover_schedule_plan.md"),
                    },
                    "qae_moonlab_grover_schedule_plan_icc_evidence": {
                        "path": (
                            "advantage/"
                            "qae_moonlab_grover_schedule_plan_icc_evidence.json"),
                    },
                    "scaling_summary": {"path": "scaling_summary.json"},
                },
                "resource": {
                    "envelope": {"path": "resource/qge_resource_envelope.json"},
                    "full_game_map_coverage": {
                        "path": "resource/qge_full_game_map_coverage.json"
                    },
                    "asset_inventory": {
                        "path": "resource/qge_asset_inventory.json"
                    },
                    "asset_requirements": {
                        "path": "resource/qge_asset_requirements.json"
                    },
                    "asset_requirements_markdown": {
                        "path": "resource/qge_asset_requirements.md"
                    },
                    "asset_requirements_icc_evidence": {
                        "path": (
                            "resource/"
                            "qge_asset_requirements_icc_evidence.json")
                    },
                    "native_backend_boundary": {
                        "path": "resource/qge_native_backend_boundary.json"
                    },
                    "moonlab_job_specs": {
                        "path": "resource/qge_moonlab_job_specs.json"
                    },
                    "moonlab_job_results": {
                        "path": "resource/qge_moonlab_job_results.json"
                    },
                    "moonlab_replay_plan": {
                        "path": "resource/qge_moonlab_replay_plan.json"
                    },
                    "moonlab_submission_packet": {
                        "path": "resource/qge_moonlab_submission_packet.json"
                    },
                    "moonlab_submission_bundle": {
                        "path": "resource/qge_moonlab_submission_bundle.json"
                    },
                    "moonlab_submission_bundle_markdown": {
                        "path": "resource/qge_moonlab_submission_bundle.md"
                    },
                    "moonlab_submission_bundle_icc_evidence": {
                        "path": (
                            "resource/"
                            "qge_moonlab_submission_bundle_icc_evidence.json")
                    },
                    "moonlab_hardware_record_template": {
                        "path": (
                            "resource/"
                            "qge_moonlab_hardware_record_template.json")
                    },
                    "moonlab_hardware_submission_scope": {
                        "path": (
                            "resource/"
                            "qge_moonlab_hardware_submission_scope.json")
                    },
                    "moonlab_hardware_submission_scope_icc_evidence": {
                        "path": (
                            "resource/"
                            "qge_moonlab_hardware_submission_scope_icc_evidence.json")
                    },
                    "moonlab_full_game_plan": {
                        "path": "resource/qge_moonlab_full_game_plan.json"
                    },
                    "moonlab_full_game_plan_markdown": {
                        "path": "resource/qge_moonlab_full_game_plan.md"
                    },
                    "moonlab_full_game_plan_icc_evidence": {
                        "path": (
                            "resource/"
                            "qge_moonlab_full_game_plan_icc_evidence.json")
                    },
                    "moonlab_deployment_gate": {
                        "path": "resource/qge_moonlab_deployment_gate.json"
                    },
                    "moonlab_deployment_gate_markdown": {
                        "path": "resource/qge_moonlab_deployment_gate.md"
                    },
                    "moonlab_deployment_gate_icc_evidence": {
                        "path": (
                            "resource/"
                            "qge_moonlab_deployment_gate_icc_evidence.json")
                    },
                },
                "vanilla": {
                    "matrix": {"packed": {"path": "vanilla_capture_matrix.json"}},
                    "icc_evidence": {
                        "packed": {
                            "path": "vanilla/qge_vanilla_icc_evidence.json"
                        }
                    },
                },
                "breadth": {
                    "evidence": {"packed": {"path": "breadth_evidence.json"}},
                    "icc_evidence": {
                        "packed": {"path": "qge_breadth_icc_evidence.json"}
                    },
                },
                "capture": {
                    "performance_summary": {"packed": {"path": "qge_perf_summary.json"}},
                    "performance_icc_evidence": {"packed": {"path": "qge_perf_icc_evidence.json"}},
                },
                "agent_stream": {
                    "manifest": {"packed": {"path": "manifest.json"}},
                    "events": {"packed": {"path": "events.ndjson"}},
                    "stream_directory": {"packed": {"file_count": 7}},
                },
            },
            "advantage_summary": {
                "moonlab_qae_payload_summary": {
                    "schema": "qge.moonlab_qae_payload.v0",
                    "status": (
                        "calibration_payload_ready_"
                        "oracle_transpilation_required"),
                    "semantic_scope": "mlae_observation_distribution_payload",
                    "payload_resource_estimate": {
                        "logical_qubits": 1,
                        "circuit_count": 4,
                        "total_shots": 384,
                    },
                    "full_qae_oracle_transpiled": False,
                },
                "moonlab_qae_oracle_kernel_summary": {
                    "schema": "qge.moonlab_qae_oracle_kernel.v0",
                    "status": (
                        "qf_oracle_kernel_ready_"
                        "qae_transpilation_required"),
                    "semantic_scope": "bernoulli_lift_qf_oracle_kernel",
                    "resource_estimate": {
                        "logical_qubits": 32,
                        "gate_count": 189041,
                        "body_bytes": 3141392,
                    },
                    "control_plane_executable": True,
                    "qf_oracle_kernel_transpiled": True,
                    "full_qae_oracle_transpiled": False,
                },
                "moonlab_qae_observation_zero_summary": {
                    "schema": "qge.moonlab_qae_observation_circuit.v0",
                    "status": (
                        "qae_observation_zero_ready_"
                        "grover_schedule_required"),
                    "semantic_scope": (
                        "bernoulli_lift_qae_power_zero_observation"),
                    "resource_estimate": {
                        "logical_qubits": 32,
                        "gate_count": 98240,
                        "body_bytes": 611783,
                    },
                    "state_preparation": {
                        "candidate_count": 234,
                        "invalid_candidate_probability": 0.0,
                    },
                    "control_plane_executable": True,
                    "candidate_state_preparation_transpiled": True,
                    "power_zero_observation_transpiled": True,
                    "full_qae_oracle_transpiled": False,
                },
                "moonlab_qae_grover_schedule_plan_summary": {
                    "schema": "qge.moonlab_qae_grover_schedule_plan.v0",
                    "status": (
                        "qae_grover_schedule_blocked_"
                        "control_plane_body_limit"),
                    "semantic_scope": (
                        "bernoulli_lift_qae_grover_schedule_"
                        "control_plane_plan"),
                    "resource_estimate": {
                        "logical_qubits": 32,
                        "observation_count": 4,
                        "ready_observation_count": 3,
                        "blocked_observation_count": 1,
                        "first_blocked_power": 4,
                        "power_zero_body_bytes": 611783,
                    },
                    "ready_observation_count": 3,
                    "blocked_observation_count": 1,
                    "first_blocked_power": 4,
                    "grover_schedule_transpiled": False,
                    "full_qae_oracle_transpiled": False,
                },
                "moonlab_job_specs_summary": {
                    "selected_job_count": 4,
                    "hardware_candidate_job_count": 1,
                },
                "moonlab_job_results_summary": {
                    "overall_status": "simulator_complete_hardware_not_submitted",
                    "completed_simulator_job_count": 4,
                    "completed_native_replay_job_count": 2,
                    "hardware_submitted_job_count": 0,
                    "blocked_job_count": 0,
                },
                "moonlab_replay_plan_summary": {
                    "schema": "qge.moonlab_replay_plan.v0",
                    "selected_job_count": 4,
                    "hardware_candidate_job_count": 1,
                    "hardware_submitted_job_count": 0,
                    "blocked_job_count": 0,
                },
                "moonlab_submission_packet_summary": {
                    "schema": "qge.moonlab_submission_packet.v0",
                    "hardware_candidate_job_count": 1,
                    "ready_candidate_count": 1,
                    "blocked_candidate_count": 0,
                    "submitted_candidate_count": 0,
                },
                "moonlab_submission_bundle_summary": {
                    "schema": "qge.moonlab_submission_bundle.v0",
                    "status": (
                        "qae_observation_zero_ready_"
                        "grover_schedule_required"),
                    "hardware_candidate_job_count": 1,
                    "ready_for_control_plane_submission_count": 0,
                    "calibration_payload_ready_count": 1,
                    "oracle_kernel_ready_count": 1,
                    "qae_observation_ready_count": 1,
                    "transpilation_required_count": 1,
                    "missing_artifact_candidate_count": 0,
                    "hardware_submission_directly_executable": False,
                    "control_plane_payload_directly_executable": True,
                    "oracle_kernel_directly_executable": True,
                    "qae_observation_directly_executable": True,
                },
                "moonlab_hardware_record_template_summary": {
                    "schema": "qge.moonlab_hardware_record_template.v0",
                    "record_schema": "qge.moonlab_hardware_record.v0",
                    "job_id": "qge.light_transport_qae_benchmark.mlae.v0",
                    "candidate_digest": "candidate-digest",
                },
                "moonlab_hardware_submission_scope_summary": {
                    "schema": "qge.moonlab_hardware_submission_scope.v0",
                    "status": (
                        "attention_required_for_control_plane_submission"),
                    "hardware_submission_scope_ready": False,
                    "hardware_candidate_job_count": 1,
                    "ready_for_control_plane_submission_count": 0,
                    "passing_check_count": 7,
                    "attention_check_count": 2,
                    "out_of_scope": [
                        "full_game_moonlab_deployment_gate",
                        "registered_bsp_asset_availability",
                    ],
                },
                "moonlab_full_game_plan_summary": {
                    "schema": "qge.moonlab_full_game_deployment_plan.v0",
                    "status": "blocked_asset_unavailable",
                    "target_map_count": 32,
                    "covered_map_count": 4,
                    "missing_map_count": 28,
                    "asset_unavailable_map_count": 28,
                    "whole_game_moonlab_deployment_claimed": False,
                },
                "moonlab_deployment_gate_summary": {
                    "schema": "qge.moonlab_deployment_gate.v0",
                    "status": "blocked",
                    "failed_criterion_count": 4,
                    "blocker_count": 4,
                    "whole_game_moonlab_deployment_claim_allowed": False,
                    "whole_game_hardware_execution_claim_allowed": False,
                    "hardware_quantum_advantage_claim_allowed": False,
                    "dense_70000_qubit_state_claim_allowed": False,
                    "target_map_count": 32,
                    "covered_map_count": 4,
                    "coverage_missing_map_count": 28,
                    "asset_missing_map_count": 28,
                    "invalid_bsp_count": 0,
                },
                "native_backend_boundary_summary": {
                    "status": "pass",
                    "required_target_count": 3,
                    "passed_target_count": 3,
                    "blocked_target_count": 0,
                },
                "full_game_map_coverage_summary": {
                    "status": "partial",
                    "target_map_count": 32,
                    "covered_map_count": 4,
                    "missing_map_count": 28,
                },
                "asset_inventory_summary": {
                    "status": "partial",
                    "available_map_count": 4,
                    "missing_map_count": 28,
                    "invalid_bsp_count": 0,
                    "full_game_asset_ready": False,
                },
                "asset_requirements_summary": {
                    "schema": "qge.asset_requirements.v0",
                    "status": "blocked_missing_registered_assets",
                    "target_map_count": 32,
                    "present_map_count": 4,
                    "missing_map_count": 28,
                    "asset_requirements_satisfied": False,
                },
            },
            "runtime_summary": {
                "publication_ready_for_complete_claim": True,
                "fallback_count": 0,
                "surrogate_count": 0,
                "vanilla_ready_for_complete_claim": True,
                "agent_stream_runs_success": True,
                "vanilla_performance_ok": True,
                "agent_stream_manifest_ok": True,
                "performance_ok": True,
                "breadth_ready_for_complete_claim": True,
                "breadth_map_count": 4,
                "full_game_map_coverage_status": "partial",
                "full_game_map_target_count": 32,
                "full_game_map_covered_count": 4,
                "full_game_map_missing_count": 28,
                "breadth_total_native_bridge_count": 420,
                "breadth_total_runtime_backend_probe_event_count": 16,
                "breadth_runtime_backend_probe_resolved_run_count": 4,
                "breadth_evidence_ok": True,
            },
        }
        icc = publication_pack.build_icc_evidence(
            manifest,
            Path("publication_manifest.json"),
            Path("qge_publication_icc_evidence.json"),
        )
        icc_audit = publication_icc_audit.publication_icc_evidence_audit(
            manifest,
            icc,
            manifest_path=Path("publication_manifest.json"),
            icc_path=Path("qge_publication_icc_evidence.json"),
            required=True,
        )
        self.assertTrue(icc_audit["passed"])
        self.assertEqual(icc_audit["mismatch_count"], 0)
        stale_icc = json.loads(json.dumps(icc))
        stale_icc["moonlab_deployment_gate_blocker_count"] = 0
        stale_icc["hardware_quantum_advantage_claimed"] = True
        stale_audit = publication_icc_audit.publication_icc_evidence_audit(
            manifest,
            stale_icc,
            manifest_path=Path("publication_manifest.json"),
            icc_path=Path("qge_publication_icc_evidence.json"),
            required=True,
        )
        self.assertFalse(stale_audit["passed"])
        self.assertIn(
            "moonlab_deployment_gate_blocker_count",
            stale_audit["field_mismatches"],
        )
        self.assertTrue(any(
            flag.get("flag") == "hardware_quantum_advantage_claimed"
            for flag in stale_audit["overclaim_flags"]
        ))
        self.assertEqual(icc["runtime_backend"], "qge_publication_pack")
        self.assertEqual(icc["completion_reason"], "qge_publication_artifact_pack_complete")
        self.assertTrue(icc["publication_ready_for_complete_claim"])
        self.assertEqual(
            icc["vanilla_icc_evidence_file"],
            "vanilla/qge_vanilla_icc_evidence.json")
        self.assertEqual(
            icc["resource_envelope_file"],
            "resource/qge_resource_envelope.json")
        self.assertEqual(
            icc["full_game_map_coverage_file"],
            "resource/qge_full_game_map_coverage.json")
        self.assertEqual(icc["full_game_map_coverage_status"], "partial")
        self.assertEqual(icc["full_game_map_target_count"], 32)
        self.assertEqual(icc["full_game_map_covered_count"], 4)
        self.assertEqual(icc["full_game_map_missing_count"], 28)
        self.assertEqual(
            icc["asset_inventory_file"],
            "resource/qge_asset_inventory.json")
        self.assertEqual(icc["asset_inventory_status"], "partial")
        self.assertEqual(icc["asset_inventory_available_map_count"], 4)
        self.assertEqual(icc["asset_inventory_missing_map_count"], 28)
        self.assertEqual(icc["asset_inventory_invalid_bsp_count"], 0)
        self.assertFalse(icc["full_game_asset_ready"])
        self.assertEqual(
            icc["asset_requirements_file"],
            "resource/qge_asset_requirements.json")
        self.assertEqual(
            icc["asset_requirements_markdown_file"],
            "resource/qge_asset_requirements.md")
        self.assertEqual(
            icc["asset_requirements_icc_evidence_file"],
            "resource/qge_asset_requirements_icc_evidence.json")
        self.assertEqual(
            icc["asset_requirements_schema"],
            "qge.asset_requirements.v0")
        self.assertEqual(
            icc["asset_requirement_status"],
            "blocked_missing_registered_assets")
        self.assertEqual(icc["asset_requirements_present_map_count"], 4)
        self.assertEqual(icc["asset_requirements_missing_map_count"], 28)
        self.assertFalse(icc["asset_requirements_satisfied"])
        self.assertEqual(
            icc["native_backend_boundary_file"],
            "resource/qge_native_backend_boundary.json")
        self.assertEqual(icc["native_backend_boundary_status"], "pass")
        self.assertEqual(
            icc["native_backend_boundary_passed_target_count"], 3)
        self.assertEqual(
            icc["moonlab_qae_payload_file"],
            "advantage/qae_moonlab_payload.json")
        self.assertEqual(
            icc["moonlab_qae_payload_markdown_file"],
            "advantage/qae_moonlab_payload.md")
        self.assertEqual(
            icc["moonlab_qae_payload_icc_evidence_file"],
            "advantage/qae_moonlab_payload_icc_evidence.json")
        self.assertEqual(icc["moonlab_qae_payload_circuit_file_count"], 4)
        self.assertEqual(
            icc["moonlab_qae_payload_schema"],
            "qge.moonlab_qae_payload.v0")
        self.assertEqual(
            icc["moonlab_qae_payload_status"],
            "calibration_payload_ready_oracle_transpilation_required")
        self.assertEqual(
            icc["moonlab_qae_payload_semantic_scope"],
            "mlae_observation_distribution_payload")
        self.assertFalse(
            icc["moonlab_qae_payload_full_qae_oracle_transpiled"])
        self.assertEqual(
            icc["moonlab_qae_oracle_kernel_file"],
            "advantage/qae_moonlab_oracle_kernel.json")
        self.assertEqual(
            icc["moonlab_qae_oracle_kernel_circuit_file"],
            "advantage/qae_moonlab_oracle_kernel.moonlab")
        self.assertEqual(
            icc["moonlab_qae_oracle_kernel_markdown_file"],
            "advantage/qae_moonlab_oracle_kernel.md")
        self.assertEqual(
            icc["moonlab_qae_oracle_kernel_icc_evidence_file"],
            "advantage/qae_moonlab_oracle_kernel_icc_evidence.json")
        self.assertEqual(
            icc["moonlab_qae_oracle_kernel_schema"],
            "qge.moonlab_qae_oracle_kernel.v0")
        self.assertEqual(
            icc["moonlab_qae_oracle_kernel_status"],
            "qf_oracle_kernel_ready_qae_transpilation_required")
        self.assertEqual(
            icc["moonlab_qae_oracle_kernel_semantic_scope"],
            "bernoulli_lift_qf_oracle_kernel")
        self.assertTrue(
            icc["moonlab_qae_oracle_kernel_control_plane_executable"])
        self.assertTrue(
            icc["moonlab_qae_qf_oracle_kernel_transpiled"])
        self.assertFalse(
            icc[
                "moonlab_qae_oracle_kernel_full_qae_oracle_transpiled"])
        self.assertEqual(
            icc["moonlab_qae_observation_zero_file"],
            "advantage/qae_moonlab_observation_zero.json")
        self.assertEqual(
            icc["moonlab_qae_observation_zero_circuit_file"],
            "advantage/qae_moonlab_observation_zero.moonlab")
        self.assertEqual(
            icc["moonlab_qae_observation_zero_markdown_file"],
            "advantage/qae_moonlab_observation_zero.md")
        self.assertEqual(
            icc["moonlab_qae_observation_zero_icc_evidence_file"],
            "advantage/qae_moonlab_observation_zero_icc_evidence.json")
        self.assertEqual(
            icc["moonlab_qae_observation_zero_schema"],
            "qge.moonlab_qae_observation_circuit.v0")
        self.assertEqual(
            icc["moonlab_qae_observation_zero_status"],
            "qae_observation_zero_ready_grover_schedule_required")
        self.assertEqual(
            icc["moonlab_qae_observation_zero_semantic_scope"],
            "bernoulli_lift_qae_power_zero_observation")
        self.assertTrue(
            icc["moonlab_qae_observation_zero_control_plane_executable"])
        self.assertTrue(
            icc["moonlab_qae_candidate_state_preparation_transpiled"])
        self.assertTrue(
            icc["moonlab_qae_power_zero_observation_transpiled"])
        self.assertFalse(
            icc[
                "moonlab_qae_observation_zero_full_qae_oracle_transpiled"])
        self.assertEqual(
            icc["moonlab_qae_grover_schedule_plan_file"],
            "advantage/qae_moonlab_grover_schedule_plan.json")
        self.assertEqual(
            icc["moonlab_qae_grover_schedule_plan_markdown_file"],
            "advantage/qae_moonlab_grover_schedule_plan.md")
        self.assertEqual(
            icc["moonlab_qae_grover_schedule_plan_icc_evidence_file"],
            "advantage/qae_moonlab_grover_schedule_plan_icc_evidence.json")
        self.assertEqual(
            icc["moonlab_qae_grover_schedule_plan_schema"],
            "qge.moonlab_qae_grover_schedule_plan.v0")
        self.assertEqual(
            icc["moonlab_qae_grover_schedule_plan_status"],
            "qae_grover_schedule_blocked_control_plane_body_limit")
        self.assertEqual(
            icc["moonlab_qae_grover_schedule_plan_semantic_scope"],
            "bernoulli_lift_qae_grover_schedule_control_plane_plan")
        self.assertEqual(
            icc["moonlab_qae_grover_schedule_ready_observation_count"], 3)
        self.assertEqual(
            icc["moonlab_qae_grover_schedule_blocked_observation_count"], 1)
        self.assertEqual(
            icc["moonlab_qae_grover_schedule_first_blocked_power"], 4)
        self.assertFalse(
            icc["moonlab_qae_grover_schedule_transpiled"])
        self.assertFalse(
            icc[
                "moonlab_qae_grover_schedule_full_qae_oracle_transpiled"])
        self.assertEqual(
            icc["moonlab_job_specs_file"],
            "resource/qge_moonlab_job_specs.json")
        self.assertEqual(
            icc["moonlab_job_results_file"],
            "resource/qge_moonlab_job_results.json")
        self.assertEqual(
            icc["moonlab_replay_plan_file"],
            "resource/qge_moonlab_replay_plan.json")
        self.assertEqual(
            icc["moonlab_replay_plan_schema"],
            "qge.moonlab_replay_plan.v0")
        self.assertEqual(
            icc["moonlab_submission_packet_file"],
            "resource/qge_moonlab_submission_packet.json")
        self.assertEqual(
            icc["moonlab_submission_packet_schema"],
            "qge.moonlab_submission_packet.v0")
        self.assertEqual(
            icc["moonlab_submission_ready_candidate_count"], 1)
        self.assertEqual(
            icc["moonlab_submission_blocked_candidate_count"], 0)
        self.assertEqual(
            icc["moonlab_submission_submitted_candidate_count"], 0)
        self.assertEqual(
            icc["moonlab_submission_bundle_file"],
            "resource/qge_moonlab_submission_bundle.json")
        self.assertEqual(
            icc["moonlab_submission_bundle_markdown_file"],
            "resource/qge_moonlab_submission_bundle.md")
        self.assertEqual(
            icc["moonlab_submission_bundle_icc_evidence_file"],
            "resource/qge_moonlab_submission_bundle_icc_evidence.json")
        self.assertEqual(
            icc["moonlab_submission_bundle_schema"],
            "qge.moonlab_submission_bundle.v0")
        self.assertEqual(
            icc["moonlab_submission_bundle_status"],
            "qae_observation_zero_ready_grover_schedule_required")
        self.assertEqual(
            icc[
                "moonlab_submission_ready_for_control_plane_submission_count"],
            0)
        self.assertEqual(
            icc["moonlab_submission_calibration_payload_ready_count"], 1)
        self.assertEqual(
            icc["moonlab_submission_oracle_kernel_ready_count"], 1)
        self.assertEqual(
            icc["moonlab_submission_qae_observation_ready_count"], 1)
        self.assertEqual(
            icc["moonlab_submission_transpilation_required_count"], 1)
        self.assertEqual(
            icc["moonlab_submission_missing_artifact_candidate_count"], 0)
        self.assertFalse(
            icc["moonlab_hardware_submission_directly_executable"])
        self.assertTrue(
            icc["moonlab_control_plane_payload_directly_executable"])
        self.assertTrue(
            icc["moonlab_oracle_kernel_directly_executable"])
        self.assertTrue(
            icc["moonlab_qae_observation_directly_executable"])
        self.assertEqual(
            icc["moonlab_hardware_record_template_file"],
            "resource/qge_moonlab_hardware_record_template.json")
        self.assertEqual(
            icc["moonlab_hardware_record_template_schema"],
            "qge.moonlab_hardware_record_template.v0")
        self.assertEqual(
            icc["moonlab_hardware_record_schema"],
            "qge.moonlab_hardware_record.v0")
        self.assertEqual(
            icc["moonlab_hardware_record_template_job_id"],
            "qge.light_transport_qae_benchmark.mlae.v0")
        self.assertEqual(
            icc["moonlab_hardware_submission_scope_file"],
            "resource/qge_moonlab_hardware_submission_scope.json")
        self.assertEqual(
            icc["moonlab_hardware_submission_scope_icc_evidence_file"],
            "resource/qge_moonlab_hardware_submission_scope_icc_evidence.json")
        self.assertEqual(
            icc["moonlab_hardware_submission_scope_schema"],
            "qge.moonlab_hardware_submission_scope.v0")
        self.assertEqual(
            icc["moonlab_hardware_submission_scope_status"],
            "attention_required_for_control_plane_submission")
        self.assertFalse(icc["moonlab_hardware_submission_scope_ready"])
        self.assertEqual(
            icc["moonlab_hardware_submission_scope_passing_check_count"], 7)
        self.assertEqual(
            icc["moonlab_hardware_submission_scope_attention_check_count"], 2)
        self.assertEqual(
            icc["moonlab_full_game_plan_file"],
            "resource/qge_moonlab_full_game_plan.json")
        self.assertEqual(
            icc["moonlab_full_game_plan_markdown_file"],
            "resource/qge_moonlab_full_game_plan.md")
        self.assertEqual(
            icc["moonlab_full_game_plan_icc_evidence_file"],
            "resource/qge_moonlab_full_game_plan_icc_evidence.json")
        self.assertEqual(
            icc["moonlab_full_game_plan_schema"],
            "qge.moonlab_full_game_deployment_plan.v0")
        self.assertEqual(
            icc["moonlab_full_game_deployment_status"],
            "blocked_asset_unavailable")
        self.assertEqual(
            icc["moonlab_full_game_asset_unavailable_map_count"], 28)
        self.assertFalse(icc["whole_game_moonlab_deployment_claimed"])
        self.assertEqual(
            icc["moonlab_deployment_gate_file"],
            "resource/qge_moonlab_deployment_gate.json")
        self.assertEqual(
            icc["moonlab_deployment_gate_markdown_file"],
            "resource/qge_moonlab_deployment_gate.md")
        self.assertEqual(
            icc["moonlab_deployment_gate_icc_evidence_file"],
            "resource/qge_moonlab_deployment_gate_icc_evidence.json")
        self.assertEqual(
            icc["moonlab_deployment_gate_schema"],
            "qge.moonlab_deployment_gate.v0")
        self.assertEqual(icc["moonlab_deployment_gate_status"], "blocked")
        self.assertEqual(icc["moonlab_deployment_gate_blocker_count"], 4)
        self.assertFalse(
            icc["whole_game_moonlab_deployment_claim_allowed"])
        self.assertFalse(
            icc["whole_game_hardware_execution_claim_allowed"])
        self.assertFalse(icc["hardware_quantum_advantage_claim_allowed"])
        self.assertFalse(icc["dense_70000_qubit_state_claim_allowed"])
        self.assertEqual(icc["moonlab_selected_job_count"], 4)
        self.assertEqual(icc["moonlab_hardware_candidate_job_count"], 1)
        self.assertEqual(icc["moonlab_completed_simulator_job_count"], 4)
        self.assertEqual(icc["moonlab_completed_native_replay_job_count"], 2)
        self.assertEqual(icc["moonlab_hardware_submitted_job_count"], 0)
        self.assertEqual(
            icc["moonlab_job_results_status"],
            "simulator_complete_hardware_not_submitted")
        self.assertFalse(icc["whole_game_hardware_execution_claimed"])
        self.assertEqual(icc["breadth_map_count"], 4)
        self.assertEqual(
            icc["breadth_total_runtime_backend_probe_event_count"], 16)
        self.assertEqual(
            icc["breadth_runtime_backend_probe_resolved_run_count"], 4)
        self.assertEqual(icc["status"], "success")

    def test_runtime_icc_sidecar_audit_detects_stale_copies(self) -> None:
        probe_targets = [
            "qge_context_get_or_create_render_acceleration",
            "qge_dwt_render",
            "qge_metal_init_common",
        ]
        probe_proofs = {
            target: {
                "active_evidence": True,
                "native_bridge_evidence": True,
                "event_count": 1,
                "backends": ["Metal"],
                "paths": ["native_sparse_dwt_render_bridge"],
                "results": ["active"],
            }
            for target in probe_targets
        }
        vanilla_matrix = {
            "capture_dir": "diagnostics/quake_graphics/test",
            "metrics_file": "diagnostics/quake_graphics/test/metrics.json",
            "modes": [
                {
                    "mode": "classic",
                    "frame": {
                        "path": "diagnostics/quake_graphics/test/classic.png",
                    },
                },
                {
                    "mode": "quantum",
                    "frame": {
                        "path": "diagnostics/quake_graphics/test/quantum.png",
                    },
                },
            ],
            "conformance_summary": {
                "ready_for_complete_claim": True,
                "fallback_count": 0,
                "qge_surface_surrogates": 0,
                "qge_surface_culled": 0,
                "classic3d_count": 0,
                "classic2d_count": 1,
                "viewmodel_encoded": 1,
                "agent_stream_runs_success": True,
                "classic_agent_run_status": "ok",
                "qge_agent_run_status": "ok",
                "performance_sidecars_success": True,
                "qge_backend_gate_event_count": 3,
                "qge_runtime_backend_probe_event_count": 3,
                "qge_runtime_backend_probe_targets": probe_targets,
                "qge_runtime_backend_probe_proofs": probe_proofs,
                "qge_runtime_backend_probe_missing_targets": [],
                "qge_runtime_backend_probe_native_targets": probe_targets,
                "qge_runtime_backend_probe_resolved": True,
                "runtime_evidence_ready": True,
                "moonlab_authority_ready": True,
                "moonlab_authority_blockers": [],
                "qge_trace_summary_file": (
                    "diagnostics/quake_graphics/test/qge_trace_summary.json"),
            },
        }
        breadth_evidence = {
            "aggregate": {
                "breadth_ready_for_complete_claim": True,
                "matrix_run_count": 1,
                "publication_pack_count": 0,
                "ready_matrix_run_count": 1,
                "ready_publication_pack_count": 0,
                "map_count": 1,
                "maps": ["e1m1"],
                "full_game_map_set": "quake_registered_single_player",
                "full_game_map_coverage_status": "partial",
                "full_game_map_target_count": 32,
                "full_game_map_covered_count": 1,
                "full_game_map_missing_count": 31,
                "full_game_map_missing_maps": ["e1m2"],
                "full_game_map_extra_maps": [],
                "total_fallback_count": 0,
                "total_surrogate_count": 0,
                "total_cpu_idwt_count": 0,
                "total_native_bridge_count": 10,
                "total_backend_gate_event_count": 3,
                "backend_gate_backends": ["Metal"],
                "backend_gate_paths": ["native_sparse_dwt_render_bridge"],
                "backend_gate_render_bridge_paths": [
                    "native_sparse_dwt_render_bridge"],
                "backend_gate_render_bridge_run_count": 1,
                "total_runtime_backend_probe_event_count": 3,
                "route_contract_authority_ready_run_count": 1,
                "route_contract_authority_blocker_count": 0,
                "route_contract_authority_blockers": [],
                "runtime_backend_probe_targets": probe_targets,
                "runtime_backend_probe_backends": ["Metal"],
                "runtime_backend_probe_paths": [
                    "native_sparse_dwt_render_bridge"],
                "runtime_backend_probe_results": ["active"],
                "runtime_backend_probe_run_count": 1,
                "required_runtime_backend_probe_targets": probe_targets,
                "runtime_backend_probe_proofs": probe_proofs,
                "runtime_backend_probe_missing_targets": [],
                "runtime_backend_probe_native_targets": probe_targets,
                "runtime_backend_probe_resolved_run_count": 1,
                "issue_count": 0,
            },
        }
        runtime_boundary = {
            "schema": "qge.native_backend_boundary.v0",
            "status": "pass",
            "required_target_count": 3,
            "passed_target_count": 3,
            "blocked_target_count": 0,
            "targets": [
                {"target": target, "status": "pass"}
                for target in probe_targets
            ],
        }
        performance_summary = {
            "status": "pass",
            "aggregate": {
                "log_count": 1,
                "missing_logs": [],
                "engine_average_quantum_ms_max": None,
                "render_time_ms_max": 22.0,
                "native_idwt_sum": 10,
                "idwt_fallback_sum": 0,
                "cpu_idwt_sum": 0,
                "idwt_backend_values": ["native"],
                "backend_gate_event_count": 3,
                "backend_gate_paths": ["native_sparse_dwt_render_bridge"],
                "backend_gate_backends": ["Metal"],
                "backend_gate_render_bridge_paths": [
                    "native_sparse_dwt_render_bridge"],
                "backend_gate_render_bridge_active": True,
                "runtime_backend_probe_event_count": 3,
                "runtime_backend_probe_targets": probe_targets,
                "runtime_backend_probe_backends": ["Metal"],
                "runtime_backend_probe_paths": [
                    "native_sparse_dwt_render_bridge"],
                "runtime_backend_probe_results": ["active"],
                "required_runtime_backend_probe_targets": probe_targets,
                "runtime_backend_probe_proofs": probe_proofs,
                "runtime_backend_probe_missing_targets": [],
                "runtime_backend_probe_native_targets": probe_targets,
                "runtime_backend_probe_resolved": True,
                "runtime_backend_boundary": runtime_boundary,
                "max_average_ms": None,
                "max_render_ms": 22.0,
                "threshold_failures": [],
                "metric_evidence_present": True,
            },
        }
        source_artifacts = {
            "vanilla_matrix": vanilla_matrix,
            "breadth_evidence": breadth_evidence,
            "performance_summary": performance_summary,
        }
        artifact_paths = {
            "vanilla_matrix": "vanilla/vanilla_capture_matrix.json",
            "vanilla_icc_evidence": "vanilla/qge_vanilla_icc_evidence.json",
            "breadth_evidence": "breadth/breadth_evidence.json",
            "breadth_icc_evidence": "breadth/qge_breadth_icc_evidence.json",
            "performance_summary": "capture/qge_perf_summary.json",
            "performance_icc_evidence": (
                "capture/qge_perf_icc_evidence.json"),
        }
        sidecars = runtime_icc_audit.expected_runtime_icc_sidecars(
            source_artifacts,
            artifact_paths=artifact_paths,
        )
        clean_audit = runtime_icc_audit.runtime_icc_sidecar_audit(
            source_artifacts,
            sidecars,
            artifact_paths=artifact_paths,
            required=True,
        )
        self.assertTrue(clean_audit["passed"])
        self.assertEqual(clean_audit["recorded_sidecar_count"], 3)
        self.assertEqual(clean_audit["mismatch_count"], 0)

        stale_sidecars = json.loads(json.dumps(sidecars))
        stale_sidecars["performance_icc_evidence"]["native_idwt_sum"] = 0
        stale_sidecars[
            "vanilla_icc_evidence"
        ]["hardware_quantum_advantage_claimed"] = True
        stale_audit = runtime_icc_audit.runtime_icc_sidecar_audit(
            source_artifacts,
            stale_sidecars,
            artifact_paths=artifact_paths,
            required=True,
        )
        self.assertFalse(stale_audit["passed"])
        self.assertTrue(any(
            item.get("sidecar") == "performance_icc_evidence"
            and "native_idwt_sum" in item.get("fields", [])
            for item in stale_audit["sidecar_mismatches"]
        ))
        self.assertTrue(any(
            flag.get("flag") == "hardware_quantum_advantage_claimed"
            for flag in stale_audit["overclaim_flags"]
        ))

    def test_moonlab_submission_bundle_classifies_circuit_payloads(self) -> None:
        job_id = "qge.light_transport_qae_benchmark.mlae.v0"
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            abstract_circuit = tmpdir / "qae_circuit.abstract.txt"
            abstract_circuit.write_text(
                "QGE QAE abstract circuit v0\nlogical_qubits: 19\n",
                encoding="utf-8",
            )
            moonlab_circuit = tmpdir / "qae_circuit.moonlab.txt"
            moonlab_circuit.write_text(
                "# moonlab-circuit v1\nNUM_QUBITS 2\nH 0\n",
                encoding="utf-8",
            )

            def packet_for(path: Path, schedule_path: Path | None = None) -> dict:
                required_artifacts = {
                    "qae_circuit": str(path),
                }
                evidence = [
                    {
                        "name": "qae_circuit",
                        "exists": True,
                        "sha256": (
                            moonlab_submission_bundle.sha256_file(
                                path)),
                    },
                ]
                if schedule_path is not None:
                    required_artifacts["moonlab_qae_grover_schedule_plan"] = (
                        str(schedule_path))
                    evidence.append({
                        "name": "moonlab_qae_grover_schedule_plan",
                        "exists": True,
                        "sha256": moonlab_submission_bundle.sha256_file(
                            schedule_path),
                    })
                return {
                    "schema": "qge.moonlab_submission_packet.v0",
                    "candidate_jobs": [
                        {
                            "job_id": job_id,
                            "domain": "light_transport_qae_benchmark",
                            "kind": "moonlab_qae_kernel",
                            "submission_status": (
                                "ready_for_hardware_submission_metadata"),
                            "hardware_submission_status": "not_submitted",
                            "candidate_digest": "candidate-digest",
                            "resource": {"shots": 384},
                            "required_artifacts": required_artifacts,
                            "artifact_evidence": evidence,
                        },
                    ],
                }

            abstract_bundle = moonlab_submission_bundle.build_submission_bundle(
                packet_for(abstract_circuit))
            self.assertEqual(
                abstract_bundle["status"],
                "blocked_transpilation_required")
            self.assertEqual(
                abstract_bundle["transpilation_required_count"], 1)
            self.assertFalse(
                abstract_bundle["hardware_submission_directly_executable"])

            ready_bundle = moonlab_submission_bundle.build_submission_bundle(
                packet_for(moonlab_circuit))
            self.assertEqual(
                ready_bundle["status"],
                "ready_for_control_plane_submission")
            self.assertEqual(
                ready_bundle["ready_for_control_plane_submission_count"], 1)
            self.assertTrue(
                ready_bundle["hardware_submission_directly_executable"])
            self.assertEqual(
                ready_bundle["candidate_jobs"][0]
                ["qae_circuit_check"]["logical_qubits_declared"],
                2)

            grover_schedule = tmpdir / "qae_moonlab_grover_schedule_plan.json"
            publication_pack.write_json(grover_schedule, {
                "schema": "qge.moonlab_qae_grover_schedule_plan.v0",
                "status": (
                    "qae_grover_schedule_ready_for_control_plane_submission"),
                "semantic_scope": (
                    "bernoulli_lift_qae_grover_schedule_control_plane_plan"),
                "resource_estimate": {
                    "logical_qubits": 2,
                    "observation_count": 1,
                    "ready_observation_count": 1,
                    "blocked_observation_count": 0,
                    "max_body_bytes": moonlab_circuit.stat().st_size,
                    "max_gate_count": 1,
                },
                "claim_posture": {
                    "full_mlae_schedule_transpiled": True,
                    "full_qae_oracle_transpiled": True,
                },
                "observations": [
                    {
                        "observation_index": 0,
                        "grover_power": 0,
                        "status": "ready_for_control_plane_submission",
                        "body_bytes": moonlab_circuit.stat().st_size,
                        "gate_count": 1,
                        "control_plane_executable": True,
                        "moonlab_circuit_file": str(moonlab_circuit),
                        "moonlab_circuit_sha256": (
                            moonlab_submission_bundle.sha256_file(
                                moonlab_circuit)),
                    },
                ],
            })
            schedule_bundle = (
                moonlab_submission_bundle.build_submission_bundle(
                    packet_for(abstract_circuit, grover_schedule)))
            self.assertEqual(
                schedule_bundle["status"],
                "ready_for_control_plane_submission")
            self.assertEqual(
                schedule_bundle["grover_schedule_ready_count"], 1)
            self.assertEqual(
                schedule_bundle["transpilation_required_count"], 0)
            self.assertTrue(
                schedule_bundle["hardware_submission_directly_executable"])

            schedule_packet = packet_for(abstract_circuit, grover_schedule)
            hardware_template = (
                moonlab_hardware_ingest.build_hardware_record_template(
                    schedule_packet)
            )
            submission_scope = (
                moonlab_submission_bundle.build_hardware_submission_scope(
                    schedule_packet,
                    schedule_bundle,
                    hardware_template,
                )
            )
            self.assertEqual(
                submission_scope["schema"],
                "qge.moonlab_hardware_submission_scope.v0")
            self.assertEqual(
                submission_scope["status"],
                "ready_for_control_plane_submission")
            self.assertTrue(
                submission_scope["hardware_submission_scope_ready"])
            self.assertEqual(
                submission_scope["attention_check_count"], 0)
            self.assertIn(
                "full_game_moonlab_deployment_gate",
                submission_scope["out_of_scope"])
            scope_icc = moonlab_submission_bundle.build_scope_icc_evidence(
                submission_scope)
            self.assertEqual(
                scope_icc["runtime_backend"],
                "qge_moonlab_hardware_submission_scope")
            self.assertEqual(
                scope_icc["completion_reason"],
                "qge_moonlab_hardware_submission_scope_ready")

            packet_path = tmpdir / "qge_moonlab_submission_packet.json"
            out_path = tmpdir / "qge_moonlab_submission_bundle.json"
            markdown_path = tmpdir / "qge_moonlab_submission_bundle.md"
            icc_path = (
                tmpdir / "qge_moonlab_submission_bundle_icc_evidence.json")
            publication_pack.write_json(packet_path, packet_for(abstract_circuit))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    moonlab_submission_bundle.main([
                        str(packet_path),
                        "--out",
                        str(out_path),
                        "--markdown",
                        str(markdown_path),
                        "--icc-json",
                        str(icc_path),
                    ]),
                    0,
                )
            self.assertIn(
                "QGE_MOONLAB_SUBMISSION_BUNDLE",
                stdout.getvalue(),
            )
            cli_bundle = publication_pack.load_json(out_path)
            cli_icc = publication_pack.load_json(icc_path)
            self.assertEqual(
                cli_bundle["status"],
                "blocked_transpilation_required")
            self.assertIn(
                "blocked_transpilation_required",
                markdown_path.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                cli_icc["runtime_backend"],
                "qge_moonlab_submission_bundle")
            self.assertFalse(
                cli_icc["hardware_submission_directly_executable"])

            ready_packet_path = (
                tmpdir / "qge_moonlab_submission_packet.ready.json")
            ready_out_path = (
                tmpdir / "qge_moonlab_submission_bundle.ready.json")
            template_path = (
                tmpdir / "qge_moonlab_hardware_record_template.json")
            scope_path = (
                tmpdir / "qge_moonlab_hardware_submission_scope.json")
            scope_icc_path = (
                tmpdir /
                "qge_moonlab_hardware_submission_scope_icc_evidence.json")
            publication_pack.write_json(ready_packet_path, schedule_packet)
            publication_pack.write_json(template_path, hardware_template)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    moonlab_submission_bundle.main([
                        str(ready_packet_path),
                        "--out",
                        str(ready_out_path),
                        "--hardware-template",
                        str(template_path),
                        "--scope-out",
                        str(scope_path),
                        "--scope-icc-json",
                        str(scope_icc_path),
                    ]),
                    0,
                )
            self.assertIn(
                "QGE_MOONLAB_HARDWARE_SUBMISSION_SCOPE",
                stdout.getvalue(),
            )
            cli_scope = publication_pack.load_json(scope_path)
            self.assertTrue(cli_scope["hardware_submission_scope_ready"])
            cli_scope_icc = publication_pack.load_json(scope_icc_path)
            self.assertEqual(
                cli_scope_icc["runtime_backend"],
                "qge_moonlab_hardware_submission_scope")

    def test_moonlab_hardware_ingest_records_bounded_result(self) -> None:
        job_id = "qge.light_transport_qae_benchmark.mlae.v0"
        packet = {
            "schema": "qge.moonlab_submission_packet.v0",
            "candidate_jobs": [
                {
                    "job_id": job_id,
                    "domain": "light_transport_qae_benchmark",
                    "kind": "moonlab_qae_kernel",
                    "submission_status": (
                        "ready_for_hardware_submission_metadata"),
                    "candidate_digest": "candidate-digest",
                    "missing_required_artifacts": [],
                    "resource": {"shots": 384},
                    "required_artifacts": {
                        "qae_circuit": "advantage/qae_circuit.txt"
                    },
                    "artifact_evidence": [
                        {"name": "qae_circuit", "exists": True}
                    ],
                },
            ],
        }
        results = {
            "schema": "qge.moonlab_job_results.v0",
            "blocked_job_count": 0,
            "hardware_submitted_job_count": 0,
            "jobs": [
                {
                    "job_id": job_id,
                    "domain": "light_transport_qae_benchmark",
                    "kind": "moonlab_qae_kernel",
                    "result_status": (
                        "simulator_completed_hardware_not_submitted"),
                    "hardware_submission_status": "not_submitted",
                    "backend_results": [
                        {
                            "backend_id": (
                                "moonlab-simulator-local/qge-publication-pack"),
                            "backend_kind": "moonlab_simulator",
                            "status": "completed",
                        },
                        {
                            "backend_id": None,
                            "backend_kind": "moonlab_hardware_candidate",
                            "status": "not_submitted",
                        },
                    ],
                    "observations": {
                        "reference_value": 0.5,
                        "shots": 384,
                    },
                    "claim_posture": {
                        "hardware_result_claimed": False,
                        "hardware_quantum_advantage_claimed": False,
                        "whole_game_hardware_execution_claimed": False,
                    },
                },
            ],
        }
        record = {
            "schema": "qge.moonlab_hardware_record.v0",
            "job_id": job_id,
            "candidate_digest": "candidate-digest",
            "backend_id": "moonlab-hardware/mock-qpu",
            "backend_kind": "moonlab_hardware",
            "status": "completed",
            "run_id": "moonlab-hw-run-001",
            "submitted_utc": "2026-05-23T20:30:00Z",
            "completed_utc": "2026-05-23T20:31:00Z",
            "shot_schedule": {
                "shots": 384,
                "batches": 3,
                "schedule_id": "qge-mlae-384-v1",
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

        updated, comparison = (
            moonlab_hardware_ingest.ingest_hardware_record(
                packet, results, record)
        )
        self.assertEqual(updated["hardware_submitted_job_count"], 1)
        self.assertEqual(updated["completed_hardware_job_count"], 1)
        self.assertEqual(
            updated["overall_status"],
            "simulator_complete_hardware_recorded")
        self.assertEqual(
            updated["jobs"][0]["result_status"],
            "hardware_completed_simulator_retained")
        self.assertEqual(
            updated["jobs"][0]["backend_results"][-1]["backend_kind"],
            "moonlab_hardware")
        self.assertEqual(
            comparison["schema"], "qge.moonlab_hardware_comparison.v0")
        self.assertAlmostEqual(comparison["value_delta"], 0.003)
        self.assertFalse(
            comparison["claim_posture"]
            ["hardware_quantum_advantage_claimed"])
        result_audit = (
            moonlab_hardware_result_audit.hardware_result_ledger_audit(
                packet,
                updated,
                {
                    "schema": "qge.moonlab_hardware_submission_scope.v0",
                    "candidate_digests": {job_id: "candidate-digest"},
                },
            )
        )
        self.assertTrue(result_audit["passed"], result_audit)
        self.assertEqual(result_audit["hardware_result_row_count"], 1)
        self.assertEqual(result_audit["mismatch_count"], 0)
        template = moonlab_hardware_ingest.build_hardware_record_template(
            packet)
        self.assertEqual(
            template["schema"], "qge.moonlab_hardware_record_template.v0")
        self.assertEqual(
            template["record_schema"], "qge.moonlab_hardware_record.v0")
        self.assertEqual(template["job_id"], job_id)
        self.assertEqual(template["candidate_digest"], "candidate-digest")
        self.assertEqual(template["backend_kind"], "moonlab_hardware")
        self.assertEqual(template["record"]["schema"],
                         "qge.moonlab_hardware_record.v0")
        self.assertEqual(template["record"]["shot_schedule"]["shots"], 384)
        self.assertEqual(
            template["validation_contract"]["shot_schedule"]["schedule_id"],
            "non-empty schedule identifier")
        self.assertFalse(
            template["record"]["whole_game_hardware_execution_claimed"])

        bad_record = dict(record)
        bad_record["hardware_quantum_advantage_claimed"] = True
        with self.assertRaises(ValueError):
            moonlab_hardware_ingest.ingest_hardware_record(
                packet, results, bad_record)

        bad_record = json.loads(json.dumps(record))
        bad_record["readout_metadata"]["shots_completed"] = 383
        with self.assertRaisesRegex(ValueError, "shots_completed"):
            moonlab_hardware_ingest.ingest_hardware_record(
                packet, results, bad_record)

        bad_record = json.loads(json.dumps(record))
        bad_record["observations"]["mean_value"] = float("nan")
        with self.assertRaisesRegex(ValueError, "mean_value"):
            moonlab_hardware_ingest.ingest_hardware_record(
                packet, results, bad_record)

        bad_record = json.loads(json.dumps(record))
        bad_record["shot_schedule"]["schedule_id"] = ""
        with self.assertRaisesRegex(ValueError, "schedule_id"):
            moonlab_hardware_ingest.ingest_hardware_record(
                packet, results, bad_record)

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            packet_path = tmpdir / "qge_moonlab_submission_packet.json"
            results_path = tmpdir / "qge_moonlab_job_results.json"
            record_path = tmpdir / "qge_moonlab_hardware_record.json"
            out_path = tmpdir / "qge_moonlab_job_results.hardware.json"
            comparison_path = tmpdir / "qge_moonlab_hardware_comparison.json"
            icc_path = tmpdir / "qge_moonlab_hardware_icc_evidence.json"
            template_path = (
                tmpdir / "qge_moonlab_hardware_record.template.json")
            publication_pack.write_json(packet_path, packet)
            publication_pack.write_json(results_path, results)
            publication_pack.write_json(record_path, record)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    moonlab_hardware_ingest.main([
                        str(packet_path),
                        "--template-out",
                        str(template_path),
                    ]),
                    0,
                )
            self.assertIn(
                "QGE_MOONLAB_HARDWARE_RECORD_TEMPLATE", stdout.getvalue())
            cli_template = publication_pack.load_json(template_path)
            self.assertEqual(
                cli_template["record_schema"],
                "qge.moonlab_hardware_record.v0")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    moonlab_hardware_ingest.main([
                        str(packet_path),
                        "--job-results",
                        str(results_path),
                        "--hardware-record",
                        str(record_path),
                        "--out",
                        str(out_path),
                        "--comparison-out",
                        str(comparison_path),
                        "--icc-out",
                        str(icc_path),
                    ]),
                    0,
                )
            self.assertIn(
                "QGE_MOONLAB_HARDWARE_RESULTS", stdout.getvalue())
            self.assertIn(
                "QGE_MOONLAB_HARDWARE_COMPARISON", stdout.getvalue())
            self.assertIn(
                "QGE_MOONLAB_HARDWARE_ICC_EVIDENCE", stdout.getvalue())
            cli_icc = publication_pack.load_json(icc_path)
            self.assertEqual(
                cli_icc["completion_reason"],
                "qge_moonlab_hardware_result_recorded")
            self.assertEqual(cli_icc["completed_hardware_job_count"], 1)
            self.assertFalse(
                cli_icc["whole_game_hardware_execution_claimed"])

    def test_moonlab_full_game_plan_tracks_asset_blockers(self) -> None:
        coverage = breadth_evidence.build_full_game_map_coverage(
            ["start", "e1m1"])
        inventory = {
            "schema": "qge.asset_inventory.v0",
            "map_set": "quake_registered_single_player",
            "status": "partial",
            "target_map_count": 32,
            "available_map_count": 3,
            "missing_map_count": 29,
            "available_maps": ["start", "e1m1", "e1m2"],
            "missing_maps": [
                name for name in
                breadth_evidence.QUAKE_REGISTERED_SINGLE_PLAYER_MAPS
                if name not in {"start", "e1m1", "e1m2"}
            ],
            "full_game_asset_ready": False,
        }
        breadth = {
            "schema": "qge.breadth_evidence.v0",
            "matrix_runs": [
                {
                    "map": "start",
                    "matrix_file": "start/vanilla_capture_matrix.json",
                    "ready": True,
                    "ready_for_complete_claim": True,
                    "moonlab_authority_ready": True,
                    "fallback_count": 0,
                    "surrogate_count": 0,
                    "cpu_idwt_count": 0,
                    "native_bridge_count": 105,
                    "runtime_backend_probe_resolved": True,
                    "route_contract_authority_ready": True,
                    "route_contract_authority_blockers": [],
                },
                {
                    "map": "e1m1",
                    "matrix_file": "e1m1/vanilla_capture_matrix.json",
                    "ready": True,
                    "ready_for_complete_claim": True,
                    "moonlab_authority_ready": True,
                    "fallback_count": 0,
                    "surrogate_count": 0,
                    "cpu_idwt_count": 0,
                    "native_bridge_count": 105,
                    "runtime_backend_probe_resolved": True,
                    "route_contract_authority_ready": True,
                    "route_contract_authority_blockers": [],
                }
            ],
        }
        job_results = {
            "schema": "qge.moonlab_job_results.v0",
            "overall_status": "simulator_complete_hardware_not_submitted",
            "completed_simulator_job_count": 4,
            "completed_native_replay_job_count": 2,
            "hardware_submitted_job_count": 0,
        }
        packet = {
            "schema": "qge.moonlab_submission_packet.v0",
            "hardware_candidate_job_count": 1,
            "ready_candidate_count": 1,
            "submitted_candidate_count": 0,
        }
        template = {
            "schema": "qge.moonlab_hardware_record_template.v0",
            "record_schema": "qge.moonlab_hardware_record.v0",
        }
        missing_after_plan = [
            name for name in inventory["missing_maps"]
            if name != "e2m1"
        ]
        registered_asset_intake = {
            "schema": "qge.registered_asset_intake.v0",
            "status": "blocked_candidate_copy_plan",
            "manual_registered_asset_required": True,
            "registered_asset_blocker_reason": (
                "candidate_copy_plan_blocked"),
            "copy_script_mode": "blocked_copy_plan",
            "no_candidate_asset_copy_plan": False,
            "missing_map_count_after_plan": len(missing_after_plan),
            "missing_maps_after_plan": missing_after_plan,
            "actionable_copy_plan_count": 1,
            "copy_plan_unblocked_map_count": 1,
            "copy_plan_unblocked_maps": ["e2m1"],
            "copy_plan_blocked_map_count": 1,
            "copy_plan_blocked_maps": ["e2m2"],
            "candidate_discovery_command": (
                "python3 tools/qge_registered_asset_intake.py "
                "--discover-common"),
            "post_install_verification": {
                "commands": [
                    {
                        "kind": "asset_inventory",
                        "shell_command": (
                            "python3 tools/qge_asset_inventory.py "
                            "--asset-root assets/id1"),
                    },
                    {
                        "kind": "capture_queue",
                        "shell_command": (
                            "python3 tools/qge_full_game_capture_queue.py "
                            "pack --asset-root assets/id1"),
                    },
                ],
            },
        }
        plan = moonlab_full_game_plan.build_plan(
            coverage,
            inventory,
            source_path=Path("publication_pack"),
            breadth_evidence=breadth,
            moonlab_job_results=job_results,
            submission_packet=packet,
            hardware_record_template=template,
            registered_asset_intake=registered_asset_intake,
        )
        self.assertEqual(
            plan["schema"], "qge.moonlab_full_game_deployment_plan.v0")
        self.assertEqual(plan["status"], "blocked_asset_unavailable")
        self.assertEqual(plan["covered_map_count"], 2)
        self.assertEqual(plan["capture_required_maps"], ["e1m2"])
        self.assertIn("e2m1", plan["asset_unavailable_maps"])
        self.assertEqual(
            plan["route_contract_schema"],
            full_game_capture_queue.ROUTE_CONTRACT_SCHEMA,
        )
        self.assertEqual(plan["route_contract_map_count"], 32)
        self.assertTrue(plan["route_contracts_complete"])
        self.assertEqual(plan["missing_route_contract_maps"], [])
        self.assertTrue(plan["covered_route_contract_authority_complete"])
        self.assertEqual(
            plan["covered_route_contract_authority_ready_count"], 2)
        self.assertTrue(plan["registered_asset_handoff"]["present"])
        self.assertEqual(
            plan["registered_asset_handoff"][
                "registered_asset_intake_status"],
            "blocked_candidate_copy_plan",
        )
        self.assertEqual(
            plan["registered_asset_handoff"][
                "copy_plan_unblocked_maps"],
            ["e2m1"],
        )
        self.assertEqual(
            plan["registered_asset_handoff"][
                "copy_plan_blocked_maps"],
            ["e2m2"],
        )
        self.assertFalse(
            plan["claim_posture"]["whole_game_moonlab_deployment_claimed"])
        self.assertNotIn("map_status", plan)
        start = next(
            row for row in plan["map_deployment_rows"]
            if row["map"] == "start")
        self.assertEqual(
            start["deployment_status"],
            "simulator_native_evidence_present")
        self.assertEqual(start["evidence"][0]["fallback_count"], 0)
        e1m2 = next(
            row for row in plan["map_deployment_rows"]
            if row["map"] == "e1m2")
        self.assertEqual(e1m2["deployment_status"], "capture_required")
        self.assertEqual(e1m2["asset_handoff_status"], "asset_present")
        self.assertEqual(
            e1m2["route_contract"]["map_class"], "registered_combat")
        self.assertIn(
            "ai_authority", e1m2["route_contract"]["authority_domains"])
        e2m1 = next(
            row for row in plan["map_deployment_rows"]
            if row["map"] == "e2m1")
        self.assertEqual(
            e2m1["deployment_status"], "blocked_asset_unavailable")
        self.assertEqual(
            e2m1["asset_handoff_status"], "copy_plan_unblocked")
        self.assertEqual(
            e2m1["next_action"], "run_registered_asset_copy_plan")
        e2m2 = next(
            row for row in plan["map_deployment_rows"]
            if row["map"] == "e2m2")
        self.assertEqual(
            e2m2["asset_handoff_status"], "copy_plan_blocked")
        self.assertEqual(
            e2m2["next_action"],
            "resolve_blocked_registered_asset_copy_plan",
        )
        e2m3 = next(
            row for row in plan["map_deployment_rows"]
            if row["map"] == "e2m3")
        self.assertEqual(
            e2m3["asset_handoff_status"], "missing_after_copy_plan")
        icc = moonlab_full_game_plan.build_icc_evidence(
            plan, out_path=Path("qge_moonlab_full_game_plan.json"))
        self.assertEqual(
            icc["runtime_backend"], "qge_moonlab_full_game_plan")
        self.assertEqual(icc["capture_required_map_count"], 1)
        self.assertTrue(icc["registered_asset_handoff_present"])
        self.assertEqual(
            icc["registered_asset_handoff_status"],
            "blocked_candidate_copy_plan",
        )
        self.assertEqual(
            icc["registered_asset_handoff_copy_plan_unblocked_map_count"],
            1,
        )
        self.assertEqual(
            icc["registered_asset_handoff_copy_plan_blocked_map_count"],
            1,
        )
        self.assertTrue(icc["route_contracts_complete"])
        self.assertFalse(icc["whole_game_hardware_execution_claimed"])
        markdown = moonlab_full_game_plan.markdown_report(plan)
        self.assertIn("blocked_asset_unavailable", markdown)
        self.assertIn("Route contracts: 32 (complete=True)", markdown)
        self.assertIn("Registered Asset Handoff", markdown)
        self.assertIn("copy_plan_unblocked", markdown)
        self.assertIn("copy_plan_blocked", markdown)
        self.assertIn("registered_combat", markdown)

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            resource = tmpdir / "resource"
            resource.mkdir()
            publication_pack.write_json(
                resource / "qge_full_game_map_coverage.json", coverage)
            publication_pack.write_json(
                resource / "qge_asset_inventory.json", inventory)
            publication_pack.write_json(
                resource / "qge_moonlab_job_results.json", job_results)
            publication_pack.write_json(
                resource / "qge_moonlab_submission_packet.json", packet)
            publication_pack.write_json(
                resource / "qge_moonlab_hardware_record_template.json",
                template,
            )
            publication_pack.write_json(
                resource / "qge_registered_asset_intake.json",
                registered_asset_intake,
            )
            publication_pack.write_json(
                tmpdir / "breadth_evidence.json", breadth)
            manifest = {
                "schema": "qge.publication_pack.v0",
                "source_inputs": {
                    "breadth_evidence": str(tmpdir / "breadth_evidence.json")
                },
                "artifacts": {
                    "resource": {
                        "full_game_map_coverage": {
                            "path": str(
                                resource / "qge_full_game_map_coverage.json")
                        },
                        "asset_inventory": {
                            "path": str(resource / "qge_asset_inventory.json")
                        },
                        "moonlab_job_results": {
                            "path": str(
                                resource / "qge_moonlab_job_results.json")
                        },
                        "moonlab_submission_packet": {
                            "path": str(
                                resource /
                                "qge_moonlab_submission_packet.json")
                        },
                        "moonlab_hardware_record_template": {
                            "path": str(
                                resource /
                                "qge_moonlab_hardware_record_template.json")
                        },
                        "registered_asset_intake": {
                            "path": str(
                                resource /
                                "qge_registered_asset_intake.json")
                        },
                    }
                },
            }
            manifest_path = tmpdir / "publication_manifest.json"
            publication_pack.write_json(manifest_path, manifest)
            out_path = tmpdir / "qge_moonlab_full_game_plan.json"
            markdown_path = tmpdir / "qge_moonlab_full_game_plan.md"
            icc_path = tmpdir / "qge_moonlab_full_game_plan_icc.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    moonlab_full_game_plan.main([
                        str(tmpdir),
                        "--out",
                        str(out_path),
                        "--markdown",
                        str(markdown_path),
                        "--icc-json",
                        str(icc_path),
                    ]),
                    0,
                )
            self.assertIn(
                "QGE_MOONLAB_FULL_GAME_PLAN", stdout.getvalue())
            cli_plan = publication_pack.load_json(out_path)
            self.assertEqual(
                cli_plan["schema"],
                "qge.moonlab_full_game_deployment_plan.v0")
            self.assertTrue(cli_plan["route_contracts_complete"])
            self.assertTrue(
                cli_plan["registered_asset_handoff"]["present"])
            self.assertEqual(
                cli_plan["registered_asset_handoff"][
                    "copy_script_mode"],
                "blocked_copy_plan",
            )
            cli_icc = publication_pack.load_json(icc_path)
            self.assertEqual(
                cli_icc["deployment_status"], "blocked_asset_unavailable")
            self.assertEqual(
                cli_icc["registered_asset_handoff_copy_script_mode"],
                "blocked_copy_plan",
            )


    def test_moonlab_deployment_gate_blocks_until_full_game_ready(self) -> None:
        partial_coverage = breadth_evidence.build_full_game_map_coverage(
            ["start", "e1m1"])
        partial_inventory = {
            "schema": "qge.asset_inventory.v0",
            "map_set": "quake_registered_single_player",
            "status": "partial",
            "target_map_count": 32,
            "available_map_count": 2,
            "missing_map_count": 30,
            "invalid_pak_count": 0,
            "invalid_bsp_count": 0,
            "available_maps": ["start", "e1m1"],
            "missing_maps": [
                name for name in
                breadth_evidence.QUAKE_REGISTERED_SINGLE_PLAYER_MAPS
                if name not in {"start", "e1m1"}
            ],
            "full_game_asset_ready": False,
        }
        partial_requirements = {
            "schema": "qge.asset_requirements.v0",
            "status": "blocked_missing_registered_assets",
            "target_map_count": 32,
            "present_map_count": 2,
            "missing_map_count": 30,
            "missing_maps": partial_inventory["missing_maps"],
            "claim_posture": {
                "asset_requirements_satisfied": False,
                "whole_game_hardware_execution_claimed": False,
                "hardware_quantum_advantage_claimed": False,
                "dense_70000_qubit_state_claimed": False,
            },
        }
        job_specs = {
            "schema": "qge.moonlab_job_specs.v0",
            "selected_job_count": 4,
            "hardware_candidate_job_count": 1,
            "jobs": moonlab_selected_job_spec_jobs(),
        }
        job_results = {
            "schema": "qge.moonlab_job_results.v0",
            "overall_status": "simulator_complete_hardware_not_submitted",
            "selected_job_count": 4,
            "completed_simulator_job_count": 4,
            "completed_native_replay_job_count": 2,
            "blocked_job_count": 0,
            "hardware_candidate_job_count": 1,
            "hardware_submitted_job_count": 0,
            "jobs": moonlab_selected_job_result_jobs(
                partial_coverage,
                partial_inventory,
                partial_requirements,
            ),
        }
        submission_packet = moonlab_job_runner.build_moonlab_submission_packet(
            job_specs,
            job_results,
        )
        hardware_template = (
            moonlab_hardware_ingest.build_hardware_record_template(
                submission_packet)
        )
        submission_bundle = moonlab_submission_bundle.build_submission_bundle(
            submission_packet)
        hardware_submission_scope = (
            moonlab_submission_bundle.build_hardware_submission_scope(
                submission_packet,
                submission_bundle,
                hardware_template,
            )
        )

        def source_icc_for(plan: dict[str, object]) -> dict[str, object]:
            return {
                "moonlab_submission_bundle_icc_evidence": (
                    moonlab_submission_bundle.build_icc_evidence(
                        submission_bundle)),
                "moonlab_hardware_submission_scope_icc_evidence": (
                    moonlab_submission_bundle.build_scope_icc_evidence(
                        hardware_submission_scope)),
                "moonlab_full_game_plan_icc_evidence": (
                    moonlab_full_game_plan.build_icc_evidence(plan)),
            }

        def resource_icc_for(
            inventory: dict[str, object],
            requirements: dict[str, object],
            intake: dict[str, object],
        ) -> dict[str, object]:
            return {
                "asset_inventory_icc_evidence": (
                    asset_inventory.build_icc_evidence(inventory)),
                "asset_requirements_icc_evidence": (
                    asset_requirements.build_icc_evidence(requirements)),
                "registered_asset_intake_icc_evidence": (
                    registered_asset_intake.build_icc_evidence(intake)),
            }

        advantage_artifact_paths = {
            "advantage_metrics": "advantage/advantage_metrics.json",
            "qae_curve": "advantage/qae_curve.csv",
            "qae_circuit": "advantage/qae_circuit.txt",
            "scaling_summary": "advantage/scaling_summary.json",
            "qae_moonlab_payload": "advantage/qae_moonlab_payload.json",
            "qae_moonlab_oracle_kernel": (
                "advantage/qae_moonlab_oracle_kernel.json"),
            "qae_moonlab_observation_zero": (
                "advantage/qae_moonlab_observation_zero.json"),
            "qae_moonlab_grover_schedule_plan": (
                "advantage/qae_moonlab_grover_schedule_plan.json"),
        }
        advantage_artifacts = {
            "advantage_metrics": {
                "advantage_problem_id": "advantage.test",
                "comparison": {
                    "best_qae": {
                        "oracle_eval_count": 1728,
                        "shots": 384,
                        "mean_reference_value": 0.5,
                        "rmse": 0.01,
                        "ci95_absolute_delta": 0.02,
                    },
                    "best_classical": {
                        "oracle_eval_count": 128,
                    },
                },
                "oracle": {
                    "state_prep_cost": 234,
                    "readout_model": "finite_shot_mlae",
                },
                "scaling_summary": {
                    "trial_count": 3,
                    "confidence_level": 0.95,
                },
                "resource_estimate": {
                    "logical_qubits": 19,
                    "candidate_index_bits": 8,
                    "contribution_threshold_bits": 8,
                    "controlled_oracle_calls": 1728,
                    "one_qubit_gates": 34560,
                    "two_qubit_gates": 27648,
                    "circuit_depth": 1350,
                },
            },
            "qae_moonlab_payload": {
                "schema": "qge.moonlab_qae_payload.v0",
                "status": (
                    "calibration_payload_ready_oracle_transpilation_required"),
                "semantic_scope": "mlae_observation_distribution_payload",
                "payload_resource_estimate": {
                    "circuit_count": 4,
                    "total_shots": 384,
                    "logical_qubits": 1,
                },
            },
            "qae_moonlab_oracle_kernel": {
                "schema": "qge.moonlab_qae_oracle_kernel.v0",
                "status": "qf_oracle_kernel_ready_qae_transpilation_required",
                "semantic_scope": "bernoulli_lift_qf_oracle_kernel",
                "moonlab_circuit_file": (
                    "advantage/qae_moonlab_oracle_kernel.moonlab"),
                "moonlab_control_plane": {
                    "control_plane_executable": True,
                    "body_bytes": 64172,
                    "body_limit_bytes": 4194304,
                },
                "resource_estimate": {
                    "logical_qubits": 32,
                    "gate_count": 7415,
                },
                "claim_posture": {
                    "qf_oracle_kernel_transpiled": True,
                    "candidate_state_preparation_transpiled": False,
                    "grover_operator_transpiled": False,
                    "full_qae_oracle_transpiled": False,
                },
            },
            "qae_moonlab_observation_zero": {
                "schema": "qge.moonlab_qae_observation_circuit.v0",
                "status": (
                    "qae_observation_zero_ready_grover_schedule_required"),
                "semantic_scope": (
                    "bernoulli_lift_qae_power_zero_observation"),
                "moonlab_circuit_file": (
                    "advantage/qae_moonlab_observation_zero.moonlab"),
                "moonlab_control_plane": {
                    "control_plane_executable": True,
                    "body_bytes": 67643,
                    "body_limit_bytes": 4194304,
                },
                "resource_estimate": {
                    "logical_qubits": 32,
                    "gate_count": 7740,
                },
                "state_preparation": {
                    "candidate_count": 234,
                    "invalid_candidate_probability": 0.0,
                },
                "claim_posture": {
                    "candidate_state_preparation_transpiled": True,
                    "qf_oracle_kernel_transpiled": True,
                    "power_zero_observation_transpiled": True,
                    "grover_operator_transpiled": False,
                    "full_mlae_schedule_transpiled": False,
                    "full_qae_oracle_transpiled": False,
                },
            },
            "qae_moonlab_grover_schedule_plan": {
                "schema": "qge.moonlab_qae_grover_schedule_plan.v0",
                "status": (
                    "qae_grover_schedule_ready_for_control_plane_submission"),
                "semantic_scope": (
                    "bernoulli_lift_qae_grover_schedule_control_plane_plan"),
                "moonlab_control_plane": {
                    "ready_observation_count": 4,
                    "blocked_observation_count": 0,
                    "first_blocked_power": None,
                    "body_limit_bytes": 4194304,
                },
                "resource_estimate": {
                    "observation_count": 4,
                    "power_zero_body_bytes": 67643,
                    "logical_qubits": 32,
                    "max_gate_count": 69924,
                    "max_body_bytes": 610599,
                },
                "claim_posture": {
                    "candidate_state_preparation_transpiled": True,
                    "qf_oracle_kernel_transpiled": True,
                    "power_zero_observation_transpiled": True,
                    "nonzero_grover_powers_transpiled": True,
                    "grover_operator_transpiled": True,
                    "full_mlae_schedule_transpiled": True,
                    "full_qae_oracle_transpiled": True,
                },
            },
        }
        advantage_icc_evidence = (
            moonlab_advantage_icc_audit.expected_advantage_icc_sidecars(
                advantage_artifacts,
                artifact_paths=advantage_artifact_paths,
            )
        )
        native_probe_proofs = {
            "qge_context_get_or_create_render_acceleration": {
                "event_count": 2,
                "backends": ["Metal"],
                "paths": ["native_sparse_dwt_render_bridge"],
                "results": ["created", "cached"],
                "phases": ["create", "cache_hit"],
                "native_bridge_evidence": True,
                "active_evidence": True,
                "latest_event": {
                    "target": "qge_context_get_or_create_render_acceleration",
                    "phase": "cache_hit",
                    "backend": "Metal",
                    "path": "native_sparse_dwt_render_bridge",
                    "result": "cached",
                },
            },
            "qge_dwt_render": {
                "event_count": 1,
                "backends": ["Metal"],
                "paths": ["native_sparse_dwt_render_bridge"],
                "results": ["native"],
                "phases": ["idwt"],
                "native_bridge_evidence": True,
                "active_evidence": True,
                "latest_event": {
                    "target": "qge_dwt_render",
                    "phase": "idwt",
                    "backend": "Metal",
                    "path": "native_sparse_dwt_render_bridge",
                    "result": "native",
                },
            },
            "qge_metal_init_common": {
                "event_count": 1,
                "backends": ["Metal"],
                "paths": ["native_sparse_dwt_render_bridge"],
                "results": ["active"],
                "phases": ["create"],
                "native_bridge_evidence": True,
                "active_evidence": True,
                "latest_event": {
                    "target": "qge_metal_init_common",
                    "phase": "create",
                    "backend": "Metal",
                    "path": "native_sparse_dwt_render_bridge",
                    "result": "active",
                },
            },
        }

        def resource_boundary_sources_for(
            coverage: dict[str, object],
        ) -> dict[str, object]:
            maps = list(coverage.get("covered_maps", []))
            return {
                "oracle_scene": {
                    "cost_model": {"candidate_count": 234, "shots": 64},
                    "sample_space": {
                        "candidate_count": 234,
                        "register_bits": 8,
                    },
                    "snapshot": {
                        "render": {
                            "shots": 64,
                            "gates": 26,
                            "idwt_path": (
                                "native_sparse_dwt_render_bridge"),
                            "idwt_backend": "native",
                            "cpu_idwt": 0,
                        },
                    },
                },
                "advantage_metrics": advantage_artifacts[
                    "advantage_metrics"],
                "vanilla_matrix": {
                    "conformance_summary": {
                        "ready_for_complete_claim": True,
                        "fallback_count": 0,
                        "qge_surface_surrogates": 0,
                    },
                },
                "performance_summary": {
                    "status": "pass",
                    "aggregate": {
                        "required_runtime_backend_probe_targets": list(
                            native_probe_proofs),
                        "runtime_backend_probe_proofs": native_probe_proofs,
                        "runtime_backend_probe_missing_targets": [],
                        "runtime_backend_probe_native_targets": list(
                            native_probe_proofs),
                        "runtime_backend_probe_resolved": True,
                    },
                },
                "breadth_evidence": {
                    "status": "pass",
                    "aggregate": {
                        "breadth_ready_for_complete_claim": True,
                        "map_count": len(maps),
                        "maps": maps,
                        "full_game_coverage": coverage,
                        "total_fallback_count": 0,
                        "total_surrogate_count": 0,
                        "total_cpu_idwt_count": 0,
                        "total_native_bridge_count": len(maps) * 105,
                        "required_runtime_backend_probe_targets": list(
                            native_probe_proofs),
                        "runtime_backend_probe_missing_targets": [],
                        "runtime_backend_probe_native_targets": list(
                            native_probe_proofs),
                        "runtime_backend_probe_resolved_run_count": len(maps),
                    },
                },
            }

        partial_breadth = {
            "schema": "qge.breadth_evidence.v0",
            "matrix_runs": [
                {
                    "map": "start",
                    "route_contract_authority_ready": True,
                    "route_contract_authority_blockers": [],
                },
                {
                    "map": "e1m1",
                    "route_contract_authority_ready": True,
                    "route_contract_authority_blockers": [],
                },
            ],
        }
        partial_registered_asset_intake = {
            "schema": "qge.registered_asset_intake.v0",
            "status": "blocked_no_candidate_assets",
            "current_asset_root": "assets/id1",
            "candidate_new_map_count": 0,
            "missing_map_count_after_plan": 30,
            "missing_maps_after_plan": partial_inventory["missing_maps"],
            "manual_registered_asset_required": True,
            "registered_asset_blocker_reason": (
                "no_candidate_assets_found"),
            "copy_script_mode": "no_op_blocked",
            "no_candidate_asset_copy_plan": True,
            "copy_plan_count": 0,
            "actionable_copy_plan_count": 0,
            "copy_plan_unblocked_map_count": 0,
            "copy_plan_unblocked_maps": [],
            "copy_plan_blocked_map_count": 0,
            "copy_plan_blocked_maps": [],
            "discovered_candidate_count": 1,
            "discovery_metadata": {
                "roots_scanned_count": 4,
                "steam_library_root_count": 1,
                "steam_quake_path_count": 3,
            },
            "post_install_verification_command_count": 2,
            "post_install_verification": {
                "command_count": 2,
                "commands": [
                    {
                        "kind": "asset_inventory",
                        "shell_command": (
                            "python3 tools/qge_asset_inventory.py "
                            "--asset-root assets/id1"
                        ),
                    },
                    {
                        "kind": "capture_queue",
                        "shell_command": (
                            "python3 tools/"
                            "qge_full_game_capture_queue.py "
                            "partial-pack --asset-root assets/id1"
                        ),
                        "json": (
                            "/tmp/"
                            "qge_full_game_capture_queue.after.json"
                        ),
                        "script": "/tmp/run_missing_maps.after.sh",
                        "markdown": (
                            "/tmp/"
                            "qge_full_game_capture_queue.after.md"
                        ),
                    },
                ],
            },
            "claim_posture": {
                "asset_intake_copies_game_data": False,
            },
        }
        partial_plan = moonlab_full_game_plan.build_plan(
            partial_coverage,
            partial_inventory,
            breadth_evidence=partial_breadth,
            moonlab_job_results=job_results,
            submission_packet=submission_packet,
            hardware_record_template=hardware_template,
            registered_asset_intake=partial_registered_asset_intake,
        )
        partial_source_icc_evidence = source_icc_for(partial_plan)
        partial_resource_icc_evidence = resource_icc_for(
            partial_inventory,
            partial_requirements,
            partial_registered_asset_intake,
        )
        partial_resource_boundary_sources = resource_boundary_sources_for(
            partial_coverage)
        partial_resource_boundary_ledgers = (
            resource_boundary_audit.expected_resource_boundary_ledgers(
                partial_resource_boundary_sources)
        )
        partial_asset_remediation = (
            moonlab_deployment_gate.asset_remediation_from_intake(
                partial_registered_asset_intake,
                intake_path=Path("resource/qge_registered_asset_intake.json"),
                markdown_path=Path("resource/qge_registered_asset_intake.md"),
                script_path=Path("resource/install_registered_assets.sh"),
                icc_evidence_path=Path(
                    "resource/qge_registered_asset_intake_icc_evidence.json"),
            )
        )
        blocked_gate = moonlab_deployment_gate.build_gate(
            partial_coverage,
            partial_inventory,
            partial_requirements,
            partial_plan,
            job_specs,
            job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            registered_asset_intake=partial_registered_asset_intake,
            resource_icc_evidence=partial_resource_icc_evidence,
            resource_icc_evidence_required=True,
            source_icc_evidence=partial_source_icc_evidence,
            source_icc_evidence_required=True,
            advantage_artifacts=advantage_artifacts,
            advantage_icc_evidence=advantage_icc_evidence,
            advantage_icc_evidence_required=True,
            resource_envelope=partial_resource_boundary_ledgers[
                "resource_envelope"],
            native_backend_boundary=partial_resource_boundary_ledgers[
                "native_backend_boundary"],
            resource_boundary_sources=partial_resource_boundary_sources,
            resource_boundary_required=True,
            artifact_paths=advantage_artifact_paths,
            asset_remediation=partial_asset_remediation,
            source_path=Path("partial-pack"),
        )
        self.assertEqual(
            blocked_gate["schema"], "qge.moonlab_deployment_gate.v0")
        self.assertEqual(blocked_gate["status"], "blocked")
        self.assertFalse(
            blocked_gate["whole_game_moonlab_deployment_claim_allowed"])
        blocker_ids = {item["id"] for item in blocked_gate["blockers"]}
        self.assertIn("full_game_map_coverage_complete", blocker_ids)
        self.assertIn("registered_bsp_assets_ready", blocker_ids)
        self.assertIn("asset_requirements_satisfied", blocker_ids)
        self.assertIn("full_game_deployment_plan_complete", blocker_ids)
        self.assertNotIn("full_game_route_contracts_complete", blocker_ids)
        self.assertNotIn(
            "covered_route_contract_authority_complete", blocker_ids)
        self.assertNotIn(
            "registered_asset_handoff_consistent", blocker_ids)
        self.assertNotIn(
            "moonlab_full_game_plan_ledger_consistent", blocker_ids)
        self.assertNotIn(
            "moonlab_coverage_ledger_consistent", blocker_ids)
        self.assertNotIn(
            "moonlab_selected_job_result_ledger_consistent", blocker_ids)
        self.assertNotIn(
            "moonlab_hardware_result_ledger_consistent", blocker_ids)
        self.assertNotIn(
            "moonlab_advantage_icc_evidence_consistent", blocker_ids)
        self.assertNotIn(
            "resource_boundary_ledgers_consistent", blocker_ids)
        self.assertTrue(all(
            item["status"] == "blocked"
            for item in blocked_gate["blockers"]
        ))
        self.assertNotIn(
            "fail",
            {item["status"] for item in blocked_gate["criteria"]},
        )
        route_criterion = next(
            item for item in blocked_gate["criteria"]
            if item["id"] == "full_game_route_contracts_complete")
        self.assertEqual(route_criterion["status"], "pass")
        authority_criterion = next(
            item for item in blocked_gate["criteria"]
            if item["id"] == "covered_route_contract_authority_complete")
        self.assertEqual(authority_criterion["status"], "pass")
        handoff_criterion = next(
            item for item in blocked_gate["criteria"]
            if item["id"] == "registered_asset_handoff_consistent")
        self.assertEqual(handoff_criterion["status"], "pass")
        self.assertTrue(
            handoff_criterion["registered_asset_handoff_recorded"])
        self.assertEqual(
            handoff_criterion[
                "registered_asset_handoff_licensed_asset_required_count"],
            30,
        )
        plan_ledger_criterion = next(
            item for item in blocked_gate["criteria"]
            if item["id"] == "moonlab_full_game_plan_ledger_consistent")
        self.assertEqual(plan_ledger_criterion["status"], "pass")
        self.assertTrue(
            plan_ledger_criterion[
                "moonlab_full_game_plan_ledger_recorded"])
        self.assertEqual(
            plan_ledger_criterion[
                "moonlab_full_game_plan_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            plan_ledger_criterion[
                "moonlab_full_game_plan_ledger_row_count"],
            32,
        )
        coverage_ledger_criterion = next(
            item for item in blocked_gate["criteria"]
            if item["id"] == "moonlab_coverage_ledger_consistent")
        self.assertEqual(coverage_ledger_criterion["status"], "pass")
        self.assertTrue(
            coverage_ledger_criterion["moonlab_coverage_ledger_recorded"])
        self.assertEqual(
            coverage_ledger_criterion[
                "moonlab_coverage_ledger_mismatch_count"],
            0,
        )
        selected_job_ledger_criterion = next(
            item for item in blocked_gate["criteria"]
            if item["id"] ==
            "moonlab_selected_job_result_ledger_consistent")
        self.assertEqual(selected_job_ledger_criterion["status"], "pass")
        self.assertEqual(
            selected_job_ledger_criterion[
                "moonlab_selected_job_spec_job_count"],
            4,
        )
        self.assertEqual(
            selected_job_ledger_criterion[
                "moonlab_selected_job_result_job_count"],
            4,
        )
        self.assertEqual(
            selected_job_ledger_criterion[
                "moonlab_selected_job_result_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            selected_job_ledger_criterion[
                "moonlab_selected_job_required_artifact_count"],
            11,
        )
        self.assertEqual(
            selected_job_ledger_criterion[
                "moonlab_selected_job_artifact_evidence_count"],
            11,
        )
        self.assertEqual(
            selected_job_ledger_criterion[
                "moonlab_selected_job_artifact_evidence_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_gate["asset_remediation"][
                "registered_asset_install_script"],
            "resource/install_registered_assets.sh",
        )
        self.assertTrue(
            blocked_gate["summary"][
                "post_install_capture_queue_command_present"])
        self.assertIn(
            "qge_full_game_capture_queue.py",
            blocked_gate["summary"]["post_install_capture_queue_command"],
        )
        self.assertEqual(
            blocked_gate["summary"][
                "registered_asset_intake_discovery_roots_scanned_count"],
            4,
        )
        self.assertEqual(
            blocked_gate["summary"][
                "registered_asset_intake_steam_quake_path_count"],
            3,
        )
        self.assertTrue(
            blocked_gate["summary"][
                "registered_asset_intake_manual_asset_required"])
        self.assertEqual(
            blocked_gate["summary"][
                "registered_asset_intake_copy_script_mode"],
            "no_op_blocked",
        )
        self.assertTrue(
            blocked_gate["summary"][
                "registered_asset_intake_no_candidate_asset_copy_plan"])
        self.assertEqual(
            blocked_gate["summary"][
                "registered_asset_intake_actionable_copy_plan_count"],
            0,
        )
        self.assertTrue(
            blocked_gate["summary"]["registered_asset_handoff_present"])
        self.assertEqual(
            blocked_gate["summary"]["registered_asset_handoff_status"],
            "blocked_no_candidate_assets",
        )
        self.assertEqual(
            blocked_gate["summary"][
                "registered_asset_handoff_licensed_asset_required_count"],
            30,
        )
        self.assertEqual(
            blocked_gate["summary"][
                "registered_asset_handoff_not_recorded_count"],
            0,
        )
        self.assertTrue(
            blocked_gate["summary"][
                "moonlab_full_game_plan_ledger_recorded"])
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_full_game_plan_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_full_game_plan_ledger_row_count"],
            32,
        )
        self.assertTrue(blocked_gate["summary"]["route_contracts_complete"])
        self.assertEqual(
            blocked_gate["summary"]["route_contract_map_count"], 32)
        self.assertTrue(
            blocked_gate["summary"][
                "covered_route_contract_authority_complete"])
        self.assertTrue(
            blocked_gate["summary"][
                "registered_asset_discovery_command_present"])
        self.assertTrue(
            blocked_gate["summary"]["moonlab_coverage_ledger_recorded"])
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_coverage_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_coverage_ledger_observed_missing_map_count"],
            30,
        )
        self.assertTrue(
            blocked_gate["summary"][
                "moonlab_selected_job_result_ledger_recorded"])
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_selected_job_result_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_gate["summary"]["moonlab_selected_job_result_job_count"],
            4,
        )
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_selected_job_artifact_evidence_mismatch_count"],
            0,
        )
        self.assertTrue(
            blocked_gate["summary"][
                "moonlab_submission_packet_ledger_recorded"])
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_submission_packet_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_submission_packet_candidate_count"],
            1,
        )
        self.assertTrue(
            blocked_gate["summary"][
                "moonlab_hardware_record_template_ledger_recorded"])
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_hardware_record_template_ledger_mismatch_count"],
            0,
        )
        self.assertTrue(
            blocked_gate["summary"][
                "moonlab_hardware_record_template_candidate_found"])
        self.assertTrue(
            blocked_gate["summary"][
                "moonlab_hardware_submission_scope_ledger_recorded"])
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_hardware_submission_scope_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_hardware_submission_scope_recorded_ready"],
            blocked_gate["summary"][
                "moonlab_hardware_submission_scope_expected_ready"],
        )
        self.assertTrue(
            blocked_gate["summary"][
                "moonlab_hardware_result_ledger_recorded"])
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_hardware_result_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_gate["summary"]["moonlab_hardware_result_row_count"],
            0,
        )
        self.assertTrue(
            blocked_gate["summary"]["resource_icc_evidence_recorded"])
        self.assertEqual(
            blocked_gate["summary"]["resource_icc_evidence_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_gate["summary"]["resource_icc_evidence_recorded_count"],
            3,
        )
        self.assertTrue(
            blocked_gate["summary"][
                "moonlab_source_icc_evidence_recorded"])
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_source_icc_evidence_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_source_icc_evidence_recorded_count"],
            3,
        )
        self.assertTrue(
            blocked_gate["summary"][
                "moonlab_advantage_icc_evidence_recorded"])
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_advantage_icc_evidence_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_gate["summary"][
                "moonlab_advantage_icc_evidence_recorded_count"],
            5,
        )
        self.assertTrue(
            blocked_gate["summary"]["resource_boundary_recorded"])
        self.assertEqual(
            blocked_gate["summary"]["resource_boundary_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_gate["summary"]["resource_boundary_recorded_count"],
            2,
        )
        self.assertIn(
            "qge_registered_asset_intake.py",
            blocked_gate["summary"]["registered_asset_discovery_command"],
        )
        self.assertTrue(any(
            "install_registered_assets.sh" in action
            for action in blocked_gate["next_actions"]
        ))
        self.assertTrue(any(
            "qge_registered_asset_intake.py" in action
            for action in blocked_gate["next_actions"]
        ))
        self.assertTrue(any(
            "No registered asset copy plan exists yet" in action
            for action in blocked_gate["next_actions"]
        ))
        self.assertTrue(any(
            "qge_full_game_capture_queue.py" in action
            for action in blocked_gate["next_actions"]
        ))
        blocked_markdown = moonlab_deployment_gate.markdown_report(
            blocked_gate)
        self.assertIn("blocked", blocked_markdown)
        self.assertIn("## Asset Remediation", blocked_markdown)
        self.assertIn("install_registered_assets.sh", blocked_markdown)
        self.assertIn("copy script mode", blocked_markdown)
        self.assertIn("Route contracts: 32 (complete=True)", blocked_markdown)
        self.assertIn("Registered asset handoff", blocked_markdown)
        self.assertIn("Full-game plan ledger", blocked_markdown)
        self.assertIn("Moonlab coverage ledger", blocked_markdown)
        self.assertIn("Moonlab submission packet ledger", blocked_markdown)
        self.assertIn(
            "Moonlab hardware record template ledger", blocked_markdown)
        self.assertIn(
            "Moonlab hardware submission scope ledger", blocked_markdown)
        self.assertIn(
            "Moonlab hardware result ledger", blocked_markdown)
        self.assertIn("Resource ICC sidecars", blocked_markdown)
        self.assertIn("Moonlab source ICC sidecars", blocked_markdown)
        self.assertIn("Moonlab advantage ICC sidecars", blocked_markdown)
        self.assertIn("Resource boundary ledgers", blocked_markdown)
        self.assertIn(
            "Covered route authority: 2 / 2 (complete=True)",
            blocked_markdown,
        )
        self.assertIn("discovery refresh", blocked_markdown)
        blocked_icc = moonlab_deployment_gate.build_icc_evidence(
            blocked_gate,
            out_path=Path("qge_moonlab_deployment_gate.blocked.json"),
        )
        self.assertEqual(
            blocked_icc["completion_reason"],
            "qge_moonlab_deployment_gate_blocked")
        self.assertEqual(
            blocked_icc["registered_asset_install_script"],
            "resource/install_registered_assets.sh",
        )
        self.assertTrue(
            blocked_icc["post_install_capture_queue_command_present"])
        self.assertTrue(
            blocked_icc["registered_asset_discovery_command_present"])
        self.assertTrue(
            blocked_icc[
                "registered_asset_intake_manual_asset_required"])
        self.assertEqual(
            blocked_icc["registered_asset_intake_copy_script_mode"],
            "no_op_blocked",
        )
        self.assertTrue(
            blocked_icc[
                "registered_asset_intake_no_candidate_asset_copy_plan"])
        self.assertEqual(
            blocked_icc[
                "registered_asset_intake_actionable_copy_plan_count"],
            0,
        )
        self.assertTrue(
            blocked_icc["registered_asset_handoff_present"])
        self.assertEqual(
            blocked_icc[
                "registered_asset_handoff_licensed_asset_required_count"],
            30,
        )
        self.assertEqual(
            blocked_icc["registered_asset_handoff_not_recorded_count"],
            0,
        )
        self.assertTrue(
            blocked_icc["moonlab_full_game_plan_ledger_recorded"])
        self.assertEqual(
            blocked_icc["moonlab_full_game_plan_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_icc["moonlab_full_game_plan_ledger_row_count"],
            32,
        )
        self.assertTrue(
            blocked_icc["full_game_route_contracts_complete"])
        self.assertEqual(
            blocked_icc["full_game_route_contract_map_count"], 32)
        self.assertTrue(
            blocked_icc["covered_route_contract_authority_complete"])
        self.assertTrue(
            blocked_icc["moonlab_coverage_ledger_recorded"])
        self.assertEqual(
            blocked_icc["moonlab_coverage_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_icc[
                "moonlab_coverage_ledger_observed_missing_map_count"],
            30,
        )
        self.assertTrue(
            blocked_icc["moonlab_selected_job_result_ledger_recorded"])
        self.assertEqual(
            blocked_icc[
                "moonlab_selected_job_result_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_icc["moonlab_selected_job_result_job_count"],
            4,
        )
        self.assertEqual(
            blocked_icc[
                "moonlab_selected_job_artifact_evidence_mismatch_count"],
            0,
        )
        self.assertTrue(
            blocked_icc["moonlab_submission_packet_ledger_recorded"])
        self.assertEqual(
            blocked_icc["moonlab_submission_packet_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_icc["moonlab_submission_packet_candidate_count"],
            1,
        )
        self.assertTrue(
            blocked_icc[
                "moonlab_hardware_record_template_ledger_recorded"])
        self.assertEqual(
            blocked_icc[
                "moonlab_hardware_record_template_ledger_mismatch_count"],
            0,
        )
        self.assertTrue(
            blocked_icc[
                "moonlab_hardware_record_template_candidate_found"])
        self.assertTrue(
            blocked_icc[
                "moonlab_hardware_submission_scope_ledger_recorded"])
        self.assertEqual(
            blocked_icc[
                "moonlab_hardware_submission_scope_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            blocked_icc[
                "moonlab_hardware_submission_scope_recorded_ready"],
            blocked_icc[
                "moonlab_hardware_submission_scope_expected_ready"],
        )
        self.assertTrue(
            blocked_icc["moonlab_hardware_result_ledger_recorded"])
        self.assertEqual(
            blocked_icc["moonlab_hardware_result_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(blocked_icc["moonlab_hardware_result_row_count"], 0)
        self.assertTrue(blocked_icc["resource_icc_evidence_recorded"])
        self.assertEqual(
            blocked_icc["resource_icc_evidence_mismatch_count"],
            0,
        )
        self.assertTrue(blocked_icc["moonlab_source_icc_evidence_recorded"])
        self.assertEqual(
            blocked_icc["moonlab_source_icc_evidence_mismatch_count"],
            0,
        )
        self.assertTrue(
            blocked_icc["moonlab_advantage_icc_evidence_recorded"])
        self.assertEqual(
            blocked_icc["moonlab_advantage_icc_evidence_mismatch_count"],
            0,
        )
        self.assertTrue(blocked_icc["resource_boundary_recorded"])
        self.assertEqual(blocked_icc["resource_boundary_mismatch_count"], 0)
        self.assertIn(
            "qge_registered_asset_intake.py",
            blocked_icc["registered_asset_discovery_command"],
        )

        stale_resource_icc_evidence = json.loads(
            json.dumps(partial_resource_icc_evidence))
        stale_resource_icc_evidence[
            "asset_requirements_icc_evidence"
        ]["missing_map_count"] = 0
        stale_resource_icc_evidence[
            "registered_asset_intake_icc_evidence"
        ]["whole_game_hardware_execution_claimed"] = True
        stale_resource_icc_gate = moonlab_deployment_gate.build_gate(
            partial_coverage,
            partial_inventory,
            partial_requirements,
            partial_plan,
            job_specs,
            job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            registered_asset_intake=partial_registered_asset_intake,
            resource_icc_evidence=stale_resource_icc_evidence,
            resource_icc_evidence_required=True,
            source_icc_evidence=partial_source_icc_evidence,
            source_icc_evidence_required=True,
            asset_remediation=partial_asset_remediation,
            source_path=Path("stale-resource-icc-pack"),
        )
        stale_resource_icc_blockers = {
            item["id"] for item in stale_resource_icc_gate["blockers"]
        }
        self.assertIn(
            "resource_icc_evidence_consistent",
            stale_resource_icc_blockers,
        )
        stale_resource_icc_criterion = next(
            item for item in stale_resource_icc_gate["criteria"]
            if item["id"] == "resource_icc_evidence_consistent")
        self.assertEqual(stale_resource_icc_criterion["status"], "blocked")
        self.assertTrue(any(
            item.get("sidecar") == "asset_requirements_icc_evidence"
            and "missing_map_count" in item.get("fields", [])
            for item in stale_resource_icc_criterion[
                "resource_icc_evidence_mismatches"]
        ))
        self.assertTrue(any(
            flag.get("flag") == "whole_game_hardware_execution_claimed"
            for flag in stale_resource_icc_criterion[
                "resource_icc_evidence_overclaim_flags"]
        ))

        stale_plan = moonlab_full_game_plan.build_plan(
            partial_coverage,
            partial_inventory,
            breadth_evidence=partial_breadth,
            moonlab_job_results=job_results,
            submission_packet=submission_packet,
            hardware_record_template=hardware_template,
        )
        stale_gate = moonlab_deployment_gate.build_gate(
            partial_coverage,
            partial_inventory,
            partial_requirements,
            stale_plan,
            job_specs,
            job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            asset_remediation=partial_asset_remediation,
            source_path=Path("stale-pack"),
        )
        stale_blocker_ids = {
            item["id"] for item in stale_gate["blockers"]
        }
        self.assertIn(
            "registered_asset_handoff_consistent", stale_blocker_ids)
        stale_handoff_criterion = next(
            item for item in stale_gate["criteria"]
            if item["id"] == "registered_asset_handoff_consistent")
        self.assertEqual(stale_handoff_criterion["status"], "blocked")
        self.assertFalse(
            stale_handoff_criterion["registered_asset_handoff_recorded"])
        self.assertTrue(any(
            "asset_handoff_status" in action
            for action in stale_gate["next_actions"]
        ))

        stale_row_plan = json.loads(json.dumps(partial_plan))
        stale_row_plan["map_deployment_rows"] = [
            row for row in stale_row_plan["map_deployment_rows"]
            if row.get("map") != "e1m1"
        ]
        stale_row_gate = moonlab_deployment_gate.build_gate(
            partial_coverage,
            partial_inventory,
            partial_requirements,
            stale_row_plan,
            job_specs,
            job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            asset_remediation=partial_asset_remediation,
            source_path=Path("stale-row-pack"),
        )
        stale_row_blockers = {
            item["id"] for item in stale_row_gate["blockers"]
        }
        self.assertIn(
            "moonlab_full_game_plan_ledger_consistent",
            stale_row_blockers,
        )
        stale_row_criterion = next(
            item for item in stale_row_gate["criteria"]
            if item["id"] == "moonlab_full_game_plan_ledger_consistent")
        self.assertEqual(stale_row_criterion["status"], "blocked")
        self.assertIn(
            "e1m1",
            stale_row_criterion[
                "moonlab_full_game_plan_ledger_missing_row_maps"],
        )
        self.assertTrue(any(
            "qge_moonlab_full_game_plan.json" in action
            for action in stale_row_gate["next_actions"]
        ))

        all_maps = breadth_evidence.QUAKE_REGISTERED_SINGLE_PLAYER_MAPS
        complete_coverage = breadth_evidence.build_full_game_map_coverage(
            all_maps)
        complete_inventory = {
            "schema": "qge.asset_inventory.v0",
            "map_set": "quake_registered_single_player",
            "status": "complete",
            "target_map_count": len(all_maps),
            "available_map_count": len(all_maps),
            "missing_map_count": 0,
            "invalid_pak_count": 0,
            "invalid_bsp_count": 0,
            "available_maps": list(all_maps),
            "missing_maps": [],
            "full_game_asset_ready": True,
        }
        complete_requirements = {
            "schema": "qge.asset_requirements.v0",
            "status": "complete",
            "target_map_count": len(all_maps),
            "present_map_count": len(all_maps),
            "missing_map_count": 0,
            "missing_maps": [],
            "claim_posture": {
                "asset_requirements_satisfied": True,
                "whole_game_hardware_execution_claimed": False,
                "hardware_quantum_advantage_claimed": False,
                "dense_70000_qubit_state_claimed": False,
            },
        }
        complete_breadth = {
            "schema": "qge.breadth_evidence.v0",
            "matrix_runs": [
                {
                    "map": name,
                    "route_contract_authority_ready": True,
                    "route_contract_authority_blockers": [],
                }
                for name in all_maps
            ],
        }
        complete_job_results = {
            "schema": "qge.moonlab_job_results.v0",
            "overall_status": "simulator_complete_hardware_not_submitted",
            "selected_job_count": 4,
            "completed_simulator_job_count": 4,
            "completed_native_replay_job_count": 2,
            "blocked_job_count": 0,
            "hardware_candidate_job_count": 1,
            "hardware_submitted_job_count": 0,
            "jobs": moonlab_selected_job_result_jobs(
                complete_coverage,
                complete_inventory,
                complete_requirements,
            ),
        }
        complete_plan = moonlab_full_game_plan.build_plan(
            complete_coverage,
            complete_inventory,
            breadth_evidence=complete_breadth,
            moonlab_job_results=complete_job_results,
            submission_packet=submission_packet,
            hardware_record_template=hardware_template,
        )
        complete_source_icc_evidence = source_icc_for(complete_plan)
        complete_resource_boundary_sources = resource_boundary_sources_for(
            complete_coverage)
        complete_resource_boundary_ledgers = (
            resource_boundary_audit.expected_resource_boundary_ledgers(
                complete_resource_boundary_sources)
        )
        ready_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            complete_plan,
            job_specs,
            complete_job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            source_icc_evidence=complete_source_icc_evidence,
            source_icc_evidence_required=True,
            advantage_artifacts=advantage_artifacts,
            advantage_icc_evidence=advantage_icc_evidence,
            advantage_icc_evidence_required=True,
            resource_envelope=complete_resource_boundary_ledgers[
                "resource_envelope"],
            native_backend_boundary=complete_resource_boundary_ledgers[
                "native_backend_boundary"],
            resource_boundary_sources=complete_resource_boundary_sources,
            resource_boundary_required=True,
            artifact_paths=advantage_artifact_paths,
            source_path=Path("complete-pack"),
        )
        self.assertEqual(
            ready_gate["status"],
            "ready_for_moonlab_simulator_deployment_claim")
        self.assertTrue(
            ready_gate["whole_game_moonlab_deployment_claim_allowed"])
        self.assertFalse(
            ready_gate["whole_game_hardware_execution_claim_allowed"])
        self.assertFalse(ready_gate["hardware_quantum_advantage_claim_allowed"])
        self.assertEqual(ready_gate["failed_criterion_count"], 0)
        self.assertTrue(ready_gate["summary"]["route_contracts_complete"])
        self.assertEqual(
            ready_gate["summary"][
                "moonlab_full_game_plan_ledger_mismatch_count"],
            0,
        )
        self.assertTrue(
            ready_gate["summary"][
                "covered_route_contract_authority_complete"])
        self.assertTrue(
            ready_gate["summary"]["moonlab_coverage_ledger_recorded"])
        self.assertEqual(
            ready_gate["summary"][
                "moonlab_coverage_ledger_mismatch_count"],
            0,
        )
        self.assertTrue(
            ready_gate["summary"][
                "moonlab_selected_job_result_ledger_recorded"])
        self.assertEqual(
            ready_gate["summary"][
                "moonlab_selected_job_result_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            ready_gate["summary"][
                "moonlab_selected_job_artifact_evidence_mismatch_count"],
            0,
        )
        self.assertTrue(
            ready_gate["summary"][
                "moonlab_submission_packet_ledger_recorded"])
        self.assertEqual(
            ready_gate["summary"][
                "moonlab_submission_packet_ledger_mismatch_count"],
            0,
        )
        self.assertTrue(
            ready_gate["summary"][
                "moonlab_hardware_record_template_ledger_recorded"])
        self.assertEqual(
            ready_gate["summary"][
                "moonlab_hardware_record_template_ledger_mismatch_count"],
            0,
        )
        self.assertTrue(
            ready_gate["summary"][
                "moonlab_hardware_submission_scope_ledger_recorded"])
        self.assertEqual(
            ready_gate["summary"][
                "moonlab_hardware_submission_scope_ledger_mismatch_count"],
            0,
        )
        self.assertTrue(
            ready_gate["summary"][
                "moonlab_hardware_result_ledger_recorded"])
        self.assertEqual(
            ready_gate["summary"][
                "moonlab_hardware_result_ledger_mismatch_count"],
            0,
        )
        self.assertTrue(
            ready_gate["summary"]["moonlab_source_icc_evidence_recorded"])
        self.assertEqual(
            ready_gate["summary"][
                "moonlab_source_icc_evidence_mismatch_count"],
            0,
        )
        self.assertTrue(
            ready_gate["summary"][
                "moonlab_advantage_icc_evidence_recorded"])
        self.assertEqual(
            ready_gate["summary"][
                "moonlab_advantage_icc_evidence_mismatch_count"],
            0,
        )
        self.assertTrue(
            ready_gate["summary"]["resource_boundary_recorded"])
        self.assertEqual(
            ready_gate["summary"]["resource_boundary_mismatch_count"],
            0,
        )
        icc = moonlab_deployment_gate.build_icc_evidence(
            ready_gate, out_path=Path("qge_moonlab_deployment_gate.json"))
        self.assertEqual(
            icc["runtime_backend"], "qge_moonlab_deployment_gate")
        self.assertEqual(
            icc["completion_reason"], "qge_moonlab_deployment_gate_ready")
        self.assertEqual(
            icc["moonlab_full_game_plan_ledger_mismatch_count"], 0)
        self.assertEqual(
            icc["moonlab_submission_packet_ledger_mismatch_count"], 0)
        self.assertEqual(
            icc[
                "moonlab_hardware_record_template_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            icc[
                "moonlab_hardware_submission_scope_ledger_mismatch_count"],
            0,
        )
        self.assertEqual(
            icc["moonlab_hardware_result_ledger_mismatch_count"], 0)
        self.assertEqual(
            icc["moonlab_source_icc_evidence_mismatch_count"], 0)
        self.assertEqual(
            icc["moonlab_advantage_icc_evidence_mismatch_count"], 0)
        self.assertEqual(icc["resource_boundary_mismatch_count"], 0)
        self.assertTrue(
            icc["whole_game_moonlab_deployment_claim_allowed"])

        stale_boundary_envelope = json.loads(json.dumps(
            complete_resource_boundary_ledgers["resource_envelope"]))
        stale_boundary_envelope[
            "posture"
        ]["hardware_quantum_advantage_claimed"] = True
        stale_native_boundary = json.loads(json.dumps(
            complete_resource_boundary_ledgers["native_backend_boundary"]))
        stale_native_boundary["targets"][0]["status"] = "blocked"
        stale_boundary_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            complete_plan,
            job_specs,
            complete_job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            advantage_artifacts=advantage_artifacts,
            advantage_icc_evidence=advantage_icc_evidence,
            advantage_icc_evidence_required=True,
            resource_envelope=stale_boundary_envelope,
            native_backend_boundary=stale_native_boundary,
            resource_boundary_sources=complete_resource_boundary_sources,
            resource_boundary_required=True,
            source_path=Path("stale-boundary-pack"),
        )
        stale_boundary_blockers = {
            item["id"] for item in stale_boundary_gate["blockers"]
        }
        self.assertIn(
            "resource_boundary_ledgers_consistent",
            stale_boundary_blockers,
        )
        stale_boundary_criterion = next(
            item for item in stale_boundary_gate["criteria"]
            if item["id"] == "resource_boundary_ledgers_consistent")
        self.assertEqual(stale_boundary_criterion["status"], "blocked")
        self.assertTrue(any(
            item.get("ledger") == "resource_envelope" and
            "posture.hardware_quantum_advantage_claimed" in
            item.get("fields", [])
            for item in stale_boundary_criterion[
                "resource_boundary_mismatches"]
        ))
        self.assertTrue(any(
            item.get("ledger") == "native_backend_boundary" and
            "targets[0].status" in item.get("fields", [])
            for item in stale_boundary_criterion[
                "resource_boundary_mismatches"]
        ))
        self.assertTrue(any(
            flag.get("flag") == "hardware_quantum_advantage_claimed"
            for flag in stale_boundary_criterion[
                "resource_boundary_overclaim_flags"]
        ))
        self.assertFalse(
            stale_boundary_gate[
                "whole_game_moonlab_deployment_claim_allowed"])

        nested_overclaim_plan = json.loads(json.dumps(complete_plan))
        nested_overclaim_plan["map_deployment_rows"][0]["evidence"] = [
            {
                "nested_posture": {
                    "hardware_quantum_advantage_claimed": True,
                },
            },
        ]
        nested_overclaim_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            nested_overclaim_plan,
            job_specs,
            complete_job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            source_path=Path("nested-overclaim-pack"),
        )
        nested_overclaim_blockers = {
            item["id"] for item in nested_overclaim_gate["blockers"]
        }
        self.assertIn(
            "no_forbidden_hardware_or_advantage_overclaim",
            nested_overclaim_blockers,
        )
        nested_overclaim_criterion = next(
            item for item in nested_overclaim_gate["criteria"]
            if item["id"] == "no_forbidden_hardware_or_advantage_overclaim")
        self.assertEqual(nested_overclaim_criterion["status"], "blocked")
        self.assertTrue(any(
            "moonlab_full_game_plan.map_deployment_rows[0].evidence[0]"
            in flag["source"]
            for flag in nested_overclaim_criterion["overclaim_flags"]
        ))
        self.assertFalse(
            nested_overclaim_gate[
                "whole_game_moonlab_deployment_claim_allowed"])

        stale_submission_packet = json.loads(json.dumps(submission_packet))
        stale_submission_packet["candidate_jobs"] = []
        stale_submission_packet["hardware_candidate_job_count"] = 0
        stale_submission_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            complete_plan,
            job_specs,
            complete_job_results,
            stale_submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            source_path=Path("stale-submission-packet-pack"),
        )
        stale_submission_blockers = {
            item["id"] for item in stale_submission_gate["blockers"]
        }
        self.assertIn(
            "moonlab_submission_packet_ledger_consistent",
            stale_submission_blockers,
        )
        stale_submission_criterion = next(
            item for item in stale_submission_gate["criteria"]
            if item["id"] == "moonlab_submission_packet_ledger_consistent")
        self.assertEqual(stale_submission_criterion["status"], "blocked")
        self.assertIn(
            "qge.light_transport_qae_benchmark.mlae.v0",
            stale_submission_criterion[
                "moonlab_submission_packet_missing_candidate_ids"],
        )
        self.assertFalse(
            stale_submission_gate[
                "whole_game_moonlab_deployment_claim_allowed"])

        stale_hardware_template = json.loads(json.dumps(hardware_template))
        stale_hardware_template["candidate_digest"] = "stale-digest"
        stale_hardware_template["record"]["candidate_digest"] = "stale-digest"
        stale_template_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            complete_plan,
            job_specs,
            complete_job_results,
            submission_packet,
            stale_hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            source_path=Path("stale-hardware-template-pack"),
        )
        stale_template_blockers = {
            item["id"] for item in stale_template_gate["blockers"]
        }
        self.assertIn(
            "moonlab_hardware_record_template_consistent",
            stale_template_blockers,
        )
        stale_template_criterion = next(
            item for item in stale_template_gate["criteria"]
            if item["id"] == "moonlab_hardware_record_template_consistent")
        self.assertEqual(stale_template_criterion["status"], "blocked")
        self.assertGreater(
            stale_template_criterion[
                "moonlab_hardware_record_template_row_mismatch_count"],
            0,
        )
        self.assertFalse(
            stale_template_gate[
                "whole_game_moonlab_deployment_claim_allowed"])

        stale_scope = json.loads(json.dumps(hardware_submission_scope))
        stale_scope["candidate_digests"] = {}
        stale_scope["passing_check_count"] = 0
        stale_scope_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            complete_plan,
            job_specs,
            complete_job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=stale_scope,
            source_path=Path("stale-hardware-submission-scope-pack"),
        )
        stale_scope_blockers = {
            item["id"] for item in stale_scope_gate["blockers"]
        }
        self.assertIn(
            "moonlab_hardware_submission_scope_consistent",
            stale_scope_blockers,
        )
        stale_scope_criterion = next(
            item for item in stale_scope_gate["criteria"]
            if item["id"] == "moonlab_hardware_submission_scope_consistent")
        self.assertEqual(stale_scope_criterion["status"], "blocked")
        self.assertIn(
            "candidate_digests",
            stale_scope_criterion[
                "moonlab_hardware_submission_scope_mismatches"],
        )
        self.assertFalse(
            stale_scope_gate[
                "whole_game_moonlab_deployment_claim_allowed"])

        stale_hardware_result_jobs = json.loads(
            json.dumps(complete_job_results))
        stale_hardware_result_job = next(
            job for job in stale_hardware_result_jobs["jobs"]
            if job.get("job_id") == "qge.light_transport_qae_benchmark.mlae.v0")
        stale_hardware_result_job["backend_results"].append({
            "backend_id": "moonlab-hardware/mock-qpu",
            "backend_kind": "moonlab_hardware",
            "status": "completed",
            "run_id": "moonlab-hw-run-001",
            "candidate_digest": "stale-digest",
            "hardware_record_sha256": "a" * 64,
            "submitted_utc": "2026-05-25T16:00:00Z",
            "completed_utc": "2026-05-25T16:01:00Z",
            "shot_schedule": {
                "shots": 384,
                "batches": 3,
                "schedule_id": "qge-mlae-384-v1",
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
        })
        stale_hardware_result_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            complete_plan,
            job_specs,
            stale_hardware_result_jobs,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            source_path=Path("stale-hardware-result-pack"),
        )
        stale_hardware_result_blockers = {
            item["id"] for item in stale_hardware_result_gate["blockers"]
        }
        self.assertIn(
            "moonlab_hardware_result_ledger_consistent",
            stale_hardware_result_blockers,
        )
        stale_hardware_result_criterion = next(
            item for item in stale_hardware_result_gate["criteria"]
            if item["id"] == "moonlab_hardware_result_ledger_consistent")
        self.assertEqual(stale_hardware_result_criterion["status"], "blocked")
        self.assertIn(
            "qge.light_transport_qae_benchmark.mlae.v0",
            stale_hardware_result_criterion[
                "moonlab_hardware_result_row_mismatch_job_ids"],
        )
        self.assertFalse(
            stale_hardware_result_gate[
                "whole_game_moonlab_deployment_claim_allowed"])

        stale_source_icc_evidence = json.loads(
            json.dumps(complete_source_icc_evidence))
        stale_source_icc_evidence[
            "moonlab_submission_bundle_icc_evidence"
        ]["hardware_candidate_job_count"] = 0
        stale_source_icc_evidence[
            "moonlab_hardware_submission_scope_icc_evidence"
        ]["hardware_quantum_advantage_claimed"] = True
        stale_source_icc_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            complete_plan,
            job_specs,
            complete_job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            source_icc_evidence=stale_source_icc_evidence,
            source_icc_evidence_required=True,
            source_path=Path("stale-source-icc-pack"),
        )
        stale_source_icc_blockers = {
            item["id"] for item in stale_source_icc_gate["blockers"]
        }
        self.assertIn(
            "moonlab_source_icc_evidence_consistent",
            stale_source_icc_blockers,
        )
        stale_source_icc_criterion = next(
            item for item in stale_source_icc_gate["criteria"]
            if item["id"] == "moonlab_source_icc_evidence_consistent")
        self.assertEqual(stale_source_icc_criterion["status"], "blocked")
        self.assertTrue(any(
            item.get("sidecar") == "moonlab_submission_bundle_icc_evidence"
            and "hardware_candidate_job_count" in item.get("fields", [])
            for item in stale_source_icc_criterion[
                "moonlab_source_icc_evidence_mismatches"]
        ))
        self.assertTrue(any(
            flag.get("flag") == "hardware_quantum_advantage_claimed"
            for flag in stale_source_icc_criterion[
                "moonlab_source_icc_evidence_overclaim_flags"]
        ))
        self.assertFalse(
            stale_source_icc_gate[
                "whole_game_moonlab_deployment_claim_allowed"])

        stale_advantage_icc_evidence = json.loads(
            json.dumps(advantage_icc_evidence))
        stale_advantage_icc_evidence[
            "qae_moonlab_grover_schedule_plan_icc_evidence"
        ]["ready_observation_count"] = 0
        stale_advantage_icc_evidence[
            "advantage_icc_evidence"
        ]["hardware_quantum_advantage_claimed"] = True
        stale_advantage_icc_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            complete_plan,
            job_specs,
            complete_job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            advantage_artifacts=advantage_artifacts,
            advantage_icc_evidence=stale_advantage_icc_evidence,
            advantage_icc_evidence_required=True,
            artifact_paths=advantage_artifact_paths,
            source_path=Path("stale-advantage-icc-pack"),
        )
        stale_advantage_icc_blockers = {
            item["id"] for item in stale_advantage_icc_gate["blockers"]
        }
        self.assertIn(
            "moonlab_advantage_icc_evidence_consistent",
            stale_advantage_icc_blockers,
        )
        stale_advantage_icc_criterion = next(
            item for item in stale_advantage_icc_gate["criteria"]
            if item["id"] == "moonlab_advantage_icc_evidence_consistent")
        self.assertEqual(stale_advantage_icc_criterion["status"], "blocked")
        self.assertTrue(any(
            item.get("sidecar") ==
            "qae_moonlab_grover_schedule_plan_icc_evidence"
            and "ready_observation_count" in item.get("fields", [])
            for item in stale_advantage_icc_criterion[
                "moonlab_advantage_icc_evidence_mismatches"]
        ))
        self.assertTrue(any(
            flag.get("flag") == "hardware_quantum_advantage_claimed"
            for flag in stale_advantage_icc_criterion[
                "moonlab_advantage_icc_evidence_overclaim_flags"]
        ))
        self.assertFalse(
            stale_advantage_icc_gate[
                "whole_game_moonlab_deployment_claim_allowed"])

        coverage_only_job_results = dict(complete_job_results)
        coverage_only_job_results["jobs"] = [
            moonlab_coverage_ledger_result_job(
                complete_coverage,
                complete_inventory,
                complete_requirements,
            ),
        ]
        coverage_only_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            complete_plan,
            job_specs,
            coverage_only_job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            source_path=Path("coverage-only-results-pack"),
        )
        coverage_only_blockers = {
            item["id"] for item in coverage_only_gate["blockers"]
        }
        self.assertIn(
            "moonlab_selected_job_result_ledger_consistent",
            coverage_only_blockers,
        )
        self.assertNotIn(
            "moonlab_coverage_ledger_consistent",
            coverage_only_blockers,
        )
        coverage_only_criterion = next(
            item for item in coverage_only_gate["criteria"]
            if item["id"] ==
            "moonlab_selected_job_result_ledger_consistent")
        self.assertEqual(coverage_only_criterion["status"], "blocked")
        self.assertEqual(
            coverage_only_criterion[
                "moonlab_selected_job_result_job_count"],
            1,
        )
        self.assertIn(
            "qge.render_primary_framebuffer.sparse_dwt_replay.v0",
            coverage_only_criterion[
                "moonlab_selected_job_missing_result_ids"],
        )
        self.assertTrue(any(
            "qge_moonlab_job_specs.json" in action
            for action in coverage_only_gate["next_actions"]
        ))

        artifactless_job_results = json.loads(
            json.dumps(complete_job_results))
        artifactless_job_results["jobs"][0]["artifact_evidence"] = []
        artifactless_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            complete_plan,
            job_specs,
            artifactless_job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            source_path=Path("artifactless-results-pack"),
        )
        artifactless_blockers = {
            item["id"] for item in artifactless_gate["blockers"]
        }
        self.assertIn(
            "moonlab_selected_job_result_ledger_consistent",
            artifactless_blockers,
        )
        artifactless_criterion = next(
            item for item in artifactless_gate["criteria"]
            if item["id"] ==
            "moonlab_selected_job_result_ledger_consistent")
        self.assertEqual(artifactless_criterion["status"], "blocked")
        self.assertEqual(
            artifactless_criterion[
                "moonlab_selected_job_artifact_evidence_mismatch_count"],
            3,
        )
        self.assertIn(
            "qge.render_primary_framebuffer.sparse_dwt_replay.v0",
            artifactless_criterion[
                "moonlab_selected_job_artifact_missing_evidence_job_ids"],
        )

        stale_job_results = dict(complete_job_results)
        stale_job_results["jobs"] = moonlab_selected_job_result_jobs(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            observations_override={
                "coverage_status": "partial",
                "missing_map_count": 30,
            },
        )
        stale_ledger_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            complete_plan,
            job_specs,
            stale_job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            source_path=Path("stale-ledger-pack"),
        )
        stale_ledger_blockers = {
            item["id"] for item in stale_ledger_gate["blockers"]
        }
        self.assertIn(
            "moonlab_coverage_ledger_consistent",
            stale_ledger_blockers,
        )
        self.assertNotIn(
            "moonlab_selected_job_result_ledger_consistent",
            stale_ledger_blockers,
        )
        stale_ledger_criterion = next(
            item for item in stale_ledger_gate["criteria"]
            if item["id"] == "moonlab_coverage_ledger_consistent")
        self.assertEqual(stale_ledger_criterion["status"], "blocked")
        self.assertIn(
            "coverage_status",
            stale_ledger_criterion["moonlab_coverage_ledger_mismatches"],
        )
        self.assertIn(
            "missing_map_count",
            stale_ledger_criterion["moonlab_coverage_ledger_mismatches"],
        )
        self.assertTrue(any(
            "qge_moonlab_job_results.json" in action
            for action in stale_ledger_gate["next_actions"]
        ))

        legacy_plan = dict(complete_plan)
        for key in (
            "route_contract_schema",
            "route_contract_map_count",
            "route_contracts_complete",
            "missing_route_contract_maps",
            "route_contracts",
        ):
            legacy_plan.pop(key, None)
        legacy_gate = moonlab_deployment_gate.build_gate(
            complete_coverage,
            complete_inventory,
            complete_requirements,
            legacy_plan,
            job_specs,
            complete_job_results,
            submission_packet,
            hardware_template,
            submission_bundle=submission_bundle,
            hardware_submission_scope=hardware_submission_scope,
            source_path=Path("legacy-pack"),
        )
        legacy_blockers = {
            item["id"] for item in legacy_gate["blockers"]
        }
        self.assertIn(
            "full_game_route_contracts_complete", legacy_blockers)
        self.assertIn("full_game_deployment_plan_complete", legacy_blockers)
        self.assertFalse(
            legacy_gate["whole_game_moonlab_deployment_claim_allowed"])

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            resource = tmpdir / "resource"
            resource.mkdir()
            publication_pack.write_json(
                resource / "qge_full_game_map_coverage.json",
                partial_coverage,
            )
            publication_pack.write_json(
                resource / "qge_asset_inventory.json", partial_inventory)
            publication_pack.write_json(
                resource / "qge_asset_requirements.json",
                partial_requirements,
            )
            publication_pack.write_json(
                resource / "qge_moonlab_full_game_plan.json", partial_plan)
            publication_pack.write_json(
                resource / "qge_moonlab_job_specs.json", job_specs)
            publication_pack.write_json(
                resource / "qge_moonlab_job_results.json", job_results)
            publication_pack.write_json(
                resource / "qge_moonlab_submission_packet.json",
                submission_packet,
            )
            publication_pack.write_json(
                resource / "qge_moonlab_hardware_record_template.json",
                hardware_template,
            )
            publication_pack.write_json(
                resource / "qge_registered_asset_intake.json",
                partial_registered_asset_intake,
            )
            manifest = {
                "schema": "qge.publication_pack.v0",
                "artifacts": {
                    "resource": {
                        "full_game_map_coverage": {
                            "path": str(
                                resource / "qge_full_game_map_coverage.json")
                        },
                        "asset_inventory": {
                            "path": str(resource / "qge_asset_inventory.json")
                        },
                        "asset_requirements": {
                            "path": str(
                                resource / "qge_asset_requirements.json")
                        },
                        "moonlab_full_game_plan": {
                            "path": str(
                                resource / "qge_moonlab_full_game_plan.json")
                        },
                        "moonlab_job_specs": {
                            "path": str(
                                resource / "qge_moonlab_job_specs.json")
                        },
                        "moonlab_job_results": {
                            "path": str(
                                resource / "qge_moonlab_job_results.json")
                        },
                        "moonlab_submission_packet": {
                            "path": str(
                                resource /
                                "qge_moonlab_submission_packet.json")
                        },
                        "moonlab_hardware_record_template": {
                            "path": str(
                                resource /
                                "qge_moonlab_hardware_record_template.json")
                        },
                        "registered_asset_intake": {
                            "path": str(
                                resource /
                                "qge_registered_asset_intake.json")
                        },
                        "registered_asset_intake_markdown": {
                            "path": str(
                                resource /
                                "qge_registered_asset_intake.md")
                        },
                        "registered_asset_intake_script": {
                            "path": str(
                                resource / "install_registered_assets.sh")
                        },
                        "registered_asset_intake_icc_evidence": {
                            "path": str(
                                resource /
                                "qge_registered_asset_intake_icc_evidence.json"
                            )
                        },
                    }
                },
            }
            publication_pack.write_json(
                tmpdir / "publication_manifest.json", manifest)
            out_path = tmpdir / "qge_moonlab_deployment_gate.json"
            markdown_path = tmpdir / "qge_moonlab_deployment_gate.md"
            icc_path = tmpdir / "qge_moonlab_deployment_gate_icc.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    moonlab_deployment_gate.main([
                        str(tmpdir),
                        "--out",
                        str(out_path),
                        "--markdown",
                        str(markdown_path),
                        "--icc-json",
                        str(icc_path),
                    ]),
                    0,
                )
            self.assertIn(
                "QGE_MOONLAB_DEPLOYMENT_GATE", stdout.getvalue())
            cli_gate = publication_pack.load_json(out_path)
            self.assertEqual(cli_gate["status"], "blocked")
            self.assertEqual(
                cli_gate["asset_remediation"][
                    "registered_asset_install_script"],
                str(resource / "install_registered_assets.sh"),
            )
            self.assertTrue(
                cli_gate["summary"][
                    "post_install_capture_queue_command_present"])
            self.assertTrue(
                cli_gate["summary"]["registered_asset_handoff_present"])
            self.assertEqual(
                cli_gate["summary"][
                    "registered_asset_handoff_licensed_asset_required_count"],
                30,
            )
            cli_icc = publication_pack.load_json(icc_path)
            self.assertEqual(
                cli_icc["completion_reason"],
                "qge_moonlab_deployment_gate_blocked")
            self.assertFalse(
                cli_icc["whole_game_moonlab_deployment_claim_allowed"])
            self.assertEqual(
                cli_icc["registered_asset_install_script"],
                str(resource / "install_registered_assets.sh"),
            )
            self.assertTrue(
                cli_icc["post_install_capture_queue_command_present"])
            self.assertTrue(cli_icc["registered_asset_handoff_present"])
            self.assertEqual(
                cli_icc[
                    "registered_asset_handoff_licensed_asset_required_count"],
                30,
            )
            self.assertEqual(
                cli_icc[
                    "registered_asset_intake_discovery_roots_scanned_count"],
                4,
            )
            self.assertEqual(
                cli_icc["registered_asset_intake_steam_quake_path_count"],
                3,
            )
            self.assertTrue(
                cli_icc["registered_asset_discovery_command_present"])
            self.assertIn(
                "qge_registered_asset_intake.py",
                cli_icc["registered_asset_discovery_command"],
            )


class BreadthEvidenceTests(unittest.TestCase):
    def test_asset_inventory_reports_registered_map_availability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asset_root = Path(tmp) / "id1"
            maps_dir = asset_root / "maps"
            maps_dir.mkdir(parents=True)
            (maps_dir / "e1m2.bsp").write_bytes(minimal_bsp_bytes())
            write_pak(asset_root / "pak0.pak", [
                "maps/start.bsp",
                "maps/e1m1.bsp",
                "maps/custom.bsp",
            ])

            inventory = asset_inventory.build_inventory(asset_root)

            self.assertEqual(inventory["schema"], "qge.asset_inventory.v0")
            self.assertEqual(
                inventory["available_maps"],
                ["start", "e1m1", "e1m2"],
            )
            self.assertIn("e2m1", inventory["missing_maps"])
            self.assertEqual(inventory["missing_map_count"], 29)
            self.assertEqual(inventory["extra_maps"], ["custom"])
            self.assertFalse(inventory["full_game_asset_ready"])
            self.assertEqual(inventory["pak_count"], 1)
            self.assertEqual(inventory["loose_bsp_count"], 1)
            self.assertEqual(inventory["invalid_bsp_count"], 0)
            self.assertTrue(
                inventory["available_map_sources"]["e1m1"][0]["bsp_valid"])
            self.assertIn(
                "QGE Asset Inventory",
                asset_inventory.markdown_report(inventory),
            )
            icc = asset_inventory.build_icc_evidence(inventory)
            self.assertEqual(
                icc["completion_reason"],
                "qge_registered_asset_inventory_complete",
            )
            self.assertFalse(icc["whole_game_moonlab_coverage_claimed"])

            requirements = asset_requirements.build_requirements(inventory)
            self.assertEqual(
                requirements["schema"], "qge.asset_requirements.v0")
            self.assertEqual(
                requirements["status"],
                "blocked_missing_registered_assets")
            self.assertEqual(requirements["present_map_count"], 3)
            self.assertEqual(requirements["missing_map_count"], 29)
            self.assertIn(
                "maps/e2m1.bsp",
                requirements["missing_required_entries"])
            e1m2 = next(
                item for item in requirements["requirements"]
                if item["map"] == "e1m2")
            self.assertEqual(e1m2["status"], "present")
            self.assertEqual(
                e1m2["next_action"], "keep_existing_registered_asset")
            req_icc = asset_requirements.build_icc_evidence(
                requirements,
                out_path=Path("qge_asset_requirements.json"),
            )
            self.assertEqual(
                req_icc["runtime_backend"], "qge_asset_requirements")
            self.assertEqual(req_icc["missing_map_count"], 29)
            self.assertFalse(
                req_icc["whole_game_moonlab_deployment_claimed"])
            self.assertIn(
                "blocked_missing_registered_assets",
                asset_requirements.markdown_report(requirements))

            req_path = Path(tmp) / "qge_asset_requirements.json"
            req_md = Path(tmp) / "qge_asset_requirements.md"
            req_icc_path = Path(tmp) / "qge_asset_requirements_icc.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    asset_requirements.main([
                        "--asset-root",
                        str(asset_root),
                        "--json",
                        str(req_path),
                        "--markdown",
                        str(req_md),
                        "--icc-json",
                        str(req_icc_path),
                    ]),
                    0,
                )
            self.assertIn("QGE_ASSET_REQUIREMENTS", stdout.getvalue())
            cli_req = publication_pack.load_json(req_path)
            self.assertEqual(
                cli_req["schema"], "qge.asset_requirements.v0")

    def test_asset_inventory_rejects_placeholder_bsp_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            asset_root = tmpdir / "id1"
            maps_dir = asset_root / "maps"
            maps_dir.mkdir(parents=True)
            (maps_dir / "e1m3.bsp").write_bytes(b"not a bsp")
            write_pak(
                asset_root / "pak0.pak",
                ["maps/e1m4.bsp", "maps/e1m5.bsp"],
                payloads={"maps/e1m4.bsp": b"not a bsp either"},
            )

            inventory = asset_inventory.build_inventory(asset_root)

            self.assertEqual(inventory["available_maps"], ["e1m5"])
            self.assertIn("e1m3", inventory["missing_maps"])
            self.assertIn("e1m4", inventory["missing_maps"])
            self.assertEqual(inventory["invalid_bsp_count"], 2)
            invalid_maps = {
                item["map"] for item in inventory["invalid_bsp_sources"]
            }
            self.assertEqual(invalid_maps, {"e1m3", "e1m4"})
            self.assertEqual(
                inventory["pak_files"][0]["invalid_bsp_entry_count"], 1)
            self.assertIn(
                "Invalid BSPs",
                asset_inventory.markdown_report(inventory))

            breadth_path = tmpdir / "breadth_evidence.json"
            breadth_evidence.write_json(
                breadth_path,
                {
                    "schema": "qge.full_game_map_coverage.v0",
                    "map_set": "quake_registered_single_player",
                    "target_map_count": 32,
                    "covered_map_count": 2,
                    "missing_map_count": 30,
                    "coverage_ratio": 2 / 32,
                    "covered_maps": ["e1m1", "e1m2"],
                    "missing_maps": [
                        "e1m3",
                        "e1m4",
                        "e1m5",
                    ],
                },
            )
            queue = full_game_capture_queue.build_queue(SimpleNamespace(
                source=breadth_path,
                limit=3,
                frames=3,
                wait_frames=12,
                trace=True,
                special_maps_last=True,
                authority_smoke=True,
                force_world_metrics=True,
                asset_root=asset_root,
                include_unavailable_assets=False,
                env=[],
            ))
            self.assertEqual(queue["available_asset_maps"], ["e1m5"])
            self.assertEqual([job["map"] for job in queue["jobs"]], ["e1m5"])
            self.assertIn("e1m3", queue["asset_unavailable_missing_maps"])
            self.assertIn("e1m4", queue["asset_unavailable_missing_maps"])

    def test_registered_asset_intake_builds_safe_copy_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            current_root = tmpdir / "current-id1"
            candidate_root = tmpdir / "registered-id1"
            current_root.mkdir()
            candidate_root.mkdir()
            candidate_maps = candidate_root / "MAPS"
            candidate_maps.mkdir()
            write_pak(current_root / "pak0.pak", [
                "maps/start.bsp",
                "maps/e1m1.bsp",
            ])
            write_pak(
                candidate_root / "PAK1.PAK",
                [
                    "maps/e2m1.bsp",
                    "maps/e2m2.bsp",
                    "maps/e3m1.bsp",
                ],
                payloads={"maps/e3m1.bsp": b"not-a-valid-bsp"},
            )
            (candidate_maps / "e3m2.bsp").write_bytes(minimal_bsp_bytes())

            intake = registered_asset_intake.build_intake(
                current_root,
                [candidate_root],
                publication_pack_dir=tmpdir / "publication-pack",
            )
            self.assertEqual(
                intake["schema"], "qge.registered_asset_intake.v0")
            self.assertEqual(
                intake["status"], "partial_candidate_assets_found")
            self.assertEqual(intake["current_available_map_count"], 2)
            self.assertEqual(intake["candidate_scan_target_count"], 1)
            self.assertEqual(
                intake["candidate_scan_targets"][0]["path"],
                str(candidate_root),
            )
            self.assertEqual(intake["candidate_new_map_count"], 3)
            self.assertEqual(intake["copy_plan_unblocked_map_count"], 3)
            self.assertEqual(intake["copy_plan_blocked_map_count"], 0)
            self.assertEqual(intake["actionable_copy_plan_count"], 2)
            self.assertEqual(
                intake["missing_map_count_after_plan"],
                intake["current_missing_map_count"] - 3,
            )
            self.assertTrue(intake["manual_registered_asset_required"])
            self.assertEqual(
                intake["registered_asset_blocker_reason"],
                "partial_plan_remaining_registered_assets_missing",
            )
            self.assertEqual(intake["copy_script_mode"], "partial_copy_plan")
            self.assertFalse(intake["no_candidate_asset_copy_plan"])
            self.assertIn("e2m1", intake["candidate_new_maps"])
            self.assertIn("e3m2", intake["candidate_new_maps"])
            self.assertEqual(intake["invalid_candidate_source_count"], 1)
            pak_plan = next(
                item for item in intake["copy_plan"]
                if item["kind"] == "copy_pak")
            self.assertEqual(pak_plan["status"], "planned")
            self.assertEqual(
                pak_plan["maps_unblocked"], ["e2m1", "e2m2"])
            self.assertTrue(
                pak_plan["destination"].endswith("current-id1/pak1.pak"))
            self.assertEqual(
                intake["post_install_verification_command_count"], 2)
            self.assertIn(
                "qge_registered_asset_intake.py",
                intake["candidate_discovery_command"],
            )
            self.assertIn(
                "--discover-common",
                intake["candidate_discovery_command"],
            )
            self.assertTrue(any(
                command["kind"] == "capture_queue"
                for command in
                intake["post_install_verification"]["commands"]
            ))
            loose_plan = next(
                item for item in intake["copy_plan"]
                if item["kind"] == "copy_loose_bsp")
            self.assertEqual(loose_plan["maps_unblocked"], ["e3m2"])
            script = "\n".join(registered_asset_intake.script_lines(intake))
            self.assertIn("QGE_REGISTERED_ASSET_INTAKE_LICENSE_CHECK", script)
            self.assertIn("verify_sha256", script)
            self.assertIn("copy_registered_asset", script)
            self.assertIn("cp -n", script)
            self.assertIn("QGE_REGISTERED_ASSET_PARTIAL_COPY_PLAN", script)
            self.assertIn("qge_asset_inventory.py", script)
            self.assertIn("qge_full_game_capture_queue.py", script)
            icc = registered_asset_intake.build_icc_evidence(
                intake,
                out_path=Path("qge_registered_asset_intake.json"),
            )
            self.assertEqual(
                icc["runtime_backend"], "qge_registered_asset_intake")
            self.assertFalse(icc["asset_intake_copies_game_data"])
            self.assertEqual(
                icc["post_install_verification_command_count"], 2)
            self.assertEqual(icc["candidate_scan_target_count"], 1)
            self.assertEqual(icc["copy_plan_unblocked_map_count"], 3)
            self.assertEqual(icc["copy_plan_blocked_map_count"], 0)
            self.assertTrue(icc["post_install_capture_queue_command_present"])
            self.assertTrue(icc["manual_registered_asset_required"])
            self.assertEqual(icc["copy_script_mode"], "partial_copy_plan")
            self.assertIn("missing_maps_after_plan", icc)
            markdown = registered_asset_intake.markdown_report(intake)
            self.assertIn("partial_candidate_assets_found", markdown)
            self.assertIn("Blocker Summary", markdown)
            self.assertIn("partial_copy_plan", markdown)
            self.assertIn("Candidate Discovery Refresh", markdown)
            self.assertIn("Post-Install Verification", markdown)
            self.assertIn("qge_full_game_capture_queue.py", markdown)

            blocked_current = tmpdir / "blocked-current-id1"
            blocked_candidate = tmpdir / "blocked-candidate-id1"
            blocked_maps = blocked_current / "maps"
            blocked_candidate_maps = blocked_candidate / "maps"
            blocked_maps.mkdir(parents=True)
            blocked_candidate_maps.mkdir(parents=True)
            write_pak(blocked_current / "pak0.pak", [
                "maps/start.bsp",
                "maps/e1m1.bsp",
            ])
            (blocked_maps / "e2m1.bsp").write_bytes(b"not-a-valid-bsp")
            (blocked_candidate_maps / "e2m1.bsp").write_bytes(
                minimal_bsp_bytes())

            blocked_intake = registered_asset_intake.build_intake(
                blocked_current,
                [blocked_candidate],
            )
            self.assertEqual(
                blocked_intake["status"], "blocked_candidate_copy_plan")
            self.assertEqual(blocked_intake["candidate_new_maps"], ["e2m1"])
            self.assertEqual(
                blocked_intake["copy_plan_blocked_maps"], ["e2m1"])
            self.assertEqual(
                blocked_intake["copy_plan_unblocked_map_count"], 0)
            self.assertEqual(blocked_intake["actionable_copy_plan_count"], 0)
            self.assertIn("e2m1", blocked_intake["missing_maps_after_plan"])
            self.assertEqual(
                blocked_intake["missing_map_count_after_plan"],
                blocked_intake["current_missing_map_count"],
            )
            self.assertEqual(
                blocked_intake["registered_asset_blocker_reason"],
                "candidate_copy_plan_blocked",
            )
            self.assertEqual(
                blocked_intake["copy_script_mode"], "blocked_copy_plan")
            blocked_script = "\n".join(
                registered_asset_intake.script_lines(blocked_intake))
            self.assertIn(
                "QGE_REGISTERED_ASSET_BLOCKED_COPY_PLAN",
                blocked_script,
            )
            blocked_icc = registered_asset_intake.build_icc_evidence(
                blocked_intake)
            self.assertEqual(
                blocked_icc["copy_plan_blocked_maps"], ["e2m1"])
            self.assertEqual(
                blocked_icc["registered_asset_blocker_reason"],
                "candidate_copy_plan_blocked",
            )

            out_path = tmpdir / "qge_registered_asset_intake.json"
            markdown_path = tmpdir / "qge_registered_asset_intake.md"
            script_path = tmpdir / "install_registered_assets.sh"
            icc_path = tmpdir / "qge_registered_asset_intake_icc.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    registered_asset_intake.main([
                        "--current-root",
                        str(current_root),
                        "--candidate",
                        str(candidate_root),
                        "--publication-pack",
                        str(tmpdir / "publication-pack"),
                        "--json",
                        str(out_path),
                        "--markdown",
                        str(markdown_path),
                        "--script-out",
                        str(script_path),
                        "--icc-json",
                        str(icc_path),
                    ]),
                    0,
                )
            self.assertIn(
                "QGE_REGISTERED_ASSET_INTAKE", stdout.getvalue())
            cli_intake = publication_pack.load_json(out_path)
            self.assertEqual(cli_intake["candidate_new_map_count"], 3)
            self.assertTrue(script_path.stat().st_mode & 0o111)
            cli_icc = publication_pack.load_json(icc_path)
            self.assertEqual(
                cli_icc["completion_reason"],
                "qge_registered_asset_intake_plan_recorded")
            self.assertIn(
                "qge_registered_asset_intake.py",
                cli_icc["candidate_discovery_command"],
            )

    def test_registered_asset_intake_discovers_candidate_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            current_root = tmpdir / "current-id1"
            search_root = tmpdir / "library"
            candidate_root = search_root / "Quake" / "ID1"
            current_root.mkdir()
            candidate_root.mkdir(parents=True)
            write_pak(current_root / "pak0.pak", [
                "maps/start.bsp",
                "maps/e1m1.bsp",
            ])
            write_pak(candidate_root / "PAK1.PAK", [
                "maps/e2m1.bsp",
                "maps/e2m2.bsp",
            ])

            discovery = registered_asset_intake.discover_candidate_paths(
                [search_root],
                max_depth=3,
            )
            self.assertEqual(discovery["found_candidate_count"], 1)
            self.assertEqual(
                discovery["found_candidates"][0]["reason"],
                "contains_pak_files",
            )
            intake = registered_asset_intake.build_intake(
                current_root,
                [Path(discovery["found_candidates"][0]["path"])],
                discovery=discovery,
            )
            self.assertEqual(intake["discovered_candidate_count"], 1)
            self.assertEqual(intake["candidate_scan_target_count"], 1)
            self.assertEqual(
                intake["discovery_metadata"]["roots_scanned_count"], 1)
            self.assertEqual(intake["candidate_new_map_count"], 2)
            self.assertIn(
                "Candidate paths found: 1",
                registered_asset_intake.markdown_report(intake),
            )
            icc = registered_asset_intake.build_icc_evidence(intake)
            self.assertEqual(icc["discovered_candidate_count"], 1)
            self.assertEqual(icc["candidate_scan_target_count"], 1)
            self.assertEqual(icc["discovery_roots_scanned_count"], 1)

            out_path = tmpdir / "intake.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    registered_asset_intake.main([
                        "--current-root",
                        str(current_root),
                        "--discover-root",
                        str(search_root),
                        "--discover-max-depth",
                        "3",
                        "--json",
                        str(out_path),
                    ]),
                    0,
                )
            self.assertIn(
                "QGE_REGISTERED_ASSET_INTAKE", stdout.getvalue())
            cli_intake = publication_pack.load_json(out_path)
            self.assertEqual(cli_intake["discovered_candidate_count"], 1)
            self.assertEqual(cli_intake["candidate_new_map_count"], 2)

            empty_root = tmpdir / "empty-library"
            empty_root.mkdir()
            empty_path = tmpdir / "empty_intake.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(
                    registered_asset_intake.main([
                        "--current-root",
                        str(current_root),
                        "--discover-root",
                        str(empty_root),
                        "--json",
                        str(empty_path),
                    ]),
                    0,
                )
            self.assertIn(
                "QGE_REGISTERED_ASSET_INTAKE", stdout.getvalue())
            empty_intake = publication_pack.load_json(empty_path)
            self.assertEqual(
                empty_intake["status"], "blocked_no_candidate_assets")
            self.assertEqual(empty_intake["discovered_candidate_count"], 0)
            self.assertTrue(
                empty_intake["manual_registered_asset_required"])
            self.assertEqual(
                empty_intake["registered_asset_blocker_reason"],
                "no_candidate_assets_found",
            )
            self.assertEqual(
                empty_intake["copy_script_mode"], "no_op_blocked")
            self.assertTrue(empty_intake["no_candidate_asset_copy_plan"])
            self.assertEqual(empty_intake["candidate_scan_target_count"], 0)
            empty_script = "\n".join(
                registered_asset_intake.script_lines(empty_intake))
            self.assertIn(
                "QGE_REGISTERED_ASSET_COPY_SCRIPT_MODE no_op_blocked",
                empty_script,
            )
            self.assertIn(
                "QGE_REGISTERED_ASSET_NO_CANDIDATES",
                empty_script,
            )
            self.assertIn(
                "QGE_REGISTERED_ASSET_MISSING_MAP_COUNT",
                empty_script,
            )
            empty_icc = registered_asset_intake.build_icc_evidence(
                empty_intake)
            self.assertTrue(empty_icc["manual_registered_asset_required"])
            self.assertEqual(
                empty_icc["registered_asset_blocker_reason"],
                "no_candidate_assets_found",
            )
            self.assertTrue(empty_icc["no_candidate_asset_copy_plan"])
            self.assertEqual(empty_icc["candidate_scan_target_count"], 0)

            enhanced_root = tmpdir / "QuakeEnhanced"
            enhanced_id1 = enhanced_root / "rerelease" / "id1"
            enhanced_id1.mkdir(parents=True)
            write_pak(enhanced_id1 / "PAK1.PAK", [
                "maps/e2m1.bsp",
                "maps/e2m2.bsp",
            ])
            enhanced_targets = (
                registered_asset_intake.candidate_scan_targets(
                    [enhanced_root]))
            self.assertEqual(
                enhanced_targets,
                [{"kind": "asset_root", "path": enhanced_id1}],
            )
            enhanced_intake = registered_asset_intake.build_intake(
                current_root,
                [enhanced_root],
            )
            self.assertEqual(enhanced_intake["candidate_new_map_count"], 2)
            self.assertEqual(
                enhanced_intake["candidate_scan_targets"][0]["path"],
                str(enhanced_id1),
            )

    def test_registered_asset_intake_derives_steam_quake_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            current_root = tmpdir / "current-id1"
            steam_root = tmpdir / "Steam"
            external_root = tmpdir / "ExternalSteamLibrary"
            libraryfolders = steam_root / "steamapps" / "libraryfolders.vdf"
            manifest = external_root / "steamapps" / "appmanifest_2310.acf"
            candidate_root = (
                external_root / "steamapps" / "common" /
                "Quake Enhanced" / "rerelease" / "id1"
            )
            current_root.mkdir()
            libraryfolders.parent.mkdir(parents=True)
            manifest.parent.mkdir(parents=True)
            candidate_root.mkdir(parents=True)

            def vdf_path(path: Path) -> str:
                return str(path).replace("\\", "\\\\")

            libraryfolders.write_text(
                '"libraryfolders"\n'
                "{\n"
                '    "0"\n'
                "    {\n"
                f'        "path" "{vdf_path(steam_root)}"\n'
                "    }\n"
                '    "1"\n'
                "    {\n"
                f'        "path" "{vdf_path(external_root)}"\n'
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            manifest.write_text(
                '"AppState"\n'
                "{\n"
                '    "appid" "2310"\n'
                '    "installdir" "Quake Enhanced"\n'
                "}\n",
                encoding="utf-8",
            )
            write_pak(current_root / "pak0.pak", [
                "maps/start.bsp",
                "maps/e1m1.bsp",
            ])
            write_pak(candidate_root / "PAK1.PAK", [
                "maps/e2m1.bsp",
                "maps/e2m2.bsp",
            ])

            original_libraryfolders = (
                registered_asset_intake.STEAM_LIBRARYFOLDERS)
            try:
                registered_asset_intake.STEAM_LIBRARYFOLDERS = [
                    libraryfolders]
                steam_paths = (
                    registered_asset_intake.steam_quake_discovery_paths())
                self.assertIn(candidate_root, steam_paths)

                discovery = registered_asset_intake.discover_candidate_paths(
                    steam_paths,
                    max_depth=0,
                )
                self.assertEqual(discovery["found_candidate_count"], 1)
                intake = registered_asset_intake.build_intake(
                    current_root,
                    [Path(discovery["found_candidates"][0]["path"])],
                    discovery=discovery,
                )
            finally:
                registered_asset_intake.STEAM_LIBRARYFOLDERS = (
                    original_libraryfolders)

            self.assertEqual(intake["candidate_new_map_count"], 2)
            metadata = intake["discovery_metadata"]
            self.assertEqual(metadata["steam_library_root_count"], 2)
            self.assertGreaterEqual(metadata["steam_quake_path_count"], 6)
            self.assertEqual(
                metadata["roots_scanned_count"], len(steam_paths))
            markdown = registered_asset_intake.markdown_report(intake)
            self.assertIn("Steam library roots", markdown)
            self.assertIn("Steam Quake candidate paths", markdown)
            icc = registered_asset_intake.build_icc_evidence(intake)
            self.assertEqual(icc["steam_library_root_count"], 2)
            self.assertGreaterEqual(icc["steam_quake_path_count"], 6)

    def write_matrix(self,
                     directory: Path,
                     *,
                     map_name: str,
                     ready: bool = True,
                     fallback_count: int = 0) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "README.txt").write_text(
            f"Map: {map_name}\n",
            encoding="utf-8",
        )
        matrix_path = directory / "vanilla_capture_matrix.json"
        probe_targets = [
            "qge_context_get_or_create_render_acceleration",
            "qge_dwt_render",
            "qge_metal_init_common",
        ]
        probe_proofs = {
            "qge_context_get_or_create_render_acceleration": {
                "event_count": 1,
                "backends": ["Metal"],
                "paths": ["native_sparse_dwt_render_bridge"],
                "results": ["created"],
                "phases": ["create"],
                "native_values": [1],
                "active_values": [1],
                "native_bridge_evidence": True,
                "active_evidence": True,
            },
            "qge_dwt_render": {
                "event_count": 1,
                "backends": ["Metal"],
                "paths": ["native_sparse_dwt_render_bridge"],
                "results": ["native"],
                "phases": ["idwt"],
                "native_values": [1],
                "active_values": [1],
                "native_bridge_evidence": True,
                "active_evidence": True,
            },
            "qge_metal_init_common": {
                "event_count": 1,
                "backends": ["Metal"],
                "paths": ["native_sparse_dwt_render_bridge"],
                "results": ["active"],
                "phases": ["create"],
                "native_values": [],
                "active_values": [],
                "native_bridge_evidence": True,
                "active_evidence": True,
            },
        }
        breadth_evidence.write_json(matrix_path, {
            "schema": "qge.vanilla_capture_matrix.v0",
            "capture_dir": str(directory),
            "conformance_summary": {
                "ready_for_complete_claim": ready,
                "moonlab_authority_ready": ready,
                "fallback_count": fallback_count,
                "qge_surface_surrogates": 0,
                "qge_primary_owner": "qge_3d",
                "qge_render_idwt_backend": "native",
                "qge_render_native_idwt": 3,
                "qge_render_cpu_idwt": 0,
                "qge_backend_gate_event_count": 3,
                "qge_backend_gate_backends": ["Metal"],
                "qge_backend_gate_paths": [
                    "native_sparse_dwt_render_bridge",
                    "sparse_dwt_cpu_render_path",
                ],
                "qge_backend_gate_render_bridge_paths": [
                    "native_sparse_dwt_render_bridge",
                ],
                "qge_backend_gate_render_bridge_active": True,
                "qge_runtime_backend_probe_event_count": 3,
                "qge_runtime_backend_probe_targets": probe_targets,
                "qge_runtime_backend_probe_backends": ["Metal"],
                "qge_runtime_backend_probe_paths": [
                    "native_sparse_dwt_render_bridge",
                ],
                "qge_runtime_backend_probe_results": ["active", "created", "native"],
                "qge_required_runtime_backend_probe_targets": probe_targets,
                "qge_runtime_backend_probe_proofs": probe_proofs,
                "qge_runtime_backend_probe_missing_targets": [],
                "qge_runtime_backend_probe_native_targets": probe_targets,
                "qge_runtime_backend_probe_resolved": True,
                "moonlab_domain_readiness": {
                    "qge_primary_framebuffer": {
                        "ready": ready,
                        "evidence": {
                            "owner": "qge_3d",
                            "fallback_count": fallback_count,
                            "surrogate_count": 0,
                        },
                    },
                    "render_quantum_workload": {
                        "ready": ready,
                        "evidence": {
                            "idwt_backend": "native",
                            "native_bridge_count": 12,
                            "cpu_idwt_count": 0,
                        },
                    },
                    "capture_artifacts": {
                        "ready": ready,
                        "evidence": {
                            "agent_stream_runs_success": ready,
                        },
                    },
                    "visibility_authority": {
                        "ready": ready,
                        "evidence": {
                            "authority_gate_count": 3,
                            "authority_apply_count": 3,
                        },
                    },
                    "audio_authority": {
                        "ready": ready,
                        "evidence": {
                            "source_spatial_count": 2,
                        },
                    },
                    "projectile_live_authority": {
                        "ready": ready,
                        "evidence": {
                            "authority_gate_count": 2,
                            "active_projectiles": 1,
                            "decision_or_measurement_count": 1,
                        },
                    },
                    "ai_authority": {
                        "ready": ready,
                        "evidence": {
                            "decision_count": 4,
                        },
                    },
                },
            },
        })
        return matrix_path

    def write_publication_pack(self, directory: Path, ready: bool = True) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        manifest_path = directory / "publication_manifest.json"
        breadth_evidence.write_json(manifest_path, {
            "schema": "qge.publication_pack.v0",
            "runtime_summary": {
                "publication_ready_for_complete_claim": ready,
                "vanilla_ready_for_complete_claim": ready,
                "fallback_count": 0,
                "surrogate_count": 0,
                "performance_source": "graphics_qge_candidate",
            },
        })
        breadth_evidence.write_json(
            directory / "qge_publication_icc_evidence.json",
            {
                "completion_reason": (
                    "qge_publication_artifact_pack_complete"
                    if ready else "qge_publication_artifact_pack_evidence_only"
                ),
            },
        )
        return manifest_path

    def test_breadth_evidence_complete_for_ready_matrix_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            matrix_a = self.write_matrix(tmpdir / "run_a", map_name="e1m1")
            matrix_b = self.write_matrix(tmpdir / "run_b", map_name="e1m2")
            pack = self.write_publication_pack(tmpdir / "publication")
            args = SimpleNamespace(
                inputs=[],
                matrix=[matrix_a, matrix_b],
                publication_pack=[pack],
                min_runs=2,
                min_maps=2,
            )

            manifest = breadth_evidence.build_manifest(args)
            aggregate = manifest["aggregate"]
            self.assertTrue(aggregate["breadth_ready_for_complete_claim"])
            self.assertEqual(aggregate["matrix_run_count"], 2)
            self.assertEqual(aggregate["map_count"], 2)
            self.assertEqual(aggregate["maps"], ["e1m1", "e1m2"])
            self.assertEqual(
                aggregate["route_contract_authority_ready_run_count"], 2)
            self.assertEqual(
                aggregate["route_contract_authority_blocker_count"], 0)
            self.assertTrue(
                manifest["matrix_runs"][0][
                    "route_contract_authority_ready"])
            route_authority = (
                manifest["matrix_runs"][0]["route_contract_authority"])
            self.assertIn(
                "ai_authority",
                route_authority["required_authority_domains"],
            )
            self.assertIn("domain_checks", route_authority)
            self.assertNotIn("domain_status", route_authority)
            self.assertTrue(route_authority["domain_checks"])
            self.assertEqual(
                manifest["full_game_coverage"]["schema"],
                "qge.full_game_map_coverage.v0",
            )
            self.assertEqual(
                aggregate["full_game_map_coverage_status"], "partial")
            self.assertEqual(aggregate["full_game_map_target_count"], 32)
            self.assertEqual(aggregate["full_game_map_covered_count"], 2)
            self.assertEqual(aggregate["full_game_map_missing_count"], 30)
            self.assertIn(
                "start",
                aggregate["full_game_map_missing_maps"],
            )
            self.assertEqual(aggregate["total_fallback_count"], 0)
            self.assertGreater(aggregate["total_native_bridge_count"], 0)
            self.assertEqual(aggregate["total_backend_gate_event_count"], 6)
            self.assertEqual(aggregate["backend_gate_backends"], ["Metal"])
            self.assertEqual(
                aggregate["backend_gate_render_bridge_paths"],
                ["native_sparse_dwt_render_bridge"],
            )
            self.assertEqual(aggregate["backend_gate_render_bridge_run_count"], 2)
            self.assertEqual(
                aggregate["total_runtime_backend_probe_event_count"], 6)
            self.assertEqual(
                aggregate["runtime_backend_probe_targets"],
                [
                    "qge_context_get_or_create_render_acceleration",
                    "qge_dwt_render",
                    "qge_metal_init_common",
                ],
            )
            self.assertEqual(aggregate["runtime_backend_probe_run_count"], 2)
            self.assertEqual(
                aggregate["runtime_backend_probe_resolved_run_count"], 2)
            self.assertEqual(
                aggregate["runtime_backend_probe_missing_targets"], [])
            self.assertEqual(
                aggregate["runtime_backend_probe_proofs"]
                ["qge_dwt_render"]["native_bridge_run_count"], 2)

            icc = breadth_evidence.build_icc_evidence(
                manifest,
                tmpdir / "breadth_evidence.json",
                tmpdir / "qge_breadth_icc_evidence.json",
            )
            self.assertEqual(icc["runtime_backend"], "qge_breadth_evidence")
            self.assertEqual(
                icc["completion_reason"],
                "qge_breadth_evidence_pack_complete",
            )
            self.assertTrue(icc["breadth_ready_for_complete_claim"])
            self.assertEqual(icc["full_game_map_coverage_status"], "partial")
            self.assertEqual(icc["full_game_map_target_count"], 32)
            self.assertEqual(icc["full_game_map_covered_count"], 2)
            self.assertEqual(icc["full_game_map_missing_count"], 30)
            self.assertEqual(icc["total_backend_gate_event_count"], 6)
            self.assertEqual(icc["total_runtime_backend_probe_event_count"], 6)
            self.assertEqual(icc["runtime_backend_probe_resolved_run_count"], 2)
            self.assertEqual(
                icc["route_contract_authority_ready_run_count"], 2)
            self.assertEqual(
                icc["route_contract_authority_blocker_count"], 0)

    def test_breadth_evidence_blocks_fallback_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            matrix = self.write_matrix(
                tmpdir / "run_a",
                map_name="e1m1",
                ready=False,
                fallback_count=1,
            )
            args = SimpleNamespace(
                inputs=[],
                matrix=[matrix],
                publication_pack=[],
                min_runs=1,
                min_maps=1,
            )

            manifest = breadth_evidence.build_manifest(args)
            aggregate = manifest["aggregate"]
            self.assertFalse(aggregate["breadth_ready_for_complete_claim"])
            self.assertIn("matrix_0:fallback_count_nonzero",
                          aggregate["issues"])
            icc = breadth_evidence.build_icc_evidence(
                manifest,
                tmpdir / "breadth_evidence.json",
                tmpdir / "qge_breadth_icc_evidence.json",
            )
            self.assertEqual(
                icc["completion_reason"],
                "qge_breadth_evidence_pack_evidence_only",
            )

    def test_breadth_evidence_blocks_insufficient_map_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            matrix_a = self.write_matrix(tmpdir / "run_a", map_name="e1m1")
            matrix_b = self.write_matrix(tmpdir / "run_b", map_name="e1m1")
            args = SimpleNamespace(
                inputs=[],
                matrix=[matrix_a, matrix_b],
                publication_pack=[],
                min_runs=2,
                min_maps=2,
            )

            manifest = breadth_evidence.build_manifest(args)
            aggregate = manifest["aggregate"]
            self.assertFalse(aggregate["breadth_ready_for_complete_claim"])
            self.assertEqual(aggregate["map_count"], 1)
            self.assertIn("minimum_map_count_not_met", aggregate["issues"])
            icc = breadth_evidence.build_icc_evidence(
                manifest,
                tmpdir / "breadth_evidence.json",
                tmpdir / "qge_breadth_icc_evidence.json",
            )
            self.assertEqual(
                icc["completion_reason"],
                "qge_breadth_evidence_pack_evidence_only",
            )

    def test_full_game_capture_queue_from_breadth_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            matrix_a = self.write_matrix(tmpdir / "run_a", map_name="e1m1")
            matrix_b = self.write_matrix(tmpdir / "run_b", map_name="e1m2")
            args = SimpleNamespace(
                inputs=[],
                matrix=[matrix_a, matrix_b],
                publication_pack=[],
                min_runs=2,
                min_maps=2,
                map_set="quake_registered_single_player",
            )
            manifest = breadth_evidence.build_manifest(args)
            breadth_path = tmpdir / "breadth_evidence.json"
            breadth_evidence.write_json(breadth_path, manifest)

            queue = full_game_capture_queue.build_queue(SimpleNamespace(
                source=breadth_path,
                limit=2,
                frames=3,
                wait_frames=12,
                trace=True,
                special_maps_last=True,
                authority_smoke=True,
                force_world_metrics=True,
                env=["QGE_STREAM_LAUNCH=open"],
            ))

            self.assertEqual(queue["schema"], "qge.full_game_capture_queue.v0")
            self.assertEqual(queue["queue_job_count"], 2)
            self.assertTrue(queue["special_maps_last"])
            self.assertTrue(queue["route_contracts_complete"])
            self.assertEqual(queue["route_contract_map_count"], 32)
            self.assertEqual(queue["missing_route_contract_maps"], [])
            self.assertEqual(queue["jobs"][0]["map"], "e1m3")
            self.assertEqual(queue["jobs"][1]["map"], "e1m4")
            self.assertEqual(
                queue["jobs"][0]["route_profile"],
                "noesis_authority_smoke",
            )
            self.assertEqual(
                queue["jobs"][0]["route_contract"]["map_class"],
                "registered_combat",
            )
            self.assertEqual(
                queue["jobs"][0]["route_contract"]["episode"], "e1")
            self.assertEqual(queue["jobs"][0]["route_contract"]["slot"], 3)
            self.assertTrue(
                queue["jobs"][0]["route_contract"]["combat_required"])
            self.assertIn(
                "ai_authority",
                queue["jobs"][0]["route_contract"]["authority_domains"],
            )
            self.assertEqual(queue["covered_map_count_before"], 2)
            self.assertEqual(queue["covered_map_count_after_queue"], 4)
            self.assertEqual(queue["post_capture"]["breadth_min_runs"], 4)
            self.assertEqual(queue["post_capture"]["breadth_min_maps"], 4)
            self.assertEqual(
                queue["jobs"][0]["environment"]
                ["QGE_HARNESS_FORCE_WORLD_METRICS"],
                "1",
            )
            self.assertEqual(
                queue["jobs"][0]["environment"]["QGE_STREAM_LAUNCH"],
                "open",
            )
            self.assertEqual(
                queue["jobs"][0]["environment"]["QGE_STREAM_PLAYER"],
                "noesis",
            )
            self.assertEqual(
                queue["jobs"][0]["environment"]["QGE_STREAM_FIRE_MIN_FRAMES"],
                "4",
            )
            self.assertEqual(
                queue["jobs"][0]["environment"]["QGE_NOESIS_MIN_CAPTURE_WAIT"],
                "100",
            )
            self.assertEqual(
                queue["jobs"][0]["environment"]["QGE_HARNESS_FIRE_TEST"],
                "1",
            )
            self.assertEqual(
                queue["jobs"][0]["environment"]["QGE_HARNESS_SPRITE_TEST"],
                "1",
            )
            self.assertEqual(
                queue["jobs"][0]["environment"]
                ["QGE_HARNESS_SND_QUANTUM_SOURCE_AUTHORITY"],
                "1",
            )
            self.assertEqual(
                queue["jobs"][0]["environment"]
                ["QGE_HARNESS_PHYSICS_AUTHORITATIVE"],
                "1",
            )
            script = "\n".join(full_game_capture_queue.script_lines(queue))
            self.assertIn("QGE_FULL_GAME_CAPTURE_QUEUE_MAP e1m3", script)
            self.assertIn(
                "QGE_FULL_GAME_CAPTURE_ROUTE_PROFILE noesis_authority_smoke",
                script,
            )
            self.assertIn(
                "QGE_FULL_GAME_CAPTURE_ROUTE_CLASS registered_combat",
                script,
            )
            self.assertIn("--min-runs 4", script)
            self.assertIn("--min-maps 4", script)
            self.assertIn(str(matrix_a), script)
            markdown = full_game_capture_queue.markdown_report(queue)
            self.assertIn("QGE Full Game Capture Queue", markdown)
            self.assertIn("noesis_authority_smoke", markdown)
            self.assertIn("Route contracts: 32 (complete=True)", markdown)
            self.assertIn("Asset-unavailable missing maps", markdown)

            canonical_queue = full_game_capture_queue.build_queue(SimpleNamespace(
                source=breadth_path,
                limit=1,
                frames=3,
                wait_frames=12,
                trace=True,
                special_maps_last=False,
                authority_smoke=True,
                force_world_metrics=True,
                env=[],
            ))
            self.assertEqual(canonical_queue["jobs"][0]["map"], "start")
            self.assertEqual(
                canonical_queue["jobs"][0]["route_profile"],
                "start_hub_route_authority_smoke",
            )
            self.assertEqual(
                canonical_queue["jobs"][0]["route_contract"]["map_class"],
                "start_hub",
            )
            self.assertFalse(
                canonical_queue["jobs"][0]["route_contract"]
                ["combat_required"],
            )
            self.assertNotIn(
                "ai_authority",
                canonical_queue["jobs"][0]["route_contract"]
                ["authority_domains"],
            )
            self.assertEqual(canonical_queue["special_route_maps"], ["end"])
            self.assertEqual(canonical_queue["start_hub_route_maps"], ["start"])
            self.assertTrue(
                canonical_queue["route_contracts"]["end"]
                ["special_route_required"],
            )
            self.assertEqual(
                canonical_queue["route_contracts"]["end"]["map_class"],
                "endgame_special",
            )
            self.assertEqual(
                canonical_queue["jobs"][0]["environment"]["QGE_NOESIS_PLAN"],
                "start-hub-route",
            )
            self.assertEqual(
                canonical_queue["jobs"][0]["environment"]
                ["QGE_NOESIS_REQUIRE_COMBAT"],
                "0",
            )
            self.assertEqual(
                canonical_queue["jobs"][0]["environment"]
                ["QGE_NOESIS_MIN_LOG_PHASES"],
                "2",
            )

    def test_full_game_capture_queue_skips_unavailable_local_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            matrix_a = self.write_matrix(tmpdir / "run_a", map_name="e1m1")
            matrix_b = self.write_matrix(tmpdir / "run_b", map_name="e1m2")
            args = SimpleNamespace(
                inputs=[],
                matrix=[matrix_a, matrix_b],
                publication_pack=[],
                min_runs=2,
                min_maps=2,
                map_set="quake_registered_single_player",
            )
            manifest = breadth_evidence.build_manifest(args)
            breadth_path = tmpdir / "breadth_evidence.json"
            breadth_evidence.write_json(breadth_path, manifest)
            asset_root = tmpdir / "id1"
            asset_root.mkdir()
            write_pak(asset_root / "pak0.pak", ["maps/e1m3.bsp"])

            queue = full_game_capture_queue.build_queue(SimpleNamespace(
                source=breadth_path,
                limit=3,
                frames=3,
                wait_frames=12,
                trace=True,
                special_maps_last=True,
                authority_smoke=True,
                force_world_metrics=True,
                asset_root=asset_root,
                include_unavailable_assets=False,
                env=[],
            ))

            self.assertEqual(queue["queue_job_count"], 1)
            self.assertEqual(queue["status"], "pending_partial_asset_blocked")
            self.assertEqual(queue["jobs"][0]["map"], "e1m3")
            self.assertTrue(queue["asset_filter_enabled"])
            self.assertEqual(queue["available_asset_maps"], ["e1m3"])
            self.assertEqual(queue["asset_available_missing_maps"], ["e1m3"])
            self.assertIn("e1m4", queue["asset_unavailable_missing_maps"])
            self.assertIn("start", queue["asset_unavailable_missing_maps"])
            self.assertEqual(queue["covered_map_count_after_queue"], 3)

            override = full_game_capture_queue.build_queue(SimpleNamespace(
                source=breadth_path,
                limit=2,
                frames=3,
                wait_frames=12,
                trace=True,
                special_maps_last=True,
                authority_smoke=True,
                force_world_metrics=True,
                asset_root=asset_root,
                include_unavailable_assets=True,
                env=[],
            ))
            self.assertFalse(override["asset_filter_enabled"])
            self.assertEqual(override["status"], "pending")
            self.assertEqual([job["map"] for job in override["jobs"]],
                             ["e1m3", "e1m4"])

            blocked = full_game_capture_queue.build_queue(SimpleNamespace(
                source=breadth_path,
                limit=2,
                frames=3,
                wait_frames=12,
                trace=True,
                special_maps_last=True,
                authority_smoke=True,
                force_world_metrics=True,
                asset_root=tmpdir / "empty-id1",
                include_unavailable_assets=False,
                env=[],
            ))
            self.assertEqual(blocked["queue_job_count"], 0)
            self.assertEqual(blocked["status"], "blocked_asset_unavailable")
            self.assertIn("Status: blocked_asset_unavailable",
                          full_game_capture_queue.markdown_report(blocked))


class ImageMetricsTests(unittest.TestCase):
    def test_markdown_report_without_optional_dependencies(self) -> None:
        metrics = {
            "reference": "classic.png",
            "candidate": "quantum.png",
            "width": 2,
            "height": 2,
            "resize_note": None,
            "mae_rgb": 0.0,
            "mae_rgb_normalized": 0.0,
            "rmse_rgb": 0.0,
            "psnr_db": None,
            "psnr_is_infinite": True,
            "luma_mae": 0.0,
            "luma_rmse": 0.0,
            "luma_ssim_global": 1.0,
            "histogram_intersection_rgb": 1.0,
            "reference_occupancy_luma_gt_8": 0.5,
            "candidate_occupancy_luma_gt_8": 0.5,
            "edge": {
                "edge_precision": 1.0,
                "edge_recall": 1.0,
                "edge_f1": 1.0,
                "edge_jaccard": 1.0,
            },
            "blockiness": {
                "reference": {
                    "16": {"ratio": 1.0},
                },
                "candidate": {
                    "16": {"ratio": 1.0},
                },
            },
        }

        markdown = image_metrics.markdown_report(metrics)
        self.assertIn("# QGE Image Metrics", markdown)
        self.assertIn("| PSNR dB | inf |", markdown)
        self.assertIn("| Edge F1 | 1.000000 |", markdown)

    def test_world_frame_metrics_without_optional_dependencies(self) -> None:
        reference = world_frame_metrics.ImageData(
            2,
            2,
            [
                [(0.0, 0.0, 0.0), (0.4, 0.4, 0.4)],
                [(0.2, 0.2, 0.2), (0.6, 0.6, 0.6)],
            ],
        )
        candidate = world_frame_metrics.ImageData(
            2,
            2,
            [
                [(0.0, 0.0, 0.0), (0.5, 0.5, 0.5)],
                [(0.2, 0.2, 0.2), (0.7, 0.7, 0.7)],
            ],
        )

        metrics = world_frame_metrics.compare_images(
            reference, candidate, {"all": (0, 0, 2, 2)}
        )
        region = metrics["regions"]["all"]
        self.assertEqual(metrics["schema"], "qge.world_frame_metrics.v0")
        self.assertEqual(region["pixel_count"], 4)
        self.assertGreater(region["rmse_rgb"], 0.0)
        self.assertGreater(region["candidate_luma_mean"], region["reference_luma_mean"])
        self.assertIn("QGE World Frame Metrics", world_frame_metrics.markdown_report(metrics))

    def test_world_frame_metrics_default_regions_split_viewmodel(self) -> None:
        regions = world_frame_metrics.DEFAULT_REGIONS
        self.assertEqual(regions["world"], (0, 0, 800, 540))
        self.assertEqual(regions["world_upper"], (0, 0, 800, 440))
        self.assertEqual(regions["viewmodel"], (320, 420, 480, 540))

    def test_world_frame_metrics_frame_set_baseline_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            candidate_dir = tmpdir / "candidate"
            baseline_dir = tmpdir / "baseline"
            candidate_dir.mkdir()
            baseline_dir.mkdir()
            reference = tmpdir / "reference.png"
            write_rgb_png(reference, [
                [(0, 0, 0), (80, 80, 80)],
                [(160, 160, 160), (240, 240, 240)],
            ])
            for frame in (1, 2):
                write_rgb_png(candidate_dir / f"frame_{frame:03d}.png", [
                    [(4, 4, 4), (84, 84, 84)],
                    [(164, 164, 164), (244, 244, 244)],
                ])
                write_rgb_png(baseline_dir / f"frame_{frame:03d}.png", [
                    [(16, 16, 16), (96, 96, 96)],
                    [(176, 176, 176), (255, 255, 255)],
                ])

            metrics = world_frame_metrics.compare_frame_set(
                reference,
                candidate_dir,
                {"all": (0, 0, 2, 2)},
                baseline_dir,
            )
            region = metrics["regions"]["all"]
            self.assertEqual(metrics["schema"], "qge.world_frame_metrics.frames.v0")
            self.assertEqual(metrics["frame_count"], 2)
            self.assertLess(region["rmse_rgb"], region["baseline_rmse_rgb"])
            self.assertLess(region["delta_rmse_rgb"], 0.0)
            self.assertEqual(region["candidate_temporal_rmse_rgb"], 0.0)
            self.assertEqual(region["baseline_temporal_rmse_rgb"], 0.0)
            self.assertIn("Delta RMSE", world_frame_metrics.markdown_report(metrics))
            self.assertIn("Candidate Drift", world_frame_metrics.markdown_report(metrics))

    def test_world_frame_metrics_frame_set_temporal_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            reference_dir = tmpdir / "reference"
            candidate_dir = tmpdir / "candidate"
            reference_dir.mkdir()
            candidate_dir.mkdir()
            stable = [
                [(0, 0, 0), (80, 80, 80)],
                [(160, 160, 160), (240, 240, 240)],
            ]
            for frame in (1, 2):
                write_rgb_png(reference_dir / f"frame_{frame:03d}.png", stable)
            write_rgb_png(candidate_dir / "frame_001.png", stable)
            write_rgb_png(candidate_dir / "frame_002.png", [
                [(20, 20, 20), (80, 80, 80)],
                [(160, 160, 160), (220, 220, 220)],
            ])

            metrics = world_frame_metrics.compare_frame_set(
                reference_dir,
                candidate_dir,
                {"all": (0, 0, 2, 2)},
            )
            region = metrics["regions"]["all"]
            self.assertEqual(region["reference_temporal_rmse_rgb"], 0.0)
            self.assertGreater(region["candidate_temporal_rmse_rgb"], 0.0)
            self.assertIn("Candidate Drift", world_frame_metrics.markdown_report(metrics))


class PerformanceSummaryTests(unittest.TestCase):
    def test_parse_log_summary_and_icc_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            log_path = tmpdir / "quantum_quake.log"
            log_path.write_text(
                "\n".join(
                    [
                        "QGE backend gate phase=init backend=Metal "
                        "status=capable, inactive native=1 active=0 "
                        "flags=0x3d path=sparse_dwt_cpu_render_path "
                        "reason=native_backend_available_sparse_dwt_cpu_path_pending_renderer_bridge "
                        "probe=metal_system_device_available",
                        "QGE render frame=7 time=29.5 setup=1 encode=14 raster=8 "
                        "fdwt=2 dwt=3 convert=1 blit=9 native_idwt=3 "
                        "idwt_fallback=0 cpu_idwt=0 idwt_backend=native",
                        "QGE: Average quantum render time: 31.25 ms (24 frames)",
                        "QGE: Backend gate phase=render_bridge backend=Metal "
                        "status=active acceleration native=1 active=1 "
                        "flags=0x17 path=native_sparse_dwt_render_bridge "
                        "reason=native_sparse_dwt_render_bridge_active "
                        "probe=metal_system_device_available",
                        "QGE: Runtime backend probe "
                        "target=qge_metal_init_common phase=create "
                        "backend=Metal path=native_sparse_dwt_render_bridge "
                        "result=active dense_amplitudes=0 qubits=28 "
                        "screen_res=1024",
                        "QGE: Runtime backend probe "
                        "target=qge_context_get_or_create_render_acceleration "
                        "phase=create backend=Metal "
                        "path=native_sparse_dwt_render_bridge result=created "
                        "native=1 active=1 screen_res=1024 "
                        "reason=native_sparse_dwt_render_bridge_active "
                        "probe=metal_system_device_available",
                        "QGE: Runtime backend probe target=qge_dwt_render "
                        "phase=idwt backend=Metal "
                        "path=native_sparse_dwt_render_bridge result=native "
                        "native_render_backend=native native=1 active=1 "
                        "screen_res=1024 levels=6 gpu_reconstruct=1 mode=0 "
                        "active_coeffs=192495 "
                        "reason=native_sparse_dwt_render_bridge_active",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            args = SimpleNamespace(
                paths=[tmpdir],
                max_average_ms=40.0,
                max_render_ms=35.0,
            )

            parsed = perf_summary.parse_log(tmpdir)
            self.assertTrue(parsed["exists"])
            self.assertEqual(parsed["render_frame_count"], 1)
            self.assertEqual(parsed["engine_average_quantum_ms"], 31.25)
            self.assertEqual(parsed["render_time_ms"]["max"], 29.5)
            self.assertEqual(parsed["components"]["encode"]["max_ms"], 14.0)
            self.assertEqual(parsed["backend_gate_count"], 2)
            self.assertEqual(parsed["backend_gate_event_count"], 2)
            self.assertEqual(parsed["runtime_backend_probe_event_count"], 3)
            self.assertTrue(parsed["runtime_backend_probe_resolved"])
            self.assertEqual(parsed["runtime_backend_probe_missing_targets"], [])
            self.assertTrue(
                parsed["runtime_backend_probe_proofs"]["qge_dwt_render"]
                ["native_bridge_evidence"]
            )
            self.assertEqual(
                parsed["runtime_backend_probe_targets"],
                [
                    "qge_context_get_or_create_render_acceleration",
                    "qge_dwt_render",
                    "qge_metal_init_common",
                ],
            )
            self.assertEqual(
                parsed["backend_gate_paths"],
                ["native_sparse_dwt_render_bridge", "sparse_dwt_cpu_render_path"],
            )
            self.assertTrue(parsed["backend_gate_render_bridge_active"])
            self.assertEqual(
                parsed["runtime_backend_boundary"]["status"], "pass")
            self.assertEqual(
                parsed["runtime_backend_boundary"]["passed_target_count"], 3)

            summary = perf_summary.build_summary(args)
            self.assertEqual(summary["status"], "pass")
            self.assertTrue(summary["aggregate"]["metric_evidence_present"])
            self.assertEqual(summary["aggregate"]["native_idwt_sum"], 3)
            self.assertEqual(summary["aggregate"]["backend_gate_event_count"], 2)
            self.assertEqual(
                summary["aggregate"]["runtime_backend_probe_event_count"], 3)
            self.assertTrue(
                summary["aggregate"]["runtime_backend_probe_resolved"])
            self.assertEqual(
                summary["aggregate"]["runtime_backend_probe_missing_targets"],
                [],
            )
            self.assertEqual(
                summary["aggregate"]["runtime_backend_boundary"]["status"],
                "pass",
            )
            icc = perf_summary.build_icc_evidence(
                summary,
                tmpdir / "qge_perf_summary.json",
                tmpdir / "qge_perf_icc_evidence.json",
            )
            self.assertEqual(icc["runtime_backend"], "qge_perf_summary")
            self.assertEqual(
                icc["completion_reason"],
                "qge_runtime_performance_complete",
            )
            self.assertTrue(icc["failure_free"])
            self.assertEqual(icc["backend_gate_backends"], ["Metal"])
            self.assertEqual(
                icc["backend_gate_render_bridge_paths"],
                ["native_sparse_dwt_render_bridge"],
            )
            self.assertEqual(icc["runtime_backend_probe_event_count"], 3)
            self.assertTrue(icc["runtime_backend_probe_resolved"])
            self.assertEqual(icc["runtime_backend_boundary_status"], "pass")
            self.assertEqual(
                icc["runtime_backend_boundary_passed_target_count"], 3)


class NoesisSummaryTests(unittest.TestCase):
    def test_phase_clear_without_enemy_contact_is_not_combat_blocked(self) -> None:
        phase_events = [
            {
                "type": "event",
                "kind": "noesis_phase",
                "phase": "e1m1_entry_clear",
                "frame": 1,
                "state": {
                    "route": {
                        "total_distance": 0.0,
                        "max_displacement_from_start": 0.0,
                        "leaf_transition_count": 0,
                    },
                    "combat": {
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_visible_total": 0,
                        "attack_aligned_total": 0,
                    },
                },
            }
        ]
        samples = [
            {
                "type": "sample",
                "frame": 4,
                "route": {
                    "total_distance": 80.0,
                    "max_displacement_from_start": 70.0,
                    "leaf_transition_count": 1,
                },
                "combat": {
                    "visible_enemy_count": 0,
                    "nearest_enemy_distance": 1024.0,
                    "nearest_enemy_visible": False,
                    "damage_dealt_inferred_total": 0,
                    "kills_total": 0,
                    "attack_visible_total": 0,
                    "attack_aligned_total": 0,
                },
                "player": {
                    "attack_active": True,
                },
            }
        ]

        phase = noesis_summary.summarize_phase_progress(phase_events, samples)

        self.assertEqual(phase["progress_blocked_count"], 0)
        self.assertEqual(phase["combat_blocked_count"], 0)
        self.assertEqual(phase["blocked_phases"], [])
        self.assertFalse(phase["intervals"][0]["combat_required"])
        self.assertFalse(phase["intervals"][0]["combat_opportunity"])

    def test_phase_clear_with_distant_hidden_enemy_is_not_combat_blocked(self) -> None:
        phase_events = [
            {
                "type": "event",
                "kind": "noesis_phase",
                "phase": "e1m1_entry_clear",
                "frame": 1,
                "state": {
                    "route": {
                        "total_distance": 0.0,
                        "max_displacement_from_start": 0.0,
                        "leaf_transition_count": 0,
                    },
                    "combat": {
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_visible_total": 0,
                        "attack_aligned_total": 0,
                    },
                },
            }
        ]
        samples = [
            {
                "type": "sample",
                "frame": 4,
                "route": {
                    "total_distance": 80.0,
                    "max_displacement_from_start": 70.0,
                    "leaf_transition_count": 1,
                },
                "combat": {
                    "visible_enemy_count": 0,
                    "nearest_enemy_distance": 700.0,
                    "nearest_enemy_visible": False,
                    "damage_dealt_inferred_total": 0,
                    "kills_total": 0,
                    "attack_visible_total": 0,
                    "attack_aligned_total": 0,
                },
                "player": {
                    "attack_active": False,
                },
            }
        ]

        phase = noesis_summary.summarize_phase_progress(phase_events, samples)
        interval = phase["intervals"][0]

        self.assertEqual(phase["progress_blocked_count"], 0)
        self.assertEqual(phase["combat_blocked_count"], 0)
        self.assertEqual(phase["blocked_phases"], [])
        self.assertEqual(interval["enemy_contact_sample_count"], 1)
        self.assertEqual(interval["close_enemy_contact_sample_count"], 0)
        self.assertFalse(interval["combat_required"])
        self.assertFalse(interval["combat_opportunity"])

    def test_phase_clear_with_enemy_contact_requires_combat(self) -> None:
        phase_events = [
            {
                "type": "event",
                "kind": "noesis_phase",
                "phase": "e1m1_entry_clear",
                "frame": 1,
                "state": {
                    "route": {
                        "total_distance": 0.0,
                        "max_displacement_from_start": 0.0,
                        "leaf_transition_count": 0,
                    },
                    "combat": {
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_visible_total": 0,
                        "attack_aligned_total": 0,
                    },
                },
            }
        ]
        samples = [
            {
                "type": "sample",
                "frame": 4,
                "route": {
                    "total_distance": 80.0,
                    "max_displacement_from_start": 70.0,
                    "leaf_transition_count": 1,
                },
                "combat": {
                    "visible_enemy_count": 0,
                    "nearest_enemy_distance": 256.0,
                    "nearest_enemy_visible": False,
                    "damage_dealt_inferred_total": 0,
                    "kills_total": 0,
                    "attack_visible_total": 0,
                    "attack_aligned_total": 0,
                },
                "player": {
                    "attack_active": False,
                },
            }
        ]

        phase = noesis_summary.summarize_phase_progress(phase_events, samples)

        self.assertEqual(phase["progress_blocked_count"], 1)
        self.assertEqual(phase["combat_blocked_count"], 1)
        self.assertEqual(phase["blocked_phases"], ["e1m1_entry_clear"])
        self.assertTrue(phase["intervals"][0]["combat_required"])
        self.assertTrue(phase["intervals"][0]["combat_opportunity"])
        self.assertEqual(phase["intervals"][0]["close_enemy_contact_sample_count"], 1)

    def test_build_summary_and_icc_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            input_dir = tmpdir / "input"
            log_dir = tmpdir / "logs"
            trace_dir = tmpdir / "trace"
            input_dir.mkdir()
            log_dir.mkdir()
            trace_dir.mkdir()
            actions_path = input_dir / "noesis_actions.txt"
            commands_path = input_dir / "noesis_commands.cfg"
            log_path = log_dir / "quantum_quake.log"
            trace_path = trace_dir / "qge_trace_summary.json"
            gameplay_path = tmpdir / "gameplay_outcomes.ndjson"
            manifest_path = tmpdir / "manifest.json"

            actions_path.write_text(
                "\n".join(
                    [
                        "cmd echo QGE_NOESIS_POLICY map=e1m1 plan=adaptive",
                        "center-view",
                        "cmd echo QGE_NOESIS_PHASE phase=e1m1_entry_clear",
                        "advance-fire 12",
                        "wall-slide-right 10",
                        "speed-jump-forward 3",
                        "door-open 4",
                        "door-bump 4",
                        "circle-fire-left 8",
                        "jump-forward 4",
                        "clear-input 2",
                        "cmd echo QGE_NOESIS_POLICY done",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            commands_path.write_text(
                "\n".join(
                    [
                        "echo QGE_NOESIS_PLAYER start source=cmd start_wait=0",
                        "echo QGE_NOESIS_POLICY map=e1m1 plan=adaptive",
                        "centerview",
                        "echo QGE_NOESIS_PHASE phase=e1m1_entry_clear",
                        "qge_noesis_phase phase=e1m1_entry_clear",
                        "+forward",
                        "+attack",
                        "wait",
                        "-attack",
                        "-forward",
                        "+moveleft",
                        "+right",
                        "+attack",
                        "wait",
                        "-attack",
                        "-right",
                        "-moveleft",
                        "+speed",
                        "+forward",
                        "+moveright",
                        "wait",
                        "-moveright",
                        "-forward",
                        "-speed",
                        "+speed",
                        "+jump",
                        "+forward",
                        "wait",
                        "-forward",
                        "-jump",
                        "-speed",
                        "+speed",
                        "+forward",
                        "wait",
                        "-forward",
                        "-speed",
                        "+jump",
                        "+forward",
                        "wait",
                        "-forward",
                        "-jump",
                        "echo QGE_NOESIS_PLAYER wait_clamped requested=8 max=3",
                        "echo QGE_NOESIS_PLAYER done",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            log_path.write_text(
                "QGE_NOESIS_POLICY map=e1m1 plan=adaptive\n"
                "QGE_NOESIS_PHASE phase=e1m1_entry_clear\n",
                encoding="utf-8",
            )
            gameplay_path.write_text(
                "\n".join(
                    [
                        json.dumps({
                            "schema": "qge.gameplay_outcome.v0",
                            "type": "sample",
                            "frame": 1,
                            "player": {
                                "health": 100,
                                "armor": 0,
                                "origin": [0, 0, 0],
                            },
                            "route": {
                                "total_distance": 0.0,
                                "displacement_from_start": 0.0,
                                "max_displacement_from_start": 0.0,
                                "leaf_transition_count": 0,
                            },
                            "combat": {
                                "damage_taken_total": 0,
                                "damage_dealt_inferred_total": 0,
                                "kills_total": 0,
                                "attack_presses_total": 0,
                                "visible_enemy_count": 0,
                                "nearest_enemy_distance": 320.0,
                                "nearest_enemy_visible": False,
                                "nearest_enemy_angle_error_deg": 38.0,
                                "nearest_enemy_aligned": False,
                                "aligned_visible_enemy_count": 0,
                                "attack_visible_total": 0,
                                "attack_aligned_total": 0,
                            },
                            "pickup": {
                                "pickups_total": 0,
                                "weapon_changes_total": 0,
                            },
                            "assist": {
                                "mode": 0,
                                "active": False,
                                "target_visible": False,
                                "target_distance": -1.0,
                                "forwardmove": 0.0,
                                "sidemove": 0.0,
                            },
                        }),
                        json.dumps({
                            "schema": "qge.gameplay_outcome.v0",
                            "type": "sample",
                            "frame": 6,
                            "player": {
                                "health": 94,
                                "armor": 0,
                                "attack_active": True,
                                "origin": [128, 12, 0],
                            },
                            "route": {
                                "total_distance": 148.0,
                                "displacement_from_start": 128.6,
                                "max_displacement_from_start": 128.6,
                                "leaf_transition_count": 2,
                            },
                            "combat": {
                                "damage_taken_total": 6,
                                "damage_dealt_inferred_total": 18,
                                "kills_total": 0,
                                "attack_presses_total": 1,
                                "visible_enemy_count": 1,
                                "nearest_enemy_distance": 280.0,
                                "nearest_enemy_visible": True,
                                "nearest_enemy_angle_error_deg": 4.5,
                                "nearest_enemy_aligned": True,
                                "aligned_visible_enemy_count": 1,
                                "attack_visible_delta": 1,
                                "attack_visible_total": 1,
                                "attack_aligned_delta": 1,
                                "attack_aligned_total": 1,
                            },
                            "pickup": {
                                "pickups_total": 1,
                                "weapon_changes_total": 1,
                            },
                            "assist": {
                                "mode": 2,
                                "active": True,
                                "target_visible": True,
                                "target_distance": 280.0,
                                "forwardmove": 400.0,
                                "sidemove": 220.0,
                                "pre_assist_aim_error_deg": 4.5,
                                "view_injected": True,
                                "movement_injected": True,
                                "attack_injected": True,
                                "attack_suppressed": False,
                                "fire_gate_passed": True,
                                "target_locked": True,
                                "target_switched": False,
                                "target_switches_total": 1,
                                "locked_frames_total": 7,
                                "switch_fire_suppressed": True,
                                "hidden_chase_timeout": True,
                                "hidden_chase_timeouts_total": 1,
                                "hidden_wall_timeout": True,
                                "hidden_wall_timeouts_total": 1,
                            },
                        }),
                        json.dumps({
                            "schema": "qge.gameplay_outcome.v0",
                            "type": "event",
                            "kind": "noesis_phase",
                            "phase": "e1m1_entry_clear",
                            "phase_sequence": 1,
                            "frame": 1,
                            "state": {
                                "player": {
                                    "health": 100,
                                    "armor": 0,
                                    "origin": [0, 0, 0],
                                },
                                "route": {
                                    "total_distance": 0.0,
                                    "displacement_from_start": 0.0,
                                    "max_displacement_from_start": 0.0,
                                    "leaf_transition_count": 0,
                                },
                                "combat": {
                                    "damage_taken_total": 0,
                                    "damage_dealt_inferred_total": 0,
                                    "kills_total": 0,
                                    "attack_presses_total": 0,
                                    "visible_enemy_count": 0,
                                    "nearest_enemy_distance": 320.0,
                                    "nearest_enemy_visible": False,
                                    "nearest_enemy_angle_error_deg": 38.0,
                                    "nearest_enemy_aligned": False,
                                    "aligned_visible_enemy_count": 0,
                                    "attack_visible_total": 0,
                                    "attack_aligned_total": 0,
                                },
                                "pickup": {
                                    "pickups_total": 0,
                                    "weapon_changes_total": 0,
                                },
                            },
                        }),
                        json.dumps({
                            "schema": "qge.gameplay_outcome.v0",
                            "type": "event",
                            "kind": "damage_dealt_inferred",
                            "frame": 6,
                            "amount": 18,
                            "total": 18,
                        }),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            trace_path.write_text(
                json.dumps({
                    "header": {
                        "run_id": 0x5151455F52554E31,
                        "moonlab_abi_hash": 0x2,
                        "qge_build_hash": 0x3,
                        "quake_content_hash": 0x4,
                    },
                    "replay_health": {
                        "entropy_replay_events": 1,
                        "replay_metadata_mismatches": 0,
                        "replay_exhaustions": 0,
                        "ai_decision_replay_metadata_mismatches": 0,
                        "ai_decision_replay_exhaustions": 0,
                    },
                    "runtime_evidence": {
                        "single_trace_ready": False,
                        "ai": {"decision_count": 7},
                        "render": {
                            "sparse_dwt_count": 5,
                            "native_bridge_count": 5,
                            "native_fallback_count": 0,
                        },
                        "visibility": {"authority_apply_count": 3},
                        "projectile": {
                            "branch_state_count": 2,
                            "save_demo_boundary_count": 3,
                            "save_demo_writeback_count": 1,
                            "save_demo_branch_count": 1,
                            "save_demo_collision_oracle_count": 1,
                            "save_demo_trace_id_xor": 0xAA55,
                            "flags_or": 0x70000000,
                            "off_reason": "none",
                            "branch_selected_probability_max": 0.875,
                            "preimpact_selected_probability_max": 0.75,
                        },
                    },
                }),
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps({
                    "status": "complete",
                    "map": "e1m1",
                    "frames_requested": 0,
                    "frames_captured": 0,
                    "run": {
                        "status": "ok",
                        "success": 1,
                        "timed_out": 0,
                        "startup_issue": "",
                    },
                    "input": {
                        "player": "noesis",
                        "noesis_plan": "adaptive",
                        "noesis_assist": 2,
                    },
                    "noesis": {
                        "gameplay_outcomes_file": str(gameplay_path),
                    },
                }),
                encoding="utf-8",
            )

            args = SimpleNamespace(
                manifest=manifest_path,
                actions=actions_path,
                commands=commands_path,
                log=log_path,
                gameplay_outcomes=gameplay_path,
                trace_summary=trace_path,
                frames_dir=None,
                plan="",
                player="",
                min_actions=1,
                min_commands=1,
                min_frames=0,
                min_frame_mae=None,
                min_log_phases=1,
                min_phase_outcomes=1,
                min_gameplay_samples=2,
                min_route_distance=64.0,
                require_phase_markers=True,
                require_combat=True,
            )
            summary = noesis_summary.build_summary(args)
            self.assertEqual(summary["schema"], "qge.noesis_summary.v0")
            self.assertEqual(summary["status"], "pass")
            self.assertEqual(summary["map"], "e1m1")
            self.assertEqual(summary["plan"], "adaptive")
            self.assertEqual(summary["actions"]["verb_counts"]["advance-fire"], 1)
            self.assertEqual(summary["actions"]["verb_counts"]["wall-slide-right"], 1)
            self.assertEqual(summary["actions"]["verb_counts"]["door-open"], 1)
            self.assertEqual(summary["actions"]["verb_counts"]["door-bump"], 1)
            self.assertEqual(summary["actions"]["combat_action_count"], 2)
            self.assertEqual(summary["actions"]["route_action_count"], 5)
            self.assertTrue(summary["quality_gates"]["movement_actions_present"])
            self.assertTrue(summary["quality_gates"]["combat_required"])
            self.assertEqual(summary["commands"]["pressed_button_variety"], 7)
            self.assertTrue(summary["commands"]["player_start_present"])
            self.assertTrue(summary["commands"]["player_done_present"])
            self.assertEqual(summary["commands"]["wait_clamped_count"], 1)
            self.assertEqual(summary["log"]["phase_count"], 1)
            self.assertEqual(summary["gameplay"]["sample_count"], 2)
            self.assertEqual(
                summary["gameplay"]["phase"]["outcome_event_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["phase"]["progress_pass_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["route"]["total_distance"],
                148.0,
            )
            self.assertFalse(summary["gameplay"]["route"]["terminal_stall"])
            self.assertEqual(
                summary["gameplay"]["route"]["movement_efficiency"],
                0.8689,
            )
            self.assertTrue(summary["gameplay"]["player"]["survived"])
            self.assertEqual(summary["inputs"]["noesis_assist_requested"], 2)
            self.assertEqual(summary["inputs"]["claim_scope"], "server_assisted")
            self.assertFalse(
                summary["claim_gates"]["unassisted_claim_supported"]
            )
            self.assertEqual(summary["gameplay"]["assist"]["mode_max"], 2.0)
            self.assertEqual(summary["gameplay"]["assist"]["active_frames"], 1)
            self.assertEqual(
                summary["gameplay"]["assist"]["active_fraction"],
                0.5,
            )
            self.assertEqual(
                summary["gameplay"]["assist"]["visible_target_frames"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"]["attack_visible_frames"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"][
                    "view_injected_sample_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"][
                    "movement_injected_sample_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"][
                    "attack_injected_sample_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"][
                    "attack_suppressed_sample_count"],
                0,
            )
            self.assertEqual(
                summary["gameplay"]["assist"][
                    "fire_gate_passed_sample_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"][
                    "target_locked_sample_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"]["target_locked_fraction"],
                0.5,
            )
            self.assertEqual(
                summary["gameplay"]["assist"]["target_switch_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"]["locked_frames_total"],
                7,
            )
            self.assertEqual(
                summary["gameplay"]["assist"][
                    "switch_fire_suppressed_sample_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"][
                    "hidden_chase_timeout_sample_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"]["hidden_chase_timeout_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"][
                    "hidden_wall_timeout_sample_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"]["hidden_wall_timeout_count"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["assist"]["pre_assist_aim_error_min"],
                4.5,
            )
            self.assertEqual(
                summary["gameplay"]["assist"]["pre_assist_aim_error_avg"],
                4.5,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["attack_visible_frames"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["attack_active_frames"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["blind_attack_frames"],
                0,
            )
            self.assertEqual(
                summary["gameplay"]["combat"][
                    "visible_unaligned_attack_frames"],
                0.0,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["unproductive_attack_frames"],
                0.0,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["attack_visibility_fraction"],
                1.0,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["blind_attack_fraction"],
                0.0,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["unproductive_attack_fraction"],
                0.0,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["attack_aligned_frames"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["attack_alignment_fraction"],
                1.0,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["nearest_enemy_angle_error_min"],
                4.5,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["damage_per_attack_press"],
                18.0,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["net_damage_per_attack_press"],
                12.0,
            )
            self.assertTrue(summary["quality_gates"]["route_progress_required"])
            self.assertTrue(
                summary["quality_gates"]["combat_effectiveness_required"]
            )
            self.assertEqual(summary["trace"]["ai_decision_count"], 7)
            self.assertEqual(
                summary["trace"]["projectile_save_demo_boundary_count"],
                3,
            )
            self.assertEqual(
                summary["trace"]["projectile_save_demo_trace_id_xor"],
                0xAA55,
            )
            self.assertGreaterEqual(summary["gameplay_score"]["score"], 35.0)
            self.assertEqual(summary["gameplay_score"]["executed_phase_count"], 1)
            self.assertEqual(
                summary["gameplay_score"]["outcome_telemetry_present"],
                True,
            )

            icc = noesis_summary.build_icc_evidence(
                summary,
                tmpdir / "qge_noesis_summary.json",
            )
            by_name = {entry["name"]: entry["value"] for entry in icc}
            self.assertEqual(by_name["runtime_backend"], "qge_noesis_summary")
            self.assertEqual(
                by_name["completion_reason"],
                "qge_noesis_summary_complete",
            )
            self.assertTrue(by_name["noesis_failure_free"])
            self.assertEqual(by_name["noesis_plan"], "adaptive")
            self.assertEqual(by_name["noesis_action_count"], 12)
            self.assertEqual(by_name["noesis_route_action_count"], 5)
            self.assertGreaterEqual(by_name["noesis_gameplay_quality_score"], 35.0)
            self.assertEqual(by_name["noesis_claim_scope"], "server_assisted")
            self.assertFalse(by_name["noesis_scripted"])
            self.assertFalse(by_name["noesis_autonomous"])
            self.assertFalse(by_name["noesis_autonomous_control"])
            self.assertFalse(by_name["noesis_unassisted_claim_supported"])
            self.assertEqual(by_name["noesis_log_phase_count"], 1)
            self.assertEqual(by_name["noesis_trace_run_id"], 0x5151455F52554E31)
            self.assertEqual(by_name["noesis_trace_qge_build_hash"], 0x3)
            self.assertEqual(
                by_name["noesis_projectile_save_demo_boundary_count"],
                3,
            )
            self.assertEqual(
                by_name["noesis_projectile_save_demo_writeback_count"],
                1,
            )
            self.assertEqual(
                by_name["noesis_projectile_save_demo_branch_count"],
                1,
            )
            self.assertEqual(
                by_name["noesis_projectile_save_demo_collision_oracle_count"],
                1,
            )
            self.assertEqual(
                by_name["noesis_projectile_save_demo_trace_id_xor"],
                0xAA55,
            )
            self.assertEqual(by_name["noesis_projectile_off_reason"], "none")
            self.assertEqual(
                by_name["noesis_projectile_branch_selected_probability_max"],
                0.875,
            )
            self.assertEqual(by_name["noesis_gameplay_phase_event_count"], 1)
            self.assertEqual(by_name["noesis_gameplay_phase_state_count"], 1)
            self.assertEqual(
                by_name["noesis_gameplay_phase_progress_pass_count"],
                1,
            )
            self.assertEqual(by_name["noesis_gameplay_outcome_sample_count"], 2)
            self.assertEqual(by_name["noesis_gameplay_total_distance"], 148.0)
            self.assertFalse(by_name["noesis_gameplay_terminal_stall"])
            self.assertEqual(by_name["noesis_gameplay_movement_efficiency"], 0.8689)
            self.assertTrue(by_name["noesis_gameplay_survived"])
            self.assertEqual(
                by_name["noesis_gameplay_attack_visible_frames"],
                1,
            )
            self.assertEqual(
                by_name["noesis_gameplay_attack_active_frames"],
                1,
            )
            self.assertEqual(
                by_name["noesis_gameplay_blind_attack_frames"],
                0,
            )
            self.assertEqual(
                by_name["noesis_gameplay_visible_unaligned_attack_frames"],
                0.0,
            )
            self.assertEqual(
                by_name["noesis_gameplay_unproductive_attack_frames"],
                0.0,
            )
            self.assertEqual(
                by_name["noesis_gameplay_attack_visibility_fraction"],
                1.0,
            )
            self.assertEqual(
                by_name["noesis_gameplay_blind_attack_fraction"],
                0.0,
            )
            self.assertEqual(
                by_name["noesis_gameplay_unproductive_attack_fraction"],
                0.0,
            )
            self.assertEqual(
                by_name["noesis_gameplay_attack_aligned_frames"],
                1,
            )
            self.assertEqual(
                by_name["noesis_gameplay_attack_alignment_fraction"],
                1.0,
            )
            self.assertEqual(
                by_name["noesis_gameplay_nearest_enemy_angle_error_min"],
                4.5,
            )
            self.assertEqual(
                by_name["noesis_gameplay_damage_per_attack_press"],
                18.0,
            )
            self.assertEqual(
                by_name["noesis_gameplay_net_damage_per_attack_press"],
                12.0,
            )
            self.assertEqual(by_name["noesis_assist_requested_mode"], 2)
            self.assertEqual(by_name["noesis_assist_mode_max"], 2.0)
            self.assertEqual(by_name["noesis_assist_active_sample_count"], 1)
            self.assertEqual(by_name["noesis_assist_active_fraction"], 0.5)
            self.assertEqual(
                by_name["noesis_assist_target_visible_sample_count"],
                1,
            )
            self.assertEqual(by_name["noesis_assist_steering_sample_count"], 1)
            self.assertEqual(by_name["noesis_assist_attack_visible_frames"], 1)
            self.assertEqual(
                by_name["noesis_assist_view_injected_sample_count"],
                1,
            )
            self.assertEqual(
                by_name["noesis_assist_movement_injected_sample_count"],
                1,
            )
            self.assertEqual(
                by_name["noesis_assist_attack_injected_sample_count"],
                1,
            )
            self.assertEqual(
                by_name["noesis_assist_attack_suppressed_sample_count"],
                0,
            )
            self.assertEqual(
                by_name["noesis_assist_fire_gate_passed_sample_count"],
                1,
            )
            self.assertEqual(
                by_name["noesis_assist_target_locked_sample_count"],
                1,
            )
            self.assertEqual(
                by_name["noesis_assist_target_locked_fraction"],
                0.5,
            )
            self.assertEqual(
                by_name["noesis_assist_target_switch_count"],
                1,
            )
            self.assertEqual(
                by_name["noesis_assist_locked_frames_total"],
                7,
            )
            self.assertEqual(
                by_name[
                    "noesis_assist_switch_fire_suppressed_sample_count"],
                1,
            )
            self.assertEqual(
                by_name[
                    "noesis_assist_hidden_chase_timeout_sample_count"],
                1,
            )
            self.assertEqual(
                by_name["noesis_assist_hidden_chase_timeout_count"],
                1,
            )
            self.assertEqual(
                by_name[
                    "noesis_assist_hidden_wall_timeout_sample_count"],
                1,
            )
            self.assertEqual(
                by_name["noesis_assist_hidden_wall_timeout_count"],
                1,
            )
            self.assertEqual(
                by_name["noesis_assist_pre_assist_aim_error_min"],
                4.5,
            )
            self.assertEqual(
                by_name["noesis_assist_pre_assist_aim_error_avg"],
                4.5,
            )

            no_phase_path = tmpdir / "gameplay_without_phase.ndjson"
            no_phase_path.write_text(
                "\n".join(
                    line for line in gameplay_path.read_text(
                        encoding="utf-8").splitlines()
                    if '"kind": "noesis_phase"' not in line
                ) + "\n",
                encoding="utf-8",
            )
            phase_block_args = SimpleNamespace(
                **{**args.__dict__, "gameplay_outcomes": no_phase_path}
            )
            phase_blocked = noesis_summary.build_summary(phase_block_args)
            self.assertEqual(phase_blocked["status"], "blocked")
            self.assertIn(
                "phase_outcome_events_required",
                phase_blocked["failures"],
            )

            commands_path.unlink()
            blocked = noesis_summary.build_summary(args)
            self.assertEqual(blocked["status"], "blocked")
            self.assertIn(str(commands_path), blocked["inputs"]["missing_inputs"])
            self.assertIn("commands_present", blocked["failures"])

    def test_autonomous_assist_counts_as_no_script_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            actions_path = tmpdir / "actions.txt"
            commands_path = tmpdir / "commands.cfg"
            log_path = tmpdir / "quantum_quake.log"
            gameplay_path = tmpdir / "gameplay_outcomes.ndjson"
            manifest_path = tmpdir / "manifest.json"

            actions_path.write_text("", encoding="utf-8")
            commands_path.write_text(
                "\n".join([
                    "echo QGE_NOESIS_PLAYER start source=autonomous "
                    "scripts=disabled provider=engine_assist start_wait=0",
                    "echo QGE_NOESIS_PLAYER autonomous "
                    "scripts=disabled control=engine_assist",
                    "echo QGE_NOESIS_PLAYER done",
                ]) + "\n",
                encoding="utf-8",
            )
            log_path.write_text("", encoding="utf-8")
            gameplay_path.write_text(
                "\n".join([
                    json.dumps({
                        "schema": "qge.gameplay_outcome.v0",
                        "type": "sample",
                        "frame": 1,
                        "player": {"health": 100, "origin": [0, 0, 0]},
                        "route": {
                            "total_distance": 0.0,
                            "displacement_from_start": 0.0,
                            "max_displacement_from_start": 0.0,
                        },
                        "combat": {
                            "damage_dealt_inferred_total": 0,
                            "kills_total": 0,
                            "attack_presses_total": 0,
                            "visible_enemy_count": 0,
                            "attack_aligned_total": 0,
                        },
                        "assist": {
                            "mode": 2,
                            "active": False,
                            "movement_injected": False,
                            "attack_injected": False,
                            "fire_gate_passed": False,
                        },
                    }),
                    json.dumps({
                        "schema": "qge.gameplay_outcome.v0",
                        "type": "sample",
                        "frame": 8,
                        "player": {
                            "health": 100,
                            "attack_active": True,
                            "origin": [90, 0, 0],
                        },
                        "route": {
                            "total_distance": 96.0,
                            "displacement_from_start": 90.0,
                            "max_displacement_from_start": 90.0,
                            "leaf_transition_count": 1,
                        },
                        "combat": {
                            "damage_dealt_inferred_total": 12,
                            "kills_total": 0,
                            "attack_presses_total": 1,
                            "visible_enemy_count": 1,
                            "nearest_enemy_visible": True,
                            "nearest_enemy_aligned": True,
                            "attack_visible_total": 1,
                            "attack_aligned_total": 1,
                        },
                        "assist": {
                            "mode": 2,
                            "active": True,
                            "movement_injected": True,
                            "attack_injected": True,
                            "fire_gate_passed": True,
                        },
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps({
                    "status": "complete",
                    "map": "e1m1",
                    "frames_requested": 0,
                    "frames_captured": 0,
                    "run": {
                        "status": "ok",
                        "success": 1,
                        "timed_out": 0,
                        "startup_issue": "",
                    },
                    "input": {
                        "player": "noesis",
                        "noesis_plan": "adaptive",
                        "noesis_assist": 2,
                        "noesis_scripted": 0,
                        "noesis_autonomous": 1,
                    },
                    "noesis": {
                        "gameplay_outcomes_file": str(gameplay_path),
                    },
                }),
                encoding="utf-8",
            )

            args = SimpleNamespace(
                manifest=manifest_path,
                actions=actions_path,
                commands=commands_path,
                log=log_path,
                gameplay_outcomes=gameplay_path,
                trace_summary=None,
                frames_dir=None,
                plan="",
                player="",
                min_actions=0,
                min_commands=1,
                min_frames=0,
                min_frame_mae=None,
                min_log_phases=0,
                min_phase_outcomes=0,
                min_gameplay_samples=2,
                min_route_distance=64.0,
                require_phase_markers=False,
                require_combat=True,
            )
            summary = noesis_summary.build_summary(args)
            self.assertEqual(summary["status"], "pass")
            self.assertEqual(summary["inputs"]["claim_scope"], "server_autonomous")
            self.assertTrue(summary["inputs"]["autonomous_control"])
            self.assertEqual(summary["actions"]["line_count"], 0)
            self.assertTrue(summary["quality_gates"]["actions_present"])
            self.assertTrue(
                summary["quality_gates"]["no_script_action_trace_empty"]
            )
            self.assertTrue(summary["quality_gates"]["movement_actions_present"])
            self.assertTrue(summary["quality_gates"]["combat_actions_present"])
            self.assertTrue(summary["quality_gates"]["combat_required"])
            self.assertTrue(summary["quality_gates"]["not_stuck"])

            icc = noesis_summary.build_icc_evidence(
                summary,
                tmpdir / "qge_noesis_summary.json",
            )
            by_name = {entry["name"]: entry["value"] for entry in icc}
            self.assertEqual(by_name["noesis_claim_scope"], "server_autonomous")
            self.assertFalse(by_name["noesis_scripted"])
            self.assertTrue(by_name["noesis_autonomous"])
            self.assertTrue(by_name["noesis_autonomous_control"])

    def test_poor_aim_blocks_required_combat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            actions_path = tmpdir / "actions.txt"
            commands_path = tmpdir / "commands.cfg"
            log_path = tmpdir / "quantum_quake.log"
            gameplay_path = tmpdir / "gameplay_outcomes.ndjson"
            manifest_path = tmpdir / "manifest.json"

            actions_path.write_text(
                "\n".join([
                    "cmd echo QGE_NOESIS_POLICY map=e1m1 plan=combat",
                    "advance-fire 8",
                    "cmd echo QGE_NOESIS_POLICY done",
                ]) + "\n",
                encoding="utf-8",
            )
            commands_path.write_text(
                "\n".join([
                    "echo QGE_NOESIS_PLAYER start source=cmd start_wait=0",
                    "+forward",
                    "+attack",
                    "wait",
                    "-attack",
                    "-forward",
                    "echo QGE_NOESIS_PLAYER done",
                ]) + "\n",
                encoding="utf-8",
            )
            log_path.write_text(
                "QGE_NOESIS_POLICY map=e1m1 plan=combat\n"
                "QGE_NOESIS_POLICY done\n",
                encoding="utf-8",
            )
            gameplay_path.write_text(
                "\n".join([
                    json.dumps({
                        "schema": "qge.gameplay_outcome.v0",
                        "type": "sample",
                        "frame": 1,
                        "player": {
                            "health": 100,
                            "armor": 0,
                            "weapon": 2,
                            "origin": [0, 0, 0],
                        },
                        "route": {
                            "total_distance": 0.0,
                            "displacement_from_start": 0.0,
                            "max_displacement_from_start": 0.0,
                            "leaf_transition_count": 0,
                        },
                        "combat": {
                            "damage_taken_total": 0,
                            "damage_dealt_inferred_total": 0,
                            "kills_total": 0,
                            "attack_presses_total": 0,
                            "visible_enemy_count": 1,
                            "nearest_enemy_distance": 240.0,
                            "nearest_enemy_visible": True,
                            "nearest_enemy_angle_error_deg": 42.0,
                            "nearest_enemy_aligned": False,
                            "aligned_visible_enemy_count": 0,
                            "attack_visible_total": 0,
                            "attack_aligned_total": 0,
                        },
                        "pickup": {
                            "pickups_total": 0,
                            "weapon_changes_total": 0,
                        },
                    }),
                    json.dumps({
                        "schema": "qge.gameplay_outcome.v0",
                        "type": "sample",
                        "frame": 2,
                        "player": {
                            "health": 100,
                            "armor": 0,
                            "weapon": 2,
                            "attack_active": True,
                            "origin": [72, 0, 0],
                        },
                        "route": {
                            "frame_distance": 72.0,
                            "total_distance": 72.0,
                            "displacement_from_start": 72.0,
                            "max_displacement_from_start": 72.0,
                            "leaf_transition_count": 1,
                        },
                        "combat": {
                            "damage_taken_total": 0,
                            "damage_dealt_inferred_total": 0,
                            "kills_total": 0,
                            "attack_presses_total": 1,
                            "visible_enemy_count": 1,
                            "nearest_enemy_distance": 220.0,
                            "nearest_enemy_visible": True,
                            "nearest_enemy_angle_error_deg": 38.0,
                            "nearest_enemy_aligned": False,
                            "aligned_visible_enemy_count": 0,
                            "attack_visible_delta": 1,
                            "attack_visible_total": 1,
                            "attack_aligned_delta": 0,
                            "attack_aligned_total": 0,
                        },
                        "pickup": {
                            "pickups_total": 0,
                            "weapon_changes_total": 0,
                        },
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps({
                    "map": "e1m1",
                    "run": {
                        "status": "ok",
                        "success": 1,
                        "timed_out": 0,
                        "startup_issue": "",
                    },
                    "input": {
                        "player": "noesis",
                        "noesis_plan": "combat",
                    },
                    "noesis": {
                        "gameplay_outcomes_file": str(gameplay_path),
                    },
                }),
                encoding="utf-8",
            )

            args = SimpleNamespace(
                manifest=manifest_path,
                actions=actions_path,
                commands=commands_path,
                log=log_path,
                gameplay_outcomes=gameplay_path,
                trace_summary=None,
                frames_dir=None,
                plan="",
                player="",
                min_actions=1,
                min_commands=1,
                min_frames=0,
                min_frame_mae=None,
                min_log_phases=0,
                min_phase_outcomes=0,
                min_gameplay_samples=2,
                min_route_distance=64.0,
                require_phase_markers=False,
                require_combat=True,
            )
            summary = noesis_summary.build_summary(args)
            self.assertEqual(summary["status"], "blocked")
            self.assertEqual(
                summary["gameplay"]["combat"]["attack_visible_frames"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["blind_attack_frames"],
                0,
            )
            self.assertEqual(
                summary["gameplay"]["combat"][
                    "visible_unaligned_attack_frames"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["unproductive_attack_frames"],
                1,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["unproductive_attack_fraction"],
                1.0,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["attack_aligned_frames"],
                0,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["nearest_enemy_angle_error_min"],
                38.0,
            )
            self.assertEqual(
                summary["gameplay"]["combat"]["net_damage_per_attack_press"],
                0.0,
            )
            self.assertFalse(
                summary["quality_gates"]["combat_effectiveness_required"]
            )
            self.assertIn(
                "combat_effectiveness_required",
                summary["failures"],
            )

    def test_net_damage_per_attack_press_tracks_bad_trades(self) -> None:
        def write_gameplay(path: Path, attack_presses: int) -> None:
            samples = [
                {
                    "schema": "qge.gameplay_outcome.v0",
                    "type": "sample",
                    "frame": 1,
                    "player": {
                        "health": 100,
                        "armor": 0,
                        "weapon": 2,
                        "origin": [0, 0, 0],
                    },
                    "route": {
                        "total_distance": 0.0,
                        "displacement_from_start": 0.0,
                        "max_displacement_from_start": 0.0,
                        "leaf_transition_count": 0,
                    },
                    "combat": {
                        "damage_taken_total": 0,
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_presses_total": 0,
                        "visible_enemy_count": 1,
                        "nearest_enemy_distance": 220.0,
                        "nearest_enemy_visible": True,
                    },
                    "pickup": {
                        "pickups_total": 0,
                        "weapon_changes_total": 0,
                    },
                },
                {
                    "schema": "qge.gameplay_outcome.v0",
                    "type": "sample",
                    "frame": 2,
                    "player": {
                        "health": 80,
                        "armor": 0,
                        "weapon": 2,
                        "origin": [16, 0, 0],
                    },
                    "route": {
                        "frame_distance": 16.0,
                        "total_distance": 16.0,
                        "displacement_from_start": 16.0,
                        "max_displacement_from_start": 16.0,
                        "leaf_transition_count": 0,
                    },
                    "combat": {
                        "damage_taken_total": 20,
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_presses_total": attack_presses,
                        "visible_enemy_count": 1,
                        "nearest_enemy_distance": 210.0,
                        "nearest_enemy_visible": True,
                    },
                    "pickup": {
                        "pickups_total": 0,
                        "weapon_changes_total": 0,
                    },
                },
            ]
            path.write_text(
                "\n".join(json.dumps(sample) for sample in samples) + "\n",
                encoding="utf-8",
            )

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            punished_path = tmpdir / "punished.ndjson"
            passive_path = tmpdir / "passive.ndjson"
            write_gameplay(punished_path, 1)
            write_gameplay(passive_path, 0)

            punished = noesis_summary.summarize_gameplay(punished_path)
            self.assertEqual(
                punished["combat"]["net_damage_per_attack_press"],
                -20.0,
            )
            self.assertEqual(
                punished["combat"]["damage_per_attack_press"],
                0.0,
            )

            passive = noesis_summary.summarize_gameplay(passive_path)
            self.assertEqual(
                passive["combat"]["net_damage_per_attack_press"],
                0.0,
            )

    def test_ammo_efficiency_tracks_spend_gain_and_waste(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gameplay_path = Path(tmp) / "gameplay_outcomes.ndjson"
            samples = [
                {
                    "schema": "qge.gameplay_outcome.v0",
                    "type": "sample",
                    "frame": 1,
                    "player": {
                        "health": 100,
                        "armor": 0,
                        "weapon": 2,
                        "shells": 25,
                        "nails": 0,
                        "rockets": 0,
                        "cells": 0,
                        "origin": [0, 0, 0],
                    },
                    "route": {
                        "total_distance": 0.0,
                        "displacement_from_start": 0.0,
                        "max_displacement_from_start": 0.0,
                        "leaf_transition_count": 0,
                    },
                    "combat": {
                        "damage_taken_total": 0,
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_presses_total": 0,
                        "visible_enemy_count": 0,
                        "nearest_enemy_distance": -1,
                        "nearest_enemy_visible": False,
                        "nearest_enemy_aligned": False,
                    },
                    "pickup": {
                        "pickups_total": 0,
                        "weapon_changes_total": 0,
                    },
                },
                {
                    "schema": "qge.gameplay_outcome.v0",
                    "type": "sample",
                    "frame": 2,
                    "player": {
                        "health": 100,
                        "armor": 0,
                        "weapon": 2,
                        "shells": 24,
                        "nails": 0,
                        "rockets": 0,
                        "cells": 0,
                        "attack_active": True,
                        "origin": [0, 0, 0],
                    },
                    "route": {
                        "frame_distance": 0.0,
                        "total_distance": 0.0,
                        "displacement_from_start": 0.0,
                        "max_displacement_from_start": 0.0,
                        "leaf_transition_count": 0,
                    },
                    "combat": {
                        "damage_taken_total": 0,
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_presses_total": 1,
                        "visible_enemy_count": 0,
                        "nearest_enemy_distance": -1,
                        "nearest_enemy_visible": False,
                        "nearest_enemy_aligned": False,
                        "attack_aligned_delta": 0,
                    },
                    "pickup": {
                        "pickups_total": 0,
                        "weapon_changes_total": 0,
                    },
                },
                {
                    "schema": "qge.gameplay_outcome.v0",
                    "type": "sample",
                    "frame": 3,
                    "player": {
                        "health": 100,
                        "armor": 0,
                        "weapon": 2,
                        "shells": 26,
                        "nails": 0,
                        "rockets": 0,
                        "cells": 0,
                        "origin": [8, 0, 0],
                    },
                    "route": {
                        "frame_distance": 8.0,
                        "total_distance": 8.0,
                        "displacement_from_start": 8.0,
                        "max_displacement_from_start": 8.0,
                        "leaf_transition_count": 0,
                    },
                    "combat": {
                        "damage_taken_total": 0,
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_presses_total": 1,
                        "visible_enemy_count": 0,
                        "nearest_enemy_distance": -1,
                        "nearest_enemy_visible": False,
                        "nearest_enemy_aligned": False,
                    },
                    "pickup": {
                        "pickups_total": 1,
                        "weapon_changes_total": 0,
                    },
                },
                {
                    "schema": "qge.gameplay_outcome.v0",
                    "type": "sample",
                    "frame": 4,
                    "player": {
                        "health": 100,
                        "armor": 0,
                        "weapon": 2,
                        "shells": 25,
                        "nails": 0,
                        "rockets": 0,
                        "cells": 0,
                        "attack_active": True,
                        "origin": [16, 0, 0],
                    },
                    "route": {
                        "frame_distance": 8.0,
                        "total_distance": 16.0,
                        "displacement_from_start": 16.0,
                        "max_displacement_from_start": 16.0,
                        "leaf_transition_count": 0,
                    },
                    "combat": {
                        "damage_taken_total": 0,
                        "damage_dealt_inferred_delta": 18,
                        "damage_dealt_inferred_total": 18,
                        "kills_total": 0,
                        "attack_presses_total": 2,
                        "visible_enemy_count": 1,
                        "nearest_enemy_distance": 180,
                        "nearest_enemy_visible": True,
                        "nearest_enemy_aligned": True,
                        "aligned_visible_enemy_count": 1,
                        "attack_aligned_delta": 1,
                    },
                    "pickup": {
                        "pickups_total": 1,
                        "weapon_changes_total": 0,
                    },
                },
            ]
            gameplay_path.write_text(
                "\n".join(json.dumps(sample) for sample in samples) + "\n",
                encoding="utf-8",
            )

            summary = noesis_summary.summarize_gameplay(gameplay_path)
            self.assertEqual(summary["combat"]["ammo_start_total"], 25.0)
            self.assertEqual(summary["combat"]["ammo_end_total"], 25.0)
            self.assertEqual(summary["combat"]["ammo_min_total"], 24.0)
            self.assertEqual(summary["combat"]["ammo_max_total"], 26.0)
            self.assertEqual(summary["combat"]["ammo_spent"], 2.0)
            self.assertEqual(summary["combat"]["ammo_gained"], 2.0)
            self.assertEqual(
                summary["combat"]["unproductive_ammo_spent"],
                1.0,
            )
            self.assertEqual(summary["combat"]["ammo_waste_fraction"], 0.5)
            self.assertEqual(
                summary["combat"]["damage_per_ammo_spent"],
                9.0,
            )
            self.assertEqual(
                summary["combat"]["net_damage_per_ammo_spent"],
                9.0,
            )

    def test_blind_attack_frames_track_invisible_fire(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gameplay_path = Path(tmp) / "gameplay_outcomes.ndjson"
            samples = [
                {
                    "schema": "qge.gameplay_outcome.v0",
                    "type": "sample",
                    "frame": 1,
                    "player": {
                        "health": 100,
                        "armor": 0,
                        "weapon": 2,
                        "origin": [0, 0, 0],
                    },
                    "route": {
                        "total_distance": 0.0,
                        "displacement_from_start": 0.0,
                        "max_displacement_from_start": 0.0,
                        "leaf_transition_count": 0,
                    },
                    "combat": {
                        "damage_taken_total": 0,
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_presses_total": 0,
                        "visible_enemy_count": 0,
                        "nearest_enemy_distance": 512.0,
                        "nearest_enemy_visible": False,
                    },
                    "pickup": {
                        "pickups_total": 0,
                        "weapon_changes_total": 0,
                    },
                },
                {
                    "schema": "qge.gameplay_outcome.v0",
                    "type": "sample",
                    "frame": 2,
                    "player": {
                        "health": 100,
                        "armor": 0,
                        "weapon": 2,
                        "attack_active": True,
                        "origin": [32, 0, 0],
                    },
                    "route": {
                        "frame_distance": 32.0,
                        "total_distance": 32.0,
                        "displacement_from_start": 32.0,
                        "max_displacement_from_start": 32.0,
                        "leaf_transition_count": 0,
                    },
                    "combat": {
                        "damage_taken_total": 0,
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_presses_total": 1,
                        "visible_enemy_count": 0,
                        "nearest_enemy_distance": 500.0,
                        "nearest_enemy_visible": False,
                        "attack_visible_total": 0,
                        "attack_aligned_total": 0,
                    },
                    "pickup": {
                        "pickups_total": 0,
                        "weapon_changes_total": 0,
                    },
                },
            ]
            gameplay_path.write_text(
                "\n".join(json.dumps(sample) for sample in samples) + "\n",
                encoding="utf-8",
            )

            summary = noesis_summary.summarize_gameplay(gameplay_path)
            self.assertEqual(summary["combat"]["attack_active_frames"], 1)
            self.assertEqual(summary["combat"]["attack_visible_frames"], 0)
            self.assertEqual(summary["combat"]["blind_attack_frames"], 1)
            self.assertEqual(
                summary["combat"]["visible_unaligned_attack_frames"],
                0.0,
            )
            self.assertEqual(
                summary["combat"]["unproductive_attack_frames"],
                1.0,
            )
            self.assertEqual(
                summary["combat"]["attack_visibility_fraction"],
                0.0,
            )
            self.assertEqual(summary["combat"]["blind_attack_fraction"], 1.0)
            self.assertEqual(
                summary["combat"]["unproductive_attack_fraction"],
                1.0,
            )

    def test_route_recovery_after_stationary_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gameplay_path = Path(tmp) / "gameplay_outcomes.ndjson"
            origins = [0, 64, 64, 64, 64, 64, 64, 64, 112, 128]
            totals = [0, 64, 64, 64, 64, 64, 64, 64, 112, 128]
            samples = []
            for index, (origin_x, total) in enumerate(zip(origins, totals)):
                prev_total = totals[index - 1] if index > 0 else total
                frame_distance = max(0, total - prev_total)
                samples.append({
                    "schema": "qge.gameplay_outcome.v0",
                    "type": "sample",
                    "frame": index + 1,
                    "player": {
                        "health": 100,
                        "armor": 0,
                        "weapon": 2,
                        "origin": [origin_x, 0, 0],
                    },
                    "route": {
                        "frame_distance": frame_distance,
                        "total_distance": total,
                        "displacement_from_start": origin_x,
                        "max_displacement_from_start": max(origins[:index + 1]),
                        "leaf_transition_count": 1 if index >= 8 else 0,
                    },
                    "combat": {
                        "damage_taken_total": 0,
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_presses_total": 0,
                        "visible_enemy_count": 0,
                        "nearest_enemy_distance": -1,
                        "nearest_enemy_visible": False,
                    },
                    "pickup": {
                        "pickups_total": 0,
                        "weapon_changes_total": 0,
                    },
                })
            gameplay_path.write_text(
                "\n".join(json.dumps(sample) for sample in samples) + "\n",
                encoding="utf-8",
            )

            summary = noesis_summary.summarize_gameplay(gameplay_path)
            self.assertFalse(summary["route"]["terminal_stall"])
            self.assertTrue(summary["route"]["recovered_after_stall"])
            self.assertEqual(summary["route"]["stationary_run_max"], 6)
            self.assertEqual(summary["route"]["terminal_stationary_run"], 0)

    def test_gameplay_score_discounts_unproductive_fire(self) -> None:
        actions = {
            "line_count": 4,
            "movement_action_count": 1,
            "combat_action_count": 1,
            "phase_count": 0,
        }
        commands = {
            "line_count": 10,
            "wait_count": 5,
            "pressed_button_variety": 3,
            "press_counts": {"forward": 1, "attack": 1},
            "wait_clamped_count": 0,
        }
        log = {"policy_done_present": True, "phase_count": 0}
        frames = {"frame_count": 0, "delta": {}}
        trace = {"exists": False}
        gates = {
            "required_inputs_present": True,
            "run_completed": True,
            "frames_present": True,
            "no_unknown_actions": True,
            "no_unknown_commands": True,
        }

        base_gameplay = {
            "sample_count": 2,
            "player": {"survived": True},
            "route": {
                "total_distance": 72.0,
                "max_displacement_from_start": 72.0,
                "terminal_stall": False,
                "leaf_transition_count": 1,
            },
            "pickup": {"pickup_count": 0},
            "combat": {
                "damage_dealt_inferred": 0,
                "damage_taken": 0,
                "kills": 0,
                "attack_press_count": 2,
                "attack_visible_frames": 0,
                "attack_aligned_frames": 0,
                "visible_enemy_frames": 0,
                "enemy_contact_frames": 0,
            },
        }
        disciplined_gameplay = json.loads(json.dumps(base_gameplay))
        disciplined_gameplay["combat"]["unproductive_attack_fraction"] = 0.0
        wasteful_gameplay = json.loads(json.dumps(base_gameplay))
        wasteful_gameplay["combat"]["unproductive_attack_fraction"] = 1.0

        disciplined = noesis_summary.build_gameplay_score(
            actions, commands, log, frames, trace, disciplined_gameplay, gates
        )
        wasteful = noesis_summary.build_gameplay_score(
            actions, commands, log, frames, trace, wasteful_gameplay, gates
        )

        self.assertEqual(
            disciplined["breakdown"]["combat_effectiveness"] -
            wasteful["breakdown"]["combat_effectiveness"],
            3.0,
        )

    def test_gameplay_score_discounts_unproductive_ammo_spend(self) -> None:
        actions = {
            "line_count": 4,
            "movement_action_count": 1,
            "combat_action_count": 1,
            "phase_count": 0,
        }
        commands = {
            "line_count": 10,
            "wait_count": 5,
            "pressed_button_variety": 3,
            "press_counts": {"forward": 1, "attack": 1},
            "wait_clamped_count": 0,
        }
        log = {"policy_done_present": True, "phase_count": 0}
        frames = {"frame_count": 0, "delta": {}}
        trace = {"exists": False}
        gates = {
            "required_inputs_present": True,
            "run_completed": True,
            "frames_present": True,
            "no_unknown_actions": True,
            "no_unknown_commands": True,
        }
        base_gameplay = {
            "sample_count": 2,
            "player": {"survived": True},
            "route": {
                "total_distance": 72.0,
                "max_displacement_from_start": 72.0,
                "terminal_stall": False,
                "leaf_transition_count": 1,
            },
            "pickup": {"pickup_count": 0},
            "combat": {
                "damage_dealt_inferred": 0,
                "damage_taken": 0,
                "kills": 0,
                "attack_press_count": 0,
                "attack_visible_frames": 0,
                "attack_aligned_frames": 0,
                "visible_enemy_frames": 4,
                "enemy_contact_frames": 8,
                "unproductive_attack_fraction": 0.0,
            },
        }
        no_spend_gameplay = json.loads(json.dumps(base_gameplay))
        no_spend_gameplay["combat"]["ammo_spent"] = 0.0
        no_spend_gameplay["combat"]["ammo_waste_fraction"] = 0.0
        wasted_gameplay = json.loads(json.dumps(base_gameplay))
        wasted_gameplay["combat"]["ammo_spent"] = 4.0
        wasted_gameplay["combat"]["ammo_waste_fraction"] = 1.0

        no_spend = noesis_summary.build_gameplay_score(
            actions, commands, log, frames, trace, no_spend_gameplay, gates
        )
        wasted = noesis_summary.build_gameplay_score(
            actions, commands, log, frames, trace, wasted_gameplay, gates
        )

        self.assertEqual(no_spend["ammo_efficiency_penalty"], 0.0)
        self.assertEqual(wasted["ammo_efficiency_penalty"], 2.0)
        self.assertEqual(
            no_spend["breakdown"]["combat_effectiveness"] -
            wasted["breakdown"]["combat_effectiveness"],
            2.0,
        )

    def test_terminal_stall_blocks_route_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            actions_path = tmpdir / "actions.txt"
            commands_path = tmpdir / "commands.cfg"
            log_path = tmpdir / "quantum_quake.log"
            gameplay_path = tmpdir / "gameplay_outcomes.ndjson"
            manifest_path = tmpdir / "manifest.json"

            actions_path.write_text(
                "\n".join([
                    "cmd echo QGE_NOESIS_POLICY map=e1m1 plan=adaptive",
                    "cmd echo QGE_NOESIS_PHASE phase=e1m1_door_slide",
                    "door-open 8",
                    "wall-slide-right 8",
                    "cmd echo QGE_NOESIS_POLICY done",
                ]) + "\n",
                encoding="utf-8",
            )
            commands_path.write_text(
                "\n".join([
                    "echo QGE_NOESIS_PLAYER start source=cmd start_wait=0",
                    "echo QGE_NOESIS_PHASE phase=e1m1_door_slide",
                    "+speed",
                    "+forward",
                    "+use",
                    "wait",
                    "-use",
                    "-forward",
                    "-speed",
                    "echo QGE_NOESIS_PLAYER done",
                ]) + "\n",
                encoding="utf-8",
            )
            log_path.write_text(
                "QGE_NOESIS_POLICY map=e1m1 plan=adaptive\n"
                "QGE_NOESIS_PHASE phase=e1m1_door_slide\n"
                "QGE_NOESIS_POLICY done\n",
                encoding="utf-8",
            )
            samples = []
            for i in range(15):
                moved = i >= 1
                samples.append({
                    "schema": "qge.gameplay_outcome.v0",
                    "type": "sample",
                    "frame": i + 1,
                    "player": {
                        "health": 100,
                        "armor": 0,
                        "weapon": 2,
                        "origin": [96, 0, 0] if moved else [0, 0, 0],
                    },
                    "route": {
                        "frame_distance": 96.0 if i == 1 else 0.0,
                        "total_distance": 96.0 if moved else 0.0,
                        "displacement_from_start": 96.0 if moved else 0.0,
                        "max_displacement_from_start": 96.0 if moved else 0.0,
                        "leaf_transition_count": 1 if moved else 0,
                    },
                    "combat": {
                        "damage_taken_total": 0,
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_presses_total": 0,
                        "visible_enemy_count": 0,
                        "nearest_enemy_distance": -1,
                        "nearest_enemy_visible": False,
                    },
                    "pickup": {
                        "pickups_total": 0,
                        "weapon_changes_total": 0,
                    },
                })
            gameplay_path.write_text(
                "\n".join(json.dumps(sample) for sample in samples) + "\n",
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps({
                    "map": "e1m1",
                    "run": {
                        "status": "ok",
                        "success": 1,
                        "timed_out": 0,
                        "startup_issue": "",
                    },
                    "input": {
                        "player": "noesis",
                        "noesis_plan": "adaptive",
                    },
                    "noesis": {
                        "gameplay_outcomes_file": str(gameplay_path),
                    },
                }),
                encoding="utf-8",
            )

            args = SimpleNamespace(
                manifest=manifest_path,
                actions=actions_path,
                commands=commands_path,
                log=log_path,
                gameplay_outcomes=gameplay_path,
                trace_summary=None,
                frames_dir=None,
                plan="",
                player="",
                min_actions=1,
                min_commands=1,
                min_frames=0,
                min_frame_mae=None,
                min_log_phases=1,
                min_gameplay_samples=2,
                min_route_distance=64.0,
                require_phase_markers=True,
                require_combat=False,
            )
            summary = noesis_summary.build_summary(args)
            self.assertEqual(summary["status"], "blocked")
            self.assertTrue(summary["gameplay"]["route"]["terminal_stall"])
            self.assertEqual(
                summary["gameplay"]["route"]["terminal_stationary_run"],
                13,
            )
            self.assertIn("terminal_stall_absent", summary["failures"])
            self.assertIn("not_stuck", summary["failures"])

            icc = noesis_summary.build_icc_evidence(
                summary,
                tmpdir / "qge_noesis_summary.json",
            )
            by_name = {entry["name"]: entry["value"] for entry in icc}
            self.assertTrue(by_name["noesis_gameplay_terminal_stall"])
            self.assertEqual(by_name["noesis_gameplay_max_stationary_run"], 13)
            self.assertGreater(by_name["noesis_gameplay_stationary_fraction"], 0.8)

    def test_visible_enemy_without_combat_does_not_mask_terminal_stall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            actions_path = tmpdir / "actions.txt"
            commands_path = tmpdir / "commands.cfg"
            log_path = tmpdir / "quantum_quake.log"
            gameplay_path = tmpdir / "gameplay_outcomes.ndjson"
            manifest_path = tmpdir / "manifest.json"

            actions_path.write_text(
                "\n".join([
                    "cmd echo QGE_NOESIS_POLICY map=e1m1 plan=raw",
                    "cmd +forward",
                    "cmd echo QGE_NOESIS_POLICY done",
                ]) + "\n",
                encoding="utf-8",
            )
            commands_path.write_text(
                "\n".join([
                    "echo QGE_NOESIS_PLAYER start source=cmd start_wait=0",
                    "+forward",
                    "wait",
                    "-forward",
                    "echo QGE_NOESIS_PLAYER done",
                ]) + "\n",
                encoding="utf-8",
            )
            log_path.write_text(
                "QGE_NOESIS_POLICY map=e1m1 plan=raw\n"
                "QGE_NOESIS_POLICY done\n",
                encoding="utf-8",
            )
            samples = []
            for i in range(15):
                moved = i >= 1
                samples.append({
                    "schema": "qge.gameplay_outcome.v0",
                    "type": "sample",
                    "frame": i + 1,
                    "player": {
                        "health": 100,
                        "armor": 0,
                        "weapon": 2,
                        "origin": [96, 0, 0] if moved else [0, 0, 0],
                    },
                    "route": {
                        "frame_distance": 96.0 if i == 1 else float("nan"),
                        "total_distance": 96.0 if moved else 0.0,
                        "displacement_from_start": 96.0 if moved else 0.0,
                        "max_displacement_from_start": 96.0 if moved else 0.0,
                        "leaf_transition_count": 1 if moved else 0,
                    },
                    "combat": {
                        "damage_taken_total": 0,
                        "damage_dealt_inferred_total": 0,
                        "kills_total": 0,
                        "attack_presses_total": 0,
                        "visible_enemy_count": 1 if i >= 2 else 0,
                        "nearest_enemy_distance": 256,
                        "nearest_enemy_visible": i >= 2,
                    },
                    "pickup": {
                        "pickups_total": 0,
                        "weapon_changes_total": 0,
                    },
                })
            gameplay_path.write_text(
                "\n".join(json.dumps(sample) for sample in samples) + "\n",
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps({
                    "map": "e1m1",
                    "run": {
                        "status": "ok",
                        "success": 1,
                        "timed_out": 0,
                        "startup_issue": "",
                    },
                    "input": {
                        "player": "noesis",
                        "noesis_plan": "raw",
                    },
                    "noesis": {
                        "gameplay_outcomes_file": str(gameplay_path),
                    },
                }),
                encoding="utf-8",
            )

            args = SimpleNamespace(
                manifest=manifest_path,
                actions=actions_path,
                commands=commands_path,
                log=log_path,
                gameplay_outcomes=gameplay_path,
                trace_summary=None,
                frames_dir=None,
                plan="",
                player="",
                min_actions=1,
                min_commands=1,
                min_frames=0,
                min_frame_mae=None,
                min_log_phases=0,
                min_phase_outcomes=0,
                min_gameplay_samples=2,
                min_route_distance=64.0,
                require_phase_markers=False,
                require_combat=False,
            )
            summary = noesis_summary.build_summary(args)
            self.assertEqual(summary["status"], "blocked")
            self.assertTrue(summary["quality_gates"]["movement_actions_present"])
            self.assertTrue(summary["gameplay"]["route"]["terminal_stall"])
            self.assertEqual(
                summary["gameplay"]["route"]["terminal_visible_enemy_samples"],
                13,
            )
            self.assertIn("terminal_stall_absent", summary["failures"])
            self.assertIn("not_stuck", summary["failures"])


class TraceSummaryTests(unittest.TestCase):
    def test_parse_trace_state_probe_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "qge_trace.bin"
            label = b"render_gate_kernel"
            fallback_message = b"replay entropy metadata mismatch"
            entropy_payload = trace_summary.ENTROPY.pack(
                7,         # frame
                125,       # server time msec
                6,         # rng domain
                1,         # replay source
                0,         # subject id
                11,        # request id
                0x123456,  # value
                3,         # entropy offset
            )
            payload = trace_summary.STATE_PROBE.pack(
                7,      # frame
                125,    # server time msec
                0,      # render domain
                2,      # sparse DWT representation
                9,      # subject id / gate count
                0x3,    # probe flags
                0xAA55, # state hash
                0.25,   # entropy
                0.75,   # coherence
                0.5,    # max probability
                16.0,   # total probability / shots
                128,    # active basis count
                8,      # qubit count
                4096,   # memory bytes
                label + b"\0" * (32 - len(label)),
            )
            fallback_payload = trace_summary.FALLBACK.pack(
                8,      # frame
                140,    # server time msec
                6,      # rng domain
                0,      # none representation
                0,      # subject id
                1,      # replay metadata mismatch
                0.0,    # metric value
                fallback_message + b"\0" * (96 - len(fallback_message)),
            )
            ai_payload = trace_summary.AI_DECISION.pack(
                9,       # frame
                156,     # server time msec
                17,      # enemy id
                2,       # enemy type
                1,       # target entnum
                0x10,    # input flags
                0x9,     # output flags
                0x2,     # legal action mask
                0x1234,  # input hash
                0x5,     # raw basis
                0x1,     # action basis
                4,       # entropy offset
                1,       # mapped patrol
                1,       # action patrol
                0.125,   # selected probability
                0.5,     # action probability
                0.5,     # max probability
                1.0,     # total probability
                0.25,    # confidence
            )
            trace_path.write_bytes(
                trace_summary.HEADER.pack(
                    trace_summary.TRACE_MAGIC,
                    trace_summary.TRACE_VERSION,
                    trace_summary.HEADER.size,
                    0x1,
                    0,
                    0x5151455F52554E31,
                    0x2,
                    0x3,
                    0x4,
                )
                + trace_summary.RECORD.pack(
                    3,
                    trace_summary.TRACE_VERSION,
                    len(entropy_payload),
                    0,
                )
                + entropy_payload
                + trace_summary.RECORD.pack(
                    5,
                    trace_summary.TRACE_VERSION,
                    len(payload),
                    1,
                )
                + payload
                + trace_summary.RECORD.pack(
                    6,
                    trace_summary.TRACE_VERSION,
                    len(fallback_payload),
                    2,
                )
                + fallback_payload
                + trace_summary.RECORD.pack(
                    8,
                    trace_summary.TRACE_VERSION,
                    len(ai_payload),
                    3,
                )
                + ai_payload
            )

            parsed = trace_summary.parse_trace(str(trace_path))
            self.assertEqual(parsed["header"]["run_id"], 0x5151455F52554E31)
            self.assertEqual(parsed["records"]["entropy"], 1)
            self.assertEqual(parsed["records"]["state_probe"], 1)
            self.assertEqual(parsed["records"]["fallback"], 1)
            self.assertEqual(parsed["records"]["ai_decision"], 1)
            self.assertEqual(parsed["sequence_errors"], 0)
            self.assertEqual(parsed["replay_health"]["entropy_replay_events"], 1)
            self.assertEqual(parsed["replay_health"]["replay_metadata_mismatches"], 1)
            self.assertEqual(parsed["replay_health"]["ai_decision_events"], 1)
            entropy = parsed["entropy_events"][0]
            self.assertEqual(entropy["domain"], "rng")
            self.assertEqual(entropy["source"], "replay")
            self.assertEqual(entropy["last_request_id"], 11)
            fallback = parsed["fallback_events"][0]
            self.assertEqual(fallback["domain"], "rng")
            self.assertEqual(fallback["reason_code"], 1)
            self.assertEqual(
                fallback["message"],
                "replay entropy metadata mismatch",
            )
            decision = parsed["ai_decisions"][0]
            self.assertEqual(decision["enemy_id"], 17)
            self.assertEqual(decision["enemy_type"], 2)
            self.assertEqual(decision["action"], "patrol")
            self.assertEqual(decision["mapped_action"], "patrol")
            self.assertEqual(decision["legal_action_mask_or"], 0x2)
            self.assertEqual(decision["input_flags_or"], 0x10)
            self.assertEqual(decision["output_flags_or"], 0x9)
            self.assertEqual(decision["action_basis_xor"], 0x1)
            self.assertEqual(decision["last_entropy_offset"], 4)
            self.assertEqual(decision["confidence_max"], 0.25)
            probe = parsed["state_probes"][0]
            self.assertEqual(probe["label"], "render_gate_kernel")
            self.assertEqual(probe["domain"], "render")
            self.assertEqual(probe["representation"], "sparse_dwt")
            self.assertEqual(probe["active_basis_max"], 128)
            self.assertEqual(probe["flags_or"], 0x3)

    def test_runtime_evidence_groups_from_single_trace(self) -> None:
        def label_bytes(label: bytes) -> bytes:
            return label + b"\0" * (32 - len(label))

        def state_probe_payload(
            frame: int,
            domain: int,
            representation: int,
            subject_id: int,
            flags: int,
            label: bytes,
            active_basis: int = 1,
            qubits: int = 1,
        ) -> bytes:
            return trace_summary.STATE_PROBE.pack(
                frame,
                100 + frame,
                domain,
                representation,
                subject_id,
                flags,
                0xAA00 + frame,
                1.0,
                1.0,
                1.0,
                1.0,
                active_basis,
                qubits,
                active_basis * 16,
                label_bytes(label),
            )

        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "qge_trace.bin"
            ai_payload = trace_summary.AI_DECISION.pack(
                1,
                101,
                17,
                2,
                1,
                0x10,
                0x9,
                0x2,
                0x1234,
                0x5,
                0x1,
                4,
                1,
                1,
                0.125,
                0.5,
                0.5,
                1.0,
                0.25,
            )
            payloads = [
                (8, ai_payload),
                (4, trace_summary.MEASUREMENT.pack(
                    2,
                    3,
                    2,
                    8,
                    108,
                    313,
                    0x6F0600,
                    2,
                    0.875,
                    1.0,
                    0x55,
                    0x12345678,
                )),
                (4, trace_summary.MEASUREMENT.pack(
                    2,
                    11,
                    7,
                    7,
                    109,
                    313,
                    0x50013F00,
                    1,
                    1.0,
                    1.0,
                    0x101,
                    0x202,
                )),
                (4, trace_summary.MEASUREMENT.pack(
                    2,
                    12,
                    7,
                    8,
                    110,
                    313,
                    0x106F0600,
                    1,
                    1.0,
                    1.0,
                    0x303,
                    0x404,
                )),
                (4, trace_summary.MEASUREMENT.pack(
                    2,
                    13,
                    7,
                    9,
                    111,
                    313,
                    0x33933F00,
                    1,
                    1.0,
                    1.0,
                    0x505,
                    0x606,
                )),
                (5, state_probe_payload(
                    2, 4, 9, 3, 0x0A, b"audio_source_spatial")),
                (5, state_probe_payload(
                    2, 0, 2, 117, 0x30000, b"render_sparse_dwt",
                    192, 20)),
                (5, state_probe_payload(
                    3, 1, 8, 12, 0x461, b"vis_shadow_parity", 6, 4)),
                (5, state_probe_payload(
                    4, 1, 7, 1, 0x7E0, b"vis_authority_gate", 5, 4)),
                (5, state_probe_payload(
                    5, 1, 7, 2, 0x4E0, b"vis_authority_apply", 5, 4)),
                (5, state_probe_payload(
                    6, 2, 7, 1, 0x0F03, b"projectile_authority_gate", 2, 1)),
                (5, state_probe_payload(
                    7, 2, 7, 1, 0x0F00, b"projectile_authority_gate", 4, 3)),
                (5, state_probe_payload(
                    7, 2, 7, 313, 0x13F00, b"projectile_writeback_decision",
                    0, 0)),
                (5, state_probe_payload(
                    8, 2, 4, 313, 0x6F0600, b"projectile_branch_state",
                    3, 2)),
                (5, state_probe_payload(
                    9, 2, 4, 313, 0x3933F00,
                    b"projectile_preimpact_selection", 2, 1)),
            ]
            data = trace_summary.HEADER.pack(
                trace_summary.TRACE_MAGIC,
                trace_summary.TRACE_VERSION,
                trace_summary.HEADER.size,
                0x1,
                0,
                0x5151455F52554E31,
                0x2,
                0x3,
                0x4,
            )
            for sequence, (kind, payload) in enumerate(payloads):
                data += trace_summary.RECORD.pack(
                    kind,
                    trace_summary.TRACE_VERSION,
                    len(payload),
                    sequence,
                )
                data += payload
            trace_path.write_bytes(data)

            parsed = trace_summary.parse_trace(str(trace_path))
            evidence = parsed["runtime_evidence"]
            self.assertEqual(parsed["records"]["measurement"], 4)
            self.assertTrue(evidence["single_trace_ready"])
            self.assertEqual(evidence["ai"]["decision_count"], 1)
            self.assertEqual(evidence["audio"]["source_spatial_count"], 1)
            self.assertTrue(evidence["audio"]["flags"]["spatial"])
            self.assertTrue(evidence["audio"]["flags"]["processed"])
            self.assertEqual(evidence["render"]["sparse_dwt_count"], 1)
            self.assertTrue(evidence["render"]["flags"]["primary_owned"])
            self.assertTrue(evidence["render"]["flags"]["native_idwt"])
            self.assertFalse(
                evidence["render"]["flags"]["native_idwt_fallback"]
            )
            self.assertFalse(evidence["render"]["flags"]["cpu_idwt"])
            self.assertEqual(evidence["render"]["idwt_backend"], "native")
            self.assertEqual(evidence["render"]["native_bridge_count"], 1)
            self.assertEqual(evidence["render"]["native_fallback_count"], 0)
            self.assertEqual(evidence["render"]["cpu_idwt_count"], 0)
            self.assertEqual(
                evidence["visibility"]["authority_gate_count"],
                1,
            )
            self.assertEqual(
                evidence["visibility"]["authority_apply_count"],
                1,
            )
            self.assertTrue(
                evidence["visibility"]["flags"]["authority_requested"]
            )
            self.assertTrue(evidence["visibility"]["flags"]["authority_ready"])
            self.assertTrue(
                evidence["visibility"]["flags"]["authority_selected"]
            )
            self.assertTrue(
                evidence["visibility"]["flags"]["controlled_authority_smoke"]
            )
            self.assertFalse(
                evidence["visibility"]["flags"]["fallback_selected"]
            )
            self.assertFalse(
                evidence["visibility"]["flags"]["warmup_pending"]
            )
            self.assertEqual(
                evidence["projectile"]["authority_gate_count"],
                2,
            )
            self.assertEqual(evidence["projectile"]["active_projectiles"], 1)
            self.assertEqual(evidence["projectile"]["active_projectiles_max"], 1)
            self.assertEqual(
                evidence["projectile"]["writeback_decision_count"],
                1,
            )
            self.assertEqual(evidence["projectile"]["branch_state_count"], 1)
            self.assertEqual(
                evidence["projectile"]["preimpact_selection_count"],
                1,
            )
            self.assertEqual(
                evidence["projectile"]["impact_measurement_count"],
                1,
            )
            self.assertTrue(
                evidence["projectile"]["flags"]["authority_ready"]
            )
            self.assertTrue(
                evidence["projectile"]["flags"]["authority_requested"]
            )
            self.assertTrue(
                evidence["projectile"]["flags"]["quantum_projectiles_enabled"]
            )
            self.assertTrue(
                evidence["projectile"]["flags"]["writeback_selected"]
            )
            self.assertTrue(
                evidence["projectile"]["flags"]["physics_authoritative_cvar"]
            )
            self.assertTrue(evidence["projectile"]["flags"]["branch_state"])
            self.assertTrue(evidence["projectile"]["flags"]["branch_observed"])
            self.assertTrue(evidence["projectile"]["flags"]["impact_measured"])
            self.assertTrue(
                evidence["projectile"]["flags"]["branch_selected_qge"]
            )
            self.assertTrue(
                evidence["projectile"]["flags"]["branch_selected_impact"]
            )
            self.assertTrue(evidence["projectile"]["flags"]["branch_decohered"])
            self.assertTrue(evidence["projectile"]["flags"]["collision_oracle"])
            self.assertTrue(evidence["projectile"]["flags"]["oracle_qge_trace"])
            self.assertTrue(evidence["projectile"]["flags"]["oracle_no_impact"])
            self.assertEqual(evidence["projectile"]["preimpact_oracle_count"], 1)
            self.assertEqual(
                evidence["projectile"]["save_demo_boundary_count"],
                3,
            )
            self.assertEqual(
                evidence["projectile"]["save_demo_writeback_count"],
                1,
            )
            self.assertEqual(evidence["projectile"]["save_demo_branch_count"], 1)
            self.assertEqual(
                evidence["projectile"]["save_demo_collision_oracle_count"],
                1,
            )
            self.assertTrue(
                evidence["projectile"]["flags"]["save_demo_boundary"]
            )
            self.assertTrue(
                evidence["projectile"]["flags"]["save_demo_writeback"]
            )
            self.assertTrue(
                evidence["projectile"]["flags"]["save_demo_collision_oracle"]
            )
            self.assertEqual(
                evidence["projectile"]["preimpact_no_impact_count"],
                1,
            )
            self.assertEqual(evidence["projectile"]["branch_basis_max"], 3)
            self.assertEqual(
                evidence["projectile"]["branch_selected_probability_max"],
                1.0,
            )
            self.assertEqual(
                evidence["projectile"]["preimpact_selected_probability_max"],
                1.0,
            )
            self.assertEqual(evidence["projectile"]["off_reason"], "none")

    def test_runtime_evidence_tracks_cpu_render_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trace_path = Path(tmp) / "qge_trace.bin"
            label = b"render_sparse_dwt"
            payload = trace_summary.STATE_PROBE.pack(
                4,
                104,
                0,
                2,
                64,
                0x80000,
                0xCAFE,
                0.125,
                0.875,
                0.75,
                256.0,
                512,
                10,
                4096,
                label + b"\0" * (32 - len(label)),
            )
            trace_path.write_bytes(
                trace_summary.HEADER.pack(
                    trace_summary.TRACE_MAGIC,
                    trace_summary.TRACE_VERSION,
                    trace_summary.HEADER.size,
                    0x1,
                    0,
                    0x5151455F52554E31,
                    0x2,
                    0x3,
                    0x4,
                )
                + trace_summary.RECORD.pack(
                    5,
                    trace_summary.TRACE_VERSION,
                    len(payload),
                    0,
                )
                + payload
            )

            parsed = trace_summary.parse_trace(str(trace_path))
            evidence = parsed["runtime_evidence"]
            self.assertEqual(evidence["render"]["sparse_dwt_count"], 1)
            self.assertEqual(evidence["render"]["idwt_backend"], "cpu")
            self.assertFalse(evidence["render"]["flags"]["native_idwt"])
            self.assertFalse(
                evidence["render"]["flags"]["native_idwt_fallback"]
            )
            self.assertTrue(evidence["render"]["flags"]["cpu_idwt"])
            self.assertEqual(evidence["render"]["native_bridge_count"], 0)
            self.assertEqual(evidence["render"]["native_fallback_count"], 0)
            self.assertEqual(evidence["render"]["cpu_idwt_count"], 1)


class VanillaCaptureMatrixTests(unittest.TestCase):
    def test_build_matrix_and_icc_evidence(self) -> None:
        probe_targets = [
            "qge_context_get_or_create_render_acceleration",
            "qge_dwt_render",
            "qge_metal_init_common",
        ]
        probe_proofs = {
            "qge_context_get_or_create_render_acceleration": {
                "event_count": 1,
                "backends": ["Metal"],
                "paths": ["native_sparse_dwt_render_bridge"],
                "results": ["created"],
                "phases": ["create"],
                "native_values": [1],
                "active_values": [1],
                "native_bridge_evidence": True,
                "active_evidence": True,
            },
            "qge_dwt_render": {
                "event_count": 1,
                "backends": ["Metal"],
                "paths": ["native_sparse_dwt_render_bridge"],
                "results": ["native"],
                "phases": ["idwt"],
                "native_values": [1],
                "active_values": [1],
                "native_bridge_evidence": True,
                "active_evidence": True,
            },
            "qge_metal_init_common": {
                "event_count": 1,
                "backends": ["Metal"],
                "paths": ["native_sparse_dwt_render_bridge"],
                "results": ["active"],
                "phases": ["create"],
                "native_values": [],
                "active_values": [],
                "native_bridge_evidence": True,
                "active_evidence": True,
            },
        }
        metrics = {
            "mae_rgb_normalized": 0.0,
            "rmse_rgb": 0.0,
            "psnr_db": None,
            "luma_ssim_global": 1.0,
            "histogram_intersection_rgb": 1.0,
            "edge": {
                "edge_precision": 1.0,
                "edge_recall": 1.0,
                "edge_f1": 1.0,
                "edge_jaccard": 1.0,
            },
        }
        manifest = {
            "status": "complete",
            "frames_requested": 1,
            "frames_captured": 1,
            "trace_requested": 1,
            "trace_status": "copied",
            "trace_bytes": 128,
            "run": {
                "status": "ok",
                "success": 1,
                "startup_issue": "",
                "process_status": 0,
                "timed_out": 0,
            },
        }
        performance = {
            "status": "pass",
            "aggregate": {
                "engine_average_quantum_ms_max": 10.0,
                "render_time_ms_max": 20.0,
                "threshold_failures": [],
                "metric_evidence_present": True,
                "backend_gate_event_count": 3,
                "backend_gate_paths": [
                    "native_sparse_dwt_render_bridge",
                    "sparse_dwt_cpu_render_path",
                ],
                "backend_gate_backends": ["Metal"],
                "backend_gate_render_bridge_paths": [
                    "native_sparse_dwt_render_bridge",
                ],
                "backend_gate_render_bridge_active": True,
                "runtime_backend_probe_event_count": 3,
                "runtime_backend_probe_targets": probe_targets,
                "runtime_backend_probe_backends": ["Metal"],
                "runtime_backend_probe_paths": [
                    "native_sparse_dwt_render_bridge",
                ],
                "runtime_backend_probe_results": [
                    "active",
                    "created",
                    "native",
                ],
                "required_runtime_backend_probe_targets": probe_targets,
                "runtime_backend_probe_proofs": probe_proofs,
                "runtime_backend_probe_missing_targets": [],
                "runtime_backend_probe_native_targets": probe_targets,
                "runtime_backend_probe_resolved": True,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            capture_dir = Path(tmp)
            vanilla_matrix.write_json(capture_dir / "metrics.json", metrics)
            runtime_evidence = {
                "single_trace_ready": True,
                "render": {
                    "sparse_dwt_count": 1,
                    "native_bridge_count": 1,
                    "cpu_idwt_count": 0,
                    "idwt_backend": "native",
                },
                "ai": {"ready": True, "decision_count": 2},
                "audio": {
                    "ready": True,
                    "source_spatial_count": 3,
                },
                "visibility": {
                    "ready": True,
                    "authority_gate_count": 1,
                    "authority_apply_count": 1,
                    "flags": {"authority_requested": True},
                },
                "projectile": {
                    "ready": True,
                    "authority_gate_count": 1,
                    "active_projectiles": 0,
                    "active_projectiles_max": 1,
                    "writeback_decision_count": 1,
                    "off_reason": "no_projectiles",
                },
            }
            vanilla_matrix.write_json(
                capture_dir / "quantum.qge_trace_summary.json",
                {
                    "records": {
                        "ai_decision": 2,
                        "entropy": 2,
                        "measurement": 2,
                    },
                    "runtime_evidence": runtime_evidence,
                },
            )
            for mode, render_value in (("classic", 0), ("quantum", 2)):
                (capture_dir / f"{mode}.png").write_bytes(b"png")
                (capture_dir / f"{mode}.README.txt").write_text(
                    "Frames captured: 1\nMap: e1m1\n",
                    encoding="utf-8",
                )
                vanilla_matrix.write_json(
                    capture_dir / f"{mode}.agent_stream.json", manifest
                )
                vanilla_matrix.write_json(
                    capture_dir / f"{mode}.qge_perf_summary.json",
                    performance,
                )
                owner = "qge_3d" if mode == "quantum" else "classic"
                ownership = (
                    "own_world=1 own_textures=1 own_lightmaps=1 "
                    "own_entities=1 own_sprites=1 own_particles=1 "
                    "own_viewmodel=1 own_hud=1 own_console=1 "
                    if mode == "quantum" else ""
                )
                warmup = ""
                if mode == "quantum":
                    warmup = (
                        f"QGE render frame=0 render={render_value} fallback=0 "
                        f"surrogate=0 classic3d=0 classic2d=1 viewmodel=1 "
                        f"owner={owner} suppressed3d=1 suppressed2d=0 "
                        "own_world=1 own_textures=1 own_lightmaps=1 "
                        "own_entities=1 own_sprites=1 own_particles=1 "
                        "own_viewmodel=1 own_hud=0 own_console=1 "
                        "entity_culls=2 entity_misses=0 "
                        "poly=3 tris=6 edgefills=2 gate_kernel=1 gates=26 "
                        "shots=64 primary_fb=1 native_idwt=1 cpu_idwt=0 "
                        "idwt_backend=native fallback_reason=classic2d_unowned\n"
                    )
                (capture_dir / f"{mode}.log").write_text(
                    warmup +
                    f"QGE render frame=1 render={render_value} fallback=0 "
                    f"surrogate=0 classic3d=0 classic2d=0 viewmodel=1 "
                    f"owner={owner} suppressed3d=1 suppressed2d=1 "
                    f"{ownership}entity_culls=2 entity_misses=0 "
                    f"poly=3 tris=6 edgefills=2 "
                    f"gate_kernel=1 gates=26 shots=64 primary_fb=1 "
                    f"native_idwt=1 cpu_idwt=0 idwt_backend=native\n",
                    encoding="utf-8",
                )

            args = SimpleNamespace(
                capture_dir=capture_dir,
                metrics=None,
                classic_mode="classic",
                qge_mode="quantum",
                classic_render=0,
                qge_render=2,
            )
            matrix = vanilla_matrix.build_matrix(args)
            summary = matrix["conformance_summary"]
            self.assertTrue(summary["classic_frame_exists"])
            self.assertTrue(summary["qge_frame_exists"])
            self.assertTrue(summary["agent_stream_runs_success"])
            self.assertTrue(summary["performance_sidecars_success"])
            self.assertTrue(summary["ready_for_complete_claim"])
            self.assertEqual(summary["qge_primary_owner"], "qge_3d")
            self.assertTrue(summary["qge_classic_output_hidden"])
            self.assertTrue(summary["qge_classic_output_seen_any_frame"])
            self.assertEqual(summary["classic2d_count"], 1)
            self.assertEqual(summary["classic2d_latest"], 0)
            self.assertTrue(summary["qge_asset_ownership_complete"])
            self.assertEqual(summary["qge_asset_ownership"]["own_world"], 1)
            self.assertEqual(summary["qge_entity_culls"], 2)
            self.assertEqual(summary["qge_entity_misses"], 0)
            self.assertTrue(summary["runtime_evidence_ready"])
            self.assertTrue(summary["moonlab_authority_ready"])
            self.assertEqual(summary["moonlab_authority_blockers"], [])
            self.assertEqual(summary["qge_backend_gate_event_count"], 3)
            self.assertEqual(summary["qge_backend_gate_backends"], ["Metal"])
            self.assertTrue(summary["qge_backend_gate_render_bridge_active"])
            self.assertEqual(summary["qge_runtime_backend_probe_event_count"], 3)
            self.assertTrue(summary["qge_runtime_backend_probe_resolved"])
            self.assertEqual(
                summary["qge_runtime_backend_probe_missing_targets"], [])
            self.assertTrue(
                summary["qge_runtime_backend_probe_proofs"]
                ["qge_dwt_render"]["native_bridge_evidence"]
            )
            self.assertEqual(
                summary["qge_runtime_backend_probe_targets"],
                probe_targets,
            )
            self.assertTrue(
                summary["moonlab_domain_readiness"]["projectile_live_authority"]["ready"]
            )
            self.assertTrue(
                summary["moonlab_domain_readiness"]["qge_performance"]["ready"]
            )
            self.assertTrue(
                matrix["runtime_evidence_summary"]["single_trace_ready"]
            )

            icc = vanilla_matrix.build_icc_evidence(
                matrix,
                capture_dir / "vanilla_capture_matrix.json",
                capture_dir / "qge_vanilla_icc_evidence.json",
            )
            self.assertEqual(icc["runtime_backend"], "qge_vanilla_capture_matrix")
            self.assertTrue(icc["runtime_evidence_ready"])
            self.assertTrue(icc["moonlab_authority_ready"])
            self.assertEqual(icc["qge_render_gates"], 26)
            self.assertEqual(icc["qge_backend_gate_event_count"], 3)
            self.assertEqual(
                icc["qge_backend_gate_render_bridge_paths"],
                ["native_sparse_dwt_render_bridge"],
            )
            self.assertEqual(icc["qge_runtime_backend_probe_event_count"], 3)
            self.assertTrue(icc["qge_runtime_backend_probe_resolved"])
            self.assertEqual(icc["runtime_evidence_ai_decision_count"], 2)
            self.assertEqual(
                icc["completion_reason"],
                "qge_vanilla_capture_matrix_complete",
            )
            self.assertEqual(icc["status"], "success")

            vanilla_matrix.write_json(
                capture_dir / "classic.qge_perf_summary.json",
                {
                    "status": "blocked",
                    "aggregate": {
                        "engine_average_quantum_ms_max": None,
                        "render_time_ms_max": None,
                        "threshold_failures": [],
                        "metric_evidence_present": False,
                    },
                },
            )
            summary = vanilla_matrix.build_matrix(args)["conformance_summary"]
            self.assertTrue(summary["performance_sidecars_success"])
            self.assertTrue(summary["ready_for_complete_claim"])

    def test_missing_asset_ownership_blocks_complete_claim(self) -> None:
        metrics = {
            "mae_rgb_normalized": 0.0,
            "rmse_rgb": 0.0,
            "psnr_db": None,
            "luma_ssim_global": 1.0,
            "histogram_intersection_rgb": 1.0,
            "edge": {},
        }
        manifest = {
            "status": "complete",
            "frames_requested": 1,
            "frames_captured": 1,
            "trace_requested": 1,
            "trace_status": "copied",
            "trace_bytes": 128,
            "run": {
                "status": "ok",
                "success": 1,
                "startup_issue": "",
                "process_status": 0,
                "timed_out": 0,
            },
        }
        performance = {
            "status": "pass",
            "aggregate": {
                "engine_average_quantum_ms_max": 10.0,
                "render_time_ms_max": 20.0,
                "threshold_failures": [],
                "metric_evidence_present": True,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            capture_dir = Path(tmp)
            vanilla_matrix.write_json(capture_dir / "metrics.json", metrics)
            for mode, render_value in (("classic", 0), ("quantum", 2)):
                (capture_dir / f"{mode}.png").write_bytes(b"png")
                (capture_dir / f"{mode}.README.txt").write_text(
                    "Frames captured: 1\nMap: e1m1\n",
                    encoding="utf-8",
                )
                vanilla_matrix.write_json(
                    capture_dir / f"{mode}.agent_stream.json", manifest
                )
                vanilla_matrix.write_json(
                    capture_dir / f"{mode}.qge_perf_summary.json",
                    performance,
                )
                owner = "qge_3d" if mode == "quantum" else "classic"
                (capture_dir / f"{mode}.log").write_text(
                    f"QGE render frame=1 render={render_value} fallback=0 "
                    f"surrogate=0 classic3d=0 classic2d=0 viewmodel=1 "
                    f"owner={owner} suppressed3d=1 suppressed2d=1 "
                    "poly=3 tris=6 edgefills=2\n",
                    encoding="utf-8",
                )

            args = SimpleNamespace(
                capture_dir=capture_dir,
                metrics=None,
                classic_mode="classic",
                qge_mode="quantum",
                classic_render=0,
                qge_render=2,
            )
            summary = vanilla_matrix.build_matrix(args)["conformance_summary"]
            self.assertFalse(summary["ready_for_complete_claim"])
            self.assertFalse(summary["qge_asset_ownership_complete"])
            self.assertIn(
                "own_world",
                summary["qge_asset_ownership_missing_fields"],
            )

    def test_start_map_does_not_require_monster_ai_authority(self) -> None:
        summary = {
            "classic_frame_exists": True,
            "qge_frame_exists": True,
            "agent_stream_runs_success": True,
            "fallback_count": 0,
            "qge_surface_surrogates": 0,
            "qge_classic_output_hidden": True,
            "classic2d_latest": 0,
            "classic3d_latest": 0,
            "qge_classic_output_seen_any_frame": True,
            "qge_primary_owner": "qge_3d",
            "viewmodel_encoded": 1,
            "qge_render_gates": 26,
            "qge_render_shots": 64,
            "qge_render_primary_fb": 1,
            "qge_asset_ownership_complete": True,
            "qge_asset_ownership": {
                "own_particles": 1,
                "own_sprites": 1,
            },
            "performance_sidecars_success": True,
            "classic_performance_status": "blocked",
            "qge_performance_status": "pass",
            "qge_performance_threshold_failures": [],
            "qge_backend_gate_event_count": 3,
            "qge_backend_gate_backends": ["Metal"],
            "qge_backend_gate_paths": ["native_sparse_dwt_render_bridge"],
            "qge_backend_gate_render_bridge_paths": [
                "native_sparse_dwt_render_bridge",
            ],
            "qge_backend_gate_render_bridge_active": True,
            "qge_runtime_backend_probe_event_count": 3,
            "qge_runtime_backend_probe_targets": [
                "qge_context_get_or_create_render_acceleration",
                "qge_dwt_render",
                "qge_metal_init_common",
            ],
            "qge_runtime_backend_probe_paths": [
                "native_sparse_dwt_render_bridge",
            ],
            "qge_runtime_backend_probe_proofs": {},
            "qge_runtime_backend_probe_missing_targets": [],
            "qge_runtime_backend_probe_native_targets": [
                "qge_context_get_or_create_render_acceleration",
                "qge_dwt_render",
                "qge_metal_init_common",
            ],
            "qge_runtime_backend_probe_resolved": True,
        }
        runtime_evidence = {
            "render": {
                "sparse_dwt_count": 1,
                "native_bridge_count": 1,
                "cpu_idwt_count": 0,
                "idwt_backend": "native",
            },
            "ai": {"ready": False, "decision_count": 0, "record_count": 0},
            "audio": {"ready": True, "source_spatial_count": 1},
            "visibility": {
                "ready": True,
                "authority_gate_count": 1,
                "authority_apply_count": 1,
            },
            "projectile": {
                "ready": True,
                "authority_gate_count": 1,
                "active_projectiles_max": 1,
                "writeback_decision_count": 1,
            },
        }
        trace_evidence = {"records": {"entropy": 1, "measurement": 1}}

        start_domains = vanilla_matrix.build_moonlab_domain_readiness(
            summary,
            runtime_evidence,
            trace_evidence,
            "start",
        )
        self.assertFalse(start_domains["ai_authority"]["required"])
        self.assertTrue(start_domains["ai_authority"]["ready"])
        self.assertEqual(vanilla_matrix.domain_blockers(start_domains), [])
        self.assertTrue(vanilla_matrix.domains_ready(start_domains))

        combat_domains = vanilla_matrix.build_moonlab_domain_readiness(
            summary,
            runtime_evidence,
            trace_evidence,
            "e1m1",
        )
        self.assertTrue(combat_domains["ai_authority"]["required"])
        self.assertFalse(combat_domains["ai_authority"]["ready"])
        self.assertIn(
            "ai_authority: AI must have QGE decisions in the trace",
            vanilla_matrix.domain_blockers(combat_domains),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
