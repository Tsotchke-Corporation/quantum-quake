#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/qge-noesis-contract.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

grep -q 'stream_mouse="${QGE_STREAM_MOUSE:-0}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'stream_display="${QGE_STREAM_DISPLAY:-}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'app_bin="${QGE_STREAM_APP_BIN:-$repo_root/QuantumQuake.app/Contents/MacOS/quantum_quake}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq '"app_bin": $(json_string "$app_bin")' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'run_args+=(-nomouse)' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'run_args=(-nolauncher -basedir "$basedir" "${video_args[@]}")' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'arguments = [[QuakeArguments alloc] initWithArguments:gArgv + 1 count:gArgc - 1];' "$repo_root/quake/MacOSX/AppController.m"
grep -Fq 'if ([arguments argument:@"-nolauncher"] != nil)' "$repo_root/quake/MacOSX/AppController.m"
grep -Fq '[self launchQuakeUsingLauncherControls:NO];' "$repo_root/quake/MacOSX/AppController.m"
grep -Fq '[self launchQuakeUsingLauncherControls:YES];' "$repo_root/quake/MacOSX/AppController.m"
grep -Fq '[quakeArgs removeObjectAtIndex:i];' "$repo_root/quake/MacOSX/QuakeArguments.m"
grep -Fq 'video_args+=(-display "$stream_display")' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'open "${open_args[@]}" --args -ApplePersistenceIgnoreState YES "${run_args[@]}" -condebug >>"$open_log_file" 2>&1' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'startup_issue="gl_context_failed"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'startup_issue="open_failed_\$open_status"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'latest_icc_evidence.txt' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'write_latest_stream_pointers' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'recover_latest_trace_pointer' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'if [[ "$trace" == "1" && -s "$trace_file" ]]; then' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'replay_trace="${QGE_STREAM_REPLAY_TRACE:-${QGE_REPLAY_TRACE_PATH:-}}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'run_args+=(-qgereplay "$replay_trace" -qgereplaystrict "$replay_strict")' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq '"trace_file": $(json_string "$replay_trace")' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'QGE_CommandLineReplayPath' "$repo_root/quake/Quake/qge_hooks.c"
grep -Fq 'QGE_REPLAY_TRACE_PATH' "$repo_root/quake/Quake/qge_hooks.c"
grep -Fq 'QGE_REPLAY_STRICT' "$repo_root/quake/Quake/qge_hooks.c"
grep -Fq 'qge_quantum_runtime_load_replay_trace(rt, replay_path)' "$repo_root/quake/Quake/qge_hooks.c"
grep -Fq 'QGE_ENTROPY_SOURCE_REPLAY' "$repo_root/qge/qge_rng.c"
grep -Fq 'QGE_STREAM_REPLAY_TRACE' "$repo_root/docs/qge_agent_stream.md"
grep -q 'find "$quake_stream_root" -mindepth 2 -maxdepth 2' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'latest non-empty trace file' "$repo_root/docs/qge_agent_stream.md"
grep -q 'repairs it from the newest existing non-empty' "$repo_root/docs/qge_agent_stream.md"
grep -q 'timeout_seconds="${QGE_STREAM_TIMEOUT_SECONDS:-}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'normalize_positive_int' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'width="$(normalize_positive_int "$width" 800)"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'render_res="$(normalize_positive_int "$render_res" 1024)"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'sound="$(normalize_bool "$sound")"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'trace="$(normalize_bool "$trace")"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'trace_status="not_requested"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q '"trace_status":' "$repo_root/tools/quake_graphics_stream.sh"
grep -q '"trace_bytes": \$trace_bytes' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'trace_status.*not_requested' "$repo_root/docs/qge_agent_stream.md"
grep -q '"frames_captured": \$manifest_frame_count' "$repo_root/tools/quake_graphics_stream.sh"
grep -q '"run": {' "$repo_root/tools/quake_graphics_stream.sh"
grep -q '"startup_issue":' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'run.status.*run.success.*run.startup_issue' "$repo_root/docs/qge_agent_stream.md"
grep -q 'agent_stream_run_status' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'agent_stream_run_success' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'agent_stream_startup_issue' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'agent_stream_trace_status' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'agent_trace_file' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'run outcome, trace status' "$repo_root/docs/qge_agent_stream.md"
grep -q 'perf_max_average_ms="${QGE_PERF_MAX_AVERAGE_MS:-}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'qge_perf_summary.py' "$repo_root/tools/quake_graphics_stream.sh"
grep -q '"performance": {' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'agent_stream_perf_status' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'agent_perf_summary_file' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'QGE_PERF_MAX_AVERAGE_MS' "$repo_root/docs/qge_agent_stream.md"
grep -q 'agent_manifest_summary' "$repo_root/tools/qge_vanilla_capture_matrix.py"
grep -q 'explicit_agent_run_failure' "$repo_root/tools/qge_vanilla_capture_matrix.py"
grep -q 'agent_stream_runs_success' "$repo_root/tools/qge_vanilla_capture_matrix.py"
grep -q 'performance_sidecars_success' "$repo_root/tools/qge_vanilla_capture_matrix.py"
grep -q 'qge_perf_summary.json' "$repo_root/tools/quake_graphics_harness.sh"
grep -q 'agent-stream run failure blocks' "$repo_root/docs/qge_agent_stream.md"
grep -q 'agent_stream_runs_success' "$repo_root/tools/qge_publication_pack.py"
grep -q 'agent_stream_manifest_run' "$repo_root/tools/qge_publication_pack.py"
grep -q 'publication_ready_for_complete_claim' "$repo_root/tools/qge_publication_pack.py"
grep -q 'performance_summary' "$repo_root/tools/qge_publication_pack.py"
grep -q 'performance_ok' "$repo_root/tools/qge_publication_pack.py"
grep -q 'vanilla_performance_sidecars_success' "$repo_root/tools/qge_publication_pack.py"
grep -q 'qge_performance_status' "$repo_root/tools/qge_publication_pack.py"
grep -q 'vanilla_performance_ok' "$repo_root/tools/qge_publication_pack.py"
grep -q 'pack copies these run-status fields' "$repo_root/docs/qge_agent_stream.md"
grep -q 'Publication packs copy capture and vanilla-matrix performance sidecars' "$repo_root/docs/qge_agent_stream.md"
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
grep -q 'stream_display="${QGE_STREAM_DISPLAY:-}"' "$repo_root/tools/quake_crash_watch.sh"
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
grep -Fq 'qconsole_file="$basedir/qconsole.log"' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'qconsole_root_file="$repo_root/qconsole.log"' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'cp "$qconsole_file" "$outdir/qconsole.log"' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'cp "$qconsole_root_file" "$outdir/qconsole.root.log"' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'rm -f "$qconsole_file"' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'rm -f "$qconsole_root_file"' "$repo_root/tools/quake_crash_watch.sh"
grep -q 'input/noesis_actions.txt' "$repo_root/docs/qge_agent_stream.md"
grep -q 'diagnostics/agent_stream/latest_stream.txt' "$repo_root/docs/qge_agent_stream.md"
grep -q 'QGE_STREAM_TIMEOUT_SECONDS' "$repo_root/docs/qge_agent_stream.md"
grep -q 'child process exit status' "$repo_root/docs/qge_agent_stream.md"
grep -q 'process exit status in its final' "$repo_root/docs/qge_agent_stream.md"
grep -q 'QGE_NOESIS_MAX_WAIT' "$repo_root/tools/noesis_quake_player.sh"
grep -q 'wait_clamped requested=' "$repo_root/tools/noesis_quake_player.sh"
grep -q 'qge_noesis_summary.py' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'qge_noesis_summary.json' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'qge_noesis_icc_evidence.json' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'agent_stream_noesis_status' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'agent_noesis_summary_file' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'agent_noesis_icc_evidence_file' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'agent_noesis_gameplay_file' "$repo_root/tools/quake_graphics_stream.sh"
grep -q '"noesis": {' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'gameplay_outcomes_file' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'qge_noesis_summary.py' "$repo_root/docs/qge_agent_stream.md"
grep -q 'qge_noesis_summary.json' "$repo_root/docs/qge_agent_stream.md"
grep -q 'agent_stream_noesis_status' "$repo_root/docs/qge_agent_stream.md"
grep -Fq 'plan="${QGE_NOESIS_PLAN:-adaptive}"' "$repo_root/tools/noesis_quake_player.sh"
grep -Fq 'plan="${QGE_NOESIS_PLAN:-adaptive}"' "$repo_root/tools/noesis_quake_policy.sh"
grep -Fq 'noesis_plan="${QGE_NOESIS_PLAN:-adaptive}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'noesis_plan="${QGE_NOESIS_PLAN:-adaptive}"' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'stream_activate="${QGE_STREAM_ACTIVATE:-0}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'advance-fire' "$repo_root/tools/noesis_quake_player.sh"
grep -q 'wall-slide-right' "$repo_root/tools/noesis_quake_player.sh"
grep -q 'door-bump' "$repo_root/tools/noesis_quake_player.sh"
grep -q 'door-open' "$repo_root/tools/noesis_quake_player.sh"
grep -q 'speed-jump-forward' "$repo_root/tools/noesis_quake_player.sh"
grep -q 'scan-fire-left' "$repo_root/tools/noesis_quake_player.sh"
grep -q 'scan-fire-right' "$repo_root/tools/noesis_quake_player.sh"
grep -q 'attack 1' "$repo_root/tools/noesis_quake_policy.sh"
grep -q 'circle-left' "$repo_root/tools/noesis_quake_policy.sh"
grep -q 'door-open' "$repo_root/tools/noesis_quake_policy.sh"
grep -q 'e1m1-route-push' "$repo_root/tools/noesis_quake_policy.sh"
grep -q 'QGE_NOESIS_PHASE' "$repo_root/tools/noesis_quake_policy.sh"
grep -q 'phase=e1m1_hunt_loop' "$repo_root/tools/noesis_quake_policy.sh"
grep -q 'back 8' "$repo_root/tools/noesis_quake_policy.sh"
grep -q 'speed-jump-forward 6' "$repo_root/tools/noesis_quake_policy.sh"
grep -q 'bounded hunt loop with a keyboard-only' "$repo_root/docs/qge_agent_stream.md"
grep -q 'QGE_NOESIS_MAX_WAIT' "$repo_root/docs/qge_agent_stream.md"
grep -q 'combat-explore' "$repo_root/docs/qge_agent_stream.md"
grep -q 'advance-fire' "$repo_root/docs/qge_agent_stream.md"
grep -q 'wall-slide-right' "$repo_root/docs/qge_agent_stream.md"
grep -q 'door-bump' "$repo_root/docs/qge_agent_stream.md"
grep -q 'door-open' "$repo_root/docs/qge_agent_stream.md"
grep -q 'speed-jump-forward' "$repo_root/docs/qge_agent_stream.md"
grep -q 'scan-fire-left' "$repo_root/docs/qge_agent_stream.md"
grep -q 'noesis_gameplay_quality_score' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_claim_scope' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_unassisted_claim_supported' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_outcome_sample_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_total_distance' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_terminal_stall' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_max_stationary_run' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_stationary_fraction' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_movement_efficiency' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_phase_event_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_phase_stuck_window_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_projectile_save_demo_boundary_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_projectile_save_demo_trace_id_xor' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_replay_metadata_mismatches' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_trace_qge_build_hash' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_attack_visible_frames' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_attack_aligned_frames' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_blind_attack_frames' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_visible_unaligned_attack_frames' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_unproductive_attack_frames' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_nearest_enemy_angle_error_min' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_net_damage_per_attack_press' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_ammo_spent' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_unproductive_ammo_spent' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_ammo_waste_fraction' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_gameplay_damage_per_ammo_spent' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'combat_opportunity' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'close_enemy_contact_sample_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'close enemy-contact samples' "$repo_root/docs/qge_agent_stream.md"
grep -q 'Blind fire by itself does not turn a route-only interval into a' "$repo_root/docs/qge_agent_stream.md"
grep -q 'combat_effectiveness_required' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'terminal_stall_threshold' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_requested_mode' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_active_fraction' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_active_sample_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_target_visible_sample_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_steering_sample_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_view_injected_sample_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_movement_injected_sample_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_attack_injected_sample_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_attack_suppressed_sample_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_pre_assist_aim_error_min' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_target_locked_sample_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_target_switch_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_assist_switch_fire_suppressed_sample_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_route_action_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'noesis_log_phase_count' "$repo_root/tools/qge_noesis_summary.py"
grep -q 'door-open' "$repo_root/tools/qge_noesis_summary.py"
grep -Fq 'noesis_min_log_phases="${QGE_NOESIS_MIN_LOG_PHASES:-0}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'noesis_min_gameplay_samples="${QGE_NOESIS_MIN_GAMEPLAY_SAMPLES:-2}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'noesis_min_route_distance="${QGE_NOESIS_MIN_ROUTE_DISTANCE:-64}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'noesis_min_capture_wait="${QGE_NOESIS_MIN_CAPTURE_WAIT:-280}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq '"noesis_min_capture_wait": $noesis_min_capture_wait' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'if (( noesis_min_capture_wait > noesis_capture_min )); then' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'noesis_assist="${QGE_NOESIS_ASSIST:-2}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'noesis_assist="$(normalize_nonnegative_int "$noesis_assist" 2)"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq '"noesis_min_log_phases": $noesis_min_log_phases' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq '"noesis_min_gameplay_samples": $noesis_min_gameplay_samples' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq '"noesis_assist": $noesis_assist' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'qge_noesis_assist $noesis_assist' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq -- '--min-log-phases "$noesis_min_log_phases"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq -- '--min-phase-outcomes "$noesis_min_log_phases"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq -- '--min-gameplay-samples "$noesis_min_gameplay_samples"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'if (( frames >= 2 )); then' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'noesis_args+=(--min-frame-mae 2.0)' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'QGE_NOESIS_MIN_LOG_PHASES' "$repo_root/docs/qge_agent_stream.md"
grep -q 'QGE_NOESIS_MIN_GAMEPLAY_SAMPLES' "$repo_root/docs/qge_agent_stream.md"
grep -q 'QGE_NOESIS_MIN_CAPTURE_WAIT' "$repo_root/docs/qge_agent_stream.md"
grep -q 'QGE_NOESIS_ASSIST' "$repo_root/docs/qge_agent_stream.md"
grep -q 'claim scope' "$repo_root/docs/qge_agent_stream.md"
grep -q 'attack-aligned frame counts' "$repo_root/docs/qge_agent_stream.md"
grep -q 'left bridge side before a bounded `scan-fire-left` sweep' "$repo_root/docs/qge_agent_stream.md"
grep -q 'remaining marked `server_assisted`' "$repo_root/docs/qge_agent_stream.md"
grep -q 'kites visible close' "$repo_root/docs/qge_agent_stream.md"
grep -q 'Hidden distant targets do not override' "$repo_root/docs/qge_agent_stream.md"
grep -q 'QGE_NoesisAssistClientThink' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'QGE_GameplayEnemyAimPoint' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'QGE_GameplayAimErrorDegrees(player, candidate_aim)' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'pre_assist_aim_error_deg' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'view_injected' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'movement_injected' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'attack_injected' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'target_locked' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'switch_fire_suppressed' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'QGE_NOESIS_TARGET_LOCK_FRAMES' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'QGE_NOESIS_VIEW_HOLD_DEG' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'pre_aim_error > QGE_NOESIS_VIEW_HOLD_DEG' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'QGE_NoesisAssistSetRelativeMove(move, movement_yaw, aim\[YAW\]' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'move->forwardmove = DotProduct(wish, basis_forward)' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'enemy = QGE_NoesisAssistFindEnemy(player, chase_mode ? false : true' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'QGE_NOESIS_AIM_ALIGNED_DEG' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'qge_gameplay_attack_aligned_total' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'distance < 192.0f' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'engage_target = visible' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'QGE_NOESIS_HIDDEN_CHASE_DISTANCE 768.0f' "$repo_root/quake/Quake/qge_hooks.c"
grep -Fq 'relative_side = left_clear >= right_clear ? -320.0f : 320.0f;' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'player->v.button0 = 0.0f' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'Cmd_AddCommand("qge_noesis_phase", QGE_NoesisPhase_f)' "$repo_root/quake/Quake/qge_hooks.c"
grep -q '\\"kind\\":\\"noesis_phase\\"' "$repo_root/quake/Quake/qge_hooks.c"
grep -q '\\"assist\\"' "$repo_root/quake/Quake/qge_hooks.c"
grep -q 'gameplay_outcomes.ndjson' "$repo_root/docs/qge_agent_stream.md"
grep -q 'weapon-cycle-smoke' "$repo_root/docs/qge_agent_stream.md"
grep -Fq 'noesis_max_wait="${QGE_NOESIS_MAX_WAIT:-600}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq '"noesis_max_wait": $noesis_max_wait' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'fire_min_start_wait="${QGE_STREAM_FIRE_MIN_START_WAIT:-48}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'fire_min_frames="${QGE_STREAM_FIRE_MIN_FRAMES:-8}"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq '"fire_min_start_wait": $fire_min_start_wait' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq '"fire_min_frames": $fire_min_frames' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'QGE_STREAM_FIRE_MIN_START_WAIT' "$repo_root/docs/qge_agent_stream.md"
grep -q 'projectile authority warmup' "$repo_root/docs/qge_agent_stream.md"
grep -Fq 'QGE_NOESIS_MAX_WAIT="$noesis_max_wait"' "$repo_root/tools/quake_graphics_stream.sh"
grep -Fq 'QGE_NOESIS_MAX_WAIT="$noesis_max_wait"' "$repo_root/tools/quake_crash_watch.sh"
grep -Fq 'rm -f "$runtime_log_file"' "$repo_root/tools/quake_graphics_stream.sh"
grep -q 'removes the root `qconsole.log` copy' "$repo_root/docs/qge_agent_stream.md"
grep -q 'archives it and then removes' "$repo_root/docs/qge_agent_stream.md"

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

