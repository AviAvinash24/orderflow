# OrderFlow

Concurrency-safe e-commerce **order fulfillment backend** (portfolio demo).

Not a storefront and not a real payment processor. It models the hard path: reserve stock, take payment under unreliable webhooks, fulfill the order, and release inventory correctly when things fail.

Focus:

1. **Inventory correctness under concurrency** — never oversell
2. **Payment safety under unreliable webhooks** — exactly-once application of gateway events
3. **Reliable side effects** — transactional outbox so workers can crash without losing events

---

## Order lifecycle

```
placed ──payment succeeded──► paid ──► packed ──► shipped ──► delivered
   │                              │
   ├──reservation expiry──► expired
   └──user cancel─────────► cancelled
                                  ▲
                            paid orders can also cancel
                            (refund is stubbed / not a real PSP refund)
```

| Status | Meaning |
|---|---|
| `placed` | Order created; stock held in `quantity_reserved`; unpaid reservation has `expires_at` |
| `paid` | Payment webhook applied; order ready for fulfillment |
| `packed` | Warehouse packed the order; reserved stock is consumed (sold) |
| `shipped` | Order left the warehouse |
| `delivered` | Order reached the customer — terminal success |
| `expired` | Unpaid reservation timed out; stock returned to available |
| `cancelled` | User cancelled while `placed` or `paid`; stock returned to available |

### What is implemented today

| Transition | Status | How |
|---|---|---|
| → `placed` | Done | `POST /orders` reserves stock |
| `placed` → `paid` | Done | `POST /webhooks/payment` (`succeeded`) |
| `placed` → `expired` | Done | Background expiry job |
| `placed` → `cancelled` | Done | `POST /orders/{id}/cancel` |
| `paid` → `cancelled` | Done | Same cancel endpoint (no real refund yet) |
| `paid` → `packed` | Schema only | Enum exists; API not exposed yet |
| `packed` → `shipped` | Schema only | Enum exists; API not exposed yet |
| `shipped` → `delivered` | Schema only | Enum exists; API not exposed yet |

Schema source of truth: `migrations/0005_create_orders.sql`.

### Inventory rules across the flow

| Event | Inventory effect |
|---|---|
| Place order | `available -= qty`, `reserved += qty` |
| Expire / cancel (`placed` or `paid`) | `reserved -= qty`, `available += qty` |
| Pack (`paid` → `packed`, planned) | `reserved -= qty` (stock leaves the system as sold) |
| Ship / deliver | Status only — no further stock math |

Cancel is blocked once an order reaches `packed` or later (`409`).

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

```bash
# Auth unit tests (ASGI)
pytest app/tests/test_auth_deps.py

# Failure-case tests need docker compose up
pytest app/tests/test_failure_cases.py
```

---

## Architecture

```
Client ──► FastAPI (api)
              │
              ├──► PostgreSQL   (orders, inventory, payments, outbox)
              ├──► Redis        (rate limits)
              └──► expiry loop  (unpaid reservations)

Worker (RQ) ◄── Redis broker
    │
    └──► drains outbox_events from PostgreSQL
```

| Concern | Process |
|---|---|
| HTTP API + reservation expiry | `api` (`app/main.py` lifespan) |
| Outbox drain | `worker` (`app/worker.py` + RQ) |
| System of record | PostgreSQL |
| Rate limits + job wake-ups | Redis |

---

## Happy path (place → pay → fulfill)

### 1. Place order → `placed`

```
POST /orders (JWT)
  → rate limit (Redis)
  → BEGIN
      → sort items by product_id          # deadlock avoidance
      → for each item: available → reserved
      → INSERT order (status=placed, expires_at)
      → INSERT order_items
  → COMMIT → 201
```

Insufficient stock → `409`, whole TX rolls back.

**Code:** `create_order` in `app/routers/orders.py`

### 2. Payment webhook → `paid`

```
POST /webhooks/payment
  → BEGIN
      → SELECT order FOR UPDATE
      → INSERT payment_events (gateway_event_id UNIQUE)
      → if succeeded AND status=placed:
           UPDATE → paid
           INSERT outbox_events (order.paid)   # same TX
  → COMMIT → always 200 {"ok": true}
```

