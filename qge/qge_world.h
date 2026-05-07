/**
 * @file qge_world.h
 * @brief Stable world/resource registry and immutable frame snapshots.
 */

#ifndef QGE_WORLD_H
#define QGE_WORLD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifndef QGE_VEC3_T_DEFINED
#define QGE_VEC3_T_DEFINED
typedef struct {
    float x, y, z;
} qge_vec3_t;
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define QGE_WORLD_NAME_MAX 64
#define QGE_WORLD_STYLE_COUNT 4
#define QGE_RESOURCE_ID_INVALID ((qge_resource_id_t)0)
#define QGE_RESOURCE_ID_KIND_SHIFT 24u
#define QGE_RESOURCE_ID_INDEX_MASK 0x00ffffffu

#define QGE_FRAME_MAX_VISIBLE_SURFACES 4096
#define QGE_FRAME_MAX_EDICTS 1024
#define QGE_FRAME_MAX_DYNAMIC_LIGHTS 128
#define QGE_FRAME_MAX_PARTICLES 4096
#define QGE_FRAME_MAX_SOUND_SOURCES 128
#define QGE_FRAME_MAX_ENTROPY_REFS 512

typedef uint32_t qge_resource_id_t;

typedef enum {
    QGE_RESOURCE_NONE = 0,
    QGE_RESOURCE_WORLD = 1,
    QGE_RESOURCE_BSP_MODEL = 2,
    QGE_RESOURCE_BSP_LEAF = 3,
    QGE_RESOURCE_BSP_NODE = 4,
    QGE_RESOURCE_BSP_PLANE = 5,
    QGE_RESOURCE_SURFACE = 6,
    QGE_RESOURCE_TEXTURE = 7,
    QGE_RESOURCE_LIGHTMAP = 8,
    QGE_RESOURCE_ALIAS_MODEL = 9,
    QGE_RESOURCE_SPRITE = 10,
    QGE_RESOURCE_HUD_IMAGE = 11,
    QGE_RESOURCE_SOUND = 12,
    QGE_RESOURCE_MUSIC_BLOCK = 13,
    QGE_RESOURCE_ENTITY = 14,
    QGE_RESOURCE_PARTICLE = 15,
    QGE_RESOURCE_DYNAMIC_LIGHT = 16,
    QGE_RESOURCE_AUDIO_SOURCE = 17,
    QGE_RESOURCE_KIND_COUNT
} qge_resource_kind_t;

typedef enum {
    QGE_MODEL_UNKNOWN = 0,
    QGE_MODEL_BRUSH = 1,
    QGE_MODEL_ALIAS = 2,
    QGE_MODEL_SPRITE = 3
} qge_model_type_t;

typedef enum {
    QGE_TEXTURE_FLAG_FULLBRIGHT = 1u << 0,
    QGE_TEXTURE_FLAG_WARP = 1u << 1,
    QGE_TEXTURE_FLAG_SKY = 1u << 2,
    QGE_TEXTURE_FLAG_FENCE = 1u << 3,
    QGE_TEXTURE_FLAG_ALPHA = 1u << 4
} qge_texture_flags_t;

typedef enum {
    QGE_HUD_IMAGE_FLAG_WAD = 1u << 0,
    QGE_HUD_IMAGE_FLAG_CACHE = 1u << 1,
    QGE_HUD_IMAGE_FLAG_GENERATED = 1u << 2
} qge_hud_image_flags_t;

typedef enum {
    QGE_SOUND_FLAG_LOADED = 1u << 0,
    QGE_SOUND_FLAG_16BIT = 1u << 1,
    QGE_SOUND_FLAG_LOOPED = 1u << 2
} qge_sound_flags_t;

typedef struct qge_world_s qge_world_t;

typedef struct {
    qge_resource_id_t id;
    qge_model_type_t model_type;
    char name[QGE_WORLD_NAME_MAX];
    uint64_t source_hash;
    uint64_t debug_cookie;
    qge_vec3_t mins;
    qge_vec3_t maxs;
    uint32_t flags;
    uint32_t first_surface;
    uint32_t surface_count;
    uint32_t texture_count;
    uint32_t leaf_count;
    uint32_t node_count;
    uint32_t plane_count;
} qge_model_ref_t;

typedef struct {
    qge_resource_id_t id;
    qge_resource_id_t model_id;
    uint32_t plane_index;
    qge_vec3_t normal;
    float dist;
    uint8_t type;
    uint8_t signbits;
    uint32_t flags;
    uint64_t debug_cookie;
} qge_plane_ref_t;

