"""Regenerate every result: python -m scripts.run_all [--quick]

Writes PNG figures and results/summary.json. All README numbers come from that file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from relayret import analysis as an          # noqa: E402
from relayret import corrective as ca        # noqa: E402
from relayret import field as fl             # noqa: E402
from relayret import inrush as ir            # noqa: E402
from relayret import weld as wd              # noqa: E402
from scripts import figures as fg            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
CACHE = os.path.join(RES, "cache")
T_OBS = 910.0            # analysis cut-off, days after first production
MAIN_SEED = 2026
# main populations: production keeps running after the cut-off (needed for the forecast check);
# the analysis only ever sees units shipped and returned up to T_OBS
FP_MAIN = fl.FieldParams(n_weeks=182)


def r(x, n=3):
    """Round to n significant digits for the summary file."""
    if x is None or isinstance(x, (str, bool)):
        return x
    x = float(x)
    if not np.isfinite(x) or x == 0:
        return x
    return float(f"{x:.{n}g}")


# ------------------------------------------------------------------ 1. inrush physics
def inrush_section():
    out = {"table_108_check": []}
    err_i, err_e = [], []
    for P, (R1, C) in ir.IEC_TABLE_109.items():
        o = ir.simulate_make(R1 + ir.IEC_SOURCE_R, ir.IEC_SOURCE_L, C * 1e-6, np.array([np.pi / 2]), t_end=5e-3)
        ip, i2t = ir.IEC_TABLE_108[P]
        out["table_108_check"].append({"p_w": P, "ipeak_model": r(o["i_peak"][0], 4), "ipeak_std": ip,
                                       "i2t_model": r(o["i2t"][0], 3), "i2t_std": i2t})
        err_i.append(o["i_peak"][0] / ip - 1); err_e.append(o["i2t"][0] / i2t - 1)
    out["ipeak_max_abs_err_pct"] = r(100 * np.max(np.abs(err_i)))
    out["i2t_max_abs_err_pct"] = r(100 * np.max(np.abs(err_e)))
    out["ipeak_err_at_or_below_100w_pct"] = r(100 * np.max(np.abs(err_i[:4])))
    # closing angle: peak current and bounce-arc energy on the 200 W test circuit
    R1, C = ir.IEC_TABLE_109[200]
    b = ir.Bounce()
    rng = np.random.default_rng(5)
    to, tc = b.draw(400, rng)
    ang = np.arange(0, 180, 2.0)
    ipk, wa = [], []
    for a in ang:
        o = ir.simulate_make(R1 + ir.IEC_SOURCE_R, ir.IEC_SOURCE_L, C * 1e-6, np.full(400, np.radians(a)), to, tc)
        ipk.append(o["i_peak"].mean()); wa.append(o["w_arc"].mean())
    ipk, wa = np.array(ipk), np.array(wa)
    k90, k0, kb = 45, 0, int(np.argmin(wa))
    out["angle_200w"] = {
        "ipeak_90deg_a": r(ipk[k90]), "ipeak_0deg_a": r(ipk[k0]), "ipeak_ratio_90_to_0": r(ipk[k90] / ipk[k0]),
        "w_arc_90deg_j": r(wa[k90]), "w_arc_0deg_j": r(wa[k0]), "w_arc_ratio_90_to_0": r(wa[k90] / wa[k0]),
        "w_arc_min_j": r(wa[kb]), "w_arc_min_angle_deg": float(ang[kb] - 180.0 if ang[kb] > 90 else ang[kb]),
        "w_arc_ratio_90_to_min": r(wa[k90] / wa[kb]), "w_arc_45deg_over_90deg": r(wa[22] / wa[k90]),
        "w_arc_mean_random_j": r(wa.mean()),
    }
    # scaling with the number of 10 W lamps in parallel (high-inrush class), closing at 90 deg
    n_l = np.array([1, 2, 5, 10, 20, 40, 80, 160])
    scal = {}
    for line in ("stiff", "soft"):
        pk = []
        for n in n_l:
            R, L, Cc = ir.load_circuit(10.0 * n, "high", line)
            pk.append(ir.simulate_make(R, L, Cc, np.array([np.pi / 2]), t_end=6e-3)["i_peak"][0])
        scal[line] = [r(v) for v in pk]
    out["lamp_count_scaling"] = {"n_lamps": n_l.tolist(), "ipeak_a": scal,
                                 "ipeak_per_lamp_1": r(scal["stiff"][0]),
                                 "ipeak_per_lamp_160_stiff": r(scal["stiff"][-1] / 160),
                                 "ipeak_per_lamp_160_soft": r(scal["soft"][-1] / 160)}
    fg.fig_inrush(out, ang, ipk, wa, n_l, scal, os.path.join(RES, "fig1_inrush_validation.png"))
    return out


# ------------------------------------------------------------------ 2. weld model
def build_base(params=wd.WeldParams(), bounce=ir.Bounce(), tag="base"):
    grid = wd.StressGrid(bounce=bounce, cache_dir=CACHE, tag=tag)
    x_nom, e_ref, wbar = wd.calibrate(params, bounce)
    model = wd.WeldModel(grid, params, x_nominal=x_nom, e_ref=e_ref)
    return grid, model, x_nom, e_ref, wbar


def weld_section(grid, model, x_nom, e_ref, wbar):
    out = {"w50_nominal_j": r(np.exp(x_nom)), "w_arc_mean_rated_test_j": r(wbar),
           "sigma_w": model.params.sigma_w, "kappa": model.params.kappa, "per_op": {}}
    for P in (100, 200, 400, 800, 1600):
        for ic, lk in enumerate(wd.LAMP_KEYS):
            p = model.p_op(np.array([float(P)]), np.array([ic]), np.array([0]), np.array([x_nom]))[0]
            out["per_op"][f"{P}W_{lk}"] = {"p_weld_per_op": r(p),
                                          "pct_per_year_at_6_ops_day": r(100 * (1 - np.exp(-p * 6 * 365)))}
    p200 = out["per_op"]["200W_high"]["p_weld_per_op"]
    out["p_ratio_400_to_200"] = r(out["per_op"]["400W_high"]["p_weld_per_op"] / p200)
    out["p_ratio_800_to_200"] = r(out["per_op"]["800W_high"]["p_weld_per_op"] / p200)
    fg.fig_weld(model, x_nom, os.path.join(RES, "fig2_weld_probability.png"))
    return out


# ------------------------------------------------------------------ 3. three truths, blind analysis
def clean(d):
    return {k: (r(v) if isinstance(v, (float, np.floating)) else (list(v) if isinstance(v, tuple) else v))
            for k, v in d.items() if not k.startswith("_")}


def truths_section(model):
    out, keep = {}, {}
    for name, tr in fl.TRUTHS.items():
        pop = fl.generate(tr, model, FP_MAIN, seed=MAIN_SEED)
        obs = fl.observe(pop, T_OBS)
        dec = an.decide(obs, n_sim=999, seed=1)
        pw = an.production_week_test(obs, n_sim=999, seed=1)
        wv = an.weibull_views(obs)
        ld = an.load_test(obs)
        tru = fl.truth_summary(pop, T_OBS)
        tw = tr.batch_weeks
        out[name] = {
            "hidden_truth": {k: r(v) for k, v in tru.items()} | {"batch_weeks": [min(tw), max(tw)] if tw else None},
            "blind": {"verdict": dec.verdict, "decision": clean(dec.as_dict()), "production_week": clean(pw),
                      "load": clean(ld), "weibull": clean(wv),
                      "other_cause_returns": int((~obs.is_weld).sum())},
            "check": {"verdict_correct": dec.verdict == an.TRUE_VERDICT[name],
                      "batch_fraction_estimated": r(dec.batch_fraction),
                      "batch_fraction_true": r(tru["batch_share_of_weld_returns"]),
                      "window_found": list(dec.window) if dec.window else None,
                      "window_true": [min(tw), max(tw)] if tw else None},
        }
        keep[name] = (pop, obs, pw, wv)
    fg.fig_nevada(keep, os.path.join(RES, "fig3_nevada.png"))
    fg.fig_weibull(keep, os.path.join(RES, "fig4_weibull.png"))
    return out, keep


# ------------------------------------------------------------------ 4. replicate study
def replicate_section(model, reps):
    cutoffs = [350, 380, 400, 420, 440, 460, 500, 550, 600, 700, 800, 910]
    names = list(fl.TRUTHS)
    correct = {n: np.zeros((reps, len(cutoffs))) for n in names}
    correct_nl = {n: np.zeros((reps, len(cutoffs))) for n in names}
    n_ret = {n: np.zeros((reps, len(cutoffs))) for n in names}
    verd = {n: [dict.fromkeys(("batch", "design", "mixed", "undetermined"), 0) for _ in cutoffs] for n in names}
    verd_nl = {n: [dict.fromkeys(("batch", "design", "mixed", "undetermined"), 0) for _ in cutoffs] for n in names}
    naive_p = {n: [] for n in names}
    metrics = {n: {k: [] for k in ("rate_pct", "mle_beta", "mrr_beta", "share_over_rated", "scan_lr",
                                   "trend_slope", "batch_fraction", "median_case_w")} for n in names}
    for name in names:
        for i in range(reps):
            pop = fl.generate(fl.TRUTHS[name], model, seed=1000 + i)
            for j, t in enumerate(cutoffs):
                obs = fl.observe(pop, t)
                d = an.decide(obs, seed=i)
                d2 = an.decide(obs, seed=i, use_load=False)
                correct[name][i, j] = d.verdict == an.TRUE_VERDICT[name]
                correct_nl[name][i, j] = d2.verdict == an.TRUE_VERDICT[name]
                n_ret[name][i, j] = d.n_weld
                verd[name][j][d.verdict] += 1
                verd_nl[name][j][d2.verdict] += 1
            pw = an.production_week_test(obs, seed=i)
            naive_p[name].append(pw.get("naive_batch_p", 1.0))
            wv = an.weibull_views(obs)
            ld = an.load_test(obs)
            m = metrics[name]
            m["rate_pct"].append(100 * pw["n_weld"] / obs.shipped.sum())
            m["mle_beta"].append(wv.get("mle_beta", np.nan)); m["mrr_beta"].append(wv.get("mrr_beta", np.nan))
            m["share_over_rated"].append(ld["share_cases_over_rated"]); m["median_case_w"].append(ld["median_case_w"])
            m["scan_lr"].append(pw.get("scan_lr", 0.0)); m["trend_slope"].append(pw["trend_slope"])
            m["batch_fraction"].append(pw["batch_fraction"])
    out = {"reps_per_truth": reps, "cutoff_days": cutoffs, "by_truth": {}, "views": {}}

    def needed(pc, nr, level=0.9):
        """Mean number of welded returns at the first cut-off from which P(correct) stays >= level."""
        ok = pc >= level
        for j in range(len(cutoffs)):
            if ok[j:].all():
                return int(round(nr[j])), cutoffs[j]
        return None, None

    for name in names:
        pc, pcn, nr = correct[name].mean(0), correct_nl[name].mean(0), n_ret[name].mean(0)
        n90, d90 = needed(pc, nr)
        n90n, d90n = needed(pcn, nr)
        out["by_truth"][name] = {
            "p_correct": [r(v) for v in pc], "p_correct_no_load_info": [r(v) for v in pcn],
            "mean_weld_returns": [r(v) for v in nr],
            "returns_needed_90pct": n90, "day_90pct": d90,
            "returns_needed_90pct_no_load_info": n90n, "day_90pct_no_load_info": d90n,
            "p_correct_final": r(pc[-1]), "p_correct_final_no_load_info": r(pcn[-1]),
            "verdict_counts": verd[name], "verdict_counts_no_load_info": verd_nl[name],
            "naive_scan_flags_batch_share": r(float(np.mean(np.array(naive_p[name]) <= 0.01))),
        }
    for k in metrics[names[0]]:
        a, b, c = (np.array(metrics[n][k], dtype=float) for n in names)
        out["views"][k] = {
            "A_median": r(np.nanmedian(a)), "B_median": r(np.nanmedian(b)), "C_median": r(np.nanmedian(c)),
            "A_range": [r(np.nanmin(a)), r(np.nanmax(a))], "B_range": [r(np.nanmin(b)), r(np.nanmax(b))],
            "separation_A_vs_B": r(abs(2 * an.auc(a, b) - 1)),
        }
    fg.fig_returns_needed(out, os.path.join(RES, "fig5_returns_needed.png"))
    fg.fig_views(metrics, out, os.path.join(RES, "fig6_views_separation.png"))
    return out


# ------------------------------------------------------------------ 5. corrective actions
def option_models(grid, model, x_nom, e_ref, params, bounce, inst):
    """WeldModel and evaluation settings for every option."""
    mods = {"baseline": {"model": model}, "relay": {"model": model,
                                                    "x_shift": float(np.log(params.material[ca.RELAY_FACTOR]))}}
    zc = {}
    for key, sig in ca.ZC_SIGMA_MS.items():
        tgt = ca.best_zc_target(grid, params, x_nom, e_ref, sig, inst)
        wt = wd.theta_weights("zero_cross", tgt, sig)
        mods[key] = {"model": wd.WeldModel(grid, params, w_theta=wt, x_nominal=x_nom, e_ref=e_ref), "w_theta": wt}
        zc[key] = {"sigma_ms": sig, "target_deg": tgt}
    g_cold = ca.NtcGrid(None, bounce=bounce, cache_dir=CACHE)
    g_hot = ca.NtcGrid(30.0, bounce=bounce, cache_dir=CACHE)
    m_cold = wd.WeldModel(g_cold, params, x_nominal=x_nom, e_ref=e_ref)
    m_hot = wd.WeldModel(g_hot, params, x_nominal=x_nom, e_ref=e_ref)
    m_cold.ptab = (1 - ca.NTC_HOT_SHARE) * m_cold.ptab + ca.NTC_HOT_SHARE * m_hot.ptab
    m_cold.wbar = (1 - ca.NTC_HOT_SHARE) * m_cold.wbar + ca.NTC_HOT_SHARE * m_hot.wbar
    mods["ntc"] = {"model": m_cold, "r_extra": float(ca.ntc_resistance(ca.T_AMB_DEVICE))}
    mods["derating"] = {"model": model, "derating": True}
    mods["hybrid"] = {"model": model, "hybrid": True}
    return mods, zc


def eval_option(key, mod, inst, params, bounce, x_nom, e_ref):
    model = mod["model"]
    xs = mod.get("x_shift", 0.0)
    res = {}
    for label, yrs in (("weld_pct_2y", 2.0), ("weld_pct_10y", 10.0)):
        if mod.get("hybrid"):
            v = 1.0 - np.exp(-ca.HYBRID_FIT * 1e-9 * 8760 * yrs)      # semiconductor short, load stuck on
        elif mod.get("derating"):
            k = np.ceil(inst["p_led"] / ca.DERATING_LIMIT_W)
            split = ca.weld_fraction(model, inst, yrs, p_led=inst["p_led"] / k, channels=k)
            base = ca.weld_fraction(model, inst, yrs)
            v = ca.DERATING_COMPLIANCE * split + (1 - ca.DERATING_COMPLIANCE) * base
        else:
            v = ca.weld_fraction(model, inst, yrs, x_shift=xs)
        res[label] = r(100 * v)
    wt = mod.get("w_theta", wd.theta_weights())
    for P in (200.0, 400.0):
        if mod.get("hybrid"):
            res[f"test_pass_{int(P)}w"] = 1.0
        elif mod.get("derating"):
            res[f"test_pass_{int(P)}w"] = r(ca.endurance_pass(bounce, params, x_nom, e_ref, min(P, 200.0), wt), 4)
        else:
            res[f"test_pass_{int(P)}w"] = r(ca.endurance_pass(bounce, params, x_nom + xs, e_ref, P, wt,
                                                              r_extra=mod.get("r_extra", 0.0)), 4)
    return res


WARRANTY_COST_EUR = 60.0     # cost of one field weld to the maker (assumption)
REQ_WELD_10Y_PCT = 0.5       # requirement: at most 0.5 % of units welded in 10 years on the LED-heavy mix
REQ_LOSS_W = 1.0             # at most 1 W extra dissipation per channel at 16 A


def trade_section(grid, model, x_nom, e_ref, params, bounce, tag="base"):
    inst = ca.reference_installs()
    mods, zc = option_models(grid, model, x_nom, e_ref, params, bounce, inst)
    rows = {}
    for opt in ca.OPTIONS:
        res = eval_option(opt.key, mods[opt.key], inst, params, bounce, x_nom, e_ref)
        base10 = rows["baseline"]["weld_pct_10y"] if rows else res["weld_pct_10y"]
        res["reduction_factor_10y"] = r(base10 / max(res["weld_pct_10y"], 1e-12))
        res["bom_delta_eur"] = opt.bom_delta_eur
        res["loss_w_at_16a"] = opt.loss_w_at_16a
        res["expected_cost_eur"] = r(opt.bom_delta_eur + WARRANTY_COST_EUR * res["weld_pct_10y"] / 100.0)
        res["meets_weld_req"] = bool(res["weld_pct_10y"] <= REQ_WELD_10Y_PCT)
        res["meets_loss_req"] = bool(opt.loss_w_at_16a <= REQ_LOSS_W)
        res["independent_of_installer"] = not opt.installer_dependent
        res["feasible"] = bool(res["meets_weld_req"] and res["meets_loss_req"] and not opt.installer_dependent)
        rows[opt.key] = res
    feas = {k: v for k, v in rows.items() if v["feasible"]}
    decision = min(feas, key=lambda k: feas[k]["expected_cost_eur"]) if feas else None
    out = {"options": rows, "zero_cross_targets": zc, "decision": decision,
           "requirement_weld_10y_pct": REQ_WELD_10Y_PCT, "requirement_loss_w": REQ_LOSS_W,
           "warranty_cost_eur": WARRANTY_COST_EUR,
           "ntc": {"r_cold_ohm_at_40c": r(ca.ntc_resistance(ca.T_AMB_DEVICE)),
                   "r_restart_30s_800w_ohm": r(ca.ntc_restart_resistance(800.0, 30.0)),
                   "steady_temp_800w_c": r(ca.ntc_steady_temp(800.0 / (ir.V_RMS * ca.LED_PF))),
                   "loss_w_at_16a": ca.NTC_PMAX}}
    return out, mods, inst


def zero_cross_section(grid, model, x_nom, e_ref, params, inst):
    sig = np.array([0.0, 0.1, 0.25, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0, 5.0])
    base = ca.weld_fraction(model, inst, 10.0)
    ptab = grid.p_table(params.sigma_w)
    red_opt, red_zero, tg = [], [], []
    for s in sig:
        t = ca.best_zc_target(grid, params, x_nom, e_ref, s, inst)
        m1 = wd.WeldModel(grid, params, w_theta=wd.theta_weights("zero_cross", t, s), x_nominal=x_nom, e_ref=e_ref,
                          p_table=ptab)
        m0 = wd.WeldModel(grid, params, w_theta=wd.theta_weights("zero_cross", 0.0, s), x_nominal=x_nom, e_ref=e_ref,
                          p_table=ptab)
        red_opt.append(base / ca.weld_fraction(m1, inst, 10.0))
        red_zero.append(base / ca.weld_fraction(m0, inst, 10.0))
        tg.append(t)
    ideal = red_opt[0]
    out = {"sigma_ms": sig.tolist(), "reduction_factor_best_target": [r(v) for v in red_opt],
           "reduction_factor_target_at_zero": [r(v) for v in red_zero], "best_target_deg": tg,
           "ideal_reduction_factor": r(ideal),
           "share_of_ideal_log_benefit_pct": {f"{s:g}ms": r(100 * np.log(v) / np.log(ideal))
                                              for s, v in zip(sig, red_opt)},
           "sigma_ms_for_half_log_benefit": r(float(np.interp(0.5, (np.log(red_opt) / np.log(ideal))[::-1], sig[::-1])))}
    fg.fig_zero_cross(out, os.path.join(RES, "fig7_zero_cross.png"))
    return out


def sensitivity_section(reps_quick):
    """Do the conclusions survive the deciding assumptions?"""
    cases = {
        "base": (wd.WeldParams(), ir.Bounce(), "base"),
        "sigma_w_0.5": (wd.WeldParams(sigma_w=0.5), ir.Bounce(), "base"),
        "sigma_w_1.2": (wd.WeldParams(sigma_w=1.2), ir.Bounce(), "base"),
        "kappa_0": (wd.WeldParams(kappa=0.0), ir.Bounce(), "base"),
        "kappa_1.5": (wd.WeldParams(kappa=1.5), ir.Bounce(), "base"),
        "pass_prob_0.999": (wd.WeldParams(pass_prob=0.999), ir.Bounce(), "base"),
        "rated_400w": (wd.WeldParams(rated_p=400.0), ir.Bounce(), "base"),
        "short_bounce_200us": (wd.WeldParams(), ir.Bounce(d1_med=200e-6), "shortb"),
    }
    out = {}
    for name, (params, bounce, tag) in cases.items():
        grid, model, x_nom, e_ref, wbar = build_base(params, bounce, tag)
        inst = ca.reference_installs()
        base = ca.weld_fraction(model, inst, 10.0)
        relay = ca.weld_fraction(model, inst, 10.0, x_shift=float(np.log(params.material[ca.RELAY_FACTOR])))
        row = {"baseline_weld_pct_10y": r(100 * base), "relay_reduction": r(base / relay)}
        ptab = grid.p_table(params.sigma_w)
        for key, s in dict(ca.ZC_SIGMA_MS, zc_ideal=0.0).items():
            t = ca.best_zc_target(grid, params, x_nom, e_ref, s, inst)
            m = wd.WeldModel(grid, params, w_theta=wd.theta_weights("zero_cross", t, s), x_nominal=x_nom, e_ref=e_ref,
                             p_table=ptab)
            row[f"{key}_reduction"] = r(base / ca.weld_fraction(m, inst, 10.0))
        # blind verdicts on the three truths under this physics (truth knobs unchanged)
        hits = {}
        for tn, tr in fl.TRUTHS.items():
            ok, nret = 0, []
            for i in range(reps_quick):
                pop = fl.generate(tr, model, seed=500 + i)
                obs = fl.observe(pop, T_OBS)
                d = an.decide(obs, seed=i)
                ok += d.verdict == an.TRUE_VERDICT[tn]; nret.append(d.n_weld)
            hits[tn] = {"correct": int(ok), "of": reps_quick, "mean_weld_returns": r(np.mean(nret))}
        row["verdicts"] = hits
        out[name] = row
    return out


# ------------------------------------------------------------------ 6. forecast
def forecast_section(model, mods, trade, keep, n_fc_reps=10):
    fp = FP_MAIN
    tr = fl.TRUTHS["B_design"]
    cutin = 140
    n_per = 13
    key = trade["decision"] or "relay"
    mod = mods[key]
    m_ca = mod["model"]
    pop = keep["B_design"][0]                 # the same population the 8D report is written on
    if "x_shift" in mod:
        m_ca = wd.WeldModel(model.grid, model.params, x_nominal=model.x_nominal + mod["x_shift"], e_ref=model.e_ref)
    pop_ca = fl.generate(tr, m_ca, fp, seed=MAIN_SEED)
    obs = fl.observe(pop, T_OBS)
    pw = an.production_week_test(obs, n_sim=199, seed=2)
    ca_factor = trade["options"][key]["weld_pct_2y"] / trade["options"]["baseline"]["weld_pct_2y"]
    f_no = an.forecast(obs, pw, fp.units_per_week, n_per)
    f_ca = an.forecast(obs, pw, fp.units_per_week, n_per, cutin_week=cutin, ca_factor=ca_factor)

    def actual(p, p_new=None):
        t_ret, ok = p["t_return"].copy(), (p["weld_first"] & p["will_return"]).copy()
        if p_new is not None:
            new = p["week"] >= cutin
            t_ret[new] = p_new["t_return"][new]
            ok[new] = (p_new["weld_first"] & p_new["will_return"])[new]
        k = ((t_ret - T_OBS) // 28.0).astype(int)
        sel = ok & (k >= 0) & (k < n_per)
        return np.bincount(k[sel], minlength=n_per)[:n_per]

    a_no, a_ca = actual(pop), actual(pop, pop_ca)
    hist_k = ((obs.t_return[obs.is_weld]) // 28.0).astype(int)
    hist = np.bincount(hist_k, minlength=int(T_OBS // 28) + 1)
    out = {"truth": "B_design", "corrective_action": key, "cutin_week": cutin, "periods_28d": n_per,
           "ca_hazard_factor": r(ca_factor),
           "forecast_no_ca_total": r(f_no.sum()), "actual_no_ca_total": int(a_no.sum()),
           "forecast_with_ca_total": r(f_ca.sum()), "actual_with_ca_total": int(a_ca.sum()),
           "forecast_error_no_ca_pct": r(100 * (f_no.sum() / a_no.sum() - 1)),
           "forecast_error_with_ca_pct": r(100 * (f_ca.sum() / a_ca.sum() - 1)),
           "returns_avoided_forecast": r(f_no.sum() - f_ca.sum()), "returns_avoided_actual": int(a_no.sum() - a_ca.sum()),
           "share_of_next_year_returns_from_units_built_before_cutin_pct": r(100 * (1 - (f_no.sum() - f_ca.sum()) / f_no.sum())),
           "weld_returns_to_date": int(obs.is_weld.sum()),
           "returns_last_6_full_periods": [int(v) for v in hist[-7:-1]]}
    # how good is the blind forecast in general? ten more populations of the same truth, no action
    errs = []
    for sd in range(3000, 3000 + n_fc_reps):
        p2 = fl.generate(tr, model, fp, seed=sd)
        o2 = fl.observe(p2, T_OBS)
        f2 = an.forecast(o2, an.production_week_test(o2, n_sim=199, seed=sd), fp.units_per_week, n_per)
        k2 = ((p2["t_return"] - T_OBS) // 28.0).astype(int)
        act = int(np.sum(p2["weld_first"] & p2["will_return"] & (k2 >= 0) & (k2 < n_per)))
        errs.append(100 * (f2.sum() / act - 1))
    out["forecast_error_replicates_pct"] = {"n": n_fc_reps, "median": r(np.median(errs)),
                                            "min": r(np.min(errs)), "max": r(np.max(errs)),
                                            "mean_abs": r(np.mean(np.abs(errs)))}
    fg.fig_forecast(hist, f_no, f_ca, a_no, a_ca, T_OBS, os.path.join(RES, "fig9_forecast.png"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="fewer replicates (used in CI)")
    args = ap.parse_args()
    os.makedirs(RES, exist_ok=True)
    t0 = time.time()
    summary = {"note": "Simulated study. No hardware, no real return data.", "quick": bool(args.quick),
               "t_obs_days": T_OBS}
    summary["inrush"] = inrush_section()
    print(f"[{time.time() - t0:5.0f} s] inrush")
    params, bounce = wd.WeldParams(), ir.Bounce()
    grid, model, x_nom, e_ref, wbar = build_base(params, bounce)
    summary["weld"] = weld_section(grid, model, x_nom, e_ref, wbar)
    print(f"[{time.time() - t0:5.0f} s] weld model")
    summary["truths"], keep = truths_section(model)
    print(f"[{time.time() - t0:5.0f} s] three truths")
    summary["replicates"] = replicate_section(model, 6 if args.quick else 30)
    print(f"[{time.time() - t0:5.0f} s] replicate study")
    summary["trade"], mods, inst = trade_section(grid, model, x_nom, e_ref, params, bounce)
    fg.fig_trade(summary["trade"], os.path.join(RES, "fig8_trade_study.png"))
    summary["zero_cross"] = zero_cross_section(grid, model, x_nom, e_ref, params, inst)
    print(f"[{time.time() - t0:5.0f} s] trade study")
    summary["sensitivity"] = sensitivity_section(3 if args.quick else 8)
    print(f"[{time.time() - t0:5.0f} s] sensitivity")
    summary["forecast"] = forecast_section(model, mods, summary["trade"], keep, 3 if args.quick else 10)
    fg.fig_ishikawa(os.path.join(RES, "ishikawa.png"))
    name = "summary_quick.json" if args.quick else "summary.json"
    with open(os.path.join(RES, name), "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, indent=1)
    print(f"[{time.time() - t0:5.0f} s] wrote results/{name}")


if __name__ == "__main__":
    main()
