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

## Next Worker Tasks

### Strict AI Decision Replay V2

Owned files:

- `qge/qge_ai.c`
- `qge/qge_quantum_runtime.c`
- `qge/qge_quantum_runtime.h`
- `tools/qge_trace_summary.py`
- `tests/test_qge.c`

Goal:

Extend entropy replay strictness to gameplay decisions. AI replay should load
recorded decision metadata, verify input hash/legal mask/entropy offset/action,
and report deterministic mismatch or exhaustion instead of silently accepting a
different live decision.

Gate:

- A fixed replay input reproduces the same traced AI decision sequence.
- Mismatch between replay decision metadata and live request produces a strict
  replay fallback/event.
- Trace summary exposes decision replay consumed/mismatch/exhaustion counts.

### Visibility Authority Writeback Sandbox V2

Owned files:

- `qge/qge_vis.c`
- `quake/Quake/r_world.c`
- `quake/Quake/qge_hooks.c`
- `tests/test_qge.c`

Goal:

Add a sandboxed `quantum_vis 2` writeback path that can apply the QGE visible
set only after the readiness gate passes. The default remains classic
visibility unless the authority gate is explicitly requested and clean.

Gate:

- False negatives always force classic visibility for the frame.
- Authority writeback has an explicit trace event and fallback reason.
- Capture/trace artifacts prove whether the frame used classic or QGE
  visibility authority.

### Audio Attenuation/Pan Authority V2

Owned files:

- `quake/Quake/snd_mix.c`
- `quake/Quake/snd_quantum.c`
- `quake/Quake/snd_quantum.h`
- `quake/Quake/qge_hooks.c`
- `tools/quake_graphics_stream.sh`

Goal:

Compare QGE spatial attenuation/pan decisions against classic Quake source
volumes and gate any future source-volume replacement behind parity thresholds.

Gate:

- Per-source telemetry includes classic left/right volume, QGE proposed volume,
  absolute error, and fallback reason.
- Dry fallback remains exact and audible.
- `snd_quantum 2` still does not replace classic attenuation unless the gate is
  explicitly ready.

### Projectile Authority Writeback Sandbox V1

Owned files:

- `quake/Quake/qge_hooks.c`
- `qge/qge_physics.c`
- `qge/qge.h`
- `tests/test_qge.c`

Goal:

Add an opt-in projectile authority sandbox that can write back QGE projectile
position/velocity only when the warmup gate is ready and explicit authority is
requested.

Gate:

- Gate failure leaves classic Quake physics authoritative.
- Writeback records entity, origin/velocity delta, and rollback/fallback reason.
- Tests cover disabled, warmup, threshold failure, and ready authority paths.
