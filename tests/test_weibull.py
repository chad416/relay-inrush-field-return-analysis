"""Weibull estimation checked against independent library results and known parameters."""
import numpy as np
import pytest
from scipy import stats

from relayret import weibull as wb


def test_bernard_close_to_exact_median_ranks():
    n = 10
    i = np.arange(1, n + 1)
    exact = stats.beta.ppf(0.5, i, n - i + 1)
    assert np.max(np.abs(wb.bernard(i, n) - exact)) < 0.005


def test_adjusted_ranks_hand_calculation():
    # five units: F, S, F, S, F. Johnson's formula by hand: 1, 1 + 5/4 = 2.25, 2.25 + 3.75/2 = 4.125
    tf, ranks, n = wb.adjusted_ranks([5100, 15000, 40000], [9500, 22000])
    assert n == 5
    assert ranks == pytest.approx([1.0, 2.25, 4.125])


def test_adjusted_ranks_without_suspensions_are_plain_ranks():
    _, ranks, _ = wb.adjusted_ranks([3.0, 1.0, 2.0, 7.0])
    assert ranks == pytest.approx([1, 2, 3, 4])


def test_grouped_suspensions_equal_expanded():
    rng = np.random.default_rng(0)
    f = rng.weibull(1.5, 40) * 100
    a = wb.fit_mle(f, [50.0, 80.0], [300, 500])
    b = wb.fit_mle(f, np.r_[np.full(300, 50.0), np.full(500, 80.0)])
    assert a.beta == pytest.approx(b.beta, rel=1e-9) and a.eta == pytest.approx(b.eta, rel=1e-9)
    m1 = wb.fit_mrr(f, [50.0, 80.0], [300, 500])
    m2 = wb.fit_mrr(f, np.r_[np.full(300, 50.0), np.full(500, 80.0)])
    assert m1.beta == pytest.approx(m2.beta, rel=1e-9)


def test_mle_complete_data_matches_scipy():
    rng = np.random.default_rng(1)
    t = stats.weibull_min.rvs(2.2, scale=80.0, size=300, random_state=rng)
    c, _, scale = stats.weibull_min.fit(t, floc=0)
    fit = wb.fit_mle(t)
    assert fit.beta == pytest.approx(c, rel=2e-3)
    assert fit.eta == pytest.approx(scale, rel=2e-3)


def test_mle_censored_matches_lifelines():
    lifelines = pytest.importorskip("lifelines")
    rng = np.random.default_rng(2)
    t = stats.weibull_min.rvs(0.8, scale=5000.0, size=4000, random_state=rng)
    c = rng.uniform(100, 900, t.size)                 # staggered entry: every unit has its own censoring time
    obs = t <= c
    dur = np.minimum(t, c)
    ll = lifelines.WeibullFitter().fit(dur, event_observed=obs)
    fit = wb.fit_mle(dur[obs], dur[~obs])
    assert fit.beta == pytest.approx(ll.rho_, rel=1e-3)
    assert fit.eta == pytest.approx(ll.lambda_, rel=2e-3)
    assert fit.loglik == pytest.approx(ll.log_likelihood_, rel=1e-6)


def test_synthetic_known_parameters_heavy_censoring():
    rng = np.random.default_rng(3)
    beta, eta = 1.6, 1000.0
    t = stats.weibull_min.rvs(beta, scale=eta, size=20000, random_state=rng)
    obs = t <= 300.0                                   # about 13.5 % fail before the cut
    fit = wb.fit_mle(t[obs], [300.0], [np.sum(~obs)])
    assert fit.beta_lo < beta < fit.beta_hi
    assert fit.eta_lo < eta < fit.eta_hi
    assert fit.beta == pytest.approx(beta, rel=0.05)
    mrr = wb.fit_mrr(t[obs], [300.0], [np.sum(~obs)])
    assert mrr.beta == pytest.approx(beta, rel=0.08)
    assert mrr.eta == pytest.approx(eta, rel=0.15)


def test_mrr_recovers_exact_quantile_data():
    n, beta, eta = 25, 2.5, 400.0
    f = wb.bernard(np.arange(1, n + 1), n)
    t = eta * (-np.log(1 - f)) ** (1 / beta)
    fit = wb.fit_mrr(t)
    assert fit.beta == pytest.approx(beta, rel=1e-9)
    assert fit.eta == pytest.approx(eta, rel=1e-9)
    assert fit.r2 == pytest.approx(1.0)


def test_fisher_bounds_coverage():
    rng = np.random.default_rng(4)
    beta, eta, hits = 1.3, 500.0, 0
    reps = 300
    for _ in range(reps):
        t = stats.weibull_min.rvs(beta, scale=eta, size=80, random_state=rng)
        obs = t <= 600.0
        fit = wb.fit_mle(t[obs], [600.0], [np.sum(~obs)], cl=0.90)
        hits += fit.beta_lo < beta < fit.beta_hi
    assert 0.84 <= hits / reps <= 0.96                 # nominal 0.90


def test_likelihood_ratio_bounds_bracket_estimate():
    rng = np.random.default_rng(5)
    t = stats.weibull_min.rvs(1.0, scale=100.0, size=15, random_state=rng)
    fit = wb.fit_mle(t)
    assert fit.beta_lr_lo < fit.beta < fit.beta_lr_hi
    # small sample: the likelihood is skewed, the upper bound is further away than the lower one
    assert (fit.beta_lr_hi - fit.beta) > (fit.beta - fit.beta_lr_lo)


def test_small_sample_mle_shape_is_biased_high_mrr_less():
    rng = np.random.default_rng(6)
    b_mle, b_mrr = [], []
    for _ in range(400):
        t = stats.weibull_min.rvs(2.0, scale=100.0, size=10, random_state=rng)
        b_mle.append(wb.fit_mle(t).beta); b_mrr.append(wb.fit_mrr(t).beta)
    assert np.median(b_mle) > 2.0
    assert abs(np.median(b_mrr) - 2.0) < abs(np.median(b_mle) - 2.0)


def test_b_life_bounds_order():
    rng = np.random.default_rng(7)
    t = stats.weibull_min.rvs(1.5, scale=100.0, size=200, random_state=rng)
    fit = wb.fit_mle(t)
    b10, lo, hi = fit.b_life(0.10)
    assert lo < b10 < hi
    assert b10 == pytest.approx(fit.eta * (-np.log(0.9)) ** (1 / fit.beta))
