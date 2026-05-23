# QGE Quantum Advantage Research Roadmap

Status: drafted 2026-05-07; evidence status refreshed 2026-05-08.

Goal: identify what Quantum Quake would need in order to credibly demonstrate
some form of quantum advantage, while avoiding weak or easily attacked claims.

## Bottom Line

The most credible route is not whole-frame quantum rendering. The strongest
route is a bounded rendering subproblem where the classical workload is
query-limited or sample-limited:

1. **Quantum amplitude estimation for light transport / supersampling**
2. **Grover or minimum-finding style visibility/intersection search**
3. **Quantum ray marching / quantum random-walk light transport as a lab mode**
4. **QSP/QSVT-style operator transforms only after we define real block
   encodings**

The first executable version of that target now exists as the QGE
light-transport QAE benchmark. It consumes a scene-oracle sidecar, compares
plain Monte Carlo and stratified baselines with a finite-shot MLAE simulator,
and emits metrics, circuit, scaling, and ICC evidence artifacts. That is a
defensible benchmark artifact, not a practical rendering-speedup claim.

## Advantage Claim Ladder

### Level 0: Feasibility

Claim: a real-time game engine can host bounded simulated-QPU observables with
traceable gates, shots, and render effects.

Current status: demonstrated as a bounded simulated-QPU observable by
`render_gate_kernel`, with trace-side qubits, gates, shots, and finite-shot
readout.

Evidence needed:

- explicit circuit artifact
- trace with qubits/gates/shots/readout
- controlled gate-off/gate-on deltas
- no silent fallback

### Level 1: Query Advantage

Claim: for a formally defined oracle problem, QGE's quantum kernel uses fewer
oracle queries than the matching classical algorithm.

Good target:

- find visible/intersected/occluding primitive among `N` candidates
- estimate first hit or any-hit for broadphase candidates
- locate high-contribution light path among candidate paths

Review risk:

- Grover gives `O(sqrt(N))` over unstructured search, but real ray tracers use
  BVHs/BSPs/grids. We cannot compare against naive `O(N)` and call it a
  graphics advantage.

Requirement:

- define exactly when the candidate set is unstructured or adversarial enough
  that a classical acceleration structure does not erase the benefit.

### Level 2: Sample-Complexity Advantage

Claim: for an observable such as pixel luminance, patch irradiance, soft-shadow
visibility, or indirect-light contribution, QGE can evaluate the query model
needed to study amplitude-estimation scaling against classical Monte Carlo.

This remains the strongest near-term path. The current artifact proves the
benchmark harness and cost accounting exist, but it does not yet justify
language stronger than "evaluates" or "studies" quantum query scaling.

Formal problem:

- Let `x` be a sampled path, ray, light point, subpixel, or visibility event.
- Let `f(x) in [0, 1]` be its contribution to a bounded render observable.
- Classical Monte Carlo estimates `mu = E[f(x)]` with delta scaling
  `O(1 / sqrt(M))`.
- Quantum amplitude estimation estimates the same mean with ideal query scaling
  `O(1 / M)` or `O(1 / epsilon)` under a coherent sampler and oracle.

What QGE must build:

- coherent path/sample preparation for a small Quake scene
- reversible/bounded contribution oracle
- amplitude-estimation circuit or faithful simulator
- matching classical MC estimator
- delta-versus-oracle-call plots over multiple seeds and scene settings

Current artifact status:

- `tools/qge_oracle_export.py` emits `oracle_scene.json`,
  `claims_evidence.json`, and `qge_icc_evidence.json`.
- `tools/qge_advantage_benchmark.py` emits `advantage_metrics.json`,
  `scaling_summary.json`, `qae_curve.csv`, `qae_circuit.txt`, and
  `qge_advantage_icc_evidence.json`.
