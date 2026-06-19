from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
BASE_DIR = PROJECT_ROOT / "project_data" / "simple_monthly_revenue"
INPUT_CSV = BASE_DIR / "prepared_signal_universe.csv"
OUTPUT_CSV = BASE_DIR / "prepared_signal_universe_repaired.csv"
REPORT_JSON = BASE_DIR / "prepared_signal_universe_repair_report.json"
COMPANY_MASTER_CSV = Path(r"D:\dataset\processed\company_master.csv")
PRICE_DIR = Path(r"D:\dataset\processed\prices")


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_float(value: Any) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if text in {"", "-", "--", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_bool(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


def load_company_master() -> dict[str, dict[str, str]]:
    rows = load_csv(COMPANY_MASTER_CSV)
    return {row["stock_id"]: row for row in rows if row.get("stock_id")}


def load_prices(stock_id: str) -> list[dict[str, str]]:
    path = PRICE_DIR / f"{stock_id}.csv"
    return load_csv(path)


def first_trade_after(prices: list[dict[str, str]], announcement_date: str) -> int | None:
    for idx, row in enumerate(prices):
        if row.get("trade_date", "") > announcement_date:
            return idx
    return None


def lookback_values(prices: list[dict[str, str]], entry_idx: int, field: str, days: int) -> list[float]:
    rows = prices[max(0, entry_idx - days):entry_idx]
    values = []
    for row in rows:
        value = parse_float(row.get(field))
        if value is not None:
            values.append(value)
    return values


def avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def is_breakout(prices: list[dict[str, str]], entry_idx: int, days: int) -> bool | None:
    if entry_idx is None or entry_idx < 0 or entry_idx >= len(prices):
        return None
    prior_highs = lookback_values(prices, entry_idx, "high", days)
    entry_open = parse_float(prices[entry_idx].get("open"))
    if not prior_highs or entry_open is None:
        return None
    return bool(entry_open >= max(prior_highs))


def main() -> None:
    rows = load_csv(INPUT_CSV)
    if not rows:
        raise SystemExit(f"Missing input: {INPUT_CSV}")

    company_master = load_company_master()

    repaired: list[dict[str, Any]] = []
    missing_counter = Counter()
    stock_missing: defaultdict[str, list[str]] = defaultdict(list)

    for row in rows:
        repaired_row = dict(row)
        stock_id = row.get("stock_id", "")
        missing_fields: list[str] = []
        prices = load_prices(stock_id) if stock_id else []
        entry_idx = first_trade_after(prices, row.get("announcement_date", "")) if prices else None
        company = company_master.get(stock_id, {})

        for key in ("mom_pct", "yoy_pct", "foreign_net_buy_shares", "investment_trust_net_buy_shares", "dealer_net_buy_shares", "institutional_total_net_buy_shares", "avg_volume_5d", "avg_volume_20d", "previous_volume", "previous_volume_ratio_20d", "buy_price"):
            if repaired_row.get(key, "") in {"", None}:
                missing_fields.append(key)
                missing_counter[key] += 1

        for key in ("breakout_20d", "breakout_60d", "breakout_120d", "breakout_240d"):
            if repaired_row.get(key, "") in {"", None}:
                missing_fields.append(key)
                missing_counter[key] += 1

        # Rebuild the price-derived fields when possible.
        if prices and entry_idx is not None:
            repaired_row["buy_date"] = prices[entry_idx].get("trade_date") or repaired_row.get("buy_date")
            repaired_row["buy_price"] = parse_float(prices[entry_idx].get("open"))
            avg_volume_5d = avg(lookback_values(prices, entry_idx, "volume", 5))
            avg_volume_20d = avg(lookback_values(prices, entry_idx, "volume", 20))
            previous_volume = parse_float(prices[entry_idx - 1].get("volume")) if entry_idx > 0 else None
            previous_volume_ratio_20d = previous_volume / avg_volume_20d if previous_volume is not None and avg_volume_20d else None
            repaired_row["avg_volume_5d"] = avg_volume_5d
            repaired_row["avg_volume_20d"] = avg_volume_20d
            repaired_row["previous_volume"] = previous_volume
            repaired_row["previous_volume_ratio_20d"] = previous_volume_ratio_20d
            repaired_row["breakout_20d"] = is_breakout(prices, entry_idx, 20)
            repaired_row["breakout_60d"] = is_breakout(prices, entry_idx, 60)
            repaired_row["breakout_120d"] = is_breakout(prices, entry_idx, 120)
            repaired_row["breakout_240d"] = is_breakout(prices, entry_idx, 240)

        # Normalize blank fields to explicit null-like values so downstream code can detect them.
        for key in ("mom_pct", "yoy_pct", "current_month_revenue", "cumulative_yoy_pct", "foreign_net_buy_shares", "investment_trust_net_buy_shares", "dealer_net_buy_shares", "institutional_total_net_buy_shares", "avg_volume_5d", "avg_volume_20d", "previous_volume", "previous_volume_ratio_20d", "buy_price"):
            value = parse_float(repaired_row.get(key))
            repaired_row[key] = value

        for key in ("breakout_20d", "breakout_60d", "breakout_120d", "breakout_240d"):
            value = to_bool(repaired_row.get(key))
            repaired_row[key] = value

        if company:
            repaired_row["company_name"] = company.get("company_name", repaired_row.get("company_name"))
            repaired_row["market"] = company.get("market", repaired_row.get("market"))
            repaired_row["industry"] = company.get("industry", "")
            repaired_row["security_type"] = company.get("security_type", "")
            repaired_row["isin"] = company.get("isin", "")
            repaired_row["listed_date"] = company.get("listed_date", "")

        repaired_row["missing_fields"] = ";".join(missing_fields)
        stock_missing[stock_id].extend(missing_fields)
        repaired.append(repaired_row)

    fields = list(rows[0].keys()) + ["missing_fields"]
    write_csv(OUTPUT_CSV, repaired, fields)

    by_stock = {
        stock_id: sorted(set(fields))
        for stock_id, fields in stock_missing.items()
        if fields
    }
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_rows": len(rows),
        "output_rows": len(repaired),
        "missing_counts": dict(missing_counter),
        "stocks_with_missing": len(by_stock),
        "stocks_missing_sample": dict(list(by_stock.items())[:30]),
        "output_csv": str(OUTPUT_CSV),
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
