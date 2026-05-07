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
render_res="${QGE_RENDER_RES:-1024}"
render_threshold="${QGE_RENDER_THRESHOLD:-0.001}"
render_edge_gain="${QGE_RENDER_EDGE_GAIN:-0.06}"
render_material_gain="${QGE_RENDER_MATERIAL_GAIN:-0.18}"
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
engine_capture="${QGE_STREAM_ENGINE_CAPTURE:-1}"
launch_mode="${QGE_STREAM_LAUNCH:-auto}"

if [[ "$launch_mode" == "auto" ]]; then
  case "$(uname -s)" in
    Darwin) launch_mode="open" ;;
    *) launch_mode="direct" ;;
  esac
fi
if [[ "$engine_capture" == "1" ]]; then
  engine_capture=1
else
  engine_capture=0
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
agent_stream="${QGE_AGENT_STREAM_DIR:-$repo_root/diagnostics/agent_stream/$stamp}"
agent_video_dir="$agent_stream/video/frames"
agent_audio_dir="$agent_stream/audio"
agent_log_dir="$agent_stream/logs"
agent_events_file="$agent_stream/events.ndjson"
agent_manifest_file="$agent_stream/manifest.json"
agent_icc_file="$agent_stream/qge_agent_stream_icc_evidence.jsonl"
agent_audio_raw="$agent_audio_dir/quake_mix_s16le.raw"
agent_audio_meta="$agent_audio_dir/quake_mix_s16le.json"
agent_frame_count_file="$agent_stream/video/frame_count.txt"
agent_last_frame_file="$agent_stream/video/latest_frame.txt"
last_agent_frame=""
mkdir -p "$outdir" "$agent_video_dir" "$agent_audio_dir" "$agent_log_dir"
: > "$agent_events_file"
: > "$agent_frame_count_file"
: > "$agent_last_frame_file"

agent_event() {
  local event="$1"
  local path="${2:-}"
  local detail="${3:-}"
  printf '{"ts":"%s","event":"%s","path":"%s","detail":"%s"}\n' \
    "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$event" "$path" "$detail" \
    >> "$agent_events_file"
}

write_agent_manifest() {
  local status="$1"
  local audio_status="disabled"
  local audio_bytes=0
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
  cat > "$agent_manifest_file" <<EOF
{
  "schema": "qge.agent_stream.v0",
  "status": "$status",
  "stream_dir": "$agent_stream",
  "capture_dir": "$outdir",
  "map": "$map_name",
  "frames_requested": $frames,
  "waits_per_frame": $waits_per_frame,
  "engine_capture": $engine_capture,
  "window": {"width": $width, "height": $height, "fullscreen": $fullscreen},
  "sound_requested": $sound,
  "trace_requested": $trace,
  "render": {
    "quantum_render": $render_value,
    "quantum_render_res": $render_res,
    "quantum_render_threshold": "$render_threshold",
    "quantum_render_edge_gain": "$render_edge_gain",
    "quantum_render_material_gain": "$render_material_gain"
  },
  "video": {
    "frames_dir": "$agent_video_dir",
    "frame_count_file": "$agent_frame_count_file",
    "latest_frame_file": "$agent_last_frame_file",
    "format": "png"
  },
  "audio": {
    "status": "$audio_status",
    "raw_file": "$agent_audio_raw",
    "metadata_file": "$agent_audio_meta",
    "format": "s16le",
    "bytes": $audio_bytes
  },
  "logs": {
    "runtime_log": "$agent_log_dir/quantum_quake.log",
    "open_log": "$agent_log_dir/open.log",
    "events": "$agent_events_file"
  },
  "icc_evidence": "$agent_icc_file",
  "trace": "$outdir/qge_trace.bin"
}
EOF
}

write_agent_icc_evidence() {
  local audio_raw_file=""
  local audio_meta_file=""
  if [[ -s "$agent_audio_raw" ]]; then
    audio_raw_file="$agent_audio_raw"
  fi
  if [[ -s "$agent_audio_meta" ]]; then
    audio_meta_file="$agent_audio_meta"
  fi
  {
    printf '{"kind":"runtime_backend","name":"runtime_backend","value":"qge_agent_media_stream","path":"%s"}\n' "$agent_icc_file"
    printf '{"kind":"completion_condition","name":"completion_reason","value":"qge_agent_media_stream_complete","path":"%s"}\n' "$agent_icc_file"
    printf '{"kind":"artifact","name":"agent_stream_manifest_file","value":"%s","path":"%s"}\n' "$agent_manifest_file" "$agent_icc_file"
    printf '{"kind":"artifact","name":"agent_events_file","value":"%s","path":"%s"}\n' "$agent_events_file" "$agent_icc_file"
    printf '{"kind":"artifact","name":"agent_video_frame_file","value":"%s","path":"%s"}\n' "$last_agent_frame" "$agent_icc_file"
    printf '{"kind":"artifact","name":"agent_audio_raw_file","value":"%s","path":"%s"}\n' "$audio_raw_file" "$agent_icc_file"
    printf '{"kind":"artifact","name":"agent_audio_metadata_file","value":"%s","path":"%s"}\n' "$audio_meta_file" "$agent_icc_file"
  } > "$agent_icc_file"
}

write_agent_manifest "running"
agent_event "stream_start" "$agent_stream" "outdir=$outdir"

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
trace_file="$outdir/qge_trace.bin"
watch_stop_file="$outdir/watch.stop"
touch "$log_file"
touch "$agent_log_file" "$agent_open_log_file"
log_next_line=1
frame_index=0
printf '%d\n' "$frame_index" > "$agent_frame_count_file"

