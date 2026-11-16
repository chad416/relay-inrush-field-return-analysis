# Design FMEA extract: relay output channel, before and after the corrective action

Scope: one relay output channel of a switch actuator, function "switch a 230 V
lighting load on and off". Ratings 1-10 for severity (S), occurrence (O) and
detection (D); RPN = S x O x D. The ratings are engineering judgement. Where an
occurrence rating leans on a number from this study, the number is given and
comes from `results/summary.json` (simulated, see README).

Occurrence scale used: 2 = below 0.05 % of channels in 10 years, 3 = up to 0.2 %,
4 = up to 0.5 %, 6 = up to 2 %, 8 = up to 10 %.

## Before

| # | Failure mode | Effect | S | Cause | O | Present control | D | RPN |
|---|---|---|---|---|---|---|---|---|
| 1 | Contact welds at make | Load cannot be switched off; lights stay on, other loads keep running | 8 | Bounce-arc energy of LED inrush above the weld threshold when the LED load on the channel is above the 200 W rating; closing angle is random | 8 (6.65 % of channels in 10 years on the LED-heavy mix) | Type test at the rated load only; nothing limits or records the installed load | 7 | 448 |
| 2 | Contact welds at make | As 1 | 8 | Weak contact lot: wrong alloy share or low contact force, weld threshold far below nominal | 4 (one lot in 130 weeks in truth A; that lot then fails at loads below the rating) | Incoming inspection checks dimensions and coil data, not inrush endurance | 6 | 192 |
| 3 | Installed LED load above the rating | Leads to 1 | 8 | The label and manual give "16 A"; an installer reads 16 A as 3.6 kW of LED lamps | 7 | None | 8 | 448 |
| 4 | Contact resistance rises with erosion | Terminal heating | 7 | Arc erosion from repeated inrush | 3 | Temperature-rise type test | 5 | 105 |

## After (point-on-wave closing with measured closing time, lot acceptance test, LED rating in the manual, load questionnaire with every return)

| # | Failure mode | Effect | S | Cause | O | Control | D | RPN |
|---|---|---|---|---|---|---|---|---|
| 1 | Contact welds at make | As before | 8 | As before, but the contact closes about 0.6 ms before the voltage zero | 3 (0.089 % in 10 years with 0.25 ms timing scatter) | Firmware checks the measured closing angle every operation and reports a channel that is out of window | 4 | 96 |
| 2 | Contact welds at make | As before | 8 | Weak contact lot | 2 | Sample of every relay lot runs a shortened lamp-load endurance test at 400 W before release | 3 | 48 |
| 3 | Installed LED load above the rating | Leads to 1 | 8 | As before | 5 | LED watts per channel printed in the manual and in the commissioning tool; welds no longer follow directly from the overload | 6 | 240 |
| 4 | Contact resistance rises with erosion | Terminal heating | 7 | As before, less arc energy per operation | 2 | As before | 5 | 70 |
| 5 | New: closing-time measurement fails | Channel falls back to random closing; weld risk as before on that channel | 8 | Sense input open, stuck or noisy | 2 | Plausibility check of the sensed closing time; diagnostic flag on the bus | 3 | 48 |
| 6 | New: aiming point drifts | Benefit lost gradually | 6 | Operate time changes with coil temperature, supply voltage and relay age faster than the tracking filter follows | 3 | Moving average over the last 8 to 10 operations; limit on the allowed correction per operation | 4 | 72 |
| 7 | New: mains zero not detected | No synchronisation | 6 | Distorted mains, DC load, channel switched with no voltage present | 3 | Fall back to random closing and count the events | 4 | 72 |

Highest RPN goes from 448 to 240. Line 3 stays the largest item because a
firmware change in new units does nothing for the way existing installations
are loaded; see D3 and D6 of the 8D report.
