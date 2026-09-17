# bolotext-backend — Voice AI Platform, Microservices Monorepo

A multi-tenant Voice AI Agent platform backend, split into independently
deployable microservices behind an API Gateway. This is a **uv workspace**:
each service is its own Python package with its own `pyproject.toml` and
Dockerfile, sharing one dependency lockfile and a small `libs/common` package
for cross-cutting code (JWT verification, the RBAC role enum, the error
response schema).

```
bolotext-backend/
  pyproject.toml            # uv workspace root (virtual — no code of its own)
  uv.lock
  docker-compose.yml         # orchestrates mongo + all services
  libs/
    common/                  # shared: JWT verify, error schema, Role enum
  services/
    api-gateway/              # public entrypoint, reverse-proxies /api/v1/* (:8000)
    users/                     # organizations, users, auth (:8001) — fully implemented
    agents/                    # stub only, not implemented yet (:8002)
```

## Why this shape

- **Microservices, not a monolith**: each service has its own Dockerfile, own
  `pyproject.toml`, and can be deployed/scaled independently. The API Gateway
  is the only public-facing service; internal services talk to each other
  directly by hostname on a private Docker network.
- **Modular by domain, not by technical layer, inside each service**: the
  Users service has an `organizations/`, `users/`, and `auth/` package, and
  *each one* contains its own `router.py`, `service.py`, `repository.py`,
  `schema.py`, and `model.py`. Adding or changing a domain touches one folder,
  not five parallel ones.
- **Shared code lives in `libs/common`, not copy-pasted**: JWT decoding, the
  RBAC `Role` enum, and the `{code, message, details}` error schema are used
  by more than one service, so they're a real shared package (a `uv` workspace
  dependency), not duplicated files kept in sync by hand.

## Services

### `services/users` — Organizations, Users, Auth (fully implemented)

The only service with real business logic today. See
[`services/users/README.md`](services/users/README.md) for its API, RBAC
rules, env vars, and a curl walkthrough.

Internal layout:

```
services/users/src/users_service/
  organizations/   router.py, service.py, repository.py, schema.py, model.py
  users/           router.py, service.py, repository.py, schema.py, model.py
  auth/            router.py, service.py, repository.py, schema.py, model.py
                    (also owns RefreshToken — a session/auth artifact, not a user profile field)
  roles/           model.py   (seed-only reference collection, no router)
  core/            config, security (hashing + token issuance), deps (RBAC/tenancy), rate limiting
  db/              Mongo client wiring, idempotent seed script
  enums.py         OrganizationStatus, UserStatus (service-local)
  app.py           FastAPI app factory, wires all three routers under /api/v1
```

### `services/api-gateway` — public entrypoint (:8000)

A thin reverse proxy. It does **not** validate JWTs or terminate auth itself
today — it forwards `/api/v1/{prefix}/...` to whichever backend service owns
that prefix (see `_route_map()` in `api_gateway/app.py`), and that service
does its own RBAC/tenancy enforcement. This keeps the gateway simple while
there's only one real backend; centralizing auth in the gateway is a
reasonable next step once there's a second one.

| Prefix | Routes to |
|---|---|
| `/api/v1/auth/*`, `/api/v1/organizations/*`, `/api/v1/users/*`, `/api/v1/internal/*` | Users service |
| `/api/v1/agents/*` | Agents service (502 until `AGENTS_SERVICE_URL` is set and that service exists) |

### `services/agents` — stub (:8002)

Intentionally not implemented — see the file header in
`agents_service/app.py`. It exists so the microservice boundary (its own
package, Dockerfile, network membership, health check, and a slot in the
gateway's route map) is real from day one, without building agent/call
orchestration logic before it's asked for. When it grows real endpoints, it
should resolve identity via the Users service's
`POST /api/v1/internal/introspect` rather than re-implementing JWT
verification.

## Running everything locally

```bash
cp services/users/.env.example services/users/.env             # fill in real values
cp services/api-gateway/.env.example services/api-gateway/.env
docker compose up --build
```

This starts MongoDB, the Users service, the Agents stub, and the Gateway on
`:8000`. Everything goes through the gateway — see
[`services/users/README.md`](services/users/README.md) for the curl
walkthrough (org creation → admin → developer/QA), just swap the base URL
from the Users service's own port to `http://localhost:8000`.

### Running a single service without Docker

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync   # installs the whole workspace once, shared venv

cd services/users && uv run python main.py seed   # idempotent
cd services/users && uv run python main.py serve  # :8001

cd services/api-gateway && uv run python main.py   # :8000, proxies to :8001
```

Or via `make`: `make install`, `make seed`, `make run-users`, `make run-gateway`.

### Tests

```bash
make test   # Users service test suite, against an in-memory Mongo mock — no real DB needed
```

## Adding a new service

1. `services/<name>/pyproject.toml` with `common = { workspace = true }` under
   `[tool.uv.sources]` if it needs shared JWT/error/enum code.
2. `services/<name>/src/<name>_service/` — same modular-by-domain shape as
   `users_service` if it owns real domain logic; a stub `app.py` like
   `agents_service` if it's being scaffolded ahead of implementation.
3. Add it to `docker-compose.yml` and, if it should be publicly reachable, to
   the API Gateway's `_route_map()`.
4. Run `uv sync` at the repo root once — the workspace picks it up
   automatically via the `services/*` glob in the root `pyproject.toml`.
