# Quantum Quake

Quantum Quake is the QuakeSpasm-based conformance title for QGE, the
Moonlab-backed Quantum Game Engine layer. The project target is unambiguous:
the entire game should run under QGE/Moonlab authority. QuakeSpasm may remain
as host, compatibility shell, content loader, and classic reference oracle, but
it must not be hidden production authority for domains claimed as Moonlab-owned.
The current repository is centered on the C engine, QGE runtime hooks,
diagnostics harnesses, Noesis gameplay automation, and ICC evidence used to
move individual game domains from shadow telemetry toward bounded authority.

The `master` branch is the primary development branch for this codebase.
`origin/HEAD` resolves to `origin/master`, and `origin/main` is kept
fast-forwarded to the same commit for compatibility after the older unrelated
Three.js/WebTransport history was merged as provenance. The authoritative tree
is the `master` QGE/QuakeSpasm layout documented here.

Latest verified runtime baseline: the current QGE world texture-detail restore,
world-surface blue balance, one-texel bilinear world texture smoothing,
moderate-minification texture prefilter, alias-skin viewmodel path, world fullbright sampling scale,
and diagnostic notify cleanup, mirrored to both `origin/master` and
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
  world texture indices, splits world fullbright texels into a bounded unlit
  additive contribution, applies a bounded footprint prefilter to moderately
  minified world texels, moves one-texel wall/ceiling samples onto the bilinear
  palette path to reduce crawl, applies a bounded world-surface blue balance
  against the classic fixed-view reference, restores a bounded amount of
  texture detail around per-texture palette means, samples alias-model skin
  texels for the first-person weapon mesh, keeps first-person weapon geometry
  out of the world tone histogram, and derives render-gate display gain from
  deterministic state marginals instead of finite-shot readout counts.
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

- The full-port ICC target is `qge_vanilla_quake_conformance`. The current
  strongest self-contained evidence pack is
  `diagnostics/publication_pack/20260523-160950`, where ICC reports the strict
  vanilla/QGE runtime ownership matrix and `qge_vanilla_runtime_complete`
  ready. The pack includes `resource/qge_resource_envelope.json`, which scopes
  Moonlab simulator/native-backend deployment,
  `resource/qge_full_game_map_coverage.json`, which records partial canonical
  map coverage at 9/32 maps with 23 maps pending,
  `resource/qge_asset_inventory.json`, which records the PAK/BSP availability
  blocker, plus
  `resource/qge_native_backend_boundary.json` with the pass/fail proof for the
  three native backend boundaries,
  `resource/qge_moonlab_job_specs.json` with selected simulator/native replay
  jobs and one unsubmitted hardware-candidate QAE benchmark job, and
  `resource/qge_moonlab_job_results.json` with four completed simulator jobs,
  two completed native replay jobs, zero blocked jobs, and zero hardware
  submissions, plus `resource/qge_moonlab_replay_plan.json` with the exact
  replay/validation contract. `tools/qge_moonlab_job_runner.py` can regenerate
  those results directly from the job specs, compare them against the packed
  expected results, and emit a replay plan. The pack explicitly does not claim whole-game
  hardware execution, hardware quantum advantage, or a dense 70,000-qubit
  state. This is a captured workload proof, not a claim that every Quake domain
  is visually or hardware complete. Use
  `tools/qge_full_game_capture_queue.py diagnostics/publication_pack/20260523-160950`
  to generate the remaining harness queue and breadth rebuild script; the queue
  inventories loose/Pak BSP assets, skips missing local BSPs unless
  `--include-unavailable-assets` is set, and currently reports zero locally
  queueable missing maps while 23 registered maps require additional registered
  BSP assets before capture. `tools/qge_asset_inventory.py` emits the companion
  hash-backed asset audit; the current local inventory is one `pak0.pak`
  containing 9/32 canonical maps.
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
- Fixed-view renderer comparisons no longer depend solely on optional
  numpy/Pillow tooling. `tools/qge_world_frame_metrics.py` uses only the Python
  standard library to score floor, wall, ceiling, corridor, upper-playfield,
  and viewmodel PNG crops. It also averages frame directories and can compare a
  new QGE run against a baseline candidate for per-region deltas and
  frame-to-frame drift; the paired graphics harness falls back to it
  automatically. The paired harness freezes lightstyle animation by default for
  reproducible fixed-view scoring.

## Current Renderer Evidence

