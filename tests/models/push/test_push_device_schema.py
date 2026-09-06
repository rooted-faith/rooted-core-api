"""ORM seam: push.device (Device) — CONTEXT.md "Push notifications"."""

from portal.models import PushDevice


def test_push_device_maps_to_push_device_table() -> None:
    assert PushDevice.__table__.schema == "push"
    assert PushDevice.__tablename__ == "device"
    assert "device_key" in PushDevice.__table__.c
    assert "token" in PushDevice.__table__.c
    assert "platform" in PushDevice.__table__.c
    assert "app_version" in PushDevice.__table__.c
    assert "last_used_at" in PushDevice.__table__.c


def test_push_device_end_user_id_is_nullable_fk_to_app_user() -> None:
    end_user_id = PushDevice.__table__.c.end_user_id
    assert end_user_id.nullable is True
    assert end_user_id.foreign_keys
    fk = next(iter(end_user_id.foreign_keys))
    assert fk.column.table.fullname == "app.user"
    assert fk.ondelete == "CASCADE"


def test_push_device_is_active_defaults_true() -> None:
    is_active = PushDevice.__table__.c.is_active
    assert is_active.nullable is False
    assert is_active.server_default is not None
