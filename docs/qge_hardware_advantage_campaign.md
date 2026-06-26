# QGE Hardware Execution And Advantage Campaign

Status: campaign ready; real hardware result blocked.

This campaign prepares the current shareware QGE/Moonlab evidence for a real
Moonlab hardware return and a narrowly scoped advantage analysis. It does not
change the current release claim. The shareware build is ready as a
simulator/native QGE release; hardware execution and quantum advantage remain
future gated claims.

## Current State

- Source pack:
  `diagnostics/publication_pack/20260624-shareware-v8`.
- Shareware user-playable release: ICC ready, score 100.
- Moonlab hardware submission scope: ready for control-plane submission.
- Hardware candidate jobs: 1.
- Hardware submitted jobs: 0.
- Completed hardware jobs: 0.
- Hardware quantum-advantage claim: not allowed.
- Whole-game hardware execution claim: not allowed.
- Dense 70,000-qubit execution claim: not allowed.

The current hardware candidate is
`qge.light_transport_qae_benchmark.mlae.v0`. It is scoped to the bounded
`advantage.light_transport_qae_query_scaling` claim. The hardware record
template is generated at:

`diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_moonlab_hardware_record.template.json`

## Claim Boundary

Allowed now:

- Quantum Quake shareware release wording.
- Simulator/native QGE runtime wording.
- Bounded research language for the prepared Moonlab QAE candidate.
- Statements that no returned hardware result is present yet.

Forbidden until real evidence exists:

- hardware quantum advantage,
- true quantum hardware acceleration,
- practical hardware speedup,
- quantum supremacy,
- whole-game hardware execution,
- dense 70,000-qubit execution,
- registered/full-game release claims.

The advantage claim can only become eligible after a real Moonlab record is
ingested, audited, compared with simulator evidence, checked against classical
baselines, and accepted by the fail-closed hardware advantage gate.

## Definition Of Done

Hardware execution is complete only when all of the following are true:

1. The Moonlab control-plane packet and selected `.moonlab` circuit bodies
   regenerate from the publication pack without mismatch.
2. A real Moonlab hardware backend returns a completed record for the bounded
   QAE candidate job.
3. The returned record includes backend id, run id, submit/complete times, shot
   schedule, completed shots, readout format, mitigation, observed or mean
   value, and readout error.
4. `tools/qge_moonlab_hardware_ingest.py` validates and merges the returned
   record.
5. ICC sees `runtime_backend=qge_moonlab_hardware_ingest`.
6. ICC sees `completion_reason=qge_moonlab_hardware_result_recorded`.
7. The resulting comparison artifact keeps hardware advantage, whole-game
   hardware execution, and dense-state flags false unless a later gate permits
   exact stronger wording.

Quantum advantage is complete only after hardware execution is complete and all
of the following are true:

1. The problem statement fixes the bounded Quake-derived observable, input
   model, output observable, oracle, and readout model.
2. Classical baselines include high-sample reference data, plain Monte Carlo,
   stratified/Sobol sampling, and any relevant structured baseline.
3. The cost model records oracle calls, classical eval count, state-prep cost,
   qRAM assumption, circuit depth, one- and two-qubit gates, controlled oracle
   calls, shots, confidence, epsilon target, and readout model.
4. Scaling evidence spans enough problem sizes and seeds to support the exact
   query or sample-complexity statement.
5. Hardware data is compared against simulator and classical baselines without
   using simulator output as a proxy for hardware execution.
6. `tools/qge_hardware_advantage_gate.py` allows only the exact claim wording
   supported by the claims ledger.

## Workstreams

### ICC Control Plane

Keep the campaign, returned-hardware target, and advantage gate separate in
`.icc/completion-oracles.json`. Reindex ICC after every accepted source or
evidence update.

Acceptance:

```sh
/Users/tyr/Desktop/infinite_context_coder/bin/icc task-list --repo quantum_quake
/Users/tyr/Desktop/infinite_context_coder/bin/icc next-action --repo quantum_quake --goal qge_real_hardware_quantum_advantage --format markdown
```

Expected current result: the real-hardware target remains blocked with five
actions, all tied to returned hardware ingest, returned-record, comparison,
record hash, or claim-ready evidence.

### Candidate Regeneration

Regenerate the bounded QAE readout payload, reversible `Q_f` kernel, power-zero
observation circuit, selected Grover schedule, submission bundle, and hardware
submission scope. Then run the artifact audits.

