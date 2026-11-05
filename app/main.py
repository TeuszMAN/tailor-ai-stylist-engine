"""FastAPI entrypoint of the Tailor AI Engine.

Run locally:  uvicorn app.main:app --reload --port 8000
Docs:         http://localhost:8000/docs  (OpenAPI: /openapi.json)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import StylistEngine
from app.agent.llm import build_llm
from app.catalog import CatalogRepository, build_repository, resolve_catalog
from app.config import Settings, get_settings
from app.schemas import (
    API_VERSION,
    CatalogResponse,
    Category,
    ComposeLookRequest,
    ErrorResponse,
    Formality,
    HealthResponse,
    InventorySearchRequest,
    InventorySearchResult,
    OutfitRecommendation,
    SizeRecommendation,
    StylistRecommendRequest,
    StylistRecommendResponse,
    UserMeasurements,
)
from app.tools import (
    LookCompositionError,
    ToolInputError,
    attach_sizes,
    compose_complete_look,
    search_inventory,
    size_from_measurements,
)

logger = logging.getLogger("tailor_ai_engine")

DESCRIPTION = """
White-label **agentic menswear stylist** for classic tailoring.

* `POST /api/v1/fit-finder` — deterministic anthropometric sizing (Drop 6 algorithm).
* `POST /api/v1/stylist/recommend` — LangGraph agent (LLM tool calling **or** deterministic
  rule-based fallback when no API key is configured) that returns complete, validated looks.
* Catalog can be the bundled demo, a JSON file, SQLite, or sent in the request payload.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    repository = build_repository(settings.catalog_path, settings.catalog_database_url)
    llm = build_llm(settings)
    app.state.repository = repository
    app.state.engine = StylistEngine(repository, llm, settings.llm_max_tool_rounds)
    logger.info(
        "engine ready mode=%s provider=%s catalog=%s",
        app.state.engine.mode,
        llm.provider if llm else None,
        repository.source.value,
    )
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(
        title="Tailor AI Engine",
        version=API_VERSION,
        description=DESCRIPTION,
        lifespan=lifespan,
        responses={422: {"description": "Invalid payload"}},
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    _register_routes(app)
    return app


def get_engine(request: Request) -> StylistEngine:
    engine: StylistEngine = request.app.state.engine
    return engine


def get_repository(request: Request) -> CatalogRepository:
    repository: CatalogRepository = request.app.state.repository
    return repository


EngineDep = Annotated[StylistEngine, Depends(get_engine)]
RepositoryDep = Annotated[CatalogRepository, Depends(get_repository)]


def _register_routes(app: FastAPI) -> None:
    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    def health(engine: EngineDep, repository: RepositoryDep) -> HealthResponse:
        llm = engine.llm
        return HealthResponse(
            status="ok",
            service="tailor-ai-engine",
            version=API_VERSION,
            llm_mode="llm" if llm else "rule_based",
            llm_provider=llm.provider if llm else None,
            llm_model=llm.model_name if llm else None,
            catalog_source=repository.source,
            catalog_size=len(repository.list_products()),
        )

    @app.post("/api/v1/fit-finder", response_model=SizeRecommendation, tags=["sizing"])
    def fit_finder(measurements: UserMeasurements) -> SizeRecommendation:
        """Anthropometric sizing: height x weight x biotype -> suit 46-60, pants 38-54, shirt 1-6, cut."""
        return size_from_measurements(measurements)

    @app.post(
        "/api/v1/stylist/recommend",
        response_model=StylistRecommendResponse,
        tags=["stylist"],
    )
    def stylist_recommend(payload: StylistRecommendRequest, engine: EngineDep) -> StylistRecommendResponse:
        """Run the LangGraph stylist and return consultative text + validated complete looks."""
        return engine.recommend(payload)

    @app.get("/api/v1/catalog", response_model=CatalogResponse, tags=["catalog"])
    def list_catalog(
        repository: RepositoryDep,
        category: Category | None = None,
        size: Annotated[str | None, Query(max_length=8)] = None,
        formality: Formality | None = None,
        color: Annotated[str | None, Query(max_length=80)] = None,
        q: Annotated[str | None, Query(max_length=200)] = None,
        in_stock_only: bool = False,
    ) -> CatalogResponse:
        """List the configured catalog (demo by default) with optional filters."""
        products = repository.list_products()
        if any(v is not None for v in (category, size, formality, color, q)) or in_stock_only:
            result = search_inventory(
                category, size, formality, color, q, catalog=products, in_stock_only=in_stock_only, limit=500
            )
            products = result.items
        return CatalogResponse(source=repository.source, total=len(products), items=products)

    @app.post("/api/v1/inventory/search", response_model=InventorySearchResult, tags=["catalog"])
    def inventory_search(payload: InventorySearchRequest, repository: RepositoryDep) -> InventorySearchResult:
        """Semantic search over the configured catalog or over the catalog sent in the payload."""
        catalog, source = resolve_catalog(payload.catalog, repository)
        try:
            return search_inventory(
                payload.category,
                payload.size,
                payload.formality,
                payload.color_query,
                payload.query,
                catalog=catalog,
                in_stock_only=payload.in_stock_only,
                limit=payload.limit,
                source=source,
            )
        except ToolInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/api/v1/looks/compose",
        response_model=OutfitRecommendation,
        responses={422: {"model": ErrorResponse, "description": "Invalid look combination"}},
        tags=["stylist"],
    )
    def compose_look(payload: ComposeLookRequest, repository: RepositoryDep) -> OutfitRecommendation:
        """Mix & Match: validate any suit + shirt + tie + shoes combination against classic etiquette."""
        catalog, _ = resolve_catalog(payload.catalog, repository)
        try:
            look = compose_complete_look(
                payload.suit_id,
                payload.shirt_id,
                payload.tie_id,
                payload.shoe_id,
                payload.target_formality,
                payload.time_of_day,
                catalog=catalog,
            )
        except LookCompositionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if payload.measurements is None:
            return look
        sized, unavailable = attach_sizes(look, size_from_measurements(payload.measurements))
        return sized.model_copy(update={"warnings": [*sized.warnings, *unavailable]})


app = create_app()
