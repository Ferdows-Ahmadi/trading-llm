class AnalysisError(Exception):
    """Base exception for deterministic analysis engine."""


class InsufficientCandleDataError(AnalysisError):
    """Raised when analysis cannot run due to low candle count."""
