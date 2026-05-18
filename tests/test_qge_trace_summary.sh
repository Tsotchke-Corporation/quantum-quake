#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/qge-trace-summary.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

trace_file="$tmpdir/qge_trace.bin"
summary_json="$tmpdir/summary.json"
summary_text="$tmpdir/summary.txt"
bad_magic_file="$tmpdir/bad_magic.bin"
truncated_file="$tmpdir/truncated.bin"

python3 - "$trace_file" "$bad_magic_file" "$truncated_file" <<'PY'
import struct
import sys
from pathlib import Path

trace_path = Path(sys.argv[1])
bad_magic_path = Path(sys.argv[2])
truncated_path = Path(sys.argv[3])

TRACE_MAGIC = 0x52544751
TRACE_VERSION = 1
HEADER = struct.Struct("<IHHIIQQQQ")
RECORD = struct.Struct("<HHIQ")
STATE_PROBE = struct.Struct("<iiIIiIQddddiiQ32s")
AI_DECISION = struct.Struct("<iiiiiIIIQQQQiiddddd")


def label(name):
    encoded = name.encode("utf-8")
    return encoded + (b"\0" * (32 - len(encoded)))


def state_probe(
    frame,
    server_time,
    domain,
    representation,
    subject_id,
    flags,
    state_hash,
    entropy,
    coherence,
    max_probability,
    total_probability,
    active_basis_count,
    qubit_count,
    memory_bytes,
    probe_label,
):
    return STATE_PROBE.pack(
        frame,
        server_time,
        domain,
        representation,
        subject_id,
        flags,
        state_hash,
        entropy,
        coherence,
        max_probability,
        total_probability,
        active_basis_count,
        qubit_count,
        memory_bytes,
        label(probe_label),
    )


header = HEADER.pack(
    TRACE_MAGIC,
    TRACE_VERSION,
    HEADER.size,
    0x3,
    0,
    0x5151455F52554E31,
    0x1111,
    0x2222,
    0x3333,
)

records = [
    (
        5,
        0,
        state_probe(1, 100, 5, 1, 42, 0x1, 0x10, 0.25, 0.8, 0.7, 1.0, 4, 3, 128, "ai_action"),
    ),
    (
        5,
        2,
        state_probe(3, 120, 5, 1, 43, 0x4, 0x33, 0.35, 0.6, 0.9, 1.0, 8, 3, 256, "ai_action"),
    ),
    (
        5,
        3,
        state_probe(4, 140, 0, 11, 26, 0x2, 0x44, 0.45, 0.75, 0.5, 64.0, 64, 6, 512, "render_gate_kernel"),
    ),
    (
        8,
        4,
        AI_DECISION.pack(
            5,
            160,
            17,
            2,
            1,
            0x10,
            0x9,
            0x2,
            0x1234,
            0x5,
            0x1,
            7,
            1,
            1,
            0.125,
            0.5,
            0.5,
            1.0,
            0.25,
        ),
    ),
    (6, 5, b""),
]

with trace_path.open("wb") as f:
    f.write(header)
    for kind, sequence, payload in records:
        f.write(RECORD.pack(kind, TRACE_VERSION, len(payload), sequence))
        f.write(payload)

bad_magic_path.write_bytes(
    HEADER.pack(0, TRACE_VERSION, HEADER.size, 0, 0, 0, 0, 0, 0)
)
truncated_path.write_bytes(b"QG")
PY

python3 "$repo_root/tools/qge_trace_summary.py" "$trace_file" --json > "$summary_json"
python3 "$repo_root/tools/qge_trace_summary.py" "$trace_file" > "$summary_text"

python3 - "$summary_json" <<'PY'
import json
import sys

summary = json.load(open(sys.argv[1], encoding="utf-8"))
assert summary["header"]["version"] == 1
assert summary["header"]["flags"] == 0x3
assert summary["header"]["run_id"] == 0x5151455F52554E31
assert summary["records"] == {"ai_decision": 1, "fallback": 1, "state_probe": 3}
assert summary["sequence_errors"] == 1

decision = summary["ai_decisions"][0]
assert summary["replay_health"]["ai_decision_events"] == 1
assert decision["enemy_id"] == 17
assert decision["enemy_type"] == 2
assert decision["action"] == "patrol"
assert decision["mapped_action"] == "patrol"
assert decision["legal_action_mask_or"] == 0x2
assert decision["input_flags_or"] == 0x10
assert decision["output_flags_or"] == 0x9
assert decision["action_basis_xor"] == 0x1
assert decision["last_entropy_offset"] == 7
assert decision["confidence_max"] == 0.25

probes = {(probe["label"], probe["domain"], probe["representation"]): probe for probe in summary["state_probes"]}
ai = probes[("ai_action", "ai", "dense_state")]
assert ai["count"] == 2
assert ai["first_frame"] == 1
assert ai["last_frame"] == 3
assert ai["active_basis_min"] == 4
assert ai["active_basis_max"] == 8
assert ai["qubit_min"] == 3
assert ai["qubit_max"] == 3
assert ai["memory_bytes_max"] == 256
assert ai["flags_or"] == 0x5
assert ai["state_hash_xor"] == (0x10 ^ 0x33)
assert ai["last_subject_id"] == 43

render = probes[("render_gate_kernel", "render", "hybrid")]
assert render["count"] == 1
assert render["total_probability_max"] == 64.0
assert render["max_probability_max"] == 0.5
assert render["last_subject_id"] == 26
PY

grep -F 'Records: {"ai_decision": 1, "fallback": 1, "state_probe": 3}' "$summary_text" >/dev/null
grep -F 'Sequence errors: 1' "$summary_text" >/dev/null
grep -F 'AI decision enemy=17 type=2 target=1 action=patrol mapped=patrol count=1 frames=5..5 legal_mask=0x2 input_flags=0x10 output_flags=0x9 basis_xor=0x1 offsets=7..7 prob=0.500 confidence=0.250' "$summary_text" >/dev/null
grep -F 'Probe ai_action domain=ai rep=dense_state count=2 frames=1..3 basis=4..8 qubits=3..3 max_mem=256 flags_or=0x5 subject=43' "$summary_text" >/dev/null
grep -F 'Probe render_gate_kernel domain=render rep=hybrid count=1 frames=4..4 basis=64..64 qubits=6..6 max_mem=512 flags_or=0x2 gates=26 shots=64 coherence=0.750..0.750 max_prob=0.500' "$summary_text" >/dev/null

if python3 "$repo_root/tools/qge_trace_summary.py" "$bad_magic_file" > "$tmpdir/bad.out" 2> "$tmpdir/bad.err"; then
  echo "expected bad magic failure" >&2
  exit 1
fi
grep -F 'bad trace magic' "$tmpdir/bad.err" >/dev/null

if python3 "$repo_root/tools/qge_trace_summary.py" "$truncated_file" > "$tmpdir/truncated.out" 2> "$tmpdir/truncated.err"; then
  echo "expected truncated trace failure" >&2
  exit 1
fi
grep -F 'trace is too short for a header' "$tmpdir/truncated.err" >/dev/null

echo "QGE trace summary contract: PASSED"
