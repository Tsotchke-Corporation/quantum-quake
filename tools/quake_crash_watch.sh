#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

app_bin="$repo_root/QuantumQuake.app/Contents/MacOS/quantum_quake"
basedir="$repo_root/assets"
gamedir="$basedir/id1"
autoexec="$gamedir/autoexec.cfg"
qconsole_file="$basedir/qconsole.log"
qconsole_root_file="$repo_root/qconsole.log"

seconds="${QGE_CRASH_SECONDS:-90}"
script_waits="${QGE_CRASH_WAITS:-3600}"
map_name="${QGE_CRASH_MAP:-e1m1}"
stream_skill="${QGE_STREAM_SKILL:-}"
render_value="${QGE_RENDER:-1}"
render_res="${QGE_RENDER_RES:-1024}"
render_threshold="${QGE_RENDER_THRESHOLD:-0.003}"
render_edge_gain="${QGE_RENDER_EDGE_GAIN:-0}"
render_material_gain="${QGE_RENDER_MATERIAL_GAIN:-0.18}"
render_bilinear_samples="${QGE_RENDER_BILINEAR_SAMPLES:-1}"
render_edge_samples="${QGE_RENDER_EDGE_SAMPLES:-0}"
render_detail_mix="${QGE_RENDER_DETAIL_MIX:-1.0}"
render_display_filter="${QGE_RENDER_DISPLAY_FILTER:-0}"
render_update_interval="${QGE_RENDER_UPDATE_INTERVAL:-1}"
rng_value="${QGE_RNG:-1}"
ai_value="${QGE_AI:-1}"
physics_value="${QGE_PHYSICS:-1}"
projectiles_value="${QGE_PROJECTILES:-1}"
physics_authoritative="${QGE_PHYSICS_AUTHORITATIVE:-0}"
particles_value="${QGE_PARTICLES:-0}"
overlay_alpha="${QGE_OVERLAY_ALPHA:-0.10}"
scene_surface_budget="${QGE_SCENE_SURFACE_BUDGET:-512}"
width="${QGE_STREAM_WIDTH:-800}"
height="${QGE_STREAM_HEIGHT:-600}"
stream_display="${QGE_STREAM_DISPLAY:-}"
sound="${QGE_CRASH_SOUND:-0}"
stream_mouse="${QGE_STREAM_MOUSE:-0}"
stream_player="${QGE_STREAM_PLAYER:-noesis}"
noesis_dir="${QGE_NOESIS_DIR:-$HOME/Desktop/noesis}"
noesis_plan="${QGE_NOESIS_PLAN:-adaptive}"
noesis_actions_file="${QGE_NOESIS_ACTIONS_FILE:-}"
noesis_start_wait="${QGE_NOESIS_START_WAIT:-60}"
noesis_max_wait="${QGE_NOESIS_MAX_WAIT:-600}"
noesis_scripted="${QGE_NOESIS_SCRIPTED:-0}"
noesis_autonomous="${QGE_NOESIS_AUTONOMOUS:-}"
noesis_target_class="${QGE_NOESIS_TARGET_CLASS:-}"
noesis_cmd="${QGE_NOESIS_CMD:-}"
default_noesis_cmd="$repo_root/tools/noesis_quake_policy.sh"
noesis_cmd_default=0
noesis_player_tool="$repo_root/tools/noesis_quake_player.sh"

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

