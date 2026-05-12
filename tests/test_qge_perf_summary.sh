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
QGE: Backend gate phase=init backend=Metal status=capable, inactive native=1 active=0 flags=0x3d path=sparse_dwt_cpu_render_path reason=native_backend_available_sparse_dwt_cpu_path_pending_renderer_bridge probe=metal_system_device_available
QGE render frame=3 mode=primary owner=qge_3d classic3d=0 suppressed3d=9 res=1024 time=27.0 encode=13.0 setup=0.0 raster=9.0 fdwt=4.0 dwt=3.0 convert=3.0 blit=8.0 reuse=0 interval=8 coeffs=192495 snapshot=117 snapshot_miss=0 texcache=234/0 lightcache=234/0 poly=117 tris=348 edgefills=0 microfill=0 culled=0 surrogate=0 micro=0 clipped=0 fallback=0 encoded=117 material=117 edicts=1 alias=1 sprites=0 sbill=0 emesh=0 ecoeff=4 viewmodel=1 entity_miss=0 particles=0 pcoeff=0 gates=26 shots=64 readout=0.953 edgeq=0.031 ggain=1.054 egain=0.727 nonzero=448991/1048576
QGE: Average quantum render time: 16.27 ms (24 frames)
QGE: Backend gate phase=shutdown backend=Metal status=capable, inactive native=1 active=0 flags=0x3d path=sparse_dwt_cpu_render_path reason=native_backend_available_sparse_dwt_cpu_path_pending_renderer_bridge probe=metal_system_device_available
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
assert summary["logs"][0]["components"]["encode"]["max_ms"] == 13.0
assert icc["completion_reason"] == "qge_runtime_performance_complete"
assert icc["failure_free"] is True
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
