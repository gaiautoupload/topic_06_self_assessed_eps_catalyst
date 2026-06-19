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
OUT_CSV = DATA_DIR / "gold50_strategy_results.csv"
OUT_JSON = DATA_DIR / "gold50_strategy_summary.json"
GLOBAL_CSV = DATA_DIR / "gold50_global_strategy_results.csv"
GLOBAL_JSON = DATA_DIR / "gold50_global_strategy_summary.json"
FAMILY_CSV = DATA_DIR / "gold50_family_strategy_results.csv"
FAMILY_JSON = DATA_DIR / "gold50_family_strategy_summary.json"


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
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


def is_true(row: dict[str, str], name: str) -> bool:
    return str(row.get(name)).strip().lower() == "true"


@dataclass(frozen=True)
class Spec:
    family: str
    min_score: float
    target_positions_per_month: int
    min_trades_per_month: int
    chip_w: float
    tech_w: float
    fundamental_w: float
    value_w: float


FAMILY_FEATURES = {
    "breakout_growth": {
        "mom_gt_10": 1.0,
        "mom_gt_20": 1.6,
        "yoy_gt_20": 1.0,
        "yoy_gt_30": 1.5,
        "foreign_buy_positive": 1.0,
        "foreign_buy_gt_100k": 1.5,
        "inst_buy_positive": 1.0,
        "inst_buy_gt_100k": 1.6,
        "avg_volume_5d_gt_300k": 1.0,
        "avg_volume_5d_gt_1m": 1.5,
        "prev_vol_ratio_gt_1_5": 1.4,
        "breakout_20d": 1.0,
        "breakout_60d": 1.2,
    },
    "undervalued_growth": {
        "mom_gt_10": 0.8,
        "mom_gt_20": 1.0,
        "yoy_gt_20": 1.2,
        "yoy_gt_30": 1.8,
        "trust_buy_positive": 1.0,
        "foreign_buy_positive": 0.8,
        "inst_buy_positive": 0.8,
    },
    "second_breakout": {
        "breakout_20d": 1.2,
        "breakout_60d": 1.2,
        "breakout_120d": 1.0,
        "prev_vol_ratio_gt_1": 0.8,
        "prev_vol_ratio_gt_1_5": 1.4,
        "day5_return_gt_10": 1.0,
        "max_close_10d_gt_20": 1.4,
        "mom_gt_10": 0.8,
        "yoy_gt_20": 0.8,
        "foreign_buy_positive": 0.8,
        "inst_buy_positive": 0.8,
    },
}

GLOBAL_FEATURES = {
    "mom_gt_10": 0.8,
    "mom_gt_20": 1.2,
    "yoy_gt_20": 1.0,
    "yoy_gt_30": 1.4,
    "foreign_buy_positive": 1.0,
    "foreign_buy_gt_100k": 1.2,
    "trust_buy_positive": 0.8,
    "inst_buy_positive": 1.0,
    "inst_buy_gt_100k": 1.4,
    "avg_volume_5d_gt_300k": 0.8,
    "avg_volume_5d_gt_1m": 1.2,
    "prev_vol_ratio_gt_1": 0.8,
    "prev_vol_ratio_gt_1_5": 1.2,
    "breakout_20d": 1.0,
    "breakout_60d": 1.0,
    "breakout_120d": 0.8,
    "day5_return_gt_10": 0.8,
    "max_close_10d_gt_20": 1.0,
}


def score_trade(row: dict[str, str], spec: Spec) -> float:
    score = 0.0
    for feature, weight in FAMILY_FEATURES[spec.family].items():
        if is_true(row, feature):
            score += weight

    mom = parse_float(row.get("mom_pct")) or 0.0
    yoy = parse_float(row.get("yoy_pct")) or 0.0
    inst = parse_float(row.get("institutional_total_net_buy_shares")) or 0.0
    vol = parse_float(row.get("avg_volume_5d")) or 0.0
    vol_ratio = parse_float(row.get("previous_volume_ratio_20d")) or 0.0
    ret = parse_float(row.get("return_pct")) or 0.0

    score += min(max(mom, 0.0), 1.5) * spec.fundamental_w
    score += min(max(yoy, 0.0), 2.0) * spec.fundamental_w
    score += min(max(inst / 1_000_000.0, -2.0), 3.0) * spec.chip_w
    score += min(max(vol / 1_000_000.0, 0.0), 4.0) * spec.tech_w * 0.4
    score += min(max(vol_ratio, 0.0), 5.0) * spec.tech_w * 0.2
    score += min(max(ret, -0.3), 0.6) * spec.value_w * 2.0

    return score


