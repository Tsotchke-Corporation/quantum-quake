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
    8: "ai_decision",
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

ENTROPY_SOURCE_NAMES = {
    0: "qrng",
    1: "replay",
    2: "deterministic",
    3: "classical_fallback",
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

MEASURE_NAMES = {
    0: "none",
    1: "render_sample",
    2: "vis_surface_set",
    3: "projectile_impact",
    4: "particle_position",
    5: "audio_block",
    6: "ai_action",
    7: "rng_batch",
    8: "material_phase",
    9: "physics_collision",
    10: "entanglement_collapse",
    11: "projectile_writeback",
    12: "projectile_branch",
    13: "projectile_collision_oracle",
}

BOUNDARY_NAMES = {
    0: "none",
    1: "player_visible",
    2: "collision",
    3: "damage",
    4: "audio_mix",
    5: "ai_decision",
    6: "network_serialize",
    7: "save_or_demo",
    8: "debug_measure",
    9: "frame_boundary",
}

AI_ACTION_NAMES = {
    0: "idle",
    1: "patrol",
    2: "chase",
    3: "attack",
    4: "flee",
    5: "pain",
    6: "dead",
}

HEADER = struct.Struct("<IHHIIQQQQ")
RECORD = struct.Struct("<HHIQ")
ENTROPY = struct.Struct("<iiIIiIQQ")
MEASUREMENT = struct.Struct("<IIIiiiI4xQddQQ")
STATE_PROBE = struct.Struct("<iiIIiIQddddiiQ32s")
FALLBACK = struct.Struct("<iiIIiid96s")
AI_DECISION = struct.Struct("<iiiiiIIIQQQQiiddddd")

VIS_FLAGS = {
    "registered": 0x0001,
    "mismatch": 0x0002,
    "false_positive": 0x0004,
    "false_negative": 0x0008,
    "overflow": 0x0010,
    "authority_requested": 0x0020,
    "authority_ready": 0x0040,
    "authority_selected": 0x0080,
    "fallback_selected": 0x0100,
    "warmup_pending": 0x0200,
    "controlled_authority_smoke": 0x0400,
    "false_negative_repaired": 0x0800,
}

AUDIO_FLAGS = {
    "dry_fallback": 0x0001,
    "processed": 0x0002,
    "clipped": 0x0004,
    "spatial": 0x0008,
    "view_entity": 0x0010,
}

RENDER_FLAGS = {
    "primary_owned": 0x00010000,
    "native_idwt": 0x00020000,
    "native_idwt_fallback": 0x00040000,
    "cpu_idwt": 0x00080000,
}

PROJECTILE_FLAGS = {
    "authority_ready": 0x0100,
    "quantum_physics_enabled": 0x0200,
    "quantum_projectiles_enabled": 0x0400,
    "min_shadow_samples": 0x0800,
    "authority_requested": 0x1000,
    "writeback_selected": 0x2000,
    "fallback_selected": 0x4000,
    "rollback_required": 0x8000,
    "physics_authoritative_cvar": 0x10000,
    "branch_state": 0x20000,
    "branch_observed": 0x40000,
    "impact_measured": 0x80000,
    "branch_selected_qge": 0x100000,
    "branch_selected_impact": 0x200000,
    "branch_decohered": 0x400000,
    "collision_oracle": 0x800000,
    "oracle_qge_trace": 0x1000000,
    "oracle_no_impact": 0x2000000,
    "oracle_alternate_impact": 0x4000000,
    "oracle_classic_trace": 0x8000000,
    "save_demo_boundary": 0x10000000,
    "save_demo_collision_oracle": 0x20000000,
    "save_demo_writeback": 0x40000000,
}

PROJECTILE_OFF_REASONS = {
    0: "none",
    1: "disabled",
    2: "no_projectiles",
    3: "warmup",
    4: "shadow_max",
    5: "shadow_avg",
    6: "trace_invalid",
}


def clean_label(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def increment_group(groups: dict[tuple, dict], key: tuple, initial: dict, frame: int) -> dict:
    group = groups.get(key)
    if group is None:
        group = dict(initial)
        group["count"] = 0
        group["first_frame"] = frame
        group["last_frame"] = frame
        groups[key] = group
    group["count"] += 1
    group["first_frame"] = min(group["first_frame"], frame)
    group["last_frame"] = max(group["last_frame"], frame)
    return group


def flags_summary(flags: int, mapping: dict[str, int]) -> dict[str, bool]:
    return {name: bool(flags & bit) for name, bit in mapping.items()}


def classify_render_idwt_backend_name(flags: int) -> str:
    selected = []
    if flags & RENDER_FLAGS["native_idwt"]:
        selected.append("native")
    if flags & RENDER_FLAGS["native_idwt_fallback"]:
        selected.append("native_fallback")
    if flags & RENDER_FLAGS["cpu_idwt"]:
        selected.append("cpu")
    if len(selected) > 1:
        return "mixed"
    return selected[0] if selected else "none"


def probe_by_label(probes: list[dict], label: str) -> dict | None:
    for probe in probes:
        if probe.get("label") == label:
            return probe
    return None


def probe_count(probes: list[dict], label: str, domain: str | None = None) -> int:
    total = 0
    for probe in probes:
        if probe.get("label") != label:
            continue
        if domain is not None and probe.get("domain") != domain:
            continue
        total += int(probe.get("count", 0) or 0)
    return total


def build_runtime_evidence(summary: dict) -> dict:
    probes = summary.get("state_probes", [])
    records = summary.get("records", {})
    ai_decision_count = sum(
        int(decision.get("count", 0) or 0)
        for decision in summary.get("ai_decisions", [])
    )
    audio_source_spatial = probe_by_label(probes, "audio_source_spatial")
    audio_source_frame = probe_by_label(probes, "audio_source_frame")
    audio_pan_authority = probe_by_label(
        probes, "audio_attenuation_pan_authority")
    vis_shadow = probe_by_label(probes, "vis_shadow_parity")
    vis_gate = probe_by_label(probes, "vis_authority_gate")
    vis_apply = probe_by_label(probes, "vis_authority_apply")
    render_sparse = probe_by_label(probes, "render_sparse_dwt")
    projectile_gate = probe_by_label(probes, "projectile_authority_gate")
    projectile_writeback = probe_by_label(
        probes, "projectile_writeback_decision")
    projectile_branch = probe_by_label(probes, "projectile_branch_state")
    projectile_preimpact = probe_by_label(
        probes, "projectile_preimpact_selection")

    audio_source_spatial_count = probe_count(
        probes, "audio_source_spatial", "audio")
    audio_source_frame_count = probe_count(
        probes, "audio_source_frame", "audio")
    audio_pan_authority_count = probe_count(
        probes, "audio_attenuation_pan_authority", "audio")
    vis_shadow_count = probe_count(
        probes, "vis_shadow_parity", "visibility")
    vis_gate_count = probe_count(
        probes, "vis_authority_gate", "visibility")
    vis_apply_count = probe_count(
        probes, "vis_authority_apply", "visibility")
    render_sparse_count = probe_count(
        probes, "render_sparse_dwt", "render")
    projectile_gate_count = probe_count(
        probes, "projectile_authority_gate", "projectile")
    projectile_writeback_count = probe_count(
        probes, "projectile_writeback_decision", "projectile")
    projectile_branch_count = probe_count(
        probes, "projectile_branch_state", "projectile")
    projectile_preimpact_count = probe_count(
        probes, "projectile_preimpact_selection", "projectile")
    projectile_impact_measurement_count = sum(
        int(measurement.get("count", 0) or 0)
        for measurement in summary.get("measurements", [])
        if measurement.get("domain") == "projectile"
        and measurement.get("kind") == "projectile_impact"
    )
    projectile_save_demo_measurements = [
        measurement for measurement in summary.get("measurements", [])
        if measurement.get("domain") == "projectile"
        and measurement.get("boundary") == "save_or_demo"
    ]
    projectile_save_demo_count = sum(
        int(measurement.get("count", 0) or 0)
        for measurement in projectile_save_demo_measurements
    )
    projectile_save_demo_flags = 0
    projectile_save_demo_trace_xor = 0
    for measurement in projectile_save_demo_measurements:
        projectile_save_demo_flags |= int(measurement.get("flags_or", 0) or 0)
        projectile_save_demo_trace_xor ^= int(
            measurement.get("trace_id_xor", 0) or 0)
    projectile_writeback_save_demo_count = sum(
        int(measurement.get("count", 0) or 0)
        for measurement in projectile_save_demo_measurements
        if measurement.get("kind") == "projectile_writeback"
    )
    projectile_branch_save_demo_count = sum(
        int(measurement.get("count", 0) or 0)
        for measurement in projectile_save_demo_measurements
        if measurement.get("kind") == "projectile_branch"
    )
    projectile_collision_oracle_save_demo_count = sum(
        int(measurement.get("count", 0) or 0)
        for measurement in projectile_save_demo_measurements
        if measurement.get("kind") == "projectile_collision_oracle"
    )

    audio_flags = 0
    for probe in (audio_source_spatial, audio_source_frame,
                  audio_pan_authority):
        if probe:
            audio_flags |= int(probe.get("flags_or", 0) or 0)

    visibility_flags = 0
    if vis_apply:
        visibility_flags = int(vis_apply.get("last_flags", 0) or 0)
    elif vis_gate:
        visibility_flags = int(vis_gate.get("last_flags", 0) or 0)
    render_flags = (
        int(render_sparse.get("flags_or", 0) or 0)
        if render_sparse else 0
    )
    projectile_flags = (
        int(projectile_gate.get("flags_or", 0) or 0)
        if projectile_gate else 0
    )
    if projectile_writeback:
        projectile_flags |= (
            int(projectile_writeback.get("flags_or", 0) or 0) & ~0xff
        )
    if projectile_branch:
        projectile_flags |= (
            int(projectile_branch.get("flags_or", 0) or 0) & ~0xff
        )
    if projectile_preimpact:
        projectile_flags |= (
            int(projectile_preimpact.get("flags_or", 0) or 0) & ~0xff
        )
    projectile_flags |= projectile_save_demo_flags & ~0xff
    projectile_off_reason_flags = (
        int(projectile_gate.get("last_flags", projectile_flags) or 0)
        if projectile_gate else projectile_flags
    )
    projectile_off_reason_code = projectile_off_reason_flags & 0xff

    ai_ready = ai_decision_count > 0 and int(records.get("ai_decision", 0)) > 0
    audio_ready = audio_source_spatial_count > 0
    visibility_ready = (
        vis_shadow_count > 0 and
        vis_gate_count > 0 and
        vis_apply_count > 0
    )
    projectile_ready = projectile_gate_count > 0

    return {
        "single_trace_ready": (
            ai_ready and audio_ready and visibility_ready and projectile_ready
        ),
        "ai": {
            "ready": ai_ready,
            "decision_count": ai_decision_count,
            "record_count": int(records.get("ai_decision", 0) or 0),
        },
        "audio": {
            "ready": audio_ready,
            "source_spatial_count": audio_source_spatial_count,
            "source_frame_count": audio_source_frame_count,
            "attenuation_pan_authority_count": audio_pan_authority_count,
            "flags": flags_summary(audio_flags, AUDIO_FLAGS),
            "flags_or": audio_flags,
        },
        "render": {
            "sparse_dwt_count": render_sparse_count,
            "flags": flags_summary(render_flags, RENDER_FLAGS),
            "flags_or": render_flags,
            "idwt_backend": classify_render_idwt_backend_name(render_flags),
            "native_bridge_count": (
                render_sparse_count
                if render_flags & RENDER_FLAGS["native_idwt"]
                else 0
            ),
            "native_fallback_count": (
                render_sparse_count
                if render_flags & RENDER_FLAGS["native_idwt_fallback"]
                else 0
            ),
            "cpu_idwt_count": (
                render_sparse_count
                if render_flags & RENDER_FLAGS["cpu_idwt"]
                else 0
            ),
        },
        "visibility": {
            "ready": visibility_ready,
            "shadow_parity_count": vis_shadow_count,
            "authority_gate_count": vis_gate_count,
            "authority_apply_count": vis_apply_count,
            "flags": flags_summary(visibility_flags, VIS_FLAGS),
            "flags_or": visibility_flags,
            "fallback_reason_code": (
                int(round(vis_gate.get("entropy_max", 0.0)))
                if vis_gate else None
            ),
            "clean_frames": (
                int(vis_gate.get("active_basis_max", 0) or 0)
                if vis_gate else 0
            ),
            "clean_frames_required": (
                int(vis_gate.get("qubit_max", 0) or 0)
                if vis_gate else 0
            ),
        },
        "projectile": {
            "ready": projectile_ready,
            "authority_gate_count": projectile_gate_count,
            "writeback_decision_count": projectile_writeback_count,
            "branch_state_count": projectile_branch_count,
            "preimpact_selection_count": projectile_preimpact_count,
            "preimpact_oracle_count": (
                projectile_preimpact_count
                if projectile_flags & PROJECTILE_FLAGS["collision_oracle"]
                else 0
            ),
            "preimpact_no_impact_count": (
                projectile_preimpact_count
                if projectile_flags & PROJECTILE_FLAGS["oracle_no_impact"]
                else 0
            ),
            "preimpact_alternate_impact_count": (
                projectile_preimpact_count
                if projectile_flags & PROJECTILE_FLAGS["oracle_alternate_impact"]
                else 0
            ),
            "impact_measurement_count": projectile_impact_measurement_count,
            "save_demo_boundary_count": projectile_save_demo_count,
            "save_demo_writeback_count": projectile_writeback_save_demo_count,
            "save_demo_branch_count": projectile_branch_save_demo_count,
            "save_demo_collision_oracle_count": (
                projectile_collision_oracle_save_demo_count
            ),
            "save_demo_trace_id_xor": projectile_save_demo_trace_xor,
            "flags": flags_summary(projectile_flags, PROJECTILE_FLAGS),
            "flags_or": projectile_flags,
            "off_reason_code": projectile_off_reason_code,
            "off_reason": PROJECTILE_OFF_REASONS.get(
                projectile_off_reason_code,
                f"reason_{projectile_off_reason_code}",
            ),
            "active_projectiles": (
                int(projectile_gate.get("last_subject_id", 0) or 0)
                if projectile_gate else 0
            ),
            "active_projectiles_max": (
                int(projectile_gate.get("subject_id_max", 0) or 0)
                if projectile_gate else 0
            ),
            "shadow_samples": (
                int(projectile_gate.get("active_basis_max", 0) or 0)
                if projectile_gate else 0
            ),
            "branch_basis_max": (
                int(projectile_branch.get("active_basis_max", 0) or 0)
                if projectile_branch else 0
            ),
            "branch_selected_probability_max": (
                float(projectile_branch.get("max_probability_max", 0.0) or 0.0)
                if projectile_branch else 0.0
            ),
            "branch_coherence_min": (
                float(projectile_branch.get("coherence_min", 0.0) or 0.0)
                if projectile_branch else 0.0
            ),
            "branch_coherence_max": (
                float(projectile_branch.get("coherence_max", 0.0) or 0.0)
                if projectile_branch else 0.0
            ),
            "preimpact_selected_probability_max": (
                float(projectile_preimpact.get("max_probability_max", 0.0) or 0.0)
                if projectile_preimpact else 0.0
            ),
        },
    }


def parse_trace(path: str) -> dict:
    record_counts: Counter[str] = Counter()
    probe_groups: dict[tuple[str, str, str], dict] = {}
    entropy_groups: dict[tuple[str, str], dict] = {}
    measurement_groups: dict[tuple[str, str, str], dict] = {}
    fallback_groups: dict[tuple[str, int, str], dict] = {}
    ai_decision_groups: dict[tuple[int, str], dict] = {}
    replay_health = {
        "entropy_replay_events": 0,
        "replay_metadata_mismatches": 0,
        "replay_exhaustions": 0,
        "ai_decision_events": 0,
        "ai_decision_replay_metadata_mismatches": 0,
        "ai_decision_replay_exhaustions": 0,
    }

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

            if kind == 3 and payload_size == ENTROPY.size:
                unpacked = ENTROPY.unpack(payload)
                frame, _server_time, domain, source, subject_id, request_id = unpacked[:6]
                value, entropy_offset = unpacked[6:8]
                domain_name = DOMAIN_NAMES.get(domain, f"domain_{domain}")
                source_name = ENTROPY_SOURCE_NAMES.get(source, f"source_{source}")
                group = increment_group(
                    entropy_groups,
                    (domain_name, source_name),
                    {
                        "domain": domain_name,
                        "source": source_name,
                        "first_request_id": request_id,
                        "last_request_id": request_id,
                        "first_entropy_offset": entropy_offset,
                        "last_entropy_offset": entropy_offset,
                        "last_subject_id": subject_id,
                        "value_xor": 0,
                    },
                    frame,
                )
                group["last_request_id"] = request_id
                group["last_entropy_offset"] = entropy_offset
                group["last_subject_id"] = subject_id
                group["value_xor"] ^= value
                if source_name == "replay":
                    replay_health["entropy_replay_events"] += 1
                continue

            if kind == 4 and payload_size == MEASUREMENT.size:
                unpacked = MEASUREMENT.unpack(payload)
                domain, measure_kind, boundary = unpacked[:3]
                frame, _server_time, subject_id, flags = unpacked[3:7]
                basis_index, probability, phase, entropy_offset, trace_id = unpacked[7:12]
                domain_name = DOMAIN_NAMES.get(domain, f"domain_{domain}")
                kind_name = MEASURE_NAMES.get(
                    measure_kind, f"measure_{measure_kind}")
                boundary_name = BOUNDARY_NAMES.get(
                    boundary, f"boundary_{boundary}")
                group = increment_group(
                    measurement_groups,
                    (domain_name, kind_name, boundary_name),
                    {
                        "domain": domain_name,
                        "kind": kind_name,
                        "boundary": boundary_name,
                        "last_subject_id": subject_id,
                        "flags_or": 0,
                        "basis_xor": 0,
                        "probability_max": probability,
                        "phase_max": phase,
                        "first_entropy_offset": entropy_offset,
                        "last_entropy_offset": entropy_offset,
                        "trace_id_xor": 0,
                    },
                    frame,
                )
                group["last_subject_id"] = subject_id
                group["flags_or"] |= flags
                group["basis_xor"] ^= basis_index
                group["probability_max"] = max(
                    group["probability_max"], probability)
                group["phase_max"] = max(group["phase_max"], phase)
                group["first_entropy_offset"] = min(
                    group["first_entropy_offset"], entropy_offset)
                group["last_entropy_offset"] = max(
                    group["last_entropy_offset"], entropy_offset)
                group["trace_id_xor"] ^= trace_id
                continue

            if kind == 6 and payload_size == FALLBACK.size:
                unpacked = FALLBACK.unpack(payload)
                frame, _server_time, domain, rep, subject_id, reason_code = unpacked[:6]
                metric_value = unpacked[6]
                message = clean_label(unpacked[7])
                domain_name = DOMAIN_NAMES.get(domain, f"domain_{domain}")
                rep_name = REP_NAMES.get(rep, f"rep_{rep}")
                group = increment_group(
                    fallback_groups,
                    (domain_name, reason_code, message),
                    {
                        "domain": domain_name,
                        "representation": rep_name,
                        "reason_code": reason_code,
                        "message": message,
                        "last_subject_id": subject_id,
                        "metric_value_max": metric_value,
                    },
                    frame,
                )
                group["last_subject_id"] = subject_id
                group["metric_value_max"] = max(group["metric_value_max"], metric_value)
                if reason_code == 1 and message == "replay entropy metadata mismatch":
                    replay_health["replay_metadata_mismatches"] += 1
                elif reason_code == 2 and message == "replay entropy exhausted":
                    replay_health["replay_exhaustions"] += 1
                elif reason_code == 3 and message == "replay ai decision metadata mismatch":
                    replay_health["ai_decision_replay_metadata_mismatches"] += 1
                elif reason_code == 4 and message == "replay ai decision exhausted":
                    replay_health["ai_decision_replay_exhaustions"] += 1
                continue

            if kind == 8 and payload_size == AI_DECISION.size:
                replay_health["ai_decision_events"] += 1
                unpacked = AI_DECISION.unpack(payload)
                frame, _server_time, enemy_id, enemy_type, target_entnum = unpacked[:5]
                input_flags, output_flags, legal_action_mask = unpacked[5:8]
                input_hash, raw_basis, action_basis, entropy_offset = unpacked[8:12]
                mapped_action, action = unpacked[12:14]
                selected_probability, action_probability, max_probability, total_probability, confidence = unpacked[14:19]
                action_name = AI_ACTION_NAMES.get(action, f"action_{action}")
                mapped_action_name = AI_ACTION_NAMES.get(mapped_action, f"action_{mapped_action}")
                group = increment_group(
                    ai_decision_groups,
                    (enemy_id, action_name),
                    {
                        "enemy_id": enemy_id,
                        "enemy_type": enemy_type,
                        "target_entnum": target_entnum,
                        "action": action_name,
                        "action_code": action,
                        "mapped_action": mapped_action_name,
                        "mapped_action_code": mapped_action,
                        "legal_action_mask_or": 0,
                        "input_flags_or": 0,
                        "output_flags_or": 0,
                        "input_hash_xor": 0,
                        "raw_basis_xor": 0,
                        "action_basis_xor": 0,
                        "first_entropy_offset": entropy_offset,
                        "last_entropy_offset": entropy_offset,
                        "selected_probability_max": selected_probability,
                        "action_probability_max": action_probability,
                        "max_probability_max": max_probability,
                        "total_probability_max": total_probability,
                        "confidence_max": confidence,
                    },
                    frame,
                )
                group["enemy_type"] = enemy_type
                group["target_entnum"] = target_entnum
                group["mapped_action"] = mapped_action_name
                group["mapped_action_code"] = mapped_action
                group["legal_action_mask_or"] |= legal_action_mask
                group["input_flags_or"] |= input_flags
                group["output_flags_or"] |= output_flags
                group["input_hash_xor"] ^= input_hash
                group["raw_basis_xor"] ^= raw_basis
                group["action_basis_xor"] ^= action_basis
                group["first_entropy_offset"] = min(group["first_entropy_offset"], entropy_offset)
                group["last_entropy_offset"] = max(group["last_entropy_offset"], entropy_offset)
                group["selected_probability_max"] = max(group["selected_probability_max"], selected_probability)
                group["action_probability_max"] = max(group["action_probability_max"], action_probability)
                group["max_probability_max"] = max(group["max_probability_max"], max_probability)
                group["total_probability_max"] = max(group["total_probability_max"], total_probability)
                group["confidence_max"] = max(group["confidence_max"], confidence)
                continue

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
                    "last_flags": probe_flags,
                    "state_hash_xor": 0,
                    "entropy_min": entropy,
                    "entropy_max": entropy,
                    "coherence_min": coherence,
                    "coherence_max": coherence,
                    "total_probability_max": total_probability,
                    "max_probability_max": max_probability,
                    "first_server_time_msec": server_time,
                    "last_subject_id": subject_id,
                    "subject_id_max": subject_id,
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
            group["last_flags"] = probe_flags
            group["state_hash_xor"] ^= state_hash
            group["entropy_min"] = min(group["entropy_min"], entropy)
            group["entropy_max"] = max(group["entropy_max"], entropy)
            group["coherence_min"] = min(group["coherence_min"], coherence)
            group["coherence_max"] = max(group["coherence_max"], coherence)
            group["total_probability_max"] = max(group["total_probability_max"], total_probability)
            group["max_probability_max"] = max(group["max_probability_max"], max_probability)
            group["last_subject_id"] = subject_id
            group["subject_id_max"] = max(group["subject_id_max"], subject_id)

    summary = {
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
        "entropy_events": sorted(entropy_groups.values(), key=lambda item: (item["domain"], item["source"])),
        "measurements": sorted(measurement_groups.values(), key=lambda item: (item["domain"], item["kind"], item["boundary"])),
        "fallback_events": sorted(fallback_groups.values(), key=lambda item: (item["domain"], item["reason_code"], item["message"])),
        "ai_decisions": sorted(ai_decision_groups.values(), key=lambda item: (item["enemy_id"], item["action"])),
        "replay_health": replay_health,
        "state_probes": sorted(probe_groups.values(), key=lambda item: (item["domain"], item["label"])),
    }
    summary["runtime_evidence"] = build_runtime_evidence(summary)
    return summary


def print_text(summary: dict) -> None:
    print(f"Trace: {summary['path']}")
    print(f"Run: 0x{summary['header']['run_id']:016x}")
    print(f"Records: {json.dumps(summary['records'], sort_keys=True)}")
    print(f"Sequence errors: {summary['sequence_errors']}")
    print(f"Runtime evidence: {json.dumps(summary['runtime_evidence'], sort_keys=True)}")
    if any(summary["replay_health"].values()):
        print(f"Replay: {json.dumps(summary['replay_health'], sort_keys=True)}")
    for entropy in summary["entropy_events"]:
        print(
            "Entropy "
            f"domain={entropy['domain']} source={entropy['source']} "
            f"count={entropy['count']} frames={entropy['first_frame']}..{entropy['last_frame']} "
            f"requests={entropy['first_request_id']}..{entropy['last_request_id']} "
            f"offsets={entropy['first_entropy_offset']}..{entropy['last_entropy_offset']} "
            f"subject={entropy['last_subject_id']} value_xor=0x{entropy['value_xor']:x}"
        )
    for measurement in summary["measurements"]:
        print(
            "Measurement "
            f"domain={measurement['domain']} kind={measurement['kind']} "
            f"boundary={measurement['boundary']} count={measurement['count']} "
            f"frames={measurement['first_frame']}..{measurement['last_frame']} "
            f"subject={measurement['last_subject_id']} "
            f"flags=0x{measurement['flags_or']:x} "
            f"basis_xor=0x{measurement['basis_xor']:x} "
            f"prob={measurement['probability_max']:.3f}"
        )
    for fallback in summary["fallback_events"]:
        print(
            "Fallback "
            f"domain={fallback['domain']} rep={fallback['representation']} "
            f"reason={fallback['reason_code']} count={fallback['count']} "
            f"frames={fallback['first_frame']}..{fallback['last_frame']} "
            f"subject={fallback['last_subject_id']} message={fallback['message']}"
        )
    for decision in summary["ai_decisions"]:
        print(
            "AI decision "
            f"enemy={decision['enemy_id']} type={decision['enemy_type']} "
            f"target={decision['target_entnum']} action={decision['action']} "
            f"mapped={decision['mapped_action']} count={decision['count']} "
            f"frames={decision['first_frame']}..{decision['last_frame']} "
            f"legal_mask=0x{decision['legal_action_mask_or']:x} "
            f"input_flags=0x{decision['input_flags_or']:x} "
            f"output_flags=0x{decision['output_flags_or']:x} "
            f"basis_xor=0x{decision['action_basis_xor']:x} "
            f"offsets={decision['first_entropy_offset']}..{decision['last_entropy_offset']} "
            f"prob={decision['action_probability_max']:.3f} "
            f"confidence={decision['confidence_max']:.3f}"
        )
    for probe in summary["state_probes"]:
        extra = f" subject={probe['last_subject_id']}"
        if probe["label"] == "render_gate_kernel":
            extra = (
                f" gates={probe['last_subject_id']} "
                f"shots={int(round(probe['total_probability_max']))} "
                f"coherence={probe['coherence_min']:.3f}..{probe['coherence_max']:.3f} "
                f"max_prob={probe['max_probability_max']:.3f}"
            )
        print(
            "Probe "
            f"{probe['label']} domain={probe['domain']} rep={probe['representation']} "
            f"count={probe['count']} frames={probe['first_frame']}..{probe['last_frame']} "
            f"basis={probe['active_basis_min']}..{probe['active_basis_max']} "
            f"qubits={probe['qubit_min']}..{probe['qubit_max']} "
            f"max_mem={probe['memory_bytes_max']} flags_or=0x{probe['flags_or']:x}"
            f"{extra}"
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
