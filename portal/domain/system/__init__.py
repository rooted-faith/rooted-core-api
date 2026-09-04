"""
System settings domain package.
"""

from portal.domain.system.constants import SettingValueType
from portal.domain.system.entities import Setting

__all__ = ["Setting", "SettingValueType"]
