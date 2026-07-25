# OrderFlow

**A concurrency-safe order fulfillment backend for e-commerce.**

OrderFlow simulates the full lifecycle of a customer order — from placement to delivery or cancellation — the way a real production backend would need to handle it: safely, reliably, and without losing data when things go wrong.

---

## The Problem

Any e-commerce backend has to solve three hard problems at the same time:

1. **Inventory correctness under concurrent load** — when hundreds of customers try to buy the same limited-stock item at once, the system must never oversell.
2. **Payment safety under unreliable networks** — payment webhooks can arrive twice, arrive late, or arrive out of order. Each payment must be processed exactly once, no matter how many times the notification is sent.
3. **Reliable, non-blocking side effects** — sending confirmations, updating inventory ledgers, and triggering notifications should never slow down checkout, and should never be lost if a background worker crashes mid-task....

OrderFlow is built specifically to solve these three problems, not just to build another CRUD app.

---

## How It Works

### Order Lifecycle

```
placed → paid → packed → shipped → delivered
   |       |
   └───► cancelled
```

- Orders **reserve inventory** the moment they're placed.
- Unpaid reservations **auto-expire after 10 minutes**, releasing stock back to available inventory.
- Orders can contain **multiple line items** — reservation and payment are all-or-nothing across the whole order.
- **Cancellation** is only allowed while an order is `placed` or `paid`. Once an order is `packed`, it can no longer be cancelled (returns are a future feature).

### Solving Overselling

Inventory is tracked with two separate counters instead of one:

```
quantity_available   quantity_reserved
```

A reservation is a single atomic update:

```sql
UPDATE inventory
SET quantity_available = quantity_available - n,
    quantity_reserved   = quantity_reserved + n
WHERE quantity_available >= n
```

Because the check and the update happen in one atomic database operation, stock can never go negative — even under heavy concurrent traffic — and no extra locking is needed.

### Solving Duplicate Payments

Payment webhooks are made idempotent using a **database-level unique constraint** on `gateway_event_id`. If the same webhook is delivered twice, the second attempt is rejected by the database itself — not by application logic — which removes an entire category of race conditions.

### Solving Reliable Side Effects

OrderFlow uses the **transactional outbox pattern**. Every side effect (like sending a notification) is written to an `outbox_events` table in the *same database transaction* as the order or payment change. A background worker then picks up pending events and processes them asynchronously. If the worker crashes mid-task, no event is ever lost — it simply gets picked up again on restart.

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| API Framework | **FastAPI** | Fast, async-first, and gives clean automatic API docs |
| Database | **PostgreSQL** | Strong transactional guarantees and constraint enforcement |
| DB Access | **Raw SQL** (psycopg / asyncpg) | No ORM — used deliberately for explicit, transparent transaction control |
| Background Worker | **Redis + RQ** | Simpler to reason about than Celery, while still supporting the outbox pattern |
| Auth | **JWT** | Stateless authentication for the REST API |
| API Docs | **FastAPI's built-in Swagger UI** | Auto-generated, always in sync with the code |
| Containerization | **Docker + docker-compose** | Consistent local and deployment environments |
| Deployment | **Render / Railway** | Simple hosting for a portfolio-scale service |

---

## Database Schema

- **users** — id, email (unique), password_hash, created_at
- **products** — id, name, price, sku (unique), created_at
- **inventory** — id, product_id (FK, unique), quantity_available, quantity_reserved
- **orders** — id, user_id (FK), status, total_amount, created_at, expires_at
- **order_items** — id, order_id (FK), product_id (FK), quantity, unit_price_at_purchase
- **payment_events** — id, order_id (FK), gateway_event_id (unique), status, received_at
- **outbox_events** — id, event_type, payload (JSON), status, created_at

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/signup` | Create a new user account |
| `POST` | `/auth/login` | Authenticate and receive a JWT |
| `GET` | `/products` | List all products with available stock |
| `GET` | `/products/:id` | Get details for a single product |
| `POST` | `/orders` | Place a new order (all-or-nothing reservation) |
| `GET` | `/orders/:id` | Retrieve order status and details |
| `POST` | `/orders/:id/cancel` | Cancel an order (only if `placed` or `paid`) |
| `POST` | `/webhooks/payment` | Receive payment confirmation from the gateway (idempotent) |

Order placement is **rate-limited per user** (e.g. 5 requests/minute) to prevent abuse.

The payment webhook always returns `200 OK` — even for unrecognized orders — to avoid triggering retry storms from the payment gateway. Unexpected cases are logged internally as anomalies instead of surfaced as errors.

---

## Running Locally

```bash
# Clone the repository
git clone https://github.com/<your-username>/orderflow.git
cd orderflow

# Start all services (API + PostgreSQL + Redis)
docker-compose up --build

# API docs available at:
# http://localhost:8000/docs
```

---

## Testing

The project includes tests for the hardest edge cases by design, including:

- Concurrent purchase attempts on limited-stock items
- Duplicate payment webhook delivery
- Reservation expiry and stock release

---

## Project Status

This is an actively developed portfolio project, built from an empty repository to demonstrate backend engineering fundamentals — concurrency control, idempotency, and reliable async processing — using well-established patterns as reference rather than existing codebases.

---

## License

