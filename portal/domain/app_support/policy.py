"""
Field rules for one platform's App support policy, shared by the admin write path and the policy read path.
"""

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from portal.domain.app_support.constants import MAX_APP_BUILD, AppPlatform
from portal.domain.app_support.entities import AppSupportPolicy


class InvalidAppSupportPolicy(ValueError):
    """A stored or submitted platform policy breaks the field rules."""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


class _PlatformPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    minimum_build: int = Field(ge=0, le=MAX_APP_BUILD)
    latest_build: int | None = Field(default=None, ge=0, le=MAX_APP_BUILD)
    update_url: str | None = None
    update_instructions: str | None = None

    @field_validator("update_url")
    @classmethod
    def _https_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("update_url must be an absolute https URL")
        return value.strip()

    @field_validator("update_instructions")
    @classmethod
    def _non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("update_instructions must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def _consistent(self) -> "_PlatformPolicy":
        if self.latest_build is not None and self.latest_build < self.minimum_build:
            raise ValueError("latest_build must not be below minimum_build")
        if self.update_url is None and self.update_instructions is None:
            raise ValueError("update_url or update_instructions is required")
        return self


def parse_platform_policy(platform: AppPlatform, value: Any) -> AppSupportPolicy:
    """
    Validate one platform's policy object.
    :param platform:
    :param value:
    :return:
    :raises InvalidAppSupportPolicy:
    """
    try:
        parsed = _PlatformPolicy.model_validate(value)
    except ValidationError as exc:
        raise InvalidAppSupportPolicy([f"{'.'.join(str(part) for part in error['loc']) or 'policy'}: {error['msg']}" for error in exc.errors()]) from None
    return AppSupportPolicy(
        platform=platform,
        minimum_build=parsed.minimum_build,
        latest_build=parsed.latest_build,
        update_url=parsed.update_url,
        update_instructions=parsed.update_instructions,
    )
