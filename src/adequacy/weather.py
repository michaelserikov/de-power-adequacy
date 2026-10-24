"""Hourly ERA5 weather at a few points in Germany, 1991 onwards, from the Open-Meteo archive API.

The points are the subset of the 1-degree grid of github.com/michaelserikov/de-weather-to-power
whose weights in the non-negative weather-to-power regressions were largest: the 10 onshore wind
points and 8 solar points with the most learnt capacity (6 of the solar points are new) and the 4
offshore clusters that carry the offshore fit. On the 2025-26 holdout of that project, this subset
costs about 5% (onshore), 3% (solar) and 0% (offshore) in mean absolute error against all 52 points.

Data: Open-Meteo.com, CC BY 4.0; ERA5: Copernicus Climate Change Service. Times are UTC, wind in m/s.
Radiation is the mean over the preceding hour; wind and temperature are instantaneous.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

URL = "https://archive-api.open-meteo.com/v1/archive"
VARIABLES = ["wind_speed_100m", "wind_speed_10m", "shortwave_radiation", "direct_radiation", "temperature_2m"]
START, END = "1991-01-01", "2026-09-30"

ONSHORE = ["on_54.50_9.00", "on_51.50_11.00", "on_49.50_7.00", "on_51.50_9.00", "on_53.50_7.00",
           "on_53.50_10.00", "on_53.50_14.00", "on_52.50_14.00", "on_51.50_6.00", "on_49.50_9.00"]
SOLAR = ["on_48.50_10.00", "on_48.50_8.00", "on_49.50_9.00", "on_53.50_10.00", "on_50.50_11.00",
         "on_48.50_12.00", "on_50.50_7.00", "on_51.50_7.00"]
OFFSHORE = {"off_borkum": (53.95, 6.45), "off_sylt": (54.95, 7.10), "off_dolwin": (54.20, 6.60),
            "off_baltic_e": (54.80, 14.05)}


def points() -> dict[str, tuple[float, float]]:
    """Name -> (lat, lon) for every point that is downloaded."""
    pts = {}
    for name in dict.fromkeys(ONSHORE + SOLAR):
        _, la, lo = name.split("_")
        pts[name] = (float(la), float(lo))
    pts.update(OFFSHORE)
    return pts


_session = requests.Session()
_session.headers["User-Agent"] = "de-power-adequacy (research; github.com/michaelserikov)"


def _get(params: dict) -> dict:
    """GET with patience: the free API allows about 10,000 weighted calls a day, so a 429 waits and retries."""
    for attempt in range(200):
        try:
            r = _session.get(URL, params=params, timeout=180)
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(60)
            continue
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:                        # truncated body: try again
                time.sleep(30)
                continue
        if r.status_code in (429, 500, 502, 503, 504):
            reason = r.text[:120]
            wait = 30
            if r.status_code == 429:
                wait = 65 if "Minutely" in reason else 600 if "Hourly" in reason else 1800
            print(f"  {r.status_code}, waiting {wait} s ({reason[:60]})", flush=True)
            time.sleep(wait)
            continue
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")
    raise RuntimeError("gave up")


def _chunks(start: str, end: str, years: int = 5) -> list[tuple[str, str]]:
    out, y0 = [], int(start[:4])
    while y0 <= int(end[:4]):
        y1 = min(y0 + years - 1, int(end[:4]))
        out.append((max(start, f"{y0}-01-01"), min(end, f"{y1}-12-31")))
        y0 = y1 + 1
    return out


def load_point(name: str, lat: float, lon: float, cache_dir: Path) -> pd.DataFrame:
    """Hourly ERA5 at one point, START to END, cached in five-year pieces under cache_dir/<name>/."""
    parts = []
    for a, b in _chunks(START, END):
        path = cache_dir / name / f"{a[:4]}_{b[:4]}.csv"
        if not path.exists():
            doc = _get({"latitude": lat, "longitude": lon, "start_date": a, "end_date": b, "models": "era5",
                        "hourly": ",".join(VARIABLES), "timezone": "UTC", "wind_speed_unit": "ms"})
            h = doc["hourly"]
            df = pd.DataFrame({v: h[v] for v in VARIABLES}, index=pd.to_datetime(h["time"], utc=True))
            df.index.name = "ts_utc"
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(path)
        parts.append(pd.read_csv(path, index_col=0, parse_dates=True))
    return pd.concat(parts).astype(float)


def to_interval_means(df: pd.DataFrame) -> pd.DataFrame:
    """Hour [t, t+1) labelled t, as in SMARD: radiation at t+1 is already the mean over [t, t+1);
    instantaneous wind and temperature are averaged over the two ends of the hour."""
    out = pd.DataFrame(index=df.index)
    for v in df.columns:
        if v in ("shortwave_radiation", "direct_radiation"):
            out[v] = df[v].shift(-1)
        else:
            out[v] = (df[v] + df[v].shift(-1)) / 2
    return out


def load_all(cache_dir: Path) -> dict[str, pd.DataFrame]:
    """Variable -> wide frame (hour x point), aligned to SMARD hours."""
    per_point = {n: to_interval_means(load_point(n, la, lo, cache_dir)) for n, (la, lo) in points().items()}
    return {v: pd.DataFrame({n: df[v] for n, df in per_point.items()}) for v in VARIABLES}