The current QGE graphics baseline is improved but still visibly glitchy. The
latest fixed-view frame-set evidence is
`diagnostics/quake_graphics/20260522-164822/metrics.md`. That run keeps QGE
ownership of world geometry, world textures, lightmaps, HUD/console, and the
viewmodel with `own_world=1`, `own_textures=1`, `own_lightmaps=1`,
`own_viewmodel=1`, `own_console=1`, and `fallback_reason=none` on captured
frames. It also keeps QGE render/snapshot milestones in the logs instead of
painting them as Quake notify text over the world. Against the classic
`20260521-151552` reference,
the previous world-tone capture
`20260521-153315` moved the front-wall mean-luminance delta from about `-19.73`
to `-0.92`, side-wall deltas from about `-9.64/-11.01` to `+3.08/+2.65`,
ceiling delta from about `-11.51` to `+2.19`, and far-floor delta from about
`-12.88` to `+4.75`. The follow-up fullbright work keeps normal
floor/wall/ceiling regions effectively unchanged while moving sampled wall-light
crops closer to classic; the latest fixed-view run improves whole-frame RMSE
against the classic reference from `0.0457305` to `0.0452656`. The alias-skin
viewmodel follow-up leaves the fixed-view world crops unchanged while replacing
the flat gold weapon mesh with skin-sampled alias triangles and improves
whole-frame RMSE again to `0.0349406`. The moderate-minification prefilter
follow-up raises filtered world-texel coverage to roughly `193k` samples,
reduces the mid-floor blur-difference metric from `0.00841979` to
`0.00792546`, and improves whole-frame RMSE again to `0.0343281`. The
one-texel bilinear follow-up targets the remaining wall/ceiling crawl: in the
`20260521-180918` fixed-view capture, ceiling blur-difference drops from
`0.00469063` to `0.00234635`, left/right wall drops from
`0.00347071`/`0.00373587` to `0.00172187`/`0.00203961`, and front-wall drops
from `0.0027016` to `0.00168355`. Whole-frame RMSE is mixed across the three
captured frames (`0.0341756` on frame 2, `0.0347847` on frames 1/3), so this is
a targeted wall/ceiling stability improvement rather than a complete renderer
conformance win. The world-surface blue-balance follow-up at
`20260521-183949` reduces blue lift in floor, ceiling, and front-wall crops and
improves the fixed-view whole-frame RMSE again to `0.0340944`; it is still a
bounded color-conformance step, not a complete material or lighting fix. The
texture-detail follow-up at `20260521-190448` restores a conservative amount of
palette texture contrast after bilinear/prefilter sampling: whole-frame RMSE
improves to `0.0339437`, world high-frequency texture energy rises from `88.8%`
to `92.8%` of the classic reference, and the ceiling/side-wall/front-wall
high-frequency ratios improve from `75.2%`/`70.3%`/`78.8%`/`65.1%` to
`80.7%`/`74.8%`/`82.9%`/`69.3%`. The deterministic display-contrast follow-up
at `20260522-034256` applies a bounded luma contrast after QGE tone mapping:
against the flat-lightstyle `20260522-031254` baseline, ceiling, left/right
wall, front-wall, center-floor, near-floor, and mid-corridor crop RMSE all
improve, with the largest deltas on center floor (`-0.011806`) and mid corridor
(`-0.014200`). Candidate drift remains `0.000000`; the broad world crop RMSE
increases by `+0.003629` because the output now preserves more visible
texture/edge energy and the broad crop includes the first-person weapon band.
The follow-up crop audit separates that signal: `world_upper` improves by
`-0.007318` RMSE while the `viewmodel` crop regresses by `+0.034692`, making
the next renderer target explicit. The bounded viewmodel-lighting follow-up at
`20260522-115852` gives the first-person alias path its own brightness and
shade floor: against `20260522-034256`, the `viewmodel` crop RMSE drops from
`0.161956` to `0.094513`, `viewmodel_core` drops from `0.279478` to
`0.163137`, and the broad `world` crop improves by `-0.012916`. Some named
world crops move by roughly `+0.001` to `+0.002` through global DWT
reconstruction coupling, so this is a targeted viewmodel lighting improvement,
not a complete weapon/material fix. The second bounded pass at `20260522-121419`
lowers the same viewmodel-only constants again: against `20260522-115852`,
`viewmodel` RMSE drops from `0.094513` to `0.072401`, the broad `world` crop
improves by `-0.003998`, and cumulative comparison against `20260522-034256`
puts `viewmodel_core` at `0.124881` RMSE. Candidate drift remains `0.000000`.
The alias-normal viewmodel follow-up at `20260522-124349` preserves the same
world-only crops while shaping first-person alias fill with `lightnormalindex`
and reducing first-person edge intensity: against `20260522-121419`,
`viewmodel` RMSE drops from `0.072401` to `0.044634`, `viewmodel_core` drops
from `0.092357` to `0.056752`, and `viewmodel_core` luma is nearly matched
(`0.104936` candidate versus `0.104856` classic). Candidate drift remains
`0.000000`. The first-person edge-cadence follow-up at `20260522-134809`
preserves the named world-only crops while reducing viewmodel diagnostic edge
over-detail: against `20260522-124349`, `viewmodel` RMSE drops from
`0.044634` to `0.041117`, `viewmodel_core` drops from `0.056752` to
`0.052033`, and viewmodel high-frequency ratio drops from `2.710` to `2.457`.
The sparser edge-cadence/fill follow-up at `20260522-152252` keeps the named
world-only crops unchanged while dropping `viewmodel` RMSE from `0.041117` to
`0.037606` and high-frequency ratio from `2.457` to `2.186` against
`20260522-134809`. The second sparser edge-cadence follow-up at
`20260522-160233` keeps the named world-only crops unchanged while dropping
`viewmodel` RMSE from `0.037606` to `0.033139` and high-frequency ratio from
`2.186` to `1.728` against `20260522-152252`. The compensated edge-cadence
follow-up at `20260522-164822` keeps the named world-only crops unchanged while
dropping `viewmodel` RMSE from `0.033139` to `0.019361`, moving viewmodel
high-frequency ratio from `1.728` to `1.007`, and recovering luma from
`0.091578` to `0.091292` after the stride-only `20260522-164504` trial had
dropped it to `0.089538`.
Candidate drift remains `0.000000`.

What is still broken is just as important: light-emissive regions are closer but
still too dim, nearby floors are slightly over-lifted, raster seams remain visible,
turbulent water/warp materials are not vanilla-quality, and the viewmodel still
needs classic placement and material parity beyond skin sampling and coarse
lighting balance.
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
