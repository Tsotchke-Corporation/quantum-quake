# QGE State Of Development

Status date: 2026-05-21.

This document is the operational state snapshot for Quantum Quake. It is meant
to answer what exists now, what has evidence, what remains incomplete, and how
the repository should be handled after branch consolidation.

## Executive Summary

Quantum Quake is currently a QuakeSpasm-based QGE integration lab with live
diagnostic harnesses. The project has working runtime hooks, traces, tests, and
bounded authority experiments, but it is not yet a finished player-facing Quake
distribution.

The strongest current areas are QGE runtime evidence, traceability, controlled
visibility/projectile/audio paths, repeatable stream diagnostics, and the ICC
control plane around verified changes. The most visible weak areas are still QGE
world rendering fidelity and Noesis general gameplay. Noesis now moves in
no-script harness runs through an engine-side autonomous controller with local
wall, floor, and hazard probes, but it is not learning from experience and
should not be described as a trained Quake player or as having a robust
map-level planner.

The latest verified branch state is:

- `master` is the primary branch locally and remotely.
- Remote `HEAD` resolves to `refs/heads/master`.
- `origin/main` is fast-forwarded to the same commit as `origin/master` for
  compatibility after the historical merge.
- Latest verified runtime baseline is the current tone-headroom QGE renderer
  slice after `b1b7578` (`Use base palette for QGE world textures`), mirrored
  to both `origin/master` and `origin/main`.
- The active runtime tree is the C/QuakeSpasm/QGE tree, not the older
  JavaScript/WebTransport history.

## Branch And Repository State

- `master` is the primary development branch for Quantum Quake.
- `origin/main` was an unrelated Three.js/WebTransport Quake history. It has
  been merged into `master` for repository ancestry, then fast-forwarded to the
  current `master` commit so both remote branch names resolve to the same QGE
  tree. Remote `HEAD` still points at `origin/master`.
- The active source layout is the C/QuakeSpasm/QGE tree:
  `qge/`, `quake/Quake/`, `deps/moonlab/`, `tools/`, `tests/`, `.icc/`, and
  `docs/`.
- The JavaScript/WebTransport history is useful provenance, but it is not the
  active runtime tree for this project unless deliberately re-imported under a
  non-conflicting directory in a future task.
- Do not delete `origin/main` as part of normal cleanup without an explicit
  destructive-branch-change request; it is harmless as a compatibility pointer
  to the same commit as `master`.

## Recent Verified Baseline

Recent verified slices on `master` establish the current baseline:

- The current tone-headroom QGE renderer slice increases
  `QGE_NO_FLOOR_TONE_WHITE_HEADROOM` to keep preserved-detail world surfaces
  from over-brightening the fixed-view scene. Fixed-view evidence at
  `diagnostics/quake_stream/20260521-143859/frame_001.png` keeps QGE ownership
  of world geometry, textures, lightmaps, and the viewmodel with
  `fallback_reason=none`. Region checks against the classic `20260521-125448`
  reference show ceiling mean-luminance delta improving from about `+9.07` to
  `+2.30`, side-wall deltas from about `+9.79/+9.90` to `+3.83/+3.67`, and
  far-floor delta from about `+7.36` to `+3.70`. Raster seams, turbulent
  material fidelity, residual wall/ceiling brightness, and viewmodel fidelity
  remain open.
- `b1b7578` makes ordinary QGE world texture sampling use the base Quake
  palette instead of globally boosting high palette indices as fullbright.
  Fixed-view evidence at `diagnostics/quake_stream/20260521-135044/frame_001.png`
  keeps QGE ownership of world textures and lightmaps while moving the far-floor
  luminance and high-frequency texture noise closer to the classic reference.
  Side walls and ceilings remain visibly too bright, so this is a targeted
  floor/noise improvement rather than a renderer-complete claim.
- `656caf4` stabilizes QGE render-gate display gain by deriving the visible
  gain values from deterministic quantum-state marginal probabilities instead
  of finite-shot readout counts. Finite-shot readout and edge counters remain in
  the logs as measurement telemetry, but static floors, walls, and ceilings no
  longer shimmer just because a different shot distribution was sampled on the
  next frame.
