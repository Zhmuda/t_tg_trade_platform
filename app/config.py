from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str
    # Some hosts (e.g. Russian VPS providers) can't reach api.telegram.org directly - set
    # this to an HTTP proxy URL (http://user:pass@host:port) to route Bot API calls through it.
    telegram_proxy_url: str = ""
    master_encryption_key: str
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"
    newsapi_key: str = ""
    gemini_api_key: str = ""
    # flash-lite has a much higher free-tier daily quota than plain 2.5-flash (500 RPD vs
    # 20 RPD at last check) and is plenty capable for a one-line sentiment judgement.
    gemini_model: str = "gemini-3.1-flash-lite"
    real_trading_allowlist: str = ""
    # 1800s (30 min) keeps daily Gemini calls (one per tracked ticker per cycle) well
    # under the free-tier RPD even with several tickers tracked at once - see README.
    sentiment_refresh_interval_seconds: int = 1800

    # Optional single-user convenience: pre-provision T-Invest tokens from .env instead of
    # typing them into the bot via /start. See app/bootstrap.py.
    owner_telegram_id: int | None = None
    tinkoff_sandbox_token: str = ""
    tinkoff_production_token: str = ""

    @property
    def real_trading_allowed_user_ids(self) -> set[int]:
        return {
            int(uid.strip())
            for uid in self.real_trading_allowlist.split(",")
            if uid.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
