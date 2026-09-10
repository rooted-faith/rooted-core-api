"""
Map End user application results to API serializers.
"""

from portal.application.app.commands import UpdatePreferencesCommand
from portal.application.app.results import PreferencesResult
from portal.serializers.apis.v1.user import MemberPreferences, UpdateMemberPreferences


def update_preferences_to_command(serializer: UpdateMemberPreferences) -> UpdatePreferencesCommand:
    return UpdatePreferencesCommand.model_validate(serializer.model_dump(exclude_unset=True))


def preferences_result_to_api(result: PreferencesResult) -> MemberPreferences:
    return MemberPreferences.model_validate(result, from_attributes=True)
