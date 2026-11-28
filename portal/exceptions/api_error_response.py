"""
Shared JSON envelope for ApiBaseException, used by the root exception handler and by middleware
that rejects a request before routing (middleware errors never reach exception handlers).
"""

from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse

from portal.config import settings
from portal.exceptions.responses import ApiBaseException


def api_exception_response(request: Request, exc: ApiBaseException) -> JSONResponse:
    content = defaultdict()
    content["detail"] = exc.detail
    if exc.error_code:
        content["error_code"] = exc.error_code
    if exc.context:
        content["context"] = exc.context
    if settings.is_dev:
        content["debug_detail"] = exc.debug_detail
        content["url"] = str(request.url)
    return JSONResponse(content=content, status_code=exc.status_code, headers=exc.headers)
