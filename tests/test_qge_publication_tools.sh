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
assert manifest["artifacts"]["resource"]["envelope"]["exists"] is True
assert manifest["artifacts"]["resource"]["full_game_map_coverage"]["exists"] is True
assert manifest["artifacts"]["resource"]["asset_inventory"]["exists"] is True
assert manifest["artifacts"]["resource"]["asset_inventory_icc_evidence"]["exists"] is True
assert manifest["artifacts"]["resource"]["asset_requirements"]["exists"] is True
assert manifest["artifacts"]["resource"]["asset_requirements_markdown"]["exists"] is True
assert manifest["artifacts"]["resource"]["asset_requirements_icc_evidence"]["exists"] is True
assert manifest["artifacts"]["resource"]["native_backend_boundary"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_job_specs"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_job_results"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_replay_plan"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_submission_packet"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_hardware_record_template"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_full_game_plan"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_full_game_plan_markdown"]["exists"] is True
assert manifest["artifacts"]["resource"]["moonlab_full_game_plan_icc_evidence"]["exists"] is True
assert manifest["advantage_summary"]["resource_envelope_summary"]["whole_game_hardware_execution_claimed"] is False
assert manifest["advantage_summary"]["full_game_map_coverage_summary"]["status"] == "partial"
assert manifest["advantage_summary"]["full_game_map_coverage_summary"]["target_map_count"] == 32
assert manifest["advantage_summary"]["full_game_map_coverage_summary"]["covered_map_count"] == 0
assert manifest["advantage_summary"]["asset_inventory_summary"]["missing_map_count"] == 32
assert manifest["advantage_summary"]["asset_inventory_summary"]["full_game_asset_ready"] is False
assert manifest["advantage_summary"]["asset_requirements_summary"]["schema"] == "qge.asset_requirements.v0"
assert manifest["advantage_summary"]["asset_requirements_summary"]["status"] == "blocked_missing_registered_assets"
assert manifest["advantage_summary"]["asset_requirements_summary"]["missing_map_count"] == 32
assert manifest["advantage_summary"]["asset_requirements_summary"]["asset_requirements_satisfied"] is False
assert manifest["advantage_summary"]["native_backend_boundary_summary"]["status"] == "pass"
assert manifest["advantage_summary"]["native_backend_boundary_summary"]["passed_target_count"] == 3
assert manifest["advantage_summary"]["moonlab_job_specs_summary"]["hardware_candidate_job_count"] == 1
assert manifest["advantage_summary"]["moonlab_job_results_summary"]["completed_simulator_job_count"] >= 2
assert manifest["advantage_summary"]["moonlab_job_results_summary"]["hardware_submitted_job_count"] == 0
assert manifest["advantage_summary"]["moonlab_replay_plan_summary"]["schema"] == "qge.moonlab_replay_plan.v0"
assert manifest["advantage_summary"]["moonlab_submission_packet_summary"]["schema"] == "qge.moonlab_submission_packet.v0"
assert manifest["advantage_summary"]["moonlab_submission_packet_summary"]["ready_candidate_count"] == 1
assert manifest["advantage_summary"]["moonlab_hardware_record_template_summary"]["schema"] == "qge.moonlab_hardware_record_template.v0"
assert manifest["advantage_summary"]["moonlab_hardware_record_template_summary"]["record_schema"] == "qge.moonlab_hardware_record.v0"
assert manifest["advantage_summary"]["moonlab_full_game_plan_summary"]["schema"] == "qge.moonlab_full_game_deployment_plan.v0"
assert manifest["advantage_summary"]["moonlab_full_game_plan_summary"]["status"] == "blocked_asset_unavailable"
assert manifest["advantage_summary"]["moonlab_full_game_plan_summary"]["asset_unavailable_map_count"] == 32
assert manifest["advantage_summary"]["moonlab_full_game_plan_summary"]["whole_game_moonlab_deployment_claimed"] is False
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
assert icc["full_game_asset_ready"] is False
assert icc["asset_requirements_file"].endswith("resource/qge_asset_requirements.json")
assert icc["asset_requirements_markdown_file"].endswith("resource/qge_asset_requirements.md")
assert icc["asset_requirements_icc_evidence_file"].endswith("resource/qge_asset_requirements_icc_evidence.json")
assert icc["asset_requirements_schema"] == "qge.asset_requirements.v0"
assert icc["asset_requirement_status"] == "blocked_missing_registered_assets"
assert icc["asset_requirements_missing_map_count"] == 32
assert icc["asset_requirements_satisfied"] is False
assert icc["native_backend_boundary_file"].endswith("resource/qge_native_backend_boundary.json")
assert icc["native_backend_boundary_status"] == "pass"
assert icc["moonlab_job_specs_file"].endswith("resource/qge_moonlab_job_specs.json")
assert icc["moonlab_job_results_file"].endswith("resource/qge_moonlab_job_results.json")
assert icc["moonlab_replay_plan_file"].endswith("resource/qge_moonlab_replay_plan.json")
assert icc["moonlab_replay_plan_schema"] == "qge.moonlab_replay_plan.v0"
assert icc["moonlab_submission_packet_file"].endswith("resource/qge_moonlab_submission_packet.json")
assert icc["moonlab_submission_packet_schema"] == "qge.moonlab_submission_packet.v0"
assert icc["moonlab_submission_ready_candidate_count"] == 1
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
assert icc["moonlab_hardware_candidate_job_count"] == 1
assert icc["moonlab_completed_simulator_job_count"] >= 2
assert icc["moonlab_hardware_submitted_job_count"] == 0
assert icc["whole_game_hardware_execution_claimed"] is False
assert icc["vanilla_icc_evidence_file"].endswith("vanilla/qge_vanilla_icc_evidence.json")
assert icc["status"] == "success"
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
