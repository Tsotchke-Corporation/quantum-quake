#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

app_bin="$repo_root/QuantumQuake.app/Contents/MacOS/quantum_quake"
basedir="$repo_root/assets"
gamedir="$basedir/id1"

map_name="${QGE_HARNESS_MAP:-start}"
frames="${QGE_HARNESS_FRAMES:-1}"
waits_per_frame="${QGE_HARNESS_WAIT_FRAMES:-90}"
classic_render="${QGE_HARNESS_CLASSIC_RENDER:-0}"
quantum_render="${QGE_HARNESS_QUANTUM_RENDER:-2}"
render_res="${QGE_RENDER_RES:-1024}"
render_threshold="${QGE_RENDER_THRESHOLD:-0.001}"
render_edge_gain="${QGE_RENDER_EDGE_GAIN:-0}"
render_material_gain="${QGE_RENDER_MATERIAL_GAIN:-0.18}"
render_edge_samples="${QGE_RENDER_EDGE_SAMPLES:-0}"
scene_surface_budget="${QGE_SCENE_SURFACE_BUDGET:-512}"
width="${QGE_STREAM_WIDTH:-800}"
height="${QGE_STREAM_HEIGHT:-600}"
launch_mode="${QGE_STREAM_LAUNCH:-auto}"
sound="${QGE_HARNESS_SOUND:-0}"

normalize_bool() {
  if [[ "${1:-}" == "1" ]]; then
    printf '1\n'
  else
    printf '0\n'
  fi
}

normalize_nonnegative_int() {
  local value="${1:-}"
  local default_value="$2"
  case "$value" in
    ''|*[!0-9]*) printf '%s\n' "$default_value"; return ;;
  esac
  printf '%s\n' "$((10#$value))"
}

normalize_positive_int() {
  local value="${1:-}"
  local default_value="$2"
  value="$(normalize_nonnegative_int "$value" "$default_value")"
  if (( value < 1 )); then
    printf '%s\n' "$default_value"
  else
    printf '%s\n' "$value"
  fi
}

frames="$(normalize_positive_int "$frames" 1)"
waits_per_frame="$(normalize_positive_int "$waits_per_frame" 90)"
classic_render="$(normalize_nonnegative_int "$classic_render" 0)"
quantum_render="$(normalize_nonnegative_int "$quantum_render" 2)"
render_res="$(normalize_positive_int "$render_res" 1024)"
render_edge_samples="$(normalize_nonnegative_int "$render_edge_samples" 0)"
scene_surface_budget="$(normalize_positive_int "$scene_surface_budget" 512)"
width="$(normalize_positive_int "$width" 800)"
height="$(normalize_positive_int "$height" 600)"
sound="$(normalize_bool "$sound")"

image_metrics_available=1
if ! python3 tools/qge_image_metrics.py --check-deps; then
  image_metrics_available=0
  echo "qge_image_metrics dependencies are unavailable; falling back to stdlib world-frame metrics." >&2
fi

if [[ ! -x "$app_bin" ]]; then
  echo "QuantumQuake.app is missing; building it first." >&2
  make quake
fi

if [[ ! -f "$gamedir/pak0.pak" ]]; then
  echo "Missing $gamedir/pak0.pak" >&2
  exit 1
fi

stamp="$(date +%Y%m%d-%H%M%S)"
outdir="$repo_root/diagnostics/quake_graphics/$stamp"
mkdir -p "$outdir"

