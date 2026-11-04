"""Daily Germany-mean temperature and near-surface wind from CMIP6 (Pangeo cloud copy).

Writes one CSV per model, experiment and variable to data/raw/cmip6/. Finished files are skipped.
Used only for change factors between 1991-2020 and 2041-2070, never as absolute weather.
"""
import sys
from pathlib import Path

import gcsfs
import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "cmip6"
CATALOG = "https://storage.googleapis.com/cmip6/pangeo-cmip6.csv"
BOX = dict(lat=(47.5, 54.5), lon=(6.0, 15.0))
MEMBER_ORDER = ["r1i1p1f1", "r1i1p1f2", "r1i1p2f1"]
SPANS = {"historical": ("1991-01-01", "2014-12-31"), "ssp245": ("2015-01-01", "2070-12-31"), "ssp370": ("2015-01-01", "2070-12-31")}
VARS = ["tas", "sfcWind"]
MAX_MODELS = 12


def pick(cat):
    c = cat[(cat.table_id == "day") & cat.variable_id.isin(VARS) & cat.experiment_id.isin(SPANS)]
    models = []
    for model, g in c.groupby("source_id"):
        for member in MEMBER_ORDER:
            m = g[g.member_id == member]
            if len(m.groupby(["experiment_id", "variable_id"])) == len(SPANS) * len(VARS):
                models.append((model, member))
                break
    return c, models


def box_mean(store, var, span):
    fs = gcsfs.GCSFileSystem(token="anon")
    ds = xr.open_zarr(fs.get_mapper(store), consolidated=True, decode_times=True, use_cftime=True)
    da = ds[var]
    lat, lon = "lat" if "lat" in da.coords else "latitude", "lon" if "lon" in da.coords else "longitude"
    lon_values = ((da[lon] + 180) % 360) - 180
    if da[lat].ndim != 1:
        raise ValueError("curvilinear grid")
    da = da.assign_coords({lon: lon_values}).sortby(lon).sortby(lat)
    da = da.sel({lat: slice(*BOX["lat"]), lon: slice(*BOX["lon"])}).sel(time=slice(*span))
    w = np.cos(np.deg2rad(da[lat]))
    s = da.weighted(w).mean([lat, lon]).compute()
    t = s["time"].to_index()
    return pd.DataFrame({"year": [x.year for x in t], "month": [x.month for x in t], "day": [x.day for x in t], var: s.to_numpy()})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cat = pd.read_csv(CATALOG)
    c, models = pick(cat)
    print(len(models), "models", [m for m, _ in models], flush=True)
    done = 0
    for model, member in models:
        if done >= MAX_MODELS:
            break
        ok = True
        for exp, span in SPANS.items():
            for var in VARS:
                path = OUT / f"{model}_{exp}_{var}.csv"
                if path.exists():
                    continue
                rows = c[(c.source_id == model) & (c.member_id == member) & (c.experiment_id == exp) & (c.variable_id == var)]
                try:
                    box_mean(rows.iloc[-1].zstore, var, span).to_csv(path, index=False)
                    print("ok", path.name, flush=True)
                except Exception as err:
                    print("fail", model, exp, var, str(err)[:120], flush=True)
                    ok = False
        done += ok
    print("finished models", done, flush=True)


if __name__ == "__main__":
    sys.exit(main())
