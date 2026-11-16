"""Weld model, field generator, blind analysis and corrective-action physics."""
import os

import numpy as np
import pytest

from relayret import analysis as an
from relayret import corrective as ca
from relayret import field as fl
from relayret import inrush as ir
from relayret import weld as wd

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "cache")


@pytest.fixture(scope="session")
def base():
    params, bounce = wd.WeldParams(), ir.Bounce()
    grid = wd.StressGrid(bounce=bounce, cache_dir=CACHE)
    x_nom, e_ref, wbar = wd.calibrate(params, bounce)
    return {"params": params, "bounce": bounce, "grid": grid, "x_nom": x_nom, "e_ref": e_ref,
            "model": wd.WeldModel(grid, params, x_nominal=x_nom, e_ref=e_ref)}


@pytest.fixture(scope="session")
def pops(base):
    # the main populations of scripts.run_all (production continues after the cut-off)
    fp = fl.FieldParams(n_weeks=182)
    return {n: fl.generate(t, base["model"], fp, seed=2026) for n, t in fl.TRUTHS.items()}


# ------------------------------------------------------------------ weld model
def test_calibration_hits_the_rated_test(base):
    W = wd.endurance_energy(base["params"].rated_p, base["bounce"])
    s = wd.endurance_survival(W, wd.theta_weights(), base["x_nom"], base["params"], base["e_ref"])
    assert s == pytest.approx(base["params"].pass_prob, abs=1e-4)


def test_weld_probability_rises_with_load_and_falls_with_threshold(base):
    m, x = base["model"], base["x_nom"]
    P = np.array([50.0, 100.0, 200.0, 400.0, 800.0, 1600.0])
    z = np.zeros(P.size, dtype=int)
    p = m.p_op(P, z, z, np.full(P.size, x))
    assert np.all(np.diff(p) > 0)
    assert np.all(m.p_op(P, z, z, np.full(P.size, x + 1.0)) < p)
    # lamp classes: high inrush is worst
    assert m.p_op(P, z, z, np.full(P.size, x))[3] > m.p_op(P, z + 1, z, np.full(P.size, x))[3] > \
        m.p_op(P, z + 2, z, np.full(P.size, x))[3]


def test_wear_raises_the_hazard(base):
    m = base["model"]
    one = np.array([800.0]); z = np.array([0])
    n_ops = np.linspace(0, 40000, 25)[None, :]
    H = m.cum_hazard(one, z, z, np.array([base["x_nom"]]), n_ops)[0]
    assert H[12] < 0.5 * H[24]          # second half of the life is worse than the first


def test_theta_weights():
    assert wd.theta_weights().sum() == pytest.approx(1.0)
    w = wd.theta_weights("zero_cross", 0.0, 0.0)
    assert w[0] == 1.0 and w.sum() == 1.0
    wide = wd.theta_weights("zero_cross", 0.0, 50.0)
    assert np.max(np.abs(wide - 1.0 / wd.N_THETA)) < 1e-3     # huge scatter = random closing
    w = wd.theta_weights("zero_cross", -18.0, 0.5)             # 18 deg = 1 ms before the zero
    assert np.degrees(wd.THETA[np.argmax(w)]) == pytest.approx(162.0, abs=2.0)


def test_zero_cross_helps_and_scatter_takes_it_away(base):
    g, p, x, e = base["grid"], base["params"], base["x_nom"], base["e_ref"]
    inst = ca.reference_installs(n=4000)
    f = lambda s: ca.weld_fraction(wd.WeldModel(g, p, w_theta=wd.theta_weights("zero_cross", -10.0, s),
                                                x_nominal=x, e_ref=e), inst, 10.0)
    rnd = ca.weld_fraction(base["model"], inst, 10.0)
    assert f(0.1) < f(1.0) < f(3.0) <= rnd * 1.05
    assert f(0.1) < 0.2 * rnd


# ------------------------------------------------------------------ field generator
def test_generator_is_deterministic(base):
    a = fl.generate(fl.TRUTHS["B_design"], base["model"], seed=5)
    b = fl.generate(fl.TRUTHS["B_design"], base["model"], seed=5)
    assert np.array_equal(a["t_weld"], b["t_weld"]) and np.array_equal(a["t_return"], b["t_return"])


def test_truths_have_similar_return_rates_but_different_causes(pops):
    s = {n: fl.truth_summary(p, 910.0) for n, p in pops.items()}
    rates = [v["weld_return_rate_pct"] for v in s.values()]
    assert max(rates) / min(rates) < 1.35
    assert s["A_batch"]["batch_share_of_weld_returns"] > 0.85
    assert s["B_design"]["batch_share_of_weld_returns"] == 0.0
    assert 0.25 < s["C_mixed"]["batch_share_of_weld_returns"] < 0.75
    assert s["A_batch"]["median_led_w_weld_returns"] < 200.0 < s["B_design"]["median_led_w_weld_returns"]


def test_reporting_effects(pops):
    pop = pops["B_design"]
    obs = fl.observe(pop, 910.0)
    tru = fl.truth_summary(pop, 910.0)
    assert obs.is_weld.sum() == tru["weld_returns"] < tru["weld_failures"]      # not every failure comes back
    assert np.all(obs.t_return <= 910.0)
    assert 0.2 < np.isnan(obs.p_led).mean() < 0.8                               # questionnaire only on some
    assert obs.shipped.sum() > 100 * obs.week.size                              # almost everything is censored
    early = fl.observe(pop, 500.0)
    assert early.is_weld.sum() < obs.is_weld.sum() and early.n_weeks < obs.n_weeks


def test_no_led_no_weld(pops):
    pop = pops["B_design"]
    assert np.all(np.isinf(pop["t_weld"][pop["seg"] == 0]))


