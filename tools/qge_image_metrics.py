#!/usr/bin/env python3
"""Compute publication-friendly image metrics for QGE render captures."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def load_rgb(path: Path) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    return np.asarray(image, dtype=np.float32)


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114


def global_ssim(a: np.ndarray, b: np.ndarray) -> float:
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    mu_a = float(np.mean(a))
    mu_b = float(np.mean(b))
    var_a = float(np.mean((a - mu_a) ** 2))
    var_b = float(np.mean((b - mu_b) ** 2))
    cov = float(np.mean((a - mu_a) * (b - mu_b)))
    numerator = (2.0 * mu_a * mu_b + c1) * (2.0 * cov + c2)
    denominator = (mu_a * mu_a + mu_b * mu_b + c1) * (var_a + var_b + c2)
    if denominator <= 0.0:
        return 1.0 if numerator <= 0.0 else 0.0
    return numerator / denominator


def sobel_edges(gray: np.ndarray) -> np.ndarray:
    padded = np.pad(gray, 1, mode="edge")
    tl = padded[:-2, :-2]
    tc = padded[:-2, 1:-1]
    tr = padded[:-2, 2:]
    ml = padded[1:-1, :-2]
    mr = padded[1:-1, 2:]
    bl = padded[2:, :-2]
    bc = padded[2:, 1:-1]
    br = padded[2:, 2:]
    gx = -tl - 2.0 * ml - bl + tr + 2.0 * mr + br
    gy = -tl - 2.0 * tc - tr + bl + 2.0 * bc + br
    return np.sqrt(gx * gx + gy * gy)


def edge_metrics(ref_luma: np.ndarray, cand_luma: np.ndarray) -> dict[str, float]:
    ref_edges = sobel_edges(ref_luma)
    cand_edges = sobel_edges(cand_luma)
    nonzero = ref_edges[ref_edges > 0.0]
    if nonzero.size:
        threshold = float(np.percentile(nonzero, 82.0))
    else:
        threshold = 1.0
    threshold = max(threshold, 8.0)
    ref_mask = ref_edges >= threshold
    cand_mask = cand_edges >= threshold
    tp = int(np.count_nonzero(ref_mask & cand_mask))
    fp = int(np.count_nonzero(~ref_mask & cand_mask))
    fn = int(np.count_nonzero(ref_mask & ~cand_mask))
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2.0 * precision * recall / (precision + recall)
          if (precision + recall) else 0.0)
    union = int(np.count_nonzero(ref_mask | cand_mask))
    jaccard = tp / union if union else 1.0
    return {
        "edge_threshold": threshold,
        "edge_precision": precision,
        "edge_recall": recall,
        "edge_f1": f1,
        "edge_jaccard": jaccard,
        "reference_edge_pixels": int(np.count_nonzero(ref_mask)),
        "candidate_edge_pixels": int(np.count_nonzero(cand_mask)),
    }


def histogram_intersection(ref: np.ndarray, cand: np.ndarray, bins: int = 32) -> float:
    total = 0.0
    for channel in range(3):
        hist_ref, _ = np.histogram(ref[:, :, channel], bins=bins, range=(0, 255))
        hist_cand, _ = np.histogram(cand[:, :, channel], bins=bins, range=(0, 255))
        hist_ref = hist_ref.astype(np.float64)
        hist_cand = hist_cand.astype(np.float64)
        if hist_ref.sum() > 0:
            hist_ref /= hist_ref.sum()
        if hist_cand.sum() > 0:
            hist_cand /= hist_cand.sum()
        total += float(np.minimum(hist_ref, hist_cand).sum())
    return total / 3.0


def blockiness(gray: np.ndarray, block: int) -> dict[str, float]:
    if gray.shape[0] < 2 or gray.shape[1] < 2:
        return {"block": block, "boundary_mean": 0.0, "interior_mean": 0.0,
                "ratio": 0.0}

    vertical = np.abs(gray[:, 1:] - gray[:, :-1])
    horizontal = np.abs(gray[1:, :] - gray[:-1, :])
    v_positions = np.arange(1, gray.shape[1])
    h_positions = np.arange(1, gray.shape[0])
    v_boundary = (v_positions % block) == 0
    h_boundary = (h_positions % block) == 0

    boundary_values = []
    interior_values = []
    if np.any(v_boundary):
        boundary_values.append(vertical[:, v_boundary])
    if np.any(~v_boundary):
        interior_values.append(vertical[:, ~v_boundary])
    if np.any(h_boundary):
        boundary_values.append(horizontal[h_boundary, :])
    if np.any(~h_boundary):
        interior_values.append(horizontal[~h_boundary, :])

    boundary = (float(np.mean(np.concatenate([v.ravel() for v in boundary_values])))
                if boundary_values else 0.0)
    interior = (float(np.mean(np.concatenate([v.ravel() for v in interior_values])))
                if interior_values else 0.0)
    ratio = boundary / (interior + 1e-6)
    return {
        "block": block,
        "boundary_mean": boundary,
        "interior_mean": interior,
        "ratio": ratio,
    }


def resize_to_reference(ref: np.ndarray, cand: np.ndarray) -> tuple[np.ndarray, str | None]:
    if ref.shape == cand.shape:
        return cand, None
    ref_h, ref_w = ref.shape[:2]
    image = Image.fromarray(np.clip(cand, 0, 255).astype(np.uint8), "RGB")
    resized = image.resize((ref_w, ref_h), Image.Resampling.BILINEAR)
    return np.asarray(resized, dtype=np.float32), (
        f"candidate resized from {cand.shape[1]}x{cand.shape[0]} "
        f"to {ref_w}x{ref_h}"
    )


def compute_metrics(reference: Path, candidate: Path, block_sizes: list[int]) -> dict:
    ref = load_rgb(reference)
    cand = load_rgb(candidate)
    cand, resize_note = resize_to_reference(ref, cand)
    ref_luma = luma(ref)
    cand_luma = luma(cand)
    diff = cand - ref
    abs_diff = np.abs(diff)
    mse_rgb = float(np.mean(diff * diff))
    rmse_rgb = math.sqrt(mse_rgb)
    psnr_is_infinite = rmse_rgb <= 0.0
    psnr_db = None if psnr_is_infinite else 20.0 * math.log10(255.0 / rmse_rgb)
    luma_diff = cand_luma - ref_luma
    luma_rmse = math.sqrt(float(np.mean(luma_diff * luma_diff)))

    metrics = {
        "reference": str(reference),
        "candidate": str(candidate),
        "width": int(ref.shape[1]),
        "height": int(ref.shape[0]),
        "resize_note": resize_note,
        "mae_rgb": float(np.mean(abs_diff)),
        "mae_rgb_normalized": float(np.mean(abs_diff) / 255.0),
        "rmse_rgb": rmse_rgb,
        "psnr_db": psnr_db,
        "psnr_is_infinite": psnr_is_infinite,
        "luma_mae": float(np.mean(np.abs(luma_diff))),
        "luma_rmse": luma_rmse,
        "luma_ssim_global": global_ssim(ref_luma, cand_luma),
        "histogram_intersection_rgb": histogram_intersection(ref, cand),
        "reference_occupancy_luma_gt_8": float(np.mean(ref_luma > 8.0)),
        "candidate_occupancy_luma_gt_8": float(np.mean(cand_luma > 8.0)),
        "edge": edge_metrics(ref_luma, cand_luma),
        "blockiness": {
            "reference": {str(b): blockiness(ref_luma, b) for b in block_sizes},
            "candidate": {str(b): blockiness(cand_luma, b) for b in block_sizes},
        },
    }
    return metrics


def markdown_report(metrics: dict) -> str:
    psnr = metrics["psnr_db"]
    psnr_text = "inf" if metrics["psnr_is_infinite"] else f"{psnr:.3f}"
    lines = [
        "# QGE Image Metrics",
        "",
        f"Reference: `{metrics['reference']}`",
        f"Candidate: `{metrics['candidate']}`",
        f"Resolution: {metrics['width']}x{metrics['height']}",
    ]
    if metrics["resize_note"]:
        lines.append(f"Resize note: {metrics['resize_note']}")
    lines.extend([
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| RGB MAE | {metrics['mae_rgb']:.4f} |",
        f"| RGB MAE normalized | {metrics['mae_rgb_normalized']:.6f} |",
        f"| RGB RMSE | {metrics['rmse_rgb']:.4f} |",
        f"| PSNR dB | {psnr_text} |",
        f"| Luma MAE | {metrics['luma_mae']:.4f} |",
        f"| Luma RMSE | {metrics['luma_rmse']:.4f} |",
        f"| Global luma SSIM | {metrics['luma_ssim_global']:.6f} |",
        f"| RGB histogram intersection | {metrics['histogram_intersection_rgb']:.6f} |",
        f"| Reference occupancy luma>8 | {metrics['reference_occupancy_luma_gt_8']:.6f} |",
        f"| Candidate occupancy luma>8 | {metrics['candidate_occupancy_luma_gt_8']:.6f} |",
        f"| Edge precision | {metrics['edge']['edge_precision']:.6f} |",
        f"| Edge recall | {metrics['edge']['edge_recall']:.6f} |",
        f"| Edge F1 | {metrics['edge']['edge_f1']:.6f} |",
        f"| Edge Jaccard | {metrics['edge']['edge_jaccard']:.6f} |",
    ])
    for block, data in metrics["blockiness"]["candidate"].items():
        ref_ratio = metrics["blockiness"]["reference"][block]["ratio"]
        lines.append(f"| Blockiness ratio {block}px, reference | {ref_ratio:.6f} |")
        lines.append(f"| Blockiness ratio {block}px, candidate | {data['ratio']:.6f} |")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare QGE and classic Quake screenshots."
    )
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--block", action="append", type=int, default=[16, 32, 64],
                        help="Block size for blockiness metric; repeatable.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metrics = compute_metrics(args.reference, args.candidate, args.block)
    if args.json:
        args.json.write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n")
    if args.markdown:
        args.markdown.write_text(markdown_report(metrics))
    if not args.json and not args.markdown:
        print(json.dumps(metrics, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"qge_image_metrics.py: {exc}", file=sys.stderr)
        raise SystemExit(1)
