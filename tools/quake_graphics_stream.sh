#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

app_bin="$repo_root/QuantumQuake.app/Contents/MacOS/quantum_quake"
app_bundle="$repo_root/QuantumQuake.app"
app_bundle_id="com.quantumquake.QuantumQuake"
basedir="$repo_root/assets"
gamedir="$basedir/id1"
autoexec="$gamedir/autoexec.cfg"

frames="${QGE_STREAM_FRAMES:-12}"
waits_per_frame="${QGE_STREAM_WAIT_FRAMES:-20}"
capture_wait_override="${QGE_STREAM_CAPTURE_WAIT:-}"
map_name="${QGE_STREAM_MAP:-start}"
render_value="${QGE_RENDER:-1}"
render_res="${QGE_RENDER_RES:-1024}"
render_threshold="${QGE_RENDER_THRESHOLD:-0.001}"
render_edge_gain="${QGE_RENDER_EDGE_GAIN:-0.06}"
render_material_gain="${QGE_RENDER_MATERIAL_GAIN:-0.18}"
render_bilinear_samples="${QGE_RENDER_BILINEAR_SAMPLES:-0}"
render_edge_samples="${QGE_RENDER_EDGE_SAMPLES:-0}"
render_display_filter="${QGE_RENDER_DISPLAY_FILTER:-0}"
render_update_interval="${QGE_RENDER_UPDATE_INTERVAL:-8}"
sprite_test="${QGE_STREAM_SPRITE_TEST:-0}"
physics_value="${QGE_PHYSICS:-1}"
projectiles_value="${QGE_PROJECTILES:-1}"
physics_authoritative="${QGE_PHYSICS_AUTHORITATIVE:-0}"
particles_value="${QGE_PARTICLES:-0}"
ai_value="${QGE_STREAM_AI:-${QGE_AI:-1}}"
vis_value="${QGE_STREAM_VIS:-${QGE_VIS:-2}}"
overlay_alpha="${QGE_OVERLAY_ALPHA:-0.10}"
scene_surface_budget="${QGE_SCENE_SURFACE_BUDGET:-128}"
stream_mouse="${QGE_STREAM_MOUSE:-0}"
stream_player="${QGE_STREAM_PLAYER:-noesis}"
stream_activate="${QGE_STREAM_ACTIVATE:-0}"
stream_activate_attempts="${QGE_STREAM_ACTIVATE_ATTEMPTS:-8}"
noesis_dir="${QGE_NOESIS_DIR:-$HOME/Desktop/noesis}"
noesis_plan="${QGE_NOESIS_PLAN:-adaptive}"
noesis_actions_file="${QGE_NOESIS_ACTIONS_FILE:-}"
noesis_start_wait="${QGE_NOESIS_START_WAIT:-16}"
noesis_max_wait="${QGE_NOESIS_MAX_WAIT:-600}"
noesis_cmd="${QGE_NOESIS_CMD:-}"
default_noesis_cmd="$repo_root/tools/noesis_quake_policy.sh"
noesis_cmd_default=0
noesis_player_tool="$repo_root/tools/noesis_quake_player.sh"
width="${QGE_STREAM_WIDTH:-800}"
height="${QGE_STREAM_HEIGHT:-600}"
stream_display="${QGE_STREAM_DISPLAY:-}"
fullscreen="${QGE_STREAM_FULLSCREEN:-0}"
fire_test="${QGE_STREAM_FIRE_TEST:-0}"
fire_min_start_wait="${QGE_STREAM_FIRE_MIN_START_WAIT:-48}"
fire_min_frames="${QGE_STREAM_FIRE_MIN_FRAMES:-8}"
sound="${QGE_STREAM_SOUND:-0}"
sound_quantum_mode="${QGE_STREAM_SND_QUANTUM:-1}"
sound_source_authority="${QGE_STREAM_SND_QUANTUM_SOURCE_AUTHORITY:-0}"
trace="${QGE_STREAM_TRACE:-0}"
replay_trace="${QGE_STREAM_REPLAY_TRACE:-${QGE_REPLAY_TRACE_PATH:-}}"
replay_strict="${QGE_STREAM_REPLAY_STRICT:-${QGE_REPLAY_STRICT:-1}}"
engine_capture="${QGE_STREAM_ENGINE_CAPTURE:-1}"
launch_mode="${QGE_STREAM_LAUNCH:-auto}"
timeout_seconds="${QGE_STREAM_TIMEOUT_SECONDS:-}"
perf_max_average_ms="${QGE_PERF_MAX_AVERAGE_MS:-}"
perf_max_render_ms="${QGE_PERF_MAX_RENDER_MS:-}"

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

if [[ "$launch_mode" == "auto" ]]; then
  case "$(uname -s)" in
    Darwin) launch_mode="open" ;;
    *) launch_mode="direct" ;;
  esac
fi
engine_capture="$(normalize_bool "$engine_capture")"
stream_mouse="$(normalize_bool "$stream_mouse")"
sprite_test="$(normalize_bool "$sprite_test")"
fire_test="$(normalize_bool "$fire_test")"
fullscreen="$(normalize_bool "$fullscreen")"
sound="$(normalize_bool "$sound")"
sound_quantum_mode="$(normalize_nonnegative_int "$sound_quantum_mode" 1)"
sound_source_authority="$(normalize_bool "$sound_source_authority")"
trace="$(normalize_bool "$trace")"
render_value="$(normalize_nonnegative_int "$render_value" 1)"
render_res="$(normalize_positive_int "$render_res" 1024)"
render_bilinear_samples="$(normalize_nonnegative_int "$render_bilinear_samples" 0)"
render_edge_samples="$(normalize_nonnegative_int "$render_edge_samples" 0)"
render_display_filter="$(normalize_nonnegative_int "$render_display_filter" 0)"
render_update_interval="$(normalize_positive_int "$render_update_interval" 8)"
physics_value="$(normalize_nonnegative_int "$physics_value" 1)"
projectiles_value="$(normalize_nonnegative_int "$projectiles_value" 1)"
physics_authoritative="$(normalize_bool "$physics_authoritative")"
particles_value="$(normalize_nonnegative_int "$particles_value" 0)"
ai_value="$(normalize_nonnegative_int "$ai_value" 1)"
vis_value="$(normalize_nonnegative_int "$vis_value" 2)"
replay_strict="$(normalize_bool "$replay_strict")"
scene_surface_budget="$(normalize_positive_int "$scene_surface_budget" 128)"
width="$(normalize_positive_int "$width" 800)"
height="$(normalize_positive_int "$height" 600)"
noesis_start_wait="$(normalize_nonnegative_int "$noesis_start_wait" 16)"
noesis_max_wait="$(normalize_positive_int "$noesis_max_wait" 600)"
fire_min_start_wait="$(normalize_nonnegative_int "$fire_min_start_wait" 48)"
fire_min_frames="$(normalize_nonnegative_int "$fire_min_frames" 8)"
frames="$(normalize_positive_int "$frames" 12)"
waits_per_frame="$(normalize_positive_int "$waits_per_frame" 20)"
case "$capture_wait_override" in
  ''|*[!0-9]*) capture_wait_override="" ;;
