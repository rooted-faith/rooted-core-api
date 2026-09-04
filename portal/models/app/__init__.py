"""
App schema ORM: End user identity and Preferences (ADR 0004).

Convention: future product foreign keys MUST target app.user.id (End user),
never auth.user.id. auth.user is the shared credential only; auth.user_profile
stays Admin-oriented and is not Rooted Preferences.
"""

from .user import AppUser, AppUserPreferences

__all__ = ["AppUser", "AppUserPreferences"]
