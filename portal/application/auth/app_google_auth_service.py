"""
End-user Google ID-token sign-in application service (ADR 0008).

Parallel to AdminGoogleAuthService, with one deliberate difference: a first
success that matches nothing may create the Auth credential + End user +
Preferences, whereas the Admin flow only ever binds to an existing credential.
"""

from portal.application.app.commands import ProvisionIdentityCommand
from portal.application.app.end_user_provisioning_service import EndUserProvisioningService
from portal.application.auth.commands import AppGoogleLoginCommand
from portal.application.auth.member_login_service import MemberLoginService
from portal.application.auth.results import MemberLoginResult, UserSensitive
from portal.config import settings
from portal.domain.app.ports import EndUserRepositoryPort
from portal.domain.auth.entities import GoogleIdentityClaims
from portal.domain.auth.ports import GoogleIdTokenVerifierPort, UserRepositoryPort
from portal.exceptions.responses import UnauthorizedException
from portal.libs.contexts.request_context import get_resolved_locale_code
from portal.libs.tracing.distributed_trace import distributed_trace

GOOGLE_PROVIDER_CODE = "google"
GENERIC_FAILURE_DETAIL = "Google sign-in failed"


def _is_end_user_eligible(user: UserSensitive) -> bool:
    return user.verified and user.is_active


class AppGoogleAuthService:
    """Resolve a verified Google ID token to an End user, provisioning one on first success."""

    def __init__(
        self,
        provisioning_service: EndUserProvisioningService,
        user_repository: UserRepositoryPort,
        end_user_repository: EndUserRepositoryPort,
        google_id_token_verifier: GoogleIdTokenVerifierPort,
        member_login_service: MemberLoginService,
    ):
        self._provisioning_service = provisioning_service
        self._user_repository = user_repository
        self._end_user_repository = end_user_repository
        self._verifier = google_id_token_verifier
        self._member_login_service = member_login_service

    @distributed_trace()
    async def login_with_google(self, command: AppGoogleLoginCommand) -> MemberLoginResult:
        """
        Resolution order: existing Identity link by `sub`, else verified email
        (case-insensitive) match to an existing End user's Auth credential, else
        provision a brand-new credential + End user + Preferences. Every rejection
        path raises the same generic failure — no account enumeration.
        """
        app_code = self._member_login_service.resolve_app_code()

        client_ids = settings.google_app_client_ids
        if not client_ids or not await self._user_repository.identity_provider_is_active(GOOGLE_PROVIDER_CODE):
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)

        claims = await self._verifier.verify(command.id_token, audiences=client_ids)
        if not claims or not claims.email_verified or not claims.email:
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)

        linked_user_id = await self._user_repository.get_user_id_by_identity_link(GOOGLE_PROVIDER_CODE, claims.subject)
        if linked_user_id:
            user = await self._user_repository.get_sensitive_by_id(linked_user_id)
            if not user or not _is_end_user_eligible(user):
                raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)
            end_user = await self._end_user_repository.get_by_auth_user_id(user.id)
            if not end_user:
                raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)
            return await self._member_login_service.complete_member_login(user=user, end_user_id=end_user.id, app_code=app_code)

        email = claims.email.strip().lower()
        # An End user credential has no AuthUserProfile row, so the profile-joining
        # lookup the Admin flow uses would never match one.
        user = await self._user_repository.get_sensitive_by_email_without_profile(email)
        if user is None:
            return await self._provision_and_login(claims=claims, email=email, app_code=app_code)

        if not _is_end_user_eligible(user):
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)
        # An admin-only credential has no End user row; refuse it here exactly as OTP verify does,
        # rather than silently attaching product identity to a console account.
        end_user = await self._end_user_repository.get_by_auth_user_id(user.id)
        if not end_user:
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)

        await self._user_repository.upsert_identity_link(user.id, GOOGLE_PROVIDER_CODE, claims.subject, additional_data={"email": claims.email})
        return await self._member_login_service.complete_member_login(user=user, end_user_id=end_user.id, app_code=app_code)

    async def _provision_and_login(self, *, claims: GoogleIdentityClaims, email: str, app_code: str) -> MemberLoginResult:
        provisioned = await self._provisioning_service.provision(
            ProvisionIdentityCommand(email=email, password=None, create_end_user=True, locale_code=get_resolved_locale_code())
        )
        if provisioned.end_user_id is None:
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)

        user = await self._user_repository.get_sensitive_by_email_without_profile(email)
        if not user:
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)

        await self._user_repository.upsert_identity_link(user.id, GOOGLE_PROVIDER_CODE, claims.subject, additional_data={"email": claims.email})
        return await self._member_login_service.complete_member_login(user=user, end_user_id=provisioned.end_user_id, app_code=app_code)
