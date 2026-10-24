"""Installed capacity in Germany from Energy-Charts (Fraunhofer ISE), GW in the source, MW here.

Monthly wind and solar capacity (to turn observed generation into capacity factors) and the
yearly fleet of every technology, including the EEG 2023 and WindSeeG targets for 2030:
https://api.energy-charts.info/installed_power?country=de&time_step=monthly|yearly (CC BY 4.0).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests

URL = "https://api.energy-charts.info/installed_power"
WIND_SOLAR = {"onshore": "Wind onshore", "offshore": "Wind offshore", "solar": "Solar AC"}


def _doc(cache: Path, time_step: str) -> dict:
    if not cache.exists():
        r = requests.get(URL, params={"country": "de", "time_step": time_step,
                                      "installation_decommission": "false"}, timeout=60)
        r.raise_for_status()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(r.text, encoding="utf-8")
    return json.loads(cache.read_text(encoding="utf-8"))


def monthly(cache: Path) -> pd.DataFrame:
    """Monthly wind and solar (AC) capacity in MW, indexed by the first day of the month (UTC)."""
    doc = _doc(cache, "monthly")
    idx = pd.to_datetime(doc["time"], format="%m.%Y").tz_localize("UTC")
    by_name = {p["name"]: p["data"] for p in doc["production_types"]}
    return pd.DataFrame({k: pd.Series(by_name[v], index=idx, dtype=float) * 1000.0 for k, v in WIND_SOLAR.items()})


def hourly(monthly_mw: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Capacity on each hour: month-end values, linearly interpolated between month ends."""
    m = monthly_mw.copy()
    m.index = m.index + pd.offsets.MonthEnd(0) + pd.Timedelta(hours=23)
    grid = m.reindex(m.index.union(index)).interpolate(method="time").ffill().bfill()
    return grid.reindex(index)


def yearly(cache: Path, year: str) -> dict[str, float]:
    """Every technology's capacity in MW in one year (None where the source has no value)."""
    doc = _doc(cache, "yearly")
    i = doc["time"].index(year)
    return {p["name"]: (None if p["data"][i] is None else p["data"][i] * 1000.0) for p in doc["production_types"]}
