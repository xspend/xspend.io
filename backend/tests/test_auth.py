"""Unit tests for app/auth/security.py (pure functions, no DB)."""
from app.auth.security import create_token, decode_token, hash_password, verify_password


def test_hash_password_roundtrip():
    h = hash_password("hunter2!")
    assert h != "hunter2!"                    # never store plaintext
    assert verify_password("hunter2!", h)
    assert not verify_password("wrong", h)


def test_verify_password_bad_hash_is_false():
    # Malformed hash must not raise, just return False.
    assert verify_password("x", "not-a-bcrypt-hash") is False


def test_token_roundtrip():
    token = create_token("user-123", "a@test.com")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "a@test.com"


def test_decode_garbage_token_returns_none():
    assert decode_token("garbage.token.value") is None


def test_decode_token_signed_with_other_key_returns_none():
    from jose import jwt
    forged = jwt.encode({"sub": "x"}, "a-different-secret", algorithm="HS256")
    assert decode_token(forged) is None
