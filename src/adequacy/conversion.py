"""Weather to national wind and solar capacity factors.

Physical point features as in github.com/michaelserikov/de-weather-to-power: wind at hub height
from the 100 m wind and the local shear through a generic power curve, and PV output from
irradiance with a cell-temperature correction. A non-negative linear regression on these
features (one weight per point) maps them to the national capacity factor of today's fleet.
The linear form is chosen on purpose: it extrapolates calmly to weather outside the training
years, which matters more here than the last percent of accuracy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from adequacy import weather

HUB_ONSHORE = 135.0   # m, typical hub height of the turbines added in the 2020s
HUB_OFFSHORE = 110.0  # m


def shear_exponent(ws100: pd.DataFrame, ws10: pd.DataFrame) -> pd.DataFrame:
    """Power-law shear exponent from 10 m and 100 m wind, clipped to a plausible range."""
    with np.errstate(divide="ignore", invalid="ignore"):
        a = np.log(ws100 / ws10) / np.log(10.0)
    return a.where(np.isfinite(a), 1 / 7).clip(0.05, 0.45)


def hub_wind(ws100: pd.DataFrame, ws10: pd.DataFrame, hub: float) -> pd.DataFrame:
    return ws100 * (hub / 100.0) ** shear_exponent(ws100, ws10)


def power_curve(v, cut_in: float = 3.0, rated: float = 11.5, cut_out: float = 25.0):
    """Generic turbine power curve as a capacity factor (0-1): cubic between cut-in and rated speed."""
    v = np.asarray(v, dtype=float)
    cf = (v**3 - cut_in**3) / (rated**3 - cut_in**3)
    cf = np.where(v < cut_in, 0.0, np.where(v >= rated, 1.0, cf))
    return np.where(v >= cut_out, 0.0, cf)


def pv_output(ghi: pd.DataFrame, t2m: pd.DataFrame, gamma: float = -0.004, k: float = 0.03) -> pd.DataFrame:
    """Relative PV output: irradiance times an efficiency factor for cell temperature T2m + k * GHI."""
    return (ghi / 1000.0) * (1.0 + gamma * (t2m + k * ghi - 25.0))


def physical(wx: dict[str, pd.DataFrame], tech: str) -> pd.DataFrame:
    """One physical feature per point for one technology."""
    if tech == "solar":
        pts = weather.SOLAR
        return pv_output(wx["shortwave_radiation"][pts], wx["temperature_2m"][pts])
    pts = weather.ONSHORE if tech == "onshore" else list(weather.OFFSHORE)
    hub = HUB_ONSHORE if tech == "onshore" else HUB_OFFSHORE
    v = hub_wind(wx["wind_speed_100m"][pts], wx["wind_speed_10m"][pts], hub)
    return pd.DataFrame(power_curve(v), index=v.index, columns=pts)


def fit(phys: pd.DataFrame, cf: pd.Series, solar: bool = False) -> LinearRegression:
    """Non-negative least squares (with free intercept) of the capacity factor on the point features.

    For solar only daylight hours are used; night hours are set to zero in predict().
    """
    ok = phys.notna().all(axis=1) & cf.notna()
    if solar:
        ok &= phys.sum(axis=1) > 0
    return LinearRegression(positive=True).fit(phys[ok].values, cf[ok].values)


def predict(model: LinearRegression, phys: pd.DataFrame, solar: bool = False) -> pd.Series:
    p = pd.Series(model.predict(phys.fillna(0.0).values), index=phys.index)
    if solar:
        p = p.where(phys.sum(axis=1) > 0, 0.0)
    return p.clip(0.0, 1.0)
