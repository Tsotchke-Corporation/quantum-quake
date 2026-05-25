#!/usr/bin/env python3
"""Audit publication manifest Markdown artifacts against source JSON."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_asset_requirements  # noqa: E402
import qge_moonlab_deployment_gate  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402
import qge_moonlab_oracle_transpile  # noqa: E402
import qge_moonlab_qae_grover_plan  # noqa: E402
import qge_moonlab_qae_observation_transpile  # noqa: E402
import qge_moonlab_qae_transpile  # noqa: E402
import qge_moonlab_submission_bundle  # noqa: E402
import qge_registered_asset_intake  # noqa: E402


@dataclass(frozen=True)
class MarkdownArtifactSpec:
    section: str
    source_artifact: str
    markdown_artifact: str
    label: str
    renderer: Callable[[dict[str, Any]], str]


MARKDOWN_ARTIFACTS = (
    MarkdownArtifactSpec(
        "advantage",
        "qae_moonlab_payload",
        "qae_moonlab_payload_markdown",
        "advantage.qae_moonlab_payload_markdown",
        qge_moonlab_qae_transpile.markdown_report,
    ),
    MarkdownArtifactSpec(
        "advantage",
        "qae_moonlab_oracle_kernel",
        "qae_moonlab_oracle_kernel_markdown",
        "advantage.qae_moonlab_oracle_kernel_markdown",
        qge_moonlab_oracle_transpile.markdown_report,
    ),
    MarkdownArtifactSpec(
        "advantage",
        "qae_moonlab_observation_zero",
        "qae_moonlab_observation_zero_markdown",
        "advantage.qae_moonlab_observation_zero_markdown",
        qge_moonlab_qae_observation_transpile.markdown_report,
    ),
    MarkdownArtifactSpec(
        "advantage",
        "qae_moonlab_grover_schedule_plan",
        "qae_moonlab_grover_schedule_plan_markdown",
        "advantage.qae_moonlab_grover_schedule_plan_markdown",
        qge_moonlab_qae_grover_plan.markdown_report,
    ),
    MarkdownArtifactSpec(
        "resource",
        "asset_requirements",
        "asset_requirements_markdown",
        "resource.asset_requirements_markdown",
        qge_asset_requirements.markdown_report,
    ),
    MarkdownArtifactSpec(
        "resource",
        "registered_asset_intake",
        "registered_asset_intake_markdown",
        "resource.registered_asset_intake_markdown",
        qge_registered_asset_intake.markdown_report,
    ),
    MarkdownArtifactSpec(
        "resource",
        "moonlab_submission_bundle",
        "moonlab_submission_bundle_markdown",
        "resource.moonlab_submission_bundle_markdown",
        qge_moonlab_submission_bundle.markdown_report,
    ),
    MarkdownArtifactSpec(
        "resource",
        "moonlab_full_game_plan",
        "moonlab_full_game_plan_markdown",
        "resource.moonlab_full_game_plan_markdown",
        qge_moonlab_full_game_plan.markdown_report,
    ),
    MarkdownArtifactSpec(
        "resource",
        "moonlab_deployment_gate",
        "moonlab_deployment_gate_markdown",
        "resource.moonlab_deployment_gate_markdown",
        qge_moonlab_deployment_gate.markdown_report,
    ),
)


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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def first_line_mismatch(expected: str, actual: str) -> dict[str, Any] | None:
    expected_lines = expected.splitlines()
    actual_lines = actual.splitlines()
    max_len = max(len(expected_lines), len(actual_lines))
    for index in range(max_len):
        expected_line = (
            expected_lines[index] if index < len(expected_lines) else None)
        actual_line = actual_lines[index] if index < len(actual_lines) else None
        if expected_line != actual_line:
            return {
                "line": index + 1,
                "expected": expected_line,
                "actual": actual_line,
            }
    return None


def artifact_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> str | None:
    entry = dict_or_empty(
        dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(section))
        .get(name)
    )
    path = entry.get("path")
    return path if isinstance(path, str) and path else None


def resolve_path(raw_path: str | None, *, base_dir: Path | None = None) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        return None
    path = Path(raw_path)
    if path.exists() or path.is_absolute() or base_dir is None:
        return path
    candidate = base_dir / path
    return candidate if candidate.exists() else path


def empty_audit(required: bool, specs: Iterable[MarkdownArtifactSpec]) -> dict[str, Any]:
    expected_count = len(tuple(specs))
    return {
        "required": required,
        "recorded": False,
        "expected_markdown_count": expected_count,
        "recorded_markdown_count": 0,
        "missing_sources": [],
        "missing_markdown": [],
        "render_errors": [],
        "markdown_mismatches": [],
        "mismatch_count": 0,
        "passed": not required,
    }


def manifest_markdown_audit(
    manifest: dict[str, Any] | None,
    *,
    manifest_path: Path | None = None,
    required: bool = True,
    specs: Iterable[MarkdownArtifactSpec] = MARKDOWN_ARTIFACTS,
) -> dict[str, Any]:
    manifest_data = dict_or_empty(manifest)
    spec_list = tuple(specs)
    if not manifest_data and not required:
        return empty_audit(required, spec_list)

    base_dir = manifest_path.parent if manifest_path is not None else None
    missing_sources = []
    missing_markdown = []
    render_errors = []
    markdown_mismatches = []
    recorded_count = 0

    for spec in spec_list:
        source_path = resolve_path(
            artifact_path(manifest_data, spec.section, spec.source_artifact),
            base_dir=base_dir,
        )
        markdown_path = resolve_path(
            artifact_path(manifest_data, spec.section, spec.markdown_artifact),
            base_dir=base_dir,
        )
        if source_path is None or not source_path.is_file():
            missing_sources.append({
                "artifact": f"{spec.section}.{spec.source_artifact}",
                "path": str(source_path) if source_path is not None else None,
            })
            continue
        if markdown_path is None or not markdown_path.is_file():
            missing_markdown.append({
                "artifact": spec.label,
                "path": (
                    str(markdown_path) if markdown_path is not None else None),
            })
            continue

        recorded_count += 1
        source = load_json(source_path)
        actual = markdown_path.read_text(encoding="utf-8")
        try:
            expected = spec.renderer(source)
        except (KeyError, TypeError, ValueError) as exc:
            render_errors.append({
                "artifact": spec.label,
                "source_path": str(source_path),
                "error": str(exc),
            })
            continue
        if actual != expected:
            markdown_mismatches.append({
                "kind": "markdown_content_mismatch",
                "artifact": spec.label,
                "source_path": str(source_path),
                "markdown_path": str(markdown_path),
                "expected_sha256": sha256_text(expected),
                "actual_sha256": sha256_text(actual),
                "first_line_mismatch": first_line_mismatch(expected, actual),
            })

    mismatch_count = (
        len(missing_sources) +
        len(missing_markdown) +
        len(render_errors) +
        len(markdown_mismatches)
    )
    recorded = recorded_count == len(spec_list)
    return {
        "required": required,
        "recorded": recorded,
        "expected_markdown_count": len(spec_list),
        "recorded_markdown_count": recorded_count,
        "missing_sources": missing_sources,
        "missing_markdown": missing_markdown,
        "render_errors": render_errors,
        "markdown_mismatches": markdown_mismatches,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (recorded or not required),
    }


def resolve_manifest(pack_or_manifest: Path) -> Path:
    if pack_or_manifest.is_dir():
        return pack_or_manifest / "publication_manifest.json"
    return pack_or_manifest


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pack_or_manifest",
        type=Path,
        help="Publication pack directory or publication_manifest.json path.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional audit JSON output path.",
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit nonzero when packed Markdown artifacts are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest_path = resolve_manifest(args.pack_or_manifest)
    try:
        audit = manifest_markdown_audit(
            load_json(manifest_path),
            manifest_path=manifest_path,
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_MANIFEST_MARKDOWN_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_manifest_markdown_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
