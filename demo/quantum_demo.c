/**
 * @file quantum_demo.c
 * @brief Standalone Quantum Rendering Demo
 *
 * Proves quantum DWT rendering works without Quake integration.
 * Renders a simple 3D scene using quantum wavelet coefficients.
 *
 * Controls:
 * - Arrow keys: Move camera
 * - Q/E: Rotate view
 * - Space: Reset scene
 * - Escape: Quit
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <math.h>
#include <time.h>

#ifdef USE_SDL
#include <SDL2/SDL.h>
#endif

#include "qge.h"

/* ============================================================================
 * Configuration
 * ============================================================================ */

#define WINDOW_WIDTH    640
#define WINDOW_HEIGHT   480
#define RENDER_RES      256     /* Internal quantum render resolution */
#define TARGET_FPS      30
#define FRAME_TIME_MS   (1000 / TARGET_FPS)

/* ============================================================================
 * Scene Definition
 * ============================================================================ */

typedef struct {
    float x, y;         /* Position */
    float width, height;/* Size */
    float brightness;   /* 0.0 - 1.0 */
    float depth;        /* 0.0 (near) - 1.0 (far) */
} wall_t;

typedef struct {
    float x, y;         /* Screen position */
    float size;         /* Sprite size */
    float brightness;   /* 0.0 - 1.0 */
    float depth;        /* 0.0 - 1.0 */
    int type;           /* Sprite type */
} sprite_t;

typedef struct {
    wall_t walls[32];
    int num_walls;
    sprite_t sprites[16];
    int num_sprites;

    /* Camera state */
    float cam_x, cam_y;
    float cam_angle;
} scene_t;

/* ============================================================================
 * Demo State
 * ============================================================================ */

typedef struct {
    qge_context_t* ctx;
    dwt_framebuffer_t* dwt_fb;
    scene_t scene;

    /* Output buffers */
    float* render_buffer;       /* RENDER_RES x RENDER_RES floats */
    uint8_t* display_buffer;    /* WINDOW_WIDTH x WINDOW_HEIGHT RGB */

    /* Timing */
    double frame_time_ms;
    double avg_frame_time_ms;
    int frame_count;

    /* Stats */
    int active_coeffs;
    float sparsity;

    bool running;
} demo_state_t;

/* ============================================================================
 * Scene Setup
 * ============================================================================ */

/**
 * @brief Create a classic FPS-style scene with corridor and enemies
 */
static void scene_init(scene_t* scene) {
    memset(scene, 0, sizeof(scene_t));

    /* Camera at center */
    scene->cam_x = RENDER_RES / 2.0f;
    scene->cam_y = RENDER_RES / 2.0f;
    scene->cam_angle = 0.0f;

    /* Back wall (large, far) */
    scene->walls[0] = (wall_t){
        .x = 20, .y = 20,
        .width = 216, .height = 40,
        .brightness = 0.4f, .depth = 0.9f
    };

    /* Left wall */
    scene->walls[1] = (wall_t){
        .x = 10, .y = 30,
        .width = 30, .height = 180,
        .brightness = 0.5f, .depth = 0.7f
    };

    /* Right wall */
    scene->walls[2] = (wall_t){
        .x = 216, .y = 30,
        .width = 30, .height = 180,
        .brightness = 0.5f, .depth = 0.7f
    };

    /* Floor (bottom wall) */
    scene->walls[3] = (wall_t){
        .x = 40, .y = 200,
        .width = 176, .height = 40,
        .brightness = 0.3f, .depth = 0.5f
    };

    /* Front pillars */
    scene->walls[4] = (wall_t){
        .x = 50, .y = 80,
        .width = 20, .height = 100,
        .brightness = 0.7f, .depth = 0.3f
    };
    scene->walls[5] = (wall_t){
        .x = 186, .y = 80,
        .width = 20, .height = 100,
        .brightness = 0.7f, .depth = 0.3f
    };

    /* Central platform */
    scene->walls[6] = (wall_t){
        .x = 90, .y = 120,
        .width = 76, .height = 30,
        .brightness = 0.6f, .depth = 0.4f
    };

    scene->num_walls = 7;

    /* Enemy sprites */
    scene->sprites[0] = (sprite_t){
        .x = 100, .y = 90,
        .size = 24, .brightness = 0.9f,
        .depth = 0.35f, .type = 0
    };

    scene->sprites[1] = (sprite_t){
        .x = 156, .y = 95,
        .size = 20, .brightness = 0.85f,
        .depth = 0.4f, .type = 1
    };

    /* Item pickups */
    scene->sprites[2] = (sprite_t){
        .x = 128, .y = 130,
        .size = 12, .brightness = 1.0f,
        .depth = 0.42f, .type = 2
    };

    scene->num_sprites = 3;
}

