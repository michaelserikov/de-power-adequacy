"""Resource adequacy of the German power system across 35 weather years (1991-2025).

Pipeline:
1. Fit weather-to-capacity-factor models (wind onshore, offshore, solar) and a weather-dependent
   load model on 2024 to September 2025; check them on October 2025 to September 2026; refit on
   the whole period.
2. Run every weather year 1991-2025 through today's (and a 2030) fleet: hourly load, extra heat
   pumps, wind, solar and hydro.
3. Capacity outage probability table of the dispatchable fleet -> LOLE and EENS per weather year,
   the firm capacity needed for the German reliability standard (2.77 h per year), the capacity
   credit (ELCC) of wind, solar and storage, and the weather behind the loss-of-load hours.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy import stats

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from adequacy import capacity, conversion, copt, demand, smard, weather  # noqa: E402
from adequacy.copt import Tech  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
TABLES = ROOT / "results" / "tables"
FIGS = ROOT / "results" / "figures"

FIT_START, HOLDOUT_START, FIT_END = "2024-01-01", "2025-10-01", "2026-09-30"
YEARS = list(range(1991, 2026))
STANDARD = 2.77            # h per year, German reliability standard (ACER, CHEST data item 283)
TECHS = ("onshore", "offshore", "solar")
LAND = list(dict.fromkeys(weather.ONSHORE + weather.SOLAR))

# Unit sizes and forced outage rates: illustrative assumptions, varied in the sensitivity runs.
UNIT = {"lignite": (500.0, 0.07), "hard_coal": (500.0, 0.07), "gas": (250.0, 0.05), "oil": (100.0, 0.10),
        "other": (50.0, 0.10), "biomass": (10.0, 0.10), "new_gas": (250.0, 0.05)}
PUMPED_HOURS = 4.0         # pumped storage energy per unit of power (about 40 GWh for 9.9 GW)
AC_PER_DC = None           # set from Energy-Charts: solar AC / DC capacity in 2026


@dataclass
class Scenario:
    name: str
    firm: dict[str, float]                  # MW per dispatchable technology
    res: dict[str, float]                   # MW wind onshore, offshore, solar (AC)
    heat_pumps: float = 0.0                 # additional heat pumps (number)
    imports: float = 0.0                    # MW of imports assumed available in every hour
    storage: list[tuple[float, float]] = field(default_factory=list)  # (power MW, energy MWh)
    outage_scale: float = 1.0


def fleet(s: Scenario, extra_firm: float = 0.0) -> dict[str, Tech]:
    firm = dict(s.firm)
    firm["new_gas"] = firm.get("new_gas", 0.0) + extra_firm
    return {k: Tech(v, UNIT[k][0], min(UNIT[k][1] * s.outage_scale, 0.5)) for k, v in firm.items() if v > 0}


def net_demand(s: Scenario, base: pd.DataFrame, p: np.ndarray, res_scale: dict | None = None) -> pd.Series:
    """Load + heat pumps - wind - solar - hydro - imports, after storage discharge (MW)."""
    res = {k: v * (res_scale or {}).get(k, 1.0) for k, v in s.res.items()}
    d = base["load"] + base["hp_per_pump"] * s.heat_pumps - base["hydro"] - s.imports
    for t in TECHS:
        d = d - base[f"cf_{t}"] * res[t]
    headroom = copt.mean_available(p) - d
    for power, energy in s.storage:
        d = copt.storage_shave(d, power, energy, headroom=headroom)
        headroom = copt.mean_available(p) - d
    return d


def evaluate(s: Scenario, base: pd.DataFrame, extra_firm: float = 0.0, res_scale: dict | None = None) -> pd.DataFrame:
    p = copt.distribution(fleet(s, extra_firm))
    r = copt.lolp_eens(net_demand(s, base, p, res_scale), p)
    r["year"] = base["year"]
    return r


def summary(r: pd.DataFrame) -> dict:
    by_year = r.groupby("year")[["lolp", "eens"]].sum()
    return {"LOLE h/yr": by_year["lolp"].mean(), "EENS GWh/yr": by_year["eens"].mean() / 1000,
            "worst year": int(by_year["lolp"].idxmax()) if by_year["lolp"].max() > 0.005 else "-",
            "LOLE worst year": by_year["lolp"].max(),
            "years with LOLE > 2.77": int((by_year["lolp"] > STANDARD).sum())}


def firm_needed(s: Scenario, base: pd.DataFrame, target: float = STANDARD) -> float:
    """New firm capacity (MW, gas units) at which mean LOLE equals the target (bisection)."""
    def lole(x):
        return evaluate(s, base, extra_firm=x).groupby("year")["lolp"].sum().mean()
    if lole(0.0) <= target:
        return 0.0
    lo, hi = 0.0, 5000.0
    while lole(hi) > target:
        lo, hi = hi, hi * 2
    for _ in range(14):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if lole(mid) > target else (lo, mid)
    return hi


def capacity_credit(s: Scenario, base: pd.DataFrame, x0: float, added: float, res_scale: dict | None = None) -> float:
    """Equivalent load-carrying capability in % of `added` MW.

    Start from the scenario made adequate with x0 MW of new firm capacity. With the extra resource
    in place, remove firm capacity until LOLE is back at the standard; the firm capacity removed is
    the resource's capacity credit.
    """
    def lole(remove):
        return evaluate(s, base, extra_firm=x0 - remove, res_scale=res_scale).groupby("year")["lolp"].sum().mean()
    lo, hi = 0.0, min(added, x0)
    if lole(hi) <= STANDARD:
        return hi / added * 100
    for _ in range(14):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if lole(mid) <= STANDARD else (lo, mid)
    return lo / added * 100


# ---------------------------------------------------------------------------------------------
def load_inputs():
    wx = weather.load_all(RAW / "era5")
    obs = smard.load_all("2015-01-05", FIT_END, RAW / "smard")
    idx = wx["temperature_2m"].index
    obs = obs.reindex(idx)
    cap = capacity.hourly(capacity.monthly(RAW / "installed_power_monthly.json"), idx)
    return wx, obs, cap


def mae_pct(a: pd.Series, b: pd.Series) -> float:
    return float((a - b).abs().mean() * 100)


def fit_models(wx, obs, cap):
    """Weather-to-CF and load models; holdout check, then refit on the full fitting period."""
    idx = wx["temperature_2m"].index
    fit = (idx >= pd.Timestamp(FIT_START, tz="UTC")) & (idx < pd.Timestamp(HOLDOUT_START, tz="UTC"))
    hold = (idx >= pd.Timestamp(HOLDOUT_START, tz="UTC")) & (idx <= pd.Timestamp(FIT_END + " 23:00", tz="UTC"))
    full = fit | hold
    rows, cf, models = [], {}, {}
    for t in TECHS:
        phys = conversion.physical(wx, t)
        y = obs[t] / cap[t]
        solar = t == "solar"
        m = conversion.fit(phys[fit], y[fit], solar=solar)
        pred = conversion.predict(m, phys[hold], solar=solar)
        yh = y[hold]
        ok = yh.notna()
        daily = pd.concat([pred[ok], yh[ok]], axis=1).resample("D").mean()
        rows.append({"model": f"{t} capacity factor", "MAE (% of capacity)": mae_pct(pred[ok], yh[ok]),
                     "mean modelled": pred[ok].mean() * 100, "mean observed": yh[ok].mean() * 100,
                     "daily correlation": daily.corr().iloc[0, 1]})
        models[t] = conversion.fit(phys[full], y[full], solar=solar)
        cf[t] = conversion.predict(models[t], phys, solar=solar)
    t2m = wx["temperature_2m"][LAND].mean(axis=1).rename("t2m")   # national mean over the 16 land points
    ghi = wx["shortwave_radiation"][weather.SOLAR].mean(axis=1)
    X = demand.features(t2m, ghi)
    lm = demand.fit_load(X[fit], obs["load"][fit])
    pl = demand.predict_load(lm, X[hold])
    ok = obs["load"][hold].notna()
    err = (pl[ok] - obs["load"][hold][ok]).abs()
    rows.append({"model": "load (MW)", "MAE (% of capacity)": np.nan, "mean modelled": pl[ok].mean(),
                 "mean observed": obs["load"][hold][ok].mean(), "daily correlation":
                 pd.concat([pl[ok], obs["load"][hold][ok]], axis=1).resample("D").mean().corr().iloc[0, 1],
                 "MAE (MW)": err.mean(), "MAPE (%)": (err / obs["load"][hold][ok]).mean() * 100})
    lm = demand.fit_load(X[full], obs["load"][full])
    coef = pd.Series(lm.coef_, index=X.columns)
    load = demand.predict_load(lm, X)
    return pd.DataFrame(rows), cf, load, t2m, coef


def build_base(wx, obs, cf, load, t2m) -> pd.DataFrame:
    """Hourly inputs for the weather years 1991-2025 at today's demand level."""
    keep = (load.index.year >= YEARS[0]) & (load.index.year <= YEARS[-1])
    idx = load.index[keep]
    hydro = obs["hydro"]["2023":"2025"]
    hydro_month = hydro.groupby(hydro.index.month).mean()
    base = pd.DataFrame({
        "load": load[idx], "hp_per_pump": demand.heat_pump_load(t2m[idx], 1.0),
        "hydro": hydro_month.reindex(idx.month).to_numpy(), "t2m": t2m[idx],
        "cf_onshore": cf["onshore"][idx], "cf_offshore": cf["offshore"][idx], "cf_solar": cf["solar"][idx],
        "year": idx.year}, index=idx)
    assert base.notna().all().all(), base.isna().sum()
    return base


