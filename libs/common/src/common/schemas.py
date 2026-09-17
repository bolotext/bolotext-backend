from typing import Generic, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class SuccessResponse(BaseModel, Generic[DataT]):
    """Envelope every successful API response is returned in. Pair with
    `common.responses.success_response()` when building the return value, and
    set `response_model=SuccessResponse[YourSchema]` on the route so the
    OpenAPI docs describe the real (wrapped) shape.
    """

    status: str = "success"
    code: int = 200
    message: str = "Success"
    data: DataT | None = None