recovery_actions="$tmpdir/recovery-actions.txt"
recovery_commands="$tmpdir/recovery-commands.cfg"
recovery_stdout="$tmpdir/recovery-stdout.cfg"

QGE_NOESIS_DIR="$repo_root" \
QGE_NOESIS_PLAN=combat-explore \
QGE_STREAM_MAP=start \
QGE_NOESIS_CMD="$repo_root/tools/noesis_quake_policy.sh" \
QGE_NOESIS_START_WAIT=0 \
QGE_NOESIS_ACTION_TRACE_FILE="$recovery_actions" \
QGE_NOESIS_COMMAND_TRACE_FILE="$recovery_commands" \
  "$repo_root/tools/noesis_quake_player.sh" > "$recovery_stdout"

cmp -s "$recovery_stdout" "$recovery_commands"
grep -q '^cmd echo QGE_NOESIS_PHASE phase=stuck_recovery$' "$recovery_actions"
grep -q '^back 5$' "$recovery_actions"
grep -q '^wall-slide-left 6$' "$recovery_actions"
grep -q '^turn-right 8$' "$recovery_actions"
grep -q '^jump-forward 5$' "$recovery_actions"
grep -q '^cmd echo QGE_NOESIS_PHASE phase=second_push$' "$recovery_actions"
grep -q '^+back$' "$recovery_commands"
grep -q '^-back$' "$recovery_commands"
grep -q '^+moveleft$' "$recovery_commands"
grep -q '^-moveleft$' "$recovery_commands"
grep -q '^+jump$' "$recovery_commands"

