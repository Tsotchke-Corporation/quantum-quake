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
RegionMap = dict[str, tuple[int, int, int, int]]


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


def mean_rgb_lists(values: list[list[float]]) -> list[float]:
    return [mean([item[channel] for item in values]) for channel in range(3)]


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
    regions: RegionMap,
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


def expand_png_paths(path: Path) -> list[Path]:
    if path.is_dir():
        paths = sorted(path.glob("frame_*.png"))
        if not paths:
            paths = sorted(path.glob("*.png"))
    else:
        paths = [path]
    if not paths:
        raise ValueError(f"{path} does not contain PNG frames")
    return paths


def reference_path_for_frame(reference_paths: list[Path], index: int) -> Path:
    if len(reference_paths) == 1:
        return reference_paths[0]
    if index >= len(reference_paths):
        raise ValueError("reference and candidate frame counts do not match")
    return reference_paths[index]


def average_region_metrics(frame_metrics: list[dict], region_name: str) -> dict:
    entries = [metrics["regions"][region_name] for metrics in frame_metrics]
    first = entries[0]
    return {
        "region": first["region"],
        "pixel_count": int(mean([entry["pixel_count"] for entry in entries])),
        "rmse_rgb": mean([entry["rmse_rgb"] for entry in entries]),
        "reference_mean_rgb": mean_rgb_lists(
            [entry["reference_mean_rgb"] for entry in entries]
        ),
        "candidate_mean_rgb": mean_rgb_lists(
            [entry["candidate_mean_rgb"] for entry in entries]
        ),
        "reference_luma_mean": mean(
            [entry["reference_luma_mean"] for entry in entries]
        ),
        "candidate_luma_mean": mean(
            [entry["candidate_luma_mean"] for entry in entries]
        ),
        "reference_hf_luma": mean([entry["reference_hf_luma"] for entry in entries]),
        "candidate_hf_luma": mean([entry["candidate_hf_luma"] for entry in entries]),
        "hf_luma_ratio": mean([entry["hf_luma_ratio"] for entry in entries]),
    }


def compare_frame_set(
    reference_path: Path,
    candidate_path: Path,
    regions: RegionMap,
    baseline_candidate_path: Path | None = None,
) -> dict:
    reference_paths = expand_png_paths(reference_path)
    candidate_paths = expand_png_paths(candidate_path)
    if len(reference_paths) > 1 and len(reference_paths) != len(candidate_paths):
        raise ValueError("reference and candidate frame counts do not match")

    frame_metrics: list[dict] = []
    for index, candidate_frame in enumerate(candidate_paths):
        frame_metrics.append(compare_images(
            load_png_rgb(reference_path_for_frame(reference_paths, index)),
            load_png_rgb(candidate_frame),
            regions,
        ))

    metrics: dict[str, object] = {
        "schema": "qge.world_frame_metrics.frames.v0",
        "reference": str(reference_path),
        "candidate": str(candidate_path),
        "frame_count": len(candidate_paths),
        "regions": {
            name: average_region_metrics(frame_metrics, name)
            for name in regions
        },
    }

    if baseline_candidate_path:
        baseline_paths = expand_png_paths(baseline_candidate_path)
        if len(baseline_paths) != len(candidate_paths):
            raise ValueError("baseline and candidate frame counts do not match")
        baseline_frame_metrics: list[dict] = []
        for index, baseline_frame in enumerate(baseline_paths):
            baseline_frame_metrics.append(compare_images(
                load_png_rgb(reference_path_for_frame(reference_paths, index)),
                load_png_rgb(baseline_frame),
                regions,
            ))
        metrics["baseline_candidate"] = str(baseline_candidate_path)
        baseline_regions = {
            name: average_region_metrics(baseline_frame_metrics, name)
            for name in regions
        }
        metrics["baseline_regions"] = baseline_regions
        for name, data in metrics["regions"].items():
            baseline = baseline_regions[name]
            data["baseline_rmse_rgb"] = baseline["rmse_rgb"]
            data["delta_rmse_rgb"] = data["rmse_rgb"] - baseline["rmse_rgb"]
            data["baseline_candidate_luma_mean"] = baseline["candidate_luma_mean"]
            data["delta_candidate_luma_mean"] = (
                data["candidate_luma_mean"] - baseline["candidate_luma_mean"]
            )
            data["baseline_hf_luma_ratio"] = baseline["hf_luma_ratio"]
            data["delta_hf_luma_ratio"] = (
                data["hf_luma_ratio"] - baseline["hf_luma_ratio"]
            )

    return metrics


def markdown_report(metrics: dict) -> str:
    if metrics["schema"] == "qge.world_frame_metrics.frames.v0":
        return markdown_frame_set_report(metrics)

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


def markdown_frame_set_report(metrics: dict) -> str:
    frame_count = metrics["frame_count"]
    has_baseline = "baseline_regions" in metrics
    lines = [
        "# QGE World Frame Metrics",
        "",
        f"Frames: {frame_count}",
        "",
    ]
    if has_baseline:
        lines.extend([
            "| Region | Baseline RMSE | Candidate RMSE | Delta RMSE | "
            "Ref Luma | Baseline Luma | Candidate Luma | "
            "Baseline HF | Candidate HF | Delta HF |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        for name, data in metrics["regions"].items():
            lines.append(
                f"| {name} | {data['baseline_rmse_rgb']:.6f} | "
                f"{data['rmse_rgb']:.6f} | {data['delta_rmse_rgb']:+.6f} | "
                f"{data['reference_luma_mean']:.6f} | "
                f"{data['baseline_candidate_luma_mean']:.6f} | "
                f"{data['candidate_luma_mean']:.6f} | "
                f"{data['baseline_hf_luma_ratio']:.3f} | "
                f"{data['hf_luma_ratio']:.3f} | "
                f"{data['delta_hf_luma_ratio']:+.3f} |"
            )
    else:
        lines.extend([
            "| Region | RGB RMSE | Luma Ref | Luma Candidate | HF Ratio | Pixels |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ])
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
    parser.add_argument("--baseline-candidate", type=Path,
                        help="Optional previous QGE frame/file set for delta metrics")
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
    if args.baseline_candidate or args.reference.is_dir() or args.candidate.is_dir():
        metrics = compare_frame_set(
            args.reference,
            args.candidate,
            regions,
            args.baseline_candidate,
        )
    else:
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
