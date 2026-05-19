# QGE 100 Percent Swarm Queue

This queue tracks the next concrete swarm slices required to move Quantum
Quake from evidence-complete milestones toward actual QGE/Moonlab domain
ownership. The standard for completion is not "a hook exists"; each domain
needs a stable contract, shadow parity, explicit telemetry, replayable
measurement, safe fallback, and an authoritative mode when appropriate.

## Wave 1 Checkpoint

- Renderer/artifact gate: render logs now expose primary-framebuffer,
  classic-2D, explicit asset-ownership, and fallback-reason fields. The
  capture matrix blocks complete claims unless classic output is hidden and
  required ownership fields are present and nonzero.
- Physics: the shadow registry now mirrors bounds, owner, ground entity, water
  state, and impact metadata for toss/bounce/gib/projectile entities. Gameplay
  authority is unchanged.

Verified with:

- `python3 -m py_compile tests/test_qge_python_tools.py tools/qge_vanilla_capture_matrix.py tools/qge_publication_pack.py`
- `make test_qge_python_tools`
- `bash tests/test_qge_vanilla_matrix_perf.sh`
- `make test`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1`

## Wave 2 Checkpoint

- Replay strictness: replay now loads full entropy records and strict mode
  validates frame, server time, domain, subject, request ID, and entropy offset
  before accepting a replay value. Metadata mismatch and exhaustion paths
  produce fallback counters and trace events instead of silent fallback.
- AI advisory protocol: QGE AI decisions now use a typed input/output trace
  with input hash, legal-action mask, measured basis, mapped action,
  probabilities, confidence, and entropy offset. `quantum_ai 1` is advisory
  only; `quantum_ai 2` is the explicit authority mode that may write entity
  control state.
- Visibility shadow parity: `R_MarkSurfaces()` now runs a shadow-only QGE
  parity pass, compares QGE visible-surface predictions to the classic
  accepted set, and emits false-positive/false-negative telemetry without
  changing renderer authority.
- Audio source ownership: `snd_quantum 2` now processes SFX/ambient source
  blocks before they are mixed, while `snd_quantum 1` remains the existing
  post-mix path. Source-mode telemetry reports ownership, processed/skipped
  blocks, dry fallbacks, clipping, and transducer timing.

Verified with:

- `make test_qge`
- `bash tests/test_snd_quantum_source_contract.sh`
- `python3 -m py_compile tools/qge_trace_summary.py tests/test_qge_python_tools.py`
- `python3 tests/test_qge_python_tools.py`
- `bash tests/test_qge_trace_summary.sh`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B qge_hooks.o`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B r_world.o`
- `make test`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1`

## Wave 3 Checkpoint

- Replayable AI decision artifacts: typed AI decisions now enter the shared
  binary trace as `ai_decision` records carrying input hash, legal-action mask,
  raw/action basis, mapped/final action, probabilities, confidence, and entropy
  offset. The trace summary groups these records for replay evidence.
- Visibility authority gate: the shadow visibility path now tracks clean
  warmup windows, cumulative mismatches, false negatives, readiness, and
  fallback/authority reasons. `quantum_vis 1` remains shadow-only; requested
  authority is gated by parity readiness.
- Audio spatial source telemetry: source-mode quantum audio now receives source
  and listener vectors, distance attenuation, pan, volumes, and channel count.
  Per-source probes/fallbacks include spatial hashes and exact dry fallback
  reasons.
- Projectile authority warmup: projectile shadow telemetry now evaluates a
  conservative readiness gate with warmup frames, minimum samples, max/average
  shadow-error thresholds, and explicit off reasons. No entity writeback is
  introduced in this slice.

Verified with:

- `python3 -m py_compile tools/qge_trace_summary.py tests/test_qge_python_tools.py`
- `python3 tests/test_qge_python_tools.py`
- `bash tests/test_qge_trace_summary.sh`
- `make -B build/qge/qge_ai.o build/qge/qge_quantum_runtime.o build/qge/qge_trace.o`
- `make test_qge`
- `./bin/test_qge`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B snd_quantum.o`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B snd_mix.o`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B qge_hooks.o`
- `bash tests/test_snd_quantum_source_contract.sh`
- `make test`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1`

## Wave 4 Checkpoint

- Strict AI decision replay: replay traces now load `ai_decision` records, and
  strict mode validates frame, server time, enemy metadata, input hash,
  legal-action mask, and entropy offset before accepting a recorded gameplay
  decision. Metadata mismatch and exhaustion paths emit replay fallback
  telemetry instead of silently diverging.
- Visibility writeback sandbox: visibility authority now has an explicit
  decision contract and `R_MarkSurfaces()` queries the decision flags after
  shadow parity. Classic visibility remains authoritative unless a future
  writeback path explicitly sees a clean, ready gate; false negatives force
  classic.
- Audio attenuation/pan parity gate: source-mode audio now computes QGE
  proposed left/right source volumes from spatial metadata, compares them to
  classic Quake attenuation/panning, and only substitutes volumes when
  `snd_quantum_source_authority` is explicitly requested and parity is ready.
- Projectile writeback sandbox: a pure helper now evaluates classic vs QGE
  projectile state selection, reports entity ID, origin/velocity deltas,
  fallback/rollback/off reasons, and only allows QGE source selection when the
  existing warmup gate is ready and authority is explicitly requested.

Verified with:

