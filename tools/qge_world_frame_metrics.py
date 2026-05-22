#!/usr/bin/env python3
"""Stdlib world-surface frame metrics for QGE fixed-view renderer work."""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_REGIONS: dict[str, tuple[int, int, int, int]] = {
    "world": (0, 0, 800, 540),
    "ceiling": (90, 0, 710, 44),
    "left_wall": (0, 80, 100, 430),
    "right_wall": (700, 80, 800, 430),
    "front_wall": (260, 45, 610, 250),
    "center_floor": (300, 330, 500, 445),
    "left_near_floor": (0, 430, 240, 555),
    "right_near_floor": (560, 430, 800, 555),
    "mid_corridor": (260, 250, 545, 395),
}


Pixel = tuple[float, float, float]


@dataclass(frozen=True)
class ImageData:
    width: int
    height: int
    rows: list[list[Pixel]]


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def load_png_rgb(path: Path) -> ImageData:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG file")

    width = height = bit_depth = color_type = None
    payload: list[bytes] = []
    pos = 8
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
        chunk_type = data[pos:pos + 4]
        pos += 4
        chunk = data[pos:pos + length]
        pos += length + 4
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, png_filter, interlace = (
                struct.unpack(">IIBBBBB", chunk)
            )
            if bit_depth != 8 or compression != 0 or png_filter != 0 or interlace != 0:
                raise ValueError(f"{path} uses unsupported PNG encoding")
        elif chunk_type == b"IDAT":
            payload.append(chunk)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None or color_type is None:
        raise ValueError(f"{path} is missing PNG header data")
    channels_by_type = {0: 1, 2: 3, 6: 4}
    if color_type not in channels_by_type:
        raise ValueError(f"{path} uses unsupported PNG color type {color_type}")

    channels = channels_by_type[color_type]
    stride = width * channels
    decoded = zlib.decompress(b"".join(payload))
    rows: list[list[Pixel]] = []
    prev = [0] * stride
    offset = 0
    for _y in range(height):
        filter_type = decoded[offset]
        offset += 1
        src = list(decoded[offset:offset + stride])
        offset += stride
        out = [0] * stride
        for x, value in enumerate(src):
            a = out[x - channels] if x >= channels else 0
            b = prev[x]
            c = prev[x - channels] if x >= channels else 0
            if filter_type == 0:
                decoded_value = value
            elif filter_type == 1:
                decoded_value = (value + a) & 255
            elif filter_type == 2:
                decoded_value = (value + b) & 255
            elif filter_type == 3:
                decoded_value = (value + ((a + b) // 2)) & 255
            elif filter_type == 4:
                decoded_value = (value + _paeth(a, b, c)) & 255
            else:
                raise ValueError(f"{path} contains unsupported PNG filter {filter_type}")
            out[x] = decoded_value
        prev = out
        if color_type == 6:
            rows.append([
                (out[i] / 255.0, out[i + 1] / 255.0, out[i + 2] / 255.0)
                for i in range(0, stride, 4)
            ])
        elif color_type == 2:
            rows.append([
                (out[i] / 255.0, out[i + 1] / 255.0, out[i + 2] / 255.0)
                for i in range(0, stride, 3)
            ])
        else:
            rows.append([(value / 255.0, value / 255.0, value / 255.0) for value in out])
    return ImageData(width, height, rows)


def luma(pixel: Pixel) -> float:
    return 0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]


def crop_pixels(image: ImageData, region: tuple[int, int, int, int]) -> list[Pixel]:
    x0, y0, x1, y1 = region
    x0 = max(0, min(image.width, x0))
    x1 = max(0, min(image.width, x1))
    y0 = max(0, min(image.height, y0))
    y1 = max(0, min(image.height, y1))
    if x1 <= x0 or y1 <= y0:
        return []
    return [image.rows[y][x] for y in range(y0, y1) for x in range(x0, x1)]


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def mean_rgb(pixels: list[Pixel]) -> list[float]:
    return [mean([pixel[channel] for pixel in pixels]) for channel in range(3)]


def rmse_rgb(reference: list[Pixel], candidate: list[Pixel]) -> float:
    count = min(len(reference), len(candidate))
    if count <= 0:
        return 0.0
    total = 0.0
    for index in range(count):
        for channel in range(3):
            delta = candidate[index][channel] - reference[index][channel]
            total += delta * delta
    return math.sqrt(total / (count * 3))


def high_frequency_luma(image: ImageData, region: tuple[int, int, int, int]) -> float:
    x0, y0, x1, y1 = region
    x0 = max(0, min(image.width, x0))
    x1 = max(0, min(image.width, x1))
    y0 = max(0, min(image.height, y0))
    y1 = max(0, min(image.height, y1))
    total = 0.0
    count = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            here = luma(image.rows[y][x])
            if x + 1 < x1:
                delta = here - luma(image.rows[y][x + 1])
                total += delta * delta
                count += 1
            if y + 1 < y1:
                delta = here - luma(image.rows[y + 1][x])
                total += delta * delta
                count += 1
    return math.sqrt(total / count) if count else 0.0


def parse_region(value: str) -> tuple[str, tuple[int, int, int, int]]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("region must be name:x0,y0,x1,y1")
    name, body = value.split(":", 1)
    parts = body.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("region must have four coordinates")
    try:
        coords = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("region coordinates must be integers") from exc
    return name, coords  # type: ignore[return-value]


def compare_images(
    reference: ImageData,
    candidate: ImageData,
    regions: dict[str, tuple[int, int, int, int]],
) -> dict:
    metrics: dict[str, object] = {
        "schema": "qge.world_frame_metrics.v0",
        "reference_size": {"width": reference.width, "height": reference.height},
        "candidate_size": {"width": candidate.width, "height": candidate.height},
        "regions": {},
    }
    region_metrics: dict[str, dict[str, object]] = {}
    for name, region in regions.items():
        ref_pixels = crop_pixels(reference, region)
        cand_pixels = crop_pixels(candidate, region)
        ref_luma = [luma(pixel) for pixel in ref_pixels]
        cand_luma = [luma(pixel) for pixel in cand_pixels]
        ref_hf = high_frequency_luma(reference, region)
        cand_hf = high_frequency_luma(candidate, region)
        region_metrics[name] = {
            "region": list(region),
            "pixel_count": min(len(ref_pixels), len(cand_pixels)),
            "rmse_rgb": rmse_rgb(ref_pixels, cand_pixels),
            "reference_mean_rgb": mean_rgb(ref_pixels),
            "candidate_mean_rgb": mean_rgb(cand_pixels),
            "reference_luma_mean": mean(ref_luma),
            "candidate_luma_mean": mean(cand_luma),
            "reference_hf_luma": ref_hf,
            "candidate_hf_luma": cand_hf,
            "hf_luma_ratio": cand_hf / ref_hf if ref_hf > 0.0 else 0.0,
        }
    metrics["regions"] = region_metrics
    return metrics


def markdown_report(metrics: dict) -> str:
    lines = [
        "# QGE World Frame Metrics",
        "",
        "| Region | RGB RMSE | Luma Ref | Luma Candidate | HF Ratio | Pixels |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, data in metrics["regions"].items():
        lines.append(
            f"| {name} | {data['rmse_rgb']:.6f} | "
            f"{data['reference_luma_mean']:.6f} | "
            f"{data['candidate_luma_mean']:.6f} | "
            f"{data['hf_luma_ratio']:.3f} | {data['pixel_count']} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare classic and QGE fixed-view world-surface PNG frames."
    )
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--region", action="append", type=parse_region,
                        help="Override/add region as name:x0,y0,x1,y1")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    regions = dict(DEFAULT_REGIONS)
    if args.region:
        regions.update(dict(args.region))
    metrics = compare_images(
        load_png_rgb(args.reference),
        load_png_rgb(args.candidate),
        regions,
    )
    if args.json:
        args.json.write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n")
    if args.markdown:
        args.markdown.write_text(markdown_report(metrics), encoding="utf-8")
    if not args.json and not args.markdown:
        print(json.dumps(metrics, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"qge_world_frame_metrics.py: {exc}", file=sys.stderr)
        raise SystemExit(1)
