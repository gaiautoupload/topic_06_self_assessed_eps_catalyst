from __future__ import annotations

import csv
import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DATASET_DIR = Path(r"D:\dataset")
LOCAL_DIR = PROJECT_DIR / "project_data" / "fundamental_event_lab"
PRICE_DIR = DATASET_DIR / "processed" / "prices"

INSTITUTION_KEYWORDS = [
    "foreign",
    "investment_trust",
    "dealer",
    "institution",
    "外資",
    "投信",
    "自營",
    "三大法人",
]


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def find_institution_files() -> list[str]:
    hits: list[str] = []
    for path in DATASET_DIR.rglob("*"):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if any(keyword.lower() in lowered for keyword in INSTITUTION_KEYWORDS):
            hits.append(str(path))
    return hits


def main() -> int:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    events = load_csv(LOCAL_DIR / "fundamental_events_2026_h1.csv")
    stock_ids = sorted({row["stock_id"] for row in events})
    price_files = sorted(path.stem for path in PRICE_DIR.glob("*.csv"))
    price_set = set(price_files)
    institution_files = find_institution_files()

    rows = []
    for stock_id in stock_ids:
        rows.append(
            {
                "stock_id": stock_id,
                "has_price_file": stock_id in price_set,
                "has_institution_file": False,
                "institution_note": "not_found_in_dataset",
            }
        )

    coverage_csv = LOCAL_DIR / "market_data_coverage.csv"
    with coverage_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["stock_id", "has_price_file", "has_institution_file", "institution_note"],
        )
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "stocks": len(stock_ids),
        "price_files_total": len(price_files),
        "stocks_with_price": sum(1 for row in rows if row["has_price_file"]),
        "institution_candidate_files": institution_files,
        "institution_status": "missing",
        "coverage_csv": str(coverage_csv),
    }
    with (LOCAL_DIR / "market_data_coverage_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
