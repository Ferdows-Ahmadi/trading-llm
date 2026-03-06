from fastapi import APIRouter, Depends, HTTPException, status

from app.analysis.exceptions import AnalysisError
from app.analysis.service import AnalysisService, get_analysis_service, serialize_analysis_result
from app.schemas.analysis import AnalysisResponse, AnalysisRunRequest

router = APIRouter()


@router.post("/run", response_model=AnalysisResponse)
def run_analysis(
    payload: AnalysisRunRequest,
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisResponse:
    try:
        result = service.analyze_asset(
            raw_symbol=payload.symbol,
            timeframe=payload.timeframe,
            limit=payload.limit,
            asset_class=payload.asset_class,
        )
    except AnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "analysis_error", "message": str(exc)},
        ) from exc
    return AnalysisResponse.model_validate(serialize_analysis_result(result))
