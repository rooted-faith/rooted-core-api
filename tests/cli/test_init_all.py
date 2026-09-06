"""
init-all orchestration: fixed step order, fail-fast on the first error.
"""

import pytest

from portal.cli import init_all


def test_init_all_process_calls_steps_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(init_all, "init_locales_process", lambda: calls.append("locale"))
    monkeypatch.setattr(init_all, "seed_identity_providers_process", lambda: calls.append("identity_provider"))
    monkeypatch.setattr(init_all, "seed_legal_documents_process", lambda: calls.append("legal_document"))
    monkeypatch.setattr(init_all, "seed_system_settings_process", lambda: calls.append("system_setting"))
    monkeypatch.setattr(init_all, "init_rbac_process", lambda: calls.append("rbac"))
    monkeypatch.setattr(init_all, "create_superuser_process", lambda: calls.append("superuser"))

    init_all.init_all_process()

    assert calls == ["locale", "identity_provider", "legal_document", "system_setting", "rbac", "superuser"]


def test_init_all_process_stops_after_a_failing_step(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(init_all, "init_locales_process", lambda: calls.append("locale"))
    monkeypatch.setattr(init_all, "seed_identity_providers_process", lambda: calls.append("identity_provider"))

    def failing_legal_document() -> None:
        calls.append("legal_document")
        raise RuntimeError("legal document seed failed")

    monkeypatch.setattr(init_all, "seed_legal_documents_process", failing_legal_document)
    monkeypatch.setattr(init_all, "seed_system_settings_process", lambda: calls.append("system_setting"))
    monkeypatch.setattr(init_all, "init_rbac_process", lambda: calls.append("rbac"))
    monkeypatch.setattr(init_all, "create_superuser_process", lambda: calls.append("superuser"))

    with pytest.raises(RuntimeError, match="legal document seed failed"):
        init_all.init_all_process()

    assert calls == ["locale", "identity_provider", "legal_document"]
