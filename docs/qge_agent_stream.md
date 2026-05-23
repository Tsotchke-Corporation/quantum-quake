# QGE Agent Media Stream

`tools/quake_graphics_stream.sh` runs Quantum Quake and mirrors the useful
runtime artifacts into a project-local directory that other agents can inspect
while the game is still running.

The default stream directory is:

```text
diagnostics/agent_stream/<timestamp>/
```

Set `QGE_AGENT_STREAM_DIR=/path/to/dir` to choose a stable location.

## Quick Start

Capture one traced frame on the default `start` map:

```sh
QGE_STREAM_FRAMES=1 QGE_STREAM_TRACE=1 bash tools/quake_graphics_stream.sh
```

Capture a specific map with sound enabled:

```sh
QGE_STREAM_MAP=e1m1 QGE_STREAM_SOUND=1 QGE_STREAM_TRACE=1 \
  bash tools/quake_graphics_stream.sh
```

Capture a compact runtime-ownership evidence run:

```sh
QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=16 QGE_STREAM_WAIT_FRAMES=12 \
  QGE_STREAM_TRACE=1 QGE_STREAM_SOUND=1 QGE_STREAM_SND_QUANTUM=2 \
  QGE_STREAM_SND_QUANTUM_SOURCE_AUTHORITY=1 QGE_STREAM_FIRE_TEST=1 \
  QGE_STREAM_AI=1 QGE_STREAM_VIS=2 QGE_RENDER=2 QGE_PHYSICS=1 \
  QGE_PROJECTILES=1 bash tools/quake_graphics_stream.sh
```

Use `QGE_STREAM_VIS=2` for the raw Grover/PVS authority path. Raw mode feeds
the audited classic PVS/cull accepted set into the Grover oracle, applies a
conservative probability floor to suppress diffuse over-inclusion, and only
hands the QGE mask to the renderer after the shadow parity/warmup gate is clean.
It still records `false_negative_repaired` and falls back if a raw run ever
needs repair or has another mismatch. Use `QGE_STREAM_VIS=3` only for the
controlled authority smoke that proves the renderer can consume an audited QGE
visibility mask independently of raw oracle quality.

Run the scripted weapon smoke and capture before the script exits:

```sh
QGE_STREAM_MAP=e1m1 QGE_STREAM_FIRE_TEST=1 QGE_STREAM_TRACE=1 \
  bash tools/quake_graphics_stream.sh
```

For `QGE_STREAM_FIRE_TEST=1`, the stream harness promotes the Noesis start
wait to at least `QGE_STREAM_FIRE_MIN_START_WAIT` (default `48`) and engine
captures to at least `QGE_STREAM_FIRE_MIN_FRAMES` (default `8`). These defaults
let the scripted rocket spawn after full signon and keep the run alive long
enough for projectile authority warmup, writeback, and pre-impact oracle trace
records. The fire-test Noesis path defaults `QGE_NOESIS_ASSIST` to `0` so the
assist layer cannot suppress the scripted attack; set it explicitly when
intentionally testing assisted fire control. Set either minimum to `0` only when
intentionally testing a shorter input or capture path.

Projectile branch, writeback, and collision-oracle selections also emit
`save_or_demo` measurement records. These records carry the selected branch or
oracle source, probability, and stable trace hash so a captured `qge_trace.bin`
has explicit persistence-boundary evidence for replay/demo verification, not
only frame-boundary probes.

To load an earlier trace while recording a fresh replay-consumption trace:

```sh
QGE_STREAM_TRACE=1 QGE_STREAM_REPLAY_TRACE=diagnostics/quake_stream/<run>/qge_trace.bin \
  QGE_STREAM_REPLAY_STRICT=0 bash tools/quake_graphics_stream.sh
```

The harness passes the replay path as `-qgereplay` and mirrors strictness as
`-qgereplaystrict`. Strict replay defaults to `1`, which requires frame/time,
domain, subject, request, and entropy-offset metadata to match exactly.
`QGE_STREAM_REPLAY_STRICT=0` is useful for smoke tests that prove the engine can
load and consume a prior trace while allowing a fresh live run to differ in
timing. The output trace summary should show
`replay_health.entropy_replay_events > 0` and zero replay mismatch/exhaustion
counters.

To exercise the sprite billboard encoder without relying on a hand-played scene:

```sh
QGE_STREAM_SPRITE_TEST=1 QGE_STREAM_FRAMES=1 QGE_STREAM_TRACE=1 \
  bash tools/quake_graphics_stream.sh
```

## Stream Contract

The stream directory is intentionally simple and tail-friendly:

- `manifest.json`: rewritten whenever stream state changes. It records the
  capture path, map, render settings, trace status, and current audio/video/log
  locations. The input block also records `noesis_max_wait`, the per-action
  wait cap used by the Noesis command translator for that run, plus fire-test
  minimums when the scripted projectile smoke is enabled. When
  `QGE_STREAM_TRACE=0`, `trace_status` is `not_requested`, `trace_bytes` is
  `0`, and `trace` is an empty string rather than a nonexistent planned path.
  Top-level `status` reports stream artifact finalization; `run.status`,
  `run.success`, `run.startup_issue`, `run.process_status`, and
  `run.timed_out` report the launched game's outcome.
- `events.ndjson`: append-only runtime events. This is the safest file to tail
  for incremental progress.
- `video/frames/frame_###.png`: screenshots copied into stable frame names as
  they are produced.
- `video/frame_count.txt`: current number of mirrored frames. It starts at `0`
  and is overwritten after each copied frame.
- `video/latest_frame.txt`: absolute path to the newest mirrored frame. It is
  empty until the first frame arrives.
- `audio/quake_mix_s16le.raw`: post-QGE mixed stereo PCM when sound is enabled.
- `audio/quake_mix_s16le.json`: audio metadata, including sample rate, format,
  channels, and sample pair count.
- `audio/bytes.txt`: current raw PCM byte count. It starts at `0` and is
  overwritten as audio grows.
- `input/noesis_actions.txt`: Noesis action lines selected for this run.
- `input/noesis_commands.cfg`: translated Quake console commands emitted by
  the Noesis player.
- `noesis/qge_noesis_summary.json`: gameplay-quality reducer for Noesis runs,
  combining action/command traces, engine outcome telemetry, log health,
  captured frame motion, and trace evidence into a pass/blocked/not-requested
  status plus `noesis_gameplay_quality_score`.
- `noesis/qge_noesis_icc_evidence.json`: ICC evidence generated from the
  Noesis summary, including `agent_stream_noesis_status` inputs.
- `noesis/gameplay_outcomes.ndjson`: engine-owned Noesis outcome sidecar
  written once per host frame when `-qgestreamdir` is present. It records player
  health, armor, ammo, weapon, origin/view angles, route distance, leaf
  transitions, inferred damage dealt/taken, kills, pickups, attack presses, and
  enemy proximity/visibility. The summary derives ammo spent/gained,
  unproductive ammo spent, ammo waste fraction, and damage per ammo spent from
  these samples. When `QGE_NOESIS_ASSIST` is enabled, samples also include assist
  mode, target visibility/distance, aim yaw/pitch, steering commands,
  wall-probe distances, pre-assist aim error, and whether the assist injected
  view, movement, or attack state. Mode `2` also keeps a bounded target lock and
  suppresses fire on large first-frame target switches so Noesis can finish one
  viable monster instead of oscillating between nearby candidates. The assist
  keeps early E1M1 route phases visible-only for combat takeover, leaves the
  current view alone only when the pre-assist aim error is already close to
  aligned, and projects target-relative movement back into the current view basis
  so route movement is not dependent on a server view snap.