/**
 * @brief Apply camera transform to scene coordinates
 */
static void transform_point(scene_t* scene, float in_x, float in_y,
                            float* out_x, float* out_y) {
    float dx = in_x - scene->cam_x;
    float dy = in_y - scene->cam_y;

    float cos_a = cosf(scene->cam_angle);
    float sin_a = sinf(scene->cam_angle);

    *out_x = dx * cos_a - dy * sin_a + RENDER_RES / 2.0f;
    *out_y = dx * sin_a + dy * cos_a + RENDER_RES / 2.0f;
}

/* ============================================================================
 * Quantum Encoding
 * ============================================================================ */

/**
 * @brief Encode entire scene as wavelet coefficients in quantum state
 */
static void encode_scene(demo_state_t* demo) {
    scene_t* scene = &demo->scene;
    dwt_framebuffer_t* fb = demo->dwt_fb;

    /* Reset framebuffer for new frame */
    qge_dwt_framebuffer_reset(fb);

    /* Encode walls */
    for (int i = 0; i < scene->num_walls; i++) {
        wall_t* wall = &scene->walls[i];

        /* Transform wall position by camera */
        float tx1, ty1, tx2, ty2;
        transform_point(scene, wall->x, wall->y, &tx1, &ty1);
        transform_point(scene, wall->x + wall->width, wall->y + wall->height, &tx2, &ty2);

        /* Sort coordinates */
        if (tx1 > tx2) { float t = tx1; tx1 = tx2; tx2 = t; }
        if (ty1 > ty2) { float t = ty1; ty1 = ty2; ty2 = t; }

        screen_rect_t bounds = {
            .x1 = (int)tx1, .y1 = (int)ty1,
            .x2 = (int)tx2, .y2 = (int)ty2
        };

        qge_encode_wall_dwt(fb, &bounds, wall->brightness, wall->depth);
    }

    /* Encode sprites */
    for (int i = 0; i < scene->num_sprites; i++) {
        sprite_t* sprite = &scene->sprites[i];

        /* Transform sprite position by camera */
        float tx, ty;
        transform_point(scene, sprite->x, sprite->y, &tx, &ty);

        int sx = (int)(tx - sprite->size / 2);
        int sy = (int)(ty - sprite->size / 2);

        qge_encode_sprite_dwt(fb, sx, sy,
                              (int)sprite->size, (int)sprite->size,
                              sprite->brightness, sprite->depth);
    }
}

/* ============================================================================
 * Rendering
 * ============================================================================ */

/**
 * @brief Render scene to float buffer using quantum DWT
 */
static void render_frame(demo_state_t* demo) {
    /* Encode scene geometry as wavelet coefficients */
    encode_scene(demo);

    /* Extract and inverse transform to get pixels */
    qge_dwt_render(demo->dwt_fb, demo->render_buffer);

    /* Update stats */
    demo->active_coeffs = qge_dwt_get_active_count(demo->dwt_fb);
    demo->sparsity = qge_dwt_get_sparsity(demo->dwt_fb);
}

/**
 * @brief Convert float buffer to RGB display buffer with upscaling
 */