esac
if [[ "$fire_test" == "1" && "$stream_player" == "noesis" && -z "${QGE_NOESIS_PLAN+x}" ]]; then
  noesis_plan="fire"
fi
if [[ "$fire_test" == "1" && "$stream_player" == "noesis" &&
      "$fire_min_start_wait" -gt 0 &&
      "$noesis_start_wait" -lt "$fire_min_start_wait" ]]; then
  noesis_start_wait="$fire_min_start_wait"
fi
if [[ "$fire_test" == "1" && "$engine_capture" == "1" &&
      "$fire_min_frames" -gt 0 &&
      "$frames" -lt "$fire_min_frames" ]]; then
  frames="$fire_min_frames"
fi
if [[ "$stream_player" == "noesis" && -z "$noesis_cmd" && -z "$noesis_actions_file" && -x "$default_noesis_cmd" ]]; then
  noesis_cmd="$default_noesis_cmd"
  noesis_cmd_default=1
fi
stream_activate_attempts="$(normalize_positive_int "$stream_activate_attempts" 8)"
timeout_seconds="$(normalize_nonnegative_int "$timeout_seconds" 0)"
if (( timeout_seconds > 0 )); then
  max_seconds="$timeout_seconds"
else
  max_seconds=$((90 + frames * waits_per_frame / 10))
fi
game_status=0
game_timed_out=0
open_status=0
startup_issue=""

if [[ ! -f "$gamedir/pak0.pak" ]]; then
  echo "Missing $gamedir/pak0.pak" >&2
  exit 1
fi

if [[ ! -x "$app_bin" ]]; then
  echo "QuantumQuake.app is missing; building it first." >&2
  make quake
fi

stamp="$(date +%Y%m%d-%H%M%S)"
quake_stream_root="$repo_root/diagnostics/quake_stream"
agent_stream_root="$repo_root/diagnostics/agent_stream"
outdir="$quake_stream_root/$stamp"
agent_stream="${QGE_AGENT_STREAM_DIR:-$agent_stream_root/$stamp}"
agent_video_dir="$agent_stream/video/frames"
agent_audio_dir="$agent_stream/audio"
agent_trace_dir="$agent_stream/trace"
agent_input_dir="$agent_stream/input"
agent_log_dir="$agent_stream/logs"
agent_perf_dir="$agent_stream/performance"
agent_noesis_dir="$agent_stream/noesis"
agent_events_file="$agent_stream/events.ndjson"
agent_manifest_file="$agent_stream/manifest.json"
agent_icc_file="$agent_stream/qge_agent_stream_icc_evidence.jsonl"
agent_latest_stream_file="$agent_stream_root/latest_stream.txt"
agent_latest_manifest_file="$agent_stream_root/latest_manifest.txt"
agent_latest_events_file="$agent_stream_root/latest_events.txt"
agent_latest_icc_file="$agent_stream_root/latest_icc_evidence.txt"
quake_latest_stream_file="$quake_stream_root/latest_stream.txt"
quake_latest_trace_file="$quake_stream_root/latest_trace.txt"
trace_file="$outdir/qge_trace.bin"
trace_summary_file="$outdir/qge_trace_summary.json"
trace_summary_stderr_file="$outdir/qge_trace_summary.err"
perf_summary_file="$outdir/qge_perf_summary.json"
perf_icc_file="$outdir/qge_perf_icc_evidence.json"
perf_stdout_file="$outdir/qge_perf_summary.txt"
perf_stderr_file="$outdir/qge_perf_summary.err"
noesis_summary_file="$outdir/qge_noesis_summary.json"
noesis_icc_file="$outdir/qge_noesis_icc_evidence.json"
noesis_stdout_file="$outdir/qge_noesis_summary.txt"
noesis_stderr_file="$outdir/qge_noesis_summary.err"
agent_perf_summary_file="$agent_perf_dir/qge_perf_summary.json"
agent_perf_icc_file="$agent_perf_dir/qge_perf_icc_evidence.json"
agent_noesis_summary_file="$agent_noesis_dir/qge_noesis_summary.json"
agent_noesis_icc_file="$agent_noesis_dir/qge_noesis_icc_evidence.json"
agent_trace_summary_file="$agent_trace_dir/qge_trace_summary.json"
agent_trace_summary_stderr_file="$agent_trace_dir/qge_trace_summary.err"
agent_input_actions_file="$agent_input_dir/noesis_actions.txt"
agent_input_commands_file="$agent_input_dir/noesis_commands.cfg"
agent_audio_raw="$agent_audio_dir/quake_mix_s16le.raw"
agent_audio_meta="$agent_audio_dir/quake_mix_s16le.json"
agent_audio_bytes_file="$agent_audio_dir/bytes.txt"
agent_frame_count_file="$agent_stream/video/frame_count.txt"
agent_last_frame_file="$agent_stream/video/latest_frame.txt"
last_agent_frame=""
perf_status="not_run"
noesis_summary_status="not_run"
trace_summary_status="not_requested"
trace_runtime_evidence_ready=0
mkdir -p "$quake_stream_root" "$agent_stream_root" "$outdir" "$agent_video_dir" "$agent_audio_dir" "$agent_trace_dir" "$agent_input_dir" "$agent_log_dir" "$agent_perf_dir" "$agent_noesis_dir"
: > "$agent_events_file"
: > "$agent_input_actions_file"
: > "$agent_input_commands_file"
: > "$agent_audio_bytes_file"
: > "$agent_frame_count_file"
: > "$agent_last_frame_file"

json_escape() {
  local value="${1:-}"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  value="${value//$'\r'/\\r}"
  value="${value//$'\t'/\\t}"
  printf '%s' "$value"
}

json_string() {
  printf '"%s"' "$(json_escape "${1:-}")"
}

