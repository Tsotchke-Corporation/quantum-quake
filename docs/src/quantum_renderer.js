import * as THREE from 'three';
import { cvar_t, Cvar_RegisterVariable, Cvar_SetValue } from './cvar.js';
import { renderer } from './vid.js';
import { isXRActive } from './webxr.js';
import { Con_Printf } from './common.js';
import { cl, cl_dlights, cl_entities, cl_static_entities } from './client.js';

const PHASE_TEXTURE_SIZE = 128;
const PHASE_TEXEL_COUNT = PHASE_TEXTURE_SIZE * PHASE_TEXTURE_SIZE;
const STATE_STRUCT_SIZE = 256;
const AMPLITUDE_PTR_OFFSET = 8; // quantum_state_t.amplitudes pointer (WASM32 layout)
const RT_MAX_TRIANGLES_DEFAULT = 19456;
const RT_LEAF_TRIANGLES = 8;
const RT_MAX_BVH_DEPTH = 24;
const RT_BVH_REBUILD_INTERVAL = 45;
const RT_TEX_WIDTH = 1024;
const RT_MAX_EMISSIVE_LIGHTS = 40;
const RT_RESERVED_DYNAMIC_LIGHTS = 12;
const RT_RESERVED_MODEL_EMITTERS = 12;

const _rtSize = new THREE.Vector2();
const _savedClearColor = new THREE.Color();
const _whiteColor = new THREE.Color( 1, 1, 1 );

let _initialized = false;
let _cvarsRegistered = false;

let _postScene = null;
let _postCamera = null;
let _postQuad = null;
let _accumMaterial = null;
let _composeMaterial = null;
let _rayTraceMaterial = null;
let _waveletMaterial = null;
let _rayCompositeMaterial = null;

let _sceneTarget = null;
const _accumTargets = [ null, null ];
let _rayTraceTarget = null;
let _waveletTarget = null;
let _accumPing = 0;

let _phaseTexture = null;
const _phaseData = new Uint8Array( PHASE_TEXEL_COUNT * 4 );
let _bvhTriTexture = null;
let _bvhNodeTexture = null;
let _bvhTriCount = 0;
let _bvhNodeCount = 0;
let _bvhReady = false;
let _bvhClipped = false;
let _bvhLastBuildFrame = -99999;
let _bvhSignature = '';
let _rtLightBuildSignature = '';
const _bvhTriTexSize = new THREE.Vector2( 1, 1 );
const _bvhNodeTexSize = new THREE.Vector2( 1, 1 );
let _lastBvhBuildMs = 0;

const _rayCamPos = new THREE.Vector3();
const _rayCamRight = new THREE.Vector3();
const _rayCamUp = new THREE.Vector3();
const _rayCamForward = new THREE.Vector3();
const _tmpTriangleV0 = new THREE.Vector3();
const _tmpTriangleV1 = new THREE.Vector3();
const _tmpTriangleV2 = new THREE.Vector3();
const _tmpEdge1 = new THREE.Vector3();
const _tmpEdge2 = new THREE.Vector3();
const _tmpNormal = new THREE.Vector3();
const _tmpBvhCamPos = new THREE.Vector3();
const _tmpUv0 = new THREE.Vector2();
const _tmpTexel0 = [ 0, 0, 0 ];
const _tmpTexel1 = [ 0, 0, 0 ];
const _tmpTexel2 = [ 0, 0, 0 ];
const _tmpTexel3 = [ 0, 0, 0 ];
const _tmpSampleAlbedo = [ 0, 0, 0 ];
const _tmpSampleEmission = [ 0, 0, 0 ];
const _textureSamplerCache = new WeakMap();
const _rayAlbedoMaterialCache = new WeakMap();
const _rayAlbedoSwapObjects = [];
const _rayAlbedoSwapMaterials = [];
const _rtEmissiveLightPos = [];
const _rtEmissiveLightColor = [];
const _rtEmissiveLightRadius = new Float32Array( RT_MAX_EMISSIVE_LIGHTS );
for ( let i = 0; i < RT_MAX_EMISSIVE_LIGHTS; i ++ ) {

	_rtEmissiveLightPos.push( new THREE.Vector3() );
	_rtEmissiveLightColor.push( new THREE.Vector3() );
	_rtEmissiveLightRadius[ i ] = 0;

}
let _rtEmissiveLightCount = 0;
let _rtStaticLightCount = 0;
let _rtDynamicLightCount = 0;
let _rtModelEmitterLightCount = 0;

const _rtEmitterNameHints = [ 'flame', 'torch', 'candle', 'fire', 'brazier', 'lava' ];

let _frameCounter = 0;
let _fallbackSeed = 1;
let _lastRenderMs = 0;
let _lastMoonlabMs = 0;

let _moonlabModule = null;
let _moonlabInitPromise = null;
let _moonlabFailed = false;
let _moonlabStatePtr = 0;
let _moonlabQubits = 0;
let _moonlabCollapseState = 0;
let _moonlabFrame = 0;

let _uiRoot = null;
let _uiEnabled = null;
let _uiMode = null;
let _uiQubits = null;
let _uiDepth = null;
let _uiSpp = null;
let _uiBounces = null;
let _uiBundle = null;
let _uiRtTris = null;
let _uiRtDebugTex = null;
let _uiWavelet = null;
let _uiStrength = null;
let _uiGain = null;
let _uiExposure = null;
let _uiEnabledValue = null;
let _uiModeValue = null;
let _uiQubitsValue = null;
let _uiDepthValue = null;
let _uiSppValue = null;
let _uiBouncesValue = null;
let _uiBundleValue = null;
let _uiRtTrisValue = null;
let _uiRtDebugTexValue = null;
let _uiWaveletValue = null;
let _uiStrengthValue = null;
let _uiGainValue = null;
let _uiExposureValue = null;
let _uiStatus = null;
let _uiPerf = null;
let _lastUiSync = 0;
let _uiToggle = null;
let _uiMinimized = false;

export const r_quantum = new cvar_t( 'r_quantum', '1', true );
export const r_quantum_mode = new cvar_t( 'r_quantum_mode', '3', true );
export const r_quantum_qubits = new cvar_t( 'r_quantum_qubits', '12', true );
export const r_quantum_depth = new cvar_t( 'r_quantum_depth', '24', true );
export const r_quantum_spp = new cvar_t( 'r_quantum_spp', '4', true );
export const r_quantum_bounces = new cvar_t( 'r_quantum_bounces', '6', true );
export const r_quantum_bundle = new cvar_t( 'r_quantum_bundle', '5', true );
export const r_quantum_rt_tris = new cvar_t( 'r_quantum_rt_tris', String( RT_MAX_TRIANGLES_DEFAULT ), true );
export const r_quantum_rt_debugtex = new cvar_t( 'r_quantum_rt_debugtex', '0', true );
export const r_quantum_wavelet = new cvar_t( 'r_quantum_wavelet', '0.080', true );
export const r_quantum_strength = new cvar_t( 'r_quantum_strength', '2.00', true );
export const r_quantum_gain = new cvar_t( 'r_quantum_gain', '0.90', true );
export const r_quantum_exposure = new cvar_t( 'r_quantum_exposure', '3.10', true );

const _fullscreenVertex = `
varying vec2 vUv;
void main() {
	vUv = uv;
	gl_Position = vec4( position.xy, 0.0, 1.0 );
}
`;

const _accumFragment = `
precision highp float;
varying vec2 vUv;
uniform sampler2D uBaseTex;
uniform sampler2D uPrevAccumTex;
uniform sampler2D uPhaseTex;
uniform float uFrame;
uniform float uSpp;
uniform float uBounces;
uniform float uStrength;
uniform float uCollapseMix;
uniform float uCollapseSeed;
uniform vec2 uPixelStep;

float hash12( vec2 p ) {
	vec3 p3 = fract( vec3( p.xyx ) * 0.1031 );
	p3 += dot( p3, p3.yzx + 33.33 );
	return fract( ( p3.x + p3.y ) * p3.z );
}

vec2 hash22( vec2 p ) {
	float n = hash12( p );
	float m = hash12( p + vec2( 11.7, 3.1 ) );
	return vec2( n, m );
}

void main() {
	const int MAX_SPP = 4;
	const int MAX_BOUNCES = 6;
	vec3 baseCenter = texture2D( uBaseTex, vUv ).rgb;
	float baseWeight = 1.25;
	vec3 radiance = baseCenter * baseWeight;
	float weightSum = baseWeight;

	for ( int i = 0; i < MAX_SPP; i ++ ) {
		if ( float( i ) >= uSpp ) break;
		vec2 h = hash22( vUv * vec2( 173.0 + float( i ) * 17.0, 97.0 - float( i ) * 11.0 ) + uFrame * 0.113 + uCollapseSeed * 0.013 );
		vec2 dir = normalize( h * 2.0 - 1.0 + vec2( 0.0001, - 0.0001 ) );
		vec2 uv2 = vUv;
		float bounceWeight = 0.78;
		float bounceDamp = 0.84;

		for ( int b = 0; b < MAX_BOUNCES; b ++ ) {
			if ( float( b ) >= uBounces ) break;
			float bF = float( b );
			vec2 j = hash22( uv2 * vec2( 83.0 + bF * 9.0, 61.0 + bF * 7.0 ) + vec2( uFrame * 0.071 + float( i ) * 0.31, uCollapseSeed * 0.27 + bF * 0.11 ) );
			vec2 bounceDir = normalize( j * 2.0 - 1.0 + vec2( - 0.0001, 0.0001 ) );
			dir = normalize( mix( dir, bounceDir, 0.34 + 0.08 * bF ) );
			float stepScale = ( 0.72 + h.y * 1.18 + j.x * 0.45 ) * float( i + 1 ) * ( 1.0 + bF * 0.82 );
			uv2 = clamp( uv2 + dir * uPixelStep * stepScale * 3.0, vec2( 0.001 ), vec2( 0.999 ) );
			radiance += texture2D( uBaseTex, uv2 ).rgb * bounceWeight;
			weightSum += bounceWeight;
			bounceWeight *= bounceDamp;
			bounceDamp *= 0.96;
		}
	}

	radiance /= max( weightSum, 1.0 );
	float centerLum = dot( baseCenter, vec3( 0.2126, 0.7152, 0.0722 ) );
	float sampleLum = dot( radiance, vec3( 0.2126, 0.7152, 0.0722 ) );
	float energyComp = ( centerLum + 0.02 ) / ( sampleLum + 0.02 );
	radiance *= mix( 1.0, energyComp, 0.62 );
	float amplitude = dot( radiance, vec3( 0.2126, 0.7152, 0.0722 ) );

	vec2 qUv0 = fract( vUv * 1.618 + vec2( uFrame * 0.0017, uCollapseSeed * 0.00073 ) );
	vec2 qUv1 = fract( vUv.yx * 1.131 + vec2( uCollapseSeed * 0.0019, uFrame * 0.0023 ) );
	vec4 q0 = texture2D( uPhaseTex, qUv0 );
	vec4 q1 = texture2D( uPhaseTex, qUv1 );
	float qPhase = ( q0.r * 0.65 + q1.r * 0.35 ) * 6.28318530718;
	float qMag = q0.g * 0.7 + q1.g * 0.3;
	float jitter = ( hash12( vUv + vec2( uFrame * 0.019, uCollapseSeed * 0.07 ) ) - 0.5 ) * 0.85;
	float phase = qPhase + jitter + amplitude * 8.0;
	phase += ( hash12( vUv * vec2( 547.3, 113.7 ) + vec2( uCollapseSeed, uFrame * 0.004 ) ) - 0.5 ) * 0.55;
	float contribMag = amplitude * ( 0.08 + qMag * 0.72 ) * ( 0.45 + 0.55 * uStrength );
	vec2 contrib = vec2( cos( phase ), sin( phase ) ) * contribMag;

	vec2 prev = texture2D( uPrevAccumTex, vUv ).rg * 2.0 - 1.0;
	float history = mix( 0.95, 0.40, clamp( uCollapseMix, 0.0, 1.0 ) );
	vec2 next = clamp( prev * history + contrib, vec2( -1.0 ), vec2( 1.0 ) );

	gl_FragColor = vec4( next * 0.5 + 0.5, 0.0, 1.0 );
}
`;

const _composeFragment = `
precision highp float;
varying vec2 vUv;
uniform sampler2D uBaseTex;
uniform sampler2D uAccumTex;
uniform sampler2D uPhaseTex;
uniform float uMode;
uniform float uStrength;
uniform float uGain;
uniform float uExposure;
uniform float uFrame;
uniform float uCollapseSeed;

float hash12( vec2 p ) {
	vec3 p3 = fract( vec3( p.xyx ) * 0.1031 );
	p3 += dot( p3, p3.yzx + 33.33 );
	return fract( ( p3.x + p3.y ) * p3.z );
}

vec3 phasePalette( float t ) {
	return 0.5 + 0.5 * cos( 6.28318530718 * ( t + vec3( 0.0, 0.33, 0.67 ) ) );
}

void main() {
	vec3 base = texture2D( uBaseTex, vUv ).rgb;
	vec2 c = texture2D( uAccumTex, vUv ).rg * 2.0 - 1.0;
	float intensity = dot( c, c );
	float inten = clamp( intensity * 0.58, 0.0, 1.6 );
	float phase = atan( c.y, c.x );
	float phaseNorm = fract( phase / 6.28318530718 + 0.5 );
	float fringe = 0.5 + 0.5 * cos( phase * 6.0 + texture2D( uPhaseTex, vUv * 2.0 ).r * 6.28318530718 );

	vec3 outColor = base;

	if ( uMode < 0.5 ) {
		float gain = 0.98 + inten * ( 0.82 + uStrength * 0.42 );
		outColor = base * gain + vec3( fringe ) * ( 0.02 * uStrength );
	} else if ( uMode < 1.5 ) {
		vec3 phaseColor = phasePalette( phaseNorm );
		vec3 tint = mix( vec3( 1.0 ), phaseColor, 0.58 );
		float mask = smoothstep( 0.08, 1.0, inten );
		vec3 quantum = tint * ( 0.12 + 0.45 * mask ) * fringe * uStrength;
		outColor = base * ( 1.02 + inten * ( 0.42 + 0.56 * uStrength ) ) + quantum;
		outColor = mix( base, outColor, 0.86 );
	} else {
		float collapseNoise = hash12( vUv * 1024.0 + vec2( uCollapseSeed, uFrame * 0.13 ) );
		float collapsed = step( collapseNoise, clamp( inten * 1.4, 0.0, 1.0 ) );
		float glow = smoothstep( 0.12, 1.45, inten ) * fringe;
		outColor = base * ( 0.84 + collapsed * 0.76 ) + vec3( glow ) * 0.08 + phasePalette( phaseNorm ) * ( glow * 0.04 );
	}

	outColor *= ( uExposure * uGain );
	outColor = pow( max( outColor, vec3( 0.0 ) ), vec3( 0.92 ) );
	gl_FragColor = vec4( outColor, 1.0 );
}
`;

