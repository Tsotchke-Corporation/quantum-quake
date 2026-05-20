#!/usr/bin/env bash
set -euo pipefail

noesis_dir="${QGE_NOESIS_DIR:-$HOME/Desktop/noesis}"
plan="${QGE_NOESIS_PLAN:-adaptive}"
map_name="${QGE_STREAM_MAP:-start}"
actions_file="${QGE_NOESIS_ACTIONS_FILE:-}"
start_wait="${QGE_NOESIS_START_WAIT:-16}"
max_wait="${QGE_NOESIS_MAX_WAIT:-600}"
noesis_cmd="${QGE_NOESIS_CMD:-}"
action_trace_file="${QGE_NOESIS_ACTION_TRACE_FILE:-}"
command_trace_file="${QGE_NOESIS_COMMAND_TRACE_FILE:-}"

emit_command() {
  printf '%s\n' "$*"
  if [[ -n "$command_trace_file" ]]; then
    printf '%s\n' "$*" >> "$command_trace_file"
  fi
}

record_action() {
  if [[ -n "$action_trace_file" ]]; then
    printf '%s\n' "$*" >> "$action_trace_file"
  fi
}

emit_passthrough_command() {
  local command="$*"
  local phase

  emit_command "$command"
  if [[ "$command" == echo\ QGE_NOESIS_PHASE* ]]; then
    phase="${command#echo QGE_NOESIS_PHASE }"
    if [[ -n "$phase" && "$phase" != "$command" ]]; then
      emit_command "qge_noesis_phase $phase"
    fi
  fi
}

emit_waits() {
  local count="${1:-1}"
  local i=0

  case "$count" in
    ''|*[!0-9]*) count=1 ;;
  esac
  count="$((10#$count))"
  if (( count < 1 )); then
    count=1
  fi
  if (( count > max_wait )); then
    emit_command "echo QGE_NOESIS_PLAYER wait_clamped requested=$count max=$max_wait"
    count="$max_wait"
  fi

  while (( i < count )); do
    emit_command "wait"
    i=$((i + 1))
  done
}

hold_command() {
  local command="$1"
  local count="${2:-1}"

  hold_command_set "$count" "$command"
}

hold_command_set() {
  local count="${1:-1}"
  shift || true
  local -a commands=("$@")
  local command
  local i

  if (( ${#commands[@]} == 0 )); then
    emit_waits "$count"
    return
  fi

  for command in "${commands[@]}"; do
    emit_command "+$command"
  done
  emit_waits "$count"
  for (( i=${#commands[@]} - 1; i >= 0; i-- )); do
    emit_command "-${commands[$i]}"
  done
}

clear_held_commands() {
  local -a commands=(
    attack forward back left right moveleft moveright
    jump use speed strafe moveup movedown lookup lookdown klook mlook
  )
  local command

  for command in "${commands[@]}"; do
    emit_command "-$command"
  done
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
  record_action "$line"

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
    jump|hop)
      hold_command "jump" "${arg:-1}"
      ;;
    use|activate)
      hold_command "use" "${arg:-1}"
      ;;
    speed|run)
      hold_command "speed" "${arg:-1}"
      ;;
    strafe)
      hold_command "strafe" "${arg:-1}"
      ;;
    swim-up|move-up|rise)
      hold_command "moveup" "${arg:-1}"
      ;;
    swim-down|move-down|drop)
      hold_command "movedown" "${arg:-1}"
      ;;
    look-up|lookup)
      hold_command "lookup" "${arg:-1}"
      ;;
    look-down|lookdown)
      hold_command "lookdown" "${arg:-1}"
      ;;
    center-view|centerview)
      emit_command "centerview"
      ;;
    attack|fire|shoot)
      hold_command "attack" "${arg:-1}"
      ;;
    run-forward|sprint-forward|charge)
      hold_command_set "${arg:-1}" "speed" "forward"
      ;;
    wall-slide-left|route-left|corridor-left)
      hold_command_set "${arg:-1}" "speed" "forward" "moveleft"
      ;;
    wall-slide-right|route-right|corridor-right)
      hold_command_set "${arg:-1}" "speed" "forward" "moveright"
      ;;
    jump-forward|hop-forward)
      hold_command_set "${arg:-1}" "jump" "forward"
      ;;
    speed-jump-forward|run-jump-forward|jump-run-forward)
      hold_command_set "${arg:-1}" "speed" "jump" "forward"
      ;;
    door-open|use-bump|open-door)
      hold_command_set "${arg:-8}" "speed" "forward" "use"
      clear_held_commands
      emit_waits 1
      hold_command "back" 2
      emit_command "centerview"
      ;;
    door-bump|door-push|bump-door)
      hold_command_set "${arg:-8}" "speed" "forward"
      clear_held_commands
      emit_waits 1
      hold_command "back" 2
      emit_command "centerview"
      ;;
    advance-fire|fire-forward|push-fire|attack-move)
      hold_command_set "${arg:-1}" "forward" "attack"
      ;;
    retreat-fire|kite-back)
      hold_command_set "${arg:-1}" "back" "attack"
      ;;
    strafe-fire-left|fire-strafe-left)
      hold_command_set "${arg:-1}" "moveleft" "attack"
      ;;
    strafe-fire-right|fire-strafe-right)
      hold_command_set "${arg:-1}" "moveright" "attack"
      ;;
    circle-left)
      hold_command_set "${arg:-1}" "moveleft" "right"
      ;;
    circle-right)
      hold_command_set "${arg:-1}" "moveright" "left"
      ;;
    circle-fire-left|circle-strafe-left)
      hold_command_set "${arg:-1}" "moveleft" "right" "attack"
      ;;
    circle-fire-right|circle-strafe-right)
      hold_command_set "${arg:-1}" "moveright" "left" "attack"
      ;;
    clear-input|release-all|stop)
      clear_held_commands
      if [[ -n "${arg:-}" ]]; then
        emit_waits "$arg"
      fi
      ;;
    weapon|impulse)
      emit_command "impulse ${arg:-7}"
      ;;
    weapon-next|next-weapon)
      emit_command "impulse 10"
      ;;
    weapon-prev|prev-weapon|previous-weapon)
      emit_command "impulse 12"
      ;;
    give)
      if [[ -n "${arg:-}" && -n "${rest:-}" ]]; then
        emit_command "give $arg $rest"
      elif [[ -n "${arg:-}" ]]; then
        emit_command "give $arg"
      fi
      ;;
    cmd|quake)
      if [[ -n "${arg:-}" && -n "${rest:-}" ]]; then
        emit_passthrough_command "$arg $rest"
      elif [[ -n "${arg:-}" ]]; then
        emit_passthrough_command "$arg"
      fi
      ;;
    +forward|+back|+left|+right|+moveleft|+moveright|+attack|+jump|+use|+speed|+moveup|+movedown|+lookup|+lookdown|-forward|-back|-left|-right|-moveleft|-moveright|-attack|-jump|-use|-speed|-moveup|-movedown|-lookup|-lookdown)
      emit_command "$line"
      ;;
    *)
      emit_command "echo QGE_NOESIS_PLAYER skipped_unknown_action=$action"
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
    map-scout)
      case "$map_name" in
        e1m1)
          emit_action "forward 8"
          emit_action "turn-right 4"
          emit_action "forward 6"
          emit_action "give 7"
          emit_action "give r 100"
          emit_action "weapon 7"
          emit_action "wait 8"
          emit_action "attack 8"
          emit_action "wait 8"
          emit_action "turn-right 6"
          emit_action "attack 8"
          ;;
        *)
          emit_action "forward 18"
          emit_action "turn-right 8"
          emit_action "forward 18"
          ;;
      esac
      ;;
    combat|combat-scout|combat-explore|adaptive)
      emit_action "weapon 2"
      emit_action "wait 4"
      emit_action "advance-fire 10"
      emit_action "circle-fire-left 8"
      emit_action "circle-fire-right 8"
      emit_action "wall-slide-right 10"
      emit_action "wall-slide-left 8"
      emit_action "speed-jump-forward 4"
      emit_action "turn-right 5"
      emit_action "advance-fire 12"
      emit_action "strafe-fire-left 6"
      emit_action "strafe-fire-right 6"
      emit_action "clear-input 2"
      ;;
    e1m1-route-push|route-push)
      emit_action "weapon 2"
      emit_action "center-view"
      emit_action "wait 6"
      emit_action "advance-fire 12"
      emit_action "wall-slide-right 12"
      emit_action "circle-fire-left 6"
      emit_action "run-forward 10"
      emit_action "wall-slide-left 12"
      emit_action "speed-jump-forward 4"
      emit_action "advance-fire 10"
      emit_action "clear-input 2"
      emit_action "wall-slide-right 10"
      emit_action "door-bump 8"
      emit_action "wall-slide-left 8"
      emit_action "advance-fire 14"
      emit_action "circle-fire-right 8"
      emit_action "clear-input 2"
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

  emit_command "echo QGE_NOESIS_PLAYER start dir=$noesis_dir status=$noesis_status source=$source plan=$plan start_wait=$start_wait${detail:+ $detail}"
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