builtin_recovery_actions="$tmpdir/builtin-recovery-actions.txt"
builtin_recovery_commands="$tmpdir/builtin-recovery-commands.cfg"
builtin_recovery_stdout="$tmpdir/builtin-recovery-stdout.cfg"

QGE_NOESIS_DIR="$repo_root" \
QGE_NOESIS_PLAN=combat-explore \
QGE_STREAM_MAP=start \
QGE_NOESIS_START_WAIT=0 \
QGE_NOESIS_ACTION_TRACE_FILE="$builtin_recovery_actions" \
QGE_NOESIS_COMMAND_TRACE_FILE="$builtin_recovery_commands" \
  "$repo_root/tools/noesis_quake_player.sh" > "$builtin_recovery_stdout"

cmp -s "$builtin_recovery_stdout" "$builtin_recovery_commands"
grep -q '^back 5$' "$builtin_recovery_actions"
grep -q '^wall-slide-left 6$' "$builtin_recovery_actions"
grep -q '^turn-right 8$' "$builtin_recovery_actions"
grep -q '^jump-forward 5$' "$builtin_recovery_actions"
grep -q '^run-forward 10$' "$builtin_recovery_actions"
grep -q '^+back$' "$builtin_recovery_commands"
grep -q '^+moveleft$' "$builtin_recovery_commands"
grep -q '^+jump$' "$builtin_recovery_commands"

