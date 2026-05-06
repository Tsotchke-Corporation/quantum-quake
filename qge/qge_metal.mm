/**
 * @file qge_metal.mm
 * @brief Metal GPU acceleration implementation for QGE
 *
 * Objective-C++ implementation of GPU-accelerated quantum rendering.
 */

#import <Metal/Metal.h>
#import <Foundation/Foundation.h>
#include <complex.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/* Include Moonlab Metal header */
#include "optimization/gpu_metal.h"

/* Include our header after Moonlab */
#include "qge_metal.h"

/* ============================================================================
 * METAL SHADER SOURCE
 * ============================================================================ */

static const char* qge_metal_shader_source = R"(
#include <metal_stdlib>
using namespace metal;

/* Complex number as float2 (real, imag) */
typedef float2 cfloat;

/* Helper: squared magnitude of complex number */
inline float mag_squared(cfloat c) {
    return c.x * c.x + c.y * c.y;
}

/* ============================================================================
 * KERNEL: Screen Probability Marginalization
 * ============================================================================
 *
 * Extracts 64×64 screen probability grid from 2^28 quantum state.
 *
 * Layout: position in lower 12 bits (6 bits X, 6 bits Y)
 * Each pixel sums |amp|² over all 2^16 states with matching (x,y)
 *
 * Threadgroup: 256 threads per pixel
 * Each thread handles 256 states (256 * 256 = 65536 = 2^16)
 */
