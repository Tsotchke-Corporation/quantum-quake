# QGE Claims Ledger

Status: schema v0.

The claims ledger prevents vague or unsupported research language. Every public
claim must map to an explicit evidence contract.

Machine-readable claims live in `docs/claims/qge_claims.json`.

## Claim Fields

Required fields:

- `claim_id`: stable dotted identifier
- `claim_type`: feasibility, conformance, benchmark, query_advantage,
  sample_complexity, systems
- `status`: planned, partial, supported, blocked, rejected
- `allowed_wording`: wording that can appear in docs/papers
- `disallowed_wording`: wording that must not be used
- `problem_statement`: formal scope of the claim
- `input_model`: allowed input assumptions
- `output_observable`: measured or rendered output
- `quantum_algorithm`: algorithm or representation involved
- `classical_baseline`: required baseline(s)
- `required_trace_fields`: trace or sidecar fields required for support
- `accepted_evidence`: concrete artifact requirements
- `failure_conditions`: conditions that invalidate the claim

## Initial Claim Policy

- Feasibility claims may rely on traces, screenshots, and gate/shot telemetry.
- Vanilla conformance claims require classic/QGE parity captures and fallback
  accounting.
- Query/sample-complexity claims require oracle-call accounting and strong
  classical baselines.
- Practical hardware advantage is not an allowed current claim.
- Full-frame quantum readout is not an allowed current claim.
- Noesis learning or trained-player claims are not allowed yet. Current Noesis
  wording must describe no-script autonomous diagnostics, local reactive
  exploration, and explicit harness evidence unless a future change adds a real
  replay/training/update loop with held-out evaluation.

## Review Rule

If a claim cannot be validated from traces, sidecars, metrics, circuits, and
baseline artifacts, it is not supported.
