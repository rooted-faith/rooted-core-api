"""
App support policy lookup and the shared App build check (ADR 0017).
"""

import re

from portal.application.app_support.results import AppSupportPolicyResult
from portal.domain.app_support.constants import MAX_APP_BUILD, AppPlatform, AppSupportEnforcement, AppSupportErrorCode
from portal.domain.app_support.entities import AppSupportPolicy
from portal.domain.app_support.ports import AppSupportPolicySource
from portal.exceptions.responses import BadRequestException, ServiceUnavailableException, UpgradeRequiredException
from portal.libs.tracing.distributed_trace import distributed_trace

_BUILD_PATTERN = re.compile(rf"[0-9]{{1,{len(str(MAX_APP_BUILD))}}}", flags=re.ASCII)


class AppSupportService:
    def __init__(self, policy_source: AppSupportPolicySource, enforcement: AppSupportEnforcement):
        self._policy_source = policy_source
        self._enforcement = enforcement

    @distributed_trace()
    async def get_policy(self, platform: str | None) -> AppSupportPolicyResult:
        """
        Policy discovery: never gated, needs no sign-in, and always uses this server's environment.
        :param platform:
        :return:
        """
        policy = self._require_policy(self._parse_platform(platform))
        return AppSupportPolicyResult(
            environment=self._policy_source.environment,
            platform=policy.platform,
            minimum_build=policy.minimum_build,
            latest_build=policy.latest_build,
            update_url=policy.update_url,
            update_instructions=policy.update_instructions,
            enforcement=self._enforcement,
        )

    @distributed_trace()
    async def check_request(self, platform: str | None, build: str | None) -> None:
        """
        Gate an App request. COMPATIBLE admits everything; ENFORCED raises for an invalid identity,
        an unavailable policy, or a build below the minimum.
        :param platform:
        :param build:
        :return:
        """
        if self._enforcement is AppSupportEnforcement.COMPATIBLE:
            return
        app_platform = self._parse_platform(platform)
        app_build = self._parse_build(build)
        policy = self._require_policy(app_platform)
        if not policy.supports(app_build):
            raise UpgradeRequiredException(
                detail="This App build is no longer supported. Update the App to continue.",
                error_code=AppSupportErrorCode.APP_UPDATE_REQUIRED,
                context={"platform": app_platform.value, "build": app_build, "minimum_build": policy.minimum_build},
            )

    @staticmethod
    def _parse_platform(raw: str | None) -> AppPlatform:
        try:
            return AppPlatform((raw or "").strip().lower())
        except ValueError:
            raise BadRequestException(detail="Unknown App platform", error_code=AppSupportErrorCode.APP_IDENTITY_INVALID) from None

    @staticmethod
    def _parse_build(raw: str | None) -> int:
        value = (raw or "").strip()
        if not _BUILD_PATTERN.fullmatch(value):
            raise BadRequestException(detail="Invalid App build number", error_code=AppSupportErrorCode.APP_IDENTITY_INVALID)
        return int(value)

    def _require_policy(self, platform: AppPlatform) -> AppSupportPolicy:
        policy = self._policy_source.get(platform)
        if policy is None:
            raise ServiceUnavailableException(
                detail="App support policy is unavailable", error_code=AppSupportErrorCode.APP_SUPPORT_POLICY_UNAVAILABLE, context={"platform": platform.value}
            )
        return policy
