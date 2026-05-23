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
write_json(capture / "qge_perf_summary.json", {
    "status": "pass",
    "aggregate": {
        "engine_average_quantum_ms_max": 12.5,
        "render_time_ms_max": 22.0,
        "threshold_failures": [],
        "metric_evidence_present": True,
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
assert manifest["artifacts"]["vanilla"]["icc_evidence"]["packed"]["exists"] is True
assert icc["completion_reason"] == "qge_publication_artifact_pack_complete"
assert icc["runtime_backend"] == "qge_publication_pack"
assert icc["publication_ready_for_complete_claim"] is True
assert icc["vanilla_icc_evidence_file"].endswith("vanilla/qge_vanilla_icc_evidence.json")
assert icc["status"] == "success"
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
