#!/usr/bin/env python3
"""Audit packed Moonlab hardware handoff artifacts against the manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_moonlab_full_game_plan  # noqa: E402
import qge_moonlab_hardware_ingest  # noqa: E402
import qge_moonlab_overclaim_audit  # noqa: E402
import qge_moonlab_submission_bundle  # noqa: E402
import qge_resource_boundary_audit  # noqa: E402


SOURCE_ARTIFACTS = ("moonlab_submission_packet",)
HANDOFF_OUTPUTS = (
    "moonlab_submission_bundle",
    "moonlab_submission_bundle_icc_evidence",
    "moonlab_hardware_record_template",
    "moonlab_hardware_submission_scope",
    "moonlab_hardware_submission_scope_icc_evidence",
)
HANDOFF_FORBIDDEN_CLAIMS = (
    "hardware_result_claimed",
    "hardware_quantum_advantage_claimed",
    "whole_game_hardware_execution_claimed",
    "dense_70000_qubit_state_claimed",
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


def artifact_entry(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> dict[str, Any]:
    return dict_or_empty(
        dict_or_empty(dict_or_empty(manifest.get("artifacts")).get(section))
        .get(name)
    )


def artifact_path_string(
    manifest: dict[str, Any],
    section: str,
    name: str,
) -> str | None:
    entry = artifact_entry(manifest, section, name)
    raw_path = entry.get("path")
    if not raw_path:
        raw_path = dict_or_empty(entry.get("packed")).get("path")
    return raw_path if isinstance(raw_path, str) and raw_path else None


def artifact_path(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    base_dir: Path | None = None,
) -> Path | None:
    return qge_moonlab_full_game_plan.resolve_path(
        artifact_path_string(manifest, section, name),
        base_dir=base_dir,
    )


def load_artifact_json(
    manifest: dict[str, Any],
    section: str,
    name: str,
    *,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    path = artifact_path(manifest, section, name, base_dir=base_dir)
    if path is None or not path.is_file():
        return {}
    return load_json(path)


def raw_path_or_none(value: str | None) -> Path | None:
    return Path(value) if isinstance(value, str) and value else None


def expected_handoff_artifacts(
    manifest: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    packet = load_artifact_json(
        manifest,
        "resource",
        "moonlab_submission_packet",
        base_dir=base_dir,
    )
    packet_path = raw_path_or_none(artifact_path_string(
        manifest, "resource", "moonlab_submission_packet"))
    bundle_path = raw_path_or_none(artifact_path_string(
        manifest, "resource", "moonlab_submission_bundle"))
    template_path = raw_path_or_none(artifact_path_string(
        manifest, "resource", "moonlab_hardware_record_template"))
    scope_path = raw_path_or_none(artifact_path_string(
        manifest, "resource", "moonlab_hardware_submission_scope"))

    bundle = qge_moonlab_submission_bundle.build_submission_bundle(
        packet,
        packet_path=packet_path,
    )
    bundle_icc = qge_moonlab_submission_bundle.build_icc_evidence(
        bundle,
        out_path=bundle_path,
    )
    hardware_template = (
        qge_moonlab_hardware_ingest.build_hardware_record_template(packet)
    )
    hardware_scope = (
        qge_moonlab_submission_bundle.build_hardware_submission_scope(
            packet,
            bundle,
            hardware_template,
            packet_path=packet_path,
            bundle_path=bundle_path,
            hardware_template_path=template_path,
        )
    )
    hardware_scope_icc = (
        qge_moonlab_submission_bundle.build_scope_icc_evidence(
            hardware_scope,
            out_path=scope_path,
        )
    )
    return {
        "moonlab_submission_bundle": bundle,
        "moonlab_submission_bundle_icc_evidence": bundle_icc,
        "moonlab_hardware_record_template": hardware_template,
        "moonlab_hardware_submission_scope": hardware_scope,
        "moonlab_hardware_submission_scope_icc_evidence": hardware_scope_icc,
    }


def empty_audit(required: bool) -> dict[str, Any]:
    return {
        "required": required,
        "recorded": False,
        "expected_artifact_count": len(HANDOFF_OUTPUTS),
        "recorded_artifact_count": 0,
        "missing_artifacts": [],
        "build_errors": [],
        "artifact_mismatches": [],
        "overclaim_flags": [],
        "mismatch_count": 0,
        "passed": not required,
    }


def moonlab_handoff_audit(
    manifest: dict[str, Any] | None,
    *,
    manifest_path: Path,
    required: bool = True,
) -> dict[str, Any]:
    manifest_data = dict_or_empty(manifest)
    base_dir = manifest_path.parent
    active = required or bool(manifest_data)
    if not active:
        return empty_audit(required)

    artifact_names = SOURCE_ARTIFACTS + HANDOFF_OUTPUTS
    paths = {
        name: artifact_path(manifest_data, "resource", name, base_dir=base_dir)
        for name in artifact_names
    }
    missing_artifacts = [
        {
            "artifact": f"resource.{name}",
            "path": str(path) if path is not None else None,
        }
        for name, path in paths.items()
        if path is None or not path.is_file()
    ]
    recorded = {
        name: load_json(path)
        for name, path in paths.items()
        if name in HANDOFF_OUTPUTS and path is not None and path.is_file()
    }

    build_errors: list[dict[str, str]] = []
    try:
        expected = expected_handoff_artifacts(
            manifest_data,
            base_dir=base_dir,
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        build_errors.append({
            "artifact": "resource.moonlab_submission_bundle",
            "error": str(exc),
        })
        expected = {}

    artifact_mismatches = []
    for name in HANDOFF_OUTPUTS:
        recorded_artifact = dict_or_empty(recorded.get(name))
        if not recorded_artifact:
            continue
        fields = qge_resource_boundary_audit.mismatch_paths(
            dict_or_empty(expected.get(name)),
            recorded_artifact,
        )
        if fields:
            artifact_mismatches.append({
                "artifact": f"resource.{name}",
                "fields": fields,
            })

    overclaim_flags = []
    for name, artifact in recorded.items():
        overclaim_flags.extend(
            qge_moonlab_overclaim_audit.recursive_overclaim_flags(
                name,
                artifact,
                forbidden=HANDOFF_FORBIDDEN_CLAIMS,
            )
        )

    mismatch_count = (
        len(missing_artifacts) +
        len(build_errors) +
        sum(len(item["fields"]) for item in artifact_mismatches) +
        len(overclaim_flags)
    )
    recorded_count = sum(
        1 for name in HANDOFF_OUTPUTS
        if dict_or_empty(recorded.get(name))
    )
    recorded_all = recorded_count == len(HANDOFF_OUTPUTS)
    return {
        "required": required,
        "recorded": recorded_all,
        "expected_artifact_count": len(HANDOFF_OUTPUTS),
        "recorded_artifact_count": recorded_count,
        "missing_artifacts": missing_artifacts,
        "build_errors": build_errors,
        "artifact_mismatches": artifact_mismatches,
        "overclaim_flags": overclaim_flags,
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0 and (recorded_all or not required),
    }


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
        help="Exit nonzero when Moonlab handoff artifacts are stale.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        manifest_path = qge_moonlab_full_game_plan.resolve_publication_manifest(
            args.pack_or_manifest)
        audit = moonlab_handoff_audit(
            load_json(manifest_path),
            manifest_path=manifest_path,
            required=True,
        )
        if args.out is not None:
            write_json(args.out, audit)
            print(f"QGE_MOONLAB_HANDOFF_AUDIT {args.out}")
        else:
            print(json.dumps(audit, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"qge_moonlab_handoff_audit: {exc}", file=sys.stderr)
        return 1
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
