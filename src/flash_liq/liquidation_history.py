from __future__ import annotations

from collections.abc import Callable
from typing import Any

from flash_liq.morpho_api import MorphoApiClient, fetch_markets_by_ids
from flash_liq.morpho_rpc import (
    LIQUIDATE_TOPIC,
    MORPHO_BLUE,
    RpcError,
    eth_block_number,
    eth_get_logs,
    hex_to_int,
    normalize_address,
)


def find_morpho_liquidations(
    *,
    rpc_url: str,
    from_block: int,
    to_block: int | str,
    chunk_size: int = 10,
    limit: int | None = None,
    market_id: str | None = None,
    borrower: str | None = None,
    morpho_address: str = MORPHO_BLUE,
    progress: Callable[[dict[str, int]], None] | None = None,
    progress_every: int = 100,
) -> list[dict[str, Any]]:
    latest = eth_block_number(rpc_url=rpc_url) if to_block == "latest" else int(to_block)
    if from_block < 0:
        raise RpcError("from_block must be non-negative")
    if latest < from_block:
        raise RpcError("to_block must be greater than or equal to from_block")
    if chunk_size <= 0:
        raise RpcError("chunk_size must be positive")

    topics = [
        LIQUIDATE_TOPIC,
        normalize_topic(market_id) if market_id else None,
        None,
        encode_address_topic(borrower) if borrower else None,
    ]

    results: list[dict[str, Any]] = []
    start = from_block
    chunks_scanned = 0
    total_chunks = ((latest - from_block) // chunk_size) + 1
    while start <= latest:
        end = min(start + chunk_size - 1, latest)
        logs = eth_get_logs(
            rpc_url=rpc_url,
            address=morpho_address,
            from_block=start,
            to_block=end,
            topics=topics,
        )
        chunks_scanned += 1
        for log in logs:
            results.append(decode_liquidate_log(log))
            if limit is not None and len(results) >= limit:
                if progress is not None:
                    progress(
                        {
                            "from_block": from_block,
                            "to_block": latest,
                            "current_block": end,
                            "chunks_scanned": chunks_scanned,
                            "total_chunks": total_chunks,
                            "events_found": len(results),
                        }
                    )
                return results
        if (
            progress is not None
            and progress_every > 0
            and chunks_scanned % progress_every == 0
        ):
            progress(
                {
                    "from_block": from_block,
                    "to_block": latest,
                    "current_block": end,
                    "chunks_scanned": chunks_scanned,
                    "total_chunks": total_chunks,
                    "events_found": len(results),
                }
            )
        start = end + 1

    if progress is not None:
        progress(
            {
                "from_block": from_block,
                "to_block": latest,
                "current_block": latest,
                "chunks_scanned": chunks_scanned,
                "total_chunks": total_chunks,
                "events_found": len(results),
            }
        )
    return results


def enrich_liquidations_with_market_metadata(
    events: list[dict[str, Any]],
    *,
    chain_id: int,
    client: MorphoApiClient | None = None,
    batch_size: int = 100,
) -> list[dict[str, Any]]:
    if not events:
        return []

    api = client or MorphoApiClient()
    market_ids = sorted({str(event.get("market_id")) for event in events if event.get("market_id")})
    metadata: dict[str, dict[str, Any]] = {}
    for start in range(0, len(market_ids), batch_size):
        batch = market_ids[start : start + batch_size]
        for market in fetch_markets_by_ids(api, chain_id=chain_id, market_ids=batch):
            market_id = str(market.get("marketId") or "").lower()
            if market_id:
                metadata[market_id] = market

    enriched = []
    for event in events:
        market = metadata.get(str(event.get("market_id") or "").lower())
        enriched_event = dict(event)
        if market is not None:
            enriched_event["loan"] = market.get("loanAsset") or {}
            enriched_event["collateral_asset"] = market.get("collateralAsset") or {}
            enriched_event["lltv"] = market.get("lltv")
            enriched_event["oracle"] = (market.get("oracle") or {}).get("address")
            enriched_event["market_warnings"] = list(market.get("warnings") or [])
        enriched.append(enriched_event)
    return enriched


def filter_liquidations_by_market_metadata(
    events: list[dict[str, Any]],
    *,
    collateral_symbols: tuple[str, ...] = (),
    loan_symbols: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    results = []
    collateral_needles = tuple(symbol.lower() for symbol in collateral_symbols)
    loan_needles = tuple(symbol.lower() for symbol in loan_symbols)
    for event in events:
        collateral_symbol = str((event.get("collateral_asset") or {}).get("symbol") or "").lower()
        loan_symbol = str((event.get("loan") or {}).get("symbol") or "").lower()
        if collateral_needles and not any(
            needle in collateral_symbol for needle in collateral_needles
        ):
            continue
        if loan_needles and not any(needle in loan_symbol for needle in loan_needles):
            continue
        results.append(event)
    return results


def decode_liquidate_log(log: dict[str, Any]) -> dict[str, Any]:
    topics = log.get("topics") or []
    if len(topics) < 4:
        raise RpcError("Liquidate log missing indexed topics")

    values = decode_uint256_words(str(log.get("data") or "0x"), expected_words=5)
    block_number = hex_to_int(str(log.get("blockNumber") or "0x0"))
    return {
        "block_number": block_number,
        "fork_block": max(block_number - 1, 0),
        "transaction_hash": log.get("transactionHash"),
        "log_index": hex_to_int(str(log.get("logIndex") or "0x0")),
        "market_id": topics[1],
        "caller": topic_to_address(str(topics[2])),
        "borrower": topic_to_address(str(topics[3])),
        "repaid_assets": str(values[0]),
        "repaid_shares": str(values[1]),
        "seized_assets": str(values[2]),
        "bad_debt_assets": str(values[3]),
        "bad_debt_shares": str(values[4]),
    }


def decode_uint256_words(data: str, *, expected_words: int) -> list[int]:
    if not data.startswith("0x"):
        raise RpcError("Log data is not hex encoded")
    payload = data[2:]
    if len(payload) != expected_words * 64:
        raise RpcError("Log data has unexpected length")
    return [int(payload[index : index + 64], 16) for index in range(0, len(payload), 64)]


def normalize_topic(topic: str) -> str:
    value = topic.strip()
    if value.startswith("0x"):
        value = value[2:]
    if len(value) != 64 or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise RpcError("Invalid bytes32 topic")
    return "0x" + value.lower()


def encode_address_topic(address: str) -> str:
    return "0x" + normalize_address(address)[2:].lower().rjust(64, "0")


def topic_to_address(topic: str) -> str:
    value = normalize_topic(topic)
    return "0x" + value[-40:]
