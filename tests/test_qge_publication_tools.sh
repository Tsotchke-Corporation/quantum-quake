#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/qge-publication-tools.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

capture_dir="$tmpdir/capture"
agent_dir="$tmpdir/agent_stream"
matrix_dir="$tmpdir/matrix"
oracle_dir="$tmpdir/oracle"
advantage_dir="$tmpdir/advantage"
pack_dir="$tmpdir/publication_pack"
metrics_dir="$tmpdir/image_metrics"

mkdir -p "$capture_dir" "$agent_dir" "$matrix_dir" "$oracle_dir" \
  "$advantage_dir" "$pack_dir" "$metrics_dir"

python3 - "$capture_dir" "$agent_dir" "$matrix_dir" <<'PY'
import json
import struct
import sys
from pathlib import Path

capture = Path(sys.argv[1])
agent = Path(sys.argv[2])
matrix = Path(sys.argv[3])

TRACE_MAGIC = 0x52544751
TRACE_VERSION = 1
HEADER = struct.Struct("<IHHIIQQQQ")
RECORD = struct.Struct("<HHIQ")
STATE_PROBE = struct.Struct("<iiIIiIQddddiiQ32s")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def label(name):
    encoded = name.encode("utf-8")
    return encoded + (b"\0" * (32 - len(encoded)))


def state_probe(frame, domain, representation, subject, flags, basis, qubits,
                memory, probe_label, total_probability=1.0,
                coherence=0.75, max_probability=0.5):
    return STATE_PROBE.pack(
        frame,
        frame * 16,
        domain,
        representation,
        subject,
        flags,
        subject * 17 + basis,
        0.25,
        coherence,
        max_probability,
        total_probability,
        basis,
        qubits,
        memory,
        label(probe_label),
    )


header = HEADER.pack(
    TRACE_MAGIC,
    TRACE_VERSION,
    HEADER.size,
    0x3,
    0,
    0x5151455F52554E31,
    0x1111,
    0x2222,
    0x3333,
)
payloads = [
    state_probe(1, 0, 7, 8, 0x1, 8, 3, 256, "world_registry"),
    state_probe(2, 0, 2, 128, 0x1, 128, 8, 2048, "render_sparse_dwt"),
    state_probe(3, 0, 11, 12, 0x2, 64, 6, 1024, "render_gate_kernel",
                total_probability=16.0, coherence=0.875,
                max_probability=0.625),
    state_probe(4, 1, 7, 8, 0x1, 8, 3, 512, "frame_snapshot"),
]
with (capture / "qge_trace.bin").open("wb") as f:
    f.write(header)
    for sequence, payload in enumerate(payloads):
        f.write(RECORD.pack(5, TRACE_VERSION, len(payload), sequence))
        f.write(payload)

(capture / "README.txt").write_text(
    "\n".join([
        "Map: e1m1",
        "Internal render resolution: 1024",
        "Render cvar: 2",
        f"Agent stream: {agent}",
        "",
    ]),
    encoding="utf-8",
)
(capture / "quantum_quake.log").write_text(
    "\n".join([
        "QGE: World registry map=e1m1 models=1 surfaces=8 textures=2 lightmaps=2",
        "QGE snapshot frame=7 surfaces=8 edicts=2 lights=1 sounds=1 particles=0",
        "QGE render frame=7 mode=primary owner=qge_3d classic3d=0 suppressed3d=1 res=1024 time=22.0 encode=8.0 setup=1.0 raster=6.0 fdwt=2.0 dwt=1.0 convert=2.0 blit=3.0 reuse=0 interval=8 coeffs=128 snapshot=8 snapshot_miss=0 texcache=8/0 lightcache=8/0 poly=8 tris=16 edgefills=2 microfill=0 culled=0 surrogate=0 micro=0 clipped=0 fallback=0 encoded=8 material=8 edicts=2 alias=1 sprites=1 sbill=1 emesh=1 ecoeff=4 viewmodel=1 entity_miss=0 particles=0 pcoeff=0 gates=12 shots=16 readout=0.875 edgeq=0.125 ggain=1.0 egain=0.75 nonzero=128/1024",
        "QGE: Average quantum render time: 12.50 ms (8 frames)",
        "",
    ]),
    encoding="utf-8",
)
(capture / "frame_001.png").write_bytes(b"synthetic frame placeholder\n")
(capture / "autoexec.cfg.used").write_text("map e1m1\n", encoding="utf-8")
probe_targets = [
    "qge_context_get_or_create_render_acceleration",
    "qge_dwt_render",
    "qge_metal_init_common",
]
probe_proofs = {
    target: {
        "event_count": 1,
        "backends": ["Metal"],
        "paths": ["native_sparse_dwt_render_bridge"],
        "results": [result],
        "phases": [phase],
        "native_values": [1] if target != "qge_metal_init_common" else [],
        "active_values": [1] if target != "qge_metal_init_common" else [],
        "native_bridge_evidence": True,
        "active_evidence": True,
        "latest_event": {
            "target": target,
            "phase": phase,
            "backend": "Metal",
            "path": "native_sparse_dwt_render_bridge",
            "result": result,
        },
    }
    for target, phase, result in [
        ("qge_context_get_or_create_render_acceleration", "create", "created"),
        ("qge_dwt_render", "idwt", "native"),
        ("qge_metal_init_common", "create", "active"),
    ]
}
write_json(capture / "qge_perf_summary.json", {
    "status": "pass",
    "aggregate": {
        "engine_average_quantum_ms_max": 12.5,
        "render_time_ms_max": 22.0,
        "threshold_failures": [],
        "metric_evidence_present": True,
        "runtime_backend_probe_event_count": 3,
        "runtime_backend_probe_targets": probe_targets,
        "runtime_backend_probe_backends": ["Metal"],
        "runtime_backend_probe_paths": ["native_sparse_dwt_render_bridge"],
        "runtime_backend_probe_results": ["active", "created", "native"],
        "required_runtime_backend_probe_targets": probe_targets,
        "runtime_backend_probe_proofs": probe_proofs,
        "runtime_backend_probe_missing_targets": [],
        "runtime_backend_probe_native_targets": probe_targets,
        "runtime_backend_probe_resolved": True,
    },
})
write_json(capture / "qge_perf_icc_evidence.json", {
    "schema": "qge.icc_evidence.v0",
    "completion_reason": "qge_runtime_performance_complete",
    "status": "success",
})

write_json(agent / "manifest.json", {
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
})
(agent / "events.ndjson").write_text(
    '{"event":"complete","status":"ok"}\n',
    encoding="utf-8",
)
(agent / "qge_agent_stream_icc_evidence.jsonl").write_text(
    '{"completion_reason":"qge_agent_media_stream_complete","status":"success"}\n',
    encoding="utf-8",
)
(agent / "frame_001.png").write_bytes(b"agent frame placeholder\n")

classic_frame = matrix / "classic.png"
qge_frame = matrix / "quantum.png"
classic_frame.write_bytes(b"classic frame placeholder\n")
qge_frame.write_bytes(b"qge frame placeholder\n")
write_json(matrix / "vanilla_capture_matrix.json", {
    "modes": [
        {"mode": "classic", "frame": {"path": str(classic_frame)}},
        {"mode": "quantum", "frame": {"path": str(qge_frame)}},
    ],
    "conformance_summary": {
        "ready_for_complete_claim": True,
        "fallback_count": 0,
        "qge_surface_surrogates": 0,
        "classic3d_count": 0,
        "viewmodel_encoded": True,
        "agent_stream_runs_success": True,
        "classic_agent_run_status": "ok",
        "qge_agent_run_status": "ok",
        "classic_agent_startup_issue": "",
        "qge_agent_startup_issue": "",
        "performance_sidecars_success": True,
        "classic_performance_status": "pass",
        "qge_performance_status": "pass",
        "classic_performance_engine_average_quantum_ms_max": 8.0,
        "qge_performance_engine_average_quantum_ms_max": 12.5,
        "classic_performance_render_time_ms_max": 11.0,
        "qge_performance_render_time_ms_max": 22.0,
        "classic_performance_threshold_failures": [],
        "qge_performance_threshold_failures": [],
    },
})
write_json(matrix / "qge_vanilla_icc_evidence.json", {
    "schema": "qge.icc_evidence.v0",
    "runtime_backend": "qge_vanilla_capture_matrix",
    "completion_reason": "qge_vanilla_capture_matrix_complete",
    "vanilla_capture_matrix_file": str(matrix / "vanilla_capture_matrix.json"),
    "ready_for_complete_claim": True,
    "status": "success",
})
PY

