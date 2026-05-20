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
records. Set either minimum to `0` only when intentionally testing a shorter
input or capture path.

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
  mode, target visibility/distance, aim yaw/pitch, steering
  commands, and wall-probe distances.
- `logs/quantum_quake.log`: runtime console log mirrored into the stream.
- `logs/open.log`: LaunchServices notes for macOS `open` mode.
- `trace/qge_trace_summary.json`: JSON summary of `qge_trace.bin`, including
  `runtime_evidence.single_trace_ready` and per-domain AI, audio, visibility,
  and projectile evidence counts. Visibility readiness requires an applied
  `vis_authority_apply` record, not only shadow/gate telemetry. Projectile
  evidence includes `save_demo_boundary_count` and per-kind save/demo counts
  for writeback, branch, and collision-oracle persistence boundaries.
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
  inverse-DWT path.
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
QGE field is regenerated. The default interval is `8`, which reuses the last
QGE texture between updates while still drawing at the requested resolution.
Skipped frames also avoid collecting world surfaces for the QGE encoder. Set
`QGE_RENDER_UPDATE_INTERVAL=1` for strict every-frame profiling.

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
traces prove both the selected backend and the teardown path.
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
bundle also opts the launcher window out of AppKit state restoration. The
harness passes `-nomouse` by default so SDL does not enter relative mouse mode
or warp/capture the user cursor. It lets SDL choose the display by default;
set `QGE_STREAM_DISPLAY` only when a specific display index is required. Set
`QGE_STREAM_ACTIVATE=1` only if the local window manager requires a foreground
app for capture. A side watcher tails `qconsole.log`, mirrors screenshots, and
refreshes audio byte counts while the app is still running. After the run, the
harness archives the log into the capture and agent-stream directories and
removes the root `qconsole.log` copy so generated runtime output does not
pollute source-drift checks.
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
`QGE_NOESIS_START_WAIT + 4`, so short smoke runs still capture after the policy
provider has started emitting actions. An explicit `QGE_STREAM_CAPTURE_WAIT`
continues to mean exactly the frame requested.

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
require numpy and Pillow; if either dependency is unavailable, the harness exits
before starting the app.
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
evidence-only instead of `qge_publication_artifact_pack_complete`.
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
Publication packs copy capture and vanilla-matrix performance sidecars into the
pack, expose direct and per-mode max average/render timing fields in the
publication runtime summary and ICC evidence, and treat an explicit blocked
performance sidecar as evidence-only rather than
`qge_publication_artifact_pack_complete`.

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
an enemy is not enough. The gameplay score discounts attack-press credit when
attack frames are blind or visible-but-unaligned, and applies a small combat
penalty when observed ammo spend is unproductive. Route telemetry also reports
movement efficiency, stationary fraction, maximum stationary run, and
duration-aware terminal-stall evidence, so a route that moves early and ends
wedged cannot pass as clean progress while a short post-plan idle tail does not
poison a long successful route. Assist runs additionally emit requested mode, active sample count,
visible-target sample count, steering sample count, attack-visible frames,
target-distance evidence, and a claim scope. Assisted runs are marked `server_assisted` so they cannot be
mistaken for unassisted play evidence. Set `QGE_NOESIS_MIN_LOG_PHASES` to
require that many `QGE_NOESIS_PHASE` markers to appear in the engine log and
matching engine-owned `noesis_phase` outcome events to appear in gameplay
telemetry, which is useful when proving that a longer route plan actually
executed rather than only being generated. Set `QGE_NOESIS_MIN_GAMEPLAY_SAMPLES` and
`QGE_NOESIS_MIN_ROUTE_DISTANCE` to require engine-owned state samples and route
movement evidence. This reducer is evidence-only: a blocked Noesis quality
summary does not turn a completed media stream into a process failure.

`tools/quake_crash_watch.sh` uses the same Noesis player/provider contract for
its scripted movement by default, stores `input/noesis_actions.txt` and
`input/noesis_commands.cfg` under its crash-watch output directory, passes
`-nomouse` unless `QGE_STREAM_MOUSE=1`, targets `QGE_STREAM_DISPLAY` like the
stream harness, and pins the same high-resolution CPU render defaults: 1024
internal render resolution, no bilinear/edge/display smoothing, and
`QGE_RENDER_UPDATE_INTERVAL=8` unless overridden. The crash watcher records
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
The E1M1 adaptive route brackets its first scan-fire block with a short
keyboard `look-up` and `center-view` recenter so attacks sweep a more useful
enemy sightline without taking over the user's mouse. After the door bump it
adds a short keyboard speed-jump-forward recovery to reduce door-phase stalls.
Generic combat-exploration recovery backs out, side-slides, turns, and jumps
forward before the second push so a terminal wall contact is less likely to
leave the plan wedged.

Action streams can come from either `QGE_NOESIS_ACTIONS_FILE` or
`QGE_NOESIS_CMD`. The command provider runs from `QGE_NOESIS_DIR` and should
print the same action lines to stdout; this is the hook for a Noesis policy
runtime that writes actions instead of capturing the user's mouse. The provider
is executed directly, so use a small wrapper script for shell pipelines,
redirection, or other compound commands.
Every run also mirrors the selected action stream and translated Quake command
stream into `input/noesis_actions.txt` and `input/noesis_commands.cfg`.

