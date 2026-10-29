from enum import StrEnum


class Feature(StrEnum):
    """A product area a Super Admin can switch on or off per organization.
    Shared because the Users service stores/serves it and the Agents service
    enforces it.
    """

    VOICE_AGENTS = "voice_agents"
    WHATSAPP = "whatsapp"
    SMS = "sms"


ALL_FEATURES = [f.value for f in Feature]


class Role(StrEnum):
    """Platform-wide RBAC roles. Shared because any service that gates access
    by role (not just the Users service that issues tokens) needs the same
    values to interpret the `role` claim on an access token.
    """

    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    DEVELOPER = "DEVELOPER"
    QA = "QA"
