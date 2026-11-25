"""
Admin audit logs record RequestContext.ip from trusted client IP resolution.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from portal.application.audit.rbac_audit_service import RbacAuditService
from portal.application.auth.results import HeaderInfo
from portal.libs.consts.enums import OperationType
from portal.libs.contexts.request_context import RequestContext, reset_request_context, set_request_context


@pytest.mark.asyncio
async def test_audit_log_uses_request_context_ip_not_forged_client_fallback(monkeypatch: pytest.MonkeyPatch):
    captured: list = []

    def _capture(event):
        captured.append(event)

    monkeypatch.setattr("portal.application.audit.rbac_audit_service.publish_event_in_background", _capture)

    token = set_request_context(RequestContext(ip="10.0.0.1", client_ip="10.0.0.1", headers=HeaderInfo(user_agent="pytest")))
    try:
        RbacAuditService().create_log(
            operation_type=OperationType.UPDATE, record_id=uuid4(), operation_code="role.update", old_data={"name": "a"}, new_data={"name": "b"}
        )
    finally:
        reset_request_context(token)

    assert len(captured) == 1
    assert captured[0].ip_address == "10.0.0.1"


@pytest.mark.asyncio
async def test_audit_log_uses_trusted_resolved_ip_when_set(monkeypatch: pytest.MonkeyPatch):
    captured: list = []

    def _capture(event):
        captured.append(event)

    monkeypatch.setattr("portal.application.audit.rbac_audit_service.publish_event_in_background", _capture)

    token = set_request_context(RequestContext(ip="198.51.100.7", client_ip="10.0.0.1", headers=HeaderInfo(user_agent="pytest")))
    try:
        RbacAuditService().create_log(operation_type=OperationType.CREATE, record_id=uuid4(), operation_code="role.create")
    finally:
        reset_request_context(token)

    assert len(captured) == 1
    assert captured[0].ip_address == "198.51.100.7"