typedef struct {
    qge_resource_id_t id;
    qge_resource_id_t model_id;
    qge_resource_id_t plane_id;
    qge_resource_id_t child_ids[2];
    uint32_t node_index;
    int32_t contents;
    uint32_t first_surface;
    uint32_t surface_count;
    qge_vec3_t mins;
    qge_vec3_t maxs;
    uint64_t debug_cookie;
} qge_node_ref_t;

typedef struct {
    qge_resource_id_t id;
    qge_resource_id_t model_id;
    uint32_t leaf_index;
    int32_t contents;
    uint32_t first_marksurface;
    uint32_t marksurface_count;
    uint32_t compressed_vis_offset;
    uint8_t ambient_sound_level[4];
    qge_vec3_t mins;
    qge_vec3_t maxs;
    uint64_t debug_cookie;
} qge_leaf_ref_t;

typedef struct {
    qge_resource_id_t id;
    qge_resource_id_t model_id;
    qge_resource_id_t texture_id;
    qge_resource_id_t lightmap_id;
    uint32_t surface_index;
    uint32_t plane_index;
    uint32_t flags;
    int32_t first_edge;
    int32_t edge_count;
    uint64_t debug_cookie;
    qge_vec3_t mins;
    qge_vec3_t maxs;
    qge_vec3_t centroid;
    float light_energy;
    float light_contrast;
    float material_signal;
} qge_surface_ref_t;

typedef struct {
    qge_resource_id_t id;
    qge_resource_id_t owner_model_id;
    char name[QGE_WORLD_NAME_MAX];
    uint32_t texture_index;
    uint32_t width;
    uint32_t height;
    uint32_t source_crc;
    uint32_t source_format;
    uint32_t flags;
    uint64_t source_hash;
    uint64_t debug_cookie;
} qge_texture_ref_t;

typedef struct {
    qge_resource_id_t id;
    qge_resource_id_t model_id;
    qge_resource_id_t surface_id;
    uint32_t lightmap_index;
    uint32_t width;
    uint32_t height;
    uint8_t styles[QGE_WORLD_STYLE_COUNT];
    uint64_t sample_hash;
    float energy;
    float contrast;
} qge_lightmap_ref_t;

typedef struct {
    qge_resource_id_t id;
    char name[QGE_WORLD_NAME_MAX];
    uint32_t precache_index;
    uint32_t vertex_count;
    uint32_t triangle_count;
    uint32_t skin_count;
    uint32_t frame_count;
    uint32_t flags;
    uint64_t source_hash;
    uint64_t debug_cookie;
    qge_vec3_t mins;
    qge_vec3_t maxs;
} qge_alias_model_ref_t;

typedef struct {
    qge_resource_id_t id;
    char name[QGE_WORLD_NAME_MAX];
    uint32_t precache_index;
    uint32_t frame_count;
    uint32_t width;
    uint32_t height;
    uint32_t flags;
    uint32_t sprite_type;
    uint64_t source_hash;
    uint64_t debug_cookie;
} qge_sprite_ref_t;

typedef struct {
    qge_resource_id_t id;
    char name[QGE_WORLD_NAME_MAX];
    uint32_t precache_index;
    uint32_t sample_rate;
    uint32_t channels;
    uint32_t sample_count;
    uint32_t sample_width;
    uint32_t flags;
    uint64_t source_hash;
    uint64_t debug_cookie;
} qge_sound_ref_t;

typedef struct {
    qge_resource_id_t id;
    char name[QGE_WORLD_NAME_MAX];
    uint32_t width;
    uint32_t height;
    uint32_t source_crc;
    uint32_t source_format;
    uint32_t flags;
    uint64_t source_hash;
    uint64_t debug_cookie;
} qge_hud_image_ref_t;

typedef struct {
    qge_resource_id_t current_world_id;
    uint32_t map_revision;
    char map_name[QGE_WORLD_NAME_MAX];
    uint64_t map_hash;
    uint32_t total_resources;
    uint32_t model_count;
    uint32_t plane_count;
    uint32_t node_count;
    uint32_t leaf_count;
    uint32_t surface_count;
    uint32_t texture_count;
    uint32_t lightmap_count;
    uint32_t alias_model_count;
    uint32_t sprite_count;
    uint32_t sound_count;
    uint32_t hud_image_count;
} qge_world_stats_t;

typedef struct {
    qge_vec3_t origin;
    qge_vec3_t forward;
    qge_vec3_t right;
    qge_vec3_t up;
    float fov_x;
    float fov_y;
    int viewport_x;
    int viewport_y;
    int viewport_width;
    int viewport_height;
} qge_camera_snapshot_t;

