import pytest

from app.market_data.exceptions import SymbolNormalizationError
from app.market_data.normalization import normalize_symbol, provider_symbol_for


def test_normalize_crypto_delimited() -> None:
    symbol = normalize_symbol("btc/usdt", asset_class="crypto")
    assert symbol.normalized_symbol == "BTCUSDT"
    assert symbol.base_currency == "BTC"
    assert symbol.quote_currency == "USDT"
    assert symbol.asset_class == "crypto"


def test_normalize_forex_compact() -> None:
    symbol = normalize_symbol("eurusd")
    assert symbol.normalized_symbol == "EURUSD"
    assert symbol.asset_class == "forex"


def test_provider_symbol_formatting() -> None:
    symbol = normalize_symbol("ETHUSDT", asset_class="crypto")
    assert provider_symbol_for("ccxt", symbol) == "ETH/USDT"
    assert provider_symbol_for("alpha_vantage", symbol) == "ETHUSDT"


def test_invalid_symbol_raises() -> None:
    with pytest.raises(SymbolNormalizationError):
        normalize_symbol("x")
