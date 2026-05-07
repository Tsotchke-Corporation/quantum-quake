# QGE Scene Oracle IR

Status: schema v0, JSON sidecar format.

The Scene Oracle IR is the media compiler boundary between a live game capture
and a quantum algorithm benchmark. It describes a bounded observable over a
captured scene, the sample space the algorithm may query, the input/readout
assumptions, and the cost model reviewers need to audit.

## File Shape

The v0 artifact is `oracle_scene.json`.

Required top-level fields:

- `schema`: fixed string, `qge.scene_oracle_ir.v0`
- `source_capture`: paths and hashes for trace, log, frame, and config inputs
- `scene`: map, frame range, asset/content hashes, render resolution, seed
- `world`: resource counts and stable registry identifiers when available
- `snapshot`: visible surface/entity/light/particle/audio counts
- `observable`: bounded game/media property being estimated or consumed
- `sample_space`: finite query domain and candidate counts
- `oracle_contract`: input register layout, output range, reversibility notes
- `cost_model`: input, state preparation, oracle, readout, and fallback costs
- `trace_summary`: selected publication-facing probe summaries
- `claims`: related claim ids and evidence status

## Observable Contract

Each observable must state:

- `observable_id`: stable identifier
- `domain`: render, visibility, audio, physics, ai, material, ui
- `kind`: mean_estimation, predicate_search, band_energy, finite_shot_control
- `description`: one sentence
- `range`: numeric range, usually `[0.0, 1.0]`
- `reference_mode`: none, high_sample_classical, classic_frame, analytic

Initial allowed observables:

- `render.finite_shot_gate_control`
- `light_transport.soft_shadow_visibility`
- `light_transport.patch_irradiance`
- `visibility.surface_candidate_predicate`
- `render.edge_energy`
- `render.dwt_band_energy`
- `material.phase_transition`

## Sample Space

The sample space must be explicit and finite for v0:

- `kind`: light_samples, subpixels, paths, surfaces, entities, bands
- `candidate_count`: total queryable candidates
- `candidate_sources`: where candidates came from
- `register_bits`: bits needed for candidate index
- `normalization`: how raw game values map into the observable range

The exporter may use aggregate candidate counts in v0. Later versions should
include sampled candidate records where practical.

## Oracle Contract

The oracle contract records what a quantum algorithm is allowed to assume:

- `oracle_kind`: bounded_contribution or predicate
- `input_register`: bit layout for candidate/sample ids
- `output_register`: contribution, predicate bit, phase mark, or amplitude
- `reversibility`: reversible, reversible_with_work_registers, or classical_model
- `function`: deterministic description of `f(x)` or predicate `P(x)`
- `implementation_status`: model, simulator, live_kernel, or hardware_candidate

No advantage claim may omit this contract.

## Cost Model

Required fields:

- `candidate_count`
- `classical_samples_touched`
- `texture_samples_touched`
- `lightmap_samples_touched`
- `state_prep_cost`
- `qram_assumption`
- `oracle_eval_count`
- `classical_eval_count`
- `readout_model`
- `shots`
- `fallback_count`

Use `null` only when the value is genuinely unavailable. Unknown costs block
advantage claims.

## Determinism

For the same capture directory and claim ledger, `qge_oracle_export.py` must
produce byte-stable JSON except for explicitly configured output paths.

All generated JSON uses sorted keys and two-space indentation.