def interannual_check(cf, obs, cap) -> pd.DataFrame:
    """Modelled (today's fleet) vs observed annual capacity factors, 2015-2025."""
    out = {}
    for t in ("onshore", "solar"):
        o = (obs[t] / cap[t])["2015":"2025"]
        m = cf[t].reindex(o.index)
        ok = o.notna()
        out[(t, "observed")] = o[ok].groupby(o[ok].index.year).mean() * 100
        out[(t, "modelled")] = m[ok].groupby(m[ok].index.year).mean() * 100
    df = pd.DataFrame(out)
    return df


def scenarios(base: pd.DataFrame) -> dict[str, Scenario]:
    y26 = capacity.yearly(RAW / "installed_power_yearly.json", "2026")
    y30 = capacity.yearly(RAW / "installed_power_yearly.json", "2030")
    ac_per_dc = y26["Solar AC"] / y26["Solar DC"]
    firm26 = {"lignite": y26["Fossil brown coal / lignite"], "hard_coal": y26["Fossil hard coal"],
              "gas": y26["Fossil gas"], "oil": y26["Fossil oil"], "other": y26["Other, non-renewable"],
              "biomass": y26["Biomass"]}
    res26 = {"onshore": y26["Wind onshore"], "offshore": y26["Wind offshore"], "solar": y26["Solar AC"]}
    res30 = {"onshore": y30["Wind onshore planned (EEG 2023)"], "offshore": y30["Wind offshore planned (WindSeeG)"],
             "solar": y30["Solar planned (EEG 2023)"] * ac_per_dc}
    pumped = [(y26["Hydro pumped storage"], y26["Hydro pumped storage"] * PUMPED_HOURS)]
    kvbg = dict(firm26, lignite=9000.0, hard_coal=8000.0)       # KVBG section 4: 9 GW lignite, 8 GW hard coal in 2030
    no_coal = dict(firm26, lignite=0.0, hard_coal=0.0)
    S = {
        "2026 fleet": Scenario("2026 fleet", firm26, res26, storage=pumped),
        "2030 RES targets, coal at KVBG path": Scenario("2030 KVBG", kvbg, res30, storage=pumped),
        "2030, KVBG path, +3 m heat pumps": Scenario("2030 KVBG +3m HP", kvbg, res30, 3e6, storage=pumped),
        "2030, no coal": Scenario("2030 no coal", no_coal, res30, storage=pumped),
        "2030, no coal, +3 m heat pumps": Scenario("2030 no coal +3m HP", no_coal, res30, 3e6, storage=pumped),
        "2030, no coal, +6 m heat pumps": Scenario("2030 no coal +6m HP", no_coal, res30, 6e6, storage=pumped),
    }
    return S, ac_per_dc


