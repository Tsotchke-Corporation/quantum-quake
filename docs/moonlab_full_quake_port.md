# Moonlab Full Quake Port

This is the whole-game authority contract for Quantum Quake. The ICC task for
this contract is `qge_vanilla_quake_conformance`. The current strongest
self-contained publication pack proves the strict vanilla capture matrix for a
captured workload; the remaining work is expanding that authority and fidelity
until it covers the full game without hidden classic production authority.

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
`qge_vanilla_quake_conformance`. As of
`diagnostics/publication_pack/20260525-route-authority-gate`, ICC reports
`qge_vanilla_runtime_complete` ready for the bundled e1m1 QGE/vanilla capture
matrix. That evidence proves the ownership counters for the captured workload;
it does not by itself close renderer fidelity, all-map breadth, or whole-game
hardware deployment claims. The bundled `resource/qge_resource_envelope.json`
states the current Moonlab simulator/native-backend posture, and
`resource/qge_full_game_map_coverage.json` records the canonical registered
single-player map ledger: 9/32 maps covered, 23 maps pending, status `partial`.
`resource/qge_asset_inventory.json` records the PAK/BSP asset availability
behind that partial ledger.
`resource/qge_asset_requirements.json` records the exact registered
`maps/*.bsp` entries needed for every canonical target map, including which
entries are already present and which entries are still missing.
`resource/qge_moonlab_full_game_plan.json` records the combined deployment
ledger for the entire registered map set: which maps already have strict
simulator/native capture evidence, which maps would become capture jobs if
assets existed locally, and which maps are blocked by unavailable registered
BSP assets. It also carries `registered_asset_handoff` and per-map
`asset_handoff_status`, so an unavailable map distinguishes a runnable copy
plan from a blocked copy destination or a manual licensed-asset requirement.
The post-asset capture queue and Moonlab full-game deployment plan now share a
route-contract ledger for all 32 canonical registered maps, so queued jobs and
the final claim gate carry explicit route class, episode/slot,
combat/special-route requirements, and authority-domain requirements instead of
relying on one generic missing-map smoke profile. The gate remains blocked if a
future plan lacks that complete route-contract ledger, or if a covered map lacks
route-contract authority evidence from breadth capture matrices. The current
covered set is 9/9 route-authority ready; the remaining 23 maps are still asset
unavailable.
`resource/qge_moonlab_deployment_gate.json` is the fail-closed claim gate for
the sentence "the entire game runs in Moonlab." It is currently `blocked`
because coverage is 9/32, the remaining 23 registered BSP assets are
unavailable locally, and the whole-game simulator/native deployment claim is
not allowed until those criteria all pass. The gate summary, Markdown, next
actions, and ICC evidence now cite the registered-asset install script and the
post-install capture queue command needed to continue without weakening the
claim gate. When discovery finds no licensed candidate assets, the intake
evidence and generated script now say `no_op_blocked`, set
`manual_registered_asset_required`, and list the remaining maps instead of
looking like a real copy plan was produced.
`resource/qge_native_backend_boundary.json` records the native bridge boundary
verdict for `qge_context_get_or_create_render_acceleration`, `qge_dwt_render`,
and `qge_metal_init_common`.
`resource/qge_moonlab_job_specs.json` breaks that posture into selected replay
and benchmark jobs. `resource/qge_moonlab_job_results.json` records the local
simulator/native replay results: four simulator jobs completed, two native
replay jobs completed, zero blocked jobs, and zero hardware submissions.
`resource/qge_moonlab_replay_plan.json` records the replay/validation contract
for those selected jobs, including which artifacts must be present and which
job remains an unsubmitted hardware candidate.
`resource/qge_moonlab_submission_packet.json` records the deterministic
hardware-candidate handoff contract: artifact hashes, required backend ID, shot
schedule, readout metadata, and the result file that must be updated after a
real submission.
`advantage/qae_moonlab_payload.json` and
`advantage/moonlab_qae_circuits/*.moonlab` record the directly executable
Moonlab control-plane payload currently available: four one-qubit `RY`
circuits for the MLAE observation/readout distribution, 384 total shots.
`advantage/qae_moonlab_oracle_kernel.json` and
`advantage/qae_moonlab_oracle_kernel.moonlab` record the next compiled
Moonlab artifact: a 32-qubit, 7,415-gate reversible `Q_f` predicate kernel
for the Bernoulli-lift benchmark oracle. It is supported-gate
`# moonlab-circuit v1` text and remains under the 4 MB control-plane body
limit.
`advantage/qae_moonlab_observation_zero.json` and
`advantage/qae_moonlab_observation_zero.moonlab` record the first actual
benchmark observation circuit: exact uniform state preparation over the 234
captured candidates, uniform threshold preparation, and inline `Q_f` for the
`grover_power=0` observation. The current circuit is 32 qubits, 7,740 gates,
and 67,643 bytes, below Moonlab's 4 MB control-plane body limit.
`advantage/qae_moonlab_grover_schedule_plan.json` records the exact next
control-plane payload set: selected powers 0, 1, 2, and 4 all fit, and
`advantage/qae_moonlab_grover_circuits/*.moonlab` contains the four exact
per-power Moonlab circuits. The largest selected body is `grover_power=4` at
69,924 gates and 610,599 bytes.
`resource/qge_moonlab_submission_bundle.json` records the stricter Moonlab
control-plane readiness verdict. It checks whether the candidate circuit
artifacts are directly executable `# moonlab-circuit v1` text with
`NUM_QUBITS`. The current bundle is `ready_for_control_plane_submission`: the
readout payload, `Q_f` kernel, power-zero observation, and selected Grover
schedule are executable Moonlab control-plane text. No hardware result is
claimed from that artifact alone.
`resource/qge_moonlab_hardware_record_template.json` is generated from that
packet and provides the exact `qge.moonlab_hardware_record.v0` object Moonlab
must fill before any hardware result is ingested.
`resource/qge_moonlab_hardware_submission_scope.json` is the scoped handoff
verdict for that bounded QAE candidate; it excludes the full-game deployment
gate so asset blockers do not contaminate hardware-packet readiness evidence.
`tools/qge_moonlab_job_runner.py` regenerates those results independently from
the job specs, can compare them with `--expect`, and can emit a replay plan
with `--plan-out` plus the submission packet with `--submission-out`, so the
Moonlab execution evidence is not trapped inside the pack builder. The pack
also includes `tools/qge_moonlab_hardware_ingest.py` for the return path: it
accepts a `qge.moonlab_hardware_record.v0`, validates the backend ID,
candidate digest, shot schedule, and readout metadata, and writes an updated
job-results artifact plus a bounded hardware comparison. The pack still keeps
full-game hardware execution, hardware quantum advantage, and dense-state
claims out of scope until separate hardware deployment evidence exists.