static void float_to_rgb(demo_state_t* demo) {
    float* src = demo->render_buffer;
    uint8_t* dst = demo->display_buffer;

    /* Find max value for normalization */
    float max_val = 0.0001f;
    for (int i = 0; i < RENDER_RES * RENDER_RES; i++) {
        float v = fabsf(src[i]);
        if (v > max_val) max_val = v;
    }

    /* Upscale from RENDER_RES to WINDOW dimensions */
    float scale_x = (float)RENDER_RES / WINDOW_WIDTH;
    float scale_y = (float)RENDER_RES / WINDOW_HEIGHT;

    for (int y = 0; y < WINDOW_HEIGHT; y++) {
        for (int x = 0; x < WINDOW_WIDTH; x++) {
            /* Bilinear sample from render buffer */
            float fx = x * scale_x;
            float fy = y * scale_y;
            int ix = (int)fx;
            int iy = (int)fy;

            if (ix >= RENDER_RES - 1) ix = RENDER_RES - 2;
            if (iy >= RENDER_RES - 1) iy = RENDER_RES - 2;

            float dx = fx - ix;
            float dy = fy - iy;

            /* Sample 4 neighbors */
            float v00 = src[iy * RENDER_RES + ix];
            float v10 = src[iy * RENDER_RES + ix + 1];
            float v01 = src[(iy + 1) * RENDER_RES + ix];
            float v11 = src[(iy + 1) * RENDER_RES + ix + 1];

            /* Bilinear interpolation */
            float v = v00 * (1-dx) * (1-dy) +
                     v10 * dx * (1-dy) +
                     v01 * (1-dx) * dy +
                     v11 * dx * dy;

            /* Normalize and apply gamma for better contrast */
            float normalized = fabsf(v) / max_val;
            normalized = powf(normalized, 0.6f);  /* Gamma correction */

            /* Convert to grayscale with slight color tint */
            uint8_t gray = (uint8_t)(normalized * 255.0f);
            int idx = (y * WINDOW_WIDTH + x) * 3;

            /* Slight blue tint for "quantum" aesthetic */
            dst[idx + 0] = (uint8_t)(gray * 0.85f);        /* R */
            dst[idx + 1] = (uint8_t)(gray * 0.90f);        /* G */
            dst[idx + 2] = gray;                           /* B */
        }
    }
}

/* ============================================================================
 * Demo Initialization
 * ============================================================================ */

static demo_state_t* demo_init(void) {
    demo_state_t* demo = calloc(1, sizeof(demo_state_t));
    if (!demo) {
        fprintf(stderr, "Failed to allocate demo state\n");
        return NULL;
    }

    printf("=== Quantum Game Engine Demo ===\n\n");

    /* Initialize QGE */
    printf("Initializing QGE...\n");
    demo->ctx = qge_init();
    if (!demo->ctx) {
        fprintf(stderr, "Failed to initialize QGE\n");
        free(demo);
        return NULL;
    }

    /* Create DWT framebuffer */
    printf("Creating DWT framebuffer (%dx%d, 28 qubits)...\n",
           RENDER_RES, RENDER_RES);

    dwt_config_t config = {
        .mode = DWT_MODE_HAAR,
        .num_levels = 4,
        .base_resolution = RENDER_RES,
        .gpu_reconstruct = false,
        .sparsity_threshold = 0.01f
    };

    demo->dwt_fb = qge_dwt_framebuffer_create(demo->ctx, &config);
    if (!demo->dwt_fb) {
        fprintf(stderr, "Failed to create DWT framebuffer\n");
        qge_shutdown(demo->ctx);
        free(demo);
        return NULL;
    }

    /* Allocate output buffers */
    demo->render_buffer = calloc(RENDER_RES * RENDER_RES, sizeof(float));
    demo->display_buffer = calloc(WINDOW_WIDTH * WINDOW_HEIGHT * 3, sizeof(uint8_t));
    if (!demo->render_buffer || !demo->display_buffer) {
        fprintf(stderr, "Failed to allocate buffers\n");
        qge_dwt_framebuffer_free(demo->dwt_fb);
        qge_shutdown(demo->ctx);
        free(demo->render_buffer);
        free(demo->display_buffer);
        free(demo);
        return NULL;
    }

    /* Initialize scene */
    printf("Setting up scene...\n");
    scene_init(&demo->scene);

    demo->running = true;
    demo->frame_count = 0;
    demo->avg_frame_time_ms = 0;

    printf("\nQuantum renderer ready!\n");
    printf("- Quantum state: 2^28 = 268 million amplitudes\n");
    printf("- Render resolution: %dx%d\n", RENDER_RES, RENDER_RES);
    printf("- Display resolution: %dx%d\n", WINDOW_WIDTH, WINDOW_HEIGHT);
    printf("- DWT levels: %d\n", config.num_levels);
    printf("\n");

    return demo;
}

