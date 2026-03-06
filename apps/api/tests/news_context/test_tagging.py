import uuid
from datetime import UTC, datetime

from app.news_context.domain import NewsCandidate
from app.news_context.tagging import tag_assets
from app.repositories.news_context_repository import AssetRef


def test_asset_tagging_from_text_and_tickers() -> None:
    assets = [
        AssetRef(
            id=uuid.uuid4(),
            normalized_symbol="BTCUSDT",
            base_currency="BTC",
            quote_currency="USDT",
            display_symbol="BTC/USDT",
            asset_class="crypto",
        ),
        AssetRef(
            id=uuid.uuid4(),
            normalized_symbol="EURUSD",
            base_currency="EUR",
            quote_currency="USD",
            display_symbol="EUR/USD",
            asset_class="forex",
        ),
    ]
    candidate = NewsCandidate(
        external_id="abc",
        source_name="Wire",
        title="BTC spikes while EUR/USD stalls",
        summary="Traders watch BTC momentum after breakout.",
        url="https://example.com/news3",
        published_at=datetime(2026, 1, 2, tzinfo=UTC),
        provider_tickers=["BTC"],
    )

    tagged = tag_assets(candidate, assets)
    symbols = [item.normalized_symbol for item in tagged]
    assert "BTCUSDT" in symbols
