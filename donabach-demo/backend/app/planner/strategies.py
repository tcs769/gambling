"""The strategy menu: every combination of the seven choices Donabach plans over.

* Stock share of long-term money: 50/60/70/80/90/100%, held until 58, then gliding down 25 points by 70
* Roth conversions: none, or fill the 12/22/24% bracket, either in low-income years and
  retirement only, or every year (7 options)
* Private credit sleeve: 0, 5, 10 or 15% of long-term money (pre-tax account first, then Roth, then taxable)
* Direct indexing: off (fund-level harvesting) or on (harvest by stock)
* Goal-matched bonds: off, or fund each goal fully four years ahead in bonds
* 401(k) contributions: pre-tax, Roth, or Roth in low-income years only
* Goal funding: sell assets, or borrow against the taxable account (box spread, up to 30% of it)

Every strategy also uses Donabach asset location (private credit, then bonds, in pre-tax first;
Roth holds stocks), withdraws pre-tax up to the bracket target then brokerage then Roth, and
pays a flat 0.35% fee.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from app.sim.simulate import DONABACH_FLAT_FEE, Policy
from app.tax import params_2026 as P

STOCK_SHARES = (0.50, 0.60, 0.70, 0.80, 0.90, 1.00)
PRE_REVIEW_STOCK_SHARES = (0.70, 0.80, 0.90, 1.00)  # the menu before spec A2 widened it
GLIDE_START_AGE = 58.0
GLIDE_DROP = 0.25
PRIVATE_CREDIT_SHARES = (0.0, 0.05, 0.10, 0.15)
K401_OPTIONS = ("pretax", "roth", "roth_low")
GOAL_FUNDING_OPTIONS = ("sell", "borrow")

# option name -> (bracket label, bracket top, every year?)
CONVERSION_OPTIONS: dict[str, tuple[int | None, float, bool]] = {
    "none": (None, 0.0, False),
    "fill12_low": (12, P.TOP_OF_12, False),
    "fill12_every": (12, P.TOP_OF_12, True),
    "fill22_low": (22, P.TOP_OF_22, False),
    "fill22_every": (22, P.TOP_OF_22, True),
    "fill24_low": (24, P.TOP_OF_24, False),
    "fill24_every": (24, P.TOP_OF_24, True),
}

# The seven choices, in the order the recommender reports them.
CHOICES = ("stock_share", "conversion", "private_credit", "direct_indexing", "goal_bonds", "k401", "goal_funding")
CHOICE_OPTIONS: dict[str, tuple[str, ...]] = {
    "stock_share": tuple(f"{round(s * 100)}" for s in STOCK_SHARES),
    "conversion": tuple(CONVERSION_OPTIONS),
    "private_credit": tuple(f"{round(s * 100)}" for s in PRIVATE_CREDIT_SHARES),
    "direct_indexing": ("off", "on"),
    "goal_bonds": ("off", "on"),
    "k401": K401_OPTIONS,
    "goal_funding": GOAL_FUNDING_OPTIONS,
}


@dataclass(frozen=True)
class Strategy:
    stock_share: float
    conversion: str
    private_credit: float  # share of long-term money: one of PRIVATE_CREDIT_SHARES
    direct_indexing: bool
    goal_bonds: bool
    k401: str = "pretax"  # 401(k) contribution type: one of K401_OPTIONS
    goal_funding: str = "sell"  # how goals are paid when they come due: one of GOAL_FUNDING_OPTIONS

    def __post_init__(self) -> None:
        if self.conversion not in CONVERSION_OPTIONS:
            raise ValueError(f"unknown conversion option {self.conversion!r}")
        if self.k401 not in K401_OPTIONS:
            raise ValueError(f"unknown 401(k) option {self.k401!r}; expected one of {K401_OPTIONS}")
        if self.goal_funding not in GOAL_FUNDING_OPTIONS:
            raise ValueError(f"unknown goal funding option {self.goal_funding!r}; expected one of {GOAL_FUNDING_OPTIONS}")
        if not any(abs(self.private_credit - share) < 1e-9 for share in PRIVATE_CREDIT_SHARES):
            raise ValueError(f"private credit share {self.private_credit!r} is not one of {PRIVATE_CREDIT_SHARES}")

    @property
    def key(self) -> str:
        return "|".join(self.choices().values())

    def choices(self) -> dict[str, str]:
        """The seven choices as option labels (the vocabulary the recommender uses)."""
        return {
            "stock_share": f"{round(self.stock_share * 100)}",
            "conversion": self.conversion,
            "private_credit": f"{round(self.private_credit * 100)}",
            "direct_indexing": "on" if self.direct_indexing else "off",
            "goal_bonds": "on" if self.goal_bonds else "off",
            "k401": self.k401,
            "goal_funding": self.goal_funding,
        }

    @classmethod
    def from_choices(cls, choices: dict[str, str]) -> Strategy:
        return cls(
            stock_share=int(choices["stock_share"]) / 100.0,
            conversion=choices["conversion"],
            private_credit=int(choices["private_credit"]) / 100.0,
            direct_indexing=choices["direct_indexing"] == "on",
            goal_bonds=choices["goal_bonds"] == "on",
            k401=choices["k401"],
            goal_funding=choices["goal_funding"],
        )

    @property
    def conversion_bracket(self) -> int | None:
        return CONVERSION_OPTIONS[self.conversion][0]

    @property
    def conversion_every_year(self) -> bool:
        return CONVERSION_OPTIONS[self.conversion][2]

    def policy(self) -> Policy:
        _, top, every = CONVERSION_OPTIONS[self.conversion]
        return Policy(
            stock_share=self.stock_share,
            glide_start_age=GLIDE_START_AGE,
            glide_drop=GLIDE_DROP,
            private_credit=self.private_credit,
            direct_indexing=self.direct_indexing,
            goal_bonds=self.goal_bonds,
            donabach_location=True,
            conversion_top=top,
            conversion_every_year=every,
            bracket_withdrawals=True,
            withdrawal_top=top if top > 0 else P.TOP_OF_22,
            breakpoint_fees=False,
            flat_fee=DONABACH_FLAT_FEE,
            k401=self.k401,
            goal_funding=self.goal_funding,
        )

    def short_label(self) -> str:
        """A compact label for tables, e.g. "90% stocks, fill 22% bracket (low income), private credit"."""
        if self.conversion_bracket is None:
            conversions = "no conversions"
        else:
            when = "every year" if self.conversion_every_year else "low-income years"
            conversions = f"fill {self.conversion_bracket}% bracket ({when})"
        parts = [f"{round(self.stock_share * 100)}% stocks", conversions]
        if self.private_credit:
            parts.append(f"{round(self.private_credit * 100)}% private credit")
        if self.direct_indexing:
            parts.append("direct indexing")
        if self.goal_bonds:
            parts.append("goal bonds")
        if self.k401 == "roth":
            parts.append("Roth 401(k)")
        elif self.k401 == "roth_low":
            parts.append("Roth 401(k) in low-income years")
        if self.goal_funding == "borrow":
            parts.append("borrow for goals")
        return ", ".join(parts)

    def describe(self) -> str:
        """The strategy in one plain-language sentence."""
        parts = [
            f"Hold {round(self.stock_share * 100)}% of long-term money in stocks until "
            f"{round(GLIDE_START_AGE)}, then glide down"
        ]
        if self.conversion_bracket is None:
            parts.append("no Roth conversions")
        else:
            when = "every year" if self.conversion_every_year else "in low-income years and retirement"
            parts.append(f"fill the {self.conversion_bracket}% bracket with Roth conversions {when}")
        if self.private_credit:
            parts.append(
                f"keep a {round(self.private_credit * 100)}% private credit sleeve, in the pre-tax account first, "
                "then the Roth, then the taxable account"
            )
        if self.direct_indexing:
            parts.append("harvest losses stock by stock with direct indexing")
        else:
            parts.append("harvest losses at fund level")
        if self.goal_bonds:
            parts.append("fund each goal in bonds four years ahead")
        if self.k401 == "roth":
            parts.append("make 401(k) contributions to the Roth side")
        elif self.k401 == "roth_low":
            parts.append("make 401(k) contributions to the Roth side only in low-income years, pre-tax otherwise")
        if self.goal_funding == "borrow":
            parts.append(
                "pay for goals by borrowing against the taxable account with a box-spread loan (up to 30% of it), "
                "repaid from savings or by realizing gains in low-tax years"
            )
        return "; ".join(parts) + "."


def menu(
    stock_shares: tuple[float, ...] = STOCK_SHARES,
    private_credit_shares: tuple[float, ...] = PRIVATE_CREDIT_SHARES,
) -> list[Strategy]:
    """Every strategy, in a fixed order (4,032 with the full menus)."""
    return [
        Strategy(s, conv, pc, di, gb, k401, funding)
        for s, conv, pc, di, gb, k401, funding in product(
            stock_shares,
            CONVERSION_OPTIONS,
            private_credit_shares,
            (False, True),
            (False, True),
            K401_OPTIONS,
            GOAL_FUNDING_OPTIONS,
        )
    ]
