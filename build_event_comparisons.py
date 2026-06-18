from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


DEFAULT_EVENTS = Path(__file__).resolve().parent / "output" / "events.csv"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


@dataclass
class EventComparison:
    event_id: str
    stock_id: str
    announcement_date: str
    metric_kind: str
    metric_current: Optional[float]
    metric_prev: Optional[float]
    metric_yoy_base: Optional[float]
    prev_event_id: str
    yoy_event_id: str
    prev_delta: Optional[float]
    prev_pct: Optional[float]
    yoy_delta: Optional[float]
    yoy_pct: Optional[float]
    turned_profit_from_loss: bool
    turned_loss_from_profit: bool
    comparison_source: str
    strategy_bucket: str


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


def calc_delta(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None:
        return None
    return round(current - previous, 6)


def calc_pct(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / abs(previous), 6)


def detect_metric_kind(row: dict[str, str]) -> str:
    if parse_float(row.get("eps_value", "")) is not None:
        return "eps"
    if parse_float(row.get("profit_value", "")) is not None:
        return "profit"
    return "unknown"


def current_metric_value(row: dict[str, str], metric_kind: str) -> Optional[float]:
    if metric_kind == "eps":
        return parse_float(row.get("eps_value", ""))
    if metric_kind == "profit":
        return parse_float(row.get("profit_value", ""))
    return None


def choose_strategy_bucket(current: Optional[float], previous: Optional[float]) -> tuple[bool, bool, str]:
    turned_profit_from_loss = previous is not None and current is not None and previous < 0 < current
    turned_loss_from_profit = previous is not None and current is not None and previous > 0 > current
    if turned_profit_from_loss:
        return True, False, "turnaround_loss_to_profit"
    if turned_loss_from_profit:
        return False, True, "turnaround_profit_to_loss"
    return False, False, "topic_06_eps_catalyst"


def sort_key(row: dict[str, str]) -> tuple[str, str]:
    return (row["announcement_date"], row["announcement_time"])


def build_comparisons(events: list[dict[str, str]]) -> list[EventComparison]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in events:
        grouped.setdefault(row["stock_id"], []).append(row)

    results: list[EventComparison] = []
    for stock_id, stock_events in grouped.items():
        ordered = sorted(stock_events, key=sort_key)
        for idx, row in enumerate(ordered):
            metric_kind = detect_metric_kind(row)
            current = current_metric_value(row, metric_kind)

            previous_candidates = [
                prior for prior in ordered[:idx]
                if detect_metric_kind(prior) == metric_kind and current_metric_value(prior, metric_kind) is not None
            ]
            prev_row = previous_candidates[-1] if previous_candidates else None
            yoy_row = previous_candidates[-4] if len(previous_candidates) >= 4 else None

            prev_value = current_metric_value(prev_row, metric_kind) if prev_row else None
            yoy_value = current_metric_value(yoy_row, metric_kind) if yoy_row else None

            turned_profit_from_loss, turned_loss_from_profit, strategy_bucket = choose_strategy_bucket(current, prev_value)

            comparison_source = "sequential_same_stock"
            if yoy_row:
                comparison_source = "sequential_same_stock_with_yoy_proxy"

            results.append(
                EventComparison(
                    event_id=row["event_id"],
                    stock_id=stock_id,
                    announcement_date=row["announcement_date"],
                    metric_kind=metric_kind,
                    metric_current=current,
                    metric_prev=prev_value,
                    metric_yoy_base=yoy_value,
                    prev_event_id=prev_row["event_id"] if prev_row else "",
                    yoy_event_id=yoy_row["event_id"] if yoy_row else "",
                    prev_delta=calc_delta(current, prev_value),
                    prev_pct=calc_pct(current, prev_value),
                    yoy_delta=calc_delta(current, yoy_value),
                    yoy_pct=calc_pct(current, yoy_value),
                    turned_profit_from_loss=turned_profit_from_loss,
                    turned_loss_from_profit=turned_loss_from_profit,
                    comparison_source=comparison_source,
                    strategy_bucket=strategy_bucket,
                )
            )
    return sorted(results, key=lambda row: (row.announcement_date, row.stock_id, row.event_id))


def write_csv(path: Path, rows: list[EventComparison]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(rows[0]).keys()) if rows else list(EventComparison.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build comparison layer for topic 06 events.")
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    events = load_csv(args.events)
    comparisons = build_comparisons(events)

    output_dir = args.output_dir
    write_csv(output_dir / "event_comparisons.csv", comparisons)

    summary = {
        "events": len(events),
        "comparisons": len(comparisons),
        "with_prev": sum(1 for row in comparisons if row.metric_prev is not None),
        "with_yoy_proxy": sum(1 for row in comparisons if row.metric_yoy_base is not None),
        "turnaround_loss_to_profit": sum(1 for row in comparisons if row.turned_profit_from_loss),
        "turnaround_profit_to_loss": sum(1 for row in comparisons if row.turned_loss_from_profit),
        "comparison_csv": str(output_dir / "event_comparisons.csv"),
    }
    with (output_dir / "event_comparisons_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
