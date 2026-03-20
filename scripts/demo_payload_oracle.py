#!/usr/bin/env python3
"""
AXS Ethos Intelligence Suite — Interactive Demo
================================================
Runs all three modules in sequence to demonstrate the full system.

Usage:  python scripts/demo_payload_oracle.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.payload_oracle.physics_model import (
    PayloadOracleEngine, TripProfile, VEHICLE_PLATFORMS, format_analysis_report
)


def demo_family_trip():
    print("\n" + "=" * 55)
    print("  SCENARIO 1: Full Family Trip — Munich → Innsbruck")
    print("=" * 55)

    vehicle = VEHICLE_PLATFORMS["mercedes_eqs_450"]
    engine = PayloadOracleEngine(vehicle)

    trip = TripProfile(
        route_distance_miles=85,
        avg_speed_mph=65,
        passengers=[82, 74, 68, 52, 40],
        luggage_kg=154,
        roof_box=True,
        elevation_gain_m=450,
        ambient_temp_celsius=6.0,
        load_placement="standard",
    )

    analysis = engine.compute(trip)
    print(format_analysis_report(vehicle.name, trip, analysis))


def demo_optimised_trip():
    print("\n" + "=" * 55)
    print("  SCENARIO 2: Same Trip — After AXS Optimisation")
    print("=" * 55)

    vehicle = VEHICLE_PLATFORMS["mercedes_eqs_450"]
    engine = PayloadOracleEngine(vehicle)

    trip = TripProfile(
        route_distance_miles=85,
        avg_speed_mph=65,
        passengers=[82, 74, 68, 52, 40],
        luggage_kg=120,   # Reduced: removed roof box, redistributed luggage
        roof_box=False,
        elevation_gain_m=450,
        ambient_temp_celsius=6.0,
        load_placement="frunk_heavy",
    )

    analysis = engine.compute(trip)
    print(format_analysis_report(vehicle.name, trip, analysis))


def demo_solo_driver():
    print("\n" + "=" * 55)
    print("  SCENARIO 3: Solo Driver — BMW i7 Long Motorway Run")
    print("=" * 55)

    vehicle = VEHICLE_PLATFORMS["bmw_i7_xdrive60"]
    engine = PayloadOracleEngine(vehicle)

    trip = TripProfile(
        route_distance_miles=280,
        avg_speed_mph=80,
        passengers=[85],
        luggage_kg=15,
        roof_box=False,
        elevation_gain_m=150,
        ambient_temp_celsius=22.0,
        load_placement="standard",
    )

    analysis = engine.compute(trip)
    print(format_analysis_report(vehicle.name, trip, analysis))


if __name__ == "__main__":
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║   AXS PAYLOAD ORACLE — Interactive Demo              ║")
    print("║   Ethos Intelligence Suite — Module II               ║")
    print("╚══════════════════════════════════════════════════════╝")

    demo_family_trip()
    demo_optimised_trip()
    demo_solo_driver()

    print("\n✅  Demo complete. See src/payload_oracle/physics_model.py for full implementation.")
