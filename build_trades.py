from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


ROOT = Path(r"D:\dataset")
DEFAULT_SNAPSHOTS = Path(__file__).resolve().parent / "output" / "valuation_snapshot.csv"
DEFAULT_PRICES_DIR = ROOT / "processed" / "prices"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
HOLDING_WINDOWS = (5, 10, 20)


@dataclass
class TradeRow:
    trade_id: str
    event_id: str
    stock_id: str
    strategy_tag: str
    signal_strength: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    holding_days: int
    return_pct: float
    exit_reason: str


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


def load_price_index(stock_id: str, prices_dir: Path) -> list[dict[str, str]]:
    price_path = prices_dir / f"{stock_id}.csv"
    if not price_path.exists():
        return []
    return load_csv(price_path)


def find_trade(prices: list[dict[str, str]], entry_date: str, holding_days: int) -> Optional[TradeRow]:
    entry_idx = next((idx for idx, row in enumerate(prices) if row["trade_date"] == entry_date), None)
    if entry_idx is None:
        return None
    exit_idx = entry_idx + holding_days
    if exit_idx >= len(prices):
        return None

    entry_row = prices[entry_idx]
    exit_row = prices[exit_idx]
    entry_price = parse_float(entry_row["close"])
    exit_price = parse_float(exit_row["close"])
    if entry_price is None or exit_price is None or entry_price == 0:
        return None

    return_pct = round((exit_price - entry_price) / entry_price, 6)
    return TradeRow(
        trade_id="",
        event_id="",
        stock_id="",
        strategy_tag=f"hold_{holding_days}",
        signal_strength="",
        entry_date=entry_row["trade_date"],
        entry_price=entry_price,
        exit_date=exit_row["trade_date"],
        exit_price=exit_price,
        holding_days=holding_days,
        return_pct=return_pct,
        exit_reason=f"T+{holding_days}",
    )


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build fixed-horizon trades for topic 06.")
    parser.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPSHOTS)
    parser.add_argument("--prices-dir", type=Path, default=DEFAULT_PRICES_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    snapshots = load_csv(args.snapshots)
    trades: list[TradeRow] = []
    skipped: list[dict[str, str]] = []

    for snapshot in snapshots:
        stock_id = snapshot["stock_id"]
        entry_date = snapshot["entry_date"]
        prices = load_price_index(stock_id, args.prices_dir)
        if not prices:
            skipped.append({"event_id": snapshot["event_id"], "stock_id": stock_id, "reason": "missing_price_file"})
            continue

        for holding_days in HOLDING_WINDOWS:
            trade = find_trade(prices, entry_date, holding_days)
            if trade is None:
                skipped.append(
                    {
                        "event_id": snapshot["event_id"],
                        "stock_id": stock_id,
                        "reason": f"cannot_build_t{holding_days}",
                    }
                )
                continue
            trade.trade_id = f"{snapshot['event_id']}_T{holding_days}"
            trade.event_id = snapshot["event_id"]
            trade.stock_id = stock_id
            trade.signal_strength = snapshot["signal_strength"]
            trades.append(trade)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    trade_rows = [asdict(row) for row in trades]
    write_csv(
        output_dir / "trades.csv",
        list(trade_rows[0].keys()) if trade_rows else [
            "trade_id", "event_id", "stock_id", "strategy_tag", "signal_strength",
            "entry_date", "entry_price", "exit_date", "exit_price", "holding_days",
            "return_pct", "exit_reason"
        ],
        trade_rows,
    )
    write_csv(
        output_dir / "trades_skipped.csv",
        ["event_id", "stock_id", "reason"],
        skipped,
    )

    summary = {
        "snapshots": len(snapshots),
        "trades": len(trades),
        "skipped": len(skipped),
        "windows": list(HOLDING_WINDOWS),
        "trade_csv": str(output_dir / "trades.csv"),
        "skipped_csv": str(output_dir / "trades_skipped.csv"),
    }
    with (output_dir / "trades_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
