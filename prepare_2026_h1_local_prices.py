from __future__ import annotations

import csv
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
LOCAL_DIR = PROJECT_DIR / "project_data" / "2026_h1"
LOCAL_PRICES_DIR = LOCAL_DIR / "prices"


def load_main_events() -> list[dict[str, str]]:
    path = LOCAL_DIR / "main_strategy_events.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    LOCAL_PRICES_DIR.mkdir(parents=True, exist_ok=True)
    stock_ids = sorted({row["stock_id"] for row in load_main_events()})
    todo_path = LOCAL_DIR / "prices_needed.txt"
    with todo_path.open("w", encoding="utf-8") as fh:
        for stock_id in stock_ids:
            fh.write(f"{stock_id}\n")
    print(str(todo_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
