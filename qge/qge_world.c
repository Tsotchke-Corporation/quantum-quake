/**
 * @file qge_world.c
 * @brief Stable QGE world/resource registry and frame snapshots.
 */

#include "qge_world.h"
#include <stdlib.h>
#include <string.h>

struct qge_world_s {
    qge_resource_id_t current_world_id;
    uint32_t map_revision;
    char map_name[QGE_WORLD_NAME_MAX];
    uint64_t map_hash;

    qge_model_ref_t* models;
    qge_plane_ref_t* planes;
    qge_node_ref_t* nodes;
    qge_leaf_ref_t* leafs;
    qge_surface_ref_t* surfaces;
    qge_texture_ref_t* textures;
    qge_lightmap_ref_t* lightmaps;
    qge_alias_model_ref_t* alias_models;
    qge_sprite_ref_t* sprites;
    qge_sound_ref_t* sounds;
    qge_hud_image_ref_t* hud_images;

    size_t model_count;
    size_t plane_count;
    size_t node_count;
    size_t leaf_count;
    size_t surface_count;
    size_t texture_count;
    size_t lightmap_count;
    size_t alias_model_count;
    size_t sprite_count;
    size_t sound_count;
    size_t hud_image_count;

    size_t model_capacity;
    size_t plane_capacity;
    size_t node_capacity;
    size_t leaf_capacity;
    size_t surface_capacity;
    size_t texture_capacity;
    size_t lightmap_capacity;
    size_t alias_model_capacity;
    size_t sprite_capacity;
    size_t sound_capacity;
    size_t hud_image_capacity;
};

static void qge_copy_name(char dst[QGE_WORLD_NAME_MAX], const char* src) {
    if (!dst) return;
    if (!src) src = "";
    strncpy(dst, src, QGE_WORLD_NAME_MAX - 1);
    dst[QGE_WORLD_NAME_MAX - 1] = '\0';
}

static int qge_grow_array(void** items,
                          size_t* capacity,
                          size_t count,
                          size_t item_size) {
    size_t old_capacity;
    size_t new_capacity;
    void* new_items;

    if (!items || !capacity || item_size == 0) return -1;
    if (count < *capacity) return 0;

    old_capacity = *capacity;
    new_capacity = old_capacity ? old_capacity * 2 : 64;
    while (new_capacity <= count) {
        if (new_capacity > (QGE_RESOURCE_ID_INDEX_MASK / 2u)) return -1;
        new_capacity *= 2;
    }
    if (new_capacity > QGE_RESOURCE_ID_INDEX_MASK) {
        new_capacity = QGE_RESOURCE_ID_INDEX_MASK;
        if (new_capacity <= count) return -1;
    }

    new_items = realloc(*items, new_capacity * item_size);
    if (!new_items) return -1;
    memset((char*)new_items + old_capacity * item_size, 0,
           (new_capacity - old_capacity) * item_size);
    *items = new_items;
    *capacity = new_capacity;
    return 0;
}

const char* qge_resource_kind_name(qge_resource_kind_t kind) {
    switch (kind) {
        case QGE_RESOURCE_NONE: return "none";
        case QGE_RESOURCE_WORLD: return "world";
        case QGE_RESOURCE_BSP_MODEL: return "bsp_model";
        case QGE_RESOURCE_BSP_LEAF: return "bsp_leaf";
        case QGE_RESOURCE_BSP_NODE: return "bsp_node";
        case QGE_RESOURCE_BSP_PLANE: return "bsp_plane";
        case QGE_RESOURCE_SURFACE: return "surface";
        case QGE_RESOURCE_TEXTURE: return "texture";
        case QGE_RESOURCE_LIGHTMAP: return "lightmap";
        case QGE_RESOURCE_ALIAS_MODEL: return "alias_model";
        case QGE_RESOURCE_SPRITE: return "sprite";
        case QGE_RESOURCE_HUD_IMAGE: return "hud_image";
        case QGE_RESOURCE_SOUND: return "sound";
        case QGE_RESOURCE_MUSIC_BLOCK: return "music_block";
        case QGE_RESOURCE_ENTITY: return "entity";
        case QGE_RESOURCE_PARTICLE: return "particle";
        case QGE_RESOURCE_DYNAMIC_LIGHT: return "dynamic_light";
        case QGE_RESOURCE_AUDIO_SOURCE: return "audio_source";
        default: return "unknown";
    }
}