kernel void marginalize_screen_probs(
    device const cfloat* amplitudes [[buffer(0)]],
    device float* probabilities [[buffer(1)]],
    constant uint& num_qubits [[buffer(2)]],
    constant uint& screen_bits [[buffer(3)]],
    uint2 gid [[thread_position_in_grid]],
    uint tid [[thread_index_in_threadgroup]],
    uint2 tgid [[threadgroup_position_in_grid]]
) {
    /* Screen position from threadgroup ID */
    uint screen_x = tgid.x;
    uint screen_y = tgid.y;
    uint screen_xy = (screen_y << 6) | screen_x;  /* Lower 12 bits */

    /* Non-position qubits */
    uint non_pos_bits = num_qubits - screen_bits;
    uint states_per_pixel = 1u << non_pos_bits;  /* 2^16 = 65536 */

    /* Each thread sums a portion of states */
    uint threads_per_group = 256;
    uint states_per_thread = states_per_pixel / threads_per_group;

    float local_sum = 0.0f;

    /* Sum |amplitude|² for this thread's states */
    uint start = tid * states_per_thread;
    uint end = start + states_per_thread;

    for (uint offset = start; offset < end; offset++) {
        uint state_idx = (offset << screen_bits) | screen_xy;
        cfloat amp = amplitudes[state_idx];
        local_sum += mag_squared(amp);
    }

    /* Threadgroup reduction */
    threadgroup float shared_sum[256];
    shared_sum[tid] = local_sum;
    threadgroup_barrier(mem_flags::mem_threadgroup);

    /* Parallel reduction */
    for (uint stride = 128; stride > 0; stride >>= 1) {
        if (tid < stride) {
            shared_sum[tid] += shared_sum[tid + stride];
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
    }

    /* Thread 0 writes final result */
    if (tid == 0) {
        uint out_idx = screen_y * 64 + screen_x;
        probabilities[out_idx] = shared_sum[0];
    }
}

/* ============================================================================
 * KERNEL: Sparse Coefficient Extraction
 * ============================================================================
 *
 * Scans quantum state and extracts significant DWT coefficients.
 * Uses atomic counter for output indexing.
 */
kernel void extract_sparse_coeffs(
    device const cfloat* amplitudes [[buffer(0)]],
    device uint64_t* indices [[buffer(1)]],
    device float* values [[buffer(2)]],
    device atomic_uint* counter [[buffer(3)]],
    constant uint& state_dim [[buffer(4)]],
    constant float& threshold [[buffer(5)]],
    constant uint& max_coeffs [[buffer(6)]],
    uint gid [[thread_position_in_grid]]
) {
    if (gid >= state_dim) return;

    cfloat amp = amplitudes[gid];
    float mag = sqrt(mag_squared(amp));

    if (mag > threshold) {
        uint idx = atomic_fetch_add_explicit(counter, 1, memory_order_relaxed);
        if (idx < max_coeffs) {
            indices[idx] = gid;
            values[idx] = mag;
        }
    }
}

/* ============================================================================
 * KERNEL: Inverse Haar DWT (Single Level)
 * ============================================================================
 *
 * Reconstructs spatial image from wavelet coefficients.
 * Processes one level of the DWT pyramid.
 *
 * Input: LL, HL, LH, HH subbands at level L
 * Output: Approximation at level L-1
 */
kernel void haar_inverse_level(
    device const float* input [[buffer(0)]],
    device float* output [[buffer(1)]],
    constant uint& width [[buffer(2)]],
    constant uint& height [[buffer(3)]],
    uint2 gid [[thread_position_in_grid]]
) {
    uint x = gid.x;
    uint y = gid.y;
    uint half_w = width / 2;
    uint half_h = height / 2;

    if (x >= half_w || y >= half_h) return;

    /* Read four subband values */
    float ll = input[y * width + x];                      /* LL */
    float hl = input[y * width + (half_w + x)];          /* HL */
    float lh = input[(half_h + y) * width + x];          /* LH */
    float hh = input[(half_h + y) * width + (half_w + x)]; /* HH */

    /* Haar inverse: reconstruct 2×2 block */
    uint out_x = x * 2;
    uint out_y = y * 2;
    uint out_w = width;

    /* 2D inverse Haar:
     * [a b]   [ll+hl+lh+hh  ll-hl+lh-hh]
     * [c d] = [ll+hl-lh-hh  ll-hl-lh+hh] × 0.5
     */
    output[out_y * out_w + out_x]         = (ll + hl + lh + hh) * 0.5f;
    output[out_y * out_w + out_x + 1]     = (ll - hl + lh - hh) * 0.5f;
    output[(out_y + 1) * out_w + out_x]   = (ll + hl - lh - hh) * 0.5f;
    output[(out_y + 1) * out_w + out_x + 1] = (ll - hl - lh + hh) * 0.5f;
}

/* ============================================================================
 * KERNEL: Direct Spatial Rendering
 * ============================================================================
 *
 * Renders DWT coefficients directly to spatial positions.
 * Bypasses full inverse DWT for speed.
 */
kernel void render_direct_spatial(
    device const uint64_t* coeff_indices [[buffer(0)]],
    device const float* coeff_values [[buffer(1)]],
    device float* output [[buffer(2)]],
    constant uint& num_coeffs [[buffer(3)]],
    constant uint& base_res [[buffer(4)]],
    uint gid [[thread_position_in_grid]]
) {
    if (gid >= num_coeffs) return;

    uint64_t index = coeff_indices[gid];
    float value = coeff_values[gid];

    /* Decode DWT index:
     * bits 0-7: cy (coefficient Y)
     * bits 8-15: cx (coefficient X)
     * bits 16-17: subband (LL=0, HL=1, LH=2, HH=3)
     * bits 18-20: level (0-7)
     */
    uint cy = index & 0xFF;
    uint cx = (index >> 8) & 0xFF;
    uint subband = (index >> 16) & 0x3;
    uint level = (index >> 18) & 0x7;

    uint scale = 1u << level;
    uint px = cx * scale;
    uint py = cy * scale;
    float intensity = fabs(value);

    /* Render block based on subband */
    for (uint dy = 0; dy < scale && (py + dy) < base_res; dy++) {
        for (uint dx = 0; dx < scale && (px + dx) < base_res; dx++) {
            uint idx = (py + dy) * base_res + (px + dx);

            float contrib = 0.0f;
            switch (subband) {
                case 0: contrib = intensity * 0.5f; break;  /* LL */
                case 1: contrib = (dx < scale/2) ? intensity : 0; break;  /* HL */
                case 2: contrib = (dy < scale/2) ? intensity : 0; break;  /* LH */
                case 3: contrib = (dx < scale/2 && dy < scale/2) ? intensity * 0.7f : 0; break; /* HH */
            }

            /* Atomic add for thread safety */
            atomic_fetch_add_explicit((device atomic_float*)&output[idx], contrib, memory_order_relaxed);
        }
    }
}

/* ============================================================================
 * KERNEL: Float to RGB Conversion
 * ============================================================================ */
kernel void float_to_rgb(
    device const float* input [[buffer(0)]],
    device uchar* output [[buffer(1)]],
    constant uint& width [[buffer(2)]],
    constant uint& height [[buffer(3)]],
    constant float& scale [[buffer(4)]],
    uint2 gid [[thread_position_in_grid]]
) {
    if (gid.x >= width || gid.y >= height) return;

    uint idx = gid.y * width + gid.x;
    float val = input[idx] * scale;

    /* Clamp to [0, 1] */
    val = clamp(val, 0.0f, 1.0f);

    /* Apply gamma correction */
    val = pow(val, 0.45f);

    uchar pixel = (uchar)(val * 255.0f);

    /* RGB output (grayscale) */
    uint out_idx = idx * 3;
    output[out_idx + 0] = pixel;
    output[out_idx + 1] = pixel;
    output[out_idx + 2] = pixel;
}

)";

