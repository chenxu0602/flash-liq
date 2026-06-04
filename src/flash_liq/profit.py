from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

WAD = Decimal(10) ** 18
LIQUIDATION_CURSOR = Decimal("0.3")
MAX_LIQUIDATION_INCENTIVE_FACTOR = Decimal("1.15")


def estimate_liquidation_profit(position: dict[str, Any]) -> dict[str, Any]:
    """Estimate gross liquidation upside from Morpho API USD fields."""
    borrow_usd = parse_decimal(position.get("borrow_assets_usd"))
    collateral_usd = parse_decimal(position.get("collateral_usd"))
    lif = liquidation_incentive_factor(position.get("lltv"))

    missing = []
    if borrow_usd is None:
        missing.append("borrow_assets_usd")
    if collateral_usd is None:
        missing.append("collateral_usd")
    if lif is None:
        missing.append("lltv")

    if missing:
        return unpriced_estimate("missing:" + ",".join(missing))

    if borrow_usd <= 0 or collateral_usd <= 0:
        return unpriced_estimate("non_positive:borrow_or_collateral_usd")

    repay_limited_by_collateral = collateral_usd / lif
    repay_usd = min(borrow_usd, repay_limited_by_collateral)
    seized_collateral_usd = min(collateral_usd, repay_usd * lif)
    gross_profit_usd = seized_collateral_usd - repay_usd

    value_limited_by = "collateral" if repay_limited_by_collateral < borrow_usd else "debt"

    return {
        "priced": True,
        "unpriced_reason": None,
        "liquidation_incentive_factor": decimal_to_float(lif),
        "liquidation_bonus_bps": decimal_to_float((lif - 1) * Decimal(10_000)),
        "max_repay_usd": decimal_to_float(repay_usd),
        "seized_collateral_usd": decimal_to_float(seized_collateral_usd),
        "gross_profit_usd": decimal_to_float(gross_profit_usd),
        "value_limited_by": value_limited_by,
    }


def rank_positions_by_estimated_profit(
    positions: list[dict[str, Any]],
    *,
    include_unpriced: bool = False,
    min_gross_profit_usd: float | None = None,
) -> list[dict[str, Any]]:
    ranked = []
    min_profit = Decimal(str(min_gross_profit_usd)) if min_gross_profit_usd is not None else None

    for position in positions:
        enriched = dict(position)
        estimate = estimate_liquidation_profit(position)
        enriched["profit_estimate"] = estimate

        gross_profit = parse_decimal(estimate.get("gross_profit_usd"))
        if not estimate["priced"]:
            if include_unpriced:
                ranked.append(enriched)
            continue
        if min_profit is not None and (gross_profit is None or gross_profit < min_profit):
            continue
        ranked.append(enriched)

    return sorted(
        ranked,
        key=lambda position: position["profit_estimate"].get("gross_profit_usd") or 0,
        reverse=True,
    )


def liquidation_incentive_factor(lltv_wad: Any) -> Decimal | None:
    lltv = parse_decimal(lltv_wad)
    if lltv is None:
        return None

    lltv_fraction = lltv / WAD
    if lltv_fraction < 0 or lltv_fraction >= 1:
        return None

    lif = Decimal(1) / (Decimal(1) - LIQUIDATION_CURSOR * (Decimal(1) - lltv_fraction))
    return min(MAX_LIQUIDATION_INCENTIVE_FACTOR, lif)


def parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def decimal_to_float(value: Decimal) -> float:
    return float(value)


def unpriced_estimate(reason: str) -> dict[str, Any]:
    return {
        "priced": False,
        "unpriced_reason": reason,
        "liquidation_incentive_factor": None,
        "liquidation_bonus_bps": None,
        "max_repay_usd": None,
        "seized_collateral_usd": None,
        "gross_profit_usd": None,
        "value_limited_by": None,
    }
