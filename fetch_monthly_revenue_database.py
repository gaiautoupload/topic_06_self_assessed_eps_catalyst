from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from io import StringIO
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_DIR = PROJECT_DIR / "project_data" / "fundamental_event_lab"
OUT_DIR = LOCAL_DIR / "monthly_revenue"

START_ROC_YEAR = 115
END_ROC_YEAR = 115
START_MONTH = 1
END_MONTH = 6
MARKETS = {
    "listed": "sii",
    "otc": "otc",
}


@dataclass
class MonthlyRevenueRow:
    revenue_month: str
    market: str
    stock_id: str
    company_name: str
    current_month_revenue: float | None
    previous_month_revenue: float | None
    previous_year_month_revenue: float | None
    mom_pct: float | None
    yoy_pct: float | None
    cumulative_revenue: float | None
    previous_year_cumulative_revenue: float | None
    cumulative_yoy_pct: float | None
    note: str
    source_url: str


def parse_float(value: object) -> float | None:
    text = str(value).strip().replace(",", "")
    if not text or text.lower() == "nan" or text == "--":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = ["".join(str(part) for part in col if str(part) != "nan") if isinstance(col, tuple) else str(col) for col in df.columns]
    return df


def find_column(columns: list[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        for column in columns:
            if candidate in column:
                return column
    return None


def candidate_urls(roc_year: int, month: int, market_code: str) -> list[str]:
    return [
        f"https://mops.twse.com.tw/nas/t21/{market_code}/t21sc03_{roc_year}_{month}.html",
        f"https://mops.twse.com.tw/nas/t21/{market_code}/t21sc03_{roc_year}_{month}_0.html",
        f"https://mops.twse.com.tw/nas/t21/{market_code}/t21sc03_{roc_year}_{month:02d}.html",
        f"https://mops.twse.com.tw/nas/t21/{market_code}/t21sc03_{roc_year}_{month:02d}_0.html",
    ]


def read_url(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("big5", errors="replace")


def fetch_market_month(roc_year: int, month: int, market_label: str, market_code: str) -> list[MonthlyRevenueRow]:
    url = ""
    html = ""
    errors = []
    for candidate in candidate_urls(roc_year, month, market_code):
        try:
            html = read_url(candidate)
            url = candidate
            break
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
    if not html:
        raise RuntimeError(" | ".join(errors))
    tables = pd.read_html(StringIO(html))

    rows: list[MonthlyRevenueRow] = []
    revenue_month = f"{roc_year + 1911:04d}-{month:02d}"
    for table in tables:
        df = normalize_columns(table)
        columns = list(df.columns)
        stock_col = find_column(columns, ["公司代號"])
        name_col = find_column(columns, ["公司名稱"])
        current_col = find_column(columns, ["當月營收"])
        prev_month_col = find_column(columns, ["上月營收"])
        prev_year_col = find_column(columns, ["去年當月營收"])
        mom_col = find_column(columns, ["上月比較", "上月增減"])
        yoy_col = find_column(columns, ["去年同月", "去年同月增減"])
        cumulative_col = find_column(columns, ["當月累計營收"])
        prev_cumulative_col = find_column(columns, ["去年累計營收"])
        cumulative_yoy_col = find_column(columns, ["前期比較", "累計增減"])
        note_col = find_column(columns, ["備註"])
        if not stock_col or not name_col or not current_col:
            continue

        for _, item in df.iterrows():
            stock_id = str(item.get(stock_col, "")).strip()
            if not stock_id.isdigit():
                continue
            rows.append(
                MonthlyRevenueRow(
                    revenue_month=revenue_month,
                    market=market_label,
                    stock_id=stock_id,
                    company_name=str(item.get(name_col, "")).strip(),
                    current_month_revenue=parse_float(item.get(current_col)),
                    previous_month_revenue=parse_float(item.get(prev_month_col)) if prev_month_col else None,
                    previous_year_month_revenue=parse_float(item.get(prev_year_col)) if prev_year_col else None,
                    mom_pct=(parse_float(item.get(mom_col)) / 100.0) if mom_col and parse_float(item.get(mom_col)) is not None else None,
                    yoy_pct=(parse_float(item.get(yoy_col)) / 100.0) if yoy_col and parse_float(item.get(yoy_col)) is not None else None,
                    cumulative_revenue=parse_float(item.get(cumulative_col)) if cumulative_col else None,
                    previous_year_cumulative_revenue=parse_float(item.get(prev_cumulative_col)) if prev_cumulative_col else None,
                    cumulative_yoy_pct=(parse_float(item.get(cumulative_yoy_col)) / 100.0)
                    if cumulative_yoy_col and parse_float(item.get(cumulative_yoy_col)) is not None
                    else None,
                    note=str(item.get(note_col, "")).strip() if note_col else "",
                    source_url=url,
                )
            )
    return rows


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[MonthlyRevenueRow] = []
    failures: list[dict[str, object]] = []

    for roc_year in range(START_ROC_YEAR, END_ROC_YEAR + 1):
        for month in range(START_MONTH, END_MONTH + 1):
            for market_label, market_code in MARKETS.items():
                try:
                    rows.extend(fetch_market_month(roc_year, month, market_label, market_code))
                except Exception as exc:
                    failures.append(
                        {
                            "roc_year": roc_year,
                            "month": month,
                            "market": market_label,
                            "error": str(exc),
                        }
                    )

    out_csv = OUT_DIR / "monthly_revenue_2026_h1.csv"
    fields = list(MonthlyRevenueRow.__dataclass_fields__.keys())
    with out_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    summary = {
        "rows": len(rows),
        "failures": failures,
        "output_csv": str(out_csv),
    }
    with (OUT_DIR / "monthly_revenue_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
