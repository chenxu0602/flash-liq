from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any

from flash_liq.curve_sdola import replay_as_dict, replay_env_lines
from flash_liq.liquidation_history import (
    enrich_liquidations_with_market_metadata,
    filter_liquidations_by_market_metadata,
    find_morpho_liquidations,
)
from flash_liq.morpho_api import MorphoApiError
from flash_liq.morpho_rpc import MORPHO_BLUE, RpcError, check_morpho_authorization
from flash_liq.profit import rank_positions_by_estimated_profit
from flash_liq.scanner import ScanFilters, scan_morpho_positions


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "scan-morpho":
            positions = scan_morpho_positions(
                ScanFilters(
                    chain_id=args.chain_id,
                    max_health_factor=args.max_health_factor,
                    page_size=args.page_size,
                    max_positions=args.limit,
                    market_ids=tuple(args.market_id),
                    users=tuple(args.user),
                    collateral_addresses=tuple(args.collateral_address),
                    collateral_symbols=tuple(args.collateral_symbol),
                    collateral_tags=tuple(args.collateral_tag),
                    complex_only=args.complex_only,
                    listed_only=args.listed_only,
                )
            )
            write_positions(positions, args.output, short=args.short)
            return
        if args.command == "rank-morpho":
            positions = scan_morpho_positions(
                ScanFilters(
                    chain_id=args.chain_id,
                    max_health_factor=args.max_health_factor,
                    page_size=args.page_size,
                    max_positions=args.scan_limit,
                    market_ids=tuple(args.market_id),
                    users=tuple(args.user),
                    collateral_addresses=tuple(args.collateral_address),
                    collateral_symbols=tuple(args.collateral_symbol),
                    collateral_tags=tuple(args.collateral_tag),
                    complex_only=args.complex_only,
                    listed_only=args.listed_only,
                )
            )
            ranked = rank_positions_by_estimated_profit(
                positions,
                include_unpriced=args.include_unpriced,
                min_gross_profit_usd=args.min_gross_profit_usd,
            )
            if args.limit is not None:
                ranked = ranked[: args.limit]
            write_ranked_positions(ranked, args.output, short=args.short)
            return
        if args.command == "check-morpho-auth":
            rpc_url = args.rpc_url or os.environ.get("MAINNET_FORKING_URL")
            if not rpc_url:
                raise SystemExit("MAINNET_FORKING_URL is not set; pass --rpc-url or source .env")
            check = check_morpho_authorization(
                rpc_url=rpc_url,
                morpho_address=args.morpho_address,
                authorizer=args.authorizer,
                authorizee=args.authorizee,
            )
            write_authorization_check(check.__dict__, args.output)
            return
        if args.command == "find-morpho-liquidations":
            rpc_url = args.rpc_url or os.environ.get("MAINNET_FORKING_URL")
            if not rpc_url:
                raise SystemExit("MAINNET_FORKING_URL is not set; pass --rpc-url or source .env")
            events = find_morpho_liquidations(
                rpc_url=rpc_url,
                from_block=args.from_block,
                to_block=args.to_block,
                chunk_size=args.chunk_size,
                limit=None
                if args.collateral_symbol or args.loan_symbol or args.enrich_markets
                else args.limit,
                market_id=args.market_id,
                borrower=args.borrower,
                morpho_address=args.morpho_address,
                progress=write_liquidation_scan_progress if args.progress else None,
                progress_every=args.progress_every,
            )
            if args.collateral_symbol or args.loan_symbol or args.enrich_markets:
                events = enrich_liquidations_with_market_metadata(
                    events,
                    chain_id=args.chain_id,
                )
            if args.collateral_symbol or args.loan_symbol:
                events = filter_liquidations_by_market_metadata(
                    events,
                    collateral_symbols=tuple(args.collateral_symbol),
                    loan_symbols=tuple(args.loan_symbol),
                )
            if args.limit is not None:
                events = events[: args.limit]
            write_liquidation_events(events, args.output, short=args.short)
            return
        if args.command == "curve-sdola-replay-env":
            replay = replay_as_dict()
            if args.output == "json":
                print(json.dumps(replay, indent=2, sort_keys=True))
                return
            for line in replay_env_lines():
                print(f"export {line}" if args.export else line)
            if args.include_borrowers:
                for borrower in replay["borrowers"]:
                    print(f"CURVE_SDOLA_BORROWER={borrower}")
            return
        parser.error("missing command")
    except MorphoApiError as exc:
        raise SystemExit(str(exc)) from exc
    except RpcError as exc:
        raise SystemExit(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flash-liq",
        description="Liquidation research tools.",
    )
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser(
        "scan-morpho",
        help="Scan Morpho Blue accounts by health factor using the Morpho API.",
    )
    add_scan_arguments(scan)

    rank = subparsers.add_parser(
        "rank-morpho",
        help="Rank Morpho Blue liquidation candidates by estimated gross profit.",
    )
    add_scan_arguments(rank, ranked=True)
    rank.add_argument(
        "--min-gross-profit-usd",
        type=float,
        help="Only include priced candidates with estimated gross profit at least this amount.",
    )
    rank.add_argument(
        "--include-unpriced",
        action="store_true",
        help="Include candidates missing API USD fields after priced candidates.",
    )

    auth = subparsers.add_parser(
        "check-morpho-auth",
        help="Check Morpho isAuthorized(authorizer, authorizee) without printing RPC secrets.",
    )
    auth.add_argument("--authorizer", required=True, help="Borrower/owner address.")
    auth.add_argument("--authorizee", required=True, help="Operator or pre-liquidation address.")
    auth.add_argument(
        "--morpho-address",
        default=MORPHO_BLUE,
        help="Morpho Blue contract address.",
    )
    auth.add_argument(
        "--rpc-url",
        help="RPC URL. Defaults to MAINNET_FORKING_URL from the environment.",
    )
    auth.add_argument(
        "--output",
        choices=("table", "json"),
        default="table",
        help="Output format.",
    )

    liquidations = subparsers.add_parser(
        "find-morpho-liquidations",
        help="Find historical Morpho Blue Liquidate events for fork replay.",
    )
    liquidations.add_argument("--from-block", type=int, required=True, help="First block to scan.")
    liquidations.add_argument(
        "--to-block",
        default="latest",
        help="Last block to scan. Defaults to latest.",
    )
    liquidations.add_argument(
        "--chunk-size",
        type=int,
        default=10,
        help="eth_getLogs block range per request. Alchemy Free tier allows up to 10.",
    )
    liquidations.add_argument("--limit", type=int, help="Maximum number of events to return.")
    liquidations.add_argument("--chain-id", type=int, default=1, help="EVM chain id for metadata.")
    liquidations.add_argument("--market-id", help="Restrict to a Morpho market id.")
    liquidations.add_argument("--borrower", help="Restrict to a borrower address.")
    liquidations.add_argument(
        "--collateral-symbol",
        action="append",
        default=[],
        help="Enrich markets and restrict to collateral symbols containing this text.",
    )
    liquidations.add_argument(
        "--loan-symbol",
        action="append",
        default=[],
        help="Enrich markets and restrict to loan symbols containing this text.",
    )
    liquidations.add_argument(
        "--enrich-markets",
        action="store_true",
        help="Add loan/collateral symbols, oracle, LLTV, and warnings from the Morpho API.",
    )
    liquidations.add_argument(
        "--morpho-address",
        default=MORPHO_BLUE,
        help="Morpho Blue contract address.",
    )
    liquidations.add_argument(
        "--rpc-url",
        help="RPC URL. Defaults to MAINNET_FORKING_URL from the environment.",
    )
    liquidations.add_argument(
        "--output",
        choices=("table", "json", "csv"),
        default="table",
        help="Output format.",
    )
    liquidations.add_argument(
        "--short",
        action="store_true",
        help="Truncate long table fields. JSON and CSV always keep full values.",
    )
    liquidations.add_argument(
        "--progress",
        action="store_true",
        help="Print eth_getLogs scan progress to stderr.",
    )
    liquidations.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="Print progress every N log chunks when --progress is set.",
    )

    sdola = subparsers.add_parser(
        "curve-sdola-replay-env",
        help="Print constants for the historical Curve sDOLA LlamaLend replay.",
    )
    sdola.add_argument(
        "--output",
        choices=("env", "json"),
        default="env",
        help="Output format.",
    )
    sdola.add_argument(
        "--export",
        action="store_true",
        help="Prefix env output with export for shell evaluation.",
    )
    sdola.add_argument(
        "--include-borrowers",
        action="store_true",
        help="Also print each affected borrower address in env output.",
    )
    return parser


