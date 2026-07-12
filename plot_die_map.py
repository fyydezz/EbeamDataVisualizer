from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Optional

import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Rectangle

from ebeam_backend import query_die_value_map


def plot_die_value_map(
    input_path: str,
    output_path: str = "die_value_map.png",
    value_col: str = "CD",
    die_size_x: float = 10.0,
    die_size_y: float = 10.0,
    wafer_diameter: float = 300.0,
    filters: Optional[Dict[str, str]] = None,
    cmap: str = "jet",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
) -> Path:
    if die_size_x <= 0 or die_size_y <= 0:
        raise ValueError("Die X size and Die Y size must be greater than zero.")
    df = query_die_value_map(input_path, value_col=value_col, filters=filters)
    if df.empty:
        raise RuntimeError("No valid DieIDX/DieIDY map data found.")

    values = df[["die_idx", "die_idy", "value_mean"]].dropna().to_numpy(dtype=float)
    output = Path(output_path).resolve()
    fig, ax = plt.subplots(figsize=(8.2, 7.2), dpi=150)
    cmap_obj = plt.get_cmap(cmap).copy()
    cmap_obj.set_bad((1, 1, 1, 0))
    patches = []
    for die_x, die_y, _value in values:
        center_x = die_x * die_size_x
        center_y = die_y * die_size_y
        patches.append(Rectangle((center_x - die_size_x / 2.0, center_y - die_size_y / 2.0), die_size_x, die_size_y))
    collection = PatchCollection(patches, cmap=cmap_obj, edgecolor="#FFFFFF", linewidth=0.18)
    collection.set_array(values[:, 2])
    collection.set_clim(vmin, vmax)
    ax.add_collection(collection)
    min_x, max_x = values[:, 0].min(), values[:, 0].max()
    min_y, max_y = values[:, 1].min(), values[:, 1].max()
    ax.set_xlim((min_x - 0.5) * die_size_x, (max_x + 0.5) * die_size_x)
    ax.set_ylim((min_y - 0.5) * die_size_y, (max_y + 0.5) * die_size_y)
    if wafer_diameter > 0:
        ax.add_patch(plt.Circle((0, 0), wafer_diameter / 2.0, edgecolor="#2E3440", facecolor="none", linewidth=1.0))
    ax.axhline(0, color="#58606F", linewidth=0.6, alpha=0.6)
    ax.axvline(0, color="#58606F", linewidth=0.6, alpha=0.6)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("By Die {} Map".format(value_col))
    ax.set_xlabel("DieIDX position")
    ax.set_ylabel("DieIDY position")
    ax.grid(False)
    cbar = fig.colorbar(collection, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(value_col)
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot an image-weighted value map by DieIDX/DieIDY.")
    parser.add_argument("input", help="Input CSV, Parquet, or small XLSX file")
    parser.add_argument("-o", "--output", default="die_value_map.png")
    parser.add_argument("--value-col", default="CD")
    parser.add_argument("--die-size-x", type=float, required=True)
    parser.add_argument("--die-size-y", type=float, default=None)
    parser.add_argument("--wafer-diameter", type=float, default=300.0)
    parser.add_argument("--cmap", default="jet")
    parser.add_argument("--vmin", type=float, default=None)
    parser.add_argument("--vmax", type=float, default=None)
    parser.add_argument("--layer-type", default="")
    parser.add_argument("--layer-no", default="")
    parser.add_argument("--moduleindex", default="")
    args = parser.parse_args()
    filters = {"LayerType": args.layer_type, "LayerNO": args.layer_no, "Moduleindex": args.moduleindex}
    output = plot_die_value_map(
        args.input,
        args.output,
        args.value_col,
        args.die_size_x,
        args.die_size_y if args.die_size_y is not None else args.die_size_x,
        args.wafer_diameter,
        filters,
        args.cmap,
        args.vmin,
        args.vmax,
    )
    print("Saved: {}".format(output))


if __name__ == "__main__":
    main()
