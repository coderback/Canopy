"""Xero identity: authorize URL, code exchange, refresh, id_token validation.

One Xero app serves both purposes:
- Sign Up with Xero (OIDC `openid profile email`) identifies the *person*.
- Connecting orgs adds `offline_access` + accounting scopes (incremental consent).
PKCE (S256) is used on every authorization, on top of the client secret.
"""

from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlencode

import httpx
import jwt

from ..core.config import get_settings

AUTHORIZE_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"
JWKS_URL = "https://identity.xero.com/.well-known/openid-configuration/jwks"
CONNECTIONS_URL = "https://api.xero.com/connections"
REVOCATION_URL = "https://identity.xero.com/connect/revocation"
ISSUER = "https://identity.xero.com"

LOGIN_SCOPES = "openid profile email"


class XeroAuthError(Exception):
    """Token endpoint rejected the request. `revoked` means the grant is gone
    (refresh token expired or the user disconnected) and needs re-consent."""

    def __init__(self, message: str, *, revoked: bool = False):
        super().__init__(message)
        self.revoked = revoked


@dataclass(frozen=True)
class Identity:
    xero_user_id: str
    email: str
    name: str


def redirect_uri() -> str:
    return f"{get_settings().api_base_url}/auth/xero/callback"


def authorize_url(*, scopes: str, state: str, nonce: str, code_challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": get_settings().xero_client_id,
        "redirect_uri": redirect_uri(),
        "scope": scopes,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


class XeroIdentityClient:
    """HTTP calls to Xero's identity service. `transport` is injectable for tests."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=30.0)

    async def _token_request(self, data: dict) -> dict:
        s = get_settings()
        async with self._client() as client:
            resp = await client.post(
                TOKEN_URL, data=data, auth=(s.xero_client_id, s.xero_client_secret)
            )
        if resp.status_code >= 400:
            body = resp.text[:300]
            revoked = resp.status_code == 400 and "invalid_grant" in body
            raise XeroAuthError(f"Xero token endpoint {resp.status_code}: {body}", revoked=revoked)
        return resp.json()

    async def exchange_code(self, code: str, code_verifier: str) -> dict:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(),
                "code_verifier": code_verifier,
            }
        )

    async def refresh(self, refresh_token: str) -> dict:
        return await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )

    async def list_connections(self, access_token: str, auth_event_id: str | None = None) -> list[dict]:
        """Tenants this token can reach; filtered to one consent when auth_event_id is given."""
        params = {"authEventId": auth_event_id} if auth_event_id else None
        async with self._client() as client:
            resp = await client.get(
                CONNECTIONS_URL,
                params=params,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
        resp.raise_for_status()
        return resp.json()

    async def delete_connection(self, access_token: str, xero_connection_ref: str) -> None:
        async with self._client() as client:
            resp = await client.delete(
                f"{CONNECTIONS_URL}/{xero_connection_ref}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code not in (204, 404):
            resp.raise_for_status()

    async def revoke(self, refresh_token: str) -> None:
        """Revoke a grant: Xero drops every connection it holds. Used once none of
        its organisations is connected in Canopy any more."""
        s = get_settings()
        async with self._client() as client:
            resp = await client.post(REVOCATION_URL, data={"token": refresh_token},
                                     auth=(s.xero_client_id, s.xero_client_secret))
        # A token that's already invalid is fine: the grant is gone either way.
        if resp.status_code >= 400 and not (resp.status_code == 400 and "invalid" in resp.text):
            resp.raise_for_status()


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(JWKS_URL, cache_keys=True)


# Our clock and Xero's are never exactly in step: a token Xero issued "now" can
# look a few seconds into the future here (seen live: ~4s), which a zero-tolerance
# check rejects. A minute is the usual allowance for iat/exp.
CLOCK_SKEW_SECONDS = 60


def verify_id_token(id_token: str, *, nonce: str, signing_key=None) -> Identity:
    """Validate signature, issuer, audience, expiry and nonce; return the person.
    `signing_key` is injectable for tests; production fetches it from Xero's JWKS."""
    key = signing_key or _jwks_client().get_signing_key_from_jwt(id_token).key
    claims = jwt.decode(
        id_token,
        key=key,
        algorithms=["RS256"],
        audience=get_settings().xero_client_id,
        issuer=ISSUER,
        options={"require": ["exp", "iat", "aud", "iss"]},
        leeway=CLOCK_SKEW_SECONDS,
    )
    if claims.get("nonce") != nonce:
        raise jwt.InvalidTokenError("nonce mismatch")
    xero_user_id = claims.get("xero_userid") or claims.get("sub")
    if not xero_user_id or not claims.get("email"):
        raise jwt.InvalidTokenError("id_token missing user id or email")
    name = claims.get("name") or " ".join(
        p for p in (claims.get("given_name"), claims.get("family_name")) if p
    )
    return Identity(xero_user_id=xero_user_id, email=claims["email"], name=name)


def unverified_claims(access_token: str) -> dict:
    """Read claims from Xero's JWT access token (e.g. authentication_event_id).
    Only used for routing hints from a token we just received over TLS from
    Xero's token endpoint; never for authorization decisions."""
    return jwt.decode(access_token, options={"verify_signature": False})