def add_scan_arguments(parser: argparse.ArgumentParser, *, ranked: bool = False) -> None:
    parser.add_argument(
        "--chain-id",
        type=int,
        default=1,
        help="EVM chain id. Defaults to mainnet.",
    )
    parser.add_argument(
        "--max-health-factor",
        type=float,
        default=1.0,
        help="Return accounts with healthFactor <= this value.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        choices=range(1, 1001),
        metavar="[1-1000]",
        help="GraphQL page size.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help=(
            "Maximum number of ranked rows to output."
            if ranked
            else "Maximum number of returned positions after filters."
        ),
    )
    if ranked:
        parser.add_argument(
            "--scan-limit",
            type=int,
            help="Maximum number of scanner positions to inspect before ranking.",
        )
    parser.add_argument(
        "--market-id",
        action="append",
        default=[],
        help="Restrict scan to a Morpho market id. Can be repeated.",
    )
    parser.add_argument(
        "--user",
        action="append",
        default=[],
        help="Restrict scan to a borrower address. Can be repeated.",
    )
    parser.add_argument(
        "--collateral-address",
        action="append",
        default=[],
        help="Restrict scan to a collateral token address. Can be repeated.",
    )
    parser.add_argument(
        "--collateral-symbol",
        action="append",
        default=[],
        help="Restrict scan to collateral symbols containing this text. Can be repeated.",
    )
    parser.add_argument(
        "--collateral-tag",
        action="append",
        default=[],
        help="Restrict scan to Morpho asset tags such as erc4626 or vault-v1.",
    )
    parser.add_argument(
        "--complex-only",
        action="store_true",
        help=(
            "Only show positions whose collateral looks like a derivative, "
            "vault, LP, or warning-heavy asset."
        ),
    )
    parser.add_argument(
        "--listed-only",
        action="store_true",
        help="Only include listed Morpho markets.",
    )
    parser.add_argument(
        "--output",
        choices=("table", "json", "csv"),
        default="table",
        help="Output format.",
    )
    parser.add_argument(
        "--short",
        action="store_true",
        help="Truncate long table fields. JSON and CSV always keep full values.",
    )


