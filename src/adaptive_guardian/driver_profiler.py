"""
Adaptive Guardian AI — Driver Profiler
=======================================
Maintains a continuously-learning Driver Score model per registered driver.
Processes journey telemetry to update profile, identify blind spots, and
return a chassis configuration recommendation.

AXS Ethos Intelligence Suite — Module III
"""

from __future__ import annotations
import json
import math
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from datetime import datetime


# ─────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────

@dataclass
class JourneyTelemetry:
    """
    Telemetry snapshot from a single journey, ingested from the CAN bus.
    All values represent aggregated statistics for the journey.
    """
    journey_id: str
    timestamp: str

    # Braking
    avg_brake_reaction_time_ms: float     # ms from hazard detection to brake input
    emergency_brake_events: int           # Threshold: >0.6g deceleration
    smooth_braking_score: float           # 0.0 (abrupt) to 1.0 (smooth) 

    # Acceleration
    smooth_acceleration_score: float      # 0.0 to 1.0
    torque_demand_variance: float         # Low = smooth, high = aggressive

    # Lane Keeping
    lane_departure_events: int            # Count per 100 miles
    avg_lateral_deviation_cm: float       # Average deviation from lane centre

    # Gap Management
    avg_following_distance_s: float       # Time headway in seconds (>2.0 = good)
    tailgating_events: int                # Count of <1.0s following distance

    # ADAS Response
    avg_adas_alert_response_ms: float     # ms to respond to ADAS alert
    adas_ignored_events: int              # Count of ignored ADAS alerts

    # Gaze
    eyes_off_road_events: int             # Count of >1.5s off-road gaze
    max_gaze_off_road_duration_ms: float  # Longest single off-road gaze

    # Route context
    urban_miles: float
    highway_miles: float
    night_miles: float


@dataclass
class DriverBlindSpot:
    """A specific, learned vulnerability pattern for a driver."""
    category: str                      # e.g., "left_rear_cyclist", "roundabout_entry"
    confidence: float                  # 0.0 to 1.0 (increases with more data)
    event_count: int
    description: str
    aga_mitigation: str               # How the AGA compensates


@dataclass
class DriverProfile:
    """
    The persistent Driver Score Profile maintained per registered driver.
    Updated after every journey via incremental weighted averaging.
    """
    driver_id: str
    display_name: str
    created_at: str
    last_updated: str
    total_journeys: int = 0
    total_miles: float = 0.0

    # Core score dimensions (0-100, higher = more skilled/experienced)
    score_braking: float = 50.0
    score_acceleration: float = 50.0
    score_lane_keeping: float = 50.0
    score_gap_management: float = 50.0
    score_hazard_response: float = 50.0
    score_attention: float = 50.0

    # Composite score
    composite_score: float = 50.0

    # Classification
    classification: str = "Intermediate"   # Novice | Intermediate | Proficient | Expert

    # Learned blind spots
    blind_spots: List[DriverBlindSpot] = field(default_factory=list)

    # Journey history (last 20 composite scores for trend)
    score_history: List[float] = field(default_factory=list)


@dataclass
class ChassisConfiguration:
    """
    The Digital Chassis configuration to apply for this driver session.
    Returned by the AGA system based on Driver Profile.
    """
    driver_id: str
    classification: str
    composite_score: float

    # Braking
    brake_prefill_sensitivity: str    # "high" | "standard" | "minimal"
    brake_advisory_threshold_g: float # Deceleration at which advisory triggers

    # Acceleration
    torque_ramp_profile: str          # "gradual" | "standard" | "immediate"
    launch_control_enabled: bool

    # Speed
    soft_speed_limit_mph: Optional[int]  # None = no limit

    # Alerts
    alert_modality: str               # "all" | "visual_haptic" | "haptic_only"
    lane_departure_sensitivity: str   # "high" | "standard"
    blind_spot_sensitivity_pct: int   # % expansion of standard warning zone

    # Gaze Monitoring
    gaze_alert_threshold_ms: int      # ms of off-road gaze before haptic alert

    # Customised mitigations from blind spots
    custom_mitigations: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────
# Scoring Engine
# ─────────────────────────────────────────────