Duplicate `gateway_event_id` → ignored (idempotent).  
Late success after non-`placed` → payment recorded, status unchanged.

**Code:** `app/routers/webhooks.py`

### 3. Fulfillment → `packed` → `shipped` → `delivered` (planned APIs)

```
POST /orders/{id}/pack      # paid → packed; consume reserved stock
POST /orders/{id}/ship      # packed → shipped
POST /orders/{id}/deliver   # shipped → delivered
```

Each step: `FOR UPDATE` + conditional status UPDATE + outbox event in the same TX.  
Illegal transition → `409`.

---

## Side paths

### Unpaid reservation expiry → `expired`

```
API lifespan expiry loop (every EXPIRY_JOB_INTERVAL_SECONDS)
  → claim placed + expires_at < now (SKIP LOCKED)
  → status=expired
  → release reserved → available
```

Only unpaid `placed` orders expire. Paid/packed+ are never touched.

**Code:** `app/jobs/expire_reservations.py`

### Cancel → `cancelled`

```
POST /orders/{id}/cancel
  → FOR UPDATE
  → allow only placed | paid
  → status=cancelled
  → release reserved → available
```

Cancel after `paid` is allowed; a real gateway refund is **not** implemented (future: refund stub / outbox `order.refund_requested`).

**Code:** `cancel_order` in `app/routers/orders.py`

### Outbox → worker

```
Worker
  → poll / enqueue when queue empty
  → process_outbox_batch
      → SELECT pending FOR UPDATE SKIP LOCKED
      → handle (log stub today)
      → mark processed
```

**Code:** `app/jobs/outbox.py`, `app/worker.py`

---

## API surface

| Area | Prefix | File |
|---|---|---|
| Auth (signup / login → JWT) | `/auth` | `app/routers/auth.py` |
| Products | `/products` | `app/routers/products.py` |
| Orders (create, get, cancel) | `/orders` | `app/routers/orders.py` |
| Payment webhooks | `/webhooks` | `app/routers/webhooks.py` |
| Health / me | `/health`, `/me` | `app/main.py` |

Webhooks are unauthenticated (simulated gateway).

---

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| API | FastAPI + Uvicorn |
| Validation | Pydantic v2 |
| DB | PostgreSQL 16 + **asyncpg** (raw SQL, no ORM) |
| Auth | JWT (PyJWT) + bcrypt |
| Cache / broker | Redis 7 |
| Background jobs | RQ |
| Tests | pytest + pytest-asyncio + httpx |
| Containers | Docker Compose |

Deliberate absences: no ORM, no Celery, no `services/` / `models/` packages — business logic lives in routers + jobs with explicit SQL transactions.

---

## Directory structure

```
.
├── README.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pytest.ini
├── migrations/                 # Ordered SQL schema + seed + indexes
├── scripts/run_migrations.py
└── app/
    ├── main.py                 # FastAPI app, lifespan, expiry loop
    ├── worker.py               # RQ outbox worker
    ├── core/                   # config, db, auth, rate limit
    ├── routers/                # HTTP handlers
    ├── schemas/                # Pydantic DTOs
    ├── jobs/                   # outbox drain + reservation expiry
    └── tests/
```

---

## Data model

```
users 1──* orders 1──* order_items *──1 products 1──1 inventory
              │
              ├──* payment_events   (gateway_event_id UNIQUE)
              └── outbox_events     (payload refs order_id in JSON)
```

| Table | Key fields | Migration |
|---|---|---|
| `users` | `email` UNIQUE, `password_hash` | `0002_*` |
| `products` | `sku` UNIQUE, `price >= 0` | `0003_*` |
| `inventory` | `quantity_available`, `quantity_reserved` (≥ 0) | `0004_*` |
| `orders` | `order_status`, `expires_at`, `total_amount` | `0005_*` |
| `order_items` | price snapshot, `quantity > 0` | `0006_*` |
| `payment_events` | `gateway_event_id` UNIQUE | `0007_*` |
| `outbox_events` | `event_type`, JSONB payload, status | `0008_*` |

