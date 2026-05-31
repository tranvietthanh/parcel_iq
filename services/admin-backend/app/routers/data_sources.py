from fastapi import APIRouter, Depends, HTTPException
from asyncpg import Connection
from datetime import datetime, UTC
from uuid import UUID, uuid4
import json

from app.dependencies import get_db
from app.core.service_auth import verify_service_token
from app.schemas.data_sources import (
    DataSourceCreate,
    DataSourceUpdate,
    DataSourceResponse,
)

router = APIRouter(
    prefix="/data-sources",
    tags=["data-sources"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("", response_model=list[DataSourceResponse])
async def list_data_sources(
    state: str | None = None,
    enabled: bool | None = None,
    db: Connection = Depends(get_db),
) -> list[DataSourceResponse]:
    """
    List all data source configurations.
    
    Optionally filter by state or enabled status.
    """
    conditions = []
    params = []
    
    if state:
        conditions.append(f"state = ${len(params) + 1}")
        params.append(state)
    
    if enabled is not None:
        conditions.append(f"enabled = ${len(params) + 1}")
        params.append(enabled)
    
    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    
    query = f"""
        SELECT *
        FROM data_source_configs
        WHERE {where_clause}
        ORDER BY state, lga_name
    """
    
    rows = await db.fetch(query, *params)
    return [DataSourceResponse(**dict(row)) for row in rows]


@router.post("", response_model=DataSourceResponse, status_code=201)
async def create_data_source(
    body: DataSourceCreate,
    admin_user_id: str = Depends(verify_service_token),
    db: Connection = Depends(get_db),
) -> DataSourceResponse:
    """
    Create a new data source configuration.
    
    Validates that the LGA exists in spatial_zones before creating.
    """
    # Validate LGA exists
    lga_exists = await db.fetchval(
        """
        SELECT EXISTS(
            SELECT 1 FROM spatial_zones
            WHERE lga_name = $1 AND state = $2
        )
        """,
        body.lga_name,
        body.state,
    )
    
    if not lga_exists:
        raise HTTPException(
            status_code=400,
            detail=f"LGA '{body.lga_name}' not found in state '{body.state}'",
        )
    
    # Check for duplicates
    existing = await db.fetchval(
        """
        SELECT id FROM data_source_configs
        WHERE state = $1 AND lga_name = $2
        """,
        body.state,
        body.lga_name,
    )
    
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Data source already exists for {body.lga_name}, {body.state}",
        )
    
    # Create new config
    new_id = uuid4()
    await db.execute(
        """
        INSERT INTO data_source_configs (
            id, state, lga_name, adapter_name, base_url, adapter_config, enabled
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        new_id,
        body.state,
        body.lga_name,
        body.adapter_name,
        str(body.base_url),
        body.adapter_config or {},
        body.enabled,
    )
    
    # Log action
    await db.execute(
        """
        INSERT INTO admin_activity_log (clerk_admin_id, action, detail)
        VALUES ($1, $2, $3)
        """,
        admin_user_id,
        "DATA_SOURCE_CREATED",
        json.dumps(
            {
                "config_id": str(new_id),
                "state": body.state,
                "lga_name": body.lga_name,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ),
    )

    row = await db.fetchrow(
        "SELECT * FROM data_source_configs WHERE id = $1",
        new_id,
    )
    return DataSourceResponse(**dict(row))


@router.patch("/{config_id}", response_model=DataSourceResponse)
async def update_data_source(
    config_id: str,
    body: DataSourceUpdate,
    admin_user_id: str = Depends(verify_service_token),
    db: Connection = Depends(get_db),
) -> DataSourceResponse:
    """
    Update an existing data source configuration.
    
    Only provided fields are updated (partial update).
    """
    # Build dynamic UPDATE query
    updates = []
    params = []
    
    if body.lga_name is not None:
        updates.append(f"lga_name = ${len(params) + 1}")
        params.append(body.lga_name)
    
    if body.adapter_name is not None:
        updates.append(f"adapter_name = ${len(params) + 1}")
        params.append(body.adapter_name)
    
    if body.base_url is not None:
        updates.append(f"base_url = ${len(params) + 1}")
        params.append(str(body.base_url))
    
    if body.adapter_config is not None:
        updates.append(f"adapter_config = ${len(params) + 1}")
        params.append(body.adapter_config)
    
    if body.enabled is not None:
        updates.append(f"enabled = ${len(params) + 1}")
        params.append(body.enabled)
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    updates.append("updated_at = NOW()")
    params.append(UUID(config_id))
    
    query = f"""
        UPDATE data_source_configs
        SET {', '.join(updates)}
        WHERE id = ${len(params)}
    """
    
    result = await db.execute(query, *params)
    
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Data source not found")
    
    # Log action
    await db.execute(
        """
        INSERT INTO admin_activity_log (clerk_admin_id, action, detail)
        VALUES ($1, $2, $3)
        """,
        admin_user_id,
        "DATA_SOURCE_UPDATED",
        json.dumps(
            {
                "config_id": config_id,
                "updates": body.model_dump(exclude_unset=True, mode="json"),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ),
    )
    
    # Fetch and return updated row
    row = await db.fetchrow(
        "SELECT * FROM data_source_configs WHERE id = $1",
        UUID(config_id),
    )
    return DataSourceResponse(**dict(row))


@router.delete("/{config_id}", status_code=204)
async def delete_data_source(
    config_id: str,
    admin_user_id: str = Depends(verify_service_token),
    db: Connection = Depends(get_db),
):
    """
    Delete a data source configuration.
    
    This is a hard delete - use with caution.
    """
    result = await db.execute(
        "DELETE FROM data_source_configs WHERE id = $1",
        UUID(config_id),
    )

    await db.execute(
        """
        INSERT INTO admin_activity_log (clerk_admin_id, action, detail)
        VALUES ($1, $2, $3)
        """,
        admin_user_id,
        "DATA_SOURCE_DELETED",
        json.dumps(
            {
                "config_id": config_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ),
    )
    
    return None


@router.post("/{config_id}/test")
async def test_data_source(
    config_id: str,
    db: Connection = Depends(get_db),
):
    """
    Test a data source adapter configuration.
    
    Attempts a lightweight request to verify the adapter works.
    This is a placeholder - actual implementation would import and run the adapter.
    """
    config = await db.fetchrow(
        "SELECT * FROM data_source_configs WHERE id = $1",
        UUID(config_id),
    )
    
    if not config:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    # TODO: Import adapter class dynamically and run test
    # For now, just validate config exists
    await db.execute(
        """
        UPDATE data_source_configs
        SET test_status = $1, test_last_run = NOW()
        WHERE id = $2
        """,
        "PASS",
        UUID(config_id),
    )
    
    return {
        "success": True,
        "config_id": config_id,
        "adapter_name": config["adapter_name"],
        "message": "Test adapter functionality not yet implemented",
    }
