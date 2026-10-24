"""Probabilistic adequacy: capacity outage probability table, LOLE and EENS.

Dispatchable plants are modelled as identical two-state units per technology (available or on
forced outage, independently), the classic capacity outage probability table (Billinton and
Allan, Reliability Evaluation of Power Systems). For every hour the loss-of-load probability is
P(available capacity < net demand), where net demand is load minus wind, solar, hydro, imports
and storage discharge. Summed over hours this gives the loss-of-load expectation (LOLE, hours
per year) and the expected energy not served (EENS).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import binom

STEP = 50.0  # MW, resolution of the capacity distribution


@dataclass(frozen=True)
class Tech:
    capacity: float   # MW installed
    unit: float       # MW per unit
    outage: float     # forced outage rate


def distribution(fleet: dict[str, Tech], step: float = STEP) -> np.ndarray:
    """Probability of each available capacity level 0, step, 2*step, ... (MW)."""
    p = np.array([1.0])
    for t in fleet.values():
        n = int(round(t.capacity / t.unit))
        if n == 0:
            continue
        k = np.arange(n + 1)
        pk = binom.pmf(k, n, 1.0 - t.outage)
        levels = np.round(k * t.capacity / n / step).astype(int)
        q = np.zeros(levels[-1] + 1)
        np.add.at(q, levels, pk)
        p = np.convolve(p, q)
    return p / p.sum()


def mean_available(p: np.ndarray, step: float = STEP) -> float:
    return float((np.arange(len(p)) * step * p).sum())


def lolp_eens(net_demand: pd.Series, p: np.ndarray, step: float = STEP) -> pd.DataFrame:
    """Loss-of-load probability and expected unserved energy (MWh) in each hour.

    LOLP = P(C < D); EENS = E[max(D - C, 0)] = D F(D) - E[C; C < D], with C the available capacity.
    """
    c = np.arange(len(p)) * step
    cdf = np.concatenate([[0.0], np.cumsum(p)])          # cdf[j] = P(C < c_j)
    cpart = np.concatenate([[0.0], np.cumsum(c * p)])    # E[C; C < c_j]
    d = net_demand.to_numpy(dtype=float)
    j = np.clip(np.ceil(d / step).astype(int), 0, len(p))  # levels strictly below d
    lolp = cdf[j]
    eens = np.maximum(d * lolp - cpart[j], 0.0)
    return pd.DataFrame({"lolp": lolp, "eens": eens}, index=net_demand.index)


def storage_shave(net_demand: pd.Series, power: float, energy: float, headroom: pd.Series | None = None,
                  efficiency: float = 0.75) -> pd.Series:
    """Discharge storage into the highest net-demand hours of each day (UTC days).

    Within a day the storage lowers the peak to a level theta with sum(min(power, D - theta)^+) =
    energy available that day. The energy available is the full reservoir only if it could be
    refilled the same day from spare dispatchable capacity: min(energy, efficiency * sum of
    min(power, headroom)^+), headroom being expected available capacity minus net demand.
    """
    d = net_demand.to_numpy(dtype=float)
    n = len(d) // 24 * 24
    D = d[:n].reshape(-1, 24)
    if headroom is None:
        e_day = np.full(D.shape[0], energy)
    else:
        h = headroom.to_numpy(dtype=float)[:n].reshape(-1, 24)
        e_day = np.minimum(energy, efficiency * np.clip(h, 0.0, power).sum(axis=1))
    lo = D.min(axis=1) - power
    hi = D.max(axis=1)
    for _ in range(40):                               # bisection on theta, all days at once
        mid = 0.5 * (lo + hi)
        used = np.clip(D - mid[:, None], 0.0, power).sum(axis=1)
        too_much = used > e_day
        lo = np.where(too_much, mid, lo)
        hi = np.where(too_much, hi, mid)
    out = d.copy()
    out[:n] = (D - np.clip(D - hi[:, None], 0.0, power)).ravel()
    return pd.Series(out, index=net_demand.index)
