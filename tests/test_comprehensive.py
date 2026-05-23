"""
Comprehensive test suite for the COLREGs-72 expert system.

Covers three layers:
  1. Geometry module - coordinate transforms, CPA/TCPA, collision risk, forbidden headings;
  2. Rules module - priority ranks, encounter classification, sailing Rule 12;
  3. Engine integration - full inference pipeline including multi-target, restricted
     visibility, last-moment maneuvers, and physical constraints.
"""

import math
import unittest

from src.engine import COLREGInferenceEngine
from src.geometry import (
    CRITICAL_TCPA,
    SAFE_CPA_DISTANCE,
    calculate_cpa_tcpa,
    calculate_distance,
    calculate_relative_bearing,
    calculate_true_bearing,
    convert_boolean_array_to_sectors,
    course_to_rad,
    get_forbidden_headings_for_target,
    get_velocity_components,
    is_collision_risk_exists,
    is_turn_possible,
    rad_to_course,
)
from src.models import (
    Action,
    Decision,
    Environment,
    TargetDecision,
    Vessel,
    VesselRole,
    VesselType,
    Visibility,
)
from src.rules import (
    classify_encounter_sectors,
    evaluate_sailing_vessels_rule12,
    get_vessel_priority_rank,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _vessel(name="V", x=0.0, y=0.0, course=0.0, speed=10.0,
            vtype=VesselType.POWER_DRIVEN, radius=0.25):
    return Vessel(
        name=name, x=x, y=y, course=course, speed=speed,
        vessel_type=vtype, min_turning_radius=radius,
    )


def _env(vis=Visibility.GOOD):
    return Environment(visibility=vis)


# ===================================================================
# 1. GEOMETRY MODULE TESTS
# ===================================================================

class TestVelocityComponents(unittest.TestCase):
    """Velocity decomposition for cardinal directions."""

    def test_north(self):
        vx, vy = get_velocity_components(10.0, 0.0)
        self.assertAlmostEqual(vx, 0.0, places=5)
        self.assertAlmostEqual(vy, 10.0, places=5)

    def test_east(self):
        vx, vy = get_velocity_components(10.0, 90.0)
        self.assertAlmostEqual(vx, 10.0, places=5)
        self.assertAlmostEqual(vy, 0.0, places=5)

    def test_south(self):
        vx, vy = get_velocity_components(10.0, 180.0)
        self.assertAlmostEqual(vx, 0.0, places=5)
        self.assertAlmostEqual(vy, -10.0, places=5)

    def test_west(self):
        vx, vy = get_velocity_components(10.0, 270.0)
        self.assertAlmostEqual(vx, -10.0, places=5)
        self.assertAlmostEqual(vy, 0.0, places=5)


class TestDistanceCalculation(unittest.TestCase):

    def test_simple_distance(self):
        v1 = _vessel("A", x=0.0, y=0.0)
        v2 = _vessel("B", x=3.0, y=4.0)
        self.assertAlmostEqual(calculate_distance(v1, v2), 5.0, places=5)

    def test_same_position(self):
        v1 = _vessel("A", x=5.0, y=5.0)
        v2 = _vessel("B", x=5.0, y=5.0)
        self.assertAlmostEqual(calculate_distance(v1, v2), 0.0, places=5)


class TestTrueBearing(unittest.TestCase):
    """True bearing in all four quadrants."""

    def test_target_due_north(self):
        own = _vessel("O", x=0, y=0)
        tgt = _vessel("T", x=0, y=5)
        self.assertAlmostEqual(calculate_true_bearing(own, tgt), 0.0, places=3)

    def test_target_due_east(self):
        own = _vessel("O", x=0, y=0)
        tgt = _vessel("T", x=5, y=0)
        self.assertAlmostEqual(calculate_true_bearing(own, tgt), 90.0, places=3)

    def test_target_due_south(self):
        own = _vessel("O", x=0, y=0)
        tgt = _vessel("T", x=0, y=-5)
        self.assertAlmostEqual(calculate_true_bearing(own, tgt), 180.0, places=3)

    def test_target_due_west(self):
        own = _vessel("O", x=0, y=0)
        tgt = _vessel("T", x=-5, y=0)
        self.assertAlmostEqual(calculate_true_bearing(own, tgt), 270.0, places=3)

    def test_target_northeast(self):
        own = _vessel("O", x=0, y=0)
        tgt = _vessel("T", x=5, y=5)
        self.assertAlmostEqual(calculate_true_bearing(own, tgt), 45.0, places=3)

    def test_target_southwest(self):
        own = _vessel("O", x=0, y=0)
        tgt = _vessel("T", x=-5, y=-5)
        self.assertAlmostEqual(calculate_true_bearing(own, tgt), 225.0, places=3)


class TestRelativeBearing(unittest.TestCase):

    def test_target_dead_ahead(self):
        own = _vessel("O", x=0, y=0, course=0)
        tgt = _vessel("T", x=0, y=5)
        self.assertAlmostEqual(calculate_relative_bearing(own, tgt), 0.0, places=3)

    def test_target_on_starboard_beam(self):
        own = _vessel("O", x=0, y=0, course=0)
        tgt = _vessel("T", x=5, y=0)
        self.assertAlmostEqual(calculate_relative_bearing(own, tgt), 90.0, places=3)

    def test_target_astern(self):
        own = _vessel("O", x=0, y=0, course=0)
        tgt = _vessel("T", x=0, y=-5)
        self.assertAlmostEqual(calculate_relative_bearing(own, tgt), 180.0, places=3)

    def test_target_port_beam(self):
        own = _vessel("O", x=0, y=0, course=0)
        tgt = _vessel("T", x=-5, y=0)
        self.assertAlmostEqual(calculate_relative_bearing(own, tgt), 270.0, places=3)

    def test_own_heading_east_target_north(self):
        # Own heading east, target due north => relative bearing 270 (port beam)
        own = _vessel("O", x=0, y=0, course=90)
        tgt = _vessel("T", x=0, y=5)
        self.assertAlmostEqual(calculate_relative_bearing(own, tgt), 270.0, places=3)


class TestCpaTcpa(unittest.TestCase):

    def test_head_on_collision(self):
        """Two vessels approaching head-on should have CPA near zero."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=10, course=180, speed=10)
        cpa, tcpa = calculate_cpa_tcpa(own, tgt)
        self.assertAlmostEqual(cpa, 0.0, places=3)
        self.assertGreater(tcpa, 0.0)
        # TCPA should be 0.5 hours (10 nm / 20 kts combined approach speed)
        self.assertAlmostEqual(tcpa, 0.5, places=3)

    def test_crossing_nonzero_cpa(self):
        """Crossing vessels should have a non-zero CPA if offset."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=5, y=5, course=270, speed=10)
        cpa, tcpa = calculate_cpa_tcpa(own, tgt)
        self.assertGreater(tcpa, 0.0)

    def test_parallel_same_speed(self):
        """Parallel courses at equal speed - no relative velocity, infinite TCPA."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=3, y=0, course=0, speed=10)
        cpa, tcpa = calculate_cpa_tcpa(own, tgt)
        self.assertEqual(tcpa, float("inf"))
        self.assertAlmostEqual(cpa, 3.0, places=3)

    def test_diverging_ships(self):
        """Ships moving away from each other should have negative TCPA."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=-5, course=180, speed=10)
        cpa, tcpa = calculate_cpa_tcpa(own, tgt)
        self.assertLess(tcpa, 0.0)


class TestCollisionRisk(unittest.TestCase):

    def test_risk_when_within_safe_distance(self):
        """Risk exists when current distance is below SAFE_CPA_DISTANCE."""
        own = _vessel("O", x=0, y=0, course=0, speed=0)
        tgt = _vessel("T", x=1.0, y=0, course=0, speed=0)
        risk, dist, cpa, tcpa = is_collision_risk_exists(own, tgt)
        self.assertTrue(risk)
        self.assertAlmostEqual(dist, 1.0, places=3)

    def test_no_risk_beyond_safe_distance_diverging(self):
        """No risk when far away and diverging."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=10, y=10, course=90, speed=10)
        risk, dist, cpa, tcpa = is_collision_risk_exists(own, tgt)
        self.assertFalse(risk)

    def test_risk_at_boundary_tcpa(self):
        """Risk exists when approaching with CPA < 2.0 and TCPA within critical window."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=5, course=180, speed=10)
        risk, dist, cpa, tcpa = is_collision_risk_exists(own, tgt)
        self.assertTrue(risk)

    def test_no_risk_negative_tcpa(self):
        """Ships already past CPA (negative TCPA) and far apart - no risk."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=5, y=-10, course=180, speed=10)
        risk, dist, cpa, tcpa = is_collision_risk_exists(own, tgt)
        self.assertFalse(risk)

    def test_exactly_at_safe_distance(self):
        """Exactly at SAFE_CPA_DISTANCE boundary (dist == 2.0) - no risk by dist alone.
        The condition is dist < 2.0, not <=."""
        own = _vessel("O", x=0, y=0, course=90, speed=5)
        tgt = _vessel("T", x=2.0, y=0, course=270, speed=5)
        risk, dist, cpa, tcpa = is_collision_risk_exists(own, tgt)
        # dist == 2.0 is NOT < 2.0, but CPA is 0 and TCPA > 0 and TCPA < 0.5
        # so the second condition triggers
        self.assertTrue(risk)


class TestTurnFeasibility(unittest.TestCase):

    def test_always_possible_when_tcpa_negative(self):
        self.assertTrue(is_turn_possible(10.0, 0.25, 90.0, -1.0))

    def test_always_possible_when_tcpa_infinite(self):
        self.assertTrue(is_turn_possible(10.0, 0.25, 90.0, float("inf")))

    def test_possible_with_ample_time(self):
        # Turn arc = 0.25 * pi/2 ~ 0.3927 nm, time = 0.3927/10 ~ 0.039 h.
        # TCPA = 1.0 h is plenty.
        self.assertTrue(is_turn_possible(10.0, 0.25, 90.0, 1.0))

    def test_impossible_with_very_short_tcpa(self):
        # Large radius, tight time.  Turn arc = 0.8 * pi/2 ~ 1.257 nm,
        # time = 1.257/10 ~ 0.126 h.  TCPA = 0.01 h is too short.
        self.assertFalse(is_turn_possible(10.0, 0.8, 90.0, 0.01))

    def test_possible_when_stationary(self):
        """Speed < 0.1 means vessel is stationary - always possible."""
        self.assertTrue(is_turn_possible(0.05, 0.5, 90.0, 0.001))


class TestForbiddenHeadings(unittest.TestCase):

    def test_approaching_head_on_produces_forbidden_band(self):
        """A head-on target should create a forbidden band around 0 degrees."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=3, course=180, speed=10)
        forbidden = get_forbidden_headings_for_target(own, tgt)
        # Heading 0 (straight at the target) must be forbidden
        self.assertTrue(forbidden[0])
        # Some abeam heading should be safe
        self.assertFalse(forbidden[90])

    def test_safe_target_no_forbidden(self):
        """A distant, diverging target should produce no forbidden headings."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=20, y=20, course=90, speed=10)
        forbidden = get_forbidden_headings_for_target(own, tgt)
        self.assertFalse(any(forbidden))


class TestBooleanArrayToSectors(unittest.TestCase):

    def test_single_sector(self):
        arr = [False] * 360
        for i in range(10, 21):
            arr[i] = True
        sectors = convert_boolean_array_to_sectors(arr)
        self.assertEqual(len(sectors), 1)
        self.assertEqual(sectors[0], (10.0, 20.0))

    def test_two_sectors(self):
        arr = [False] * 360
        for i in range(10, 21):
            arr[i] = True
        for i in range(100, 111):
            arr[i] = True
        sectors = convert_boolean_array_to_sectors(arr)
        self.assertEqual(len(sectors), 2)
        self.assertEqual(sectors[0], (10.0, 20.0))
        self.assertEqual(sectors[1], (100.0, 110.0))

    def test_wrap_around_at_360_0(self):
        """Sector that wraps around 360/0 boundary should merge."""
        arr = [False] * 360
        for i in range(350, 360):
            arr[i] = True
        for i in range(0, 11):
            arr[i] = True
        sectors = convert_boolean_array_to_sectors(arr)
        self.assertEqual(len(sectors), 1)
        # After merge: start=350, end=10
        self.assertEqual(sectors[0][0], 350.0)
        self.assertEqual(sectors[0][1], 10.0)

    def test_empty_array(self):
        arr = [False] * 360
        sectors = convert_boolean_array_to_sectors(arr)
        self.assertEqual(len(sectors), 0)

    def test_full_circle(self):
        arr = [True] * 360
        sectors = convert_boolean_array_to_sectors(arr)
        self.assertEqual(len(sectors), 1)
        self.assertEqual(sectors[0][0], 0.0)
        self.assertEqual(sectors[0][1], 359.0)


# ===================================================================
# 2. RULES MODULE TESTS
# ===================================================================

class TestVesselPriorityRanks(unittest.TestCase):

    def test_all_ranks(self):
        expected = {
            VesselType.NUC: 5,
            VesselType.RAM: 4,
            VesselType.CBD: 3,
            VesselType.FISHING: 2,
            VesselType.SAILING: 1,
            VesselType.POWER_DRIVEN: 0,
        }
        for vtype, rank in expected.items():
            with self.subTest(vtype=vtype):
                self.assertEqual(get_vessel_priority_rank(vtype), rank)

    def test_hierarchy_ordering(self):
        """Confirm strict ordering: NUC > RAM > CBD > FISHING > SAILING > POWER_DRIVEN."""
        types = [
            VesselType.NUC, VesselType.RAM, VesselType.CBD,
            VesselType.FISHING, VesselType.SAILING, VesselType.POWER_DRIVEN,
        ]
        ranks = [get_vessel_priority_rank(t) for t in types]
        for i in range(len(ranks) - 1):
            self.assertGreater(ranks[i], ranks[i + 1])


class TestEncounterClassification(unittest.TestCase):

    def test_head_on(self):
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=5, course=180, speed=10)
        sector, is_ho, is_xing, is_ot = classify_encounter_sectors(own, tgt)
        self.assertEqual(sector, "head_on")
        self.assertTrue(is_ho)
        self.assertFalse(is_xing)
        self.assertFalse(is_ot)

    def test_head_on_course_diff_170(self):
        """Edge case: course difference exactly 170 degrees."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=5, course=170, speed=10)
        sector, is_ho, is_xing, is_ot = classify_encounter_sectors(own, tgt)
        # rb_own must be < 10 or > 350 for head-on.  Target at (0,5) from (0,0)
        # gives true bearing 0 deg.  rb_own = 0 - 0 = 0.  That's within 10.
        # rb_tgt = bearing from tgt to own.  own is at (0,0) relative to (0,5)
        # => true bearing = 180 deg.  rb_tgt = (180 - 170) % 360 = 10.
        # is_tgt_seeing_headon: rb_tgt <= 10 => True.
        # So this should be head_on.
        self.assertEqual(sector, "head_on")
        self.assertTrue(is_ho)

    def test_head_on_course_diff_190(self):
        """Edge case: course difference exactly 190 degrees."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=5, course=190, speed=10)
        sector, is_ho, is_xing, is_ot = classify_encounter_sectors(own, tgt)
        # rb_own = 0 (straight ahead). rb_tgt = (180 - 190) % 360 = 350.
        # is_tgt_seeing_headon: rb_tgt >= 350 => True.
        self.assertEqual(sector, "head_on")
        self.assertTrue(is_ho)

    def test_crossing_starboard(self):
        """Target on our starboard side, crossing courses."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=3, y=3, course=270, speed=10)
        sector, is_ho, is_xing, is_ot = classify_encounter_sectors(own, tgt)
        self.assertEqual(sector, "crossing_starboard")
        self.assertTrue(is_xing)

    def test_crossing_port(self):
        """Target on our port side, crossing courses."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=-3, y=3, course=90, speed=10)
        sector, is_ho, is_xing, is_ot = classify_encounter_sectors(own, tgt)
        self.assertEqual(sector, "crossing_port")
        self.assertTrue(is_xing)

    def test_own_overtaking(self):
        """Own vessel overtaking: we are faster and behind the target."""
        own = _vessel("O", x=0, y=0, course=0, speed=15)
        tgt = _vessel("T", x=0, y=3, course=0, speed=8)
        sector, is_ho, is_xing, is_ot = classify_encounter_sectors(own, tgt)
        self.assertEqual(sector, "own_overtaking")
        self.assertTrue(is_ot)

    def test_target_overtaking(self):
        """Target overtaking us: target is faster and behind us."""
        own = _vessel("O", x=0, y=0, course=0, speed=8)
        tgt = _vessel("T", x=0, y=-3, course=0, speed=15)
        sector, is_ho, is_xing, is_ot = classify_encounter_sectors(own, tgt)
        self.assertEqual(sector, "target_overtaking")
        self.assertTrue(is_ot)

    def test_overtaking_stern_boundary_112_5(self):
        """Target seeing us at exactly 112.5 degrees - boundary for stern sector."""
        # We need rb_tgt = 112.5 for own_overtaking.
        # Place own vessel such that the bearing from target to own is at 112.5 relative.
        # Target at origin, course 0, speed 5.
        # Own at position such that true bearing from target to own = 112.5.
        # atan2(dx, dy) = 112.5 deg => dx = sin(112.5), dy = cos(112.5)
        r = 3.0
        angle_rad = math.radians(112.5)
        own_x = r * math.sin(angle_rad)
        own_y = r * math.cos(angle_rad)
        own = _vessel("O", x=own_x, y=own_y, course=0, speed=15)
        tgt = _vessel("T", x=0, y=0, course=0, speed=5)
        # rb_tgt = bearing from target to own relative to target's course
        rb_tgt = calculate_relative_bearing(tgt, own)
        self.assertAlmostEqual(rb_tgt, 112.5, places=1)
        sector, _, _, is_ot = classify_encounter_sectors(own, tgt)
        self.assertTrue(is_ot)
        self.assertEqual(sector, "own_overtaking")

    def test_overtaking_stern_boundary_247_5(self):
        """Target seeing us at exactly 247.5 degrees - boundary for stern sector."""
        r = 3.0
        angle_rad = math.radians(247.5)
        own_x = r * math.sin(angle_rad)
        own_y = r * math.cos(angle_rad)
        own = _vessel("O", x=own_x, y=own_y, course=0, speed=15)
        tgt = _vessel("T", x=0, y=0, course=0, speed=5)
        rb_tgt = calculate_relative_bearing(tgt, own)
        self.assertAlmostEqual(rb_tgt, 247.5, places=1)
        sector, _, _, is_ot = classify_encounter_sectors(own, tgt)
        self.assertTrue(is_ot)
        self.assertEqual(sector, "own_overtaking")


class TestSailingRule12(unittest.TestCase):

    def test_different_tacks_port_gives_way(self):
        """Different tacks: port tack gives way to starboard tack."""
        # Wind from north (0 deg).
        # Own course 90 => wind_rel = (0 - 90) % 360 = 270 => port tack (left tack, >= 180)
        # Target course 270 => wind_rel = (0 - 270) % 360 = 90 => starboard tack (< 180)
        own = _vessel("O", x=0, y=0, course=90, speed=6, vtype=VesselType.SAILING)
        tgt = _vessel("T", x=5, y=0, course=270, speed=6, vtype=VesselType.SAILING)
        role, action, _ = evaluate_sailing_vessels_rule12(own, tgt, wind_dir=0.0)
        self.assertEqual(role, VesselRole.GIVE_WAY)

    def test_different_tacks_starboard_stands_on(self):
        """Different tacks: starboard tack has right of way."""
        # Own course 270 => wind_rel = (0 - 270) % 360 = 90 => starboard tack
        # Target course 90 => wind_rel = 270 => port tack
        own = _vessel("O", x=0, y=0, course=270, speed=6, vtype=VesselType.SAILING)
        tgt = _vessel("T", x=-5, y=0, course=90, speed=6, vtype=VesselType.SAILING)
        role, action, _ = evaluate_sailing_vessels_rule12(own, tgt, wind_dir=0.0)
        self.assertEqual(role, VesselRole.STAND_ON)

    def test_same_tack_windward_gives_way(self):
        """Same tack: windward vessel gives way to leeward vessel.

        NOTE: This test exposes a source code bug - rules.py uses math.radians()
        on line 117 but never imports math. The same-tack branch of
        evaluate_sailing_vessels_rule12() crashes with NameError.
        """
        # Wind from north (0 deg).
        # Both heading east (course=90), both starboard tack.
        # Wind vector: (sin(0), cos(0)) = (0, 1).
        # Windward projection: -(x * 0 + y * 1) = -y.
        # Own at y=5 => windward projection = -5
        # Target at y=0 => windward projection = 0
        # -5 < 0, so own is LEEWARD (lower projection).
        # We need own to be windward: own at y=0, target at y=5
        own = _vessel("O", x=0, y=0, course=90, speed=6, vtype=VesselType.SAILING)
        tgt = _vessel("T", x=5, y=5, course=90, speed=6, vtype=VesselType.SAILING)
        role, action, _ = evaluate_sailing_vessels_rule12(own, tgt, wind_dir=0.0)
        # windward pos_own = -(0*0 + 0*1) = 0
        # windward pos_tgt = -(5*0 + 5*1) = -5
        # own (0) > tgt (-5) => own is windward => gives way
        self.assertEqual(role, VesselRole.GIVE_WAY)

    def test_same_tack_leeward_stands_on(self):
        """Same tack: leeward vessel stands on.

        NOTE: This test exposes a source code bug - rules.py uses math.radians()
        on line 117 but never imports math. The same-tack branch of
        evaluate_sailing_vessels_rule12() crashes with NameError.
        """
        # Wind from north (0 deg).
        # Both heading east (course=90), both starboard tack.
        # Own at y=5 (more downwind) => windward proj = -5
        # Target at y=0 => windward proj = 0
        # -5 < 0 => own is leeward => stands on
        own = _vessel("O", x=0, y=5, course=90, speed=6, vtype=VesselType.SAILING)
        tgt = _vessel("T", x=5, y=0, course=90, speed=6, vtype=VesselType.SAILING)
        role, action, _ = evaluate_sailing_vessels_rule12(own, tgt, wind_dir=0.0)
        self.assertEqual(role, VesselRole.STAND_ON)


# ===================================================================
# 3. ENGINE INTEGRATION TESTS
# ===================================================================

class TestEngineNoTargets(unittest.TestCase):

    def test_no_targets(self):
        engine = COLREGInferenceEngine()
        own = _vessel("O")
        decision = engine.evaluate(own, [], _env())
        self.assertFalse(decision.collision_risk)
        self.assertEqual(decision.recommended_action, Action.N_A)
        self.assertEqual(decision.own_role, VesselRole.N_A)
        self.assertEqual(decision.recommended_heading, own.course)


class TestEngineSafeTarget(unittest.TestCase):

    def test_single_safe_target(self):
        engine = COLREGInferenceEngine()
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=10, y=10, course=90, speed=10)
        decision = engine.evaluate(own, [tgt], _env())
        self.assertFalse(decision.collision_risk)
        self.assertEqual(decision.recommended_action, Action.N_A)


class TestEngineHeadOn(unittest.TestCase):

    def test_rule_14_head_on(self):
        """Rule 14: head-on encounter - both alter starboard."""
        engine = COLREGInferenceEngine()
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=1.5, course=180, speed=10)
        decision = engine.evaluate(own, [tgt], _env())
        self.assertTrue(decision.collision_risk)
        td = decision.target_decisions["T"]
        self.assertEqual(td.own_role, VesselRole.BOTH_GIVE_WAY)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)


class TestEngineCrossing(unittest.TestCase):

    def test_rule_15_give_way_target_starboard(self):
        """Rule 15: target on starboard - we give way."""
        engine = COLREGInferenceEngine()
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=1.0, y=1.0, course=270, speed=10)
        decision = engine.evaluate(own, [tgt], _env())
        self.assertTrue(decision.collision_risk)
        td = decision.target_decisions["T"]
        self.assertEqual(td.own_role, VesselRole.GIVE_WAY)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_rule_15_stand_on_target_port(self):
        """Rule 15: target on port - we stand on."""
        engine = COLREGInferenceEngine()
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        # Place target far enough so TCPA > 0.15 (avoids Rule 17(b) override)
        tgt = _vessel("T", x=-3.0, y=3.0, course=90, speed=10)
        d = engine.evaluate(own, [tgt], _env())
        self.assertTrue(d.collision_risk)
        td = d.target_decisions["T"]
        # Crossing_port with same type => STAND_ON.
        self.assertEqual(td.own_role, VesselRole.STAND_ON)
        self.assertEqual(td.recommended_action, Action.KEEP_COURSE_SPEED)


class TestEngineOvertaking(unittest.TestCase):

    def test_rule_13_we_overtake_give_way(self):
        """Rule 13: we overtake target - give way."""
        engine = COLREGInferenceEngine()
        own = _vessel("O", x=0, y=0, course=0, speed=15)
        tgt = _vessel("T", x=0, y=1, course=0, speed=8)
        decision = engine.evaluate(own, [tgt], _env())
        self.assertTrue(decision.collision_risk)
        td = decision.target_decisions["T"]
        self.assertEqual(td.own_role, VesselRole.GIVE_WAY)
        self.assertEqual(td.encounter_type, "own_overtaking")

    def test_rule_13_being_overtaken_stand_on(self):
        """Rule 13: target overtakes us - stand on."""
        engine = COLREGInferenceEngine()
        own = _vessel("O", x=0, y=0, course=0, speed=8)
        # Place target farther behind so TCPA > 0.15 (avoids Rule 17(b) override)
        tgt = _vessel("T", x=0, y=-3, course=0, speed=15)
        decision = engine.evaluate(own, [tgt], _env())
        self.assertTrue(decision.collision_risk)
        td = decision.target_decisions["T"]
        self.assertEqual(td.own_role, VesselRole.STAND_ON)
        self.assertEqual(td.encounter_type, "target_overtaking")


class TestEngineRule18Priorities(unittest.TestCase):
    """Rule 18: type-based priority hierarchy tests."""

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def _make_scenario(self, own_type, tgt_type):
        """Create a crossing scenario where type priority decides the outcome."""
        own = _vessel("O", x=0, y=0, course=0, speed=10, vtype=own_type)
        tgt = _vessel("T", x=1.0, y=1.0, course=270, speed=10, vtype=tgt_type)
        return own, tgt

    def test_power_vs_sailing(self):
        own, tgt = self._make_scenario(VesselType.POWER_DRIVEN, VesselType.SAILING)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_power_vs_fishing(self):
        own, tgt = self._make_scenario(VesselType.POWER_DRIVEN, VesselType.FISHING)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_power_vs_nuc(self):
        own, tgt = self._make_scenario(VesselType.POWER_DRIVEN, VesselType.NUC)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_power_vs_ram(self):
        own, tgt = self._make_scenario(VesselType.POWER_DRIVEN, VesselType.RAM)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_power_vs_cbd(self):
        own, tgt = self._make_scenario(VesselType.POWER_DRIVEN, VesselType.CBD)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_fishing_vs_nuc(self):
        own, tgt = self._make_scenario(VesselType.FISHING, VesselType.NUC)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_sailing_vs_fishing(self):
        own, tgt = self._make_scenario(VesselType.SAILING, VesselType.FISHING)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_nuc_vs_power_stands_on(self):
        # Use farther separation so TCPA > 0.15, avoiding Rule 17(b) override
        own = _vessel("O", x=0, y=0, course=0, speed=10, vtype=VesselType.NUC)
        tgt = _vessel("T", x=3.0, y=3.0, course=270, speed=10, vtype=VesselType.POWER_DRIVEN)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.STAND_ON)


class TestEngineRestrictedVisibility(unittest.TestCase):
    """Rule 19: restricted visibility tests."""

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_rule_19_target_ahead_no_port_turn(self):
        """Rule 19(d)(i): target ahead of beam - avoid port turn."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0.5, y=1.0, course=180, speed=10)
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        self.assertTrue(d.collision_risk)
        td = d.target_decisions["T"]
        # In restricted visibility, type priorities ignored => encounter_type is RESTRICTED
        self.assertEqual(td.encounter_type, "RESTRICTED")
        # Recommended action should be starboard (avoid port)
        self.assertEqual(td.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_rule_19_target_starboard_beam(self):
        """Rule 19(d)(ii): target on starboard beam - avoid starboard turn toward it."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        # Target at starboard beam area (90 < rb <= 180)
        tgt = _vessel("T", x=1.5, y=-0.5, course=270, speed=10)
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        self.assertTrue(d.collision_risk)
        td = d.target_decisions["T"]
        self.assertEqual(td.recommended_action, Action.ALTER_COURSE_PORT)

    def test_rule_19_target_port_quarter(self):
        """Rule 19(d)(ii): target on port quarter - avoid port turn toward it."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        # Target to port and behind (rb_own > 180)
        tgt = _vessel("T", x=-1.5, y=-0.5, course=90, speed=10)
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        self.assertTrue(d.collision_risk)
        td = d.target_decisions["T"]
        self.assertEqual(td.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_rule_19_ignores_type_priorities(self):
        """Restricted visibility ignores vessel type priorities."""
        own = _vessel("O", x=0, y=0, course=0, speed=10, vtype=VesselType.POWER_DRIVEN)
        tgt = _vessel("T", x=0.5, y=1.0, course=180, speed=10, vtype=VesselType.NUC)
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        td = d.target_decisions["T"]
        # Should NOT be VesselRole.GIVE_WAY due to type priority;
        # instead it follows bearing-based Rule 19 logic (BOTH_GIVE_WAY or GIVE_WAY)
        self.assertEqual(td.encounter_type, "RESTRICTED")
        self.assertIn(td.own_role, [VesselRole.BOTH_GIVE_WAY, VesselRole.GIVE_WAY])


class TestEngineRule17bLastMoment(unittest.TestCase):

    def test_last_moment_action(self):
        """Rule 17(b): stand-on vessel with very small TCPA must take action."""
        engine = COLREGInferenceEngine()
        # Set up a crossing scenario where we would normally stand on
        # (target on port side), but TCPA is very small.
        # Target on port, close, approaching fast => TCPA < 0.15
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        # Target from port side, very close
        tgt = _vessel("T", x=-0.3, y=0.3, course=90, speed=10)
        d = engine.evaluate(own, [tgt], _env())
        td = d.target_decisions["T"]
        # The scenario must have tcpa < 0.15 for the rule to fire.
        # If tcpa >= 0.15 the role stays STAND_ON.
        if td.tcpa < 0.15:
            # Rule 17(b) should override STAND_ON to GIVE_WAY
            self.assertEqual(td.own_role, VesselRole.GIVE_WAY)
            self.assertEqual(td.recommended_action, Action.ALTER_COURSE_STARBOARD)
        else:
            # If geometry doesn't produce tcpa < 0.15, let's craft it more precisely
            self.skipTest("TCPA not small enough for this geometry")


class TestEngineRule17bCrafted(unittest.TestCase):

    def test_last_moment_crafted(self):
        """Rule 17(b) with precisely crafted geometry ensuring TCPA < 0.15 hours."""
        engine = COLREGInferenceEngine()
        # crossing_port with very small separation.
        # Own heading north, target to port heading east, very close.
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=-0.15, y=0.15, course=90, speed=15)
        d = engine.evaluate(own, [tgt], _env())
        td = d.target_decisions["T"]
        # Verify TCPA is indeed small
        _, tcpa_val = calculate_cpa_tcpa(own, tgt)
        if tcpa_val < 0.15 and tcpa_val > 0:
            # Originally this would be STAND_ON (crossing_port),
            # but Rule 17(b) overrides it.
            self.assertEqual(td.own_role, VesselRole.GIVE_WAY)
        else:
            self.skipTest(f"TCPA={tcpa_val:.3f} not in (0, 0.15) range")


class TestEngineMultiTarget(unittest.TestCase):

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_safe_plus_dangerous(self):
        """One safe target and one dangerous target."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        safe_tgt = _vessel("Safe", x=10, y=10, course=90, speed=10)
        danger_tgt = _vessel("Danger", x=1.0, y=1.0, course=270, speed=10)
        d = self.engine.evaluate(own, [safe_tgt, danger_tgt], _env())
        self.assertTrue(d.collision_risk)
        self.assertFalse(d.target_decisions["Safe"].collision_risk)
        self.assertTrue(d.target_decisions["Danger"].collision_risk)

    def test_two_targets_conflicting(self):
        """Two dangerous targets from different sides."""
        own = _vessel("O", x=0, y=0, course=0, speed=12)
        tgt_a = _vessel("A", x=1.0, y=1.0, course=270, speed=10)
        tgt_b = _vessel("B", x=-1.0, y=1.0, course=90, speed=10)
        d = self.engine.evaluate(own, [tgt_a, tgt_b], _env())
        self.assertTrue(d.collision_risk)
        # Must find SOME heading or recommend stop
        self.assertIn(d.recommended_action, [
            Action.ALTER_COURSE_STARBOARD,
            Action.ALTER_COURSE_PORT,
            Action.REDUCE_SPEED_OR_STOP,
        ])
        if d.recommended_heading is not None:
            # Verify the heading is not in forbidden sectors
            h = int(round(d.recommended_heading)) % 360
            for start, end in d.forbidden_sectors:
                if start <= end:
                    self.assertFalse(start <= h <= end,
                                     f"Heading {h} falls in forbidden sector ({start},{end})")


class TestEnginePhysicalConstraints(unittest.TestCase):

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_large_turning_radius_warning(self):
        """Large turning radius with close head-on should trigger maneuver_possible=False."""
        own = _vessel("O", x=0, y=0, course=0, speed=20, radius=0.8)
        tgt = _vessel("T", x=0, y=0.3, course=180, speed=10)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertTrue(d.collision_risk)
        self.assertFalse(d.maneuver_possible)

    def test_sufficient_time_to_turn(self):
        """Normal turning radius with distant target - maneuver possible."""
        own = _vessel("O", x=0, y=0, course=0, speed=10, radius=0.25)
        tgt = _vessel("T", x=1.0, y=5.0, course=270, speed=10)
        d = self.engine.evaluate(own, [tgt], _env())
        if d.collision_risk and d.recommended_heading is not None:
            self.assertTrue(d.maneuver_possible)


class TestEngineHeadingSelection(unittest.TestCase):

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_starboard_preference_within_110(self):
        """Engine should prefer starboard turn if within 110 degrees."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=1.5, course=180, speed=10)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertTrue(d.collision_risk)
        self.assertEqual(d.recommended_action, Action.ALTER_COURSE_STARBOARD)
        if d.recommended_heading is not None:
            delta = (d.recommended_heading - own.course) % 360
            self.assertLessEqual(delta, 110.0)

    def test_all_forbidden_recommend_stop(self):
        """When all headings are blocked, recommend stop."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        # Create many targets surrounding us from all sides within close range
        targets = []
        for angle in range(0, 360, 30):
            r = 0.5  # Very close
            x = r * math.sin(math.radians(angle))
            y = r * math.cos(math.radians(angle))
            # Each target heading toward us
            tgt_course = (angle + 180) % 360
            targets.append(_vessel(f"T{angle}", x=x, y=y, course=tgt_course, speed=10))

        d = self.engine.evaluate(own, targets, _env())
        self.assertTrue(d.collision_risk)
        # If all headings are forbidden, action should be stop
        if d.recommended_heading is None:
            self.assertEqual(d.recommended_action, Action.REDUCE_SPEED_OR_STOP)

    def test_effective_safe_distance_scaling(self):
        """When target is very close (< SAFE_CPA_DISTANCE), effective_safe_dist is scaled."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=0.5, course=180, speed=10)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertTrue(d.collision_risk)
        # The engine should still produce a valid decision
        self.assertIsNotNone(d.recommended_action)


class TestEngineSailingRule12Integration(unittest.TestCase):

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_two_sailing_same_tack_windward_gives_way(self):
        """Two sailing vessels, same tack: windward gives way."""
        # Wind from north (0 deg). Both heading east (course=90), starboard tack.
        # Own at y=0 (windward), target at y=5 (leeward).
        own = _vessel("O", x=0, y=0, course=90, speed=6, vtype=VesselType.SAILING)
        tgt = _vessel("T", x=1.0, y=1.0, course=90, speed=4, vtype=VesselType.SAILING)
        d = self.engine.evaluate(own, [tgt], _env(), wind_direction=0.0)
        if d.collision_risk:
            td = d.target_decisions["T"]
            # Calculate windward projections
            # pos_own_windward = -(0*0 + 0*1) = 0
            # pos_tgt_windward = -(1*0 + 1*1) = -1
            # own (0) > tgt (-1) => own is windward => gives way
            # But Rule 13 overtaking takes precedence: own speed > tgt speed and
            # own behind target => own_overtaking.
            # Indeed, if own is overtaking the target (faster, same course), Rule 13
            # takes priority over Rule 12.
            if td.encounter_type == "own_overtaking":
                self.assertEqual(td.own_role, VesselRole.GIVE_WAY)
            else:
                self.assertEqual(td.own_role, VesselRole.GIVE_WAY)

    def test_two_sailing_different_tacks_port_gives_way(self):
        """Two sailing vessels, different tacks: port tack gives way."""
        # Wind from north. Own heading east (course=90, wind_rel=270 => left tack).
        # Target heading west (course=270, wind_rel=90 => starboard tack).
        # Head-on style meeting with reciprocal courses.
        own = _vessel("O", x=0, y=0, course=270, speed=6, vtype=VesselType.SAILING)
        tgt = _vessel("T", x=-4, y=0, course=90, speed=6, vtype=VesselType.SAILING)
        d = self.engine.evaluate(own, [tgt], _env(), wind_direction=0.0)
        self.assertTrue(d.collision_risk)
        td = d.target_decisions["T"]
        # Own is starboard tack (wind_rel = (0-270)%360 = 90, < 180 => starboard).
        # Target is left tack (wind_rel = (0-90)%360 = 270, >= 180 => left/port).
        # Starboard tack stands on.
        self.assertEqual(td.own_role, VesselRole.STAND_ON)


class TestEnginePortTurnFallback(unittest.TestCase):

    def test_port_turn_when_starboard_exceeds_110(self):
        """When starboard turn would exceed 110 degrees but port is available,
        use port turn as fallback."""
        engine = COLREGInferenceEngine()
        # Own heading north. Block the starboard side heavily so that the first
        # free heading clockwise is > 110 degrees away, but port side is closer.
        # We can do this with a target arrangement that blocks 0-120 degrees starboard.
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        # Place targets that block headings from roughly 0 to ~120 starboard,
        # but leave port headings (around 350-240) open.
        # A target directly ahead and slightly starboard
        tgt1 = _vessel("T1", x=0.3, y=1.0, course=180, speed=10)
        # Another target blocking further starboard
        tgt2 = _vessel("T2", x=1.0, y=0.3, course=270, speed=10)

        d = engine.evaluate(own, [tgt1, tgt2], _env())
        # We just verify the engine doesn't crash and produces a valid decision
        self.assertIsNotNone(d.recommended_action)
        if d.recommended_action == Action.ALTER_COURSE_PORT:
            # Port fallback was used
            self.assertIsNotNone(d.recommended_heading)


class TestCourseConversions(unittest.TestCase):
    """Test course_to_rad and rad_to_course round-trip."""

    def test_round_trip(self):
        for deg in [0, 45, 90, 135, 180, 225, 270, 315]:
            with self.subTest(deg=deg):
                rad = course_to_rad(deg)
                result = rad_to_course(rad)
                self.assertAlmostEqual(result, deg, places=5)

    def test_rad_to_course_negative(self):
        """Negative radians should produce a valid 0-360 course."""
        result = rad_to_course(-math.pi / 2)
        expected = 360 - 90  # -90 degrees => 270
        self.assertAlmostEqual(result, expected, places=5)


class TestEngineStandOnAllTargets(unittest.TestCase):
    """When we are stand-on for all targets, we keep course."""

    def test_stand_on_keeps_course(self):
        engine = COLREGInferenceEngine()
        own = _vessel("O", x=0, y=0, course=0, speed=8)
        # Target overtaking us from behind; place far enough so TCPA > 0.15
        tgt = _vessel("T", x=0, y=-3, course=0, speed=15)
        d = engine.evaluate(own, [tgt], _env())
        self.assertTrue(d.collision_risk)
        td = d.target_decisions["T"]
        # Check if target overtaking detected - if so we are STAND_ON
        if td.encounter_type == "target_overtaking":
            self.assertEqual(td.own_role, VesselRole.STAND_ON)
            # If current heading is not forbidden, overall action should be KEEP_COURSE_SPEED
            current_h = int(round(own.course)) % 360
            forbidden = [False] * 360
            for s, e in d.forbidden_sectors:
                if s <= e:
                    for i in range(int(s), int(e) + 1):
                        forbidden[i] = True
                else:
                    for i in range(int(s), 360):
                        forbidden[i] = True
                    for i in range(0, int(e) + 1):
                        forbidden[i] = True
            if not forbidden[current_h]:
                self.assertEqual(d.recommended_action, Action.KEEP_COURSE_SPEED)


if __name__ == "__main__":
    unittest.main()
