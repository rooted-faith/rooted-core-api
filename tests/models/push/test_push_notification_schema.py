"""ORM seam: push.notification / push.notification_delivery (CONTEXT.md "Push notifications")."""

from portal.models import PushNotification, PushNotificationDelivery


def test_push_notification_maps_to_push_notification_table() -> None:
    assert PushNotification.__table__.schema == "push"
    assert PushNotification.__tablename__ == "notification"
    assert "category" in PushNotification.__table__.c
    assert "title" in PushNotification.__table__.c
    assert "body" in PushNotification.__table__.c
    assert "data" in PushNotification.__table__.c
    assert "created_at" in PushNotification.__table__.c


def test_push_notification_end_user_id_is_required_fk_to_app_user() -> None:
    end_user_id = PushNotification.__table__.c.end_user_id
    assert end_user_id.nullable is False
    assert end_user_id.foreign_keys
    fk = next(iter(end_user_id.foreign_keys))
    assert fk.column.table.fullname == "app.user"
    assert fk.ondelete == "CASCADE"


def test_push_notification_delivery_maps_to_push_notification_delivery_table() -> None:
    assert PushNotificationDelivery.__table__.schema == "push"
    assert PushNotificationDelivery.__tablename__ == "notification_delivery"
    assert "status" in PushNotificationDelivery.__table__.c
    assert "error" in PushNotificationDelivery.__table__.c
    assert "delivered_at" in PushNotificationDelivery.__table__.c
    assert "created_at" in PushNotificationDelivery.__table__.c


def test_push_notification_delivery_foreign_keys_cascade() -> None:
    notification_id = PushNotificationDelivery.__table__.c.notification_id
    device_id = PushNotificationDelivery.__table__.c.device_id
    assert notification_id.nullable is False
    assert device_id.nullable is False

    notification_fk = next(iter(notification_id.foreign_keys))
    assert notification_fk.column.table.fullname == "push.notification"
    assert notification_fk.ondelete == "CASCADE"

    device_fk = next(iter(device_id.foreign_keys))
    assert device_fk.column.table.fullname == "push.device"
    assert device_fk.ondelete == "CASCADE"


def test_push_notification_delivery_unique_on_notification_and_device() -> None:
    unique_constraints = [c for c in PushNotificationDelivery.__table__.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert any({col.name for col in constraint.columns} == {"notification_id", "device_id"} for constraint in unique_constraints)


def test_push_notification_delivery_status_defaults_pending() -> None:
    status = PushNotificationDelivery.__table__.c.status
    assert status.nullable is False
    assert status.server_default is not None
