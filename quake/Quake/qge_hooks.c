/*
 * qge_hooks.c - Quantum Game Engine integration for QuakeSpasm
 *
 * Routes Quake subsystems through QGE quantum processing:
 *   RNG:        rand() → qge_random() (Bell-verified quantum measurement)
 *   Rendering:  R_RenderScene() → QGE DWT pipeline (wavelet coefficient encoding → inverse DWT)
 *   Visibility: R_DrawWorld() → Grover-accelerated BSP search
 *   Particles:  R_DrawParticles() → Wave packet evolution + measurement
 *   AI:         PF_random() → Entangled quantum AI decisions
 *
 * This is the same quantum signal processing pattern as snd_quantum.c (audio):
 *   Classical domain → Transform → Quantum circuit → Measurement → Inverse transform → Classical domain
 *
 * Architecture: qge_hooks.c → QGE (qge.h) → Moonlab (quantum simulator)
 */

#include "quakedef.h"
#include "qge_hooks.h"
#include "gl_texmgr.h"

/* QGE API */
#include "../../qge/qge.h"
#include "../../deps/moonlab/src/quantum/gates.h"
#include "../../deps/moonlab/src/quantum/measurement.h"
#include "../../deps/moonlab/src/quantum/state.h"

/* GL headers come via quakedef.h → SDL_opengl.h */

#if defined(__GNUC__) || defined(__clang__)
#define QGE_HOT_INLINE static inline __attribute__((always_inline))
#else
#define QGE_HOT_INLINE static inline
#endif

/* ============================================================================
 * CVars
 * ============================================================================ */

cvar_t quantum_render    = {"quantum_render",    "0", CVAR_ARCHIVE};
cvar_t quantum_rng       = {"quantum_rng",       "1", CVAR_ARCHIVE};
cvar_t quantum_ai        = {"quantum_ai",        "1", CVAR_ARCHIVE};
cvar_t quantum_particles = {"quantum_particles", "0", CVAR_ARCHIVE};
cvar_t quantum_vis       = {"quantum_vis",       "0", CVAR_ARCHIVE};
cvar_t quantum_physics   = {"quantum_physics",   "1", CVAR_ARCHIVE};
cvar_t quantum_projectiles = {"quantum_projectiles", "1", CVAR_ARCHIVE};
cvar_t quantum_physics_authoritative = {"quantum_physics_authoritative", "0", CVAR_ARCHIVE};
cvar_t quantum_debug     = {"quantum_debug",     "0", CVAR_NONE};
cvar_t qge_noesis_assist = {"qge_noesis_assist", "0", CVAR_NONE};
cvar_t quantum_overlay_alpha = {"quantum_overlay_alpha", "0.10", CVAR_ARCHIVE};
cvar_t quantum_scene_surface_budget = {"quantum_scene_surface_budget", "128", CVAR_ARCHIVE};
cvar_t quantum_render_res = {"quantum_render_res", "1024", CVAR_ARCHIVE};
cvar_t quantum_render_threshold = {"quantum_render_threshold", "0.001", CVAR_ARCHIVE};
cvar_t quantum_render_edge_gain = {"quantum_render_edge_gain", "0.06", CVAR_ARCHIVE};
cvar_t quantum_render_material_gain = {"quantum_render_material_gain", "0.18", CVAR_ARCHIVE};
cvar_t quantum_render_bilinear_samples = {"quantum_render_bilinear_samples", "0", CVAR_ARCHIVE};
cvar_t quantum_render_edge_samples = {"quantum_render_edge_samples", "0", CVAR_ARCHIVE};
cvar_t quantum_render_display_filter = {"quantum_render_display_filter", "0", CVAR_ARCHIVE};
cvar_t quantum_render_update_interval = {"quantum_render_update_interval", "8", CVAR_ARCHIVE};
cvar_t quantum_render_gate_kernel = {"quantum_render_gate_kernel", "1", CVAR_ARCHIVE};
cvar_t quantum_render_gate_shots = {"quantum_render_gate_shots", "64", CVAR_ARCHIVE};
cvar_t quantum_debug_sprite_billboard = {"quantum_debug_sprite_billboard", "0", CVAR_NONE};

/* ============================================================================
 * State
 * ============================================================================ */

static qge_context_t* qge_ctx = NULL;
static qge_particle_system_t* qge_particles = NULL;

#define QGE_DWT_CHANNELS 3
#define QGE_DWT_R 0
#define QGE_DWT_G 1
#define QGE_DWT_B 2

/* Quantum DWT framebuffers — one sparse DWT field per RGB channel */
static dwt_framebuffer_t* qge_dwt_fb[QGE_DWT_CHANNELS] = {NULL, NULL, NULL};

/* Render buffers */
static float* qge_render_buffer = NULL;
static float* qge_render_color_buffer[QGE_DWT_CHANNELS] = {NULL, NULL, NULL};
static uint8_t* qge_display_buffer = NULL;
static float* qge_spatial_encode_buffer = NULL;
static float* qge_spatial_color_buffer[QGE_DWT_CHANNELS] = {NULL, NULL, NULL};
static float* qge_spatial_depth_buffer = NULL;

static int qge_render_res = 1024;  /* Internal quantum render resolution */

#define QGE_SPATIAL_DEPTH_FAR 1.0e30f
#define QGE_SPATIAL_DEPTH_EPSILON 2.0f

/* GL texture for quantum framebuffer */
static GLuint qge_texture = 0;
static GLint qge_blit_texture_units = 1;
static qboolean qge_display_texture_dirty = false;
static GLenum qge_last_gl_upload_error = GL_NO_ERROR;
static GLenum qge_last_gl_draw_error = GL_NO_ERROR;
static float qge_last_tone_floor = 0.0f;
static float qge_last_tone_white = 1.0f;
static int qge_last_tone_clipped = 0;
static int qge_render_classic_3d_passes = 0;
static int qge_render_suppressed_3d_passes = 0;
static int qge_render_qge_primary_owned = 0;
static int qge_render_last_update_frame = -1;
static int qge_render_reused_frames = 0;
static qboolean qge_render_collect_frame = true;
static qboolean qge_vis_shadow_active = false;
static const qmodel_t *qge_vis_shadow_model = NULL;
static int qge_vis_shadow_registered_surfaces = 0;
static int qge_vis_authority_requested = 0;
static int qge_vis_authority_selected = 0;
static int qge_vis_fallback_selected = 1;
static const char *qge_vis_authority_reason = "not_evaluated";
static const char *qge_vis_fallback_reason = "not_evaluated";
static const qmodel_t *qge_vis_authority_model = NULL;
static const unsigned char *qge_vis_authority_mask = NULL;
static int qge_vis_authority_mask_count = 0;
static qge_vis_writeback_decision_t qge_vis_last_decision;
static qboolean qge_vis_last_decision_valid = false;

#define QGE_VIS_TRACE_FLAG_REGISTERED          0x0001u
#define QGE_VIS_TRACE_FLAG_MISMATCH            0x0002u
#define QGE_VIS_TRACE_FLAG_FALSE_POSITIVE      0x0004u
#define QGE_VIS_TRACE_FLAG_FALSE_NEGATIVE      0x0008u
#define QGE_VIS_TRACE_FLAG_OVERFLOW            0x0010u
#define QGE_VIS_TRACE_FLAG_AUTHORITY_REQUESTED 0x0020u
#define QGE_VIS_TRACE_FLAG_AUTHORITY_READY     0x0040u
#define QGE_VIS_TRACE_FLAG_AUTHORITY_SELECTED  0x0080u
#define QGE_VIS_TRACE_FLAG_FALLBACK_SELECTED   0x0100u
#define QGE_VIS_TRACE_FLAG_WARMUP_PENDING      0x0200u
#define QGE_VIS_TRACE_FLAG_CONTROLLED_SMOKE    0x0400u
#define QGE_VIS_TRACE_FLAG_FN_REPAIRED         0x0800u

#define QGE_CLASSIC_2D_VISIBLE 1

static qboolean qge_initialized = false;

static FILE *qge_gameplay_outcome_file = NULL;
static qboolean qge_gameplay_outcome_tried = false;
static qboolean qge_gameplay_prev_valid = false;
static char qge_gameplay_outcome_path[MAX_OSPATH];
static char qge_gameplay_map[64];
static vec3_t qge_gameplay_start_origin;
static vec3_t qge_gameplay_prev_origin;
static int qge_gameplay_prev_leaf = -1;
static int qge_gameplay_samples = 0;
static double qge_gameplay_total_distance = 0.0;
static double qge_gameplay_max_displacement = 0.0;
static int qge_gameplay_leaf_transitions = 0;
static int qge_gameplay_damage_taken_total = 0;
static int qge_gameplay_damage_dealt_total = 0;
static int qge_gameplay_kills_total = 0;
static int qge_gameplay_pickups_total = 0;
static int qge_gameplay_weapon_changes_total = 0;
static int qge_gameplay_attack_presses_total = 0;
static int qge_gameplay_prev_health = 0;
static int qge_gameplay_prev_armor = 0;
static int qge_gameplay_prev_ammo_total = 0;
static int qge_gameplay_prev_items = 0;
static int qge_gameplay_prev_weapon = 0;
static int qge_gameplay_prev_frags = 0;
static int qge_gameplay_prev_killed_monsters = 0;
static int qge_gameplay_prev_attack_active = 0;
static int qge_gameplay_prev_damageable_alive = 0;
static float *qge_gameplay_prev_edict_health = NULL;
static int qge_gameplay_prev_edict_capacity = 0;
static int qge_noesis_assist_last_log_frame = -999999;
static int qge_noesis_assist_mode = 0;
static qboolean qge_noesis_assist_active = false;
static int qge_noesis_assist_target_id = 0;
static qboolean qge_noesis_assist_target_visible = false;
static float qge_noesis_assist_target_distance = -1.0f;
static float qge_noesis_assist_aim_pitch = 0.0f;
static float qge_noesis_assist_aim_yaw = 0.0f;
static float qge_noesis_assist_forwardmove = 0.0f;
static float qge_noesis_assist_sidemove = 0.0f;
static float qge_noesis_assist_forward_clear = -1.0f;
static float qge_noesis_assist_left_clear = -1.0f;
static float qge_noesis_assist_right_clear = -1.0f;

static int QGE_RenderUpdateInterval(void);
static qboolean QGE_RenderShouldUpdateFrame(void);

#define QGE_RENDER_GATE_QUBITS 6
#define QGE_RENDER_GATE_DIM (1u << QGE_RENDER_GATE_QUBITS)
#define QGE_RENDER_GATE_FLAG_ACTIVE 0x20000u
#define QGE_RENDER_GATE_FLAG_ERROR 0x40000u
#define QGE_RENDER_TRACE_FLAG_PRIMARY_OWNED 0x00010000u
#define QGE_RENDER_TRACE_FLAG_NATIVE_IDWT 0x00020000u
#define QGE_RENDER_TRACE_FLAG_NATIVE_IDWT_FALLBACK 0x00040000u
#define QGE_RENDER_TRACE_FLAG_CPU_IDWT 0x00080000u
#define QGE_TONE_LUT_SIZE 4096

static quantum_state_t qge_render_gate_state;
static qboolean qge_render_gate_initialized = false;
static int qge_render_gate_shots = 0;
static int qge_render_gate_readout_ones = 0;
static int qge_render_gate_edge_ones = 0;
static int qge_render_gate_total = 0;
static int qge_render_gate_h = 0;
static int qge_render_gate_ry = 0;
static int qge_render_gate_rz = 0;
static int qge_render_gate_entangling = 0;
static int qge_render_gate_phase_count = 0;
static int qge_render_gate_errors = 0;
static int qge_render_gate_active_basis = 0;
static float qge_render_gate_gain = 1.0f;
static float qge_render_gate_edge_gain = 1.0f;
static float qge_render_gate_material_gain = 1.0f;
static float qge_render_gate_color_gain[QGE_DWT_CHANNELS] = {1.0f, 1.0f, 1.0f};
static float qge_render_gate_probability = 0.5f;
static float qge_render_gate_edge_observable = 0.5f;
static float qge_render_gate_coherence = 0.0f;
static float qge_render_gate_entropy = 0.0f;
static float qge_render_gate_max_probability = 1.0f;
static uint64_t qge_render_gate_majority_basis = 0;
static uint64_t qge_render_gate_state_hash = 0;
static float qge_tone_lut[QGE_TONE_LUT_SIZE];
static qboolean qge_tone_lut_ready = false;

static const char *QGE_CommandLineTracePath(void)
{
	int arg;

	arg = COM_CheckParm("-qgetrace");
	if (arg && arg < com_argc - 1 && com_argv[arg + 1] &&
		com_argv[arg + 1][0])
		return com_argv[arg + 1];
	return NULL;
}

static const char *QGE_CommandLineReplayPath(void)
{
	int arg;

	arg = COM_CheckParm("-qgereplay");
	if (arg && arg < com_argc - 1 && com_argv[arg + 1] &&
		com_argv[arg + 1][0])
		return com_argv[arg + 1];
	arg = COM_CheckParm("-qgereplaytrace");
	if (arg && arg < com_argc - 1 && com_argv[arg + 1] &&
		com_argv[arg + 1][0])
		return com_argv[arg + 1];
	return NULL;
}

static qboolean QGE_CommandLineValue(const char *parm, const char **value)
{
	int arg;

	if (value)
		*value = NULL;
	arg = COM_CheckParm(parm);
	if (arg && arg < com_argc - 1 && com_argv[arg + 1] &&
		com_argv[arg + 1][0]) {
		if (value)
			*value = com_argv[arg + 1];
		return true;
	}
	return false;
}

static qboolean QGE_ParseBoolValue(const char *value, qboolean default_value)
{
	if (!value || !value[0])
		return default_value;
	if (value[0] == '0' || value[0] == 'f' || value[0] == 'F' ||
		value[0] == 'n' || value[0] == 'N')
		return false;
	return true;
}

static void QGE_ApplyEarlyRenderOverrides(void)
{
	const char *value;
	const char *source;

	source = NULL;
	if (QGE_CommandLineValue("-qgerenderres", &value))
		source = "-qgerenderres";
	else if ((value = getenv("QGE_RENDER_RES")) && value[0])
		source = "QGE_RENDER_RES";
	if (source) {
		Cvar_SetValueQuick(&quantum_render_res, (float)Q_atoi(value));
		Con_Printf("QGE: early %s quantum_render_res %d\n",
				   source, (int)quantum_render_res.value);
	}

	source = NULL;
	if (QGE_CommandLineValue("-qgerenderthreshold", &value))
		source = "-qgerenderthreshold";
	else if ((value = getenv("QGE_RENDER_THRESHOLD")) && value[0])
		source = "QGE_RENDER_THRESHOLD";
	if (source) {
		Cvar_SetValueQuick(&quantum_render_threshold, Q_atof(value));
		Con_Printf("QGE: early %s quantum_render_threshold %.4f\n",
				   source, quantum_render_threshold.value);
	}
}

/* Frame timing */
static double qge_frame_start = 0.0;
static int qge_frame_count = 0;
static double qge_avg_frame_ms = 0.0;

/* Physics ingestion telemetry */
static int qge_phys_toss_count = 0;
static int qge_phys_projectile_count = 0;
static int qge_phys_impact_count = 0;
static int qge_phys_particle_spawns = 0;

#define QGE_MAX_SCENE_SURFACES 4096
#define QGE_MAX_PHYS_OBJECTS 512

typedef struct {
	const msurface_t *surf;
	int surface_id;
	int texture_id;
	int flags;
	int numverts;
	int lightmap;
	unsigned int texture_crc;
	unsigned int texture_hash;
	unsigned int texture_width;
	unsigned int texture_height;
	unsigned int texture_format;
	unsigned int light_hash;
	qboolean has_fullbright;
	qboolean has_warp;
	char texture_name[16];
	vec3_t mins;
	vec3_t maxs;
	vec3_t centroid;
	float depth;
	float brightness;
	float light_energy;
	float light_contrast;
	float material_signal;
} qge_scene_surface_t;

typedef struct {
	qboolean active;
	int entnum;
	int movetype;
	int solid;
	int flags;
	int owner_entnum;
	int groundentity_entnum;
	int waterlevel;
	int watertype;
	int last_seen_frame;
	int seen_count;
	int impacts;
	int last_impact_frame;
	int last_impact_entnum;
	float last_impact_fraction;
	qboolean last_impact_inopen;
	qboolean last_impact_inwater;
	vec3_t origin;
	vec3_t velocity;
	vec3_t mins;
	vec3_t maxs;
	vec3_t absmin;
	vec3_t absmax;
	vec3_t predicted_origin;
	vec3_t last_impact_origin;
	vec3_t last_impact_normal;
	float shadow_error;
	float max_shadow_error;
	qboolean branch_state_valid;
	qge_projectile_branch_state_t branch_state;
	int preimpact_selection_frame;
} qge_phys_object_t;

static qge_scene_surface_t qge_scene_surfaces[QGE_MAX_SCENE_SURFACES];
static int qge_scene_surface_count = 0;
static int qge_scene_surface_dropped = 0;
static int qge_scene_world_surfaces = 0;
static int qge_scene_sky_surfaces = 0;
static int qge_scene_water_surfaces = 0;
static int qge_scene_encoded_surfaces = 0;
static int qge_scene_textured_surfaces = 0;
static int qge_scene_lightmapped_surfaces = 0;
static int qge_scene_material_encoded = 0;
static int qge_scene_snapshot_surfaces = 0;
static int qge_scene_snapshot_misses = 0;
static int qge_scene_texture_cache_hits = 0;
static int qge_scene_texture_cache_misses = 0;
static int qge_scene_lightmap_cache_hits = 0;
static int qge_scene_lightmap_cache_misses = 0;
static int qge_scene_polygon_encoded = 0;
static int qge_scene_polygon_fallback = 0;
static int qge_scene_polygon_surrogate = 0;
static int qge_scene_polygon_surrogate_micro = 0;
static int qge_scene_polygon_surrogate_clipped = 0;
static int qge_scene_polygon_surrogate_invalid = 0;
static int qge_scene_polygon_culled = 0;
static int qge_scene_polygon_triangles = 0;
static int qge_scene_triangle_edge_fills = 0;
static int qge_scene_polygon_micro_fills = 0;
static int qge_scene_snapshot_edicts = 0;
static int qge_scene_encoded_edicts = 0;
static int qge_scene_alias_encoded = 0;
static int qge_scene_sprite_encoded = 0;
static int qge_scene_viewmodel_encoded = 0;
static int qge_scene_entity_misses = 0;
static int qge_scene_entity_coefficients = 0;
static int qge_scene_entity_mesh_triangles = 0;
static int qge_scene_sprite_billboards = 0;
static int qge_scene_snapshot_particles = 0;
static int qge_scene_encoded_particles = 0;
static int qge_scene_particle_coefficients = 0;
static double qge_scene_setup_ms = 0.0;
static double qge_scene_raster_ms = 0.0;
static double qge_scene_forward_dwt_ms = 0.0;

static qge_phys_object_t qge_phys_objects[QGE_MAX_PHYS_OBJECTS];
static int qge_phys_active_objects = 0;
static int qge_phys_active_projectiles = 0;
static int qge_phys_registry_purged = 0;
static int qge_phys_mirrored_bounds = 0;
static int qge_phys_mirrored_owner = 0;
static int qge_phys_mirrored_water = 0;
static int qge_phys_mirrored_impacts = 0;
static float qge_phys_avg_shadow_error = 0.0f;
static float qge_phys_max_shadow_error = 0.0f;
static int qge_phys_projectile_shadow_samples = 0;
static float qge_phys_projectile_avg_shadow_error = 0.0f;
static float qge_phys_projectile_max_shadow_error = 0.0f;
static int qge_phys_projectile_authority_warmup_frames = 0;
static int qge_phys_projectile_authority_ready_frames = 0;
static int qge_phys_projectile_authority_off_frames = 0;
static qboolean qge_phys_projectile_authority_ready = false;
static qge_projectile_authority_off_reason_t qge_phys_projectile_authority_off_reason =
	QGE_PROJECTILE_AUTHORITY_OFF_DISABLED;
static qge_projectile_authority_state_t qge_phys_projectile_authority_state;
static int qge_phys_projectile_writeback_decisions = 0;
static int qge_phys_projectile_writeback_selected = 0;
static int qge_phys_projectile_writeback_fallback = 0;
static int qge_phys_projectile_writeback_rollback = 0;
static int qge_phys_projectile_branch_states = 0;
static int qge_phys_projectile_impact_measurements = 0;
static int qge_phys_projectile_preimpact_decisions = 0;
static int qge_phys_projectile_preimpact_selected = 0;
static int qge_phys_projectile_preimpact_collisions = 0;
static int qge_phys_projectile_preimpact_oracle_traces = 0;
static int qge_phys_projectile_preimpact_noimpact = 0;
static int qge_phys_projectile_preimpact_alternate_impacts = 0;

enum {
	QGE_PROJECTILE_TRACE_FLAG_COLLISION_ORACLE = 0x00800000u,
	QGE_PROJECTILE_TRACE_FLAG_ORACLE_QGE_TRACE = 0x01000000u,
	QGE_PROJECTILE_TRACE_FLAG_ORACLE_NO_IMPACT = 0x02000000u,
	QGE_PROJECTILE_TRACE_FLAG_ORACLE_ALT_IMPACT = 0x04000000u,
	QGE_PROJECTILE_TRACE_FLAG_ORACLE_CLASSIC = 0x08000000u,
	QGE_PROJECTILE_TRACE_FLAG_SAVE_DEMO_BOUNDARY = 0x10000000u,
	QGE_PROJECTILE_TRACE_FLAG_SAVE_DEMO_ORACLE = 0x20000000u,
	QGE_PROJECTILE_TRACE_FLAG_SAVE_DEMO_WRITEBACK = 0x40000000u
};

static void QGE_PhysicsRefreshStats(void);
static qboolean QGE_PhysicsProjectileAuthorityRequested(void);
static void QGE_PhysicsUpdateProjectileAuthorityGate(void);
static void QGE_TraceProjectileBranchState(
	qge_quantum_runtime_t *rt,
	const qge_projectile_branch_state_t *state);
static void QGE_TraceProjectilePreimpactSelection(
	qge_quantum_runtime_t *rt,
	const qge_projectile_branch_state_t *state,
	const qge_projectile_writeback_decision_t *decision,
	const qge_projectile_collision_oracle_decision_t *oracle);
static void QGE_TraceProjectileSaveDemoBoundary(
	qge_quantum_runtime_t *rt,
	const qge_projectile_branch_state_t *state,
	const qge_projectile_writeback_decision_t *decision,
	const qge_projectile_collision_oracle_decision_t *oracle,
	uint64_t decision_hash,
	qboolean writeback_boundary);
static void QGE_TraceProjectileImpactMeasurement(
	qge_quantum_runtime_t *rt,
	const qge_projectile_branch_state_t *state);
static void QGE_TraceProjectileAuthorityGate(qge_quantum_runtime_t *rt);
static void QGE_TraceProjectileWritebackDecision(
	qge_quantum_runtime_t *rt,
	const qge_projectile_writeback_decision_t *decision);
static qboolean QGE_PhysicsBuildProjectileBranchRequest(
	qge_phys_object_t *obj,
	edict_t *ent,
	qge_observation_boundary_t boundary,
	const trace_t *trace,
	qge_projectile_branch_request_t *request);
static qboolean QGE_PhysicsBuildProjectileWritebackRequest(
	qge_phys_object_t *obj,
	edict_t *ent,
	qge_projectile_writeback_request_t *request);
static unsigned int QGE_SurfaceLightSignal(const msurface_t *surf,
										   float *energy,
										   float *contrast);

static int qge_dwt_levels = 4;       /* Configured DWT reconstruction levels */

static qmodel_t *qge_registered_worldmodel = NULL;
static char qge_registered_world_name[MAX_QPATH];
static qge_world_stats_t qge_registry_stats;
static qge_resource_id_t qge_precache_model_resource_ids[MAX_MODELS];
static qge_resource_id_t qge_precache_sound_resource_ids[MAX_SOUNDS];
static qge_resource_id_t qge_debug_sprite_logged_id = QGE_RESOURCE_ID_INVALID;

#define QGE_MAX_TEXTURE_SIGNAL_CACHE MAX_MAP_TEXTURES
typedef struct {
	qboolean valid;
	unsigned int texture_hash;
	unsigned int texture_crc;
	unsigned int texture_width;
	unsigned int texture_height;
	unsigned int texture_format;
	qboolean has_fullbright;
	qboolean has_warp;
} qge_texture_signal_cache_t;

static qge_texture_signal_cache_t qge_texture_signal_cache[QGE_MAX_TEXTURE_SIGNAL_CACHE];
static int qge_texture_signal_cache_entries = 0;
static int qge_texture_signal_gltexture_entries = 0;
static int qge_texture_signal_fullbright_entries = 0;
static int qge_texture_signal_warp_entries = 0;
static uint64_t qge_texture_signal_cache_hash = 0;

static unsigned int QGE_TextureSignalBuild(const texture_t *tex,
										   qge_texture_signal_cache_t *out);

#define QGE_MAX_LIGHTMAP_SIGNAL_CACHE MAX_MAP_FACES
#define QGE_MAX_PROJECTED_POLY_VERTS 96
#define QGE_MAX_PROJECTED_TRIS (QGE_MAX_PROJECTED_POLY_VERTS - 2)
#define QGE_MAX_ALIAS_ENTITY_TRIS 96
#define QGE_PROJECTED_AREA_EPSILON 0.000001f
typedef struct {
	qboolean valid;
	unsigned int light_hash;
	float light_energy;
	float light_contrast;
} qge_lightmap_signal_cache_t;

static qge_lightmap_signal_cache_t qge_lightmap_signal_cache[QGE_MAX_LIGHTMAP_SIGNAL_CACHE];
static int qge_lightmap_signal_cache_entries = 0;
static int qge_lightmap_signal_lit_entries = 0;
static int qge_lightmap_signal_contrast_entries = 0;
static uint64_t qge_lightmap_signal_cache_hash = 0;

typedef struct {
	float x;
	float y;
	float depth;
	float tex_s;
	float tex_t;
	float light_s;
	float light_t;
} qge_projected_vertex_t;

typedef struct {
	qge_projected_vertex_t v[3];
} qge_projected_triangle_t;

typedef struct {
	const qge_projected_vertex_t *a;
	const qge_projected_vertex_t *b;
	const qge_projected_vertex_t *c;
	float inv_denom;
	float ia;
	float ib;
	float ic;
	float a_tex_s_ia;
	float b_tex_s_ib;
	float c_tex_s_ic;
	float a_tex_t_ia;
	float b_tex_t_ib;
	float c_tex_t_ic;
	float a_light_s_ia;
	float b_light_s_ib;
	float c_light_s_ic;
	float a_light_t_ia;
	float b_light_t_ib;
	float c_light_t_ic;
	float inv_depth_dx;
	float tex_s_num_dx;
	float tex_t_num_dx;
	float light_s_num_dx;
	float light_t_num_dx;
	float w0_origin;
	float w1_origin;
	float w0_dx;
	float w0_dy;
	float w1_dx;
	float w1_dy;
	qboolean valid;
} qge_projected_triangle_sampler_t;

typedef enum {
	QGE_PROJECT_FAIL_NONE = 0,
	QGE_PROJECT_FAIL_INVALID,
	QGE_PROJECT_FAIL_NO_POLY,
	QGE_PROJECT_FAIL_NEAR_CLIP_EMPTY,
	QGE_PROJECT_FAIL_PROJECT_EMPTY,
	QGE_PROJECT_FAIL_VIEWPORT_CLIP_EMPTY,
	QGE_PROJECT_FAIL_MICRO_AREA
} qge_project_fail_reason_t;

typedef struct {
	vec3_t world;
	float depth;
	float tex_s;
	float tex_t;
	float light_s;
	float light_t;
} qge_clip_vertex_t;

typedef struct {
	float depth;
	float tex_s;
	float tex_t;
	float light_s;
	float light_t;
} qge_projected_sample_t;

typedef struct {
	float r;
	float g;
	float b;
} qge_rgb_sample_t;

static qge_rgb_sample_t qge_palette_lut[256];
static qboolean qge_palette_opaque[256];
static qboolean qge_palette_lut_ready = false;

typedef struct {
	const qge_scene_surface_t *surface;
	const msurface_t *surf;
	texture_t *tex;
	const byte *tex_pixels;
	unsigned int tex_width;
	unsigned int tex_height;
	unsigned int tex_width_mask;
	unsigned int tex_height_mask;
	float tex_width_f;
	float tex_height_f;
	int light_smax;
	int light_tmax;
	int light_size;
	int light_map_count;
	float light_s_scale;
	float light_t_scale;
	float light_s_offset;
	float light_t_offset;
	float light_scales[MAXLIGHTMAPS];
	qboolean has_light;
	qboolean bilinear;
	qboolean sky;
	qboolean fence;
	qboolean tex_power2;
	float color_gain_r;
	float color_gain_g;
	float color_gain_b;
} qge_surface_sample_context_t;

#define QGE_MAX_HUD_IMAGE_REFS 256
typedef struct {
	qboolean used;
	qge_hud_image_ref_t ref;
	uint32_t registered_revision;
	qge_resource_id_t id;
} qge_hud_image_pending_t;

static qge_hud_image_pending_t qge_hud_images[QGE_MAX_HUD_IMAGE_REFS];
static int qge_hud_image_count = 0;
static int qge_hud_image_dropped = 0;
static qboolean qge_hud_conchars_registered = false;

typedef struct {
	int hud_draws;
	int hud_owned;
	int hud_unowned;
	int console_draws;
	int console_owned;
	int console_unowned;
	int other_draws;
} qge_2d_ownership_frame_t;

static qge_2d_ownership_frame_t qge_2d_current;
static qge_2d_ownership_frame_t qge_2d_last;
static qboolean qge_2d_collecting = false;
static qboolean qge_2d_last_valid = false;
static int qge_2d_layer = QGE_2D_LAYER_NONE;

static int QGE_ServerTimeMsec(void)
{
	return (int)(sv.time * 1000.0);
}

static qge_quantum_runtime_t *QGE_Runtime(void)
{
	return qge_get_quantum_runtime(qge_ctx);
}

static const char *QGE_GameplayStreamDir(void)
{
	int arg;
	const char *env;

	arg = COM_CheckParm("-qgestreamdir");
	if (arg && arg < com_argc - 1 && com_argv[arg + 1] &&
		com_argv[arg + 1][0])
		return com_argv[arg + 1];

	env = getenv("QGE_AGENT_STREAM_DIR");
	if (env && env[0])
		return env;
	return NULL;
}

static void QGE_GameplayOutcomeResetState(void)
{
	qge_gameplay_prev_valid = false;
	qge_gameplay_prev_leaf = -1;
	qge_gameplay_samples = 0;
	qge_gameplay_total_distance = 0.0;
	qge_gameplay_max_displacement = 0.0;
	qge_gameplay_leaf_transitions = 0;
	qge_gameplay_damage_taken_total = 0;
	qge_gameplay_damage_dealt_total = 0;
	qge_gameplay_kills_total = 0;
	qge_gameplay_pickups_total = 0;
	qge_gameplay_weapon_changes_total = 0;
	qge_gameplay_attack_presses_total = 0;
	qge_gameplay_prev_health = 0;
	qge_gameplay_prev_armor = 0;
	qge_gameplay_prev_ammo_total = 0;
	qge_gameplay_prev_items = 0;
	qge_gameplay_prev_weapon = 0;
	qge_gameplay_prev_frags = 0;
	qge_gameplay_prev_killed_monsters = 0;
	qge_gameplay_prev_attack_active = 0;
	qge_gameplay_prev_damageable_alive = 0;
}

static qboolean QGE_GameplayEnsureEdictCapacity(int capacity)
{
	float *health;
	size_t old_bytes;
	size_t new_bytes;

	if (capacity <= qge_gameplay_prev_edict_capacity)
		return true;
	if (capacity <= 0)
		return false;

	old_bytes = (size_t)qge_gameplay_prev_edict_capacity *
				sizeof(qge_gameplay_prev_edict_health[0]);
	new_bytes = (size_t)capacity *
				sizeof(qge_gameplay_prev_edict_health[0]);
	health = (float *)realloc(qge_gameplay_prev_edict_health, new_bytes);
	if (!health)
		return false;
	qge_gameplay_prev_edict_health = health;
	memset((byte *)qge_gameplay_prev_edict_health + old_bytes, 0,
		   new_bytes - old_bytes);
	qge_gameplay_prev_edict_capacity = capacity;
	return true;
}

static void QGE_GameplayOutcomeInit(void)
{
	const char *stream_dir;
	char path[MAX_OSPATH];

	if (qge_gameplay_outcome_tried)
		return;
	qge_gameplay_outcome_tried = true;

	stream_dir = QGE_GameplayStreamDir();
	if (!stream_dir || !stream_dir[0])
		return;

	q_snprintf(qge_gameplay_outcome_path, sizeof(qge_gameplay_outcome_path),
			   "%s/noesis/gameplay_outcomes.ndjson", stream_dir);
	q_strlcpy(path, qge_gameplay_outcome_path, sizeof(path));
	COM_CreatePath(path);
	qge_gameplay_outcome_file = fopen(qge_gameplay_outcome_path, "w");
	if (!qge_gameplay_outcome_file) {
		Con_Printf("QGE gameplay outcome stream: failed to open %s\n",
				   qge_gameplay_outcome_path);
		return;
	}

	QGE_GameplayOutcomeResetState();
	Con_Printf("QGE gameplay outcome stream: %s\n",
			   qge_gameplay_outcome_path);
}

static qboolean QGE_GameplayIsDamageable(edict_t *ent, int entnum)
{
	if (!ent || ent->free || entnum <= 1 || ent->v.health <= 0.0f)
		return false;
	return (((int)ent->v.flags & FL_MONSTER) ||
			ent->v.takedamage != DAMAGE_NO) ? true : false;
}

static int QGE_GameplayPlayerLeaf(edict_t *player)
{
	mleaf_t *leaf;

	if (!player || !sv.worldmodel)
		return -1;
	leaf = Mod_PointInLeaf(player->v.origin, sv.worldmodel);
	if (!leaf)
		return -1;
	return (int)(leaf - sv.worldmodel->leafs) - 1;
}

static qboolean QGE_GameplayEnemyVisible(edict_t *player, edict_t *enemy)
{
	trace_t trace;
	vec3_t start;
	vec3_t end;

	if (!player || !enemy)
		return false;

	VectorAdd(player->v.origin, player->v.view_ofs, start);
	end[0] = enemy->v.origin[0] + 0.5f * (enemy->v.mins[0] + enemy->v.maxs[0]);
	end[1] = enemy->v.origin[1] + 0.5f * (enemy->v.mins[1] + enemy->v.maxs[1]);
	end[2] = enemy->v.origin[2] + 0.5f * (enemy->v.mins[2] + enemy->v.maxs[2]);

	trace = SV_Move(start, vec3_origin, vec3_origin, end, MOVE_NOMONSTERS,
					player);
	return (!trace.allsolid && !trace.startsolid &&
			trace.fraction >= 0.99f) ? true : false;
}

static float QGE_NoesisAssistTraceDistance(edict_t *player, float yaw)
{
	trace_t trace;
	vec3_t angles;
	vec3_t forward;
	vec3_t right;
	vec3_t up;
	vec3_t start;
	vec3_t end;
	const float probe_distance = 128.0f;

	if (!player)
		return 0.0f;

	angles[0] = angles[1] = angles[2] = 0.0f;
	angles[YAW] = yaw;
	AngleVectors(angles, forward, right, up);
	VectorCopy(player->v.origin, start);
	start[2] += player->v.view_ofs[2] * 0.5f;
	VectorMA(start, probe_distance, forward, end);
	trace = SV_Move(start, player->v.mins, player->v.maxs, end,
					MOVE_NOMONSTERS, player);
	if (trace.startsolid || trace.allsolid)
		return 0.0f;
	return trace.fraction * probe_distance;
}

static edict_t *QGE_NoesisAssistFindEnemy(edict_t *player,
										  qboolean *visible_out,
										  float *distance_out)
{
	edict_t *best_visible = NULL;
	edict_t *best_nearest = NULL;
	float best_visible_distance = 999999.0f;
	float best_nearest_distance = 999999.0f;

	if (visible_out)
		*visible_out = false;
	if (distance_out)
		*distance_out = -1.0f;
	if (!player || !sv.active)
		return NULL;

	for (int i = 2; i < sv.num_edicts; i++) {
		edict_t *ent = EDICT_NUM(i);
		vec3_t delta;
		float distance;

		if (!ent || ent->free || ent->v.health <= 0.0f ||
			!((int)ent->v.flags & FL_MONSTER))
			continue;

		VectorSubtract(ent->v.origin, player->v.origin, delta);
		distance = VectorLength(delta);
		if (distance < best_nearest_distance) {
			best_nearest_distance = distance;
			best_nearest = ent;
		}
		if (QGE_GameplayEnemyVisible(player, ent) &&
			distance < best_visible_distance) {
			best_visible_distance = distance;
			best_visible = ent;
		}
	}

	if (best_visible) {
		if (visible_out)
			*visible_out = true;
		if (distance_out)
			*distance_out = best_visible_distance;
		return best_visible;
	}
	if (distance_out && best_nearest)
		*distance_out = best_nearest_distance;
	return best_nearest;
}

static void QGE_NoesisAssistResetFrame(void)
{
	qge_noesis_assist_mode = (int)qge_noesis_assist.value;
	qge_noesis_assist_active = false;
	qge_noesis_assist_target_id = 0;
	qge_noesis_assist_target_visible = false;
	qge_noesis_assist_target_distance = -1.0f;
	qge_noesis_assist_aim_pitch = 0.0f;
	qge_noesis_assist_aim_yaw = 0.0f;
	qge_noesis_assist_forwardmove = 0.0f;
	qge_noesis_assist_sidemove = 0.0f;
	qge_noesis_assist_forward_clear = -1.0f;
	qge_noesis_assist_left_clear = -1.0f;
	qge_noesis_assist_right_clear = -1.0f;
}

void QGE_NoesisAssistClientThink(client_t *client,
								 edict_t *player,
								 usercmd_t *move)
{
	edict_t *enemy;
	vec3_t eye;
	vec3_t target;
	vec3_t delta;
	vec3_t aim;
	qboolean visible = false;
	float distance = -1.0f;
	float forward_clear;
	float left_clear;
	float right_clear;
	int chase_mode;

	(void)client;
	if (!qge_initialized || qge_noesis_assist.value < 0.5f ||
		!move || !player || player->free || player->v.health <= 0.0f ||
		!sv.active || !QGE_GameplayStreamDir())
		return;

	enemy = QGE_NoesisAssistFindEnemy(player, &visible, &distance);
	if (!enemy)
		return;

	VectorAdd(player->v.origin, player->v.view_ofs, eye);
	target[0] = enemy->v.origin[0] +
				0.5f * (enemy->v.mins[0] + enemy->v.maxs[0]);
	target[1] = enemy->v.origin[1] +
				0.5f * (enemy->v.mins[1] + enemy->v.maxs[1]);
	target[2] = enemy->v.origin[2] +
				0.5f * (enemy->v.mins[2] + enemy->v.maxs[2]);
	VectorSubtract(target, eye, delta);
	VectorAngles(delta, aim);
	aim[PITCH] = q_max(-60.0f, q_min(60.0f, aim[PITCH]));
	aim[YAW] = anglemod(aim[YAW]);
	aim[ROLL] = 0.0f;

	VectorCopy(aim, player->v.v_angle);
	player->v.angles[PITCH] = -aim[PITCH] / 3.0f;
	player->v.angles[YAW] = aim[YAW];
	player->v.angles[ROLL] = 0.0f;
	player->v.fixangle = 1.0f;

	chase_mode = qge_noesis_assist.value >= 1.5f ? 1 : 0;
	forward_clear = left_clear = right_clear = -1.0f;
	if (chase_mode) {
		move->forwardmove = visible && distance < 384.0f ? 120.0f : 400.0f;
		move->sidemove = 0.0f;
		move->upmove = 0.0f;

		forward_clear = QGE_NoesisAssistTraceDistance(player, aim[YAW]);
		left_clear = QGE_NoesisAssistTraceDistance(player,
												   anglemod(aim[YAW] + 45.0f));
		right_clear = QGE_NoesisAssistTraceDistance(player,
													anglemod(aim[YAW] - 45.0f));
		if (forward_clear < 56.0f) {
			move->sidemove = left_clear >= right_clear ? 320.0f : -320.0f;
			move->forwardmove = 180.0f;
		}
		else if (visible && distance < 512.0f) {
			move->sidemove = (qge_frame_count & 8) ? 220.0f : -220.0f;
		}
	}

	if (visible && distance <= 1024.0f) {
		player->v.button0 = 1.0f;
	}
	else if (chase_mode) {
		player->v.button0 = 0.0f;
	}

	qge_noesis_assist_mode = chase_mode ? 2 : 1;
	qge_noesis_assist_active = true;
	qge_noesis_assist_target_id = NUM_FOR_EDICT(enemy);
	qge_noesis_assist_target_visible = visible;
	qge_noesis_assist_target_distance = distance;
	qge_noesis_assist_aim_pitch = aim[PITCH];
	qge_noesis_assist_aim_yaw = aim[YAW];
	qge_noesis_assist_forwardmove = move->forwardmove;
	qge_noesis_assist_sidemove = move->sidemove;
	qge_noesis_assist_forward_clear = forward_clear;
	qge_noesis_assist_left_clear = left_clear;
	qge_noesis_assist_right_clear = right_clear;

	if (quantum_debug.value >= 1.0f &&
		qge_frame_count - qge_noesis_assist_last_log_frame >= 30) {
		qge_noesis_assist_last_log_frame = qge_frame_count;
		Con_Printf("QGE noesis assist frame=%d mode=%d target=%d "
				   "visible=%d distance=%.1f fmove=%.1f smove=%.1f\n",
				   qge_frame_count, chase_mode ? 2 : 1,
				   NUM_FOR_EDICT(enemy), visible ? 1 : 0, distance,
				   move->forwardmove, move->sidemove);
	}
}

static void QGE_GameplayOutcomeSample(void)
{
	edict_t *player;
	vec3_t delta;
	vec3_t from_start;
	double frame_distance = 0.0;
	double displacement = 0.0;
	int health, armor, ammo, shells, nails, rockets, cells;
	int items, weapon, frags, killed_monsters;
	int leaf, damage_taken_delta, damage_dealt_delta, kills_delta;
	int pickup_delta, item_bits_added, weapon_changed_delta;
	int attack_active, attack_press_delta;
	int ammo_total, combined, prev_combined;
	int damageable_alive = 0;
	int visible_enemy_count = 0;
	int nearest_enemy_id = 0;
	int nearest_enemy_visible = 0;
	float nearest_enemy_distance = -1.0f;
	float damageable_health;

	if (!qge_initialized)
		return;
	QGE_GameplayOutcomeInit();
	if (!qge_gameplay_outcome_file)
		return;
	if (!sv.active || sv.num_edicts <= 1)
		return;

	player = EDICT_NUM(1);
	if (!player || player->free) {
		QGE_GameplayOutcomeResetState();
		return;
	}
	if (strcmp(qge_gameplay_map, sv.name) != 0) {
		q_strlcpy(qge_gameplay_map, sv.name, sizeof(qge_gameplay_map));
		QGE_GameplayOutcomeResetState();
	}

	health = (int)player->v.health;
	armor = (int)player->v.armorvalue;
	ammo = (int)player->v.currentammo;
	shells = (int)player->v.ammo_shells;
	nails = (int)player->v.ammo_nails;
	rockets = (int)player->v.ammo_rockets;
	cells = (int)player->v.ammo_cells;
	items = (int)player->v.items;
	weapon = (int)player->v.weapon;
	frags = (int)player->v.frags;
	if (!qge_gameplay_prev_valid && health <= 0 && items == 0 &&
		weapon == 0)
		return;
	if (!QGE_GameplayEnsureEdictCapacity(sv.max_edicts + 1))
		return;

	killed_monsters = pr_global_struct ?
		(int)pr_global_struct->killed_monsters : 0;
	leaf = QGE_GameplayPlayerLeaf(player);
	ammo_total = shells + nails + rockets + cells;
	attack_active = player->v.button0 != 0.0f ? 1 : 0;

	damage_dealt_delta = 0;
	for (int i = 2; i < sv.num_edicts; i++) {
		edict_t *ent = EDICT_NUM(i);
		if (!QGE_GameplayIsDamageable(ent, i)) {
			if (i < qge_gameplay_prev_edict_capacity)
				qge_gameplay_prev_edict_health[i] = 0.0f;
			continue;
		}

		damageable_alive++;
		damageable_health = ent->v.health;
		if (qge_gameplay_prev_valid &&
			i < qge_gameplay_prev_edict_capacity &&
			qge_gameplay_prev_edict_health[i] > damageable_health)
			damage_dealt_delta +=
				(int)(qge_gameplay_prev_edict_health[i] -
					  damageable_health + 0.5f);
		qge_gameplay_prev_edict_health[i] = damageable_health;

		if (((int)ent->v.flags & FL_MONSTER) && ent->v.health > 0.0f) {
			float dist;

			VectorSubtract(ent->v.origin, player->v.origin, delta);
			dist = VectorLength(delta);
			if (nearest_enemy_distance < 0.0f ||
				dist < nearest_enemy_distance) {
				nearest_enemy_distance = dist;
				nearest_enemy_id = i;
				nearest_enemy_visible =
					QGE_GameplayEnemyVisible(player, ent) ? 1 : 0;
			}
			if (QGE_GameplayEnemyVisible(player, ent))
				visible_enemy_count++;
		}
	}

	damage_taken_delta = 0;
	pickup_delta = 0;
	item_bits_added = 0;
	weapon_changed_delta = 0;
	attack_press_delta = 0;
	kills_delta = 0;
	if (qge_gameplay_prev_valid) {
		VectorSubtract(player->v.origin, qge_gameplay_prev_origin, delta);
		frame_distance = VectorLength(delta);
		qge_gameplay_total_distance += frame_distance;
		if (leaf >= 0 && qge_gameplay_prev_leaf >= 0 &&
			leaf != qge_gameplay_prev_leaf)
			qge_gameplay_leaf_transitions++;

		prev_combined = qge_gameplay_prev_health + qge_gameplay_prev_armor;
		combined = health + armor;
		if (combined < prev_combined)
			damage_taken_delta = prev_combined - combined;
		if (health > qge_gameplay_prev_health ||
			armor > qge_gameplay_prev_armor ||
			ammo_total > qge_gameplay_prev_ammo_total ||
			(items & ~qge_gameplay_prev_items) != 0) {
			pickup_delta = 1;
			qge_gameplay_pickups_total++;
		}
		item_bits_added = items & ~qge_gameplay_prev_items;
		if (weapon != qge_gameplay_prev_weapon) {
			weapon_changed_delta = 1;
			qge_gameplay_weapon_changes_total++;
		}
		if (attack_active && !qge_gameplay_prev_attack_active) {
			attack_press_delta = 1;
			qge_gameplay_attack_presses_total++;
		}
		if (killed_monsters > qge_gameplay_prev_killed_monsters)
			kills_delta = killed_monsters - qge_gameplay_prev_killed_monsters;
		else if (damageable_alive < qge_gameplay_prev_damageable_alive)
			kills_delta = qge_gameplay_prev_damageable_alive -
						  damageable_alive;
	}
	else {
		VectorCopy(player->v.origin, qge_gameplay_start_origin);
	}

	VectorSubtract(player->v.origin, qge_gameplay_start_origin, from_start);
	displacement = VectorLength(from_start);
	if (displacement > qge_gameplay_max_displacement)
		qge_gameplay_max_displacement = displacement;

	qge_gameplay_damage_taken_total += damage_taken_delta;
	qge_gameplay_damage_dealt_total += damage_dealt_delta;
	qge_gameplay_kills_total += kills_delta;
	qge_gameplay_samples++;

	fprintf(qge_gameplay_outcome_file,
		"{\"schema\":\"qge.gameplay_outcome.v0\",\"type\":\"sample\","
		"\"frame\":%d,\"time_msec\":%d,\"map\":\"%s\","
		"\"player\":{\"health\":%d,\"armor\":%d,\"armortype\":%.3f,"
		"\"ammo\":%d,\"shells\":%d,\"nails\":%d,\"rockets\":%d,"
		"\"cells\":%d,\"items\":%d,\"weapon\":%d,\"frags\":%d,"
		"\"origin\":[%.3f,%.3f,%.3f],"
		"\"angles\":[%.3f,%.3f,%.3f],"
		"\"v_angle\":[%.3f,%.3f,%.3f],"
		"\"onground\":%s,\"attack_active\":%s},"
		"\"route\":{\"leaf\":%d,\"frame_distance\":%.3f,"
		"\"total_distance\":%.3f,\"displacement_from_start\":%.3f,"
		"\"max_displacement_from_start\":%.3f,"
		"\"leaf_transition_count\":%d},"
		"\"combat\":{\"damage_taken_delta\":%d,"
		"\"damage_taken_total\":%d,"
		"\"damage_dealt_inferred_delta\":%d,"
		"\"damage_dealt_inferred_total\":%d,"
		"\"kills_delta\":%d,\"kills_total\":%d,"
		"\"killed_monsters\":%d,\"damageable_alive\":%d,"
		"\"nearest_enemy_id\":%d,\"nearest_enemy_distance\":%.3f,"
		"\"nearest_enemy_visible\":%s,\"visible_enemy_count\":%d,"
		"\"attack_press_delta\":%d,\"attack_presses_total\":%d},"
		"\"assist\":{\"mode\":%d,\"active\":%s,\"target_id\":%d,"
		"\"target_visible\":%s,\"target_distance\":%.3f,"
		"\"aim_pitch\":%.3f,\"aim_yaw\":%.3f,"
		"\"forwardmove\":%.3f,\"sidemove\":%.3f,"
		"\"forward_clear\":%.3f,\"left_clear\":%.3f,"
		"\"right_clear\":%.3f},"
		"\"pickup\":{\"pickup_delta\":%d,\"pickups_total\":%d,"
		"\"item_bits_added\":%d,\"weapon_changed_delta\":%d,"
		"\"weapon_changes_total\":%d}}\n",
		qge_frame_count, QGE_ServerTimeMsec(), sv.name,
		health, armor, player->v.armortype,
		ammo, shells, nails, rockets, cells, items, weapon, frags,
		player->v.origin[0], player->v.origin[1], player->v.origin[2],
		player->v.angles[0], player->v.angles[1], player->v.angles[2],
		player->v.v_angle[0], player->v.v_angle[1], player->v.v_angle[2],
		((int)player->v.flags & FL_ONGROUND) ? "true" : "false",
		attack_active ? "true" : "false",
		leaf, frame_distance, qge_gameplay_total_distance, displacement,
		qge_gameplay_max_displacement, qge_gameplay_leaf_transitions,
		damage_taken_delta, qge_gameplay_damage_taken_total,
		damage_dealt_delta, qge_gameplay_damage_dealt_total,
		kills_delta, qge_gameplay_kills_total,
		killed_monsters, damageable_alive, nearest_enemy_id,
		nearest_enemy_distance,
		nearest_enemy_visible ? "true" : "false", visible_enemy_count,
		attack_press_delta, qge_gameplay_attack_presses_total,
		qge_noesis_assist_mode,
		qge_noesis_assist_active ? "true" : "false",
		qge_noesis_assist_target_id,
		qge_noesis_assist_target_visible ? "true" : "false",
		qge_noesis_assist_target_distance,
		qge_noesis_assist_aim_pitch, qge_noesis_assist_aim_yaw,
		qge_noesis_assist_forwardmove, qge_noesis_assist_sidemove,
		qge_noesis_assist_forward_clear, qge_noesis_assist_left_clear,
		qge_noesis_assist_right_clear,
		pickup_delta, qge_gameplay_pickups_total, item_bits_added,
		weapon_changed_delta, qge_gameplay_weapon_changes_total);

	if (damage_taken_delta > 0)
		fprintf(qge_gameplay_outcome_file,
			"{\"schema\":\"qge.gameplay_outcome.v0\",\"type\":\"event\","
			"\"kind\":\"damage_taken\",\"frame\":%d,\"amount\":%d,"
			"\"total\":%d}\n",
			qge_frame_count, damage_taken_delta,
			qge_gameplay_damage_taken_total);
	if (damage_dealt_delta > 0)
		fprintf(qge_gameplay_outcome_file,
			"{\"schema\":\"qge.gameplay_outcome.v0\",\"type\":\"event\","
			"\"kind\":\"damage_dealt_inferred\",\"frame\":%d,"
			"\"amount\":%d,\"total\":%d}\n",
			qge_frame_count, damage_dealt_delta,
			qge_gameplay_damage_dealt_total);
	if (kills_delta > 0)
		fprintf(qge_gameplay_outcome_file,
			"{\"schema\":\"qge.gameplay_outcome.v0\",\"type\":\"event\","
			"\"kind\":\"kill_inferred\",\"frame\":%d,\"count\":%d,"
			"\"total\":%d}\n",
			qge_frame_count, kills_delta, qge_gameplay_kills_total);
	if (pickup_delta > 0)
		fprintf(qge_gameplay_outcome_file,
			"{\"schema\":\"qge.gameplay_outcome.v0\",\"type\":\"event\","
			"\"kind\":\"pickup_inferred\",\"frame\":%d,"
			"\"item_bits_added\":%d,\"total\":%d}\n",
			qge_frame_count, item_bits_added, qge_gameplay_pickups_total);
	if (weapon_changed_delta > 0)
		fprintf(qge_gameplay_outcome_file,
			"{\"schema\":\"qge.gameplay_outcome.v0\",\"type\":\"event\","
			"\"kind\":\"weapon_changed\",\"frame\":%d,"
			"\"weapon\":%d,\"total\":%d}\n",
			qge_frame_count, weapon, qge_gameplay_weapon_changes_total);
	fflush(qge_gameplay_outcome_file);

	VectorCopy(player->v.origin, qge_gameplay_prev_origin);
	qge_gameplay_prev_leaf = leaf;
	qge_gameplay_prev_health = health;
	qge_gameplay_prev_armor = armor;
	qge_gameplay_prev_ammo_total = ammo_total;
	qge_gameplay_prev_items = items;
	qge_gameplay_prev_weapon = weapon;
	qge_gameplay_prev_frags = frags;
	qge_gameplay_prev_killed_monsters = killed_monsters;
	qge_gameplay_prev_attack_active = attack_active;
	qge_gameplay_prev_damageable_alive = damageable_alive;
	qge_gameplay_prev_valid = true;
}

static void QGE_GameplayOutcomeShutdown(void)
{
	if (qge_gameplay_outcome_file) {
		fclose(qge_gameplay_outcome_file);
		qge_gameplay_outcome_file = NULL;
	}
	free(qge_gameplay_prev_edict_health);
	qge_gameplay_prev_edict_health = NULL;
	qge_gameplay_prev_edict_capacity = 0;
	qge_gameplay_outcome_tried = false;
	qge_gameplay_outcome_path[0] = 0;
	qge_gameplay_map[0] = 0;
	QGE_GameplayOutcomeResetState();
}

static void QGE_TraceBackendGate(const char *phase)
{
	qge_quantum_runtime_t *rt;
	qge_state_probe_t probe;
	qge_profile_t profile;
	qge_backend_t backend;
	uint32_t flags;
	int active;
	int native_available;
	const char *backend_name;
	const char *status;
	const char *reason;
	const char *probe_reason;
	const char *runtime_path;

	if (!qge_ctx)
		return;
	if (!phase || !phase[0])
		phase = "runtime";

	rt = QGE_Runtime();
	backend = qge_get_backend(qge_ctx);
	flags = qge_context_backend_flags(qge_ctx);
	active = qge_context_has_active_acceleration(qge_ctx) ? 1 : 0;
	native_available = qge_context_backend_native_available(qge_ctx) ? 1 : 0;
	backend_name = qge_backend_name(backend);
	status = qge_context_acceleration_status(qge_ctx);
	reason = qge_context_backend_reason(qge_ctx);
	probe_reason = qge_context_backend_probe_reason(qge_ctx);
	runtime_path = qge_context_backend_runtime_path(qge_ctx);
	memset(&profile, 0, sizeof(profile));
	qge_get_profile(qge_ctx, &profile);

	Con_Printf("QGE: Backend gate phase=%s backend=%s status=%s native=%d active=%d flags=0x%x path=%s reason=%s probe=%s\n",
			   phase, backend_name, status, native_available, active, flags, runtime_path, reason, probe_reason);
	fprintf(stderr, "QGE backend gate phase=%s backend=%s status=%s native=%d active=%d flags=0x%x path=%s reason=%s probe=%s qubits=%d memory=%llu\n",
			phase, backend_name, status, native_available, active, flags, runtime_path, reason, probe_reason, profile.current_qubits,
			(unsigned long long)profile.memory_used_bytes);

	if (!rt)
		return;

	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_RENDER;
	probe.representation = QGE_REP_CLASSICAL_ORACLE;
	probe.subject_id = (int32_t)backend;
	probe.flags = flags;
	probe.state_hash = ((uint64_t)backend << 32) ^ (uint64_t)flags;
	probe.entropy = qge_backend_is_accelerated(backend) ? 1.0 : 0.0;
	probe.coherence = active ? 1.0 : 0.0;
	probe.max_probability = native_available ? 1.0 : 0.0;
	probe.total_probability = 1.0;
	probe.active_basis_count = native_available + active;
	probe.qubit_count = profile.current_qubits;
	probe.memory_bytes = profile.memory_used_bytes;
	strlcpy(probe.label, "backend_gate", sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);
}

static float QGE_ClampUnit(float value)
{
	if (value < 0.0f)
		return 0.0f;
	if (value > 1.0f)
		return 1.0f;
	return value;
}

static int QGE_RenderGateShotCount(void)
{
	int shots = (int)(quantum_render_gate_shots.value + 0.5f);

	if (shots < 8)
		shots = 8;
	if (shots > 256)
		shots = 256;
	return shots;
}

static uint64_t QGE_RenderGateAnalyzeState(const quantum_state_t *state,
										   int *active_basis,
										   float *basis_entropy,
										   float *max_probability,
										   double *total_probability)
{
	uint64_t hash = 1469598103934665603ULL;
	int active = 0;
	double entropy = 0.0;
	double total = 0.0;
	double max_prob = 0.0;

	if (!state)
		return hash;

	for (uint64_t i = 0; i < (uint64_t)state->state_dim; i++) {
		double p = quantum_state_get_probability(state, i);
		uint64_t bucket;

		if (!isfinite(p) || p < 0.0)
			p = 0.0;
		total += p;
		if (p > 1.0e-9)
			active++;
		if (p > max_prob)
			max_prob = p;
		if (p > 1.0e-12)
			entropy -= p * (log(p) / log(2.0));

		bucket = (uint64_t)(p * 1000000000.0 + 0.5);
		hash ^= i + 0x9e3779b97f4a7c15ULL;
		hash *= 1099511628211ULL;
		hash ^= bucket;
		hash *= 1099511628211ULL;
	}

	if (active_basis)
		*active_basis = active;
	if (basis_entropy)
		*basis_entropy = (float)entropy;
	if (max_probability)
		*max_probability = (float)max_prob;
	if (total_probability)
		*total_probability = total;
	return hash;
}

static void QGE_ResetRenderGateTelemetry(void)
{
	qge_render_gate_shots = 0;
	qge_render_gate_readout_ones = 0;
	qge_render_gate_edge_ones = 0;
	qge_render_gate_total = 0;
	qge_render_gate_h = 0;
	qge_render_gate_ry = 0;
	qge_render_gate_rz = 0;
	qge_render_gate_entangling = 0;
	qge_render_gate_phase_count = 0;
	qge_render_gate_errors = 0;
	qge_render_gate_active_basis = 0;
	qge_render_gate_gain = 1.0f;
	qge_render_gate_edge_gain = 1.0f;
	qge_render_gate_material_gain = 1.0f;
	qge_render_gate_color_gain[QGE_DWT_R] = 1.0f;
	qge_render_gate_color_gain[QGE_DWT_G] = 1.0f;
	qge_render_gate_color_gain[QGE_DWT_B] = 1.0f;
	qge_render_gate_probability = 0.5f;
	qge_render_gate_edge_observable = 0.5f;
	qge_render_gate_coherence = 0.0f;
	qge_render_gate_entropy = 0.0f;
	qge_render_gate_max_probability = 1.0f;
	qge_render_gate_majority_basis = 0;
	qge_render_gate_state_hash = 0;
}

static void QGE_RenderGateRecordMeasurements(qge_quantum_runtime_t *rt,
											 const double probabilities[QGE_RENDER_GATE_QUBITS])
{
	for (int q = 0; q < QGE_RENDER_GATE_QUBITS; q++) {
		qge_measurement_event_t event;

		memset(&event, 0, sizeof(event));
		event.frame = qge_frame_count;
		event.server_time_msec = QGE_ServerTimeMsec();
		event.domain = QGE_DOMAIN_RENDER;
		event.kind = QGE_MEASURE_RENDER_SAMPLE;
		event.boundary = QGE_OBSERVE_FRAME_BOUNDARY;
		event.subject_id = q;
		event.flags = QGE_RENDER_GATE_FLAG_ACTIVE;
		event.basis_index = qge_render_gate_majority_basis;
		event.probability = probabilities[q];
		event.phase = qge_render_gate_coherence;
		event.entropy_offset = (uint64_t)qge_render_gate_shots;
		event.trace_id = qge_render_gate_state_hash ^ (uint64_t)q;
		qge_quantum_record_measurement(rt, &event);
	}
}

static void QGE_RecordRenderGateProbe(qge_quantum_runtime_t *rt)
{
	qge_state_probe_t probe;

	if (!rt)
		return;

	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_RENDER;
	probe.representation = QGE_REP_DENSE_STATE;
	probe.active_basis_count = qge_render_gate_active_basis;
	probe.qubit_count = QGE_RENDER_GATE_QUBITS;
	probe.memory_bytes = (uint64_t)qge_render_gate_state.state_dim *
						 (uint64_t)sizeof(complex_t);
	probe.subject_id = qge_render_gate_total;
	probe.flags = QGE_RENDER_GATE_FLAG_ACTIVE |
				  (qge_render_gate_errors ? QGE_RENDER_GATE_FLAG_ERROR : 0u);
	probe.state_hash = qge_render_gate_state_hash;
	probe.entropy = qge_render_gate_entropy;
	probe.coherence = qge_render_gate_coherence;
	probe.max_probability = qge_render_gate_max_probability;
	probe.total_probability = (double)qge_render_gate_shots;
	strlcpy(probe.label, "render_gate_kernel", sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);
}

QGE_HOT_INLINE uint64_t QGE_RenderGateNextShotEntropy(uint64_t *state)
{
	uint64_t value;

	if (!state)
		return 0;
	*state += 0x9e3779b97f4a7c15ULL;
	value = *state;
	value = (value ^ (value >> 30)) * 0xbf58476d1ce4e5b9ULL;
	value = (value ^ (value >> 27)) * 0x94d049bb133111ebULL;
	return value ^ (value >> 31);
}

static uint64_t QGE_RenderGateSampleBasis(uint64_t raw)
{
	double sample = (double)(raw >> 11) * (1.0 / 9007199254740992.0);
	double cumulative = 0.0;

	for (uint64_t basis = 0; basis < (uint64_t)qge_render_gate_state.state_dim;
		 basis++) {
		double p = quantum_state_get_probability(&qge_render_gate_state, basis);

		if (!isfinite(p) || p < 0.0)
			p = 0.0;
		cumulative += p;
		if (sample <= cumulative)
			return basis;
	}
	return qge_render_gate_state.state_dim > 0 ?
		   (uint64_t)qge_render_gate_state.state_dim - 1u : 0u;
}

/* Bounded reviewer-facing simulated QPU workload: scene/material/light
 * statistics are angle-encoded into a 6-qubit Moonlab state, entangling gates
 * mix feature and readout qubits, and finite-shot measurements produce an edge
 * preservation observable used by the sparse-DWT renderer. */
static void QGE_RunRenderGateKernel(const qge_frame_snapshot_t *snapshot)
{
	qge_quantum_runtime_t *rt;
	float surface_ratio;
	float light_avg = 0.0f;
	float contrast_avg = 0.0f;
	float material_avg = 0.0f;
	float entity_ratio;
	float special_ratio = 0.0f;
	double shot_probabilities[QGE_RENDER_GATE_QUBITS] = {0.0};
	int basis_counts[QGE_RENDER_GATE_DIM];
	int surface_count = qge_scene_surface_count;
	int entity_count = snapshot ? (int)snapshot->edict_count : 0;
	int special_count = 0;
	qs_error_t err = QS_SUCCESS;

	QGE_ResetRenderGateTelemetry();
	if (!qge_render_gate_initialized || quantum_render_gate_kernel.value < 0.5f)
		return;

	if (surface_count > 0) {
		double light_sum = 0.0;
		double contrast_sum = 0.0;
		double material_sum = 0.0;

		for (int i = 0; i < surface_count; i++) {
			light_sum += qge_scene_surfaces[i].light_energy;
			contrast_sum += qge_scene_surfaces[i].light_contrast;
			material_sum += qge_scene_surfaces[i].material_signal;
			if (qge_scene_surfaces[i].has_warp ||
				qge_scene_surfaces[i].has_fullbright ||
				(qge_scene_surfaces[i].flags &
				 (SURF_DRAWWATER | SURF_DRAWLAVA | SURF_DRAWTELE | SURF_DRAWSKY)))
				special_count++;
		}
		light_avg = QGE_ClampUnit((float)(light_sum / (double)surface_count));
		contrast_avg = QGE_ClampUnit((float)(contrast_sum / (double)surface_count));
		material_avg = QGE_ClampUnit((float)(material_sum / (double)surface_count));
		special_ratio = QGE_ClampUnit((float)special_count / (float)surface_count);
	}

	surface_ratio = QGE_ClampUnit((float)surface_count / 512.0f);
	entity_ratio = QGE_ClampUnit((float)entity_count / 64.0f);

	quantum_state_reset(&qge_render_gate_state);

#define QGE_GATE_CALL(expr, counter) \
	do { \
		qs_error_t qge_gate_err = (expr); \
		qge_render_gate_total++; \
		(counter)++; \
		if (qge_gate_err != QS_SUCCESS) \
			err = qge_gate_err; \
	} while (0)

	for (int q = 0; q < QGE_RENDER_GATE_QUBITS; q++)
		QGE_GATE_CALL(gate_hadamard(&qge_render_gate_state, q),
					  qge_render_gate_h);
	QGE_GATE_CALL(gate_ry(&qge_render_gate_state, 0,
						  (double)surface_ratio * M_PI * 0.85),
				  qge_render_gate_ry);
	QGE_GATE_CALL(gate_ry(&qge_render_gate_state, 1,
						  (double)light_avg * M_PI * 0.70),
				  qge_render_gate_ry);
	QGE_GATE_CALL(gate_ry(&qge_render_gate_state, 2,
						  (double)material_avg * M_PI * 0.75),
				  qge_render_gate_ry);
	QGE_GATE_CALL(gate_ry(&qge_render_gate_state, 3,
						  (double)entity_ratio * M_PI * 0.55),
				  qge_render_gate_ry);
	QGE_GATE_CALL(gate_ry(&qge_render_gate_state, 4,
						  (double)contrast_avg * M_PI * 0.80),
				  qge_render_gate_ry);
	QGE_GATE_CALL(gate_ry(&qge_render_gate_state, 5,
						  (double)special_ratio * M_PI * 0.65),
				  qge_render_gate_ry);
	QGE_GATE_CALL(gate_rz(&qge_render_gate_state, 1,
						  (double)(light_avg - surface_ratio) * M_PI * 0.35),
				  qge_render_gate_rz);
	QGE_GATE_CALL(gate_rz(&qge_render_gate_state, 2,
						  (double)(material_avg - light_avg) * M_PI * 0.45),
				  qge_render_gate_rz);
	QGE_GATE_CALL(gate_rz(&qge_render_gate_state, 4,
						  (double)(contrast_avg + special_ratio) * M_PI * 0.30),
				  qge_render_gate_rz);
	QGE_GATE_CALL(gate_cnot(&qge_render_gate_state, 0, 4),
				  qge_render_gate_entangling);
	QGE_GATE_CALL(gate_cnot(&qge_render_gate_state, 1, 4),
				  qge_render_gate_entangling);
	QGE_GATE_CALL(gate_cnot(&qge_render_gate_state, 2, 5),
				  qge_render_gate_entangling);
	QGE_GATE_CALL(gate_cnot(&qge_render_gate_state, 3, 5),
				  qge_render_gate_entangling);
	QGE_GATE_CALL(gate_cnot(&qge_render_gate_state, 4, 5),
				  qge_render_gate_entangling);
	QGE_GATE_CALL(gate_cz(&qge_render_gate_state, 0, 5),
				  qge_render_gate_entangling);
	QGE_GATE_CALL(gate_phase(&qge_render_gate_state, 4,
							 ((double)contrast_avg + (double)material_avg -
							  (double)light_avg) * M_PI * 0.25),
				  qge_render_gate_phase_count);
	QGE_GATE_CALL(gate_ry(&qge_render_gate_state, 4,
						  (double)(contrast_avg + material_avg) * M_PI * 0.25),
				  qge_render_gate_ry);
	QGE_GATE_CALL(gate_ry(&qge_render_gate_state, 5,
						  (double)(entity_ratio + special_ratio) * M_PI * 0.25),
				  qge_render_gate_ry);
	QGE_GATE_CALL(gate_hadamard(&qge_render_gate_state, 4),
				  qge_render_gate_h);
	QGE_GATE_CALL(gate_hadamard(&qge_render_gate_state, 5),
				  qge_render_gate_h);

#undef QGE_GATE_CALL

	if (err != QS_SUCCESS) {
		qge_render_gate_errors++;
		QGE_ResetRenderGateTelemetry();
		qge_render_gate_errors = 1;
		return;
	}

	qge_render_gate_shots = QGE_RenderGateShotCount();
	memset(basis_counts, 0, sizeof(basis_counts));
	rt = QGE_Runtime();
	uint64_t shot_state = qge_quantum_entropy_u64(rt, QGE_DOMAIN_RENDER,
												  qge_frame_count);
	for (int shot = 0; shot < qge_render_gate_shots; shot++) {
		uint64_t basis = QGE_RenderGateSampleBasis(
			QGE_RenderGateNextShotEntropy(&shot_state));

		if (basis < QGE_RENDER_GATE_DIM)
			basis_counts[basis]++;
		for (int q = 0; q < QGE_RENDER_GATE_QUBITS; q++) {
			if (basis & (1u << q))
				shot_probabilities[q] += 1.0;
		}
		if (basis & (1u << 4))
			qge_render_gate_edge_ones++;
		if (basis & (1u << 5))
			qge_render_gate_readout_ones++;
	}
	if (qge_render_gate_shots > 0) {
		for (int q = 0; q < QGE_RENDER_GATE_QUBITS; q++)
			shot_probabilities[q] /= (double)qge_render_gate_shots;
		for (int basis = 1; basis < QGE_RENDER_GATE_DIM; basis++) {
			if (basis_counts[basis] >
				basis_counts[(int)qge_render_gate_majority_basis])
				qge_render_gate_majority_basis = (uint64_t)basis;
		}
	}

	qge_render_gate_coherence =
		(float)fabs(measurement_expectation_x(&qge_render_gate_state, 5));
	qge_render_gate_probability = (float)shot_probabilities[5];
	qge_render_gate_edge_observable = (float)shot_probabilities[4];
	qge_render_gate_gain = 0.94f + 0.12f * qge_render_gate_probability;
	qge_render_gate_edge_gain = 0.70f + 0.85f * qge_render_gate_edge_observable;
	qge_render_gate_material_gain = 0.85f + 0.30f * qge_render_gate_edge_observable;
	qge_render_gate_color_gain[QGE_DWT_R] = 0.94f + 0.10f * (float)shot_probabilities[0];
	qge_render_gate_color_gain[QGE_DWT_G] = 0.94f + 0.10f * (float)shot_probabilities[1];
	qge_render_gate_color_gain[QGE_DWT_B] = 0.94f + 0.10f * (float)shot_probabilities[2];
	qge_render_gate_state_hash = QGE_RenderGateAnalyzeState(
		&qge_render_gate_state,
		&qge_render_gate_active_basis,
		&qge_render_gate_entropy,
		&qge_render_gate_max_probability,
		NULL);

	QGE_RenderGateRecordMeasurements(rt, shot_probabilities);
	QGE_RecordRenderGateProbe(rt);
}

static int QGE_ClampRenderResolution(float requested)
{
	int value = (int)(requested + 0.5f);

	if (value <= 96)
		return 64;
	if (value <= 192)
		return 128;
	if (value <= 384)
		return 256;
	if (value <= 768)
		return 512;
	return 1024;
}

static uint64_t QGE_RegistryHashStep(uint64_t hash, uint64_t value)
{
	hash ^= value;
	hash *= 1099511628211ULL;
	return hash;
}

static uint64_t QGE_RegistryHashString(const char *text)
{
	uint64_t hash = 1469598103934665603ULL;

	if (!text)
		return hash;
	while (*text)
		hash = QGE_RegistryHashStep(hash, (unsigned char)*text++);
	return hash;
}

static qge_vec3_t QGE_RegistryVec3(const float v[3])
{
	qge_vec3_t out;
	out.x = v ? v[0] : 0.0f;
	out.y = v ? v[1] : 0.0f;
	out.z = v ? v[2] : 0.0f;
	return out;
}

static qge_vec3_t QGE_RegistryMinmaxMin(const float minmaxs[6])
{
	qge_vec3_t out;
	out.x = minmaxs ? minmaxs[0] : 0.0f;
	out.y = minmaxs ? minmaxs[1] : 0.0f;
	out.z = minmaxs ? minmaxs[2] : 0.0f;
	return out;
}

static qge_vec3_t QGE_RegistryMinmaxMax(const float minmaxs[6])
{
	qge_vec3_t out;
	out.x = minmaxs ? minmaxs[3] : 0.0f;
	out.y = minmaxs ? minmaxs[4] : 0.0f;
	out.z = minmaxs ? minmaxs[5] : 0.0f;
	return out;
}

static void QGE_TraceWorldRegistryProbe(const qge_world_stats_t *stats)
{
	qge_quantum_runtime_t *rt;
	qge_state_probe_t probe;
	uint64_t hash;

	if (!stats)
		return;
	rt = QGE_Runtime();
	if (!rt)
		return;

	hash = stats->map_hash;
	hash = QGE_RegistryHashStep(hash, stats->current_world_id);
	hash = QGE_RegistryHashStep(hash, stats->map_revision);
	hash = QGE_RegistryHashStep(hash, stats->total_resources);
	hash = QGE_RegistryHashStep(hash, stats->model_count);
	hash = QGE_RegistryHashStep(hash, stats->plane_count);
	hash = QGE_RegistryHashStep(hash, stats->node_count);
	hash = QGE_RegistryHashStep(hash, stats->leaf_count);
	hash = QGE_RegistryHashStep(hash, stats->surface_count);
	hash = QGE_RegistryHashStep(hash, stats->texture_count);
	hash = QGE_RegistryHashStep(hash, stats->lightmap_count);
	hash = QGE_RegistryHashStep(hash, stats->alias_model_count);
	hash = QGE_RegistryHashStep(hash, stats->sprite_count);
	hash = QGE_RegistryHashStep(hash, stats->sound_count);
	hash = QGE_RegistryHashStep(hash, stats->hud_image_count);

	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_MATERIAL;
	probe.representation = QGE_REP_CLASSICAL_ORACLE;
	probe.subject_id = (int32_t)stats->current_world_id;
	probe.flags = stats->map_revision;
	probe.state_hash = hash;
	probe.coherence = qge_resource_id_is_valid(stats->current_world_id) ? 1.0 : 0.0;
	probe.max_probability = (double)stats->surface_count;
	probe.total_probability = (double)stats->total_resources;
	probe.active_basis_count = (int32_t)stats->total_resources;
	probe.qubit_count =
		qge_quantum_qubits_for_basis_count(stats->total_resources);
	probe.memory_bytes = (uint64_t)stats->total_resources * sizeof(qge_resource_id_t);
	strlcpy(probe.label, "world_registry", sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);
}

static qge_model_type_t QGE_RegistryModelType(const qmodel_t *model)
{
	if (!model)
		return QGE_MODEL_UNKNOWN;
	switch (model->type) {
	case mod_brush:
		return QGE_MODEL_BRUSH;
	case mod_alias:
		return QGE_MODEL_ALIAS;
	case mod_sprite:
		return QGE_MODEL_SPRITE;
	default:
		return QGE_MODEL_UNKNOWN;
	}
}

static qge_resource_id_t QGE_RegistryIndexedId(qge_resource_kind_t kind, int index)
{
	if (index < 0)
		return QGE_RESOURCE_ID_INVALID;
	return qge_resource_id_make(kind, (uint32_t)index + 1u);
}

static qge_resource_id_t QGE_RegistryPlaneId(const qmodel_t *model, const mplane_t *plane)
{
	if (!model || !plane || !model->planes)
		return QGE_RESOURCE_ID_INVALID;
	if (plane < model->planes || plane >= model->planes + model->numplanes)
		return QGE_RESOURCE_ID_INVALID;
	return QGE_RegistryIndexedId(QGE_RESOURCE_BSP_PLANE, (int)(plane - model->planes));
}

static qge_resource_id_t QGE_RegistryTextureId(const qmodel_t *model, const texture_t *texture)
{
	if (!model || !texture || !model->textures)
		return QGE_RESOURCE_ID_INVALID;
	for (int i = 0; i < model->numtextures; i++) {
		if (model->textures[i] == texture)
			return QGE_RegistryIndexedId(QGE_RESOURCE_TEXTURE, i);
	}
	return QGE_RESOURCE_ID_INVALID;
}

static qge_resource_id_t QGE_RegistryNodeChildId(const qmodel_t *model, const mnode_t *child)
{
	if (!model || !child)
		return QGE_RESOURCE_ID_INVALID;

	if (child->contents < 0) {
		const mleaf_t *leaf = (const mleaf_t *)child;
		if (model->leafs && leaf >= model->leafs && leaf < model->leafs + model->numleafs)
			return QGE_RegistryIndexedId(QGE_RESOURCE_BSP_LEAF, (int)(leaf - model->leafs));
		return QGE_RESOURCE_ID_INVALID;
	}

	if (model->nodes && child >= model->nodes && child < model->nodes + model->numnodes)
		return QGE_RegistryIndexedId(QGE_RESOURCE_BSP_NODE, (int)(child - model->nodes));
	return QGE_RESOURCE_ID_INVALID;
}

static uint32_t QGE_RegistryTextureFlags(const texture_t *tex)
{
	uint32_t flags = 0;

	if (!tex)
		return flags;
	if (tex->fullbright)
		flags |= QGE_TEXTURE_FLAG_FULLBRIGHT;
	if (tex->warpimage || tex->name[0] == '*')
		flags |= QGE_TEXTURE_FLAG_WARP;
	if (!q_strncasecmp(tex->name, "sky", 3))
		flags |= QGE_TEXTURE_FLAG_SKY;
	if (tex->name[0] == '{')
		flags |= QGE_TEXTURE_FLAG_FENCE | QGE_TEXTURE_FLAG_ALPHA;
	return flags;
}

static uint64_t QGE_RegistryModelHash(const qmodel_t *model)
{
	uint64_t hash;

	if (!model)
		return 0;
	hash = QGE_RegistryHashString(model->name);
	hash = QGE_RegistryHashStep(hash, (uint64_t)model->path_id);
	hash = QGE_RegistryHashStep(hash, (uint64_t)model->type);
	hash = QGE_RegistryHashStep(hash, (uint64_t)model->numframes);
	hash = QGE_RegistryHashStep(hash, (uint64_t)model->flags);
	return hash;
}

static void QGE_RegisterAliasModelAsset(qge_world_t *world, qmodel_t *model, int precache_index)
{
	qge_alias_model_ref_t ref;
	qge_resource_id_t id;

	if (!world || !model || model->type != mod_alias)
		return;

	memset(&ref, 0, sizeof(ref));
	strlcpy(ref.name, model->name, sizeof(ref.name));
	ref.precache_index = (uint32_t)precache_index;
	ref.frame_count = (uint32_t)(model->numframes < 0 ? 0 : model->numframes);
	ref.flags = (uint32_t)model->flags;
	ref.source_hash = QGE_RegistryModelHash(model);
	if (model->cache.data) {
		aliashdr_t *hdr = (aliashdr_t *)model->cache.data;
		ref.vertex_count = (uint32_t)(hdr->numverts < 0 ? 0 : hdr->numverts);
		ref.triangle_count = (uint32_t)(hdr->numtris < 0 ? 0 : hdr->numtris);
		ref.skin_count = (uint32_t)(hdr->numskins < 0 ? 0 : hdr->numskins);
		ref.frame_count = (uint32_t)(hdr->numframes < 0 ? 0 : hdr->numframes);
		ref.source_hash = QGE_RegistryHashStep(ref.source_hash, hdr->skinwidth);
		ref.source_hash = QGE_RegistryHashStep(ref.source_hash, hdr->skinheight);
		ref.source_hash = QGE_RegistryHashStep(ref.source_hash, hdr->numposes);
		ref.source_hash = QGE_RegistryHashStep(ref.source_hash, hdr->poseverts);
	}
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.vertex_count);
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.triangle_count);
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.skin_count);
	ref.debug_cookie = (uint64_t)(uintptr_t)model;
	ref.mins = QGE_RegistryVec3(model->mins);
	ref.maxs = QGE_RegistryVec3(model->maxs);
	id = qge_world_register_alias_model(world, &ref);
	if (precache_index >= 0 && precache_index < MAX_MODELS)
		qge_precache_model_resource_ids[precache_index] = id;
}

static void QGE_RegisterSpriteAsset(qge_world_t *world, qmodel_t *model, int precache_index)
{
	qge_sprite_ref_t ref;
	qge_resource_id_t id;

	if (!world || !model || model->type != mod_sprite)
		return;

	memset(&ref, 0, sizeof(ref));
	strlcpy(ref.name, model->name, sizeof(ref.name));
	ref.precache_index = (uint32_t)precache_index;
	ref.frame_count = (uint32_t)(model->numframes < 0 ? 0 : model->numframes);
	ref.width = (uint32_t)fabsf(model->maxs[0] - model->mins[0]);
	ref.height = (uint32_t)fabsf(model->maxs[2] - model->mins[2]);
	ref.flags = (uint32_t)model->flags;
	ref.source_hash = QGE_RegistryModelHash(model);
	if (model->cache.data) {
		msprite_t *sprite = (msprite_t *)model->cache.data;
		ref.frame_count = (uint32_t)(sprite->numframes < 0 ? 0 : sprite->numframes);
		ref.width = (uint32_t)(sprite->maxwidth < 0 ? 0 : sprite->maxwidth);
		ref.height = (uint32_t)(sprite->maxheight < 0 ? 0 : sprite->maxheight);
		ref.sprite_type = (uint32_t)sprite->type;
	}
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.width);
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.height);
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.sprite_type);
	ref.debug_cookie = (uint64_t)(uintptr_t)model;
	id = qge_world_register_sprite(world, &ref);
	if (precache_index >= 0 && precache_index < MAX_MODELS)
		qge_precache_model_resource_ids[precache_index] = id;
}

static void QGE_RegisterSoundAsset(qge_world_t *world, sfx_t *sfx, int precache_index)
{
	sfxcache_t *cache;
	qge_sound_ref_t ref;
	qge_resource_id_t id;

	if (!world || !sfx)
		return;
	cache = (sfxcache_t *)sfx->cache.data;

	memset(&ref, 0, sizeof(ref));
	strlcpy(ref.name, sfx->name, sizeof(ref.name));
	ref.precache_index = (uint32_t)precache_index;
	ref.source_hash = QGE_RegistryHashString(sfx->name);
	ref.debug_cookie = (uint64_t)(uintptr_t)sfx;
	if (cache) {
		ref.sample_rate = (uint32_t)(cache->speed < 0 ? 0 : cache->speed);
		ref.channels = (uint32_t)(cache->stereo < 0 ? 0 : cache->stereo);
		ref.sample_count = (uint32_t)(cache->length < 0 ? 0 : cache->length);
		ref.sample_width = (uint32_t)(cache->width < 0 ? 0 : cache->width);
		ref.flags |= QGE_SOUND_FLAG_LOADED;
		if (cache->width == 2)
			ref.flags |= QGE_SOUND_FLAG_16BIT;
		if (cache->loopstart >= 0)
			ref.flags |= QGE_SOUND_FLAG_LOOPED;
		ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.sample_rate);
		ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.sample_count);
	}

	id = qge_world_register_sound(world, &ref);
	if (precache_index >= 0 && precache_index < MAX_SOUNDS)
		qge_precache_sound_resource_ids[precache_index] = id;
}

static void QGE_RegisterPrecacheAssets(qge_world_t *world, qge_resource_id_t world_model_id)
{
	if (!world)
		return;

	memset(qge_precache_model_resource_ids, 0, sizeof(qge_precache_model_resource_ids));
	memset(qge_precache_sound_resource_ids, 0, sizeof(qge_precache_sound_resource_ids));

	for (int i = 1; i < MAX_MODELS && cl.model_precache[i]; i++) {
		qmodel_t *asset = cl.model_precache[i];
		if (asset == cl.worldmodel) {
			qge_precache_model_resource_ids[i] = world_model_id;
		} else if (asset->type == mod_alias) {
			QGE_RegisterAliasModelAsset(world, asset, i);
		} else if (asset->type == mod_sprite) {
			QGE_RegisterSpriteAsset(world, asset, i);
		}
	}

	for (int i = 1; i < MAX_SOUNDS && cl.sound_precache[i]; i++)
		QGE_RegisterSoundAsset(world, cl.sound_precache[i], i);
}

static void QGE_RebuildTextureSignalCache(const qmodel_t *model)
{
	memset(qge_texture_signal_cache, 0, sizeof(qge_texture_signal_cache));
	qge_texture_signal_cache_entries = 0;
	qge_texture_signal_gltexture_entries = 0;
	qge_texture_signal_fullbright_entries = 0;
	qge_texture_signal_warp_entries = 0;
	qge_texture_signal_cache_hash = 1469598103934665603ULL;

	if (!model || !model->textures)
		return;

	for (int i = 0; i < model->numtextures && i < QGE_MAX_TEXTURE_SIGNAL_CACHE; i++) {
		unsigned int signal_hash;
		if (!model->textures[i])
			continue;
		signal_hash = QGE_TextureSignalBuild(model->textures[i],
											 &qge_texture_signal_cache[i]);
		qge_texture_signal_cache_hash =
			QGE_RegistryHashStep(qge_texture_signal_cache_hash, signal_hash);
		if (qge_texture_signal_cache[i].valid) {
			qge_texture_signal_cache_entries++;
			if (qge_texture_signal_cache[i].texture_crc ||
				qge_texture_signal_cache[i].texture_width ||
				qge_texture_signal_cache[i].texture_height)
				qge_texture_signal_gltexture_entries++;
			if (qge_texture_signal_cache[i].has_fullbright)
				qge_texture_signal_fullbright_entries++;
			if (qge_texture_signal_cache[i].has_warp)
				qge_texture_signal_warp_entries++;
		}
	}
}

static void QGE_TraceTextureSignalCacheProbe(const qmodel_t *model)
{
	qge_quantum_runtime_t *rt;
	qge_state_probe_t probe;
	uint32_t flags = 0x1u;
	int texture_count = model && model->numtextures > 0 ? model->numtextures : 0;

	if (qge_texture_signal_gltexture_entries > 0)
		flags |= 0x2u;
	if (qge_texture_signal_fullbright_entries > 0)
		flags |= 0x4u;
	if (qge_texture_signal_warp_entries > 0)
		flags |= 0x8u;

	Con_Printf("QGE: Texture signal cache backend=cpu_gltexture_cache entries=%d gltexture=%d fullbright=%d warp=%d\n",
			   qge_texture_signal_cache_entries,
			   qge_texture_signal_gltexture_entries,
			   qge_texture_signal_fullbright_entries,
			   qge_texture_signal_warp_entries);
	fprintf(stderr, "QGE texture signal cache backend=cpu_gltexture_cache entries=%d gltexture=%d fullbright=%d warp=%d hash=0x%llx\n",
			qge_texture_signal_cache_entries,
			qge_texture_signal_gltexture_entries,
			qge_texture_signal_fullbright_entries,
			qge_texture_signal_warp_entries,
			(unsigned long long)qge_texture_signal_cache_hash);

	rt = QGE_Runtime();
	if (!rt)
		return;

	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_MATERIAL;
	probe.representation = QGE_REP_CLASSICAL_ORACLE;
	probe.subject_id = texture_count;
	probe.flags = flags;
	probe.state_hash = qge_texture_signal_cache_hash;
	probe.entropy = texture_count > 0 ?
		(double)qge_texture_signal_cache_entries / (double)texture_count : 0.0;
	probe.coherence = 1.0;
	probe.max_probability = (double)qge_texture_signal_gltexture_entries;
	probe.total_probability = (double)texture_count;
	probe.active_basis_count = qge_texture_signal_cache_entries;
	probe.qubit_count =
		qge_quantum_qubits_for_basis_count(qge_texture_signal_cache_entries);
	probe.memory_bytes = (uint64_t)qge_texture_signal_cache_entries *
						 (uint64_t)sizeof(qge_texture_signal_cache_t);
	strlcpy(probe.label, "texture_signal_cache", sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);
}

static void QGE_ClearLightmapSignalCache(void)
{
	memset(qge_lightmap_signal_cache, 0, sizeof(qge_lightmap_signal_cache));
	qge_lightmap_signal_cache_entries = 0;
	qge_lightmap_signal_lit_entries = 0;
	qge_lightmap_signal_contrast_entries = 0;
	qge_lightmap_signal_cache_hash = 1469598103934665603ULL;
}

static void QGE_StoreLightmapSignalCache(int surface_index,
										 unsigned int light_hash,
										 float light_energy,
										 float light_contrast)
{
	qge_lightmap_signal_cache_t *signal;

	if (surface_index < 0 || surface_index >= QGE_MAX_LIGHTMAP_SIGNAL_CACHE)
		return;
	signal = &qge_lightmap_signal_cache[surface_index];
	if (!signal->valid) {
		qge_lightmap_signal_cache_entries++;
		if (light_energy > 0.0f)
			qge_lightmap_signal_lit_entries++;
		if (light_contrast > 0.001f)
			qge_lightmap_signal_contrast_entries++;
	}
	signal->valid = true;
	signal->light_hash = light_hash;
	signal->light_energy = light_energy;
	signal->light_contrast = light_contrast;
	qge_lightmap_signal_cache_hash =
		QGE_RegistryHashStep(qge_lightmap_signal_cache_hash, light_hash);
	qge_lightmap_signal_cache_hash =
		QGE_RegistryHashStep(qge_lightmap_signal_cache_hash,
							 (uint64_t)(light_energy * 100000.0f));
	qge_lightmap_signal_cache_hash =
		QGE_RegistryHashStep(qge_lightmap_signal_cache_hash,
							 (uint64_t)(light_contrast * 100000.0f));
}

static void QGE_TraceLightmapSignalCacheProbe(const qmodel_t *model)
{
	qge_quantum_runtime_t *rt;
	qge_state_probe_t probe;
	uint32_t flags = 0x1u;
	int surface_count = model && model->numsurfaces > 0 ? model->numsurfaces : 0;

	if (qge_lightmap_signal_lit_entries > 0)
		flags |= 0x2u;
	if (qge_lightmap_signal_contrast_entries > 0)
		flags |= 0x4u;

	Con_Printf("QGE: Lightmap signal cache backend=cpu_lightmap_samples entries=%d lit=%d contrast=%d\n",
			   qge_lightmap_signal_cache_entries,
			   qge_lightmap_signal_lit_entries,
			   qge_lightmap_signal_contrast_entries);
	fprintf(stderr, "QGE lightmap signal cache backend=cpu_lightmap_samples entries=%d lit=%d contrast=%d hash=0x%llx\n",
			qge_lightmap_signal_cache_entries,
			qge_lightmap_signal_lit_entries,
			qge_lightmap_signal_contrast_entries,
			(unsigned long long)qge_lightmap_signal_cache_hash);

	rt = QGE_Runtime();
	if (!rt)
		return;

	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_MATERIAL;
	probe.representation = QGE_REP_CLASSICAL_ORACLE;
	probe.subject_id = surface_count;
	probe.flags = flags;
	probe.state_hash = qge_lightmap_signal_cache_hash;
	probe.entropy = surface_count > 0 ?
		(double)qge_lightmap_signal_cache_entries / (double)surface_count : 0.0;
	probe.coherence = 1.0;
	probe.max_probability = (double)qge_lightmap_signal_lit_entries;
	probe.total_probability = (double)surface_count;
	probe.active_basis_count = qge_lightmap_signal_cache_entries;
	probe.qubit_count =
		qge_quantum_qubits_for_basis_count(qge_lightmap_signal_cache_entries);
	probe.memory_bytes = (uint64_t)qge_lightmap_signal_cache_entries *
						 (uint64_t)sizeof(qge_lightmap_signal_cache_t);
	strlcpy(probe.label, "lightmap_signal_cache", sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);
}

static qge_resource_id_t QGE_RegisterHudImageIndex(qge_world_t *world, int index)
{
	qge_world_stats_t stats;
	qge_hud_image_pending_t *pending;
	qge_resource_id_t id;

	if (!world || index < 0 || index >= qge_hud_image_count)
		return QGE_RESOURCE_ID_INVALID;
	pending = &qge_hud_images[index];
	if (!pending->used)
		return QGE_RESOURCE_ID_INVALID;

	qge_world_get_stats(world, &stats);
	if (!qge_resource_id_is_valid(stats.current_world_id) || stats.map_revision == 0)
		return QGE_RESOURCE_ID_INVALID;
	if (pending->registered_revision == stats.map_revision)
		return pending->id;

	id = qge_world_register_hud_image(world, &pending->ref);
	if (qge_resource_id_is_valid(id)) {
		pending->id = id;
		pending->registered_revision = stats.map_revision;
	}
	return id;
}

static void QGE_RegisterPendingHudImages(qge_world_t *world)
{
	if (!world)
		return;
	for (int i = 0; i < qge_hud_image_count; i++)
		QGE_RegisterHudImageIndex(world, i);
}

void QGE_RegisterHudImageAsset(const char *name,
							   int width,
							   int height,
							   unsigned int source_crc,
							   unsigned int source_format,
							   unsigned int flags,
							   const void *debug_cookie)
{
	qge_hud_image_pending_t *pending = NULL;
	qge_hud_image_ref_t ref;
	qge_world_t *world;
	int index = -1;

	if (!name || !name[0] || width <= 0 || height <= 0)
		return;

	for (int i = 0; i < qge_hud_image_count; i++) {
		if (qge_hud_images[i].used && !strcmp(qge_hud_images[i].ref.name, name)) {
			pending = &qge_hud_images[i];
			index = i;
			break;
		}
	}
	if (!pending) {
		if (qge_hud_image_count == QGE_MAX_HUD_IMAGE_REFS) {
			qge_hud_image_dropped++;
			return;
		}
		index = qge_hud_image_count++;
		pending = &qge_hud_images[index];
		memset(pending, 0, sizeof(*pending));
		pending->used = true;
	}

	memset(&ref, 0, sizeof(ref));
	strlcpy(ref.name, name, sizeof(ref.name));
	ref.width = (uint32_t)width;
	ref.height = (uint32_t)height;
	ref.source_crc = source_crc;
	ref.source_format = source_format;
	ref.flags = flags;
	ref.source_hash = QGE_RegistryHashString(name);
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.width);
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.height);
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, source_crc);
	ref.debug_cookie = (uint64_t)(uintptr_t)debug_cookie;
	pending->ref = ref;
	if (strstr(name, "conchars"))
		qge_hud_conchars_registered = true;

	if (!qge_initialized || !qge_ctx)
		return;
	world = qge_get_world(qge_ctx);
	if (world)
		QGE_RegisterHudImageIndex(world, index);
}

static qboolean QGE_HudImageCookieRegistered(const void *debug_cookie)
{
	uint64_t cookie = (uint64_t)(uintptr_t)debug_cookie;

	if (!cookie)
		return false;
	for (int i = 0; i < qge_hud_image_count; i++) {
		if (qge_hud_images[i].used &&
			qge_hud_images[i].ref.debug_cookie == cookie)
			return true;
	}
	return false;
}

static void QGE_2DAccountDraw(qboolean owned)
{
	if (!qge_2d_collecting)
		return;
	if (qge_2d_layer == QGE_2D_LAYER_HUD) {
		qge_2d_current.hud_draws++;
		if (owned)
			qge_2d_current.hud_owned++;
		else
			qge_2d_current.hud_unowned++;
	} else if (qge_2d_layer == QGE_2D_LAYER_CONSOLE) {
		qge_2d_current.console_draws++;
		if (owned)
			qge_2d_current.console_owned++;
		else
			qge_2d_current.console_unowned++;
	} else {
		qge_2d_current.other_draws++;
	}
}

static int QGE_2DLastDrawCount(void)
{
	return qge_2d_last.hud_draws +
		   qge_2d_last.console_draws +
		   qge_2d_last.other_draws;
}

static int QGE_2DOwnsHud(void)
{
	return qge_2d_last_valid &&
		   qge_2d_last.hud_draws > 0 &&
		   qge_2d_last.hud_unowned == 0;
}

static int QGE_2DOwnsConsole(void)
{
	return qge_2d_last_valid &&
		   qge_hud_conchars_registered &&
		   qge_2d_last.console_unowned == 0;
}

static int QGE_2DHasUnownedClassicOutput(void)
{
	if (!QGE_RenderIsPrimary())
		return 1;
	return !(QGE_2DOwnsHud() && QGE_2DOwnsConsole());
}

void QGE_2DBeginFrame(void)
{
	memset(&qge_2d_current, 0, sizeof(qge_2d_current));
	qge_2d_layer = QGE_2D_LAYER_NONE;
	qge_2d_collecting = qge_initialized && quantum_render.value >= 0.5f;
}

void QGE_2DEndFrame(void)
{
	qge_quantum_runtime_t *rt;
	qge_state_probe_t probe;
	int draw_count;
	uint32_t flags = 0u;

	if (!qge_2d_collecting)
		return;

	qge_2d_last = qge_2d_current;
	qge_2d_last_valid = true;
	qge_2d_collecting = false;
	qge_2d_layer = QGE_2D_LAYER_NONE;

	draw_count = QGE_2DLastDrawCount();
	if (QGE_2DOwnsHud())
		flags |= 0x1u;
	if (QGE_2DOwnsConsole())
		flags |= 0x2u;
	if (qge_2d_last.hud_unowned || qge_2d_last.console_unowned)
		flags |= 0x4u;
	if (qge_2d_last.other_draws)
		flags |= 0x8u;

	rt = QGE_Runtime();
	if (!rt)
		return;
	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_RENDER;
	probe.representation = QGE_REP_CLASSICAL_ORACLE;
	probe.active_basis_count = (uint32_t)draw_count;
	probe.qubit_count =
		qge_quantum_qubits_for_basis_count((uint64_t)(draw_count > 0 ? draw_count : 1));
	probe.subject_id = (uint64_t)qge_2d_last.hud_draws;
	probe.flags = flags;
	probe.total_probability = (double)qge_2d_last.console_draws;
	probe.max_probability = (double)qge_2d_last.hud_owned;
	probe.coherence = (double)qge_2d_last.console_owned;
	probe.entropy = (double)(qge_2d_last.hud_unowned +
							 qge_2d_last.console_unowned);
	strlcpy(probe.label, "render_2d_overlay", sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);
}

void QGE_2DSetLayer(int layer)
{
	if (layer != QGE_2D_LAYER_HUD &&
		layer != QGE_2D_LAYER_CONSOLE)
		layer = QGE_2D_LAYER_NONE;
	qge_2d_layer = layer;
}

void QGE_2DSubmitPic(const qpic_t *pic)
{
	QGE_2DAccountDraw(QGE_HudImageCookieRegistered(pic));
}

void QGE_2DSubmitCharacter(int ch)
{
	(void)ch;
	QGE_2DAccountDraw(qge_hud_conchars_registered);
}

void QGE_2DSubmitFill(void)
{
	QGE_2DAccountDraw(true);
}

static void QGE_RegisterWorldIfNeeded(void)
{
	qge_world_t *world;
	qmodel_t *model;
	qge_resource_id_t world_id;
	qge_resource_id_t model_id;
	qge_model_ref_t model_ref;
	uint64_t map_hash;

	if (!qge_initialized || !qge_ctx)
		return;
	model = cl.worldmodel;
	if (!model || model->type != mod_brush)
		return;
	if (qge_registered_worldmodel == model &&
		!strcmp(qge_registered_world_name, model->name))
		return;

	world = qge_get_world(qge_ctx);
	if (!world)
		return;

	map_hash = QGE_RegistryHashString(model->name);
	map_hash = QGE_RegistryHashStep(map_hash, (uint64_t)model->path_id);
	map_hash = QGE_RegistryHashStep(map_hash, (uint64_t)model->bspversion);
	map_hash = QGE_RegistryHashStep(map_hash, (uint64_t)model->numsurfaces);
	map_hash = QGE_RegistryHashStep(map_hash, (uint64_t)model->numtextures);

	world_id = qge_world_begin_map(world,
								   cl.mapname[0] ? cl.mapname : model->name,
								   map_hash);

	memset(&model_ref, 0, sizeof(model_ref));
	strlcpy(model_ref.name, model->name, sizeof(model_ref.name));
	model_ref.model_type = QGE_RegistryModelType(model);
	model_ref.source_hash = map_hash;
	model_ref.debug_cookie = (uint64_t)(uintptr_t)model;
	model_ref.mins = QGE_RegistryVec3(model->mins);
	model_ref.maxs = QGE_RegistryVec3(model->maxs);
	model_ref.flags = (uint32_t)model->flags;
	model_ref.first_surface = (uint32_t)(model->firstmodelsurface < 0 ? 0 : model->firstmodelsurface);
	model_ref.surface_count = (uint32_t)(model->numsurfaces < 0 ? 0 : model->numsurfaces);
	model_ref.texture_count = (uint32_t)(model->numtextures < 0 ? 0 : model->numtextures);
	model_ref.leaf_count = (uint32_t)(model->numleafs < 0 ? 0 : model->numleafs);
	model_ref.node_count = (uint32_t)(model->numnodes < 0 ? 0 : model->numnodes);
	model_ref.plane_count = (uint32_t)(model->numplanes < 0 ? 0 : model->numplanes);
	model_id = qge_world_register_model(world, &model_ref);

	for (int i = 0; model->planes && i < model->numplanes; i++) {
		const mplane_t *plane = &model->planes[i];
		qge_plane_ref_t ref;
		memset(&ref, 0, sizeof(ref));
		ref.model_id = model_id;
		ref.plane_index = (uint32_t)i;
		ref.normal = QGE_RegistryVec3(plane->normal);
		ref.dist = plane->dist;
		ref.type = plane->type;
		ref.signbits = plane->signbits;
		ref.debug_cookie = (uint64_t)(uintptr_t)plane;
		qge_world_register_plane(world, &ref);
	}

	for (int i = 0; model->leafs && i < model->numleafs; i++) {
		const mleaf_t *leaf = &model->leafs[i];
		qge_leaf_ref_t ref;
		memset(&ref, 0, sizeof(ref));
		ref.model_id = model_id;
		ref.leaf_index = (uint32_t)i;
		ref.contents = leaf->contents;
		if (model->marksurfaces && leaf->firstmarksurface >= model->marksurfaces &&
			leaf->firstmarksurface < model->marksurfaces + model->nummarksurfaces) {
			ref.first_marksurface = (uint32_t)(leaf->firstmarksurface - model->marksurfaces);
		}
		ref.marksurface_count = (uint32_t)(leaf->nummarksurfaces < 0 ? 0 : leaf->nummarksurfaces);
		if (model->visdata && leaf->compressed_vis && leaf->compressed_vis >= model->visdata)
			ref.compressed_vis_offset = (uint32_t)(leaf->compressed_vis - model->visdata);
		memcpy(ref.ambient_sound_level, leaf->ambient_sound_level,
			   sizeof(ref.ambient_sound_level));
		ref.mins = QGE_RegistryMinmaxMin(leaf->minmaxs);
		ref.maxs = QGE_RegistryMinmaxMax(leaf->minmaxs);
		ref.debug_cookie = (uint64_t)(uintptr_t)leaf;
		qge_world_register_leaf(world, &ref);
	}

	for (int i = 0; model->nodes && i < model->numnodes; i++) {
		const mnode_t *node = &model->nodes[i];
		qge_node_ref_t ref;
		memset(&ref, 0, sizeof(ref));
		ref.model_id = model_id;
		ref.node_index = (uint32_t)i;
		ref.contents = node->contents;
		ref.plane_id = QGE_RegistryPlaneId(model, node->plane);
		ref.child_ids[0] = QGE_RegistryNodeChildId(model, node->children[0]);
		ref.child_ids[1] = QGE_RegistryNodeChildId(model, node->children[1]);
		ref.first_surface = node->firstsurface;
		ref.surface_count = node->numsurfaces;
		ref.mins = QGE_RegistryMinmaxMin(node->minmaxs);
		ref.maxs = QGE_RegistryMinmaxMax(node->minmaxs);
		ref.debug_cookie = (uint64_t)(uintptr_t)node;
		qge_world_register_node(world, &ref);
	}

	for (int i = 0; model->textures && i < model->numtextures; i++) {
		const texture_t *tex = model->textures[i];
		qge_texture_ref_t ref;
		const gltexture_t *glt;
		if (!tex)
			continue;
		memset(&ref, 0, sizeof(ref));
		ref.owner_model_id = model_id;
		strlcpy(ref.name, tex->name, sizeof(ref.name));
		ref.texture_index = (uint32_t)i;
		ref.width = tex->width;
		ref.height = tex->height;
		ref.flags = QGE_RegistryTextureFlags(tex);
		ref.source_hash = QGE_RegistryHashString(tex->name);
		ref.debug_cookie = (uint64_t)(uintptr_t)tex;
		glt = tex->gltexture;
		if (glt) {
			ref.source_crc = glt->source_crc;
			ref.source_format = (uint32_t)glt->source_format;
			ref.source_hash = QGE_RegistryHashStep(ref.source_hash, glt->source_crc);
			ref.source_hash = QGE_RegistryHashStep(ref.source_hash, glt->source_width);
			ref.source_hash = QGE_RegistryHashStep(ref.source_hash, glt->source_height);
		}
		qge_world_register_texture(world, &ref);
	}
	QGE_RebuildTextureSignalCache(model);
	QGE_TraceTextureSignalCacheProbe(model);
	QGE_ClearLightmapSignalCache();

	for (int i = 0; model->surfaces && i < model->numsurfaces; i++) {
		const msurface_t *surf = &model->surfaces[i];
		qge_resource_id_t surface_id = QGE_RegistryIndexedId(QGE_RESOURCE_SURFACE, i);
		qge_resource_id_t lightmap_id = QGE_RegistryIndexedId(QGE_RESOURCE_LIGHTMAP, i);
		qge_surface_ref_t surface_ref;
		qge_lightmap_ref_t lightmap_ref;
		float energy = 0.0f;
		float contrast = 0.0f;
		unsigned int light_hash = QGE_SurfaceLightSignal(surf, &energy, &contrast);

		memset(&surface_ref, 0, sizeof(surface_ref));
		surface_ref.model_id = model_id;
		surface_ref.texture_id = surf->texinfo ?
			QGE_RegistryTextureId(model, surf->texinfo->texture) : QGE_RESOURCE_ID_INVALID;
		surface_ref.lightmap_id = lightmap_id;
		surface_ref.surface_index = (uint32_t)i;
		surface_ref.plane_index = surf->plane && model->planes &&
			surf->plane >= model->planes && surf->plane < model->planes + model->numplanes ?
			(uint32_t)(surf->plane - model->planes) : 0;
		surface_ref.flags = (uint32_t)surf->flags;
		surface_ref.first_edge = surf->firstedge;
		surface_ref.edge_count = surf->numedges;
		surface_ref.debug_cookie = (uint64_t)(uintptr_t)surf;
		surface_ref.mins = QGE_RegistryVec3(surf->mins);
		surface_ref.maxs = QGE_RegistryVec3(surf->maxs);
		surface_ref.centroid.x = (surface_ref.mins.x + surface_ref.maxs.x) * 0.5f;
		surface_ref.centroid.y = (surface_ref.mins.y + surface_ref.maxs.y) * 0.5f;
		surface_ref.centroid.z = (surface_ref.mins.z + surface_ref.maxs.z) * 0.5f;
		surface_ref.light_energy = energy;
		surface_ref.light_contrast = contrast;
		surface_ref.material_signal = 0.25f;
		qge_world_register_surface(world, &surface_ref);
		QGE_StoreLightmapSignalCache(i, light_hash, energy, contrast);

		memset(&lightmap_ref, 0, sizeof(lightmap_ref));
		lightmap_ref.model_id = model_id;
		lightmap_ref.surface_id = surface_id;
		lightmap_ref.lightmap_index = (uint32_t)(surf->lightmaptexturenum < 0 ? 0 : surf->lightmaptexturenum);
		lightmap_ref.width = (uint32_t)((surf->extents[0] >> 4) + 1);
		lightmap_ref.height = (uint32_t)((surf->extents[1] >> 4) + 1);
		memcpy(lightmap_ref.styles, surf->styles, sizeof(lightmap_ref.styles));
		lightmap_ref.sample_hash = light_hash;
		lightmap_ref.energy = energy;
			lightmap_ref.contrast = contrast;
			qge_world_register_lightmap(world, &lightmap_ref);
		}
		QGE_TraceLightmapSignalCacheProbe(model);

		QGE_RegisterPrecacheAssets(world, model_id);
	QGE_RegisterPendingHudImages(world);

	qge_world_get_stats(world, &qge_registry_stats);
	qge_registered_worldmodel = model;
	strlcpy(qge_registered_world_name, model->name, sizeof(qge_registered_world_name));
	qge_debug_sprite_logged_id = QGE_RESOURCE_ID_INVALID;
	QGE_TraceWorldRegistryProbe(&qge_registry_stats);

	Con_Printf("QGE: World registry map=%s models=%u planes=%u nodes=%u leafs=%u surfaces=%u textures=%u lightmaps=%u alias=%u sprites=%u sounds=%u hud=%u\n",
			   qge_registry_stats.map_name,
			   qge_registry_stats.model_count,
			   qge_registry_stats.plane_count,
			   qge_registry_stats.node_count,
			   qge_registry_stats.leaf_count,
			   qge_registry_stats.surface_count,
			   qge_registry_stats.texture_count,
			   qge_registry_stats.lightmap_count,
			   qge_registry_stats.alias_model_count,
			   qge_registry_stats.sprite_count,
			   qge_registry_stats.sound_count,
			   qge_registry_stats.hud_image_count);
	fprintf(stderr, "QGE registry map=%s world=0x%x models=%u planes=%u nodes=%u leafs=%u surfaces=%u textures=%u lightmaps=%u alias=%u sprites=%u sounds=%u hud=%u total=%u\n",
			qge_registry_stats.map_name,
			world_id,
			qge_registry_stats.model_count,
			qge_registry_stats.plane_count,
			qge_registry_stats.node_count,
			qge_registry_stats.leaf_count,
			qge_registry_stats.surface_count,
			qge_registry_stats.texture_count,
			qge_registry_stats.lightmap_count,
			qge_registry_stats.alias_model_count,
			qge_registry_stats.sprite_count,
			qge_registry_stats.sound_count,
			qge_registry_stats.hud_image_count,
			qge_registry_stats.total_resources);
}

static qge_resource_id_t QGE_ModelStableResourceId(const qmodel_t *model)
{
	if (!model)
		return QGE_RESOURCE_ID_INVALID;
	for (int i = 1; i < MAX_MODELS && cl.model_precache[i]; i++) {
		if (cl.model_precache[i] == model &&
			qge_resource_id_is_valid(qge_precache_model_resource_ids[i]))
			return qge_precache_model_resource_ids[i];
	}
	if (model == cl.worldmodel)
		return qge_resource_id_make(QGE_RESOURCE_BSP_MODEL, 1);
	return QGE_RESOURCE_ID_INVALID;
}

static qge_resource_id_t QGE_SoundStableResourceId(const sfx_t *sfx)
{
	if (!sfx)
		return QGE_RESOURCE_ID_INVALID;
	for (int i = 1; i < MAX_SOUNDS && cl.sound_precache[i]; i++) {
		if (cl.sound_precache[i] == sfx &&
			qge_resource_id_is_valid(qge_precache_sound_resource_ids[i]))
			return qge_precache_sound_resource_ids[i];
	}
	return QGE_RESOURCE_ID_INVALID;
}

static qge_resource_id_t QGE_EntityStableResourceId(const entity_t *ent)
{
	if (!ent)
		return QGE_RESOURCE_ID_INVALID;
	if (cl_entities && ent >= cl_entities && ent < cl_entities + cl.num_entities)
		return qge_resource_id_make(QGE_RESOURCE_ENTITY,
									(uint32_t)(ent - cl_entities) + 1u);
	if (ent >= cl_static_entities && ent < cl_static_entities + MAX_STATIC_ENTITIES)
		return qge_resource_id_make(QGE_RESOURCE_ENTITY,
									0x10000u + (uint32_t)(ent - cl_static_entities) + 1u);
	if (ent >= cl_temp_entities && ent < cl_temp_entities + MAX_TEMP_ENTITIES)
		return qge_resource_id_make(QGE_RESOURCE_ENTITY,
									0x20000u + (uint32_t)(ent - cl_temp_entities) + 1u);
	if (ent == &cl.viewent)
		return qge_resource_id_make(QGE_RESOURCE_ENTITY, 0x30000u);
	return QGE_RESOURCE_ID_INVALID;
}

static uint32_t QGE_FrameViewLeafIndex(void)
{
	mleaf_t *leaf;

	if (!cl.worldmodel || !cl.worldmodel->leafs)
		return 0;
	leaf = Mod_PointInLeaf(r_refdef.vieworg, cl.worldmodel);
	if (!leaf || leaf < cl.worldmodel->leafs ||
		leaf >= cl.worldmodel->leafs + cl.worldmodel->numleafs)
		return 0;
	return (uint32_t)(leaf - cl.worldmodel->leafs);
}

static void QGE_FrameSnapshotSetCameraAndWorld(qge_frame_snapshot_t *snapshot)
{
	qge_world_t *world;
	qge_resource_id_t world_id;
	qge_resource_id_t world_model_id;
	qge_camera_snapshot_t camera;
	uint32_t view_leaf_index;
	uint32_t pvs_hash;
	vec3_t forward, right, up;

	if (!snapshot || snapshot->sealed)
		return;

	memset(&camera, 0, sizeof(camera));
	AngleVectors(r_refdef.viewangles, forward, right, up);
	camera.origin = QGE_RegistryVec3(r_refdef.vieworg);
	camera.forward = QGE_RegistryVec3(forward);
	camera.right = QGE_RegistryVec3(right);
	camera.up = QGE_RegistryVec3(up);
	camera.fov_x = r_refdef.fov_x;
	camera.fov_y = r_refdef.fov_y;
	camera.viewport_x = r_refdef.vrect.x;
	camera.viewport_y = r_refdef.vrect.y;
	camera.viewport_width = r_refdef.vrect.width;
	camera.viewport_height = r_refdef.vrect.height;
	qge_frame_snapshot_set_camera(snapshot, &camera);

	world = qge_get_world(qge_ctx);
	world_id = qge_world_current_map_id(world);
	world_model_id = QGE_ModelStableResourceId(cl.worldmodel);
	view_leaf_index = QGE_FrameViewLeafIndex();
	pvs_hash = (uint32_t)QGE_RegistryHashStep((uint64_t)view_leaf_index,
											  (uint64_t)qge_frame_count);
	qge_frame_snapshot_set_world(snapshot, world_id, world_model_id,
								 view_leaf_index, pvs_hash);
}

static void QGE_FrameSnapshotBeginCurrent(void)
{
	qge_frame_snapshot_t *snapshot;

	if (!qge_ctx)
		return;
	snapshot = qge_get_frame_snapshot(qge_ctx);
	if (!snapshot)
		return;
	qge_frame_snapshot_begin(snapshot,
							 (uint32_t)qge_frame_count,
							 (int64_t)(qge_frame_start * 1000.0),
							 QGE_ServerTimeMsec(),
							 (int64_t)(cl.time * 1000.0));
	QGE_FrameSnapshotSetCameraAndWorld(snapshot);
}

static void QGE_FrameSnapshotAddVisibleSurface(const qge_scene_surface_t *surface)
{
	qge_frame_snapshot_t *snapshot;
	qge_snapshot_surface_t item;

	if (!qge_ctx || !surface || surface->surface_id < 0)
		return;
	snapshot = qge_get_frame_snapshot(qge_ctx);
	if (!snapshot || snapshot->sealed)
		return;

	memset(&item, 0, sizeof(item));
	item.surface_id = qge_resource_id_make(QGE_RESOURCE_SURFACE,
										   (uint32_t)surface->surface_id + 1u);
	item.visibility = 1.0f;
	item.depth = surface->depth;
	item.flags = (uint32_t)surface->flags;
	qge_frame_snapshot_add_visible_surface(snapshot, &item);
}

static void QGE_FrameSnapshotAddEntity(qge_frame_snapshot_t *snapshot,
									   const entity_t *ent)
{
	qge_snapshot_edict_t item;
	qge_resource_id_t entity_id;
	qge_resource_id_t model_id;

	if (!snapshot || !ent || !ent->model)
		return;
	entity_id = QGE_EntityStableResourceId(ent);
	model_id = QGE_ModelStableResourceId(ent->model);
	if (!qge_resource_id_is_valid(entity_id) ||
		!qge_resource_id_is_valid(model_id))
		return;

	memset(&item, 0, sizeof(item));
	item.entity_id = entity_id;
	item.model_id = model_id;
	item.origin = QGE_RegistryVec3(ent->origin);
	item.angles = QGE_RegistryVec3(ent->angles);
	item.mins.x = ent->origin[0] + ent->model->mins[0];
	item.mins.y = ent->origin[1] + ent->model->mins[1];
	item.mins.z = ent->origin[2] + ent->model->mins[2];
	item.maxs.x = ent->origin[0] + ent->model->maxs[0];
	item.maxs.y = ent->origin[1] + ent->model->maxs[1];
	item.maxs.z = ent->origin[2] + ent->model->maxs[2];
	item.effects = (uint32_t)ent->effects;
	item.frame = ent->frame;
	item.alpha = ENTALPHA_DECODE(ent->alpha);
	item.scale = ENTSCALE_DECODE(ent->scale);
	qge_frame_snapshot_add_edict(snapshot, &item);
}

static qge_resource_id_t QGE_FirstRegisteredSpriteId(const qge_sprite_ref_t **out_ref)
{
	qge_world_t *world;

	if (out_ref)
		*out_ref = NULL;
	if (!qge_ctx)
		return QGE_RESOURCE_ID_INVALID;
	world = qge_get_world(qge_ctx);
	if (!world)
		return QGE_RESOURCE_ID_INVALID;

	for (int i = 1; i < MAX_MODELS && cl.model_precache[i]; i++) {
		qge_resource_id_t id = qge_precache_model_resource_ids[i];
		if (qge_resource_id_kind(id) != QGE_RESOURCE_SPRITE)
			continue;
		const qge_sprite_ref_t *ref = qge_world_get_sprite(world, id);
		if (!ref || !ref->debug_cookie)
			continue;
		if (out_ref)
			*out_ref = ref;
		return id;
	}
	return QGE_RESOURCE_ID_INVALID;
}

static void QGE_FrameSnapshotAddDiagnosticSprite(qge_frame_snapshot_t *snapshot)
{
	const qge_sprite_ref_t *ref;
	qge_resource_id_t sprite_id;
	qmodel_t *model;
	qge_snapshot_edict_t item;
	vec3_t forward, right, up;
	float distance;

	if (!snapshot || snapshot->sealed || quantum_debug_sprite_billboard.value < 0.5f)
		return;

	sprite_id = QGE_FirstRegisteredSpriteId(&ref);
	if (!qge_resource_id_is_valid(sprite_id) || !ref)
		return;
	model = (qmodel_t *)(uintptr_t)ref->debug_cookie;
	if (!model || model->type != mod_sprite)
		return;

	distance = quantum_debug_sprite_billboard.value > 1.0f ?
		quantum_debug_sprite_billboard.value : 96.0f;
	if (distance < 32.0f)
		distance = 32.0f;
	if (distance > 512.0f)
		distance = 512.0f;

	AngleVectors(r_refdef.viewangles, forward, right, up);
	memset(&item, 0, sizeof(item));
	item.entity_id = qge_resource_id_make(QGE_RESOURCE_ENTITY, 0x30010u);
	item.model_id = sprite_id;
	item.origin.x = r_refdef.vieworg[0] + forward[0] * distance;
	item.origin.y = r_refdef.vieworg[1] + forward[1] * distance;
	item.origin.z = r_refdef.vieworg[2] + forward[2] * distance;
	item.mins.x = item.origin.x + model->mins[0];
	item.mins.y = item.origin.y + model->mins[1];
	item.mins.z = item.origin.z + model->mins[2];
	item.maxs.x = item.origin.x + model->maxs[0];
	item.maxs.y = item.origin.y + model->maxs[1];
	item.maxs.z = item.origin.z + model->maxs[2];
	item.effects = EF_BRIGHTLIGHT;
	item.frame = ref->frame_count ? (int32_t)(qge_frame_count % ref->frame_count) : 0;
	item.alpha = 1.0f;
	item.scale = 1.0f;
	qge_frame_snapshot_add_edict(snapshot, &item);

	if (qge_debug_sprite_logged_id != sprite_id) {
		Con_Printf("QGE: Diagnostic sprite billboard model=%s id=0x%x distance=%.1f\n",
				   ref->name, sprite_id, distance);
		fprintf(stderr, "QGE diagnostic sprite model=%s id=0x%x distance=%.1f\n",
				ref->name, sprite_id, distance);
		qge_debug_sprite_logged_id = sprite_id;
	}
}

static void QGE_FrameSnapshotCaptureEdicts(qge_frame_snapshot_t *snapshot)
{
	if (!snapshot || snapshot->edict_count > 0 || cls.signon != SIGNONS)
		return;
	for (int i = 0; i < cl_numvisedicts; i++)
		QGE_FrameSnapshotAddEntity(snapshot, cl_visedicts[i]);
	QGE_FrameSnapshotAddEntity(snapshot, &cl.viewent);
	QGE_FrameSnapshotAddDiagnosticSprite(snapshot);
}

static void QGE_FrameSnapshotCaptureLights(qge_frame_snapshot_t *snapshot)
{
	if (!snapshot || cls.signon != SIGNONS)
		return;
	for (int i = 0; i < MAX_DLIGHTS; i++) {
		dlight_t *light = &cl_dlights[i];
		qge_snapshot_light_t item;
		if (light->die < cl.time || light->radius <= 0.0f)
			continue;
		memset(&item, 0, sizeof(item));
		item.light_id = qge_resource_id_make(QGE_RESOURCE_DYNAMIC_LIGHT,
											 (uint32_t)i + 1u);
		item.origin = QGE_RegistryVec3(light->origin);
		item.color = QGE_RegistryVec3(light->color);
		item.radius = light->radius;
		item.intensity = light->radius / 256.0f;
		qge_frame_snapshot_add_dynamic_light(snapshot, &item);
	}
}

static void QGE_FrameSnapshotCaptureSounds(qge_frame_snapshot_t *snapshot)
{
	if (!snapshot || cls.signon != SIGNONS)
		return;
	for (int i = 0; i < total_channels && i < MAX_CHANNELS; i++) {
		channel_t *channel = &snd_channels[i];
		qge_snapshot_sound_t item;
		qge_resource_id_t sound_id;

		if (!channel->sfx || channel->end <= paintedtime ||
			(!channel->leftvol && !channel->rightvol))
			continue;
		sound_id = QGE_SoundStableResourceId(channel->sfx);
		if (!qge_resource_id_is_valid(sound_id))
			continue;

		memset(&item, 0, sizeof(item));
		item.source_id = qge_resource_id_make(QGE_RESOURCE_AUDIO_SOURCE,
											  (uint32_t)i + 1u);
		item.sound_id = sound_id;
		item.origin = QGE_RegistryVec3(channel->origin);
		item.volume = (float)channel->master_vol / 255.0f;
		item.attenuation = channel->dist_mult;
		item.channel = channel->entchannel;
		qge_frame_snapshot_add_sound_source(snapshot, &item);
	}
}

static void QGE_FrameSnapshotCaptureQuantumParticles(qge_frame_snapshot_t *snapshot)
{
	qge_vec3_t positions[64];
	int count;

	if (!snapshot || !qge_particles || quantum_particles.value < 0.5f)
		return;
	count = qge_particle_get_positions(qge_particles, positions,
									   (int)(sizeof(positions) / sizeof(positions[0])));
	for (int i = 0; i < count; i++) {
		qge_snapshot_particle_t item;
		memset(&item, 0, sizeof(item));
		item.particle_id = qge_resource_id_make(QGE_RESOURCE_PARTICLE,
												(uint32_t)i + 1u);
		item.origin = positions[i];
		item.color = 0xffffffffu;
		item.lifetime = (float)host_frametime;
		qge_frame_snapshot_add_particle(snapshot, &item);
	}
}

static void QGE_FrameSnapshotCaptureParticles(qge_frame_snapshot_t *snapshot)
{
	if (!snapshot || snapshot->particle_count > 0 || cls.signon != SIGNONS)
		return;

	if (quantum_particles.value >= 0.5f)
		QGE_FrameSnapshotCaptureQuantumParticles(snapshot);
	else
		QGE_CaptureClassicParticles(snapshot);
}

static uint64_t QGE_FrameSnapshotHash(const qge_frame_snapshot_t *snapshot,
									  const qge_frame_snapshot_stats_t *stats)
{
	uint64_t hash = 1469598103934665603ULL;

	if (!snapshot)
		return hash;
	hash = QGE_RegistryHashStep(hash, snapshot->frame_number);
	hash = QGE_RegistryHashStep(hash, snapshot->world_id);
	hash = QGE_RegistryHashStep(hash, snapshot->world_model_id);
	hash = QGE_RegistryHashStep(hash, snapshot->view_leaf_index);
	hash = QGE_RegistryHashStep(hash, snapshot->pvs_hash);
	if (stats) {
		hash = QGE_RegistryHashStep(hash, stats->visible_surface_count);
		hash = QGE_RegistryHashStep(hash, stats->edict_count);
		hash = QGE_RegistryHashStep(hash, stats->dynamic_light_count);
		hash = QGE_RegistryHashStep(hash, stats->particle_count);
		hash = QGE_RegistryHashStep(hash, stats->sound_source_count);
		hash = QGE_RegistryHashStep(hash, stats->entropy_ref_count);
		hash = QGE_RegistryHashStep(hash, stats->dropped_visible_surfaces);
		hash = QGE_RegistryHashStep(hash, stats->dropped_edicts);
		hash = QGE_RegistryHashStep(hash, stats->dropped_dynamic_lights);
		hash = QGE_RegistryHashStep(hash, stats->dropped_particles);
		hash = QGE_RegistryHashStep(hash, stats->dropped_sound_sources);
		hash = QGE_RegistryHashStep(hash, stats->dropped_entropy_refs);
	}

	for (uint32_t i = 0; i < snapshot->visible_surface_count; i++) {
		hash = QGE_RegistryHashStep(hash, snapshot->visible_surfaces[i].surface_id);
		hash = QGE_RegistryHashStep(hash, snapshot->visible_surfaces[i].flags);
	}
	for (uint32_t i = 0; i < snapshot->edict_count; i++) {
		hash = QGE_RegistryHashStep(hash, snapshot->edicts[i].entity_id);
		hash = QGE_RegistryHashStep(hash, snapshot->edicts[i].model_id);
		hash = QGE_RegistryHashStep(hash, (uint64_t)(uint32_t)snapshot->edicts[i].frame);
		hash = QGE_RegistryHashStep(hash,
			(uint64_t)(uint32_t)(snapshot->edicts[i].scale * 65536.0f));
	}
	for (uint32_t i = 0; i < snapshot->dynamic_light_count; i++)
		hash = QGE_RegistryHashStep(hash, snapshot->dynamic_lights[i].light_id);
	for (uint32_t i = 0; i < snapshot->particle_count; i++)
		hash = QGE_RegistryHashStep(hash, snapshot->particles[i].particle_id);
	for (uint32_t i = 0; i < snapshot->sound_source_count; i++) {
		hash = QGE_RegistryHashStep(hash, snapshot->sound_sources[i].source_id);
		hash = QGE_RegistryHashStep(hash, snapshot->sound_sources[i].sound_id);
	}
	for (uint32_t i = 0; i < snapshot->entropy_ref_count; i++)
		hash = QGE_RegistryHashStep(hash, snapshot->entropy_refs[i].entropy_event_id);
	return hash;
}

static void QGE_TraceFrameSnapshotProbe(const qge_frame_snapshot_t *snapshot,
										const qge_frame_snapshot_stats_t *stats)
{
	qge_quantum_runtime_t *rt;
	qge_state_probe_t probe;
	uint32_t active_items;
	uint32_t dropped_items;

	if (!snapshot || !stats)
		return;
	rt = QGE_Runtime();
	if (!rt)
		return;

	active_items = stats->visible_surface_count +
				   stats->edict_count +
				   stats->dynamic_light_count +
				   stats->particle_count +
				   stats->sound_source_count +
				   stats->entropy_ref_count;
	dropped_items = stats->dropped_visible_surfaces +
					stats->dropped_edicts +
					stats->dropped_dynamic_lights +
					stats->dropped_particles +
					stats->dropped_sound_sources +
					stats->dropped_entropy_refs;

	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_VISIBILITY;
	probe.representation = QGE_REP_CLASSICAL_ORACLE;
	probe.subject_id = (int32_t)snapshot->world_id;
	probe.flags = (stats->sealed ? 1u : 0u) |
				  (dropped_items ? 2u : 0u);
	probe.state_hash = QGE_FrameSnapshotHash(snapshot, stats);
	probe.entropy = (double)dropped_items;
	probe.coherence = stats->sealed ? 1.0 : 0.0;
	probe.max_probability = (double)stats->visible_surface_count;
	probe.total_probability = (double)active_items;
	probe.active_basis_count = (int32_t)active_items;
	probe.qubit_count = qge_quantum_qubits_for_basis_count(active_items);
	probe.memory_bytes = sizeof(*snapshot);
	strlcpy(probe.label, "frame_snapshot", sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);
}

static void QGE_FrameSnapshotFinalize(void)
{
	qge_frame_snapshot_t *snapshot;
	qge_frame_snapshot_stats_t stats;

	if (!qge_ctx)
		return;
	snapshot = qge_get_frame_snapshot(qge_ctx);
	if (!snapshot || snapshot->sealed)
		return;

	QGE_FrameSnapshotSetCameraAndWorld(snapshot);
	QGE_FrameSnapshotCaptureEdicts(snapshot);
	QGE_FrameSnapshotCaptureLights(snapshot);
	QGE_FrameSnapshotCaptureSounds(snapshot);
	QGE_FrameSnapshotCaptureParticles(snapshot);
	qge_frame_snapshot_seal(snapshot);

	memset(&stats, 0, sizeof(stats));
	qge_frame_snapshot_get_stats(snapshot, &stats);
	QGE_TraceFrameSnapshotProbe(snapshot, &stats);

	if (quantum_debug.value >= 1.0f) {
		if (qge_frame_count < 5 || (qge_frame_count % 60) == 0 ||
			stats.particle_count > 0) {
			Con_Printf("QGE snapshot frame=%d surfaces=%u edicts=%u lights=%u "
					   "particles=%u sounds=%u world=0x%x model=0x%x leaf=%u sealed=%d\n",
					   qge_frame_count,
					   stats.visible_surface_count,
					   stats.edict_count,
					   stats.dynamic_light_count,
					   stats.particle_count,
					   stats.sound_source_count,
					   snapshot->world_id,
					   snapshot->world_model_id,
					   snapshot->view_leaf_index,
					   stats.sealed ? 1 : 0);
		}
		fprintf(stderr, "QGE snapshot frame=%d surfaces=%u edicts=%u lights=%u "
				"particles=%u sounds=%u entropy=%u dropped_surfaces=%u "
				"dropped_edicts=%u dropped_lights=%u dropped_particles=%u "
				"dropped_sounds=%u world=0x%x model=0x%x leaf=%u sealed=%d\n",
				qge_frame_count,
				stats.visible_surface_count,
				stats.edict_count,
				stats.dynamic_light_count,
				stats.particle_count,
				stats.sound_source_count,
				stats.entropy_ref_count,
				stats.dropped_visible_surfaces,
				stats.dropped_edicts,
				stats.dropped_dynamic_lights,
				stats.dropped_particles,
				stats.dropped_sound_sources,
				snapshot->world_id,
				snapshot->world_model_id,
				snapshot->view_leaf_index,
				stats.sealed ? 1 : 0);
	}
}

/* ============================================================================
 * Lifecycle
 * ============================================================================ */

void QGE_Init(void)
{
	if (qge_initialized)
		return;

	fprintf(stderr, "QGE: Init starting...\n");

	Con_Printf("\n======= Quantum Game Engine =======\n");

	/* Register CVars */
	Cvar_RegisterVariable(&quantum_render);
	Cvar_RegisterVariable(&quantum_rng);
	Cvar_RegisterVariable(&quantum_ai);
	Cvar_RegisterVariable(&quantum_particles);
	Cvar_RegisterVariable(&quantum_vis);
	Cvar_RegisterVariable(&quantum_physics);
	Cvar_RegisterVariable(&quantum_projectiles);
	Cvar_RegisterVariable(&quantum_physics_authoritative);
	Cvar_RegisterVariable(&quantum_debug);
	Cvar_RegisterVariable(&qge_noesis_assist);
	Cvar_RegisterVariable(&quantum_overlay_alpha);
	Cvar_RegisterVariable(&quantum_scene_surface_budget);
	Cvar_RegisterVariable(&quantum_render_res);
	Cvar_RegisterVariable(&quantum_render_threshold);
	Cvar_RegisterVariable(&quantum_render_edge_gain);
	Cvar_RegisterVariable(&quantum_render_material_gain);
	Cvar_RegisterVariable(&quantum_render_bilinear_samples);
	Cvar_RegisterVariable(&quantum_render_edge_samples);
	Cvar_RegisterVariable(&quantum_render_display_filter);
	Cvar_RegisterVariable(&quantum_render_update_interval);
	Cvar_RegisterVariable(&quantum_render_gate_kernel);
	Cvar_RegisterVariable(&quantum_render_gate_shots);
	Cvar_RegisterVariable(&quantum_debug_sprite_billboard);
	QGE_ApplyEarlyRenderOverrides();

	fprintf(stderr, "QGE: CVars registered, initializing core...\n");

	/* Initialize QGE core (hardware detection, tier selection) */
	qge_ctx = qge_init();
	if (!qge_ctx) {
		Con_Printf("QGE: Failed to initialize quantum engine\n");
		fprintf(stderr, "QGE: FAILED to initialize quantum engine\n");
		return;
	}

	fprintf(stderr, "QGE: Core initialized, starting RNG...\n");

	/* Initialize quantum RNG early */
	if (qge_rng_init() == 0) {
		Con_Printf("QGE: Quantum RNG initialized (Bell-verified)\n");
		qge_rng_set_runtime(QGE_Runtime());
	} else {
		Con_Printf("QGE: Quantum RNG failed, using classical fallback\n");
	}

	const char *replay_path = QGE_CommandLineReplayPath();
	const char *replay_strict_value = NULL;
	qboolean replay_strict =
		QGE_ParseBoolValue(getenv("QGE_REPLAY_STRICT"), true);
	if (QGE_CommandLineValue("-qgereplaystrict", &replay_strict_value))
		replay_strict = QGE_ParseBoolValue(replay_strict_value, replay_strict);
	if (!replay_path || !replay_path[0])
		replay_path = getenv("QGE_REPLAY_TRACE_PATH");
	if (replay_path && replay_path[0]) {
		qge_quantum_runtime_t *rt = QGE_Runtime();
		qge_quantum_runtime_stats_t replay_stats;

		qge_quantum_runtime_set_replay_strict(rt, replay_strict ? true : false);
		if (qge_quantum_runtime_load_replay_trace(rt, replay_path) == 0) {
			memset(&replay_stats, 0, sizeof(replay_stats));
			qge_quantum_runtime_get_stats(rt, &replay_stats);
			Con_Printf("QGE: Replay trace loaded from %s (strict=%d)\n",
					   replay_path, replay_strict ? 1 : 0);
			fprintf(stderr,
					"QGE replay path=%s strict=%d entropy_loaded=%llu ai_loaded=%llu\n",
					replay_path, replay_strict ? 1 : 0,
					(unsigned long long)replay_stats.replay_events_loaded,
					(unsigned long long)replay_stats.replay_ai_decisions_loaded);
		} else {
			Con_Printf("QGE: Failed to load replay trace %s\n", replay_path);
			fprintf(stderr, "QGE replay load failed path=%s strict=%d\n",
					replay_path, replay_strict ? 1 : 0);
		}
	}

	if (quantum_state_init(&qge_render_gate_state, QGE_RENDER_GATE_QUBITS) == QS_SUCCESS) {
		qge_render_gate_initialized = true;
		Con_Printf("QGE: Render gate kernel initialized (%d qubits)\n",
				   QGE_RENDER_GATE_QUBITS);
	} else {
		qge_render_gate_initialized = false;
		Con_Printf("QGE: Render gate kernel unavailable\n");
	}

	const char *trace_path = QGE_CommandLineTracePath();
	if (!trace_path || !trace_path[0])
		trace_path = getenv("QGE_TRACE_PATH");
	if (trace_path && trace_path[0]) {
		if (qge_quantum_trace_open(QGE_Runtime(), trace_path) == 0) {
			Con_Printf("QGE: Trace recording to %s\n", trace_path);
			fprintf(stderr, "QGE trace path=%s\n", trace_path);
		} else {
			Con_Printf("QGE: Failed to open trace %s\n", trace_path);
			fprintf(stderr, "QGE trace open failed path=%s\n", trace_path);
		}
	}
	QGE_TraceBackendGate("init");

	fprintf(stderr, "QGE: RNG done, creating DWT framebuffers...\n");
	qge_render_res = QGE_ClampRenderResolution(quantum_render_res.value);
	if ((int)quantum_render_res.value != qge_render_res)
		Con_Printf("QGE: quantum_render_res clamped to %d\n", qge_render_res);

	/* Phase 4.1: Create one sparse DWT framebuffer per RGB channel */
	dwt_config_t dwt_cfg = {
		.mode = DWT_MODE_HAAR,
		.num_levels = qge_render_res >= 1024 ? 6 : (qge_render_res >= 512 ? 5 : 4),
		.base_resolution = qge_render_res,
		.gpu_reconstruct = true,
		.sparsity_threshold = quantum_render_threshold.value,
		.quantum_measurement_extract = false
	};
	if (dwt_cfg.sparsity_threshold < 0.0001f)
		dwt_cfg.sparsity_threshold = 0.0001f;
	if (dwt_cfg.sparsity_threshold > 0.10f)
		dwt_cfg.sparsity_threshold = 0.10f;
	qge_dwt_levels = dwt_cfg.num_levels;

	if (dwt_cfg.gpu_reconstruct) {
		void *render_bridge =
			qge_context_get_or_create_render_acceleration(qge_ctx,
														  qge_render_res);
		if (render_bridge) {
			Con_Printf("QGE: Native sparse DWT render bridge active (%dx%d)\n",
					   qge_render_res, qge_render_res);
			fprintf(stderr,
					"QGE render bridge active backend=%s res=%d path=%s\n",
					qge_backend_name(qge_get_backend(qge_ctx)),
					qge_render_res,
					qge_context_backend_runtime_path(qge_ctx));
		} else if (qge_context_backend_native_available(qge_ctx)) {
			Con_Printf("QGE: Native render bridge unavailable, using sparse CPU DWT\n");
			fprintf(stderr,
					"QGE render bridge unavailable backend=%s res=%d reason=%s\n",
					qge_backend_name(qge_get_backend(qge_ctx)),
					qge_render_res,
					qge_context_backend_reason(qge_ctx));
		}
		QGE_TraceBackendGate("render_bridge");
	}

	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++) {
		fprintf(stderr, "QGE: Creating DWT framebuffer channel %d...\n", ch);
		qge_dwt_fb[ch] = qge_dwt_framebuffer_create(qge_ctx, &dwt_cfg);
	}
	if (qge_dwt_fb[QGE_DWT_R] && qge_dwt_fb[QGE_DWT_G] &&
		qge_dwt_fb[QGE_DWT_B]) {
		Con_Printf("QGE: RGB sparse DWT framebuffers created (%dx%d, threshold %.4f)\n",
				   qge_render_res, qge_render_res, dwt_cfg.sparsity_threshold);
	}

	fprintf(stderr, "QGE: Framebuffers created, allocating render buffers...\n");

	/* Allocate render buffers */
	qge_render_buffer = (float *)calloc(qge_render_res * qge_render_res, sizeof(float));
	qge_display_buffer = (uint8_t *)calloc(qge_render_res * qge_render_res * 3, sizeof(uint8_t));
	qge_spatial_encode_buffer = (float *)calloc(qge_render_res * qge_render_res, sizeof(float));
	qge_spatial_depth_buffer = (float *)calloc(qge_render_res * qge_render_res, sizeof(float));
	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++) {
		qge_render_color_buffer[ch] = (float *)calloc(qge_render_res * qge_render_res,
													  sizeof(float));
		qge_spatial_color_buffer[ch] = (float *)calloc(qge_render_res * qge_render_res,
													   sizeof(float));
	}

	/* Create particle system */
	qge_particles = qge_particle_system_create(64);
	if (qge_particles) {
		Con_Printf("QGE: Quantum particle system created (18 qubits)\n");
	}

	fprintf(stderr, "QGE: Creating GL texture...\n");

	/* Create GL texture for quantum framebuffer display */
	glGenTextures(1, &qge_texture);
	glBindTexture(GL_TEXTURE_2D, qge_texture);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
#ifdef GL_CLAMP_TO_EDGE
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
#endif
	glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, qge_render_res, qge_render_res,
				 0, GL_RGB, GL_UNSIGNED_BYTE, NULL);
	glBindTexture(GL_TEXTURE_2D, 0);  /* Unbind — don't corrupt Quake's GL state */
	qge_display_texture_dirty = false;
	qge_render_last_update_frame = -1;
	qge_render_reused_frames = 0;

	qge_blit_texture_units = 1;
	if (GL_SelectTextureFunc) {
		glGetIntegerv(GL_MAX_TEXTURE_UNITS, &qge_blit_texture_units);
		if (qge_blit_texture_units < 1)
			qge_blit_texture_units = 1;
		if (qge_blit_texture_units > 8)
			qge_blit_texture_units = 8;
	}

	/* Phase 4.2: Enable adaptive quality for real-time performance */
	qge_set_adaptive_quality(qge_ctx, true);

	qge_initialized = true;

	fprintf(stderr, "QGE: Init complete!\n");

	Con_Printf("QGE: Engine ready — all quantum subsystems online\n");
	Con_Printf("  quantum_rng %d | quantum_ai %d | quantum_render %d\n",
			   (int)quantum_rng.value, (int)quantum_ai.value,
			   (int)quantum_render.value);
	Con_Printf("  quantum_physics %d | quantum_projectiles %d | quantum_physics_authoritative %d | quantum_particles %d\n",
			   (int)quantum_physics.value, (int)quantum_projectiles.value,
			   (int)quantum_physics_authoritative.value,
			   (int)quantum_particles.value);
	Con_Printf("  RGB sparse DWT | Stable DWT quality | Backend bridge pending\n");
	Con_Printf("===================================\n\n");
}

void QGE_Shutdown(void)
{
	if (!qge_initialized)
		return;

	Con_Printf("QGE: Shutting down quantum engine\n");

	if (qge_avg_frame_ms > 0 && qge_frame_count > 0)
		Con_Printf("QGE: Average quantum render time: %.2f ms (%d frames)\n",
				   qge_avg_frame_ms, qge_frame_count);

	QGE_GameplayOutcomeShutdown();

	if (qge_texture) {
		glDeleteTextures(1, &qge_texture);
		qge_texture = 0;
	}

	if (qge_particles) {
		qge_particle_system_free(qge_particles);
		qge_particles = NULL;
	}

	if (qge_render_gate_initialized) {
		quantum_state_free(&qge_render_gate_state);
		qge_render_gate_initialized = false;
	}

	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++) {
		if (qge_dwt_fb[ch]) {
			qge_dwt_framebuffer_free(qge_dwt_fb[ch]);
			qge_dwt_fb[ch] = NULL;
		}
	}

	free(qge_render_buffer);
	qge_render_buffer = NULL;
	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++) {
		free(qge_render_color_buffer[ch]);
		qge_render_color_buffer[ch] = NULL;
	}
	free(qge_display_buffer);
	qge_display_buffer = NULL;
	qge_display_texture_dirty = false;
	qge_render_last_update_frame = -1;
	qge_render_reused_frames = 0;
	free(qge_spatial_encode_buffer);
	qge_spatial_encode_buffer = NULL;
	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++) {
		free(qge_spatial_color_buffer[ch]);
		qge_spatial_color_buffer[ch] = NULL;
	}
	free(qge_spatial_depth_buffer);
	qge_spatial_depth_buffer = NULL;

	qge_rng_set_runtime(NULL);
	qge_rng_shutdown();

	if (qge_ctx) {
		qge_quantum_runtime_stats_t replay_stats;

		memset(&replay_stats, 0, sizeof(replay_stats));
		qge_quantum_runtime_get_stats(QGE_Runtime(), &replay_stats);
		if (replay_stats.replay_events_loaded ||
			replay_stats.replay_ai_decisions_loaded ||
			replay_stats.replay_events_consumed ||
			replay_stats.replay_ai_decisions_consumed) {
			fprintf(stderr,
					"QGE replay stats entropy_loaded=%llu entropy_consumed=%llu entropy_mismatches=%llu entropy_exhaustions=%llu ai_loaded=%llu ai_consumed=%llu ai_mismatches=%llu ai_exhaustions=%llu\n",
					(unsigned long long)replay_stats.replay_events_loaded,
					(unsigned long long)replay_stats.replay_events_consumed,
					(unsigned long long)replay_stats.replay_mismatches,
					(unsigned long long)replay_stats.replay_exhaustions,
					(unsigned long long)replay_stats.replay_ai_decisions_loaded,
					(unsigned long long)replay_stats.replay_ai_decisions_consumed,
					(unsigned long long)replay_stats.replay_ai_decision_mismatches,
					(unsigned long long)replay_stats.replay_ai_decision_exhaustions);
		}
		QGE_TraceBackendGate("shutdown");
		qge_shutdown(qge_ctx);
		qge_ctx = NULL;
	}

	qge_initialized = false;
}

void QGE_FrameBegin(void)
{
	if (!qge_initialized) return;
	qge_frame_start = Sys_DoubleTime();
	qge_quantum_frame_begin(QGE_Runtime(), qge_frame_count, QGE_ServerTimeMsec());
	QGE_RegisterWorldIfNeeded();
	qge_render_collect_frame = QGE_RenderShouldUpdateFrame();
	QGE_FrameSnapshotBeginCurrent();
	QGE_SceneBegin();
	QGE_NoesisAssistResetFrame();
	qge_phys_toss_count = 0;
	qge_phys_projectile_count = 0;
	qge_phys_impact_count = 0;
	qge_phys_particle_spawns = 0;
	qge_phys_registry_purged = 0;
	qge_phys_mirrored_bounds = 0;
	qge_phys_mirrored_owner = 0;
	qge_phys_mirrored_water = 0;
	qge_phys_mirrored_impacts = 0;
	qge_phys_projectile_writeback_decisions = 0;
	qge_phys_projectile_writeback_selected = 0;
	qge_phys_projectile_writeback_fallback = 0;
	qge_phys_projectile_writeback_rollback = 0;
	qge_phys_projectile_branch_states = 0;
	qge_phys_projectile_impact_measurements = 0;
	qge_phys_projectile_preimpact_decisions = 0;
	qge_phys_projectile_preimpact_selected = 0;
	qge_phys_projectile_preimpact_collisions = 0;
	qge_phys_projectile_preimpact_oracle_traces = 0;
	qge_phys_projectile_preimpact_noimpact = 0;
	qge_phys_projectile_preimpact_alternate_impacts = 0;
}

static void QGE_TraceWorldSurfaceSubmissionProbe(qge_quantum_runtime_t *rt)
{
	qge_state_probe_t probe;
	uint64_t hash;
	uint32_t flags = 0u;

	if (!rt || (!qge_scene_world_surfaces && !qge_scene_surface_count &&
				!qge_scene_surface_dropped))
		return;

	if (qge_render_collect_frame)
		flags |= 0x1u;
	if (qge_scene_surface_dropped > 0)
		flags |= 0x2u;
	if (qge_scene_snapshot_surfaces > 0)
		flags |= 0x4u;

	hash = QGE_RegistryHashStep((uint64_t)qge_frame_count,
								(uint64_t)qge_scene_world_surfaces);
	hash = QGE_RegistryHashStep(hash, (uint64_t)qge_scene_surface_count);
	hash = QGE_RegistryHashStep(hash, (uint64_t)qge_scene_surface_dropped);
	hash = QGE_RegistryHashStep(hash, (uint64_t)qge_scene_snapshot_surfaces);
	hash = QGE_RegistryHashStep(hash, (uint64_t)qge_scene_snapshot_misses);

	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_RENDER;
	probe.representation = QGE_REP_CLASSICAL_ORACLE;
	probe.subject_id = qge_scene_world_surfaces;
	probe.flags = flags;
	probe.state_hash = hash;
	probe.entropy = qge_scene_world_surfaces > 0 ?
		(double)qge_scene_surface_count / (double)qge_scene_world_surfaces : 0.0;
	probe.coherence = qge_scene_surface_dropped > 0 ? 0.0 : 1.0;
	probe.max_probability = (double)qge_scene_surface_dropped;
	probe.total_probability = (double)qge_scene_world_surfaces;
	probe.active_basis_count = qge_scene_surface_count;
	probe.qubit_count =
		qge_quantum_qubits_for_basis_count(qge_scene_surface_count);
	probe.memory_bytes = (uint64_t)qge_scene_surface_count *
						 (uint64_t)sizeof(qge_scene_surface_t);
	strlcpy(probe.label, "world_surface_submission", sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);
}

void QGE_FrameEnd(void)
{
	if (!qge_initialized) return;

	double elapsed = (Sys_DoubleTime() - qge_frame_start) * 1000.0;
	qge_avg_frame_ms = qge_avg_frame_ms * 0.95 + elapsed * 0.05;
	QGE_RegisterWorldIfNeeded();
	QGE_PhysicsRefreshStats();
	QGE_PhysicsUpdateProjectileAuthorityGate();
	QGE_FrameSnapshotFinalize();
	QGE_GameplayOutcomeSample();
	qge_quantum_runtime_t *rt = QGE_Runtime();
	if (rt) {
		qge_state_probe_t probe;
		qge_quantum_runtime_stats_t stats;

		memset(&probe, 0, sizeof(probe));
		probe.frame = qge_frame_count;
		probe.server_time_msec = QGE_ServerTimeMsec();
		probe.domain = QGE_DOMAIN_PHYSICS;
		probe.representation = QGE_REP_CLASSICAL_ORACLE;
		probe.active_basis_count = qge_phys_active_objects;
		probe.qubit_count =
			qge_quantum_qubits_for_basis_count((uint64_t)qge_phys_active_objects);
		probe.max_probability = qge_phys_max_shadow_error;
		probe.total_probability = qge_phys_avg_shadow_error;
		strlcpy(probe.label, "physics_shadow", sizeof(probe.label));
		qge_quantum_record_probe(rt, &probe);

		QGE_TraceProjectileAuthorityGate(rt);

		memset(&stats, 0, sizeof(stats));
		qge_quantum_runtime_get_stats(rt, &stats);
		memset(&probe, 0, sizeof(probe));
		probe.frame = qge_frame_count;
		probe.server_time_msec = QGE_ServerTimeMsec();
		probe.domain = QGE_DOMAIN_RNG;
		probe.representation = QGE_REP_DENSE_STATE;
		probe.active_basis_count = (int)stats.entropy_events;
		probe.qubit_count =
			qge_quantum_qubits_for_basis_count(stats.entropy_events);
		probe.total_probability = (double)stats.entropy_events;
		strlcpy(probe.label, "rng_entropy", sizeof(probe.label));
		qge_quantum_record_probe(rt, &probe);

		QGE_TraceWorldSurfaceSubmissionProbe(rt);
	}

	if (quantum_debug.value >= 1.0f &&
		(qge_phys_toss_count || qge_phys_projectile_count || qge_phys_impact_count)) {
		int active_particles = qge_particles ? qge_particle_system_active_count(qge_particles) : 0;
		fprintf(stderr, "QGE physics frame=%d toss=%d projectiles=%d impacts=%d "
				"tracked=%d active_projectiles=%d purged=%d "
				"mirrored_bounds=%d mirrored_owner=%d mirrored_water=%d mirrored_impacts=%d "
				"shadow_avg=%.2f shadow_max=%.2f "
				"projectile_authority=%s reason=%s requested=%d authoritative_cvar=%d warmup=%d samples=%d "
				"pshadow_avg=%.2f pshadow_max=%.2f ready_frames=%d off_frames=%d "
				"pwriteback decisions=%d selected=%d fallback=%d rollback=%d "
				"branch_states=%d impact_measurements=%d "
				"preimpact decisions=%d selected=%d collisions=%d "
				"oracle_traces=%d noimpact=%d alternate_impacts=%d "
				"qparticle_spawns=%d active_qparticles=%d frame_ms=%.2f\n",
				qge_frame_count, qge_phys_toss_count, qge_phys_projectile_count,
				qge_phys_impact_count, qge_phys_active_objects,
				qge_phys_active_projectiles, qge_phys_registry_purged,
				qge_phys_mirrored_bounds, qge_phys_mirrored_owner,
				qge_phys_mirrored_water, qge_phys_mirrored_impacts,
				qge_phys_avg_shadow_error, qge_phys_max_shadow_error,
				qge_phys_projectile_authority_ready ? "ready" : "off",
				qge_projectile_authority_off_reason_name(
					qge_phys_projectile_authority_off_reason),
				QGE_PhysicsProjectileAuthorityRequested() ? 1 : 0,
				quantum_physics_authoritative.value >= 0.5f ? 1 : 0,
				qge_phys_projectile_authority_warmup_frames,
				qge_phys_projectile_shadow_samples,
				qge_phys_projectile_avg_shadow_error,
				qge_phys_projectile_max_shadow_error,
				qge_phys_projectile_authority_ready_frames,
				qge_phys_projectile_authority_off_frames,
				qge_phys_projectile_writeback_decisions,
				qge_phys_projectile_writeback_selected,
				qge_phys_projectile_writeback_fallback,
				qge_phys_projectile_writeback_rollback,
				qge_phys_projectile_branch_states,
				qge_phys_projectile_impact_measurements,
				qge_phys_projectile_preimpact_decisions,
				qge_phys_projectile_preimpact_selected,
				qge_phys_projectile_preimpact_collisions,
				qge_phys_projectile_preimpact_oracle_traces,
				qge_phys_projectile_preimpact_noimpact,
				qge_phys_projectile_preimpact_alternate_impacts,
				qge_phys_particle_spawns,
				active_particles, elapsed);
	}

	if (quantum_debug.value >= 1.0f && qge_scene_surface_count) {
		fprintf(stderr, "QGE scene frame=%d world_surfaces=%d submitted=%d dropped=%d "
				"snapshot=%d snapshot_miss=%d encoded=%d material_encoded=%d "
				"tex=%d texcache=%d/%d entries=%d light=%d lightcache=%d/%d "
				"light_entries=%d poly=%d culled=%d surrogate=%d micro=%d clipped=%d invalid=%d "
				"fallback=%d sky=%d water=%d\n",
				qge_frame_count, qge_scene_world_surfaces, qge_scene_surface_count,
				qge_scene_surface_dropped, qge_scene_snapshot_surfaces,
				qge_scene_snapshot_misses, qge_scene_encoded_surfaces,
				qge_scene_material_encoded, qge_scene_textured_surfaces,
				qge_scene_texture_cache_hits, qge_scene_texture_cache_misses,
				qge_texture_signal_cache_entries, qge_scene_lightmapped_surfaces,
				qge_scene_lightmap_cache_hits, qge_scene_lightmap_cache_misses,
				qge_lightmap_signal_cache_entries, qge_scene_polygon_encoded,
				qge_scene_polygon_culled,
				qge_scene_polygon_surrogate, qge_scene_polygon_surrogate_micro,
				qge_scene_polygon_surrogate_clipped,
				qge_scene_polygon_surrogate_invalid,
				qge_scene_polygon_fallback,
				qge_scene_sky_surfaces, qge_scene_water_surfaces);
	}

	qge_quantum_frame_end(rt);
	qge_frame_count++;

}

/* ============================================================================
 * Quantum RNG
 * ============================================================================ */

int QGE_Random(void)
{
	if (!qge_initialized || quantum_rng.value < 0.5f)
		return rand();

	return (int)(qge_random() & 0x7FFF);
}

float QGE_RandomFloat(void)
{
	if (!qge_initialized || quantum_rng.value < 0.5f)
		return (rand() & 0x7fff) / ((float)0x7fff);

	return qge_random_float();
}

/* ============================================================================
 * Quantum Rendering
 * ============================================================================ */

void QGE_SceneBegin(void)
{
	qge_scene_surface_count = 0;
	qge_scene_surface_dropped = 0;
	qge_scene_world_surfaces = 0;
	qge_scene_sky_surfaces = 0;
	qge_scene_water_surfaces = 0;
	qge_scene_encoded_surfaces = 0;
	qge_scene_textured_surfaces = 0;
	qge_scene_lightmapped_surfaces = 0;
	qge_scene_material_encoded = 0;
	qge_scene_snapshot_surfaces = 0;
	qge_scene_snapshot_misses = 0;
	qge_scene_texture_cache_hits = 0;
	qge_scene_texture_cache_misses = 0;
	qge_scene_lightmap_cache_hits = 0;
	qge_scene_lightmap_cache_misses = 0;
	qge_scene_polygon_encoded = 0;
	qge_scene_polygon_fallback = 0;
	qge_scene_polygon_surrogate = 0;
	qge_scene_polygon_surrogate_micro = 0;
	qge_scene_polygon_surrogate_clipped = 0;
	qge_scene_polygon_surrogate_invalid = 0;
	qge_scene_polygon_culled = 0;
	qge_scene_polygon_triangles = 0;
	qge_scene_triangle_edge_fills = 0;
	qge_scene_polygon_micro_fills = 0;
	qge_scene_snapshot_edicts = 0;
	qge_scene_encoded_edicts = 0;
	qge_scene_alias_encoded = 0;
	qge_scene_sprite_encoded = 0;
	qge_scene_viewmodel_encoded = 0;
	qge_scene_entity_misses = 0;
	qge_scene_entity_coefficients = 0;
	qge_scene_entity_mesh_triangles = 0;
	qge_scene_sprite_billboards = 0;
	qge_scene_snapshot_particles = 0;
	qge_scene_encoded_particles = 0;
	qge_scene_particle_coefficients = 0;
	qge_scene_setup_ms = 0.0;
	qge_scene_raster_ms = 0.0;
	qge_scene_forward_dwt_ms = 0.0;
	QGE_ResetRenderGateTelemetry();
}

static float QGE_SurfaceBrightness(const qge_scene_surface_t *surface)
{
	const msurface_t *surf;
	float brightness;

	if (!surface)
		return 0.25f;
	surf = surface->surf;
	if (!surf)
		return 0.25f;

	if (surface->light_energy > 0.0f || surface->light_contrast > 0.0f) {
		brightness = 0.18f + surface->light_energy * 0.72f +
					 surface->light_contrast * 0.18f;
	} else if (surf->samples) {
		brightness = 0.48f;
	} else {
		brightness = 0.42f;
	}

	brightness = brightness * 0.72f + surface->material_signal * 0.28f;

	if (surface->flags & SURF_DRAWSKY)
		return 0.08f;
	if (surface->flags & SURF_DRAWLAVA)
		brightness = fmaxf(brightness, 0.85f);
	if (surface->flags & SURF_DRAWTELE)
		brightness = fmaxf(brightness, 0.75f);
	if (surface->flags & (SURF_DRAWWATER | SURF_DRAWTURB | SURF_DRAWSLIME))
		brightness = brightness * 0.55f + 0.32f * 0.45f;
	if (surface->has_fullbright)
		brightness = fmaxf(brightness, 0.72f);
	if (brightness < 0.08f)
		brightness = 0.08f;
	if (brightness > 1.0f)
		brightness = 1.0f;
	return brightness;
}

static unsigned int QGE_HashStep(unsigned int hash, unsigned int value)
{
	hash ^= value;
	hash *= 16777619u;
	return hash;
}

static unsigned int QGE_TextureSignalBuild(const texture_t *tex,
										   qge_texture_signal_cache_t *out)
{
	const gltexture_t *glt;
	unsigned int hash = 2166136261u;
	qge_texture_signal_cache_t local;

	if (!tex)
		return hash;

	memset(&local, 0, sizeof(local));
	for (int i = 0; i < (int)sizeof(tex->name) && tex->name[i]; i++)
		hash = QGE_HashStep(hash, (unsigned char)tex->name[i]);

	glt = tex->gltexture;
	if (glt) {
		local.texture_crc = glt->source_crc;
		local.texture_width = glt->source_width;
		local.texture_height = glt->source_height;
		local.texture_format = (unsigned int)glt->source_format;
		hash = QGE_HashStep(hash, glt->source_crc);
		hash = QGE_HashStep(hash, glt->source_width);
		hash = QGE_HashStep(hash, glt->source_height);
		hash = QGE_HashStep(hash, (unsigned int)glt->source_format);
	}

	if (tex->fullbright) {
		local.has_fullbright = true;
		hash = QGE_HashStep(hash, tex->fullbright->source_crc ^ 0xf00du);
	}
	if (tex->warpimage) {
		local.has_warp = true;
		hash = QGE_HashStep(hash, tex->warpimage->source_crc ^ 0x5a5au);
	}

	local.valid = true;
	local.texture_hash = hash;
	if (out)
		*out = local;
	return hash;
}

static void QGE_ApplyTextureSignal(const qge_texture_signal_cache_t *signal,
								   qge_scene_surface_t *dst)
{
	if (!signal || !dst)
		return;
	dst->texture_hash = signal->texture_hash;
	dst->texture_crc = signal->texture_crc;
	dst->texture_width = signal->texture_width;
	dst->texture_height = signal->texture_height;
	dst->texture_format = signal->texture_format;
	dst->has_fullbright = signal->has_fullbright;
	dst->has_warp = signal->has_warp;
}

static unsigned int QGE_SurfaceTextureSignal(const texture_t *tex,
											 int texture_index,
											 qge_scene_surface_t *dst)
{
	qge_texture_signal_cache_t signal;

	if (!dst)
		return 2166136261u;
	if (texture_index >= 0 &&
		texture_index < QGE_MAX_TEXTURE_SIGNAL_CACHE &&
		qge_texture_signal_cache[texture_index].valid) {
		QGE_ApplyTextureSignal(&qge_texture_signal_cache[texture_index], dst);
		qge_scene_texture_cache_hits++;
		return dst->texture_hash;
	}

	qge_scene_texture_cache_misses++;
	QGE_TextureSignalBuild(tex, &signal);
	QGE_ApplyTextureSignal(&signal, dst);
	return dst->texture_hash;
}

static unsigned int QGE_SurfaceLightSignal(const msurface_t *surf,
										   float *energy,
										   float *contrast)
{
	unsigned int hash = 2166136261u;
	int width, height, samples, bytes_per_sample, step;
	double sum = 0.0;
	double sum_sq = 0.0;
	int count = 0;

	*energy = 0.0f;
	*contrast = 0.0f;

	if (!surf || !surf->samples)
		return hash;

	width = (surf->extents[0] >> 4) + 1;
	height = (surf->extents[1] >> 4) + 1;
	samples = width * height;
	if (samples <= 0)
		return hash;

	bytes_per_sample = lightmap_bytes;
	if (bytes_per_sample <= 0)
		bytes_per_sample = 3;
	step = samples > 96 ? samples / 96 : 1;

	for (int i = 0; i < samples; i += step) {
		const byte *p = surf->samples + i * bytes_per_sample;
		unsigned int lum;

		if (bytes_per_sample >= 3)
			lum = ((unsigned int)p[0] + (unsigned int)p[1] + (unsigned int)p[2]) / 3u;
		else
			lum = (unsigned int)p[0];

		hash = QGE_HashStep(hash, lum + (unsigned int)i);
		sum += (double)lum;
		sum_sq += (double)lum * (double)lum;
		count++;
	}

	if (count > 0) {
		double mean = sum / (double)count;
		double variance = sum_sq / (double)count - mean * mean;
		if (variance < 0.0)
			variance = 0.0;
		*energy = (float)(mean / 255.0);
		*contrast = (float)(sqrt(variance) / 255.0);
	}

	return hash;
}

static unsigned int QGE_CachedSurfaceLightSignal(int surface_index,
												 const msurface_t *surf,
												 float *energy,
												 float *contrast)
{
	if (surface_index >= 0 &&
		surface_index < QGE_MAX_LIGHTMAP_SIGNAL_CACHE &&
		qge_lightmap_signal_cache[surface_index].valid) {
		*energy = qge_lightmap_signal_cache[surface_index].light_energy;
		*contrast = qge_lightmap_signal_cache[surface_index].light_contrast;
		qge_scene_lightmap_cache_hits++;
		return qge_lightmap_signal_cache[surface_index].light_hash;
	}

	qge_scene_lightmap_cache_misses++;
	return QGE_SurfaceLightSignal(surf, energy, contrast);
}

static float QGE_SurfaceMaterialSignal(const qge_scene_surface_t *surface)
{
	float signal = 0.25f;

	if (!surface)
		return signal;

	if (surface->flags & SURF_DRAWSKY)
		signal += 0.10f;
	if (surface->flags & (SURF_DRAWWATER | SURF_DRAWTURB | SURF_DRAWSLIME))
		signal += 0.22f;
	if (surface->flags & SURF_DRAWLAVA)
		signal += 0.34f;
	if (surface->flags & SURF_DRAWTELE)
		signal += 0.30f;
	if (surface->flags & SURF_DRAWFENCE)
		signal += 0.18f;
	if (surface->has_fullbright)
		signal += 0.16f;
	if (surface->has_warp)
		signal += 0.12f;

	signal += surface->light_energy * 0.20f;
	signal += surface->light_contrast * 0.18f;
	if (signal > 1.0f)
		signal = 1.0f;
	return signal;
}

void QGE_SceneSubmitWorldSurface(qmodel_t *model, msurface_t *surf)
{
	qge_scene_surface_t *dst;
	texture_t *tex;
	int i;

	if (!qge_initialized || !model || !surf)
		return;
	if (!qge_render_collect_frame)
		return;

	qge_scene_world_surfaces++;
	if (surf->flags & SURF_DRAWSKY)
		qge_scene_sky_surfaces++;
	if (surf->flags & (SURF_DRAWWATER | SURF_DRAWTURB | SURF_DRAWSLIME | SURF_DRAWLAVA))
		qge_scene_water_surfaces++;

	if (qge_scene_surface_count >= QGE_MAX_SCENE_SURFACES) {
		qge_scene_surface_dropped++;
		return;
	}

	dst = &qge_scene_surfaces[qge_scene_surface_count++];
	memset(dst, 0, sizeof(*dst));

	if (surf >= model->surfaces && surf < model->surfaces + model->numsurfaces)
		dst->surface_id = (int)(surf - model->surfaces);
	else
		dst->surface_id = qge_scene_world_surfaces - 1;

	tex = surf->texinfo ? surf->texinfo->texture : NULL;
	dst->surf = surf;
	dst->texture_id = -1;
	if (tex) {
		for (i = 0; i < model->numtextures; i++) {
			if (model->textures[i] == tex) {
				dst->texture_id = i;
				break;
			}
		}
	}
	dst->flags = surf->flags;
	dst->lightmap = surf->lightmaptexturenum;
	dst->light_hash = QGE_CachedSurfaceLightSignal(dst->surface_id, surf,
												  &dst->light_energy,
												  &dst->light_contrast);
	if (surf->samples)
		qge_scene_lightmapped_surfaces++;
	VectorCopy(surf->mins, dst->mins);
	VectorCopy(surf->maxs, dst->maxs);
	VectorAdd(surf->mins, surf->maxs, dst->centroid);
	VectorScale(dst->centroid, 0.5f, dst->centroid);

	if (tex) {
		dst->texture_hash = QGE_SurfaceTextureSignal(tex, dst->texture_id, dst);
		dst->material_signal = QGE_SurfaceMaterialSignal(dst);
		qge_scene_textured_surfaces++;
		for (i = 0; i < (int)sizeof(dst->texture_name) - 1 && tex->name[i]; i++)
			dst->texture_name[i] = tex->name[i];
		dst->texture_name[i] = 0;
	} else
		dst->material_signal = QGE_SurfaceMaterialSignal(dst);
	dst->brightness = QGE_SurfaceBrightness(dst);

	dst->numverts = surf->polys ? surf->polys->numverts : surf->numedges;
	{
		vec3_t view_delta;
		VectorSubtract(dst->centroid, r_refdef.vieworg, view_delta);
		dst->depth = DotProduct(view_delta, vpn);
	}
	QGE_FrameSnapshotAddVisibleSurface(dst);
}

static qboolean QGE_ProjectPoint(const vec3_t world, float *x, float *y, float *depth)
{
	vec3_t view_delta;
	float dist, scale;

	VectorSubtract(world, r_refdef.vieworg, view_delta);
	dist = DotProduct(view_delta, vpn);
	if (dist < 1.0f)
		return false;

	scale = (float)qge_render_res / (dist * 2.0f);
	*x = (float)qge_render_res * 0.5f + DotProduct(view_delta, vright) * scale;
	*y = (float)qge_render_res * 0.5f - DotProduct(view_delta, vup) * scale;
	*depth = dist;
	return true;
}

static float QGE_ViewDepth(const vec3_t world)
{
	vec3_t view_delta;

	VectorSubtract(world, r_refdef.vieworg, view_delta);
	return DotProduct(view_delta, vpn);
}

static void QGE_AddClipVertex(qge_clip_vertex_t *out,
							  int *count,
							  int max_count,
							  const qge_clip_vertex_t *vertex)
{
	if (!out || !count || *count >= max_count)
		return;
	out[*count] = *vertex;
	(*count)++;
}

static void QGE_SetClipVertexFromPoly(const glpoly_t *poly,
									  int index,
									  qge_clip_vertex_t *vertex)
{
	if (!poly || !vertex)
		return;
	vertex->world[0] = poly->verts[index][0];
	vertex->world[1] = poly->verts[index][1];
	vertex->world[2] = poly->verts[index][2];
	vertex->depth = QGE_ViewDepth(vertex->world);
	vertex->tex_s = poly->verts[index][3];
	vertex->tex_t = poly->verts[index][4];
	vertex->light_s = poly->verts[index][5];
	vertex->light_t = poly->verts[index][6];
}

static void QGE_IntersectNearPlane(const qge_clip_vertex_t *a,
								   const qge_clip_vertex_t *b,
								   qge_clip_vertex_t *out)
{
	float denom;
	float t;

	if (!a || !b || !out)
		return;

	denom = b->depth - a->depth;
	if (fabsf(denom) < 0.0001f)
		t = 0.0f;
	else
		t = (1.0f - a->depth) / denom;
	if (t < 0.0f) t = 0.0f;
	if (t > 1.0f) t = 1.0f;

	out->world[0] = a->world[0] + (b->world[0] - a->world[0]) * t;
	out->world[1] = a->world[1] + (b->world[1] - a->world[1]) * t;
	out->world[2] = a->world[2] + (b->world[2] - a->world[2]) * t;
	out->depth = 1.0f;
	out->tex_s = a->tex_s + (b->tex_s - a->tex_s) * t;
	out->tex_t = a->tex_t + (b->tex_t - a->tex_t) * t;
	out->light_s = a->light_s + (b->light_s - a->light_s) * t;
	out->light_t = a->light_t + (b->light_t - a->light_t) * t;
}

static int QGE_ClipSurfacePolygonNear(const glpoly_t *poly,
									  qge_clip_vertex_t *out,
									  int max_count)
{
	qge_clip_vertex_t prev;
	qboolean prev_inside;
	int count = 0;

	if (!poly || !out || max_count <= 0 || poly->numverts < 3)
		return 0;

	QGE_SetClipVertexFromPoly(poly, poly->numverts - 1, &prev);
	prev_inside = prev.depth >= 1.0f;

	for (int i = 0; i < poly->numverts; i++) {
		qge_clip_vertex_t cur;
		qboolean cur_inside;

		QGE_SetClipVertexFromPoly(poly, i, &cur);
		cur_inside = cur.depth >= 1.0f;

		if (prev_inside && cur_inside) {
			QGE_AddClipVertex(out, &count, max_count, &cur);
		} else if (prev_inside && !cur_inside) {
			qge_clip_vertex_t hit;
			QGE_IntersectNearPlane(&prev, &cur, &hit);
			QGE_AddClipVertex(out, &count, max_count, &hit);
		} else if (!prev_inside && cur_inside) {
			qge_clip_vertex_t hit;
			QGE_IntersectNearPlane(&prev, &cur, &hit);
			QGE_AddClipVertex(out, &count, max_count, &hit);
			QGE_AddClipVertex(out, &count, max_count, &cur);
		}

		prev = cur;
		prev_inside = cur_inside;
	}

	return count;
}

static qge_projected_vertex_t QGE_ProjectVertexLerp(
	const qge_projected_vertex_t *a,
	const qge_projected_vertex_t *b,
	float t)
{
	qge_projected_vertex_t out;

	if (t < 0.0f) t = 0.0f;
	if (t > 1.0f) t = 1.0f;
	out.x = a->x + (b->x - a->x) * t;
	out.y = a->y + (b->y - a->y) * t;
	out.depth = a->depth + (b->depth - a->depth) * t;
	out.tex_s = a->tex_s + (b->tex_s - a->tex_s) * t;
	out.tex_t = a->tex_t + (b->tex_t - a->tex_t) * t;
	out.light_s = a->light_s + (b->light_s - a->light_s) * t;
	out.light_t = a->light_t + (b->light_t - a->light_t) * t;
	return out;
}

static float QGE_ProjectVertexClipDistance(const qge_projected_vertex_t *v,
										   int plane)
{
	float max_coord = (float)(qge_render_res - 1);

	switch (plane) {
	case 0: return v->x;
	case 1: return max_coord - v->x;
	case 2: return v->y;
	default: return max_coord - v->y;
	}
}

static int QGE_ClipProjectedPolygonPlane(const qge_projected_vertex_t *in,
										 int in_count,
										 qge_projected_vertex_t *out,
										 int max_count,
										 int plane)
{
	qge_projected_vertex_t prev;
	float prev_dist;
	qboolean prev_inside;
	int out_count = 0;

	if (!in || !out || in_count <= 0 || max_count <= 0)
		return 0;

	prev = in[in_count - 1];
	prev_dist = QGE_ProjectVertexClipDistance(&prev, plane);
	prev_inside = prev_dist >= -0.001f;

	for (int i = 0; i < in_count; i++) {
		qge_projected_vertex_t cur = in[i];
		float cur_dist = QGE_ProjectVertexClipDistance(&cur, plane);
		qboolean cur_inside = cur_dist >= -0.001f;

		if (prev_inside != cur_inside && out_count < max_count) {
			float denom = prev_dist - cur_dist;
			float t = fabsf(denom) > 0.0001f ? prev_dist / denom : 0.0f;
			out[out_count++] = QGE_ProjectVertexLerp(&prev, &cur, t);
		}
		if (cur_inside && out_count < max_count)
			out[out_count++] = cur;

		prev = cur;
		prev_dist = cur_dist;
		prev_inside = cur_inside;
	}

	return out_count;
}

static int QGE_ClipProjectedPolygonViewport(const qge_projected_vertex_t *in,
											int in_count,
											qge_projected_vertex_t *out,
											int max_count)
{
	qge_projected_vertex_t tmp_a[QGE_MAX_PROJECTED_POLY_VERTS];
	qge_projected_vertex_t tmp_b[QGE_MAX_PROJECTED_POLY_VERTS];
	int count;

	if (!in || !out || in_count < 3 || max_count < 3)
		return 0;
	if (in_count > QGE_MAX_PROJECTED_POLY_VERTS)
		in_count = QGE_MAX_PROJECTED_POLY_VERTS;

	for (int i = 0; i < in_count; i++)
		tmp_a[i] = in[i];
	count = in_count;

	for (int plane = 0; plane < 4 && count >= 3; plane++) {
		if ((plane & 1) == 0)
			count = QGE_ClipProjectedPolygonPlane(tmp_a, count, tmp_b,
												  QGE_MAX_PROJECTED_POLY_VERTS,
												  plane);
		else
			count = QGE_ClipProjectedPolygonPlane(tmp_b, count, tmp_a,
												  QGE_MAX_PROJECTED_POLY_VERTS,
												  plane);
	}

	if (count < 3)
		return 0;

	if ((4 & 1) == 0) {
		for (int i = 0; i < count && i < max_count; i++)
			out[i] = tmp_a[i];
	} else {
		for (int i = 0; i < count && i < max_count; i++)
			out[i] = tmp_b[i];
	}
	return count < max_count ? count : max_count;
}

static qboolean QGE_SurfaceScreenBounds(const qge_scene_surface_t *surface,
										const msurface_t *surf,
										screen_rect_t *bounds,
										float *depth)
{
	float min_x = (float)qge_render_res;
	float min_y = (float)qge_render_res;
	float max_x = 0.0f;
	float max_y = 0.0f;
	float depth_sum = 0.0f;
	int projected = 0;
	glpoly_t *poly = surf ? surf->polys : NULL;

	if (poly) {
		qge_clip_vertex_t clipped[QGE_MAX_PROJECTED_POLY_VERTS];
		int clipped_count = QGE_ClipSurfacePolygonNear(poly, clipped,
													   QGE_MAX_PROJECTED_POLY_VERTS);
		for (int i = 0; i < clipped_count; i++) {
			float sx, sy, sd;
			if (!QGE_ProjectPoint(clipped[i].world, &sx, &sy, &sd))
				continue;
			if (sx < min_x) min_x = sx;
			if (sy < min_y) min_y = sy;
			if (sx > max_x) max_x = sx;
			if (sy > max_y) max_y = sy;
			depth_sum += sd;
			projected++;
		}
	}

	if (!projected) {
		float sx, sy, sd;
		if (!QGE_ProjectPoint(surface->centroid, &sx, &sy, &sd))
			return false;
		min_x = sx - 2.0f;
		max_x = sx + 2.0f;
		min_y = sy - 2.0f;
		max_y = sy + 2.0f;
		depth_sum = sd;
		projected = 1;
	}

	if (min_x < 0.0f) min_x = 0.0f;
	if (min_y < 0.0f) min_y = 0.0f;
	if (max_x > qge_render_res - 1) max_x = (float)(qge_render_res - 1);
	if (max_y > qge_render_res - 1) max_y = (float)(qge_render_res - 1);
	if (max_x <= min_x) max_x = min_x + 1.0f;
	if (max_y <= min_y) max_y = min_y + 1.0f;

	bounds->x1 = (int)min_x;
	bounds->y1 = (int)min_y;
	bounds->x2 = (int)max_x;
	bounds->y2 = (int)max_y;
	*depth = depth_sum / (float)projected;
	return true;
}

static qboolean QGE_ProjectSurfaceFail(qge_project_fail_reason_t *fail_reason,
									   qge_project_fail_reason_t reason)
{
	if (fail_reason)
		*fail_reason = reason;
	return false;
}

static qboolean QGE_ProjectSurfacePolygon(const qge_scene_surface_t *surface,
										  const msurface_t *surf,
										  qge_projected_vertex_t *verts,
										  int max_verts,
										  int *num_verts,
										  screen_rect_t *bounds,
										  float *depth,
										  float *area,
										  qge_project_fail_reason_t *fail_reason)
{
	glpoly_t *poly = surf ? surf->polys : NULL;
	float min_x = (float)qge_render_res;
	float min_y = (float)qge_render_res;
	float max_x = 0.0f;
	float max_y = 0.0f;
	float depth_sum = 0.0f;
	float signed_area = 0.0f;
	int count = 0;
	qge_clip_vertex_t clipped[QGE_MAX_PROJECTED_POLY_VERTS];
	qge_projected_vertex_t projected[QGE_MAX_PROJECTED_POLY_VERTS];
	int clipped_count;
	int clipped_projected_count;

	if (!surface || !poly || !verts || !num_verts || !bounds || !depth || !area)
		return QGE_ProjectSurfaceFail(fail_reason,
									  poly ? QGE_PROJECT_FAIL_INVALID :
									  QGE_PROJECT_FAIL_NO_POLY);
	if (fail_reason)
		*fail_reason = QGE_PROJECT_FAIL_NONE;
	if (max_verts > QGE_MAX_PROJECTED_POLY_VERTS)
		max_verts = QGE_MAX_PROJECTED_POLY_VERTS;

	clipped_count = QGE_ClipSurfacePolygonNear(poly, clipped,
											   QGE_MAX_PROJECTED_POLY_VERTS);
	if (clipped_count < 3)
		return QGE_ProjectSurfaceFail(fail_reason,
									  QGE_PROJECT_FAIL_NEAR_CLIP_EMPTY);

	for (int i = 0; i < clipped_count && count < max_verts; i++) {
		float sx, sy, sd;
		if (!QGE_ProjectPoint(clipped[i].world, &sx, &sy, &sd))
			continue;

		projected[count].x = sx;
		projected[count].y = sy;
		projected[count].depth = sd;
		projected[count].tex_s = clipped[i].tex_s;
		projected[count].tex_t = clipped[i].tex_t;
		projected[count].light_s = clipped[i].light_s;
		projected[count].light_t = clipped[i].light_t;
		count++;
	}

	if (count < 3)
		return QGE_ProjectSurfaceFail(fail_reason,
									  QGE_PROJECT_FAIL_PROJECT_EMPTY);

	clipped_projected_count = QGE_ClipProjectedPolygonViewport(projected,
															   count,
															   verts,
															   max_verts);
	if (clipped_projected_count < 3)
		return QGE_ProjectSurfaceFail(fail_reason,
									  QGE_PROJECT_FAIL_VIEWPORT_CLIP_EMPTY);
	count = clipped_projected_count;

	for (int i = 0; i < count; i++) {
		int j = (i + 1) % count;
		signed_area += verts[i].x * verts[j].y - verts[j].x * verts[i].y;
		if (verts[i].x < min_x) min_x = verts[i].x;
		if (verts[i].y < min_y) min_y = verts[i].y;
		if (verts[i].x > max_x) max_x = verts[i].x;
		if (verts[i].y > max_y) max_y = verts[i].y;
		depth_sum += verts[i].depth;
	}
	signed_area = fabsf(signed_area) * 0.5f;
	if (signed_area < QGE_PROJECTED_AREA_EPSILON)
		return QGE_ProjectSurfaceFail(fail_reason,
									  QGE_PROJECT_FAIL_MICRO_AREA);

	if (max_x <= min_x) max_x = min_x + 1.0f;
	if (max_y <= min_y) max_y = min_y + 1.0f;
	bounds->x1 = (int)min_x;
	bounds->y1 = (int)min_y;
	bounds->x2 = (int)max_x;
	bounds->y2 = (int)max_y;
	*num_verts = count;
	*depth = depth_sum / (float)count;
	*area = signed_area;
	return true;
}

static void QGE_SpatialClear(void)
{
	qboolean rgb_ready = qge_spatial_color_buffer[QGE_DWT_R] &&
						 qge_spatial_color_buffer[QGE_DWT_G] &&
						 qge_spatial_color_buffer[QGE_DWT_B];
	if (!qge_spatial_encode_buffer && !rgb_ready)
		return;
	if (qge_spatial_encode_buffer && !rgb_ready) {
		memset(qge_spatial_encode_buffer, 0,
			   qge_render_res * qge_render_res * sizeof(float));
	}
	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++) {
		if (qge_spatial_color_buffer[ch]) {
			memset(qge_spatial_color_buffer[ch], 0,
				   qge_render_res * qge_render_res * sizeof(float));
		}
	}
	if (qge_spatial_depth_buffer) {
		int pixels = qge_render_res * qge_render_res;
		for (int i = 0; i < pixels; i++)
			qge_spatial_depth_buffer[i] = QGE_SPATIAL_DEPTH_FAR;
	}
}

QGE_HOT_INLINE float QGE_ClampSpatialSignal(float value)
{
	if (value < 0.0f)
		return 0.0f;
	if (value > 1.5f)
		return 1.5f;
	return value;
}

static void QGE_SpatialAddPixelColorDepthIndex(int idx,
											   const qge_rgb_sample_t *color,
											   float depth);

static void QGE_SpatialAddPixelColorDepth(int x,
										  int y,
										  const qge_rgb_sample_t *color,
										  float depth)
{
	int idx;

	if (!color || x < 0 || y < 0 ||
		x >= qge_render_res || y >= qge_render_res)
		return;

	idx = y * qge_render_res + x;
	QGE_SpatialAddPixelColorDepthIndex(idx, color, depth);
}

static void QGE_SpatialAddPixelColorDepthIndex(int idx,
											   const qge_rgb_sample_t *color,
											   float depth)
{
	float current_depth;
	qge_rgb_sample_t sample;
	float value;
	float *encode = qge_spatial_encode_buffer;
	float *depth_buffer = qge_spatial_depth_buffer;
	float *rbuf = qge_spatial_color_buffer[QGE_DWT_R];
	float *gbuf = qge_spatial_color_buffer[QGE_DWT_G];
	float *bbuf = qge_spatial_color_buffer[QGE_DWT_B];

	if (!color)
		return;
	sample = *color;
	if (sample.r < 0.0f) sample.r = 0.0f;
	if (sample.g < 0.0f) sample.g = 0.0f;
	if (sample.b < 0.0f) sample.b = 0.0f;
	value = 0.299f * sample.r + 0.587f * sample.g + 0.114f * sample.b;

	if (value <= 0.0f)
		return;

	if (depth <= 0.0f || !isfinite(depth))
		depth = QGE_SPATIAL_DEPTH_FAR * 0.5f;

	if (depth_buffer && rbuf && gbuf && bbuf) {
		current_depth = depth_buffer[idx];
		if (depth > current_depth + QGE_SPATIAL_DEPTH_EPSILON)
			return;
		if (depth < current_depth - QGE_SPATIAL_DEPTH_EPSILON) {
			rbuf[idx] = sample.r;
			gbuf[idx] = sample.g;
			bbuf[idx] = sample.b;
			depth_buffer[idx] = depth;
		} else {
			rbuf[idx] += sample.r;
			gbuf[idx] += sample.g;
			bbuf[idx] += sample.b;
			if (depth < current_depth)
				depth_buffer[idx] = depth;
		}
		rbuf[idx] = QGE_ClampSpatialSignal(rbuf[idx]);
		gbuf[idx] = QGE_ClampSpatialSignal(gbuf[idx]);
		bbuf[idx] = QGE_ClampSpatialSignal(bbuf[idx]);
		return;
	}

	if (!encode)
		return;

	if (!depth_buffer) {
		encode[idx] += value;
		if (rbuf)
			rbuf[idx] += sample.r;
		if (gbuf)
			gbuf[idx] += sample.g;
		if (bbuf)
			bbuf[idx] += sample.b;
	} else {
		current_depth = depth_buffer[idx];
		if (depth > current_depth + QGE_SPATIAL_DEPTH_EPSILON)
			return;
		if (depth < current_depth - QGE_SPATIAL_DEPTH_EPSILON) {
			encode[idx] = value;
			if (rbuf)
				rbuf[idx] = sample.r;
			if (gbuf)
				gbuf[idx] = sample.g;
			if (bbuf)
				bbuf[idx] = sample.b;
			depth_buffer[idx] = depth;
		} else {
			encode[idx] += value;
			if (rbuf)
				rbuf[idx] += sample.r;
			if (gbuf)
				gbuf[idx] += sample.g;
			if (bbuf)
				bbuf[idx] += sample.b;
			if (depth < current_depth)
				depth_buffer[idx] = depth;
		}
	}
	encode[idx] = QGE_ClampSpatialSignal(encode[idx]);
	if (rbuf)
		rbuf[idx] = QGE_ClampSpatialSignal(rbuf[idx]);
	if (gbuf)
		gbuf[idx] = QGE_ClampSpatialSignal(gbuf[idx]);
	if (bbuf)
		bbuf[idx] = QGE_ClampSpatialSignal(bbuf[idx]);
}

static void QGE_SpatialAddPixelRGBDepthIndex(int idx,
											 float r,
											 float g,
											 float b,
											 float depth)
{
	float current_depth;
	float *depth_buffer = qge_spatial_depth_buffer;
	float *rbuf = qge_spatial_color_buffer[QGE_DWT_R];
	float *gbuf = qge_spatial_color_buffer[QGE_DWT_G];
	float *bbuf = qge_spatial_color_buffer[QGE_DWT_B];

	if (!(depth_buffer && rbuf && gbuf && bbuf)) {
		qge_rgb_sample_t color = {r, g, b};
		QGE_SpatialAddPixelColorDepthIndex(idx, &color, depth);
		return;
	}

	if (depth <= 0.0f || !isfinite(depth))
		depth = QGE_SPATIAL_DEPTH_FAR * 0.5f;

	current_depth = depth_buffer[idx];
	if (depth > current_depth + QGE_SPATIAL_DEPTH_EPSILON)
		return;

	if (r < 0.0f) r = 0.0f;
	if (g < 0.0f) g = 0.0f;
	if (b < 0.0f) b = 0.0f;
	if (r <= 0.0f && g <= 0.0f && b <= 0.0f)
		return;

	if (depth < current_depth - QGE_SPATIAL_DEPTH_EPSILON) {
		rbuf[idx] = r;
		gbuf[idx] = g;
		bbuf[idx] = b;
		depth_buffer[idx] = depth;
	} else {
		rbuf[idx] += r;
		gbuf[idx] += g;
		bbuf[idx] += b;
		if (depth < current_depth)
			depth_buffer[idx] = depth;
	}
	rbuf[idx] = QGE_ClampSpatialSignal(rbuf[idx]);
	gbuf[idx] = QGE_ClampSpatialSignal(gbuf[idx]);
	bbuf[idx] = QGE_ClampSpatialSignal(bbuf[idx]);
}

static inline void QGE_SpatialAddPixelRGBDepthPositivePrepared(int idx,
															  float r,
															  float g,
															  float b,
															  float depth,
															  float *depth_buffer,
															  float *rbuf,
															  float *gbuf,
															  float *bbuf)
{
	float current_depth = depth_buffer[idx];

	if (!(depth > 0.0f))
		depth = QGE_SPATIAL_DEPTH_FAR * 0.5f;
	if (depth > current_depth + QGE_SPATIAL_DEPTH_EPSILON)
		return;

	if (depth < current_depth - QGE_SPATIAL_DEPTH_EPSILON) {
		rbuf[idx] = r;
		gbuf[idx] = g;
		bbuf[idx] = b;
		depth_buffer[idx] = depth;
	} else {
		rbuf[idx] += r;
		gbuf[idx] += g;
		bbuf[idx] += b;
		if (depth < current_depth)
			depth_buffer[idx] = depth;
	}
	if (rbuf[idx] > 1.5f) rbuf[idx] = 1.5f;
	if (gbuf[idx] > 1.5f) gbuf[idx] = 1.5f;
	if (bbuf[idx] > 1.5f) bbuf[idx] = 1.5f;
}

static void QGE_SpatialAddPixelDepth(int x, int y, float value, float depth)
{
	qge_rgb_sample_t gray;

	gray.r = value;
	gray.g = value;
	gray.b = value;
	QGE_SpatialAddPixelColorDepth(x, y, &gray, depth);
}

static void QGE_SpatialFillRectDepth(const screen_rect_t *bounds,
									 float value,
									 float depth)
{
	int x1, y1, x2, y2;

	if (!bounds || value <= 0.0f)
		return;

	x1 = bounds->x1;
	y1 = bounds->y1;
	x2 = bounds->x2;
	y2 = bounds->y2;
	if (x1 < 0) x1 = 0;
	if (y1 < 0) y1 = 0;
	if (x2 >= qge_render_res) x2 = qge_render_res - 1;
	if (y2 >= qge_render_res) y2 = qge_render_res - 1;
	if (x2 < x1 || y2 < y1)
		return;

	for (int y = y1; y <= y2; y++) {
		for (int x = x1; x <= x2; x++)
			QGE_SpatialAddPixelDepth(x, y, value, depth);
	}
}

static void QGE_SpatialFillRectColorDepth(const screen_rect_t *bounds,
										  const qge_rgb_sample_t *color,
										  float depth)
{
	int x1, y1, x2, y2;

	if (!bounds || !color)
		return;

	x1 = bounds->x1;
	y1 = bounds->y1;
	x2 = bounds->x2;
	y2 = bounds->y2;
	if (x1 < 0) x1 = 0;
	if (y1 < 0) y1 = 0;
	if (x2 >= qge_render_res) x2 = qge_render_res - 1;
	if (y2 >= qge_render_res) y2 = qge_render_res - 1;
	if (x2 < x1 || y2 < y1)
		return;

	for (int y = y1; y <= y2; y++) {
		int idx = y * qge_render_res + x1;
		for (int x = x1; x <= x2; x++, idx++)
			QGE_SpatialAddPixelColorDepthIndex(idx, color, depth);
	}
}

static void QGE_SpatialLineDepth(float x1,
								 float y1,
								 float x2,
								 float y2,
								 float value,
								 float depth1,
								 float depth2)
{
	float dx = x2 - x1;
	float dy = y2 - y1;
	int samples = (int)fmaxf(fabsf(dx), fabsf(dy)) + 1;

	if (samples < 1)
		samples = 1;
	for (int i = 0; i <= samples; i++) {
		float t = (float)i / (float)samples;
		int x = (int)(x1 + dx * t + 0.5f);
		int y = (int)(y1 + dy * t + 0.5f);
		float depth = depth1 + (depth2 - depth1) * t;
		QGE_SpatialAddPixelDepth(x, y, value, depth);
	}
}

static void QGE_SpatialLineColorDepth(float x1,
									  float y1,
									  float x2,
									  float y2,
									  const qge_rgb_sample_t *color,
									  float depth1,
									  float depth2)
{
	float dx = x2 - x1;
	float dy = y2 - y1;
	int samples = (int)fmaxf(fabsf(dx), fabsf(dy)) + 1;
	float *depth_buffer = qge_spatial_depth_buffer;
	float *rbuf = qge_spatial_color_buffer[QGE_DWT_R];
	float *gbuf = qge_spatial_color_buffer[QGE_DWT_G];
	float *bbuf = qge_spatial_color_buffer[QGE_DWT_B];
	qboolean prepared_rgb_depth = depth_buffer && rbuf && gbuf && bbuf;
	float r, g, b;

	if (!color)
		return;
	if (samples < 1)
		samples = 1;
	if (prepared_rgb_depth) {
		r = color->r > 0.0f ? color->r : 0.0f;
		g = color->g > 0.0f ? color->g : 0.0f;
		b = color->b > 0.0f ? color->b : 0.0f;
		if (r <= 0.0f && g <= 0.0f && b <= 0.0f)
			return;
	}
	for (int i = 0; i <= samples; i++) {
		float t = (float)i / (float)samples;
		int x = (int)(x1 + dx * t + 0.5f);
		int y = (int)(y1 + dy * t + 0.5f);
		float depth = depth1 + (depth2 - depth1) * t;
		if (prepared_rgb_depth) {
			if (x < 0 || y < 0 || x >= qge_render_res || y >= qge_render_res)
				continue;
			QGE_SpatialAddPixelRGBDepthPositivePrepared(
				y * qge_render_res + x,
				r, g, b, depth,
				depth_buffer, rbuf, gbuf, bbuf);
		} else {
			QGE_SpatialAddPixelColorDepth(x, y, color, depth);
		}
	}
}

static void QGE_SpatialOutlineRectDepth(const screen_rect_t *bounds,
										float value,
										float depth)
{
	if (!bounds)
		return;
	QGE_SpatialLineDepth((float)bounds->x1, (float)bounds->y1,
						 (float)bounds->x2, (float)bounds->y1,
						 value, depth, depth);
	QGE_SpatialLineDepth((float)bounds->x2, (float)bounds->y1,
						 (float)bounds->x2, (float)bounds->y2,
						 value, depth, depth);
	QGE_SpatialLineDepth((float)bounds->x2, (float)bounds->y2,
						 (float)bounds->x1, (float)bounds->y2,
						 value, depth, depth);
	QGE_SpatialLineDepth((float)bounds->x1, (float)bounds->y2,
						 (float)bounds->x1, (float)bounds->y1,
						 value, depth, depth);
}

static void QGE_SpatialOutlineRectColorDepth(const screen_rect_t *bounds,
											 const qge_rgb_sample_t *color,
											 float depth)
{
	if (!bounds || !color)
		return;
	QGE_SpatialLineColorDepth((float)bounds->x1, (float)bounds->y1,
							  (float)bounds->x2, (float)bounds->y1,
							  color, depth, depth);
	QGE_SpatialLineColorDepth((float)bounds->x2, (float)bounds->y1,
							  (float)bounds->x2, (float)bounds->y2,
							  color, depth, depth);
	QGE_SpatialLineColorDepth((float)bounds->x2, (float)bounds->y2,
							  (float)bounds->x1, (float)bounds->y2,
							  color, depth, depth);
	QGE_SpatialLineColorDepth((float)bounds->x1, (float)bounds->y2,
							  (float)bounds->x1, (float)bounds->y1,
							  color, depth, depth);
}

static qge_projected_sample_t QGE_ProjectedPolygonAverageSample(const qge_projected_vertex_t *verts,
																int num_verts)
{
	qge_projected_sample_t sample;

	memset(&sample, 0, sizeof(sample));
	if (!verts || num_verts <= 0) {
		sample.depth = QGE_SPATIAL_DEPTH_FAR * 0.5f;
		return sample;
	}

	for (int i = 0; i < num_verts; i++) {
		sample.depth += verts[i].depth;
		sample.tex_s += verts[i].tex_s;
		sample.tex_t += verts[i].tex_t;
		sample.light_s += verts[i].light_s;
		sample.light_t += verts[i].light_t;
	}
	sample.depth /= (float)num_verts;
	sample.tex_s /= (float)num_verts;
	sample.tex_t /= (float)num_verts;
	sample.light_s /= (float)num_verts;
	sample.light_t /= (float)num_verts;
	return sample;
}

static qboolean QGE_PrepareProjectedTriangleSampler(
	const qge_projected_vertex_t *a,
	const qge_projected_vertex_t *b,
	const qge_projected_vertex_t *c,
	qge_projected_triangle_sampler_t *sampler)
{
	float denom;
	float w0_x;
	float w0_y;
	float w1_x;
	float w1_y;

	if (!a || !b || !c || !sampler)
		return false;

	denom = (b->y - c->y) * (a->x - c->x) +
			(c->x - b->x) * (a->y - c->y);
	if (fabsf(denom) < 0.0001f)
		return false;

	sampler->a = a;
	sampler->b = b;
	sampler->c = c;
	sampler->inv_denom = 1.0f / denom;
	sampler->ia = a->depth > 0.0001f ? 1.0f / a->depth : 1.0f;
	sampler->ib = b->depth > 0.0001f ? 1.0f / b->depth : 1.0f;
	sampler->ic = c->depth > 0.0001f ? 1.0f / c->depth : 1.0f;
	sampler->a_tex_s_ia = a->tex_s * sampler->ia;
	sampler->b_tex_s_ib = b->tex_s * sampler->ib;
	sampler->c_tex_s_ic = c->tex_s * sampler->ic;
	sampler->a_tex_t_ia = a->tex_t * sampler->ia;
	sampler->b_tex_t_ib = b->tex_t * sampler->ib;
	sampler->c_tex_t_ic = c->tex_t * sampler->ic;
	sampler->a_light_s_ia = a->light_s * sampler->ia;
	sampler->b_light_s_ib = b->light_s * sampler->ib;
	sampler->c_light_s_ic = c->light_s * sampler->ic;
	sampler->a_light_t_ia = a->light_t * sampler->ia;
	sampler->b_light_t_ib = b->light_t * sampler->ib;
	sampler->c_light_t_ic = c->light_t * sampler->ic;
	w0_x = (b->y - c->y) * sampler->inv_denom;
	w0_y = (c->x - b->x) * sampler->inv_denom;
	w1_x = (c->y - a->y) * sampler->inv_denom;
	w1_y = (a->x - c->x) * sampler->inv_denom;
	sampler->w0_dx = w0_x;
	sampler->w0_dy = w0_y;
	sampler->w1_dx = w1_x;
	sampler->w1_dy = w1_y;
	sampler->inv_depth_dx =
		w0_x * (sampler->ia - sampler->ic) +
		w1_x * (sampler->ib - sampler->ic);
	sampler->tex_s_num_dx =
		w0_x * (sampler->a_tex_s_ia - sampler->c_tex_s_ic) +
		w1_x * (sampler->b_tex_s_ib - sampler->c_tex_s_ic);
	sampler->tex_t_num_dx =
		w0_x * (sampler->a_tex_t_ia - sampler->c_tex_t_ic) +
		w1_x * (sampler->b_tex_t_ib - sampler->c_tex_t_ic);
	sampler->light_s_num_dx =
		w0_x * (sampler->a_light_s_ia - sampler->c_light_s_ic) +
		w1_x * (sampler->b_light_s_ib - sampler->c_light_s_ic);
	sampler->light_t_num_dx =
		w0_x * (sampler->a_light_t_ia - sampler->c_light_t_ic) +
		w1_x * (sampler->b_light_t_ib - sampler->c_light_t_ic);
	sampler->w0_origin = -(w0_x * c->x + w0_y * c->y);
	sampler->w1_origin = -(w1_x * c->x + w1_y * c->y);
	sampler->valid = true;
	return true;
}

static qboolean QGE_ProjectedTriangleSampleWeights(
	const qge_projected_triangle_sampler_t *sampler,
	float w0,
	float w1,
	qge_projected_sample_t *sample)
{
	const qge_projected_vertex_t *a;
	const qge_projected_vertex_t *b;
	const qge_projected_vertex_t *c;
	float w2;
	float inv_depth;
	float depth_scale;

	if (!sampler || !sampler->valid || !sample)
		return false;

	a = sampler->a;
	b = sampler->b;
	c = sampler->c;
	w2 = 1.0f - w0 - w1;

	if (w0 < -0.001f || w1 < -0.001f || w2 < -0.001f)
		return false;

	inv_depth = w0 * sampler->ia + w1 * sampler->ib + w2 * sampler->ic;
	if (!(inv_depth > 0.000001f)) {
		sample->depth = w0 * a->depth + w1 * b->depth + w2 * c->depth;
		sample->tex_s = w0 * a->tex_s + w1 * b->tex_s + w2 * c->tex_s;
		sample->tex_t = w0 * a->tex_t + w1 * b->tex_t + w2 * c->tex_t;
		sample->light_s = w0 * a->light_s + w1 * b->light_s + w2 * c->light_s;
		sample->light_t = w0 * a->light_t + w1 * b->light_t + w2 * c->light_t;
		return true;
	}

	depth_scale = 1.0f / inv_depth;
	sample->depth = depth_scale;
	sample->tex_s = (w0 * sampler->a_tex_s_ia +
					 w1 * sampler->b_tex_s_ib +
					 w2 * sampler->c_tex_s_ic) * depth_scale;
	sample->tex_t = (w0 * sampler->a_tex_t_ia +
					 w1 * sampler->b_tex_t_ib +
					 w2 * sampler->c_tex_t_ic) * depth_scale;
	sample->light_s = (w0 * sampler->a_light_s_ia +
					   w1 * sampler->b_light_s_ib +
					   w2 * sampler->c_light_s_ic) * depth_scale;
	sample->light_t = (w0 * sampler->a_light_t_ia +
					   w1 * sampler->b_light_t_ib +
					   w2 * sampler->c_light_t_ic) * depth_scale;
	return true;
}

static qboolean QGE_ProjectedTriangleSampleWeightsUnchecked(
	const qge_projected_triangle_sampler_t *sampler,
	float w0,
	float w1,
	qge_projected_sample_t *sample)
{
	float w2;
	float inv_depth;
	float depth_scale;

	if (!sampler || !sampler->valid || !sample)
		return false;

	w2 = 1.0f - w0 - w1;
	inv_depth = w0 * sampler->ia + w1 * sampler->ib + w2 * sampler->ic;
	if (!(inv_depth > 0.000001f))
		return QGE_ProjectedTriangleSampleWeights(sampler, w0, w1, sample);

	depth_scale = 1.0f / inv_depth;
	sample->depth = depth_scale;
	sample->tex_s = (w0 * sampler->a_tex_s_ia +
					 w1 * sampler->b_tex_s_ib +
					 w2 * sampler->c_tex_s_ic) * depth_scale;
	sample->tex_t = (w0 * sampler->a_tex_t_ia +
					 w1 * sampler->b_tex_t_ib +
					 w2 * sampler->c_tex_t_ic) * depth_scale;
	sample->light_s = (w0 * sampler->a_light_s_ia +
					   w1 * sampler->b_light_s_ib +
					   w2 * sampler->c_light_s_ic) * depth_scale;
	sample->light_t = (w0 * sampler->a_light_t_ia +
					   w1 * sampler->b_light_t_ib +
					   w2 * sampler->c_light_t_ic) * depth_scale;
	return true;
}

static qboolean QGE_ProjectedTriangleSamplePrepared(
	float x,
	float y,
	const qge_projected_triangle_sampler_t *sampler,
	qge_projected_sample_t *sample)
{
	float w0, w1;

	if (!sampler || !sampler->valid)
		return false;
	w0 = sampler->w0_origin + sampler->w0_dx * x + sampler->w0_dy * y;
	w1 = sampler->w1_origin + sampler->w1_dx * x + sampler->w1_dy * y;
	return QGE_ProjectedTriangleSampleWeights(sampler, w0, w1, sample);
}

static qboolean QGE_ProjectedTrianglePixelSamplePrepared(
	int x,
	int y,
	const qge_projected_triangle_sampler_t *sampler,
	qge_projected_sample_t *sample,
	float *coverage)
{
	static const float offsets[4][2] = {
		{0.25f, 0.25f},
		{0.75f, 0.25f},
		{0.25f, 0.75f},
		{0.75f, 0.75f}
	};
	qge_projected_sample_t sub;
	int hits = 0;

	if (!sample || !coverage)
		return false;
	if (QGE_ProjectedTriangleSamplePrepared((float)x + 0.5f,
											(float)y + 0.5f,
											sampler, sample)) {
		*coverage = 1.0f;
		return true;
	}

	memset(sample, 0, sizeof(*sample));
	for (int i = 0; i < 4; i++) {
		if (!QGE_ProjectedTriangleSamplePrepared((float)x + offsets[i][0],
												 (float)y + offsets[i][1],
												 sampler, &sub))
			continue;
		sample->depth += sub.depth;
		sample->tex_s += sub.tex_s;
		sample->tex_t += sub.tex_t;
		sample->light_s += sub.light_s;
		sample->light_t += sub.light_t;
		hits++;
	}
	if (!hits)
		return false;

	sample->depth /= (float)hits;
	sample->tex_s /= (float)hits;
	sample->tex_t /= (float)hits;
	sample->light_s /= (float)hits;
	sample->light_t /= (float)hits;
	*coverage = (float)hits * 0.25f;
	qge_scene_triangle_edge_fills++;
	return true;
}

static qboolean QGE_ProjectedTriangleRowSpan(
	const qge_projected_triangle_t *tri,
	float sample_y,
	int *span_x1,
	int *span_x2)
{
	float xs[3];
	int hits = 0;

	if (!tri || !span_x1 || !span_x2)
		return false;

	for (int i = 0; i < 3; i++) {
		const qge_projected_vertex_t *a = &tri->v[i];
		const qge_projected_vertex_t *b = &tri->v[(i + 1) % 3];
		float y_min = fminf(a->y, b->y);
		float y_max = fmaxf(a->y, b->y);
		float dy = b->y - a->y;
		float t;

		if (fabsf(dy) < 0.0001f)
			continue;
		if (sample_y < y_min || sample_y >= y_max)
			continue;
		t = (sample_y - a->y) / dy;
		if (hits < 3)
			xs[hits++] = a->x + (b->x - a->x) * t;
	}
	if (hits < 2)
		return false;

	{
		float min_x = xs[0];
		float max_x = xs[0];
		for (int i = 1; i < hits; i++) {
			if (xs[i] < min_x) min_x = xs[i];
			if (xs[i] > max_x) max_x = xs[i];
		}
		*span_x1 = (int)ceilf(min_x - 0.5f);
		*span_x2 = (int)floorf(max_x - 0.5f);
	}
	return *span_x2 >= *span_x1;
}

static float QGE_ProjectedTriangleArea2D(const qge_projected_vertex_t *a,
										 const qge_projected_vertex_t *b,
										 const qge_projected_vertex_t *c)
{
	if (!a || !b || !c)
		return 0.0f;
	return ((b->x - a->x) * (c->y - a->y) -
			(b->y - a->y) * (c->x - a->x)) * 0.5f;
}

static qboolean QGE_PointInProjectedTriangle2D(
	float x,
	float y,
	const qge_projected_vertex_t *a,
	const qge_projected_vertex_t *b,
	const qge_projected_vertex_t *c)
{
	float area;
	float w0, w1, w2;

	if (!a || !b || !c)
		return false;
	area = (b->y - c->y) * (a->x - c->x) +
		   (c->x - b->x) * (a->y - c->y);
	if (fabsf(area) < 0.0001f)
		return false;
	w0 = ((b->y - c->y) * (x - c->x) +
		  (c->x - b->x) * (y - c->y)) / area;
	w1 = ((c->y - a->y) * (x - c->x) +
		  (a->x - c->x) * (y - c->y)) / area;
	w2 = 1.0f - w0 - w1;
	return w0 >= -0.0005f && w1 >= -0.0005f && w2 >= -0.0005f;
}

static qboolean QGE_AddProjectedTriangle(qge_projected_triangle_t *tris,
										 int *num_tris,
										 int max_tris,
										 const qge_projected_vertex_t *a,
										 const qge_projected_vertex_t *b,
										 const qge_projected_vertex_t *c)
{
	float area;

	if (!tris || !num_tris || *num_tris >= max_tris)
		return false;
	area = fabsf(QGE_ProjectedTriangleArea2D(a, b, c));
	if (area < 0.25f)
		return false;
	tris[*num_tris].v[0] = *a;
	tris[*num_tris].v[1] = *b;
	tris[*num_tris].v[2] = *c;
	(*num_tris)++;
	return true;
}

static int QGE_TriangulateProjectedPolygon(const qge_projected_vertex_t *verts,
										   int num_verts,
										   qge_projected_triangle_t *tris,
										   int max_tris)
{
	int indices[QGE_MAX_PROJECTED_POLY_VERTS];
	float polygon_area = 0.0f;
	float winding;
	int remaining;
	int num_tris = 0;
	int guard;

	if (!verts || !tris || num_verts < 3 || max_tris <= 0)
		return 0;
	if (num_verts > QGE_MAX_PROJECTED_POLY_VERTS)
		num_verts = QGE_MAX_PROJECTED_POLY_VERTS;

	for (int i = 0; i < num_verts; i++) {
		int j = (i + 1) % num_verts;
		polygon_area += verts[i].x * verts[j].y - verts[j].x * verts[i].y;
		indices[i] = i;
	}
	if (fabsf(polygon_area) < 0.5f)
		return 0;
	winding = polygon_area >= 0.0f ? 1.0f : -1.0f;
	remaining = num_verts;
	guard = num_verts * num_verts;

	while (remaining > 3 && guard-- > 0) {
		qboolean clipped_ear = false;

		for (int i = 0; i < remaining && !clipped_ear; i++) {
			int prev_i = (i + remaining - 1) % remaining;
			int next_i = (i + 1) % remaining;
			const qge_projected_vertex_t *a = &verts[indices[prev_i]];
			const qge_projected_vertex_t *b = &verts[indices[i]];
			const qge_projected_vertex_t *c = &verts[indices[next_i]];
			float area = QGE_ProjectedTriangleArea2D(a, b, c) * winding;
			qboolean contains = false;

			if (area <= 0.25f)
				continue;

			for (int k = 0; k < remaining; k++) {
				if (k == prev_i || k == i || k == next_i)
					continue;
				if (QGE_PointInProjectedTriangle2D(verts[indices[k]].x,
												   verts[indices[k]].y,
												   a, b, c)) {
					contains = true;
					break;
				}
			}
			if (contains)
				continue;

			if (QGE_AddProjectedTriangle(tris, &num_tris, max_tris, a, b, c)) {
				for (int k = i; k + 1 < remaining; k++)
					indices[k] = indices[k + 1];
				remaining--;
				clipped_ear = true;
			}
		}

		if (!clipped_ear)
			break;
	}

	if (remaining == 3) {
		QGE_AddProjectedTriangle(tris, &num_tris, max_tris,
								 &verts[indices[0]], &verts[indices[1]],
								 &verts[indices[2]]);
	}

	if (num_tris <= 0) {
		for (int i = 1; i + 1 < num_verts; i++)
			QGE_AddProjectedTriangle(tris, &num_tris, max_tris,
									 &verts[0], &verts[i], &verts[i + 1]);
	}

	return num_tris;
}

QGE_HOT_INLINE float QGE_RGBLuma(const qge_rgb_sample_t *color)
{
	if (!color)
		return 0.0f;
	return 0.299f * color->r + 0.587f * color->g + 0.114f * color->b;
}

static void QGE_RGBClamp(qge_rgb_sample_t *color)
{
	if (!color)
		return;
	color->r = QGE_ClampSpatialSignal(color->r);
	color->g = QGE_ClampSpatialSignal(color->g);
	color->b = QGE_ClampSpatialSignal(color->b);
}

static void QGE_InitPaletteLut(void)
{
	const float inv_255 = 1.0f / 255.0f;

	if (qge_palette_lut_ready)
		return;
	for (int i = 0; i < 256; i++) {
		const byte *rgba = (const byte *)&d_8to24table[i];
		float fullbright_boost = i >= 224 ? 0.25f : 0.0f;
		qge_palette_lut[i].r = (float)rgba[0] * inv_255 + fullbright_boost;
		qge_palette_lut[i].g = (float)rgba[1] * inv_255 + fullbright_boost;
		qge_palette_lut[i].b = (float)rgba[2] * inv_255 + fullbright_boost;
		qge_palette_opaque[i] = rgba[3] != 0;
	}
	qge_palette_lut_ready = true;
}

static float QGE_TexturePaletteSample(const qge_scene_surface_t *surface,
									  const texture_t *tex,
									  int tx,
									  int ty,
									  qge_rgb_sample_t *color)
{
	const byte *pixels;
	int palette_index;

	if (!surface || !tex || !color || tex->width <= 0 || tex->height <= 0)
		return 0.0f;
	QGE_InitPaletteLut();

	tx %= (int)tex->width;
	ty %= (int)tex->height;
	if (tx < 0) tx += (int)tex->width;
	if (ty < 0) ty += (int)tex->height;

	pixels = (const byte *)(tex + 1);
	palette_index = pixels[ty * (int)tex->width + tx];
	if (!qge_palette_opaque[palette_index] ||
		((surface->flags & SURF_DRAWFENCE) && palette_index == 255)) {
		color->r = 0.0f;
		color->g = 0.0f;
		color->b = 0.0f;
		return 0.0f;
	}

	*color = qge_palette_lut[palette_index];
	QGE_RGBClamp(color);
	return 1.0f;
}

static float QGE_TexturePaletteSampleDirect(const qge_scene_surface_t *surface,
											const texture_t *tex,
											int tx,
											int ty,
											qge_rgb_sample_t *color)
{
	const byte *pixels;
	int palette_index;

	if (!surface || !tex || !color)
		return 0.0f;
	QGE_InitPaletteLut();

	pixels = (const byte *)(tex + 1);
	palette_index = pixels[ty * (int)tex->width + tx];
	if (!qge_palette_opaque[palette_index] ||
		((surface->flags & SURF_DRAWFENCE) && palette_index == 255)) {
		color->r = 0.0f;
		color->g = 0.0f;
		color->b = 0.0f;
		return 0.0f;
	}

	*color = qge_palette_lut[palette_index];
	return 1.0f;
}

static qboolean QGE_SurfaceTextureColorPrepared(const qge_scene_surface_t *surface,
												texture_t *tex,
												float tex_s,
												float tex_t,
												qge_rgb_sample_t *color,
												qboolean bilinear)
{
	unsigned int width, height;
	float fx, fy;
	int x0, y0, x1, y1;
	float tx_frac, ty_frac;
	qge_rgb_sample_t c00, c10, c01, c11;
	float a00, a10, a01, a11;
	float w00, w10, w01, w11;
	float alpha;

	if (!color)
		return false;
	color->r = 0.75f;
	color->g = 0.75f;
	color->b = 0.75f;

	if (!tex)
		return true;

	width = tex->width;
	height = tex->height;
	if (!width || !height)
		return true;

	if (tex_s < 0.0f || tex_s >= 1.0f) {
		tex_s = tex_s - floorf(tex_s);
		if (tex_s < 0.0f) tex_s += 1.0f;
	}
	if (tex_t < 0.0f || tex_t >= 1.0f) {
		tex_t = tex_t - floorf(tex_t);
		if (tex_t < 0.0f) tex_t += 1.0f;
	}

	if (!bilinear) {
		x0 = (int)(tex_s * (float)width);
		y0 = (int)(tex_t * (float)height);
		if (x0 >= (int)width) x0 = (int)width - 1;
		if (y0 >= (int)height) y0 = (int)height - 1;
		return QGE_TexturePaletteSampleDirect(surface, tex, x0, y0, color) > 0.0f;
	}

	fx = tex_s * (float)width - 0.5f;
	fy = tex_t * (float)height - 0.5f;
	x0 = (int)floorf(fx);
	y0 = (int)floorf(fy);
	x1 = x0 + 1;
	y1 = y0 + 1;
	tx_frac = fx - floorf(fx);
	ty_frac = fy - floorf(fy);

	a00 = QGE_TexturePaletteSample(surface, tex, x0, y0, &c00);
	a10 = QGE_TexturePaletteSample(surface, tex, x1, y0, &c10);
	a01 = QGE_TexturePaletteSample(surface, tex, x0, y1, &c01);
	a11 = QGE_TexturePaletteSample(surface, tex, x1, y1, &c11);
	w00 = (1.0f - tx_frac) * (1.0f - ty_frac) * a00;
	w10 = tx_frac * (1.0f - ty_frac) * a10;
	w01 = (1.0f - tx_frac) * ty_frac * a01;
	w11 = tx_frac * ty_frac * a11;
	alpha = w00 + w10 + w01 + w11;
	if (alpha <= 0.01f)
		return false;

	color->r = (c00.r * w00 + c10.r * w10 + c01.r * w01 + c11.r * w11) / alpha;
	color->g = (c00.g * w00 + c10.g * w10 + c01.g * w01 + c11.g * w11) / alpha;
	color->b = (c00.b * w00 + c10.b * w10 + c01.b * w01 + c11.b * w11) / alpha;
	QGE_RGBClamp(color);
	return true;
}

static qge_rgb_sample_t QGE_LightmapSampleTexel(const msurface_t *surf,
												int map,
												int s,
												int t,
												int smax,
												int tmax,
												int size)
{
	const byte *p;
	float scale;
	qge_rgb_sample_t color;

	color.r = 0.0f;
	color.g = 0.0f;
	color.b = 0.0f;
	if (!surf || !surf->samples || map < 0 || smax <= 0 || tmax <= 0 || size <= 0)
		return color;

	if (s < 0) s = 0;
	if (t < 0) t = 0;
	if (s >= smax) s = smax - 1;
	if (t >= tmax) t = tmax - 1;

	p = surf->samples + map * size * 3 + (t * smax + s) * 3;
	scale = (float)d_lightstylevalue[surf->styles[map]] / 256.0f;
	color.r = ((float)p[0] / 255.0f) * scale;
	color.g = ((float)p[1] / 255.0f) * scale;
	color.b = ((float)p[2] / 255.0f) * scale;
	return color;
}

static qboolean QGE_SurfaceLightGeometry(const msurface_t *surf,
										 int *smax,
										 int *tmax,
										 int *size)
{
	if (smax) *smax = 0;
	if (tmax) *tmax = 0;
	if (size) *size = 0;
	if (!surf || !surf->samples)
		return false;

	if (smax) *smax = (surf->extents[0] >> 4) + 1;
	if (tmax) *tmax = (surf->extents[1] >> 4) + 1;
	if (size && smax && tmax) *size = (*smax) * (*tmax);
	return smax && tmax && size && *smax > 0 && *tmax > 0 && *size > 0;
}

static qge_rgb_sample_t QGE_SurfaceLightColorPrepared(const msurface_t *surf,
													  const qge_projected_sample_t *sample,
													  int smax,
													  int tmax,
													  int size,
													  qboolean bilinear)
{
	int s0, t0, s1, t1;
	float local_s, local_t;
	float sf, tf;
	float s_frac, t_frac;
	int maps = 0;
	qge_rgb_sample_t color;

	color.r = 0.95f;
	color.g = 0.95f;
	color.b = 0.95f;

	if (!surf || !sample)
		return color;
	if (!surf->samples || smax <= 0 || tmax <= 0 || size <= 0)
		return color;

	color.r = 0.0f;
	color.g = 0.0f;
	color.b = 0.0f;

	local_s = sample->light_s * (float)(LMBLOCK_WIDTH * 16) -
			  (float)(surf->light_s * 16) - 8.0f;
	local_t = sample->light_t * (float)(LMBLOCK_HEIGHT * 16) -
			  (float)(surf->light_t * 16) - 8.0f;
	sf = local_s / 16.0f;
	tf = local_t / 16.0f;

	if (!bilinear) {
		s0 = (int)(sf + 0.5f);
		t0 = (int)(tf + 0.5f);
		if (s0 < 0) s0 = 0;
		if (t0 < 0) t0 = 0;
		if (s0 >= smax) s0 = smax - 1;
		if (t0 >= tmax) t0 = tmax - 1;
		for (int map = 0; map < MAXLIGHTMAPS && surf->styles[map] != 255; map++) {
			const byte *p = surf->samples + map * size * 3 +
							(t0 * smax + s0) * 3;
			float scale = (float)d_lightstylevalue[surf->styles[map]] / 256.0f;
			color.r += ((float)p[0] / 255.0f) * scale;
			color.g += ((float)p[1] / 255.0f) * scale;
			color.b += ((float)p[2] / 255.0f) * scale;
			maps++;
		}
		if (!maps) {
			color.r = 0.85f;
			color.g = 0.85f;
			color.b = 0.85f;
			return color;
		}
		if (color.r > 1.35f) color.r = 1.35f;
		if (color.g > 1.35f) color.g = 1.35f;
		if (color.b > 1.35f) color.b = 1.35f;
		return color;
	}

	s0 = (int)floorf(sf);
	t0 = (int)floorf(tf);
	s1 = s0 + 1;
	t1 = t0 + 1;
	s_frac = sf - floorf(sf);
	t_frac = tf - floorf(tf);

	for (int map = 0; map < MAXLIGHTMAPS && surf->styles[map] != 255; map++) {
		qge_rgb_sample_t c00 = QGE_LightmapSampleTexel(surf, map, s0, t0, smax, tmax, size);
		qge_rgb_sample_t c10 = QGE_LightmapSampleTexel(surf, map, s1, t0, smax, tmax, size);
		qge_rgb_sample_t c01 = QGE_LightmapSampleTexel(surf, map, s0, t1, smax, tmax, size);
		qge_rgb_sample_t c11 = QGE_LightmapSampleTexel(surf, map, s1, t1, smax, tmax, size);
		float w00 = (1.0f - s_frac) * (1.0f - t_frac);
		float w10 = s_frac * (1.0f - t_frac);
		float w01 = (1.0f - s_frac) * t_frac;
		float w11 = s_frac * t_frac;
		color.r += c00.r * w00 + c10.r * w10 + c01.r * w01 + c11.r * w11;
		color.g += c00.g * w00 + c10.g * w10 + c01.g * w01 + c11.g * w11;
		color.b += c00.b * w00 + c10.b * w10 + c01.b * w01 + c11.b * w11;
		maps++;
	}

	if (!maps) {
		color.r = 0.85f;
		color.g = 0.85f;
		color.b = 0.85f;
		return color;
	}
	if (color.r > 1.35f) color.r = 1.35f;
	if (color.g > 1.35f) color.g = 1.35f;
	if (color.b > 1.35f) color.b = 1.35f;
	return color;
}

static qge_rgb_sample_t QGE_SurfaceLightColor(const msurface_t *surf,
											  const qge_projected_sample_t *sample)
{
	int smax, tmax, size;

	if (!QGE_SurfaceLightGeometry(surf, &smax, &tmax, &size)) {
		qge_rgb_sample_t color;
		color.r = 0.95f;
		color.g = 0.95f;
		color.b = 0.95f;
		return color;
	}
	return QGE_SurfaceLightColorPrepared(surf, sample, smax, tmax, size,
										 quantum_render_bilinear_samples.value >= 0.5f);
}

static void QGE_PrepareSurfaceSampleContext(qge_surface_sample_context_t *ctx,
											const qge_scene_surface_t *surface,
											texture_t *tex,
											int light_smax,
											int light_tmax,
											int light_size)
{
	float gain = 1.0f;

	if (!ctx)
		return;

	ctx->surface = surface;
	ctx->surf = surface ? surface->surf : NULL;
	ctx->tex = tex;
	ctx->tex_pixels = tex ? (const byte *)(tex + 1) : NULL;
	ctx->tex_width = tex ? tex->width : 0;
	ctx->tex_height = tex ? tex->height : 0;
	ctx->tex_width_mask = ctx->tex_width ? ctx->tex_width - 1u : 0u;
	ctx->tex_height_mask = ctx->tex_height ? ctx->tex_height - 1u : 0u;
	ctx->tex_width_f = (float)ctx->tex_width;
	ctx->tex_height_f = (float)ctx->tex_height;
	ctx->light_smax = light_smax;
	ctx->light_tmax = light_tmax;
	ctx->light_size = light_size;
	ctx->has_light = light_smax > 0 && light_tmax > 0 && light_size > 0;
	ctx->light_map_count = 0;
	ctx->light_s_scale = (float)LMBLOCK_WIDTH;
	ctx->light_t_scale = (float)LMBLOCK_HEIGHT;
	ctx->light_s_offset = ctx->surf ? -(float)ctx->surf->light_s : 0.0f;
	ctx->light_t_offset = ctx->surf ? -(float)ctx->surf->light_t : 0.0f;
	ctx->bilinear = quantum_render_bilinear_samples.value >= 0.5f;
	ctx->sky = surface && (surface->flags & SURF_DRAWSKY);
	ctx->fence = surface && (surface->flags & SURF_DRAWFENCE);
	ctx->tex_power2 = ctx->tex_width && ctx->tex_height &&
					  ((ctx->tex_width & ctx->tex_width_mask) == 0u) &&
					  ((ctx->tex_height & ctx->tex_height_mask) == 0u);
	if (ctx->tex_pixels && ctx->tex_width && ctx->tex_height)
		QGE_InitPaletteLut();

	if (surface) {
		gain = 0.85f + surface->material_signal * 0.25f;
		if (surface->flags & (SURF_DRAWLAVA | SURF_DRAWTELE))
			gain *= 1.20f;
	}
	if (ctx->has_light && ctx->surf && ctx->surf->samples) {
		for (int map = 0;
			 map < MAXLIGHTMAPS && ctx->surf->styles[map] != 255;
			 map++) {
			ctx->light_scales[ctx->light_map_count++] =
				(float)d_lightstylevalue[ctx->surf->styles[map]] /
				(256.0f * 255.0f);
		}
	}
	ctx->color_gain_r = gain * qge_render_gate_color_gain[QGE_DWT_R];
	ctx->color_gain_g = gain * qge_render_gate_color_gain[QGE_DWT_G];
	ctx->color_gain_b = gain * qge_render_gate_color_gain[QGE_DWT_B];
}

QGE_HOT_INLINE qge_rgb_sample_t QGE_SurfaceLightColorContext(
	const qge_surface_sample_context_t *ctx,
	const qge_projected_sample_t *sample)
{
	const msurface_t *surf;
	const byte *sample_base;
	int s0, t0;
	qge_rgb_sample_t color;

	color.r = 0.95f;
	color.g = 0.95f;
	color.b = 0.95f;

	if (!ctx || !sample)
		return color;
	if (!ctx->has_light || !ctx->surf || !ctx->surf->samples)
		return QGE_SurfaceLightColor(ctx->surf, sample);
	if (ctx->bilinear)
		return QGE_SurfaceLightColorPrepared(ctx->surf, sample,
											 ctx->light_smax,
											 ctx->light_tmax,
											 ctx->light_size,
											 true);

	if (ctx->light_map_count <= 0) {
		color.r = 0.85f;
		color.g = 0.85f;
		color.b = 0.85f;
		return color;
	}

	surf = ctx->surf;
	s0 = (int)(sample->light_s * ctx->light_s_scale + ctx->light_s_offset);
	t0 = (int)(sample->light_t * ctx->light_t_scale + ctx->light_t_offset);
	if (s0 < 0) s0 = 0;
	if (t0 < 0) t0 = 0;
	if (s0 >= ctx->light_smax) s0 = ctx->light_smax - 1;
	if (t0 >= ctx->light_tmax) t0 = ctx->light_tmax - 1;

	sample_base = surf->samples + (t0 * ctx->light_smax + s0) * 3;
	if (ctx->light_map_count == 1) {
		float scale = ctx->light_scales[0];
		color.r = (float)sample_base[0] * scale;
		color.g = (float)sample_base[1] * scale;
		color.b = (float)sample_base[2] * scale;
		return color;
	}

	color.r = 0.0f;
	color.g = 0.0f;
	color.b = 0.0f;
	for (int map = 0; map < ctx->light_map_count; map++) {
		const byte *p = sample_base + map * ctx->light_size * 3;
		float scale = ctx->light_scales[map];
		color.r += (float)p[0] * scale;
		color.g += (float)p[1] * scale;
		color.b += (float)p[2] * scale;
	}
	if (color.r > 1.35f) color.r = 1.35f;
	if (color.g > 1.35f) color.g = 1.35f;
	if (color.b > 1.35f) color.b = 1.35f;
	return color;
}

QGE_HOT_INLINE qboolean QGE_SurfaceTextureColorContext(
	const qge_surface_sample_context_t *ctx,
	float tex_s,
	float tex_t,
	qge_rgb_sample_t *color)
{
	int x0, y0;
	int palette_index;

	if (!color)
		return false;
	color->r = 0.75f;
	color->g = 0.75f;
	color->b = 0.75f;

	if (!ctx || !ctx->tex)
		return true;
	if (ctx->bilinear)
		return QGE_SurfaceTextureColorPrepared(ctx->surface, ctx->tex,
											   tex_s, tex_t, color, true);
	if (!ctx->tex_pixels || !ctx->tex_width || !ctx->tex_height)
		return true;

	if (ctx->tex_power2 && tex_s >= 0.0f && tex_t >= 0.0f) {
		x0 = ((int)(tex_s * ctx->tex_width_f)) & (int)ctx->tex_width_mask;
		y0 = ((int)(tex_t * ctx->tex_height_f)) & (int)ctx->tex_height_mask;
	} else {
		if (tex_s < 0.0f || tex_s >= 1.0f) {
			tex_s = tex_s - floorf(tex_s);
			if (tex_s < 0.0f) tex_s += 1.0f;
		}
		if (tex_t < 0.0f || tex_t >= 1.0f) {
			tex_t = tex_t - floorf(tex_t);
			if (tex_t < 0.0f) tex_t += 1.0f;
		}

		x0 = (int)(tex_s * ctx->tex_width_f);
		y0 = (int)(tex_t * ctx->tex_height_f);
		if (x0 >= (int)ctx->tex_width) x0 = (int)ctx->tex_width - 1;
		if (y0 >= (int)ctx->tex_height) y0 = (int)ctx->tex_height - 1;
	}

	palette_index = ctx->tex_pixels[y0 * (int)ctx->tex_width + x0];
	if (!qge_palette_opaque[palette_index] ||
		(ctx->fence && palette_index == 255)) {
		color->r = 0.0f;
		color->g = 0.0f;
		color->b = 0.0f;
		return false;
	}

	*color = qge_palette_lut[palette_index];
	return true;
}

QGE_HOT_INLINE qge_rgb_sample_t QGE_SurfaceSampleColorContext(
	const qge_surface_sample_context_t *ctx,
	const qge_projected_sample_t *sample)
{
	qge_rgb_sample_t tex_color;
	qge_rgb_sample_t light_color;
	qge_rgb_sample_t out;
	float luma;

	out.r = 1.0f;
	out.g = 1.0f;
	out.b = 1.0f;
	if (!ctx || !sample)
		return out;
	if (!ctx->surface)
		return out;

	if (ctx->sky) {
		out.r = 0.020f;
		out.g = 0.035f;
		out.b = 0.090f;
		return out;
	}

	if (!QGE_SurfaceTextureColorContext(ctx, sample->tex_s, sample->tex_t,
										&tex_color)) {
		out.r = 0.0f;
		out.g = 0.0f;
		out.b = 0.0f;
		return out;
	}
	light_color = QGE_SurfaceLightColorContext(ctx, sample);

	out.r = (0.18f + tex_color.r * 0.82f) *
			(0.30f + light_color.r * 0.90f) * ctx->color_gain_r;
	out.g = (0.18f + tex_color.g * 0.82f) *
			(0.30f + light_color.g * 0.90f) * ctx->color_gain_g;
	out.b = (0.18f + tex_color.b * 0.82f) *
			(0.30f + light_color.b * 0.90f) * ctx->color_gain_b;
	out.r = QGE_ClampSpatialSignal(out.r);
	out.g = QGE_ClampSpatialSignal(out.g);
	out.b = QGE_ClampSpatialSignal(out.b);
	luma = QGE_RGBLuma(&out);
	if (luma < 0.05f) {
		out.r += 0.05f;
		out.g += 0.05f;
		out.b += 0.05f;
	}
	return out;
}

static void QGE_SpatialFillPolygonDepth(const qge_scene_surface_t *surface,
										const qge_projected_vertex_t *verts,
										int num_verts,
										const screen_rect_t *bounds,
										float value)
{
	int x1, y1, x2, y2;
	int filled = 0;
	float edge_gain;
	qge_projected_sample_t avg_sample;
	qge_projected_triangle_t tris[QGE_MAX_PROJECTED_TRIS];
	int num_tris;
	const msurface_t *surf = surface ? surface->surf : NULL;
	texture_t *tex = surf && surf->texinfo ? surf->texinfo->texture : NULL;
	int light_smax = 0;
	int light_tmax = 0;
	int light_size = 0;
	qge_surface_sample_context_t sample_ctx;
	qboolean edge_samples = quantum_render_edge_samples.value >= 0.5f;
	float *depth_buffer = qge_spatial_depth_buffer;
	float *rbuf = qge_spatial_color_buffer[QGE_DWT_R];
	float *gbuf = qge_spatial_color_buffer[QGE_DWT_G];
	float *bbuf = qge_spatial_color_buffer[QGE_DWT_B];
	qboolean prepared_rgb_depth = depth_buffer && rbuf && gbuf && bbuf;

	if (!verts || num_verts < 3 || !bounds || value <= 0.0f)
		return;

	if (tex)
		tex = R_TextureAnimation(tex, 0);
	QGE_SurfaceLightGeometry(surf, &light_smax, &light_tmax, &light_size);
	QGE_PrepareSurfaceSampleContext(&sample_ctx, surface, tex,
									light_smax, light_tmax, light_size);

	avg_sample = QGE_ProjectedPolygonAverageSample(verts, num_verts);
	num_tris = QGE_TriangulateProjectedPolygon(verts, num_verts,
											   tris, QGE_MAX_PROJECTED_TRIS);
	qge_scene_polygon_triangles += num_tris;

	x1 = bounds->x1;
	y1 = bounds->y1;
	x2 = bounds->x2;
	y2 = bounds->y2;
	if (x1 < 0) x1 = 0;
	if (y1 < 0) y1 = 0;
	if (x2 >= qge_render_res) x2 = qge_render_res - 1;
	if (y2 >= qge_render_res) y2 = qge_render_res - 1;

	for (int tri_i = 0; tri_i < num_tris; tri_i++) {
		const qge_projected_triangle_t *tri = &tris[tri_i];
		qge_projected_triangle_sampler_t sampler;
		int tx1 = (int)floorf(fminf(fminf(tri->v[0].x, tri->v[1].x), tri->v[2].x));
		int ty1 = (int)floorf(fminf(fminf(tri->v[0].y, tri->v[1].y), tri->v[2].y));
		int tx2 = (int)ceilf(fmaxf(fmaxf(tri->v[0].x, tri->v[1].x), tri->v[2].x));
		int ty2 = (int)ceilf(fmaxf(fmaxf(tri->v[0].y, tri->v[1].y), tri->v[2].y));

		if (!QGE_PrepareProjectedTriangleSampler(&tri->v[0],
												 &tri->v[1],
												 &tri->v[2],
												 &sampler))
			continue;
		if (tx1 < x1) tx1 = x1;
		if (ty1 < y1) ty1 = y1;
		if (tx2 > x2) tx2 = x2;
		if (ty2 > y2) ty2 = y2;
		if (tx2 < tx1 || ty2 < ty1)
			continue;

		for (int y = ty1; y <= ty2; y++) {
			float sample_y = (float)y + 0.5f;
			int sx1 = tx1;
			int sx2 = tx2;
			int row_index = y * qge_render_res;
			float w0, w1;

			if (!edge_samples) {
				if (!QGE_ProjectedTriangleRowSpan(tri, sample_y, &sx1, &sx2))
					continue;
				if (sx1 < tx1) sx1 = tx1;
				if (sx2 > tx2) sx2 = tx2;
				if (sx2 < sx1)
					continue;
			}

			w0 = sampler.w0_origin +
				 sampler.w0_dx * ((float)sx1 + 0.5f) +
				 sampler.w0_dy * sample_y;
			w1 = sampler.w1_origin +
				 sampler.w1_dx * ((float)sx1 + 0.5f) +
				 sampler.w1_dy * sample_y;

			if (!edge_samples) {
				float row_w0 = w0;
				float row_w1 = w1;
				float w2 = 1.0f - w0 - w1;
				float inv_depth = w0 * sampler.ia + w1 * sampler.ib +
								  w2 * sampler.ic;
				float tex_s_num = w0 * sampler.a_tex_s_ia +
								  w1 * sampler.b_tex_s_ib +
								  w2 * sampler.c_tex_s_ic;
				float tex_t_num = w0 * sampler.a_tex_t_ia +
								  w1 * sampler.b_tex_t_ib +
								  w2 * sampler.c_tex_t_ic;
				float light_s_num = w0 * sampler.a_light_s_ia +
									w1 * sampler.b_light_s_ib +
									w2 * sampler.c_light_s_ic;
				float light_t_num = w0 * sampler.a_light_t_ia +
									w1 * sampler.b_light_t_ib +
									w2 * sampler.c_light_t_ic;

				for (int x = sx1, x_offset = 0; x <= sx2;
					 x++, x_offset++,
					 inv_depth += sampler.inv_depth_dx,
					 tex_s_num += sampler.tex_s_num_dx,
					 tex_t_num += sampler.tex_t_num_dx,
					 light_s_num += sampler.light_s_num_dx,
					 light_t_num += sampler.light_t_num_dx) {
					qge_projected_sample_t sample;
					qge_rgb_sample_t pixel_color;

					if (!(inv_depth > 0.000001f)) {
						float fallback_w0 = row_w0 +
											sampler.w0_dx * (float)x_offset;
						float fallback_w1 = row_w1 +
											sampler.w1_dx * (float)x_offset;
						if (!QGE_ProjectedTriangleSampleWeightsUnchecked(&sampler,
																		 fallback_w0,
																		 fallback_w1,
																		 &sample))
							continue;
					} else {
						float depth_scale = 1.0f / inv_depth;
						sample.depth = depth_scale;
						sample.tex_s = tex_s_num * depth_scale;
						sample.tex_t = tex_t_num * depth_scale;
						sample.light_s = light_s_num * depth_scale;
						sample.light_t = light_t_num * depth_scale;
					}

					if (prepared_rgb_depth &&
						sample.depth > depth_buffer[row_index + x] +
									   QGE_SPATIAL_DEPTH_EPSILON)
						continue;
					pixel_color = QGE_SurfaceSampleColorContext(&sample_ctx, &sample);
					if (prepared_rgb_depth) {
						float r = pixel_color.r * value;
						float g = pixel_color.g * value;
						float b = pixel_color.b * value;
						if (r <= 0.0f && g <= 0.0f && b <= 0.0f)
							continue;
						QGE_SpatialAddPixelRGBDepthPositivePrepared(
							row_index + x,
							r, g, b,
							sample.depth,
							depth_buffer, rbuf, gbuf, bbuf);
					} else {
						QGE_SpatialAddPixelRGBDepthIndex(
							row_index + x,
							pixel_color.r * value,
							pixel_color.g * value,
							pixel_color.b * value,
							sample.depth);
					}
					filled++;
				}
			} else {
				for (int x = sx1; x <= sx2;
					 x++, w0 += sampler.w0_dx, w1 += sampler.w1_dx) {
					qge_projected_sample_t sample;
					qge_rgb_sample_t pixel_color;
					float coverage = 1.0f;

					if (!QGE_ProjectedTriangleSampleWeights(&sampler, w0, w1,
														   &sample)) {
						if (!QGE_ProjectedTrianglePixelSamplePrepared(x, y,
																	  &sampler,
																	  &sample,
																	  &coverage))
							continue;
					}
					if (prepared_rgb_depth &&
						sample.depth > depth_buffer[row_index + x] +
									   QGE_SPATIAL_DEPTH_EPSILON)
						continue;
					pixel_color = QGE_SurfaceSampleColorContext(&sample_ctx,
																&sample);
					QGE_SpatialAddPixelRGBDepthIndex(
						row_index + x,
						pixel_color.r * value * coverage,
						pixel_color.g * value * coverage,
						pixel_color.b * value * coverage,
						sample.depth);
					filled++;
				}
			}
		}
	}

	edge_gain = quantum_render_edge_gain.value;
	edge_gain *= qge_render_gate_edge_gain;
	if (edge_gain < 0.0f)
		edge_gain = 0.0f;
	if (edge_gain > 0.50f)
		edge_gain = 0.50f;
	if (surface && (surface->flags & SURF_DRAWSKY))
		edge_gain = 0.0f;
	for (int i = 0; i < num_verts && edge_gain > 0.0f; i++) {
		const qge_projected_vertex_t *a = &verts[i];
		const qge_projected_vertex_t *b = &verts[(i + 1) % num_verts];
		QGE_SpatialLineDepth(a->x, a->y, b->x, b->y,
							 value * edge_gain, a->depth, b->depth);
	}

	if (!filled) {
		qge_rgb_sample_t fill_color =
			QGE_SurfaceSampleColorContext(&sample_ctx, &avg_sample);
		fill_color.r *= value;
		fill_color.g *= value;
		fill_color.b *= value;
		QGE_SpatialFillRectColorDepth(bounds, &fill_color, avg_sample.depth);
		qge_scene_polygon_micro_fills++;
	}
}

static float QGE_WorldEncodeGain(void)
{
	float gain = 0.11f;

	if (qge_scene_surface_count > 192)
		gain *= sqrtf(192.0f / (float)qge_scene_surface_count);
	if (gain < 0.035f)
		gain = 0.035f;
	gain *= qge_render_gate_gain;
	return gain;
}

static void QGE_EncodeSurfaceMaterialDWT(dwt_framebuffer_t *fb,
										 const qge_scene_surface_t *surface,
										 const screen_rect_t *bounds,
										 float brightness,
										 float depth,
										 float depth_world)
{
	unsigned int hash;
	float material;
	float material_gain;
	float detail;
	int center_x, center_y;
	int width, height;

	(void)fb;

	if (!surface || !bounds)
		return;
	if (surface->flags & SURF_DRAWSKY)
		return;

	material_gain = quantum_render_material_gain.value;
	material_gain *= qge_render_gate_material_gain;
	if (material_gain <= 0.0f)
		return;
	if (material_gain > 1.0f)
		material_gain = 1.0f;

	hash = surface->texture_hash ^ (surface->light_hash << 1) ^
		   (unsigned int)(surface->surface_id * 2654435761u);
	material = surface->material_signal;
	if (material <= 0.0f)
		material = 0.25f;

	center_x = (bounds->x1 + bounds->x2) / 2;
	center_y = (bounds->y1 + bounds->y2) / 2;
	width = bounds->x2 - bounds->x1;
	height = bounds->y2 - bounds->y1;
	if (width < 1) width = 1;
	if (height < 1) height = 1;

	detail = brightness * (0.20f + material * 0.55f) *
			 (1.0f - depth * 0.25f) * material_gain;
	if (detail < 0.004f)
		detail = 0.004f;

	QGE_SpatialAddPixelDepth(center_x, center_y,
							 detail * (0.50f + surface->light_contrast),
							 depth_world);
	QGE_SpatialAddPixelDepth(center_x + (int)(hash & 7u) - 3,
							 center_y + (int)((hash >> 4) & 7u) - 3,
							 detail * (surface->light_energy + 0.15f),
							 depth_world);

	if (surface->flags & (SURF_DRAWWATER | SURF_DRAWTURB | SURF_DRAWLAVA | SURF_DRAWSLIME | SURF_DRAWTELE)) {
		int wave_x = bounds->x1 + (int)(hash % (unsigned int)width);
		int wave_y = bounds->y1 + (int)((hash >> 8) % (unsigned int)height);
		QGE_SpatialAddPixelDepth(wave_x, wave_y, detail * 0.75f,
								 depth_world);
	}

	if (surface->has_fullbright)
		QGE_SpatialAddPixelDepth(center_x, center_y, detail * 0.80f,
								 depth_world);

	qge_scene_material_encoded++;
}

static void QGE_EncodeProjectedPolygonDWT(dwt_framebuffer_t *fb,
										  const qge_scene_surface_t *surface,
										  const qge_projected_vertex_t *verts,
										  int num_verts,
										  const screen_rect_t *bounds,
										  float brightness,
										  float depth,
										  float depth_world,
										  float area)
{
	float fill;

	if (!surface || !verts || num_verts < 3 || !bounds)
		return;

	fill = brightness * (1.0f - depth * 0.1f) * 1.75f;
	fill *= 0.60f + fminf(area / 4096.0f, 1.0f) * 0.40f;
	if (fill < 0.004f)
		fill = 0.004f;
	QGE_SpatialFillPolygonDepth(surface, verts, num_verts, bounds, fill);

	QGE_EncodeSurfaceMaterialDWT(fb, surface, bounds, brightness,
								 depth, depth_world);
	qge_scene_polygon_encoded++;
}

static void QGE_RecordSurfaceSurrogate(qge_project_fail_reason_t reason)
{
	qge_scene_polygon_surrogate++;
	switch (reason) {
	case QGE_PROJECT_FAIL_MICRO_AREA:
		qge_scene_polygon_surrogate_micro++;
		break;
	case QGE_PROJECT_FAIL_NEAR_CLIP_EMPTY:
	case QGE_PROJECT_FAIL_PROJECT_EMPTY:
	case QGE_PROJECT_FAIL_VIEWPORT_CLIP_EMPTY:
		qge_scene_polygon_surrogate_clipped++;
		break;
	case QGE_PROJECT_FAIL_INVALID:
	case QGE_PROJECT_FAIL_NO_POLY:
	default:
		qge_scene_polygon_surrogate_invalid++;
		break;
	}
}

static qboolean QGE_ProjectFailIsCull(qge_project_fail_reason_t reason)
{
	return reason == QGE_PROJECT_FAIL_NEAR_CLIP_EMPTY ||
		   reason == QGE_PROJECT_FAIL_PROJECT_EMPTY ||
		   reason == QGE_PROJECT_FAIL_VIEWPORT_CLIP_EMPTY;
}

static void QGE_EncodeSurfaceSurrogateDWT(dwt_framebuffer_t *fb,
										  const qge_scene_surface_t *surface,
										  const screen_rect_t *bounds,
										  float brightness,
										  float depth,
										  float depth_world,
										  qge_project_fail_reason_t reason)
{
	if (!surface || !bounds)
		return;

	QGE_SpatialFillRectDepth(bounds,
							 brightness * (1.0f - depth * 0.1f),
							 depth_world);
	QGE_SpatialOutlineRectDepth(bounds, brightness * 0.65f,
								depth_world);
	QGE_EncodeSurfaceMaterialDWT(fb, surface, bounds, brightness,
								 depth, depth_world);
	QGE_RecordSurfaceSurrogate(reason);
}

static qge_scene_surface_t *QGE_FindSceneSurfaceByResourceId(qge_resource_id_t surface_id)
{
	if (qge_resource_id_kind(surface_id) != QGE_RESOURCE_SURFACE)
		return NULL;

	uint32_t index = qge_resource_id_index(surface_id);
	if (index == 0)
		return NULL;
	index--;

	for (int i = 0; i < qge_scene_surface_count; i++) {
		if (qge_scene_surfaces[i].surface_id >= 0 &&
			(uint32_t)qge_scene_surfaces[i].surface_id == index)
			return &qge_scene_surfaces[i];
	}
	return NULL;
}

static qboolean QGE_EncodeWorldSurfaceDWT(dwt_framebuffer_t *fb,
										  qge_scene_surface_t *surface,
										  int *encoded_world)
{
	screen_rect_t bounds;
	qge_projected_vertex_t verts[QGE_MAX_PROJECTED_POLY_VERTS];
	int num_verts = 0;
	float depth_world;
	float depth;
	float brightness;
	float area = 0.0f;
	qge_project_fail_reason_t project_fail = QGE_PROJECT_FAIL_NONE;

	if (!fb || !surface || !encoded_world)
		return false;

	if (QGE_ProjectSurfacePolygon(surface, surface->surf, verts,
								  QGE_MAX_PROJECTED_POLY_VERTS,
								  &num_verts, &bounds, &depth_world, &area,
								  &project_fail)) {
		depth = depth_world / 4096.0f;
		if (depth > 1.0f) depth = 1.0f;
		if (depth < 0.0f) depth = 0.0f;
		brightness = surface->brightness * (1.0f - depth * 0.45f) * QGE_WorldEncodeGain();
		if (brightness < 0.015f) brightness = 0.015f;
		QGE_EncodeProjectedPolygonDWT(fb, surface, verts, num_verts,
									  &bounds, brightness, depth,
									  depth_world, area);
	} else if (QGE_ProjectFailIsCull(project_fail)) {
		qge_scene_polygon_culled++;
	} else if (QGE_SurfaceScreenBounds(surface, surface->surf, &bounds,
									   &depth_world)) {
		depth = depth_world / 4096.0f;
		if (depth > 1.0f) depth = 1.0f;
		if (depth < 0.0f) depth = 0.0f;
		brightness = surface->brightness * (1.0f - depth * 0.45f) * QGE_WorldEncodeGain();
		if (brightness < 0.015f) brightness = 0.015f;
		QGE_EncodeSurfaceSurrogateDWT(fb, surface, &bounds, brightness,
									  depth, depth_world, project_fail);
	} else {
		QGE_RecordSurfaceSurrogate(project_fail);
	}
	(*encoded_world)++;
	return true;
}

static int QGE_EncodeSnapshotWorldSurfaces(dwt_framebuffer_t *fb,
										   const qge_frame_snapshot_t *snapshot,
										   int surface_budget)
{
	int encoded_world = 0;
	int surface_stride = 1;

	if (!fb || !snapshot || snapshot->visible_surface_count == 0)
		return 0;

	if ((int)snapshot->visible_surface_count > surface_budget)
		surface_stride = ((int)snapshot->visible_surface_count + surface_budget - 1) /
						 surface_budget;

	for (int i = 0;
		 i < (int)snapshot->visible_surface_count && encoded_world < surface_budget;
		 i += surface_stride) {
		const qge_snapshot_surface_t *visible = &snapshot->visible_surfaces[i];
		qge_scene_surface_t *surface = QGE_FindSceneSurfaceByResourceId(visible->surface_id);

		qge_scene_snapshot_surfaces++;
		if (!surface) {
			qge_scene_snapshot_misses++;
			continue;
		}
		QGE_EncodeWorldSurfaceDWT(fb, surface, &encoded_world);
	}
	return encoded_world;
}

static int QGE_EncodeTransientWorldSurfaces(dwt_framebuffer_t *fb,
											int surface_budget)
{
	int encoded_world = 0;
	int surface_stride = 1;

	if (!fb || qge_scene_surface_count == 0)
		return 0;

	if (qge_scene_surface_count > surface_budget)
		surface_stride = (qge_scene_surface_count + surface_budget - 1) / surface_budget;

	for (int i = 0; i < qge_scene_surface_count && encoded_world < surface_budget; i += surface_stride)
		QGE_EncodeWorldSurfaceDWT(fb, &qge_scene_surfaces[i], &encoded_world);
	return encoded_world;
}

static qboolean QGE_IsSnapshotViewmodel(const qge_snapshot_edict_t *edict)
{
	return edict &&
		qge_resource_id_kind(edict->entity_id) == QGE_RESOURCE_ENTITY &&
		qge_resource_id_index(edict->entity_id) == 0x30000u;
}

static qboolean QGE_ProjectSnapshotEdictBounds(const qge_snapshot_edict_t *edict,
											   screen_rect_t *bounds,
											   float *depth)
{
	float min_x = (float)qge_render_res;
	float min_y = (float)qge_render_res;
	float max_x = 0.0f;
	float max_y = 0.0f;
	float depth_sum = 0.0f;
	int projected = 0;

	if (!edict || !bounds || !depth)
		return false;

	if (QGE_IsSnapshotViewmodel(edict)) {
		bounds->x1 = (qge_render_res * 48) / 100;
		bounds->x2 = (qge_render_res * 53) / 100;
		bounds->y1 = (qge_render_res * 76) / 100;
		bounds->y2 = (qge_render_res * 92) / 100;
		*depth = 32.0f;
		return true;
	}

	for (int ix = 0; ix < 2; ix++) {
		for (int iy = 0; iy < 2; iy++) {
			for (int iz = 0; iz < 2; iz++) {
				vec3_t p;
				float sx, sy, sd;
				p[0] = ix ? edict->maxs.x : edict->mins.x;
				p[1] = iy ? edict->maxs.y : edict->mins.y;
				p[2] = iz ? edict->maxs.z : edict->mins.z;
				if (!QGE_ProjectPoint(p, &sx, &sy, &sd))
					continue;
				if (sx < min_x) min_x = sx;
				if (sy < min_y) min_y = sy;
				if (sx > max_x) max_x = sx;
				if (sy > max_y) max_y = sy;
				depth_sum += sd;
				projected++;
			}
		}
	}

	if (!projected) {
		vec3_t origin;
		float sx, sy, sd;
		origin[0] = edict->origin.x;
		origin[1] = edict->origin.y;
		origin[2] = edict->origin.z;
		if (!QGE_ProjectPoint(origin, &sx, &sy, &sd))
			return false;
		min_x = sx - 3.0f;
		max_x = sx + 3.0f;
		min_y = sy - 3.0f;
		max_y = sy + 3.0f;
		depth_sum = sd;
		projected = 1;
	}

	if (min_x < 0.0f) min_x = 0.0f;
	if (min_y < 0.0f) min_y = 0.0f;
	if (max_x > qge_render_res - 1) max_x = (float)(qge_render_res - 1);
	if (max_y > qge_render_res - 1) max_y = (float)(qge_render_res - 1);
	if (max_x <= min_x) max_x = min_x + 2.0f;
	if (max_y <= min_y) max_y = min_y + 2.0f;
	if (max_x > qge_render_res - 1) max_x = (float)(qge_render_res - 1);
	if (max_y > qge_render_res - 1) max_y = (float)(qge_render_res - 1);

	bounds->x1 = (int)min_x;
	bounds->y1 = (int)min_y;
	bounds->x2 = (int)max_x;
	bounds->y2 = (int)max_y;
	*depth = depth_sum / (float)projected;
	return true;
}

static float QGE_SnapshotEntityBrightness(const qge_snapshot_edict_t *edict,
										  qge_resource_kind_t model_kind,
										  float depth)
{
	float brightness = 0.18f;

	if (!edict)
		return brightness;
	if (model_kind == QGE_RESOURCE_SPRITE)
		brightness = 0.30f;
	else if (model_kind == QGE_RESOURCE_ALIAS_MODEL)
		brightness = 0.23f;
	else if (model_kind == QGE_RESOURCE_BSP_MODEL)
		brightness = 0.20f;
	if (QGE_IsSnapshotViewmodel(edict))
		brightness = 0.36f;
	if (edict->effects & (EF_BRIGHTFIELD | EF_MUZZLEFLASH | EF_BRIGHTLIGHT |
						  EF_DIMLIGHT | EF_QEX_QUADLIGHT | EF_QEX_PENTALIGHT |
						  EF_QEX_CANDLELIGHT))
		brightness *= 1.45f;
	if (edict->alpha > 0.0f && edict->alpha < 1.0f)
		brightness *= 0.35f + edict->alpha * 0.65f;
	brightness *= 1.0f - depth * 0.30f;
	if (brightness < 0.025f)
		brightness = 0.025f;
	if (brightness > 0.65f)
		brightness = 0.65f;
	return brightness;
}

static qge_rgb_sample_t QGE_RGBScaled(qge_rgb_sample_t color, float scale)
{
	color.r *= scale;
	color.g *= scale;
	color.b *= scale;
	QGE_RGBClamp(&color);
	return color;
}

static uint64_t QGE_SnapshotEntityAssetHash(const qge_snapshot_edict_t *edict,
											qge_resource_kind_t model_kind)
{
	qge_world_t *world;
	uint64_t hash;

	if (!edict)
		return 0;
	hash = (uint64_t)edict->model_id;
	world = qge_ctx ? qge_get_world(qge_ctx) : NULL;
	if (world && model_kind == QGE_RESOURCE_ALIAS_MODEL) {
		const qge_alias_model_ref_t *ref =
			qge_world_get_alias_model(world, edict->model_id);
		if (ref) {
			hash = QGE_RegistryHashStep(ref->source_hash, ref->vertex_count);
			hash = QGE_RegistryHashStep(hash, ref->triangle_count);
			hash = QGE_RegistryHashStep(hash, ref->skin_count);
			hash = QGE_RegistryHashStep(hash, ref->frame_count);
		}
	} else if (world && model_kind == QGE_RESOURCE_SPRITE) {
		const qge_sprite_ref_t *ref =
			qge_world_get_sprite(world, edict->model_id);
		if (ref) {
			hash = QGE_RegistryHashStep(ref->source_hash, ref->width);
			hash = QGE_RegistryHashStep(hash, ref->height);
			hash = QGE_RegistryHashStep(hash, ref->sprite_type);
			hash = QGE_RegistryHashStep(hash, ref->frame_count);
		}
	}
	hash = QGE_RegistryHashStep(hash, (uint64_t)edict->entity_id);
	hash = QGE_RegistryHashStep(hash, (uint64_t)(uint32_t)edict->frame);
	hash = QGE_RegistryHashStep(hash, edict->effects);
	return hash;
}

static qge_rgb_sample_t QGE_SnapshotEntityColor(const qge_snapshot_edict_t *edict,
												qge_resource_kind_t model_kind,
												float brightness)
{
	qge_rgb_sample_t color;
	uint64_t hash = QGE_SnapshotEntityAssetHash(edict, model_kind);
	float h0 = (float)(hash & 0xffu) / 255.0f;
	float h1 = (float)((hash >> 8) & 0xffu) / 255.0f;
	float h2 = (float)((hash >> 16) & 0xffu) / 255.0f;

	if (model_kind == QGE_RESOURCE_SPRITE) {
		color.r = brightness * (0.95f + h0 * 0.35f);
		color.g = brightness * (0.55f + h1 * 0.45f);
		color.b = brightness * (0.18f + h2 * 0.35f);
	} else if (model_kind == QGE_RESOURCE_ALIAS_MODEL) {
		color.r = brightness * (0.55f + h0 * 0.45f);
		color.g = brightness * (0.48f + h1 * 0.38f);
		color.b = brightness * (0.34f + h2 * 0.42f);
	} else {
		color.r = brightness * (0.42f + h0 * 0.35f);
		color.g = brightness * (0.48f + h1 * 0.35f);
		color.b = brightness * (0.42f + h2 * 0.35f);
	}

	if (QGE_IsSnapshotViewmodel(edict)) {
		color.r = brightness * 0.88f;
		color.g = brightness * 0.72f;
		color.b = brightness * 0.48f;
	}
	if (edict && (edict->effects & (EF_MUZZLEFLASH | EF_BRIGHTLIGHT |
									EF_QEX_QUADLIGHT | EF_QEX_PENTALIGHT))) {
		color.r *= 1.35f;
		color.g *= 1.22f;
		color.b *= 0.92f;
	}
	color.r *= qge_render_gate_color_gain[QGE_DWT_R];
	color.g *= qge_render_gate_color_gain[QGE_DWT_G];
	color.b *= qge_render_gate_color_gain[QGE_DWT_B];
	QGE_RGBClamp(&color);
	return color;
}

static void QGE_EntityCoeffPixel(int x,
								 int y,
								 const qge_rgb_sample_t *color,
								 float depth)
{
	QGE_SpatialAddPixelColorDepth(x, y, color, depth);
	qge_scene_entity_coefficients++;
}

static void QGE_EntityCoeffLine(float x1,
								float y1,
								float x2,
								float y2,
								const qge_rgb_sample_t *color,
								float depth)
{
	QGE_SpatialLineColorDepth(x1, y1, x2, y2, color, depth, depth);
	qge_scene_entity_coefficients++;
}

static int QGE_EntityBoundedTapCount(uint32_t primary,
									 uint32_t secondary)
{
	int taps = 4 + (int)(primary / 64u) + (int)(secondary / 128u);

	if (taps < 4)
		taps = 4;
	if (taps > 14)
		taps = 14;
	return taps;
}

static void QGE_AliasVertexToWorld(const qge_snapshot_edict_t *edict,
								   const aliashdr_t *hdr,
								   const trivertx_t *vertex,
								   vec3_t world)
{
	vec3_t p;
	float yaw, pitch, roll;
	float sy, cy, sp, cp, sr, cr;
	float x, y, z;
	float x2, y2, z2;

	if (!edict || !hdr || !vertex || !world)
		return;

	p[0] = hdr->scale_origin[0] + (float)vertex->v[0] * hdr->scale[0];
	p[1] = hdr->scale_origin[1] + (float)vertex->v[1] * hdr->scale[1];
	p[2] = hdr->scale_origin[2] + (float)vertex->v[2] * hdr->scale[2];

	yaw = DEG2RAD(edict->angles.y);
	pitch = DEG2RAD(-edict->angles.x);
	roll = DEG2RAD(edict->angles.z);
	sy = sinf(yaw); cy = cosf(yaw);
	sp = sinf(pitch); cp = cosf(pitch);
	sr = sinf(roll); cr = cosf(roll);

	x = p[0];
	y = p[1] * cr - p[2] * sr;
	z = p[1] * sr + p[2] * cr;

	x2 = x * cp + z * sp;
	y2 = y;
	z2 = -x * sp + z * cp;

	world[0] = edict->origin.x + x2 * cy - y2 * sy;
	world[1] = edict->origin.y + x2 * sy + y2 * cy;
	world[2] = edict->origin.z + z2;
}

static qboolean QGE_ProjectAliasVertex(const qge_snapshot_edict_t *edict,
									   const aliashdr_t *hdr,
									   const trivertx_t *vertex,
									   qge_projected_vertex_t *out)
{
	vec3_t world;
	float sx, sy, sd;

	if (!out)
		return false;
	QGE_AliasVertexToWorld(edict, hdr, vertex, world);
	if (!QGE_ProjectPoint(world, &sx, &sy, &sd))
		return false;
	out->x = sx;
	out->y = sy;
	out->depth = sd;
	out->tex_s = 0.0f;
	out->tex_t = 0.0f;
	out->light_s = 0.0f;
	out->light_t = 0.0f;
	return true;
}

static void QGE_FillEntityTriangleColor(const qge_projected_vertex_t *a,
										const qge_projected_vertex_t *b,
										const qge_projected_vertex_t *c,
										const qge_rgb_sample_t *color)
{
	int x1, y1, x2, y2;
	float *depth_buffer = qge_spatial_depth_buffer;
	float *rbuf = qge_spatial_color_buffer[QGE_DWT_R];
	float *gbuf = qge_spatial_color_buffer[QGE_DWT_G];
	float *bbuf = qge_spatial_color_buffer[QGE_DWT_B];
	qge_projected_triangle_sampler_t sampler;
	qge_projected_triangle_t tri;
	qboolean prepared_rgb_depth = depth_buffer && rbuf && gbuf && bbuf;

	if (!a || !b || !c || !color)
		return;
	if (fabsf(QGE_ProjectedTriangleArea2D(a, b, c)) < 0.35f)
		return;
	if (!QGE_PrepareProjectedTriangleSampler(a, b, c, &sampler))
		return;
	tri.v[0] = *a;
	tri.v[1] = *b;
	tri.v[2] = *c;

	x1 = (int)floorf(fminf(fminf(a->x, b->x), c->x));
	y1 = (int)floorf(fminf(fminf(a->y, b->y), c->y));
	x2 = (int)ceilf(fmaxf(fmaxf(a->x, b->x), c->x));
	y2 = (int)ceilf(fmaxf(fmaxf(a->y, b->y), c->y));
	if (x1 < 0) x1 = 0;
	if (y1 < 0) y1 = 0;
	if (x2 >= qge_render_res) x2 = qge_render_res - 1;
	if (y2 >= qge_render_res) y2 = qge_render_res - 1;
	if (x2 < x1 || y2 < y1)
		return;

	for (int y = y1; y <= y2; y++) {
		float sample_y = (float)y + 0.5f;
		int sx1 = x1;
		int sx2 = x2;
		float w0, w1;

		if (!QGE_ProjectedTriangleRowSpan(&tri, sample_y, &sx1, &sx2))
			continue;
		if (sx1 < x1) sx1 = x1;
		if (sx2 > x2) sx2 = x2;
		if (sx2 < sx1)
			continue;

		w0 = sampler.w0_origin +
			 sampler.w0_dx * ((float)sx1 + 0.5f) +
			 sampler.w0_dy * sample_y;
		w1 = sampler.w1_origin +
			 sampler.w1_dx * ((float)sx1 + 0.5f) +
			 sampler.w1_dy * sample_y;

		for (int x = sx1; x <= sx2;
			 x++, w0 += sampler.w0_dx, w1 += sampler.w1_dx) {
			qge_projected_sample_t sample;
			qge_rgb_sample_t pixel;

			if (!QGE_ProjectedTriangleSampleWeightsUnchecked(&sampler, w0, w1,
															 &sample))
				continue;
			if (prepared_rgb_depth) {
				QGE_SpatialAddPixelRGBDepthPositivePrepared(
					y * qge_render_res + x,
					color->r,
					color->g,
					color->b,
					sample.depth,
					depth_buffer, rbuf, gbuf, bbuf);
			} else {
				pixel = *color;
				QGE_SpatialAddPixelColorDepth(x, y, &pixel, sample.depth);
			}
		}
	}
	qge_scene_entity_mesh_triangles++;
}

static qboolean QGE_EncodeAliasModelMeshCoefficients(
	const qge_snapshot_edict_t *edict,
	const qge_alias_model_ref_t *ref,
	qge_rgb_sample_t color)
{
	qmodel_t *model;
	aliashdr_t *hdr;
	const aliasmesh_t *desc;
	const unsigned short *indexes;
	const trivertx_t *poseverts_data;
	int frame, pose, tri_count, stride;
	int encoded = 0;
	qge_rgb_sample_t fill = QGE_RGBScaled(color, 0.24f);
	qge_rgb_sample_t edge = QGE_RGBScaled(color, 0.85f);

	if (!edict || !ref || !ref->debug_cookie)
		return false;
	if (QGE_IsSnapshotViewmodel(edict))
		return false;

	model = (qmodel_t *)(uintptr_t)ref->debug_cookie;
	if (!model || model->type != mod_alias || !model->cache.data)
		return false;
	hdr = (aliashdr_t *)model->cache.data;
	if (hdr->numframes <= 0 || hdr->numindexes < 3 ||
		hdr->numverts_vbo <= 0 || !hdr->vertexes ||
		!hdr->indexes || !hdr->meshdesc)
		return false;

	frame = edict->frame;
	if (frame < 0 || frame >= hdr->numframes)
		frame = 0;
	pose = hdr->frames[frame].firstpose;
	if (pose < 0 || pose >= hdr->numposes)
		pose = 0;

	desc = (const aliasmesh_t *)((const byte *)hdr + hdr->meshdesc);
	indexes = (const unsigned short *)((const byte *)hdr + hdr->indexes);
	poseverts_data = (const trivertx_t *)((const byte *)hdr + hdr->vertexes) +
		pose * hdr->numverts;
	tri_count = hdr->numindexes / 3;
	stride = (tri_count + QGE_MAX_ALIAS_ENTITY_TRIS - 1) /
		QGE_MAX_ALIAS_ENTITY_TRIS;
	if (stride < 1)
		stride = 1;

	for (int tri = 0; tri < tri_count; tri += stride) {
		qge_projected_vertex_t pv[3];
		qboolean projected = true;

		for (int i = 0; i < 3; i++) {
			unsigned short mesh_index = indexes[tri * 3 + i];
			unsigned short vertex_index;
			if (mesh_index >= hdr->numverts_vbo) {
				projected = false;
				break;
			}
			vertex_index = desc[mesh_index].vertindex;
			if (vertex_index >= hdr->numverts) {
				projected = false;
				break;
			}
			if (!QGE_ProjectAliasVertex(edict, hdr,
										&poseverts_data[vertex_index],
										&pv[i])) {
				projected = false;
				break;
			}
		}
		if (!projected)
			continue;

		QGE_FillEntityTriangleColor(&pv[0], &pv[1], &pv[2], &fill);
		if ((encoded & 7) == 0) {
			QGE_EntityCoeffLine(pv[0].x, pv[0].y, pv[1].x, pv[1].y,
								&edge, fminf(fminf(pv[0].depth, pv[1].depth),
											 pv[2].depth));
			QGE_EntityCoeffLine(pv[1].x, pv[1].y, pv[2].x, pv[2].y,
								&edge, fminf(fminf(pv[0].depth, pv[1].depth),
											 pv[2].depth));
			QGE_EntityCoeffLine(pv[2].x, pv[2].y, pv[0].x, pv[0].y,
								&edge, fminf(fminf(pv[0].depth, pv[1].depth),
											 pv[2].depth));
		}
		encoded++;
	}

	return encoded > 0;
}

static void QGE_SnapshotOriginVec3(const qge_snapshot_edict_t *edict,
								   vec3_t out)
{
	if (!edict || !out)
		return;
	out[0] = edict->origin.x;
	out[1] = edict->origin.y;
	out[2] = edict->origin.z;
}

static void QGE_SnapshotAnglesVec3(const qge_snapshot_edict_t *edict,
								   vec3_t out)
{
	if (!edict || !out)
		return;
	out[0] = edict->angles.x;
	out[1] = edict->angles.y;
	out[2] = edict->angles.z;
}

static mspriteframe_t *QGE_SpriteFrameFromSnapshot(
	const qge_snapshot_edict_t *edict,
	const msprite_t *sprite)
{
	const mspriteframedesc_t *desc;
	mspritegroup_t *group;
	int frame;

	if (!edict || !sprite || sprite->numframes <= 0)
		return NULL;

	frame = edict->frame;
	if (frame < 0 || frame >= sprite->numframes)
		frame = 0;
	desc = &sprite->frames[frame];
	if (desc->type == SPR_SINGLE)
		return desc->frameptr;

	group = (mspritegroup_t *)desc->frameptr;
	if (!group || group->numframes <= 0)
		return NULL;

	if (desc->type == SPR_ANGLED) {
		vec3_t angles, axis[3];
		float f, r;
		int dir;

		QGE_SnapshotAnglesVec3(edict, angles);
		AngleVectors(angles, axis[0], axis[1], axis[2]);
		f = DotProduct(vpn, axis[0]);
		r = DotProduct(vright, axis[0]);
		dir = (int)((atan2f(r, f) + 1.125f * (float)M_PI) *
					(4.0f / (float)M_PI));
		return group->frames[(dir & 7) % group->numframes];
	}

	if (group->intervals) {
		float fullinterval = group->intervals[group->numframes - 1];
		float time = cl.time;
		float targettime;

		if (fullinterval > 0.0f) {
			targettime = time - ((int)(time / fullinterval)) * fullinterval;
			for (int i = 0; i < group->numframes - 1; i++) {
				if (group->intervals[i] > targettime)
					return group->frames[i];
			}
		}
	}
	return group->frames[group->numframes - 1];
}

static qboolean QGE_SpriteAxesFromSnapshot(const qge_snapshot_edict_t *edict,
										   const msprite_t *sprite,
										   vec3_t right,
										   vec3_t up)
{
	vec3_t origin, forward, angles;
	float angle, sr, cr;

	if (!edict || !sprite || !right || !up)
		return false;

	switch (sprite->type) {
	case SPR_VP_PARALLEL_UPRIGHT:
		up[0] = 0.0f; up[1] = 0.0f; up[2] = 1.0f;
		CrossProduct(vpn, up, right);
		VectorNormalizeFast(right);
		return true;
	case SPR_FACING_UPRIGHT:
		QGE_SnapshotOriginVec3(edict, origin);
		VectorSubtract(origin, r_origin, forward);
		forward[2] = 0.0f;
		if (VectorLength(forward) < 0.001f)
			VectorCopy(vpn, forward);
		VectorNormalizeFast(forward);
		right[0] = forward[1];
		right[1] = -forward[0];
		right[2] = 0.0f;
		up[0] = 0.0f; up[1] = 0.0f; up[2] = 1.0f;
		return true;
	case SPR_VP_PARALLEL:
		VectorCopy(vright, right);
		VectorCopy(vup, up);
		return true;
	case SPR_ORIENTED:
		QGE_SnapshotAnglesVec3(edict, angles);
		AngleVectors(angles, forward, right, up);
		return true;
	case SPR_VP_PARALLEL_ORIENTED:
		angle = edict->angles.z * (float)M_PI_DIV_180;
		sr = sinf(angle);
		cr = cosf(angle);
		right[0] = vright[0] * cr + vup[0] * sr;
		right[1] = vright[1] * cr + vup[1] * sr;
		right[2] = vright[2] * cr + vup[2] * sr;
		up[0] = vright[0] * -sr + vup[0] * cr;
		up[1] = vright[1] * -sr + vup[1] * cr;
		up[2] = vright[2] * -sr + vup[2] * cr;
		return true;
	default:
		return false;
	}
}

static void QGE_SpriteCorner(const vec3_t origin,
							 const vec3_t up,
							 const vec3_t right,
							 float up_offset,
							 float right_offset,
							 float scale,
							 vec3_t out)
{
	out[0] = origin[0] + up[0] * up_offset * scale +
			 right[0] * right_offset * scale;
	out[1] = origin[1] + up[1] * up_offset * scale +
			 right[1] * right_offset * scale;
	out[2] = origin[2] + up[2] * up_offset * scale +
			 right[2] * right_offset * scale;
}

static qboolean QGE_ProjectSpriteFrameQuad(const qge_snapshot_edict_t *edict,
										   const msprite_t *sprite,
										   const mspriteframe_t *frame,
										   qge_projected_vertex_t pv[4])
{
	vec3_t origin, up, right, point;
	float scale;

	if (!edict || !sprite || !frame || !pv)
		return false;
	if (!QGE_SpriteAxesFromSnapshot(edict, sprite, right, up))
		return false;

	QGE_SnapshotOriginVec3(edict, origin);
	scale = edict->scale > 0.0f ? edict->scale : 1.0f;

	QGE_SpriteCorner(origin, up, right, frame->down, frame->left,
					 scale, point);
	if (!QGE_ProjectPoint(point, &pv[0].x, &pv[0].y, &pv[0].depth))
		return false;
	pv[0].tex_s = 0.0f; pv[0].tex_t = 1.0f;

	QGE_SpriteCorner(origin, up, right, frame->up, frame->left,
					 scale, point);
	if (!QGE_ProjectPoint(point, &pv[1].x, &pv[1].y, &pv[1].depth))
		return false;
	pv[1].tex_s = 0.0f; pv[1].tex_t = 0.0f;

	QGE_SpriteCorner(origin, up, right, frame->up, frame->right,
					 scale, point);
	if (!QGE_ProjectPoint(point, &pv[2].x, &pv[2].y, &pv[2].depth))
		return false;
	pv[2].tex_s = frame->smax; pv[2].tex_t = 0.0f;

	QGE_SpriteCorner(origin, up, right, frame->down, frame->right,
					 scale, point);
	if (!QGE_ProjectPoint(point, &pv[3].x, &pv[3].y, &pv[3].depth))
		return false;
	pv[3].tex_s = frame->smax; pv[3].tex_t = frame->tmax;
	return true;
}

static qboolean QGE_EncodeSpriteBillboardCoefficients(
	const qge_snapshot_edict_t *edict,
	const qge_sprite_ref_t *ref,
	qge_rgb_sample_t color)
{
	qmodel_t *model;
	msprite_t *sprite;
	mspriteframe_t *frame;
	qge_projected_vertex_t pv[4];
	qge_rgb_sample_t fill = QGE_RGBScaled(color, 0.42f);
	qge_rgb_sample_t edge = QGE_RGBScaled(color, 1.10f);
	qge_rgb_sample_t detail = QGE_RGBScaled(color, 1.35f);
	uint64_t hash;
	int bands;

	if (!edict || !ref || !ref->debug_cookie)
		return false;
	model = (qmodel_t *)(uintptr_t)ref->debug_cookie;
	if (!model || model->type != mod_sprite || !model->cache.data)
		return false;
	sprite = (msprite_t *)model->cache.data;
	frame = QGE_SpriteFrameFromSnapshot(edict, sprite);
	if (!frame || !QGE_ProjectSpriteFrameQuad(edict, sprite, frame, pv))
		return false;

	QGE_FillEntityTriangleColor(&pv[0], &pv[1], &pv[2], &fill);
	QGE_FillEntityTriangleColor(&pv[0], &pv[2], &pv[3], &fill);
	QGE_EntityCoeffLine(pv[0].x, pv[0].y, pv[1].x, pv[1].y,
						&edge, fminf(pv[0].depth, pv[1].depth));
	QGE_EntityCoeffLine(pv[1].x, pv[1].y, pv[2].x, pv[2].y,
						&edge, fminf(pv[1].depth, pv[2].depth));
	QGE_EntityCoeffLine(pv[2].x, pv[2].y, pv[3].x, pv[3].y,
						&edge, fminf(pv[2].depth, pv[3].depth));
	QGE_EntityCoeffLine(pv[3].x, pv[3].y, pv[0].x, pv[0].y,
						&edge, fminf(pv[3].depth, pv[0].depth));

	hash = QGE_SnapshotEntityAssetHash(edict, QGE_RESOURCE_SPRITE);
	if (frame->gltexture)
		hash = QGE_RegistryHashStep(hash, frame->gltexture->source_crc);
	bands = 2 + (int)(hash & 3u);
	for (int i = 1; i <= bands; i++) {
		float t = (float)i / (float)(bands + 1);
		float ax = pv[0].x + (pv[1].x - pv[0].x) * t;
		float ay = pv[0].y + (pv[1].y - pv[0].y) * t;
		float bx = pv[3].x + (pv[2].x - pv[3].x) * t;
		float by = pv[3].y + (pv[2].y - pv[3].y) * t;
		float depth = (pv[0].depth + pv[1].depth +
					   pv[2].depth + pv[3].depth) * 0.25f;
		QGE_EntityCoeffLine(ax, ay, bx, by, &detail, depth);
	}

	qge_scene_sprite_billboards++;
	return true;
}

static void QGE_EncodeAliasModelCoefficients(
	const qge_snapshot_edict_t *edict,
	const screen_rect_t *bounds,
	qge_rgb_sample_t color,
	float depth_world)
{
	qge_world_t *world = qge_ctx ? qge_get_world(qge_ctx) : NULL;
	const qge_alias_model_ref_t *ref = world ?
		qge_world_get_alias_model(world, edict->model_id) : NULL;
	uint64_t hash = QGE_SnapshotEntityAssetHash(edict,
												QGE_RESOURCE_ALIAS_MODEL);
	int x1, y1, x2, y2, cx, w, h;
	int taps;
	qge_rgb_sample_t fill = QGE_RGBScaled(color,
										  QGE_IsSnapshotViewmodel(edict) ?
										  0.42f : 0.34f);
	qge_rgb_sample_t edge = QGE_RGBScaled(color, 1.20f);
	qge_rgb_sample_t detail = QGE_RGBScaled(color, 1.45f);

	if (!edict || !bounds)
		return;
	x1 = bounds->x1; y1 = bounds->y1; x2 = bounds->x2; y2 = bounds->y2;
	cx = (x1 + x2) / 2;
	w = x2 - x1;
	h = y2 - y1;
	if (w < 1) w = 1;
	if (h < 1) h = 1;

	if (QGE_IsSnapshotViewmodel(edict)) {
		QGE_EntityCoeffLine((float)x1, (float)y2,
							(float)cx, (float)y1,
							&detail, depth_world);
		QGE_EntityCoeffLine((float)x2, (float)y2,
							(float)cx, (float)y1,
							&detail, depth_world);
		QGE_EntityCoeffLine((float)(x1 + w / 4), (float)(y2 - h / 5),
							(float)(x2 - w / 5), (float)(y1 + h / 3),
							&edge, depth_world);
		QGE_EntityCoeffPixel(cx, y1 + h / 5, &detail, depth_world);
		return;
	}

	if (QGE_EncodeAliasModelMeshCoefficients(edict, ref, color))
		return;

	QGE_SpatialFillRectColorDepth(bounds, &fill, depth_world);
	QGE_SpatialOutlineRectColorDepth(bounds, &edge, depth_world);

	QGE_EntityCoeffLine((float)cx, (float)y1,
						(float)cx, (float)y2,
						&detail, depth_world);
	QGE_EntityCoeffLine((float)(x1 + w / 5), (float)(y1 + h / 3),
						(float)(x2 - w / 5), (float)(y1 + h / 3),
						&edge, depth_world);
	QGE_EntityCoeffLine((float)cx, (float)(y1 + h / 2),
						(float)(x1 + w / 4), (float)y2,
						&edge, depth_world);
	QGE_EntityCoeffLine((float)cx, (float)(y1 + h / 2),
						(float)(x2 - w / 4), (float)y2,
						&edge, depth_world);

	taps = ref ? QGE_EntityBoundedTapCount(ref->vertex_count,
										   ref->triangle_count) : 6;
	for (int i = 0; i < taps; i++) {
		uint64_t tap = QGE_RegistryHashStep(hash, (uint64_t)i + 1u);
		int x = x1 + (int)(tap % (uint64_t)(w + 1));
		int y = y1 + (int)((tap >> 11) % (uint64_t)(h + 1));
		QGE_EntityCoeffPixel(x, y, &detail, depth_world);
	}
}

static void QGE_EncodeSpriteCoefficients(const qge_snapshot_edict_t *edict,
										 const screen_rect_t *bounds,
										 qge_rgb_sample_t color,
										 float depth_world)
{
	qge_world_t *world = qge_ctx ? qge_get_world(qge_ctx) : NULL;
	const qge_sprite_ref_t *ref = world ?
		qge_world_get_sprite(world, edict->model_id) : NULL;
	uint64_t hash = QGE_SnapshotEntityAssetHash(edict, QGE_RESOURCE_SPRITE);
	int x1, y1, x2, y2, cx, cy, w, h;
	int bands, taps;
	qge_rgb_sample_t fill = QGE_RGBScaled(color, 0.58f);
	qge_rgb_sample_t edge = QGE_RGBScaled(color, 1.18f);
	qge_rgb_sample_t detail = QGE_RGBScaled(color, 1.50f);

	if (!edict || !bounds)
		return;
	x1 = bounds->x1; y1 = bounds->y1; x2 = bounds->x2; y2 = bounds->y2;
	cx = (x1 + x2) / 2;
	cy = (y1 + y2) / 2;
	w = x2 - x1;
	h = y2 - y1;
	if (w < 1) w = 1;
	if (h < 1) h = 1;

	if (ref && QGE_EncodeSpriteBillboardCoefficients(edict, ref, color))
		return;

	QGE_SpatialFillRectColorDepth(bounds, &fill, depth_world);
	QGE_SpatialOutlineRectColorDepth(bounds, &edge, depth_world);
	QGE_EntityCoeffLine((float)cx, (float)y1,
						(float)cx, (float)y2,
						&detail, depth_world);
	QGE_EntityCoeffLine((float)x1, (float)cy,
						(float)x2, (float)cy,
						&edge, depth_world);

	bands = ref && ref->width > ref->height ? 4 : 3;
	for (int i = 1; i < bands; i++) {
		int x = x1 + (w * i) / bands;
		QGE_EntityCoeffLine((float)x, (float)(y1 + 1),
							(float)x, (float)(y2 - 1),
							&edge, depth_world);
	}

	taps = ref ? QGE_EntityBoundedTapCount(ref->width, ref->height) : 5;
	for (int i = 0; i < taps; i++) {
		uint64_t tap = QGE_RegistryHashStep(hash, (uint64_t)i + 17u);
		int x = x1 + (int)(tap % (uint64_t)(w + 1));
		int y = y1 + (int)((tap >> 9) % (uint64_t)(h + 1));
		QGE_EntityCoeffPixel(x, y, &detail, depth_world);
	}
}

static void QGE_EncodeBrushEntityCoefficients(
	const qge_snapshot_edict_t *edict,
	const screen_rect_t *bounds,
	qge_rgb_sample_t color,
	float depth_world)
{
	uint64_t hash = QGE_SnapshotEntityAssetHash(edict, QGE_RESOURCE_BSP_MODEL);
	int cx, cy, w, h;
	qge_rgb_sample_t fill = QGE_RGBScaled(color, 0.38f);
	qge_rgb_sample_t edge = QGE_RGBScaled(color, 1.15f);
	qge_rgb_sample_t detail = QGE_RGBScaled(color, 1.35f);

	if (!bounds)
		return;
	cx = (bounds->x1 + bounds->x2) / 2;
	cy = (bounds->y1 + bounds->y2) / 2;
	w = bounds->x2 - bounds->x1;
	h = bounds->y2 - bounds->y1;
	if (w < 1) w = 1;
	if (h < 1) h = 1;

	QGE_SpatialFillRectColorDepth(bounds, &fill, depth_world);
	QGE_SpatialOutlineRectColorDepth(bounds, &edge, depth_world);
	QGE_EntityCoeffLine((float)bounds->x1, (float)bounds->y1,
						(float)bounds->x2, (float)bounds->y2,
						&detail, depth_world);
	QGE_EntityCoeffLine((float)bounds->x2, (float)bounds->y1,
						(float)bounds->x1, (float)bounds->y2,
						&detail, depth_world);
	QGE_EntityCoeffPixel(bounds->x1 + (int)(hash % (uint64_t)(w + 1)),
						 cy, &detail, depth_world);
	QGE_EntityCoeffPixel(cx,
						 bounds->y1 + (int)((hash >> 8) % (uint64_t)(h + 1)),
						 &detail, depth_world);
}

static void QGE_EncodeSnapshotEntityDetailDWT(dwt_framebuffer_t *fb,
											  const qge_snapshot_edict_t *edict,
											  const screen_rect_t *bounds,
											  float brightness,
											  float depth_world)
{
	qge_resource_kind_t model_kind;
	qge_rgb_sample_t color;

	(void)fb;

	if (!edict || !bounds)
		return;

	model_kind = qge_resource_id_kind(edict->model_id);
	color = QGE_SnapshotEntityColor(edict, model_kind, brightness);
	if (model_kind == QGE_RESOURCE_ALIAS_MODEL)
		QGE_EncodeAliasModelCoefficients(edict, bounds, color, depth_world);
	else if (model_kind == QGE_RESOURCE_SPRITE)
		QGE_EncodeSpriteCoefficients(edict, bounds, color, depth_world);
	else
		QGE_EncodeBrushEntityCoefficients(edict, bounds, color, depth_world);
}

static qboolean QGE_EncodeSnapshotEdictDWT(dwt_framebuffer_t *fb,
										   const qge_snapshot_edict_t *edict)
{
	qge_resource_kind_t model_kind;
	screen_rect_t bounds;
	float depth_world;
	float depth;
	float brightness;

	if (!fb || !edict || !qge_resource_id_is_valid(edict->model_id))
		return false;

	model_kind = qge_resource_id_kind(edict->model_id);
	if (model_kind != QGE_RESOURCE_ALIAS_MODEL &&
		model_kind != QGE_RESOURCE_SPRITE &&
		model_kind != QGE_RESOURCE_BSP_MODEL)
		return false;
	if (!QGE_ProjectSnapshotEdictBounds(edict, &bounds, &depth_world))
		return false;

	depth = depth_world / 4096.0f;
	if (depth > 1.0f) depth = 1.0f;
	if (depth < 0.0f) depth = 0.0f;
	brightness = QGE_SnapshotEntityBrightness(edict, model_kind, depth);

	QGE_EncodeSnapshotEntityDetailDWT(fb, edict, &bounds, brightness,
									  depth_world);

	qge_scene_encoded_edicts++;
	if (model_kind == QGE_RESOURCE_ALIAS_MODEL)
		qge_scene_alias_encoded++;
	else if (model_kind == QGE_RESOURCE_SPRITE)
		qge_scene_sprite_encoded++;
	if (QGE_IsSnapshotViewmodel(edict))
		qge_scene_viewmodel_encoded++;
	return true;
}

static int QGE_EncodeSnapshotEdicts(dwt_framebuffer_t *fb,
									const qge_frame_snapshot_t *snapshot)
{
	int encoded = 0;

	if (!fb || !snapshot || snapshot->edict_count == 0)
		return 0;

	for (int i = 0; i < (int)snapshot->edict_count; i++) {
		qge_scene_snapshot_edicts++;
		if (QGE_EncodeSnapshotEdictDWT(fb, &snapshot->edicts[i]))
			encoded++;
		else
			qge_scene_entity_misses++;
	}
	return encoded;
}

static qge_rgb_sample_t QGE_ParticleColor(uint32_t color_index, float intensity)
{
	const byte *rgba = (const byte *)&d_8to24table[color_index & 0xffu];
	qge_rgb_sample_t color;

	color.r = ((float)rgba[0] / 255.0f) * intensity;
	color.g = ((float)rgba[1] / 255.0f) * intensity;
	color.b = ((float)rgba[2] / 255.0f) * intensity;
	if (color.r + color.g + color.b < 0.01f) {
		color.r = intensity;
		color.g = intensity * 0.82f;
		color.b = intensity * 0.48f;
	}
	QGE_RGBClamp(&color);
	return color;
}

static qboolean QGE_EncodeSnapshotParticleDWT(dwt_framebuffer_t *fb,
											  const qge_snapshot_particle_t *particle)
{
	vec3_t origin;
	float sx, sy, depth_world, depth, intensity, scale;
	int radius;
	screen_rect_t bounds;
	qge_rgb_sample_t fill, edge;

	(void)fb;
	if (!particle)
		return false;

	origin[0] = particle->origin.x;
	origin[1] = particle->origin.y;
	origin[2] = particle->origin.z;
	if (!QGE_ProjectPoint(origin, &sx, &sy, &depth_world))
		return false;

	depth = depth_world / 4096.0f;
	if (depth > 1.0f) depth = 1.0f;
	if (depth < 0.0f) depth = 0.0f;
	scale = depth_world < 20.0f ? 1.08f : 1.0f + depth_world * 0.004f;
	radius = (int)(scale * 0.5f + 1.0f);
	if (radius < 1) radius = 1;
	if (radius > 7) radius = 7;

	bounds.x1 = (int)sx - radius;
	bounds.y1 = (int)sy - radius;
	bounds.x2 = (int)sx + radius;
	bounds.y2 = (int)sy + radius;
	if (bounds.x2 < 0 || bounds.y2 < 0 ||
		bounds.x1 >= qge_render_res || bounds.y1 >= qge_render_res)
		return false;
	if (bounds.x1 < 0) bounds.x1 = 0;
	if (bounds.y1 < 0) bounds.y1 = 0;
	if (bounds.x2 >= qge_render_res) bounds.x2 = qge_render_res - 1;
	if (bounds.y2 >= qge_render_res) bounds.y2 = qge_render_res - 1;

	intensity = 0.22f * (1.0f - depth * 0.25f);
	if (particle->lifetime > 0.0f && particle->lifetime < 0.5f)
		intensity *= 0.55f + particle->lifetime;
	if (intensity < 0.04f)
		intensity = 0.04f;
	fill = QGE_ParticleColor(particle->color, intensity);
	edge = QGE_RGBScaled(fill, 1.55f);

	QGE_SpatialFillRectColorDepth(&bounds, &fill, depth_world);
	QGE_SpatialOutlineRectColorDepth(&bounds, &edge, depth_world);
	QGE_EntityCoeffPixel((int)sx, (int)sy, &edge, depth_world);
	qge_scene_particle_coefficients += 3;
	return true;
}

static int QGE_EncodeSnapshotParticles(dwt_framebuffer_t *fb,
									   const qge_frame_snapshot_t *snapshot)
{
	int encoded = 0;

	if (!fb || !snapshot || snapshot->particle_count == 0)
		return 0;

	for (int i = 0; i < (int)snapshot->particle_count; i++) {
		qge_scene_snapshot_particles++;
		if (QGE_EncodeSnapshotParticleDWT(fb, &snapshot->particles[i]))
			encoded++;
	}
	qge_scene_encoded_particles += encoded;
	return encoded;
}

static float QGE_DisplayChannelEnergyAt(const float *buffer, int x, int y)
{
	float center;
	float axial = 0.0f;
	float diagonal = 0.0f;
	int res = qge_render_res;
	int idx = y * res + x;

	if (!buffer)
		return 0.0f;

	center = buffer[idx] > 0.0f ? buffer[idx] : 0.0f;
	if (quantum_render_display_filter.value < 0.5f)
		return center;

	if (x > 0)
		axial += buffer[idx - 1] > 0.0f ? buffer[idx - 1] : 0.0f;
	if (x + 1 < res)
		axial += buffer[idx + 1] > 0.0f ? buffer[idx + 1] : 0.0f;
	if (y > 0)
		axial += buffer[idx - res] > 0.0f ? buffer[idx - res] : 0.0f;
	if (y + 1 < res)
		axial += buffer[idx + res] > 0.0f ? buffer[idx + res] : 0.0f;
	if (x > 0 && y > 0)
		diagonal += buffer[idx - res - 1] > 0.0f ? buffer[idx - res - 1] : 0.0f;
	if (x + 1 < res && y > 0)
		diagonal += buffer[idx - res + 1] > 0.0f ? buffer[idx - res + 1] : 0.0f;
	if (x > 0 && y + 1 < res)
		diagonal += buffer[idx + res - 1] > 0.0f ? buffer[idx + res - 1] : 0.0f;
	if (x + 1 < res && y + 1 < res)
		diagonal += buffer[idx + res + 1] > 0.0f ? buffer[idx + res + 1] : 0.0f;

	return center * 0.70f + axial * 0.05f + diagonal * 0.0125f;
}

static float QGE_DisplayEnergyAt(int x, int y)
{
	float r = QGE_DisplayChannelEnergyAt(qge_render_color_buffer[QGE_DWT_R], x, y);
	float g = QGE_DisplayChannelEnergyAt(qge_render_color_buffer[QGE_DWT_G], x, y);
	float b = QGE_DisplayChannelEnergyAt(qge_render_color_buffer[QGE_DWT_B], x, y);

	return 0.299f * r + 0.587f * g + 0.114f * b;
}

static void QGE_InitToneLut(void)
{
	const float inv_log_tone = 1.0f / log1pf(4.0f);

	if (qge_tone_lut_ready)
		return;
	for (int i = 0; i < QGE_TONE_LUT_SIZE; i++) {
		float normalized = (float)i / (float)(QGE_TONE_LUT_SIZE - 1);
		qge_tone_lut[i] = log1pf(normalized * 4.0f) * inv_log_tone;
	}
	qge_tone_lut_ready = true;
}

static void QGE_ConvertRenderBufferToDisplay(int total_pixels,
											 float *max_val,
											 int *nonzero_pixels,
											 double *abs_sum)
{
	enum { QGE_TONE_BINS = 256 };
	int hist[QGE_TONE_BINS];
	float max_abs = 0.0001f;
	float median = 0.0f;
	float white = 1.0f;
	float floor_val;
	float inv_range;
	float hist_scale;
	float tone_index_scale = (float)(QGE_TONE_LUT_SIZE - 1);
	double abs_total = 0.0;
	int active = 0;
	int hist_active = 0;
	int hist_stride = 1;
	int median_target;
	int white_target;
	int running;
	int i;
	qboolean direct_display = quantum_render_display_filter.value < 0.5f;
	const float *rbuf = qge_render_color_buffer[QGE_DWT_R];
	const float *gbuf = qge_render_color_buffer[QGE_DWT_G];
	const float *bbuf = qge_render_color_buffer[QGE_DWT_B];

	if (!rbuf || !gbuf || !bbuf) {
		memset(qge_display_buffer, 0, total_pixels * 3);
		*max_val = max_abs;
		*nonzero_pixels = 0;
		*abs_sum = 0.0;
		return;
	}

	QGE_InitToneLut();
	memset(hist, 0, sizeof(hist));

	if (direct_display) {
		for (i = 0; i < total_pixels; i++) {
			float r = rbuf[i] > 0.0f ? rbuf[i] : 0.0f;
			float g = gbuf[i] > 0.0f ? gbuf[i] : 0.0f;
			float b = bbuf[i] > 0.0f ? bbuf[i] : 0.0f;
			float v = 0.299f * r + 0.587f * g + 0.114f * b;
			qge_render_buffer[i] = v;
			if (v > max_abs)
				max_abs = v;
			if (v > 0.0001f) {
				active++;
			}
			abs_total += v;
		}
	} else {
		for (int y = 0; y < qge_render_res; y++) {
			for (int x = 0; x < qge_render_res; x++) {
				i = y * qge_render_res + x;
				float v = QGE_DisplayEnergyAt(x, y);
				qge_render_buffer[i] = v;
				if (v > max_abs)
					max_abs = v;
				if (v > 0.0001f) {
					active++;
				}
				abs_total += v;
			}
		}
	}
	*nonzero_pixels = active;
	*abs_sum = abs_total;

	if (active <= 0) {
		memset(qge_display_buffer, 0, total_pixels * 3);
		*max_val = max_abs;
		qge_last_tone_floor = 0.0f;
		qge_last_tone_white = 1.0f;
		qge_last_tone_clipped = 0;
		return;
	}

	if (direct_display && total_pixels >= 512 * 512)
		hist_stride = 4;

	hist_scale = (float)(QGE_TONE_BINS - 1) / max_abs;
	for (i = 0; i < total_pixels; i += hist_stride) {
		float v = qge_render_buffer[i];
		if (v > 0.0001f) {
			int bin = (int)(v * hist_scale);
			if (bin < 0) bin = 0;
			if (bin >= QGE_TONE_BINS) bin = QGE_TONE_BINS - 1;
			hist[bin]++;
			hist_active++;
		}
	}
	if (hist_active <= 0 && hist_stride > 1) {
		for (i = 0; i < total_pixels; i++) {
			float v = qge_render_buffer[i];
			if (v > 0.0001f) {
				int bin = (int)(v * hist_scale);
				if (bin < 0) bin = 0;
				if (bin >= QGE_TONE_BINS) bin = QGE_TONE_BINS - 1;
				hist[bin]++;
				hist_active++;
			}
		}
	}

	median_target = hist_active / 2;
	white_target = (hist_active * 992) / 1000;
	if (white_target < median_target + 1)
		white_target = median_target + 1;

	running = 0;
	for (i = 0; i < QGE_TONE_BINS; i++) {
		running += hist[i];
		if (running >= median_target && median <= 0.0f)
			median = ((float)i / (float)(QGE_TONE_BINS - 1)) * max_abs;
		if (running >= white_target) {
			white = ((float)i / (float)(QGE_TONE_BINS - 1)) * max_abs;
			break;
		}
	}

	floor_val = median * 0.85f;
	if (white <= floor_val + 0.0001f)
		white = max_abs;
	inv_range = 1.0f / (white - floor_val + 0.0001f);

	qge_last_tone_floor = floor_val;
	qge_last_tone_white = white;
	qge_last_tone_clipped = 0;

	if (direct_display) {
		uint8_t *dst = qge_display_buffer;
		for (i = 0; i < total_pixels; i++) {
			float v = qge_render_buffer[i];
			float normalized = (v - floor_val) * inv_range;
			float scale;
			float r, g, b;
			int tone_index;

			if (normalized <= 0.0f || v <= 0.0001f) {
				dst[0] = 0;
				dst[1] = 0;
				dst[2] = 0;
				dst += 3;
				continue;
			}
			if (normalized >= 1.0f) {
				normalized = 1.0f;
				qge_last_tone_clipped++;
			}

			tone_index = (int)(normalized * tone_index_scale + 0.5f);
			normalized = qge_tone_lut[tone_index];
			scale = normalized / v;
			r = rbuf[i] > 0.0f ? rbuf[i] : 0.0f;
			g = gbuf[i] > 0.0f ? gbuf[i] : 0.0f;
			b = bbuf[i] > 0.0f ? bbuf[i] : 0.0f;
			r *= scale;
			g *= scale;
			b *= scale;
			if (r > 1.0f) r = 1.0f;
			if (g > 1.0f) g = 1.0f;
			if (b > 1.0f) b = 1.0f;
			dst[0] = (uint8_t)(r * 255.0f);
			dst[1] = (uint8_t)(g * 255.0f);
			dst[2] = (uint8_t)(b * 255.0f);
			dst += 3;
		}
	} else {
		for (int y = 0; y < qge_render_res; y++) {
			for (int x = 0; x < qge_render_res; x++) {
				i = y * qge_render_res + x;
				float r = QGE_DisplayChannelEnergyAt(qge_render_color_buffer[QGE_DWT_R], x, y);
				float g = QGE_DisplayChannelEnergyAt(qge_render_color_buffer[QGE_DWT_G], x, y);
				float b = QGE_DisplayChannelEnergyAt(qge_render_color_buffer[QGE_DWT_B], x, y);
				float v = qge_render_buffer[i];
				float normalized = (v - floor_val) * inv_range;
				float scale;
				int idx;

				if (normalized <= 0.0f)
					normalized = 0.0f;
				else if (normalized >= 1.0f) {
					normalized = 1.0f;
					qge_last_tone_clipped++;
				}

				normalized = qge_tone_lut[(int)(normalized * tone_index_scale + 0.5f)];
				if (v > 0.0001f)
					scale = normalized / v;
				else
					scale = 0.0f;
				r *= scale;
				g *= scale;
				b *= scale;
				if (r > 1.0f) r = 1.0f;
				if (g > 1.0f) g = 1.0f;
				if (b > 1.0f) b = 1.0f;
				idx = i * 3;
				qge_display_buffer[idx + 0] = (uint8_t)(r * 255.0f);
				qge_display_buffer[idx + 1] = (uint8_t)(g * 255.0f);
				qge_display_buffer[idx + 2] = (uint8_t)(b * 255.0f);
			}
		}
	}

	*max_val = max_abs;
}

/*
 * Encode the current Quake scene as wavelet coefficients in quantum state.
 *
 * Signal chain: BSP surfaces → screen-space bounds → DWT coefficient encoding
 *
 * This walks Quake's visible scene snapshot and rasterizes surfaces into
 * RGB spatial fields, then encodes each channel into sparse 32-qubit DWT
 * coefficient space before inverse reconstruction.
 */
static void QGE_EncodeScene(void)
{
	int encoded_world = 0;
	int surface_budget;
	qge_frame_snapshot_t *snapshot;
	double start, after_setup, after_raster, after_forward;

	if (!qge_dwt_fb[QGE_DWT_R] || !qge_dwt_fb[QGE_DWT_G] ||
		!qge_dwt_fb[QGE_DWT_B])
		return;

	start = Sys_DoubleTime();

	/* Reset write framebuffer for new frame */
	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++)
		qge_dwt_framebuffer_reset(qge_dwt_fb[ch]);
	QGE_SpatialClear();

	/* Encode visible BSP world surfaces submitted by R_MarkSurfaces. */
	surface_budget = (int)quantum_scene_surface_budget.value;
	if (surface_budget < 16) surface_budget = 16;
	if (surface_budget > QGE_MAX_SCENE_SURFACES) surface_budget = QGE_MAX_SCENE_SURFACES;
	snapshot = qge_get_frame_snapshot(qge_ctx);
	if (snapshot && !snapshot->sealed) {
		QGE_FrameSnapshotCaptureEdicts(snapshot);
		QGE_FrameSnapshotCaptureParticles(snapshot);
	}
	QGE_RunRenderGateKernel(snapshot);
	after_setup = Sys_DoubleTime();

	encoded_world = QGE_EncodeSnapshotWorldSurfaces(qge_dwt_fb[QGE_DWT_R],
													snapshot,
													surface_budget);
	if (!encoded_world)
		encoded_world = QGE_EncodeTransientWorldSurfaces(qge_dwt_fb[QGE_DWT_R],
														 surface_budget);
	qge_scene_encoded_surfaces = encoded_world;

	QGE_EncodeSnapshotEdicts(qge_dwt_fb[QGE_DWT_R], snapshot);
	QGE_EncodeSnapshotParticles(qge_dwt_fb[QGE_DWT_R], snapshot);

	if (!encoded_world) {
		screen_rect_t world_bounds = {
			.x1 = 0, .y1 = 0,
			.x2 = qge_render_res - 1, .y2 = qge_render_res - 1
		};
		QGE_SpatialFillRectDepth(&world_bounds,
								 0.15f * (1.0f - 0.95f * 0.1f),
								 8192.0f);
	}
	after_raster = Sys_DoubleTime();

	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++) {
		float *source = qge_spatial_color_buffer[ch] ?
						qge_spatial_color_buffer[ch] :
						qge_spatial_encode_buffer;
		qge_dwt_encode_spatial_inplace(qge_dwt_fb[ch], source,
									   qge_render_res, qge_render_res);
	}
	after_forward = Sys_DoubleTime();
	qge_scene_setup_ms = (after_setup - start) * 1000.0;
	qge_scene_raster_ms = (after_raster - after_setup) * 1000.0;
	qge_scene_forward_dwt_ms = (after_forward - after_raster) * 1000.0;
}

static void QGE_ResetTextureUnitsForBlit(void)
{
	if (GL_SelectTextureFunc) {
		for (int unit = qge_blit_texture_units - 1; unit >= 3; unit--) {
			GL_SelectTextureFunc(GL_TEXTURE0_ARB + unit);
			glDisable(GL_TEXTURE_2D);
			glBindTexture(GL_TEXTURE_2D, 0);
		}
	}

	GL_SelectTexture(GL_TEXTURE2_ARB);
	GL_Bind(NULL);
	glDisable(GL_TEXTURE_2D);
	GL_SelectTexture(GL_TEXTURE1_ARB);
	GL_Bind(NULL);
	glDisable(GL_TEXTURE_2D);
	GL_SelectTexture(GL_TEXTURE0_ARB);
}

/*
 * Blit the quantum framebuffer to the GL display.
 * Renders the quantum pixel buffer as a fullscreen textured quad.
 */
static void QGE_BlitToScreen(void)
{
	if (!qge_texture || !qge_display_buffer) return;

	/* Quake rendering often leaves multitexture enabled on unit 1/2.
	 * QGE owns a single GL_TEXTURE_2D blit texture, so force all higher
	 * texture units inert before upload/draw or the driver may sample an
	 * unloaded unit. */
	QGE_ResetTextureUnitsForBlit();

	while (glGetError() != GL_NO_ERROR) {
		/* Clear stale GL errors so diagnostics below describe this blit. */
	}

	/* Upload quantum frame to GL texture */
	glBindTexture(GL_TEXTURE_2D, qge_texture);
	if (qge_display_texture_dirty) {
		glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
		glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, qge_render_res, qge_render_res,
						GL_RGB, GL_UNSIGNED_BYTE, qge_display_buffer);
		qge_last_gl_upload_error = glGetError();
		qge_display_texture_dirty = false;
	} else {
		qge_last_gl_upload_error = GL_NO_ERROR;
	}

	/* Save GL state */
	glPushAttrib(GL_ALL_ATTRIB_BITS);
	glMatrixMode(GL_PROJECTION);
	glPushMatrix();
	glLoadIdentity();
	glOrtho(0, 1, 0, 1, -1, 1);
	glMatrixMode(GL_MODELVIEW);
	glPushMatrix();
	glLoadIdentity();

	/* Draw fullscreen quad with quantum texture */
	glEnable(GL_TEXTURE_2D);
	glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);
	glDisable(GL_DEPTH_TEST);
	glDisable(GL_CULL_FACE);
	glEnable(GL_BLEND);
	glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);

	float alpha = QGE_RenderIsPrimary() ? 1.0f : quantum_overlay_alpha.value;
	if (alpha < 0.0f) alpha = 0.0f;
	if (alpha > 1.0f) alpha = 1.0f;
	glColor4f(1, 1, 1, alpha);

	glBegin(GL_QUADS);
	glTexCoord2f(0, 1); glVertex2f(0, 0);
	glTexCoord2f(1, 1); glVertex2f(1, 0);
	glTexCoord2f(1, 0); glVertex2f(1, 1);
	glTexCoord2f(0, 0); glVertex2f(0, 1);
	glEnd();
	qge_last_gl_draw_error = glGetError();

	/* Restore GL state */
	glPopMatrix();
	glMatrixMode(GL_PROJECTION);
	glPopMatrix();
	glPopAttrib();

	QGE_ResetTextureUnitsForBlit();
}

static int QGE_RenderUpdateInterval(void)
{
	int interval = (int)(quantum_render_update_interval.value + 0.5f);

	if (interval < 1)
		interval = 1;
	if (interval > 16)
		interval = 16;
	return interval;
}

static qboolean QGE_RenderShouldUpdateFrame(void)
{
	int interval;

	if (!qge_initialized || quantum_render.value < 0.5f)
		return false;
	interval = QGE_RenderUpdateInterval();
	if (qge_render_last_update_frame < 0)
		return true;
	if (qge_frame_count <= qge_render_last_update_frame)
		return true;
	return qge_frame_count - qge_render_last_update_frame >= interval;
}

static const char *QGE_RenderOwnershipFallbackReason(void)
{
	if (!QGE_RenderIsPrimary())
		return "overlay_not_primary";
	if (qge_render_classic_3d_passes > 0)
		return "classic3d_visible";
	if (qge_scene_polygon_fallback > 0)
		return "polygon_fallback";
	if (qge_scene_polygon_surrogate > 0)
		return "polygon_surrogate";
	if (qge_scene_entity_misses > 0)
		return "entity_miss";
	if (qge_scene_snapshot_misses > 0)
		return "surface_snapshot_miss";
	if (qge_scene_encoded_surfaces <= 0 &&
		(qge_scene_surface_count > 0 || qge_scene_world_surfaces > 0))
		return "world_unowned";
	if (QGE_CLASSIC_2D_VISIBLE > 0 && QGE_2DHasUnownedClassicOutput())
		return "classic2d_unowned";
	return "none";
}

void QGE_RenderScene(void)
{
	int active = 0;
	float sparsity = 0.0f;
	int total_coefficients;
	double after_encode, after_dwt, after_convert, after_blit;
	double encode_ms, dwt_ms, convert_ms, blit_ms;
	int update_interval;
	int primary_fb;
	int classic2d;
	int suppressed2d;
	int own_world;
	int own_textures;
	int own_lightmaps;
	int own_entities;
	int own_sprites;
	int own_particles;
	int own_viewmodel;
	int own_hud;
	int own_console;
	int native_idwt_success = 0;
	int native_idwt_fallback = 0;
	int cpu_idwt = 0;
	uint32_t render_trace_flags;

	if (!qge_initialized ||
		!qge_dwt_fb[QGE_DWT_R] || !qge_dwt_fb[QGE_DWT_G] ||
		!qge_dwt_fb[QGE_DWT_B] ||
		!qge_render_buffer || !qge_display_buffer ||
		!qge_render_color_buffer[QGE_DWT_R] ||
		!qge_render_color_buffer[QGE_DWT_G] ||
		!qge_render_color_buffer[QGE_DWT_B])
		return;

	if (quantum_render.value < 0.5f)
		return;

	update_interval = QGE_RenderUpdateInterval();
	if (!QGE_RenderShouldUpdateFrame()) {
		qge_render_reused_frames++;
		QGE_BlitToScreen();
		return;
	}

	double start = Sys_DoubleTime();

	/* Step 1: Encode scene geometry as wavelet coefficients.
	 * Resets the framebuffer then encodes all visible entities. */
	QGE_EncodeScene();
	after_encode = Sys_DoubleTime();

	/* Step 2: Quantum signal processing — extract coefficients and inverse DWT.
	 * Uses the SAME buffer we just encoded into (like the working demo).
	 * Sparse-only path — active_indices/values provide the wavelet representation
	 * without iterating all 268M amplitudes. */
	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++) {
		qge_dwt_render(qge_dwt_fb[ch], qge_render_color_buffer[ch]);
		switch (qge_dwt_last_render_backend(qge_dwt_fb[ch])) {
		case QGE_DWT_RENDER_BACKEND_NATIVE:
			native_idwt_success++;
			break;
		case QGE_DWT_RENDER_BACKEND_NATIVE_FALLBACK:
			native_idwt_fallback++;
			break;
		case QGE_DWT_RENDER_BACKEND_CPU:
			cpu_idwt++;
			break;
		case QGE_DWT_RENDER_BACKEND_NONE:
		default:
			break;
		}
	}
	after_dwt = Sys_DoubleTime();

	/* Step 3: Convert float pixels to RGB display buffer. */
	float max_val = 0.0001f;
	int nonzero_pixels = 0;
	double abs_sum = 0.0;
	int total_pixels = qge_render_res * qge_render_res;
	QGE_ConvertRenderBufferToDisplay(total_pixels, &max_val, &nonzero_pixels, &abs_sum);
	qge_display_texture_dirty = true;
	after_convert = Sys_DoubleTime();

	/* Step 4: Blit to screen */
	QGE_BlitToScreen();
	after_blit = Sys_DoubleTime();
	qge_render_last_update_frame = qge_frame_count;

	double elapsed = (after_blit - start) * 1000.0;
	encode_ms = (after_encode - start) * 1000.0;
	dwt_ms = (after_dwt - after_encode) * 1000.0;
	convert_ms = (after_convert - after_dwt) * 1000.0;
	blit_ms = (after_blit - after_convert) * 1000.0;
	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++)
		active += qge_dwt_get_active_count(qge_dwt_fb[ch]);
	total_coefficients = qge_render_res * qge_render_res * QGE_DWT_CHANNELS;
	if (total_coefficients > 0)
		sparsity = (float)active / (float)total_coefficients;

	primary_fb = QGE_RenderIsPrimary() ? 1 : 0;
	own_hud = QGE_2DOwnsHud();
	own_console = QGE_2DOwnsConsole();
	classic2d = QGE_2DHasUnownedClassicOutput() ? QGE_CLASSIC_2D_VISIBLE : 0;
	suppressed2d = (!classic2d && QGE_RenderIsPrimary()) ?
		(QGE_2DLastDrawCount() > 0 ? QGE_2DLastDrawCount() : 1) : 0;
	own_world =
		qge_scene_encoded_surfaces > 0 &&
		qge_scene_polygon_fallback == 0 &&
		qge_scene_polygon_surrogate == 0 &&
		qge_scene_snapshot_misses == 0;
	own_textures =
		qge_scene_material_encoded > 0 &&
		qge_scene_texture_cache_misses == 0;
	own_lightmaps =
		qge_scene_lightmapped_surfaces > 0 &&
		qge_scene_lightmap_cache_misses == 0;
	own_entities =
		qge_scene_snapshot_edicts == qge_scene_encoded_edicts &&
		qge_scene_entity_misses == 0;
	own_sprites =
		(qge_scene_sprite_encoded > 0) ||
		(own_entities && qge_scene_snapshot_edicts == 0);
	own_particles =
		qge_scene_snapshot_particles == qge_scene_encoded_particles;
	own_viewmodel = qge_scene_viewmodel_encoded > 0;

	qge_quantum_runtime_t *rt = QGE_Runtime();
	if (rt) {
		qge_state_probe_t probe;
		render_trace_flags = (uint32_t)qge_scene_snapshot_misses;
		if (qge_render_qge_primary_owned)
			render_trace_flags |= QGE_RENDER_TRACE_FLAG_PRIMARY_OWNED;
		if (native_idwt_success > 0)
			render_trace_flags |= QGE_RENDER_TRACE_FLAG_NATIVE_IDWT;
		if (native_idwt_fallback > 0)
			render_trace_flags |= QGE_RENDER_TRACE_FLAG_NATIVE_IDWT_FALLBACK;
		if (cpu_idwt > 0)
			render_trace_flags |= QGE_RENDER_TRACE_FLAG_CPU_IDWT;
		memset(&probe, 0, sizeof(probe));
		probe.frame = qge_frame_count;
		probe.server_time_msec = QGE_ServerTimeMsec();
		probe.domain = QGE_DOMAIN_RENDER;
		probe.representation = QGE_REP_SPARSE_DWT;
		probe.active_basis_count = active;
		probe.qubit_count =
			qge_quantum_qubits_for_basis_count((uint64_t)total_coefficients);
		probe.memory_bytes = (uint64_t)qge_render_res * (uint64_t)qge_render_res *
							 (uint64_t)QGE_DWT_CHANNELS *
							 (uint64_t)sizeof(float);
		probe.subject_id = qge_scene_snapshot_surfaces;
		probe.flags = render_trace_flags;
		probe.entropy = sparsity;
		probe.coherence = 1.0 - sparsity;
		probe.max_probability = max_val;
		probe.total_probability = abs_sum;
		strlcpy(probe.label, "render_sparse_dwt", sizeof(probe.label));
		qge_quantum_record_probe(rt, &probe);
	}

	/* Print stats every 30 frames */
	if (quantum_debug.value >= 1.0f || qge_frame_count % 30 == 0) {
		if (quantum_debug.value >= 1.0f) {
			if (qge_frame_count < 5 || (qge_frame_count % 60) == 0 ||
				qge_scene_encoded_particles > 0) {
				Con_Printf("QGE render frame=%d mode=%s owner=%s classic3d=%d suppressed3d=%d "
						   "res=%d time=%.1f encode=%.1f setup=%.1f raster=%.1f fdwt=%.1f dwt=%.1f convert=%.1f blit=%.1f reuse=%d interval=%d "
						   "coeffs=%d snapshot=%d snapshot_miss=%d "
						   "texcache=%d/%d lightcache=%d/%d poly=%d tris=%d edgefills=%d microfill=%d "
						   "culled=%d surrogate=%d micro=%d clipped=%d fallback=%d "
						   "encoded=%d material=%d edicts=%d alias=%d sprites=%d sbill=%d emesh=%d ecoeff=%d "
						   "viewmodel=%d entity_miss=%d particles=%d pcoeff=%d gates=%d shots=%d "
						   "readout=%.3f edgeq=%.3f ggain=%.3f egain=%.3f "
						   "native_idwt=%d idwt_fallback=%d cpu_idwt=%d "
						   "nonzero=%d/%d primary_fb=%d classic2d=%d suppressed2d=%d "
						   "own_world=%d own_textures=%d own_lightmaps=%d own_entities=%d own_sprites=%d own_particles=%d own_viewmodel=%d "
						   "own_hud=%d own_console=%d "
						   "fallback_reason=%s\n",
						   qge_frame_count, QGE_RenderIsPrimary() ? "primary" : "overlay",
						   qge_render_qge_primary_owned ? "qge_3d" : "mixed",
						   qge_render_classic_3d_passes,
						   qge_render_suppressed_3d_passes,
						   qge_render_res, elapsed, encode_ms,
						   qge_scene_setup_ms, qge_scene_raster_ms,
						   qge_scene_forward_dwt_ms, dwt_ms,
						   convert_ms, blit_ms,
						   qge_render_reused_frames, update_interval,
						   active, qge_scene_snapshot_surfaces,
						   qge_scene_snapshot_misses, qge_scene_texture_cache_hits,
						   qge_scene_texture_cache_misses, qge_scene_lightmap_cache_hits,
						   qge_scene_lightmap_cache_misses, qge_scene_polygon_encoded,
						   qge_scene_polygon_triangles, qge_scene_triangle_edge_fills,
						   qge_scene_polygon_micro_fills,
						   qge_scene_polygon_culled,
						   qge_scene_polygon_surrogate,
						   qge_scene_polygon_surrogate_micro,
						   qge_scene_polygon_surrogate_clipped,
						   qge_scene_polygon_fallback,
						   qge_scene_encoded_surfaces,
						   qge_scene_material_encoded, qge_scene_encoded_edicts,
						   qge_scene_alias_encoded, qge_scene_sprite_encoded,
						   qge_scene_sprite_billboards,
						   qge_scene_entity_mesh_triangles,
						   qge_scene_entity_coefficients,
						   qge_scene_viewmodel_encoded, qge_scene_entity_misses,
						   qge_scene_encoded_particles,
						   qge_scene_particle_coefficients,
						   qge_render_gate_total, qge_render_gate_shots,
						   qge_render_gate_probability,
						   qge_render_gate_edge_observable,
						   qge_render_gate_gain, qge_render_gate_edge_gain,
						   native_idwt_success, native_idwt_fallback,
						   cpu_idwt,
						   nonzero_pixels, total_pixels,
						   primary_fb, classic2d, suppressed2d,
						   own_world, own_textures, own_lightmaps,
						   own_entities, own_sprites, own_particles,
						   own_viewmodel,
						   own_hud, own_console,
						   QGE_RenderOwnershipFallbackReason());
			}
			fprintf(stderr, "QGE render frame=%d mode=%s owner=%s classic3d=%d suppressed3d=%d "
					"res=%d time=%.1fms encode=%.1fms setup=%.1fms raster=%.1fms fdwt=%.1fms dwt=%.1fms convert=%.1fms blit=%.1fms reuse=%d interval=%d "
					"coeffs=%d sparse=%.1f%% "
					"scene_surfaces=%d snapshot_surfaces=%d snapshot_misses=%d "
					"texcache=%d/%d lightcache=%d/%d poly=%d tris=%d edgefills=%d microfill=%d "
					"culled=%d surrogate=%d micro=%d clipped=%d invalid=%d fallback=%d encoded_surfaces=%d "
					"material_encoded=%d snapshot_edicts=%d encoded_edicts=%d alias=%d "
					"sprites=%d sprite_billboards=%d entity_mesh_tris=%d entity_coeffs=%d viewmodel=%d entity_misses=%d "
					"snapshot_particles=%d encoded_particles=%d particle_coeffs=%d visedicts=%d nonzero=%d/%d max=%.6f sum=%.3f "
					"gate_kernel=%d gates=%d h=%d ry=%d rz=%d ent=%d phase=%d gate_active=%d "
					"shots=%d readout_ones=%d edge_ones=%d majority=0x%llx "
					"gate_p=%.6f gate_edge=%.6f gate_gain=%.6f edge_gain=%.6f material_gain=%.6f "
					"gate_rgb=%.4f/%.4f/%.4f gate_entropy=%.3f gate_coh=%.3f "
					"native_idwt=%d idwt_fallback=%d cpu_idwt=%d "
					"tone_floor=%.6f tone_white=%.6f tone_clip=%d levels=%d gl_upload=0x%x gl_draw=0x%x "
					"primary_fb=%d classic2d=%d suppressed2d=%d "
					"own_world=%d own_textures=%d own_lightmaps=%d own_entities=%d own_sprites=%d own_particles=%d own_viewmodel=%d "
					"own_hud=%d own_console=%d "
					"fallback_reason=%s\n",
					qge_frame_count, QGE_RenderIsPrimary() ? "primary" : "overlay",
					qge_render_qge_primary_owned ? "qge_3d" : "mixed",
					qge_render_classic_3d_passes,
					qge_render_suppressed_3d_passes,
					qge_render_res, elapsed, encode_ms,
					qge_scene_setup_ms, qge_scene_raster_ms,
					qge_scene_forward_dwt_ms, dwt_ms, convert_ms,
					blit_ms, qge_render_reused_frames, update_interval,
					active, sparsity * 100.0f,
					qge_scene_surface_count, qge_scene_snapshot_surfaces,
					qge_scene_snapshot_misses, qge_scene_texture_cache_hits,
					qge_scene_texture_cache_misses, qge_scene_lightmap_cache_hits,
					qge_scene_lightmap_cache_misses, qge_scene_polygon_encoded,
					qge_scene_polygon_triangles, qge_scene_triangle_edge_fills,
					qge_scene_polygon_micro_fills,
					qge_scene_polygon_culled,
					qge_scene_polygon_surrogate,
					qge_scene_polygon_surrogate_micro,
					qge_scene_polygon_surrogate_clipped,
					qge_scene_polygon_surrogate_invalid,
					qge_scene_polygon_fallback,
					qge_scene_encoded_surfaces,
					qge_scene_material_encoded, qge_scene_snapshot_edicts,
					qge_scene_encoded_edicts, qge_scene_alias_encoded,
					qge_scene_sprite_encoded, qge_scene_sprite_billboards,
					qge_scene_entity_mesh_triangles,
					qge_scene_entity_coefficients,
					qge_scene_viewmodel_encoded,
					qge_scene_entity_misses, qge_scene_snapshot_particles,
					qge_scene_encoded_particles,
					qge_scene_particle_coefficients, cl_numvisedicts,
					nonzero_pixels, total_pixels,
					max_val, abs_sum,
					qge_render_gate_initialized && quantum_render_gate_kernel.value >= 0.5f,
					qge_render_gate_total, qge_render_gate_h, qge_render_gate_ry,
					qge_render_gate_rz, qge_render_gate_entangling,
					qge_render_gate_phase_count, qge_render_gate_active_basis,
					qge_render_gate_shots, qge_render_gate_readout_ones,
					qge_render_gate_edge_ones,
					(unsigned long long)qge_render_gate_majority_basis,
					qge_render_gate_probability, qge_render_gate_edge_observable,
					qge_render_gate_gain, qge_render_gate_edge_gain,
					qge_render_gate_material_gain,
					qge_render_gate_color_gain[QGE_DWT_R],
					qge_render_gate_color_gain[QGE_DWT_G],
					qge_render_gate_color_gain[QGE_DWT_B],
					qge_render_gate_entropy, qge_render_gate_coherence,
					native_idwt_success, native_idwt_fallback, cpu_idwt,
					qge_last_tone_floor, qge_last_tone_white,
					qge_last_tone_clipped, qge_dwt_levels,
					(unsigned)qge_last_gl_upload_error,
					(unsigned)qge_last_gl_draw_error,
					primary_fb, classic2d, suppressed2d,
					own_world, own_textures, own_lightmaps,
					own_entities, own_sprites, own_particles,
					own_viewmodel,
					own_hud, own_console,
					QGE_RenderOwnershipFallbackReason());
		} else {
			Con_DPrintf("QGE render: %.1f ms | %d coeffs (%.1f%% sparse) | %d DWT levels\n",
					   elapsed, active, sparsity * 100.0f,
					   qge_dwt_levels);
		}
	}
}

qboolean QGE_RenderIsPrimary(void)
{
	return qge_initialized && quantum_render.value >= 1.5f;
}

void QGE_RenderSetOwnershipTelemetry(int classic_3d_passes,
									 int suppressed_3d_passes)
{
	if (classic_3d_passes < 0)
		classic_3d_passes = 0;
	if (suppressed_3d_passes < 0)
		suppressed_3d_passes = 0;
	qge_render_classic_3d_passes = classic_3d_passes;
	qge_render_suppressed_3d_passes = suppressed_3d_passes;
	qge_render_qge_primary_owned =
		QGE_RenderIsPrimary() && classic_3d_passes == 0 &&
		suppressed_3d_passes > 0;
}

/* ============================================================================
 * Quantum Visibility
 * ============================================================================ */

static qboolean QGE_VisAuthorityRequested(void)
{
	/* Mode 2 is the documented authority request; mode 1 stays shadow-only. */
	return qge_initialized && quantum_vis.value >= 1.5f;
}

static qboolean QGE_VisControlledAuthoritySmoke(void)
{
	/* Mode 3 is a controlled smoke path for the authority handoff only. */
	return qge_initialized && quantum_vis.value >= 2.5f;
}

qboolean QGE_VisShadowBegin(qmodel_t *model)
{
	int i;

	qge_vis_shadow_active = false;
	qge_vis_shadow_model = NULL;
	qge_vis_shadow_registered_surfaces = 0;
	qge_vis_authority_requested = QGE_VisAuthorityRequested() ? 1 : 0;
	qge_vis_authority_selected = 0;
	qge_vis_fallback_selected = 1;
	qge_vis_shadow_set_controlled_authority_smoke(
		QGE_VisControlledAuthoritySmoke() ? true : false);
	qge_vis_authority_model = NULL;
	qge_vis_authority_mask = NULL;
	qge_vis_authority_mask_count = 0;
	memset(&qge_vis_last_decision, 0, sizeof(qge_vis_last_decision));
	qge_vis_last_decision_valid = false;
	qge_vis_authority_reason = qge_vis_authority_requested ?
		"shadow_unavailable_fallback" : "authority_not_requested";
	qge_vis_fallback_reason = qge_vis_authority_reason;

	if (!qge_initialized || quantum_vis.value < 0.5f ||
		!model || !model->surfaces || model->numsurfaces <= 0)
		return false;

	qge_vis_clear_surfaces();
	for (i = 0; i < model->numsurfaces; i++) {
		msurface_t *surf = &model->surfaces[i];
		qge_vis_register_surface(i,
								 surf->mins[0], surf->mins[1], surf->mins[2],
								 surf->maxs[0], surf->maxs[1], surf->maxs[2]);
	}

	qge_vis_shadow_begin(model->numsurfaces, 0.0f);

	qge_vis_shadow_active = true;
	qge_vis_shadow_model = model;
	qge_vis_shadow_registered_surfaces = model->numsurfaces;
	return true;
}

void QGE_VisShadowMarkClassicSurface(qmodel_t *model, msurface_t *surf)
{
	int surface_id;

	if (!qge_vis_shadow_active || model != qge_vis_shadow_model ||
		!model || !surf)
		return;
	if (surf < model->surfaces || surf >= model->surfaces + model->numsurfaces)
		return;

	surface_id = (int)(surf - model->surfaces);
	qge_vis_shadow_mark_classic_visible(surface_id);
}

static void QGE_TraceVisShadowParity(const qge_vis_shadow_stats_t *stats)
{
	qge_quantum_runtime_t *rt;
	qge_state_probe_t probe;
	int mismatch_count;
	uint64_t hash;
	uint32_t flags = 0u;

	if (!stats)
		return;

	mismatch_count = stats->false_positive_count +
		stats->false_negative_count + stats->false_negative_repaired_count;
	if (qge_vis_shadow_registered_surfaces > 0)
		flags |= QGE_VIS_TRACE_FLAG_REGISTERED;
	if (mismatch_count > 0)
		flags |= QGE_VIS_TRACE_FLAG_MISMATCH;
	if (stats->false_positive_count > 0)
		flags |= QGE_VIS_TRACE_FLAG_FALSE_POSITIVE;
	if (stats->false_negative_count > 0)
		flags |= QGE_VIS_TRACE_FLAG_FALSE_NEGATIVE;
	if (stats->false_negative_repaired_count > 0)
		flags |= QGE_VIS_TRACE_FLAG_FN_REPAIRED;
	if (stats->overflow_count > 0)
		flags |= QGE_VIS_TRACE_FLAG_OVERFLOW;

	qge_vis_authority_requested = QGE_VisAuthorityRequested() ? 1 : 0;
	qge_vis_authority_selected =
		qge_vis_authority_requested && stats->authority_ready &&
		!stats->fallback_required;
	qge_vis_fallback_selected = !qge_vis_authority_selected;

	if (!qge_vis_authority_requested) {
		qge_vis_authority_reason =
			qge_vis_gate_reason_name(QGE_VIS_GATE_REASON_AUTHORITY_NOT_REQUESTED);
		qge_vis_fallback_reason = qge_vis_authority_reason;
	} else {
		qge_vis_authority_reason =
			qge_vis_gate_reason_name(stats->authority_reason);
		qge_vis_fallback_reason = qge_vis_authority_selected ?
			qge_vis_gate_reason_name(QGE_VIS_GATE_REASON_NONE) :
			qge_vis_gate_reason_name(stats->fallback_reason);
	}

	if (qge_vis_authority_requested)
		flags |= QGE_VIS_TRACE_FLAG_AUTHORITY_REQUESTED;
	if (stats->authority_ready)
		flags |= QGE_VIS_TRACE_FLAG_AUTHORITY_READY;
	if (qge_vis_authority_selected)
		flags |= QGE_VIS_TRACE_FLAG_AUTHORITY_SELECTED;
	if (qge_vis_fallback_selected)
		flags |= QGE_VIS_TRACE_FLAG_FALLBACK_SELECTED;
	if (stats->fallback_reason == QGE_VIS_GATE_REASON_WARMUP_PENDING ||
		stats->fallback_reason == QGE_VIS_GATE_REASON_SURFACE_COUNT_CHANGED)
		flags |= QGE_VIS_TRACE_FLAG_WARMUP_PENDING;
	if (stats->controlled_authority_smoke)
		flags |= QGE_VIS_TRACE_FLAG_CONTROLLED_SMOKE;

	hash = QGE_RegistryHashStep(stats->classic_fingerprint,
								stats->qge_fingerprint);
	hash = QGE_RegistryHashStep(hash, stats->mismatch_fingerprint);
	hash = QGE_RegistryHashStep(hash, (uint64_t)(uint32_t)mismatch_count);
	hash = QGE_RegistryHashStep(hash, (uint64_t)stats->authority_reason);
	hash = QGE_RegistryHashStep(hash, (uint64_t)stats->fallback_reason);
	hash = QGE_RegistryHashStep(hash,
								(uint64_t)stats->consecutive_clean_frames);

	rt = QGE_Runtime();
	if (rt) {
		memset(&probe, 0, sizeof(probe));
		probe.frame = qge_frame_count;
		probe.server_time_msec = QGE_ServerTimeMsec();
		probe.domain = QGE_DOMAIN_VISIBILITY;
		probe.representation = QGE_REP_GROVER_SEARCH;
		probe.subject_id = stats->total_surfaces;
		probe.flags = flags;
		probe.state_hash = hash;
		probe.entropy = stats->total_surfaces > 0 ?
			(double)stats->classic_visible_count /
			(double)stats->total_surfaces : 0.0;
		probe.coherence = stats->total_surfaces > 0 ?
			1.0 - ((double)mismatch_count / (double)stats->total_surfaces) : 1.0;
		if (probe.coherence < 0.0)
			probe.coherence = 0.0;
		probe.max_probability = (double)stats->false_positive_count;
		probe.total_probability =
			(double)(stats->false_negative_count +
					 stats->false_negative_repaired_count);
		probe.active_basis_count = stats->qge_visible_count;
		probe.qubit_count =
			qge_quantum_qubits_for_basis_count((uint64_t)stats->total_surfaces);
		probe.memory_bytes = (uint64_t)stats->total_surfaces * 2u;
		strlcpy(probe.label, "vis_shadow_parity", sizeof(probe.label));
		qge_quantum_record_probe(rt, &probe);

		memset(&probe, 0, sizeof(probe));
		probe.frame = qge_frame_count;
		probe.server_time_msec = QGE_ServerTimeMsec();
		probe.domain = QGE_DOMAIN_VISIBILITY;
		probe.representation = QGE_REP_CLASSICAL_ORACLE;
		probe.subject_id = qge_vis_authority_selected ? 1 : 0;
		probe.flags = flags;
		probe.state_hash = hash ^
			((uint64_t)stats->cumulative_mismatch_count << 32);
		probe.entropy = (double)stats->fallback_reason;
		probe.coherence = stats->authority_ready ? 1.0 : 0.0;
		probe.max_probability = stats->fallback_required ? 1.0 : 0.0;
		probe.total_probability =
			(double)stats->cumulative_false_negative_count;
		probe.active_basis_count = stats->consecutive_clean_frames;
		probe.qubit_count = stats->clean_frames_required;
		probe.memory_bytes = (uint64_t)stats->cumulative_mismatch_count;
		strlcpy(probe.label, "vis_authority_gate", sizeof(probe.label));
		qge_quantum_record_probe(rt, &probe);

		if (mismatch_count > 0 ||
			(qge_vis_authority_requested && qge_vis_fallback_selected)) {
			qge_fallback_event_t event;

			memset(&event, 0, sizeof(event));
			event.frame = qge_frame_count;
			event.server_time_msec = QGE_ServerTimeMsec();
			event.domain = QGE_DOMAIN_VISIBILITY;
			event.representation = QGE_REP_GROVER_SEARCH;
			event.subject_id = stats->total_surfaces;
			event.reason_code =
				(stats->false_positive_count > 0 ? 1 : 0) |
				(stats->false_negative_count > 0 ? 2 : 0) |
				(stats->false_negative_repaired_count > 0 ? 8 : 0) |
				((int)stats->fallback_reason << 8);
			event.metric_value = (double)mismatch_count;
			q_snprintf(event.message, sizeof(event.message),
					   "reason=%s authority=%s fp=%d fn=%d repaired_fn=%d clean=%d/%d total_mismatch=%d c=%llx q=%llx m=%llx",
					   qge_vis_fallback_reason,
					   qge_vis_authority_reason,
					   stats->false_positive_count,
					   stats->false_negative_count,
					   stats->false_negative_repaired_count,
					   stats->consecutive_clean_frames,
					   stats->clean_frames_required,
					   stats->cumulative_mismatch_count,
					   (unsigned long long)stats->classic_fingerprint,
					   (unsigned long long)stats->qge_fingerprint,
					   (unsigned long long)stats->mismatch_fingerprint);
			qge_quantum_record_fallback(rt, &event);
		}
	}

	if (quantum_debug.value >= 1.0f ||
		qge_frame_count < 5 || (qge_frame_count % 60) == 0) {
		fprintf(stderr, "QGE vis shadow frame=%d total=%d classic=%d qge=%d "
				"match=%d hidden=%d fp=%d fn=%d repaired_fn=%d overflow=%d "
				"first_fp=%d first_fn=%d first_repaired_fn=%d threshold=%.8f prob_sum=%.6f "
				"prob_max=%.6f classic_fp=0x%llx qge_fp=0x%llx "
				"mismatch_fp=0x%llx clean=%d/%d frames=%d "
				"total_mismatch=%d total_fn=%d authority_ready=%d "
				"authority_requested=%d authority_selected=%d "
				"fallback_selected=%d controlled_smoke=%d "
				"authority_reason=%s "
				"fallback_reason=%s\n",
				qge_frame_count, stats->total_surfaces,
				stats->classic_visible_count, stats->qge_visible_count,
				stats->matched_visible_count, stats->matched_hidden_count,
				stats->false_positive_count, stats->false_negative_count,
				stats->false_negative_repaired_count,
				stats->overflow_count,
				stats->first_false_positive, stats->first_false_negative,
				stats->first_false_negative_repaired,
				stats->threshold, stats->qge_probability_sum,
				stats->qge_probability_max,
				(unsigned long long)stats->classic_fingerprint,
				(unsigned long long)stats->qge_fingerprint,
				(unsigned long long)stats->mismatch_fingerprint,
				stats->consecutive_clean_frames,
				stats->clean_frames_required,
				stats->frames_observed,
				stats->cumulative_mismatch_count,
				stats->cumulative_false_negative_count,
				stats->authority_ready ? 1 : 0,
				qge_vis_authority_requested,
				qge_vis_authority_selected,
				qge_vis_fallback_selected,
				stats->controlled_authority_smoke ? 1 : 0,
				qge_vis_authority_reason,
				qge_vis_fallback_reason);
	}
}

void QGE_VisShadowEnd(qmodel_t *model)
{
	qge_vis_shadow_stats_t stats;
	const unsigned char *visible_mask = NULL;
	int surface_count = 0;

	if (!qge_vis_shadow_active || model != qge_vis_shadow_model)
		return;

	qge_vis_setup_viewpoint((qge_vec3_t){
							r_refdef.vieworg[0],
							r_refdef.vieworg[1],
							r_refdef.vieworg[2]
						},
						(qge_vec3_t){vpn[0], vpn[1], vpn[2]});
	if (qge_vis_shadow_finish(&stats))
	{
		QGE_TraceVisShadowParity(&stats);
		qge_vis_last_decision_valid =
			qge_vis_get_writeback_decision(QGE_VisAuthorityRequested(),
										   &qge_vis_last_decision);
		if (qge_vis_last_decision_valid &&
			qge_vis_get_audited_visible_mask(&qge_vis_last_decision,
											 &visible_mask,
											 &surface_count))
		{
			qge_vis_authority_model = model;
			qge_vis_authority_mask = visible_mask;
			qge_vis_authority_mask_count = surface_count;
		}
	}

	qge_vis_shadow_active = false;
	qge_vis_shadow_model = NULL;
	qge_vis_shadow_registered_surfaces = 0;
}

qboolean QGE_VisAuthorityGetMask(qmodel_t *model,
								 const unsigned char **visible_mask,
								 int *surface_count)
{
	if (visible_mask)
		*visible_mask = NULL;
	if (surface_count)
		*surface_count = 0;
	if (!qge_initialized || !model || model != qge_vis_authority_model ||
		!qge_vis_last_decision_valid ||
		!qge_vis_last_decision.writeback_allowed ||
		!qge_vis_authority_mask || qge_vis_authority_mask_count <= 0)
		return false;
	if (visible_mask)
		*visible_mask = qge_vis_authority_mask;
	if (surface_count)
		*surface_count = qge_vis_authority_mask_count;
	return true;
}

void QGE_VisAuthorityTraceApply(qmodel_t *model, int applied_surfaces)
{
	qge_quantum_runtime_t *rt;
	qge_state_probe_t probe;
	uint32_t flags = 0u;
	uint64_t hash;

	if (!qge_initialized || !model || !qge_vis_last_decision_valid)
		return;

	if (qge_vis_authority_mask_count > 0)
		flags |= QGE_VIS_TRACE_FLAG_REGISTERED;
	if (qge_vis_last_decision.authority_requested)
		flags |= QGE_VIS_TRACE_FLAG_AUTHORITY_REQUESTED;
	if (qge_vis_last_decision.authority_ready)
		flags |= QGE_VIS_TRACE_FLAG_AUTHORITY_READY;
	if (qge_vis_last_decision.writeback_allowed)
		flags |= QGE_VIS_TRACE_FLAG_AUTHORITY_SELECTED;
	if (qge_vis_last_decision.fallback_selected)
		flags |= QGE_VIS_TRACE_FLAG_FALLBACK_SELECTED;
	if (qge_vis_last_decision.false_negative_forced_classic)
		flags |= QGE_VIS_TRACE_FLAG_FALSE_NEGATIVE;
	if (qge_vis_last_decision.fallback_reason ==
		QGE_VIS_GATE_REASON_WARMUP_PENDING ||
		qge_vis_last_decision.fallback_reason ==
		QGE_VIS_GATE_REASON_SURFACE_COUNT_CHANGED)
		flags |= QGE_VIS_TRACE_FLAG_WARMUP_PENDING;
	if (QGE_VisControlledAuthoritySmoke())
		flags |= QGE_VIS_TRACE_FLAG_CONTROLLED_SMOKE;

	hash = QGE_RegistryHashStep(1469598103934665603ULL,
								(uint64_t)(uint32_t)model->numsurfaces);
	hash = QGE_RegistryHashStep(hash, (uint64_t)(uint32_t)applied_surfaces);
	hash = QGE_RegistryHashStep(hash, (uint64_t)qge_vis_last_decision.flags);
	hash = QGE_RegistryHashStep(hash,
								(uint64_t)qge_vis_last_decision.authority_reason);
	hash = QGE_RegistryHashStep(hash,
								(uint64_t)qge_vis_last_decision.fallback_reason);

	rt = QGE_Runtime();
	if (!rt)
		return;

	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_VISIBILITY;
	probe.representation = QGE_REP_CLASSICAL_ORACLE;
	probe.subject_id = applied_surfaces;
	probe.flags = flags;
	probe.state_hash = hash;
	probe.entropy = (double)qge_vis_last_decision.fallback_reason;
	probe.coherence = qge_vis_last_decision.writeback_allowed ? 1.0 : 0.0;
	probe.max_probability =
		qge_vis_last_decision.fallback_selected ? 1.0 : 0.0;
	probe.total_probability =
		(double)qge_vis_last_decision.last_false_negative_count;
	probe.active_basis_count =
		qge_vis_last_decision.consecutive_clean_frames;
	probe.qubit_count = qge_vis_last_decision.clean_frames_required;
	probe.memory_bytes = (uint64_t)qge_vis_authority_mask_count;
	strlcpy(probe.label, "vis_authority_apply", sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);
}

float QGE_VisQuerySurface(int surface_id)
{
	if (!qge_initialized || quantum_vis.value < 0.5f)
		return 1.0f;  /* Fully visible when disabled */

	return qge_vis_query_surface(surface_id);
}

void QGE_VisRegisterSurface(int surface_id,
                             float min_x, float min_y, float min_z,
                             float max_x, float max_y, float max_z)
{
	if (!qge_initialized) return;
	qge_vis_register_surface(surface_id, min_x, min_y, min_z, max_x, max_y, max_z);
}

void QGE_VisSetupViewpoint(float eye_x, float eye_y, float eye_z,
                            float fwd_x, float fwd_y, float fwd_z)
{
	if (!qge_initialized) return;

	qge_vec3_t eye = {eye_x, eye_y, eye_z};
	qge_vec3_t fwd = {fwd_x, fwd_y, fwd_z};
	qge_vis_setup_viewpoint(eye, fwd);
}

/* ============================================================================
 * Quantum Particles
 * ============================================================================ */

static qboolean QGE_PhysicsShouldTrack(edict_t *ent)
{
	int movetype;

	if (!qge_initialized || quantum_physics.value < 0.5f)
		return false;
	if (!ent || ent->free)
		return false;

	movetype = (int)ent->v.movetype;
	if (movetype == MOVETYPE_FLYMISSILE)
		return quantum_projectiles.value >= 0.5f;

	return movetype == MOVETYPE_TOSS ||
		   movetype == MOVETYPE_BOUNCE ||
		   movetype == MOVETYPE_GIB;
}

static qboolean QGE_PhysicsProjectileAuthorityRequested(void)
{
	if (quantum_physics.value < 0.5f || quantum_projectiles.value < 0.5f)
		return false;

	/* Compatibility: quantum_projectiles 2 requested authority before the
	 * explicit quantum_physics_authoritative cvar existed. */
	return quantum_physics_authoritative.value >= 0.5f ||
		   quantum_projectiles.value >= 1.5f;
}

static qge_phys_object_t *QGE_PhysicsFindObject(int entnum, qboolean allocate)
{
	qge_phys_object_t *oldest = NULL;
	int oldest_frame = 0x7fffffff;

	for (int i = 0; i < QGE_MAX_PHYS_OBJECTS; i++) {
		qge_phys_object_t *obj = &qge_phys_objects[i];
		if (obj->active && obj->entnum == entnum)
			return obj;
		if (!obj->active && allocate) {
			memset(obj, 0, sizeof(*obj));
			obj->active = true;
			obj->entnum = entnum;
			return obj;
		}
		if (allocate && obj->last_seen_frame < oldest_frame) {
			oldest = obj;
			oldest_frame = obj->last_seen_frame;
		}
	}

	if (allocate && oldest) {
		memset(oldest, 0, sizeof(*oldest));
		oldest->active = true;
		oldest->entnum = entnum;
		return oldest;
	}

	return NULL;
}

static void QGE_PhysicsRefreshStats(void)
{
	float sum_error = 0.0f;
	float projectile_sum_error = 0.0f;
	int error_count = 0;
	int projectile_error_count = 0;

	qge_phys_active_objects = 0;
	qge_phys_active_projectiles = 0;
	qge_phys_avg_shadow_error = 0.0f;
	qge_phys_max_shadow_error = 0.0f;
	qge_phys_projectile_shadow_samples = 0;
	qge_phys_projectile_avg_shadow_error = 0.0f;
	qge_phys_projectile_max_shadow_error = 0.0f;

	for (int i = 0; i < QGE_MAX_PHYS_OBJECTS; i++) {
		qge_phys_object_t *obj = &qge_phys_objects[i];
		if (!obj->active)
			continue;

		if (qge_frame_count - obj->last_seen_frame > 2) {
			obj->active = false;
			qge_phys_registry_purged++;
			continue;
		}

		qge_phys_active_objects++;
		if (obj->movetype == MOVETYPE_FLYMISSILE)
			qge_phys_active_projectiles++;

		if (obj->seen_count > 1) {
			sum_error += obj->shadow_error;
			error_count++;
			if (obj->shadow_error > qge_phys_max_shadow_error)
				qge_phys_max_shadow_error = obj->shadow_error;

			if (obj->movetype == MOVETYPE_FLYMISSILE) {
				projectile_sum_error += obj->shadow_error;
				projectile_error_count++;
				qge_phys_projectile_shadow_samples += obj->seen_count - 1;
				if (obj->max_shadow_error > qge_phys_projectile_max_shadow_error)
					qge_phys_projectile_max_shadow_error = obj->max_shadow_error;
			}
		}
	}

	if (error_count > 0)
		qge_phys_avg_shadow_error = sum_error / (float)error_count;
	if (projectile_error_count > 0)
		qge_phys_projectile_avg_shadow_error =
			projectile_sum_error / (float)projectile_error_count;
}

static void QGE_PhysicsUpdateProjectileAuthorityGate(void)
{
	qge_projectile_authority_telemetry_t telemetry;

	if (quantum_physics.value >= 0.5f && quantum_projectiles.value >= 0.5f &&
		(qge_phys_active_projectiles > 0 || qge_phys_projectile_count > 0)) {
		qge_phys_projectile_authority_warmup_frames++;
	} else {
		qge_phys_projectile_authority_warmup_frames = 0;
	}

	memset(&telemetry, 0, sizeof(telemetry));
	telemetry.requested =
		quantum_physics.value >= 0.5f && quantum_projectiles.value >= 0.5f;
	telemetry.active_projectiles = qge_phys_active_projectiles;
	telemetry.frame_projectiles = qge_phys_projectile_count;
	telemetry.warmup_frames = qge_phys_projectile_authority_warmup_frames;
	telemetry.shadow_samples = qge_phys_projectile_shadow_samples;
	telemetry.avg_shadow_error = qge_phys_projectile_avg_shadow_error;
	telemetry.max_shadow_error = qge_phys_projectile_max_shadow_error;

	qge_phys_projectile_authority_state =
		qge_projectile_authority_evaluate(NULL, &telemetry);
	qge_phys_projectile_authority_ready =
		qge_phys_projectile_authority_state.ready ? true : false;
	qge_phys_projectile_authority_off_reason =
		qge_phys_projectile_authority_state.off_reason;

	if (qge_phys_projectile_authority_ready)
		qge_phys_projectile_authority_ready_frames++;
	else if (telemetry.requested &&
			 (telemetry.active_projectiles > 0 ||
			  telemetry.frame_projectiles > 0))
		qge_phys_projectile_authority_off_frames++;
}

static uint32_t QGE_PhysicsProjectileAuthorityFlags(void)
{
	uint32_t flags = (uint32_t)qge_phys_projectile_authority_off_reason & 0xffu;

	if (qge_phys_projectile_authority_ready)
		flags |= 0x100u;
	if (quantum_physics.value >= 0.5f)
		flags |= 0x200u;
	if (quantum_projectiles.value >= 0.5f)
		flags |= 0x400u;
	if (qge_phys_projectile_shadow_samples >=
		QGE_PROJECTILE_AUTHORITY_DEFAULT_MIN_SHADOW_SAMPLES)
		flags |= 0x800u;
	if (quantum_physics_authoritative.value >= 0.5f)
		flags |= 0x10000u;
	return flags;
}

static uint32_t QGE_PhysicsProjectileWritebackFlags(
	const qge_projectile_writeback_decision_t *decision)
{
	uint32_t flags;

	if (!decision)
		return 0u;

	flags = (uint32_t)decision->off_reason & 0xffu;
	if (decision->authority_ready)
		flags |= 0x100u;
	if (quantum_physics.value >= 0.5f)
		flags |= 0x200u;
	if (quantum_projectiles.value >= 0.5f)
		flags |= 0x400u;
	if (decision->gate_state.shadow_samples_remaining <= 0)
		flags |= 0x800u;
	if (decision->authority_requested)
		flags |= 0x1000u;
	if (decision->writeback_allowed)
		flags |= 0x2000u;
	if (decision->fallback_selected)
		flags |= 0x4000u;
	if (decision->rollback_required)
		flags |= 0x8000u;
	if (quantum_physics_authoritative.value >= 0.5f)
		flags |= 0x10000u;
	return flags;
}

static uint32_t QGE_PhysicsProjectileBranchFlags(
	const qge_projectile_branch_state_t *state)
{
	uint32_t flags = 0u;

	if (!state)
		return flags;

	if (quantum_physics.value >= 0.5f)
		flags |= 0x200u;
	if (quantum_projectiles.value >= 0.5f)
		flags |= 0x400u;
	if (quantum_physics_authoritative.value >= 0.5f)
		flags |= 0x10000u;
	if (state->branch_count > 0)
		flags |= 0x20000u;
	if (state->observed)
		flags |= 0x40000u;
	if (state->impact_measured)
		flags |= 0x80000u;
	if (state->selected_branch_id == QGE_PROJECTILE_BRANCH_QGE_PREDICTION)
		flags |= 0x100000u;
	if (state->selected_branch_id == QGE_PROJECTILE_BRANCH_IMPACT_OBSERVATION)
		flags |= 0x200000u;
	if (state->decoherence > 0.25f)
		flags |= 0x400000u;
	return flags;
}

static void QGE_TraceProjectileSaveDemoBoundary(
	qge_quantum_runtime_t *rt,
	const qge_projectile_branch_state_t *state,
	const qge_projectile_writeback_decision_t *decision,
	const qge_projectile_collision_oracle_decision_t *oracle,
	uint64_t decision_hash,
	qboolean writeback_boundary)
{
	qge_measurement_event_t event;
	uint32_t flags = QGE_PROJECTILE_TRACE_FLAG_SAVE_DEMO_BOUNDARY;
	uint64_t trace_id = decision_hash;
	int entity_id = 0;

	if (!state && !decision && !oracle)
		return;
	if (!rt)
		return;

	if (state) {
		flags |= QGE_PhysicsProjectileBranchFlags(state);
		trace_id = state->state_hash;
		entity_id = state->entity_id;
	}
	if (decision) {
		flags |= QGE_PhysicsProjectileWritebackFlags(decision);
		entity_id = decision->entity_id;
		if (writeback_boundary)
			flags |= QGE_PROJECTILE_TRACE_FLAG_SAVE_DEMO_WRITEBACK;
	}
	if (oracle) {
		flags |= QGE_PROJECTILE_TRACE_FLAG_COLLISION_ORACLE |
				 QGE_PROJECTILE_TRACE_FLAG_SAVE_DEMO_ORACLE;
		entity_id = oracle->entity_id;
		if (oracle->source == QGE_PROJECTILE_COLLISION_TRACE_QGE)
			flags |= QGE_PROJECTILE_TRACE_FLAG_ORACLE_QGE_TRACE;
		else
			flags |= QGE_PROJECTILE_TRACE_FLAG_ORACLE_CLASSIC;
		if (oracle->selected_no_impact)
			flags |= QGE_PROJECTILE_TRACE_FLAG_ORACLE_NO_IMPACT;
		if (oracle->selected_alternate_impact)
			flags |= QGE_PROJECTILE_TRACE_FLAG_ORACLE_ALT_IMPACT;
		if (oracle->state_hash)
			trace_id = oracle->state_hash;
	}

	memset(&event, 0, sizeof(event));
	event.domain = QGE_DOMAIN_PROJECTILE;
	event.kind = oracle ? QGE_MEASURE_PROJECTILE_COLLISION_ORACLE :
		(writeback_boundary ? QGE_MEASURE_PROJECTILE_WRITEBACK :
		 QGE_MEASURE_PROJECTILE_BRANCH);
	event.boundary = QGE_OBSERVE_SAVE_OR_DEMO;
	event.frame = qge_frame_count;
	event.server_time_msec = QGE_ServerTimeMsec();
	event.subject_id = entity_id;
	event.flags = flags;
	if (state)
		event.basis_index = (uint64_t)state->selected_branch_id;
	else if (decision)
		event.basis_index = (uint64_t)decision->source;
	if (oracle)
		event.basis_index |= (uint64_t)oracle->source << 32;
	event.probability = oracle ? oracle->selected_probability :
		(state ? state->selected_probability :
		 (decision && decision->writeback_allowed ? 1.0 : 0.0));
	event.phase = state ? state->coherence :
		(decision && decision->authority_ready ? 1.0 : 0.0);
	event.entropy_offset = trace_id;
	event.trace_id = trace_id;
	qge_quantum_record_measurement(rt, &event);
}

static void QGE_TraceProjectileBranchState(
	qge_quantum_runtime_t *rt,
	const qge_projectile_branch_state_t *state)
{
	qge_state_probe_t probe;

	if (!rt || !state || state->branch_count <= 0)
		return;

	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_PROJECTILE;
	probe.representation = QGE_REP_CA_MPS;
	probe.subject_id = state->entity_id;
	probe.flags = QGE_PhysicsProjectileBranchFlags(state);
	probe.state_hash = state->state_hash;
	probe.entropy = state->decoherence;
	probe.coherence = state->coherence;
	probe.max_probability = state->selected_probability;
	probe.total_probability = state->total_weight;
	probe.active_basis_count = state->branch_count;
	probe.qubit_count =
		qge_quantum_qubits_for_basis_count((uint64_t)state->branch_count);
	probe.memory_bytes = sizeof(*state);
	strlcpy(probe.label, "projectile_branch_state", sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);
	QGE_TraceProjectileSaveDemoBoundary(rt, state, NULL, NULL, 0, false);
}

static void QGE_TraceProjectilePreimpactSelection(
	qge_quantum_runtime_t *rt,
	const qge_projectile_branch_state_t *state,
	const qge_projectile_writeback_decision_t *decision,
	const qge_projectile_collision_oracle_decision_t *oracle)
{
	qge_state_probe_t probe;
	uint32_t flags;

	if (!rt || !state || !decision || state->branch_count <= 0)
		return;

	flags = QGE_PhysicsProjectileBranchFlags(state);
	flags |= QGE_PhysicsProjectileWritebackFlags(decision) & ~0xffu;
	if (oracle) {
		flags |= QGE_PROJECTILE_TRACE_FLAG_COLLISION_ORACLE;
		if (oracle->source == QGE_PROJECTILE_COLLISION_TRACE_QGE)
			flags |= QGE_PROJECTILE_TRACE_FLAG_ORACLE_QGE_TRACE;
		else
			flags |= QGE_PROJECTILE_TRACE_FLAG_ORACLE_CLASSIC;
		if (oracle->selected_no_impact)
			flags |= QGE_PROJECTILE_TRACE_FLAG_ORACLE_NO_IMPACT;
		if (oracle->selected_alternate_impact)
			flags |= QGE_PROJECTILE_TRACE_FLAG_ORACLE_ALT_IMPACT;
		if (!oracle->authority_applied && oracle->off_reason !=
			QGE_PROJECTILE_AUTHORITY_OFF_NONE)
			flags = (flags & ~0xffu) | ((uint32_t)oracle->off_reason & 0xffu);
	}

	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_PROJECTILE;
	probe.representation = QGE_REP_CA_MPS;
	probe.subject_id = state->entity_id;
	probe.flags = flags;
	probe.state_hash = oracle && oracle->state_hash ?
		oracle->state_hash : state->state_hash;
	probe.entropy = state->decoherence;
	probe.coherence =
		(oracle && oracle->authority_applied) ? 1.0 : state->coherence;
	probe.max_probability = state->selected_probability;
	probe.total_probability = state->total_weight;
	probe.active_basis_count = state->branch_count;
	probe.qubit_count =
		qge_quantum_qubits_for_basis_count((uint64_t)state->branch_count);
	probe.memory_bytes = sizeof(*state) + sizeof(*decision);
	if (oracle)
		probe.memory_bytes += sizeof(*oracle);
	strlcpy(probe.label, "projectile_preimpact_selection",
			sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);
	QGE_TraceProjectileSaveDemoBoundary(rt, state, decision, oracle, 0, false);
}

static void QGE_TraceProjectileImpactMeasurement(
	qge_quantum_runtime_t *rt,
	const qge_projectile_branch_state_t *state)
{
	qge_measurement_event_t event;
	const qge_projectile_branch_t *branch = NULL;

	if (!rt || !state || !state->impact_measured ||
		state->selected_branch_index < 0 ||
		state->selected_branch_index >= state->branch_count)
		return;

	branch = &state->branches[state->selected_branch_index];
	memset(&event, 0, sizeof(event));
	event.domain = QGE_DOMAIN_PROJECTILE;
	event.kind = QGE_MEASURE_PROJECTILE_IMPACT;
	event.boundary = state->boundary;
	event.frame = qge_frame_count;
	event.server_time_msec = QGE_ServerTimeMsec();
	event.subject_id = state->entity_id;
	event.flags = QGE_PhysicsProjectileBranchFlags(state);
	event.basis_index = (uint64_t)state->selected_branch_id;
	event.probability = state->selected_probability;
	event.phase = branch->phase;
	event.entropy_offset = state->state_hash;
	event.trace_id = state->state_hash;
	qge_quantum_record_measurement(rt, &event);
}

static void QGE_TraceProjectileWritebackDecision(
	qge_quantum_runtime_t *rt,
	const qge_projectile_writeback_decision_t *decision)
{
	qge_state_probe_t probe;
	qge_fallback_event_t fallback;
	uint64_t hash;

	if (!rt || !decision)
		return;

	hash = QGE_RegistryHashStep((uint64_t)(uint32_t)decision->entity_id,
								(uint64_t)decision->source);
	hash = QGE_RegistryHashStep(hash, (uint64_t)decision->off_reason);
	hash = QGE_RegistryHashStep(hash,
								(uint64_t)decision->fallback_reason);
	hash = QGE_RegistryHashStep(hash,
								(uint64_t)decision->rollback_reason);
	hash = QGE_RegistryHashStep(hash,
								(uint64_t)(decision->origin_delta_length *
										   1000.0f));
	hash = QGE_RegistryHashStep(hash,
								(uint64_t)(decision->velocity_delta_length *
										   1000.0f));

	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_PROJECTILE;
	probe.representation = QGE_REP_CLASSICAL_ORACLE;
	probe.subject_id = decision->entity_id;
	probe.flags = QGE_PhysicsProjectileWritebackFlags(decision);
	probe.state_hash = hash;
	probe.entropy = decision->writeback_allowed ? 1.0 : 0.0;
	probe.coherence = decision->authority_ready ? 1.0 : 0.0;
	probe.max_probability = decision->origin_delta_length;
	probe.total_probability = decision->velocity_delta_length;
	probe.active_basis_count = decision->gate_state.shadow_samples_remaining;
	probe.qubit_count = decision->gate_state.warmup_frames_remaining;
	probe.memory_bytes = sizeof(*decision);
	strlcpy(probe.label, "projectile_writeback_decision",
			sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);
	QGE_TraceProjectileSaveDemoBoundary(rt, NULL, decision, NULL, hash, true);

	if (!decision->authority_requested || !decision->fallback_selected)
		return;

	memset(&fallback, 0, sizeof(fallback));
	fallback.frame = qge_frame_count;
	fallback.server_time_msec = QGE_ServerTimeMsec();
	fallback.domain = QGE_DOMAIN_PROJECTILE;
	fallback.representation = QGE_REP_CLASSICAL_ORACLE;
	fallback.subject_id = decision->entity_id;
	fallback.reason_code = (int32_t)decision->fallback_reason;
	fallback.metric_value = decision->rollback_required ?
		decision->origin_delta_length : decision->velocity_delta_length;
	q_snprintf(fallback.message, sizeof(fallback.message),
			   "projectile_writeback source=classic reason=%s rollback=%s ent=%d origin_delta=%.3f velocity_delta=%.3f",
			   qge_projectile_authority_off_reason_name(
				   decision->fallback_reason),
			   qge_projectile_authority_off_reason_name(
				   decision->rollback_reason),
			   decision->entity_id,
			   decision->origin_delta_length,
			   decision->velocity_delta_length);
	qge_quantum_record_fallback(rt, &fallback);
}

static void QGE_TraceProjectileAuthorityGate(qge_quantum_runtime_t *rt)
{
	qge_state_probe_t probe;
	qge_fallback_event_t fallback;
	uint64_t hash;
	float warmup_ratio;
	qge_projectile_authority_gate_t gate;

	if (!rt)
		return;

	gate = qge_projectile_authority_default_gate();
	warmup_ratio = gate.warmup_frames_required > 0 ?
		(float)qge_phys_projectile_authority_warmup_frames /
		(float)gate.warmup_frames_required : 1.0f;
	warmup_ratio = QGE_ClampUnit(warmup_ratio);

	hash = QGE_RegistryHashStep((uint64_t)qge_frame_count,
								(uint64_t)qge_phys_projectile_count);
	hash = QGE_RegistryHashStep(hash,
								(uint64_t)qge_phys_active_projectiles);
	hash = QGE_RegistryHashStep(hash,
								(uint64_t)qge_phys_projectile_shadow_samples);
	hash = QGE_RegistryHashStep(hash,
								(uint64_t)qge_phys_projectile_authority_off_reason);
	hash = QGE_RegistryHashStep(hash,
								(uint64_t)(qge_phys_projectile_max_shadow_error *
										   1000.0f));

	memset(&probe, 0, sizeof(probe));
	probe.frame = qge_frame_count;
	probe.server_time_msec = QGE_ServerTimeMsec();
	probe.domain = QGE_DOMAIN_PROJECTILE;
	probe.representation = QGE_REP_CLASSICAL_ORACLE;
	probe.subject_id = qge_phys_active_projectiles;
	probe.flags = QGE_PhysicsProjectileAuthorityFlags();
	probe.state_hash = hash;
	probe.entropy = qge_phys_projectile_authority_ready ? 1.0 : 0.0;
	probe.coherence = warmup_ratio;
	probe.max_probability = qge_phys_projectile_max_shadow_error;
	probe.total_probability = qge_phys_projectile_avg_shadow_error;
	probe.active_basis_count = qge_phys_projectile_shadow_samples;
	probe.qubit_count = qge_quantum_qubits_for_basis_count(
		(uint64_t)qge_phys_projectile_shadow_samples);
	probe.memory_bytes = (uint64_t)qge_phys_active_projectiles *
						 (uint64_t)sizeof(qge_phys_object_t);
	strlcpy(probe.label, "projectile_authority_gate", sizeof(probe.label));
	qge_quantum_record_probe(rt, &probe);

	if (qge_phys_projectile_authority_ready ||
		qge_phys_projectile_authority_off_reason ==
			QGE_PROJECTILE_AUTHORITY_OFF_NO_PROJECTILES)
		return;

	memset(&fallback, 0, sizeof(fallback));
	fallback.frame = qge_frame_count;
	fallback.server_time_msec = QGE_ServerTimeMsec();
	fallback.domain = QGE_DOMAIN_PROJECTILE;
	fallback.representation = QGE_REP_CLASSICAL_ORACLE;
	fallback.subject_id = qge_phys_active_projectiles;
	fallback.reason_code = (int32_t)qge_phys_projectile_authority_off_reason;
	fallback.metric_value = qge_phys_projectile_authority_off_reason ==
		QGE_PROJECTILE_AUTHORITY_OFF_SHADOW_MAX ?
		qge_phys_projectile_max_shadow_error :
		qge_phys_projectile_avg_shadow_error;
	strlcpy(fallback.message,
			qge_projectile_authority_off_reason_name(
				qge_phys_projectile_authority_off_reason),
			sizeof(fallback.message));
	qge_quantum_record_fallback(rt, &fallback);
}

static qge_vec3_t QGE_VecFromQuake(const vec3_t v)
{
	qge_vec3_t out = {v[0], v[1], v[2]};
	return out;
}

static qboolean QGE_PhysicsTraceHasImpact(const trace_t *trace)
{
	if (!trace)
		return false;
	return trace->allsolid || trace->startsolid || trace->fraction < 1.0f ||
		   trace->ent != NULL;
}

static void QGE_PhysicsFillCollisionOracleRequest(
	qge_projectile_collision_oracle_request_t *request,
	const qge_projectile_branch_request_t *branch_request,
	const trace_t *classic_trace,
	qge_vec3_t qge_velocity,
	const trace_t *qge_trace)
{
	qboolean classic_has_impact;
	qboolean qge_has_impact;

	if (!request || !branch_request || !classic_trace || !qge_trace)
		return;

	memset(request, 0, sizeof(*request));
	request->entity_id = branch_request->entity_id;
	request->telemetry = branch_request->telemetry;
	request->classic_origin = QGE_VecFromQuake(classic_trace->endpos);
	request->classic_velocity = branch_request->classic_velocity;
	request->qge_origin = QGE_VecFromQuake(qge_trace->endpos);
	request->qge_velocity = qge_velocity;
	request->qge_trace_valid = !qge_trace->allsolid && !qge_trace->startsolid;

	classic_has_impact = QGE_PhysicsTraceHasImpact(classic_trace);
	qge_has_impact = QGE_PhysicsTraceHasImpact(qge_trace);
	request->classic_has_impact = classic_has_impact ? true : false;
	request->qge_has_impact = qge_has_impact ? true : false;

	if (classic_has_impact) {
		request->classic_impact_entity_id =
			classic_trace->ent ? NUM_FOR_EDICT(classic_trace->ent) : 0;
		request->classic_impact_fraction = classic_trace->fraction;
		request->classic_impact_origin =
			QGE_VecFromQuake(classic_trace->endpos);
		request->classic_impact_normal =
			QGE_VecFromQuake(classic_trace->plane.normal);
	}
	if (qge_has_impact) {
		request->qge_impact_entity_id =
			qge_trace->ent ? NUM_FOR_EDICT(qge_trace->ent) : 0;
		request->qge_impact_fraction = qge_trace->fraction;
		request->qge_impact_origin = QGE_VecFromQuake(qge_trace->endpos);
		request->qge_impact_normal =
			QGE_VecFromQuake(qge_trace->plane.normal);
	}
}

static int QGE_PhysicsEdictNumFromProg(int prog)
{
	int entnum;
	edict_t *ed;

	if (!prog || !sv.edicts || pr_edict_size <= 0)
		return 0;
	if (prog < 0 || (prog % pr_edict_size) != 0)
		return 0;

	entnum = prog / pr_edict_size;
	if (entnum < 0 || entnum >= sv.num_edicts)
		return 0;

	ed = EDICT_NUM(entnum);
	if (!ed || ed->free)
		return 0;
	return entnum;
}

static void QGE_PhysicsMirrorEdictState(qge_phys_object_t *obj,
										edict_t *ent)
{
	if (!obj || !ent)
		return;

	obj->movetype = (int)ent->v.movetype;
	obj->solid = (int)ent->v.solid;
	obj->flags = (int)ent->v.flags;
	obj->owner_entnum = QGE_PhysicsEdictNumFromProg(ent->v.owner);
	obj->groundentity_entnum = QGE_PhysicsEdictNumFromProg(ent->v.groundentity);
	obj->waterlevel = (int)ent->v.waterlevel;
	obj->watertype = (int)ent->v.watertype;
	VectorCopy(ent->v.origin, obj->origin);
	VectorCopy(ent->v.velocity, obj->velocity);
	VectorCopy(ent->v.mins, obj->mins);
	VectorCopy(ent->v.maxs, obj->maxs);
	VectorCopy(ent->v.absmin, obj->absmin);
	VectorCopy(ent->v.absmax, obj->absmax);

	qge_phys_mirrored_bounds++;
	if (obj->owner_entnum)
		qge_phys_mirrored_owner++;
	if (obj->waterlevel > 0 || obj->watertype <= CONTENTS_WATER)
		qge_phys_mirrored_water++;
}

static qboolean QGE_PhysicsBuildProjectileBranchRequest(
	qge_phys_object_t *obj,
	edict_t *ent,
	qge_observation_boundary_t boundary,
	const trace_t *trace,
	qge_projectile_branch_request_t *request)
{
	if (!request || !ent || (int)ent->v.movetype != MOVETYPE_FLYMISSILE)
		return false;

	memset(request, 0, sizeof(*request));
	request->entity_id = NUM_FOR_EDICT(ent);
	request->telemetry.requested =
		QGE_PhysicsProjectileAuthorityRequested();
	request->telemetry.active_projectiles =
		qge_phys_active_projectiles > 0 ? qge_phys_active_projectiles : 1;
	request->telemetry.frame_projectiles = qge_phys_projectile_count + 1;
	request->telemetry.warmup_frames =
		qge_phys_projectile_authority_warmup_frames;
	request->telemetry.shadow_samples =
		(obj && obj->seen_count > 1) ? obj->seen_count - 1 : 0;
	request->telemetry.avg_shadow_error = obj ? obj->shadow_error : 0.0f;
	request->telemetry.max_shadow_error = obj ? obj->max_shadow_error : 0.0f;
	request->classic_origin = QGE_VecFromQuake(ent->v.origin);
	request->classic_velocity = QGE_VecFromQuake(ent->v.velocity);
	if (obj && obj->seen_count > 0) {
		request->qge_origin = QGE_VecFromQuake(obj->predicted_origin);
		request->qge_velocity = QGE_VecFromQuake(obj->velocity);
	} else {
		request->qge_origin = request->classic_origin;
		request->qge_velocity = request->classic_velocity;
	}
	request->boundary = boundary;
	if (trace) {
		request->has_impact = true;
		request->impact_origin = QGE_VecFromQuake(trace->endpos);
		request->impact_normal = QGE_VecFromQuake(trace->plane.normal);
		request->impact_entity_id =
			trace->ent ? NUM_FOR_EDICT(trace->ent) : 0;
		request->impact_fraction = trace->fraction;
	}
	return true;
}

static qboolean QGE_PhysicsBuildProjectileWritebackRequest(
	qge_phys_object_t *obj,
	edict_t *ent,
	qge_projectile_writeback_request_t *request)
{
	qge_projectile_branch_request_t branch_request;
	qge_projectile_branch_state_t branch_state;

	if (!request || !ent || (int)ent->v.movetype != MOVETYPE_FLYMISSILE)
		return false;
	if (!QGE_PhysicsBuildProjectileBranchRequest(
			obj, ent, QGE_OBSERVE_FRAME_BOUNDARY, NULL, &branch_request))
		return false;

	branch_state =
		qge_projectile_branch_state_evaluate(NULL, &branch_request);
	if (obj) {
		obj->branch_state = branch_state;
		obj->branch_state_valid = true;
	}
	qge_phys_projectile_branch_states++;
	QGE_TraceProjectileBranchState(QGE_Runtime(), &branch_state);

	memset(request, 0, sizeof(*request));
	request->entity_id = branch_request.entity_id;
	request->telemetry = branch_request.telemetry;
	request->classic_origin = branch_request.classic_origin;
	request->classic_velocity = branch_request.classic_velocity;
	request->qge_origin = branch_state.selected_origin;
	request->qge_velocity = branch_state.selected_velocity;
	return true;
}

qboolean QGE_PhysicsSelectProjectileBranch(edict_t *ent,
										   const vec3_t push,
										   trace_t *trace)
{
	qge_phys_object_t *obj;
	qge_projectile_branch_request_t branch_request;
	qge_projectile_branch_request_t selected_branch_request;
	qge_projectile_branch_state_t branch_state;
	qge_projectile_branch_state_t selected_branch_state;
	qge_projectile_writeback_request_t writeback_request;
	qge_projectile_writeback_decision_t decision;
	qge_projectile_collision_oracle_request_t oracle_request;
	qge_projectile_collision_oracle_decision_t oracle_decision;
	trace_t classic_trace;
	trace_t qge_trace;
	trace_t *selected_trace;
	vec3_t qge_end;
	qboolean collision_observed;
	qboolean qge_trace_ready = false;
	qboolean selected_collision;
	qboolean adjusted = false;

	(void)push;

	if (!trace || !QGE_PhysicsShouldTrack(ent) ||
		(int)ent->v.movetype != MOVETYPE_FLYMISSILE)
		return false;

	obj = QGE_PhysicsFindObject(NUM_FOR_EDICT(ent), true);
	classic_trace = *trace;
	collision_observed = QGE_PhysicsTraceHasImpact(&classic_trace);
	if (!QGE_PhysicsBuildProjectileBranchRequest(
			obj,
			ent,
			QGE_OBSERVE_FRAME_BOUNDARY,
			NULL,
			&branch_request))
		return false;

	branch_state =
		qge_projectile_branch_state_evaluate(NULL, &branch_request);
	memset(&writeback_request, 0, sizeof(writeback_request));
	writeback_request.entity_id = branch_request.entity_id;
	writeback_request.telemetry = branch_request.telemetry;
	writeback_request.classic_origin = branch_request.classic_origin;
	writeback_request.classic_velocity = branch_request.classic_velocity;
	writeback_request.qge_origin = branch_state.selected_origin;
	writeback_request.qge_velocity = branch_state.selected_velocity;
	decision = qge_projectile_writeback_evaluate(NULL, &writeback_request);

	qge_trace = classic_trace;
	if (decision.writeback_allowed &&
		branch_state.selected_branch_id ==
			QGE_PROJECTILE_BRANCH_QGE_PREDICTION) {
		qge_end[0] = branch_state.selected_origin.x;
		qge_end[1] = branch_state.selected_origin.y;
		qge_end[2] = branch_state.selected_origin.z;
		qge_trace = SV_Move(ent->v.origin,
							ent->v.mins,
							ent->v.maxs,
							qge_end,
							MOVE_MISSILE,
							ent);
		qge_trace_ready = true;
		qge_phys_projectile_preimpact_oracle_traces++;
	}

	QGE_PhysicsFillCollisionOracleRequest(&oracle_request,
										  &branch_request,
										  &classic_trace,
										  branch_state.selected_velocity,
										  &qge_trace);
	oracle_decision =
		qge_projectile_collision_oracle_evaluate(NULL, &oracle_request);
	selected_trace =
		(oracle_decision.source == QGE_PROJECTILE_COLLISION_TRACE_QGE &&
		 qge_trace_ready) ? &qge_trace : &classic_trace;
	selected_collision = QGE_PhysicsTraceHasImpact(selected_trace);
	if (!QGE_PhysicsBuildProjectileBranchRequest(
			obj,
			ent,
			selected_collision ? QGE_OBSERVE_COLLISION :
								 QGE_OBSERVE_FRAME_BOUNDARY,
			selected_collision ? selected_trace : NULL,
			&selected_branch_request))
		return false;
	selected_branch_state =
		qge_projectile_branch_state_evaluate(NULL, &selected_branch_request);

	if (obj) {
		obj->branch_state = selected_branch_state;
		obj->branch_state_valid = true;
		obj->preimpact_selection_frame = qge_frame_count;
	}

	qge_phys_projectile_preimpact_decisions++;
	if (collision_observed)
		qge_phys_projectile_preimpact_collisions++;
	if (oracle_decision.selected_no_impact)
		qge_phys_projectile_preimpact_noimpact++;
	if (oracle_decision.selected_alternate_impact)
		qge_phys_projectile_preimpact_alternate_impacts++;

	if (oracle_decision.authority_applied && qge_trace_ready) {
		*trace = qge_trace;
		ent->v.velocity[0] = oracle_decision.selected_velocity.x;
		ent->v.velocity[1] = oracle_decision.selected_velocity.y;
		ent->v.velocity[2] = oracle_decision.selected_velocity.z;
		qge_phys_projectile_preimpact_selected++;
		adjusted = true;
	}

	QGE_TraceProjectilePreimpactSelection(QGE_Runtime(),
										  &selected_branch_state,
										  &decision,
										  &oracle_decision);
	return adjusted;
}

void QGE_PhysicsTrackToss(edict_t *ent, float dt)
{
	int movetype;
	int entnum;
	qge_phys_object_t *obj;
	qge_projectile_writeback_request_t writeback_request;
	qge_projectile_writeback_decision_t writeback_decision;

	if (!QGE_PhysicsShouldTrack(ent))
		return;

	movetype = (int)ent->v.movetype;
	entnum = NUM_FOR_EDICT(ent);
	obj = QGE_PhysicsFindObject(entnum, true);

	if (obj) {
		if (obj->seen_count > 0) {
			vec3_t delta;
			VectorSubtract(ent->v.origin, obj->predicted_origin, delta);
			obj->shadow_error = VectorLength(delta);
			if (obj->shadow_error > obj->max_shadow_error)
				obj->max_shadow_error = obj->shadow_error;
		}

		if (movetype == MOVETYPE_FLYMISSILE &&
			QGE_PhysicsBuildProjectileWritebackRequest(obj, ent,
													   &writeback_request)) {
			writeback_decision =
				qge_projectile_writeback_evaluate(NULL, &writeback_request);
			qge_phys_projectile_writeback_decisions++;
			if (writeback_decision.writeback_allowed) {
				ent->v.origin[0] = writeback_request.qge_origin.x;
				ent->v.origin[1] = writeback_request.qge_origin.y;
				ent->v.origin[2] = writeback_request.qge_origin.z;
				ent->v.velocity[0] = writeback_request.qge_velocity.x;
				ent->v.velocity[1] = writeback_request.qge_velocity.y;
				ent->v.velocity[2] = writeback_request.qge_velocity.z;
				qge_phys_projectile_writeback_selected++;
			} else if (writeback_decision.authority_requested) {
				qge_phys_projectile_writeback_fallback++;
				if (writeback_decision.rollback_required)
					qge_phys_projectile_writeback_rollback++;
			}
			QGE_TraceProjectileWritebackDecision(QGE_Runtime(),
												 &writeback_decision);
		}

		obj->last_seen_frame = qge_frame_count;
		obj->seen_count++;
		QGE_PhysicsMirrorEdictState(obj, ent);
		VectorMA(ent->v.origin, dt, ent->v.velocity, obj->predicted_origin);
	}

	qge_phys_toss_count++;

	if (movetype == MOVETYPE_FLYMISSILE) {
		qge_phys_projectile_count++;

		if (qge_particles && quantum_particles.value >= 0.5f &&
			(qge_frame_count & 1) == 0) {
			qge_vec3_t pos = QGE_VecFromQuake(ent->v.origin);
			qge_vec3_t vel = {
				-ent->v.velocity[0] * 0.02f,
				-ent->v.velocity[1] * 0.02f,
				-ent->v.velocity[2] * 0.02f
			};
			qge_particle_spawn(qge_particles, pos, vel, dt * 8.0f + 0.15f);
			qge_phys_particle_spawns++;
		}
	}
}

void QGE_PhysicsTrackImpact(edict_t *ent, const trace_t *trace)
{
	qge_phys_object_t *obj;
	qge_projectile_branch_request_t branch_request;
	qge_projectile_branch_state_t branch_state;

	if (!trace || !QGE_PhysicsShouldTrack(ent))
		return;

	qge_phys_impact_count++;
	obj = QGE_PhysicsFindObject(NUM_FOR_EDICT(ent), true);
	if (obj) {
		obj->impacts++;
		obj->last_seen_frame = qge_frame_count;
		obj->last_impact_frame = qge_frame_count;
		obj->last_impact_entnum = trace->ent ? NUM_FOR_EDICT(trace->ent) : 0;
		obj->last_impact_fraction = trace->fraction;
		obj->last_impact_inopen = trace->inopen;
		obj->last_impact_inwater = trace->inwater;
		QGE_PhysicsMirrorEdictState(obj, ent);
		VectorCopy(trace->endpos, obj->origin);
		VectorCopy(trace->endpos, obj->last_impact_origin);
		VectorCopy(trace->plane.normal, obj->last_impact_normal);
		qge_phys_mirrored_impacts++;
	}

	if ((int)ent->v.movetype == MOVETYPE_FLYMISSILE &&
		QGE_PhysicsBuildProjectileBranchRequest(
			obj, ent, QGE_OBSERVE_COLLISION, trace, &branch_request)) {
		branch_state =
			qge_projectile_branch_state_evaluate(NULL, &branch_request);
		if (obj) {
			obj->branch_state = branch_state;
			obj->branch_state_valid = true;
		}
		qge_phys_projectile_branch_states++;
		QGE_TraceProjectileBranchState(QGE_Runtime(), &branch_state);
		if (branch_state.impact_measured) {
			qge_phys_projectile_impact_measurements++;
			QGE_TraceProjectileImpactMeasurement(QGE_Runtime(),
												 &branch_state);
		}
	}

	if (qge_particles && quantum_particles.value >= 0.5f) {
		qge_vec3_t pos = QGE_VecFromQuake(trace->endpos);
		qge_vec3_t vel = {
			trace->plane.normal[0] * 20.0f,
			trace->plane.normal[1] * 20.0f,
			trace->plane.normal[2] * 20.0f
		};
		qge_particle_spawn(qge_particles, pos, vel, 0.35f);
		qge_particle_system_impulse(qge_particles, pos, 30.0f);
		qge_phys_particle_spawns++;
	}
}

void QGE_DrawParticles(void)
{
	if (!qge_initialized || !qge_particles || quantum_particles.value < 0.5f)
		return;

	/* Evolve quantum particle system */
	float dt = (float)host_frametime;
	qge_particle_evolve(qge_particles, dt);

	/* Get particle positions via quantum measurement */
	qge_vec3_t positions[256];
	int count = qge_particle_get_positions(qge_particles, positions, 256);

	if (count == 0) return;

	/* Render particles as GL points */
	glPushAttrib(GL_ALL_ATTRIB_BITS);
	glDisable(GL_TEXTURE_2D);
	glEnable(GL_BLEND);
	glBlendFunc(GL_SRC_ALPHA, GL_ONE);
	glDepthMask(GL_FALSE);

	glPointSize(3.0f);
	glBegin(GL_POINTS);

	for (int i = 0; i < count; i++) {
		/* Quantum particles get a ghostly blue-white color */
		float alpha = 0.5f + 0.5f * ((float)(i % 4) / 4.0f);
		glColor4f(0.7f, 0.8f, 1.0f, alpha);
		glVertex3f(positions[i].x, positions[i].y, positions[i].z);
	}

	glEnd();
	glPopAttrib();
}

/* ============================================================================
 * Quantum AI
 * ============================================================================ */

int QGE_AIDecide(int enemy_id, float aggression, float distance, int visible)
{
	if (!qge_initialized || quantum_ai.value < 0.5f)
		return 0;  /* IDLE when disabled */

	ai_action_t action = qge_ai_decide(enemy_id, aggression, distance,
										visible ? true : false);
	qge_quantum_runtime_t *rt = QGE_Runtime();
	if (rt) {
		qge_measurement_event_t event;
		qge_state_probe_t probe;

		memset(&event, 0, sizeof(event));
		event.domain = QGE_DOMAIN_AI;
		event.kind = QGE_MEASURE_AI_ACTION;
		event.boundary = QGE_OBSERVE_AI_DECISION;
		event.frame = qge_frame_count;
		event.server_time_msec = QGE_ServerTimeMsec();
		event.subject_id = enemy_id;
		event.basis_index = (uint64_t)action;
		event.probability = 1.0;
		qge_quantum_record_measurement(rt, &event);

		memset(&probe, 0, sizeof(probe));
		probe.frame = qge_frame_count;
		probe.server_time_msec = QGE_ServerTimeMsec();
		probe.domain = QGE_DOMAIN_AI;
		probe.representation = QGE_REP_DENSE_STATE;
		probe.subject_id = enemy_id;
		probe.active_basis_count = 7;
		probe.qubit_count = qge_quantum_qubits_for_basis_count(7);
		probe.max_probability = 1.0;
		strlcpy(probe.label, "ai_action", sizeof(probe.label));
		qge_quantum_record_probe(rt, &probe);
	}
	return (int)action;
}
