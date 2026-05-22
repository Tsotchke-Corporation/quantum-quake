#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/qge-vanilla-matrix-perf.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

cat > "$tmpdir/metrics.json" <<'JSON'
{
  "mae_rgb_normalized": 0.01,
  "rmse_rgb": 1.0,
  "psnr_db": 42.0,
  "luma_ssim_global": 0.99,
  "histogram_intersection_rgb": 0.98,
  "edge": {
    "edge_precision": 1.0,
    "edge_recall": 1.0,
    "edge_f1": 1.0,
    "edge_jaccard": 1.0
  }
}
JSON

for mode in classic quantum; do
  printf 'png\n' > "$tmpdir/$mode.png"
  cat > "$tmpdir/$mode.README.txt" <<'EOF'
Frames captured: 1
Map: e1m1
EOF
  cat > "$tmpdir/$mode.agent_stream.json" <<'JSON'
{
  "status": "complete",
  "frames_requested": 1,
  "frames_captured": 1,
  "trace_requested": 0,
  "trace_status": "not_requested",
  "trace_bytes": 0,
  "run": {
    "status": "ok",
    "success": 1,
    "startup_issue": "",
    "process_status": 0,
    "timed_out": 0
  },
  "performance": {
    "status": "complete",
    "summary_file": "agent_stream/performance/qge_perf_summary.json",
    "icc_evidence_file": "agent_stream/performance/qge_perf_icc_evidence.json"
  }
}
JSON
  : > "$tmpdir/$mode.agent_events.ndjson"
  : > "$tmpdir/$mode.agent_icc_evidence.jsonl"
done

cat > "$tmpdir/classic.log" <<'LOG'
QGE render frame=3 mode=classic owner=classic_3d classic3d=0 suppressed3d=0 res=1024 time=12.0 encode=1.0 setup=0.0 raster=4.0 fdwt=0.0 dwt=0.0 convert=2.0 blit=5.0 reuse=0 interval=8 coeffs=0 snapshot=117 snapshot_miss=0 texcache=0/0 lightcache=0/0 poly=0 tris=0 edgefills=0 microfill=0 culled=0 surrogate=0 micro=0 clipped=0 fallback=0 encoded=0 material=0 edicts=1 alias=1 sprites=0 sbill=0 emesh=0 ecoeff=0 viewmodel=1 entity_miss=0 particles=0 pcoeff=0 gates=0 shots=0 readout=0.0 edgeq=0.0 ggain=0.0 egain=0.0 nonzero=1/1
QGE: Average quantum render time: 8.00 ms (24 frames)
LOG

cat > "$tmpdir/quantum.log" <<'LOG'
QGE render frame=0 mode=primary owner=qge_3d classic3d=0 suppressed3d=9 classic2d=1 suppressed2d=0 res=1024 time=26.0 encode=12.0 setup=0.0 raster=9.0 fdwt=4.0 dwt=3.0 convert=3.0 blit=8.0 reuse=0 interval=8 coeffs=192495 snapshot=117 snapshot_miss=0 texcache=234/0 lightcache=234/0 poly=117 tris=348 edgefills=0 microfill=0 culled=0 surrogate=0 micro=0 clipped=0 fallback=0 encoded=117 material=117 edicts=1 alias=1 sprites=0 sbill=0 emesh=0 ecoeff=4 viewmodel=1 entity_miss=0 particles=0 pcoeff=0 own_world=117 own_textures=117 own_lightmaps=117 own_entities=1 own_sprites=1 own_particles=1 own_viewmodel=1 own_hud=0 own_console=1 gate_kernel=1 gates=26 shots=64 primary_fb=1 native_idwt=1 cpu_idwt=0 idwt_backend=native readout=0.953 edgeq=0.031 ggain=1.054 egain=0.727 nonzero=448991/1048576 fallback_reason=classic2d_unowned
QGE render frame=3 mode=primary owner=qge_3d classic3d=0 suppressed3d=9 classic2d=0 suppressed2d=4 res=1024 time=27.0 encode=13.0 setup=0.0 raster=9.0 fdwt=4.0 dwt=3.0 convert=3.0 blit=8.0 reuse=0 interval=8 coeffs=192495 snapshot=117 snapshot_miss=0 texcache=234/0 lightcache=234/0 poly=117 tris=348 edgefills=0 microfill=0 culled=0 surrogate=0 micro=0 clipped=0 fallback=0 encoded=117 material=117 edicts=1 alias=1 sprites=0 sbill=0 emesh=0 ecoeff=4 viewmodel=1 entity_miss=0 particles=0 pcoeff=0 own_world=117 own_textures=117 own_lightmaps=117 own_entities=1 own_sprites=1 own_particles=1 own_viewmodel=1 own_hud=1 own_console=1 gate_kernel=1 gates=26 shots=64 primary_fb=1 native_idwt=1 cpu_idwt=0 idwt_backend=native readout=0.953 edgeq=0.031 ggain=1.054 egain=0.727 nonzero=448991/1048576
QGE: Average quantum render time: 16.27 ms (24 frames)
LOG