- The publication pack at
  `diagnostics/publication_pack/20260523-162303/` bundles the benchmark,
  oracle, trace, stream, vanilla, vanilla ICC evidence sidecar, claims, source
  artifacts, `resource/qge_resource_envelope.json`,
  `resource/qge_full_game_map_coverage.json`,
  `resource/qge_asset_inventory.json`,
  `resource/qge_native_backend_boundary.json`,
  `resource/qge_moonlab_job_specs.json`,
  `resource/qge_moonlab_job_results.json`,
  `resource/qge_moonlab_replay_plan.json`,
  `resource/qge_moonlab_submission_packet.json`, and the nine-map breadth
  evidence sidecar with per-target native backend proof maps. The map coverage
  artifact is `partial`: 9/32 canonical registered single-player maps covered
  and 23 pending. The current local asset inventory has zero locally runnable
  missing maps; 23 registered maps require additional registered BSP assets. Its agent stream
  also carries macOS AppKit/SDL launcher probes,
  including intentional
  `-nolauncher` skips for UI-only launcher controls. A real hardware return
  should be merged with `tools/qge_moonlab_hardware_ingest.py`, which records a
  bounded hardware comparison while keeping hardware advantage and whole-game
  hardware claims false.
- Current metrics are evidence for a reproducible QAE-style benchmark under an
  explicit oracle model, not evidence for hardware advantage or end-to-end
  renderer acceleration.

### Level 3: Practical Simulator Advantage

Claim: on a simulator or hybrid runtime, QGE beats a matching classical
baseline for a constrained benchmark.

This is harder than Level 2 because statevector simulation is expensive and can
erase algorithmic gains. It may still be possible for small scene/operator
families if the classical baseline is also constrained, but this is not the
main paper claim to chase first.

### Level 4: Hardware Advantage

Claim: a QPU-backed implementation beats a classical system on wall clock,
energy, or accuracy for a useful render task.

Current status: not realistic until we have resource estimates, a coherent
input model, noise analysis, and likely fault-tolerant assumptions.

## Literature Anchors

### Amplitude Estimation / Quantum Monte Carlo

- Brassard, Hoyer, Mosca, Tapp introduced quantum amplitude amplification and
  estimation: https://arxiv.org/abs/quant-ph/0005055
- Montanaro showed a broad quantum speedup of Monte Carlo methods:
  https://royalsocietypublishing.org/doi/10.1098/rspa.2015.0301
- Iterative/amplitude-estimation variants reduce some phase-estimation burden
  and are better suited to near-term experiments:
  https://arxiv.org/abs/1904.10246

Implication for QGE: light transport, soft shadows, stochastic supersampling,
and indirect-light probes are the best candidates because rendering already
uses Monte Carlo estimators.

### Quantum Rendering / Ray Tracing

- "Towards Quantum Ray Tracing" studies quantum ray tracing and discusses
  Grover-style query improvements for ray-tracing tasks:
  https://arxiv.org/abs/2204.12797
- "Quantum Ray Marching for Reformulating Light Transport Simulation" is a
  recent graphics-facing attempt to recast light transport with quantum random
  walks and quantum numerical integration:
  https://about.roblox.com/publications/quantum-ray-marching-for-reformulating-light-transport-simulation

Implication for QGE: the field is young. A Quake-backed benchmark with
reproducible dynamic scenes could be more compelling than another tiny static
image circuit, but only if the baseline and cost model are rigorous.

### Input Models / qRAM / Dequantization Risk

- qRAM can address superposed memory locations, but it is an architecture with
  cost and physical assumptions, not a free loader:
  https://arxiv.org/abs/0807.4994
- Modern work continues to emphasize qRAM implementation constraints:
  https://www.nature.com/articles/s41534-024-00848-3
- Quantum-inspired classical algorithms and "fine print" critiques show that
  hidden input assumptions can erase claimed QML-style advantages.

Implication for QGE: every advantage claim must report input cost. A reviewer
will reject "log qubits for a million pixels" unless we account for preparing
or querying those pixels.

### Readout / Observable Extraction

