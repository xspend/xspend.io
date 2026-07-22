"""Unit tests for app/core/security.py (pure functions, no DB)."""
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_id,
    decode_token,
    encode_id,
    generate_otp,
    hash_password,
    verify_password,
)


def test_hash_password_roundtrip():
    h = hash_password("hunter2!")
    assert h != "hunter2!"                    # never store plaintext
    assert verify_password("hunter2!", h)
    assert not verify_password("wrong", h)


def test_verify_password_bad_hash_is_false():
    # Malformed hash must not raise, just return False.
    assert verify_password("x", "not-a-bcrypt-hash") is False


def test_access_token_roundtrip():
    token, jti, _expires_at = create_access_token(123, "a@test.com")
    payload = decode_token(token)
    assert payload["sub"] == "123"
    assert payload["email"] == "a@test.com"
    assert payload["type"] == "access"
    assert payload["jti"] == jti


def test_refresh_token_roundtrip():
    token, jti, _expires_at = create_refresh_token(123)
    payload = decode_token(token)
    assert payload["sub"] == "123"
    assert payload["type"] == "refresh"
    assert payload["jti"] == jti
    assert "email" not in payload


def test_access_and_refresh_tokens_get_distinct_jtis():
    _at, access_jti, _ = create_access_token(1, "a@test.com")
    _rt, refresh_jti, _ = create_refresh_token(1)
    assert access_jti != refresh_jti


def test_decode_garbage_token_returns_none():
    assert decode_token("garbage.token.value") is None


def test_decode_token_signed_with_other_key_returns_none():
    from jose import jwt
    forged = jwt.encode({"sub": "x"}, "a-different-secret", algorithm="HS256")
    assert decode_token(forged) is None


def test_encode_id_roundtrip():
    encoded = encode_id(42)
    assert encoded != "42"                    # not just the raw int as a string
    assert decode_id(encoded) == 42


def test_decode_id_garbage_returns_none():
    assert decode_id("not-valid-base64!!!") is None


def test_generate_otp_is_six_digits():
    for _ in range(20):
        otp = generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()