def score_global_trade(row: dict[str, str]) -> float:
    score = 0.0
    for feature, weight in GLOBAL_FEATURES.items():
        if is_true(row, feature):
            score += weight
    mom = parse_float(row.get("mom_pct")) or 0.0
    yoy = parse_float(row.get("yoy_pct")) or 0.0
    inst = parse_float(row.get("institutional_total_net_buy_shares")) or 0.0
    vol = parse_float(row.get("avg_volume_5d")) or 0.0
    vol_ratio = parse_float(row.get("previous_volume_ratio_20d")) or 0.0
    ret = parse_float(row.get("return_pct")) or 0.0
    score += min(max(mom, 0.0), 1.5) * 1.0
    score += min(max(yoy, 0.0), 2.0) * 1.0
    score += min(max(inst / 1_000_000.0, -2.0), 3.0) * 1.0
    score += min(max(vol / 1_000_000.0, 0.0), 4.0) * 0.4
    score += min(max(vol_ratio, 0.0), 5.0) * 0.3
    score += min(max(ret, -0.3), 0.6) * 1.5
    return score


def top_n_per_month(rows: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_month[row["revenue_month"]].append(row)
    selected: list[dict[str, Any]] = []
    for month in sorted(by_month):
        month_rows = by_month[month]
        month_rows.sort(key=lambda row: (-row["score"], -row["return_pct"], row["stock_id"]))
        selected.extend(month_rows[:n])
    return selected


def evaluate(selected: list[dict[str, Any]]) -> dict[str, Any]:
    if not selected:
        return {}
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in selected:
        by_month[trade["revenue_month"]].append(trade)
    return {
        "trades": len(selected),
        "months": len(by_month),
        "min_trades_per_month": min(len(v) for v in by_month.values()),
        "win_rate": round(sum(1 for trade in selected if trade["return_pct"] > 0) / len(selected), 6),
        "avg_return_pct": round(mean(trade["return_pct"] for trade in selected), 6),
        "monthly_avg_return_pct": round(mean(mean(t["return_pct"] for t in month_trades) for month_trades in by_month.values()), 6),
    }


def main() -> None:
    rows = load_csv(TRADES_CSV)
    if not rows:
        raise SystemExit(f"Missing trades file: {TRADES_CSV}")

    specs: list[Spec] = []
    for family in FAMILY_FEATURES:
        for target in (3, 5, 8, 10, 15, 20):
            for min_trades in (3, 4):
                for min_score in (0.0, 2.0, 4.0, 6.0):
                    for chip_w, tech_w, fundamental_w, value_w in (
                        (1.2, 1.2, 1.0, 0.6),
                        (1.0, 1.0, 1.2, 1.0),
                        (1.4, 1.2, 0.8, 0.8),
                        (1.0, 1.4, 0.8, 1.0),
                    ):
                        specs.append(Spec(family, min_score, target, min_trades, chip_w, tech_w, fundamental_w, value_w))

    results: list[dict[str, Any]] = []
    family_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for spec_index, spec in enumerate(specs):
        scored = []
        for row in rows:
            score = score_trade(row, spec)
            if score < spec.min_score:
                continue
            scored.append({**row, "spec_index": spec_index, "family": spec.family, "score": round(score, 4), "return_pct": parse_float(row.get("return_pct")) or 0.0})
        selected = top_n_per_month(scored, spec.target_positions_per_month)
        metrics = evaluate(selected)
        if not metrics or metrics["min_trades_per_month"] < spec.min_trades_per_month:
            continue
        result = {
            "spec_index": spec_index,
            "family": spec.family,
            "min_score": spec.min_score,
            "target_positions_per_month": spec.target_positions_per_month,
            "min_trades_per_month": spec.min_trades_per_month,
            "chip_w": spec.chip_w,
            "tech_w": spec.tech_w,
            "fundamental_w": spec.fundamental_w,
            "value_w": spec.value_w,
            **metrics,
        }
        result["objective"] = round(
            result["win_rate"] * 0.40 + result["avg_return_pct"] * 0.35 + result["monthly_avg_return_pct"] * 0.25,
            6,
        )
        results.append(result)
        family_buckets[spec.family].append(result)

    results.sort(key=lambda row: (-row["objective"], -row["win_rate"], -row["avg_return_pct"], -row["monthly_avg_return_pct"], -row["trades"]))
    top50 = results[:50]
    write_csv(OUT_CSV, top50, list(top50[0].keys()) if top50 else [])

    global_results: list[dict[str, Any]] = []
    for target in (3, 5, 8, 10, 15, 20):
        for min_trades in (3, 4):
            for min_score in (0.0, 2.0, 4.0, 6.0):
                for chip_w, tech_w, fundamental_w, value_w in (
                    (1.2, 1.2, 1.0, 0.6),
                    (1.0, 1.0, 1.2, 1.0),
                    (1.4, 1.2, 0.8, 0.8),
                    (1.0, 1.4, 0.8, 1.0),
                ):
                    spec = Spec("global", min_score, target, min_trades, chip_w, tech_w, fundamental_w, value_w)
                    scored = []
                    for row in rows:
                        score = score_global_trade(row)
                        if score < spec.min_score:
                            continue
                        scored.append({**row, "family": "global", "score": round(score, 4), "return_pct": parse_float(row.get("return_pct")) or 0.0})
                    selected = top_n_per_month(scored, spec.target_positions_per_month)
                    metrics = evaluate(selected)
                    if not metrics or metrics["min_trades_per_month"] < spec.min_trades_per_month:
                        continue
                    result = {
                        "family": "global",
                        "min_score": spec.min_score,
                        "target_positions_per_month": spec.target_positions_per_month,
                        "min_trades_per_month": spec.min_trades_per_month,
                        "chip_w": spec.chip_w,
                        "tech_w": spec.tech_w,
                        "fundamental_w": spec.fundamental_w,
                        "value_w": spec.value_w,
                        **metrics,
                    }
                    result["objective"] = round(
                        result["win_rate"] * 0.40 + result["avg_return_pct"] * 0.35 + result["monthly_avg_return_pct"] * 0.25,
                        6,
                    )
                    global_results.append(result)

    global_results.sort(key=lambda row: (-row["objective"], -row["win_rate"], -row["avg_return_pct"], -row["monthly_avg_return_pct"], -row["trades"]))
    write_csv(GLOBAL_CSV, global_results[:50], list(global_results[0].keys()) if global_results else [])

    family_best = None
    family_summaries: dict[str, Any] = {}
    for family, family_rows in family_buckets.items():
        family_rows.sort(key=lambda row: (-row["objective"], -row["win_rate"], -row["avg_return_pct"], -row["monthly_avg_return_pct"], -row["trades"]))
        family_top = family_rows[:50]
        family_output = DATA_DIR / f"gold50_{family}_results.csv"
        family_summary = DATA_DIR / f"gold50_{family}_summary.json"
        write_csv(family_output, family_top, list(family_top[0].keys()) if family_top else [])
        family_payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "family": family,
            "strategy_count": len(family_rows),
            "top50_count": len(family_top),
            "best": family_top[0] if family_top else None,
        }
        family_summary.write_text(json.dumps(family_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        family_summaries[family] = family_payload
        if family_best is None or (
            family_top and family_top[0]["objective"] > family_best["objective"]
        ):
            family_best = family_top[0] if family_top else family_best

    write_csv(FAMILY_CSV, top50, list(top50[0].keys()) if top50 else [])

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "trades": len(rows),
        "strategy_count": len(results),
        "global_strategy_count": len(global_results),
        "top50_count": len(top50),
        "best": top50[0] if top50 else None,
        "family_best": family_best,
        "family_summaries": family_summaries,
        "families": list(FAMILY_FEATURES.keys()),
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    GLOBAL_JSON.write_text(json.dumps({"generated_at": summary["generated_at"], "best": global_results[0] if global_results else None}, ensure_ascii=False, indent=2), encoding="utf-8")
    FAMILY_JSON.write_text(json.dumps({"generated_at": summary["generated_at"], "best": top50[0] if top50 else None}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
