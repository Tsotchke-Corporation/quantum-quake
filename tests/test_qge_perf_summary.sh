#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/qge-perf-summary.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

log_file="$tmpdir/quantum_quake.log"
summary_json="$tmpdir/summary.json"
icc_json="$tmpdir/icc.json"
fail_json="$tmpdir/fail-summary.json"
fail_icc_json="$tmpdir/fail-icc.json"

cat > "$log_file" <<'LOG'
QGE backend gate phase=init backend=Metal status=capable, inactive native=1 active=0 flags=0x3d path=sparse_dwt_cpu_render_path reason=native_backend_available_sparse_dwt_cpu_path_pending_renderer_bridge probe=metal_system_device_available
QGE: Backend gate phase=render_bridge backend=Metal status=active acceleration native=1 active=1 flags=0x17 path=native_sparse_dwt_render_bridge reason=native_sparse_dwt_render_bridge_active probe=metal_system_device_available
QGE: Runtime backend probe target=qge_metal_init_common phase=create backend=Metal path=native_sparse_dwt_render_bridge result=active dense_amplitudes=0 qubits=28 screen_res=1024
QGE: Runtime backend probe target=qge_context_get_or_create_render_acceleration phase=create backend=Metal path=native_sparse_dwt_render_bridge result=created native=1 active=1 screen_res=1024 reason=native_sparse_dwt_render_bridge_active probe=metal_system_device_available
QGE: Runtime backend probe target=qge_dwt_render phase=idwt backend=Metal path=native_sparse_dwt_render_bridge result=native native_render_backend=native native=1 active=1 screen_res=1024 levels=6 gpu_reconstruct=1 mode=0 active_coeffs=192495 reason=native_sparse_dwt_render_bridge_active
QGE render frame=3 mode=primary owner=qge_3d classic3d=0 suppressed3d=9 res=1024 time=27.0 encode=13.0 setup=0.0 raster=9.0 fdwt=4.0 dwt=3.0 convert=3.0 blit=8.0 reuse=0 interval=8 coeffs=192495 snapshot=117 snapshot_miss=0 texcache=234/0 lightcache=234/0 poly=117 tris=348 edgefills=0 microfill=0 culled=0 surrogate=0 micro=0 clipped=0 fallback=0 encoded=117 material=117 edicts=1 alias=1 sprites=0 sbill=0 emesh=0 ecoeff=4 viewmodel=1 entity_miss=0 particles=0 pcoeff=0 gates=26 shots=64 readout=0.953 edgeq=0.031 ggain=1.054 egain=0.727 native_idwt=3 idwt_fallback=0 cpu_idwt=0 idwt_backend=native idwt_path=native_sparse_dwt_render_bridge idwt_reason=native_sparse_dwt_render_bridge_active nonzero=448991/1048576
QGE: Average quantum render time: 16.27 ms (24 frames)
QGE: Backend gate phase=shutdown backend=Metal status=active acceleration native=1 active=1 flags=0x17 path=native_sparse_dwt_render_bridge reason=native_sparse_dwt_render_bridge_active probe=metal_system_device_available
LOG

python3 "$repo_root/tools/qge_perf_summary.py" \
  "$tmpdir" \
  --json \
  --out "$summary_json" \
  --icc-out "$icc_json" \
  --max-average-ms 20 \
  --max-render-ms 30 > "$tmpdir/stdout.json"

python3 - "$summary_json" "$icc_json" <<'PY'
import json
import sys

