"""Blind analysis of field returns, the way a quality engineer would do it.

Input is only a ``field.Observed`` object: shipments per production week and the
returned units. No function in this module may look at the hidden truth.

Views:
  1. Weibull of time in service with suspensions (MRR and MLE).
  2. Nevada chart: production period against return period.
  3. Production-week test: log-linear trend, then a scan for a window of weeks with
     an elevated rate (Kulldorff-type likelihood ratio, Monte Carlo p-value).
  4. Load stratification: welded returns against other-cause returns (case-control)
     and against the published lamp rating.
  5. A decision rule that turns the test results into batch / design / mixed.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
from scipy.stats import chi2, fisher_exact

from . import weibull as wb
from .field import Observed

RATED_LED_W = 200.0   # published LED rating of the channel (IEC 60669-1 Table 2, 16 A switch)


# ----------------------------------------------------------------- 1. Weibull
def weibull_views(obs: Observed, cl: float = 0.90) -> dict:
    """Weibull fits of time in service of welded returns; everything else is a suspension."""
    w = obs.is_weld
    tis = np.where(np.isnan(obs.tis), obs.age_ship - obs.install_lag_med - obs.return_lag_med, obs.tis)
    tis = np.maximum(tis, 1.0)
    t_fail = tis[w]
    ret_per_week = np.bincount(obs.week, minlength=obs.n_weeks)[:obs.n_weeks]
    age = obs.t_obs - obs.ship_day - obs.install_lag_med
    ok = age > 1.0
    t_susp = np.concatenate([age[ok], tis[~w]])
    w_susp = np.concatenate([(obs.shipped - ret_per_week)[ok], np.ones((~w).sum())])
    out = {"n_fail": int(t_fail.size), "n_susp": float(w_susp.sum())}
    if t_fail.size < 5:
        return out
    mle = wb.fit_mle(t_fail, t_susp, w_susp, cl=cl)
    mrr = wb.fit_mrr(t_fail, t_susp, w_susp)
    out.update({
        "mle_beta": mle.beta, "mle_beta_lo": mle.beta_lo, "mle_beta_hi": mle.beta_hi,
        "mle_beta_lr_lo": mle.beta_lr_lo, "mle_beta_lr_hi": mle.beta_lr_hi,
        "mle_eta_days": mle.eta, "mle_eta_lo": mle.eta_lo, "mle_eta_hi": mle.eta_hi,
        "mrr_beta": mrr.beta, "mrr_eta_days": mrr.eta, "mrr_r2": mrr.r2,
        "mle_f_3y_pct": float(100 * mle.cdf(3 * 365.0)), "mrr_f_3y_pct": float(100 * mrr.cdf(3 * 365.0)),
    })
    out["_fits"] = (mle, mrr, t_fail, t_susp, w_susp)
    return out


# ----------------------------------------------------------------- 2. Nevada chart
def nevada(obs: Observed, bucket_days: float = 28.0):
    """Welded returns per (production period, return period) and units shipped per production period."""
    nb_ret = int(np.ceil(obs.t_obs / bucket_days))
    pb = (obs.ship_day // bucket_days).astype(int)
    n_pb = pb.max() + 1
    shipped = np.bincount(pb, weights=obs.shipped, minlength=n_pb)
    w = obs.is_weld
    counts = np.zeros((n_pb, nb_ret))
    np.add.at(counts, (pb[obs.week[w]], np.minimum((obs.t_return[w] // bucket_days).astype(int), nb_ret - 1)), 1)
    return counts, shipped


# ----------------------------------------------------------------- 3. production week
def week_counts(obs: Observed, age_bucket: float = 28.0):
    """Observed welded returns per production week and the count expected if every week
    had the same return hazard by age since shipment (indirect standardisation)."""
    w = obs.is_weld
    O = np.bincount(obs.week[w], minlength=obs.n_weeks)[:obs.n_weeks].astype(float)
    max_age = obs.t_obs - obs.ship_day                               # per production week
    na = int(np.ceil(max_age.max() / age_bucket))
    edges = np.arange(na + 1) * age_bucket
    # exposure of week w in age bucket a (fraction of the bucket already observed)
    expo = np.clip((max_age[:, None] - edges[None, :-1]) / age_bucket, 0.0, 1.0) * obs.shipped[:, None]
    cases_a = np.bincount(np.minimum((obs.age_ship[w] // age_bucket).astype(int), na - 1), minlength=na)
    haz = cases_a / np.maximum(expo.sum(axis=0), 1e-9)
    E = expo @ haz
    return O, E * O.sum() / max(E.sum(), 1e-12)


def fit_trend(O: np.ndarray, E: np.ndarray, mask: np.ndarray | None = None, iters: int = 25):
    """Poisson fit of O ~ E * exp(a + b*w) (vectorised over leading axes). Returns a, b, loglik."""
    n = O.shape[-1]
    wk = (np.arange(n) - n / 2.0) / n
    m = np.ones(n) if mask is None else mask.astype(float)
    Em = E * m
    Om = O * m
    a = np.log(np.maximum(Om.sum(-1), 1e-9) / np.maximum(Em.sum(-1), 1e-12))
    b = np.zeros_like(a)
    for _ in range(iters):
        mu = Em * np.exp(a[..., None] + b[..., None] * wk)
        g0, g1 = (Om - mu).sum(-1), ((Om - mu) * wk).sum(-1)
        h00, h01, h11 = mu.sum(-1), (mu * wk).sum(-1), (mu * wk * wk).sum(-1)
        det = np.maximum(h00 * h11 - h01 * h01, 1e-12)
        da = np.clip((h11 * g0 - h01 * g1) / det, -2.0, 2.0)
        db = np.clip((h00 * g1 - h01 * g0) / det, -2.0, 2.0)
        a, b = a + da, b + db
    mu = Em * np.exp(a[..., None] + b[..., None] * wk)
    ll = np.sum(np.where(Om > 0, Om * np.log(np.maximum(mu, 1e-300)), 0.0) - mu, axis=-1)
    return a, b, ll, E * np.exp(a[..., None] + b[..., None] * wk)


def scan(O: np.ndarray, E: np.ndarray, min_len: int = 2, max_len: int = 16):
    """Largest likelihood ratio over all windows of consecutive production weeks with an
    elevated rate (Kulldorff). O, E: (..., n) with equal totals. Returns LR, start, length."""
    n = O.shape[-1]
    N = O.sum(-1)[..., None]
    cO = np.concatenate([np.zeros(O.shape[:-1] + (1,)), np.cumsum(O, -1)], -1)
    cE = np.concatenate([np.zeros(E.shape[:-1] + (1,)), np.cumsum(E, -1)], -1)
    best = np.zeros(O.shape[:-1])
    b_start = np.zeros(O.shape[:-1], dtype=int)
    b_len = np.zeros(O.shape[:-1], dtype=int)
    for ln in range(min_len, max_len + 1):
        oin = cO[..., ln:] - cO[..., :-ln]
        ein = np.maximum(cE[..., ln:] - cE[..., :-ln], 1e-12)
        oout, eout = N - oin, np.maximum(N - ein, 1e-12)
        with np.errstate(divide="ignore", invalid="ignore"):
            lr = np.where(oin > 0, oin * np.log(oin / ein), 0.0) + np.where(oout > 0, oout * np.log(oout / eout), 0.0)
        lr = np.where(oin / ein > oout / eout, lr, 0.0)
        j = lr.argmax(-1)
        v = np.take_along_axis(lr, j[..., None], -1)[..., 0]
        upd = v > best
        best = np.where(upd, v, best)
        b_start = np.where(upd, j, b_start)
        b_len = np.where(upd, ln, b_len)
    return best, b_start, b_len


def production_week_test(obs: Observed, n_sim: int = 199, seed: int = 0) -> dict:
    """Trend and batch-window tests on welded returns by production week."""
    rng = np.random.default_rng(seed)
    O, E0 = week_counts(obs)
    n_tot = int(O.sum())
    out = {"n_weld": n_tot, "batch_p": 1.0, "batch_detected": False, "window": None,
           "trend_p": 1.0, "trend_slope": 0.0, "batch_fraction": 0.0, "rate_ratio": 1.0}
    if n_tot < 8:
        return out
    a, b, ll1, E1 = fit_trend(O, E0)
    E1 = E1 * n_tot / E1.sum()
    lr_obs, s, ln = scan(O, E1)
    # Monte Carlo null: counts follow the fitted trend, trend refitted for every sample
    sims = rng.multinomial(n_tot, E1 / E1.sum(), size=n_sim).astype(float)
    _, _, _, Es = fit_trend(sims, np.broadcast_to(E0, sims.shape))
    Es = Es * n_tot / Es.sum(-1, keepdims=True)
    lr_sim, _, _ = scan(sims, Es)
    p_batch = (1 + np.sum(lr_sim >= lr_obs)) / (1 + n_sim)
    out.update({"batch_p": float(p_batch), "scan_lr": float(lr_obs)})
    # the naive version of the same test: no trend term (shows how a trend is mistaken for a batch)
    En = E0 * n_tot / E0.sum()
    lr_naive, sn, lnn = scan(O, En)
    sims_n = rng.multinomial(n_tot, En / En.sum(), size=n_sim).astype(float)
    lr_sim_n, _, _ = scan(sims_n, np.broadcast_to(En, sims_n.shape))
    out.update({"naive_batch_p": float((1 + np.sum(lr_sim_n >= lr_naive)) / (1 + n_sim)),
                "naive_window": (int(sn), int(sn) + int(lnn) - 1)})
    mask = np.ones(O.size, dtype=bool)
    if p_batch <= 0.01:
        mask[int(s):int(s) + int(ln)] = False
        out.update({"batch_detected": True, "window": (int(s), int(s) + int(ln) - 1)})
    # trend outside the window (or everywhere if no window)
    a0, _, ll0, _ = fit_trend(O, E0 * 1.0, mask=mask, iters=0)
    a2, b2, ll2, E2 = fit_trend(O, E0, mask=mask)
    lr_trend = max(2.0 * float(ll2 - ll0), 0.0)
    out.update({"trend_p": float(chi2.sf(lr_trend, 1)), "trend_slope": float(b2),
                "trend_rate_ratio_last_to_first": float(np.exp(b2 * (O.size - 1) / O.size))})
    if out["batch_detected"]:
        o_in, e_in = O[~mask].sum(), E2[~mask].sum()        # E2: expectation from the outside fit
        out.update({"rate_ratio": float(o_in / max(e_in, 1e-9)),
                    "batch_fraction": float(max(o_in - e_in, 0.0) / n_tot)})
    out["_O"], out["_E0"] = O, E0
    return out


# ----------------------------------------------------------------- 4. load stratification
def load_test(obs: Observed, exclude_weeks: tuple | None = None) -> dict:
    """Welded returns (cases) against other-cause returns (controls): share above the rating."""
    has = ~np.isnan(obs.p_led)
    case = obs.is_weld & has
    if exclude_weeks is not None:
        case &= ~((obs.week >= exclude_weeks[0]) & (obs.week <= exclude_weeks[1]))
    ctrl = ~obs.is_weld & has
    a = int((obs.p_led[case] > RATED_LED_W).sum()); b = int(case.sum() - a)
    c = int((obs.p_led[ctrl] > RATED_LED_W).sum()); d = int(ctrl.sum() - c)
    out = {"cases": a + b, "controls": c + d, "cases_over_rated": a, "controls_over_rated": c,
           "share_cases_over_rated": a / max(a + b, 1), "share_controls_over_rated": c / max(c + d, 1),
           "median_case_w": float(np.median(obs.p_led[case])) if case.any() else float("nan"),
           "odds_ratio": float(((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5))), "p": 1.0}
    if a + b >= 3 and c + d >= 3:
        out["p"] = float(fisher_exact([[a, b], [c, d]], alternative="greater")[1])
    return out


# ----------------------------------------------------------------- 5. decision
@dataclass
class Decision:
    verdict: str                  # batch / design / mixed / undetermined
    n_weld: int
    batch_detected: bool
    batch_p: float
    window: tuple | None
    batch_fraction: float
    rate_ratio: float
    trend_p: float
    trend_slope: float
    load_p_outside: float
    share_over_rated_all: float
    share_over_rated_outside: float
    design_evidence: bool

    def as_dict(self):
        return asdict(self)


def decide(obs: Observed, n_sim: int = 199, seed: int = 0, alpha: float = 0.01,
           batch_dominant: float = 0.75, use_load: bool = True) -> Decision:
    """Decision rule (fixed before looking at any truth):
      batch  : a window of production weeks is significant and explains >= 75 % of welded returns
      design : no window; welded returns rise with production week or sit above the lamp rating
      mixed  : a window is significant but explains < 75 %, and the rest shows design evidence
    """
    pw = production_week_test(obs, n_sim=n_sim, seed=seed)
    ld_all = load_test(obs)
    ld_out = load_test(obs, exclude_weeks=pw["window"])
    if not use_load:                      # variant: no load questionnaire is collected
        ld_out = dict(ld_out, p=1.0)
    design = bool((pw["trend_p"] <= alpha and pw["trend_slope"] > 0) or (ld_out["p"] <= alpha))
    if pw["batch_detected"]:
        verdict = "batch" if (pw["batch_fraction"] >= batch_dominant or not design) else "mixed"
    else:
        verdict = "design" if design else "undetermined"
    return Decision(verdict=verdict, n_weld=pw["n_weld"], batch_detected=pw["batch_detected"],
                    batch_p=pw["batch_p"], window=pw["window"], batch_fraction=pw["batch_fraction"],
                    rate_ratio=pw["rate_ratio"], trend_p=pw["trend_p"], trend_slope=pw["trend_slope"],
                    load_p_outside=ld_out["p"], share_over_rated_all=ld_all["share_cases_over_rated"],
                    share_over_rated_outside=ld_out["share_cases_over_rated"], design_evidence=design)


# ----------------------------------------------------------------- 6. forecast
def forecast(obs: Observed, pw: dict, units_per_week: float, n_periods: int, cutin_week: int | None = None,
             ca_factor: float = 1.0, bucket: float = 28.0) -> np.ndarray:
    """Expected welded returns per 28-day period after the cut-off, from the fitted
    age hazard and production-week effect. Production is assumed to continue at
    units_per_week. The production-week trend is frozen at its last fitted value.
    Units built from cutin_week on get their hazard multiplied by ca_factor."""
    O, E0 = pw["_O"], pw["_E0"]
    n = obs.n_weeks
    mask = np.ones(n, dtype=bool)
    if pw["window"] is not None:
        mask[pw["window"][0]:pw["window"][1] + 1] = False
    _, b, _, _ = fit_trend(O, E0, mask=mask)
    wk = (np.arange(n) - n / 2.0) / n
    m = np.exp(float(b) * wk)
    if pw["window"] is not None:
        m[~mask] *= pw["rate_ratio"]
    # age hazard re-estimated with the production-week multipliers
    w = obs.is_weld
    max_age = obs.t_obs - obs.ship_day
    na = int(np.ceil(max_age.max() / bucket))
    edges = np.arange(na + 1) * bucket
    expo = np.clip((max_age[:, None] - edges[None, :-1]) / bucket, 0.0, 1.0) * obs.shipped[:, None]
    cases_a = np.bincount(np.minimum((obs.age_ship[w] // bucket).astype(int), na - 1), minlength=na)
    denom = (expo * m[:, None]).sum(axis=0)
    haz = cases_a / np.maximum(denom, 1e-9)
    good = np.flatnonzero(denom > 0.2 * denom.max())
    tail = haz[good[-6:]].mean()
    haz_ext = np.concatenate([haz[:good[-1] + 1], np.full(n_periods + na + 60, tail)])
    # all production weeks, past and future
    n_all = n + int(np.ceil(n_periods * bucket / 7.0)) + 1
    ship_all = 7.0 * np.arange(n_all) + 3.5 + (obs.ship_day[0] - 3.5)
    shipped_all = np.concatenate([obs.shipped, np.full(n_all - n, units_per_week)])
    m_all = np.concatenate([m, np.full(n_all - n, m[mask][-1])])
    if cutin_week is not None:
        m_all[cutin_week:] *= ca_factor
    out = np.zeros(n_periods)
    for k in range(n_periods):
        t_mid = obs.t_obs + (k + 0.5) * bucket
        age = t_mid - ship_all
        ok = age > 0
        out[k] = np.sum(shipped_all[ok] * m_all[ok] * haz_ext[(age[ok] // bucket).astype(int)])
    return out


TRUE_VERDICT = {"A_batch": "batch", "B_design": "design", "C_mixed": "mixed"}


def auc(x, y) -> float:
    """P(x > y) + 0.5 P(x = y): how well a metric separates two groups (0.5 = not at all)."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    x, y = x[~np.isnan(x)], y[~np.isnan(y)]
    if x.size == 0 or y.size == 0:
        return float("nan")
    d = x[:, None] - y[None, :]
    return float(((d > 0).sum() + 0.5 * (d == 0).sum()) / d.size)
