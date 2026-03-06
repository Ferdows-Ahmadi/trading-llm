export type AssetClass = "crypto" | "forex";

export interface Asset {
  id: string;
  symbol: string;
  displayName: string;
  assetClass: AssetClass;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}
