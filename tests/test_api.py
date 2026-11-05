from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.catalog import DEMO_CATALOG_PATH, SqliteCatalogRepository, build_repository
from app.schemas import CatalogSource, Product

MEASUREMENTS = {"height_cm": 180, "weight_kg": 85, "chest_type": "medio", "belly_type": "medio", "shoe_size": 41}


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["llm_mode"] == "rule_based"
    assert body["catalog_source"] == "demo"
    assert body["catalog_size"] == 21


def test_fit_finder(client: TestClient) -> None:
    body = client.post("/api/v1/fit-finder", json=MEASUREMENTS).json()
    assert (body["suit_size"], body["pants_size"], body["shirt_size"], body["fit"]) == (52, 46, 4, "regular")


def test_fit_finder_validation(client: TestClient) -> None:
    assert client.post("/api/v1/fit-finder", json={**MEASUREMENTS, "height_cm": 120}).status_code == 422
    assert client.post("/api/v1/fit-finder", json={**MEASUREMENTS, "chest_type": "gigante"}).status_code == 422


def test_recommend_with_demo_catalog(client: TestClient) -> None:
    response = client.post(
        "/api/v1/stylist/recommend",
        json={"message": "Sou padrinho de casamento à tarde", "measurements": MEASUREMENTS, "session_id": "abc"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "abc"
    assert len(body["recommended_looks"]) == 3
    assert body["engine"]["catalog_source"] == "demo"
    assert body["engine"]["latency_ms"] > 0
    assert body["recommended_looks"][0]["items"][0]["product"]["available_sizes"]


def test_recommend_with_payload_catalog(client: TestClient) -> None:
    catalog = json.loads(DEMO_CATALOG_PATH.read_text(encoding="utf-8"))
    for product in catalog:  # white-label clients may echo computed/extra fields
        product["in_stock"] = True
        product["brand"] = "Any Store"
    body = client.post(
        "/api/v1/stylist/recommend", json={"message": "Entrevista de emprego", "catalog": catalog, "max_looks": 2}
    ).json()
    assert body["engine"]["catalog_source"] == "payload"
    assert len(body["recommended_looks"]) == 2


def test_recommend_rejects_duplicate_ids(client: TestClient) -> None:
    catalog = json.loads(DEMO_CATALOG_PATH.read_text(encoding="utf-8"))
    response = client.post("/api/v1/stylist/recommend", json={"message": "oi", "catalog": [catalog[0], catalog[0]]})
    assert response.status_code == 422


def test_catalog_listing_and_filters(client: TestClient) -> None:
    assert client.get("/api/v1/catalog").json()["total"] == 21
    ties = client.get("/api/v1/catalog", params={"category": "tie"}).json()
    assert ties["total"] == 5
    sized = client.get("/api/v1/catalog", params={"category": "suit", "size": "52", "in_stock_only": True}).json()
    assert "terno-cinza-chumbo" not in {p["id"] for p in sized["items"]}


def test_inventory_search(client: TestClient) -> None:
    body = client.post("/api/v1/inventory/search", json={"query": "gravata vinho"}).json()
    assert body["inferred_category"] == "tie"
    assert [p["id"] for p in body["items"]] == ["gravata-seda-bordo"]


def test_compose_look(client: TestClient) -> None:
    combo = {
        "suit_id": "terno-cinza-chumbo",
        "shirt_id": "camisa-branca-algodao-egipcio",
        "tie_id": "gravata-seda-prata",
        "shoe_id": "sapato-oxford-preto",
        "target_formality": "formal",
        "time_of_day": "noite",
        "measurements": MEASUREMENTS,
    }
    body = client.post("/api/v1/looks/compose", json=combo).json()
    assert body["is_valid"] is True
    assert body["items"][0]["selected_size"] == "52"
    assert any("sem estoque no tamanho 52" in w for w in body["warnings"])
    bad = client.post("/api/v1/looks/compose", json={**combo, "suit_id": "camisa-branca-algodao-egipcio"})
    assert bad.status_code == 422
    assert "não é um terno" in bad.json()["detail"]


def test_openapi_exposes_required_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", "/api/v1/fit-finder", "/api/v1/stylist/recommend"} <= set(paths)


def test_sqlite_repository_roundtrip(tmp_path: Path, catalog: list[Product]) -> None:
    db = tmp_path / "catalog.db"
    assert SqliteCatalogRepository.write_products(db, catalog) == len(catalog)
    repository = build_repository(None, f"sqlite:///{db}")
    assert repository.source is CatalogSource.SQLITE
    assert [p.id for p in repository.list_products()] == [p.id for p in catalog]