adaptive_actions="$tmpdir/adaptive-actions.txt"
adaptive_commands="$tmpdir/adaptive-commands.cfg"
adaptive_stdout="$tmpdir/adaptive-stdout.cfg"

QGE_NOESIS_DIR="$repo_root" \
QGE_NOESIS_PLAN=adaptive \
QGE_STREAM_MAP=e1m1 \
QGE_NOESIS_CMD="$repo_root/tools/noesis_quake_policy.sh" \
QGE_NOESIS_START_WAIT=0 \
QGE_NOESIS_ACTION_TRACE_FILE="$adaptive_actions" \
QGE_NOESIS_COMMAND_TRACE_FILE="$adaptive_commands" \
  "$repo_root/tools/noesis_quake_player.sh" > "$adaptive_stdout"

cmp -s "$adaptive_stdout" "$adaptive_commands"

grep -q '^cmd echo QGE_NOESIS_POLICY .*map=e1m1 plan=adaptive' "$adaptive_actions"
grep -q '^center-view$' "$adaptive_actions"
grep -q '^cmd echo QGE_NOESIS_PHASE phase=e1m1_entry_clear$' "$adaptive_actions"
grep -q '^cmd echo QGE_NOESIS_PHASE phase=e1m1_bridge_route$' "$adaptive_actions"
grep -q '^cmd echo QGE_NOESIS_PHASE phase=e1m1_door_slide$' "$adaptive_actions"
grep -q '^cmd echo QGE_NOESIS_PHASE phase=e1m1_exit_route$' "$adaptive_actions"
grep -q '^look-up 2$' "$adaptive_actions"
grep -q '^turn-left 5$' "$adaptive_actions"
grep -q '^turn-right 10$' "$adaptive_actions"
grep -q '^attack 1$' "$adaptive_actions"
grep -q '^run-forward 12$' "$adaptive_actions"
grep -q '^wall-slide-right 12$' "$adaptive_actions"
grep -q '^circle-left 6$' "$adaptive_actions"
grep -q '^turn-left 10$' "$adaptive_actions"
grep -q '^run-forward 14$' "$adaptive_actions"
grep -q '^wall-slide-left 10$' "$adaptive_actions"
grep -q '^scan-fire-left 12$' "$adaptive_actions"
grep -q '^attack 2$' "$adaptive_actions"
grep -q '^door-open 8$' "$adaptive_actions"
grep -q '^door-bump 6$' "$adaptive_actions"
grep -q '^scan-fire-left 6$' "$adaptive_actions"
grep -q '^scan-fire-right 6$' "$adaptive_actions"
grep -q '^speed-jump-forward 4$' "$adaptive_actions"
grep -q '^clear-input 2$' "$adaptive_actions"
grep -q '^cmd echo QGE_NOESIS_POLICY done$' "$adaptive_actions"
adaptive_speed_jump_count="$(grep -c '^speed-jump-forward 4$' "$adaptive_actions" | tr -d ' ')"
if (( adaptive_speed_jump_count < 1 )); then
  echo "expected E1M1 adaptive route to include post-door speed jump recovery" >&2
  exit 1
