#!/usr/bin/env python3
"""Direct unit coverage for QGE Python publication/research tools."""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import qge_advantage_benchmark as advantage  # noqa: E402
import qge_image_metrics as image_metrics  # noqa: E402
import qge_noesis_summary as noesis_summary  # noqa: E402
import qge_oracle_export as oracle_export  # noqa: E402
import qge_perf_summary as perf_summary  # noqa: E402
import qge_publication_pack as publication_pack  # noqa: E402
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
            "scene": {"scene_id": "e1m1:7", "trace_run_id": "0x1"},
            "observable": {"observable_id": "light_transport"},
            "sample_space": {"candidate_count": 8},
            "cost_model": {
                "state_prep_cost": 8,
                "readout_model": "sidecar_model",
                "shots": 16,
                "fallback_count": 0,
            },
            "trace_summary": {"sequence_errors": 0},
        }
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


class AdvantageBenchmarkTests(unittest.TestCase):
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


class PublicationPackTests(unittest.TestCase):
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

        manifest = {
            "pack_dir": "pack",
            "artifacts": {
                "oracle": {
                    "oracle_scene": {"path": "oracle_scene.json"},
                    "claims_evidence": {"path": "claims_evidence.json"},
                },
                "advantage": {
                    "metrics": {"path": "advantage_metrics.json"},
                    "scaling_summary": {"path": "scaling_summary.json"},
                },
                "vanilla": {
                    "matrix": {"packed": {"path": "vanilla_capture_matrix.json"}},
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
            "runtime_summary": {
                "publication_ready_for_complete_claim": True,
                "fallback_count": 0,
                "surrogate_count": 0,
                "vanilla_ready_for_complete_claim": True,
                "agent_stream_runs_success": True,
                "vanilla_performance_ok": True,
                "agent_stream_manifest_ok": True,
                "performance_ok": True,
            },
        }
        icc = publication_pack.build_icc_evidence(
            manifest,
            Path("publication_manifest.json"),
            Path("qge_publication_icc_evidence.json"),
        )
        self.assertEqual(icc["runtime_backend"], "qge_publication_pack")
        self.assertEqual(icc["completion_reason"], "qge_publication_artifact_pack_complete")
        self.assertTrue(icc["publication_ready_for_complete_claim"])
        self.assertEqual(icc["status"], "success")


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
            self.assertIn("Delta RMSE", world_frame_metrics.markdown_report(metrics))


class PerformanceSummaryTests(unittest.TestCase):
    def test_parse_log_summary_and_icc_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            log_path = tmpdir / "quantum_quake.log"
            log_path.write_text(
                "\n".join(
                    [
                        "QGE: Backend gate native=1 active=0 flags=0x3d",
                        "QGE render frame=7 time=29.5 setup=1 encode=14 raster=8 "
                        "fdwt=2 dwt=3 convert=1 blit=9",
                        "QGE: Average quantum render time: 31.25 ms (24 frames)",
                        "QGE: Backend gate shutdown native=1 active=0 flags=0x3d",
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

            summary = perf_summary.build_summary(args)
            self.assertEqual(summary["status"], "pass")
            self.assertTrue(summary["aggregate"]["metric_evidence_present"])
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
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            capture_dir = Path(tmp)
            vanilla_matrix.write_json(capture_dir / "metrics.json", metrics)
            runtime_evidence = {
                "single_trace_ready": True,
                "ai": {"ready": True, "decision_count": 2},
                "audio": {
                    "ready": True,
                    "source_spatial_count": 3,
                },
                "visibility": {
                    "ready": True,
                    "authority_gate_count": 1,
                    "flags": {"authority_requested": True},
                },
                "projectile": {
                    "ready": True,
                    "authority_gate_count": 1,
                    "off_reason": "none",
                },
            }
            vanilla_matrix.write_json(
                capture_dir / "quantum.qge_trace_summary.json",
                {
                    "records": {"ai_decision": 2},
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
                (capture_dir / f"{mode}.log").write_text(
                    f"QGE render frame=1 render={render_value} fallback=0 "
                    f"surrogate=0 classic3d=0 classic2d=0 viewmodel=1 "
                    f"owner={owner} suppressed3d=1 suppressed2d=1 "
                    f"{ownership}poly=3 tris=6 edgefills=2\n",
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
            self.assertTrue(summary["qge_asset_ownership_complete"])
            self.assertEqual(summary["qge_asset_ownership"]["own_world"], 1)
            self.assertTrue(summary["runtime_evidence_ready"])
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
            self.assertEqual(icc["runtime_evidence_ai_decision_count"], 2)
            self.assertEqual(
                icc["completion_reason"],
                "qge_vanilla_capture_matrix_complete",
            )
            self.assertEqual(icc["status"], "success")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
