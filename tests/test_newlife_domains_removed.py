"""
Wave 1 #2: NewLife facility/org/member surfaces must be gone; platform remains.
"""

import importlib
from pathlib import Path

import pytest

import portal.models as models
from portal.container import Container
from portal.models.auth.user import AuthUser

REPO_ROOT = Path(__file__).resolve().parent.parent

NEWLIFE_PACKAGE_PREFIXES = (
    "portal.models.facility",
    "portal.models.org",
    "portal.models.member",
    "portal.domain.facility",
    "portal.domain.org",
    "portal.domain.member",
    "portal.infrastructure.persistence.repositories.facility",
    "portal.infrastructure.persistence.repositories.org",
    "portal.infrastructure.persistence.repositories.member",
    "portal.serializers.admin.v1.facility",
    "portal.serializers.admin.v1.org",
    "portal.serializers.apis.v1.facility",
    "portal.serializers.apis.v1.org",
)

NEWLIFE_MODEL_EXPORTS = (
    "FacilityRoom",
    "FacilityBooking",
    "MemberPerson",
    "OrgMinistry",
    "OrgPosition",
)

NEWLIFE_PATHS = (
    "portal/models/facility",
    "portal/models/org",
    "portal/models/member",
    "portal/domain/facility",
    "portal/domain/org",
    "portal/domain/member",
    "portal/infrastructure/persistence/repositories/facility",
    "portal/infrastructure/persistence/repositories/org",
    "portal/infrastructure/persistence/repositories/member",
    "portal/serializers/admin/v1/facility",
    "portal/serializers/admin/v1/org",
    "portal/serializers/admin/v1/ministry.py",
    "portal/serializers/admin/v1/ministry_catalog.py",
    "portal/serializers/apis/v1/facility.py",
    "portal/serializers/apis/v1/org.py",
    "portal/routers/admin/v1/member",
)


def test_models_package_does_not_export_newlife_entities():
    for name in NEWLIFE_MODEL_EXPORTS:
        assert name not in models.__all__
        assert not hasattr(models, name)


def test_auth_user_has_no_person_id():
    assert not hasattr(AuthUser, "person_id")


@pytest.mark.parametrize("module_name", NEWLIFE_PACKAGE_PREFIXES)
def test_newlife_packages_are_not_importable(module_name: str):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


@pytest.mark.parametrize("relative_path", NEWLIFE_PATHS)
def test_newlife_paths_are_removed_from_tree(relative_path: str):
    assert not (REPO_ROOT / relative_path).exists()


def test_container_constructs_with_bible_and_admin_platform():
    container = Container()
    assert container.bible_service is not None
    assert container.login_service is not None
    assert container.locale_service is not None
    assert container.setting_service is not None
    assert container.permission_service is not None
    assert container.file_service is not None
    assert container.legal_document_service is not None
    assert container.rbac_audit_service is not None


def test_kept_platform_packages_remain_importable():
    for module_name in (
        "portal.models.auth",
        "portal.models.content",
        "portal.models.audit",
        "portal.application.locale",
        "portal.application.rbac",
        "portal.application.system",
        "portal.application.content",
        "portal.application.bible",
    ):
        importlib.import_module(module_name)
