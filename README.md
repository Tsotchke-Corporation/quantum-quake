# Quantum Quake

Quantum Quake is the QuakeSpasm-based conformance title for QGE, the
Moonlab-backed Quantum Game Engine layer. The current repository is centered on
the C engine, QGE runtime hooks, diagnostics harnesses, Noesis gameplay
automation, and ICC evidence used to move individual game domains from shadow
telemetry toward bounded authority.

The `master` branch is the primary development branch for this codebase.
`origin/HEAD` resolves to `origin/master`, and `origin/main` is kept
fast-forwarded to the same commit for compatibility after the older unrelated
Three.js/WebTransport history was merged as provenance. The authoritative tree
is the `master` QGE/QuakeSpasm layout documented here.

Latest verified runtime baseline: the current QGE world fullbright sampling
slice plus diagnostic notify cleanup, mirrored to both `origin/master` and
`origin/main`.

## Current Status

This is an active research and systems-engineering project, not a finished
player-facing Quake distribution.

Working and routinely verified:

- Moonlab-backed QGE core runtime, trace, RNG, AI, render, visibility, audio,
  physics, and world snapshot libraries.
- A macOS QuakeSpasm application build with QGE hooks and cvars.
- Sparse DWT QGE primary rendering with world-surface, material, lightmap,
  entity, HUD/console ownership telemetry, native IDWT evidence, and explicit
  fallback reasons. The current graphics baseline updates the QGE primary
  render every host frame by default, seeds a far-depth ambient world
  background for missing world pixels, normalizes warp/water texture
  coordinates before palette sampling, uses the base Quake palette for ordinary
  world texture indices, splits world fullbright texels into an unlit additive
  contribution, keeps first-person weapon geometry out of the world tone
  histogram, and derives render-gate display gain from deterministic state
  marginals instead of finite-shot readout counts.
- QGE visibility shadow/parity paths with audited authority-gate telemetry.
- QGE projectile shadow/writeback/collision-oracle evidence paths with replay
  and persistence-boundary trace records.
- QGE audio post-mix and source-mode telemetry, including source authority
  smoke checks.
- Noesis harness play on `e1m1` with no-script autonomous server control by
  default, opt-in keyboard-style action-plan fixtures for regression tests,
  engine-side assist telemetry, route/combat outcome summaries, stale hidden
  target cooldowns, local wall/floor/hazard probes when no target is engaged,
  and ICC evidence sidecars.
- Reproducible diagnostic streams under `diagnostics/agent_stream/` and
  `diagnostics/quake_stream/`.

Important known limitations:

- `quantum_render 2` is not visually complete. The current renderer has
  improved world-surface coverage, Quake-FOV world projection, bilinear
  surface/light sampling, darker lightmap-preserving surface shading, and
  preserved spatial detail for the final display while still running the sparse
  DWT path for evidence. QGE now refreshes every host frame by default and
  removes finite-shot render-gate shimmer from static floors, walls, and
  ceilings, and no longer globally boosts high palette indices into noisy
  floor speckles. Remaining issues are now more clearly projection/material
  problems: residual tone mismatch, raster seams, warp/water seams, fullbright
  material fidelity, viewmodel fidelity, and incomplete vanilla-material
  fidelity.
- Noesis is not yet learning Quake from experience and does not yet have a
  map-level world model. Current no-script runs use a reactive server-side
  controller with an explicit autonomous assist hint, target feedback,
  wall-contact heuristics, and local floor/hazard probes; scripted route
  fixtures are opt-in regression tools, not the default gameplay path.
- QGE is not yet the sole owner of all vanilla Quake media. Sky, water/warp,
  full conformance lighting, particles, sprites, menus, and all edge cases are
  still in progress.
- Practical quantum hardware advantage is not a current claim. Supported
  claims are limited to bounded simulated-QPU observables, scene-oracle IR, and
  explicitly scoped query/sample-complexity experiments.
- Live graphics harnesses launch a local Quake app. Safe runs used by agents
  set `QGE_STREAM_MOUSE=0` and `QGE_STREAM_ACTIVATE=0` unless a human is
  intentionally testing interactivity.

## Current Renderer Evidence

