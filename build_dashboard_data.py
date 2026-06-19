from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
SITE_DIR = PROJECT_DIR / "site"
DOCS_DIR = PROJECT_DIR / "docs"

SIMPLE_DIR = PROJECT_DIR / "project_data" / "simple_monthly_revenue"
WINNER_DIR = SIMPLE_DIR / "winner_factor_mining"
FULL_WINNER_DIR = SIMPLE_DIR / "winner_factor_mining_full_market"
LOCAL_DIR = PROJECT_DIR / "project_data" / "2026_h1"

OUT_JS = SITE_DIR / "data.js"
DOCS_JS = DOCS_DIR / "data.js"


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "--", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def clip_text(text: Any, limit: int = 44) -> str:
    value = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def parse_num_row(row: dict[str, str], float_fields: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in float_fields:
            out[key] = parse_float(value)
        elif value in {"", None}:
            out[key] = None
        else:
            out[key] = value
    return out


def group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) or "")].append(row)
    return grouped


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, Any], ...]] = set()
    deduped: list[dict[str, Any]] = []
    ignore = {"spec_index", "min_score"}
    for row in rows:
        key = tuple(sorted((key, value) for key, value in row.items() if key not in ignore))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def build_monthly_portfolio() -> list[dict[str, Any]]:
    selected_rows = load_csv(LOCAL_DIR / "selected_events.csv")
    selected_lookup = {row["event_id"]: row for row in selected_rows if row.get("event_id")}
    portfolio_rows = load_csv(LOCAL_DIR / "monthly_portfolio.csv")
    summary_months = load_json(LOCAL_DIR / "monthly_portfolio_summary.json").get("months", {})
    float_fields = {"allocation_amount"}
    rows: list[dict[str, Any]] = []
    for row in portfolio_rows:
        enriched = parse_num_row(row, float_fields)
        selected = selected_lookup.get(row.get("event_id", ""), {})
        enriched.update(
            {
                "title": clip_text(selected.get("title", "")),
                "announcement_time": selected.get("announcement_time"),
                "eps_value": parse_float(selected.get("eps_value")),
                "profit_value": parse_float(selected.get("profit_value")),
                "has_price_file": parse_bool(selected.get("has_price_file")),
                "has_compare_context": parse_bool(selected.get("has_compare_context")),
                "source": selected.get("source"),
            }
        )
        rows.append(enriched)

    grouped = []
    for month, month_rows in sorted(group_by(rows, "month").items()):
        month_rows.sort(key=lambda row: (row.get("selected_rank") or 999, row.get("stock_id") or ""))
        total_allocation = sum(parse_float(row.get("allocation_amount")) or 0.0 for row in month_rows)
        month_summary = summary_months.get(month, {})
        grouped.append(
            {
                "month": month,
                "candidate_events": parse_float(month_summary.get("candidate_events")),
                "selected_events": parse_float(month_summary.get("selected_events")),
                "allocation_per_event": parse_float(month_summary.get("allocation_per_event")),
                "allocated_capital": parse_float(month_summary.get("allocated_capital")),
                "fill_rule": month_summary.get("fill_rule"),
                "total_allocation": total_allocation,
                "entries": month_rows,
            }
        )
    return grouped