- `8c52e0c` makes QGE primary rendering refresh every host frame by default.
  The stream tools default `QGE_RENDER_UPDATE_INTERVAL` to `1`, eliminating the
  previous stale-frame reuse that made floors, walls, ceilings, entities, and
  the viewmodel appear frozen or desynchronized unless the harness overrode the
  interval.
- `d0cfc8e` improves QGE world texture stability by closing narrow
  floor/wall/ceiling coverage gaps and adding bounded palette prefiltering for
  large projected texture footprints. This reduces noisy aliasing on close BSP
  surfaces without claiming vanilla material conformance.
- `a584125` adds targetless local exploration for no-script Noesis autonomous
  control. When no monster target is engaged, the server-side controller probes
  forward/left/right clearance, checks for floor and non-lethal contents ahead,
  then moves, turns, or slides away from wall contacts without using a cached
  route script. This directly addresses the "Noesis sits still" failure mode,
  but it is still reactive local navigation, not learned world planning.
- `76ae4da` improves QGE world render coverage by seeding a far-depth ambient
  world background before rasterization and normalizing raw warp/water texture
  coordinates before palette sampling. The verified live run removed the hard
  black voids seen when classic 3D was suppressed and reduced the wide gray
  warp band to a thinner seam, but floor, wall, ceiling, water, and material
  fidelity still need conformance work.
- `c93dcc9`, `889b25e`, `1c1acc3`, and `c4ec5f0` are the current Noesis combat
  and target-fixation baseline: visible-target arbitration, hidden wall-stall
  gating, hidden-target cooldowns, and reduced hidden-target wall push keep the
  no-script controller from ignoring visible enemies or grinding indefinitely
  into blocked hidden targets.
- `5da523e`, `edad050`, `e0c8e36`, `59c8d0f`, and `53cd998` are earlier
  rendering baseline slices: preserved-detail QGE display, no-floor tone
  mapping, normal-world palette opacity fixes, bilinear surface/lightmap
  sampling, duplicate snapshot clearing, near-plane clipping, FOV-aware world
  projection, non-additive same-depth ownership, lower world-surface ambient
  floors, tighter depth tie windows, and reduced per-face exposure patches.
- The historical `origin/main` history is merged for ancestry and the remote
  `origin/main` branch now matches `origin/master`; `master` remains the primary
  branch and remote `HEAD`.

Useful live evidence anchors:

- `diagnostics/quake_stream/20260521-112111/frame_001.png` plus
  `diagnostics/quake_stream/20260521-112111/quantum_quake.log`: fixed-view QGE
  graphics evidence after `656caf4`. Across 14 render frames, `gate_p`,
  `gate_edge`, `gate_gain`, `edge_gain`, `material_gain`, and `gate_rgb` each
  have one unique value, while `readout_ones` and `edge_ones` still vary. This
  is the current proof that visible render-gate gain is stable without dropping
  finite-shot measurement telemetry.
- `diagnostics/quake_stream/20260521-111059/frame_001.png` plus
  `diagnostics/quake_stream/20260521-111059/quantum_quake.log`: fixed-view QGE
  graphics evidence after `8c52e0c`. The stream used the tool defaults and logs
  `update_interval=1`, `reuse=0`, QGE ownership of world/textures/lightmaps and
  viewmodel after HUD warm-up, and no QGE-render fallback reason.
- `diagnostics/agent_stream/20260521-020917/noesis/qge_noesis_summary.json`:
  no-target `start` map evidence after `a584125`: `noesis_scripted=0`,
  `noesis_autonomous=1`, `target_count=0`, survived with no terminal stall,
  route distance `7005.019`, stationary fraction `0.0035`, 42 leaf transitions,
  movement injected on 280 samples, and view turns on 143 samples. This is the
  current proof that Noesis does not sit still when no route script or monster
  target is available.
