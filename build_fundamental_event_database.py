from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
DATASET_DIR = Path(r"D:\dataset")
EVENTS_PATH = DATASET_DIR / "processed" / "material_events.jsonl"
PRICES_DIR = DATASET_DIR / "processed" / "prices"
LOCAL_DIR = PROJECT_DIR / "project_data" / "fundamental_event_lab"

START_DATE = "2026-01-01"
END_DATE = "2026-06-30"

FINANCIAL_KEYWORDS = [
    "財務業務資訊",
    "營業收入",
    "每月營業收入",
    "合併營收",
    "自結損益",
    "每股盈餘",
    "財務報告",
]

NOISE_KEYWORDS = [
    "澄清媒體報導",
    "法人說明會",
    "股東常會",
    "更正",
    "重編",
    "資金貸與",
]


@dataclass
class FundamentalEvent:
    event_id: str
    stock_id: str
    company_name: str
    announcement_date: str
    announcement_time: str
    fact_date: str
    title: str
    clause: str
    source: str
    report_month: str
    monthly_revenue: float | None
    monthly_revenue_yoy_pct: float | None
    quarterly_revenue: float | None
    quarterly_revenue_yoy_pct: float | None
    pretax_profit: float | None
    pretax_profit_yoy_pct: float | None
    parent_net_profit: float | None
    parent_net_profit_yoy_pct: float | None
    eps: float | None
    eps_yoy_pct: float | None
    gross_margin: float | None
    operating_margin: float | None
    net_margin: float | None
    revenue_mom_pct: float | None
    revenue_yoy_positive: bool
    pretax_yoy_positive: bool
    eps_yoy_positive: bool
    three_rises_count: int
    has_price_file: bool
    signal_score: float


def parse_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def percent_to_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    return value / 100.0


def extract_numbers(line: str) -> list[float]:
    pattern = re.compile(r"\(?[-+]?\d[\d,]*(?:\.\d+)?\)?%?")
    values = []
    for match in pattern.findall(line):
        value = parse_float(match)
        if value is not None:
            values.append(value)
    return values


def get_line_after_label(text: str, label_patterns: list[str]) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for idx, line in enumerate(lines):
        joined = line
        if idx + 1 < len(lines):
            joined = f"{joined} {lines[idx + 1]}"
        if any(pattern in joined for pattern in label_patterns):
            return joined
    return ""


def parse_monthly_table_metric(text: str, labels: list[str]) -> tuple[float | None, float | None, float | None, float | None]:
    line = get_line_after_label(text, labels)
    if not line:
        return None, None, None, None
    if "%" not in line:
        return None, None, None, None
    values = extract_numbers(line)
    if len(values) >= 4:
        return values[0], percent_to_ratio(values[1]), values[2], percent_to_ratio(values[3])
    if len(values) >= 2:
        return values[0], percent_to_ratio(values[1]), None, None
    if len(values) == 1:
        return values[0], None, None, None
    return None, None, None, None


def parse_report_month(text: str) -> str:
    match = re.search(r"(\d{3})年\s*(\d{1,2})月", text)
    if not match:
        return ""
    year = int(match.group(1)) + 1911
    month = int(match.group(2))
    return f"{year:04d}-{month:02d}"


def load_events() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with EVENTS_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            date_text = obj.get("announcement_date", "")
            if START_DATE <= date_text <= END_DATE:
                rows.append(obj)
    return rows


def is_financial_event(obj: dict[str, Any]) -> bool:
    text = f"{obj.get('title', '')}\n{obj.get('content', '')}"
    if any(keyword in text for keyword in NOISE_KEYWORDS):
        return False
    if "財務業務資訊" in text and "營業收入" in text:
        return True
    if "近期營業收入及損益資訊" in text and "每股盈餘" in text:
        return True
    return False


def has_price_file(stock_id: str) -> bool:
    return (PRICES_DIR / f"{stock_id}.csv").exists()


def signal_score(row: FundamentalEvent) -> float:
    score = 0.0
    for value in [
        row.monthly_revenue_yoy_pct,
        row.pretax_profit_yoy_pct,
        row.parent_net_profit_yoy_pct,
        row.eps_yoy_pct,
        row.revenue_mom_pct,
    ]:
        if value is not None:
            score += value
    score += row.three_rises_count * 0.25
    if row.eps is not None and row.eps > 0:
        score += 0.2
    return round(score, 6)


