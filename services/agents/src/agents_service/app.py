"""Placeholder only. This service is intentionally not implemented yet — see
the platform README. It exists so the microservice boundary (its own package,
Dockerfile, and a slot in the API Gateway's route map) is real from day one,
without building agent/call orchestration logic before it's asked for.

When this service grows real endpoints, resolve identity the same way any
non-Users service should: call the Users service's
`POST /api/v1/internal/introspect` (shared internal API key) rather than
re-implementing JWT verification.
"""

from common.errors import register_exception_handlers
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import FastAPI

app = FastAPI(title="agents-service", version="0.1.0")
register_exception_handlers(app)


@app.get("/health", tags=["health"], response_model=SuccessResponse[dict])
async def health() -> dict:
    return success_response(data={"service": "agents-service", "implemented": False})
