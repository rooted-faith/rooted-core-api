"""
App support policy serializers (camelCase JSON via serialization_alias).
"""

from typing import Literal

from pydantic import BaseModel, Field


class AppSupportPolicyResponse(BaseModel):
    """Effective minimum supported App build for one platform in this backend environment."""

    environment: str = Field(..., description="Backend environment resolved by the server (dev, stg, prod)")
    platform: Literal["ios", "android"] = Field(...)
    minimum_build: int = Field(..., serialization_alias="minimumBuild", description="Builds below this number must update")
    latest_build: int | None = Field(default=None, serialization_alias="latestBuild", description="Newest available build; informational only")
    update_url: str | None = Field(default=None, serialization_alias="updateUrl", description="https destination for the replacement build")
    update_instructions: str | None = Field(default=None, serialization_alias="updateInstructions", description="Manual update steps when no URL applies")
    enforcement: Literal["compatible", "enforced"] = Field(..., description="Whether the request gate is rejecting unsupported builds")
