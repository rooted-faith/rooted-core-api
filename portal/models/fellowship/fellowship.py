"""Fellowship and membership tables under the fellowship schema."""

import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID

from portal.libs.database.orm import ModelBase
from portal.models.app.user import AppUser
from portal.models.mixins import AuditMixin, DeletedMixin


class FellowshipFellowship(ModelBase, AuditMixin, DeletedMixin):
    """Invitation-based Fellowship community."""

    __extra_table_args__ = (
        sa.CheckConstraint("discoverability IN ('public', 'private')", name="discoverability"),
        {"comment": "Fellowship community. Public/private is future search eligibility only."},
    )

    name = Column(sa.String(100), nullable=False, comment="Fellowship display name")
    discoverability = Column(
        sa.String(16), nullable=False, server_default="private", comment="Future search eligibility: public|private (not content visibility)"
    )


class FellowshipMembership(ModelBase, AuditMixin, DeletedMixin):
    """End-user participation in a Fellowship."""

    __extra_table_args__ = (
        sa.CheckConstraint("role IN ('owner', 'admin', 'group_leader', 'member')", name="role"),
        sa.Index("uq_membership_active_user", "fellowship_id", "user_id", unique=True, postgresql_where=sa.text("is_deleted = false")),
        sa.Index("uq_membership_one_owner", "fellowship_id", unique=True, postgresql_where=sa.text("role = 'owner' AND is_deleted = false")),
        {"comment": "Fellowship membership with covenant acceptance and fixed roles"},
    )

    fellowship_id = Column(UUID, sa.ForeignKey(FellowshipFellowship.id, ondelete="CASCADE"), nullable=False, index=True, comment="FK to fellowship.fellowship")
    user_id = Column(UUID, sa.ForeignKey(AppUser.id, ondelete="CASCADE"), nullable=False, index=True, comment="FK to app.user.id (End user)")
    role = Column(sa.String(32), nullable=False, comment="owner|admin|group_leader|member")
    covenant_accepted_at = Column(sa.DateTime(timezone=True), nullable=True, comment="When the member explicitly accepted the Covenant; null until accepted")
