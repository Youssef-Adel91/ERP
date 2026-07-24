# Omni ERP — Modular ERP & Trust Network Platform

**Backend foundation for a multi-tenant, event-driven ERP system tailored for Egyptian merchants.**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                         │
│                                                                  │
│  ┌──────────────┐  ┌────────────────────────────────────────┐   │
│  │  TenantMW    │  │         API Routers (/api/v1)          │   │
│  │ (JWT decode) │  │  /system  /accounting  /contacts       │   │
│  │ search_path  │  │  /inventory  /shipping                 │   │
│  └──────────────┘  └────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                      EventBus                            │   │
│  │  InMemoryEventBus (dev) │ RedisEventBus (prod+Celery)    │   │
│  │                                                          │   │
│  │  Plugins EMIT:           Core HANDLES:                   │   │
│  │  invoice.created    →    create + post journal entry     │   │
│  │  payment.received   →    clear receivable account        │   │
│  │  contact.created    →    (future: Neo4j node creation)   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
          │                                    │
          ▼                                    ▼
┌──────────────────────┐           ┌─────────────────────────┐
│     PostgreSQL       │           │          Redis           │
│                      │           │                          │
│  public schema:      │           │  Refresh tokens (7d TTL) │
│    tenants           │           │  EventBus pub/sub        │
│    users             │           │  Celery task queue       │
│    subscriptions     │           └─────────────────────────┘
│                      │
│  tenant_* schemas:   │
│    accounts          │
│    journal_entries   │
│    transaction_lines │  ← PostgreSQL trigger enforces
│    contacts          │    sum(debit) == sum(credit)
│    contact_rels      │  ← Neo4j-ready for Trust Network
│    products          │
│    sale_invoices     │
└──────────────────────┘
```

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### 2. Install Dependencies

```bash
cd backend
pip install -e ".[dev]"
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL, REDIS_URL, SECRET_KEY
```

### 4. Run Database Migrations

```bash
# Creates public schema tables (tenants, users, subscriptions)
alembic upgrade head
```

### 5. Start the Dev Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Explore the API

Open **http://localhost:8000/docs** → FastAPI interactive documentation.

---

## Key Design Decisions

### Multi-Tenancy: Schema-per-Tenant

Every merchant gets an isolated PostgreSQL schema (`tenant_{uuid}`).

```sql
-- Before any query in a tenant request:
SET search_path TO tenant_abc123, public;
-- All ORM operations automatically target this tenant's tables
```

**No row-level tenant_id filtering needed** — isolation is enforced by the database engine.

### Double-Entry Accounting (Dual Enforcement)

Balance enforcement is **two-layered**:

| Layer | Mechanism | Catches |
|---|---|---|
| **Pydantic** | `model_validator` on `JournalEntryCreateRequest` | Bad API payloads |
| **Service** | `UnbalancedEntryError` before `db.commit()` | Programmatic bugs |
| **PostgreSQL** | `trg_enforce_journal_balance` trigger | Any direct DB writes |

### EventBus: Zero Coupling Between Modules

```
Inventory Plugin              Accounting Core
      │                             │
      │  emit("invoice.created")    │
      │ ──────────────────────────► │
      │                             │ handle_invoice_created()
      │                             │ → create_draft_journal_entry()
      │                             │ → post_journal_entry()
      │                             │
```

The inventory plugin has **zero imports** from `app.modules.accounting`.
The accounting module has **zero imports** from `app.plugins.inventory`.

### Neo4j Readiness

Contact models are annotated with comments that document future graph export:

```python
# NEO4J_NODE_LABEL: Contact
# NEO4J_EXPORT_FIELDS: [id, name, contact_type, phone, cod_risk_score]
# NEO4J_NODE_ID: phone  ← natural key for deduplication across tenants