def build_trade_months() -> list[dict[str, Any]]:
    selected_rows = load_csv(LOCAL_DIR / "selected_events.csv")
    selected_lookup: dict[tuple[str, str], dict[str, str]] = {}
    for row in selected_rows:
        key = (str(row.get("stock_id", "")), str(row.get("announcement_date", "")))
        selected_lookup[key] = row

    trade_rows = load_csv(SIMPLE_DIR / "batch_best_trades.csv")
    float_fields = {
        "buy_price",
        "exit_price",
        "allocation_amount",
        "return_pct",
        "pnl_amount",
        "mom_pct",
        "yoy_pct",
        "institutional_total_net_buy_shares",
        "avg_volume_5d",
        "previous_volume_ratio_20d",
    }
    rows: list[dict[str, Any]] = []
    for row in trade_rows:
        enriched = parse_num_row(row, float_fields)
        buy_date = str(row.get("buy_date") or "")
        exit_date = str(row.get("exit_date") or "")
        holding_days = None
        if buy_date and exit_date:
            try:
                holding_days = (datetime.fromisoformat(exit_date) - datetime.fromisoformat(buy_date)).days
            except ValueError:
                holding_days = None
        event = selected_lookup.get((str(row.get("stock_id", "")), str(row.get("announcement_date", ""))), {})
        enriched.update(
            {
                "title": clip_text(event.get("title", "")),
                "strategy_bucket": event.get("strategy_bucket") or row.get("parameter_id"),
                "announcement_time": event.get("announcement_time"),
                "has_price_file": parse_bool(event.get("has_price_file")),
                "has_compare_context": parse_bool(event.get("has_compare_context")),
                "holding_days": holding_days,
            }
        )
        rows.append(enriched)

    grouped = []
    for month, month_rows in sorted(group_by(rows, "revenue_month").items(), reverse=True):
        month_rows.sort(key=lambda row: (row.get("buy_date") or "", row.get("stock_id") or ""))
        trade_count = len(month_rows)
        win_rate = 0.0
        avg_return = 0.0
        total_pnl = 0.0
        if trade_count:
            win_rate = sum(1 for row in month_rows if (row.get("return_pct") or 0.0) > 0) / trade_count
            avg_return = sum((row.get("return_pct") or 0.0) for row in month_rows) / trade_count
            total_pnl = sum((row.get("pnl_amount") or 0.0) for row in month_rows)
        grouped.append(
            {
                "month": month,
                "trade_count": trade_count,
                "win_rate": win_rate,
                "avg_return_pct": avg_return,
                "total_pnl_amount": total_pnl,
                "trades": month_rows,
            }
        )
    return grouped


def build_strategy_leaderboards() -> dict[str, Any]:
    float_fields = {
        "spec_index",
        "min_score",
        "target_positions_per_month",
        "min_trades_per_month",
        "chip_w",
        "tech_w",
        "fundamental_w",
        "value_w",
        "trades",
        "months",
        "win_rate",
        "avg_return_pct",
        "monthly_avg_return_pct",
        "objective",
    }
    all_top = load_csv(WINNER_DIR / "gold50_strategy_results.csv")
    global_top = load_csv(WINNER_DIR / "gold50_global_strategy_results.csv")
    family_files = {
        "breakout_growth": WINNER_DIR / "gold50_breakout_growth_results.csv",
        "undervalued_growth": WINNER_DIR / "gold50_undervalued_growth_results.csv",
        "second_breakout": WINNER_DIR / "gold50_second_breakout_results.csv",
    }
    raw_families: dict[str, list[dict[str, Any]]] = {}
    families: dict[str, list[dict[str, Any]]] = {}
    for name, path in family_files.items():
        raw_rows = [parse_num_row(row, float_fields) for row in load_csv(path)]
        raw_families[name] = raw_rows
        families[name] = dedupe_rows(raw_rows)
    return {
        "raw_all": [parse_num_row(row, float_fields) for row in all_top],
        "raw_global": [parse_num_row(row, float_fields) for row in global_top],
        "raw_families": raw_families,
        "all": dedupe_rows([parse_num_row(row, float_fields) for row in all_top]),
        "global": dedupe_rows([parse_num_row(row, float_fields) for row in global_top]),
        "families": families,
    }


def build_strategy_cards() -> list[dict[str, Any]]:
    summaries = {
        "global": load_json(WINNER_DIR / "gold50_global_strategy_summary.json"),
        "breakout_growth": load_json(WINNER_DIR / "gold50_breakout_growth_summary.json"),
        "undervalued_growth": load_json(WINNER_DIR / "gold50_undervalued_growth_summary.json"),
        "second_breakout": load_json(WINNER_DIR / "gold50_second_breakout_summary.json"),
    }
    labels = {
        "global": "全局策略",
        "breakout_growth": "股價創高加營收成長",
        "undervalued_growth": "股價低估營收很好的潛在股",
        "second_breakout": "創高後壓回但有基本面支撐的二次創高股",
    }
    cards: list[dict[str, Any]] = []
    for key in ("global", "breakout_growth", "undervalued_growth", "second_breakout"):
        summary = summaries.get(key, {}).get("best") or summaries.get(key, {}).get("best_combo") or {}
        cards.append(
            {
                "key": key,
                "label": labels[key],
                "best_combo": summary.get("combo"),
                "trades": parse_float(summary.get("trades")),
                "win_rate": parse_float(summary.get("win_rate")),
                "avg_return_pct": parse_float(summary.get("avg_return_pct")),
                "monthly_avg_return_pct": parse_float(summary.get("monthly_avg_return_pct")),
                "objective": parse_float(summary.get("objective")),
                "months": parse_float(summary.get("months")),
            }
        )
    return cards


