"""
Ports for Device, Notification, and PushGateway.
"""

from datetime import datetime
from typing import Optional, Protocol
from uuid import UUID

from portal.domain.push.entities import Device, Notification, NotificationDeliveryDraft, PushSendResult


class DeviceRepositoryPort(Protocol):
    """Persist push Device rows keyed by device_key."""

    async def upsert_device(
        self, *, device_key: str, token: str, platform: str, app_version: Optional[str], end_user_id: Optional[UUID], last_used_at: datetime
    ) -> Device:
        """
        Insert a Device on first registration, or overwrite token/platform/
        app_version/last_used_at/end_user_id on every subsequent call.
        """

    async def list_active_devices(self, end_user_id: UUID) -> list[Device]:
        """List every is_active Device belonging to an End user."""

    async def deactivate_devices(self, device_ids: list[UUID]) -> None:
        """Set is_active = false on the given Device ids."""


class NotificationRepositoryPort(Protocol):
    """Persist Notification and NotificationDelivery rows."""

    async def create_notification(self, *, end_user_id: UUID, category: str, title: str, body: str, data: Optional[dict]) -> Notification:
        """Create a Notification row addressed to an End user."""

    async def record_deliveries(self, deliveries: list[NotificationDeliveryDraft]) -> None:
        """Persist one NotificationDelivery row per attempted Device."""


class PushGatewayPort(Protocol):
    """Send a push message to a batch of device tokens."""

    async def send_multicast(self, *, tokens: list[str], title: str, body: str, data: Optional[dict]) -> list[PushSendResult]:
        """
        Send one message to every token, returning one PushSendResult per
        token in the same order as `tokens`.
        """
