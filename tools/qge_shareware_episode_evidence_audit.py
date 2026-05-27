#!/usr/bin/env python3
"""Audit regenerated shareware Episode 1 breadth evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_breadth_evidence  # noqa: E402
import qge_breadth_evidence_audit  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402
import qge_shareware_episode_evidence  # noqa: E402


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def resolve_existing_path(raw_path: Path) -> Path:
    if raw_path.exists() or raw_path.is_absolute():
        return raw_path
    return REPO_ROOT / raw_path


def normalized_selection(value: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(json.dumps(dict_or_empty(value)))
    data.pop("created_utc", None)
    return data


def selection_path(evidence_dir: Path) -> Path:
    return evidence_dir / qge_shareware_episode_evidence.SELECTION_FILENAME


def breadth_path(evidence_dir: Path) -> Path:
    return evidence_dir / qge_shareware_episode_evidence.BREADTH_FILENAME


def icc_path(evidence_dir: Path) -> Path:
    return evidence_dir / qge_shareware_episode_evidence.ICC_FILENAME


def recorded_matrix_root(
    selection: dict[str, Any],
    override: Path | None,
) -> Path:
    if override is not None:
        return override
    raw_root = selection.get("matrix_root")
    if not isinstance(raw_root, str) or not raw_root:
        return qge_shareware_episode_evidence.DEFAULT_MATRIX_ROOT
    return resolve_existing_path(Path(raw_root))


def shareware_episode_evidence_audit(
    evidence_dir: Path,
    *,
    matrix_root: Path | None = None,
) -> dict[str, Any]:
    evidence_dir = resolve_existing_path(evidence_dir)
    paths = {
        "selection": selection_path(evidence_dir),
        "breadth": breadth_path(evidence_dir),
        "icc": icc_path(evidence_dir),
    }
    build_errors: list[str] = []
    try:
        recorded_selection = load_json(paths["selection"])
        root = recorded_matrix_root(recorded_selection, matrix_root)
        expected_selection = (
            qge_shareware_episode_evidence.scan_ready_shareware_runs(root)
        )
    except (OSError, ValueError, KeyError, IndexError) as exc:
        recorded_selection = {}
        expected_selection = {}
        root = matrix_root or qge_shareware_episode_evidence.DEFAULT_MATRIX_ROOT
        build_errors.append(str(exc))

    try:
        recorded_breadth = load_json(paths["breadth"])
    except (OSError, ValueError, KeyError, IndexError) as exc:
        recorded_breadth = {}
        build_errors.append(str(exc))

    try:
        recorded_icc = load_json(paths["icc"])
    except (OSError, ValueError, KeyError, IndexError) as exc:
        recorded_icc = {}
        build_errors.append(str(exc))

    selection_field_mismatches = (
        qge_resource_boundary_audit.mismatch_paths(
            normalized_selection(expected_selection),
            normalized_selection(recorded_selection),
        )
        if expected_selection and recorded_selection else []
    )
    breadth_audit = qge_breadth_evidence_audit.breadth_evidence_audit(
        recorded_breadth,
        required=True,
    )
    expected_icc = (
        qge_breadth_evidence.build_icc_evidence(
            recorded_breadth,
            paths["breadth"],
            paths["icc"],
        )
        if recorded_breadth else {}
    )
    icc_field_mismatches = (
        qge_resource_boundary_audit.mismatch_paths(
            expected_icc,
            recorded_icc,
        )
        if expected_icc and recorded_icc else []
    )
    mismatch_count = (
        len(selection_field_mismatches) +
        int(breadth_audit.get("mismatch_count") or 0) +
        len(icc_field_mismatches) +
        len(build_errors)
    )
    return {
        "schema": "qge.shareware_episode1_evidence_audit.v0",
        "evidence_dir": str(evidence_dir),
        "matrix_root": str(root),
        "selection_file": str(paths["selection"]),
        "breadth_evidence_file": str(paths["breadth"]),
        "breadth_icc_evidence_file": str(paths["icc"]),
        "selection_field_mismatches": selection_field_mismatches,
        "breadth_field_mismatches": breadth_audit.get(
            "field_mismatches", []),
        "breadth_overclaim_flags": breadth_audit.get(
            "overclaim_flags", []),
        "breadth_build_errors": breadth_audit.get("build_errors", []),
        "icc_field_mismatches": icc_field_mismatches,
        "build_errors": build_errors,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "evidence_dir",
        nargs="?",
        type=Path,
        default=qge_shareware_episode_evidence.DEFAULT_OUTDIR,
    )
    parser.add_argument("--matrix-root", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit nonzero when the generated evidence is stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        audit = shareware_episode_evidence_audit(
            args.evidence_dir,
            matrix_root=args.matrix_root,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_SHAREWARE_EPISODE1_EVIDENCE_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_shareware_episode_evidence_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
