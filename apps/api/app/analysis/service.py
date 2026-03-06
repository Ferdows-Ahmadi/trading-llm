from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import cast

import pandas as pd

from app.analysis.domain import AnalysisResult
from app.analysis.exceptions import AnalysisError, InsufficientCandleDataError
from app.analysis.indicators import candles_to_frame, compute_indicators
from app.analysis.levels import detect_support_resistance
from app.analysis.regime import classify_trend_regime
from app.analysis.scoring import score_asset
from app.analysis.setups import detect_setups
from app.market_data.domain import AssetClass
from app.market_data.exceptions import SymbolNormalizationError
from app.market_data.normalization import normalize_symbol
from app.repositories.base import SessionLocal
from app.repositories.market_data_repository import MarketDataRepository


class AnalysisService:
    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def analyze_asset(
        self,
        *,
        raw_symbol: str,
        timeframe: str,
        limit: int,
        asset_class: str | None,
    ) -> AnalysisResult:
        typed_asset_class = cast(AssetClass | None, asset_class)
        try:
            normalized = normalize_symbol(raw_symbol, asset_class=typed_asset_class)
        except SymbolNormalizationError as exc:
            raise AnalysisError(str(exc)) from exc
        candles = self._repository.list_candles(
            normalized_symbol=normalized.normalized_symbol,
            timeframe=timeframe,
            limit=limit,
        )
        if len(candles) < 60:
            raise InsufficientCandleDataError(
                f"Need at least 60 candles for analysis; received {len(candles)} for {normalized.normalized_symbol}"
            )

        frame = candles_to_frame(candles)
        indicators = compute_indicators(frame)
        regime = classify_trend_regime(indicators)
        supports, resistances = detect_support_resistance(indicators)
        setups = detect_setups(indicators, regime=regime, supports=supports, resistances=resistances)
        score = score_asset(indicators, regime=regime, setups=setups)

        latest_row = indicators.iloc[-1]
        latest_indicators = _latest_indicator_snapshot(latest_row)

        return AnalysisResult(
            symbol=normalized.normalized_symbol,
            timeframe=timeframe,
            analyzed_at=datetime.now(tz=UTC),
            candle_count=len(candles),
            latest_close=float(latest_row["close"]),
            latest_indicators=latest_indicators,
            trend_regime=regime,
            supports=supports,
            resistances=resistances,
            setups=setups,
            score=score,
        )


def _latest_indicator_snapshot(row: pd.Series) -> dict[str, float | None]:
    keys = [
        "sma_20",
        "ema_20",
        "ema_50",
        "ema_200",
        "rsi_14",
        "macd_line",
        "macd_signal",
        "macd_hist",
        "atr_14",
        "bb_upper",
        "bb_middle",
        "bb_lower",
        "adx_14",
    ]
    snapshot: dict[str, float | None] = {}
    for key in keys:
        value = row.get(key)
        if value is None or pd.isna(value):
            snapshot[key] = None
        else:
            snapshot[key] = round(float(value), 8)
    return snapshot


_analysis_service_instance: AnalysisService | None = None


def get_analysis_service() -> AnalysisService:
    global _analysis_service_instance
    if _analysis_service_instance is None:
        _analysis_service_instance = AnalysisService(MarketDataRepository(session_factory=SessionLocal))
    return _analysis_service_instance


def serialize_analysis_result(result: AnalysisResult) -> dict[str, object]:
    payload = asdict(result)
    payload["analyzed_at"] = result.analyzed_at.isoformat()
    return payload