typedef struct {
    qge_resource_id_t surface_id;
    float visibility;
    float depth;
    uint32_t flags;
} qge_snapshot_surface_t;

typedef struct {
    qge_resource_id_t entity_id;
    qge_resource_id_t model_id;
    qge_vec3_t origin;
    qge_vec3_t angles;
    qge_vec3_t mins;
    qge_vec3_t maxs;
    uint32_t effects;
    int32_t frame;
    float alpha;
    float scale;
} qge_snapshot_edict_t;

typedef struct {
    qge_resource_id_t light_id;
    qge_vec3_t origin;
    qge_vec3_t color;
    float radius;
    float intensity;
} qge_snapshot_light_t;

typedef struct {
    qge_resource_id_t particle_id;
    qge_vec3_t origin;
    qge_vec3_t velocity;
    uint32_t color;
    float lifetime;
} qge_snapshot_particle_t;

typedef struct {
    qge_resource_id_t source_id;
    qge_resource_id_t sound_id;
    qge_vec3_t origin;
    float volume;
    float attenuation;
    int32_t channel;
} qge_snapshot_sound_t;

typedef struct {
    uint64_t entropy_event_id;
    uint32_t domain;
    uint32_t kind;
    uint64_t value;
} qge_snapshot_entropy_t;

typedef struct {
    uint32_t visible_surface_count;
    uint32_t edict_count;
    uint32_t dynamic_light_count;
    uint32_t particle_count;
    uint32_t sound_source_count;
    uint32_t entropy_ref_count;
    uint32_t dropped_visible_surfaces;
    uint32_t dropped_edicts;
    uint32_t dropped_dynamic_lights;
    uint32_t dropped_particles;
    uint32_t dropped_sound_sources;
    uint32_t dropped_entropy_refs;
    bool sealed;
} qge_frame_snapshot_stats_t;

typedef struct {
    bool sealed;
    uint32_t frame_number;
    int64_t host_time_msec;
    int64_t server_time_msec;
    int64_t client_time_msec;
    qge_camera_snapshot_t camera;
    qge_resource_id_t world_id;
    qge_resource_id_t world_model_id;
    uint32_t view_leaf_index;
    uint32_t pvs_hash;

    uint32_t visible_surface_count;
    uint32_t edict_count;
    uint32_t dynamic_light_count;
    uint32_t particle_count;
    uint32_t sound_source_count;
    uint32_t entropy_ref_count;

    uint32_t dropped_visible_surfaces;
    uint32_t dropped_edicts;
    uint32_t dropped_dynamic_lights;
    uint32_t dropped_particles;
    uint32_t dropped_sound_sources;
    uint32_t dropped_entropy_refs;

    qge_snapshot_surface_t visible_surfaces[QGE_FRAME_MAX_VISIBLE_SURFACES];
    qge_snapshot_edict_t edicts[QGE_FRAME_MAX_EDICTS];
    qge_snapshot_light_t dynamic_lights[QGE_FRAME_MAX_DYNAMIC_LIGHTS];
    qge_snapshot_particle_t particles[QGE_FRAME_MAX_PARTICLES];
    qge_snapshot_sound_t sound_sources[QGE_FRAME_MAX_SOUND_SOURCES];
    qge_snapshot_entropy_t entropy_refs[QGE_FRAME_MAX_ENTROPY_REFS];
} qge_frame_snapshot_t;

const char* qge_resource_kind_name(qge_resource_kind_t kind);
qge_resource_id_t qge_resource_id_make(qge_resource_kind_t kind, uint32_t index);
qge_resource_kind_t qge_resource_id_kind(qge_resource_id_t id);
uint32_t qge_resource_id_index(qge_resource_id_t id);
bool qge_resource_id_is_valid(qge_resource_id_t id);

qge_world_t* qge_world_create(void);
void qge_world_free(qge_world_t* world);
void qge_world_clear(qge_world_t* world);
qge_resource_id_t qge_world_begin_map(qge_world_t* world,
                                      const char* map_name,
                                      uint64_t map_hash);
qge_resource_id_t qge_world_current_map_id(const qge_world_t* world);
void qge_world_get_stats(const qge_world_t* world, qge_world_stats_t* stats);

qge_resource_id_t qge_world_register_model(qge_world_t* world,
                                           const qge_model_ref_t* ref);
qge_resource_id_t qge_world_register_plane(qge_world_t* world,
                                           const qge_plane_ref_t* ref);
qge_resource_id_t qge_world_register_node(qge_world_t* world,
                                          const qge_node_ref_t* ref);
