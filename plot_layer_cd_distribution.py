from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, Optional

import matplotlib.pyplot as plt
import numpy as np

from ebeam_backend import query_layer_histogram


COLORS = ["#1F5A8A", "#C28E2C", "#6E8B3D", "#B05A7A", "#58606F", "#5B8C8C", "#8A6FB0", "#A85C3A"]


def _parse_series_colors(text: str, labels) -> Dict[str, str]:
    if not text:
        return {}
    color_map = {}
    ordered_colors = []
    tokens = []
    for chunk in text.replace("\n", ";").split(";"):
        tokens.extend([part.strip() for part in chunk.split(",") if part.strip()])
    for token in tokens:
        if ":" in token:
            key, color = token.rsplit(":", 1)
            key = key.strip()
            color = color.strip()
            if key and color:
                for label in labels:
                    if key == label or key in label:
                        color_map[label] = color
            continue
        ordered_colors.append(token)
    for index, color in enumerate(ordered_colors):
        if index < len(labels) and labels[index] not in color_map:
            color_map[labels[index]] = color
    return color_map


def _normal_pdf(x: np.ndarray, mean: float, std: float) -> np.ndarray:
    if not np.isfinite(std) or std <= 0:
        return np.zeros_like(x)
    return np.exp(-0.5 * ((x - mean) / std) ** 2) / (std * np.sqrt(2 * np.pi))


def plot_layer_cd_distribution(
    input_path: str,
    output_path: str = "layer_cd_distribution.png",
    value_col: str = "CD",
    bins: int = 80,
    max_layers: int = 8,
    filters: Optional[Dict[str, str]] = None,
    series_mode: str = "overlay",
    series_colors: str = "",
) -> Path:
    if series_mode not in {"combine", "overlay", "facets"}:
        raise ValueError("series_mode must be combine, overlay, or facets")

    output = Path(output_path).resolve()
    hist, stats = query_layer_histogram(
        input_path,
        value_col=value_col,
        bins=bins,
        max_layers=max_layers,
        filters=filters,
        group_series=series_mode != "combine",
    )
    if hist.empty or stats.empty:
        raise RuntimeError("No valid layer distribution data found.")

    labels = stats["layer_label"].astype(str).tolist()
    color_map = _parse_series_colors(series_colors, labels)
    if series_mode == "facets" and len(labels) > 1:
        columns = 2
        rows = int(math.ceil(len(labels) / 2.0))
        fig, axes_array = plt.subplots(rows, columns, figsize=(12, max(4.0, rows * 3.4)), dpi=140, squeeze=False)
        axes = list(axes_array.flat)
        for unused in axes[len(labels) :]:
            unused.set_visible(False)
        axes_by_label = {label: axes[index] for index, label in enumerate(labels)}
    else:
        fig, ax = plt.subplots(figsize=(12, 7), dpi=140)
        axes_by_label = {label: ax for label in labels}

    for index, row in stats.iterrows():
        label = str(row["layer_label"])
        ax = axes_by_label[label]
        part = hist[hist["layer_label"].astype(str) == label].copy()
        if part.empty:
            continue
        total = part["n"].sum()
        y = part["n"] / total
        color = color_map.get(label, COLORS[index % len(COLORS)])
        legend_label = "{} (μ={:.4g}, σ={:.4g}, n={})".format(label, float(row["mean"]), float(row["std"]), int(total))
        ax.plot(part["bin_center"], y, marker="o", markersize=2.5, linewidth=1.4, color=color, label=legend_label)

        x = np.linspace(part["bin_center"].min(), part["bin_center"].max(), 250)
        pdf = _normal_pdf(x, float(row["mean"]), float(row["std"]))
        if pdf.max() > 0:
            pdf_scaled = pdf / pdf.sum() * len(part)
            pdf_scaled = pdf_scaled / max(pdf_scaled.max(), 1e-12) * max(y.max(), 1e-12)
            ax.plot(x, pdf_scaled, linestyle="--", linewidth=1.0, color=color, alpha=0.75)
        ax.set_title(label if series_mode == "facets" else "CD Distribution by Layer")
        ax.set_xlabel(value_col)
        ax.set_ylabel("Share within layer bin")
        ax.grid(True, color="#D7DEE8", linewidth=0.7, alpha=0.8)

    if series_mode == "overlay" and len(labels) > 1:
        ax.legend(loc="best", fontsize=8)
    if series_mode == "facets" and len(labels) > 1:
        fig.suptitle("CD Distribution by Layer", fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, 0.96))
    else:
        fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot CD distributions with layer filtering and series comparison.")
    parser.add_argument("input", help="Input CSV, Parquet, or small XLSX file")
    parser.add_argument("-o", "--output", default="layer_cd_distribution.png")
    parser.add_argument("--value-col", default="CD")
    parser.add_argument("--bins", type=int, default=80)
    parser.add_argument("--max-layers", type=int, default=8)
    parser.add_argument("--layer-type", default="", help="Comma-separated visible LayerType values")
    parser.add_argument("--layer-no", default="", help="Comma-separated visible LayerNO values")
    parser.add_argument("--moduleindex", default="", help="Comma-separated visible Moduleindex values")
    parser.add_argument("--series-mode", choices=["combine", "overlay", "facets"], default="overlay")
    parser.add_argument("--series-colors", default="", help="Comma-separated colors, or label-fragment:color pairs separated by semicolon")
    args = parser.parse_args()

    filters = {"LayerType": args.layer_type, "LayerNO": args.layer_no, "Moduleindex": args.moduleindex}
    path = plot_layer_cd_distribution(
        args.input,
        args.output,
        args.value_col,
        args.bins,
        args.max_layers,
        filters,
        args.series_mode,
        args.series_colors,
    )
    print("Saved: {}".format(path))


if __name__ == "__main__":
    main()
