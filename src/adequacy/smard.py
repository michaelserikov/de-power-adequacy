"""Hourly German load, wind, solar and hydro generation from SMARD (Bundesnetzagentur), region DE.

Weekly JSON chunks from https://www.smard.de/app/chart_data, cached on disk (CC BY 4.0).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

BASE = "https://www.smard.de/app/chart_data"
REGION = "DE"

SERIES = {
    "load": 410,       # total electricity consumption (grid load), MWh per hour
    "onshore": 4067,   # actual generation, wind onshore
    "offshore": 1225,  # actual generation, wind offshore
    "solar": 4068,     # actual generation, photovoltaics
    "hydro": 1226,     # actual generation, hydropower (run-of-river and reservoirs)
}

_session = requests.Session()
_session.headers["User-Agent"] = "de-power-adequacy (research; github.com/michaelserikov)"


def _get_json(url: str, retries: int = 5) -> dict:
    for attempt in range(retries):
        try:
            r = _session.get(url, timeout=30)
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(5)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
    raise RuntimeError(f"failed: {url}")


def parse_chunk(doc: dict) -> pd.Series:
    rows = [(t, v) for t, v in doc.get("series", []) if v is not None]
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows, columns=["ts_ms", "value"])
    return pd.Series(df["value"].values, index=pd.to_datetime(df["ts_ms"], unit="ms", utc=True), dtype=float)


def load_series(name: str, start: str, end: str, cache_dir: Path) -> pd.Series:
    """Hourly series from start to end (inclusive dates, UTC); complete weeks are cached."""
    fid = SERIES[name]
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    week = pd.Timedelta(days=7)
    folder = cache_dir / f"{fid}_{REGION}"
    folder.mkdir(parents=True, exist_ok=True)
    parts = []
    for ts in _get_json(f"{BASE}/{fid}/{REGION}/index_hour.json")["timestamps"]:
        t0 = pd.Timestamp(ts, unit="ms", tz="UTC")
        if t0 + week <= start_ts or t0 >= end_ts:
            continue
        path = folder / f"{ts}.json"
        if path.exists():
            doc = json.loads(path.read_text(encoding="utf-8"))
        else:
            doc = _get_json(f"{BASE}/{fid}/{REGION}/{fid}_{REGION}_hour_{ts}.json")
            if t0 + week < pd.Timestamp.now(tz="UTC"):
                path.write_text(json.dumps(doc), encoding="utf-8")
            time.sleep(0.1)
        parts.append(parse_chunk(doc))
    s = pd.concat(parts)
    s = s[~s.index.duplicated()].sort_index()
    return s[(s.index >= start_ts) & (s.index < end_ts)].rename(name)


def load_all(start: str, end: str, cache_dir: Path) -> pd.DataFrame:
    return pd.concat([load_series(n, start, end, cache_dir) for n in SERIES], axis=1)
