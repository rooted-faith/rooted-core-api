"""identity_link_and_auth_credential

Revision ID: 94a54cea8e8f
Revises: 5786a69aae71
Create Date: 2026-09-05 18:41:00.000000

Human-owned migration for ADR 0005 / issue #14:
- auth.user: email NOT NULL; drop phone_number
- replace auth.user_third_party with identity_provider + identity_link
- seed google + apple Identity providers
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "94a54cea8e8f"
down_revision: Union[str, Sequence[str], None] = "5786a69aae71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, table_name: str, schema: str = "auth") -> bool:
    return inspector.has_table(table_name, schema=schema)


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str, schema: str = "auth") -> bool:
    if not _has_table(inspector, table_name, schema=schema):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name, schema=schema))


def _has_unique_constraint(inspector: sa.Inspector, table_name: str, constraint_name: str, schema: str = "auth") -> bool:
    if not _has_table(inspector, table_name, schema=schema):
        return False
    return any(uq.get("name") == constraint_name for uq in inspector.get_unique_constraints(table_name, schema=schema))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str, schema: str = "auth") -> bool:
    if not _has_table(inspector, table_name, schema=schema):
        return False
    return any(ix.get("name") == index_name for ix in inspector.get_indexes(table_name, schema=schema))


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS auth"))

    if not _has_table(inspector, "user"):
        raise RuntimeError("auth.user is missing. Apply the platform auth baseline (or create_all for auth) before this revision.")

    # --- auth.user: required email, drop phone ---
    if _has_column(inspector, "user", "email"):
        op.execute(sa.text("DELETE FROM auth.user WHERE email IS NULL"))
        op.alter_column("user", "email", existing_type=sa.String(length=255), nullable=False, schema="auth", comment="Email, required unique identifier")

    if _has_unique_constraint(inspector, "user", "uq_user_phone_number"):
        op.drop_constraint("uq_user_phone_number", "user", schema="auth", type_="unique")
    if _has_index(inspector, "user", "uq_user_phone_number"):
        op.drop_index("uq_user_phone_number", table_name="user", schema="auth")
    if _has_column(inspector, "user", "phone_number"):
        op.drop_column("user", "phone_number", schema="auth")

    # Refresh inspector after user alterations
    inspector = sa.inspect(bind)

    # --- Identity provider catalog ---
    if not _has_table(inspector, "identity_provider"):
        op.create_table(
            "identity_provider",
            sa.Column("code", sa.String(length=32), nullable=False, comment="Stable provider code, e.g. google, apple"),
            sa.Column("name", sa.String(length=64), nullable=False, comment="English display name"),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False, comment="Whether provider may be used for new links"),
            sa.Column(
                "requires_tenant",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
                comment="Whether provider_tenant is required on Identity links",
            ),
            sa.PrimaryKeyConstraint("code", name=op.f("pk_identity_provider")),
            schema="auth",
        )

    # --- Identity link ---
    if not _has_table(inspector, "identity_link"):
        op.create_table(
            "identity_link",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False, comment="Primary Key"),
            sa.Column("user_id", sa.UUID(), nullable=False, comment="Auth credential ID"),
            sa.Column("provider", sa.String(length=32), nullable=False, comment="Identity provider code"),
            sa.Column("provider_tenant", sa.String(length=255), nullable=True, comment="Optional provider tenant (string); null for consumer IdPs"),
            sa.Column("provider_subject", sa.String(length=255), nullable=False, comment="Provider subject / stable user id at the IdP"),
            sa.Column(
                "additional_data",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                comment="Optional IdP snapshot (email, name, auth_time); not the identity key",
            ),
            sa.Column("delete_reason", sa.String(length=64), nullable=True, comment="Delete Reason"),
            sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False, comment="Is Deleted(Logical Delete)"),
            sa.Column("created_by_id", sa.UUID(), nullable=True, comment="Create User ID"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="Create Date"),
            sa.Column("created_by", sa.String(length=64), nullable=False, comment="Create User Name"),
            sa.Column("updated_by_id", sa.UUID(), nullable=True, comment="Update User ID"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="Update Date"),
            sa.Column("updated_by", sa.String(length=64), nullable=False, comment="Update User Name"),
            sa.ForeignKeyConstraint(
                ["provider"], ["auth.identity_provider.code"], name=op.f("fk_identity_link_provider_identity_provider"), ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], name=op.f("fk_identity_link_user_id_user"), ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_link")),
            schema="auth",
        )
        op.create_index(op.f("ix_identity_link_provider"), "identity_link", ["provider"], unique=False, schema="auth")
        op.create_index(op.f("ix_identity_link_user_id"), "identity_link", ["user_id"], unique=False, schema="auth")
        op.create_index(
            "uq_identity_link_provider_subject_active",
            "identity_link",
            ["provider", "provider_tenant", "provider_subject"],
            unique=True,
            schema="auth",
            postgresql_where=sa.text("is_deleted IS false"),
            postgresql_nulls_not_distinct=True,
        )
        op.create_index(
            "uq_identity_link_user_provider_active",
            "identity_link",
            ["user_id", "provider"],
            unique=True,
            schema="auth",
            postgresql_where=sa.text("is_deleted IS false"),
        )

    # --- Drop legacy NewLife third-party table ---
    inspector = sa.inspect(bind)
    if _has_table(inspector, "user_third_party"):
        if _has_index(inspector, "user_third_party", "ix_user_third_party_user_id"):
            op.drop_index(op.f("ix_user_third_party_user_id"), table_name="user_third_party", schema="auth")
        op.drop_table("user_third_party", schema="auth")

    # --- Seed Identity providers (google + apple only) ---
    op.execute(
        sa.text(
            """
            INSERT INTO auth.identity_provider (code, name, is_active, requires_tenant)
            VALUES
                ('google', 'Google', true, false),
                ('apple', 'Apple', true, false)
            ON CONFLICT (code) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "identity_link"):
        op.drop_index("uq_identity_link_user_provider_active", table_name="identity_link", schema="auth")
        op.drop_index("uq_identity_link_provider_subject_active", table_name="identity_link", schema="auth")
        op.drop_index(op.f("ix_identity_link_user_id"), table_name="identity_link", schema="auth")
        op.drop_index(op.f("ix_identity_link_provider"), table_name="identity_link", schema="auth")
        op.drop_table("identity_link", schema="auth")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "identity_provider"):
        op.drop_table("identity_provider", schema="auth")

    if not _has_table(inspector, "user_third_party") and _has_table(inspector, "user"):
        op.create_table(
            "user_third_party",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False, comment="Primary Key"),
            sa.Column("user_id", sa.UUID(), nullable=False, comment="User ID"),
            sa.Column("provider", sa.String(length=16), nullable=False, comment="Provider name, Enum: ThirdPartyProvider"),
            sa.Column("provider_tenant_id", sa.UUID(), nullable=False, comment="Provider tenant ID"),
            sa.Column("provider_uid", sa.String(length=255), nullable=False, comment="Provider UID"),
            sa.Column("access_token", sa.String(length=255), nullable=True, comment="Access token"),
            sa.Column("refresh_token", sa.String(length=255), nullable=True, comment="Refresh token"),
            sa.Column("token_expires_at", sa.TIMESTAMP(timezone=True), nullable=True, comment="Token expiration time"),
            sa.Column("additional_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Additional data"),
            sa.Column("delete_reason", sa.String(length=64), nullable=True, comment="Delete Reason"),
            sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False, comment="Is Deleted(Logical Delete)"),
            sa.Column("created_by_id", sa.UUID(), nullable=True, comment="Create User ID"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="Create Date"),
            sa.Column("created_by", sa.String(length=64), nullable=False, comment="Create User Name"),
            sa.Column("updated_by_id", sa.UUID(), nullable=True, comment="Update User ID"),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="Update Date"),
            sa.Column("updated_by", sa.String(length=64), nullable=False, comment="Update User Name"),
            sa.ForeignKeyConstraint(["user_id"], ["auth.user.id"], name="fk_user_third_party_user", ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_user_third_party")),
            sa.UniqueConstraint("user_id", "provider", "provider_uid", name=op.f("uq_user_third_party_user_id_provider_provider_uid")),
            schema="auth",
        )
        op.create_index(op.f("ix_user_third_party_user_id"), "user_third_party", ["user_id"], unique=False, schema="auth")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "user") and not _has_column(inspector, "user", "phone_number"):
        op.add_column("user", sa.Column("phone_number", sa.String(length=16), nullable=True, comment="Phone number, unique identifier"), schema="auth")
        op.create_unique_constraint(op.f("uq_user_phone_number"), "user", ["phone_number"], schema="auth")

    if _has_table(inspector, "user") and _has_column(inspector, "user", "email"):
        op.alter_column("user", "email", existing_type=sa.String(length=255), nullable=True, schema="auth", comment="Email, unique identifier")
