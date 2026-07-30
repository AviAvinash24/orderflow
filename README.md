# OrderFlow

Concurrency-safe e-commerce **order fulfillment backend** (portfolio demo) — not a full storefront or real payment processor.

It focuses on three hard problems:

1. **Inventory correctness under concurrency** — never oversell
2. **Payment safety under unreliable webhooks** — exactly-once application of gateway events
3. **Reliable non-blocking side effects** — transactional outbox so notifications aren’t lost if workers crash

**Implemented lifecycle:** place order → reserve stock → pay via webhook → cancel / auto-expire unpaid reservations.  
**Schema-ready, not yet exposed as APIs:** `packed` → `shipped` → `delivered` (`migrations/0005_create_orders.sql`).

---

## Quick start

```bash
# 1. Create .env (gitignored)
cat > .env <<'EOF'
POSTGRES_USER=orderflow
POSTGRES_PASSWORD=orderflow
POSTGRES_DB=orderflow
JWT_SECRET=change-me
JWT_EXPIRE_MINUTES=60
EOF

# 2. Start API, worker, Postgres, Redis
docker compose up --build

# 3. Apply migrations (from host, against localhost:5432)
export POSTGRES_USER=orderflow POSTGRES_PASSWORD=orderflow POSTGRES_DB=orderflow
python scripts/run_migrations.py

# 4. Smoke check
curl http://localhost:8000/health
```

API: `http://localhost:8000` · Docs: `http://localhost:8000/docs`

**Tests**

```bash
# Auth unit tests (ASGI, no live stack required beyond deps)
pytest app/tests/test_auth_deps.py

# Failure-case tests need docker compose up
pytest app/tests/test_failure_cases.py
```

---

## Architecture overview

```
Client ──► FastAPI (api)
              │
              ├──► PostgreSQL   (orders, inventory, payments, outbox)
              ├──► Redis        (rate limits)
              └──► expiry loop  (in-process: unpaid reservations)

Worker (RQ) ◄── Redis broker
    │
    └──► drains outbox_events from PostgreSQL
```

| Concern | Where it runs |
|---|---|
| HTTP API + reservation expiry | `api` process (`app/main.py` lifespan) |
| Outbox drain | separate `worker` process (`app/worker.py` + RQ) |
| System of record | PostgreSQL |
| Rate limits + job wake-ups | Redis |

---

## Tech stack

| Layer | Choice | Where |
|---|---|---|
| Language | Python 3.12 | `Dockerfile` |
| API | FastAPI + Uvicorn | `app/main.py`, `requirements.txt` |
| Validation | Pydantic v2 | `app/schemas/` |
| DB | PostgreSQL 16 | `docker-compose.yml` |
| DB driver | **asyncpg** (raw SQL, no ORM) | `app/core/db.py`, routers |
| Auth | JWT (PyJWT) + bcrypt | `app/core/security.py` |
| Cache / rate limit / broker | Redis 7 | `docker-compose.yml`, `app/core/rate_limit.py` |
| Background jobs | RQ | `app/worker.py` |
| Tests | pytest + pytest-asyncio + httpx | `app/tests/`, `pytest.ini` |
| Containers | Docker + docker-compose | `Dockerfile`, `docker-compose.yml` |
| Config | `python-dotenv` + env vars | `app/core/config.py` |
| Migrations | Custom SQL runner + `schema_migrations` | `scripts/run_migrations.py` |

Deliberate absences: no ORM, no Celery, no `services/` or `models/` packages — business logic lives in routers + jobs with explicit SQL transactions.

---

## Directory structure

```
.
├── README.md
├── Dockerfile
├── docker-compose.yml          # api, worker, db, redis
├── requirements.txt
├── pytest.ini
├── migrations/                 # Ordered SQL schema + seed + indexes
├── scripts/run_migrations.py   # Applies *.sql once via schema_migrations
└── app/
    ├── main.py                 # FastAPI app, lifespan (DB/Redis + expiry loop)
    ├── worker.py               # RQ outbox worker process
    ├── core/                   # config, db, auth deps, security, rate limit
    ├── routers/                # HTTP handlers
    ├── schemas/                # Pydantic request/response DTOs
    ├── jobs/                   # Outbox drain + reservation expiry
    └── tests/
```