qge_resource_id_t qge_resource_id_make(qge_resource_kind_t kind, uint32_t index) {
    if (kind <= QGE_RESOURCE_NONE ||
        kind >= QGE_RESOURCE_KIND_COUNT ||
        index == 0 ||
        index > QGE_RESOURCE_ID_INDEX_MASK) {
        return QGE_RESOURCE_ID_INVALID;
    }
    return ((qge_resource_id_t)kind << QGE_RESOURCE_ID_KIND_SHIFT) | index;
}

qge_resource_kind_t qge_resource_id_kind(qge_resource_id_t id) {
    return (qge_resource_kind_t)(id >> QGE_RESOURCE_ID_KIND_SHIFT);
}

uint32_t qge_resource_id_index(qge_resource_id_t id) {
    return id & QGE_RESOURCE_ID_INDEX_MASK;
}

bool qge_resource_id_is_valid(qge_resource_id_t id) {
    qge_resource_kind_t kind = qge_resource_id_kind(id);
    return id != QGE_RESOURCE_ID_INVALID &&
           kind > QGE_RESOURCE_NONE &&
           kind < QGE_RESOURCE_KIND_COUNT &&
           qge_resource_id_index(id) != 0;
}

qge_world_t* qge_world_create(void) {
    return (qge_world_t*)calloc(1, sizeof(qge_world_t));
}

void qge_world_clear(qge_world_t* world) {
    if (!world) return;

    world->current_world_id = QGE_RESOURCE_ID_INVALID;
    world->map_hash = 0;
    world->map_name[0] = '\0';
    world->model_count = 0;
    world->plane_count = 0;
    world->node_count = 0;
    world->leaf_count = 0;
    world->surface_count = 0;
    world->texture_count = 0;
    world->lightmap_count = 0;
    world->alias_model_count = 0;
    world->sprite_count = 0;
    world->sound_count = 0;
    world->hud_image_count = 0;
}

void qge_world_free(qge_world_t* world) {
    if (!world) return;
    free(world->models);
    free(world->planes);
    free(world->nodes);
    free(world->leafs);
    free(world->surfaces);
    free(world->textures);
    free(world->lightmaps);
    free(world->alias_models);
    free(world->sprites);
    free(world->sounds);
    free(world->hud_images);
    free(world);
}

qge_resource_id_t qge_world_begin_map(qge_world_t* world,
                                      const char* map_name,
                                      uint64_t map_hash) {
    if (!world) return QGE_RESOURCE_ID_INVALID;

    qge_world_clear(world);
    world->map_revision++;
    qge_copy_name(world->map_name, map_name);
    world->map_hash = map_hash;
    world->current_world_id = qge_resource_id_make(QGE_RESOURCE_WORLD, 1);
    return world->current_world_id;
}

qge_resource_id_t qge_world_current_map_id(const qge_world_t* world) {
    return world ? world->current_world_id : QGE_RESOURCE_ID_INVALID;
}

