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
        
        decision = self.engine.evaluate(own, target, env)
        self.assertFalse(decision.collision_risk)
        self.assertEqual(decision.encounter_type, "SAFE")
        self.assertEqual(decision.recommended_action, Action.N_A)

    def test_overtaking_give_way(self):
        # Наше судно идет сзади цели с большей скоростью (курс 0, позиция (0, 0), скорость 15)
        # Цель идет курсом 0, позиция (0, 1), скорость 8
        # Относительный пеленг от цели на нас: 180 градусов (прямо за кормой)
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=15, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=0, y=1, course=0, speed=8, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, target, env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.encounter_type, "OVERTAKING_GIVE_WAY")
        self.assertEqual(decision.own_role, VesselRole.GIVE_WAY)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_overtaking_stand_on(self):
        # Цель идет сзади нас с большей скоростью
        own = Vessel(name="OwnShip", x=0, y=1, course=0, speed=8, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=0, y=0, course=0, speed=15, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, target, env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.encounter_type, "OVERTAKING_STAND_ON")
        self.assertEqual(decision.own_role, VesselRole.STAND_ON)
        self.assertEqual(decision.recommended_action, Action.KEEP_COURSE_SPEED)

    def test_head_on(self):
        # Идем навстречу друг другу
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=0, y=1.5, course=180, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, target, env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.encounter_type, "HEAD_ON")
        self.assertEqual(decision.own_role, VesselRole.BOTH_GIVE_WAY)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_crossing_give_way(self):
        # Цель идет слева направо перед нами, находится с нашего правого борта
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=1.0, y=1.0, course=270, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, target, env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.encounter_type, "CROSSING_GIVE_WAY")
        self.assertEqual(decision.own_role, VesselRole.GIVE_WAY)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_crossing_stand_on(self):
        # Цель идет справа налево перед нами, находится с нашего левого борта
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=-1.0, y=1.0, course=90, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, target, env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.encounter_type, "CROSSING_STAND_ON")
        self.assertEqual(decision.own_role, VesselRole.STAND_ON)
        self.assertEqual(decision.recommended_action, Action.KEEP_COURSE_SPEED)

    def test_priority_sailing_beats_power(self):
        # Мы на моторной лодке, цель под парусом идет слева (казалось бы, мы на пересечении должны быть главными)
        # Но по Правилу 18 моторное уступает паруснику
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=-1.0, y=1.0, course=90, speed=10, vessel_type=VesselType.SAILING)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, target, env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.encounter_type, "PRIORITY_GIVE_WAY")
        self.assertEqual(decision.own_role, VesselRole.GIVE_WAY)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_priority_ram_beats_sailing(self):
        # Мы — судно, ограниченное в возможности маневрировать (RAM), цель — парусник
        # Парусник должен нам уступать
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=10, vessel_type=VesselType.RAM)
        target = Vessel(name="TargetShip", x=1.0, y=1.0, course=270, speed=10, vessel_type=VesselType.SAILING)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, target, env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.encounter_type, "PRIORITY_STAND_ON")
        self.assertEqual(decision.own_role, VesselRole.STAND_ON)
        self.assertEqual(decision.recommended_action, Action.KEEP_COURSE_SPEED)

    def test_restricted_visibility_ahead(self):
        # Ограниченная видимость. Цель впереди по правому борту.
        # В тумане Правило 19 предписывает избегать поворота влево, уступают оба.
        own = Vessel(name="OwnShip", x=0, y=0, course=0, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        target = Vessel(name="TargetShip", x=1.0, y=1.0, course=270, speed=10, vessel_type=VesselType.POWER_DRIVEN)
        env = Environment(visibility=Visibility.RESTRICTED)
        
        decision = self.engine.evaluate(own, target, env)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.encounter_type, "RESTRICTED_VISIBILITY_AHEAD")
        self.assertEqual(decision.own_role, VesselRole.BOTH_GIVE_WAY)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_sailing_rules_wind_crossing(self):
        # Два парусных судна, разные галсы. Wind from North (0 degrees).
        # OwnShip идет курсом 90 (ветер с левого борта -> правый галс)
        # TargetShip идет курсом 270 (ветер с правого борта -> левый галс)
        # Судно на левом галсу уступает. То есть TargetShip должен уступить.
        # Проверяем решение для OwnShip (должно быть STAND_ON)
        own = Vessel(name="OwnShip", x=0, y=0, course=90, speed=6, vessel_type=VesselType.SAILING)
        target = Vessel(name="TargetShip", x=1.0, y=0, course=270, speed=6, vessel_type=VesselType.SAILING)
        env = Environment(visibility=Visibility.GOOD)
        
        decision = self.engine.evaluate(own, target, env, wind_direction=0)
        self.assertTrue(decision.collision_risk)
        self.assertEqual(decision.encounter_type, "SAILING_CROSSING")
        self.assertEqual(decision.own_role, VesselRole.STAND_ON)
        self.assertEqual(decision.recommended_action, Action.KEEP_COURSE_SPEED)

if __name__ == "__main__":
    unittest.main()