stream_mouse="$(normalize_bool "$stream_mouse")"
sound="$(normalize_bool "$sound")"
render_value="$(normalize_nonnegative_int "$render_value" 1)"
render_res="$(normalize_positive_int "$render_res" 1024)"
render_bilinear_samples="$(normalize_nonnegative_int "$render_bilinear_samples" 0)"
render_edge_samples="$(normalize_nonnegative_int "$render_edge_samples" 0)"
render_detail_mix="${render_detail_mix:-1.0}"
render_display_filter="$(normalize_nonnegative_int "$render_display_filter" 0)"
render_update_interval="$(normalize_positive_int "$render_update_interval" 1)"
rng_value="$(normalize_bool "$rng_value")"
ai_value="$(normalize_bool "$ai_value")"
physics_value="$(normalize_bool "$physics_value")"
projectiles_value="$(normalize_nonnegative_int "$projectiles_value" 1)"
physics_authoritative="$(normalize_bool "$physics_authoritative")"
particles_value="$(normalize_bool "$particles_value")"
scene_surface_budget="$(normalize_positive_int "$scene_surface_budget" 512)"
width="$(normalize_positive_int "$width" 800)"
height="$(normalize_positive_int "$height" 600)"
noesis_start_wait="$(normalize_nonnegative_int "$noesis_start_wait" 60)"
noesis_max_wait="$(normalize_positive_int "$noesis_max_wait" 600)"
noesis_scripted="$(normalize_bool "$noesis_scripted")"
if [[ -n "$noesis_autonomous" ]]; then
  noesis_autonomous="$(normalize_bool "$noesis_autonomous")"
fi
seconds="$(normalize_nonnegative_int "$seconds" 90)"
script_waits="$(normalize_nonnegative_int "$script_waits" 3600)"
case "$stream_skill" in
  ''|*[!0-9]*) stream_skill="" ;;
esac
if [[ "$stream_player" == "noesis" && "$noesis_scripted" == "1" &&
      -z "$noesis_cmd" && -z "$noesis_actions_file" && -x "$default_noesis_cmd" ]]; then
  noesis_cmd="$default_noesis_cmd"
  noesis_cmd_default=1
fi
if [[ -z "$noesis_autonomous" ]]; then
  noesis_autonomous=0
  if [[ "$stream_player" == "noesis" && "$noesis_scripted" == "0" &&
        -z "$noesis_cmd" && -z "$noesis_actions_file" ]]; then
    noesis_autonomous=1
  fi
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
outdir="$repo_root/diagnostics/crash_watch/$stamp"
input_dir="$outdir/input"
input_actions_file="$input_dir/noesis_actions.txt"
input_commands_file="$input_dir/noesis_commands.cfg"
mkdir -p "$outdir" "$input_dir"
: > "$input_actions_file"
: > "$input_commands_file"

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

emit_noesis_player_script() {
  QGE_NOESIS_DIR="$noesis_dir" \
    QGE_NOESIS_PLAN="$noesis_plan" \
    QGE_NOESIS_ACTIONS_FILE="$noesis_actions_file" \
    QGE_NOESIS_START_WAIT="$noesis_start_wait" \
    QGE_NOESIS_MAX_WAIT="$noesis_max_wait" \
    QGE_NOESIS_SCRIPTED="$noesis_scripted" \
    QGE_NOESIS_CMD="$noesis_cmd" \
    QGE_NOESIS_ACTION_TRACE_FILE="$input_actions_file" \
    QGE_NOESIS_COMMAND_TRACE_FILE="$input_commands_file" \
    QGE_STREAM_MAP="$map_name" \
    "$noesis_player_tool"
}

find /Users/tyr/Library/Logs/DiagnosticReports -maxdepth 1 -type f -print | sort > "$outdir/crash_reports.before"
rm -f "$qconsole_file" "$qconsole_root_file"

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
  echo "quantum_render_bilinear_samples $render_bilinear_samples"
  echo "quantum_render_edge_samples $render_edge_samples"
  echo "quantum_render_detail_mix $render_detail_mix"
  echo "quantum_render_display_filter $render_display_filter"
  echo "quantum_render_update_interval $render_update_interval"
  echo "quantum_rng $rng_value"
  echo "quantum_ai $ai_value"
  echo "quantum_overlay_alpha $overlay_alpha"
  echo "quantum_scene_surface_budget $scene_surface_budget"
  echo "quantum_physics $physics_value"
  echo "quantum_projectiles $projectiles_value"
  echo "quantum_physics_authoritative $physics_authoritative"
  echo "quantum_particles $particles_value"
  echo "qge_noesis_autonomous $noesis_autonomous"
  echo "qge_noesis_target_class \"$noesis_target_class\""
  if [[ -n "$stream_skill" ]]; then
    echo "skill $stream_skill"
  fi
  echo "map $map_name"
  if [[ "$stream_player" == "noesis" ]]; then
    emit_noesis_player_script
  else
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
  fi
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
echo "  seconds=$seconds script_waits=$script_waits map=$map_name window=${width}x${height} display=$stream_display sound=$sound mouse=$stream_mouse player=$stream_player noesis_plan=$noesis_plan noesis_scripted=$noesis_scripted noesis_autonomous=$noesis_autonomous"
if [[ "$stream_player" == "noesis" ]]; then
  echo "  noesis_cmd=$noesis_cmd noesis_cmd_default=$noesis_cmd_default max_wait=$noesis_max_wait actions=$input_actions_file commands=$input_commands_file"
