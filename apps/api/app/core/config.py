from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(
        default="postgresql+psycopg://trading:trading@localhost:5432/trading_analyst",
        alias="DATABASE_URL",
    )
    alpha_vantage_api_key: str = Field(default="", alias="ALPHAVANTAGE_API_KEY")
    market_data_cache_ttl_seconds: int = Field(default=30, alias="MARKET_DATA_CACHE_TTL_SECONDS")
    market_data_retry_attempts: int = Field(default=3, alias="MARKET_DATA_RETRY_ATTEMPTS")
    market_data_retry_backoff_seconds: float = Field(
        default=0.3, alias="MARKET_DATA_RETRY_BACKOFF_SECONDS"
    )
    ccxt_exchange_id: str = Field(default="binance", alias="CCXT_EXCHANGE_ID")
    news_cache_ttl_seconds: int = Field(default=120, alias="NEWS_CACHE_TTL_SECONDS")
    news_retry_attempts: int = Field(default=3, alias="NEWS_RETRY_ATTEMPTS")
    news_retry_backoff_seconds: float = Field(default=0.4, alias="NEWS_RETRY_BACKOFF_SECONDS")


settings = Settings()
