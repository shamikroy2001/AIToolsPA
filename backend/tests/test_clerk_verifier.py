from fastapi import HTTPException

from app.core.auth import ClerkTokenVerifier
from app.core.settings import Settings


def test_clerk_verifier_rejects_when_unconfigured():
    verifier = ClerkTokenVerifier(
        Settings.model_construct(clerk_issuer=None, clerk_jwks_url=None)
    )
    try:
        verifier.verify("anything")
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 401
