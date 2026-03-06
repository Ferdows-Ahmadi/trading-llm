from fastapi import APIRouter

from app.schemas.asset import AssetOut
from app.services.asset_service import list_assets

router = APIRouter()


@router.get("/", response_model=list[AssetOut])
async def get_assets() -> list[AssetOut]:
    return list_assets()
