#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/qge-noesis-contract.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

grep -q 'stream_mouse="${QGE_STREAM_MOUSE:-0}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'stream_display="${QGE_STREAM_DISPLAY:-1}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'run_args+=(-nomouse)' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'video_args+=(-display "$stream_display")' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'latest_icc_evidence.txt' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'write_latest_stream_pointers' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'recover_latest_trace_pointer' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'if [[ "$trace" == "1" && -s "$trace_file" ]]; then' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'find "$quake_stream_root" -mindepth 2 -maxdepth 2' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'latest non-empty trace file' "$repo_root/docs/qge_agent_stream.md"
grep -q 'repairs it from the newest existing non-empty' "$repo_root/docs/qge_agent_stream.md"
grep -q 'timeout_seconds="${QGE_STREAM_TIMEOUT_SECONDS:-}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'normalize_positive_int' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'width="$(normalize_positive_int "$width" 800)"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'render_res="$(normalize_positive_int "$render_res" 1024)"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'sound="$(normalize_bool "$sound")"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'trace="$(normalize_bool "$trace")"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'frames="$(normalize_positive_int "$frames" 12)"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'waits_per_frame="$(normalize_positive_int "$waits_per_frame" 20)"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'capture_wait_override=""' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'frames="$(normalize_positive_int "$frames" 1)"' "$repo_root/tools/quake_graphics_harness.sh"
grep -Fq 'waits_per_frame="$(normalize_positive_int "$waits_per_frame" 90)"' "$repo_root/tools/quake_graphics_harness.sh"
grep -Fq 'width="$(normalize_positive_int "$width" 800)"' "$repo_root/tools/quake_graphics_harness.sh"
grep -q -- '--check-deps' "$repo_root/tools/qge_image_metrics.py"
grep -Fq 'python3 tools/qge_image_metrics.py --check-deps' "$repo_root/tools/quake_graphics_harness.sh"
grep -q 'numpy and Pillow' "$repo_root/docs/qge_agent_stream.md"
grep -q '"timeout_seconds": \$max_seconds' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'agent_event "process_exit"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'startup_issue="process_exit_\$game_status"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'stream_mouse="${QGE_STREAM_MOUSE:-0}"' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'stream_display="${QGE_STREAM_DISPLAY:-1}"' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'run_args+=(-nomouse)' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'run_args+=(-display "$stream_display")' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'stream_player="${QGE_STREAM_PLAYER:-noesis}"' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'emit_noesis_player_script' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'normalize_nonnegative_int' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'seconds="$(normalize_nonnegative_int "$seconds" 90)"' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'width="$(normalize_positive_int "$width" 800)"' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'sound="$(normalize_bool "$sound")"' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'quantum_render_update_interval \$render_update_interval' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'timed_out=1' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'exit_status=\$?' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'QGE_CRASH_WATCH_TIMEOUT status=\$exit_status' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'QGE_CRASH_WATCH_DONE status=\$exit_status' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'input/noesis_actions.txt' "$repo_root/docs/qge_agent_stream.md"
grep -q 'diagnostics/agent_stream/latest_stream.txt' "$repo_root/docs/qge_agent_stream.md"
grep -q 'QGE_STREAM_TIMEOUT_SECONDS' "$repo_root/docs/qge_agent_stream.md"
grep -q 'child process exit status' "$repo_root/docs/qge_agent_stream.md"
grep -q 'process exit status in its final' "$repo_root/docs/qge_agent_stream.md"
grep -q 'QGE_NOESIS_MAX_WAIT' "$repo_root/tools/noesis_quake_player.sh"
grep -q 'wait_clamped requested=' "$repo_root/tools/noesis_quake_player.sh"
grep -q 'QGE_NOESIS_MAX_WAIT' "$repo_root/docs/qge_agent_stream.md"
grep -Fq 'noesis_max_wait="${QGE_NOESIS_MAX_WAIT:-600}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq '"noesis_max_wait": $noesis_max_wait' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'QGE_NOESIS_MAX_WAIT="$noesis_max_wait"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'QGE_NOESIS_MAX_WAIT="$noesis_max_wait"' "$repo_root/tools/quake_crash_watch.sh"

python3 "$repo_root/tools/qge_image_metrics.py" --help > "$tmpdir/image_metrics_help.txt"
grep -q -- '--check-deps' "$tmpdir/image_metrics_help.txt"

actions_file="$tmpdir/actions.txt"
commands_file="$tmpdir/commands.cfg"
stdout_file="$tmpdir/stdout.cfg"

