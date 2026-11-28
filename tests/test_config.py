"""App support activation control (ROO-163): enforcement is off unless explicitly enabled, and a typo fails startup."""

import pytest
from pydantic import ValidationError

from portal.config import Configuration


@pytest.mark.parametrize("value", [None, "", "  "])
def test_enforcement_defaults_to_compatible_when_unset_or_empty(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("APP_SUPPORT_ENFORCEMENT", raising=False)
    else:
        monkeypatch.setenv("APP_SUPPORT_ENFORCEMENT", value)

    assert Configuration().APP_SUPPORT_ENFORCEMENT == "compatible"


def test_enforcement_is_enabled_only_by_the_exact_value(monkeypatch):
    monkeypatch.setenv("APP_SUPPORT_ENFORCEMENT", "enforced")

    assert Configuration().APP_SUPPORT_ENFORCEMENT == "enforced"


@pytest.mark.parametrize("value", ["enforce", "Enforced", "true", "on"])
def test_an_unknown_enforcement_value_fails_startup(monkeypatch, value):
    monkeypatch.setenv("APP_SUPPORT_ENFORCEMENT", value)

    with pytest.raises(ValidationError):
        Configuration()
