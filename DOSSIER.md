# Dossier: welded relay contacts, field-return analysis and corrective action

Simulated study. There is no hardware and no real return data. The field
failures come from a generator built on the failure physics below; the analysis
is then done blind and checked against the hidden truth. All numbers are from
`results/summary.json`. Source tags (S1, P4, ...) refer to `docs/SOURCES.md`.
The structure follows Wasson, *System Engineering Analysis, Design, and
Development* (M1).

## 1. Need and operational concept

A multi-channel switch actuator for building installations switches 230 V
loads with one 16 A relay per channel. The product sits in a distribution
board, is commanded over a bus, and is expected to run for more than 10 years.
Installers increasingly put LED lighting on these channels. LED lamps and
drivers have a capacitor behind a rectifier, so each switch-on is a short,
high current pulse through a contact that is still bouncing.

The quality team sees returns with welded contacts: the load stays on although
the channel is commanded off. They need three things:

1. a decision between "a production lot is defective" and "the design meets a
   limit in the field", because the actions are completely different (sort and
   replace a lot, or change the design and the published rating);
2. to know how much return data that decision needs;
3. a corrective action that removes the failure, shown with the same physics
   that explains the failure.

Stakeholders: quality (owner of the 8D), hardware and firmware development,
production and supplier quality (relay lots), technical support (installer
guidance), and the installer, who reads "16 A" on the label.

## 2. Modes and states

Channel, one switch-on:

| State | What happens | Model |
|---|---|---|
| Off | contact open, lamp capacitor discharged | initial condition |
| First touch | contact closes at phase angle theta | `inrush.simulate_make` |
| Bounce open 1, 2 | contact lifts; current continues through a short arc of about 13 V while more than 0.4 A flows | arc energy summed |
| Settled | contact closed, capacitor charged | end of transient |
| Welded (failure) | weld stronger than the opening force; load cannot be switched off | `weld.WeldModel` |

Closing-angle modes of the firmware: random (baseline); synchronised with a
fixed delay; synchronised with end-of-line calibration; synchronised with the
closing time measured on every operation. The last mode has a fallback state
(random closing) when the measurement is implausible; see `docs/FMEA.md`.

Analysis states: undetermined, batch, design, mixed (section 8.4).

## 3. Requirements

| ID | Requirement | Source | Verification |
|---|---|---|---|
| R1 | The contact mechanism withstands 40 000 operations on the lamp-load circuit for the declared lamp rating without sticking | IEC 60669-2-1, 19.109 and Table 108 (S1) | Test. Here: model probability that one specimen passes, at least 0.95 |
| R2 | A 16 A channel is declared for at least 200 W of self-ballasted lamps | IEC 60669-1 Table 2 as summarised in S3 | Inspection of the rating |
| R3 | At most 0.5 % of channels welded within 10 years on an LED-heavy installed base | Project target (assumption) | Analysis with the field model |
| R4 | A corrective action adds at most 1 W of dissipation per channel at 16 A | Project thermal budget for a multi-channel DIN-rail device (assumption) | Analysis; on hardware the temperature-rise test of IEC 60669-1 |
| R5 | The corrective action does not depend on what the installer does | Project decision | Review |
| R6 | A new single fault must not make the load unswitchable without being detected | Project decision | FMEA |
| R7 | The batch / design / mixed verdict is correct in at least 90 % of cases; the number of returns this needs is stated | Project decision | Replicate study, 30 populations per truth |
| R8 | The Weibull estimator agrees with an independent implementation within 0.5 % on censored data | Project decision | Tests against `lifelines` and `scipy` (M5) |
| R9 | The inrush model reproduces the standard's test table within 8 % on Ipeak and 12 % on I2t | S1, Table 108 (the standard asks for +/-5 % after trimming the circuit) | Test |

## 4. Architecture and interfaces

```
lamp + line parameters --> inrush.py  --(arc energy per make, by closing angle)--> weld.py
                                                                                      |
            hidden truth (lot, installation mix) --> field.py <--(weld probability per operation)
                                                        |
                         shipments per week + returned units only (Observed)
                                                        |
                              analysis.py: Weibull, Nevada, scan, load test, verdict, forecast
                                                        |
                              corrective.py: same inrush + weld model for each option
```