agent_event() {
  local event="$1"
  local path="${2:-}"
  local detail="${3:-}"
  printf '{"ts":%s,"event":%s,"path":%s,"detail":%s}\n' \
    "$(json_string "$(date -u +"%Y-%m-%dT%H:%M:%SZ")")" \
    "$(json_string "$event")" \
    "$(json_string "$path")" \
    "$(json_string "$detail")" \
    >> "$agent_events_file"
}

write_agent_manifest() {
  local status="$1"
  local audio_status="disabled"
  local audio_bytes=0
  local manifest_frame_count="${frame_index:-0}"
  local run_status="ok"
  local run_success=1
  local manifest_trace_file=""
  local trace_status="not_requested"
  local trace_bytes=0
  local manifest_trace_summary_file=""
  local manifest_agent_trace_summary_file=""
  if [[ "$status" == "running" ]]; then
    run_status="running"
    run_success=0
  elif [[ -n "$startup_issue" ]]; then
    run_status="failed"
    run_success=0
  fi
  if [[ "$sound" == "1" ]]; then
    audio_status="requested_missing"
    if [[ -s "$agent_audio_raw" ]]; then
      audio_status="streaming"
      audio_bytes="$(wc -c < "$agent_audio_raw" | tr -d ' ')"
      if [[ "$status" == "complete" ]]; then
        audio_status="complete"
      fi
    fi
  fi
  if [[ "$trace" == "1" ]]; then
    manifest_trace_file="$trace_file"
    trace_status="requested_missing"
    if [[ -s "$trace_file" ]]; then
      trace_status="complete"
      trace_bytes="$(wc -c < "$trace_file" | tr -d ' ')"
    fi
    manifest_trace_summary_file="$trace_summary_file"
    manifest_agent_trace_summary_file="$agent_trace_summary_file"
  fi
  cat > "$agent_manifest_file" <<EOF
{
  "schema": "qge.agent_stream.v0",
  "status": $(json_string "$status"),
  "stream_dir": $(json_string "$agent_stream"),
  "capture_dir": $(json_string "$outdir"),
  "map": $(json_string "$map_name"),
  "frames_requested": $frames,
  "frames_captured": $manifest_frame_count,
  "waits_per_frame": $waits_per_frame,
  "engine_capture": $engine_capture,
  "run": {
    "status": $(json_string "$run_status"),
    "success": $run_success,
    "startup_issue": $(json_string "$startup_issue"),
    "process_status": $game_status,
    "timed_out": $game_timed_out
  },
  "launch": {
    "mode": $(json_string "$launch_mode"),
    "macos_bundle_id": $(json_string "$app_bundle_id"),
    "macos_nolauncher": 1,
    "macos_fresh_instance": $([[ "$launch_mode" == "open" ]] && printf '1' || printf '0'),
    "macos_persistence_ignore": $([[ "$launch_mode" == "open" ]] && printf '1' || printf '0'),
    "macos_activate": $([[ "$launch_mode" == "open" && "$stream_activate" == "1" ]] && printf '1' || printf '0'),
    "macos_activate_attempts": $stream_activate_attempts
  },
  "window": {
    "width": $width,
    "height": $height,
    "fullscreen": $fullscreen,
    "display": $(json_string "$stream_display")
  },
  "sound_requested": $sound,
  "trace_requested": $trace,
  "replay": {
    "requested": $([[ -n "$replay_trace" ]] && printf '1' || printf '0'),
    "trace_file": $(json_string "$replay_trace"),
    "strict": $replay_strict
  },
  "timeout_seconds": $max_seconds,
  "input": {
    "mouse_enabled": $stream_mouse,
    "player": $(json_string "$stream_player"),
    "noesis_dir": $(json_string "$noesis_dir"),
    "noesis_plan": $(json_string "$noesis_plan"),
    "noesis_actions_file": $(json_string "$noesis_actions_file"),
    "noesis_start_wait": $noesis_start_wait,
    "noesis_max_wait": $noesis_max_wait,
    "fire_test": $fire_test,
    "fire_min_start_wait": $fire_min_start_wait,
    "fire_min_frames": $fire_min_frames,
    "noesis_cmd": $(json_string "$noesis_cmd"),
    "noesis_cmd_default": $noesis_cmd_default,
    "noesis_player_tool": $(json_string "$noesis_player_tool"),
    "action_trace_file": $(json_string "$agent_input_actions_file"),
    "command_trace_file": $(json_string "$agent_input_commands_file")
  },
  "render": {
    "quantum_render": $render_value,
    "quantum_render_res": $render_res,
    "quantum_render_threshold": $(json_string "$render_threshold"),
    "quantum_render_edge_gain": $(json_string "$render_edge_gain"),
    "quantum_render_material_gain": $(json_string "$render_material_gain"),
    "quantum_render_bilinear_samples": $render_bilinear_samples,
    "quantum_render_edge_samples": $render_edge_samples,
    "quantum_render_display_filter": $render_display_filter,
    "quantum_render_update_interval": $render_update_interval,
    "sprite_test": $sprite_test
  },
  "ai": {
    "quantum_ai": $ai_value
  },
  "visibility": {
    "quantum_vis": $vis_value
  },
  "physics": {
    "quantum_physics": $physics_value,
    "quantum_projectiles": $projectiles_value,
    "quantum_physics_authoritative": $physics_authoritative,
    "quantum_particles": $particles_value
  },
  "video": {
    "frames_dir": $(json_string "$agent_video_dir"),
    "frame_count_file": $(json_string "$agent_frame_count_file"),
    "latest_frame_file": $(json_string "$agent_last_frame_file"),
    "format": "png"
  },
  "audio": {
    "status": $(json_string "$audio_status"),
    "raw_file": $(json_string "$agent_audio_raw"),
    "metadata_file": $(json_string "$agent_audio_meta"),
    "bytes_file": $(json_string "$agent_audio_bytes_file"),
    "snd_quantum": $sound_quantum_mode,
    "snd_quantum_source_authority": $sound_source_authority,
    "format": "s16le",
    "bytes": $audio_bytes
  },
  "logs": {
    "runtime_log": $(json_string "$agent_log_dir/quantum_quake.log"),
    "open_log": $(json_string "$agent_log_dir/open.log"),
    "events": $(json_string "$agent_events_file")
  },
  "performance": {
    "status": $(json_string "$perf_status"),
    "summary_file": $(json_string "$agent_perf_summary_file"),
    "icc_evidence_file": $(json_string "$agent_perf_icc_file"),
    "capture_summary_file": $(json_string "$perf_summary_file"),
    "capture_icc_evidence_file": $(json_string "$perf_icc_file"),
    "max_average_ms": $(json_string "$perf_max_average_ms"),
    "max_render_ms": $(json_string "$perf_max_render_ms")
  },
  "noesis": {
    "status": $(json_string "$noesis_summary_status"),
    "summary_file": $(json_string "$agent_noesis_summary_file"),
    "icc_evidence_file": $(json_string "$agent_noesis_icc_file"),
    "capture_summary_file": $(json_string "$noesis_summary_file"),
    "capture_icc_evidence_file": $(json_string "$noesis_icc_file")
  },
  "icc_evidence": $(json_string "$agent_icc_file"),
  "trace": $(json_string "$manifest_trace_file"),
  "trace_status": $(json_string "$trace_status"),
  "trace_bytes": $trace_bytes,
  "trace_summary": {
    "status": $(json_string "$trace_summary_status"),
    "file": $(json_string "$manifest_trace_summary_file"),
    "agent_file": $(json_string "$manifest_agent_trace_summary_file"),
    "stderr_file": $(json_string "$trace_summary_stderr_file"),
    "runtime_evidence_ready": $trace_runtime_evidence_ready
  }
}
EOF
}