/* ============================================================================
 * INTERNAL STRUCTURES
 * ============================================================================ */

struct qge_metal_internal {
    id<MTLDevice> device;
    id<MTLCommandQueue> commandQueue;
    id<MTLLibrary> library;

    /* Pipeline states */
    id<MTLComputePipelineState> marginalizeScreenPipeline;
    id<MTLComputePipelineState> extractSparseCoeffsPipeline;
    id<MTLComputePipelineState> haarInverseLevelPipeline;
    id<MTLComputePipelineState> renderDirectSpatialPipeline;
    id<MTLComputePipelineState> floatToRgbPipeline;

    /* Timing */
    NSDate* lastStartTime;
    double lastExecutionTime;
};

/* ============================================================================
 * INITIALIZATION
 * ============================================================================ */

extern "C" qge_metal_ctx_t* qge_metal_init(int num_qubits, int screen_res) {
    @autoreleasepool {
        /* Check Metal availability */
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        if (!device) {
            fprintf(stderr, "[QGE Metal] No Metal device available\n");
            return NULL;
        }

        /* Allocate context */
        qge_metal_ctx_t* ctx = (qge_metal_ctx_t*)calloc(1, sizeof(qge_metal_ctx_t));
        if (!ctx) return NULL;

        struct qge_metal_internal* internal = new qge_metal_internal();
        internal->device = device;
        internal->commandQueue = [device newCommandQueue];

        /* Compile shaders */
        NSError* error = nil;
        NSString* source = [NSString stringWithUTF8String:qge_metal_shader_source];
        id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];

        if (!library) {
            fprintf(stderr, "[QGE Metal] Shader compile error: %s\n",
                    [[error localizedDescription] UTF8String]);
            delete internal;
            free(ctx);
            return NULL;
        }

        internal->library = library;

        /* Create pipeline states */
        id<MTLFunction> marginalizeFn = [library newFunctionWithName:@"marginalize_screen_probs"];
        id<MTLFunction> extractSparseFn = [library newFunctionWithName:@"extract_sparse_coeffs"];
        id<MTLFunction> haarInverseFn = [library newFunctionWithName:@"haar_inverse_level"];
        id<MTLFunction> renderDirectFn = [library newFunctionWithName:@"render_direct_spatial"];
        id<MTLFunction> floatToRgbFn = [library newFunctionWithName:@"float_to_rgb"];

        internal->marginalizeScreenPipeline = [device newComputePipelineStateWithFunction:marginalizeFn error:&error];
        internal->extractSparseCoeffsPipeline = [device newComputePipelineStateWithFunction:extractSparseFn error:&error];
        internal->haarInverseLevelPipeline = [device newComputePipelineStateWithFunction:haarInverseFn error:&error];
        internal->renderDirectSpatialPipeline = [device newComputePipelineStateWithFunction:renderDirectFn error:&error];
        internal->floatToRgbPipeline = [device newComputePipelineStateWithFunction:floatToRgbFn error:&error];

        if (error) {
            fprintf(stderr, "[QGE Metal] Pipeline creation error: %s\n",
                    [[error localizedDescription] UTF8String]);
        }

        /* Initialize Moonlab Metal context for interop */
        ctx->metal_ctx = metal_compute_init();

        ctx->num_qubits = num_qubits;
        ctx->screen_res = screen_res;
        ctx->position_qubits = (int)(2 * log2(screen_res));  /* 12 for 64×64 */
        ctx->initialized = true;

        /* Store internal pointer for GPU dispatch access */
        ctx->internal_ptr = (void*)internal;

        printf("[QGE Metal] Initialized: %d qubits, %dx%d screen\n",
               num_qubits, screen_res, screen_res);
        printf("[QGE Metal] Device: %s\n", [[device name] UTF8String]);
        printf("[QGE Metal] Position qubits: %d, non-position: %d\n",
               ctx->position_qubits, num_qubits - ctx->position_qubits);

        /* Allocate GPU buffers */
        size_t state_size = (1ULL << num_qubits) * sizeof(float) * 2;  /* Complex as 2 floats */
        size_t prob_size = screen_res * screen_res * sizeof(float);

        ctx->amplitude_buffer = metal_buffer_create(ctx->metal_ctx, state_size);
        ctx->probability_buffer = metal_buffer_create(ctx->metal_ctx, prob_size);
        ctx->output_buffer = metal_buffer_create(ctx->metal_ctx, screen_res * screen_res * 3);

        printf("[QGE Metal] Allocated %.1f GB for quantum state\n",
               state_size / (1024.0 * 1024.0 * 1024.0));

        return ctx;
    }
}

