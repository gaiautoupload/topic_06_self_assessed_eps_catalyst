from __future__ import annotations

import csv
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
LAB_DIR = PROJECT_ROOT / "project_data" / "fundamental_event_lab"
EVENTS_PATH = LAB_DIR / "fundamental_events_2026_h1.csv"
PRICE_DIR = LAB_DIR / "prices"
SUMMARY_PATH = LAB_DIR / "event_price_history_summary.json"

MONTH_STARTS = ["20260101", "20260201", "20260301", "20260401", "20260501", "20260601"]


def read_events() -> list[dict[str, str]]:
    with EVENTS_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def parse_number(value: Any) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if text in {"", "--", "-", "X"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def roc_slash_date_to_iso(value: str) -> str:
    year_text, month, day = value.split("/")
    return f"{int(year_text) + 1911:04d}-{int(month):02d}-{int(day):02d}"


def fetch_twse_stock_month(stock_id: str, month_start: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={month_start}&stockNo={stock_id}&response=json"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8-sig"))
    rows = []
    for row in payload.get("data", []):
        rows.append(
            {
                "trade_date": roc_slash_date_to_iso(row[0]),
                "stock_id": stock_id,
                "open": parse_number(row[3]),
                "high": parse_number(row[4]),
                "low": parse_number(row[5]),
                "close": parse_number(row[6]),
                "volume": parse_number(row[1]),
                "turnover": parse_number(row[2]),
                "trades": parse_number(row[8]),
                "market": "listed",
            }
        )
    return rows, {"ok": payload.get("stat") == "OK", "rows": len(rows), "url": url}


def write_price_csv(stock_id: str, rows: list[dict[str, Any]]) -> None:
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    path = PRICE_DIR / f"{stock_id}.csv"
    fieldnames = ["trade_date", "stock_id", "open", "high", "low", "close", "volume", "turnover", "trades", "market"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: row["trade_date"]))


def main() -> int:
    events = read_events()
    stock_ids = sorted({event["stock_id"] for event in events})
    stock_status: dict[str, Any] = {}

    for stock_id in stock_ids:
        all_rows: list[dict[str, Any]] = []
        month_status = []
        for month_start in MONTH_STARTS:
            try:
                rows, status = fetch_twse_stock_month(stock_id, month_start)
                all_rows.extend(rows)
                month_status.append(status)
            except Exception as exc:  # noqa: BLE001 - keep batch moving.
                month_status.append({"ok": False, "month_start": month_start, "error": str(exc)})
        unique_rows = {row["trade_date"]: row for row in all_rows}
        write_price_csv(stock_id, list(unique_rows.values()))
        stock_status[stock_id] = {
            "rows": len(unique_rows),
            "first_trade_date": min(unique_rows) if unique_rows else "",
            "last_trade_date": max(unique_rows) if unique_rows else "",
            "months": month_status,
        }

    summary = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "stocks": len(stock_ids),
        "price_dir": str(PRICE_DIR),
        "stock_status": stock_status,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
