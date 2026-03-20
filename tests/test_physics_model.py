"""
Unit Tests — Payload Oracle Physics Model
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from src.payload_oracle.physics_model import (
    PayloadOracleEngine, TripProfile, VEHICLE_PLATFORMS
)

@pytest.fixture
def eqs_engine():
    return PayloadOracleEngine(VEHICLE_PLATFORMS["mercedes_eqs_450"])

def test_solo_driver_near_baseline(eqs_engine):
    """Solo driver with minimal luggage should be close to rated range."""
    trip = TripProfile(route_distance_miles=100, avg_speed_mph=65,
                       passengers=[80], luggage_kg=5)
    result = eqs_engine.compute(trip)
    penalty_pct = result.payload_penalty_pct
    assert penalty_pct < 5.0, f"Solo driver penalty too high: {penalty_pct}%"

def test_full_load_penalty_in_range(eqs_engine):
    """Fully loaded vehicle should show 10-20% range penalty."""
    trip = TripProfile(route_distance_miles=100, avg_speed_mph=65,
                       passengers=[85, 75, 70, 55, 45], luggage_kg=160)
    result = eqs_engine.compute(trip)
    assert 8.0 <= result.payload_penalty_pct <= 22.0, \
        f"Full load penalty {result.payload_penalty_pct}% outside expected range"

def test_roof_box_penalty_positive(eqs_engine):
    """Roof box should always increase penalty."""
    base_trip = TripProfile(route_distance_miles=100, avg_speed_mph=70,
                            passengers=[80], luggage_kg=20, roof_box=False)
    box_trip = TripProfile(route_distance_miles=100, avg_speed_mph=70,
                           passengers=[80], luggage_kg=20, roof_box=True)
    base_result = eqs_engine.compute(base_trip)
    box_result = eqs_engine.compute(box_trip)
    assert box_result.payload_adjusted_range_miles < base_result.payload_adjusted_range_miles

def test_frunk_heavy_improves_range(eqs_engine):
    """Frunk-heavy placement should improve range vs standard."""
    std_trip = TripProfile(route_distance_miles=100, avg_speed_mph=65,
                           passengers=[80, 75], luggage_kg=80, load_placement="standard")
    frunk_trip = TripProfile(route_distance_miles=100, avg_speed_mph=65,
                             passengers=[80, 75], luggage_kg=80, load_placement="frunk_heavy")
    std_result = eqs_engine.compute(std_trip)
    frunk_result = eqs_engine.compute(frunk_trip)
    assert frunk_result.payload_adjusted_range_miles > std_result.payload_adjusted_range_miles

def test_shortfall_flagged_correctly(eqs_engine):
    """Trip longer than adjusted range should flag shortfall."""
    trip = TripProfile(route_distance_miles=340, avg_speed_mph=65,
                       passengers=[85, 78, 72, 60, 45], luggage_kg=180)
    result = eqs_engine.compute(trip)
    assert not result.can_complete_trip
    assert result.range_shortfall_miles > 0

def test_recommendations_not_empty(eqs_engine):
    """Recommendations should always be provided."""
    trip = TripProfile(route_distance_miles=80, avg_speed_mph=60,
                       passengers=[80, 70], luggage_kg=50)
    result = eqs_engine.compute(trip)
    assert len(result.recommendations) > 0
