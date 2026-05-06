# Quantum Quake Full Architecture Plan

Status: updated 2026-05-06 after the sparse DWT, GL-state, memory, audio, material, and physics-registry passes.

This is the current implementation contract for turning Quantum Quake from a QuakeSpasm build with QGE hooks into a Moonlab-owned game port. It supersedes the older high-level PDF plan for day-to-day engineering, while preserving its core ambition: the runtime should be genuinely backed by Moonlab quantum computation, not just decorated with effects.

## 1. Target

The final product is still Quake, but these runtime domains are owned by QGE/Moonlab:

- rendering: BSP world, lightmaps, textures, alias models, sprites, particles, viewmodel, HUD, console
- visibility: surface and entity visibility set generation
- media: sound effects, ambient loops, mixed audio, music stream blocks, temporal effects
- simulation: toss, bounce, gib, missile, projectile trails, particle fields
- stochastic events: QuakeC `random`, spread, particles, AI perturbations, replayable entropy
- AI influence: explicit action-probability proposals and measured decisions

Quake remains the reference implementation, content loader, input shell, QuakeC rules VM, networking/demo format base, savegame format base, and fallback renderer/mixer/simulator. The port is complete only when QGE can own the output of each listed runtime domain behind explicit authoritative cvars and pass parity gates against classic Quake.

## 2. Current Snapshot

Working now:

- `PF_random()` can route to QGE QRNG through `quantum_rng`.
- `S_QuantumProcess()` runs mixed stereo blocks through QGE DCT/transducer processing, with dry/wet blending.
- `R_MarkSurfaces()` submits visible world surfaces into a QGE scene buffer.
- QGE sparse DWT encodes surface bounds plus material/light signals and composites a GL blit over classic Quake.
- Dense 28-qubit render states are lazy; sparse DWT no longer allocates dense 4.3 GB frame states by default.
- `SV_Physics_Toss()` feeds toss/bounce/gib/missile entities into an edict-keyed QGE physics registry with shadow-error telemetry.
- `R_DrawParticles()` can draw QGE particles when enabled.
- `quantum_vis` can set up a viewpoint and query the QGE visibility module, but Quake PVS/BSP remains authoritative.
- `QGE_AIDecide()` is called from server physics for monsters, but the contract is still thin.
- Harnesses exist for windowed render streams, crash watching, screenshot capture, SDL dummy-audio startup, and per-frame QGE telemetry.

Not complete:

- QGE is not yet the primary framebuffer.
- Texture/lightmap pixels are sampled only as signals, not rendered as assets.
- Alias models, sprites, viewmodel, HUD, console, dynamic lights, sky, water warps, and fullbrights are not owned by QGE.
- Physics remains observational except for particle side effects.
- Audio is post-mix, not per-source.
- Visibility is a query path, not the provider of the visible set.
- AI decisions are not a stable entity-state protocol.
- Replay and multiplayer entropy determinism are not solved.

## 3. Core Principle: Domain Ownership With Parity

Every domain has three stages:

1. Shadow: QGE consumes the same inputs as Quake and reports what it would do.
2. Composite or advisory: QGE output is visible or affects choices, but Quake remains the fallback oracle.
3. Authoritative: QGE output drives the actual frame, audio block, visible set, projectile state, or decision.

No domain jumps directly to authoritative. Each transition requires:

- a stable data contract
- deterministic capture/replay
- per-frame telemetry
- parity tests against Quake
- memory and frame-time budgets
- runtime fallback on error

## 4. Representation Strategy

Use the Moonlab representation that matches the problem. Do not force a dense state vector into every subsystem.

| Workload | Moonlab representation | Quake use |
| --- | --- | --- |
| Small exact registers | Dense state vector and gates | QRNG batches, AI decision registers, compact visibility/measurement tests |
| Sparse image fields | Sparse DWT coefficient state | Real-time QGE renderer |
| Dense probability framebuffer | Dense state vector, direct probability extraction | 64x64 reference/hero mode, not default gameplay |
| Many particles/projectiles | MPS, CA-MPS, TDVP | projectile fields, particle trails, temporal state evolution |
| Many stochastic entities | Clifford tableau / Pauli frame | cheap correlated AI, impact noise, spread, many-shot effects |
| Surface/entity search | Grover and GPU batch search | visible surface set, target/entity candidate search |
| Real-time kernels | Metal backend first, CPU fallback | IDWT, coefficient splat/resolve, Grover batch, probability marginalization |
| Audio blocks | Dense 8-16 qubit transducer states | per-source and post-mix DCT processing |
| Noise and mitigation | Moonlab noise + ZNE | diagnostics, parity confidence, optional stylized uncertainty |
| QGT/topology | Moonlab quantum geometry/topology modules | offline material analysis, teleporter/liquid field demos, research mode |
| PQC/Shor/QV/etc. | Moonlab applications/benchmarks | integrated lab/benchmark menu, not per-frame gameplay |

The default real-time path is sparse and bounded. Dense 28-qubit allocation is allowed only in explicit dense/probability modes and must fail closed to sparse mode.

## 4.5 Quantum Differentiation

The port is not finished if it only recreates classical Quake through harder machinery. Quantum Quake must expose quantum semantics as part of the engine and, in opt-in modes, as part of the game.

The minimum bar:

- state is represented as amplitudes, phases, tensor factors, tableaux, or probability distributions where that representation changes behavior
- measurement events are explicit and logged
- interference, entanglement, decoherence, topology, or amplitude amplification produce visible, audible, or simulated consequences
- the player can tell which systems are quantum-owned without reading source code
- debug/lab views expose the actual state being evolved, not just a post-effect

### 4.5.1 Classical Quake Vs Quantum Quake

| Domain | Classical Quake | Quantum Quake target |
| --- | --- | --- |
| Framebuffer | Rasterized polygons, z-buffer, textures, lightmaps | Sparse quantum wavelet field, optional dense probability framebuffer, phase/interference diagnostics |
| Visibility | Boolean PVS/frustum/BSP traversal | Probability distribution over visible surfaces, Grover-amplified candidates, measured or thresholded visible set |
| RNG | Deterministic table/PRNG semantics | Bell-verified QRNG stream with replay traces and domain-tagged entropy |
| Projectiles | One authoritative trajectory per entity | Shadow or authoritative state over trajectory/impact possibilities, measured at collision or observation boundaries |
| Particles | Independent sprite particles | MPS/CA-MPS/Pauli-frame particle fields with correlated trails, interference, decoherence |
| AI | Local branches plus random draws | Action superpositions, measurement, entangled groups, explicit probability vectors |
| Audio | Mixed channels plus classical DSP | Per-source and post-mix quantum transducers, phase/interference state, source entanglement |
| Materials | Texture flags and light values | Material phase, fullbright/warp/lightmap coefficients, optional QGT/topological field metadata |
| Debugging | Counters, screenshots, demos | State-vector probabilities, DWT coefficient maps, phase maps, entanglement/entropy/noise telemetry |

