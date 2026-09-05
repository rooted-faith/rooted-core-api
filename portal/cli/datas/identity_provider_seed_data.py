"""Identity provider catalog seed rows (google + apple only)."""

seed_identity_providers: list[dict] = [
    {"code": "google", "name": "Google", "is_active": True, "requires_tenant": False},
    {"code": "apple", "name": "Apple", "is_active": True, "requires_tenant": False},
]
