# QGE State Of Development

Status date: 2026-05-20.

This document is the operational state snapshot for Quantum Quake. It is meant
to answer what exists now, what has evidence, what remains incomplete, and how
the repository should be handled after branch consolidation.

## Executive Summary

Quantum Quake is currently a QuakeSpasm-based QGE integration lab with live
diagnostic harnesses. The project has working runtime hooks, traces, tests, and
bounded authority experiments, but it is not yet a finished player-facing Quake
distribution.

The strongest current areas are QGE runtime evidence, traceability, controlled
visibility/projectile/audio paths, and repeatable stream diagnostics. The most
visible weak areas are QGE world rendering fidelity and Noesis general gameplay.
Noesis now moves in no-script harness runs through the engine-side autonomous
controller, but it is not learning from experience and should not be described
as a trained Quake player.

The latest verified branch state is:

- `master` is the primary branch locally and remotely.
- Remote `HEAD` resolves to `refs/heads/master`.
- `origin/main` is fast-forwarded to the same commit as `origin/master` for
  compatibility after the historical merge.
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

- `1c1acc3` adds hidden-target cooldowns for no-script Noesis autonomous
  control. A hidden target that does not become visible within the timeout is
  temporarily cooled down so the controller can reacquire another target
  instead of running the player into the same wall or obstruction indefinitely.
- `c4ec5f0` reduces hidden-target wall push by removing forward pressure when
  the target-facing wall probes are blocked and the target is not visible.
- `e0c8e36`, `59c8d0f`, and `53cd998` are the current rendering baseline:
  preserved-detail QGE display, no-floor tone mapping, normal-world palette
  opacity fixes, bilinear surface/lightmap sampling, duplicate snapshot
  clearing, and near-plane clipping for close world surfaces.
- `0809057` and earlier no-script movement commits improve autonomous
  wall-contact steering, but do not make Noesis a learned Quake player.
- The historical `origin/main` history is merged for ancestry and the remote
  `origin/main` branch now matches `origin/master`; `master` remains the primary
  branch and remote `HEAD`.

Useful live evidence anchors:

- `diagnostics/agent_stream/20260520-223950/noesis/qge_noesis_summary.json`:
  latest no-script Noesis autonomous evidence after hidden-target cooldowns:
  `noesis_scripted=0`, action trace line count `0`, `claim_scope` is
  `server_autonomous`, three kills, `48.0` inferred damage, no damage taken,
  score `81.574`, no terminal stall, `target_count=5`, and two
  `hidden_chase_timeout` events that forced target reacquisition.
- `diagnostics/agent_stream/20260520-221936/noesis/qge_noesis_summary.json`:
  no-script evidence after hidden wall-push reduction and before hidden-target
  cooldowns: action trace line count `0`, one kill, `24.0` inferred damage,
  `16.0` damage taken, route distance `8085.643`, and no terminal stall. This
  run showed that wall pushing had been reduced but target fixation was still a
  gameplay problem.
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
- `diagnostics/agent_stream/20260520-215458/noesis/qge_noesis_summary.json`:
  no-script Noesis evidence on the same renderer build:
  `noesis_scripted=0`, action trace line count `0`, total route distance
  `7147.375`, max displacement `1093.127`, one kill, and no terminal stall.

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
| AI/Noesis | No-script autonomous controller, wall-contact heuristics, hidden-target cooldowns, and opt-in scripted fixtures | Harness-only autonomous assist, not learning | General play, navigation, target choice, and training loop |
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
- Render logs report surface counts, snapshot misses, ownership fields, native
  IDWT counts, fallback reasons, and timing splits.

Known current visual state:

- The most recent coverage work fixes large missing-world holes in fixed-view
  captures.
- Floors, walls, and ceilings still need conformance work: raster seams,
  warped/noisy surfaces, and incomplete vanilla-material fidelity remain, even
  after default bilinear sampling, preserved-detail highlight headroom, and
  duplicate-snapshot clearing reduce sparse DWT block bands, tone-floor
  artifacts, and ghost panels.
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
  latest live capture the world is less blocky and avoids the worst dark holes
  and near-plane strips, but floors, walls, and ceilings still do not match
  vanilla Quake fidelity.

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
- Recent `e1m1` no-script harnesses can produce safe three-kill smoke runs
  without mouse capture, window activation, or route action scripts. The current
  strongest evidence is
  `diagnostics/agent_stream/20260520-223950/noesis/qge_noesis_summary.json`.

Partial or pending:

- Noesis is not yet learning Quake from experience; current autonomous runs use
  a reactive server-side controller, and scripted route policies are regression
  fixtures rather than learned play.
- It does not yet demonstrate robust, general Quake skill outside the bounded
  `e1m1` smoke.
- Target selection, real navigation/search, post-kill continuation, and
  learned policy updates remain active work.
- No-script wall-contact behavior now has bounded wall-follow, hidden wall-push
  reduction, and hidden-target cooldowns, but it can still look confused because
  it is steering from local probes and reactive target feedback rather than a
  map-level navigation plan.
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
  `tools/noesis_quake_policy.sh`.
- **Noesis moves but does not improve:** this is expected for now. The current
  controller is reactive; there is no weight update, replay training, or policy
  optimizer in the loop.
- **QGE graphics look smeared:** check whether `QGE_RENDER_DISPLAY_FILTER=1`
  was enabled. It can hide noise but over-blurred recent live frames.
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
QGE_STREAM_LAUNCH=direct QGE_STREAM_MOUSE=0 QGE_STREAM_ACTIVATE=0 \
QGE_STREAM_TRACE=1 QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=1 \
QGE_STREAM_WAIT_FRAMES=12 QGE_STREAM_PLAYER=none QGE_RENDER=2 \
QGE_RENDER_UPDATE_INTERVAL=1 QGE_STREAM_SOUND=0 \
bash tools/quake_graphics_stream.sh
```

Safe Noesis gameplay capture:

```sh
QGE_STREAM_LAUNCH=direct QGE_STREAM_MOUSE=0 QGE_STREAM_ACTIVATE=0 \
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
