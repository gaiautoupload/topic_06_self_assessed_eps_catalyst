from __future__ import annotations

import csv
import json
import math
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Any, Iterable, Optional


ROOT = Path(r"D:\dataset")
DEFAULT_INPUT = ROOT / "processed" / "material_events.jsonl"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"

POSITIVE_KEYWORDS = [
    "自結",
    "EPS",
    "每股盈餘",
    "稅後純益",
    "獲利",
    "盈餘",
    "財報",
    "法說",
]

SELF_ASSESSED_KEYWORDS = [
    "自結",
    "自結合併損益",
    "自結損益",
    "自結獲利",
    "最近一季每股盈餘",
    "最近一月自結",
]

METRIC_KEYWORDS = [
    "EPS",
    "每股盈餘",
    "稅後純益",
    "稅後淨利",
    "稅後損益",
    "獲利",
    "合併損益",
]

NEGATIVE_KEYWORDS = [
    "新聞",
    "評論",
    "分析",
    "預估",
    "法人看法",
    "目標價",
    "買回庫藏股",
    "庫藏股",
    "股東會",
    "除權息",
    "現金股利",
    "增資",
    "減資",
    "董事會決議",
]

EPS_PATTERNS = [
    re.compile(r"(?:EPS|每股盈餘|稅後每股盈餘)\s*[:=]?\s*([-+]?\d+(?:\.\d+)?)", re.I),
    re.compile(r"(?:EPS|每股盈餘|稅後每股盈餘)[^\d]{0,12}([-+]?\d+(?:\.\d+)?)", re.I),
]

PROFIT_PATTERNS = [
    re.compile(r"(?:稅後純益|稅後淨利|稅後損益|獲利)\s*[:=]?\s*([-+]?\d+(?:,\d{3})*(?:\.\d+)?)"),
]


@dataclass
class NormalizedEvent:
    event_id: str
    stock_id: str
    company_name: str
    market: str
    industry: str
    announcement_date: str
    announcement_time: str
    fact_date: str
    title: str
    content: str
    event_type: str
    signal_strength: str
    eps_value: Optional[float]
    eps_unit: str
    profit_value: Optional[float]
    profit_unit: str
    period_label: str
    source: str
    raw_event_id: str
    confidence: float


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def looks_like_self_assessed(title: str, content: str) -> bool:
    text = f"{title}\n{content}"
    positive = any(keyword.lower() in text.lower() for keyword in POSITIVE_KEYWORDS)
    negative = any(keyword.lower() in text.lower() for keyword in NEGATIVE_KEYWORDS)
    return positive and not negative


def is_strong_candidate(title: str, content: str) -> bool:
    text = f"{title}\n{content}"
    lowered = text.lower()
    has_self_assessed = any(keyword.lower() in lowered for keyword in SELF_ASSESSED_KEYWORDS)
    has_metric = any(keyword.lower() in lowered for keyword in METRIC_KEYWORDS)
    has_number = any(ch.isdigit() for ch in text)
    negative = any(keyword.lower() in lowered for keyword in NEGATIVE_KEYWORDS)
    return has_self_assessed and has_metric and has_number and not negative


def extract_first_float(patterns: list[re.Pattern[str]], text: str) -> Optional[float]:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            raw = match.group(1).replace(",", "")
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def extract_eps_value(text: str) -> Optional[float]:
    return extract_first_float(EPS_PATTERNS, text)


def extract_profit_value(text: str) -> Optional[float]:
    return extract_first_float(PROFIT_PATTERNS, text)


def classify_event_type(title: str, content: str, eps_value: Optional[float], profit_value: Optional[float]) -> tuple[str, str, float]:
    text = f"{title}\n{content}"
    title_hit = any(keyword.lower() in title.lower() for keyword in ["自結", "EPS", "每股盈餘"])
    content_hit = looks_like_self_assessed(title, content)
    confidence = 0.35

    if title_hit:
        confidence += 0.25
    if content_hit:
        confidence += 0.2
    if eps_value is not None:
        confidence += 0.15
    if profit_value is not None:
        confidence += 0.05

    if eps_value is not None and title_hit:
        return "self_assessed_eps", "A", min(confidence, 0.99)
    if profit_value is not None and content_hit:
        return "self_assessed_profit", "B", min(confidence, 0.95)
    if content_hit:
        return "guidance_or_expectation", "C", min(confidence, 0.8)
    return "guidance_or_expectation", "C", min(confidence, 0.5)


