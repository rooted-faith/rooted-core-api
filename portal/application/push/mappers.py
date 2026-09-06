"""
Map push application results to API serializers.
"""

from portal.application.push.results import DeviceResult
from portal.serializers.apis.v1.push import DeviceRegistration


def device_to_api(result: DeviceResult) -> DeviceRegistration:
    return DeviceRegistration.model_validate(result)
