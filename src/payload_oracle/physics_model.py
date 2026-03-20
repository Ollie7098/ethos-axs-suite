"""
Payload Oracle — Physics Engine
================================
Computes the Payload Penalty (range reduction) for a given vehicle trip
based on additional mass (passengers + luggage) above the baseline curb weight.

AXS Ethos Intelligence Suite — Module II
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class VehicleSpec:
    """Base specifications for a supported luxury EV platform."""
    name: str
    base_range_miles: float        # EPA-rated range at curb weight
    curb_weight_kg: float          # Vehicle curb weight (no passengers/luggage)
    battery_capacity_kwh: float    # Usable battery capacity
    drag_coefficient: float        # Cd value
    frontal_area_m2: float         # Frontal area in square metres
    regen_efficiency: float = 0.70 # Regenerative braking recovery factor (0-1)


@dataclass
class TripProfile:
    """A driver-defined trip payload profile collected via the AXS mobile app."""
    route_distance_miles: float
    avg_speed_mph: float
    passengers: List[float]         # List of passenger weights in kg
    luggage_kg: float               # Total luggage weight in kg
    roof_box: bool = False          # Roof box attached?
    roof_box_drag_penalty: float = 0.07  # Estimated Cd increase for roof box
    elevation_gain_m: float = 0.0   # Net elevation gain for the route (metres)
    ambient_temp_celsius: float = 20.0   # Affects HVAC load
    load_placement: str = "standard"  # "standard", "frunk_heavy", "balanced"


@dataclass
class RangeAnalysis:
    """Output from the Payload Oracle physics engine."""
    baseline_range_miles: float
    payload_adjusted_range_miles: float
    payload_penalty_miles: float
    payload_penalty_pct: float
    confidence_interval_miles: float   # +/- miles
    can_complete_trip: bool
    range_shortfall_miles: float       # 0 if can complete
    energy_breakdown_kwh: dict = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


# Supported vehicle platforms
VEHICLE_PLATFORMS = {
    "mercedes_eqs_450": VehicleSpec(
        name="Mercedes-Benz EQS 450+",
        base_range_miles=350,
        curb_weight_kg=2585,
        battery_capacity_kwh=107.8,
        drag_coefficient=0.20,
        frontal_area_m2=2.51,
    ),
    "bmw_i7_xdrive60": VehicleSpec(
        name="BMW i7 xDrive60",
        base_range_miles=318,
        curb_weight_kg=2715,
        battery_capacity_kwh=101.7,
        drag_coefficient=0.24,
        frontal_area_m2=2.65,
    ),
    "audi_etron_gt": VehicleSpec(
        name="Audi e-tron GT quattro",
        base_range_miles=298,
        curb_weight_kg=2340,
        battery_capacity_kwh=93.4,
        drag_coefficient=0.24,
        frontal_area_m2=2.40,
    ),
    "porsche_taycan_4s": VehicleSpec(
        name="Porsche Taycan 4S",
        base_range_miles=283,
        curb_weight_kg=2295,
        battery_capacity_kwh=93.4,
        drag_coefficient=0.22,
        frontal_area_m2=2.35,
    ),
}


class PayloadOracleEngine:
    """
    Core physics engine for the AXS Payload Oracle.

    Computes range impact of payload using a multi-factor energy model:
    1. Kinetic energy penalty from additional mass
    2. Rolling resistance increase from payload
    3. Aerodynamic drag penalty from roof box / load
    4. Elevation energy cost
    5. HVAC thermal load (temperature-dependent)
    6. Load placement efficiency modifier
    """

    # Physical constants
    G = 9.81            # Gravitational acceleration (m/s²)
    AIR_DENSITY = 1.225 # kg/m³ at sea level, 20°C
    KM_PER_MILE = 1.60934

    # Rolling resistance coefficients
    CRR_BASE = 0.010           # Baseline Crr for luxury EV tires
    CRR_MASS_FACTOR = 0.00002  # Crr increase per kg of additional mass

    # Load placement efficiency modifiers
    PLACEMENT_MODIFIERS = {
        "standard":     1.000,   # No adjustment
        "frunk_heavy":  0.985,   # 1.5% improvement (better CoG, reduced tire scrub)
        "balanced":     0.992,   # 0.8% improvement (even axle loading → better regen)
    }

    # HVAC thermal load (kWh per 100 miles, deviation from 20°C optimum)
    HVAC_PENALTY_PER_DEGREE = 0.08  # kWh/100mi per °C of deviation

    def __init__(self, vehicle: VehicleSpec):
        self.vehicle = vehicle
        self.efficiency_kwh_per_mile = (
            vehicle.battery_capacity_kwh / vehicle.base_range_miles
        )

    def compute(self, trip: TripProfile) -> RangeAnalysis:
        """Run the full Payload Oracle analysis for a given trip profile."""

        total_payload_kg = sum(trip.passengers) + trip.luggage_kg
        trip_distance_km = trip.route_distance_miles * self.KM_PER_MILE
        avg_speed_ms = trip.avg_speed_mph * 0.44704

        # --- 1. Baseline energy consumption ---
        baseline_energy_kwh = (
            self.efficiency_kwh_per_mile * trip.route_distance_miles
        )

        # --- 2. Kinetic energy penalty (mass × acceleration cycles) ---
        # Models energy lost to inertia over the trip's start-stop cycles
        # Approximated as: ΔKE = 0.5 × Δm × v² × trip_cycles × (1 - regen_eff)
        trip_cycles = max(1, trip_distance_km / 2.0)  # avg stop every 2km in mixed driving
        ke_penalty_j = (
            0.5
            * total_payload_kg
            * (avg_speed_ms ** 2)
            * trip_cycles
            * (1 - self.vehicle.regen_efficiency)
        )
        ke_penalty_kwh = ke_penalty_j / 3_600_000

        # --- 3. Rolling resistance penalty ---
        crr_payload = self.CRR_BASE + (total_payload_kg * self.CRR_MASS_FACTOR)
        crr_baseline = self.CRR_BASE
        total_mass_kg = self.vehicle.curb_weight_kg + total_payload_kg
        rr_penalty_j = (
            (crr_payload - crr_baseline)
            * total_mass_kg
            * self.G
            * trip_distance_km * 1000
        )
        rr_penalty_kwh = rr_penalty_j / 3_600_000

        # --- 4. Aerodynamic penalty (roof box) ---
        if trip.roof_box:
            effective_cd = self.vehicle.drag_coefficient + trip.roof_box_drag_penalty
        else:
            effective_cd = self.vehicle.drag_coefficient

        aero_drag_j = (
            0.5
            * self.AIR_DENSITY
            * effective_cd
            * self.vehicle.frontal_area_m2
            * (avg_speed_ms ** 3)
            * (trip_distance_km * 1000 / avg_speed_ms)
        )
        aero_baseline_j = (
            0.5
            * self.AIR_DENSITY
            * self.vehicle.drag_coefficient
            * self.vehicle.frontal_area_m2
            * (avg_speed_ms ** 3)
            * (trip_distance_km * 1000 / avg_speed_ms)
        )
        aero_penalty_kwh = (aero_drag_j - aero_baseline_j) / 3_600_000

        # --- 5. Elevation energy cost ---
        elevation_energy_j = (
            total_mass_kg * self.G * trip.elevation_gain_m
        ) if trip.elevation_gain_m > 0 else 0
        elevation_kwh = elevation_energy_j / 3_600_000

        # --- 6. HVAC thermal penalty ---
        temp_deviation = abs(trip.ambient_temp_celsius - 20.0)
        hvac_penalty_kwh = (
            self.HVAC_PENALTY_PER_DEGREE
            * temp_deviation
            * trip.route_distance_miles / 100
        )

        # --- 7. Load placement efficiency modifier ---
        placement_modifier = self.PLACEMENT_MODIFIERS.get(
            trip.load_placement, 1.0
        )

        # --- Total energy with payload ---
        total_energy_kwh = (
            baseline_energy_kwh
            + ke_penalty_kwh
            + rr_penalty_kwh
            + aero_penalty_kwh
            + elevation_kwh
            + hvac_penalty_kwh
        ) * placement_modifier

        # --- Compute adjusted range ---
        usable_battery = self.vehicle.battery_capacity_kwh
        adjusted_efficiency = total_energy_kwh / trip.route_distance_miles
        payload_adjusted_range = usable_battery / adjusted_efficiency

        payload_penalty_miles = self.vehicle.base_range_miles - payload_adjusted_range
        payload_penalty_pct = (payload_penalty_miles / self.vehicle.base_range_miles) * 100

        can_complete = payload_adjusted_range >= trip.route_distance_miles
        shortfall = max(0, trip.route_distance_miles - payload_adjusted_range)

        # Confidence interval: ±5% accounting for driving style variance
        ci_miles = payload_adjusted_range * 0.05

        analysis = RangeAnalysis(
            baseline_range_miles=round(self.vehicle.base_range_miles, 1),
            payload_adjusted_range_miles=round(payload_adjusted_range, 1),
            payload_penalty_miles=round(payload_penalty_miles, 1),
            payload_penalty_pct=round(payload_penalty_pct, 1),
            confidence_interval_miles=round(ci_miles, 1),
            can_complete_trip=can_complete,
            range_shortfall_miles=round(shortfall, 1),
            energy_breakdown_kwh={
                "baseline": round(baseline_energy_kwh, 2),
                "kinetic_penalty": round(ke_penalty_kwh, 2),
                "rolling_resistance": round(rr_penalty_kwh, 2),
                "aerodynamic_drag": round(aero_penalty_kwh, 2),
                "elevation": round(elevation_kwh, 2),
                "hvac": round(hvac_penalty_kwh, 2),
            },
        )

        analysis.recommendations = self._generate_recommendations(
            trip, analysis, total_payload_kg
        )
        return analysis

    def _generate_recommendations(
        self,
        trip: TripProfile,
        analysis: RangeAnalysis,
        total_payload_kg: float
    ) -> List[str]:
        """Generate natural language Trade-off Insights for the driver."""
        recs = []

        if trip.roof_box:
            # Compute range gain from removing roof box
            trip_no_box = TripProfile(**{**trip.__dict__, "roof_box": False})
            analysis_no_box = self.compute(trip_no_box)
            gain = analysis_no_box.payload_adjusted_range_miles - analysis.payload_adjusted_range_miles
            recs.append(
                f"Removing the roof box would recover approximately {gain:.0f} miles of range "
                f"by eliminating aerodynamic drag penalties."
            )

        if trip.load_placement == "standard":
            trip_frunk = TripProfile(**{**trip.__dict__, "load_placement": "frunk_heavy"})
            analysis_frunk = self.compute(trip_frunk)
            gain = analysis_frunk.payload_adjusted_range_miles - analysis.payload_adjusted_range_miles
            if gain > 1:
                recs.append(
                    f"Redistributing heavier luggage to the front trunk (frunk) could improve "
                    f"range by ~{gain:.0f} miles by optimizing centre of gravity and reducing tire rolling resistance."
                )

        if analysis.range_shortfall_miles > 0:
            # Calculate how much luggage to remove to make the trip
            energy_per_kg = (
                analysis.energy_breakdown_kwh["kinetic_penalty"]
                + analysis.energy_breakdown_kwh["rolling_resistance"]
            ) / max(total_payload_kg, 1)
            kwh_needed = analysis.range_shortfall_miles * (
                self.vehicle.battery_capacity_kwh / self.vehicle.base_range_miles
            )
            luggage_to_remove_kg = kwh_needed / max(energy_per_kg, 0.001)
            luggage_to_remove_lbs = luggage_to_remove_kg * 2.205
            recs.append(
                f"You are currently {analysis.range_shortfall_miles:.0f} miles short of your destination. "
                f"Reducing luggage by approximately {luggage_to_remove_lbs:.0f} lbs ({luggage_to_remove_kg:.0f} kg) "
                f"would allow you to complete the journey without a charging stop."
            )

        if analysis.payload_penalty_pct > 10:
            recs.append(
                f"Your current payload is reducing range by {analysis.payload_penalty_pct:.1f}% "
                f"({analysis.payload_penalty_miles:.0f} miles). Consider leaving non-essential items behind."
            )

        if not recs:
            recs.append("Your current load is well-optimized. No significant trade-offs identified.")

        return recs


def format_analysis_report(vehicle_name: str, trip: TripProfile, analysis: RangeAnalysis) -> str:
    """Format the RangeAnalysis as a human-readable AXS app output."""
    status = "✅  Trip Feasible" if analysis.can_complete_trip else "⚠️  Charging Stop Required"
    lines = [
        f"╔══════════════════════════════════════════════════╗",
        f"║      AXS PAYLOAD ORACLE — RANGE ANALYSIS         ║",
        f"╚══════════════════════════════════════════════════╝",
        f"  Vehicle:         {vehicle_name}",
        f"  Route Distance:  {trip.route_distance_miles:.0f} miles",
        f"  Status:          {status}",
        f"",
        f"  Baseline Range:       {analysis.baseline_range_miles:.0f} miles",
        f"  Payload-Adjusted:     {analysis.payload_adjusted_range_miles:.0f} miles",
        f"  Payload Penalty:      -{analysis.payload_penalty_miles:.0f} miles  ({analysis.payload_penalty_pct:.1f}%)",
        f"  Confidence Interval:  ±{analysis.confidence_interval_miles:.0f} miles",
    ]
    if not analysis.can_complete_trip:
        lines.append(f"  Range Shortfall:      {analysis.range_shortfall_miles:.0f} miles")
    lines += [
        f"",
        f"  ── Energy Breakdown (kWh) ──────────────────────",
        f"  Baseline consumption:   {analysis.energy_breakdown_kwh['baseline']:.2f} kWh",
        f"  Kinetic penalty:       +{analysis.energy_breakdown_kwh['kinetic_penalty']:.2f} kWh",
        f"  Rolling resistance:    +{analysis.energy_breakdown_kwh['rolling_resistance']:.2f} kWh",
        f"  Aerodynamic drag:      +{analysis.energy_breakdown_kwh['aerodynamic_drag']:.2f} kWh",
        f"  Elevation cost:        +{analysis.energy_breakdown_kwh['elevation']:.2f} kWh",
        f"  HVAC load:             +{analysis.energy_breakdown_kwh['hvac']:.2f} kWh",
        f"",
        f"  ── Trade-off Insights ──────────────────────────",
    ]
    for i, rec in enumerate(analysis.recommendations, 1):
        # Word-wrap at 55 chars
        words = rec.split()
        line, wrapped = f"  {i}. ", []
        for word in words:
            if len(line) + len(word) > 58:
                wrapped.append(line)
                line = "     " + word + " "
            else:
                line += word + " "
        wrapped.append(line)
        lines.extend(wrapped)
    lines.append(f"{'═' * 52}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Example: Family trip Munich → Innsbruck (85 miles)
    vehicle = VEHICLE_PLATFORMS["mercedes_eqs_450"]
    engine = PayloadOracleEngine(vehicle)

    trip = TripProfile(
        route_distance_miles=85,
        avg_speed_mph=65,
        passengers=[80, 72, 68, 55, 42],  # 5 passengers (kg)
        luggage_kg=154,  # ~340 lbs
        roof_box=True,
        elevation_gain_m=450,
        ambient_temp_celsius=8.0,
        load_placement="standard",
    )

    analysis = engine.compute(trip)
    print(format_analysis_report(vehicle.name, trip, analysis))