void qge_world_get_stats(const qge_world_t* world, qge_world_stats_t* stats) {
    if (!stats) return;
    memset(stats, 0, sizeof(*stats));
    if (!world) return;

    stats->current_world_id = world->current_world_id;
    stats->map_revision = world->map_revision;
    qge_copy_name(stats->map_name, world->map_name);
    stats->map_hash = world->map_hash;
    stats->model_count = (uint32_t)world->model_count;
    stats->plane_count = (uint32_t)world->plane_count;
    stats->node_count = (uint32_t)world->node_count;
    stats->leaf_count = (uint32_t)world->leaf_count;
    stats->surface_count = (uint32_t)world->surface_count;
    stats->texture_count = (uint32_t)world->texture_count;
    stats->lightmap_count = (uint32_t)world->lightmap_count;
    stats->alias_model_count = (uint32_t)world->alias_model_count;
    stats->sprite_count = (uint32_t)world->sprite_count;
    stats->sound_count = (uint32_t)world->sound_count;
    stats->hud_image_count = (uint32_t)world->hud_image_count;
    stats->total_resources = stats->model_count +
                             stats->plane_count +
                             stats->node_count +
                             stats->leaf_count +
                             stats->surface_count +
                             stats->texture_count +
                             stats->lightmap_count +
                             stats->alias_model_count +
                             stats->sprite_count +
                             stats->sound_count +
                             stats->hud_image_count;
    if (qge_resource_id_is_valid(world->current_world_id)) {
        stats->total_resources++;
    }
}

#define QGE_REGISTER_REF(fn_name, ref_type, field, count_field, cap_field, kind_value) \
qge_resource_id_t fn_name(qge_world_t* world, const ref_type* ref) { \
    ref_type copy; \
    qge_resource_id_t id; \
    if (!world || !ref) return QGE_RESOURCE_ID_INVALID; \
    if (qge_grow_array((void**)&world->field, &world->cap_field, \
                       world->count_field, sizeof(ref_type)) != 0) { \
        return QGE_RESOURCE_ID_INVALID; \
    } \
    id = qge_resource_id_make(kind_value, (uint32_t)world->count_field + 1u); \
    if (!qge_resource_id_is_valid(id)) return QGE_RESOURCE_ID_INVALID; \
    copy = *ref; \
    copy.id = id; \
    world->field[world->count_field++] = copy; \
    return id; \
}

QGE_REGISTER_REF(qge_world_register_model, qge_model_ref_t,
                 models, model_count, model_capacity, QGE_RESOURCE_BSP_MODEL)
QGE_REGISTER_REF(qge_world_register_plane, qge_plane_ref_t,
                 planes, plane_count, plane_capacity, QGE_RESOURCE_BSP_PLANE)
QGE_REGISTER_REF(qge_world_register_node, qge_node_ref_t,
                 nodes, node_count, node_capacity, QGE_RESOURCE_BSP_NODE)
QGE_REGISTER_REF(qge_world_register_leaf, qge_leaf_ref_t,
                 leafs, leaf_count, leaf_capacity, QGE_RESOURCE_BSP_LEAF)
QGE_REGISTER_REF(qge_world_register_surface, qge_surface_ref_t,
                 surfaces, surface_count, surface_capacity, QGE_RESOURCE_SURFACE)
QGE_REGISTER_REF(qge_world_register_texture, qge_texture_ref_t,
                 textures, texture_count, texture_capacity, QGE_RESOURCE_TEXTURE)
QGE_REGISTER_REF(qge_world_register_lightmap, qge_lightmap_ref_t,
                 lightmaps, lightmap_count, lightmap_capacity, QGE_RESOURCE_LIGHTMAP)
QGE_REGISTER_REF(qge_world_register_alias_model, qge_alias_model_ref_t,
                 alias_models, alias_model_count, alias_model_capacity,
                 QGE_RESOURCE_ALIAS_MODEL)
QGE_REGISTER_REF(qge_world_register_sprite, qge_sprite_ref_t,
                 sprites, sprite_count, sprite_capacity, QGE_RESOURCE_SPRITE)
QGE_REGISTER_REF(qge_world_register_sound, qge_sound_ref_t,
                 sounds, sound_count, sound_capacity, QGE_RESOURCE_SOUND)
QGE_REGISTER_REF(qge_world_register_hud_image, qge_hud_image_ref_t,
                 hud_images, hud_image_count, hud_image_capacity,
                 QGE_RESOURCE_HUD_IMAGE)

#undef QGE_REGISTER_REF

