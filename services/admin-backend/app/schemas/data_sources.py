from typing import Any
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl


class DataSourceCreate(BaseModel):
    """Request to create a new data source config."""

    state: str = Field(..., min_length=2, max_length=3)
    lga_name: str = Field(..., min_length=1, max_length=100)
    adapter_name: str = Field(..., description="Python class name (e.g. VictoriaPlanningAdapter)")
    base_url: HttpUrl
    adapter_config: dict[str, Any] | None = Field(default_factory=dict)
    enabled: bool = True


class DataSourceUpdate(BaseModel):
    """Request to update an existing data source config."""

    lga_name: str | None = None
    adapter_name: str | None = None
    base_url: HttpUrl | None = None
    adapter_config: dict[str, Any] | None = None
    enabled: bool | None = None


class DataSourceResponse(BaseModel):
    """Data source config response."""

    id: str
    state: str
    lga_name: str
    adapter_name: str
    base_url: str
    adapter_config: dict[str, Any]
    enabled: bool
    test_status: str | None
    created_at: datetime
    updated_at: datetime