- `logs/quantum_quake.log`: runtime console log mirrored into the stream.
- `logs/open.log`: LaunchServices notes for macOS `open` mode.
- `trace/qge_trace_summary.json`: JSON summary of `qge_trace.bin`, including
  `runtime_evidence.single_trace_ready` and per-domain AI, audio, visibility,
  and projectile evidence counts. Visibility readiness requires an applied
  `vis_authority_apply` record, not only shadow/gate telemetry. Projectile
  evidence includes `active_projectiles_max`, `save_demo_boundary_count`, and
  per-kind save/demo counts for writeback, branch, and collision-oracle
  persistence boundaries.
- `qge_agent_stream_icc_evidence.jsonl`: ICC-native evidence entries for the
  manifest, events file, Noesis input traces, latest video frame, raw audio,
  audio metadata, trace artifact, trace summary, frame count, run outcome,
  trace status, Noesis summary status, runtime evidence readiness, and
  completion signal. Consumers can key on run outcome, trace status,
  `agent_stream_noesis_status`, and runtime evidence readiness without reading
  the console log.

The harness also refreshes stable pointers in the diagnostics roots:

- `diagnostics/agent_stream/latest_stream.txt`
- `diagnostics/agent_stream/latest_manifest.txt`
- `diagnostics/agent_stream/latest_events.txt`
- `diagnostics/agent_stream/latest_icc_evidence.txt`
- `diagnostics/quake_stream/latest_stream.txt`
- `diagnostics/quake_stream/latest_trace.txt`: latest non-empty trace file.
  Runs with `QGE_STREAM_TRACE=0`, or trace-requested runs that fail before
  writing `qge_trace.bin`, do not overwrite this pointer. If the pointer is
  empty or stale, the harness repairs it from the newest existing non-empty
  `diagnostics/quake_stream/*/qge_trace.bin`.

Consumers should treat `events.ndjson` as append-only and `manifest.json`,
`video/frame_count.txt`, `video/latest_frame.txt`, and `audio/bytes.txt` as
current-state pointers that may be rewritten.

## Stdout Markers

The script also prints machine-readable markers for harnesses that drive it
through stdout:

```text
QGE_AGENT_STREAM <dir>
QGE_AGENT_VIDEO_FRAME <index> <png>
QGE_AGENT_STREAM_DONE <dir>
```

Trace and failure paths may additionally print:

```text
QGE_TRACE_DONE <trace> bytes=<n>
QGE_TRACE_MISSING <trace>
QGE_RUNTIME_LOG_EMPTY <log>
QGE_STARTUP_FAILED <reason> <log>
```

Prefer the stream files for long-running consumers. Stdout is useful for launch
wrappers and CI logs, but it is not the canonical live state.

## Performance Timing

When `quantum_debug 1` is active, `QGE render frame=...` log lines include a
high-resolution CPU timing split:

- `encode`: total scene encoding before inverse DWT.
- `setup`: QGE frame reset, snapshot lookup, and render-gate work.
- `raster`: world/entity/particle rasterization into sparse spatial fields.
- `fdwt`: forward sparse DWT encoding for the RGB spatial fields.
- `dwt`: sparse coefficient extraction plus inverse DWT reconstruction.
  Native bridge runs also emit `native_idwt`, `idwt_fallback`, and `cpu_idwt`
  counts. `native_idwt>0` with `idwt_fallback=0` proves the sparse DWT
  framebuffer reconstructed through the native Metal bridge instead of the CPU
  inverse-DWT path. The same line includes `idwt_backend`, `idwt_path`, and
  `idwt_reason` so CPU, native, mixed, and intentional fallback paths remain
  machine-readable in `qge_perf_summary.py` and trace-derived runtime evidence.
- `gate_p`, `gate_edge`, `gate_gain`, `edge_gain`, `material_gain`, and
  `gate_rgb`: render-gate state observables and derived display gains. The
  finite-shot counters remain logged as measurement telemetry, but visible
  floor/wall/ceiling gain uses deterministic state marginals so a static camera
  does not shimmer from per-frame shot noise.
- `convert`: tone mapping and RGB display-buffer conversion.
- `blit`: OpenGL texture upload and screen draw.

Primary render logs also include ownership fields for the 2D pass. QGE mirrors
HUD and console draw calls through registered HUD image refs, the conchars
glyph atlas, and generated fill primitives. Once a completed 2D frame has been
mirrored, `own_hud=1`, `own_console=1`, `classic2d=0`,
`suppressed2d=<draws>`, and `fallback_reason=none` prove the classic 2D output
is accounted for by QGE ownership telemetry. The trace also records
`render_2d_overlay` probes for those mirrored draw calls.

`quantum_render_update_interval` controls how often the expensive 1024-frame
QGE field is regenerated. The default interval is `1`, so primary QGE rendering
updates every host frame while the player moves. Higher values deliberately
reuse stale world textures between updates and are useful only for reuse-cost
profiling.

For CPU-only profiling, keep `QGE_RENDER_RES` fixed and compare these fields
across runs. A slow 1024 run is usually dominated by `raster`, not by the
LaunchServices wrapper.

Startup logs and traces also include a `backend_gate` probe. It reports the
selected backend, whether the native backend probe succeeded, whether
acceleration is active for the live context, the runtime path, the native probe
reason, and the reason when a capable backend is intentionally running the
sparse CPU path. Once the sparse render bridge is active, the path becomes
`native_sparse_dwt_render_bridge` and render traces set the `native_idwt` flag.
The engine emits the gate at init, render-bridge activation, and shutdown so
traces prove both the selected backend and the teardown path. The performance
summary sidecar parses these lines into `backend_gate_event_count`,
`backend_gate_paths`, and `backend_gate_render_bridge_paths`; the vanilla matrix
requires that backend-gate evidence before marking the QGE performance domain
ready. Native backend selection points also emit `QGE: Runtime backend probe`
lines for `qge_context_get_or_create_render_acceleration`, `qge_dwt_render`,
and `qge_metal_init_common`. The performance sidecar parses them into
`runtime_backend_probe_event_count`, `runtime_backend_probe_targets`,
`runtime_backend_probe_paths`, `runtime_backend_probe_results`, and
`runtime_backend_probe_proofs`, plus a compact `runtime_backend_boundary`
verdict. The proof map is keyed by native boundary and records each target's
backend, phase, result, path, active/native flags, and whether that target
reached `native_sparse_dwt_render_bridge`. Publication packs also materialize
that verdict as `resource/qge_native_backend_boundary.json`. The vanilla
matrix requires `runtime_backend_probe_resolved=1`, meaning
`qge_context_get_or_create_render_acceleration`, `qge_dwt_render`, and
`qge_metal_init_common` all have native render-bridge proof alongside the
backend gate before marking QGE performance ready.
Texture/material setup emits `texture_signal_cache` and
`lightmap_signal_cache` probes as well. These mark the surface texture and
lightmap signal paths as intentional CPU-side metadata/sample caches and record
cache entry, fullbright, warp, lit-surface, and contrast counts for the loaded
map. During rendered frames, `world_surface_submission` records how many BSP
surfaces were submitted into the QGE scene buffer, dropped by the fixed budget,
and copied into the frame snapshot.

## Launch Modes

