from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int, db_session=None) -> Decimal:
    """
    Calculates revenue for a specific month, using the property's local
    timezone to decide which month a check-in belongs to.
    """
    from app.core.database_pool import db_pool
    from sqlalchemy import text

    # Local (naive) month boundaries; compared against check_in_date
    # converted to the property's timezone.
    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)

    print(f"DEBUG: Querying revenue for {property_id} from {start_date} to {end_date}")

    query = text("""
        SELECT SUM(r.total_amount) as total
        FROM reservations r
        JOIN properties p ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
        AND r.tenant_id = :tenant_id
        AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_date
        AND (r.check_in_date AT TIME ZONE p.timezone) < :end_date
    """)

    # Initialize the shared pool only if it is not ready yet
    if not db_pool.session_factory:
        await db_pool.initialize()

    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        })
        total = result.scalar()

    return Decimal(str(total)) if total is not None else Decimal('0')

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.

    Database errors propagate to the caller instead of being replaced by
    fabricated numbers, so the API can answer 503 and nothing gets cached.
    """
    from app.core.database_pool import db_pool
    from sqlalchemy import text

    # Initialize the shared pool only if it is not ready yet
    if not db_pool.session_factory:
        await db_pool.initialize()

    async with db_pool.get_session() as session:
        query = text("""
            SELECT
                property_id,
                SUM(total_amount) as total_revenue,
                COUNT(*) as reservation_count
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
            GROUP BY property_id
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id
        })
        row = result.fetchone()

    if row:
        total_revenue = Decimal(str(row.total_revenue))
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(total_revenue),
            "currency": "USD",
            "count": row.reservation_count
        }

    # No reservations found for this property
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": "0.00",
        "currency": "USD",
        "count": 0
    }
