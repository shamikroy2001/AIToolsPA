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


class ClerkTokenVerifier:
    def __init__(self, settings: Settings) -> None:
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
        email = payload.get("email") or payload.get("primary_email") or ""
        if not isinstance(email, str):
            email = ""
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