The only interface from the generator to the analysis is `field.Observed`:
units shipped per production week, and per returned unit the production week,
lab finding (weld or other), arrival day, time in service if the commissioning
date is known, and the reported LED load if a questionnaire came back. The
analysis code never receives the truth object.

## 5. Budgets and margins

Energy at the contact, 200 W lamp-test circuit (240 uF behind 0.95 ohm, supply
0.319 ohm + 126 uH):

| Quantity | Value |
|---|---|
| Charge to move, C x Vpeak | 78 mC |
| Peak current, closing at 90 degrees / at the zero | 175 A / 35.8 A |
| Bounce-arc energy per make at 90 degrees | 0.757 J |
| ... mean over random closing angles | 0.509 J |
| ... at the voltage zero | 0.171 J |
| ... at the best angle (10 degrees before the zero) | 0.0855 J |
| Median weld threshold of a nominal contact (calibrated) | 45.3 J |
| Margin, threshold over mean arc energy at the rating | 88 times, or 5.6 standard deviations of the assumed log-scatter |

The margin sounds large, but 40 000 operations probe the far tail of the
weld-force distribution. Because of that tail, doubling the load from 200 W to
400 W raises the weld probability per operation by 66 times (1.0e-7 to 6.7e-6),
and 800 W by 1360 times. At 6 operations a day that is 0.022 %, 1.5 % and 26 %
of channels welded per year. This steepness is why the failure looks like a
cliff in the field and why any weakness of a lot shows up loudly.

Timing budget for synchronised closing (section 6): the reduction halves (on a
log scale) at 0.59 ms of closing-time scatter. The relay's operate time is
7 ms typical and 15 ms maximum (S7), so the scatter that matters is under 10 %
of the operate time.

Thermal budget: 1 W per channel (R4). The NTC option needs 5.1 W at 16 A (S11).

## 6. Trade study

Decision rule, fixed before the runs: an option is feasible if it meets R3, R4
and R5; among feasible options take the lowest expected cost per channel over
10 years = BOM delta + 60 EUR x probability of a weld (cost figures are
assumptions).

Evaluated on 30 000 installations with the LED-heavy mix of truth B (half of
the LED channels in commercial lighting, median 290 W):

| Option | Welded in 2 y | Welded in 10 y | Factor at 10 y | Passes 400 W lamp test (one specimen) | BOM delta | Extra loss at 16 A | Feasible |
|---|---|---|---|---|---|---|---|
| Baseline: 16 A AgSnO2 relay, random closing | 2.08 % | 6.65 % | 1 | 0.00 | 0 | 0 | no (R3) |
| Relay with tungsten pre-make contact (S7) | 0.155 % | 2.24 % | 3.0 | 0.954 | 0.80 EUR | 0 | no (R3) |
| Zero-cross, fixed delay, sigma 1.5 ms | 0.701 % | 3.37 % | 2.0 | 0.62 | 0.30 EUR | 0 | no (R3) |
| Zero-cross, end-of-line calibrated, sigma 0.7 ms | 0.071 % | 0.858 % | 7.8 | 0.990 | 0.35 EUR | 0 | no (R3) |
| Point-on-wave, closing time measured, sigma 0.25 ms | 0.0017 % | 0.089 % | 75 | 0.9995 | 0.55 EUR | 0 | **yes** |
| Series NTC 1 ohm (S10, S11) | 1.04 % | 5.01 % | 1.33 | 0.07 | 0.45 EUR | 5.1 W | no (R3, R4) |
| Published 200 W LED limit, 70 % compliance | 0.651 % | 2.82 % | 2.4 | n/a | 0 | 0 | no (R3, R5) |
| Hybrid: semiconductor makes, relay carries | 0.018 % | 0.088 % | 76 | 1.00 | 1.60 EUR | 0 | yes |

Decision: **point-on-wave closing with measured closing time** (expected cost
0.60 EUR per channel against 1.65 EUR for the hybrid).

What the table shows that was not obvious before the runs:

- The NTC does little against this mechanism. 0.64 ohm of cold resistance
  (at 40 deg C inside the device) cuts the peak current of an 800 W load from
  375 A to 221 A, but the bounce-arc energy only from 2.75 J to 1.83 J: the
  capacitor charge still passes through the bouncing contact, only more
  slowly. After a 30 s off-time on that load the NTC is down to 0.17 ohm.