`QGE_STREAM_LAUNCH=auto` is the default. On macOS it selects `open`; on other
platforms it selects direct binary execution.

All stream launches pass the app's `-nolauncher` argument so automation cannot
stall behind the click-through launcher window. The macOS launcher parses this
argument before probing display modes, skips launcher UI argument rewriting, and
hands the original command line to Quake directly. On macOS `open` mode, the
harness also uses `open -W -n -F` plus `-ApplePersistenceIgnoreState YES`: it
waits for the app, starts a new instance, asks LaunchServices to ignore
restored window state, and does not require a manual click. The generated app
bundle also opts the launcher window out of AppKit state restoration and writes
an exact `APPL????` `PkgInfo` record so LaunchServices can scan the bundle. The
harness passes `-nomouse` by default so SDL does not enter relative mouse mode
or warp/capture the user cursor. It lets SDL choose the display by default;
set `QGE_STREAM_DISPLAY` only when a specific display index is required. Set
`QGE_STREAM_ACTIVATE=1` only if the local window manager requires a foreground
app for capture. A side watcher tails `qconsole.log`, mirrors screenshots, and
refreshes audio byte counts while the app is still running. After the run, the
harness archives the log into the capture and agent-stream directories and
removes the root `qconsole.log` copy so generated runtime output does not
pollute source-drift checks.
The macOS bootstrap emits `QGE launcher probe` lines for host-side AppKit/SDL
entry points (`SDLMain`, `SDLApplication`, `AppController`, `QuakeArguments`,
`QuakeArgument`, `IsFinderLaunch`, and `ScreenInfo`). These lines are host
launch evidence only, not Moonlab authority claims. In `-nolauncher`
automation, launcher UI controls and display-mode enumeration are reported as
intentional skips so ICC can distinguish the deliberate automation path from an
unexercised production launch path.
The harness also passes `-display "$QGE_STREAM_DISPLAY"` when set. On the
current capture workstation the default is SDL display `1`, which maps to the
BenQ PD3200U; SDL display `0` is the LG. The engine logs the available display
indexes and bounds at video startup so this can be adjusted when the monitor
layout changes.

Use `QGE_STREAM_LAUNCH=direct` only when running the app binary directly is
more reliable in the local environment. Direct mode redirects the runtime log
through the harness process instead of reading `qconsole.log`, and records the
child process exit status if the app aborts before video/log initialization.

## Capture Timing

Engine auto-capture is enabled by default with `QGE_STREAM_ENGINE_CAPTURE=1`.
The screenshot frame defaults to `QGE_STREAM_WAIT_FRAMES`.

Some action scripts execute fewer rendered frames than their command-buffer wait
count suggests. For those runs, set `QGE_STREAM_CAPTURE_WAIT=<frames>` to choose
the engine screenshot frame explicitly. When `QGE_STREAM_FIRE_TEST=1` and no
override is provided, the harness captures at roughly two-thirds of
`QGE_STREAM_WAIT_FRAMES`, with a floor that falls back to the normal wait for
very small values.

For the default Noesis player, the implicit capture frame is never earlier than
`QGE_NOESIS_MIN_CAPTURE_WAIT` (default `280`) or `QGE_NOESIS_START_WAIT + 4`,
whichever is larger. This keeps short screenshot smokes from quitting before the
E1M1 route/combat plan has enough engine-owned gameplay samples. An explicit
`QGE_STREAM_CAPTURE_WAIT` continues to mean exactly the frame requested.
Scripted Noesis runs also append a `QGE_NOESIS_CAPTURE_HOLD` wait block when
engine auto-capture is active, so fire/combat scripts cannot exhaust the command
buffer one or two frames before `-qgeautocapture` writes the evidence PNGs.

The launch watchdog defaults to `90 + QGE_STREAM_FRAMES *
QGE_STREAM_WAIT_FRAMES / 10` seconds. Set `QGE_STREAM_TIMEOUT_SECONDS` for
large map-load smokes or slow display launches that need a fixed budget.
Malformed or zero numeric overrides fall back to the documented defaults before
the watchdog budget, manifest, and engine capture arguments are written. Boolean
overrides use `1` for enabled and otherwise fall back to disabled, keeping
`manifest.json` parseable even when an environment override is malformed.

Set `QGE_STREAM_ENGINE_CAPTURE=0` to use scripted `screenshot png` commands
instead of engine auto-capture. This mode still mirrors discovered `spasm*.png`
files into the agent stream.

## Sprite Diagnostics

`QGE_STREAM_SPRITE_TEST=1` enables the engine cvar
`quantum_debug_sprite_billboard 1` for that run. The QGE snapshot then adds one
diagnostic sprite entity from the first registered sprite asset directly in
front of the camera. This is opt-in evidence for the sprite billboard encoder:
normal gameplay captures leave the diagnostic disabled and report only actual
visible entities.

## Related Harnesses

