"""
Admin Google ID-token sign-in application service (ADR 0006).
"""

from portal.application.auth.commands import AdminGoogleLoginCommand
from portal.application.auth.login_service import LoginService
from portal.application.auth.results import LoginResult, UserSensitive
from portal.config import settings
from portal.domain.auth.ports import GoogleIdTokenVerifierPort, UserRepositoryPort
from portal.exceptions.responses import UnauthorizedException
from portal.libs.tracing.distributed_trace import distributed_trace

GOOGLE_PROVIDER_CODE = "google"
GENERIC_FAILURE_DETAIL = "Google sign-in failed"


def _is_admin_eligible(user: UserSensitive) -> bool:
    return user.is_admin and user.verified and user.is_active


class AdminGoogleAuthService:
    """Resolve a verified Google ID token to an existing admin-eligible Auth credential and issue admin tokens."""

    def __init__(self, user_repository: UserRepositoryPort, google_id_token_verifier: GoogleIdTokenVerifierPort, login_service: LoginService):
        self._repository = user_repository
        self._verifier = google_id_token_verifier
        self._login_service = login_service

    @distributed_trace()
    async def login_with_google(self, command: AdminGoogleLoginCommand) -> LoginResult:
        """
        Resolution order (ADR 0006): existing Identity link by `sub`, else verified email
        (case-insensitive) match to an admin-eligible Auth credential, then upsert the link.
        Every rejection path raises the same generic failure — no account enumeration.
        """
        client_ids = settings.google_admin_client_ids
        if not client_ids or not await self._repository.identity_provider_is_active(GOOGLE_PROVIDER_CODE):
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)

        claims = await self._verifier.verify(command.id_token, audiences=client_ids)
        if not claims or not claims.email_verified or not claims.email:
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)

        linked_user_id = await self._repository.get_user_id_by_identity_link(GOOGLE_PROVIDER_CODE, claims.subject)
        if linked_user_id:
            user = await self._repository.get_sensitive_by_id(linked_user_id)
            if not user or not _is_admin_eligible(user):
                raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)
            return await self._login_service.complete_admin_login(user)

        user = await self._repository.get_sensitive_by_email(claims.email)
        if not user or not _is_admin_eligible(user):
            raise UnauthorizedException(detail=GENERIC_FAILURE_DETAIL)

        await self._repository.upsert_identity_link(user.id, GOOGLE_PROVIDER_CODE, claims.subject, additional_data={"email": claims.email})
        return await self._login_service.complete_admin_login(user)
