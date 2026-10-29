"""Run the Users, Agents and API Gateway services as one backend from a single .env.

Only the API Gateway is public (PORT, 7860 by default — the port Hugging Face
Spaces exposes). Users and Agents bind to 127.0.0.1, so they are reachable by
the gateway and by each other but not from outside the container.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

users_port = os.getenv("USERS_PORT", "8001")
agents_port = os.getenv("AGENTS_PORT", "8002")
gateway_port = os.getenv("PORT", "7860")

# Service-to-service URLs always point at the in-container processes.
os.environ.setdefault("USERS_SERVICE_URL", f"http://127.0.0.1:{users_port}")
os.environ.setdefault("AGENTS_SERVICE_URL", f"http://127.0.0.1:{agents_port}")

# Same rule as each service's own entrypoint: reload only in development, and
# reload mode is always single-process.
reload = os.getenv("ENVIRONMENT", "development").lower() == "development"
workers = "1" if reload else os.getenv("WORKERS", "1")
log_level = os.getenv("LOG_LEVEL", "info").lower()

# (name, app, host, port, per-service env overrides, source dir)
SERVICES = [
    (
        "users",
        "users_service.app:app",
        "127.0.0.1",
        users_port,
        {"MONGO_DB_NAME": os.getenv("USERS_MONGO_DB_NAME", "bolotext_users")},
        "services/users/src",
    ),
    (
        "agents",
        "agents_service.app:app",
        "127.0.0.1",
        agents_port,
        {"MONGO_DB_NAME": os.getenv("AGENTS_MONGO_DB_NAME", "bolotext_agents")},
        "services/agents/src",
    ),
    (
        "api-gateway",
        "api_gateway.app:app",
        "0.0.0.0",  # noqa: S104 - the only public entrypoint
        gateway_port,
        {},
        "services/api-gateway/src",
    ),
]


def _spawn(app: str, host: str, port: str, overrides: dict[str, str], src: str) -> subprocess.Popen:
    cmd = [
        sys.executable, "-m", "uvicorn", app,
        "--host", host, "--port", port,
        "--log-level", log_level,
    ]  # fmt: skip
    if reload:
        cmd += ["--reload", "--reload-dir", src, "--reload-dir", "libs/common/src"]
    else:
        cmd += ["--workers", workers]
    return subprocess.Popen(cmd, cwd=ROOT, env={**os.environ, **overrides})


def main() -> int:
    procs = {name: _spawn(app, host, port, env, src) for name, app, host, port, env, src in SERVICES}
    print(f"Started {', '.join(procs)}; public gateway on :{gateway_port}", flush=True)

    def _stop(*_: object) -> None:
        for p in procs.values():
            if p.poll() is None:
                p.terminate()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    # If any service dies, stop the rest and exit non-zero so the container restarts.
    exit_code = 0
    while True:
        dead = [(n, p.returncode) for n, p in procs.items() if p.poll() is not None]
        if dead:
            for name, code in dead:
                print(f"{name} exited with code {code}", flush=True)
                exit_code = exit_code or code or 1
            _stop()
            break
        time.sleep(1)

    for p in procs.values():
        p.wait()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
