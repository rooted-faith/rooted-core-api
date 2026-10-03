"""End-user Sign in with Apple application service (ADR 0008)."""

from portal.application.app.commands import ProvisionIdentityCommand
from portal.application.app.end_user_provisioning_service import EndUserProvisioningService
from portal.application.auth.commands import AppAppleLoginCommand
from portal.application.auth.member_login_service import MemberLoginService
from portal.application.auth.results import MemberLoginResult, UserSensitive
from portal.config import settings
from portal.domain.app.ports import EndUserRepositoryPort
from portal.domain.auth.entities import AppleIdentityClaims
from portal.domain.auth.ports import AppleIdTokenVerifierPort, UserRepositoryPort
from portal.exceptions.responses import UnauthorizedException
from portal.libs.contexts.request_context import get_resolved_locale_code
from portal.libs.tracing.distributed_trace import distributed_trace

APPLE_PROVIDER_CODE = "apple"
GENERIC_FAILURE_DETAIL = "Apple sign-in failed"


def _is_end_user_eligible(user: UserSensitive) -> bool:
    return user.verified and user.is_active


class AppAppleAuthService:
    """Resolve a verified Apple identity token to an End user, provisioning on first success."""

    def __init__(
        self,
        provisioning_service: EndUserProvisioningService,
        user_repository: UserRepositoryPort,
        end_user_repository: EndUserRepositoryPort,
        apple_id_token_verifier: AppleIdTokenVerifierPort,
        member_login_service: MemberLoginService,
    ):
        self._provisioning_service = provisioning_service
        self._user_repository = user_repository
        self._end_user_repository = end_user_repository
        self._verifier = apple_id_token_verifier
        self._member_login_service = member_login_service

    @distributed_trace()
    async def login_with_apple(self, command: AppAppleLoginCommand) -> MemberLoginResult:
        app_code = self._member_login_service.resolve_app_code()
        client_ids = settings.apple_app_client_ids
        if not client_ids or not await self._user_repository.identity_provider_is_active(APPLE_PROVIDER_CODE):
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)

        claims = await self._verifier.verify(command.id_token, audiences=client_ids)
        if not claims:
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)

        linked_user_id = await self._user_repository.get_user_id_by_identity_link(APPLE_PROVIDER_CODE, claims.subject)
        if linked_user_id:
            user = await self._user_repository.get_sensitive_by_id(linked_user_id)
            if not user or not _is_end_user_eligible(user):
                raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)
            end_user = await self._end_user_repository.get_by_auth_user_id(user.id)
            if not end_user:
                raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)
            return await self._member_login_service.complete_member_login(user=user, end_user_id=end_user.id, app_code=app_code)

        if not claims.email_verified or not claims.email:
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)
        email = claims.email.strip().lower()
        user = await self._user_repository.get_sensitive_by_email_without_profile(email)
        if user is None:
            return await self._provision_and_login(claims=claims, email=email, app_code=app_code)
        if not _is_end_user_eligible(user):
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)
        end_user = await self._end_user_repository.get_by_auth_user_id(user.id)
        if not end_user:
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)

        await self._user_repository.upsert_identity_link(user.id, APPLE_PROVIDER_CODE, claims.subject, additional_data={"email": claims.email})
        return await self._member_login_service.complete_member_login(user=user, end_user_id=end_user.id, app_code=app_code)

    async def _provision_and_login(self, *, claims: AppleIdentityClaims, email: str, app_code: str) -> MemberLoginResult:
        provisioned = await self._provisioning_service.provision(
            ProvisionIdentityCommand(email=email, password=None, create_end_user=True, locale_code=get_resolved_locale_code())
        )
        if provisioned.end_user_id is None:
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)
        user = await self._user_repository.get_sensitive_by_email_without_profile(email)
        if not user:
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)
        await self._user_repository.upsert_identity_link(user.id, APPLE_PROVIDER_CODE, claims.subject, additional_data={"email": claims.email})
        return await self._member_login_service.complete_member_login(user=user, end_user_id=provisioned.end_user_id, app_code=app_code)