write_agent_icc_evidence() {
  local audio_raw_file=""
  local audio_meta_file=""
  local icc_run_status="ok"
  local icc_run_success=1
  local icc_trace_file=""
  local icc_trace_status="not_requested"
  local icc_trace_bytes=0
  local icc_trace_summary_file=""
  if [[ -n "$startup_issue" ]]; then
    icc_run_status="failed"
    icc_run_success=0
  fi
  if [[ "$trace" == "1" ]]; then
    icc_trace_file="$trace_file"
    icc_trace_status="requested_missing"
    if [[ -s "$trace_file" ]]; then
      icc_trace_status="complete"
      icc_trace_bytes="$(wc -c < "$trace_file" | tr -d ' ')"
    fi
    icc_trace_summary_file="$trace_summary_file"
  fi
  if [[ -s "$agent_audio_raw" ]]; then
    audio_raw_file="$agent_audio_raw"
  fi
  if [[ -s "$agent_audio_meta" ]]; then
    audio_meta_file="$agent_audio_meta"
  fi
  {
    printf '{"kind":"runtime_backend","name":"runtime_backend","value":"qge_agent_media_stream","path":%s}\n' "$(json_string "$agent_icc_file")"
    printf '{"kind":"completion_condition","name":"completion_reason","value":"qge_agent_media_stream_complete","path":%s}\n' "$(json_string "$agent_icc_file")"
    printf '{"kind":"runtime_state","name":"agent_stream_run_status","value":%s,"path":%s}\n' "$(json_string "$icc_run_status")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"runtime_state","name":"agent_stream_run_success","value":%s,"path":%s}\n' "$(json_string "$icc_run_success")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"runtime_state","name":"agent_stream_startup_issue","value":%s,"path":%s}\n' "$(json_string "$startup_issue")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"runtime_state","name":"agent_stream_process_status","value":%s,"path":%s}\n' "$(json_string "$game_status")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"runtime_state","name":"agent_stream_timed_out","value":%s,"path":%s}\n' "$(json_string "$game_timed_out")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"runtime_state","name":"agent_stream_frames_captured","value":%s,"path":%s}\n' "$(json_string "$frame_index")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"runtime_state","name":"agent_stream_trace_status","value":%s,"path":%s}\n' "$(json_string "$icc_trace_status")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"runtime_state","name":"agent_stream_trace_bytes","value":%s,"path":%s}\n' "$(json_string "$icc_trace_bytes")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"runtime_state","name":"agent_stream_trace_summary_status","value":%s,"path":%s}\n' "$(json_string "$trace_summary_status")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"runtime_state","name":"agent_stream_runtime_evidence_ready","value":%s,"path":%s}\n' "$(json_string "$trace_runtime_evidence_ready")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"runtime_state","name":"agent_stream_perf_status","value":%s,"path":%s}\n' "$(json_string "$perf_status")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"runtime_state","name":"agent_stream_noesis_status","value":%s,"path":%s}\n' "$(json_string "$noesis_summary_status")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_stream_manifest_file","value":%s,"path":%s}\n' "$(json_string "$agent_manifest_file")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_events_file","value":%s,"path":%s}\n' "$(json_string "$agent_events_file")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_trace_file","value":%s,"path":%s}\n' "$(json_string "$icc_trace_file")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_trace_summary_file","value":%s,"path":%s}\n' "$(json_string "$icc_trace_summary_file")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_perf_summary_file","value":%s,"path":%s}\n' "$(json_string "$agent_perf_summary_file")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_perf_icc_evidence_file","value":%s,"path":%s}\n' "$(json_string "$agent_perf_icc_file")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_noesis_summary_file","value":%s,"path":%s}\n' "$(json_string "$agent_noesis_summary_file")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_noesis_icc_evidence_file","value":%s,"path":%s}\n' "$(json_string "$agent_noesis_icc_file")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_input_actions_file","value":%s,"path":%s}\n' "$(json_string "$agent_input_actions_file")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_input_commands_file","value":%s,"path":%s}\n' "$(json_string "$agent_input_commands_file")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_video_frame_file","value":%s,"path":%s}\n' "$(json_string "$last_agent_frame")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_audio_raw_file","value":%s,"path":%s}\n' "$(json_string "$audio_raw_file")" "$(json_string "$agent_icc_file")"
    printf '{"kind":"artifact","name":"agent_audio_metadata_file","value":%s,"path":%s}\n' "$(json_string "$audio_meta_file")" "$(json_string "$agent_icc_file")"
  } > "$agent_icc_file"
}

write_perf_summary() {
  local perf_args=("$log_file" "--out" "$perf_summary_file" "--icc-out" "$perf_icc_file")

  if [[ -n "$perf_max_average_ms" ]]; then
    perf_args+=("--max-average-ms" "$perf_max_average_ms")
  fi
  if [[ -n "$perf_max_render_ms" ]]; then
    perf_args+=("--max-render-ms" "$perf_max_render_ms")
  fi

  if python3 "$repo_root/tools/qge_perf_summary.py" "${perf_args[@]}" \
    > "$perf_stdout_file" 2> "$perf_stderr_file"; then
    perf_status="complete"
  else
    perf_status="blocked"
  fi

  if [[ -s "$perf_summary_file" ]]; then
    cp "$perf_summary_file" "$agent_perf_summary_file"
  fi
  if [[ -s "$perf_icc_file" ]]; then
    cp "$perf_icc_file" "$agent_perf_icc_file"
  fi
  agent_event "performance_summary" "$agent_perf_summary_file" "status=$perf_status"
  echo "QGE_PERF_SUMMARY status=$perf_status $perf_summary_file"
}

