"""Seed data contract: google + apple only (ADR 0005)."""

from portal.cli.datas.identity_provider_seed_data import seed_identity_providers


def test_identity_provider_seed_is_google_and_apple_only() -> None:
    codes = [row["code"] for row in seed_identity_providers]
    assert codes == ["google", "apple"]
    assert "microsoft" not in codes
    for row in seed_identity_providers:
        assert row["is_active"] is True
        assert row["requires_tenant"] is False
        assert isinstance(row["name"], str) and row["name"]
