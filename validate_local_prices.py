from __future__ import annotations

import csv
import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_DIR = PROJECT_DIR / "project_data" / "2026_h1"
LOCAL_PRICES_DIR = LOCAL_DIR / "prices"

REQUIRED_COLUMNS = {
    "trade_date",
    "stock_id",
    "open",
    "high",
    "low",
    "close",
    "volume",
}


def load_needed_stock_ids() -> list[str]:
    path = LOCAL_DIR / "prices_needed.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_one(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = set(reader.fieldnames or [])
        rows = list(reader)

    missing_columns = sorted(REQUIRED_COLUMNS - columns)
    stock_ids = sorted({row.get("stock_id", "").strip() for row in rows if row.get("stock_id", "").strip()})
    return {
        "file": path.name,
        "rows": len(rows),
        "missing_columns": missing_columns,
        "stock_ids": stock_ids,
        "valid": not missing_columns and len(rows) > 0,
    }


def main() -> int:
    needed = load_needed_stock_ids()
    reports = []
    present = []
    for stock_id in needed:
        file_path = LOCAL_PRICES_DIR / f"{stock_id}.csv"
        if file_path.exists():
            reports.append(validate_one(file_path))
            present.append(stock_id)
        else:
            reports.append(
                {
                    "file": f"{stock_id}.csv",
                    "rows": 0,
                    "missing_columns": list(REQUIRED_COLUMNS),
                    "stock_ids": [],
                    "valid": False,
                }
            )

    missing_files = [stock_id for stock_id in needed if stock_id not in present]
    summary = {
        "needed_files": len(needed),
        "present_files": len(present),
        "missing_files": missing_files,
        "valid_files": sum(1 for report in reports if report["valid"]),
        "reports": reports,
    }
    with (LOCAL_DIR / "price_validation_report.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