find "$gamedir" -maxdepth 1 -name 'spasm*.png' -print | sort > "$before_file"
cp "$before_file" "$seen_file"

echo "Streaming Quantum Quake graphics diagnostics"
echo "  outdir=$outdir"
echo "  agent_stream=$agent_stream"
echo "  quantum_render=$render_value quantum_render_res=$render_res quantum_render_threshold=$render_threshold edge_gain=$render_edge_gain material_gain=$render_material_gain quantum_physics=$physics_value quantum_projectiles=$projectiles_value quantum_particles=$particles_value"
echo "  map=$map_name frames=$frames waits_per_frame=$waits_per_frame fullscreen=$fullscreen sound=$sound trace=$trace fire_test=$fire_test scene_surface_budget=$scene_surface_budget launch=$launch_mode engine_capture=$engine_capture"
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
	      -e '/QGE registry /p' \
	      -e '/QGE snapshot /p' \
	      -e '/QGE physics frame=/p' \
	      -e '/QGE trace /p' \
	      -e '/Sound Initialization/p' \
	      -e '/SDL audio/p' \
	      -e '/QGE quantum audio/p' \
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

watch_open_stream() {
  while [[ ! -f "$watch_stop_file" ]]; do
    print_log_updates
    collect_new_frames
    sleep 1
  done
  print_log_updates
  collect_new_frames
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

run_args=(-basedir "$basedir" "${video_args[@]}")
run_args+=(-qgestreamdir "$agent_stream")
if [[ "$engine_capture" == "1" ]]; then
  engine_capture_wait="$waits_per_frame"
  if [[ "$fire_test" == "1" ]]; then
    engine_capture_wait=$((engine_capture_wait + 24))
  fi
  run_args+=(-qgeautocapture "$frames" -qgecapturewait "$engine_capture_wait")
fi
if [[ "$sound" != "1" ]]; then
  run_args+=(-nosound)
fi
if [[ "$trace" == "1" ]]; then
  run_args+=(-qgetrace "$trace_file")
fi

if [[ "$launch_mode" == "open" ]]; then
  runtime_log_file="$qconsole_file"
  : > "$runtime_log_file"
  echo "open output is not redirected; qconsole.log is captured as the runtime log." > "$open_log_file"
  cp "$open_log_file" "$agent_open_log_file"
  open_args=(-W -n)
  open_args+=("$app_bundle")
  rm -f "$watch_stop_file"
  watch_open_stream &
  watch_pid=$!
  open_status=0
  open "${open_args[@]}" --args "${run_args[@]}" -condebug || open_status=$?
  touch "$watch_stop_file"
  wait "$watch_pid" 2>/dev/null || true
  sync_agent_frame_state
  if (( open_status != 0 )); then
    echo "QGE_OPEN_FAILED status=$open_status" >> "$open_log_file"
    echo "QGE_OPEN_FAILED status=$open_status" >&2
    agent_event "open_failed" "$app_bundle" "status=$open_status"
  fi
  print_log_updates
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
  max_seconds=$((60 + frames * waits_per_frame / 20))

  while kill -0 "$game_pid" 2>/dev/null; do
    print_log_updates
    collect_new_frames

    if (( elapsed >= max_seconds )); then
      echo "QGE_STREAM_TIMEOUT killing process $game_pid" >&2
      kill "$game_pid" 2>/dev/null || true
      break
    fi

    sleep 1
    elapsed=$((elapsed + 1))
  done

  wait "$game_pid" 2>/dev/null || true
  print_log_updates
fi

if [[ "$launch_mode" == "open" && -f "$runtime_log_file" ]]; then
  cp "$runtime_log_file" "$log_file"
  cp "$runtime_log_file" "$agent_log_file"
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

sync_agent_frame_state
collect_new_frames
sync_agent_frame_state

cat > "$outdir/README.txt" <<EOF
Quantum Quake graphics stream

Frames captured: $frame_index
Map: $map_name
Render cvar: quantum_render $render_value
Internal render resolution: $render_res
Render threshold: $render_threshold
Render edge gain: $render_edge_gain
Render material gain: $render_material_gain
Scene surface budget: $scene_surface_budget
Physics cvars: quantum_physics $physics_value, quantum_projectiles $projectiles_value, quantum_particles $particles_value
Fire test: $fire_test
Launch mode: $launch_mode
Trace: $trace_file
Log: $log_file
Agent stream: $agent_stream
Agent manifest: $agent_manifest_file
Agent events: $agent_events_file
Agent video frames: $agent_video_dir
Agent audio raw: $agent_audio_raw
Engine auto capture: $engine_capture
Autoexec used: $outdir/autoexec.cfg.used
EOF

if [[ "$trace" == "1" ]]; then
  if [[ -s "$trace_file" ]]; then
    trace_bytes="$(wc -c < "$trace_file" | tr -d ' ')"
    agent_event "trace_done" "$trace_file" "bytes=$trace_bytes"
    echo "QGE_TRACE_DONE $trace_file bytes=$trace_bytes"
  else
    agent_event "trace_missing" "$trace_file"
    echo "QGE_TRACE_MISSING $trace_file" >&2
  fi
fi

if [[ -s "$agent_audio_raw" ]]; then
  audio_bytes="$(wc -c < "$agent_audio_raw" | tr -d ' ')"
  agent_event "audio_raw" "$agent_audio_raw" "bytes=$audio_bytes"
fi
agent_event "stream_done" "$outdir" "frames=$frame_index"
write_agent_manifest "complete"
write_agent_icc_evidence
echo "QGE_AGENT_STREAM_DONE $agent_stream"
echo "QGE_STREAM_DONE $outdir frames=$frame_index"
