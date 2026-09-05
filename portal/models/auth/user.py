"""
User-related models: Auth credential, profile, Identity provider / link, devices, tokens.
"""

import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from portal.libs.consts.enums import Gender
from portal.libs.database.orm import Base, ModelBase
from portal.models.mixins import AuditMixin, DeletedMixin, DescriptionMixin, RemarkMixin

from .relationships import AuthUserRole


class AuthUser(ModelBase, RemarkMixin, DeletedMixin, AuditMixin):
    """Auth credential (sign-in subject)."""

    email = Column(sa.String(255), nullable=False, unique=True, comment="Email, required unique identifier")
    password_hash = Column(sa.String(512), nullable=True, comment="Password hash; null for passwordless End users")
    salt = Column(sa.String(128), nullable=True, comment="Salt for password hash")
    verified = Column(sa.Boolean, default=False, comment="Is verified")
    is_active = Column(sa.Boolean, default=True, index=True, comment="Is active")
    is_superuser = Column(sa.Boolean, default=False, comment="Is superuser")  # Top-level admin can access all resources in the admin panel
    is_admin = Column(sa.Boolean, default=False, comment="Is admin")  # Can access the admin panel
    account_kind = Column(sa.String(32), comment="Account kind: member, guest, external, service")
    password_changed_at = Column(sa.TIMESTAMP(timezone=True), comment="Password last changed time")
    password_expires_at = Column(sa.TIMESTAMP(timezone=True), comment="Password expiration time")
    last_login_at = Column(sa.TIMESTAMP(timezone=True), comment="Last login")

    # Relationships
    roles = relationship("AuthRole", secondary=AuthUserRole.__table__, back_populates="users", passive_deletes=True)


class AuthUserProfile(ModelBase, AuditMixin, DescriptionMixin):
    """Auth User Profile Model (admin-oriented)."""

    user_id = Column(UUID, sa.ForeignKey(AuthUser.id, ondelete="CASCADE"), nullable=False, unique=True, comment="User ID", index=True)
    first_name = Column(sa.String(64), nullable=False, comment="First name")
    last_name = Column(sa.String(64), nullable=False, comment="Last name")
    title = Column(sa.String(64), comment="Title")
    gender = Column(sa.Integer, default=Gender.UNKNOWN.value, comment="Refer to Gender enum")
    preferred_name = Column(sa.String(64), comment="Preferred name")
    preferred_locale_id = Column(UUID, sa.ForeignKey("public.system_locale.id", ondelete="SET NULL"), nullable=True, index=True, comment="Preferred locale ID")


class AuthIdentityProvider(Base):
    """Catalog of external sign-in sources (Identity provider)."""

    code = Column(sa.String(32), primary_key=True, comment="Stable provider code, e.g. google, apple")
    name = Column(sa.String(64), nullable=False, comment="English display name")
    is_active = Column(sa.Boolean, nullable=False, server_default=sa.text("true"), comment="Whether provider may be used for new links")
    requires_tenant = Column(sa.Boolean, nullable=False, server_default=sa.text("false"), comment="Whether provider_tenant is required on Identity links")


class AuthIdentityLink(ModelBase, DeletedMixin, AuditMixin):
    """Durable binding from an Identity provider subject to an Auth credential."""

    __extra_table_args__ = (
        sa.Index(
            "uq_identity_link_provider_subject_active",
            "provider",
            "provider_tenant",
            "provider_subject",
            unique=True,
            postgresql_where=sa.text("is_deleted IS false"),
            postgresql_nulls_not_distinct=True,
        ),
        sa.Index("uq_identity_link_user_provider_active", "user_id", "provider", unique=True, postgresql_where=sa.text("is_deleted IS false")),
    )

    user_id = Column(UUID, sa.ForeignKey(AuthUser.id, ondelete="CASCADE"), nullable=False, index=True, comment="Auth credential ID")
    provider = Column(
        sa.String(32), sa.ForeignKey("auth.identity_provider.code", ondelete="RESTRICT"), nullable=False, index=True, comment="Identity provider code"
    )
    provider_tenant = Column(sa.String(255), nullable=True, comment="Optional provider tenant (string); null for consumer IdPs")
    provider_subject = Column(sa.String(255), nullable=False, comment="Provider subject / stable user id at the IdP")
    additional_data = Column(JSONB, comment="Optional IdP snapshot (email, name, auth_time); not the identity key")


class AuthDevice(ModelBase, AuditMixin, DeletedMixin):
    """Auth Device Model"""

    __extra_table_args__ = (sa.UniqueConstraint("id", "user_id"),)
    user_id = Column(UUID, sa.ForeignKey("auth.user.id", ondelete="CASCADE"), nullable=False, index=True, comment="User ID")
    first_seen_at = Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="First seen at")
    last_seen_at = Column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), server_onupdate=sa.func.now(), comment="Last seen at")
    last_ip = Column(sa.String(45), nullable=True, comment="Last IP")
    last_user_agent = Column(sa.String(512), nullable=True, comment="Last user agent")


class AuthRefreshToken(ModelBase, AuditMixin, DeletedMixin):
    """Auth Refresh Token Model (whitelist)"""

    user_id = Column(UUID, sa.ForeignKey("auth.user.id", ondelete="CASCADE"), nullable=False, index=True, comment="User ID")
    device_id = Column(UUID, sa.ForeignKey(AuthDevice.id, ondelete="SET NULL"), nullable=True, index=True, comment="Device ID")
    family_id = Column(UUID, nullable=False, index=True, comment="Family ID")
    parent_id = Column(UUID, sa.ForeignKey("auth.refresh_token.id", ondelete="SET NULL"), nullable=True, index=True, comment="Parent ID")
    replaced_by_id = Column(UUID, sa.ForeignKey("auth.refresh_token.id", ondelete="SET NULL"), nullable=True, index=True, comment="Replaced by ID")
    token_hash = Column(sa.String(128), nullable=False, unique=True, index=True, comment="Token hash")
    expires_at = Column(sa.DateTime(timezone=True), nullable=False, index=True, comment="Expires at")
    last_used_at = Column(sa.DateTime(timezone=True), nullable=True, index=True, comment="Last used at")

    revoked_at = Column(sa.DateTime(timezone=True), nullable=True, comment="Revoked at")
    revoked_reason = Column(sa.String(32), nullable=True, comment="Revoked reason")
    ip = Column(sa.String(45), nullable=True, comment="IP")
    user_agent = Column(sa.String(512), nullable=True, comment="User agent")
