#!/usr/bin/env python3
"""
AXS Ethos Intelligence Suite — ARE Demo
========================================
Demonstrates the Acoustic Resurrection Engine across all Heritage Profiles.

Usage:  python scripts/demo_are_profile.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.are.dsp_engine import AcousticDSPEngine, MotorTelemetry, HERITAGE_PROFILES


SCENARIOS = [
    ("Idle",          MotorTelemetry(0,   0,   False, 0,  0,   0,  0.0),  0.0),
    ("Gentle pull",   MotorTelemetry(120, 18,  False, 0,  30,  25, 1.2),  0.0),
    ("Motorway cruise",MotorTelemetry(180, 55,  False, 0,  110, 35, 0.5),  0.0),
    ("Hard push",     MotorTelemetry(680, 310, False, 0,  155, 92, 7.1),  0.0),
    ("Throttle lift", MotorTelemetry(60,  8,   False, 0,  140, 5,  -2.5), 0.8),
]

if __name__ == "__main__":
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║   AXS ACOUSTIC RESURRECTION ENGINE — Demo            ║")
    print("║   Ethos Intelligence Suite — Module I                ║")
    print("╚══════════════════════════════════════════════════════╝")

    for profile_id, profile in HERITAGE_PROFILES.items():
        engine = AcousticDSPEngine(profile)
        print(f"\n{'═' * 55}")
        print(f"  🎵  {profile.display_name.upper()}")
        print(f"  Tier: {profile.tier.replace('_', ' ').title()}  |  Topology: {profile.engine_topology}")
        print(f"{'═' * 55}")

        for label, tel, prev_rpm in SCENARIOS:
            engine._prev_rpm_pct = prev_rpm
            out = engine.process(tel)
            bark = "  💥 OVERRUN BARK" if out.overrun_bark_active else ""
            print(f"  [{label:<18}]  RPM: {out.rpm_equivalent:>5,}  Haptic: {out.haptic_frequency_hz:>5.1f}Hz @ {out.haptic_intensity_pct:>4.0f}%{bark}")
            print(f"   └─ {out.character_description}")

    print(f"\n✅  ARE Demo complete. See src/are/dsp_engine.py for DSP transfer function implementation.")