fi
echo "  quantum_render=$render_value quantum_render_res=$render_res quantum_render_threshold=$render_threshold edge_gain=$render_edge_gain material_gain=$render_material_gain bilinear_samples=$render_bilinear_samples edge_samples=$render_edge_samples detail_mix=$render_detail_mix display_filter=$render_display_filter update_interval=$render_update_interval quantum_rng=$rng_value quantum_ai=$ai_value"
echo "  quantum_physics=$physics_value quantum_projectiles=$projectiles_value quantum_physics_authoritative=$physics_authoritative quantum_particles=$particles_value"

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
      -e '/QGE_NOESIS_/p' \
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
if [[ -n "$stream_display" ]]; then
  run_args+=(-display "$stream_display")
fi
if [[ "$stream_mouse" != "1" ]]; then
  run_args+=(-nomouse)
fi
if [[ "$sound" != "1" ]]; then
  run_args+=(-nosound)
fi
run_args+=(-condebug)

"$app_bin" "${run_args[@]}" >"$log_file" 2>&1 &

game_pid=$!
elapsed=0
exit_status=0
timed_out=0

while kill -0 "$game_pid" 2>/dev/null; do
  print_log_updates
  if (( elapsed >= seconds )); then
    echo "QGE_CRASH_WATCH_ALIVE killing process $game_pid after ${seconds}s"
    timed_out=1
    kill "$game_pid" 2>/dev/null || true
    break
  fi
  sleep 1
  elapsed=$((elapsed + 1))
done

if wait "$game_pid" 2>/dev/null; then
  exit_status=0
else
  exit_status=$?
fi

print_log_updates
find /Users/tyr/Library/Logs/DiagnosticReports -maxdepth 1 -type f -print | sort > "$outdir/crash_reports.after"
comm -13 "$outdir/crash_reports.before" "$outdir/crash_reports.after" > "$outdir/crash_reports.new"
if [[ -f "$qconsole_file" ]]; then
  cp "$qconsole_file" "$outdir/qconsole.log"
  rm -f "$qconsole_file"
fi
if [[ -f "$qconsole_root_file" ]]; then
  if [[ -f "$outdir/qconsole.log" ]]; then
    cp "$qconsole_root_file" "$outdir/qconsole.root.log"
  else
    cp "$qconsole_root_file" "$outdir/qconsole.log"
  fi
  rm -f "$qconsole_root_file"
fi

if [[ -s "$outdir/crash_reports.new" ]]; then
  echo "QGE_CRASH_WATCH_REPORTS"
  cat "$outdir/crash_reports.new"
fi

if (( timed_out == 1 )); then
  echo "QGE_CRASH_WATCH_TIMEOUT status=$exit_status elapsed=${elapsed}s log=$log_file"
elif (( exit_status != 0 )); then
  echo "QGE_CRASH_WATCH_EXIT status=$exit_status elapsed=${elapsed}s log=$log_file"
else
  echo "QGE_CRASH_WATCH_DONE status=$exit_status elapsed=${elapsed}s log=$log_file"
fi
