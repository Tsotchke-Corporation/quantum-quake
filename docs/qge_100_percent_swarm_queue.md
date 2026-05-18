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

## Next Worker Tasks

### Replay Decision Artifact V1

Owned files:

- `qge/qge_ai.c`
- `quake/Quake/qge_hooks.c`
- `qge/qge_quantum_runtime.c`
- `tools/qge_trace_summary.py`
- `tests/test_qge.c`

Goal:

Connect typed AI decisions to the shared runtime trace so replay artifacts can
reconstruct complete gameplay-affecting decisions, not only entropy pulls.
Decision records should carry input hash, legal-action mask, raw/mapped action,
probability/confidence, and the entropy offset used by the decision.

Gate:

- Trace summary reports AI decision groups and replay decision counts.
- A fixed replay input reproduces the same traced AI decision sequence.
- Mismatch between replay decision metadata and live request is reported as a
  strict replay failure.

### Visibility Authority Gate V1

Owned files:

- `qge/qge_vis.c`
- `qge/qge_world.c`
- `qge/qge_world.h`
- `quake/Quake/r_world.c`
- `quake/Quake/gl_rmain.c`
- `quake/Quake/qge_hooks.c`
- `tests/test_qge.c`

Goal:

Turn shadow parity into an authority-readiness gate. False negatives must force
classic visibility for the frame. Only a clean warmup window may allow any
future `quantum_vis 2` authority path.

Gate:

- Warmup counters track consecutive clean frames and total mismatches.
- `quantum_vis 2` remains disabled unless parity thresholds are met.
- Logs and trace expose the selected authority/fallback reason.

### Audio Spatial Authority V1

Owned files:

- `quake/Quake/snd_mix.c`
- `quake/Quake/snd_quantum.c`
- `quake/Quake/snd_quantum.h`
- `quake/Quake/qge_hooks.c`
- `tools/quake_graphics_stream.sh`

Goal:

Extend source ownership from per-source transduction to spatial authority:
QGE should consume source origin/listener vectors, expose per-source spatial
metadata, and prove parity/fallback behavior before replacing classic
attenuation/panning.

Gate:

- Source telemetry includes entnum, channel, position/listener hash, attenuation,
  and panning decision.
- Dry fallback records the exact reason per source.
- Agent stream manifest records nonzero source-mode audio plus spatial metadata.

### Projectile Authority Warmup V0

Owned files:

- `quake/Quake/qge_hooks.c`
- `qge/qge_physics.c`
- `qge/qge.h`
- `tests/test_qge.c`

Goal:

Extend physics shadow telemetry into an authority-readiness gate. Mirror
post-move/post-water-transition state, record a warmup window, and define
thresholds for projectile `shadow_error` before any
`quantum_physics_authoritative` writeback path can be enabled.

Gate:

- Warmup counters and max/average shadow-error thresholds are logged.
- Authority remains off unless the warmup gate passes.
- No Quake entity writeback is introduced in this slice.
