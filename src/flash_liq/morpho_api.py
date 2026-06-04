from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

BLUE_API_GRAPHQL_URL = "https://blue-api.morpho.org/graphql"


class MorphoApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class GraphQLPage:
    items: list[dict[str, Any]]
    count: int | None
    count_total: int | None


class MorphoApiClient:
    def __init__(self, url: str = BLUE_API_GRAPHQL_URL, timeout: float = 30.0) -> None:
        self.url = url
        self.timeout = timeout

    def request(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"query": query, "variables": variables}).encode()
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise MorphoApiError(f"Morpho API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise MorphoApiError(f"Morpho API request failed: {exc}") from exc

        errors = payload.get("errors")
        if errors:
            messages = "; ".join(str(error.get("message", error)) for error in errors)
            raise MorphoApiError(f"Morpho API GraphQL error: {messages}")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise MorphoApiError("Morpho API returned no data")
        return data


MARKET_POSITIONS_QUERY = """
query ScanMarketPositions(
  $chainId: Int!
  $first: Int!
  $skip: Int!
  $healthFactorLte: Float!
  $marketIds: [String!]
  $users: [String!]
  $marketListed: Boolean
) {
  marketPositions(
    first: $first
    skip: $skip
    where: {
      chainId_in: [$chainId]
      healthFactor_lte: $healthFactorLte
      borrowShares_gte: "1"
      marketUniqueKey_in: $marketIds
      userAddress_in: $users
      marketListed: $marketListed
    }
    orderBy: HealthFactor
    orderDirection: Asc
  ) {
    pageInfo {
      count
      countTotal
      limit
      skip
    }
    items {
      healthFactor
      priceVariationToLiquidationPrice
      user {
        address
      }
      state {
        borrowShares
        borrowAssets
        borrowAssetsUsd
        collateral
        collateralUsd
        supplyShares
      }
      market {
        marketId
        lltv
        irmAddress
        loanAsset {
          address
          symbol
          decimals
          tags
        }
        collateralAsset {
          address
          symbol
          decimals
          tags
          isListed
        }
        oracle {
          address
        }
        warnings {
          level
          type
        }
        preLiquidations(first: 20) {
          items {
            address
            preLltv
            preLCF1
            preLCF2
            preLIF1
            preLIF2
            preLiquidationOracle
          }
        }
      }
    }
  }
}
"""

MARKETS_QUERY = """
query FetchMarkets(
  $chainId: Int!
  $first: Int!
  $marketIds: [String!]
) {
  markets(
    first: $first
    where: {
      chainId_in: [$chainId]
      uniqueKey_in: $marketIds
    }
  ) {
    items {
      marketId
      lltv
      loanAsset {
        address
        symbol
        decimals
        tags
      }
      collateralAsset {
        address
        symbol
        decimals
        tags
        isListed
      }
      oracle {
        address
      }
      warnings {
        level
        type
      }
    }
  }
}
"""


def fetch_market_positions(
    client: MorphoApiClient,
    *,
    chain_id: int,
    health_factor_lte: float,
    first: int,
    skip: int,
    market_ids: list[str] | None = None,
    users: list[str] | None = None,
    market_listed: bool | None = None,
) -> GraphQLPage:
    data = client.request(
        MARKET_POSITIONS_QUERY,
        {
            "chainId": chain_id,
            "healthFactorLte": health_factor_lte,
            "first": first,
            "skip": skip,
            "marketIds": market_ids,
            "users": users,
            "marketListed": market_listed,
        },
    )
    positions = data["marketPositions"]
    page_info = positions.get("pageInfo") or {}
    return GraphQLPage(
        items=list(positions.get("items") or []),
        count=page_info.get("count"),
        count_total=page_info.get("countTotal"),
    )


def fetch_markets_by_ids(
    client: MorphoApiClient,
    *,
    chain_id: int,
    market_ids: list[str],
) -> list[dict[str, Any]]:
    if not market_ids:
        return []

    data = client.request(
        MARKETS_QUERY,
        {
            "chainId": chain_id,
            "first": len(market_ids),
            "marketIds": market_ids,
        },
    )
    return list((data.get("markets") or {}).get("items") or [])
