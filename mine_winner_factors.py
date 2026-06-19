from __future__ import annotations

import csv
import itertools
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "project_data" / "simple_monthly_revenue"
FULL_PRICE_DIR = PROJECT_ROOT / "project_data" / "full_market_prices" / "prices"
SIGNAL_CSV = DATA_DIR / "prepared_signal_universe.csv"
OUTPUT_DIR = DATA_DIR / "winner_factor_mining_full_market"

TARGET_WIN_RATE = 0.70
TARGET_AVG_RETURN = 0.30
TARGET_MONTHLY_AVG_RETURN = 0.70
TARGET_POSITIONS_PER_MONTH = 5
MIN_WINNERS_PER_MONTH = 5
MAX_WINNERS_PER_MONTH = 100
BASE_WINNER_POOL_TOP_N = None
MAX_FEATURE_COMBO_SIZE = 8
TOP_FEATURES_TO_KEEP = 12


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


def load_prices(path: Path) -> list[dict[str, str]]:
    return load_csv(path)


def price_by_date(prices: list[dict[str, str]], trade_date: str) -> int | None:
    for idx, row in enumerate(prices):
        if row.get("trade_date") == trade_date:
            return idx
    return None


def simulate_exit(prices: list[dict[str, str]], entry_idx: int, exit_idx: int) -> tuple[str, float] | None:
    entry_price = parse_float(prices[entry_idx].get("open"))
    exit_price = parse_float(prices[exit_idx].get("close"))
    if entry_price is None or exit_price is None:
        return None
    return prices[exit_idx]["trade_date"], (exit_price - entry_price) / entry_price


def relative_return(prices: list[dict[str, str]], entry_idx: int, offset: int) -> float | None:
    target_idx = entry_idx + offset
    if target_idx >= len(prices):
        return None
    entry_price = parse_float(prices[entry_idx].get("open"))
    target_price = parse_float(prices[target_idx].get("close"))
    if entry_price is None or target_price is None or entry_price == 0:
        return None
    return (target_price - entry_price) / entry_price


def max_close_return(prices: list[dict[str, str]], entry_idx: int, lookahead: int) -> float | None:
    entry_price = parse_float(prices[entry_idx].get("open"))
    if entry_price is None or entry_price == 0:
        return None
    closes: list[float] = []
    for idx in range(entry_idx, min(len(prices), entry_idx + lookahead + 1)):
        close_price = parse_float(prices[idx].get("close"))
        if close_price is not None:
            closes.append(close_price)
    if not closes:
        return None
    return (max(closes) - entry_price) / entry_price


def maybe_monthly_return(prices: list[dict[str, str]], entry_idx: int, exit_rule: str) -> tuple[int, str] | None:
    entry_month = prices[entry_idx]["trade_date"][:7]
    if exit_rule == "month_end":
        idx = entry_idx
        for i in range(entry_idx, len(prices)):
            if prices[i]["trade_date"][:7] != entry_month:
                break
            idx = i
        return idx, "month_end"
    if exit_rule == "next_month_5":
        target_month = next_month(entry_month)
        indices = [i for i, row in enumerate(prices) if row["trade_date"][:7] == target_month]
        if len(indices) < 5:
            return None
        return indices[4], "next_month_5"
    if exit_rule == "next_month_10":
        target_month = next_month(entry_month)
        indices = [i for i, row in enumerate(prices) if row["trade_date"][:7] == target_month]
        if len(indices) < 10:
            return None
        return indices[9], "next_month_10"
    return None


def next_month(month: str) -> str:
    year = int(month[:4])
    mm = int(month[5:])
    if mm == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{mm + 1:02d}"


@dataclass
class Trade:
    stock_id: str
    company_name: str
    revenue_month: str
    announcement_date: str
    buy_date: str
    exit_date: str
    return_pct: float
    mom_pct: float | None
    yoy_pct: float | None
    institutional_total_net_buy_shares: float | None
    avg_volume_5d: float | None
    previous_volume_ratio_20d: float | None
    foreign_net_buy_shares: float | None
    investment_trust_net_buy_shares: float | None
    dealer_net_buy_shares: float | None
    breakout_20d: bool
    breakout_60d: bool
    breakout_120d: bool
    breakout_240d: bool
    day1_return_pct: float | None
    day3_return_pct: float | None
    day5_return_pct: float | None
    max_close_10d_return_pct: float | None


