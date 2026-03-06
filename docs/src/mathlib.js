// Ported from: WinQuake/mathlib.c -- math primitives

import { PITCH, YAW, ROLL } from './quakedef.js';

export const M_PI = 3.14159265358979323846;

export const vec3_origin = new Float32Array( [ 0, 0, 0 ] );

/*-----------------------------------------------------------------*/

const DEG2RAD = ( a ) => ( a * M_PI ) / 180.0;

export function DotProduct( x, y ) {

	return x[ 0 ] * y[ 0 ] + x[ 1 ] * y[ 1 ] + x[ 2 ] * y[ 2 ];

}

export function VectorSubtract( a, b, c ) {

	c[ 0 ] = a[ 0 ] - b[ 0 ];
	c[ 1 ] = a[ 1 ] - b[ 1 ];
	c[ 2 ] = a[ 2 ] - b[ 2 ];

}

export function VectorAdd( a, b, c ) {

	c[ 0 ] = a[ 0 ] + b[ 0 ];
	c[ 1 ] = a[ 1 ] + b[ 1 ];
	c[ 2 ] = a[ 2 ] + b[ 2 ];

}

export function VectorCopy( a, b ) {

	b[ 0 ] = a[ 0 ];
	b[ 1 ] = a[ 1 ];
	b[ 2 ] = a[ 2 ];

}

export function VectorMA( veca, scale, vecb, vecc ) {

	vecc[ 0 ] = veca[ 0 ] + scale * vecb[ 0 ];
	vecc[ 1 ] = veca[ 1 ] + scale * vecb[ 1 ];
	vecc[ 2 ] = veca[ 2 ] + scale * vecb[ 2 ];

}

export function VectorCompare( v1, v2 ) {

	for ( let i = 0; i < 3; i ++ ) {

		if ( v1[ i ] !== v2[ i ] ) return 0;

	}

	return 1;

}

export function Length( v ) {

	let length = 0;
	for ( let i = 0; i < 3; i ++ )
		length += v[ i ] * v[ i ];
	length = Math.sqrt( length );

	return length;

}

export function VectorNormalize( v ) {

	let length = v[ 0 ] * v[ 0 ] + v[ 1 ] * v[ 1 ] + v[ 2 ] * v[ 2 ];
	length = Math.sqrt( length );

	if ( length ) {

		const ilength = 1 / length;
		v[ 0 ] *= ilength;
		v[ 1 ] *= ilength;
		v[ 2 ] *= ilength;

	}

	return length;

}

export function VectorInverse( v ) {

	v[ 0 ] = - v[ 0 ];
	v[ 1 ] = - v[ 1 ];
	v[ 2 ] = - v[ 2 ];

}

export function VectorScale( _in, scale, out ) {

	out[ 0 ] = _in[ 0 ] * scale;
	out[ 1 ] = _in[ 1 ] * scale;
	out[ 2 ] = _in[ 2 ] * scale;

}

export function CrossProduct( v1, v2, cross ) {

	cross[ 0 ] = v1[ 1 ] * v2[ 2 ] - v1[ 2 ] * v2[ 1 ];
	cross[ 1 ] = v1[ 2 ] * v2[ 0 ] - v1[ 0 ] * v2[ 2 ];
	cross[ 2 ] = v1[ 0 ] * v2[ 1 ] - v1[ 1 ] * v2[ 0 ];

}

export function Q_log2( val ) {

	let answer = 0;
	while ( ( val >>= 1 ) )
		answer ++;
	return answer;

}

export function anglemod( a ) {

	return ( 360.0 / 65536 ) * ( ( ( a * ( 65536 / 360.0 ) ) | 0 ) & 65535 );

}

