"""
App product identity (End user) and Preferences.

Future product FKs (journal, groups, walk days, …) MUST reference app.user.id,
never auth.user.id. auth.user remains the shared credential row only.
"""

from portal.domain.app.entities import EndUser, UserPreferences

__all__ = ["EndUser", "UserPreferences"]