## Current State

| Domain | Current integration | Honest status |
| --- | --- | --- |
| RNG | `PF_random()` routes through `QGE_RandomFloat()` when `quantum_rng=1`. | Real Moonlab-backed QRNG use. |
| Audio | `S_QuantumProcess()` transduces the mixed paintbuffer through QGE DCT/quantum gates and source-authority telemetry. | Good post-mix media path with observable source authority, not full decoded-stream ownership yet. |
| Rendering | `R_MarkSurfaces()` submits visible BSP surfaces to a QGE scene buffer; `quantum_render 2` can own the primary captured framebuffer path with native sparse-DWT evidence. | Captured workload authority is proven; visual fidelity and complete special-surface coverage remain incomplete. |
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
  strict runtime matrix complete for the claimed publication/capture bundle.

## Immediate Implementation Order

1. Expand the ready matrix beyond the current 9/32 partial full-game map
   coverage ledger. Re-run the missing-map queue with
   `tools/qge_full_game_capture_queue.py diagnostics/publication_pack/20260525-route-authority-gate`
   after installing registered BSP assets. With the current `assets/id1/pak0.pak`,
   the queue has zero locally runnable missing maps and 23 registered maps
   require additional registered BSP assets before capture. Use
   `tools/qge_asset_inventory.py --asset-root assets/id1` to verify the PAK/BSP
   hashes, BSP29 header/lump validity, and canonical-map availability before
   rebuilding the queue.
2. Improve `quantum_render 2` visual fidelity without weakening ownership
   counters or native sparse-DWT evidence.
3. Move particles/projectile visuals from separate effects into the scene graph.
4. Submit the QAE hardware-candidate job from `qge_moonlab_job_specs.json`
   through Moonlab hardware when available, recording backend IDs and readout
   metadata in `qge_moonlab_job_results.json` and preserving the submission
   posture in `qge_moonlab_replay_plan.json`. Start from
   `qge_moonlab_submission_packet.json`; it is the no-claim hardware handoff
   contract for the bounded QAE benchmark job. Ingest the returned
   `qge.moonlab_hardware_record.v0` with `tools/qge_moonlab_hardware_ingest.py`
   so the simulator result, hardware result, and claim posture remain separate.
5. Push per-source audio/media transduction from post-mix authority toward
   decoded-stream ownership.
