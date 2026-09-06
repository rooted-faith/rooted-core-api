"""
Top-level package for models.
"""

from .app import AppUser, AppUserPreferences
from .audit import AuditLog
from .auth import (
    AuthDevice,
    AuthIdentityLink,
    AuthIdentityProvider,
    AuthPermission,
    AuthPermissionTranslation,
    AuthRefreshToken,
    AuthResource,
    AuthResourceTranslation,
    AuthRole,
    AuthRolePermission,
    AuthRoleTranslation,
    AuthUser,
    AuthUserProfile,
    AuthUserRole,
    AuthVerb,
    AuthVerbTranslation,
)
from .bible import BibleBook, BibleVerse, BibleVersion
from .content import ContentFile, ContentFileAssociation, ContentLegalDocument, ContentLegalDocumentTranslation
from .push import PushDevice
from .system_locale import SystemLocale
from .system_setting import SystemSetting

__all__ = [
    # audit
    "AuditLog",
    # user
    "AuthUser",
    "AuthUserProfile",
    "AuthIdentityProvider",
    "AuthIdentityLink",
    # app end user (product FKs target AppUser.id, not AuthUser.id)
    "AppUser",
    "AppUserPreferences",
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
    # locale
    "SystemLocale",
    # system setting
    "SystemSetting",
    # auth
    "AuthDevice",
    "AuthRefreshToken",
    # content
    "ContentFile",
    "ContentFileAssociation",
    "ContentLegalDocument",
    "ContentLegalDocumentTranslation",
    # bible
    "BibleBook",
    "BibleVerse",
    "BibleVersion",
    # push
    "PushDevice",
]
