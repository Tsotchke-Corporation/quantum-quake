# QGE Quantum Signal Processing Research Notes

Status: collected 2026-05-07 during the QGE render fidelity pass.

Scope: this note collects literature relevant to QGE's sparse-DWT render path,
state-preparation/readout claims, and the current geometry artifacts. It separates
"quantum signal processing" in the Low/Chuang QSP sense from the broader quantum
image/signal-processing literature, because the render tearing issue maps more
directly to quantum image representation, resampling, interpolation, and
measurement reconstruction.

## Working Conclusions

- The literature has dealt with problems adjacent to our tearing/artifact issue,
  but mostly as representation, sampling, interpolation, aliasing, state
  preparation, and readout problems. It does not treat game-raster tearing as a
  first-class quantum graphics problem.
- QGE should keep the renderer honest as a sparse signal reconstruction pipeline:
  explicit geometry coverage first, then DWT/frequency filtering, then measured
  output/trace summaries. Do not hide geometry cracks with color grading.
- Full-frame quantum readout is the wrong QPU claim. Papers repeatedly show that
  compact encodings are attractive, but loading classical pixels and retrieving a
  whole classical image dominate practical cost.
- Publishable QGE traces should report the same budgets the literature worries
  about: basis count, qubit count, state-preparation/input cost proxy, readout
  mode, sample/shot count, reconstruction metric, and any lossy filter or
  downsample parameter.
- Bounded kernels remain plausible QPU targets: transform-domain filters,
  edge/visibility predicates, local observables, amplitude-amplified candidate
  selection, and small shadow/tomography summaries. A whole 1024x1024 color frame
  read back every game frame is not a credible near-term target.

## Source Bank

