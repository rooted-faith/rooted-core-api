"""Member Fellowship API routes (ADR 0017 / ROO-123)."""

from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import Depends

from portal.application.fellowship.fellowship_service import FellowshipService
from portal.application.fellowship.mappers import (
    accept_covenant_to_command,
    create_fellowship_to_command,
    fellowship_list_to_api,
    fellowship_result_to_api,
    set_primary_to_command,
)
from portal.container import Container
from portal.exceptions.responses import UnauthorizedException
from portal.libs.contexts.user_context import get_user_context
from portal.libs.depends.rate_limiters import WRITE_RATE_LIMITERS
from portal.routers.auth_router import AuthRouter
from portal.serializers.apis.v1.fellowship import CreateFellowshipRequest, FellowshipListResponse, FellowshipResponse, SetPrimaryFellowshipRequest

router: AuthRouter = AuthRouter()


def _auth_user_id():
    user_context = get_user_context()
    if user_context is None:
        raise UnauthorizedException(detail="Authentication required")
    return user_context.user_id


@router.post(
    "",
    response_model=FellowshipResponse,
    response_model_by_alias=True,
    dependencies=[*WRITE_RATE_LIMITERS],
    operation_id="create_fellowship",
    summary="Create Fellowship",
)
@inject
async def create_fellowship(
    request: CreateFellowshipRequest, fellowship_service: FellowshipService = Depends(Provide[Container.fellowship_service])
) -> FellowshipResponse:
    result = await fellowship_service.create_fellowship(auth_user_id=_auth_user_id(), command=create_fellowship_to_command(request))
    return fellowship_result_to_api(result)


@router.get("", response_model=FellowshipListResponse, response_model_by_alias=True, operation_id="list_fellowships", summary="List my Fellowships")
@inject
async def list_fellowships(fellowship_service: FellowshipService = Depends(Provide[Container.fellowship_service])) -> FellowshipListResponse:
    return fellowship_list_to_api(await fellowship_service.list_fellowships(auth_user_id=_auth_user_id()))


@router.put(
    "/primary",
    response_model=FellowshipListResponse,
    response_model_by_alias=True,
    dependencies=[*WRITE_RATE_LIMITERS],
    operation_id="set_primary_fellowship",
    summary="Set Primary Fellowship",
)
@inject
async def set_primary_fellowship(
    request: SetPrimaryFellowshipRequest, fellowship_service: FellowshipService = Depends(Provide[Container.fellowship_service])
) -> FellowshipListResponse:
    result = await fellowship_service.set_primary_fellowship(auth_user_id=_auth_user_id(), command=set_primary_to_command(request))
    return fellowship_list_to_api(result)


@router.get("/{fellowship_id}", response_model=FellowshipResponse, response_model_by_alias=True, operation_id="get_fellowship", summary="Get Fellowship")
@inject
async def get_fellowship(fellowship_id: UUID, fellowship_service: FellowshipService = Depends(Provide[Container.fellowship_service])) -> FellowshipResponse:
    result = await fellowship_service.get_fellowship(auth_user_id=_auth_user_id(), fellowship_id=fellowship_id)
    return fellowship_result_to_api(result)


@router.post(
    "/{fellowship_id}/covenant",
    response_model=FellowshipResponse,
    response_model_by_alias=True,
    dependencies=[*WRITE_RATE_LIMITERS],
    operation_id="accept_fellowship_covenant",
    summary="Accept Fellowship Covenant",
)
@inject
async def accept_fellowship_covenant(
    fellowship_id: UUID, fellowship_service: FellowshipService = Depends(Provide[Container.fellowship_service])
) -> FellowshipResponse:
    result = await fellowship_service.accept_covenant(auth_user_id=_auth_user_id(), command=accept_covenant_to_command(fellowship_id))
    return fellowship_result_to_api(result)