const _raytraceFragment = `
precision highp float;
varying vec2 vUv;
uniform sampler2D uBaseTex;
uniform sampler2D uDepthTex;
uniform sampler2D uTriTex;
uniform sampler2D uNodeTex;
uniform vec2 uTriTexSize;
uniform vec2 uNodeTexSize;
uniform float uTriCount;
uniform float uNodeCount;
uniform vec3 uCamPos;
uniform vec3 uCamRight;
uniform vec3 uCamUp;
uniform vec3 uCamForward;
uniform float uTanHalfFov;
uniform float uAspect;
uniform float uCameraNear;
uniform float uCameraFar;
uniform float uEmissiveLightCount;
uniform vec3 uEmissiveLightPos[ ${RT_MAX_EMISSIVE_LIGHTS} ];
uniform vec3 uEmissiveLightColor[ ${RT_MAX_EMISSIVE_LIGHTS} ];
uniform float uEmissiveLightRadius[ ${RT_MAX_EMISSIVE_LIGHTS} ];
uniform float uFrame;
uniform float uSpp;
uniform float uBounces;
uniform float uStrength;
uniform float uDebugWhite;
uniform vec2 uPixelStep;

const int MAX_SPP = 4;
const int MAX_BOUNCES = 6;
const int MAX_STACK = 96;
const int MAX_STEPS = 512;
const int MAX_LEAF_TRIS = 8;

float hash12( vec2 p ) {
	vec3 p3 = fract( vec3( p.xyx ) * 0.1031 );
	p3 += dot( p3, p3.yzx + 33.33 );
	return fract( ( p3.x + p3.y ) * p3.z );
}

vec2 hash22( vec2 p ) {
	float n = hash12( p );
	float m = hash12( p + vec2( 11.7, 3.1 ) );
	return vec2( n, m );
}

vec4 readPackedTex( sampler2D tex, vec2 texSize, int index ) {
	float fi = float( index );
	float x = mod( fi, texSize.x );
	float y = floor( fi / texSize.x );
	vec2 uv = ( vec2( x, y ) + 0.5 ) / texSize;
	return texture2D( tex, uv );
}

void fetchNode( int nodeIndex, out vec3 bmin, out vec3 bmax, out float a, out float b ) {
	vec4 n0 = readPackedTex( uNodeTex, uNodeTexSize, nodeIndex * 2 );
	vec4 n1 = readPackedTex( uNodeTex, uNodeTexSize, nodeIndex * 2 + 1 );
	bmin = n0.xyz;
	bmax = n1.xyz;
	a = n0.w;
	b = n1.w;
}

void fetchTriangle( int triIndex, out vec3 v0, out vec3 v1, out vec3 v2, out vec3 albedo, out vec3 emissive ) {
	int texel = triIndex * 4;
	vec4 t0 = readPackedTex( uTriTex, uTriTexSize, texel );
	vec4 t1 = readPackedTex( uTriTex, uTriTexSize, texel + 1 );
	vec4 t2 = readPackedTex( uTriTex, uTriTexSize, texel + 2 );
	vec4 t3 = readPackedTex( uTriTex, uTriTexSize, texel + 3 );
	v0 = t0.xyz;
	v1 = t1.xyz;
	v2 = t2.xyz;
	albedo = clamp( vec3( t0.w, t1.w, t2.w ), vec3( 0.01 ), vec3( 2.5 ) );
	emissive = clamp( t3.xyz, vec3( 0.0 ), vec3( 6.0 ) );
}

bool intersectAabb( vec3 ro, vec3 invDir, vec3 bmin, vec3 bmax, float tLimit ) {
	vec3 t0 = ( bmin - ro ) * invDir;
	vec3 t1 = ( bmax - ro ) * invDir;
	vec3 tsm = min( t0, t1 );
	vec3 tbx = max( t0, t1 );
	float tNear = max( max( tsm.x, tsm.y ), max( tsm.z, 0.0 ) );
	float tFar = min( min( tbx.x, tbx.y ), min( tbx.z, tLimit ) );
	return tFar >= tNear;
}

bool intersectTriangle( vec3 ro, vec3 rd, vec3 v0, vec3 v1, vec3 v2, out float t, out vec3 n ) {
	vec3 e1 = v1 - v0;
	vec3 e2 = v2 - v0;
	vec3 p = cross( rd, e2 );
	float det = dot( e1, p );
	if ( abs( det ) < 1e-6 ) return false;
	float invDet = 1.0 / det;
	vec3 s = ro - v0;
	float u = dot( s, p ) * invDet;
	if ( u < 0.0 || u > 1.0 ) return false;
	vec3 q = cross( s, e1 );
	float v = dot( rd, q ) * invDet;
	if ( v < 0.0 || u + v > 1.0 ) return false;
	float hitT = dot( e2, q ) * invDet;
	if ( hitT <= 0.0007 ) return false;
	t = hitT;
	n = normalize( cross( e1, e2 ) );
	return true;
}

vec3 cosineHemisphere( vec3 n, vec2 xi ) {
	float phi = 6.28318530718 * xi.x;
	float r = sqrt( xi.y );
	float z = sqrt( max( 0.0, 1.0 - xi.y ) );
	vec3 t = normalize( abs( n.z ) < 0.999 ? cross( vec3( 0.0, 0.0, 1.0 ), n ) : cross( vec3( 1.0, 0.0, 0.0 ), n ) );
	vec3 b = cross( n, t );
	return normalize( t * ( r * cos( phi ) ) + b * ( r * sin( phi ) ) + n * z );
}

vec3 skyColor( vec3 rd ) {
	float h = clamp( rd.y * 0.5 + 0.5, 0.0, 1.0 );
	vec3 low = vec3( 0.015, 0.02, 0.028 );
	vec3 high = vec3( 0.10, 0.13, 0.18 );
	return mix( low, high, h );
}

float perspectiveDepthToViewZ( float depth, float nearPlane, float farPlane ) {
	return ( nearPlane * farPlane ) / ( ( farPlane - nearPlane ) * depth - farPlane );
}

bool traceAny( vec3 ro, vec3 rd, float tLimit );

vec3 sampleEmissiveLights( vec3 hitPos, vec3 hitNormal ) {
	vec3 light = vec3( 0.0 );
	int count = int( min( uEmissiveLightCount, float( ${RT_MAX_EMISSIVE_LIGHTS} ) ) );
	for ( int i = 0; i < ${RT_MAX_EMISSIVE_LIGHTS}; i ++ ) {
		if ( i >= count ) break;
		float radius = max( uEmissiveLightRadius[ i ], 1.0 );
		vec3 toLight = uEmissiveLightPos[ i ] - hitPos;
		float distSq = dot( toLight, toLight );
		if ( distSq > radius * radius ) continue;
		float invDist = inversesqrt( distSq + 1e-4 );
		vec3 L = toLight * invDist;
		float nDotL = max( dot( hitNormal, L ), 0.0 );
		if ( nDotL <= 0.0 ) continue;
		float lightDist = 1.0 / max( invDist, 1e-5 );
		float shadowInset = 0.12 + min( radius * 0.18, 10.0 );
		float shadowMax = max( lightDist - shadowInset, 0.001 );
		if ( traceAny( hitPos + hitNormal * 0.04, L, shadowMax ) ) continue;
		float atten = 1.0 / ( 1.0 + distSq / ( radius * radius ) );
		light += uEmissiveLightColor[ i ] * ( nDotL * atten );
	}
	return light;
}

bool traceScene( vec3 ro, vec3 rd, out vec3 hitPos, out vec3 hitNormal, out vec3 hitAlbedo, out vec3 hitEmission ) {
	if ( uNodeCount < 1.0 || uTriCount < 1.0 ) return false;

	vec3 invDir = 1.0 / ( rd + sign( rd ) * 1e-6 );
	int stack[ MAX_STACK ];
	int sp = 0;
	stack[ 0 ] = 0;

	float bestT = 1e20;
	bool found = false;
	vec3 bestN = vec3( 0.0 );
	vec3 bestAlb = vec3( 0.0 );
	vec3 bestEmit = vec3( 0.0 );

	for ( int step = 0; step < MAX_STEPS; step ++ ) {
		if ( sp < 0 ) break;
		int nodeIndex = stack[ sp ];
		sp --;
		if ( float( nodeIndex ) >= uNodeCount ) continue;

		vec3 bmin;
		vec3 bmax;
		float a;
		float b;
		fetchNode( nodeIndex, bmin, bmax, a, b );
		if ( intersectAabb( ro, invDir, bmin, bmax, bestT ) == false ) continue;

		if ( a < 0.0 ) {
			int triCount = int( - a + 0.5 );
			int triStart = int( b + 0.5 );

			for ( int t = 0; t < MAX_LEAF_TRIS; t ++ ) {
				if ( t >= triCount ) break;
				int triIndex = triStart + t;
				if ( float( triIndex ) >= uTriCount ) break;
				vec3 v0;
				vec3 v1;
				vec3 v2;
				vec3 alb;
				vec3 emit;
				fetchTriangle( triIndex, v0, v1, v2, alb, emit );
				float triT;
				vec3 triN;
				if ( intersectTriangle( ro, rd, v0, v1, v2, triT, triN ) && triT < bestT ) {
					bestT = triT;
					bestN = triN;
					bestAlb = alb;
					bestEmit = emit;
					found = true;
				}
			}
		} else {
			int left = int( a + 0.5 );
			int right = int( b + 0.5 );
			if ( sp + 2 < MAX_STACK ) {
				stack[ ++ sp ] = right;
				stack[ ++ sp ] = left;
			}
		}
	}

	if ( found == false ) return false;
	hitPos = ro + rd * bestT;
	hitNormal = bestN;
	hitAlbedo = bestAlb;
	hitEmission = bestEmit;
	return true;
}

bool traceAny( vec3 ro, vec3 rd, float tLimit ) {
	if ( uNodeCount < 1.0 || uTriCount < 1.0 ) return false;

	vec3 invDir = 1.0 / ( rd + sign( rd ) * 1e-6 );
	int stack[ MAX_STACK ];
	int sp = 0;
	stack[ 0 ] = 0;
	float limit = max( tLimit, 0.001 );

	for ( int step = 0; step < MAX_STEPS; step ++ ) {
		if ( sp < 0 ) break;
		int nodeIndex = stack[ sp ];
		sp --;
		if ( float( nodeIndex ) >= uNodeCount ) continue;

		vec3 bmin;
		vec3 bmax;
		float a;
		float b;
		fetchNode( nodeIndex, bmin, bmax, a, b );
		if ( intersectAabb( ro, invDir, bmin, bmax, limit ) == false ) continue;

		if ( a < 0.0 ) {
			int triCount = int( - a + 0.5 );
			int triStart = int( b + 0.5 );

			for ( int t = 0; t < MAX_LEAF_TRIS; t ++ ) {
				if ( t >= triCount ) break;
				int triIndex = triStart + t;
				if ( float( triIndex ) >= uTriCount ) break;
				vec3 v0;
				vec3 v1;
				vec3 v2;
				vec3 alb;
				vec3 emit;
				fetchTriangle( triIndex, v0, v1, v2, alb, emit );
				float triT;
				vec3 triN;
				if ( intersectTriangle( ro, rd, v0, v1, v2, triT, triN ) && triT < limit ) return true;
			}
		} else {
			int left = int( a + 0.5 );
			int right = int( b + 0.5 );
			if ( sp + 2 < MAX_STACK ) {
				stack[ ++ sp ] = right;
				stack[ ++ sp ] = left;
			}
		}
	}

	return false;
}

void main() {
	float debugMix = step( 0.5, uDebugWhite );
	float sampleCount = debugMix > 0.5
		? 1.0
		: max( 1.0, min( uSpp, float( MAX_SPP ) ) );
	vec3 total = vec3( 0.0 );

	for ( int s = 0; s < MAX_SPP; s ++ ) {
		if ( float( s ) >= sampleCount ) break;

		vec2 jitter = debugMix > 0.5
			? vec2( 0.0 )
			: ( hash22( vUv * vec2( 983.0, 577.0 ) + vec2( float( s ) * 13.0, uFrame * 0.19 ) ) - 0.5 ) * uPixelStep;
		vec2 uv = clamp( vUv + jitter, vec2( 0.0005 ), vec2( 0.9995 ) );
		vec3 basePrimary = texture2D( uBaseTex, uv ).rgb;
		vec2 ndc = uv * 2.0 - 1.0;
		vec3 rd = normalize( uCamForward + ndc.x * uCamRight * uTanHalfFov * uAspect + ndc.y * uCamUp * uTanHalfFov );
		float sceneDepth = texture2D( uDepthTex, uv ).x;
		float sceneViewDepth = sceneDepth >= 0.99999
			? 1e20
			: max( 0.0, - perspectiveDepthToViewZ( sceneDepth, uCameraNear, uCameraFar ) );

		vec3 ro = uCamPos;
		vec3 throughput = vec3( 1.0 );
		vec3 radiance = vec3( 0.0 );

		for ( int bounce = 0; bounce < MAX_BOUNCES; bounce ++ ) {
			if ( float( bounce ) >= uBounces ) break;

			vec3 hitPos;
			vec3 hitNormal;
			vec3 hitAlbedo;
			vec3 hitEmission;
			if ( traceScene( ro, rd, hitPos, hitNormal, hitAlbedo, hitEmission ) == false ) {
				if ( bounce == 0 ) {
					radiance += basePrimary;
				} else {
					radiance += throughput * skyColor( rd ) * 0.36;
				}
				break;
			}

			if ( bounce == 0 && sceneViewDepth < 1e19 ) {
				float hitViewDepth = max( 0.0, dot( hitPos - uCamPos, uCamForward ) );
				float depthSlack = max( 2.5, sceneViewDepth * 0.05 );
				if ( hitViewDepth > sceneViewDepth + depthSlack ) {
					radiance += basePrimary;
					break;
				}
			}

			vec3 geoNormal = normalize( hitNormal );
			vec3 bounceNormal = dot( geoNormal, rd ) < 0.0 ? geoNormal : - geoNormal;
			vec3 lightDir = normalize( vec3( 0.32, 0.84, 0.21 ) );
			float nDotL = max( dot( bounceNormal, lightDir ), 0.0 );
			float sunVisibility = 1.0;
			if ( nDotL > 0.0001 && traceAny( hitPos + bounceNormal * 0.04, lightDir, 2048.0 ) ) sunVisibility = 0.0;
			float hemi = bounceNormal.y * 0.5 + 0.5;
			vec3 inspectDir = normalize( vec3( -0.42, 0.76, 0.37 ) );
			float inspectN = max( dot( bounceNormal, inspectDir ), 0.0 );
			float inspectVisibility = 1.0;
			if ( inspectN > 0.0001 && traceAny( hitPos + bounceNormal * 0.04, inspectDir, 512.0 ) ) inspectVisibility = 0.0;
			vec3 directSun = hitAlbedo * ( 0.010 + 0.82 * nDotL * sunVisibility );
			vec3 directDebug = hitAlbedo * ( 0.070 + 1.08 * inspectN * inspectVisibility );
			vec3 ambientBase = hitAlbedo * ( 0.022 + 0.060 * hemi );
			vec3 ambientDebug = hitAlbedo * ( 0.050 + 0.160 * hemi );
			vec3 direct = mix( directSun, directDebug, debugMix );
			vec3 ambient = mix( ambientBase, ambientDebug, debugMix );
			vec3 emissiveDirect = hitAlbedo * sampleEmissiveLights( hitPos + bounceNormal * 0.02, bounceNormal ) * ( 0.46 + 0.52 * uStrength ) * mix( 1.0, 1.35, debugMix );
			vec3 emissiveSelf = hitEmission * ( 0.42 + 0.46 * uStrength ) * ( 1.0 - debugMix );
			radiance += throughput * ( direct + ambient + emissiveDirect ) * ( 0.58 + 0.62 * uStrength );
			radiance += throughput * emissiveSelf;

			if ( debugMix > 0.5 ) {

				float ao = 1.0;
				vec3 t = normalize( abs( bounceNormal.z ) < 0.999 ? cross( vec3( 0.0, 0.0, 1.0 ), bounceNormal ) : cross( vec3( 1.0, 0.0, 0.0 ), bounceNormal ) );
				vec3 b = cross( bounceNormal, t );
				vec3 aoDir0 = normalize( bounceNormal * 0.84 + t * 0.39 );
				vec3 aoDir1 = normalize( bounceNormal * 0.82 - t * 0.26 + b * 0.33 );
				if ( traceAny( hitPos + bounceNormal * 0.04, aoDir0, 128.0 ) ) ao -= 0.18;
				if ( traceAny( hitPos + bounceNormal * 0.04, aoDir1, 128.0 ) ) ao -= 0.16;
				ao = clamp( ao, 0.32, 1.0 );
				radiance *= ao;
				break;

			}

			throughput *= clamp( hitAlbedo, vec3( 0.12 ), vec3( 1.35 ) ) * 0.74;
			float maxCh = max( throughput.r, max( throughput.g, throughput.b ) );
			if ( bounce > 1 ) {
				float survive = clamp( maxCh, 0.08, 0.95 );
				float rr = hash12( vUv * 1711.0 + vec2( float( bounce ) * 19.0, uFrame * 0.41 + float( s ) * 5.0 ) );
				if ( rr > survive ) break;
				throughput /= survive;
			}

			vec2 xi = hash22( hitPos.xy * 0.173 + vec2( float( bounce ) * 2.7, uFrame * 0.13 + float( s ) * 0.37 ) );
			rd = cosineHemisphere( bounceNormal, xi );
			ro = hitPos + bounceNormal * 0.01;
		}

		total += radiance;
	}

	vec3 traced = total / sampleCount;
	gl_FragColor = vec4( max( traced, vec3( 0.0 ) ), 1.0 );
}
`;

