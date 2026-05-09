/*
 * qge_hooks.h - Quantum Game Engine integration hooks for QuakeSpasm
 *
 * Bridge layer between Quake engine and QGE library.
 * All quantum operations are routed through these hooks:
 *   - Quantum RNG replaces rand()
 *   - Quantum AI decisions for monsters
 *   - Quantum DWT rendering pipeline
 *   - Quantum visibility (Grover BSP)
 *   - Quantum physics (wave packet particles)
 *
 * Architecture: Quake -> qge_hooks -> QGE -> Moonlab
 */

#ifndef QGE_HOOKS_H
#define QGE_HOOKS_H

#include "quakedef.h"
#include "../../qge/qge_world.h"

/* ============================================================================
 * Lifecycle
 * ============================================================================ */

/* Initialize QGE — called from Host_Init() after S_Init() */
void QGE_Init(void);

/* Shutdown QGE — called from Host_Shutdown() before S_Shutdown() */
void QGE_Shutdown(void);

/* Per-frame begin/end — called from _Host_Frame() */
void QGE_FrameBegin(void);
void QGE_FrameEnd(void);

/* ============================================================================
 * Quantum RNG
 * ============================================================================ */

/* Quantum replacement for rand() — returns 0 to RAND_MAX */
int QGE_Random(void);

/* Quantum random float in [0, 1) — replaces PF_random() */
float QGE_RandomFloat(void);

/* ============================================================================
 * Quantum Rendering
 * ============================================================================ */

/* Render the current scene through quantum DWT pipeline.
 * Called from R_RenderScene() when quantum_render is enabled.
 * Encodes visible surfaces/entities as wavelet coefficients,
 * extracts via measurement, inverse DWT to pixels, blits to screen. */
void QGE_RenderScene(void);

/* True when QGE should own the primary 3D framebuffer instead of acting as
 * a translucent diagnostic overlay. */
qboolean QGE_RenderIsPrimary(void);

/* Record whether the classic 3D renderer or QGE owns this frame's final 3D
 * framebuffer. Counts are emitted in render telemetry for publication gates. */
void QGE_RenderSetOwnershipTelemetry(int classic_3d_passes,
                                     int suppressed_3d_passes);

/* Begin collecting world/entity draw submissions for this frame. */
void QGE_SceneBegin(void);

/* Submit a visible BSP world surface to the QGE scene graph. */
void QGE_SceneSubmitWorldSurface(qmodel_t *model, msurface_t *surf);

/* Register a 2D HUD/menu image as a stable QGE asset ref. */
void QGE_RegisterHudImageAsset(const char *name,
                               int width,
                               int height,
                               unsigned int source_crc,
                               unsigned int source_format,
                               unsigned int flags,
                               const void *debug_cookie);

/* ============================================================================
 * Quantum Visibility
 * ============================================================================ */

/* Query whether a BSP surface is visible using Grover-accelerated search.
 * Returns visibility probability (0.0 = hidden, 1.0 = visible). */
float QGE_VisQuerySurface(int surface_id);

/* Register a BSP surface for quantum visibility testing */
void QGE_VisRegisterSurface(int surface_id,
                             float min_x, float min_y, float min_z,
                             float max_x, float max_y, float max_z);

/* Setup viewpoint for visibility queries */
void QGE_VisSetupViewpoint(float eye_x, float eye_y, float eye_z,
                            float fwd_x, float fwd_y, float fwd_z);

/* ============================================================================
 * Quantum Particles
 * ============================================================================ */

/* Draw particles using quantum wave packet system */
void QGE_DrawParticles(void);

/* Copy currently active classic Quake particles into the QGE frame snapshot.
 * Implemented by r_part.c because the classic particle list is renderer-local. */
void QGE_CaptureClassicParticles(qge_frame_snapshot_t *snapshot);

/* ============================================================================
 * Quantum Physics
 * ============================================================================ */

/* Feed Quake server toss/bounce/missile entities into QGE/Moonlab physics.
 * These hooks are observational today: they register authoritative Quake state
 * and quantum particle effects without changing collision/gameplay outcomes. */
void QGE_PhysicsTrackToss(edict_t *ent, float dt);
void QGE_PhysicsTrackImpact(edict_t *ent, const trace_t *trace);

/* ============================================================================
 * Quantum AI
 * ============================================================================ */

/* Make a quantum AI decision for a monster entity.
 * Returns an action index (0=IDLE, 1=PATROL, 2=CHASE, 3=ATTACK, 4=FLEE). */
int QGE_AIDecide(int enemy_id, float aggression, float distance, int visible);

/* ============================================================================
 * CVars
 * ============================================================================ */

extern cvar_t quantum_render;       /* 0 classic, 1 QGE overlay, 2 QGE primary */
extern cvar_t quantum_rng;          /* Enable quantum RNG (default 1) */
extern cvar_t quantum_ai;           /* Enable quantum AI decisions (default 1) */
extern cvar_t quantum_particles;    /* Enable quantum particles (default 0) */
extern cvar_t quantum_vis;          /* Enable quantum visibility (default 0) */
extern cvar_t quantum_physics;      /* Feed server physics into QGE (default 1) */
extern cvar_t quantum_projectiles;  /* Feed projectile/missile state into QGE (default 1) */
extern cvar_t quantum_debug;        /* Emit QGE render diagnostics (default 0) */
extern cvar_t quantum_overlay_alpha;/* Quantum render composite alpha (default 0.10) */
extern cvar_t quantum_scene_surface_budget; /* DWT surface encode budget (default 160) */
extern cvar_t quantum_render_update_interval; /* QGE update cadence in host frames (default 8) */

#endif /* QGE_HOOKS_H */