- The relay upgrade is the best hardware-only option over the warranty period
  (13 times) and falls to 3 times over 10 years because worn contacts lose
  margin in this model. That ranking depends on the wear factor kappa (section 7.4).
- "Zero-cross switching" as a fixed delay is worth a factor of 2. The benefit
  is in the last half millisecond of timing accuracy, and the right aiming
  point is about 0.6 ms before the zero, not at it (factor 149 against 16 with
  ideal timing). A relay maker's note (S8) recommends making within about
  +/-1 ms of the zero and quotes life gains of 8 to 10 times; the model gives
  3.7 to 7.8 times for 1.0 to 0.7 ms of scatter. Same order; this is a
  plausibility check, not a validation.
- The hybrid's residual is not welding but an assumed semiconductor short
  (10 FIT), which produces the same symptom. It is the most robust option
  against wrong bounce assumptions and the most expensive.

Side effects and the test that would prove each option:

| Option | Side effects | Verification test |
|---|---|---|
| Relay with tungsten pre-make | pre-make contact wears; maker rates some loads at 6 000 to 30 000 cycles (S7); second source needed | 19.109 lamp-load endurance at the new declared rating; maker's inrush rating check |
| Zero-cross, fixed delay or calibrated | wrong timing after relay ageing goes unnoticed; needs a mains zero detector per channel group | closing-angle histogram over temperature and coil voltage; 19.109 with the product's own timing |
| Point-on-wave, closing time measured | voltage sense on the load side of every channel; fallback to random closing if the sense fails | as above over 40 000 operations, plus fault insertion on the sense input |
| Series NTC | 5.1 W at 16 A; weak after a short off-time; cracks on overload | 19.109 cold and with 30 s off-time; temperature-rise test at 16 A |
| Published LED limit | none in the product; lost applications; relies on the installer | no lab test; field audit of installed loads |
| Hybrid relay | semiconductor short = load stuck on; surge voltage across the open channel; leakage current when off | 19.109; surge test (EN 61000-4-5) across the open channel; semiconductor I2t check at the zero-cross inrush |

Verification that would prove the choice on hardware: histogram of the measured
closing angle over temperature, coil voltage and 40 000 operations (must stay
within +/-0.5 ms); the 19.109 lamp-load endurance test at 400 W with the
product's own timing; the same test with the closing-time sense input
disconnected, to confirm the fallback is detected and reported.

## 7. The model and its validation

### 7.1 Inrush

Series R-L-C loop with a sine source, a rectifier (current cannot reverse) and
an initially empty capacitor, integrated with an exact discretisation of the
linear part at 2 us steps. Lamp and supply values:

| Parameter | Value | Source |
|---|---|---|
| Lamp-test circuit R1, C for 15 to 400 W | 13 ohm, 20 uF ... 0.59 ohm, 480 uF | S1 Table 109 |
| Test supply | 0.319 ohm + 126 uH | S1 Annex BB |
| "High" inrush lamps | 1.2 uF/W, 190 ohm x W | fitted to S1 Table 109 |
| "Medium" and "low" inrush lamps | 0.5 uF/W, 400 ohm x W; 0.12 uF/W, 1500 ohm x W | assumption; P9 reports that lamp types differ this much |
| Supply classes | stiff = test supply; medium 0.5 ohm + 250 uH; soft 0.7 ohm + 400 uH | assumption between the two impedances given in S1 |

Validation:

- Against S1 Table 108, all ten rows from 15 W to 400 W, with the informative
  Table 109 values and no tuning: Ipeak within 7.3 %, I2t within 11.3 %; up to
  100 W within 3.1 %. The model is high at large loads because the standard
  adds cable for every three further lamps and I do not.
- Against Table BB.1 of S1 (one lamp up to 15 W behind 0.2 ohm + 400 uH:
  20 A, 0.08 A2s): the model gives 20.2 A and 0.079 A2s.
- Against the analytic R-L-C step response: within 1 % at 15, 100 and 400 W.
- Limiting cases: V/R without inductance, V x sqrt(C/L) without resistance,
  I2t = C V^2 / (2R) for the over-damped circuit (3 %).
