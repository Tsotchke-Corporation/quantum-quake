#!/usr/bin/env python3
"""Audit registered full-game progress reports."""

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

import qge_registered_full_game_progress as progress_tool  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402


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


def resolve_existing_path(path: Path) -> Path:
    if path.exists() or path.is_absolute():
        return path
    return REPO_ROOT / path


def normalized_progress(value: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(json.dumps(value))
    data.pop("created_utc", None)
    return data


def optional_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    return resolve_existing_path(path)


def progress_audit(
    progress_path: Path,
    *,
    selection_path: Path | None = None,
    matrix_root: Path | None = None,
    asset_root: Path | None = None,
    markdown_path: Path | None = None,
    icc_path: Path | None = None,
) -> dict[str, Any]:
    progress_path = resolve_existing_path(progress_path)
    build_errors: list[str] = []
    try:
        recorded = load_json(progress_path)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        recorded = {}
        build_errors.append(str(exc))

    resolved_selection = optional_path(selection_path)
    if resolved_selection is None:
        raw_selection = recorded.get("selection_file")
        if isinstance(raw_selection, str) and raw_selection:
            resolved_selection = resolve_existing_path(Path(raw_selection))
        else:
            resolved_selection = progress_tool.DEFAULT_SELECTION

    resolved_matrix_root = (
        resolve_existing_path(matrix_root)
        if matrix_root is not None
        else resolve_existing_path(Path(
            recorded.get("matrix_root") or
            progress_tool.qge_map_set_evidence.DEFAULT_MATRIX_ROOT
        ))
    )
    resolved_asset_root = (
        resolve_existing_path(asset_root)
        if asset_root is not None
        else resolve_existing_path(Path(
            recorded.get("asset_root") or
            progress_tool.qge_asset_inventory.DEFAULT_ASSET_ROOT
        ))
    )
    map_set = str(
        recorded.get("map_set") or
        progress_tool.qge_map_sets.DEFAULT_FULL_GAME_MAP_SET
    )

    try:
        expected = progress_tool.build_progress(
            selection_path=resolved_selection,
            matrix_root=resolved_matrix_root,
            asset_root=resolved_asset_root,
            map_set=map_set,
        )
    except (OSError, ValueError, KeyError, IndexError) as exc:
        expected = {}
        build_errors.append(str(exc))

    progress_field_mismatches = (
        qge_resource_boundary_audit.mismatch_paths(
            normalized_progress(expected),
            normalized_progress(recorded),
        )
        if expected and recorded else []
    )

    markdown_mismatch = False
    markdown_error = None
    resolved_markdown_path = optional_path(markdown_path)
    if resolved_markdown_path is not None:
        try:
            recorded_markdown = resolved_markdown_path.read_text(
                encoding="utf-8")
            expected_markdown = (
                progress_tool.markdown_report(expected) if expected else ""
            )
            markdown_mismatch = recorded_markdown != expected_markdown
        except OSError as exc:
            markdown_error = str(exc)
            markdown_mismatch = True

    icc_field_mismatches: list[str] = []
    icc_error = None
    resolved_icc_path = optional_path(icc_path)
    if resolved_icc_path is not None:
        try:
            recorded_icc = load_json(resolved_icc_path)
            expected_icc = (
                progress_tool.build_icc_evidence(expected) if expected else {}
            )
            if expected_icc:
                expected_icc["registered_full_game_progress_file"] = str(
                    progress_path)
            icc_field_mismatches = (
                qge_resource_boundary_audit.mismatch_paths(
                    expected_icc,
                    recorded_icc,
                )
                if expected_icc else []
            )
        except (OSError, ValueError, KeyError, IndexError) as exc:
            icc_error = str(exc)
            icc_field_mismatches = ["<load_error>"]

    mismatch_count = (
        len(progress_field_mismatches) +
        len(icc_field_mismatches) +
        int(markdown_mismatch) +
        len(build_errors)
    )
    return {
        "schema": "qge.registered_full_game_progress_audit.v0",
        "progress_file": str(progress_path),
        "selection_file": str(resolved_selection),
        "matrix_root": str(resolved_matrix_root),
        "asset_root": str(resolved_asset_root),
        "markdown_file": (
            str(resolved_markdown_path) if resolved_markdown_path else None
        ),
        "icc_file": str(resolved_icc_path) if resolved_icc_path else None,
        "progress_field_mismatches": progress_field_mismatches,
        "markdown_mismatch": markdown_mismatch,
        "markdown_error": markdown_error,
        "icc_field_mismatches": icc_field_mismatches,
        "icc_error": icc_error,
        "build_errors": build_errors,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--progress",
        type=Path,
        default=progress_tool.DEFAULT_OUTDIR / progress_tool.PROGRESS_FILENAME,
    )
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--matrix-root", type=Path)
    parser.add_argument("--asset-root", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--icc-json", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit nonzero when the progress report is stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        audit = progress_audit(
            args.progress,
            selection_path=args.selection,
            matrix_root=args.matrix_root,
            asset_root=args.asset_root,
            markdown_path=args.markdown,
            icc_path=args.icc_json,
        )
        if args.out:
            write_json(args.out, audit)
            print(f"QGE_REGISTERED_FULL_GAME_PROGRESS_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_registered_full_game_progress_audit: {exc}",
              file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
