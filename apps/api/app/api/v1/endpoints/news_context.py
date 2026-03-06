from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.news_context.exceptions import NewsContextError
from app.news_context.service import NewsContextService, get_news_context_service
from app.schemas.news_context import (
    NewsFeedItemOut,
    NewsFeedResponse,
    NewsIngestionRequest,
    NewsIngestionResponse,
)

router = APIRouter()


@router.get("/providers", response_model=list[str])
def list_news_providers(service: NewsContextService = Depends(get_news_context_service)) -> list[str]:
    return service.provider_codes()


@router.post("/ingest", response_model=NewsIngestionResponse)
def ingest_news(
    payload: NewsIngestionRequest,
    service: NewsContextService = Depends(get_news_context_service),
) -> NewsIngestionResponse:
    try:
        result = service.ingest_news(
            provider_code=payload.provider_code,
            limit=payload.limit,
            symbols=payload.symbols,
            asset_class=payload.asset_class,
        )
    except NewsContextError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "news_context_error", "message": str(exc)},
        ) from exc
    return NewsIngestionResponse.model_validate(result.__dict__)


@router.get("/feed", response_model=NewsFeedResponse)
def get_news_feed(
    limit: int = Query(default=40, ge=1, le=200),
    hours: int = Query(default=72, ge=1, le=720),
    symbol: str | None = Query(default=None, description="Optional asset symbol filter"),
    asset_class: str | None = Query(default=None, pattern="^(crypto|forex)$"),
    service: NewsContextService = Depends(get_news_context_service),
) -> NewsFeedResponse:
    try:
        rows = service.list_feed(
            limit=limit,
            hours=hours,
            symbol=symbol,
            asset_class=asset_class,
        )
    except NewsContextError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "news_context_error", "message": str(exc)},
        ) from exc

    items = [NewsFeedItemOut.model_validate(row.__dict__) for row in rows]
    return NewsFeedResponse(items=items)
