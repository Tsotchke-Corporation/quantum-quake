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
  runtime baseline is the current world texture-detail renderer slice, mirrored
  to both `origin/master` and `origin/main`.
- QGE has test-backed runtime, trace, visibility, projectile, audio, and
  rendering surfaces, but classic Quake remains the reference for full
  conformance.
- QGE primary rendering is improved but not visually complete. The current
  fixed-view renderer has better FOV alignment, depth ownership,
  lightmap-preserving contrast, every-frame QGE refresh by default, an ambient
  far-depth world background, normalized warp/water texture sampling, stable
  render-gate display gain from deterministic state marginals, base-palette
  ordinary world textures, bounded fullbright wall texel contribution,
  moderate-minification texture prefiltering, one-texel bilinear wall/ceiling
  smoothing, bounded world-surface blue balance, bounded texture-detail
  restoration, and alias-skin first-person weapon sampling. The latest
  fixed-view evidence is
  `diagnostics/quake_stream/20260521-190448/frame_001.png`; it restores some
  wall, ceiling, and floor texture energy relative to `20260521-183949`, but
  floors, walls, and ceilings are still not vanilla-quality. Remaining renderer
  gaps include nearby floor brightness/color mismatch, raster seams, warp/water
  seams, viewmodel lighting/placement/material parity, and vanilla-material
  fidelity.

## Renderer Evidence Snapshot

The current visual baseline should be read as a sequence of narrow verified
renderer fixes, not as one finished renderer claim:

- `20260521-151552`: current classic fixed-view reference frame.
- `20260521-153315`: world tone/headroom capture; brought fixed-view ceiling,
  side-wall, and far-floor luminance closer to classic.
- `20260521-164816`: fullbright wall-material split; restored bounded unlit
  additive contribution for true fullbright wall texels.
- `20260521-173303`: alias-skin viewmodel capture; replaced the flat QGE weapon
  mesh with skin-sampled alias triangles.
- `20260521-174755`: moderate-minification prefilter capture; improved
  mid-floor texture crawl and whole-frame RMSE.
- `20260521-180918`: one-texel bilinear capture; reduced side-wall,
  front-wall, and ceiling crawl, with mixed whole-frame RMSE across the three
  captured frames.
- `20260521-183949`: world-surface blue-balance capture; reduced blue lift in
  floor, ceiling, and front-wall crops and improved fixed-view RMSE to
  `0.0340944`.
- `20260521-190448`: texture-detail restore capture; raises world
  high-frequency texture energy from `88.8%` to `92.8%` of the classic
  reference and improves fixed-view RMSE to `0.0339437`.
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
