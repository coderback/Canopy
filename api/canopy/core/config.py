from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"  # development | test | production

    # The app connects as a NON-owner role so Postgres row-level security applies.
    # Migrations run as the owner role (see migrations/env.py).
    database_url: str = "postgresql+psycopg://canopy_app:canopy_app@localhost:5432/canopy"
    migrations_database_url: str = "postgresql+psycopg://canopy:canopy@localhost:5432/canopy"

    # Public URLs: the API (OAuth callbacks) and the web app (redirect after login).
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"

    # Xero app (standard auth-code flow). One app is both the identity provider
    # (Sign Up with Xero, OIDC) and the data connection (accounting scopes).
    xero_client_id: str = ""
    xero_client_secret: str = ""
    # Milestone 1 is read-only by construction: request no write scopes.
    xero_connect_scopes: str = "openid profile email offline_access accounting.settings.read"

    # Comma-separated Fernet keys, newest first. MultiFernet encrypts with the first
    # and decrypts with any, so keys can be rotated without re-consenting.
    token_encryption_keys: str = ""

    session_cookie_name: str = "canopy_session"
    session_ttl_hours: int = 12
    # Cookies need Secure in production; plain http://localhost in development.
    cookie_secure: bool = False

    # LLM (mapping suggestions). Provider modes mirror the hackathon seam:
    # "azure_ad" (Foundry + Entra ID), "azure" (api key), "openai" (compatible endpoint).
    llm_provider: str = "azure_ad"
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_ad_scope: str = "https://ai.azure.com/.default"
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"
    llm_temperature: float | None = None

    # Xero quota: defer a tenant's jobs when its remaining calls drop to this floor.
    xero_min_remaining_floor: int = Field(default=3, ge=0)
    xero_day_remaining_floor: int = Field(default=50, ge=0)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
