# QGE State Of Development

Status date: 2026-05-21.

This document is the operational state snapshot for Quantum Quake. It is meant
to answer what exists now, what has evidence, what remains incomplete, and how
the repository should be handled after branch consolidation.

## Executive Summary

Quantum Quake is currently a QuakeSpasm-based QGE integration lab with live
diagnostic harnesses. The project has working runtime hooks, traces, tests, and
bounded authority experiments, but it is not yet a finished player-facing Quake
distribution.

The target is stronger than "quantum effects in Quake": the entire game should
run under QGE/Moonlab authority. QuakeSpasm can remain as host, compatibility
shell, content loader, and classic reference oracle, but not as hidden
production authority for domains claimed as Moonlab-owned. The ICC task
`qge_vanilla_quake_conformance` tracks this whole-game target; its current top
blocker is the strict vanilla capture matrix proving runtime ownership counters.

The strongest current areas are QGE runtime evidence, traceability, controlled
visibility/projectile/audio paths, repeatable stream diagnostics, and the ICC
control plane around verified changes. The most visible weak areas are still QGE
world rendering fidelity and Noesis general gameplay. Noesis now moves in
no-script harness runs through an engine-side autonomous controller with local
wall, floor, and hazard probes, but it is not learning from experience and
should not be described as a trained Quake player or as having a robust
map-level planner.

The latest verified branch state is:

- `master` is the primary branch locally and remotely.
- Remote `HEAD` resolves to `refs/heads/master`.
- `origin/main` is fast-forwarded to the same commit as `origin/master` for
  compatibility after the historical merge.
- Latest verified runtime baseline is the current QGE world texture-detail
  restore, world-surface blue balance, one-texel bilinear world texture
  smoothing, moderate-minification texture prefilter, alias-skin viewmodel path,
  world fullbright sampling scale, and diagnostic notify cleanup, mirrored to
  both `origin/master` and `origin/main`.
- The active runtime tree is the C/QuakeSpasm/QGE tree, not the older
  JavaScript/WebTransport history.

## Branch And Repository State

- `master` is the primary development branch for Quantum Quake.
- `origin/main` was an unrelated Three.js/WebTransport Quake history. It has
  been merged into `master` for repository ancestry, then fast-forwarded to the
  current `master` commit so both remote branch names resolve to the same QGE
  tree. Remote `HEAD` still points at `origin/master`.
- The active source layout is the C/QuakeSpasm/QGE tree:
  `qge/`, `quake/Quake/`, `deps/moonlab/`, `tools/`, `tests/`, `.icc/`, and
  `docs/`.
- The JavaScript/WebTransport history is useful provenance, but it is not the
  active runtime tree for this project unless deliberately re-imported under a
  non-conflicting directory in a future task.
- Do not delete `origin/main` as part of normal cleanup without an explicit
  destructive-branch-change request; it is harmless as a compatibility pointer
  to the same commit as `master`.

## Recent Verified Baseline

Recent verified slices on `master` establish the current baseline:

- The current QGE viewmodel-lighting slice gives the first-person alias path
  its own bounded brightness, shade gain, shade floor, alias-normal fill
  shaping, lower first-person edge intensity, and a slower viewmodel-only edge
  cadence. Fixed-view evidence at
  `diagnostics/quake_graphics/20260522-164822/metrics.md` compares against the
  `20260522-160233` edge-cadence baseline: `viewmodel` RMSE drops from
  `0.033139` to `0.019361`, viewmodel high-frequency ratio moves from `1.728`
  to `1.007`, and candidate drift remains `0.000000`. Named world-only crops
  remain unchanged. This remains a bounded foreground lighting/detail fix
  rather than a complete weapon-material fix.
- The current QGE display-contrast slice applies bounded luma contrast after
  tone mapping so the fixed-view renderer no longer lifts dark ceiling/floor
  regions while compressing brighter walls and corridors. Fixed-view evidence
  at `diagnostics/quake_graphics/20260522-034256/metrics.md` compares against
  the flat-lightstyle `20260522-031254` QGE baseline: ceiling, side-wall,
  front-wall, center-floor, near-floor, and mid-corridor crop RMSE all improve,
  candidate drift remains `0.000000`, and the broad world crop RMSE increases
  by `+0.003629` because visible texture/edge energy rises and the broad crop
  includes the first-person weapon band. The follow-up crop audit separates the
  signal: `world_upper` improves by `-0.007318` RMSE, while `viewmodel`
  worsens by `+0.034692`.
- The current QGE world texture-detail slice corrects the surface luma floor to
  add only the missing lift and applies `QGE_SURFACE_TEXTURE_DETAIL_RESTORE
  0.28f` after bilinear/prefilter sampling. The restore remains asymmetric:
  dark grooves receive the full bounded detail restore, while highlights are
  scaled down by `QGE_SURFACE_TEXTURE_DETAIL_HIGHLIGHT_SCALE` so the far floor
  does not wash out. Fixed-view evidence at
  `diagnostics/quake_graphics/20260522-024351/metrics.md` keeps QGE ownership
  of world geometry, textures, lightmaps, HUD/console, and the viewmodel; it
  lowers world RMSE from `0.032731` to `0.032623` versus the pushed QGE
  baseline and improves every tracked crop except the mid-corridor, whose delta
  is `+0.000079`.
- The current QGE world-surface blue-balance slice applies
  `QGE_SURFACE_WORLD_BLUE_BALANCE` during BSP surface sampling because the QGE
  fixed-view floor, ceiling, and wall crops were consistently too blue against
  the classic reference. Fixed-view evidence at
  `diagnostics/quake_stream/20260521-183949/frame_001.png` keeps QGE ownership
  of world geometry, textures, lightmaps, HUD/console, and the viewmodel with
  `own_console=1`, `own_viewmodel=1`, `emesh=58`, `ecoeff=27`, and
  `fallback_reason=none` on captured frames. Against the previous
  `20260521-180918` QGE baseline, whole-frame RMSE improves from `0.0341756`
  to `0.0340944`; ceiling blue mean moves from `6.52138%` to `5.71603%`, the
  center far-floor blue mean from `7.68358%` to `6.74801%`, and the front-wall
  blue mean from `7.1062%` to `6.23555%`. Side-wall blue becomes slightly low,
  so this is a conservative color-balance improvement rather than a complete
  material/lighting fix.
- The previous QGE one-texel bilinear world texture slice lowers
  `QGE_TEXTURE_BILINEAR_MIN_FOOTPRINT` to the clamped one-texel footprint so
  wall, ceiling, and floor samples that previously used nearest palette lookup
  enter the bilinear palette path before the stronger minification prefilter is
  needed. Fixed-view evidence at
  `diagnostics/quake_stream/20260521-180918/frame_002.png` keeps QGE ownership
  of world geometry, textures, lightmaps, HUD/console, and the viewmodel with
  `own_console=1`, `own_viewmodel=1`, `emesh=58`, `ecoeff=27`, and
  `fallback_reason=none` on captured frames. Against the previous
  `20260521-174755` QGE baseline, ceiling blur-difference drops from
  `0.00469063` to `0.00234635`, left/right wall drops from
  `0.00347071`/`0.00373587` to `0.00172187`/`0.00203961`, and front-wall drops
  from `0.0027016` to `0.00168355`. Whole-frame RMSE against the classic
  `20260521-151552` reference is mixed across the three-frame capture
  (`0.0341756` on frame 2, `0.0347847` on frames 1/3), so this is recorded as a
  targeted wall/ceiling crawl reduction rather than a complete renderer
  conformance fix.