write_noesis_summary() {
  local -a noesis_args

  if [[ "$stream_player" != "noesis" ]]; then
    noesis_summary_status="not_requested"
    agent_event "noesis_summary" "$agent_noesis_summary_file" \
      "status=$noesis_summary_status"
    return
  fi

  noesis_args=(
    --manifest "$agent_manifest_file"
    --actions "$agent_input_actions_file"
    --commands "$agent_input_commands_file"
    --log "$agent_log_file"
    --frames-dir "$agent_video_dir"
    --plan "$noesis_plan"
    --player "$stream_player"
    --min-actions 1
    --min-commands 1
    --min-frames "$frames"
    --min-frame-mae 2.0
    --require-phase-markers
    --require-combat
    --out "$noesis_summary_file"
    --icc-out "$noesis_icc_file"
  )
  if [[ "$trace_summary_status" == "complete" && -s "$trace_summary_file" ]]; then
    noesis_args+=(--trace-summary "$trace_summary_file")
  fi

  if python3 "$repo_root/tools/qge_noesis_summary.py" "${noesis_args[@]}" \
    > "$noesis_stdout_file" 2> "$noesis_stderr_file"; then
    noesis_summary_status="pass"
  else
    noesis_summary_status="blocked"
  fi

  if [[ -s "$noesis_summary_file" ]]; then
    noesis_summary_status="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status", "blocked"))' "$noesis_summary_file" 2>/dev/null || printf '%s' "$noesis_summary_status")"
    cp "$noesis_summary_file" "$agent_noesis_summary_file"
  fi
  if [[ -s "$noesis_icc_file" ]]; then
    cp "$noesis_icc_file" "$agent_noesis_icc_file"
  fi
  agent_event "noesis_summary" "$agent_noesis_summary_file" \
    "status=$noesis_summary_status"
  echo "QGE_NOESIS_SUMMARY status=$noesis_summary_status $noesis_summary_file"
}

recover_latest_trace_pointer() {
  local current_trace_pointer=""
  local recovered_trace=""

  if [[ -s "$quake_latest_trace_file" ]]; then
    current_trace_pointer="$(tail -n 1 "$quake_latest_trace_file")"
    if [[ -n "$current_trace_pointer" && -s "$current_trace_pointer" ]]; then
      return
    fi
  fi

  recovered_trace="$(find "$quake_stream_root" -mindepth 2 -maxdepth 2 \
    -name qge_trace.bin -type f -size +0c -print 2>/dev/null | sort | tail -n 1)"
  if [[ -n "$recovered_trace" ]]; then
    printf '%s\n' "$recovered_trace" > "$quake_latest_trace_file"
  fi
}

write_trace_summary() {
  trace_summary_status="not_requested"
  trace_runtime_evidence_ready=0
  if [[ "$trace" != "1" ]]; then
    return
  fi
  trace_summary_status="requested_missing"
  if [[ ! -s "$trace_file" ]]; then
    return
  fi
  if python3 "$repo_root/tools/qge_trace_summary.py" "$trace_file" --json \
      > "$trace_summary_file" 2> "$trace_summary_stderr_file"; then
    trace_summary_status="complete"
    if grep -q '"single_trace_ready": true' "$trace_summary_file"; then
      trace_runtime_evidence_ready=1
    fi
    cp "$trace_summary_file" "$agent_trace_summary_file"
    if [[ -s "$trace_summary_stderr_file" ]]; then
      cp "$trace_summary_stderr_file" "$agent_trace_summary_stderr_file"
    else
      : > "$agent_trace_summary_stderr_file"
    fi
    agent_event "trace_summary_done" "$trace_summary_file" \
      "runtime_evidence_ready=$trace_runtime_evidence_ready"
  else
    trace_summary_status="failed"
    cp "$trace_summary_stderr_file" "$agent_trace_summary_stderr_file" 2>/dev/null || true
    agent_event "trace_summary_failed" "$trace_summary_file"
  fi
}

write_latest_stream_pointers() {
  printf '%s\n' "$agent_stream" > "$agent_latest_stream_file"
  printf '%s\n' "$agent_manifest_file" > "$agent_latest_manifest_file"
  printf '%s\n' "$agent_events_file" > "$agent_latest_events_file"
  printf '%s\n' "$agent_icc_file" > "$agent_latest_icc_file"
  printf '%s\n' "$outdir" > "$quake_latest_stream_file"
  if [[ "$trace" == "1" && -s "$trace_file" ]]; then
    printf '%s\n' "$trace_file" > "$quake_latest_trace_file"
  else
    recover_latest_trace_pointer
  fi
}

write_agent_manifest "running"
write_latest_stream_pointers
agent_event "stream_start" "$agent_stream" "outdir=$outdir"

emit_noesis_player_script() {
  QGE_NOESIS_DIR="$noesis_dir" \
    QGE_NOESIS_PLAN="$noesis_plan" \
    QGE_NOESIS_ACTIONS_FILE="$noesis_actions_file" \
    QGE_NOESIS_START_WAIT="$noesis_start_wait" \
    QGE_NOESIS_MAX_WAIT="$noesis_max_wait" \
    QGE_NOESIS_CMD="$noesis_cmd" \
    QGE_NOESIS_ACTION_TRACE_FILE="$agent_input_actions_file" \
    QGE_NOESIS_COMMAND_TRACE_FILE="$agent_input_commands_file" \
    QGE_STREAM_MAP="$map_name" \
    QGE_STREAM_FIRE_TEST="$fire_test" \
    "$noesis_player_tool"
}

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
  echo "quantum_render_threshold $render_threshold"
  echo "quantum_render_edge_gain $render_edge_gain"
  echo "quantum_render_material_gain $render_material_gain"
  echo "quantum_render_bilinear_samples $render_bilinear_samples"
  echo "quantum_render_edge_samples $render_edge_samples"
  echo "quantum_render_display_filter $render_display_filter"
  echo "quantum_render_update_interval $render_update_interval"
  echo "quantum_debug_sprite_billboard $sprite_test"
  echo "quantum_overlay_alpha $overlay_alpha"
  echo "quantum_scene_surface_budget $scene_surface_budget"
  echo "quantum_physics $physics_value"
  echo "quantum_projectiles $projectiles_value"
  echo "quantum_physics_authoritative $physics_authoritative"
  echo "quantum_particles $particles_value"
  echo "quantum_ai $ai_value"
  echo "quantum_vis $vis_value"
  if [[ "$sound" == "1" ]]; then
    echo "snd_quantum $sound_quantum_mode"
    echo "snd_quantum_source_authority $sound_source_authority"
  fi
  echo "map $map_name"
  if [[ "$stream_player" == "noesis" ]]; then
    emit_noesis_player_script
  elif [[ "$fire_test" == "1" ]]; then
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
  if [[ "$engine_capture" != "1" ]]; then
    for frame in $(seq 1 "$frames"); do
      for _ in $(seq 1 "$waits_per_frame"); do
        echo "wait"
      done
      echo "echo QGE_STREAM_CAPTURE $frame"
      echo "screenshot png"
    done
    echo "quit"
  fi
} > "$autoexec"
cp "$autoexec" "$outdir/autoexec.cfg.used"
if [[ "$stream_player" == "noesis" ]]; then
  input_action_count="$(wc -l < "$agent_input_actions_file" | tr -d ' ')"
  input_command_count="$(wc -l < "$agent_input_commands_file" | tr -d ' ')"
  agent_event "input_actions" "$agent_input_actions_file" "actions=$input_action_count"
  agent_event "input_commands" "$agent_input_commands_file" "commands=$input_command_count"
  write_agent_manifest "running"
