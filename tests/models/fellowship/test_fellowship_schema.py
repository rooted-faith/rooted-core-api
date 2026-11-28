"""ORM schema contracts for Fellowship tables."""

from portal.models.fellowship import FellowshipFellowship, FellowshipMembership


def test_fellowship_tables_use_fellowship_schema_and_expected_columns() -> None:
    assert FellowshipFellowship.__table__.schema == "fellowship"
    assert FellowshipFellowship.__tablename__ == "fellowship"
    assert {"name", "discoverability", "is_deleted"} <= set(FellowshipFellowship.__table__.columns.keys())

    assert FellowshipMembership.__table__.schema == "fellowship"
    assert FellowshipMembership.__tablename__ == "membership"
    assert {"fellowship_id", "user_id", "role", "covenant_accepted_at", "is_deleted"} <= set(FellowshipMembership.__table__.columns.keys())


def test_preferences_primary_fellowship_column_exists() -> None:
    from portal.models.app import AppUserPreferences

    assert "primary_fellowship_id" in AppUserPreferences.__table__.columns.keys()
