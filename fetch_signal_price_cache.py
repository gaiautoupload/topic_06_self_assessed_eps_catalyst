from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from simple_monthly_revenue_backtest import fetch_price_month, write_csv


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "project_data" / "simple_monthly_revenue"
REVENUE_CSV = DATA_DIR / "monthly_revenue_2026_to_date.csv"
PRICE_DIR = DATA_DIR / "prices"
SUMMARY_JSON = DATA_DIR / "price_cache_summary.json"
MONTHS = ["202601", "202602", "202603", "202604", "202605", "202606"]
REQUIRED_LAST_DATE = "2026-06-18"


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def existing_is_complete(path: Path) -> bool:
    rows = load_csv(path)
    if not rows:
        return False
    return rows[-1].get("trade_date", "") >= REQUIRED_LAST_DATE


def main() -> int:
    rows = load_csv(REVENUE_CSV)
    stocks: dict[str, str] = {}
    for row in rows:
        stocks[row["stock_id"]] = row["market"]

    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    fetched = 0
    skipped = 0
    failures: list[dict[str, Any]] = []

    for idx, (stock_id, market) in enumerate(sorted(stocks.items()), start=1):
        path = PRICE_DIR / f"{stock_id}.csv"
        if existing_is_complete(path):
            skipped += 1
            continue
        all_rows: list[dict[str, Any]] = []
        month_errors = []
        for month in MONTHS:
            try:
                all_rows.extend(fetch_price_month(stock_id, market, month))
            except Exception as exc:  # noqa: BLE001 - keep the cache fill resumable.
                month_errors.append({"month": month, "error": str(exc)})
        by_date = {row["trade_date"]: row for row in all_rows}
        ordered = [by_date[key] for key in sorted(by_date)]
        write_csv(
            path,
            ordered,
            ["trade_date", "stock_id", "open", "high", "low", "close", "volume", "turnover", "trades", "market"],
        )
        fetched += 1
        if month_errors:
            failures.append({"stock_id": stock_id, "market": market, "errors": month_errors, "rows": len(ordered)})
        if idx % 100 == 0:
            print(json.dumps({"progress": idx, "stocks": len(stocks), "fetched": fetched, "skipped": skipped}, ensure_ascii=False))

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stocks": len(stocks),
        "fetched": fetched,
        "skipped_complete": skipped,
        "failures": failures,
        "price_dir": str(PRICE_DIR),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
