from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from agents_service.agent_assignments.model import AgentAssignment
from agents_service.agent_configs.model import AgentConfig
from agents_service.agents.model import Agent
from agents_service.core.config import get_settings
from agents_service.prompt.version_model import SystemPromptVersion

if not hasattr(AsyncIOMotorClient, "_bolotext_append_metadata_patched"):
    # motor's async method table predates pymongo's MongoClient.append_metadata,
    # so unpatched attribute access falls through to motor's "unknown attribute ->
    # treat as a database name" convenience shorthand instead of the real method,
    # which breaks beanie's init_beanie() (it calls database.client.append_metadata(...)).
    # Delegate straight to the underlying (synchronous, non-network) pymongo call.
    def _append_metadata(self: AsyncIOMotorClient, *args, **kwargs) -> None:
        self.delegate.append_metadata(*args, **kwargs)

    AsyncIOMotorClient.append_metadata = _append_metadata
    AsyncIOMotorClient._bolotext_append_metadata_patched = True

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client


async def init_db(client: AsyncIOMotorClient | None = None) -> None:
    settings = get_settings()
    active_client = client or get_client()
    await init_beanie(
        database=active_client[settings.mongo_db_name],
        document_models=[Agent, AgentConfig, SystemPromptVersion, AgentAssignment],
    )


async def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
