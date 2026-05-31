"""Tests for the adapter registry."""

from __future__ import annotations

from app.adapters.base import BaseAdapter
from app.adapters.registry import (
    COUNCIL_ADAPTER_MAP,
    NATIONAL_ADAPTERS,
    STATE_ADAPTER_MAP,
)


class TestAdapterRegistry:
    """Tests for the adapter registry maps."""

    def test_all_states_have_adapter(self):
        expected_states = {"VIC", "NSW", "QLD", "SA", "WA", "TAS", "ACT", "NT"}
        assert set(STATE_ADAPTER_MAP.keys()) == expected_states

    def test_all_state_adapters_inherit_base(self):
        for state, adapter_cls in STATE_ADAPTER_MAP.items():
            assert issubclass(adapter_cls, BaseAdapter), (
                f"{state} adapter {adapter_cls} does not inherit BaseAdapter"
            )

    def test_all_council_adapters_inherit_base(self):
        for name, adapter_cls in COUNCIL_ADAPTER_MAP.items():
            assert issubclass(adapter_cls, BaseAdapter), (
                f"{name} adapter {adapter_cls} does not inherit BaseAdapter"
            )

    def test_national_adapters_exist(self):
        assert len(NATIONAL_ADAPTERS) >= 2

    def test_national_adapters_inherit_base(self):
        for adapter_cls in NATIONAL_ADAPTERS:
            assert issubclass(adapter_cls, BaseAdapter)

    def test_council_adapter_names(self):
        expected_names = {"TechOne_Council", "Objective_Council", "GenericHtml_Council"}
        assert set(COUNCIL_ADAPTER_MAP.keys()) == expected_names
