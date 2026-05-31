"""Adapter registry — maps adapter names to classes.

National adapters always run for every property.
State adapters are chosen by the ``state`` field.
Council adapters are chosen by ``data_source_configs.adapter_name``.
"""

from __future__ import annotations

from app.adapters.base import BaseAdapter
from app.adapters.council.generic_html import GenericHtmlCouncilAdapter
from app.adapters.council.objective import ObjectiveCouncilAdapter
from app.adapters.council.tech_one import TechOneCouncilAdapter
from app.adapters.national.abs_census import AbsCensusAdapter
from app.adapters.national.nbnco import NbnCoAdapter
from app.adapters.state.generic_state import GenericStateAdapter
from app.adapters.state.vic_plan import VicPlanAdapter

# ── State-level planning adapter per Australian state ────────────────────────
STATE_ADAPTER_MAP: dict[str, type[BaseAdapter]] = {
    "VIC": VicPlanAdapter,
    "NSW": GenericStateAdapter,
    "QLD": GenericStateAdapter,  # stub until QLD adapter built
    "SA": GenericStateAdapter,
    "WA": GenericStateAdapter,
    "TAS": GenericStateAdapter,
    "ACT": GenericStateAdapter,
    "NT": GenericStateAdapter,
}

# ── Council-level adapter (matched via data_source_configs.adapter_name) ─────
COUNCIL_ADAPTER_MAP: dict[str, type[BaseAdapter]] = {
    "TechOne_Council": TechOneCouncilAdapter,
    "Objective_Council": ObjectiveCouncilAdapter,
    "GenericHtml_Council": GenericHtmlCouncilAdapter,
}

# ── National adapters — always run for every property ────────────────────────
NATIONAL_ADAPTERS: list[type[BaseAdapter]] = [AbsCensusAdapter, NbnCoAdapter]
