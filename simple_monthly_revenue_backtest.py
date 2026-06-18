from __future__ import annotations

import csv
import html
import json
import re
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fetch_watchlist_market_data import fetch_tpex_chip, fetch_twse_chip
from strategy_config import load_brain_rule_config


PROJECT_ROOT = Path(__file__).resolve().parent
OUT_DIR = PROJECT_ROOT / "project_data" / "simple_monthly_revenue"
REVENUE_CSV = OUT_DIR / "monthly_revenue_2026_to_date.csv"
CHIP_CSV = OUT_DIR / "event_chips.csv"
PRICE_DIR = OUT_DIR / "prices"
RESULT_CSV = OUT_DIR / "parameter_results.csv"
TRADE_CSV = OUT_DIR / "best_trades.csv"
SUMMARY_JSON = OUT_DIR / "summary.json"

REVENUE_MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
MARKETS = {"listed": "sii", "otc": "otc"}

MOM_THRESHOLDS = [0.0, 0.10, 0.20, 0.30, 0.50]
YOY_THRESHOLDS = [0.0, 0.10, 0.20, 0.30, 0.50]
FOREIGN_BUY_THRESHOLDS = [None, 0.0, 100_000.0, 500_000.0, 1_000_000.0]
TRUST_BUY_THRESHOLDS = [None, 0.0, 50_000.0, 100_000.0]
BREAKOUT_DAYS_VALUES = [0, 60, 120]
VOLUME_RATIO_VALUES = [0.0, 1.5, 2.0, 3.0]
TOP_N_VALUES = [5]
EXIT_RULES = ["month_end", "next_month_5", "next_month_10"]
MONTHLY_CAPITAL = 1_000_000.0
TARGET_MONTHLY_POSITIONS = 5


@dataclass
class RevenueRow:
    event_id: str
    revenue_month: str
    announcement_date: str
    announcement_time: str
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


@dataclass
class Trade:
    parameter_id: str
    revenue_month: str
    stock_id: str
    company_name: str
    announcement_date: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    exit_status: str
    allocation_amount: float
    return_pct: float
    pnl_amount: float
    mom_pct: float | None
    yoy_pct: float | None
    foreign_net_buy_shares: float | None
    investment_trust_net_buy_shares: float | None
    breakout_days: int
    volume_ratio_20d: float | None


def parse_number(value: Any) -> float | None:
    text = str(value or "").replace(",", "").replace("+", "").strip()
    if text in {"", "-", "--", "X", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def request_text(url: str, encoding: str = "utf-8") -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode(encoding, errors="replace")


def request_json(url: str) -> dict[str, Any]:
    return json.loads(request_text(url, "utf-8-sig"))


def next_month_10(revenue_month: str) -> str:
    year, month = [int(part) for part in revenue_month.split("-")]
    if month == 12:
        return f"{year + 1:04d}-01-10"
    return f"{year:04d}-{month + 1:02d}-10"


def roc_date_to_iso(value: str) -> str:
    parts = value.split("/")
    return f"{int(parts[0]) + 1911:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def revenue_url(revenue_month: str, market_code: str) -> str:
    year, month = [int(part) for part in revenue_month.split("-")]
    return f"https://mopsov.twse.com.tw/nas/t21/{market_code}/t21sc03_{year - 1911}_{month}.html"


def parse_revenue_html(text: str, revenue_month: str, market: str, source_url: str) -> list[RevenueRow]:
    rows: list[RevenueRow] = []
    for tr in re.findall(r"<tr[^>]*align=right[^>]*>(.*?)</tr>", text, flags=re.I | re.S):
        cells = [
            html.unescape(re.sub(r"<.*?>", "", cell, flags=re.S)).replace("\xa0", " ").strip()
            for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.I | re.S)
        ]
        if len(cells) < 10 or not re.fullmatch(r"\d{4,6}", cells[0]):
            continue
        stock_id = cells[0]
        announcement_date = next_month_10(revenue_month)
        rows.append(
            RevenueRow(
                event_id=f"revenue_{revenue_month.replace('-', '')}_{stock_id}",
                revenue_month=revenue_month,
                announcement_date=announcement_date,
                announcement_time="after_close",
                market=market,
                stock_id=stock_id,
                company_name=cells[1],
                current_month_revenue=parse_number(cells[2]),
                previous_month_revenue=parse_number(cells[3]),
                previous_year_month_revenue=parse_number(cells[4]),
                mom_pct=(parse_number(cells[5]) / 100.0) if parse_number(cells[5]) is not None else None,
                yoy_pct=(parse_number(cells[6]) / 100.0) if parse_number(cells[6]) is not None else None,
                cumulative_revenue=parse_number(cells[7]),
                previous_year_cumulative_revenue=parse_number(cells[8]),
                cumulative_yoy_pct=(parse_number(cells[9]) / 100.0) if parse_number(cells[9]) is not None else None,
                note=cells[10] if len(cells) > 10 else "",
                source_url=source_url,
            )
        )
    return rows


