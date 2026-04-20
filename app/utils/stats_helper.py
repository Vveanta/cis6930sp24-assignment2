"""Rolling stats and simple anomaly highlights for incident time series."""
from __future__ import annotations

from typing import Any

import pandas as pd


def rows_to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "Incident Time" not in df.columns:
        return df
    df["_dt"] = pd.to_datetime(df["Incident Time"], format="%m/%d/%Y %H:%M", errors="coerce")
    return df


def compute_anomaly_alerts(rows: list[dict[str, Any]], window: int = 7) -> list[str]:
    """
    Compare the most recent complete window to the prior window of the same length.
    Flags large spikes in daily incident counts (simple heuristic).
    """
    df = rows_to_dataframe(rows)
    if df.empty or "_dt" not in df.columns or df["_dt"].notna().sum() < window * 2:
        return []

    daily = (
        df.dropna(subset=["_dt"])
        .assign(day=lambda x: x["_dt"].dt.normalize())
        .groupby("day", as_index=False)
        .size()
        .rename(columns={"size": "count"})
        .sort_values("day")
    )
    if len(daily) < window * 2:
        return []

    counts = daily["count"].astype(float).tolist()
    recent = counts[-window:]
    prior = counts[-window * 2 : -window]
    if not prior or not recent:
        return []

    avg_prior = sum(prior) / len(prior)
    avg_recent = sum(recent) / len(recent)
    if avg_prior < 1:
        return []

    pct = (avg_recent - avg_prior) / avg_prior * 100.0
    alerts: list[str] = []
    if pct >= 25:
        alerts.append(
            f"In the last {window} days with data, daily incidents averaged "
            f"{avg_recent:.1f} vs {avg_prior:.1f} in the previous {window} days "
            f"({pct:+.0f}% vs prior period)."
        )
    elif pct <= -25:
        alerts.append(
            f"Incident volume looks lower recently: last {window} days averaged "
            f"{avg_recent:.1f} per day vs {avg_prior:.1f} in the prior {window} days "
            f"({pct:+.0f}% vs prior period)."
        )
    return alerts


def summary_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    df = rows_to_dataframe(rows)
    if df.empty:
        return {"total": 0}
    out: dict[str, Any] = {"total": len(df)}
    if "_dt" in df.columns and df["_dt"].notna().any():
        s = df["_dt"].min()
        e = df["_dt"].max()
        out["date_min"] = s.strftime("%Y-%m-%d") if pd.notna(s) else None
        out["date_max"] = e.strftime("%Y-%m-%d") if pd.notna(e) else None
    if "Nature" in df.columns:
        out["top_nature"] = (
            df["Nature"].value_counts().head(1).index.tolist()[0]
            if len(df["Nature"].value_counts()) > 0
            else None
        )
    return out