QGE_NOESIS_DIR="$repo_root" \
QGE_NOESIS_PLAN=map-scout \
QGE_STREAM_MAP=e1m1 \
QGE_NOESIS_CMD="$repo_root/tools/noesis_quake_policy.sh" \
QGE_NOESIS_START_WAIT=0 \
QGE_NOESIS_ACTION_TRACE_FILE="$actions_file" \
QGE_NOESIS_COMMAND_TRACE_FILE="$commands_file" \
  "$repo_root/tools/noesis_quake_player.sh" > "$stdout_file"

cmp -s "$stdout_file" "$commands_file"

grep -q '^cmd echo QGE_NOESIS_POLICY .*map=e1m1 plan=map-scout' "$actions_file"
grep -q '^forward 8$' "$actions_file"
grep -q '^weapon 7$' "$actions_file"
grep -q '^attack 8$' "$actions_file"
grep -q '^cmd echo QGE_NOESIS_POLICY done$' "$actions_file"

grep -q '^echo QGE_NOESIS_PLAYER start .*source=cmd .*start_wait=0' "$commands_file"
grep -q '^echo QGE_NOESIS_POLICY .*map=e1m1 plan=map-scout' "$commands_file"
grep -q '^+forward$' "$commands_file"
grep -q '^-forward$' "$commands_file"
grep -q '^impulse 7$' "$commands_file"
grep -q '^+attack$' "$commands_file"
grep -q '^-attack$' "$commands_file"
grep -q '^echo QGE_NOESIS_PLAYER done$' "$commands_file"

action_count="$(wc -l < "$actions_file" | tr -d ' ')"
command_count="$(wc -l < "$commands_file" | tr -d ' ')"
if [[ "$action_count" != "13" ]]; then
  echo "expected 13 Noesis action lines, got $action_count" >&2
  exit 1
fi
if (( command_count < 50 )); then
  echo "expected translated Quake command trace, got only $command_count lines" >&2
  exit 1
fi

override_actions="$tmpdir/override-actions.txt"
override_commands="$tmpdir/override-commands.cfg"
override_stdout="$tmpdir/override-stdout.cfg"
provider_file="$tmpdir/provider.sh"
actions_input="$tmpdir/input-actions.txt"

printf '%s\n' 'attack 3' > "$actions_input"
cat > "$provider_file" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' 'forward 1'
EOF
chmod +x "$provider_file"

QGE_NOESIS_DIR="$repo_root" \
QGE_NOESIS_ACTIONS_FILE="$actions_input" \
QGE_NOESIS_CMD="$provider_file" \
QGE_NOESIS_START_WAIT=0 \
QGE_NOESIS_ACTION_TRACE_FILE="$override_actions" \
QGE_NOESIS_COMMAND_TRACE_FILE="$override_commands" \
  "$repo_root/tools/noesis_quake_player.sh" > "$override_stdout"

cmp -s "$override_stdout" "$override_commands"
grep -q '^forward 1$' "$override_actions"
grep -q '^+forward$' "$override_commands"
if grep -q '^+attack$' "$override_commands"; then
  echo "QGE_NOESIS_ACTIONS_FILE unexpectedly overrode QGE_NOESIS_CMD" >&2
  exit 1
fi

clamp_actions="$tmpdir/clamp-actions.txt"
clamp_trace="$tmpdir/clamp-trace.txt"
clamp_commands="$tmpdir/clamp-commands.cfg"
clamp_stdout="$tmpdir/clamp-stdout.cfg"
printf '%s\n' 'wait 0008' > "$clamp_actions"

QGE_NOESIS_DIR="$repo_root" \
QGE_NOESIS_ACTIONS_FILE="$clamp_actions" \
QGE_NOESIS_START_WAIT=0 \
QGE_NOESIS_MAX_WAIT=3 \
QGE_NOESIS_ACTION_TRACE_FILE="$clamp_trace" \
QGE_NOESIS_COMMAND_TRACE_FILE="$clamp_commands" \
  "$repo_root/tools/noesis_quake_player.sh" > "$clamp_stdout"

cmp -s "$clamp_stdout" "$clamp_commands"
grep -q '^wait 0008$' "$clamp_trace"
grep -q '^echo QGE_NOESIS_PLAYER wait_clamped requested=8 max=3$' "$clamp_commands"
clamped_wait_count="$(grep -c '^wait$' "$clamp_commands" | tr -d ' ')"
if [[ "$clamped_wait_count" != "3" ]]; then
  echo "expected clamped wait count 3, got $clamped_wait_count" >&2
  exit 1
fi

echo "Noesis input contract: PASSED"
