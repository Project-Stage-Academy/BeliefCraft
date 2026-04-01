from __future__ import annotations

from typing import Protocol, cast

import redis
from common.logging import get_logger
from database.inventory import Product
from database.logistics import Route, Supplier, Warehouse
from environment_api.config_load import settings
from environment_api.smart_query_builder.db.session import get_session
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

router = APIRouter(tags=["form-options"])
logger = get_logger(__name__)
CACHE_KEY = "form-options"


class ProductOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)


class FormOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origins: list[str]
    destinations: list[str]
    products: list[ProductOption]
    transport_modes: list[str]


class CacheClient(Protocol):
    def get(self, key: str) -> str | None: ...

    def setex(self, key: str, ttl_seconds: int, value: str) -> bool: ...


def get_cache_client() -> CacheClient | None:
    """Return a cache client instance if available."""
    client = redis.Redis.from_url(settings.cache.redis_url, decode_responses=True)
    return cast(CacheClient, client)


def fetch_form_options(
    session: Session,
    cache_client: CacheClient | None,
    ttl_seconds: int,
) -> FormOptionsResponse:
    """Fetch and cache form options for dropdown fields."""
    if cache_client is not None:
        try:
            cached_payload = cache_client.get(CACHE_KEY)
        except redis.RedisError as exc:
            logger.warning("form_options_cache_read_failed", error=str(exc))
            cached_payload = None

        if cached_payload:
            try:
                return FormOptionsResponse.model_validate_json(cached_payload)
            except ValueError as exc:
                logger.warning("form_options_cache_invalid", error=str(exc))

    result = load_form_options_from_db(session)

    if cache_client is not None and ttl_seconds > 0:
        try:
            cache_client.setex(CACHE_KEY, ttl_seconds, result.model_dump_json())
        except redis.RedisError as exc:
            logger.warning("form_options_cache_write_failed", error=str(exc))

    return result


def load_form_options_from_db(session: Session) -> FormOptionsResponse:
    """Load form options directly from the database."""
    warehouse_names = session.scalars(select(distinct(Warehouse.name))).all()
    supplier_names = session.scalars(select(distinct(Supplier.name))).all()

    origins = sorted({*warehouse_names, *supplier_names})
    destinations = sorted(warehouse_names)

    product_rows = session.execute(select(Product.name, Product.category).distinct()).all()
    products = [ProductOption(name=row.name, category=row.category) for row in product_rows]
    products.sort(key=lambda product: (product.category, product.name))

    transport_modes_raw = session.scalars(select(distinct(Route.mode))).all()
    transport_modes = sorted({str(getattr(mode, "value", mode)) for mode in transport_modes_raw})

    return FormOptionsResponse(
        origins=origins,
        destinations=destinations,
        products=products,
        transport_modes=transport_modes,
    )


@router.get("/form-options", response_model=FormOptionsResponse)
def get_form_options() -> FormOptionsResponse:
    """Return cached form options for dropdown fields."""
    cache_client = get_cache_client()

    try:
        with get_session() as session:
            return fetch_form_options(session, cache_client, settings.cache.ttl_seconds)
    except Exception as exc:
        logger.exception("form_options_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch form options.",
        ) from exc