| Path | Role |
|---|---|
| `app/main.py` | App wiring, lifespan, `/health`, `/me` |
| `app/core/config.py` | Env-driven knobs (JWT, reservation TTL, outbox, rate limits) |
| `app/core/db.py` | Global asyncpg pool |
| `app/core/deps.py` | `CurrentUser` + Bearer JWT dependency |
| `app/core/security.py` | Password hash/verify + JWT create/decode |
| `app/core/rate_limit.py` | Redis fixed-window order placement limit |
| `app/routers/*.py` | HTTP business logic (SQL in handlers) |
| `app/schemas/*.py` | API contracts |
| `app/jobs/outbox.py` | Claim/process outbox rows |
| `app/jobs/expire_reservations.py` | Expire unpaid `placed` orders; release stock |
| `app/worker.py` | Enqueue + RQ consume |
| `migrations/` | Source of truth for the data model |

---

## Request flows

### Place order

```
Client
  → POST /orders (JWT)
  → enforce_order_rate_limit (Redis)
  → BEGIN transaction
      → sort items by product_id (deadlock avoidance)
      → for each item: atomic inventory UPDATE (available → reserved)
      → INSERT orders (status=placed, expires_at=now+RESERVATION_MINUTES)
      → INSERT order_items
  → COMMIT
  → 201 OrderResponse
```

**Code:** `create_order` in `app/routers/orders.py`, `app/core/rate_limit.py`, `RESERVATION_MINUTES` in `app/core/config.py`.

On insufficient stock: `409` and the whole transaction rolls back (all-or-nothing multi-item reservation).

### Payment webhook → outbox → worker

```
Gateway
  → POST /webhooks/payment
  → BEGIN
      → SELECT order FOR UPDATE
      → INSERT payment_events (unique gateway_event_id)
      → if succeeded AND status=placed:
           UPDATE orders → paid
           INSERT outbox_events (event_type=order.paid)   ← same TX
  → COMMIT
  → always 200 {"ok": true}

Worker (app/worker.py)
  → enqueue_loop every OUTBOX_POLL_SECONDS if queue empty
  → RQ runs process_outbox_batch
      → SELECT pending FOR UPDATE SKIP LOCKED
      → handle (currently a log stub)
      → UPDATE status=processed
```

**Code:** `app/routers/webhooks.py`, `app/jobs/outbox.py`, `app/worker.py`, migrations `0007_*`, `0008_*`, `0011_*`.

### Unpaid reservation expiry (API process)

```
API lifespan (main.py)
  → asyncio task: expiry_loop
  → every EXPIRY_JOB_INTERVAL_SECONDS:
      → claim placed+expired orders (SKIP LOCKED)
      → status=expired
      → release reserved stock → available
```

**Code:** `app/main.py`, `app/jobs/expire_reservations.py`, index `migrations/0010_orders_expire_index.sql`.

### Cancel

```
POST /orders/{id}/cancel
  → FOR UPDATE order
  → only if placed|paid
  → status=cancelled
  → release inventory (same TX)
```

**Code:** `cancel_order` in `app/routers/orders.py`.

### Auth / catalog

- Signup/login → JWT (`app/routers/auth.py`)
- List/get products with `quantity_available` (`app/routers/products.py`)

| Router | Prefix | File |
|---|---|---|
| Auth | `/auth` | `app/routers/auth.py` |
| Products | `/products` | `app/routers/products.py` |
| Orders | `/orders` | `app/routers/orders.py` |
| Webhooks | `/webhooks` | `app/routers/webhooks.py` |
| App-level | `/health`, `/me` | `app/main.py` |

Webhooks are unauthenticated (simulated gateway callbacks).

---

## Design patterns

