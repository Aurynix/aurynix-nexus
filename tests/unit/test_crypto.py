from app.core.crypto import decrypt, encrypt


def test_encrypt_decrypt_roundtrip():
    plaintext = "hello world"
    assert decrypt(encrypt(plaintext)) == plaintext


def test_encrypt_produces_different_ciphertext_each_call():
    plaintext = "same text"
    assert encrypt(plaintext) != encrypt(plaintext)


def test_roundtrip_json():
    import json

    data = {"token": "abc", "refresh_token": "xyz", "scopes": ["email", "calendar"]}
    blob = encrypt(json.dumps(data))
    recovered = json.loads(decrypt(blob))
    assert recovered == data
