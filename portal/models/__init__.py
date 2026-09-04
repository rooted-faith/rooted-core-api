"""
Top-level package for models.
"""

from .audit import AuditLog
from .auth import (
    AuthDevice,
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
    AuthUserThirdParty,
    AuthVerb,
    AuthVerbTranslation,
)
from .bible import BibleBook, BibleVerse, BibleVersion
from .content import ContentFile, ContentFileAssociation, ContentLegalDocument, ContentLegalDocumentTranslation
from .system_locale import SystemLocale
from .system_setting import SystemSetting

__all__ = [
    # audit
    "AuditLog",
    # user
    "AuthUser",
    "AuthUserProfile",
    "AuthUserThirdParty",
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
]