def write_positions(positions: list[dict[str, Any]], output: str, *, short: bool) -> None:
    if output == "json":
        print(json.dumps(positions, indent=2, sort_keys=True))
        return

    rows = [flatten_position(position) for position in positions]
    if output == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=POSITION_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        return

    write_table(rows, POSITION_COLUMNS, short=short)


def write_ranked_positions(positions: list[dict[str, Any]], output: str, *, short: bool) -> None:
    if output == "json":
        print(json.dumps(positions, indent=2, sort_keys=True))
        return

    rows = [flatten_ranked_position(position) for position in positions]
    if output == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=RANK_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        return

    write_table(rows, RANK_COLUMNS, short=short)


def write_authorization_check(check: dict[str, Any], output: str) -> None:
    if output == "json":
        print(json.dumps(check, indent=2, sort_keys=True))
        return

    print("authorizer authorizee authorized")
    print("---------- ---------- ----------")
    print(f"{check['authorizer']} {check['authorizee']} {str(check['authorized']).lower()}")


def write_liquidation_events(
    events: list[dict[str, Any]],
    output: str,
    *,
    short: bool,
) -> None:
    if output == "json":
        print(json.dumps(events, indent=2, sort_keys=True))
        return

    rows = [flatten_liquidation_event(event) for event in events]
    if output == "csv":
        writer = csv.DictWriter(sys.stdout, fieldnames=LIQUIDATION_EVENT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        return

    write_table(rows, LIQUIDATION_EVENT_COLUMNS, short=short)


def write_liquidation_scan_progress(progress: dict[str, int]) -> None:
    print(
        "scan "
        f"{progress['chunks_scanned']}/{progress['total_chunks']} chunks "
        f"current_block={progress['current_block']} "
        f"events_found={progress['events_found']}",
        file=sys.stderr,
        flush=True,
    )


POSITION_COLUMNS = [
    "health_factor",
    "borrow_usd",
    "collateral_usd",
    "collateral_symbol",
    "loan_symbol",
    "preliq",
    "user",
    "market_id",
    "complex_reasons",
    "warnings",
]

RANK_COLUMNS = [
    "gross_profit_usd",
    "max_repay_usd",
    "seized_collateral_usd",
    "lif",
    "health_factor",
    "borrow_usd",
    "collateral_usd",
    "value_limited_by",
    "collateral_symbol",
    "loan_symbol",
    "preliq",
    "user",
    "market_id",
    "warnings",
    "unpriced_reason",
]

LIQUIDATION_EVENT_COLUMNS = [
    "block_number",
    "fork_block",
    "transaction_hash",
    "loan_symbol",
    "collateral_symbol",
    "market_id",
    "borrower",
    "caller",
    "repaid_assets",
    "repaid_shares",
    "seized_assets",
    "bad_debt_assets",
    "warnings",
    "probe_env",
]


def flatten_position(position: dict[str, Any]) -> dict[str, str]:
    warnings = ",".join(
        str(warning.get("type"))
        for warning in position["market_warnings"]
        if warning.get("type") is not None
    )
    return {
        "health_factor": format_value(position.get("health_factor")),
        "borrow_usd": format_value(position.get("borrow_assets_usd")),
        "collateral_usd": format_value(position.get("collateral_usd")),
        "collateral_symbol": str(position["collateral_asset"].get("symbol") or ""),
        "loan_symbol": str(position["loan"].get("symbol") or ""),
        "preliq": str(len(position.get("pre_liquidations") or [])),
        "user": str(position.get("user") or ""),
        "market_id": str(position.get("market_id") or ""),
        "complex_reasons": ";".join(position.get("complex_reasons") or []),
        "warnings": warnings,
    }


def flatten_ranked_position(position: dict[str, Any]) -> dict[str, str]:
    estimate = position["profit_estimate"]
    warnings = ",".join(
        str(warning.get("type"))
        for warning in position["market_warnings"]
        if warning.get("type") is not None
    )
    return {
        "gross_profit_usd": format_value(estimate.get("gross_profit_usd")),
        "max_repay_usd": format_value(estimate.get("max_repay_usd")),
        "seized_collateral_usd": format_value(estimate.get("seized_collateral_usd")),
        "lif": format_value(estimate.get("liquidation_incentive_factor")),
        "health_factor": format_value(position.get("health_factor")),
        "borrow_usd": format_value(position.get("borrow_assets_usd")),
        "collateral_usd": format_value(position.get("collateral_usd")),
        "value_limited_by": str(estimate.get("value_limited_by") or ""),
        "collateral_symbol": str(position["collateral_asset"].get("symbol") or ""),
        "loan_symbol": str(position["loan"].get("symbol") or ""),
        "preliq": str(len(position.get("pre_liquidations") or [])),
        "user": str(position.get("user") or ""),
        "market_id": str(position.get("market_id") or ""),
        "warnings": warnings,
        "unpriced_reason": str(estimate.get("unpriced_reason") or ""),
    }


def flatten_liquidation_event(event: dict[str, Any]) -> dict[str, str]:
    probe_env = (
        f"MORPHO_FORK_BLOCK={event.get('fork_block')} "
        f"MORPHO_MARKET_ID={event.get('market_id')} "
        f"MORPHO_BORROWER={event.get('borrower')} "
        f"MORPHO_REPAID_SHARES={event.get('repaid_shares')}"
    )
    return {
        "block_number": str(event.get("block_number") or ""),
        "fork_block": str(event.get("fork_block") or ""),
        "transaction_hash": str(event.get("transaction_hash") or ""),
        "loan_symbol": str((event.get("loan") or {}).get("symbol") or ""),
        "collateral_symbol": str((event.get("collateral_asset") or {}).get("symbol") or ""),
        "market_id": str(event.get("market_id") or ""),
        "borrower": str(event.get("borrower") or ""),
        "caller": str(event.get("caller") or ""),
        "repaid_assets": str(event.get("repaid_assets") or ""),
        "repaid_shares": str(event.get("repaid_shares") or ""),
        "seized_assets": str(event.get("seized_assets") or ""),
        "bad_debt_assets": str(event.get("bad_debt_assets") or ""),
        "warnings": ",".join(
            str(warning.get("type"))
            for warning in event.get("market_warnings", [])
            if warning.get("type") is not None
        ),
        "probe_env": probe_env,
    }


def write_table(rows: list[dict[str, str]], columns: list[str], *, short: bool) -> None:
    if not rows:
        print("No positions matched.")
        return

    widths = {column: table_width(column, rows, short=short) for column in columns}

    print("  ".join(column.ljust(widths[column]) for column in columns))
    print("  ".join("-" * widths[column] for column in columns))
    for row in rows:
        print(
            "  ".join(
                format_cell(row[column], column, widths[column], short=short).ljust(
                    widths[column]
                )
                for column in columns
            )
        )


def table_width(column: str, rows: list[dict[str, str]], *, short: bool) -> int:
    full_width = max(len(column), *(len(row[column]) for row in rows))
    if not short:
        if column == "market_id":
            return max(full_width, 66)
        if column == "user":
            return max(full_width, 42)
        return min(full_width, 32)
    return min(full_width, 42 if column in {"user", "market_id"} else 28)


def format_cell(value: str, column: str, width: int, *, short: bool) -> str:
    if not short and column in {"user", "market_id"}:
        return value
    return trim(value, width)


def trim(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value == 0:
            return "0"
        if abs(value) >= 100:
            return f"{value:.2f}"
        if abs(value) >= 1:
            return f"{value:.4f}"
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return str(value)


if __name__ == "__main__":
    main()
