"""
Push device ORM: app install push registration (CONTEXT.md "Device").

Exists independently of authentication: registered on first app launch,
before any account exists, so an anonymous install can hold a Device row
with no End user attached.
"""

import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID

from portal.libs.database.orm import ModelBase
from portal.models.app.user import AppUser
from portal.models.mixins import AuditMixin


class PushDevice(ModelBase, AuditMixin):
    """
    An app install identified by a client-generated device_key.

    Holds at most one push token/platform, and end_user_id is overwritten
    on every registration call (bound on sign-in, cleared on sign-out).
    """

    __extra_table_args__ = (sa.UniqueConstraint("device_key"), {"comment": "Push notification device registrations"})

    device_key = Column(sa.String(255), nullable=False, index=True, comment="Client-generated device install key")
    token = Column(sa.Text, nullable=False, comment="Current push token (FCM/APNs-via-FCM)")
    platform = Column(sa.String(10), nullable=False, comment="Platform: ios|android")
    end_user_id = Column(
        UUID, sa.ForeignKey(AppUser.id, ondelete="CASCADE"), nullable=True, index=True, comment="FK to app.user.id (End user); null when unauthenticated"
    )
    is_active = Column(sa.Boolean, nullable=False, server_default=sa.text("true"), comment="Whether this device should receive pushes")
    last_used_at = Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="Last time this device registered/refreshed")
    app_version = Column(sa.String(32), nullable=True, comment="Client app version at last registration")
