"""
app/scripts/cutover_plugins_to_modules.py — Inventory/Sales/Purchasing cutover
(plugins/ -> modules/), Phase 2 of the migration plan.

WARNING: DESTRUCTIVE. Drops the retired app.plugins.{inventory,sales,purchases}
tables from a tenant schema. Intended for dev environments with no data worth
preserving, per the explicit go-ahead to do a destructive drop+recreate.

What this does, per tenant schema:
  1. DROP TABLE (CASCADE) the seven retired plugins/ tables, if present:
     invoice_lines, invoices, items, sales_invoice_lines, sales_invoices,
     purchase_invoice_lines, purchase_invoices.
     (invoice_lines/sales_invoice_lines/purchase_invoice_lines dropped first
     since they FK into the parent tables.)
  2. Re-run the real tenant provisioning routine
     (app.core.db.database._provision_tenant_schema_internal's table-creation
     step) so every app.modules.{inventory,sales,purchasing} table defined in
     the current `tenant_tables` list gets created. This is additive/
     idempotent — CREATE TABLE IF NOT EXISTS semantics via SQLAlchemy
     create_all — so it's safe to re-run.

Usage:
    cd backend
    python -m app.scripts.cutover_plugins_to_modules <tenant_id> [<tenant_id> ...]
    python -m app.scripts.cutover_plugins_to_modules --all-tenants

This connects to whatever DATABASE_URL is configured in your environment —
it does not run inside the agent sandbox (no DB there). Review the table
list below before running against anything other than a disposable dev DB.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.core.db.context import schema_for
from app.core.db.database import engine, _provision_tenant_schema_internal

# Retired app.plugins.{inventory,sales,purchases} tables, drop order matters:
# child (FK-bearing) tables before parent tables.
RETIRED_TABLES = [
    "invoice_lines",           # FK -> invoices, items
    "sales_invoice_lines",     # FK -> sales_invoices, items
    "purchase_invoice_lines",  # FK -> purchase_invoices, items
    "invoices",                # FK -> contacts
    "sales_invoices",          # FK -> contacts
    "purchase_invoices",       # FK -> contacts
    "items",
]


async def cutover_tenant(tenant_id: str) -> None:
    schema = schema_for(tenant_id)
    print(f"\n── Tenant {tenant_id} (schema: {schema}) ──")

    async with engine.begin() as conn:
        for table in RETIRED_TABLES:
            print(f"  Dropping {schema}.{table} (if exists)...")
            await conn.execute(text(f'DROP TABLE IF EXISTS "{schema}"."{table}" CASCADE'))
    print("  ✅ Retired plugins/ tables dropped.")

    print("  Re-provisioning modules/ tables...")
    # seed_coa=False: this tenant already has its Chart of Accounts from its
    # original provisioning — re-seeding would violate Account.code's unique
    # constraint. Only the table-creation step (idempotent, CREATE TABLE IF
    # NOT EXISTS semantics) runs here.
    await _provision_tenant_schema_internal(tenant_id, seed_coa=False)
    print("  ✅ modules/ tables created (Item, Warehouse, SalesOrder, SalesInvoice, "
          "PurchaseOrder, VendorBill, LandedCost*, and the rest of the tenant_tables list).")


async def list_all_tenant_ids() -> list[str]:
    from sqlalchemy import select
    from app.core.db.database import AsyncSessionLocal
    from app.modules.system.models import Tenant

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Tenant.id))
        return [str(row[0]) for row in result.all()]


async def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--all-tenants":
        tenant_ids = await list_all_tenant_ids()
        if not tenant_ids:
            print("No tenants found in public.tenants — nothing to do.")
            return
        print(f"Found {len(tenant_ids)} tenant(s): {tenant_ids}")
    else:
        tenant_ids = sys.argv[1:]

    for tenant_id in tenant_ids:
        await cutover_tenant(tenant_id)

    print("\n🎉 Cutover complete for all specified tenants.")


if __name__ == "__main__":
    asyncio.run(main())
