"""
Read the test passcode policy from Firebase Remote Config's server template (ADR 0016).
"""

import asyncio
import importlib
import json
import logging
import time
from typing import Any, Callable, Optional

import firebase_admin
from firebase_admin import credentials

from portal.domain.auth.constants import OTP_TEST_FIREBASE_PROJECT_ID, OTP_TEST_POLICY_REFRESH_SECONDS
from portal.domain.auth.otp_test_policy import OtpTestPolicy
from portal.libs.logger import logger

FLAG_PARAMETER = "otp_test_mode_enabled"
ALLOWLIST_PARAMETER = "otp_test_allowlist"
_DEFAULTS = {FLAG_PARAMETER: "false", ALLOWLIST_PARAMETER: "[]"}

_RETRY_AFTER_FAILURE_SECONDS = 10.0
_FIREBASE_APP_NAME = "rooted-otp-test-policy"


def _remote_config() -> Any:
    """Import the SDK module without letting its module-level logging.basicConfig reconfigure the root logger."""
    root_logger = logging.getLogger()
    guard = logging.NullHandler()
    root_logger.addHandler(guard)
    try:
        return importlib.import_module("firebase_admin.remote_config")
    finally:
        root_logger.removeHandler(guard)


class FirebaseOtpTestPolicy:
    """
    Implements OtpTestPolicyPort with a snapshot that is refreshed once it is 60 seconds old.

    Uses its own named Firebase App pinned to the allowed project, so it neither depends on nor
    affects the default App that push delivery uses. Every problem resolves to "no policy".
    """

    def __init__(self, credentials_dict: Optional[dict], clock: Callable[[], float] = time.monotonic, load_timeout_seconds: float = 5.0):
        self._credentials_dict = credentials_dict
        self._clock = clock
        self._load_timeout_seconds = load_timeout_seconds
        self._lock = asyncio.Lock()
        self._policy: Optional[OtpTestPolicy] = None
        self._expires_at: Optional[float] = None
        self._retry_at: Optional[float] = None

    async def current(self) -> Optional[OtpTestPolicy]:
        async with self._lock:
            now = self._clock()
            if self._expires_at is not None and now < self._expires_at:
                return self._policy
            self._policy = None
            self._expires_at = None
            if self._retry_at is not None and now < self._retry_at:
                return None
            try:
                policy = await asyncio.wait_for(self._load(), timeout=self._load_timeout_seconds)
            except Exception as error:  # noqa: BLE001 - any SDK, credential, or template failure means email mode
                logger.warning(f"Test passcode policy could not be loaded: {type(error).__name__}")
                self._retry_at = self._clock() + _RETRY_AFTER_FAILURE_SECONDS
                return None
            self._policy = policy
            self._expires_at = now + OTP_TEST_POLICY_REFRESH_SECONDS
            self._retry_at = None
            return policy

    async def _load(self) -> Optional[OtpTestPolicy]:
        app = self._firebase_app()
        if app is None:
            return None
        template = await _remote_config().get_server_template(app=app, default_config=_DEFAULTS)
        config = template.evaluate()
        return self._validate(app.project_id, config.get_string(FLAG_PARAMETER), config.get_string(ALLOWLIST_PARAMETER))

    def _firebase_app(self) -> Optional[firebase_admin.App]:
        if not self._credentials_dict:
            logger.warning("Firebase credentials are not configured; test passcodes are unavailable")
            return None
        credential = credentials.Certificate(self._credentials_dict)
        if credential.project_id != OTP_TEST_FIREBASE_PROJECT_ID:
            logger.warning("Firebase credentials belong to a project without test passcodes")
            return None
        try:
            app = firebase_admin.get_app(_FIREBASE_APP_NAME)
        except ValueError:
            options = {"projectId": credential.project_id, "httpTimeout": self._load_timeout_seconds}
            app = firebase_admin.initialize_app(credential, options, name=_FIREBASE_APP_NAME)
        return app

    @staticmethod
    def _validate(project_id: str, flag: str, allowlist: str) -> Optional[OtpTestPolicy]:
        if flag not in ("true", "false"):
            logger.warning(f"{FLAG_PARAMETER} is not a boolean; test passcodes are unavailable")
            return None
        try:
            rules = json.loads(allowlist)
        except ValueError, RecursionError:
            rules = None
        if not isinstance(rules, list) or not all(isinstance(rule, str) for rule in rules):
            logger.warning(f"{ALLOWLIST_PARAMETER} is not a JSON array of strings; test passcodes are unavailable")
            return None
        policy = OtpTestPolicy(project_id=project_id, test_mode_enabled=flag == "true", allowlist=tuple(rules))
        if not policy.allowlist_is_valid:
            logger.warning(f"{ALLOWLIST_PARAMETER} contains an unsupported rule; test passcodes are unavailable")
            return None
        return policy
