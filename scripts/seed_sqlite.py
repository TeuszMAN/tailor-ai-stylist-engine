"""Load a JSON catalog into SQLite (run: `python -m scripts.seed_sqlite [catalog.json] [catalog.db]`).

Then start the engine with `CATALOG_DATABASE_URL=sqlite:///catalog.db`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.catalog import DEMO_CATALOG_PATH, JsonFileCatalogRepository, SqliteCatalogRepository


def main(argv: list[str]) -> None:
    source = Path(argv[1]) if len(argv) > 1 else DEMO_CATALOG_PATH
    target = Path(argv[2]) if len(argv) > 2 else Path("catalog.db")
    products = JsonFileCatalogRepository(source).list_products()
    count = SqliteCatalogRepository.write_products(target, products)
    print(f"seeded {count} products into {target}")


if __name__ == "__main__":
    main(sys.argv)
