"""Adequacy under future climate: ERA5 weather years perturbed with CMIP6 change factors (v0.2).

For each model, daily Germany-mean temperature and near-surface wind are compared between
1991-2020 and 2041-2070, by calendar month and decile. Every ERA5 day then gets the change for its
own month and decile, applied to all hours and points. Temperature changes are added, wind changes
multiplied. Solar radiation stays unchanged. The 2030 power system and its demand level stay fixed,
so the result isolates the climate signal; it is not a forecast of 2050.

    python -m adequacy.future
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from adequacy import conversion, demand, weather
from adequacy.run import (FIT_END, FIT_START, LAND, RAW, TABLES, TECHS, build_base, evaluate, firm_needed, fit_models,
                          load_inputs, scenarios)

CMIP = RAW / "cmip6"
HIST, FUT = (1991, 2020), (2041, 2070)
QUANTILES = np.linspace(0.05, 0.95, 10)


def read_model(model: str, exp: str, var: str) -> pd.DataFrame:
    return pd.read_csv(CMIP / f"{model}_{exp}_{var}.csv")


def series(model: str, exp: str, var: str, span: tuple[int, int]) -> pd.DataFrame:
    frames = [read_model(model, "historical", var), read_model(model, exp, var)]
    d = pd.concat(frames, ignore_index=True).drop_duplicates(["year", "month", "day"])
    return d[(d["year"] >= span[0]) & (d["year"] <= span[1])]


def change_table(model: str, exp: str, var: str, ratio: bool) -> np.ndarray:
    """Change by calendar month (rows) and decile mid-point (columns)."""
    h, f = series(model, exp, var, HIST), series(model, exp, var, FUT)
    out = np.zeros((12, len(QUANTILES)))
    for m in range(1, 13):
        qh = h.loc[h["month"] == m, var].quantile(QUANTILES).to_numpy()
        qf = f.loc[f["month"] == m, var].quantile(QUANTILES).to_numpy()
        out[m - 1] = qf / qh if ratio else qf - qh
    return out


def daily_factor(national: pd.Series, table: np.ndarray) -> pd.Series:
    """Change for each day from its month and rank in that month, interpolated between deciles."""
    daily = national.groupby(national.index.floor("D")).mean()
    factor = pd.Series(index=daily.index, dtype=float)
    for m in range(1, 13):
        part = daily[daily.index.month == m]
        rank = (part.rank() - 0.5) / len(part)
        factor[part.index] = np.interp(rank, QUANTILES, table[m - 1])
    return factor


def perturb(wx: dict, dt_table: np.ndarray, wind_table: np.ndarray) -> dict:
    out = dict(wx)
    t = wx["temperature_2m"]
    days = t.index.floor("D")
    dt = daily_factor(t[LAND].mean(axis=1), dt_table).reindex(days).to_numpy()
    out["temperature_2m"] = t.add(dt, axis=0)
    wnd = wx["wind_speed_100m"]
    w = daily_factor(wx["wind_speed_10m"][weather.ONSHORE].mean(axis=1), wind_table).reindex(days).to_numpy()
    for key in ("wind_speed_100m", "wind_speed_10m"):
        out[key] = wx[key].mul(w, axis=0)
    return out


def result_row(name, s, base) -> dict:
    r = evaluate(s, base)
    by_year = r.groupby("year")[["lolp", "eens"]].sum()
    winter = r[r.index.month.isin([12, 1, 2])]["lolp"].sum() / max(r["lolp"].sum(), 1e-9)
    return {"case": name, "lole": by_year["lolp"].mean(), "eens_gwh": by_year["eens"].mean() / 1000,
            "firm_needed_gw": firm_needed(s, base) / 1000, "winter_share": winter,
            "t2m_djf": base.loc[base.index.month.isin([12, 1, 2]), "t2m"].mean(),
            "cf_onshore_djf": base.loc[base.index.month.isin([12, 1, 2]), "cf_onshore"].mean()}


def models_available() -> list[str]:
    names = {p.name.split("_")[0] for p in CMIP.glob("*_ssp245_tas.csv")}
    keep = []
    for n in sorted(names):
        if all((CMIP / f"{n}_{e}_{v}.csv").exists() for e in ("historical", "ssp245", "ssp370") for v in ("tas", "sfcWind")):
            keep.append(n)
    return keep


def main() -> dict:
    wx, obs, cap = load_inputs()
    check, cf, load, t2m, coef = fit_models(wx, obs, cap)
    base = build_base(wx, obs, cf, load, t2m)
    S, _ = scenarios(base)
    cases = {"2030, no coal": S["2030, no coal"], "central": S["2030, no coal, +3 m heat pumps"]}
    idx = wx["temperature_2m"].index
    full = (idx >= pd.Timestamp(FIT_START, tz="UTC")) & (idx <= pd.Timestamp(FIT_END + " 23:00", tz="UTC"))
    fitted = {t: conversion.fit(conversion.physical(wx, t)[full], (obs[t] / cap[t])[full], solar=t == "solar") for t in TECHS}
    ghi = wx["shortwave_radiation"][weather.SOLAR].mean(axis=1)
    load_fit = demand.fit_load(demand.features(t2m, ghi)[full], obs["load"][full])

    rows = []
    for key, s in cases.items():
        rows.append({"model": "ERA5", "exp": "observed", **result_row(key, s, base)})
    for model in models_available():
        for exp in ("ssp245", "ssp370"):
            w2 = perturb(wx, change_table(model, exp, "tas", False), change_table(model, exp, "sfcWind", True))
            cf2 = {t: conversion.predict(fitted[t], conversion.physical(w2, t), solar=t == "solar") for t in TECHS}
            t2 = w2["temperature_2m"][LAND].mean(axis=1).rename("t2m")
            load2 = demand.predict_load(load_fit, demand.features(t2, ghi))
            b2 = build_base(w2, obs, cf2, load2, t2)
            for key, s in cases.items():
                row = {"model": model, "exp": exp, **result_row(key, s, b2)}
                rows.append(row)
                print({k: round(v, 3) if isinstance(v, float) else v for k, v in row.items()}, flush=True)
    t = pd.DataFrame(rows)
    t.to_csv(TABLES / "future_climate_by_model.csv", index=False, float_format="%.3f")
    fut = t[t["exp"] != "observed"].groupby(["case", "exp"])
    cols = ["lole", "eens_gwh", "firm_needed_gw", "t2m_djf", "cf_onshore_djf", "winter_share"]
    summ = fut[cols].median().round(2).join(fut["lole"].agg(["min", "max", "count"]).round(1).add_suffix("_lole"))
    summ = summ.join(fut["firm_needed_gw"].agg(["min", "max"]).round(1).add_suffix("_firm"))
    summ.to_csv(TABLES / "future_climate_summary.csv")
    print(t[t["exp"] == "observed"].round(3).to_string(index=False))
    print(summ.to_string())
    return {"models": models_available()}


if __name__ == "__main__":
    print(json.dumps(main()))
