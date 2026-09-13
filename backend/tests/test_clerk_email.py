from app.core.auth import email_from_clerk_api, email_from_clerk_claims


def test_email_from_flat_claims():
    assert email_from_clerk_claims({"email": "a@example.com"}) == "a@example.com"
    assert email_from_clerk_claims({"primary_email_address": "b@example.com"}) == (
        "b@example.com"
    )


def test_email_from_nested_user_claim():
    assert (
        email_from_clerk_claims({"user": {"primary_email_address": "c@example.com"}})
        == "c@example.com"
    )


def test_default_clerk_session_has_no_email():
    assert email_from_clerk_claims({"sub": "user_123", "sid": "sess_1"}) == ""


def test_clerk_api_fallback_uses_primary(monkeypatch):
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "primary_email_address_id": "idn_2",
                "email_addresses": [
                    {"id": "idn_1", "email_address": "old@example.com"},
                    {"id": "idn_2", "email_address": "now@example.com"},
                ],
            }

    monkeypatch.setattr(
        "httpx.get", lambda *args, **kwargs: FakeResponse()
    )
    assert email_from_clerk_api("sk_test", "user_123") == "now@example.com"


def test_clerk_api_fallback_skips_without_secret():
    assert email_from_clerk_api(None, "user_123") == ""
