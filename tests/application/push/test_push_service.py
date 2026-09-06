"""
Tests for PushService.
"""

from uuid import uuid4

import pytest

from portal.application.push.push_service import PushService
from portal.domain.push.entities import Device


class StubDeviceRepository:
    def __init__(self):
        self.devices: dict[str, Device] = {}

    async def upsert_device(self, *, device_key, token, platform, app_version, end_user_id, last_used_at):
        existing = self.devices.get(device_key)
        device = Device(
            id=existing.id if existing else uuid4(),
            device_key=device_key,
            token=token,
            platform=platform,
            end_user_id=end_user_id,
            is_active=existing.is_active if existing else True,
            last_used_at=last_used_at,
            app_version=app_version,
        )
        self.devices[device_key] = device
        return device


@pytest.mark.asyncio
async def test_register_device_anonymous_leaves_end_user_id_none():
    service = PushService(StubDeviceRepository())
    result = await service.register_device(device_key="device-1", token="tok-1", platform="ios", app_version="1.0.0", end_user_id=None)
    assert result.end_user_id is None
    assert result.device_key == "device-1"
    assert result.token == "tok-1"
    assert result.platform == "ios"
    assert result.app_version == "1.0.0"
    assert result.is_active is True


@pytest.mark.asyncio
async def test_register_device_authenticated_sets_end_user_id():
    end_user_id = uuid4()
    service = PushService(StubDeviceRepository())
    result = await service.register_device(device_key="device-1", token="tok-1", platform="android", app_version=None, end_user_id=end_user_id)
    assert result.end_user_id == end_user_id


@pytest.mark.asyncio
async def test_reregistering_same_device_key_overwrites_previous_owner():
    repository = StubDeviceRepository()
    service = PushService(repository)
    first_owner = uuid4()
    first = await service.register_device(device_key="device-1", token="tok-1", platform="ios", app_version="1.0.0", end_user_id=first_owner)

    second_owner = uuid4()
    second = await service.register_device(device_key="device-1", token="tok-2", platform="ios", app_version="1.1.0", end_user_id=second_owner)

    assert second.id == first.id
    assert second.end_user_id == second_owner
    assert second.token == "tok-2"
    assert second.app_version == "1.1.0"


@pytest.mark.asyncio
async def test_reregistering_unauthenticated_after_sign_in_clears_end_user_id():
    """Sign-out case: the client calls again without a bearer token, overwriting end_user_id back to None."""
    repository = StubDeviceRepository()
    service = PushService(repository)
    await service.register_device(device_key="device-1", token="tok-1", platform="ios", app_version="1.0.0", end_user_id=uuid4())

    signed_out = await service.register_device(device_key="device-1", token="tok-1", platform="ios", app_version="1.0.0", end_user_id=None)

    assert signed_out.end_user_id is None
