#!/usr/bin/env python3
"""Canonical QGE map-set registry shared by evidence tools."""

from __future__ import annotations

from typing import Any


DEFAULT_FULL_GAME_MAP_SET = "quake_registered_single_player"
SHAREWARE_EPISODE_ONE_MAP_SET = "quake_shareware_episode1"

QUAKE_REGISTERED_SINGLE_PLAYER_MAPS = [
    "start",
    "e1m1",
    "e1m2",
    "e1m3",
    "e1m4",
    "e1m5",
    "e1m6",
    "e1m7",
    "e1m8",
    "e2m1",
    "e2m2",
    "e2m3",
    "e2m4",
    "e2m5",
    "e2m6",
    "e2m7",
    "e3m1",
    "e3m2",
    "e3m3",
    "e3m4",
    "e3m5",
    "e3m6",
    "e3m7",
    "e4m1",
    "e4m2",
    "e4m3",
    "e4m4",
    "e4m5",
    "e4m6",
    "e4m7",
    "e4m8",
    "end",
]

QUAKE_SHAREWARE_EPISODE_ONE_MAPS = [
    "start",
    "e1m1",
    "e1m2",
    "e1m3",
    "e1m4",
    "e1m5",
    "e1m6",
    "e1m7",
    "e1m8",
]

MAP_SETS = {
    DEFAULT_FULL_GAME_MAP_SET: QUAKE_REGISTERED_SINGLE_PLAYER_MAPS,
    SHAREWARE_EPISODE_ONE_MAP_SET: QUAKE_SHAREWARE_EPISODE_ONE_MAPS,
}


def map_targets_for_set(name: str) -> list[str]:
    try:
        return list(MAP_SETS[name])
    except KeyError as exc:
        choices = ", ".join(sorted(MAP_SETS))
        raise ValueError(
            f"unknown QGE map set {name!r}; expected one of: {choices}"
        ) from exc


def is_registered_full_game_map_set(name: Any) -> bool:
    return name == DEFAULT_FULL_GAME_MAP_SET


def is_shareware_episode_one_map_set(name: Any) -> bool:
    return name == SHAREWARE_EPISODE_ONE_MAP_SET


def map_set_scope_label(name: Any) -> str:
    if is_registered_full_game_map_set(name):
        return "registered_single_player_full_game"
    if is_shareware_episode_one_map_set(name):
        return "shareware_episode_one"
    return "custom_map_set"