/*
==================
BoxOnPlaneSide

Returns 1, 2, or 1 + 2
==================
*/
export function BoxOnPlaneSide( emins, emaxs, p ) {

	let dist1, dist2;
	let sides;

	// fast axial cases
	if ( p.type < 3 ) {

		if ( p.dist <= emins[ p.type ] )
			return 1;
		if ( p.dist >= emaxs[ p.type ] )
			return 2;
		return 3;

	}

	// general case
	switch ( p.signbits ) {

		case 0:
			dist1 = p.normal[ 0 ] * emaxs[ 0 ] + p.normal[ 1 ] * emaxs[ 1 ] + p.normal[ 2 ] * emaxs[ 2 ];
			dist2 = p.normal[ 0 ] * emins[ 0 ] + p.normal[ 1 ] * emins[ 1 ] + p.normal[ 2 ] * emins[ 2 ];
			break;
		case 1:
			dist1 = p.normal[ 0 ] * emins[ 0 ] + p.normal[ 1 ] * emaxs[ 1 ] + p.normal[ 2 ] * emaxs[ 2 ];
			dist2 = p.normal[ 0 ] * emaxs[ 0 ] + p.normal[ 1 ] * emins[ 1 ] + p.normal[ 2 ] * emins[ 2 ];
			break;
		case 2:
			dist1 = p.normal[ 0 ] * emaxs[ 0 ] + p.normal[ 1 ] * emins[ 1 ] + p.normal[ 2 ] * emaxs[ 2 ];
			dist2 = p.normal[ 0 ] * emins[ 0 ] + p.normal[ 1 ] * emaxs[ 1 ] + p.normal[ 2 ] * emins[ 2 ];
			break;
		case 3:
			dist1 = p.normal[ 0 ] * emins[ 0 ] + p.normal[ 1 ] * emins[ 1 ] + p.normal[ 2 ] * emaxs[ 2 ];
			dist2 = p.normal[ 0 ] * emaxs[ 0 ] + p.normal[ 1 ] * emaxs[ 1 ] + p.normal[ 2 ] * emins[ 2 ];
			break;
		case 4:
			dist1 = p.normal[ 0 ] * emaxs[ 0 ] + p.normal[ 1 ] * emaxs[ 1 ] + p.normal[ 2 ] * emins[ 2 ];
			dist2 = p.normal[ 0 ] * emins[ 0 ] + p.normal[ 1 ] * emins[ 1 ] + p.normal[ 2 ] * emaxs[ 2 ];
			break;
		case 5:
			dist1 = p.normal[ 0 ] * emins[ 0 ] + p.normal[ 1 ] * emaxs[ 1 ] + p.normal[ 2 ] * emins[ 2 ];
			dist2 = p.normal[ 0 ] * emaxs[ 0 ] + p.normal[ 1 ] * emins[ 1 ] + p.normal[ 2 ] * emaxs[ 2 ];
			break;
		case 6:
			dist1 = p.normal[ 0 ] * emaxs[ 0 ] + p.normal[ 1 ] * emins[ 1 ] + p.normal[ 2 ] * emins[ 2 ];
			dist2 = p.normal[ 0 ] * emins[ 0 ] + p.normal[ 1 ] * emaxs[ 1 ] + p.normal[ 2 ] * emaxs[ 2 ];
			break;
		case 7:
			dist1 = p.normal[ 0 ] * emins[ 0 ] + p.normal[ 1 ] * emins[ 1 ] + p.normal[ 2 ] * emins[ 2 ];
			dist2 = p.normal[ 0 ] * emaxs[ 0 ] + p.normal[ 1 ] * emaxs[ 1 ] + p.normal[ 2 ] * emaxs[ 2 ];
			break;
		default:
			dist1 = dist2 = 0; // shut up compiler
			Sys_Error( 'BoxOnPlaneSide: Bad signbits' );
			break;

	}

	sides = 0;
	if ( dist1 >= p.dist )
		sides = 1;
	if ( dist2 < p.dist )
		sides |= 2;

	return sides;

}

export function AngleVectors( angles, forward, right, up ) {

	let angle;
	let sr, sp, sy, cr, cp, cy;

	angle = angles[ YAW ] * ( M_PI * 2 / 360 );
	sy = Math.sin( angle );
	cy = Math.cos( angle );
	angle = angles[ PITCH ] * ( M_PI * 2 / 360 );
	sp = Math.sin( angle );
	cp = Math.cos( angle );
	angle = angles[ ROLL ] * ( M_PI * 2 / 360 );
	sr = Math.sin( angle );
	cr = Math.cos( angle );

	forward[ 0 ] = cp * cy;
	forward[ 1 ] = cp * sy;
	forward[ 2 ] = - sp;
	right[ 0 ] = ( - 1 * sr * sp * cy + - 1 * cr * - sy );
	right[ 1 ] = ( - 1 * sr * sp * sy + - 1 * cr * cy );
	right[ 2 ] = - 1 * sr * cp;
	up[ 0 ] = ( cr * sp * cy + - sr * - sy );
	up[ 1 ] = ( cr * sp * sy + - sr * cy );
	up[ 2 ] = cr * cp;

}

