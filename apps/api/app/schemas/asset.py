from pydantic import BaseModel


class AssetOut(BaseModel):
    id: str
    symbol: str
    display_name: str
    asset_class: str
