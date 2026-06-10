"""Тесты трассировки вывода: проверка, что в известных сценариях
срабатывают ожидаемые правила МППСС-72, и что Decision.trace
содержит полный путь доказательства.
"""
import unittest

from src.inference import COLREGInferenceEngine
from src.models import (
    Action,
    Environment,
    Vessel,
    VesselRole,
    VesselType,
    Visibility,
)


def _v(name, x, y, course, speed, vtype=VesselType.POWER_DRIVEN, radius=0.25):
    return Vessel(name, x, y, course, speed, vtype, min_turning_radius=radius)


def _env(vis=Visibility.GOOD, narrow=False, tss=False):
    return Environment(visibility=vis, in_narrow_channel=narrow, in_tss=tss)


class TestFiredRules(unittest.TestCase):
    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_head_on_fires_rule_14(self):
        """Встречные курсы → должно сработать правило 14."""
        own = _v("O", 0, 0, 0, 10)
        tgt = _v("T", 0, 1.5, 180, 10)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertIn("rule_14_head_on", d.fired_rules)
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.BOTH_GIVE_WAY)

    def test_crossing_stbd_fires_rule_15(self):
        """Цель справа, пересечение → правило 15, GIVE_WAY."""
        own = _v("O", 0, 0, 0, 10)
        tgt = _v("T", 3, 3, 270, 10)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertIn("rule_15_crossing_stbd", d.fired_rules)
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_overtaking_fires_rule_13(self):
        """Обгон с нашей стороны → правило 13, GIVE_WAY."""
        own = _v("O", 0, 0, 0, 15)
        tgt = _v("T", 0, 1, 0, 8)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertIn("rule_13_own_overtaking", d.fired_rules)
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_priority_rule_18_fires_for_power_vs_sailing(self):
        """Power-driven vs sailing → правило 18, GIVE_WAY."""
        own = _v("O", 0, 0, 0, 10, vtype=VesselType.POWER_DRIVEN)
        tgt = _v("T", -1, 1, 90, 6, vtype=VesselType.SAILING)
        d = self.engine.evaluate(own, [tgt], _env(), wind_direction=0.0)
        self.assertIn("rule_18_give_way", d.fired_rules)
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_sailing_rule_12_fires(self):
        """Два парусных на разных галсах → правило 12."""
        own = _v("O", 0, 0, 270, 6, vtype=VesselType.SAILING)
        tgt = _v("T", -4, 0, 90, 6, vtype=VesselType.SAILING)
        d = self.engine.evaluate(own, [tgt], _env(), wind_direction=0.0)
        # должно сработать хотя бы одно из правил 12
        rule_12_fired = any(
            rid.startswith("rule_12_") for rid in d.fired_rules
        )
        self.assertTrue(rule_12_fired, f"expected rule_12_*, got {d.fired_rules}")

    def test_rule_19_fires_in_restricted_visibility(self):
        """Ограниченная видимость → правило 19."""
        own = _v("O", 0, 0, 0, 10)
        tgt = _v("T", 1, 1, 270, 10)
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        rule_19_fired = any(rid.startswith("rule_19_") for rid in d.fired_rules)
        self.assertTrue(rule_19_fired, f"expected rule_19_*, got {d.fired_rules}")

    def test_rule_17_fires_for_critical_tcpa(self):
        """Критический TCPA → правило 17, last_resort."""
        own = _v("O", 0, 0, 0, 10)
        tgt = _v("T", -0.3, 0.3, 90, 10)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertIn("rule_17_last_resort_action", d.fired_rules)

    def test_sound_signal_rule_34_fires(self):
        """Power-driven starboard action → rule 34, one short blast."""
        own = _v("O", 0, 0, 0, 10, vtype=VesselType.POWER_DRIVEN)
        tgt = _v("T", 1, 1, 270, 10)
        d = self.engine.evaluate(own, [tgt], _env())
        sound_rules = [
            rid for rid in d.fired_rules
            if rid.startswith("rule_34_") or rid.startswith("rule_35_")
        ]
        self.assertTrue(sound_rules, f"expected sound signal rule, got {d.fired_rules}")

    def test_trace_iterations_recorded(self):
        own = _v("O", 0, 0, 0, 10)
        tgt = _v("T", 1, 1, 270, 10)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertGreater(d.trace.iterations, 0)
        self.assertGreater(d.trace.fired_count, 0)
        self.assertEqual(len(d.trace.steps), d.trace.fired_count)


class TestTargetDecisionFiredRules(unittest.TestCase):
    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_target_decision_has_fired_rules(self):
        own = _v("O", 0, 0, 0, 10)
        tgt = _v("T", 1, 1, 270, 10)
        d = self.engine.evaluate(own, [tgt], _env())
        td = d.target_decisions["T"]
        self.assertTrue(len(td.fired_rules) > 0)
        # каждое правило должно начинаться с "rule_" или "extend_"
        for rid in td.fired_rules:
            self.assertTrue(
                rid.startswith("rule_") or rid.startswith("extend_"),
                f"unexpected rule id: {rid}",
            )


if __name__ == "__main__":
    unittest.main()
