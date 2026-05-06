#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

app_bin="$repo_root/QuantumQuake.app/Contents/MacOS/quantum_quake"
basedir="$repo_root/assets"
gamedir="$basedir/id1"

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
  local before_file="$outdir/${mode}.before"
  local after_file="$outdir/${mode}.after"
  local new_file="$outdir/${mode}.new"
  local log_file="$outdir/${mode}.log"
  local cfg_file="$gamedir/qge_harness_${mode}.cfg"

  find "$gamedir" -maxdepth 1 -name 'spasm*.png' -print | sort > "$before_file"

  {
    echo "cl_startdemos 0"
    echo "quantum_render $render_value"
    echo "map start"
    for _ in $(seq 1 90); do
      echo "wait"
    done
    echo "screenshot png"
    echo "quit"
  } > "$cfg_file"

  echo "Capturing $mode frame with quantum_render=$render_value"
  (
    "$app_bin" \
      -basedir "$basedir" \
      -window -width 800 -height 600 -nosound \
      +exec "qge_harness_${mode}.cfg"
  ) >"$log_file" 2>&1 &

  local pid=$!
  local elapsed=0
  while kill -0 "$pid" 2>/dev/null; do
    if (( elapsed >= 45 )); then
      echo "Timed out waiting for $mode capture; killing process $pid" >&2
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  wait "$pid"

  find "$gamedir" -maxdepth 1 -name 'spasm*.png' -print | sort > "$after_file"
  comm -13 "$before_file" "$after_file" > "$new_file"

  local screenshot
  screenshot="$(tail -n 1 "$new_file" || true)"
  if [[ -z "$screenshot" || ! -f "$screenshot" ]]; then
    echo "No screenshot produced for $mode. See $log_file" >&2
    return 1
  fi

  cp "$screenshot" "$outdir/${mode}.png"
  echo "$outdir/${mode}.png"
}

classic_png="$(capture_mode classic 0)"
quantum_png="$(capture_mode quantum 1)"

cat > "$outdir/README.txt" <<EOF
Quantum Quake graphics harness

classic: $classic_png
quantum: $quantum_png

Commands captured the shareware start map after 90 rendered frames:
  quantum_render 0: normal Quake renderer
  quantum_render 1: QGE DWT overlay enabled

Logs:
  $outdir/classic.log
  $outdir/quantum.log
EOF

echo "Harness output: $outdir"
