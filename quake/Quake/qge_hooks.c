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

/* GL headers come via quakedef.h → SDL_opengl.h */

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
cvar_t quantum_debug     = {"quantum_debug",     "0", CVAR_NONE};
cvar_t quantum_overlay_alpha = {"quantum_overlay_alpha", "0.10", CVAR_ARCHIVE};
cvar_t quantum_scene_surface_budget = {"quantum_scene_surface_budget", "1024", CVAR_ARCHIVE};
cvar_t quantum_render_res = {"quantum_render_res", "1024", CVAR_ARCHIVE};
cvar_t quantum_render_threshold = {"quantum_render_threshold", "0.001", CVAR_ARCHIVE};
cvar_t quantum_render_edge_gain = {"quantum_render_edge_gain", "0.06", CVAR_ARCHIVE};
cvar_t quantum_render_material_gain = {"quantum_render_material_gain", "0.18", CVAR_ARCHIVE};

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
static GLenum qge_last_gl_upload_error = GL_NO_ERROR;
static GLenum qge_last_gl_draw_error = GL_NO_ERROR;
static float qge_last_tone_floor = 0.0f;
static float qge_last_tone_white = 1.0f;
static int qge_last_tone_clipped = 0;
static int qge_render_classic_3d_passes = 0;
static int qge_render_suppressed_3d_passes = 0;
static int qge_render_qge_primary_owned = 0;

static qboolean qge_initialized = false;

static const char *QGE_CommandLineTracePath(void)
{
	int arg;

	arg = COM_CheckParm("-qgetrace");
	if (arg && arg < com_argc - 1 && com_argv[arg + 1] &&
		com_argv[arg + 1][0])
		return com_argv[arg + 1];
	return NULL;
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
	int last_seen_frame;
	int seen_count;
	int impacts;
	vec3_t origin;
	vec3_t velocity;
	vec3_t predicted_origin;
	float shadow_error;
	float max_shadow_error;
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
static int qge_scene_snapshot_edicts = 0;
static int qge_scene_encoded_edicts = 0;
static int qge_scene_alias_encoded = 0;
static int qge_scene_sprite_encoded = 0;
static int qge_scene_viewmodel_encoded = 0;
static int qge_scene_entity_misses = 0;

static qge_phys_object_t qge_phys_objects[QGE_MAX_PHYS_OBJECTS];
static int qge_phys_active_objects = 0;
static int qge_phys_active_projectiles = 0;
static int qge_phys_registry_purged = 0;
static float qge_phys_avg_shadow_error = 0.0f;
static float qge_phys_max_shadow_error = 0.0f;

static void QGE_PhysicsRefreshStats(void);
static unsigned int QGE_SurfaceLightSignal(const msurface_t *surf,
										   float *energy,
										   float *contrast);

static int qge_dwt_levels = 4;       /* Configured DWT reconstruction levels */

static qmodel_t *qge_registered_worldmodel = NULL;
static char qge_registered_world_name[MAX_QPATH];
static qge_world_stats_t qge_registry_stats;
static qge_resource_id_t qge_precache_model_resource_ids[MAX_MODELS];
static qge_resource_id_t qge_precache_sound_resource_ids[MAX_SOUNDS];

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

static unsigned int QGE_TextureSignalBuild(const texture_t *tex,
										   qge_texture_signal_cache_t *out);

#define QGE_MAX_LIGHTMAP_SIGNAL_CACHE MAX_MAP_FACES
#define QGE_MAX_PROJECTED_POLY_VERTS 64
typedef struct {
	qboolean valid;
	unsigned int light_hash;
	float light_energy;
	float light_contrast;
} qge_lightmap_signal_cache_t;

static qge_lightmap_signal_cache_t qge_lightmap_signal_cache[QGE_MAX_LIGHTMAP_SIGNAL_CACHE];
static int qge_lightmap_signal_cache_entries = 0;

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

static int QGE_ServerTimeMsec(void)
{
	return (int)(sv.time * 1000.0);
}

static qge_quantum_runtime_t *QGE_Runtime(void)
{
	return qge_get_quantum_runtime(qge_ctx);
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
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.vertex_count);
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.triangle_count);
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
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.width);
	ref.source_hash = QGE_RegistryHashStep(ref.source_hash, ref.height);
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

	if (!model || !model->textures)
		return;

	for (int i = 0; i < model->numtextures && i < QGE_MAX_TEXTURE_SIGNAL_CACHE; i++) {
		if (!model->textures[i])
			continue;
		QGE_TextureSignalBuild(model->textures[i], &qge_texture_signal_cache[i]);
		if (qge_texture_signal_cache[i].valid)
			qge_texture_signal_cache_entries++;
	}
}

static void QGE_ClearLightmapSignalCache(void)
{
	memset(qge_lightmap_signal_cache, 0, sizeof(qge_lightmap_signal_cache));
	qge_lightmap_signal_cache_entries = 0;
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
	if (!signal->valid)
		qge_lightmap_signal_cache_entries++;
	signal->valid = true;
	signal->light_hash = light_hash;
	signal->light_energy = light_energy;
	signal->light_contrast = light_contrast;
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

	if (!qge_initialized || !qge_ctx)
		return;
	world = qge_get_world(qge_ctx);
	if (world)
		QGE_RegisterHudImageIndex(world, index);
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

	QGE_RegisterPrecacheAssets(world, model_id);
	QGE_RegisterPendingHudImages(world);

	qge_world_get_stats(world, &qge_registry_stats);
	qge_registered_worldmodel = model;
	strlcpy(qge_registered_world_name, model->name, sizeof(qge_registered_world_name));
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
	qge_frame_snapshot_add_edict(snapshot, &item);
}

