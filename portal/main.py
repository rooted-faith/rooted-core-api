"""
main application
"""

import secrets
from pathlib import Path

import sentry_sdk
from fastapi import Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sentry_sdk.integrations.asyncpg import AsyncPGIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from portal.apps import get_main_application
from portal.config import settings

__all__ = ["app"]

basic_security = HTTPBasic()
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def setup_tracing() -> None:
    """
    Setup Sentry tracing when configured.
    """
    if not settings.SENTRY_URL:
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_URL,
        integrations=[
            AsyncPGIntegration(),
            FastApiIntegration(),
            HttpxIntegration(),
            RedisIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
        environment=settings.ENV.upper(),
        enable_tracing=True,
    )


def _verify_docs_access(credentials: HTTPBasicCredentials) -> None:
    is_valid_username = secrets.compare_digest(credentials.username, settings.DOCS_BASIC_AUTH_USERNAME)
    is_valid_password = secrets.compare_digest(credentials.password, settings.DOCS_BASIC_AUTH_PASSWORD)
    if is_valid_username and is_valid_password:
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid basic auth credentials.", headers={"WWW-Authenticate": "Basic"})


def _render_docs_scope_html() -> str:
    template_path = TEMPLATES_DIR / "root.html"
    html_content = template_path.read_text(encoding="utf-8")
    return html_content.replace("{{APP_NAME}}", settings.APP_NAME)


setup_tracing()
app = get_main_application()


@app.get("/")
async def root(credentials: HTTPBasicCredentials = Depends(basic_security)):
    """Root path serves scope selector after basic auth"""
    _verify_docs_access(credentials)
    return HTMLResponse(content=_render_docs_scope_html())
