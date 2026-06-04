"""
Visualization Agent.

Selects appropriate chart type and generates Plotly figure configs.

Chart selection rules:
  - time dimension → Line Chart
  - category comparison → Bar Chart (horizontal if many categories)
  - part-of-whole → Pie Chart
  - two numeric columns → Scatter Plot
  - single numeric column → Histogram
  - correlation matrix → Heatmap
  - forecast present → Combined Line + Confidence Band

Improvement: generates multiple charts where appropriate (e.g. trend + breakdown),
applies consistent dark theme, and adds forecast chart with CI bands.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from core.state import AgentState, ChartConfig, ChartType

# Consistent dark theme colour palette
COLOURS = [
    "#6366f1", "#22d3ee", "#10b981", "#f59e0b", "#ef4444",
    "#a78bfa", "#34d399", "#fb923c", "#60a5fa", "#f472b6",
]

GRID_COLOUR = "rgba(148,163,184,0.1)"
FONT_COLOUR = "#94a3b8"
TITLE_COLOUR = "#e2e8f0"
BG = "rgba(0,0,0,0)"


def _base_layout(title: str) -> Dict[str, Any]:
    return {
        "title": {"text": title, "font": {"color": TITLE_COLOUR, "size": 13}},
        "paper_bgcolor": BG,
        "plot_bgcolor": BG,
        "font": {"color": FONT_COLOUR, "family": "Inter, sans-serif", "size": 11},
        "margin": {"l": 60, "r": 20, "t": 50, "b": 60},
        "legend": {"bgcolor": BG, "font": {"color": FONT_COLOUR}},
        "xaxis": {"gridcolor": GRID_COLOUR, "zerolinecolor": GRID_COLOUR},
        "yaxis": {"gridcolor": GRID_COLOUR, "zerolinecolor": GRID_COLOUR},
    }


async def visualization_node(state: AgentState) -> AgentState:
    """
    LangGraph node: builds Plotly figure configs from SQL + analysis results.
    Generates up to 3 charts per response.
    """
    if not state.sql_result or not state.sql_result.data:
        state.agent_trace.append("visualization:no_data")
        return state

    df = pd.DataFrame(state.sql_result.data)
    charts: List[ChartConfig] = []

    # Convert numeric columns
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass

    date_col = _find_date_col(df)
    metric_col = _find_metric_col(df)
    dim_col = _find_dim_col(df)
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    # -----------------------------------------------------------------------
    # Chart 1: Primary data chart
    # -----------------------------------------------------------------------
    has_time = date_col is not None

    if has_time and metric_col:
        # Time series — line chart; group by dimension if present
        if dim_col:
            chart = _multi_series_line(df, date_col, metric_col, dim_col)
        else:
            chart = _single_line(df, date_col, metric_col)
        charts.append(chart)

    elif dim_col and metric_col:
        # Category breakdown — bar chart
        chart = _bar_chart(df, dim_col, metric_col)
        charts.append(chart)

    elif len(numeric_cols) == 2:
        # Two numeric columns — scatter
        chart = _scatter_chart(df, numeric_cols[0], numeric_cols[1])
        charts.append(chart)

    elif len(numeric_cols) == 1:
        # Single metric — histogram
        chart = _histogram(df, numeric_cols[0])
        charts.append(chart)

    # -----------------------------------------------------------------------
    # Chart 2: Forecast chart (if forecasting was done)
    # -----------------------------------------------------------------------
    if state.analysis and state.analysis.forecast and state.analysis.forecast.get("available"):
        fc = state.analysis.forecast
        forecast_chart = _forecast_chart(fc)
        charts.append(forecast_chart)

    # -----------------------------------------------------------------------
    # Chart 3: Top performers breakdown (if available)
    # -----------------------------------------------------------------------
    if state.analysis and state.analysis.top_performers and len(state.analysis.top_performers) >= 3:
        top_chart = _top_performers_chart(state.analysis.top_performers, metric_col or "value")
        charts.append(top_chart)

    state.charts = charts
    state.agent_trace.append("visualization")
    return state


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _single_line(df: pd.DataFrame, date_col: str, metric_col: str) -> ChartConfig:
    labels = [str(v) for v in df[date_col].tolist()]
    values = [round(float(v), 2) for v in df[metric_col].tolist()]
    title = f"{metric_col.replace('_', ' ').title()} Over Time"
    return ChartConfig(
        chart_type=ChartType.LINE,
        title=title,
        x_axis=date_col,
        y_axis=metric_col,
        plotly_figure={
            "data": [{
                "type": "scatter", "mode": "lines+markers",
                "x": labels, "y": values, "name": metric_col,
                "line": {"color": COLOURS[0], "width": 2},
                "marker": {"color": COLOURS[0], "size": 5},
                "fill": "tozeroy", "fillcolor": "rgba(99,102,241,0.08)",
            }],
            "layout": _base_layout(title),
        },
    )


def _multi_series_line(df: pd.DataFrame, date_col: str, metric_col: str, dim_col: str) -> ChartConfig:
    title = f"{metric_col.replace('_', ' ').title()} by {dim_col.replace('_', ' ').title()}"
    traces = []
    for i, (dim_val, group) in enumerate(df.groupby(dim_col)):
        group = group.sort_values(date_col)
        traces.append({
            "type": "scatter", "mode": "lines+markers",
            "x": [str(v) for v in group[date_col].tolist()],
            "y": [round(float(v), 2) for v in group[metric_col].tolist()],
            "name": str(dim_val),
            "line": {"color": COLOURS[i % len(COLOURS)], "width": 2},
            "marker": {"size": 5},
        })
    return ChartConfig(
        chart_type=ChartType.LINE, title=title,
        x_axis=date_col, y_axis=metric_col,
        plotly_figure={"data": traces, "layout": _base_layout(title)},
    )


def _bar_chart(df: pd.DataFrame, dim_col: str, metric_col: str) -> ChartConfig:
    title = f"{metric_col.replace('_', ' ').title()} by {dim_col.replace('_', ' ').title()}"
    grouped = df.groupby(dim_col)[metric_col].sum().reset_index().sort_values(metric_col, ascending=False)
    horizontal = len(grouped) > 6
    orientation = "h" if horizontal else "v"
    return ChartConfig(
        chart_type=ChartType.BAR, title=title,
        x_axis=dim_col, y_axis=metric_col,
        plotly_figure={
            "data": [{
                "type": "bar",
                "x": [round(float(v), 2) for v in grouped[metric_col]] if horizontal else [str(v) for v in grouped[dim_col]],
                "y": [str(v) for v in grouped[dim_col]] if horizontal else [round(float(v), 2) for v in grouped[metric_col]],
                "orientation": orientation,
                "marker": {"color": COLOURS[:len(grouped)]},
            }],
            "layout": {**_base_layout(title), "showlegend": False},
        },
    )


def _scatter_chart(df: pd.DataFrame, x_col: str, y_col: str) -> ChartConfig:
    title = f"{x_col.replace('_', ' ').title()} vs {y_col.replace('_', ' ').title()}"
    return ChartConfig(
        chart_type=ChartType.SCATTER, title=title,
        x_axis=x_col, y_axis=y_col,
        plotly_figure={
            "data": [{
                "type": "scatter", "mode": "markers",
                "x": df[x_col].tolist(), "y": df[y_col].tolist(),
                "marker": {"color": COLOURS[0], "size": 8, "opacity": 0.7},
            }],
            "layout": _base_layout(title),
        },
    )


def _histogram(df: pd.DataFrame, col: str) -> ChartConfig:
    title = f"Distribution of {col.replace('_', ' ').title()}"
    return ChartConfig(
        chart_type=ChartType.HISTOGRAM, title=title,
        x_axis=col, y_axis="count",
        plotly_figure={
            "data": [{"type": "histogram", "x": df[col].tolist(),
                      "marker": {"color": COLOURS[0]}, "nbinsx": 20}],
            "layout": _base_layout(title),
        },
    )


def _forecast_chart(fc: Dict[str, Any]) -> ChartConfig:
    title = f"{fc['metric'].replace('_', ' ').title()} Forecast ({fc['periods']} periods)"
    traces = [
        {
            "type": "scatter", "mode": "lines+markers", "name": "Historical",
            "x": fc["historical_labels"], "y": fc["historical_values"],
            "line": {"color": COLOURS[0], "width": 2},
        },
        {
            "type": "scatter", "mode": "lines+markers", "name": "Forecast",
            "x": fc["forecast_labels"], "y": fc["forecast_values"],
            "line": {"color": COLOURS[1], "width": 2, "dash": "dot"},
            "marker": {"color": COLOURS[1], "size": 6},
        },
        {
            "type": "scatter", "mode": "lines", "name": "Upper CI",
            "x": fc["forecast_labels"], "y": fc["upper_ci"],
            "line": {"color": "rgba(34,211,238,0.2)", "width": 0},
            "showlegend": False,
        },
        {
            "type": "scatter", "mode": "lines", "name": "Confidence Band",
            "x": fc["forecast_labels"], "y": fc["lower_ci"],
            "line": {"color": "rgba(34,211,238,0.2)", "width": 0},
            "fill": "tonexty", "fillcolor": "rgba(34,211,238,0.1)",
        },
    ]
    return ChartConfig(
        chart_type=ChartType.LINE, title=title,
        x_axis="date", y_axis=fc["metric"],
        plotly_figure={"data": traces, "layout": _base_layout(title)},
    )


def _top_performers_chart(performers: List[Dict], metric_col: str) -> ChartConfig:
    keys = list(performers[0].keys())
    dim_key = next((k for k in keys if k not in [metric_col] and isinstance(performers[0].get(k), str)), keys[0])
    title = f"Top Performers by {metric_col.replace('_', ' ').title()}"
    labels = [str(p.get(dim_key, "")) for p in performers]
    values = [round(float(p.get(metric_col, 0)), 2) for p in performers]
    return ChartConfig(
        chart_type=ChartType.PIE, title=title,
        x_axis=dim_key, y_axis=metric_col,
        plotly_figure={
            "data": [{
                "type": "pie", "labels": labels, "values": values,
                "hole": 0.4,
                "marker": {"colors": COLOURS[:len(labels)]},
                "textinfo": "label+percent",
                "textfont": {"color": TITLE_COLOUR},
            }],
            "layout": _base_layout(title),
        },
    )


# ---------------------------------------------------------------------------
# Column detection helpers
# ---------------------------------------------------------------------------

def _find_date_col(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if any(k in col.lower() for k in ["date", "month", "quarter", "year", "period"]):
            return col
    return None


def _find_metric_col(df: pd.DataFrame) -> str | None:
    for pref in ["revenue", "profit", "units_sold", "orders_count", "total", "amount", "value"]:
        for col in df.columns:
            if pref in col.lower():
                try:
                    pd.to_numeric(df[col])
                    return col
                except Exception:
                    pass
    numeric = df.select_dtypes(include="number").columns.tolist()
    return numeric[0] if numeric else None


def _find_dim_col(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if any(k in col.lower() for k in ["region", "product", "category", "segment", "name"]):
            if df[col].dtype == object:
                return col
    return None
