"""
NotificationDelivery ORM: one delivery attempt of a Notification to one Device
(CONTEXT.md "Notification delivery").
"""

import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID

from portal.libs.database.orm import ModelBase
from portal.models.mixins import AuditCreatedAtMixin
from portal.models.push.device import PushDevice
from portal.models.push.notification import PushNotification


class PushNotificationDelivery(ModelBase, AuditCreatedAtMixin):
    """
    Records success/failure of sending one Notification to one Device.

    The basis for deactivating a Device whose token has permanently failed.
    """

    __extra_table_args__ = (sa.UniqueConstraint("notification_id", "device_id"), {"comment": "Per-device delivery attempts for a Notification"})

    notification_id = Column(UUID, sa.ForeignKey(PushNotification.id, ondelete="CASCADE"), nullable=False, index=True, comment="FK to push.notification.id")
    device_id = Column(UUID, sa.ForeignKey(PushDevice.id, ondelete="CASCADE"), nullable=False, index=True, comment="FK to push.device.id")
    status = Column(sa.String(16), nullable=False, server_default=sa.text("'pending'"), comment="Delivery status: pending|success|failed")
    error = Column(sa.Text, nullable=True, comment="Failure detail, if any")
    delivered_at = Column(sa.DateTime(timezone=True), nullable=True, comment="When delivery to this Device succeeded")
