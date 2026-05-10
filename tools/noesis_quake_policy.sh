#!/usr/bin/env bash
set -euo pipefail

noesis_dir="${QGE_NOESIS_DIR:-$HOME/Desktop/noesis}"
plan="${QGE_NOESIS_PLAN:-patrol}"
map_name="${QGE_STREAM_MAP:-start}"
fire_test="${QGE_STREAM_FIRE_TEST:-0}"

if [[ "$fire_test" == "1" && -z "${QGE_NOESIS_PLAN+x}" ]]; then
  plan="fire"
fi

emit() {
  printf '%s\n' "$*"
}

emit_marker() {
  emit "cmd echo QGE_NOESIS_POLICY $*"
}

emit_common_setup() {
  emit "give 7"
  emit "give r 100"
  emit "weapon 7"
}

emit_patrol() {
  emit "forward 12"
  emit "turn-right 6"
  emit "forward 12"
  emit "turn-left 6"
  emit_common_setup
  emit "wait 4"
  emit "attack 6"
}

emit_scout() {
  emit "forward 18"
  emit "turn-right 8"
  emit "forward 18"
}

emit_fire() {
  emit_common_setup
  emit "wait 8"
  emit "attack 8"
  emit "wait 8"
  emit "turn-right 6"
  emit "attack 8"
}

emit_map_scout() {
  case "$map_name" in
    e1m1)
      emit "forward 8"
      emit "turn-right 4"
      emit "forward 6"
      emit_fire
      ;;
    e1m6)
      emit "turn-right 4"
      emit "forward 10"
      emit "turn-left 4"
      emit "forward 6"
      emit_fire
      ;;
    start)
      emit "turn-right 6"
      emit "forward 12"
      emit "turn-left 6"
      emit "forward 10"
      ;;
    *)
      emit_patrol
      ;;
  esac
}

noesis_status="missing"
if [[ -d "$noesis_dir" ]]; then
  noesis_status="present"
fi

emit_marker "provider=tools/noesis_quake_policy.sh noesis_dir=$noesis_status map=$map_name plan=$plan"
case "$plan" in
  scout)
    emit_scout
    ;;
  fire)
    emit_fire
    ;;
  map-scout|adaptive)
    emit_map_scout
    ;;
  patrol|*)
    emit_patrol
    ;;
esac
emit_marker "done"
