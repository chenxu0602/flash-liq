from __future__ import annotations

import pytest

from flash_liq.liquidation_history import (
    decode_liquidate_log,
    encode_address_topic,
    filter_liquidations_by_market_metadata,
    normalize_topic,
)


def test_decode_liquidate_log() -> None:
    market_id = "0x" + "11" * 32
    caller = "0x2222222222222222222222222222222222222222"
    borrower = "0x3333333333333333333333333333333333333333"
    data = "0x" + "".join(value.to_bytes(32, "big").hex() for value in [100, 200, 300, 0, 0])

    event = decode_liquidate_log(
        {
            "blockNumber": "0x64",
            "transactionHash": "0x" + "aa" * 32,
            "logIndex": "0x2",
            "topics": [
                "0xa4946ede45d0c6f06a0f5ce92c9ad3b4751452d2fe0e25010783bcab57a67e41",
                market_id,
                encode_address_topic(caller),
                encode_address_topic(borrower),
            ],
            "data": data,
        }
    )

    assert event["block_number"] == 100
    assert event["fork_block"] == 99
    assert event["market_id"] == market_id
    assert event["caller"] == caller.lower()
    assert event["borrower"] == borrower.lower()
    assert event["repaid_assets"] == "100"
    assert event["repaid_shares"] == "200"
    assert event["seized_assets"] == "300"


def test_normalize_topic_requires_bytes32() -> None:
    with pytest.raises(Exception):
        normalize_topic("0x1234")


def test_filter_liquidations_by_collateral_symbol() -> None:
    events = [
        {
            "collateral_asset": {"symbol": "PT-sUSDE-26DEC2024"},
            "loan": {"symbol": "DAI"},
        },
        {
            "collateral_asset": {"symbol": "wstETH"},
            "loan": {"symbol": "WETH"},
        },
    ]

    filtered = filter_liquidations_by_market_metadata(
        events,
        collateral_symbols=("PT-",),
    )

    assert len(filtered) == 1
    assert filtered[0]["loan"]["symbol"] == "DAI"
