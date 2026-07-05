from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, Optional

import matplotlib.pyplot as plt

from ebeam_backend import query_radius_sigma


COLORS = ["#1F5A8A", "#C28E2C", "#6E8B3D", "#B05A7A", "#58606F", "#5B8C8C", "#8A6FB0", "#A85C3A"]


def plot_radius_sigma(
    input_path: str,
    output_path: str = "radius_sigma.png",
    value_col: str = "CD",
    radius_bin: float = 2.0,
    filters: Optional[Dict[str, str]] = None,
    series_mode: str = "overlay",
    max_series: int = 8,
    sigma_mode: str = "radius_bin",
    center_x: float = 0.0,
    center_y: float = 0.0,
) -> Path:
    if series_mode not in {"combine", "overlay", "facets"}:
        raise ValueError("series_mode must be combine, overlay, or facets")

    df = query_radius_sigma(
        input_path,
        value_col=value_col,
        radius_bin=radius_bin,
        filters=filters,
        group_series=series_mode != "combine",
        sigma_mode=sigma_mode,
        radius_center=(center_x, center_y),
    )
    if df.empty:
        raise RuntimeError("No valid radius sigma data found.")

    labels = df.groupby("series_label")["n"].sum().sort_values(ascending=False).index.astype(str).tolist()[:max_series]
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

    for index, label in enumerate(labels):
        ax = axes_by_label[label]
        part = df[df["series_label"].astype(str) == label].sort_values("radius_bin")
        color = COLORS[index % len(COLORS)]
        ax.plot(part["radius_bin"], part["sigma"], color=color, linewidth=1.6, marker="o", markersize=3, label=label)
        ax.set_title(label if series_mode == "facets" else "Radius Sigma by Wafer Radius")
        ax.set_xlabel("Wafer radius")
        ax.set_ylabel("{} sigma".format(value_col))
        ax.grid(True, color="#D7DEE8", linewidth=0.7, alpha=0.8)

    if series_mode == "overlay" and len(labels) > 1:
        ax.legend(loc="best", fontsize=8)
    if series_mode == "facets" and len(labels) > 1:
        fig.suptitle("Radius Sigma by Wafer Radius", fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, 0.96))
    else:
        fig.tight_layout()

    output = Path(output_path).resolve()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot value sigma by wafer radius.")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", default="radius_sigma.png")
    parser.add_argument("--value-col", default="CD")
    parser.add_argument("--radius-bin", type=float, default=2.0)
    parser.add_argument("--sigma-mode", choices=["radius_bin", "image"], default="radius_bin")
    parser.add_argument("--layer-type", default="")
    parser.add_argument("--layer-no", default="")
    parser.add_argument("--moduleindex", default="")
    parser.add_argument("--series-mode", choices=["combine", "overlay", "facets"], default="overlay")
    parser.add_argument("--max-series", type=int, default=8)
    parser.add_argument("--center-x", type=float, default=0.0)
    parser.add_argument("--center-y", type=float, default=0.0)
    args = parser.parse_args()

    filters = {"LayerType": args.layer_type, "LayerNO": args.layer_no, "Moduleindex": args.moduleindex}
    path = plot_radius_sigma(
        args.input,
        args.output,
        args.value_col,
        args.radius_bin,
        filters,
        args.series_mode,
        args.max_series,
        args.sigma_mode,
        args.center_x,
        args.center_y,
    )
    print("Saved: {}".format(path))


if __name__ == "__main__":
    main()