- Scaling: one 10 W lamp gives 15.6 A; 160 lamps give 513 A on the stiff supply
  (3.2 A per lamp) and 275 A on the soft one. Peak current follows the sine of
  the closing angle for a short pulse; at the zero it is about omega x C x Vpeak.

### 7.2 Bounce and arc

| Parameter | Value | Source |
|---|---|---|
| First opening starts after | 100 us median, log-sigma 0.5 | assumption |
| First opening lasts | 600 us median, log-sigma 0.4 | P7 simulates a 600 us relay bounce; S9 reports population spread above 2 ms |
| Second opening | after 200 us, 0.4 times as long | assumption |
| Arc voltage, minimum arc current | 13 V, 0.4 A | assumption (textbook order for silver; no primary source found) |

During an opening the current continues through the arc. The arc energy is
13 V times the charge that flows while the contact is open. Checked: no bounce
gives zero arc energy; arc charge never exceeds C x Vpeak; arc energy falls less
with closing angle than peak current does.

### 7.3 Weld probability

p = Phi((ln W_arc - ln W50) / sigma_w), with W50 falling as the contact absorbs
arc energy: ln W50(n) = ln W50_0 - kappa x (absorbed energy / energy of one
rated endurance test).

| Parameter | Value | Source |
|---|---|---|
| Form: weld force rises with bounce-arc energy, large scatter, weld counts when it exceeds the opening force | | P1, P2, P3, P6 |
| sigma_w, log-scatter of weld force | 0.8 | assumption |
| kappa, wear factor | 0.7 (threshold halves over one rated test) | assumption; direction from P4, P5 |
| W50_0 | 45.3 J | calibrated: a nominal unit passes 40 000 operations at 200 W with random closing with probability 0.95 (R1, R2) |
| Unit-to-unit log spread | 0.20 | assumption (contact force tolerance) |
| Weak lot factor | 0.065 (truth A), 0.22 (truth C) | assumption, chosen so the truths have the same return rate |
| Tungsten pre-make factor | 3.4 | derived from S7 (800 A at 200 us) against the 235 A test peak of a 400 W rating (S1); assumption |

There is no published weld-probability curve for a specific relay, so the
level cannot be validated. What can be checked is the calibration point (test:
0.95 at the rated load), monotonic behaviour in load and threshold, and that a
relay maker's "400 W LED" rating for a 16 A AgSnO2 contact (S6) is not
contradicted: recalibrating at 400 W is one of the sensitivity runs.

### 7.4 Sensitivity of the deciding assumptions

Factors are reductions of the 10-year weld fraction against the baseline.

| Case | Baseline 10 y | Relay | Fixed delay | Calibrated | Measured | Ideal | Verdicts correct |
|---|---|---|---|---|---|---|---|
| Base | 6.65 % | 3.0 | 2.0 | 7.8 | 75 | 149 | 24 of 24 |
| sigma_w 0.5 | 7.79 % | 2.9 | 1.7 | 5.6 | 59 | 100 | 24 of 24 |
| sigma_w 1.2 | 5.38 % | 2.9 | 2.2 | 9.6 | 89 | 175 | 24 of 24 |
| kappa 0 (no wear) | 6.24 % | 22 | 1.8 | 7.6 | 169 | 382 | 24 of 24 |
| kappa 1.5 | 6.68 % | 1.9 | 2.1 | 7.2 | 48 | 74 | 24 of 24 |
| Calibration pass probability 0.999 | 3.79 % | 2.7 | 2.5 | 14 | 211 | 436 | 23 of 24 |
| Rated at 400 W instead of 200 W | 2.10 % | 4.3 | 3.1 | 25 | 570 | 2150 | 22 of 24 |
| Bounce 200 us instead of 600 us | 4.37 % | 4.2 | 3.0 | 30 | 15 900 | 5.6e7 | 24 of 24 |

Reading: the choice of measured point-on-wave closing holds in every row (it
stays below 0.5 %; the worst is 0.14 % at kappa 1.5). The relay upgrade passes
R3 only without wear (0.28 %), and even then costs more. The size of the
zero-cross benefit depends strongly on bounce duration; the order of the options
does not. The verdict rule was wrong 3 times in 192, all for the mixed truth in
the two cases where the calibration leaves few returns (54 and 72 on average).

### 7.5 Field population

