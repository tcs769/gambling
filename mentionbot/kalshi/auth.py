"""Kalshi API request signing.

Kalshi authenticates each request with an RSA-PSS signature over
``timestamp_ms + HTTP_METHOD + path``, where ``path`` is the request path
*without* the query string. Verified against the official ``kalshi-python-sync``
SDK (see tests/test_signing.py).
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

ACCESS_KEY_HEADER = "KALSHI-ACCESS-KEY"
SIGNATURE_HEADER = "KALSHI-ACCESS-SIGNATURE"
TIMESTAMP_HEADER = "KALSHI-ACCESS-TIMESTAMP"


def signing_path(url_or_path: str) -> str:
    """Return the path Kalshi expects in the signed message.

    Accepts a full URL or a bare path and strips any query string. The path is
    signed in full, including the ``/trade-api/v2`` prefix.
    """
    if url_or_path.startswith(("http://", "https://")):
        return urlparse(url_or_path).path
    return url_or_path.split("?", 1)[0]


class KalshiSigner:
    """Signs Kalshi requests with an RSA private key."""

    def __init__(self, key_id: str, private_key: RSAPrivateKey):
        if not key_id:
            raise ValueError("KALSHI_API_KEY_ID is empty")
        self.key_id = key_id
        self._private_key = private_key

    @classmethod
    def from_pem_path(cls, key_id: str, pem_path: str | Path) -> KalshiSigner:
        """Load an RSA private key from a PEM file on disk."""
        pem_bytes = Path(pem_path).read_bytes()
        return cls.from_pem_bytes(key_id, pem_bytes)

    @classmethod
    def from_pem_bytes(cls, key_id: str, pem_bytes: bytes) -> KalshiSigner:
        key = serialization.load_pem_private_key(
            pem_bytes, password=None, backend=default_backend()
        )
        if not isinstance(key, RSAPrivateKey):
            raise ValueError("Kalshi requires an RSA private key")
        return cls(key_id, key)

    def sign_message(self, message: str) -> str:
        """Sign a pre-built message string, returning base64."""
        signature = self._private_key.sign(
            message.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii")

    def headers(
        self, method: str, url_or_path: str, timestamp_ms: int | None = None
    ) -> dict[str, str]:
        """Build the three Kalshi auth headers for one request."""
        ts = str(timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))
        path = signing_path(url_or_path)
        message = ts + method.upper() + path
        return {
            ACCESS_KEY_HEADER: self.key_id,
            SIGNATURE_HEADER: self.sign_message(message),
            TIMESTAMP_HEADER: ts,
        }
