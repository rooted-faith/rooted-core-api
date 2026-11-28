"""Fellowship domain constants."""

from enum import Enum


class FellowshipDiscoverability(str, Enum):
    """Future search eligibility only; not content visibility."""

    PUBLIC = "public"
    PRIVATE = "private"


class FellowshipRole(str, Enum):
    """Fixed first-release Fellowship roles."""

    OWNER = "owner"
    ADMIN = "admin"
    GROUP_LEADER = "group_leader"
    MEMBER = "member"


class FellowshipErrorCode(str, Enum):
    """Machine-readable Fellowship error codes for clients."""

    COVENANT_REQUIRED = "FELLOWSHIP_COVENANT_REQUIRED"
    FULL = "FELLOWSHIP_FULL"
    NOT_FOUND = "FELLOWSHIP_NOT_FOUND"
    NOT_MEMBER = "FELLOWSHIP_NOT_MEMBER"
    ALREADY_MEMBER = "FELLOWSHIP_ALREADY_MEMBER"
    INVALID_DISCOVERABILITY = "FELLOWSHIP_INVALID_DISCOVERABILITY"


FELLOWSHIP_SETTING_NAMESPACE = "fellowship"
FELLOWSHIP_MAX_ACTIVE_MEMBERS_KEY = "max_active_members"
FELLOWSHIP_MAX_GROUP_MEMBERS_KEY = "max_group_members"
DEFAULT_FELLOWSHIP_MAX_ACTIVE_MEMBERS = 50
DEFAULT_FELLOWSHIP_MAX_GROUP_MEMBERS = 15