| Topic | Source | What It Contributes | QGE Implication |
| --- | --- | --- | --- |
| FRQI image representation | Le, Dong, Hirota, "A flexible representation of quantum images..." Quantum Information Processing 2011. https://link.springer.com/article/10.1007/s11128-010-0177-y | Introduces FRQI as a normalized state carrying color and position, with polynomial preparation plus compression/processing examples. | Useful conceptual ancestor for "one state encodes color and position", but its probabilistic color readout is a warning against claiming easy full-frame recovery. |
| NEQR image representation | Zhang et al., "NEQR: a novel enhanced quantum representation of digital images", Quantum Information Processing 2013. https://link.springer.com/article/10.1007/s11128-013-0567-z | Stores gray-scale values in qubit basis states rather than amplitudes, enabling more accurate retrieval at the cost of more qubits. | QGE traces should distinguish amplitude/probability encodings from basis/bit-plane encodings; each has a different readout and resource story. |
| Modern QIR/QPIXL survey and implementation | Amankwah et al., "Quantum pixel representations and compression for N-dimensional images", Scientific Reports 2022. https://www.nature.com/articles/s41598-022-11024-y | Unifies FRQI/NEQR-style pixel representations, reduces gate complexity, and discusses NISQ practicality. It explicitly notes large measurement cost for FRQI retrieval and the qubit/readout tradeoff for NEQR. | Strong support for our trace-contract direction: report qubits, gate/input complexity, compression, and retrieval mode instead of only "frame rendered". |
| Practical NISQ FRQI limits | Geng et al., "Improved FRQI on superconducting processors and its restrictions in the NISQ era", Quantum Information Processing 2023. https://link.springer.com/article/10.1007/s11128-023-03838-0 | Studies real/simulated backend limits and emphasizes that data conversion, implementation, and classical interpretation of measurements are hard in practice. | QGE should not overclaim hardware viability. For research mode, include readout error/measurement mitigation fields and treat large-frame recovery as simulator-backed unless proven otherwise. |
| Quantum image edge detection | Yao et al., "Quantum Image Processing and Its Application to Edge Detection: Theory and Experiment", Physical Review X 2017. https://journals.aps.org/prx/abstract/10.1103/PhysRevX.7.031041 | Encodes pixel values in probability amplitudes and positions in basis states; edge detection can be expressed as a very small quantum operation independent of image size. | Good model for QGE: use quantum kernels for compact predicates and edge/visibility transforms, not necessarily to emit every pixel. Edge maps are better QPU-facing artifacts than whole frames. |
| Quantum bilinear interpolation | Zhou et al., "Quantum realization of the bilinear interpolation method for NEQR", Scientific Reports 2017. https://www.nature.com/articles/s41598-017-02575-6 | Implements scaling up/down for NEQR with circuit modules for coordinate mapping and arithmetic. The simulation section reports bilinear scaling as clearer and less distorted than nearest-neighbor scaling, and the measurement section reiterates that reconstructing the classical image requires repeated preparation/measurement. | This is the closest direct analog to QGE's current seam work: interpolate from well-defined neighboring samples, but report reconstruction/readout cost. Conservative triangle coverage is our classical front-end equivalent of giving the signal a valid neighborhood before resampling. |
| Quantum frequency resampling | Tumbiolo et al., "Quantum frequency resampling", npj Quantum Information 2025. https://www.nature.com/articles/s41534-025-01076-z | Gives quantum upsampling/downsampling protocols for probability-encoded signals using QFTs. It explicitly connects downsampling quality to high-frequency content and aliasing. | Directly relevant to QGE tearing: preserve geometry coverage, then use transform-domain filtering with explicit high-frequency/aliasing telemetry. Sharp Quake edges need careful filtering, not naive qubit discard/downsample. |
| Efficient quantum transforms | Hoyer, "Efficient Quantum Transforms", arXiv 1997. https://arxiv.org/abs/quant-ph/9702028 | Gives efficient networks for several transforms, including wavelet transforms. | Supports sparse-DWT as a legitimate quantum-signal representation family, while leaving state-prep/readout outside the speedup claim. |
| Quantum wavelet transforms | Fijany and Williams, "Quantum Wavelet Transforms: Fast Algorithms and Complete Circuits", arXiv 1998. https://arxiv.org/abs/quant-ph/9809004 | Derives complete quantum Haar and Daubechies D4 circuits and notes that some classically cheap operations, especially permutations, must be counted explicitly on quantum hardware. | QGE's DWT trace should account for permutation/index-routing cost. A sparse-DWT renderer is defensible, but not if we pretend index movement is free. |
| Quantum convolution caveat | Lomont, "Quantum convolution and quantum correlation algorithms are physically impossible", arXiv 2003. https://arxiv.org/abs/quant-ph/0309070 | Argues that the componentwise multiplication step behind classical convolution/correlation cannot generally be performed on arbitrary quantum state coefficients. | Do not describe QGE texture/lightmap filtering as naive quantum convolution on amplitudes unless the operation is implemented as a valid unitary/measurement protocol. |
| qRAM data loading | Giovannetti, Lloyd, Maccone, "Architectures for a quantum random access memory", Physical Review A 2008. DOI 10.1103/PhysRevA.78.052310; arXiv:0807.4994. | qRAM can address superpositions of memory sites; bucket-brigade designs reduce active interactions but still require a memory architecture. | QGE should log data-loading assumptions. Texture/lightmap/framebuffer upload cannot be handwaved as "log qubits" without a qRAM or explicit prepared-state cost. |
| qRAM modern bounds | Wang et al., "Fundamental causal bounds of quantum random access memories", npj Quantum Information 2024. https://www.nature.com/articles/s41534-024-00848-3 | Frames qRAM as the classical-to-quantum interface needed by many algorithms and emphasizes implementation challenges. | Reinforces that QGE should separate simulator-backed sparse states from future hardware-backed memory assumptions. |
| Readout/tomography | Huang, Kueng, Preskill, "Predicting many properties of a quantum system from very few measurements", Nature Physics 2020. https://www.nature.com/articles/s41567-020-0932-7 | Classical shadows can predict many chosen properties with few measurements, but they predict properties/observables rather than dumping an entire state vector. | QGE should add shadow-style summary probes for render fields: edge energy, coefficient bands, visibility observables, depth occupancy, not only raw frame dumps. |
| QSP proper | Low and Chuang, "Optimal Hamiltonian Simulation by Quantum Signal Processing", PRL 2017 / arXiv:1606.02685. https://arxiv.org/abs/1606.02685 | QSP transforms eigenvalues through single-qubit rotation sequences inside Hamiltonian simulation. | Useful for future bounded operator kernels, but not the term to use for our current raster tearing unless we actually implement QSP/QSVT-style polynomial transformations. |
| Qubitization | Low and Chuang, "Hamiltonian Simulation by Qubitization", Quantum 2019. https://quantum-journal.org/papers/q-2019-07-12-163/ | Embeds Hamiltonians in invariant SU(2) subspaces and supports optimal operator-function transforms. | A later path for visibility/material operators; not a near-term fix for screen-space polygon cracks. |

