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


def _interpolate_nan_axis(arr: np.ndarray, axis: int) -> np.ndarray:
    work = arr.T.copy() if axis == 0 else arr.copy()
    x = np.arange(work.shape[1])
    out = np.full_like(work, np.nan, dtype=float)
    for row_index in range(work.shape[0]):
        row = work[row_index]
        valid = np.isfinite(row)
        if valid.any():
            out[row_index] = np.interp(x, x[valid], row[valid])
    return out.T if axis == 0 else out


def _fill_heatmap_gaps(z: np.ndarray, inside: np.ndarray) -> np.ndarray:
    original = np.isfinite(z)
    if not original.any():
        return z
    row_filled = _interpolate_nan_axis(z, axis=1)
    col_filled = _interpolate_nan_axis(z, axis=0)
    row_ok = np.isfinite(row_filled)
    col_ok = np.isfinite(col_filled)
    filled = z.copy()
    both = (~original) & row_ok & col_ok
    filled[both] = (row_filled[both] + col_filled[both]) / 2.0
    row_only = (~original) & row_ok & ~col_ok
    filled[row_only] = row_filled[row_only]
    col_only = (~original) & ~row_ok & col_ok
    filled[col_only] = col_filled[col_only]
    filled[original] = z[original]
    return np.where(inside, filled, np.nan)


def _heatmap_matrix(df, half: float, bin_size: float):
    grid_count = max(int(math.ceil((2.0 * half) / bin_size)), 1)
    first_center = -half + bin_size / 2.0
    x_centers = first_center + np.arange(grid_count) * bin_size
    y_centers = first_center + np.arange(grid_count) * bin_size
    z = np.full((grid_count, grid_count), np.nan, dtype=float)
    values = df[["x_bin", "y_bin", "value_mean"]].dropna().to_numpy(dtype=float)
    if values.size:
        x_idx = np.rint((values[:, 0] - first_center) / bin_size).astype(int)
        y_idx = np.rint((values[:, 1] - first_center) / bin_size).astype(int)
        valid = (x_idx >= 0) & (x_idx < grid_count) & (y_idx >= 0) & (y_idx < grid_count)
        z[y_idx[valid], x_idx[valid]] = values[valid, 2]
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
) -> Path:
    if df.empty:
        raise RuntimeError("No valid wafer heatmap data found.")

    half = float(wafer_diameter) / 2.0
    bin_value = float(bin_size)
    x_centers, y_centers, z = _heatmap_matrix(df, half, bin_value)
    mask_x, mask_y = np.meshgrid(x_centers, y_centers)
    inside = np.sqrt(mask_x ** 2 + mask_y ** 2) <= half
    z = np.where(inside, z, np.nan)
    z = _fill_heatmap_gaps(z, inside)
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
        interpolation="bilinear",
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
) -> Path:
    df = query_wafer_value_heatmap(
        input_path,
        value_col=value_col,
        bin_size=bin_size,
        wafer_diameter=wafer_diameter,
        filters=filters,
        radius_center=(center_x, center_y),
    )
    return _draw_heatmap(df, output_path, "Wafer {} Heatmap".format(value_col), value_col, wafer_diameter, bin_size, cmap, vmin, vmax)


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
    return _draw_heatmap(df, output_path, title, label, wafer_diameter, bin_size, cmap, vmin, vmax)


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
        )
    print("Saved: {}".format(path))


if __name__ == "__main__":
    main()
