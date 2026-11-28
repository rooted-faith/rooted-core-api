"""
App support application results.
"""

from pydantic import BaseModel, Field

from portal.domain.app_support.constants import AppPlatform, AppSupportEnforcement


class AppSupportPolicyResult(BaseModel):
    """Effective policy for one platform in the running environment."""

    environment: str = Field(...)
    platform: AppPlatform = Field(...)
    minimum_build: int = Field(...)
    latest_build: int | None = Field(default=None)
    update_url: str | None = Field(default=None)
    update_instructions: str | None = Field(default=None)
    enforcement: AppSupportEnforcement = Field(...)
