# QGE Publishable Results Research

Status date: 2026-05-22.

This memo summarizes the external quantum-game landscape and the strongest
publishable path for Quantum Quake. It is intentionally conservative: the goal
is to beat prior work without overstating what Moonlab/QGE has already proven.

## External Baseline

### Quandoom

Quandoom is the closest public comparison point. Its own project page describes
it as a port of the first level of DOOM to a single QASM circuit. The reported
scale is roughly 72,000 qubits and 80 million gates, with the last 64,000
qubits measured into a 320 x 200 binary display. The author also states that no
current quantum computer can run it and that it is simulated on a classical
computer at roughly 10-20 FPS.

Important limitations from the project page and paper:

- first level only
- binary pixels rather than color
- no sound or music
- x-ray rendering from reversibility constraints
- simplified gameplay, including constrained enemy movement and hitscan imp
  fireballs
- designed to be classically simulable

The important technical critique is not that particular gates are "fake".
Hadamard, Toffoli, and T-gate decompositions are valid quantum-circuit
building blocks. The weak claim is that a 70,000+ qubit monolithic game circuit
is presented as a quantum-computer port while being intentionally structured for
classical simulation. A general 70,000-qubit dense or materially entangled state
would require an impossible `2^70000` amplitude space; laptop playback at
10-20 FPS necessarily means the simulator is exploiting restricted circuit
structure, not simulating an arbitrary quantum state at that width. A
review-safe comparison should therefore describe Quandoom as a static
gate-list/reversible-circuit game benchmark, not as evidence of a live
dense-entangled quantum game runtime.

Sources:

- https://github.com/Lumorti/Quandoom
- https://arxiv.org/abs/2412.12162

### Other Quantum-Game Work

The broader quantum-game literature is mostly educational or prototype-scale:

- Quantum Game Jam reports 68 prototypes from 2014-2019, including games about
  quantum mechanics, games for quantum research, and games utilizing quantum
  computers.
- Flying Unicorn is a small Qiskit game that discusses Grover search and
  physical IBMQ execution/performance.
- Quantum Forge is a modern quantum-mechanics game framework with web and Unity
  tooling, plus quantum-game outreach and game-jam work.

These are relevant, but they are not evidence of a full classic FPS engine being
ported into a quantum-engine authority model.

Sources:

- https://arxiv.org/abs/2408.09014
- https://arxiv.org/abs/1910.08238
- https://quantum.dev/

### Hardware Reality

Quandoom's published scale is far beyond current hardware. For context,
Quantinuum's Helios launch materials describe a 98-physical-qubit trapped-ion
commercial system, and IBM's roadmap discusses a 2029 Starling system targeting
200 logical qubits and circuits of about 100 million gates. That makes full
hardware execution of a 72,000-qubit game circuit a future-facing benchmark
claim, not a current hardware result.

Sources:

- https://www.quantinuum.com/press-releases/quantinuum-announces-commercial-launch-of-new-helios-quantum-computer-that-offers-unprecedented-accuracy-to-enable-generative-quantum-ai-genqai
- https://www.ibm.com/quantum/blog/large-scale-ftqc

## Quantum Quake Position

Quantum Quake should not compete by claiming "we also made a giant static game
circuit." The stronger claim is different:

> Quantum Quake is a live classic-FPS conformance port whose authoritative game
> domains are being moved into a Moonlab-backed QGE runtime, with per-frame
> ownership counters, traces, replay, strict fallback evidence, and classic
> Quake retained only as host/reference oracle.

This is materially different from Quandoom:

- Quandoom is a static QASM recreation of one DOOM level.
- Quantum Quake is a live QuakeSpasm/QGE runtime integration.
- Quandoom measures a binary screen from a circuit.
- Quantum Quake tracks world registry, frame snapshots, rendering, visibility,
  physics/projectiles, AI, audio, RNG, and UI/media ownership.
- Quandoom's strongest result is "DOOM as a quantum circuit."
- Quantum Quake's strongest publishable result should be "a classic FPS runtime
  ported into a Moonlab-owned game-engine authority model."

## Real Quantum Computing Bar

For Quantum Quake, "real quantum computing" must mean more than a QASM-shaped
artifact. A claimed Moonlab-owned domain needs evidence that:

- the domain uses a named Moonlab representation: small exact state vector,
  MPS/CA-MPS, Clifford/Pauli frame, Grover/search, QRNG, noise/mitigation, or a
  hardware-backed backend when available
- the trace records resource shape: qubits/registers, gates or kernel steps,
  shots, measurements, backend, fallback reason, and frame/domain ownership
- the state has quantum semantics that matter: phase, interference,
  measurement, entanglement/correlation, noise, or amplitude amplification
  changes the output or decision
- the result is not reducible to a scalar cvar, lookup table, or purely
  classical replay without losing the claimed behavior
- the host consumes the Moonlab/QGE result as authority for that domain
- the resource envelope is honest: small dense registers where dense state is
  realistic, tensor-network/sparse forms for larger correlated fields, and
  70,000-qubit dense-state fiction is forbidden

This means Quantum Quake should be built as many runtime quantum kernels and
state fields with explicit ownership, not as one enormous all-game circuit. That
is the route that can eventually deploy selected kernels to real quantum
hardware through Moonlab while preserving a full-game simulator path.

## Publishable Claim To Target

The most defensible near-term paper/demo claim is:

> We present Quantum Quake, a Moonlab-backed quantum game-engine conformance
> port of Quake, and a strict runtime ownership matrix showing which gameplay,
> rendering, media, visibility, physics, AI, RNG, and UI domains are actually
> QGE/Moonlab-owned frame by frame.

Do not claim:

- quantum advantage
- hardware execution of the whole game
- complete vanilla fidelity
- full port completion before ICC `qge_vanilla_runtime_complete` passes

Do claim, once proven:

- first evidence-backed classic FPS engine conformance port into a
  Moonlab-backed quantum game-engine authority model
- reproducible classic-vs-QGE capture matrix
- strict no-hidden-classic-output counters
- per-domain fallback accounting
- resource and trace evidence for Moonlab-compatible runtime workloads

## Required Results Package

Minimum publishable artifact package:

Current strongest publication bundle:
`diagnostics/publication_pack/20260523-162303`. It packages a ready e1m1
QGE/vanilla capture, vanilla ICC evidence sidecar, agent stream, oracle scene,
claims evidence, finite-shot QAE benchmark artifacts,
`resource/qge_resource_envelope.json`,
`resource/qge_full_game_map_coverage.json`,
`resource/qge_asset_inventory.json`,
`resource/qge_native_backend_boundary.json`,
`resource/qge_moonlab_job_specs.json`,
`resource/qge_moonlab_job_results.json`,
`resource/qge_moonlab_replay_plan.json`,
`resource/qge_moonlab_submission_packet.json`, and the nine-map breadth sidecar from
`diagnostics/breadth_evidence/20260523-152522`. The full-game map coverage
ledger is explicit: 9/32 canonical registered single-player maps covered, 23
missing, status `partial`. The Moonlab job results record
four completed simulator jobs, two completed native replay jobs, zero blocked
jobs, and zero hardware submissions; `tools/qge_moonlab_job_runner.py` can
regenerate the same result evidence from the job specs and emits
`QGE_MOONLAB_JOB_RESULTS` when it writes the output. With `--expect` and
`--plan-out`, the same tool compares regenerated results against the packed
expected artifact and writes a standalone replay contract; with
`--submission-out`, it also writes the deterministic hardware-candidate
handoff packet. The QAE benchmark remains unsubmitted until Moonlab hardware
backend IDs, shot schedules, and readout metadata are recorded separately. The
post-submission return path is `tools/qge_moonlab_hardware_ingest.py`, which
requires a `qge.moonlab_hardware_record.v0`, rejects advantage/full-game/dense
state overclaim flags, and emits updated job results plus a bounded hardware
comparison artifact. The
bundled agent stream also records host-side macOS AppKit/SDL launcher probes
and marks UI-only `-nolauncher` paths as intentional skips.

1. Strict ownership matrix
   - ICC target: `qge_vanilla_quake_conformance`
   - Required pass: `qge_vanilla_runtime_complete`
   - Evidence: `qge_vanilla_capture_matrix_complete`
   - Must show no hidden classic production authority for claimed domains.

