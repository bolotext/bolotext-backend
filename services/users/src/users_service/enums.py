from enum import StrEnum

# Role (SUPER_ADMIN/ADMIN/DEVELOPER/QA) lives in the shared `common` package:
# any service that verifies an access token needs the same values to read its
# `role` claim. These two statuses are internal to this service's own domain
# models, so they stay local.


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class UserStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    DISABLED = "disabled"
