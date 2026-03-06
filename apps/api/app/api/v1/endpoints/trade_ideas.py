from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.trade_ideas import TradeIdeaRequest, TradeIdeaResponse
from app.trade_ideas.exceptions import TradeIdeaError
from app.trade_ideas.service import TradeIdeaService, get_trade_idea_service, serialize_trade_thesis

router = APIRouter()


@router.post("/generate", response_model=TradeIdeaResponse)
def generate_trade_idea(
    payload: TradeIdeaRequest,
    service: TradeIdeaService = Depends(get_trade_idea_service),
) -> TradeIdeaResponse:
    try:
        thesis = service.generate_thesis(
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            asset_class=payload.asset_class,
            candle_limit=payload.candle_limit,
            news_limit=payload.news_limit,
            news_hours=payload.news_hours,
        )
    except TradeIdeaError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "trade_idea_error", "message": str(exc)},
        ) from exc
    return TradeIdeaResponse.model_validate(serialize_trade_thesis(thesis))