Representative commands:

```sh
python3 tools/qge_moonlab_job_runner.py diagnostics/publication_pack/20260624-shareware-v8/resource/qge_moonlab_job_specs.json --out diagnostics/hardware_advantage/20260626-shareware-v8-current/regenerated/qge_moonlab_job_results.verify.json --expect diagnostics/publication_pack/20260624-shareware-v8/resource/qge_moonlab_job_results.json --plan-out diagnostics/hardware_advantage/20260626-shareware-v8-current/regenerated/qge_moonlab_replay_plan.verify.json --submission-out diagnostics/hardware_advantage/20260626-shareware-v8-current/regenerated/qge_moonlab_submission_packet.verify.json
python3 tools/qge_moonlab_advantage_artifact_audit.py diagnostics/publication_pack/20260624-shareware-v8 --out diagnostics/hardware_advantage/20260626-shareware-v8-current/regenerated/qge_moonlab_advantage_artifact_audit.json --fail-on-mismatch
```

### Hardware Submission And Return

Submit only the bounded QAE candidate job. Do not submit the game loop, the full
framebuffer, or registered/full-game content under this campaign.

Generate the operator template:

```sh
python3 tools/qge_moonlab_hardware_ingest.py diagnostics/publication_pack/20260624-shareware-v8/resource/qge_moonlab_submission_packet.json --template-out diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_moonlab_hardware_record.template.json
```

After a real hardware return, ingest the completed record:

```sh
python3 tools/qge_moonlab_hardware_ingest.py diagnostics/publication_pack/20260624-shareware-v8/resource/qge_moonlab_submission_packet.json --job-results diagnostics/publication_pack/20260624-shareware-v8/resource/qge_moonlab_job_results.json --hardware-record qge_moonlab_hardware_record.json --out diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_moonlab_job_results.hardware.json --comparison-out diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_moonlab_hardware_comparison.json --icc-out diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_moonlab_hardware_icc_evidence.json
```

The returned record must keep overclaim flags false unless a later audited gate
changes that posture.

### Strict Hardware Audit

Run the hardware-result audit in strict real-campaign mode. Zero returned rows
must remain blocked, not treated as a clean empty ledger.

```sh
python3 tools/qge_moonlab_hardware_result_audit.py diagnostics/publication_pack/20260624-shareware-v8/resource/qge_moonlab_submission_packet.json diagnostics/publication_pack/20260624-shareware-v8/resource/qge_moonlab_job_results.json --hardware-scope diagnostics/publication_pack/20260624-shareware-v8/resource/qge_moonlab_hardware_submission_scope.json --strict-real-campaign --out diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_moonlab_hardware_result_audit.strict.json --icc-out diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_moonlab_hardware_result_audit.strict_icc.json
```

### Advantage Gate

Run the fail-closed advantage gate only after strict hardware audit and hardware
comparison artifacts exist.

```sh
python3 tools/qge_advantage_metrics_audit.py diagnostics/publication_pack/20260624-shareware-v8 --out diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_advantage_metrics_audit.json --fail-on-mismatch
python3 tools/qge_hardware_advantage_gate.py --advantage-metrics diagnostics/publication_pack/20260624-shareware-v8/advantage/advantage_metrics.json --job-results diagnostics/publication_pack/20260624-shareware-v8/resource/qge_moonlab_job_results.json --hardware-comparison diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_moonlab_hardware_comparison.json --hardware-result-audit diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_moonlab_hardware_result_audit.strict.json --advantage-metrics-audit diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_advantage_metrics_audit.json --claims docs/claims/qge_claims.json --out diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_hardware_advantage_gate.json --icc-out diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_hardware_advantage_gate_icc.json
```

## Disjoint Work Lanes

- Compiler lane: Moonlab QAE payload, oracle kernel, observation circuit, and
  Grover schedule tools.
- Hardware lane: returned-record ingest, strict audit, comparison, and operator
  fixtures.
- Benchmark lane: advantage metrics, classical baselines, claims-ledger
  alignment.
- Gate lane: `qge_hardware_advantage_gate.py`, ICC oracle tests, and publication
  addendum logic.
- Docs lane: release claims, limitations, operator handoff, and user-facing
  wording.

Each lane must preserve the current no-overclaim posture until real hardware
evidence satisfies the gate.