- The previous QGE moderate-minification texture prefilter slice lowers
  `QGE_TEXTURE_PREFILTER_MIN_FOOTPRINT` so the existing nine-tap world texture
  footprint filter engages on moderately minified floor, wall, and ceiling
  texels while magnified and near one-texel samples stay on the bilinear path.
  Fixed-view evidence at `diagnostics/quake_stream/20260521-174755/frame_001.png`
  keeps QGE ownership of world geometry, textures, lightmaps, HUD/console, and
  the viewmodel with `own_console=1`, `own_viewmodel=1`, `emesh=58`,
  `ecoeff=27`, and `fallback_reason=none` on captured frames. Against the
  classic `20260521-151552` reference, whole-frame RMSE improves from
  `0.0349406` in the alias-skin baseline to `0.0343281`; the mid-floor
  blur-difference metric drops from `0.00841979` to `0.00792546`, and the
  over-broad `1.35f` threshold was rejected because it lost that RMSE gain
  without improving side-wall crops.
- The current QGE alias-skin viewmodel slice projects Quake alias-model skin
  coordinates through the QGE triangle path and bilinear-samples
  `hdr->texels[skin]` for the first-person weapon mesh instead of filling that
  mesh with flat synthetic color. Fixed-view evidence at
  `diagnostics/quake_stream/20260521-173303/frame_001.png` keeps QGE ownership
  of world geometry, textures, lightmaps, HUD/console, and the viewmodel with
  `own_console=1`, `own_viewmodel=1`, `emesh=58`, `ecoeff=27`, and
  `fallback_reason=none` on captured frames. Against the classic
  `20260521-151552` reference, whole-frame RMSE improves from `0.0452656` in
  the fullbright-wall-material baseline to `0.0349406`; fixed-view world crops
  are unchanged apart from the foreground weapon overlap, and the weapon is no
  longer the flat gold placeholder mesh.
- The current QGE world fullbright scale slice raises
  `QGE_SURFACE_FULLBRIGHT_SCALE` to keep true fullbright wall texels closer to
  classic Quake's unlit additive contribution without changing ordinary
  lightmapped texture samples. Fixed-view evidence at
  `diagnostics/quake_stream/20260521-170934/frame_001.png` keeps QGE ownership
  of world geometry, textures, lightmaps, HUD/console, and the viewmodel with
  `own_console=1`, `own_viewmodel=1`, `emesh=58`, `ecoeff=27`, and
  `fallback_reason=none` on captured frames. Against the classic
  `20260521-151552` reference, whole-frame RMSE improves from `0.0457305` in
  the diagnostic-notify-clean capture to `0.0452656`; sampled wall-light crops
  move closer to classic while normal ceiling/front-wall/side-wall crops remain
  unchanged.
- The current diagnostic-notify cleanup keeps QGE render/snapshot milestones in
  stderr-backed logs instead of Quake notify text, so graphics captures no
  longer paint diagnostic strings over the floors, walls, and ceilings being
  inspected. Fixed-view evidence at
  `diagnostics/quake_stream/20260521-164816/frame_001.png` keeps QGE ownership
  of world geometry, textures, lightmaps, HUD/console, and the viewmodel with
  `own_console=1`, `own_viewmodel=1`, `emesh=58`, `ecoeff=27`, and
  `fallback_reason=none` on captured frames. This removes a capture contaminant;
  it does not claim that the underlying world-surface renderer is vanilla
  faithful.
- The current QGE world fullbright sampling slice splits world texture palette
  indices `>=224` into an unlit additive contribution when the texture has a
  fullbright mask, while normal texture indices remain in the lightmapped base
  sample. Activation-only fixed-view evidence at
  `diagnostics/quake_stream/20260521-155209/frame_001.png` keeps QGE ownership
  of world geometry, textures, lightmaps, and the viewmodel with
  `emesh=58`, `ecoeff=27`, `own_viewmodel=1`, and `fallback_reason=none`.
  Region checks against the classic `20260521-151552` reference show the
  sampled wall-light deltas improving from about `-37.42/-28.70` after the
  world-tone slice to about `-19.83/-12.57`, while the normal wall/floor/ceiling
  regions remain effectively unchanged. Light-emissive regions are still dimmer
  than classic, but this fixes the missing unlit fullbright contribution without
  adding a separate fullscreen pass.
- The current world-tone histogram QGE renderer slice keeps the lower
  first-person viewmodel/HUD band out of direct-display tone-map histogram
  selection while still converting the full frame. Activation-only fixed-view
  evidence at `diagnostics/quake_stream/20260521-153315/frame_001.png` keeps QGE
  ownership of world geometry, textures, lightmaps, and the viewmodel with
  `emesh=58`, `ecoeff=27`, `own_viewmodel=1`, and `fallback_reason=none`.
  Region checks against the classic `20260521-151552` reference show the
  previous QGE viewmodel capture's front-wall mean-luminance delta moving from
  about `-19.73` to `-0.92`, side-wall deltas from about `-9.64/-11.01` to
  `+3.08/+2.65`, ceiling delta from about `-11.51` to `+2.19`, and far-floor
  delta from about `-12.88` to `+4.75`. Light-emissive regions remain too dim,
  nearby floors are slightly over-lifted, and raster/material/viewmodel fidelity
  remain open.
- The current tone-headroom QGE renderer slice increases
  `QGE_NO_FLOOR_TONE_WHITE_HEADROOM` to keep preserved-detail world surfaces
  from over-brightening the fixed-view scene. Fixed-view evidence at
  `diagnostics/quake_stream/20260521-143859/frame_001.png` keeps QGE ownership
  of world geometry, textures, lightmaps, and the viewmodel with
  `fallback_reason=none`. Region checks against the classic `20260521-125448`
  reference show ceiling mean-luminance delta improving from about `+9.07` to
  `+2.30`, side-wall deltas from about `+9.79/+9.90` to `+3.83/+3.67`, and
  far-floor delta from about `+7.36` to `+3.70`. Raster seams, turbulent
  material fidelity, residual wall/ceiling brightness, and viewmodel fidelity
  remain open.
- The current viewmodel mesh slice replaced the synthetic first-person weapon
  glyph with bounded alias-model mesh encoding. Activation-only fixed-view
  evidence at `diagnostics/quake_stream/20260521-150734/frame_001.png` reports
  `emesh=58`, `ecoeff=27`, `own_viewmodel=1`, and `fallback_reason=none`.
  The later alias-skin slice samples the original Quake skin texels for that
  mesh, but classic weapon lighting, placement, and material parity remain
  incomplete.
- `b1b7578` makes ordinary QGE world texture sampling use the base Quake
  palette instead of globally boosting high palette indices as fullbright.
  Fixed-view evidence at `diagnostics/quake_stream/20260521-135044/frame_001.png`
  keeps QGE ownership of world textures and lightmaps while moving the far-floor
  luminance and high-frequency texture noise closer to the classic reference.
  Side walls and ceilings remain visibly too bright, so this is a targeted
  floor/noise improvement rather than a renderer-complete claim.
- `656caf4` stabilizes QGE render-gate display gain by deriving the visible
  gain values from deterministic quantum-state marginal probabilities instead
  of finite-shot readout counts. Finite-shot readout and edge counters remain in
  the logs as measurement telemetry, but static floors, walls, and ceilings no
  longer shimmer just because a different shot distribution was sampled on the
  next frame.
- `8c52e0c` makes QGE primary rendering refresh every host frame by default.
  The stream tools default `QGE_RENDER_UPDATE_INTERVAL` to `1`, eliminating the
  previous stale-frame reuse that made floors, walls, ceilings, entities, and
  the viewmodel appear frozen or desynchronized unless the harness overrode the
  interval.
- `d0cfc8e` improves QGE world texture stability by closing narrow
  floor/wall/ceiling coverage gaps and adding bounded palette prefiltering for
  large projected texture footprints. This reduces noisy aliasing on close BSP
  surfaces without claiming vanilla material conformance.
- `a584125` adds targetless local exploration for no-script Noesis autonomous
  control. When no monster target is engaged, the server-side controller probes
  forward/left/right clearance, checks for floor and non-lethal contents ahead,
  then moves, turns, or slides away from wall contacts without using a cached
  route script. This directly addresses the "Noesis sits still" failure mode,
  but it is still reactive local navigation, not learned world planning.
