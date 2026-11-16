"""Inrush current of a capacitor-input lamp load closed by a bouncing relay contact.

Circuit (the load B of IEC 60669-2-1, 19.109): mains source with series R and L,
the switching contact, and the lamp as a series resistance R1 feeding a bulk
capacitor C behind a bridge rectifier. The lamp's steady load resistor is left
out: it draws well under 1 % of the inrush current during the first milliseconds.

The contact closes at phase angle theta, then bounces open once or twice. While
it is open and current is flowing, the current continues through a short arc
with a constant arc voltage. The energy put into that arc is the weld stress
used by ``relayret.weld``.

All numbers taken from standards and datasheets are listed in docs/SOURCES.md.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

V_RMS = 230.0
F_MAINS = 50.0
V_PK = V_RMS * np.sqrt(2.0)
OMEGA = 2.0 * np.pi * F_MAINS

# IEC 60669-2-1, Table 108 (230 V systems): rated SBL power [W] -> (Ipeak [A], I2t [A2s])
IEC_TABLE_108 = {
    15: (22.0, 0.08), 30: (41.0, 0.3), 60: (73.0, 1.2), 100: (108.0, 2.8),
    150: (142.0, 5.5), 200: (170.0, 9.0), 250: (192.0, 13.0), 300: (209.0, 16.5),
    350: (223.0, 20.5), 400: (235.0, 24.5),
}
# IEC 60669-2-1, Table 109 (informative, 230 V): rated power [W] -> (R1 [ohm], C [uF])
IEC_TABLE_109 = {
    15: (13.0, 20.0), 30: (6.5, 40.0), 60: (3.25, 80.0), 100: (1.9, 125.0),
    150: (1.25, 180.0), 200: (0.95, 240.0), 250: (0.8, 310.0), 300: (0.7, 355.0),
    350: (0.64, 420.0), 400: (0.59, 480.0),
}
# IEC 60669-2-1, Annex BB.3: 3 kA prospective, cos phi 0.9 (0.069 ohm + 106 uH) plus
# test cable (0.25 ohm + 20 uH)
IEC_SOURCE_R = 0.319
IEC_SOURCE_L = 126e-6


@dataclass(frozen=True)
class Bounce:
    """Contact bounce after first touch. All values are assumptions (see DOSSIER 7.2).

    t1: delay from first touch to the first opening; d1: duration of the first
    opening; gap: closed time before the second opening; d2 = ratio2 * d1.
    Each is lognormal with the given median [s] and log-sigma.
    """
    t1_med: float = 100e-6
    t1_sig: float = 0.5
    d1_med: float = 600e-6   # Doublet et al. 2004 simulate a 600 us relay bounce
    d1_sig: float = 0.4
    gap_med: float = 200e-6
    gap_sig: float = 0.5
    ratio2: float = 0.4

    def draw(self, n: int, rng: np.random.Generator):
        t1 = self.t1_med * np.exp(self.t1_sig * rng.standard_normal(n))
        d1 = self.d1_med * np.exp(self.d1_sig * rng.standard_normal(n))
        gap = self.gap_med * np.exp(self.gap_sig * rng.standard_normal(n))
        o1, c1 = t1, t1 + d1
        o2, c2 = c1 + gap, c1 + gap + self.ratio2 * d1
        return np.stack([o1, o2], axis=1), np.stack([c1, c2], axis=1)


U_ARC = 13.0      # V, short silver arc (assumption, textbook order: 12-15 V)
I_ARC_MIN = 0.4   # A, minimum arc current (assumption, textbook order)


def _discretise(R: float, L: float, C: float, dt: float):
    """Exact zero-order-hold discretisation of the series R-L-C loop."""
    from scipy.linalg import expm
    A = np.array([[-R / L, -1.0 / L], [1.0 / C, 0.0]])
    B = np.array([1.0 / L, 0.0])
    Ad = expm(A * dt)
    Bd = np.linalg.solve(A, (Ad - np.eye(2)) @ B)
    return Ad, Bd


def simulate_make(R: float, L: float, C: float, theta, t_open=None, t_close=None,
                  u_arc: float = U_ARC, i_arc_min: float = I_ARC_MIN,
                  dt: float = 2e-6, t_end: float = 3e-3, v_pk: float = V_PK,
                  return_trace: bool = False):
    """Simulate contact closure at phase angle theta [rad] (0 = voltage zero).

    R, L: total series resistance and inductance (source + wiring + lamp R1).
    C: total bulk capacitance, initially discharged.
    t_open, t_close: arrays (n, nb) of bounce opening / re-closing times after
    first touch [s]; None means a bounce-free contact.

    Returns dict of arrays (n,): i_peak [A], i2t [A2s], w_arc [J], q_arc [C].
    """
    theta = np.atleast_1d(np.asarray(theta, dtype=float))
    n = theta.size
    if t_open is None:
        t_open = np.full((n, 1), np.inf)
        t_close = np.full((n, 1), np.inf)
    Ad, Bd = _discretise(R, L, C, dt)
    i = np.zeros(n)
    vc = np.zeros(n)
    arc_out = np.zeros(n, dtype=bool)     # arc extinguished during the present opening
    i_peak = np.zeros(n)
    i2t = np.zeros(n)
    w_arc = np.zeros(n)
    q_arc = np.zeros(n)
    steps = int(round(t_end / dt))
    trace = np.zeros((steps, n)) if return_trace else None
    for k in range(steps):
        t = k * dt
        vs = v_pk * np.abs(np.sin(theta + OMEGA * (t + 0.5 * dt)))
        is_open = ((t >= t_open) & (t < t_close)).any(axis=1)
        arc_out &= is_open                       # reset when the contact is closed again
        arc_on = is_open & (i > i_arc_min) & ~arc_out
        u = vs - u_arc * arc_on
        path = ~is_open | arc_on                 # a current path exists
        conduct = path & ((i > 0.0) | (u > vc))  # rectifier conducts
        i_n = np.where(conduct, Ad[0, 0] * i + Ad[0, 1] * vc + Bd[0] * u, 0.0)
        vc_n = np.where(conduct, Ad[1, 0] * i + Ad[1, 1] * vc + Bd[1] * u, vc)
        i_n = np.maximum(i_n, 0.0)
        dies = arc_on & (i_n <= i_arc_min)       # arc starves and goes out
        i_n = np.where(dies, 0.0, i_n)
        arc_out |= dies | (is_open & ~arc_on)
        i_mid = 0.5 * (i + i_n)
        i2t += 0.5 * (i * i + i_n * i_n) * dt
        w_arc += np.where(arc_on, u_arc * i_mid * dt, 0.0)
        q_arc += np.where(arc_on, i_mid * dt, 0.0)
        i_peak = np.maximum(i_peak, i_n)
        i, vc = i_n, vc_n
        if return_trace:
            trace[k] = i
    out = {"i_peak": i_peak, "i2t": i2t, "w_arc": w_arc, "q_arc": q_arc}
    if return_trace:
        out["t"] = (np.arange(steps) + 1) * dt
        out["i"] = trace
    return out


def rlc_step_peak(V0: float, R: float, L: float, C: float) -> float:
    """Analytic peak current of a series R-L-C loop for a voltage step V0 (C empty)."""
    alpha = R / (2.0 * L)
    w0sq = 1.0 / (L * C)
    if alpha * alpha < w0sq:                       # under-damped
        wd = np.sqrt(w0sq - alpha * alpha)
        tp = np.arctan2(wd, alpha) / wd
        return V0 / (wd * L) * np.exp(-alpha * tp) * np.sin(wd * tp)
    if np.isclose(alpha * alpha, w0sq):
        return V0 / L * (1.0 / alpha) * np.exp(-1.0)
    b = np.sqrt(alpha * alpha - w0sq)
    s1, s2 = -alpha + b, -alpha - b
    tp = np.log(s2 / s1) / (s1 - s2)
    return V0 / (L * (s1 - s2)) * (np.exp(s1 * tp) - np.exp(s2 * tp))


# ---------------------------------------------------------------- lamp population
# Lamp "inrush classes". The reference is the standard's worst-case lamp model:
# Table 109 gives about 1.2 uF per watt behind about 190 ohm*W of series resistance.
# The other classes are assumptions (see DOSSIER 7.1): c_per_w in uF/W, r_times_w in ohm*W.
LAMP_CLASSES = {
    "high": {"c_per_w": 1.20, "r_times_w": 190.0},     # cap-input, as the IEC model
    "medium": {"c_per_w": 0.50, "r_times_w": 400.0},   # smaller bulk cap, fusible resistor
    "low": {"c_per_w": 0.12, "r_times_w": 1500.0},     # valley-fill / active limiting
}
# Supply as seen by the contact. "stiff" is the IEC 60669-2-1 test network; "soft" is
# the 0.2 ohm + 400 uH lamp-test impedance of Table BB.1 with 0.5 ohm of extra wiring.
LINE_CLASSES = {
    "stiff": {"R": 0.319, "L": 126e-6},
    "medium": {"R": 0.50, "L": 250e-6},
    "soft": {"R": 0.70, "L": 400e-6},
}


def load_circuit(p_led: float, lamp_class: str, line_class: str, r_extra: float = 0.0):
    """Total R, L, C for p_led watts of lamps of one class on one line class."""
    lc, ln = LAMP_CLASSES[lamp_class], LINE_CLASSES[line_class]
    C = lc["c_per_w"] * p_led * 1e-6
    R = ln["R"] + lc["r_times_w"] / p_led + r_extra
    return R, ln["L"], C