- `diagnostics/agent_stream/20260521-021006/noesis/qge_noesis_summary.json`:
  E1M1 no-script evidence after `a584125`: `claim_scope` is
  `server_autonomous`, three kills, `56.0` inferred damage, no damage taken,
  route distance `7962.604`, 82 leaf transitions, no terminal stall, and one
  hidden-chase timeout. This shows the targetless exploration fallback did not
  break the existing E1M1 combat smoke.
- `diagnostics/agent_stream/20260521-013044/noesis/qge_noesis_summary.json`:
  live evidence for `76ae4da`: no-script E1M1 smoke passed with three kills,
  `48.0` inferred damage, no damage taken, no terminal stall, and the graphics
  run showed the black void removed with the broad gray warp band reduced.
- `diagnostics/quake_stream/20260520-191730/frame_001.png` and
  `diagnostics/quake_stream/20260520-193513/frame_001.png`: older blockier QGE
  world captures used as visual comparisons.
- `diagnostics/agent_stream/20260520-212112/noesis/qge_noesis_summary.json`:
  no-script Noesis wall-follow evidence after the autonomous wall-contact
  tuning: `noesis_scripted=0`, action trace line count `0`, three kills,
  `72.0` inferred damage, no damage taken, and no terminal stall. The matching
  frame at `diagnostics/quake_stream/20260520-212112/frame_001.png` still shows
  close-geometry QGE rendering artifacts, so this is a gameplay improvement and
  not a rendering-quality completion claim.
- `diagnostics/quake_stream/20260520-200246/frame_001.png`: improved QGE
  world-rendering capture after the detail, opacity, and near-clip fixes.
- `diagnostics/quake_stream/20260520-202448/frame_001.png`: follow-up no-floor
  tone-map capture that keeps the same preserved-detail path bright enough
  without the median-derived black floor.
- `diagnostics/quake_stream/20260520-215105/frame_001.png`: fixed-view classic
  reference capture used to distinguish real E1M1 brush panels from QGE
  rendering artifacts.
- `diagnostics/quake_stream/20260520-215412/frame_001.png`: fixed-view QGE
  capture after preserved-detail highlight headroom and authoritative-snapshot
  clearing; render logs show `snapshot_surfaces` matching `scene_surfaces`
  instead of the prior doubled snapshot surface count.
- `diagnostics/quake_stream/20260520-232353/frame_001.png`: fixed-view QGE
  capture after FOV-aware projection, darker lightmap-preserving surface
  shading, non-additive depth ties, and tighter depth ownership. The world is
  substantially closer to the classic fixed-view reference, but the remaining
  wall/doorway face panels are still visible and should stay on the rendering
  backlog.
- `diagnostics/quake_stream/20260521-021006/frame_001.png`: current live QGE
  frame from the latest Noesis run. Use it as a practical smoke reference, not
  as a vanilla-conformance claim; visible floor/wall/ceiling artifacts remain.
- `diagnostics/quake_stream/20260521-131825/frame_001.png`: fixed-view QGE
  capture after stronger direct-spatial tone headroom and the stratified
  footprint prefilter. The stable frame reports `fallback_reason=none`,
  `own_world=1`, `own_textures=1`, `own_lightmaps=1`, `own_viewmodel=1`,
  `res=1024`, and `texfilter=110668`. Region checks against the classic
  `20260521-125448` reference show ceiling mean luminance dropping from about
  `47` to `30`, front-wall mean from about `51` to `32`, and side-wall mean
  from about `56` to `36`, moving the QGE frame closer to classic while
  preserving QGE ownership.
- `diagnostics/quake_stream/20260521-135044/frame_001.png`: fixed-view QGE
  capture after removing the global high-palette fullbright boost from ordinary
  world texture sampling. The stable frame reports `fallback_reason=none`,
  `own_world=1`, `own_textures=1`, `own_lightmaps=1`, `own_viewmodel=1`,
  `res=1024`, and `texfilter=110668`. Region checks against the classic
  `20260521-125448` reference show the far-floor mean luminance moving from
  about `37.25` to `32.75` and horizontal high-frequency delta moving from
  about `2.71` to `2.47`, while the run keeps QGE texture and lightmap
  ownership. Side walls and ceilings remain visibly too bright, so this is a
  targeted floor/noise improvement rather than a renderer-complete claim.

