"""Map Fellowship serializers to commands and results to API models."""

from uuid import UUID

from portal.application.fellowship.commands import AcceptCovenantCommand, CreateFellowshipCommand, SetPrimaryFellowshipCommand
from portal.application.fellowship.results import FellowshipListResult, FellowshipResult
from portal.serializers.apis.v1.fellowship import CreateFellowshipRequest, FellowshipListResponse, FellowshipResponse, SetPrimaryFellowshipRequest


def create_fellowship_to_command(request: CreateFellowshipRequest) -> CreateFellowshipCommand:
    return CreateFellowshipCommand(name=request.name, discoverability=request.discoverability, covenant_accepted=request.covenant_accepted)


def set_primary_to_command(request: SetPrimaryFellowshipRequest) -> SetPrimaryFellowshipCommand:
    return SetPrimaryFellowshipCommand(fellowship_id=request.fellowship_id)


def accept_covenant_to_command(fellowship_id: UUID) -> AcceptCovenantCommand:
    return AcceptCovenantCommand(fellowship_id=fellowship_id)


def fellowship_result_to_api(result: FellowshipResult) -> FellowshipResponse:
    return FellowshipResponse.model_validate(result.model_dump())


def fellowship_list_to_api(result: FellowshipListResult) -> FellowshipListResponse:
    return FellowshipListResponse(items=[fellowship_result_to_api(item) for item in result.items], primary_fellowship_id=result.primary_fellowship_id)
