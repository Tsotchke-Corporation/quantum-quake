# Quantum Quake Documentation

This directory contains the working documentation for Quantum Quake and QGE.
The docs are intentionally split by purpose: engineering contracts, current
state, claims policy, stream/harness operation, and long-range research plans.

## Start Here

- [QGE state of development](qge_state_of_development.md): current implemented
  systems, known gaps, recent verified baseline, branch consolidation status,
  failure-mode triage, and verification commands. Treat this as the
  authoritative project snapshot.
- [QGE engine architecture](qge_engine_architecture.md): reusable engine model,
  ownership stages, runtime domains, artifact contract, and conformance target.
- [QGE agent media stream](qge_agent_stream.md): live graphics/audio/Noesis
  diagnostic harness, manifest contract, no-script Noesis triage, environment
  variables, and stream artifacts.
- [QGE claims ledger](qge_claims_ledger.md): rules for supported wording and
  evidence requirements.

## Current Reality Check

- `master` is the primary branch; `origin/HEAD` points at `origin/master`, and
  `origin/main` is fast-forwarded to the same commit for compatibility. The
  active runtime tree is the C/QuakeSpasm/QGE tree on `master`. Latest verified
  runtime baseline is the current tone-headroom QGE renderer slice after
  `b1b7578` (`Use base palette for QGE world textures`), mirrored to both
  `origin/master` and `origin/main`.
- QGE has test-backed runtime, trace, visibility, projectile, audio, and
  rendering surfaces, but classic Quake remains the reference for full
  conformance.
- QGE primary rendering is improved but not visually complete. The current
  fixed-view renderer has better FOV alignment, depth ownership,
  lightmap-preserving contrast, every-frame QGE refresh by default, an ambient
  far-depth world background, normalized warp/water texture sampling, and stable
  render-gate display gain from deterministic state marginals. Normal world
  textures now use the base Quake palette instead of a global high-index
  fullbright boost, reducing noisy floor speckles. The current tone-headroom
  slice also pulls the fixed-view ceiling, side-wall, and far-floor luminance
  closer to the classic reference. Floors, walls, and ceilings no longer shimmer
  from finite-shot display gain, but they are still visibly glitchy: residual
  side-wall/ceiling brightness, raster seams, warp/water seams, viewmodel
  fidelity, and vanilla-material fidelity remain open.
- Default Noesis runs are no-script autonomous diagnostics with server-side
  movement/combat feedback plus local clearance, floor, and hazard probes when
  no target is engaged. Noesis is not yet learning Quake from experience, has
  no robust map-level planning model yet, and scripted route fixtures are opt-in
  regression tools.
- Claims need evidence from tests, traces, screenshots, summaries, or ICC
  attempts.

## Research And Roadmap

- [Quantum Quake full architecture plan](quantum_quake_full_architecture_plan.md):
  detailed target architecture and quantum-native capability matrix.
- [QGE quantum advantage research roadmap](qge_quantum_advantage_research_roadmap.md):
  bounded research workloads and baseline expectations.
- [QGE quantum signal processing research](qge_quantum_signal_processing_research.md):
  signal-processing context for QGE media experiments.
- [QGE scene oracle IR](qge_scene_oracle_ir.md): compiler boundary from captured
  Quake state to auditable oracle inputs.
- [QGE 100 percent swarm queue](qge_100_percent_swarm_queue.md): historical
  engineering wave log and remaining domain-ownership queue.

## Claims And Publication Support

- [QGE publication adversarial audit](qge_publication_adversarial_audit.md):
  adversarial review posture for research/publication language.
- [QGE claims JSON](claims/qge_claims.json): machine-readable claim policy.

## Generated Or Local Evidence

Runtime streams and screenshots are written under `diagnostics/`, not `docs/`.
Current stream harnesses also refresh stable pointers such as:

- `diagnostics/agent_stream/latest_stream.txt`
- `diagnostics/agent_stream/latest_manifest.txt`
- `diagnostics/quake_stream/latest_stream.txt`
- `diagnostics/quake_stream/latest_trace.txt`

Do not cite a visual or gameplay claim from memory. Cite the diagnostic run,
summary JSON, trace summary, or ICC task attempt that supports it.