static void QGE_FrameSnapshotCaptureEdicts(qge_frame_snapshot_t *snapshot)
{
	if (!snapshot || snapshot->edict_count > 0 || cls.signon != SIGNONS)
		return;
	for (int i = 0; i < cl_numvisedicts; i++)
		QGE_FrameSnapshotAddEntity(snapshot, cl_visedicts[i]);
	QGE_FrameSnapshotAddEntity(snapshot, &cl.viewent);
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
	QGE_FrameSnapshotCaptureQuantumParticles(snapshot);
	qge_frame_snapshot_seal(snapshot);

	memset(&stats, 0, sizeof(stats));
	qge_frame_snapshot_get_stats(snapshot, &stats);
	QGE_TraceFrameSnapshotProbe(snapshot, &stats);

	if (quantum_debug.value >= 1.0f) {
		if (qge_frame_count < 5 || (qge_frame_count % 60) == 0) {
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
	Cvar_RegisterVariable(&quantum_debug);
	Cvar_RegisterVariable(&quantum_overlay_alpha);
	Cvar_RegisterVariable(&quantum_scene_surface_budget);
	Cvar_RegisterVariable(&quantum_render_res);
	Cvar_RegisterVariable(&quantum_render_threshold);
	Cvar_RegisterVariable(&quantum_render_edge_gain);
	Cvar_RegisterVariable(&quantum_render_material_gain);

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

	/* Phase 4.2: Enable adaptive quality for real-time performance */
	qge_set_adaptive_quality(qge_ctx, true);

	qge_initialized = true;

	fprintf(stderr, "QGE: Init complete!\n");

	Con_Printf("QGE: Engine ready — all quantum subsystems online\n");
	Con_Printf("  quantum_rng %d | quantum_ai %d | quantum_render %d\n",
			   (int)quantum_rng.value, (int)quantum_ai.value,
			   (int)quantum_render.value);
	Con_Printf("  quantum_physics %d | quantum_projectiles %d | quantum_particles %d\n",
			   (int)quantum_physics.value, (int)quantum_projectiles.value,
			   (int)quantum_particles.value);
	Con_Printf("  RGB sparse DWT | Stable DWT quality | Sparse-only GPU path\n");
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

	if (qge_texture) {
		glDeleteTextures(1, &qge_texture);
		qge_texture = 0;
	}

	if (qge_particles) {
		qge_particle_system_free(qge_particles);
		qge_particles = NULL;
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
	QGE_FrameSnapshotBeginCurrent();
	QGE_SceneBegin();
	qge_phys_toss_count = 0;
	qge_phys_projectile_count = 0;
	qge_phys_impact_count = 0;
	qge_phys_particle_spawns = 0;
	qge_phys_registry_purged = 0;
}

void QGE_FrameEnd(void)
{
	if (!qge_initialized) return;

	double elapsed = (Sys_DoubleTime() - qge_frame_start) * 1000.0;
	qge_avg_frame_ms = qge_avg_frame_ms * 0.95 + elapsed * 0.05;
	QGE_RegisterWorldIfNeeded();
	QGE_PhysicsRefreshStats();
	QGE_FrameSnapshotFinalize();
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
	}

	if (quantum_debug.value >= 1.0f &&
		(qge_phys_toss_count || qge_phys_projectile_count || qge_phys_impact_count)) {
		int active_particles = qge_particles ? qge_particle_system_active_count(qge_particles) : 0;
		fprintf(stderr, "QGE physics frame=%d toss=%d projectiles=%d impacts=%d "
				"tracked=%d active_projectiles=%d purged=%d shadow_avg=%.2f shadow_max=%.2f "
				"qparticle_spawns=%d active_qparticles=%d frame_ms=%.2f\n",
				qge_frame_count, qge_phys_toss_count, qge_phys_projectile_count,
				qge_phys_impact_count, qge_phys_active_objects,
				qge_phys_active_projectiles, qge_phys_registry_purged,
				qge_phys_avg_shadow_error, qge_phys_max_shadow_error,
				qge_phys_particle_spawns,
				active_particles, elapsed);
	}

	if (quantum_debug.value >= 1.0f && qge_scene_surface_count) {
		fprintf(stderr, "QGE scene frame=%d world_surfaces=%d submitted=%d dropped=%d "
				"snapshot=%d snapshot_miss=%d encoded=%d material_encoded=%d "
				"tex=%d texcache=%d/%d entries=%d light=%d lightcache=%d/%d "
				"light_entries=%d poly=%d fallback=%d sky=%d water=%d\n",
				qge_frame_count, qge_scene_world_surfaces, qge_scene_surface_count,
				qge_scene_surface_dropped, qge_scene_snapshot_surfaces,
				qge_scene_snapshot_misses, qge_scene_encoded_surfaces,
				qge_scene_material_encoded, qge_scene_textured_surfaces,
				qge_scene_texture_cache_hits, qge_scene_texture_cache_misses,
				qge_texture_signal_cache_entries, qge_scene_lightmapped_surfaces,
				qge_scene_lightmap_cache_hits, qge_scene_lightmap_cache_misses,
				qge_lightmap_signal_cache_entries, qge_scene_polygon_encoded,
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
	qge_scene_snapshot_edicts = 0;
	qge_scene_encoded_edicts = 0;
	qge_scene_alias_encoded = 0;
	qge_scene_sprite_encoded = 0;
	qge_scene_viewmodel_encoded = 0;
	qge_scene_entity_misses = 0;
}

static float QGE_SurfaceBrightness(const msurface_t *surf)
{
	if (!surf)
		return 0.25f;
	if (surf->flags & SURF_DRAWSKY)
		return 0.08f;
	if (surf->flags & SURF_DRAWLAVA)
		return 0.85f;
	if (surf->flags & SURF_DRAWTELE)
		return 0.75f;
	if (surf->flags & (SURF_DRAWWATER | SURF_DRAWTURB | SURF_DRAWSLIME))
		return 0.32f;
	if (surf->samples)
		return 0.58f;
	return 0.42f;
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
	dst->brightness = QGE_SurfaceBrightness(surf);
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

static qboolean QGE_ProjectSurfacePolygon(const qge_scene_surface_t *surface,
										  const msurface_t *surf,
										  qge_projected_vertex_t *verts,
										  int max_verts,
										  int *num_verts,
										  screen_rect_t *bounds,
										  float *depth,
										  float *area)
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
	int clipped_count;

	if (!surface || !poly || !verts || !num_verts || !bounds || !depth || !area)
		return false;

	clipped_count = QGE_ClipSurfacePolygonNear(poly, clipped,
											   QGE_MAX_PROJECTED_POLY_VERTS);

	for (int i = 0; i < clipped_count && count < max_verts; i++) {
		float sx, sy, sd;
		if (!QGE_ProjectPoint(clipped[i].world, &sx, &sy, &sd))
			continue;

		if (sx < 0.0f) sx = 0.0f;
		if (sy < 0.0f) sy = 0.0f;
		if (sx > qge_render_res - 1) sx = (float)(qge_render_res - 1);
		if (sy > qge_render_res - 1) sy = (float)(qge_render_res - 1);

		verts[count].x = sx;
		verts[count].y = sy;
		verts[count].depth = sd;
		verts[count].tex_s = clipped[i].tex_s;
		verts[count].tex_t = clipped[i].tex_t;
		verts[count].light_s = clipped[i].light_s;
		verts[count].light_t = clipped[i].light_t;
		if (sx < min_x) min_x = sx;
		if (sy < min_y) min_y = sy;
		if (sx > max_x) max_x = sx;
		if (sy > max_y) max_y = sy;
		depth_sum += sd;
		count++;
	}

	if (count < 3)
		return false;

	for (int i = 0; i < count; i++) {
		int j = (i + 1) % count;
		signed_area += verts[i].x * verts[j].y - verts[j].x * verts[i].y;
	}
	signed_area = fabsf(signed_area) * 0.5f;
	if (signed_area < 1.0f)
		return false;

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

static qboolean QGE_PointInsideProjectedPolygon(float x,
												float y,
												const qge_projected_vertex_t *verts,
												int num_verts)
{
	qboolean inside = false;

	if (!verts || num_verts < 3)
		return false;

	for (int i = 0, j = num_verts - 1; i < num_verts; j = i++) {
		float yi = verts[i].y;
		float yj = verts[j].y;
		float xi = verts[i].x;
		float xj = verts[j].x;
		qboolean crosses = ((yi > y) != (yj > y));
		if (crosses) {
			float at_x = (xj - xi) * (y - yi) / (yj - yi + 0.0001f) + xi;
			if (x < at_x)
				inside = !inside;
		}
	}
	return inside;
}

static void QGE_SpatialClear(void)
{
	if (!qge_spatial_encode_buffer)
		return;
	memset(qge_spatial_encode_buffer, 0,
		   qge_render_res * qge_render_res * sizeof(float));
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

static float QGE_ClampSpatialSignal(float value)
{
	if (value < 0.0f)
		return 0.0f;
	if (value > 1.5f)
		return 1.5f;
	return value;
}

static void QGE_SpatialAddPixelColorDepth(int x,
										  int y,
										  const qge_rgb_sample_t *color,
										  float depth)
{
	int idx;
	float current_depth;
	qge_rgb_sample_t sample;
	float value;

	if (!color)
		return;
	sample = *color;
	if (sample.r < 0.0f) sample.r = 0.0f;
	if (sample.g < 0.0f) sample.g = 0.0f;
	if (sample.b < 0.0f) sample.b = 0.0f;
	value = 0.299f * sample.r + 0.587f * sample.g + 0.114f * sample.b;

	if (!qge_spatial_encode_buffer || x < 0 || y < 0 ||
		x >= qge_render_res || y >= qge_render_res || value <= 0.0f)
		return;

	if (depth <= 0.0f || !isfinite(depth))
		depth = QGE_SPATIAL_DEPTH_FAR * 0.5f;

	idx = y * qge_render_res + x;
	if (!qge_spatial_depth_buffer) {
		qge_spatial_encode_buffer[idx] += value;
		if (qge_spatial_color_buffer[QGE_DWT_R])
			qge_spatial_color_buffer[QGE_DWT_R][idx] += sample.r;
		if (qge_spatial_color_buffer[QGE_DWT_G])
			qge_spatial_color_buffer[QGE_DWT_G][idx] += sample.g;
		if (qge_spatial_color_buffer[QGE_DWT_B])
			qge_spatial_color_buffer[QGE_DWT_B][idx] += sample.b;
	} else {
		current_depth = qge_spatial_depth_buffer[idx];
		if (depth > current_depth + QGE_SPATIAL_DEPTH_EPSILON)
			return;
		if (depth < current_depth - QGE_SPATIAL_DEPTH_EPSILON) {
			qge_spatial_encode_buffer[idx] = value;
			if (qge_spatial_color_buffer[QGE_DWT_R])
				qge_spatial_color_buffer[QGE_DWT_R][idx] = sample.r;
			if (qge_spatial_color_buffer[QGE_DWT_G])
				qge_spatial_color_buffer[QGE_DWT_G][idx] = sample.g;
			if (qge_spatial_color_buffer[QGE_DWT_B])
				qge_spatial_color_buffer[QGE_DWT_B][idx] = sample.b;
			qge_spatial_depth_buffer[idx] = depth;
		} else {
			qge_spatial_encode_buffer[idx] += value;
			if (qge_spatial_color_buffer[QGE_DWT_R])
				qge_spatial_color_buffer[QGE_DWT_R][idx] += sample.r;
			if (qge_spatial_color_buffer[QGE_DWT_G])
				qge_spatial_color_buffer[QGE_DWT_G][idx] += sample.g;
			if (qge_spatial_color_buffer[QGE_DWT_B])
				qge_spatial_color_buffer[QGE_DWT_B][idx] += sample.b;
			if (depth < current_depth)
				qge_spatial_depth_buffer[idx] = depth;
		}
	}
	qge_spatial_encode_buffer[idx] =
		QGE_ClampSpatialSignal(qge_spatial_encode_buffer[idx]);
	if (qge_spatial_color_buffer[QGE_DWT_R])
		qge_spatial_color_buffer[QGE_DWT_R][idx] =
			QGE_ClampSpatialSignal(qge_spatial_color_buffer[QGE_DWT_R][idx]);
	if (qge_spatial_color_buffer[QGE_DWT_G])
		qge_spatial_color_buffer[QGE_DWT_G][idx] =
			QGE_ClampSpatialSignal(qge_spatial_color_buffer[QGE_DWT_G][idx]);
	if (qge_spatial_color_buffer[QGE_DWT_B])
		qge_spatial_color_buffer[QGE_DWT_B][idx] =
			QGE_ClampSpatialSignal(qge_spatial_color_buffer[QGE_DWT_B][idx]);
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
		for (int x = x1; x <= x2; x++)
			QGE_SpatialAddPixelColorDepth(x, y, color, depth);
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

static qboolean QGE_ProjectedTriangleSampleAt(float x,
											  float y,
											  const qge_projected_vertex_t *a,
											  const qge_projected_vertex_t *b,
											  const qge_projected_vertex_t *c,
											  qge_projected_sample_t *sample)
{
	float denom;
	float w0, w1, w2;
	float ia, ib, ic;
	float inv_depth;

	if (!a || !b || !c || !sample)
		return false;

	denom = (b->y - c->y) * (a->x - c->x) +
			(c->x - b->x) * (a->y - c->y);
	if (fabsf(denom) < 0.0001f)
		return false;

	w0 = ((b->y - c->y) * (x - c->x) +
		  (c->x - b->x) * (y - c->y)) / denom;
	w1 = ((c->y - a->y) * (x - c->x) +
		  (a->x - c->x) * (y - c->y)) / denom;
	w2 = 1.0f - w0 - w1;

	if (w0 < -0.001f || w1 < -0.001f || w2 < -0.001f)
		return false;

	ia = a->depth > 0.0001f ? 1.0f / a->depth : 1.0f;
	ib = b->depth > 0.0001f ? 1.0f / b->depth : 1.0f;
	ic = c->depth > 0.0001f ? 1.0f / c->depth : 1.0f;
	inv_depth = w0 * ia + w1 * ib + w2 * ic;
	if (inv_depth <= 0.000001f || !isfinite(inv_depth)) {
		sample->depth = w0 * a->depth + w1 * b->depth + w2 * c->depth;
		sample->tex_s = w0 * a->tex_s + w1 * b->tex_s + w2 * c->tex_s;
		sample->tex_t = w0 * a->tex_t + w1 * b->tex_t + w2 * c->tex_t;
		sample->light_s = w0 * a->light_s + w1 * b->light_s + w2 * c->light_s;
		sample->light_t = w0 * a->light_t + w1 * b->light_t + w2 * c->light_t;
		return true;
	}

	sample->depth = 1.0f / inv_depth;
	sample->tex_s = (w0 * a->tex_s * ia + w1 * b->tex_s * ib +
					 w2 * c->tex_s * ic) / inv_depth;
	sample->tex_t = (w0 * a->tex_t * ia + w1 * b->tex_t * ib +
					 w2 * c->tex_t * ic) / inv_depth;
	sample->light_s = (w0 * a->light_s * ia + w1 * b->light_s * ib +
					   w2 * c->light_s * ic) / inv_depth;
	sample->light_t = (w0 * a->light_t * ia + w1 * b->light_t * ib +
					   w2 * c->light_t * ic) / inv_depth;
	return true;
}

static qge_projected_sample_t QGE_ProjectedPolygonSampleAt(float x,
														   float y,
														   const qge_projected_vertex_t *verts,
														   int num_verts,
														   qge_projected_sample_t fallback)
{
	if (!verts || num_verts < 3)
		return fallback;

	for (int i = 1; i + 1 < num_verts; i++) {
		qge_projected_sample_t sample;
		if (QGE_ProjectedTriangleSampleAt(x, y, &verts[0], &verts[i],
										  &verts[i + 1], &sample))
			return sample;
	}
	return fallback;
}

static float QGE_RGBLuma(const qge_rgb_sample_t *color)
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

static float QGE_TexturePaletteSample(const qge_scene_surface_t *surface,
									  const texture_t *tex,
									  int tx,
									  int ty,
									  qge_rgb_sample_t *color)
{
	const byte *pixels;
	const byte *rgba;
	int palette_index;

	if (!surface || !tex || !color || tex->width <= 0 || tex->height <= 0)
		return 0.0f;

	tx %= (int)tex->width;
	ty %= (int)tex->height;
	if (tx < 0) tx += (int)tex->width;
	if (ty < 0) ty += (int)tex->height;

	pixels = (const byte *)(tex + 1);
	palette_index = pixels[ty * (int)tex->width + tx];
	rgba = (const byte *)&d_8to24table[palette_index];
	if (rgba[3] == 0 || ((surface->flags & SURF_DRAWFENCE) && palette_index == 255)) {
		color->r = 0.0f;
		color->g = 0.0f;
		color->b = 0.0f;
		return 0.0f;
	}

	color->r = (float)rgba[0] / 255.0f;
	color->g = (float)rgba[1] / 255.0f;
	color->b = (float)rgba[2] / 255.0f;
	if (palette_index >= 224) {
		color->r += 0.25f;
		color->g += 0.25f;
		color->b += 0.25f;
	}
	QGE_RGBClamp(color);
	return 1.0f;
}

static qboolean QGE_SurfaceTextureColor(const qge_scene_surface_t *surface,
										float tex_s,
										float tex_t,
										qge_rgb_sample_t *color)
{
	const msurface_t *surf = surface ? surface->surf : NULL;
	texture_t *tex = surf && surf->texinfo ? surf->texinfo->texture : NULL;
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

	tex = R_TextureAnimation(tex, 0);
	width = tex->width;
	height = tex->height;
	if (!width || !height)
		return true;

	tex_s = tex_s - floorf(tex_s);
	tex_t = tex_t - floorf(tex_t);
	if (tex_s < 0.0f) tex_s += 1.0f;
	if (tex_t < 0.0f) tex_t += 1.0f;

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

static qge_rgb_sample_t QGE_SurfaceLightColor(const msurface_t *surf,
											  const qge_projected_sample_t *sample)
{
	int smax, tmax, size;
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
	if (!surf->samples)
		return color;

	smax = (surf->extents[0] >> 4) + 1;
	tmax = (surf->extents[1] >> 4) + 1;
	size = smax * tmax;
	if (smax <= 0 || tmax <= 0 || size <= 0)
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

static qge_rgb_sample_t QGE_SurfaceSampleColor(const qge_scene_surface_t *surface,
											   const qge_projected_sample_t *sample)
{
	qge_rgb_sample_t tex_color;
	qge_rgb_sample_t light_color;
	qge_rgb_sample_t out;
	float material_gain;

	out.r = 1.0f;
	out.g = 1.0f;
	out.b = 1.0f;
	if (!surface || !sample)
		return out;

	if (surface->flags & SURF_DRAWSKY) {
		out.r = 0.020f;
		out.g = 0.035f;
		out.b = 0.090f;
		return out;
	}

	if (!QGE_SurfaceTextureColor(surface, sample->tex_s, sample->tex_t,
								 &tex_color)) {
		out.r = 0.0f;
		out.g = 0.0f;
		out.b = 0.0f;
		return out;
	}
	light_color = QGE_SurfaceLightColor(surface->surf, sample);
	material_gain = 0.85f + surface->material_signal * 0.25f;

	out.r = (0.18f + tex_color.r * 0.82f) *
			(0.30f + light_color.r * 0.90f) * material_gain;
	out.g = (0.18f + tex_color.g * 0.82f) *
			(0.30f + light_color.g * 0.90f) * material_gain;
	out.b = (0.18f + tex_color.b * 0.82f) *
			(0.30f + light_color.b * 0.90f) * material_gain;
	if (surface->flags & (SURF_DRAWLAVA | SURF_DRAWTELE)) {
		out.r *= 1.20f;
		out.g *= 1.20f;
		out.b *= 1.20f;
	}
	out.r = QGE_ClampSpatialSignal(out.r);
	out.g = QGE_ClampSpatialSignal(out.g);
	out.b = QGE_ClampSpatialSignal(out.b);
	if (QGE_RGBLuma(&out) < 0.05f) {
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

	if (!verts || num_verts < 3 || !bounds || value <= 0.0f)
		return;

	avg_sample = QGE_ProjectedPolygonAverageSample(verts, num_verts);

	x1 = bounds->x1;
	y1 = bounds->y1;
	x2 = bounds->x2;
	y2 = bounds->y2;
	if (x1 < 0) x1 = 0;
	if (y1 < 0) y1 = 0;
	if (x2 >= qge_render_res) x2 = qge_render_res - 1;
	if (y2 >= qge_render_res) y2 = qge_render_res - 1;

	for (int y = y1; y <= y2; y++) {
		for (int x = x1; x <= x2; x++) {
			float sample_x = (float)x + 0.5f;
			float sample_y = (float)y + 0.5f;
			qge_projected_sample_t sample;
			qge_rgb_sample_t pixel_color;
			if (!QGE_PointInsideProjectedPolygon(sample_x,
												sample_y,
												verts, num_verts))
				continue;
			sample = QGE_ProjectedPolygonSampleAt(sample_x, sample_y,
												  verts, num_verts,
												  avg_sample);
			pixel_color = QGE_SurfaceSampleColor(surface, &sample);
			pixel_color.r *= value;
			pixel_color.g *= value;
			pixel_color.b *= value;
			QGE_SpatialAddPixelColorDepth(x, y, &pixel_color, sample.depth);
			filled++;
		}
	}

	edge_gain = quantum_render_edge_gain.value;
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
		qge_rgb_sample_t fill_color = QGE_SurfaceSampleColor(surface, &avg_sample);
		fill_color.r *= value;
		fill_color.g *= value;
		fill_color.b *= value;
		QGE_SpatialFillRectColorDepth(bounds, &fill_color, avg_sample.depth);
	}
}

static float QGE_WorldEncodeGain(void)
{
	float gain = 0.11f;

	if (qge_scene_surface_count > 192)
		gain *= sqrtf(192.0f / (float)qge_scene_surface_count);
	if (gain < 0.035f)
		gain = 0.035f;
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

	if (!fb || !surface || !encoded_world)
		return false;
	if (!QGE_SurfaceScreenBounds(surface, surface->surf, &bounds, &depth_world))
		return false;

	depth = depth_world / 4096.0f;
	if (depth > 1.0f) depth = 1.0f;
	if (depth < 0.0f) depth = 0.0f;

	brightness = surface->brightness * (1.0f - depth * 0.45f) * QGE_WorldEncodeGain();
	if (brightness < 0.015f) brightness = 0.015f;

	if (QGE_ProjectSurfacePolygon(surface, surface->surf, verts,
								  QGE_MAX_PROJECTED_POLY_VERTS,
								  &num_verts, &bounds, &depth_world, &area)) {
		depth = depth_world / 4096.0f;
		if (depth > 1.0f) depth = 1.0f;
		if (depth < 0.0f) depth = 0.0f;
		brightness = surface->brightness * (1.0f - depth * 0.45f) * QGE_WorldEncodeGain();
		if (brightness < 0.015f) brightness = 0.015f;
		QGE_EncodeProjectedPolygonDWT(fb, surface, verts, num_verts,
									  &bounds, brightness, depth,
									  depth_world, area);
	} else {
		QGE_SpatialFillRectDepth(&bounds,
								 brightness * (1.0f - depth * 0.1f),
								 depth_world);
		QGE_SpatialOutlineRectDepth(&bounds, brightness * 0.65f,
									depth_world);
		QGE_EncodeSurfaceMaterialDWT(fb, surface, &bounds, brightness,
									 depth, depth_world);
		qge_scene_polygon_fallback++;
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
		bounds->x1 = (qge_render_res * 47) / 100;
		bounds->x2 = (qge_render_res * 55) / 100;
		bounds->y1 = (qge_render_res * 72) / 100;
		bounds->y2 = qge_render_res - 4;
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

static void QGE_EncodeSnapshotEntityDetailDWT(dwt_framebuffer_t *fb,
											  const qge_snapshot_edict_t *edict,
											  const screen_rect_t *bounds,
											  float brightness,
											  float depth_world)
{
	uint64_t hash;
	int center_x, center_y;
	int width, height;

	(void)fb;

	if (!edict || !bounds)
		return;

	hash = (uint64_t)edict->entity_id;
	hash = QGE_RegistryHashStep(hash, (uint64_t)edict->model_id);
	hash = QGE_RegistryHashStep(hash, (uint64_t)(uint32_t)edict->frame);
	hash = QGE_RegistryHashStep(hash, edict->effects);
	center_x = (bounds->x1 + bounds->x2) / 2;
	center_y = (bounds->y1 + bounds->y2) / 2;
	width = bounds->x2 - bounds->x1;
	height = bounds->y2 - bounds->y1;
	if (width < 1) width = 1;
	if (height < 1) height = 1;

	if (QGE_IsSnapshotViewmodel(edict)) {
		QGE_SpatialLineDepth((float)bounds->x1, (float)bounds->y2,
							 (float)center_x, (float)bounds->y1,
							 brightness * 0.55f, depth_world, depth_world);
		QGE_SpatialLineDepth((float)bounds->x2, (float)bounds->y2,
							 (float)center_x, (float)bounds->y1,
							 brightness * 0.55f, depth_world, depth_world);
		QGE_SpatialAddPixelDepth(center_x, bounds->y1, brightness * 0.85f,
								 depth_world);
		return;
	}

	QGE_SpatialOutlineRectDepth(bounds, brightness * 1.25f, depth_world);
	QGE_SpatialAddPixelDepth(center_x, center_y, brightness * 0.55f,
							 depth_world);
	QGE_SpatialAddPixelDepth(bounds->x1 + (int)(hash % (uint64_t)width),
							 center_y, brightness * 0.32f, depth_world);
	QGE_SpatialAddPixelDepth(center_x,
							 bounds->y1 + (int)((hash >> 8) % (uint64_t)height),
							 brightness * 0.32f, depth_world);

	if (QGE_IsSnapshotViewmodel(edict) ||
		(edict->effects & (EF_MUZZLEFLASH | EF_BRIGHTLIGHT |
						   EF_QEX_QUADLIGHT | EF_QEX_PENTALIGHT))) {
		QGE_SpatialAddPixelDepth(center_x, center_y, brightness * 0.90f,
								 depth_world);
	}
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
	if (QGE_IsSnapshotViewmodel(edict))
		return true;

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

	if (!QGE_IsSnapshotViewmodel(edict)) {
		QGE_SpatialFillRectDepth(&bounds,
								 model_kind == QGE_RESOURCE_SPRITE ?
								 brightness * 1.05f : brightness * 0.80f,
								 depth_world);
	} else {
		QGE_SpatialOutlineRectDepth(&bounds, brightness * 0.70f,
									depth_world);
	}
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
	int active = 0;
	int median_target;
	int white_target;
	int running;
	int i;

	memset(hist, 0, sizeof(hist));
	*nonzero_pixels = 0;
	*abs_sum = 0.0;

	for (i = 0; i < total_pixels; i++) {
		int x = i % qge_render_res;
		int y = i / qge_render_res;
		float v = QGE_DisplayEnergyAt(x, y);
		qge_render_buffer[i] = v;
		if (v > max_abs)
			max_abs = v;
		if (v > 0.0001f) {
			(*nonzero_pixels)++;
			active++;
		}
		*abs_sum += v;
	}

	if (active <= 0) {
		memset(qge_display_buffer, 0, total_pixels * 3);
		*max_val = max_abs;
		qge_last_tone_floor = 0.0f;
		qge_last_tone_white = 1.0f;
		qge_last_tone_clipped = 0;
		return;
	}

	for (i = 0; i < total_pixels; i++) {
		int x = i % qge_render_res;
		int y = i / qge_render_res;
		float v = QGE_DisplayEnergyAt(x, y);
		if (v > 0.0001f) {
			int bin = (int)((v / max_abs) * (float)(QGE_TONE_BINS - 1));
			if (bin < 0) bin = 0;
			if (bin >= QGE_TONE_BINS) bin = QGE_TONE_BINS - 1;
			hist[bin]++;
		}
	}

	median_target = active / 2;
	white_target = (active * 992) / 1000;
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

	for (i = 0; i < total_pixels; i++) {
		int x = i % qge_render_res;
		int y = i / qge_render_res;
		float r = QGE_DisplayChannelEnergyAt(qge_render_color_buffer[QGE_DWT_R], x, y);
		float g = QGE_DisplayChannelEnergyAt(qge_render_color_buffer[QGE_DWT_G], x, y);
		float b = QGE_DisplayChannelEnergyAt(qge_render_color_buffer[QGE_DWT_B], x, y);
		float v = 0.299f * r + 0.587f * g + 0.114f * b;
		float normalized = (v - floor_val) * inv_range;
		float scale;
		int idx;

		if (normalized <= 0.0f)
			normalized = 0.0f;
		else if (normalized >= 1.0f) {
			normalized = 1.0f;
			qge_last_tone_clipped++;
		}

		normalized = log1pf(normalized * 4.0f) / log1pf(4.0f);
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

	if (!qge_dwt_fb[QGE_DWT_R] || !qge_dwt_fb[QGE_DWT_G] ||
		!qge_dwt_fb[QGE_DWT_B])
		return;

	/* Reset write framebuffer for new frame */
	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++)
		qge_dwt_framebuffer_reset(qge_dwt_fb[ch]);
	QGE_SpatialClear();

	/* Encode visible BSP world surfaces submitted by R_MarkSurfaces. */
	surface_budget = (int)quantum_scene_surface_budget.value;
	if (surface_budget < 16) surface_budget = 16;
	if (surface_budget > QGE_MAX_SCENE_SURFACES) surface_budget = QGE_MAX_SCENE_SURFACES;
	snapshot = qge_get_frame_snapshot(qge_ctx);
	if (snapshot && !snapshot->sealed)
		QGE_FrameSnapshotCaptureEdicts(snapshot);
	encoded_world = QGE_EncodeSnapshotWorldSurfaces(qge_dwt_fb[QGE_DWT_R],
													snapshot,
													surface_budget);
	if (!encoded_world)
		encoded_world = QGE_EncodeTransientWorldSurfaces(qge_dwt_fb[QGE_DWT_R],
														 surface_budget);
	qge_scene_encoded_surfaces = encoded_world;

	QGE_EncodeSnapshotEdicts(qge_dwt_fb[QGE_DWT_R], snapshot);

	if (!encoded_world) {
		screen_rect_t world_bounds = {
			.x1 = 0, .y1 = 0,
			.x2 = qge_render_res - 1, .y2 = qge_render_res - 1
		};
		QGE_SpatialFillRectDepth(&world_bounds,
								 0.15f * (1.0f - 0.95f * 0.1f),
								 8192.0f);
	}

	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++) {
		const float *source = qge_spatial_color_buffer[ch] ?
							  qge_spatial_color_buffer[ch] :
							  qge_spatial_encode_buffer;
		qge_dwt_encode_spatial(qge_dwt_fb[ch], source,
							   qge_render_res, qge_render_res);
	}
}

static void QGE_ResetTextureUnitsForBlit(void)
{
	if (GL_SelectTextureFunc) {
		GLint max_units = 1;

		glGetIntegerv(GL_MAX_TEXTURE_UNITS, &max_units);
		if (max_units < 1)
			max_units = 1;
		if (max_units > 8)
			max_units = 8;

		for (int unit = max_units - 1; unit >= 3; unit--) {
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
	glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
	glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, qge_render_res, qge_render_res,
					GL_RGB, GL_UNSIGNED_BYTE, qge_display_buffer);
	qge_last_gl_upload_error = glGetError();

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

void QGE_RenderScene(void)
{
	int active = 0;
	float sparsity = 0.0f;
	int total_coefficients;

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

	double start = Sys_DoubleTime();

	/* Step 1: Encode scene geometry as wavelet coefficients.
	 * Resets the framebuffer then encodes all visible entities. */
	QGE_EncodeScene();

	/* Step 2: Quantum signal processing — extract coefficients and inverse DWT.
	 * Uses the SAME buffer we just encoded into (like the working demo).
	 * Sparse-only path — active_indices/values provide the wavelet representation
	 * without iterating all 268M amplitudes. */
	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++)
		qge_dwt_render(qge_dwt_fb[ch], qge_render_color_buffer[ch]);

	/* Step 3: Convert float pixels to RGB display buffer. */
	float max_val = 0.0001f;
	int nonzero_pixels = 0;
	double abs_sum = 0.0;
	int total_pixels = qge_render_res * qge_render_res;
	QGE_ConvertRenderBufferToDisplay(total_pixels, &max_val, &nonzero_pixels, &abs_sum);

	/* Step 4: Blit to screen */
	QGE_BlitToScreen();

	double elapsed = (Sys_DoubleTime() - start) * 1000.0;
	for (int ch = 0; ch < QGE_DWT_CHANNELS; ch++)
		active += qge_dwt_get_active_count(qge_dwt_fb[ch]);
	total_coefficients = qge_render_res * qge_render_res * QGE_DWT_CHANNELS;
	if (total_coefficients > 0)
		sparsity = (float)active / (float)total_coefficients;

	qge_quantum_runtime_t *rt = QGE_Runtime();
	if (rt) {
		qge_state_probe_t probe;
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
		probe.flags = (uint32_t)qge_scene_snapshot_misses |
					  (qge_render_qge_primary_owned ? 0x10000u : 0u);
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
			if (qge_frame_count < 5 || (qge_frame_count % 60) == 0) {
				Con_Printf("QGE render frame=%d mode=%s owner=%s classic3d=%d suppressed3d=%d "
						   "res=%d coeffs=%d snapshot=%d snapshot_miss=%d "
						   "texcache=%d/%d lightcache=%d/%d poly=%d fallback=%d "
						   "encoded=%d material=%d edicts=%d alias=%d sprites=%d "
						   "viewmodel=%d entity_miss=%d nonzero=%d/%d\n",
						   qge_frame_count, QGE_RenderIsPrimary() ? "primary" : "overlay",
						   qge_render_qge_primary_owned ? "qge_3d" : "mixed",
						   qge_render_classic_3d_passes,
						   qge_render_suppressed_3d_passes,
						   qge_render_res, active, qge_scene_snapshot_surfaces,
						   qge_scene_snapshot_misses, qge_scene_texture_cache_hits,
						   qge_scene_texture_cache_misses, qge_scene_lightmap_cache_hits,
						   qge_scene_lightmap_cache_misses, qge_scene_polygon_encoded,
						   qge_scene_polygon_fallback, qge_scene_encoded_surfaces,
						   qge_scene_material_encoded, qge_scene_encoded_edicts,
						   qge_scene_alias_encoded, qge_scene_sprite_encoded,
						   qge_scene_viewmodel_encoded, qge_scene_entity_misses,
						   nonzero_pixels, total_pixels);
			}
			fprintf(stderr, "QGE render frame=%d mode=%s owner=%s classic3d=%d suppressed3d=%d "
					"res=%d time=%.1fms coeffs=%d sparse=%.1f%% "
					"scene_surfaces=%d snapshot_surfaces=%d snapshot_misses=%d "
					"texcache=%d/%d lightcache=%d/%d poly=%d fallback=%d encoded_surfaces=%d "
					"material_encoded=%d snapshot_edicts=%d encoded_edicts=%d alias=%d "
					"sprites=%d viewmodel=%d entity_misses=%d visedicts=%d nonzero=%d/%d max=%.6f sum=%.3f "
					"tone_floor=%.6f tone_white=%.6f tone_clip=%d levels=%d gl_upload=0x%x gl_draw=0x%x\n",
					qge_frame_count, QGE_RenderIsPrimary() ? "primary" : "overlay",
					qge_render_qge_primary_owned ? "qge_3d" : "mixed",
					qge_render_classic_3d_passes,
					qge_render_suppressed_3d_passes,
					qge_render_res, elapsed, active, sparsity * 100.0f,
					qge_scene_surface_count, qge_scene_snapshot_surfaces,
					qge_scene_snapshot_misses, qge_scene_texture_cache_hits,
					qge_scene_texture_cache_misses, qge_scene_lightmap_cache_hits,
					qge_scene_lightmap_cache_misses, qge_scene_polygon_encoded,
					qge_scene_polygon_fallback, qge_scene_encoded_surfaces,
					qge_scene_material_encoded, qge_scene_snapshot_edicts,
					qge_scene_encoded_edicts, qge_scene_alias_encoded,
					qge_scene_sprite_encoded, qge_scene_viewmodel_encoded,
					qge_scene_entity_misses, cl_numvisedicts, nonzero_pixels, total_pixels,
					max_val, abs_sum, qge_last_tone_floor, qge_last_tone_white,
					qge_last_tone_clipped, qge_dwt_levels,
					(unsigned)qge_last_gl_upload_error,
					(unsigned)qge_last_gl_draw_error);
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
	int error_count = 0;

	qge_phys_active_objects = 0;
	qge_phys_active_projectiles = 0;
	qge_phys_avg_shadow_error = 0.0f;
	qge_phys_max_shadow_error = 0.0f;

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
		}
	}

	if (error_count > 0)
		qge_phys_avg_shadow_error = sum_error / (float)error_count;
}

static qge_vec3_t QGE_VecFromQuake(const vec3_t v)
{
	qge_vec3_t out = {v[0], v[1], v[2]};
	return out;
}

void QGE_PhysicsTrackToss(edict_t *ent, float dt)
{
	int movetype;
	int entnum;
	qge_phys_object_t *obj;

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

		obj->movetype = movetype;
		obj->last_seen_frame = qge_frame_count;
		obj->seen_count++;
		VectorCopy(ent->v.origin, obj->origin);
		VectorCopy(ent->v.velocity, obj->velocity);
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

	if (!trace || !QGE_PhysicsShouldTrack(ent))
		return;

	qge_phys_impact_count++;
	obj = QGE_PhysicsFindObject(NUM_FOR_EDICT(ent), true);
	if (obj) {
		obj->impacts++;
		obj->last_seen_frame = qge_frame_count;
		VectorCopy(trace->endpos, obj->origin);
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