- `76ae4da` improves QGE world render coverage by seeding a far-depth ambient
  world background before rasterization and normalizing raw warp/water texture
  coordinates before palette sampling. The verified live run removed the hard
  black voids seen when classic 3D was suppressed and reduced the wide gray
  warp band to a thinner seam, but floor, wall, ceiling, water, and material
  fidelity still need conformance work.
- `c93dcc9`, `889b25e`, `1c1acc3`, and `c4ec5f0` are the current Noesis combat
  and target-fixation baseline: visible-target arbitration, hidden wall-stall
  gating, hidden-target cooldowns, and reduced hidden-target wall push keep the
  no-script controller from ignoring visible enemies or grinding indefinitely
  into blocked hidden targets.
- `5da523e`, `edad050`, `e0c8e36`, `59c8d0f`, and `53cd998` are earlier
  rendering baseline slices: preserved-detail QGE display, no-floor tone
  mapping, normal-world palette opacity fixes, bilinear surface/lightmap
  sampling, duplicate snapshot clearing, near-plane clipping, FOV-aware world
  projection, non-additive same-depth ownership, lower world-surface ambient
  floors, tighter depth tie windows, and reduced per-face exposure patches.
- The historical `origin/main` history is merged for ancestry and the remote
  `origin/main` branch now matches `origin/master`; `master` remains the primary
  branch and remote `HEAD`.

Useful live evidence anchors:

- `diagnostics/quake_stream/20260521-112111/frame_001.png` plus
  `diagnostics/quake_stream/20260521-112111/quantum_quake.log`: fixed-view QGE
  graphics evidence after `656caf4`. Across 14 render frames, `gate_p`,
  `gate_edge`, `gate_gain`, `edge_gain`, `material_gain`, and `gate_rgb` each
  have one unique value, while `readout_ones` and `edge_ones` still vary. This
  is the current proof that visible render-gate gain is stable without dropping
  finite-shot measurement telemetry.
- `diagnostics/quake_stream/20260521-111059/frame_001.png` plus
  `diagnostics/quake_stream/20260521-111059/quantum_quake.log`: fixed-view QGE
  graphics evidence after `8c52e0c`. The stream used the tool defaults and logs
  `update_interval=1`, `reuse=0`, QGE ownership of world/textures/lightmaps and
  viewmodel after HUD warm-up, and no QGE-render fallback reason.
- `diagnostics/agent_stream/20260521-020917/noesis/qge_noesis_summary.json`:
  no-target `start` map evidence after `a584125`: `noesis_scripted=0`,
  `noesis_autonomous=1`, `target_count=0`, survived with no terminal stall,
  route distance `7005.019`, stationary fraction `0.0035`, 42 leaf transitions,
  movement injected on 280 samples, and view turns on 143 samples. This is the
  current proof that Noesis does not sit still when no route script or monster
  target is available.
- `diagnostics/agent_stream/20260521-021006/noesis/qge_noesis_summary.json`:
  E1M1 no-script evidence after `a584125`: `claim_scope` is
  `server_autonomous`, three kills, `56.0` inferred damage, no damage taken,
  route distance `7962.604`, 82 leaf transitions, no terminal stall, and one
  hidden-chase timeout. This shows the targetless exploration fallback did not
  break the existing E1M1 combat smoke.
- `diagnostics/agent_stream/20260521-013044/noesis/qge_noesis_summary.json`:
  live evidence for `76ae4da`: no-script E1M1 smoke passed with three kills,
  `48.0` inferred damage, no damage taken, no terminal stall, and the graphics
  run showed the black void removed with the broad gray warp band reduced.
- `diagnostics/quake_stream/20260520-191730/frame_001.png` and
  `diagnostics/quake_stream/20260520-193513/frame_001.png`: older blockier QGE
  world captures used as visual comparisons.
- `diagnostics/agent_stream/20260520-212112/noesis/qge_noesis_summary.json`:
  no-script Noesis wall-follow evidence after the autonomous wall-contact
  tuning: `noesis_scripted=0`, action trace line count `0`, three kills,
  `72.0` inferred damage, no damage taken, and no terminal stall. The matching
  frame at `diagnostics/quake_stream/20260520-212112/frame_001.png` still shows
  close-geometry QGE rendering artifacts, so this is a gameplay improvement and
  not a rendering-quality completion claim.
- `diagnostics/quake_stream/20260520-200246/frame_001.png`: improved QGE
  world-rendering capture after the detail, opacity, and near-clip fixes.
- `diagnostics/quake_stream/20260520-202448/frame_001.png`: follow-up no-floor
  tone-map capture that keeps the same preserved-detail path bright enough
  without the median-derived black floor.
- `diagnostics/quake_stream/20260520-215105/frame_001.png`: fixed-view classic
  reference capture used to distinguish real E1M1 brush panels from QGE
  rendering artifacts.
- `diagnostics/quake_stream/20260520-215412/frame_001.png`: fixed-view QGE
  capture after preserved-detail highlight headroom and authoritative-snapshot
  clearing; render logs show `snapshot_surfaces` matching `scene_surfaces`
  instead of the prior doubled snapshot surface count.
- `diagnostics/quake_stream/20260520-232353/frame_001.png`: fixed-view QGE
  capture after FOV-aware projection, darker lightmap-preserving surface
  shading, non-additive depth ties, and tighter depth ownership. The world is
  substantially closer to the classic fixed-view reference, but the remaining
  wall/doorway face panels are still visible and should stay on the rendering
  backlog.
- `diagnostics/quake_stream/20260521-021006/frame_001.png`: current live QGE
  frame from the latest Noesis run. Use it as a practical smoke reference, not
  as a vanilla-conformance claim; visible floor/wall/ceiling artifacts remain.
- `diagnostics/quake_stream/20260521-131825/frame_001.png`: fixed-view QGE
  capture after stronger direct-spatial tone headroom and the stratified
  footprint prefilter. The stable frame reports `fallback_reason=none`,
  `own_world=1`, `own_textures=1`, `own_lightmaps=1`, `own_viewmodel=1`,
  `res=1024`, and `texfilter=110668`. Region checks against the classic
  `20260521-125448` reference show ceiling mean luminance dropping from about
  `47` to `30`, front-wall mean from about `51` to `32`, and side-wall mean
  from about `56` to `36`, moving the QGE frame closer to classic while
  preserving QGE ownership.
- `diagnostics/quake_stream/20260521-135044/frame_001.png`: fixed-view QGE
  capture after removing the global high-palette fullbright boost from ordinary
  world texture sampling. The stable frame reports `fallback_reason=none`,
  `own_world=1`, `own_textures=1`, `own_lightmaps=1`, `own_viewmodel=1`,
  `res=1024`, and `texfilter=110668`. Region checks against the classic
  `20260521-125448` reference show the far-floor mean luminance moving from
  about `37.25` to `32.75` and horizontal high-frequency delta moving from
  about `2.71` to `2.47`, while the run keeps QGE texture and lightmap
  ownership. Side walls and ceilings remain visibly too bright, so this is a
  targeted floor/noise improvement rather than a renderer-complete claim.
- `diagnostics/quake_stream/20260521-153315/frame_001.png`: activation-only QGE
  capture after excluding the lower first-person viewmodel/HUD band from the
  direct-display tone histogram. The stable frame reports `fallback_reason=none`,
  `own_world=1`, `own_textures=1`, `own_lightmaps=1`, `own_viewmodel=1`,
  `emesh=58`, and `ecoeff=27`. Region checks against the classic
  `20260521-151552` reference show walls and ceilings moving from strongly too
  dark to near the classic luma range, while fullbright lamp regions remain too
  dim and nearby floors are slightly over-lifted.
