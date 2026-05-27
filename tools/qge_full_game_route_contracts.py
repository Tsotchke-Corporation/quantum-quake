#!/usr/bin/env python3
"""Route contracts for selected QGE capture map sets."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import qge_map_sets  # noqa: E402

ROUTE_CONTRACT_SCHEMA = "qge.full_game_capture_route_contract.v0"
ROUTE_CONTRACT_AUTHORITY_SCHEMA = (
    "qge.full_game_route_contract_authority.v0"
)
SHAREWARE_EPISODE_ONE_MAP_SET = qge_map_sets.SHAREWARE_EPISODE_ONE_MAP_SET
SPECIAL_ROUTE_MAPS = {"end"}
START_HUB_ROUTE_MAPS = {"start"}
DEFERRED_ROUTE_MAPS = SPECIAL_ROUTE_MAPS | START_HUB_ROUTE_MAPS
BASE_AUTHORITY_DOMAINS = [
    "render_quantum_workload",
    "visibility_authority",
    "projectile_authority",
    "audio_source_authority",
    "noesis_route_observation",
]
MATRIX_DOMAIN_BY_AUTHORITY_DOMAIN = {
    "render_quantum_workload": "render_quantum_workload",
    "visibility_authority": "visibility_authority",
    "projectile_authority": "projectile_live_authority",
    "audio_source_authority": "audio_authority",
    "noesis_route_observation": "capture_artifacts",
    "ai_authority": "ai_authority",
    "special_route_evidence": "special_route_evidence",
}


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def route_profile_for_map(map_name: str) -> str:
    if map_name in START_HUB_ROUTE_MAPS:
        return "start_hub_route_authority_smoke"
    if map_name in SPECIAL_ROUTE_MAPS:
        return "special_route_required"
    return "noesis_authority_smoke"


def map_episode_and_slot(map_name: str) -> tuple[str, int | None]:
    if map_name in START_HUB_ROUTE_MAPS:
        return "start_hub", 0
    if map_name in SPECIAL_ROUTE_MAPS:
        return "endgame", None
    if (
        len(map_name) == 4 and
        map_name[0] == "e" and
        map_name[2] == "m" and
        map_name[1].isdigit() and
        map_name[3].isdigit()
    ):
        return f"e{map_name[1]}", int(map_name[3])
    return "unknown", None


def route_contract_for_map(
    map_name: str,
    *,
    map_set: str | None = None,
) -> dict[str, Any]:
    episode, slot = map_episode_and_slot(map_name)
    start_hub_route = map_name in START_HUB_ROUTE_MAPS
    special_route = map_name in SPECIAL_ROUTE_MAPS
    combat_required = not start_hub_route and not special_route
    if start_hub_route:
        map_class = "start_hub"
        route_goal = "start hub route with projectile authority smoke"
    elif special_route:
        map_class = "endgame_special"
        route_goal = "special endgame route evidence required"
    else:
        if map_set == SHAREWARE_EPISODE_ONE_MAP_SET and episode == "e1":
            map_class = "shareware_combat"
            route_goal = (
                f"{episode} shareware map {slot} "
                "route/combat authority smoke"
            )
        else:
            map_class = "registered_combat"
            route_goal = f"{episode} map {slot} route/combat authority smoke"
    authority_domains = list(BASE_AUTHORITY_DOMAINS)
    if combat_required:
        authority_domains.append("ai_authority")
    if special_route:
        authority_domains.append("special_route_evidence")
    return {
        "schema": ROUTE_CONTRACT_SCHEMA,
        "map": map_name,
        "episode": episode,
        "slot": slot,
        "map_class": map_class,
        "route_profile": route_profile_for_map(map_name),
        "route_goal": route_goal,
        "combat_required": combat_required,
        "route_progress_required": True,
        "projectile_authority_required": True,
        "audio_authority_required": True,
        "special_route_required": special_route,
        "start_hub_route": start_hub_route,
        "authority_domains": authority_domains,
    }


def matrix_domain_for_authority_domain(authority_domain: str) -> str:
    return MATRIX_DOMAIN_BY_AUTHORITY_DOMAIN.get(
        authority_domain,
        authority_domain,
    )


def route_contract_authority_audit(
    map_name: str | None,
    moonlab_domain_readiness: dict[str, Any],
    *,
    map_set: str | None = None,
) -> dict[str, Any]:
    if not map_name:
        return {
            "schema": ROUTE_CONTRACT_AUTHORITY_SCHEMA,
            "ready": False,
            "map": None,
            "blockers": ["canonical_map_missing"],
            "domain_checks": [],
        }
    contract = route_contract_for_map(map_name, map_set=map_set)
    domain_checks = []
    blockers = []
    for authority_domain in contract["authority_domains"]:
        matrix_domain = matrix_domain_for_authority_domain(authority_domain)
        matrix_entry = dict_or_empty(moonlab_domain_readiness.get(
            matrix_domain))
        ready = matrix_entry.get("ready") is True
        if not matrix_entry:
            blockers.append(f"{authority_domain}:matrix_domain_missing")
        elif not ready:
            blockers.append(f"{authority_domain}:matrix_domain_not_ready")
        domain_checks.append({
            "authority_domain": authority_domain,
            "matrix_domain": matrix_domain,
            "ready": ready,
            "evidence": dict_or_empty(matrix_entry.get("evidence")),
            "blockers": matrix_entry.get("blockers", []),
        })
    return {
        "schema": ROUTE_CONTRACT_AUTHORITY_SCHEMA,
        "route_contract_schema": ROUTE_CONTRACT_SCHEMA,
        "map": map_name,
        "route_contract": contract,
        "required_authority_domains": contract["authority_domains"],
        "domain_checks": domain_checks,
        "ready": not blockers,
        "blockers": blockers,
    }