Every number in `field.FieldParams` is an assumption about a plausible
installed base: 600 channels per production week, 14 days to shipment, 45 days
median to commissioning, 60 % of channels on LED lighting, residential median
40 W, commercial median 160 to 290 W depending on the truth, 3 and 6 operations
per day, 0.4 % per year of unrelated failures, 60 % of failures returned after a
median of 30 days, load questionnaire on half of the returns with 25 % error.

Hidden truths (the analysis never sees these):

| Truth | Weak lot | Installed mix | Welded returns at day 910 | Share from the weak lot |
|---|---|---|---|---|
| A | weeks 44 to 51, threshold x 0.065 | 8 % commercial, constant | 289 (0.38 %) | 91 % |
| B | none | commercial share 10 % to 50 % with install date | 247 (0.32 %) | 0 |
| C | weeks 46 to 51, threshold x 0.22 | commercial share 10 % to 32 % | 252 (0.33 %) | 44 % |

## 8. Blind analysis and its check against the truth

### 8.1 Weibull with censored units

Time in service of welded returns; all 72 500 other units are suspensions at
their estimated age; other-cause returns are suspensions at their failure time.

| Truth | MLE shape (90 % bounds) | MRR shape | r2 of MRR | F(3 years) MLE / MRR |
|---|---|---|---|---|
| A | 0.441 (0.402 to 0.484) | 0.591 | 0.905 | 0.64 % / 1.02 % |
| B | 0.651 (0.590 to 0.717) | 0.736 | 0.983 | 0.66 % / 0.80 % |
| C | 0.502 (0.455 to 0.554) | 0.616 | 0.941 | 0.59 % / 0.81 % |

Fisher-matrix and likelihood-ratio bounds agree to the third digit at these
sample sizes. The characteristic life is meaningless here (0.3 % failed, eta
extrapolates to thousands of years), so the table gives F(3 years) instead.
Findings: the shape is below 1 in all three truths, also in B where nothing is
wrong with production; the cause is the mix of installations with very
different constant hazards. The value does differ between the truths (medians
of 30 replicates 0.46 in A and 0.74 in B, no overlap), but an analyst has one
population and no reference for what the other truth would have given, and
the usual reading of "below 1" points at production in both. Median-rank
regression and maximum likelihood disagree by 60 % on F(3 years) in A and by
22 % in B, and the MRR fit is visibly bent in A (r2 0.905 against 0.983). That disagreement is a usable hint that the population
is not homogeneous, but it does not say why. On synthetic data with known
parameters (shape 2, n = 10, 400 samples) the median MLE shape is 2.27 and the
median MRR shape 2.02; with 20 000 units of which 2765 fail before the cut
(true shape 1.6, scale 1000) MLE gives 1.554 and 1022, MRR 1.558 and 1017.

### 8.2 Production week

Expected counts per production week come from indirect standardisation on the
pooled return hazard by age since shipment. Then a log-linear trend in
production week, then a scan over all windows of 2 to 16 consecutive weeks
for an elevated rate (likelihood ratio, Monte Carlo p-value with the trend
refitted in every sample).

| Truth | Window found (true) | Rate ratio in window | Scan p | Trend outside the window | Batch share estimated (true) |
|---|---|---|---|---|---|
| A | weeks 44-51 (44-51) | 124 | 0.001 | not significant (p 0.08) | 0.906 (0.913) |
| B | none (none) | - | 0.39 | last week 3.1 times the first, p 2e-5 | 0 (0) |
| C | weeks 46-51 (46-51) | 12 | 0.001 | not significant (p 0.21) | 0.400 (0.437) |

Without the trend term the scan flags a "batch" in 7 of 30 replicates of truth
B (not on the main seed: weeks 92 to 102, p = 0.27). The trend in B is
not a production effect at all: later units went into a more LED-heavy
installed mix.

### 8.3 Load

Welded returns with a questionnaire are the cases, other-cause returns with a
questionnaire are the controls (they sample the installed base without bias,
because their failure does not depend on load).

| Truth | Cases above 200 W | Controls above 200 W | Odds ratio | p (Fisher, one-sided) | Median case load |
|---|---|---|---|---|---|
| A | 52 of 148 | 2 of 96 | 21 | 2e-11 | 120 W |
| B | 125 of 125 | 8 of 95 | 2580 | 2e-52 | 791 W |
| C | 126 of 135 | 6 of 95 | 183 | 4e-45 | 561 W |

