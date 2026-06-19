from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from strategy_config import load_brain_rule_config


PROJECT_DIR = Path(__file__).resolve().parent
DATASET_DIR = Path(r"D:\dataset")
LOCAL_DIR = PROJECT_DIR / "project_data" / "fundamental_event_lab"
LOCAL_PRICE_DIR = LOCAL_DIR / "prices"
SHARED_PRICE_DIR = DATASET_DIR / "processed" / "prices"

MONTHLY_CAPITAL = 1_000_000.0
MIN_REVENUE_YOY_VALUES = [0.0, 0.10, 0.20, 0.50]
MIN_EPS_YOY_VALUES = [0.0, 0.20, 0.50]
REQUIRE_POSITIVE_EPS_VALUES = [True, False]
REQUIRE_THREE_RISES_VALUES = [True, False]
EXIT_RULES = ["month_end", "next_month_3", "next_month_5", "next_month_10"]


@dataclass
class BacktestTrade:
    parameter_id: str
    month: str
    stock_id: str
    company_name: str
    event_id: str
    announcement_date: str
    announcement_time: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    exit_status: str
    allocation_amount: float
    return_pct: float
    pnl_amount: float
    signal_score: float
    chip_score: float
    chip_date: str
    foreign_net_buy_shares: float | None
    investment_trust_net_buy_shares: float | None
    institutional_total_net_buy_shares: float | None
    exit_rule: str


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def parse_float(value: str | None) -> float | None:
    text = (value or "").strip()
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