extern "C" void qge_metal_free(qge_metal_ctx_t* ctx) {
    if (!ctx) return;

    if (ctx->amplitude_buffer) metal_buffer_free(ctx->amplitude_buffer);
    if (ctx->probability_buffer) metal_buffer_free(ctx->probability_buffer);
    if (ctx->dwt_coeff_buffer) metal_buffer_free(ctx->dwt_coeff_buffer);
    if (ctx->output_buffer) metal_buffer_free(ctx->output_buffer);
    if (ctx->metal_ctx) metal_compute_free(ctx->metal_ctx);

    if (ctx->internal_ptr) {
        delete (struct qge_metal_internal*)ctx->internal_ptr;
        ctx->internal_ptr = NULL;
    }

    free(ctx);
}

extern "C" bool qge_metal_available(void) {
    return metal_is_available() != 0;
}

/* ============================================================================
 * MARGINALIZATION (Key operation!)
 * ============================================================================ */

/**
 * @brief Convert double _Complex amplitudes to float2 for GPU processing
 *
 * Converts the Moonlab quantum state (double _Complex, 16 bytes/element) to
 * Metal-compatible float2 (8 bytes/element). On Apple Silicon unified memory,
 * the GPU can access this directly without a copy.
 */
static void convert_amplitudes_to_float2(
    const double _Complex* src,
    float* dst_float2,
    uint64_t count
) {
    const double* src_d = (const double*)src;
    for (uint64_t i = 0; i < count; i++) {
        dst_float2[i * 2]     = (float)src_d[i * 2];      /* real */
        dst_float2[i * 2 + 1] = (float)src_d[i * 2 + 1];  /* imag */
    }
}

extern "C" int qge_metal_marginalize_screen(
    qge_metal_ctx_t* ctx,
    const double _Complex* amplitudes,
    float* probabilities
) {
    if (!ctx || !amplitudes || !probabilities) return -1;

    uint64_t state_dim = 1ULL << ctx->num_qubits;
    int screen_res = ctx->screen_res;

    /* Try GPU path: convert amplitudes to float2, then dispatch GPU kernel */
    if (ctx->internal_ptr && ctx->amplitude_buffer) {
        float* gpu_amps = (float*)metal_buffer_contents(ctx->amplitude_buffer);
        if (gpu_amps) {
            /* Convert double _Complex → float2 (unified memory, GPU reads directly) */
            convert_amplitudes_to_float2(amplitudes, gpu_amps, state_dim);

            /* Run GPU marginalization */
            int result = qge_metal_marginalize_screen_gpu(ctx);
            if (result == 0) {
                /* Copy results from GPU probability buffer */
                float* gpu_probs = (float*)metal_buffer_contents(ctx->probability_buffer);
                if (gpu_probs) {
                    memcpy(probabilities, gpu_probs,
                           screen_res * screen_res * sizeof(float));
                    return 0;
                }
            }
        }
        /* Fall through to CPU if GPU fails */
        fprintf(stderr, "[QGE Metal] GPU marginalization failed, using CPU fallback\n");
    }

    /* CPU fallback: iterate over all 2^N amplitudes */
    int screen_bits = ctx->position_qubits;
    memset(probabilities, 0, screen_res * screen_res * sizeof(float));

    uint64_t pos_mask = (1ULL << screen_bits) - 1;
    const double* amp_data = (const double*)amplitudes;

    for (uint64_t i = 0; i < state_dim; i++) {
        uint64_t screen_idx = i & pos_mask;
        double real = amp_data[i * 2];
        double imag = amp_data[i * 2 + 1];
        probabilities[screen_idx] += (float)(real * real + imag * imag);
    }

    return 0;
}

