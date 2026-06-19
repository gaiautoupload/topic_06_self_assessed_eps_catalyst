from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
DATASET_DIR = Path(r"D:\dataset")
PROCESS_DIR = DATASET_DIR / "processed"
COMPANY_MASTER_CSV = PROCESS_DIR / "company_master.csv"
PRICE_DIR = PROCESS_DIR / "prices"
OUT_DIR = PROJECT_DIR / "project_data" / "full_market_base"
WATCHLIST_DIR = PROJECT_DIR / "project_data" / "fundamental_event_lab" / "watchlist_market_data"
FULL_PRICE_DIR = PROJECT_DIR / "project_data" / "full_market_prices" / "prices"

TWSE_QUOTE = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TWSE_VALUATION = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
TPEX_QUOTE = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
TPEX_VALUATION = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
TWSE_CHIP = "https://www.twse.com.tw/rwd/zh/fund/T86?date={date}&selectType=ALLBUT0999&response=json"
TPEX_CHIP = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?date={date}&type=Daily&response=json"


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
    text = str(value or "").strip().replace(",", "").replace("%", "")
    if text in {"", "-", "--", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def official_stock_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.isdigit() else ""


def fetch_json(url: str) -> dict[str, Any]:
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    company_rows = load_csv(COMPANY_MASTER_CSV)
    price_files = {path.stem for path in PRICE_DIR.glob("*.csv")} | {path.stem for path in FULL_PRICE_DIR.glob("*.csv")}

    # Use the latest official snapshot already fetched for the watchlist as a model for schema.
    watch_snapshot = load_csv(WATCHLIST_DIR / "watchlist_market_snapshot.csv")
    snapshot_date = ""
    for row in watch_snapshot:
        if row.get("chip_date"):
            snapshot_date = row["chip_date"]
            break
    if not snapshot_date:
        import datetime as dt
        snapshot_date = dt.date.today().strftime("%Y%m%d")

    twse_quote = fetch_json(TWSE_QUOTE)
    twse_valuation = fetch_json(TWSE_VALUATION)
    tpex_quote = fetch_json(TPEX_QUOTE)
    tpex_valuation = fetch_json(TPEX_VALUATION)

    def map_twse(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {official_stock_id(row.get("Code")): row for row in rows if official_stock_id(row.get("Code"))}

    def map_tpex(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {official_stock_id(row.get("SecuritiesCompanyCode")): row for row in rows if official_stock_id(row.get("SecuritiesCompanyCode"))}

    twse_quote_map = map_twse(twse_quote)
    tpex_quote_map = map_tpex(tpex_quote)
    twse_val_map = map_twse(twse_valuation)
    tpex_val_map = map_tpex(tpex_valuation)

    def market_for(row: dict[str, str]) -> str:
        market = str(row.get("market", "")).lower()
        if "上" in market or market == "twse":
            return "twse"
        if "櫃" in market or market == "tpex":
            return "tpex"
        return "twse" if row.get("security_type") == "股票" else "tpex"

    rows: list[dict[str, Any]] = []
    for row in company_rows:
        stock_id = row.get("stock_id", "")
        market = market_for(row)
        quote = twse_quote_map.get(stock_id, {}) if market == "twse" else tpex_quote_map.get(stock_id, {})
        val = twse_val_map.get(stock_id, {}) if market == "twse" else tpex_val_map.get(stock_id, {})
        rows.append(
            {
                "stock_id": stock_id,
                "company_name": row.get("company_name", ""),
                "market": market,
                "industry": row.get("industry", ""),
                "security_type": row.get("security_type", ""),
                "listed_date": row.get("listed_date", ""),
                "isin": row.get("isin", ""),
                "quote_date": quote.get("Date") or quote.get("quote_date", ""),
                "close": parse_float(quote.get("ClosingPrice") if market == "twse" else quote.get("Close")),
                "change": parse_float(quote.get("Change")),
                "volume_shares": parse_float(quote.get("TradeVolume") if market == "twse" else quote.get("TradingShares")),
                "valuation_date": val.get("Date") or val.get("valuation_date", ""),
                "pe_ratio": parse_float(val.get("PEratio") if market == "twse" else val.get("PriceEarningRatio")),
                "pb_ratio": parse_float(val.get("PBratio") if market == "twse" else val.get("PriceBookRatio")),
                "dividend_yield_pct": parse_float(val.get("DividendYield") if market == "twse" else val.get("YieldRatio")),
                "chip_date": snapshot_date if (stock_id in twse_quote_map or stock_id in tpex_quote_map) else "",
                "has_price_file": stock_id in price_files,
                "price_file": str((FULL_PRICE_DIR / f"{stock_id}.csv") if (FULL_PRICE_DIR / f"{stock_id}.csv").exists() else (PRICE_DIR / f"{stock_id}.csv")) if stock_id in price_files else "",
            }
        )

    # Pull latest chip snapshot for all market stocks.
    chip_rows: list[dict[str, Any]] = []
    if snapshot_date:
        try:
            twse_chip = fetch_json(TWSE_CHIP.format(date=snapshot_date))
            fields = twse_chip.get("fields", [])
            data = twse_chip.get("data", [])
            idx = {name: i for i, name in enumerate(fields)}

            def get(row: list[Any], name: str) -> Any:
                i = idx.get(name)
                return row[i] if i is not None and i < len(row) else None

            for row in data:
                stock_id = official_stock_id(row[0] if row else "")
                if not stock_id:
                    continue
                chip_rows.append(
                    {
                        "stock_id": stock_id,
                        "market": "twse",
                        "chip_date": snapshot_date,
                        "foreign_net_buy_shares": parse_float(get(row, "外陸資買賣超股數(不含外資自營商)")),
                        "investment_trust_net_buy_shares": parse_float(get(row, "投信買賣超股數")),
                        "dealer_net_buy_shares": parse_float(get(row, "自營商買賣超股數")),
                        "institutional_total_net_buy_shares": parse_float(get(row, "三大法人買賣超股數")),
                    }
                )
        except Exception:
            pass
        try:
            tpex_chip = fetch_json(TPEX_CHIP.format(date=f"{snapshot_date[:4]}/{snapshot_date[4:6]}/{snapshot_date[6:8]}"))
            tables = tpex_chip.get("tables", [])
            data = tables[0].get("data", []) if tables else []
            for row in data:
                stock_id = official_stock_id(row[0] if row else "")
                if not stock_id:
                    continue
                chip_rows.append(
                    {
                        "stock_id": stock_id,
                        "market": "tpex",
                        "chip_date": snapshot_date,
                        "foreign_net_buy_shares": parse_float(row[10] if len(row) > 10 else None),
                        "investment_trust_net_buy_shares": parse_float(row[13] if len(row) > 13 else None),
                        "dealer_net_buy_shares": parse_float(row[22] if len(row) > 22 else None),
                        "institutional_total_net_buy_shares": parse_float(row[23] if len(row) > 23 else None),
                    }
                )
        except Exception:
            pass

    chips_by_id = {row["stock_id"]: row for row in chip_rows if row.get("stock_id")}
    for row in rows:
        chip = chips_by_id.get(row["stock_id"], {})
        row["foreign_net_buy_shares"] = chip.get("foreign_net_buy_shares")
        row["investment_trust_net_buy_shares"] = chip.get("investment_trust_net_buy_shares")
        row["dealer_net_buy_shares"] = chip.get("dealer_net_buy_shares")
        row["institutional_total_net_buy_shares"] = chip.get("institutional_total_net_buy_shares")

    out_csv = OUT_DIR / "full_market_base.csv"
    write_csv(
        out_csv,
        rows,
        [
            "stock_id",
            "company_name",
            "market",
            "industry",
            "security_type",
            "listed_date",
            "isin",
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
            "has_price_file",
            "price_file",
        ],
    )
    summary = {
        "companies": len(company_rows),
        "rows": len(rows),
        "price_files": len(price_files),
        "with_price_file": sum(1 for row in rows if row["has_price_file"]),
        "with_quote": sum(1 for row in rows if row.get("close") is not None),
        "with_valuation": sum(1 for row in rows if row.get("pe_ratio") is not None or row.get("pb_ratio") is not None),
        "with_chip": sum(1 for row in rows if row.get("foreign_net_buy_shares") is not None),
        "snapshot_date": snapshot_date,
        "output_csv": str(out_csv),
    }
    (OUT_DIR / "full_market_base_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
