"""
Auth and RBAC domain constants.
"""

from enum import Enum

# Test passcodes are confined to these exact environments and this one Firebase project (ADR 0016).
OTP_TEST_ENVIRONMENTS = frozenset({"dev", "stg"})
OTP_TEST_FIREBASE_PROJECT_ID = "rooted-app-dev"
OTP_TEST_POLICY_REFRESH_SECONDS = 60.0


class OtpDeliveryMode(str, Enum):
    """How the person obtains the passcode for a challenge; also the challenge's origin."""

    EMAIL = "email"
    FIXED = "fixed"


class AuthErrorCode(str, Enum):
    """Machine-readable auth/RBAC admin error codes for clients."""

    USER_NOT_FOUND = "AUTH_USER_NOT_FOUND"
    USER_ALREADY_EXISTS = "AUTH_USER_ALREADY_EXISTS"
    ROLE_NOT_FOUND = "AUTH_ROLE_NOT_FOUND"
    ROLE_CODE_EXISTS = "AUTH_ROLE_CODE_EXISTS"
    PERMISSION_NOT_FOUND = "AUTH_PERMISSION_NOT_FOUND"
    PERMISSION_CODE_EXISTS = "AUTH_PERMISSION_CODE_EXISTS"
    RESOURCE_NOT_FOUND = "AUTH_RESOURCE_NOT_FOUND"
    RESOURCE_CODE_EXISTS = "AUTH_RESOURCE_CODE_EXISTS"
