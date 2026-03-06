from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AssetClass = Literal["crypto", "forex"]


class OhlcvIngestionRequest(BaseModel):
    provider_code: str = Field(description="Provider adapter code, e.g. ccxt or alpha_vantage")
    symbol: str = Field(description="Symbol in normalized or provider form, e.g. BTC/USDT or EURUSD")
    timeframe: str = Field(default="1h")
    limit: int = Field(default=200, ge=1, le=1000)
    asset_class: AssetClass | None = None
    since: datetime | None = None


class OhlcvIngestionResponse(BaseModel):
    provider_code: str
    normalized_symbol: str
    timeframe: str
    fetched_count: int
    inserted_count: int
    updated_count: int
    duration_ms: int


class StoredCandleResponse(BaseModel):
    symbol: str
    timeframe: str
    provider_code: str
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class OhlcvQueryResponse(BaseModel):
    symbol: str
    timeframe: str
    candles: list[StoredCandleResponse]
