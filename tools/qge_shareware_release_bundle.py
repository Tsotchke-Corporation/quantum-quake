#!/usr/bin/env python3
"""Create a persistent shareware release bundle from a ready QGE pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_map_sets  # noqa: E402
import qge_moonlab_full_game_plan  # noqa: E402
import qge_shareware_release_candidate_gate  # noqa: E402


READY_STATUS = "ready_for_shareware_release_bundle"
BLOCKED = "blocked"
PASS = "pass"
SHAREWARE_MAP_SET = qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
SELF_BUNDLE_PREFIX = "release/qge_shareware_release_bundle"


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def bool_true(value: Any) -> bool:
    return value is True or value == 1


def int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def load_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_archive_mode(path: Path) -> int:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o111:
        return 0o755
    return 0o644


def resolve_pack_dir(pack_or_manifest: Path) -> Path:
    manifest_path = qge_moonlab_full_game_plan.resolve_publication_manifest(
        pack_or_manifest)
    if not manifest_path.is_file():
        raise ValueError(f"publication manifest not found: {manifest_path}")
    return manifest_path.parent


def release_artifact_paths(pack_dir: Path) -> dict[str, Path]:
    return {
        "publication_manifest": pack_dir / "publication_manifest.json",
        "publication_icc_evidence": pack_dir / "qge_publication_icc_evidence.json",
        "postpack_audit": pack_dir / "qge_postpack_audit.json",
        "release_candidate_gate": (
            pack_dir / "release" /
            "qge_shareware_release_candidate_gate.json"),
        "release_candidate_markdown": (
            pack_dir / "release" /
            "qge_shareware_release_candidate_gate.md"),
        "release_candidate_icc_evidence": (
            pack_dir / "release" /
            "qge_shareware_release_candidate_gate_icc_evidence.json"),
        "shareware_deployment_gate": (
            pack_dir / "resource" /
            "qge_moonlab_shareware_deployment_gate.json"),
        "noesis_release_gate": (
            pack_dir / "agent_stream_release" / "noesis" /
            "qge_noesis_release_gate.json"),
        "registered_full_game_deployment_gate": (
            pack_dir / "resource" / "qge_moonlab_deployment_gate.json"),
    }


def file_manifest(pack_dir: Path) -> list[dict[str, Any]]:
    files = [
        path for path in pack_dir.rglob("*")
        if path.is_file() and
        not path.relative_to(pack_dir).as_posix().startswith(
            SELF_BUNDLE_PREFIX)
    ]
    entries = []
    for path in sorted(files, key=lambda item: item.relative_to(pack_dir).as_posix()):
        archive_mode = normalized_archive_mode(path)
        rel = path.relative_to(pack_dir).as_posix()
        entries.append({
            "path": rel,
            "size_bytes": path.stat().st_size,
            "archive_mode": f"{archive_mode:04o}",
            "sha256": sha256_file(path),
        })
    return entries


def archive_zip(
    pack_dir: Path,
    archive_path: Path,
    entries: list[dict[str, Any]],
    *,
    root_name: str,
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for item in entries:
            rel = str(item["path"])
            archive_mode = int(str(item.get("archive_mode", "0644")), 8)
            info = zipfile.ZipInfo(
                filename=f"{root_name}/{rel}",
                date_time=ZIP_TIMESTAMP,
            )
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | archive_mode) << 16
            archive.writestr(info, (pack_dir / rel).read_bytes())


def criterion(
    criterion_id: str,
    label: str,
    passed: bool,
    blocker: str,
    **fields: Any,
) -> dict[str, Any]:
    item = {
        "id": criterion_id,
        "label": label,
        "status": PASS if passed else BLOCKED,
        "blocker": None if passed else blocker,
    }
    item.update(fields)
    return item


def failed_criteria(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in criteria
        if dict_or_empty(item).get("status") != PASS
    ]


def build_criteria(
    *,
    artifacts: dict[str, Path],
    release_candidate_gate: dict[str, Any],
    release_candidate_icc: dict[str, Any],
    publication_manifest: dict[str, Any],
    publication_icc: dict[str, Any],
    postpack_audit: dict[str, Any],
    archive_path: Path,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    artifact_statuses = {
        name: path.is_file()
        for name, path in artifacts.items()
    }
    artifacts_ready = all(artifact_statuses.values())
    rc_ready = (
        release_candidate_gate.get("schema") ==
        "qge.shareware_release_candidate_gate.v0" and
        release_candidate_gate.get("status") ==
        qge_shareware_release_candidate_gate.READY_STATUS and
        release_candidate_gate.get(
            "shareware_release_candidate_claim_allowed") is True and
        int_value(release_candidate_gate.get("blocker_count")) == 0 and
        release_candidate_gate.get(
            "whole_game_moonlab_deployment_claim_allowed") is False and
        release_candidate_gate.get(
            "hardware_quantum_advantage_claim_allowed") is False and
        release_candidate_gate.get("learned_play_claim_allowed") is False
    )
    rc_icc_ready = (
        release_candidate_icc.get("schema") == "qge.icc_evidence.v0" and
        release_candidate_icc.get("runtime_backend") ==
        "qge_shareware_release_candidate_gate" and
        release_candidate_icc.get("completion_reason") ==
        "qge_shareware_release_candidate_gate_ready" and
        release_candidate_icc.get("runtime_backend_scope_map_set") ==
        SHAREWARE_MAP_SET
    )
    publication_ready = (
        publication_manifest.get("schema") == "qge.publication_pack.v0" and
        publication_manifest.get("status") == "success" and
        bool_true(dict_or_empty(publication_manifest.get(
            "runtime_summary")).get("publication_ready_for_complete_claim")) and
        publication_icc.get("runtime_backend") == "qge_publication_pack" and
        publication_icc.get("completion_reason") ==
        "qge_publication_artifact_pack_complete"
    )
    postpack_ready = (
        postpack_audit.get("schema") == "qge.postpack_audit.v0" and
        postpack_audit.get("passed") is True and
        int_value(postpack_audit.get("failed_count")) == 0 and
        int_value(postpack_audit.get("mismatch_count_total")) == 0
    )
    archive_ready = (
        archive_path.is_file() and
        archive_path.stat().st_size > 0 and
        len(entries) > 0 and
        any(item.get("path") == "publication_manifest.json" for item in entries)
        and any(
            item.get("path") ==
            "release/qge_shareware_release_candidate_gate.json"
            for item in entries)
    )
    return [
        criterion(
            "release_bundle_required_artifacts_present",
            "Publication, postpack, and release-candidate artifacts exist",
            artifacts_ready,
            "one or more required bundle inputs are missing",
            artifacts=artifact_statuses,
        ),
        criterion(
            "release_candidate_gate_ready",
            "Shareware release-candidate gate is ready and scoped",
            rc_ready and rc_icc_ready,
            "release-candidate gate or ICC sidecar is blocked or stale",
            gate_status=release_candidate_gate.get("status"),
            gate_blocker_count=release_candidate_gate.get("blocker_count"),
            icc_completion_reason=release_candidate_icc.get(
                "completion_reason"),
            map_set=release_candidate_icc.get("runtime_backend_scope_map_set"),
        ),
        criterion(
            "publication_and_postpack_ready",
            "Publication pack and postpack audit are complete",
            publication_ready and postpack_ready,
            "publication pack or postpack audit is incomplete",
            publication_status=publication_manifest.get("status"),
            publication_icc_completion_reason=publication_icc.get(
                "completion_reason"),
            postpack_passed=postpack_audit.get("passed"),
            postpack_failed_count=postpack_audit.get("failed_count"),
        ),
        criterion(
            "release_archive_written",
            "Release ZIP archive was written with required pack files",
            archive_ready,
            "release archive is missing required files",
            archive_file=str(archive_path),
            archive_size_bytes=(
                archive_path.stat().st_size if archive_path.is_file() else 0),
            file_count=len(entries),
        ),
    ]


def next_actions_for_blockers(blockers: list[dict[str, Any]]) -> list[str]:
    if not blockers:
        return [
            "Publish the ZIP archive together with the bundle manifest, Markdown, and ICC sidecar.",
            "Keep the registered full-game release separate until registered BSP assets and full-game capture evidence are complete.",
        ]
    actions = []
    for blocker in blockers:
        blocker_id = blocker.get("id")
        if blocker_id == "release_bundle_required_artifacts_present":
            actions.append(
                "Regenerate the v8 publication pack, postpack audit, and release-candidate gate before bundling.")
        elif blocker_id == "release_candidate_gate_ready":
            actions.append(
                "Rerun tools/qge_shareware_release_candidate_gate.py until the RC gate is ready.")
        elif blocker_id == "publication_and_postpack_ready":
            actions.append(
                "Rerun tools/qge_postpack_audit.py with --fail-on-mismatch and fix stale child audits.")
        elif blocker_id == "release_archive_written":
            actions.append(
                "Recreate the release archive outside the publication pack directory.")
    return actions


def default_outdir(pack_dir: Path) -> Path:
    return Path("diagnostics") / "release_bundles" / pack_dir.name


def default_name(pack_dir: Path) -> str:
    return f"quantum-quake-shareware-{pack_dir.name}"


def build_bundle(
    pack_or_manifest: Path,
    *,
    outdir: Path | None = None,
    name: str | None = None,
    archive_path: Path | None = None,
) -> dict[str, Any]:
    pack_dir = resolve_pack_dir(pack_or_manifest)
    bundle_name = name or default_name(pack_dir)
    resolved_outdir = outdir or default_outdir(pack_dir)
    resolved_archive = archive_path or (
        resolved_outdir / f"{bundle_name}.zip")
    if pack_dir.resolve() in [resolved_outdir.resolve()] + list(
        resolved_outdir.resolve().parents):
        raise ValueError("release bundle output directory must be outside pack_dir")

    artifacts = release_artifact_paths(pack_dir)
    publication_manifest = load_json_object(artifacts["publication_manifest"])
    publication_icc = load_json_object(artifacts["publication_icc_evidence"])
    postpack_audit = load_json_object(artifacts["postpack_audit"])
    rc_gate = load_json_object(artifacts["release_candidate_gate"])
    rc_icc = load_json_object(artifacts["release_candidate_icc_evidence"])
    entries = file_manifest(pack_dir)
    archive_zip(pack_dir, resolved_archive, entries, root_name=pack_dir.name)
    archive_info = {
        "path": str(resolved_archive),
        "name": resolved_archive.name,
        "size_bytes": resolved_archive.stat().st_size,
        "sha256": sha256_file(resolved_archive),
    }
    criteria = build_criteria(
        artifacts=artifacts,
        release_candidate_gate=rc_gate,
        release_candidate_icc=rc_icc,
        publication_manifest=publication_manifest,
        publication_icc=publication_icc,
        postpack_audit=postpack_audit,
        archive_path=resolved_archive,
        entries=entries,
    )
    blockers = failed_criteria(criteria)
    bundle_ready = not blockers
    rc_summary = dict_or_empty(rc_gate.get("summary"))
    return {
        "schema": "qge.shareware_release_bundle.v0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "name": bundle_name,
        "pack_dir": str(pack_dir),
        "status": READY_STATUS if bundle_ready else BLOCKED,
        "shareware_release_bundle_ready": bundle_ready,
        "shareware_release_candidate_claim_allowed": bundle_ready,
        "whole_game_moonlab_deployment_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "hardware_quantum_advantage_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "learned_play_claim_allowed": False,
        "archive": archive_info,
        "file_count": len(entries),
        "total_uncompressed_bytes": sum(
            int_value(item.get("size_bytes")) for item in entries),
        "file_manifest": entries,
        "criteria": criteria,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "summary": {
            "map_set": SHAREWARE_MAP_SET,
            "publication_status": publication_manifest.get("status"),
            "postpack_passed": postpack_audit.get("passed"),
            "shareware_release_candidate_status": rc_gate.get("status"),
            "shareware_gate_status": rc_summary.get("shareware_gate_status"),
            "noesis_gate_status": rc_summary.get("noesis_gate_status"),
            "registered_full_game_gate_status": rc_summary.get(
                "registered_full_game_gate_status"),
            "shareware_covered_map_count": rc_summary.get(
                "shareware_covered_map_count"),
            "shareware_target_map_count": rc_summary.get(
                "shareware_target_map_count"),
            "shareware_native_bridge_count": rc_summary.get(
                "shareware_native_bridge_count"),
            "noesis_quality_score": rc_summary.get("noesis_quality_score"),
            "noesis_quality_grade": rc_summary.get("noesis_quality_grade"),
        },
        "next_actions": next_actions_for_blockers(blockers),
        "limits": [
            "This bundle is a shareware Episode 1 release-candidate evidence bundle.",
            "It does not include or authorize registered full-game assets.",
            "It does not claim hardware execution, hardware quantum advantage, or dense state-vector execution.",
        ],
    }


def archive_checksum_record(bundle: dict[str, Any]) -> dict[str, Any]:
    archive = dict_or_empty(bundle.get("archive"))
    return {
        "schema": "qge.shareware_release_bundle_archive_checksum.v0",
        "kind": "artifact",
        "name": "shareware_release_bundle_archive_checksum_file",
        "value": archive.get("path"),
        "archive_file": archive.get("path"),
        "archive_name": archive.get("name"),
        "archive_sha256": archive.get("sha256"),
        "archive_size_bytes": archive.get("size_bytes"),
        "release_scope": SHAREWARE_MAP_SET,
        "snippet": (
            f"{archive.get('name')} sha256={archive.get('sha256')}"
        ),
    }


def build_icc_evidence(
    bundle: dict[str, Any],
    *,
    manifest_path: Path | None = None,
    archive_checksum_path: Path | None = None,
) -> dict[str, Any]:
    summary = dict_or_empty(bundle.get("summary"))
    ready = bundle.get("shareware_release_bundle_ready") is True
    return {
        "schema": "qge.icc_evidence.v0",
        "runtime_backend": "qge_shareware_release_bundle",
        "completion_reason": (
            "qge_shareware_release_bundle_ready"
            if ready else "qge_shareware_release_bundle_blocked"),
        "status": "success",
        "shareware_release_bundle_manifest_file": (
            str(manifest_path) if manifest_path else None),
        "shareware_release_bundle_archive_file": (
            dict_or_empty(bundle.get("archive")).get("path")),
        "shareware_release_bundle_archive_sha256": (
            dict_or_empty(bundle.get("archive")).get("sha256")),
        "shareware_release_bundle_archive_checksum_file": (
            str(archive_checksum_path) if archive_checksum_path else None),
        "shareware_release_bundle_ready": ready,
        "release_scope": SHAREWARE_MAP_SET,
        "runtime_backend_scope_map_set": SHAREWARE_MAP_SET,
        "map_set": SHAREWARE_MAP_SET,
        "file_count": bundle.get("file_count"),
        "total_uncompressed_bytes": bundle.get("total_uncompressed_bytes"),
        "archive_size_bytes": dict_or_empty(bundle.get("archive")).get(
            "size_bytes"),
        "postpack_audit_passed": summary.get("postpack_passed"),
        "shareware_release_candidate_status": summary.get(
            "shareware_release_candidate_status"),
        "shareware_gate_status": summary.get("shareware_gate_status"),
        "noesis_gate_status": summary.get("noesis_gate_status"),
        "registered_full_game_deployment_gate_status": summary.get(
            "registered_full_game_gate_status"),
        "shareware_covered_map_count": summary.get(
            "shareware_covered_map_count"),
        "shareware_target_map_count": summary.get(
            "shareware_target_map_count"),
        "whole_game_moonlab_deployment_claim_allowed": False,
        "whole_game_hardware_execution_claim_allowed": False,
        "hardware_quantum_advantage_claim_allowed": False,
        "dense_70000_qubit_state_claim_allowed": False,
        "noesis_learned_play_claim_allowed": False,
    }


def markdown_report(bundle: dict[str, Any]) -> str:
    summary = dict_or_empty(bundle.get("summary"))
    archive = dict_or_empty(bundle.get("archive"))
    lines = [
        "# QGE Shareware Release Bundle",
        "",
        f"Status: {bundle.get('status')}",
        f"Name: {bundle.get('name')}",
        "",
        "| Artifact | Value |",
        "| --- | ---: |",
        f"| archive | {archive.get('path')} |",
        f"| archive sha256 | {archive.get('sha256')} |",
        f"| archive bytes | {archive.get('size_bytes')} |",
        f"| file count | {bundle.get('file_count')} |",
        f"| uncompressed bytes | {bundle.get('total_uncompressed_bytes')} |",
        "",
        "| Release Evidence | Value |",
        "| --- | ---: |",
        f"| map set | {summary.get('map_set')} |",
        f"| postpack passed | {summary.get('postpack_passed')} |",
        (
            "| shareware maps | "
            f"{summary.get('shareware_covered_map_count')} / "
            f"{summary.get('shareware_target_map_count')} |"
        ),
        f"| native bridges | {summary.get('shareware_native_bridge_count')} |",
        f"| Noesis score | {summary.get('noesis_quality_score')} |",
        f"| Noesis grade | {summary.get('noesis_quality_grade')} |",
        (
            "| registered full-game gate | "
            f"{summary.get('registered_full_game_gate_status')} |"
        ),
        "",
        "| Criterion | Status | Blocker |",
        "| --- | --- | --- |",
    ]
    for item in list_or_empty(bundle.get("criteria")):
        item_data = dict_or_empty(item)
        lines.append(
            f"| {item_data.get('id')} | {item_data.get('status')} | "
            f"{item_data.get('blocker') or ''} |"
        )
    lines.extend(["", "## Next Actions", ""])
    for action in list_or_empty(bundle.get("next_actions")):
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pack_dir",
        type=Path,
        help="Publication pack directory or publication_manifest.json path.",
    )
    parser.add_argument("--outdir", type=Path, default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--archive", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--icc-json", type=Path, default=None)
    parser.add_argument("--archive-checksum", type=Path, default=None)
    parser.add_argument(
        "--fail-on-blocked",
        action="store_true",
        help="Exit nonzero when the bundle is not ready.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        pack_dir = resolve_pack_dir(args.pack_dir)
        outdir = args.outdir or default_outdir(pack_dir)
        bundle = build_bundle(
            args.pack_dir,
            outdir=outdir,
            name=args.name,
            archive_path=args.archive,
        )
        manifest_path = args.manifest or (
            outdir / "qge_shareware_release_bundle.json")
        markdown_path = args.markdown or (
            outdir / "qge_shareware_release_bundle.md")
        icc_path = args.icc_json or (
            outdir / "qge_shareware_release_bundle_icc_evidence.json")
        archive_checksum_path = args.archive_checksum or (
            outdir / "qge_shareware_release_bundle_archive_checksum.json")
        bundle.setdefault("sidecars", {})[
            "archive_checksum_file"] = str(archive_checksum_path)
        write_json(manifest_path, bundle)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown_report(bundle), encoding="utf-8")
        write_json(archive_checksum_path, archive_checksum_record(bundle))
        write_json(
            icc_path,
            build_icc_evidence(
                bundle,
                manifest_path=manifest_path,
                archive_checksum_path=archive_checksum_path,
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"qge_shareware_release_bundle: {exc}", file=sys.stderr)
        return 1
    print(f"QGE_SHAREWARE_RELEASE_BUNDLE {manifest_path}")
    print(f"QGE_SHAREWARE_RELEASE_BUNDLE_MARKDOWN {markdown_path}")
    print(f"QGE_SHAREWARE_RELEASE_BUNDLE_ICC {icc_path}")
    print(f"QGE_SHAREWARE_RELEASE_BUNDLE_ARCHIVE_CHECKSUM {archive_checksum_path}")
    print(f"QGE_SHAREWARE_RELEASE_BUNDLE_ARCHIVE {bundle['archive']['path']}")
    if args.fail_on_blocked and bundle.get("status") != READY_STATUS:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
