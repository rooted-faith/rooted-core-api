from enum import StrEnum

# Largest build number the gate and the policy accept (nine decimal digits).
MAX_APP_BUILD = 999_999_999


class AppPlatform(StrEnum):
    IOS = "ios"
    ANDROID = "android"


class AppSupportEnforcement(StrEnum):
    """COMPATIBLE never rejects a request; ENFORCED rejects unsupported or unidentified App requests."""

    COMPATIBLE = "compatible"
    ENFORCED = "enforced"


class AppSupportErrorCode(StrEnum):
    APP_UPDATE_REQUIRED = "APP_UPDATE_REQUIRED"
    APP_IDENTITY_INVALID = "APP_IDENTITY_INVALID"
    APP_SUPPORT_POLICY_UNAVAILABLE = "APP_SUPPORT_POLICY_UNAVAILABLE"
