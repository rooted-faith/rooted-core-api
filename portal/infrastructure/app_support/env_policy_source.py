"""
App support policy read once from the APP_SUPPORT_POLICY environment variable (docs/operations/app-support-policy.md).
"""

import json
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from portal.domain.app_support.constants import MAX_APP_BUILD, AppPlatform
from portal.domain.app_support.entities import AppSupportPolicy
from portal.libs.logger import logger


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


class EnvAppSupportPolicySource:
    """
    Parse `{"<env>": {"ios": {...}, "android": {...}}}` and keep only this environment's entry.
    Each platform is validated on its own, so one broken entry leaves the other platform usable.
    """

    def __init__(self, raw: str | None, environment: str):
        self._environment = environment.lower()
        self._policies: dict[AppPlatform, AppSupportPolicy] = self._parse(raw)

    @property
    def environment(self) -> str:
        return self._environment

    def get(self, platform: AppPlatform) -> AppSupportPolicy | None:
        return self._policies.get(platform)

    def _parse(self, raw: str | None) -> dict[AppPlatform, AppSupportPolicy]:
        if not raw or not raw.strip():
            logger.warning("APP_SUPPORT_POLICY is not set; App support policy is unavailable")
            return {}
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error(f"APP_SUPPORT_POLICY is not valid JSON; App support policy is unavailable: {exc.msg}")
            return {}
        if not isinstance(document, dict):
            logger.error("APP_SUPPORT_POLICY must be a JSON object keyed by environment; App support policy is unavailable")
            return {}
        entry = document.get(self._environment)
        if not isinstance(entry, dict):
            logger.error(f"APP_SUPPORT_POLICY has no object for environment '{self._environment}'; App support policy is unavailable")
            return {}

        known = {platform.value for platform in AppPlatform}
        for unknown in sorted(set(entry) - known):
            logger.error(f"APP_SUPPORT_POLICY.{self._environment}.{unknown} is not a supported platform and is ignored")

        policies: dict[AppPlatform, AppSupportPolicy] = {}
        for platform in AppPlatform:
            if platform.value not in entry:
                logger.warning(f"APP_SUPPORT_POLICY.{self._environment}.{platform.value} is missing; that platform's policy is unavailable")
                continue
            try:
                parsed = _PlatformPolicy.model_validate(entry[platform.value])
            except ValidationError as exc:
                reasons = "; ".join(f"{'.'.join(str(part) for part in error['loc']) or 'policy'}: {error['msg']}" for error in exc.errors())
                logger.error(f"APP_SUPPORT_POLICY.{self._environment}.{platform.value} is invalid and unavailable: {reasons}")
                continue
            policies[platform] = AppSupportPolicy(
                platform=platform,
                minimum_build=parsed.minimum_build,
                latest_build=parsed.latest_build,
                update_url=parsed.update_url,
                update_instructions=parsed.update_instructions,
            )
        return policies