- Classical shadows show how to predict many chosen observables with fewer
  measurements than full tomography:
  https://www.nature.com/articles/s41567-020-0932-7

Implication for QGE: advantage claims should target observables such as edge
energy, light contribution, visibility probability, or coefficient-band energy.
Do not target full-frame readout first.

### QSP / QSVT

- Low/Chuang QSP and qubitization:
  https://arxiv.org/abs/1606.02685
  https://quantum-journal.org/papers/q-2019-07-12-163/
- QSVT unifies many quantum algorithms through block-encoded operator
  transformations:
  https://arxiv.org/abs/1806.01838

Implication for QGE: this is the long-term foundation for material, visibility,
or transport-operator kernels. We should not claim QSP/QSVT until we define a
real block encoding and polynomial transform.

## Best Advantage Demonstration for Quantum Quake

### Benchmark: Quantum Light-Transport Mean Estimation

Define a controlled Quake scene with:

- fixed camera path
- fixed map and asset hash
- one or more area lights
- optional mirror/portal/water/material events later
- a patch or pixel group whose luminance is estimated by stochastic samples

Classical baseline:

- plain Monte Carlo
- stratified/Sobol sampling
- optional path-guided baseline for honesty

Quantum kernel:

- coherent sampler over light points, subpixels, or path choices
- contribution oracle `f(x)` normalized to `[0, 1]`
- amplitude estimation to estimate mean contribution
- finite-shot/noisy variants

Primary plot:

- mean absolute delta or RMSE versus oracle evaluations
- classical slope near `M^-1/2`
- quantum-estimation slope closer to `M^-1` in the ideal oracle model

Required trace fields:

- `advantage_problem_id`
- `oracle_kind`
- `oracle_eval_count`
- `classical_eval_count`
- `state_prep_cost`
- `qram_assumption`
- `circuit_depth`
- `one_qubit_gates`
- `two_qubit_gates`
- `controlled_oracle_calls`
- `shots`
- `epsilon_target`
- `confidence`
- `observable`
- `reference_value`
- `absolute_delta`
- `rmse`
- `seed`

Publication-safe claim:

> On a Quake-derived light-transport observable, the QGE amplitude-estimation
> lab mode demonstrates the expected quantum query/sample-complexity scaling
> under an explicit oracle/input model, while the real-time renderer uses the
> resulting bounded observables in a hybrid sparse-DWT media pipeline.

## Second Advantage Route: Visibility / Intersection Search

Target:

- any-hit visibility among many candidate surfaces
- first relevant occluder under an adversarial or unstructured candidate list
- high-contribution candidate path among many generated options

Quantum kernel:

- predicate oracle marks candidates satisfying hit/visibility/contribution
- Grover/amplitude amplification locates marked candidates
- Durr-Hoyer minimum finding can target nearest intersection if distance is
  oracle-comparable

Risk:

- Quake BSP already gives strong classical structure. A reviewer will reject
  "Grover beats linear search" if an optimized BSP/BVH baseline is omitted.

Good use:

- broadphase candidate lists generated by dynamic effects
- visibility over stochastic light-path candidates
- unstructured material/portal event search
- offline benchmark mode, not core rasterization

## Third Advantage Route: Quantum Ray Marching Lab Mode

Target:

- voxel/SDF conversion of a Quake room
- quantum random-walk/ray-marching estimator for a small light-transport task
- compare to classical ray marching and Monte Carlo under matched assumptions

Why it matters:

- this aligns with emerging quantum-rendering literature more directly than
  sparse-DWT framebuffer reconstruction
- it is likely more publishable as a "beyond feasibility" experiment

Risk:

- implementation difficulty is high
- advantage depends heavily on the oracle and memory model
- may not be real-time

## Fourth Route: QSVT/QSP Operator Kernels

Possible operators:

- visibility adjacency matrix
- material transition operator
- transport/occlusion operator over patches
- DWT coefficient-band operator

Possible transforms:

- threshold visibility confidence
- amplify high-frequency seam/edge components
- suppress noisy low-contribution bands
- estimate spectral properties of transport graph

Requirement:

- formal sparse/block encoding
- polynomial transform specification
- circuit/resource estimate
- classical baseline

This is the strongest theoretical route, but it requires much more math before
implementation.

## Implementation Plan

### Slice 1: Advantage Claims Ledger

Status: v0 exists at `docs/claims/qge_claims.json`.

Maintain the machine-readable ledger:

- claim id
- problem statement
- input model
- output observable
- allowed assumptions
- classical baseline
- quantum algorithm
- accepted evidence
- disallowed wording

### Slice 2: Baseline and Metrics Harness

Status: partially implemented.

Present in v0:

- `tools/qge_advantage_benchmark.py`
- classical MC, stratified low-discrepancy, and finite-shot MLAE simulator
  comparisons
- `advantage_metrics.json`, `scaling_summary.json`, `qae_curve.csv`, and
  circuit artifact output

Still needed for stronger renderer claims:

- classic/QGE/gate-off/gate-on capture modes
- controlled camera/seed/map runner
- PSNR/SSIM/edge-energy/hole metrics
- trace aggregation into `publication_metrics.json`

This does not prove advantage, but it is required before advantage work is
credible.

### Slice 3: Oracle Cost Trace Schema

Status: sidecar v0 exists for the QAE benchmark.

Continue extending traces or companion records for:

- oracle calls
- state preparation
- input samples
- readout samples
- qRAM assumptions
- circuit depth
- baseline algorithm id
- delta and confidence

### Slice 4: Amplitude Estimation Module

Status: v0 exists as a finite-shot MLAE simulator. Continue hardening it with:

- Bernoulli/amplitude oracle tests
- mean-estimation harness
- classical MC comparator
- iterative amplitude estimation or maximum-likelihood amplitude estimation
- JSON/trace output

### Slice 5: Quake Light Observable

Status: v0 exists for `light_transport.soft_shadow_visibility`. Remaining
work:

- patch irradiance or soft-shadow estimator
- controlled area-light samples
- reference value from high-sample classical integration
- QAE simulator estimate
- MC baseline estimate

### Slice 6: Query Search Workload

Implement a visibility/intersection search benchmark with:

- naive baseline
- BSP/BVH baseline
- Grover-query count model
- explicit statement of where advantage survives or disappears

### Slice 7: Resource Estimator

For every circuit:

- logical qubits
- gates by type
- depth
- controlled oracle calls
- T-count/T-depth estimate where possible
- shots
- noise sensitivity
- physical qubit estimates for one or two target assumptions

## Go / No-Go Criteria

No-go for quantum advantage language if:

- the baseline is naive while optimized classical structures exist
- state-preparation or qRAM cost is omitted
- the result is a full-frame readout claim
- only wall-clock statevector simulation is measured
- visual output changes but the quantum observable has no ablation evidence

Go for query/sample-complexity advantage language if:

- the problem is formally defined
- the classical baseline is matched and strong
- the oracle/input model is explicit
- traces record oracle calls, circuit depth, shots, and readout
- plots show the expected scaling over enough problem sizes
- the paper states the assumptions clearly

Go for a major systems claim if:

- QGE provides dynamic Quake scenes as benchmark workloads
- all traces and frames are reproducible
- multiple quantum kernels are implemented as bounded observables
- the artifact includes baselines, metrics, circuits, and resource estimates

## Strategic Recommendation

Build toward this thesis:

> Quantum Quake is a reproducible benchmark and systems architecture for
> quantum-enhanced interactive media. It demonstrates real-time feasibility with
> bounded simulated-QPU observables, and it provides Quake-derived
> light-transport and visibility workloads where quantum algorithms can be
> evaluated for query/sample-complexity advantage under explicit input and
> readout models.

That is much stronger than claiming a quantum framebuffer, and it is more likely
to survive adversarial review.