static int qge_lookup_index(qge_resource_id_t id,
                            qge_resource_kind_t expected_kind,
                            size_t count,
                            size_t* out_index) {
    uint32_t index;
    if (!qge_resource_id_is_valid(id) ||
        qge_resource_id_kind(id) != expected_kind) {
        return -1;
    }
    index = qge_resource_id_index(id);
    if (index == 0 || (size_t)index > count) return -1;
    if (out_index) *out_index = (size_t)index - 1u;
    return 0;
}

#define QGE_LOOKUP_REF(fn_name, ref_type, field, count_field, kind_value) \
const ref_type* fn_name(const qge_world_t* world, qge_resource_id_t id) { \
    size_t index; \
    if (!world) return NULL; \
    if (qge_lookup_index(id, kind_value, world->count_field, &index) != 0) { \
        return NULL; \
    } \
    if (world->field[index].id != id) return NULL; \
    return &world->field[index]; \
}

QGE_LOOKUP_REF(qge_world_get_model, qge_model_ref_t,
               models, model_count, QGE_RESOURCE_BSP_MODEL)
QGE_LOOKUP_REF(qge_world_get_plane, qge_plane_ref_t,
               planes, plane_count, QGE_RESOURCE_BSP_PLANE)
QGE_LOOKUP_REF(qge_world_get_node, qge_node_ref_t,
               nodes, node_count, QGE_RESOURCE_BSP_NODE)
QGE_LOOKUP_REF(qge_world_get_leaf, qge_leaf_ref_t,
               leafs, leaf_count, QGE_RESOURCE_BSP_LEAF)
QGE_LOOKUP_REF(qge_world_get_surface, qge_surface_ref_t,
               surfaces, surface_count, QGE_RESOURCE_SURFACE)
QGE_LOOKUP_REF(qge_world_get_texture, qge_texture_ref_t,
               textures, texture_count, QGE_RESOURCE_TEXTURE)
QGE_LOOKUP_REF(qge_world_get_lightmap, qge_lightmap_ref_t,
               lightmaps, lightmap_count, QGE_RESOURCE_LIGHTMAP)
QGE_LOOKUP_REF(qge_world_get_alias_model, qge_alias_model_ref_t,
               alias_models, alias_model_count, QGE_RESOURCE_ALIAS_MODEL)
QGE_LOOKUP_REF(qge_world_get_sprite, qge_sprite_ref_t,
               sprites, sprite_count, QGE_RESOURCE_SPRITE)
QGE_LOOKUP_REF(qge_world_get_sound, qge_sound_ref_t,
               sounds, sound_count, QGE_RESOURCE_SOUND)
QGE_LOOKUP_REF(qge_world_get_hud_image, qge_hud_image_ref_t,
               hud_images, hud_image_count, QGE_RESOURCE_HUD_IMAGE)

#undef QGE_LOOKUP_REF

void qge_frame_snapshot_reset(qge_frame_snapshot_t* snapshot) {
    if (!snapshot) return;
    memset(snapshot, 0, sizeof(*snapshot));
}

void qge_frame_snapshot_begin(qge_frame_snapshot_t* snapshot,
                              uint32_t frame_number,
                              int64_t host_time_msec,
                              int64_t server_time_msec,
                              int64_t client_time_msec) {
    if (!snapshot) return;
    qge_frame_snapshot_reset(snapshot);
    snapshot->frame_number = frame_number;
    snapshot->host_time_msec = host_time_msec;
    snapshot->server_time_msec = server_time_msec;
    snapshot->client_time_msec = client_time_msec;
}

void qge_frame_snapshot_set_camera(qge_frame_snapshot_t* snapshot,
                                   const qge_camera_snapshot_t* camera) {
    if (!snapshot || !camera || snapshot->sealed) return;
    snapshot->camera = *camera;
}

void qge_frame_snapshot_set_world(qge_frame_snapshot_t* snapshot,
                                  qge_resource_id_t world_id,
                                  qge_resource_id_t world_model_id,
                                  uint32_t view_leaf_index,
                                  uint32_t pvs_hash) {
    if (!snapshot || snapshot->sealed) return;
    snapshot->world_id = world_id;
    snapshot->world_model_id = world_model_id;
    snapshot->view_leaf_index = view_leaf_index;
    snapshot->pvs_hash = pvs_hash;
}

