# Sources

Each entry says what was taken and how much of the source was actually read
(looked up on 16 November 2026). Paywalled standard text is not quoted; table
values are used as test data. Anything not listed here is an assumption and is
marked as such in `DOSSIER.md` section 7.

## Standards

| # | Source | Read | What was taken |
|---|---|---|---|
| S1 | IEC 60669-2-1, *Switches for household and similar fixed electrical installations, Part 2-1: Electronic switches*. Read as the national adoption PS IEC 60669-2-1 published by the Pakistan Standards and Quality Control Authority: https://psqca.com.pk/cs/newitems2021/electrotechnical/42-PS%20IEC%2060669-2-1.pdf | 19.109, Tables 108 and 109, Annex BB in full | Lamp-load test for contact mechanisms in electronic switches: 40 000 operations (30 per minute up to 250 W, 15 per minute above). Table 108: peak current and I2t against rated lamp power for 230 V (15 W: 22 A, 0.08 A2s ... 200 W: 170 A, 9 A2s ... 400 W: 235 A, 24.5 A2s). Table 109 (informative): R1 and C of the equivalent lamp circuit (15 W: 13 ohm, 20 uF ... 400 W: 0.59 ohm, 480 uF). Circuit values are set for closing at (90 +/- 5) degrees. Annex BB: supply of 3 kA prospective current at cos phi 0.9 (0.069 ohm + 106 uH) plus cable (0.25 ohm + 20 uH) = 0.319 ohm + 126 uH; single lamp up to 15 W at 230 V: 20 A, 0.08 A2s behind 0.2 ohm + 400 uH; multiple-lamp rules; the table stops at 400 W because larger inrush trips circuit breakers; the annex names sticking of contacts in electromechanical contact mechanisms as the problem. |
| S2 | IEC 60669-1:2017 (edition 4), preview with table of contents: https://assets.vde-verlag.de/iec-normen/preview-pdf/info_iec60669-1%7Bed4.0.RLV%7Den.pdf | Contents and foreword only | Edition 4 added 19.3 "Test for switches intended for self ballasted lamp loads", Table 2 (rated current against rated SBL power), Table 19 (Ipeak and I2t) and Annex C (circuit development). The values themselves were not read from Part 1; the project uses the Part 2-1 tables (S1). |
| S3 | Intertek, summary of EN 60669-1:2018: https://www.intertek.com.hk/electrical/appliances-consumer-electronics-testing/wall-switch-standard-en-60669-1/ | Full page | SBL loads of 100 / 150 / 200 / 250 W for switches rated 10 / 13 / 16 / 20 A; 5 000 to 20 000 cycles in Part 1. Used for the 200 W rating of a 16 A channel. Secondary source. |
| S4 | IEC 61810-1 / IEC 61810-2 (electromechanical elementary relays; reliability) | Not read | Named only as the relay standards a relay maker tests to (S7 lists IEC 61810-1 compliance). No value taken. |

## Relay makers