fi
adaptive_attack_tap_count="$(grep -c '^attack 1$' "$adaptive_actions" | tr -d ' ')"
if (( adaptive_attack_tap_count < 3 )); then
  echo "expected E1M1 adaptive route to keep disciplined attack taps" >&2
  exit 1
fi
if grep -Eq '^(advance-fire|circle-fire|strafe-fire)' "$adaptive_actions"; then
  echo "E1M1 adaptive route kept long default fire holds" >&2
  exit 1
fi

grep -q '^echo QGE_NOESIS_PHASE phase=e1m1_entry_clear$' "$adaptive_commands"
grep -q '^qge_noesis_phase phase=e1m1_entry_clear$' "$adaptive_commands"
grep -q '^qge_noesis_phase phase=e1m1_bridge_route$' "$adaptive_commands"
grep -q '^qge_noesis_phase phase=e1m1_door_slide$' "$adaptive_commands"
grep -q '^qge_noesis_phase phase=e1m1_exit_route$' "$adaptive_commands"
grep -q '^centerview$' "$adaptive_commands"
grep -q '^+forward$' "$adaptive_commands"
grep -q '^+attack$' "$adaptive_commands"
grep -q '^+lookup$' "$adaptive_commands"
grep -q '^+left$' "$adaptive_commands"
grep -q '^+right$' "$adaptive_commands"
grep -q '^+speed$' "$adaptive_commands"
grep -q '^+moveleft$' "$adaptive_commands"
grep -q '^+moveright$' "$adaptive_commands"
grep -q '^+jump$' "$adaptive_commands"
grep -q '^+use$' "$adaptive_commands"
grep -q '^-speed$' "$adaptive_commands"
grep -q '^-use$' "$adaptive_commands"
grep -q '^-lookup$' "$adaptive_commands"
grep -q '^-attack$' "$adaptive_commands"
grep -q '^-forward$' "$adaptive_commands"
grep -q '^echo QGE_NOESIS_PLAYER done$' "$adaptive_commands"

