# Ebeam Data Visualizer

Windows-friendly Ebeam data visualization toolkit for large CSV/Parquet production data.

## Included Files

| File | Purpose |
|---|---|
| `ui_app.py` | Tkinter UI application |
| `ebeam_backend.py` | Shared DuckDB data engine |
| `plot_cd_by_radius.py` | CD or other value by wafer radius |
| `plot_layer_cd_distribution.py` | Layer value distribution |
| `plot_line_cd_loading.py` | Line A/B loading by wafer radius |
| `plot_wafer_heatmap.py` | Wafer value/loading heatmap |
| `generate_demo_data.py` | Generate synthetic test data |
| `build_exe.ps1` | Build Windows executable |
| `requirements.txt` | Python dependencies |
| `脚本使用说明.md` | User guide in Chinese |
| `工程详细说明.md` | Engineering and method guide in Chinese |

## Data Fields

Recommended fields:

```text
DieIDX, DieIDY, WaferPosX, WaferPosY, ImageID, CD, BendingAngle,
LayerType, LayerNO, Moduleindex
```

`ImageIDX` is still accepted as a backward-compatible alias, but new data and scripts use `ImageID`.

`Value column` is not limited to `CD`. You can choose any numeric measurement column, such as `CD`, `BendingAngle`, or other process metrics.

## Install

```powershell
cd "D:\python demo\EbeamDataVisualizer"
python -m pip install -r requirements.txt
```

## Run UI

```powershell
python ui_app.py
```

The UI now dynamically shows only controls needed by the selected chart type.

## Quick Commands

CD by radius:

```powershell
python plot_cd_by_radius.py demo_ebeam_imageid_mm.csv -o cd_radius.png --value-col CD --radius-bin 2 --layer-type M0 --layer-no 1 --line-only
```

Layer distribution:

```powershell
python plot_layer_cd_distribution.py demo_ebeam_imageid_mm.csv -o layer_dist.png --value-col CD --layer-type M0 --series-mode overlay
```

Line loading by radius:

```powershell
python plot_line_cd_loading.py demo_ebeam_imageid_mm.csv -o loading_radius.png --value-col CD --a-layer-type M0 --a-layer-no 1 --b-layer-type M0 --b-layer-no 2 --operation subtract --radius-bin 2
```

Wafer value heatmap:

```powershell
python plot_wafer_heatmap.py demo_ebeam_imageid_mm.csv -o wafer_cd_heatmap.png --mode value --value-col CD --layer-type M0 --layer-no 1 --bin-size 5 --wafer-diameter 300 --vmin 12 --vmax 15
```

Wafer loading heatmap:

```powershell
python plot_wafer_heatmap.py demo_ebeam_imageid_mm.csv -o wafer_loading_heatmap.png --mode loading --value-col CD --a-layer-type M0 --a-layer-no 1 --b-layer-type M0 --b-layer-no 2 --operation subtract --bin-size 5 --wafer-diameter 300 --cmap coolwarm --vmin -0.5 --vmax 0.5
```

## Build EXE

```powershell
cd "D:\python demo\EbeamDataVisualizer"
.\build_exe.ps1
```

Output:

```text
dist\EbeamDataVisualizer\EbeamDataVisualizer.exe
```

Copy the full `dist\EbeamDataVisualizer` folder, not only the `.exe`.

## Large Data Notes

- Prefer CSV or Parquet for production data.
- Avoid Excel for very large data.
- Radius and loading charts aggregate in DuckDB before returning data to Python.
- Scatter can use ImageID-level means to reduce overplotting.
- Heatmap bins aggregate in DuckDB and return only grid-level results.
- Fix `Color min` and `Color max` when comparing different wafers.
