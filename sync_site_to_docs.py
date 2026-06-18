from __future__ import annotations

import shutil
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
SITE_DIR = PROJECT_DIR / "site"
DOCS_DIR = PROJECT_DIR / "docs"


def main() -> int:
    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    shutil.copytree(SITE_DIR, DOCS_DIR)
    print(str(DOCS_DIR))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
