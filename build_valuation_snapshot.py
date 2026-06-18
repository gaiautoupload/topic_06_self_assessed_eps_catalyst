from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


ROOT = Path(r"D:\dataset")
DEFAULT_EVENTS = Path(__file__).resolve().parent / "output" / "events.csv"
DEFAULT_PRICES_DIR = ROOT / "processed" / "prices"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


@dataclass
class ValuationSnapshot:
    event_id: str
    stock_id: str
    company_name: str
    event_type: str
    signal_strength: str
    announcement_date: str
    announcement_time: str
    entry_date: str
    close: float
    eps_value: Optional[float]
    implied_pe: Optional[float]
    price_file_found: bool
    price_rows_scanned: int
    signal_reason: str


def parse_date(value: str) -> datetime.date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_float(value: str) -> Optional[float]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_events(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_price_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def find_entry_row(price_rows: list[dict[str, str]], announcement_date: str, announcement_time: str) -> Optional[dict[str, str]]:
    event_date = parse_date(announcement_date)
    after_close = bool(announcement_time) and announcement_time >= "13:30:00"

    for row in price_rows:
        trade_date = parse_date(row["trade_date"])
        if trade_date < event_date:
            continue
        if trade_date == event_date and after_close:
            continue
        return row
    return None


def calc_implied_pe(close: Optional[float], eps_value: Optional[float]) -> Optional[float]:
    if close is None or eps_value is None:
        return None
    if eps_value <= 0:
        return None
    return round(close / eps_value, 4)


def build_snapshot_row(event: dict[str, str], price_rows: list[dict[str, str]]) -> Optional[ValuationSnapshot]:
    entry_row = find_entry_row(
        price_rows=price_rows,
        announcement_date=event["announcement_date"],
        announcement_time=event["announcement_time"],
    )
    if entry_row is None:
        return None

    close = parse_float(entry_row["close"])
    eps_value = parse_float(event["eps_value"])
    implied_pe = calc_implied_pe(close, eps_value)
    signal_reason = "eps_available" if implied_pe is not None else "price_only_or_nonpositive_eps"

    return ValuationSnapshot(
        event_id=event["event_id"],
        stock_id=event["stock_id"],
        company_name=event["company_name"],
        event_type=event["event_type"],
        signal_strength=event["signal_strength"],
        announcement_date=event["announcement_date"],
        announcement_time=event["announcement_time"],
        entry_date=entry_row["trade_date"],
        close=close if close is not None else 0.0,
        eps_value=eps_value,
        implied_pe=implied_pe,
        price_file_found=True,
        price_rows_scanned=len(price_rows),
        signal_reason=signal_reason,
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

    parser = argparse.ArgumentParser(description="Build valuation snapshots for topic 06.")
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--prices-dir", type=Path, default=DEFAULT_PRICES_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    events = load_events(args.events)
    snapshots: list[ValuationSnapshot] = []
    missing_prices: list[dict[str, str]] = []

    for event in events:
        price_path = args.prices_dir / f"{event['stock_id']}.csv"
        if not price_path.exists():
            missing_prices.append(
                {
                    "event_id": event["event_id"],
                    "stock_id": event["stock_id"],
                    "announcement_date": event["announcement_date"],
                    "reason": "missing_price_file",
                }
            )
            continue

        price_rows = load_price_rows(price_path)
        snapshot = build_snapshot_row(event, price_rows)
        if snapshot is None:
            missing_prices.append(
                {
                    "event_id": event["event_id"],
                    "stock_id": event["stock_id"],
                    "announcement_date": event["announcement_date"],
                    "reason": "no_trade_date_on_or_after_event",
                }
            )
            continue
        snapshots.append(snapshot)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_rows = [asdict(row) for row in snapshots]
    missing_rows = missing_prices

    write_csv(
        output_dir / "valuation_snapshot.csv",
        list(snapshot_rows[0].keys()) if snapshot_rows else [
            "event_id", "stock_id", "company_name", "event_type", "signal_strength",
            "announcement_date", "announcement_time", "entry_date", "close",
            "eps_value", "implied_pe", "price_file_found", "price_rows_scanned", "signal_reason"
        ],
        snapshot_rows,
    )
    write_csv(
        output_dir / "valuation_missing_prices.csv",
        ["event_id", "stock_id", "announcement_date", "reason"],
        missing_rows,
    )

    summary = {
        "events": len(events),
        "snapshots": len(snapshots),
        "missing_prices": len(missing_prices),
        "coverage_ratio": round(len(snapshots) / len(events), 4) if events else 0.0,
        "events_with_implied_pe": sum(1 for row in snapshots if row.implied_pe is not None),
        "snapshot_csv": str(output_dir / "valuation_snapshot.csv"),
        "missing_price_csv": str(output_dir / "valuation_missing_prices.csv"),
    }
    with (output_dir / "valuation_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
