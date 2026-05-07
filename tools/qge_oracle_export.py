#!/usr/bin/env python3
"""Export a QGE capture directory as scene-oracle and claims sidecars."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_trace_summary  # noqa: E402


REGISTRY_RE = re.compile(r"QGE: World registry (?P<body>.+)$")
RENDER_RE = re.compile(r"QGE render frame=(?P<frame>\d+) (?P<body>.+)$")
SNAPSHOT_RE = re.compile(r"QGE snapshot frame=(?P<frame>\d+) (?P<body>.+)$")


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_scalar(value: str) -> Any:
    if value.startswith("0x"):
        try:
            return int(value, 16)
        except ValueError:
            return value
    try:
        if any(ch in value for ch in ".eE"):
            number = float(value)
            if math.isfinite(number):
                return number
            return value
        return int(value)
    except ValueError:
        return value


def parse_kv_body(body: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for item in body.split():
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        fields[key] = parse_scalar(value)
    return fields


def parse_readme(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    result: dict[str, Any] = {}
    for line in path.read_text(errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        result[key] = value.strip()
    return result


def parse_log(path: Path) -> dict[str, Any]:
    registry: dict[str, Any] | None = None
    renders: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    if not path.is_file():
        return {"registry": None, "renders": renders, "snapshots": snapshots}

    for line in path.read_text(errors="replace").splitlines():
        match = REGISTRY_RE.search(line)
        if match:
            registry = parse_kv_body(match.group("body"))
            continue
        match = RENDER_RE.search(line)
        if match:
            fields = parse_kv_body(match.group("body"))
            fields["frame"] = int(match.group("frame"))
            renders.append(fields)
            continue
        match = SNAPSHOT_RE.search(line)
        if match:
            fields = parse_kv_body(match.group("body"))
            fields["frame"] = int(match.group("frame"))
            snapshots.append(fields)

    return {"registry": registry, "renders": renders, "snapshots": snapshots}


def latest(items: list[dict[str, Any]]) -> dict[str, Any]:
    return items[-1] if items else {}


def ceil_log2(value: int) -> int:
    if value <= 1:
        return 0
    return (value - 1).bit_length()


def parse_cache_hit_count(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        head = value.split("/", 1)[0]
        try:
            return int(head)
        except ValueError:
            return None
    return None


def probe_by_label(trace: dict[str, Any], label: str) -> dict[str, Any] | None:
    for probe in trace.get("state_probes", []):
        if probe.get("label") == label:
            return probe
    return None


def load_claims(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def field_available(field: str, trace: dict[str, Any], render: dict[str, Any],
                    oracle_scene: dict[str, Any]) -> bool:
    labels = {probe.get("label") for probe in trace.get("state_probes", [])}
    if field in labels:
        return True
    if field in render:
        return True
    if field == "records":
        return bool(trace.get("records"))
    if field == "state_probes":
        return bool(trace.get("state_probes"))
    if field in trace.get("records", {}):
        return True
    if field in oracle_scene.get("cost_model", {}):
        return oracle_scene["cost_model"][field] is not None
    if field in oracle_scene.get("observable", {}):
        return oracle_scene["observable"][field] is not None
    if field in oracle_scene.get("oracle_contract", {}):
        return oracle_scene["oracle_contract"][field] is not None
    if field == "qubits":
        return probe_by_label(trace, "render_gate_kernel") is not None
    if field == "basis":
        return probe_by_label(trace, "render_gate_kernel") is not None
    if field == "gates":
        return "gates" in render or probe_by_label(trace, "render_gate_kernel") is not None
    if field == "shots":
        return "shots" in render or oracle_scene.get("cost_model", {}).get("shots") is not None
    if field == "coherence":
        return probe_by_label(trace, "render_gate_kernel") is not None
    if field == "max_prob":
        return probe_by_label(trace, "render_gate_kernel") is not None
    if field == "asset-class counters":
        return any(key in render for key in ("alias", "sprites", "viewmodel", "material"))
    if field == "candidate_count":
        return oracle_scene.get("sample_space", {}).get("candidate_count") is not None
    if field == "baseline_id":
        return False
    return False


def build_oracle_scene(capture_dir: Path, claims_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    trace_path = capture_dir / "qge_trace.bin"
    log_path = capture_dir / "quantum_quake.log"
    readme_path = capture_dir / "README.txt"
    frame_path = capture_dir / "frame_001.png"
    autoexec_path = capture_dir / "autoexec.cfg.used"

    trace = qge_trace_summary.parse_trace(str(trace_path))
    readme = parse_readme(readme_path)
    log = parse_log(log_path)
    render = latest(log["renders"])
    snapshot = latest(log["snapshots"])
    registry = log["registry"] or {}

    render_sparse = probe_by_label(trace, "render_sparse_dwt") or {}
    gate_probe = probe_by_label(trace, "render_gate_kernel") or {}
    frame_snapshot_probe = probe_by_label(trace, "frame_snapshot") or {}
    world_probe = probe_by_label(trace, "world_registry") or {}
    probe_frames = [
        frame
        for probe in trace.get("state_probes", [])
        for frame in (probe.get("first_frame"), probe.get("last_frame"))
        if frame is not None
    ]

    surface_candidates = int(snapshot.get("surfaces") or render.get("snapshot") or
                             frame_snapshot_probe.get("active_basis_max") or 0)
    entity_candidates = int(snapshot.get("edicts") or render.get("edicts") or 0)
    candidate_count = max(surface_candidates, 0)

    oracle_scene = {
        "schema": "qge.scene_oracle_ir.v0",
        "source_capture": {
            "capture_dir": str(capture_dir),
            "trace": str(trace_path),
            "trace_sha256": sha256_file(trace_path),
            "log": str(log_path),
            "log_sha256": sha256_file(log_path),
            "frame": str(frame_path) if frame_path.exists() else None,
            "frame_sha256": sha256_file(frame_path),
            "autoexec": str(autoexec_path) if autoexec_path.exists() else None,
            "autoexec_sha256": sha256_file(autoexec_path),
            "claims_ledger": str(claims_path),
            "claims_ledger_sha256": sha256_file(claims_path),
        },
        "scene": {
            "scene_id": f"{readme.get('map', registry.get('map', 'unknown'))}:"
                        f"{snapshot.get('frame', render.get('frame', 'unknown'))}",
            "map": readme.get("map", registry.get("map")),
            "frame_range": [
                min(probe_frames) if probe_frames else None,
                max(probe_frames) if probe_frames else None,
            ],
            "selected_frame": snapshot.get("frame", render.get("frame")),
            "render_resolution": readme.get("internal_render_resolution"),
            "render_cvar": readme.get("render_cvar"),
            "seed": None,
            "trace_run_id": f"0x{trace['header']['run_id']:016x}",
            "moonlab_abi_hash": f"0x{trace['header']['moonlab_abi_hash']:016x}",
            "qge_build_hash": f"0x{trace['header']['qge_build_hash']:016x}",
            "quake_content_hash": f"0x{trace['header']['quake_content_hash']:016x}",
        },
        "world": {
            "registry": registry,
            "world_basis": {
                "basis": world_probe.get("active_basis_max"),
                "qubits": world_probe.get("qubit_max"),
                "representation": world_probe.get("representation"),
            },
        },
        "snapshot": {
            "latest": snapshot,
            "render": render,
            "frame_snapshot_basis": {
                "basis": frame_snapshot_probe.get("active_basis_max"),
                "qubits": frame_snapshot_probe.get("qubit_max"),
                "representation": frame_snapshot_probe.get("representation"),
            },
        },
        "observable": {
            "observable_id": "light_transport.soft_shadow_visibility",
            "domain": "render",
            "kind": "mean_estimation",
            "description": "Bounded soft-shadow visibility over visible surface candidates for the captured Quake frame.",
            "range": [0.0, 1.0],
            "reference_mode": "high_sample_classical",
            "implementation_status": "model",
        },
        "sample_space": {
            "kind": "surfaces",
            "candidate_count": candidate_count,
            "candidate_sources": ["frame_snapshot.visible_surfaces", "render.snapshot"],
            "surface_candidates": surface_candidates,
            "entity_candidates": entity_candidates,
            "register_bits": ceil_log2(candidate_count),
            "normalization": "candidate contribution is normalized to [0, 1] by the benchmark oracle",
        },
        "oracle_contract": {
            "oracle_kind": "bounded_contribution",
            "input_register": {
                "candidate_index_bits": ceil_log2(candidate_count),
                "candidate_index_range": [0, max(candidate_count - 1, 0)],
            },
            "output_register": {
                "contribution": "[0, 1]"
            },
            "reversibility": "classical_model",
            "function": "f(candidate) returns modelled visibility/light contribution for a captured scene candidate.",
            "implementation_status": "model",
        },
        "cost_model": {
            "candidate_count": candidate_count,
            "classical_samples_touched": candidate_count,
            "texture_samples_touched": parse_cache_hit_count(render.get("texcache")),
            "lightmap_samples_touched": parse_cache_hit_count(render.get("lightcache")),
            "state_prep_cost": candidate_count,
            "qram_assumption": "none in v0 exporter; direct classical sidecar model",
            "oracle_eval_count": None,
            "classical_eval_count": None,
            "readout_model": "sidecar_model",
            "shots": int(render.get("shots")) if "shots" in render else None,
            "fallback_count": int(render.get("fallback", 0)) if "fallback" in render else None,
        },
        "trace_summary": {
            "header": trace["header"],
            "records": trace["records"],
            "sequence_errors": trace["sequence_errors"],
            "state_probes": trace["state_probes"],
            "render_sparse_dwt": render_sparse,
            "render_gate_kernel": gate_probe,
        },
        "claims": {
            "related_claim_ids": [
                "compiler.scene_oracle_ir",
                "feasibility.finite_shot_render_observable",
                "advantage.light_transport_qae_query_scaling",
            ]
        },
    }
    claims_evidence = build_claims_evidence(oracle_scene, trace, render, load_claims(claims_path))
    return oracle_scene, claims_evidence


def build_claims_evidence(oracle_scene: dict[str, Any], trace: dict[str, Any],
                          render: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    evidence = {
        "schema": "qge.claims_evidence.v0",
        "source_scene": oracle_scene["scene"]["scene_id"],
        "trace_run_id": oracle_scene["scene"]["trace_run_id"],
        "claims": [],
    }
    for claim in ledger.get("claims", []):
        required = claim.get("required_trace_fields", [])
        present = [
            field for field in required
            if field_available(field, trace, render, oracle_scene)
        ]
        missing = [field for field in required if field not in present]
        if claim.get("claim_id") == "compiler.scene_oracle_ir":
            supported = not missing
            status = "supported" if supported else "blocked"
        elif claim.get("claim_id") == "feasibility.finite_shot_render_observable":
            supported = not missing
            status = "supported" if supported else "blocked"
        else:
            supported = False
            status = claim.get("status", "planned")
        evidence["claims"].append({
            "claim_id": claim.get("claim_id"),
            "ledger_status": claim.get("status"),
            "evidence_status": status,
            "required_fields": required,
            "present_fields": present,
            "missing_fields": missing,
            "allowed_wording": claim.get("allowed_wording"),
            "disallowed_wording": claim.get("disallowed_wording"),
        })
    return evidence


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path, help="QGE graphics stream directory")
    parser.add_argument("--claims", type=Path, default=Path("docs/claims/qge_claims.json"))
    parser.add_argument("--oracle-out", type=Path, help="Output oracle_scene.json path")
    parser.add_argument("--claims-out", type=Path, help="Output claims_evidence.json path")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    capture_dir = args.capture_dir
    claims_path = args.claims
    if not capture_dir.is_dir():
        print(f"qge_oracle_export: capture directory not found: {capture_dir}", file=sys.stderr)
        return 1
    if not (capture_dir / "qge_trace.bin").is_file():
        print(f"qge_oracle_export: missing qge_trace.bin in {capture_dir}", file=sys.stderr)
        return 1
    if not claims_path.is_file():
        print(f"qge_oracle_export: claims ledger not found: {claims_path}", file=sys.stderr)
        return 1

    oracle_scene, claims_evidence = build_oracle_scene(capture_dir, claims_path)
    oracle_out = args.oracle_out or (capture_dir / "oracle_scene.json")
    claims_out = args.claims_out or (capture_dir / "claims_evidence.json")
    write_json(oracle_out, oracle_scene)
    write_json(claims_out, claims_evidence)
    print(f"QGE_ORACLE_SCENE {oracle_out}")
    print(f"QGE_CLAIMS_EVIDENCE {claims_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
