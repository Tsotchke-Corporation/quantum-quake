#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/qge-noesis-contract.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

grep -q 'stream_mouse="${QGE_STREAM_MOUSE:-0}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'stream_display="${QGE_STREAM_DISPLAY:-1}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'run_args+=(-nomouse)' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'video_args+=(-display "$stream_display")' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'stream_mouse="${QGE_STREAM_MOUSE:-0}"' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'stream_display="${QGE_STREAM_DISPLAY:-1}"' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'run_args+=(-nomouse)' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'run_args+=(-display "$stream_display")' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'stream_player="${QGE_STREAM_PLAYER:-noesis}"' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'emit_noesis_player_script' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'quantum_render_update_interval \$render_update_interval' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'input/noesis_actions.txt' "$repo_root/docs/qge_agent_stream.md"

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

echo "Noesis input contract: PASSED"