capture_mode() {
  local mode="$1"
  local render_value="$2"
  local stream_stdout="$outdir/${mode}.stream.txt"
  local stream_dir
  local agent_stream
  local frame_path

  echo "Capturing $mode frame with quantum_render=$render_value" >&2
  if ! QGE_STREAM_FRAMES="$frames" \
       QGE_STREAM_WAIT_FRAMES="$waits_per_frame" \
       QGE_STREAM_MAP="$map_name" \
       QGE_RENDER="$render_value" \
       QGE_RENDER_RES="$render_res" \
       QGE_RENDER_THRESHOLD="$render_threshold" \
       QGE_RENDER_EDGE_GAIN="$render_edge_gain" \
       QGE_RENDER_MATERIAL_GAIN="$render_material_gain" \
       QGE_RENDER_EDGE_SAMPLES="$render_edge_samples" \
       QGE_SCENE_SURFACE_BUDGET="$scene_surface_budget" \
       QGE_STREAM_WIDTH="$width" \
       QGE_STREAM_HEIGHT="$height" \
       QGE_STREAM_LAUNCH="$launch_mode" \
       QGE_STREAM_SOUND="$sound" \
       QGE_STREAM_FULLSCREEN=0 \
       QGE_STREAM_FIRE_TEST=0 \
       QGE_PARTICLES=0 \
       bash tools/quake_graphics_stream.sh > "$stream_stdout" 2>&1; then
    cat "$stream_stdout" >&2
    return 1
  fi

  stream_dir="$(awk '/QGE_STREAM_DONE / {print $2}' "$stream_stdout" | tail -n 1)"
  agent_stream="$(awk '/QGE_AGENT_STREAM_DONE / {print $2}' "$stream_stdout" | tail -n 1)"
  frame_path="$(awk '/QGE_STREAM_FRAME / {print $3}' "$stream_stdout" | tail -n 1)"
  if [[ -z "$stream_dir" || ! -d "$stream_dir" ]]; then
    echo "No stream directory reported for $mode. See $stream_stdout" >&2
    return 1
  fi
  if [[ -z "$frame_path" || ! -f "$frame_path" ]]; then
    echo "No screenshot produced for $mode. See $stream_stdout and $stream_dir" >&2
    return 1
  fi

  cp "$frame_path" "$outdir/${mode}.png"
  cp "$stream_dir/README.txt" "$outdir/${mode}.README.txt" 2>/dev/null || true
  cp "$stream_dir/quantum_quake.log" "$outdir/${mode}.log" 2>/dev/null || true
  cp "$stream_dir/open.log" "$outdir/${mode}.open.log" 2>/dev/null || true
  if [[ -n "$agent_stream" && -d "$agent_stream" ]]; then
    cp "$agent_stream/manifest.json" "$outdir/${mode}.agent_stream.json" 2>/dev/null || true
    cp "$agent_stream/events.ndjson" "$outdir/${mode}.agent_events.ndjson" 2>/dev/null || true
    cp "$agent_stream/input/noesis_actions.txt" "$outdir/${mode}.noesis_actions.txt" 2>/dev/null || true
    cp "$agent_stream/input/noesis_commands.cfg" "$outdir/${mode}.noesis_commands.cfg" 2>/dev/null || true
    cp "$agent_stream/qge_agent_stream_icc_evidence.jsonl" "$outdir/${mode}.agent_icc_evidence.jsonl" 2>/dev/null || true
    cp "$agent_stream/performance/qge_perf_summary.json" "$outdir/${mode}.qge_perf_summary.json" 2>/dev/null || true
    cp "$agent_stream/performance/qge_perf_icc_evidence.json" "$outdir/${mode}.qge_perf_icc_evidence.json" 2>/dev/null || true
  fi
  echo "$outdir/${mode}.png"
}

classic_png="$(capture_mode classic "$classic_render")"
quantum_png="$(capture_mode quantum "$quantum_render")"

if (( image_metrics_available )); then
  python3 tools/qge_image_metrics.py \
    --reference "$classic_png" \
    --candidate "$quantum_png" \
    --json "$outdir/metrics.json" \
    --markdown "$outdir/metrics.md"
  metrics_tool="qge_image_metrics.py"
else
  python3 tools/qge_world_frame_metrics.py \
    --reference "$classic_png" \
    --candidate "$quantum_png" \
    --json "$outdir/metrics.json" \
    --markdown "$outdir/metrics.md"
  metrics_tool="qge_world_frame_metrics.py"
fi

python3 tools/qge_vanilla_capture_matrix.py "$outdir" \
  --out "$outdir/vanilla_capture_matrix.json" \
  --icc-out "$outdir/qge_vanilla_icc_evidence.json"

cat > "$outdir/README.txt" <<EOF
Quantum Quake graphics harness

This directory is a paired classic-vs-QGE capture suitable for reproducible
renderer tracking and paper/demo artifacts.

Map: $map_name
Frames captured per mode: $frames
Waits before each capture: $waits_per_frame
Window: ${width}x${height}
Launch mode: $launch_mode
Sound streaming requested: $sound

Classic reference:
  quantum_render $classic_render
  image: $classic_png
  log: $outdir/classic.log
  stream stdout: $outdir/classic.stream.txt
  agent stream manifest: $outdir/classic.agent_stream.json
  Noesis actions: $outdir/classic.noesis_actions.txt
  Noesis commands: $outdir/classic.noesis_commands.cfg
  agent stream ICC: $outdir/classic.agent_icc_evidence.jsonl
  performance summary: $outdir/classic.qge_perf_summary.json
  performance ICC: $outdir/classic.qge_perf_icc_evidence.json

QGE candidate:
  quantum_render $quantum_render
  quantum_render_res $render_res
  quantum_render_threshold $render_threshold
  quantum_render_edge_gain $render_edge_gain
  quantum_render_material_gain $render_material_gain
  quantum_render_edge_samples $render_edge_samples
  quantum_scene_surface_budget $scene_surface_budget
  image: $quantum_png
  log: $outdir/quantum.log
  stream stdout: $outdir/quantum.stream.txt
  agent stream manifest: $outdir/quantum.agent_stream.json
  Noesis actions: $outdir/quantum.noesis_actions.txt
  Noesis commands: $outdir/quantum.noesis_commands.cfg
  agent stream ICC: $outdir/quantum.agent_icc_evidence.jsonl
  performance summary: $outdir/quantum.qge_perf_summary.json
  performance ICC: $outdir/quantum.qge_perf_icc_evidence.json

Metrics:
  tool: $metrics_tool
  JSON: $outdir/metrics.json
  Markdown: $outdir/metrics.md

Vanilla capture matrix:
  JSON: $outdir/vanilla_capture_matrix.json
  ICC evidence: $outdir/qge_vanilla_icc_evidence.json
EOF

echo "QGE_GRAPHICS_HARNESS_DONE $outdir"
