# Trading Analyst API

## Run locally
```bash
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Docs
- OpenAPI: `http://localhost:8000/api/v1/openapi.json`
- Swagger UI: `http://localhost:8000/api/v1/docs`

## Market Data Endpoints
- `GET /api/v1/market-data/providers`
- `POST /api/v1/market-data/ingest/ohlcv`
- `GET /api/v1/market-data/candles`
- `POST /api/v1/analysis/run`
- `GET /api/v1/news/providers`
- `POST /api/v1/news/ingest`
- `GET /api/v1/news/feed`
- `POST /api/v1/trade-ideas/generate`

## Example Calls
```bash
curl http://localhost:8000/api/v1/market-data/providers

curl -X POST http://localhost:8000/api/v1/market-data/ingest/ohlcv \
  -H "Content-Type: application/json" \
  -d '{
    "provider_code": "ccxt",
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "limit": 200,
    "asset_class": "crypto"
  }'

curl "http://localhost:8000/api/v1/market-data/candles?symbol=BTCUSDT&timeframe=1h&limit=50"

curl -X POST http://localhost:8000/api/v1/analysis/run \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "limit": 300,
    "asset_class": "crypto"
  }'

curl -X POST http://localhost:8000/api/v1/news/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "provider_code": "alpha_vantage",
    "limit": 50,
    "symbols": ["BTCUSDT", "EURUSD"],
    "asset_class": "crypto"
  }'

curl "http://localhost:8000/api/v1/news/feed?limit=20&hours=72"

curl -X POST http://localhost:8000/api/v1/trade-ideas/generate \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "asset_class": "crypto",
    "candle_limit": 300,
    "news_limit": 20,
    "news_hours": 72
  }'
```
