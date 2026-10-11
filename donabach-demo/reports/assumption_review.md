# Review of two modelling assumptions against published research (spec A8)

**Status: evidence reported, values NOT changed.** The simulator still uses the assumptions below exactly as
specified. This note reports what the research says, proposes corrected values, and (once the simulator has
the option) shows what the proposed values would do to the advantage. Whether to adopt them is your call.

## How much of this was verified

The research was done by a delegated research agent in this environment, which had no working page access:
every page fetch failed (DNS errors and a 403 from the egress proxy for irs.gov, imf.org, federalreserve.gov and
the academic hosts). **No page was opened.** Every figure below comes from web-search result excerpts. Marks:

* **S**: text seen in a search-result excerpt of the named page (the page itself was not opened)
* **S2**: second-hand: a blog, news item or summary quoting the source; treat as a lead
* **C**: our own calculation (Monte Carlo of the rule as coded)
* **M**: from memory, unverified

Treat the numbers as well-sourced leads to be confirmed against the primary documents before they are quoted
externally. Where search summaries disagreed, the agent said so and the disagreement is kept below.

## 1. Direct-indexing loss harvesting

**What the simulator assumes.** For a direct-indexing strategy, each year harvested losses are
`min(0.85 x (the year's equity decline) + 0.03 x value x min(1, basis/value), 0.35 x value, basis)`.
The dispersion term (3%) shrinks as basis falls toward value; the 85%-of-decline term does not. Harvested losses
lower basis, offset realized gains and $3,000 a year of ordinary income, carry forward, and are valued at 15% in
the terminal wealth. Not modelled: a direct-indexing fee premium, tracking error, wash-sale friction, step-up
at death (which would make part of the deferral permanent; that omission is conservative).

**What that rule produces** (C, 200,000-path Monte Carlo of the exact rule, lump sum, no flows, real returns
N(5.5%, 16%) as in `markets.py`):

| | Year 1 | Year 5 | Year 10 | Year 20 |
|---|---|---|---|---|
| Expected harvest, % of opening value | 6.2% | 5.4% | 4.6% | 2.5% |
| Cumulative harvest, % of initial principal | 6% | 32% | 67% (p10-p90 43-91%) | 139% |

**What the literature reports.**

* About 13% of the initial investment harvested in year 1, over 20% by year 3, roughly 30% cumulative by year 10 and
  then a plateau; across 64 historical 10-year starts the cumulative range was 12-62%. (The ~30% plateau is in the
  AQR abstract, S; the 13% and 12-62% figures reach us via Morningstar summaries, S2.)
* Tax benefit of about 69 bp a year in years 1-5 falling to about 9 bp in years 6-10 (S2, via Morningstar's summary
  of Israelov and Lu).
* Published after-tax "alpha" of TLH: Chaudhuri, Burnham and Lo 1.08% a year before costs, 0.82% with the wash-sale
  rule (S); Vanguard 0.47-1.27% before fees for investors with offsetting gains (S); Berkin and Ye about 0.4% (S).
  Vendor claims run 1-2% or more.
* For a household with **no other large gains** only $3,000 a year of ordinary income can be offset (IRS Topic 409,
  S), and a lack of short-term gains cuts tax alpha by about 40% (Goldberg et al., S).
* Costs the model omits: direct-indexing fees of 0.20-0.40% versus 0.03-0.10% for ETFs (Morningstar, S); tracking
  error typically 20-100 bp (blog, S2); the wash-sale rule's cost.