When neither is set, the default Noesis player runs
`tools/noesis_quake_policy.sh`, a repo-local cached-policy provider. It emits a
`QGE_NOESIS_POLICY` marker into the Quake log, then writes action lines for the
selected plan. `QGE_NOESIS_ACTIONS_FILE` still takes precedence over this
default provider, and an explicit `QGE_NOESIS_CMD` takes precedence over both.

## Common Environment Variables

- `QGE_AGENT_STREAM_DIR`: override the agent stream output directory.
- `QGE_STREAM_MAP`: map to load, default `start`.
- `QGE_STREAM_FRAMES`: number of screenshots requested, default `12`.
- `QGE_STREAM_WAIT_FRAMES`: default engine capture wait, default `20`.
- `QGE_STREAM_CAPTURE_WAIT`: explicit engine capture frame.
- `QGE_STREAM_TIMEOUT_SECONDS`: explicit launch/watchdog timeout.
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
  `QGE_NOESIS_PLAN` is set explicitly.
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
- `QGE_STREAM_PLAYER`: scripted input owner, default `noesis`. Set to `none`
  to disable harness-generated gameplay commands.
- `QGE_NOESIS_DIR`: Noesis repo path used for player provenance, default
  `~/Desktop/noesis`.
- `QGE_NOESIS_PLAN`: Noesis command-buffer plan, default `adaptive`;
  supported plans are `patrol`, `scout`, `fire`, `map-scout`, `combat-scout`,
  `combat-explore`, `e1m1-route-push`, `weapon-cycle-smoke`, and `adaptive`.
  `adaptive` selects a map-aware route/combat plan when one exists, and
  otherwise falls back to the generic combat-exploration loop.
- `QGE_NOESIS_ACTIONS_FILE`: optional Noesis action file. When present, the
  harness translates each line into Quake console commands instead of using
  the built-in plan. Supported actions include `forward`, `back`,
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
- `QGE_NOESIS_ASSIST`: opt-in server-state assist for Noesis automation,
  default `0`. Mode `1` aims and fires at visible monsters while preserving the
  scripted movement command. Mode `2` also steers the server usercmd toward the
  nearest monster with a small wall-avoidance probe and kites visible close
  targets instead of walking into them. Visibility and aim use a sampled monster
  bbox point, so partly exposed enemies are not limited to a center-point trace.
  The engine-side cvar is `qge_noesis_assist`, remains off by default, and only
  acts during `-qgestreamdir` runs so normal local play is untouched.
- `QGE_NOESIS_CMD`: optional Noesis action provider command. When set, the
  harness runs it from `QGE_NOESIS_DIR` and translates its stdout action lines;
  this takes precedence over `QGE_NOESIS_ACTIONS_FILE` and the default
  `tools/noesis_quake_policy.sh` provider.
- `QGE_STREAM_WIDTH`, `QGE_STREAM_HEIGHT`, `QGE_STREAM_FULLSCREEN`: window
  controls.
- `QGE_RENDER`, `QGE_RENDER_RES`, `QGE_RENDER_THRESHOLD`,
  `QGE_RENDER_EDGE_GAIN`, `QGE_RENDER_MATERIAL_GAIN`,
  `QGE_RENDER_BILINEAR_SAMPLES`, `QGE_RENDER_EDGE_SAMPLES`,
  `QGE_RENDER_DISPLAY_FILTER`, `QGE_RENDER_UPDATE_INTERVAL`: QGE render
  controls.
  `QGE_RENDER_BILINEAR_SAMPLES=0` uses nearest texture/light samples in the
  quantum rasterizer for faster CPU-only captures; set it to `1` for smoother
  per-pixel sampling.
  `QGE_RENDER_EDGE_SAMPLES=0` uses center-sampled triangle coverage in the
  quantum rasterizer for faster high-resolution captures; set it to `1` to
  restore subpixel edge coverage.
  `QGE_RENDER_DISPLAY_FILTER=0` skips neighbor smoothing during display-buffer
  conversion for faster high-resolution CPU captures; set it to `1` to restore
  the smoothed display filter.
  `QGE_RENDER_UPDATE_INTERVAL=8` updates the full QGE frame every eighth host
  frame and reuses the last texture between updates; set it to `1` to update
  every frame. Values above `16` are clamped.
  `QGE_RENDER_RES` and `QGE_RENDER_THRESHOLD` are also passed as early
  `-qgerenderres` / `-qgerenderthreshold` launch arguments so DWT buffers are
  allocated at the requested size before `autoexec.cfg` runs.
- `QGE_PHYSICS`, `QGE_PROJECTILES`, `QGE_PARTICLES`: QGE simulation toggles.
- `QGE_SCENE_SURFACE_BUDGET`: QGE scene surface budget, default `128`.
  This is independent of `QGE_RENDER_RES`; raising it improves surface coverage
  but increases CPU raster and sparse-DWT cost.
- `QGE_STREAM_ACTIVATE`: macOS `open` mode foreground activation, default `0`.
  Set to `1` only when the local window manager requires the app to be brought
  foreground for capture.
- `QGE_STREAM_ACTIVATE_ATTEMPTS`: number of activation attempts after the
  harnessed app process appears, default `8`.
