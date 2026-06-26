# Quantum Quake Release And Swarm Handoff

Date: 2026-06-26

This handoff records the release state for the shareware build and the
Moonlab hardware-advantage addendum. ICC is the authoritative source for
readiness, blockers, and permitted claims.

## Release State

The shareware release lanes are complete. After reindexing, plain ICC
`next-action` commands that use only the default `diagnostics/publication_pack/*`
trace source report zero actions for both release targets:

- `qge_shareware_user_playable_release`: ready, score 100, actions 0.
- `qge_shareware_public_release_snapshot`: ready, score 100, actions 0.
- `qge_shareware_release_bundle`: ready, score 100.
- `qge_shareware_complete_effects`: ready, score 100.

The hardware lane is not complete:

- `qge_hardware_advantage_campaign`: ready, score 100.
- `qge_real_hardware_quantum_advantage`: blocked, score 60, actions 5.

That blocked state is intentional. The current build may be described as a
Quantum Quake shareware simulator/native QGE release. It may not be described
as a hardware quantum-advantage result, whole-game hardware execution, practical
hardware speedup, quantum supremacy, or dense 70,000-qubit execution.

## Key Artifacts

- Public release snapshot:
  `diagnostics/public_release/20260626-shareware-current/qge_shareware_public_release_snapshot.json`.
- Public release ICC sidecar:
  `diagnostics/public_release/20260626-shareware-current/qge_shareware_public_release_snapshot_icc_evidence.json`.
- Default ICC release trace mirror:
  `diagnostics/publication_pack/20260624-shareware-v8/release/qge_shareware_current_release_icc_trace.jsonl`.
- User-playable package manifest:
  `diagnostics/user_release/20260626-shareware-playable/qge_shareware_user_package.json`.
- User package archive:
  `diagnostics/user_release/20260626-shareware-playable/QuantumQuake-shareware-macos.zip`.
- Complete effects gate:
  `diagnostics/shareware_effects/20260625-050156/qge_shareware_complete_effects_gate.json`.
- Fail-closed hardware advantage gate:
  `diagnostics/hardware_advantage/20260626-shareware-v8-current/qge_hardware_advantage_gate.json`.
- Hardware campaign ICC evidence:
  `docs/qge_hardware_advantage_campaign_icc_evidence.json`.

The default ICC trace mirror is the important process guard. It mirrors release
and hardware-boundary sidecars into the publication-pack path that plain ICC
commands already auto-discover. It includes:

- user package readiness,
- public release snapshot readiness,
- Moonlab hardware submission-scope readiness,
- blocked hardware advantage gate evidence,
- bounded QAE claim-scope artifact evidence.

It does not include returned-hardware ingest, returned-record, comparison, hash,
or claim-ready events. Those remain blocked until real Moonlab hardware evidence
exists.

## External Hardware Blockers

Only these `qge_real_hardware_quantum_advantage` criteria remain open:

- `qge_real_hardware_result_backend`
- `qge_real_hardware_result_recorded`
- `qge_real_hardware_comparison_artifact`
- `qge_real_hardware_record_hash`
- `qge_advantage_claim_ready`

No lane should emit `qge_hardware_advantage_claim_ready` until a real returned
Moonlab record is ingested, hashed, compared with simulator evidence, audited in
strict mode, and accepted by `qge_hardware_advantage_gate.py`.

## Swarm Results

Initial task manifests were created on Atlas for three lanes:

- `task-2026-06-26-679285`: pre-hardware development audit.
- `task-2026-06-26-49a85b`: user-playable shareware package audit.
- `task-2026-06-26-5ea4cd`: parallel execution map.

The first forwarding attempt failed because Enki could not write queue files:
`No space left on device`. A read-only disk probe showed
`/System/Volumes/Data` at 100% usage with about 126 MiB available. Direct
Qwen/Kimi routes also failed at the `resource-leases.json` write step.

After storage repair, Enki reported about 1.0 GiB available. The supervisor was
running with concurrency 4, max workers 8, and no resource-blocked pending work.
The three tasks were requeued and completed through `route-substrate` to qLLM:

- `task-2026-06-26-71c611`: pre-hardware audit,
  `route-handoff-20260626T050701774504Z-39d51e-qllm`.
- `task-2026-06-26-6fd1cd`: user package audit,
  `route-handoff-20260626T050701798461Z-e9b96e-qllm`.
- `task-2026-06-26-cb3d18`: execution map,
  `route-handoff-20260626T050701793942Z-9bc04d-qllm`.

These completions are advisory only. Enki could not probe
`/Users/tyr/Desktop/quantum_quake/.git` because of a permission error, and the
route policy disabled writes for these goals. The tasks did not produce repo
edits or replacement release evidence.

Additional read-only backend audits were requested:

- `task-2026-06-26-80c35c`, `codex`: unusable, auth refresh failed.
- `task-2026-06-26-6afa51`, `kimi-agent`: unusable, connection refused.
- `task-2026-06-26-370826`, `openrouter`: completed; agreed that shareware
  simulator release wording is allowed and hardware/advantage wording is not.
- `task-2026-06-26-51cd8c`, `claude`: pending when this handoff was refreshed.

ICC on Atlas remains authoritative.

## Local Work Lanes

| Lane | Scope | Files |
|---|---|---|
| Hardware return workflow | Operator workflow for real returned Moonlab ingest, strict audit, comparison, and gate handoff. No fabricated hardware evidence. | `tools/qge_moonlab_hardware_ingest.py`, `tools/qge_moonlab_hardware_result_audit.py`, hardware-return docs/tests |
| User package hardening | Ensure a player package cannot pass without `QuantumQuake.app`, `assets/id1/pak0.pak`, and final release evidence. | `tools/qge_shareware_user_package.py`, `tools/qge_shareware_release_bundle.py`, release tests |
| Execution map | Reconcile ICC tasks, release artifacts, stale diagnostics, and parallel work lanes. | docs only |

## Stale Diagnostics

Older shareware effects matrices and session plans can still show blocked
capture work. The current complete-effects gate is the 2026-06-25 05:01:56
artifact listed above. It supersedes earlier blocked matrices and capture
checklists.

The hardware campaign being ready is not a hardware-success claim. It means the
submission scope and operator workflow are ready, while returned hardware data
is still absent.
