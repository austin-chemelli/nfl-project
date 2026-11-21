"""Price arithmetic for the betting guide (ADR 0033). Pure functions on floats, no data.

American odds: -150 means stake 150 to win 100; +130 means stake 100 to win 130.
Decimal odds: the total returned per 1 staked on a win (stake included).
"""

from __future__ import annotations

import math


def decimal(american: float) -> float:
    """American -> decimal odds."""
    if american == 0:
        raise ValueError("0 is not a price")
    return 1 + (american / 100 if american > 0 else 100 / -american)


def american(dec: float) -> float:
    """Decimal -> American odds (continuous across even money)."""
    if dec <= 1:
        raise ValueError("decimal odds must exceed 1")
    return (dec - 1) * 100 if dec >= 2 else -100 / (dec - 1)


def implied(american_price: float) -> float:
    """The win chance the price implies, vig included (the break-even rate)."""
    return 1 / decimal(american_price)


def vig_free(home: float, away: float) -> tuple[float, float]:
    """Both sides' prices -> the two vig-free win chances (proportional method)."""
    ph, pa = implied(home), implied(away)
    return ph / (ph + pa), pa / (ph + pa)


def hold(home: float, away: float) -> float:
    """The book's cut on a two-way market: the share of a balanced book it keeps."""
    s = implied(home) + implied(away)
    return 1 - 1 / s


def ev(p: float, american_price: float) -> float:
    """Expected profit per 1 staked when the true win chance is p."""
    return p * decimal(american_price) - 1


def breakeven_price(p: float) -> float:
    """The worst American price at which a bet with win chance p still breaks even."""
    if not 0 < p < 1:
        raise ValueError("p must be in (0, 1)")
    return american(1 / p)


def kelly(p: float, american_price: float) -> float:
    """Kelly stake as a share of bankroll: (p·d − 1)/(d − 1); 0 when the bet has no edge."""
    d = decimal(american_price)
    return max(0.0, (p * d - 1) / (d - 1))


def parlay_decimal(prices: list[float]) -> float:
    """Decimal odds of a parlay of independent legs: the product of the legs' decimal odds."""
    return math.prod(decimal(x) for x in prices)


def exchange_price(p_contract: float, fee_rate: float = 0.07) -> float:
    """An exchange contract bought at p_contract (0-1, dollars per $1 payout) with a taker fee of
    fee_rate·p·(1−p) per contract (Kalshi-style), as the equivalent American price."""
    cost = p_contract + fee_rate * p_contract * (1 - p_contract)
    return american(1 / cost)


def shade(american_price: float, cents: float) -> float:
    """A price `cents` worse for the bettor, in the bettor's usual sense of cents: -140 -> -150
    for 10 cents; +130 -> +120. Crossing even money continues on the other side."""
    if american_price < 0:
        return american_price - cents
    out = american_price - cents
    return out if out >= 100 else -100 - (100 - out)
