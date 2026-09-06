"""
Google ID token verifier (ADR 0006) — signature, issuer, expiry, and audience via PyJWT + Google's published JWKS.
"""

from typing import Optional

import jwt

from portal.domain.auth.entities import GoogleIdentityClaims
from portal.libs.logger import logger

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}


class GoogleIdTokenVerifier:
    """Verifies Google-issued ID tokens against Google's published JWKS (RS256)."""

    def __init__(self):
        self._jwk_client = jwt.PyJWKClient(GOOGLE_JWKS_URL)

    async def verify(self, id_token: str, audiences: list[str]) -> Optional[GoogleIdentityClaims]:
        if not id_token or not audiences:
            return None
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(id_token, signing_key.key, algorithms=["RS256"], audience=audiences, issuer=GOOGLE_ISSUERS)
        except jwt.PyJWTError as error:
            logger.warning(f"Google ID token verification failed: {error}")
            return None

        subject = claims.get("sub")
        if not subject:
            return None
        return GoogleIdentityClaims(subject=subject, email=claims.get("email"), email_verified=bool(claims.get("email_verified")), audience=claims.get("aud"))
