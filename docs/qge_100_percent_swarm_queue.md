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
- `make quake`
- `QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=2 QGE_STREAM_WAIT_FRAMES=40 QGE_STREAM_CAPTURE_WAIT=40 QGE_STREAM_TRACE=1 QGE_STREAM_SOUND=1 QGE_STREAM_SND_QUANTUM=2 QGE_STREAM_SND_QUANTUM_SOURCE_AUTHORITY=1 QGE_STREAM_FIRE_TEST=1 QGE_STREAM_AI=1 QGE_STREAM_VIS=2 QGE_STREAM_DISPLAY=0 QGE_RENDER=2 QGE_PHYSICS=1 QGE_PROJECTILES=2 QGE_STREAM_TIMEOUT_SECONDS=120 QGE_STREAM_LAUNCH=direct bash tools/quake_graphics_stream.sh`
- `python3` validation of `diagnostics/agent_stream/20260518-223046/trace/qge_trace_summary.json`:
  `runtime_evidence.projectile.writeback_decision_count=21`,
  `authority_requested=true`, and `writeback_selected=true`.

## Wave 8 Checkpoint

- Explicit physics authority cvar: projectile writeback now recognizes
  `quantum_physics_authoritative 1` as the documented authority request while
  preserving `quantum_projectiles >= 1.5` as a compatibility path for existing
  authority smokes.
- Harness propagation: `tools/quake_graphics_stream.sh` and
  `tools/quake_crash_watch.sh` can set `QGE_PHYSICS_AUTHORITATIVE`, write
  `quantum_physics_authoritative` into generated autoexec files, and mirror the
  setting into run output or agent manifests.
- Traceability: projectile runtime evidence now exposes a
  `physics_authoritative_cvar` flag so authority traces can distinguish the
  explicit cvar from the legacy projectile-mode compatibility request.

Verified with:

- `python3 -m py_compile tools/qge_trace_summary.py tests/test_qge_python_tools.py`
- `bash -n tools/quake_graphics_stream.sh`
- `bash -n tools/quake_crash_watch.sh`
- `python3 tests/test_qge_python_tools.py`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B qge_hooks.o`
- `make test_qge_python_tools`
- `make test_qge`
- `./bin/test_qge`
- `make test`
- `make quake`
- `QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=2 QGE_STREAM_WAIT_FRAMES=40 QGE_STREAM_CAPTURE_WAIT=40 QGE_STREAM_TRACE=1 QGE_STREAM_SOUND=1 QGE_STREAM_SND_QUANTUM=2 QGE_STREAM_SND_QUANTUM_SOURCE_AUTHORITY=1 QGE_STREAM_FIRE_TEST=1 QGE_STREAM_AI=1 QGE_STREAM_VIS=2 QGE_STREAM_DISPLAY=0 QGE_RENDER=2 QGE_PHYSICS=1 QGE_PROJECTILES=1 QGE_PHYSICS_AUTHORITATIVE=1 QGE_STREAM_TIMEOUT_SECONDS=120 QGE_STREAM_LAUNCH=direct bash tools/quake_graphics_stream.sh`
- `python3` validation of `diagnostics/agent_stream/20260518-224342/trace/qge_trace_summary.json`:
  `runtime_evidence.projectile.writeback_decision_count=21`,
  `authority_requested=true`, `writeback_selected=true`, and
  `physics_authoritative_cvar=true`.

## Next Worker Tasks

- No Wave 12 projectile/runtime evidence task remains in this queue. Use
  `icc assistant-status` for the next cross-task goal suggestion.

## Wave 9 Checkpoint

- Projectile branch-state module: QGE now has a pure projectile branch-state
  evaluator with explicit classic-shadow, QGE-prediction, and
  impact-observation branches. The evaluator normalizes branch weights,
  computes coherence/decoherence from shadow error telemetry, records the
  observation boundary, and returns selected branch origin/velocity metadata
  without mutating Quake state.
- Writeback source upgrade: projectile writeback now fills its QGE candidate
  from the selected branch-state output instead of directly replaying the
  previous prediction slot. Authority still requires the conservative
  projectile gate plus the explicit authority request.
- Runtime evidence: projectile traces now include `projectile_branch_state`
  probes with CA-MPS representation, branch basis count, selected probability,
  coherence/decoherence, and branch-selection flags. Collision observations
  record `QGE_MEASURE_PROJECTILE_IMPACT` measurement events at the collision
  boundary.
- Summary coverage: `qge_trace_summary.py` now decodes generic measurement
  records and exposes projectile branch-state counts plus projectile impact
  measurement counts in `runtime_evidence.projectile`.

Verified with:

- `python3 -m py_compile tools/qge_trace_summary.py tests/test_qge_python_tools.py`
- `python3 tests/test_qge_python_tools.py`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B qge_hooks.o`
- `make test_qge`
- `./bin/test_qge`
- `bash tests/test_qge_trace_summary.sh`
- `make test_qge_python_tools`