# ------------------------------------------------------------------ blind analysis
def test_scan_finds_injected_window_and_ignores_flat_data():
    rng = np.random.default_rng(0)
    E = np.full(100, 2.0)
    flat = rng.poisson(E).astype(float)
    lr_flat, _, _ = an.scan(flat, E * flat.sum() / E.sum())
    hot = flat.copy(); hot[40:46] += rng.poisson(12.0, 6)
    lr_hot, s, ln = an.scan(hot, E * hot.sum() / E.sum())
    assert lr_hot > 5 * max(lr_flat, 1.0)
    assert 38 <= s <= 42 and 4 <= ln <= 8


def test_trend_fit_recovers_slope():
    rng = np.random.default_rng(1)
    n = 120
    wk = (np.arange(n) - n / 2) / n
    E = np.full(n, 5.0)
    O = rng.poisson(E * np.exp(1.2 * wk)).astype(float)
    _, b, _, _ = an.fit_trend(O, E)
    assert float(b) == pytest.approx(1.2, abs=0.35)


def test_blind_verdicts_on_main_seed(pops):
    for name, pop in pops.items():
        d = an.decide(fl.observe(pop, 910.0), n_sim=199, seed=1)
        assert d.verdict == an.TRUE_VERDICT[name], (name, d)


def test_window_found_matches_the_weak_lot(pops):
    d = an.decide(fl.observe(pops["A_batch"], 910.0), seed=1)
    lo, hi = d.window
    assert abs(lo - 44) <= 1 and abs(hi - 51) <= 1
    assert an.decide(fl.observe(pops["B_design"], 910.0), seed=1).window is None


def test_too_few_returns_gives_no_verdict(pops):
    d = an.decide(fl.observe(pops["A_batch"], 330.0), seed=1)
    assert d.verdict == "undetermined"


def test_weibull_view_runs_and_is_heavily_censored(pops):
    wv = an.weibull_views(fl.observe(pops["B_design"], 910.0))
    assert wv["n_susp"] > 100 * wv["n_fail"]
    assert wv["mle_beta_lo"] < wv["mle_beta"] < wv["mle_beta_hi"]
    assert 0.3 < wv["mrr_beta"] < 2.0


def test_forecast_with_action_is_lower(pops):
    obs = fl.observe(pops["B_design"], 910.0)
    pw = an.production_week_test(obs, seed=1)
    f0 = an.forecast(obs, pw, 600, 13)
    f1 = an.forecast(obs, pw, 600, 13, cutin_week=135, ca_factor=0.1)
    assert np.all(f0 > 0) and f1.sum() < f0.sum()
    assert f1[0] == pytest.approx(f0[0], rel=0.05)      # nothing built after cut-in has aged yet


def test_auc():
    assert an.auc([3, 4, 5], [0, 1, 2]) == 1.0
    assert an.auc([1, 2], [1, 2]) == 0.5


# ------------------------------------------------------------------ corrective actions
def test_ntc_physics():
    assert float(ca.ntc_resistance(25.0)) == pytest.approx(1.0)
    assert float(ca.ntc_resistance(100.0)) < 0.2
    t = ca.ntc_steady_temp(3.0)
    assert 60.0 < t < 170.0
    assert 3.0 ** 2 * float(ca.ntc_resistance(t)) == pytest.approx(ca.NTC_DELTA * (t - ca.T_AMB_DEVICE), rel=1e-3)
    cold = float(ca.ntc_resistance(ca.T_AMB_DEVICE))
    assert ca.ntc_restart_resistance(800.0, 3600.0) == pytest.approx(cold, rel=1e-3)   # fully cooled
    assert ca.ntc_restart_resistance(800.0, 10.0) < 0.5 * cold                         # hot restart


def test_series_resistance_cuts_peak_more_than_arc_energy():
    rng = np.random.default_rng(2)
    to, tc = ir.Bounce().draw(300, rng)
    R, L, C = ir.load_circuit(800.0, "high", "stiff")
    th = np.full(300, np.pi / 2)
    a = ir.simulate_make(R, L, C, th, to, tc)
    b = ir.simulate_make(R + 0.64, L, C, th, to, tc)
    peak_cut = a["i_peak"].mean() / b["i_peak"].mean()
    arc_cut = a["w_arc"].mean() / b["w_arc"].mean()
    assert peak_cut > 1.5 and arc_cut < peak_cut


def test_relay_upgrade_and_derating_reduce_welds(base):
    inst = ca.reference_installs(n=4000)
    m = base["model"]
    b = ca.weld_fraction(m, inst, 10.0)
    b2 = ca.weld_fraction(m, inst, 2.0)
    # the stronger contact helps a lot early; over 10 years contact wear eats part of the margin
    assert ca.weld_fraction(m, inst, 2.0, x_shift=np.log(3.4)) < 0.2 * b2
    assert ca.weld_fraction(m, inst, 10.0, x_shift=np.log(3.4)) < 0.6 * b
    k = np.ceil(inst["p_led"] / 200.0)
    assert ca.weld_fraction(m, inst, 10.0, p_led=inst["p_led"] / k, channels=k) < 0.2 * b
    assert b2 < b


def test_endurance_pass_orders(base):
    args = (base["bounce"], base["params"], base["x_nom"], base["e_ref"])
    wt = wd.theta_weights()
    p200, p400 = ca.endurance_pass(*args, 200.0, wt), ca.endurance_pass(*args, 400.0, wt)
    assert p200 == pytest.approx(0.95, abs=1e-3) and p400 < p200
    assert ca.endurance_pass(base["bounce"], base["params"], base["x_nom"] + np.log(3.4), base["e_ref"], 400.0, wt) > p400
