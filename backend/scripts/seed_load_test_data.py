"""
scripts/seed_load_test_data.py
Seeder for Workstream B (Performance, Load & Capacity) FR-820 - FR-831
Generates high-volume records bypassing logic checks for rapid bulk inserts.
"""

import argparse
import asyncio
import logging
import random
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import insert
from app.core.db.database import tenant_session
from app.modules.contacts.models import Contact, ContactStatus, ContactType
from app.modules.inventory.models.core import CostLayer, StockMovement
from app.modules.sales.models.invoice import SalesInvoice, SalesInvoiceStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("seed_load_test_data")

# --- Constants ---
CHUNK_SIZE = 10_000

# Target Volumes
NUM_CONTACTS = 50_000
NUM_COST_LAYERS = 100_000
NUM_STOCK_MOVEMENTS = 500_000
NUM_INVOICES = 200_000

# Pre-generate some UUIDs for relational data to satisfy loose FK references
ITEM_IDS = [uuid4() for _ in range(500)]
WAREHOUSE_IDS = [uuid4() for _ in range(10)]
ORDER_IDS = [uuid4() for _ in range(5000)]
CONTACT_IDS = [uuid4() for _ in range(1000)]  # Sample to use for invoices/movements


def get_random_date():
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(days=random.randint(1, 365))


async def seed_contacts(session, tenant_id):
    logger.info(f"Seeding {NUM_CONTACTS} Contacts...")
    start = time.time()
    
    total = 0
    while total < NUM_CONTACTS:
        batch_size = min(CHUNK_SIZE, NUM_CONTACTS - total)
        batch = [
            {
                "id": CONTACT_IDS[total % len(CONTACT_IDS)] if total < len(CONTACT_IDS) else uuid4(),
                "contact_type": random.choice(list(ContactType)),
                "status": ContactStatus.ACTIVE,
                "name": f"Load Test Contact {total + i}",
                "name_ar": f"عميل {total + i}",
                "phone": f"+2010{random.randint(1000000, 9999999)}",
                "phone_e164": f"+2010{random.randint(1000000, 9999999)}",
                "cod_risk_score": 0.05,
                "cod_rejection_count": 0,
                "cod_acceptance_count": 10
            }
            for i in range(batch_size)
        ]
        
        await session.execute(insert(Contact), batch)
        total += batch_size
        logger.info(f"  Inserted {total}/{NUM_CONTACTS} Contacts")
        
    await session.commit()
    logger.info(f"Contacts seeded in {time.time() - start:.2f}s")


async def seed_cost_layers(session, tenant_id):
    logger.info(f"Seeding {NUM_COST_LAYERS} Cost Layers...")
    start = time.time()
    
    total = 0
    while total < NUM_COST_LAYERS:
        batch_size = min(CHUNK_SIZE, NUM_COST_LAYERS - total)
        batch = [
            {
                "id": uuid4(),
                "item_id": random.choice(ITEM_IDS),
                "warehouse_id": random.choice(WAREHOUSE_IDS),
                "qty_received": 100.0,
                "qty_remaining": random.uniform(0, 100.0),
                "unit_cost_original": 50.0,
                "unit_cost_current": 50.0,
                "landed_cost_applied": 0.0,
                "is_provisional": False,
                "received_at": get_random_date(),
                "sequence_no": total + i
            }
            for i in range(batch_size)
        ]
        
        await session.execute(insert(CostLayer), batch)
        total += batch_size
        logger.info(f"  Inserted {total}/{NUM_COST_LAYERS} Cost Layers")
        
    await session.commit()
    logger.info(f"Cost Layers seeded in {time.time() - start:.2f}s")


async def seed_stock_movements(session, tenant_id):
    logger.info(f"Seeding {NUM_STOCK_MOVEMENTS} Stock Movements...")
    start = time.time()
    
    total = 0
    while total < NUM_STOCK_MOVEMENTS:
        batch_size = min(CHUNK_SIZE, NUM_STOCK_MOVEMENTS - total)
        batch = [
            {
                "id": uuid4(),
                "item_id": random.choice(ITEM_IDS),
                "warehouse_id": random.choice(WAREHOUSE_IDS),
                "qty": random.choice([10.0, -5.0, 1.0, -1.0]),
                "movement_type": random.choice(["IN", "OUT"]),
                "reference_id": f"REF-{total + i}",
                "contact_id": random.choice(CONTACT_IDS),
                "occurred_at": get_random_date(),
                "created_at": get_random_date(),
                "updated_at": get_random_date()
            }
            for i in range(batch_size)
        ]
        
        await session.execute(insert(StockMovement), batch)
        total += batch_size
        logger.info(f"  Inserted {total}/{NUM_STOCK_MOVEMENTS} Stock Movements")
        
    await session.commit()
    logger.info(f"Stock Movements seeded in {time.time() - start:.2f}s")


async def seed_invoices(session, tenant_id):
    logger.info(f"Seeding {NUM_INVOICES} Sales Invoices...")
    start = time.time()
    
    total = 0
    while total < NUM_INVOICES:
        batch_size = min(CHUNK_SIZE, NUM_INVOICES - total)
        batch = [
            {
                "id": uuid4(),
                "invoice_number": f"INV-{uuid4().hex[:8].upper()}-{total + i}",
                "order_id": random.choice(ORDER_IDS),
                "contact_id": random.choice(CONTACT_IDS),
                "status": random.choice(list(SalesInvoiceStatus)),
                "issue_date": get_random_date().date(),
                "due_date": (get_random_date() + timedelta(days=30)).date(),
                "currency": "EGP",
                "subtotal": 1000.0,
                "tax_total": 140.0,
                "grand_total": 1140.0,
                "created_at": get_random_date(),
                "updated_at": get_random_date()
            }
            for i in range(batch_size)
        ]
        
        await session.execute(insert(SalesInvoice), batch)
        total += batch_size
        logger.info(f"  Inserted {total}/{NUM_INVOICES} Sales Invoices")
        
    await session.commit()
    logger.info(f"Sales Invoices seeded in {time.time() - start:.2f}s")


async def run_seed(tenant_id: str):
    logger.info(f"Starting Realistic Data Seeding for Tenant: {tenant_id}")
    overall_start = time.time()
    
    async with tenant_session(tenant_id) as session:
        # Disable foreign key checks momentarily for pure bulk data ingestion performance
        # if using SQLite: await session.execute(text("PRAGMA foreign_keys = OFF"))
        # if using Postgres: we rely on deferrable constraints or order of ops
        
        await seed_contacts(session, tenant_id)
        await seed_cost_layers(session, tenant_id)
        await seed_stock_movements(session, tenant_id)
        await seed_invoices(session, tenant_id)
        
    logger.info(f"Total Seeding Completed in {time.time() - overall_start:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load Test Data Seeder")
    parser.add_argument("--tenant-id", type=str, required=True, help="Target Tenant UUID")
    args = parser.parse_args()
    
    asyncio.run(run_seed(args.tenant_id))