The ICC control plane is part of the baseline. Verified slices should refresh
index, memory, git history, source-drift, production-audit, task-attempt, and
attempt-eval artifacts before push.

## Domain Ownership Matrix

| Domain | Current State | Authority Posture | Main Gap |
|---|---|---|---|
| Core runtime and trace | Working test-backed QGE runtime, event spine, and binary traces | Evidence and shadow ownership | Public API boundary and trace v2 coverage |
| Rendering | QGE primary path renders live captures with telemetry | Diagnostic primary render, classic remains visual reference | Vanilla-quality floors, walls, ceilings, sky, water, particles, and seams |
| Visibility | Shadow/parity telemetry and controlled authority smoke | Bounded audited writeback only | Map breadth, dynamic cases, and user-visible quantum modes |
| Projectiles/physics | Shadow state, branch state, writeback gates, collision oracle | Controlled authority gates | Full gameplay authority and quantum-native effects |
| Audio | Post-mix and source-mode telemetry with smoke evidence | Diagnostic/source authority experiments | Complete source authority and player-facing effects |
| AI/Noesis | No-script autonomous controller, target arbitration, wall/floor/hazard probes, hidden-target cooldowns, and opt-in scripted fixtures | Harness-only autonomous assist, not learning | Map-level planning, learned policy updates, general play, and robust navigation |
| Documentation/claims | Claims ledger, state doc, architecture docs, ICC attempts | Evidence-gated wording | Keeping docs synchronized after each verified slice |

## Implemented Runtime Surfaces

### QGE Core

Implemented:

- `qge_quantum_runtime_t` event spine with binary trace output.
- World registry and immutable frame snapshot structures for stable runtime
  references.
- Moonlab-backed RNG, AI, rendering, visibility, audio, physics, and trace
  modules.
- Native sparse IDWT bridge evidence and CPU fallback accounting.
- Test coverage through `tests/test_qge.c` and shell/Python contract tests.

Partial or pending:

- Stable trace v2 records for every sidecar-only diagnostic.
- Public API boundaries for QGE as an engine independent of Quantum Quake.
- More explicit ownership/fallback contracts for every domain transition.

### Rendering

Implemented:

- Sparse DWT framebuffer path for QGE primary rendering.
- Texture and lightmap signal caches.
- BSP surface projection, triangle raster, material/light encoding, viewmodel
  and entity coefficient paths.
- Surface-budget telemetry and default scene surface budget increased to 512
  after fixed-view `e1m1` diagnostics showed the old 128 limit dropped visible
  floor/wall/ceiling surfaces.
- QGE primary rendering updates every host frame by default. Stream tools
  default `QGE_RENDER_UPDATE_INTERVAL` to `1`, and the latest fixed-view
  evidence reports `reuse=0`, so renderer-owned world geometry and viewmodel
  output do not freeze behind the live camera.
- Detail-preserving QGE render output: the full RGB raster is kept while sparse
  DWT coefficients are encoded, then used as the default final display signal so
  floor/wall/ceiling detail is not dominated by sparse-block reconstruction.
- Full preserved-detail display uses a no-floor tone map with highlight
  headroom, so ordinary dark texture samples are not converted into black holes
  and bright floors/ceilings do not wash out as quickly while the scene still
  gets the brightness lift needed for live capture.
- Bilinear texture and lightmap sampling is enabled by default for QGE primary
  captures; the nearest-sample path remains available for faster diagnostics.
- Normal floor, wall, and ceiling textures no longer inherit the global
  transparent palette rule. Palette alpha is now reserved for fence/transparent
  world surfaces so ordinary world texels do not punch dark holes through the
  raster.
