"""
Firebase Cloud Messaging push gateway (ADR 0007 — direct FCM integration).
"""

import asyncio
import json
from typing import Optional

import firebase_admin
from firebase_admin import credentials, messaging

from portal.domain.push.constants import PushSendStatus
from portal.domain.push.entities import PushSendResult
from portal.libs.logger import logger

FCM_MULTICAST_TOKEN_LIMIT = 500


class FirebasePushGateway:
    """
    Implements PushGatewayPort via firebase_admin.messaging.send_each_for_multicast.

    Initializes the underlying Firebase App once, guarded against re-init
    (firebase_admin raises if initialize_app is called twice for the same
    default app, which would otherwise blow up on every DI construction).
    """

    def __init__(self, credentials_json: Optional[str]):
        self._app = None
        try:
            self._app = firebase_admin.get_app()
        except ValueError:
            if not credentials_json:
                logger.warning("FIREBASE_CREDENTIALS_JSON is not set; push notifications will fail until it is configured")
                return
            certificate = credentials.Certificate(json.loads(credentials_json))
            self._app = firebase_admin.initialize_app(certificate)

    async def send_multicast(self, *, tokens: list[str], title: str, body: str, data: Optional[dict]) -> list[PushSendResult]:
        if self._app is None:
            raise RuntimeError("Firebase push gateway is not configured (missing FIREBASE_CREDENTIALS_JSON)")

        string_data = {key: str(value) for key, value in (data or {}).items()}
        results: list[PushSendResult] = []
        for start in range(0, len(tokens), FCM_MULTICAST_TOKEN_LIMIT):
            batch = tokens[start : start + FCM_MULTICAST_TOKEN_LIMIT]
            message = messaging.MulticastMessage(notification=messaging.Notification(title=title, body=body), data=string_data, tokens=batch)
            try:
                response = await asyncio.to_thread(messaging.send_each_for_multicast, message, app=self._app)
            except Exception as error:
                # A failure sending one batch must not discard already-sent batches' results.
                logger.warning(f"FCM send_each_for_multicast failed for a batch of {len(batch)} tokens: {error}")
                results.extend(PushSendResult(token=token, status=PushSendStatus.FAILED, error=str(error)) for token in batch)
                continue
            results.extend(self._classify(token, send_response) for token, send_response in zip(batch, response.responses))
        return results

    @staticmethod
    def _classify(token: str, send_response: "messaging.SendResponse") -> PushSendResult:
        if send_response.success:
            return PushSendResult(token=token, status=PushSendStatus.SUCCESS)

        error = send_response.exception
        if isinstance(error, messaging.UnregisteredError):
            return PushSendResult(token=token, status=PushSendStatus.UNREGISTERED, error=str(error))

        logger.warning(f"FCM send failed for a token: {error}")
        return PushSendResult(token=token, status=PushSendStatus.FAILED, error=str(error) if error else "unknown error")
