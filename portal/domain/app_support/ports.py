from typing import Protocol

from portal.domain.app_support.constants import AppPlatform
from portal.domain.app_support.entities import AppSupportPolicy


class AppSupportPolicySource(Protocol):
    """Operational policy for the environment this process runs in."""

    @property
    def environment(self) -> str: ...

    async def get(self, platform: AppPlatform) -> AppSupportPolicy | None:
        """The valid policy for the platform, or None when it is missing, invalid, or cannot be read."""
        ...
