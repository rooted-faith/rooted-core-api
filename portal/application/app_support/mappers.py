"""
App support application mappers (API boundary).
"""

from portal.application.app_support.results import AppSupportPolicyResult
from portal.serializers.apis.v1.app_support import AppSupportPolicyResponse


def app_support_policy_to_api(result: AppSupportPolicyResult) -> AppSupportPolicyResponse:
    return AppSupportPolicyResponse(
        environment=result.environment,
        platform=result.platform.value,
        minimum_build=result.minimum_build,
        latest_build=result.latest_build,
        update_url=result.update_url,
        update_instructions=result.update_instructions,
        enforcement=result.enforcement.value,
    )