static void demo_shutdown(demo_state_t* demo) {
    if (!demo) return;

    printf("\nShutting down...\n");
    printf("Average frame time: %.2f ms (%.1f FPS)\n",
           demo->avg_frame_time_ms,
           1000.0 / demo->avg_frame_time_ms);

    qge_dwt_framebuffer_free(demo->dwt_fb);
    qge_shutdown(demo->ctx);
    free(demo->render_buffer);
    free(demo->display_buffer);
    free(demo);
}

/* ============================================================================
 * Input Handling
 * ============================================================================ */

static void handle_input_key(demo_state_t* demo, int key) {
    scene_t* scene = &demo->scene;
    float move_speed = 5.0f;
    float rot_speed = 0.1f;

    switch (key) {
        case 'w': case 'W':
            scene->cam_y -= move_speed * cosf(scene->cam_angle);
            scene->cam_x += move_speed * sinf(scene->cam_angle);
            break;
        case 's': case 'S':
            scene->cam_y += move_speed * cosf(scene->cam_angle);
            scene->cam_x -= move_speed * sinf(scene->cam_angle);
            break;
        case 'a': case 'A':
            scene->cam_x -= move_speed * cosf(scene->cam_angle);
            scene->cam_y -= move_speed * sinf(scene->cam_angle);
            break;
        case 'd': case 'D':
            scene->cam_x += move_speed * cosf(scene->cam_angle);
            scene->cam_y += move_speed * sinf(scene->cam_angle);
            break;
        case 'q': case 'Q':
            scene->cam_angle -= rot_speed;
            break;
        case 'e': case 'E':
            scene->cam_angle += rot_speed;
            break;
        case ' ':
            scene_init(scene);
            printf("Scene reset\n");
            break;
        case 27: /* Escape */
            demo->running = false;
            break;
    }
}

/* ============================================================================
 * SDL2 Version (Interactive Window)
 * ============================================================================ */

#ifdef USE_SDL

