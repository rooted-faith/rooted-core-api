"""
Decide when a shared test passcode may replace an emailed OTP (ADR 0016).
"""

import asyncio
import re
from typing import Optional

from portal.config import settings
from portal.domain.auth.constants import OTP_TEST_ENVIRONMENTS, OTP_TEST_FIREBASE_PROJECT_ID, OTP_TEST_POLICY_REFRESH_SECONDS, OtpDeliveryMode
from portal.domain.auth.entities import OtpChallenge
from portal.domain.auth.otp_test_policy import OtpTestPolicy
from portal.domain.auth.ports import OtpTestPolicyPort, OtpTokenPort
from portal.libs.logger import logger
from portal.libs.tracing.distributed_trace import distributed_trace

_DEFAULT_TEST_PASSCODE = "123456"
_SIX_ASCII_DIGITS = re.compile(r"[0-9]{6}")
_NOTHING_OBSERVED = object()


class OtpTestPasscodeService:
    """
    Gate test passcodes on environment, Firebase project, remote flag, and allowlist.

    Must be shared process-wide: it remembers the last policy it observed so that a change
    withdraws outstanding challenges once, and a later re-enablement cannot revive them.
    """

    def __init__(self, otp_test_policy: OtpTestPolicyPort, otp_token_store: OtpTokenPort):
        self._otp_test_policy = otp_test_policy
        self._otp_token_store = otp_token_store
        self._lock = asyncio.Lock()
        self._last_observed: object = _NOTHING_OBSERVED
        self._withdraw_all = False

    @distributed_trace()
    async def passcode_for(self, email: str) -> Optional[str]:
        """Return the current test passcode when this normalized email may use it, else None (email mode)."""
        if not self._permits(await self._observe_policy(), email):
            return None
        if not settings.OTP_FIXED_CODE:
            logger.warning("OTP_FIXED_CODE is not set; using the default test passcode")
        elif not _SIX_ASCII_DIGITS.fullmatch(settings.OTP_FIXED_CODE):
            logger.warning("OTP_FIXED_CODE is not six ASCII digits; using the default test passcode")
        return self._current_passcode()

    @distributed_trace()
    async def honors(self, email: str, challenge: OtpChallenge) -> bool:
        """Whether an outstanding fixed challenge may still be redeemed under the policy observed right now."""
        return self._is_redeemable(await self._observe_policy(), email, challenge)

    async def watch(self, interval_seconds: float = OTP_TEST_POLICY_REFRESH_SECONDS) -> None:
        """Keep observing the policy without OTP traffic, so a withdrawal is noticed even if it is later reverted."""
        while self._is_test_environment():
            try:
                await self._observe_policy()
            except Exception as error:  # noqa: BLE001 - a storage outage must not end the watch
                logger.warning(f"Test passcode policy could not be applied: {type(error).__name__}")
            await asyncio.sleep(interval_seconds)

    async def _observe_policy(self) -> Optional[OtpTestPolicy]:
        if not self._is_test_environment():
            return None
        async with self._lock:
            policy = await self._otp_test_policy.current()
            if policy is self._last_observed and not self._withdraw_all:
                return policy
            # Stays set if this sweep fails, so the next one withdraws everything rather than losing this observation.
            withdraw_all, self._withdraw_all = self._withdraw_all, True
            for email, challenge in await self._otp_token_store.list_fixed():
                if withdraw_all or not self._is_redeemable(policy, email, challenge):
                    await self._otp_token_store.consume(email, challenge)
            self._withdraw_all = False
            self._last_observed = policy
            return policy

    @staticmethod
    def _is_test_environment() -> bool:
        return settings.explicit_env in OTP_TEST_ENVIRONMENTS

    @staticmethod
    def _permits(policy: Optional[OtpTestPolicy], email: str) -> bool:
        return policy is not None and policy.project_id == OTP_TEST_FIREBASE_PROJECT_ID and policy.permits(email)

    @classmethod
    def _is_redeemable(cls, policy: Optional[OtpTestPolicy], email: str, challenge: OtpChallenge) -> bool:
        return cls._permits(policy, email) and challenge == OtpChallenge.of(email, cls._current_passcode(), OtpDeliveryMode.FIXED)

    @staticmethod
    def _current_passcode() -> str:
        return settings.OTP_FIXED_CODE if _SIX_ASCII_DIGITS.fullmatch(settings.OTP_FIXED_CODE) else _DEFAULT_TEST_PASSCODE
