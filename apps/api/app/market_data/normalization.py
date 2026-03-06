from __future__ import annotations

import re

from app.market_data.domain import AssetClass, NormalizedSymbol
from app.market_data.exceptions import SymbolNormalizationError

_FOREX_QUOTES = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CHF", "CAD"}
_CRYPTO_QUOTES = ("USDT", "USDC", "USD", "BTC", "ETH", "EUR", "GBP", "JPY")


def normalize_symbol(raw_symbol: str, asset_class: AssetClass | None = None) -> NormalizedSymbol:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw_symbol).upper()
    if len(cleaned) < 6:
        raise SymbolNormalizationError(f"Symbol is too short to normalize: {raw_symbol}")

    if "/" in raw_symbol or "-" in raw_symbol or "_" in raw_symbol:
        base, quote = _split_delimited_symbol(raw_symbol)
    elif asset_class == "forex" or _looks_like_forex_pair(cleaned):
        base, quote = _split_forex_compact(cleaned)
    else:
        base, quote = _split_crypto_compact(cleaned)

    resolved_asset_class: AssetClass = asset_class or ("forex" if quote in _FOREX_QUOTES else "crypto")
    return NormalizedSymbol(
        raw_symbol=raw_symbol,
        normalized_symbol=f"{base}{quote}",
        base_currency=base,
        quote_currency=quote,
        asset_class=resolved_asset_class,
    )


def provider_symbol_for(provider_code: str, symbol: NormalizedSymbol) -> str:
    if provider_code == "ccxt":
        return symbol.display_symbol
    if provider_code == "alpha_vantage":
        return symbol.normalized_symbol
    raise SymbolNormalizationError(f"Unsupported provider for symbol formatting: {provider_code}")


def _split_delimited_symbol(raw_symbol: str) -> tuple[str, str]:
    parts = re.split(r"[/\-_]", raw_symbol.upper())
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise SymbolNormalizationError(f"Invalid delimited symbol: {raw_symbol}")
    return parts[0], parts[1]


def _looks_like_forex_pair(symbol: str) -> bool:
    return len(symbol) == 6 and symbol[0:3] in _FOREX_QUOTES and symbol[3:6] in _FOREX_QUOTES


def _split_forex_compact(symbol: str) -> tuple[str, str]:
    if len(symbol) != 6:
        raise SymbolNormalizationError(f"Forex symbol must be 6 chars: {symbol}")
    return symbol[0:3], symbol[3:6]


def _split_crypto_compact(symbol: str) -> tuple[str, str]:
    for quote in _CRYPTO_QUOTES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    raise SymbolNormalizationError(f"Unable to infer crypto quote currency: {symbol}")