adaptive_command_count="$(wc -l < "$adaptive_commands" | tr -d ' ')"
if (( adaptive_command_count < 150 )); then
  echo "expected rich adaptive Quake command trace, got only $adaptive_command_count lines" >&2
  exit 1
fi

builtin_route_actions="$tmpdir/builtin-route-actions.txt"
builtin_route_commands="$tmpdir/builtin-route-commands.cfg"
builtin_route_stdout="$tmpdir/builtin-route-stdout.cfg"

QGE_NOESIS_DIR="$repo_root" \
QGE_NOESIS_PLAN=e1m1-route-push \
QGE_STREAM_MAP=e1m1 \
QGE_NOESIS_START_WAIT=0 \
QGE_NOESIS_ACTION_TRACE_FILE="$builtin_route_actions" \
QGE_NOESIS_COMMAND_TRACE_FILE="$builtin_route_commands" \
  "$repo_root/tools/noesis_quake_player.sh" > "$builtin_route_stdout"

cmp -s "$builtin_route_stdout" "$builtin_route_commands"
grep -q '^door-open 8$' "$builtin_route_actions"
grep -q '^door-bump 6$' "$builtin_route_actions"
grep -q '^turn-left 10$' "$builtin_route_actions"
grep -q '^run-forward 14$' "$builtin_route_actions"
grep -q '^wall-slide-left 10$' "$builtin_route_actions"
grep -q '^scan-fire-left 12$' "$builtin_route_actions"
grep -q '^attack 2$' "$builtin_route_actions"
grep -q '^scan-fire-left 6$' "$builtin_route_actions"
grep -q '^scan-fire-right 6$' "$builtin_route_actions"
grep -q '^speed-jump-forward 4$' "$builtin_route_actions"
grep -q '^attack 1$' "$builtin_route_actions"
if grep -q '^jump-forward 3$' "$builtin_route_actions"; then
  echo "built-in E1M1 route kept weak post-door jump-forward recovery" >&2
  exit 1
