from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fetch_watchlist_market_data import fetch_tpex_chip, fetch_twse_chip


PROJECT_ROOT = Path(__file__).resolve().parent
LAB_DIR = PROJECT_ROOT / "project_data" / "fundamental_event_lab"
EVENTS_PATH = LAB_DIR / "fundamental_events_2026_h1.csv"
OUTPUT_PATH = LAB_DIR / "event_historical_chips.csv"
SUMMARY_PATH = LAB_DIR / "event_historical_chips_summary.json"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def ad_date_text(value: str) -> str:
    return value.replace("-", "")


def previous_date_text(value: str, days: int) -> str:
    parsed = date.fromisoformat(value)
    return (parsed - timedelta(days=days)).strftime("%Y%m%d")


def fetch_chip_by_date(ad_date: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    status: dict[str, Any] = {"date": ad_date}
    rows: list[dict[str, Any]] = []
    try:
        twse_rows, twse_status = fetch_twse_chip(ad_date)
        status["twse"] = twse_status
        rows.extend(twse_rows)
    except Exception as exc:  # noqa: BLE001 - keep historical batch moving.
        status["twse"] = {"ok": False, "error": str(exc)}
    try:
        tpex_rows, tpex_status = fetch_tpex_chip(ad_date)
        status["tpex"] = tpex_status
        rows.extend(tpex_rows)
    except Exception as exc:  # noqa: BLE001 - keep historical batch moving.
        status["tpex"] = {"ok": False, "error": str(exc)}
    status["rows"] = len(rows)
    return rows, status


def find_latest_known_chip(event_date: str, stock_id: str, cache: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for offset in range(0, 8):
        candidate_date = previous_date_text(event_date, offset)
        if candidate_date not in cache:
            cache[candidate_date] = fetch_chip_by_date(candidate_date)
        rows, status = cache[candidate_date]
        attempts.append(status)
        for row in rows:
            if str(row.get("stock_id")) == stock_id:
                return row, {"used_date": candidate_date, "offset_days": offset, "attempts": attempts}
    return None, {"used_date": "", "offset_days": None, "attempts": attempts}


def main() -> int:
    events = read_csv(EVENTS_PATH)
    cache: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = {}
    output_rows: list[dict[str, Any]] = []
    misses: list[dict[str, Any]] = []

    for event in events:
        event_id = event["event_id"]
        stock_id = event["stock_id"]
        event_date = event["announcement_date"]
        chip, lookup = find_latest_known_chip(event_date, stock_id, cache)
        if chip is None:
            misses.append(
                {
                    "event_id": event_id,
                    "stock_id": stock_id,
                    "announcement_date": event_date,
                    "lookup": lookup,
                }
            )
            continue
        output_rows.append(
            {
                "event_id": event_id,
                "stock_id": stock_id,
                "company_name": event.get("company_name") or chip.get("company_name"),
                "announcement_date": event_date,
                "chip_date": chip.get("chip_date"),
                "chip_offset_days": lookup["offset_days"],
                "market": chip.get("market"),
                "foreign_net_buy_shares": chip.get("foreign_net_buy_shares"),
                "investment_trust_net_buy_shares": chip.get("investment_trust_net_buy_shares"),
                "dealer_net_buy_shares": chip.get("dealer_net_buy_shares"),
                "institutional_total_net_buy_shares": chip.get("institutional_total_net_buy_shares"),
            }
        )

    fieldnames = [
        "event_id",
        "stock_id",
        "company_name",
        "announcement_date",
        "chip_date",
        "chip_offset_days",
        "market",
        "foreign_net_buy_shares",
        "investment_trust_net_buy_shares",
        "dealer_net_buy_shares",
        "institutional_total_net_buy_shares",
    ]
    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    summary = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "events": len(events),
        "rows": len(output_rows),
        "misses": len(misses),
        "unique_chip_dates_requested": len(cache),
        "output_csv": str(OUTPUT_PATH),
        "miss_details": misses,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