**Statuses:** `placed | paid | packed | shipped | delivered | cancelled | expired`  
**Seed catalog:** `0009_seed_products.sql` (tests use mouse `11111111-…`).

---

## Design patterns

| Pattern | Mechanism | Where |
|---|---|---|
| Atomic reservation | `UPDATE … WHERE available >= n RETURNING` | `create_order` |
| Available vs reserved | Two counters + `CHECK >= 0` | `0004_create_inventory.sql` |
| Deadlock avoidance | Sort line items by `product_id` | `create_order` |
| Row lock on cancel | `SELECT … FOR UPDATE` + conditional UPDATE | `cancel_order` |
| Idempotent payments | `UNIQUE(gateway_event_id)` | `webhooks.py` |
| Transactional outbox | Insert outbox in same TX as status change | `webhooks.py` |
| Concurrent drain / expiry | `FOR UPDATE SKIP LOCKED` | `outbox.py`, `expire_reservations.py` |
| Always-200 webhook | Avoid gateway retry storms | `webhooks.py` |
| Place-order rate limit | Redis fixed window per user | `rate_limit.py` |

---

## Failure handling

| Failure | Behavior |
|---|---|
| Duplicate signup email | `409` |
| Bad / missing JWT | `401` |
| Unknown product | `404` |
| Insufficient stock | `409`; TX abort |
| Concurrent last unit | One `201`, one `409` |
| Cancel after `packed`+ | `409` |
| Concurrent cancel | One wins via `FOR UPDATE` |
| Duplicate payment webhook | `200`; second insert ignored |
| Unknown order webhook | `200` + warning log |
| Failed payment event | Recorded; order stays `placed` |
| Rate limit exceeded | `429` + `Retry-After` |

### Tests (`app/tests/test_failure_cases.py`)

1. **Double webhook** — same `gateway_event_id` → one `paid`, one payment row, one `order.paid` outbox event  
2. **Concurrent last unit** — stock=1, two buyers → `[201, 409]`, inventory correct  
3. **Expiry** — stale `placed` → `expired`, reserved stock released  

Auth edge cases: `app/tests/test_auth_deps.py`.

---

## Infrastructure & config

| Service | Role |
|---|---|
| `api` | FastAPI + expiry loop (port 8000) |
| `worker` | RQ outbox processor |
| `db` | PostgreSQL 16 |
| `redis` | Rate limits + RQ broker |

| Var | Default | Purpose |
|---|---|---|
| `POSTGRES_*` | required | DB |
| `JWT_SECRET` | required | Token signing |
| `JWT_EXPIRE_MINUTES` | 60 | Token TTL |
| `RESERVATION_MINUTES` | 10 | Unpaid hold duration |
| `EXPIRY_JOB_INTERVAL_SECONDS` | 30 | Expiry poll |
| `REDIS_URL` | `redis://redis:6379/0` | Redis |
| `OUTBOX_POLL_SECONDS` | 5 | Worker enqueue interval |
| `OUTBOX_BATCH_SIZE` | 100 | Drain batch size |
| `ORDER_RATE_LIMIT` | 5 | Max place-order / window |
| `ORDER_RATE_WINDOW_SECONDS` | 60 | Rate-limit window |

---

## Roadmap (to finish place → delivered)

1. Fulfillment endpoints: pack / ship / deliver with strict status gates  
2. Consume reserved stock on `paid` → `packed`  
3. Outbox events for packed / shipped / delivered / cancelled  
4. Refund stub on cancel-after-paid (table or outbox only — no real PSP)  
5. Tests for illegal transitions and pack-vs-cancel races  

### Known gaps

- No `packed` / `shipped` / `delivered` APIs yet (enum only)
- Outbox handler is a log stub
- No outbox dead-letter / `failed` status
- Webhook has no signature verification (simulated gateway)
- Cancel after `paid` does not issue a real refund
- `.env` is required locally and not committed
