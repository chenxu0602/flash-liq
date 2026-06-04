from __future__ import annotations

import pytest

from flash_liq.morpho_rpc import (
    RpcError,
    decode_bool_result,
    encode_is_authorized_call,
    normalize_address,
)


def test_encode_is_authorized_call() -> None:
    data = encode_is_authorized_call(
        "0x1111111111111111111111111111111111111111",
        "0x2222222222222222222222222222222222222222",
    )

    assert (
        data
        == "0x65e4ad9e"
        "0000000000000000000000001111111111111111111111111111111111111111"
        "0000000000000000000000002222222222222222222222222222222222222222"
    )


def test_decode_bool_result() -> None:
    assert decode_bool_result("0x" + "0" * 63 + "1")
    assert not decode_bool_result("0x" + "0" * 64)


def test_rejects_invalid_address() -> None:
    with pytest.raises(RpcError):
        normalize_address("https://example.invalid/rpc-secret")