extern "C" int qge_metal_marginalize_screen_gpu(qge_metal_ctx_t* ctx) {
    if (!ctx || !ctx->internal_ptr || !ctx->amplitude_buffer || !ctx->probability_buffer)
        return -1;

    @autoreleasepool {
        struct qge_metal_internal* internal = (struct qge_metal_internal*)ctx->internal_ptr;
        if (!internal->marginalizeScreenPipeline) return -1;

        NSDate* startTime = [NSDate date];

        /* Create command buffer and compute encoder */
        id<MTLCommandBuffer> cmdBuf = [internal->commandQueue commandBuffer];
        if (!cmdBuf) return -1;

        id<MTLComputeCommandEncoder> encoder = [cmdBuf computeCommandEncoder];
        if (!encoder) return -1;

        /* Get raw Metal buffers from Moonlab wrappers
         * metal_buffer_contents() returns the CPU-accessible pointer for unified memory.
         * We need the actual MTL buffer objects for the compute encoder.
         * Since Moonlab's metal_buffer_t wraps an id<MTLBuffer>, we access it directly.
         */

        /* Use Moonlab buffer contents as the backing store.
         * For Apple Silicon unified memory, the GPU reads directly from this memory. */
        uint32_t num_qubits = (uint32_t)ctx->num_qubits;
        uint32_t screen_bits = (uint32_t)ctx->position_qubits;
        uint32_t screen_res = (uint32_t)ctx->screen_res;
        uint64_t state_dim = 1ULL << num_qubits;

        /* Create temporary Metal buffers with the data pointers
         * The amplitude_buffer should already contain float2 data after conversion */
        size_t amp_size = state_dim * sizeof(float) * 2;  /* float2 per amplitude */
        size_t prob_size = screen_res * screen_res * sizeof(float);

        id<MTLBuffer> ampBuf = [internal->device newBufferWithBytesNoCopy:
            metal_buffer_contents(ctx->amplitude_buffer)
            length:amp_size
            options:MTLResourceStorageModeShared
            deallocator:nil];

        id<MTLBuffer> probBuf = [internal->device newBufferWithBytesNoCopy:
            metal_buffer_contents(ctx->probability_buffer)
            length:prob_size
            options:MTLResourceStorageModeShared
            deallocator:nil];

        if (!ampBuf || !probBuf) {
            [encoder endEncoding];
            return -1;
        }

        /* Zero the probability buffer */
        memset(metal_buffer_contents(ctx->probability_buffer), 0, prob_size);

        /* Set pipeline and buffers */
        [encoder setComputePipelineState:internal->marginalizeScreenPipeline];
        [encoder setBuffer:ampBuf offset:0 atIndex:0];
        [encoder setBuffer:probBuf offset:0 atIndex:1];
        [encoder setBytes:&num_qubits length:sizeof(uint32_t) atIndex:2];
        [encoder setBytes:&screen_bits length:sizeof(uint32_t) atIndex:3];

        /* Dispatch: one threadgroup per pixel (64×64 = 4096 threadgroups)
         * Each threadgroup has 256 threads for parallel reduction */
        MTLSize threadgroupSize = MTLSizeMake(256, 1, 1);
        MTLSize gridSize = MTLSizeMake(screen_res, screen_res, 1);
        [encoder dispatchThreadgroups:gridSize threadsPerThreadgroup:threadgroupSize];

        [encoder endEncoding];
        [cmdBuf commit];
        [cmdBuf waitUntilCompleted];

        /* Record timing */
        ctx->last_marginalize_time_ms = -[startTime timeIntervalSinceNow] * 1000.0;

        return 0;
    }
}

/* ============================================================================
 * INVERSE DWT
 * ============================================================================ */

