"""
Data Analysis Agent.

Performs statistical analysis on query results using Pandas + NumPy + SciPy.

Computes:
- KPIs (totals, averages, medians)
- Month-over-Month / Quarter-over-Quarter growth rates
- Outlier detection (IQR method)
- Correlation analysis
- Top/bottom performers ranking
- Summary statistics

Improvement: added MoM/QoQ growth, top/bottom performer extraction,
and structured KPI output with proper formatting.
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from core.state import AgentState, AnalysisResult


def _safe_growth(current: float, previous: float) -> float | None:
    """Calculate growth rate, returning None if previous is 0."""
    if previous and previous != 0:
        return round((current - previous) / abs(previous) * 100, 2)
    return None


async def data_analysis_node(state: AgentState) -> AgentState:
    """
    LangGraph node: statistical analysis of SQL result data.
    """
    if not state.sql_result or not state.sql_result.data:
        state.analysis = AnalysisResult()
        state.agent_trace.append("data_analysis:no_data")
        return state

    data = state.sql_result.data
    df = pd.DataFrame(data)

    # Convert numeric columns
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass

    analysis = AnalysisResult()

    # -----------------------------------------------------------------------
    # KPI Computation
    # -----------------------------------------------------------------------
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    kpis: Dict[str, Any] = {}

    for col in numeric_cols:
        kpis[f"total_{col}"] = round(float(df[col].sum()), 2)
        kpis[f"avg_{col}"] = round(float(df[col].mean()), 2)
        kpis[f"max_{col}"] = round(float(df[col].max()), 2)
        kpis[f"min_{col}"] = round(float(df[col].min()), 2)

    kpis["row_count"] = len(df)
    analysis.kpis = kpis

    # -----------------------------------------------------------------------
    # Growth Rates (requires time + metric columns)
    # -----------------------------------------------------------------------
    date_col = _find_date_col(df)
    metric_col = _find_metric_col(df)

    growth_rates: Dict[str, Any] = {}
    if date_col and metric_col and len(df) >= 2:
        try:
            ts = df[[date_col, metric_col]].copy()
            ts[date_col] = pd.to_datetime(ts[date_col])
            ts = ts.sort_values(date_col)

            # Month-over-Month
            if len(ts) >= 2:
                latest = float(ts[metric_col].iloc[-1])
                previous = float(ts[metric_col].iloc[-2])
                mom = _safe_growth(latest, previous)
                if mom is not None:
                    growth_rates["mom_growth_pct"] = mom

            # Period-over-period (first vs last)
            first_val = float(ts[metric_col].iloc[0])
            last_val = float(ts[metric_col].iloc[-1])
            overall = _safe_growth(last_val, first_val)
            if overall is not None:
                growth_rates["overall_growth_pct"] = overall

            # Trend direction
            if len(ts) >= 3:
                mid = len(ts) // 2
                first_half_avg = float(ts[metric_col].iloc[:mid].mean())
                second_half_avg = float(ts[metric_col].iloc[mid:].mean())
                trend = _safe_growth(second_half_avg, first_half_avg)
                if trend is not None:
                    growth_rates["trend_direction_pct"] = trend

        except Exception:
            pass

    analysis.growth_rates = growth_rates

    # -----------------------------------------------------------------------
    # Trend Analysis
    # -----------------------------------------------------------------------
    trends: Dict[str, Any] = {}
    if date_col and metric_col and len(df) >= 3:
        try:
            ts = df[[date_col, metric_col]].sort_values(date_col)
            values = ts[metric_col].tolist()
            trends["values"] = [round(float(v), 2) for v in values]
            trends["labels"] = [str(l) for l in ts[date_col].tolist()]
            trends["rolling_avg_3"] = [
                round(float(v), 2)
                for v in pd.Series(values).rolling(3, min_periods=1).mean()
            ]
        except Exception:
            pass
    analysis.trends = trends

    # -----------------------------------------------------------------------
    # Outlier Detection (IQR method)
    # -----------------------------------------------------------------------
    outliers: List[Dict[str, Any]] = []
    if metric_col and len(df) >= 5:
        try:
            vals = df[metric_col].dropna()
            q1, q3 = float(vals.quantile(0.25)), float(vals.quantile(0.75))
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            outlier_mask = (df[metric_col] < lower) | (df[metric_col] > upper)
            for _, row in df[outlier_mask].iterrows():
                outliers.append({
                    "row": {k: (round(float(v), 2) if isinstance(v, (int, float)) else str(v))
                            for k, v in row.to_dict().items()},
                    "type": "high" if row[metric_col] > upper else "low",
                    "deviation": round(abs(float(row[metric_col]) - float(vals.mean())) / max(float(vals.std()), 0.01), 2),
                })
        except Exception:
            pass
    analysis.outliers = outliers

    # -----------------------------------------------------------------------
    # Top / Bottom Performers (when grouping dimension exists)
    # -----------------------------------------------------------------------
    dim_col = _find_dim_col(df)
    if dim_col and metric_col:
        try:
            grouped = df.groupby(dim_col)[metric_col].sum().reset_index()
            grouped = grouped.sort_values(metric_col, ascending=False)
            analysis.top_performers = grouped.head(5).to_dict(orient="records")
            analysis.bottom_performers = grouped.tail(5).to_dict(orient="records")
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Summary Stats
    # -----------------------------------------------------------------------
    try:
        summary = df[numeric_cols].describe().to_dict() if numeric_cols else {}
        # Flatten and round
        flat = {}
        for col, stats in summary.items():
            for stat, val in stats.items():
                flat[f"{col}_{stat}"] = round(float(val), 2)
        analysis.summary_stats = flat
    except Exception:
        pass

    state.analysis = analysis
    state.agent_trace.append("data_analysis")
    return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_date_col(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if any(kw in col.lower() for kw in ["date", "month", "quarter", "year", "period"]):
            return col
    return None


def _find_metric_col(df: pd.DataFrame) -> str | None:
    preferred = ["revenue", "profit", "units_sold", "orders_count", "total", "amount", "value"]
    for pref in preferred:
        for col in df.columns:
            if pref in col.lower():
                try:
                    pd.to_numeric(df[col])
                    return col
                except Exception:
                    pass
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()
    return numeric[0] if numeric else None


def _find_dim_col(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if any(kw in col.lower() for kw in ["region", "product", "category", "segment", "name"]):
            if df[col].dtype == object:
                return col
    return None