python3 "$repo_root/tools/qge_oracle_export.py" "$capture_dir" \
  --claims "$repo_root/docs/claims/qge_claims.json" \
  --oracle-out "$oracle_dir/oracle_scene.json" \
  --claims-out "$oracle_dir/claims_evidence.json" \
  --icc-out "$oracle_dir/qge_icc_evidence.json" > "$tmpdir/oracle.stdout"

python3 - "$oracle_dir/oracle_scene.json" "$oracle_dir/claims_evidence.json" "$oracle_dir/qge_icc_evidence.json" <<'PY'
import json
import sys

oracle = json.load(open(sys.argv[1], encoding="utf-8"))
claims = json.load(open(sys.argv[2], encoding="utf-8"))
icc = json.load(open(sys.argv[3], encoding="utf-8"))
assert oracle["schema"] == "qge.scene_oracle_ir.v0"
assert oracle["scene"]["map"] == "e1m1"
assert oracle["sample_space"]["candidate_count"] == 8
assert oracle["cost_model"]["texture_samples_touched"] == 8
assert oracle["cost_model"]["lightmap_samples_touched"] == 8
assert oracle["cost_model"]["fallback_count"] == 0
assert oracle["trace_summary"]["render_gate_kernel"]["last_subject_id"] == 12
assert claims["schema"] == "qge.claims_evidence.v0"
assert len(claims["claims"]) >= 1
assert icc["completion_reason"] == "qge_scene_oracle_ir_exported"
assert icc["runtime_backend"] == "qge_oracle_export"
assert icc["candidate_count"] == 8
assert icc["status"] == "success"
PY

python3 "$repo_root/tools/qge_advantage_benchmark.py" \
  "$oracle_dir/oracle_scene.json" \
  --outdir "$advantage_dir" \
  --trials 1 \
  --samples 4 \
  --qae-levels 2 \
  --qae-shots 4 \
  --qae-grid-steps 64 \
  --contribution-bits 4 > "$tmpdir/advantage.stdout"

python3 - "$advantage_dir/advantage_metrics.json" "$advantage_dir/qge_advantage_icc_evidence.json" <<'PY'
import json
import sys

metrics = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
assert metrics["schema"] == "qge.advantage_metrics.v0"
assert metrics["observable"]["candidate_count"] == 8
assert metrics["scaling_summary"]["trial_count"] == 1
assert metrics["resource_estimate"]["logical_qubits"] > 0
assert icc["completion_reason"] == "qge_advantage_benchmark_complete"
assert icc["runtime_backend"] == "qge_advantage_benchmark"
assert icc["status"] == "success"
PY

if python3 "$repo_root/tools/qge_advantage_benchmark.py" \
  "$oracle_dir/oracle_scene.json" \
  --outdir "$tmpdir/invalid_advantage" \
  --samples 0 > "$tmpdir/invalid_advantage.stdout" 2> "$tmpdir/invalid_advantage.stderr"; then
  echo "expected invalid advantage benchmark args to fail" >&2
  exit 1
fi
grep -F -- "--samples values must be > 0" "$tmpdir/invalid_advantage.stderr" >/dev/null

python3 "$repo_root/tools/qge_publication_pack.py" \
  --capture-dir "$capture_dir" \
  --vanilla-matrix "$matrix_dir/vanilla_capture_matrix.json" \
  --agent-stream-dir "$agent_dir" \
  --claims "$repo_root/docs/claims/qge_claims.json" \
  --asset-root "$tmpdir/missing-id1" \
  --outdir "$pack_dir" \
  --trials 1 \
  --samples 4 \
  --qae-levels 2 \
  --qae-shots 4 \
  --qae-grid-steps 64 \
  --contribution-bits 4 > "$tmpdir/pack.stdout"

