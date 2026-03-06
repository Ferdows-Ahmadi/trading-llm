from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None


class MarketDataAdapter(ABC):
    provider_code: str

    @abstractmethod
    async def fetch_candles(self, symbol: str, timeframe: str, limit: int = 500) -> list[Candle]:
        raise NotImplementedError
