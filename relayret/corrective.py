"""Corrective-action options, all evaluated with the same inrush and weld physics.

Options:
  relay      relay with a tungsten pre-make contact (higher weld threshold)
  zc_*       closing synchronised to the voltage zero, with realistic timing scatter
  ntc        series NTC inrush limiter (cold and hot-restart resistance)
  derating   published limit of LED watts per channel, with partial compliance
  hybrid     semiconductor in parallel that makes the circuit; the relay closes on ~1.5 V
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

from . import inrush as ir
from . import weld as wd

# ---------------------------------------------------------------- NTC inrush limiter
# TDK/EPCOS S364 1 ohm type (B57364S0109M000): R25 = 1 ohm, Imax = 16 A (maker's product page);
# B = 2800 K, dissipation factor 24 mW/K, thermal time constant 100 s, Pmax 5.1 W
# (distributor listing, not re-checked against the maker's PDF).
NTC_R25 = 1.0
NTC_B = 2800.0
NTC_DELTA = 0.024      # W/K
NTC_TAU = 100.0        # s
NTC_PMAX = 5.1         # W
T_AMB_DEVICE = 40.0    # deg C inside the actuator (assumption)
LED_PF = 0.9           # power factor of the LED load for the steady current (assumption)


def ntc_resistance(temp_c):
    t = np.asarray(temp_c, dtype=float) + 273.15
    return NTC_R25 * np.exp(NTC_B * (1.0 / t - 1.0 / 298.15))


def ntc_steady_temp(i_rms: float, t_amb: float = T_AMB_DEVICE) -> float:
    """Self-heated steady temperature of the NTC carrying i_rms."""
    f = lambda t: i_rms ** 2 * ntc_resistance(t) - NTC_DELTA * (t - t_amb)
    if f(t_amb + 1e-6) <= 0:
        return t_amb
    return float(brentq(f, t_amb + 1e-6, 400.0))


def ntc_restart_resistance(p_led: float, t_off_s: float, t_amb: float = T_AMB_DEVICE) -> float:
    """NTC resistance when the load is switched on again t_off_s after switch-off."""
    t_ss = ntc_steady_temp(p_led / (ir.V_RMS * LED_PF), t_amb)
    return float(ntc_resistance(t_amb + (t_ss - t_amb) * np.exp(-t_off_s / NTC_TAU)))


class NtcGrid(wd.StressGrid):
    """Stress grid with a load-dependent extra series resistance (the NTC)."""

    def __init__(self, t_off_s: float | None, bounce=ir.Bounce(), n_b: int = 40, seed: int = 7,
                 cache_dir: str | None = None):
        import os
        self.bounce, self.n_b, self.seed = bounce, n_b, seed
        tag = "ntc_cold" if t_off_s is None else f"ntc_hot{t_off_s:.0f}"
        path = os.path.join(cache_dir, f"stress_{tag}_{n_b}_{seed}.npz") if cache_dir else None
        if path and os.path.exists(path):
            d = np.load(path)
            self.W, self.ipk = d["W"], d["ipk"]
            return
        shape = (wd.P_GRID.size, 3, 3, wd.N_THETA, n_b)
        self.W, self.ipk = np.zeros(shape), np.zeros(shape[:4])
        for a, p in enumerate(wd.P_GRID):
            r_ntc = float(ntc_resistance(T_AMB_DEVICE)) if t_off_s is None else ntc_restart_resistance(p, t_off_s)
            for b, lk in enumerate(wd.LAMP_KEYS):
                for c, nk in enumerate(wd.LINE_KEYS):
                    R, L, C = ir.load_circuit(p, lk, nk, r_ntc)
                    w, ipk = wd.arc_energy_samples(R, L, C, bounce, n_b, seed)
                    self.W[a, b, c], self.ipk[a, b, c] = w, ipk.mean(axis=1)
        if path:
            os.makedirs(cache_dir, exist_ok=True)
            np.savez_compressed(path, W=self.W, ipk=self.ipk)


# ---------------------------------------------------------------- option definitions
@dataclass(frozen=True)
class Option:
    key: str
    label: str
    bom_delta_eur: float          # per channel, assumption
    loss_w_at_16a: float          # extra dissipation per channel at rated current
    installer_dependent: bool
    new_failure_mode: str
    verification: str


OPTIONS = [
    Option("baseline", "Baseline: 16 A AgSnO2 relay, random closing", 0.0, 0.0, False, "-",
           "IEC 60669-2-1 19.109, 40 000 operations at the rated lamp load"),
    Option("relay", "Relay with tungsten pre-make contact", 0.80, 0.0, False,
           "pre-make contact wear (maker rates 25k-30k cycles on some loads)",
           "19.109 at the new declared lamp load, plus relay maker's inrush rating check"),
    Option("zc_open", "Zero-cross firmware, fixed delay (sigma 1.5 ms)", 0.30, 0.0, False,
           "wrong timing after relay ageing goes unnoticed",
           "closing-angle histogram over temperature and coil voltage; 19.109 with product's own timing"),
    Option("zc_cal", "Zero-cross firmware, end-of-line calibrated (sigma 0.7 ms)", 0.35, 0.0, False,
           "calibration lost or relay drift over life",
           "as above, plus calibration check on 100 % of production"),
    Option("zc_adapt", "Zero-cross firmware, closing time measured each operation (sigma 0.25 ms)", 0.55, 0.0, False,
           "sense circuit failure falls back to random closing",
           "closing-angle histogram over life test; 19.109 with product's own timing"),
    Option("ntc", "Series NTC 1 ohm inrush limiter", 0.45, NTC_PMAX, False,
           "hot restart, NTC crack on overload", "19.109 cold and with 30 s off-time; temperature rise test at 16 A"),
    Option("derating", "Publish 200 W LED limit per channel (70 % compliance)", 0.0, 0.0, True,
           "none in the product; relies on the installer", "none in the lab; field audit of installed loads"),
    Option("hybrid", "Hybrid: semiconductor makes, relay carries", 1.60, 0.0, False,
           "semiconductor short circuit = load cannot be switched off; surge stress on the open switch",
           "19.109 plus surge (EN 61000-4-5) across the open channel and semiconductor I2t check"),
]

ZC_SIGMA_MS = {"zc_open": 1.5, "zc_cal": 0.7, "zc_adapt": 0.25}   # assumptions, see DOSSIER 6
RELAY_FACTOR = "W_premake"
DERATING_LIMIT_W = 200.0
DERATING_COMPLIANCE = 0.70      # assumption
NTC_HOT_SHARE = 0.10            # share of operations within about 30 s of a switch-off (assumption)
HYBRID_FIT = 10.0               # failures per 1e9 h of the semiconductor ending in a short (assumption)


def best_zc_target(grid: wd.StressGrid, params: wd.WeldParams, x_nom: float, e_ref: float, sigma_ms: float,
                   inst: dict, targets=np.arange(-40.0, 11.0, 2.0)):
    """Closing-angle target (degrees after the voltage zero, negative = before) that gives the
    lowest 10-year weld fraction on the installed-base sample, for a given timing scatter."""
    sub = {k: (v[:4000] if isinstance(v, np.ndarray) else v) for k, v in inst.items()}
    ptab, wm = grid.p_table(params.sigma_w), grid.w_mean()
    m = wd.WeldModel.__new__(wd.WeldModel)
    m.grid, m.params, m.x_nominal, m.e_ref = grid, params, x_nom, e_ref
    best = (None, np.inf)
    for t in targets:
        w = wd.theta_weights("zero_cross", float(t), sigma_ms)
        m.ptab = np.tensordot(ptab, w, axes=([3], [0]))
        m.wbar = np.tensordot(wm, w, axes=([3], [0]))
        v = weld_fraction(m, sub, 10.0)
        if v < best[1]:
            best = (float(t), v)
    return best[0]


def reference_installs(n: int = 30000, seed: int = 99, com_share: float = 0.50, com_median_w: float = 290.0,
                       sigma_unit: float = 0.20):
    """Installed-base sample for the trade study: the late (LED-heavy) mix of truth B."""
    from .field import FieldParams
    fp = FieldParams()
    rng = np.random.default_rng(seed)
    has_led = rng.random(n) < fp.led_share
    is_com = has_led & (rng.random(n) < com_share)
    z = rng.standard_normal(n)
    p = np.clip(np.where(is_com, com_median_w * np.exp(fp.com_sig * z), fp.res_median_w * np.exp(fp.res_sig * z)),
                5.0, fp.p_max)
    u = rng.random(n)
    ic = np.where(is_com, np.searchsorted(np.cumsum(fp.lamp_mix_com), u),
                  np.searchsorted(np.cumsum(fp.lamp_mix_res), u)).clip(0, 2)
    u = rng.random(n)
    il = np.where(is_com, np.searchsorted(np.cumsum(fp.line_mix_com), u),
                  np.searchsorted(np.cumsum(fp.line_mix_res), u)).clip(0, 2)
    z = rng.standard_normal(n)
    ops = np.where(is_com, fp.ops_com_med * np.exp(fp.ops_com_sig * z), fp.ops_res_med * np.exp(fp.ops_res_sig * z))
    dx = sigma_unit * rng.standard_normal(n)
    k = has_led
    return {"n_all": n, "p_led": p[k], "ic": ic[k], "il": il[k], "ops": ops[k], "dx": dx[k]}


def weld_fraction(model: wd.WeldModel, inst: dict, years: float, x_shift: float = 0.0,
                  p_led=None, channels=None) -> float:
    """Expected share of ALL units (LED or not) with a welded contact within `years`."""
    p = inst["p_led"] if p_led is None else p_led
    grid = np.linspace(0.0, 1.0, 25) ** 1.5
    n_ops = (inst["ops"] * 365.0 * years)[:, None] * grid[None, :]
    H = model.cum_hazard(p, inst["ic"], inst["il"], model.x_nominal + x_shift + inst["dx"], n_ops)[:, -1]
    if channels is not None:
        H = H * channels
    return float(np.sum(1.0 - np.exp(-H)) / inst["n_all"])


def endurance_pass(bounce: ir.Bounce, params: wd.WeldParams, x: float, e_ref: float, p_rated: float,
                   w_theta: np.ndarray, r_extra: float = 0.0) -> float:
    """Probability that one specimen passes the 40 000-operation lamp test at p_rated,
    with the product's own distribution of closing angles (w_theta)."""
    W = wd.endurance_energy(p_rated, bounce, r_extra=r_extra)
    return wd.endurance_survival(W, w_theta, x, params, e_ref)
