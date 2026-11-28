"""
Seed rows for public.system_setting (insert-if-missing only).
"""

seed_system_settings: list[dict] = [
    {
        "namespace": "fellowship",
        "setting_key": "max_active_members",
        "value_type": "number",
        "value": 50,
        "is_built_in": True,
        "is_active": True,
        "remark": "Maximum active members per Fellowship (ADR 0017)",
    },
    {
        "namespace": "fellowship",
        "setting_key": "max_group_members",
        "value_type": "number",
        "value": 15,
        "is_built_in": True,
        "is_active": True,
        "remark": "Maximum active members per Group within a Fellowship (ADR 0017)",
    },
]
