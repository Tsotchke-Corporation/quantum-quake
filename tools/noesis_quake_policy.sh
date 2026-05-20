#!/usr/bin/env bash
set -euo pipefail

noesis_dir="${QGE_NOESIS_DIR:-$HOME/Desktop/noesis}"
plan="${QGE_NOESIS_PLAN:-adaptive}"
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

emit_phase() {
  emit "cmd echo QGE_NOESIS_PHASE $*"
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

emit_combat_explore() {
  emit "weapon 2"
  emit "center-view"
  emit_phase "phase=spawn_clear"
  emit "wait 6"
  emit "turn-left 5"
  emit "attack 1"
  emit "turn-right 10"
  emit "attack 1"
  emit "turn-left 5"
  emit "run-forward 10"
  emit "circle-left 8"
  emit "circle-right 8"
  emit "jump-forward 4"
  emit_phase "phase=route_probe"
  emit "turn-right 5"
  emit "attack 1"
  emit "run-forward 12"
  emit "strafe-left 6"
  emit "strafe-right 6"
  emit "attack 1"
  emit "run-forward 10"
  emit_phase "phase=stuck_recovery"
  emit "clear-input 2"
  emit "back 5"
  emit "wall-slide-left 6"
  emit "turn-right 8"
  emit "jump-forward 5"
  emit_phase "phase=second_push"
  emit "turn-left 6"
  emit "attack 1"
  emit "run-forward 12"
  emit "circle-left 6"
  emit "turn-left 6"
  emit "run-forward 10"
  emit "clear-input 2"
}

emit_e1m1_combat_explore() {
  emit "weapon 2"
  emit "center-view"
  emit_phase "phase=e1m1_entry_clear"
  emit "wait 6"
  emit "look-up 2"
  emit "turn-left 5"
  emit "attack 1"
  emit "turn-right 10"
  emit "attack 1"
  emit "turn-left 5"
  emit "center-view"
  emit "run-forward 12"
  emit "circle-left 8"
  emit "circle-right 8"
  emit "turn-right 4"
  emit_phase "phase=e1m1_bridge_push"
  emit "attack 1"
  emit "run-forward 16"
  emit "jump-forward 4"
  emit "strafe-left 6"
  emit "strafe-right 6"
  emit "attack 1"
  emit "run-forward 12"
  emit_phase "phase=e1m1_door_recovery"
  emit "clear-input 2"
  emit "back 5"
  emit "turn-left 5"
  emit "attack 1"
  emit "run-forward 14"
  emit "circle-right 8"
  emit_phase "phase=e1m1_exit_probe"
  emit "turn-right 6"
  emit "attack 1"
  emit "run-forward 14"
  emit "jump-forward 5"
  emit "clear-input 2"
}

emit_e1m1_route_push() {
  emit "weapon 2"
  emit "center-view"
  emit_phase "phase=e1m1_entry_clear"
  emit "wait 6"
  emit "look-up 2"
  emit "turn-left 5"
  emit "attack 1"
  emit "turn-right 10"
  emit "attack 1"
  emit "turn-left 5"
  emit "center-view"
  emit "run-forward 12"
  emit "wall-slide-right 12"
  emit "circle-left 6"
  emit "center-view"
  emit_phase "phase=e1m1_bridge_route"
  emit "turn-left 10"
  emit "run-forward 14"
  emit "wall-slide-left 10"
  emit "run-forward 10"
  emit "scan-fire-left 12"
  emit "attack 2"
  emit_phase "phase=e1m1_door_slide"
  emit "clear-input 2"
  emit "wall-slide-right 10"
  emit "door-open 8"
  emit "door-bump 6"
  emit "scan-fire-left 6"
  emit "scan-fire-right 6"
  emit "speed-jump-forward 4"
  emit "wall-slide-left 8"
  emit_phase "phase=e1m1_exit_route"
  emit "center-view"
  emit "look-up 2"
  emit "turn-left 6"
  emit "attack 1"
  emit "center-view"
  emit "run-forward 14"
  emit "wall-slide-right 12"
  emit "circle-right 8"
  emit "clear-input 2"
}

emit_weapon_cycle_smoke() {
  emit "weapon 2"
  emit "wait 4"
  emit "attack 4"
  emit "weapon-next"
  emit "wait 4"
  emit "attack 4"
  emit "weapon-prev"
  emit "center-view"
  emit "attack 4"
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

emit_adaptive() {
  case "$map_name" in
    e1m1)
      emit_e1m1_route_push
      ;;
    *)
      emit_combat_explore
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
  map-scout)
    emit_map_scout
    ;;
  combat|combat-scout|combat-explore)
    emit_combat_explore
    ;;
  e1m1-route-push|route-push)
    emit_e1m1_route_push
    ;;
  adaptive)
    emit_adaptive
    ;;
  weapon-cycle-smoke)
    emit_weapon_cycle_smoke
    ;;
  patrol|*)
    emit_patrol
    ;;
esac
emit_marker "done"
