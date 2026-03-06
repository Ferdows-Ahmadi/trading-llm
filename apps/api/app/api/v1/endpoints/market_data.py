from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.market_data.exceptions import MarketDataError
from app.market_data.service import MarketDataService, get_market_data_service
from app.schemas.market_data import (
    OhlcvIngestionRequest,
    OhlcvIngestionResponse,
    OhlcvQueryResponse,
    StoredCandleResponse,
)

router = APIRouter()


@router.get("/providers", response_model=list[str])
def list_providers(service: MarketDataService = Depends(get_market_data_service)) -> list[str]:
    return service.available_providers()


@router.post("/ingest/ohlcv", response_model=OhlcvIngestionResponse)
def ingest_ohlcv(
    payload: OhlcvIngestionRequest,
    service: MarketDataService = Depends(get_market_data_service),
) -> OhlcvIngestionResponse:
    try:
        result = service.ingest_ohlcv(
            provider_code=payload.provider_code,
            raw_symbol=payload.symbol,
            timeframe=payload.timeframe,
            limit=payload.limit,
            asset_class=payload.asset_class,
            since=payload.since,
        )
    except MarketDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "market_data_error", "message": str(exc)},
        ) from exc
    return OhlcvIngestionResponse.model_validate(result.__dict__)


@router.get("/candles", response_model=OhlcvQueryResponse)
def get_candles(
    symbol: str = Query(..., description="e.g. BTC/USDT or EURUSD"),
    timeframe: str = Query(default="1h"),
    limit: int = Query(default=200, ge=1, le=1000),
    asset_class: str | None = Query(default=None, pattern="^(crypto|forex)$"),
    service: MarketDataService = Depends(get_market_data_service),
) -> OhlcvQueryResponse:
    try:
        candles = service.list_candles(
            raw_symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            asset_class=asset_class,
        )
    except MarketDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "market_data_error", "message": str(exc)},
        ) from exc

    response_candles = [StoredCandleResponse.model_validate(item.__dict__) for item in candles]
    normalized_symbol = response_candles[0].symbol if response_candles else symbol
    return OhlcvQueryResponse(symbol=normalized_symbol, timeframe=timeframe, candles=response_candles)
