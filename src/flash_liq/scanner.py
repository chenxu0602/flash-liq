from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from flash_liq.morpho_api import MorphoApiClient, fetch_market_positions

COMPLEX_COLLATERAL_TAGS = {
    "erc4626",
    "vault",
    "vault-v1",
    "vault-v2",
    "lp",
    "pendle",
    "pt",
    "yt",
    "receipt",
}

COMPLEX_SYMBOL_MARKERS = (
    "PT-",
    "YT-",
    "SY-",
    "LP",
    "VLP",
    "SILO",
    "AURA",
    "BPT",
    "CURVE",
    "CVX",
    "MORPHO",
    "MW",
    "MTBILL",
    "STEAK",
    "SUSDE",
    "EUSDE",
    "WEETH",
    "EZETH",
    "RSETH",
    "WSTETH",
)

COMPLEX_WARNING_TYPES = {
    "not_whitelisted",
    "unrecognized_collateral_asset",
    "oracle_price_derivation",
    "incorrect_oracle_configuration",
}


@dataclass(frozen=True)
class ScanFilters:
    chain_id: int
    max_health_factor: float
    page_size: int = 100
    max_positions: int | None = None
    market_ids: tuple[str, ...] = ()
    users: tuple[str, ...] = ()
    collateral_addresses: tuple[str, ...] = ()
    collateral_symbols: tuple[str, ...] = ()
    collateral_tags: tuple[str, ...] = ()
    complex_only: bool = False
    listed_only: bool = False


def scan_morpho_positions(
    filters: ScanFilters,
    *,
    client: MorphoApiClient | None = None,
) -> list[dict[str, Any]]:
    api = client or MorphoApiClient()
    results: list[dict[str, Any]] = []
    skip = 0

    while True:
        page = fetch_market_positions(
            api,
            chain_id=filters.chain_id,
            health_factor_lte=filters.max_health_factor,
            first=filters.page_size,
            skip=skip,
            market_ids=list(filters.market_ids) or None,
            users=list(filters.users) or None,
            market_listed=True if filters.listed_only else None,
        )

        if not page.items:
            break

        for item in page.items:
            normalized = normalize_position(item, filters.chain_id)
            if not matches_position_filters(normalized, filters):
                continue
            results.append(normalized)

            if filters.max_positions is not None and len(results) >= filters.max_positions:
                return results

        if len(page.items) < filters.page_size:
            break
        skip += filters.page_size

    return results


def normalize_position(item: dict[str, Any], chain_id: int) -> dict[str, Any]:
    market = item.get("market") or {}
    state = item.get("state") or {}
    user = item.get("user") or {}
    collateral = market.get("collateralAsset") or {}
    loan = market.get("loanAsset") or {}
    warnings = list(market.get("warnings") or [])
    pre_liquidations = (market.get("preLiquidations") or {}).get("items") or []

    collateral_tags = tuple(str(tag).lower() for tag in collateral.get("tags") or [])
    warning_types = tuple(str(warning.get("type", "")).lower() for warning in warnings)

    complex_reasons = detect_complex_collateral(
        symbol=str(collateral.get("symbol") or ""),
        tags=collateral_tags,
        warning_types=warning_types,
    )

    return {
        "chain_id": chain_id,
        "user": user.get("address"),
        "market_id": market.get("marketId"),
        "health_factor": item.get("healthFactor"),
        "price_variation_to_liquidation": item.get("priceVariationToLiquidationPrice"),
        "borrow_shares": stringify_int(state.get("borrowShares")),
        "borrow_assets": stringify_int(state.get("borrowAssets")),
        "borrow_assets_usd": state.get("borrowAssetsUsd"),
        "collateral": stringify_int(state.get("collateral")),
        "collateral_usd": state.get("collateralUsd"),
        "supply_shares": stringify_int(state.get("supplyShares")),
        "lltv": stringify_int(market.get("lltv")),
        "oracle": (market.get("oracle") or {}).get("address"),
        "irm": market.get("irmAddress"),
        "loan": normalize_asset(loan),
        "collateral_asset": normalize_asset(collateral),
        "market_warnings": warnings,
        "pre_liquidations": [normalize_pre_liquidation(item) for item in pre_liquidations],
        "complex_collateral": bool(complex_reasons),
        "complex_reasons": complex_reasons,
    }


def matches_position_filters(position: dict[str, Any], filters: ScanFilters) -> bool:
    collateral = position["collateral_asset"]
    address = str(collateral.get("address") or "").lower()
    symbol = str(collateral.get("symbol") or "").lower()
    tags = {str(tag).lower() for tag in collateral.get("tags") or []}

    if filters.collateral_addresses:
        wanted = {item.lower() for item in filters.collateral_addresses}
        if address not in wanted:
            return False

    if filters.collateral_symbols:
        needles = tuple(item.lower() for item in filters.collateral_symbols)
        if not any(needle in symbol for needle in needles):
            return False

    if filters.collateral_tags:
        wanted_tags = {item.lower() for item in filters.collateral_tags}
        if not tags.intersection(wanted_tags):
            return False

    if filters.complex_only and not position["complex_collateral"]:
        return False

    return True


def detect_complex_collateral(
    *,
    symbol: str,
    tags: Iterable[str],
    warning_types: Iterable[str],
) -> list[str]:
    reasons: list[str] = []
    normalized_tags = {tag.lower() for tag in tags}
    tag_hits = sorted(normalized_tags.intersection(COMPLEX_COLLATERAL_TAGS))
    if tag_hits:
        reasons.append("tags:" + ",".join(tag_hits))

    symbol_upper = symbol.upper()
    symbol_hits = [marker for marker in COMPLEX_SYMBOL_MARKERS if marker in symbol_upper]
    if symbol_hits:
        reasons.append("symbol:" + ",".join(symbol_hits))

    warning_hits = sorted(
        {warning.lower() for warning in warning_types}.intersection(COMPLEX_WARNING_TYPES)
    )
    if warning_hits:
        reasons.append("warnings:" + ",".join(warning_hits))

    return reasons


def normalize_asset(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "address": asset.get("address"),
        "symbol": asset.get("symbol"),
        "decimals": asset.get("decimals"),
        "tags": list(asset.get("tags") or []),
        "is_listed": asset.get("isListed"),
    }


def normalize_pre_liquidation(item: dict[str, Any]) -> dict[str, str | None]:
    return {
        "address": item.get("address"),
        "pre_lltv": stringify_int(item.get("preLltv")),
        "pre_lcf_1": stringify_int(item.get("preLCF1")),
        "pre_lcf_2": stringify_int(item.get("preLCF2")),
        "pre_lif_1": stringify_int(item.get("preLIF1")),
        "pre_lif_2": stringify_int(item.get("preLIF2")),
        "pre_liquidation_oracle": item.get("preLiquidationOracle"),
    }


def stringify_int(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
