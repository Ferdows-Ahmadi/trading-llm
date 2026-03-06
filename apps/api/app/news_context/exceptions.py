class NewsContextError(Exception):
    """Base exception for news/context engine."""


class NewsProviderError(NewsContextError):
    """Provider request/parse error."""


class NewsProviderNotFoundError(NewsContextError):
    """Unknown provider adapter code."""
