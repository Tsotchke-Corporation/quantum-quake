#!/usr/bin/env python3
"""Recursive no-overclaim audit for Moonlab publication artifacts."""

from __future__ import annotations

from typing import Any


FORBIDDEN_CLAIM_FLAGS = (
    "whole_game_hardware_execution_claimed",
    "hardware_quantum_advantage_claimed",
    "dense_70000_qubit_state_claimed",
)


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def recursive_overclaim_flags(
    source: str,
    value: Any,
    *,
    forbidden: tuple[str, ...] = FORBIDDEN_CLAIM_FLAGS,
) -> list[dict[str, Any]]:
    flags = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_source = f"{source}.{key}" if source else str(key)
            if key in forbidden and child is True:
                flags.append({
                    "source": child_source,
                    "flag": key,
                    "value": True,
                })
            flags.extend(recursive_overclaim_flags(
                child_source,
                child,
                forbidden=forbidden,
            ))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            flags.extend(recursive_overclaim_flags(
                f"{source}[{index}]",
                child,
                forbidden=forbidden,
            ))
    return flags


def overclaim_flags(
    *,
    resource_envelope: dict[str, Any] | None = None,
    asset_requirements: dict[str, Any] | None = None,
    full_game_plan: dict[str, Any] | None = None,
    job_specs: dict[str, Any] | None = None,
    job_results: dict[str, Any] | None = None,
    submission_packet: dict[str, Any] | None = None,
    submission_bundle: dict[str, Any] | None = None,
    hardware_record_template: dict[str, Any] | None = None,
    hardware_submission_scope: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    sources = (
        ("resource_envelope", dict_or_empty(resource_envelope)),
        ("asset_requirements", dict_or_empty(asset_requirements)),
        ("moonlab_full_game_plan", dict_or_empty(full_game_plan)),
        ("moonlab_job_specs", dict_or_empty(job_specs)),
        ("moonlab_job_results", dict_or_empty(job_results)),
        ("moonlab_submission_packet", dict_or_empty(submission_packet)),
        ("moonlab_submission_bundle", dict_or_empty(submission_bundle)),
        (
            "moonlab_hardware_record_template",
            dict_or_empty(hardware_record_template),
        ),
        (
            "moonlab_hardware_submission_scope",
            dict_or_empty(hardware_submission_scope),
        ),
    )
    flags = []
    seen = set()
    for source, data in sources:
        for flag in recursive_overclaim_flags(source, data):
            identity = (flag.get("source"), flag.get("flag"))
            if identity in seen:
                continue
            seen.add(identity)
            flags.append(flag)
    return flags