class DriverScoreEngine:
    """
    Incremental, weighted-average scoring engine.
    New journeys are weighted more heavily as data accumulates,
    creating a recency bias that rewards improvement.
    """

    # Classification thresholds
    CLASSIFICATIONS = [
        (80, "Expert"),
        (65, "Proficient"),
        (45, "Intermediate"),
        (0,  "Novice"),
    ]

    # Dimension weights for composite score
    WEIGHTS = {
        "braking":        0.25,
        "acceleration":   0.15,
        "lane_keeping":   0.20,
        "gap_management": 0.20,
        "hazard_response":0.10,
        "attention":      0.10,
    }

    def score_journey(self, telemetry: JourneyTelemetry) -> Dict[str, float]:
        """Convert raw telemetry to 0-100 dimension scores for one journey."""

        # Braking score
        reaction_score = self._clamp(
            100 - ((telemetry.avg_brake_reaction_time_ms - 200) / 8), 0, 100
        )
        eb_penalty = min(telemetry.emergency_brake_events * 8, 40)
        braking = self._clamp(
            reaction_score * 0.5
            + telemetry.smooth_braking_score * 100 * 0.3
            - eb_penalty * 0.2, 0, 100
        )

        # Acceleration score
        accel_variance_score = self._clamp(100 - telemetry.torque_demand_variance * 50, 0, 100)
        acceleration = (
            telemetry.smooth_acceleration_score * 100 * 0.6
            + accel_variance_score * 0.4
        )

        # Lane keeping score
        deviation_score = self._clamp(100 - telemetry.avg_lateral_deviation_cm * 2.5, 0, 100)
        departure_penalty = min(telemetry.lane_departure_events * 10, 50)
        lane_keeping = self._clamp(deviation_score - departure_penalty, 0, 100)

        # Gap management score
        headway_score = self._clamp(
            (telemetry.avg_following_distance_s - 1.0) / 2.0 * 100, 0, 100
        )
        tailgate_penalty = min(telemetry.tailgating_events * 12, 60)
        gap_management = self._clamp(headway_score - tailgate_penalty, 0, 100)

        # Hazard response score
        response_score = self._clamp(
            100 - ((telemetry.avg_adas_alert_response_ms - 400) / 12), 0, 100
        )
        ignored_penalty = min(telemetry.adas_ignored_events * 15, 60)
        hazard_response = self._clamp(response_score - ignored_penalty, 0, 100)

        # Attention score
        gaze_penalty = min(telemetry.eyes_off_road_events * 8, 60)
        duration_penalty = min((telemetry.max_gaze_off_road_duration_ms - 1500) / 100, 20)
        attention = self._clamp(100 - gaze_penalty - max(0, duration_penalty), 0, 100)

        return {
            "braking":         round(braking, 1),
            "acceleration":    round(acceleration, 1),
            "lane_keeping":    round(lane_keeping, 1),
            "gap_management":  round(gap_management, 1),
            "hazard_response": round(hazard_response, 1),
            "attention":       round(attention, 1),
        }

    def compute_composite(self, scores: Dict[str, float]) -> float:
        return round(sum(
            scores[k] * v for k, v in self.WEIGHTS.items()
        ), 1)

    def classify(self, composite: float) -> str:
        for threshold, label in self.CLASSIFICATIONS:
            if composite >= threshold:
                return label
        return "Novice"

    @staticmethod
    def _clamp(val: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, val))


# ─────────────────────────────────────────────
# Profile Manager
# ─────────────────────────────────────────────

