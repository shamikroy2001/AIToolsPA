"""Clerk JWT verification. Tests inject a fake verifier — never call live JWKS in pytest."""

from __future__ import annotations

from typing import Protocol

import jwt
from fastapi import HTTPException, status
from jwt import PyJWKClient

from app.core.principals import ClerkPrincipal
from app.core.settings import Settings


class TokenVerifier(Protocol):
    def verify(self, token: str) -> ClerkPrincipal: ...


def email_from_clerk_claims(payload: dict) -> str:
    """Clerk's default session JWT has `sub` but usually no email."""
    for key in ("email", "primary_email", "primary_email_address"):
        value = payload.get(key)
        if isinstance(value, str) and "@" in value:
            return value
    user = payload.get("user")
    if isinstance(user, dict):
        for key in ("email", "primary_email_address"):
            value = user.get(key)
            if isinstance(value, str) and "@" in value:
                return value
    return ""


def email_from_clerk_api(secret_key: str | None, clerk_user_id: str) -> str:
    if not secret_key or not clerk_user_id:
        return ""
    try:
        import httpx

        response = httpx.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return ""
    rows = data.get("email_addresses") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return ""
    primary_id = data.get("primary_email_address_id")
    for row in rows:
        if isinstance(row, dict) and row.get("id") == primary_id:
            email = row.get("email_address")
            if isinstance(email, str) and "@" in email:
                return email
    for row in rows:
        if isinstance(row, dict):
            email = row.get("email_address")
            if isinstance(email, str) and "@" in email:
                return email
    return ""


class ClerkTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._issuer = settings.clerk_issuer
        self._jwks = (
            PyJWKClient(settings.clerk_jwks_url)
            if settings.clerk_jwks_url
            else None
        )

    def verify(self, token: str) -> ClerkPrincipal:
        if not token or self._jwks is None or not self._issuer:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={"verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            ) from exc

        clerk_user_id = payload.get("sub")
        if not clerk_user_id or not isinstance(clerk_user_id, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        email = email_from_clerk_claims(payload) or email_from_clerk_api(
            self._settings.clerk_secret_key, clerk_user_id
        )
        return ClerkPrincipal(clerk_user_id=clerk_user_id, email=email)


class StaticTokenVerifier:
    """Maps bearer tokens to principals. Used only in tests."""

    def __init__(self, tokens: dict[str, ClerkPrincipal]) -> None:
        self._tokens = tokens

    def verify(self, token: str) -> ClerkPrincipal:
        principal = self._tokens.get(token)
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        return principal
