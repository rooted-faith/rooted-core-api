from dataclasses import dataclass

from portal.domain.app_support.constants import AppPlatform


@dataclass(frozen=True)
class AppSupportPolicy:
    """Validated policy for one platform in the running environment."""

    platform: AppPlatform
    minimum_build: int
    latest_build: int | None
    update_url: str | None
    update_instructions: str | None

    def supports(self, build: int) -> bool:
        """Only a build below the minimum is unsupported; differing from latest_build never is."""
        return build >= self.minimum_build
