"""Admin Devotion authoring routes."""

from typing import Annotated
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Query, status

from portal.application.devotion.devotion_service import DevotionService
from portal.application.devotion.mappers import (
    create_devotion_to_command,
    devotion_detail_to_api,
    devotion_page_to_api,
    devotion_pages_query_to_command,
    devotion_translation_to_api,
    update_devotion_to_command,
    upsert_devotion_translation_to_command,
)
from portal.container import Container
from portal.libs.consts.permission import Permission
from portal.routers.auth_router import AuthRouter
from portal.serializers.admin.v1.devotion import (
    AdminDevotionCreate,
    AdminDevotionDetail,
    AdminDevotionPages,
    AdminDevotionQuery,
    AdminDevotionTranslation,
    AdminDevotionTranslationUpsert,
    AdminDevotionUpdate,
)

router: AuthRouter = AuthRouter(is_admin=True)


@router.get(path="", response_model=AdminDevotionPages, response_model_by_alias=True, permissions=[Permission.CONTENT_DEVOTION.read])
@inject
async def get_devotion_pages(
    query: Annotated[AdminDevotionQuery, Query()], devotion_service: DevotionService = Depends(Provide[Container.devotion_service])
) -> AdminDevotionPages:
    return devotion_page_to_api(await devotion_service.get_devotion_pages(devotion_pages_query_to_command(query)))


@router.post(
    path="",
    status_code=status.HTTP_201_CREATED,
    response_model=AdminDevotionDetail,
    response_model_by_alias=True,
    permissions=[Permission.CONTENT_DEVOTION.create],
)
@inject
async def create_devotion(body: AdminDevotionCreate, devotion_service: DevotionService = Depends(Provide[Container.devotion_service])) -> AdminDevotionDetail:
    return devotion_detail_to_api(await devotion_service.create_devotion(create_devotion_to_command(body)))


@router.get(path="/{devotion_id}", response_model=AdminDevotionDetail, response_model_by_alias=True, permissions=[Permission.CONTENT_DEVOTION.read])
@inject
async def get_devotion(devotion_id: UUID, devotion_service: DevotionService = Depends(Provide[Container.devotion_service])) -> AdminDevotionDetail:
    return devotion_detail_to_api(await devotion_service.get_devotion(devotion_id))


@router.put(path="/{devotion_id}", response_model=AdminDevotionDetail, response_model_by_alias=True, permissions=[Permission.CONTENT_DEVOTION.modify])
@inject
async def update_devotion(
    devotion_id: UUID, body: AdminDevotionUpdate, devotion_service: DevotionService = Depends(Provide[Container.devotion_service])
) -> AdminDevotionDetail:
    return devotion_detail_to_api(await devotion_service.update_devotion(devotion_id, update_devotion_to_command(body)))


@router.delete(path="/{devotion_id}", status_code=status.HTTP_204_NO_CONTENT, permissions=[Permission.CONTENT_DEVOTION.delete])
@inject
async def delete_devotion(devotion_id: UUID, devotion_service: DevotionService = Depends(Provide[Container.devotion_service])) -> None:
    await devotion_service.delete_devotion(devotion_id)


@router.put(
    path="/{devotion_id}/translations/{locale_code}",
    response_model=AdminDevotionTranslation,
    response_model_by_alias=True,
    permissions=[Permission.CONTENT_DEVOTION.modify],
)
@inject
async def upsert_devotion_translation(
    devotion_id: UUID, locale_code: str, body: AdminDevotionTranslationUpsert, devotion_service: DevotionService = Depends(Provide[Container.devotion_service])
) -> AdminDevotionTranslation:
    result = await devotion_service.upsert_devotion_translation(devotion_id, locale_code, upsert_devotion_translation_to_command(body))
    return devotion_translation_to_api(result)


@router.post(path="/{devotion_id}/publish", response_model=AdminDevotionDetail, response_model_by_alias=True, permissions=[Permission.CONTENT_DEVOTION.modify])
@inject
async def publish_devotion(devotion_id: UUID, devotion_service: DevotionService = Depends(Provide[Container.devotion_service])) -> AdminDevotionDetail:
    return devotion_detail_to_api(await devotion_service.publish_devotion(devotion_id))
