from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def generate_demo_data(output: str = "demo_ebeam.csv", rows: int = 300_000, seed: int = 7) -> Path:
    rng = np.random.default_rng(seed)
    line_defs = [
        ("M0", 1, 0),
        ("M0", 2, 0),
        ("M1", 1, 0),
        ("M1", 2, 0),
        ("V0", 1, 1),
        ("Poly", 1, 2),
    ]
    base_rows = max(1, rows // len(line_defs))
    radius = np.sqrt(rng.random(base_rows)) * 150_000
    theta = rng.random(rows) * 2 * np.pi
    theta = rng.random(base_rows) * 2 * np.pi
    x_base = radius * np.cos(theta)
    y_base = radius * np.sin(theta)
    image_idx_base = np.arange(1, base_rows + 1)

    frames = []
    for layer_type, layer_no, module in line_defs:
        layer_shift = {"M0": -1.2, "M1": 0.4, "V0": 1.0, "Poly": -0.4}[layer_type]
        cd = 42 + layer_shift + 0.000018 * radius + 0.22 * layer_no + 0.12 * module + rng.normal(0, 1.5, base_rows)
        bending = 0.08 * np.sin(theta * 3) + rng.normal(0, 0.015, base_rows)
        frames.append(
            pd.DataFrame(
                {
                    "DieIDX": np.floor(x_base / 10000).astype(int),
                    "DieIDY": np.floor(y_base / 10000).astype(int),
                    "WaferPosX": x_base,
                    "WaferPosY": y_base,
                    "ImageID": image_idx_base,
                    "CD": cd,
                    "BendingAngle": bending,
                    "LayerType": layer_type,
                    "LayerNO": layer_no,
                    "Moduleindex": module,
                }
            )
        )
    df = pd.concat(frames, ignore_index=True)
    path = Path(output).resolve()
    df.to_csv(path, index=False)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic Ebeam test data.")
    parser.add_argument("-o", "--output", default="demo_ebeam.csv")
    parser.add_argument("--rows", type=int, default=300_000)
    args = parser.parse_args()
    print(f"Saved: {generate_demo_data(args.output, args.rows)}")


if __name__ == "__main__":
    main()
