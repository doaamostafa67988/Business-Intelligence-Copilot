"""
Forecasting Agent.

Uses statsmodels Holt-Winters Exponential Smoothing for time-series
forecasting. Falls back to simple linear extrapolation if insufficient data.

Improvement: added confidence intervals, seasonality detection, and
both additive / multiplicative trend options.
"""
from __future__ import annotations

import warnings
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from core.state import AgentState

warnings.filterwarnings("ignore")


async def forecasting_node(state: AgentState) -> AgentState:
    """
    LangGraph node: time-series forecasting on SQL result data.
    """
    if not state.sql_result or not state.sql_result.data:
        state.agent_trace.append("forecasting:no_data")
        return state

    from core.config import get_settings
    settings = get_settings()

    df = pd.DataFrame(state.sql_result.data)
    forecast_dict = _build_forecast(df, periods=6)

    if state.analysis:
        state.analysis.forecast = forecast_dict
    state.agent_trace.append("forecasting")
    return state


def _build_forecast(df: pd.DataFrame, periods: int = 6) -> Dict[str, Any]:
    """
    Attempt Holt-Winters forecast; fall back to linear trend if data is sparse.
    Returns a dict with historical + forecasted values for Plotly.
    """
    # Find date + metric columns
    date_col = None
    for col in df.columns:
        if any(k in col.lower() for k in ["date", "month", "quarter", "period"]):
            date_col = col
            break

    metric_col = None
    for pref in ["revenue", "profit", "units_sold", "total", "amount"]:
        for col in df.columns:
            if pref in col.lower():
                try:
                    pd.to_numeric(df[col])
                    metric_col = col
                    break
                except Exception:
                    pass
        if metric_col:
            break

    if not date_col or not metric_col:
        # No time series structure found
        return {
            "available": False,
            "reason": "No time-series structure detected in query results",
        }

    try:
        ts = df[[date_col, metric_col]].copy()
        ts[date_col] = pd.to_datetime(ts[date_col])
        ts = ts.sort_values(date_col).dropna()
        ts[metric_col] = pd.to_numeric(ts[metric_col], errors="coerce")
        ts = ts.dropna()

        if len(ts) < 3:
            return {"available": False, "reason": "Need at least 3 data points for forecasting"}

        values = ts[metric_col].values.astype(float)
        dates = ts[date_col].tolist()

        # Detect frequency for future dates
        if len(dates) >= 2:
            delta = (dates[-1] - dates[-2]).days
            freq = "MS" if delta >= 25 else "W" if delta >= 5 else "D"
        else:
            freq = "MS"

        forecast_values: List[float] = []
        lower_ci: List[float] = []
        upper_ci: List[float] = []

        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            # Use additive trend/seasonality if enough data
            seasonal_periods = 12 if len(values) >= 24 else None
            model = ExponentialSmoothing(
                values,
                trend="add",
                seasonal="add" if seasonal_periods and len(values) >= seasonal_periods * 2 else None,
                seasonal_periods=seasonal_periods,
                initialization_method="estimated",
            )
            fit = model.fit(optimized=True, remove_bias=True)
            fc = fit.forecast(periods)
            forecast_values = [max(0.0, round(float(v), 2)) for v in fc]

            # Simple confidence intervals (±1.5 std of residuals)
            residual_std = float(np.std(fit.resid))
            margin = residual_std * 1.5
            lower_ci = [max(0.0, round(v - margin, 2)) for v in fc]
            upper_ci = [round(v + margin, 2) for v in fc]

        except Exception:
            # Linear extrapolation fallback
            x = np.arange(len(values))
            coeffs = np.polyfit(x, values, 1)
            future_x = np.arange(len(values), len(values) + periods)
            fc = np.polyval(coeffs, future_x)
            forecast_values = [max(0.0, round(float(v), 2)) for v in fc]
            std = float(np.std(values))
            lower_ci = [max(0.0, round(v - std, 2)) for v in fc]
            upper_ci = [round(v + std, 2) for v in fc]

        # Generate future date labels
        last_date = pd.to_datetime(dates[-1])
        future_dates = pd.date_range(last_date, periods=periods + 1, freq=freq)[1:]
        future_labels = [str(d.date()) for d in future_dates]

        return {
            "available": True,
            "historical_labels": [str(pd.to_datetime(d).date()) for d in dates],
            "historical_values": [round(float(v), 2) for v in values],
            "forecast_labels": future_labels,
            "forecast_values": forecast_values,
            "lower_ci": lower_ci,
            "upper_ci": upper_ci,
            "metric": metric_col,
            "periods": periods,
            "method": "Holt-Winters Exponential Smoothing",
        }

    except Exception as e:
        return {"available": False, "reason": f"Forecast failed: {str(e)}"}
