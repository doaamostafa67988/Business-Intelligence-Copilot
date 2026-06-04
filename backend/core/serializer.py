"""
JSON serialization utilities.

PostgreSQL returns Decimal and datetime types that are not natively
JSON serializable. This module provides a recursive sanitizer that
converts all non-serializable types before they enter the LangGraph
state dict or the API response.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def sanitize(obj: Any) -> Any:
    """
    Recursively convert all non-JSON-serializable types to safe equivalents.

    Decimal  → float  (or int if whole number)
    datetime → ISO string
    date     → ISO string
    bytes    → hex string
    sets     → list
    nan/inf  → None  (JSON has no NaN/Infinity)
    """
    if obj is None or isinstance(obj, (bool, str)):
        return obj

    if isinstance(obj, Decimal):
        f = float(obj)
        if math.isnan(f) or math.isinf(f):
            return None
        # Return int if lossless (e.g. Decimal("5000.00") → 5000)
        return int(f) if f == int(f) else f

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    if isinstance(obj, int):
        return obj

    if isinstance(obj, (datetime,)):
        return obj.isoformat()

    if isinstance(obj, date):
        return obj.isoformat()

    if isinstance(obj, bytes):
        return obj.hex()

    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [sanitize(i) for i in obj]

    if isinstance(obj, set):
        return [sanitize(i) for i in obj]

    # Fallback: convert to string so nothing crashes
    return str(obj)
