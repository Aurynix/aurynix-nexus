from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify():
    plain = "mysecretpassword"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)


def test_wrong_password_rejected():
    hashed = hash_password("correct")
    assert not verify_password("wrong", hashed)


def test_access_token_roundtrip():
    user_id = "user-abc-123"
    token, jti = create_access_token(user_id)
    assert token
    assert jti

    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == user_id
    assert payload["jti"] == jti
    assert payload["type"] == "access"


def test_refresh_token_type():
    token, jti = create_refresh_token("user-xyz")
    payload = decode_token(token)
    assert payload is not None
    assert payload["type"] == "refresh"


def test_invalid_token_returns_none():
    assert decode_token("not.a.valid.token") is None


def test_tampered_token_returns_none():
    token, _ = create_access_token("user-1")
    tampered = token[:-5] + "XXXXX"
    assert decode_token(tampered) is None