2. Multi-run breadth evidence
   - ICC target: `qge_breadth_evidence_pack`
   - Required pass: `qge_breadth_evidence_pack_complete`
   - Evidence: aggregated `vanilla_capture_matrix.json` runs plus optional
     publication packs, with zero fallback, surrogate, and CPU-IDWT counts.
   - Publication packs should include the same breadth sidecar with
     `tools/qge_publication_pack.py --breadth-evidence <breadth_dir>` so the
     paper bundle carries the multi-map counters, native bridge events, backend
     gate events, and runtime backend probes directly.
   - For multi-map claims, run `tools/qge_breadth_evidence.py --min-maps N`
     so repeated captures of a single map cannot satisfy the breadth gate.
   - Current strongest local checkpoint:
     `diagnostics/breadth_evidence/20260523-152522`, which aggregates nine
     ready matrices across `start` and `e1m1` through `e1m8` with
     zero fallback, zero surrogate, zero CPU-IDWT, 945 native bridge events,
     27 backend-gate events, and 36 native backend runtime-probe events parsed
     into every matrix run.
   - It also emits `qge.full_game_map_coverage.v0`, currently 9/32 maps
     covered and 23 missing. A full-game map claim requires this status to be
     `complete`, not merely `qge_breadth_evidence_pack_complete`.
   - Use `tools/qge_full_game_capture_queue.py <publication_pack_or_breadth_dir>`
     to generate `qge.full_game_capture_queue.v0` and a `run_missing_maps.sh`
     harness script. The generated queue for
     `diagnostics/publication_pack/20260523-162303` inventories local loose/Pak
     BSP assets before queuing. With the current `assets/id1/pak0.pak`, it
     reports zero locally queueable missing maps and 23 missing registered maps
     as asset-unavailable; those maps require additional registered BSP assets
     before capture.
   - `tools/qge_asset_inventory.py --asset-root assets/id1` emits
     `qge.asset_inventory.v0` and `qge_registered_asset_inventory_complete`
     ICC evidence with PAK SHA-256 hashes and the exact available/missing map
     ledger. The current local inventory is one `pak0.pak`, 9/32 canonical maps
     available, 23 missing, and no whole-game Moonlab coverage claim.
   - The sidecar also records per-target runtime backend proofs for
     `qge_context_get_or_create_render_acceleration`, `qge_dwt_render`, and
     `qge_metal_init_common`, including missing/native target sets and the
     count of matrix runs where all required native boundaries resolved to the
     native sparse DWT render bridge.
   - The current publication bundle carries those breadth counters directly:
     `diagnostics/publication_pack/20260523-162303` reports
     `breadth_map_count=9`, `breadth_total_native_bridge_count=945`, and
     `breadth_total_runtime_backend_probe_event_count=36`, with
     `breadth_runtime_backend_probe_resolved_run_count=9`, plus
     `full_game_map_coverage_status=partial`.

3. Runtime traces
   - QGE trace file for each capture.
   - Runtime summaries for render, visibility, physics/projectiles, audio, AI,
     RNG, and UI/media.
   - Explicit fallback reasons for every non-owned domain.

4. Visual evidence
   - Classic reference frame set.
   - QGE/Moonlab primary framebuffer frame set.
   - Region metrics for world, upper-playfield, viewmodel, floor, walls,
     ceiling, and corridor.

5. Domain ownership table
   - render: world, textures, lightmaps, alias/viewmodel, sprites, particles,
     sky/water/warp, HUD/console/menu
   - simulation: RNG, AI decisions, projectile/physics, visibility
   - media: audio post-mix and per-source authority

6. Comparator table against Quandoom
   - level scope
   - color/audio
   - live engine integration
   - runtime authority model
   - trace/replay
   - fallback accounting
   - simulator and hardware resource envelope

## Immediate Engineering Wedge

The previous ICC blocker was:

```text
qge_vanilla_runtime_complete -> produce_ready_vanilla_capture_matrix
```

