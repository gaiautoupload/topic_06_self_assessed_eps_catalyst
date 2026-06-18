from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_DIR = PROJECT_DIR / "project_data" / "2026_h1"
LOCAL_PRICES_DIR = LOCAL_DIR / "prices"
HOLDING_WINDOWS = (5, 10, 20)


@dataclass
class PositionTrade:
    month: str
    stock_id: str
    company_name: str
    event_id: str
    strategy_bucket: str
    allocation_amount: float
    holding_days: int
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    return_pct: float
    pnl_amount: float


@dataclass
class MarkedPosition:
    month: str
    stock_id: str
    company_name: str
    event_id: str
    strategy_bucket: str
    allocation_amount: float
    entry_date: str
    entry_price: float
    latest_date: str
    latest_price: float
    marked_return_pct: float
    marked_pnl_amount: float


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def parse_float(value: str) -> Optional[float]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_price_rows(stock_id: str) -> list[dict[str, str]]:
    price_path = LOCAL_PRICES_DIR / f"{stock_id}.csv"
    if not price_path.exists():
        return []
    return load_csv(price_path)


def load_event_time_map() -> dict[str, str]:
    path = LOCAL_DIR / "main_strategy_events.csv"
    rows = load_csv(path)
    return {row["event_id"]: row.get("announcement_time", "") for row in rows}


def find_index(prices: list[dict[str, str]], date_text: str, strictly_after: bool = False) -> Optional[int]:
    for idx, row in enumerate(prices):
        if strictly_after:
            if row["trade_date"] > date_text:
                return idx
        elif row["trade_date"] >= date_text:
            return idx
    return None


def build_trade(selection: dict[str, str], prices: list[dict[str, str]], holding_days: int, announcement_time: str) -> Optional[PositionTrade]:
    after_close = announcement_time >= "13:30:00" if announcement_time else False
    entry_idx = find_index(prices, selection["announcement_date"], strictly_after=after_close)
    if entry_idx is None:
        return None
    exit_idx = entry_idx + holding_days
    if exit_idx >= len(prices):
        return None

    entry_row = prices[entry_idx]
    exit_row = prices[exit_idx]
    entry_price = parse_float(entry_row["open"])
    exit_price = parse_float(exit_row["close"])
    allocation = parse_float(selection["allocation_amount"])
    if entry_price is None or exit_price is None or allocation is None or entry_price == 0:
        return None

    return_pct = round((exit_price - entry_price) / entry_price, 6)
    pnl_amount = round(allocation * return_pct, 2)

    return PositionTrade(
        month=selection["month"],
        stock_id=selection["stock_id"],
        company_name=selection["company_name"],
        event_id=selection["event_id"],
        strategy_bucket=selection["strategy_bucket"],
        allocation_amount=allocation,
        holding_days=holding_days,
        entry_date=entry_row["trade_date"],
        entry_price=entry_price,
        exit_date=exit_row["trade_date"],
        exit_price=exit_price,
        return_pct=return_pct,
        pnl_amount=pnl_amount,
    )


