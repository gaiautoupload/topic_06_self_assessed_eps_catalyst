"""Topic 06 — 自結 EPS 股價催化效應：finlab 還原版.

原專案資料源為本機 D:\\dataset 的 material_events.jsonl + 個股價格 CSV。
本檔把資料源換成 finlab：
  - 事件文本  ->  important_info_announcement (symbol/date/name/title/info/...)
  - 個股價格  ->  price:收盤價 (還原權值)

事件判定 / 分級 / 去重 / 進出場規則 全部 **逐字沿用原專案邏輯**
(extract_events.py / build_valuation_snapshot.py / build_trades.py)，不做任何優化。

輸出：
  - data/ 下 events / valuation_snapshot / trades 三張表 + 摘要 json
  - reports/ 下 finlab 原生回測 report（年度報酬熱力圖/權益曲線/回撤），T+5/10/20 × raw/cost

用法：
  python self_assessed_eps_strategy.py                # 完整：事件→交易→原生報表
  python self_assessed_eps_strategy.py --report-only  # 只讀現有 trades.csv 重產報表
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from finlab import data
from finlab.backtest import sim

OUTPUT_DIR = Path(__file__).resolve().parent / "data"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"
HOLDING_WINDOWS = (5, 10, 20)

# ----------------------------------------------------------------------------
# 以下關鍵字 / regex / 分級 / 去重，逐字沿用原 extract_events.py
# ----------------------------------------------------------------------------
POSITIVE_KEYWORDS = ["自結", "EPS", "每股盈餘", "稅後純益", "獲利", "盈餘", "財報", "法說"]
SELF_ASSESSED_KEYWORDS = ["自結", "自結合併損益", "自結損益", "自結獲利", "最近一季每股盈餘", "最近一月自結"]
METRIC_KEYWORDS = ["EPS", "每股盈餘", "稅後純益", "稅後淨利", "稅後損益", "獲利", "合併損益"]
NEGATIVE_KEYWORDS = [
    "新聞", "評論", "分析", "預估", "法人看法", "目標價", "買回庫藏股", "庫藏股",
    "股東會", "除權息", "現金股利", "增資", "減資", "董事會決議",
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
    positive = any(k.lower() in text.lower() for k in POSITIVE_KEYWORDS)
    negative = any(k.lower() in text.lower() for k in NEGATIVE_KEYWORDS)
    return positive and not negative


def is_strong_candidate(title: str, content: str) -> bool:
    text = f"{title}\n{content}"
    lowered = text.lower()
    has_self_assessed = any(k.lower() in lowered for k in SELF_ASSESSED_KEYWORDS)
    has_metric = any(k.lower() in lowered for k in METRIC_KEYWORDS)
    has_number = any(ch.isdigit() for ch in text)
    negative = any(k.lower() in lowered for k in NEGATIVE_KEYWORDS)
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


def classify_event_type(title, content, eps_value, profit_value):
    title_hit = any(k.lower() in title.lower() for k in ["自結", "EPS", "每股盈餘"])
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


def derive_event_id(stock_id: str, announcement_date: str, announcement_time: str, raw_id: str) -> str:
    time_part = announcement_time.replace(":", "")
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
    announcement_date = safe_text(obj.get("announcement_date"))
    announcement_time = safe_text(obj.get("announcement_time"))
    fact_date = safe_text(obj.get("fact_date")) or announcement_date

    period_label = safe_text(obj.get("period_label"))
    if not period_label:
        for token in ("月", "季", "半年", "年度", "累計"):
            if token in text:
                period_label = token
                break

    raw_event_id = safe_text(obj.get("raw_event_id"))
    event_id = derive_event_id(stock_id, announcement_date, announcement_time, raw_event_id)

    return NormalizedEvent(
        event_id=event_id,
        stock_id=stock_id,
        company_name=safe_text(obj.get("company_name")),
        market=safe_text(obj.get("market")),
        industry=safe_text(obj.get("industry")),
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


def deduplicate_events(events) -> list[NormalizedEvent]:
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


# ----------------------------------------------------------------------------
# Stage 1: 從 finlab important_info_announcement 萃取事件
# ----------------------------------------------------------------------------
def extract_events() -> pd.DataFrame:
    raw = data.get("important_info_announcement")
    df = raw[["symbol", "date", "name", "title", "info", "stock_id"]].copy()
    df["title"] = df["title"].fillna("").astype(str)
    df["info"] = df["info"].fillna("").astype(str)

    # 向量化先濾出 strong candidate，再對小子集逐列套用原 normalize 邏輯
    text = (df["title"] + "\n" + df["info"])
    low = text.str.lower()

    def any_kw(series_low, kws):
        mask = None
        for k in kws:
            m = series_low.str.contains(re.escape(k.lower()), regex=True, na=False)
            mask = m if mask is None else (mask | m)
        return mask

    has_self = any_kw(low, SELF_ASSESSED_KEYWORDS)
    has_metric = any_kw(low, METRIC_KEYWORDS)
    has_num = text.str.contains(r"\d", regex=True, na=False)
    neg = any_kw(low, NEGATIVE_KEYWORDS)
    strong = has_self & has_metric & has_num & (~neg)
    sub = df[strong].copy()

    events: list[NormalizedEvent] = []
    for row in sub.itertuples(index=False):
        dt: pd.Timestamp = row.date
        obj = {
            "title": row.title,
            "content": row.info,
            "stock_id": str(row.stock_id),
            "company_name": str(row.name),
            "market": "",
            "industry": "",
            "announcement_date": dt.strftime("%Y-%m-%d"),
            "announcement_time": dt.strftime("%H:%M:%S"),
            "fact_date": "",
            "period_label": "",
            "source": "important_info_announcement",
            "raw_event_id": f"{row.symbol}_{dt.strftime('%Y%m%d%H%M%S')}",
        }
        ev = normalize_event(obj)
        if ev is not None:
            events.append(ev)

    events = deduplicate_events(events)
    # 原專案預設 (不帶 --include-c-tier)：只留 A/B 級
    events = [e for e in events if e.event_type in {"self_assessed_eps", "self_assessed_profit"}]
    return pd.DataFrame([asdict(e) for e in events])


# ----------------------------------------------------------------------------
# Stage 2+3: valuation snapshot + trades，沿用原進出場規則
#   進場：公告當日 (盤後 >=13:30 則順延次一交易日) 的收盤
#   出場：進場日後 N 個「該股自身交易日」的收盤
# ----------------------------------------------------------------------------
def build_snapshots_and_trades(events: pd.DataFrame, close: pd.DataFrame):
    snapshots = []
    trades = []
    missing = []

    close = close.sort_index()
    by_stock = {sid: sub for sid, sub in events.groupby("stock_id")}

    for stock_id, evs in by_stock.items():
        if stock_id not in close.columns:
            for _, ev in evs.iterrows():
                missing.append({"event_id": ev.event_id, "stock_id": stock_id,
                                "announcement_date": ev.announcement_date, "reason": "missing_price_file"})
            continue
        s = close[stock_id].dropna()
        if s.empty:
            for _, ev in evs.iterrows():
                missing.append({"event_id": ev.event_id, "stock_id": stock_id,
                                "announcement_date": ev.announcement_date, "reason": "missing_price_file"})
            continue
        dates = s.index.values  # datetime64[ns], sorted
        vals = s.values.astype(float)

        for _, ev in evs.iterrows():
            ev_date = np.datetime64(ev.announcement_date)
            after_close = bool(ev.announcement_time) and ev.announcement_time >= "13:30:00"
            pos = int(np.searchsorted(dates, ev_date, side="left"))
            if pos < len(dates) and dates[pos] == ev_date and after_close:
                pos += 1
            if pos >= len(dates):
                missing.append({"event_id": ev.event_id, "stock_id": stock_id,
                                "announcement_date": ev.announcement_date,
                                "reason": "no_trade_date_on_or_after_event"})
                continue

            entry_idx = pos
            entry_date = pd.Timestamp(dates[entry_idx])
            entry_close = float(vals[entry_idx])
            eps_value = ev.eps_value if pd.notna(ev.eps_value) else None
            implied_pe = round(entry_close / eps_value, 4) if (eps_value is not None and eps_value > 0) else None

            snapshots.append({
                "event_id": ev.event_id, "stock_id": stock_id, "company_name": ev.company_name,
                "event_type": ev.event_type, "signal_strength": ev.signal_strength,
                "announcement_date": ev.announcement_date, "announcement_time": ev.announcement_time,
                "entry_date": entry_date.strftime("%Y-%m-%d"), "close": entry_close,
                "eps_value": eps_value, "implied_pe": implied_pe,
            })

            for n in HOLDING_WINDOWS:
                exit_idx = entry_idx + n
                if exit_idx >= len(dates):
                    continue
                exit_close = float(vals[exit_idx])
                if entry_close == 0:
                    continue
                ret = round((exit_close - entry_close) / entry_close, 6)
                trades.append({
                    "trade_id": f"{ev.event_id}_T{n}", "event_id": ev.event_id, "stock_id": stock_id,
                    "strategy_tag": f"hold_{n}", "signal_strength": ev.signal_strength,
                    "entry_date": entry_date.strftime("%Y-%m-%d"), "entry_price": entry_close,
                    "exit_date": pd.Timestamp(dates[exit_idx]).strftime("%Y-%m-%d"),
                    "exit_price": exit_close, "holding_days": n, "return_pct": ret,
                    "exit_reason": f"T+{n}",
                })

    return pd.DataFrame(snapshots), pd.DataFrame(trades), pd.DataFrame(missing)


# ----------------------------------------------------------------------------
# Stage 4: finlab 原生回測 report（年度報酬熱力圖/權益曲線/回撤）
#   把每筆交易攤成日頻等權重重疊投組，跑 sim()，rep.to_html() 出原生報表。
# ----------------------------------------------------------------------------
REPORT_CONFIGS = [
    ("T20_raw", 20, 0.0, 0.0),
    ("T20_cost", 20, 1.425 / 1000, 3 / 1000),
    ("T10_cost", 10, 1.425 / 1000, 3 / 1000),
    ("T5_cost", 5, 1.425 / 1000, 3 / 1000),
]


def _build_position(trades: pd.DataFrame, close: pd.DataFrame, cal, window: int) -> pd.DataFrame:
    sub = trades[trades["holding_days"] == window]
    pos = pd.DataFrame(False, index=close.index, columns=close.columns)
    for t in sub.itertuples(index=False):
        if t.stock_id not in pos.columns:
            continue
        a = np.searchsorted(cal, np.datetime64(t.entry_date), side="left")
        b = np.searchsorted(cal, np.datetime64(t.exit_date), side="left")
        if a < b:
            pos.iloc[a:b, pos.columns.get_loc(t.stock_id)] = True
    return pos


def build_native_reports(trades: pd.DataFrame, close: pd.DataFrame) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    close = close.sort_index()
    cal = close.index.values
    for tag, n, fee, tax in REPORT_CONFIGS:
        pos = _build_position(trades, close, cal, n)
        rep = sim(pos, resample=None, trade_at_price="close",
                  fee_ratio=fee, tax_ratio=tax, position_limit=1, upload=False)
        path = REPORTS_DIR / f"自結EPS_{tag}_finlab原生report.html"
        rep.to_html(str(path))
        print(f"  {tag:10s} -> {path.name}  (final_nav={float(rep.daily_creturn.iloc[-1]):.2f})")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="自結EPS催化策略 finlab 還原 + 原生回測報表")
    ap.add_argument("--report-only", action="store_true",
                    help="跳過事件萃取，讀現有 trades.csv 只重產 finlab 原生報表")
    args = ap.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.report_only:
        print("[report-only] load trades.csv + price:收盤價 ...")
        trades = pd.read_csv(OUTPUT_DIR / "trades.csv", dtype={"stock_id": str})
        close = data.get("price:收盤價")
        print("[report] build finlab native reports ...")
        build_native_reports(trades, close)
        print("done")
        return 0

    print("[1/4] extract events from important_info_announcement ...")
    events = extract_events()
    events.to_csv(OUTPUT_DIR / "events.csv", index=False, encoding="utf-8-sig")
    print(f"  events (A/B tier, deduped): {len(events)}")
    print(events["event_type"].value_counts().to_string())

    print("[2/4] load price:收盤價 (adjusted) ...")
    close = data.get("price:收盤價")

    print("[3/4] build snapshots + trades ...")
    snapshots, trades, missing = build_snapshots_and_trades(events, close)
    snapshots.to_csv(OUTPUT_DIR / "valuation_snapshot.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(OUTPUT_DIR / "trades.csv", index=False, encoding="utf-8-sig")
    missing.to_csv(OUTPUT_DIR / "valuation_missing_prices.csv", index=False, encoding="utf-8-sig")

    summary = {
        "events": int(len(events)),
        "events_self_assessed_eps": int((events["event_type"] == "self_assessed_eps").sum()),
        "events_self_assessed_profit": int((events["event_type"] == "self_assessed_profit").sum()),
        "snapshots": int(len(snapshots)),
        "missing_prices": int(len(missing)),
        "coverage_ratio": round(len(snapshots) / len(events), 4) if len(events) else 0.0,
        "events_with_implied_pe": int(snapshots["implied_pe"].notna().sum()) if len(snapshots) else 0,
        "trades": int(len(trades)),
        "windows": list(HOLDING_WINDOWS),
        "date_min": events["announcement_date"].min() if len(events) else None,
        "date_max": events["announcement_date"].max() if len(events) else None,
    }
    (OUTPUT_DIR / "pipeline_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    print("[4/4] build finlab native reports -> reports/ ...")
    build_native_reports(trades, close)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
