from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "output"
SITE_DIR = PROJECT_DIR / "site"
LOCAL_DIR = PROJECT_DIR / "project_data" / "2026_h1"
FUNDAMENTAL_LAB_DIR = PROJECT_DIR / "project_data" / "fundamental_event_lab"
SIMPLE_REVENUE_DIR = PROJECT_DIR / "project_data" / "simple_monthly_revenue"


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_float(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def build_event_map(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["event_id"]: row for row in rows if row.get("event_id")}


def build_payload() -> dict:
    today = date.today().isoformat()

    local_summary = load_json(LOCAL_DIR / "summary.json")
    monthly_summary = load_json(LOCAL_DIR / "monthly_portfolio_summary.json")
    backtest_summary = load_json(LOCAL_DIR / "backtest_summary.json")
    parameter_backtest_summary = load_json(FUNDAMENTAL_LAB_DIR / "parameter_backtest_summary.json")
    batch_backtest_summary = load_json(SIMPLE_REVENUE_DIR / "batch_backtest_summary.json")

    selected_events = load_csv(LOCAL_DIR / "selected_events.csv")
    main_events = load_csv(LOCAL_DIR / "main_strategy_events.csv")
    review_events = load_csv(LOCAL_DIR / "manual_review_events.csv")
    monthly_portfolio = load_csv(LOCAL_DIR / "monthly_portfolio.csv")
    marked_positions = load_csv(LOCAL_DIR / "backtest_marked_positions.csv")
    full_trades = load_csv(LOCAL_DIR / "backtest_trades.csv")
    best_parameter_trades = load_csv(FUNDAMENTAL_LAB_DIR / "best_parameter_trades.csv")
    batch_best_trades = load_csv(SIMPLE_REVENUE_DIR / "batch_best_trades.csv")
    batch_parameter_results = load_csv(SIMPLE_REVENUE_DIR / "batch_parameter_results.csv")
    skipped_rows = load_csv(LOCAL_DIR / "backtest_skipped.csv")
    main_gaps = load_csv(LOCAL_DIR / "main_event_gaps.csv")

    comparisons = load_csv(OUTPUT_DIR / "event_comparisons.csv")
    comparison_by_event = build_event_map(comparisons)
    main_event_by_id = build_event_map(main_events)
    selected_by_id = build_event_map(selected_events)

    trades_by_event: dict[str, list[dict[str, str]]] = {}
    for row in full_trades:
        trades_by_event.setdefault(row["event_id"], []).append(row)

    marked_by_event: dict[str, dict[str, str]] = {
        row["event_id"]: row for row in marked_positions if row.get("event_id")
    }

    portfolio_ids = {row["event_id"] for row in monthly_portfolio if row.get("event_id")}

    local_event_cards: list[dict] = []
    for row in main_events:
        event_id = row["event_id"]
        comparison = comparison_by_event.get(event_id, {})
        mark = marked_by_event.get(event_id, {})
        trades = trades_by_event.get(event_id, [])
        local_event_cards.append(
            {
                "event_id": event_id,
                "announcement_date": row["announcement_date"],
                "announcement_time": row.get("announcement_time", ""),
                "stock_id": row["stock_id"],
                "company_name": row["company_name"],
                "title": row["title"],
                "strategy_bucket": row["strategy_bucket"],
                "has_compare_context": parse_bool(row.get("has_compare_context")),
                "has_price_file": parse_bool(row.get("has_price_file")),
                "is_selected": event_id in portfolio_ids,
                "eps_value": parse_float(row.get("eps_value")),
                "profit_value": parse_float(row.get("profit_value")),
                "prev_pct": parse_float(comparison.get("prev_pct")),
                "yoy_pct": parse_float(comparison.get("yoy_pct")),
                "prev_delta": parse_float(comparison.get("prev_delta")),
                "yoy_delta": parse_float(comparison.get("yoy_delta")),
                "turned_profit_from_loss": parse_bool(comparison.get("turned_profit_from_loss")),
                "marked_return_pct": parse_float(mark.get("marked_return_pct")),
                "marked_pnl_amount": parse_float(mark.get("marked_pnl_amount")),
                "entry_date": mark.get("entry_date"),
                "entry_price": parse_float(mark.get("entry_price")),
                "latest_date": mark.get("latest_date"),
                "latest_price": parse_float(mark.get("latest_price")),
                "trades": [
                    {
                        "holding_days": int(trade["holding_days"]),
                        "entry_date": trade["entry_date"],
                        "exit_date": trade["exit_date"],
                        "return_pct": parse_float(trade["return_pct"]),
                        "pnl_amount": parse_float(trade["pnl_amount"]),
                    }
                    for trade in trades
                ],
            }
        )

    active_events = [
        event for event in local_event_cards
        if event["is_selected"] and event["has_price_file"]
    ]
    future_events = [
        event for event in local_event_cards
        if not event["has_price_file"]
    ]
    past_events = sorted(
        local_event_cards,
        key=lambda row: (row["announcement_date"], row["stock_id"]),
        reverse=True,
    )

    gap_counts: dict[str, int] = {}
    for row in main_gaps:
        issue = row["issue"]
        gap_counts[issue] = gap_counts.get(issue, 0) + 1

    skipped_by_reason: dict[str, int] = {}
    for row in skipped_rows:
        reason = row["reason"]
        skipped_by_reason[reason] = skipped_by_reason.get(reason, 0) + 1

    month_cards = []
    for month, info in sorted((monthly_summary.get("months") or {}).items()):
        month_cards.append(
            {
                "month": month,
                "candidate_events": info.get("candidate_events", 0),
                "selected_events": info.get("selected_events", 0),
                "allocation_per_event": info.get("allocation_per_event", 0),
                "allocated_capital": info.get("allocated_capital", 0),
                "fill_rule": info.get("fill_rule", ""),
            }
        )

    def numeric_batch_row(row: dict[str, str]) -> dict:
        numeric_fields = {
            "min_avg_volume_5d",
            "price_breakout_days",
            "min_institutional_net_buy",
            "eps_quality_clip_low",
            "eps_quality_clip_high",
            "stop_loss",
            "take_profit",
            "filtered",
            "selected",
            "trades",
            "covered_trade_months",
            "full_trade_months",
            "min_trades_per_month",
            "finalized_trades",
            "as_of_latest_trades",
            "win_rate",
            "avg_return_pct",
            "total_pnl_amount",
            "invested_amount",
            "portfolio_return_pct",
        }
        return {
            key: parse_float(value) if key in numeric_fields else value
            for key, value in row.items()
        }

    batch_rankings = [numeric_batch_row(row) for row in batch_parameter_results[:100]]

    return {
        "meta": {
            "title": "Topic 06: Self-Assessed EPS Catalyst",
            "today": today,
            "author": "pioter",
            "author_tagline": "分析師+1000",
        },
        "summary": {
            "selected_events": len(selected_events),
            "main_strategy_events": len(main_events),
            "manual_review_events": len(review_events),
            "active_events": len(active_events),
            "future_events": len(future_events),
            "past_events": len(past_events),
            "marked_positions": len(marked_positions),
            "full_trades": len(full_trades),
            "skipped_rows": len(skipped_rows),
        },
        "local_summary": local_summary,
        "monthly_summary": monthly_summary,
        "backtest_summary": backtest_summary,
        "parameter_backtest_summary": parameter_backtest_summary,
        "batch_backtest_summary": batch_backtest_summary,
        "batch_parameter_rankings": batch_rankings,
        "batch_best_trades": [
            {
                **row,
                "buy_price": parse_float(row.get("buy_price")),
                "exit_price": parse_float(row.get("exit_price")),
                "allocation_amount": parse_float(row.get("allocation_amount")),
                "return_pct": parse_float(row.get("return_pct")),
                "pnl_amount": parse_float(row.get("pnl_amount")),
                "mom_pct": parse_float(row.get("mom_pct")),
                "yoy_pct": parse_float(row.get("yoy_pct")),
                "institutional_total_net_buy_shares": parse_float(row.get("institutional_total_net_buy_shares")),
                "avg_volume_5d": parse_float(row.get("avg_volume_5d")),
                "previous_volume_ratio_20d": parse_float(row.get("previous_volume_ratio_20d")),
            }
            for row in batch_best_trades
        ],
        "best_parameter_trades": [
            {
                **row,
                "entry_price": parse_float(row.get("entry_price")),
                "exit_price": parse_float(row.get("exit_price")),
                "allocation_amount": parse_float(row.get("allocation_amount")),
                "return_pct": parse_float(row.get("return_pct")),
                "pnl_amount": parse_float(row.get("pnl_amount")),
                "signal_score": parse_float(row.get("signal_score")),
                "chip_score": parse_float(row.get("chip_score")),
                "foreign_net_buy_shares": parse_float(row.get("foreign_net_buy_shares")),
                "investment_trust_net_buy_shares": parse_float(row.get("investment_trust_net_buy_shares")),
                "institutional_total_net_buy_shares": parse_float(row.get("institutional_total_net_buy_shares")),
            }
            for row in best_parameter_trades
        ],
        "main_gap_counts": gap_counts,
        "skipped_by_reason": skipped_by_reason,
        "active_events": active_events,
        "future_events": future_events,
        "past_events": past_events,
        "month_cards": month_cards,
        "marked_positions": marked_positions,
        "selected_preview": [
            {
                "event_id": row["event_id"],
                "announcement_date": row["announcement_date"],
                "stock_id": row["stock_id"],
                "company_name": row["company_name"],
                "title": row["title"],
                "has_price_file": parse_bool(row.get("has_price_file")),
                "has_compare_context": parse_bool(row.get("has_compare_context")),
                "strategy_bucket": row["strategy_bucket"],
            }
            for row in selected_events
        ],
        "comparison_preview": {
            "available_rows": len(comparisons),
            "matched_main_rows": sum(
                1 for row in main_events if row["event_id"] in comparison_by_event
            ),
            "unmatched_main_rows": [
                row["event_id"] for row in main_events if row["event_id"] not in comparison_by_event
            ],
            "selected_but_not_main": [
                row["event_id"] for row in selected_events if row["event_id"] not in main_event_by_id
            ],
            "selected_missing_comparison": [
                row["event_id"] for row in selected_events if row["event_id"] not in comparison_by_event
            ],
            "selected_only_ids": [row["event_id"] for row in selected_by_id.values()],
        },
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
