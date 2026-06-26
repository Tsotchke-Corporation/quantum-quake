# Quantum Quake ICC Profile

This repo-local ICC profile makes Quantum Quake tasks evaluate against the
project's research contracts instead of ICC's generic production-app oracle.

The oracles in `completion-oracles.json` deliberately separate task classes:

- `qge_scene_oracle_ir`: artifact/compiler foundation. It requires exporter
  runtime evidence, a completion event, and oracle/claims artifacts. It does
  not block on full production fallback checks because v0 sidecars are research
  compiler artifacts.
- `qge_agent_media_stream`: agent-facing media telemetry. It requires the
  project-local stream manifest, at least one video frame, raw mixed-audio PCM,
  audio metadata, and completion evidence.
- `qge_advantage_benchmark`: benchmark work. It requires emitted artifacts and
  completion evidence, and treats synthetic/model paths as a medium-severity
  blocker until they are marked as lab models or wired to real oracles.
- `qge_vanilla_quake_conformance`: full port work. It requires smoke/test
  evidence, a ready paired classic/QGE runtime matrix, and keeps fallback-only
  production paths high-severity. Broader synthetic-model and external-backend
  scrutiny stays on the publication/advantage gates so Windows-only,
  QuakeWorld-only, codec, or Moonlab lab paths do not mask the real vanilla
  runtime ownership signal.
- `qge_publication_artifact_pack`: paper artifact work. It requires reproducible
  artifact emission and blocks on unmarked fallback-backed claims in the QGE
  publication toolchain (`tools/`, `qge/`, Quake QGE hooks, and the claims
  ledger). It intentionally does not fail on unrelated Windows, QuakeWorld,
  codec, or Moonlab research-backend symbols.
- `qge_moonlab_hardware_submission_scope`: bounded Moonlab hardware handoff
  work. It requires the scoped submission artifact, the matching runtime backend
  event, and the `qge_moonlab_hardware_submission_scope_ready` completion event.
  It suppresses the generic pack-level `failure_free` check only for this
  hardware-packet target so the full-game Moonlab deployment gate remains
  blocked until registered BSP assets and full-game evidence are present.
- `qge_hardware_advantage_campaign`: planning work for real Moonlab hardware
  execution and defensible quantum-advantage evidence. It requires the campaign
  Markdown/JSON artifacts, the bounded-QAE campaign ICC sidecar, the ready
  scoped-submission state, and explicit no-returned-hardware/no-overclaim state
  markers. Passing this oracle means the campaign exists, not that hardware
  execution or advantage is proven.
- `qge_real_hardware_quantum_advantage`: the actual future hardware/advantage
  end-state. It requires the scoped hardware handoff, a real
  `qge_moonlab_hardware_ingest` result, a hardware-vs-simulator comparison
  artifact, a returned hardware-record hash, and a future fail-closed
  `qge_hardware_advantage_gate` scoped to
  `advantage.light_transport_qae_query_scaling`. This oracle must remain
  incomplete until a returned hardware result and strong baseline evidence
  exist.
- `qge_moonlab_full_game_deployment`: whole-game Moonlab simulator/native
  deployment work. It requires the deployment-gate artifact, the matching
  runtime backend event, and the `qge_moonlab_deployment_gate_ready` completion
  event, so a blocked deployment gate is reported as an incomplete full-game
  oracle instead of a generic runtime failure.

The criteria use ICC event-name and event-value filters so an oracle-export
sidecar cannot accidentally satisfy an advantage-benchmark or publication gate.

`tools/qge_oracle_export.py` emits `qge_icc_evidence.json`, which ICC can parse
as runtime evidence. Pass that file or its containing directory to ICC with
`--trace-file` or `--trace-dir`.