`tools/quake_graphics_harness.sh` runs paired classic/QGE captures through the
stream harness and copies each run's Noesis action and command traces into the
comparison artifact directory. It probes `tools/qge_image_metrics.py
--check-deps` before launching either capture because the comparison metrics
require numpy and Pillow. If either dependency is unavailable, the harness now
continues with `tools/qge_world_frame_metrics.py`, a standard-library PNG
fallback that reports fixed world-region RMSE, luma means, and high-frequency
texture-energy ratios for floor, wall, ceiling, corridor, upper-playfield, and
viewmodel crops. The
harness copies every captured `frame_*.png` into per-mode frame directories; in
fallback mode, multi-frame captures are averaged instead of scoring only the
last screenshot. Set `QGE_HARNESS_BASELINE_CANDIDATE` to a previous QGE PNG or
frame directory to include baseline deltas in `metrics.json` and `metrics.md`.
Set `QGE_HARNESS_FORCE_WORLD_METRICS=1` to exercise the standard-library scorer
even when numpy/Pillow are installed. The graphics harness defaults
`QGE_HARNESS_FLATLIGHTSTYLES=1`, passing `QGE_STREAM_FLATLIGHTSTYLES` through
the stream autoexec as `r_flatlightstyles`, so fixed-view captures compare
renderer output instead of animated lightstyle phase.
For all-domain Moonlab evidence, the paired harness forwards
`QGE_HARNESS_TRACE`, `QGE_HARNESS_FIRE_TEST`, `QGE_HARNESS_SPRITE_TEST`,
`QGE_HARNESS_PARTICLES`, `QGE_HARNESS_SND_QUANTUM`,
`QGE_HARNESS_SND_QUANTUM_SOURCE_AUTHORITY`, and
`QGE_HARNESS_PHYSICS_AUTHORITATIVE` into each stream run so
`vanilla_capture_matrix.json` can evaluate audio, sprite, particle, projectile,
and render workload ownership in one artifact.
The paired `tools/qge_vanilla_capture_matrix.py` sidecar copies each mode's
agent-stream run and trace summary from `*.agent_stream.json`; an explicit
agent-stream run failure blocks `ready_for_complete_claim`. It also preserves
each mode's copied `*.qge_perf_summary.json` sidecar, records per-mode
performance status and max timing fields, and treats an explicit blocked
performance sidecar as not ready for the complete vanilla claim. The publication
pack copies these run-status fields from the vanilla matrix and also records the
packed agent stream manifest's direct `run.status`, `run.success`,
`run.startup_issue`, frame count, and trace status in its runtime summary and
ICC evidence. A failed direct stream manifest makes the publication ICC result
evidence-only instead of `qge_publication_artifact_pack_complete`. Pass
`--breadth-evidence <breadth_dir>` to `tools/qge_publication_pack.py` to include
the multi-map breadth sidecar in the publication bundle; the pack records the
breadth map count, fallback/surrogate/CPU-IDWT totals, native bridge count,
backend-gate count, and runtime-backend-probe totals in both the manifest and
ICC evidence.
`tools/qge_perf_summary.py` reads a capture directory or `quantum_quake.log`
and emits structured timing evidence for `QGE render frame=` component timings
and `QGE: Average quantum render time` lines, with optional JSON and ICC
sidecars plus threshold checks for performance regression smokes. The stream
harness runs this summarizer after the runtime log is finalized, writes
`qge_perf_summary.json` and `qge_perf_icc_evidence.json` under the capture
directory, mirrors both files into `agent_stream/performance/`, and records the
status in `manifest.json` plus `agent_stream_perf_status` in the JSONL ICC
sidecar. Set `QGE_PERF_MAX_AVERAGE_MS` or `QGE_PERF_MAX_RENDER_MS` to turn a
capture into a thresholded performance smoke without failing the media stream
itself; threshold failures mark the performance sidecar `blocked`.
Publication packs use the stream capture for trace/oracle inputs and prefer the
paired `quake_graphics` QGE candidate performance sidecar when the vanilla
matrix comes from a graphics harness directory. This keeps raw stream-side
summaries from blocking a paper pack when the publication evidence is the paired
classic-vs-QGE graphics run. The pack exposes direct and per-mode max
average/render timing fields in the publication runtime summary and ICC evidence,
and treats an explicit blocked publication performance sidecar as evidence-only
rather than `qge_publication_artifact_pack_complete`.
`tools/qge_breadth_evidence.py` aggregates multiple
`vanilla_capture_matrix.json` files and optional publication packs into a
machine-readable multi-run evidence sidecar. It emits
`qge_breadth_evidence_pack_complete` only when every supplied matrix keeps
Moonlab authority ready, uses the QGE primary framebuffer with native IDWT, and
reports zero fallback, surrogate, and CPU-IDWT counts. The breadth aggregate
also carries backend-gate and runtime-backend-probe counts, paths, results, and
targets, plus per-target proof maps, missing/native target sets, and
`runtime_backend_probe_resolved_run_count` so the native backend claims can be
audited across every supplied run. It also emits
`qge.full_game_map_coverage.v0`, a canonical registered single-player map
ledger that stays `partial` until every target map has a ready QGE/Moonlab run.
Use `--min-maps` when the artifact needs to prove breadth across distinct maps
instead of repeated captures of one map.
`tools/qge_full_game_capture_queue.py <publication_pack_or_breadth_dir>` turns
that ledger into `qge.full_game_capture_queue.v0` plus a runnable
`run_missing_maps.sh` script. The queue inventories loose `maps/*.bsp` files
and `pak*.pak` directories before it writes jobs, skips maps whose BSP is
absent unless `--include-unavailable-assets` is set, and records the
asset-unavailable missing maps in JSON/Markdown. The generated script runs
`tools/quake_graphics_harness.sh` for each missing canonical map using the
Noesis-fire authority-smoke profile by default, orders combat maps before
`start`/`end`, marks those noncombat/endgame maps as
`special_route_required`, and then rebuilds breadth evidence with the previous
ready matrices plus the new capture directories.

`tools/qge_noesis_summary.py` reads the stream manifest, Noesis action trace,
translated command buffer, runtime log, `noesis/gameplay_outcomes.ndjson`,
captured frames, and optional trace summary. The stream harness runs it after
frame, performance, trace, and gameplay-outcome collection, writes
`qge_noesis_summary.json` and
`qge_noesis_icc_evidence.json` under the capture directory, mirrors both files
into `agent_stream/noesis/`, and records the result as
`agent_stream_noesis_status` in the JSONL ICC sidecar. It also emits
`noesis_route_action_count`, `noesis_gameplay_quality_score`,
`noesis_gameplay_quality_grade`, `noesis_log_phase_count`,
`noesis_log_policy_done`, `noesis_gameplay_phase_event_count`,
`noesis_gameplay_phase_stuck_window_count`,
`noesis_gameplay_outcome_sample_count`, `noesis_gameplay_total_distance`,
survival, damage, kill, pickup, visible enemy evidence, attack-visible and
attack-aligned frame counts, blind/unproductive attack frame counts,
nearest-enemy aim-error evidence, damage per attack press, net damage per
attack press, ammo spent/waste evidence, damage per ammo spent, trace identity,
replay health, and projectile save/demo boundary
evidence such as
`noesis_projectile_save_demo_boundary_count` and
`noesis_projectile_save_demo_trace_id_xor`. The Noesis player
keeps the console `QGE_NOESIS_PHASE` marker for log compatibility and also
executes `qge_noesis_phase`, which queues an engine-owned `noesis_phase` event
in `gameplay_outcomes.ndjson` with the next gameplay sample's player, route,
combat, pickup, and assist state. Required combat progress needs damage, a kill,
or an attack while the player is aligned to a visible enemy; pressing fire near
an enemy is not enough. Phase names such as `*_clear` only require combat
progress when the interval also contains a combat opportunity: visible enemy
samples, close enemy-contact samples, damage, kills, or visible/aligned attack
telemetry. Blind fire by itself does not turn a route-only interval into a
blocked combat phase. The gameplay score discounts attack-press credit when
attack frames are blind or visible-but-unaligned, and applies a small combat
penalty when observed ammo spend is unproductive. Route telemetry also reports
movement efficiency, stationary fraction, maximum stationary run, and
duration-aware terminal-stall evidence, so a route that moves early and ends
wedged cannot pass as clean progress while a short post-plan idle tail does not
poison a long successful route. Assist runs additionally emit requested mode,
active sample count, visible-target sample count, steering sample count,
attack-visible frames, target-distance evidence, view/movement/attack injection
sample counts, target-lock/switch counts, pre-assist aim-error min/average,
switch-fire suppression counts, and a claim scope. Assisted runs are marked
`server_assisted` for scripted fixtures or `server_autonomous` for no-script
engine-controlled runs, so they cannot be mistaken for unassisted play
evidence. Set `QGE_NOESIS_MIN_LOG_PHASES` to
require that many `QGE_NOESIS_PHASE` markers to appear in the engine log and
matching engine-owned `noesis_phase` outcome events to appear in gameplay
telemetry, which is useful when proving that a longer route plan actually
executed rather than only being generated. Set `QGE_NOESIS_MIN_GAMEPLAY_SAMPLES` and
`QGE_NOESIS_MIN_ROUTE_DISTANCE` to require engine-owned state samples and route
movement evidence. This reducer is evidence-only: a blocked Noesis quality
summary does not turn a completed media stream into a process failure.

`tools/quake_crash_watch.sh` uses the same Noesis player/provider contract,
keeps scripted movement disabled by default, stores `input/noesis_actions.txt` and
`input/noesis_commands.cfg` under its crash-watch output directory, passes
`-nomouse` unless `QGE_STREAM_MOUSE=1`, targets `QGE_STREAM_DISPLAY` like the
stream harness, and pins the same high-resolution CPU render defaults: 1024
internal render resolution, no bilinear/edge/display smoothing, and
`QGE_RENDER_UPDATE_INTERVAL=1` unless overridden. The crash watcher records
process exit status in its final `QGE_CRASH_WATCH_EXIT`,
`QGE_CRASH_WATCH_TIMEOUT`, or `QGE_CRASH_WATCH_DONE` line so direct app aborts
and watchdog kills are not mistaken for clean runs. When QuakeSpasm emits a
crash-watch `qconsole.log` under either the game base directory or the repo
root, the harness archives it and then removes the generated source-tree copy so
crash diagnostics do not leave mutable runtime logs behind.
Numeric crash-watch inputs are normalized as decimal values before shell
arithmetic, so leading-zero overrides such as `QGE_CRASH_SECONDS=08` do not emit
bash base-conversion errors into diagnostics.