const _waveletFragment = `
precision highp float;
varying vec2 vUv;
uniform sampler2D uInputTex;
uniform vec2 uPixelStep;
uniform float uThreshold;

vec3 shrink( vec3 v, float t ) {
	return sign( v ) * max( abs( v ) - vec3( t ), vec3( 0.0 ) );
}

void main() {
	vec2 origin = vUv - 0.5 * uPixelStep;
	vec3 c00 = texture2D( uInputTex, origin ).rgb;
	vec3 c10 = texture2D( uInputTex, origin + vec2( uPixelStep.x, 0.0 ) ).rgb;
	vec3 c01 = texture2D( uInputTex, origin + vec2( 0.0, uPixelStep.y ) ).rgb;
	vec3 c11 = texture2D( uInputTex, origin + uPixelStep ).rgb;

	vec3 a = ( c00 + c10 + c01 + c11 ) * 0.25;
	vec3 hx = ( c00 - c10 + c01 - c11 ) * 0.25;
	vec3 hy = ( c00 + c10 - c01 - c11 ) * 0.25;
	vec3 hd = ( c00 - c10 - c01 + c11 ) * 0.25;

	hx = shrink( hx, uThreshold );
	hy = shrink( hy, uThreshold );
	hd = shrink( hd, uThreshold * 1.4 );

	vec2 parity = vec2( mod( floor( gl_FragCoord.x ), 2.0 ), mod( floor( gl_FragCoord.y ), 2.0 ) );
	float sx = parity.x < 0.5 ? 1.0 : -1.0;
	float sy = parity.y < 0.5 ? 1.0 : -1.0;

	vec3 reconstructed = a + hx * sx + hy * sy + hd * sx * sy;
	gl_FragColor = vec4( max( reconstructed, vec3( 0.0 ) ), 1.0 );
}
`;

const _rayCompositeFragment = `
precision highp float;
varying vec2 vUv;
uniform sampler2D uBaseTex;
uniform sampler2D uRayTex;
uniform float uStrength;
uniform float uGain;
uniform float uExposure;
uniform float uDebugWhite;

void main() {
	vec3 base = texture2D( uBaseTex, vUv ).rgb;
	vec3 ray = texture2D( uRayTex, vUv ).rgb;

	if ( uDebugWhite > 0.5 ) {
		vec3 outColor = ray * ( uExposure * uGain * 2.85 );
		outColor = outColor / ( vec3( 1.0 ) + outColor );
		outColor = pow( max( outColor, vec3( 0.0 ) ), vec3( 0.86 ) );
		gl_FragColor = vec4( outColor, 1.0 );
		return;
	}

	vec3 lumaW = vec3( 0.2126, 0.7152, 0.0722 );
	float baseLum = max( dot( base, lumaW ), 0.0002 );
	float rayLum = max( dot( ray, lumaW ), 0.0 );
	float relLight = clamp( rayLum / baseLum, 0.70, 3.80 );
	vec3 litBase = base * mix( 1.0, relLight, 0.90 );
	vec3 rayChroma = rayLum > 0.0001 ? ( ray / rayLum ) : vec3( 1.0 );
	rayChroma = clamp( rayChroma, vec3( 0.65 ), vec3( 1.6 ) );
	vec3 tinted = litBase * mix( vec3( 1.0 ), rayChroma, 0.16 + 0.20 * uStrength );
	float blend = clamp( 0.20 + 0.22 * uStrength, 0.0, 0.62 );
	vec3 outColor = mix( base, tinted, blend );
	outColor = max( outColor, base * 0.26 );
	outColor *= ( uExposure * uGain );
	outColor = outColor / ( vec3( 1.0 ) + outColor );
	outColor = pow( max( outColor, vec3( 0.0 ) ), vec3( 0.92 ) );
	gl_FragColor = vec4( outColor, 1.0 );
}
`;

function _clamp( value, min, max ) {

	return value < min ? min : ( value > max ? max : value );

}

function _clampInt( value, min, max ) {

	return Math.floor( _clamp( value, min, max ) );

}

function _fract( value ) {

	return value - Math.floor( value );

}

function _pseudoRandom( seed ) {

	return _fract( Math.sin( seed ) * 43758.5453123 );

}

function _toNumber( value, fallback = 0 ) {

	if ( typeof value === 'bigint' ) {

		const asNumber = Number( value );
		return Number.isFinite( asNumber ) ? asNumber : fallback;

	}

	const asNumber = Number( value );
	return Number.isFinite( asNumber ) ? asNumber : fallback;

}

function _textureChannelCount( texture ) {

	if ( texture == null ) return 4;

	const format = texture.format;
	if (
		format === THREE.RedFormat ||
		format === THREE.AlphaFormat ||
		( THREE.LuminanceFormat != null && format === THREE.LuminanceFormat )
	) return 1;
	if (
		format === THREE.RGFormat ||
		( THREE.LuminanceAlphaFormat != null && format === THREE.LuminanceAlphaFormat )
	) return 2;
	if ( format === THREE.RGBFormat ) return 3;
	return 4;

}

function _decodeTexelComponent( data, index ) {

	const value = data != null ? data[ index ] : null;
	if ( value == null ) return 0;
	if ( data instanceof Uint8Array || data instanceof Uint8ClampedArray ) return value / 255;
	if ( data instanceof Uint16Array ) return value / 65535;
	if ( data instanceof Int16Array ) return _clamp( ( value + 32768 ) / 65535, 0, 1 );
	return value;

}

function _getTextureSampler( texture ) {

	if ( texture == null ) return null;
	const image = texture.image != null ? texture.image : ( texture.source != null ? texture.source.data : null );
	if ( image == null || image.data == null ) return null;

	const width = _toNumber( image.width, 0 ) | 0;
	const height = _toNumber( image.height, 0 ) | 0;
	if ( width <= 0 || height <= 0 ) return null;

	const channels = _textureChannelCount( texture );
	const data = image.data;
	let sampler = _textureSamplerCache.get( texture );
	if (
		sampler == null ||
		sampler.data !== data ||
		sampler.width !== width ||
		sampler.height !== height ||
		sampler.channels !== channels
	) {

		sampler = {
			data: data,
			width: width,
			height: height,
			channels: channels
		};
		_textureSamplerCache.set( texture, sampler );

	}

	return sampler;

}

function _sampleTextureRGB( texture, u, v, outColor ) {

	const sampler = _getTextureSampler( texture );
	if ( sampler == null ) return false;

	_tmpUv0.set( u, v );
	texture.transformUv( _tmpUv0 );

	const x = _clampInt( Math.floor( _tmpUv0.x * sampler.width ), 0, sampler.width - 1 );
	const y = _clampInt( Math.floor( _tmpUv0.y * sampler.height ), 0, sampler.height - 1 );
	const offset = ( y * sampler.width + x ) * sampler.channels;
	const r = _decodeTexelComponent( sampler.data, offset );
	const g = sampler.channels > 1 ? _decodeTexelComponent( sampler.data, offset + 1 ) : r;
	const b = sampler.channels > 2 ? _decodeTexelComponent( sampler.data, offset + 2 ) : r;

	outColor[ 0 ] = r;
	outColor[ 1 ] = g;
	outColor[ 2 ] = b;
	return true;

}

function _createFloatDataTexture( data, width, height ) {

	const texture = new THREE.DataTexture( data, width, height, THREE.RGBAFormat, THREE.FloatType );
	texture.wrapS = THREE.ClampToEdgeWrapping;
	texture.wrapT = THREE.ClampToEdgeWrapping;
	texture.minFilter = THREE.NearestFilter;
	texture.magFilter = THREE.NearestFilter;
	texture.generateMipmaps = false;
	texture.flipY = false;
	texture.needsUpdate = true;
	return texture;

}

function _rtDebugTexturesEnabled() {

	return r_quantum_rt_debugtex.value !== 0;

}

function _getRayAlbedoMaterial( sourceMaterial ) {

	if ( sourceMaterial == null )
		return null;

	let mat = _rayAlbedoMaterialCache.get( sourceMaterial );
	if ( mat == null ) {

		mat = new THREE.MeshBasicMaterial();
		_rayAlbedoMaterialCache.set( sourceMaterial, mat );

	}

	const debugWhite = _rtDebugTexturesEnabled();
	mat.map = debugWhite ? null : ( sourceMaterial.map != null ? sourceMaterial.map : null );
	mat.color.copy( debugWhite ? _whiteColor : ( sourceMaterial.color != null ? sourceMaterial.color : _whiteColor ) );
	mat.transparent = sourceMaterial.transparent === true || ( sourceMaterial.opacity != null && sourceMaterial.opacity < 0.999 );
	mat.opacity = sourceMaterial.opacity != null ? sourceMaterial.opacity : 1.0;
	mat.alphaTest = sourceMaterial.alphaTest != null ? sourceMaterial.alphaTest : 0.0;
	mat.side = sourceMaterial.side != null ? sourceMaterial.side : THREE.FrontSide;
	mat.depthWrite = sourceMaterial.depthWrite !== false;
	mat.depthTest = sourceMaterial.depthTest !== false;
	mat.blending = sourceMaterial.blending != null ? sourceMaterial.blending : THREE.NormalBlending;
	mat.premultipliedAlpha = sourceMaterial.premultipliedAlpha === true;
	mat.polygonOffset = sourceMaterial.polygonOffset === true;
	mat.polygonOffsetFactor = sourceMaterial.polygonOffsetFactor != null ? sourceMaterial.polygonOffsetFactor : 0;
	mat.polygonOffsetUnits = sourceMaterial.polygonOffsetUnits != null ? sourceMaterial.polygonOffsetUnits : 0;
	mat.visible = sourceMaterial.visible !== false;
	mat.needsUpdate = false;
	return mat;

}

function _renderSceneAlbedoPass( scene, camera, target ) {

	if ( renderer == null || scene == null || camera == null || target == null )
		return;

	_rayAlbedoSwapObjects.length = 0;
	_rayAlbedoSwapMaterials.length = 0;

	scene.traverseVisible( function ( object ) {

		if ( object == null || object.isMesh !== true || object.material == null )
			return;
		if ( object.renderOrder >= 900 )
			return;

		const original = object.material;
		_rayAlbedoSwapObjects.push( object );
		_rayAlbedoSwapMaterials.push( original );

		if ( Array.isArray( original ) ) {

			const next = new Array( original.length );
			for ( let i = 0; i < original.length; i ++ )
				next[ i ] = _getRayAlbedoMaterial( original[ i ] );
			object.material = next;

		} else {

			object.material = _getRayAlbedoMaterial( original );

		}

	} );

	renderer.setRenderTarget( target );
	renderer.clear( true, true, false );
	renderer.render( scene, camera );

	for ( let i = _rayAlbedoSwapObjects.length - 1; i >= 0; i -- ) {

		_rayAlbedoSwapObjects[ i ].material = _rayAlbedoSwapMaterials[ i ];

	}

	_rayAlbedoSwapObjects.length = 0;
	_rayAlbedoSwapMaterials.length = 0;

}

function _disposeBvhTextures() {

	if ( _bvhTriTexture != null ) {

		_bvhTriTexture.dispose();
		_bvhTriTexture = null;

	}

	if ( _bvhNodeTexture != null ) {

		_bvhNodeTexture.dispose();
		_bvhNodeTexture = null;

	}

	_bvhTriCount = 0;
	_bvhNodeCount = 0;
	_bvhReady = false;
	_bvhClipped = false;
	_rtLightBuildSignature = '';
	_bvhTriTexSize.set( 1, 1 );
	_bvhNodeTexSize.set( 1, 1 );
	_rtEmissiveLightCount = 0;
	_rtStaticLightCount = 0;
	_rtDynamicLightCount = 0;
	_rtModelEmitterLightCount = 0;
	for ( let i = 0; i < RT_MAX_EMISSIVE_LIGHTS; i ++ ) {

		_rtEmissiveLightRadius[ i ] = 0;
		_rtEmissiveLightPos[ i ].set( 0, 0, 0 );
		_rtEmissiveLightColor[ i ].set( 0, 0, 0 );

	}

}

function _countActiveRuntimeDlights() {

	if ( cl_dlights == null )
		return 0;

	const now = cl != null && typeof cl.time === 'number' ? cl.time : 0;
	let active = 0;
	for ( let i = 0; i < cl_dlights.length; i ++ ) {

		const light = cl_dlights[ i ];
		if ( light == null || light.origin == null )
			continue;
		const radius = _toNumber( light.radius, 0 );
		if ( radius <= 12 )
			continue;
		const die = _toNumber( light.die, now + 1.0 );
		if ( die + 0.015 < now )
			continue;
		active ++;

	}

	return active;

}

function _updateRaytraceEmissiveLights( emissiveBins, cameraX = 0, cameraY = 0, cameraZ = 0, useCameraBias = false ) {

	_rtEmissiveLightCount = 0;
	_rtStaticLightCount = 0;
	_rtDynamicLightCount = 0;
	_rtModelEmitterLightCount = 0;
	if ( emissiveBins == null || emissiveBins.size === 0 ) {

		for ( let i = 0; i < RT_MAX_EMISSIVE_LIGHTS; i ++ )
			_rtEmissiveLightRadius[ i ] = 0;
		return;

	}

	const lights = [];
	for ( const bin of emissiveBins.values() ) {

		if ( bin.weight <= 0.0001 ) continue;
		const invW = 1 / bin.weight;
		const x = bin.x * invW;
		const y = bin.y * invW;
		const z = bin.z * invW;
		const r = bin.r * invW;
		const g = bin.g * invW;
		const b = bin.b * invW;
		const lum = r * 0.2126 + g * 0.7152 + b * 0.0722;
		if ( lum < 0.025 ) continue;

			let distSq = 1e20;
			let proximity = 1.0;
			if ( useCameraBias ) {

				const dx = x - cameraX;
				const dy = y - cameraY;
				const dz = z - cameraZ;
				distSq = dx * dx + dy * dy + dz * dz;
				proximity = 0.08 + 0.92 / ( 1.0 + distSq / ( 260 * 260 ) );

			}
			const score = lum * Math.sqrt( Math.max( bin.weight, 1.0 ) ) * proximity;
			const radius = _clamp( 72 + Math.sqrt( Math.max( bin.weight, 1.0 ) ) * 14, 72, 640 );
			const intensity = _clamp( 0.9 + lum * 3.2, 0.7, 4.8 );
		lights.push( {
			x: x,
			y: y,
			z: z,
			r: r * intensity,
			g: g * intensity,
				b: b * intensity,
				radius: radius,
				score: score,
				distSq: distSq
			} );

		}

		const activeDlights = _countActiveRuntimeDlights();
		const reserveDynamic = Math.min(
			RT_RESERVED_DYNAMIC_LIGHTS,
			Math.max( 2, activeDlights + 2 )
		);
		const reserveModelEmitters = _clampInt( RT_RESERVED_MODEL_EMITTERS, 0, RT_MAX_EMISSIVE_LIGHTS - reserveDynamic );
		const mapLightBudget = Math.max( 1, RT_MAX_EMISSIVE_LIGHTS - reserveDynamic - reserveModelEmitters );
		const count = Math.min( mapLightBudget, lights.length );
		const selectedLights = [];
		if ( useCameraBias && count > 4 && lights.length > count ) {

			const nearBudget = Math.min( count, Math.max( 6, Math.floor( count * 0.45 ) ) );
			const nearLights = lights.slice();
			nearLights.sort( function ( a, b ) {

				return a.distSq - b.distSq;

			} );
			for ( let i = 0; i < nearLights.length && selectedLights.length < nearBudget; i ++ ) {

				selectedLights.push( nearLights[ i ] );

			}

		}

		const rankedLights = lights.slice();
		rankedLights.sort( function ( a, b ) {

			return b.score - a.score;

		} );

		for ( let i = 0; i < rankedLights.length && selectedLights.length < count; i ++ ) {

			const light = rankedLights[ i ];
			if ( selectedLights.indexOf( light ) !== -1 )
				continue;
			selectedLights.push( light );

		}

		const selectedCount = selectedLights.length;
		_rtEmissiveLightCount = selectedCount;
		_rtStaticLightCount = selectedCount;
		for ( let i = 0; i < selectedCount; i ++ ) {

			const light = selectedLights[ i ];
			_rtEmissiveLightPos[ i ].set( light.x, light.y, light.z );
			_rtEmissiveLightColor[ i ].set( light.r, light.g, light.b );
			_rtEmissiveLightRadius[ i ] = light.radius;

		}
		for ( let i = selectedCount; i < RT_MAX_EMISSIVE_LIGHTS; i ++ ) {

		_rtEmissiveLightRadius[ i ] = 0;
		_rtEmissiveLightPos[ i ].set( 0, 0, 0 );
		_rtEmissiveLightColor[ i ].set( 0, 0, 0 );

	}

}

function _isModelEmitterName( modelName ) {

	if ( typeof modelName !== 'string' || modelName.length === 0 )
		return false;

	const lower = modelName.toLowerCase();
	for ( let i = 0; i < _rtEmitterNameHints.length; i ++ ) {

		if ( lower.indexOf( _rtEmitterNameHints[ i ] ) !== -1 )
			return true;

	}

	return false;

}