summary = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
assert summary["status"] == "pass"
assert summary["aggregate"]["metric_evidence_present"] is True
assert summary["aggregate"]["engine_average_quantum_ms_max"] == 16.27
assert summary["aggregate"]["render_time_ms_max"] == 27.0
assert summary["logs"][0]["render_frame_count"] == 1
assert summary["logs"][0]["last_render_frame"]["owner"] == "qge_3d"
assert summary["logs"][0]["last_render_frame"]["idwt_backend"] == "native"
assert summary["logs"][0]["native_idwt"]["sum"] == 3
assert summary["logs"][0]["idwt_fallback"]["sum"] == 0
assert summary["logs"][0]["cpu_idwt"]["sum"] == 0
assert summary["logs"][0]["idwt_backend"]["last"] == "native"
assert summary["logs"][0]["idwt_backend"]["values"] == ["native"]
assert summary["logs"][0]["backend_gate_init_event"]["path"] == "sparse_dwt_cpu_render_path"
assert summary["logs"][0]["backend_gate_render_bridge_event"]["path"] == "native_sparse_dwt_render_bridge"
assert summary["logs"][0]["backend_gate_shutdown_event"]["active"] == 1
assert summary["logs"][0]["backend_gate_event_count"] == 3
assert summary["logs"][0]["backend_gate_backends"] == ["Metal"]
assert summary["logs"][0]["backend_gate_paths"] == ["native_sparse_dwt_render_bridge", "sparse_dwt_cpu_render_path"]
assert summary["logs"][0]["backend_gate_render_bridge_active"] is True
assert summary["logs"][0]["runtime_backend_probe_event_count"] == 3
assert summary["logs"][0]["runtime_backend_probe_targets"] == [
    "qge_context_get_or_create_render_acceleration",
    "qge_dwt_render",
    "qge_metal_init_common",
]
assert summary["logs"][0]["runtime_backend_probe_paths"] == ["native_sparse_dwt_render_bridge"]
assert summary["aggregate"]["native_idwt_sum"] == 3
assert summary["aggregate"]["idwt_fallback_sum"] == 0
assert summary["aggregate"]["cpu_idwt_sum"] == 0
assert summary["aggregate"]["idwt_backend_values"] == ["native"]
assert summary["aggregate"]["backend_gate_event_count"] == 3
assert summary["aggregate"]["backend_gate_backends"] == ["Metal"]
assert summary["aggregate"]["backend_gate_render_bridge_paths"] == ["native_sparse_dwt_render_bridge"]
assert summary["aggregate"]["backend_gate_render_bridge_active"] is True
assert summary["aggregate"]["runtime_backend_probe_event_count"] == 3
assert summary["aggregate"]["runtime_backend_probe_targets"] == [
    "qge_context_get_or_create_render_acceleration",
    "qge_dwt_render",
    "qge_metal_init_common",
]
assert summary["logs"][0]["components"]["encode"]["max_ms"] == 13.0
assert icc["completion_reason"] == "qge_runtime_performance_complete"
assert icc["native_idwt_sum"] == 3
assert icc["idwt_fallback_sum"] == 0
assert icc["cpu_idwt_sum"] == 0
assert icc["idwt_backend_values"] == ["native"]
assert icc["backend_gate_event_count"] == 3
assert icc["backend_gate_render_bridge_paths"] == ["native_sparse_dwt_render_bridge"]
assert icc["backend_gate_render_bridge_active"] is True
assert icc["runtime_backend_probe_event_count"] == 3
assert icc["runtime_backend_probe_targets"] == [
    "qge_context_get_or_create_render_acceleration",
    "qge_dwt_render",
    "qge_metal_init_common",
]
assert icc["failure_free"] is True
PY

