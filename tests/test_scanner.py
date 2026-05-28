from __future__ import annotations

import unittest

from flash_liq.scanner import ScanFilters, matches_position_filters, normalize_position


class ScannerTests(unittest.TestCase):
    def test_normalize_flags_complex_erc4626_collateral(self) -> None:
        position = normalize_position(
            {
                "healthFactor": 0.98,
                "priceVariationToLiquidationPrice": -0.01,
                "user": {"address": "0x0000000000000000000000000000000000000001"},
                "state": {
                    "borrowShares": "1",
                    "borrowAssets": "100",
                    "borrowAssetsUsd": 100.0,
                    "collateral": "200",
                    "collateralUsd": 110.0,
                    "supplyShares": "0",
                },
                "market": {
                    "marketId": "0xmarket",
                    "lltv": "860000000000000000",
                    "irmAddress": "0xirm",
                    "loanAsset": {"address": "0xloan", "symbol": "USDC", "decimals": 6},
                    "collateralAsset": {
                        "address": "0xcollateral",
                        "symbol": "csUSDL",
                        "decimals": 18,
                        "tags": ["erc4626", "vault-v1"],
                        "isListed": True,
                    },
                    "oracle": {"address": "0xoracle"},
                    "warnings": [{"level": "YELLOW", "type": "not_whitelisted"}],
                    "preLiquidations": {
                        "items": [
                            {
                                "address": "0xpreliq",
                                "preLltv": "800000000000000000",
                                "preLCF1": "900000000000000000",
                                "preLCF2": "950000000000000000",
                                "preLIF1": "1010000000000000000",
                                "preLIF2": "1020000000000000000",
                                "preLiquidationOracle": "0xpreoracle",
                            }
                        ]
                    },
                },
            },
            1,
        )

        self.assertTrue(position["complex_collateral"])
        self.assertEqual(
            position["complex_reasons"],
            ["tags:erc4626,vault-v1", "warnings:not_whitelisted"],
        )
        self.assertEqual(position["pre_liquidations"][0]["address"], "0xpreliq")

    def test_filter_matches_symbol_and_complex_only(self) -> None:
        position = {
            "complex_collateral": True,
            "collateral_asset": {
                "address": "0xabc",
                "symbol": "PT-csUSDL-31JUL2025",
                "tags": [],
            },
        }

        self.assertTrue(
            matches_position_filters(
                position,
                ScanFilters(
                    chain_id=1,
                    max_health_factor=1.2,
                    collateral_symbols=("PT-",),
                    complex_only=True,
                ),
            )
        )

    def test_filter_rejects_simple_collateral_when_complex_only(self) -> None:
        position = {
            "complex_collateral": False,
            "collateral_asset": {
                "address": "0xabc",
                "symbol": "WETH",
                "tags": [],
            },
        }

        self.assertFalse(
            matches_position_filters(
                position,
                ScanFilters(chain_id=1, max_health_factor=1.0, complex_only=True),
            )
        )


if __name__ == "__main__":
    unittest.main()
