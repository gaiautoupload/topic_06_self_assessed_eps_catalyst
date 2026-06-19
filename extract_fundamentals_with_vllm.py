from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_DIR = Path(__file__).resolve().parent
DATASET_DIR = Path(r"D:\dataset")
EVENTS_PATH = DATASET_DIR / "processed" / "material_events.jsonl"
LOCAL_DIR = PROJECT_DIR / "project_data" / "fundamental_event_lab"
OUT_JSONL = LOCAL_DIR / "vllm_fundamental_extracts_2026_h1.jsonl"
OUT_CSV = LOCAL_DIR / "vllm_fundamental_extracts_2026_h1.csv"

API_BASE = os.environ.get("VLLM_API_BASE", "https://vllm-a5000.iii-ei-stack.com/v1")
MODEL = os.environ.get("VLLM_MODEL", "cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit")
API_KEY = os.environ.get("VLLM_API_KEY", "EMPTY")
START_DATE = "2026-01-01"
END_DATE = "2026-06-30"
MAX_EVENTS = int(os.environ.get("VLLM_MAX_EVENTS", "80"))
FORCE_REFRESH = os.environ.get("VLLM_FORCE_REFRESH", "0") == "1"

SYSTEM_PROMPT = """你是台股公開資訊觀測站公告資料抽取器。
請只輸出一個 JSON object，不要 Markdown，不要解釋。
若公告沒有該欄位，填 null。
百分比請用小數，例如 24.91% 輸出 0.2491。
金額保留公告原始單位，不要自行換算。
若表格同時有「最近一月 / 最近一季 / 最近四季累計」，revenue、revenue_yoy_pct、eps、eps_yoy_pct 請只取最近一月欄位。
季資料請不要填到 revenue 或 eps，最近四季累計也不要填到 revenue 或 eps。
"""

USER_TEMPLATE = """請從以下公告抽取結構化基本面資料。

需要輸出的 JSON keys:
event_type, report_period, revenue, revenue_yoy_pct, revenue_mom_pct,
gross_profit, operating_profit, pretax_profit, parent_net_profit,
eps, eps_yoy_pct, gross_margin, operating_margin, net_margin,
is_restatement, is_monthly_revenue, is_financial_business_info,
confidence, notes

公告:
股票: {stock_id} {company_name}
日期時間: {announcement_date} {announcement_time}
主旨: {title}
內容:
{content}
"""


def load_cached_ids() -> set[str]:
    if not OUT_JSONL.exists():
        return set()
    ids = set()
    with OUT_JSONL.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                ids.add(json.loads(line)["event_id"])
            except Exception:
                continue
    return ids


def load_candidate_events() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with EVENTS_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            date_text = obj.get("announcement_date", "")
            if not (START_DATE <= date_text <= END_DATE):
                continue
            text = f"{obj.get('title', '')}\n{obj.get('content', '')}"
            if "營業收入" not in text and "每股盈餘" not in text and "財務業務資訊" not in text:
                continue
            rows.append(obj)
    return rows[:MAX_EVENTS]


def call_vllm(messages: list[dict[str, str]]) -> dict[str, Any]:
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{API_BASE.rstrip('/')}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        method="POST",
    )
    with urlopen(request, timeout=90) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


def normalize_result(event: dict[str, Any], extracted: dict[str, Any]) -> dict[str, Any]:
    row = {
        "event_id": event.get("event_id", ""),
        "stock_id": event.get("stock_id", ""),
        "company_name": event.get("company_name", ""),
        "announcement_date": event.get("announcement_date", ""),
        "announcement_time": event.get("announcement_time", ""),
        "title": str(event.get("title", "")).replace("\r", " ").replace("\n", " "),
    }
    row.update(extracted)
    return row


def append_jsonl(row: dict[str, Any]) -> None:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def export_csv() -> None:
    if not OUT_JSONL.exists():
        return
    rows = [json.loads(line) for line in OUT_JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    if FORCE_REFRESH:
        OUT_JSONL.unlink(missing_ok=True)
        OUT_CSV.unlink(missing_ok=True)
    cached = load_cached_ids()
    events = [event for event in load_candidate_events() if event.get("event_id") not in cached]
    ok = 0
    failed: list[dict[str, str]] = []

    for event in events:
        user_prompt = USER_TEMPLATE.format(
            stock_id=event.get("stock_id", ""),
            company_name=event.get("company_name", ""),
            announcement_date=event.get("announcement_date", ""),
            announcement_time=event.get("announcement_time", ""),
            title=event.get("title", ""),
            content=str(event.get("content", ""))[:6000],
        )
        try:
            extracted = call_vllm(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ]
            )
            append_jsonl(normalize_result(event, extracted))
            ok += 1
            time.sleep(0.2)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
            failed.append({"event_id": event.get("event_id", ""), "error": str(exc)})

    export_csv()
    summary = {
        "model": MODEL,
        "api_base": API_BASE,
        "candidate_events": len(cached) + len(events),
        "cached_before": len(cached),
        "attempted": len(events),
        "ok": ok,
        "failed": failed[:20],
        "jsonl": str(OUT_JSONL),
        "csv": str(OUT_CSV),
    }
    with (LOCAL_DIR / "vllm_extract_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