Faithful parity modes should remain available. Quantum modes do not need to be numerically identical to classical Quake once a domain is explicitly authoritative; they need to be playable, bounded, reproducible under trace replay, and explainable through state telemetry.

### 4.5.2 Quantum-Native Capabilities

These are the features that distinguish the product, not just the implementation.

#### Probability/Phase Rendering

The renderer should have a visible quantum identity:

- amplitude budget: surfaces, entities, lights, and particles compete for normalized probability mass
- interference: overlapping surface/entity coefficients can reinforce or cancel
- phase: teleporters, liquids, fullbrights, dynamic lights, and damage effects can rotate phase rather than only changing RGB
- measurement/flicker: dense/probability modes can show shot-like shimmer and collapse as a deliberate aesthetic
- lab overlays: probability, phase, sparse coefficients, depth, and material channels can be toggled

Shipping implication: `quantum_render 2` should be recognizable Quake. `quantum_render 3` and lab overlays should look unmistakably quantum.

#### Quantum Visibility And Uncertain Occlusion

Classic Quake asks whether a surface is visible. Quantum Quake can maintain a distribution over possible visible surfaces:

- Grover amplifies likely visible surface sets
- occluders suppress probability behind them rather than merely clipping a list
- water, teleporters, and special materials can create partially coherent visibility fields
- visibility confidence can modulate render brightness, audio muffling, AI awareness, and projectile uncertainty

The new capability is not just faster PVS. It is a shared visibility probability field that multiple domains can consume.

#### Superposed Projectiles

Projectile ownership should eventually produce effects classical Quake does not naturally express:

- trajectory wave packets before collision
- branch weights for ricochet, splash, and near-miss outcomes
- measurement when a projectile hits, passes a visibility boundary, or is observed by the player
- interference trails that reveal likely paths
- decoherence near walls, water, explosions, and monsters

Default competitive gameplay can keep projectiles mostly classical. A quantum ruleset can allow nails, rockets, grenades, and vore balls to use these state fields authoritatively.

#### Entangled Monster Behavior

Monster coordination should not be a hidden global script. It should be representable as shared quantum state:

- nearby monsters can share an entanglement group
- one monster seeing the player can change action probabilities for the group
- pain, death, or line-of-sight measurement can collapse group behavior
- Pauli-frame/Clifford updates support many cheap correlated monsters
- dense registers remain for small exact decisions

This gives Quantum Quake a distinct AI feel: coordination through measured correlations, not merely better pathfinding.

#### Quantum Audio Field

Audio should evolve from post-mix processing to a quantum media field:

- each active source gets a transducer state
- source position, visibility confidence, material, and player motion condition the circuit
- related sources can be phase-locked or entangled
- room/reverb effects can be interference patterns instead of delay-line-only DSP
- lab telemetry exposes source probabilities, gate counts, clipping, and wet/dry energy

The audible difference should be spatial and stateful: teleporters, liquids, shamblers, rockets, and runes can have persistent quantum signatures.

#### Topological And Geometric Materials

Moonlab's QGT/topology modules should not be forced into every frame, but they can create new material systems:

- teleporters/slipgates: Berry-phase or winding-number driven fields
- runes/armor/powerups: topological protection scores that resist decoherence or alter projectile collapse
- liquids: phase fields with curvature/metric-driven warping
- secret/lab maps: Chern/QGT visualizations as actual level machinery
- offline material baking: QGT/topology analysis produces material coefficients consumed by the renderer and audio

This is how Moonlab's research stack becomes visible without pretending that Chern-number computation belongs in every 16 ms frame.

#### Replayable Quantum Experiments

Quantum Quake should ship with a lab surface:

- record a frame/run as a quantum experiment trace
- replay with the same QRNG/measurement trace
- inspect state evolution per subsystem
- compare classical and quantum outcomes
- export benchmark artifacts for papers and demos

This turns the game into a live demonstration of Moonlab, not only a game port.

### 4.5.3 Capability Matrix

| Moonlab capability | Engine use | Player-visible use |
| --- | --- | --- |
| Bell-verified QRNG | entropy broker, spread, AI, particles, projectile collapse | replayable "quantum seed" runs, non-PRNG randomness claims with telemetry |
| Dense state vector/gates | small exact registers, audio transducers, direct framebuffer reference | lab probability views, measured action/projectile events |
| Grover/search | visible-surface/entity candidate amplification | uncertain occlusion, visibility confidence effects |
| Metal/GPU backends | DWT, probability extraction, Grover batch kernels | higher-res primary QGE framebuffer and live overlays |
| Gate fusion | faster repeated AI/audio/visibility circuits | smoother high-entity quantum modes |
| MPS/TDVP | projectile and particle fields over time | coherent trails, spreading wave packets, temporal media state |
| CA-MPS | large Clifford-dominated particle/projectile fields with sparse non-Clifford events | many correlated quantum effects without dense memory blowups |
| Clifford/Pauli frame | cheap many-shot stochastic correlations and noise | entangled monster groups, correlated impact noise, large swarms |
| Noise models | decoherence, environmental uncertainty, hardware-style diagnostics | water/lava/teleporter decoherence effects, quantum difficulty modifiers |
| ZNE/mitigation | lab confidence and comparison runs | optional "stabilized" experiment view |
| QGT/topology | material baking, field analysis, lab maps | slipgate/rune/topological material mechanics |
| Quantum Volume/Shor/PQC | benchmark/lab menu and demo artifacts | Moonlab showcase outside core e1m1 gameplay |

### 4.5.4 Product Modes

The game should support multiple honest modes:

- Classic Reference: Quake behavior with QGE disabled or shadow-only.
- Quantum Faithful: Quake rules and maps remain intact, but render/audio/RNG/visibility/particles are QGE-owned.
- Quantum Ruleset: opt-in mechanics use projectile superposition, entangled monsters, topology materials, and measurement events.
- Lab Mode: introspection, probability/phase overlays, dense framebuffer reference, Moonlab benchmarks, trace export.
- Paper Mode: deterministic captures with fixed traces, benchmark summaries, screenshot/audio artifacts.

