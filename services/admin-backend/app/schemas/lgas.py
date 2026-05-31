from pydantic import BaseModel


class LGAItem(BaseModel):
    """LGA dropdown item."""

    id: str
    name: str
    state: str
    total_properties: int
    coverage_pct: float  # % with READY reports