That blocker is now cleared for the current self-contained publication pack:
`diagnostics/publication_pack/20260523-162303` carries
`qge_vanilla_capture_matrix_complete`, the vanilla ICC sidecar, native backend
proofs, the agent stream, the benchmark bundle, and the nine-map breadth
sidecar. It also carries `resource/qge_resource_envelope.json`, which records
per-domain resource posture and explicitly keeps whole-game hardware execution,
hardware quantum advantage, and dense 70,000-qubit state claims out of scope,
`resource/qge_full_game_map_coverage.json`, which records the 9/32 partial
canonical map ledger,
`resource/qge_asset_inventory.json`, which records the current PAK/BSP
availability ledger,
`resource/qge_native_backend_boundary.json`, which records per-target native
bridge pass/fail evidence for the three ICC-flagged runtime boundaries,
plus `resource/qge_moonlab_job_specs.json` for selected simulator/native replay
and hardware-candidate benchmark jobs, and
`resource/qge_moonlab_job_results.json` for completed local simulator/native
replay evidence, plus `resource/qge_moonlab_replay_plan.json` for the
per-job replay/validation contract and
`resource/qge_moonlab_submission_packet.json` for the hardware-candidate
handoff contract. Regenerate the latter independently with
`tools/qge_moonlab_job_runner.py` when validating or re-submitting the selected
Moonlab jobs outside publication-pack assembly:
`python3 tools/qge_moonlab_job_runner.py <pack>/resource/qge_moonlab_job_specs.json --out /tmp/qge_moonlab_job_results.verify.json --expect <pack>/resource/qge_moonlab_job_results.json --plan-out /tmp/qge_moonlab_replay_plan.verify.json --submission-out /tmp/qge_moonlab_submission_packet.verify.json`.
When Moonlab hardware returns a result, validate and merge it with:
`python3 tools/qge_moonlab_hardware_ingest.py <pack>/resource/qge_moonlab_submission_packet.json --job-results <pack>/resource/qge_moonlab_job_results.json --hardware-record qge_moonlab_hardware_record.json --out qge_moonlab_job_results.hardware.json --comparison-out qge_moonlab_hardware_comparison.json --icc-out qge_moonlab_hardware_icc_evidence.json`.

The next hard work is therefore:

1. Broaden the ready matrix beyond the current 9/32 partial full-game map
   coverage ledger, while preserving zero fallback/surrogate/CPU-IDWT counters.
   Install the remaining registered BSP assets, verify them with
   `tools/qge_asset_inventory.py`, then start from
   `tools/qge_full_game_capture_queue.py diagnostics/publication_pack/20260523-162303`
   so the 23 registered asset-unavailable maps become explicit capture jobs
   rather than weakening the authority gate.
2. Submit the QAE hardware-candidate job through Moonlab hardware when
   available, recording backend IDs, shot schedule, readout metadata, and
   hardware-vs-simulator comparison in `qge_moonlab_job_results.json`. Use
   `qge_moonlab_submission_packet.json` as the handoff input, not the
   simulator result as a proxy for hardware execution; use
   `tools/qge_moonlab_hardware_ingest.py` to merge the returned record.
3. Improve renderer fidelity enough that the QGE primary framebuffer is not
   only owned, but inspectably close to vanilla Quake on fixed-view and
   autonomous captures.
4. Keep the historical blocked check available when rebuilding evidence:

```sh
/Users/tyr/Desktop/infinite_context_coder/bin/icc completion-oracle \
  --repo quantum_quake \
  --target qge_vanilla_quake_conformance \
  --trace-dir diagnostics/quake_graphics/<capture> \
  --format markdown
```

5. Only after the oracle passes, write the paper/demo abstract.

## Paper Shape

Working title:

```text
Quantum Quake: A Moonlab-Owned Runtime Authority Model for a Classic FPS
```

Core sections:

- Prior work: Quandoom and quantum game prototypes.
- System: Quake host, QGE authority layer, Moonlab runtime, trace/replay.
- Ownership matrix: how each domain is proven or blocked.
- Rendering case study: fixed-view world/viewmodel conformance metrics.
- Runtime case studies: RNG, visibility, projectile authority gates, audio.
- Resource model: qubits/gates/shots/backend requirements per domain.
- Limitations: no hardware full-game claim, no quantum advantage claim, vanilla
  fidelity incomplete, and captured-workload readiness is not all-map/full-game
  visual completion.

This is how Quantum Quake can beat Quandoom honestly: not by being a larger
novelty circuit, but by becoming the first evidence-backed classic FPS runtime
whose game authority is systematically moved into a Moonlab-backed quantum game
engine.
