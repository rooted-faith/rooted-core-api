"""
App End user and Preferences tables under the app schema.

Product FKs (journal, groups, walk days, …) reference AppUser.id — not AuthUser.id.
"""

import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID

from portal.libs.database.orm import ModelBase
from portal.models.auth.user import AuthUser
from portal.models.mixins import AuditMixin, DeletedMixin


class AppUser(ModelBase, AuditMixin, DeletedMixin):
    """
    End user product identity.

    Own UUID distinct from auth.user.id. Created only when someone registers
    or uses the app as an End user; pure Admin accounts need not have a row.
    """

    __extra_table_args__ = (
        sa.UniqueConstraint("auth_user_id"),
        {"comment": ("End user identity (app.user). Future product FKs target this id, not auth.user.id (ADR 0004).")},
    )

    auth_user_id = Column(
        UUID, sa.ForeignKey(AuthUser.id, ondelete="CASCADE"), nullable=False, index=True, comment="Shared credential FK to auth.user (IDs are not shared)"
    )


class AppUserPreferences(ModelBase, AuditMixin):
    """
    1:1 Preferences for an End user.

    bible_version is a soft string catalog key, not a hard FK to bible.versions.
    """

    __extra_table_args__ = (sa.UniqueConstraint("user_id"), {"comment": "End user Preferences 1:1 with app.user (not auth.user_profile)"})

    user_id = Column(UUID, sa.ForeignKey(AppUser.id, ondelete="CASCADE"), nullable=False, index=True, comment="FK to app.user.id (End user)")
    display_name = Column(sa.String(100), nullable=False, comment="Display name")
    locale = Column(sa.String(10), nullable=False, server_default="zh-Hant", comment="Locale tag")
    theme = Column(sa.String(10), nullable=False, server_default="system", comment="Theme: light|dark|system")
    font_scale = Column(sa.String(2), nullable=False, server_default="M", comment="Font scale: S|M|L")
    bible_version = Column(sa.String(20), nullable=False, server_default="cuv1919", comment="Soft bible version key (not a hard FK)")
    stage = Column(sa.String(20), nullable=True, comment="Stage: seeking|growing|serving")
    reminder_time = Column(sa.Time(), nullable=True, comment="Daily reminder time")
    reminder_enabled = Column(sa.Boolean, nullable=False, server_default=sa.text("false"), comment="Whether reminder is enabled")