def normalize_event(obj: dict[str, Any]) -> FundamentalEvent:
    content = str(obj.get("content", ""))
    title = str(obj.get("title", "")).strip()
    text = f"{title}\n{content}"

    monthly_revenue, monthly_revenue_yoy, quarterly_revenue, quarterly_revenue_yoy = parse_monthly_table_metric(
        text, ["營業收入"]
    )
    pretax_profit, pretax_profit_yoy, _, _ = parse_monthly_table_metric(text, ["稅前淨利"])
    parent_net_profit, parent_net_profit_yoy, _, _ = parse_monthly_table_metric(
        text, ["歸屬母公司", "本期淨利"]
    )
    eps, eps_yoy, _, _ = parse_monthly_table_metric(text, ["每股盈餘", "基本每股盈餘"])

    revenue_yoy_positive = monthly_revenue_yoy is not None and monthly_revenue_yoy > 0
    pretax_yoy_positive = pretax_profit_yoy is not None and pretax_profit_yoy > 0
    eps_yoy_positive = eps_yoy is not None and eps_yoy > 0

    row = FundamentalEvent(
        event_id=str(obj.get("event_id", "")),
        stock_id=str(obj.get("stock_id", "")),
        company_name=str(obj.get("company_name", "")),
        announcement_date=str(obj.get("announcement_date", "")),
        announcement_time=str(obj.get("announcement_time", "")),
        fact_date=str(obj.get("fact_date", "")),
        title=title.replace("\r", " ").replace("\n", " "),
        clause=str(obj.get("clause", "")),
        source=str(obj.get("source", "")),
        report_month=parse_report_month(text),
        monthly_revenue=monthly_revenue,
        monthly_revenue_yoy_pct=monthly_revenue_yoy,
        quarterly_revenue=quarterly_revenue,
        quarterly_revenue_yoy_pct=quarterly_revenue_yoy,
        pretax_profit=pretax_profit,
        pretax_profit_yoy_pct=pretax_profit_yoy,
        parent_net_profit=parent_net_profit,
        parent_net_profit_yoy_pct=parent_net_profit_yoy,
        eps=eps,
        eps_yoy_pct=eps_yoy,
        gross_margin=None,
        operating_margin=None,
        net_margin=None,
        revenue_mom_pct=None,
        revenue_yoy_positive=revenue_yoy_positive,
        pretax_yoy_positive=pretax_yoy_positive,
        eps_yoy_positive=eps_yoy_positive,
        three_rises_count=sum([revenue_yoy_positive, pretax_yoy_positive, eps_yoy_positive]),
        has_price_file=has_price_file(str(obj.get("stock_id", ""))),
        signal_score=0.0,
    )
    row.signal_score = signal_score(row)
    return row


def add_mom_features(rows: list[FundamentalEvent]) -> None:
    by_stock: dict[str, list[FundamentalEvent]] = {}
    for row in rows:
        by_stock.setdefault(row.stock_id, []).append(row)
    for stock_rows in by_stock.values():
        stock_rows.sort(key=lambda row: (row.report_month or row.announcement_date, row.announcement_date))
        previous: FundamentalEvent | None = None
        for row in stock_rows:
            if (
                previous is not None
                and previous.monthly_revenue is not None
                and previous.monthly_revenue != 0
                and row.monthly_revenue is not None
            ):
                row.revenue_mom_pct = round((row.monthly_revenue - previous.monthly_revenue) / previous.monthly_revenue, 6)
            row.signal_score = signal_score(row)
            if row.monthly_revenue is not None:
                previous = row


def write_csv(path: Path, rows: list[FundamentalEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(FundamentalEvent.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main() -> int:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    all_events = load_events()
    rows = [normalize_event(obj) for obj in all_events if is_financial_event(obj)]
    rows.sort(key=lambda row: (row.announcement_date, row.announcement_time, row.stock_id))
    add_mom_features(rows)

    out_csv = LOCAL_DIR / "fundamental_events_2026_h1.csv"
    write_csv(out_csv, rows)

    coverage = {
        "start_date": START_DATE,
        "end_date": END_DATE,
        "raw_events_in_range": len(all_events),
        "fundamental_events": len(rows),
        "with_monthly_revenue": sum(row.monthly_revenue is not None for row in rows),
        "with_revenue_yoy": sum(row.monthly_revenue_yoy_pct is not None for row in rows),
        "with_eps": sum(row.eps is not None for row in rows),
        "with_eps_yoy": sum(row.eps_yoy_pct is not None for row in rows),
        "with_price_file": sum(row.has_price_file for row in rows),
        "three_rises_events": sum(row.three_rises_count == 3 for row in rows),
        "output_csv": str(out_csv),
    }
    with (LOCAL_DIR / "fundamental_database_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(coverage, fh, ensure_ascii=False, indent=2)
    print(json.dumps(coverage, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