The current QGE graphics baseline is improved but still visibly glitchy. The
latest fixed-view evidence is
`diagnostics/quake_stream/20260521-164816/frame_001.png`. That run keeps QGE
ownership of world geometry, world textures, lightmaps, HUD/console, and the
viewmodel with `emesh=58`, `ecoeff=27`, `own_viewmodel=1`,
`own_console=1`, and `fallback_reason=none` on captured frames. It also keeps
QGE render/snapshot milestones in the logs instead of painting them as Quake
notify text over the world. Against the classic `20260521-151552` reference,
the previous world-tone capture
`20260521-153315` moved the front-wall mean-luminance delta from about `-19.73`
to `-0.92`, side-wall deltas from about `-9.64/-11.01` to `+3.08/+2.65`,
ceiling delta from about `-11.51` to `+2.19`, and far-floor delta from about
`-12.88` to `+4.75`. The follow-up fullbright split keeps those normal
floor/wall/ceiling regions unchanged while moving the two sampled wall-light
regions from about `-37.42/-28.70` below classic to about `-19.83/-12.57`.

What is still broken is just as important: light-emissive regions are closer but
still too dim, nearby floors are slightly over-lifted, raster seams remain visible,
turbulent water/warp materials are not vanilla-quality, and the viewmodel is
still an untextured QGE mesh rather than a faithful classic weapon material.
Treat the renderer as a diagnostic primary path with useful ownership telemetry,
not as a finished replacement for classic Quake rendering.

## Quick Start

Build and run the core test binary:

```sh
make test_qge
./bin/test_qge
```

Run the full contract suite:

```sh
make test
```

Build the macOS app bundle:

```sh
make quake
```

Run a compact fixed-view QGE graphics diagnostic:

```sh
QGE_STREAM_LAUNCH=open QGE_STREAM_MOUSE=0 QGE_STREAM_ACTIVATE=0 \
QGE_STREAM_TRACE=1 QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=1 \
QGE_STREAM_WAIT_FRAMES=12 QGE_STREAM_PLAYER=none QGE_RENDER=2 \
QGE_RENDER_UPDATE_INTERVAL=1 QGE_STREAM_SOUND=0 \
bash tools/quake_graphics_stream.sh
```

`QGE_RENDER_UPDATE_INTERVAL=1` is the default, but it is left in this command
to make fixed-view graphics evidence explicit. On macOS, `QGE_STREAM_LAUNCH=open`
is the validated safe path for app-bundle GL context startup; direct launch is
kept for lower-level diagnostics.

Run a harnessed Noesis gameplay smoke:

```sh
QGE_STREAM_LAUNCH=open QGE_STREAM_MOUSE=0 QGE_STREAM_ACTIVATE=0 \
QGE_STREAM_TRACE=1 QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=3 \
QGE_STREAM_WAIT_FRAMES=12 QGE_STREAM_PLAYER=noesis QGE_RENDER=2 \
QGE_RENDER_UPDATE_INTERVAL=1 QGE_STREAM_SOUND=0 \
bash tools/quake_graphics_stream.sh
```

## Repository Layout

- `qge/`: reusable QGE runtime libraries.
- `quake/Quake/`: QuakeSpasm engine with QGE integration hooks.
- `deps/moonlab/`: Moonlab quantum simulation/runtime dependency.
- `tools/`: diagnostics, stream, publication, Noesis, trace, and benchmark
  helpers.
- `tests/`: C, shell, and Python contract tests.
- `docs/`: architecture, stream, claims, roadmap, and development-state docs.
- `diagnostics/`: generated local run artifacts. These are evidence inputs, not
  source.
- `.icc/`: ICC policy/configuration used for drift, audit, and task evidence.

## Documentation Map

Start with [docs/README.md](docs/README.md) for the curated documentation map.
The authoritative current-state snapshot is
[docs/qge_state_of_development.md](docs/qge_state_of_development.md); it covers
branch consolidation, verified runtime surfaces, known visual/gameplay gaps,
Noesis no-script reality, and the evidence baseline. The most useful current
documents are:

- [QGE state of development](docs/qge_state_of_development.md)
- [QGE engine architecture](docs/qge_engine_architecture.md)
- [QGE agent media stream](docs/qge_agent_stream.md)
- [QGE claims ledger](docs/qge_claims_ledger.md)
- [Quantum Quake full architecture plan](docs/quantum_quake_full_architecture_plan.md)

## Evidence Standard

Project claims should be backed by executable tests, traces, screenshots,
metrics, and ICC attempts. Prose-only claims are intentionally treated as
unsupported. When changing runtime behavior, prefer a narrow patch with:

- focused contract tests,
- `make test_qge` and `./bin/test_qge` for C/QGE changes,
- `make test` for broader integration changes,
- a safe harnessed stream when changing live graphics or Noesis gameplay,
- ICC source-drift, production-audit, task-attempt, and attempt-eval records
  before pushing a verified slice.
