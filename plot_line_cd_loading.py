from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict

import matplotlib.pyplot as plt

from ebeam_backend import query_line_loading


COLORS = ["#1F5A8A", "#C28E2C", "#6E8B3D", "#B05A7A", "#58606F", "#5B8C8C", "#8A6FB0", "#A85C3A"]


def _line_spec(layer_type: str, layer_no: str, moduleindex: str) -> Dict[str, str]:
    return {"LayerType": layer_type, "LayerNO": layer_no, "Moduleindex": moduleindex}


def plot_line_cd_loading(
    input_path: str,
    output_path: str = "line_cd_loading_by_radius.png",
    a_layer_type: str = "",
    a_layer_no: str = "",
    a_moduleindex: str = "",
    b_layer_type: str = "",
    b_layer_no: str = "",
    b_moduleindex: str = "",
    operation: str = "subtract",
    value_col: str = "CD",
    radius_bin: float = 500.0,
    series_mode: str = "overlay",
    max_series: int = 8,
    center_x: float = 0.0,
    center_y: float = 0.0,
) -> Path:
    if series_mode not in {"combine", "overlay", "facets"}:
        raise ValueError("series_mode must be combine, overlay, or facets")

    output = Path(output_path).resolve()
    df = query_line_loading(
        input_path,
        _line_spec(a_layer_type, a_layer_no, a_moduleindex),
        _line_spec(b_layer_type, b_layer_no, b_moduleindex),
        operation=operation,
        radius_bin=radius_bin,
        value_col=value_col,
        group_series=series_mode != "combine",
        radius_center=(center_x, center_y),
    )
    if df.empty:
        raise RuntimeError("No paired line data found. Check LayerType/LayerNO/Moduleindex filters.")

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

    op_label = {"subtract": "A - B", "add": "A + B", "ratio": "A / B"}[operation]
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
        ax.set_title(label if series_mode == "facets" else "Line CD Loading by Wafer Radius ({})".format(op_label))
        ax.set_xlabel("Wafer radius")
        ax.set_ylabel("{} loading".format(value_col))
        ax.grid(True, color="#D7DEE8", linewidth=0.7, alpha=0.8)

    if series_mode == "overlay" and len(labels) > 1:
        ax.legend(loc="best", fontsize=8)
    if series_mode == "facets" and len(labels) > 1:
        fig.suptitle("Line CD Loading by Wafer Radius ({})".format(op_label), fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, 0.96))
    else:
        fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare selected Ebeam lines and plot CD loading by radius.")
    parser.add_argument("input", help="Input CSV, Parquet, or small XLSX file")
    parser.add_argument("-o", "--output", default="line_cd_loading_by_radius.png")
    parser.add_argument("--a-layer-type", default="", help="Comma-separated Line A LayerType values")
    parser.add_argument("--a-layer-no", default="", help="Comma-separated Line A LayerNO values")
    parser.add_argument("--a-moduleindex", default="", help="Comma-separated Line A Moduleindex values")
    parser.add_argument("--b-layer-type", default="", help="Comma-separated Line B LayerType values")
    parser.add_argument("--b-layer-no", default="", help="Comma-separated Line B LayerNO values")
    parser.add_argument("--b-moduleindex", default="", help="Comma-separated Line B Moduleindex values")
    parser.add_argument("--operation", choices=["subtract", "add", "ratio"], default="subtract")
    parser.add_argument("--value-col", default="CD")
    parser.add_argument("--radius-bin", type=float, default=500.0)
    parser.add_argument("--series-mode", choices=["combine", "overlay", "facets"], default="overlay")
    parser.add_argument("--max-series", type=int, default=8)
    parser.add_argument("--center-x", type=float, default=0.0, help="Wafer center X used by Radius calculation")
    parser.add_argument("--center-y", type=float, default=0.0, help="Wafer center Y used by Radius calculation")
    args = parser.parse_args()

    path = plot_line_cd_loading(
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
        args.radius_bin,
        args.series_mode,
        args.max_series,
        args.center_x,
        args.center_y,
    )
    print("Saved: {}".format(path))


if __name__ == "__main__":
    main()
