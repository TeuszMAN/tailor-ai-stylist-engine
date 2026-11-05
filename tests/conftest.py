from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.catalog import DEMO_CATALOG_PATH, JsonFileCatalogRepository
from app.config import Settings
from app.main import create_app
from app.schemas import CatalogSource, Product


@pytest.fixture(scope="session")
def catalog() -> list[Product]:
    return JsonFileCatalogRepository(DEMO_CATALOG_PATH, CatalogSource.DEMO).list_products()


@pytest.fixture(scope="session")
def by_id(catalog: list[Product]) -> dict[str, Product]:
    return {p.id: p for p in catalog}


@pytest.fixture()
def client() -> TestClient:
    settings = Settings(llm_provider="none", _env_file=None)
    with TestClient(create_app(settings)) as test_client:
        yield test_client
