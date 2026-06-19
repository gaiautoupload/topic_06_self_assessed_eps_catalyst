from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DATASET_DIR = Path(r"D:\dataset")
LOCAL_DIR = PROJECT_DIR / "project_data" / "fundamental_event_lab"
PRICE_DIR = DATASET_DIR / "processed" / "prices"
IN_JSONL = LOCAL_DIR / "vllm_fundamental_extracts_2026_h1.jsonl"
OUT_CSV = LOCAL_DIR / "vllm_fundamental_events_2026_h1.csv"


@dataclass
class VllmFundamentalEvent:
    event_id: str
    stock_id: str
    company_name: str
    announcement_date: str
    announcement_time: str
    title: str
    event_type: str
    report_period: str
    revenue: float | None
    revenue_yoy_pct: float | None
    revenue_mom_pct: float | None
    gross_profit: float | None
    operating_profit: float | None
    pretax_profit: float | None
    parent_net_profit: float | None
    eps: float | None
    eps_yoy_pct: float | None
    gross_margin: float | None
    operating_margin: float | None
    net_margin: float | None
    is_restatement: bool
    is_monthly_revenue: bool
    is_financial_business_info: bool
    confidence: float | None
    has_price_file: bool
    revenue_yoy_positive: bool
    eps_yoy_positive: bool
    three_rate_count: int
    three_rises_count: int
    signal_score: float
    notes: str


def parse_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "是"}


def has_price_file(stock_id: str) -> bool:
    return (PRICE_DIR / f"{stock_id}.csv").exists()


def signal_score(row: VllmFundamentalEvent) -> float:
    score = 0.0
    for value in [row.revenue_yoy_pct, row.revenue_mom_pct, row.eps_yoy_pct]:
        if value is not None:
            score += value
    score += row.three_rises_count * 0.25
    score += row.three_rate_count * 0.15
    if row.eps is not None and row.eps > 0:
        score += 0.2
    return round(score, 6)


def normalize(obj: dict) -> VllmFundamentalEvent:
    revenue_yoy = parse_float(obj.get("revenue_yoy_pct"))
    eps_yoy = parse_float(obj.get("eps_yoy_pct"))
    gross_margin = parse_float(obj.get("gross_margin"))
    operating_margin = parse_float(obj.get("operating_margin"))
    net_margin = parse_float(obj.get("net_margin"))
    three_rate_count = sum(value is not None and value > 0 for value in [gross_margin, operating_margin, net_margin])
    three_rises_count = sum(value is not None and value > 0 for value in [revenue_yoy, eps_yoy])
    row = VllmFundamentalEvent(
        event_id=str(obj.get("event_id", "")),
        stock_id=str(obj.get("stock_id", "")),
        company_name=str(obj.get("company_name", "")),
        announcement_date=str(obj.get("announcement_date", "")),
        announcement_time=str(obj.get("announcement_time", "")),
        title=str(obj.get("title", "")),
        event_type=str(obj.get("event_type", "")),
        report_period=str(obj.get("report_period", "") or ""),
        revenue=parse_float(obj.get("revenue")),
        revenue_yoy_pct=revenue_yoy,
        revenue_mom_pct=parse_float(obj.get("revenue_mom_pct")),
        gross_profit=parse_float(obj.get("gross_profit")),
        operating_profit=parse_float(obj.get("operating_profit")),
        pretax_profit=parse_float(obj.get("pretax_profit")),
        parent_net_profit=parse_float(obj.get("parent_net_profit")),
        eps=parse_float(obj.get("eps")),
        eps_yoy_pct=eps_yoy,
        gross_margin=gross_margin,
        operating_margin=operating_margin,
        net_margin=net_margin,
        is_restatement=parse_bool(obj.get("is_restatement")),
        is_monthly_revenue=parse_bool(obj.get("is_monthly_revenue")),
        is_financial_business_info=parse_bool(obj.get("is_financial_business_info")),
        confidence=parse_float(obj.get("confidence")),
        has_price_file=has_price_file(str(obj.get("stock_id", ""))),
        revenue_yoy_positive=revenue_yoy is not None and revenue_yoy > 0,
        eps_yoy_positive=eps_yoy is not None and eps_yoy > 0,
        three_rate_count=three_rate_count,
        three_rises_count=three_rises_count,
        signal_score=0.0,
        notes=str(obj.get("notes", "")),
    )
    row.signal_score = signal_score(row)
    return row


def main() -> int:
    if not IN_JSONL.exists():
        raise FileNotFoundError(IN_JSONL)
    rows = [normalize(json.loads(line)) for line in IN_JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows.sort(key=lambda row: (row.announcement_date, row.announcement_time, row.stock_id))

    fields = list(VllmFundamentalEvent.__dataclass_fields__.keys())
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    summary = {
        "rows": len(rows),
        "monthly_revenue_rows": sum(row.is_monthly_revenue for row in rows),
        "financial_business_rows": sum(row.is_financial_business_info for row in rows),
        "with_price_file": sum(row.has_price_file for row in rows),
        "output_csv": str(OUT_CSV),
    }
    with (LOCAL_DIR / "vllm_fundamental_database_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