This avoids mixing incompatible goals. A faithful port, a quantum-enhanced game, and a research demo can share infrastructure without pretending to be the same mode.

### 4.5.5 Design Rules For Quantum Features

- If a feature can be implemented as a normal random number plus a shader, it needs a state/measurement/telemetry reason to live in QGE.
- Parity mode should match Quake; quantum ruleset mode may intentionally diverge.
- Every measurement that changes gameplay must be traceable and replayable.
- Every quantum-owned domain must expose fallback reasons.
- Dense states are used for small exact systems and lab references; sparse, tensor, and Clifford representations are the production path.
- The player-facing effect should match the underlying representation: phase effects should come from phase, correlations from entanglement/frame state, uncertainty from distributions/noise, search confidence from Grover/visibility probabilities.

## 4.6 Quantum Semantics Contract

Quantum Quake needs a runtime contract that is stricter than "call Moonlab somewhere." Every quantum-owned subsystem must expose the same core ideas:

- basis: what discrete states are represented
- amplitudes: what the complex weights mean
- phase: which gameplay/material/time variables rotate phase
- evolution: which unitary, tensor-network, tableau, or noise operation advances state
- measurement: when the distribution becomes a concrete Quake event
- observation boundary: what counts as player/server/world observation
- decoherence: what environmental interactions reduce coherence
- replay: which entropy and measurement events reproduce the run
- fallback: when the subsystem returns control to classical Quake

This contract should exist in code as a small common layer, not only in docs:

```c
typedef enum {
    QGE_DOMAIN_RENDER,
    QGE_DOMAIN_VISIBILITY,
    QGE_DOMAIN_PROJECTILE,
    QGE_DOMAIN_PARTICLE,
    QGE_DOMAIN_AUDIO,
    QGE_DOMAIN_AI,
    QGE_DOMAIN_RNG,
    QGE_DOMAIN_MATERIAL
} qge_quantum_domain_t;

typedef enum {
    QGE_REP_DENSE_STATE,
    QGE_REP_SPARSE_DWT,
    QGE_REP_MPS,
    QGE_REP_CA_MPS,
    QGE_REP_CLIFFORD_TABLEAU,
    QGE_REP_PAULI_FRAME,
    QGE_REP_CLASSICAL_ORACLE
} qge_quantum_representation_t;

typedef enum {
    QGE_MEASURE_RENDER_SAMPLE,
    QGE_MEASURE_VIS_SURFACE_SET,
    QGE_MEASURE_PROJECTILE_IMPACT,
    QGE_MEASURE_PARTICLE_POSITION,
    QGE_MEASURE_AUDIO_BLOCK,
    QGE_MEASURE_AI_ACTION,
    QGE_MEASURE_RNG_BATCH,
    QGE_MEASURE_MATERIAL_PHASE
} qge_measurement_kind_t;

typedef struct {
    qge_quantum_domain_t domain;
    qge_measurement_kind_t kind;
    int frame;
    int server_time_msec;
    int subject_id;
    uint64_t basis_index;
    double probability;
    double phase;
    uint64_t entropy_offset;
    uint64_t trace_id;
} qge_measurement_event_t;
```

Every gameplay-affecting measurement writes a `qge_measurement_event_t` to the experiment trace. Visual-only sampling can be rate-limited, but if it changes physics, AI, audio routing, damage, pickup state, or demo output, it must be traceable.

## 4.7 Observation Boundaries

Classical Quake has no concept of observation; an entity always has one origin, one velocity, one AI action. Quantum Quake needs explicit observation boundaries.

Observation boundaries:

- player observation: object enters the player-visible set with high confidence
- collision observation: trace/hull collision requests a concrete impact result
- damage observation: a projectile branch overlaps a damageable entity
- audio observation: a source is mixed into the audible block
- AI observation: QuakeC asks for a legal action
- network observation: server serializes a state to clients
- save/demo observation: state is written to persistent output
- debug observation: lab mode requests a measurement rather than a non-destructive probe

Non-destructive probes are allowed and should be preferred for lab overlays:

- probability mass over surfaces
- phase map
- entanglement entropy
- coefficient energy
- visibility confidence
- branch weights
- decoherence score

Destructive measurements are explicit and limited. If a player opens a lab overlay, the overlay should not accidentally collapse projectiles or AI state unless the mode says it does.

## 4.8 Quantum State Spaces

Each subsystem needs a basis chosen for game semantics, not just for mathematical convenience.

### 4.8.1 Render State

Sparse DWT basis:

```text
|level, subband, x, y, channel, material, depth_bucket, phase_bucket>
```

Meaning:

- amplitude magnitude controls coefficient energy
- phase controls interference, material phase, temporal shimmer, liquid/teleporter behavior
- channel selects luminance/chroma/fullbright/alpha/depth/confidence
- material carries world/alias/sprite/HUD class and topological tags

Current code tracks only index/value pairs. The full renderer should extend active coefficients to complex coefficients:

```c
typedef struct {
    uint64_t basis;
    float amp_re;
    float amp_im;
    float depth;
    uint16_t source_id;
    uint8_t source_kind;
    uint8_t channel;
} qge_render_coeff_t;
```

The render field is not just an image buffer. It is a coherent field that later resolves to RGB. Interference is meaningful before tone mapping:

- surfaces sharing pixel/scale/channel can reinforce
- fullbright masks can stay coherent while base textures decohere
- liquid/teleporter fields rotate phase over time
- dynamic lights can modulate amplitude and phase separately
- visibility confidence can attenuate amplitude before reconstruction

Dense probability framebuffer reference:

```text
|x, y, depth, color, material, object_id, view_state>
```

This remains a lab/reference mode. It is the most direct expression of the old PDF's "probability distribution equals image" idea, but it is not the default because dense 28-qubit state vectors are too expensive for normal play.

### 4.8.2 Visibility State

Visibility basis:

```text
|surface_id, leaf_id, depth_bucket, occluder_class, material_class>
```

The oracle marks likely-visible states from:

- Quake PVS while in shadow mode
- frustum
- leaf/node relation
- portal/water/slipgate material behavior
- dynamic occluders
- recent frame temporal prior

Grover amplification gives a candidate distribution. QGE then either thresholds it or measures a visible set, depending on mode.

Important distinction:

- parity mode: QGE must not drop any Quake-visible surface
- quantum mode: QGE can keep a probability field, allowing uncertain visibility to affect render/audio/AI before a concrete set is selected

### 4.8.3 Projectile State

Projectile basis for a single projectile family:

```text
|projectile_id, path_segment, position_bucket, velocity_bucket, impact_bucket, fuse_bucket>
```

MPS/CA-MPS layout should encode projectile histories as a chain:

```text
site 0: projectile family
site 1..N: time/path segment buckets
site N+1: impact/material bucket
site N+2: damage/fuse bucket
```

Why tensor networks:

- projectile paths are locally correlated through time
- most branches are low-entanglement until impact
- Clifford-heavy updates can be cheap in CA-MPS
- non-Clifford rotations encode gravity, splash bias, homing, or material phase

Measurement boundaries:

- impact with solid world
- overlap with player/monster hit hull
- network serialization
- high-confidence player observation, in Quantum Ruleset mode
- fuse expiration for grenades

Player-visible effect:

- pre-impact trails show likely paths
- watery/slipgate/teleporter regions preserve coherence longer
- lava/explosions cause faster decoherence
- a "collapsed" hit is logged as a measurement event

### 4.8.4 Particle State

Particles should not be 500 independent classical sprites. They should be local samples from a field:

```text
|event_id, local_x, local_y, local_z, time_bucket, energy_bucket, material_bucket>
```

Representation:

- MPS for trails and ordered time evolution
- CA-MPS when many updates are Clifford-like with sparse non-Clifford impulses
- Pauli-frame batches for cheap noise/correlation sampling

New capability:

- explosions create radial phase kicks
- teleport effects are coherent wave packets
- blood/sparks decohere quickly
- bubbles and smoke are slow-decoherence fields
- particle trails can be correlated with projectile branches

### 4.8.5 AI State

AI basis:

```text
|entity_id, action, intensity, memory, group_state>
```

Dense small-register AI remains useful for individual monsters. Group AI should use Clifford/Pauli-frame-style correlation:

- group tableau/frame tracks correlated action flips
- line-of-sight marks an observation on one entity
- measurement of one action can condition group probabilities
- damage and death inject noise/decoherence

Legal action masking must be classical and explicit. QGE proposes probabilities over legal actions; QuakeC legality remains the guardrail.

### 4.8.6 Audio State

Per-source transducer basis:

```text
|source_id, frequency_bin, phase_bucket, spatial_bucket, material_bucket>
```

Current post-mix processing uses 8-qubit DCT blocks. Full media ownership adds per-source transducers:

- encode source spectral bins with rotations
- entangle nearby or causally related sources
- condition phase on position, velocity, material, visibility confidence
- measure/interfere into an output frequency block
- preserve dry fallback for audibility

Player-visible effect:

- slipgates and teleporters have phase-coherent signatures
- shamblers/rockets can modulate nearby source phase
- water/lava muffling follows visibility/material probability, not just hard room flags
- entangled sources can produce spatial beating or collapse-like changes when seen/heard

### 4.8.7 Material/Topology State

Material basis:

```text
|material_id, phase, curvature_bucket, coherence_class, topological_charge>
```

Most material topology should be baked or updated slowly:

- QGT metric/curvature analysis creates material metadata
- slipgate/rune/liquid fields use that metadata in render/audio/projectile evolution
- topological protection alters decoherence rate
- topological charge can affect projectile branch collapse or AI perception

This gives Moonlab's QGT/topology modules a concrete game role without pretending that every wall is a Chern insulator.

## 4.9 Shared Quantum Fields

The deeper architecture should avoid isolated gimmicks. The same quantum fields should influence multiple domains.

### 4.9.1 Visibility Confidence Field

Produced by: Grover visibility.

Consumed by:

- renderer: amplitude attenuation and phase uncertainty
- audio: muffling/reverb confidence
- AI: player awareness probability
- projectiles: observation/decoherence rate
- lab: surface probability overlay

### 4.9.2 Material Phase Field

Produced by: texture/lightmap/material encoder, QGT/topology metadata, dynamic effects.

Consumed by:

- renderer: phase/interference color behavior
- audio: per-source transducer phase
- projectiles: branch rotation and decoherence
- particles: event field shape
- AI: special material perception, e.g. slipgate threat/source

### 4.9.3 Entropy/Measurement Field

Produced by: QRNG and measurement broker.

Consumed by:

- gameplay randomness
- projectile collapse
- particle samples
- AI decisions
- audio block measurement
- replay traces

### 4.9.4 Entanglement Graph

Tracks relationships between runtime subjects:

```c
typedef struct {
    int subject_a;
    int subject_b;
    qge_quantum_domain_t domain;
    float strength;
    float coherence;
    int created_frame;
    int last_observed_frame;
} qge_entanglement_edge_t;
```

Examples:

- monster pack coordination
- projectile and trail field
- teleporter pair audio/visual phase lock
- rune and protected projectile/material field
- shambler attack and nearby light/audio perturbation

The graph should decay. Entanglement is a resource and a debugging object, not an invisible permanent flag.

## 4.10 Quantum Ruleset Mechanics

The faithful port is necessary, but the project needs a mode where Moonlab enables new mechanics. These should be opt-in and testable.

### 4.10.1 Superposed Nailgun

Concept:

- each nail starts as a narrow trajectory packet
- nearby surfaces/monsters shape branch weights
- visibility and distance control decoherence
- hit measurement occurs at impact or high-confidence observation

Classical difference:

- a nail can show a fan of likely paths without being a normal spread RNG
- path probabilities are stateful and affected by phase/material fields
- replay trace can show why a branch collapsed

Moonlab:

- CA-MPS/MPS for path packet
- QRNG for measurement
- Pauli-frame noise for environmental decoherence

### 4.10.2 Rocket Wavefront

Concept:

- rocket body stays mostly classical for readability
- splash/damage field is quantum
- impact location measures a radial amplitude field
- water/lava/slipgate materials rotate or decohere the splash field

Classical difference:

- splash damage is not just radius distance; it is a measured probability field influenced by material and visibility

Moonlab:

- dense small state or MPS for splash branches
- noise/decoherence for environment
- render/audio consume the same field for explosion visuals/sound

### 4.10.3 Grenade Branch Fuse

Concept:

- grenade trajectory shadow has multiple low-weight bounce/fuse branches
- repeated bounces increase decoherence
- final detonation measures branch distribution

Classical difference:

- unpredictable but replayable branch behavior
- lab mode can show branch weights over time

Moonlab:

- MPS over path segments
- QRNG trace measurement
- classical trace collision as oracle

### 4.10.4 Entangled Monster Packs

Concept:

- monsters in a group share an entanglement edge
- one monster seeing the player rotates group action probabilities
- pain/death collapses or decoheres group state

Classical difference:

- coordinated behavior emerges from measured correlations, not a central squad script
- lab overlay shows group action probabilities and collapse events

Moonlab:

- Clifford/Pauli-frame for large packs
- dense registers for small exact groups

### 4.10.5 Slipgate Phase Zones

Concept:

- slipgates are coherent phase/material fields
- objects crossing them experience phase rotation, visibility ambiguity, audio phase lock, and altered projectile coherence

Classical difference:

- a region can affect render, audio, projectiles, and AI through one shared phase field

Moonlab:

- QGT/topology-baked material metadata
- render phase field
- audio transducer phase
- projectile decoherence modifier

### 4.10.6 Runes As Topological Protection

Concept:

- rune pickups alter coherence/decoherence rules rather than only setting stats
- protection rune reduces decoherence of player-adjacent quantum fields
- quad/pentagram can amplify probability mass or protect against collapse

Classical difference:

- powerups manipulate quantum state behavior and are visible in lab overlays

Moonlab:

- QGT/topology material metadata
- noise model modifiers
- QRNG/measurement broker tags

### 4.10.7 Quantum Secrets

Concept:

- secret triggers can depend on phase alignment, not only coordinates
- player actions align material/audio/render fields
- lab mode can expose the hidden phase if enabled

Classical difference:

- secrets are solved by manipulating coherent fields, not only pressing walls

Moonlab:

- material phase field
- audio transducer phase
- render phase overlay

## 4.11 Experiment Trace Format

Quantum Quake should be able to record a run as an experiment.

Trace layers:

1. build/version metadata
2. map and registry IDs
3. cvar/product mode state
4. frame snapshots hashes
5. entropy batches
6. measurement events
7. quantum state probes
8. fallback events
9. screenshots/audio hashes
10. performance and memory counters

Pseudo-schema:

```c
typedef struct {
    uint32_t magic;
    uint16_t version;
    uint16_t flags;
    uint64_t run_id;
    uint64_t moonlab_abi_hash;
    uint64_t qge_build_hash;
    uint64_t quake_content_hash;
} qge_trace_header_t;

typedef struct {
    int frame;
    qge_quantum_domain_t domain;
    qge_quantum_representation_t representation;
    uint64_t state_hash;
    float entropy;
    float coherence;
    float max_probability;
    float total_probability;
    int active_basis_count;
} qge_state_probe_t;

typedef struct {
    int frame;
    qge_quantum_domain_t domain;
    int subject_id;
    int reason_code;
    float metric_value;
    char message[96];
} qge_fallback_event_t;
```

Use cases:

- deterministic replay
- paper artifacts
- bug reports for "weird quantum outcome"
- side-by-side classical/quantum comparison
- regression tests for measurement boundaries

## 4.12 Lab Mode Observables

Lab Mode is how we prove Quantum Quake is real.

Required overlays:

- render coefficient heatmap
- render phase map
- render probability map
- visibility confidence map
- projectile branch-weight view
- particle field probability slices
- AI action probability table
- entanglement graph
- audio source spectrum/transducer state
- entropy and measurement timeline
- fallback event timeline

Required commands:

- `qge_trace_start`
- `qge_trace_stop`
- `qge_trace_replay`
- `qge_probe_frame`
- `qge_probe_subject <domain> <id>`
- `qge_overlay probability|phase|coefficients|visibility|entanglement|audio`
- `qge_compare_classic`

These tools are part of the product, not merely developer debug. They are how the player/researcher sees the quantum machinery.

## 4.13 Quantum Implementation Proof Obligations

For any feature claiming to be quantum-native, require at least three proofs:

1. Representation proof: the feature uses a Moonlab representation whose state cannot be reduced to the same scalar cvar without losing behavior.
2. Measurement proof: gameplay-affecting collapse/selection is recorded in the experiment trace.
3. Coupling proof: at least one other domain consumes the same quantum field or measurement.

Examples:

- A blue shimmer shader is not enough.
- A projectile wave packet with branch weights, collapse trace, and shared render/audio trails is enough.
- A random monster decision is not enough.
- an entangled group with action probabilities, measurement events, and Pauli-frame telemetry is enough.
- A teleporter texture warp is not enough.
- a slipgate phase field that affects render, audio, visibility, and projectile decoherence is enough.

This is the line that distinguishes "quantum-themed" from "Quantum Quake."

## 4.14 First Foundation Module

Before adding more effects, build a small quantum runtime spine that every domain can share.

New files:

- `qge/qge_quantum_runtime.h`
- `qge/qge_quantum_runtime.c`
- `qge/qge_trace.h`
- `qge/qge_trace.c`
- `qge/qge_observable.h`
- `qge/qge_observable.c`

Purpose:

- centralize domains, representations, measurement kinds, state probes, fallback events, and entanglement edges
- provide a domain-tagged entropy broker
- write/read trace records
- expose non-destructive observables for lab mode
- give current systems a place to report measurements without depending on renderer/audio/physics internals

Minimal API:

```c
typedef struct qge_quantum_runtime_s qge_quantum_runtime_t;
typedef struct qge_trace_writer_s qge_trace_writer_t;
typedef struct qge_trace_reader_s qge_trace_reader_t;

qge_quantum_runtime_t *qge_quantum_runtime_create(void);
void qge_quantum_runtime_free(qge_quantum_runtime_t *rt);

void qge_quantum_frame_begin(qge_quantum_runtime_t *rt, int frame, int server_time_msec);
void qge_quantum_frame_end(qge_quantum_runtime_t *rt);

uint64_t qge_quantum_entropy_u64(qge_quantum_runtime_t *rt,
                                 qge_quantum_domain_t domain,
                                 int subject_id);

void qge_quantum_record_measurement(qge_quantum_runtime_t *rt,
                                    const qge_measurement_event_t *event);

void qge_quantum_record_probe(qge_quantum_runtime_t *rt,
                              const qge_state_probe_t *probe);

void qge_quantum_record_fallback(qge_quantum_runtime_t *rt,
                                 const qge_fallback_event_t *event);

int qge_quantum_trace_open(qge_quantum_runtime_t *rt, const char *path);
void qge_quantum_trace_close(qge_quantum_runtime_t *rt);
```

First integrations:

1. `qge_rng.c`: brokered entropy batches and `QGE_MEASURE_RNG_BATCH` events.
2. `qge_hooks.c` render path: `QGE_DOMAIN_RENDER` state probes for active coefficients, coefficient energy, max value, and fallback events.
3. `snd_quantum.c`: audio block state probes and clipping/fallback events.
4. `qge_ai.c`: measured action events with action probability vector hash.
5. `qge_physics.c`/`qge_hooks.c`: projectile shadow probes and future impact measurements.