## Next Worker Tasks

## Wave 10 Checkpoint

- Pre-impact boundary hook: `SV_PushEntity()` now calls
  `QGE_PhysicsSelectProjectileBranch()` immediately after `SV_Move()` produces
  the candidate trace and before `trace.endpos` is copied into the edict or
  `SV_Impact()` runs. This gives QGE a pre-side-effect branch-selection
  boundary for missiles.
- Guarded selection: the hook reuses the wave9 branch-state evaluator and the
  existing projectile authority/writeback gate. It only adjusts trace endpos
  and projectile velocity when authority is allowed, the selected branch is
  `QGE_PROJECTILE_BRANCH_QGE_PREDICTION`, and the candidate is not an impact
  observation. Collision candidates remain mutually consistent and are traced
  as measured impact branches.
- Evidence: traces now include `projectile_preimpact_selection` probes, and
  `qge_trace_summary.py` reports
  `runtime_evidence.projectile.preimpact_selection_count` plus selected
  probability. The branch-state hash now includes selected impact entity,
  fraction, origin, and normal so pre-impact measurements are deterministic.

Verified with:

- `python3 -m py_compile tools/qge_trace_summary.py tests/test_qge_python_tools.py`
- `make test_qge`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B qge_hooks.o`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B sv_phys.o`
- `python3 tests/test_qge_python_tools.py`
- `bash tests/test_qge_trace_summary.sh`
- `./bin/test_qge`

## Next Worker Tasks

## Wave 11 Checkpoint

- Collision-oracle authority: pre-impact projectile selection now retraces the
  QGE-selected projectile endpoint through Quake `SV_Move()` and selects either
  the original classic trace or the whole QGE candidate trace. No-impact and
  alternate-impact authority therefore copy a mutually consistent `trace_t`
  tuple (`endpos`, `ent`, `fraction`, `plane`) before `SV_Impact()` runs.
- Invalid trace guard: QGE candidates that start in solid or remain all-solid
  are rejected and fall back to the classic trace with explicit
  `trace_invalid` authority reason evidence.
- Evidence: `projectile_preimpact_selection` probes now include collision
  oracle flags for QGE trace selection, no-impact selection, alternate-impact
  selection, and classic fallback. `qge_trace_summary.py` exposes matching
  `runtime_evidence.projectile` counters.
- Pure coverage: `test_qge` now covers disabled classic fallback, QGE
  no-impact authority, alternate-impact authority, invalid-trace fallback, and
  trace-hash sensitivity for the collision oracle.

Verified with:

- `python3 -m py_compile tools/qge_trace_summary.py tests/test_qge_python_tools.py`
- `make test_qge`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B qge_hooks.o`
- `python3 tests/test_qge_python_tools.py`
- `bash tests/test_qge_trace_summary.sh`
- `./bin/test_qge`

## Wave 12 Checkpoint

- Live smoke launcher: macOS stream launches now bypass the AppKit launcher
  before SDL video setup and preserve `-nolauncher`, so direct and `open`
  automation no longer stalls behind the launcher UI or rewrites stream args.
- Fire-smoke evidence: `QGE_STREAM_FIRE_TEST=1` promotes Noesis start wait and
  capture frames enough for a real projectile to pass authority warmup, select
  writeback, select pre-impact QGE branches, and emit collision-oracle traces.
- Controlled visibility smoke: `QGE_STREAM_VIS=3` forces the audited QGE
  writeback mask to match the classic accepted set, proving
  `vis_authority_apply` and all-domain `runtime_evidence.single_trace_ready`
  independently of raw oracle quality regressions.
- Raw visibility authority: `QGE_STREAM_VIS=2` now uses the audited classic
  PVS/cull accepted set as the Grover oracle input. The raw path still records
  false-negative repair and falls back on repair or any remaining parity
  mismatch, but the e1m1 live smoke now reaches clean raw
  `vis_authority_apply` without controlled smoke.
- HUD/console ownership: the renderer mirrors classic 2D HUD and console draw
  calls into QGE ownership telemetry using registered HUD image refs, the
  conchars glyph atlas, and generated fill primitives. Live primary render
  telemetry now reaches `classic2d=0`, `own_hud=1`, `own_console=1`,
  `suppressed2d>0`, and `fallback_reason=none` after the first completed 2D
  frame, with `render_2d_overlay` trace probes.
- Replay/demo boundary evidence: projectile branch, writeback, and
  collision-oracle choices now emit `save_or_demo` measurement records with
  selected basis/source, probability, and stable trace hashes. The trace summary
  exposes per-kind save/demo counts so saved runs can prove which projectile
  choices must be replayed deterministically.

Verified with:

- `python3 -m py_compile tools/qge_trace_summary.py tests/test_qge_python_tools.py`
- `python3 tests/test_qge_python_tools.py`
- `bash tests/test_qge_trace_summary.sh`
- `bash tests/test_noesis_input_contract.sh`
- `make test_qge`
- `./bin/test_qge`
- `make test`
- `make quake`
- `QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=16 QGE_STREAM_WAIT_FRAMES=12 QGE_STREAM_TRACE=1 QGE_STREAM_SOUND=1 QGE_STREAM_SND_QUANTUM=2 QGE_STREAM_SND_QUANTUM_SOURCE_AUTHORITY=1 QGE_STREAM_FIRE_TEST=1 QGE_STREAM_AI=1 QGE_STREAM_VIS=2 QGE_RENDER=2 QGE_PHYSICS=1 QGE_PROJECTILES=1 QGE_PHYSICS_AUTHORITATIVE=1 QGE_STREAM_TIMEOUT_SECONDS=180 QGE_STREAM_LAUNCH=direct bash tools/quake_graphics_stream.sh`
- `QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=8 QGE_STREAM_WAIT_FRAMES=40 QGE_STREAM_TRACE=1 QGE_STREAM_SOUND=1 QGE_STREAM_SND_QUANTUM=2 QGE_STREAM_SND_QUANTUM_SOURCE_AUTHORITY=1 QGE_STREAM_FIRE_TEST=1 QGE_STREAM_AI=1 QGE_STREAM_VIS=3 QGE_RENDER=2 QGE_PHYSICS=1 QGE_PROJECTILES=1 QGE_PHYSICS_AUTHORITATIVE=1 QGE_STREAM_TIMEOUT_SECONDS=150 QGE_STREAM_LAUNCH=direct bash tools/quake_graphics_stream.sh`
- `QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=4 QGE_STREAM_WAIT_FRAMES=12 QGE_STREAM_TRACE=1 QGE_STREAM_SOUND=0 QGE_STREAM_AI=1 QGE_STREAM_VIS=2 QGE_RENDER=2 QGE_RENDER_UPDATE_INTERVAL=1 QGE_PHYSICS=1 QGE_PROJECTILES=1 QGE_PHYSICS_AUTHORITATIVE=1 QGE_STREAM_TIMEOUT_SECONDS=90 QGE_STREAM_LAUNCH=direct bash tools/quake_graphics_stream.sh`

## Wave 13 Checkpoint

- Native sparse-DWT render bridge: Metal-capable contexts now keep the initial
  backend gate honest (`capable, inactive`) until the renderer asks for a
  sparse render bridge. Bridge activation initializes Metal without allocating
  the dense full-state amplitude buffer, switches the runtime path to
  `native_sparse_dwt_render_bridge`, and preserves the existing CPU sparse path
  as fallback.
- Runtime render authority evidence: `qge_dwt_render()` records the backend
  used for each inverse DWT. Live `QGE render frame=...` telemetry now reports
  `native_idwt`, `idwt_fallback`, and `cpu_idwt`, and `render_sparse_dwt` trace
  probes carry matching primary/native/fallback/CPU flags.
- Summary coverage: `qge_trace_summary.py` exposes
  `runtime_evidence.render.flags.native_idwt`, native bridge counts, and native
  fallback counts. `qge_perf_summary.py` aggregates native/fallback/CPU IDWT
  sums and includes them in ICC evidence.
- Live proof: `diagnostics/quake_stream/20260519-163923` captured eight e1m1
  frames with `native_idwt_sum=93`, `idwt_fallback_sum=0`, trace
  `render.flags.native_idwt=true`, and backend gate shutdown path
  `native_sparse_dwt_render_bridge`.

Verified with:

- `make -B build/qge/qge_init.o build/qge/qge_render.o build/qge/qge_metal.o`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B qge_hooks.o qge_init.o qge_render.o qge_metal.o`
- `python3 -m py_compile tools/qge_trace_summary.py tools/qge_perf_summary.py tests/test_qge_python_tools.py`
- `python3 tests/test_qge_python_tools.py`
- `bash tests/test_qge_perf_summary.sh`
- `bash tests/test_qge_trace_summary.sh`
- `make test_qge`
- `./bin/test_qge`
- `make test`
- `make quake`
- `QGE_STREAM_TRACE=1 QGE_STREAM_VIS=3 QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=8 QGE_STREAM_WAIT_FRAMES=12 QGE_STREAM_LAUNCH=direct QGE_STREAM_SOUND=0 QGE_STREAM_TIMEOUT_SECONDS=90 QGE_RENDER=2 QGE_RENDER_UPDATE_INTERVAL=1 bash tools/quake_graphics_stream.sh`

