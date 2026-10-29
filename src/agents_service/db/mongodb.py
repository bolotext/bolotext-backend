from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from agents_service.agent_assignments.model import AgentAssignment
from agents_service.agent_configs.model import AgentConfig
from agents_service.agents.model import Agent
from agents_service.call_logs.model import CallLog
from agents_service.core.config import get_settings
from agents_service.prompt.version_model import SystemPromptVersion
from agents_service.whatsapp.model import (
    WhatsAppAgent,
    WhatsAppBatch,
    WhatsAppContact,
    WhatsAppMessageEvent,
    WhatsAppSettings,
    WhatsAppTemplate,
)

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
        document_models=[
            Agent,
            AgentConfig,
            SystemPromptVersion,
            AgentAssignment,
            CallLog,
            WhatsAppAgent,
            WhatsAppTemplate,
            WhatsAppBatch,
            WhatsAppContact,
            WhatsAppMessageEvent,
            WhatsAppSettings,
        ],
    )
    await _migrate_phone_numbers()


async def _migrate_phone_numbers() -> None:
    """Contacts used to store phone_number as an E.164 string; it is now an integer."""
    coll = WhatsAppContact.get_pymongo_collection()
    async for doc in coll.find({"phone_number": {"$type": "string"}}, {"phone_number": 1}):
        digits = "".join(ch for ch in doc["phone_number"] if ch.isdigit())
        if digits:
            await coll.update_one({"_id": doc["_id"]}, {"$set": {"phone_number": int(digits)}})


async def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
