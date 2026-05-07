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
  artifact emission and blocks on unmarked fallback-backed claims.

The criteria use ICC event-name and event-value filters so an oracle-export
sidecar cannot accidentally satisfy an advantage-benchmark or publication gate.

`tools/qge_oracle_export.py` emits `qge_icc_evidence.json`, which ICC can parse
as runtime evidence. Pass that file or its containing directory to ICC with
`--trace-file` or `--trace-dir`.