extern "C" int qge_metal_inverse_dwt(
    qge_metal_ctx_t* ctx,
    const float* coefficients,
    float* output,
    int num_levels
) {
    if (!ctx || !coefficients || !output || num_levels <= 0) return -1;

    struct qge_metal_internal* internal = (struct qge_metal_internal*)ctx->internal_ptr;
    if (!internal || !internal->haarInverseLevelPipeline) return -1;

    @autoreleasepool {
        NSDate* startTime = [NSDate date];

        int base_res = ctx->screen_res;
        size_t buf_size = base_res * base_res * sizeof(float);

        /* Create double-buffered GPU storage for ping-pong */
        id<MTLBuffer> bufA = [internal->device newBufferWithLength:buf_size
            options:MTLResourceStorageModeShared];
        id<MTLBuffer> bufB = [internal->device newBufferWithLength:buf_size
            options:MTLResourceStorageModeShared];

        if (!bufA || !bufB) return -1;

        /* Copy input coefficients to buffer A */
        memcpy([bufA contents], coefficients, buf_size);

        /* Reconstruct from coarsest to finest level
         * Each level doubles the resolution */
        id<MTLBuffer> inputBuf = bufA;
        id<MTLBuffer> outputBuf = bufB;

        for (int level = num_levels - 1; level >= 0; level--) {
            uint32_t size_at_level = (uint32_t)(base_res >> level);
            uint32_t half_w = size_at_level / 2;
            uint32_t half_h = size_at_level / 2;

            if (half_w == 0 || half_h == 0) continue;

            /* Copy current input to output (we modify in-place conceptually,
             * but the kernel reads from input and writes to a new region) */
            memcpy([outputBuf contents], [inputBuf contents], buf_size);

            id<MTLCommandBuffer> cmdBuf = [internal->commandQueue commandBuffer];
            id<MTLComputeCommandEncoder> encoder = [cmdBuf computeCommandEncoder];

            [encoder setComputePipelineState:internal->haarInverseLevelPipeline];
            [encoder setBuffer:inputBuf offset:0 atIndex:0];
            [encoder setBuffer:outputBuf offset:0 atIndex:1];
            [encoder setBytes:&size_at_level length:sizeof(uint32_t) atIndex:2];
            [encoder setBytes:&size_at_level length:sizeof(uint32_t) atIndex:3];

            /* Dispatch: one thread per 2×2 output block */
            NSUInteger tgWidth = 16;
            NSUInteger tgHeight = 16;
            MTLSize threadgroupSize = MTLSizeMake(tgWidth, tgHeight, 1);
            MTLSize gridSize = MTLSizeMake(
                (half_w + tgWidth - 1) / tgWidth,
                (half_h + tgHeight - 1) / tgHeight,
                1);
            [encoder dispatchThreadgroups:gridSize threadsPerThreadgroup:threadgroupSize];

            [encoder endEncoding];
            [cmdBuf commit];
            [cmdBuf waitUntilCompleted];

            /* Swap buffers for next level */
            id<MTLBuffer> tmp = inputBuf;
            inputBuf = outputBuf;
            outputBuf = tmp;
        }

        /* Copy final result to output */
        memcpy(output, [inputBuf contents], buf_size);

        ctx->last_idwt_time_ms = -[startTime timeIntervalSinceNow] * 1000.0;
        return 0;
    }
}

/* ============================================================================
 * SPARSE COEFFICIENT EXTRACTION
 * ============================================================================ */