def build_trade(row: dict[str, str], exit_rule: str = "month_end") -> Trade | None:
    price_file = Path(row["price_file"])
    if not price_file.exists():
        return None
    prices = load_prices(price_file)
    entry_idx = price_by_date(prices, row["buy_date"])
    if entry_idx is None:
        return None
    exit_info = maybe_monthly_return(prices, entry_idx, exit_rule)
    if exit_info is None:
        return None
    exit_idx, _ = exit_info
    exit_trade = simulate_exit(prices, entry_idx, exit_idx)
    if exit_trade is None:
        return None
    exit_date, return_pct = exit_trade
    return Trade(
        stock_id=row["stock_id"],
        company_name=row["company_name"],
        revenue_month=row["revenue_month"],
        announcement_date=row["announcement_date"],
        buy_date=row["buy_date"],
        exit_date=exit_date,
        return_pct=return_pct,
        mom_pct=parse_float(row.get("mom_pct")),
        yoy_pct=parse_float(row.get("yoy_pct")),
        institutional_total_net_buy_shares=parse_float(row.get("institutional_total_net_buy_shares")),
        avg_volume_5d=parse_float(row.get("avg_volume_5d")),
        previous_volume_ratio_20d=parse_float(row.get("previous_volume_ratio_20d")),
        foreign_net_buy_shares=parse_float(row.get("foreign_net_buy_shares")),
        investment_trust_net_buy_shares=parse_float(row.get("investment_trust_net_buy_shares")),
        dealer_net_buy_shares=parse_float(row.get("dealer_net_buy_shares")),
        breakout_20d=parse_bool(row.get("breakout_20d")),
        breakout_60d=parse_bool(row.get("breakout_60d")),
        breakout_120d=parse_bool(row.get("breakout_120d")),
        breakout_240d=parse_bool(row.get("breakout_240d")),
        day1_return_pct=relative_return(prices, entry_idx, 1),
        day3_return_pct=relative_return(prices, entry_idx, 3),
        day5_return_pct=relative_return(prices, entry_idx, 5),
        max_close_10d_return_pct=max_close_return(prices, entry_idx, 10),
    )


def resolve_price_file(row: dict[str, str]) -> Path:
    full_market_file = FULL_PRICE_DIR / f"{row['stock_id']}.csv"
    if full_market_file.exists():
        return full_market_file
    return Path(row.get("price_file") or "")


def build_trade(row: dict[str, str], exit_rule: str = "month_end") -> Trade | None:
    price_file = resolve_price_file(row)
    if not price_file.exists():
        return None
    prices = load_prices(price_file)
    entry_date = row.get("buy_date") or ""
    entry_idx = price_by_date(prices, entry_date)
    if entry_idx is None:
        return None
    exit_info = maybe_monthly_return(prices, entry_idx, exit_rule)
    if exit_info is None:
        return None
    exit_idx, _ = exit_info
    exit_trade = simulate_exit(prices, entry_idx, exit_idx)
    if exit_trade is None:
        return None
    exit_date, return_pct = exit_trade
    return Trade(
        stock_id=row["stock_id"],
        company_name=row["company_name"],
        revenue_month=row["revenue_month"],
        announcement_date=row["announcement_date"],
        buy_date=prices[entry_idx]["trade_date"],
        exit_date=exit_date,
        return_pct=return_pct,
        mom_pct=parse_float(row.get("mom_pct")),
        yoy_pct=parse_float(row.get("yoy_pct")),
        institutional_total_net_buy_shares=parse_float(row.get("institutional_total_net_buy_shares")),
        avg_volume_5d=parse_float(row.get("avg_volume_5d")),
        previous_volume_ratio_20d=parse_float(row.get("previous_volume_ratio_20d")),
        foreign_net_buy_shares=parse_float(row.get("foreign_net_buy_shares")),
        investment_trust_net_buy_shares=parse_float(row.get("investment_trust_net_buy_shares")),
        dealer_net_buy_shares=parse_float(row.get("dealer_net_buy_shares")),
        breakout_20d=parse_bool(row.get("breakout_20d")),
        breakout_60d=parse_bool(row.get("breakout_60d")),
        breakout_120d=parse_bool(row.get("breakout_120d")),
        breakout_240d=parse_bool(row.get("breakout_240d")),
        day1_return_pct=relative_return(prices, entry_idx, 1),
        day3_return_pct=relative_return(prices, entry_idx, 3),
        day5_return_pct=relative_return(prices, entry_idx, 5),
        max_close_10d_return_pct=max_close_return(prices, entry_idx, 10),
    )


