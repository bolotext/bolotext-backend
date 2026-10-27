# Users Service

Owns organizations (tenants), users, roles, and JWT-based auth for the
platform. Runs on `:8001`. See the [repo root README](../../README.md) for
how this fits into the overall microservices layout.

## Stack

- **API**: FastAPI
- **DB**: MongoDB via Motor + Beanie (ODM)
- **Auth**: Google Sign-In (ID token verified server-side) issuing JWT (access + refresh). No passwords are stored
- **Tenancy**: every resource is scoped by an indexed `organization_id`; every
  org-scoped query goes through a repository function that always filters by
  it — a client can never supply its own `organization_id` to widen a query
- **RBAC**: `SUPER_ADMIN` (platform-level, org-less) → `ADMIN` → `DEVELOPER`
  (read-only user list) → `QA` (own profile only), enforced via a
  `require_role(...)` FastAPI dependency, not scattered `if` checks. `Role`
  itself lives in `libs/common` since other services will need the same enum
  to interpret a token's `role` claim.

## Module layout

Domain-modular, not layered globally: each of `organizations/`, `users/`, and
`auth/` is self-contained.

```
src/users_service/
  organizations/   router.py  service.py  repository.py  schema.py  model.py
  users/           router.py  service.py  repository.py  schema.py  model.py
  auth/            router.py  service.py  repository.py  schema.py  model.py
  roles/           model.py                       # seed-only reference collection
  core/            config.py  security.py  deps.py  rate_limit.py  time.py
  db/              mongodb.py  seed.py
  enums.py         OrganizationStatus, UserStatus  (service-local)
  app.py           FastAPI app factory
```

`auth/` owns the `RefreshToken` model (a session/auth artifact) even though
`users/service.py` calls into `auth/repository.py` to revoke sessions on
disable — that cross-module call is expected in a modular
(not fully isolated) service; what matters is there's no import cycle back
the other way.

## Setup

```bash
cp .env.example .env   # then fill in real values, see below
uv sync                 # from the repo root — this is a workspace member
```

### Environment variables (`.env`)

| Variable | Purpose |
|---|---|
| `MONGO_URI` | MongoDB connection string |
| `MONGO_DB_NAME` | Database name |
| `JWT_SECRET` | HMAC signing secret for access/refresh tokens. Must be identical wherever a token this service issues gets verified directly (not via the gateway) — never commit a real one |
| `JWT_ALGORITHM` | Defaults to `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | Token lifetimes |
| `INTERNAL_API_KEY` | Shared secret for `/api/v1/internal/introspect`, used by other internal services to resolve a token without re-implementing JWT verification |
| `LOGIN_RATE_LIMIT` | e.g. `5/minute`, applied to `POST /auth/login` |
| `BOOTSTRAP_SUPER_ADMIN_EMAIL` / `_NAME` | Used only by the seed step below, to idempotently create the first `SUPER_ADMIN`. Unset them after your first run in a shared environment. |

> A `SUPER_ADMIN` is always org-less (`organization_id` is `null`) and there is
> no API path to attach one to an organization — the bootstrap seed script is
> the only way one gets created.

### Run locally

```bash
uv run python main.py seed    # idempotent: seeds the 4 fixed roles + bootstrap Super Admin
uv run python main.py serve   # starts the API on :8001
```

### Tests

```bash
uv run pytest   # against an in-memory Mongo mock (mongomock-motor) — no real DB needed
```

Covers: auth flow (login/refresh/logout, disabled accounts), RBAC per role,
and tenant isolation (an Admin from one org cannot see or touch another org's
users).

### API docs

`http://localhost:8001/docs` (Swagger) and `http://localhost:8001/openapi.json`.

## Curl walkthrough

Create an org → admin creates a developer and QA user. Talking to this
service directly on `:8001`; swap the base URL for `http://localhost:8000` to
go through the API Gateway instead.

```bash
BASE=http://localhost:8001/api/v1

# 1. Log in as the bootstrap Super Admin (seeded via BOOTSTRAP_SUPER_ADMIN_* env vars).
#    GOOGLE_ID_TOKEN is the ID token from Google Sign-In for that email.
SUPER_TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"credential\":\"$GOOGLE_ID_TOKEN\"}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

# 2. Super Admin creates an organization, bootstrapping its first Admin in the same call
curl -s -X POST $BASE/organizations \
  -H "Authorization: Bearer $SUPER_TOKEN" -H 'Content-Type: application/json' \
  -d '{
        "name": "Acme Corp",
        "slug": "acme-corp",
        "admin_email": "admin@acme.example.com",
        "admin_full_name": "Acme Admin"
      }'

# 3. Log in as that org Admin
ADMIN_TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"credential\":\"$ADMIN_GOOGLE_ID_TOKEN\"}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

# 4. Admin creates a Developer and a QA user in their own org
curl -s -X POST $BASE/users -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"email":"dev@acme.example.com","full_name":"Dev One","role":"DEVELOPER"}'

curl -s -X POST $BASE/users -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"email":"qa@acme.example.com","full_name":"QA One","role":"QA"}'

# 5. Admin lists the org's users (Developer can too, read-only; QA gets 403)
curl -s $BASE/users -H "Authorization: Bearer $ADMIN_TOKEN"
```

## RBAC summary

| | Organizations | Create/update/disable users | List/get users | Own profile |
|---|---|---|---|---|
| `SUPER_ADMIN` | full access, any org | any org | any org | yes |
| `ADMIN` | none | own org only | own org | yes |
| `DEVELOPER` | none | no | own org (read-only) | yes |
| `QA` | none | no | no | yes |

Role can never be escalated to `SUPER_ADMIN` through the API (create or
update) — it is only ever seeded by the bootstrap script — and org-scoped
callers' requests always resolve `organization_id` from their own JWT-backed
session, never from client-supplied input.

## For other services

`POST /api/v1/internal/introspect` (guarded by `X-Internal-Api-Key`, not user
JWTs) lets another microservice resolve `user_id`, `organization_id`, and
`role` from an access token without re-implementing JWT verification itself.
