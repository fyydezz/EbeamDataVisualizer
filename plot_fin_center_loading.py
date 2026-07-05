from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict

import matplotlib.pyplot as plt

from ebeam_backend import query_fin_center_loading


COLORS = ["#1F5A8A", "#C28E2C", "#6E8B3D", "#B05A7A", "#58606F", "#5B8C8C", "#8A6FB0", "#A85C3A"]


def _line_spec(layer_type: str, layer_no: str, moduleindex: str) -> Dict[str, str]:
    return {"LayerType": layer_type, "LayerNO": layer_no, "Moduleindex": moduleindex}


def plot_fin_center_loading(
    input_path: str,
    output_path: str = "fin_center_loading.png",
    a_layer_type: str = "",
    a_layer_no: str = "",
    a_moduleindex: str = "",
    b_layer_type: str = "",
    b_layer_no: str = "",
    b_moduleindex: str = "",
    c_layer_type: str = "",
    c_layer_no: str = "",
    c_moduleindex: str = "",
    value_col: str = "CD",
    radius_bin: float = 2.0,
    series_mode: str = "combine",
    max_series: int = 8,
    center_x: float = 0.0,
    center_y: float = 0.0,
) -> Path:
    if series_mode not in {"combine", "overlay", "facets"}:
        raise ValueError("series_mode must be combine, overlay, or facets")

    df = query_fin_center_loading(
        input_path,
        _line_spec(a_layer_type, a_layer_no, a_moduleindex),
        _line_spec(b_layer_type, b_layer_no, b_moduleindex),
        _line_spec(c_layer_type, c_layer_no, c_moduleindex),
        radius_bin=radius_bin,
        value_col=value_col,
        group_series=series_mode != "combine",
        radius_center=(center_x, center_y),
    )
    if df.empty:
        raise RuntimeError("No valid FIN center loading data found.")

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
        ax.plot(part["radius_bin"], part["loading_mean"], color=color, linewidth=1.6, marker="o", markersize=3, label=label)
        ax.fill_between(
            part["radius_bin"],
            part["loading_mean"] - part["loading_std"].fillna(0),
            part["loading_mean"] + part["loading_std"].fillna(0),
            color=color,
            alpha=0.16,
        )
        ax.axhline(0, color="#58606F", linewidth=1.0, linestyle="--")
        ax.set_title(label if series_mode == "facets" else "FIN Center Loading by Wafer Radius")
        ax.set_xlabel("Wafer radius")
        ax.set_ylabel("((A + C) / 2) - B")
        ax.grid(True, color="#D7DEE8", linewidth=0.7, alpha=0.8)

    if series_mode == "overlay" and len(labels) > 1:
        ax.legend(loc="best", fontsize=8)
    if series_mode == "facets" and len(labels) > 1:
        fig.suptitle("FIN Center Loading by Wafer Radius", fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, 0.96))
    else:
        fig.tight_layout()

    output = Path(output_path).resolve()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot FIN center loading: ((Line A + Line C) / 2) - Line B.")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", default="fin_center_loading.png")
    parser.add_argument("--a-layer-type", default="")
    parser.add_argument("--a-layer-no", default="")
    parser.add_argument("--a-moduleindex", default="")
    parser.add_argument("--b-layer-type", default="")
    parser.add_argument("--b-layer-no", default="")
    parser.add_argument("--b-moduleindex", default="")
    parser.add_argument("--c-layer-type", default="")
    parser.add_argument("--c-layer-no", default="")
    parser.add_argument("--c-moduleindex", default="")
    parser.add_argument("--value-col", default="CD")
    parser.add_argument("--radius-bin", type=float, default=2.0)
    parser.add_argument("--series-mode", choices=["combine", "overlay", "facets"], default="combine")
    parser.add_argument("--max-series", type=int, default=8)
    parser.add_argument("--center-x", type=float, default=0.0)
    parser.add_argument("--center-y", type=float, default=0.0)
    args = parser.parse_args()

    path = plot_fin_center_loading(
        args.input,
        args.output,
        args.a_layer_type,
        args.a_layer_no,
        args.a_moduleindex,
        args.b_layer_type,
        args.b_layer_no,
        args.b_moduleindex,
        args.c_layer_type,
        args.c_layer_no,
        args.c_moduleindex,
        args.value_col,
        args.radius_bin,
        args.series_mode,
        args.max_series,
        args.center_x,
        args.center_y,
    )
    print("Saved: {}".format(path))


if __name__ == "__main__":
    main()
