"""
Test passcode eligibility policy: which identities may sign in without an emailed OTP (ADR 0016).
"""

import re
from dataclasses import dataclass, field
from functools import cached_property
from typing import Optional

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
# At least two labels, so a rule can never cover a whole top-level domain.
_DOMAIN = rf"{_LABEL}(?:\.{_LABEL})+"
_LOCAL_ATOM = r"[a-z0-9!#%&'+/=_`~-]+"
_LOCAL = rf"{_LOCAL_ATOM}(?:\.{_LOCAL_ATOM})*"

_EXACT_EMAIL_RULE = re.compile(rf"{_LOCAL}@{_DOMAIN}")
_EXACT_DOMAIN_RULE = re.compile(rf"\*@(?P<domain>{_DOMAIN})")
_SUBDOMAIN_RULE = re.compile(rf"\*@\*\.(?P<domain>{_DOMAIN})")


@dataclass(frozen=True)
class _AllowlistMatcher:
    emails: frozenset[str]
    domains: frozenset[str]
    parent_domains: frozenset[str]

    @classmethod
    def compile(cls, rules: tuple[str, ...]) -> Optional["_AllowlistMatcher"]:
        """Return None unless every rule is valid; a malformed list is never partially applied."""
        emails: set[str] = set()
        domains: set[str] = set()
        parent_domains: set[str] = set()
        for raw_rule in rules:
            rule = raw_rule.strip().lower()
            if match := _SUBDOMAIN_RULE.fullmatch(rule):
                parent_domains.add(match["domain"])
            elif match := _EXACT_DOMAIN_RULE.fullmatch(rule):
                domains.add(match["domain"])
            elif _EXACT_EMAIL_RULE.fullmatch(rule):
                emails.add(rule)
            else:
                return None
        return cls(emails=frozenset(emails), domains=frozenset(domains), parent_domains=frozenset(parent_domains))

    def matches(self, email: str) -> bool:
        local, _, domain = email.rpartition("@")
        if not local or "@" in local or not domain:
            return False
        if email in self.emails or domain in self.domains:
            return True
        labels = domain.split(".")
        if not all(labels):
            return False
        return any(".".join(labels[index:]) in self.parent_domains for index in range(1, len(labels)))


@dataclass(frozen=True)
class OtpTestPolicy:
    """One coherent reading of the server template: the flag and the allowlist always belong together."""

    project_id: str
    test_mode_enabled: bool = False
    allowlist: tuple[str, ...] = field(default=(), repr=False)

    @cached_property
    def _matcher(self) -> Optional[_AllowlistMatcher]:
        return _AllowlistMatcher.compile(self.allowlist)

    @property
    def allowlist_is_valid(self) -> bool:
        return self._matcher is not None

    def permits(self, email: str) -> bool:
        return self.test_mode_enabled and self._matcher is not None and self._matcher.matches(email.strip().lower())
