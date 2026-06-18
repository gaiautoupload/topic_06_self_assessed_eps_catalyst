from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "project_data" / "simple_monthly_revenue"
SIGNAL_CSV = DATA_DIR / "prepared_signal_universe.csv"
RESULT_CSV = DATA_DIR / "batch_parameter_results.csv"
BEST_TRADES_CSV = DATA_DIR / "batch_best_trades.csv"
SUMMARY_JSON = DATA_DIR / "batch_backtest_summary.json"

MONTHLY_CAPITAL = 1_000_000.0
TARGET_POSITIONS_PER_MONTH = 5

MIN_AVG_VOLUME_5D_VALUES = [0.0, 50_000.0, 100_000.0, 300_000.0, 500_000.0, 1_000_000.0, 2_000_000.0]
PRICE_BREAKOUT_DAYS_VALUES = [0, 20, 60, 120, 240]
MIN_INSTITUTIONAL_NET_BUY_VALUES = [None, 0.0, 100_000.0, 300_000.0, 500_000.0, 1_000_000.0, 2_000_000.0]
EPS_QUALITY_CLIP_LOW_VALUES = [None, -0.5, 0.0]
EPS_QUALITY_CLIP_HIGH_VALUES = [None, 1.0, 2.0]
STOP_LOSS_VALUES = [None, 0.10, 0.20, 0.30]
TAKE_PROFIT_VALUES = [None, 0.30, 0.50, 0.80, 1.20]
EXIT_RULES = ["month_end", "next_month_5", "next_month_10"]


@dataclass
class Trade:
    parameter_id: str
    revenue_month: str
    stock_id: str
    company_name: str
    announcement_date: str
    buy_date: str
    buy_price: float
    exit_date: str
    exit_price: float
    exit_reason: str
    exit_status: str
    allocation_amount: float
    return_pct: float
    pnl_amount: float
    mom_pct: float | None
    yoy_pct: float | None
    institutional_total_net_buy_shares: float | None
    avg_volume_5d: float | None
    previous_volume_ratio_20d: float | None


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


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def load_price_file(path: str) -> list[dict[str, str]]:
    return load_csv(Path(path))


def price_index_by_date(prices: list[dict[str, str]], trade_date: str) -> int | None:
    for idx, row in enumerate(prices):
        if row["trade_date"] == trade_date:
            return idx
    return None


def scheduled_exit_idx(prices: list[dict[str, str]], entry_idx: int, exit_rule: str) -> tuple[int, str] | None:
    entry_month = prices[entry_idx]["trade_date"][:7]
    if exit_rule == "month_end":
        idx = entry_idx
        finalized = False
        for i in range(entry_idx, len(prices)):
            if prices[i]["trade_date"][:7] != entry_month:
                finalized = True
                break
            idx = i
        return idx, "final" if finalized else "as_of_latest"

    year = int(entry_month[:4])
    month = int(entry_month[5:])
    if month == 12:
        next_month = f"{year + 1:04d}-01"
    else:
        next_month = f"{year:04d}-{month + 1:02d}"
    n = int(exit_rule.rsplit("_", 1)[1])
    indices = [idx for idx, row in enumerate(prices) if row["trade_date"][:7] == next_month]
    if len(indices) < n:
        return None
    return indices[n - 1], "final"


def simulate_exit(
    prices: list[dict[str, str]],
    entry_idx: int,
    exit_rule: str,
    stop_loss: float | None,
    take_profit: float | None,
) -> tuple[int, float, str, str] | None:
    scheduled = scheduled_exit_idx(prices, entry_idx, exit_rule)
    if scheduled is None:
        return None
    scheduled_idx, status = scheduled
    entry_price = parse_float(prices[entry_idx].get("open"))
    if entry_price is None:
        return None

    stop_price = entry_price * (1 - stop_loss) if stop_loss is not None else None
    take_price = entry_price * (1 + take_profit) if take_profit is not None else None
    for idx in range(entry_idx, scheduled_idx + 1):
        low = parse_float(prices[idx].get("low"))
        high = parse_float(prices[idx].get("high"))
        if stop_price is not None and low is not None and low <= stop_price:
            return idx, round(stop_price, 4), "stop_loss", "final"
        if take_price is not None and high is not None and high >= take_price:
            return idx, round(take_price, 4), "take_profit", "final"
    exit_price = parse_float(prices[scheduled_idx].get("close"))
    if exit_price is None:
        return None
    return scheduled_idx, exit_price, exit_rule, status


