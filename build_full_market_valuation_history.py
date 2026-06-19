from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fetch_watchlist_market_data import fetch_json, normalize_valuation


PROJECT_DIR = Path(__file__).resolve().parent
OUT_DIR = PROJECT_DIR / "project_data" / "full_market_history"
OUT_CSV = OUT_DIR / "valuation_history.csv"
SUMMARY_JSON = OUT_DIR / "valuation_history_summary.json"
STATE_JSON = OUT_DIR / "valuation_history_state.json"
LATEST_TWSE = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
LATEST_TPEX = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"


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


def load_state() -> dict[str, Any]:
    if not STATE_JSON.exists():
        return {"snapshots": []}
    return json.loads(STATE_JSON.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any]) -> None:
    STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATE_JSON.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_latest_snapshot() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in fetch_json(LATEST_TWSE):
        stock_id = str(raw.get("Code") or "").strip()
        if stock_id:
            rows.append(normalize_valuation(raw, "twse"))
    for raw in fetch_json(LATEST_TPEX):
        stock_id = str(raw.get("SecuritiesCompanyCode") or "").strip()
        if stock_id:
            rows.append(normalize_valuation(raw, "tpex"))
    return rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    existing_rows = load_csv(OUT_CSV)
    snapshot = fetch_latest_snapshot()
    fetched_at = datetime.now().isoformat(timespec="seconds")
    snapshot_date = ""
    if snapshot:
        snapshot_date = str(snapshot[0].get("valuation_date", ""))
    for row in snapshot:
        row["fetched_at"] = fetched_at
    all_rows = existing_rows + snapshot
    all_rows.sort(key=lambda row: (row.get("valuation_date", ""), row.get("stock_id", "")))

    write_csv(
        OUT_CSV,
        all_rows,
        ["stock_id", "company_name", "market", "valuation_date", "pe_ratio", "pb_ratio", "dividend_yield_pct", "fetched_at"],
    )
    state.setdefault("snapshots", []).append(
        {
            "fetched_at": fetched_at,
            "valuation_date": snapshot_date,
            "rows": len(snapshot),
        }
    )
    save_state(state)
    summary = {
        "generated_at": date.today().isoformat(),
        "fetched_at": fetched_at,
        "rows_written": len(snapshot),
        "rows_total": len(all_rows),
        "valuation_date": snapshot_date,
        "output_csv": str(OUT_CSV),
        "note": "Official valuation endpoints are snapshot-based; this script accumulates daily snapshots forward from today.",
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