class DriverProfileManager:
    """
    Manages the lifecycle of Driver Profiles:
    - Create new profiles at first vehicle registration
    - Update incrementally after each journey
    - Detect and register blind spots
    - Emit ChassisConfiguration for active session
    """

    LEARNING_RATE_INITIAL = 0.40   # High influence for first 10 journeys
    LEARNING_RATE_ESTABLISHED = 0.12  # Lower influence once model is established
    ESTABLISHED_THRESHOLD = 10

    def __init__(self):
        self.scorer = DriverScoreEngine()
        self._profiles: Dict[str, DriverProfile] = {}

    def register_driver(self, driver_id: str, display_name: str) -> DriverProfile:
        profile = DriverProfile(
            driver_id=driver_id,
            display_name=display_name,
            created_at=datetime.utcnow().isoformat(),
            last_updated=datetime.utcnow().isoformat(),
        )
        self._profiles[driver_id] = profile
        return profile

    def update_from_journey(self, driver_id: str, telemetry: JourneyTelemetry) -> DriverProfile:
        """Process a completed journey and update the driver's profile."""
        if driver_id not in self._profiles:
            raise ValueError(f"Driver {driver_id} not registered.")

        profile = self._profiles[driver_id]
        journey_scores = self.scorer.score_journey(telemetry)
        journey_composite = self.scorer.compute_composite(journey_scores)

        # Determine learning rate based on journey count
        lr = (
            self.LEARNING_RATE_INITIAL
            if profile.total_journeys < self.ESTABLISHED_THRESHOLD
            else self.LEARNING_RATE_ESTABLISHED
        )

        # Weighted incremental update
        profile.score_braking      = profile.score_braking      * (1 - lr) + journey_scores["braking"]         * lr
        profile.score_acceleration = profile.score_acceleration * (1 - lr) + journey_scores["acceleration"]     * lr
        profile.score_lane_keeping = profile.score_lane_keeping * (1 - lr) + journey_scores["lane_keeping"]     * lr
        profile.score_gap_management = profile.score_gap_management * (1 - lr) + journey_scores["gap_management"] * lr
        profile.score_hazard_response = profile.score_hazard_response * (1 - lr) + journey_scores["hazard_response"] * lr
        profile.score_attention    = profile.score_attention    * (1 - lr) + journey_scores["attention"]        * lr

        profile.composite_score = self.scorer.compute_composite({
            "braking":         profile.score_braking,
            "acceleration":    profile.score_acceleration,
            "lane_keeping":    profile.score_lane_keeping,
            "gap_management":  profile.score_gap_management,
            "hazard_response": profile.score_hazard_response,
            "attention":       profile.score_attention,
        })
        profile.classification = self.scorer.classify(profile.composite_score)
        profile.total_journeys += 1
        profile.total_miles += telemetry.urban_miles + telemetry.highway_miles + telemetry.night_miles
        profile.score_history.append(round(journey_composite, 1))
        if len(profile.score_history) > 20:
            profile.score_history.pop(0)

        self._detect_blind_spots(profile, telemetry)
        profile.last_updated = datetime.utcnow().isoformat()
        return profile

    def _detect_blind_spots(self, profile: DriverProfile, tel: JourneyTelemetry):
        """Heuristic blind spot detection — real system would use fleet ML models."""
        existing_categories = {bs.category for bs in profile.blind_spots}

        if tel.eyes_off_road_events > 3 and "frequent_inattention" not in existing_categories:
            profile.blind_spots.append(DriverBlindSpot(
                category="frequent_inattention",
                confidence=min(0.3 + tel.eyes_off_road_events * 0.1, 1.0),
                event_count=tel.eyes_off_road_events,
                description="Driver frequently takes eyes off road for extended periods.",
                aga_mitigation="Reduce gaze-alert threshold to 1.2s; increase haptic intensity.",
            ))
        if tel.tailgating_events > 2 and "close_following" not in existing_categories:
            profile.blind_spots.append(DriverBlindSpot(
                category="close_following",
                confidence=0.6,
                event_count=tel.tailgating_events,
                description="Driver consistently maintains insufficient following distance.",
                aga_mitigation="Enable forward collision pre-warning at 2.0s headway threshold.",
            ))

    def get_chassis_config(self, driver_id: str) -> ChassisConfiguration:
        """Return the Digital Chassis configuration for the current driver session."""
        if driver_id not in self._profiles:
            raise ValueError(f"Driver {driver_id} not registered.")
        profile = self._profiles[driver_id]
        score = profile.composite_score

        # Map classification to chassis config
        config_map = {
            "Expert": dict(
                brake_prefill_sensitivity="minimal",
                brake_advisory_threshold_g=0.55,
                torque_ramp_profile="immediate",
                launch_control_enabled=True,
                soft_speed_limit_mph=None,
                alert_modality="haptic_only",
                lane_departure_sensitivity="standard",
                blind_spot_sensitivity_pct=0,
                gaze_alert_threshold_ms=2500,
            ),
            "Proficient": dict(
                brake_prefill_sensitivity="standard",
                brake_advisory_threshold_g=0.45,
                torque_ramp_profile="standard",
                launch_control_enabled=True,
                soft_speed_limit_mph=None,
                alert_modality="visual_haptic",
                lane_departure_sensitivity="standard",
                blind_spot_sensitivity_pct=10,
                gaze_alert_threshold_ms=2000,
            ),
            "Intermediate": dict(
                brake_prefill_sensitivity="standard",
                brake_advisory_threshold_g=0.35,
                torque_ramp_profile="standard",
                launch_control_enabled=False,
                soft_speed_limit_mph=None,
                alert_modality="all",
                lane_departure_sensitivity="high",
                blind_spot_sensitivity_pct=20,
                gaze_alert_threshold_ms=1800,
            ),
            "Novice": dict(
                brake_prefill_sensitivity="high",
                brake_advisory_threshold_g=0.25,
                torque_ramp_profile="gradual",
                launch_control_enabled=False,
                soft_speed_limit_mph=70,
                alert_modality="all",
                lane_departure_sensitivity="high",
                blind_spot_sensitivity_pct=35,
                gaze_alert_threshold_ms=1500,
            ),
        }

        params = config_map[profile.classification]
        custom = [bs.aga_mitigation for bs in profile.blind_spots if bs.confidence > 0.5]

        return ChassisConfiguration(
            driver_id=driver_id,
            classification=profile.classification,
            composite_score=score,
            custom_mitigations=custom,
            **params,
        )

    def export_profile(self, driver_id: str) -> str:
        """Export the driver profile as JSON (for secure on-device storage)."""
        profile = self._profiles[driver_id]
        data = asdict(profile)
        return json.dumps(data, indent=2)