def passes_filter(
    row: dict[str, str],
    min_avg_volume_5d: float,
    breakout_days: int,
    min_institutional_net_buy: float | None,
    eps_low: float | None,
    eps_high: float | None,
) -> bool:
    avg_volume = parse_float(row.get("avg_volume_5d")) or 0.0
    if avg_volume < min_avg_volume_5d:
        return False
    if breakout_days and not parse_bool(row.get(f"breakout_{breakout_days}d")):
        return False
    institutional = parse_float(row.get("institutional_total_net_buy_shares"))
    if min_institutional_net_buy is not None and (institutional is None or institutional < min_institutional_net_buy):
        return False
    eps_quality = parse_float(row.get("eps_quality_score"))
    if eps_quality is not None:
        if eps_low is not None and eps_quality < eps_low:
            return False
        if eps_high is not None and eps_quality > eps_high:
            return False
    return True


def parameter_id(
    min_avg_volume_5d: float,
    breakout_days: int,
    min_institutional_net_buy: float | None,
    eps_low: float | None,
    eps_high: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    exit_rule: str,
) -> str:
    inst_label = "any" if min_institutional_net_buy is None else f"{int(min_institutional_net_buy / 1000)}k"
    eps_low_label = "any" if eps_low is None else str(eps_low)
    eps_high_label = "any" if eps_high is None else str(eps_high)
    stop_label = "none" if stop_loss is None else str(int(stop_loss * 100))
    take_label = "none" if take_profit is None else str(int(take_profit * 100))
    return (
        f"vol5_{int(min_avg_volume_5d)}"
        f"_high{breakout_days}"
        f"_inst{inst_label}"
        f"_epslo{eps_low_label}"
        f"_epshi{eps_high_label}"
        f"_sl{stop_label}"
        f"_tp{take_label}"
        f"_{exit_rule}"
    )