function _injectRuntimeModelEmittersToRayLights( camera ) {

	let count = _clampInt( _rtStaticLightCount, 0, RT_MAX_EMISSIVE_LIGHTS );
	_rtModelEmitterLightCount = 0;
	_rtEmissiveLightCount = count;

	const reserveDynamic = Math.min(
		RT_RESERVED_DYNAMIC_LIGHTS,
		Math.max( 2, _countActiveRuntimeDlights() + 2 )
	);
	const maxModelSlots = _clampInt(
		RT_MAX_EMISSIVE_LIGHTS - count - reserveDynamic,
		0,
		RT_MAX_EMISSIVE_LIGHTS - count
	);
	if ( maxModelSlots <= 0 )
		return;

	const candidates = [];
	const dedupe = new Set();
	let cameraX = 0;
	let cameraY = 0;
	let cameraZ = 0;
	let hasCamera = false;
	if ( camera != null && camera.getWorldPosition != null ) {

		camera.getWorldPosition( _tmpBvhCamPos );
		cameraX = _tmpBvhCamPos.x;
		cameraY = _tmpBvhCamPos.y;
		cameraZ = _tmpBvhCamPos.z;
		hasCamera = true;

	}

	const now = cl != null && typeof cl.time === 'number' ? cl.time : 0;

	function pushEmitterCandidate( ent ) {

		if ( ent == null || ent.model == null || ent.origin == null )
			return;

		const modelName = ent.model.name != null ? String( ent.model.name ) : '';
		if ( _isModelEmitterName( modelName ) === false )
			return;

		const lower = modelName.toLowerCase();
		const px = _toNumber( ent.origin[ 0 ], 0 );
		const py = _toNumber( ent.origin[ 1 ], 0 );
		const pz = _toNumber( ent.origin[ 2 ], 0 );
		if (
			Number.isFinite( px ) === false ||
			Number.isFinite( py ) === false ||
			Number.isFinite( pz ) === false
		) return;

		const dedupeKey =
			String( Math.round( px * 0.1 ) ) + ':' +
			String( Math.round( py * 0.1 ) ) + ':' +
			String( Math.round( pz * 0.1 ) );
		if ( dedupe.has( dedupeKey ) )
			return;
		dedupe.add( dedupeKey );

		let radius = 180;
		let warmR = 1.18;
		let warmG = 0.78;
		let warmB = 0.42;
		let energy = 1.0;
		if ( lower.indexOf( 'flame2' ) !== -1 ) {

			radius = 240;
			energy = 1.32;

		} else if ( lower.indexOf( 'flame' ) !== -1 ) {

			radius = 205;
			energy = 1.08;

		} else if ( lower.indexOf( 'brazier' ) !== -1 ) {

			radius = 280;
			energy = 1.44;

		} else if ( lower.indexOf( 'torch' ) !== -1 ) {

			radius = 185;
			energy = 0.92;

		} else if ( lower.indexOf( 'candle' ) !== -1 ) {

			radius = 128;
			energy = 0.58;

		} else if ( lower.indexOf( 'lava' ) !== -1 ) {

			radius = 220;
			warmR = 1.05;
			warmG = 0.54;
			warmB = 0.18;
			energy = 1.28;

		} else if ( lower.indexOf( 'fire' ) !== -1 ) {

			radius = 212;
			energy = 1.12;

		}

		const phase = px * 0.013 + py * 0.009 + pz * 0.011;
		const flicker = _clamp(
			0.80 + 0.24 * Math.sin( now * 11.7 + phase ) + 0.18 * _pseudoRandom( phase + now * 7.31 ),
			0.56,
			1.34
		);
		const radiusPulse = _clamp(
			0.90 + 0.22 * Math.sin( now * 4.2 + phase * 0.7 ),
			0.72,
			1.34
		);
		energy *= flicker;
		radius *= radiusPulse;

		let distSq = 0;
		if ( hasCamera ) {

			const dx = px - cameraX;
			const dy = py - cameraY;
			const dz = pz - cameraZ;
			distSq = dx * dx + dy * dy + dz * dz;

		}

		candidates.push( {
			x: px,
			y: py,
			z: pz,
			r: warmR * energy,
			g: warmG * energy,
			b: warmB * energy,
			radius: _clamp( radius, 72, 900 ),
			distSq: distSq,
			score: energy * radius
		} );

	}

	if ( cl_static_entities != null ) {

		const staticCount = _clampInt(
			cl != null && cl.num_statics != null ? cl.num_statics : cl_static_entities.length,
			0,
			cl_static_entities.length
		);
		for ( let i = 0; i < staticCount; i ++ )
			pushEmitterCandidate( cl_static_entities[ i ] );

	}

	if ( cl_entities != null ) {

		const entityCount = _clampInt(
			cl != null && cl.num_entities != null ? cl.num_entities : cl_entities.length,
			0,
			cl_entities.length
		);
		for ( let i = 1; i < entityCount; i ++ )
			pushEmitterCandidate( cl_entities[ i ] );

	}

	if ( candidates.length <= 0 )
		return;

	candidates.sort( function ( a, b ) {

		const scoreDelta = b.score - a.score;
		if ( Math.abs( scoreDelta ) > 0.0001 )
			return scoreDelta;
		return a.distSq - b.distSq;

	} );

	const injectCount = Math.min( maxModelSlots, candidates.length );
	for ( let i = 0; i < injectCount && count < RT_MAX_EMISSIVE_LIGHTS; i ++ ) {

		const emitter = candidates[ i ];
		_rtEmissiveLightPos[ count ].set( emitter.x, emitter.y, emitter.z );
		_rtEmissiveLightColor[ count ].set( emitter.r, emitter.g, emitter.b );
		_rtEmissiveLightRadius[ count ] = emitter.radius;
		count ++;
		_rtModelEmitterLightCount ++;

	}

	_rtEmissiveLightCount = count;

}

function _injectRuntimeDlightsToRayLights() {

	if ( cl_dlights == null )
		return;

	const now = cl != null && typeof cl.time === 'number' ? cl.time : 0;
	let count = _clampInt( _rtStaticLightCount + _rtModelEmitterLightCount, 0, RT_MAX_EMISSIVE_LIGHTS );
	let injected = 0;

	for ( let i = 0; i < cl_dlights.length && count < RT_MAX_EMISSIVE_LIGHTS; i ++ ) {

		const light = cl_dlights[ i ];
		if ( light == null || light.origin == null )
			continue;

		const radius = _toNumber( light.radius, 0 );
		if ( radius <= 12 )
			continue;

		const die = _toNumber( light.die, now + 1.0 );
		if ( die + 0.015 < now )
			continue;

		const timeLeft = Math.max( 0, die - now );
		const fade = _clamp( timeLeft * 3.8, 0.18, 1.0 );
		const energy = _clamp( radius / 190, 0.25, 4.2 ) * fade;
		const px = _toNumber( light.origin[ 0 ], 0 );
		const py = _toNumber( light.origin[ 1 ], 0 );
		const pz = _toNumber( light.origin[ 2 ], 0 );

		_rtEmissiveLightPos[ count ].set( px, py, pz );
		// Quake dynamic lights are predominantly warm (muzzle/explosions/torches).
		_rtEmissiveLightColor[ count ].set( energy * 1.18, energy * 0.78, energy * 0.42 );
		_rtEmissiveLightRadius[ count ] = _clamp( radius * 1.65, 56, 900 );
		count ++;
		injected ++;

	}

	_rtEmissiveLightCount = count;
	_rtDynamicLightCount = injected;
	for ( let i = count; i < RT_MAX_EMISSIVE_LIGHTS; i ++ ) {

		_rtEmissiveLightRadius[ i ] = 0;
		_rtEmissiveLightPos[ i ].set( 0, 0, 0 );
		_rtEmissiveLightColor[ i ].set( 0, 0, 0 );

	}

}