qge_resource_id_t qge_world_register_leaf(qge_world_t* world,
                                          const qge_leaf_ref_t* ref);
qge_resource_id_t qge_world_register_surface(qge_world_t* world,
                                             const qge_surface_ref_t* ref);
qge_resource_id_t qge_world_register_texture(qge_world_t* world,
                                             const qge_texture_ref_t* ref);
qge_resource_id_t qge_world_register_lightmap(qge_world_t* world,
                                              const qge_lightmap_ref_t* ref);
qge_resource_id_t qge_world_register_alias_model(qge_world_t* world,
                                                 const qge_alias_model_ref_t* ref);
qge_resource_id_t qge_world_register_sprite(qge_world_t* world,
                                            const qge_sprite_ref_t* ref);
qge_resource_id_t qge_world_register_sound(qge_world_t* world,
                                           const qge_sound_ref_t* ref);
qge_resource_id_t qge_world_register_hud_image(qge_world_t* world,
                                               const qge_hud_image_ref_t* ref);

const qge_model_ref_t* qge_world_get_model(const qge_world_t* world,
                                           qge_resource_id_t id);
const qge_plane_ref_t* qge_world_get_plane(const qge_world_t* world,
                                           qge_resource_id_t id);
const qge_node_ref_t* qge_world_get_node(const qge_world_t* world,
                                         qge_resource_id_t id);
const qge_leaf_ref_t* qge_world_get_leaf(const qge_world_t* world,
                                         qge_resource_id_t id);
const qge_surface_ref_t* qge_world_get_surface(const qge_world_t* world,
                                               qge_resource_id_t id);
const qge_texture_ref_t* qge_world_get_texture(const qge_world_t* world,
                                               qge_resource_id_t id);
const qge_lightmap_ref_t* qge_world_get_lightmap(const qge_world_t* world,
                                                 qge_resource_id_t id);
const qge_alias_model_ref_t* qge_world_get_alias_model(const qge_world_t* world,
                                                       qge_resource_id_t id);
const qge_sprite_ref_t* qge_world_get_sprite(const qge_world_t* world,
                                             qge_resource_id_t id);
const qge_sound_ref_t* qge_world_get_sound(const qge_world_t* world,
                                           qge_resource_id_t id);
const qge_hud_image_ref_t* qge_world_get_hud_image(const qge_world_t* world,
                                                   qge_resource_id_t id);

void qge_frame_snapshot_reset(qge_frame_snapshot_t* snapshot);
void qge_frame_snapshot_begin(qge_frame_snapshot_t* snapshot,
                              uint32_t frame_number,
                              int64_t host_time_msec,
                              int64_t server_time_msec,
                              int64_t client_time_msec);
void qge_frame_snapshot_set_camera(qge_frame_snapshot_t* snapshot,
                                   const qge_camera_snapshot_t* camera);
void qge_frame_snapshot_set_world(qge_frame_snapshot_t* snapshot,
                                  qge_resource_id_t world_id,
                                  qge_resource_id_t world_model_id,
                                  uint32_t view_leaf_index,
                                  uint32_t pvs_hash);
void qge_frame_snapshot_seal(qge_frame_snapshot_t* snapshot);
bool qge_frame_snapshot_is_sealed(const qge_frame_snapshot_t* snapshot);
int qge_frame_snapshot_copy(qge_frame_snapshot_t* dst,
                            const qge_frame_snapshot_t* src);
void qge_frame_snapshot_get_stats(const qge_frame_snapshot_t* snapshot,
                                  qge_frame_snapshot_stats_t* stats);

int qge_frame_snapshot_add_visible_surface(qge_frame_snapshot_t* snapshot,
                                           const qge_snapshot_surface_t* item);
int qge_frame_snapshot_add_edict(qge_frame_snapshot_t* snapshot,
                                 const qge_snapshot_edict_t* item);
int qge_frame_snapshot_add_dynamic_light(qge_frame_snapshot_t* snapshot,
                                         const qge_snapshot_light_t* item);
int qge_frame_snapshot_add_particle(qge_frame_snapshot_t* snapshot,
                                    const qge_snapshot_particle_t* item);
int qge_frame_snapshot_add_sound_source(qge_frame_snapshot_t* snapshot,
                                        const qge_snapshot_sound_t* item);
int qge_frame_snapshot_add_entropy_ref(qge_frame_snapshot_t* snapshot,
                                       const qge_snapshot_entropy_t* item);

#ifdef __cplusplus
}
#endif

#endif /* QGE_WORLD_H */