## Wave 14 Checkpoint

- Native sparse-DWT parity: the Metal `haar_inverse_level` kernel now mirrors
  the CPU lifting-scale convention and coefficient orientation exactly. The
  bridge no longer reports native success while reconstructing a different
  image from the same sparse DWT coefficients.
- Regression coverage: `test_dwt_native_bridge_matches_cpu` compares CPU and
  native 64x64 render output on Metal-capable hosts and requires native backend
  selection with near-zero pixel delta. Non-Metal hosts skip the Metal-only
  assertion so the portable test suite remains usable.
- Live proof: `diagnostics/quake_stream/20260519-165107` captured eight e1m1
  frames after the parity fix with `native_idwt_sum=93`,
  `idwt_fallback_sum=0`, trace `render.flags.native_idwt=true`,
  `native_bridge_count=29`, and `native_fallback_count=0`.

Verified with:

- `make -B build/qge/qge_metal.o`
- `python3 -m py_compile tests/test_qge_python_tools.py tools/qge_trace_summary.py tools/qge_perf_summary.py`
- `git diff --check`
- `make test`
- `make quake`
- `QGE_STREAM_TRACE=1 QGE_STREAM_VIS=3 QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=8 QGE_STREAM_WAIT_FRAMES=12 QGE_STREAM_LAUNCH=direct QGE_STREAM_SOUND=0 QGE_STREAM_TIMEOUT_SECONDS=90 QGE_RENDER=2 QGE_RENDER_UPDATE_INTERVAL=1 bash tools/quake_graphics_stream.sh`

## Wave 15 Checkpoint

- Live trace replay loading: Quake now accepts `-qgereplay` and
  `-qgereplaytrace`, with `QGE_REPLAY_TRACE_PATH` as an environment fallback,
  and loads the trace through the shared QGE runtime during `QGE_Init()`.
- Replay source preservation: `qge_rng_set_runtime()` no longer overwrites a
  runtime that already loaded replay entropy. The new RNG-bind replay test
  records deterministic RNG events, loads them into a fresh runtime, binds the
  RNG afterward, and verifies replay values are still consumed.
- Stream harness proof: `QGE_STREAM_REPLAY_TRACE` passes an existing trace to
  the app and `QGE_STREAM_REPLAY_STRICT` mirrors `-qgereplaystrict`. Strict mode
  remains the default; smoke runs can set strictness to `0` when proving
  load/consume against a fresh live run with different frame timing.
- Live proof: `diagnostics/quake_stream/20260519-171122` loaded
  `diagnostics/quake_stream/20260519-165107/qge_trace.bin` and captured a new
  trace with `replay_health.entropy_replay_events=81`, zero replay
  mismatch/exhaustion counters, `native_bridge_count=23`, and
  `native_fallback_count=0`. The runtime log reports
  `entropy_loaded=87 entropy_consumed=81 ... ai_loaded=368 ai_consumed=264`
  with all mismatch/exhaustion counters at zero.

Verified with:

- `bash -n tools/quake_graphics_stream.sh`
- `python3 -m py_compile tools/qge_trace_summary.py tests/test_qge_python_tools.py`
- `make -B build/qge/qge_rng.o build/qge/qge_quantum_runtime.o`
- `make -C quake/Quake -f Makefile.darwin USE_SDL2=1 -B qge_hooks.o qge_rng.o qge_quantum_runtime.o`
- `make test_qge`
- `bash tests/test_noesis_input_contract.sh`
- `./bin/test_qge`
- `make test`
- `make quake`
- `QGE_STREAM_TRACE=1 QGE_STREAM_REPLAY_TRACE=diagnostics/quake_stream/20260519-165107/qge_trace.bin QGE_STREAM_REPLAY_STRICT=0 QGE_STREAM_VIS=3 QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=2 QGE_STREAM_WAIT_FRAMES=12 QGE_STREAM_LAUNCH=direct QGE_STREAM_SOUND=0 QGE_STREAM_TIMEOUT_SECONDS=90 QGE_RENDER=2 QGE_RENDER_UPDATE_INTERVAL=1 bash tools/quake_graphics_stream.sh`

## Next Worker Tasks

- No Wave 15 live replay-loading task remains in this queue. Use
  `icc assistant-status` for the next cross-task goal suggestion.
