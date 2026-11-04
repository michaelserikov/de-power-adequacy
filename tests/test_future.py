"""Offline tests for the climate change factors, on synthetic data with known answers."""

import numpy as np
import pandas as pd
import pytest

from adequacy import future, weather
from adequacy.run import LAND


def _write(folder, model, exp, var, years, value):
    days = pd.date_range(f"{years[0]}-01-01", f"{years[1]}-12-31", freq="D")
    v = value(days) if callable(value) else np.full(len(days), float(value))
    pd.DataFrame({"year": days.year, "month": days.month, "day": days.day, var: v}).to_csv(
        folder / f"{model}_{exp}_{var}.csv", index=False)


@pytest.fixture
def cmip(tmp_path, monkeypatch):
    monkeypatch.setattr(future, "CMIP", tmp_path)
    return tmp_path


def _noise(seed, scale):
    return lambda d: np.random.default_rng(seed).normal(0, scale, len(d))


def test_temperature_shift_is_recovered_by_month_and_decile(cmip):
    _write(cmip, "M", "historical", "tas", (1991, 2014), lambda d: 280 + _noise(1, 3)(d))
    _write(cmip, "M", "ssp245", "tas", (2015, 2070),
           lambda d: 280 + _noise(1, 3)(d) + np.where(d.year >= 2041, 2.0, 0.0))
    table = future.change_table("M", "ssp245", "tas", ratio=False)
    assert table.shape == (12, len(future.QUANTILES))
    assert table.mean() == pytest.approx(2.0, abs=0.15)


def test_wind_change_is_a_ratio(cmip):
    _write(cmip, "M", "historical", "sfcWind", (1991, 2014), lambda d: 5 + _noise(2, 0.5)(d))
    _write(cmip, "M", "ssp245", "sfcWind", (2015, 2070),
           lambda d: (5 + _noise(2, 0.5)(d)) * np.where(d.year >= 2041, 0.9, 1.0))
    table = future.change_table("M", "ssp245", "sfcWind", ratio=True)
    assert table.mean() == pytest.approx(0.9, abs=0.01)


def test_series_keeps_the_requested_span_without_duplicates(cmip):
    _write(cmip, "M", "historical", "tas", (1991, 2015), 280)
    _write(cmip, "M", "ssp245", "tas", (2015, 2070), 281)
    s = future.series("M", "ssp245", "tas", future.HIST)
    assert s["year"].min() == 1991 and s["year"].max() == 2020
    assert not s.duplicated(["year", "month", "day"]).any()
    assert s.loc[s["year"] == 2015, "tas"].iloc[0] == 280    # historical wins the overlap


def test_daily_factor_follows_the_rank_within_the_month():
    idx = pd.date_range("2000-01-01", "2000-12-31 23:00", freq="h", tz="UTC")
    national = pd.Series(idx.dayofyear.to_numpy(dtype=float), index=idx)
    table = np.tile(np.linspace(1.0, 2.0, len(future.QUANTILES)), (12, 1))
    f = future.daily_factor(national, table)
    jan = f[f.index.month == 1]
    assert jan.iloc[0] == pytest.approx(1.0)      # coldest days take the lowest decile
    assert jan.iloc[-1] == pytest.approx(2.0)
    assert jan.is_monotonic_increasing


def _weather():
    idx = pd.date_range("2000-01-01", "2000-12-31 23:00", freq="h", tz="UTC")
    rng = np.random.default_rng(3)
    wind_points = list(dict.fromkeys(weather.ONSHORE + list(weather.OFFSHORE)))
    wx = {"temperature_2m": pd.DataFrame(rng.normal(10, 5, (len(idx), len(LAND))), index=idx, columns=LAND)}
    for key in ("wind_speed_100m", "wind_speed_10m"):
        wx[key] = pd.DataFrame(rng.uniform(2, 12, (len(idx), len(wind_points))), index=idx, columns=wind_points)
    wx["shortwave_radiation"] = pd.DataFrame(100.0, index=idx, columns=LAND)
    return wx


def test_zero_change_reproduces_the_weather():
    wx = _weather()
    n = len(future.QUANTILES)
    out = future.perturb(wx, np.zeros((12, n)), np.ones((12, n)))
    for key in ("temperature_2m", "wind_speed_100m", "wind_speed_10m"):
        pd.testing.assert_frame_equal(out[key], wx[key], check_freq=False)


def test_uniform_change_moves_temperature_and_wind_only():
    wx = _weather()
    n = len(future.QUANTILES)
    out = future.perturb(wx, np.full((12, n), 2.0), np.full((12, n), 0.9))
    assert ((out["temperature_2m"] - wx["temperature_2m"]).to_numpy() == pytest.approx(2.0))
    assert ((out["wind_speed_100m"] / wx["wind_speed_100m"]).to_numpy() == pytest.approx(0.9))
    assert ((out["wind_speed_10m"] / wx["wind_speed_10m"]).to_numpy() == pytest.approx(0.9))
    assert out["shortwave_radiation"] is wx["shortwave_radiation"]


def test_models_available_needs_all_six_files(cmip):
    for exp, span in (("historical", (1991, 1992)), ("ssp245", (2015, 2016)), ("ssp370", (2015, 2016))):
        for var in ("tas", "sfcWind"):
            _write(cmip, "Full", exp, var, span, 1.0)
    _write(cmip, "Part", "historical", "tas", (1991, 1992), 1.0)
    _write(cmip, "Part", "ssp245", "tas", (2015, 2016), 1.0)
    assert future.models_available() == ["Full"]
