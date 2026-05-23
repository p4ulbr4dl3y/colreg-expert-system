import unittest
from src.models import Vessel, VesselType, VesselRole, Action, Visibility, Environment
from src.engine import COLREGInferenceEngine

class TestCOLREGScenarios(unittest.TestCase):
    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_safe_encounter(self):
        # Суда далеко друг от друга (10 миль) и расходятся
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=10, y=10, course=90, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, [target], env)
        self.assertFalse(decision.collision_risk)
        self.assertEqual(decision.recommended_action, Action.N_A)

    def test_overtaking_give_way(self):
        # Наше судно идет сзади цели с большей скоростью (курс 0, позиция (0, 0), скорость 15)
        # Цель идет курсом 0, позиция (0, 1), скорость 8
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=15, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=0, y=1, course=0, speed=8, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, [target], env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.own_role, VesselRole.GIVE_WAY)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)
        # Проверяем, что текущий курс 0° заблокирован в опасных секторах
        self.assertTrue(any((start <= 0 <= end) if start <= end else (0 >= start or 0 <= end) for start, end in decision.forbidden_sectors))

    def test_head_on(self):
        # Идем навстречу друг другу
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=0, y=1.5, course=180, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, [target], env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)
        self.assertIsNotNone(decision.recommended_heading)

    def test_crossing_give_way(self):
        # Цель идет справа налево перед нами, находится с нашего правого борта
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=1.0, y=1.0, course=270, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, [target], env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.own_role, VesselRole.GIVE_WAY)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_priority_sailing_beats_power(self):
        # Мы на моторном, цель под парусом идет слева. Моторное уступает паруснику.
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=-1.0, y=1.0, course=90, speed=10, vessel_type=VesselType.SAILING)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, [target], env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.own_role, VesselRole.GIVE_WAY)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_restricted_visibility_ahead(self):
        # Ограниченная видимость. Цель впереди по правому борту.
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=1.0, y=1.0, course=270, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.RESTRICTED)
        
        decision = self.engine.evaluate(own, [target], env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_sailing_rules_wind_crossing(self):
        # Два парусных судна, разные галсы. Ветер с Севера (0 градусов).
        # OwnShip идет курсом 270 (ветер с правого борта -> правый галс -> STAND_ON)
        # TargetShip идет курсом 90 (ветер с левого борта -> левый галс -> GIVE_WAY)
        own = Vessel(name="OwnShip", x=0, y=0, course=270, speed=6, vessel_type=VesselType.SAILING)
        target = Vessel(name="TargetShip", x=-4.0, y=0, course=90, speed=6, vessel_type=VesselType.SAILING)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, [target], env, wind_direction=0)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.target_decisions["TargetShip"].own_role, VesselRole.STAND_ON)

    def test_multi_target_conflict(self):
        # Сложный случай: 2 цели одновременно
        # Цель A: справа спереди (1.0, 1.0), курс 270 (пересечение, мы уступаем)
        # Цель B: слева спереди (-1.0, 1.0), курс 90 (пересечение, цель уступает, но мы должны учитывать ее при маневре)
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=12, vessel_type=VesselType.POWER_DRIVEN)
        target_a = Vessel(name="TargetA", x=1.0, y=1.0, course=270, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        target_b = Vessel(name="TargetB", x=-1.0, y=1.0, course=90, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, [target_a, target_b], env)
        self.assertTrue(decision.collision_risk)
        
        # Решение должно найти безопасный курс
        self.assertIsNotNone(decision.recommended_heading)
        rec_heading = decision.recommended_heading
        
        # Проверяем, что выбранный курс не входит в опасные сектора
        for start, end in decision.forbidden_sectors:
            if start <= end:
                self.assertFalse(start <= rec_heading <= end)
            else: # Переход через 0
                self.assertFalse(rec_heading >= start or rec_heading <= end)

    def test_maneuverability_turning_limit_warning(self):
        # Наше судно имеет большой радиус разворота (0.8 миль) и высокую скорость (20 узлов)
        # Цель прямо по носу очень близко (0.3 мили) и идет навстречу (head-on)
        # Времени до CPA критически мало, развернуться не успеем.
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=20, vessel_type=VesselType.POWER_DRIVEN, min_turning_radius=0.8)
        target = Vessel(name="TargetShip", x=0, y=0.3, course=180, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, [target], env)
        self.assertTrue(decision.collision_risk)
        # Из-за инерции маневр физически невозможен в срок
        self.assertFalse(decision.maneuver_possible)
        # Проверяем, что в объяснении есть предупреждение
        warning_found = any("физическое ограничение:" in line for line in decision.explanation)
        self.assertTrue(warning_found)

if __name__ == "__main__":
    unittest.main()
