"""
app.modules.finance.api — Finance API Routes (COD Settlements, Aging)
"""
from app.modules.finance.api.settlements import router as settlements_router

__all__ = ["settlements_router"]
