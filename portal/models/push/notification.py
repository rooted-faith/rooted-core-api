"""
Notification ORM: a push-worthy event addressed to one End user (CONTEXT.md "Notification").
"""

import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB, UUID

from portal.libs.database.orm import ModelBase
from portal.models.app.user import AppUser
from portal.models.mixins import AuditCreatedAtMixin


class PushNotification(ModelBase, AuditCreatedAtMixin):
    """A single push-worthy event, fanned out to every active Device of end_user_id at send time."""

    __extra_table_args__ = {"comment": "Push notifications addressed to an End user"}

    end_user_id = Column(UUID, sa.ForeignKey(AppUser.id, ondelete="CASCADE"), nullable=False, index=True, comment="FK to app.user.id (End user)")
    category = Column(sa.String(64), nullable=False, comment="Free-form notification category")
    title = Column(sa.Text, nullable=False, comment="Notification title")
    body = Column(sa.Text, nullable=False, comment="Notification body")
    data = Column(JSONB, nullable=True, comment="Optional structured payload")