- Audited visibility-authority rendering now clears the earlier classic PVS
  visible-surface snapshot before recording the authoritative surface set, so
  QGE does not double-rasterize world panels as ghosted rectangles.
- QGE world-surface projection now clips at `QGE_SURFACE_NEAR_CLIP_DEPTH`
  instead of one unit from the camera, reducing giant over-projected wall and
  ceiling strips when the autonomous player is very close to level geometry.
- QGE world-surface projection now uses Quake's horizontal and vertical FOV
  separately, and world shading uses lower texture/light ambient floors with
  wider tone headroom so floors, walls, and ceilings keep more lightmap
  contrast instead of washing into bright BSP panels.
- The direct-spatial no-floor tone path now uses a higher
  `QGE_NO_FLOOR_TONE_WHITE_HEADROOM`, reducing fixed-view over-bright ceiling,
  side-wall, and floor regions while preserving the no-median-floor display
  path.
- QGE polygon raster fill now uses a near-uniform world gain instead of
  multiplying every texel on a BSP face by that face's coarse brightness score.
  Texture and lightmap samples still provide local shading, but adjacent floor,
  wall, and ceiling faces are less likely to appear as rectangular exposure
  blocks.
- Same-depth world samples use whole-sample luma ownership with a tight
  `QGE_SPATIAL_DEPTH_EPSILON`, which reduces seam brightening and avoids
  synthetic per-channel color combinations without treating nearby distinct
  faces as the same surface.
- QGE spatial rendering now seeds a far-depth ambient world background before
  world rasterization. Pixels not covered by the current visible surface set no
  longer collapse into hard black voids when the classic 3D fallback is
  suppressed for QGE diagnostics.
- Warp and water world surfaces normalize Quake raw `SURF_DRAWTURB` texture
  coordinates before palette sampling, reducing broad flat gray bands in water
  and adjacent world captures. Thin seams and incomplete turbulent-material
  fidelity remain.
- Texture footprint prefiltering is intentionally limited to stronger
  minification. Mildly minified floors, walls, and ceilings stay on bilinear
  sampling so nearby surfaces do not smear into broad bands, while distant
  texture crawl still has a bounded palette filter.
- Magnified and one-texel world texture samples stay on nearest palette lookup
  even when bilinear sampling is enabled. This keeps close floors, walls, and
  ceilings sharper while leaving bilinear/minification handling available for
  distance and slanted surfaces.
- QGE world texture sampling now uses the base Quake palette for ordinary
  palette indices instead of globally boosting indices `>=224` as fullbright.
  Fullbright texture metadata remains tracked separately, avoiding noisy
  emissive speckles on normal floors, walls, and ceilings.
- Render-gate visible display gain now uses deterministic state marginals
  rather than finite-shot readout counts. The stochastic counters are still
  logged, but static floors, walls, and ceilings do not pick up frame-to-frame
  brightness or color shimmer from measurement shot noise.
- Render logs report surface counts, snapshot misses, ownership fields, native
  IDWT counts, fallback reasons, and timing splits.

Known current visual state:

- The most recent coverage work fixes large missing-world holes in fixed-view
  captures.
- The most recent default-update work fixes stale-frame reuse in the stream
  harness, so QGE-owned floors, walls, ceilings, entities, and the viewmodel
  move with the camera by default instead of only refreshing every eighth host
  frame.
- The most recent render-gate work fixes one class of static-scene shimmer:
  finite-shot readout counts still vary in telemetry, but the visible display
  gain is stable for an unchanged camera.
- The most recent tone-headroom work reduces the fixed-view over-bright
  ceiling, side-wall, and far-floor deltas against the classic reference, but
  does not fix seams, turbulent surfaces, or vanilla material fidelity.
- Floors, walls, and ceilings still need conformance work: raster seams,
  warped/noisy surfaces, gray/turbulent seams, and incomplete vanilla-material
  fidelity remain, even after default bilinear sampling, preserved-detail
  highlight headroom, flattened raster fill, duplicate-snapshot clearing,
  ambient world background fill, warp coordinate normalization, every-frame
  refresh, deterministic render-gate display gain, direct-spatial tone headroom,
  and stratified footprint filtering reduce sparse DWT block bands,
  tone-floor artifacts, exposure panels, ghost panels, black voids, broad water
  bands, stale-frame artifacts, shot-noise shimmer, and over-bright world
  surfaces.