function _collectRaytraceTriangles( scene, maxTriangles, camera ) {

	const triangles = [];
	if ( scene == null ) {

		_updateRaytraceEmissiveLights( null );
		return triangles;

	}

	scene.updateMatrixWorld( true );
	const debugWhite = _rtDebugTexturesEnabled();

	const prioritizeByCamera = camera != null;
	let cameraX = 0;
	let cameraY = 0;
	let cameraZ = 0;
	if ( prioritizeByCamera ) {

		camera.getWorldPosition( _tmpBvhCamPos );
		cameraX = _tmpBvhCamPos.x;
		cameraY = _tmpBvhCamPos.y;
		cameraZ = _tmpBvhCamPos.z;

	}

	const meshEntries = [];
	let sourceTriangleEstimate = 0;
	scene.traverse( function ( object ) {

		if ( object == null || object.isMesh !== true || object.geometry == null ) return;
		if ( object.renderOrder >= 900 ) return;

		const geometry = object.geometry;
		const positions = geometry.attributes != null ? geometry.attributes.position : null;
		if ( positions == null || positions.count < 3 ) return;

		const material = Array.isArray( object.material ) ? object.material[ 0 ] : object.material;
		if ( material == null || material.visible === false ) return;
		if ( material.opacity != null && material.opacity <= 0.001 ) return;

		const index = geometry.index != null ? geometry.index.array : null;
		const triCount = index != null ? Math.floor( index.length / 3 ) : Math.floor( positions.count / 3 );
		if ( triCount > 0 ) {

			sourceTriangleEstimate += triCount;
			meshEntries.push( {
				object: object,
				geometry: geometry,
				positions: positions,
				index: index,
				triCount: triCount,
				material: material,
				cameraDistSq: 0
			} );

		}

	} );

	const overBudget = sourceTriangleEstimate > maxTriangles;
	if ( prioritizeByCamera && overBudget && meshEntries.length > 1 ) {

		for ( let i = 0; i < meshEntries.length; i ++ ) {

			const entry = meshEntries[ i ];
			entry.object.getWorldPosition( _tmpTriangleV0 );
			const dx = _tmpTriangleV0.x - cameraX;
			const dy = _tmpTriangleV0.y - cameraY;
			const dz = _tmpTriangleV0.z - cameraZ;
			entry.cameraDistSq = dx * dx + dy * dy + dz * dz;

		}

		meshEntries.sort( function ( a, b ) {

			return a.cameraDistSq - b.cameraDistSq;

		} );

	}

	let remainingSourceTriangles = sourceTriangleEstimate;
	const emissiveBins = new Map();
	const buildMapWideLights = true;

	function addEmissiveBin( x, y, z, emitR, emitG, emitB, area ) {

		const emitLum = emitR * 0.2126 + emitG * 0.7152 + emitB * 0.0722;
		if ( emitLum <= 0.03 ) return;

		const binScale = 40;
		const bxKey = Math.floor( x / binScale );
		const byKey = Math.floor( y / binScale );
		const bzKey = Math.floor( z / binScale );
		const binKey = bxKey + ':' + byKey + ':' + bzKey;
		let bin = emissiveBins.get( binKey );
		if ( bin == null ) {

			bin = { x: 0, y: 0, z: 0, r: 0, g: 0, b: 0, weight: 0 };
			emissiveBins.set( binKey, bin );

		}

		const weight = Math.max( area, 2.0 ) * emitLum;
		bin.x += x * weight;
		bin.y += y * weight;
		bin.z += z * weight;
		bin.r += emitR * weight;
		bin.g += emitG * weight;
		bin.b += emitB * weight;
		bin.weight += weight;

	}

	if ( buildMapWideLights ) {

		for ( let entryIndex = 0; entryIndex < meshEntries.length; entryIndex ++ ) {

			const entry = meshEntries[ entryIndex ];
			const material = entry.material;
			const emissiveMap = material.emissiveMap != null
				? material.emissiveMap
				: ( material.map != null && material.map._fullbright != null ? material.map._fullbright : null );
			if ( emissiveMap == null ) continue;
			const emissiveSampler = emissiveMap != null ? _getTextureSampler( emissiveMap ) : null;
			if ( emissiveSampler == null ) continue;

			if ( emissiveMap != null && emissiveMap.matrixAutoUpdate === true ) emissiveMap.updateMatrix();

			const geometry = entry.geometry;
			const uv = geometry.attributes != null ? geometry.attributes.uv : null;
			if ( uv == null ) continue;

			const emissive = material.emissive != null ? material.emissive : null;
			const emitScaleR = emissive != null ? _clamp( emissive.r, 0.5, 3.0 ) * 2.2 : 2.2;
			const emitScaleG = emissive != null ? _clamp( emissive.g, 0.5, 3.0 ) * 2.2 : 2.2;
			const emitScaleB = emissive != null ? _clamp( emissive.b, 0.5, 3.0 ) * 2.2 : 2.2;

			const positions = entry.positions;
			const index = entry.index;
			const triCount = entry.triCount;
			const object = entry.object;

			for ( let tri = 0; tri < triCount; tri ++ ) {

				const i0 = index != null ? index[ tri * 3 ] : tri * 3;
				const i1 = index != null ? index[ tri * 3 + 1 ] : tri * 3 + 1;
				const i2 = index != null ? index[ tri * 3 + 2 ] : tri * 3 + 2;

				_tmpTriangleV0.fromBufferAttribute( positions, i0 ).applyMatrix4( object.matrixWorld );
				_tmpTriangleV1.fromBufferAttribute( positions, i1 ).applyMatrix4( object.matrixWorld );
				_tmpTriangleV2.fromBufferAttribute( positions, i2 ).applyMatrix4( object.matrixWorld );

				_tmpEdge1.subVectors( _tmpTriangleV1, _tmpTriangleV0 );
				_tmpEdge2.subVectors( _tmpTriangleV2, _tmpTriangleV0 );
				_tmpNormal.crossVectors( _tmpEdge1, _tmpEdge2 );
				const area = Math.sqrt( _tmpNormal.lengthSq() ) * 0.5;
				if ( area < 0.01 ) continue;

				const u0 = uv.getX( i0 );
				const v0 = uv.getY( i0 );
				const u1 = uv.getX( i1 );
				const v1 = uv.getY( i1 );
				const u2 = uv.getX( i2 );
				const v2 = uv.getY( i2 );

				const s0u = u0 * 0.6 + u1 * 0.2 + u2 * 0.2;
				const s0v = v0 * 0.6 + v1 * 0.2 + v2 * 0.2;
				const s1u = u0 * 0.2 + u1 * 0.6 + u2 * 0.2;
				const s1v = v0 * 0.2 + v1 * 0.6 + v2 * 0.2;
				const s2u = u0 * 0.2 + u1 * 0.2 + u2 * 0.6;
				const s2v = v0 * 0.2 + v1 * 0.2 + v2 * 0.6;
					let sampleCount = 0;
					let peakR = 0;
					let peakG = 0;
					let peakB = 0;
					if ( _sampleTextureRGB( emissiveMap, s0u, s0v, _tmpTexel0 ) ) {

						peakR = Math.max( peakR, _tmpTexel0[ 0 ] );
						peakG = Math.max( peakG, _tmpTexel0[ 1 ] );
						peakB = Math.max( peakB, _tmpTexel0[ 2 ] );
						sampleCount ++;

					}
					if ( _sampleTextureRGB( emissiveMap, s1u, s1v, _tmpTexel1 ) ) {

						peakR = Math.max( peakR, _tmpTexel1[ 0 ] );
						peakG = Math.max( peakG, _tmpTexel1[ 1 ] );
						peakB = Math.max( peakB, _tmpTexel1[ 2 ] );
						sampleCount ++;

					}
					if ( _sampleTextureRGB( emissiveMap, s2u, s2v, _tmpTexel2 ) ) {

						peakR = Math.max( peakR, _tmpTexel2[ 0 ] );
						peakG = Math.max( peakG, _tmpTexel2[ 1 ] );
						peakB = Math.max( peakB, _tmpTexel2[ 2 ] );
						sampleCount ++;

					}
					if ( sampleCount <= 0 ) continue;

					const emitLum = peakR * 0.2126 + peakG * 0.7152 + peakB * 0.0722;
					if ( emitLum <= 0.025 ) continue;

					const emitBoost = _clamp( ( emitLum - 0.025 ) * 2.6, 0.28, 3.2 );
					const emitR = peakR * emitScaleR * emitBoost;
					const emitG = peakG * emitScaleG * emitBoost;
					const emitB = peakB * emitScaleB * emitBoost;

				addEmissiveBin(
					( _tmpTriangleV0.x + _tmpTriangleV1.x + _tmpTriangleV2.x ) / 3,
					( _tmpTriangleV0.y + _tmpTriangleV1.y + _tmpTriangleV2.y ) / 3,
					( _tmpTriangleV0.z + _tmpTriangleV1.z + _tmpTriangleV2.z ) / 3,
					emitR,
					emitG,
					emitB,
					area
				);

			}

		}

			_updateRaytraceEmissiveLights( emissiveBins, cameraX, cameraY, cameraZ, false );

	}

	for ( let entryIndex = 0; entryIndex < meshEntries.length && triangles.length < maxTriangles; entryIndex ++ ) {

		const entry = meshEntries[ entryIndex ];
		const object = entry.object;
		const geometry = entry.geometry;
		const positions = entry.positions;
		const material = entry.material;
		const index = entry.index;
		const triCount = entry.triCount;

		const diffuseMap = material.map != null ? material.map : null;
		const emissiveMap = material.emissiveMap != null
			? material.emissiveMap
			: ( material.map != null && material.map._fullbright != null ? material.map._fullbright : null );
		const lightMap = material.lightMap != null ? material.lightMap : null;
		const diffuseSampler = diffuseMap != null ? _getTextureSampler( diffuseMap ) : null;
		const emissiveSampler = emissiveMap != null ? _getTextureSampler( emissiveMap ) : null;
		const lightMapSampler = lightMap != null ? _getTextureSampler( lightMap ) : null;
		const uv = geometry.attributes != null ? geometry.attributes.uv : null;
		const uv1 = geometry.attributes != null ? geometry.attributes.uv1 : null;
		const uv2 = geometry.attributes != null ? geometry.attributes.uv2 : null;
		const colorAttr = geometry.attributes != null ? geometry.attributes.color : null;
		const lightMapUv = lightMap == null
			? null
			: ( lightMap.channel === 1 ? ( uv1 != null ? uv1 : uv2 ) : uv );

		if ( diffuseMap != null && diffuseMap.matrixAutoUpdate === true ) diffuseMap.updateMatrix();
		if ( emissiveMap != null && emissiveMap.matrixAutoUpdate === true ) emissiveMap.updateMatrix();
		if ( lightMap != null && lightMap.matrixAutoUpdate === true ) lightMap.updateMatrix();

		const color = material != null && material.color != null ? material.color : null;
		const tintR = color != null ? _clamp( color.r, 0.0, 2.0 ) : 1.0;
		const tintG = color != null ? _clamp( color.g, 0.0, 2.0 ) : 1.0;
		const tintB = color != null ? _clamp( color.b, 0.0, 2.0 ) : 1.0;
		const emissive = material != null && material.emissive != null ? material.emissive : null;
		const emissiveR = emissive != null ? _clamp( emissive.r, 0.0, 2.0 ) : 0.0;
		const emissiveG = emissive != null ? _clamp( emissive.g, 0.0, 2.0 ) : 0.0;
		const emissiveB = emissive != null ? _clamp( emissive.b, 0.0, 2.0 ) : 0.0;

		let triOrder = null;
		if ( prioritizeByCamera && overBudget && triCount > 64 ) {

			const triDist = new Float32Array( triCount );
			triOrder = new Array( triCount );
			for ( let t = 0; t < triCount; t ++ ) {

				triOrder[ t ] = t;
				const i0 = index != null ? index[ t * 3 ] : t * 3;
				_tmpTriangleV0.fromBufferAttribute( positions, i0 ).applyMatrix4( object.matrixWorld );
				const dx = _tmpTriangleV0.x - cameraX;
				const dy = _tmpTriangleV0.y - cameraY;
				const dz = _tmpTriangleV0.z - cameraZ;
				triDist[ t ] = dx * dx + dy * dy + dz * dz;

			}
			triOrder.sort( function ( a, b ) {

				return triDist[ a ] - triDist[ b ];

			} );

		}

			function sampleMaterialAt( u, v, lu, lv, colorScaleR, colorScaleG, colorScaleB, outAlbedo, outEmission ) {

			let albedoR = debugWhite ? 1.0 : tintR * colorScaleR;
			let albedoG = debugWhite ? 1.0 : tintG * colorScaleG;
			let albedoB = debugWhite ? 1.0 : tintB * colorScaleB;
			let emitR = 0;
			let emitG = 0;
			let emitB = 0;

				if ( diffuseSampler != null && uv != null ) {

					if ( _sampleTextureRGB( diffuseMap, u, v, _tmpTexel0 ) ) {

						if ( debugWhite === false ) {

						albedoR *= _tmpTexel0[ 0 ];
						albedoG *= _tmpTexel0[ 1 ];
						albedoB *= _tmpTexel0[ 2 ];

						}

					}

				}

			// Raytrace DWT replaces legacy Quake lightmaps, so keep albedo unlit here.

				if ( emissiveSampler != null && uv != null ) {

					if ( _sampleTextureRGB( emissiveMap, u, v, _tmpTexel2 ) ) {

						const emitLum = _tmpTexel2[ 0 ] * 0.2126 + _tmpTexel2[ 1 ] * 0.7152 + _tmpTexel2[ 2 ] * 0.0722;
						if ( emitLum > 0.05 ) {

							const emitBoost = _clamp( ( emitLum - 0.05 ) * 3.0, 0.20, 3.0 );
							emitR += _tmpTexel2[ 0 ] * Math.max( emissiveR, 0.65 ) * emitBoost;
							emitG += _tmpTexel2[ 1 ] * Math.max( emissiveG, 0.65 ) * emitBoost;
							emitB += _tmpTexel2[ 2 ] * Math.max( emissiveB, 0.65 ) * emitBoost;

						}

					}

				}

			outAlbedo[ 0 ] = _clamp( albedoR, 0.01, 2.5 );
			outAlbedo[ 1 ] = _clamp( albedoG, 0.01, 2.5 );
			outAlbedo[ 2 ] = _clamp( albedoB, 0.01, 2.5 );
			outEmission[ 0 ] = _clamp( emitR, 0.0, 6.0 );
			outEmission[ 1 ] = _clamp( emitG, 0.0, 6.0 );
			outEmission[ 2 ] = _clamp( emitB, 0.0, 6.0 );

		}

		for ( let triIter = 0; triIter < triCount && triangles.length < maxTriangles; triIter ++ ) {

			const tri = triOrder != null ? triOrder[ triIter ] : triIter;

			if ( remainingSourceTriangles > 0 )
				remainingSourceTriangles --;

			const i0 = index != null ? index[ tri * 3 ] : tri * 3;
			const i1 = index != null ? index[ tri * 3 + 1 ] : tri * 3 + 1;
			const i2 = index != null ? index[ tri * 3 + 2 ] : tri * 3 + 2;

			_tmpTriangleV0.fromBufferAttribute( positions, i0 ).applyMatrix4( object.matrixWorld );
			_tmpTriangleV1.fromBufferAttribute( positions, i1 ).applyMatrix4( object.matrixWorld );
			_tmpTriangleV2.fromBufferAttribute( positions, i2 ).applyMatrix4( object.matrixWorld );

			_tmpEdge1.subVectors( _tmpTriangleV1, _tmpTriangleV0 );
			_tmpEdge2.subVectors( _tmpTriangleV2, _tmpTriangleV0 );
			_tmpNormal.crossVectors( _tmpEdge1, _tmpEdge2 );
			if ( _tmpNormal.lengthSq() < 1e-8 ) continue;

			const p0x = _tmpTriangleV0.x;
			const p0y = _tmpTriangleV0.y;
			const p0z = _tmpTriangleV0.z;
			const p1x = _tmpTriangleV1.x;
			const p1y = _tmpTriangleV1.y;
			const p1z = _tmpTriangleV1.z;
			const p2x = _tmpTriangleV2.x;
			const p2y = _tmpTriangleV2.y;
			const p2z = _tmpTriangleV2.z;

			const hasUv = uv != null;
			const hasLightUv = lightMapUv != null;
			const hasVertexColor = colorAttr != null;

			const u0 = hasUv ? uv.getX( i0 ) : 0;
			const v0 = hasUv ? uv.getY( i0 ) : 0;
			const u1v = hasUv ? uv.getX( i1 ) : 0;
			const v1v = hasUv ? uv.getY( i1 ) : 0;
			const u2v = hasUv ? uv.getX( i2 ) : 0;
			const v2v = hasUv ? uv.getY( i2 ) : 0;

			const lu0 = hasLightUv ? lightMapUv.getX( i0 ) : 0;
			const lv0 = hasLightUv ? lightMapUv.getY( i0 ) : 0;
			const lu1 = hasLightUv ? lightMapUv.getX( i1 ) : 0;
			const lv1 = hasLightUv ? lightMapUv.getY( i1 ) : 0;
			const lu2 = hasLightUv ? lightMapUv.getX( i2 ) : 0;
			const lv2 = hasLightUv ? lightMapUv.getY( i2 ) : 0;

			const c0r = hasVertexColor ? colorAttr.getX( i0 ) : 1;
			const c0g = hasVertexColor ? colorAttr.getY( i0 ) : 1;
			const c0b = hasVertexColor ? colorAttr.getZ( i0 ) : 1;
			const c1r = hasVertexColor ? colorAttr.getX( i1 ) : 1;
			const c1g = hasVertexColor ? colorAttr.getY( i1 ) : 1;
			const c1b = hasVertexColor ? colorAttr.getZ( i1 ) : 1;
			const c2r = hasVertexColor ? colorAttr.getX( i2 ) : 1;
			const c2g = hasVertexColor ? colorAttr.getY( i2 ) : 1;
			const c2b = hasVertexColor ? colorAttr.getZ( i2 ) : 1;

			let subdiv = 1;
			if ( diffuseSampler != null && hasUv ) {

				const uvArea = Math.abs( ( u1v - u0 ) * ( v2v - v0 ) - ( u2v - u0 ) * ( v1v - v0 ) );
				const texelArea = uvArea * diffuseSampler.width * diffuseSampler.height;
				if ( texelArea > 1.0 )
					subdiv = Math.max( subdiv, Math.ceil( Math.sqrt( texelArea / 48.0 ) ) );

			}
			if ( lightMapSampler != null && hasLightUv ) {

				const uvArea = Math.abs( ( lu1 - lu0 ) * ( lv2 - lv0 ) - ( lu2 - lu0 ) * ( lv1 - lv0 ) );
				const texelArea = uvArea * lightMapSampler.width * lightMapSampler.height;
				if ( texelArea > 1.0 )
					subdiv = Math.max( subdiv, Math.ceil( Math.sqrt( texelArea / 20.0 ) ) );

			}

			subdiv = _clampInt( subdiv, 1, 10 );
			// Reserve at least one triangle slot for every unprocessed source triangle
			// so nearby walls do not disappear when subdivision is high.
			const budgetLeft = maxTriangles - triangles.length;
			const maxForCurrentSource = budgetLeft - remainingSourceTriangles;
			const maxSubdivFromReserve = Math.max( 1, Math.floor( Math.sqrt( Math.max( 1, maxForCurrentSource ) ) ) );
			if ( subdiv > maxSubdivFromReserve ) subdiv = maxSubdivFromReserve;

			const remaining = maxTriangles - triangles.length;
			if ( remaining <= 0 ) break;

			const maxSubdivFromBudget = Math.max( 1, Math.floor( Math.sqrt( remaining ) ) );
			if ( subdiv > maxSubdivFromBudget ) subdiv = maxSubdivFromBudget;

			const invSubdiv = 1 / subdiv;

			function emitSubTriangle( a0, a1, a2, b0, b1, b2, c0, c1, c2 ) {

				const ax = p0x * a0 + p1x * a1 + p2x * a2;
				const ay = p0y * a0 + p1y * a1 + p2y * a2;
				const az = p0z * a0 + p1z * a1 + p2z * a2;
				const bx = p0x * b0 + p1x * b1 + p2x * b2;
				const by = p0y * b0 + p1y * b1 + p2y * b2;
				const bz = p0z * b0 + p1z * b1 + p2z * b2;
				const cx = p0x * c0 + p1x * c1 + p2x * c2;
				const cy = p0y * c0 + p1y * c1 + p2y * c2;
				const cz = p0z * c0 + p1z * c1 + p2z * c2;

				const e1x = bx - ax;
				const e1y = by - ay;
				const e1z = bz - az;
				const e2x = cx - ax;
				const e2y = cy - ay;
				const e2z = cz - az;
				const nx = e1y * e2z - e1z * e2y;
				const ny = e1z * e2x - e1x * e2z;
				const nz = e1x * e2y - e1y * e2x;
				if ( ( nx * nx + ny * ny + nz * nz ) < 1e-10 ) return;

				const w0 = ( a0 + b0 + c0 ) / 3;
				const w1 = ( a1 + b1 + c1 ) / 3;
				const w2 = ( a2 + b2 + c2 ) / 3;

				const uc = u0 * w0 + u1v * w1 + u2v * w2;
				const vc = v0 * w0 + v1v * w1 + v2v * w2;
				const luc = lu0 * w0 + lu1 * w1 + lu2 * w2;
				const lvc = lv0 * w0 + lv1 * w1 + lv2 * w2;

					const colorScaleR = _clamp( c0r * w0 + c1r * w1 + c2r * w2, 0.0, 2.0 );
					const colorScaleG = _clamp( c0g * w0 + c1g * w1 + c2g * w2, 0.0, 2.0 );
					const colorScaleB = _clamp( c0b * w0 + c1b * w1 + c2b * w2, 0.0, 2.0 );
					sampleMaterialAt( uc, vc, luc, lvc, colorScaleR, colorScaleG, colorScaleB, _tmpSampleAlbedo, _tmpSampleEmission );

					triangles.push( {
						v0: [ ax, ay, az ],
						v1: [ bx, by, bz ],
						v2: [ cx, cy, cz ],
						centroid: [ ( ax + bx + cx ) / 3, ( ay + by + cy ) / 3, ( az + bz + cz ) / 3 ],
						albedo: [ _tmpSampleAlbedo[ 0 ], _tmpSampleAlbedo[ 1 ], _tmpSampleAlbedo[ 2 ] ],
						emissive: [ _tmpSampleEmission[ 0 ], _tmpSampleEmission[ 1 ], _tmpSampleEmission[ 2 ] ]
					} );

			}

			for ( let row = 0; row < subdiv && triangles.length < maxTriangles; row ++ ) {

				for ( let col = 0; col < ( subdiv - row ) && triangles.length < maxTriangles; col ++ ) {

					const a0 = 1 - ( row + col ) * invSubdiv;
					const a1 = row * invSubdiv;
					const a2 = col * invSubdiv;
					const b0 = 1 - ( row + col + 1 ) * invSubdiv;
					const b1 = ( row + 1 ) * invSubdiv;
					const b2 = col * invSubdiv;
					const c0 = 1 - ( row + col + 1 ) * invSubdiv;
					const c1 = row * invSubdiv;
					const c2 = ( col + 1 ) * invSubdiv;

					emitSubTriangle( a0, a1, a2, b0, b1, b2, c0, c1, c2 );
					if ( triangles.length >= maxTriangles ) break;

					if ( row + col < subdiv - 1 ) {

						const d0 = 1 - ( row + col + 2 ) * invSubdiv;
						const d1 = ( row + 1 ) * invSubdiv;
						const d2 = ( col + 1 ) * invSubdiv;
						emitSubTriangle( b0, b1, b2, d0, d1, d2, c0, c1, c2 );

					}

				}

			}

		}

	}

	return triangles;

}

function _computeTriangleBounds( triangles, indices ) {

	const min = [ Infinity, Infinity, Infinity ];
	const max = [ - Infinity, - Infinity, - Infinity ];
	const centroidMin = [ Infinity, Infinity, Infinity ];
	const centroidMax = [ - Infinity, - Infinity, - Infinity ];

	for ( let i = 0; i < indices.length; i ++ ) {

		const tri = triangles[ indices[ i ] ];
		const v0 = tri.v0;
		const v1 = tri.v1;
		const v2 = tri.v2;

		for ( let axis = 0; axis < 3; axis ++ ) {

			const lo = Math.min( v0[ axis ], Math.min( v1[ axis ], v2[ axis ] ) );
			const hi = Math.max( v0[ axis ], Math.max( v1[ axis ], v2[ axis ] ) );
			if ( lo < min[ axis ] ) min[ axis ] = lo;
			if ( hi > max[ axis ] ) max[ axis ] = hi;

			const c = tri.centroid[ axis ];
			if ( c < centroidMin[ axis ] ) centroidMin[ axis ] = c;
			if ( c > centroidMax[ axis ] ) centroidMax[ axis ] = c;

		}

	}

	return { min: min, max: max, centroidMin: centroidMin, centroidMax: centroidMax };

}

