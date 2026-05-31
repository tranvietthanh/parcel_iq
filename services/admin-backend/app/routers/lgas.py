from fastapi import APIRouter, Depends
from asyncpg import Connection

from app.dependencies import get_db
from app.core.service_auth import verify_service_token
from app.schemas.lgas import LGAItem

router = APIRouter(
    prefix="/lgas",
    tags=["lgas"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("", response_model=list[LGAItem])
async def list_lgas(
    state: str | None = None,
    db: Connection = Depends(get_db),
) -> list[LGAItem]:
    """
    Get list of LGAs for dropdown population.
    
    Optionally filter by state.
    Includes property count and coverage percentage for each LGA.
    """
    conditions = []
    params = []
    
    if state:
        conditions.append(f"sz.state = ${len(params) + 1}")
        params.append(state)
    
    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    
    query = f"""
        SELECT 
            sz.id::text AS id,
            sz.name,
            sz.state,
            COUNT(DISTINCT p.id) AS total_properties,
            COALESCE(
                ROUND(
                    100.0 * COUNT(DISTINCT CASE WHEN pr.status = 'READY' THEN p.id END) 
                    / NULLIF(COUNT(DISTINCT p.id), 0),
                    1
                ),
                0
            ) AS coverage_pct
        FROM spatial_zones sz
        LEFT JOIN properties p ON p.lga_id = sz.id
        LEFT JOIN property_reports pr ON pr.property_id = p.id
        WHERE sz.zone_type = 'LGA' AND {where_clause}
        GROUP BY sz.id, sz.name, sz.state
        ORDER BY sz.state, sz.name
    """
    
    rows = await db.fetch(query, *params)
    return [LGAItem(**dict(row)) for row in rows]
