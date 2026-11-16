"""Plots for scripts.run_all. Every figure is drawn from numbers computed in the run."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from relayret import analysis as an
from relayret import inrush as ir
from relayret import weibull as wb
from relayret import weld as wd

COL = {"A_batch": "#b03a2e", "B_design": "#1f618d", "C_mixed": "#7d6608"}
LAB = {"A_batch": "Truth A: weak contact lot", "B_design": "Truth B: design limit", "C_mixed": "Truth C: both"}
plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3, "figure.dpi": 130})


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fig_inrush(out, ang, ipk, wa, n_l, scal, path):
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    P = [d["p_w"] for d in out["table_108_check"]]
    ax[0].loglog(P, [d["ipeak_std"] for d in out["table_108_check"]], "ko", label="Ipeak, IEC 60669-2-1 Table 108")
    ax[0].loglog(P, [d["ipeak_model"] for d in out["table_108_check"]], "k-", label="Ipeak, model")
    ax[0].loglog(P, [d["i2t_std"] for d in out["table_108_check"]], "s", color="#b03a2e", label="I2t, Table 108")
    ax[0].loglog(P, [d["i2t_model"] for d in out["table_108_check"]], "-", color="#b03a2e", label="I2t, model")
    ax[0].set_xticks([15, 30, 60, 100, 200, 400]); ax[0].set_xticklabels(["15", "30", "60", "100", "200", "400"])
    ax[0].minorticks_off()
    ax[0].set_xlabel("rated lamp power [W]"); ax[0].set_ylabel("Ipeak [A]  /  I2t [A2s]")
    ax[0].set_title("Model check against the standard's test table"); ax[0].legend(fontsize=7)
    a2 = np.where(ang > 90, ang - 180, ang); o = np.argsort(a2)
    ax[1].plot(a2[o], ipk[o] / ipk.max(), "k-", label="peak current")
    ax[1].plot(a2[o], wa[o] / wa.max(), "-", color="#b03a2e", label="bounce-arc energy")
    ax[1].set_xlabel("closing angle relative to voltage zero [deg]"); ax[1].set_ylabel("relative to maximum")
    ax[1].set_title("200 W lamp test circuit: what the closing angle changes"); ax[1].legend()
    ax[2].loglog(n_l, scal["stiff"], "o-", color="k", label="stiff supply (0.32 ohm + 126 uH)")
    ax[2].loglog(n_l, scal["soft"], "s-", color="#1f618d", label="soft supply (0.70 ohm + 400 uH)")
    ax[2].loglog(n_l, scal["stiff"][0] * n_l, "k:", label="N x one lamp")
    ax[2].set_xlabel("number of 10 W lamps on the channel"); ax[2].set_ylabel("peak inrush at 90 deg [A]")
    ax[2].set_title("Peak inrush saturates on the line impedance"); ax[2].legend(fontsize=7)
    _save(fig, path)


def fig_weld(model, x_nom, path):
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    P = np.geomspace(20, 1600, 60)
    for ic, lk in enumerate(wd.LAMP_KEYS):
        p = model.p_op(P, np.full(P.size, ic), np.zeros(P.size, dtype=int), np.full(P.size, x_nom))
        ax[0].loglog(P, p, label=f"{lk}-inrush lamps")
    ax[0].axvline(200, color="k", ls="--", lw=0.8); ax[0].text(205, 1e-15, "rated 200 W", fontsize=7)
    ax[0].set_ylim(1e-16, 1e-2); ax[0].set_xlabel("LED load on the channel [W]")
    ax[0].set_ylabel("weld probability per operation"); ax[0].set_title("Nominal relay, random closing angle")
    ax[0].legend()
    for f, lab in ((1.0, "nominal AgSnO2"), (0.22, "weak lot, factor 0.22"), (0.065, "weak lot, factor 0.065"),
                   (3.4, "tungsten pre-make")):
        p = model.p_op(P, np.zeros(P.size, dtype=int), np.zeros(P.size, dtype=int), np.full(P.size, x_nom + np.log(f)))
        ax[1].loglog(P, 100 * (1 - np.exp(-p * 6 * 365)), label=lab)
    ax[1].axvline(200, color="k", ls="--", lw=0.8)
    ax[1].set_ylim(1e-4, 100); ax[1].set_xlabel("LED load, high-inrush lamps [W]")
    ax[1].set_ylabel("welded per year at 6 operations/day [%]")
    ax[1].set_title("The same curve shifts with the weld threshold"); ax[1].legend(fontsize=7)
    _save(fig, path)


def fig_nevada(keep, path):
    fig, ax = plt.subplots(2, 3, figsize=(13, 7), gridspec_kw={"height_ratios": [3, 1.6]})
    for j, (name, (pop, obs, pw, wv)) in enumerate(keep.items()):
        counts, shipped = an.nevada(obs)
        rate = 1000 * counts / shipped[:, None]
        im = ax[0, j].imshow(rate, aspect="auto", origin="upper", cmap="Reds", vmin=0, vmax=max(rate.max(), 1e-9))
        ax[0, j].set_title(f"{LAB[name]}\n{int(counts.sum())} welded returns of {int(obs.shipped.sum())} shipped", fontsize=9)
        ax[0, j].set_xlabel("return period (4 weeks)"); ax[0, j].set_ylabel("production period (4 weeks)")
        ax[0, j].grid(False)
        fig.colorbar(im, ax=ax[0, j], label="returns per 1000 shipped", fraction=0.046)
        O, E0 = pw["_O"], pw["_E0"]
        wk = np.arange(O.size)
        ax[1, j].bar(wk, O, color=COL[name], width=1.0, label="observed")
        ax[1, j].plot(wk, E0, "k-", lw=1, label="expected if all weeks were alike")
        ax[1, j].set_xlabel("production week"); ax[1, j].set_ylabel("welded returns")
        ax[1, j].legend(fontsize=7)
    fig.suptitle("Nevada chart of welded-contact returns at day 910: same return rate, different shape", fontsize=11)
    _save(fig, path)


def fig_weibull(keep, path):
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.9), sharey=True)
    for j, (name, (pop, obs, pw, wv)) in enumerate(keep.items()):
        mle, mrr, t_fail, t_susp, w_susp = wv["_fits"]
        tf, ranks, n_tot = wb.adjusted_ranks(t_fail, t_susp, w_susp)
        y = np.log(-np.log(1 - wb.bernard(ranks, n_tot)))
        ax[j].plot(tf, y, ".", color=COL[name], ms=3, label="welded returns (median ranks)")
        t = np.geomspace(max(tf.min(), 1), 1500, 50)
        for fit, ls in ((mle, "-"), (mrr, "--")):
            ax[j].plot(t, np.log(-np.log(1 - fit.cdf(t))), "k" + ls, lw=1,
                       label=f"{fit.method}: beta {fit.beta:.2f}, eta {fit.eta:.2g} d")
        ax[j].set_xscale("log"); ax[j].set_xlabel("days in service"); ax[j].set_title(LAB[name])
        ax[j].legend(fontsize=7, loc="upper left")
    ticks = np.array([1e-5, 1e-4, 1e-3, 1e-2])
    ax[0].set_yticks(np.log(-np.log(1 - ticks))); ax[0].set_yticklabels([f"{100 * v:g} %" for v in ticks])
    ax[0].set_ylabel("cumulative share returned")
    _save(fig, path)


def fig_returns_needed(out, path):
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for name, d in out["by_truth"].items():
        ax[0].plot(d["mean_weld_returns"], d["p_correct"], "o-", color=COL[name], label=LAB[name])
        ax[1].plot(d["mean_weld_returns"], d["p_correct_no_load_info"], "o-", color=COL[name], label=LAB[name])
    for a, t in zip(ax, ("with load questionnaire on half of the returns", "without any load information")):
        a.axhline(0.9, color="k", ls=":", lw=0.8); a.set_xscale("log"); a.set_xlabel("welded returns in hand (mean)")
        a.set_title(t); a.set_ylim(-0.03, 1.03)
    ax[0].set_ylabel("share of replicates with the correct verdict"); ax[0].legend(fontsize=7)
    _save(fig, path)


def fig_views(metrics, out, path):
    keys = [("rate_pct", "return rate [%]"), ("mle_beta", "Weibull shape (MLE)"), ("scan_lr", "production-week scan LR"),
            ("share_over_rated", "share of welded returns above rated load")]
    fig, ax = plt.subplots(1, 4, figsize=(13, 3.6))
    for a, (k, lab) in zip(ax, keys):
        data = [np.array(metrics[n][k], dtype=float) for n in metrics]
        data = [d[~np.isnan(d)] for d in data]
        bp = a.boxplot(data, patch_artist=True, widths=0.6)
        for patch, n in zip(bp["boxes"], metrics):
            patch.set_facecolor(COL[n]); patch.set_alpha(0.6)
        a.set_xticklabels(["A", "B", "C"])
        a.set_title(f"{lab}\nA vs B separation {out['views'][k]['separation_A_vs_B']:.2f}", fontsize=8)
        if k == "scan_lr":
            a.set_yscale("log")
    fig.suptitle("Which view separates a weak lot (A) from a design limit (B)? 0 = no separation, 1 = complete", fontsize=10)
    _save(fig, path)


def fig_zero_cross(out, path):
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    s = np.array(out["sigma_ms"])
    ax[0].semilogy(s, out["reduction_factor_best_target"], "o-", color="k", label="target angle optimised")
    ax[0].semilogy(s, out["reduction_factor_target_at_zero"], "s--", color="#1f618d", label="target exactly at voltage zero")
    ax[0].axhline(1, color="k", lw=0.6)
    ax[0].set_xlabel("closing-time scatter, sigma [ms]"); ax[0].set_ylabel("10-year weld fraction: reduction factor")
    ax[0].set_title("Zero-cross switching: benefit against relay timing scatter"); ax[0].legend(fontsize=7)
    ax[1].plot(s, out["best_target_deg"], "o-", color="k")
    ax[1].set_xlabel("closing-time scatter, sigma [ms]"); ax[1].set_ylabel("best target [deg after voltage zero]")
    ax[1].set_title("Best aiming point (negative = before the zero)")
    _save(fig, path)


def fig_trade(trade, path):
    fig, ax = plt.subplots(1, 2, figsize=(12, 4))
    keys = list(trade["options"])
    v = [max(trade["options"][k]["weld_pct_10y"], 1e-4) for k in keys]
    col = ["#1e8449" if trade["options"][k]["feasible"] else "#909497" for k in keys]
    ax[0].barh(keys[::-1], v[::-1], color=col[::-1])
    ax[0].set_xscale("log"); ax[0].axvline(trade["requirement_weld_10y_pct"], color="k", ls="--", lw=0.8)
    ax[0].set_xlabel("units welded within 10 years on the LED-heavy mix [%]")
    ax[0].set_title("Green = meets all requirements; dashed = 0.5 % limit")
    c = [trade["options"][k]["expected_cost_eur"] for k in keys]
    b = [trade["options"][k]["bom_delta_eur"] for k in keys]
    ax[1].barh(keys[::-1], c[::-1], color="#d5d8dc", label="BOM + expected weld cost")
    ax[1].barh(keys[::-1], b[::-1], color="#566573", label="BOM delta")
    ax[1].set_xlabel("EUR per channel over 10 years (cost figures are assumptions)"); ax[1].legend(fontsize=7)
    ax[1].set_title(f"Decision: {trade['decision']}")
    _save(fig, path)


def fig_forecast(hist, f_no, f_ca, a_no, a_ca, t_obs, path):
    fig, ax = plt.subplots(figsize=(8.5, 3.9))
    kh = np.arange(hist.size - 1)
    ax.bar(kh * 28 / 7, hist[:-1], width=3.6, color="#aab7b8", label="welded returns received (history)")
    kf = (int(t_obs // 28) + np.arange(f_no.size) + 0.5) * 28 / 7
    ax.plot(kf, f_no, "k-", label="blind forecast, no corrective action")
    ax.plot(kf, f_ca, "-", color="#1e8449", label="blind forecast, with corrective action")
    ax.plot(kf, a_no, "ko", ms=4, label="hidden truth, no corrective action")
    ax.plot(kf, a_ca, "o", color="#1e8449", ms=4, label="hidden truth, with corrective action")
    ax.axvline(t_obs / 7, color="k", ls=":", lw=0.8); ax.axvline(140, color="#1e8449", ls=":", lw=0.8)
    ax.text(140.5, ax.get_ylim()[1] * 0.93, "cut-in, week 140", fontsize=7, color="#1e8449")
    ax.set_xlabel("week"); ax.set_ylabel("welded returns per 4 weeks")
    ax.set_title("Warranty-return forecast, truth B (design limit)"); ax.legend(fontsize=7, loc="upper left")
    _save(fig, path)


def fig_ishikawa(path):
    """Cause-and-effect diagram for the 8D report. Status marks follow docs/8D_REPORT.md."""
    cats = {
        "Material": ["contact alloy lot (AgSnO2 share) [A: cause]", "contact rivet hardness", "spring material"],
        "Machine / process": ["contact force and over-travel setting [A: cause]", "relay adjustment drift",
                              "solder flux on contacts [excluded]"],
        "Design": ["relay inrush rating vs LED load [B: cause]", "random closing angle [B: contributes]",
                   "no inrush limiting in the channel", "bounce time of the relay type"],
        "Load / environment": ["LED watts per channel [B: cause]", "lamp driver bulk capacitance",
                               "low line impedance", "switching frequency (presence detectors)"],
        "Method / information": ["16 A rating read as LED rating [B: cause]", "no LED limit in the manual",
                                 "load not recorded at commissioning"],
        "Measurement": ["type test at rated load only", "no load questionnaire with returns",
                        "returns lag failures by weeks"],
    }
    fig, ax = plt.subplots(figsize=(13, 6.2))
    ax.axis("off"); ax.set_xlim(0, 13); ax.set_ylim(0, 8)
    ax.annotate("", xy=(11.2, 4), xytext=(0.3, 4), arrowprops=dict(arrowstyle="-|>", lw=2, color="k"))
    ax.text(11.3, 4, "Relay contact\nwelded:\nload stays on", fontsize=11, va="center", weight="bold")
    xs = [1.6, 5.0, 8.4]
    for i, (cat, items) in enumerate(cats.items()):
        top = i % 2 == 0
        x0 = xs[i // 2]
        y_end = 7.3 if top else 0.7
        ax.plot([x0, x0 + 1.6], [y_end, 4], color="k", lw=1.2)
        ax.text(x0, y_end + (0.25 if top else -0.25), cat, fontsize=10, weight="bold", ha="center",
                va="bottom" if top else "top")
        for k, it in enumerate(items):
            f = (k + 1) / (len(items) + 1)
            xa, ya = x0 + 1.6 * f, y_end + (4 - y_end) * f
            colr = "#b03a2e" if "cause]" in it else ("#7b7d7d" if "excluded" in it else "k")
            ax.plot([xa - 0.25, xa], [ya, ya], color=colr, lw=0.8)
            ax.text(xa - 0.3, ya, it, fontsize=7.5, ha="right", va="center", color=colr)
    ax.text(0.3, 0.05, "Red: confirmed as cause in truth A (weak lot) or truth B (design limit) of this simulated study. "
            "Grey: excluded. Black: possible contributor, not separated.", fontsize=7.5)
    _save(fig, path)
