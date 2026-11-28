"""Fellowship capacity settings are declared via system setting seeds."""

from portal.cli.datas.system_setting_seed_data import seed_system_settings
from portal.domain.fellowship.constants import (
    DEFAULT_FELLOWSHIP_MAX_ACTIVE_MEMBERS,
    DEFAULT_FELLOWSHIP_MAX_GROUP_MEMBERS,
    FELLOWSHIP_MAX_ACTIVE_MEMBERS_KEY,
    FELLOWSHIP_MAX_GROUP_MEMBERS_KEY,
    FELLOWSHIP_SETTING_NAMESPACE,
)


def test_fellowship_capacity_seed_rows_match_accepted_defaults() -> None:
    by_key = {(row["namespace"], row["setting_key"]): row for row in seed_system_settings}

    active = by_key[(FELLOWSHIP_SETTING_NAMESPACE, FELLOWSHIP_MAX_ACTIVE_MEMBERS_KEY)]
    group = by_key[(FELLOWSHIP_SETTING_NAMESPACE, FELLOWSHIP_MAX_GROUP_MEMBERS_KEY)]

    assert active["value_type"] == "number"
    assert active["value"] == DEFAULT_FELLOWSHIP_MAX_ACTIVE_MEMBERS
    assert active["is_built_in"] is True
    assert group["value"] == DEFAULT_FELLOWSHIP_MAX_GROUP_MEMBERS
