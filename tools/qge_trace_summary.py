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
    10: "weapon",
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
    14: "weapon_operation",
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

REQUIRED_OBSERVATION_BOUNDARIES = (
    "player_visible",
    "collision",
    "damage",
    "audio_mix",
    "ai_decision",
    "save_or_demo",
    "debug_measure",
)

AI_ACTION_NAMES = {
    0: "idle",
    1: "patrol",
    2: "chase",
    3: "attack",
    4: "flee",
    5: "pain",
    6: "dead",
}

AI_ENEMY_TYPE_CLASSES = {
    0: "monster_army",
    1: "monster_knight",
    2: "monster_ogre",
    3: "monster_demon1",
    4: "monster_shambler",
    5: "monster_zombie",
    6: "monster_dog",
    7: "monster_wizard",
    8: "monster_boss",
    9: "unknown",
}

QGE_AI_INPUT_FLAG_ENEMY_CLASS_KNOWN = 1 << 31

WEAPON_ID_CLASSES = {
    1: "weapon_shotgun",
    2: "weapon_supershotgun",
    4: "weapon_nailgun",
    8: "weapon_supernailgun",
    16: "weapon_grenadelauncher",
    32: "weapon_rocketlauncher",
    64: "weapon_lightning",
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
    "gameplay_authority_measurement": 0x80000000,
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

MATERIAL_FLAGS = {
    "gameplay_state": 0x0001,
    "world_surface": 0x0002,
    "player_medium": 0x0004,
    "player_powerup": 0x0008,
}

WEAPON_FLAGS = {
    "gameplay_state": 0x0001,
    "hitscan": 0x0002,
    "projectile": 0x0004,
    "melee": 0x0008,
    "continuous": 0x0010,
    "ammo_consumed": 0x0020,
    "damage_result": 0x0040,
    "noise_operation": 0x0080,
    "noncommuting": 0x0100,
}

SHAREWARE_ENCOUNTER_FLAGS = {
    "active": 0x00010000,
    "interference": 0x00020000,
    "decoherence": 0x00040000,
    "observed": 0x00080000,
    "material_phase": 0x00100000,
    "player_visible": 0x00200000,
    "e1m1": 0x00400000,
    "render_feedback": 0x00800000,
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


def probe_by_label_domain(
    probes: list[dict],
    label: str,
    domain: str,
) -> dict | None:
    for probe in probes:
        if probe.get("label") == label and probe.get("domain") == domain:
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


def probe_subject_count(
    probes: list[dict],
    label: str,
    domain: str | None = None,
) -> int:
    total = 0
    for probe in probes:
        if probe.get("label") != label:
            continue
        if domain is not None and probe.get("domain") != domain:
            continue
        total = max(
            total,
            int(probe.get("subject_id_max", 0) or 0),
            int(probe.get("active_basis_max", 0) or 0),
        )
    return total


def build_observation_boundary_evidence(measurements: list[dict]) -> dict:
    boundary_counts: Counter[str] = Counter()
    measurement_keys_by_boundary: dict[str, set[str]] = {}

    for measurement in measurements:
        boundary = str(measurement.get("boundary", "none"))
        count = int(measurement.get("count", 0) or 0)
        boundary_counts[boundary] += count
        measurement_key = (
            f"{measurement.get('domain', 'unknown')}."
            f"{measurement.get('kind', 'unknown')}"
        )
        measurement_keys_by_boundary.setdefault(
            boundary, set()).add(measurement_key)

    required_counts = {
        boundary: int(boundary_counts.get(boundary, 0))
        for boundary in REQUIRED_OBSERVATION_BOUNDARIES
    }
    required = {
        boundary: count > 0
        for boundary, count in required_counts.items()
    }
    missing = [
        boundary for boundary in REQUIRED_OBSERVATION_BOUNDARIES
        if not required[boundary]
    ]

    evidence = {
        "all_required_boundaries": not missing,
        "missing_required_boundaries": missing,
        "observed_boundary_count": sum(
            1 for count in boundary_counts.values() if count > 0
        ),
        "boundary_counts": {
            boundary: int(boundary_counts[boundary])
            for boundary in sorted(boundary_counts)
        },
        "required_boundary_counts": required_counts,
        "required": required,
        "measurement_keys_by_boundary": {
            boundary: sorted(keys)
            for boundary, keys in sorted(measurement_keys_by_boundary.items())
        },
    }
    evidence.update(required)
    return evidence


def build_lab_overlay_evidence(summary: dict) -> dict:
    probes = summary.get("state_probes", [])
    measurements = summary.get("measurements", [])
    entropy_events = summary.get("entropy_events", [])
    fallback_events = summary.get("fallback_events", [])
    branch_labels = {
        "projectile_branch_state",
        "projectile_preimpact_selection",
    }

    state_probe_count = sum(
        int(probe.get("count", 0) or 0) for probe in probes
    )
    probability_probe_count = sum(
        int(probe.get("count", 0) or 0)
        for probe in probes
        if "max_probability_max" in probe and "total_probability_max" in probe
    )
    coherence_probe_count = sum(
        int(probe.get("count", 0) or 0)
        for probe in probes
        if "coherence_min" in probe and "coherence_max" in probe
    )
    entropy_probe_count = sum(
        int(probe.get("count", 0) or 0)
        for probe in probes
        if "entropy_min" in probe and "entropy_max" in probe
    )
    branch_weight_probe_count = sum(
        int(probe.get("count", 0) or 0)
        for probe in probes
        if probe.get("label") in branch_labels
    )
    phase_measurement_count = sum(
        int(measurement.get("count", 0) or 0)
        for measurement in measurements
        if abs(float(measurement.get("phase_max", 0.0) or 0.0)) > 0.0
    )
    debug_measurement_count = sum(
        int(measurement.get("count", 0) or 0)
        for measurement in measurements
        if measurement.get("boundary") == "debug_measure"
    )
    entropy_event_count = sum(
        int(event.get("count", 0) or 0) for event in entropy_events
    )
    fallback_event_count = sum(
        int(event.get("count", 0) or 0) for event in fallback_events
    )
    non_destructive_source_count = (
        state_probe_count + entropy_event_count + fallback_event_count
    )
    required = {
        "probability": probability_probe_count > 0,
        "phase": phase_measurement_count > 0,
        "coherence": coherence_probe_count > 0,
        "branch_weights": branch_weight_probe_count > 0,
        "entropy": entropy_probe_count > 0 or entropy_event_count > 0,
        "fallback": fallback_event_count > 0,
    }

    return {
        "ready": all(required.values()),
        "non_destructive_probe_ready": (
            all(required.values()) and non_destructive_source_count > 0
        ),
        "debug_measurement_requested": debug_measurement_count > 0,
        "state_probe_count": state_probe_count,
        "probability_probe_count": probability_probe_count,
        "phase_measurement_count": phase_measurement_count,
        "coherence_probe_count": coherence_probe_count,
        "branch_weight_probe_count": branch_weight_probe_count,
        "entropy_probe_count": entropy_probe_count,
        "entropy_event_count": entropy_event_count,
        "fallback_event_count": fallback_event_count,
        "debug_measurement_count": debug_measurement_count,
        "non_destructive_source_count": non_destructive_source_count,
        "required": required,
    }


def build_replay_trace_evidence(summary: dict) -> dict:
    measurements = summary.get("measurements", [])
    replayable_measurements = [
        measurement for measurement in measurements
        if int(measurement.get("trace_id_xor", 0) or 0) != 0
    ]
    projectile_replay_measurements = [
        measurement for measurement in replayable_measurements
        if measurement.get("domain") == "projectile"
    ]
    projectile_save_demo_measurements = [
        measurement for measurement in projectile_replay_measurements
        if measurement.get("boundary") == "save_or_demo"
    ]

    def count_kind(kind: str, source: list[dict]) -> int:
        return sum(
            int(measurement.get("count", 0) or 0)
            for measurement in source
            if measurement.get("kind") == kind
        )

    trace_id_xor = 0
    flags_or = 0
    for measurement in projectile_save_demo_measurements:
        trace_id_xor ^= int(measurement.get("trace_id_xor", 0) or 0)
        flags_or |= int(measurement.get("flags_or", 0) or 0)

    projectile_branch_count = count_kind(
        "projectile_branch", projectile_save_demo_measurements)
    projectile_writeback_count = count_kind(
        "projectile_writeback", projectile_save_demo_measurements)
    projectile_collision_oracle_count = count_kind(
        "projectile_collision_oracle", projectile_save_demo_measurements)
    branch_writeback_ready = (
        projectile_branch_count > 0 and projectile_writeback_count > 0
    )
    save_demo_ready = bool(projectile_save_demo_measurements)

    return {
        "ready": branch_writeback_ready and save_demo_ready,
        "branch_writeback_ready": branch_writeback_ready,
        "save_demo_ready": save_demo_ready,
        "measurement_trace_count": sum(
            int(measurement.get("count", 0) or 0)
            for measurement in replayable_measurements
        ),
        "projectile_measurement_trace_count": sum(
            int(measurement.get("count", 0) or 0)
            for measurement in projectile_replay_measurements
        ),
        "projectile_save_demo_measurement_count": sum(
            int(measurement.get("count", 0) or 0)
            for measurement in projectile_save_demo_measurements
        ),
        "projectile_branch_replay_count": projectile_branch_count,
        "projectile_writeback_replay_count": projectile_writeback_count,
        "projectile_collision_oracle_replay_count": (
            projectile_collision_oracle_count
        ),
        "trace_id_xor": trace_id_xor,
        "flags": flags_summary(flags_or, PROJECTILE_FLAGS),
        "flags_or": flags_or,
    }


def build_shareware_encounter_evidence(summary: dict) -> dict:
    probes = summary.get("state_probes", [])
    measurements = summary.get("measurements", [])
    labels = {
        "interference": "shareware_interference_field",
        "decoherence": "shareware_decoherence_field",
        "collapse": "shareware_observation_collapse",
        "material_phase": "shareware_material_phase",
    }
    counts = {
        name: probe_count(probes, label, "material")
        for name, label in labels.items()
    }
    projectile_branch_count = probe_count(
        probes, "projectile_branch_state", "projectile")
    projectile_preimpact_count = probe_count(
        probes, "projectile_preimpact_selection", "projectile")
    projectile_writeback_apply_count = probe_count(
        probes, "projectile_writeback_apply", "projectile")
    projectile_kick_count = probe_count(
        probes, "shareware_projectile_kick", "projectile")
    projectile_probe_groups = {
        "branch": probe_by_label_domain(
            probes, "projectile_branch_state", "projectile"),
        "preimpact": probe_by_label_domain(
            probes, "projectile_preimpact_selection", "projectile"),
        "writeback": probe_by_label_domain(
            probes, "projectile_writeback_apply", "projectile"),
        "kick": probe_by_label_domain(
            probes, "shareware_projectile_kick", "projectile"),
    }
    present_projectile_groups = [
        group for group in projectile_probe_groups.values()
        if group and int(group.get("count", 0) or 0) > 0
    ]
    projectile_subject_maps: dict[str, dict[int, dict]] = {}
    for name, group in projectile_probe_groups.items():
        subjects = {}
        if group:
            for subject_id, subject in dict(
                group.get("subjects") or {}
            ).items():
                subject_int = int(subject_id)
                if subject_int > 0 and int(subject.get("count", 0) or 0) > 0:
                    subjects[subject_int] = subject
        projectile_subject_maps[name] = subjects
    projectile_common_subjects: set[int] = set()
    if len(present_projectile_groups) == len(projectile_probe_groups):
        subject_sets = [
            set(subjects.keys())
            for subjects in projectile_subject_maps.values()
        ]
        if subject_sets:
            projectile_common_subjects = set.intersection(*subject_sets)
    projectile_correlation_subject_id = None
    projectile_overlap_first_frame = 0
    projectile_overlap_last_frame = -1
    projectile_frame_overlap = False
    for subject_id in sorted(projectile_common_subjects):
        subject_groups = [
            projectile_subject_maps[name][subject_id]
            for name in projectile_probe_groups.keys()
        ]
        first_frame = max(
            int(subject.get("first_frame", 0) or 0)
            for subject in subject_groups
        )
        last_frame = min(
            int(subject.get("last_frame", 0) or 0)
            for subject in subject_groups
        )
        if first_frame <= last_frame:
            projectile_correlation_subject_id = subject_id
            projectile_overlap_first_frame = first_frame
            projectile_overlap_last_frame = last_frame
            projectile_frame_overlap = True
            break
    projectile_same_subject = projectile_correlation_subject_id is not None
    projectile_correlation_ready = (
        projectile_branch_count > 0 and
        projectile_preimpact_count > 0 and
        projectile_writeback_apply_count > 0 and
        projectile_kick_count > 0 and
        projectile_same_subject and
        projectile_frame_overlap
    )
    projectile_impact_count = sum(
        int(measurement.get("count", 0) or 0)
        for measurement in measurements
        if measurement.get("domain") == "projectile"
        and measurement.get("kind") == "projectile_impact"
    )
    flags = 0
    max_probability = 0.0
    coherence_min = None
    for probe in probes:
        if probe.get("domain") == "material" and (
            probe.get("label") in labels.values()
        ):
            flags |= int(probe.get("flags_or", 0) or 0)
            if probe.get("label") in (
                "shareware_interference_field",
                "shareware_observation_collapse",
            ):
                max_probability = max(
                    max_probability,
                    float(probe.get("max_probability_max", 0.0) or 0.0),
                )
            value = float(probe.get("coherence_min", 0.0) or 0.0)
            coherence_min = value if coherence_min is None else min(
                coherence_min, value)

    collapse_measurement_count = sum(
        int(measurement.get("count", 0) or 0)
        for measurement in measurements
        if measurement.get("domain") == "material"
        and measurement.get("kind") == "material_phase"
        and measurement.get("boundary") == "player_visible"
        and (
            int(measurement.get("flags_or", 0) or 0) &
            SHAREWARE_ENCOUNTER_FLAGS["active"]
        )
    )
    measurement_trace_xor = 0
    for measurement in measurements:
        if measurement.get("domain") == "material" and (
            measurement.get("kind") == "material_phase"
        ) and (
            int(measurement.get("flags_or", 0) or 0) &
            SHAREWARE_ENCOUNTER_FLAGS["active"]
        ):
            measurement_trace_xor ^= int(
                measurement.get("trace_id_xor", 0) or 0)

    required_flags = (
        SHAREWARE_ENCOUNTER_FLAGS["active"] |
        SHAREWARE_ENCOUNTER_FLAGS["interference"] |
        SHAREWARE_ENCOUNTER_FLAGS["decoherence"] |
        SHAREWARE_ENCOUNTER_FLAGS["observed"] |
        SHAREWARE_ENCOUNTER_FLAGS["material_phase"] |
        SHAREWARE_ENCOUNTER_FLAGS["player_visible"] |
        SHAREWARE_ENCOUNTER_FLAGS["e1m1"] |
        SHAREWARE_ENCOUNTER_FLAGS["render_feedback"]
    )
    required = {
        "interference": counts["interference"] > 0,
        "decoherence": counts["decoherence"] > 0,
        "observation_collapse": counts["collapse"] > 0,
        "material_phase": counts["material_phase"] > 0,
        "player_visible_measurement": collapse_measurement_count > 0,
        "projectile_branch": projectile_branch_count > 0,
        "projectile_preimpact": projectile_preimpact_count > 0,
        "projectile_kick": projectile_kick_count > 0,
        "projectile_correlated": projectile_correlation_ready,
        "projectile_gameplay_outcome": (
            projectile_impact_count > 0 or projectile_writeback_apply_count > 0
        ),
        "required_flags": (flags & required_flags) == required_flags,
    }

    return {
        "ready": all(required.values()),
        "interference_count": counts["interference"],
        "decoherence_count": counts["decoherence"],
        "observation_collapse_count": counts["collapse"],
        "material_phase_count": counts["material_phase"],
        "player_visible_material_phase_measurement_count": (
            collapse_measurement_count
        ),
        "projectile_branch_count": projectile_branch_count,
        "projectile_preimpact_selection_count": projectile_preimpact_count,
        "shareware_projectile_kick_count": projectile_kick_count,
        "projectile_correlation_ready": projectile_correlation_ready,
        "projectile_correlation_subject_id": projectile_correlation_subject_id,
        "projectile_correlation_first_frame": (
            projectile_overlap_first_frame
            if projectile_frame_overlap
            else None
        ),
        "projectile_correlation_last_frame": (
            projectile_overlap_last_frame
            if projectile_frame_overlap
            else None
        ),
        "projectile_correlation": {
            "same_subject": projectile_same_subject,
            "frame_overlap": projectile_frame_overlap,
            "common_subject_ids": sorted(projectile_common_subjects),
            "groups": {
                name: {
                    "count": int(group.get("count", 0) or 0),
                    "subject_id_min": int(group.get(
                        "subject_id_min",
                        group.get("last_subject_id", 0)) or 0),
                    "subject_id_max": int(group.get(
                        "subject_id_max", 0) or 0),
                    "first_frame": int(group.get("first_frame", 0) or 0),
                    "last_frame": int(group.get("last_frame", 0) or 0),
                    "subjects": group.get("subjects") or {},
                }
                for name, group in projectile_probe_groups.items()
                if group
            },
        },
        "projectile_impact_measurement_count": projectile_impact_count,
        "projectile_writeback_apply_count": projectile_writeback_apply_count,
        "selected_probability_max": max_probability,
        "coherence_min": 0.0 if coherence_min is None else coherence_min,
        "measurement_trace_id_xor": measurement_trace_xor,
        "flags": flags_summary(flags, SHAREWARE_ENCOUNTER_FLAGS),
        "flags_or": flags,
        "required": required,
    }


def build_runtime_evidence(summary: dict) -> dict:
    probes = summary.get("state_probes", [])
    records = summary.get("records", {})
    measurements = summary.get("measurements", [])
    weapon_class_counts = {
        str(name): int(count)
        for name, count in (
            summary.get("weapon_class_counts") or {}).items()
    }
    ai_decision_count = sum(
        int(decision.get("count", 0) or 0)
        for decision in summary.get("ai_decisions", [])
    )
    ai_enemy_type_counts: Counter[str] = Counter()
    ai_enemy_class_counts: Counter[str] = Counter()
    for decision in summary.get("ai_decisions", []):
        count = int(decision.get("count", 0) or 0)
        enemy_type = decision.get("enemy_type")
        enemy_class = str(decision.get("enemy_class") or "")
        ai_enemy_type_counts[str(enemy_type)] += count
        if enemy_class.startswith("monster_"):
            ai_enemy_class_counts[enemy_class] += count
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
    projectile_writeback_apply = probe_by_label(
        probes, "projectile_writeback_apply")
    projectile_branch = probe_by_label(probes, "projectile_branch_state")
    projectile_preimpact = probe_by_label(
        probes, "projectile_preimpact_selection")
    material_labels = {
        "water_decoherence": "material_water",
        "lava_phase": "material_lava",
        "slipgate_phase": "material_slipgate",
        "quad_amplification": "material_quad",
        "ring_protection": "material_ring",
        "pentagram_protection": "material_pentagram",
        "rune_phase": "material_rune",
    }
    material_class_labels = {
        "ordinary": "material_class_ordinary",
        "water": "material_class_water",
        "lava": "material_class_lava",
        "slime": "material_class_slime",
        "teleport": "material_class_teleport",
        "sky": "material_class_sky",
        "fullbright": "material_class_fullbright",
        "warp": "material_class_warp",
    }
    weapon_labels = {
        "shotgun_spread_measurement": "weapon_shotgun",
        "nail_pauli_noise": "weapon_nailgun",
        "rocket_splash_wavefront": "weapon_rocket",
        "grenade_fuse_branch": "weapon_grenade",
        "lightning_continuous_measurement": "weapon_lightning",
        "axe_contact_measurement": "weapon_axe",
    }

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
    projectile_writeback_apply_count = probe_count(
        probes, "projectile_writeback_apply", "projectile")
    projectile_branch_count = probe_count(
        probes, "projectile_branch_state", "projectile")
    projectile_preimpact_count = probe_count(
        probes, "projectile_preimpact_selection", "projectile")
    material_counts = {
        name: probe_count(probes, label, "material")
        for name, label in material_labels.items()
    }
    material_class_counts = {
        name: probe_subject_count(probes, label, "material")
        for name, label in material_class_labels.items()
    }
    material_class_counts = {
        name: count for name, count in material_class_counts.items()
        if count > 0
    }
    material_operator_count = sum(material_counts.values())
    weapon_counts = {
        name: probe_count(probes, label, "weapon")
        for name, label in weapon_labels.items()
    }
    weapon_operator_count = sum(weapon_counts.values())
    weapon_operation_measurement_count = sum(
        int(measurement.get("count", 0) or 0)
        for measurement in measurements
        if measurement.get("domain") == "weapon"
        and measurement.get("kind") == "weapon_operation"
    )
    projectile_impact_measurement_count = sum(
        int(measurement.get("count", 0) or 0)
        for measurement in measurements
        if measurement.get("domain") == "projectile"
        and measurement.get("kind") == "projectile_impact"
    )
    projectile_save_demo_measurements = [
        measurement for measurement in measurements
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
    if projectile_writeback_apply:
        projectile_flags |= (
            int(projectile_writeback_apply.get("flags_or", 0) or 0) & ~0xff
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
    material_flags = 0
    for probe in probes:
        if probe.get("domain") == "material" and (
            probe.get("label") in material_labels.values()
        ):
            material_flags |= int(probe.get("flags_or", 0) or 0)
    weapon_flags = 0
    for probe in probes:
        if probe.get("domain") == "weapon" and (
            probe.get("label") in weapon_labels.values()
        ):
            weapon_flags |= int(probe.get("flags_or", 0) or 0)

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
            "enemy_type_counts": dict(sorted(ai_enemy_type_counts.items())),
            "enemy_class_counts": dict(sorted(ai_enemy_class_counts.items())),
            "observed_enemy_class_count": len(ai_enemy_class_counts),
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
        "material": {
            "operator_count": material_operator_count,
            "class_counts": dict(sorted(material_class_counts.items())),
            "observed_class_count": len(material_class_counts),
            "water_decoherence_count": material_counts["water_decoherence"],
            "lava_phase_count": material_counts["lava_phase"],
            "slipgate_phase_count": material_counts["slipgate_phase"],
            "quad_amplification_count": material_counts[
                "quad_amplification"],
            "ring_protection_count": material_counts["ring_protection"],
            "pentagram_protection_count": material_counts[
                "pentagram_protection"],
            "rune_phase_count": material_counts["rune_phase"],
            "flags": flags_summary(material_flags, MATERIAL_FLAGS),
            "flags_or": material_flags,
        },
        "observation_boundaries": build_observation_boundary_evidence(
            measurements
        ),
        "lab_overlay": build_lab_overlay_evidence(summary),
        "replay_trace": build_replay_trace_evidence(summary),
        "shareware_encounter": build_shareware_encounter_evidence(summary),
        "weapon": {
            "ready": all(count > 0 for count in weapon_counts.values()),
            "operator_count": weapon_operator_count,
            "operation_measurement_count": (
                weapon_operation_measurement_count
            ),
            "class_counts": dict(sorted(weapon_class_counts.items())),
            "observed_class_count": len(weapon_class_counts),
            "shotgun_spread_measurement_count": weapon_counts[
                "shotgun_spread_measurement"],
            "nail_pauli_noise_count": weapon_counts["nail_pauli_noise"],
            "rocket_splash_wavefront_count": weapon_counts[
                "rocket_splash_wavefront"],
            "grenade_fuse_branch_count": weapon_counts[
                "grenade_fuse_branch"],
            "lightning_continuous_measurement_count": weapon_counts[
                "lightning_continuous_measurement"],
            "axe_contact_measurement_count": weapon_counts[
                "axe_contact_measurement"],
            "flags": flags_summary(weapon_flags, WEAPON_FLAGS),
            "flags_or": weapon_flags,
        },
        "projectile": {
            "ready": projectile_ready,
            "authority_gate_count": projectile_gate_count,
            "writeback_decision_count": projectile_writeback_count,
            "writeback_apply_count": projectile_writeback_apply_count,
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
    ai_decision_groups: dict[tuple[int, int, str], dict] = {}
    weapon_class_counts: Counter[str] = Counter()
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
                if (domain_name == "weapon" and
                        kind_name == "weapon_operation"):
                    weapon_id = basis_index & 0xffffffff
                    weapon_class = WEAPON_ID_CLASSES.get(weapon_id)
                    if weapon_class:
                        weapon_class_counts[weapon_class] += 1
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
                enemy_class_known = (
                    input_flags & QGE_AI_INPUT_FLAG_ENEMY_CLASS_KNOWN) != 0
                enemy_class = (
                    AI_ENEMY_TYPE_CLASSES.get(enemy_type, f"type_{enemy_type}")
                    if enemy_class_known else f"unclassified_type_{enemy_type}"
                )
                group = increment_group(
                    ai_decision_groups,
                    (enemy_id, enemy_type, action_name),
                    {
                        "enemy_id": enemy_id,
                        "enemy_type": enemy_type,
                        "enemy_class_known": enemy_class_known,
                        "enemy_class": enemy_class,
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
                group["enemy_class_known"] = enemy_class_known
                group["enemy_class"] = enemy_class
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
                    "subject_id_min": subject_id,
                    "last_subject_id": subject_id,
                    "subject_id_max": subject_id,
                    "subjects": {},
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
            group["subject_id_min"] = min(group["subject_id_min"], subject_id)
            group["last_subject_id"] = subject_id
            group["subject_id_max"] = max(group["subject_id_max"], subject_id)
            subject_key = str(subject_id)
            subject_group = group["subjects"].get(subject_key)
            if subject_group is None:
                subject_group = {
                    "count": 0,
                    "first_frame": frame,
                    "last_frame": frame,
                    "flags_or": 0,
                    "state_hash_xor": 0,
                }
                group["subjects"][subject_key] = subject_group
            subject_group["count"] += 1
            subject_group["first_frame"] = min(
                subject_group["first_frame"], frame)
            subject_group["last_frame"] = max(
                subject_group["last_frame"], frame)
            subject_group["flags_or"] |= probe_flags
            subject_group["state_hash_xor"] ^= state_hash

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
        "weapon_class_counts": dict(sorted(weapon_class_counts.items())),
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
            f"class={decision.get('enemy_class', 'unknown')} "
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
