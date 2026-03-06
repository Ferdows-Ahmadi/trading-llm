from app.schemas.asset import AssetOut


def list_assets() -> list[AssetOut]:
    # Phase 1 scaffold: deterministic placeholder response until repository wiring lands.
    return [
        AssetOut(
            id="seed-btcusdt",
            symbol="BTC/USDT",
            display_name="Bitcoin / Tether",
            asset_class="crypto",
        ),
        AssetOut(
            id="seed-eurusd",
            symbol="EUR/USD",
            display_name="Euro / US Dollar",
            asset_class="forex",
        ),
    ]
