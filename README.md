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
  `description`, `status` (`active`/`inactive`, defaults to `active` — an
  agent is usable as soon as it's created, there's no draft/publish gate),
  timestamps. Small, rarely written.
- **`agent_configs`** — one document per (agent, **environment**) holding
  every builder-tab section (prompt, flow, transcriber, llm, voice_persona,
  analytics, others, faq, deployment, actions, mcp, plus the non-identity
  part of "Agent Details" — region/timezone/bot_type — and `languages`, its
  own dedicated field/endpoint, see below). Not versioned as a whole — see
  Versioning below for why.

The two are joined by `agent_id` (+ `environment`) and merged back into one
`AgentOut` shape at the API layer (see `agents/service.to_out`), so the
tabbed builder UI's contract — one PATCH per tab — doesn't need to know or
care about the split. `GET /agents/{id}` returns this full `AgentOut`;
`GET /agents` (the list) deliberately doesn't — see "Listing agents" below.

#### Listing agents

`GET /agents` returns `AgentListItem` rows, not `AgentOut`: identity only
(`id`/`user_id`/`org_id`/`status`/`agent_details.name`+`description`/
`created_at`/`updated_at`), nothing from `AgentConfig` (no environment,
languages, region/timezone/bot_type, or any builder-tab section). It never
reads `AgentConfig` at all — see `agents.service.list_agents`/`to_list_item`.
Fetch `GET /agents/{id}` (→ `AgentOut`) for an individual agent's full config.

#### Environments: development / stage / production

Every agent has three `agent_configs` documents, one per environment.
`development` is the only one edited directly — every tab's PATCH route
implicitly targets it. `stage` and `production` are read-only snapshots,
written only by promoting the environment immediately before them in the
pipeline, never skipping a step:

| Route | Effect |
|---|---|
| `GET /agents/{id}/environments` | Summary of all three (`exists`, `updated_at`) |
| `GET /agents/{id}/environments/{env}` | One environment's full `AgentOut` (`env` ∈ `development`/`stage`/`production`); **404** if that environment hasn't been populated yet (never fabricates an empty one — unlike plain `GET /agents/{id}`, which self-heals `development`) |
| `POST /agents/{id}/move-to-stage` | Deep-copies `development` → `stage` |
| `POST /agents/{id}/move-to-prod` | Deep-copies `stage` → `production`; blocked (422) if stage is missing required sections (`agents.service._missing_sections`) |

`stage`/`production` configs are created lazily (empty) the first time
they're read or promoted into — see `agents.service._get_config`'s self-heal
— so a brand-new agent's `GET .../environments` shows them as
`exists: false` until promoted at least once.

#### Languages

An agent is always created English-only (`AgentConfig.languages` defaults to
`["en-IN"]`) — creation never asks for languages, even if a caller's payload
includes the key (silently ignored: `languages` isn't a field on
`AgentDetails` at all). The only way to change it is
`PUT /agents/{id}/languages` (`{"languages": [...]}`, full replace, at least
one required) — see `agents_service.languages`. This list is also what `language_switch_mode` scopes its generated prompt to
— see Language-switch prompts below; configure two or more languages here
before `implicit`/`explicit` mode does anything.

#### Pre-call variables