# NEO4J_EDGE_TYPE: TRADED_WITH
# NEO4J_EDGE_PROPERTIES: [transaction_count, cod_rejection_rate, weight]
```

---

## Project Structure

```
backend/
├── app/
│   ├── core/
│   │   ├── config.py       # Pydantic Settings (reads .env)
│   │   ├── database.py     # Async engine, TenantMiddleware, session deps
│   │   ├── security.py     # JWT + bcrypt + Redis refresh tokens
│   │   └── event_bus.py    # InMemory + Redis EventBus
│   ├── modules/
│   │   ├── system/         # PUBLIC SCHEMA: Tenants, Users, Auth
│   │   ├── accounting/     # TENANT SCHEMA: Accounts, Journal Entries
│   │   └── contacts/       # TENANT SCHEMA: Customers, Suppliers (Neo4j-ready)
│   ├── plugins/
│   │   ├── inventory/      # Products, Sale Invoices (emits events)
│   │   └── shipping/       # Stub — coming next sprint
│   └── main.py             # App factory + middleware + router wiring
├── alembic/
│   ├── env.py              # Custom multi-schema runner
│   └── versions/
│       ├── 001_initial_public_schema.py
│       └── 002_initial_tenant_schema.py  ← includes PG trigger
├── tests/
│   ├── conftest.py         # Fixtures: SQLite in-memory, seeded data
│   ├── test_accounting.py  # Double-entry constraint tests (9 cases)
│   └── test_event_bus.py   # Pub/Sub round-trip tests (6 cases)
├── pyproject.toml
└── .env.example
```

---

## Running Tests

```bash
# All tests with coverage report
pytest tests/ -v --cov=app --cov-report=term-missing

# Accounting constraint tests only
pytest tests/test_accounting.py -v

# EventBus round-trip tests
pytest tests/test_event_bus.py -v
```

---

## API Endpoints Summary

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/system/tenants/register` | None | Register tenant + first admin |
| `POST` | `/api/v1/system/auth/login` | None | Login, get JWT tokens |
| `POST` | `/api/v1/system/auth/refresh` | None | Refresh access token |
| `POST` | `/api/v1/system/auth/logout` | Bearer | Revoke session |
| `POST` | `/api/v1/system/auth/logout-all` | Bearer | Force-logout all sessions |
| `GET` | `/api/v1/accounting/accounts` | Bearer | Chart of Accounts |
| `POST` | `/api/v1/accounting/accounts` | Bearer+accountant | Create account |
| `GET` | `/api/v1/accounting/accounts/{id}/balance` | Bearer | Account balance |
| `POST` | `/api/v1/accounting/journal-entries` | Bearer+accountant | Create DRAFT entry |
| `POST` | `/api/v1/accounting/journal-entries/{id}/post` | Bearer+accountant | Post entry |
| `POST` | `/api/v1/accounting/journal-entries/{id}/reverse` | Bearer+accountant | Reversing entry |
| `GET` | `/api/v1/contacts/` | Bearer | List contacts |
| `POST` | `/api/v1/contacts/` | Bearer | Create contact |
| `POST` | `/api/v1/contacts/relationships` | Bearer | Create graph edge |
| `GET` | `/api/v1/inventory/products` | Bearer | List products |
| `POST` | `/api/v1/inventory/invoices` | Bearer | Create invoice (triggers EventBus) |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `SECRET_KEY` | — | JWT signing key (generate with `openssl rand -hex 64`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime in Redis |
| `EVENT_BUS_BACKEND` | `memory` | `"memory"` or `"redis"` |
| `ENVIRONMENT` | `development` | `development`, `staging`, `production` |

---

## Roadmap

- [ ] **COD Risk Assessment Plugin** — Phone-based fraud scoring using transaction history
- [ ] **Omnichannel Chat Plugin** — WhatsApp/Messenger integration
- [ ] **Neo4j Trust Network** — Export contacts/relationships as graph, compute community scores
- [ ] **Egyptian Arabic NLP** — Voice note processing for COD confirmation calls
- [ ] **Celery Worker** — Replace in-memory EventBus with production Redis worker
- [ ] **Multi-currency** — Exchange rates and currency conversion for journal entries
- [ ] **Financial Reports** — Trial Balance, Income Statement, Balance Sheet