- This means the current QGE graphics path is useful for diagnostics and
  iterative comparison, but it should still be called visibly glitchy for
  player-facing floor, wall, and ceiling fidelity.
- `QGE_RENDER_BILINEAR_SAMPLES=0` and `QGE_RENDER_DETAIL_MIX=0` remain useful
  for isolating raw sparse DWT and nearest-sample behavior during diagnostics.
- `QGE_RENDER_DISPLAY_FILTER=1` can smooth noisy captures, but it is not the
  default because recent live captures showed whole-frame blur.
- Edge sampling was rejected as a default because it produced blurred/line
  artifacts and much higher frame cost.
- The current renderer should be described as improved, not fixed. In the
  latest fixed-view capture the world projection, contrast, and brightness are
  much closer to classic Quake, but floors, walls, and ceilings still do not
  match vanilla Quake fidelity.

Next rendering priorities:

- Remove diagnostic notify text from captured world frames without hiding log
  evidence.
- Compare default detail-preserving output against raw sparse DWT captures in a
  stable visual regression set.
- Separate projection/raster bugs from DWT/tone-map artifacts using paired
  classic/QGE captures.
- Add focused tests for surface coverage, seam stability, and texture sampling
  behavior.
- Add paired capture tooling that can score QGE frames against the classic
  renderer for known `e1m1` viewpoints.

### Visibility

Implemented:

- QGE visibility shadow/parity telemetry.
- Conservative authority readiness gates.
- Audited visibility mask application path for controlled authority smokes.
- Trace summary evidence for visibility gate and authority-apply counts.

Partial or pending:

- Broader parity across maps, water/sky/warp cases, and dynamic occlusion.
- Clear player-visible quantum visibility modes beyond conformance telemetry.

### Physics And Projectiles

Implemented:

- Projectile shadow telemetry, readiness gates, branch state, writeback
  decisions, and collision-oracle evidence.
- Persistence-boundary trace hashes for save/demo/replay transitions.
- Explicit `quantum_physics_authoritative` gate.

Partial or pending:

- Full gameplay authority beyond controlled projectile cases.
- Quantum-native projectile effects that are both playable and traceable.

### Audio

Implemented:

- Post-mix QGE audio processing.
- Source-mode quantum audio telemetry and source authority smoke evidence.
- Audio byte/metadata mirroring in agent streams.

Partial or pending:

- Complete per-source authority and material/visibility-conditioned source
  behavior.
- Player-facing quantum audio signatures beyond diagnostics.

### AI And Noesis Gameplay

Implemented:

- Typed QGE AI decision traces and replay metadata.
- Noesis no-script harness mode by default, with opt-in scripted player
  fixtures through `tools/noesis_quake_policy.sh` and
  `tools/noesis_quake_player.sh`.
- Engine-side autonomous assist hint for no-script Noesis runs.
- Engine-side Noesis gameplay outcome telemetry.
- Noesis summary reducer with route/combat/ammo/assist scoring.
- Assist telemetry for target visibility, target locks, target switches, aim
  alignment, movement injection, attack injection, and fire suppression.
- Hidden-target wall-push reduction: when Noesis is chasing an unseen target and
  the forward probe is blocked, the controller keeps clearer-side strafe but
  removes hidden-target forward pressure instead of grinding into the wall.
- Hidden-target cooldown feedback for no-script autonomous runs: a hidden target
  that does not become visible within the timeout is cooled down briefly so
  target reacquisition can try another enemy.
- Targetless local exploration for no-script autonomous runs: when no target is
  engaged, the controller probes forward/left/right clearance, checks that
  there is floor and no lava/slime ahead, moves through open space, and
  turns/slides away from wall contacts without using a cached route script.