fi

before_file="$outdir/screens.before"
seen_file="$outdir/screens.seen"
current_file="$outdir/screens.current"
new_file="$outdir/screens.new"
log_file="$outdir/quantum_quake.log"
agent_log_file="$agent_log_dir/quantum_quake.log"
runtime_log_file="$log_file"
open_log_file="$outdir/open.log"
agent_open_log_file="$agent_log_dir/open.log"
qconsole_file="$repo_root/qconsole.log"
watch_stop_file="$outdir/watch.stop"
touch "$log_file"
touch "$agent_log_file" "$agent_open_log_file"
log_next_line=1
frame_index=0
printf '0\n' > "$agent_audio_bytes_file"
printf '%d\n' "$frame_index" > "$agent_frame_count_file"

find "$gamedir" -maxdepth 1 -name 'spasm*.png' -print | sort > "$before_file"
cp "$before_file" "$seen_file"

echo "Streaming Quantum Quake graphics diagnostics"
echo "  outdir=$outdir"
echo "  agent_stream=$agent_stream"
echo "  quantum_render=$render_value quantum_render_res=$render_res quantum_render_threshold=$render_threshold edge_gain=$render_edge_gain material_gain=$render_material_gain bilinear_samples=$render_bilinear_samples edge_samples=$render_edge_samples display_filter=$render_display_filter update_interval=$render_update_interval sprite_test=$sprite_test quantum_physics=$physics_value quantum_projectiles=$projectiles_value quantum_physics_authoritative=$physics_authoritative quantum_particles=$particles_value quantum_ai=$ai_value quantum_vis=$vis_value"
echo "  map=$map_name frames=$frames waits_per_frame=$waits_per_frame timeout=${max_seconds}s fullscreen=$fullscreen display=$stream_display sound=$sound snd_quantum=$sound_quantum_mode snd_quantum_source_authority=$sound_source_authority trace=$trace replay=$replay_trace replay_strict=$replay_strict fire_test=$fire_test fire_min_start_wait=$fire_min_start_wait fire_min_frames=$fire_min_frames scene_surface_budget=$scene_surface_budget launch=$launch_mode engine_capture=$engine_capture mouse=$stream_mouse player=$stream_player noesis_plan=$noesis_plan noesis_max_wait=$noesis_max_wait"
echo "QGE_AGENT_STREAM $agent_stream"

print_log_updates() {
  local total_lines
  [[ -f "$runtime_log_file" ]] || return
  total_lines="$(wc -l < "$runtime_log_file" | tr -d ' ')"
  if (( total_lines >= log_next_line )); then
	      sed -n "${log_next_line},${total_lines}p" "$runtime_log_file" | sed -n \
	      -e '/QGE render frame=/p' \
	      -e '/QGE scene frame=/p' \
	      -e '/QGE: World registry/p' \
	      -e '/QGE: Diagnostic sprite/p' \
	      -e '/QGE: Texture signal cache/p' \
	      -e '/QGE: Lightmap signal cache/p' \
	      -e '/QGE registry /p' \
	      -e '/QGE snapshot /p' \
	      -e '/QGE physics frame=/p' \
	      -e '/QGE trace /p' \
	      -e '/QGE_NOESIS_/p' \
	      -e '/Sound Initialization/p' \
	      -e '/SDL audio/p' \
	      -e '/QGE quantum audio/p' \
	      -e '/QGE audio source/p' \
	      -e '/QGE_STREAM_CAPTURE/p' \
	      -e '/QGE_AUTO_CAPTURE/p' \
      -e '/Wrote spasm/p' \
      -e '/UNSUPPORTED/p'
    log_next_line=$((total_lines + 1))
  fi
}

publish_frame() {
  local screenshot="$1"
  local frame_name
  local agent_frame

  if [[ ! -f "$screenshot" ]]; then
    return
  fi
  frame_index=$((frame_index + 1))
  frame_name="$(printf 'frame_%03d.png' "$frame_index")"
  cp "$screenshot" "$outdir/$frame_name"
  agent_frame="$agent_video_dir/$frame_name"
  cp "$screenshot" "$agent_frame"
  last_agent_frame="$agent_frame"
  printf '%d\n' "$frame_index" > "$agent_frame_count_file"
  printf '%s\n' "$last_agent_frame" > "$agent_last_frame_file"
  agent_event "video_frame" "$agent_frame" "index=$frame_index"
  write_agent_manifest "running"
  echo "QGE_AGENT_VIDEO_FRAME $frame_index $agent_frame"
  echo "QGE_STREAM_FRAME $frame_index $outdir/$frame_name"
}

collect_new_frames() {
  find "$gamedir" -maxdepth 1 -name 'spasm*.png' -print | sort > "$current_file"
  comm -13 "$seen_file" "$current_file" > "$new_file"
  if [[ -s "$new_file" ]]; then
    while IFS= read -r screenshot; do
      publish_frame "$screenshot"
    done < "$new_file"
    cp "$current_file" "$seen_file"
  fi
}

