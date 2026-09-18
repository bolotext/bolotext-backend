import argparse
import logging

import uvicorn

from agents_service.core.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="bolotext Agents microservice")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level.upper())

    settings = get_settings()
    # Reload is derived from ENVIRONMENT, never its own independent flag —
    # that's what makes "accidentally on in production" structurally
    # impossible rather than just discouraged. Reload mode is always
    # single-process, so WORKERS is only honored once it's off.
    reload = settings.environment.lower() == "development"
    workers = 1 if reload else settings.workers

    uvicorn.run(
        "agents_service.app:app",
        host=settings.host,
        port=settings.port,
        log_level=args.log_level.lower(),
        reload=reload,
        workers=workers,
    )


if __name__ == "__main__":
    main()