def merge_event_chips(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    chip_rows = load_csv(LOCAL_DIR / "event_historical_chips.csv")
    chips_by_event = {row["event_id"]: row for row in chip_rows if row.get("event_id")}
    enriched: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        chip = chips_by_event.get(row.get("event_id", ""), {})
        for key in [
            "chip_date",
            "chip_offset_days",
            "foreign_net_buy_shares",
            "investment_trust_net_buy_shares",
            "dealer_net_buy_shares",
            "institutional_total_net_buy_shares",
        ]:
            item[key] = chip.get(key, "")
        enriched.append(item)
    return enriched


def month_key(date_text: str) -> str:
    return date_text[:7]


def load_prices(stock_id: str) -> list[dict[str, str]]:
    local_rows = load_csv(LOCAL_PRICE_DIR / f"{stock_id}.csv")
    if local_rows:
        return local_rows
    return load_csv(SHARED_PRICE_DIR / f"{stock_id}.csv")


def has_price_file(stock_id: str) -> bool:
    return (LOCAL_PRICE_DIR / f"{stock_id}.csv").exists() or (SHARED_PRICE_DIR / f"{stock_id}.csv").exists()


def next_trade_index(prices: list[dict[str, str]], announcement_date: str) -> int | None:
    for idx, row in enumerate(prices):
        if row["trade_date"] > announcement_date:
            return idx
    return None


def month_end_exit_index(prices: list[dict[str, str]], entry_idx: int) -> tuple[int, str] | None:
    entry_month = prices[entry_idx]["trade_date"][:7]
    exit_idx = entry_idx
    saw_next_month = False
    for idx in range(entry_idx, len(prices)):
        if prices[idx]["trade_date"][:7] != entry_month:
            saw_next_month = True
            break
        exit_idx = idx
    return exit_idx, "final" if saw_next_month else "as_of_latest"


def next_month_n_exit_index(prices: list[dict[str, str]], entry_idx: int, n: int) -> tuple[int, str] | None:
    entry_date = date.fromisoformat(prices[entry_idx]["trade_date"])
    if entry_date.month == 12:
        next_month = f"{entry_date.year + 1:04d}-01"
    else:
        next_month = f"{entry_date.year:04d}-{entry_date.month + 1:02d}"
    indices = [idx for idx, row in enumerate(prices) if row["trade_date"][:7] == next_month]
    if len(indices) < n:
        return None
    return indices[n - 1], "final"


def exit_index_for_rule(prices: list[dict[str, str]], entry_idx: int, exit_rule: str) -> tuple[int, str] | None:
    if exit_rule == "month_end":
        return month_end_exit_index(prices, entry_idx)
    if exit_rule.startswith("next_month_"):
        n = int(exit_rule.rsplit("_", 1)[1])
        return next_month_n_exit_index(prices, entry_idx, n)
    return None


def passes_filters(
    row: dict[str, str],
    min_revenue_yoy: float,
    min_eps_yoy: float,
    require_positive_eps: bool,
    require_three_rises: bool,
    min_institutional_net_buy: float | None,
    require_foreign_net_buy: bool,
    require_investment_trust_net_buy: bool,
) -> bool:
    revenue_yoy = parse_float(row.get("monthly_revenue_yoy_pct"))
    eps_yoy = parse_float(row.get("eps_yoy_pct"))
    eps = parse_float(row.get("eps"))
    three_rises_count = int(float(row.get("three_rises_count") or 0))
    foreign_net_buy = parse_float(row.get("foreign_net_buy_shares"))
    investment_trust_net_buy = parse_float(row.get("investment_trust_net_buy_shares"))
    institutional_total_net_buy = parse_float(row.get("institutional_total_net_buy_shares"))

    if revenue_yoy is None or revenue_yoy < min_revenue_yoy:
        return False
    if eps_yoy is None or eps_yoy < min_eps_yoy:
        return False
    if require_positive_eps and (eps is None or eps <= 0):
        return False
    if require_three_rises and three_rises_count < 3:
        return False
    if min_institutional_net_buy is not None and (
        institutional_total_net_buy is None or institutional_total_net_buy < min_institutional_net_buy
    ):
        return False
    if require_foreign_net_buy and (foreign_net_buy is None or foreign_net_buy <= 0):
        return False
    if require_investment_trust_net_buy and (
        investment_trust_net_buy is None or investment_trust_net_buy <= 0
    ):
        return False
    if not has_price_file(row["stock_id"]):
        return False
    return True


def chip_score(row: dict[str, str]) -> float:
    institutional_total = parse_float(row.get("institutional_total_net_buy_shares")) or 0.0
    foreign = parse_float(row.get("foreign_net_buy_shares")) or 0.0
    investment_trust = parse_float(row.get("investment_trust_net_buy_shares")) or 0.0
    raw_score = institutional_total / 1_000_000.0
    if foreign > 0:
        raw_score += 0.5
    if investment_trust > 0:
        raw_score += 0.75
    return max(-5.0, min(5.0, raw_score))


def select_monthly(rows: Iterable[dict[str, str]], top_n: int) -> list[dict[str, str]]:
    by_month: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_month.setdefault(month_key(row["announcement_date"]), []).append(row)

    selected: list[dict[str, str]] = []
    for month, month_rows in by_month.items():
        ordered = sorted(
            month_rows,
            key=lambda row: (
                -((parse_float(row.get("signal_score")) or 0.0) + chip_score(row)),
                row["announcement_date"],
                row["announcement_time"],
                row["stock_id"],
            ),
        )
        chosen = ordered[:top_n]
        allocation = MONTHLY_CAPITAL / len(chosen) if chosen else 0
        for row in chosen:
            enriched = dict(row)
            enriched["allocation_amount"] = str(round(allocation, 2))
            selected.append(enriched)
    return selected


def build_trade(row: dict[str, str], parameter_id: str, exit_rule: str) -> BacktestTrade | None:
    prices = load_prices(row["stock_id"])
    if not prices:
        return None
    entry_idx = next_trade_index(prices, row["announcement_date"])
    if entry_idx is None:
        return None
    exit_result = exit_index_for_rule(prices, entry_idx, exit_rule)
    if exit_result is None:
        return None
    exit_idx, exit_status = exit_result
    if exit_idx < entry_idx:
        return None

    entry_price = parse_float(prices[entry_idx].get("open"))
    exit_price = parse_float(prices[exit_idx].get("close"))
    allocation = parse_float(row.get("allocation_amount"))
    if entry_price is None or exit_price is None or allocation is None or entry_price == 0:
        return None

    return_pct = round((exit_price - entry_price) / entry_price, 6)
    return BacktestTrade(
        parameter_id=parameter_id,
        month=month_key(row["announcement_date"]),
        stock_id=row["stock_id"],
        company_name=row["company_name"],
        event_id=row["event_id"],
        announcement_date=row["announcement_date"],
        announcement_time=row["announcement_time"],
        entry_date=prices[entry_idx]["trade_date"],
        entry_price=entry_price,
        exit_date=prices[exit_idx]["trade_date"],
        exit_price=exit_price,
        exit_status=exit_status,
        allocation_amount=allocation,
        return_pct=return_pct,
        pnl_amount=round(allocation * return_pct, 2),
        signal_score=parse_float(row.get("signal_score")) or 0.0,
        chip_score=chip_score(row),
        chip_date=row.get("chip_date", ""),
        foreign_net_buy_shares=parse_float(row.get("foreign_net_buy_shares")),
        investment_trust_net_buy_shares=parse_float(row.get("investment_trust_net_buy_shares")),
        institutional_total_net_buy_shares=parse_float(row.get("institutional_total_net_buy_shares")),
        exit_rule=exit_rule,
    )


def parameter_id(
    top_n: int,
    min_revenue_yoy: float,
    min_eps_yoy: float,
    require_positive_eps: bool,
    require_three_rises: bool,
    min_institutional_net_buy: float | None,
    require_foreign_net_buy: bool,
    require_investment_trust_net_buy: bool,
    exit_rule: str,
) -> str:
    inst_label = "any" if min_institutional_net_buy is None else str(int(min_institutional_net_buy / 1000)) + "k"
    return (
        f"top{top_n}_rev{int(min_revenue_yoy * 100)}"
        f"_eps{int(min_eps_yoy * 100)}"
        f"_poseps{int(require_positive_eps)}"
        f"_rise{int(require_three_rises)}"
        f"_inst{inst_label}"
        f"_foreign{int(require_foreign_net_buy)}"
        f"_trust{int(require_investment_trust_net_buy)}"
        f"_{exit_rule}"
    )


def summarize_trades(parameter: dict[str, object], trades: list[BacktestTrade], candidates: int, selected: int) -> dict[str, object]:
    returns = [trade.return_pct for trade in trades]
    wins = [value for value in returns if value > 0]
    total_pnl = round(sum(trade.pnl_amount for trade in trades), 2)
    invested = round(sum(trade.allocation_amount for trade in trades), 2)
    return {
        **parameter,
        "candidates": candidates,
        "selected": selected,
        "trades": len(trades),
        "finalized_trades": len([trade for trade in trades if trade.exit_status == "final"]),
        "as_of_latest_trades": len([trade for trade in trades if trade.exit_status == "as_of_latest"]),
        "win_rate": round(len(wins) / len(returns), 6) if returns else None,
        "avg_return_pct": round(sum(returns) / len(returns), 6) if returns else None,
        "total_pnl_amount": total_pnl,
        "invested_amount": invested,
        "portfolio_return_pct": round(total_pnl / invested, 6) if invested else None,
    }


def write_dict_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_trade_csv(path: Path, rows: list[BacktestTrade]) -> None:
    fields = list(BacktestTrade.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main() -> int:
    brain_config = load_brain_rule_config()
    events_path = LOCAL_DIR / "fundamental_events_2026_h1.csv"
    rows = merge_event_chips(load_csv(events_path))
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    result_rows: list[dict[str, object]] = []
    trades_by_parameter: dict[str, list[BacktestTrade]] = {}

    for top_n in brain_config.top_n_values:
        for min_revenue_yoy in MIN_REVENUE_YOY_VALUES:
            for min_eps_yoy in MIN_EPS_YOY_VALUES:
                for require_positive_eps in REQUIRE_POSITIVE_EPS_VALUES:
                    for require_three_rises in REQUIRE_THREE_RISES_VALUES:
                        for min_institutional_net_buy in brain_config.min_institutional_net_buy_values:
                            for require_foreign_net_buy in brain_config.require_foreign_net_buy_values:
                                for require_investment_trust_net_buy in brain_config.require_investment_trust_net_buy_values:
                                    filtered = [
                                        row for row in rows
                                        if passes_filters(
                                            row,
                                            min_revenue_yoy,
                                            min_eps_yoy,
                                            require_positive_eps,
                                            require_three_rises,
                                            min_institutional_net_buy,
                                            require_foreign_net_buy,
                                            require_investment_trust_net_buy,
                                        )
                                    ]
                                    selected = select_monthly(filtered, top_n)
                                    for exit_rule in EXIT_RULES:
                                        pid = parameter_id(
                                            top_n,
                                            min_revenue_yoy,
                                            min_eps_yoy,
                                            require_positive_eps,
                                            require_three_rises,
                                            min_institutional_net_buy,
                                            require_foreign_net_buy,
                                            require_investment_trust_net_buy,
                                            exit_rule,
                                        )
                                        parameter = {
                                            "parameter_id": pid,
                                            "top_n": top_n,
                                            "min_revenue_yoy_pct": min_revenue_yoy,
                                            "min_eps_yoy_pct": min_eps_yoy,
                                            "require_positive_eps": require_positive_eps,
                                            "require_three_rises": require_three_rises,
                                            "min_institutional_net_buy_shares": min_institutional_net_buy,
                                            "require_foreign_net_buy": require_foreign_net_buy,
                                            "require_investment_trust_net_buy": require_investment_trust_net_buy,
                                            "exit_rule": exit_rule,
                                        }
                                        trades = [
                                            trade for row in selected
                                            if (trade := build_trade(row, pid, exit_rule)) is not None
                                        ]
                                        trades_by_parameter[pid] = trades
                                        result_rows.append(summarize_trades(parameter, trades, len(filtered), len(selected)))

    result_rows.sort(
        key=lambda row: (
            -(row["portfolio_return_pct"] if row["portfolio_return_pct"] is not None else -999),
            -(row["trades"]),
        )
    )
    best = result_rows[0] if result_rows else {}
    best_trades = trades_by_parameter.get(str(best.get("parameter_id")), [])

    write_dict_csv(LOCAL_DIR / "parameter_results.csv", result_rows)
    write_trade_csv(LOCAL_DIR / "best_parameter_trades.csv", best_trades)

    summary = {
        "events": len(rows),
        "event_chip_rows": len([row for row in rows if row.get("chip_date")]),
        "use_local_brain_rules": brain_config.use_local_brain_rules,
        "parameter_sets": len(result_rows),
        "best": best,
        "result_csv": str(LOCAL_DIR / "parameter_results.csv"),
        "best_trades_csv": str(LOCAL_DIR / "best_parameter_trades.csv"),
    }
    with (LOCAL_DIR / "parameter_backtest_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
