"""
Push application results — aliases of domain read models.
"""

from portal.domain.push.entities import Device, Notification

DeviceResult = Device
NotificationResult = Notification

__all__ = ["DeviceResult", "NotificationResult"]
