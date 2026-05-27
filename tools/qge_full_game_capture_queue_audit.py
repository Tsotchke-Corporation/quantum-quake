#!/usr/bin/env python3
"""Audit QGE full-game capture queue outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_full_game_capture_queue as queue_tool  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402

PACK_QUEUE_PATH = Path("resource/qge_full_game_capture_queue.json")
PACK_SOURCE_PATH = Path("resource/qge_registered_full_game_progress.json")
PACK_SCRIPT_PATH = Path("resource/run_missing_maps.sh")
PACK_MARKDOWN_PATH = Path("resource/qge_full_game_capture_queue.md")


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


def resolve_existing_path(path: Path) -> Path:
    if path.exists() or path.is_absolute():
        return path
    return REPO_ROOT / path


def normalized_queue(value: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(json.dumps(value))
    data.pop("created_utc", None)
    return data


def queue_args_from_recorded(
    recorded: dict[str, Any],
    *,
    source: Path | None = None,
    asset_root: Path | None = None,
) -> SimpleNamespace:
    reproduction = dict_or_empty(recorded.get("reproduction"))
    raw_source = source or Path(
        reproduction.get("source") or recorded.get("source_path") or ".")
    raw_asset_root = asset_root or Path(
        reproduction.get("asset_root") or
        recorded.get("asset_root") or
        queue_tool.DEFAULT_ASSET_ROOT
    )
    return SimpleNamespace(
        source=resolve_existing_path(raw_source),
        asset_root=resolve_existing_path(raw_asset_root),
        limit=reproduction.get("limit"),
        frames=int(reproduction.get("frames", 4)),
        wait_frames=int(reproduction.get("wait_frames", 35)),
        trace=bool(reproduction.get("trace", True)),
        special_maps_last=bool(reproduction.get("special_maps_last", True)),
        authority_smoke=bool(reproduction.get("authority_smoke", True)),
        force_world_metrics=bool(
            reproduction.get("force_world_metrics", True)),
        include_unavailable_assets=bool(
            reproduction.get("include_unavailable_assets",
                             not recorded.get("asset_filter_enabled", True))),
        env=list(reproduction.get("env") or []),
    )


def optional_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    return resolve_existing_path(path)


def resolved_audit_inputs(
    target: Path,
    *,
    source: Path | None = None,
    script_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Path | None]:
    resolved_target = resolve_existing_path(target)
    pack_dir = resolved_target if resolved_target.is_dir() else None
    if pack_dir is None:
        return {
            "pack_dir": None,
            "queue": resolved_target,
            "source": source,
            "script": script_path,
            "markdown": markdown_path,
        }
    return {
        "pack_dir": pack_dir,
        "queue": pack_dir / PACK_QUEUE_PATH,
        "source": source or pack_dir / PACK_SOURCE_PATH,
        "script": script_path or pack_dir / PACK_SCRIPT_PATH,
        "markdown": markdown_path or pack_dir / PACK_MARKDOWN_PATH,
    }


def capture_queue_audit(
    queue_path: Path,
    *,
    source: Path | None = None,
    asset_root: Path | None = None,
    script_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    resolved_inputs = resolved_audit_inputs(
        queue_path,
        source=source,
        script_path=script_path,
        markdown_path=markdown_path,
    )
    pack_dir = resolved_inputs["pack_dir"]
    queue_path = resolved_inputs["queue"]
    source = resolved_inputs["source"]
    script_path = resolved_inputs["script"]
    markdown_path = resolved_inputs["markdown"]
    assert isinstance(queue_path, Path)
    build_errors: list[str] = []
    try:
        recorded = load_json(queue_path)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        recorded = {}
        build_errors.append(str(exc))

    try:
        args = queue_args_from_recorded(
            recorded,
            source=source,
            asset_root=asset_root,
        )
        expected = queue_tool.build_queue(args)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        args = SimpleNamespace(
            source=source or Path("."),
            asset_root=asset_root or queue_tool.DEFAULT_ASSET_ROOT,
        )
        expected = {}
        build_errors.append(str(exc))

    queue_field_mismatches = (
        qge_resource_boundary_audit.mismatch_paths(
            normalized_queue(expected),
            normalized_queue(recorded),
        )
        if expected and recorded else []
    )

    resolved_script_path = optional_path(script_path)
    script_mismatch = False
    script_error = None
    if resolved_script_path is not None:
        try:
            expected_script = "\n".join(
                queue_tool.script_lines(expected)) if expected else ""
            recorded_script = resolved_script_path.read_text(
                encoding="utf-8")
            script_mismatch = recorded_script != expected_script
        except OSError as exc:
            script_error = str(exc)
            script_mismatch = True

    resolved_markdown_path = optional_path(markdown_path)
    markdown_mismatch = False
    markdown_error = None
    if resolved_markdown_path is not None:
        try:
            expected_markdown = (
                queue_tool.markdown_report(expected) if expected else ""
            )
            recorded_markdown = resolved_markdown_path.read_text(
                encoding="utf-8")
            markdown_mismatch = recorded_markdown != expected_markdown
        except OSError as exc:
            markdown_error = str(exc)
            markdown_mismatch = True

    mismatch_count = (
        len(queue_field_mismatches) +
        int(script_mismatch) +
        int(markdown_mismatch) +
        len(build_errors)
    )
    return {
        "schema": "qge.full_game_capture_queue_audit.v0",
        "pack_dir": str(pack_dir) if isinstance(pack_dir, Path) else None,
        "queue_file": str(queue_path),
        "source": str(getattr(args, "source", "")),
        "asset_root": str(getattr(args, "asset_root", "")),
        "script_file": (
            str(resolved_script_path) if resolved_script_path else None
        ),
        "markdown_file": (
            str(resolved_markdown_path) if resolved_markdown_path else None
        ),
        "queue_field_mismatches": queue_field_mismatches,
        "script_mismatch": script_mismatch,
        "script_error": script_error,
        "markdown_mismatch": markdown_mismatch,
        "markdown_error": markdown_error,
        "build_errors": build_errors,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue", nargs="?", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--asset-root", type=Path)
    parser.add_argument("--script", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit nonzero when the queue, script, or Markdown is stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    queue_path = args.queue or (
        REPO_ROOT / "diagnostics" / "full_game_capture_queue" /
        "capture_queue.json"
    )
    try:
        audit = capture_queue_audit(
            queue_path,
            source=args.source,
            asset_root=args.asset_root,
            script_path=args.script,
            markdown_path=args.markdown,
        )
        if args.out:
            write_json(args.out, audit)
            print(f"QGE_FULL_GAME_CAPTURE_QUEUE_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_full_game_capture_queue_audit: {exc}",
              file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
