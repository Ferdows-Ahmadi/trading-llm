from app.repositories.news_context_repository import _sentiment_price_contradiction


def test_contradiction_rules() -> None:
    assert _sentiment_price_contradiction("positive", -1.2) is True
    assert _sentiment_price_contradiction("negative", 1.3) is True
    assert _sentiment_price_contradiction("positive", 2.1) is False
    assert _sentiment_price_contradiction("neutral", -5.0) is False
