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

Run the scripted weapon smoke and capture before the script exits:

```sh
QGE_STREAM_MAP=e1m1 QGE_STREAM_FIRE_TEST=1 QGE_STREAM_CAPTURE_WAIT=20 \
  QGE_STREAM_FRAMES=1 QGE_STREAM_WAIT_FRAMES=30 QGE_STREAM_TRACE=1 \
  bash tools/quake_graphics_stream.sh
```

## Stream Contract

The stream directory is intentionally simple and tail-friendly:

- `manifest.json`: rewritten whenever stream state changes. It records the
  capture path, map, render settings, trace path, and current audio/video/log
  locations.
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
- `logs/quantum_quake.log`: runtime console log mirrored into the stream.
- `logs/open.log`: LaunchServices notes for macOS `open` mode.
- `qge_agent_stream_icc_evidence.jsonl`: ICC-native evidence entries for the
  manifest, events file, latest video frame, raw audio, audio metadata, and
  completion signal.

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
- `convert`: tone mapping and RGB display-buffer conversion.
- `blit`: OpenGL texture upload and screen draw.

`quantum_render_update_interval` controls how often the expensive 1024-frame
QGE field is regenerated. The default interval is `8`, which reuses the last
QGE texture between updates while still drawing at the requested resolution.
Skipped frames also avoid collecting world surfaces for the QGE encoder. Set
`QGE_RENDER_UPDATE_INTERVAL=1` for strict every-frame profiling.

For CPU-only profiling, keep `QGE_RENDER_RES` fixed and compare these fields
across runs. A slow 1024 run is usually dominated by `raster`, not by the
LaunchServices wrapper.

## Launch Modes

`QGE_STREAM_LAUNCH=auto` is the default. On macOS it selects `open`; on other
platforms it selects direct binary execution.

In macOS `open` mode, the harness uses `open -W -n -F` plus the app's
`-nolauncher` argument: it waits for the app, starts a new instance, bypasses
the click-through launcher window, and asks LaunchServices to ignore restored
window state, and does not require a manual click. It also passes `-nomouse`
by default so SDL does not enter relative mouse mode or warp/capture the user
cursor. Set `QGE_STREAM_ACTIVATE=1` only if the local window manager requires a
foreground app for capture. A side watcher tails `qconsole.log`, mirrors
screenshots, and refreshes audio byte counts while the app is still running.

Use `QGE_STREAM_LAUNCH=direct` when running the app binary directly is more
reliable in the local environment. Direct mode redirects the runtime log through
the harness process instead of reading `qconsole.log`.

## Capture Timing

Engine auto-capture is enabled by default with `QGE_STREAM_ENGINE_CAPTURE=1`.
The screenshot frame defaults to `QGE_STREAM_WAIT_FRAMES`.

Some action scripts execute fewer rendered frames than their command-buffer wait
count suggests. For those runs, set `QGE_STREAM_CAPTURE_WAIT=<frames>` to choose
the engine screenshot frame explicitly. When `QGE_STREAM_FIRE_TEST=1` and no
override is provided, the harness captures at roughly two-thirds of
`QGE_STREAM_WAIT_FRAMES`, with a floor that falls back to the normal wait for
very small values.

Set `QGE_STREAM_ENGINE_CAPTURE=0` to use scripted `screenshot png` commands
instead of engine auto-capture. This mode still mirrors discovered `spasm*.png`
files into the agent stream.

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
with status `complete`, `events.ndjson` receives `stream_done`, and the frame and
audio pointer files remain present for consumers that expect a stable contract.

## Noesis Action Files

`tools/noesis_quake_player.sh` translates a small line-oriented action stream
into Quake console commands. Blank lines and `#` comments are ignored. Each
action accepts an optional wait-count argument, so `forward 12` emits
`+forward`, twelve `wait` commands, then `-forward`.

Example:

```text
forward 12
turn-right 6
attack 4
wait 2
```

Supported movement/action verbs are `forward`, `back`, `turn-left`,
`turn-right`, `strafe-left`, `strafe-right`, `attack`, `wait`, `weapon`, and
`give`. `cmd` or `quake` passes the remaining text through as a raw Quake
console command for targeted probes.

Action streams can come from either `QGE_NOESIS_ACTIONS_FILE` or
`QGE_NOESIS_CMD`. The command provider runs from `QGE_NOESIS_DIR` and should
print the same action lines to stdout; this is the hook for a Noesis policy
runtime that writes actions instead of capturing the user's mouse.

## Common Environment Variables

- `QGE_AGENT_STREAM_DIR`: override the agent stream output directory.
- `QGE_STREAM_MAP`: map to load, default `start`.
- `QGE_STREAM_FRAMES`: number of screenshots requested, default `12`.
- `QGE_STREAM_WAIT_FRAMES`: default engine capture wait, default `20`.
- `QGE_STREAM_CAPTURE_WAIT`: explicit engine capture frame.
- `QGE_STREAM_TRACE`: write `qge_trace.bin` when set to `1`.
- `QGE_STREAM_SOUND`: run with game sound enabled when set to `1`.
- `QGE_STREAM_FIRE_TEST`: run the scripted weapon smoke when set to `1`.
  With the default Noesis player this selects the Noesis `fire` plan unless
  `QGE_NOESIS_PLAN` is set explicitly.
- `QGE_STREAM_ENGINE_CAPTURE`: use engine auto-capture when set to `1`, default
  `1`.
- `QGE_STREAM_LAUNCH`: `auto`, `open`, or `direct`.
- `QGE_STREAM_MOUSE`: pass through SDL mouse input when set to `1`. The default
  is `0`, which launches Quake with `-nomouse` so the harness never captures
  the user's cursor.
- `QGE_STREAM_PLAYER`: scripted input owner, default `noesis`. Set to `none`
  to disable harness-generated gameplay commands.
- `QGE_NOESIS_DIR`: Noesis repo path used for player provenance, default
  `~/Desktop/noesis`.
- `QGE_NOESIS_PLAN`: Noesis command-buffer plan, default `patrol`; supported
  plans are `patrol`, `scout`, and `fire`.
- `QGE_NOESIS_ACTIONS_FILE`: optional Noesis action file. When present, the
  harness translates each line into Quake console commands instead of using
  the built-in plan. Supported actions include `forward`, `back`,
  `turn-left`, `turn-right`, `strafe-left`, `strafe-right`, `attack`, `wait`,
  `weapon`, and `give`, with an optional wait-count argument.
- `QGE_NOESIS_START_WAIT`: command-buffer waits emitted before Noesis actions,
  default `16`. Set to `0` when the action file already includes its own
  startup delay.
- `QGE_NOESIS_CMD`: optional Noesis action provider command. When set, the
  harness runs it from `QGE_NOESIS_DIR` and translates its stdout action lines;
  this takes precedence over `QGE_NOESIS_ACTIONS_FILE`.
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
