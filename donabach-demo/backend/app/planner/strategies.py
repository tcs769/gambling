"""The strategy menu: every combination of the five choices Donabach plans over.

* Stock share of long-term money: 70/80/90/100%, held until 58, then gliding down 25 points by 70
* Roth conversions: none, or fill the 12/22/24% bracket, either in low-income years and
  retirement only, or every year (7 options)
* Private credit sleeve: off, or 10% of long-term money (held in the pre-tax account)
* Direct indexing: off (fund-level harvesting) or on (harvest by stock)
* Goal-matched bonds: off, or fund each goal fully four years ahead in bonds

Every strategy also uses Donabach asset location (private credit, then bonds, in pre-tax first;
Roth holds stocks), withdraws pre-tax up to the bracket target then brokerage then Roth, and
pays a flat 0.35% fee.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from app.sim.simulate import DONABACH_FLAT_FEE, Policy
from app.tax import params_2026 as P

STOCK_SHARES = (0.70, 0.80, 0.90, 1.00)
GLIDE_START_AGE = 58.0
GLIDE_DROP = 0.25
PRIVATE_CREDIT_SHARE = 0.10

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

# The five choices, in the order the recommender reports them.
CHOICES = ("stock_share", "conversion", "private_credit", "direct_indexing", "goal_bonds")
CHOICE_OPTIONS: dict[str, tuple[str, ...]] = {
    "stock_share": tuple(f"{round(s * 100)}" for s in STOCK_SHARES),
    "conversion": tuple(CONVERSION_OPTIONS),
    "private_credit": ("off", "on"),
    "direct_indexing": ("off", "on"),
    "goal_bonds": ("off", "on"),
}


@dataclass(frozen=True)
class Strategy:
    stock_share: float
    conversion: str
    private_credit: bool
    direct_indexing: bool
    goal_bonds: bool

    def __post_init__(self) -> None:
        if self.conversion not in CONVERSION_OPTIONS:
            raise ValueError(f"unknown conversion option {self.conversion!r}")

    @property
    def key(self) -> str:
        return "|".join(self.choices().values())

    def choices(self) -> dict[str, str]:
        """The five choices as option labels (the vocabulary the recommender uses)."""
        return {
            "stock_share": f"{round(self.stock_share * 100)}",
            "conversion": self.conversion,
            "private_credit": "on" if self.private_credit else "off",
            "direct_indexing": "on" if self.direct_indexing else "off",
            "goal_bonds": "on" if self.goal_bonds else "off",
        }

    @classmethod
    def from_choices(cls, choices: dict[str, str]) -> Strategy:
        return cls(
            stock_share=int(choices["stock_share"]) / 100.0,
            conversion=choices["conversion"],
            private_credit=choices["private_credit"] == "on",
            direct_indexing=choices["direct_indexing"] == "on",
            goal_bonds=choices["goal_bonds"] == "on",
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
            private_credit=PRIVATE_CREDIT_SHARE if self.private_credit else 0.0,
            direct_indexing=self.direct_indexing,
            goal_bonds=self.goal_bonds,
            donabach_location=True,
            conversion_top=top,
            conversion_every_year=every,
            bracket_withdrawals=True,
            withdrawal_top=top if top > 0 else P.TOP_OF_22,
            breakpoint_fees=False,
            flat_fee=DONABACH_FLAT_FEE,
        )

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
            parts.append("keep a 10% private credit sleeve in the pre-tax account")
        if self.direct_indexing:
            parts.append("harvest losses stock by stock with direct indexing")
        else:
            parts.append("harvest losses at fund level")
        if self.goal_bonds:
            parts.append("fund each goal in bonds four years ahead")
        return "; ".join(parts) + "."


def menu() -> list[Strategy]:
    """All 224 strategies, in a fixed order."""
    return [
        Strategy(s, conv, pc, di, gb)
        for s, conv, pc, di, gb in product(
            STOCK_SHARES, CONVERSION_OPTIONS, (False, True), (False, True), (False, True)
        )
    ]
