from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./app.db"

    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-02-15-preview"
    azure_openai_deployment: str | None = None

    who_odata_base_url: str = "https://ghoapi.azureedge.net/api"
    who_odata_url: str = "https://ghoapi.azureedge.net/api/WHOSIS_000001"
    ingest_http_timeout_seconds: float = 15.0
    ingest_who_item_limit: int = 200
    exa_api_url: str = "https://api.exa.ai/search"
    exa_api_key: str | None = None
    exa_default_query: str = "global outbreak signals public health risk"
    exa_num_results: int = 5
    agent_row_limit: int = 100
    agent_query_timeout_seconds: float = 5.0
    agent_allowed_tables_csv: str = "pipeline_run,indicator_snapshot,source_registry"
    agent_max_steps: int = 12
    agent_max_targets: int = 5
    agent_max_exa_calls: int = 5
    agent_snapshot_context_limit: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
