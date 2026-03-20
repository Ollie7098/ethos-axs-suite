"""
Acoustic Resurrection Engine — DSP Engine Prototype
=====================================================
Models the acoustic transfer function that maps EV motor telemetry
to the corresponding audio characteristics of a Heritage ICE engine profile.

AXS Ethos Intelligence Suite — Module I
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class MotorTelemetry:
    """Real-time EV motor state (sampled at ~100Hz in production)."""
    torque_nm: float          # Current motor torque output
    power_kw: float           # Current motor power draw
    regen_active: bool        # True if regenerative braking is active
    regen_torque_nm: float    # Regen braking torque
    speed_kph: float          # Current vehicle speed
    throttle_position_pct: float  # 0-100: driver demand
    acceleration_ms2: float   # Current longitudinal acceleration


@dataclass
class HeritageProfile:
    """
    Acoustic profile configuration for a specific ICE engine topology.
    Defines the transfer function parameters used by the DSP engine.
    """
    profile_id: str
    display_name: str
    engine_topology: str       # e.g., "V8_NA", "V12_TT", "F6_GT3"
    tier: str                  # "classic" | "v12_symphony" | "motorsport"

    # RPM-equivalent mapping
    idle_rpm_equivalent: float     # EV torque state that maps to ICE idle
    max_rpm_equivalent: float      # EV torque state that maps to ICE redline

    # Acoustic character parameters
    fundamental_freq_hz: float     # Base firing frequency at "idle"
    harmonic_series: List[float]   # Relative amplitudes of harmonics [H1, H2, H3, H4]
    induction_noise_db: float      # Induction roar contribution
    exhaust_resonance_hz: float    # Primary exhaust resonance frequency
    exhaust_bark_on_lift: bool     # Overrun/decel "pop" enabled
    vibration_freq_hz: float       # Steering/seat haptic frequency at idle

    # Emotion curve: maps RPM-equivalent % to audio character intensity
    # List of (rpm_pct, intensity_multiplier) tuples
    emotion_curve: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class AcousticOutput:
    """
    The DSP engine output at a given motor state.
    In production, this feeds the audio DSP and haptic controllers.
    """
    rpm_equivalent: float           # Computed RPM equivalent (0 to max_rpm)
    rpm_pct: float                  # % of redline
    fundamental_freq_hz: float      # Current fundamental firing frequency
    active_harmonics: Dict[str, float]  # Harmonic freq → amplitude (dB)
    exhaust_resonance_hz: float     # Active exhaust resonance
    induction_level_db: float       # Induction noise level
    haptic_frequency_hz: float      # Haptic output frequency
    haptic_intensity_pct: float     # Haptic intensity (0-100%)
    overrun_bark_active: bool       # Decel pop triggered?
    character_description: str      # Human-readable state


# ─────────────────────────────────────────────
# Heritage Profile Library
# ─────────────────────────────────────────────

HERITAGE_PROFILES: Dict[str, HeritageProfile] = {
    "v8_na_classic": HeritageProfile(
        profile_id="v8_na_classic",
        display_name="V8 Naturally Aspirated — Classic",
        engine_topology="V8_NA",
        tier="classic",
        idle_rpm_equivalent=800,
        max_rpm_equivalent=7200,
        fundamental_freq_hz=26.7,   # 800 RPM / 60 * 4 cylinders firing per rev / 2
        harmonic_series=[1.0, 0.6, 0.35, 0.18],
        induction_noise_db=42.0,
        exhaust_resonance_hz=85.0,
        exhaust_bark_on_lift=True,
        vibration_freq_hz=28.0,
        emotion_curve=[
            (0.0, 0.5), (0.2, 0.6), (0.5, 0.8), (0.7, 1.0), (0.9, 1.3), (1.0, 1.5)
        ],
    ),
    "v12_biturbo_symphony": HeritageProfile(
        profile_id="v12_biturbo_symphony",
        display_name="V12 Biturbo Symphony Pack",
        engine_topology="V12_TT",
        tier="v12_symphony",
        idle_rpm_equivalent=700,
        max_rpm_equivalent=7000,
        fundamental_freq_hz=35.0,   # V12: 6 firing events per rev
        harmonic_series=[1.0, 0.5, 0.25, 0.12, 0.06],
        induction_noise_db=38.0,    # Turbos suppress induction noise
        exhaust_resonance_hz=68.0,  # Lower, deeper resonance
        exhaust_bark_on_lift=True,
        vibration_freq_hz=22.0,     # Smoother, lower vibration
        emotion_curve=[
            (0.0, 0.4), (0.3, 0.55), (0.6, 0.8), (0.8, 1.1), (0.95, 1.4), (1.0, 1.6)
        ],
    ),
    "f6_gt3_motorsport": HeritageProfile(
        profile_id="f6_gt3_motorsport",
        display_name="GT3 Flat-Six Motorsport Edition",
        engine_topology="F6_GT3",
        tier="motorsport",
        idle_rpm_equivalent=3000,   # GT3 engines idle high
        max_rpm_equivalent=9200,
        fundamental_freq_hz=100.0,  # High-revving, 3 firing events per rev
        harmonic_series=[1.0, 0.8, 0.55, 0.30, 0.15],  # Rich harmonic content
        induction_noise_db=62.0,    # Prominent induction roar
        exhaust_resonance_hz=180.0, # High-frequency motorsport crackle
        exhaust_bark_on_lift=True,
        vibration_freq_hz=55.0,     # High-frequency motorsport vibration
        emotion_curve=[
            (0.0, 0.7), (0.3, 0.9), (0.6, 1.2), (0.8, 1.5), (0.95, 1.8), (1.0, 2.0)
        ],
    ),
}


# ─────────────────────────────────────────────
# DSP Engine
# ─────────────────────────────────────────────

class AcousticDSPEngine:
    """
    The Acoustic Resurrection Engine DSP core.

    In production:
    - Runs on the vehicle's High-Performance Compute unit
    - Processes motor telemetry at ~100Hz sample rate
    - Outputs audio coefficients to the speaker DSP processor
    - Outputs haptic parameters to steering wheel and seat actuators

    This prototype demonstrates the transfer function logic.
    """

    def __init__(self, profile: HeritageProfile):
        self.profile = profile
        self._prev_rpm_pct = 0.0

    def process(self, telemetry: MotorTelemetry) -> AcousticOutput:
        """Compute acoustic output for the current motor state."""

        # 1. Compute RPM-equivalent from motor torque and speed
        rpm_equivalent = self._compute_rpm_equivalent(telemetry)
        rpm_pct = rpm_equivalent / self.profile.max_rpm_equivalent

        # 2. Compute emotion curve multiplier
        emotion = self._interpolate_emotion(rpm_pct)

        # 3. Compute current fundamental frequency (scales with RPM)
        current_fundamental = (
            self.profile.fundamental_freq_hz
            * (rpm_equivalent / self.profile.idle_rpm_equivalent)
        )

        # 4. Build harmonic spectrum
        harmonics = {}
        for i, amp in enumerate(self.profile.harmonic_series, 1):
            freq = current_fundamental * i
            # Apply emotion multiplier and slight randomisation for organic character
            adjusted_amp_db = (
                20 * math.log10(max(amp * emotion, 0.001))
                + (i * -3.0)  # Natural harmonic rolloff
            )
            harmonics[f"H{i}_{freq:.1f}Hz"] = round(adjusted_amp_db, 1)

        # 5. Induction noise scales with throttle demand
        induction_db = (
            self.profile.induction_noise_db
            * (telemetry.throttle_position_pct / 100)
            * emotion
        )

        # 6. Exhaust resonance
        exhaust_hz = self.profile.exhaust_resonance_hz * (0.85 + rpm_pct * 0.15)

        # 7. Haptic parameters
        haptic_freq = self.profile.vibration_freq_hz * (rpm_pct ** 0.6)
        haptic_intensity = min(rpm_pct * 120 * emotion, 100)

        # 8. Overrun bark: triggered on rapid throttle lift at medium-high RPM
        rpm_drop = self._prev_rpm_pct - rpm_pct
        overrun = (
            self.profile.exhaust_bark_on_lift
            and rpm_drop > 0.08
            and rpm_pct > 0.35
            and not telemetry.regen_active
        )
        self._prev_rpm_pct = rpm_pct

        # 9. Character description
        character = self._describe_character(rpm_pct, telemetry, overrun)

        return AcousticOutput(
            rpm_equivalent=round(rpm_equivalent),
            rpm_pct=round(rpm_pct, 3),
            fundamental_freq_hz=round(current_fundamental, 1),
            active_harmonics=harmonics,
            exhaust_resonance_hz=round(exhaust_hz, 1),
            induction_level_db=round(induction_db, 1),
            haptic_frequency_hz=round(haptic_freq, 1),
            haptic_intensity_pct=round(haptic_intensity, 1),
            overrun_bark_active=overrun,
            character_description=character,
        )

    def _compute_rpm_equivalent(self, tel: MotorTelemetry) -> float:
        """
        Maps EV motor state to an ICE RPM-equivalent.
        Uses a combined torque-demand and speed model:
        - At low speeds: RPM tracks throttle demand (inertia feel)
        - At high speeds: RPM tracks speed (road-load feel)
        """
        max_rpm = self.profile.max_rpm_equivalent
        idle_rpm = self.profile.idle_rpm_equivalent

        speed_component = (tel.speed_kph / 250.0) * max_rpm * 0.5
        torque_component = (tel.throttle_position_pct / 100.0) * max_rpm * 0.5

        raw = idle_rpm + speed_component + torque_component
        return max(idle_rpm, min(raw, max_rpm))

    def _interpolate_emotion(self, rpm_pct: float) -> float:
        """Linear interpolation over the emotion curve."""
        curve = self.profile.emotion_curve
        if rpm_pct <= curve[0][0]:
            return curve[0][1]
        if rpm_pct >= curve[-1][0]:
            return curve[-1][1]
        for i in range(len(curve) - 1):
            x0, y0 = curve[i]
            x1, y1 = curve[i + 1]
            if x0 <= rpm_pct <= x1:
                t = (rpm_pct - x0) / (x1 - x0)
                return y0 + t * (y1 - y0)
        return 1.0

    def _describe_character(self, rpm_pct: float, tel: MotorTelemetry, overrun: bool) -> str:
        if overrun:
            return "⚡ Overrun — exhaust bark active"
        if rpm_pct < 0.15:
            return "🟢 Idle burble — low, settled character"
        if rpm_pct < 0.35:
            return "🔵 Pulling away — smooth torque swell"
        if rpm_pct < 0.60:
            return "🟡 Mid-range surge — character building"
        if rpm_pct < 0.80:
            return "🟠 Hard acceleration — full voice engaged"
        return "🔴 Near redline — full acoustic drama"


# ─────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════╗")
    print("║   AXS — Acoustic Resurrection Engine Demo        ║")
    print("╚══════════════════════════════════════════════════╝\n")

    profile = HERITAGE_PROFILES["v8_na_classic"]
    engine = AcousticDSPEngine(profile)

    print(f"  Active Profile: {profile.display_name}\n")

    scenarios = [
        ("Idle at traffic light",    MotorTelemetry(torque_nm=0,   power_kw=0,   regen_active=False, regen_torque_nm=0,  speed_kph=0,   throttle_position_pct=0,   acceleration_ms2=0.0)),
        ("Gentle pull-away",         MotorTelemetry(torque_nm=120, power_kw=18,  regen_active=False, regen_torque_nm=0,  speed_kph=30,  throttle_position_pct=25,  acceleration_ms2=1.2)),
        ("Mid-range acceleration",   MotorTelemetry(torque_nm=350, power_kw=95,  regen_active=False, regen_torque_nm=0,  speed_kph=90,  throttle_position_pct=65,  acceleration_ms2=3.5)),
        ("Hard acceleration",        MotorTelemetry(torque_nm=650, power_kw=290, regen_active=False, regen_torque_nm=0,  speed_kph=140, throttle_position_pct=90,  acceleration_ms2=6.8)),
        ("Throttle lift / overrun",  MotorTelemetry(torque_nm=80,  power_kw=10,  regen_active=False, regen_torque_nm=0,  speed_kph=130, throttle_position_pct=8,   acceleration_ms2=-2.1)),
    ]
    # Prime the previous RPM for overrun detection
    engine._prev_rpm_pct = 0.75

    for label, tel in scenarios:
        out = engine.process(tel)
        print(f"  ── {label} {'─' * max(0, 40 - len(label))}")
        print(f"     RPM-Equiv: {out.rpm_equivalent:,} ({out.rpm_pct*100:.0f}% of redline)")
        print(f"     State:     {out.character_description}")
        print(f"     Haptic:    {out.haptic_frequency_hz:.0f} Hz @ {out.haptic_intensity_pct:.0f}% intensity")
        if out.overrun_bark_active:
            print(f"     🎯  OVERRUN BARK FIRED")
        print()