poll_agent_audio() {
  local audio_bytes=0
  local previous_bytes=0

  if [[ ! -s "$agent_audio_raw" ]]; then
    return
  fi
  audio_bytes="$(wc -c < "$agent_audio_raw" | tr -d ' ')"
  if [[ -s "$agent_audio_bytes_file" ]]; then
    previous_bytes="$(tail -n 1 "$agent_audio_bytes_file" | tr -d ' ')"
    if [[ -z "$previous_bytes" ]]; then
      previous_bytes=0
    fi
  fi
  if (( audio_bytes == previous_bytes )); then
    return
  fi

  printf '%s\n' "$audio_bytes" > "$agent_audio_bytes_file"
  agent_event "audio_raw" "$agent_audio_raw" "bytes=$audio_bytes"
  if [[ -s "$agent_audio_meta" ]]; then
    agent_event "audio_metadata" "$agent_audio_meta" "bytes=$audio_bytes"
  fi
  write_agent_manifest "running"
}

watch_open_stream() {
  while [[ ! -f "$watch_stop_file" ]]; do
    print_log_updates
    collect_new_frames
    poll_agent_audio
    sleep 1
  done
  print_log_updates
  collect_new_frames
  poll_agent_audio
}

kill_open_run_processes() {
  local app_pid
  local app_cmd

  ps -axo pid=,command= | while read -r app_pid app_cmd; do
    [[ -n "$app_pid" ]] || continue
    if [[ "$app_cmd" == *"$app_bin"* && "$app_cmd" == *"$agent_stream"* ]]; then
      kill "$app_pid" 2>/dev/null || true
    fi
  done
}

open_run_process_exists() {
  local app_pid
  local app_cmd

  while read -r app_pid app_cmd; do
    [[ -n "$app_pid" ]] || continue
    if [[ "$app_cmd" == *"$app_bin"* && "$app_cmd" == *"$agent_stream"* ]]; then
      return 0
    fi
  done < <(ps -axo pid=,command=)
  return 1
}

activate_open_stream() {
  local attempts=0
  local status=0
  local activated=0

  if [[ "$stream_activate" != "1" ]]; then
    return
  fi
  if [[ "$(uname -s)" != "Darwin" ]]; then
    return
  fi

  while [[ ! -f "$watch_stop_file" ]]; do
    if ! open_run_process_exists; then
      sleep 0.25
      continue
    fi

    status=0
    osascript -e "tell application id \"$app_bundle_id\" to activate" \
      >> "$open_log_file" 2>&1 || status=$?
    if (( status == 0 )); then
      if (( activated == 0 )); then
        echo "QGE_OPEN_ACTIVATED bundle_id=$app_bundle_id" >> "$open_log_file"
        agent_event "open_activated" "$app_bundle" "bundle_id=$app_bundle_id"
        activated=1
      fi
    else
      echo "QGE_OPEN_ACTIVATE_FAILED status=$status bundle_id=$app_bundle_id" \
        >> "$open_log_file"
    fi

    attempts=$((attempts + 1))
    if (( attempts >= stream_activate_attempts )); then
      return
    fi
    sleep 1
  done
}

sync_agent_frame_state() {
  if [[ -s "$agent_frame_count_file" ]]; then
    frame_index="$(tail -n 1 "$agent_frame_count_file" | tr -d ' ')"
    if [[ -z "$frame_index" ]]; then
      frame_index=0
    fi
  fi
  if [[ -s "$agent_last_frame_file" ]]; then
    last_agent_frame="$(tail -n 1 "$agent_last_frame_file")"
  fi
}

video_args=(-window -width "$width" -height "$height")
if [[ "$fullscreen" == "1" ]]; then
  video_args=(-fullscreen)
fi
if [[ -n "$stream_display" ]]; then
  video_args+=(-display "$stream_display")
fi

run_args=(-nolauncher -basedir "$basedir" "${video_args[@]}")
if [[ "$stream_mouse" != "1" ]]; then
  run_args+=(-nomouse)
fi
run_args+=(-qgestreamdir "$agent_stream")
run_args+=(-qgerenderres "$render_res" -qgerenderthreshold "$render_threshold")
if [[ "$engine_capture" == "1" ]]; then
  if [[ -n "$capture_wait_override" ]]; then
    engine_capture_wait="$capture_wait_override"
  else
    engine_capture_wait="$waits_per_frame"
    if [[ "$fire_test" == "1" ]]; then
      engine_capture_wait=$((waits_per_frame * 2 / 3))
      if (( engine_capture_wait < 8 )); then
        engine_capture_wait="$waits_per_frame"
      fi
    fi
    if [[ "$stream_player" == "noesis" ]]; then
      noesis_capture_min=$((noesis_start_wait + 4))
      if (( engine_capture_wait < noesis_capture_min )); then
        engine_capture_wait="$noesis_capture_min"
      fi
    fi
  fi
  run_args+=(-qgeautocapture "$frames" -qgecapturewait "$engine_capture_wait")
fi
if [[ "$sound" != "1" ]]; then
  run_args+=(-nosound)
fi
if [[ "$trace" == "1" ]]; then
  run_args+=(-qgetrace "$trace_file")
fi
if [[ -n "$replay_trace" ]]; then
  run_args+=(-qgereplay "$replay_trace" -qgereplaystrict "$replay_strict")
fi
if [[ "$launch_mode" == "open" ]]; then
  runtime_log_file="$qconsole_file"
  : > "$runtime_log_file"
  echo "open output follows; qconsole.log is captured as the runtime log." > "$open_log_file"
  echo "QGE_OPEN_NOLAUNCHER enabled" >> "$open_log_file"
  cp "$open_log_file" "$agent_open_log_file"
  open_args=(-W -n -F)
  open_args+=("$app_bundle")
  rm -f "$watch_stop_file"
  watch_open_stream &
  watch_pid=$!
  activate_open_stream &
  activator_pid=$!
	  (
	    sleep "$max_seconds"
	    if [[ ! -f "$watch_stop_file" ]]; then
	      echo "QGE_STREAM_TIMEOUT killing app launched by open" >&2
	      kill_open_run_processes
	    fi
	  ) &
  watchdog_pid=$!
  open "${open_args[@]}" --args -ApplePersistenceIgnoreState YES "${run_args[@]}" -condebug >>"$open_log_file" 2>&1 || open_status=$?
  touch "$watch_stop_file"
  kill "$activator_pid" 2>/dev/null || true
  kill "$watchdog_pid" 2>/dev/null || true
  wait "$activator_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true
  wait "$watch_pid" 2>/dev/null || true
  sync_agent_frame_state
  if (( open_status != 0 )); then
    game_status="$open_status"
    echo "QGE_OPEN_FAILED status=$open_status" >> "$open_log_file"
    echo "QGE_OPEN_FAILED status=$open_status" >&2
    agent_event "open_failed" "$app_bundle" "status=$open_status"
  fi