- Recent `start` and `e1m1` no-script harnesses can move safely without mouse
  capture, window activation, or route action scripts. The current targetless
  movement evidence is
  `diagnostics/agent_stream/20260521-020917/noesis/qge_noesis_summary.json`;
  the current E1M1 combat evidence is
  `diagnostics/agent_stream/20260521-021006/noesis/qge_noesis_summary.json`.

Partial or pending:

- Noesis is not yet learning Quake from experience; current autonomous runs use
  a reactive server-side controller, and scripted route policies are regression
  fixtures rather than learned play.
- It does not yet demonstrate robust, general Quake skill outside the bounded
  `e1m1` smoke.
- Target selection, real navigation/search, spatial memory, frontier selection,
  avoided-hazard memory, post-kill continuation, and learned policy updates
  remain active work.
- No-script wall-contact behavior now has bounded wall-follow, hidden wall-push
  reduction, hidden-target cooldowns, and floor/hazard checks, but it can still
  look confused because it is steering from local probes and reactive target
  feedback rather than a map-level navigation plan.
- If Noesis appears stationary, first check the run manifest and summary:
  `input.noesis_scripted` should be `0`, `input.noesis_autonomous` should be
  `1`, the action trace should have zero route-script lines, and route movement
  should appear in `gameplay.route.total_distance` plus
  `assist.movement_injected_sample_count`. If all movement counters are zero,
  the no-script autonomous hint or server assist did not engage.

What "learning" would require:

- A replay dataset or live experience buffer with state/action/outcome records
  beyond the current diagnostic summaries.
- An optimizer or policy update loop that changes model/controller parameters
  across runs.
- Evaluation splits that show improvement on held-out routes, maps, or combat
  situations instead of a single scripted or hand-tuned `e1m1` smoke.

## What Counts As Progress

A change is not considered verified just because it looks better once. For this
repo, progress means a narrow code/docs change plus at least one of:

- a focused unit or contract test that would fail without the change,
- a successful live graphics or Noesis stream with preserved diagnostics,
- a trace, manifest, screenshot, or summary JSON path cited in the attempt,
- an ICC task-attempt record and passing attempt-eval report.

Visual work should explicitly say whether it improves fixed-view captures,
autonomous movement captures, or both. Noesis work should explicitly say whether
it uses no-script autonomous control or an opt-in scripted fixture.

## Common Failure Modes

- **Noesis sits still:** verify the no-script path is active and that
  `qge_noesis_autonomous` plus `qge_noesis_assist` are present in the stream
  configuration. A default no-script run should not rely on
  `tools/noesis_quake_policy.sh`. The current `start` map targetless baseline is
  `diagnostics/agent_stream/20260521-020917/noesis/qge_noesis_summary.json`,
  where `target_count=0` but route distance is `7005.019`; a new stationary run
  should be treated as an autonomous-assist engagement regression.
- **Noesis moves but does not improve:** this is expected for now. The current
  controller is reactive; there is no weight update, replay training, spatial
  memory, or policy optimizer in the loop.
- **QGE graphics look smeared:** check whether `QGE_RENDER_DISPLAY_FILTER=1`
  was enabled. It can hide noise but over-blurred recent live frames.
- **QGE graphics look over-bright or noisy:** use a 1024 fixed-view capture as
  the first reference. The current direct-spatial path uses
  `QGE_NO_FLOOR_TONE_WHITE_HEADROOM` plus a stratified footprint filter for
  strongly minified floor, wall, and ceiling samples; lower-resolution 512
  smokes are useful for speed but make the surface artifacts look worse.
- **QGE graphics look frozen or lagged:** verify the stream is using the
  current default `QGE_RENDER_UPDATE_INTERVAL=1`. Logs should report
  `update_interval=1` and `reuse=0` for a fresh primary render every host
  frame.
- **QGE graphics shimmer on a static camera:** inspect render-gate logs. After
  `656caf4`, `gate_p`, `gate_edge`, `gate_gain`, `edge_gain`,
  `material_gain`, and `gate_rgb` should be stable for an unchanged scene even
  though `readout_ones` and `edge_ones` continue to vary as finite-shot
  measurement telemetry.
