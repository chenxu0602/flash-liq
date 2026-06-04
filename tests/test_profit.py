from __future__ import annotations

import pytest

from flash_liq.profit import estimate_liquidation_profit, rank_positions_by_estimated_profit


def test_estimate_debt_limited_profit_from_lltv() -> None:
    estimate = estimate_liquidation_profit(
        {
            "borrow_assets_usd": 1000,
            "collateral_usd": 2000,
            "lltv": "860000000000000000",
        }
    )

    assert estimate["priced"]
    assert estimate["value_limited_by"] == "debt"
    assert estimate["liquidation_incentive_factor"] == pytest.approx(1.0438413361)
    assert estimate["gross_profit_usd"] == pytest.approx(43.8413361)


def test_estimate_collateral_limited_profit() -> None:
    estimate = estimate_liquidation_profit(
        {
            "borrow_assets_usd": 1000,
            "collateral_usd": 500,
            "lltv": "860000000000000000",
        }
    )

    assert estimate["priced"]
    assert estimate["value_limited_by"] == "collateral"
    assert estimate["max_repay_usd"] == pytest.approx(479.0)
    assert estimate["gross_profit_usd"] == pytest.approx(21.0)


def test_rank_filters_unpriced_by_default() -> None:
    positions = [
        {"borrow_assets_usd": 100, "collateral_usd": 100, "lltv": "860000000000000000"},
        {"borrow_assets_usd": 1000, "collateral_usd": None, "lltv": "860000000000000000"},
        {"borrow_assets_usd": 200, "collateral_usd": 200, "lltv": "860000000000000000"},
    ]

    ranked = rank_positions_by_estimated_profit(positions)

    assert len(ranked) == 2
    assert ranked[0]["borrow_assets_usd"] == 200