/*
================
R_ConcatRotations
================
*/
export function R_ConcatRotations( in1, in2, out ) {

	out[ 0 ][ 0 ] = in1[ 0 ][ 0 ] * in2[ 0 ][ 0 ] + in1[ 0 ][ 1 ] * in2[ 1 ][ 0 ] +
				in1[ 0 ][ 2 ] * in2[ 2 ][ 0 ];
	out[ 0 ][ 1 ] = in1[ 0 ][ 0 ] * in2[ 0 ][ 1 ] + in1[ 0 ][ 1 ] * in2[ 1 ][ 1 ] +
				in1[ 0 ][ 2 ] * in2[ 2 ][ 1 ];
	out[ 0 ][ 2 ] = in1[ 0 ][ 0 ] * in2[ 0 ][ 2 ] + in1[ 0 ][ 1 ] * in2[ 1 ][ 2 ] +
				in1[ 0 ][ 2 ] * in2[ 2 ][ 2 ];
	out[ 1 ][ 0 ] = in1[ 1 ][ 0 ] * in2[ 0 ][ 0 ] + in1[ 1 ][ 1 ] * in2[ 1 ][ 0 ] +
				in1[ 1 ][ 2 ] * in2[ 2 ][ 0 ];
	out[ 1 ][ 1 ] = in1[ 1 ][ 0 ] * in2[ 0 ][ 1 ] + in1[ 1 ][ 1 ] * in2[ 1 ][ 1 ] +
				in1[ 1 ][ 2 ] * in2[ 2 ][ 1 ];
	out[ 1 ][ 2 ] = in1[ 1 ][ 0 ] * in2[ 0 ][ 2 ] + in1[ 1 ][ 1 ] * in2[ 1 ][ 2 ] +
				in1[ 1 ][ 2 ] * in2[ 2 ][ 2 ];
	out[ 2 ][ 0 ] = in1[ 2 ][ 0 ] * in2[ 0 ][ 0 ] + in1[ 2 ][ 1 ] * in2[ 1 ][ 0 ] +
				in1[ 2 ][ 2 ] * in2[ 2 ][ 0 ];
	out[ 2 ][ 1 ] = in1[ 2 ][ 0 ] * in2[ 0 ][ 1 ] + in1[ 2 ][ 1 ] * in2[ 1 ][ 1 ] +
				in1[ 2 ][ 2 ] * in2[ 2 ][ 1 ];
	out[ 2 ][ 2 ] = in1[ 2 ][ 0 ] * in2[ 0 ][ 2 ] + in1[ 2 ][ 1 ] * in2[ 1 ][ 2 ] +
				in1[ 2 ][ 2 ] * in2[ 2 ][ 2 ];

}