- `diagnostics/quake_stream/20260521-155209/frame_001.png`: activation-only QGE
  capture after splitting fullbright wall texels into an unlit additive sample.
  The stable frame reports `fallback_reason=none`, `own_world=1`,
  `own_textures=1`, `own_lightmaps=1`, `own_viewmodel=1`, `emesh=58`, and
  `ecoeff=27`. Region checks against the classic `20260521-151552` reference
  show wall-light deltas improving from about `-37.42/-28.70` to
  `-19.83/-12.57` while front wall, floors, side walls, and ceiling stay within
  the previous world-tone range.
- `diagnostics/quake_stream/20260521-164816/frame_001.png`: fixed-view QGE
  capture after moving QGE render/snapshot diagnostic milestones out of Quake
  notify text and into stderr-backed logs. The captured frames keep
  `fallback_reason=none`, `own_world=1`, `own_textures=1`, `own_lightmaps=1`,
  `own_viewmodel=1`, `own_console=1`, `emesh=58`, and `ecoeff=27`. This is a
  capture-cleanliness fix for inspecting floors, walls, and ceilings; residual
  texture, seam, material, and tone-map artifacts remain open.
- `diagnostics/quake_stream/20260521-170934/frame_001.png`: fixed-view QGE
  capture after increasing the bounded fullbright wall-texel additive scale.
  The captured frames keep `fallback_reason=none`, `own_world=1`,
  `own_textures=1`, `own_lightmaps=1`, `own_viewmodel=1`, `own_console=1`,
  `emesh=58`, and `ecoeff=27`. ImageMagick checks against the classic
  `20260521-151552` reference show whole-frame RMSE improving from `0.0457305`
  to `0.0452656`; sampled wall-light crops move closer to classic while normal
  ceiling/front-wall/side-wall crops stay unchanged.
- `diagnostics/quake_stream/20260521-173303/frame_001.png`: fixed-view QGE
  capture after sampling alias-model skin texels for the first-person weapon
  mesh. The captured frames keep `fallback_reason=none`, `own_world=1`,
  `own_textures=1`, `own_lightmaps=1`, `own_viewmodel=1`, `own_console=1`,
  `emesh=58`, and `ecoeff=27`. ImageMagick checks against the classic
  `20260521-151552` reference show whole-frame RMSE improving from `0.0452656`
  in the previous fullbright-wall-material capture to `0.0349406`; fixed-view
  world crops are unchanged apart from foreground weapon overlap, and the
  first-person weapon is no longer the flat gold mesh.
- `diagnostics/quake_stream/20260521-174755/frame_001.png`: fixed-view QGE
  capture after engaging the existing nine-tap footprint prefilter on moderately
  minified world texels. The captured frames keep `fallback_reason=none`,
  `own_world=1`, `own_textures=1`, `own_lightmaps=1`, `own_viewmodel=1`,
  `own_console=1`, `emesh=58`, and `ecoeff=27`, with `texfilter` around
  `193k` samples. ImageMagick checks against the classic `20260521-151552`
  reference show whole-frame RMSE improving from `0.0349406` to `0.0343281`,
  while the mid-floor blur-difference metric drops from `0.00841979` to
  `0.00792546`.
- `diagnostics/quake_stream/20260521-183949/frame_001.png`: fixed-view QGE
  capture after applying the bounded world-surface blue balance. The captured
  frames keep `fallback_reason=none`, `own_world=1`, `own_textures=1`,
  `own_lightmaps=1`, `own_viewmodel=1`, `own_console=1`, `emesh=58`, and
  `ecoeff=27`. ImageMagick checks against the classic `20260521-151552`
  reference show whole-frame RMSE improving from `0.0341756` to `0.0340944`
  relative to the previous one-texel bilinear frame, while blue-heavy floor,
  ceiling, and front-wall crops move closer to classic.
- `diagnostics/quake_stream/20260521-190448/frame_001.png`: fixed-view QGE
  capture after applying bounded world texture-detail restoration. The captured
  frames keep `fallback_reason=none`, `own_world=1`, `own_textures=1`,
  `own_lightmaps=1`, `own_viewmodel=1`, `own_console=1`, `emesh=58`, and
  `ecoeff=27`. Region checks against the classic `20260521-151552` reference
  show whole-frame RMSE improving from `0.0340944` to `0.0339437` relative to
  the world-surface blue-balance frame, while world high-frequency texture
  energy rises from `88.8%` to `92.8%` of the classic reference.

The ICC control plane is part of the baseline. Verified slices should refresh
index, memory, git history, source-drift, production-audit, task-attempt, and
attempt-eval artifacts before push.

## Domain Ownership Matrix

| Domain | Current State | Authority Posture | Main Gap |
|---|---|---|---|
| Core runtime and trace | Working test-backed QGE runtime, event spine, and binary traces | Evidence and shadow ownership | Public API boundary and trace v2 coverage |
| Rendering | QGE primary path renders live captures with telemetry | Diagnostic primary render, classic remains visual reference | Vanilla-quality floors, walls, ceilings, sky, water, particles, and seams |
| Visibility | Shadow/parity telemetry and controlled authority smoke | Bounded audited writeback only | Map breadth, dynamic cases, and user-visible quantum modes |
| Projectiles/physics | Shadow state, branch state, writeback gates, collision oracle | Controlled authority gates | Full gameplay authority and quantum-native effects |
| Audio | Post-mix and source-mode telemetry with smoke evidence | Diagnostic/source authority experiments | Complete source authority and player-facing effects |
| AI/Noesis | No-script autonomous controller, target arbitration, wall/floor/hazard probes, hidden-target cooldowns, and opt-in scripted fixtures | Harness-only autonomous assist, not learning | Map-level planning, learned policy updates, general play, and robust navigation |
| Documentation/claims | Claims ledger, state doc, architecture docs, ICC attempts | Evidence-gated wording | Keeping docs synchronized after each verified slice |

## Implemented Runtime Surfaces

### QGE Core

Implemented:

- `qge_quantum_runtime_t` event spine with binary trace output.
- World registry and immutable frame snapshot structures for stable runtime
  references.
- Moonlab-backed RNG, AI, rendering, visibility, audio, physics, and trace
  modules.
- Native sparse IDWT bridge evidence and CPU fallback accounting.
- Test coverage through `tests/test_qge.c` and shell/Python contract tests.

Partial or pending:

- Stable trace v2 records for every sidecar-only diagnostic.
- Public API boundaries for QGE as an engine independent of Quantum Quake.
- More explicit ownership/fallback contracts for every domain transition.

### Rendering

Implemented:

- Sparse DWT framebuffer path for QGE primary rendering.
- Texture and lightmap signal caches.
- BSP surface projection, triangle raster, material/light encoding, viewmodel
  and entity coefficient paths.
- The first-person viewmodel uses alias-model mesh encoding with a larger
  bounded triangle budget instead of the previous synthetic center-line glyph
  when alias mesh metadata is available, and the QGE alias path projects
  alias-model skin texels so the weapon mesh samples the original Quake skin
  instead of a flat diagnostic color.
- Surface-budget telemetry and default scene surface budget increased to 512
  after fixed-view `e1m1` diagnostics showed the old 128 limit dropped visible
  floor/wall/ceiling surfaces.
- QGE primary rendering updates every host frame by default. Stream tools
  default `QGE_RENDER_UPDATE_INTERVAL` to `1`, and the latest fixed-view
  evidence reports `reuse=0`, so renderer-owned world geometry and viewmodel
  output do not freeze behind the live camera.
- Detail-preserving QGE render output: the full RGB raster is kept while sparse
  DWT coefficients are encoded, then used as the default final display signal so
  floor/wall/ceiling detail is not dominated by sparse-block reconstruction.
- Full preserved-detail display uses a no-floor tone map with highlight
  headroom, so ordinary dark texture samples are not converted into black holes
  and bright floors/ceilings do not wash out as quickly while the scene still
  gets the brightness lift needed for live capture.
