"""
App (End user) password register / login use cases.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from portal.application.app.commands import ProvisionIdentityCommand
from portal.application.app.end_user_provisioning_service import EndUserProvisioningService
from portal.application.auth.commands import AppLoginCommand, AppRegisterCommand
from portal.application.auth.mappers import normalize_user_for_token
from portal.application.auth.member_web_app_resolver import resolve_request_app_code
from portal.application.auth.results import MemberLoginResult, MemberProfileResult, TokenResult, UserSensitive
from portal.config import settings
from portal.domain.app.ports import EndUserRepositoryPort, PreferencesRepositoryPort
from portal.domain.auth.member_web_app import MemberWebAppRegistry
from portal.domain.auth.ports import UserRepositoryPort
from portal.exceptions.responses import UnauthorizedException
from portal.libs.consts.enums import AccessTokenAudType
from portal.libs.tracing.distributed_trace import distributed_trace
from portal.providers.jwt_provider import JWTProvider
from portal.providers.member_refresh_app_binding_provider import MemberRefreshAppBindingProvider
from portal.providers.password_provider import PasswordProvider
from portal.providers.refresh_token_provider import RefreshTokenProvider


class AppAuthService:
    """
    Password register/login for End users.

    Issues member JWTs via shared providers; product identity in the response
    is app.user.id (End user), not auth.user.id.
    """

    def __init__(
        self,
        provisioning_service: EndUserProvisioningService,
        user_repository: UserRepositoryPort,
        end_user_repository: EndUserRepositoryPort,
        preferences_repository: PreferencesRepositoryPort,
        password_provider: PasswordProvider,
        jwt_provider: JWTProvider,
        refresh_token_provider: RefreshTokenProvider,
        member_refresh_app_binding_provider: Optional[MemberRefreshAppBindingProvider],
        member_web_app_registry: MemberWebAppRegistry,
    ):
        self._provisioning_service = provisioning_service
        self._user_repository = user_repository
        self._end_user_repository = end_user_repository
        self._preferences_repository = preferences_repository
        self._password_provider = password_provider
        self._jwt_provider = jwt_provider
        self._refresh_token_provider = refresh_token_provider
        self._member_refresh_app_binding_provider = member_refresh_app_binding_provider
        self._member_web_app_registry = member_web_app_registry

    def _resolve_app_code(self) -> str:
        app_code = resolve_request_app_code(self._member_web_app_registry, required=True)
        assert app_code is not None
        return app_code

    @distributed_trace()
    async def register(self, command: AppRegisterCommand) -> MemberLoginResult:
        app_code = self._resolve_app_code()
        provisioned = await self._provisioning_service.provision(
            ProvisionIdentityCommand(email=command.email, password=command.password, display_name=command.display_name, create_end_user=True)
        )
        if provisioned.end_user_id is None:
            raise UnauthorizedException(detail="End user was not provisioned")

        user = await self._user_repository.get_sensitive_by_email_without_profile(command.email.strip().lower())
        if not user:
            raise UnauthorizedException(detail="User not found after register")

        preferences = await self._preferences_repository.get_by_user_id(provisioned.end_user_id)
        preferred_name = preferences.display_name if preferences else command.display_name
        return await self._issue_member_tokens(user=user, app_code=app_code, end_user_id=provisioned.end_user_id, preferred_name=preferred_name)

    @distributed_trace()
    async def login(self, command: AppLoginCommand) -> MemberLoginResult:
        app_code = self._resolve_app_code()
        email = command.email.strip().lower()
        user = await self._user_repository.get_sensitive_by_email_without_profile(email)
        if not user or not user.password_hash:
            raise UnauthorizedException(detail="Invalid email or password")
        if not self._password_provider.verify_password(command.password, user.password_hash):
            raise UnauthorizedException(detail="Invalid email or password")
        if not user.verified or not user.is_active:
            raise UnauthorizedException(detail="User is not allowed to access the app")

        end_user = await self._end_user_repository.get_by_auth_user_id(user.id)
        if not end_user:
            raise UnauthorizedException(detail="Invalid email or password")

        preferences = await self._preferences_repository.get_by_user_id(end_user.id)
        preferred_name = preferences.display_name if preferences else None
        return await self._issue_member_tokens(user=user, app_code=app_code, end_user_id=end_user.id, preferred_name=preferred_name)

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
