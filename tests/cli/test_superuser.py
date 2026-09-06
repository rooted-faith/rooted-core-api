"""
create_superuser: a failing seed must propagate (not swallow to None) after rollback.
"""

import pytest

from portal.cli import superuser as superuser_module


class _StubSession:
    def __init__(self) -> None:
        self.rollback_called = False
        self.closed = False

    async def rollback(self) -> None:
        self.rollback_called = True

    async def close(self) -> None:
        self.closed = True


class _StubContainer:
    def __init__(self, session: _StubSession) -> None:
        self._session = session

    def db_session(self) -> _StubSession:
        return self._session


class _RaisingSuperuserSeedService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def run(self, **kwargs):
        raise RuntimeError("seed failed")


@pytest.mark.asyncio
async def test_create_superuser_propagates_exception_after_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _StubSession()
    monkeypatch.setattr(superuser_module, "Container", lambda: _StubContainer(session))
    monkeypatch.setattr(superuser_module, "SuperuserSeedService", _RaisingSuperuserSeedService)

    with pytest.raises(RuntimeError, match="seed failed"):
        await superuser_module.create_superuser(email="admin@example.com", password="password123", first_name="Ada", last_name="Min")

    assert session.rollback_called is True
    assert session.closed is True
