"""
Shared member (End user) login completion — issue JWTs and build the member profile.

Mirrors LoginService.complete_admin_login for the app side: every End-user sign-in
path (email OTP, Google, …) funnels through here so token issuance stays in one place.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from portal.application.auth.mappers import normalize_user_for_token
from portal.application.auth.member_web_app_resolver import resolve_request_app_code
from portal.application.auth.results import MemberLoginResult, MemberProfileResult, TokenResult, UserSensitive
from portal.config import settings
from portal.domain.app.ports import PreferencesRepositoryPort
from portal.domain.auth.member_web_app import MemberWebAppRegistry
from portal.domain.auth.ports import UserRepositoryPort
from portal.libs.consts.enums import AccessTokenAudType
from portal.libs.tracing.distributed_trace import distributed_trace
from portal.providers.jwt_provider import JWTProvider
from portal.providers.member_refresh_app_binding_provider import MemberRefreshAppBindingProvider
from portal.providers.refresh_token_provider import RefreshTokenProvider


class MemberLoginService:
    """Issue member tokens for an already-resolved End user."""

    def __init__(
        self,
        user_repository: UserRepositoryPort,
        preferences_repository: PreferencesRepositoryPort,
        jwt_provider: JWTProvider,
        refresh_token_provider: RefreshTokenProvider,
        member_refresh_app_binding_provider: Optional[MemberRefreshAppBindingProvider],
        member_web_app_registry: MemberWebAppRegistry,
    ):
        self._user_repository = user_repository
        self._preferences_repository = preferences_repository
        self._jwt_provider = jwt_provider
        self._refresh_token_provider = refresh_token_provider
        self._member_refresh_app_binding_provider = member_refresh_app_binding_provider
        self._member_web_app_registry = member_web_app_registry

    def resolve_app_code(self) -> str:
        """Resolve the calling member web app from the request, raising when it is not allowed."""
        app_code = resolve_request_app_code(self._member_web_app_registry, required=True)
        assert app_code is not None
        return app_code

    @distributed_trace()
    async def complete_member_login(self, *, user: UserSensitive, end_user_id: UUID, app_code: str) -> MemberLoginResult:
        """
        Issue an access/refresh pair bound to the calling app and return the member
        profile. The profile id is app.user.id (End user), never auth.user.id.
        """
        preferences = await self._preferences_repository.get_by_user_id(end_user_id)
        preferred_name = preferences.display_name if preferences else None

        token_user = normalize_user_for_token(user)
        if preferred_name:
            token_user = token_user.model_copy(update={"preferred_name": preferred_name, "first_name": preferred_name})

        family_id = uuid4()
        device_id = uuid4()
        access_token = self._jwt_provider.create_access_token(user=token_user, family_id=family_id, aud_type=AccessTokenAudType.USER, azp=app_code)
        refresh_token = await self._refresh_token_provider.issue(user_id=user.id, device_id=device_id, family_id=family_id)
        if self._member_refresh_app_binding_provider:
            await self._member_refresh_app_binding_provider.bind(family_id, app_code)

        await self._user_repository.update_last_login_at(user_id=user.id, last_login_at=datetime.now(timezone.utc))

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