- When the first-person viewmodel is present, direct-display tone mapping builds
  its histogram from the upper `QGE_TONE_HISTOGRAM_WORLD_Y_PERCENT` percent of
  the frame. The full frame still displays, but the lower weapon/HUD band no
  longer forces the world white point to leave floors, walls, and ceilings too
  dark.
- Bilinear texture and lightmap sampling is enabled by default for QGE primary
  captures; the nearest-sample path remains available for faster diagnostics.
- Normal floor, wall, and ceiling textures no longer inherit the global
  transparent palette rule. Palette alpha is now reserved for fence/transparent
  world surfaces so ordinary world texels do not punch dark holes through the
  raster.
- Sub-pixel projected BSP surfaces now stay in the owned projected-polygon path
  and use the existing QGE micro-fill encoder instead of being counted as
  polygon surrogates. The `e1m2` capture at
  `diagnostics/quake_graphics/20260522-231423` verifies zero fallback,
  zero surrogate surfaces, native IDWT, and Moonlab authority readiness.
- World textures with fullbright masks now split palette indices
  `>=QGE_SURFACE_FULLBRIGHT_INDEX` out of the lightmapped base color and add
  them back through `QGE_SURFACE_FULLBRIGHT_SCALE`, matching classic Quake's
  additive fullbright behavior more closely without changing ordinary texture
  sampling.
- Audited visibility-authority rendering now clears the earlier classic PVS
  visible-surface snapshot before recording the authoritative surface set, so
  QGE does not double-rasterize world panels as ghosted rectangles.
- QGE world-surface projection now clips at `QGE_SURFACE_NEAR_CLIP_DEPTH`
  instead of one unit from the camera, reducing giant over-projected wall and
  ceiling strips when the autonomous player is very close to level geometry.
- QGE world-surface projection now uses Quake's horizontal and vertical FOV
  separately, and world shading uses lower texture/light ambient floors with
  wider tone headroom so floors, walls, and ceilings keep more lightmap
  contrast instead of washing into bright BSP panels.
- The direct-spatial no-floor tone path now uses a higher
  `QGE_NO_FLOOR_TONE_WHITE_HEADROOM`, reducing fixed-view over-bright ceiling,
  side-wall, and floor regions while preserving the no-median-floor display
  path.
- The direct-display tone histogram excludes the lower viewmodel/HUD band when a
  viewmodel is encoded, which brings wall and ceiling brightness much closer to
  the classic fixed-view reference without changing the displayed frame.
- QGE polygon raster fill now uses a near-uniform world gain instead of
  multiplying every texel on a BSP face by that face's coarse brightness score.
  Texture and lightmap samples still provide local shading, but adjacent floor,
  wall, and ceiling faces are less likely to appear as rectangular exposure
  blocks.
- Same-depth world samples use whole-sample luma ownership with a tight
  `QGE_SPATIAL_DEPTH_EPSILON`, which reduces seam brightening and avoids
  synthetic per-channel color combinations without treating nearby distinct
  faces as the same surface.
- QGE spatial rendering now seeds a far-depth ambient world background before
  world rasterization. Pixels not covered by the current visible surface set no
  longer collapse into hard black voids when the classic 3D fallback is
  suppressed for QGE diagnostics.
- Warp and water world surfaces normalize Quake raw `SURF_DRAWTURB` texture
  coordinates before palette sampling, reducing broad flat gray bands in water
  and adjacent world captures. Thin seams and incomplete turbulent-material
  fidelity remain.
- Texture footprint prefiltering now starts at moderate minification. Magnified
  and near one-texel floors, walls, and ceilings stay on bilinear sampling so
  nearby surfaces do not smear into broad bands, while moderate and distant
  texture crawl use bounded palette filters.
- One-texel world texture samples now enter the bilinear palette path when
  bilinear sampling is enabled. Truly magnified samples below that footprint can
  still use nearest lookup, while distance and slanted surfaces keep the bounded
  bilinear/minification handling.
- QGE world texture sampling now uses the base Quake palette for ordinary
  palette indices instead of globally boosting indices `>=224` as fullbright.
  Fullbright texture metadata remains tracked separately, avoiding noisy
  emissive speckles on normal floors, walls, and ceilings.
- On surfaces that actually have a fullbright texture, QGE now samples those
  high palette indices as an unlit additive contribution instead of multiplying
  them only by the lightmap.
- Render-gate visible display gain now uses deterministic state marginals
  rather than finite-shot readout counts. The stochastic counters are still
  logged, but static floors, walls, and ceilings do not pick up frame-to-frame
  brightness or color shimmer from measurement shot noise.
- Render logs report surface counts, snapshot misses, ownership fields, native
  IDWT counts, fallback reasons, and timing splits.

Known current visual state:

- The most recent coverage work fixes large missing-world holes in fixed-view
  captures.
- The most recent default-update work fixes stale-frame reuse in the stream
  harness, so QGE-owned floors, walls, ceilings, entities, and the viewmodel
  move with the camera by default instead of only refreshing every eighth host
  frame.
- The most recent render-gate work fixes one class of static-scene shimmer:
  finite-shot readout counts still vary in telemetry, but the visible display
  gain is stable for an unchanged camera.
- The most recent tone-histogram work fixes the post-viewmodel dark-world
  regression by selecting the world white point from the upper scene area. It
  does not fix seams, turbulent surfaces, fullbright material fidelity, or full
  classic weapon rendering parity.
- The most recent fullbright sampling work restores and scales a bounded unlit
  additive contribution for true fullbright wall texels. The sampled lamp strips
  are closer to classic but still dim, so this is not a complete
  material-fidelity fix.
- The most recent world-texture prefilter work engages the nine-tap footprint
  filter at moderate minification (`QGE_TEXTURE_PREFILTER_MIN_FOOTPRINT 1.75f`),
  improving the fixed-view RMSE to `0.0343281` and reducing mid-floor texture
  crawl without accepting the blurrier rejected `1.35f` threshold.
- The most recent one-texel bilinear work engages bilinear palette sampling at
  the clamped one-texel footprint (`QGE_TEXTURE_BILINEAR_MIN_FOOTPRINT 1.00f`).
  It cuts measured side-wall, front-wall, and ceiling high-frequency crawl in
  the fixed-view capture, but whole-frame RMSE remains mixed because weapon and
  world conformance are still not complete.
- The earlier texture-detail work applies
  `QGE_SURFACE_TEXTURE_DETAIL_RESTORE 0.16f` with asymmetric highlight scaling
  to recover some floor, wall, and ceiling texture energy after
  bilinear/prefilter sampling. It improves fixed-view RMSE to `0.0339437` and
  raises world high-frequency texture energy from `88.8%` to `92.8%` of the
  classic reference.
- The recent world-surface blue-balance work applies
  `QGE_SURFACE_WORLD_BLUE_BALANCE 0.88f`, improving the fixed-view RMSE to
  `0.0340944` and pulling floor, ceiling, and front-wall blue means closer to
  classic. Side-wall blue is now slightly low, so this remains a bounded
  color-balance fix rather than full material fidelity.
- The earlier tone-headroom work reduces fixed-view over-bright ceiling,
  side-wall, and far-floor deltas against the classic reference.
- The recent viewmodel work samples Quake alias-model skin texels for the
  first-person weapon mesh (`emesh=58` and RMSE `0.0349406` in the
  `20260521-173303` capture) instead of the old flat-color QGE mesh. The latest
  viewmodel-lighting passes lower first-person alias brightness and shade floor,
  shape fill from alias `lightnormalindex`, and reduce first-person edge
  intensity/cadence, but classic placement and material parity remain open.