python3 - "$pack_dir/publication_manifest.json" "$pack_dir/qge_publication_icc_evidence.json" <<'PY'
import json
import shlex
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
runtime = manifest["runtime_summary"]
assert manifest["schema"] == "qge.publication_pack.v0"
assert runtime["publication_ready_for_complete_claim"] is True
assert runtime["agent_stream_manifest_ok"] is True
assert runtime["performance_ok"] is True
assert runtime["vanilla_performance_ok"] is True
assert manifest["artifacts"]["oracle"]["oracle_scene"]["exists"] is True
assert manifest["artifacts"]["advantage"]["metrics"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_payload"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_payload_markdown"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_payload_icc_evidence"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_circuits"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_circuits"]["file_count"] > 0
assert manifest["artifacts"]["advantage"]["qae_moonlab_oracle_kernel"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_oracle_kernel_circuit"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_oracle_kernel_markdown"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_oracle_kernel_icc_evidence"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_observation_zero"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_observation_zero_circuit"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_observation_zero_markdown"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_observation_zero_icc_evidence"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_grover_schedule_plan"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_grover_schedule_plan_markdown"]["exists"] is True
assert manifest["artifacts"]["advantage"]["qae_moonlab_grover_schedule_plan_icc_evidence"]["exists"] is True
assert manifest["artifacts"]["resource"]["envelope"]["exists"] is True
assert manifest["artifacts"]["resource"]["full_game_map_coverage"]["exists"] is True
assert manifest["artifacts"]["resource"]["asset_inventory"]["exists"] is True
assert manifest["artifacts"]["resource"]["asset_inventory_icc_evidence"]["exists"] is True
assert manifest["artifacts"]["resource"]["asset_requirements"]["exists"] is True
assert manifest["artifacts"]["resource"]["asset_requirements_markdown"]["exists"] is True
assert manifest["artifacts"]["resource"]["asset_requirements_icc_evidence"]["exists"] is True
assert manifest["artifacts"]["resource"]["registered_asset_intake"]["exists"] is True
assert manifest["artifacts"]["resource"]["registered_asset_intake_markdown"]["exists"] is True
assert manifest["artifacts"]["resource"]["registered_asset_intake_script"]["exists"] is True
assert manifest["artifacts"]["resource"]["registered_asset_intake_icc_evidence"]["exists"] is True
assert manifest["artifacts"]["resource"]["native_backend_boundary"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_job_specs"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_job_results"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_replay_plan"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_submission_packet"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_submission_bundle"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_submission_bundle_markdown"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_submission_bundle_icc_evidence"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_hardware_record_template"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_full_game_plan"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_full_game_plan_markdown"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_full_game_plan_icc_evidence"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_deployment_gate"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_deployment_gate_markdown"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_deployment_gate_icc_evidence"]["exists"] is True
assert manifest["advantage_summary"]["resource_envelope_summary"]["whole_game_hardware_execution_claimed"] is False
assert manifest["advantage_summary"]["full_game_map_coverage_summary"]["status"] == "partial"
assert manifest["advantage_summary"]["full_game_map_coverage_summary"]["target_map_count"] == 32
assert manifest["advantage_summary"]["full_game_map_coverage_summary"]["covered_map_count"] == 0
assert manifest["advantage_summary"]["asset_inventory_summary"]["missing_map_count"] == 32
assert manifest["advantage_summary"]["asset_inventory_summary"]["invalid_bsp_count"] == 0
assert manifest["advantage_summary"]["asset_inventory_summary"]["full_game_asset_ready"] is False
assert manifest["advantage_summary"]["asset_requirements_summary"]["schema"] == "qge.asset_requirements.v0"
assert manifest["advantage_summary"]["asset_requirements_summary"]["status"] == "blocked_missing_registered_assets"
assert manifest["advantage_summary"]["asset_requirements_summary"]["missing_map_count"] == 32
assert manifest["advantage_summary"]["asset_requirements_summary"]["asset_requirements_satisfied"] is False
assert manifest["advantage_summary"]["registered_asset_intake_summary"]["schema"] == "qge.registered_asset_intake.v0"
assert manifest["advantage_summary"]["registered_asset_intake_summary"]["status"] == "blocked_no_candidate_assets"
assert manifest["advantage_summary"]["registered_asset_intake_summary"]["candidate_new_map_count"] == 0
assert manifest["advantage_summary"]["registered_asset_intake_summary"]["missing_map_count_after_plan"] == 32
assert manifest["advantage_summary"]["registered_asset_intake_summary"]["post_install_verification_command_count"] == 2
assert manifest["advantage_summary"]["registered_asset_intake_summary"]["post_install_capture_queue_command_present"] is True
assert manifest["advantage_summary"]["registered_asset_intake_summary"]["asset_intake_copies_game_data"] is False
assert manifest["advantage_summary"]["native_backend_boundary_summary"]["status"] == "pass"
assert manifest["advantage_summary"]["native_backend_boundary_summary"]["passed_target_count"] == 3
assert manifest["advantage_summary"]["moonlab_qae_payload_summary"]["schema"] == "qge.moonlab_qae_payload.v0"
assert manifest["advantage_summary"]["moonlab_qae_payload_summary"]["status"] == "calibration_payload_ready_oracle_transpilation_required"
assert manifest["advantage_summary"]["moonlab_qae_payload_summary"]["semantic_scope"] == "mlae_observation_distribution_payload"
assert manifest["advantage_summary"]["moonlab_qae_payload_summary"]["full_qae_oracle_transpiled"] is False
assert manifest["advantage_summary"]["moonlab_qae_oracle_kernel_summary"]["schema"] == "qge.moonlab_qae_oracle_kernel.v0"
assert manifest["advantage_summary"]["moonlab_qae_oracle_kernel_summary"]["status"] == "qf_oracle_kernel_ready_qae_transpilation_required"
assert manifest["advantage_summary"]["moonlab_qae_oracle_kernel_summary"]["semantic_scope"] == "bernoulli_lift_qf_oracle_kernel"
assert manifest["advantage_summary"]["moonlab_qae_oracle_kernel_summary"]["control_plane_executable"] is True
assert manifest["advantage_summary"]["moonlab_qae_oracle_kernel_summary"]["qf_oracle_kernel_transpiled"] is True
assert manifest["advantage_summary"]["moonlab_qae_oracle_kernel_summary"]["full_qae_oracle_transpiled"] is False
assert manifest["advantage_summary"]["moonlab_qae_observation_zero_summary"]["schema"] == "qge.moonlab_qae_observation_circuit.v0"
assert manifest["advantage_summary"]["moonlab_qae_observation_zero_summary"]["status"] == "qae_observation_zero_ready_grover_schedule_required"
assert manifest["advantage_summary"]["moonlab_qae_observation_zero_summary"]["semantic_scope"] == "bernoulli_lift_qae_power_zero_observation"
assert manifest["advantage_summary"]["moonlab_qae_observation_zero_summary"]["control_plane_executable"] is True
assert manifest["advantage_summary"]["moonlab_qae_observation_zero_summary"]["candidate_state_preparation_transpiled"] is True
assert manifest["advantage_summary"]["moonlab_qae_observation_zero_summary"]["power_zero_observation_transpiled"] is True
assert manifest["advantage_summary"]["moonlab_qae_observation_zero_summary"]["full_qae_oracle_transpiled"] is False
grover_summary = manifest["advantage_summary"]["moonlab_qae_grover_schedule_plan_summary"]
assert grover_summary["schema"] == "qge.moonlab_qae_grover_schedule_plan.v0"
assert grover_summary["status"] in {
    "qae_grover_schedule_ready_for_control_plane_submission",
    "qae_grover_schedule_blocked_control_plane_body_limit",
}
assert grover_summary["semantic_scope"] == "bernoulli_lift_qae_grover_schedule_control_plane_plan"
assert grover_summary["ready_observation_count"] >= 1
assert grover_summary["blocked_observation_count"] >= 0
if grover_summary["blocked_observation_count"] > 0:
    assert grover_summary["first_blocked_power"] >= 1
    assert grover_summary["grover_schedule_transpiled"] is False
else:
    assert grover_summary["first_blocked_power"] is None
    assert grover_summary["grover_schedule_transpiled"] is True
assert manifest["advantage_summary"]["moonlab_job_specs_summary"]["hardware_candidate_job_count"] == 1
assert manifest["advantage_summary"]["moonlab_job_results_summary"]["completed_simulator_job_count"] >= 2
assert manifest["advantage_summary"]["moonlab_job_results_summary"]["hardware_submitted_job_count"] == 0
assert manifest["advantage_summary"]["moonlab_replay_plan_summary"]["schema"] == "qge.moonlab_replay_plan.v0"
assert manifest["advantage_summary"]["moonlab_submission_packet_summary"]["schema"] == "qge.moonlab_submission_packet.v0"
assert manifest["advantage_summary"]["moonlab_submission_packet_summary"]["ready_candidate_count"] == 1
assert manifest["advantage_summary"]["moonlab_submission_bundle_summary"]["schema"] == "qge.moonlab_submission_bundle.v0"
assert manifest["advantage_summary"]["moonlab_submission_bundle_summary"]["status"] == "ready_for_control_plane_submission"
assert manifest["advantage_summary"]["moonlab_submission_bundle_summary"]["ready_for_control_plane_submission_count"] == 1
assert manifest["advantage_summary"]["moonlab_submission_bundle_summary"]["calibration_payload_ready_count"] == 1
assert manifest["advantage_summary"]["moonlab_submission_bundle_summary"]["oracle_kernel_ready_count"] == 1
assert manifest["advantage_summary"]["moonlab_submission_bundle_summary"]["qae_observation_ready_count"] == 1
assert manifest["advantage_summary"]["moonlab_submission_bundle_summary"]["grover_schedule_ready_count"] == 1
assert manifest["advantage_summary"]["moonlab_submission_bundle_summary"]["transpilation_required_count"] == 0
assert manifest["advantage_summary"]["moonlab_submission_bundle_summary"]["hardware_submission_directly_executable"] is True
assert manifest["advantage_summary"]["moonlab_submission_bundle_summary"]["control_plane_payload_directly_executable"] is True
assert manifest["advantage_summary"]["moonlab_submission_bundle_summary"]["oracle_kernel_directly_executable"] is True
assert manifest["advantage_summary"]["moonlab_submission_bundle_summary"]["qae_observation_directly_executable"] is True
assert manifest["advantage_summary"]["moonlab_hardware_record_template_summary"]["schema"] == "qge.moonlab_hardware_record_template.v0"
assert manifest["advantage_summary"]["moonlab_hardware_record_template_summary"]["record_schema"] == "qge.moonlab_hardware_record.v0"
assert manifest["advantage_summary"]["moonlab_full_game_plan_summary"]["schema"] == "qge.moonlab_full_game_deployment_plan.v0"
assert manifest["advantage_summary"]["moonlab_full_game_plan_summary"]["status"] == "blocked_asset_unavailable"
assert manifest["advantage_summary"]["moonlab_full_game_plan_summary"]["asset_unavailable_map_count"] == 32
assert manifest["advantage_summary"]["moonlab_full_game_plan_summary"]["whole_game_moonlab_deployment_claimed"] is False
assert manifest["advantage_summary"]["moonlab_deployment_gate_summary"]["schema"] == "qge.moonlab_deployment_gate.v0"
assert manifest["advantage_summary"]["moonlab_deployment_gate_summary"]["status"] == "blocked"
assert manifest["advantage_summary"]["moonlab_deployment_gate_summary"]["whole_game_moonlab_deployment_claim_allowed"] is False
assert manifest["advantage_summary"]["moonlab_deployment_gate_summary"]["whole_game_hardware_execution_claim_allowed"] is False
assert manifest["advantage_summary"]["moonlab_deployment_gate_summary"]["hardware_quantum_advantage_claim_allowed"] is False
assert manifest["advantage_summary"]["moonlab_deployment_gate_summary"]["dense_70000_qubit_state_claim_allowed"] is False
assert manifest["advantage_summary"]["moonlab_deployment_gate_summary"]["registered_asset_install_script"].endswith("resource/install_registered_assets.sh")
assert manifest["advantage_summary"]["moonlab_deployment_gate_summary"]["registered_asset_intake_file"].endswith("resource/qge_registered_asset_intake.json")
assert manifest["advantage_summary"]["moonlab_deployment_gate_summary"]["post_install_verification_command_count"] == 2
assert manifest["advantage_summary"]["moonlab_deployment_gate_summary"]["post_install_capture_queue_command_present"] is True
assert "qge_full_game_capture_queue.py" in manifest["advantage_summary"]["moonlab_deployment_gate_summary"]["post_install_capture_queue_command"]
assert manifest["artifacts"]["vanilla"]["icc_evidence"]["packed"]["exists"] is True
assert icc["completion_reason"] == "qge_publication_artifact_pack_complete"
assert icc["runtime_backend"] == "qge_publication_pack"
assert icc["publication_ready_for_complete_claim"] is True
assert icc["resource_envelope_file"].endswith("resource/qge_resource_envelope.json")
assert icc["full_game_map_coverage_file"].endswith("resource/qge_full_game_map_coverage.json")
assert icc["full_game_map_coverage_status"] == "partial"
assert icc["full_game_map_target_count"] == 32
assert icc["full_game_map_covered_count"] == 0
assert icc["asset_inventory_file"].endswith("resource/qge_asset_inventory.json")
assert icc["asset_inventory_missing_map_count"] == 32
assert icc["asset_inventory_invalid_bsp_count"] == 0
assert icc["full_game_asset_ready"] is False
assert icc["asset_requirements_file"].endswith("resource/qge_asset_requirements.json")
assert icc["asset_requirements_markdown_file"].endswith("resource/qge_asset_requirements.md")
assert icc["asset_requirements_icc_evidence_file"].endswith("resource/qge_asset_requirements_icc_evidence.json")
assert icc["asset_requirements_schema"] == "qge.asset_requirements.v0"
assert icc["asset_requirement_status"] == "blocked_missing_registered_assets"
assert icc["asset_requirements_missing_map_count"] == 32
assert icc["asset_requirements_satisfied"] is False
assert icc["registered_asset_intake_file"].endswith("resource/qge_registered_asset_intake.json")
assert icc["registered_asset_intake_markdown_file"].endswith("resource/qge_registered_asset_intake.md")
assert icc["registered_asset_intake_script_file"].endswith("resource/install_registered_assets.sh")
assert icc["registered_asset_intake_icc_evidence_file"].endswith("resource/qge_registered_asset_intake_icc_evidence.json")
assert icc["registered_asset_intake_schema"] == "qge.registered_asset_intake.v0"
assert icc["registered_asset_intake_status"] == "blocked_no_candidate_assets"
assert icc["registered_asset_intake_candidate_new_map_count"] == 0
assert icc["registered_asset_intake_missing_map_count_after_plan"] == 32
assert icc["registered_asset_intake_post_install_verification_command_count"] == 2
assert icc["registered_asset_intake_post_install_capture_queue_command_present"] is True
assert icc["asset_intake_copies_game_data"] is False
assert icc["native_backend_boundary_file"].endswith("resource/qge_native_backend_boundary.json")
assert icc["native_backend_boundary_status"] == "pass"
assert icc["moonlab_qae_payload_file"].endswith("advantage/qae_moonlab_payload.json")
assert icc["moonlab_qae_payload_markdown_file"].endswith("advantage/qae_moonlab_payload.md")
assert icc["moonlab_qae_payload_icc_evidence_file"].endswith("advantage/qae_moonlab_payload_icc_evidence.json")
assert icc["moonlab_qae_payload_circuit_file_count"] > 0
assert icc["moonlab_qae_payload_schema"] == "qge.moonlab_qae_payload.v0"
assert icc["moonlab_qae_payload_status"] == "calibration_payload_ready_oracle_transpilation_required"
assert icc["moonlab_qae_payload_semantic_scope"] == "mlae_observation_distribution_payload"
assert icc["moonlab_qae_payload_full_qae_oracle_transpiled"] is False
assert icc["moonlab_qae_oracle_kernel_file"].endswith("advantage/qae_moonlab_oracle_kernel.json")
assert icc["moonlab_qae_oracle_kernel_circuit_file"].endswith("advantage/qae_moonlab_oracle_kernel.moonlab")
assert icc["moonlab_qae_oracle_kernel_markdown_file"].endswith("advantage/qae_moonlab_oracle_kernel.md")
assert icc["moonlab_qae_oracle_kernel_icc_evidence_file"].endswith("advantage/qae_moonlab_oracle_kernel_icc_evidence.json")
assert icc["moonlab_qae_oracle_kernel_schema"] == "qge.moonlab_qae_oracle_kernel.v0"
assert icc["moonlab_qae_oracle_kernel_status"] == "qf_oracle_kernel_ready_qae_transpilation_required"
assert icc["moonlab_qae_oracle_kernel_semantic_scope"] == "bernoulli_lift_qf_oracle_kernel"
assert icc["moonlab_qae_oracle_kernel_control_plane_executable"] is True
assert icc["moonlab_qae_qf_oracle_kernel_transpiled"] is True
assert icc["moonlab_qae_oracle_kernel_full_qae_oracle_transpiled"] is False
assert icc["moonlab_qae_observation_zero_file"].endswith("advantage/qae_moonlab_observation_zero.json")
assert icc["moonlab_qae_observation_zero_circuit_file"].endswith("advantage/qae_moonlab_observation_zero.moonlab")
assert icc["moonlab_qae_observation_zero_markdown_file"].endswith("advantage/qae_moonlab_observation_zero.md")
assert icc["moonlab_qae_observation_zero_icc_evidence_file"].endswith("advantage/qae_moonlab_observation_zero_icc_evidence.json")
assert icc["moonlab_qae_observation_zero_schema"] == "qge.moonlab_qae_observation_circuit.v0"
assert icc["moonlab_qae_observation_zero_status"] == "qae_observation_zero_ready_grover_schedule_required"
assert icc["moonlab_qae_observation_zero_semantic_scope"] == "bernoulli_lift_qae_power_zero_observation"
assert icc["moonlab_qae_observation_zero_control_plane_executable"] is True
assert icc["moonlab_qae_candidate_state_preparation_transpiled"] is True
assert icc["moonlab_qae_power_zero_observation_transpiled"] is True
assert icc["moonlab_qae_observation_zero_full_qae_oracle_transpiled"] is False
assert icc["moonlab_qae_grover_schedule_plan_file"].endswith("advantage/qae_moonlab_grover_schedule_plan.json")
assert icc["moonlab_qae_grover_schedule_plan_markdown_file"].endswith("advantage/qae_moonlab_grover_schedule_plan.md")
assert icc["moonlab_qae_grover_schedule_plan_icc_evidence_file"].endswith("advantage/qae_moonlab_grover_schedule_plan_icc_evidence.json")
assert icc["moonlab_qae_grover_schedule_plan_schema"] == "qge.moonlab_qae_grover_schedule_plan.v0"
assert icc["moonlab_qae_grover_schedule_plan_status"] in {
    "qae_grover_schedule_ready_for_control_plane_submission",
    "qae_grover_schedule_blocked_control_plane_body_limit",
}
assert icc["moonlab_qae_grover_schedule_plan_semantic_scope"] == "bernoulli_lift_qae_grover_schedule_control_plane_plan"
assert icc["moonlab_qae_grover_schedule_ready_observation_count"] >= 1
assert icc["moonlab_qae_grover_schedule_blocked_observation_count"] >= 0
if icc["moonlab_qae_grover_schedule_blocked_observation_count"] > 0:
    assert icc["moonlab_qae_grover_schedule_first_blocked_power"] >= 1
    assert icc["moonlab_qae_grover_schedule_transpiled"] is False
    assert icc["moonlab_qae_grover_schedule_full_qae_oracle_transpiled"] is False
else:
    assert icc["moonlab_qae_grover_schedule_first_blocked_power"] is None
    assert icc["moonlab_qae_grover_schedule_transpiled"] is True
    assert icc["moonlab_qae_grover_schedule_full_qae_oracle_transpiled"] is True
assert icc["moonlab_job_specs_file"].endswith("resource/qge_moonlab_job_specs.json")
assert icc["moonlab_job_results_file"].endswith("resource/qge_moonlab_job_results.json")
assert icc["moonlab_replay_plan_file"].endswith("resource/qge_moonlab_replay_plan.json")
assert icc["moonlab_replay_plan_schema"] == "qge.moonlab_replay_plan.v0"
assert icc["moonlab_submission_packet_file"].endswith("resource/qge_moonlab_submission_packet.json")
assert icc["moonlab_submission_packet_schema"] == "qge.moonlab_submission_packet.v0"
assert icc["moonlab_submission_ready_candidate_count"] == 1
assert icc["moonlab_submission_bundle_file"].endswith("resource/qge_moonlab_submission_bundle.json")
assert icc["moonlab_submission_bundle_markdown_file"].endswith("resource/qge_moonlab_submission_bundle.md")
assert icc["moonlab_submission_bundle_icc_evidence_file"].endswith("resource/qge_moonlab_submission_bundle_icc_evidence.json")
assert icc["moonlab_submission_bundle_schema"] == "qge.moonlab_submission_bundle.v0"
assert icc["moonlab_submission_bundle_status"] == "ready_for_control_plane_submission"
assert icc["moonlab_submission_ready_for_control_plane_submission_count"] == 1
assert icc["moonlab_submission_calibration_payload_ready_count"] == 1
assert icc["moonlab_submission_oracle_kernel_ready_count"] == 1
assert icc["moonlab_submission_qae_observation_ready_count"] == 1
assert icc["moonlab_submission_transpilation_required_count"] == 0
assert icc["moonlab_hardware_submission_directly_executable"] is True
assert icc["moonlab_control_plane_payload_directly_executable"] is True
assert icc["moonlab_oracle_kernel_directly_executable"] is True
assert icc["moonlab_qae_observation_directly_executable"] is True
assert icc["moonlab_hardware_record_template_file"].endswith("resource/qge_moonlab_hardware_record_template.json")
assert icc["moonlab_hardware_record_template_schema"] == "qge.moonlab_hardware_record_template.v0"
assert icc["moonlab_hardware_record_schema"] == "qge.moonlab_hardware_record.v0"
assert icc["moonlab_full_game_plan_file"].endswith("resource/qge_moonlab_full_game_plan.json")
assert icc["moonlab_full_game_plan_markdown_file"].endswith("resource/qge_moonlab_full_game_plan.md")
assert icc["moonlab_full_game_plan_icc_evidence_file"].endswith("resource/qge_moonlab_full_game_plan_icc_evidence.json")
assert icc["moonlab_full_game_plan_schema"] == "qge.moonlab_full_game_deployment_plan.v0"
assert icc["moonlab_full_game_deployment_status"] == "blocked_asset_unavailable"
assert icc["moonlab_full_game_asset_unavailable_map_count"] == 32
assert icc["whole_game_moonlab_deployment_claimed"] is False
assert icc["moonlab_deployment_gate_file"].endswith("resource/qge_moonlab_deployment_gate.json")
assert icc["moonlab_deployment_gate_markdown_file"].endswith("resource/qge_moonlab_deployment_gate.md")
assert icc["moonlab_deployment_gate_icc_evidence_file"].endswith("resource/qge_moonlab_deployment_gate_icc_evidence.json")
assert icc["moonlab_deployment_gate_schema"] == "qge.moonlab_deployment_gate.v0"
assert icc["moonlab_deployment_gate_status"] == "blocked"
assert icc["moonlab_deployment_gate_blocker_count"] >= 4
assert icc["moonlab_deployment_gate_registered_asset_install_script"].endswith("resource/install_registered_assets.sh")
assert icc["moonlab_deployment_gate_registered_asset_intake_file"].endswith("resource/qge_registered_asset_intake.json")
assert icc["moonlab_deployment_gate_post_install_verification_command_count"] == 2
assert icc["moonlab_deployment_gate_post_install_capture_queue_command_present"] is True
assert "qge_full_game_capture_queue.py" in icc["moonlab_deployment_gate_post_install_capture_queue_command"]
assert icc["whole_game_moonlab_deployment_claim_allowed"] is False
assert icc["whole_game_hardware_execution_claim_allowed"] is False
assert icc["hardware_quantum_advantage_claim_allowed"] is False
assert icc["dense_70000_qubit_state_claim_allowed"] is False
assert icc["moonlab_hardware_candidate_job_count"] == 1
assert icc["moonlab_completed_simulator_job_count"] >= 2
assert icc["moonlab_hardware_submitted_job_count"] == 0
assert icc["whole_game_hardware_execution_claimed"] is False
assert icc["vanilla_icc_evidence_file"].endswith("vanilla/qge_vanilla_icc_evidence.json")
assert icc["status"] == "success"
assert any(
    "qge_publication_icc_audit.py" in command
    for command in manifest["reproduce_commands"]
)
assert any(
    "qge_postpack_audit.py" in command
    for command in manifest["reproduce_commands"]
)
source_inputs = manifest["source_inputs"]
oracle_commands = [
    command for command in manifest["reproduce_commands"]
    if command.startswith("tools/qge_oracle_export.py ")
]
assert len(oracle_commands) == 1
oracle_tokens = shlex.split(oracle_commands[0])
assert oracle_tokens[1] == source_inputs["capture_dir"]
assert oracle_tokens[oracle_tokens.index("--claims") + 1] == source_inputs["claims_ledger"]
assert "<capture_dir>" not in oracle_commands[0]
vanilla_commands = [
    command for command in manifest["reproduce_commands"]
    if command.startswith("tools/qge_vanilla_capture_matrix.py ")
]
assert len(vanilla_commands) == 1
vanilla_tokens = shlex.split(vanilla_commands[0])
assert vanilla_tokens[1] == source_inputs["vanilla_matrix"].rsplit("/", 1)[0]
assert "<graphics_capture_dir>" not in vanilla_commands[0]
pack_commands = [
    command for command in manifest["reproduce_commands"]
    if command.startswith("tools/qge_publication_pack.py ")
]
assert len(pack_commands) == 1
pack_tokens = shlex.split(pack_commands[0])
for option, expected in (
    ("--capture-dir", source_inputs["capture_dir"]),
    ("--vanilla-matrix", source_inputs["vanilla_matrix"]),
    ("--agent-stream-dir", source_inputs["agent_stream_dir"]),
    ("--asset-root", source_inputs["asset_root"]),
    ("--claims", source_inputs["claims_ledger"]),
    ("--seed", "1337"),
    ("--trials", "1"),
    ("--qae-levels", "2"),
    ("--qae-shots", "4"),
    ("--qae-grid-steps", "64"),
    ("--contribution-bits", "4"),
):
    index = pack_tokens.index(option)
    assert pack_tokens[index + 1] == str(expected)
assert pack_tokens.count("--samples") == 1
assert pack_tokens[pack_tokens.index("--samples") + 1] == "4"
assert "<trace_capture_dir>" not in pack_commands[0]
asset_requirement_commands = [
    command for command in manifest["reproduce_commands"]
    if command.startswith("tools/qge_asset_requirements.py ")
]
assert len(asset_requirement_commands) == 1
asset_tokens = shlex.split(asset_requirement_commands[0])
assert asset_tokens[asset_tokens.index("--asset-root") + 1] == source_inputs["asset_root"]
assert "<asset_root>" not in asset_requirement_commands[0]
PY

python3 "$repo_root/tools/qge_publication_icc_audit.py" "$pack_dir" \
  --out "$tmpdir/qge_publication_icc_audit.json" \
  --fail-on-mismatch > "$tmpdir/qge_publication_icc_audit.stdout"
grep -F 'QGE_PUBLICATION_ICC_AUDIT' "$tmpdir/qge_publication_icc_audit.stdout" >/dev/null
python3 - "$tmpdir/qge_publication_icc_audit.json" <<'PY'
import json
import sys

audit = json.load(open(sys.argv[1], encoding="utf-8"))
assert audit["passed"] is True
assert audit["recorded"] is True
assert audit["mismatch_count"] == 0
assert audit["field_mismatches"] == []
PY

python3 "$repo_root/tools/qge_moonlab_qae_transpile.py" \
  --metrics "$pack_dir/advantage/advantage_metrics.json" \
  --abstract-circuit "$pack_dir/advantage/qae_circuit.txt" \
  --out "$tmpdir/qae_moonlab_payload.json" \
  --circuit-dir "$tmpdir/moonlab_qae_circuits" \
  --markdown "$tmpdir/qae_moonlab_payload.md" \
  --icc-json "$tmpdir/qae_moonlab_payload_icc_evidence.json" \
  > "$tmpdir/moonlab_qae_transpile.stdout"
grep -F 'QGE_MOONLAB_QAE_PAYLOAD' "$tmpdir/moonlab_qae_transpile.stdout" >/dev/null
grep -F 'QGE_MOONLAB_QAE_CIRCUITS' "$tmpdir/moonlab_qae_transpile.stdout" >/dev/null
grep -F 'QGE_MOONLAB_QAE_PAYLOAD_ICC_EVIDENCE' "$tmpdir/moonlab_qae_transpile.stdout" >/dev/null
python3 - "$tmpdir/qae_moonlab_payload.json" "$tmpdir/qae_moonlab_payload_icc_evidence.json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
assert payload["schema"] == "qge.moonlab_qae_payload.v0"
assert payload["status"] == "calibration_payload_ready_oracle_transpilation_required"
assert payload["semantic_scope"] == "mlae_observation_distribution_payload"
assert payload["payload_resource_estimate"]["circuit_count"] > 0
assert payload["claim_posture"]["full_qae_oracle_transpiled"] is False
assert icc["runtime_backend"] == "qge_moonlab_qae_transpile"
assert icc["full_qae_oracle_transpiled"] is False
PY

python3 "$repo_root/tools/qge_moonlab_oracle_transpile.py" \
  --metrics "$pack_dir/advantage/advantage_metrics.json" \
  --oracle-scene "$pack_dir/oracle/oracle_scene.json" \
  --out "$tmpdir/qae_moonlab_oracle_kernel.json" \
  --circuit "$tmpdir/qae_moonlab_oracle_kernel.moonlab" \
  --markdown "$tmpdir/qae_moonlab_oracle_kernel.md" \
  --icc-json "$tmpdir/qae_moonlab_oracle_kernel_icc_evidence.json" \
  > "$tmpdir/moonlab_oracle_transpile.stdout"
grep -F 'QGE_MOONLAB_QAE_ORACLE_KERNEL' "$tmpdir/moonlab_oracle_transpile.stdout" >/dev/null
grep -F 'QGE_MOONLAB_QAE_ORACLE_CIRCUIT' "$tmpdir/moonlab_oracle_transpile.stdout" >/dev/null
grep -F 'QGE_MOONLAB_QAE_ORACLE_KERNEL_ICC_EVIDENCE' "$tmpdir/moonlab_oracle_transpile.stdout" >/dev/null
python3 - "$tmpdir/qae_moonlab_oracle_kernel.json" "$tmpdir/qae_moonlab_oracle_kernel_icc_evidence.json" <<'PY'
import json
import sys

kernel = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
assert kernel["schema"] == "qge.moonlab_qae_oracle_kernel.v0"
assert kernel["status"] == "qf_oracle_kernel_ready_qae_transpilation_required"
assert kernel["semantic_scope"] == "bernoulli_lift_qf_oracle_kernel"
assert kernel["moonlab_control_plane"]["control_plane_executable"] is True
assert kernel["resource_estimate"]["logical_qubits"] <= 32
assert kernel["resource_estimate"]["gate_count"] > 0
assert kernel["claim_posture"]["qf_oracle_kernel_transpiled"] is True
assert kernel["claim_posture"]["full_qae_oracle_transpiled"] is False
assert icc["runtime_backend"] == "qge_moonlab_oracle_transpile"
assert icc["qf_oracle_kernel_transpiled"] is True
assert icc["full_qae_oracle_transpiled"] is False
PY

python3 "$repo_root/tools/qge_moonlab_qae_observation_transpile.py" \
  --metrics "$pack_dir/advantage/advantage_metrics.json" \
  --oracle-scene "$pack_dir/oracle/oracle_scene.json" \
  --out "$tmpdir/qae_moonlab_observation_zero.json" \
  --circuit "$tmpdir/qae_moonlab_observation_zero.moonlab" \
  --markdown "$tmpdir/qae_moonlab_observation_zero.md" \
  --icc-json "$tmpdir/qae_moonlab_observation_zero_icc_evidence.json" \
  > "$tmpdir/moonlab_observation_transpile.stdout"
grep -F 'QGE_MOONLAB_QAE_OBSERVATION' "$tmpdir/moonlab_observation_transpile.stdout" >/dev/null
grep -F 'QGE_MOONLAB_QAE_OBSERVATION_CIRCUIT' "$tmpdir/moonlab_observation_transpile.stdout" >/dev/null
grep -F 'QGE_MOONLAB_QAE_OBSERVATION_ICC_EVIDENCE' "$tmpdir/moonlab_observation_transpile.stdout" >/dev/null
python3 - "$tmpdir/qae_moonlab_observation_zero.json" "$tmpdir/qae_moonlab_observation_zero_icc_evidence.json" <<'PY'
import json
import sys

observation = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
assert observation["schema"] == "qge.moonlab_qae_observation_circuit.v0"
assert observation["status"] == "qae_observation_zero_ready_grover_schedule_required"
assert observation["semantic_scope"] == "bernoulli_lift_qae_power_zero_observation"
assert observation["moonlab_control_plane"]["control_plane_executable"] is True
assert observation["resource_estimate"]["logical_qubits"] <= 32
assert observation["resource_estimate"]["gate_count"] > 0
assert observation["state_preparation"]["invalid_candidate_probability"] == 0.0
assert observation["claim_posture"]["candidate_state_preparation_transpiled"] is True
assert observation["claim_posture"]["power_zero_observation_transpiled"] is True
assert observation["claim_posture"]["full_qae_oracle_transpiled"] is False
assert icc["runtime_backend"] == "qge_moonlab_qae_observation_transpile"
assert icc["candidate_state_preparation_transpiled"] is True
assert icc["power_zero_observation_transpiled"] is True
assert icc["full_qae_oracle_transpiled"] is False
PY

python3 "$repo_root/tools/qge_moonlab_qae_grover_plan.py" \
  --metrics "$pack_dir/advantage/advantage_metrics.json" \
  --oracle-scene "$pack_dir/oracle/oracle_scene.json" \
  --out "$tmpdir/qae_moonlab_grover_schedule_plan.json" \
  --markdown "$tmpdir/qae_moonlab_grover_schedule_plan.md" \
  --icc-json "$tmpdir/qae_moonlab_grover_schedule_plan_icc_evidence.json" \
  > "$tmpdir/moonlab_grover_plan.stdout"
grep -F 'QGE_MOONLAB_QAE_GROVER_PLAN' "$tmpdir/moonlab_grover_plan.stdout" >/dev/null
grep -F 'QGE_MOONLAB_QAE_GROVER_PLAN_MARKDOWN' "$tmpdir/moonlab_grover_plan.stdout" >/dev/null
grep -F 'QGE_MOONLAB_QAE_GROVER_PLAN_ICC_EVIDENCE' "$tmpdir/moonlab_grover_plan.stdout" >/dev/null
python3 - "$tmpdir/qae_moonlab_grover_schedule_plan.json" "$tmpdir/qae_moonlab_grover_schedule_plan_icc_evidence.json" <<'PY'
import json
import sys

plan = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
assert plan["schema"] == "qge.moonlab_qae_grover_schedule_plan.v0"
assert plan["status"] in {
    "qae_grover_schedule_ready_for_control_plane_submission",
    "qae_grover_schedule_blocked_control_plane_body_limit",
}
assert plan["semantic_scope"] == "bernoulli_lift_qae_grover_schedule_control_plane_plan"
assert plan["moonlab_control_plane"]["ready_observation_count"] >= 1
assert plan["moonlab_control_plane"]["blocked_observation_count"] >= 0
assert plan["observations"][0]["control_plane_executable"] is True
if plan["moonlab_control_plane"]["blocked_observation_count"] > 0:
    blocked = [
        item for item in plan["observations"]
        if not item["control_plane_executable"]
    ]
    assert plan["moonlab_control_plane"]["first_blocked_power"] == blocked[0]["grover_power"]
    assert plan["claim_posture"]["full_mlae_schedule_transpiled"] is False
else:
    assert plan["moonlab_control_plane"]["first_blocked_power"] is None
    assert plan["claim_posture"]["full_mlae_schedule_transpiled"] is True
assert plan["claim_posture"]["power_zero_observation_transpiled"] is True
assert icc["runtime_backend"] == "qge_moonlab_qae_grover_plan"
assert icc["blocked_observation_count"] >= 0
if icc["blocked_observation_count"] > 0:
    assert icc["first_blocked_power"] >= 1
    assert icc["full_qae_oracle_transpiled"] is False
else:
    assert icc["first_blocked_power"] is None
    assert icc["full_qae_oracle_transpiled"] is True
PY

python3 "$repo_root/tools/qge_moonlab_job_runner.py" \
  "$pack_dir/resource/qge_moonlab_job_specs.json" \
  --out "$tmpdir/qge_moonlab_job_results.json" \
  --expect "$pack_dir/resource/qge_moonlab_job_results.json" \
  --plan-out "$tmpdir/qge_moonlab_replay_plan.json" \
  --submission-out "$tmpdir/qge_moonlab_submission_packet.json" \
  > "$tmpdir/moonlab_job_runner.stdout"
grep -F 'QGE_MOONLAB_JOB_RESULTS' "$tmpdir/moonlab_job_runner.stdout" >/dev/null
grep -F 'QGE_MOONLAB_EXPECTED_RESULTS_MATCH' "$tmpdir/moonlab_job_runner.stdout" >/dev/null
grep -F 'QGE_MOONLAB_REPLAY_PLAN' "$tmpdir/moonlab_job_runner.stdout" >/dev/null
grep -F 'QGE_MOONLAB_SUBMISSION_PACKET' "$tmpdir/moonlab_job_runner.stdout" >/dev/null
python3 - "$tmpdir/qge_moonlab_job_results.json" "$tmpdir/qge_moonlab_replay_plan.json" "$tmpdir/qge_moonlab_submission_packet.json" "$pack_dir/publication_manifest.json" <<'PY'
import json
import sys

results = json.load(open(sys.argv[1], encoding="utf-8"))
plan = json.load(open(sys.argv[2], encoding="utf-8"))
submission = json.load(open(sys.argv[3], encoding="utf-8"))
manifest = json.load(open(sys.argv[4], encoding="utf-8"))
summary = manifest["advantage_summary"]["moonlab_job_results_summary"]
assert results["schema"] == "qge.moonlab_job_results.v0"
assert results["completed_simulator_job_count"] >= 2
assert results["hardware_submitted_job_count"] == 0
assert results["completed_simulator_job_count"] == summary["completed_simulator_job_count"]
assert results["blocked_job_count"] == summary["blocked_job_count"]
assert plan["schema"] == "qge.moonlab_replay_plan.v0"
assert plan["selected_job_count"] == manifest["advantage_summary"]["moonlab_job_specs_summary"]["selected_job_count"]
assert plan["hardware_submitted_job_count"] == 0
assert "--expect" in plan["pack_validation"]["verify_results_command"]
assert submission["schema"] == "qge.moonlab_submission_packet.v0"
assert submission["hardware_candidate_job_count"] == 1
assert submission["ready_candidate_count"] == 1
assert submission["candidate_jobs"][0]["submission_status"] == "ready_for_hardware_submission_metadata"
PY

python3 "$repo_root/tools/qge_moonlab_submission_bundle.py" \
  "$pack_dir/resource/qge_moonlab_submission_packet.json" \
  --out "$tmpdir/qge_moonlab_submission_bundle.json" \
  --markdown "$tmpdir/qge_moonlab_submission_bundle.md" \
  --icc-json "$tmpdir/qge_moonlab_submission_bundle_icc_evidence.json" \
  > "$tmpdir/moonlab_submission_bundle.stdout"
grep -F 'QGE_MOONLAB_SUBMISSION_BUNDLE' "$tmpdir/moonlab_submission_bundle.stdout" >/dev/null
grep -F 'QGE_MOONLAB_SUBMISSION_BUNDLE_MARKDOWN' "$tmpdir/moonlab_submission_bundle.stdout" >/dev/null
grep -F 'QGE_MOONLAB_SUBMISSION_BUNDLE_ICC_EVIDENCE' "$tmpdir/moonlab_submission_bundle.stdout" >/dev/null
python3 - "$tmpdir/qge_moonlab_submission_bundle.json" "$tmpdir/qge_moonlab_submission_bundle_icc_evidence.json" "$pack_dir/publication_manifest.json" <<'PY'
import json
import sys

bundle = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
manifest = json.load(open(sys.argv[3], encoding="utf-8"))
summary = manifest["advantage_summary"]["moonlab_submission_bundle_summary"]
assert bundle["schema"] == "qge.moonlab_submission_bundle.v0"
assert bundle["status"] == summary["status"]
assert bundle["status"] == "ready_for_control_plane_submission"
assert bundle["ready_for_control_plane_submission_count"] == 1
assert bundle["calibration_payload_ready_count"] == 1
assert bundle["oracle_kernel_ready_count"] == 1
assert bundle["qae_observation_ready_count"] == 1
assert bundle["grover_schedule_ready_count"] == 1
assert bundle["transpilation_required_count"] == 0
assert bundle["hardware_submission_directly_executable"] is True
assert bundle["control_plane_payload_directly_executable"] is True
assert bundle["oracle_kernel_directly_executable"] is True
assert bundle["qae_observation_directly_executable"] is True
assert bundle["candidate_jobs"][0]["qae_circuit_check"]["format"] == "qge_abstract_qae_circuit_v0"
assert bundle["candidate_jobs"][0]["moonlab_qae_payload_check"]["semantic_scope"] == "mlae_observation_distribution_payload"
assert bundle["candidate_jobs"][0]["moonlab_qae_oracle_kernel_check"]["semantic_scope"] == "bernoulli_lift_qf_oracle_kernel"
assert bundle["candidate_jobs"][0]["moonlab_qae_observation_zero_check"]["semantic_scope"] == "bernoulli_lift_qae_power_zero_observation"
assert bundle["candidate_jobs"][0]["moonlab_qae_grover_schedule_plan_check"]["semantic_scope"] == "bernoulli_lift_qae_grover_schedule_control_plane_plan"
assert icc["runtime_backend"] == "qge_moonlab_submission_bundle"
assert icc["submission_bundle_status"] == bundle["status"]
assert icc["hardware_submission_directly_executable"] is True
assert icc["control_plane_payload_directly_executable"] is True
assert icc["oracle_kernel_directly_executable"] is True
assert icc["qae_observation_directly_executable"] is True
PY

python3 "$repo_root/tools/qge_moonlab_hardware_ingest.py" \
  "$pack_dir/resource/qge_moonlab_submission_packet.json" \
  --template-out "$tmpdir/qge_moonlab_hardware_record.template.json" \
  > "$tmpdir/moonlab_hardware_template.stdout"
grep -F 'QGE_MOONLAB_HARDWARE_RECORD_TEMPLATE' "$tmpdir/moonlab_hardware_template.stdout" >/dev/null
python3 - "$tmpdir/qge_moonlab_hardware_record.template.json" "$pack_dir/publication_manifest.json" <<'PY'
import json
import sys

template = json.load(open(sys.argv[1], encoding="utf-8"))
manifest = json.load(open(sys.argv[2], encoding="utf-8"))
summary = manifest["advantage_summary"]["moonlab_hardware_record_template_summary"]
assert template["schema"] == "qge.moonlab_hardware_record_template.v0"
assert template["record_schema"] == "qge.moonlab_hardware_record.v0"
assert template["record"]["schema"] == "qge.moonlab_hardware_record.v0"
assert template["record"]["backend_kind"] == "moonlab_hardware"
assert template["record"]["hardware_quantum_advantage_claimed"] is False
assert template["record"]["whole_game_hardware_execution_claimed"] is False
assert template["record"]["dense_70000_qubit_state_claimed"] is False
assert template["job_id"] == summary["job_id"]
assert template["candidate_digest"] == summary["candidate_digest"]
PY

python3 "$repo_root/tools/qge_moonlab_full_game_plan.py" \
  "$pack_dir" \
  --out "$tmpdir/qge_moonlab_full_game_plan.json" \
  --markdown "$tmpdir/qge_moonlab_full_game_plan.md" \
  --icc-json "$tmpdir/qge_moonlab_full_game_plan_icc_evidence.json" \
  > "$tmpdir/moonlab_full_game_plan.stdout"
grep -F 'QGE_MOONLAB_FULL_GAME_PLAN' "$tmpdir/moonlab_full_game_plan.stdout" >/dev/null
grep -F 'QGE_MOONLAB_FULL_GAME_PLAN_MARKDOWN' "$tmpdir/moonlab_full_game_plan.stdout" >/dev/null
grep -F 'QGE_MOONLAB_FULL_GAME_PLAN_ICC_EVIDENCE' "$tmpdir/moonlab_full_game_plan.stdout" >/dev/null
python3 - "$tmpdir/qge_moonlab_full_game_plan.json" "$tmpdir/qge_moonlab_full_game_plan_icc_evidence.json" "$pack_dir/publication_manifest.json" <<'PY'
import json
import sys

plan = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
manifest = json.load(open(sys.argv[3], encoding="utf-8"))
summary = manifest["advantage_summary"]["moonlab_full_game_plan_summary"]
assert plan["schema"] == "qge.moonlab_full_game_deployment_plan.v0"
assert plan["status"] == summary["status"]
assert plan["asset_unavailable_map_count"] == summary["asset_unavailable_map_count"]
assert plan["claim_posture"]["whole_game_moonlab_deployment_claimed"] is False
assert icc["runtime_backend"] == "qge_moonlab_full_game_plan"
assert icc["deployment_status"] == plan["status"]
assert icc["whole_game_moonlab_deployment_claimed"] is False
PY

python3 "$repo_root/tools/qge_moonlab_deployment_gate.py" \
  "$pack_dir" \
  --out "$tmpdir/qge_moonlab_deployment_gate.json" \
  --markdown "$tmpdir/qge_moonlab_deployment_gate.md" \
  --icc-json "$tmpdir/qge_moonlab_deployment_gate_icc_evidence.json" \
  > "$tmpdir/moonlab_deployment_gate.stdout"
grep -F 'QGE_MOONLAB_DEPLOYMENT_GATE' "$tmpdir/moonlab_deployment_gate.stdout" >/dev/null
grep -F 'QGE_MOONLAB_DEPLOYMENT_GATE_MARKDOWN' "$tmpdir/moonlab_deployment_gate.stdout" >/dev/null
grep -F 'QGE_MOONLAB_DEPLOYMENT_GATE_ICC_EVIDENCE' "$tmpdir/moonlab_deployment_gate.stdout" >/dev/null
python3 - "$tmpdir/qge_moonlab_deployment_gate.json" "$tmpdir/qge_moonlab_deployment_gate_icc_evidence.json" "$pack_dir/publication_manifest.json" <<'PY'
import json
import sys

gate = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
manifest = json.load(open(sys.argv[3], encoding="utf-8"))
summary = manifest["advantage_summary"]["moonlab_deployment_gate_summary"]
assert gate["schema"] == "qge.moonlab_deployment_gate.v0"
assert gate["status"] == summary["status"]
assert gate["whole_game_moonlab_deployment_claim_allowed"] is False
assert gate["whole_game_hardware_execution_claim_allowed"] is False
assert gate["hardware_quantum_advantage_claim_allowed"] is False
assert gate["dense_70000_qubit_state_claim_allowed"] is False
assert len(gate["blockers"]) == gate["blocker_count"]
assert gate["asset_remediation"]["registered_asset_install_script"].endswith("resource/install_registered_assets.sh")
assert gate["summary"]["post_install_capture_queue_command_present"] is True
assert "qge_full_game_capture_queue.py" in gate["summary"]["post_install_capture_queue_command"]
assert icc["runtime_backend"] == "qge_moonlab_deployment_gate"
assert icc["gate_status"] == gate["status"]
assert icc["whole_game_moonlab_deployment_claim_allowed"] is False
assert icc["registered_asset_install_script"].endswith("resource/install_registered_assets.sh")
assert icc["post_install_capture_queue_command_present"] is True
PY

python3 "$repo_root/tools/qge_asset_requirements.py" \
  --asset-root "$tmpdir/missing-id1" \
  --json "$tmpdir/qge_asset_requirements.json" \
  --markdown "$tmpdir/qge_asset_requirements.md" \
  --icc-json "$tmpdir/qge_asset_requirements_icc_evidence.json" \
  > "$tmpdir/asset_requirements.stdout"
grep -F 'QGE_ASSET_REQUIREMENTS' "$tmpdir/asset_requirements.stdout" >/dev/null
grep -F 'QGE_ASSET_REQUIREMENTS_MARKDOWN' "$tmpdir/asset_requirements.stdout" >/dev/null
grep -F 'QGE_ASSET_REQUIREMENTS_ICC_EVIDENCE' "$tmpdir/asset_requirements.stdout" >/dev/null
python3 - "$tmpdir/qge_asset_requirements.json" "$tmpdir/qge_asset_requirements_icc_evidence.json" <<'PY'
import json
import sys

requirements = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
assert requirements["schema"] == "qge.asset_requirements.v0"
assert requirements["status"] == "blocked_missing_registered_assets"
assert requirements["missing_map_count"] == 32
assert "maps/e1m1.bsp" in requirements["missing_required_entries"]
assert requirements["claim_posture"]["whole_game_moonlab_deployment_claimed"] is False
assert icc["runtime_backend"] == "qge_asset_requirements"
assert icc["asset_requirement_status"] == "blocked_missing_registered_assets"
PY

if python3 "$repo_root/tools/qge_image_metrics.py" --check-deps > "$tmpdir/image_deps.stdout" 2> "$tmpdir/image_deps.stderr"; then
  grep -F 'QGE_IMAGE_METRICS_DEPS_OK' "$tmpdir/image_deps.stdout" >/dev/null

  python3 - "$metrics_dir/reference.ppm" "$metrics_dir/candidate.ppm" <<'PY'
import sys
from pathlib import Path

data = b"P6\n2 2\n255\n" + bytes([
    0, 0, 0,
    255, 0, 0,
    0, 255, 0,
    0, 0, 255,
])
Path(sys.argv[1]).write_bytes(data)
Path(sys.argv[2]).write_bytes(data)
PY

  python3 "$repo_root/tools/qge_image_metrics.py" \
    --reference "$metrics_dir/reference.ppm" \
    --candidate "$metrics_dir/candidate.ppm" \
    --json "$metrics_dir/metrics.json" \
    --markdown "$metrics_dir/metrics.md" > "$tmpdir/image_metrics.stdout"

  python3 - "$metrics_dir/metrics.json" "$metrics_dir/metrics.md" <<'PY'
import json
import sys

metrics = json.load(open(sys.argv[1], encoding="utf-8"))
markdown = open(sys.argv[2], encoding="utf-8").read()
assert metrics["width"] == 2
assert metrics["height"] == 2
assert metrics["mae_rgb"] == 0.0
assert metrics["psnr_is_infinite"] is True
assert metrics["edge"]["edge_f1"] == 1.0
assert "# QGE Image Metrics" in markdown
assert "| PSNR dB | inf |" in markdown
PY
else
  grep -F 'requires numpy and Pillow for image metrics' "$tmpdir/image_deps.stderr" >/dev/null
  grep -F 'missing:' "$tmpdir/image_deps.stderr" >/dev/null
fi

echo "QGE publication tools contract: PASSED"
