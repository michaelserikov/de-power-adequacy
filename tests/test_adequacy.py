import datetime as dt

import numpy as np
import pandas as pd
import pytest

from adequacy import copt, demand
from adequacy.copt import Tech


def test_distribution_two_units():
    p = copt.distribution({"a": Tech(200.0, 100.0, 0.1)}, step=100.0)
    assert p == pytest.approx([0.01, 0.18, 0.81])
    assert copt.mean_available(p, step=100.0) == pytest.approx(180.0)


def test_convolution_of_technologies():
    p = copt.distribution({"a": Tech(100.0, 100.0, 0.5), "b": Tech(100.0, 100.0, 0.5)}, step=100.0)
    assert p == pytest.approx([0.25, 0.5, 0.25])


def test_lolp_and_eens():
    p = np.array([0.01, 0.18, 0.81])                   # 0, 100, 200 MW
    d = pd.Series([50.0, 150.0, 250.0, 0.0])
    r = copt.lolp_eens(d, p, step=100.0)
    assert r["lolp"].tolist() == pytest.approx([0.01, 0.19, 1.0, 0.0])
    # EENS for D = 150: 0.01 * 150 + 0.18 * 50
    assert r["eens"].iloc[1] == pytest.approx(0.01 * 150 + 0.18 * 50)
    assert r["eens"].iloc[2] == pytest.approx(250 - 180)


def test_storage_shave_conserves_energy_and_power():
    d = pd.Series(np.tile(np.r_[np.full(20, 100.0), [130, 160, 150, 120]], 2))
    out = copt.storage_shave(d, power=40.0, energy=60.0)
    assert (d - out).sum() == pytest.approx(120.0, abs=1e-6)
    assert (d - out).max() <= 40.0 + 1e-6
    assert out.iloc[21] == pytest.approx(out.iloc[22], abs=1e-6)   # peak levelled


def test_storage_needs_headroom_to_refill():
    d = pd.Series(np.full(24, 100.0))
    out = copt.storage_shave(d, power=50.0, energy=100.0, headroom=pd.Series(np.zeros(24)))
    assert (d - out).sum() == pytest.approx(0.0, abs=1e-6)


def test_easter_and_holidays():
    assert demand.easter(2026) == dt.date(2026, 4, 5)
    assert demand.easter(1991) == dt.date(1991, 3, 31)
    h = demand.holidays([2026])
    assert dt.date(2026, 4, 6) in h and dt.date(2026, 5, 14) in h and len(h) == 9


def test_cop_values():
    # 7 C outside, radiators at 33 C: lift clipped to 26 K
    assert demand.cop(7.0, 33.0) == pytest.approx(0.85 * (6.08 - 0.0941 * 26 + 0.000464 * 26**2))
    assert demand.cop(-10.0, 50.0) < demand.cop(5.0, 35.0)


def test_heat_pump_load_energy():
    idx = pd.date_range("2001-01-01", periods=24 * 365 * 2, freq="h", tz="UTC")
    t = pd.Series(10 - 10 * np.cos(2 * np.pi * idx.day_of_year / 365.25), index=idx)
    hp = demand.heat_pump_load(t, 1.0)
    assert (hp > 0).all()
    assert hp[t.idxmin()] > hp[t.idxmax()]
    # heat delivered = electricity * COP averages HEAT_PER_PUMP per year; electricity is less
    assert hp.sum() / 2 < demand.HEAT_PER_PUMP
