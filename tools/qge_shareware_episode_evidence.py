#!/usr/bin/env python3
"""Regenerate the canonical shareware Episode 1 breadth evidence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_breadth_evidence  # noqa: E402
import qge_map_sets  # noqa: E402


DEFAULT_MATRIX_ROOT = REPO_ROOT / "diagnostics" / "quake_graphics"
DEFAULT_OUTDIR = (
    REPO_ROOT / "diagnostics" / "breadth_evidence" /
    "shareware_episode1"
)
SELECTION_FILENAME = "qge_shareware_episode1_selection.json"
BREADTH_FILENAME = "breadth_evidence.json"
ICC_FILENAME = "qge_breadth_icc_evidence.json"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def iter_matrix_files(matrix_root: Path) -> list[Path]:
    if matrix_root.is_file():
        if matrix_root.name != "vanilla_capture_matrix.json":
            raise ValueError(
                f"matrix file must be vanilla_capture_matrix.json: {matrix_root}"
            )
        return [matrix_root]
    if not matrix_root.is_dir():
        raise ValueError(f"matrix root does not exist: {matrix_root}")
    return sorted(matrix_root.rglob("vanilla_capture_matrix.json"))


def scan_ready_shareware_runs(matrix_root: Path) -> dict[str, Any]:
    target_maps = qge_map_sets.QUAKE_SHAREWARE_EPISODE_ONE_MAPS
    target_set = set(target_maps)
    candidates_by_map: dict[str, list[dict[str, Any]]] = {
        name: [] for name in target_maps
    }
    rejected: list[dict[str, Any]] = []
    scanned_count = 0

    for matrix_path in iter_matrix_files(matrix_root):
        scanned_count += 1
        try:
            summary = qge_breadth_evidence.build_matrix_run_summary(
                matrix_path,
                map_set=qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET,
            )
        except (OSError, ValueError, KeyError, IndexError) as exc:
            rejected.append({
                "matrix_file": str(matrix_path),
                "reason": "scan_error",
                "error": str(exc),
            })
            continue

        map_name = qge_breadth_evidence.canonical_map_name(
            summary.get("map"))
        record = {
            "matrix_file": summary.get("matrix_file"),
            "capture_dir": summary.get("capture_dir"),
            "map": map_name,
            "ready": summary.get("ready"),
            "issues": summary.get("issues", []),
            "route_contract_authority_ready": (
                summary.get("route_contract_authority_ready")),
            "route_contract_authority_blockers": (
                summary.get("route_contract_authority_blockers", [])),
        }
        if map_name not in target_set:
            record["reason"] = "not_shareware_episode1_target"
            rejected.append(record)
            continue
        if summary.get("ready") is not True:
            record["reason"] = "not_ready"
            rejected.append(record)
            continue
        candidates_by_map[map_name].append(record)

    selected_by_map: dict[str, dict[str, Any]] = {}
    for map_name in target_maps:
        candidates = sorted(
            candidates_by_map[map_name],
            key=lambda item: str(item.get("matrix_file") or ""),
        )
        if candidates:
            selected_by_map[map_name] = candidates[-1]

    missing_ready_maps = [
        name for name in target_maps if name not in selected_by_map
    ]
    return {
        "schema": "qge.shareware_episode1_selection.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if not missing_ready_maps else "partial",
        "matrix_root": str(matrix_root),
        "map_set": qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET,
        "map_scope": qge_map_sets.map_set_scope_label(
            qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET),
        "target_maps": target_maps,
        "target_map_count": len(target_maps),
        "scanned_matrix_count": scanned_count,
        "ready_candidate_count": sum(
            len(candidates) for candidates in candidates_by_map.values()),
        "selected_matrix_count": len(selected_by_map),
        "missing_ready_maps": missing_ready_maps,
        "missing_ready_map_count": len(missing_ready_maps),
        "selection_policy": (
            "select lexicographically latest ready vanilla_capture_matrix.json "
            "per shareware Episode 1 target map"
        ),
        "selected_runs": [
            selected_by_map[name] for name in target_maps
            if name in selected_by_map
        ],
        "selected_matrix_files": [
            str(selected_by_map[name]["matrix_file"]) for name in target_maps
            if name in selected_by_map
        ],
        "rejected_runs": rejected,
        "claim_limits": [
            (
                "This selection is scoped to quake_shareware_episode1: start "
                "plus e1m1 through e1m8."
            ),
            (
                "A complete shareware Episode 1 selection is not registered "
                "full-game coverage."
            ),
        ],
    }


def build_shareware_breadth_evidence(
    *,
    matrix_root: Path,
    outdir: Path,
) -> dict[str, Any]:
    selection = scan_ready_shareware_runs(matrix_root)
    selection_path = outdir / SELECTION_FILENAME
    breadth_path = outdir / BREADTH_FILENAME
    icc_path = outdir / ICC_FILENAME
    write_json(selection_path, selection)
    if selection["missing_ready_maps"]:
        raise ValueError(
            "missing ready shareware Episode 1 matrices: " +
            ", ".join(selection["missing_ready_maps"])
        )

    args = SimpleNamespace(
        inputs=[],
        matrix=[Path(path) for path in selection["selected_matrix_files"]],
        publication_pack=[],
        min_runs=selection["target_map_count"],
        min_maps=selection["target_map_count"],
        map_set=qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET,
    )
    manifest = qge_breadth_evidence.build_manifest(args)
    write_json(breadth_path, manifest)
    write_json(
        icc_path,
        qge_breadth_evidence.build_icc_evidence(
            manifest,
            breadth_path,
            icc_path,
        ),
    )
    return {
        "selection_path": selection_path,
        "breadth_path": breadth_path,
        "icc_path": icc_path,
        "selection": selection,
        "manifest": manifest,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-root", type=Path, default=DEFAULT_MATRIX_ROOT)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        result = build_shareware_breadth_evidence(
            matrix_root=args.matrix_root,
            outdir=args.outdir,
        )
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_shareware_episode_evidence: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_SHAREWARE_EPISODE1_SELECTION {result['selection_path']}")
    print(f"QGE_BREADTH_EVIDENCE {result['breadth_path']}")
    print(f"QGE_BREADTH_ICC_EVIDENCE {result['icc_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
