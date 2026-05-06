#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

app_bin="$repo_root/QuantumQuake.app/Contents/MacOS/quantum_quake"
app_bundle="$repo_root/QuantumQuake.app"
basedir="$repo_root/assets"
gamedir="$basedir/id1"
autoexec="$gamedir/autoexec.cfg"

frames="${QGE_STREAM_FRAMES:-12}"
waits_per_frame="${QGE_STREAM_WAIT_FRAMES:-20}"
map_name="${QGE_STREAM_MAP:-start}"
render_value="${QGE_RENDER:-1}"
render_res="${QGE_RENDER_RES:-512}"
physics_value="${QGE_PHYSICS:-1}"
projectiles_value="${QGE_PROJECTILES:-1}"
particles_value="${QGE_PARTICLES:-0}"
overlay_alpha="${QGE_OVERLAY_ALPHA:-0.10}"
scene_surface_budget="${QGE_SCENE_SURFACE_BUDGET:-1024}"
width="${QGE_STREAM_WIDTH:-800}"
height="${QGE_STREAM_HEIGHT:-600}"
fullscreen="${QGE_STREAM_FULLSCREEN:-0}"
fire_test="${QGE_STREAM_FIRE_TEST:-0}"
sound="${QGE_STREAM_SOUND:-0}"
trace="${QGE_STREAM_TRACE:-0}"
launch_mode="${QGE_STREAM_LAUNCH:-auto}"

if [[ "$launch_mode" == "auto" ]]; then
  case "$(uname -s)" in
    Darwin) launch_mode="open" ;;
    *) launch_mode="direct" ;;
  esac
fi

if [[ ! -f "$gamedir/pak0.pak" ]]; then
  echo "Missing $gamedir/pak0.pak" >&2
  exit 1
fi

if [[ ! -x "$app_bin" ]]; then
  echo "QuantumQuake.app is missing; building it first." >&2
  make quake
fi

stamp="$(date +%Y%m%d-%H%M%S)"
outdir="$repo_root/diagnostics/quake_stream/$stamp"
mkdir -p "$outdir"

restore_autoexec() {
  if [[ -f "$outdir/autoexec.cfg.before" ]]; then
    cp "$outdir/autoexec.cfg.before" "$autoexec"
  else
    cat > "$autoexec" <<'EOF'
// Empty autoexec restored after Quantum Quake graphics stream harness.
EOF
  fi
}

if [[ -f "$autoexec" ]]; then
  cp "$autoexec" "$outdir/autoexec.cfg.before"
fi
trap restore_autoexec EXIT

{
  echo "developer 1"
  echo "con_notifytime 0"
  echo "cl_startdemos 0"
  echo "quantum_debug 1"
  echo "quantum_render $render_value"
  echo "quantum_render_res $render_res"
  echo "quantum_overlay_alpha $overlay_alpha"
  echo "quantum_scene_surface_budget $scene_surface_budget"
  echo "quantum_physics $physics_value"
  echo "quantum_projectiles $projectiles_value"
  echo "quantum_particles $particles_value"
  echo "map $map_name"
  if [[ "$fire_test" == "1" ]]; then
    for _ in $(seq 1 40); do
      echo "wait"
    done
    echo "give 7"
    echo "give r 100"
    echo "impulse 7"
    for _ in $(seq 1 12); do
      echo "wait"
    done
    echo "+attack"
    for _ in $(seq 1 18); do
      echo "wait"
    done
    echo "-attack"
  fi
  for frame in $(seq 1 "$frames"); do
    for _ in $(seq 1 "$waits_per_frame"); do
      echo "wait"
    done
    echo "echo QGE_STREAM_CAPTURE $frame"
    echo "screenshot png"
  done
  echo "quit"
} > "$autoexec"
cp "$autoexec" "$outdir/autoexec.cfg.used"

before_file="$outdir/screens.before"
seen_file="$outdir/screens.seen"
current_file="$outdir/screens.current"
new_file="$outdir/screens.new"
log_file="$outdir/quantum_quake.log"
runtime_log_file="$log_file"
open_log_file="$outdir/open.log"
qconsole_file="$repo_root/qconsole.log"
trace_file="$outdir/qge_trace.bin"
touch "$log_file"
log_next_line=1

find "$gamedir" -maxdepth 1 -name 'spasm*.png' -print | sort > "$before_file"
cp "$before_file" "$seen_file"

echo "Streaming Quantum Quake graphics diagnostics"
echo "  outdir=$outdir"
echo "  quantum_render=$render_value quantum_render_res=$render_res quantum_physics=$physics_value quantum_projectiles=$projectiles_value quantum_particles=$particles_value"
echo "  map=$map_name frames=$frames waits_per_frame=$waits_per_frame fullscreen=$fullscreen sound=$sound trace=$trace fire_test=$fire_test scene_surface_budget=$scene_surface_budget launch=$launch_mode"