# ─────────────────────────────────────────────
# Example usage
# ─────────────────────────────────────────────

if __name__ == "__main__":
    manager = DriverProfileManager()
    manager.register_driver("user_001", "Alex (Enthusiast)")
    manager.register_driver("user_002", "Sam (Teen Driver)")

    # Simulate journeys for an experienced driver
    expert_telemetry = JourneyTelemetry(
        journey_id="j_001", timestamp="2026-03-20T08:30:00Z",
        avg_brake_reaction_time_ms=220, emergency_brake_events=0,
        smooth_braking_score=0.92, smooth_acceleration_score=0.88,
        torque_demand_variance=0.3, lane_departure_events=0,
        avg_lateral_deviation_cm=8.0, avg_following_distance_s=2.8,
        tailgating_events=0, avg_adas_alert_response_ms=420,
        adas_ignored_events=0, eyes_off_road_events=1,
        max_gaze_off_road_duration_ms=800, urban_miles=12, highway_miles=43, night_miles=0
    )
    for _ in range(15):
        manager.update_from_journey("user_001", expert_telemetry)

    # Simulate journeys for a novice teen driver
    novice_telemetry = JourneyTelemetry(
        journey_id="j_002", timestamp="2026-03-20T16:00:00Z",
        avg_brake_reaction_time_ms=480, emergency_brake_events=2,
        smooth_braking_score=0.55, smooth_acceleration_score=0.60,
        torque_demand_variance=0.9, lane_departure_events=3,
        avg_lateral_deviation_cm=28.0, avg_following_distance_s=1.4,
        tailgating_events=4, avg_adas_alert_response_ms=820,
        adas_ignored_events=2, eyes_off_road_events=6,
        max_gaze_off_road_duration_ms=2800, urban_miles=8, highway_miles=5, night_miles=2
    )
    for _ in range(5):
        manager.update_from_journey("user_002", novice_telemetry)

    for driver_id, name in [("user_001", "Alex"), ("user_002", "Sam")]:
        profile = manager._profiles[driver_id]
        config = manager.get_chassis_config(driver_id)
        print(f"\n{'═'*52}")
        print(f"  AGA DRIVER PROFILE: {name}")
        print(f"{'═'*52}")
        print(f"  Classification:     {profile.classification}")
        print(f"  Composite Score:    {profile.composite_score:.1f}/100")
        print(f"  Total Journeys:     {profile.total_journeys}")
        print(f"\n  ── Chassis Config Applied ──────────────────")
        print(f"  Brake Sensitivity:  {config.brake_prefill_sensitivity}")
        print(f"  Torque Profile:     {config.torque_ramp_profile}")
        print(f"  Speed Limit:        {config.soft_speed_limit_mph or 'None (driver control)'} mph")
        print(f"  Alert Mode:         {config.alert_modality}")
        print(f"  Gaze Alert:         >{config.gaze_alert_threshold_ms}ms")
        if config.custom_mitigations:
            print(f"\n  ── Personalised Mitigations ─────────────────")
            for m in config.custom_mitigations:
                print(f"  • {m}")
