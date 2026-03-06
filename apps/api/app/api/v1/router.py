from fastapi import APIRouter

from app.api.v1.endpoints import analysis, assets, health, market_data, news_context, trade_ideas

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(market_data.router, prefix="/market-data", tags=["market-data"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(news_context.router, prefix="/news", tags=["news-context"])
api_router.include_router(trade_ideas.router, prefix="/trade-ideas", tags=["trade-ideas"])