print_log_updates() {
  local total_lines
  [[ -f "$runtime_log_file" ]] || return
  total_lines="$(wc -l < "$runtime_log_file" | tr -d ' ')"
  if (( total_lines >= log_next_line )); then
	      sed -n "${log_next_line},${total_lines}p" "$runtime_log_file" | sed -n \
	      -e '/QGE render frame=/p' \
	      -e '/QGE scene frame=/p' \
	      -e '/QGE: World registry/p' \
	      -e '/QGE registry /p' \
	      -e '/QGE snapshot /p' \
	      -e '/QGE physics frame=/p' \
	      -e '/QGE trace /p' \
	      -e '/Sound Initialization/p' \
	      -e '/SDL audio/p' \
	      -e '/QGE quantum audio/p' \
	      -e '/QGE_STREAM_CAPTURE/p' \
      -e '/Wrote spasm/p' \
      -e '/UNSUPPORTED/p'
    log_next_line=$((total_lines + 1))
  fi
}

video_args=(-window -width "$width" -height "$height")
if [[ "$fullscreen" == "1" ]]; then
  video_args=(-fullscreen)
fi

run_args=(-basedir "$basedir" "${video_args[@]}")
if [[ "$sound" != "1" ]]; then
  run_args+=(-nosound)
fi

if [[ "$launch_mode" == "open" ]]; then
  runtime_log_file="$qconsole_file"
  : > "$runtime_log_file"
  touch "$app_bundle" 2>/dev/null || true
  open_args=(-W -n)
  if [[ "$trace" == "1" ]]; then
    open_args+=(--env "QGE_TRACE_PATH=$trace_file")
  fi
  open_args+=("$app_bundle")
  open "${open_args[@]}" --args "${run_args[@]}" -condebug >"$open_log_file" 2>&1 &
elif [[ "$trace" == "1" ]]; then
  QGE_TRACE_PATH="$trace_file" "$app_bin" "${run_args[@]}" >"$log_file" 2>&1 &
else
  "$app_bin" "${run_args[@]}" >"$log_file" 2>&1 &
fi

game_pid=$!
frame_index=0
elapsed=0
max_seconds=$((60 + frames * waits_per_frame / 20))

while kill -0 "$game_pid" 2>/dev/null; do
  print_log_updates
  find "$gamedir" -maxdepth 1 -name 'spasm*.png' -print | sort > "$current_file"
  comm -13 "$seen_file" "$current_file" > "$new_file"
  if [[ -s "$new_file" ]]; then
    while IFS= read -r screenshot; do
      if [[ -f "$screenshot" ]]; then
        frame_index=$((frame_index + 1))
        frame_name="$(printf 'frame_%03d.png' "$frame_index")"
        cp "$screenshot" "$outdir/$frame_name"
        echo "QGE_STREAM_FRAME $frame_index $outdir/$frame_name"
      fi
    done < "$new_file"
    cp "$current_file" "$seen_file"
  fi

  if (( elapsed >= max_seconds )); then
    echo "QGE_STREAM_TIMEOUT killing process $game_pid" >&2
    kill "$game_pid" 2>/dev/null || true
    if [[ "$launch_mode" == "open" ]]; then
      pgrep -f "$app_bin" | while read -r app_pid; do
        kill "$app_pid" 2>/dev/null || true
      done
    fi
    break
  fi

  sleep 1
  elapsed=$((elapsed + 1))
done

wait "$game_pid" 2>/dev/null || true
print_log_updates

if [[ "$launch_mode" == "open" && -f "$runtime_log_file" ]]; then
  cp "$runtime_log_file" "$log_file"
fi

find "$gamedir" -maxdepth 1 -name 'spasm*.png' -print | sort > "$current_file"
comm -13 "$seen_file" "$current_file" > "$new_file"
if [[ -s "$new_file" ]]; then
  while IFS= read -r screenshot; do
    if [[ -f "$screenshot" ]]; then
      frame_index=$((frame_index + 1))
      frame_name="$(printf 'frame_%03d.png' "$frame_index")"
      cp "$screenshot" "$outdir/$frame_name"
      echo "QGE_STREAM_FRAME $frame_index $outdir/$frame_name"
    fi
  done < "$new_file"
fi

cat > "$outdir/README.txt" <<EOF
Quantum Quake graphics stream

Frames captured: $frame_index
Map: $map_name
Render cvar: quantum_render $render_value
Internal render resolution: $render_res
Scene surface budget: $scene_surface_budget
Physics cvars: quantum_physics $physics_value, quantum_projectiles $projectiles_value, quantum_particles $particles_value
Fire test: $fire_test
Launch mode: $launch_mode
Trace: $trace_file
Log: $log_file
Autoexec used: $outdir/autoexec.cfg.used
EOF

if [[ "$trace" == "1" ]]; then
  if [[ -s "$trace_file" ]]; then
    trace_bytes="$(wc -c < "$trace_file" | tr -d ' ')"
    echo "QGE_TRACE_DONE $trace_file bytes=$trace_bytes"
  else
    echo "QGE_TRACE_MISSING $trace_file" >&2
  fi
fi

echo "QGE_STREAM_DONE $outdir frames=$frame_index"
