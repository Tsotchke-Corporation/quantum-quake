#!/usr/bin/env bash
set -euo pipefail

noesis_dir="${QGE_NOESIS_DIR:-$HOME/Desktop/noesis}"
plan="${QGE_NOESIS_PLAN:-patrol}"
actions_file="${QGE_NOESIS_ACTIONS_FILE:-}"
start_wait="${QGE_NOESIS_START_WAIT:-16}"
noesis_cmd="${QGE_NOESIS_CMD:-}"

emit_waits() {
  local count="${1:-1}"
  local i=0

  case "$count" in
    ''|*[!0-9]*) count=1 ;;
  esac
  if (( count < 1 )); then
    count=1
  fi

  while (( i < count )); do
    echo "wait"
    i=$((i + 1))
  done
}

hold_command() {
  local command="$1"
  local count="${2:-1}"

  echo "+$command"
  emit_waits "$count"
  echo "-$command"
}

emit_action() {
  local raw="$1"
  local line
  local action
  local arg
  local rest

  line="${raw%%#*}"
  line="$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  if [[ -z "$line" ]]; then
    return
  fi

  action="${line%%[[:space:]]*}"
  if [[ "$action" == "$line" ]]; then
    arg=""
    rest=""
  else
    read -r action arg rest <<< "$line"
  fi
  action="$(printf '%s' "$action" | tr '[:upper:]' '[:lower:]')"

  case "$action" in
    wait|sleep)
      emit_waits "${arg:-1}"
      ;;
    forward|up|north|thrust-forward)
      hold_command "forward" "${arg:-1}"
      ;;
    back|backward|down|south|thrust-back)
      hold_command "back" "${arg:-1}"
      ;;
    turn-left|rotate-left|yaw-left|left)
      hold_command "left" "${arg:-1}"
      ;;
    turn-right|rotate-right|yaw-right|right)
      hold_command "right" "${arg:-1}"
      ;;
    strafe-left|move-left|west)
      hold_command "moveleft" "${arg:-1}"
      ;;
    strafe-right|move-right|east)
      hold_command "moveright" "${arg:-1}"
      ;;
    attack|fire|shoot)
      hold_command "attack" "${arg:-1}"
      ;;
    weapon|impulse)
      echo "impulse ${arg:-7}"
      ;;
    give)
      if [[ -n "${arg:-}" && -n "${rest:-}" ]]; then
        echo "give $arg $rest"
      elif [[ -n "${arg:-}" ]]; then
        echo "give $arg"
      fi
      ;;
    cmd|quake)
      if [[ -n "${arg:-}" && -n "${rest:-}" ]]; then
        echo "$arg $rest"
      elif [[ -n "${arg:-}" ]]; then
        echo "$arg"
      fi
      ;;
    +forward|+back|+left|+right|+moveleft|+moveright|+attack|-forward|-back|-left|-right|-moveleft|-moveright|-attack)
      echo "$line"
      ;;
    *)
      echo "echo QGE_NOESIS_PLAYER skipped_unknown_action=$action"
      ;;
  esac
}

emit_builtin_plan() {
  case "$plan" in
    scout)
      emit_action "forward 18"
      emit_action "turn-right 8"
      emit_action "forward 18"
      ;;
    fire)
      emit_action "give 7"
      emit_action "give r 100"
      emit_action "weapon 7"
      emit_action "wait 8"
      emit_action "attack 8"
      emit_action "wait 8"
      emit_action "turn-right 6"
      emit_action "attack 8"
      ;;
    patrol|*)
      emit_action "forward 12"
      emit_action "turn-right 6"
      emit_action "forward 12"
      emit_action "turn-left 6"
      emit_action "give 7"
      emit_action "give r 100"
      emit_action "weapon 7"
      emit_action "wait 4"
      emit_action "attack 6"
      ;;
  esac
}

emit_start() {
  local source="$1"
  local detail="${2:-}"

  echo "echo QGE_NOESIS_PLAYER start dir=$noesis_dir status=$noesis_status source=$source plan=$plan start_wait=$start_wait${detail:+ $detail}"
  if (( start_wait > 0 )); then
    emit_waits "$start_wait"
  fi
}

emit_actions_from_file() {
  local path="$1"

  while IFS= read -r line || [[ -n "$line" ]]; do
    emit_action "$line"
  done < "$path"
}

noesis_status="missing"
if [[ -d "$noesis_dir" ]]; then
  noesis_status="present"
fi
case "$start_wait" in
  ''|*[!0-9]*) start_wait=16 ;;
esac

if [[ -n "$noesis_cmd" ]]; then
  emit_start "cmd" "provider=QGE_NOESIS_CMD"
  cmd_output="$(mktemp "${TMPDIR:-/tmp}/qge-noesis-actions.XXXXXX")"
  cmd_status=0
  set +e
  (cd "$noesis_dir" 2>/dev/null || cd /; bash -lc "$noesis_cmd") > "$cmd_output"
  cmd_status=$?
  set -e
  if (( cmd_status != 0 )); then
    echo "echo QGE_NOESIS_PLAYER command_failed status=$cmd_status"
  fi
  if [[ -s "$cmd_output" ]]; then
    emit_actions_from_file "$cmd_output"
  else
    echo "echo QGE_NOESIS_PLAYER empty_command_output"
    emit_builtin_plan
  fi
  rm -f "$cmd_output"
elif [[ -n "$actions_file" ]]; then
  emit_start "file" "actions=$actions_file"
  if [[ -f "$actions_file" ]]; then
    emit_actions_from_file "$actions_file"
  else
    echo "echo QGE_NOESIS_PLAYER missing_actions_file=$actions_file"
    emit_builtin_plan
  fi
else
  emit_start "builtin"
  emit_builtin_plan
fi
echo "echo QGE_NOESIS_PLAYER done"