cpu_log_file="$tmpdir/cpu-quantum_quake.log"
cpu_summary_json="$tmpdir/cpu-summary.json"
cpu_icc_json="$tmpdir/cpu-icc.json"
cat > "$cpu_log_file" <<'LOG'
QGE: Backend gate phase=init backend=Metal status=capable, inactive native=1 active=0 flags=0x3d path=sparse_dwt_cpu_render_path reason=native_backend_available_sparse_dwt_cpu_path_pending_renderer_bridge probe=metal_system_device_available
QGE: Runtime backend probe target=qge_dwt_render phase=idwt backend=Metal path=sparse_dwt_cpu_render_path result=cpu native_render_backend=cpu native=1 active=0 screen_res=512 levels=5 gpu_reconstruct=1 mode=0 active_coeffs=12000 reason=native_backend_available_sparse_dwt_cpu_path_pending_renderer_bridge
QGE render frame=4 mode=primary owner=qge_3d classic3d=0 suppressed3d=9 res=512 time=12.0 encode=5.0 setup=0.0 raster=3.0 fdwt=1.0 dwt=2.0 convert=1.0 blit=1.0 reuse=0 interval=1 coeffs=12000 snapshot=64 snapshot_miss=0 native_idwt=0 idwt_fallback=0 cpu_idwt=3 idwt_backend=cpu idwt_path=sparse_dwt_cpu_render_path idwt_reason=native_backend_available_sparse_dwt_cpu_path_pending_renderer_bridge nonzero=50000/262144
QGE: Average quantum render time: 12.00 ms (1 frames)
QGE backend gate phase=shutdown backend=Metal status=capable, inactive native=1 active=0 flags=0x3d path=sparse_dwt_cpu_render_path reason=native_backend_available_sparse_dwt_cpu_path_pending_renderer_bridge probe=metal_system_device_available
LOG

python3 "$repo_root/tools/qge_perf_summary.py" \
  "$cpu_log_file" \
  --json \
  --out "$cpu_summary_json" \
  --icc-out "$cpu_icc_json" > "$tmpdir/cpu-stdout.json"

python3 - "$cpu_summary_json" "$cpu_icc_json" <<'PY'
import json
import sys

summary = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
assert summary["status"] == "pass"
assert summary["logs"][0]["native_idwt"]["sum"] == 0
assert summary["logs"][0]["idwt_fallback"]["sum"] == 0
assert summary["logs"][0]["cpu_idwt"]["sum"] == 3
assert summary["logs"][0]["idwt_backend"]["last"] == "cpu"
assert summary["logs"][0]["backend_gate_init_event"]["flags_int"] == 0x3D
assert summary["aggregate"]["native_idwt_sum"] == 0
assert summary["aggregate"]["cpu_idwt_sum"] == 3
assert summary["aggregate"]["idwt_backend_values"] == ["cpu"]
assert icc["cpu_idwt_sum"] == 3
assert icc["idwt_backend_values"] == ["cpu"]
PY

if python3 "$repo_root/tools/qge_perf_summary.py" \
  "$log_file" \
  --out "$fail_json" \
  --icc-out "$fail_icc_json" \
  --max-average-ms 10 \
  --max-render-ms 30 > "$tmpdir/fail-stdout.txt"; then
  echo "expected threshold failure" >&2
  exit 1
fi

python3 - "$fail_json" "$fail_icc_json" <<'PY'
import json
import sys

summary = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
assert summary["status"] == "blocked"
assert summary["aggregate"]["metric_evidence_present"] is True
assert summary["aggregate"]["threshold_failures"][0]["metric"] == "engine_average_quantum_ms"
assert icc["completion_reason"] == "qge_runtime_performance_evidence_only"
assert icc["failure_free"] is False
assert icc["status"] == "blocked"
PY

empty_log="$tmpdir/empty.log"
empty_json="$tmpdir/empty-summary.json"
empty_icc_json="$tmpdir/empty-icc.json"
printf '%s\n' 'Quantum Quake console dump without QGE timing' > "$empty_log"

if python3 "$repo_root/tools/qge_perf_summary.py" \
  "$empty_log" \
  --out "$empty_json" \
  --icc-out "$empty_icc_json" > "$tmpdir/empty-stdout.txt"; then
  echo "expected empty timing log failure" >&2
  exit 1
fi

python3 - "$empty_json" "$empty_icc_json" <<'PY'
import json
import sys

summary = json.load(open(sys.argv[1], encoding="utf-8"))
icc = json.load(open(sys.argv[2], encoding="utf-8"))
assert summary["status"] == "blocked"
assert summary["aggregate"]["metric_evidence_present"] is False
assert icc["runtime_evidence_present"] is False
assert icc["failure_free"] is False
PY

echo "QGE performance summary contract: PASSED"
