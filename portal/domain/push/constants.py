"""
Push domain constants.
"""

from enum import Enum


class DeliveryStatus(str, Enum):
    """NotificationDelivery.status — one attempt to deliver to one Device."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class PushSendStatus(str, Enum):
    """Per-token classification of a PushGatewayPort.send_multicast result."""

    SUCCESS = "success"
    FAILED = "failed"
    UNREGISTERED = "unregistered"