def base_candidates(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    eligible = []
    for row in rows:
        mom = parse_float(row.get("mom_pct"))
        yoy = parse_float(row.get("yoy_pct"))
        if mom is None or yoy is None:
            continue
        if mom <= 0 or yoy <= 0:
            continue
        eligible.append(row)
    eligible.sort(
        key=lambda row: (
            -(parse_float(row.get("yoy_pct")) or 0.0),
            -(parse_float(row.get("mom_pct")) or 0.0),
            -(parse_float(row.get("institutional_total_net_buy_shares")) or 0.0),
            -(parse_float(row.get("avg_volume_5d")) or 0.0),
            row["stock_id"],
        )
    )
    return eligible


def month_winners(rows: list[dict[str, str]], top_n: int | None = BASE_WINNER_POOL_TOP_N) -> list[dict[str, str]]:
    by_month: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_month[row["revenue_month"]].append(row)
    winners: list[dict[str, str]] = []
    for month, month_rows in sorted(by_month.items()):
        month_rows.sort(
            key=lambda row: (
                -(parse_float(row.get("mom_pct")) or 0.0),
                -(parse_float(row.get("yoy_pct")) or 0.0),
                -(parse_float(row.get("institutional_total_net_buy_shares")) or 0.0),
                -(parse_float(row.get("avg_volume_5d")) or 0.0),
                row["stock_id"],
            )
        )
        winners.extend(month_rows if top_n is None else month_rows[:top_n])
    return winners


def add_signal_features(row: dict[str, str]) -> dict[str, Any]:
    return {
        "stock_id": row["stock_id"],
        "company_name": row["company_name"],
        "revenue_month": row["revenue_month"],
        "announcement_date": row["announcement_date"],
        "buy_date": row["buy_date"],
        "mom_positive": (parse_float(row.get("mom_pct")) or 0.0) > 0,
        "yoy_positive": (parse_float(row.get("yoy_pct")) or 0.0) > 0,
        "mom_gt_10": (parse_float(row.get("mom_pct")) or 0.0) >= 0.10,
        "mom_gt_20": (parse_float(row.get("mom_pct")) or 0.0) >= 0.20,
        "yoy_gt_20": (parse_float(row.get("yoy_pct")) or 0.0) >= 0.20,
        "yoy_gt_30": (parse_float(row.get("yoy_pct")) or 0.0) >= 0.30,
        "inst_buy_positive": (parse_float(row.get("institutional_total_net_buy_shares")) or 0.0) > 0,
        "inst_buy_gt_100k": (parse_float(row.get("institutional_total_net_buy_shares")) or 0.0) >= 100_000,
        "inst_buy_gt_300k": (parse_float(row.get("institutional_total_net_buy_shares")) or 0.0) >= 300_000,
        "inst_buy_gt_500k": (parse_float(row.get("institutional_total_net_buy_shares")) or 0.0) >= 500_000,
        "foreign_buy_positive": (parse_float(row.get("foreign_net_buy_shares")) or 0.0) > 0,
        "foreign_buy_gt_100k": (parse_float(row.get("foreign_net_buy_shares")) or 0.0) >= 100_000,
        "foreign_buy_gt_300k": (parse_float(row.get("foreign_net_buy_shares")) or 0.0) >= 300_000,
        "trust_buy_positive": (parse_float(row.get("investment_trust_net_buy_shares")) or 0.0) > 0,
        "trust_buy_gt_50k": (parse_float(row.get("investment_trust_net_buy_shares")) or 0.0) >= 50_000,
        "dealer_buy_positive": (parse_float(row.get("dealer_net_buy_shares")) or 0.0) > 0,
        "avg_volume_5d_gt_100k": (parse_float(row.get("avg_volume_5d")) or 0.0) >= 100_000,
        "avg_volume_5d_gt_300k": (parse_float(row.get("avg_volume_5d")) or 0.0) >= 300_000,
        "avg_volume_5d_gt_1m": (parse_float(row.get("avg_volume_5d")) or 0.0) >= 1_000_000,
        "prev_vol_ratio_gt_1": (parse_float(row.get("previous_volume_ratio_20d")) or 0.0) >= 1.0,
        "prev_vol_ratio_gt_1_5": (parse_float(row.get("previous_volume_ratio_20d")) or 0.0) >= 1.5,
        "day1_return_gt_3": (parse_float(row.get("day1_return_pct")) or 0.0) >= 0.03,
        "day3_return_gt_5": (parse_float(row.get("day3_return_pct")) or 0.0) >= 0.05,
        "day5_return_gt_10": (parse_float(row.get("day5_return_pct")) or 0.0) >= 0.10,
        "max_close_10d_gt_20": (parse_float(row.get("max_close_10d_return_pct")) or 0.0) >= 0.20,
        "breakout_20d": parse_bool(row.get("breakout_20d")),
        "breakout_60d": parse_bool(row.get("breakout_60d")),
        "breakout_120d": parse_bool(row.get("breakout_120d")),
        "breakout_240d": parse_bool(row.get("breakout_240d")),
    }


def feature_names() -> list[str]:
    return [
        "mom_positive",
        "yoy_positive",
        "mom_gt_10",
        "mom_gt_20",
        "yoy_gt_20",
        "yoy_gt_30",
        "inst_buy_positive",
        "inst_buy_gt_100k",
        "inst_buy_gt_300k",
        "inst_buy_gt_500k",
        "foreign_buy_positive",
        "foreign_buy_gt_100k",
        "foreign_buy_gt_300k",
        "trust_buy_positive",
        "trust_buy_gt_50k",
        "dealer_buy_positive",
        "avg_volume_5d_gt_100k",
        "avg_volume_5d_gt_300k",
        "avg_volume_5d_gt_1m",
        "prev_vol_ratio_gt_1",
        "prev_vol_ratio_gt_1_5",
        "day1_return_gt_3",
        "day3_return_gt_5",
        "day5_return_gt_10",
        "max_close_10d_gt_20",
        "breakout_20d",
        "breakout_60d",
        "breakout_120d",
        "breakout_240d",
    ]


def evaluate_combo(trades: list[dict[str, Any]], combo: tuple[str, ...]) -> dict[str, Any]:
    selected = [trade for trade in trades if all(trade.get(name) for name in combo)]
    if not selected:
        return {
            "combo": ",".join(combo),
            "trades": 0,
            "months": 0,
            "win_rate": 0.0,
            "avg_return_pct": 0.0,
            "median_return_pct": 0.0,
            "monthly_avg_return_pct": 0.0,
            "hit_goal": False,
        }
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in selected:
        by_month[trade["revenue_month"]].append(trade)
    month_returns = []
    for month, month_trades in by_month.items():
        month_returns.append(mean(t["return_pct"] for t in month_trades))
    win_rate = sum(1 for trade in selected if trade["return_pct"] > 0) / len(selected)
    avg_return = mean(trade["return_pct"] for trade in selected)
    monthly_avg_return = mean(month_returns) if month_returns else 0.0
    return {
        "combo": ",".join(combo),
        "trades": len(selected),
        "months": len(by_month),
        "win_rate": round(win_rate, 6),
        "avg_return_pct": round(avg_return, 6),
        "median_return_pct": round(sorted(t["return_pct"] for t in selected)[len(selected) // 2], 6),
        "monthly_avg_return_pct": round(monthly_avg_return, 6),
        "hit_goal": bool(
            (win_rate >= TARGET_WIN_RATE and avg_return >= TARGET_AVG_RETURN)
            or monthly_avg_return >= TARGET_MONTHLY_AVG_RETURN
        ),
    }


def mine_combos(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = feature_names()
    single_scores = []
    for name in names:
        result = evaluate_combo(trades, (name,))
        if result["trades"] >= TARGET_POSITIONS_PER_MONTH:
            single_scores.append(result)
    single_scores.sort(key=lambda row: (-row["monthly_avg_return_pct"], -row["avg_return_pct"], -row["win_rate"], -row["trades"]))
    kept_names = [row["combo"] for row in single_scores[:TOP_FEATURES_TO_KEEP]]
    if not kept_names:
        kept_names = names

    results: list[dict[str, Any]] = []
    for r in range(1, min(MAX_FEATURE_COMBO_SIZE, len(kept_names)) + 1):
        for combo in itertools.combinations(kept_names, r):
            result = evaluate_combo(trades, combo)
            if result["trades"] >= TARGET_POSITIONS_PER_MONTH:
                results.append(result)
                if result["hit_goal"]:
                    return sorted(results, key=lambda row: (-row["hit_goal"], -row["monthly_avg_return_pct"], -row["avg_return_pct"], -row["win_rate"], -row["trades"]))
    return sorted(results, key=lambda row: (-row["hit_goal"], -row["monthly_avg_return_pct"], -row["avg_return_pct"], -row["win_rate"], -row["trades"]))


def main() -> None:
    rows = load_csv(SIGNAL_CSV)
    if not rows:
        raise SystemExit(f"Missing signal file: {SIGNAL_CSV}")

    eligible = base_candidates(rows)
    winners = month_winners(eligible, top_n=None)

    trades: list[dict[str, Any]] = []
    for row in winners:
        built = build_trade(row)
        if built is None:
            continue
        feature_row = add_signal_features(row)
        feature_row.update(
            {
                "return_pct": round(built.return_pct, 6),
                "mom_pct": built.mom_pct,
                "yoy_pct": built.yoy_pct,
                "institutional_total_net_buy_shares": built.institutional_total_net_buy_shares,
                "avg_volume_5d": built.avg_volume_5d,
                "previous_volume_ratio_20d": built.previous_volume_ratio_20d,
                "foreign_net_buy_shares": built.foreign_net_buy_shares,
                "investment_trust_net_buy_shares": built.investment_trust_net_buy_shares,
                "dealer_net_buy_shares": built.dealer_net_buy_shares,
                "breakout_20d": built.breakout_20d,
                "breakout_60d": built.breakout_60d,
                "breakout_120d": built.breakout_120d,
                "breakout_240d": built.breakout_240d,
                "day1_return_pct": built.day1_return_pct,
                "day3_return_pct": built.day3_return_pct,
                "day5_return_pct": built.day5_return_pct,
                "max_close_10d_return_pct": built.max_close_10d_return_pct,
                "exit_date": built.exit_date,
            }
        )
        trades.append(feature_row)

    combos = mine_combos(trades)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(OUTPUT_DIR / "winner_trades.csv", trades, list(trades[0].keys()) if trades else [])
    write_csv(OUTPUT_DIR / "winner_factor_results.csv", combos, list(combos[0].keys()) if combos else ["combo"])

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "signal_rows": len(rows),
        "eligible_rows": len(eligible),
        "winner_rows": len(winners),
        "trade_rows": len(trades),
        "targets": {
            "win_rate": TARGET_WIN_RATE,
            "avg_return_pct": TARGET_AVG_RETURN,
            "monthly_avg_return_pct": TARGET_MONTHLY_AVG_RETURN,
        },
        "best_combo": combos[0] if combos else None,
        "stopped_early": bool(combos and combos[0].get("hit_goal")),
    }
    with (OUTPUT_DIR / "winner_factor_summary.json").open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
