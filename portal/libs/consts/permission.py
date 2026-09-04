"""
Permission constants - Template: System resources only
"""

from enum import Enum


class Verb(Enum):
    """Verb enum"""

    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class Resource(Enum):
    """Resource enum"""

    SYSTEM_PERMISSION = "system:permission"
    SYSTEM_RESOURCE = "system:resource"
    SYSTEM_ROLE = "system:role"
    SYSTEM_USER = "system:user"
    SYSTEM_LOG = "system:log"
    SYSTEM_SETTING = "system:setting"
    CONTENT_FILE = "content:file"
    CONTENT_LEGAL_DOCUMENT = "content:legal_document"


class Permission:
    """
    Permission - usage: Permission.{resource}.{verb}
    E.g., Permission.SYSTEM_USER.READ = "system:user:read"
    """

    class PermissionCode:
        def __init__(self, resource: Resource):
            self._resource_value = resource.value

        @property
        def all(self):
            return f"{self._resource_value}:*"

        @property
        def read(self):
            return f"{self._resource_value}:{Verb.READ.value}"

        @property
        def create(self):
            return f"{self._resource_value}:{Verb.CREATE.value}"

        @property
        def modify(self):
            return f"{self._resource_value}:{Verb.UPDATE.value}"

        @property
        def delete(self):
            return f"{self._resource_value}:{Verb.DELETE.value}"

    SYSTEM_PERMISSION = PermissionCode(Resource.SYSTEM_PERMISSION)
    SYSTEM_RESOURCE = PermissionCode(Resource.SYSTEM_RESOURCE)
    SYSTEM_ROLE = PermissionCode(Resource.SYSTEM_ROLE)
    SYSTEM_USER = PermissionCode(Resource.SYSTEM_USER)
    SYSTEM_LOG = PermissionCode(Resource.SYSTEM_LOG)
    SYSTEM_SETTING = PermissionCode(Resource.SYSTEM_SETTING)
    CONTENT_FILE = PermissionCode(Resource.CONTENT_FILE)
    CONTENT_LEGAL_DOCUMENT = PermissionCode(Resource.CONTENT_LEGAL_DOCUMENT)
