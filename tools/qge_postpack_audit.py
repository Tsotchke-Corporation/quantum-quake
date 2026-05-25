#!/usr/bin/env python3
"""Run the full publication-pack postpack audit suite."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_manifest_reproduce_audit  # noqa: E402


POSTPACK_AUDIT_TOOLS = tuple(
    prefix.strip()
    for prefix in qge_manifest_reproduce_audit.POSTPACK_REPRODUCE_COMMAND_PREFIXES
    if prefix.strip() != "tools/qge_postpack_audit.py"
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


def audit_output_path(outdir: Path, tool: str) -> Path:
    return outdir / f"{Path(tool).stem}.json"


def audit_command(tool: str, pack_dir: Path, out_path: Path) -> list[str]:
    return [
        sys.executable,
        tool,
        str(pack_dir),
        "--out",
        str(out_path),
        "--fail-on-mismatch",
    ]


def prepare_audit_output(out_path: Path) -> dict[str, Any]:
    if not out_path.exists() and not out_path.is_symlink():
        return {
            "stale_output_removed": False,
            "stale_output_error": None,
        }
    if not out_path.is_file() and not out_path.is_symlink():
        return {
            "stale_output_removed": False,
            "stale_output_error": "audit_output_path_not_file",
        }
    try:
        out_path.unlink()
    except OSError as exc:
        return {
            "stale_output_removed": False,
            "stale_output_error": str(exc),
        }
    return {
        "stale_output_removed": True,
        "stale_output_error": None,
    }


def summarize_result(
    tool: str,
    command: list[str],
    out_path: Path,
    completed: subprocess.CompletedProcess[str],
    output_prep: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    load_error = None
    if out_path.is_file():
        try:
            payload = load_json(out_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            load_error = str(exc)
    else:
        load_error = "audit_output_missing"

    payload_passed = bool(dict_or_empty(payload).get("passed"))
    passed = (
        completed.returncode == 0 and
        load_error is None and
        output_prep.get("stale_output_error") is None and
        payload_passed
    )
    return {
        "tool": tool,
        "command": command,
        "out": str(out_path),
        "stale_output_removed": output_prep.get("stale_output_removed"),
        "stale_output_error": output_prep.get("stale_output_error"),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "load_error": load_error,
        "payload_passed": payload_passed,
        "mismatch_count": dict_or_empty(payload).get("mismatch_count"),
        "passed": passed,
    }


Runner = Callable[
    [list[str]],
    subprocess.CompletedProcess[str],
]


def default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def postpack_audit(
    pack_dir: Path,
    *,
    outdir: Path,
    audit_tools: tuple[str, ...] = POSTPACK_AUDIT_TOOLS,
    runner: Runner = default_runner,
) -> dict[str, Any]:
    outdir.mkdir(parents=True, exist_ok=True)
    results = []
    for tool in audit_tools:
        out_path = audit_output_path(outdir, tool)
        command = audit_command(tool, pack_dir, out_path)
        output_prep = prepare_audit_output(out_path)
        try:
            completed = runner(command)
        except OSError as exc:
            completed = subprocess.CompletedProcess(
                command,
                returncode=1,
                stdout="",
                stderr=str(exc),
            )
        results.append(summarize_result(
            tool,
            command,
            out_path,
            completed,
            output_prep,
        ))

    failed = [item for item in results if not item.get("passed")]
    passed = not failed and bool(results)
    return {
        "schema": "qge.postpack_audit.v0",
        "pack_dir": str(pack_dir),
        "outdir": str(outdir),
        "audit_count": len(results),
        "passed_count": len(results) - len(failed),
        "failed_count": len(failed),
        "failed_tools": [item["tool"] for item in failed],
        "audits": results,
        "passed": passed,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pack_dir",
        type=Path,
        help="Publication pack directory to audit.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("/tmp/qge_postpack_audits"),
        help="Directory for child audit JSON outputs.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional combined audit summary JSON output path.",
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit nonzero when any child postpack audit fails.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    audit = postpack_audit(args.pack_dir, outdir=args.outdir)
    if args.out is not None:
        write_json(args.out, audit)
        print(f"QGE_POSTPACK_AUDIT {args.out}")
    else:
        print(json.dumps(audit, indent=2, sort_keys=True))
    return 1 if args.fail_on_mismatch and not audit.get("passed") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
