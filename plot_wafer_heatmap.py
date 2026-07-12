from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, Optional

import matplotlib.pyplot as plt
import numpy as np

from ebeam_backend import query_wafer_loading_heatmap, query_wafer_value_heatmap


def _line_spec(layer_type: str, layer_no: str, moduleindex: str) -> Dict[str, str]:
    return {"LayerType": layer_type, "LayerNO": layer_no, "Moduleindex": moduleindex}


def _shift_grid(values: np.ndarray, dy: int, dx: int, fill_value=np.nan) -> np.ndarray:
    shifted = np.full_like(values, fill_value)
    if abs(dy) >= values.shape[0] or abs(dx) >= values.shape[1]:
        return shifted
    source_y0, source_y1 = max(0, -dy), values.shape[0] - max(0, dy)
    source_x0, source_x1 = max(0, -dx), values.shape[1] - max(0, dx)
    target_y0, target_y1 = max(0, dy), values.shape[0] - max(0, -dy)
    target_x0, target_x1 = max(0, dx), values.shape[1] - max(0, -dx)
    shifted[target_y0:target_y1, target_x0:target_x1] = values[source_y0:source_y1, source_x0:source_x1]
    return shifted


def _nearest_image_completion(z: np.ndarray, inside: np.ndarray) -> np.ndarray:
    valid = np.isfinite(z) & inside
    if not valid.any():
        return z
    rows, cols = z.shape
    yy, xx = np.indices(z.shape)
    nearest_y = np.where(valid, yy, -1)
    nearest_x = np.where(valid, xx, -1)
    step = 1
    while step < max(rows, cols):
        step *= 2
    while step:
        current_valid = nearest_y >= 0
        current_distance = np.where(
            current_valid,
            (yy - nearest_y) ** 2 + (xx - nearest_x) ** 2,
            np.inf,
        )
        for dy in (-step, 0, step):
            for dx in (-step, 0, step):
                if dy == 0 and dx == 0:
                    continue
                candidate_y = _shift_grid(nearest_y, dy, dx, fill_value=-1)
                candidate_x = _shift_grid(nearest_x, dy, dx, fill_value=-1)
                candidate_valid = candidate_y >= 0
                candidate_distance = (yy - candidate_y) ** 2 + (xx - candidate_x) ** 2
                replace = candidate_valid & ((~current_valid) | (candidate_distance < current_distance))
                nearest_y[replace] = candidate_y[replace]
                nearest_x[replace] = candidate_x[replace]
                current_valid[replace] = True
                current_distance[replace] = candidate_distance[replace]
        step //= 2
    completed = z.copy()
    missing = inside & ~np.isfinite(completed) & (nearest_y >= 0)
    completed[missing] = z[nearest_y[missing], nearest_x[missing]]
    return np.where(inside, completed, np.nan)


def _smooth_heatmap_gaps(z: np.ndarray, inside: np.ndarray) -> np.ndarray:
    """Use local averaging first, then nearest-image completion for display only."""
    filled = np.where(inside, z, np.nan).copy()
    if not np.isfinite(filled).any():
        return filled
    original = np.isfinite(filled)
    neighbours = [
        (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, 0.707), (-1, 1, 0.707), (1, -1, 0.707), (1, 1, 0.707),
    ]
    for _ in range(32):
        missing = inside & ~np.isfinite(filled)
        if not missing.any():
            break
        numerator = np.zeros_like(filled, dtype=float)
        denominator = np.zeros_like(filled, dtype=float)
        for dy, dx, weight in neighbours:
            neighbour = _shift_grid(filled, dy, dx)
            valid = np.isfinite(neighbour)
            numerator[valid] += neighbour[valid] * weight
            denominator[valid] += weight
        update = missing & (denominator > 0)
        if not update.any():
            break
        filled[update] = numerator[update] / denominator[update]
    filled[original] = z[original]
    return _nearest_image_completion(filled, inside)