**Verdict: generous in aggregate; conservative in year 1.** Cumulative harvest matches the literature through
about year 3 (19% against about 20%), is too low in year 1 (6% against about 13%; Wealthfront's 2025 starters
7.86%, S), and from year 4 on is too high: about 2.2 times the published mean at year 10 and above the published
maximum of 62%. The 3% dispersion term alone already reproduces the literature's total, which includes market
declines, so stacking 85% of declines on top double-counts. The 85% share is plausible only for lots under about
two years old (Wealthfront's 2022 all-vintage yield of 10.01% in a -19% year, S); nothing found supports it for
lots with embedded gains.

**Proposed corrected parameterisation** (the agent's synthesis, not a published formula; confidence medium on
direction and the first ten years, low on the shape beyond that):

| Year | Expected harvest, % of initial value |
|---|---|
| 1 | 10-13% |
| 2 | 5-7% |
| 3 | 2-4% |
| 4-10 | 1-1.5% a year |
| 11+ | 0.5-1% a year |

Cumulative about 30% by year 10 (p10-p90 roughly 10-60%), applied to each new contribution and reinvested dividend as
well, less a direct-indexing fee premium of 0.10-0.30% a year. In the form the simulator uses, a fit to those
benchmarks is `harvest = min(0.35 V, B, 0.85 b0^3 x decline + 0.14 V b1^14)` with b = basis/value (b0 at the start of the
year, b1 after returns); it gives cumulative 11/20/26/34/47/58% at years 1/3/5/10/20/30. In a -25% year at b = 0.6
it harvests about 2-10% of value, against about 23% as coded.

## 2. Private credit sleeve

**What the simulator assumes.** 3.5% real net return, 8% volatility, normally distributed returns, correlation 0.5
with equities, no separate default or loss model, held in tax-deferred accounts first.

| Component | Verdict | Proposal |
|---|---|---|
| 3.5% real net return | Reasonable | Keep as the central case; plausible range 2-5% real (3.5% arithmetic is about 3.2% geometric, C) |
| 8% volatility | Reasonable only for an unlevered, mark-to-market-equivalent exposure | 10-12% for levered or semi-liquid retail vehicles |
| No default modelling, normal tails | Generous | A two-state or skewed distribution |
| 0.5 correlation with equities | Reasonable for reported (appraisal) returns; low for market-based returns and in stress | 0.6-0.7 in calm states, about 0.8+ in stress |

Evidence pointing both ways:

* **Return.** Cliffwater Direct Lending Index: 9.5% average over 20 years, one negative year (2008), 2025 +9.3%
  (S); but it is built from BDC filings, unlevered and gross of fees. Net to investors: BCRED Class I about 9.0% a
  year since 2021 (S); Cliffwater Corporate Lending Fund 5-year 8.9% (S2). J.P. Morgan's 2026 capital-market
  assumption for direct lending is 7.6% nominal after fees, with leverage (S). Market-based proxies are lower: a
  listed-BDC proxy 7.3% over five years (AQR, S), BIZD about 6.2% over five years (S). Academic work finds no net
  alpha (Erel, Flanagan and Weisbach; Suhonen at market value; AQR's BDC proxy alpha -3.8%, S). A forward-looking
  build-up (C): 9-10% gross yield, less 1-2% credit losses, less 2.5-3.5% retail-fund fees is about 3.5-6.5% nominal,
  roughly 1-4% real.
* **Volatility.** De-smoothed CDLI volatility 3.59% against 18.96% for a BDC market-price index over the same period
  (Suhonen, FAJ 2024, S); BIZD annual NAV returns 2018-24 have a standard deviation near 20% (C from S2 data);
  CDLI volatility is understated by about 26% (Kang, S2). 8% sits between the appraisal-based and market-based extremes.
* **Tails and defaults.** Measures disagree widely: Proskauer 2.51% (Q2 2026), KBRA about 3.3% by count, Fitch 6.3% (a
  record, twelve months to August 2026) (S); Lincoln's "bad PIK" 6.2% of loans (S); CDLI average realized loss about
  1.0% a year over 20 years (S2). BDCs show negative skew and excess kurtosis (Suhonen, S). Under N(3.5%, 8%) the
  chance of a return below -20% is 0.17% (C); an illustrative calm/stress mixture with the same mean and standard
  deviation gives 1.6% (C). Liquidity gating is a separate risk returns do not capture: non-traded BDC redemption
  requests in 2026 ran about 10-40% against 5% caps (S2 trade press); the Fed's May 2026 Financial Stability Report
  says most managers capped redemptions at 5% (S).
* **Correlation.** AQR's BDC proxy has an equity beta of 0.63 (0.70 in one secondary source) (S), implying a
  correlation of about 0.5-0.8 depending on the proxy's volatility; BDC market returns correlate 0.85 with high
  yield and 0.92 with leveraged loans (Suhonen, S); on the appraisal side a Cliffwater fund's monthly correlation
  with the S&P 500 is 0.52 (S2).
* **Fees.** Retail vehicles: management plus incentive plus other costs of roughly 3-4% before leverage; the
  Cliffwater Corporate Lending Fund's total expenses 3.20%; BlackRock BDEBT 10.5-11.4% including interest (S).

**Verdict.** The 3.5% real net return is reasonable (the historical net-of-fee records are higher, but they embed BDC
leverage and a rising-rate period; forward-looking builds are lower). The 8% volatility is reasonable for an
unlevered exposure and low for market-priced or levered vehicles. Normal tails with no separate default model are
generous: private credit's risk is concentrated in a stress state that a normal distribution with 8% volatility
understates, and the correlation with equities rises in that state.

## 3. What the corrections would do to the sample household (analysis only)

`reports/sensitivity.md` repeats the whole search with each proposed correction applied, on the same futures, scored on 2,000
held-out futures against the good RIA. As specified, the sample household gets a median advantage of +0.27% a year and a
risk-adjusted advantage of +2.54% a year (recommendation: 50% stocks, fill the 24% bracket every year, 15% private credit).

* **Direct-indexing harvest: no effect on the sample household's headline.** Its winning strategy does not use direct indexing, and
  forcing the planner to use it changes nothing, with the specified rule or the evidence-based one (with or without a 0.20% fee premium).
  The reason is mechanical: a harvested loss lowers basis by the same amount, so at the horizon the valuation credits 15% of the carried
  loss and charges 15% of the extra unrealized gain, which cancel; direct indexing only pays when losses are used earlier against
  gains or ordinary income taxed at more than 15%, which this household rarely has. That agrees with the literature's point that the
  benefit depends on the investor's other gains. For households that realize large gains the specified rule is the generous one, as
  section 1 finds.
* **Private credit is the assumption that matters.** The planner puts the maximum 15% in private credit in the sample household and in
  nearly all of the 300 household-study households, because as specified it beats bonds on both return (3.5% against 1.5%) and, per unit
  of return, risk. With a 1-point lower return the advantage is +0.11% median and +2.25% risk-adjusted; with 12% volatility and a 0.7
  correlation with stocks, +0.21% and +1.61%; with equity-linked stress tails, +0.29% and +2.36%; with the lower return and the higher
  risk together (plus the direct-indexing correction), the planner cuts the sleeve to 5% and the advantage is +0.14% and +1.37%.
  Forbidding private credit altogether gives -0.09% and +1.51%.
* **So the review points one way for the headline**: the risk-adjusted advantage of about 2.5% a year is roughly 1 point larger than it would
  be without the private-credit sleeve, and the median advantage of about +0.27% disappears without it. Neither correction is applied to the
  app; if you adopt the proposed private-credit values the sample household's figures become the rows above.

## 4. Source table (all marks as above)

| Source | Mark | Figures taken |
|---|---|---|
| Chaudhuri, Burnham, Lo (2020), "An Empirical Evaluation of Tax-Loss-Harvesting Alpha", Financial Analysts Journal 76(3) | S | 500 largest US stocks 1926-2018; alpha 1.08%/yr before costs, 0.82% with the wash-sale rule |
| Khang, Paradise, Dickson (2021), "Tax-Loss Harvesting: An Individual Investor's Perspective", FAJ 77(4) | S | Earlier work assumed unlimited gains; investor profile explains about 60% of outcome variation |
| Khang, Cummings, Paradise (2023), J. of Beta Investment Strategies 14(3) | S2 | Lump sum: about 30% of principal over 10 years, min 12%, max 62% (64 starts) |
| Israelov and Lu (2022/2023), "A Tax-Loss Harvesting Horserace" | S2 | About 69 bp/yr tax benefit in years 1-5, about 9 bp in 6-10; stocks harvest about 2.5x ETF losses |
| Liberman, Krasner, Sosner, Freitas (2023), "Beyond Direct Indexing", JBIS 14(3), AQR | S abstract; S2 | Losses taper; max average cumulative about 30%; about 13% in year 1, over 20% by year 3 (AQR sells long-short products) |
| Sosner, Gromis, Krasner (2022), JBIS 13(2); AQR (2024), "Loss Harvesting or Gain Deferral?" | S | Benefit depends on the investor's other gains; mostly deferral |
| Goldberg, Cai, Schneider (2024); Goldberg, Hand, Cai (2019), FAJ 75(2) | S | Liquidation halves tax alpha; no short-term gains cuts about 40%; 1.6-2.3% pre-liquidation in 1995-2018 with short-term gains |
| Berkin and Ye (2003), FAJ 59(4) | S | About 40 bp/yr; contributions sustain the benefit |
| Vanguard (July 2024), "Tax-loss harvesting: Why a personalized approach is important" | S | 0.47-1.27% before fees; without gains only $3,000/yr of ordinary income |
| Wealthfront (vendor) white paper and annual results | S, S2 | Direct indexing 3.61%/yr vs ETF-level 2.60% harvest yield (2015-2025); 2022 all-vintage 10.01% |
| Morningstar (Nov 2023), "Taking Tax-Loss Harvesting to the Next Level" | S | Source of the Israelov-Lu and Khang figures; direct-indexing fees 0.20-0.40% |
| Constantinides (1983), Econometrica 51(3); Stiglitz (1983); Dammon, Spatt, Zhang (2001), RFS 14(3) | S | Tax-timing option is a large part of the benefit; step-up at death raises late-life equity holdings |
| IRS Topic 409 | S | $3,000/yr offset against ordinary income, indefinite carryforward |
| Cliffwater Direct Lending Index press releases and site | S | 20-year average 9.5%; 2025 +9.3%; H1 2026 +3.0%; built from BDC filings, unlevered, gross of fees |
| Suhonen (2024), "Direct Lending Returns", FAJ 80(1) | S | De-smoothed CDLI volatility 3.59% vs BDC price index 18.96% (2009-2022); negative skew, excess kurtosis; correlations 0.85 (HY), 0.92 (leveraged loans) |
| Erel, Flanagan, Weisbach (2024), NBER WP 32278; Joenvaara and Suhonen (2026) | S, S2 | Net-of-fee abnormal return insignificant; private-credit indexes beat liquid credit |
| AQR (April 2026) note on stock-bond correlation; AQR (January 2024) private-credit modelling note | S | BDC proxy 7.3%/yr over 5 years, equity beta 0.63, alpha -3.8%; smoothing dampens beta |
| Kang (June 2026) via Swedroe | S2 | CDLI AR(1) 0.29; volatility understated about 26% |
| Fed (Cai and Haque, FEDS Note, February 2024; FEDS Note August 2026; Boston Fed August 2026; Financial Stability Report May 2026) | S | Characteristics and risks; BDC PIK share about 6% to about 10%; managers capped redemptions at 5% |
| IMF Global Financial Stability Report, April 2024, ch. 2; FSB (6 May 2026) | S (qualitative) | Fragile borrowers, stale valuations, semi-liquid vehicles |
| Proskauer Private Credit Default Index (Q2 2026); Fitch (via Bloomberg, September 2026); KBRA; Lincoln International; Moody's | S; S2 for KBRA 2026 and Moody's | Default rates 2.51% / 6.3% / about 3.3%; bad PIK 6.2% |
| BIZD and BDC market data (YCharts, Yahoo, Institutional Investor, Morningstar) | S2; S | BIZD NAV returns 2018-24 -6.9, +30.9, -6.8, +36.2, -8.6, +27.1, +15.7%; 2020 single-BDC drawdowns of 45-56% |
| BCRED, BlackRock BDEBT, Cliffwater Corporate Lending Fund fact pages; Morningstar on non-traded BDCs and interval funds | S; S2 | BCRED Class I +9.0%/yr since 2021; BDEBT total expenses 10.5-11.4%; CCLFX 3.20% |
| J.P. Morgan 2026 Long-Term Capital Market Assumptions; BlackRock direct-lending note | S | Direct lending 7.6% nominal after fees with leverage; gross asset yield about 10% |
| Redemption data (trade press: Altswire, Stanger) | S2 | BCRED 7.9% (Q1), about 10% (Q2, Q3) vs 5% cap; some funds 17-41% |

## 5. What could not be verified

* **Everything at the page level** (see the top of this note).
* TLH: the full texts of the papers; the 13% / over-20% / about 30% / 12-62% path comes only second-hand via
  Morningstar, and which of two papers it belongs to is unclear; a rigorous tracking-error number (the only one found
  is blog-level); Dammon et al.'s option value in percent.
* Private credit: the CDLI's reported standard-deviation series, 2008 and 2020 drawdowns and any net-of-fee series; any
  CDLI-to-S&P 500 correlation; the BDC index's 2020 peak-to-trough; numeric content of the IMF, BIS, ECB and Bank of
  England work; J.P. Morgan's direct-lending volatility and correlation; any Research Affiliates, Morningstar or Vanguard
  assumption for direct lending.
* Conflicts left unresolved: AQR's equity beta 0.63 versus 0.70 and its alpha's significance; Chaudhuri et al.'s
  published (1.08/0.82) versus SSRN (1.10/0.85) figures; Wealthfront's 2024 yield; the inflation assumption behind
  J.P. Morgan's real figures.

## 6. Tax constants checked in the same pass (spec A1)

Evidence level: search excerpts of IRS-hosted documents (not opened).

* **Uniform Lifetime Table** (Pub. 590-B, Table III), ages 73-90: 26.5, 25.5, 24.6, 23.7, 22.9, 22.0, 21.1, 20.2, 19.4,
  18.5, 17.7, 16.8, 16.0, 15.2, 14.4, 13.7, 12.9, 12.2. Only ages 73 and 75 appeared on IRS-hosted pages (Pub. 590-B worked
  examples); the rest matched non-IRS reproductions of Table III. `ULT_PERIODS` in `params_2026.py` matches all of them.
* **RMD start ages**: 73 for those born 1951 to 1958 or 1959 and 75 for those born 1960 or later. Born in 1959 is a statutory
  overlap (73 and 75 both apply by the text); the proposed regulations treat it as 73 and sources conflict on whether
  the final regulations settled it. The repository uses the rule as specified: 73 for 1951-1959, 75 for 1960 on.
* **2026 standard deduction** (Rev. Proc. 2025-32): married filing jointly $32,200; additional for age 65+, married,
  $1,650 per spouse ($2,050 if unmarried); both spouses 65+ gives $35,500. The separate $6,000 senior deduction of the One
  Big Beautiful Bill Act (2025-2028) is excluded on purpose.