void qge_frame_snapshot_seal(qge_frame_snapshot_t* snapshot) {
    if (!snapshot) return;
    snapshot->sealed = true;
}

bool qge_frame_snapshot_is_sealed(const qge_frame_snapshot_t* snapshot) {
    return snapshot ? snapshot->sealed : false;
}

int qge_frame_snapshot_copy(qge_frame_snapshot_t* dst,
                            const qge_frame_snapshot_t* src) {
    if (!dst || !src) return -1;
    memcpy(dst, src, sizeof(*dst));
    return 0;
}

void qge_frame_snapshot_get_stats(const qge_frame_snapshot_t* snapshot,
                                  qge_frame_snapshot_stats_t* stats) {
    if (!stats) return;
    memset(stats, 0, sizeof(*stats));
    if (!snapshot) return;

    stats->visible_surface_count = snapshot->visible_surface_count;
    stats->edict_count = snapshot->edict_count;
    stats->dynamic_light_count = snapshot->dynamic_light_count;
    stats->particle_count = snapshot->particle_count;
    stats->sound_source_count = snapshot->sound_source_count;
    stats->entropy_ref_count = snapshot->entropy_ref_count;
    stats->dropped_visible_surfaces = snapshot->dropped_visible_surfaces;
    stats->dropped_edicts = snapshot->dropped_edicts;
    stats->dropped_dynamic_lights = snapshot->dropped_dynamic_lights;
    stats->dropped_particles = snapshot->dropped_particles;
    stats->dropped_sound_sources = snapshot->dropped_sound_sources;
    stats->dropped_entropy_refs = snapshot->dropped_entropy_refs;
    stats->sealed = snapshot->sealed;
}

#define QGE_SNAPSHOT_ADD(fn_name, item_type, field, count_field, dropped_field, max_count) \
int fn_name(qge_frame_snapshot_t* snapshot, const item_type* item) { \
    if (!snapshot || !item || snapshot->sealed) return -1; \
    if (snapshot->count_field >= (max_count)) { \
        snapshot->dropped_field++; \
        return -1; \
    } \
    snapshot->field[snapshot->count_field++] = *item; \
    return 0; \
}

QGE_SNAPSHOT_ADD(qge_frame_snapshot_add_visible_surface,
                 qge_snapshot_surface_t, visible_surfaces,
                 visible_surface_count, dropped_visible_surfaces,
                 QGE_FRAME_MAX_VISIBLE_SURFACES)
QGE_SNAPSHOT_ADD(qge_frame_snapshot_add_edict,
                 qge_snapshot_edict_t, edicts,
                 edict_count, dropped_edicts,
                 QGE_FRAME_MAX_EDICTS)
QGE_SNAPSHOT_ADD(qge_frame_snapshot_add_dynamic_light,
                 qge_snapshot_light_t, dynamic_lights,
                 dynamic_light_count, dropped_dynamic_lights,
                 QGE_FRAME_MAX_DYNAMIC_LIGHTS)
QGE_SNAPSHOT_ADD(qge_frame_snapshot_add_particle,
                 qge_snapshot_particle_t, particles,
                 particle_count, dropped_particles,
                 QGE_FRAME_MAX_PARTICLES)
QGE_SNAPSHOT_ADD(qge_frame_snapshot_add_sound_source,
                 qge_snapshot_sound_t, sound_sources,
                 sound_source_count, dropped_sound_sources,
                 QGE_FRAME_MAX_SOUND_SOURCES)
QGE_SNAPSHOT_ADD(qge_frame_snapshot_add_entropy_ref,
                 qge_snapshot_entropy_t, entropy_refs,
                 entropy_ref_count, dropped_entropy_refs,
                 QGE_FRAME_MAX_ENTROPY_REFS)

#undef QGE_SNAPSHOT_ADD
