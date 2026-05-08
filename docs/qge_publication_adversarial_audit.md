# QGE Publication Adversarial Audit

Status: drafted 2026-05-07 after the finite-shot render-gate slice; refreshed
2026-05-08 after the publication artifact pack, scene-oracle export,
light-transport QAE benchmark, fallback cleanup, and backend gate.

Verdict: the current architecture can support a research-grade systems paper
only if the claim is narrowed to a reproducible hybrid quantum-rendering
testbed with explicit traces, bounded simulated-QPU kernels, and honest
classical input/readout accounting. It does not yet support an end-to-end
"quantum renderer" or "quantum advantage" claim.

## Defensible Claims Today

- QGE has an instrumented primary render path that can suppress classic 3D
  drawing and produce a QGE-owned framebuffer.
- The main render representation is sparse DWT, not a dense full-frame quantum
  state. This is honest for real-time use and is recorded as `render_sparse_dwt`.
- A bounded 6-qubit dense-state render kernel now exists and uses explicit
  gates (`H`, `RY`, `RZ`, `CNOT`, `CZ`, phase) plus finite-shot readout.
- The latest trace smoke records the render gate kernel as:
  `dense_state`, `basis=64`, `qubits=6`, `gates=26`, `shots=64`.
- The trace runtime records domains, representations, measurements, probes,
  entropy events, fallbacks, and entanglement edges through a common contract.
- QGE now has a reproducible publication pack that bundles vanilla conformance
  captures, agent media stream artifacts, scene-oracle IR, claims evidence,
  advantage-benchmark metrics, circuit output, source documents, and ICC
  completion evidence.
- The scene-oracle exporter emits `oracle_scene.json`, `claims_evidence.json`,
  and `qge_icc_evidence.json` sidecars for captured Quake-derived workloads.
- The light-transport benchmark evaluates a bounded soft-shadow visibility
  observable with classical MC, stratified sampling, and a finite-shot MLAE
  simulator under an explicit oracle/input/readout model.
- The backend selection path is now explicit in the QGE API and logs both the
  selected backend capability and whether acceleration is active for the live
  context. A Metal-capable host is no longer reported as actively accelerated
  unless a GPU context has been initialized for that runtime path.

## Claims That Would Fail Review

### End-to-end quantum rendering

The visible frame is not prepared, evolved, and read out as a hardware-plausible
full-frame quantum image. The live path encodes classical rasterized geometry
into sparse coefficient buffers, reconstructs with classical arrays, and blits
a classical RGB texture. That is acceptable if presented as a hybrid
transform-domain renderer; it is not acceptable if presented as "the frame is
rendered by a quantum computer."

Relevant code:

- `quake/Quake/qge_hooks.c`: `QGE_EncodeScene` rasterizes surfaces into RGB
  spatial fields before DWT encoding.
- `qge/qge_render.c`: dense DWT state allocation is disabled for high-qubit
  real-time paths; sparse active coefficient extraction is the default.

### Quantum advantage

There is now an executable light-transport benchmark with classical baselines
and finite-shot QAE-style estimates, but it does not prove practical renderer
speedup, hardware advantage, or full-frame quantum rendering. Current smoke and
benchmark evidence prove traceability, artifact completeness, and benchmark
execution under an explicit oracle model.

Minimum missing evidence for stronger advantage language:

- runtime and quality curves versus classic Quake and classical DWT baselines
- ablation with `quantum_render_gate_kernel 0`
- matched visual metrics: PSNR/SSIM/LPIPS/edge energy against a classic reference
- gate/shot/depth scaling under varied scene complexity and resolution
- confidence intervals over multiple seeds and maps

### Hardware plausibility of full-frame readout

The literature is clear that quantum image encodings save representation space
only under strong assumptions, while state preparation and classical readout are
dominant costs. QGE currently avoids this by using sparse simulator-backed
buffers, but the paper must say that explicitly.

Relevant literature:

- FRQI stores color and position in a normalized quantum state and demonstrates
  image operations, but retrieval is probabilistic and preparation/readout
  matter: https://link.springer.com/article/10.1007/s11128-010-0177-y
- NEQR improves accurate retrieval by storing grayscale in basis states, but
  uses more qubits: https://link.springer.com/article/10.1007/s11128-013-0567-z
- QPIXL unifies quantum pixel representations and highlights the FRQI/NEQR
  measurement-versus-qubit tradeoff:
  https://www.nature.com/articles/s41598-022-11024-y
- qRAM is a nontrivial classical-to-quantum interface, not a free primitive:
  https://arxiv.org/abs/0807.4994 and
  https://www.nature.com/articles/s41534-024-00848-3

### Misuse of "quantum signal processing"

Low/Chuang QSP is a specific eigenvalue-transformation/Hamiltonian-simulation
methodology. The current QGE renderer is quantum image/signal processing in the
broader sense, plus a small variational-style render observable. It should not
claim Low/Chuang QSP unless we implement a concrete block-encoded operator and
polynomial transformation.

Reference: https://arxiv.org/abs/1606.02685

### Quantum convolution/filtering claims

Any claim that texture filtering, lightmap convolution, or image correlation is
performed by direct componentwise multiplication of arbitrary quantum
amplitudes is unsafe. Lomont's critique is directly relevant:
https://arxiv.org/abs/quant-ph/0309070

## Reviewer Attack Surface