## Audio

Audio is disabled by default because most graphics smokes run with `-nosound`.
Enable it with:

```sh
QGE_STREAM_SOUND=1 bash tools/quake_graphics_stream.sh
```

The raw audio format is signed 16-bit little-endian stereo PCM. Read
`audio/quake_mix_s16le.json` for the sample rate before playback or conversion.
If sound is requested but no audio has arrived yet, `manifest.json` reports
`audio.status` as `requested_missing` and `audio/bytes.txt` remains `0`.

For source-authority runs, `tools/qge_audio_authority_smoke.py` validates a
completed agent stream. It checks `snd_quantum 2`, source authority enabled,
nonzero captured audio, source-spatial/source-frame trace probes, and source
volume selection or explicit gated fallback telemetry in the runtime log.

## Failure Signals

When trace capture is requested but no trace file is written, the harness
classifies startup progress from the runtime log:

- `gl_context_failed`: the log reported an SDL/OpenGL context failure.
- `video_init_missing`: the process did not reach Quake video initialization.
- `trace_init_missing`: video initialized, but QGE trace startup did not.

The failure is emitted both as `QGE_STARTUP_FAILED <reason> <log>` on stderr and
as a `startup_failed` entry in `events.ndjson`. LaunchServices failures are
reported as `open_failed` events and `QGE_OPEN_FAILED status=<n>` in
`logs/open.log`.

Even on failure, the harness finalizes the stream: `manifest.json` is written
with top-level status `complete`, `events.ndjson` receives `stream_done`, and
the frame and audio pointer files remain present for consumers that expect a
stable contract. Consumers that need launch success should read
`manifest.json`'s `run.status`, `run.success`, and `run.startup_issue` fields.

## Noesis Action Files

`tools/noesis_quake_player.sh` translates a small line-oriented action stream
into Quake console commands. Blank lines and `#` comments are ignored. Each
action accepts an optional wait-count argument, so `forward 12` emits
`+forward`, twelve `wait` commands, then `-forward`.
Wait counts are normalized as decimal integers and clamped to
`QGE_NOESIS_MAX_WAIT` waits per action, default `600`, so a malformed provider
cannot accidentally expand the command buffer without a visible
`QGE_NOESIS_PLAYER wait_clamped` marker.

Example:

```text
forward 12
turn-right 6
attack 4
wait 2
```

Supported movement/action verbs are `forward`, `back`, `turn-left`,
`turn-right`, `strafe-left`, `strafe-right`, `jump`, `use`, `speed`,
`look-up`, `look-down`, `center-view`, `swim-up`, `swim-down`, `attack`,
`wait`, `weapon`, `weapon-next`, `weapon-prev`, and `give`. Composite combat
verbs include `run-forward`, `jump-forward`, `advance-fire`, `retreat-fire`,
`scan-fire-left`, `scan-fire-right`, `strafe-fire-left`, `strafe-fire-right`, `circle-fire-left`,
`circle-fire-right`, `wall-slide-left`, `wall-slide-right`,
`speed-jump-forward`, `door-open`, `door-bump`, and `clear-input`. `door-open`
holds forward plus use before recovery; `door-bump` uses a timed forward bump
because classic Quake doors are often route-touch targets in this command-buffer
path. `cmd` or
`quake` passes the remaining text through as a raw Quake console command for
targeted probes.
`scan-fire-left` and `scan-fire-right` hold keyboard yaw plus attack for a
short target-acquisition sweep; they do not use mouse input or screen control.
The adaptive/E1M1 route plans are now explicit scripted fixtures, not the
default Noesis behavior. Set `QGE_NOESIS_SCRIPTED=1`, `QGE_NOESIS_ACTIONS_FILE`,
or `QGE_NOESIS_CMD` when you intentionally want command-buffer route playback.
Those fixtures aim and move with keyboard-only turns and route actions, then
use short attack taps or bounded scan-fire sweeps instead of long blind fire
holds. The E1M1 adaptive route brackets its first acquisition block with a
short keyboard `look-up` and `center-view` recenter so attacks sweep a more
useful enemy sightline without taking over the user's mouse. The bridge block
closes farther along the left bridge side before a bounded `scan-fire-left`
sweep, and the door block adds a short left/right scan after the door bump
before its speed-jump-forward recovery, then begins the bounded hunt loop with
a keyboard-only back/turn/jump unstick prelude before another controlled
movement and acquisition pass.

With the default `QGE_NOESIS_SCRIPTED=0` and `QGE_NOESIS_ASSIST=2`, Noesis is a
server-autonomous diagnostic controller: movement and combat evidence must come
from engine-owned gameplay telemetry and assist injection counters, not from a
cached route script. The harness also sets `qge_noesis_autonomous 1` in this
mode so the engine can use a wider hidden-target chase window before any
scripted route phase exists. This is not yet a learning loop; no model weights
or policy parameters are trained during a run.
Scripted fixture runs remain marked `server_assisted` when assist is enabled.
Generic combat-exploration recovery backs out, side-slides, turns, and jumps
forward before the second push so a terminal wall contact is less likely to
leave the plan wedged.

Action streams can come from either `QGE_NOESIS_ACTIONS_FILE` or
`QGE_NOESIS_CMD`. The command provider runs from `QGE_NOESIS_DIR` and should
print the same action lines to stdout; this remains the hook for scripted
policy fixtures that write actions instead of capturing the user's mouse. The
provider is executed directly, so use a small wrapper script for shell
pipelines, redirection, or other compound commands. Every run mirrors the
selected action stream and translated Quake command stream into
`input/noesis_actions.txt` and `input/noesis_commands.cfg`.

When neither an action file nor a provider is set, `QGE_NOESIS_SCRIPTED=0`
keeps the Noesis player in autonomous mode and emits only metadata commands;
it does not run `tools/noesis_quake_policy.sh` or any built-in route plan. Set
`QGE_NOESIS_SCRIPTED=1` to use `tools/noesis_quake_policy.sh`, the repo-local
cached-policy provider. An explicit `QGE_NOESIS_CMD` still takes precedence over
`QGE_NOESIS_ACTIONS_FILE`, and both take precedence over the scripted default.

### Noesis No-Script Triage

For default no-script runs, `input/noesis_actions.txt` being empty is expected.
That means no cached route script was translated. Movement should instead show
up in engine-owned telemetry:

- manifest input fields should report `noesis_scripted=0`,
  `noesis_autonomous=1`, and `noesis_assist=2` unless the run deliberately
  overrides them;
- `noesis/qge_noesis_summary.json` should report nonzero
  `gameplay.route.total_distance` or displacement;
- `gameplay.assist.movement_injected_sample_count` should be nonzero when the
  autonomous controller is steering the server usercmd;
- `noesis/gameplay_outcomes.ndjson` should contain `sample` records with
  `assist.movement_injected` or visible route displacement.