function _buildRaytraceBvh( triangles ) {

	const nodes = [];
	const orderedTriangleIndices = [];

	function buildNode( triIndices, depth ) {

		const bounds = _computeTriangleBounds( triangles, triIndices );
		const nodeIndex = nodes.length;
		const node = {
			min: bounds.min,
			max: bounds.max,
			left: - 1,
			right: - 1,
			triStart: 0,
			triCount: 0,
			isLeaf: false
		};
		nodes.push( node );

		if ( triIndices.length <= RT_LEAF_TRIANGLES || depth >= RT_MAX_BVH_DEPTH ) {

			node.isLeaf = true;
			node.triStart = orderedTriangleIndices.length;
			node.triCount = triIndices.length;
			for ( let i = 0; i < triIndices.length; i ++ ) {

				orderedTriangleIndices.push( triIndices[ i ] );

			}
			return nodeIndex;

		}

		let axis = 0;
		let extent = bounds.centroidMax[ 0 ] - bounds.centroidMin[ 0 ];
		for ( let testAxis = 1; testAxis < 3; testAxis ++ ) {

			const testExtent = bounds.centroidMax[ testAxis ] - bounds.centroidMin[ testAxis ];
			if ( testExtent > extent ) {

				axis = testAxis;
				extent = testExtent;

			}

		}

		triIndices.sort( function ( a, b ) {

			return triangles[ a ].centroid[ axis ] - triangles[ b ].centroid[ axis ];

		} );

		const split = triIndices.length >> 1;
		if ( split <= 0 || split >= triIndices.length ) {

			node.isLeaf = true;
			node.triStart = orderedTriangleIndices.length;
			node.triCount = triIndices.length;
			for ( let i = 0; i < triIndices.length; i ++ ) {

				orderedTriangleIndices.push( triIndices[ i ] );

			}
			return nodeIndex;

		}

		const leftIndices = triIndices.slice( 0, split );
		const rightIndices = triIndices.slice( split );
		node.left = buildNode( leftIndices, depth + 1 );
		node.right = buildNode( rightIndices, depth + 1 );

		return nodeIndex;

	}

	const rootIndices = new Array( triangles.length );
	for ( let i = 0; i < triangles.length; i ++ )
		rootIndices[ i ] = i;
	buildNode( rootIndices, 0 );

	return { nodes: nodes, orderedTriangleIndices: orderedTriangleIndices };

}

function _uploadRaytraceBvh( triangles, bvh ) {

	const orderedTriangles = new Array( bvh.orderedTriangleIndices.length );
	for ( let i = 0; i < bvh.orderedTriangleIndices.length; i ++ ) {

		orderedTriangles[ i ] = triangles[ bvh.orderedTriangleIndices[ i ] ];

	}

	const triCount = orderedTriangles.length;
	const triTexelCount = Math.max( 1, triCount * 4 );
	const triWidth = RT_TEX_WIDTH;
	const triHeight = Math.max( 1, Math.ceil( triTexelCount / triWidth ) );
	const triData = new Float32Array( triWidth * triHeight * 4 );

	for ( let triIndex = 0; triIndex < triCount; triIndex ++ ) {

		const tri = orderedTriangles[ triIndex ];
		const baseTexel = triIndex * 4;
		const offset0 = baseTexel * 4;
		const offset1 = ( baseTexel + 1 ) * 4;
		const offset2 = ( baseTexel + 2 ) * 4;
		const offset3 = ( baseTexel + 3 ) * 4;

		triData[ offset0 ] = tri.v0[ 0 ];
		triData[ offset0 + 1 ] = tri.v0[ 1 ];
		triData[ offset0 + 2 ] = tri.v0[ 2 ];
		triData[ offset0 + 3 ] = tri.albedo[ 0 ];

		triData[ offset1 ] = tri.v1[ 0 ];
		triData[ offset1 + 1 ] = tri.v1[ 1 ];
		triData[ offset1 + 2 ] = tri.v1[ 2 ];
		triData[ offset1 + 3 ] = tri.albedo[ 1 ];

		triData[ offset2 ] = tri.v2[ 0 ];
		triData[ offset2 + 1 ] = tri.v2[ 1 ];
		triData[ offset2 + 2 ] = tri.v2[ 2 ];
		triData[ offset2 + 3 ] = tri.albedo[ 2 ];

		triData[ offset3 ] = tri.emissive != null ? tri.emissive[ 0 ] : 0;
		triData[ offset3 + 1 ] = tri.emissive != null ? tri.emissive[ 1 ] : 0;
		triData[ offset3 + 2 ] = tri.emissive != null ? tri.emissive[ 2 ] : 0;
		triData[ offset3 + 3 ] = 1;

	}

	const nodes = bvh.nodes;
	const nodeCount = nodes.length;
	const nodeTexelCount = Math.max( 1, nodeCount * 2 );
	const nodeWidth = RT_TEX_WIDTH;
	const nodeHeight = Math.max( 1, Math.ceil( nodeTexelCount / nodeWidth ) );
	const nodeData = new Float32Array( nodeWidth * nodeHeight * 4 );

	for ( let nodeIndex = 0; nodeIndex < nodeCount; nodeIndex ++ ) {

		const node = nodes[ nodeIndex ];
		const texel = nodeIndex * 2;
		const offset0 = texel * 4;
		const offset1 = ( texel + 1 ) * 4;

		nodeData[ offset0 ] = node.min[ 0 ];
		nodeData[ offset0 + 1 ] = node.min[ 1 ];
		nodeData[ offset0 + 2 ] = node.min[ 2 ];
		nodeData[ offset0 + 3 ] = node.isLeaf ? - node.triCount : node.left;

		nodeData[ offset1 ] = node.max[ 0 ];
		nodeData[ offset1 + 1 ] = node.max[ 1 ];
		nodeData[ offset1 + 2 ] = node.max[ 2 ];
		nodeData[ offset1 + 3 ] = node.isLeaf ? node.triStart : node.right;

	}

	if ( _bvhTriTexture != null ) _bvhTriTexture.dispose();
	if ( _bvhNodeTexture != null ) _bvhNodeTexture.dispose();

	_bvhTriTexture = _createFloatDataTexture( triData, triWidth, triHeight );
	_bvhNodeTexture = _createFloatDataTexture( nodeData, nodeWidth, nodeHeight );
	_bvhTriTexSize.set( triWidth, triHeight );
	_bvhNodeTexSize.set( nodeWidth, nodeHeight );
	_bvhTriCount = triCount;
	_bvhNodeCount = nodeCount;
	_bvhReady = triCount > 0 && nodeCount > 0;

}

function _ensureRaytraceBvh( scene, camera ) {

	const maxTriangles = _clampInt( r_quantum_rt_tris.value, 512, 131072 );
	const debugWhite = _rtDebugTexturesEnabled() ? 1 : 0;
	let cameraKey = '0:0:0';
	if ( camera != null ) {

		camera.getWorldPosition( _tmpBvhCamPos );
		const cx = Math.floor( _tmpBvhCamPos.x / 192 );
		const cy = Math.floor( _tmpBvhCamPos.y / 192 );
		const cz = Math.floor( _tmpBvhCamPos.z / 128 );
		cameraKey = String( cx ) + ':' + String( cy ) + ':' + String( cz );

	}
	const signature = String( scene != null && scene.children != null ? scene.children.length : 0 ) + ':' + maxTriangles + ':' + cameraKey + ':' + debugWhite;
	const lightSignature = String( scene != null && scene.children != null ? scene.children.length : 0 ) + ':' + maxTriangles;
	if ( _rtLightBuildSignature !== lightSignature ) {

		_rtLightBuildSignature = lightSignature;
		_rtEmissiveLightCount = 0;
		_rtStaticLightCount = 0;
		_rtDynamicLightCount = 0;
		_rtModelEmitterLightCount = 0;

	}
	const rebuildInterval = _bvhClipped ? 8 : RT_BVH_REBUILD_INTERVAL;
	if (
		_bvhReady === true &&
		signature === _bvhSignature &&
		_frameCounter - _bvhLastBuildFrame < rebuildInterval
	) {

		return true;

	}

	const start = performance.now();
	const triangles = _collectRaytraceTriangles( scene, maxTriangles, camera );
	if ( triangles.length === 0 ) {

		_disposeBvhTextures();
		return false;

	}
	_bvhClipped = triangles.length >= maxTriangles;

	const bvh = _buildRaytraceBvh( triangles );
	_uploadRaytraceBvh( triangles, bvh );
	_lastBvhBuildMs = performance.now() - start;
	_bvhSignature = signature;
	_bvhLastBuildFrame = _frameCounter;
	return _bvhReady;

}

function _setupRaytraceCameraUniforms( camera ) {

	if ( camera == null || _rayTraceMaterial == null ) return;

	camera.getWorldPosition( _rayCamPos );
	camera.getWorldDirection( _rayCamForward );
	_rayCamForward.normalize();
	_rayCamRight.setFromMatrixColumn( camera.matrixWorld, 0 ).normalize();
	_rayCamUp.setFromMatrixColumn( camera.matrixWorld, 1 ).normalize();

	const tanHalfFov = Math.tan( THREE.MathUtils.degToRad( camera.fov * 0.5 ) );
	const aspect = camera.aspect > 0 ? camera.aspect : ( _sceneTarget != null ? _sceneTarget.width / Math.max( 1, _sceneTarget.height ) : 1 );

	const uniforms = _rayTraceMaterial.uniforms;
	uniforms.uCamPos.value.copy( _rayCamPos );
	uniforms.uCamRight.value.copy( _rayCamRight );
	uniforms.uCamUp.value.copy( _rayCamUp );
	uniforms.uCamForward.value.copy( _rayCamForward );
	uniforms.uTanHalfFov.value = tanHalfFov;
	uniforms.uAspect.value = aspect;

}

function _registerCvars() {

	if ( _cvarsRegistered ) return;
	_cvarsRegistered = true;

	Cvar_RegisterVariable( r_quantum );
	Cvar_RegisterVariable( r_quantum_mode );
	Cvar_RegisterVariable( r_quantum_qubits );
	Cvar_RegisterVariable( r_quantum_depth );
	Cvar_RegisterVariable( r_quantum_spp );
	Cvar_RegisterVariable( r_quantum_bounces );
	Cvar_RegisterVariable( r_quantum_bundle );
	Cvar_RegisterVariable( r_quantum_rt_tris );
	Cvar_RegisterVariable( r_quantum_rt_debugtex );
	Cvar_RegisterVariable( r_quantum_wavelet );
	Cvar_RegisterVariable( r_quantum_strength );
	Cvar_RegisterVariable( r_quantum_gain );
	Cvar_RegisterVariable( r_quantum_exposure );

}

function _buildPostResources() {

	if ( _postScene != null ) return;

	_phaseTexture = new THREE.DataTexture(
		_phaseData,
		PHASE_TEXTURE_SIZE,
		PHASE_TEXTURE_SIZE,
		THREE.RGBAFormat,
		THREE.UnsignedByteType
	);
	_phaseTexture.wrapS = THREE.RepeatWrapping;
	_phaseTexture.wrapT = THREE.RepeatWrapping;
	_phaseTexture.magFilter = THREE.LinearFilter;
	_phaseTexture.minFilter = THREE.LinearFilter;
	_phaseTexture.needsUpdate = true;

	_postScene = new THREE.Scene();
	_postCamera = new THREE.OrthographicCamera( - 1, 1, 1, - 1, 0, 1 );

	_accumMaterial = new THREE.ShaderMaterial( {
		uniforms: {
			uBaseTex: { value: null },
			uPrevAccumTex: { value: null },
			uPhaseTex: { value: _phaseTexture },
			uFrame: { value: 0 },
			uSpp: { value: 3 },
			uBounces: { value: 2 },
			uStrength: { value: 1.2 },
			uCollapseMix: { value: 0.15 },
			uCollapseSeed: { value: 0 },
			uPixelStep: { value: new THREE.Vector2( 1 / 640, 1 / 480 ) }
		},
		vertexShader: _fullscreenVertex,
		fragmentShader: _accumFragment,
		depthWrite: false,
		depthTest: false
	} );

	_composeMaterial = new THREE.ShaderMaterial( {
		uniforms: {
			uBaseTex: { value: null },
			uAccumTex: { value: null },
			uPhaseTex: { value: _phaseTexture },
			uMode: { value: 1 },
			uStrength: { value: 1.2 },
			uGain: { value: 1.10 },
			uExposure: { value: 2.5 },
			uFrame: { value: 0 },
			uCollapseSeed: { value: 0 }
		},
		vertexShader: _fullscreenVertex,
		fragmentShader: _composeFragment,
		depthWrite: false,
		depthTest: false
	} );

	_rayTraceMaterial = new THREE.ShaderMaterial( {
		uniforms: {
			uBaseTex: { value: null },
			uDepthTex: { value: null },
			uTriTex: { value: null },
			uNodeTex: { value: null },
			uTriTexSize: { value: _bvhTriTexSize.clone() },
			uNodeTexSize: { value: _bvhNodeTexSize.clone() },
			uTriCount: { value: 0 },
			uNodeCount: { value: 0 },
			uCamPos: { value: new THREE.Vector3() },
			uCamRight: { value: new THREE.Vector3( 1, 0, 0 ) },
			uCamUp: { value: new THREE.Vector3( 0, 1, 0 ) },
			uCamForward: { value: new THREE.Vector3( 0, 0, - 1 ) },
			uTanHalfFov: { value: 0.6 },
			uAspect: { value: 1.0 },
			uCameraNear: { value: 1.0 },
			uCameraFar: { value: 8192.0 },
			uEmissiveLightCount: { value: 0 },
			uEmissiveLightPos: { value: _rtEmissiveLightPos },
			uEmissiveLightColor: { value: _rtEmissiveLightColor },
			uEmissiveLightRadius: { value: _rtEmissiveLightRadius },
			uFrame: { value: 0 },
			uSpp: { value: 2 },
			uBounces: { value: 2 },
			uStrength: { value: 1.0 },
			uDebugWhite: { value: 0 },
			uPixelStep: { value: new THREE.Vector2( 1 / 640, 1 / 480 ) }
		},
		vertexShader: _fullscreenVertex,
		fragmentShader: _raytraceFragment,
		depthWrite: false,
		depthTest: false
	} );

	_waveletMaterial = new THREE.ShaderMaterial( {
		uniforms: {
			uInputTex: { value: null },
			uPixelStep: { value: new THREE.Vector2( 1 / 640, 1 / 480 ) },
			uThreshold: { value: 0.075 }
		},
		vertexShader: _fullscreenVertex,
		fragmentShader: _waveletFragment,
		depthWrite: false,
		depthTest: false
	} );

	_rayCompositeMaterial = new THREE.ShaderMaterial( {
		uniforms: {
			uBaseTex: { value: null },
			uRayTex: { value: null },
			uStrength: { value: 1.0 },
			uGain: { value: 1.10 },
			uExposure: { value: 2.5 },
			uDebugWhite: { value: 0 }
		},
		vertexShader: _fullscreenVertex,
		fragmentShader: _rayCompositeFragment,
		depthWrite: false,
		depthTest: false
	} );

	_postQuad = new THREE.Mesh( new THREE.PlaneGeometry( 2, 2 ), _accumMaterial );
	_postScene.add( _postQuad );

}

function _disposeRenderTargets() {

	if ( _sceneTarget != null ) {

		_sceneTarget.dispose();
		_sceneTarget = null;

	}

	for ( let i = 0; i < 2; i ++ ) {

		if ( _accumTargets[ i ] != null ) {

			_accumTargets[ i ].dispose();
			_accumTargets[ i ] = null;

		}

	}

	if ( _rayTraceTarget != null ) {

		_rayTraceTarget.dispose();
		_rayTraceTarget = null;

	}

	if ( _waveletTarget != null ) {

		_waveletTarget.dispose();
		_waveletTarget = null;

	}

}

function _clearAccumTargets() {

	if (
		renderer == null ||
		_accumTargets[ 0 ] == null ||
		_accumTargets[ 1 ] == null ||
		_rayTraceTarget == null ||
		_waveletTarget == null
	)
		return;

	const oldTarget = renderer.getRenderTarget();
	const oldAlpha = renderer.getClearAlpha();
	renderer.getClearColor( _savedClearColor );

	renderer.setClearColor( 0x808080, 1 );

	renderer.setRenderTarget( _accumTargets[ 0 ] );
	renderer.clear( true, false, false );

	renderer.setRenderTarget( _accumTargets[ 1 ] );
	renderer.clear( true, false, false );

	renderer.setRenderTarget( _rayTraceTarget );
	renderer.clear( true, false, false );

	renderer.setRenderTarget( _waveletTarget );
	renderer.clear( true, false, false );

	renderer.setRenderTarget( oldTarget );
	renderer.setClearColor( _savedClearColor, oldAlpha );

	_accumPing = 0;

}