def load_csv(path: Path) -> list[dict[str, str]]:
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


def build_revenue_database(refresh: bool = False) -> list[dict[str, str]]:
    if REVENUE_CSV.exists() and not refresh:
        return load_csv(REVENUE_CSV)
    rows: list[RevenueRow] = []
    failures = []
    for revenue_month in REVENUE_MONTHS:
        for market, market_code in MARKETS.items():
            url = revenue_url(revenue_month, market_code)
            try:
                rows.extend(parse_revenue_html(request_text(url, "big5"), revenue_month, market, url))
            except Exception as exc:  # noqa: BLE001
                failures.append({"revenue_month": revenue_month, "market": market, "error": str(exc), "url": url})
    write_csv(REVENUE_CSV, [asdict(row) for row in rows], list(RevenueRow.__dataclass_fields__.keys()))
    (OUT_DIR / "monthly_revenue_fetch_summary.json").write_text(
        json.dumps({"rows": len(rows), "failures": failures}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return load_csv(REVENUE_CSV)


def fetch_chip_for_date(ad_date: str) -> list[dict[str, Any]]:
    yyyymmdd = ad_date.replace("-", "")
    rows: list[dict[str, Any]] = []
    twse_rows, _ = fetch_twse_chip(yyyymmdd)
    tpex_rows, _ = fetch_tpex_chip(yyyymmdd)
    rows.extend(twse_rows)
    rows.extend(tpex_rows)
    return rows


def build_chip_database(events: list[dict[str, str]], refresh: bool = False) -> dict[tuple[str, str], dict[str, str]]:
    if CHIP_CSV.exists() and not refresh:
        chip_rows = load_csv(CHIP_CSV)
    else:
        chip_rows = []
        by_date = sorted({row["announcement_date"] for row in events})
        for announcement_date in by_date:
            lookup_date = date.fromisoformat(announcement_date)
            chips = []
            used_date = ""
            for _ in range(8):
                try:
                    chips = fetch_chip_for_date(lookup_date.isoformat())
                    if chips:
                        used_date = lookup_date.isoformat()
                        break
                except Exception:
                    pass
                lookup_date -= timedelta(days=1)
            for chip in chips:
                chip_rows.append({**chip, "announcement_date": announcement_date, "used_chip_date": used_date})
        write_csv(
            CHIP_CSV,
            chip_rows,
            [
                "announcement_date",
                "used_chip_date",
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
    return {(row["announcement_date"], row["stock_id"]): row for row in chip_rows}


def fetch_price_month(stock_id: str, market: str, yyyymm: str) -> list[dict[str, Any]]:
    if market == "otc":
        url = f"https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?code={stock_id}&date={yyyymm[:4]}/{yyyymm[4:]}/01&response=json"
        data = request_json(url)
        tables = data.get("tables") or []
        source_rows = tables[0].get("data", []) if tables else []
        return [
            {
                "trade_date": roc_date_to_iso(row[0]),
                "stock_id": stock_id,
                "open": parse_number(row[3]),
                "high": parse_number(row[4]),
                "low": parse_number(row[5]),
                "close": parse_number(row[6]),
                "volume": int((parse_number(row[1]) or 0) * 1000),
                "turnover": int((parse_number(row[2]) or 0) * 1000),
                "trades": int(parse_number(row[8]) or 0),
                "market": "otc",
            }
            for row in source_rows
        ]
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={yyyymm}01&stockNo={stock_id}&response=json"
    data = request_json(url)
    if data.get("stat") != "OK":
        return []
    return [
        {
            "trade_date": roc_date_to_iso(row[0]),
            "stock_id": stock_id,
            "open": parse_number(row[3]),
            "high": parse_number(row[4]),
            "low": parse_number(row[5]),
            "close": parse_number(row[6]),
            "volume": int(parse_number(row[1]) or 0),
            "turnover": int(parse_number(row[2]) or 0),
            "trades": int(parse_number(row[8]) or 0),
            "market": "listed",
        }
        for row in data.get("data", [])
    ]


def yyyymm_range(start: str, end: str) -> list[str]:
    cursor = date.fromisoformat(start).replace(day=1)
    end_date = date.fromisoformat(end).replace(day=1)
    values = []
    while cursor <= end_date:
        values.append(cursor.strftime("%Y%m"))
        year = cursor.year + (cursor.month == 12)
        month = 1 if cursor.month == 12 else cursor.month + 1
        cursor = date(year, month, 1)
    return values


def load_or_fetch_prices(stock_id: str, market: str) -> list[dict[str, str]]:
    path = PRICE_DIR / f"{stock_id}.csv"
    if path.exists():
        return load_csv(path)
    rows: list[dict[str, Any]] = []
    for yyyymm in yyyymm_range("2026-01-01", "2026-06-18"):
        try:
            rows.extend(fetch_price_month(stock_id, market, yyyymm))
        except Exception:
            continue
    rows_by_date = {row["trade_date"]: row for row in rows}
    ordered = [rows_by_date[key] for key in sorted(rows_by_date)]
    write_csv(path, ordered, ["trade_date", "stock_id", "open", "high", "low", "close", "volume", "turnover", "trades", "market"])
    return load_csv(path)


def first_trade_after(prices: list[dict[str, str]], after_date: str) -> int | None:
    for idx, row in enumerate(prices):
        if row["trade_date"] > after_date:
            return idx
    return None


def exit_index(prices: list[dict[str, str]], entry_idx: int, rule: str) -> tuple[int, str] | None:
    entry_month = prices[entry_idx]["trade_date"][:7]
    if rule == "month_end":
        idx = entry_idx
        finalized = False
        for i in range(entry_idx, len(prices)):
            if prices[i]["trade_date"][:7] != entry_month:
                finalized = True
                break
            idx = i
        return idx, "final" if finalized else "as_of_latest"
    next_month = (date.fromisoformat(prices[entry_idx]["trade_date"]).replace(day=28) + timedelta(days=4)).replace(day=1).strftime("%Y-%m")
    wanted = int(rule.rsplit("_", 1)[1])
    indices = [i for i, row in enumerate(prices) if row["trade_date"][:7] == next_month]
    if len(indices) < wanted:
        return None
    return indices[wanted - 1], "final"


def price_features(prices: list[dict[str, str]], entry_idx: int, breakout_days: int) -> tuple[bool, float | None]:
    lookback = prices[max(0, entry_idx - max(breakout_days, 20)):entry_idx]
    if not lookback:
        return False, None
    entry_close = parse_number(prices[entry_idx].get("close")) or parse_number(prices[entry_idx].get("open"))
    highs = [parse_number(row.get("high")) for row in lookback[-breakout_days:]] if breakout_days else []
    is_breakout = True if breakout_days == 0 else bool(entry_close is not None and highs and entry_close >= max(v for v in highs if v is not None))
    recent_volumes = [parse_number(row.get("volume")) for row in lookback[-20:]]
    avg_volume = sum(v for v in recent_volumes if v is not None) / len([v for v in recent_volumes if v is not None]) if recent_volumes else None
    entry_volume = parse_number(prices[entry_idx].get("volume"))
    volume_ratio = (entry_volume / avg_volume) if entry_volume is not None and avg_volume else None
    return is_breakout, volume_ratio


def enriched_candidates(rows: list[dict[str, str]], chips: dict[tuple[str, str], dict[str, str]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        chip = chips.get((row["announcement_date"], row["stock_id"]), {})
        output.append(
            {
                **row,
                "mom_pct": parse_number(row.get("mom_pct")),
                "yoy_pct": parse_number(row.get("yoy_pct")),
                "current_month_revenue": parse_number(row.get("current_month_revenue")),
                "foreign_net_buy_shares": parse_number(chip.get("foreign_net_buy_shares")),
                "investment_trust_net_buy_shares": parse_number(chip.get("investment_trust_net_buy_shares")),
                "institutional_total_net_buy_shares": parse_number(chip.get("institutional_total_net_buy_shares")),
            }
        )
    return output


def passes_base(row: dict[str, Any], mom_min: float, yoy_min: float, foreign_min: float | None, trust_min: float | None) -> bool:
    if row["mom_pct"] is None or row["mom_pct"] < mom_min:
        return False
    if row["yoy_pct"] is None or row["yoy_pct"] < yoy_min:
        return False
    if foreign_min is not None and (row["foreign_net_buy_shares"] is None or row["foreign_net_buy_shares"] < foreign_min):
        return False
    if trust_min is not None and (row["investment_trust_net_buy_shares"] is None or row["investment_trust_net_buy_shares"] < trust_min):
        return False
    return True


def parameter_id(mom: float, yoy: float, foreign: float | None, trust: float | None, breakout: int, volume: float, top_n: int, exit_rule: str) -> str:
    foreign_label = "any" if foreign is None else f"{int(foreign / 1000)}k"
    trust_label = "any" if trust is None else f"{int(trust / 1000)}k"
    return f"mom{int(mom*100)}_yoy{int(yoy*100)}_foreign{foreign_label}_trust{trust_label}_high{breakout}_vol{volume}_top{top_n}_{exit_rule}"


def run_backtest(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[Trade]]]:
    results = []
    trades_by_param: dict[str, list[Trade]] = {}
    price_cache: dict[str, list[dict[str, str]]] = {}
    _ = load_brain_rule_config()
    candidate_seed = [
        row for row in rows
        if row["mom_pct"] is not None
        and row["yoy_pct"] is not None
        and row["mom_pct"] >= 0
        and row["yoy_pct"] >= 0
        and ((row["foreign_net_buy_shares"] or 0) > 0 or (row["investment_trust_net_buy_shares"] or 0) > 0)
    ]

    prepared_by_breakout: dict[int, list[dict[str, Any]]] = {value: [] for value in BREAKOUT_DAYS_VALUES}
    for row in candidate_seed:
        prices = price_cache.setdefault(row["stock_id"], load_or_fetch_prices(row["stock_id"], row["market"]))
        entry_idx = first_trade_after(prices, row["announcement_date"]) if prices else None
        if entry_idx is None:
            continue
        for breakout_days in BREAKOUT_DAYS_VALUES:
            is_breakout, volume_ratio = price_features(prices, entry_idx, breakout_days)
            prepared_by_breakout[breakout_days].append(
                {
                    **row,
                    "is_breakout": is_breakout,
                    "volume_ratio_20d": volume_ratio,
                    "entry_idx": entry_idx,
                }
            )

    for mom_min in MOM_THRESHOLDS:
        for yoy_min in YOY_THRESHOLDS:
            for foreign_min in FOREIGN_BUY_THRESHOLDS:
                for trust_min in TRUST_BUY_THRESHOLDS:
                    for breakout_days in BREAKOUT_DAYS_VALUES:
                        base = [
                            row for row in prepared_by_breakout[breakout_days]
                            if passes_base(row, mom_min, yoy_min, foreign_min, trust_min)
                        ]
                        for volume_min in VOLUME_RATIO_VALUES:
                            filtered = [
                                row for row in base
                                if row["is_breakout"] and (volume_min == 0.0 or ((row["volume_ratio_20d"] or 0.0) >= volume_min))
                            ]
                            for top_n in TOP_N_VALUES:
                                selected = []
                                by_month: dict[str, list[dict[str, Any]]] = {}
                                for row in filtered:
                                    by_month.setdefault(row["announcement_date"][:7], []).append(row)
                                for month_rows in by_month.values():
                                    selected.extend(
                                        sorted(
                                            month_rows,
                                            key=lambda row: (
                                                -(row["mom_pct"] or 0),
                                                -(row["yoy_pct"] or 0),
                                                -(row["foreign_net_buy_shares"] or 0),
                                                row["stock_id"],
                                            ),
                                        )[:top_n]
                                    )
                                for exit_rule in EXIT_RULES:
                                    pid = parameter_id(mom_min, yoy_min, foreign_min, trust_min, breakout_days, volume_min, top_n, exit_rule)
                                    trades: list[Trade] = []
                                    for row in selected:
                                        prices = price_cache[row["stock_id"]]
                                        entry_idx = row["entry_idx"]
                                        if entry_idx is None:
                                            continue
                                        result = exit_index(prices, entry_idx, exit_rule)
                                        if result is None:
                                            continue
                                        out_idx, exit_status = result
                                        entry_price = parse_number(prices[entry_idx].get("open"))
                                        exit_price = parse_number(prices[out_idx].get("close"))
                                        if not entry_price or exit_price is None:
                                            continue
                                        allocation = MONTHLY_CAPITAL / max(1, len([r for r in selected if r["announcement_date"][:7] == row["announcement_date"][:7]]))
                                        return_pct = (exit_price - entry_price) / entry_price
                                        trades.append(
                                            Trade(
                                                parameter_id=pid,
                                                revenue_month=row["revenue_month"],
                                                stock_id=row["stock_id"],
                                                company_name=row["company_name"],
                                                announcement_date=row["announcement_date"],
                                                entry_date=prices[entry_idx]["trade_date"],
                                                entry_price=entry_price,
                                                exit_date=prices[out_idx]["trade_date"],
                                                exit_price=exit_price,
                                                exit_status=exit_status,
                                                allocation_amount=round(allocation, 2),
                                                return_pct=round(return_pct, 6),
                                                pnl_amount=round(allocation * return_pct, 2),
                                                mom_pct=row["mom_pct"],
                                                yoy_pct=row["yoy_pct"],
                                                foreign_net_buy_shares=row["foreign_net_buy_shares"],
                                                investment_trust_net_buy_shares=row["investment_trust_net_buy_shares"],
                                                breakout_days=breakout_days,
                                                volume_ratio_20d=row["volume_ratio_20d"],
                                            )
                                        )
                                    returns = [trade.return_pct for trade in trades]
                                    pnl = sum(trade.pnl_amount for trade in trades)
                                    invested = sum(trade.allocation_amount for trade in trades)
                                    selected_by_month: dict[str, int] = {}
                                    trades_by_month: dict[str, int] = {}
                                    for row in selected:
                                        selected_by_month[row["revenue_month"]] = selected_by_month.get(row["revenue_month"], 0) + 1
                                    for trade in trades:
                                        trades_by_month[trade.revenue_month] = trades_by_month.get(trade.revenue_month, 0) + 1
                                    full_selected_months = len(
                                        [count for count in selected_by_month.values() if count >= TARGET_MONTHLY_POSITIONS]
                                    )
                                    full_trade_months = len(
                                        [count for count in trades_by_month.values() if count >= TARGET_MONTHLY_POSITIONS]
                                    )
                                    trades_by_param[pid] = trades
                                    results.append(
                                        {
                                            "parameter_id": pid,
                                            "mom_min": mom_min,
                                            "yoy_min": yoy_min,
                                            "foreign_min": foreign_min,
                                            "trust_min": trust_min,
                                            "breakout_days": breakout_days,
                                            "volume_ratio_min": volume_min,
                                            "top_n": top_n,
                                            "exit_rule": exit_rule,
                                            "revenue_filtered": len(base),
                                            "price_filtered": len(filtered),
                                            "selected": len(selected),
                                            "trades": len(trades),
                                            "covered_selected_months": len(selected_by_month),
                                            "full_selected_months": full_selected_months,
                                            "covered_trade_months": len(trades_by_month),
                                            "full_trade_months": full_trade_months,
                                            "min_selected_per_month": min(selected_by_month.values()) if selected_by_month else 0,
                                            "min_trades_per_month": min(trades_by_month.values()) if trades_by_month else 0,
                                            "finalized_trades": len([trade for trade in trades if trade.exit_status == "final"]),
                                            "as_of_latest_trades": len([trade for trade in trades if trade.exit_status != "final"]),
                                            "win_rate": round(len([value for value in returns if value > 0]) / len(returns), 6) if returns else None,
                                            "avg_return_pct": round(sum(returns) / len(returns), 6) if returns else None,
                                            "total_pnl_amount": round(pnl, 2),
                                            "invested_amount": round(invested, 2),
                                            "portfolio_return_pct": round(pnl / invested, 6) if invested else None,
                                        }
                                    )
    return results, trades_by_param


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    revenue_rows = build_revenue_database(refresh=False)
    chip_map = build_chip_database(revenue_rows, refresh=False)
    candidates = enriched_candidates(revenue_rows, chip_map)
    results, trades_by_param = run_backtest(candidates)
    results.sort(
        key=lambda row: (
            -row["full_trade_months"],
            -row["covered_trade_months"],
            -row["min_trades_per_month"],
            -(row["portfolio_return_pct"] if row["portfolio_return_pct"] is not None else -999),
            -row["trades"],
        )
    )
    coverage_first_best = results[0] if results else {}
    high_return_best = sorted(
        results,
        key=lambda row: (
            -(row["portfolio_return_pct"] if row["portfolio_return_pct"] is not None else -999),
            -row["trades"],
        ),
    )[0] if results else {}
    best = coverage_first_best
    best_trades = trades_by_param.get(str(best.get("parameter_id")), [])

    write_csv(RESULT_CSV, results, list(results[0].keys()) if results else ["parameter_id"])
    write_csv(TRADE_CSV, [asdict(trade) for trade in best_trades], list(Trade.__dataclass_fields__.keys()))
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "revenue_months": REVENUE_MONTHS,
        "revenue_rows": len(revenue_rows),
        "chip_rows": len(chip_map),
        "parameter_sets": len(results),
        "best": best,
        "high_return_best_without_monthly_coverage_constraint": high_return_best,
        "target_monthly_positions": TARGET_MONTHLY_POSITIONS,
        "outputs": {
            "revenue_csv": str(REVENUE_CSV),
            "chip_csv": str(CHIP_CSV),
            "result_csv": str(RESULT_CSV),
            "best_trades_csv": str(TRADE_CSV),
        },
        "assumption": "Monthly revenue is treated as available after market close on the 10th of the following month; entry is the next trading day.",
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
