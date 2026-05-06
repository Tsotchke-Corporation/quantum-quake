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
render_edge_gain="${QGE_RENDER_EDGE_GAIN:-0.06}"
render_material_gain="${QGE_RENDER_MATERIAL_GAIN:-0.18}"
scene_surface_budget="${QGE_SCENE_SURFACE_BUDGET:-1024}"
width="${QGE_STREAM_WIDTH:-800}"
height="${QGE_STREAM_HEIGHT:-600}"
launch_mode="${QGE_STREAM_LAUNCH:-auto}"

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
       QGE_SCENE_SURFACE_BUDGET="$scene_surface_budget" \
       QGE_STREAM_WIDTH="$width" \
       QGE_STREAM_HEIGHT="$height" \
       QGE_STREAM_LAUNCH="$launch_mode" \
       QGE_STREAM_FULLSCREEN=0 \
       QGE_STREAM_FIRE_TEST=0 \
       QGE_PARTICLES=0 \
       bash tools/quake_graphics_stream.sh > "$stream_stdout" 2>&1; then
    cat "$stream_stdout" >&2
    return 1
  fi

  stream_dir="$(awk '/QGE_STREAM_DONE / {print $2}' "$stream_stdout" | tail -n 1)"
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
  echo "$outdir/${mode}.png"
}

classic_png="$(capture_mode classic "$classic_render")"
quantum_png="$(capture_mode quantum "$quantum_render")"

python3 tools/qge_image_metrics.py \
  --reference "$classic_png" \
  --candidate "$quantum_png" \
  --json "$outdir/metrics.json" \
  --markdown "$outdir/metrics.md"

cat > "$outdir/README.txt" <<EOF
Quantum Quake graphics harness

This directory is a paired classic-vs-QGE capture suitable for reproducible
renderer tracking and paper/demo artifacts.

Map: $map_name
Frames captured per mode: $frames
Waits before each capture: $waits_per_frame
Window: ${width}x${height}
Launch mode: $launch_mode

Classic reference:
  quantum_render $classic_render
  image: $classic_png
  log: $outdir/classic.log
  stream stdout: $outdir/classic.stream.txt

QGE candidate:
  quantum_render $quantum_render
  quantum_render_res $render_res
  quantum_render_threshold $render_threshold
  quantum_render_edge_gain $render_edge_gain
  quantum_render_material_gain $render_material_gain
  quantum_scene_surface_budget $scene_surface_budget
  image: $quantum_png
  log: $outdir/quantum.log
  stream stdout: $outdir/quantum.stream.txt

Metrics:
  JSON: $outdir/metrics.json
  Markdown: $outdir/metrics.md
EOF

echo "QGE_GRAPHICS_HARNESS_DONE $outdir"
