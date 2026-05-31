"""Unit tests for property teaser builder."""

from __future__ import annotations

from app.routers.properties import _build_teaser


class TestBuildTeaser:
    def test_none_insights(self):
        assert _build_teaser(None) is None

    def test_empty_insights(self):
        assert _build_teaser({}) is None

    def test_overlay_detected(self):
        insights = {
            "zoning_and_planning": {
                "overlays": ["HO123", "SLO2"]
            }
        }
        teaser = _build_teaser(insights)
        assert "2 planning overlay(s)" in teaser
        assert "Unlock to view details" in teaser

    def test_flood_risk(self):
        insights = {
            "risk_factors": {
                "flood_risk": "Moderate"
            }
        }
        teaser = _build_teaser(insights)
        assert "Flood risk identified" in teaser

    def test_bushfire_risk(self):
        insights = {
            "risk_factors": {
                "bushfire_risk": "High"
            }
        }
        teaser = _build_teaser(insights)
        assert "Bushfire risk identified" in teaser

    def test_low_risk_no_teaser(self):
        insights = {
            "risk_factors": {
                "flood_risk": "Low",
                "bushfire_risk": "Negligible"
            },
            "zoning_and_planning": {
                "overlays": []
            }
        }
        assert _build_teaser(insights) is None
