# QGE Shareware Complete Effects Sprint

Status: complete for the current shareware release.

This sprint closed the last release-risk gap between map breadth and a
user-playable shareware package. The target is literal Quake shareware Episode
1, not registered/full-game content. A release may claim complete shareware QGE
effects only when the generated inventory, runtime matrix, complete-effects
gate, and release-candidate gate all agree.

## Scope

The map set is exactly `quake_shareware_episode1`:

- `start`
- `e1m1`
- `e1m2`
- `e1m3`
- `e1m4`
- `e1m5`
- `e1m6`
- `e1m7`
- `e1m8`

No registered/full-game maps, assets, or release claims are included.

## Current Evidence

- Complete-effects gate:
  `diagnostics/shareware_effects/20260625-050156/qge_shareware_complete_effects_gate.json`.
- Complete-effects ICC evidence:
  `diagnostics/shareware_effects/20260625-050156/qge_shareware_complete_effects_icc_evidence.json`.
- Current release-candidate gate:
  `diagnostics/publication_pack/20260624-shareware-v8/release/qge_shareware_release_candidate_gate_after_effects.json`.
- Strict shareware breadth evidence:
  `diagnostics/breadth_evidence/shareware_episode1/qge_breadth_icc_evidence.json`.

The complete matrix reports:

- 9/9 shareware maps covered.
- 9/9 runtime enemy classes covered.
- 6 discovered weapon pickup classes covered by runtime weapon/projectile
  evidence.
- 8 runtime material classes covered.
- 9/9 slipgate maps covered.
- 342 matrix-backed footage captures.
- 4,343 sprite-billboard frames.
- 5,292 snapshot-particle frames.
- 4,290 encoded-particle frames.
- 394 quantum particle-spawn frames.
- 2,331 projectile save-demo boundary measurements.

The targeted post-patch captures that closed the remaining BSP material gaps
are:

- `diagnostics/quake_stream/20260625-004306/` (`e1m2`)
- `diagnostics/quake_stream/20260625-004343/` (`e1m3`)
- `diagnostics/quake_stream/20260625-004448/` (`e1m4` plus slime)
- `diagnostics/quake_stream/20260625-004524/` (`e1m6`)
- `diagnostics/quake_stream/20260625-004550/` (`e1m7`)
- `diagnostics/quake_stream/20260625-004618/` (`e1m8`)

The E1M1 Quantum Rules v0 run at
`diagnostics/quake_stream/20260624-202925/` proves projectile gameplay evidence:
shareware projectile kick, branch/collision/writeback correlation, gameplay
authority, replay/save-demo evidence, and honest material scope. That run does
not claim slipgate material phase behavior unless the captured scene contains
matching `SURF_DRAWTELE` surfaces.

## Inventory Basis

The inventory is built from the local shareware `assets/id1/pak0.pak` and BSP
data. It records:

- 9/9 maps inventoried.
- 9 monster classes.
- 6 weapon pickup classes.
- teleport/slipgate surfaces on all nine maps.
- teleport triggers on all nine maps.
- liquids on all nine maps.
- 42,326 BSP surfaces.

Discovered monster classes:

- `monster_army`
- `monster_boss`
- `monster_demon1`
- `monster_dog`
- `monster_knight`
- `monster_ogre`
- `monster_shambler`
- `monster_wizard`
- `monster_zombie`

Discovered weapon pickup classes:

- `weapon_grenadelauncher`
- `weapon_lightning`
- `weapon_nailgun`
- `weapon_rocketlauncher`
- `weapon_supernailgun`
- `weapon_supershotgun`

## Completion Criteria

The sprint is complete because generated ICC evidence now proves all of the
following:

- The target map set is exactly `quake_shareware_episode1`.
- All nine maps are covered without registered/full-game overclaim.
- The effect inventory is built from real shareware PAK/BSP data.
- Discovered enemy, weapon, projectile, material, sprite, particle, pickup,
  audio, HUD, route, and Noesis-relevant classes are either exercised by runtime
  evidence or explicitly scoped out with a reason.
- Slipgate and teleport surfaces are treated honestly: a run may claim
  slipgate material operator evidence only when the captured map/run contains
  matching teleport surfaces.
- Enemy coverage follows discovered shareware monster classnames, not generic
  combat presence.
- Weapon and projectile coverage includes gameplay-authoritative
  branch/writeback/replay evidence.
- World-material coverage includes ordinary BSP surfaces plus liquid, sky,
  fullbright, lightmap, and teleport/slipgate classes where present.
- Release footage comes from real captured frames; interpolated media is never
  evidence for weapon identity, projectile path, or quantum behavior.
- Noesis evidence remains bounded: no learned-player claim and no hidden route
  script claim.

## Implemented Workstreams

### Effect Inventory

Implemented by `tools/qge_shareware_effects_inventory.py`.

Required outputs:

- `diagnostics/shareware_effects/<stamp>/qge_shareware_effects_inventory.json`
- `diagnostics/shareware_effects/<stamp>/qge_shareware_effects_inventory.md`

The inventory records map set, source hashes, per-map entity classnames,
texture/material flags, route-critical triggers, pickups, monster classes,
weapons, sounds, sprites, and special effects.

### Effect Matrix

Implemented by `tools/qge_shareware_effects_matrix.py`.

Required outputs:

- `diagnostics/shareware_effects/<stamp>/qge_shareware_effects_matrix.json`
- `diagnostics/shareware_effects/<stamp>/qge_shareware_effects_icc_evidence.json`

The matrix joins inventory requirements to runtime captures and fails closed
when an inventoried effect has no matching runtime trace, video, audio, or
Noesis evidence.

### Targeted Captures

Targeted captures now cover:

- all nine shareware maps,
- start-hub slipgate/teleport surfaces,
- maps with `SURF_DRAWTELE`,
- water, warp, lava, and slime encounters,
- combat with discovered monster classes,
- weapon and projectile examples,
- particle, sprite, explosion, gib, and pickup scenes,
- source-authority audio scenes,
- HUD/status bar, intermission, and front-end surfaces.

Captures prefer real high-cadence frames over interpolation.

### Complete-Effects Gate

Implemented by `tools/qge_shareware_complete_effects_gate.py`.

Required outputs:

- `diagnostics/shareware_effects/<stamp>/qge_shareware_complete_effects_gate.json`
- `diagnostics/shareware_effects/<stamp>/qge_shareware_complete_effects_gate.md`
- `diagnostics/shareware_effects/<stamp>/qge_shareware_complete_effects_icc_evidence.json`

The gate composes shareware breadth evidence, shareware Moonlab deployment,
Quantum Rules v0, Noesis release evidence, the inventory, the matrix, and
claim-policy guardrails.

## Maintenance Rules

- Do not replace shareware scope with registered/full-game scope.
- Do not treat visual artifacts as quantum behavior.
- Do not use interpolated footage as evidence.
- Do not regress the matrix to a map-only breadth check.
- Re-run ICC after any inventory, matrix, capture, or release-gate change.
