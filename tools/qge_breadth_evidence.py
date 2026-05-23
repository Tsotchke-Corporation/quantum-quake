#!/usr/bin/env python3
"""Aggregate QGE/Moonlab readiness over multiple capture artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


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


def as_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def as_bool(value: Any) -> bool:
    return bool(value)


def read_readme_value(path: Path, label: str) -> str | None:
    if not path.is_file():
        return None
    prefix = f"{label}:"
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(prefix):
                return line.split(":", 1)[1].strip()
    return None


def resolve_matrix_path(path: Path) -> Path:
    if path.is_dir():
        direct = path / "vanilla_capture_matrix.json"
        packed = path / "vanilla" / "vanilla_capture_matrix.json"
        if direct.is_file():
            return direct
        if packed.is_file():
            return packed
    return path


def resolve_publication_manifest_path(path: Path) -> Path:
    if path.is_dir():
        return path / "publication_manifest.json"
    return path


def detect_input_kind(path: Path) -> str:
    if path.is_dir():
        if (path / "publication_manifest.json").is_file():
            return "publication"
        if (path / "vanilla_capture_matrix.json").is_file():
            return "matrix"
        if (path / "vanilla" / "vanilla_capture_matrix.json").is_file():
            return "matrix"
    if path.name == "publication_manifest.json":
        return "publication"
    if path.name == "vanilla_capture_matrix.json":
        return "matrix"
    raise ValueError(f"cannot classify input path: {path}")


def domain_evidence(summary: dict[str, Any], name: str) -> dict[str, Any]:
    domains = summary.get("moonlab_domain_readiness", {})
    if not isinstance(domains, dict):
        return {}
    entry = domains.get(name, {})
    if not isinstance(entry, dict):
        return {}
    evidence = entry.get("evidence", {})
    return evidence if isinstance(evidence, dict) else {}


def map_name_for_matrix(matrix: dict[str, Any], matrix_path: Path) -> str | None:
    capture_dir = matrix.get("capture_dir")
    candidates = []
    if isinstance(capture_dir, str):
        candidates.append(Path(capture_dir) / "README.txt")
    candidates.append(matrix_path.parent / "README.txt")
    for candidate in candidates:
        value = read_readme_value(candidate, "Map")
        if value:
            return value
    return None


def matrix_run_summary(path: Path) -> dict[str, Any]:
    matrix_path = resolve_matrix_path(path)
    matrix = load_json(matrix_path)
    summary = matrix.get("conformance_summary", {})
    if not isinstance(summary, dict):
        raise ValueError(f"{matrix_path} is missing conformance_summary")

    primary = domain_evidence(summary, "qge_primary_framebuffer")
    render = domain_evidence(summary, "render_quantum_workload")
    fallback_count = as_int(summary.get("fallback_count"))
    surrogate_count = as_int(summary.get("qge_surface_surrogates"))
    if "fallback_count" in primary:
        fallback_count = max(fallback_count, as_int(primary.get("fallback_count")))
    if "surrogate_count" in primary:
        surrogate_count = max(surrogate_count, as_int(primary.get("surrogate_count")))

    native_bridge_count = max(
        as_int(render.get("native_bridge_count")),
        as_int(summary.get("qge_render_native_idwt")),
    )
    cpu_idwt_count = max(
        as_int(render.get("cpu_idwt_count")),
        as_int(summary.get("qge_render_cpu_idwt")),
    )
    idwt_backend = (
        render.get("idwt_backend") or summary.get("qge_render_idwt_backend"))
    qge_primary_owner = primary.get("owner") or summary.get("qge_primary_owner")

    issues = []
    if not as_bool(summary.get("ready_for_complete_claim")):
        issues.append("matrix_not_ready")
    if not as_bool(summary.get("moonlab_authority_ready")):
        issues.append("moonlab_authority_not_ready")
    if fallback_count != 0:
        issues.append("fallback_count_nonzero")
    if surrogate_count != 0:
        issues.append("surrogate_count_nonzero")
    if qge_primary_owner != "qge_3d":
        issues.append("qge_primary_owner_not_qge_3d")
    if idwt_backend != "native":
        issues.append("idwt_backend_not_native")
    if native_bridge_count <= 0:
        issues.append("native_bridge_missing")
    if cpu_idwt_count != 0:
        issues.append("cpu_idwt_nonzero")

    return {
        "kind": "vanilla_capture_matrix",
        "source_path": str(path),
        "matrix_file": str(matrix_path),
        "capture_dir": matrix.get("capture_dir"),
        "map": map_name_for_matrix(matrix, matrix_path),
        "ready": not issues,
        "issues": issues,
        "ready_for_complete_claim": as_bool(
            summary.get("ready_for_complete_claim")),
        "moonlab_authority_ready": as_bool(
            summary.get("moonlab_authority_ready")),
        "fallback_count": fallback_count,
        "surrogate_count": surrogate_count,
        "qge_primary_owner": qge_primary_owner,
        "idwt_backend": idwt_backend,
        "native_bridge_count": native_bridge_count,
        "cpu_idwt_count": cpu_idwt_count,
    }


def publication_pack_summary(path: Path) -> dict[str, Any]:
    manifest_path = resolve_publication_manifest_path(path)
    manifest = load_json(manifest_path)
    runtime = manifest.get("runtime_summary", {})
    if not isinstance(runtime, dict):
        raise ValueError(f"{manifest_path} is missing runtime_summary")
    icc_path = manifest_path.parent / "qge_publication_icc_evidence.json"
    completion_reason = None
    if icc_path.is_file():
        completion_reason = load_json(icc_path).get("completion_reason")

    issues = []
    if not as_bool(runtime.get("publication_ready_for_complete_claim")):
        issues.append("publication_not_ready")
    if completion_reason != "qge_publication_artifact_pack_complete":
        issues.append("publication_completion_missing")
    if as_int(runtime.get("fallback_count")) != 0:
        issues.append("publication_fallback_count_nonzero")
    if as_int(runtime.get("surrogate_count")) != 0:
        issues.append("publication_surrogate_count_nonzero")

    return {
        "kind": "publication_pack",
        "source_path": str(path),
        "publication_manifest_file": str(manifest_path),
        "publication_icc_evidence_file": str(icc_path) if icc_path.is_file() else None,
        "ready": not issues,
        "issues": issues,
        "publication_ready_for_complete_claim": as_bool(
            runtime.get("publication_ready_for_complete_claim")),
        "completion_reason": completion_reason,
        "fallback_count": as_int(runtime.get("fallback_count")),
        "surrogate_count": as_int(runtime.get("surrogate_count")),
        "performance_source": runtime.get("performance_source"),
        "vanilla_ready_for_complete_claim": as_bool(
            runtime.get("vanilla_ready_for_complete_claim")),
    }


def unique_sorted(values: list[Any]) -> list[Any]:
    return sorted({value for value in values if value is not None})


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    matrix_paths = list(args.matrix or [])
    publication_paths = list(args.publication_pack or [])
    for path in args.inputs:
        kind = detect_input_kind(path)
        if kind == "matrix":
            matrix_paths.append(path)
        elif kind == "publication":
            publication_paths.append(path)

    matrix_runs = [matrix_run_summary(path) for path in matrix_paths]
    publication_packs = [
        publication_pack_summary(path) for path in publication_paths
    ]
    all_runs = matrix_runs + publication_packs
    if not all_runs:
        raise ValueError("at least one matrix or publication pack is required")

    matrix_ready = all(run["ready"] for run in matrix_runs)
    publication_ready = all(pack["ready"] for pack in publication_packs)
    min_runs_met = len(matrix_runs) >= args.min_runs
    total_fallback_count = sum(as_int(run.get("fallback_count")) for run in all_runs)
    total_surrogate_count = sum(as_int(run.get("surrogate_count")) for run in all_runs)
    total_cpu_idwt_count = sum(as_int(run.get("cpu_idwt_count")) for run in matrix_runs)
    total_native_bridge_count = sum(
        as_int(run.get("native_bridge_count")) for run in matrix_runs)
    issues = []
    if not min_runs_met:
        issues.append("minimum_matrix_runs_not_met")
    for index, run in enumerate(matrix_runs):
        for issue in run["issues"]:
            issues.append(f"matrix_{index}:{issue}")
    for index, pack in enumerate(publication_packs):
        for issue in pack["issues"]:
            issues.append(f"publication_{index}:{issue}")

    complete = (
        min_runs_met and
        matrix_ready and
        publication_ready and
        total_fallback_count == 0 and
        total_surrogate_count == 0 and
        total_cpu_idwt_count == 0 and
        total_native_bridge_count > 0
    )

    return {
        "schema": "qge.breadth_evidence.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "success" if complete else "incomplete",
        "min_matrix_runs": args.min_runs,
        "matrix_runs": matrix_runs,
        "publication_packs": publication_packs,
        "aggregate": {
            "breadth_ready_for_complete_claim": complete,
            "matrix_run_count": len(matrix_runs),
            "publication_pack_count": len(publication_packs),
            "ready_matrix_run_count": sum(1 for run in matrix_runs if run["ready"]),
            "ready_publication_pack_count": sum(
                1 for pack in publication_packs if pack["ready"]),
            "map_count": len(unique_sorted([run.get("map") for run in matrix_runs])),
            "maps": unique_sorted([run.get("map") for run in matrix_runs]),
            "qge_primary_owners": unique_sorted([
                run.get("qge_primary_owner") for run in matrix_runs]),
            "idwt_backends": unique_sorted([
                run.get("idwt_backend") for run in matrix_runs]),
            "total_fallback_count": total_fallback_count,
            "total_surrogate_count": total_surrogate_count,
            "total_cpu_idwt_count": total_cpu_idwt_count,
            "total_native_bridge_count": total_native_bridge_count,
            "issue_count": len(issues),
            "issues": issues,
        },
        "claim_posture": {
            "allowed_wording": (
                "This artifact aggregates multiple QGE/Moonlab capture or "
                "publication artifacts and reports whether every supplied run "
                "meets the strict authority counters."
            ),
            "disallowed_wording": (
                "This artifact alone proves unrestricted map coverage, hardware "
                "speedup, or deployment on physical quantum hardware."
            ),
        },
    }


def build_icc_evidence(manifest: dict[str, Any],
                       manifest_path: Path,
                       icc_path: Path) -> dict[str, Any]:
    aggregate = manifest["aggregate"]
    ready = bool(aggregate.get("breadth_ready_for_complete_claim"))
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_breadth_evidence",
        "completion_reason": (
            "qge_breadth_evidence_pack_complete"
            if ready else "qge_breadth_evidence_pack_evidence_only"
        ),
        "breadth_evidence_file": str(manifest_path),
        "breadth_icc_evidence_file": str(icc_path),
        "breadth_ready_for_complete_claim": ready,
        "matrix_run_count": aggregate.get("matrix_run_count"),
        "publication_pack_count": aggregate.get("publication_pack_count"),
        "ready_matrix_run_count": aggregate.get("ready_matrix_run_count"),
        "ready_publication_pack_count": aggregate.get(
            "ready_publication_pack_count"),
        "map_count": aggregate.get("map_count"),
        "maps": aggregate.get("maps"),
        "total_fallback_count": aggregate.get("total_fallback_count"),
        "total_surrogate_count": aggregate.get("total_surrogate_count"),
        "total_cpu_idwt_count": aggregate.get("total_cpu_idwt_count"),
        "total_native_bridge_count": aggregate.get("total_native_bridge_count"),
        "issue_count": aggregate.get("issue_count"),
        "status": "success" if ready else "incomplete",
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path,
                        help="Matrix files/directories or publication pack directories")
    parser.add_argument("--matrix", action="append", type=Path,
                        help="vanilla_capture_matrix.json or graphics capture directory")
    parser.add_argument("--publication-pack", action="append", type=Path,
                        help="publication_manifest.json or publication pack directory")
    parser.add_argument("--min-runs", type=int, default=1,
                        help="Minimum ready vanilla matrix runs required")
    parser.add_argument("--out", type=Path,
                        default=REPO_ROOT / "diagnostics" /
                        "breadth_evidence" / stamp / "breadth_evidence.json")
    parser.add_argument("--icc-out", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.min_runs <= 0:
        print("qge_breadth_evidence: --min-runs must be > 0", file=sys.stderr)
        return 1
    icc_path = args.icc_out or args.out.parent / "qge_breadth_icc_evidence.json"
    try:
        manifest = build_manifest(args)
        write_json(args.out, manifest)
        write_json(icc_path, build_icc_evidence(manifest, args.out, icc_path))
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print(f"qge_breadth_evidence: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_BREADTH_EVIDENCE {args.out}")
    print(f"QGE_BREADTH_ICC_EVIDENCE {icc_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