- `python3 -m py_compile tools/qge_trace_summary.py tests/test_qge_python_tools.py`
- `python3 tests/test_qge_python_tools.py`
- `bash tests/test_qge_trace_summary.sh`
- `bash tests/test_snd_quantum_source_contract.sh`
- `bash -n tools/quake_graphics_stream.sh`
- `make -B build/qge/qge_ai.o build/qge/qge_quantum_runtime.o build/qge/qge_trace.o`
- `make test_qge`
- `./bin/test_qge`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B snd_quantum.o`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B snd_mix.o`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B r_world.o`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B qge_hooks.o`
- `make test`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1`

## Wave 5 Checkpoint

- Runtime evidence capture: the stream harness now exposes explicit
  `quantum_ai` and `quantum_vis` knobs, writes a `qge_trace_summary.json`
  sidecar, mirrors that summary into the agent stream, and reports
  `runtime_evidence_ready` through the manifest and ICC evidence.
- Single-trace evidence: `qge_trace_summary.py` derives a
  `runtime_evidence` block from one binary trace. The ready gate requires
  nonzero AI decision records, audio source-spatial probes, visibility shadow
  parity plus authority-gate probes, and projectile authority-gate probes.
- Matrix propagation: `qge_vanilla_capture_matrix.py` loads the trace summary
  sidecar and exposes runtime-evidence counts in the matrix and ICC sidecar
  without folding them into the vanilla renderer conformance claim.
- Live proof: a compact `e1m1` trace produced
  `runtime_evidence.single_trace_ready=true` with 245 AI decisions, 25 audio
  source-spatial probes, 43 visibility authority-gate probes, and 45
  projectile authority-gate probes.

Verified with:

- `python3 -m py_compile tools/qge_trace_summary.py tools/qge_vanilla_capture_matrix.py tests/test_qge_python_tools.py`
- `python3 tests/test_qge_python_tools.py`
- `bash tests/test_qge_trace_summary.sh`
- `bash tests/test_snd_quantum_source_contract.sh`
- `bash tests/test_noesis_input_contract.sh`
- `make test_qge_python_tools`
- `make test`
- `QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=2 QGE_STREAM_WAIT_FRAMES=40 QGE_STREAM_CAPTURE_WAIT=40 QGE_STREAM_TRACE=1 QGE_STREAM_SOUND=1 QGE_STREAM_SND_QUANTUM=2 QGE_STREAM_SND_QUANTUM_SOURCE_AUTHORITY=1 QGE_STREAM_FIRE_TEST=1 QGE_STREAM_AI=1 QGE_STREAM_VIS=2 QGE_RENDER=2 QGE_PHYSICS=1 QGE_PROJECTILES=1 QGE_STREAM_TIMEOUT_SECONDS=120 QGE_STREAM_LAUNCH=open bash tools/quake_graphics_stream.sh`
- `python3 tools/qge_trace_summary.py diagnostics/quake_stream/20260518-213208/qge_trace.bin --json`

## Wave 6 Checkpoint

- Visibility authority apply: `R_MarkSurfaces()` can now opt into an audited
  QGE visibility mask after the shadow parity gate reports clean, ready
  authority. Classic PVS/cull output remains the default, and false negatives
  still force classic visibility for the frame.
- Visibility apply traceability: QGE records `vis_authority_apply` probes when
  the renderer consumes the audited mask, and the trace summary reports
  `runtime_evidence.visibility.authority_apply_count`.
- Audio authority smoke: a reusable checker validates compact agent-stream
  runs for `snd_quantum 2` plus `snd_quantum_source_authority 1`, requiring
  nonzero audio bytes, source-spatial trace probes, source-frame probes, and
  selected or explicitly gated source-volume telemetry.

Verified with:

- `python3 -m py_compile tools/qge_trace_summary.py tools/qge_audio_authority_smoke.py tests/test_qge_python_tools.py`
- `python3 tests/test_qge_python_tools.py`
- `bash tests/test_qge_audio_authority_smoke.sh`
- `bash tests/test_qge_trace_summary.sh`
- `make test_qge_python_tools`
- `make test_qge_audio_authority_smoke`
- `make test_qge`
- `./bin/test_qge`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B qge_hooks.o`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B r_world.o`

## Wave 7 Checkpoint

- Projectile hook writeback: `QGE_PhysicsTrackToss()` now evaluates the pure
  projectile writeback helper for `MOVETYPE_FLYMISSILE` entities and applies
  the previous QGE prediction only when `quantum_projectiles >= 1.5` explicitly
  requests authority and the conservative gate is ready.
- Projectile safety: `quantum_projectiles 0.5..1.49` remains shadow telemetry
  only, gate failure leaves classic Quake physics authoritative, and threshold
  failures record rollback/fallback decisions instead of silently mutating
  entities.
- Projectile traceability: QGE records `projectile_writeback_decision` probes
  with entity id, source selection, origin/velocity deltas, and fallback or
  rollback reason. `qge_trace_summary.py` reports
  `runtime_evidence.projectile.writeback_decision_count` and writeback flags.

Verified with:

- `python3 -m py_compile tools/qge_trace_summary.py tests/test_qge_python_tools.py`
- `python3 tests/test_qge_python_tools.py`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B qge_hooks.o`
- `make test_qge`
- `./bin/test_qge`

## Next Worker Tasks

- Run a compact live `e1m1` authority smoke with `QGE_PROJECTILES=2`,
  `QGE_PHYSICS=1`, and `QGE_STREAM_TRACE=1`, then verify
  `projectile_writeback_decision` appears in `qge_trace_summary.json`.