extern "C" int qge_metal_extract_sparse_coeffs(
    qge_metal_ctx_t* ctx,
    const double _Complex* amplitudes,
    uint64_t* indices,
    float* values,
    int max_coeffs,
    float threshold,
    int* num_extracted
) {
    if (!ctx || !amplitudes || !indices || !values || !num_extracted) return -1;

    struct qge_metal_internal* internal = (struct qge_metal_internal*)ctx->internal_ptr;
    if (!internal || !internal->extractSparseCoeffsPipeline) {
        /* CPU fallback: linear scan */
        uint64_t state_dim = 1ULL << ctx->num_qubits;
        const double* amp_data = (const double*)amplitudes;
        int count = 0;

        for (uint64_t i = 0; i < state_dim && count < max_coeffs; i++) {
            double real = amp_data[i * 2];
            double imag = amp_data[i * 2 + 1];
            float mag = (float)sqrt(real * real + imag * imag);
            if (mag > threshold) {
                indices[count] = i;
                values[count] = mag;
                count++;
            }
        }

        *num_extracted = count;
        return 0;
    }

    @autoreleasepool {
        uint64_t state_dim = 1ULL << ctx->num_qubits;

        /* Convert amplitudes to float2 in the GPU amplitude buffer */
        float* gpu_amps = (float*)metal_buffer_contents(ctx->amplitude_buffer);
        if (!gpu_amps) return -1;
        convert_amplitudes_to_float2(amplitudes, gpu_amps, state_dim);

        /* Allocate output buffers on GPU */
        size_t indices_size = max_coeffs * sizeof(uint64_t);
        size_t values_size = max_coeffs * sizeof(float);
        size_t counter_size = sizeof(uint32_t);

        id<MTLBuffer> ampBuf = [internal->device newBufferWithBytesNoCopy:
            gpu_amps length:state_dim * sizeof(float) * 2
            options:MTLResourceStorageModeShared deallocator:nil];

        id<MTLBuffer> indicesBuf = [internal->device newBufferWithLength:indices_size
            options:MTLResourceStorageModeShared];
        id<MTLBuffer> valuesBuf = [internal->device newBufferWithLength:values_size
            options:MTLResourceStorageModeShared];
        id<MTLBuffer> counterBuf = [internal->device newBufferWithLength:counter_size
            options:MTLResourceStorageModeShared];

        if (!ampBuf || !indicesBuf || !valuesBuf || !counterBuf) return -1;

        /* Zero the atomic counter */
        memset([counterBuf contents], 0, counter_size);

        uint32_t state_dim_u32 = (uint32_t)state_dim;
        uint32_t max_coeffs_u32 = (uint32_t)max_coeffs;

        /* Create command buffer */
        id<MTLCommandBuffer> cmdBuf = [internal->commandQueue commandBuffer];
        id<MTLComputeCommandEncoder> encoder = [cmdBuf computeCommandEncoder];

        [encoder setComputePipelineState:internal->extractSparseCoeffsPipeline];
        [encoder setBuffer:ampBuf offset:0 atIndex:0];
        [encoder setBuffer:indicesBuf offset:0 atIndex:1];
        [encoder setBuffer:valuesBuf offset:0 atIndex:2];
        [encoder setBuffer:counterBuf offset:0 atIndex:3];
        [encoder setBytes:&state_dim_u32 length:sizeof(uint32_t) atIndex:4];
        [encoder setBytes:&threshold length:sizeof(float) atIndex:5];
        [encoder setBytes:&max_coeffs_u32 length:sizeof(uint32_t) atIndex:6];

        /* Dispatch: one thread per state, up to 268M threads
         * Use threadgroups of 256, so ~1M threadgroups */
        NSUInteger threadgroupWidth = internal->extractSparseCoeffsPipeline.maxTotalThreadsPerThreadgroup;
        if (threadgroupWidth > 256) threadgroupWidth = 256;

        MTLSize threadgroupSize = MTLSizeMake(threadgroupWidth, 1, 1);
        MTLSize gridSize = MTLSizeMake((state_dim + threadgroupWidth - 1) / threadgroupWidth, 1, 1);
        [encoder dispatchThreadgroups:gridSize threadsPerThreadgroup:threadgroupSize];

        [encoder endEncoding];
        [cmdBuf commit];
        [cmdBuf waitUntilCompleted];

        /* Read back results */
        uint32_t extracted_count = *(uint32_t*)[counterBuf contents];
        if (extracted_count > (uint32_t)max_coeffs) extracted_count = (uint32_t)max_coeffs;

        memcpy(indices, [indicesBuf contents], extracted_count * sizeof(uint64_t));
        memcpy(values, [valuesBuf contents], extracted_count * sizeof(float));
        *num_extracted = (int)extracted_count;

        return 0;
    }
}

/* ============================================================================
 * COMPLETE RENDER PIPELINE
 * ============================================================================ */