| # | Source | Read | What was taken |
|---|---|---|---|
| S5 | Finder, *Technical information* (general technical pages of the catalogue): https://cdn.findernet.com/app/uploads/TecEN.pdf | Contact, lamp-load and timing sections | Contact material table: AgNi "medium resistance to welding", AgSnO2 "excellent resistance to welding", for lamp, capacitive and very high inrush loads. Maximum peak current is defined for inrush up to 0.5 s. LED lamp ratings are given as a peak current and I2t "not to be exceeded to avoid sticking of the relay contacts". Life from the charts can be taken as B10; operate time excludes bounce time. |
| S6 | Finder 19.91 power relay module 16 A, data sheet (distributor copy): https://static.maritex.eu/file/display/wnuTu-N8NLRuMswZulpvuiLONAiR5LO2/19-91-9-024-4000.pdf | Full | A 16 A AgSnO2 contact: peak 120 A for 5 ms, 230 V LED lamps 400 W, CFL 400 W, incandescent 2000 W, electrical life 80 000 cycles at AC1, operate / release time 12 / 8 ms. Used as the picture of a "normal" 16 A lamp relay. |
| S7 | Zettler AZ762T, 16 A high inrush relay, data sheet: https://www.azettler.com/pdfs/az762t.pdf | Full | AgSnO2 with tungsten pre-make contact; inrush 165 A (20 ms) / 500 A (2 ms) / 800 A (200 us); operate time typical 7 ms, maximum 15 ms; rated loads with 6 000 to 30 000 cycles. Used for the relay-upgrade option: 800 A at 200 us against the 235 A test peak of a 400 W LED rating gives the factor 3.4 on the weld threshold (my derivation, an assumption). |
| S8 | TE Connectivity, "Contact load/life performance enhancement": https://www.te.com/en/products/relays-and-contactors/relays/intersection/contact-load-life-performance-enhancement.html | Full page | Make within about +/-1 ms of the voltage zero for lamps and capacitive loads; operate time varies by relay family, relay to relay, lot to lot and over life; best done with a microcontroller that measures the real operate time and uses a moving average over 8 to 10 operations; life gains of about 8 to 10 times are quoted. Used to set the three timing-scatter levels and to compare the model's benefit with a published figure. |
| S9 | TE Connectivity, electromechanical relay information page (operate time and bounce against temperature and coil voltage): https://www.te.com/en/products/relays-and-contactors/electromechanical-relays/intersection/electro-mechanical-relays.html | Full page (graphs not readable as numbers) | Operate time rises and scatters more with temperature; higher coil voltage shortens it; bounce time in a population of monostable relays varies by more than 2 ms. Qualitative support for the scatter levels; no number taken. |

## Inrush limiter

| # | Source | Read | What was taken |
|---|---|---|---|
| S10 | TDK product data for EPCOS B57364S0109M000 (S364, 1 ohm): https://electrokit.com/upload/quick/3f/90/d18f_41022391.pdf | Full (one page) | R25 = 1 ohm +/-20 %, maximum current 16 A, test capacitance 1000 uF at 230 V, diameter 21 mm, -55 to 170 deg C. |
| S11 | Distributor listing for the same part (B = 2800 K, dissipation factor 24 mW/K, thermal time constant 100 s, 5.1 W) | Seen in a search-result summary only | Used for the NTC thermal model. Not re-checked against the maker's PDF (the maker's server refused the download). Treat as an assumption. |

## Papers (abstracts only unless stated)

