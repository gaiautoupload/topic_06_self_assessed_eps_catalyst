from __future__ import annotations

import csv
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
LAB_DIR = PROJECT_ROOT / "project_data" / "fundamental_event_lab"
OUTPUT_DIR = LAB_DIR / "watchlist_market_data"
DATASET_ROOT = Path("D:/dataset")

WATCHLIST_SOURCES = [
    LAB_DIR / "fundamental_events_2026_h1.csv",
    PROJECT_ROOT / "project_data" / "2026_h1" / "main_strategy_events.csv",
    LAB_DIR / "watchlist.csv",
]

OFFICIAL_ENDPOINTS = {
    "twse_quote": "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
    "twse_valuation": "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
    "tpex_quote": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes",
    "tpex_valuation": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
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


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if text in {"", "-", "--", "N/A", "NA", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_stock_id(value: Any) -> str:
    match = re.search(r"\d{4,6}", str(value or ""))
    return match.group(0) if match else ""


def official_stock_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"\d{4,6}", text) else ""


def collect_watchlist() -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    for source in WATCHLIST_SOURCES:
        for row in read_csv_rows(source):
            stock_id = normalize_stock_id(row.get("stock_id") or row.get("Code") or row.get("SecuritiesCompanyCode"))
            if not stock_id:
                continue
            item = seen.setdefault(
                stock_id,
                {
                    "stock_id": stock_id,
                    "company_name": "",
                    "sources": "",
                    "event_count": "0",
                },
            )
            company_name = row.get("company_name") or row.get("Name") or row.get("CompanyName") or ""
            if company_name and not item["company_name"]:
                item["company_name"] = company_name
            source_name = source.relative_to(PROJECT_ROOT).as_posix()
            sources = set(filter(None, item["sources"].split(";")))
            sources.add(source_name)
            item["sources"] = ";".join(sorted(sources))
            item["event_count"] = str(int(item["event_count"]) + 1)
    return sorted(seen.values(), key=lambda row: row["stock_id"])


def fetch_json(url: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read().decode("utf-8-sig")
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError(f"Expected list payload from {url}")
    return data


def fetch_json_object(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read().decode("utf-8-sig")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object payload from {url}")
    return data


def roc_date_to_ad(value: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{7}", text):
        year = int(text[:3]) + 1911
        return f"{year}{text[3:5]}{text[5:7]}"
    if re.fullmatch(r"\d{8}", text):
        return text
    return ""


def normalize_quote(row: dict[str, Any], market: str) -> dict[str, Any]:
    if market == "twse":
        return {
            "stock_id": official_stock_id(row.get("Code")),
            "company_name": row.get("Name", ""),
            "market": "twse",
            "quote_date": row.get("Date", ""),
            "open": parse_number(row.get("OpeningPrice")),
            "high": parse_number(row.get("HighestPrice")),
            "low": parse_number(row.get("LowestPrice")),
            "close": parse_number(row.get("ClosingPrice")),
            "change": parse_number(row.get("Change")),
            "volume_shares": parse_number(row.get("TradeVolume")),
            "turnover_value": parse_number(row.get("TradeValue")),
            "transactions": parse_number(row.get("Transaction")),
        }
    return {
        "stock_id": official_stock_id(row.get("SecuritiesCompanyCode")),
        "company_name": row.get("CompanyName", ""),
        "market": "tpex",
        "quote_date": row.get("Date", ""),
        "open": parse_number(row.get("Open")),
        "high": parse_number(row.get("High")),
        "low": parse_number(row.get("Low")),
        "close": parse_number(row.get("Close")),
        "change": parse_number(row.get("Change")),
        "volume_shares": parse_number(row.get("TradingShares")),
        "turnover_value": parse_number(row.get("TransactionAmount")),
        "transactions": parse_number(row.get("TransactionNumber")),
    }


def normalize_valuation(row: dict[str, Any], market: str) -> dict[str, Any]:
    if market == "twse":
        return {
            "stock_id": official_stock_id(row.get("Code")),
            "company_name": row.get("Name", ""),
            "market": "twse",
            "valuation_date": row.get("Date", ""),
            "pe_ratio": parse_number(row.get("PEratio")),
            "pb_ratio": parse_number(row.get("PBratio")),
            "dividend_yield_pct": parse_number(row.get("DividendYield")),
        }
    return {
        "stock_id": official_stock_id(row.get("SecuritiesCompanyCode")),
        "company_name": row.get("CompanyName", ""),
        "market": "tpex",
        "valuation_date": row.get("Date", ""),
        "pe_ratio": parse_number(row.get("PriceEarningRatio")),
        "pb_ratio": parse_number(row.get("PriceBookRatio")),
        "dividend_yield_pct": parse_number(row.get("YieldRatio")),
    }


def fetch_twse_chip(ad_date: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={ad_date}&selectType=ALLBUT0999&response=json"
    payload = fetch_json_object(url)
    fields = payload.get("fields", [])
    rows = payload.get("data", [])
    field_index = {name: idx for idx, name in enumerate(fields)}

    def get(row: list[Any], name: str) -> Any:
        index = field_index.get(name)
        return row[index] if index is not None and index < len(row) else None

    chip_rows = []
    for row in rows:
        stock_id = official_stock_id(row[0] if row else "")
        if not stock_id:
            continue
        chip_rows.append(
            {
                "stock_id": stock_id,
                "company_name": row[1].strip() if len(row) > 1 else "",
                "market": "twse",
                "chip_date": ad_date,
                "foreign_net_buy_shares": parse_number(get(row, "外陸資買賣超股數(不含外資自營商)")),
                "investment_trust_net_buy_shares": parse_number(get(row, "投信買賣超股數")),
                "dealer_net_buy_shares": parse_number(get(row, "自營商買賣超股數")),
                "institutional_total_net_buy_shares": parse_number(get(row, "三大法人買賣超股數")),
            }
        )
    return chip_rows, {"ok": payload.get("stat") == "OK", "rows": len(chip_rows), "url": url}


def fetch_tpex_chip(ad_date: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    date_with_slashes = f"{ad_date[:4]}/{ad_date[4:6]}/{ad_date[6:8]}"
    url = f"https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?date={date_with_slashes}&type=Daily&response=json"
    payload = fetch_json_object(url)
    tables = payload.get("tables", [])
    table = tables[0] if tables else {}
    rows = table.get("data", [])
    chip_rows = []
    for row in rows:
        stock_id = official_stock_id(row[0] if row else "")
        if not stock_id:
            continue
        # TPEX repeats generic field names by investor group. The current table layout is:
        # code/name, foreign excl. dealer, foreign dealer, foreign total, investment trust,
        # dealer self, dealer hedge, dealer total, grand total.
        chip_rows.append(
            {
                "stock_id": stock_id,
                "company_name": row[1].strip() if len(row) > 1 else "",
                "market": "tpex",
                "chip_date": ad_date,
                "foreign_net_buy_shares": parse_number(row[10] if len(row) > 10 else None),
                "investment_trust_net_buy_shares": parse_number(row[13] if len(row) > 13 else None),
                "dealer_net_buy_shares": parse_number(row[22] if len(row) > 22 else None),
                "institutional_total_net_buy_shares": parse_number(row[23] if len(row) > 23 else None),
            }
        )
    return chip_rows, {"ok": bool(rows), "rows": len(chip_rows), "url": url}


def local_price_file_status(stock_id: str) -> dict[str, Any]:
    candidates = [
        DATASET_ROOT / "processed" / "prices" / f"{stock_id}.csv",
        DATASET_ROOT / "prices" / f"{stock_id}.csv",
    ]
    for path in candidates:
        if path.exists():
            return {"local_price_file": str(path), "has_local_price_file": True}
    return {"local_price_file": "", "has_local_price_file": False}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now().isoformat(timespec="seconds")

    watchlist = collect_watchlist()
    watch_ids = {row["stock_id"] for row in watchlist}

    endpoint_status: dict[str, Any] = {}
    raw_payloads: dict[str, list[dict[str, Any]]] = {}
    for key, url in OFFICIAL_ENDPOINTS.items():
        try:
            rows = fetch_json(url)
            raw_payloads[key] = rows
            endpoint_status[key] = {"ok": True, "rows": len(rows), "url": url}
        except Exception as exc:  # noqa: BLE001 - keep batch fetch resilient.
            raw_payloads[key] = []
            endpoint_status[key] = {"ok": False, "error": str(exc), "url": url}

    quote_rows = [
        normalize_quote(row, "twse")
        for row in raw_payloads["twse_quote"]
        if official_stock_id(row.get("Code")) in watch_ids
    ]
    quote_rows.extend(
        normalize_quote(row, "tpex")
        for row in raw_payloads["tpex_quote"]
        if official_stock_id(row.get("SecuritiesCompanyCode")) in watch_ids
    )

    valuation_rows = [
        normalize_valuation(row, "twse")
        for row in raw_payloads["twse_valuation"]
        if official_stock_id(row.get("Code")) in watch_ids
    ]
    valuation_rows.extend(
        normalize_valuation(row, "tpex")
        for row in raw_payloads["tpex_valuation"]
        if official_stock_id(row.get("SecuritiesCompanyCode")) in watch_ids
    )

    quotes_by_id = {row["stock_id"]: row for row in quote_rows if row["stock_id"]}
    valuation_by_id = {row["stock_id"]: row for row in valuation_rows if row["stock_id"]}

    latest_ad_date = ""
    for row in quote_rows:
        latest_ad_date = roc_date_to_ad(str(row.get("quote_date") or ""))
        if latest_ad_date:
            break

    chip_rows: list[dict[str, Any]] = []
    chip_endpoint_status: dict[str, Any] = {}
    if latest_ad_date:
        try:
            twse_chip_rows, chip_endpoint_status["twse_chip"] = fetch_twse_chip(latest_ad_date)
            chip_rows.extend(row for row in twse_chip_rows if row["stock_id"] in watch_ids)
        except Exception as exc:  # noqa: BLE001 - keep snapshot generation resilient.
            chip_endpoint_status["twse_chip"] = {"ok": False, "error": str(exc)}
        try:
            tpex_chip_rows, chip_endpoint_status["tpex_chip"] = fetch_tpex_chip(latest_ad_date)
            chip_rows.extend(row for row in tpex_chip_rows if row["stock_id"] in watch_ids)
        except Exception as exc:  # noqa: BLE001 - keep snapshot generation resilient.
            chip_endpoint_status["tpex_chip"] = {"ok": False, "error": str(exc)}
    chips_by_id = {row["stock_id"]: row for row in chip_rows if row["stock_id"]}

    snapshot_rows: list[dict[str, Any]] = []
    for item in watchlist:
        stock_id = item["stock_id"]
        quote = quotes_by_id.get(stock_id, {})
        valuation = valuation_by_id.get(stock_id, {})
        chip = chips_by_id.get(stock_id, {})
        local_price = local_price_file_status(stock_id)
        snapshot_rows.append(
            {
                **item,
                "market": quote.get("market") or valuation.get("market") or "",
                "quote_date": quote.get("quote_date", ""),
                "close": quote.get("close"),
                "change": quote.get("change"),
                "volume_shares": quote.get("volume_shares"),
                "valuation_date": valuation.get("valuation_date", ""),
                "pe_ratio": valuation.get("pe_ratio"),
                "pb_ratio": valuation.get("pb_ratio"),
                "dividend_yield_pct": valuation.get("dividend_yield_pct"),
                "chip_date": chip.get("chip_date", ""),
                "foreign_net_buy_shares": chip.get("foreign_net_buy_shares"),
                "investment_trust_net_buy_shares": chip.get("investment_trust_net_buy_shares"),
                "dealer_net_buy_shares": chip.get("dealer_net_buy_shares"),
                "institutional_total_net_buy_shares": chip.get("institutional_total_net_buy_shares"),
                **local_price,
                "fetched_at": fetched_at,
            }
        )

    write_csv(OUTPUT_DIR / "watchlist.csv", watchlist, ["stock_id", "company_name", "sources", "event_count"])
    write_csv(
        OUTPUT_DIR / "watchlist_quotes.csv",
        quote_rows,
        [
            "stock_id",
            "company_name",
            "market",
            "quote_date",
            "open",
            "high",
            "low",
            "close",
            "change",
            "volume_shares",
            "turnover_value",
            "transactions",
        ],
    )
    write_csv(
        OUTPUT_DIR / "watchlist_valuation.csv",
        valuation_rows,
        [
            "stock_id",
            "company_name",
            "market",
            "valuation_date",
            "pe_ratio",
            "pb_ratio",
            "dividend_yield_pct",
        ],
    )
    write_csv(
        OUTPUT_DIR / "watchlist_chips.csv",
        chip_rows,
        [
            "stock_id",
            "company_name",
            "market",
            "chip_date",
            "foreign_net_buy_shares",
            "investment_trust_net_buy_shares",
            "dealer_net_buy_shares",
            "institutional_total_net_buy_shares",
        ],
    )
    write_csv(
        OUTPUT_DIR / "watchlist_market_snapshot.csv",
        snapshot_rows,
        [
            "stock_id",
            "company_name",
            "sources",
            "event_count",
            "market",
            "quote_date",
            "close",
            "change",
            "volume_shares",
            "valuation_date",
            "pe_ratio",
            "pb_ratio",
            "dividend_yield_pct",
            "chip_date",
            "foreign_net_buy_shares",
            "investment_trust_net_buy_shares",
            "dealer_net_buy_shares",
            "institutional_total_net_buy_shares",
            "has_local_price_file",
            "local_price_file",
            "fetched_at",
        ],
    )

    chip_status = {
        "status": "ok" if chip_rows else "missing",
        "date": latest_ad_date,
        "rows": len(chip_rows),
        "endpoint_status": chip_endpoint_status,
    }

    summary = {
        "fetched_at": fetched_at,
        "watchlist_count": len(watchlist),
        "quote_rows": len(quote_rows),
        "valuation_rows": len(valuation_rows),
        "chip_rows": len(chip_rows),
        "snapshot_rows": len(snapshot_rows),
        "local_price_file_count": sum(1 for row in snapshot_rows if row["has_local_price_file"]),
        "endpoint_status": endpoint_status,
        "chip_status": chip_status,
        "outputs": {
            "watchlist": str(OUTPUT_DIR / "watchlist.csv"),
            "quotes": str(OUTPUT_DIR / "watchlist_quotes.csv"),
            "valuation": str(OUTPUT_DIR / "watchlist_valuation.csv"),
            "chips": str(OUTPUT_DIR / "watchlist_chips.csv"),
            "snapshot": str(OUTPUT_DIR / "watchlist_market_snapshot.csv"),
            "summary": str(OUTPUT_DIR / "market_data_fetch_summary.json"),
        },
    }
    (OUTPUT_DIR / "market_data_fetch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
