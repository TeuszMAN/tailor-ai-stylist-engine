"""Catalog repositories (Repository pattern).

The engine is white-label: the catalog can come from
* the bundled demo file (`mock_catalog.json`, default),
* any JSON file (`CATALOG_PATH`),
* a SQLite database (`CATALOG_DATABASE_URL=sqlite:///path/to/catalog.db`),
* or the request payload (`catalog: [...]`), which always wins for that request.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter

from app.schemas import CatalogSource, Product

DEMO_CATALOG_PATH = Path(__file__).with_name("mock_catalog.json")
_PRODUCTS = TypeAdapter(list[Product])


class CatalogRepository(Protocol):
    source: CatalogSource

    def list_products(self) -> list[Product]: ...


class JsonFileCatalogRepository:
    """Loads and validates a JSON array of products once (re-read when the file changes)."""

    def __init__(self, path: Path, source: CatalogSource = CatalogSource.FILE) -> None:
        self.path = path
        self.source = source
        self._cache: list[Product] | None = None
        self._mtime: float | None = None

    def list_products(self) -> list[Product]:
        mtime = self.path.stat().st_mtime
        if self._cache is None or mtime != self._mtime:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._cache = _PRODUCTS.validate_python(raw)
            self._mtime = mtime
        return list(self._cache)


class SqliteCatalogRepository:
    """Reads products from a `products(id TEXT PRIMARY KEY, payload TEXT)` table (JSON payloads)."""

    source = CatalogSource.SQLITE

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def list_products(self) -> list[Product]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            rows = connection.execute("SELECT payload FROM products ORDER BY position, id").fetchall()
        return [Product.model_validate_json(row[0]) for row in rows]

    @staticmethod
    def write_products(database_path: Path, products: Sequence[Product]) -> int:
        with closing(sqlite3.connect(database_path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, position INTEGER NOT NULL, payload TEXT NOT NULL)"
            )
            connection.execute("DELETE FROM products")
            connection.executemany(
                "INSERT INTO products (id, position, payload) VALUES (?, ?, ?)",
                [
                    (p.id, position, p.model_dump_json(exclude={"available_sizes", "in_stock"}))
                    for position, p in enumerate(products)
                ],
            )
        return len(products)


class InMemoryCatalogRepository:
    """Wraps a catalog received in the request payload."""

    source = CatalogSource.PAYLOAD

    def __init__(self, products: Sequence[Product]) -> None:
        self._products = list(products)

    def list_products(self) -> list[Product]:
        return list(self._products)


def sqlite_path_from_url(url: str) -> Path:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise ValueError("CATALOG_DATABASE_URL must look like sqlite:///path/to/catalog.db")
    return Path(url[len(prefix) :])


def build_repository(catalog_path: Path | None, database_url: str | None) -> CatalogRepository:
    if database_url:
        return SqliteCatalogRepository(sqlite_path_from_url(database_url))
    if catalog_path is not None:
        return JsonFileCatalogRepository(catalog_path, CatalogSource.FILE)
    return JsonFileCatalogRepository(DEMO_CATALOG_PATH, CatalogSource.DEMO)


def resolve_catalog(
    payload: Sequence[Product] | None, repository: CatalogRepository
) -> tuple[list[Product], CatalogSource]:
    """A catalog sent by the client always wins; otherwise use the configured repository."""
    if payload:
        return list(payload), CatalogSource.PAYLOAD
    return repository.list_products(), repository.source