/*
================
R_ConcatTransforms
================
*/
export function R_ConcatTransforms( in1, in2, out ) {

	out[ 0 ][ 0 ] = in1[ 0 ][ 0 ] * in2[ 0 ][ 0 ] + in1[ 0 ][ 1 ] * in2[ 1 ][ 0 ] +
				in1[ 0 ][ 2 ] * in2[ 2 ][ 0 ];
	out[ 0 ][ 1 ] = in1[ 0 ][ 0 ] * in2[ 0 ][ 1 ] + in1[ 0 ][ 1 ] * in2[ 1 ][ 1 ] +
				in1[ 0 ][ 2 ] * in2[ 2 ][ 1 ];
	out[ 0 ][ 2 ] = in1[ 0 ][ 0 ] * in2[ 0 ][ 2 ] + in1[ 0 ][ 1 ] * in2[ 1 ][ 2 ] +
				in1[ 0 ][ 2 ] * in2[ 2 ][ 2 ];
	out[ 0 ][ 3 ] = in1[ 0 ][ 0 ] * in2[ 0 ][ 3 ] + in1[ 0 ][ 1 ] * in2[ 1 ][ 3 ] +
				in1[ 0 ][ 2 ] * in2[ 2 ][ 3 ] + in1[ 0 ][ 3 ];
	out[ 1 ][ 0 ] = in1[ 1 ][ 0 ] * in2[ 0 ][ 0 ] + in1[ 1 ][ 1 ] * in2[ 1 ][ 0 ] +
				in1[ 1 ][ 2 ] * in2[ 2 ][ 0 ];
	out[ 1 ][ 1 ] = in1[ 1 ][ 0 ] * in2[ 0 ][ 1 ] + in1[ 1 ][ 1 ] * in2[ 1 ][ 1 ] +
				in1[ 1 ][ 2 ] * in2[ 2 ][ 1 ];
	out[ 1 ][ 2 ] = in1[ 1 ][ 0 ] * in2[ 0 ][ 2 ] + in1[ 1 ][ 1 ] * in2[ 1 ][ 2 ] +
				in1[ 1 ][ 2 ] * in2[ 2 ][ 2 ];
	out[ 1 ][ 3 ] = in1[ 1 ][ 0 ] * in2[ 0 ][ 3 ] + in1[ 1 ][ 1 ] * in2[ 1 ][ 3 ] +
				in1[ 1 ][ 2 ] * in2[ 2 ][ 3 ] + in1[ 1 ][ 3 ];
	out[ 2 ][ 0 ] = in1[ 2 ][ 0 ] * in2[ 0 ][ 0 ] + in1[ 2 ][ 1 ] * in2[ 1 ][ 0 ] +
				in1[ 2 ][ 2 ] * in2[ 2 ][ 0 ];
	out[ 2 ][ 1 ] = in1[ 2 ][ 0 ] * in2[ 0 ][ 1 ] + in1[ 2 ][ 1 ] * in2[ 1 ][ 1 ] +
				in1[ 2 ][ 2 ] * in2[ 2 ][ 1 ];
	out[ 2 ][ 2 ] = in1[ 2 ][ 0 ] * in2[ 0 ][ 2 ] + in1[ 2 ][ 1 ] * in2[ 1 ][ 2 ] +
				in1[ 2 ][ 2 ] * in2[ 2 ][ 2 ];
	out[ 2 ][ 3 ] = in1[ 2 ][ 0 ] * in2[ 0 ][ 3 ] + in1[ 2 ][ 1 ] * in2[ 1 ][ 3 ] +
				in1[ 2 ][ 2 ] * in2[ 2 ][ 3 ] + in1[ 2 ][ 3 ];

}

export function ProjectPointOnPlane( dst, p, normal ) {

	const inv_denom = 1.0 / DotProduct( normal, normal );
	const d = DotProduct( normal, p ) * inv_denom;
	const n = new Float32Array( 3 );

	n[ 0 ] = normal[ 0 ] * inv_denom;
	n[ 1 ] = normal[ 1 ] * inv_denom;
	n[ 2 ] = normal[ 2 ] * inv_denom;

	dst[ 0 ] = p[ 0 ] - d * n[ 0 ];
	dst[ 1 ] = p[ 1 ] - d * n[ 1 ];
	dst[ 2 ] = p[ 2 ] - d * n[ 2 ];

}

/*
** assumes "src" is normalized
*/
export function PerpendicularVector( dst, src ) {

	let pos = 0;
	let minelem = 1.0;
	const tempvec = new Float32Array( 3 );

	// find the smallest magnitude axially aligned vector
	for ( let i = 0; i < 3; i ++ ) {

		if ( Math.abs( src[ i ] ) < minelem ) {

			pos = i;
			minelem = Math.abs( src[ i ] );

		}

	}

	tempvec[ 0 ] = tempvec[ 1 ] = tempvec[ 2 ] = 0.0;
	tempvec[ pos ] = 1.0;

	// project the point onto the plane defined by src
	ProjectPointOnPlane( dst, tempvec, src );

	// normalize the result
	VectorNormalize( dst );

}