- Floors, walls, and ceilings still need conformance work: raster seams,
  warped/noisy surfaces, gray/turbulent seams, and incomplete vanilla-material
  fidelity remain. Default bilinear sampling, preserved-detail
  highlight headroom, flattened raster fill, duplicate-snapshot clearing,
  ambient world background fill, warp coordinate normalization, every-frame
  refresh, deterministic render-gate display gain, direct-spatial tone headroom,
  viewmodel-aware tone histogram selection, fullbright texture splitting,
  alias-skin viewmodel sampling, one-texel bilinear sampling,
  moderate-minification prefiltering, and
  stratified footprint filtering reduce sparse DWT block bands, tone-floor
  artifacts, exposure panels, ghost panels, black voids, broad water bands,
  stale-frame artifacts, shot-noise shimmer, and over-bright world surfaces, but
  they do not make the QGE renderer visually complete.
- This means the current QGE graphics path is useful for diagnostics and
  iterative comparison, but it should still be called visibly glitchy for
  player-facing floor, wall, and ceiling fidelity.
- `QGE_RENDER_BILINEAR_SAMPLES=0` and `QGE_RENDER_DETAIL_MIX=0` remain useful
  for isolating raw sparse DWT and nearest-sample behavior during diagnostics.
- `QGE_RENDER_DISPLAY_FILTER=1` can smooth noisy captures, but it is not the
  default because recent live captures showed whole-frame blur.
- Edge sampling was rejected as a default because it produced blurred/line
  artifacts and much higher frame cost.
- `tools/qge_world_frame_metrics.py` now provides dependency-free fixed-region
  PNG metrics for renderer triage. It emits `qge.world_frame_metrics.v0`
  evidence for single frames and `qge.world_frame_metrics.frames.v0` evidence
  for averaged frame directories, temporal drift, or baseline-candidate deltas
  over world, upper-playfield, ceiling, side-wall, front-wall, floor, corridor,
  and viewmodel crops. The paired graphics harness falls back to it when
  numpy/Pillow are not available and defaults to flat lightstyles for
  fixed-view renderer comparisons.
- `tools/qge_breadth_evidence.py --min-maps` now enforces distinct-map breadth
  in addition to strict ownership counters. The current strongest breadth pack
  is `diagnostics/breadth_evidence/20260523-152522`, covering nine ready
  matrices across `start` and `e1m1` through `e1m8` with zero fallback, zero
  surrogate, zero CPU-IDWT, 945 native bridge events, 27 parsed backend-gate
  events, and 36 native backend runtime-probe events across
  `qge_context_get_or_create_render_acceleration`, `qge_dwt_render`, and
  `qge_metal_init_common`. Runtime performance, vanilla matrix, breadth, and
  publication artifacts now carry per-target `runtime_backend_probe_proofs`,
  resolved/missing/native target sets, and
  `resource/qge_native_backend_boundary.json` so native backend evidence is
  auditable by boundary instead of only as aggregate counts. The same breadth
  sidecar now emits `qge.full_game_map_coverage.v0` full-game map coverage:
  the canonical registered single-player ledger is 9/32 covered, 23 missing,
  status `partial`. `tools/qge_full_game_capture_queue.py` turns that ledger
  into `qge.full_game_capture_queue.v0` and a runnable
  `run_missing_maps.sh`; it now inventories local loose/Pak BSP assets before
  queuing. Against the current publication pack and current `assets/id1/pak0.pak`,
  zero locally queueable missing maps remain and 23 registered maps are reported
  as asset-unavailable until additional registered BSP assets are installed; the
  queue status is explicitly `blocked_asset_unavailable`, not complete.
  `tools/qge_asset_inventory.py` now emits the hash-backed
  `qge.asset_inventory.v0` audit independently of queue generation and rejects
  placeholder BSPs that fail the Quake BSP29 header/lump gate; the current local
  inventory has one valid `pak0.pak`, 9/32 canonical maps available, 23 missing,
  zero invalid BSP entries, and no whole-game Moonlab coverage claim.
  `tools/qge_registered_asset_intake.py` now scans external registered Quake
  install roots, PAKs, or loose BSPs and emits `qge.registered_asset_intake.v0`
  plus an optional non-destructive copy script. Direct install-root candidates
  now derive nested `id1` and `rerelease/id1` scan targets and record the exact
  scan-target ledger. Missing-after-plan counts are now based on actionable
  copy-plan entries, with blocked destinations reported separately, so invalid
  existing BSP paths cannot make a candidate look installed. It can also run
  bounded local discovery with `--discover-root` or `--discover-common`, making
  the 23 missing-map asset blocker operational without checking game payloads
  into the repo. Publication packs now carry the intake ledger and safe install
  script as first-class resource artifacts; that script verifies copied SHA-256s,
  marks no-candidate plans as `no_op_blocked`, emits
  `QGE_REGISTERED_ASSET_NO_CANDIDATES`, and still prints the post-install
  full-game capture queue command for the same pack. The Moonlab deployment
  gate now repeats those remediation artifacts plus the manual-asset blocker
  reason in its summary, next actions, Markdown, and ICC evidence.
- The post-install full-game capture queue now emits per-map route contracts for
  all 32 canonical registered maps. Queued jobs record route class, episode/slot,
  route profile, combat/special-route requirements, and authority domains, and
  the generated script prints route profile/class markers before each harness
  run. The Moonlab full-game deployment plan repeats that route-contract ledger,
  and the deployment gate requires it to be complete before the whole-game
  simulator/native deployment claim can become ready. Breadth evidence now also
  audits each covered matrix against that map's route-contract authority
  domains, and the gate requires covered route authority to be complete. This
  keeps the post-asset capture path explicit instead of a generic one-profile
  queue.
