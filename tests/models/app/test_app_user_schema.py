"""ORM seam: app.user and app.user_preferences under the app schema (ADR 0004)."""

from portal.models import AppUser, AppUserPreferences, AuthUserProfile


def test_app_user_maps_to_app_user_table() -> None:
    assert AppUser.__table__.schema == "app"
    assert AppUser.__tablename__ == "user"
    assert "auth_user_id" in AppUser.__table__.c


def test_app_user_preferences_maps_to_user_preferences_table() -> None:
    assert AppUserPreferences.__table__.schema == "app"
    assert AppUserPreferences.__tablename__ == "user_preferences"
    assert "bible_version" in AppUserPreferences.__table__.c
    assert AppUserPreferences.__table__.c.user_id.foreign_keys


def test_app_user_preferences_has_sunday_week_start_default() -> None:
    column = AppUserPreferences.__table__.c.week_start

    assert column.nullable is False
    assert column.server_default is not None
    assert column.server_default.arg == "sunday"
    constraints = {str(constraint.sqltext) for constraint in AppUserPreferences.__table__.constraints if hasattr(constraint, "sqltext")}
    assert "week_start IN ('sunday', 'monday')" in constraints


def test_app_user_preferences_has_no_account_level_locale_column() -> None:
    """ADR 0009: UI language follows each Device's system locale — never a synced account Preference."""
    assert "locale" not in AppUserPreferences.__table__.c


def test_auth_user_profile_remains_admin_oriented_separate_from_app_prefs() -> None:
    assert AuthUserProfile.__table__.schema == "auth"
    assert AuthUserProfile.__tablename__ == "user_profile"
    assert "display_name" not in AuthUserProfile.__table__.c
    assert "bible_version" not in AuthUserProfile.__table__.c
