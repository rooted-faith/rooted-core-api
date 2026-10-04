"""
Resend email event webhook.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status

from portal.config import settings
from portal.infrastructure.mail.resend_email_events import InvalidResendSignatureError, ResendEmailEventReceiver, ResendWebhookNotConfiguredError

router = APIRouter(tags=["webhooks"])


@router.post("/email-events", operation_id="resend_email_events", include_in_schema=False)
async def receive_email_event(request: Request) -> Response:
    """
    Verify the Svix signature over the raw body, then acknowledge.
    Only genuine receiver failures return 5xx so Resend retries just those.
    """
    payload = await request.body()
    try:
        ResendEmailEventReceiver(settings.RESEND_WEBHOOK_SECRET).receive(payload, request.headers)
    except InvalidResendSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature.")
    except ResendWebhookNotConfiguredError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook receiver is not configured.")
    return Response(status_code=status.HTTP_200_OK)
