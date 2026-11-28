"""
Top-level package for responses of exceptions.
"""

from .auth import *
from .base import *

__all__ = [
    # base
    "ApiBaseException",
    "BadRequestException",  # 400
    "ParamError",  # 400
    "NotFoundException",  # 404
    "ConflictErrorException",  # 409
    "EntityTooLargeException",  # 413
    "UpgradeRequiredException",  # 426
    "TooManyRequestsException",  # 429
    "NotImplementedException",  # 501
    "ServiceUnavailableException",  # 503
    # auth
    "InvalidTokenException",  # 401
    "UnauthorizedException",  # 401
    "RefreshTokenInvalidException",  # 401
    "ForbiddenException",  # 403
]