| Pattern | Mechanism | Where |
|---|---|---|
| Atomic inventory reservation | `UPDATE … WHERE quantity_available >= n RETURNING` | `create_order` in `app/routers/orders.py` |
| Available vs reserved stock | Two counters + `CHECK >= 0` | `migrations/0004_create_inventory.sql` |
| Transactional order create | One TX: reserve all lines + insert order/items | `create_order` |
| Deadlock avoidance | Sort line items by `product_id` before locking | `create_order` |
| Row locking for cancel | `SELECT … FOR UPDATE` + conditional status UPDATE | `cancel_order` |
| Idempotent payments | `UNIQUE(gateway_event_id)` + catch `UniqueViolationError` | `migrations/0007_*`, `app/routers/webhooks.py` |
| Transactional outbox | Insert `outbox_events` in same TX as `paid` transition | `app/routers/webhooks.py` |
| Outbox drain concurrency | `FOR UPDATE SKIP LOCKED` + batch limit | `app/jobs/outbox.py` |
| Reservation expiry concurrency | Nested `FOR UPDATE SKIP LOCKED` claim | `app/jobs/expire_reservations.py` |
| Always-200 webhook | Avoid gateway retry storms | `app/routers/webhooks.py` |
| Fixed-window rate limit | Redis incr/expire per user | `app/core/rate_limit.py` |
| Retry-safe outbox handlers | Documented “must be safe to retry” | `_handle_event` in `app/jobs/outbox.py` |
| Enqueue without spam | Enqueue only if `queue.count == 0` | `app/worker.py` |
| Partial indexes | Expiry + pending outbox scans | `migrations/0010_*`, `0011_*` |

---

## Data model

```
users 1──* orders 1──* order_items *──1 products 1──1 inventory
              │
              ├──* payment_events  (gateway_event_id UNIQUE)
              └── outbox_events (independent; payload refs order_id in JSON)
```

| Table | Key fields / constraints | Migration |
|---|---|---|
| `users` | `email` UNIQUE, `password_hash` | `0002_create_users.sql` |
| `products` | `sku` UNIQUE, `price >= 0` | `0003_create_products.sql` |
| `inventory` | 1:1 `product_id`, `quantity_available/reserved >= 0` | `0004_create_inventory.sql` |
| `orders` | `order_status` enum, `expires_at`, `total_amount` | `0005_create_orders.sql` |
| `order_items` | snapshot `unit_price_at_purchase`, `quantity > 0` | `0006_create_order_items.sql` |
| `payment_events` | `gateway_event_id` UNIQUE, `payment_status` | `0007_create_payment_events.sql` |
| `outbox_events` | `event_type`, `payload` JSONB, `outbox_status` | `0008_create_outbox_events.sql` |

**Order status enum:** `placed | paid | packed | shipped | delivered | cancelled | expired`  
**Seed catalog:** `0009_seed_products.sql` (fixed UUIDs; tests use mouse `11111111-…`).

- Order items snapshot price at purchase time
- Inventory is separate from products so stock math stays isolated
- Payment events are append-only; uniqueness is the idempotency key
- Outbox is decoupled from `orders`; the payload carries `order_id`

---

## Infrastructure

### docker-compose services

| Service | Role |
|---|---|
| `api` | FastAPI + in-process expiry loop (port 8000) |
| `worker` | RQ outbox processor (`python -m app.worker`) |
| `db` | PostgreSQL 16 (port 5432, volume `pgdata`) |
| `redis` | Redis 7 — rate limits + RQ broker (port 6379) |

Both `api` and `worker` use `env_file: .env` (not committed).

### Config knobs (`app/core/config.py`)

| Var | Default | Purpose |
|---|---|---|
| `POSTGRES_*` | required | DB connection |
| `JWT_SECRET` | required | Token signing |
| `JWT_EXPIRE_MINUTES` | 60 | Token TTL |
| `RESERVATION_MINUTES` | 10 | Hold stock after place |
| `EXPIRY_JOB_INTERVAL_SECONDS` | 30 | Expiry poll interval |
| `REDIS_URL` | `redis://redis:6379/0` | Redis |
| `OUTBOX_POLL_SECONDS` | 5 | Worker enqueue interval |
| `OUTBOX_BATCH_SIZE` | 100 | Drain batch size |
| `ORDER_RATE_LIMIT` | 5 | Max place-order / window |
| `ORDER_RATE_WINDOW_SECONDS` | 60 | Rate-limit window |

