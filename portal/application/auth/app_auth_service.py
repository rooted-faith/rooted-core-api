"""
App (End user) passwordless email-OTP auth use cases (ADR 0008).
"""

import hashlib
import secrets

from portal.application.app.commands import ProvisionIdentityCommand
from portal.application.app.end_user_provisioning_service import EndUserProvisioningService
from portal.application.auth.commands import AppOtpRequestCommand, AppOtpVerifyCommand
from portal.application.auth.member_login_service import MemberLoginService
from portal.application.auth.results import MemberLoginResult, OtpRequestResult
from portal.config import settings
from portal.domain.app.ports import EndUserRepositoryPort
from portal.domain.auth.ports import OtpMailerPort, OtpTokenPort, UserRepositoryPort
from portal.exceptions.responses import TooManyRequestsException, UnauthorizedException
from portal.libs.contexts.request_context import get_resolved_locale_code
from portal.libs.tracing.distributed_trace import distributed_trace

_OTP_ACK_MESSAGE = "If the email is valid, a passcode has been sent"
_OTP_FAILURE_DETAIL = "Invalid or expired passcode"
_OTP_THROTTLED_DETAIL = "Too many passcode requests, please try again later"
_OTP_CODE_DIGITS = 6


class AppAuthService:
    """
    Email one-time passcode request/verify for End users.

    Issues member JWTs via shared providers; product identity in the response
    is app.user.id (End user), not auth.user.id.
    """

    def __init__(
        self,
        provisioning_service: EndUserProvisioningService,
        user_repository: UserRepositoryPort,
        end_user_repository: EndUserRepositoryPort,
        otp_token_store: OtpTokenPort,
        otp_mailer: OtpMailerPort,
        member_login_service: MemberLoginService,
    ):
        self._provisioning_service = provisioning_service
        self._user_repository = user_repository
        self._end_user_repository = end_user_repository
        self._otp_token_store = otp_token_store
        self._otp_mailer = otp_mailer
        self._member_login_service = member_login_service

    @staticmethod
    def _generate_code() -> str:
        return f"{secrets.randbelow(10**_OTP_CODE_DIGITS):0{_OTP_CODE_DIGITS}d}"

    @staticmethod
    def _hash_code(email: str, code: str) -> str:
        return hashlib.sha256(f"{email}:{code}".encode("utf-8")).hexdigest()

    @distributed_trace()
    async def request_otp(self, command: AppOtpRequestCommand) -> OtpRequestResult:
        """
        Always answer with the same acknowledgement, whether or not the email has an
        account. The passcode email's language is the locale CoreRequestMiddleware
        already resolved from this request's Accept-Language (ADR 0009).
        """
        email = command.email.strip().lower()
        allowed = await self._otp_token_store.allow_request(
            email, max_requests=settings.OTP_REQUEST_MAX_PER_WINDOW, window_seconds=settings.OTP_REQUEST_WINDOW_SECONDS
        )
        if not allowed:
            raise TooManyRequestsException(detail=_OTP_THROTTLED_DETAIL)

        code = self._generate_code()
        await self._otp_token_store.store(email, self._hash_code(email, code), settings.OTP_CODE_EXPIRE_MINUTES * 60)
        await self._otp_mailer.send_otp(email, code, locale=get_resolved_locale_code())
        return OtpRequestResult(message=_OTP_ACK_MESSAGE)

    @distributed_trace()
    async def verify_otp(self, command: AppOtpVerifyCommand) -> MemberLoginResult:
        """
        Redeem a live passcode: sign in an existing End user, or provision credential +
        End user + Preferences on first use. Every rejection path raises the same generic
        failure — no account enumeration.
        """
        app_code = self._member_login_service.resolve_app_code()
        email = command.email.strip().lower()
        if not await self._otp_token_store.consume(email, self._hash_code(email, command.code)):
            raise UnauthorizedException(detail=_OTP_FAILURE_DETAIL)

        user = await self._user_repository.get_sensitive_by_email_without_profile(email)
        if user is None:
            provisioned = await self._provisioning_service.provision(
                ProvisionIdentityCommand(email=email, password=None, create_end_user=True, locale_code=get_resolved_locale_code())
            )
            if provisioned.end_user_id is None:
                raise UnauthorizedException(detail=_OTP_FAILURE_DETAIL)
            user = await self._user_repository.get_sensitive_by_email_without_profile(email)
            if not user:
                raise UnauthorizedException(detail=_OTP_FAILURE_DETAIL)
            end_user_id = provisioned.end_user_id
        else:
            if not user.verified or not user.is_active:
                raise UnauthorizedException(detail=_OTP_FAILURE_DETAIL)
            end_user = await self._end_user_repository.get_by_auth_user_id(user.id)
            if not end_user:
                raise UnauthorizedException(detail=_OTP_FAILURE_DETAIL)
            end_user_id = end_user.id

        return await self._member_login_service.complete_member_login(user=user, end_user_id=end_user_id, app_code=app_code)
