"""
Identity provider catalog seed use case for CLI (insert-if-missing).
"""

import click

from portal.libs.database import Session
from portal.libs.logger import logger
from portal.models import AuthIdentityProvider


class IdentityProviderSeedService:
    """Insert Identity provider catalog rows when code is absent; never overwrite."""

    def __init__(self, session: Session):
        self._session = session

    async def run(self, seed_rows: list[dict]) -> int:
        inserted = 0
        for row in seed_rows:
            existing = await self._session.select(AuthIdentityProvider.code).where(AuthIdentityProvider.code == row["code"]).fetchval()
            if existing:
                continue
            await (
                self._session.insert(AuthIdentityProvider)
                .values(code=row["code"], name=row["name"], is_active=row["is_active"], requires_tenant=row["requires_tenant"])
                .execute()
            )
            inserted += 1
        await self._session.commit()
        click.echo(click.style(f"Identity providers seeded. inserted={inserted} skipped={len(seed_rows) - inserted}", fg="bright_green"))
        logger.info("Identity provider seed completed. inserted=%s skipped=%s", inserted, len(seed_rows) - inserted)
        return inserted
