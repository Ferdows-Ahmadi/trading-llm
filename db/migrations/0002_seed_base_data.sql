INSERT INTO providers (code, name, category, rate_limit_per_minute)
VALUES
  ('ccxt', 'CCXT Unified Exchange API', 'market_data', 60),
  ('alpha_vantage', 'Alpha Vantage', 'market_data_and_news', 5)
ON CONFLICT (code) DO NOTHING;

INSERT INTO assets (symbol, normalized_symbol, display_name, asset_class, base_currency, quote_currency)
VALUES
  ('BTC/USDT', 'BTCUSDT', 'Bitcoin / Tether', 'crypto', 'BTC', 'USDT'),
  ('ETH/USDT', 'ETHUSDT', 'Ethereum / Tether', 'crypto', 'ETH', 'USDT'),
  ('EUR/USD', 'EURUSD', 'Euro / US Dollar', 'forex', 'EUR', 'USD')
ON CONFLICT (normalized_symbol) DO NOTHING;
