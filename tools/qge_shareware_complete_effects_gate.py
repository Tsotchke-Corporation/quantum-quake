#!/usr/bin/env python3
"""Compose the complete shareware effects matrix into an ICC-ready gate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

GATE_SCHEMA = "qge.shareware_complete_effects_gate.v0"
FOOTAGE_SCHEMA = "qge.shareware_effects_footage_manifest.v0"
ICC_SCHEMA = "qge.icc_evidence.v0"
DEFAULT_EFFECTS_ROOT = REPO_ROOT / "diagnostics" / "shareware_effects"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return default


def latest_file(root: Path, name: str) -> Path | None:
    candidates = sorted(root.glob(f"*/{name}"))
    return candidates[-1] if candidates else None


def build_footage_manifest(matrix: dict[str, Any],
                           matrix_path: Path) -> dict[str, Any]:
    runtime = dict_or_empty(matrix.get("runtime"))
    footage_index = [
        item for item in runtime.get("footage_index", [])
        if isinstance(item, dict)
    ]
    maps_with_footage = sorted(
        str(name) for name in runtime.get("maps_with_footage", [])
    )
    status = "complete" if footage_index else "blocked"
    return {
        "schema": FOOTAGE_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "source_matrix_file": str(matrix_path),
        "map_set": matrix.get("map_set"),
        "capture_count": len(footage_index),
        "maps_with_footage": maps_with_footage,
        "captures": footage_index,
    }


def build_gate(*,
               matrix: dict[str, Any],
               matrix_path: Path,
               inventory: dict[str, Any],
               inventory_path: Path,
               footage_manifest: dict[str, Any],
               footage_manifest_path: Path) -> dict[str, Any]:
    criteria = {
        str(item.get("id")): item.get("status")
        for item in matrix.get("criteria", [])
        if isinstance(item, dict)
    }
    failed_criteria = [
        key for key, status in sorted(criteria.items())
        if status != "pass"
    ]
    matrix_ready = matrix.get("status") == "complete"
    inventory_ready = inventory.get("status") == "complete"
    footage_ready = footage_manifest.get("status") == "complete"
    status = (
        "ready_for_shareware_complete_effects_claim"
        if matrix_ready and inventory_ready and footage_ready and not failed_criteria
        else "blocked"
    )
    return {
        "schema": GATE_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "map_set": matrix.get("map_set"),
        "source_matrix_file": str(matrix_path),
        "source_inventory_file": str(inventory_path),
        "footage_manifest_file": str(footage_manifest_path),
        "criteria": {
            "matrix_complete": matrix_ready,
            "inventory_complete": inventory_ready,
            "footage_manifest_complete": footage_ready,
            "matrix_failed_criteria": failed_criteria,
        },
        "summary": {
            "ready_for_complete_effects_claim": status != "blocked",
            "matrix_status": matrix.get("status"),
            "inventory_status": inventory.get("status"),
            "footage_status": footage_manifest.get("status"),
            "footage_capture_count": footage_manifest.get("capture_count"),
            "matrix_summary": matrix.get("summary"),
        },
    }


def build_icc_evidence(gate: dict[str, Any],
                       gate_path: Path,
                       matrix_path: Path,
                       inventory_path: Path,
                       footage_manifest_path: Path) -> dict[str, Any]:
    ready = gate.get("status") == "ready_for_shareware_complete_effects_claim"
    matrix_summary = dict_or_empty(
        dict_or_empty(gate.get("summary")).get("matrix_summary"))
    evidence: dict[str, Any] = {
        "schema": ICC_SCHEMA,
        "runtime_backend": "qge_shareware_complete_effects",
        "completion_reason": (
            "qge_shareware_complete_effects_ready"
            if ready else "qge_shareware_complete_effects_blocked"
        ),
        "runtime_backend_scope_map_set": gate.get("map_set"),
        "shareware_complete_effects_gate_file": str(gate_path),
        "qge_shareware_complete_effects_gate.json": str(gate_path),
        "shareware_effects_inventory_file": str(inventory_path),
        "qge_shareware_effects_inventory.json": str(inventory_path),
        "shareware_effects_matrix_file": str(matrix_path),
        "qge_shareware_effects_matrix.json": str(matrix_path),
        "shareware_effects_footage_file": str(footage_manifest_path),
        "qge_shareware_effects_footage_manifest.json": str(
            footage_manifest_path),
        "shareware_complete_effects_gate_status": gate.get("status"),
    }
    if ready:
        evidence.update({
            "qge_shareware_complete_effects_ready": True,
            "shareware_effects_map_coverage_completion": "complete",
            "shareware_slipgate_effect_evidence_completion": "present",
            "shareware_enemy_effect_evidence_completion": "complete",
            "shareware_material_effect_evidence_completion": "complete",
            "shareware_projectile_effect_evidence_completion": "complete",
            "shareware_particle_sprite_effect_evidence_completion": "complete",
            "shareware_audio_effect_evidence_completion": "complete",
            "shareware_noesis_replay_effect_evidence_completion": "complete",
            "shareware_effects_footage_completion": "complete",
            "shareware_effects_footage_capture_count": matrix_summary.get(
                "runtime_footage_capture_count"),
        })
    return evidence


def markdown_report(gate: dict[str, Any]) -> str:
    summary = dict_or_empty(gate.get("summary"))
    return "\n".join([
        "# QGE Shareware Complete Effects Gate",
        "",
        f"- `status`: `{gate.get('status')}`",
        f"- `map_set`: `{gate.get('map_set')}`",
        f"- `matrix_status`: `{summary.get('matrix_status')}`",
        f"- `inventory_status`: `{summary.get('inventory_status')}`",
        f"- `footage_status`: `{summary.get('footage_status')}`",
        f"- `footage_capture_count`: `{summary.get('footage_capture_count')}`",
        "",
    ])


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    parser.add_argument("--footage-manifest", type=Path)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_EFFECTS_ROOT)
    parser.add_argument("--fail-on-blocked", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    matrix_path = args.matrix or latest_file(
        args.out_root, "qge_shareware_effects_matrix.json")
    if matrix_path is None:
        raise SystemExit("no shareware effects matrix found")
    matrix = load_json(matrix_path)
    inventory_path = args.inventory
    if inventory_path is None:
        inventory_value = matrix.get("source_inventory_file")
        inventory_path = Path(str(inventory_value)) if inventory_value else None
    if inventory_path is None:
        inventory_path = latest_file(
            args.out_root, "qge_shareware_effects_inventory.json")
    if inventory_path is None:
        raise SystemExit("no shareware effects inventory found")
    inventory = load_json(inventory_path)

    run_dir = args.out_root / datetime.now(timezone.utc).strftime(
        "%Y%m%d-%H%M%S")
    out_path = args.out or run_dir / "qge_shareware_complete_effects_gate.json"
    markdown_path = args.markdown or out_path.with_suffix(".md")
    icc_path = args.icc_json or out_path.with_name(
        "qge_shareware_complete_effects_icc_evidence.json")
    footage_path = args.footage_manifest or out_path.with_name(
        "qge_shareware_effects_footage_manifest.json")

    footage_manifest = build_footage_manifest(matrix, matrix_path)
    write_json(footage_path, footage_manifest)
    gate = build_gate(
        matrix=matrix,
        matrix_path=matrix_path,
        inventory=inventory,
        inventory_path=inventory_path,
        footage_manifest=footage_manifest,
        footage_manifest_path=footage_path,
    )
    write_json(out_path, gate)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown_report(gate), encoding="utf-8")
    write_json(
        icc_path,
        build_icc_evidence(
            gate,
            out_path,
            matrix_path,
            inventory_path,
            footage_path,
        ),
    )
    print(f"QGE_SHAREWARE_COMPLETE_EFFECTS_GATE {out_path}")
    print(f"QGE_SHAREWARE_COMPLETE_EFFECTS_GATE_MARKDOWN {markdown_path}")
    print(f"QGE_SHAREWARE_COMPLETE_EFFECTS_GATE_ICC {icc_path}")
    print(f"QGE_SHAREWARE_EFFECTS_FOOTAGE_MANIFEST {footage_path}")
    if args.fail_on_blocked and gate.get("status") == "blocked":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
