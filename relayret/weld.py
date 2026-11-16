"""Probability of a contact weld per switching operation.

Structure (from the literature, see docs/SOURCES.md):
  * the weld forms from the bounce arc at make; weld force rises with the arc energy
    put into the contact surface (Hotta et al. 2015/2017, Zhang et al. 2020);
  * weld force at a given energy scatters widely from operation to operation;
  * a weld is a failure when it is stronger than the opening force of the relay;
  * contacts that have already absorbed a lot of arc energy weld more easily
    (Zhang et al. 2019, Guo et al. 2019).

Model: weld force F = k * W_arc * exp(sigma_w * z), failure if F > F_open, so
    p_weld = Phi((ln W_arc - ln W50) / sigma_w),   W50 = F_open / k.
W50 is not measured anywhere in the open literature for a given relay. It is
calibrated so that a nominal unit just passes the 40 000-operation lamp test of
IEC 60669-2-1 at its rated lamp load. sigma_w, the wear factor kappa and the unit
spread are assumptions with sensitivity runs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
from scipy.special import ndtr

from . import inrush as ir

P_GRID = np.array([15.0, 23.0, 35.0, 54.0, 82.0, 125.0, 190.0, 290.0, 440.0, 680.0, 1040.0, 1600.0])
LAMP_KEYS = ("high", "medium", "low")
LINE_KEYS = ("stiff", "medium", "soft")
N_THETA = 90                     # 2 degree steps over the rectified half cycle
THETA = np.arange(N_THETA) * np.pi / N_THETA
X_GRID = np.linspace(np.log(1e-3), np.log(3e3), 121)   # ln W50 [J]


@dataclass(frozen=True)
class WeldParams:
    sigma_w: float = 0.8          # log-scatter of weld force at fixed arc energy (assumption)
    kappa: float = 0.7            # ln W50 falls by kappa per "rated test" of absorbed arc energy
    sigma_unit: float = 0.20      # unit-to-unit log spread of W50 (contact force spread)
    rated_p: float = 200.0        # W, rated SBL load of a 16 A switch (IEC 60669-1 Table 2)
    n_test: int = 40000           # operations, IEC 60669-2-1 19.109
    pass_prob: float = 0.95       # calibration: nominal unit passes the rated test with this probability
    # weld-resistance factors relative to the baseline AgSnO2 contact
    material: dict = field(default_factory=lambda: {
        "AgSnO2": 1.0,
        "AgNi": 0.4,              # assumption: "medium" vs "excellent" weld resistance
        "W_premake": 3.4,         # 800 A / 200 us rating vs 235 A test peak of the 400 W LED rating
    })


def arc_energy_samples(R, L, C, bounce: ir.Bounce, n_b: int, seed: int, theta=THETA, **kw):
    """Bounce-arc energy W[theta, b] for one circuit, common random bounce draws."""
    rng = np.random.default_rng(seed)
    t_open, t_close = bounce.draw(n_b, rng)
    th = np.repeat(theta, n_b)
    o = ir.simulate_make(R, L, C, th, np.tile(t_open, (theta.size, 1)),
                         np.tile(t_close, (theta.size, 1)), **kw)
    return o["w_arc"].reshape(theta.size, n_b), o["i_peak"].reshape(theta.size, n_b)


class StressGrid:
    """Arc-energy samples on the grid of field circuits: W[ip, ic, il, theta, b]."""

    def __init__(self, bounce: ir.Bounce = ir.Bounce(), n_b: int = 40, seed: int = 7,
                 r_extra: float = 0.0, cache_dir: str | None = None, tag: str = "base"):
        self.bounce, self.n_b, self.seed, self.r_extra = bounce, n_b, seed, r_extra
        key = f"{tag}_{n_b}_{seed}_{r_extra:.4f}_{bounce.t1_med:.2e}_{bounce.d1_med:.2e}"
        path = os.path.join(cache_dir, f"stress_{key}.npz") if cache_dir else None
        if path and os.path.exists(path):
            d = np.load(path)
            self.W, self.ipk = d["W"], d["ipk"]
            return
        shape = (P_GRID.size, len(LAMP_KEYS), len(LINE_KEYS), N_THETA, n_b)
        self.W = np.zeros(shape)
        self.ipk = np.zeros(shape[:4])
        for a, p in enumerate(P_GRID):
            for b, lk in enumerate(LAMP_KEYS):
                for c, nk in enumerate(LINE_KEYS):
                    R, L, C = ir.load_circuit(p, lk, nk, r_extra)
                    w, ipk = arc_energy_samples(R, L, C, bounce, n_b, seed)
                    self.W[a, b, c] = w
                    self.ipk[a, b, c] = ipk.mean(axis=1)
        if path:
            os.makedirs(cache_dir, exist_ok=True)
            np.savez_compressed(path, W=self.W, ipk=self.ipk)

    def p_table(self, sigma_w: float) -> np.ndarray:
        """P[ip, ic, il, theta, x]: weld probability per operation, averaged over bounce."""
        lw = np.log(np.maximum(self.W, 1e-12))
        out = np.empty(self.W.shape[:4] + (X_GRID.size,))
        for j, x in enumerate(X_GRID):
            out[..., j] = ndtr((lw - x) / sigma_w).mean(axis=-1)
        return out

    def w_mean(self) -> np.ndarray:
        """Mean arc energy per operation, W[ip, ic, il, theta]."""
        return self.W.mean(axis=-1)


def theta_weights(mode: str = "random", target_deg: float = 0.0, sigma_ms: float = 0.0) -> np.ndarray:
    """Distribution of the closing angle over the THETA grid.

    random: uniform. zero_cross: normal timing error with sigma_ms around target_deg
    (degrees after a voltage zero; negative = before), wrapped onto the half cycle.
    """
    if mode == "random":
        return np.full(N_THETA, 1.0 / N_THETA)
    half = 1e3 / (2.0 * ir.F_MAINS)                 # 10 ms
    t_grid = np.degrees(THETA) / 180.0 * half       # ms after the zero
    t0 = target_deg / 180.0 * half
    if sigma_ms <= 1e-9:
        w = np.zeros(N_THETA)
        w[int(round((t0 % half) / half * N_THETA)) % N_THETA] = 1.0
        return w
    k = np.arange(-6, 7)[:, None]
    d = t_grid[None, :] - t0 + k * half
    w = np.exp(-0.5 * (d / sigma_ms) ** 2).sum(axis=0)
    return w / w.sum()


def _interp_x(tab: np.ndarray, j, ic, il, x: np.ndarray) -> np.ndarray:
    """tab[j, ic, il, :] linearly interpolated along the x axis at positions x (per unit)."""
    f = (np.clip(x, X_GRID[0], X_GRID[-1]) - X_GRID[0]) / (X_GRID[1] - X_GRID[0])
    k = np.minimum(f.astype(int), X_GRID.size - 2)
    r = f - k
    return tab[j, ic, il, k] * (1.0 - r) + tab[j, ic, il, k + 1] * r


class WeldModel:
    """Weld probability per operation for field units, for one hardware/firmware design."""

    def __init__(self, grid: StressGrid, params: WeldParams = WeldParams(),
                 w_theta: np.ndarray | None = None, x_nominal: float | None = None,
                 e_ref: float | None = None, p_table: np.ndarray | None = None):
        self.grid, self.params = grid, params
        self.w_theta = theta_weights() if w_theta is None else w_theta
        ptab = grid.p_table(params.sigma_w) if p_table is None else p_table
        self.ptab = np.tensordot(ptab, self.w_theta, axes=([3], [0]))           # [ip, ic, il, x]
        self.wbar = np.tensordot(grid.w_mean(), self.w_theta, axes=([3], [0]))  # [ip, ic, il]
        self.x_nominal = x_nominal
        self.e_ref = e_ref

    # -- per-unit quantities, interpolated in log(P_led)
    def _pidx(self, p_led):
        lp = np.log(np.clip(p_led, P_GRID[0], P_GRID[-1]))
        f = np.interp(lp, np.log(P_GRID), np.arange(P_GRID.size))
        j = np.minimum(f.astype(int), P_GRID.size - 2)
        return j, f - j

    def w_per_op(self, p_led, ic, il):
        j, r = self._pidx(p_led)
        lo, hi = np.maximum(self.wbar[j, ic, il], 1e-12), np.maximum(self.wbar[j + 1, ic, il], 1e-12)
        return np.exp(np.log(lo) * (1 - r) + np.log(hi) * r)

    def p_op(self, p_led, ic, il, x):
        """Weld probability per operation at threshold x = ln W50 (arrays broadcast on units)."""
        j, r = self._pidx(p_led)
        lo = _interp_x(self.ptab, j, ic, il, x)
        hi = _interp_x(self.ptab, j + 1, ic, il, x)
        return np.exp(np.log(np.maximum(lo, 1e-300)) * (1 - r) + np.log(np.maximum(hi, 1e-300)) * r)

    def cum_hazard(self, p_led, ic, il, x0, n_ops):
        """Cumulative weld hazard after n_ops operations; n_ops has shape (units, m)."""
        dmg = n_ops * (self.w_per_op(p_led, ic, il) / self.e_ref)[:, None]
        m = n_ops.shape[1]
        h = np.empty_like(n_ops, dtype=float)
        for k in range(m):
            h[:, k] = self.p_op(p_led, ic, il, x0 - self.params.kappa * dmg[:, k])
        dn = np.diff(n_ops, axis=1)
        H = np.concatenate([np.zeros((n_ops.shape[0], 1)),
                            np.cumsum(0.5 * (h[:, 1:] + h[:, :-1]) * dn, axis=1)], axis=1)
        return H


def endurance_energy(p_rated: float, bounce: ir.Bounce, n_b: int = 60, seed: int = 11,
                     r_extra: float = 0.0) -> np.ndarray:
    """Arc-energy samples W[theta, b] of the IEC 60669-2-1 load B at the rated lamp power.

    R1 and C come from Table 109 (interpolated); the source is the 3 kA network plus cable."""
    ps = np.array(sorted(ir.IEC_TABLE_109))
    r1 = np.interp(p_rated, ps, [ir.IEC_TABLE_109[p][0] for p in ps])
    c = np.interp(p_rated, ps, [ir.IEC_TABLE_109[p][1] for p in ps]) * 1e-6
    w, _ = arc_energy_samples(r1 + ir.IEC_SOURCE_R + r_extra, ir.IEC_SOURCE_L, c, bounce, n_b, seed)
    return w


def endurance_survival(W: np.ndarray, w_theta: np.ndarray, x0: float, params: WeldParams, e_ref: float,
                       n_ops: int | None = None) -> float:
    """Probability that one unit with threshold x0 = ln W50 gets through the endurance test
    without a weld. W[theta, b] from ``endurance_energy``; w_theta is the product's own
    distribution of closing angles (the standard fixes the circuit, not the closing angle)."""
    n_ops = params.n_test if n_ops is None else n_ops
    n = np.linspace(0.0, n_ops, 41)
    wbar = float(W.mean(axis=1) @ w_theta)
    lw = np.log(np.maximum(W, 1e-12))
    h = np.array([ndtr((lw - (x0 - params.kappa * k * wbar / e_ref)) / params.sigma_w).mean(axis=1) @ w_theta
                  for k in n])
    return float(np.exp(-np.trapezoid(h, n)))


def calibrate(params: WeldParams, bounce: ir.Bounce):
    """Nominal ln W50 and reference arc energy from the rated lamp test with random closing.

    Returns (x_nominal, e_ref, mean arc energy per test operation)."""
    from scipy.optimize import brentq
    W = endurance_energy(params.rated_p, bounce)
    wt = theta_weights()
    wbar = float(W.mean(axis=1) @ wt)
    e_ref = params.n_test * wbar
    f = lambda x: endurance_survival(W, wt, x, params, e_ref) - params.pass_prob
    x_nom = brentq(f, np.log(wbar) - 1.0, np.log(wbar) + 12.0)
    return x_nom, e_ref, wbar