If all of those are zero, Noesis did not learn to stay still; the autonomous
controller failed to engage or the stream launched without the intended Noesis
mode. Current Noesis is a reactive controller with telemetry, not a training
loop with policy updates.

## Common Environment Variables

- `QGE_AGENT_STREAM_DIR`: override the agent stream output directory.
- `QGE_STREAM_MAP`: map to load, default `start`.
- `QGE_STREAM_FRAMES`: number of screenshots requested, default `12`.
- `QGE_STREAM_WAIT_FRAMES`: default engine capture wait, default `20`.
- `QGE_STREAM_CAPTURE_WAIT`: explicit engine capture frame.
- `QGE_STREAM_TIMEOUT_SECONDS`: explicit launch/watchdog timeout.
- `QGE_STREAM_APP_BIN`: optional direct-launch executable override. This keeps
  the same harness, `-nomouse`, and stream manifest path when macOS
  LaunchServices refuses the app bundle but the standalone build product is
  usable.
- `QGE_STREAM_TRACE`: write `qge_trace.bin` when set to `1`.
- `QGE_STREAM_REPLAY_TRACE`: load an existing QGE trace with `-qgereplay`.
- `QGE_STREAM_REPLAY_STRICT`: strict replay metadata checks, default `1`.
- `QGE_STREAM_SOUND`: run with game sound enabled when set to `1`.
- `QGE_STREAM_AI`: emitted as `quantum_ai`, default `1`.
- `QGE_STREAM_VIS`: emitted as `quantum_vis`, default `2`. Raw mode `2` uses
  the audited classic PVS/cull accepted set as the Grover oracle input, applies
  a confidence floor to suppress diffuse low-amplitude over-inclusion, and
  still falls back on repair or any remaining parity mismatch. Mode `3` enables
  the controlled visibility-authority smoke path: the audited QGE writeback mask
  is forced to match the classic accepted surface set so the renderer handoff
  can prove `vis_authority_apply` independently of raw oracle quality.
- `QGE_STREAM_FIRE_TEST`: run the scripted weapon smoke when set to `1`.
  With the default Noesis player this selects the Noesis `fire` plan unless
  `QGE_NOESIS_PLAN` is set explicitly, and enables `QGE_NOESIS_SCRIPTED=1`
  unless that variable is explicitly set.
- `QGE_STREAM_SPRITE_TEST`: inject one QGE diagnostic sprite billboard when set
  to `1`, default `0`.
- `QGE_STREAM_ENGINE_CAPTURE`: use engine auto-capture when set to `1`, default
  `1`.
- `QGE_STREAM_LAUNCH`: `auto`, `open`, or `direct`.
- `QGE_STREAM_DISPLAY`: SDL display index or display-name substring, default
  `1` for the BenQ PD3200U on this workstation. Use `0` for the LG, or a
  display-name substring on SDL builds that expose monitor names.
- `QGE_STREAM_MOUSE`: pass through SDL mouse input when set to `1`. The default
  is `0`, which launches Quake with `-nomouse` so the harness never captures
  the user's cursor.
- `QGE_STREAM_PLAYER`: harness player owner, default `noesis`. Set to `none`
  to disable harness-generated gameplay commands.
- `QGE_NOESIS_DIR`: Noesis repo path used for player provenance, default
  `~/Desktop/noesis`.
- `QGE_NOESIS_SCRIPTED`: opt in to repo-local scripted command-buffer playback,
  default `0`. Normal `QGE_STREAM_PLAYER=noesis` runs leave this off so Noesis
  does not use cached route scripts. Set it to `1` for regression fixtures that
  intentionally use `tools/noesis_quake_policy.sh`.
- `QGE_NOESIS_AUTONOMOUS`: optional override for the engine-side no-script
  controller hint. When unset, the stream harness enables it for
  `QGE_STREAM_PLAYER=noesis` runs that have no action file, no provider, and
  `QGE_NOESIS_SCRIPTED=0`.
- `QGE_NOESIS_REQUIRE_COMBAT`: optional Noesis summary combat gate override.
  When unset, scripted fixture runs require combat evidence and no-script
  autonomous runs first require movement/control evidence. Set it to `1` to
  demand visible/aligned combat from a no-script run.
- `QGE_NOESIS_PLAN`: Noesis command-buffer plan used only for scripted fixture
  runs, default `adaptive`;
  supported plans are `patrol`, `scout`, `fire`, `map-scout`, `combat-scout`,
  `combat-explore`, `e1m1-route-push`, `weapon-cycle-smoke`, and `adaptive`.
  `adaptive` selects a map-aware route/combat plan when one exists, and
  otherwise falls back to the generic combat-exploration loop.
- `QGE_NOESIS_ACTIONS_FILE`: optional Noesis action file. When present, the
  harness translates each line into Quake console commands instead of using
  autonomous control. Supported actions include `forward`, `back`,
  `turn-left`, `turn-right`, `strafe-left`, `strafe-right`, `jump`,
  `center-view`, `advance-fire`, `circle-fire-left`, `circle-fire-right`,
  `scan-fire-left`, `scan-fire-right`, `wall-slide-left`, `wall-slide-right`,
  `speed-jump-forward`, `door-bump`,
  `door-open`, `weapon-next`, `weapon-prev`, `attack`, `wait`, `weapon`, and
  `give`, with an optional wait-count argument.
- `QGE_NOESIS_START_WAIT`: command-buffer waits emitted before Noesis actions,
  default `16`. Set to `0` when the action file already includes its own
  startup delay.
- `QGE_NOESIS_MAX_WAIT`: maximum waits emitted by a single Noesis action,
  default `600`; larger counts are clamped and traced. The stream manifest
  records the normalized cap as `input.noesis_max_wait`.
- `QGE_NOESIS_MIN_LOG_PHASES`: minimum Noesis phase markers that must appear in
  the runtime log and as engine-owned `noesis_phase` gameplay outcome events for
  the Noesis summary to pass, default `0`.
- `QGE_NOESIS_MIN_GAMEPLAY_SAMPLES`: minimum engine-owned
  `gameplay_outcomes.ndjson` samples required for the Noesis summary to pass,
  default `2` in the stream harness.
- `QGE_NOESIS_MIN_ROUTE_DISTANCE`: minimum route distance or displacement, in
  Quake units, required for route-heavy Noesis plans once gameplay telemetry is
  present, default `64`.
- `QGE_NOESIS_MIN_CAPTURE_WAIT`: minimum engine auto-capture delay for Noesis
  runs when `QGE_STREAM_CAPTURE_WAIT` is unset, default `280`. Set to `0` only
  when intentionally testing early capture or startup behavior.
