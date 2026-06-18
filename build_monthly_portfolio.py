from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_DIR = PROJECT_DIR / "project_data" / "2026_h1"

MONTHLY_CAPITAL = 1_000_000
TARGET_POSITIONS = 5
REBALANCE_DAY_HINT = "10-12"
ALLOWED_BUCKETS = {"topic_06_eps_catalyst", "turnaround_loss_to_profit"}


@dataclass
class MonthlyPortfolioRow:
    month: str
    stock_id: str
    company_name: str
    event_id: str
    announcement_date: str
    strategy_bucket: str
    allocation_amount: float
    selected_rank: int
    selected_count: int
    fill_rule: str


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def strategy_rank(bucket: str) -> int:
    if bucket == "turnaround_loss_to_profit":
        return 0
    if bucket == "topic_06_eps_catalyst":
        return 1
    return 9


def parse_float(value: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def score_row(row: dict[str, str]) -> tuple:
    eps_value = parse_float(row.get("eps_value", ""))
    has_compare = row.get("has_compare_context", "") == "True"
    return (
        strategy_rank(row.get("strategy_bucket", "")),
        0 if has_compare else 1,
        -(eps_value if eps_value is not None else -9999),
        row.get("announcement_date", ""),
        row.get("stock_id", ""),
    )


def month_key(date_text: str) -> str:
    return date_text[:7]


def main() -> int:
    rows = [
        row
        for row in load_csv(LOCAL_DIR / "main_strategy_events.csv")
        if row.get("strategy_bucket", "") in ALLOWED_BUCKETS
    ]
    by_month: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_month.setdefault(month_key(row["announcement_date"]), []).append(row)

    output_rows: list[MonthlyPortfolioRow] = []
    month_summary: dict[str, dict[str, object]] = {}

    for month, month_rows in sorted(by_month.items()):
        ordered = sorted(month_rows, key=score_row)
        if len(ordered) >= TARGET_POSITIONS:
            chosen = ordered[:TARGET_POSITIONS]
            allocation = MONTHLY_CAPITAL / TARGET_POSITIONS
            fill_rule = "top5_equal_200k"
        else:
            chosen = ordered
            allocation = MONTHLY_CAPITAL / len(chosen) if chosen else 0.0
            fill_rule = "rebalance_to_full_1m_after_10_12"

        for index, row in enumerate(chosen, start=1):
            output_rows.append(
                MonthlyPortfolioRow(
                    month=month,
                    stock_id=row["stock_id"],
                    company_name=row["company_name"],
                    event_id=row["event_id"],
                    announcement_date=row["announcement_date"],
                    strategy_bucket=row["strategy_bucket"],
                    allocation_amount=round(allocation, 2),
                    selected_rank=index,
                    selected_count=len(chosen),
                    fill_rule=fill_rule,
                )
            )

        month_summary[month] = {
            "candidate_events": len(month_rows),
            "selected_events": len(chosen),
            "allocation_per_event": round(allocation, 2),
            "allocated_capital": round(allocation * len(chosen), 2),
            "fill_rule": fill_rule,
        }

    out_csv = LOCAL_DIR / "monthly_portfolio.csv"
    with out_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        fieldnames = list(MonthlyPortfolioRow.__dataclass_fields__.keys())
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in output_rows:
            writer.writerow(asdict(row))

    summary = {
        "monthly_capital": MONTHLY_CAPITAL,
        "target_positions": TARGET_POSITIONS,
        "rebalance_day_hint": REBALANCE_DAY_HINT,
        "months": month_summary,
        "output_csv": str(out_csv),
    }
    with (LOCAL_DIR / "monthly_portfolio_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
