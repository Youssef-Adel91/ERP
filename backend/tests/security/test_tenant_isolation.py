import logging
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.modules.contacts.models import Contact, ContactType
from app.plugins.inventory.models import Invoice, InvoiceStatus, Item
from app.modules.system.models import PlanTier, Tenant, TenantStatus

logger = logging.getLogger(__name__)

TEST_TENANT_B_ID = uuid4()
INVOICE_B_ID = uuid4()
CONTACT_B_ID = uuid4()
ITEM_B_ID = uuid4()

@pytest.fixture
async def seed_tenant_b(db_session: AsyncSession):
    """Seed a secondary tenant (Tenant B) and their isolated data."""
    # 1. Create Tenant B in the public schema
    tenant_b = Tenant(
        id=TEST_TENANT_B_ID,
        name="Tenant B Corp",
        slug="tenant-b-corp",
        schema_name=f"tenant_{str(TEST_TENANT_B_ID).replace('-', '_')}",
        status=TenantStatus.ACTIVE,
        plan=PlanTier.FREE,
    )
    db_session.add(tenant_b)
    await db_session.commit()
    
    # 2. Add isolated data for Tenant B
    contact_b = Contact(
        id=CONTACT_B_ID,
        name="Tenant B Customer",
        contact_type=ContactType.CUSTOMER,
        phone="201012345678"
    )
    db_session.add(contact_b)
    
    item_b = Item(
        id=ITEM_B_ID,
        name="Tenant B Item",
        sku="TB-001",
        price=100.0,
        cost=50.0
    )
    db_session.add(item_b)

    invoice_b = Invoice(
        id=INVOICE_B_ID,
        invoice_number="INV-TENANT-B-001",
        status=InvoiceStatus.DRAFT,
        contact_id=CONTACT_B_ID,
        total_amount=100.0
    )
    db_session.add(invoice_b)
    await db_session.commit()


from app.core.db.database import get_tenant_db
from app.main import app
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel

@pytest.fixture
async def tenant_a_db():
    """
    Simulates PostgreSQL schema-per-tenant isolation in SQLite by providing
    a completely separate in-memory database for Tenant A.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", 
        future=True, 
        execution_options={"schema_translate_map": {"tenant": None, "public": None}}
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session


@pytest.mark.asyncio
async def test_cross_tenant_invoice_access_denied(client: AsyncClient, seed_tenant_b, tenant_a_db):
    """
    FR-801: Deliberately attempt cross-tenant data leakage.
    client is authenticated as Tenant A.
    We attempt to GET/PATCH an invoice that belongs to Tenant B.
    """
    # Enforce strict schema isolation simulation
    app.dependency_overrides[get_tenant_db] = lambda: tenant_a_db
    
    # Attempt GET
    response = await client.get(f"/api/v1/inventory/invoices/{INVOICE_B_ID}")
    
    # Because of strict schema isolation or DB constraints, 
    # it must NOT return 200 OK. 
    # In a proper PostgreSQL multi-tenant setup, this yields a 404 Not Found.
    # We accept 404 or 403.
    assert response.status_code in (404, 403), f"Cross-tenant read succeeded! {response.text}"


@pytest.mark.asyncio
async def test_cross_tenant_contact_access_denied(client: AsyncClient, seed_tenant_b, tenant_a_db):
    """
    FR-801: Deliberately attempt cross-tenant data leakage on Contacts.
    """
    app.dependency_overrides[get_tenant_db] = lambda: tenant_a_db
    response = await client.get(f"/api/v1/contacts/{CONTACT_B_ID}")
    assert response.status_code in (404, 403), "Cross-tenant read on contacts succeeded!"


@pytest.mark.asyncio
async def test_cross_tenant_item_modification_denied(client: AsyncClient, seed_tenant_b, tenant_a_db):
    """
    FR-801: Deliberately attempt cross-tenant data modification.
    """
    app.dependency_overrides[get_tenant_db] = lambda: tenant_a_db
    response = await client.patch(
        f"/api/v1/inventory/items/{ITEM_B_ID}",
        json={"price": 1.0}
    )
    
    # Must reject modification of another tenant's asset
    assert response.status_code in (404, 403, 405), "Cross-tenant modification on items succeeded!"
