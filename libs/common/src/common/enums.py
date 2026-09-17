from enum import StrEnum


class Role(StrEnum):
    """Platform-wide RBAC roles. Shared because any service that gates access
    by role (not just the Users service that issues tokens) needs the same
    values to interpret the `role` claim on an access token.
    """

    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    DEVELOPER = "DEVELOPER"
    QA = "QA"
