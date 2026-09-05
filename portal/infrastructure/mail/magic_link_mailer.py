"""
Deliver magic-link tokens (log when SMTP is not wired).
"""

import logging

from portal.config import settings

logger = logging.getLogger(__name__)


class MagicLinkMailer:
    """Out-of-band delivery of a one-time magic-link token."""

    async def send_magic_link(self, email: str, token: str) -> None:
        # SMTP settings are not yet part of Configuration; log so local/dev
        # verify flows can still capture tokens from the mailer stub in tests.
        logger.info("Magic link issued for %s (expires in %s minutes)", email, settings.MAGIC_LINK_TOKEN_EXPIRE_MINUTES)
        if settings.IS_DEV:
            logger.debug("Magic link token for %s: %s", email, token)