def build_overview() -> dict[str, Any]:
    batch_summary = load_json(SIMPLE_DIR / "batch_backtest_summary.json")
    parameter_summary = load_json(PROJECT_DIR / "project_data" / "fundamental_event_lab" / "parameter_backtest_summary.json")
    winner_summary = load_json(FULL_WINNER_DIR / "winner_factor_summary.json")
    monthly_summary = load_json(LOCAL_DIR / "monthly_portfolio_summary.json")
    backtest_summary = load_json(LOCAL_DIR / "backtest_summary.json")
    gold50_global = load_json(WINNER_DIR / "gold50_global_strategy_summary.json")
    gold50_second = load_json(WINNER_DIR / "gold50_second_breakout_summary.json")
    return {
        "month_budget": parse_float(monthly_summary.get("monthly_capital")) or 1_000_000.0,
        "target_positions": parse_float(monthly_summary.get("target_positions")) or 5.0,
        "rebalance_hint": monthly_summary.get("rebalance_day_hint"),
        "local_trades": parse_float(backtest_summary.get("trades")) or 0.0,
        "batch_best": batch_summary.get("best", {}),
        "parameter_best": parameter_summary.get("best", {}),
        "winner_best": winner_summary.get("best_combo") or winner_summary.get("best") or {},
        "global_best": gold50_global.get("best") or {},
        "second_breakout_best": gold50_second.get("best") or {},
    }


def build_payload() -> dict[str, Any]:
    strategy_leaderboards = build_strategy_leaderboards()
    monthly_portfolio = build_monthly_portfolio()
    trade_months = build_trade_months()
    strategy_cards = build_strategy_cards()
    overview = build_overview()

    latest_month = monthly_portfolio[-1] if monthly_portfolio else {"month": "", "entries": []}
    current_holdings = latest_month.get("entries", [])[:5]

    return {
        "meta": {
            "title": "Topic 06 自結 EPS 戰情室",
            "subtitle": "公告先手、每月買賣、回測績效與策略排行一次看完",
            "author": "pioter",
            "author_tagline": "分析師+1000",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "overview": overview,
        "strategy_cards": strategy_cards,
        "strategy_leaderboards": strategy_leaderboards,
        "monthly_portfolio": monthly_portfolio,
        "current_holdings": current_holdings,
        "trade_months": trade_months,
        "backtest_summaries": {
            "batch": load_json(SIMPLE_DIR / "batch_backtest_summary.json"),
            "parameter": load_json(PROJECT_DIR / "project_data" / "fundamental_event_lab" / "parameter_backtest_summary.json"),
            "winner_factor": load_json(FULL_WINNER_DIR / "winner_factor_summary.json"),
            "global": load_json(WINNER_DIR / "gold50_global_strategy_summary.json"),
            "breakout_growth": load_json(WINNER_DIR / "gold50_breakout_growth_summary.json"),
            "undervalued_growth": load_json(WINNER_DIR / "gold50_undervalued_growth_summary.json"),
            "second_breakout": load_json(WINNER_DIR / "gold50_second_breakout_summary.json"),
        },
    }


def write_js(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    js = "window.TOPIC06_DASHBOARD = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"
    path.write_text(js, encoding="utf-8")


def main() -> int:
    payload = build_payload()
    write_js(OUT_JS, payload)
    if DOCS_DIR.exists():
        write_js(DOCS_JS, payload)
    boards = payload["strategy_leaderboards"]
    print(json.dumps(
        {
            "generated_at": payload["meta"]["generated_at"],
            "monthly_portfolio_months": len(payload["monthly_portfolio"]),
            "trade_months": len(payload["trade_months"]),
            "raw_global_strategies": len(boards.get("raw_global", [])),
            "raw_all_strategies": len(boards.get("raw_all", [])),
            "unique_global_strategies": len(boards.get("global", [])),
            "unique_all_strategies": len(boards.get("all", [])),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
