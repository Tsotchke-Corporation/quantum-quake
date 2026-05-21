# QGE Engine Architecture

Status: initial engine contract, 2026-05-07.

QGE is the Moonlab-backed quantum game engine layer. Quantum Quake is the first
complete conformance title, not the permanent boundary of the engine.

## Engine Goal

QGE should provide reusable engine services for games that need quantum-owned
runtime domains, traceable bounded quantum observables, and research-grade
benchmark artifacts.

The engine must support two simultaneous modes:

- **Conformance mode**: reproduce a complete game faithfully enough that QGE is
  a credible runtime. For this repo, the target is vanilla Quake.
- **Research mode**: compile game state into quantum oracle/observable problems
  with explicit input, readout, baseline, and resource costs.

## Core Runtime Model

QGE runtime data flows through these layers:

1. **World registry**: stable resources such as BSP models, surfaces, textures,
   lightmaps, alias models, sprites, HUD images, sounds, and dynamic resources.
2. **Frame snapshot**: immutable per-frame camera, visible surfaces, entities,
   particles, sounds, lights, entropy refs, and ownership counters.
3. **Scene/media graph**: renderable and audible graph consumed by QGE domains.
4. **Quantum runtime**: Moonlab-backed states, gates, measurements, entropy,
   probes, entanglement edges, and fallbacks.
5. **Observable compiler**: transforms scene/media state into bounded
   observables and oracle IR.
6. **Artifact layer**: trace, replay, claims evidence, benchmark metrics,
   circuits, and resource estimates.

Existing implementation anchors:

- `qge_world_t` and `qge_frame_snapshot_t` are the first world/snapshot API.
- `qge_quantum_runtime_t` is the common trace and event spine.
- `qge_trace.bin` remains the fixed-width binary trace.
- JSON sidecars carry new compiler and benchmark metadata until stable binary
  trace v2 records exist.

## Engine Domains

Each domain progresses through the same ownership stages:

1. **Shadow**: QGE consumes game inputs and reports what it would do.
2. **Advisory/composite**: QGE output is visible or affects bounded choices.
3. **Authoritative**: QGE owns the final frame, audio block, visible set,
   projectile state, particle field, or decision.

Domains:

- render: sparse DWT, dense reference, material/phase observables
- visibility: surface/entity visible-set probabilities and search predicates
- media/audio: per-source and post-mix quantum transducers
- physics/projectiles: shadow and authoritative measured trajectory fields
- particles: field-based particle ownership
- AI: legal action probability registers and measured choices
- RNG/entropy: replayable domain-tagged quantum entropy
- UI: HUD, console, menu, glyph, and 2D media ownership

Every fallback from a domain must become a trace event. Silent fallback is a
publication blocker.

## Vanilla Quake Conformance Target

Quantum Quake is complete only when `quantum_render 2` can play vanilla Quake
with classic 3D and 2D draw paths hidden.

Required QGE-owned media:

- BSP world geometry, textures, lightmaps, lightstyles, fullbrights
- sky, water, lava, teleporter, warps, transparency
- dynamic lights
- alias models, sprite models, projectiles, pickups, monsters, viewmodel
- classic particles and projectile trails
- HUD, status bar, console, menu, glyphs, crosshair
- audio source telemetry and eventually per-source source processing
- visibility parity and physics/projectile shadow parity before authority

Classic Quake remains the reference, content shell, demo/save/network base, and
fallback. It is not acceptable as hidden production output for a QGE-owned
publication smoke.

Current implementation status:

- QGE primary rendering is active in diagnostics, but it is not yet vanilla
  complete. Floors, walls, and ceilings still show visible seams, noisy
  projection/tone artifacts, and incomplete material fidelity.
- Noesis gameplay evidence currently comes from a no-script, server-autonomous
  controller with local steering, combat assist telemetry, wall-contact
  heuristics, and hidden-target cooldowns. It is not a learned policy yet.
- Branch authority is consolidated on `master`; `origin/main` is a compatibility
  pointer to the same commit, not a separate active runtime tree.

## Quantum Media Compiler

The media compiler turns a game frame into a research problem:

- input: world registry, frame snapshot, scene/media graph, seed/replay trace
- output: bounded observables, oracle IR, resource costs, and circuit/benchmark
  artifacts

Initial observables:

- render gate finite-shot observable
- soft-shadow visibility
- patch irradiance
- visibility confidence
- edge or DWT band energy
- material transition/phase score

Initial algorithms:

- finite-shot dense registers for small render/media decisions
- amplitude estimation for bounded light-transport means
- Grover/minimum-finding models for unstructured candidate search
- QSP/QSVT only after a real block encoding exists

## Public Artifact Contract

Every publication or benchmark run must emit:

- binary QGE trace when available
- trace summary JSON
- scene/oracle IR JSON
- claims evidence JSON
- metrics JSON
- replay command
- circuit/resource summary when a circuit is used
- ICC task attempt

No claim should rely on prose alone.
