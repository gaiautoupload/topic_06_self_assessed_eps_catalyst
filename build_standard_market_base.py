from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
LAB_DIR = PROJECT_DIR / "project_data" / "fundamental_event_lab"
MKT_DIR = LAB_DIR / "watchlist_market_data"
OUT_CSV = LAB_DIR / "standard_market_base.csv"
OUT_JSON = LAB_DIR / "standard_market_base_summary.json"


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-", "--", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def main() -> None:
    snapshot = load_csv(MKT_DIR / "watchlist_market_snapshot.csv")
    quotes = {row["stock_id"]: row for row in load_csv(MKT_DIR / "watchlist_quotes.csv") if row.get("stock_id")}
    valuation = {row["stock_id"]: row for row in load_csv(MKT_DIR / "watchlist_valuation.csv") if row.get("stock_id")}
    chips = {row["stock_id"]: row for row in load_csv(MKT_DIR / "watchlist_chips.csv") if row.get("stock_id")}
    local_prepared = {row["stock_id"]: row for row in load_csv(PROJECT_DIR / "project_data" / "simple_monthly_revenue" / "prepared_signal_universe.csv") if row.get("stock_id")}

    rows: list[dict[str, Any]] = []
    for row in snapshot:
        stock_id = row.get("stock_id", "")
        prepared = local_prepared.get(stock_id, {})
        quote = quotes.get(stock_id, {})
        val = valuation.get(stock_id, {})
        chip = chips.get(stock_id, {})
        rows.append(
            {
                "stock_id": stock_id,
                "company_name": row.get("company_name") or prepared.get("company_name", ""),
                "market": row.get("market") or prepared.get("market", ""),
                "sources": row.get("sources", ""),
                "event_count": parse_float(row.get("event_count")) or 0,
                "quote_date": row.get("quote_date") or quote.get("quote_date", ""),
                "close": parse_float(row.get("close")) or parse_float(quote.get("close")),
                "change": parse_float(row.get("change")) or parse_float(quote.get("change")),
                "volume_shares": parse_float(row.get("volume_shares")) or parse_float(quote.get("volume_shares")),
                "valuation_date": row.get("valuation_date") or val.get("valuation_date", ""),
                "pe_ratio": parse_float(row.get("pe_ratio")) or parse_float(val.get("pe_ratio")),
                "pb_ratio": parse_float(row.get("pb_ratio")) or parse_float(val.get("pb_ratio")),
                "dividend_yield_pct": parse_float(row.get("dividend_yield_pct")) or parse_float(val.get("dividend_yield_pct")),
                "chip_date": row.get("chip_date") or chip.get("chip_date", ""),
                "foreign_net_buy_shares": parse_float(row.get("foreign_net_buy_shares")) or parse_float(chip.get("foreign_net_buy_shares")),
                "investment_trust_net_buy_shares": parse_float(row.get("investment_trust_net_buy_shares")) or parse_float(chip.get("investment_trust_net_buy_shares")),
                "dealer_net_buy_shares": parse_float(row.get("dealer_net_buy_shares")) or parse_float(chip.get("dealer_net_buy_shares")),
                "institutional_total_net_buy_shares": parse_float(row.get("institutional_total_net_buy_shares")) or parse_float(chip.get("institutional_total_net_buy_shares")),
                "has_local_price_file": str(row.get("has_local_price_file", "")).strip(),
                "local_price_file": row.get("local_price_file", ""),
                "buy_date": prepared.get("buy_date", ""),
                "buy_price": parse_float(prepared.get("buy_price")),
                "mom_pct": parse_float(prepared.get("mom_pct")),
                "yoy_pct": parse_float(prepared.get("yoy_pct")),
                "avg_volume_5d": parse_float(prepared.get("avg_volume_5d")),
                "previous_volume_ratio_20d": parse_float(prepared.get("previous_volume_ratio_20d")),
                "breakout_20d": prepared.get("breakout_20d", ""),
                "breakout_60d": prepared.get("breakout_60d", ""),
                "breakout_120d": prepared.get("breakout_120d", ""),
                "breakout_240d": prepared.get("breakout_240d", ""),
            }
        )

    fieldnames = list(rows[0].keys()) if rows else []
    write_csv(OUT_CSV, rows, fieldnames)
    summary = {
        "rows": len(rows),
        "stocks": len({row["stock_id"] for row in rows if row.get("stock_id")}),
        "with_quote": sum(1 for row in rows if row.get("close") is not None),
        "with_valuation": sum(1 for row in rows if row.get("pe_ratio") is not None or row.get("pb_ratio") is not None),
        "with_chip": sum(1 for row in rows if row.get("foreign_net_buy_shares") is not None),
        "output_csv": str(OUT_CSV),
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