`AgentPrompt.pre_call_variables` (`dict[str, str]`, e.g.
`{"customer_name": "", "company_name": "Acme Bank"}`) — nested inside the
`prompt` section, not a bare `AgentConfig` field — holds this agent's
default values for `{{var}}` placeholders in `welcome_message`/the text
resolved for `system_prompt`/`ending_message`/a `custom`-mode
`language_switch_prompt`. It's also now the **declared set** a `{{var}}`
reference in `welcome_message`/`ending_message` must belong to
(`prompt.service.validate_prompt`) — there's no separate "declare a
variable name" field any more; adding a key to `pre_call_variables` *is*
declaring it, with its value doubling as the default. Set with
`PUT /agents/{id}/pre-call-variables` (full replace; an empty mapping is
fine — unlike languages, there's no non-empty requirement); like every
other write to `prompt`, it re-validates the whole section
(`agents.service._save_prompt`), so you can't remove a variable that's
still referenced in text this way either. Resolved wherever a "what would
actually be sent" render already happens: `POST /agents/{id}/test`
(`sample_values` in the request wins over a pre-call default, which wins
over a bare `<var_name>` placeholder) and
`GET /agents/{id}/prompt/language-switch-preview` (only for `custom` mode's
text — `implicit`/`explicit` are fixed language-detection templates with no
customer data to substitute). See `prompt.service.render_test`/
`resolve_language_switch_prompt`.

Note this is a distinct field from `others.precall_variables` (a
`list[{variable, sample_value, description}]`, richer per-variable metadata
but no default *value* to resolve against, and not tied into prompt-text
validation) — the two currently overlap in purpose without being unified;
see that section's schema if you're touching either.

#### Language-switch prompts

`AgentPrompt.language_switch_mode` (`implicit`/`explicit`/`custom`) controls
what's sent to a separate mid-call LLM step that watches multi-engine STT
output and decides whether the caller is switching languages. Set it (plus
`language_switch_prompt`/`min_words_for_lang_switch`) via
`PATCH /agents/{id}/prompt/language-switch` — the only way to change it
(there's no generic whole-section `PATCH /agents/{id}/prompt` any more; see
below). `implicit`/`explicit` each render a fixed template (`prompt/language_switch.py`)
scoped to exactly the languages configured above — an agent set to Hindi +
English only ever sees those two in its rendered prompt, never Kannada/
Tamil/Telugu. Below two configured languages, both modes render to `None`
(nothing to switch between). `custom` skips the template and uses
`language_switch_prompt` verbatim (required in that mode — 422 otherwise).
`GET /agents/{id}/prompt/language-switch-preview` returns exactly what would
be sent right now: `{mode, languages, prompt}`.

Code follows the same split, plus — like `users_service`'s
`organizations/`/`users/`/`auth/` layout — **each tab is its own top-level
module**, owning its schema, its PATCH route, and any section-specific logic:

```
services/agents/src/agents_service/
  agents/          The identity aggregate: model.py (the Agent document),
                   schema.py (the SECTIONS dispatch table + AgentOut/
                   AgentListItem/EnvironmentSummary/AgentStatusUpdate), repository.py, service.py
                   (create/list/get/delete (cascading — see Deleting an agent)/
                   clone/update_status (+activate/deactivate)/environments/
                   move_to_stage/move_to_prod — orchestrates across `agents`,
                   `agent_configs` and `system_prompt_versions`), router.py
                   (same, as routes)
  agent_configs/   model.py (the AgentConfig document), repository.py
  agent_details/   schema.py + router.py (PATCH .../agent-details — the one
                   tab split across both documents; see
                   agents.service.update_agent_details). `languages` is
                   deliberately not part of this tab — see languages/ below.
  languages/       schema.py + router.py (PUT .../languages — the only way
                   AgentConfig.languages changes; see Languages above)
  precall_variables/ schema.py + router.py (PUT .../pre-call-variables — the
                   only way AgentPrompt.pre_call_variables changes; see
                   Pre-call variables above. Named for the route/field, even
                   though the field it writes now lives on `prompt`, not
                   directly on `AgentConfig`.)
  prompt/          schema.py (AgentPrompt — welcome/system_prompt/ending,
                   language-switch fields, pre_call_variables and
                   dynamic_message all nested in one section now, with no
                   PATCH route of its own — see PromptMessages/
                   LanguageSwitchSettings, the narrower models each backing
                   the one route that can actually change that part of it)
                   + service.py ({{var}} validation against
                   pre_call_variables, test render, system-prompt-version
                   CRUD (an independent snippet library — see Versioning);
                   language-switch prompt rendering — see Language-switch
                   prompts) + language_switch.py (the implicit/explicit
                   templates) + version_model.py (the SystemPromptVersion
                   document) + repository.py + router.py (PATCH
                   .../prompt/messages, PATCH .../prompt/language-switch,
                   POST .../test, GET .../prompt/language-switch-preview,
                   POST/GET/PATCH .../prompt/versions (PATCH replaces one
                   version's text, `prompt_key` in the body — see
                   Versioning), DELETE .../prompt/versions/{prompt_key} —
                   deliberately no PATCH .../prompt; every AgentPrompt field
                   has its own narrower route)
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
  dynamic_message/ schema.py only (DynamicMessageSettings, nested inside
                   AgentPrompt — see prompt/ above) + router.py (POST/GET/
                   PATCH/DELETE .../dynamic-message, POST
                   .../dynamic-message/enable|disable, all implemented in
                   agents.service against config.prompt.dynamic_message —
                   see Dynamic message configuration below)
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

**Versioning**: `AgentPrompt.system_prompt` is plain text, stored and used
directly — set it via `PATCH /agents/{id}/prompt/messages`
(`{welcome_message, system_prompt, ending_message}` only, see
`prompt/schema.py`'s `PromptMessages` — the *only* way to change it; there's
no generic whole-section `PATCH /agents/{id}/prompt`). It is **not**
validated against or resolved from anything else.

`system_prompt_versions` (its own collection, capped at **5 per agent**,
`{prompt_key, prompt_description, system_prompt}`) is a separate, optional
library of reusable snippets — somewhere to save text for later copy/reuse,
nothing more. Same field name as `AgentPrompt.system_prompt` (that one's a
saved snippet's text, this one's live agent state) — don't confuse the two;
they're otherwise unrelated, and a version can be created, replaced, or
deleted freely regardless of what any agent's `system_prompt` currently
holds:

| Route | Effect |
|---|---|
| `POST /agents/{id}/prompt/versions` | Create a version (`prompt_key` unique per agent — 409 if reused; 422 past the cap) |
| `GET /agents/{id}/prompt/versions` | List this agent's versions (newest first) |
| `PATCH /agents/{id}/prompt/versions` | Replace one version's `system_prompt` text — body is `{prompt_key, system_prompt}` (`prompt_key` identifies which version, not a path param; `prompt_description` isn't settable this way) — `prompt.service.replace_system_prompt` |
| `DELETE /agents/{id}/prompt/versions/{prompt_key}` | Delete |

**Status**: `Agent.status` is just `active`/`inactive` (default `active` —
an agent is usable as soon as it's created, there's no draft/publish gate to
go through first). `PATCH /agents/{id}/status` sets it explicitly;
`POST /agents/{id}/activate` / `.../deactivate` are shortcuts for the two
values.

**Deleting an agent**: `DELETE /agents/{id}` is a hard delete, and a
cascading one — it removes every environment's `AgentConfig` (development/
stage/production) and every `SystemPromptVersion` row for that agent, then
the `Agent` document itself (`agents.service.delete_agent`). There is no
soft-delete/recovery and no `PUT /agents/{id}` full-replace route either (a
tab is always edited section-by-section, via its own PATCH route, or via
`PUT /agents/{id}/languages`/`PUT /agents/{id}/pre-call-variables` for those
two fields — see Languages/Pre-call variables above).

**Dynamic message configuration** (`AgentPrompt.dynamic_message` — nested in
the `prompt` section, not a section of its own, even though it gets its own
URL prefix): an external API the agent can call mid-call for a dynamic
message — `{dynamic_message_enabled, method, url, headers}`, `method` ∈
`GET`/`POST`/`PUT`/`PATCH`/`DELETE`. This service only stores the config;
actually calling that API is a live-call-runtime concern outside it. Every
write goes through `agents.service._save_prompt` like any other prompt
change (harmless here — a dynamic-message-only edit never touches
welcome/ending text or pre_call_variables, so re-validating them is a
no-op), via its own dedicated functions
(`update_dynamic_message`/`set_dynamic_message`/`reset_dynamic_message`) —
`dynamic_message` isn't in the `SECTIONS` table, so it can't go through the
generic `update_section` dispatch. Unlike every other section (always
present with defaults, only ever PATCHed), this one gets the fuller
CRUD-style surface a "dynamic message" config was asked for:

| Route | Effect |
|---|---|
| `POST /agents/{id}/dynamic-message` | Full replace (`agents.service.set_dynamic_message` — the "create/define it from scratch" counterpart to the usual PATCH-merge; still a replace, not a true single-use create, since the field always exists) |
| `GET /agents/{id}/dynamic-message` | This field alone (`config.prompt.dynamic_message`), not the whole `AgentOut` |
| `PATCH /agents/{id}/dynamic-message` | Partial update (`agents.service.update_dynamic_message`) |
| `DELETE /agents/{id}/dynamic-message` | Reset to defaults (`agents.service.reset_dynamic_message` — the closest equivalent to "delete" here) |
| `POST /agents/{id}/dynamic-message/enable` / `.../disable` | Shortcuts for `dynamic_message_enabled`, same idea as agent `/activate`/`/deactivate` |

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

### Dev vs. production runtime

Every service's `main()`/`_serve()` (`<service>/src/<pkg>/__init__.py`) calls
`uvicorn.run(...)` with `host`/`port`/`workers` read from `Settings`
(`ENVIRONMENT`/`HOST`/`PORT`/`WORKERS` env vars, see each service's
`.env.example`) — there's no separate `--reload` flag to set: **reload is
only ever on when `ENVIRONMENT=development`** (the default), which is what
makes it impossible to leave it accidentally on in production. Any other
value (`production`, `staging`, ...) runs without it, honoring `WORKERS`
instead (ignored under reload, which is always single-process).

| | `make run-agents` (and `run-users`/`run-gateway`) | `make run-agents-prod` (and `-users`/`-gateway`) | `docker compose up` |
|---|---|---|---|
| `ENVIRONMENT` | `development` (from `.env`/`Settings` default) | `production` (forced by the make target) | `production` (forced in `docker-compose.yml`, overriding even the per-service `.env`) |
| Equivalent to | `uvicorn <pkg>.app:app --host 0.0.0.0 --port <port> --reload` | `uvicorn <pkg>.app:app --host 0.0.0.0 --port <port> --workers ${WORKERS:-4}` | same as the prod make target, plus each Dockerfile's own `ENV ENVIRONMENT=production` default |

The Docker images bake in `ENVIRONMENT=production`/`WORKERS=4` as their own
defaults (see each `Dockerfile`), so even a container run standalone
(outside `docker-compose.yml`, no env vars passed) never starts in reload
mode.

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
