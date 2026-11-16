"""Two-parameter Weibull estimation with right-censored (suspended) units.

Two estimators are provided because quality teams use both:
  * median-rank regression (Bernard's approximation, Johnson's adjusted ranks,
    regression of ln t on the plotting position, "X on Y");
  * maximum likelihood, with Fisher-matrix and likelihood-ratio confidence bounds.
Suspensions may be given in groups (time, count) so that tens of thousands of
running units cost nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq
from scipy.stats import chi2, norm


def bernard(adj_rank, n):
    """Bernard's approximation of the median rank."""
    return (np.asarray(adj_rank, dtype=float) - 0.3) / (n + 0.4)


def adjusted_ranks(t_fail, t_susp=(), w_susp=None):
    """Johnson's adjusted ranks for failures among suspensions.

    Returns (sorted failure times, adjusted ranks, total number of units)."""
    tf = np.sort(np.asarray(t_fail, dtype=float))
    ts = np.asarray(t_susp, dtype=float)
    ws = np.ones(ts.size) if w_susp is None else np.asarray(w_susp, dtype=float)
    n_tot = tf.size + ws.sum()
    order = np.argsort(ts)
    ts, cw = ts[order], np.concatenate([[0.0], np.cumsum(ws[order])])
    # suspensions strictly before each failure (a tie counts as still at risk)
    susp_before = cw[np.searchsorted(ts, tf, side="left")]
    ranks = np.empty(tf.size)
    prev = 0.0
    for i in range(tf.size):
        at_risk = n_tot - i - susp_before[i]          # units still running, incl. this one
        prev = prev + (n_tot + 1.0 - prev) / (1.0 + at_risk)
        ranks[i] = prev
    return tf, ranks, n_tot


@dataclass
class WeibullFit:
    beta: float
    eta: float
    method: str
    n_fail: int
    n_total: float
    r2: float = np.nan
    loglik: float = np.nan
    beta_lo: float = np.nan      # Fisher-matrix bounds
    beta_hi: float = np.nan
    eta_lo: float = np.nan
    eta_hi: float = np.nan
    beta_lr_lo: float = np.nan   # likelihood-ratio bounds on beta
    beta_lr_hi: float = np.nan
    cov: np.ndarray | None = None   # covariance of (ln eta, ln beta)

    def cdf(self, t):
        return 1.0 - np.exp(-(np.asarray(t, dtype=float) / self.eta) ** self.beta)

    def b_life(self, p: float, cl: float = 0.90):
        """Time by which a fraction p has failed, with two-sided Fisher bounds."""
        k = np.log(-np.log(1.0 - p))
        ln_t = np.log(self.eta) + k / self.beta
        if self.cov is None:
            return float(np.exp(ln_t)), np.nan, np.nan
        g = np.array([1.0, -k / self.beta])           # d ln t / d(ln eta, ln beta)
        se = float(np.sqrt(g @ self.cov @ g))
        z = norm.ppf(0.5 + cl / 2.0)
        return float(np.exp(ln_t)), float(np.exp(ln_t - z * se)), float(np.exp(ln_t + z * se))


def fit_mrr(t_fail, t_susp=(), w_susp=None) -> WeibullFit:
    """Median-rank regression, X on Y."""
    tf, ranks, n_tot = adjusted_ranks(t_fail, t_susp, w_susp)
    y = np.log(-np.log(1.0 - bernard(ranks, n_tot)))
    x = np.log(tf)
    b, a = np.polyfit(y, x, 1)                        # x = a + b*y
    r = np.corrcoef(x, y)[0, 1]
    return WeibullFit(beta=1.0 / b, eta=float(np.exp(a)), method="MRR", n_fail=tf.size,
                      n_total=float(n_tot), r2=float(r * r))


def _loglik(ln_eta, ln_beta, ltf, lts, ws):
    beta = np.exp(ln_beta)
    zf = beta * (ltf - ln_eta)
    ll = np.sum(ln_beta - ln_eta + zf - (ltf - ln_eta) - np.exp(zf))
    if lts.size:
        ll -= np.sum(ws * np.exp(beta * (lts - ln_eta)))
    return ll


def _profile(beta, ltf, lts, ws):
    """Profile log-likelihood in beta (eta maximised out) and the eta that does it."""
    r = ltf.size
    m = max(ltf.max(), lts.max() if lts.size else -np.inf)
    s = np.sum(np.exp(beta * (ltf - m)))
    if lts.size:
        s += np.sum(ws * np.exp(beta * (lts - m)))
    ln_eta = m + np.log(s / r) / beta
    return _loglik(ln_eta, np.log(beta), ltf, lts, ws), ln_eta


def fit_mle(t_fail, t_susp=(), w_susp=None, cl: float = 0.90) -> WeibullFit:
    """Maximum likelihood with right-censored units; bounds at two-sided level cl."""
    ltf = np.log(np.asarray(t_fail, dtype=float))
    lts = np.log(np.asarray(t_susp, dtype=float))
    ws = np.ones(lts.size) if w_susp is None else np.asarray(w_susp, dtype=float)
    r = ltf.size
    m = max(ltf.max(), lts.max() if lts.size else -np.inf)

    def score(beta):
        ef = np.exp(beta * (ltf - m))
        num, den = np.sum(ef * ltf), np.sum(ef)
        if lts.size:
            es = ws * np.exp(beta * (lts - m))
            num, den = num + np.sum(es * lts), den + np.sum(es)
        return num / den - 1.0 / beta - ltf.mean()

    beta = brentq(score, 1e-3, 200.0)
    ll, ln_eta = _profile(beta, ltf, lts, ws)
    # observed information by central differences in (ln eta, ln beta)
    th = np.array([ln_eta, np.log(beta)])
    f = lambda v: _loglik(v[0], v[1], ltf, lts, ws)
    h = 1e-4
    H = np.zeros((2, 2))
    for i in range(2):
        for j in range(2):
            ei, ej = np.eye(2)[i] * h, np.eye(2)[j] * h
            H[i, j] = (f(th + ei + ej) - f(th + ei - ej) - f(th - ei + ej) + f(th - ei - ej)) / (4 * h * h)
    cov = np.linalg.inv(-H)
    z = norm.ppf(0.5 + cl / 2.0)
    se_e, se_b = np.sqrt(cov[0, 0]), np.sqrt(cov[1, 1])
    fit = WeibullFit(beta=float(beta), eta=float(np.exp(ln_eta)), method="MLE", n_fail=r,
                     n_total=float(r + ws.sum()), loglik=float(ll), cov=cov,
                     beta_lo=float(beta * np.exp(-z * se_b)), beta_hi=float(beta * np.exp(z * se_b)),
                     eta_lo=float(np.exp(ln_eta - z * se_e)), eta_hi=float(np.exp(ln_eta + z * se_e)))
    # likelihood-ratio bounds on beta
    target = ll - 0.5 * chi2.ppf(cl, 1)
    g = lambda b: _profile(b, ltf, lts, ws)[0] - target
    try:
        fit.beta_lr_lo = float(brentq(g, beta / 20.0, beta))
        fit.beta_lr_hi = float(brentq(g, beta, beta * 20.0))
    except ValueError:
        pass
    return fit
