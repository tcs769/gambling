# Tanaka: every number on every screen (as displayed, with exact dollars)

All figures are the engine's, in 2026 dollars, liquidated at 80 unless a row says "heirs", on 2,000 simulated futures the plan was not chosen on.
They are identical on every run in demo mode. Copied from the screens at `http://localhost:3000/showcase...` on the final build; exact values from
`GET /showcase` and `GET /showcase/scenarios/{job_loss,market_drop}`.

## Screen 1: Household (`/showcase`)
Kenji Tanaka, 50, one earner, a child aged 10. Income $204,268 a year. Saved $1,193,283: taxable $645,777 (54%; cost basis $232,795, unrealized gain $412,981),
401(k)/IRA $429,185 (36%), Roth $94,380 (8%), cash $23,940 (2%). College $44,540 a year for 4 years from age 58; retire at 60 spending $90,015 a year;
Social Security $61,280 a year from 67. Footer: "Results for this household. A typical household in our model sees about 1.7% a year. Prototype for illustration only."

## Screen 2: Wealth, advisor only (`/showcase/wealth`)
| | Good advisor |
|---|---|
| Typical (median) wealth at 80 | $1.3M ($1,297,356) |
| Bad market (10th percentile) at 80 | $280k ($280,009) |
| Chance of running out of money | 3.9% |

## Screen 2b: after "Show what Donabach does"
| | Donabach | Good advisor |
|---|---|---|
| Typical (median) wealth at 80 | $2.38M ($2,383,672) | $1.3M ($1,297,356) |
| Bad market (10th percentile) | $396k ($396,246) | $280k ($280,009) |
| Chance of running out of money | 2.8% (2.75%) | 3.9% |

* **Median advantage: +2.05% a year** (+2.048%), **$1.09M more at 80** ($1,086,316); 90% range when the futures are resampled +1.97% to +2.15%.
* **Risk-adjusted advantage: +0.60% a year** (+0.599%), +$40.8k at 80 ($40,760). Shown once, here. "Bad futures weigh more than good ones (risk aversion 3, a $50,000 floor), so extra risk is credited less."
* Passed to heirs at 80: Donabach $2.38M ($2,384,063), good advisor $1.26M ($1,255,583), median advantage +2.16% a year, $1.13M more at 80 ($1,128,480). No risk-adjusted figure for heirs.

## Screen 3: Waterfall, median only (`/showcase/strategies`)
Good advisor median $1.3M at 80 → Donabach $2.38M. Total +2.05% a year, +$1.09M at 80.
| Strategy | Dollars at 80 | Percent a year |
|---|---|---|
| Lower, flat fee | +$331k ($331,457) | +0.76% (0.761) |
| Asset location | +$121k ($120,975) | +0.24% |
| Highest-cost lots first | +$45.1k ($45,055) | +0.086% |
| 6-year spending reserve, the rest in stocks | +$322k ($321,993) | +0.56% |
| 15% private credit | +$126k ($126,202) | +0.20% |
| Roth conversions up to the 22% bracket | +$120k ($119,680) | +0.18% |
| Tax-aware withdrawal order | +$21k ($20,955) | +0.030% |
| **Total** | **+$1.09M ($1,086,316)** | **+2.05%** |

## Screen 4: What if (`/showcase/whatif`)
| | No change | Job loss next year | Market drops 30% next year |
|---|---|---|---|
| Median advantage | +2.05% a year | **+1.98%** a year (+1.978%) | **+1.08%** a year (+1.078%) |
| In dollars at 80 | $1.09M more | $989k more ($988,861) | $295k more ($295,477) |
| Donabach typical wealth at 80 | $2.38M | $2.23M ($2,225,746) | $1.07M ($1,074,315) |
| Good advisor typical wealth at 80 | $1.3M | $1.24M ($1,236,885) | $779k ($778,838) |
| Bad market (10th percentile): Donabach | $396k | $319k ($318,717) | $84.3k ($84,328) |
| Bad market (10th percentile): advisor | $280k | $237k ($236,680) | −$26k (−$25,991) |
| Chance of running out of money: Donabach | 2.8% | 3.4% | 7% (7.05%) |
| Chance of running out of money: advisor | 3.9% | 4.3% | 11.3% (11.35%) |
| Passed to heirs, median advantage | +2.16% | +2.09% | +1.37% |
| Planning again vs keeping the original plan | | +0.018% a year (+$12.2k) | −0.66% a year (−$238k) |

The risk-adjusted advantage is not on the what-if screen: it appears once, on the wealth screen (+0.60%). For reference the what-if runs measured +0.46% (job loss) and +0.58% (market drop).

What the plan changes (the plan's own response to the event, from the screen):
* Job loss: at 51 $243,600 is converted to Roth (before: $62,324); at 60 $78,805 of gains are realized tax-free (before: $0). Planning again also changes: at 50 $255,144 converted (before $62,994); at 74 $73,302 of gains realized tax-free (before $12,421); at 76 $52,754 of losses harvested (before $0).
* Market drop: at 60 $45,873 is converted to Roth (before: $143,195); at 66 $6,854 of gains realized tax-free (before $98,900); at 60 the plan holds 66% stocks (before 75%). Planning again: a 9-year reserve, fill the 12% bracket in low-income years, instead of a 6-year reserve and the 22% bracket; it costs −0.66% a year of median wealth on those futures.

## Things that do not match what you may have in mind
* The typical household in the footer is **1.7%** (1.67%, the median of the 300-household study, liquidity-matched plans), not 1.6%. The footer is computed from the study, so it says 1.7%.
* The headline is +2.05%, not 2.2%.