1. "This is a classical renderer with quantum-themed telemetry."

   Response required: isolate the exact QPU-style kernel, show its circuit,
   input features, output observable, shot noise, and effect on the frame.
   Do not blur it with the sparse-DWT classical reconstruction path.

2. "The dense 6-qubit circuit is too small to matter."

   Response required: frame it as a bounded observable kernel. Then add a
   scaling study from 4/6/8/10 qubits and prove the observable improves a
   measurable render property under finite-shot noise.

3. "The data-loading problem invalidates the quantum speedup story."

   Response required: add explicit `input_cost` telemetry for samples,
   surfaces, texture/lightmap samples, coefficient writes, and any qRAM
   assumption. Do not claim exponential speedup for classical-frame ingestion.

4. "The readout problem invalidates full-frame recovery."

   Response required: move the research contribution toward observable
   prediction: edge energy, visibility confidence, coefficient-band energy,
   material phase, depth occupancy. Classical shadows are a better model than
   full-state dumping: https://www.nature.com/articles/s41567-020-0932-7

5. "Fallbacks and synthetic paths hide the real behavior."

   Current response: the known generic fallback/stub false positives have been
   cleaned up or fenced, `condump.txt` has an artifact validator, and backend
   selection is explicit. Continue requiring every production fallback to be
   trace-recorded with reason, domain, and representation.

6. "The visual output is not yet media-grade."

   Response required: continue geometry, lighting, aliasing, HUD, sprites,
   particles, transparency, water/sky, and tone mapping until a frame can be
   compared quantitatively to a classic reference.

## What Would Be Novel If Done Correctly

The strongest publishable angle is not "Quake on a quantum computer." It is:

> A reproducible real-time game-engine testbed for hybrid quantum media
> processing, with trace contracts that expose encoding basis, qubits,
> classical input cost, transform-domain sparsity, explicit gate kernels,
> finite-shot observables, ownership, fallbacks, and visual reconstruction
> metrics.

That is plausibly beyond much of the existing quantum image-processing
literature, because most papers operate on small static images or abstract
circuits. QGE can contribute dynamic, frame-by-frame, asset-backed, interactive
workloads with adversarial runtime traces.

## Required Next Slices

### 1. Claims ledger and trace schema

Status: v0 exists and is exercised by the publication pack.

Continue expanding explicit per-probe fields or companion records for:

- `encoding`: sparse_dwt, dense_state, classical_oracle, sampled_observable
- `input_cost`: surfaces, vertices, texture samples, lightmap samples,
  coefficient writes
- `transform_cost`: DWT levels, permutation/routing estimates, gate counts
- `readout`: simulator_direct, finite_shot, replay, classical_shadow, fallback
- `shots`, `shot_error`, `seed`, `replay_id`
- `baseline_id` and `reconstruction_metrics`

### 2. Baseline harness

Status: partially complete. The QAE benchmark has MC, stratified, and
finite-shot MLAE comparisons. Renderer-facing gate-off/gate-on and visual
quality comparisons still need more coverage.

Capture matched frames for:

- classic Quake
- QGE sparse DWT without gate kernel
- QGE sparse DWT with finite-shot gate kernel
- optional dense/small-reference mode

Compute PSNR, SSIM, edge-energy drift, hole count, coefficient-band energy,
frame time, and trace totals.

### 3. Gate-kernel escalation

Move from one hand-tuned observable to a family of publishable kernels:

- edge-preservation observable
- material/lighting phase observable
- visibility-confidence observable
- coefficient-band pruning observable

Each needs a circuit diagram, gate count, qubit count, shots, and ablation.

### 4. Shadow/tomography-style observables

Use classical-shadow-inspired probes for properties instead of full-frame
readout. Candidate properties:

- high-frequency DWT band energy
- edge occupancy by depth slice
- visibility-set stability
- material transition probability
- sprite/viewmodel occupancy

### 5. Fallback audit

Status: improved. ICC no longer reports unmarked production stub/fallback paths
for the current deep-audit readiness target.

Turn every production fallback into a trace event. No silent fallback should be
allowed in a publication smoke.

### 6. Literature boundary

Keep these terms precise:

- "quantum image processing": acceptable for the broad sparse/image-transform
  context
- "quantum wavelet transform": acceptable only when discussing circuit-level
  wavelet transforms or the DWT representation with caveats
- "quantum signal processing": reserve for Low/Chuang/QSVT-style operator
  transforms unless explicitly qualified
- "simulated QPU observable": accurate for the current render gate kernel
- "quantum advantage": not yet supported

## Immediate Go/No-Go

No-go for a top-tier quantum-computing publication today.

Potential go for a systems/workshop artifact or short paper now if the claims
stay narrow: reproducible hybrid quantum-media testbed, bounded simulated-QPU
observable, scene-oracle IR, ICC-evaluable evidence, and explicit no-advantage
caveats.

Potential go for a fuller systems/workshop paper after:

- baseline harness
- metrics table over multiple maps/seeds
- broader fallback-free trace contract
- circuit diagram and ablation for the finite-shot render observable
- precise claims that avoid quantum-advantage language

Potential go for a stronger research paper after:

- multiple bounded observables with measurable visual or runtime benefit
- explicit input/readout cost accounting
- hardware-backend or noise-model experiments
- shadow-style property prediction
- release-quality reproducibility scripts and artifact package
