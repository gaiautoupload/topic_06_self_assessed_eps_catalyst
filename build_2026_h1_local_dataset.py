from __future__ import annotations

import csv
import json
import re
from pathlib import Path


SHARED_EVENTS = Path(r"D:\dataset\processed\material_events.jsonl")
CURRENT_MOPS_JSON = Path(r"D:\dataset\mops\20260617\t187ap04_L.json")
PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_DIR = PROJECT_DIR / "project_data" / "2026_h1"
PRICES_DIR = Path(r"D:\dataset\processed\prices")

START_DATE = "2026-01-01"
END_DATE = "2026-06-30"

CANDIDATE_KEYWORDS = [
    "自結",
    "自結合併損益",
    "每股盈餘",
    "每股稅後盈餘",
    "每股純益",
    "EPS",
    "由虧轉盈",
]

EXCLUDE_KEYWORDS = [
    "解除新任董事競業禁止",
    "股東常會",
    "董事會決議",
    "買回庫藏股",
    "現金股利",
    "除權息",
    "增資",
    "減資",
]

REVIEW_ONLY_KEYWORDS = [
    "董事會重要決議事項",
    "更正",
    "澄清新聞媒體報導",
    "關係人交易申報數調整",
]

EPS_PATTERNS = [
    re.compile(r"(?:EPS|每股盈餘|每股稅後盈餘|每股純益)\s*[:：]?\s*([-+]?\d+(?:\.\d+)?)"),
    re.compile(r"(?:EPS|每股盈餘|每股稅後盈餘|每股純益)[^\d-]{0,10}([-+]?\d+(?:\.\d+)?)"),
]

PROFIT_PATTERNS = [
    re.compile(r"(?:稅後純益|稅後淨利|稅後利益|歸屬母公司稅後利益)\s*[:：]?\s*([-+]?\d+(?:,\d{3})*(?:\.\d+)?)"),
]

COMPARE_KEYWORDS = [
    "較上月",
    "較前月",
    "較上季",
    "較去年同期",
    "與去年同期",
    "年增",
    "季增",
    "月增",
    "由虧轉盈",
    "由盈轉虧",
    "增 減%",
    "增減%",
    "增     減%",
]


