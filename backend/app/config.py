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

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Fernet key for encrypting the OAuth token set at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    canopy_fernet_key: str = ""

    database_url: str = "sqlite:///./canopy.sqlite3"

    snapshot_ttl_seconds: int = 300
    frontend_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
