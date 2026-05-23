#!/usr/bin/env python3
"""Build a runnable capture queue from QGE full-game map coverage."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_breadth_evidence  # noqa: E402

DEFAULT_ENV = {
    "QGE_HARNESS_FRAMES": "4",
    "QGE_HARNESS_WAIT_FRAMES": "35",
    "QGE_STREAM_LAUNCH": "direct",
    "QGE_STREAM_MOUSE": "0",
    "QGE_STREAM_PLAYER": "noesis",
    "QGE_STREAM_ACTIVATE": "0",
    "QGE_STREAM_TRACE": "1",
    "QGE_STREAM_FIRE_MIN_FRAMES": "4",
    "QGE_NOESIS_MIN_CAPTURE_WAIT": "100",
    "QGE_HARNESS_SOUND": "1",
    "QGE_HARNESS_FIRE_TEST": "1",
    "QGE_HARNESS_SPRITE_TEST": "1",
    "QGE_HARNESS_PARTICLES": "1",
    "QGE_HARNESS_SND_QUANTUM": "2",
    "QGE_HARNESS_SND_QUANTUM_SOURCE_AUTHORITY": "1",
    "QGE_HARNESS_PHYSICS_AUTHORITATIVE": "1",
    "QGE_HARNESS_FORCE_WORLD_METRICS": "1",
    "QGE_RENDER_RES": "1024",
    "QGE_RENDER_THRESHOLD": "0.001",
    "QGE_RENDER_EDGE_GAIN": "0",
    "QGE_RENDER_MATERIAL_GAIN": "0.18",
    "QGE_RENDER_EDGE_SAMPLES": "0",
}
SPECIAL_ROUTE_MAPS = {"start", "end"}


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


def resolve_source_path(path: Path) -> Path:
    if path.is_dir():
        candidates = [
            path / "publication_manifest.json",
            path / "breadth_evidence.json",
            path / "resource" / "qge_full_game_map_coverage.json",
            path / "full_game_map_coverage.json",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    return path


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def existing_matrix_sources(data: dict[str, Any]) -> list[str]:
    schema = data.get("schema")
    if schema == "qge.breadth_evidence.v0":
        sources = []
        for run in list_or_empty(data.get("matrix_runs")):
            if not isinstance(run, dict):
                continue
            source = run.get("source_path") or run.get("matrix_file")
            if isinstance(source, str) and source:
                sources.append(source)
        return sources
    if schema == "qge.publication_pack.v0":
        source_inputs = dict_or_empty(data.get("source_inputs"))
        breadth_path = source_inputs.get("breadth_evidence")
        if not isinstance(breadth_path, str) or not breadth_path:
            return []
        path = Path(breadth_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            return []
        try:
            return existing_matrix_sources(load_json(path))
        except (OSError, ValueError):
            return []
    return []


def coverage_from_data(data: dict[str, Any]) -> dict[str, Any]:
    schema = data.get("schema")
    if schema == "qge.full_game_map_coverage.v0":
        return data
    if schema == "qge.breadth_evidence.v0":
        coverage = data.get("full_game_coverage")
        if not isinstance(coverage, dict):
            aggregate = dict_or_empty(data.get("aggregate"))
            coverage = aggregate.get("full_game_coverage")
        if isinstance(coverage, dict):
            return coverage
        aggregate = dict_or_empty(data.get("aggregate"))
        return qge_breadth_evidence.build_full_game_map_coverage(
            list_or_empty(aggregate.get("maps")))
    if schema == "qge.publication_pack.v0":
        runtime = dict_or_empty(data.get("runtime_summary"))
        coverage = runtime.get("full_game_map_coverage")
        if isinstance(coverage, dict):
            return coverage
        return qge_breadth_evidence.build_full_game_map_coverage(
            list_or_empty(runtime.get("breadth_maps")))
    raise ValueError(f"unsupported source schema: {schema!r}")


def shell_env(env: dict[str, str]) -> str:
    return " ".join(
        f"{key}={shlex.quote(value)}" for key, value in sorted(env.items()))


def harness_command(env: dict[str, str]) -> str:
    return f"{shell_env(env)} bash tools/quake_graphics_harness.sh"


def queue_environment(args: argparse.Namespace, map_name: str) -> dict[str, str]:
    env = dict(DEFAULT_ENV)
    env.update({
        "QGE_HARNESS_MAP": map_name,
        "QGE_HARNESS_FRAMES": str(args.frames),
        "QGE_HARNESS_WAIT_FRAMES": str(args.wait_frames),
        "QGE_STREAM_TRACE": "1" if args.trace else "0",
    })
    if not getattr(args, "authority_smoke", True):
        env.update({
            "QGE_HARNESS_SOUND": "0",
            "QGE_HARNESS_FIRE_TEST": "0",
            "QGE_HARNESS_SPRITE_TEST": "0",
            "QGE_HARNESS_PARTICLES": "0",
            "QGE_HARNESS_SND_QUANTUM": "1",
            "QGE_HARNESS_SND_QUANTUM_SOURCE_AUTHORITY": "0",
            "QGE_HARNESS_PHYSICS_AUTHORITATIVE": "0",
        })
    env["QGE_HARNESS_FORCE_WORLD_METRICS"] = (
        "1" if args.force_world_metrics else "0"
    )
    for item in args.env or []:
        key, value = item.split("=", 1)
        env[key] = value
    return env


def selected_missing_maps(
    coverage: dict[str, Any],
    limit: int | None,
    special_maps_last: bool = True,
) -> list[str]:
    missing = [
        item for item in list_or_empty(coverage.get("missing_maps"))
        if isinstance(item, str)
    ]
    if special_maps_last:
        missing = (
            [name for name in missing if name not in SPECIAL_ROUTE_MAPS] +
            [name for name in missing if name in SPECIAL_ROUTE_MAPS]
        )
    if limit is not None:
        missing = missing[:limit]
    return missing


def build_queue(args: argparse.Namespace) -> dict[str, Any]:
    source_path = resolve_source_path(args.source)
    data = load_json(source_path)
    coverage = coverage_from_data(data)
    special_maps_last = getattr(args, "special_maps_last", True)
    missing_maps = selected_missing_maps(coverage, args.limit, special_maps_last)
    existing_sources = existing_matrix_sources(data)
    jobs = []
    for index, map_name in enumerate(missing_maps, start=1):
        env = queue_environment(args, map_name)
        jobs.append({
            "index": index,
            "map": map_name,
            "route_profile": (
                "special_route_required"
                if map_name in SPECIAL_ROUTE_MAPS
                else "noesis_authority_smoke"
            ),
            "status": "pending_capture",
            "environment": env,
            "command": ["bash", "tools/quake_graphics_harness.sh"],
            "shell_command": harness_command(env),
        })
    target_after_queue = int(coverage.get("covered_map_count", 0) or 0) + len(jobs)
    target_map_count = int(coverage.get("target_map_count", 0) or 0)
    return {
        "schema": "qge.full_game_capture_queue.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path),
        "source_schema": data.get("schema"),
        "status": "complete" if not jobs else "pending",
        "special_maps_last": special_maps_last,
        "special_route_maps": sorted(SPECIAL_ROUTE_MAPS),
        "coverage_before": coverage,
        "existing_matrix_sources": existing_sources,
        "queue_job_count": len(jobs),
        "target_map_count": target_map_count,
        "covered_map_count_before": coverage.get("covered_map_count"),
        "covered_map_count_after_queue": target_after_queue,
        "remaining_map_count_after_queue": max(
            target_map_count - target_after_queue, 0),
        "jobs": jobs,
        "post_capture": {
            "breadth_min_runs": len(existing_sources) + len(jobs),
            "breadth_min_maps": target_after_queue,
            "command": (
                "tools/qge_breadth_evidence.py with every existing matrix "
                "plus every successful queued capture directory"
            ),
        },
        "limits": [
            "This queue does not prove coverage until the generated captures run.",
            "Every queued harness output must still pass the strict breadth gates.",
            "Maps with route_profile=special_route_required are ordered last because they need noncombat/endgame-specific evidence, not a weakened Moonlab claim.",
            "Do not claim full-game map coverage until remaining_map_count_after_queue is zero and the rebuilt breadth artifact is complete.",
        ],
    }


def script_lines(queue: dict[str, Any]) -> list[str]:
    existing = [
        item for item in list_or_empty(queue.get("existing_matrix_sources"))
        if isinstance(item, str)
    ]
    jobs = [
        item for item in list_or_empty(queue.get("jobs"))
        if isinstance(item, dict)
    ]
    post_capture = dict_or_empty(queue.get("post_capture"))
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        f"repo_root={shlex.quote(str(REPO_ROOT))}",
        'cd "$repo_root"',
        "",
        "capture_dirs=()",
        "",
    ]
    for job in jobs:
        map_name = str(job.get("map"))
        env = {
            key: str(value)
            for key, value in dict_or_empty(job.get("environment")).items()
        }
        lines.extend([
            f"echo QGE_FULL_GAME_CAPTURE_QUEUE_MAP {shlex.quote(map_name)}",
            "capture_output=\"$(",
            f"  {harness_command(env)}",
            ")\"",
            'printf "%s\\n" "$capture_output"',
            "capture_dir=\"$(",
            '  printf "%s\\n" "$capture_output" |',
            "  awk '/QGE_GRAPHICS_HARNESS_DONE / {print $2}' |",
            "  tail -n 1",
            ")\"",
            'if [[ -z "$capture_dir" || ! -d "$capture_dir" ]]; then',
            f"  echo \"capture failed for {map_name}\" >&2",
            "  exit 1",
            "fi",
            'capture_dirs+=("$capture_dir")',
            "",
        ])
    lines.extend([
        "breadth_args=()",
    ])
    for source in existing:
        lines.append(f"breadth_args+=(--matrix {shlex.quote(source)})")
    lines.extend([
        'for capture_dir in "${capture_dirs[@]}"; do',
        '  breadth_args+=(--matrix "$capture_dir")',
        "done",
        "",
        'if (( ${#breadth_args[@]} > 0 )); then',
        "  python3 tools/qge_breadth_evidence.py \\",
        '    "${breadth_args[@]}" \\',
        f"    --min-runs {int(post_capture.get('breadth_min_runs', 1) or 1)} \\",
        f"    --min-maps {int(post_capture.get('breadth_min_maps', 1) or 1)}",
        "fi",
        "",
    ])
    return lines


def markdown_report(queue: dict[str, Any]) -> str:
    coverage = dict_or_empty(queue.get("coverage_before"))
    lines = [
        "# QGE Full Game Capture Queue",
        "",
        f"Status: {queue['status']}",
        f"Source: `{queue['source_path']}`",
        "",
        "| Map Set | Covered Before | Jobs | Covered After Queue | Remaining |",
        "| --- | ---: | ---: | ---: | ---: |",
        (
            f"| {coverage.get('map_set')} | "
            f"{queue.get('covered_map_count_before')} / "
            f"{queue.get('target_map_count')} | "
            f"{queue.get('queue_job_count')} | "
            f"{queue.get('covered_map_count_after_queue')} / "
            f"{queue.get('target_map_count')} | "
            f"{queue.get('remaining_map_count_after_queue')} |"
        ),
        "",
        "| # | Map | Route Profile | Command |",
        "| ---: | --- | --- | --- |",
    ]
    for job in list_or_empty(queue.get("jobs")):
        if not isinstance(job, dict):
            continue
        lines.append(
            f"| {job.get('index')} | {job.get('map')} | "
            f"{job.get('route_profile')} | "
            f"`{job.get('shell_command')}` |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_env(value: str) -> str:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--env values must be KEY=VALUE")
    key, _value = value.split("=", 1)
    if not key or any(ch in key for ch in " \t\n="):
        raise argparse.ArgumentTypeError("--env key is invalid")
    return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_out = (
        REPO_ROOT / "diagnostics" / "full_game_capture_queue" /
        stamp / "capture_queue.json"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path,
                        help="Coverage JSON, breadth evidence, or publication pack")
    parser.add_argument("--out", type=Path, default=default_out)
    parser.add_argument("--script-out", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--limit", type=int,
                        help="Only queue the first N missing maps")
    parser.add_argument("--frames", type=int, default=4)
    parser.add_argument("--wait-frames", type=int, default=35)
    parser.add_argument("--trace", action=argparse.BooleanOptionalAction,
                        default=True)
    parser.add_argument("--special-maps-last",
                        action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Queue start/end after combat maps because they require special route evidence")
    parser.add_argument("--authority-smoke",
                        action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Enable fire, sprite, particles, sound-source, and projectile authority smoke")
    parser.add_argument("--force-world-metrics",
                        action=argparse.BooleanOptionalAction,
                        default=True)
    parser.add_argument("--env", action="append", type=parse_env,
                        help="Extra KEY=VALUE environment override")
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if args.limit is not None and args.limit < 0:
        raise ValueError("--limit must be >= 0")
    if args.frames <= 0:
        raise ValueError("--frames must be > 0")
    if args.wait_frames <= 0:
        raise ValueError("--wait-frames must be > 0")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        validate_args(args)
        queue = build_queue(args)
        script_out = (
            args.script_out or args.out.parent / "run_missing_maps.sh"
        )
        write_json(args.out, queue)
        script_out.parent.mkdir(parents=True, exist_ok=True)
        script_out.write_text("\n".join(script_lines(queue)), encoding="utf-8")
        script_out.chmod(script_out.stat().st_mode | 0o111)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown_report(queue), encoding="utf-8")
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_full_game_capture_queue: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_FULL_GAME_CAPTURE_QUEUE {args.out}")
    print(f"QGE_FULL_GAME_CAPTURE_SCRIPT {script_out}")
    if args.markdown:
        print(f"QGE_FULL_GAME_CAPTURE_QUEUE_MARKDOWN {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