def select_monthly(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_month: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_month.setdefault(row["revenue_month"], []).append(row)
    selected: list[dict[str, str]] = []
    for month_rows in by_month.values():
        selected.extend(
            sorted(
                month_rows,
                key=lambda row: (
                    -(parse_float(row.get("mom_pct")) or 0),
                    -(parse_float(row.get("yoy_pct")) or 0),
                    -(parse_float(row.get("institutional_total_net_buy_shares")) or 0),
                    -(parse_float(row.get("avg_volume_5d")) or 0),
                    row["stock_id"],
                ),
            )[:TARGET_POSITIONS_PER_MONTH]
        )
    return selected


def build_trades(
    pid: str,
    selected: list[dict[str, str]],
    exit_rule: str,
    stop_loss: float | None,
    take_profit: float | None,
    price_cache: dict[str, list[dict[str, str]]],
) -> list[Trade]:
    selected_count_by_month: dict[str, int] = {}
    for row in selected:
        selected_count_by_month[row["revenue_month"]] = selected_count_by_month.get(row["revenue_month"], 0) + 1

    trades = []
    for row in selected:
        prices = price_cache.setdefault(row["stock_id"], load_price_file(row["price_file"]))
        entry_idx = price_index_by_date(prices, row["buy_date"])
        if entry_idx is None:
            continue
        exit_result = simulate_exit(prices, entry_idx, exit_rule, stop_loss, take_profit)
        if exit_result is None:
            continue
        exit_idx, exit_price, exit_reason, exit_status = exit_result
        buy_price = parse_float(row.get("buy_price"))
        if buy_price is None or buy_price == 0:
            continue
        allocation = MONTHLY_CAPITAL / selected_count_by_month[row["revenue_month"]]
        return_pct = (exit_price - buy_price) / buy_price
        trades.append(
            Trade(
                parameter_id=pid,
                revenue_month=row["revenue_month"],
                stock_id=row["stock_id"],
                company_name=row["company_name"],
                announcement_date=row["announcement_date"],
                buy_date=row["buy_date"],
                buy_price=buy_price,
                exit_date=prices[exit_idx]["trade_date"],
                exit_price=exit_price,
                exit_reason=exit_reason,
                exit_status=exit_status,
                allocation_amount=round(allocation, 2),
                return_pct=round(return_pct, 6),
                pnl_amount=round(allocation * return_pct, 2),
                mom_pct=parse_float(row.get("mom_pct")),
                yoy_pct=parse_float(row.get("yoy_pct")),
                institutional_total_net_buy_shares=parse_float(row.get("institutional_total_net_buy_shares")),
                avg_volume_5d=parse_float(row.get("avg_volume_5d")),
                previous_volume_ratio_20d=parse_float(row.get("previous_volume_ratio_20d")),
            )
        )
    return trades


def summarize(parameter: dict[str, Any], filtered: list[dict[str, str]], selected: list[dict[str, str]], trades: list[Trade]) -> dict[str, Any]:
    selected_by_month: dict[str, int] = {}
    trades_by_month: dict[str, int] = {}
    for row in selected:
        selected_by_month[row["revenue_month"]] = selected_by_month.get(row["revenue_month"], 0) + 1
    for trade in trades:
        trades_by_month[trade.revenue_month] = trades_by_month.get(trade.revenue_month, 0) + 1
    returns = [trade.return_pct for trade in trades]
    invested = sum(trade.allocation_amount for trade in trades)
    pnl = sum(trade.pnl_amount for trade in trades)
    return {
        **parameter,
        "filtered": len(filtered),
        "selected": len(selected),
        "trades": len(trades),
        "covered_trade_months": len(trades_by_month),
        "full_trade_months": len([count for count in trades_by_month.values() if count >= TARGET_POSITIONS_PER_MONTH]),
        "min_trades_per_month": min(trades_by_month.values()) if trades_by_month else 0,
        "finalized_trades": len([trade for trade in trades if trade.exit_status == "final"]),
        "as_of_latest_trades": len([trade for trade in trades if trade.exit_status != "final"]),
        "win_rate": round(len([value for value in returns if value > 0]) / len(returns), 6) if returns else None,
        "avg_return_pct": round(sum(returns) / len(returns), 6) if returns else None,
        "total_pnl_amount": round(pnl, 2),
        "invested_amount": round(invested, 2),
        "portfolio_return_pct": round(pnl / invested, 6) if invested else None,
    }


def main() -> int:
    signal_rows = load_csv(SIGNAL_CSV)
    result_rows: list[dict[str, Any]] = []
    trades_by_pid: dict[str, list[Trade]] = {}
    price_cache: dict[str, list[dict[str, str]]] = {}
    has_eps_quality = any(parse_float(row.get("eps_quality_score")) is not None for row in signal_rows)
    eps_low_values = EPS_QUALITY_CLIP_LOW_VALUES if has_eps_quality else [None]
    eps_high_values = EPS_QUALITY_CLIP_HIGH_VALUES if has_eps_quality else [None]

    for min_avg_volume_5d in MIN_AVG_VOLUME_5D_VALUES:
        for breakout_days in PRICE_BREAKOUT_DAYS_VALUES:
            for min_institutional_net_buy in MIN_INSTITUTIONAL_NET_BUY_VALUES:
                for eps_low in eps_low_values:
                    for eps_high in eps_high_values:
                        if eps_low is not None and eps_high is not None and eps_low > eps_high:
                            continue
                        filtered = [
                            row for row in signal_rows
                            if passes_filter(row, min_avg_volume_5d, breakout_days, min_institutional_net_buy, eps_low, eps_high)
                        ]
                        selected = select_monthly(filtered)
                        for stop_loss in STOP_LOSS_VALUES:
                            for take_profit in TAKE_PROFIT_VALUES:
                                for exit_rule in EXIT_RULES:
                                    pid = parameter_id(
                                        min_avg_volume_5d,
                                        breakout_days,
                                        min_institutional_net_buy,
                                        eps_low,
                                        eps_high,
                                        stop_loss,
                                        take_profit,
                                        exit_rule,
                                    )
                                    parameter = {
                                        "parameter_id": pid,
                                        "min_avg_volume_5d": min_avg_volume_5d,
                                        "price_breakout_days": breakout_days,
                                        "min_institutional_net_buy": min_institutional_net_buy,
                                        "eps_quality_clip_low": eps_low,
                                        "eps_quality_clip_high": eps_high,
                                        "stop_loss": stop_loss,
                                        "take_profit": take_profit,
                                        "exit_rule": exit_rule,
                                    }
                                    trades = build_trades(pid, selected, exit_rule, stop_loss, take_profit, price_cache)
                                    trades_by_pid[pid] = trades
                                    result_rows.append(summarize(parameter, filtered, selected, trades))

    result_rows.sort(
        key=lambda row: (
            -row["full_trade_months"],
            -row["min_trades_per_month"],
            -(row["portfolio_return_pct"] if row["portfolio_return_pct"] is not None else -999),
            -row["trades"],
        )
    )
    best = result_rows[0] if result_rows else {}
    best_trades = trades_by_pid.get(str(best.get("parameter_id")), [])
    write_csv(RESULT_CSV, result_rows, list(result_rows[0].keys()) if result_rows else ["parameter_id"])
    write_csv(BEST_TRADES_CSV, [asdict(trade) for trade in best_trades], list(Trade.__dataclass_fields__.keys()))
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "signal_rows": len(signal_rows),
        "has_eps_quality": has_eps_quality,
        "parameter_sets": len(result_rows),
        "target_positions_per_month": TARGET_POSITIONS_PER_MONTH,
        "best": best,
        "outputs": {
            "result_csv": str(RESULT_CSV),
            "best_trades_csv": str(BEST_TRADES_CSV),
        },
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
