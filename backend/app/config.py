from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Xero OAuth 2.0 app (standard auth-code flow — ONE app connected to all orgs)
    xero_client_id: str = ""
    xero_client_secret: str = ""
    xero_redirect_uri: str = "http://localhost:8000/auth/xero/callback"
    # Broad scopes remain valid until Sept 2027; override with granular scopes via .env
    # once confirmed against developer.xero.com (March 2026 scope changes).
    xero_scopes: str = (
        "offline_access openid profile email "
        "accounting.settings accounting.contacts accounting.transactions"
    )

    # LLM = Azure AI Foundry via the OpenAI-compatible SDK (mapping/ingest/matching
    # engines). "azure" uses AzureOpenAI(azure_endpoint, api_version, deployment);
    # "openai" uses OpenAI(base_url, api_key, model) for a plain OpenAI-compatible
    # endpoint (OpenAI, DeepSeek, a Foundry serverless URL, etc.).
    llm_provider: str = "azure"

    azure_openai_endpoint: str = ""       # https://<resource>.openai.azure.com
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str = ""     # the model deployment name

    # Generic OpenAI-compatible fallback (used when llm_provider="openai").
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"

    # Fernet key for encrypting the OAuth token set at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    canopy_fernet_key: str = ""

    database_url: str = "sqlite:///./canopy.sqlite3"

    snapshot_ttl_seconds: int = 300
    frontend_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
