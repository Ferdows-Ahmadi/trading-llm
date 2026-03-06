from __future__ import annotations

from abc import ABC, abstractmethod

from app.market_data.domain import OHLCVCandle, OHLCVFetchRequest


class MarketDataAdapter(ABC):
    provider_code: str

    @abstractmethod
    def fetch_ohlcv(self, request: OHLCVFetchRequest) -> list[OHLCVCandle]:
        raise NotImplementedError