- **QGE graphics show black holes:** check normal texture palette opacity and
  transparent/fence classification before treating it as a DWT problem.
- **QGE graphics show full-frame wall strips:** inspect near-plane clipping,
  camera proximity, and projected polygon depth before tuning DWT thresholds.
- **A branch appears stale:** fetch first, then verify `origin/HEAD` and
  compare `origin/main` and `origin/master`. The intended current state is that
  both resolve to the same commit, with `origin/HEAD` pointing at
  `origin/master`.

## Claims Policy

Allowed current claims are intentionally narrow:

- QGE demonstrates bounded simulated-QPU observables inside live Quake frames.
- QGE compiles captured Quake scene/runtime data into auditable evidence and
  oracle-style sidecars.
- Quantum Quake is progressing toward vanilla conformance under explicit
  ownership and fallback accounting.

Not allowed:

- Claims of practical hardware quantum advantage.
- Claims that the full frame is rendered by a quantum computer.
- Claims that Quantum Quake is a complete vanilla Quake port.
- Claims that a visual/gameplay result is supported without trace, metric, test,
  screenshot, or ICC evidence.

See [qge_claims_ledger.md](qge_claims_ledger.md) and
[claims/qge_claims.json](claims/qge_claims.json).

## Build And Test Baseline

Common checks:

```sh
make test_qge
./bin/test_qge
bash tests/test_noesis_input_contract.sh
python3 tests/test_qge_python_tools.py
make test
```

Build the macOS app:

```sh
make quake
```

Safe fixed-view graphics capture:

```sh
QGE_STREAM_LAUNCH=open QGE_STREAM_MOUSE=0 QGE_STREAM_ACTIVATE=0 \
QGE_STREAM_TRACE=1 QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=1 \
QGE_STREAM_WAIT_FRAMES=12 QGE_STREAM_PLAYER=none QGE_RENDER=2 \
QGE_RENDER_UPDATE_INTERVAL=1 QGE_STREAM_SOUND=0 \
bash tools/quake_graphics_stream.sh
```

`QGE_RENDER_UPDATE_INTERVAL=1` is now the default; keep it explicit in evidence
commands when the purpose is to prove every-frame QGE refresh.

Safe Noesis gameplay capture:

```sh
QGE_STREAM_LAUNCH=open QGE_STREAM_MOUSE=0 QGE_STREAM_ACTIVATE=0 \
QGE_STREAM_TRACE=1 QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=3 \
QGE_STREAM_WAIT_FRAMES=12 QGE_STREAM_PLAYER=noesis QGE_RENDER=2 \
QGE_RENDER_UPDATE_INTERVAL=1 QGE_STREAM_SOUND=0 \
bash tools/quake_graphics_stream.sh
```

ICC checks used for verified slices:

```sh
/Users/tyr/Desktop/infinite_context_coder/bin/icc source-drift --repo quantum_quake --format markdown
/Users/tyr/Desktop/infinite_context_coder/bin/icc assistant-status --repo quantum_quake --format markdown
/Users/tyr/Desktop/infinite_context_coder/bin/icc production-audit --repo quantum_quake --preset shell-hardening --format markdown
```

## Development Rules Of Thumb

- Keep QGE domain changes narrow and evidence-backed.
- Preserve classic Quake as the reference/fallback until a domain has a clean
  authority gate.
- Do not promote a visual option to default just because it looks smoother once;
  it needs performance and artifact evidence.
- Treat live harnesses as controlled diagnostics. Use `QGE_STREAM_MOUSE=0` and
  `QGE_STREAM_ACTIVATE=0` by default.
- Update docs and contracts when a runtime behavior becomes intentional.
- Record ICC attempts for verified gameplay, rendering, or production-hardening
  slices.
- Keep Noesis no-script by default. Use scripted route files only when the task
  is explicitly a regression fixture or policy-command-buffer test.