| # | Source | What was taken |
|---|---|---|
| P1 | K. Hotta et al., "Contact Welding Mechanism With Bounce Arc on Ag and Cu Contacts in Low-Voltage Switches", IEEE Trans. CPMT, 2017. https://consensus.app/papers/details/w:324ffa11-54ba-416d-8277-7cbbff7f9e0a/ | Weld force rises with the arc energy supplied during bounce at make (200 V AC, 60-500 A, 0.12-2.42 ms); the welded area is 25-40 % of the melted area. Basis of "weld force proportional to bounce-arc energy". |
| P2 | K. Hotta et al., "Dependence of contact weld force on arc energy supplied to contact surface in low voltage switches", IEEE Holm Conf., 2015. https://consensus.app/papers/details/w:a8d619c3-1322-4b17-9718-9222200ea36f/ | Same relation; tensile strength of silver 170 N/mm2. |
| P3 | X. Zhang et al., "Experimental Investigation of Contact Welding Characteristics of Electromechanical Relays", IEEE Trans. Ind. Electron., 2020. https://consensus.app/papers/details/w:e438ed84-9902-4912-880e-a60fc2543275/ | The bounce arc is decisive for the weld nugget; weld force is reported as a statistical distribution. Basis of the operation-to-operation scatter. |
| P4 | X. Zhang et al., "Effect of Electrical Load on Contact Welding Failure of Silver Tin Oxide Material Used in DC Electromechanical Relays", IEEE Access, 2019. https://consensus.app/papers/details/w:c2767f6b-1b36-4a1a-9315-483678613709/ | Under capacitive load, bounce energy and contact resistance rise sharply near the end of life and precede the weld. Basis of the wear term (kappa). |
| P5 | F. Guo et al., "Preliminary Study on Making Arc Characteristics of AgSnO2 Contact", Plasma Physics and Technology, 2019. https://consensus.app/papers/details/w:91700949-c600-45df-8180-d0a8a9e7b9ad/ | Welding at make appears after the contact has been eroded to a certain extent. Same use as P4. |
| P6 | L. Morin et al., "Make arc erosion and welding in the automotive area", IEEE Trans. CPT, 2000. https://consensus.app/papers/details/w:1f90c96e-8021-42db-a6c7-53f40874cdfc/ | Welding happens at the beginning of a bounce and mainly under the high inrush of lamp loads. |
| P7 | L. Doublet et al., "Make arc erosion and welding tendency under 42 VDC in automotive area", IEEE Holm Conf., 2004. https://consensus.app/papers/details/w:f756a794-f743-46cd-ae5b-1db3ab5a094f/ | A relay bounce is simulated as 600 us long and 80 um high. Source of the 600 us median bounce opening. |
| P8 | A. Ksiazkiewicz et al., "Welding tendency for selected contact materials under different switching conditions", Eksploatacja i Niezawodnosc, 2019. https://consensus.app/papers/details/w:e8f8f554-763f-4e3c-a0ae-3f74657312c9/ | For AgNi, AgCdO and AgSnO2 the welding tendency in AC depends on the phase at which the contact makes. |
| P9 | V. Cuk, J.F.G. Cobben, W.L. Kling, "Inrush related problems caused by lamps with electronic drivers and their mitigation", 15th WSEAS Int. Conf. on Systems, 2011. https://research.tue.nl/en/publications/inrush-related-problems-caused-by-lamps-with-electronic-drivers-a/ | Some LED and discharge lamps cause trouble in small numbers, others not even in large numbers. Reason for three lamp inrush classes. |
| P10 | OliNo, "Inrush current for (LED) light bulbs", measurement method article: https://olino.org/blog/us/articles/2013/10/22/inrush-current-for-led-light-bulbs/ (full page) | Inrush is measured by sweeping the switch-on angle; the worst case for LED lamps is usually near 90 degrees. |

## Method references

| # | Source | What was taken |
|---|---|---|
| M1 | C. S. Wasson, *System Engineering Analysis, Design, and Development*, Wiley | Structure of `DOSSIER.md`. |
| M2 | R. B. Abernethy, *The New Weibull Handbook* (median-rank regression, Bernard's approximation, Johnson's adjusted ranks, batch clues) | Method only, from general knowledge of the book; no number taken. |
| M3 | U. Genschel, W. Q. Meeker, "A comparison of maximum likelihood and median-rank regression for Weibull estimation", Quality Engineering, 2010 | Seen as cited in the `weibulltools` package vignette (search-result summary). Used only as the reason to report both estimators; the comparison in this repo is my own (tests and results). |
| M4 | M. Kulldorff, "A spatial scan statistic", Commun. Statist. Theory Meth., 1997 | The likelihood-ratio scan used for the production-week window. From general knowledge; not re-read. |
| M5 | `lifelines` 0.30.3 (WeibullFitter) and `scipy.stats.weibull_min` | Independent implementations that the Weibull code is tested against. |

## Looked for and not found

- The Ipeak / I2t table of IEC 60669-1:2017 itself (Table 19). Only the contents page is public.
- A primary source for the minimum arc voltage and current of silver (about 12 V and 0.4 A in the textbooks). The values in the code (13 V, 0.4 A) are assumptions.
- A published worked Weibull example with censored data that I could open and check digit by digit. The estimator is checked against two libraries and against synthetic data instead.
- Measured operate-time scatter of a relay in numbers. The three scatter levels are assumptions bracketed by S7 (7 ms typical, 15 ms maximum) and S8 (+/-1 ms target).
