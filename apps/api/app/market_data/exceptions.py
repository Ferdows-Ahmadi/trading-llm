class MarketDataError(Exception):
    """Base market data exception."""


class SymbolNormalizationError(MarketDataError):
    """Raised when a symbol cannot be normalized."""


class UnsupportedTimeframeError(MarketDataError):
    """Raised when provider does not support requested timeframe."""


class ProviderRequestError(MarketDataError):
    """Raised when external provider request fails."""


class ProviderNotFoundError(MarketDataError):
    """Raised when an adapter cannot be resolved by provider code."""
