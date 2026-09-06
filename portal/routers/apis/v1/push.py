"""
Push device API router.
"""

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from starlette import status

from portal.application.push.mappers import device_to_api
from portal.application.push.push_service import PushService
from portal.container import Container
from portal.libs.contexts.user_context import get_user_context
from portal.libs.depends.rate_limiters import WRITE_RATE_LIMITERS
from portal.routers.auth_router import AuthRouter
from portal.serializers.apis.v1.push import DeviceRegistration, DeviceRegistrationRequest

router: AuthRouter = AuthRouter()


@router.put(
    "/devices/{device_key}",
    response_model=DeviceRegistration,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    require_auth=False,
    optional_auth=True,
    dependencies=[*WRITE_RATE_LIMITERS],
    operation_id="register_push_device",
    summary="Register or refresh a push device",
    description=(
        "Upsert a push Device by device_key. Authorization is optional: when present it must verify "
        "(invalid/expired tokens still 401), and end_user_id is always overwritten to whatever this call resolved."
    ),
)
@inject
async def register_device(
    device_key: str, body: DeviceRegistrationRequest, push_service: PushService = Depends(Provide[Container.push_service])
) -> DeviceRegistration:
    user_context = get_user_context()
    auth_user_id = user_context.user_id if user_context else None
    end_user_id = await push_service.resolve_end_user_id(auth_user_id)

    result = await push_service.register_device(
        device_key=device_key, token=body.token, platform=body.platform, app_version=body.app_version, end_user_id=end_user_id
    )
    return device_to_api(result)