- `tools/qge_publication_pack.py --breadth-evidence` now carries that multi-map
  breadth evidence into the paper/demo bundle. The current strongest
  publication pack is `diagnostics/publication_pack/20260525-route-authority-gate`, with
  `qge_publication_artifact_pack_complete`, the e1m1 ready vanilla/QGE capture,
  vanilla ICC evidence sidecar, agent stream, oracle/claims exports, QAE
  benchmark artifacts, `resource/qge_resource_envelope.json`,
  `resource/qge_full_game_map_coverage.json`,
  `resource/qge_asset_inventory.json`,
  `resource/qge_asset_requirements.json`,
  `resource/qge_moonlab_full_game_plan.json`,
  `resource/qge_native_backend_boundary.json`,
  `resource/qge_moonlab_job_specs.json`,
  `resource/qge_moonlab_job_results.json`,
  `resource/qge_moonlab_replay_plan.json`,
  `resource/qge_moonlab_submission_packet.json`,
  `resource/qge_moonlab_submission_bundle.json`,
  `resource/qge_moonlab_hardware_record_template.json`,
  `resource/qge_moonlab_hardware_submission_scope.json`,
  `resource/qge_moonlab_deployment_gate.json`, and the nine-map breadth
  counters plus per-target native backend proof maps. The full-game plan joins
  coverage and asset inventory into one deployment ledger; current status is
  `blocked_asset_unavailable`, with 9/32 maps covered, zero capture-required
  maps queueable with local assets, and 23 registered BSP assets unavailable.
  It also joins the registered-asset intake handoff into each deployment row,
  so unavailable maps record whether they have an actionable copy plan, a
  blocked copy destination, or a remaining manual licensed-asset requirement.
  The deployment gate now audits that handoff for presence and consistency with
  the intake remediation ledger, audits the plan's per-map deployment rows
  against current coverage, asset inventory, and canonical route contracts, and
  separately audits the Moonlab `full_game_map_coverage` job result against
  current coverage, inventory, and asset-requirements artifacts. It also scans
  the packed Moonlab evidence recursively for nested hardware execution,
  hardware advantage, or dense-state overclaim flags, and compares every
  selected Moonlab job spec with the job-result ledger, so aggregate success
  counts are not enough unless each selected job has a matching completed
  simulator result row and artifact evidence for its required artifact names.
  It also audits the hardware submission packet against those same specs and
  results, so stale or count-only candidate handoff rows cannot satisfy the
  gate, then checks the hardware record template against that packet so the
  eventual returned Moonlab record targets the same bounded candidate. The
  scoped hardware-submission readiness artifact is also checked against the
  packet, submission bundle, and template before it can support a bounded
  handoff claim. If a returned Moonlab hardware backend row appears in the job
  results, the gate audits that row against the same bounded packet/scope
  before accepting the ledger. The Moonlab source ICC sidecars are also
  recomputed from their source ledgers before the gate accepts the publication
  sidecar evidence, and resource ICC sidecars are recomputed from the asset
  inventory, asset requirements, and registered-asset intake ledgers.
  Advantage/control-plane ICC sidecars are recomputed from the advantage metrics
  plus Moonlab payload, kernel, observation, and Grover schedule artifacts.
  The resource envelope and native backend boundary ledgers are rebuilt from
  the oracle, advantage, vanilla, performance, and breadth evidence before the
  gate accepts their simulator/native posture. The top-level publication ICC
  sidecar is audited against `publication_manifest.json` after pack generation,
  and the copied vanilla, breadth, and performance ICC sidecars are audited
  against their runtime source artifacts. The scene-oracle ICC sidecar is
  audited against the packed oracle and claims evidence, and the oracle claims
  evidence is rebuilt from the packed claims ledger plus oracle scene. The
  oracle scene is rebuilt from its recorded source capture. The publication
  manifest's file and directory records are checked against current path
  existence, sizes, and SHA-256 digests, and its runtime/advantage summary
  mirrors are rebuilt from the recorded source inputs plus packed resource and
  advantage artifacts. The recorded source inputs are checked against copied
  artifact `source_path` provenance, and the manifest claim posture is checked
  against the blocked deployment-gate claim flags. The manifest reproduction
  command list is checked for core command coverage and unsafe shell fragments,
  and the registered-asset install script is rebuilt from the packed intake
  ledger. Packed Markdown evidence reports are regenerated from their source
  JSON ledgers before they are treated as current.
  The deployment gate turns that ledger into the hard claim verdict:
  `blocked`, with whole-game Moonlab simulator/native deployment, whole-game
  hardware execution, hardware advantage, and dense 70,000-qubit state claims
  all disallowed.
  The asset requirements packet enumerates those missing `maps/*.bsp` entries
  separately from the no-claim deployment ledger.
  The job results complete
  four simulator jobs total: the three simulator/native evidence jobs plus the
  coverage-ledger replay, with two native replay jobs, zero blocked jobs, zero
  hardware submissions, and runtime-backend-probe observations copied from the
  performance and breadth aggregates so the job result records native target
  sets, missing target sets, proof maps, event counts, nine resolved breadth
  runs, and 945 native bridge events; `tools/qge_moonlab_job_runner.py`
  regenerates that
  result evidence directly from the job-spec artifact, can compare it to the
  packed expected results, and can emit the replay plan plus the
  hardware-candidate submission packet. `tools/qge_moonlab_qae_transpile.py`
  now emits `advantage/qae_moonlab_payload.json` plus four
  `# moonlab-circuit v1` observation circuits for the MLAE readout schedule.
  `tools/qge_moonlab_oracle_transpile.py` now emits
  `advantage/qae_moonlab_oracle_kernel.moonlab`, a 32-qubit, 7,415-gate
  supported-gate reversible `Q_f` predicate kernel for the captured
  Bernoulli-lift oracle. `tools/qge_moonlab_qae_observation_transpile.py` now
  emits `advantage/qae_moonlab_observation_zero.moonlab`, a 32-qubit,
  7,740-gate power-zero observation circuit with exact 234-candidate state
  preparation, uniform threshold preparation, and inline `Q_f`.
  `tools/qge_moonlab_qae_grover_plan.py` now writes the exact selected MLAE
  Grover schedule body files: powers 0, 1, 2, and 4 all fit, with power 4 at
  610,599 bytes under the 4 MB control-plane cap.
  `tools/qge_moonlab_submission_bundle.py` verifies those payloads while
  keeping the current QAE candidate at
  `ready_for_control_plane_submission`: readout, `Q_f`, power-zero, and
  selected Grover schedule circuits are executable Moonlab control-plane text.
  `tools/qge_moonlab_hardware_ingest.py`
  is the guarded return path for a real Moonlab hardware record: it can generate
  the no-claim hardware record template from the submission packet, then
  requires backend ID, run ID, schedule ID, matching scheduled/completed/observed
  shot counts, readout metadata, finite observations, and matching candidate
  digest before writing a bounded hardware comparison. The resource artifacts
  explicitly avoid whole-game hardware execution, hardware advantage, and
  dense-state claims. The bundled agent stream includes host launcher probes for
  the macOS AppKit/SDL bootstrap and marks `-nolauncher` UI-only launcher paths
  as intentional skips.
- The current renderer should be described as improved, not fixed. In the
  latest fixed-view capture the world projection, contrast, and brightness are
  much closer to classic Quake, but floors, walls, and ceilings still do not
  match vanilla Quake fidelity.

Next rendering priorities:

- Compare default detail-preserving output against raw sparse DWT captures in a
  stable visual regression set.
- Separate projection/raster bugs from DWT/tone-map artifacts using paired
  classic/QGE captures.
- Add focused tests for surface coverage, seam stability, and texture sampling
  behavior.
- Extend the paired capture scoring from fixed `e1m1` crops into a small visual
  regression set with multiple viewpoints and explicit pass/fail thresholds.

### Visibility

Implemented:

- QGE visibility shadow/parity telemetry.
- Conservative authority readiness gates.
- Audited visibility mask application path for controlled authority smokes.
- Trace summary evidence for visibility gate and authority-apply counts.

Partial or pending:

- Broader parity across maps, water/sky/warp cases, and dynamic occlusion.
- Clear player-visible quantum visibility modes beyond conformance telemetry.

### Physics And Projectiles

Implemented:

- Projectile shadow telemetry, readiness gates, branch state, writeback
  decisions, and collision-oracle evidence.
- Persistence-boundary trace hashes for save/demo/replay transitions.
- Explicit `quantum_physics_authoritative` gate.

Partial or pending:

- Full gameplay authority beyond controlled projectile cases.
- Quantum-native projectile effects that are both playable and traceable.

### Audio

Implemented:

- Post-mix QGE audio processing.
- Source-mode quantum audio telemetry and source authority smoke evidence.
- Audio byte/metadata mirroring in agent streams.

Partial or pending:

- Complete per-source authority and material/visibility-conditioned source
  behavior.
- Player-facing quantum audio signatures beyond diagnostics.

### AI And Noesis Gameplay

Implemented:

- Typed QGE AI decision traces and replay metadata.
- Noesis no-script harness mode by default, with opt-in scripted player
  fixtures through `tools/noesis_quake_policy.sh` and
  `tools/noesis_quake_player.sh`.
- Engine-side autonomous assist hint for no-script Noesis runs.
- Engine-side Noesis gameplay outcome telemetry.
- Noesis summary reducer with route/combat/ammo/assist scoring.
- Assist telemetry for target visibility, target locks, target switches, aim
  alignment, movement injection, attack injection, and fire suppression.
- Hidden-target wall-push reduction: when Noesis is chasing an unseen target and
  the forward probe is blocked, the controller keeps clearer-side strafe but
  removes hidden-target forward pressure instead of grinding into the wall.
- Hidden-target cooldown feedback for no-script autonomous runs: a hidden target
  that does not become visible within the timeout is cooled down briefly so
  target reacquisition can try another enemy.
- Targetless local exploration for no-script autonomous runs: when no target is
  engaged, the controller probes forward/left/right clearance, checks that
  there is floor and no lava/slime ahead, moves through open space, and
  turns/slides away from wall contacts without using a cached route script.