extern "C" int qge_metal_render_frame(
    qge_metal_ctx_t* ctx,
    dwt_framebuffer_t* dwt_fb,
    uint8_t* output,
    int width,
    int height
) {
    if (!ctx || !dwt_fb || !output) return -1;

    struct qge_metal_internal* internal = (struct qge_metal_internal*)ctx->internal_ptr;
    if (!internal) return -1;

    @autoreleasepool {
        NSDate* totalStart = [NSDate date];

        int base_res = ctx->screen_res;

        /* Step 1: Extract coefficients from DWT framebuffer
         * Use the tracked coefficient arrays (fast path).
         * The coefficients are already in the DWT pyramid layout
         * via qge_extract_coefficients(). */

        /* Allocate workspace for the coefficient and pixel buffers */
        size_t buf_size = base_res * base_res * sizeof(float);
        float* coeff_buf = (float*)calloc(base_res * base_res, sizeof(float));
        float* pixel_buf = (float*)calloc(base_res * base_res, sizeof(float));
        if (!coeff_buf || !pixel_buf) {
            free(coeff_buf);
            free(pixel_buf);
            return -1;
        }

        /* Use the CPU coefficient extraction (reads tracked active coefficients) */
        /* This is declared in qge.h */
        extern void qge_extract_coefficients(dwt_framebuffer_t* fb, float* coeffs);
        qge_extract_coefficients(dwt_fb, coeff_buf);

        /* Step 2: GPU Inverse DWT reconstruction */
        int num_levels = 4;  /* Default DWT levels */
        int idwt_result = qge_metal_inverse_dwt(ctx, coeff_buf, pixel_buf, num_levels);
        if (idwt_result != 0) {
            /* CPU fallback for inverse DWT */
            extern void qge_inverse_dwt(const float* coeffs, float* pixels,
                                         int width, int height, int levels,
                                         int mode);
            qge_inverse_dwt(coeff_buf, pixel_buf, base_res, base_res, num_levels, 0);
        }

        /* Step 3: Normalize pixel buffer */
        float max_val = 0.0001f;
        for (int i = 0; i < base_res * base_res; i++) {
            float v = fabsf(pixel_buf[i]);
            if (v > max_val) max_val = v;
        }
        float norm_scale = 1.0f / max_val;

        /* Step 4: GPU float→RGB conversion with upscaling */
        if (internal->floatToRgbPipeline && width == base_res && height == base_res) {
            /* Direct GPU conversion (no upscaling needed) */
            id<MTLBuffer> inputBuf = [internal->device newBufferWithBytes:pixel_buf
                length:buf_size options:MTLResourceStorageModeShared];
            id<MTLBuffer> outputBuf = [internal->device newBufferWithLength:width * height * 3
                options:MTLResourceStorageModeShared];

            if (inputBuf && outputBuf) {
                uint32_t w = (uint32_t)width;
                uint32_t h = (uint32_t)height;

                id<MTLCommandBuffer> cmdBuf = [internal->commandQueue commandBuffer];
                id<MTLComputeCommandEncoder> encoder = [cmdBuf computeCommandEncoder];

                [encoder setComputePipelineState:internal->floatToRgbPipeline];
                [encoder setBuffer:inputBuf offset:0 atIndex:0];
                [encoder setBuffer:outputBuf offset:0 atIndex:1];
                [encoder setBytes:&w length:sizeof(uint32_t) atIndex:2];
                [encoder setBytes:&h length:sizeof(uint32_t) atIndex:3];
                [encoder setBytes:&norm_scale length:sizeof(float) atIndex:4];

                MTLSize tgSize = MTLSizeMake(16, 16, 1);
                MTLSize gridSize = MTLSizeMake(
                    (w + 15) / 16, (h + 15) / 16, 1);
                [encoder dispatchThreadgroups:gridSize threadsPerThreadgroup:tgSize];

                [encoder endEncoding];
                [cmdBuf commit];
                [cmdBuf waitUntilCompleted];

                memcpy(output, [outputBuf contents], width * height * 3);
            }
        } else {
            /* CPU fallback: normalize, gamma correct, and upscale */
            float scale_x = (float)base_res / width;
            float scale_y = (float)base_res / height;

            for (int y = 0; y < height; y++) {
                for (int x = 0; x < width; x++) {
                    int src_x = (int)(x * scale_x);
                    int src_y = (int)(y * scale_y);
                    if (src_x >= base_res) src_x = base_res - 1;
                    if (src_y >= base_res) src_y = base_res - 1;

                    float val = fabsf(pixel_buf[src_y * base_res + src_x]) * norm_scale;
                    if (val > 1.0f) val = 1.0f;
                    val = powf(val, 0.45f);  /* Gamma correction */

                    uint8_t gray = (uint8_t)(val * 255.0f);
                    int idx = (y * width + x) * 3;
                    output[idx + 0] = (uint8_t)(gray * 0.85f);  /* R - slight blue tint */
                    output[idx + 1] = (uint8_t)(gray * 0.90f);  /* G */
                    output[idx + 2] = gray;                     /* B */
                }
            }
        }

        free(coeff_buf);
        free(pixel_buf);

        ctx->last_total_time_ms = -[totalStart timeIntervalSinceNow] * 1000.0;
        return 0;
    }
}

/* ============================================================================
 * PERFORMANCE MONITORING
 * ============================================================================ */

extern "C" qge_metal_stats_t qge_metal_get_stats(qge_metal_ctx_t* ctx) {
    qge_metal_stats_t stats = {0};
    if (ctx) {
        stats.marginalize_ms = ctx->last_marginalize_time_ms;
        stats.idwt_ms = ctx->last_idwt_time_ms;
        stats.total_ms = ctx->last_total_time_ms;
    }
    return stats;
}

extern "C" void qge_metal_print_stats(qge_metal_ctx_t* ctx) {
    if (!ctx) return;
    printf("[QGE Metal] Stats:\n");
    printf("  Marginalize: %.2f ms\n", ctx->last_marginalize_time_ms);
    printf("  Inverse DWT: %.2f ms\n", ctx->last_idwt_time_ms);
    printf("  Total frame: %.2f ms\n", ctx->last_total_time_ms);
}
