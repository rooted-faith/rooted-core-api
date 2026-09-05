"""Port seam: create_credential accepts null password_hash for passwordless End users."""

from typing import Optional
from uuid import UUID, uuid4

import pytest

from portal.application.auth.results import UserSensitive


class StubCredentialRepository:
    def __init__(self) -> None:
        self.created: list[dict] = []

    async def create_credential(
        self, *, auth_user_id: UUID, email: str, password_hash: Optional[str], is_admin: bool, is_superuser: bool = False, verified: bool = False
    ) -> UUID:
        self.created.append(
            {
                "auth_user_id": auth_user_id,
                "email": email,
                "password_hash": password_hash,
                "is_admin": is_admin,
                "is_superuser": is_superuser,
                "verified": verified,
            }
        )
        return auth_user_id


@pytest.mark.asyncio
async def test_create_credential_allows_null_password_hash() -> None:
    repo = StubCredentialRepository()
    auth_user_id = uuid4()

    result = await repo.create_credential(auth_user_id=auth_user_id, email="member@example.com", password_hash=None, is_admin=False, verified=True)

    assert result == auth_user_id
    assert repo.created[0]["password_hash"] is None
    assert repo.created[0]["email"] == "member@example.com"


@pytest.mark.asyncio
async def test_create_credential_still_accepts_admin_password_hash() -> None:
    repo = StubCredentialRepository()
    auth_user_id = uuid4()

    await repo.create_credential(
        auth_user_id=auth_user_id, email="admin@example.com", password_hash="hashed:Secure1!", is_admin=True, is_superuser=True, verified=True
    )

    assert repo.created[0]["password_hash"] == "hashed:Secure1!"
    assert repo.created[0]["is_admin"] is True
    # Sensitive read model still allows optional password_hash
    user = UserSensitive(id=auth_user_id, email="admin@example.com", password_hash="hashed:Secure1!", first_name="", last_name="")
    assert user.password_hash == "hashed:Secure1!"
