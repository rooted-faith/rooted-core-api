"""ORM seam: Auth credential + Identity provider / Identity link (ADR 0005)."""

from portal.models import AuthIdentityLink, AuthIdentityProvider, AuthUser


def test_auth_user_requires_email_and_drops_phone_number() -> None:
    assert AuthUser.__table__.schema == "auth"
    assert AuthUser.__tablename__ == "user"
    assert AuthUser.__table__.c.email.nullable is False
    assert "phone_number" not in AuthUser.__table__.c
    assert AuthUser.__table__.c.password_hash.nullable is True


def test_identity_provider_uses_code_primary_key() -> None:
    assert AuthIdentityProvider.__table__.schema == "auth"
    assert AuthIdentityProvider.__tablename__ == "identity_provider"
    assert list(AuthIdentityProvider.__table__.primary_key.columns.keys()) == ["code"]
    assert "name" in AuthIdentityProvider.__table__.c
    assert "is_active" in AuthIdentityProvider.__table__.c
    assert "requires_tenant" in AuthIdentityProvider.__table__.c
    assert "id" not in AuthIdentityProvider.__table__.c


def test_identity_link_has_no_oauth_token_columns_and_soft_delete() -> None:
    assert AuthIdentityLink.__table__.schema == "auth"
    assert AuthIdentityLink.__tablename__ == "identity_link"
    columns = AuthIdentityLink.__table__.c
    assert "provider" in columns
    assert "provider_tenant" in columns
    assert columns.provider_tenant.nullable is True
    assert "provider_subject" in columns
    assert columns.provider_subject.nullable is False
    assert "additional_data" in columns
    assert "is_deleted" in columns
    assert "access_token" not in columns
    assert "refresh_token" not in columns
    assert "token_expires_at" not in columns
    assert "provider_uid" not in columns
    assert "provider_tenant_id" not in columns
