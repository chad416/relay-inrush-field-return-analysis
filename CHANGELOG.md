# Changelog

## 0.1.0 - 2026-11-16

First complete version.

- Inrush model of a capacitor-input lamp load behind a bouncing relay contact,
  checked against Table 108 of IEC 60669-2-1 and an analytic R-L-C solution.
- Weld model: probability of a weld per operation from bounce-arc energy,
  calibrated on the 40 000-operation lamp test at the rated load.
- Field generator for three hidden truths (weak contact lot, design limit, both)
  with return lag, unreturned failures and censored units.
- Blind analysis: Weibull (median-rank regression and maximum likelihood with
  bounds), Nevada chart, production-week trend and scan test, load case-control
  test, decision rule, replicate study of how many returns are needed.
- Corrective-action trade study with eight variants of five options, zero-cross
  timing-scatter sweep, sensitivity runs, warranty-return forecast.
- 8D report, Ishikawa diagram, FMEA extract, dossier, sources.
- 53 tests.