- `QGE_NOESIS_ASSIST`: server-state assist for Noesis automation. The stream
  harness defaults to mode `2`; set `QGE_NOESIS_ASSIST=0` for unassisted claim
  runs. In no-script mode, this is the only current source of gameplay control.
  When `qge_noesis_autonomous` is enabled, hidden-target chase can begin out to
  `QGE_NOESIS_AUTONOMOUS_CHASE_DISTANCE`; scripted fixture phases keep the
  narrower `QGE_NOESIS_HIDDEN_CHASE_DISTANCE` route-protection behavior. If
  all target-facing wall probes are blocked under `QGE_NOESIS_WALL_TRAP_CLEAR`,
  the controller backs out and strafes instead of continuing to push forward.
  Partial wall contacts under `QGE_NOESIS_WALL_SLIDE_CLEAR` keep the clearer-side
  strafe but remove forward pressure for hidden targets, so no-script movement
  is less likely to park the camera against nearby floors, walls, or ceilings
  while trying to chase an enemy through solid geometry. The clearer-side choice
  is held for `QGE_NOESIS_WALL_FOLLOW_FRAMES` frames so a blocked hidden target
  does not make the controller flip-flop in place. In autonomous no-script mode,
  hidden targets are additionally wall-stall gated: if a target inside
  `QGE_NOESIS_HIDDEN_WALL_STALL_DISTANCE` keeps the target-facing probe below
  `QGE_NOESIS_WALL_SLIDE_CLEAR` for
  `QGE_NOESIS_HIDDEN_WALL_STALL_FRAMES`, the target is cooled down instead of
  letting Noesis sidestep around the same wall contact. A hidden target that
  does not become visible within
  `QGE_NOESIS_HIDDEN_CHASE_VISIBILITY_TIMEOUT_FRAMES` is cooled down for
  `QGE_NOESIS_HIDDEN_CHASE_COOLDOWN_FRAMES`, forcing target reacquisition
  instead of indefinitely pursuing the same unseen monster. A hidden locked
  target is also dropped when a visible enemy is within
  `QGE_NOESIS_VISIBLE_BREAK_HIDDEN_LOCK_DISTANCE`, so the autonomous controller
  does not ignore an immediate fight in favor of pathing into a wall toward an
  unseen monster. If autonomous mode has no engaged target, the controller now
  falls back to local clearance exploration: it probes forward/left/right from
  the current view, verifies floor and non-lethal contents ahead with
  `QGE_NOESIS_EXPLORE_FLOOR_PROBE_DISTANCE`, moves forward through open space,
  and turns/slides away from wall contacts using `QGE_NOESIS_EXPLORE_TURN_DEG`.
  This keeps no-script runs moving without a cached route script.
  Mode `1` aims and fires at visible monsters while preserving any existing
  movement command. For mode `1`, visible targets are ranked by
  current aim error first and distance second, so a scan does not abandon the
  enemy closest to the crosshair for a merely nearer side target. Mode `2` also
  steers the server usercmd toward a short-lived locked monster target with a
  small wall-avoidance probe and kites visible close targets instead of walking
  into them. When hidden-target chase hits a wall, its sidestep follows the clearer
  probe side using Quake's sidemove sign convention. Hidden distant targets do not override
  scripted view or route movement; the E1M1 entry, bridge, and door-slide phases
  are visible-only for combat takeover so hidden enemies cannot hijack the route
  through walls. Once the scripted route reaches the exit/hunt phases,
  hidden-target chase can help finish the approach, while assist still
  suppresses blind fire until a target is visible. It also skips server view
  injection when Noesis is already aimed within `QGE_NOESIS_VIEW_HOLD_DEG`,
  which is intentionally tighter than `QGE_NOESIS_AIM_ALIGNED_DEG` because
  firing and view control have different risk budgets. Injected movement is
  projected through the current view basis, so holding the view does not make
  target chase movement drift into walls. Visibility and aim use a sampled
  monster bbox point, so partly exposed enemies are not limited to a center-point
  trace.
  The engine-side cvar is `qge_noesis_assist`, remains off by default, and only
  acts during `-qgestreamdir` runs so normal local play is untouched.
- `QGE_NOESIS_CMD`: optional Noesis action provider command. When set, the
  harness runs it from `QGE_NOESIS_DIR` and translates its stdout action lines;
  this takes precedence over `QGE_NOESIS_ACTIONS_FILE` and the opt-in
  `tools/noesis_quake_policy.sh` provider.
- `QGE_STREAM_WIDTH`, `QGE_STREAM_HEIGHT`, `QGE_STREAM_FULLSCREEN`: window
  controls.
