from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import duckdb
import pandas as pd


DEFAULT_COLUMNS = [
    "DieIDX",
    "DieIDY",
    "WaferPosX",
    "WaferPosY",
    "ImageID",
    "CD",
    "BendingAngle",
    "LayerType",
    "LayerNO",
    "Moduleindex",
]

LAYER_COLUMNS = ["LayerType", "LayerNO", "Moduleindex"]
JOIN_KEYS = ["ImageID"]
RADIUS_COLUMN = "Radius"
COLUMN_ALIASES = {
    "ImageID": ["ImageID", "ImageIDX"],
}


@dataclass
class DataSource:
    path: Path
    relation_sql: str
    con: duckdb.DuckDBPyConnection
    temp_view: Optional[str] = None

    def close(self) -> None:
        self.con.close()


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def string_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def make_connection(memory_limit: str = "4GB", threads: Optional[int] = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    con.execute("SET memory_limit=" + string_literal(memory_limit))
    if threads:
        con.execute("SET threads={}".format(int(threads)))
    return con


def open_source(path: os.PathLike, memory_limit: str = "4GB", threads: Optional[int] = None) -> DataSource:
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    con = make_connection(memory_limit=memory_limit, threads=threads)
    suffix = file_path.suffix.lower()
    escaped = str(file_path).replace("'", "''")

    if suffix in {".csv", ".txt"}:
        relation_sql = "read_csv_auto('{}', header=true, ignore_errors=true, sample_size=200000)".format(escaped)
        return DataSource(file_path, relation_sql, con)
    if suffix in {".parquet", ".pq"}:
        relation_sql = "read_parquet('{}')".format(escaped)
        return DataSource(file_path, relation_sql, con)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        df = pd.read_excel(file_path)
        con.register("xlsx_input", df)
        return DataSource(file_path, "xlsx_input", con, temp_view="xlsx_input")

    raise ValueError("Unsupported file type: {}. Use CSV, Parquet, or small Excel files.".format(suffix))


def list_columns(path: os.PathLike) -> List[str]:
    src = open_source(path)
    try:
        rows = src.con.execute("DESCRIBE SELECT * FROM {} LIMIT 0".format(src.relation_sql)).fetchall()
        return [row[0] for row in rows]
    finally:
        src.close()


def list_plot_columns(path: os.PathLike) -> List[str]:
    columns = list_columns(path)
    if has_columns(columns, ["WaferPosX", "WaferPosY"]):
        return [RADIUS_COLUMN] + columns
    return columns


def resolve_column(columns: Sequence[str], requested: str) -> str:
    candidates = [requested] + COLUMN_ALIASES.get(requested, [])
    for candidate in candidates:
        for column in columns:
            if column == candidate:
                return column
    candidate_keys = [candidate.strip().lower() for candidate in candidates]
    for candidate_key in candidate_keys:
        for column in columns:
            if column.strip().lower() == candidate_key:
                return column
    raise ValueError("Missing selected column: {}".format(requested))


def distinct_values(path: os.PathLike, column: str, limit: int = 100) -> List[str]:
    columns = require_columns(path, [column], "Distinct value lookup")
    actual_column = resolve_column(columns, column)
    src = open_source(path)
    try:
        sql = """
        SELECT DISTINCT cast({column} AS VARCHAR) AS value
        FROM {source}
        WHERE {column} IS NOT NULL
        ORDER BY value
        LIMIT {limit}
        """.format(column=quote_ident(actual_column), source=src.relation_sql, limit=int(limit))
        return [str(row[0]) for row in src.con.execute(sql).fetchall()]
    finally:
        src.close()


def has_columns(columns: Sequence[str], required: Iterable[str]) -> bool:
    for column in required:
        try:
            resolve_column(columns, column)
        except ValueError:
            return False
    return True


def missing_columns(columns: Sequence[str], required: Iterable[str]) -> List[str]:
    missing = []
    for column in required:
        try:
            resolve_column(columns, column)
        except ValueError:
            missing.append(column)
    return missing


def validate_required_columns(columns: Sequence[str], required: Iterable[str] = DEFAULT_COLUMNS) -> List[str]:
    return missing_columns(columns, required)


def require_columns(path: os.PathLike, required: Iterable[str], feature_name: str) -> List[str]:
    columns = list_columns(path)
    missing = missing_columns(columns, required)
    if missing:
        raise ValueError("{} needs missing column(s): {}".format(feature_name, ", ".join(missing)))
    return columns


def radius_expr(x_col: str = "WaferPosX", y_col: str = "WaferPosY", center_x: float = 0.0, center_y: float = 0.0) -> str:
    return "sqrt(pow(try_cast({} AS DOUBLE) - ({center_x}), 2) + pow(try_cast({} AS DOUBLE) - ({center_y}), 2))".format(
        quote_ident(x_col),
        quote_ident(y_col),
        center_x=float(center_x),
        center_y=float(center_y),
    )


def field_expr(field: str, columns: Sequence[str], radius_center: Tuple[float, float] = (0.0, 0.0)) -> str:
    if field == RADIUS_COLUMN:
        if not has_columns(columns, ["WaferPosX", "WaferPosY"]):
            raise ValueError("Radius needs WaferPosX and WaferPosY.")
        x_col = resolve_column(columns, "WaferPosX")
        y_col = resolve_column(columns, "WaferPosY")
        return radius_expr(x_col, y_col, radius_center[0], radius_center[1])
    if not has_columns(columns, [field]):
        raise ValueError("Missing selected column: {}".format(field))
    return "try_cast({} AS DOUBLE)".format(quote_ident(resolve_column(columns, field)))


def layer_label_expr(columns: Sequence[str], table_alias: str = "") -> str:
    prefix = table_alias + "." if table_alias else ""
    parts = []
    if has_columns(columns, ["LayerType"]):
        parts.append("'LayerType=' || coalesce(cast({}{} AS VARCHAR), 'NA')".format(prefix, quote_ident(resolve_column(columns, "LayerType"))))
    if has_columns(columns, ["LayerNO"]):
        parts.append("'LayerNO=' || coalesce(cast({}{} AS VARCHAR), 'NA')".format(prefix, quote_ident(resolve_column(columns, "LayerNO"))))
    if has_columns(columns, ["Moduleindex"]):
        parts.append("'Module=' || coalesce(cast({}{} AS VARCHAR), 'NA')".format(prefix, quote_ident(resolve_column(columns, "Moduleindex"))))
    if not parts:
        return "'All data'"
    return " || ' | ' || ".join(parts)


def split_filter_values(value: Union[str, Sequence[str]]) -> List[str]:
    if isinstance(value, str):
        raw_values = value.replace(";", ",").split(",")
    else:
        raw_values = list(value)
    return [str(v).strip() for v in raw_values if str(v).strip()]


def where_from_filters(filters: Optional[Dict[str, Union[str, Sequence[str]]]], columns: Optional[Sequence[str]] = None) -> str:
    if not filters:
        return ""
    clauses = []
    for col, value in filters.items():
        if value is None or str(value).strip() == "":
            continue
        if columns is not None and not has_columns(columns, [col]):
            raise ValueError("Filter column does not exist: {}".format(col))
        actual_col = resolve_column(columns, col) if columns is not None else col
        values = split_filter_values(value)
        if not values:
            continue
        if len(values) == 1:
            clauses.append("cast({} AS VARCHAR) = {}".format(quote_ident(actual_col), string_literal(values[0])))
        else:
            clauses.append("cast({} AS VARCHAR) IN ({})".format(quote_ident(actual_col), ", ".join(string_literal(v) for v in values)))
    return "" if not clauses else "WHERE " + " AND ".join(clauses)


def query_radius_aggregate(
    path: os.PathLike,
    value_col: str = "CD",
    radius_bin: float = 500.0,
    filters: Optional[Dict[str, Union[str, Sequence[str]]]] = None,
    group_series: bool = False,
    radius_center: Tuple[float, float] = (0.0, 0.0),
    memory_limit: str = "4GB",
) -> pd.DataFrame:
    columns = require_columns(path, ["WaferPosX", "WaferPosY", value_col], "CD by wafer radius")
    x_col = resolve_column(columns, "WaferPosX")
    y_col = resolve_column(columns, "WaferPosY")
    actual_value_col = resolve_column(columns, value_col)
    src = open_source(path, memory_limit=memory_limit)
    try:
        r = radius_expr(x_col, y_col, radius_center[0], radius_center[1])
        where = where_from_filters(filters, columns)
        series_expr = layer_label_expr(columns) if group_series else "'All selected data'"
        sql = """
        WITH base AS (
            SELECT
                floor(({r}) / {radius_bin}) * {radius_bin} + ({radius_bin} / 2.0) AS radius_bin,
                try_cast({value_col} AS DOUBLE) AS value,
                {series_expr} AS series_label
            FROM {source}
            {where_clause}
        )
        SELECT
            radius_bin,
            series_label,
            avg(value) AS value_mean,
            stddev_samp(value) AS value_std,
            min(value) AS value_min,
            max(value) AS value_max,
            count(*) AS n
        FROM base
        WHERE radius_bin IS NOT NULL AND value IS NOT NULL
        GROUP BY radius_bin, series_label
        ORDER BY series_label, radius_bin
        """.format(
            r=r,
            radius_bin=float(radius_bin),
            value_col=quote_ident(actual_value_col),
            series_expr=series_expr,
            source=src.relation_sql,
            where_clause=where,
        )
        return src.con.execute(sql).fetchdf()
    finally:
        src.close()


def query_radius_sigma(
    path: os.PathLike,
    value_col: str = "CD",
    radius_bin: float = 500.0,
    filters: Optional[Dict[str, Union[str, Sequence[str]]]] = None,
    group_series: bool = False,
    sigma_mode: str = "radius_bin",
    radius_center: Tuple[float, float] = (0.0, 0.0),
    memory_limit: str = "4GB",
) -> pd.DataFrame:
    if sigma_mode not in {"radius_bin", "image"}:
        raise ValueError("sigma_mode must be radius_bin or image")

    required = ["WaferPosX", "WaferPosY", value_col]
    if sigma_mode == "image":
        required.append("ImageID")
    columns = require_columns(path, required, "Radius sigma")
    x_col = resolve_column(columns, "WaferPosX")
    y_col = resolve_column(columns, "WaferPosY")
    actual_value_col = resolve_column(columns, value_col)
    src = open_source(path, memory_limit=memory_limit)
    try:
        r = radius_expr(x_col, y_col, radius_center[0], radius_center[1])
        where = where_from_filters(filters, columns)
        series_expr = layer_label_expr(columns) if group_series else "'All selected data'"
        value = "try_cast({} AS DOUBLE)".format(quote_ident(actual_value_col))

        if sigma_mode == "radius_bin":
            sql = """
            WITH base AS (
                SELECT
                    floor(({r}) / {radius_bin}) * {radius_bin} + ({radius_bin} / 2.0) AS radius_bin,
                    {value} AS value,
                    {series_expr} AS series_label
                FROM {source}
                {where_clause}
            )
            SELECT
                radius_bin,
                series_label,
                stddev_samp(value) AS sigma,
                count(*) AS n
            FROM base
            WHERE radius_bin IS NOT NULL AND value IS NOT NULL
            GROUP BY radius_bin, series_label
            ORDER BY series_label, radius_bin
            """.format(
                r=r,
                radius_bin=float(radius_bin),
                value=value,
                series_expr=series_expr,
                source=src.relation_sql,
                where_clause=where,
            )
        else:
            image_col = quote_ident(resolve_column(columns, "ImageID"))
            sql = """
            WITH base AS (
                SELECT
                    cast({image_col} AS VARCHAR) AS image_id,
                    {r} AS radius_value,
                    {value} AS value,
                    {series_expr} AS series_label
                FROM {source}
                {where_clause}
            ),
            image_sigma AS (
                SELECT
                    image_id,
                    series_label,
                    avg(radius_value) AS radius_value,
                    stddev_samp(value) AS image_sigma,
                    count(*) AS raw_n
                FROM base
                WHERE image_id IS NOT NULL AND radius_value IS NOT NULL AND value IS NOT NULL
                GROUP BY image_id, series_label
            )
            SELECT
                floor(radius_value / {radius_bin}) * {radius_bin} + ({radius_bin} / 2.0) AS radius_bin,
                series_label,
                avg(image_sigma) AS sigma,
                count(*) AS n
            FROM image_sigma
            WHERE image_sigma IS NOT NULL
            GROUP BY radius_bin, series_label
            ORDER BY series_label, radius_bin
            """.format(
                image_col=image_col,
                r=r,
                value=value,
                series_expr=series_expr,
                source=src.relation_sql,
                where_clause=where,
                radius_bin=float(radius_bin),
            )
        return src.con.execute(sql).fetchdf()
    finally:
        src.close()


def query_xy(
    path: os.PathLike,
    x_col: str,
    y_col: str,
    sample_rows: int = 200000,
    use_sample: bool = True,
    filters: Optional[Dict[str, Union[str, Sequence[str]]]] = None,
    group_series: bool = True,
    aggregate_by_image: bool = False,
    radius_center: Tuple[float, float] = (0.0, 0.0),
    memory_limit: str = "4GB",
) -> pd.DataFrame:
    columns = list_columns(path)
    aggregate_by_image = aggregate_by_image and has_columns(columns, ["ImageID"])
    x_expr = field_expr(x_col, columns, radius_center=radius_center)
    y_expr = field_expr(y_col, columns, radius_center=radius_center)
    src = open_source(path, memory_limit=memory_limit)
    try:
        where = where_from_filters(filters, columns)
        sample_clause = "USING SAMPLE reservoir({} ROWS)".format(int(sample_rows)) if use_sample else ""
        series_expr = layer_label_expr(columns) if group_series else "'All selected data'"
        if aggregate_by_image:
            image_col = quote_ident(resolve_column(columns, "ImageID"))
            where_clause = where
            sql = """
            WITH base AS (
                SELECT
                    cast({image_col} AS VARCHAR) AS image_id,
                    {x_expr} AS x,
                    {y_expr} AS y,
                    {series_expr} AS layer_label
                FROM {source}
                {where_clause}
            ),
            image_level AS (
                SELECT
                    avg(x) AS x,
                    avg(y) AS y,
                    layer_label,
                    count(*) AS raw_n
                FROM base
                WHERE image_id IS NOT NULL AND x IS NOT NULL AND y IS NOT NULL
                GROUP BY image_id, layer_label
            )
            SELECT x, y, layer_label
            FROM image_level
            {sample_clause}
            """.format(
                image_col=image_col,
                x_expr=x_expr,
                y_expr=y_expr,
                series_expr=series_expr,
                source=src.relation_sql,
                where_clause=where_clause,
                sample_clause=sample_clause,
            )
        elif where:
            sql = """
            WITH filtered AS (
                SELECT * FROM {source}
                {where_clause}
            )
            SELECT
                {x_expr} AS x,
                {y_expr} AS y,
                {series_expr} AS layer_label
            FROM filtered
            {sample_clause}
            """.format(
                x_expr=x_expr,
                y_expr=y_expr,
                series_expr=series_expr,
                source=src.relation_sql,
                sample_clause=sample_clause,
                where_clause=where,
            )
        else:
            sql = """
            SELECT
                {x_expr} AS x,
                {y_expr} AS y,
                {series_expr} AS layer_label
            FROM {source}
            {sample_clause}
            """.format(
                x_expr=x_expr,
                y_expr=y_expr,
                series_expr=series_expr,
                source=src.relation_sql,
                sample_clause=sample_clause,
            )
        df = src.con.execute(sql).fetchdf()
        return df.dropna(subset=["x", "y"])
    finally:
        src.close()


def query_layer_histogram(
    path: os.PathLike,
    value_col: str = "CD",
    bins: int = 80,
    max_layers: int = 12,
    filters: Optional[Dict[str, Union[str, Sequence[str]]]] = None,
    group_series: bool = True,
    memory_limit: str = "4GB",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    columns = require_columns(path, [value_col], "Layer CD distribution")
    actual_value_col = resolve_column(columns, value_col)
    src = open_source(path, memory_limit=memory_limit)
    try:
        where = where_from_filters(filters, columns)
        layer_expr = layer_label_expr(columns) if group_series else "'All selected data'"
        value = "try_cast({} AS DOUBLE)".format(quote_ident(actual_value_col))

        top_layers_sql = """
        SELECT {layer_expr} AS layer_label, count(*) AS n
        FROM {source}
        {where_clause}
        GROUP BY layer_label
        ORDER BY n DESC
        LIMIT {max_layers}
        """.format(layer_expr=layer_expr, source=src.relation_sql, where_clause=where, max_layers=int(max_layers))
        top_layers = src.con.execute(top_layers_sql).fetchdf()
        if top_layers.empty:
            return pd.DataFrame(), pd.DataFrame()
        label_filter = ", ".join([string_literal(x) for x in top_layers["layer_label"].astype(str).tolist()])

        stats_sql = """
        WITH base AS (
            SELECT {layer_expr} AS layer_label, {value} AS value
            FROM {source}
            {where_clause}
        )
        SELECT layer_label, count(*) AS n, avg(value) AS mean, stddev_samp(value) AS std,
               min(value) AS min_value, max(value) AS max_value
        FROM base
        WHERE value IS NOT NULL AND layer_label IN ({label_filter})
        GROUP BY layer_label
        ORDER BY n DESC
        """.format(layer_expr=layer_expr, value=value, source=src.relation_sql, where_clause=where, label_filter=label_filter)
        stats = src.con.execute(stats_sql).fetchdf()
        if stats.empty:
            return pd.DataFrame(), pd.DataFrame()

        min_v = float(stats["min_value"].min())
        max_v = float(stats["max_value"].max())
        if not math.isfinite(min_v) or not math.isfinite(max_v) or min_v == max_v:
            min_v -= 0.5
            max_v += 0.5
        bin_width = (max_v - min_v) / int(bins)

        hist_sql = """
        WITH base AS (
            SELECT {layer_expr} AS layer_label, {value} AS value
            FROM {source}
            {where_clause}
        ),
        binned AS (
            SELECT
                layer_label,
                greatest(0, least({last_bin}, floor((value - {min_v}) / {bin_width}))) AS bin_id
            FROM base
            WHERE value IS NOT NULL AND layer_label IN ({label_filter})
        )
        SELECT
            layer_label,
            bin_id,
            {min_v} + (bin_id + 0.5) * {bin_width} AS bin_center,
            count(*) AS n
        FROM binned
        GROUP BY layer_label, bin_id
        ORDER BY layer_label, bin_id
        """.format(
            layer_expr=layer_expr,
            value=value,
            source=src.relation_sql,
            where_clause=where,
            last_bin=int(bins) - 1,
            min_v=min_v,
            bin_width=bin_width,
            label_filter=label_filter,
        )
        hist = src.con.execute(hist_sql).fetchdf()
        return hist, stats
    finally:
        src.close()


def build_line_filter(layer_type: str = "", layer_no: str = "", moduleindex: str = "", columns: Optional[Sequence[str]] = None) -> str:
    filters = {}
    if layer_type.strip():
        filters["LayerType"] = layer_type.strip()
    if layer_no.strip():
        filters["LayerNO"] = layer_no.strip()
    if moduleindex.strip():
        filters["Moduleindex"] = moduleindex.strip()
    return where_from_filters(filters, columns)


def query_line_loading(
    path: os.PathLike,
    line_a: Dict[str, str],
    line_b: Dict[str, str],
    operation: str = "subtract",
    radius_bin: float = 500.0,
    value_col: str = "CD",
    group_series: bool = False,
    radius_center: Tuple[float, float] = (0.0, 0.0),
    memory_limit: str = "4GB",
) -> pd.DataFrame:
    if operation not in {"subtract", "add", "ratio"}:
        raise ValueError("operation must be subtract, add, or ratio")

    required = ["ImageID", "WaferPosX", "WaferPosY", value_col]
    columns = require_columns(path, required, "Line CD loading")
    actual_image_col = resolve_column(columns, "ImageID")
    actual_value_col = resolve_column(columns, value_col)
    x_col = resolve_column(columns, "WaferPosX")
    y_col = resolve_column(columns, "WaferPosY")
    src = open_source(path, memory_limit=memory_limit)
    try:
        a_where = build_line_filter(line_a.get("LayerType", ""), line_a.get("LayerNO", ""), line_a.get("Moduleindex", ""), columns)
        b_where = build_line_filter(line_b.get("LayerType", ""), line_b.get("LayerNO", ""), line_b.get("Moduleindex", ""), columns)
        join_clause = "a.image_id = b.image_id"
        r = radius_expr(x_col, y_col, radius_center[0], radius_center[1])
        value = "try_cast({} AS DOUBLE)".format(quote_ident(actual_value_col))
        a_label = layer_label_expr(columns)
        b_label = layer_label_expr(columns)
        paired_series = "a.line_label || ' vs ' || b.line_label" if group_series else "'All selected pairs'"

        if operation == "subtract":
            metric = "a.cd_value - b.cd_value"
        elif operation == "add":
            metric = "a.cd_value + b.cd_value"
        else:
            metric = "CASE WHEN b.cd_value = 0 THEN NULL ELSE a.cd_value / b.cd_value END"

        sql = """
        WITH a_raw AS (
            SELECT
                cast({image_col} AS VARCHAR) AS image_id,
                {radius} AS radius_value,
                {value} AS cd_value,
                {a_label} AS line_label
            FROM {source}
            {a_where}
        ),
        b_raw AS (
            SELECT
                cast({image_col} AS VARCHAR) AS image_id,
                {value} AS cd_value,
                {b_label} AS line_label
            FROM {source}
            {b_where}
        ),
        a AS (
            SELECT
                image_id,
                line_label,
                avg(radius_value) AS radius_value,
                avg(cd_value) AS cd_value,
                count(*) AS raw_n
            FROM a_raw
            WHERE image_id IS NOT NULL AND cd_value IS NOT NULL AND radius_value IS NOT NULL
            GROUP BY image_id, line_label
        ),
        b AS (
            SELECT
                image_id,
                line_label,
                avg(cd_value) AS cd_value,
                count(*) AS raw_n
            FROM b_raw
            WHERE image_id IS NOT NULL AND cd_value IS NOT NULL
            GROUP BY image_id, line_label
        ),
        paired AS (
            SELECT
                floor((a.radius_value) / {radius_bin}) * {radius_bin} + ({radius_bin} / 2.0) AS radius_bin,
                {metric} AS loading_value,
                {paired_series} AS series_label
            FROM a
            INNER JOIN b ON {join_clause}
            WHERE a.cd_value IS NOT NULL AND b.cd_value IS NOT NULL
        )
        SELECT
            radius_bin,
            series_label,
            avg(loading_value) AS loading_mean,
            stddev_samp(loading_value) AS loading_std,
            min(loading_value) AS loading_min,
            max(loading_value) AS loading_max,
            count(*) AS n
        FROM paired
        WHERE radius_bin IS NOT NULL AND loading_value IS NOT NULL
        GROUP BY radius_bin, series_label
        ORDER BY series_label, radius_bin
        """.format(
            image_col=quote_ident(actual_image_col),
            value=value,
            a_label=a_label,
            b_label=b_label,
            source=src.relation_sql,
            a_where=a_where,
            b_where=b_where,
            radius=r,
            radius_bin=float(radius_bin),
            metric=metric,
            paired_series=paired_series,
            join_clause=join_clause,
        )
        return src.con.execute(sql).fetchdf()
    finally:
        src.close()


def query_fin_center_loading(
    path: os.PathLike,
    line_a: Dict[str, str],
    line_b: Dict[str, str],
    line_c: Dict[str, str],
    radius_bin: float = 500.0,
    value_col: str = "CD",
    group_series: bool = False,
    radius_center: Tuple[float, float] = (0.0, 0.0),
    memory_limit: str = "4GB",
) -> pd.DataFrame:
    required = ["ImageID", "WaferPosX", "WaferPosY", value_col]
    columns = require_columns(path, required, "FIN center loading")
    actual_image_col = resolve_column(columns, "ImageID")
    actual_value_col = resolve_column(columns, value_col)
    x_col = resolve_column(columns, "WaferPosX")
    y_col = resolve_column(columns, "WaferPosY")
    src = open_source(path, memory_limit=memory_limit)
    try:
        a_where = build_line_filter(line_a.get("LayerType", ""), line_a.get("LayerNO", ""), line_a.get("Moduleindex", ""), columns)
        b_where = build_line_filter(line_b.get("LayerType", ""), line_b.get("LayerNO", ""), line_b.get("Moduleindex", ""), columns)
        c_where = build_line_filter(line_c.get("LayerType", ""), line_c.get("LayerNO", ""), line_c.get("Moduleindex", ""), columns)
        r = radius_expr(x_col, y_col, radius_center[0], radius_center[1])
        value = "try_cast({} AS DOUBLE)".format(quote_ident(actual_value_col))
        label_expr = layer_label_expr(columns)
        paired_series = "a.line_label || ' / ' || b.line_label || ' / ' || c.line_label" if group_series else "'All selected FIN triplets'"

        sql = """
        WITH a_raw AS (
            SELECT cast({image_col} AS VARCHAR) AS image_id, {radius} AS radius_value,
                   {value} AS cd_value, {label_expr} AS line_label
            FROM {source}
            {a_where}
        ),
        b_raw AS (
            SELECT cast({image_col} AS VARCHAR) AS image_id,
                   {value} AS cd_value, {label_expr} AS line_label
            FROM {source}
            {b_where}
        ),
        c_raw AS (
            SELECT cast({image_col} AS VARCHAR) AS image_id,
                   {value} AS cd_value, {label_expr} AS line_label
            FROM {source}
            {c_where}
        ),
        a AS (
            SELECT image_id, line_label, avg(radius_value) AS radius_value, avg(cd_value) AS cd_value
            FROM a_raw
            WHERE image_id IS NOT NULL AND radius_value IS NOT NULL AND cd_value IS NOT NULL
            GROUP BY image_id, line_label
        ),
        b AS (
            SELECT image_id, line_label, avg(cd_value) AS cd_value
            FROM b_raw
            WHERE image_id IS NOT NULL AND cd_value IS NOT NULL
            GROUP BY image_id, line_label
        ),
        c AS (
            SELECT image_id, line_label, avg(cd_value) AS cd_value
            FROM c_raw
            WHERE image_id IS NOT NULL AND cd_value IS NOT NULL
            GROUP BY image_id, line_label
        ),
        paired AS (
            SELECT
                floor((a.radius_value) / {radius_bin}) * {radius_bin} + ({radius_bin} / 2.0) AS radius_bin,
                ((a.cd_value + c.cd_value) / 2.0) - b.cd_value AS loading_value,
                {paired_series} AS series_label
            FROM a
            INNER JOIN b ON a.image_id = b.image_id
            INNER JOIN c ON a.image_id = c.image_id
        )
        SELECT
            radius_bin,
            series_label,
            avg(loading_value) AS loading_mean,
            stddev_samp(loading_value) AS loading_std,
            min(loading_value) AS loading_min,
            max(loading_value) AS loading_max,
            count(*) AS n
        FROM paired
        WHERE radius_bin IS NOT NULL AND loading_value IS NOT NULL
        GROUP BY radius_bin, series_label
        ORDER BY series_label, radius_bin
        """.format(
            image_col=quote_ident(actual_image_col),
            radius=r,
            value=value,
            label_expr=label_expr,
            source=src.relation_sql,
            a_where=a_where,
            b_where=b_where,
            c_where=c_where,
            radius_bin=float(radius_bin),
            paired_series=paired_series,
        )
        return src.con.execute(sql).fetchdf()
    finally:
        src.close()


def query_wafer_value_heatmap(
    path: os.PathLike,
    value_col: str = "CD",
    bin_size: float = 5.0,
    wafer_diameter: float = 300.0,
    filters: Optional[Dict[str, Union[str, Sequence[str]]]] = None,
    radius_center: Tuple[float, float] = (0.0, 0.0),
    memory_limit: str = "4GB",
) -> pd.DataFrame:
    columns = require_columns(path, ["WaferPosX", "WaferPosY", value_col], "Wafer value heatmap")
    x_col = resolve_column(columns, "WaferPosX")
    y_col = resolve_column(columns, "WaferPosY")
    actual_value_col = resolve_column(columns, value_col)
    src = open_source(path, memory_limit=memory_limit)
    try:
        half = float(wafer_diameter) / 2.0
        bin_value = float(bin_size)
        where = where_from_filters(filters, columns)
        value = "try_cast({} AS DOUBLE)".format(quote_ident(actual_value_col))
        x_value = "try_cast({} AS DOUBLE) - ({})".format(quote_ident(x_col), float(radius_center[0]))
        y_value = "try_cast({} AS DOUBLE) - ({})".format(quote_ident(y_col), float(radius_center[1]))
        sql = """
        WITH base AS (
            SELECT
                {x_value} AS x,
                {y_value} AS y,
                {value} AS value
            FROM {source}
            {where_clause}
        ),
        binned AS (
            SELECT
                floor((x + {half}) / {bin_size}) * {bin_size} - {half} + ({bin_size} / 2.0) AS x_bin,
                floor((y + {half}) / {bin_size}) * {bin_size} - {half} + ({bin_size} / 2.0) AS y_bin,
                value
            FROM base
            WHERE x IS NOT NULL AND y IS NOT NULL AND value IS NOT NULL
              AND sqrt(pow(x, 2) + pow(y, 2)) <= {half}
        )
        SELECT x_bin, y_bin, avg(value) AS value_mean, min(value) AS value_min,
               max(value) AS value_max, count(*) AS n
        FROM binned
        GROUP BY x_bin, y_bin
        ORDER BY y_bin, x_bin
        """.format(
            x_value=x_value,
            y_value=y_value,
            value=value,
            source=src.relation_sql,
            where_clause=where,
            half=half,
            bin_size=bin_value,
        )
        return src.con.execute(sql).fetchdf()
    finally:
        src.close()


def query_wafer_loading_heatmap(
    path: os.PathLike,
    line_a: Dict[str, str],
    line_b: Dict[str, str],
    operation: str = "subtract",
    value_col: str = "CD",
    bin_size: float = 5.0,
    wafer_diameter: float = 300.0,
    radius_center: Tuple[float, float] = (0.0, 0.0),
    memory_limit: str = "4GB",
) -> pd.DataFrame:
    if operation not in {"subtract", "add", "ratio"}:
        raise ValueError("operation must be subtract, add, or ratio")

    columns = require_columns(path, ["ImageID", "WaferPosX", "WaferPosY", value_col], "Wafer loading heatmap")
    actual_image_col = resolve_column(columns, "ImageID")
    x_col = resolve_column(columns, "WaferPosX")
    y_col = resolve_column(columns, "WaferPosY")
    actual_value_col = resolve_column(columns, value_col)
    src = open_source(path, memory_limit=memory_limit)
    try:
        a_where = build_line_filter(line_a.get("LayerType", ""), line_a.get("LayerNO", ""), line_a.get("Moduleindex", ""), columns)
        b_where = build_line_filter(line_b.get("LayerType", ""), line_b.get("LayerNO", ""), line_b.get("Moduleindex", ""), columns)
        half = float(wafer_diameter) / 2.0
        bin_value = float(bin_size)
        x_value = "try_cast({} AS DOUBLE) - ({})".format(quote_ident(x_col), float(radius_center[0]))
        y_value = "try_cast({} AS DOUBLE) - ({})".format(quote_ident(y_col), float(radius_center[1]))
        value = "try_cast({} AS DOUBLE)".format(quote_ident(actual_value_col))
        label_expr = layer_label_expr(columns)
        if operation == "subtract":
            metric = "a.cd_value - b.cd_value"
        elif operation == "add":
            metric = "a.cd_value + b.cd_value"
        else:
            metric = "CASE WHEN b.cd_value = 0 THEN NULL ELSE a.cd_value / b.cd_value END"

        sql = """
        WITH a_raw AS (
            SELECT
                cast({image_col} AS VARCHAR) AS image_id,
                {x_value} AS x,
                {y_value} AS y,
                {value} AS cd_value,
                {label_expr} AS line_label
            FROM {source}
            {a_where}
        ),
        b_raw AS (
            SELECT
                cast({image_col} AS VARCHAR) AS image_id,
                {value} AS cd_value,
                {label_expr} AS line_label
            FROM {source}
            {b_where}
        ),
        a AS (
            SELECT image_id, line_label, avg(x) AS x, avg(y) AS y, avg(cd_value) AS cd_value
            FROM a_raw
            WHERE image_id IS NOT NULL AND x IS NOT NULL AND y IS NOT NULL AND cd_value IS NOT NULL
            GROUP BY image_id, line_label
        ),
        b AS (
            SELECT image_id, line_label, avg(cd_value) AS cd_value
            FROM b_raw
            WHERE image_id IS NOT NULL AND cd_value IS NOT NULL
            GROUP BY image_id, line_label
        ),
        paired AS (
            SELECT
                a.x,
                a.y,
                {metric} AS loading_value
            FROM a
            INNER JOIN b ON a.image_id = b.image_id
        ),
        binned AS (
            SELECT
                floor((x + {half}) / {bin_size}) * {bin_size} - {half} + ({bin_size} / 2.0) AS x_bin,
                floor((y + {half}) / {bin_size}) * {bin_size} - {half} + ({bin_size} / 2.0) AS y_bin,
                loading_value
            FROM paired
            WHERE x IS NOT NULL AND y IS NOT NULL AND loading_value IS NOT NULL
              AND sqrt(pow(x, 2) + pow(y, 2)) <= {half}
        )
        SELECT x_bin, y_bin, avg(loading_value) AS value_mean, min(loading_value) AS value_min,
               max(loading_value) AS value_max, count(*) AS n
        FROM binned
        GROUP BY x_bin, y_bin
        ORDER BY y_bin, x_bin
        """.format(
            image_col=quote_ident(actual_image_col),
            x_value=x_value,
            y_value=y_value,
            value=value,
            label_expr=label_expr,
            source=src.relation_sql,
            a_where=a_where,
            b_where=b_where,
            metric=metric,
            half=half,
            bin_size=bin_value,
        )
        return src.con.execute(sql).fetchdf()
    finally:
        src.close()
