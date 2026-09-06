"""
Notification repository — SQLAlchemy-backed create + delivery recording.
"""

import json
from typing import Optional
from uuid import UUID, uuid4

from portal.domain.push.entities import Notification, NotificationDeliveryDraft
from portal.libs.database import Session
from portal.models.push import PushNotification, PushNotificationDelivery


class NotificationRepository:
    """Implements NotificationRepositoryPort via structural typing."""

    def __init__(self, session: Session):
        self._session = session

    @staticmethod
    def _serialize_jsonb(value: Optional[dict]) -> Optional[str]:
        """asyncpg JSONB bind expects a JSON text string, not a raw Python value."""
        return json.dumps(value) if value is not None else None

    async def create_notification(self, *, end_user_id: UUID, category: str, title: str, body: str, data: Optional[dict]) -> Notification:
        notification_id = uuid4()
        await (
            self._session.insert(PushNotification)
            .values(id=notification_id, end_user_id=end_user_id, category=category, title=title, body=body, data=self._serialize_jsonb(data))
            .execute()
        )
        return await (
            self._session.select(
                PushNotification.id,
                PushNotification.end_user_id,
                PushNotification.category,
                PushNotification.title,
                PushNotification.body,
                PushNotification.data,
                PushNotification.created_at,
            )
            .where(PushNotification.id == notification_id)
            .fetchrow(as_model=Notification)
        )

    async def record_deliveries(self, deliveries: list[NotificationDeliveryDraft]) -> None:
        if not deliveries:
            return
        await (
            self._session.insert(PushNotificationDelivery)
            .values(
                [
                    {
                        "id": uuid4(),
                        "notification_id": delivery.notification_id,
                        "device_id": delivery.device_id,
                        "status": delivery.status.value,
                        "error": delivery.error,
                        "delivered_at": delivery.delivered_at,
                    }
                    for delivery in deliveries
                ]
            )
            .execute()
        )
