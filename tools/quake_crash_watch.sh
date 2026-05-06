#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

app_bin="$repo_root/QuantumQuake.app/Contents/MacOS/quantum_quake"
basedir="$repo_root/assets"
gamedir="$basedir/id1"
autoexec="$gamedir/autoexec.cfg"

seconds="${QGE_CRASH_SECONDS:-90}"
script_waits="${QGE_CRASH_WAITS:-3600}"
map_name="${QGE_CRASH_MAP:-e1m1}"
render_value="${QGE_RENDER:-1}"
render_res="${QGE_RENDER_RES:-1024}"
render_threshold="${QGE_RENDER_THRESHOLD:-0.003}"
render_edge_gain="${QGE_RENDER_EDGE_GAIN:-0.06}"
render_material_gain="${QGE_RENDER_MATERIAL_GAIN:-0.18}"
rng_value="${QGE_RNG:-1}"
ai_value="${QGE_AI:-1}"
physics_value="${QGE_PHYSICS:-1}"
projectiles_value="${QGE_PROJECTILES:-1}"
particles_value="${QGE_PARTICLES:-0}"
overlay_alpha="${QGE_OVERLAY_ALPHA:-0.10}"
scene_surface_budget="${QGE_SCENE_SURFACE_BUDGET:-1024}"
width="${QGE_STREAM_WIDTH:-800}"
height="${QGE_STREAM_HEIGHT:-600}"
sound="${QGE_CRASH_SOUND:-0}"

if [[ ! -x "$app_bin" ]]; then
  echo "QuantumQuake.app is missing; building it first." >&2
  make quake
fi

if [[ ! -f "$gamedir/pak0.pak" ]]; then
  echo "Missing $gamedir/pak0.pak" >&2
  exit 1
fi

stamp="$(date +%Y%m%d-%H%M%S)"
outdir="$repo_root/diagnostics/crash_watch/$stamp"
mkdir -p "$outdir"

restore_autoexec() {
  if [[ -f "$outdir/autoexec.cfg.before" ]]; then
    cp "$outdir/autoexec.cfg.before" "$autoexec"
  else
    printf '%s\n' '// Empty autoexec restored after Quantum Quake crash watch.' > "$autoexec"
  fi
}

if [[ -f "$autoexec" ]]; then
  cp "$autoexec" "$outdir/autoexec.cfg.before"
fi
trap restore_autoexec EXIT

find /Users/tyr/Library/Logs/DiagnosticReports -maxdepth 1 -type f -print | sort > "$outdir/crash_reports.before"
rm -f "$basedir/qconsole.log"

{
  echo "developer 1"
  echo "con_notifytime 0"
  echo "cl_startdemos 0"
  echo "quantum_debug 1"
  echo "quantum_render $render_value"
  echo "quantum_render_res $render_res"
  echo "quantum_render_threshold $render_threshold"
  echo "quantum_render_edge_gain $render_edge_gain"
  echo "quantum_render_material_gain $render_material_gain"
  echo "quantum_rng $rng_value"
  echo "quantum_ai $ai_value"
  echo "quantum_overlay_alpha $overlay_alpha"
  echo "quantum_scene_surface_budget $scene_surface_budget"
  echo "quantum_physics $physics_value"
  echo "quantum_projectiles $projectiles_value"
  echo "quantum_particles $particles_value"
  echo "map $map_name"
  for _ in $(seq 1 60); do
    echo "wait"
  done
  echo "give 7"
  echo "give r 100"
  echo "impulse 7"
  echo "+forward"
  for _ in $(seq 1 90); do
    echo "wait"
  done
  echo "-forward"
  echo "+attack"
  for _ in $(seq 1 45); do
    echo "wait"
  done
  echo "-attack"
  for _ in $(seq 1 "$script_waits"); do
    echo "wait"
  done
  echo "echo QGE_CRASH_WATCH_SCRIPT_DONE"
  echo "quit"
} > "$autoexec"
cp "$autoexec" "$outdir/autoexec.cfg.used"

log_file="$outdir/quantum_quake.log"
touch "$log_file"
log_next_line=1

echo "Watching Quantum Quake for crashes"
echo "  outdir=$outdir"
echo "  seconds=$seconds script_waits=$script_waits map=$map_name window=${width}x${height} sound=$sound"
echo "  quantum_render=$render_value quantum_render_res=$render_res quantum_render_threshold=$render_threshold edge_gain=$render_edge_gain material_gain=$render_material_gain quantum_rng=$rng_value quantum_ai=$ai_value"
echo "  quantum_physics=$physics_value quantum_projectiles=$projectiles_value quantum_particles=$particles_value"

print_log_updates() {
  local total_lines
  total_lines="$(wc -l < "$log_file" | tr -d ' ')"
  if (( total_lines >= log_next_line )); then
      sed -n "${log_next_line},${total_lines}p" "$log_file" | sed -n \
      -e '/QGE render frame=/p' \
      -e '/QGE scene frame=/p' \
      -e '/QGE: World registry/p' \
      -e '/QGE registry /p' \
      -e '/QGE snapshot /p' \
      -e '/QGE physics frame=/p' \
      -e '/Sound Initialization/p' \
      -e '/SDL audio/p' \
      -e '/QGE quantum audio/p' \
      -e '/Host_Error/p' \
      -e '/Sys_Error/p' \
      -e '/Segmentation/p' \
      -e '/Assertion/p' \
      -e '/UNSUPPORTED/p' \
      -e '/QGE: Shutting down/p' \
      -e '/QGE: Shutdown/p'
    log_next_line=$((total_lines + 1))
  fi
}

run_args=(-basedir "$basedir" -window -width "$width" -height "$height")
if [[ "$sound" != "1" ]]; then
  run_args+=(-nosound)
fi
run_args+=(-condebug)

"$app_bin" "${run_args[@]}" >"$log_file" 2>&1 &

game_pid=$!
elapsed=0
exit_status=0

while kill -0 "$game_pid" 2>/dev/null; do
  print_log_updates
  if (( elapsed >= seconds )); then
    echo "QGE_CRASH_WATCH_ALIVE killing process $game_pid after ${seconds}s"
    kill "$game_pid" 2>/dev/null || true
    wait "$game_pid" 2>/dev/null || true
    exit_status=0
    break
  fi
  sleep 1
  elapsed=$((elapsed + 1))
done

if (( elapsed < seconds )); then
  if ! wait "$game_pid" 2>/dev/null; then
    exit_status=$?
  fi
fi

print_log_updates
find /Users/tyr/Library/Logs/DiagnosticReports -maxdepth 1 -type f -print | sort > "$outdir/crash_reports.after"
comm -13 "$outdir/crash_reports.before" "$outdir/crash_reports.after" > "$outdir/crash_reports.new"
if [[ -f "$basedir/qconsole.log" ]]; then
  cp "$basedir/qconsole.log" "$outdir/qconsole.log"
fi

if [[ -s "$outdir/crash_reports.new" ]]; then
  echo "QGE_CRASH_WATCH_REPORTS"
  cat "$outdir/crash_reports.new"
fi

if (( elapsed < seconds )); then
  echo "QGE_CRASH_WATCH_EXIT status=$exit_status elapsed=${elapsed}s log=$log_file"
else
  echo "QGE_CRASH_WATCH_DONE elapsed=${elapsed}s log=$log_file"
fi
