# flash-liq

`flash-liq` is a liquidation research workspace. The current focus is Morpho Blue:
find accounts that are liquidatable or close to liquidation, prioritize accounts with complex
collateral, and replay candidates on a local mainnet fork before building any execution bot.

The repo intentionally starts with discovery and simulation. It is not yet a production
liquidator.

## What Exists

- Python scanner for Morpho Blue borrower accounts.
- Heuristics for complex collateral such as ERC-4626 vault shares, Pendle PT/YT-style tokens,
  LP-like assets, unlisted collateral, and warning-heavy markets.
- JSON/CSV output for piping scan results into later automation.
- Foundry fork probe that tests whether Morpho reaches the liquidation callback for a specific
  market/account pair.
- A local copy of `morpho-blue-liquidation-bot` can be used as reference material, but it is not
  part of this repo's implementation or version-controlled scope.

## Setup

Install/use the Python package through `uv`:

```bash
uv run flash-liq --help
```

For fork simulation, put a mainnet RPC URL in `.env`:

```bash
MAINNET_FORKING_URL=https://...
```

Do not commit `.env`. Foundry reads this value through the `mainnet` RPC alias in
`foundry.toml`.

## Scan Morpho Accounts

Find currently liquidatable mainnet positions with complex collateral:

```bash
uv run flash-liq scan-morpho --chain-id 1 --max-health-factor 1 --complex-only --limit 20
```

Find near-liquidation positions:

```bash
uv run flash-liq scan-morpho --chain-id 1 --max-health-factor 1.05 --complex-only --limit 50
```

Focus on a collateral family:

```bash
uv run flash-liq scan-morpho --chain-id 1 --collateral-symbol PT- --max-health-factor 1.2 --limit 20
```

Export candidates for tooling:

```bash
uv run flash-liq scan-morpho --chain-id 1 --max-health-factor 1.05 --complex-only --output json
uv run flash-liq scan-morpho --chain-id 1 --max-health-factor 1.05 --complex-only --output csv
```

Table output keeps `user` and `market_id` untruncated so they can be copied into the fork probe.
Use `--short` for a compact terminal view.

Useful filters:

- `--market-id 0x...`: restrict to one or more Morpho markets.
- `--user 0x...`: restrict to one or more borrowers.
- `--collateral-address 0x...`: restrict to one or more collateral assets.
- `--collateral-tag erc4626`: match Morpho asset tags.
- `--listed-only`: ignore unlisted markets.

Scanner output includes:

- borrower and market id;
- health factor and borrow/collateral values from the Morpho API;
- loan and collateral token metadata;
- market warnings;
- `complex_reasons`, explaining why the collateral was flagged;
- `pre_liquidations`, when the API exposes market-level pre-liquidation contracts.

`pre_liquidations` are market-level configs only. They do not prove that a borrower has authorized
that pre-liquidation contract.

## Probe A Candidate On A Fork

Pick a `market_id` and `user` from scanner output:

```bash
set -a; source .env; set +a
export MORPHO_MARKET_ID=0x...
export MORPHO_BORROWER=0x...
forge test --match-path test/MorphoLiquidationProbe.t.sol -vv
```

The probe calls Morpho `liquidate` with callback data.

- If execution reaches `onMorphoLiquidate(uint256,bytes)`, the test passes. That means Morpho
  accepted the position as liquidatable and computed repayment before any external funding or
  swap route was needed.
- If execution reverts before the callback, inspect the trace with `-vvvv`. Common causes are a
  stale API candidate, a bad market/user pair, invalid seized/repaid sizing, oracle failure, or
  collateral transfer behavior.

`LiquidationDidNotReachCallback(..., 0x)` means Morpho reverted before callback and did not return
a Solidity error selector. Run the same command with `-vvvv`; the trace usually shows whether the
failure happened in interest accrual, oracle pricing, collateral transfer, or another external
call.

The default probe uses `MORPHO_REPAID_SHARES=1` to avoid full-position rounding and stale-state
underflow edges. You can override sizing:

```bash
export MORPHO_SEIZED_ASSETS=123
export MORPHO_REPAID_SHARES=0
```

## Why This Shape

The official `morpho-blue-liquidation-bot` separates discovery from execution:

- `data-providers` fetch markets and positions;
- the client handles liquidation construction, collateral conversion, and profitability checks;
- pre-liquidation support requires indexed contracts and borrower authorizations, which the
  official repo handles with HyperIndex.

This repo mirrors that separation. The first implementation uses Morpho's public GraphQL API
because it has the lowest setup cost and gives a useful candidate queue. Fork probes then test
whether candidates still work against current chain state.

## Known Limitations

- The scanner depends on Morpho API health factors, which can lag or differ from fork state.
- Standard API scanning does not prove pre-liquidation authorization.
- The fork probe is protocol-level. It does not yet simulate funding loan tokens, converting
  seized collateral, gas cost, slippage, or MEV execution.
- Complex collateral often fails before callback because an oracle, wrapper, vault, or token
  transfer path reverts. That is useful signal, not necessarily a scanner bug.

## Development Checks

```bash
uv run python -m unittest discover -s tests
forge build
```

For a deeper fork failure:

```bash
forge test --match-path test/MorphoLiquidationProbe.t.sol -vvvv
```