def parse_date(value: Any) -> str:
    text = safe_text(value)
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def derive_event_id(obj: dict[str, Any], stock_id: str, announcement_date: str) -> str:
    existing = safe_text(obj.get("event_id"))
    if existing:
        return existing
    time_part = safe_text(obj.get("announcement_time")).replace(":", "")
    raw_id = safe_text(obj.get("raw_event_id"))
    suffix = raw_id[-8:] if raw_id else "unknown"
    return f"topic06_{stock_id}_{announcement_date.replace('-', '')}_{time_part or '000000'}_{suffix}"


def normalize_event(obj: dict[str, Any]) -> Optional[NormalizedEvent]:
    title = safe_text(obj.get("title"))
    content = safe_text(obj.get("content"))
    text = f"{title}\n{content}"
    if not is_strong_candidate(title, content):
        return None

    eps_value = extract_eps_value(text)
    profit_value = extract_profit_value(text)
    event_type, signal_strength, confidence = classify_event_type(title, content, eps_value, profit_value)

    stock_id = safe_text(obj.get("stock_id"))
    company_name = safe_text(obj.get("company_name"))
    market = safe_text(obj.get("market"))
    industry = safe_text(obj.get("industry"))
    announcement_date = parse_date(obj.get("announcement_date"))
    announcement_time = safe_text(obj.get("announcement_time"))
    fact_date = parse_date(obj.get("fact_date")) or announcement_date

    period_label = safe_text(obj.get("period_label"))
    if not period_label:
        for token in ("月", "季", "半年", "年度", "累計"):
            if token in text:
                period_label = token
                break

    raw_event_id = safe_text(obj.get("event_id"))
    event_id = derive_event_id(obj, stock_id, announcement_date)

    return NormalizedEvent(
        event_id=event_id,
        stock_id=stock_id,
        company_name=company_name,
        market=market,
        industry=industry,
        announcement_date=announcement_date,
        announcement_time=announcement_time,
        fact_date=fact_date,
        title=title,
        content=content,
        event_type=event_type,
        signal_strength=signal_strength,
        eps_value=eps_value,
        eps_unit="元",
        profit_value=profit_value,
        profit_unit="元",
        period_label=period_label,
        source=safe_text(obj.get("source")),
        raw_event_id=raw_event_id,
        confidence=round(confidence, 3),
    )


def deduplicate_events(events: Iterable[NormalizedEvent]) -> list[NormalizedEvent]:
    best: dict[tuple[str, str, str], NormalizedEvent] = {}
    for event in events:
        key = (event.stock_id, event.announcement_date, event.period_label)
        existing = best.get(key)
        if existing is None:
            best[key] = event
            continue
        current_score = (existing.confidence, len(existing.content), 1 if existing.eps_value is not None else 0)
        new_score = (event.confidence, len(event.content), 1 if event.eps_value is not None else 0)
        if new_score > current_score:
            best[key] = event
    return sorted(best.values(), key=lambda e: (e.announcement_date, e.stock_id, e.event_id))


def load_candidates(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def write_csv(path: Path, rows: list[NormalizedEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(rows[0]).keys()) if rows else [])
        if rows:
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))


def write_parquet(path: Path, rows: list[NormalizedEvent]) -> bool:
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return False
    try:
        df = pd.DataFrame([asdict(row) for row in rows])
        df.to_parquet(path, index=False)
        return True
    except Exception:
        return False


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Extract topic 06 self-assessed EPS events.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--include-c-tier", action="store_true")
    args = parser.parse_args()

    raw_events = (normalize_event(obj) for obj in load_candidates(args.input))
    events = deduplicate_events(event for event in raw_events if event is not None)
    if not args.include_c_tier:
        events = [event for event in events if event.event_type in {"self_assessed_eps", "self_assessed_profit"}]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "events.csv"
    parquet_path = args.output_dir / "events.parquet"

    write_csv(csv_path, events)
    parquet_ok = write_parquet(parquet_path, events)

    summary = {
        "input": str(args.input),
        "events": len(events),
        "csv": str(csv_path),
        "parquet": str(parquet_path) if parquet_ok else None,
        "parquet_written": parquet_ok,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
