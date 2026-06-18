from __future__ import annotations

import csv
import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_DIR = PROJECT_DIR / "project_data" / "2026_h1"
LOCAL_PRICES_DIR = LOCAL_DIR / "prices"


REQUIRED_COLUMNS = [
    "trade_date",
    "stock_id",
    "open",
    "high",
    "low",
    "close",
    "volume",
]


def load_needed_stock_ids() -> list[str]:
    path = LOCAL_DIR / "prices_needed.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_template() -> None:
    template_path = LOCAL_PRICES_DIR / "_template_price.csv"
    with template_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(REQUIRED_COLUMNS)
        writer.writerow(["2026-01-02", "1234", "10.0", "10.5", "9.8", "10.2", "100000"])


def main() -> int:
    LOCAL_PRICES_DIR.mkdir(parents=True, exist_ok=True)
    write_template()

    summary = {
        "local_prices_dir": str(LOCAL_PRICES_DIR),
        "required_columns": REQUIRED_COLUMNS,
        "needed_stock_ids": load_needed_stock_ids(),
        "template_file": str(LOCAL_PRICES_DIR / "_template_price.csv"),
    }
    with (LOCAL_DIR / "price_specs.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
