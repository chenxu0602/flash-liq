from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import Any

from flash_liq.morpho_api import MorphoApiError
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
        parser.error("missing command")
    except MorphoApiError as exc:
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
    scan.add_argument("--chain-id", type=int, default=1, help="EVM chain id. Defaults to mainnet.")
    scan.add_argument(
        "--max-health-factor",
        type=float,
        default=1.0,
        help="Return accounts with healthFactor <= this value.",
    )
    scan.add_argument(
        "--page-size",
        type=int,
        default=100,
        choices=range(1, 1001),
        metavar="[1-1000]",
        help="GraphQL page size.",
    )
    scan.add_argument(
        "--limit",
        type=int,
        help="Maximum number of returned positions after filters.",
    )
    scan.add_argument(
        "--market-id",
        action="append",
        default=[],
        help="Restrict scan to a Morpho market id. Can be repeated.",
    )
    scan.add_argument(
        "--user",
        action="append",
        default=[],
        help="Restrict scan to a borrower address. Can be repeated.",
    )
    scan.add_argument(
        "--collateral-address",
        action="append",
        default=[],
        help="Restrict scan to a collateral token address. Can be repeated.",
    )
    scan.add_argument(
        "--collateral-symbol",
        action="append",
        default=[],
        help="Restrict scan to collateral symbols containing this text. Can be repeated.",
    )
    scan.add_argument(
        "--collateral-tag",
        action="append",
        default=[],
        help="Restrict scan to Morpho asset tags such as erc4626 or vault-v1.",
    )
    scan.add_argument(
        "--complex-only",
        action="store_true",
        help=(
            "Only show positions whose collateral looks like a derivative, "
            "vault, LP, or warning-heavy asset."
        ),
    )
    scan.add_argument(
        "--listed-only",
        action="store_true",
        help="Only include listed Morpho markets.",
    )
    scan.add_argument(
        "--output",
        choices=("table", "json", "csv"),
        default="table",
        help="Output format.",
    )
    scan.add_argument(
        "--short",
        action="store_true",
        help="Truncate long table fields. JSON and CSV always keep full values.",
    )
    return parser


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

    write_table(rows, short=short)


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


def write_table(rows: list[dict[str, str]], *, short: bool) -> None:
    if not rows:
        print("No positions matched.")
        return

    widths = {column: table_width(column, rows, short=short) for column in POSITION_COLUMNS}

    print("  ".join(column.ljust(widths[column]) for column in POSITION_COLUMNS))
    print("  ".join("-" * widths[column] for column in POSITION_COLUMNS))
    for row in rows:
        print(
            "  ".join(
                format_cell(row[column], column, widths[column], short=short).ljust(
                    widths[column]
                )
                for column in POSITION_COLUMNS
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
