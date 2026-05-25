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
`diagnostics/publication_pack/20260525-route-authority-gate`. It packages a ready e1m1
QGE/vanilla capture, vanilla ICC evidence sidecar, agent stream, oracle scene,
claims evidence, finite-shot QAE benchmark artifacts,
`resource/qge_resource_envelope.json`,
`resource/qge_full_game_map_coverage.json`,
`resource/qge_asset_inventory.json`,
`resource/qge_asset_requirements.json`,
`resource/qge_moonlab_full_game_plan.json`,
`resource/qge_native_backend_boundary.json`,
`resource/qge_moonlab_job_specs.json`,
`resource/qge_moonlab_job_results.json`,
`resource/qge_moonlab_replay_plan.json`,
`resource/qge_moonlab_submission_packet.json`,
`advantage/qae_moonlab_payload.json`,
`advantage/moonlab_qae_circuits/*.moonlab`,
`advantage/qae_moonlab_oracle_kernel.json`,
`advantage/qae_moonlab_oracle_kernel.moonlab`,
`resource/qge_moonlab_submission_bundle.json`,
`resource/qge_moonlab_hardware_record_template.json`,
`resource/qge_moonlab_hardware_submission_scope.json`,
`resource/qge_moonlab_deployment_gate.json`, and the nine-map breadth sidecar from
`diagnostics/breadth_evidence/20260523-152522`. The full-game map coverage
ledger is explicit: 9/32 canonical registered single-player maps covered, 23
missing, status `partial`. The Moonlab full-game plan records the same blocker
as a deployment ledger: covered maps have strict simulator/native evidence,
zero missing maps are locally queueable with the current assets, and 23 maps
are `blocked_asset_unavailable`. The Moonlab deployment gate records the
claim verdict in one place: status `blocked`, whole-game simulator/native
deployment claim not allowed, whole-game hardware execution not allowed,
hardware advantage not allowed, and dense 70,000-qubit state claim not
allowed. The asset requirements packet lists the exact registered
`maps/*.bsp` entries needed to turn those blockers into capture jobs without
bundling copyrighted game data, and the deployment gate now cites the
registered-asset install script plus the post-install capture queue command.
The Moonlab job results record
four completed simulator jobs, two completed native replay jobs, zero blocked
jobs, and zero hardware submissions. The runtime-backend-probe job now carries
the performance and breadth aggregate observations directly, including native
target sets, missing target sets, proof maps, event counts, nine resolved
breadth runs, and the 945 native bridge breadth count.
`tools/qge_moonlab_job_runner.py` can
regenerate the same result evidence from the job specs and emits
`QGE_MOONLAB_JOB_RESULTS` when it writes the output. With `--expect` and
`--plan-out`, the same tool compares regenerated results against the packed
expected artifact and writes a standalone replay contract; with
`--submission-out`, it also writes the deterministic hardware-candidate
handoff packet. `tools/qge_moonlab_qae_transpile.py` now emits a real
Moonlab control-plane payload for the MLAE observation/readout distribution:
four `# moonlab-circuit v1` one-qubit `RY` circuits with 384 total shots,
matching the scheduled observation probabilities. This payload is useful for
hardware shot plumbing and readout comparison. `tools/qge_moonlab_oracle_transpile.py`
now emits the next harder artifact: a 32-qubit, 7,415-gate
`# moonlab-circuit v1` reversible `Q_f` predicate kernel for the captured
Bernoulli-lift oracle. It uses Moonlab-supported `CCX`, `CNOT`, `H`, and `X`,
is 64,172
bytes, and stays under Moonlab's 4,194,304-byte control-plane body cap.
`tools/qge_moonlab_qae_observation_transpile.py` then assembles the first real
benchmark observation circuit: exact state preparation over the 234 captured
candidates, uniform threshold preparation, and inline `Q_f` for
`grover_power=0`. That Moonlab circuit is 32 qubits, 7,740 gates, 67,643
bytes, and stays under the same body cap.
`tools/qge_moonlab_qae_grover_plan.py` now assembles the exact selected
Grover schedule bodies and writes the exact per-power Moonlab circuits:
powers 0, 1, 2, and 4 all fit. The largest selected body is power 4 at
69,924 gates and 610,599 bytes, below Moonlab's current 4,194,304-byte body
cap.
`tools/qge_moonlab_submission_bundle.py` records that distinction. In the
current pack the bundle status is `ready_for_control_plane_submission`, with
`control_plane_payload_directly_executable=true` and
`oracle_kernel_directly_executable=true`, and
`qae_observation_directly_executable=true`,
`grover_schedule_directly_executable=true`, and
`hardware_submission_directly_executable=true`. The publication pack also
includes a generated hardware record template so the returned Moonlab record
has a deterministic schema, validation contract, and candidate digest before
ingestion. The QAE benchmark remains unsubmitted as a full oracle job until
Grover diffusion, full MLAE circuit assembly, Moonlab
hardware backend IDs, shot schedules, and readout metadata are recorded
separately. The post-submission return path is
`tools/qge_moonlab_hardware_ingest.py`, which requires a
`qge.moonlab_hardware_record.v0`, rejects advantage/full-game/dense state
overclaim flags, rejects placeholder shot/readout payloads, requires matching
scheduled/completed/observed shot counts plus finite numeric observations, and
emits updated job results plus a bounded hardware comparison artifact. The
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
     `diagnostics/breadth_evidence/20260525-route-authority`, which aggregates nine
     ready matrices across `start` and `e1m1` through `e1m8` with
     zero fallback, zero surrogate, zero CPU-IDWT, 945 native bridge events,
     27 backend-gate events, and 36 native backend runtime-probe events parsed
     into every matrix run, plus 9/9 route-contract-authority-ready covered
     maps and zero route-authority blockers.
   - It also emits `qge.full_game_map_coverage.v0`, currently 9/32 maps
     covered and 23 missing. A full-game map claim requires this status to be
     `complete`, not merely `qge_breadth_evidence_pack_complete`.
   - Use `tools/qge_full_game_capture_queue.py <publication_pack_or_breadth_dir>`
     to generate `qge.full_game_capture_queue.v0` and a `run_missing_maps.sh`
     harness script. The generated queue for
     `diagnostics/publication_pack/20260525-route-authority-gate` inventories local loose/Pak
     BSP assets before queuing. With the current `assets/id1/pak0.pak`, it
     reports zero locally queueable missing maps and 23 missing registered maps
     as asset-unavailable; those maps require additional registered BSP assets
     before capture. The queue now accepts assets only after the dependency-free
     BSP29 header/lump validator confirms a real Quake BSP payload. It also
     emits a route contract for every canonical registered map, and the Moonlab
     deployment plan/gate require that complete ledger, so post-asset jobs carry
     route class, episode/slot, combat/special-route requirements, and authority
     domains before they run. Breadth evidence also audits every covered matrix
     against those authority domains, and the deployment gate requires covered
     route authority to stay complete.
   - `tools/qge_asset_inventory.py --asset-root assets/id1` emits
     `qge.asset_inventory.v0` and `qge_registered_asset_inventory_complete`
     ICC evidence with PAK SHA-256 hashes, BSP validation status, invalid-BSP
     counts, and the exact available/missing map ledger. The current local
     inventory is one `pak0.pak`, 9/32 canonical maps available, 23 missing,
     zero invalid BSP entries, and no whole-game Moonlab coverage claim.
   - Use `tools/qge_registered_asset_intake.py --current-root assets/id1 --candidate <quake_install_or_pak> --discover-common --json /tmp/qge_registered_asset_intake.json --markdown /tmp/qge_registered_asset_intake.md --script-out /tmp/install_registered_assets.sh --icc-json /tmp/qge_registered_asset_intake_icc_evidence.json`
     to validate external registered asset candidates and produce a
     non-destructive copy plan. Direct install-root candidates now derive
     nested `id1` and `rerelease/id1` scan targets and record
     `candidate_scan_target_count` plus the exact target paths. The after-plan
     missing-map ledger is based on actionable copy-plan entries, with blocked
     destinations reported separately as `copy_plan_blocked_maps`. The Moonlab
     full-game deployment plan now imports that handoff and records per-map
     `asset_handoff_status`, so the post-asset plan can tell copy-plan-ready
     maps from blocked destinations and maps that still need manual licensed
     assets. The Moonlab deployment gate rejects stale plans whose handoff is
     missing or inconsistent with the intake remediation ledger, rejects plans
     whose per-map deployment rows disagree with current coverage, asset
     inventory, or canonical route contracts, and rejects stale Moonlab
     coverage-ledger job results that disagree with current coverage,
     inventory, or asset-requirements artifacts. It also rejects count-only
     Moonlab job-result ledgers and recursively rejects nested hardware
     execution, hardware advantage, or dense-state overclaim flags: every
     selected job spec must have a matching completed simulator result row with
     the required artifact evidence, and the submission packet's hardware
     candidate rows plus the hardware record template and scoped submission
     readiness artifact must match those specs/results. Any returned Moonlab
     hardware backend result row must also match that bounded packet/scope
     before the full-game deployment gate can pass, and the Moonlab source ICC
     sidecars must match the current full-game plan, submission bundle, and
     hardware-submission scope ledgers. Resource ICC sidecars must likewise
     match the current asset inventory, asset requirements, and registered
     asset-intake ledgers. Advantage/control-plane ICC sidecars must match the
     current advantage metrics plus Moonlab payload, kernel, observation, and
     Grover schedule artifacts.
   - `--discover-common` derives Steam Quake roots from `libraryfolders.vdf`
     and `appmanifest_2310.acf`, then adds GOG/Heroic-style local roots before
     scanning bounded candidate directories. The intake artifact records
     `qge.registered_asset_intake.v0`, candidate-new maps, invalid candidate
     BSPs, bounded discovery results, and no-claim posture; it does not copy or
     bundle game data by default. When discovery finds no licensed candidates,
     the JSON/ICC evidence sets `manual_registered_asset_required`, records
     `registered_asset_blocker_reason`, and the script announces
     `QGE_REGISTERED_ASSET_NO_CANDIDATES` / `no_op_blocked` before running
     verification. It also records a discovery-refresh command that rebuilds
     the intake/install script after licensed assets are installed or linked.
     `tools/qge_publication_pack.py` now writes
     the same intake ledger, Markdown, ICC evidence, and safe install script
     under `resource/`, and accepts `--registered-asset-candidate`,
     `--registered-asset-discover-root`, and
     `--registered-asset-discover-common` to preserve discovery attempts in the
     publication bundle. The generated install script verifies copied
     SHA-256s and emits a post-install `qge_full_game_capture_queue.py`
     command against the same publication pack. The Moonlab deployment gate now
     repeats the install script and post-install queue command in its summary,
     next actions, Markdown, and ICC evidence.
   - The sidecar also records per-target runtime backend proofs for
     `qge_context_get_or_create_render_acceleration`, `qge_dwt_render`, and
     `qge_metal_init_common`, including missing/native target sets and the
     count of matrix runs where all required native boundaries resolved to the
     native sparse DWT render bridge.
   - The current publication bundle carries those breadth counters directly:
     `diagnostics/publication_pack/20260525-route-authority-gate` reports
     `breadth_map_count=9`, `breadth_total_native_bridge_count=945`, and
     `breadth_total_runtime_backend_probe_event_count=36`, with
     `breadth_runtime_backend_probe_resolved_run_count=9`,
     `route_contract_authority_ready_run_count=9`, plus
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
`diagnostics/publication_pack/20260525-route-authority-gate` carries
`qge_vanilla_capture_matrix_complete`, the vanilla ICC sidecar, native backend
proofs, the agent stream, the benchmark bundle, and the nine-map breadth
sidecar. It also carries `resource/qge_resource_envelope.json`, which records
per-domain resource posture and explicitly keeps whole-game hardware execution,
hardware quantum advantage, and dense 70,000-qubit state claims out of scope,
`resource/qge_full_game_map_coverage.json`, which records the 9/32 partial
canonical map ledger,
`resource/qge_asset_inventory.json`, which records the current PAK/BSP
availability ledger,
`resource/qge_asset_requirements.json`, which lists the required registered BSP
entries still needed to unblock captures,
`resource/qge_registered_asset_intake.json`, which records the bounded local
candidate discovery attempt, zero new registered maps, the manual licensed
asset requirement, and the safe no-op install script,
`resource/qge_moonlab_full_game_plan.json`, which records the full registered
map deployment ledger and no-claim posture,
`resource/qge_moonlab_deployment_gate.json`, which records the hard
fail-closed whole-game Moonlab claim eligibility verdict,
`resource/qge_native_backend_boundary.json`, which records per-target native
bridge pass/fail evidence for the three ICC-flagged runtime boundaries,
plus `resource/qge_moonlab_job_specs.json` for selected simulator/native replay
and hardware-candidate benchmark jobs, and
`resource/qge_moonlab_job_results.json` for completed local simulator/native
replay evidence, plus `resource/qge_moonlab_replay_plan.json` for the
per-job replay/validation contract and
`resource/qge_moonlab_submission_packet.json` for the hardware-candidate
handoff contract,
`advantage/qae_moonlab_payload.json` and
`advantage/moonlab_qae_circuits/*.moonlab` for the readout-equivalent Moonlab
control-plane payload,
`advantage/qae_moonlab_oracle_kernel.json` and
`advantage/qae_moonlab_oracle_kernel.moonlab` for the reversible `Q_f`
predicate kernel,
`advantage/qae_moonlab_observation_zero.json` and
`advantage/qae_moonlab_observation_zero.moonlab` for the power-zero benchmark
observation circuit with exact candidate state preparation and inline `Q_f`,
`advantage/qae_moonlab_grover_schedule_plan.json` for exact selected Grover
power body-limit evidence,
`resource/qge_moonlab_submission_bundle.json` for the control-plane readiness
verdict, `resource/qge_moonlab_hardware_record_template.json` for the
exact no-claim hardware-return object, and
`resource/qge_moonlab_hardware_submission_scope.json` for the scoped QAE
hardware handoff verdict that intentionally excludes the full-game deployment
gate. Regenerate the submission packet
independently with
`tools/qge_moonlab_job_runner.py` when validating or re-submitting the selected
Moonlab jobs outside publication-pack assembly:
`python3 tools/qge_moonlab_job_runner.py <pack>/resource/qge_moonlab_job_specs.json --out /tmp/qge_moonlab_job_results.verify.json --expect <pack>/resource/qge_moonlab_job_results.json --plan-out /tmp/qge_moonlab_replay_plan.verify.json --submission-out /tmp/qge_moonlab_submission_packet.verify.json`.
Regenerate the Moonlab QAE readout payload with:
`python3 tools/qge_moonlab_qae_transpile.py --metrics <pack>/advantage/advantage_metrics.json --abstract-circuit <pack>/advantage/qae_circuit.txt --out /tmp/qae_moonlab_payload.json --circuit-dir /tmp/moonlab_qae_circuits --markdown /tmp/qae_moonlab_payload.md --icc-json /tmp/qae_moonlab_payload_icc_evidence.json`.
Regenerate the Moonlab QAE `Q_f` kernel with:
`python3 tools/qge_moonlab_oracle_transpile.py --metrics <pack>/advantage/advantage_metrics.json --oracle-scene <pack>/oracle/oracle_scene.json --out /tmp/qae_moonlab_oracle_kernel.json --circuit /tmp/qae_moonlab_oracle_kernel.moonlab --markdown /tmp/qae_moonlab_oracle_kernel.md --icc-json /tmp/qae_moonlab_oracle_kernel_icc_evidence.json`.
Regenerate the Moonlab QAE power-zero observation circuit with:
`python3 tools/qge_moonlab_qae_observation_transpile.py --metrics <pack>/advantage/advantage_metrics.json --oracle-scene <pack>/oracle/oracle_scene.json --out /tmp/qae_moonlab_observation_zero.json --circuit /tmp/qae_moonlab_observation_zero.moonlab --markdown /tmp/qae_moonlab_observation_zero.md --icc-json /tmp/qae_moonlab_observation_zero_icc_evidence.json`.
Regenerate the exact Moonlab QAE Grover schedule plan with:
`python3 tools/qge_moonlab_qae_grover_plan.py --metrics <pack>/advantage/advantage_metrics.json --oracle-scene <pack>/oracle/oracle_scene.json --out /tmp/qae_moonlab_grover_schedule_plan.json --markdown /tmp/qae_moonlab_grover_schedule_plan.md --icc-json /tmp/qae_moonlab_grover_schedule_plan_icc_evidence.json`.
Regenerate the control-plane readiness bundle with:
`python3 tools/qge_moonlab_submission_bundle.py <pack>/resource/qge_moonlab_submission_packet.json --out /tmp/qge_moonlab_submission_bundle.json --markdown /tmp/qge_moonlab_submission_bundle.md --icc-json /tmp/qge_moonlab_submission_bundle_icc_evidence.json`.
Regenerate the hardware-return template from the submission packet with:
`python3 tools/qge_moonlab_hardware_ingest.py <pack>/resource/qge_moonlab_submission_packet.json --template-out /tmp/qge_moonlab_hardware_record.template.json`.
Regenerate the full-game Moonlab deployment ledger with:
`python3 tools/qge_moonlab_full_game_plan.py <pack> --out /tmp/qge_moonlab_full_game_plan.json --markdown /tmp/qge_moonlab_full_game_plan.md --icc-json /tmp/qge_moonlab_full_game_plan_icc_evidence.json`.
Regenerate the deployment claim gate with:
`python3 tools/qge_moonlab_deployment_gate.py <pack> --out /tmp/qge_moonlab_deployment_gate.json --markdown /tmp/qge_moonlab_deployment_gate.md --icc-json /tmp/qge_moonlab_deployment_gate_icc_evidence.json`.
Regenerate the asset requirements packet with:
`python3 tools/qge_asset_requirements.py --asset-root assets/id1 --json /tmp/qge_asset_requirements.json --markdown /tmp/qge_asset_requirements.md --icc-json /tmp/qge_asset_requirements_icc_evidence.json`.
When Moonlab hardware returns a result, validate and merge it with:
`python3 tools/qge_moonlab_hardware_ingest.py <pack>/resource/qge_moonlab_submission_packet.json --job-results <pack>/resource/qge_moonlab_job_results.json --hardware-record qge_moonlab_hardware_record.json --out qge_moonlab_job_results.hardware.json --comparison-out qge_moonlab_hardware_comparison.json --icc-out qge_moonlab_hardware_icc_evidence.json`.

The next hard work is therefore:

1. Broaden the ready matrix beyond the current 9/32 partial full-game map
   coverage ledger, while preserving zero fallback/surrogate/CPU-IDWT counters.
   Use `tools/qge_registered_asset_intake.py` against the user's registered
   Quake install or PAKs, run the generated copy script only for assets the
   user is licensed to install locally, verify them with
   `tools/qge_asset_inventory.py`, then start from
   `tools/qge_full_game_capture_queue.py diagnostics/publication_pack/20260525-route-authority-gate`
   so the 23 registered asset-unavailable maps become explicit capture jobs
   rather than weakening the authority gate.
2. Submit the QAE hardware-candidate job through Moonlab hardware when
   available, recording backend IDs, shot schedule, readout metadata, and
   hardware-vs-simulator comparison in `qge_moonlab_job_results.json`. Use
   `qge_moonlab_submission_packet.json` as the handoff input, not the
   simulator result as a proxy for hardware execution; start from
   `qge_moonlab_hardware_record_template.json` and use
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