# ---------------------------------------------------------------------------------------------
def fmt(df: pd.DataFrame, digits: int = 2) -> str:
    return df.round(digits).to_markdown()


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)
    wx, obs, cap = load_inputs()
    check, cf, load, t2m, coef = fit_models(wx, obs, cap)
    base = build_base(wx, obs, cf, load, t2m)
    inter = interannual_check(cf, obs, cap)
    S, ac_per_dc = scenarios(base)
    print(check.round(3).to_string(), flush=True)

    res = {}
    rows = []
    for name, s in S.items():
        r = evaluate(s, base)
        res[name] = r
        row = summary(r)
        row["new firm capacity for 2.77 h (GW)"] = firm_needed(s, base) / 1000
        row["peak net demand (GW)"] = net_demand(s, base, copt.distribution(fleet(s))).max() / 1000
        row["mean available firm (GW)"] = copt.mean_available(copt.distribution(fleet(s))) / 1000
        rows.append(pd.Series(row, name=name))
        print(name, {k: round(v, 2) if isinstance(v, float) else v for k, v in row.items()}, flush=True)
    table = pd.DataFrame(rows)

    # Sensitivities on the central 2030 case
    central = S["2030, no coal, +3 m heat pumps"]
    sens = {
        "central": central,
        "imports 10 GW in every hour": replace(central, imports=10000.0),
        "forced outage rates x 1.5": replace(central, outage_scale=1.5),
        "batteries 10 GW / 20 GWh added": replace(central, storage=central.storage + [(10000.0, 20000.0)]),
        "no storage": replace(central, storage=[]),
    }
    srows = []
    for name, s in sens.items():
        r = evaluate(s, base)
        row = summary(r)
        row["new firm capacity for 2.77 h (GW)"] = firm_needed(s, base) / 1000
        srows.append(pd.Series(row, name=name))
        print("sens", name, round(row["LOLE h/yr"], 2), round(row["new firm capacity for 2.77 h (GW)"], 2), flush=True)
    stable = pd.DataFrame(srows)

    # Capacity credit (ELCC): firm capacity that buys the same LOLE as +10 GW of each resource,
    # measured on the central case after it has been made adequate.
    x0 = firm_needed(central, base)
    add = 10000.0
    elcc = {f"+10 GW {t}": capacity_credit(central, base, x0, add, res_scale={t: (central.res[t] + add) / central.res[t]})
            for t in TECHS}
    elcc["+10 GW / 40 GWh batteries"] = capacity_credit(
        replace(central, storage=central.storage + [(add, 4 * add)]), base, x0, add)
    print("ELCC", {k: round(v, 1) for k, v in elcc.items()}, flush=True)

    # Weather behind the loss-of-load hours (central case, made adequate)
    rc = evaluate(central, base, extra_firm=x0)
    nd = net_demand(central, base, copt.distribution(fleet(central, x0)))
    by_year = rc.groupby("year")[["lolp", "eens"]].sum()
    w = rc["lolp"]
    wind_cf = (base["cf_onshore"] * central.res["onshore"] + base["cf_offshore"] * central.res["offshore"]) / (
        central.res["onshore"] + central.res["offshore"])
    anatomy = pd.Series({
        "share of LOLE in Dec-Feb (%)": w[base.index.month.isin([12, 1, 2])].sum() / w.sum() * 100,
        "share of LOLE between 16 and 20 h local (%)": w[pd.Series(base.index.tz_convert("Europe/Berlin").hour, index=base.index).between(16, 20)].sum() / w.sum() * 100,
        "LOLE-weighted temperature (C)": (w * base["t2m"]).sum() / w.sum(),
        "mean winter temperature, all hours (C)": base["t2m"][base.index.month.isin([12, 1, 2])].mean(),
        "LOLE-weighted wind capacity factor (%)": (w * wind_cf).sum() / w.sum() * 100,
        "mean winter wind capacity factor (%)": wind_cf[base.index.month.isin([12, 1, 2])].mean() * 100,
        "LOLE-weighted heat pump load (GW)": (w * base["hp_per_pump"] * central.heat_pumps).sum() / w.sum() / 1000,
        "share of LOLE in the 5 worst years (%)": by_year["lolp"].nlargest(5).sum() / by_year["lolp"].sum() * 100,
    })

    # Periods of 1991-2008 vs 2009-2025, and trends over the 35 years
    coldest = base["t2m"].rolling(72).mean().groupby(base["year"]).min()
    lole_y = by_year["lolp"]
    halves = pd.DataFrame({
        "LOLE h/yr": [lole_y.loc[1991:2008].mean(), lole_y.loc[2009:2025].mean()],
        "years with LOLE > 0.5 h": [int((lole_y.loc[1991:2008] > 0.5).sum()), int((lole_y.loc[2009:2025] > 0.5).sum())],
        "coldest 72 h mean temperature (C)": [coldest.loc[1991:2008].mean(), coldest.loc[2009:2025].mean()],
    }, index=["1991-2008 (18 years)", "2009-2025 (17 years)"])
    tr_cold = stats.linregress(coldest.index, coldest.values)
    tr_lole = stats.linregress(lole_y.index, lole_y.values)
    mw = stats.mannwhitneyu(lole_y.loc[1991:2008], lole_y.loc[2009:2025], alternative="two-sided")
    trends = pd.DataFrame({
        "per decade": [tr_cold.slope * 10, tr_lole.slope * 10],
        "p (OLS slope)": [tr_cold.pvalue, tr_lole.pvalue]},
        index=["coldest 72 h mean temperature (C)", "LOLE (h)"])

    # Renewable droughts: days with wind + solar output below half its long-run daily mean (2030 fleet),
    # runs of at least three days
    ren = sum(base[f"cf_{t}"] * central.res[t] for t in TECHS)
    daily = ren.resample("D").mean()
    low = daily < 0.5 * daily.mean()
    runs = (low != low.shift()).cumsum()
    grp = daily[low].groupby(runs[low])
    events = pd.DataFrame({"start": grp.apply(lambda g: g.index[0]), "days": grp.size(),
                           "wind + solar (% of mean)": grp.mean() / daily.mean() * 100})
    events = events[events["days"] >= 3].sort_values("days", ascending=False)
    tday = base["t2m"].resample("D").mean()
    lday = rc["lolp"].resample("D").sum()
    span = [slice(e.start, e.start + pd.Timedelta(days=e.days - 1)) for e in events.itertuples()]
    events["mean temperature (C)"] = [tday[s].mean() for s in span]
    events["LOLE in the event (h)"] = [lday[s].sum() for s in span]
    events["start"] = events["start"].dt.strftime("%Y-%m-%d")
    drought_days = pd.Series(False, index=lday.index)
    for s in span:
        drought_days[s] = True
    drought = pd.Series({
        "drought events of 3 days or more": len(events),
        "per winter (Nov-Feb starts)": (pd.to_datetime(events["start"]).dt.month.isin([11, 12, 1, 2])).sum() / len(YEARS),
        "share of all days in such events (%)": drought_days.mean() * 100,
        "share of LOLE on those days (%)": lday[drought_days].sum() / lday.sum() * 100,
    })
    corr_on = inter[("onshore", "observed")].corr(inter[("onshore", "modelled")])

    # Tables
    with open(TABLES / "adequacy.md", "w", encoding="utf-8") as f:
        f.write("# Resource adequacy of the German power system, weather years 1991-2025\n\n")
        f.write(f"Solar AC per DC capacity (Energy-Charts 2026): {ac_per_dc:.3f}\n\n")
        f.write("## Model checks on the holdout (October 2025 to September 2026)\n\n" + fmt(check.set_index("model")) + "\n\n")
        f.write("## Annual capacity factor, observed vs modelled with today's fleet (%)\n\n" + fmt(inter, 1) + "\n\n")
        f.write("## Load model coefficients (weather terms, MW)\n\n" + fmt(coef[["hdd", "hdd_day", "cdd", "ghi", "xmas"]].to_frame("MW per unit"), 1) + "\n\n")
        f.write("## Scenarios\n\n" + fmt(table) + "\n\n")
        f.write("## Sensitivities (2030, no coal, +3 m heat pumps)\n\n" + fmt(stable) + "\n\n")
        f.write("## Capacity credit (ELCC), % of added capacity\n\n" + fmt(pd.Series(elcc).to_frame("ELCC %"), 1) + "\n\n")
        f.write("## When loss of load happens (central case made adequate)\n\n" + fmt(anatomy.to_frame("value"), 1) + "\n\n")
        f.write("## LOLE by weather year (central case made adequate)\n\n" + fmt(by_year.assign(eens=by_year.eens / 1000).rename(columns={"lolp": "LOLE h", "eens": "EENS GWh"}), 2) + "\n\n")
        f.write("## Two halves of the record\n\n" + fmt(halves) + "\n\n" + fmt(trends, 3)
                + f"\n\nMann-Whitney test, LOLE 1991-2008 vs 2009-2025: p = {mw.pvalue:.3f}\n\n")
        f.write("## Renewable droughts: wind + solar below 50% of its daily mean for 3 days or more (2030 fleet)\n\n"
                + fmt(drought.to_frame("value"), 1) + "\n\nLongest events:\n\n"
                + events.head(10).to_markdown(index=False, floatfmt=".1f") + "\n\n")
        f.write(f"Correlation of observed and modelled annual onshore capacity factors, 2015-2025: {corr_on:.2f}\n")
    base.to_parquet(ROOT / "data" / "base.parquet")
    rc.to_parquet(ROOT / "data" / "lolp_central.parquet")

    plots(base, central, rc, by_year, nd, x0, inter, res)
    print(open(TABLES / "adequacy.md", encoding="utf-8").read())


