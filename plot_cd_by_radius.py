from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, Optional

import matplotlib.pyplot as plt

from ebeam_backend import RADIUS_COLUMN, query_radius_aggregate, query_xy


COLORS = ["#1F5A8A", "#C28E2C", "#6E8B3D", "#B05A7A", "#58606F", "#5B8C8C", "#8A6FB0", "#A85C3A"]


def plot_cd_by_radius(
    input_path: str,
    output_path: str = "cd_by_radius.png",
    value_col: str = "CD",
    radius_bin: float = 500.0,
    scatter_sample: int = 0,
    scatter_all: bool = False,
    filters: Optional[Dict[str, str]] = None,
    series_mode: str = "overlay",
    max_series: int = 8,
    center_x: float = 0.0,
    center_y: float = 0.0,
    line_only: bool = False,
    scatter_image_mean: bool = True,
) -> Path:
    if series_mode not in {"combine", "overlay", "facets"}:
        raise ValueError("series_mode must be combine, overlay, or facets")

    output = Path(output_path).resolve()
    agg = query_radius_aggregate(
        input_path,
        value_col=value_col,
        radius_bin=radius_bin,
        filters=filters,
        group_series=series_mode != "combine",
        radius_center=(center_x, center_y),
    )
    if agg.empty:
        raise RuntimeError("No valid CD/radius data found.")

    labels = agg.groupby("series_label")["n"].sum().sort_values(ascending=False).index.astype(str).tolist()[:max_series]
    if series_mode == "facets" and len(labels) > 1:
        columns = 2
        rows = int(math.ceil(len(labels) / 2.0))
        fig, axes_array = plt.subplots(rows, columns, figsize=(12, max(4.0, rows * 3.4)), dpi=140, squeeze=False)
        axes = list(axes_array.flat)
        for unused in axes[len(labels) :]:
            unused.set_visible(False)
        axes_by_label = {label: axes[index] for index, label in enumerate(labels)}
    else:
        fig, ax = plt.subplots(figsize=(11, 6.5), dpi=140)
        axes_by_label = {label: ax for label in labels}

    sample = None
    if scatter_sample > 0 or scatter_all:
        sample = query_xy(
            input_path,
            RADIUS_COLUMN,
            value_col,
            sample_rows=max(scatter_sample, 1),
            use_sample=not scatter_all,
            filters=filters,
            group_series=series_mode != "combine",
            aggregate_by_image=scatter_image_mean,
            radius_center=(center_x, center_y),
        )

    for index, label in enumerate(labels):
        ax = axes_by_label[label]
        part = agg[agg["series_label"] == label].sort_values("radius_bin")
        color = COLORS[index % len(COLORS)]
        if sample is not None and not sample.empty:
            points = sample if series_mode == "combine" else sample[sample["layer_label"].astype(str) == label]
            ax.scatter(points["x"], points["y"], s=4, alpha=0.15, color=color, linewidths=0)
        ax.plot(part["radius_bin"], part["value_mean"], color=color, linewidth=1.6, label=label)
        if not line_only:
            ax.fill_between(
                part["radius_bin"],
                part["value_mean"] - part["value_std"].fillna(0),
                part["value_mean"] + part["value_std"].fillna(0),
                color=color,
                alpha=0.16,
            )
        ax.set_title(label if series_mode == "facets" else "CD by Wafer Radius")
        ax.set_xlabel("Wafer radius")
        ax.set_ylabel(value_col)
        ax.grid(True, color="#D7DEE8", linewidth=0.7, alpha=0.8)

    if series_mode == "overlay" and len(labels) > 1:
        ax.legend(loc="best", fontsize=8)
    if series_mode == "facets" and len(labels) > 1:
        fig.suptitle("CD by Wafer Radius", fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, 0.96))
    else:
        fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot CD by wafer radius with layer filtering and series comparison.")
    parser.add_argument("input", help="Input CSV, Parquet, or small XLSX file")
    parser.add_argument("-o", "--output", default="cd_by_radius.png")
    parser.add_argument("--value-col", default="CD")
    parser.add_argument("--radius-bin", type=float, default=500.0)
    parser.add_argument("--scatter-sample", type=int, default=0)
    parser.add_argument("--scatter-all", action="store_true", help="Overlay all raw points. Use carefully for very large files.")
    parser.add_argument("--layer-type", default="", help="Comma-separated visible LayerType values")
    parser.add_argument("--layer-no", default="", help="Comma-separated visible LayerNO values")
    parser.add_argument("--moduleindex", default="", help="Comma-separated visible Moduleindex values")
    parser.add_argument("--series-mode", choices=["combine", "overlay", "facets"], default="overlay")
    parser.add_argument("--max-series", type=int, default=8)
    parser.add_argument("--center-x", type=float, default=0.0, help="Wafer center X used by Radius calculation")
    parser.add_argument("--center-y", type=float, default=0.0, help="Wafer center Y used by Radius calculation")
    parser.add_argument("--line-only", action="store_true", help="Only draw the CD mean line; hide std band.")
    parser.add_argument("--raw-scatter-rows", action="store_true", help="Draw scatter from raw rows instead of ImageID-level means.")
    args = parser.parse_args()

    filters = {"LayerType": args.layer_type, "LayerNO": args.layer_no, "Moduleindex": args.moduleindex}
    path = plot_cd_by_radius(
        args.input,
        args.output,
        args.value_col,
        args.radius_bin,
        args.scatter_sample,
        args.scatter_all,
        filters,
        args.series_mode,
        args.max_series,
        args.center_x,
        args.center_y,
        args.line_only,
        not args.raw_scatter_rows,
    )
    print("Saved: {}".format(path))


if __name__ == "__main__":
    main()
