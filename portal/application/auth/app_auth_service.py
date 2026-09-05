"""
App (End user) passwordless magic-link auth use cases.
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from portal.application.app.commands import ProvisionIdentityCommand
from portal.application.app.end_user_provisioning_service import EndUserProvisioningService
from portal.application.auth.commands import AppMagicLinkRequestCommand, AppMagicLinkVerifyCommand
from portal.application.auth.mappers import normalize_user_for_token
from portal.application.auth.member_web_app_resolver import resolve_request_app_code
from portal.application.auth.results import MagicLinkRequestResult, MemberLoginResult, MemberProfileResult, TokenResult, UserSensitive
from portal.config import settings
from portal.domain.app.ports import EndUserRepositoryPort, PreferencesRepositoryPort
from portal.domain.auth.member_web_app import MemberWebAppRegistry
from portal.domain.auth.ports import MagicLinkMailerPort, MagicLinkTokenPort, UserRepositoryPort
from portal.exceptions.responses import UnauthorizedException
from portal.libs.consts.enums import AccessTokenAudType
from portal.libs.tracing.distributed_trace import distributed_trace
from portal.providers.jwt_provider import JWTProvider
from portal.providers.member_refresh_app_binding_provider import MemberRefreshAppBindingProvider
from portal.providers.refresh_token_provider import RefreshTokenProvider

_MAGIC_LINK_ACK_MESSAGE = "If the email is valid, a magic link has been sent"


class AppAuthService:
    """
    Passwordless magic-link request/verify for End users.

    Issues member JWTs via shared providers; product identity in the response
    is app.user.id (End user), not auth.user.id.
    """

    def __init__(
        self,
        provisioning_service: EndUserProvisioningService,
        user_repository: UserRepositoryPort,
        end_user_repository: EndUserRepositoryPort,
        preferences_repository: PreferencesRepositoryPort,
        magic_link_token_store: MagicLinkTokenPort,
        magic_link_mailer: MagicLinkMailerPort,
        jwt_provider: JWTProvider,
        refresh_token_provider: RefreshTokenProvider,
        member_refresh_app_binding_provider: Optional[MemberRefreshAppBindingProvider],
        member_web_app_registry: MemberWebAppRegistry,
    ):
        self._provisioning_service = provisioning_service
        self._user_repository = user_repository
        self._end_user_repository = end_user_repository
        self._preferences_repository = preferences_repository
        self._magic_link_token_store = magic_link_token_store
        self._magic_link_mailer = magic_link_mailer
        self._jwt_provider = jwt_provider
        self._refresh_token_provider = refresh_token_provider
        self._member_refresh_app_binding_provider = member_refresh_app_binding_provider
        self._member_web_app_registry = member_web_app_registry

    def _resolve_app_code(self) -> str:
        app_code = resolve_request_app_code(self._member_web_app_registry, required=True)
        assert app_code is not None
        return app_code

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @distributed_trace()
    async def request_magic_link(self, command: AppMagicLinkRequestCommand) -> MagicLinkRequestResult:
        email = command.email.strip().lower()
        token = secrets.token_urlsafe(32)
        ttl_seconds = settings.MAGIC_LINK_TOKEN_EXPIRE_MINUTES * 60
        await self._magic_link_token_store.store(email, self._hash_token(token), ttl_seconds)
        await self._magic_link_mailer.send_magic_link(email, token)
        return MagicLinkRequestResult(message=_MAGIC_LINK_ACK_MESSAGE)

    @distributed_trace()
    async def verify_magic_link(self, command: AppMagicLinkVerifyCommand) -> MemberLoginResult:
        app_code = self._resolve_app_code()
        email = command.email.strip().lower()
        token_hash = self._hash_token(command.token)
        if not await self._magic_link_token_store.consume(email, token_hash):
            raise UnauthorizedException(detail="Invalid or expired magic link")

        user = await self._user_repository.get_sensitive_by_email_without_profile(email)
        if user is None:
            provisioned = await self._provisioning_service.provision(ProvisionIdentityCommand(email=email, password=None, create_end_user=True))
            if provisioned.end_user_id is None:
                raise UnauthorizedException(detail="End user was not provisioned")
            user = await self._user_repository.get_sensitive_by_email_without_profile(email)
            if not user:
                raise UnauthorizedException(detail="User not found after magic-link verify")
            end_user_id = provisioned.end_user_id
        else:
            if not user.verified or not user.is_active:
                raise UnauthorizedException(detail="User is not allowed to access the app")
            end_user = await self._end_user_repository.get_by_auth_user_id(user.id)
            if not end_user:
                raise UnauthorizedException(detail="Invalid or expired magic link")
            end_user_id = end_user.id

        preferences = await self._preferences_repository.get_by_user_id(end_user_id)
        preferred_name = preferences.display_name if preferences else None
        return await self._issue_member_tokens(user=user, app_code=app_code, end_user_id=end_user_id, preferred_name=preferred_name)

    async def _issue_member_tokens(self, *, user: UserSensitive, app_code: str, end_user_id: UUID, preferred_name: Optional[str]) -> MemberLoginResult:
        token_user = normalize_user_for_token(user)
        if preferred_name:
            token_user = token_user.model_copy(update={"preferred_name": preferred_name, "first_name": preferred_name})

        family_id = uuid4()
        device_id = uuid4()
        access_token = self._jwt_provider.create_access_token(user=token_user, family_id=family_id, aud_type=AccessTokenAudType.USER, azp=app_code)
        refresh_token = await self._refresh_token_provider.issue(user_id=user.id, device_id=device_id, family_id=family_id)
        if self._member_refresh_app_binding_provider:
            await self._member_refresh_app_binding_provider.bind(family_id, app_code)

        now = datetime.now(timezone.utc)
        await self._user_repository.update_last_login_at(user_id=user.id, last_login_at=now)

        expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        token = TokenResult(access_token=access_token, refresh_token=refresh_token, token_type="bearer", expires_in=expires_in)
        member = MemberProfileResult(
            id=end_user_id,
            email=user.email or "",
            first_name=preferred_name or "",
            last_name="",
            preferred_name=preferred_name,
            roles=[],
            preferred_locale_id=user.preferred_locale_id,
            last_login_at=user.last_login_at,
        )
        return MemberLoginResult(member=member, token=token)
