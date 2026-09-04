"""
Provision End user identity separate from auth credentials (ADR 0004).
"""

import uuid

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

    @distributed_trace()
    async def provision(self, command: ProvisionIdentityCommand) -> ProvisionIdentityResult:
        if not self._password_provider.validate_password(command.password):
            raise BadRequestException(detail="Password is not valid")
        if command.create_end_user and not command.display_name:
            raise BadRequestException(detail="display_name is required when creating an End user")

        auth_user_id = uuid.uuid4()
        password_hash = self._password_provider.hash_password(command.password)
        # Password signup verifies the credential for app use; email magic-link
        # verification is a separate channel (ADR 0003). Admin-only rows stay unverified.
        await self._user_repository.create_credential(
            auth_user_id=auth_user_id,
            email=command.email.strip().lower(),
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
                display_name=command.display_name,
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
