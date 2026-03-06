from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.analysis.domain import PriceLevel


@dataclass(frozen=True)
class _RawLevel:
    price: float
    touches: int


def detect_support_resistance(
    indicator_frame: pd.DataFrame,
    *,
    swing_window: int = 3,
    merge_tolerance_pct: float = 0.003,
    max_levels: int = 5,
) -> tuple[list[PriceLevel], list[PriceLevel]]:
    if indicator_frame.empty or len(indicator_frame) < (swing_window * 2 + 1):
        return ([], [])

    highs = indicator_frame["high"].to_numpy()
    lows = indicator_frame["low"].to_numpy()
    close_price = float(indicator_frame.iloc[-1]["close"])

    resistance_candidates: list[float] = []
    support_candidates: list[float] = []
    for idx in range(swing_window, len(indicator_frame) - swing_window):
        high_window = highs[idx - swing_window : idx + swing_window + 1]
        low_window = lows[idx - swing_window : idx + swing_window + 1]

        current_high = highs[idx]
        current_low = lows[idx]
        if current_high == max(high_window):
            resistance_candidates.append(float(current_high))
        if current_low == min(low_window):
            support_candidates.append(float(current_low))

    support_clusters = _cluster_levels(support_candidates, merge_tolerance_pct)
    resistance_clusters = _cluster_levels(resistance_candidates, merge_tolerance_pct)

    supports = _to_price_levels(
        clusters=[cluster for cluster in support_clusters if cluster.price < close_price],
        close_price=close_price,
        reverse=True,
        max_levels=max_levels,
    )
    resistances = _to_price_levels(
        clusters=[cluster for cluster in resistance_clusters if cluster.price > close_price],
        close_price=close_price,
        reverse=False,
        max_levels=max_levels,
    )
    return supports, resistances


def _cluster_levels(candidates: list[float], tolerance_pct: float) -> list[_RawLevel]:
    if not candidates:
        return []

    sorted_candidates = sorted(candidates)
    clusters: list[list[float]] = [[sorted_candidates[0]]]

    for level in sorted_candidates[1:]:
        cluster = clusters[-1]
        cluster_mid = sum(cluster) / len(cluster)
        distance = abs(level - cluster_mid) / cluster_mid if cluster_mid else 0.0
        if distance <= tolerance_pct:
            cluster.append(level)
        else:
            clusters.append([level])

    return [_RawLevel(price=sum(cluster) / len(cluster), touches=len(cluster)) for cluster in clusters]


def _to_price_levels(
    *,
    clusters: list[_RawLevel],
    close_price: float,
    reverse: bool,
    max_levels: int,
) -> list[PriceLevel]:
    ordered = sorted(clusters, key=lambda item: item.price, reverse=reverse)
    selected = ordered[:max_levels]
    return [
        PriceLevel(
            level=round(item.price, 8),
            touches=item.touches,
            distance_pct=round(((item.price - close_price) / close_price) * 100, 4),
        )
        for item in selected
    ]