- `QGE_RENDER`, `QGE_RENDER_RES`, `QGE_RENDER_THRESHOLD`,
  `QGE_RENDER_EDGE_GAIN`, `QGE_RENDER_MATERIAL_GAIN`,
  `QGE_RENDER_BILINEAR_SAMPLES`, `QGE_RENDER_EDGE_SAMPLES`,
  `QGE_RENDER_DETAIL_MIX`, `QGE_RENDER_DISPLAY_FILTER`,
  `QGE_RENDER_UPDATE_INTERVAL`: QGE render controls. Engine autocapture skips
  the diagnostic console/dev overlay while
  capture is active, so diagnostic chatter is still logged but does not cover
  captured world frames. After the requested autocapture screenshots are queued,
  the harness exits through the console quit path instead of idling until the
  watchdog timeout. `QGE_RENDER_EDGE_GAIN` defaults to `0`; the diagnostic
  world-edge overlay is opt-in because it makes floors, walls, and ceilings read
  as noisy polygon outlines in normal captures. Viewport-clipped world polygons
  use perspective-correct interpolation for texture and lightmap coordinates.
  The native Metal render bridge is only considered available when it can create
  a command queue; if that probe fails, QGE falls back to the CPU/NEON path
  instead of accepting a no-op native reconstruction.
  `QGE_RENDER_BILINEAR_SAMPLES=1` uses bilinear texture/light samples in the
  quantum rasterizer for one-texel and minified pixels, while truly magnified
  pixels below the clamped one-texel footprint stay on nearest palette sampling;
  set it to `0` for faster raw sampling diagnostics. The bilinear path samples
  prepared surface texture and
  lightmap context directly so smoother diagnostic captures do not pay the old
  helper-call overhead per pixel. Normal world textures keep palette-index
  texels opaque and use the base Quake palette without a global fullbright
  boost; only fence/transparent surfaces use palette alpha as a cutout mask.
  For textures with a fullbright mask, palette indices at or above
  `QGE_SURFACE_FULLBRIGHT_INDEX` are removed from the lightmapped base sample
  and added back through the bounded `QGE_SURFACE_FULLBRIGHT_SCALE`, moving the
  wall-light contribution closer to the classic unlit additive fullbright pass
  without a separate QGE fullscreen pass.
  QGE world projection uses Quake's `r_refdef.fov_x` and `r_refdef.fov_y`
  separately, so floor and ceiling projection follows the classic viewport
  aspect instead of a square-FOV approximation.
  QGE world-surface shading uses the lower `QGE_SURFACE_TEXTURE_AMBIENT` and
  `QGE_SURFACE_LIGHT_AMBIENT` floors plus a wider
  `QGE_NO_FLOOR_TONE_WHITE_HEADROOM`, so dark floors, walls, and ceilings keep
  lightmap contrast without pushing side walls and ceilings as far above the
  classic reference. World-surface sampling also applies the bounded
  `QGE_SURFACE_WORLD_BLUE_BALANCE` to the blue channel because fixed-view QGE
  crops were consistently too blue against the classic reference. Texture
  signal cache entries also store per-texture palette means and contrast, and
  filtered BSP samples apply `QGE_SURFACE_TEXTURE_DETAIL_RESTORE` around those
  means after bilinear/prefilter sampling. The restore uses the smaller
  `QGE_SURFACE_TEXTURE_DETAIL_HIGHLIGHT_SCALE` for highlight-side deltas so
  wall and ceiling grooves recover detail without washing out the far floor.
  Render-gate display gain is derived from deterministic state marginals rather
  than finite-shot readout counts, so static floors, walls, and ceilings do not
  flicker just because `quantum_render_gate_shots` sampled a different basis
  distribution on the next frame.
  QGE render/snapshot diagnostic milestones are written to stderr instead of
  Quake notify text, so trace and ownership evidence remains in the stream logs
  without painting debug strings over captured floors, walls, or ceilings.
  Polygon raster fill uses a near-uniform world gain because the per-pixel
  texture and lightmap samples already carry local brightness; this reduces
  rectangular per-face exposure blocks on adjacent floors, walls, and ceilings.
  When audited QGE visibility authority replaces the classic PVS surface set,
  the frame snapshot clears its prior visible-surface entries before recording
  the authoritative set, preventing duplicate world panels from being rasterized
  as ghosted floor/wall/ceiling rectangles.
  Same-depth world samples use whole-sample luma ownership instead of additive
  accumulation or per-channel maxima, so coplanar seams and shared triangle
  edges do not brighten into synthetic translucent-looking wall or doorway
  panels. The depth tie window is the tight `QGE_SPATIAL_DEPTH_EPSILON`, so
  adjacent but distinct BSP faces keep normal nearest-surface ownership instead
  of bleeding through each other.
  After world rasterization, a bounded far-depth seam repair fills only
  background pixels surrounded by at least
  `QGE_SPATIAL_SEAM_REPAIR_MIN_NEIGHBORS` real world samples. Repaired pixels
  keep far depth, so the pass closes one-pixel floor/wall/ceiling coverage gaps
  without flooding into open background or occluding later entity/particle
  passes. Render logs expose the count as `gaprepair`.
  QGE also estimates the projected texture footprint for world-surface pixels
  and applies a bounded palette prefilter only when a floor, wall, or ceiling
  pixel is minified past `QGE_TEXTURE_PREFILTER_MIN_FOOTPRINT` texels.
  Moderate minification uses the nine-tap path; stronger minification uses a
  stratified 4x4 footprint grid so distant floors and ceilings do not alias into
  sparse crawl patterns. Magnified and near one-texel floors, walls, and
  ceilings stay on the bilinear path so they do not smear into broad bands, and
  the bounded texture-detail restore recovers some contrast lost by those
  filters without disabling anti-crawl sampling.
  Render logs expose those filtered samples as `texfilter`.
  For renderer triage without optional Python packages, compare fixed-view
  classic/QGE frames with
  `python3 tools/qge_world_frame_metrics.py --reference classic.png --candidate quantum.png`;
  it emits the dependency-free `qge.world_frame_metrics.v0` schema for single
  frames and `qge.world_frame_metrics.frames.v0` for frame directories or
  baseline-candidate comparisons. Frame-set reports also include reference,
  baseline, and candidate drift columns so fixed-view flicker is visible in the
  metrics artifact. The default regions keep the broad historical `world` crop
  and also split out `world_upper` plus the lower-center `viewmodel` band, so
  foreground weapon regressions cannot hide inside world-surface deltas.
  QGE world-surface projection clips very near geometry at
  `QGE_SURFACE_NEAR_CLIP_DEPTH` so walls or ceilings close to the camera do not
  explode into full-frame strips during autonomous captures.
  `SURF_DRAWTURB`/water polygons normalize both Quake's raw subdivided warp
  texture vectors and the already-scaled undivided water-poly coordinates before
  palette sampling, so water or slime surfaces do not become flat gray bands
  across floor/wall/ceiling captures.
  Before BSP surfaces are rasterized, the spatial framebuffer is initialized
  with a far-depth ambient world background using
  `QGE_SPATIAL_WORLD_BACKGROUND_R/G/B`; nearer world, entity, and particle
  samples still replace it through the depth buffer, but uncovered pixels no
  longer collapse into hard black voids when a close wall/floor/ceiling polygon
  is clipped or absent from the visible surface set.
  `QGE_RENDER_EDGE_SAMPLES=0` uses center-sampled triangle coverage in the
  quantum rasterizer for faster high-resolution captures; set it to `1` to
  restore subpixel edge coverage.
  `QGE_RENDER_DETAIL_MIX=1.0` preserves the pre-DWT RGB spatial raster and uses
  it as the final display signal after sparse DWT reconstruction runs. This
  keeps floor, wall, and ceiling texture detail from collapsing into sparse
  block bands while still running and logging the sparse DWT path. At the
  default full mix, display conversion uses the existing tone curve without the
  median-derived black floor that can crush darker texture samples to black, and
  leaves `QGE_NO_FLOOR_TONE_WHITE_HEADROOM` well above the sampled white point
  so bright floors and ceilings keep texture and stronger lightmap contrast
  instead of washing out to flat white; set it lower to inspect raw inverse-DWT
  contribution.
  When a first-person viewmodel is encoded, direct-display tone mapping builds
  its brightness histogram from only the upper
  `QGE_TONE_HISTOGRAM_WORLD_Y_PERCENT` percent of the frame. The full frame is
  still converted and displayed, but the lower weapon/HUD band no longer pushes
  the world white point down and leaves floors, walls, and ceilings too dark.
  `QGE_RENDER_DISPLAY_FILTER=0` skips neighbor smoothing during display-buffer
  conversion because live captures showed the smoothed display can over-blur the
  whole world frame; set it to `1` for noisy-capture experiments.
  `QGE_RENDER_UPDATE_INTERVAL=1` updates the full QGE frame every host frame so
  floors, walls, ceilings, entities, and the viewmodel move with the camera.
  Higher values deliberately reuse the last texture between updates for
  profiling; values above `16` are clamped.
  Alias-model mesh encoding also covers the first-person viewmodel with
  `QGE_MAX_ALIAS_VIEWMODEL_TRIS`, replacing the old synthetic center-line
  viewmodel glyph when alias mesh metadata is available. The QGE alias path now
  projects Quake alias-model skin texels and bilinear-samples `hdr->texels` for
  the first-person weapon mesh. First-person aliases use a separate bounded
  `QGE_ALIAS_VIEWMODEL_BRIGHTNESS`, `QGE_ALIAS_VIEWMODEL_SHADE_GAIN`, and
  `QGE_ALIAS_VIEWMODEL_SHADE_MIN` (`0.19`, `1.05`, and `0.14` in the current
  renderer) plus a viewmodel-only alias-normal shade, edge scale, and edge cadence
  (`QGE_ALIAS_VIEWMODEL_NORMAL_SHADE_BASE 0.78f` and
  `QGE_ALIAS_VIEWMODEL_EDGE_STRIDE_MASK 127` in the current renderer) so
  foreground weapon lighting and diagnostic edge density can be
  tuned without changing ordinary alias entities. Classic weapon placement and
  material parity remain separate renderer gaps.
  `QGE_RENDER_RES` and `QGE_RENDER_THRESHOLD` are also passed as early
  `-qgerenderres` / `-qgerenderthreshold` launch arguments so DWT buffers are
  allocated at the requested size before `autoexec.cfg` runs.
- `QGE_PHYSICS`, `QGE_PROJECTILES`, `QGE_PARTICLES`: QGE simulation toggles.
- `QGE_SCENE_SURFACE_BUDGET`: QGE scene surface budget, default `512`.
  This is independent of `QGE_RENDER_RES`. The higher default avoids striding
  across dense visible BSP sets, which otherwise leaves missing floor, wall, and
  ceiling spans; lowering it improves CPU cost at the expense of world coverage.
- `QGE_STREAM_ACTIVATE`: macOS `open` mode foreground activation, default `0`.
  Set to `1` only when the local window manager requires the app to be brought
  foreground for capture.
- `QGE_STREAM_ACTIVATE_ATTEMPTS`: number of activation attempts after the
  harnessed app process appears, default `8`.
