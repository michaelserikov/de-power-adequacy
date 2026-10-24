"""Hourly electricity demand: a weather-dependent model of today's load plus additional heat pumps.

Load model: ordinary least squares of SMARD grid load on hour-of-day x day-type dummies, smooth
seasonal terms, heating degrees of the national mean temperature (smoothed to mimic the thermal
inertia of buildings), cooling degrees and irradiance (daylight lowers lighting load).

Heat pumps: each additional air-source heat pump delivers HEAT_PER_PUMP MWh of heat in an
average weather year; space heating (SPACE_SHARE) follows daily heating degrees below 15 C,
hot water is flat. Electricity = heat / COP, with the COP regression of When2Heat
(Ruhnau, Hirth and Praktiknjo 2019; github.com/oruhnau/when2heat, input/cop/cop_parameters.csv):
COP = 6.08 - 0.0941 dT + 0.000464 dT^2 for air-source pumps, temperature lift dT clipped at 15 K,
sink 40 - T (radiators) or 30 - 0.5 T (floor heating), 50 C for hot water, times 0.85 for
real-world operation (the correction used in When2Heat).
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

HEAT_BASE = 15.0       # C, heating threshold of the daily mean temperature
COOL_BASE = 22.0       # C
HEAT_PER_PUMP = 12.0   # MWh of heat per pump in an average year (assumption: a single-family home)
SPACE_SHARE = 0.8      # share of space heating in that heat; the rest is hot water
COP_AIR = (6.08, -0.0941, 0.000464)
COP_CORRECTION = 0.85
HOURS_PER_YEAR = 8766.0


def easter(year: int) -> dt.date:
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def holidays(years) -> set[dt.date]:
    """Nationwide public holidays in Germany."""
    out = set()
    for y in years:
        e = easter(y)
        out |= {dt.date(y, 1, 1), dt.date(y, 5, 1), dt.date(y, 10, 3), dt.date(y, 12, 25), dt.date(y, 12, 26)}
        out |= {e + dt.timedelta(days=k) for k in (-2, 1, 39, 50)}
    return out


def calendar(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Local hour, day type (0 working day, 1 Saturday, 2 Sunday or holiday), Christmas week, day of year."""
    local = index.tz_convert("Europe/Berlin")
    hol = holidays(range(local.year.min(), local.year.max() + 1))
    is_hol = pd.Series(local.date, index=index).isin(hol).values
    dtype = np.where(local.dayofweek == 5, 1, 0)
    dtype = np.where((local.dayofweek == 6) | is_hol, 2, dtype)
    xmas = ((local.month == 12) & (local.day >= 24)) | ((local.month == 1) & (local.day == 1))
    return pd.DataFrame({"hour": local.hour, "day_type": dtype, "xmas": np.asarray(xmas, dtype=int),
                         "doy": local.day_of_year}, index=index)


def features(t2m: pd.Series, ghi: pd.Series) -> pd.DataFrame:
    """Regressors of the load model; t2m and ghi are national means on the same hourly index."""
    cal = calendar(t2m.index)
    t_eff = t2m.ewm(halflife=24).mean()          # building inertia: about one day
    X = pd.get_dummies(cal["hour"].astype(str) + "_" + cal["day_type"].astype(str), prefix="hd", dtype=float)
    X.index = t2m.index
    X = X.reindex(columns=[f"hd_{h}_{d}" for h in range(24) for d in range(3)], fill_value=0.0)
    for k in (1, 2):
        X[f"s{k}"] = np.sin(2 * np.pi * k * cal["doy"] / 365.25)
        X[f"c{k}"] = np.cos(2 * np.pi * k * cal["doy"] / 365.25)
    X["xmas"] = cal["xmas"]
    X["hdd"] = (HEAT_BASE - t_eff).clip(lower=0)
    X["hdd_day"] = X["hdd"] * cal["hour"].between(7, 20).astype(float)
    X["cdd"] = (t2m - COOL_BASE).clip(lower=0)
    X["ghi"] = ghi
    return X


def fit_load(X: pd.DataFrame, load: pd.Series) -> LinearRegression:
    ok = X.notna().all(axis=1) & load.notna()
    return LinearRegression(fit_intercept=False).fit(X[ok].values, load[ok].values)


def predict_load(model: LinearRegression, X: pd.DataFrame) -> pd.Series:
    ok = X.notna().all(axis=1)
    out = pd.Series(np.nan, index=X.index)
    out[ok] = model.predict(X[ok].values)
    return out


def cop(t_source, t_sink):
    """Air-source heat pump COP (When2Heat regression with real-world correction)."""
    d = np.clip(np.asarray(t_sink, dtype=float) - np.asarray(t_source, dtype=float), 15.0, None)
    a, b, c = COP_AIR
    return COP_CORRECTION * (a + b * d + c * d**2)


def heat_pump_load(t2m: pd.Series, n_pumps: float) -> pd.Series:
    """Electric load in MW of n_pumps additional air-source heat pumps, hourly.

    Daily heating degrees are scaled so that the mean year of the sample delivers HEAT_PER_PUMP MWh
    of heat per pump; space heat goes half through radiators, half through floor heating and is
    spread evenly over the hours of the day.
    """
    if n_pumps == 0:
        return pd.Series(0.0, index=t2m.index, name="heat_pumps")
    day = t2m.index.tz_convert("Europe/Berlin").normalize()
    t_day = t2m.groupby(day).transform("mean")
    hdd = (HEAT_BASE - t_day).clip(lower=0)
    years = len(t2m) / HOURS_PER_YEAR
    space = SPACE_SHARE * HEAT_PER_PUMP * years * hdd / hdd.sum()   # MWh of heat per pump in each hour
    water = (1 - SPACE_SHARE) * HEAT_PER_PUMP / HOURS_PER_YEAR
    cop_space = 0.5 * cop(t2m, 40.0 - t2m) + 0.5 * cop(t2m, 30.0 - 0.5 * t2m)
    elec = space / cop_space + water / cop(t2m, 50.0)
    return (elec * n_pumps).rename("heat_pumps")
