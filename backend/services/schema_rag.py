"""
Schema Retrieval Service — RAG-based schema context injection.

Instead of dumping the entire database schema into every LLM prompt
(expensive and noisy), we embed table/column descriptions and use
vector similarity search to inject only the relevant schema context.

This dramatically reduces token usage and improves SQL accuracy.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Schema Catalogue
# Each entry describes a table + its most important columns in plain English.
# Business rules and KPI definitions live here too (data dictionary RAG).
# ---------------------------------------------------------------------------

SCHEMA_CATALOGUE = [
    {
        "id": "sales_main",
        "table": "sales",
        "description": (
            "Daily aggregated sales fact table. Use for revenue trends, "
            "profit analysis, units sold, regional performance, and any "
            "time-series or growth analysis. Contains: sale_date (DATE), "
            "region_id (FK), product_id (FK), revenue (DECIMAL), units_sold (INT), "
            "orders_count (INT), profit (DECIMAL), avg_order_value (DECIMAL), "
            "new_customers (INT), returning_customers (INT), refunds (DECIMAL), "
            "marketing_spend (DECIMAL)."
        ),
        "keywords": ["revenue", "sales", "profit", "units", "growth", "trend",
                     "quarterly", "monthly", "yearly", "region", "product", "refund"],
        "join_hints": "JOIN regions ON sales.region_id = regions.id JOIN products ON sales.product_id = products.id",
        "example_sql": "SELECT DATE_TRUNC('month', sale_date) AS month, SUM(revenue) AS revenue FROM sales GROUP BY 1 ORDER BY 1",
    },
    {
        "id": "regions",
        "table": "regions",
        "description": (
            "Geographic regions: North, South, East, West, Central. "
            "Each has a manager and revenue target. "
            "Columns: id, name (VARCHAR), country, timezone, manager_name, target_revenue."
        ),
        "keywords": ["region", "north", "south", "east", "west", "central",
                     "geography", "location", "area", "territory"],
        "join_hints": "",
        "example_sql": "SELECT name FROM regions ORDER BY name",
    },
    {
        "id": "products",
        "table": "products",
        "description": (
            "Product catalogue with pricing. Categories: Software, Services, Hardware. "
            "Sub-categories: Licenses, Add-ons, Legacy, Support, Training, Devices. "
            "Columns: id, sku, name, category, sub_category, unit_price, cost_price, "
            "is_active (BOOLEAN), launch_date (DATE)."
        ),
        "keywords": ["product", "category", "software", "hardware", "service",
                     "price", "sku", "item", "licence", "module", "legacy"],
        "join_hints": "",
        "example_sql": "SELECT name, category, unit_price FROM products WHERE is_active = true",
    },
    {
        "id": "customers",
        "table": "customers",
        "description": (
            "Customer master data with segments: Enterprise, SMB, Consumer. "
            "Columns: id, name, email, segment, region_id (FK), lifetime_value, "
            "churn_risk (low/medium/high), acquisition_channel."
        ),
        "keywords": ["customer", "client", "segment", "enterprise", "smb",
                     "lifetime value", "ltv", "account", "churn"],
        "join_hints": "JOIN regions ON customers.region_id = regions.id",
        "example_sql": "SELECT segment, COUNT(*) AS count, SUM(lifetime_value) AS total_ltv FROM customers GROUP BY segment",
    },
    {
        "id": "orders",
        "table": "orders",
        "description": (
            "Individual orders. Statuses: completed, returned, cancelled. "
            "Columns: id, order_number, customer_id (FK), order_date (DATE), "
            "ship_date, status, total_amount, discount_amount, sales_rep."
        ),
        "keywords": ["order", "aov", "average order", "transaction", "discount",
                     "return", "cancelled", "fulfilment", "status"],
        "join_hints": "JOIN customers ON orders.customer_id = customers.id",
        "example_sql": "SELECT status, COUNT(*) AS cnt, SUM(total_amount) AS amount FROM orders GROUP BY status",
    },
    {
        "id": "order_items",
        "table": "order_items",
        "description": (
            "Line-item detail for each order. "
            "Columns: id, order_id (FK), product_id (FK), quantity, "
            "unit_price, discount_pct (FLOAT 0-1), line_total."
        ),
        "keywords": ["line item", "quantity", "basket", "cart", "sku level", "discount"],
        "join_hints": "JOIN orders ON order_items.order_id = orders.id JOIN products ON order_items.product_id = products.id",
        "example_sql": "SELECT p.name, SUM(oi.quantity) AS total_qty FROM order_items oi JOIN products p ON oi.product_id = p.id GROUP BY p.name",
    },
    {
        "id": "kpi_revenue",
        "table": "sales",
        "description": (
            "KPI: Total Revenue. Use SUM(revenue) FROM sales. "
            "Always add a sale_date range filter. "
            "Use DATE_TRUNC('month', sale_date) or DATE_TRUNC('quarter', sale_date) for time grouping."
        ),
        "keywords": ["total revenue", "kpi", "top line", "gross revenue", "ytd"],
        "join_hints": "",
        "example_sql": "SELECT SUM(revenue) AS total_revenue FROM sales WHERE sale_date BETWEEN '2025-10-01' AND '2025-12-31'",
    },
    {
        "id": "kpi_profit_margin",
        "table": "sales",
        "description": (
            "KPI: Profit Margin. Formula: ROUND((SUM(profit) / NULLIF(SUM(revenue),0)) * 100, 2) AS profit_margin_pct. "
            "ROI = SUM(profit) / NULLIF(SUM(marketing_spend), 0)"
        ),
        "keywords": ["margin", "profit margin", "profitability", "kpi", "roi", "return"],
        "join_hints": "",
        "example_sql": "SELECT ROUND((SUM(profit)/NULLIF(SUM(revenue),0))*100,2) AS profit_margin_pct FROM sales",
    },
]


# ---------------------------------------------------------------------------
# SchemaRetriever
# ---------------------------------------------------------------------------

class SchemaRetriever:
    """
    FAISS-backed semantic search over the schema catalogue.

    On first call, encodes all schema descriptions and builds a FAISS
    flat-L2 index in memory. Subsequent calls do only a vector search.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model = SentenceTransformer(model_name)
        self._index: faiss.IndexFlatL2 | None = None
        self._entries = SCHEMA_CATALOGUE
        self._build_index()

    def _build_index(self) -> None:
        texts = [
            f"{e['description']} {' '.join(e['keywords'])}"
            for e in self._entries
        ]
        embeddings = self._model.encode(texts, show_progress_bar=False)
        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatL2(dim)
        self._index.add(np.array(embeddings, dtype=np.float32))

    def retrieve(self, question: str, top_k: int = 4) -> str:
        """
        Return formatted schema context string for injection into SQL prompt.
        Includes example SQL snippets to improve generation accuracy.
        """
        q_emb = self._model.encode([question], show_progress_bar=False)
        _, indices = self._index.search(
            np.array(q_emb, dtype=np.float32), top_k
        )

        seen_tables: set[str] = set()
        sections: List[str] = []

        for idx in indices[0]:
            if idx >= len(self._entries):
                continue
            entry = self._entries[idx]
            table = entry["table"]
            if table in seen_tables:
                continue
            seen_tables.add(table)
            lines = [
                f"TABLE: {table}",
                f"  Purpose: {entry['description']}",
            ]
            if entry.get("join_hints"):
                lines.append(f"  Join hint: {entry['join_hints']}")
            if entry.get("example_sql"):
                lines.append(f"  Example: {entry['example_sql']}")
            sections.append("\n".join(lines))

        return "\n\n".join(sections)


@lru_cache(maxsize=1)
def get_schema_retriever() -> SchemaRetriever:
    """Singleton — model loads once at startup."""
    return SchemaRetriever()
