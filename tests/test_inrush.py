"""Inrush model checked against the standard's test table, an analytic solution and scaling laws."""
import numpy as np
import pytest

from relayret import inrush as ir


def _make(p, theta_deg=90.0, **kw):
    r1, c = ir.IEC_TABLE_109[p]
    return ir.simulate_make(r1 + ir.IEC_SOURCE_R, ir.IEC_SOURCE_L, c * 1e-6,
                            np.array([np.radians(theta_deg)]), t_end=5e-3, **kw)


@pytest.mark.parametrize("p", sorted(ir.IEC_TABLE_108))
def test_reproduces_iec_60669_2_1_table_108(p):
    """Table 109 circuit values + the Annex BB source give Table 108's Ipeak and I2t.
    The standard itself asks for the circuit to be trimmed to +/-5 %, so 8 % / 12 % untrimmed is the bar."""
    o = _make(p)
    ipk, i2t = ir.IEC_TABLE_108[p]
    assert o["i_peak"][0] == pytest.approx(ipk, rel=0.08)
    assert o["i2t"][0] == pytest.approx(i2t, rel=0.12)


def test_small_loads_match_within_standard_tolerance():
    for p in (15, 30, 60, 100):
        assert _make(p)["i_peak"][0] == pytest.approx(ir.IEC_TABLE_108[p][0], rel=0.035)


def test_single_lamp_values_of_annex_bb():
    # Table BB.1: lamp <= 15 W at 230 V: 20 A, 0.08 A2s behind 0.2 ohm + 400 uH.
    # Same lamp (13 ohm, 20 uF) on that impedance:
    o = ir.simulate_make(13.0 + 0.2, 400e-6, 20e-6, np.array([np.pi / 2]), t_end=5e-3)
    assert o["i_peak"][0] == pytest.approx(20.0, rel=0.10)
    assert o["i2t"][0] == pytest.approx(0.08, rel=0.10)


def test_matches_analytic_rlc_step():
    for p in (15, 100, 400):
        r1, c = ir.IEC_TABLE_109[p]
        ana = ir.rlc_step_peak(ir.V_PK, r1 + ir.IEC_SOURCE_R, ir.IEC_SOURCE_L, c * 1e-6)
        assert _make(p)["i_peak"][0] == pytest.approx(ana, rel=0.01)


def test_rlc_step_peak_limits():
    # no inductance to speak of: V/R; no resistance to speak of: V*sqrt(C/L)
    assert ir.rlc_step_peak(100.0, 10.0, 1e-9, 1e-5) == pytest.approx(10.0, rel=1e-2)
    assert ir.rlc_step_peak(100.0, 1e-6, 1e-4, 1e-4) == pytest.approx(100.0, rel=1e-3)


def test_i2t_of_rc_charge():
    # over-damped 15 W circuit: I2t -> C V^2 / (2 R)
    r1, c = ir.IEC_TABLE_109[15]
    expect = c * 1e-6 * ir.V_PK ** 2 / (2 * (r1 + ir.IEC_SOURCE_R))
    assert _make(15)["i2t"][0] == pytest.approx(expect, rel=0.03)


def test_peak_follows_sine_of_closing_angle_for_short_pulse():
    p90 = _make(15, 90)["i_peak"][0]
    p30 = _make(15, 30)["i_peak"][0]
    assert p30 / p90 == pytest.approx(0.5, abs=0.06)


def test_zero_cross_closing_cuts_the_peak_but_not_to_zero():
    p90, p0 = _make(200, 90)["i_peak"][0], _make(200, 0)["i_peak"][0]
    assert p0 < 0.25 * p90
    # the capacitor still charges along the rising mains: about omega*C*Vpk
    assert p0 == pytest.approx(ir.OMEGA * 240e-6 * ir.V_PK, rel=0.25)


def test_lamp_count_scaling_linear_then_saturating():
    def peak(n, line):
        R, L, C = ir.load_circuit(10.0 * n, "high", line)
        return ir.simulate_make(R, L, C, np.array([np.pi / 2]), t_end=6e-3)["i_peak"][0]
    assert 1.8 < peak(2, "stiff") / peak(1, "stiff") < 2.0                         # nearly lamp-limited
    assert peak(160, "stiff") / (160 * peak(1, "stiff")) < 0.25                    # line-limited
    assert peak(160, "soft") < 0.75 * peak(160, "stiff")                           # line impedance matters
    assert peak(160, "stiff") < ir.V_PK / ir.LINE_CLASSES["stiff"]["R"]            # bounded by V/R_line


def test_no_bounce_no_arc_energy_and_charge_bound():
    o = _make(200)
    assert o["w_arc"][0] == 0.0
    rng = np.random.default_rng(0)
    to, tc = ir.Bounce().draw(200, rng)
    r1, c = ir.IEC_TABLE_109[200]
    o = ir.simulate_make(r1 + ir.IEC_SOURCE_R, ir.IEC_SOURCE_L, c * 1e-6, np.full(200, np.pi / 2), to, tc)
    assert np.all(o["w_arc"] > 0)
    assert np.all(o["q_arc"] <= c * 1e-6 * ir.V_PK * 1.001)        # cannot move more charge than C*Vpk
    assert np.allclose(o["w_arc"], ir.U_ARC * o["q_arc"])


def test_arc_energy_depends_on_angle_less_than_peak_current_does():
    rng = np.random.default_rng(1)
    to, tc = ir.Bounce().draw(300, rng)
    r1, c = ir.IEC_TABLE_109[200]
    def run(deg):
        return ir.simulate_make(r1 + ir.IEC_SOURCE_R, ir.IEC_SOURCE_L, c * 1e-6, np.full(300, np.radians(deg)), to, tc)
    a90, a0 = run(90), run(0)
    r_peak = a90["i_peak"].mean() / a0["i_peak"].mean()
    r_arc = a90["w_arc"].mean() / a0["w_arc"].mean()
    assert r_arc > 1.5
    assert r_arc < r_peak
