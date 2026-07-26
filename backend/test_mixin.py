from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, func
from sqlmodel import Field, SQLModel, create_engine


class BaseMixin(SQLModel):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False))

class PublicBase(BaseMixin):
    pass

class Tenant(PublicBase, table=True):
    __tablename__ = "tenants"
    name: str

engine = create_engine("sqlite:///:memory:")
SQLModel.metadata.create_all(engine)
print("Tables:", SQLModel.metadata.tables.keys())
for table in SQLModel.metadata.tables.values():
    print(table.name, [c.name for c in table.columns])
