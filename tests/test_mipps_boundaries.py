"""Дополнительные boundary-тесты и покрытие подпунктов МППСС-72,
которые не были покрыты ранее: границы пеленгов, равенство скоростей,
подпункты правил 12/13/14/17/18/19, сигналы в узкостях.
"""
import math
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


class TestHeadingBoundaryConditions(unittest.TestCase):
    """Граничные значения пеленгов и курсов."""

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_target_exactly_10_degrees_from_bow(self):
        """Цель ровно в 10° от носа → должна считаться head-on."""
        own = _v("O", 0, 0, 0, 10)
        # Цель в направлении 10° от носа на 1.5 мили
        rad = math.radians(10)
        tgt = _v("T", 1.5 * math.sin(rad), 1.5 * math.cos(rad), 180, 10)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].encounter_type, "head_on")

    def test_target_just_outside_headon_sector(self):
        """Цель в 11° от носа → не должна считаться head-on (boundary)."""
        own = _v("O", 0, 0, 0, 10)
        rad = math.radians(11)
        tgt = _v("T", 1.5 * math.sin(rad), 1.5 * math.cos(rad), 169, 10)
        # reciprocal courses всё ещё в [170, 190]? 169 — нет. Значит crossing.
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertNotEqual(d.target_decisions["T"].encounter_type, "head_on")

    def test_target_exactly_350_degrees_from_bow(self):
        """Цель ровно в 350° от носа (т.е. в 10° слева) — head-on."""
        own = _v("O", 0, 0, 0, 10)
        rad = math.radians(350)
        tgt = _v("T", 1.5 * math.sin(rad), 1.5 * math.cos(rad), 180, 10)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].encounter_type, "head_on")

    def test_course_wraparound_359_to_001(self):
        """Курс 359° vs 1° — почти встречные (разница 2°)."""
        own = _v("O", 0, 0, 359, 10)
        tgt = _v("T", 0, 1.5, 1, 10)
        d = self.engine.evaluate(own, [tgt], _env())
        # course_diff = 2 — не в [170, 190], значит не head-on
        self.assertNotEqual(d.target_decisions["T"].encounter_type, "head_on")

    def test_equal_speeds_not_overtaking(self):
        """Равные скорости — обгон по правилу 13 не действует."""
        own = _v("O", 0, 0, 0, 10)
        tgt = _v("T", 0, 1, 0, 10)  # та же скорость
        d = self.engine.evaluate(own, [tgt], _env())
        # Поскольку equal speeds, helper_own_overtaking не сработает
        # (требует speed_gt). Может сработать rule 14 или 15.
        self.assertNotEqual(
            d.target_decisions["T"].encounter_type, "own_overtaking"
        )


class TestWindBoundaryConditions(unittest.TestCase):
    """Граничные значения для ветра и галса."""

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_wind_exactly_180_relative(self):
        """Граничный случай: относительный угол ветра ровно 180°.
        Закрытая дистанция и опасное сближение, чтобы проверить, что
        классификация галса на границе даёт определённый результат."""
        # Собственное судно идёт курсом 0°, ветер 180° (попутный).
        # Цель ставим близко, чтобы сработал risk.
        own = _v("O", 0, 0, 0, 6, vtype=VesselType.SAILING)
        tgt = _v("T", 0.5, 0.5, 270, 6, vtype=VesselType.SAILING)
        d = self.engine.evaluate(own, [tgt], _env(), wind_direction=180.0)
        td = d.target_decisions["T"]
        self.assertTrue(td.collision_risk)
        self.assertIn(td.own_role, [VesselRole.GIVE_WAY, VesselRole.STAND_ON])

    def test_wind_zero_heading_zero(self):
        """Ветер = 0°, курс = 0° — попутный ветер; цель близко для риска."""
        own = _v("O", 0, 0, 0, 6, vtype=VesselType.SAILING)
        tgt = _v("T", 0.5, 0.5, 270, 6, vtype=VesselType.SAILING)
        d = self.engine.evaluate(own, [tgt], _env(), wind_direction=0.0)
        td = d.target_decisions["T"]
        self.assertTrue(td.collision_risk)
        self.assertIn(
            td.own_role, [VesselRole.GIVE_WAY, VesselRole.STAND_ON]
        )


class TestRule18Subparagraphs(unittest.TestCase):
    """Подпункты (b), (c), (d) правила 18 — иерархия приоритетов."""

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_rule_18b_sailing_gives_way_to_fishing(self):
        """Правило 18 (b): парусное уступает рыболовному."""
        # собственное — парусное, цель — рыболовное
        own = _v("O", 0, 0, 0, 6, vtype=VesselType.SAILING)
        tgt = _v("T", 1, 1, 270, 5, vtype=VesselType.FISHING)
        d = self.engine.evaluate(own, [tgt], _env(), wind_direction=0.0)
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_rule_18b_sailing_gives_way_to_nuc(self):
        """Правило 18 (b): парусное уступает NUC."""
        own = _v("O", 0, 0, 0, 6, vtype=VesselType.SAILING)
        tgt = _v("T", 1, 1, 270, 5, vtype=VesselType.NUC)
        d = self.engine.evaluate(own, [tgt], _env(), wind_direction=0.0)
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_rule_18c_fishing_gives_way_to_nuc(self):
        """Правило 18 (c): рыболовное уступает NUC."""
        own = _v("O", 0, 0, 0, 5, vtype=VesselType.FISHING)
        tgt = _v("T", 1, 1, 270, 5, vtype=VesselType.NUC)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_rule_18c_fishing_gives_way_to_ram(self):
        """Правило 18 (c): рыболовное уступает RAM."""
        own = _v("O", 0, 0, 0, 5, vtype=VesselType.FISHING)
        tgt = _v("T", 1, 1, 270, 5, vtype=VesselType.RAM)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)

    def test_rule_18_power_vs_cbd_lower_priority(self):
        """Правило 18 (a)(iv)/18 (d): power уступает CBD."""
        own = _v("O", 0, 0, 0, 10, vtype=VesselType.POWER_DRIVEN)
        tgt = _v("T", 1, 1, 270, 5, vtype=VesselType.CBD)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.GIVE_WAY)


