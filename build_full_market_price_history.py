from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from simple_monthly_revenue_backtest import fetch_price_month, write_csv, yyyymm_range


PROJECT_DIR = Path(__file__).resolve().parent
DATASET_DIR = Path(r"D:\dataset")
COMPANY_MASTER_CSV = DATASET_DIR / "processed" / "company_master.csv"
OUT_DIR = PROJECT_DIR / "project_data" / "full_market_prices"
PRICE_DIR = OUT_DIR / "prices"
SUMMARY_JSON = OUT_DIR / "full_market_price_history_summary.json"
START = "2026-01-01"
END = "2026-06-18"


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def market_for(row: dict[str, str]) -> str:
    market = str(row.get("market", "")).lower()
    if "上" in market or market == "twse":
        return "listed"
    if "櫃" in market or market == "tpex":
        return "otc"
    return "listed"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    company_rows = load_csv(COMPANY_MASTER_CSV)
    months = yyyymm_range(START, END)
    fetched = 0
    skipped = 0
    failures: list[dict[str, Any]] = []

    for idx, company in enumerate(company_rows, start=1):
        stock_id = company.get("stock_id", "")
        if not stock_id:
            continue
        market = market_for(company)
        path = PRICE_DIR / f"{stock_id}.csv"
        if path.exists():
            skipped += 1
            continue

        all_rows: list[dict[str, Any]] = []
        month_errors = []
        for yyyymm in months:
            try:
                all_rows.extend(fetch_price_month(stock_id, market, yyyymm))
            except Exception as exc:  # noqa: BLE001
                month_errors.append({"yyyymm": yyyymm, "error": str(exc)})
        by_date = {row["trade_date"]: row for row in all_rows}
        ordered = [by_date[key] for key in sorted(by_date)]
        write_csv(
            path,
            ordered,
            ["trade_date", "stock_id", "open", "high", "low", "close", "volume", "turnover", "trades", "market"],
        )
        fetched += 1
        if month_errors:
            failures.append({"stock_id": stock_id, "market": market, "rows": len(ordered), "errors": month_errors})
        if idx % 100 == 0:
            print(json.dumps({"progress": idx, "companies": len(company_rows), "fetched": fetched, "skipped": skipped}, ensure_ascii=False))

    summary = {
        "generated_at": date.today().isoformat(),
        "companies": len(company_rows),
        "months": months,
        "fetched": fetched,
        "skipped_existing": skipped,
        "failures": failures,
        "price_dir": str(PRICE_DIR),
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