run_noesis_cmd() {
  local workdir="$noesis_dir"
  local -a cmd_argv

  if [[ ! -d "$workdir" ]]; then
    workdir="/"
  fi

  if [[ -x "$noesis_cmd" ]]; then
    cmd_argv=("$noesis_cmd")
  else
    read -r -a cmd_argv <<< "$noesis_cmd"
  fi
  if (( ${#cmd_argv[@]} == 0 )); then
    return 127
  fi

  (cd "$workdir" 2>/dev/null || cd /; "${cmd_argv[@]}")
}

noesis_status="missing"
if [[ -d "$noesis_dir" ]]; then
  noesis_status="present"
fi
case "$start_wait" in
  ''|*[!0-9]*) start_wait=16 ;;
esac
start_wait="$((10#$start_wait))"
if (( start_wait < 0 )); then
  start_wait=16
fi
case "$max_wait" in
  ''|*[!0-9]*) max_wait=600 ;;
esac
max_wait="$((10#$max_wait))"
if (( max_wait < 1 )); then
  max_wait=600
fi

if [[ -n "$noesis_cmd" ]]; then
  emit_start "cmd" "provider=QGE_NOESIS_CMD"
  cmd_output="$(mktemp "${TMPDIR:-/tmp}/qge-noesis-actions.XXXXXX")"
  cmd_status=0
  set +e
  run_noesis_cmd > "$cmd_output"
  cmd_status=$?
  set -e
  if (( cmd_status != 0 )); then
    emit_command "echo QGE_NOESIS_PLAYER command_failed status=$cmd_status"
  fi
  if [[ -s "$cmd_output" ]]; then
    emit_actions_from_file "$cmd_output"
  else
    emit_command "echo QGE_NOESIS_PLAYER empty_command_output"
    emit_builtin_plan
  fi
  rm -f "$cmd_output"
elif [[ -n "$actions_file" ]]; then
  emit_start "file" "actions=$actions_file"
  if [[ -f "$actions_file" ]]; then
    emit_actions_from_file "$actions_file"
  else
    emit_command "echo QGE_NOESIS_PLAYER missing_actions_file=$actions_file"
    emit_builtin_plan
  fi
else
  emit_start "builtin"
  emit_builtin_plan
fi
emit_command "echo QGE_NOESIS_PLAYER done"