def parse_float(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except Exception:
        return None


def extract_first(patterns: list[re.Pattern[str]], text: str) -> float | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            value = parse_float(match.group(1))
            if value is not None:
                return value
    return None


def is_candidate(obj: dict) -> bool:
    date = obj.get("announcement_date", "")
    if not (START_DATE <= date <= END_DATE):
        return False
    text = f"{obj.get('title', '')}\n{obj.get('content', '')}"
    if not any(keyword in text for keyword in CANDIDATE_KEYWORDS):
        return False
    if any(keyword in text for keyword in EXCLUDE_KEYWORDS):
        return False
    return True


def normalize_mops_json_obj(obj: dict) -> dict:
    roc_date = str(obj.get("發言日期", "")).strip()
    announcement_date = ""
    if len(roc_date) == 7 and roc_date.isdigit():
        year = int(roc_date[:3]) + 1911
        month = roc_date[3:5]
        day = roc_date[5:7]
        announcement_date = f"{year:04d}-{month}-{day}"
    roc_time = str(obj.get("發言時間", "")).strip()
    announcement_time = ""
    if len(roc_time) == 6 and roc_time.isdigit():
        announcement_time = f"{roc_time[:2]}:{roc_time[2:4]}:{roc_time[4:6]}"
    return {
        "announcement_date": announcement_date,
        "announcement_time": announcement_time,
        "stock_id": str(obj.get("公司代號", "")).strip(),
        "company_name": str(obj.get("公司名稱", "")).strip(),
        "title": str(obj.get("主旨 ", "")).strip() or str(obj.get("主旨", "")).strip(),
        "content": str(obj.get("說明", "")).strip(),
        "event_id": f"mopsjson_{str(obj.get('公司代號', '')).strip()}_{roc_date}_{roc_time}",
        "source": "mops_json_20260617",
    }


def load_all_candidates() -> list[dict]:
    rows: list[dict] = []
    with SHARED_EVENTS.open("r", encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            if is_candidate(obj):
                rows.append(obj)

    if CURRENT_MOPS_JSON.exists():
        decoder = json.JSONDecoder()
        with CURRENT_MOPS_JSON.open("r", encoding="utf-8") as fh:
            for line in fh:
                text = line.strip()
                if "{" not in text:
                    continue
                idx = 0
                while idx < len(text):
                    brace = text.find("{", idx)
                    if brace == -1:
                        break
                    try:
                        parsed, end = decoder.raw_decode(text, brace)
                    except json.JSONDecodeError:
                        break
                    obj = normalize_mops_json_obj(parsed)
                    if is_candidate(obj):
                        rows.append(obj)
                    idx = end

    dedup: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (row.get("stock_id", ""), row.get("announcement_date", ""), row.get("title", ""))
        dedup[key] = row
    return list(dedup.values())


def strategy_bucket(text: str, eps_value: float | None) -> str:
    if "由虧轉盈" in text:
        return "turnaround_loss_to_profit"
    if eps_value is not None and eps_value > 0:
        return "topic_06_eps_catalyst"
    return "topic_06_review"


def needs_manual_review(text: str, eps_value: float | None, profit_value: float | None) -> bool:
    if any(keyword in text for keyword in REVIEW_ONLY_KEYWORDS):
        return True
    if eps_value is None and profit_value is None:
        return True
    return False


def has_compare_context(text: str) -> bool:
    return any(keyword in text for keyword in COMPARE_KEYWORDS)


def has_price_file(stock_id: str) -> bool:
    return (PRICES_DIR / f"{stock_id}.csv").exists()


def main() -> int:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    raw_candidates: list[dict] = []
    selected_rows: list[dict[str, object]] = []
    main_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    insufficiency_rows: list[dict[str, str]] = []
    main_gap_rows: list[dict[str, str]] = []

    for obj in load_all_candidates():
            raw_candidates.append(obj)

            text = f"{obj.get('title', '')}\n{obj.get('content', '')}"
            eps_value = extract_first(EPS_PATTERNS, text)
            profit_value = extract_first(PROFIT_PATTERNS, text)
            bucket = strategy_bucket(text, eps_value)
            compare_ok = has_compare_context(text)
            price_ok = has_price_file(obj.get("stock_id", ""))

            selected_rows.append(
                row := {
                    "announcement_date": obj.get("announcement_date", ""),
                    "announcement_time": obj.get("announcement_time", ""),
                    "stock_id": obj.get("stock_id", ""),
                    "company_name": obj.get("company_name", ""),
                    "title": obj.get("title", ""),
                    "event_id": obj.get("event_id", ""),
                    "eps_value": eps_value,
                    "profit_value": profit_value,
                    "has_compare_context": compare_ok,
                    "has_price_file": price_ok,
                    "strategy_bucket": bucket,
                    "source": obj.get("source", ""),
                }
            )

            if needs_manual_review(text, eps_value, profit_value):
                review_rows.append(row)
            else:
                main_rows.append(row)
                if eps_value is None and profit_value is None:
                    main_gap_rows.append(
                        {
                            "event_id": obj.get("event_id", ""),
                            "stock_id": obj.get("stock_id", ""),
                            "announcement_date": obj.get("announcement_date", ""),
                            "issue": "missing_metric_value",
                        }
                    )
                if not compare_ok:
                    main_gap_rows.append(
                        {
                            "event_id": obj.get("event_id", ""),
                            "stock_id": obj.get("stock_id", ""),
                            "announcement_date": obj.get("announcement_date", ""),
                            "issue": "missing_compare_context",
                        }
                    )
                if not price_ok:
                    main_gap_rows.append(
                        {
                            "event_id": obj.get("event_id", ""),
                            "stock_id": obj.get("stock_id", ""),
                            "announcement_date": obj.get("announcement_date", ""),
                            "issue": "missing_price_file",
                        }
                    )

            if eps_value is None and profit_value is None:
                insufficiency_rows.append(
                    {
                        "event_id": obj.get("event_id", ""),
                        "stock_id": obj.get("stock_id", ""),
                        "announcement_date": obj.get("announcement_date", ""),
                        "issue": "missing_metric_value",
                    }
                )
            if not compare_ok:
                insufficiency_rows.append(
                    {
                        "event_id": obj.get("event_id", ""),
                        "stock_id": obj.get("stock_id", ""),
                        "announcement_date": obj.get("announcement_date", ""),
                        "issue": "missing_compare_context",
                    }
                )
            if not price_ok:
                insufficiency_rows.append(
                    {
                        "event_id": obj.get("event_id", ""),
                        "stock_id": obj.get("stock_id", ""),
                        "announcement_date": obj.get("announcement_date", ""),
                        "issue": "missing_price_file",
                    }
                )

    with (LOCAL_DIR / "raw_candidates.jsonl").open("w", encoding="utf-8") as fh:
        for obj in raw_candidates:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    with (LOCAL_DIR / "selected_events.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        fieldnames = [
            "announcement_date", "announcement_time", "stock_id", "company_name", "title",
            "event_id", "eps_value", "profit_value", "has_compare_context", "has_price_file",
            "strategy_bucket", "source"
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selected_rows)

    with (LOCAL_DIR / "main_strategy_events.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        fieldnames = [
            "announcement_date", "announcement_time", "stock_id", "company_name", "title",
            "event_id", "eps_value", "profit_value", "has_compare_context", "has_price_file",
            "strategy_bucket", "source"
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(main_rows)

    with (LOCAL_DIR / "manual_review_events.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        fieldnames = [
            "announcement_date", "announcement_time", "stock_id", "company_name", "title",
            "event_id", "eps_value", "profit_value", "has_compare_context", "has_price_file",
            "strategy_bucket", "source"
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(review_rows)

    with (LOCAL_DIR / "insufficiencies.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        fieldnames = ["event_id", "stock_id", "announcement_date", "issue"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(insufficiency_rows)

    with (LOCAL_DIR / "main_event_gaps.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        fieldnames = ["event_id", "stock_id", "announcement_date", "issue"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(main_gap_rows)

    summary = {
        "raw_candidates": len(raw_candidates),
        "selected_events": len(selected_rows),
        "main_strategy_events": len(main_rows),
        "manual_review_events": len(review_rows),
        "missing_metric_value": sum(1 for row in insufficiency_rows if row["issue"] == "missing_metric_value"),
        "missing_compare_context": sum(1 for row in insufficiency_rows if row["issue"] == "missing_compare_context"),
        "missing_price_file": sum(1 for row in insufficiency_rows if row["issue"] == "missing_price_file"),
        "main_event_gaps": len(main_gap_rows),
        "local_dir": str(LOCAL_DIR),
    }
    with (LOCAL_DIR / "summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
