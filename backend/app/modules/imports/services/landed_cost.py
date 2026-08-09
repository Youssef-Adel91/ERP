"""
app/modules/imports/services/landed_cost.py — Landed Cost Engine for Imports
"""
from uuid import UUID
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.imports.models.core import ImportDossier, ImportExpense, ImportStatus, DossierCostLayer
from app.modules.inventory.models.core import CostLayer


async def apply_landed_costs(session: AsyncSession, dossier_id: UUID) -> None:
    """
    Sums all ImportExpense records for a dossier and mathematically distributes 
    them across the linked inventory CostLayer records (pro-rated by value).
    Executes entirely within a strict transaction to prevent dirty reads.
    """
    # 1. Fetch dossier & lock it
    result = await session.execute(
        select(ImportDossier)
        .where(ImportDossier.id == dossier_id)
        .with_for_update()
    )
    dossier = result.scalar_one_or_none()
    
    if not dossier:
        raise HTTPException(status_code=404, detail="Dossier not found")
    if dossier.status == ImportStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Dossier is already closed")
    
    # 2. Sum expenses
    # Converting to local currency by applying the fx_rate fixed at dossier level.
    expenses_result = await session.execute(
        select(ImportExpense).where(ImportExpense.dossier_id == dossier_id)
    )
    expenses = expenses_result.scalars().all()
    total_expenses = sum(e.amount for e in expenses) * dossier.fx_rate
    
    # 3. Fetch linked cost layers and lock them
    links_res = await session.execute(
        select(DossierCostLayer).where(DossierCostLayer.dossier_id == dossier_id)
    )
    layer_ids = [link.layer_id for link in links_res.scalars().all()]
    
    if not layer_ids:
        # No physical layers to apply costs to, safely close the dossier without distribution
        dossier.status = ImportStatus.CLOSED
        session.add(dossier)
        return
        
    layers_res = await session.execute(
        select(CostLayer)
        .where(CostLayer.id.in_(layer_ids))
        .with_for_update()
    )
    layers = layers_res.scalars().all()
    
    if not layers:
        dossier.status = ImportStatus.CLOSED
        session.add(dossier)
        return

    # 4. Mathematically distribute by value (qty * original unit cost)
    total_value = sum(l.qty_received * l.unit_cost_original for l in layers)
    total_qty = sum(l.qty_received for l in layers)
    
    for layer in layers:
        if total_value > Decimal("0"):
            layer_value = layer.qty_received * layer.unit_cost_original
            ratio = layer_value / total_value
        else:
            # Fallback to quantity prorating if values are zero
            ratio = layer.qty_received / total_qty if total_qty > Decimal("0") else Decimal("0")
            
        allocated_expense = total_expenses * ratio
        unit_allocated = allocated_expense / layer.qty_received if layer.qty_received > Decimal("0") else Decimal("0")
        
        # Accumulate landed costs
        layer.landed_cost_applied += unit_allocated
        layer.unit_cost_current = layer.unit_cost_original + layer.landed_cost_applied
        
        session.add(layer)
        
    # Mark dossier as closed
    dossier.status = ImportStatus.CLOSED
    session.add(dossier)
