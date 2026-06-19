from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fetch_watchlist_market_data import fetch_tpex_chip, fetch_twse_chip


PROJECT_DIR = Path(__file__).resolve().parent
OUT_DIR = PROJECT_DIR / "project_data" / "full_market_history"
OUT_CSV = OUT_DIR / "chip_history.csv"
SUMMARY_JSON = OUT_DIR / "chip_history_summary.json"
STATE_JSON = OUT_DIR / "chip_history_state.json"
START_DATE = "2026-01-01"
END_DATE = "2026-06-18"


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


def parse_date(text: str) -> date:
    return date.fromisoformat(text)


def date_range(start: str, end: str) -> list[str]:
    cursor = parse_date(start)
    end_date = parse_date(end)
    values: list[str] = []
    while cursor <= end_date:
        if cursor.weekday() < 5:
            values.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return values


def fetch_for_date(iso_date: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ad_date = iso_date.replace("-", "")
    rows: list[dict[str, Any]] = []
    status: dict[str, Any] = {"date": ad_date, "twse": None, "tpex": None}
    try:
        twse_rows, twse_status = fetch_twse_chip(ad_date)
        rows.extend(twse_rows)
        status["twse"] = twse_status
    except Exception as exc:  # noqa: BLE001
        status["twse"] = {"ok": False, "error": str(exc)}
    try:
        tpex_rows, tpex_status = fetch_tpex_chip(ad_date)
        rows.extend(tpex_rows)
        status["tpex"] = tpex_status
    except Exception as exc:  # noqa: BLE001
        status["tpex"] = {"ok": False, "error": str(exc)}
    for row in rows:
        row["announcement_date"] = iso_date
    return rows, status


def load_state() -> dict[str, Any]:
    if not STATE_JSON.exists():
        return {"last_date": "", "rows": []}
    return json.loads(STATE_JSON.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATE_JSON.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    existing_rows = load_csv(OUT_CSV)
    seen = {(row.get("announcement_date", ""), row.get("stock_id", "")) for row in existing_rows}
    start = max(START_DATE, state.get("last_date") or START_DATE)
    dates = date_range(start, END_DATE)
    all_rows = list(existing_rows)
    failures: list[dict[str, Any]] = []
    fetched_dates = 0

    for iso_date in dates:
        rows, status = fetch_for_date(iso_date)
        if rows:
            fetched_dates += 1
            for row in rows:
                key = (row.get("announcement_date", ""), row.get("stock_id", ""))
                if key in seen:
                    continue
                seen.add(key)
                all_rows.append(row)
        else:
            failures.append({"date": iso_date, "status": status})
        state["last_date"] = iso_date
        state["rows"] = len(all_rows)
        save_state(state)

    all_rows.sort(key=lambda row: (row.get("announcement_date", ""), row.get("stock_id", "")))
    write_csv(
        OUT_CSV,
        all_rows,
        [
            "announcement_date",
            "stock_id",
            "company_name",
            "market",
            "chip_date",
            "foreign_net_buy_shares",
            "investment_trust_net_buy_shares",
            "dealer_net_buy_shares",
            "institutional_total_net_buy_shares",
        ],
    )
    summary = {
        "generated_at": date.today().isoformat(),
        "start_date": START_DATE,
        "end_date": END_DATE,
        "fetched_dates": fetched_dates,
        "rows": len(all_rows),
        "failures": failures,
        "output_csv": str(OUT_CSV),
        "note": "This is a date-batched historical chip store built from official TWSE/TPEX daily endpoints.",
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