## Artifact/Trace Fields To Add

These are the fields the literature suggests we need if we want the render path
to be publishable instead of just visually interesting:

- `encoding`: sparse_dwt, amplitude_probability, basis_bitplane, qpixl_like,
  dense_reference, or classical_fallback.
- `basis_count` and `qubits`: already present in binary traces; keep them on
  every render/state probe.
- `input_cost`: count of classical samples ingested, texture/lightmap samples
  touched, qRAM-assumed loads, or prepared coefficients.
- `transform_cost`: DWT/QFT/gate/projection/permutation counts when available.
- `resampling`: filter family, downsample/upsample ratio, band cutoff, and
  whether high-frequency components were discarded or zero-padded.
- `readout`: direct simulator readback, sampled shots, shadow observable,
  histogram, or CPU reconstruction.
- `shots` and `readout_error`: zero for direct simulator paths; explicit for
  stochastic or hardware-style measurements.
- `reconstruction_metrics`: coverage holes, edge-energy drift, coefficient
  energy by band, PSNR/SSIM against classic reference when a reference exists.
- `ownership`: qge_primary, qge_shadow, qge_overlay, or classic_fallback.

## Render-Fidelity Implications

1. Geometry cracks must be solved before transform filtering. Quantum frequency
   resampling and wavelet literature assume a coherent sampled signal; they do
   not rescue invalid polygon coverage.
2. Conservative triangle coverage is justified as an anti-aliasing/reconstruction
   precondition, not just a raster polish step.
3. Sharp Quake wall/floor boundaries are high-frequency content. Any DWT/QFT
   downsample or coefficient pruning needs a band/edge telemetry counter so
   artifacts can be explained.
4. Treat view, depth, material, lightmap, and visibility as separate observables
   where possible. Literature readout techniques favor targeted properties over
   full state reconstruction.
5. Keep sparse DWT as the real-time representation. Dense probability
   framebuffer modes should remain reference/lab modes with honest memory and
   readout budgets.

## Open Research Queue

- Identify a clean metric for "triangle seam energy" that can be logged beside
  DWT band energy in the smoke harness.
- Do a second pass over quantum image scaling papers beyond NEQR bilinear
  interpolation, especially floating-point and 3-D variants, to see whether any
  define artifact metrics we can reuse.
- Add a short bibliography appendix with BibTeX once the source set stabilizes.
- Decide whether QGE should implement a shadow-style observable probe for
  coefficient-band energy and edge occupancy.
- Revisit QSP/QSVT only after a concrete bounded operator is identified
  (for example, a visibility confidence operator or material phase transform).

## Search Coverage

The current collection covered these query families:

- quantum image representations: FRQI, NEQR, QPIXL, NISQ restrictions,
  compression, and retrieval/readout cost.
- quantum image scaling and interpolation: nearest-neighbor, bilinear,
  geometric transforms, and frequency-domain resampling.
- quantum wavelet and Fourier transforms: efficient transform circuits, Haar,
  Daubechies D4, QFT-based resampling, and permutation/routing cost.
- input/output bottlenecks: qRAM, classical data loading, and full-state
  readout versus observable prediction.
- measurement reduction: classical shadows and targeted observable extraction.
- QSP/QSVT terminology: Low/Chuang quantum signal processing, qubitization, and
  why those are future bounded-operator tools rather than the current raster
  artifact explanation.
