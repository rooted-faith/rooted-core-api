"""
Top-level package for auth models.
"""

from .rbac import AuthPermission, AuthPermissionTranslation, AuthResource, AuthResourceTranslation, AuthRole, AuthRoleTranslation, AuthVerb, AuthVerbTranslation
from .relationships import AuthRolePermission, AuthUserRole
from .user import AuthDevice, AuthIdentityLink, AuthIdentityProvider, AuthRefreshToken, AuthUser, AuthUserProfile

__all__ = [
    # user
    "AuthUser",
    "AuthUserProfile",
    "AuthIdentityProvider",
    "AuthIdentityLink",
    # rbac
    "AuthRole",
    "AuthRoleTranslation",
    "AuthResource",
    "AuthResourceTranslation",
    "AuthVerb",
    "AuthVerbTranslation",
    "AuthPermission",
    "AuthPermissionTranslation",
    "AuthUserRole",
    "AuthRolePermission",
    # auth
    "AuthDevice",
    "AuthRefreshToken",
]
