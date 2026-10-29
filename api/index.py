"""Vercel entrypoint: serves the backend app from src/ as a serverless function.

Serverless has no reliable app startup/shutdown, so the MongoDB/Beanie init that
src/main.py does in its lifespan runs here once per warm instance, on first request.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agents_service.db.mongodb import get_client as get_agents_client  # noqa: E402
from agents_service.db.mongodb import init_db as init_agents_db  # noqa: E402
from main import app as backend_app  # noqa: E402
from users_service.db.mongodb import get_client as get_users_client  # noqa: E402
from users_service.db.mongodb import init_db as init_users_db  # noqa: E402

_ready = False
_lock = asyncio.Lock()


async def _ensure_db() -> None:
    global _ready
    if _ready:
        return
    async with _lock:
        if not _ready:
            await init_users_db(get_users_client())
            await init_agents_db(get_agents_client())
            _ready = True


async def app(scope, receive, send) -> None:
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    await _ensure_db()
    await backend_app(scope, receive, send)