First tests:

- trace writer creates a valid header and frame record
- deterministic replay entropy returns recorded values
- measurement events preserve domain/kind/frame/subject/probability
- state probes can be recorded without allocating dense state
- no QGE subsystem needs to know the trace file layout

Exit criterion:

- one windowed run with `quantum_debug 1` emits a trace containing render probes, RNG events, audio probes when sound is enabled, and no dense 28-qubit allocation in sparse mode
- `make test` covers the trace and runtime APIs

This module is the first actual engineering step if the goal is to make the quantum distinction real. Without it, every later feature will invent its own telemetry, entropy, and measurement semantics.

ICC tracking:

- task id: `qge_quantum_runtime_trace_spine`
- artifact root: `/Users/tyr/Desktop/infinite_context_coder/artifacts/repos/quantum_quake/tasks/qge_quantum_runtime_trace_spine`
- status: foundation module implemented and verified on 2026-05-06
- next item: `qge_world_registry_and_snapshot`
- note: ICC source index and memory artifacts were refreshed on 2026-05-06; git-history is unavailable until this repo has a first commit.

ICC session-plan items:

1. `rt_types`: verified.
2. `trace_core`: verified.
3. `entropy_broker`: verified.
4. `frame_hooks`: verified.
5. `first_probes`: verified for render, audio, AI, RNG, and physics reporting.
6. `tests`: verified with focused runtime, trace, and replay unit coverage.
7. `harness`: verified with windowed trace smoke and SDL dummy-audio trace smoke.

## 5. Runtime Architecture

### 5.1 QGE World Registry

Add a persistent registry populated at map/load time:

- `qge_world_t`
- `qge_model_ref_t`
- `qge_surface_ref_t`
- `qge_texture_ref_t`
- `qge_lightmap_ref_t`
- `qge_alias_model_ref_t`
- `qge_sprite_ref_t`
- `qge_sound_ref_t`

The registry owns stable QGE IDs. Quake pointers may be cached as debug references, but runtime contracts must use stable IDs so traces survive reloads and replay.

Required registrations:

- BSP models, leaves, nodes, planes, surfaces, texture chains
- WAD/GL texture source pixels, dimensions, CRCs, fullbright masks, warp flags
- lightmaps, styles, dynamic-light channels
- alias model vertices, triangles, skins, animation frames
- sprite frames, alpha modes
- HUD/status-bar images and glyph atlas
- sound effects, music stream blocks, ambient channels

### 5.2 QGE Frame Snapshot

Each frame begins with a single immutable snapshot:

- frame number, host time, server time, client time
- camera origin, view axes, FOV, viewport
- current map/model IDs
- Quake PVS/leaf state as oracle input
- all candidate visible world surfaces
- all visible/interpolated edicts
- dynamic lights
- current particles and particle events
- active sound sources and mixed audio block IDs
- entropy events consumed this frame

Rendering, visibility, physics, audio, and AI read from this snapshot. This avoids hidden cross-domain writes.

### 5.3 Ownership Cvars

Normalize the public control surface:

- `quantum_render 0`: classic renderer
- `quantum_render 1`: QGE diagnostic composite
- `quantum_render 2`: QGE sparse-DWT primary framebuffer
- `quantum_render 3`: QGE dense probability framebuffer reference
- `quantum_render 4`: QGE hybrid/MPS upscaler, when available
- `quantum_vis 0`: classic PVS/BSP
- `quantum_vis 1`: QGE shadow telemetry
- `quantum_vis 2`: QGE visible set authoritative with Quake fallback
- `quantum_physics 0`: classic physics only
- `quantum_physics 1`: QGE shadow tracking
- `quantum_physics_authoritative 1`: QGE owns approved projectile classes
- `quantum_particles 0`: classic particles
- `quantum_particles 1`: QGE particle overlay
- `quantum_particles 2`: QGE owns particle events and rendering
- `snd_quantum 0`: classic audio
- `snd_quantum 1`: post-mix transducer
- `snd_quantum 2`: per-source transducer plus post-mix safety
- `quantum_ai 0`: classic QuakeC decisions
- `quantum_ai 1`: QGE advisory/probability telemetry
- `quantum_ai 2`: QGE measured action selection
- `quantum_rng 0`: classic deterministic PRNG
- `quantum_rng 1`: Moonlab QRNG
- `quantum_rng 2`: replay trace entropy

Existing cvars can stay, but new authoritative modes should follow this pattern.

## 6. Graphics Plan

Graphics is the centerpiece. The near-term default renderer is sparse DWT, not dense 28-qubit probability rendering.

### 6.1 Scene Graph

Build `qge_scene_t` from the frame snapshot:

- world surface instances: polygon, plane, texture ID, lightmap ID, styles, material flags, depth range
- alias model instances: model ID, skin ID, frame interpolation, transform, lighting, fullbright mask
- sprite instances: sprite ID, frame ID, transform, alpha/depth
- particle instances/fields
- dynamic light instances
- viewmodel instance
- 2D draws: HUD icons, status bar, console, crosshair, text

The existing `QGE_SceneSubmitWorldSurface()` is stage 0. Expand it into typed submit calls rather than adding more anonymous fields to one struct.

### 6.2 Asset Encoders

Add cached asset encoders:

- texture to wavelet pyramid, including RGB/YCoCg and fullbright mask
- lightmap to wavelet pyramid, including style weights
- warp/liquid procedural phase field
- sky layer and skybox encoder
- alias skin to coefficient atlas
- sprite frame to coefficient atlas
- HUD/glyph atlas to coefficient atlas

Asset encoders run on load/change, not every frame. Per-frame work should mostly transform and splat cached coefficients.

### 6.3 Surface Renderer

Replace current rectangle encoding with polygon-aware coefficient generation:

- project clipped polygon vertices
- derive screen bounds and depth gradient
- sample cached texture and lightmap coefficients
- combine material, light energy, fullbright, warp, and dynamic-light channels
- write depth-aware DWT coefficients
- resolve occlusion through a QGE depth/visibility field

Acceptance: `quantum_render 2` can render e1m1 world geometry with textures/lightmaps recognizable and classic GL world hidden.

### 6.4 Entity Renderer

Add:

- alias model pose interpolation
- triangle projection/raster-to-coefficients
- skin/fullbright coefficient sampling
- sprite billboard projection
- weapon/viewmodel path
- dynamic entity lighting

