"""Synthetic field population and return reporting.

There is no real return data in this project. This module generates units,
installations, weld failures (from ``relayret.weld``) and returns for a chosen
hidden truth, and then hands the analyst only what a quality engineer would
really have: shipments per production week and the returned units.

Every distribution here is an assumption about a plausible installed base
(see DOSSIER 7.3). Days are counted from the first production day.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from . import weld as wd

HORIZON_DAYS = 15 * 365.0


@dataclass(frozen=True)
class Truth:
    """One hidden truth. The analyst never sees this object."""
    name: str
    batch_weeks: tuple = ()          # production weeks built with the weak contact lot
    batch_factor: float = 1.0        # W50 multiplier of the weak lot
    com_share_start: float = 0.12    # share of LED channels in commercial lighting, first installs
    com_share_end: float = 0.12      # ... and for installs at day `mix_end_day`
    com_median_w: float = 220.0      # median LED load of a commercial channel [W]
    mix_end_day: float = 900.0


TRUTHS = {
    # A: weak contact lot in 8 production weeks; installed base stays light
    "A_batch": Truth("A_batch", batch_weeks=tuple(range(44, 52)), batch_factor=0.065,
                     com_share_start=0.08, com_share_end=0.08, com_median_w=160.0),
    # B: every unit is nominal; the share of big LED channels grows with the install date
    "B_design": Truth("B_design", com_share_start=0.10, com_share_end=0.50, com_median_w=290.0),
    # C: a milder weak lot and a slower growth of big LED channels
    "C_mixed": Truth("C_mixed", batch_weeks=tuple(range(46, 52)), batch_factor=0.22,
                     com_share_start=0.10, com_share_end=0.32, com_median_w=265.0),
}


@dataclass(frozen=True)
class FieldParams:
    n_weeks: int = 130               # production weeks (production is still running at the cut-off)
    units_per_week: int = 600        # one relay channel per unit
    ship_delay: float = 14.0         # days from production to shipment
    install_med: float = 45.0        # days from shipment to commissioning (lognormal median)
    install_sig: float = 0.7
    led_share: float = 0.60          # channels that switch LED lighting at all
    res_median_w: float = 40.0       # residential LED channel load [W]
    res_sig: float = 0.7
    com_sig: float = 0.75
    p_max: float = 1600.0
    lamp_mix_res: tuple = (0.30, 0.50, 0.20)   # high / medium / low inrush class
    lamp_mix_com: tuple = (0.35, 0.50, 0.15)
    line_mix_res: tuple = (0.20, 0.50, 0.30)   # stiff / medium / soft supply
    line_mix_com: tuple = (0.40, 0.45, 0.15)
    ops_res_med: float = 3.0         # switching operations per day
    ops_res_sig: float = 0.8
    ops_com_med: float = 6.0
    ops_com_sig: float = 0.9
    other_rate_per_year: float = 0.004   # unrelated failures (electronics), load independent
    p_return_weld: float = 0.60      # share of weld failures that come back
    p_return_other: float = 0.60
    return_lag_med: float = 30.0     # days from failure to arrival in the returns lab
    return_lag_sig: float = 0.6
    p_load_info: float = 0.50        # returns with a usable load questionnaire
    load_report_sig: float = 0.25    # log error of the reported LED wattage
    p_tis_known: float = 0.70        # returns with a known commissioning date


def generate(truth: Truth, model: wd.WeldModel, fp: FieldParams = FieldParams(), seed: int = 0) -> dict:
    """Generate the complete hidden unit table for one truth."""
    rng = np.random.default_rng(seed)
    n_w = rng.poisson(fp.units_per_week, fp.n_weeks)
    week = np.repeat(np.arange(fp.n_weeks), n_w)
    n = week.size
    ship = 7.0 * week + rng.uniform(0, 7, n) + fp.ship_delay
    install = ship + fp.install_med * np.exp(fp.install_sig * rng.standard_normal(n))

    # installation: segment, LED load, lamp class, line class, switching frequency
    frac = np.clip(install / truth.mix_end_day, 0.0, 1.0)
    com_share = truth.com_share_start + (truth.com_share_end - truth.com_share_start) * frac
    has_led = rng.random(n) < fp.led_share
    is_com = has_led & (rng.random(n) < com_share)
    seg = np.where(is_com, 2, np.where(has_led, 1, 0))
    z = rng.standard_normal(n)
    p_led = np.where(is_com, truth.com_median_w * np.exp(fp.com_sig * z),
                     fp.res_median_w * np.exp(fp.res_sig * z))
    p_led = np.clip(p_led, 5.0, fp.p_max)
    u = rng.random(n)
    ic = np.where(is_com, np.searchsorted(np.cumsum(fp.lamp_mix_com), u),
                  np.searchsorted(np.cumsum(fp.lamp_mix_res), u)).clip(0, 2)
    u = rng.random(n)
    il = np.where(is_com, np.searchsorted(np.cumsum(fp.line_mix_com), u),
                  np.searchsorted(np.cumsum(fp.line_mix_res), u)).clip(0, 2)
    z = rng.standard_normal(n)
    ops = np.where(is_com, fp.ops_com_med * np.exp(fp.ops_com_sig * z),
                   fp.ops_res_med * np.exp(fp.ops_res_sig * z))

    # production variables: contact force spread and the weak lot
    is_batch = np.isin(week, truth.batch_weeks)
    x0 = model.x_nominal + model.params.sigma_unit * rng.standard_normal(n)
    x0 = x0 + np.where(is_batch, np.log(truth.batch_factor), 0.0)

    # weld failure: invert the cumulative hazard over operations
    n_fail = np.full(n, np.inf)
    idx = np.flatnonzero(has_led)
    grid = np.linspace(0.0, 1.0, 25) ** 1.5
    n_ops = (ops[idx] * HORIZON_DAYS)[:, None] * grid[None, :]
    H = model.cum_hazard(p_led[idx], ic[idx], il[idx], x0[idx], n_ops)
    e = rng.exponential(1.0, idx.size)
    hit = e < H[:, -1]
    for k in np.flatnonzero(hit):
        n_fail[idx[k]] = np.interp(e[k], H[k], n_ops[k])
    t_weld = install + n_fail / ops
    t_other = install + rng.exponential(365.0 / fp.other_rate_per_year, n)

    # reporting
    weld_first = t_weld < t_other
    t_fail = np.minimum(t_weld, t_other)
    p_ret = np.where(weld_first, fp.p_return_weld, fp.p_return_other)
    will_return = rng.random(n) < p_ret
    t_return = t_fail + fp.return_lag_med * np.exp(fp.return_lag_sig * rng.standard_normal(n))
    return {
        "truth": truth, "fp": fp, "week": week, "ship": ship, "install": install, "seg": seg,
        "p_led": np.where(has_led, p_led, 0.0), "ic": ic, "il": il, "ops": ops, "x0": x0,
        "is_batch": is_batch, "t_weld": t_weld, "t_other": t_other, "weld_first": weld_first,
        "t_fail": t_fail, "will_return": will_return, "t_return": t_return,
        "load_info": rng.random(n) < fp.p_load_info,
        "p_reported": np.where(has_led, p_led * np.exp(fp.load_report_sig * rng.standard_normal(n)), 0.0),
        "tis_known": rng.random(n) < fp.p_tis_known,
        "shipped_per_week": n_w,
    }


@dataclass
class Observed:
    """What the quality engineer has at the cut-off day. Nothing else may be used."""
    t_obs: float
    n_weeks: int
    shipped: np.ndarray        # units shipped per production week
    ship_day: np.ndarray       # nominal ship day per production week
    install_lag_med: float     # known from commissioning records: typical ship-to-install lag
    return_lag_med: float      # known from RMA forms: typical failure-to-lab lag
    week: np.ndarray           # per returned unit: production week (from the serial number)
    is_weld: np.ndarray        # lab finding: welded contact (True) or other cause (False)
    t_return: np.ndarray       # arrival day in the returns lab
    age_ship: np.ndarray       # days from shipment to return
    tis: np.ndarray            # days in service at failure, NaN if commissioning date unknown
    p_led: np.ndarray          # reported LED load [W], NaN if no usable questionnaire


def observe(pop: dict, t_obs: float) -> Observed:
    fp: FieldParams = pop["fp"]
    ret = pop["will_return"] & (pop["t_return"] <= t_obs)
    i = np.flatnonzero(ret)
    tis = np.where(pop["tis_known"][i], pop["t_fail"][i] - pop["install"][i], np.nan)
    p_led = np.where(pop["load_info"][i], pop["p_reported"][i], np.nan)
    ship_day = 7.0 * np.arange(fp.n_weeks) + 3.5 + fp.ship_delay
    nw = int(np.sum(ship_day <= t_obs))
    return Observed(
        t_obs=t_obs, n_weeks=nw, shipped=pop["shipped_per_week"][:nw],
        ship_day=ship_day[:nw], install_lag_med=fp.install_med, return_lag_med=fp.return_lag_med,
        week=pop["week"][i], is_weld=pop["weld_first"][i], t_return=pop["t_return"][i],
        age_ship=pop["t_return"][i] - pop["ship"][i], tis=tis, p_led=p_led)


def truth_summary(pop: dict, t_obs: float) -> dict:
    """Hidden facts used only to score the blind analysis afterwards."""
    weld = pop["weld_first"] & (pop["t_fail"] <= t_obs)
    ret = weld & pop["will_return"] & (pop["t_return"] <= t_obs)
    n = int(np.sum(pop["ship"] <= t_obs))
    return {
        "units": n,
        "weld_failures": int(weld.sum()),
        "weld_returns": int(ret.sum()),
        "weld_return_rate_pct": float(100.0 * ret.sum() / n),
        "batch_share_of_weld_returns": float((ret & pop["is_batch"]).sum() / max(ret.sum(), 1)),
        "share_weld_returns_over_rated": float((pop["p_led"][ret] > 200.0).mean()) if ret.any() else 0.0,
        "median_led_w_weld_returns": float(np.median(pop["p_led"][ret])) if ret.any() else 0.0,
    }


def with_truth(truth: Truth, **kw) -> Truth:
    return replace(truth, **kw)
