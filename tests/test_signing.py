"""Signing tests, cross-checked against the official Kalshi SDK.

RSA-PSS is randomised, so two signatures over the same message never match
byte-for-byte. Instead we verify *our* reconstruction of the signed message
against a signature the official SDK produced: if the SDK's signature verifies
under our message string, both implementations sign the same bytes.
"""

import base64

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from mentionbot.kalshi.auth import (
    ACCESS_KEY_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    KalshiSigner,
    signing_path,
)

KEY_ID = "0c2f4e1a-1111-2222-3333-444455556666"


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def pem_bytes(rsa_key):
    return rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@pytest.fixture(scope="module")
def signer(rsa_key):
    return KalshiSigner(KEY_ID, rsa_key)


def _verify(public_key, signature_b64: str, message: str) -> bool:
    try:
        public_key.verify(
            base64.b64decode(signature_b64),
            message.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


# -- message construction -------------------------------------------------
@pytest.mark.parametrize(
    "url, expected",
    [
        ("/trade-api/v2/markets", "/trade-api/v2/markets"),
        ("/trade-api/v2/markets?limit=100", "/trade-api/v2/markets"),
        ("https://api.elections.kalshi.com/trade-api/v2/markets", "/trade-api/v2/markets"),
        (
            "https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker=X&limit=5",
            "/trade-api/v2/markets",
        ),
        ("/trade-api/v2/portfolio/orders/abc-123", "/trade-api/v2/portfolio/orders/abc-123"),
    ],
)
def test_signing_path_strips_query_keeps_prefix(url, expected):
    assert signing_path(url) == expected


def test_headers_sign_timestamp_method_path(signer, rsa_key):
    headers = signer.headers("get", "/trade-api/v2/markets?limit=10", timestamp_ms=1700000000123)
    assert headers[ACCESS_KEY_HEADER] == KEY_ID
    assert headers[TIMESTAMP_HEADER] == "1700000000123"
    # Method is upper-cased and the query string is excluded.
    assert _verify(
        rsa_key.public_key(), headers[SIGNATURE_HEADER], "1700000000123GET/trade-api/v2/markets"
    )


def test_signature_rejects_wrong_message(signer, rsa_key):
    headers = signer.headers("GET", "/trade-api/v2/markets", timestamp_ms=1700000000123)
    # Query string must NOT be part of the signed message.
    assert not _verify(
        rsa_key.public_key(),
        headers[SIGNATURE_HEADER],
        "1700000000123GET/trade-api/v2/markets?limit=10",
    )
    # Wrong verb must not verify.
    assert not _verify(
        rsa_key.public_key(), headers[SIGNATURE_HEADER], "1700000000123POST/trade-api/v2/markets"
    )


def test_each_signature_is_fresh(signer):
    """PSS is randomised: identical input must still produce distinct signatures."""
    a = signer.headers("GET", "/trade-api/v2/markets", timestamp_ms=1)[SIGNATURE_HEADER]
    b = signer.headers("GET", "/trade-api/v2/markets", timestamp_ms=1)[SIGNATURE_HEADER]
    assert a != b


def test_from_pem_bytes_roundtrip(pem_bytes, rsa_key):
    loaded = KalshiSigner.from_pem_bytes(KEY_ID, pem_bytes)
    headers = loaded.headers("POST", "/trade-api/v2/portfolio/orders", timestamp_ms=42)
    assert _verify(
        rsa_key.public_key(), headers[SIGNATURE_HEADER], "42POST/trade-api/v2/portfolio/orders"
    )


def test_from_pem_path(tmp_path, pem_bytes, rsa_key):
    p = tmp_path / "kalshi.pem"
    p.write_bytes(pem_bytes)
    headers = KalshiSigner.from_pem_path(KEY_ID, p).headers(
        "DELETE", "/trade-api/v2/portfolio/orders/x", timestamp_ms=7
    )
    assert _verify(
        rsa_key.public_key(), headers[SIGNATURE_HEADER], "7DELETE/trade-api/v2/portfolio/orders/x"
    )


def test_rejects_non_rsa_key():
    from cryptography.hazmat.primitives.asymmetric import ed25519

    pem = ed25519.Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with pytest.raises(ValueError, match="RSA"):
        KalshiSigner.from_pem_bytes(KEY_ID, pem)


# -- cross-check against the official SDK ---------------------------------
def test_matches_official_sdk_signature(pem_bytes, rsa_key):
    """The official SDK's signature must verify under our message construction."""
    kalshi_auth = pytest.importorskip("kalshi_python_sync.auth")

    sdk = kalshi_auth.KalshiAuth(KEY_ID, pem_bytes.decode())
    url = "https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker=KXFOO&limit=100"
    sdk_headers = sdk.create_auth_headers("GET", url)

    assert set(sdk_headers) == {ACCESS_KEY_HEADER, SIGNATURE_HEADER, TIMESTAMP_HEADER}
    assert sdk_headers[ACCESS_KEY_HEADER] == KEY_ID

    ts = sdk_headers[TIMESTAMP_HEADER]
    our_message = ts + "GET" + signing_path(url)
    assert _verify(rsa_key.public_key(), sdk_headers[SIGNATURE_HEADER], our_message)
