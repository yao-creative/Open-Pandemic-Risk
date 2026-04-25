from functools import lru_cache

from openai import AzureOpenAI

from .settings import get_settings


@lru_cache
def get_azure_openai_client() -> AzureOpenAI:
    settings = get_settings()
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


def check_azure_ready() -> tuple[bool, str | None]:
    settings = get_settings()
    missing = []
    if not settings.azure_openai_endpoint:
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not settings.azure_openai_api_key:
        missing.append("AZURE_OPENAI_API_KEY")
    if not settings.azure_openai_deployment:
        missing.append("AZURE_OPENAI_DEPLOYMENT")

    if missing:
        return False, f"missing env vars: {', '.join(missing)}"

    try:
        get_azure_openai_client()
        return True, None
    except Exception as exc:  # pragma: no cover - library-specific errors
        return False, f"azure client init error: {exc}"