function _ensureRenderTargets() {

	if ( renderer == null ) return false;

	renderer.getDrawingBufferSize( _rtSize );
	const bundle = _clampInt( r_quantum_bundle.value, 1, 10 );
	const targetWidth = Math.max( 1, Math.floor( _rtSize.x / bundle ) );
	const targetHeight = Math.max( 1, Math.floor( _rtSize.y / bundle ) );
	const targetFilter = bundle > 1 ? THREE.NearestFilter : THREE.LinearFilter;

	if ( targetWidth <= 0 || targetHeight <= 0 )
		return false;

	if (
		_sceneTarget != null &&
		_sceneTarget.width === targetWidth &&
		_sceneTarget.height === targetHeight
	) {

		return true;

	}

	_disposeRenderTargets();

	_sceneTarget = new THREE.WebGLRenderTarget( targetWidth, targetHeight, {
		format: THREE.RGBAFormat,
		type: THREE.UnsignedByteType,
		minFilter: targetFilter,
		magFilter: targetFilter,
		depthBuffer: true,
		stencilBuffer: false
	} );
	_sceneTarget.texture.generateMipmaps = false;
	_sceneTarget.depthTexture = new THREE.DepthTexture( targetWidth, targetHeight, THREE.UnsignedShortType );
	_sceneTarget.depthTexture.minFilter = THREE.NearestFilter;
	_sceneTarget.depthTexture.magFilter = THREE.NearestFilter;
	_sceneTarget.depthTexture.wrapS = THREE.ClampToEdgeWrapping;
	_sceneTarget.depthTexture.wrapT = THREE.ClampToEdgeWrapping;

	for ( let i = 0; i < 2; i ++ ) {

		_accumTargets[ i ] = new THREE.WebGLRenderTarget( targetWidth, targetHeight, {
			format: THREE.RGBAFormat,
			type: THREE.UnsignedByteType,
			minFilter: targetFilter,
			magFilter: targetFilter,
			depthBuffer: false,
			stencilBuffer: false
		} );
		_accumTargets[ i ].texture.generateMipmaps = false;

	}

	_rayTraceTarget = new THREE.WebGLRenderTarget( targetWidth, targetHeight, {
		format: THREE.RGBAFormat,
		type: THREE.UnsignedByteType,
		minFilter: targetFilter,
		magFilter: targetFilter,
		depthBuffer: false,
		stencilBuffer: false
	} );
	_rayTraceTarget.texture.generateMipmaps = false;

	_waveletTarget = new THREE.WebGLRenderTarget( targetWidth, targetHeight, {
		format: THREE.RGBAFormat,
		type: THREE.UnsignedByteType,
		minFilter: targetFilter,
		magFilter: targetFilter,
		depthBuffer: false,
		stencilBuffer: false
	} );
	_waveletTarget.texture.generateMipmaps = false;

	_accumMaterial.uniforms.uPixelStep.value.set( 1 / targetWidth, 1 / targetHeight );
	_rayTraceMaterial.uniforms.uPixelStep.value.set( 1 / targetWidth, 1 / targetHeight );
	_waveletMaterial.uniforms.uPixelStep.value.set( 1 / targetWidth, 1 / targetHeight );
	_clearAccumTargets();
	return true;

}

function _initMoonlab() {

	if ( _moonlabModule != null || _moonlabInitPromise != null || _moonlabFailed )
		return;

	if ( typeof window === 'undefined' ) {

		_moonlabFailed = true;
		return;

	}

	const factory = window.MoonlabModule;
	if ( typeof factory !== 'function' ) {

		_moonlabFailed = true;
		Con_Printf( 'Quantum renderer: moonlab.js not found, using fallback noise\n' );
		return;

	}

	_moonlabInitPromise = factory( {
		locateFile: function ( file, scriptDirectory ) {

			if ( file.endsWith( '.wasm' ) )
				return 'moonlab.wasm';
			return ( scriptDirectory || '' ) + file;

		}
	} )
		.then( function ( module ) {

			_moonlabModule = module;
			if ( module.ready && typeof module.ready.then === 'function' )
				return module.ready;
			return null;

		} )
		.then( function () {

			Con_Printf( 'Quantum renderer: MoonLab WASM loaded\n' );
			_ensureMoonlabState();

		} )
		.catch( function ( e ) {

			_moonlabFailed = true;
			Con_Printf( 'Quantum renderer: MoonLab init failed, fallback active\n' );
			console.error( e );

		} );

}

function _freeMoonlabState() {

	if ( _moonlabModule == null || _moonlabStatePtr === 0 )
		return;

	_moonlabModule._quantum_state_free( _moonlabStatePtr );
	_moonlabModule._free( _moonlabStatePtr );
	_moonlabStatePtr = 0;
	_moonlabQubits = 0;

}

function _ensureMoonlabState() {

	if ( _moonlabModule == null )
		return false;

	const qubits = _clampInt( r_quantum_qubits.value, 2, 12 );
	if ( _moonlabStatePtr !== 0 && _moonlabQubits === qubits )
		return true;

	_freeMoonlabState();

	_moonlabStatePtr = _moonlabModule._malloc( STATE_STRUCT_SIZE );
	if ( _moonlabStatePtr === 0 ) {

		Con_Printf( 'Quantum renderer: failed to allocate MoonLab state\n' );
		return false;

	}

	const result = _moonlabModule._quantum_state_init( _moonlabStatePtr, qubits );
	if ( result !== 0 ) {

		Con_Printf( 'Quantum renderer: MoonLab state init failed\n' );
		_moonlabModule._free( _moonlabStatePtr );
		_moonlabStatePtr = 0;
		return false;

	}

	_moonlabQubits = qubits;
	_moonlabCollapseState = 0;
	_moonlabFrame = 0;
	_clearAccumTargets();
	return true;

}

function _populateFallbackPhaseTexture() {

	const qubits = _clampInt( r_quantum_qubits.value, 2, 12 );
	const depth = _clampInt( r_quantum_depth.value, 1, 24 );
	const qScale = qubits * 0.17;
	const dScale = depth * 0.09;
	const stride = ( qubits * 13 + depth * 7 ) | 0;

	for ( let i = 0; i < PHASE_TEXEL_COUNT; i ++ ) {

		const x = i & ( PHASE_TEXTURE_SIZE - 1 );
		const y = ( i / PHASE_TEXTURE_SIZE ) | 0;
		const n0 = _pseudoRandom( ( x * 19 + y * 7 + _fallbackSeed ) * 0.71 + qScale );
		const n1 = _pseudoRandom( ( x * 5 + y * 29 + stride + _fallbackSeed ) * 1.13 + dScale );
		const n2 = _pseudoRandom( ( ( x ^ y ) + _fallbackSeed * 3 ) * 0.97 + qScale * 0.3 );
		const phase = ( n0 + n1 * 0.5 + _fallbackSeed * 0.01 ) % 1.0;
		const magnitude = 0.2 + 0.55 * n1 + 0.25 * n2;
		const offset = i * 4;

		_phaseData[ offset ] = ( phase * 255 ) | 0;
		_phaseData[ offset + 1 ] = ( magnitude * 255 ) | 0;
		_phaseData[ offset + 2 ] = ( n0 * 255 ) | 0;
		_phaseData[ offset + 3 ] = 255;

	}

	_fallbackSeed ++;
}

function _populateMoonlabPhaseTexture() {

	if ( _ensureMoonlabState() !== true ) {

		_populateFallbackPhaseTexture();
		return;

	}

	const depth = _clampInt( r_quantum_depth.value, 1, 24 );
	const dim = 1 << _moonlabQubits;
	const mask = dim - 1;
	const collapseState = _toNumber( _moonlabCollapseState, 0 ) | 0;

	for ( let i = 0; i < depth; i ++ ) {

		const q = ( _moonlabFrame + i * 3 ) % _moonlabQubits;
		const phaseAngle = Math.sin( ( _moonlabFrame + i * 1.37 ) * 0.21 + collapseState * 0.0007 ) * Math.PI;
		_moonlabModule._gate_hadamard( _moonlabStatePtr, q );
		_moonlabModule._gate_rz( _moonlabStatePtr, q, phaseAngle );

		if ( _moonlabQubits > 1 ) {

			const target = ( q + 1 + ( ( _moonlabFrame + i ) % ( _moonlabQubits - 1 ) ) ) % _moonlabQubits;
			_moonlabModule._gate_cnot( _moonlabStatePtr, q, target );

		}

	}

	const ampPtr = _moonlabModule.HEAP32[ ( _moonlabStatePtr + AMPLITUDE_PTR_OFFSET ) >> 2 ] >>> 0;
	const heap = _moonlabModule.HEAPF64;
	const ampBase = ampPtr >> 3;
	const phaseOffset = ( collapseState ^ ( _moonlabFrame * 17 ) ) & mask;

	for ( let i = 0; i < PHASE_TEXEL_COUNT; i ++ ) {

		const x = i & ( PHASE_TEXTURE_SIZE - 1 );
		const y = ( i / PHASE_TEXTURE_SIZE ) | 0;
		const hash0 = ( x * 73 ) ^ ( y * 151 ) ^ ( phaseOffset * 3 ) ^ ( _moonlabFrame * 19 );
		const hash1 = ( x * 197 + y * 29 + _moonlabFrame * 17 + collapseState * 11 );
		const a = hash0 & mask;
		const b = ( hash1 ^ ( a * 5 ) ) & mask;
		const c = ( a + b + ( ( x ^ y ) * 37 ) ) & mask;

		const re0 = heap[ ampBase + a * 2 ];
		const im0 = heap[ ampBase + a * 2 + 1 ];
		const re1 = heap[ ampBase + b * 2 ];
		const im1 = heap[ ampBase + b * 2 + 1 ];
		const re2 = heap[ ampBase + c * 2 ];
		const im2 = heap[ ampBase + c * 2 + 1 ];

		const re = re0 + re1 * 0.35 + re2 * 0.18;
		const im = im0 + im1 * 0.35 + im2 * 0.18;
		const phase = _fract( Math.atan2( im, re ) / ( Math.PI * 2 ) + 0.5 );
		const magnitude = _clamp( Math.sqrt( re * re + im * im ) * Math.sqrt( dim ), 0, 1 );
		const offset = i * 4;

		_phaseData[ offset ] = ( phase * 255 ) | 0;
		_phaseData[ offset + 1 ] = ( magnitude * 255 ) | 0;
		_phaseData[ offset + 2 ] = ( ( a ^ b ) & 255 );
		_phaseData[ offset + 3 ] = 255;

	}

	const measurementRand = _pseudoRandom( _moonlabFrame * 12.9898 + collapseState * 0.31337 + 0.1337 );
	const measured = _moonlabModule._measurement_all_qubits( _moonlabStatePtr, measurementRand );
	_moonlabCollapseState = _toNumber( measured, 0 ) | 0;
	_moonlabFrame ++;

}

function _updatePhaseTexture() {

	const moonlabStart = performance.now();

	if ( _moonlabModule != null ) {

		_populateMoonlabPhaseTexture();

	} else {

		_populateFallbackPhaseTexture();

	}

	_lastMoonlabMs = performance.now() - moonlabStart;
	_phaseTexture.needsUpdate = true;

}

function _applyUiMinimizedState() {

	if ( _uiRoot == null || _uiToggle == null )
		return;

	_uiRoot.classList.toggle( 'qc-minimized', _uiMinimized );
	_uiToggle.textContent = _uiMinimized ? 'QR +' : 'QR -';
	_uiToggle.setAttribute( 'aria-label', _uiMinimized ? 'Expand quantum renderer controls' : 'Minimize quantum renderer controls' );
	_uiToggle.title = _uiMinimized
		? 'Show quantum renderer controls'
		: 'Hide quantum renderer controls';

}

function _stopUiEventPropagation( event ) {

	event.stopPropagation();

}

function _installUiEventGuards() {

	const uiEventNames = [
		'pointerdown',
		'pointerup',
		'pointermove',
		'mousedown',
		'mouseup',
		'mousemove',
		'click',
		'dblclick',
		'wheel',
		'contextmenu',
		'touchstart',
		'touchmove',
		'touchend',
		'touchcancel',
		'keydown',
		'keyup',
		'keypress'
	];

	for ( let i = 0; i < uiEventNames.length; i ++ ) {

		const eventName = uiEventNames[ i ];
		_uiRoot.addEventListener( eventName, _stopUiEventPropagation );
		_uiToggle.addEventListener( eventName, _stopUiEventPropagation );

	}

}

function _ensureUi() {

	if ( _uiRoot != null || typeof document === 'undefined' )
		return;

	_uiToggle = document.createElement( 'button' );
	_uiToggle.id = 'qc-screen-toggle';
	_uiToggle.type = 'button';
	_uiToggle.setAttribute( 'aria-label', 'Minimize quantum renderer controls' );
	_uiToggle.title = 'Hide quantum renderer controls';
	document.body.appendChild( _uiToggle );

	_uiRoot = document.createElement( 'div' );
	_uiRoot.id = 'quantum-controls';
	_uiRoot.innerHTML = `
		<div class="qc-title">Quantum Renderer</div>
		<div id="qc-body" class="qc-body">
		<label class="qc-row" title="Master switch for the entire quantum post-process pass.">
			<span>Enabled</span>
			<input id="qc-enabled" type="checkbox" title="Enable or disable the quantum renderer.">
			<span id="qc-enabled-value"></span>
		</label>
		<label class="qc-row" title="Choose how quantum amplitudes are visualized in the final image.">
			<span>Mode</span>
			<select id="qc-mode" title="Sampling and Interference are screen-space quantum effects. Raytrace DWT uses BVH ray tracing plus wavelet denoise.">
				<option value="0">Sampling</option>
				<option value="1">Interference</option>
				<option value="2">Observation</option>
				<option value="3">Raytrace DWT</option>
			</select>
			<span id="qc-mode-value"></span>
		</label>
		<label class="qc-row" title="Debug mode for raytracing: disables texture sampling and forces white albedo to inspect lighting and shadows.">
			<span>RT Debug Tex</span>
			<input id="qc-rt-debugtex" type="checkbox" title="When enabled, Raytrace DWT uses white surfaces and ignores all texture color.">
			<span id="qc-rt-debugtex-value"></span>
		</label>
		<label class="qc-row" title="Circuit width. Higher qubits produce richer phase structure and more variation.">
			<span>Qubits</span>
			<input id="qc-qubits" type="range" min="2" max="12" step="1" title="Number of simulated qubits driving the phase/noise field.">
			<span id="qc-qubits-value"></span>
		</label>
		<label class="qc-row" title="Circuit depth per frame. Higher depth increases complexity and cost.">
			<span>Gate Depth</span>
			<input id="qc-depth" type="range" min="1" max="24" step="1" title="How many quantum gate operations are applied each frame.">
			<span id="qc-depth-value"></span>
		</label>
		<label class="qc-row" title="Path samples per pixel in the stochastic lighting estimate.">
			<span>Samples/Pixel</span>
			<input id="qc-spp" type="range" min="1" max="4" step="1" title="Higher values reduce noise and increase GPU cost.">
			<span id="qc-spp-value"></span>
		</label>
		<label class="qc-row" title="Bounce count for the stochastic path-integral walk. Higher values add richer light spread and cost more.">
			<span>Bounces</span>
			<input id="qc-bounces" type="range" min="1" max="6" step="1" title="How many bounce steps each sample ray takes.">
			<span id="qc-bounces-value"></span>
		</label>
		<label class="qc-row" title="Renders internally at reduced resolution. 2x2 means quarter pixels, 10x10 means one hundredth.">
			<span>Pixel Bundle</span>
			<input id="qc-bundle" type="range" min="1" max="10" step="1" title="Internal render scale block size. 1x1 full resolution, 10x10 heavily pixelated.">
			<span id="qc-bundle-value"></span>
		</label>
		<label class="qc-row" title="Maximum triangles included in the BVH for Raytrace DWT mode. Higher values improve geometry fidelity and cost more.">
			<span>RT Tris</span>
			<input id="qc-rt-tris" type="range" min="1024" max="131072" step="1024" title="Triangle budget for ray tracing acceleration structure rebuilds.">
			<span id="qc-rt-tris-value"></span>
		</label>
		<label class="qc-row" title="Wavelet denoise threshold for Raytrace DWT mode. Higher values smooth more aggressively.">
			<span>Wavelet</span>
			<input id="qc-wavelet" type="range" min="0.010" max="0.240" step="0.005" title="Haar shrinkage threshold applied to the raytrace output.">
			<span id="qc-wavelet-value"></span>
		</label>
		<label class="qc-row" title="Blend strength of the quantum contribution over the base Quake render.">
			<span>Strength</span>
			<input id="qc-strength" type="range" min="0.2" max="2.0" step="0.05" title="Amount of quantum modulation applied to lighting and color.">
			<span id="qc-strength-value"></span>
		</label>
		<label class="qc-row" title="Post-gain multiplier after compose. Useful for dark scenes.">
			<span>Gain</span>
			<input id="qc-gain" type="range" min="0.6" max="2.4" step="0.05" title="Final brightness multiplier on the composed quantum output.">
			<span id="qc-gain-value"></span>
		</label>
		<label class="qc-row" title="Global exposure applied before final gamma shaping.">
			<span>Exposure</span>
			<input id="qc-exposure" type="range" min="0.8" max="5.0" step="0.05" title="Overall exposure of the quantum render pass.">
			<span id="qc-exposure-value"></span>
		</label>
		<div id="qc-status" class="qc-meta" title="MoonLab runtime status."></div>
		<div id="qc-perf" class="qc-meta" title="Per-frame timing for compose and MoonLab update."></div>
		</div>
	`;

	document.body.appendChild( _uiRoot );

	_uiEnabled = document.getElementById( 'qc-enabled' );
	_uiMode = document.getElementById( 'qc-mode' );
	_uiRtDebugTex = document.getElementById( 'qc-rt-debugtex' );
	_uiQubits = document.getElementById( 'qc-qubits' );
	_uiDepth = document.getElementById( 'qc-depth' );
	_uiSpp = document.getElementById( 'qc-spp' );
	_uiBounces = document.getElementById( 'qc-bounces' );
	_uiBundle = document.getElementById( 'qc-bundle' );
	_uiRtTris = document.getElementById( 'qc-rt-tris' );
	_uiWavelet = document.getElementById( 'qc-wavelet' );
	_uiStrength = document.getElementById( 'qc-strength' );
	_uiGain = document.getElementById( 'qc-gain' );
	_uiExposure = document.getElementById( 'qc-exposure' );
	_uiEnabledValue = document.getElementById( 'qc-enabled-value' );
	_uiModeValue = document.getElementById( 'qc-mode-value' );
	_uiRtDebugTexValue = document.getElementById( 'qc-rt-debugtex-value' );
	_uiQubitsValue = document.getElementById( 'qc-qubits-value' );
	_uiDepthValue = document.getElementById( 'qc-depth-value' );
	_uiSppValue = document.getElementById( 'qc-spp-value' );
	_uiBouncesValue = document.getElementById( 'qc-bounces-value' );
	_uiBundleValue = document.getElementById( 'qc-bundle-value' );
	_uiRtTrisValue = document.getElementById( 'qc-rt-tris-value' );
	_uiWaveletValue = document.getElementById( 'qc-wavelet-value' );
	_uiStrengthValue = document.getElementById( 'qc-strength-value' );
	_uiGainValue = document.getElementById( 'qc-gain-value' );
	_uiExposureValue = document.getElementById( 'qc-exposure-value' );
	_uiStatus = document.getElementById( 'qc-status' );
	_uiPerf = document.getElementById( 'qc-perf' );

	_installUiEventGuards();

	_uiToggle.addEventListener( 'click', function () {

		_uiMinimized = ! _uiMinimized;
		_applyUiMinimizedState();

	} );
	_applyUiMinimizedState();

	_uiEnabled.addEventListener( 'change', function () {

		Cvar_SetValue( 'r_quantum', _uiEnabled.checked ? 1 : 0 );

	} );

	_uiMode.addEventListener( 'change', function () {

		Cvar_SetValue( 'r_quantum_mode', parseInt( _uiMode.value ) || 3 );

	} );

	_uiRtDebugTex.addEventListener( 'change', function () {

		Cvar_SetValue( 'r_quantum_rt_debugtex', _uiRtDebugTex.checked ? 1 : 0 );
		_bvhLastBuildFrame = -99999;
		_rtLightBuildSignature = '';
		_rtEmissiveLightCount = 0;
		_rtStaticLightCount = 0;
		_rtDynamicLightCount = 0;

	} );

	_uiQubits.addEventListener( 'input', function () {

		Cvar_SetValue( 'r_quantum_qubits', parseInt( _uiQubits.value ) || 12 );

	} );

	_uiDepth.addEventListener( 'input', function () {

		Cvar_SetValue( 'r_quantum_depth', parseInt( _uiDepth.value ) || 24 );

	} );

	_uiSpp.addEventListener( 'input', function () {

		Cvar_SetValue( 'r_quantum_spp', parseInt( _uiSpp.value ) || 4 );

	} );

	_uiBounces.addEventListener( 'input', function () {

		Cvar_SetValue( 'r_quantum_bounces', parseInt( _uiBounces.value ) || 6 );

	} );

	_uiBundle.addEventListener( 'input', function () {

		Cvar_SetValue( 'r_quantum_bundle', parseInt( _uiBundle.value ) || 5 );

	} );

	_uiRtTris.addEventListener( 'input', function () {

		Cvar_SetValue( 'r_quantum_rt_tris', parseInt( _uiRtTris.value ) || RT_MAX_TRIANGLES_DEFAULT );
		_bvhLastBuildFrame = -99999;

	} );

	_uiWavelet.addEventListener( 'input', function () {

		Cvar_SetValue( 'r_quantum_wavelet', parseFloat( _uiWavelet.value ) || 0.080 );

	} );

	_uiStrength.addEventListener( 'input', function () {

		Cvar_SetValue( 'r_quantum_strength', parseFloat( _uiStrength.value ) || 2.0 );

	} );

	_uiGain.addEventListener( 'input', function () {

		Cvar_SetValue( 'r_quantum_gain', parseFloat( _uiGain.value ) || 0.9 );

	} );

	_uiExposure.addEventListener( 'input', function () {

		Cvar_SetValue( 'r_quantum_exposure', parseFloat( _uiExposure.value ) || 3.1 );

	} );

}