cat > "$tmpdir/quantum.qge_trace_summary.json" <<'JSON'
{
  "records": {
    "ai_decision": 2,
    "entropy": 2,
    "measurement": 2
  },
  "runtime_evidence": {
    "single_trace_ready": true,
    "render": {
      "sparse_dwt_count": 1,
      "native_bridge_count": 1,
      "cpu_idwt_count": 0,
      "idwt_backend": "native"
    },
    "ai": {
      "ready": true,
      "decision_count": 2,
      "record_count": 2
    },
    "audio": {
      "ready": true,
      "source_spatial_count": 1,
      "source_frame_count": 1
    },
    "visibility": {
      "ready": true,
      "authority_gate_count": 1,
      "authority_apply_count": 1,
      "clean_frames": 8
    },
    "projectile": {
      "ready": true,
      "authority_gate_count": 1,
      "active_projectiles": 1,
      "writeback_decision_count": 1,
      "off_reason": "none"
    }
  }
}
JSON

python3 "$repo_root/tools/qge_perf_summary.py" \
  "$tmpdir/classic.log" \
  --out "$tmpdir/classic.qge_perf_summary.json" \
  --icc-out "$tmpdir/classic.qge_perf_icc_evidence.json" \
  --max-average-ms 20 \
  --max-render-ms 40 > "$tmpdir/classic.perf.txt"

python3 "$repo_root/tools/qge_perf_summary.py" \
  "$tmpdir/quantum.log" \
  --out "$tmpdir/quantum.qge_perf_summary.json" \
  --icc-out "$tmpdir/quantum.qge_perf_icc_evidence.json" \
  --max-average-ms 20 \
  --max-render-ms 40 > "$tmpdir/quantum.perf.txt"

python3 "$repo_root/tools/qge_vanilla_capture_matrix.py" "$tmpdir" \
  --out "$tmpdir/vanilla_capture_matrix.json" \
  --icc-out "$tmpdir/qge_vanilla_icc_evidence.json"

python3 - "$tmpdir/vanilla_capture_matrix.json" "$tmpdir/qge_vanilla_icc_evidence.json" <<'PY'
import json
import sys

matrix = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
summary = matrix["conformance_summary"]
assert summary["performance_sidecars_success"] is True
assert summary["qge_performance_status"] == "pass"
assert summary["qge_performance_engine_average_quantum_ms_max"] == 16.27
assert summary["qge_performance_render_time_ms_max"] == 27.0
assert summary["qge_classic_output_hidden"] is True
assert summary["qge_classic_output_seen_any_frame"] is True
assert summary["classic2d_count"] == 1
assert summary["classic2d_latest"] == 0
assert summary["qge_asset_ownership_complete"] is True
assert summary["qge_asset_ownership"]["own_world"] == 117
assert summary["moonlab_authority_ready"] is True
assert summary["moonlab_authority_blockers"] == []
assert summary["ready_for_complete_claim"] is True
assert icc["performance_sidecars_success"] is True
assert icc["moonlab_authority_ready"] is True
assert icc["qge_performance_status"] == "pass"
assert icc["status"] == "success"
PY

if python3 "$repo_root/tools/qge_perf_summary.py" \
  "$tmpdir/quantum.log" \
  --out "$tmpdir/quantum.qge_perf_summary.json" \
  --icc-out "$tmpdir/quantum.qge_perf_icc_evidence.json" \
  --max-average-ms 10 \
  --max-render-ms 40 > "$tmpdir/quantum.blocked.perf.txt"; then
  echo "expected blocked quantum performance sidecar" >&2
  exit 1
fi

python3 "$repo_root/tools/qge_vanilla_capture_matrix.py" "$tmpdir" \
  --out "$tmpdir/blocked_vanilla_capture_matrix.json" \
  --icc-out "$tmpdir/blocked_qge_vanilla_icc_evidence.json"

python3 - "$tmpdir/blocked_vanilla_capture_matrix.json" "$tmpdir/blocked_qge_vanilla_icc_evidence.json" <<'PY'
import json
import sys

matrix = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
summary = matrix["conformance_summary"]
assert summary["performance_sidecars_success"] is False
assert summary["qge_performance_status"] == "blocked"
assert summary["qge_performance_threshold_failures"][0]["metric"] == "engine_average_quantum_ms"
assert summary["ready_for_complete_claim"] is False
assert icc["performance_sidecars_success"] is False
assert icc["status"] == "blocked"
PY

echo "QGE vanilla matrix performance contract: PASSED"