fi
if grep -Eq '^(advance-fire|circle-fire|strafe-fire)' "$builtin_route_actions"; then
  echo "built-in E1M1 route kept long default fire holds" >&2
  exit 1
fi
grep -q '^+use$' "$builtin_route_commands"
grep -q '^-use$' "$builtin_route_commands"
grep -q '^+forward$' "$builtin_route_commands"
grep -q '^echo QGE_NOESIS_PLAYER done$' "$builtin_route_commands"

combo_actions="$tmpdir/combo-actions.txt"
combo_trace="$tmpdir/combo-trace.txt"
combo_commands="$tmpdir/combo-commands.cfg"
combo_stdout="$tmpdir/combo-stdout.cfg"
cat > "$combo_actions" <<'EOF'
advance-fire 2
wall-slide-left 3
wall-slide-right 2
speed-jump-forward 2
door-open 2
door-bump 3
circle-fire-right 3
scan-fire-left 2
scan-fire-right 2
jump-forward 2
use 1
look-up 1
swim-up 1
center-view
weapon-next
weapon-prev
reload 1
clear-input 1
EOF

QGE_NOESIS_DIR="$repo_root" \
QGE_NOESIS_ACTIONS_FILE="$combo_actions" \
QGE_NOESIS_START_WAIT=0 \
QGE_NOESIS_MAX_WAIT=4 \
QGE_NOESIS_ACTION_TRACE_FILE="$combo_trace" \
QGE_NOESIS_COMMAND_TRACE_FILE="$combo_commands" \
  "$repo_root/tools/noesis_quake_player.sh" > "$combo_stdout"

