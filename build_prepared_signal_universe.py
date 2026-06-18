from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "project_data" / "simple_monthly_revenue"
PRICE_DIR = DATA_DIR / "prices"
OUT_CSV = DATA_DIR / "prepared_signal_universe.csv"
OUT_JSON = DATA_DIR / "prepared_signal_universe.json"
SUMMARY_JSON = DATA_DIR / "prepared_signal_universe_summary.json"


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


def first_trade_after(prices: list[dict[str, str]], announcement_date: str) -> int | None:
    for idx, row in enumerate(prices):
        if row["trade_date"] > announcement_date:
            return idx
    return None


def avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def lookback_values(prices: list[dict[str, str]], entry_idx: int, field: str, days: int) -> list[float]:
    rows = prices[max(0, entry_idx - days):entry_idx]
    return [value for row in rows if (value := parse_float(row.get(field))) is not None]


def is_breakout(prices: list[dict[str, str]], entry_idx: int, days: int) -> bool:
    if days <= 0:
        return True
    prior_highs = lookback_values(prices, entry_idx, "high", days)
    entry_open = parse_float(prices[entry_idx].get("open"))
    return bool(prior_highs and entry_open is not None and entry_open >= max(prior_highs))


def main() -> int:
    revenue_rows = load_csv(DATA_DIR / "monthly_revenue_2026_to_date.csv")
    chip_rows = load_csv(DATA_DIR / "event_chips.csv")
    chips = {(row["announcement_date"], row["stock_id"]): row for row in chip_rows}

    output_rows: list[dict[str, Any]] = []
    skipped = {"missing_price_file": 0, "missing_entry": 0}

    for row in revenue_rows:
        price_path = PRICE_DIR / f"{row['stock_id']}.csv"
        if not price_path.exists():
            skipped["missing_price_file"] += 1
            continue
        prices = load_csv(price_path)
        entry_idx = first_trade_after(prices, row["announcement_date"])
        if entry_idx is None:
            skipped["missing_entry"] += 1
            continue

        chip = chips.get((row["announcement_date"], row["stock_id"]), {})
        avg_volume_5d = avg(lookback_values(prices, entry_idx, "volume", 5))
        avg_volume_20d = avg(lookback_values(prices, entry_idx, "volume", 20))
        previous_volume = parse_float(prices[entry_idx - 1].get("volume")) if entry_idx > 0 else None
        volume_ratio_20d = previous_volume / avg_volume_20d if previous_volume is not None and avg_volume_20d else None

        output_rows.append(
            {
                "event_id": row["event_id"],
                "revenue_month": row["revenue_month"],
                "announcement_date": row["announcement_date"],
                "announcement_time": row["announcement_time"],
                "buy_date": prices[entry_idx]["trade_date"],
                "buy_price": parse_float(prices[entry_idx].get("open")),
                "market": row["market"],
                "stock_id": row["stock_id"],
                "company_name": row["company_name"],
                "current_month_revenue": parse_float(row.get("current_month_revenue")),
                "mom_pct": parse_float(row.get("mom_pct")),
                "yoy_pct": parse_float(row.get("yoy_pct")),
                "cumulative_yoy_pct": parse_float(row.get("cumulative_yoy_pct")),
                "foreign_net_buy_shares": parse_float(chip.get("foreign_net_buy_shares")),
                "investment_trust_net_buy_shares": parse_float(chip.get("investment_trust_net_buy_shares")),
                "dealer_net_buy_shares": parse_float(chip.get("dealer_net_buy_shares")),
                "institutional_total_net_buy_shares": parse_float(chip.get("institutional_total_net_buy_shares")),
                "avg_volume_5d": avg_volume_5d,
                "avg_volume_20d": avg_volume_20d,
                "previous_volume": previous_volume,
                "previous_volume_ratio_20d": volume_ratio_20d,
                "breakout_20d": is_breakout(prices, entry_idx, 20),
                "breakout_60d": is_breakout(prices, entry_idx, 60),
                "breakout_120d": is_breakout(prices, entry_idx, 120),
                "breakout_240d": is_breakout(prices, entry_idx, 240),
                "eps_quality_score": "",
                "price_file": str(price_path),
            }
        )

    fields = [
        "event_id",
        "revenue_month",
        "announcement_date",
        "announcement_time",
        "buy_date",
        "buy_price",
        "market",
        "stock_id",
        "company_name",
        "current_month_revenue",
        "mom_pct",
        "yoy_pct",
        "cumulative_yoy_pct",
        "foreign_net_buy_shares",
        "investment_trust_net_buy_shares",
        "dealer_net_buy_shares",
        "institutional_total_net_buy_shares",
        "avg_volume_5d",
        "avg_volume_20d",
        "previous_volume",
        "previous_volume_ratio_20d",
        "breakout_20d",
        "breakout_60d",
        "breakout_120d",
        "breakout_240d",
        "eps_quality_score",
        "price_file",
    ]
    write_csv(OUT_CSV, output_rows, fields)
    OUT_JSON.write_text(json.dumps(output_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_revenue_rows": len(revenue_rows),
        "prepared_rows": len(output_rows),
        "skipped": skipped,
        "outputs": {"csv": str(OUT_CSV), "json": str(OUT_JSON)},
        "no_lookahead": "buy_date is the first trading day after announcement_date; volume and breakout factors use data before buy_date.",
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
