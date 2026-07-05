from __future__ import annotations

import math
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ebeam_backend import RADIUS_COLUMN, distinct_values, list_columns, list_plot_columns, query_fin_center_loading, query_layer_histogram, query_line_loading, query_radius_aggregate, query_radius_sigma, query_wafer_loading_heatmap, query_wafer_value_heatmap, query_xy, split_filter_values


SERIES_COLORS = ["#1F5A8A", "#C28E2C", "#6E8B3D", "#B05A7A", "#58606F", "#5B8C8C", "#8A6FB0", "#A85C3A"]
SERIES_LINESTYLES = ["-", "--", "-.", ":"]


class EbeamVisualizerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Ebeam Data Visualizer")
        self.geometry("1180x780")
        self.minsize(980, 640)

        self.input_path = tk.StringVar()
        self.chart_type = tk.StringVar(value="CD by wafer radius")
        self.x_axis = tk.StringVar(value="WaferPosX")
        self.y_axis = tk.StringVar(value="CD")
        self.value_col = tk.StringVar(value="CD")
        self.radius_bin = tk.DoubleVar(value=500.0)
        self.radius_center_x = tk.StringVar(value="0")
        self.radius_center_y = tk.StringVar(value="0")
        self.wafer_diameter = tk.DoubleVar(value=300.0)
        self.heatmap_bin = tk.DoubleVar(value=5.0)
        self.color_min = tk.StringVar()
        self.color_max = tk.StringVar()
        self.colormap = tk.StringVar(value="jet")
        self.sigma_mode = tk.StringVar(value="radius_bin")
        self.sample_rows = tk.IntVar(value=150000)
        self.data_mode = tk.StringVar(value="Sample")
        self.series_mode = tk.StringVar(value="Overlay selected series")
        self.max_layers = tk.IntVar(value=8)
        self.operation = tk.StringVar(value="subtract")
        self.status = tk.StringVar(value="Select a data file.")
        self.x_min = tk.StringVar()
        self.x_max = tk.StringVar()
        self.y_min = tk.StringVar()
        self.y_max = tk.StringVar()
        self.line_color = tk.StringVar(value="#1F5A8A")
        self.band_color = tk.StringVar(value="#8FB6D9")
        self.outlier_color = tk.StringVar(value="#B05A7A")
        self.scatter_color = tk.StringVar(value="#1F5A8A")
        self.series_colors = tk.StringVar()
        self.line_width = tk.DoubleVar(value=2.2)
        self.scatter_size = tk.DoubleVar(value=4.0)
        self.scatter_alpha = tk.DoubleVar(value=0.75)
        self.radius_line_only = tk.BooleanVar(value=False)
        self.scatter_by_image = tk.BooleanVar(value=True)
        self.x_label = tk.StringVar()
        self.y_label = tk.StringVar()
        self.axis_label_size = tk.DoubleVar(value=10.0)
        self.axis_label_weight = tk.StringVar(value="normal")
        self.filter_layer_type = tk.StringVar()
        self.filter_layer_no = tk.StringVar()
        self.filter_moduleindex = tk.StringVar()

        self.a_layer_type = tk.StringVar()
        self.a_layer_no = tk.StringVar()
        self.a_moduleindex = tk.StringVar()
        self.b_layer_type = tk.StringVar()
        self.b_layer_no = tk.StringVar()
        self.b_moduleindex = tk.StringVar()
        self.c_layer_type = tk.StringVar()
        self.c_layer_no = tk.StringVar()
        self.c_moduleindex = tk.StringVar()

        self.columns = []
        self.plot_columns = []
        self.result_queue = queue.Queue()
        self.control_panel = None
        self.panel_grid_options = {}
        self.style_controls = {}
        self.style_grid_options = {}
        self.last_plot_kind = None
        self.last_plot_payload = None
        self._style_redraw_job = None

        self._build_ui()
        self._install_auto_style_traces()
        self.update_control_visibility()
        self.after(200, self._poll_results)

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        panel_host = ttk.Frame(self)
        panel_host.grid(row=0, column=0, sticky="ns")
        panel_host.rowconfigure(0, weight=1)
        panel_host.columnconfigure(0, weight=1)

        panel_canvas = tk.Canvas(panel_host, width=360, highlightthickness=0)
        panel_scroll = ttk.Scrollbar(panel_host, orient="vertical", command=panel_canvas.yview)
        panel_canvas.configure(yscrollcommand=panel_scroll.set)
        panel_canvas.grid(row=0, column=0, sticky="ns")
        panel_scroll.grid(row=0, column=1, sticky="ns")

        panel = ttk.Frame(panel_canvas, padding=10)
        self.control_panel = panel
        panel_window = panel_canvas.create_window((0, 0), window=panel, anchor="nw")

        def _sync_scroll_region(_event=None):
            panel_canvas.configure(scrollregion=panel_canvas.bbox("all"))
            panel_canvas.itemconfigure(panel_window, width=panel_canvas.winfo_width())

        def _on_mousewheel(event):
            panel_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        panel.bind("<Configure>", _sync_scroll_region)
        panel_canvas.bind("<Configure>", _sync_scroll_region)
        panel_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        ttk.Label(panel, text="Data file").grid(row=0, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.input_path, width=42).grid(row=1, column=0, sticky="ew", pady=(2, 4))
        ttk.Button(panel, text="Browse", command=self.browse_file).grid(row=2, column=0, sticky="ew")
        ttk.Button(panel, text="Load Columns", command=self.load_columns).grid(row=3, column=0, sticky="ew", pady=(4, 10))

        ttk.Label(panel, text="Chart type").grid(row=4, column=0, sticky="w")
        chart_box = ttk.Combobox(
            panel,
            textvariable=self.chart_type,
            values=[
                "CD by wafer radius",
                "Radius sigma by wafer radius",
                "Layer CD distribution",
                "Line CD loading",
                "FIN center loading",
                "Wafer value heatmap",
                "Wafer loading heatmap",
                "Custom X-Y scatter",
            ],
            state="readonly",
            width=38,
        )
        chart_box.grid(row=5, column=0, sticky="ew", pady=(2, 10))
        chart_box.bind("<<ComboboxSelected>>", self.on_chart_change)

        self.x_combo = self._combo(panel, "X axis", self.x_axis, 6)
        self.y_combo = self._combo(panel, "Y axis", self.y_axis, 8)
        self.value_combo = self._combo(panel, "Value column", self.value_col, 10)

        ttk.Label(panel, text="Radius bin").grid(row=12, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.radius_bin, width=12).grid(row=13, column=0, sticky="ew", pady=(2, 8))
        sigma_frame = ttk.LabelFrame(panel, text="Sigma settings", padding=6)
        sigma_frame.grid(row=14, column=0, sticky="ew", pady=(2, 8))
        sigma_frame.columnconfigure(1, weight=1)
        ttk.Label(sigma_frame, text="Mode").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            sigma_frame,
            textvariable=self.sigma_mode,
            values=["radius_bin", "image"],
            state="readonly",
            width=16,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        heatmap_frame = ttk.LabelFrame(panel, text="Wafer / heatmap", padding=6)
        heatmap_frame.grid(row=15, column=0, sticky="ew", pady=(2, 8))
        heatmap_frame.columnconfigure(1, weight=1)
        heatmap_frame.columnconfigure(3, weight=1)
        ttk.Label(heatmap_frame, text="Diameter").grid(row=0, column=0, sticky="w")
        ttk.Entry(heatmap_frame, textvariable=self.wafer_diameter, width=9).grid(row=0, column=1, sticky="ew", padx=(4, 8))
        ttk.Label(heatmap_frame, text="Bin").grid(row=0, column=2, sticky="w")
        ttk.Entry(heatmap_frame, textvariable=self.heatmap_bin, width=9).grid(row=0, column=3, sticky="ew", padx=(4, 0))
        ttk.Label(heatmap_frame, text="Color min").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(heatmap_frame, textvariable=self.color_min, width=9).grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=(4, 0))
        ttk.Label(heatmap_frame, text="Color max").grid(row=1, column=2, sticky="w", pady=(4, 0))
        ttk.Entry(heatmap_frame, textvariable=self.color_max, width=9).grid(row=1, column=3, sticky="ew", padx=(4, 0), pady=(4, 0))
        ttk.Label(heatmap_frame, text="Map").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Combobox(heatmap_frame, textvariable=self.colormap, values=["jet", "turbo", "RdYlBu_r", "coolwarm", "viridis", "plasma", "inferno", "magma", "cividis"], state="readonly", width=14).grid(row=2, column=1, columnspan=3, sticky="ew", padx=(4, 0), pady=(4, 0))

        center_frame = ttk.LabelFrame(panel, text="Wafer center for Radius", padding=6)
        center_frame.grid(row=16, column=0, sticky="ew", pady=(2, 8))
        center_frame.columnconfigure(1, weight=1)
        center_frame.columnconfigure(3, weight=1)
        ttk.Label(center_frame, text="X0").grid(row=0, column=0, sticky="w")
        ttk.Entry(center_frame, textvariable=self.radius_center_x, width=9).grid(row=0, column=1, sticky="ew", padx=(4, 8))
        ttk.Label(center_frame, text="Y0").grid(row=0, column=2, sticky="w")
        ttk.Entry(center_frame, textvariable=self.radius_center_y, width=9).grid(row=0, column=3, sticky="ew", padx=(4, 0))
        ttk.Label(panel, text="Sample rows for scatter").grid(row=17, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.sample_rows, width=12).grid(row=18, column=0, sticky="ew", pady=(2, 8))
        ttk.Label(panel, text="Data mode").grid(row=19, column=0, sticky="w")
        ttk.Combobox(panel, textvariable=self.data_mode, values=["Sample", "All rows"], state="readonly").grid(row=20, column=0, sticky="ew", pady=(2, 8))
        ttk.Label(panel, text="Series display mode").grid(row=21, column=0, sticky="w")
        ttk.Combobox(
            panel,
            textvariable=self.series_mode,
            values=["Combine selected data", "Overlay selected series", "Separate panels"],
            state="readonly",
        ).grid(row=22, column=0, sticky="ew", pady=(2, 8))
        ttk.Label(panel, text="Max series to draw").grid(row=23, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.max_layers, width=12).grid(row=24, column=0, sticky="ew", pady=(2, 8))

        range_frame = ttk.LabelFrame(panel, text="Axis range after plot", padding=6)
        range_frame.grid(row=25, column=0, sticky="ew", pady=(2, 8))
        range_frame.columnconfigure(1, weight=1)
        range_frame.columnconfigure(3, weight=1)
        ttk.Label(range_frame, text="X min").grid(row=0, column=0, sticky="w")
        ttk.Entry(range_frame, textvariable=self.x_min, width=9).grid(row=0, column=1, sticky="ew", padx=(3, 6))
        ttk.Label(range_frame, text="X max").grid(row=0, column=2, sticky="w")
        ttk.Entry(range_frame, textvariable=self.x_max, width=9).grid(row=0, column=3, sticky="ew", padx=(3, 0))
        ttk.Label(range_frame, text="Y min").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(range_frame, textvariable=self.y_min, width=9).grid(row=1, column=1, sticky="ew", padx=(3, 6), pady=(4, 0))
        ttk.Label(range_frame, text="Y max").grid(row=1, column=2, sticky="w", pady=(4, 0))
        ttk.Entry(range_frame, textvariable=self.y_max, width=9).grid(row=1, column=3, sticky="ew", padx=(3, 0), pady=(4, 0))
        ttk.Button(range_frame, text="Apply Range", command=self.apply_axis_range).grid(row=2, column=0, columnspan=4, sticky="ew", pady=(6, 0))

        style_frame = ttk.LabelFrame(panel, text="Plot style", padding=6)
        style_frame.grid(row=26, column=0, sticky="ew", pady=(2, 8))
        style_frame.columnconfigure(1, weight=1)
        self._style_entry(style_frame, "Line color", self.line_color, 0, group="line")
        self._style_entry(style_frame, "Series colors", self.series_colors, 1, group="line")
        self._style_entry(style_frame, "Band color", self.band_color, 2, group="band")
        self._style_entry(style_frame, "Min/max color", self.outlier_color, 3, group="outlier")
        self._style_entry(style_frame, "Scatter color", self.scatter_color, 4, group="scatter")
        self._style_entry(style_frame, "Line width", self.line_width, 5, group="line")
        self._style_entry(style_frame, "Scatter size", self.scatter_size, 6, group="scatter")
        self._style_entry(style_frame, "Scatter alpha", self.scatter_alpha, 7, group="scatter")
        self._style_entry(style_frame, "X label", self.x_label, 8, group="axis")
        self._style_entry(style_frame, "Y label", self.y_label, 9, group="axis")
        self._style_entry(style_frame, "Axis label size", self.axis_label_size, 10, group="axis")
        axis_weight_label = ttk.Label(style_frame, text="Axis label weight")
        axis_weight_label.grid(row=11, column=0, sticky="w", pady=(0, 3))
        axis_weight_combo = ttk.Combobox(style_frame, textvariable=self.axis_label_weight, values=["normal", "bold"], state="readonly", width=14)
        axis_weight_combo.grid(row=11, column=1, sticky="ew", padx=(6, 0), pady=(0, 3))
        self._remember_style_controls("axis", axis_weight_label, axis_weight_combo)
        radius_line_only = ttk.Checkbutton(style_frame, text="Radius chart line only", variable=self.radius_line_only, command=self.update_control_visibility)
        radius_line_only.grid(row=12, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self._remember_style_controls("radius_only", radius_line_only)
        scatter_by_image = ttk.Checkbutton(style_frame, text="Scatter mean by ImageID", variable=self.scatter_by_image)
        scatter_by_image.grid(row=13, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self._remember_style_controls("scatter", scatter_by_image)
        apply_style = ttk.Button(style_frame, text="Apply Style", command=self.apply_plot_style)
        apply_style.grid(row=14, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._remember_style_controls("axis", apply_style)

        sep = ttk.Separator(panel)
        sep.grid(row=27, column=0, sticky="ew", pady=8)
        filter_frame = ttk.LabelFrame(panel, text="Visible layer values", padding=6)
        filter_frame.grid(row=28, column=0, sticky="ew", pady=(2, 8))
        filter_frame.columnconfigure(1, weight=1)
        self._style_entry(filter_frame, "LayerType", self.filter_layer_type, 0)
        self._style_entry(filter_frame, "LayerNO", self.filter_layer_no, 1)
        self._style_entry(filter_frame, "Moduleindex", self.filter_moduleindex, 2)
        ttk.Button(filter_frame, text="Choose visible values...", command=self.choose_layer_values).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(filter_frame, text="Show available values", command=self.load_filter_values).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(filter_frame, text="Clear visible filters", command=self.clear_visible_filters).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Label(filter_frame, text="Blank means all. Comma-separated values are also supported.", wraplength=300).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        ttk.Label(panel, text="Line A filters").grid(row=29, column=0, sticky="w")
        self._small_entry(panel, "LayerType", self.a_layer_type, 30)
        self._small_entry(panel, "LayerNO", self.a_layer_no, 32)
        self._small_entry(panel, "Moduleindex", self.a_moduleindex, 34)
        ttk.Button(
            panel,
            text="Choose Line A values...",
            command=lambda: self.choose_layer_values(
                {
                    "LayerType": self.a_layer_type,
                    "LayerNO": self.a_layer_no,
                    "Moduleindex": self.a_moduleindex,
                },
                "Choose Line A values",
            ),
        ).grid(row=36, column=0, sticky="ew", pady=(2, 4))
        ttk.Label(panel, text="Line B filters").grid(row=37, column=0, sticky="w", pady=(8, 0))
        self._small_entry(panel, "LayerType", self.b_layer_type, 38)
        self._small_entry(panel, "LayerNO", self.b_layer_no, 40)
        self._small_entry(panel, "Moduleindex", self.b_moduleindex, 42)
        ttk.Button(
            panel,
            text="Choose Line B values...",
            command=lambda: self.choose_layer_values(
                {
                    "LayerType": self.b_layer_type,
                    "LayerNO": self.b_layer_no,
                    "Moduleindex": self.b_moduleindex,
                },
                "Choose Line B values",
            ),
        ).grid(row=44, column=0, sticky="ew", pady=(2, 4))
        ttk.Label(panel, text="Line C filters").grid(row=45, column=0, sticky="w", pady=(8, 0))
        self._small_entry(panel, "LayerType", self.c_layer_type, 46)
        self._small_entry(panel, "LayerNO", self.c_layer_no, 48)
        self._small_entry(panel, "Moduleindex", self.c_moduleindex, 50)
        ttk.Button(
            panel,
            text="Choose Line C values...",
            command=lambda: self.choose_layer_values(
                {
                    "LayerType": self.c_layer_type,
                    "LayerNO": self.c_layer_no,
                    "Moduleindex": self.c_moduleindex,
                },
                "Choose Line C values",
            ),
        ).grid(row=52, column=0, sticky="ew", pady=(2, 4))
        ttk.Button(panel, text="Clear Line A/B/C filters", command=self.clear_line_filters).grid(row=53, column=0, sticky="ew", pady=(2, 4))
        ttk.Label(panel, text="Operation").grid(row=54, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(panel, textvariable=self.operation, values=["subtract", "add", "ratio"], state="readonly").grid(row=55, column=0, sticky="ew")

        ttk.Button(panel, text="Plot", command=self.start_plot).grid(row=56, column=0, sticky="ew", pady=(12, 4))
        ttk.Button(panel, text="Save PNG", command=self.save_current_png).grid(row=57, column=0, sticky="ew")
        ttk.Label(panel, textvariable=self.status, wraplength=310).grid(row=58, column=0, sticky="ew", pady=(12, 0))

        chart_frame = ttk.Frame(self, padding=(0, 10, 10, 10))
        chart_frame.grid(row=0, column=1, sticky="nsew")
        chart_frame.columnconfigure(0, weight=1)
        chart_frame.rowconfigure(0, weight=1)

        self.fig, self.ax = plt.subplots(figsize=(8, 5), dpi=110)
        self.ax.set_title("Ebeam Data Visualizer")
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.grid(True, color="#D7DEE8", linewidth=0.7, alpha=0.8)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    def _combo(self, parent: ttk.Frame, label: str, var: tk.StringVar, row: int) -> ttk.Combobox:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        combo = ttk.Combobox(parent, textvariable=var, values=[], width=38)
        combo.grid(row=row + 1, column=0, sticky="ew", pady=(2, 8))
        return combo

    def _small_entry(self, parent: ttk.Frame, label: str, var: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        ttk.Entry(parent, textvariable=var).grid(row=row + 1, column=0, sticky="ew", pady=(2, 4))

    def _style_entry(self, parent, label, var, row: int, group: str = "") -> None:
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky="w", pady=(0, 3))
        entry_widget = ttk.Entry(parent, textvariable=var, width=16)
        entry_widget.grid(row=row, column=1, sticky="ew", padx=(6, 0), pady=(0, 3))
        if group:
            self._remember_style_controls(group, label_widget, entry_widget)

    def _remember_style_controls(self, group: str, *widgets) -> None:
        self.style_controls.setdefault(group, []).extend(widgets)
        for widget in widgets:
            info = widget.grid_info()
            if info:
                self.style_grid_options[widget] = dict(info)

    def browse_file(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[
                ("Data files", "*.csv *.txt *.parquet *.pq *.xlsx *.xlsm *.xls"),
                ("All files", "*.*"),
            ]
        )
        if path:
            self.input_path.set(path)
            self.load_columns()

    def load_columns(self) -> None:
        path = self.input_path.get().strip()
        if not path:
            return
        try:
            self.columns = list_columns(path)
            self.plot_columns = list_plot_columns(path)
            for combo in [self.x_combo, self.y_combo, self.value_combo]:
                combo["values"] = self.plot_columns
            self._pick_default_columns()
            self.status.set(f"Loaded {len(self.columns)} physical columns. Radius is available when WaferPosX and WaferPosY exist.")
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc))

    def _pick_default_columns(self) -> None:
        if RADIUS_COLUMN in self.plot_columns:
            self.x_axis.set(RADIUS_COLUMN)
        elif "WaferPosX" in self.plot_columns:
            self.x_axis.set("WaferPosX")
        if "CD" in self.plot_columns:
            self.y_axis.set("CD")
            self.value_col.set("CD")
        elif self.plot_columns:
            self.y_axis.set(self.plot_columns[0])
            self.value_col.set(self.plot_columns[0])

    def on_chart_change(self, _event=None) -> None:
        chart = self.chart_type.get()
        if chart == "FIN center loading":
            self.x_axis.set(RADIUS_COLUMN)
            self.status.set("FIN center loading uses ((Line A + Line C) / 2) - Line B, grouped by ImageID.")
        elif chart in {"CD by wafer radius", "Radius sigma by wafer radius", "Line CD loading"}:
            self.x_axis.set(RADIUS_COLUMN)
            self.status.set("This chart uses computed Radius = sqrt(WaferPosX^2 + WaferPosY^2) as X axis.")
        elif chart == "Layer CD distribution":
            self.status.set("This chart groups by available LayerType, LayerNO, Moduleindex columns. Missing layer columns are skipped.")
        elif chart == "Wafer value heatmap":
            self.status.set("Wafer value heatmap uses WaferPosX/Y and the selected Value column.")
        elif chart == "Wafer loading heatmap":
            self.status.set("Wafer loading heatmap averages each ImageID line, compares Line A/B, then maps loading on wafer X/Y.")
        else:
            self.status.set("Custom scatter uses selected X/Y columns. Radius is a computed virtual X/Y option when available.")
        self.update_control_visibility()

    def _install_auto_style_traces(self) -> None:
        style_vars = [
            self.line_color,
            self.series_colors,
            self.band_color,
            self.outlier_color,
            self.scatter_color,
            self.line_width,
            self.scatter_size,
            self.scatter_alpha,
            self.radius_line_only,
            self.x_label,
            self.y_label,
            self.axis_label_size,
            self.axis_label_weight,
            self.x_min,
            self.x_max,
            self.y_min,
            self.y_max,
            self.color_min,
            self.color_max,
            self.colormap,
        ]
        for var in style_vars:
            var.trace_add("write", self._schedule_style_redraw)

    def _schedule_style_redraw(self, *_args) -> None:
        if self.last_plot_kind is None or self.last_plot_payload is None:
            return
        if self._style_redraw_job is not None:
            self.after_cancel(self._style_redraw_job)
        self._style_redraw_job = self.after(450, self._auto_apply_plot_style)

    def _auto_apply_plot_style(self) -> None:
        self._style_redraw_job = None
        if self.last_plot_kind is None or self.last_plot_payload is None:
            return
        try:
            self._draw(self.last_plot_kind, self.last_plot_payload)
            self.status.set("Plot style auto-applied.")
        except Exception as exc:
            self.status.set("Style not applied: {}".format(exc))

    def update_control_visibility(self) -> None:
        if self.control_panel is None:
            return
        for child in self.control_panel.winfo_children():
            info = child.grid_info()
            if info:
                self.panel_grid_options[child] = dict(info)
        chart = self.chart_type.get()
        always = set(range(0, 6)) | {56, 57, 58}
        rows = set(always)
        if chart == "CD by wafer radius":
            rows |= {10, 11, 12, 13, 16, 21, 22, 23, 24, 25, 26, 27, 28}
            style_groups = {"line", "axis", "radius_only"}
            if not self.radius_line_only.get():
                style_groups |= {"band", "outlier", "scatter"}
        elif chart == "Radius sigma by wafer radius":
            rows |= {10, 11, 12, 13, 14, 16, 21, 22, 23, 24, 25, 26, 27, 28}
            style_groups = {"line", "axis"}
        elif chart == "Layer CD distribution":
            rows |= {10, 11, 21, 22, 23, 24, 25, 26, 27, 28}
            style_groups = {"line", "axis"}
        elif chart == "Line CD loading":
            rows |= {10, 11, 12, 13, 16} | set(range(21, 28)) | set(range(29, 45)) | {53, 54, 55}
            style_groups = {"line", "band", "outlier", "scatter", "axis"}
        elif chart == "FIN center loading":
            rows |= {10, 11, 12, 13, 16} | set(range(21, 28)) | set(range(29, 54))
            style_groups = {"line", "band", "outlier", "scatter", "axis"}
        elif chart == "Wafer value heatmap":
            rows |= {10, 11, 15, 16, 25, 26, 27, 28}
            style_groups = {"axis"}
        elif chart == "Wafer loading heatmap":
            rows |= {10, 11, 15, 16, 25, 26, 27} | set(range(29, 45)) | {53, 54, 55}
            style_groups = {"axis"}
        else:
            rows |= set(range(6, 10)) | set(range(16, 29))
            style_groups = {"scatter", "axis"}

        for child in self.control_panel.winfo_children():
            info = child.grid_info()
            stored = self.panel_grid_options.get(child)
            if not info and not stored:
                continue
            row_source = info if info else stored
            row = int(row_source.get("row", -1))
            if row in rows:
                child.grid(**self.panel_grid_options.get(child, {}))
            else:
                child.grid_remove()
        self._update_style_visibility(style_groups)

    def _update_style_visibility(self, visible_groups) -> None:
        for group, widgets in self.style_controls.items():
            visible = group in visible_groups
            for widget in widgets:
                if visible:
                    widget.grid(**self.style_grid_options.get(widget, {}))
                else:
                    widget.grid_remove()

    def normal_filters(self):
        filters = {}
        if self.filter_layer_type.get().strip():
            filters["LayerType"] = self.filter_layer_type.get().strip()
        if self.filter_layer_no.get().strip():
            filters["LayerNO"] = self.filter_layer_no.get().strip()
        if self.filter_moduleindex.get().strip():
            filters["Moduleindex"] = self.filter_moduleindex.get().strip()
        return filters

    def clear_visible_filters(self) -> None:
        self.filter_layer_type.set("")
        self.filter_layer_no.set("")
        self.filter_moduleindex.set("")
        self.status.set("Visible layer filters cleared.")

    def clear_line_filters(self) -> None:
        for var in [
            self.a_layer_type,
            self.a_layer_no,
            self.a_moduleindex,
            self.b_layer_type,
            self.b_layer_no,
            self.b_moduleindex,
            self.c_layer_type,
            self.c_layer_no,
            self.c_moduleindex,
        ]:
            var.set("")
        self.status.set("Line A/B/C filters cleared.")

    def radius_center(self):
        x_text = self.radius_center_x.get().strip()
        y_text = self.radius_center_y.get().strip()
        return (float(x_text) if x_text else 0.0, float(y_text) if y_text else 0.0)

    def load_filter_values(self) -> None:
        path = self.input_path.get().strip()
        if not path:
            messagebox.showwarning("Missing file", "Please select a data file first.")
            return
        parts = []
        for col in ["LayerType", "LayerNO", "Moduleindex"]:
            if col in self.columns:
                vals = distinct_values(path, col, limit=30)
                parts.append("{}: {}".format(col, ", ".join(vals[:30])))
        if not parts:
            self.status.set("No LayerType, LayerNO, or Moduleindex columns found.")
        else:
            messagebox.showinfo("Filter values", "\n\n".join(parts))

    def choose_layer_values(self, variables=None, title: str = "Choose visible layer values") -> None:
        path = self.input_path.get().strip()
        if not path:
            messagebox.showwarning("Missing file", "Please select a data file first.")
            return

        available = {}
        try:
            for col in ["LayerType", "LayerNO", "Moduleindex"]:
                if col in self.columns:
                    available[col] = distinct_values(path, col, limit=500)
        except Exception as exc:
            messagebox.showerror("Value lookup failed", str(exc))
            return

        if not available:
            messagebox.showinfo("Layer selection", "No LayerType, LayerNO, or Moduleindex columns found.")
            return

        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry("780x440")
        dialog.transient(self)
        dialog.grab_set()
        for col_index in range(len(available)):
            dialog.columnconfigure(col_index, weight=1)
        dialog.rowconfigure(1, weight=1)

        if variables is None:
            variables = {
                "LayerType": self.filter_layer_type,
                "LayerNO": self.filter_layer_no,
                "Moduleindex": self.filter_moduleindex,
            }
        listboxes = {}

        for col_index, (col, values) in enumerate(available.items()):
            ttk.Label(dialog, text=col).grid(row=0, column=col_index, sticky="w", padx=8, pady=(8, 3))
            box = tk.Listbox(dialog, selectmode=tk.EXTENDED, exportselection=False)
            box.grid(row=1, column=col_index, sticky="nsew", padx=8)
            for value in values:
                box.insert(tk.END, value)
            current = set(split_filter_values(variables[col].get()))
            if current:
                for index, value in enumerate(values):
                    if value in current:
                        box.selection_set(index)
            else:
                box.selection_set(0, tk.END)
            listboxes[col] = (box, values)

        ttk.Label(
            dialog,
            text="Use Ctrl/Shift for multi-select. Selecting every value means no filter for that field.",
        ).grid(row=2, column=0, columnspan=len(available), sticky="w", padx=8, pady=(8, 4))

        button_row = ttk.Frame(dialog)
        button_row.grid(row=3, column=0, columnspan=len(available), sticky="ew", padx=8, pady=(4, 8))
        button_row.columnconfigure(0, weight=1)

        def select_all() -> None:
            for box, _values in listboxes.values():
                box.selection_set(0, tk.END)

        def clear_selection() -> None:
            for box, _values in listboxes.values():
                box.selection_clear(0, tk.END)

        def apply_selection() -> None:
            for col, (box, values) in listboxes.items():
                selected = [values[index] for index in box.curselection()]
                if not selected:
                    messagebox.showwarning("No values selected", "{} needs at least one visible value.".format(col), parent=dialog)
                    return
                variables[col].set("" if len(selected) == len(values) else ",".join(selected))
            dialog.destroy()
            self.status.set("Visible layer filters updated. Choose a series display mode, then plot.")

        ttk.Button(button_row, text="Select all", command=select_all).grid(row=0, column=0, sticky="w")
        ttk.Button(button_row, text="Clear selection", command=clear_selection).grid(row=0, column=1, padx=6)
        ttk.Button(button_row, text="Cancel", command=dialog.destroy).grid(row=0, column=2, padx=6)
        ttk.Button(button_row, text="Apply", command=apply_selection).grid(row=0, column=3)

    def start_plot(self) -> None:
        path = self.input_path.get().strip()
        if not path:
            messagebox.showwarning("Missing file", "Please select a data file first.")
            return
        self.status.set("Querying data and rendering plot...")
        thread = threading.Thread(target=self._plot_worker, args=(path,), daemon=True)
        thread.start()

    def _plot_worker(self, path: str) -> None:
        try:
            chart = self.chart_type.get()
            filters = self.normal_filters()
            group_series = self.series_mode.get() != "Combine selected data"
            radius_center = self.radius_center()
            if chart == "CD by wafer radius":
                df = query_radius_aggregate(
                    path,
                    self.value_col.get(),
                    self.radius_bin.get(),
                    filters=filters,
                    group_series=group_series,
                    radius_center=radius_center,
                )
                self._raise_if_empty(df, chart, filters)
                self.result_queue.put(("radius", df))
            elif chart == "Radius sigma by wafer radius":
                df = query_radius_sigma(
                    path,
                    self.value_col.get(),
                    self.radius_bin.get(),
                    filters=filters,
                    group_series=group_series,
                    sigma_mode=self.sigma_mode.get(),
                    radius_center=radius_center,
                )
                self._raise_if_empty(df, chart, filters)
                self.result_queue.put(("radius_sigma", df))
            elif chart == "Layer CD distribution":
                hist, stats = query_layer_histogram(
                    path,
                    self.value_col.get(),
                    max_layers=self.max_layers.get(),
                    filters=filters,
                    group_series=group_series,
                )
                self._raise_if_empty((hist, stats), chart, filters)
                self.result_queue.put(("layer_dist", (hist, stats)))
            elif chart == "Line CD loading":
                line_filters = {
                    "Line A LayerType": self.a_layer_type.get(),
                    "Line A LayerNO": self.a_layer_no.get(),
                    "Line A Moduleindex": self.a_moduleindex.get(),
                    "Line B LayerType": self.b_layer_type.get(),
                    "Line B LayerNO": self.b_layer_no.get(),
                    "Line B Moduleindex": self.b_moduleindex.get(),
                }
                df = query_line_loading(
                    path,
                    {"LayerType": self.a_layer_type.get(), "LayerNO": self.a_layer_no.get(), "Moduleindex": self.a_moduleindex.get()},
                    {"LayerType": self.b_layer_type.get(), "LayerNO": self.b_layer_no.get(), "Moduleindex": self.b_moduleindex.get()},
                    self.operation.get(),
                    self.radius_bin.get(),
                    self.value_col.get(),
                    group_series=group_series,
                    radius_center=radius_center,
                )
                self._raise_if_empty(df, chart, line_filters)
                self.result_queue.put(("line_loading", df))
            elif chart == "FIN center loading":
                line_filters = {
                    "Line A LayerType": self.a_layer_type.get(),
                    "Line A LayerNO": self.a_layer_no.get(),
                    "Line A Moduleindex": self.a_moduleindex.get(),
                    "Line B LayerType": self.b_layer_type.get(),
                    "Line B LayerNO": self.b_layer_no.get(),
                    "Line B Moduleindex": self.b_moduleindex.get(),
                    "Line C LayerType": self.c_layer_type.get(),
                    "Line C LayerNO": self.c_layer_no.get(),
                    "Line C Moduleindex": self.c_moduleindex.get(),
                }
                df = query_fin_center_loading(
                    path,
                    {"LayerType": self.a_layer_type.get(), "LayerNO": self.a_layer_no.get(), "Moduleindex": self.a_moduleindex.get()},
                    {"LayerType": self.b_layer_type.get(), "LayerNO": self.b_layer_no.get(), "Moduleindex": self.b_moduleindex.get()},
                    {"LayerType": self.c_layer_type.get(), "LayerNO": self.c_layer_no.get(), "Moduleindex": self.c_moduleindex.get()},
                    self.radius_bin.get(),
                    self.value_col.get(),
                    group_series=group_series,
                    radius_center=radius_center,
                )
                self._raise_if_empty(df, chart, line_filters)
                self.result_queue.put(("fin_center_loading", df))
            elif chart == "Wafer value heatmap":
                df = query_wafer_value_heatmap(
                    path,
                    self.value_col.get(),
                    self.heatmap_bin.get(),
                    self.wafer_diameter.get(),
                    filters=filters,
                    radius_center=radius_center,
                )
                self._raise_if_empty(df, chart, filters)
                self.result_queue.put(("wafer_value_heatmap", df))
            elif chart == "Wafer loading heatmap":
                line_filters = {
                    "Line A LayerType": self.a_layer_type.get(),
                    "Line A LayerNO": self.a_layer_no.get(),
                    "Line A Moduleindex": self.a_moduleindex.get(),
                    "Line B LayerType": self.b_layer_type.get(),
                    "Line B LayerNO": self.b_layer_no.get(),
                    "Line B Moduleindex": self.b_moduleindex.get(),
                }
                df = query_wafer_loading_heatmap(
                    path,
                    {"LayerType": self.a_layer_type.get(), "LayerNO": self.a_layer_no.get(), "Moduleindex": self.a_moduleindex.get()},
                    {"LayerType": self.b_layer_type.get(), "LayerNO": self.b_layer_no.get(), "Moduleindex": self.b_moduleindex.get()},
                    self.operation.get(),
                    self.value_col.get(),
                    self.heatmap_bin.get(),
                    self.wafer_diameter.get(),
                    radius_center=radius_center,
                )
                self._raise_if_empty(df, chart, line_filters)
                self.result_queue.put(("wafer_loading_heatmap", df))
            else:
                use_sample = self.data_mode.get() == "Sample"
                df = query_xy(
                    path,
                    self.x_axis.get(),
                    self.y_axis.get(),
                    self.sample_rows.get(),
                    use_sample=use_sample,
                    filters=filters,
                    group_series=group_series,
                    aggregate_by_image=self.scatter_by_image.get(),
                    radius_center=radius_center,
                )
                self._raise_if_empty(df, chart, filters)
                self.result_queue.put(("scatter", df))
        except Exception as exc:
            self.result_queue.put(("error", exc))

    def _raise_if_empty(self, payload, chart: str, filters) -> None:
        empty = False
        if isinstance(payload, tuple):
            empty = any(getattr(part, "empty", False) for part in payload)
        else:
            empty = getattr(payload, "empty", False)
        if not empty:
            return
        active = []
        for key, value in filters.items():
            text = str(value).strip()
            if text:
                active.append("{}={}".format(key, text))
        filter_text = ", ".join(active) if active else "no active filters"
        raise ValueError(
            "No valid data found for {}. Current filters: {}. Clear filters or choose values that exist together in the file.".format(
                chart,
                filter_text,
            )
        )

    def _poll_results(self) -> None:
        try:
            while True:
                kind, payload = self.result_queue.get_nowait()
                if kind == "error":
                    self.status.set("Plot failed.")
                    messagebox.showerror("Plot failed", str(payload))
                else:
                    try:
                        self._draw(kind, payload)
                    except Exception as exc:
                        self.status.set("Draw failed.")
                        messagebox.showerror("Draw failed", str(exc))
        except queue.Empty:
            pass
        self.after(200, self._poll_results)

    def _draw(self, kind: str, payload: object) -> None:
        self.last_plot_kind = kind
        self.last_plot_payload = payload
        self.fig.clear()
        line_color = self.line_color.get().strip() or "#1F5A8A"
        band_color = self.band_color.get().strip() or "#8FB6D9"
        outlier_color = self.outlier_color.get().strip() or "#B05A7A"
        scatter_color = self.scatter_color.get().strip() or "#1F5A8A"
        line_width = max(float(self.line_width.get()), 0.1)
        scatter_size = max(float(self.scatter_size.get()), 0.1)
        scatter_alpha = min(max(float(self.scatter_alpha.get()), 0.0), 1.0)
        labels = self._payload_series_labels(kind, payload)
        series_color_map = self._series_color_map(labels)
        axes_by_label, axes = self._create_series_axes(labels)
        overlay = self.series_mode.get() == "Overlay selected series"
        separate = self.series_mode.get() == "Separate panels"

        if kind == "radius":
            df = payload
            for index, label in enumerate(labels):
                ax = axes_by_label[label]
                part = df[df["series_label"] == label].sort_values("radius_bin")
                color, linestyle = self._series_style(index, line_color, label, series_color_map)
                fill_color = color if len(labels) > 1 else band_color
                ax.plot(part["radius_bin"], part["value_mean"], color=color, linestyle=linestyle, linewidth=line_width, label=label)
                if not self.radius_line_only.get():
                    ax.fill_between(
                        part["radius_bin"],
                        part["value_mean"] - part["value_std"].fillna(0),
                        part["value_mean"] + part["value_std"].fillna(0),
                        color=fill_color,
                        alpha=0.14 if overlay else 0.26,
                    )
                    ax.scatter(part["radius_bin"], part["value_min"], s=scatter_size * 2.5, alpha=0.42, color=outlier_color)
                    ax.scatter(part["radius_bin"], part["value_max"], s=scatter_size * 2.5, alpha=0.42, color=outlier_color)
                self._configure_axis(
                    ax,
                    label if separate else "CD by Wafer Radius",
                    "Radius = sqrt(WaferPosX^2 + WaferPosY^2)",
                    self.value_col.get(),
                )
        elif kind == "radius_sigma":
            df = payload
            for index, label in enumerate(labels):
                ax = axes_by_label[label]
                part = df[df["series_label"] == label].sort_values("radius_bin")
                color, linestyle = self._series_style(index, line_color, label, series_color_map)
                ax.plot(part["radius_bin"], part["sigma"], color=color, linestyle=linestyle, linewidth=line_width, marker="o", markersize=max(scatter_size * 0.65, 1.0), label=label)
                self._configure_axis(
                    ax,
                    label if separate else "Radius Sigma by Wafer Radius",
                    "Radius = sqrt(WaferPosX^2 + WaferPosY^2)",
                    "{} sigma".format(self.value_col.get()),
                )
        elif kind == "layer_dist":
            hist, stats = payload
            for index, label in enumerate(labels):
                ax = axes_by_label[label]
                part = hist[hist["layer_label"] == label]
                if part.empty:
                    continue
                y = part["n"] / part["n"].sum()
                color, linestyle = self._series_style(index, line_color, label, series_color_map)
                stats_row = stats[stats["layer_label"].astype(str) == label]
                legend_label = self._distribution_legend_label(label, stats_row.iloc[0] if not stats_row.empty else None, int(part["n"].sum()))
                ax.plot(part["bin_center"], y, linewidth=line_width, linestyle=linestyle, color=color, label=legend_label)
                self._configure_axis(
                    ax,
                    label if separate else "CD Distribution by Layer",
                    self.value_col.get(),
                    "Share within layer bin",
                )
        elif kind in {"line_loading", "fin_center_loading"}:
            df = payload
            title = "Line CD Loading by Wafer Radius ({})".format(self.operation.get())
            if kind == "fin_center_loading":
                title = "FIN Center Loading by Wafer Radius ((A + C) / 2 - B)"
            for index, label in enumerate(labels):
                ax = axes_by_label[label]
                part = df[df["series_label"] == label].sort_values("radius_bin")
                color, linestyle = self._series_style(index, line_color, label, series_color_map)
                fill_color = color if len(labels) > 1 else band_color
                ax.plot(
                    part["radius_bin"],
                    part["loading_mean"],
                    color=color,
                    linestyle=linestyle,
                    linewidth=line_width,
                    marker="o",
                    markersize=max(scatter_size * 0.75, 1.0),
                    label=label,
                )
                ax.fill_between(
                    part["radius_bin"],
                    part["loading_mean"] - part["loading_std"].fillna(0),
                    part["loading_mean"] + part["loading_std"].fillna(0),
                    color=fill_color,
                    alpha=0.14 if overlay else 0.26,
                )
                ax.scatter(part["radius_bin"], part["loading_min"], s=scatter_size * 2.5, alpha=0.42, color=outlier_color)
                ax.scatter(part["radius_bin"], part["loading_max"], s=scatter_size * 2.5, alpha=0.42, color=outlier_color)
                ax.axhline(0, color="#58606F", linewidth=1.0, linestyle="--")
                self._configure_axis(
                    ax,
                    label if separate else title,
                    "Radius = sqrt(WaferPosX^2 + WaferPosY^2)",
                    "{} loading".format(self.value_col.get()),
                )
        elif kind == "scatter":
            df = payload
            mode = "sampled" if self.data_mode.get() == "Sample" else "all-row"
            grain = "ImageID mean" if self.scatter_by_image.get() else "raw row"
            for index, label in enumerate(labels):
                ax = axes_by_label[label]
                part = df[df["layer_label"] == label]
                color, _linestyle = self._series_style(index, scatter_color, label, series_color_map)
                ax.scatter(part["x"], part["y"], s=scatter_size, alpha=scatter_alpha, color=color, linewidths=0, label=label)
                self._configure_axis(
                    ax,
                    label if separate else "{} vs {} {} {} scatter".format(self.y_axis.get(), self.x_axis.get(), grain, mode),
                    self.x_axis.get(),
                    self.y_axis.get(),
                )
        elif kind in {"wafer_value_heatmap", "wafer_loading_heatmap"}:
            df = payload
            ax = axes[0]
            title = "Wafer {} Heatmap".format(self.value_col.get()) if kind == "wafer_value_heatmap" else "Wafer Loading Heatmap ({})".format(self.operation.get())
            label = self.value_col.get() if kind == "wafer_value_heatmap" else "{} loading".format(self.value_col.get())
            self._draw_wafer_heatmap(ax, df, title, label)

        for ax in axes:
            if overlay and len(labels) > 1:
                ax.legend(fontsize=8)
            if kind in {"wafer_value_heatmap", "wafer_loading_heatmap"}:
                ax.grid(False)
            else:
                ax.grid(True, color="#D7DEE8", linewidth=0.7, alpha=0.8)
            self._apply_axis_label_style(ax)
            self._apply_axis_range_to_ax(ax)

        if separate and len(labels) > 1:
            self.fig.suptitle(self._chart_heading(kind), fontsize=12, fontweight="bold")
            self.fig.tight_layout(rect=(0, 0, 1, 0.96))
        else:
            self.fig.tight_layout()
        self.canvas.draw()
        self.status.set("Plot complete. Showing {} series in {} mode.".format(len(labels), self.series_mode.get()))

    def apply_plot_style(self) -> None:
        if self.last_plot_kind is None or self.last_plot_payload is None:
            self.status.set("No existing plot to restyle. Click Plot first.")
            return
        try:
            self._draw(self.last_plot_kind, self.last_plot_payload)
            self.status.set("Plot style applied.")
        except Exception as exc:
            messagebox.showerror("Apply style failed", str(exc))

    def _payload_series_labels(self, kind: str, payload: object):
        if kind == "layer_dist":
            _hist, stats = payload
            labels = stats["layer_label"].astype(str).tolist() if not stats.empty else []
        elif kind == "scatter":
            df = payload
            labels = df["layer_label"].astype(str).value_counts().index.tolist() if not df.empty else []
        elif kind in {"wafer_value_heatmap", "wafer_loading_heatmap"}:
            df = payload
            labels = ["Wafer map"] if not df.empty else []
        else:
            df = payload
            if df.empty:
                labels = []
            elif "n" in df.columns:
                labels = df.groupby("series_label")["n"].sum().sort_values(ascending=False).index.astype(str).tolist()
            else:
                labels = df["series_label"].astype(str).drop_duplicates().tolist()
        if not labels:
            raise ValueError("No valid data found for the selected filters.")
        max_series = max(int(self.max_layers.get()), 1)
        return labels[:max_series]

    def _create_series_axes(self, labels):
        separate = self.series_mode.get() == "Separate panels" and len(labels) > 1
        if not separate:
            ax = self.fig.add_subplot(111)
            self.ax = ax
            return {label: ax for label in labels}, [ax]

        columns = 2 if len(labels) > 1 else 1
        rows = int(math.ceil(len(labels) / float(columns)))
        axes_array = self.fig.subplots(rows, columns, squeeze=False)
        flat_axes = list(axes_array.flat)
        visible_axes = flat_axes[: len(labels)]
        for unused in flat_axes[len(labels) :]:
            unused.set_visible(False)
        self.ax = visible_axes[0]
        return {label: visible_axes[index] for index, label in enumerate(labels)}, visible_axes

    def _series_color_map(self, labels):
        text = self.series_colors.get().strip()
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

    def _series_style(self, index: int, first_color: str, label: str = "", color_map=None):
        if color_map and label in color_map:
            color = color_map[label]
        elif index == 0:
            color = first_color
        else:
            color = SERIES_COLORS[index % len(SERIES_COLORS)]
        linestyle = SERIES_LINESTYLES[(index // len(SERIES_COLORS)) % len(SERIES_LINESTYLES)]
        return color, linestyle

    def _distribution_legend_label(self, label: str, stats_row, total: int) -> str:
        if stats_row is None:
            return "{} (n={})".format(label, total)
        mean = stats_row.get("mean")
        std = stats_row.get("std")
        try:
            return "{} (μ={:.4g}, σ={:.4g}, n={})".format(label, float(mean), float(std), total)
        except (TypeError, ValueError):
            return "{} (n={})".format(label, total)

    def _configure_axis(self, ax, title: str, x_default: str, y_default: str) -> None:
        ax.set_title(title, fontsize=9 if self.series_mode.get() == "Separate panels" else 12)
        ax.set_xlabel(self._axis_label("x", x_default))
        ax.set_ylabel(self._axis_label("y", y_default))

    def _chart_heading(self, kind: str) -> str:
        headings = {
            "radius": "CD by Wafer Radius",
            "radius_sigma": "Radius Sigma by Wafer Radius",
            "layer_dist": "CD Distribution by Layer",
            "line_loading": "Line CD Loading by Wafer Radius",
            "fin_center_loading": "FIN Center Loading by Wafer Radius",
            "wafer_value_heatmap": "Wafer Value Heatmap",
            "wafer_loading_heatmap": "Wafer Loading Heatmap",
            "scatter": "{} vs {}".format(self.y_axis.get(), self.x_axis.get()),
        }
        return headings.get(kind, "Ebeam Data Visualizer")

    def _color_limits(self):
        vmin = float(self.color_min.get()) if self.color_min.get().strip() else None
        vmax = float(self.color_max.get()) if self.color_max.get().strip() else None
        return vmin, vmax

    def _draw_wafer_heatmap(self, ax, df, title: str, colorbar_label: str) -> None:
        half = float(self.wafer_diameter.get()) / 2.0
        bin_size = float(self.heatmap_bin.get())
        edges = np.arange(-half, half + bin_size, bin_size)
        x_centers = edges[:-1] + bin_size / 2.0
        y_centers = edges[:-1] + bin_size / 2.0
        pivot = df.pivot_table(index="y_bin", columns="x_bin", values="value_mean", aggfunc="mean")
        pivot = pivot.reindex(index=y_centers, columns=x_centers)
        z = pivot.to_numpy()
        mask_x, mask_y = np.meshgrid(x_centers, y_centers)
        z = np.where(np.sqrt(mask_x ** 2 + mask_y ** 2) <= half, z, np.nan)
        vmin, vmax = self._color_limits()
        cmap = plt.get_cmap(self.colormap.get()).copy()
        cmap.set_bad((1, 1, 1, 0))
        mesh = ax.imshow(
            z,
            extent=(-half, half, -half, half),
            origin="lower",
            cmap=cmap,
            interpolation="bilinear",
            vmin=vmin,
            vmax=vmax,
        )
        wafer = plt.Circle((0, 0), half, edgecolor="#2E3440", facecolor="none", linewidth=1.2)
        ax.add_patch(wafer)
        ax.axhline(0, color="#58606F", linewidth=0.6, alpha=0.6)
        ax.axvline(0, color="#58606F", linewidth=0.6, alpha=0.6)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(-half, half)
        ax.set_ylim(-half, half)
        self._configure_axis(ax, title, "WaferPosX", "WaferPosY")
        cbar = self.fig.colorbar(mesh, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label(colorbar_label)

    def _axis_label(self, axis: str, default: str) -> str:
        custom = self.x_label.get().strip() if axis == "x" else self.y_label.get().strip()
        return custom or default

    def _apply_axis_label_style(self, ax) -> None:
        size = max(float(self.axis_label_size.get()), 1.0)
        weight = self.axis_label_weight.get().strip() or "normal"
        ax.xaxis.label.set_size(size)
        ax.yaxis.label.set_size(size)
        ax.xaxis.label.set_weight(weight)
        ax.yaxis.label.set_weight(weight)

    def _apply_axis_range_to_ax(self, ax) -> None:
        try:
            xmin = float(self.x_min.get()) if self.x_min.get().strip() else None
            xmax = float(self.x_max.get()) if self.x_max.get().strip() else None
            ymin = float(self.y_min.get()) if self.y_min.get().strip() else None
            ymax = float(self.y_max.get()) if self.y_max.get().strip() else None
            if xmin is not None or xmax is not None:
                current = ax.get_xlim()
                ax.set_xlim(xmin if xmin is not None else current[0], xmax if xmax is not None else current[1])
            if ymin is not None or ymax is not None:
                current = ax.get_ylim()
                ax.set_ylim(ymin if ymin is not None else current[0], ymax if ymax is not None else current[1])
        except ValueError:
            self.status.set("Axis range ignored: please enter numeric min/max values.")

    def apply_axis_range(self) -> None:
        if not self.fig.axes:
            return
        for ax in self.fig.axes:
            if ax.get_visible():
                self._apply_axis_range_to_ax(ax)
        self.fig.tight_layout()
        self.canvas.draw()
        self.status.set("Axis range applied to all visible panels.")

    def save_current_png(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if path:
            self.fig.savefig(path, bbox_inches="tight", dpi=160)
            self.status.set(f"Saved {path}")


def main() -> None:
    app = EbeamVisualizerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
