"""
System setting domain entities.
"""

from typing import Any

from pydantic import Field

from portal.domain.common.mixins import AuditModel, DeleteModel, RemarkModel, UUIDModel


class Setting(UUIDModel, AuditModel, DeleteModel, RemarkModel):
    """System setting row."""

    namespace: str = Field(...)
    setting_key: str = Field(...)
    value_type: str = Field(...)
    value: Any = Field(...)
    is_built_in: bool = Field(default=False)
    is_active: bool = Field(default=True)