static int demo_run_sdl(demo_state_t* demo) {
    /* Initialize SDL */
    if (SDL_Init(SDL_INIT_VIDEO) < 0) {
        fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError());
        return 1;
    }

    SDL_Window* window = SDL_CreateWindow(
        "Quantum Game Engine Demo - Press ESC to quit",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        WINDOW_WIDTH, WINDOW_HEIGHT,
        SDL_WINDOW_SHOWN
    );
    if (!window) {
        fprintf(stderr, "SDL_CreateWindow failed: %s\n", SDL_GetError());
        SDL_Quit();
        return 1;
    }

    SDL_Renderer* renderer = SDL_CreateRenderer(window, -1,
        SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!renderer) {
        fprintf(stderr, "SDL_CreateRenderer failed: %s\n", SDL_GetError());
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 1;
    }

    SDL_Texture* texture = SDL_CreateTexture(renderer,
        SDL_PIXELFORMAT_RGB24,
        SDL_TEXTUREACCESS_STREAMING,
        WINDOW_WIDTH, WINDOW_HEIGHT);
    if (!texture) {
        fprintf(stderr, "SDL_CreateTexture failed: %s\n", SDL_GetError());
        SDL_DestroyRenderer(renderer);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 1;
    }

    printf("\nControls:\n");
    printf("  WASD - Move camera\n");
    printf("  Q/E  - Rotate view\n");
    printf("  Space - Reset scene\n");
    printf("  ESC  - Quit\n\n");

    Uint32 last_time = SDL_GetTicks();

    while (demo->running) {
        Uint32 frame_start = SDL_GetTicks();

        /* Handle events */
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            switch (event.type) {
                case SDL_QUIT:
                    demo->running = false;
                    break;
                case SDL_KEYDOWN:
                    handle_input_key(demo, event.key.keysym.sym);
                    break;
            }
        }

        /* Continuous movement with held keys */
        const Uint8* keys = SDL_GetKeyboardState(NULL);
        if (keys[SDL_SCANCODE_W]) handle_input_key(demo, 'w');
        if (keys[SDL_SCANCODE_S]) handle_input_key(demo, 's');
        if (keys[SDL_SCANCODE_A]) handle_input_key(demo, 'a');
        if (keys[SDL_SCANCODE_D]) handle_input_key(demo, 'd');
        if (keys[SDL_SCANCODE_Q]) handle_input_key(demo, 'q');
        if (keys[SDL_SCANCODE_E]) handle_input_key(demo, 'e');

        /* Render frame */
        render_frame(demo);
        float_to_rgb(demo);

        /* Update texture */
        SDL_UpdateTexture(texture, NULL, demo->display_buffer,
                         WINDOW_WIDTH * 3);
        SDL_RenderClear(renderer);
        SDL_RenderCopy(renderer, texture, NULL, NULL);
        SDL_RenderPresent(renderer);

        /* Calculate frame time */
        Uint32 frame_end = SDL_GetTicks();
        demo->frame_time_ms = frame_end - frame_start;
        demo->frame_count++;

        /* Update running average */
        demo->avg_frame_time_ms =
            demo->avg_frame_time_ms * 0.95 + demo->frame_time_ms * 0.05;

        /* Print stats periodically */
        if (demo->frame_count % 30 == 0) {
            printf("\rFrame %4d | %.1f ms (%.0f FPS) | %d coeffs (%.1f%% sparsity)   ",
                   demo->frame_count,
                   demo->avg_frame_time_ms,
                   1000.0 / demo->avg_frame_time_ms,
                   demo->active_coeffs,
                   demo->sparsity * 100.0f);
            fflush(stdout);
        }

        /* Frame rate limiting */
        Uint32 elapsed = frame_end - frame_start;
        if (elapsed < FRAME_TIME_MS) {
            SDL_Delay(FRAME_TIME_MS - elapsed);
        }
    }

    printf("\n");

    SDL_DestroyTexture(texture);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();

    return 0;
}

#endif /* USE_SDL */

/* ============================================================================
 * Headless Version (PPM Output)
 * ============================================================================ */

static int demo_run_headless(demo_state_t* demo) {
    printf("\nRunning headless demo (no SDL)...\n");
    printf("Will render 10 frames and save to PPM files.\n\n");

    for (int frame = 0; frame < 10; frame++) {
        clock_t start = clock();

        /* Animate camera */
        demo->scene.cam_angle = frame * 0.1f;

        /* Render */
        render_frame(demo);
        float_to_rgb(demo);

        clock_t end = clock();
        demo->frame_time_ms = (double)(end - start) * 1000.0 / CLOCKS_PER_SEC;
        demo->avg_frame_time_ms =
            demo->avg_frame_time_ms * 0.9 + demo->frame_time_ms * 0.1;

        /* Save PPM */
        char filename[64];
        snprintf(filename, sizeof(filename), "quantum_frame_%02d.ppm", frame);

        FILE* f = fopen(filename, "wb");
        if (f) {
            fprintf(f, "P6\n%d %d\n255\n", WINDOW_WIDTH, WINDOW_HEIGHT);
            fwrite(demo->display_buffer, 1, WINDOW_WIDTH * WINDOW_HEIGHT * 3, f);
            fclose(f);
        }

        printf("Frame %2d: %.1f ms | %d coeffs (%.1f%% sparse) | Saved %s\n",
               frame,
               demo->frame_time_ms,
               demo->active_coeffs,
               demo->sparsity * 100.0f,
               filename);
    }

    printf("\nDone! Open quantum_frame_XX.ppm files to see results.\n");
    return 0;
}

/* ============================================================================
 * Main
 * ============================================================================ */

int main(int argc, char* argv[]) {
    (void)argc;
    (void)argv;

    demo_state_t* demo = demo_init();
    if (!demo) {
        return 1;
    }

    int result;

#ifdef USE_SDL
    result = demo_run_sdl(demo);
#else
    result = demo_run_headless(demo);
#endif

    demo_shutdown(demo);
    return result;
}