cmp -s "$combo_stdout" "$combo_commands"
grep -q '^advance-fire 2$' "$combo_trace"
grep -q '^wall-slide-left 3$' "$combo_trace"
grep -q '^wall-slide-right 2$' "$combo_trace"
grep -q '^speed-jump-forward 2$' "$combo_trace"
grep -q '^door-open 2$' "$combo_trace"
grep -q '^door-bump 3$' "$combo_trace"
grep -q '^circle-fire-right 3$' "$combo_trace"
grep -q '^scan-fire-left 2$' "$combo_trace"
grep -q '^scan-fire-right 2$' "$combo_trace"
grep -q '^+forward$' "$combo_commands"
grep -q '^+attack$' "$combo_commands"
grep -q '^+speed$' "$combo_commands"
grep -q '^+moveleft$' "$combo_commands"
grep -q '^+moveright$' "$combo_commands"
grep -q '^+left$' "$combo_commands"
grep -q '^+right$' "$combo_commands"
grep -q '^+jump$' "$combo_commands"
grep -q '^+use$' "$combo_commands"
grep -q '^+lookup$' "$combo_commands"
grep -q '^+moveup$' "$combo_commands"
grep -q '^centerview$' "$combo_commands"
grep -q '^impulse 10$' "$combo_commands"
grep -q '^impulse 12$' "$combo_commands"
grep -q '^echo QGE_NOESIS_PLAYER skipped_unknown_action=reload$' "$combo_commands"
grep -q '^-moveup$' "$combo_commands"
grep -q '^-lookup$' "$combo_commands"
grep -q '^-use$' "$combo_commands"
grep -q '^-right$' "$combo_commands"
grep -q '^-left$' "$combo_commands"
grep -q '^-jump$' "$combo_commands"
grep -q '^-speed$' "$combo_commands"
grep -q '^-attack$' "$combo_commands"

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

grep -Fq 'void QGE_2DBeginFrame(void);' "$repo_root/quake/Quake/qge_hooks.h"
grep -Fq 'void QGE_2DSubmitPic(const qpic_t *pic);' "$repo_root/quake/Quake/qge_hooks.h"
grep -Fq 'QGE_2DBeginFrame ();' "$repo_root/quake/Quake/gl_screen.c"
grep -Fq 'QGE_2DSetLayer (QGE_2D_LAYER_CONSOLE);' "$repo_root/quake/Quake/gl_screen.c"
grep -Fq 'QGE_2DEndFrame ();' "$repo_root/quake/Quake/gl_screen.c"
grep -Fq 'QGE_2DSubmitCharacter(*str);' "$repo_root/quake/Quake/gl_draw.c"
grep -Fq 'QGE_2DSubmitPic(pic);' "$repo_root/quake/Quake/gl_draw.c"
grep -Fq 'QGE_2DSubmitFill();' "$repo_root/quake/Quake/gl_draw.c"
grep -Fq 'strlcpy(probe.label, "render_2d_overlay", sizeof(probe.label));' "$repo_root/quake/Quake/qge_hooks.c"
grep -Fq 'own_hud=%d own_console=%d' "$repo_root/quake/Quake/qge_hooks.c"
grep -Fq 'QGE_MEASURE_PROJECTILE_WRITEBACK' "$repo_root/qge/qge_quantum_runtime.h"
grep -Fq 'QGE_MEASURE_PROJECTILE_BRANCH' "$repo_root/qge/qge_quantum_runtime.h"
grep -Fq 'QGE_MEASURE_PROJECTILE_COLLISION_ORACLE' "$repo_root/qge/qge_quantum_runtime.h"
grep -Fq 'QGE_OBSERVE_SAVE_OR_DEMO' "$repo_root/quake/Quake/qge_hooks.c"
grep -Fq 'save_demo_boundary_count' "$repo_root/tools/qge_trace_summary.py"
grep -Fq 'Projectile branch, writeback, and collision-oracle selections also emit' "$repo_root/docs/qge_agent_stream.md"

echo "Noesis input contract: PASSED"
