#!/usr/bin/env python3
"""Regenerate the canonical shareware Episode 1 breadth evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_map_set_evidence  # noqa: E402
import qge_map_sets  # noqa: E402


DEFAULT_MATRIX_ROOT = qge_map_set_evidence.DEFAULT_MATRIX_ROOT
DEFAULT_OUTDIR = (
    REPO_ROOT / "diagnostics" / "breadth_evidence" /
    "shareware_episode1"
)
SELECTION_FILENAME = "qge_shareware_episode1_selection.json"
SELECTION_SCHEMA = "qge.shareware_episode1_selection.v0"
BREADTH_FILENAME = qge_map_set_evidence.BREADTH_FILENAME
ICC_FILENAME = qge_map_set_evidence.ICC_FILENAME
write_json = qge_map_set_evidence.write_json
iter_matrix_files = qge_map_set_evidence.iter_matrix_files


def scan_ready_shareware_runs(matrix_root: Path) -> dict[str, Any]:
    return qge_map_set_evidence.scan_ready_map_set_runs(
        matrix_root,
        map_set=qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET,
        selection_schema=SELECTION_SCHEMA,
    )


def build_shareware_breadth_evidence(
    *,
    matrix_root: Path,
    outdir: Path,
) -> dict[str, Any]:
    return qge_map_set_evidence.build_map_set_breadth_evidence(
        matrix_root=matrix_root,
        outdir=outdir,
        map_set=qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET,
        selection_filename=SELECTION_FILENAME,
        selection_schema=SELECTION_SCHEMA,
        require_complete=True,
    )


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