Acceptance: monsters, pickups, rockets, torches, sprites, and weapon are present in `quantum_render 2`.

### 6.5 UI Renderer

Add QGE ownership for:

- status bar
- numbers/icons
- crosshair
- centerprint
- console background and text
- menu text and images

Acceptance: the game is playable with classic GL 3D and 2D drawing disabled.

### 6.6 Output Backends

Implement in this order:

1. CPU sparse DWT reference.
2. Metal sparse coefficient splat and inverse DWT.
3. Metal tone map, depth resolve, and RGB upload.
4. Dense 64x64 probability framebuffer as explicit reference mode.
5. Hybrid low-res quantum plus MPS/diffusion upscaler only after the primary sparse renderer is stable.

The MPS/diffusion path from the old PDF is a research/quality mode. It requires a capture dataset, training pipeline, exported Moonlab-compatible MPS, deterministic conditioning schema, and pixel-diff gates before becoming a shipping default.

## 7. Visibility Plan

Move from per-surface query to full visible-set ownership.

Data:

- register all BSP surfaces and leaves on map load
- store surface bounds, leaf/node ownership, texture/material IDs
- pass Quake PVS as oracle input while in shadow mode
- pass camera/frustum each frame

Algorithm:

- build a visible-surface candidate oracle from PVS, frustum, and coarse occluders
- use Grover/batch search to amplify candidate visible surfaces
- return an ordered candidate set with probabilities
- compare against Quake traversal every frame
- classify false positives, false negatives, and ordering/depth mismatches

Acceptance:

- shadow mode reports false negatives at 0 for e1m1/e1m2 harness runs
- false positives are bounded and do not exceed surface budget
- `quantum_vis 2` can supply the surface set used by QGE rendering
- Quake PVS remains fallback on invalid telemetry

## 8. Physics, Projectiles, And Particles

### 8.1 Physics Registry

Expand the current edict-keyed registry to include:

- entnum, classname, model, owner, movetype, solid
- origin, angles, velocity, avelocity
- mins, maxs, size
- waterlevel, watertype, groundentity
- touch/impact state
- projectile family classification
- last Quake trace result
- QGE-predicted next origin/velocity
- error metrics

### 8.2 Shadow Evolution

Use multiple Moonlab representations:

- dense small state for exact projectile-family registers
- MPS/TDVP for projectile/trail fields
- Pauli-frame/noise for spread, ricochet uncertainty, and impact effects
- QRNG for spread and impact sampling

Quake trace remains the collision oracle until authoritative collision is proven.

### 8.3 Authoritative Projectile Mode

Start with narrow classes:

1. nails
2. rockets
3. grenades
4. vore balls
5. gibs/toss objects

`quantum_physics_authoritative 1` updates origin/velocity only for approved classes and only when shadow error stays under threshold for a warmup window. On error spike, the entity reverts to Quake physics and logs the reason.

### 8.4 Particle Ownership

Replace the overlay with event ownership:

- explosions
- blood
- trails
- bubbles
- teleport splash
- lava/slime
- muzzle flashes/sparks

QGE particle output becomes part of the scene graph, not a separate GL draw.

## 9. Audio And Media Plan

Post-mix transduction remains the fallback. Full media ownership requires per-source processing.

Add:

- sound asset registration on load
- source IDs for active channels
- per-source DCT/transducer state
- source-position conditioning
- ambient loop state
- music stream block processing
- post-mix limiter and dry/wet safety
- telemetry: source count, processed samples, skipped samples, gate count, block latency, clipping

Modes:

- `snd_quantum 1`: current post-mix path
- `snd_quantum 2`: source transducers plus post-mix safety
- `snd_quantum_mix 0`: pure dry debug

Acceptance:

- SDL dummy-audio harness proves initialization and processing
- real audio harness prints SDL/CoreAudio device selection
- source count and processed block counters increment in e1m1
- pure dry mode is never silent when classic Quake has audio

## 10. RNG, Replay, And Multiplayer

QRNG must not break demos, saves, or multiplayer determinism.

Add:

- central entropy broker: every random draw records domain, frame, caller, and value
- batch QRNG buffers per domain
- `quantum_rng 2` replay mode reading a trace
- deterministic seed mode for tests
- server-authoritative entropy policy for multiplayer
- savegame serialization of pending QGE entropy state

Acceptance:

- classic demo playback can run with `quantum_rng 0`
- QGE demo capture can replay with `quantum_rng 2`
- tests can assert exact outcomes under deterministic traces

## 11. AI Plan

Replace hidden action influence with an explicit protocol.

Input contract:

- entnum, classname, monster type
- health, flags, pain/death state
- enemy visible, distance, direction, line-of-sight quality
- aggression, skill, recent damage
- group membership

Output contract:

- action probability vector
- measured action
- confidence
- entropy consumed
- optional entanglement group state

Integration:

- `quantum_ai 1`: QuakeC remains authoritative, QGE logs probabilities.
- `quantum_ai 2`: QGE measured action selects among legal QuakeC actions.
- no direct writes to unrelated entity fields.

Use Clifford/Pauli-frame for large coordinated groups and dense states for small exact decisions.

## 12. Advanced Moonlab Capability Use

Capabilities should be used where they fit.

Per-frame/runtime:

- state vector and gates: QRNG, AI, transducer, direct framebuffer reference
- gate fusion: batched AI/transducer/visibility circuits once QGE has circuit descriptors
- Metal/GPU: DWT, Grover batch, dense probability extraction
- Grover: visibility set and candidate entity searches
- MPS/CA-MPS/TDVP: projectile fields, particle fields, temporal media state
- Clifford/Pauli-frame: many-entity stochastic updates, impact noise, monster coordination
- noise models: optional uncertainty effects and diagnostics
- ZNE/mitigation: offline/diagnostic parity confidence, not a per-frame requirement

Research/lab/demo layer:

- QGT/topology: material/topological field analysis, teleporter/liquid field demos, documentation figures
- Quantum Volume: benchmark menu and CI performance artifact
- Shor/PQC: Moonlab capability demo and QRNG/PQC story, not core gameplay
- VQE/QAOA/QPE: offline demos and possible encoder tuning experiments

This prevents fake integration: not every Moonlab module belongs in the render loop, but every major capability has a runtime, tool, or research surface.

## 13. Tooling And Telemetry

Every harness should emit machine-readable lines in addition to human logs.

Required counters:

- render: submitted surfaces, encoded surfaces, material/textured/lightmapped counts, aliases, sprites, particles, UI draws, coefficients, nonzero pixels, GL errors, backend time
- visibility: total surfaces, candidates, accepted, false positives, false negatives, oracle time, Grover time
- physics: tracked, projectiles, impacts, active, purges, average/max shadow error, authoritative fallbacks
- audio: device, source count, processed blocks, dry/wet mix, clipping, transducer time
- RNG: entropy draws by domain, QRNG refill count, replay trace misses
- AI: decisions, action distribution, measured action, illegal-action fallbacks
- memory: dense state allocations, sparse buffer sizes, peak resident set where available

Harnesses:

- `make test`
- syntax checks for tools
- windowed one-frame render stream
- multi-frame crash watcher
- SDL dummy-audio stream
- real-audio manual run command
- pixel-diff capture with classic/QGE paired screenshots
- replay trace runner
- long e1m1/e1m2 soak

## 14. Testing Gates

Unit tests:

- QGE world registry ID stability
- texture/lightmap encoders
- DWT coefficient layout and reconstruction
- entity/model projection math
- visibility oracle parity on synthetic maps
- physics registry lifecycle
- entropy broker replay
- per-source audio processing with nonzero output

Integration tests:

- map load registers expected counts
- e1m1 visible surface parity
- `quantum_render 2` produces nonblank primary framebuffer with classic world hidden
- projectiles shadow error remains under threshold
- authoritative projectile mode can fire rockets/nails without desync
- `snd_quantum 2` processes active sources and preserves dry fallback
- demo replay with trace is deterministic

Performance gates:

- no dense 28-qubit state allocated in sparse render mode
- startup memory remains bounded
- per-frame QGE render time budget declared and tracked
- no unbounded per-frame allocation in render/audio/physics hot paths
- fallback on backend failure is explicit and logged

## 15. Migration Sequence

### Milestone 0: Plan And Controls

- Commit this architecture doc.
- Normalize cvar semantics.
- Add trace IDs to existing telemetry.
- Keep current harnesses green.

Exit: docs and controls match current code; `make test` and one-frame harness pass.

### Milestone 1: Registries And Snapshot

- Add `qge_world_t` and stable resource IDs.
- Register BSP surfaces, textures, lightmaps, alias models, sprites, HUD assets, sounds.
- Add `qge_frame_snapshot_t`.
- Move current world-surface submit through the snapshot.

Exit: map load prints registry counts; frame snapshot drives current sparse DWT path.

### Milestone 2: Texture/Lightmap World Renderer

- Cache texture and lightmap wavelet pyramids.
- Replace surface rectangles with polygon-aware world coefficients.
- Add RGB/YCoCg channels, fullbright masks, dynamic lights, sky/water/warp handling.

Exit: `quantum_render 2` renders recognizable textured e1m1 world without classic world draw.

### Milestone 3: Entities, Sprites, Viewmodel, UI

- Add alias model encoder.
- Add sprite encoder.
- Add QGE particle scene integration.
- Add viewmodel and HUD/console/menu encoders.

Exit: e1m1 is playable with QGE primary framebuffer and classic 3D/2D draws hidden.

### Milestone 4: Visibility Ownership

- Register full BSP visibility data.
- Implement Grover/batch visible-set generation.
- Add parity telemetry.
- Enable `quantum_vis 2` for QGE render path.

Exit: no false negatives in harness maps; visible set comes from QGE with fallback.

### Milestone 5: Projectile Authority

- Complete physics registry fields.
- Add QGE projectile family evolution.
- Warmup shadow mode and thresholds.
- Enable authoritative nails/rockets first.

Exit: firing tests pass with `quantum_physics_authoritative 1`; fallback reasons are logged.

### Milestone 6: Particle Ownership

- Convert classic particle events into QGE events.
- Render particles through the scene graph.
- Use MPS/CA-MPS/Pauli-frame paths where they beat dense state.

Exit: explosions/trails/blood/bubbles are present without classic particle draw.

### Milestone 7: Per-Source Audio

- Register sound assets.
- Add per-source transducers.
- Process ambient/music blocks.
- Keep post-mix safety limiter.

Exit: `snd_quantum 2` shows source telemetry and audible dry fallback.

### Milestone 8: AI And Entropy Replay

- Add entropy broker and replay traces.
- Add AI input/output contracts.
- Batch AI decisions.
- Add entanglement groups.

Exit: deterministic QGE replay works; `quantum_ai 2` only selects legal QuakeC actions.

### Milestone 9: Advanced Backends And Lab Surface

- Wire gate-fusion descriptors for AI/audio/visibility circuits.
- Move DWT/Grover kernels to Metal where beneficial.
- Add CA-MPS/TDVP particle/projectile paths.
- Add optional QGT/topology/material lab and Moonlab benchmark menu.
- Add probability, phase, coefficient, visibility-confidence, and entanglement overlays.
- Add trace export/import for frame-level quantum experiments.
- Prototype the first Quantum Ruleset features: projectile wave packets, entangled monster groups, and topological slipgate/rune materials.

Exit: capability matrix has live tests or documented non-runtime demos for every major Moonlab subsystem; Lab Mode can replay and inspect a captured quantum run.

### Milestone 10: Productization

- Long soak on multiple maps.
- Screenshot/audio/demo artifacts.
- Memory/performance report.
- Architecture paper outline.
- Release packaging.

Exit: complete e1m1 with QGE render, audio, RNG, visibility, particles, and projectile authority enabled.

## 16. Definition Of Done

The full port is done when:

- `quantum_render 2` produces the full game frame with classic GL draw hidden.
- `quantum_vis 2` supplies the QGE render visible set and parity telemetry stays clean.
- `snd_quantum 2` processes active sources and remains audible with dry fallback.
- `quantum_physics_authoritative 1` owns at least nails, rockets, and grenades safely.
- `quantum_particles 2` owns classic particle events.
- `quantum_rng 1` is live and `quantum_rng 2` can replay traces deterministically.
- `quantum_ai 2` selects legal monster actions through an explicit protocol.
- All authoritative modes have fallback paths and log fallback reasons.
- No sparse/default mode allocates dense 28-qubit frame states.
- Harnesses cover render, audio, physics, visibility, RNG replay, and crash soak.
- Moonlab capability use is honest: each major subsystem is either in a runtime path, a tested tool path, or an explicit research/demo surface.
- Quantum Faithful mode is recognizably Quake but QGE-owned.
- Lab Mode exposes probability/phase/coefficient/measurement state directly.
- Quantum Ruleset mode has at least one shipped mechanic each for projectile superposition, entangled AI behavior, and topology/material-driven fields.
