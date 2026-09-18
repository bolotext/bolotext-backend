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
    agents/                    # voice/chat agent builder + provider registry (:8002) — fully implemented
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
| `/api/v1/agents/*`, `/api/v1/providers/*` | Agents service |

### `services/agents` — Agent builder + provider registry (:8002)

Lets a user create, configure, and manage voice/chat AI agents (similar to
Retell AI / Gnani Agents). Storage is split across two Mongo collections by
how often the data changes:

- **`agents`** — core identity only: `org_id`, `user_id`, `name`,
  `description`, `status` (`draft`/`published`/`disabled`), timestamps.
  Small, rarely written.
- **`agent_configs`** — one document per agent holding every builder-tab
  section (prompt, flow, transcriber, llm, voice_persona, analytics, others,
  faq, deployment, actions, mcp, plus the non-identity part of "Agent
  Details" — languages/region/timezone/bot_type). Edited constantly,
  section-by-section, as the user works through the tabs. Not versioned as a
  whole — see Versioning below for why.

The two are joined by `agent_id` and merged back into one `AgentOut` shape at
the API layer (see `agents/service.to_out`), so the tabbed builder UI's
contract — one PATCH per tab — doesn't need to know or care about the split.

Code follows the same split, plus — like `users_service`'s
`organizations/`/`users/`/`auth/` layout — **each tab is its own top-level
module**, owning its schema, its PATCH route, and any section-specific logic:

```
services/agents/src/agents_service/
  agents/          The identity aggregate: model.py (the Agent document),
                   schema.py (the SECTIONS dispatch table + AgentOut/AgentReplace),
                   repository.py, service.py (create/list/get/replace/delete/
                   publish/clone — orchestrates across both `agents` and
                   `agent_configs`), router.py (same, as routes)
  agent_configs/   model.py (the AgentConfig document), repository.py
  agent_details/   schema.py + router.py (PATCH .../agent-details — the one
                   tab split across both documents; see
                   agents.service.update_agent_details)
  prompt/          schema.py + service.py (dynamic-variable validation, test
                   render, system-prompt version cap — see Versioning) +
                   version_model.py (the SystemPromptVersion document) +
                   repository.py + router.py (PATCH .../prompt, POST .../test,
                   GET/DELETE .../prompt/versions[/{version}])
  flow/            conversation flow — schema.py + router.py (PATCH .../flow)
  transcriber/     STT settings — schema.py + router.py (PATCH .../transcriber)
  llm/             schema.py + router.py (PATCH .../llm)
  voice_persona/   TTS personas — schema.py + router.py (PATCH .../voice-persona)
  analytics/       schema.py + router.py (PATCH .../analytics)
  others/          no-response/voicemail/call-transfer/precall vars — schema.py
                   + router.py (PATCH .../others)
  faq/             schema.py + router.py (PATCH .../faq)
  deployment/      schema.py + router.py (PATCH .../deployment)
  actions/         webhook-style tool calls — schema.py + router.py (PATCH .../actions)
  mcp/             MCP (Model Context Protocol) tool-server connections — schema.py
                   + router.py (PATCH .../mcp)
  providers/       read-only, cached LLM/STT/TTS provider+model registry,
                   seeded from code (providers/seed_data.py), not agent CRUD
  core/            config, deps (auth), http_client (Users-service introspection),
                   partial (generates PATCH-friendly optional-field schemas,
                   used by every section module's schema.py)
  db/              Mongo client wiring
  app.py           FastAPI app factory, wires every section's router in
```

`actions` and `mcp` are both "let the agent call out to something mid-call",
but at different levels: `actions` is one bare HTTP endpoint the platform
calls with a fixed param list; `mcp` is a whole external MCP server the agent
talks to, which can expose many tools (and can be restricted to an
allowlist via `MCPServer.allowed_tools`).

**Versioning**: scoped to `system_prompt` only, not the whole `agent_configs`
document — a whole-config version-per-publish turned out not to be useful,
since almost everything on the config changes far more often than "publish"
happens. Each distinct value ever saved to `system_prompt` (via `PATCH
.../prompt` or `PUT /agents/{id}`) is kept as a `SystemPromptVersion` row, up
to **5 per agent**. Saving a 6th distinct value is rejected — the whole PATCH
fails with 422 and "Maximum of 5 system prompt versions is allowed. Delete a
previous version, then you can save." — until the caller frees a slot via
`DELETE .../prompt/versions/{version}`. Saving the *same* value again, or
editing any other prompt field, never touches the count. `GET
.../prompt/versions` lists them (newest first). `POST /agents/{id}/publish`
is back to a plain status flip (`draft` → `published`) with no snapshotting.

It does **not** decode JWTs itself: `core/deps.get_current_auth` resolves the
caller's identity by calling the Users service's
`POST /api/v1/internal/introspect` (shared internal API key), so JWT
verification lives in exactly one place. Ownership is enforced per-org (an
agent belonging to another org 404s, not 403s, to avoid confirming it
exists). See `services/agents/.env.example` for its config, and `/docs` on
the running service for the full endpoint list, request/response shapes, and
example payloads.

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
make test          # Users service test suite, against an in-memory Mongo mock — no real DB needed
make test-agents   # Agents service test suite, same in-memory Mongo mock; auth is stubbed via a
                    # FastAPI dependency override instead of a real Users service call
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