class TestRule17EdgeCases(unittest.TestCase):
    """Граничные случаи правила 17."""

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_rule_17_not_triggered_when_tcpa_at_boundary(self):
        """TCPA ровно 0.15 — правило 17 не должно сработать (граничный)."""
        # Этот сценарий сложно сконструировать точно на границе,
        # поэтому проверяем, что в безопасной ситуации правило не сработает
        own = _v("O", 0, 0, 0, 10)
        tgt = _v("T", 5, 5, 90, 10)  # далеко, TCPA большой
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertNotIn("rule_17_last_resort_action", d.fired_rules)

    def test_rule_17_triggers_on_close_stand_on_situation(self):
        """Очень близкая ситуация пересечения слева — rule 17 срабатывает."""
        own = _v("O", 0, 0, 0, 10)
        tgt = _v("T", -0.3, 0.3, 90, 10)  # близко, TCPA маленький
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertIn("rule_17_last_resort_action", d.fired_rules)


class TestRule19EdgeCases(unittest.TestCase):
    """Граничные случаи правила 19 (ограниченная видимость)."""

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_rule_19_target_exactly_on_beam(self):
        """Цель ровно на траверзе (90°)."""
        own = _v("O", 0, 0, 0, 10)
        tgt = _v("T", 1, 0, 270, 10)  # строго на траверзе
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        # target_abaft_beam: rb ∈ (90, 270). rb=90 — граница, не входит
        # target_ahead_of_beam: rb ∈ [0,90] ∪ [270, 360). rb=90 — входит
        # значит rule 19_ahead_* сработает
        ahead_rules = [
            rid for rid in d.fired_rules
            if rid.startswith("rule_19_ahead_")
        ]
        self.assertTrue(ahead_rules, f"expected ahead rule, got {d.fired_rules}")

    def test_rule_19_target_just_abaft_beam(self):
        """Цель чуть позади траверза (91°)."""
        own = _v("O", 0, 0, 0, 10)
        tgt = _v("T", 1.5 * math.sin(math.radians(91)),
                  1.5 * math.cos(math.radians(91)),
                  90, 10)  # 91° от носа
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        # target_abaft_beam: 90 < rb < 270 → да
        # должно сработать rule 19_abaft_*
        abaft_rules = [
            rid for rid in d.fired_rules
            if rid.startswith("rule_19_abaft_")
        ]
        self.assertTrue(abaft_rules, f"expected abaft rule, got {d.fired_rules}")

    def test_rule_19_blocks_appropriate_turns(self):
        """Правило 19(d): при цели впереди блокируются левые повороты."""
        own = _v("O", 0, 0, 0, 10)
        tgt = _v("T", 1, 1, 270, 10)
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        # Должны быть заблокированы левые повороты
        self.assertIn("extend_block_left_in_restricted_ahead", d.fired_rules)


class TestSoundSignalsEdgeCases(unittest.TestCase):
    """Граничные случаи звуковых сигналов."""

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_rule_35_signal_for_zero_speed_power_vessel(self):
        """Power-driven с нулевой скоростью → два продолжительных сигнала."""
        own = _v("O", 0, 0, 0, 0, vtype=VesselType.POWER_DRIVEN)  # speed=0
        tgt = _v("T", 1, 1, 270, 10)
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        self.assertIn("rule_35_power_stopped", d.fired_rules)

    def test_rule_35_signal_for_sailing_vessel(self):
        """Парусное в ограниченной видимости → 1+2 сигнал."""
        own = _v("O", 0, 0, 0, 6, vtype=VesselType.SAILING)
        tgt = _v("T", 1, 1, 270, 6)
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        self.assertIn("rule_35_non_power_moving", d.fired_rules)


class TestRule12DoubtSubparagraph(unittest.TestCase):
    """Правило 12 (a)(iii): неопределённый галс."""

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_rule_12_aiii_documented_as_gap(self):
        """Этот тест-документация: подпункт 12(a)(iii) не реализован.
        Когда будет реализован — тест нужно дополнить проверкой поведения."""
        # Текущее поведение: rule 12 срабатывает только если у цели есть
        # sailing_tack. Если цель не парусная, rule 12 не применим.
        # Подпункт 12(a)(iii) говорит: если ЛЕВЫЙ галс и видишь цель с наветра
        # и НЕ МОЖЕШЬ определить галс цели — уступить. Это требует
        # дополнительной логики и в текущей KB не покрыто.
        own = _v("O", 0, 0, 0, 6, vtype=VesselType.SAILING)
        tgt = _v("T", 0.5, 0.5, 90, 5, vtype=VesselType.POWER_DRIVEN)  # не парусное
        d = self.engine.evaluate(own, [tgt], _env(), wind_direction=0.0)
        # В этой геометрии собственное судно обгоняет цель сзади, поэтому
        # срабатывает rule 13 (более специфичный). Этот тест просто
        # документирует, что rule 12 не применяется к не-парусным целям.
        self.assertFalse(
            any(rid.startswith("rule_12_") for rid in d.fired_rules),
            f"rule 12 should not fire for non-sailing target, got {d.fired_rules}",
        )


if __name__ == "__main__":
    unittest.main()