Rate limit key: `rate:orders:{user_id}` — applied only on `POST /orders`.

---

## Failure handling

| Failure | Behavior | Code |
|---|---|---|
| Duplicate email signup | 409 | `app/routers/auth.py` |
| Bad/missing JWT | 401 | `app/core/deps.py` |
| Unknown product | 404 | `app/routers/orders.py` |
| Insufficient stock | 409; TX abort | `create_order` |
| Concurrent last-unit race | One 201, one 409 | atomic inventory UPDATE |
| Cancel after packed+ | 409 | status gate |
| Concurrent cancel | `FOR UPDATE` + conditional UPDATE | `cancel_order` |
| Duplicate webhook | 200; ignore second insert | unique + catch |
| Unknown order webhook | 200 + warning log | avoid retry storms |
| Late success after non-`placed` | Record payment, ignore status change | `app/routers/webhooks.py` |
| Failed payment status | Record event, leave order as-is | `app/routers/webhooks.py` |
| Rate limit exceeded | 429 + `Retry-After` | `app/core/rate_limit.py` |
| Expiry job exception | Logged; loop continues | `app/jobs/expire_reservations.py` |
| Enqueue failure | Logged; sleep and retry | `app/worker.py` |
| Worker crash mid-batch | Unprocessed rows stay `pending` if TX rolls back | `app/jobs/outbox.py` |

**Outbox nuance:** handle + mark processed run in one DB transaction. If the handler later performs real external I/O before commit, crashes could double-send — handlers must be safe to retry. Today the handler only logs, so that risk is latent.

### Tests (`app/tests/test_failure_cases.py`)

1. **`test_double_webhook_is_idempotent`** — same `gateway_event_id` twice → one `paid`, one `payment_events` row, one `order.paid` outbox event
2. **`test_concurrent_buyers_only_one_wins_last_unit`** — stock=1, two parallel buyers → `[201, 409]`, inventory `available=0`, `reserved=1`
3. **`test_expiry_releases_reserved_stock`** — force `expires_at` past, run `expire_stale_reservations` → `expired`, stock released

Auth edge cases: `app/tests/test_auth_deps.py`.  
Fixtures: `app/tests/conftest.py` (`live_client` expects `docker compose up`).

---

## Design rationale

1. **Raw SQL / asyncpg over ORM** — explicit control of transactions, `FOR UPDATE`, `SKIP LOCKED`, and conditional updates. Cost: more boilerplate.
2. **Split available/reserved counters** — soft-hold stock without a reservation ledger; expiry/cancel reverse the same arithmetic.
3. **DB unique constraint for webhook idempotency** — correctness under races without distributed locks; app catches `UniqueViolationError`.
4. **Transactional outbox + RQ** — side effects don’t block checkout; Postgres is the durable event store, Redis is only wake/schedule. RQ is simpler than Celery for this scope.
5. **Enqueue only when the queue is empty** — avoids stacking drain jobs every poll interval; batch size + `SKIP LOCKED` still allow parallel workers.
6. **Expiry in API vs outbox in worker** — expiry is latency-tolerant and uses the app’s asyncpg pool; outbox is a classic background consumer. Multiple API replicas are safe via `SKIP LOCKED`.
7. **Always-200 webhooks** — prefer internal anomaly logs over HTTP errors that trigger gateway retry storms.
8. **Deterministic lock order on product IDs** — prevents multi-item deadlocks under concurrent multi-SKU carts.
9. **Fixed-window Redis rate limit** — cheap abuse protection on place-order (bursty at window boundaries).
10. **Lifecycle enum ahead of fulfillment APIs** — schema documents the full state machine while code implements place/pay/cancel/expire.
11. **Price snapshot on `order_items`** — historical correctness if catalog prices change.
12. **No dedicated services layer** — keeps a small teaching codebase readable; extract if fulfillment/payment logic grows.

---

## Known gaps

- No `packed` / `shipped` / `delivered` transitions in application code yet (enum only)
- Outbox handler is a log stub (`app/jobs/outbox.py`)
- No `failed` outbox status / dead-letter queue
- Webhook endpoint has no signature verification (simulated gateway)
- `.env` is required locally and not committed