- Recent `start` and `e1m1` no-script harnesses can move safely without mouse
  capture, window activation, or route action scripts. The current targetless
  movement evidence is
  `diagnostics/agent_stream/20260521-020917/noesis/qge_noesis_summary.json`;
  the current E1M1 combat evidence is
  `diagnostics/agent_stream/20260521-021006/noesis/qge_noesis_summary.json`.

Partial or pending:

- Noesis is not yet learning Quake from experience; current autonomous runs use
  a reactive server-side controller, and scripted route policies are regression
  fixtures rather than learned play.
- It does not yet demonstrate robust, general Quake skill outside the bounded
  `e1m1` smoke.
- Target selection, real navigation/search, spatial memory, frontier selection,
  avoided-hazard memory, post-kill continuation, and learned policy updates
  remain active work.
- No-script wall-contact behavior now has bounded wall-follow, hidden wall-push
  reduction, hidden-target cooldowns, and floor/hazard checks, but it can still
  look confused because it is steering from local probes and reactive target
  feedback rather than a map-level navigation plan.
- If Noesis appears stationary, first check the run manifest and summary:
  `input.noesis_scripted` should be `0`, `input.noesis_autonomous` should be
  `1`, the action trace should have zero route-script lines, and route movement
  should appear in `gameplay.route.total_distance` plus
  `assist.movement_injected_sample_count`. If all movement counters are zero,
  the no-script autonomous hint or server assist did not engage.

What "learning" would require:

- A replay dataset or live experience buffer with state/action/outcome records
  beyond the current diagnostic summaries.
- An optimizer or policy update loop that changes model/controller parameters
  across runs.
- Evaluation splits that show improvement on held-out routes, maps, or combat
  situations instead of a single scripted or hand-tuned `e1m1` smoke.

## What Counts As Progress

A change is not considered verified just because it looks better once. For this
repo, progress means a narrow code/docs change plus at least one of:

- a focused unit or contract test that would fail without the change,
- a successful live graphics or Noesis stream with preserved diagnostics,
- a trace, manifest, screenshot, or summary JSON path cited in the attempt,
- an ICC task-attempt record and passing attempt-eval report.

Visual work should explicitly say whether it improves fixed-view captures,
autonomous movement captures, or both. Noesis work should explicitly say whether
it uses no-script autonomous control or an opt-in scripted fixture.

## Common Failure Modes

- **Noesis sits still:** verify the no-script path is active and that
  `qge_noesis_autonomous` plus `qge_noesis_assist` are present in the stream
  configuration. A default no-script run should not rely on
  `tools/noesis_quake_policy.sh`. The current `start` map targetless baseline is
  `diagnostics/agent_stream/20260521-020917/noesis/qge_noesis_summary.json`,
  where `target_count=0` but route distance is `7005.019`; a new stationary run
  should be treated as an autonomous-assist engagement regression.
- **Noesis moves but does not improve:** this is expected for now. The current
  controller is reactive; there is no weight update, replay training, spatial
  memory, or policy optimizer in the loop.
- **QGE graphics look smeared:** check whether `QGE_RENDER_DISPLAY_FILTER=1`
  was enabled. It can hide noise but over-blurred recent live frames.
- **QGE graphics look over-bright or noisy:** use a 1024 fixed-view capture as
  the first reference. The current direct-spatial path uses
  `QGE_NO_FLOOR_TONE_WHITE_HEADROOM` plus a stratified footprint filter for
  strongly minified floor, wall, and ceiling samples; lower-resolution 512
  smokes are useful for speed but make the surface artifacts look worse.
- **QGE graphics look frozen or lagged:** verify the stream is using the
  current default `QGE_RENDER_UPDATE_INTERVAL=1`. Logs should report
  `update_interval=1` and `reuse=0` for a fresh primary render every host
  frame.
- **QGE graphics shimmer on a static camera:** inspect render-gate logs. After
  `656caf4`, `gate_p`, `gate_edge`, `gate_gain`, `edge_gain`,
  `material_gain`, and `gate_rgb` should be stable for an unchanged scene even
  though `readout_ones` and `edge_ones` continue to vary as finite-shot
  measurement telemetry.
- **QGE graphics show black holes:** check normal texture palette opacity and
  transparent/fence classification before treating it as a DWT problem.
- **QGE graphics show full-frame wall strips:** inspect near-plane clipping,
  camera proximity, and projected polygon depth before tuning DWT thresholds.
- **A branch appears stale:** fetch first, then verify `origin/HEAD` and
  compare `origin/main` and `origin/master`. The intended current state is that
  both resolve to the same commit, with `origin/HEAD` pointing at
  `origin/master`.

## Claims Policy

Allowed current claims are intentionally narrow:

- QGE demonstrates bounded simulated-QPU observables inside live Quake frames.
- QGE compiles captured Quake scene/runtime data into auditable evidence and
  oracle-style sidecars.
- Quantum Quake is progressing toward vanilla conformance under explicit
  ownership and fallback accounting.

Not allowed:

- Claims of practical hardware quantum advantage.
- Claims that the full frame is rendered by a quantum computer.
- Claims that Quantum Quake is a complete vanilla Quake port.
- Claims that a visual/gameplay result is supported without trace, metric, test,
  screenshot, or ICC evidence.

See [qge_claims_ledger.md](qge_claims_ledger.md) and
[claims/qge_claims.json](claims/qge_claims.json).

## Build And Test Baseline

Common checks:

```sh
make test_qge
./bin/test_qge
bash tests/test_noesis_input_contract.sh
python3 tests/test_qge_python_tools.py
make test
```

Build the macOS app:

```sh
make quake
```

Safe fixed-view graphics capture:

```sh
QGE_STREAM_LAUNCH=open QGE_STREAM_MOUSE=0 QGE_STREAM_ACTIVATE=0 \
QGE_STREAM_TRACE=1 QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=1 \
QGE_STREAM_WAIT_FRAMES=12 QGE_STREAM_PLAYER=none QGE_RENDER=2 \
QGE_RENDER_UPDATE_INTERVAL=1 QGE_STREAM_SOUND=0 \
bash tools/quake_graphics_stream.sh
```

`QGE_RENDER_UPDATE_INTERVAL=1` is now the default; keep it explicit in evidence
commands when the purpose is to prove every-frame QGE refresh.

Safe Noesis gameplay capture:

```sh
QGE_STREAM_LAUNCH=open QGE_STREAM_MOUSE=0 QGE_STREAM_ACTIVATE=0 \
QGE_STREAM_TRACE=1 QGE_STREAM_MAP=e1m1 QGE_STREAM_FRAMES=3 \
QGE_STREAM_WAIT_FRAMES=12 QGE_STREAM_PLAYER=noesis QGE_RENDER=2 \
QGE_RENDER_UPDATE_INTERVAL=1 QGE_STREAM_SOUND=0 \
bash tools/quake_graphics_stream.sh
```

ICC checks used for verified slices:

```sh
/Users/tyr/Desktop/infinite_context_coder/bin/icc source-drift --repo quantum_quake --format markdown
/Users/tyr/Desktop/infinite_context_coder/bin/icc assistant-status --repo quantum_quake --format markdown
/Users/tyr/Desktop/infinite_context_coder/bin/icc production-audit --repo quantum_quake --preset shell-hardening --format markdown
```

## Development Rules Of Thumb

- Keep QGE domain changes narrow and evidence-backed.
- Preserve classic Quake as the reference/fallback until a domain has a clean
  authority gate.
- Do not promote a visual option to default just because it looks smoother once;
  it needs performance and artifact evidence.
- Treat live harnesses as controlled diagnostics. Use `QGE_STREAM_MOUSE=0` and
  `QGE_STREAM_ACTIVATE=0` by default.
- Update docs and contracts when a runtime behavior becomes intentional.
- Record ICC attempts for verified gameplay, rendering, or production-hardening
  slices.
- Keep Noesis no-script by default. Use scripted route files only when the task
  is explicitly a regression fixture or policy-command-buffer test.