def plots(base, central, rc, by_year, nd, x0, inter, res) -> None:
    # 1 LOLE by weather year
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.bar(by_year.index, by_year["lolp"], color="#3b6ea5")
    ax.axhline(STANDARD, color="#b5403a", lw=1, ls="--", label=f"reliability standard {STANDARD} h")
    ax.set_ylabel("LOLE (hours)")
    ax.set_title("Loss-of-load hours by weather year, 2030 fleet without coal, +3 m heat pumps, made adequate on average")
    ax.title.set_fontsize(10)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIGS / "fig1_lole_by_weather_year.png", dpi=150)
    plt.close(fig)

    # 2 Anatomy of the worst week
    worst = rc["lolp"].rolling(24 * 7).sum().idxmax()
    sl = slice(worst - pd.Timedelta(days=9), worst + pd.Timedelta(days=2))
    b = base.loc[sl]
    fig, axes = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    ax = axes[0]
    load = (b["load"] + b["hp_per_pump"] * central.heat_pumps) / 1000
    wind = (b["cf_onshore"] * central.res["onshore"] + b["cf_offshore"] * central.res["offshore"]) / 1000
    solar = b["cf_solar"] * central.res["solar"] / 1000
    ax.plot(b.index, load, color="k", lw=1.2, label="load incl. heat pumps")
    ax.plot(b.index, b["load"] / 1000, color="k", lw=0.8, ls=":", label="load without additional heat pumps")
    ax.stackplot(b.index, b["hydro"] / 1000, wind, solar, colors=["#7aa6c2", "#3b6ea5", "#e0b040"],
                 labels=["hydro", "wind", "solar"], alpha=0.85)
    avail = copt.mean_available(copt.distribution(fleet(central, x0))) / 1000
    ax.plot(b.index, (b["hydro"] / 1000 + wind + solar + avail), color="#b5403a", lw=1,
            label="+ expected available firm capacity")
    ax.set_ylabel("GW")
    ax.set_ylim(0, ax.get_ylim()[1] * 1.3)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center")
    ax.set_title(f"Days around the week with the most loss-of-load hours (weather of {worst:%B %Y}), 2030 fleet without coal, +3 m heat pumps")
    ax.title.set_fontsize(10)
    axes[1].plot(b.index, b["t2m"], color="#555")
    axes[1].set_ylabel("temperature (C)")
    axes[1].xaxis.set_major_formatter(mdates.ConciseDateFormatter(mdates.AutoDateLocator()))
    fig.tight_layout()
    fig.savefig(FIGS / "fig2_worst_week.png", dpi=150)
    plt.close(fig)

    # 3 Interannual check
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.2))
    for ax, t in zip(axes, ("onshore", "solar")):
        ax.plot(inter.index, inter[(t, "observed")], "o-", color="#555", label="observed (fleet of the year)")
        ax.plot(inter.index, inter[(t, "modelled")], "o-", color="#3b6ea5", label="modelled (today's fleet)")
        ax.set_title(f"{t} capacity factor (%)", fontsize=10)
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGS / "fig3_annual_capacity_factor_check.png", dpi=150)
    plt.close(fig)

    # 4 Scenario LOLE
    fig, ax = plt.subplots(figsize=(9, 3.4))
    names = list(res)
    vals = [res[n].groupby("year")["lolp"].sum().mean() for n in names]
    ax.barh(names, vals, color="#3b6ea5")
    for i, v in enumerate(vals):
        ax.text(max(v, 0) * 1.08 + 0.02, i, f"{v:.2f} h" if v < 10 else f"{v:.0f} h", va="center", fontsize=8)
    ax.axvline(STANDARD, color="#b5403a", lw=1, ls="--", label=f"standard {STANDARD} h")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.set_xlim(0, max(vals) * 3)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("LOLE (hours per year, mean over 35 weather years)")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(FIGS / "fig4_scenarios.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
