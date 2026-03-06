from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

AssetClass = Literal["crypto", "forex"]


@dataclass(frozen=True)
class NormalizedSymbol:
    raw_symbol: str
    normalized_symbol: str
    base_currency: str
    quote_currency: str
    asset_class: AssetClass

    @property
    def display_symbol(self) -> str:
        return f"{self.base_currency}/{self.quote_currency}"


@dataclass(frozen=True)
class OHLCVFetchRequest:
    symbol: NormalizedSymbol
    timeframe: str
    limit: int
    since: datetime | None = None


@dataclass(frozen=True)
class OHLCVCandle:
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    quote_volume: Decimal | None = None
    trade_count: int | None = None