def build_marked_position(selection: dict[str, str], prices: list[dict[str, str]], announcement_time: str) -> Optional[MarkedPosition]:
    after_close = announcement_time >= "13:30:00" if announcement_time else False
    entry_idx = find_index(prices, selection["announcement_date"], strictly_after=after_close)
    if entry_idx is None:
        return None
    entry_row = prices[entry_idx]
    latest_row = prices[-1]
    entry_price = parse_float(entry_row["open"])
    latest_price = parse_float(latest_row["close"])
    allocation = parse_float(selection["allocation_amount"])
    if entry_price is None or latest_price is None or allocation is None or entry_price == 0:
        return None
    marked_return_pct = round((latest_price - entry_price) / entry_price, 6)
    marked_pnl_amount = round(allocation * marked_return_pct, 2)
    return MarkedPosition(
        month=selection["month"],
        stock_id=selection["stock_id"],
        company_name=selection["company_name"],
        event_id=selection["event_id"],
        strategy_bucket=selection["strategy_bucket"],
        allocation_amount=allocation,
        entry_date=entry_row["trade_date"],
        entry_price=entry_price,
        latest_date=latest_row["trade_date"],
        latest_price=latest_price,
        marked_return_pct=marked_return_pct,
        marked_pnl_amount=marked_pnl_amount,
    )


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    selections = load_csv(LOCAL_DIR / "monthly_portfolio.csv")
    event_time_map = load_event_time_map()

    trades: list[PositionTrade] = []
    marked_positions: list[MarkedPosition] = []
    skipped: list[dict[str, str]] = []

    for selection in selections:
        prices = load_price_rows(selection["stock_id"])
        if not prices:
            skipped.append(
                {
                    "month": selection["month"],
                    "stock_id": selection["stock_id"],
                    "event_id": selection["event_id"],
                    "reason": "missing_local_price_file",
                }
            )
            continue

        announcement_time = event_time_map.get(selection["event_id"], "")
        marked = build_marked_position(selection, prices, announcement_time)
        if marked is not None:
            marked_positions.append(marked)

        for holding_days in HOLDING_WINDOWS:
            trade = build_trade(selection, prices, holding_days, announcement_time)
            if trade is None:
                skipped.append(
                    {
                        "month": selection["month"],
                        "stock_id": selection["stock_id"],
                        "event_id": selection["event_id"],
                        "reason": f"cannot_build_t{holding_days}",
                    }
                )
                continue
            trades.append(trade)

    out_dir = LOCAL_DIR
    trade_rows = [asdict(row) for row in trades]
    write_csv(
        out_dir / "backtest_trades.csv",
        list(trade_rows[0].keys()) if trade_rows else list(PositionTrade.__dataclass_fields__.keys()),
        trade_rows,
    )
    write_csv(
        out_dir / "backtest_skipped.csv",
        ["month", "stock_id", "event_id", "reason"],
        skipped,
    )
    marked_rows = [asdict(row) for row in marked_positions]
    write_csv(
        out_dir / "backtest_marked_positions.csv",
        list(marked_rows[0].keys()) if marked_rows else list(MarkedPosition.__dataclass_fields__.keys()),
        marked_rows,
    )

    month_window_summary: dict[str, dict[str, dict[str, float | int]]] = {}
    for row in trades:
        month_bucket = month_window_summary.setdefault(row.month, {})
        window_key = f"T{row.holding_days}"
        window_bucket = month_bucket.setdefault(window_key, {"positions": 0, "pnl_amount": 0.0, "avg_return_pct": 0.0})
        window_bucket["positions"] += 1
        window_bucket["pnl_amount"] += row.pnl_amount

    for row in trades:
        bucket = month_window_summary[row.month][f"T{row.holding_days}"]
        bucket.setdefault("_returns", [])
        bucket["_returns"].append(row.return_pct)

    for month, windows in month_window_summary.items():
        for window_key, bucket in windows.items():
            returns = bucket.pop("_returns", [])
            bucket["avg_return_pct"] = round(sum(returns) / len(returns), 6) if returns else 0.0
            bucket["pnl_amount"] = round(bucket["pnl_amount"], 2)

    marked_returns = [row.marked_return_pct for row in marked_positions]
    marked_wins = [value for value in marked_returns if value > 0]

    summary = {
        "portfolio_rows": len(selections),
        "trades": len(trades),
        "marked_positions": len(marked_positions),
        "skipped": len(skipped),
        "holding_windows": list(HOLDING_WINDOWS),
        "months": month_window_summary,
        "marked_summary": {
            "avg_return_pct": round(sum(marked_returns) / len(marked_returns), 6) if marked_returns else None,
            "win_rate": round(len(marked_wins) / len(marked_returns), 6) if marked_returns else None,
            "total_pnl_amount": round(sum(row.marked_pnl_amount for row in marked_positions), 2) if marked_positions else 0.0,
            "latest_date": max((row.latest_date for row in marked_positions), default=None),
        },
        "trade_csv": str(out_dir / "backtest_trades.csv"),
        "marked_csv": str(out_dir / "backtest_marked_positions.csv"),
        "skipped_csv": str(out_dir / "backtest_skipped.csv"),
    }
    with (out_dir / "backtest_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
