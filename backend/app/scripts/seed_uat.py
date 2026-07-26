"""
UAT Database Seed Script
Run this script to inject realistic initial data into the database for User Acceptance Testing.

Usage:
    cd backend
    python -m app.scripts.seed_uat [tenant_id]
"""

import asyncio
import sys
from decimal import Decimal

from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal, _schema_name
from app.core.security import hash_password
from app.modules.contacts.models import Contact, ContactStatus, ContactType
from app.modules.system.models import Tenant, User, UserRole
from app.plugins.inventory.models import Item


async def main():
    tenant_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    
    print("=========================================")
    print("      Starting UAT Database Seeding      ")
    print("=========================================\n")
    
    # 1. Resolve Tenant & Create Users (Public Schema)
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        
        if tenant_id_arg:
            result = await session.execute(select(Tenant).where(Tenant.id == tenant_id_arg))
            tenant = result.scalar_one_or_none()
            if not tenant:
                print(f"❌ Error: Tenant with ID {tenant_id_arg} not found.")
                return
        else:
            result = await session.execute(select(Tenant).limit(1))
            tenant = result.scalar_one_or_none()
            if not tenant:
                print("❌ Error: No tenant found in the database.")
                print("Please register a tenant first via the API or frontend UI.")
                return
                
        tenant_id = str(tenant.id)
        print(f"🏢 Using Tenant: {tenant.name} (ID: {tenant_id})")
        
        # Test Accounts to Create
        test_accounts = [
            ("sales@uat.com", "Sales Agent", UserRole.SALES),
            ("accounting@uat.com", "Accounting Officer", UserRole.ACCOUNTING),
        ]
        default_password = "Password123!"
        
        print("\n[1] Seeding Test Users...")
        for email, name, role in test_accounts:
            res = await session.execute(select(User).where(User.email == email))
            existing = res.scalar_one_or_none()
            if not existing:
                u = User(
                    tenant_id=tenant.id,
                    email=email,
                    hashed_password=hash_password(default_password),
                    full_name=name,
                    role=role,
                )
                session.add(u)
                print(f"  ✅ Created User: {email} (Role: {role.value})")
            else:
                print(f"  ⏭️  Skipped: User {email} already exists.")
        
        await session.commit()
    
    # 2. Add Contacts & Items (Tenant Schema)
    schema = _schema_name(tenant_id)
    print(f"\n[2] Switching to schema: {schema}")
    
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'SET search_path TO "{schema}", public'))
        
        # ── Seed Contacts ──
        print("    Seeding Contacts...")
        contacts_data = [
            ("المصنع الذهبي للزجاج", ContactType.SUPPLIER, "01000000001"),
            ("شركة الرواد للمقاولات", ContactType.CUSTOMER, "01100000002"),
        ]
        
        for name, c_type, phone in contacts_data:
            res = await session.execute(select(Contact).where(Contact.phone == phone))
            if not res.scalar_one_or_none():
                c = Contact(
                    name=name,
                    name_ar=name,
                    contact_type=c_type,
                    phone=phone,
                    status=ContactStatus.ACTIVE,
                )
                session.add(c)
                print(f"      ✅ Created {c_type.value}: {name}")
            else:
                print(f"      ⏭️  Skipped: Contact with phone {phone} already exists.")
                
        # ── Seed Items (Glass Accessories) ──
        print("    Seeding Inventory Items...")
        items_data = [
            ("مفصلة باب سيكوريت", "SKU-GLS-001", "150.00", "200.00"),
            ("كالون زجاج", "SKU-GLS-002", "300.00", "450.00"),
            ("مقبض ستانلس", "SKU-GLS-003", "80.00", "120.00"),
        ]
        
        for name, sku, cost, price in items_data:
            res = await session.execute(select(Item).where(Item.sku == sku))
            if not res.scalar_one_or_none():
                item = Item(
                    name=name,
                    name_ar=name,
                    sku=sku,
                    cost=Decimal(cost),
                    price=Decimal(price),
                    quantity_on_hand=Decimal("0.000"),
                )
                session.add(item)
                print(f"      ✅ Created Item: {name} (SKU: {sku})")
            else:
                print(f"      ⏭️  Skipped: Item with SKU {sku} already exists.")
                
        await session.commit()
    
    # 3. Print Output Summary
    print("\n🎉 UAT Data Seeded Successfully!")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(" 🔐 TEST ACCOUNTS FOR RBAC TESTING")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Sales User       | Email: sales@uat.com      | Password: {default_password}")
    print(f"  Accounting User  | Email: accounting@uat.com | Password: {default_password}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    
if __name__ == "__main__":
    asyncio.run(main())
