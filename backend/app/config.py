from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Xero OAuth 2.0 app (standard auth-code flow — ONE app connected to all orgs)
    xero_client_id: str = ""
    xero_client_secret: str = ""
    xero_redirect_uri: str = "http://localhost:8000/auth/xero/callback"
    # Only request scopes the app has enabled in its Xero portal config, or the
    # authorize call fails with `invalid_scope`. Phase 1 (item/account/contact/
    # tracking) needs only settings + contacts. Add `accounting.transactions` here
    # once it's enabled on the app (Phase 3: bills, manual journals, purchase orders).
    xero_scopes: str = (
        "offline_access openid profile email "
        "accounting.settings accounting.contacts"
    )

    # LLM = Azure AI Foundry via the OpenAI-compatible SDK (mapping/ingest/matching
    # engines). Provider modes:
    #   "azure_ad" — Foundry /openai/v1 endpoint + Entra ID (DefaultAzureCredential
    #                token provider); NO api key. This is our setup.
    #   "azure"    — classic AzureOpenAI(azure_endpoint, api_version) with an api key.
    #   "openai"   — plain OpenAI(base_url, api_key) for any OpenAI-compatible endpoint.
    llm_provider: str = "azure_ad"

    # Foundry /openai/v1 endpoint, e.g.
    # https://<resource>.services.ai.azure.com/openai/v1
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""     # the model deployment name (e.g. gpt-5.4-mini)
    azure_ad_scope: str = "https://ai.azure.com/.default"

    # Only used by llm_provider="azure" (api-key mode).
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # Generic OpenAI-compatible fallback (used when llm_provider="openai").
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"

    # gpt-5-class models reject non-default temperature; leave None to omit it.
    llm_temperature: float | None = None

    # Fernet key for encrypting the OAuth token set at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    canopy_fernet_key: str = ""

    database_url: str = "sqlite:///./canopy.sqlite3"

    snapshot_ttl_seconds: int = 300
    frontend_origin: str = "http://localhost:3000"

    # Dev-only: exposes POST /demo/seed and lets approval simulate Xero writes
    # (via DemoXeroApi) when no real token is connected. Set false in production.
    demo_mode: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
