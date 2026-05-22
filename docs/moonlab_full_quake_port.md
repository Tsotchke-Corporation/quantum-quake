# Moonlab Full Quake Port

This is the whole-game authority contract for Quantum Quake. The ICC task for
this contract is `qge_vanilla_quake_conformance`; its current top blocker is
the strict vanilla capture matrix proving QGE/Moonlab ownership counters.

This document defines what it means to turn Quantum Quake from a QuakeSpasm
build with quantum hooks into a real Moonlab-owned game port.

## Goal

The target is not "Quake with quantum effects". The target is that the entire
game runs under QGE/Moonlab authority. QuakeSpasm may remain as host,
compatibility shell, content loader, input/window/audio-device bridge, and
classic reference oracle, but it must not be hidden production authority for any
domain claimed as Moonlab-owned.

For this repo, "the entire game runs in Moonlab" means every authoritative
runtime domain is represented in QGE state, compiled through Moonlab-compatible
runtime abstractions, traced, replayable, and guarded by explicit ownership
counters:

- graphics: BSP world, lightmaps, alias models, sprites, particles, console/HUD
- media: mixed audio, decoded sound/music streams, temporal effects
- simulation: entity state, toss/bounce/flymissile physics, projectile fields
- stochastic events: QuakeC `random`, AI perturbations, particle spread
- visibility: BSP surface selection and occlusion
- UI and front-end game flow: menu, console, status bar, intermission, and
  other 2D/game-state surfaces

Classic Quake paths remain valuable as reference implementations and debugging
oracles. A complete Moonlab port may keep them available out of band, but no
classic path may silently produce final output, advance authoritative state, or
mask a missing QGE/Moonlab domain in production evidence.

## Authority Contract

A domain is not Moonlab-owned because a hook exists. It is Moonlab-owned only
when all of these are true:

- QGE receives the complete authoritative inputs for that domain.
- QGE stores those inputs in the world/snapshot/runtime state rather than only
  sampling them as transient side effects.
- Moonlab-compatible runtime code produces the domain output or decision.
- The host consumes the QGE/Moonlab output as authority.
- Fallback to classic is explicit in logs, traces, and ICC evidence.
- The diagnostic harness can compare against classic without allowing classic
  to be hidden production output.

The full-port acceptance target is the ICC completion oracle
`qge_vanilla_quake_conformance`. As of the current baseline, ICC reports that
the trace artifacts and tests exist, but the strict ownership matrix is still
blocked because `qge_vanilla_runtime_complete` is not proven.

## Current State

| Domain | Current integration | Honest status |
| --- | --- | --- |
| RNG | `PF_random()` routes through `QGE_RandomFloat()` when `quantum_rng=1`. | Real Moonlab-backed QRNG use. |
| Audio | `S_QuantumProcess()` transduces the mixed paintbuffer through QGE DCT/quantum gates. | Good post-mix media path, not per-asset ownership yet. |
| Rendering | `R_MarkSurfaces()` submits visible BSP surfaces to a QGE scene buffer; `R_RenderScene()` calls `QGE_RenderScene()` after classic world/entity rendering. | Scene ingestion is real; final framebuffer is still overlay/composite, not full graphics ownership. |
| Particles | `R_DrawParticles()` can call `QGE_DrawParticles()` when `quantum_particles=1`. | Separate quantum particle system, not complete Quake particle ownership. |
| Visibility | `R_DrawWorld()` has `quantum_vis` hooks. | Surface registration/query path exists but is not yet the full BSP traversal authority. |
| AI | Server think path calls `QGE_AIDecide()` for monsters. | Partial influence hook; needs explicit entity-state contract. |
| Physics/projectiles | `SV_Physics_Toss()` now calls `QGE_PhysicsTrackToss()` and `QGE_PhysicsTrackImpact()` into a persistent edict-keyed QGE registry. | Moonlab observes all toss/bounce/gib/missile state with shadow-prediction telemetry; classical collision remains authoritative. |

## Moonlab Capabilities To Use

| Moonlab subsystem | Relevant local paths | Quake use |
| --- | --- | --- |
| State vector + gates | `src/quantum/state.*`, `src/quantum/gates.*`, `src/quantum/measurement.*` | Small per-frame registers for RNG, AI, visibility masks, render coefficient extraction. |
| Metal/GPU backends | `src/optimization/gpu_metal.*`, `src/optimization/gpu/*` | DWT reconstruction, screen-space coefficient projection, batch Grover, future render target ownership. |
| Tensor networks/MPS | `src/algorithms/tensor_network/tn_state.*`, `tdvp.*`, `dmrg.*`, `contraction.*` | Projectile/particle fields, temporal media states, large sparse scene-field evolution. |
| Clifford/Pauli frame | `src/backends/clifford/pauli_frame.*`, `clifford.*` | Cheap many-entity stochastic updates, impact noise, monster coordination, many-shot effects. |
| Grover/search | `src/algorithms/grover.*`, QGE visibility API | BSP surface selection, PVS refinement, entity visibility queries. |
| Differentiable/optimization | `src/algorithms/diff/*`, VQE/QAOA/QPE modules | Offline tuning of scene encoders, visibility oracles, audio/render parameters. |
| Noise/mitigation | `src/mitigation/*`, noise APIs | Optional visual/physics uncertainty and zero-noise extrapolated diagnostics. |
| Entropy/QRNG | `src/utils/quantum_entropy.*`, `src/applications/hardware_entropy.*` | All gameplay randomness and media/particle sampling. |

## Port Architecture

### 1. Scene Ingestion Layer

Add a QGE scene graph that mirrors the Quake frame before drawing:

- map load: register BSP models, surfaces, planes, texture refs, lightmaps
- frame begin: register camera, FOV, view vectors, frame time
- world traversal: submit visible BSP surfaces with texture/lightmap IDs
- entity pass: submit alias models, sprites, viewmodel, transforms, skin refs
- particle pass: submit classic particle events and transient effects
- HUD/console pass: submit 2D draw calls and glyph atlas references

The initial implementation can keep Quake GL enabled as a visual reference.
The milestone is a QGE-owned render target that can be toggled between:

- `quantum_render 0`: classic Quake reference
- `quantum_render 1`: QGE/Moonlab composite diagnostic
- `quantum_render 2`: QGE/Moonlab primary framebuffer with classic fallback hidden

Current implementation status:

- `QGE_SceneBegin()` clears the frame scene buffer.
- `QGE_SceneSubmitWorldSurface()` receives every visible BSP surface accepted by
  Quake's PVS/frustum traversal.
- `quantum_scene_surface_budget` controls how many submitted surfaces the
  current DWT encoder consumes per frame. The buffer keeps the full submitted
  set; the default budget is 512 surfaces so normal E1M1 views do not stride
  across visible floors, walls, and ceilings and leave world-coverage gaps.
  Lower it for CPU-bound captures where performance is more important than
  visual completeness.

### 2. Full Graphics Ownership

The present DWT renderer encodes `cl_visedicts` and a background wall. That is
why windowed captures looked like a dark overlay rather than missing assets.
The real renderer needs these encoders:

- BSP surface encoder: polygon bounds, texture/lightmap coefficients, depth
- texture/media encoder: WAD/lump pixels into wavelet/frequency coefficients
- alias model encoder: pose/frame vertices and skin coefficients
- sprite encoder: sprite frame pixels, alpha, depth
- particle/projectile encoder: QGE particle field samples
- UI encoder: Quake glyphs, HUD icons, status bar images

Moonlab should own the final framebuffer. Classic GL can remain as the oracle for
pixel-diff diagnostics until parity is acceptable.

### 3. Media Ownership

Audio already has a credible post-mix quantum transducer. To make media fully
owned by Moonlab/QGE, add:

- per-sfx registration when sound effects are loaded
- stream/block IDs for music and ambient loops
- DCT/transducer state per source, not just post-mix stereo
- debug counters for processed samples, source count, quantum gate count
- fallback mixer parity checks against the classic paintbuffer

The existing `snd_quantum` cvars should stay as the public control surface.

### 4. Physics And Projectiles

All relevant Quake projectile and toss entities enter `SV_Physics_Toss()`:

- `MOVETYPE_TOSS`
- `MOVETYPE_BOUNCE`
- `MOVETYPE_GIB`
- `MOVETYPE_FLYMISSILE`

The first ownership-facing hook is now in place:

- `QGE_PhysicsTrackToss(ent, dt)`
- `QGE_PhysicsTrackImpact(ent, trace)`
- cvars: `quantum_physics`, `quantum_projectiles`
- persistent registry keyed by `NUM_FOR_EDICT(ent)`
- shadow-prediction telemetry: tracked count, active projectile count, purges,
  average/max prediction error

Next steps:

1. Mirror bounds, owner, water state, and impact state in the registry.
2. Evolve a Moonlab state for each projectile family:
   - state vector for a small exact position/momentum register
   - MPS/TDVP for projectile fields and trails
   - Pauli-frame/noise for uncertainty and impact spread
3. Run in shadow mode and compare Moonlab-predicted next origin to Quake's origin.
4. Gate authoritative replacement behind `quantum_physics_authoritative 1`.

This preserves gameplay while making the simulator increasingly responsible.

### 5. Visibility Ownership

The Grover BSP visibility path should move from per-surface optional query to a
full surface-set oracle:

- register all map surfaces at load time
- encode camera frustum and leaf/PVS state each frame
- use Moonlab/Grover batch search to return candidate visible surfaces
- keep Quake PVS as an oracle until false positives/negatives are measured
- expose debug metrics: total surfaces, candidates, accepted, rejected, time

### 6. AI Ownership

The current monster hook writes a QGE decision into entity state before QuakeC
think. This needs an explicit contract:

- entity ID, classname, health, distance, visibility, pain/death state
- action probabilities from QGE
- chosen action after measurement
- optional entanglement groups for coordinated monsters
- no hidden writes to unrelated entity fields

## Acceptance Criteria

A complete port is credible when these are true:

- `quantum_render 2` can produce the full visible game frame without relying on
  classic GL draw output.
- `snd_quantum 1` processes all active source streams with per-source telemetry.
- `quantum_physics 1` tracks every toss/bounce/gib/missile entity every server
  frame, and `quantum_physics_authoritative 1` can own at least projectiles.
- `quantum_vis 1` can provide the visible surface set and reports parity against
  Quake PVS/BSP traversal.
- Debug harnesses stream per-frame render, visibility, media, and physics
  counters with screenshots.
- Classic Quake reference paths stay available and parity-tested out of band,
  but hidden classic production output is a release blocker.
- ICC `completion-oracle --target qge_vanilla_quake_conformance` reports the
  strict runtime matrix complete.

## Immediate Implementation Order

1. Stabilize diagnostics and fullscreen/windowed harnesses.
2. Expand physics shadow tracking into a persistent projectile registry.
3. Replace render overlay with a QGE scene ingestion layer.
4. Add BSP surface and texture/lightmap encoders.
5. Add `quantum_render 2` primary framebuffer mode.
6. Move particles/projectile visuals from separate effects into the scene graph.
7. Make per-source audio/media transduction observable.
8. Add authoritative projectile mode after shadow error is bounded.
