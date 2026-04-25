from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./app.db"

    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-02-15-preview"
    azure_openai_deployment: str | None = None

    promed_api_base_url: str = "https://www.promedmail.org/api/v1"
    promed_api_key: str | None = None
    promed_limit: int = 50

    who_odata_url: str = "https://ghoapi.azureedge.net/api/WHOSIS_000001"
    ingest_http_timeout_seconds: float = 15.0
    ingest_who_item_limit: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()
