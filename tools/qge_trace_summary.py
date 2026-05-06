#!/usr/bin/env python3
"""Summarize QGE binary trace probes.

The trace format is intentionally fixed-width C records. This tool focuses on
state probes because they are the publication-facing contract for which quantum
representation owned each subsystem and how many basis states/qubits it used.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter


TRACE_MAGIC = 0x52544751
TRACE_VERSION = 1

RECORD_NAMES = {
    1: "frame_begin",
    2: "frame_end",
    3: "entropy",
    4: "measurement",
    5: "state_probe",
    6: "fallback",
    7: "entanglement",
}

DOMAIN_NAMES = {
    0: "render",
    1: "visibility",
    2: "projectile",
    3: "particle",
    4: "audio",
    5: "ai",
    6: "rng",
    7: "material",
    8: "physics",
    9: "ui",
}

REP_NAMES = {
    0: "none",
    1: "dense_state",
    2: "sparse_dwt",
    3: "mps",
    4: "ca_mps",
    5: "clifford_tableau",
    6: "pauli_frame",
    7: "classical_oracle",
    8: "grover_search",
    9: "dct_transducer",
    10: "material_phase_field",
    11: "hybrid",
}

HEADER = struct.Struct("<IHHIIQQQQ")
RECORD = struct.Struct("<HHIQ")
STATE_PROBE = struct.Struct("<iiIIiIQddddiiQ32s")


def clean_label(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def parse_trace(path: str) -> dict:
    record_counts: Counter[str] = Counter()
    probe_groups: dict[tuple[str, str, str], dict] = {}

    with open(path, "rb") as f:
        header_raw = f.read(HEADER.size)
        if len(header_raw) != HEADER.size:
            raise ValueError("trace is too short for a header")
        magic, version, header_size, flags, _reserved, run_id, moonlab_hash, qge_hash, content_hash = HEADER.unpack(header_raw)
        if magic != TRACE_MAGIC:
            raise ValueError(f"bad trace magic 0x{magic:08x}")
        if version != TRACE_VERSION:
            raise ValueError(f"unsupported trace version {version}")
        if header_size > HEADER.size:
            f.seek(header_size - HEADER.size, 1)

        sequence_errors = 0
        expected_sequence = 0
        while True:
            record_raw = f.read(RECORD.size)
            if not record_raw:
                break
            if len(record_raw) != RECORD.size:
                raise ValueError("truncated record header")
            kind, rec_version, payload_size, sequence = RECORD.unpack(record_raw)
            payload = f.read(payload_size)
            if len(payload) != payload_size:
                raise ValueError("truncated record payload")
            if rec_version != TRACE_VERSION:
                raise ValueError(f"unsupported record version {rec_version}")
            if sequence != expected_sequence:
                sequence_errors += 1
                expected_sequence = sequence
            expected_sequence += 1

            record_name = RECORD_NAMES.get(kind, f"unknown_{kind}")
            record_counts[record_name] += 1
            if kind != 5 or payload_size != STATE_PROBE.size:
                continue

            unpacked = STATE_PROBE.unpack(payload)
            frame, server_time, domain, rep, subject_id, probe_flags = unpacked[:6]
            state_hash = unpacked[6]
            entropy, coherence, max_probability, total_probability = unpacked[7:11]
            active_basis_count, qubit_count, memory_bytes = unpacked[11:14]
            label = clean_label(unpacked[14])

            domain_name = DOMAIN_NAMES.get(domain, f"domain_{domain}")
            rep_name = REP_NAMES.get(rep, f"rep_{rep}")
            key = (label, domain_name, rep_name)
            group = probe_groups.get(key)
            if group is None:
                group = {
                    "label": label,
                    "domain": domain_name,
                    "representation": rep_name,
                    "count": 0,
                    "first_frame": frame,
                    "last_frame": frame,
                    "active_basis_min": active_basis_count,
                    "active_basis_max": active_basis_count,
                    "qubit_min": qubit_count,
                    "qubit_max": qubit_count,
                    "memory_bytes_max": memory_bytes,
                    "flags_or": 0,
                    "state_hash_xor": 0,
                    "coherence_min": coherence,
                    "coherence_max": coherence,
                    "total_probability_max": total_probability,
                    "max_probability_max": max_probability,
                    "first_server_time_msec": server_time,
                    "last_subject_id": subject_id,
                }
                probe_groups[key] = group

            group["count"] += 1
            group["first_frame"] = min(group["first_frame"], frame)
            group["last_frame"] = max(group["last_frame"], frame)
            group["active_basis_min"] = min(group["active_basis_min"], active_basis_count)
            group["active_basis_max"] = max(group["active_basis_max"], active_basis_count)
            group["qubit_min"] = min(group["qubit_min"], qubit_count)
            group["qubit_max"] = max(group["qubit_max"], qubit_count)
            group["memory_bytes_max"] = max(group["memory_bytes_max"], memory_bytes)
            group["flags_or"] |= probe_flags
            group["state_hash_xor"] ^= state_hash
            group["coherence_min"] = min(group["coherence_min"], coherence)
            group["coherence_max"] = max(group["coherence_max"], coherence)
            group["total_probability_max"] = max(group["total_probability_max"], total_probability)
            group["max_probability_max"] = max(group["max_probability_max"], max_probability)
            group["last_subject_id"] = subject_id

    return {
        "path": path,
        "header": {
            "version": version,
            "flags": flags,
            "run_id": run_id,
            "moonlab_abi_hash": moonlab_hash,
            "qge_build_hash": qge_hash,
            "quake_content_hash": content_hash,
        },
        "records": dict(sorted(record_counts.items())),
        "sequence_errors": sequence_errors,
        "state_probes": sorted(probe_groups.values(), key=lambda item: (item["domain"], item["label"])),
    }


def print_text(summary: dict) -> None:
    print(f"Trace: {summary['path']}")
    print(f"Run: 0x{summary['header']['run_id']:016x}")
    print(f"Records: {json.dumps(summary['records'], sort_keys=True)}")
    print(f"Sequence errors: {summary['sequence_errors']}")
    for probe in summary["state_probes"]:
        print(
            "Probe "
            f"{probe['label']} domain={probe['domain']} rep={probe['representation']} "
            f"count={probe['count']} frames={probe['first_frame']}..{probe['last_frame']} "
            f"basis={probe['active_basis_min']}..{probe['active_basis_max']} "
            f"qubits={probe['qubit_min']}..{probe['qubit_max']} "
            f"max_mem={probe['memory_bytes_max']} flags_or=0x{probe['flags_or']:x}"
        )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", help="Path to qge_trace.bin")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args(argv)

    try:
        summary = parse_trace(args.trace)
    except (OSError, ValueError) as exc:
        print(f"qge_trace_summary: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print_text(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
