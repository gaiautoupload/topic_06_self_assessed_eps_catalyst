from __future__ import annotations

import csv
import json
from pathlib import Path
from datetime import date


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "output"
SITE_DIR = PROJECT_DIR / "site"


def load_csv(name: str) -> list[dict[str, str]]:
    path = OUTPUT_DIR / name
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_json(name: str) -> dict:
    path = OUTPUT_DIR / name
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_float(value: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def build_payload() -> dict:
    events = load_csv("events.csv")
    comparisons = load_csv("event_comparisons.csv")
    snapshots = load_csv("valuation_snapshot.csv")
    missing_prices = load_csv("valuation_missing_prices.csv")
    trades = load_csv("trades.csv")
    valuation_summary = load_json("valuation_summary.json")
    trades_summary = load_json("trades_summary.json")

    trades_by_event: dict[str, list[dict[str, str]]] = {}
    for row in trades:
        trades_by_event.setdefault(row["event_id"], []).append(row)

    snapshot_by_event = {row["event_id"]: row for row in snapshots}
    comparison_by_event = {row["event_id"]: row for row in comparisons}
    event_cards: list[dict] = []
    for event in events:
        event_trades = trades_by_event.get(event["event_id"], [])
        snapshot = snapshot_by_event.get(event["event_id"])
        comparison = comparison_by_event.get(event["event_id"])
        avg_return = None
        if event_trades:
            values = [parse_float(row["return_pct"]) for row in event_trades]
            clean_values = [value for value in values if value is not None]
            if clean_values:
                avg_return = sum(clean_values) / len(clean_values)
        event_cards.append(
            {
                "event_id": event["event_id"],
                "stock_id": event["stock_id"],
                "company_name": event["company_name"],
                "announcement_date": event["announcement_date"],
                "title": event["title"],
                "event_type": event["event_type"],
                "signal_strength": event["signal_strength"],
                "eps_value": parse_float(event["eps_value"]),
                "profit_value": parse_float(event["profit_value"]),
                "coverage": "priced" if snapshot else "missing_price",
                "strategy_bucket": comparison["strategy_bucket"] if comparison else "topic_06_eps_catalyst",
                "metric_kind": comparison["metric_kind"] if comparison else None,
                "metric_prev": parse_float(comparison["metric_prev"]) if comparison else None,
                "prev_delta": parse_float(comparison["prev_delta"]) if comparison else None,
                "prev_pct": parse_float(comparison["prev_pct"]) if comparison else None,
                "yoy_delta": parse_float(comparison["yoy_delta"]) if comparison else None,
                "yoy_pct": parse_float(comparison["yoy_pct"]) if comparison else None,
                "turned_profit_from_loss": (comparison["turned_profit_from_loss"] == "True") if comparison else False,
                "entry_date": snapshot["entry_date"] if snapshot else None,
                "entry_close": parse_float(snapshot["close"]) if snapshot else None,
                "implied_pe": parse_float(snapshot["implied_pe"]) if snapshot else None,
                "avg_return_pct": avg_return,
                "latest_exit_date": max((trade["exit_date"] for trade in event_trades), default=None),
                "trades": [
                    {
                        "strategy_tag": row["strategy_tag"],
                        "entry_date": row["entry_date"],
                        "entry_price": parse_float(row["entry_price"]),
                        "exit_date": row["exit_date"],
                        "exit_price": parse_float(row["exit_price"]),
                        "holding_days": int(row["holding_days"]),
                        "return_pct": parse_float(row["return_pct"]),
                    }
                    for row in event_trades
                ],
            }
        )

    today = date.today().isoformat()
    ongoing_events = [
        row for row in event_cards
        if row["latest_exit_date"] is not None and row["latest_exit_date"] >= today
    ]
    upcoming_events = [
        row for row in event_cards
        if row["announcement_date"] > today
    ]
    past_events = [
        row for row in event_cards
        if row not in ongoing_events and row not in upcoming_events
    ]

    priced_events = [row for row in event_cards if row["coverage"] == "priced"]
    all_trade_returns = [
        trade["return_pct"]
        for event in event_cards
        for trade in event["trades"]
        if trade["return_pct"] is not None
    ]
    positive_trades = [value for value in all_trade_returns if value > 0]
    average_trade_return = sum(all_trade_returns) / len(all_trade_returns) if all_trade_returns else None

    return {
        "meta": {
            "title": "Topic 06: Self-Assessed EPS Catalyst",
            "generated_from": "project output csv/json",
            "author": "pioter",
            "author_tagline": "分析師+1000",
            "today": today,
        },
        "summary": {
            "events": len(events),
            "priced_events": len(priced_events),
            "missing_prices": len(missing_prices),
            "coverage_ratio": valuation_summary["coverage_ratio"],
            "trades": len(trades),
            "positive_trade_ratio": (len(positive_trades) / len(all_trade_returns)) if all_trade_returns else None,
            "average_trade_return": average_trade_return,
            "events_with_implied_pe": valuation_summary["events_with_implied_pe"],
            "ongoing_events": len(ongoing_events),
            "upcoming_events": len(upcoming_events),
            "past_events": len(past_events),
        },
        "valuation_summary": valuation_summary,
        "trades_summary": trades_summary,
        "comparison_summary": load_json("event_comparisons_summary.json"),
        "missing_stock_ids": sorted({row["stock_id"] for row in missing_prices}),
        "ongoing_events": ongoing_events,
        "upcoming_events": upcoming_events,
        "past_events": past_events,
        "event_cards": event_cards,
    }


def main() -> int:
    payload = build_payload()
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = SITE_DIR / "data.js"
    with output_path.open("w", encoding="utf-8") as fh:
        fh.write("window.TOPIC06_DATA = ")
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write(";\n")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