elif [[ "$trace" == "1" ]]; then
  runtime_log_file="$agent_log_file"
  "$app_bin" "${run_args[@]}" >"$agent_log_file" 2>&1 &
else
  runtime_log_file="$agent_log_file"
  "$app_bin" "${run_args[@]}" >"$agent_log_file" 2>&1 &
fi

if [[ "$launch_mode" != "open" ]]; then
  game_pid=$!
  elapsed=0

  while kill -0 "$game_pid" 2>/dev/null; do
    print_log_updates
    collect_new_frames
    poll_agent_audio

    if (( elapsed >= max_seconds )); then
      echo "QGE_STREAM_TIMEOUT killing process $game_pid" >&2
      game_timed_out=1
      kill "$game_pid" 2>/dev/null || true
      break
    fi

    sleep 1
    elapsed=$((elapsed + 1))
  done

  wait "$game_pid" 2>/dev/null || game_status=$?
  print_log_updates
fi

if [[ "$launch_mode" == "open" && -f "$runtime_log_file" ]]; then
  cp "$runtime_log_file" "$log_file"
  cp "$runtime_log_file" "$agent_log_file"
  if [[ "$runtime_log_file" == "$qconsole_file" ]]; then
    rm -f "$runtime_log_file"
  fi
elif [[ -f "$agent_log_file" ]]; then
  cp "$agent_log_file" "$log_file"
fi
if [[ ! -s "$log_file" ]]; then
  agent_event "runtime_log_empty" "$log_file"
  echo "QGE_RUNTIME_LOG_EMPTY $log_file" >&2
fi
if [[ -f "$open_log_file" ]]; then
  cp "$open_log_file" "$agent_open_log_file"
fi
if [[ "$launch_mode" != "open" && "$game_status" != "0" ]]; then
  agent_event "process_exit" "$runtime_log_file" "status=$game_status"
  echo "QGE_PROCESS_EXIT status=$game_status $runtime_log_file" >&2
fi

if [[ "$launch_mode" != "open" && "$game_timed_out" == "1" ]]; then
  startup_issue="process_timeout"
elif [[ "$trace" == "1" && ! -s "$trace_file" ]]; then
  if grep -q "Couldn't create GL context" "$log_file" 2>/dev/null; then
    startup_issue="gl_context_failed"
  elif ! grep -q "Video mode .* initialized" "$log_file" 2>/dev/null; then
    startup_issue="video_init_missing"
  elif ! grep -q "QGE: Trace recording" "$log_file" 2>/dev/null; then
    startup_issue="trace_init_missing"
  fi
fi
if [[ "$launch_mode" == "open" && "$open_status" != "0" && -z "$startup_issue" ]]; then
  startup_issue="open_failed_$open_status"
elif [[ "$launch_mode" != "open" && "$game_status" != "0" && -z "$startup_issue" ]]; then
  startup_issue="process_exit_$game_status"
fi
if [[ -n "$startup_issue" ]]; then
  agent_event "startup_failed" "$log_file" "$startup_issue"
  echo "QGE_STARTUP_FAILED $startup_issue $log_file" >&2
fi

write_perf_summary
sync_agent_frame_state
collect_new_frames
poll_agent_audio
sync_agent_frame_state

if [[ "$trace" == "1" ]]; then
  if [[ -s "$trace_file" ]]; then
    trace_bytes="$(wc -c < "$trace_file" | tr -d ' ')"
    agent_event "trace_done" "$trace_file" "bytes=$trace_bytes"
    echo "QGE_TRACE_DONE $trace_file bytes=$trace_bytes"
    write_trace_summary
  else
    trace_summary_status="requested_missing"
    trace_runtime_evidence_ready=0
    agent_event "trace_missing" "$trace_file"
    echo "QGE_TRACE_MISSING $trace_file" >&2
  fi
fi

write_agent_manifest "complete"
write_noesis_summary

cat > "$outdir/README.txt" <<EOF
Quantum Quake graphics stream

Frames captured: $frame_index
Map: $map_name
Render cvar: quantum_render $render_value
Internal render resolution: $render_res
Render threshold: $render_threshold
Render edge gain: $render_edge_gain
Render material gain: $render_material_gain
Render edge samples: $render_edge_samples
Scene surface budget: $scene_surface_budget
Physics cvars: quantum_physics $physics_value, quantum_projectiles $projectiles_value, quantum_physics_authoritative $physics_authoritative, quantum_particles $particles_value
AI cvar: quantum_ai $ai_value
Visibility cvar: quantum_vis $vis_value
Fire test: $fire_test
Fire min start wait: $fire_min_start_wait
Fire min frames: $fire_min_frames
Sound quantum mode: $sound_quantum_mode
Sound source authority: $sound_source_authority
Launch mode: $launch_mode
Trace requested: $trace
Trace file: $([[ "$trace" == "1" ]] && printf '%s' "$trace_file" || printf 'not requested')
Trace summary: $([[ "$trace" == "1" ]] && printf '%s' "$trace_summary_file" || printf 'not requested')
Trace summary status: $trace_summary_status
Runtime evidence ready: $trace_runtime_evidence_ready
Replay trace: $([[ -n "$replay_trace" ]] && printf '%s' "$replay_trace" || printf 'not requested')
Replay strict: $replay_strict
Timeout seconds: $max_seconds
Log: $log_file
Performance summary: $perf_summary_file
Performance ICC evidence: $perf_icc_file
Performance status: $perf_status
Noesis summary: $noesis_summary_file
Noesis ICC evidence: $noesis_icc_file
Noesis status: $noesis_summary_status
Agent stream: $agent_stream
Agent manifest: $agent_manifest_file
Agent events: $agent_events_file
Agent video frames: $agent_video_dir
Agent audio raw: $agent_audio_raw
Engine auto capture: $engine_capture
Autoexec used: $outdir/autoexec.cfg.used
EOF

poll_agent_audio
agent_event "stream_done" "$outdir" "frames=$frame_index"
write_agent_manifest "complete"
write_agent_icc_evidence
write_latest_stream_pointers
echo "QGE_AGENT_STREAM_DONE $agent_stream"
echo "QGE_STREAM_DONE $outdir frames=$frame_index"