function _syncUi() {

	if ( _uiRoot == null || typeof performance === 'undefined' )
		return;

	const now = performance.now();
	if ( now - _lastUiSync < 80 )
		return;
	_lastUiSync = now;

	const mode = _clampInt( r_quantum_mode.value, 0, 3 );
	const rtDebugTex = r_quantum_rt_debugtex.value !== 0;
	const qubits = _clampInt( r_quantum_qubits.value, 2, 12 );
	const depth = _clampInt( r_quantum_depth.value, 1, 24 );
	const spp = _clampInt( r_quantum_spp.value, 1, 4 );
	const bounces = _clampInt( r_quantum_bounces.value, 1, 6 );
	const bundle = _clampInt( r_quantum_bundle.value, 1, 10 );
	const rtTris = _clampInt( r_quantum_rt_tris.value, 1024, 131072 );
	const wavelet = _clamp( r_quantum_wavelet.value, 0.010, 0.240 );
	const strength = _clamp( r_quantum_strength.value, 0.2, 2.0 );
	const gain = _clamp( r_quantum_gain.value, 0.6, 2.4 );
	const exposure = _clamp( r_quantum_exposure.value, 0.8, 5.0 );

	_uiEnabled.checked = r_quantum.value !== 0;
	_uiMode.value = String( mode );
	_uiRtDebugTex.checked = rtDebugTex;
	_uiQubits.value = String( qubits );
	_uiDepth.value = String( depth );
	_uiSpp.value = String( spp );
	_uiBounces.value = String( bounces );
	_uiBundle.value = String( bundle );
	_uiRtTris.value = String( rtTris );
	_uiWavelet.value = wavelet.toFixed( 3 );
	_uiStrength.value = strength.toFixed( 2 );
	_uiGain.value = gain.toFixed( 2 );
	_uiExposure.value = exposure.toFixed( 2 );

	_uiEnabledValue.textContent = r_quantum.value !== 0 ? 'on' : 'off';
	_uiModeValue.textContent = mode === 0
		? 'sampling'
		: ( mode === 1
			? 'interference'
			: ( mode === 2 ? 'observed' : 'raytrace+dwt' ) );
	_uiRtDebugTexValue.textContent = rtDebugTex ? 'on' : 'off';
	_uiQubitsValue.textContent = String( qubits );
	_uiDepthValue.textContent = String( depth );
	_uiSppValue.textContent = String( spp );
	_uiBouncesValue.textContent = String( bounces );
	_uiBundleValue.textContent = bundle + 'x' + bundle;
	_uiRtTrisValue.textContent = String( rtTris );
	_uiWaveletValue.textContent = wavelet.toFixed( 3 );
	_uiStrengthValue.textContent = strength.toFixed( 2 );
	_uiGainValue.textContent = gain.toFixed( 2 );
	_uiExposureValue.textContent = exposure.toFixed( 2 );

	if ( mode === 3 ) {

		if ( _bvhReady ) {

			_uiStatus.textContent =
					'BVH: ' + _bvhTriCount +
					' tris | ' + _bvhNodeCount +
					' nodes | em ' + _rtEmissiveLightCount +
					' (' + _rtStaticLightCount + '+' + _rtModelEmitterLightCount + '+' + _rtDynamicLightCount + ')' +
					( rtDebugTex ? ' | white' : '' ) +
					( _bvhClipped ? ' (capped)' : '' );

		} else {

			_uiStatus.textContent = 'BVH: building...';

		}

	} else if ( _moonlabModule != null ) {

		_uiStatus.textContent = 'MoonLab: ready';

	} else if ( _moonlabFailed ) {

		_uiStatus.textContent = 'MoonLab: fallback noise';

	} else {

		_uiStatus.textContent = 'MoonLab: loading...';

	}

	const bvhText = mode === 3 ? ' | bvh ' + _lastBvhBuildMs.toFixed( 2 ) + ' ms' : '';
	_uiPerf.textContent = 'frame ' + _lastRenderMs.toFixed( 2 ) + ' ms | moonlab ' + _lastMoonlabMs.toFixed( 2 ) + ' ms' + bvhText;

}

export function QuantumRenderer_Init() {

	if ( _initialized ) return;
	_initialized = true;

	_registerCvars();
	_buildPostResources();
	_ensureUi();
	_initMoonlab();
	_syncUi();

}

export function QuantumRenderer_Reset() {

	_clearAccumTargets();
	_disposeBvhTextures();
	_bvhLastBuildFrame = -99999;

}

export function QuantumRenderer_Render( scene, camera ) {

	if ( _initialized === false )
		QuantumRenderer_Init();

	if ( renderer == null || scene == null || camera == null )
		return false;

	if ( r_quantum.value === 0 || isXRActive() ) {

		_syncUi();
		return false;

	}

	_buildPostResources();
	if ( _ensureRenderTargets() !== true )
		return false;

	if ( _moonlabModule == null && _moonlabFailed === false )
		_initMoonlab();

	const frameStart = performance.now();

	const mode = _clampInt( r_quantum_mode.value, 0, 3 );
	const spp = _clampInt( r_quantum_spp.value, 1, 4 );
	const bounces = _clampInt( r_quantum_bounces.value, 1, 6 );
	const strength = _clamp( r_quantum_strength.value, 0.2, 2.0 );
	const gain = _clamp( r_quantum_gain.value, 0.6, 2.4 );
	const exposure = _clamp( r_quantum_exposure.value, 0.8, 5.0 );
	const bundle = _clampInt( r_quantum_bundle.value, 1, 10 );

	if ( mode === 3 ) {

		_renderSceneAlbedoPass( scene, camera, _sceneTarget );

	} else {

		renderer.setRenderTarget( _sceneTarget );
		renderer.clear( true, true, false );
		renderer.render( scene, camera );

	}

	if ( mode === 3 ) {

		_lastMoonlabMs = 0;
			const bvhReady = _ensureRaytraceBvh( scene, camera );
			if ( bvhReady === true ) {

				_injectRuntimeModelEmittersToRayLights( camera );
				_injectRuntimeDlightsToRayLights();

			_setupRaytraceCameraUniforms( camera );
			_postQuad.material = _rayTraceMaterial;
			_rayTraceMaterial.uniforms.uBaseTex.value = _sceneTarget.texture;
			_rayTraceMaterial.uniforms.uDepthTex.value = _sceneTarget.depthTexture;
			_rayTraceMaterial.uniforms.uTriTex.value = _bvhTriTexture;
			_rayTraceMaterial.uniforms.uNodeTex.value = _bvhNodeTexture;
			_rayTraceMaterial.uniforms.uTriTexSize.value.copy( _bvhTriTexSize );
			_rayTraceMaterial.uniforms.uNodeTexSize.value.copy( _bvhNodeTexSize );
			_rayTraceMaterial.uniforms.uTriCount.value = _bvhTriCount;
			_rayTraceMaterial.uniforms.uNodeCount.value = _bvhNodeCount;
			_rayTraceMaterial.uniforms.uEmissiveLightCount.value = _rtEmissiveLightCount;
			_rayTraceMaterial.uniforms.uFrame.value = _frameCounter;
			_rayTraceMaterial.uniforms.uSpp.value = spp;
			_rayTraceMaterial.uniforms.uBounces.value = bounces;
			_rayTraceMaterial.uniforms.uStrength.value = strength;
			_rayTraceMaterial.uniforms.uDebugWhite.value = _rtDebugTexturesEnabled() ? 1 : 0;
			_rayTraceMaterial.uniforms.uCameraNear.value = _clamp( camera.near != null ? camera.near : 1.0, 0.001, 1024.0 );
			_rayTraceMaterial.uniforms.uCameraFar.value = Math.max(
				_rayTraceMaterial.uniforms.uCameraNear.value + 0.01,
				_clamp( camera.far != null ? camera.far : 8192.0, 1.0, 65536.0 )
			);

			renderer.setRenderTarget( _rayTraceTarget );
			renderer.clear( true, false, false );
			renderer.render( _postScene, _postCamera );

			_postQuad.material = _waveletMaterial;
			_waveletMaterial.uniforms.uInputTex.value = _rayTraceTarget.texture;
			const baseWavelet = _clamp( r_quantum_wavelet.value, 0.010, 0.240 );
			const bundleDenoiseScale = bundle >= 4 ? 0.58 : ( bundle >= 2 ? 0.78 : 1.0 );
			const waveletThreshold = _clamp(
				baseWavelet * bundleDenoiseScale + ( bundle - 1 ) * 0.003 - ( spp - 1 ) * 0.004,
				0.010,
				0.180
			);
			_waveletMaterial.uniforms.uThreshold.value = waveletThreshold;

			renderer.setRenderTarget( _waveletTarget );
			renderer.clear( true, false, false );
			renderer.render( _postScene, _postCamera );

			_postQuad.material = _rayCompositeMaterial;
			_rayCompositeMaterial.uniforms.uBaseTex.value = _sceneTarget.texture;
			_rayCompositeMaterial.uniforms.uRayTex.value = _waveletTarget.texture;
			_rayCompositeMaterial.uniforms.uStrength.value = strength;
			_rayCompositeMaterial.uniforms.uGain.value = gain;
			_rayCompositeMaterial.uniforms.uExposure.value = _clamp( exposure * 0.75, 0.25, 3.20 );
			_rayCompositeMaterial.uniforms.uDebugWhite.value = _rtDebugTexturesEnabled() ? 1 : 0;

			renderer.setRenderTarget( null );
			renderer.render( _postScene, _postCamera );

		} else {

			renderer.setRenderTarget( null );
			renderer.render( scene, camera );

		}

		_frameCounter ++;
		_lastRenderMs = performance.now() - frameStart;
		_syncUi();
		return true;

	}

	_updatePhaseTexture();

	const collapseMix = mode === 2 ? 1.0 : 0.15;
	const collapseMax = _moonlabQubits > 0 ? ( ( 1 << _moonlabQubits ) - 1 ) : 1;
	const collapseState = _toNumber( _moonlabCollapseState, 0 ) | 0;
	const collapseSeed = _moonlabQubits > 0
		? ( collapseState / Math.max( collapseMax, 1 ) )
		: _pseudoRandom( _fallbackSeed * 0.37 );

	_postQuad.material = _accumMaterial;
	_accumMaterial.uniforms.uBaseTex.value = _sceneTarget.texture;
	_accumMaterial.uniforms.uPrevAccumTex.value = _accumTargets[ _accumPing ].texture;
	_accumMaterial.uniforms.uFrame.value = _frameCounter;
	_accumMaterial.uniforms.uSpp.value = spp;
	_accumMaterial.uniforms.uBounces.value = bounces;
	_accumMaterial.uniforms.uStrength.value = strength;
	_accumMaterial.uniforms.uCollapseMix.value = collapseMix;
	_accumMaterial.uniforms.uCollapseSeed.value = collapseSeed;

	renderer.setRenderTarget( _accumTargets[ 1 - _accumPing ] );
	renderer.clear( true, false, false );
	renderer.render( _postScene, _postCamera );

	_postQuad.material = _composeMaterial;
	_composeMaterial.uniforms.uBaseTex.value = _sceneTarget.texture;
	_composeMaterial.uniforms.uAccumTex.value = _accumTargets[ 1 - _accumPing ].texture;
	_composeMaterial.uniforms.uMode.value = mode;
	_composeMaterial.uniforms.uStrength.value = strength;
	_composeMaterial.uniforms.uGain.value = gain;
	_composeMaterial.uniforms.uExposure.value = exposure;
	_composeMaterial.uniforms.uFrame.value = _frameCounter;
	_composeMaterial.uniforms.uCollapseSeed.value = collapseSeed;

	renderer.setRenderTarget( null );
	renderer.render( _postScene, _postCamera );

	_accumPing = 1 - _accumPing;
	_frameCounter ++;
	_lastRenderMs = performance.now() - frameStart;
	_syncUi();

	return true;

}