A load effect is significant in all three. "They all had a lot of LED lamps" is
therefore no evidence for a design limit. The comparison with the rating is: in
A most welded units ran within the rating (65 % at or below 200 W), in B
none did.

### 8.4 Decision rule and how many returns it needs

Rule, fixed before the replicate study: *batch* if a window is significant at
0.01 and explains at least 75 % of welded returns; *design* if there is no
window and either the trend or the load test (outside any window) is
significant at 0.01; *mixed* if a window is significant, explains less than
75 %, and the rest shows design evidence.

30 populations per truth, verdict at 12 cut-off days:

| Truth | Correct in at least 90 % from | Without load information | Final (day 910) |
|---|---|---|---|
| A | 56 welded returns (day 440) | 56 | 30 of 30 |
| B | 18 (day 350) | 252 (day 910) | 29 of 30 (one "mixed") |
| C | 41 (day 440) | never: 1 of 30 at 251 returns | 30 of 30 |

Hits and misses, stated plainly:

- Hit: on the main seed all three verdicts, both windows to the week, and the
  batch share within 0.04.
- Miss by design of the situation: at day 380 truth C is called "design" in 29
  of 30 replicates and truth A is "undetermined" or "design". The weak lot was
  built in weeks 44 to 51 and has not reached the returns lab. A verdict is
  valid for the day it is made and has to be repeated.
- Miss: without load information the mixed truth is called a pure batch. The
  analyst would contain the lot and close the report while 56 % of the returns
  have another cause.
- Miss: one false "mixed" in truth B at day 910 (a chance window at the 0.01 level).

### 8.5 Forecast

Blind forecast for the 52 weeks after the cut-off (truth B, production
continuing, corrective action cut in at week 140): 341 welded returns without
action against 351 in the hidden truth (-3 %), 296 with action against 311
(-5 %). The action avoids 45 forecast and 40 true returns in that year: 87 %
of next year's returns come from units built before the cut-in. The small
error is partly luck: over ten more populations of the same truth the forecast
error without action ran from -22 % to +32 % (median +0.7 %, mean absolute
error 13 %).

## 9. FMEA

`docs/FMEA.md` holds the extract before and after. Highest RPN before: 448
(weld on LED load above the rating; installed load above the rating). After:
240 (installed load above the rating, which a firmware change in new units
does not touch). Three new failure modes of the corrective action are listed
with their detection.

## 10. V&V plan and results

| Requirement | Method | Result |
|---|---|---|
| R1 | Model endurance test, 40 000 operations | Baseline 0.95 at 200 W by calibration, 0.00 at 400 W; chosen option 0.9995 at 400 W. Not a hardware test. |
| R2 | Inspection | Baseline rating taken as 200 W. |
| R3 | Field model, 10 years | Baseline 6.65 % (fails); chosen option 0.089 % (passes); holds in all 8 sensitivity cases. |
| R4 | Datasheet value | NTC 5.1 W (fails); all others 0 W extra. |
| R5 | Review | Derating fails; others pass. |
| R6 | FMEA | Chosen option: sense failure falls back to random closing and is flagged. Hybrid: semiconductor short is not detectable by the channel itself. |
| R7 | Replicate study | Met with load information from 18, 41 and 56 returns. Not met for the mixed truth without load information. |
| R8 | 12 tests in `tests/test_weibull.py` | Shape and scale equal to `lifelines` to 7 digits on 4000 units with 571 failures and staggered censoring; same log-likelihood; complete data equal to `scipy` within 0.2 %; 90 % bounds cover the true shape in 90.3 % of 300 samples. |
| R9 | 20 tests in `tests/test_inrush.py` | 7.3 % and 11.3 % worst case. |

53 tests in total; `python -m pytest -q`.

## 11. Limits

- Everything is simulated. The weld level rests on one calibration point; the
  bounce timing and the wear factor are assumptions that change the size of the
  results (section 7.4).
- Only the bounce arc welds in this model. Static welding at very high peak
  current is not included, which understates options that limit the peak.
- The blind analysis was only tried on truths I built, with clean serial
  numbers and honest questionnaires.
- Cost figures are placeholders of the right order, not quotations.
- The next steps with real hardware are in the README.
