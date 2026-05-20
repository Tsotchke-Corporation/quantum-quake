# QGE State Of Development

Status date: 2026-05-20.

This document is the operational state snapshot for Quantum Quake. It is meant
to answer what exists now, what has evidence, what remains incomplete, and how
the repository should be handled after branch consolidation.

## Branch And Repository State

- `master` is the primary development branch for Quantum Quake.
- `origin/main` was an unrelated Three.js/WebTransport Quake history. It has
  been merged into `master` for repository ancestry while preserving the QGE
  tree as authoritative.
- The active source layout is the C/QuakeSpasm/QGE tree:
  `qge/`, `quake/Quake/`, `deps/moonlab/`, `tools/`, `tests/`, `.icc/`, and
  `docs/`.
- The JavaScript/WebTransport history is useful provenance, but it is not the
  active runtime tree for this project unless deliberately re-imported under a
  non-conflicting directory in a future task.

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
- Render logs report surface counts, snapshot misses, ownership fields, native
  IDWT counts, fallback reasons, and timing splits.

Known current visual state:

- The most recent coverage work fixes large missing-world holes in fixed-view
  captures.
- Floors, walls, and ceilings are still visibly glitchy: blocky texture
  sampling, raster seams, warped/noisy surfaces, and occasional diagnostic text
  contamination remain.
- `QGE_RENDER_BILINEAR_SAMPLES=1` and `QGE_RENDER_DISPLAY_FILTER=1` can improve
  smoothness, but recent live tests made them too expensive for default use.
- Edge sampling was rejected as a default because it produced blurred/line
  artifacts and much higher frame cost.

Next rendering priorities:

- Remove diagnostic notify text from captured world frames without hiding log
  evidence.
- Improve texture/lightmap sampling quality without the current bilinear cost.
- Separate projection/raster bugs from DWT/tone-map artifacts using paired
  classic/QGE captures.
- Add focused tests for surface coverage, seam stability, and texture sampling
  behavior.

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
- Noesis scripted player actions through `tools/noesis_quake_policy.sh` and
  `tools/noesis_quake_player.sh`.
- Engine-side Noesis gameplay outcome telemetry.
- Noesis summary reducer with route/combat/ammo/assist scoring.
- Assist telemetry for target visibility, target locks, target switches, aim
  alignment, movement injection, attack injection, and fire suppression.
- Recent `e1m1` harnesses can produce safe two-kill smoke runs without mouse
  capture or window activation.

Partial or pending:

- Noesis still depends on harnessed policy and engine assist for good play.
- It does not yet demonstrate robust, general Quake skill outside the bounded
  `e1m1` smoke.
- Target selection, route recovery, and post-second-kill continuation remain
  active work.

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
