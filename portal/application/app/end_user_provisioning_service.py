"""
Provision End user identity separate from auth credentials (ADR 0004).
"""

import uuid
from typing import Optional

from portal.application.app.commands import ProvisionIdentityCommand
from portal.application.app.results import ProvisionIdentityResult
from portal.domain.app.entities import UserPreferences
from portal.domain.app.ports import EndUserRepositoryPort, PreferencesRepositoryPort
from portal.domain.auth.ports import UserRepositoryPort
from portal.exceptions.responses import BadRequestException
from portal.libs.tracing.distributed_trace import distributed_trace
from portal.providers.password_provider import PasswordProvider


class EndUserProvisioningService:
    """
    App signup creates auth.user + app.user + Preferences together.
    Admin-only provisioning creates the credential without app.user.
    Password may be omitted for passwordless (magic-link) End users.
    """

    def __init__(
        self,
        user_repository: UserRepositoryPort,
        end_user_repository: EndUserRepositoryPort,
        preferences_repository: PreferencesRepositoryPort,
        password_provider: PasswordProvider,
    ):
        self._user_repository = user_repository
        self._end_user_repository = end_user_repository
        self._preferences_repository = preferences_repository
        self._password_provider = password_provider

    @staticmethod
    def _default_display_name(email: str, display_name: Optional[str]) -> str:
        if display_name:
            return display_name
        local_part = email.strip().split("@", 1)[0]
        return local_part or email

    @distributed_trace()
    async def provision(self, command: ProvisionIdentityCommand) -> ProvisionIdentityResult:
        password_hash: Optional[str] = None
        if command.password is not None:
            if not self._password_provider.validate_password(command.password):
                raise BadRequestException(detail="Password is not valid")
            password_hash = self._password_provider.hash_password(command.password)
        elif not command.create_end_user:
            raise BadRequestException(detail="Password is required for admin credentials")

        email = command.email.strip().lower()
        display_name = self._default_display_name(email, command.display_name)

        auth_user_id = uuid.uuid4()
        # Magic-link verify and password signup both mark verified for app use;
        # admin-only rows stay unverified until an admin path confirms them.
        await self._user_repository.create_credential(
            auth_user_id=auth_user_id,
            email=email,
            password_hash=password_hash,
            is_admin=command.is_admin,
            is_superuser=command.is_superuser,
            verified=command.create_end_user,
        )

        if not command.create_end_user:
            return ProvisionIdentityResult(auth_user_id=auth_user_id, end_user_id=None)

        end_user_id = uuid.uuid4()
        await self._end_user_repository.create_end_user(end_user_id=end_user_id, auth_user_id=auth_user_id)
        await self._preferences_repository.create_preferences(
            UserPreferences(
                id=uuid.uuid4(),
                user_id=end_user_id,
                display_name=display_name,
                locale=command.locale,
                theme=command.theme,
                font_scale=command.font_scale,
                bible_version=command.bible_version,
                stage=command.stage,
                reminder_time=command.reminder_time,
                reminder_enabled=command.reminder_enabled,
            )
        )
        return ProvisionIdentityResult(auth_user_id=auth_user_id, end_user_id=end_user_id)