export function RotatePointAroundVector( dst, dir, point, degrees ) {

	const m = [ new Float32Array( 3 ), new Float32Array( 3 ), new Float32Array( 3 ) ];
	const im = [ new Float32Array( 3 ), new Float32Array( 3 ), new Float32Array( 3 ) ];
	const zrot = [ new Float32Array( 3 ), new Float32Array( 3 ), new Float32Array( 3 ) ];
	const tmpmat = [ new Float32Array( 3 ), new Float32Array( 3 ), new Float32Array( 3 ) ];
	const rot = [ new Float32Array( 3 ), new Float32Array( 3 ), new Float32Array( 3 ) ];
	const vr = new Float32Array( 3 );
	const vup = new Float32Array( 3 );
	const vf = new Float32Array( 3 );

	vf[ 0 ] = dir[ 0 ];
	vf[ 1 ] = dir[ 1 ];
	vf[ 2 ] = dir[ 2 ];

	PerpendicularVector( vr, dir );
	CrossProduct( vr, vf, vup );

	m[ 0 ][ 0 ] = vr[ 0 ];
	m[ 1 ][ 0 ] = vr[ 1 ];
	m[ 2 ][ 0 ] = vr[ 2 ];

	m[ 0 ][ 1 ] = vup[ 0 ];
	m[ 1 ][ 1 ] = vup[ 1 ];
	m[ 2 ][ 1 ] = vup[ 2 ];

	m[ 0 ][ 2 ] = vf[ 0 ];
	m[ 1 ][ 2 ] = vf[ 1 ];
	m[ 2 ][ 2 ] = vf[ 2 ];

	// copy m to im then transpose
	for ( let i = 0; i < 3; i ++ )
		for ( let j = 0; j < 3; j ++ )
			im[ i ][ j ] = m[ i ][ j ];

	im[ 0 ][ 1 ] = m[ 1 ][ 0 ];
	im[ 0 ][ 2 ] = m[ 2 ][ 0 ];
	im[ 1 ][ 0 ] = m[ 0 ][ 1 ];
	im[ 1 ][ 2 ] = m[ 2 ][ 1 ];
	im[ 2 ][ 0 ] = m[ 0 ][ 2 ];
	im[ 2 ][ 1 ] = m[ 1 ][ 2 ];

	zrot[ 0 ][ 0 ] = zrot[ 1 ][ 1 ] = zrot[ 2 ][ 2 ] = 1.0;

	zrot[ 0 ][ 0 ] = Math.cos( DEG2RAD( degrees ) );
	zrot[ 0 ][ 1 ] = Math.sin( DEG2RAD( degrees ) );
	zrot[ 1 ][ 0 ] = - Math.sin( DEG2RAD( degrees ) );
	zrot[ 1 ][ 1 ] = Math.cos( DEG2RAD( degrees ) );

	R_ConcatRotations( m, zrot, tmpmat );
	R_ConcatRotations( tmpmat, im, rot );

	for ( let i = 0; i < 3; i ++ ) {

		dst[ i ] = rot[ i ][ 0 ] * point[ 0 ] + rot[ i ][ 1 ] * point[ 1 ] + rot[ i ][ 2 ] * point[ 2 ];

	}

}

/*
===================
FloorDivMod

Returns mathematically correct (floor-based) quotient and remainder for
numer and denom, both of which should contain no fractional part. The
quotient must fit in 32 bits.
====================
*/
export function FloorDivMod( numer, denom ) {

	let q, r;

	if ( numer >= 0.0 ) {

		const x = Math.floor( numer / denom );
		q = x | 0;
		r = Math.floor( numer - ( x * denom ) ) | 0;

	} else {

		const x = Math.floor( - numer / denom );
		q = - ( x | 0 );
		r = Math.floor( - numer - ( x * denom ) ) | 0;
		if ( r !== 0 ) {

			q --;
			r = ( denom | 0 ) - r;

		}

	}

	return { quotient: q, remainder: r };

}

export function GreatestCommonDivisor( i1, i2 ) {

	if ( i1 > i2 ) {

		if ( i2 === 0 ) return i1;
		return GreatestCommonDivisor( i2, i1 % i2 );

	} else {

		if ( i1 === 0 ) return i2;
		return GreatestCommonDivisor( i1, i2 % i1 );

	}

}
