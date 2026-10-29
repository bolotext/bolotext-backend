import argparse
import asyncio
import logging

import uvicorn

from users_service.core.config import get_settings


def _serve(log_level: str) -> None:
    settings = get_settings()
    # Reload is derived from ENVIRONMENT, never its own independent flag —
    # that's what makes "accidentally on in production" structurally
    # impossible rather than just discouraged. Reload mode is always
    # single-process, so WORKERS is only honored once it's off.
    reload = settings.environment.lower() == "development"
    workers = 1 if reload else settings.workers

    uvicorn.run(
        "users_service.app:app",
        host=settings.host,
        port=settings.port,
        log_level=log_level.lower(),
        reload=reload,
        workers=workers,
    )


async def _seed() -> None:
    from users_service.db.mongodb import close_db, get_client, init_db
    from users_service.db.seed import seed_all

    await init_db(get_client())
    await seed_all()
    await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description="bolotext Users microservice")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "seed"])
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level.upper())
    print(f"Starting bolotext Users microservice with command: {args.command}")
    if args.command == "seed":
        asyncio.run(_seed())
    else:
        _serve(args.log_level)


if __name__ == "__main__":
    main()
