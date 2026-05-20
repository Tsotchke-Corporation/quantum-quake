# Quantum Quake Documentation

This directory contains the working documentation for Quantum Quake and QGE.
The docs are intentionally split by purpose: engineering contracts, current
state, claims policy, stream/harness operation, and long-range research plans.

## Start Here

- [QGE state of development](qge_state_of_development.md): current implemented
  systems, known gaps, verification commands, and branch consolidation status.
- [QGE engine architecture](qge_engine_architecture.md): reusable engine model,
  ownership stages, runtime domains, artifact contract, and conformance target.
- [QGE agent media stream](qge_agent_stream.md): live graphics/audio/Noesis
  diagnostic harness, manifest contract, environment variables, and stream
  artifacts.
- [QGE claims ledger](qge_claims_ledger.md): rules for supported wording and
  evidence requirements.

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
