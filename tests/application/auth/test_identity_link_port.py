"""
Port seam: UserRepositoryPort Identity-link lookup / upsert / soft-delete re-link.

Uses an in-memory fake that encodes ADR 0005 active-row uniqueness so
application code can depend on the contract before SQL is migrated.
"""

from typing import Any, Optional
from uuid import UUID, uuid4

import pytest


class InMemoryIdentityLinkStore:
    """Fake UserRepositoryPort Identity-link methods (active-row uniqueness)."""

    def __init__(self) -> None:
        self._links: list[dict[str, Any]] = []

    def _active(self) -> list[dict[str, Any]]:
        return [row for row in self._links if not row["is_deleted"]]

    def _matches_subject(self, row: dict[str, Any], provider: str, provider_subject: str, provider_tenant: Optional[str]) -> bool:
        return row["provider"] == provider and row["provider_subject"] == provider_subject and row["provider_tenant"] == provider_tenant

    async def get_user_id_by_identity_link(self, provider: str, provider_subject: str, provider_tenant: Optional[str] = None) -> Optional[UUID]:
        for row in self._active():
            if self._matches_subject(row, provider, provider_subject, provider_tenant):
                return row["user_id"]
        return None

    async def upsert_identity_link(
        self, user_id: UUID, provider: str, provider_subject: str, *, provider_tenant: Optional[str] = None, additional_data: Optional[dict[str, Any]] = None
    ) -> None:
        for row in self._active():
            if self._matches_subject(row, provider, provider_subject, provider_tenant):
                row["user_id"] = user_id
                row["additional_data"] = additional_data
                return
            if row["user_id"] == user_id and row["provider"] == provider:
                row["provider_subject"] = provider_subject
                row["provider_tenant"] = provider_tenant
                row["additional_data"] = additional_data
                return
        self._links.append(
            {
                "id": uuid4(),
                "user_id": user_id,
                "provider": provider,
                "provider_tenant": provider_tenant,
                "provider_subject": provider_subject,
                "additional_data": additional_data,
                "is_deleted": False,
            }
        )

    async def soft_delete_identity_link(self, user_id: UUID, provider: str) -> None:
        for row in self._active():
            if row["user_id"] == user_id and row["provider"] == provider:
                row["is_deleted"] = True
                return


@pytest.mark.asyncio
async def test_identity_link_lookup_returns_user_after_upsert() -> None:
    store = InMemoryIdentityLinkStore()
    user_id = uuid4()

    await store.upsert_identity_link(user_id, "google", "google-sub-1", additional_data={"email": "a@example.com"})

    found = await store.get_user_id_by_identity_link("google", "google-sub-1")
    assert found == user_id
    assert await store.get_user_id_by_identity_link("google", "missing") is None
    assert await store.get_user_id_by_identity_link("google", "google-sub-1", provider_tenant="tenant-a") is None


@pytest.mark.asyncio
async def test_identity_link_upsert_updates_additional_data_for_same_subject() -> None:
    store = InMemoryIdentityLinkStore()
    user_id = uuid4()

    await store.upsert_identity_link(user_id, "apple", "apple-sub-1", additional_data={"v": 1})
    await store.upsert_identity_link(user_id, "apple", "apple-sub-1", additional_data={"v": 2})

    assert await store.get_user_id_by_identity_link("apple", "apple-sub-1") == user_id
    active = [row for row in store._links if not row["is_deleted"]]
    assert len(active) == 1
    assert active[0]["additional_data"] == {"v": 2}


@pytest.mark.asyncio
async def test_identity_link_soft_delete_then_re_link_same_subject() -> None:
    store = InMemoryIdentityLinkStore()
    user_id = uuid4()

    await store.upsert_identity_link(user_id, "google", "google-sub-1")
    await store.soft_delete_identity_link(user_id, "google")
    assert await store.get_user_id_by_identity_link("google", "google-sub-1") is None

    await store.upsert_identity_link(user_id, "google", "google-sub-1", additional_data={"re": True})
    assert await store.get_user_id_by_identity_link("google", "google-sub-1") == user_id
    assert sum(1 for row in store._links if not row["is_deleted"]) == 1
    assert sum(1 for row in store._links if row["is_deleted"]) == 1
