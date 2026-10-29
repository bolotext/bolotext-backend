from typing import Generic, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class SuccessResponse(BaseModel, Generic[DataT]):
    """Envelope every successful API response is returned in, always with
    HTTP status 200 — see the error equivalent this pairs with in
    `common.errors.register_exception_handlers`. Pair with
    `common.responses.success_response()` when building the return value, and
    set `response_model=SuccessResponse[YourSchema]` on the route so the
    OpenAPI docs describe the real (wrapped) shape.
    """

    status: str = Field("success", description="Always `\"success\"` for this envelope.")
    code: int = Field(200, description="The logical HTTP status of the operation, e.g. 200 or 201.")
    message: str = Field("Success", description="Short, human-readable summary of what happened.")
    data: DataT | None = Field(None, description="The endpoint's actual response payload, shaped per-endpoint; `null` for endpoints with nothing to return.")
