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
DATA_DIR = PROJECT_ROOT / "project_data" / "simple_monthly_revenue" / "winner_factor_mining"
TRADES_CSV = DATA_DIR / "winner_trades.csv"
OUTPUT_CSV = DATA_DIR / "score_strategy_results.csv"
SUMMARY_JSON = DATA_DIR / "score_strategy_summary.json"

TARGET_POSITIONS_PER_MONTH = 5
MIN_TRADES_PER_MONTH = 5
MAX_SCORE_THRESHOLD = 8.0
SCORE_STEP = 0.5


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


FEATURE_GROUPS = {
    "chip": {
        "trust_buy_positive": 2.2,
        "trust_buy_gt_50k": 1.0,
        "foreign_buy_positive": 1.8,
        "foreign_buy_gt_100k": 2.0,
        "inst_buy_positive": 1.2,
        "inst_buy_gt_100k": 1.6,
        "inst_buy_gt_300k": 2.0,
    },
    "tech": {
        "avg_volume_5d_gt_100k": 1.0,
        "avg_volume_5d_gt_300k": 1.4,
        "avg_volume_5d_gt_1m": 1.9,
        "prev_vol_ratio_gt_1": 0.8,
        "prev_vol_ratio_gt_1_5": 1.8,
        "breakout_20d": 1.0,
        "breakout_60d": 1.4,
        "breakout_120d": 1.8,
        "breakout_240d": 1.0,
        "day1_return_gt_3": 0.8,
        "day3_return_gt_5": 1.2,
        "day5_return_gt_10": 1.8,
        "max_close_10d_gt_20": 2.0,
    },
    "fundamental": {
        "mom_gt_10": 0.6,
        "mom_gt_20": 1.0,
        "yoy_gt_20": 1.1,
        "yoy_gt_30": 1.5,
        "mom_positive": 0.2,
        "yoy_positive": 0.2,
    },
}


GROUP_TUNES = [
    {"chip": 1.0, "tech": 1.0, "fundamental": 1.0},
    {"chip": 1.2, "tech": 1.0, "fundamental": 0.8},
    {"chip": 1.0, "tech": 1.2, "fundamental": 0.8},
    {"chip": 1.2, "tech": 1.2, "fundamental": 0.7},
]


def score_trade(row: dict[str, str], tune: dict[str, float]) -> float:
    score = 0.0
    for group_name, features in FEATURE_GROUPS.items():
        group_weight = tune[group_name]
        for feature, weight in features.items():
            if str(row.get(feature)).strip().lower() == "true":
                score += weight * group_weight
    mom = parse_float(row.get("mom_pct")) or 0.0
    yoy = parse_float(row.get("yoy_pct")) or 0.0
    score += min(max(mom, 0.0), 1.0) * 0.6
    score += min(max(yoy, 0.0), 1.0) * 0.6
    score += min(max(parse_float(row.get("previous_volume_ratio_20d")) or 0.0, 0.0), 4.0) * 0.15
    return score


def top_n_per_month(rows: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_month[row["revenue_month"]].append(row)
    selected: list[dict[str, Any]] = []
    for month, month_rows in sorted(by_month.items()):
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
    min_month_trades = min(len(v) for v in by_month.values())
    return {
        "trades": len(selected),
        "months": len(by_month),
        "min_trades_per_month": min_month_trades,
        "win_rate": round(win_rate, 6),
        "avg_return_pct": round(avg_return, 6),
        "monthly_avg_return_pct": round(monthly_avg, 6),
    }


def main() -> None:
    rows = load_csv(TRADES_CSV)
    if not rows:
        raise SystemExit(f"Missing trades file: {TRADES_CSV}")

    scored_rows: list[dict[str, Any]] = []
    for tune_index, tune in enumerate(GROUP_TUNES):
        for row in rows:
            scored_rows.append(
                {
                    **row,
                    "tune_index": tune_index,
                    "score": round(score_trade(row, tune), 4),
                    "return_pct": parse_float(row.get("return_pct")) or 0.0,
                }
            )

    results: list[dict[str, Any]] = []
    for tune_index, tune in enumerate(GROUP_TUNES):
        tune_rows = [row for row in scored_rows if row["tune_index"] == tune_index]
        max_score = max(row["score"] for row in tune_rows)
        threshold = 0.0
        while threshold <= max_score:
            eligible = [row for row in tune_rows if row["score"] >= threshold]
            selected = top_n_per_month(eligible, TARGET_POSITIONS_PER_MONTH)
            metrics = evaluate(selected)
            if metrics and metrics["min_trades_per_month"] >= MIN_TRADES_PER_MONTH:
                result = {
                    "tune_index": tune_index,
                    "threshold": round(threshold, 2),
                    "chip_weight": tune["chip"],
                    "tech_weight": tune["tech"],
                    "fundamental_weight": tune["fundamental"],
                    **metrics,
                }
                result["objective"] = round(
                    (result["win_rate"] * 0.5)
                    + (result["avg_return_pct"] * 0.3)
                    + (result["monthly_avg_return_pct"] * 0.2),
                    6,
                )
                results.append(result)
            threshold += SCORE_STEP

    results.sort(
        key=lambda row: (
            -row["objective"],
            -row["win_rate"],
            -row["avg_return_pct"],
            -row["monthly_avg_return_pct"],
            -row["trades"],
        )
    )
    write_csv(OUTPUT_CSV, results, list(results[0].keys()) if results else [])
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "trades": len(rows),
        "tunes": GROUP_TUNES,
        "best": results[0] if results else None,
        "goal_hit": bool(results and results[0]["win_rate"] >= 0.70 and results[0]["avg_return_pct"] >= 0.30),
    }
    with SUMMARY_JSON.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
