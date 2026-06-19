from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "project_data" / "simple_monthly_revenue" / "winner_factor_mining"
TRADES_CSV = DATA_DIR / "winner_trades.csv"
FULL_BASE_CSV = PROJECT_ROOT / "project_data" / "full_market_base" / "full_market_base.csv"
OUTPUT_CSV = DATA_DIR / "score_strategy_results_value_aware.csv"
SUMMARY_JSON = DATA_DIR / "score_strategy_summary_value_aware.json"


@dataclass(frozen=True)
class SearchSpec:
    target_positions_per_month: int
    min_trades_per_month: int
    score_step: float
    chip_weight: float
    tech_weight: float
    fundamental_weight: float
    value_weight: float


FEATURE_GROUPS = {
    "chip": {
        "trust_buy_positive": 2.2,
        "trust_buy_gt_50k": 1.2,
        "foreign_buy_positive": 1.6,
        "foreign_buy_gt_100k": 2.2,
        "inst_buy_positive": 1.2,
        "inst_buy_gt_100k": 1.8,
        "inst_buy_gt_300k": 2.2,
    },
    "tech": {
        "avg_volume_5d_gt_100k": 1.0,
        "avg_volume_5d_gt_300k": 1.5,
        "avg_volume_5d_gt_1m": 2.0,
        "prev_vol_ratio_gt_1": 0.8,
        "prev_vol_ratio_gt_1_5": 2.0,
        "breakout_20d": 1.2,
        "breakout_60d": 1.5,
        "breakout_120d": 1.7,
        "breakout_240d": 1.1,
    },
    "fundamental": {
        "mom_positive": 0.3,
        "yoy_positive": 0.3,
        "mom_gt_10": 0.6,
        "mom_gt_20": 1.0,
        "yoy_gt_20": 1.0,
        "yoy_gt_30": 1.4,
        "turned_profit_from_loss": 1.8,
    },
}


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


def build_value_lookup() -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in load_csv(FULL_BASE_CSV):
        stock_id = row.get("stock_id", "")
        if stock_id:
            lookup[stock_id] = row
    return lookup


def score_trade(row: dict[str, str], weights: dict[str, float], value_row: dict[str, Any]) -> float:
    score = 0.0
    for group_name, features in FEATURE_GROUPS.items():
        group_weight = weights[group_name]
        for feature, base_weight in features.items():
            if str(row.get(feature)).strip().lower() == "true":
                score += base_weight * group_weight

    mom = parse_float(row.get("mom_pct")) or 0.0
    yoy = parse_float(row.get("yoy_pct")) or 0.0
    broker_score = parse_float(row.get("broker_score")) or 0.0
    pe_ratio = parse_float(value_row.get("pe_ratio")) if value_row else None
    pb_ratio = parse_float(value_row.get("pb_ratio")) if value_row else None
    dividend = parse_float(value_row.get("dividend_yield_pct")) if value_row else None

    score += min(max(mom, 0.0), 1.5) * 0.6
    score += min(max(yoy, 0.0), 1.5) * 0.6
    score += min(max(broker_score, 0.0), 3.0) * 0.4
    score += min(max(parse_float(row.get("previous_volume_ratio_20d")) or 0.0, 0.0), 5.0) * 0.2

    if pe_ratio is not None:
        score += max(0.0, 2.5 - min(pe_ratio, 50.0) / 20.0)
    if pb_ratio is not None:
        score += max(0.0, 1.8 - min(pb_ratio, 10.0) / 6.0)
    if dividend is not None:
        score += min(dividend / 3.0, 1.2)
    return score