def _heatmap_matrix(df, half: float, bin_size: float):
    grid_count = max(int(math.ceil((2.0 * half) / bin_size)), 1)
    first_center = -half + bin_size / 2.0
    x_centers = first_center + np.arange(grid_count) * bin_size
    y_centers = first_center + np.arange(grid_count) * bin_size
    z = np.full((grid_count, grid_count), np.nan, dtype=float)
    if {"x_bin_id", "y_bin_id"}.issubset(df.columns):
        values = df[["x_bin_id", "y_bin_id", "value_mean"]].dropna().to_numpy(dtype=float)
        x_idx = values[:, 0].astype(int)
        y_idx = values[:, 1].astype(int)
    else:
        values = df[["x_bin", "y_bin", "value_mean"]].dropna().to_numpy(dtype=float)
        x_idx = np.rint((values[:, 0] - first_center) / bin_size).astype(int)
        y_idx = np.rint((values[:, 1] - first_center) / bin_size).astype(int)
    if values.size:
        valid = (x_idx >= 0) & (x_idx < grid_count) & (y_idx >= 0) & (y_idx < grid_count)
        z[y_idx[valid], x_idx[valid]] = values[valid, -1]
    return x_centers, y_centers, z


def _draw_heatmap(
    df,
    output_path: str,
    title: str,
    colorbar_label: str,
    wafer_diameter: float = 300.0,
    bin_size: float = 5.0,
    cmap: str = "jet",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    render_style: str = "smooth",
) -> Path:
    if df.empty:
        raise RuntimeError("No valid wafer heatmap data found.")

    half = float(wafer_diameter) / 2.0
    bin_value = float(bin_size)
    x_centers, y_centers, z = _heatmap_matrix(df, half, bin_value)
    mask_x, mask_y = np.meshgrid(x_centers, y_centers)
    inside = np.sqrt(mask_x ** 2 + mask_y ** 2) <= half
    z = np.where(inside, z, np.nan)
    if render_style == "smooth":
        z = _smooth_heatmap_gaps(z, inside)
    if not np.isfinite(z).any():
        raise RuntimeError("No finite wafer heatmap cells found after binning. Try a larger bin size or clear filters.")

    output = Path(output_path).resolve()
    fig, ax = plt.subplots(figsize=(8.2, 7.2), dpi=150)
    cmap_obj = plt.get_cmap(cmap).copy()
    cmap_obj.set_bad((1, 1, 1, 0))
    mesh = ax.imshow(
        z,
        extent=(-half, half, -half, half),
        origin="lower",
        cmap=cmap_obj,
        interpolation="bilinear" if render_style == "smooth" else "nearest",
        vmin=vmin,
        vmax=vmax,
    )
    ax.add_patch(plt.Circle((0, 0), half, edgecolor="#2E3440", facecolor="none", linewidth=1.2))
    ax.axhline(0, color="#58606F", linewidth=0.6, alpha=0.65)
    ax.axvline(0, color="#58606F", linewidth=0.6, alpha=0.65)
    ax.set_title(title)
    ax.set_xlabel("WaferPosX")
    ax.set_ylabel("WaferPosY")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-half, half)
    ax.set_ylim(-half, half)
    ax.grid(False)
    cbar = fig.colorbar(mesh, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(colorbar_label)
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output


def plot_wafer_value_heatmap(
    input_path: str,
    output_path: str = "wafer_value_heatmap.png",
    value_col: str = "CD",
    bin_size: float = 5.0,
    wafer_diameter: float = 300.0,
    filters: Optional[Dict[str, str]] = None,
    center_x: float = 0.0,
    center_y: float = 0.0,
    cmap: str = "jet",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    render_style: str = "smooth",
) -> Path:
    df = query_wafer_value_heatmap(
        input_path,
        value_col=value_col,
        bin_size=bin_size,
        wafer_diameter=wafer_diameter,
        filters=filters,
        radius_center=(center_x, center_y),
    )
    return _draw_heatmap(df, output_path, "Wafer {} Heatmap".format(value_col), value_col, wafer_diameter, bin_size, cmap, vmin, vmax, render_style)


def plot_wafer_loading_heatmap(
    input_path: str,
    output_path: str = "wafer_loading_heatmap.png",
    a_layer_type: str = "",
    a_layer_no: str = "",
    a_moduleindex: str = "",
    b_layer_type: str = "",
    b_layer_no: str = "",
    b_moduleindex: str = "",
    operation: str = "subtract",
    value_col: str = "CD",
    bin_size: float = 5.0,
    wafer_diameter: float = 300.0,
    center_x: float = 0.0,
    center_y: float = 0.0,
    cmap: str = "jet",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    render_style: str = "smooth",
) -> Path:
    df = query_wafer_loading_heatmap(
        input_path,
        _line_spec(a_layer_type, a_layer_no, a_moduleindex),
        _line_spec(b_layer_type, b_layer_no, b_moduleindex),
        operation=operation,
        value_col=value_col,
        bin_size=bin_size,
        wafer_diameter=wafer_diameter,
        radius_center=(center_x, center_y),
    )
    label = "{} loading".format(value_col)
    title = "Wafer Loading Heatmap ({})".format({"subtract": "A - B", "add": "A + B", "ratio": "A / B"}[operation])
    return _draw_heatmap(df, output_path, title, label, wafer_diameter, bin_size, cmap, vmin, vmax, render_style)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot wafer value or line-loading heatmaps.")
    parser.add_argument("input", help="Input CSV, Parquet, or small XLSX file")
    parser.add_argument("-o", "--output", default="wafer_heatmap.png")
    parser.add_argument("--mode", choices=["value", "loading"], default="value")
    parser.add_argument("--value-col", default="CD")
    parser.add_argument("--bin-size", type=float, default=5.0)
    parser.add_argument("--wafer-diameter", type=float, default=300.0)
    parser.add_argument("--center-x", type=float, default=0.0)
    parser.add_argument("--center-y", type=float, default=0.0)
    parser.add_argument("--cmap", default="")
    parser.add_argument("--vmin", type=float, default=None)
    parser.add_argument("--vmax", type=float, default=None)
    parser.add_argument("--render-style", choices=["smooth", "cells"], default="smooth")
    parser.add_argument("--layer-type", default="", help="Value heatmap LayerType filter")
    parser.add_argument("--layer-no", default="", help="Value heatmap LayerNO filter")
    parser.add_argument("--moduleindex", default="", help="Value heatmap Moduleindex filter")
    parser.add_argument("--a-layer-type", default="")
    parser.add_argument("--a-layer-no", default="")
    parser.add_argument("--a-moduleindex", default="")
    parser.add_argument("--b-layer-type", default="")
    parser.add_argument("--b-layer-no", default="")
    parser.add_argument("--b-moduleindex", default="")
    parser.add_argument("--operation", choices=["subtract", "add", "ratio"], default="subtract")
    args = parser.parse_args()

    if args.mode == "value":
        filters = {"LayerType": args.layer_type, "LayerNO": args.layer_no, "Moduleindex": args.moduleindex}
        path = plot_wafer_value_heatmap(
            args.input,
            args.output,
            args.value_col,
            args.bin_size,
            args.wafer_diameter,
            filters,
            args.center_x,
            args.center_y,
            args.cmap or "jet",
            args.vmin,
            args.vmax,
            args.render_style,
        )
    else:
        path = plot_wafer_loading_heatmap(
            args.input,
            args.output,
            args.a_layer_type,
            args.a_layer_no,
            args.a_moduleindex,
            args.b_layer_type,
            args.b_layer_no,
            args.b_moduleindex,
            args.operation,
            args.value_col,
            args.bin_size,
            args.wafer_diameter,
            args.center_x,
            args.center_y,
            args.cmap or "jet",
            args.vmin,
            args.vmax,
            args.render_style,
        )
    print("Saved: {}".format(path))


if __name__ == "__main__":
    main()
