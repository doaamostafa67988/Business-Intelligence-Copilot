"""
Database Layer — SQLAlchemy async engine + ORM models.

Tables mirror a realistic B2B SaaS / retail company:
  regions → customers → orders → order_items → products
  sales (pre-aggregated fact table for fast analytics)
  conversation_sessions (for memory persistence)
  query_audit_log (immutable audit trail of every SQL executed)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import AsyncGenerator

from sqlalchemy import (
    DECIMAL, TEXT, BigInteger, Boolean, Column, Date, DateTime,
    Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    echo=settings.app_env == "development",
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Business Domain Tables
# ---------------------------------------------------------------------------

class Region(Base):
    __tablename__ = "regions"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    country = Column(String(100), default="US")
    timezone = Column(String(50), default="UTC")
    manager_name = Column(String(200))           # Improvement: richer seed data
    target_revenue = Column(DECIMAL(14, 2))      # Improvement: KPI targets
    created_at = Column(DateTime, default=datetime.utcnow)

    customers = relationship("Customer", back_populates="region")
    sales = relationship("Sale", back_populates="region")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    sku = Column(String(50), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    category = Column(String(100))
    sub_category = Column(String(100))
    unit_price = Column(DECIMAL(12, 2), nullable=False)
    cost_price = Column(DECIMAL(12, 2), nullable=False)
    is_active = Column(Boolean, default=True)
    launch_date = Column(Date)                   # Improvement: product lifecycle
    end_of_life_date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)

    order_items = relationship("OrderItem", back_populates="product")
    sales = relationship("Sale", back_populates="product")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    email = Column(String(200), unique=True)
    segment = Column(String(50))    # Enterprise | SMB | Consumer
    region_id = Column(Integer, ForeignKey("regions.id"))
    lifetime_value = Column(DECIMAL(14, 2), default=0)
    churn_risk = Column(String(20), default="low")   # Improvement: churn tracking
    acquisition_channel = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    region = relationship("Region", back_populates="customers")
    orders = relationship("Order", back_populates="customer")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    order_number = Column(String(50), unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    order_date = Column(Date, nullable=False)
    ship_date = Column(Date)
    status = Column(String(50), default="completed")
    total_amount = Column(DECIMAL(14, 2), nullable=False)
    discount_amount = Column(DECIMAL(14, 2), default=0)
    sales_rep = Column(String(200))              # Improvement: sales attribution
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer, nullable=False)
    unit_price = Column(DECIMAL(12, 2), nullable=False)
    discount_pct = Column(Float, default=0.0)
    line_total = Column(DECIMAL(14, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")


class Sale(Base):
    """
    Pre-aggregated daily fact table for fast analytics queries.
    This is the primary table the SQL Agent queries for trends.
    """
    __tablename__ = "sales"
    __table_args__ = (
        UniqueConstraint("sale_date", "region_id", "product_id", name="uq_sale_fact"),
        Index("ix_sales_date_region", "sale_date", "region_id"),
        Index("ix_sales_date_product", "sale_date", "product_id"),
    )

    id = Column(BigInteger, primary_key=True)
    sale_date = Column(Date, nullable=False, index=True)
    region_id = Column(Integer, ForeignKey("regions.id"), index=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)
    revenue = Column(DECIMAL(14, 2), nullable=False)
    units_sold = Column(Integer, nullable=False)
    orders_count = Column(Integer, nullable=False)
    profit = Column(DECIMAL(14, 2), nullable=False)
    avg_order_value = Column(DECIMAL(12, 2))
    new_customers = Column(Integer, default=0)
    returning_customers = Column(Integer, default=0)
    refunds = Column(DECIMAL(14, 2), default=0)      # Improvement: refund tracking
    marketing_spend = Column(DECIMAL(12, 2), default=0)  # Improvement: ROI calcs

    region = relationship("Region", back_populates="sales")
    product = relationship("Product", back_populates="sales")


# ---------------------------------------------------------------------------
# Platform Meta Tables
# ---------------------------------------------------------------------------

class ConversationSession(Base):
    """Persisted memory for the conversational BI assistant."""
    __tablename__ = "conversation_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_identifier = Column(String(200), index=True)
    turns = Column(JSONB, default=list)
    context_summary = Column(Text, default="")
    last_entities = Column(JSONB, default=dict)
    last_sql_snapshot = Column(JSONB, nullable=True)
    last_analysis_snapshot = Column(JSONB, nullable=True)  # Improvement
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class QueryAuditLog(Base):
    """
    Immutable audit trail — every SQL query executed is recorded here.
    Critical for compliance and debugging in production.
    """
    __tablename__ = "query_audit_log"

    id = Column(BigInteger, primary_key=True)
    session_id = Column(String(36), index=True)
    user_message = Column(Text)
    generated_sql = Column(Text)
    sql_confidence = Column(Float)
    row_count = Column(Integer)
    execution_ms = Column(Integer)
    approved_by_human = Column(Boolean, default=False)
    had_error = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    intent = Column(String(50))        # Improvement: track intent distribution
    agent_trace = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