def top_n_per_month(rows: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_month[row["revenue_month"]].append(row)
    selected: list[dict[str, Any]] = []
    for month_rows in by_month.values():
        month_rows.sort(key=lambda row: (-row["score"], -row["return_pct"], row["stock_id"]))
        selected.extend(month_rows[:n])
    return selected


def evaluate(selected: list[dict[str, Any]]) -> dict[str, Any]:
    if not selected:
        return {}
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in selected:
        by_month[trade["revenue_month"]].append(trade)
    win_rate = sum(1 for trade in selected if trade["return_pct"] > 0) / len(selected)
    avg_return = mean(trade["return_pct"] for trade in selected)
    monthly_avg = mean(mean(t["return_pct"] for t in month_trades) for month_trades in by_month.values())
    return {
        "trades": len(selected),
        "months": len(by_month),
        "min_trades_per_month": min(len(v) for v in by_month.values()),
        "win_rate": round(win_rate, 6),
        "avg_return_pct": round(avg_return, 6),
        "monthly_avg_return_pct": round(monthly_avg, 6),
    }


def main() -> None:
    rows = load_csv(TRADES_CSV)
    if not rows:
        raise SystemExit(f"Missing trades file: {TRADES_CSV}")
    value_lookup = build_value_lookup()

    search_specs = [
        SearchSpec(tp, mt, 0.5, chip, tech, fundamental, value)
        for tp in (5, 10, 15, 20)
        for mt in (4, 5)
        for chip, tech, fundamental, value in (
            (1.2, 1.0, 1.0, 0.8),
            (1.2, 1.2, 0.8, 1.0),
            (1.0, 1.0, 1.0, 1.2),
            (1.4, 1.2, 0.8, 1.0),
            (1.0, 1.2, 0.8, 1.4),
            (1.2, 1.0, 1.0, 1.4),
        )
    ]

    scored_rows: list[dict[str, Any]] = []
    for spec_index, spec in enumerate(search_specs):
        weights = {"chip": spec.chip_weight, "tech": spec.tech_weight, "fundamental": spec.fundamental_weight}
        for row in rows:
            value_row = value_lookup.get(row["stock_id"], {})
            scored_rows.append(
                {
                    **row,
                    "spec_index": spec_index,
                    "target_positions_per_month": spec.target_positions_per_month,
                    "min_trades_per_month": spec.min_trades_per_month,
                    "score_step": spec.score_step,
                    "score": round(score_trade(row, weights, value_row), 4),
                    "return_pct": parse_float(row.get("return_pct")) or 0.0,
                }
            )

    results: list[dict[str, Any]] = []
    for spec_index, spec in enumerate(search_specs):
        spec_rows = [row for row in scored_rows if row["spec_index"] == spec_index]
        max_score = max(row["score"] for row in spec_rows)
        threshold = 0.0
        while threshold <= max_score:
            eligible = [row for row in spec_rows if row["score"] >= threshold]
            selected = top_n_per_month(eligible, spec.target_positions_per_month)
            metrics = evaluate(selected)
            if metrics and metrics["min_trades_per_month"] >= spec.min_trades_per_month:
                result = {
                    "spec_index": spec_index,
                    "target_positions_per_month": spec.target_positions_per_month,
                    "min_trades_per_month": spec.min_trades_per_month,
                    "score_step": spec.score_step,
                    "chip_weight": spec.chip_weight,
                    "tech_weight": spec.tech_weight,
                    "fundamental_weight": spec.fundamental_weight,
                    "value_weight": spec.value_weight,
                    "threshold": round(threshold, 2),
                    **metrics,
                }
                result["objective"] = round(
                    (result["win_rate"] * 0.4)
                    + (result["avg_return_pct"] * 0.35)
                    + (result["monthly_avg_return_pct"] * 0.25),
                    6,
                )
                results.append(result)
            threshold += spec.score_step

    results.sort(key=lambda row: (-row["objective"], -row["win_rate"], -row["avg_return_pct"], -row["monthly_avg_return_pct"], -row["trades"]))
    write_csv(OUTPUT_CSV, results, list(results[0].keys()) if results else [])
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "trades": len(rows),
        "spec_count": len(search_specs),
        "best": results[0] if results else None,
        "goal_hit": bool(results and results[0]["win_rate"] >= 0.70 and results[0]["avg_return_pct"] >= 0.30),
    }
    with SUMMARY_JSON.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
