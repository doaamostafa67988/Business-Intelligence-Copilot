"""
Database seeder — creates schema and seeds realistic demo data.

Run:  python -m db.seed

Data covers 2023-01-01 → 2025-12-31 to support Q4 2025 queries
from the use-case example. Includes intentional anomalies and
underperforming products to make the analysis agents interesting.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from core.config import get_settings
from db.models import (
    Base,
    Customer,
    Order,
    OrderItem,
    Product,
    QueryAuditLog,
    Region,
    Sale,
)

settings = get_settings()
engine = create_engine(settings.database_sync_url)

random.seed(42)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rand_decimal(lo: float, hi: float, dp: int = 2) -> Decimal:
    return Decimal(str(round(random.uniform(lo, hi), dp)))


def date_range(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

REGIONS = [
    {"name": "North", "country": "US", "timezone": "America/Chicago"},
    {"name": "South", "country": "US", "timezone": "America/New_York"},
    {"name": "East",  "country": "US", "timezone": "America/New_York"},
    {"name": "West",  "country": "US", "timezone": "America/Los_Angeles"},
    {"name": "Central", "country": "US", "timezone": "America/Chicago"},
]

PRODUCTS = [
    # (sku, name, category, sub_category, unit_price, cost_price)
    ("PRD-001", "Enterprise License Pro",   "Software",  "Licenses",    1200.00, 200.00),
    ("PRD-002", "Enterprise License Basic",  "Software",  "Licenses",     600.00, 100.00),
    ("PRD-003", "Analytics Module",          "Software",  "Add-ons",      400.00,  80.00),
    ("PRD-004", "Support Package Premium",   "Services",  "Support",      800.00, 150.00),
    ("PRD-005", "Support Package Standard",  "Services",  "Support",      300.00,  60.00),
    ("PRD-006", "Training Bundle",           "Services",  "Training",     250.00,  50.00),
    ("PRD-007", "Hardware Gateway",          "Hardware",  "Devices",      950.00, 500.00),
    ("PRD-008", "Hardware Sensor Kit",       "Hardware",  "Devices",      350.00, 180.00),
    # Product X — intentionally underperforming in Q4 2025
    ("PRD-009", "Product X Legacy Module",   "Software",  "Legacy",       500.00, 300.00),
    ("PRD-010", "Cloud Connector",           "Software",  "Add-ons",      700.00, 120.00),
]

SEGMENTS = ["Enterprise", "SMB", "Consumer"]
STATUSES = ["completed", "completed", "completed", "returned", "cancelled"]


def revenue_multiplier(d: date, region_name: str, product_sku: str) -> float:
    """
    Inject realistic patterns:
    - North: strong performer, slight Q4 dip in 2025
    - East: high volatility (anomaly detection target)
    - Product X: 15% decline in Q4 2025
    - Seasonal uplift in November/December
    """
    mult = 1.0
    # Seasonal
    if d.month in (11, 12):
        mult *= 1.25
    if d.month in (1, 2):
        mult *= 0.85

    # Region patterns
    if region_name == "North":
        mult *= 1.35
        if d >= date(2025, 10, 1):
            mult *= 0.82   # Q4 2025 North dip — intentional for insights
    elif region_name == "East":
        # Add volatility noise
        mult *= random.choice([0.6, 0.8, 1.0, 1.4, 1.7])
    elif region_name == "South":
        mult *= 0.90
    elif region_name == "West":
        mult *= 1.10
        if d >= date(2025, 1, 1):
            mult *= 1.15   # West growing in 2025

    # Product X decline in Q4 2025
    if product_sku == "PRD-009" and d >= date(2025, 10, 1):
        mult *= 0.70

    # YoY growth baseline
    if d.year == 2024:
        mult *= 1.12
    elif d.year == 2025:
        mult *= 1.18

    return max(mult, 0.1)


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

def seed_all() -> None:
    print("Creating tables...")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        # --- Regions ---
        print("Seeding regions...")
        regions = []
        for r in REGIONS:
            obj = Region(**r)
            db.add(obj)
            regions.append(obj)
        db.flush()

        # --- Products ---
        print("Seeding products...")
        products = []
        for sku, name, cat, sub, price, cost in PRODUCTS:
            obj = Product(
                sku=sku, name=name, category=cat, sub_category=sub,
                unit_price=Decimal(str(price)), cost_price=Decimal(str(cost))
            )
            db.add(obj)
            products.append(obj)
        db.flush()

        # --- Customers ---
        print("Seeding customers...")
        customers = []
        for i in range(500):
            region = random.choice(regions)
            obj = Customer(
                name=f"Company {i+1:04d}",
                email=f"contact{i+1}@company{i+1}.com",
                segment=random.choice(SEGMENTS),
                region_id=region.id,
                lifetime_value=rand_decimal(1000, 150000),
                created_at=datetime(2023, 1, 1) + timedelta(days=random.randint(0, 365)),
            )
            db.add(obj)
            customers.append(obj)
        db.flush()

        # --- Orders + Order Items ---
        print("Seeding orders (this takes a moment)...")
        order_counter = 1
        for _ in range(4000):
            customer = random.choice(customers)
            order_date = date(2023, 1, 1) + timedelta(days=random.randint(0, 1095))
            n_items = random.randint(1, 4)
            selected_products = random.sample(products, k=n_items)

            total = Decimal("0")
            items_data = []
            for prod in selected_products:
                qty = random.randint(1, 10)
                disc = round(random.choice([0, 0, 0.05, 0.10, 0.15]), 2)
                line = Decimal(str(float(prod.unit_price) * qty * (1 - disc))).quantize(Decimal("0.01"))
                total += line
                items_data.append((prod, qty, disc, line))

            order = Order(
                order_number=f"ORD-{order_counter:06d}",
                customer_id=customer.id,
                order_date=order_date,
                ship_date=order_date + timedelta(days=random.randint(1, 7)),
                status=random.choice(STATUSES),
                total_amount=total,
                discount_amount=rand_decimal(0, float(total) * 0.1),
            )
            db.add(order)
            db.flush()

            for prod, qty, disc, line in items_data:
                db.add(OrderItem(
                    order_id=order.id,
                    product_id=prod.id,
                    quantity=qty,
                    unit_price=prod.unit_price,
                    discount_pct=disc,
                    line_total=line,
                ))

            order_counter += 1

        db.commit()

        # --- Sales Fact Table ---
        print("Seeding sales fact table (2023-2025)...")
        start = date(2023, 1, 1)
        end   = date(2025, 12, 31)

        sales_batch = []
        for d in date_range(start, end):
            for region in regions:
                for product in products:
                    mult = revenue_multiplier(d, region.name, product.sku)
                    base_units = random.randint(1, 20)
                    units = max(1, int(base_units * mult))
                    revenue = Decimal(str(round(float(product.unit_price) * units * mult, 2)))
                    profit  = Decimal(str(round(float(product.unit_price - product.cost_price) * units * mult * 0.8, 2)))
                    sales_batch.append(Sale(
                        sale_date=d,
                        region_id=region.id,
                        product_id=product.id,
                        revenue=revenue,
                        units_sold=units,
                        orders_count=max(1, units // 3),
                        profit=profit,
                        avg_order_value=Decimal(str(round(float(revenue) / max(1, units // 3), 2))),
                        new_customers=random.randint(0, 3),
                        returning_customers=random.randint(0, 8),
                    ))

            if len(sales_batch) >= 2000:
                db.add_all(sales_batch)
                db.flush()
                sales_batch = []

        if sales_batch:
            db.add_all(sales_batch)

        db.commit()
        print(f"✅ Seed complete. Sales rows: ~{1095 * 5 * 10:,}")


if __name__ == "__main__":
    seed_all()
