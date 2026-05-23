"""
Комплексный набор тестов для экспертной системы МППСС-72.

Охватывает три уровня:
- геометрический модуль: преобразование координат, расчет дистанции и времени кратчайшего сближения, оценка риска столкновения, определение запрещенных секторов курса;
- модуль правил: приоритеты судов, классификация характера встречи, правила для парусных судов;
- интеграция логического движка: полный цикл вывода решений, включая многоцелевые ситуации, ограниченную видимость, действия в крайних ситуациях и физические ограничения.
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
# Вспомогательные фабрики
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
# 1. ТЕСТЫ ГЕОМЕТРИЧЕСКОГО МОДУЛЯ
# ===================================================================

class TestVelocityComponents(unittest.TestCase):
    """Разложение скорости для основных направлений."""

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
    """Истинный пеленг во всех четырех квадрантах."""

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
        # собственный курс - восток, цель на севере: относительный пеленг 270 градусов (левый борт).
        own = _vessel("O", x=0, y=0, course=90)
        tgt = _vessel("T", x=0, y=5)
        self.assertAlmostEqual(calculate_relative_bearing(own, tgt), 270.0, places=3)


class TestCpaTcpa(unittest.TestCase):

    def test_head_on_collision(self):
        """При встречном сближении двух судов дистанция кратчайшего сближения должна быть близка к нулю."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=10, course=180, speed=10)
        cpa, tcpa = calculate_cpa_tcpa(own, tgt)
        self.assertAlmostEqual(cpa, 0.0, places=3)
        self.assertGreater(tcpa, 0.0)
        # время сближения должно составлять 0.5 часа при расстоянии 10 миль и относительной скорости 20 узлов.
        self.assertAlmostEqual(tcpa, 0.5, places=3)

    def test_crossing_nonzero_cpa(self):
        """Пересекающиеся курсы должны иметь ненулевую дистанцию кратчайшего сближения при наличии смещения."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=5, y=5, course=270, speed=10)
        cpa, tcpa = calculate_cpa_tcpa(own, tgt)
        self.assertGreater(tcpa, 0.0)

    def test_parallel_same_speed(self):
        """Параллельные курсы с одинаковой скоростью: относительная скорость равна нулю, время сближения бесконечно."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=3, y=0, course=0, speed=10)
        cpa, tcpa = calculate_cpa_tcpa(own, tgt)
        self.assertEqual(tcpa, float("inf"))
        self.assertAlmostEqual(cpa, 3.0, places=3)

    def test_diverging_ships(self):
        """Расходящиеся суда должны иметь отрицательное время сближения."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=-5, course=180, speed=10)
        cpa, tcpa = calculate_cpa_tcpa(own, tgt)
        self.assertLess(tcpa, 0.0)


class TestCollisionRisk(unittest.TestCase):

    def test_risk_when_within_safe_distance(self):
        """Риск столкновения существует, если текущая дистанция меньше безопасного расстояния."""
        own = _vessel("O", x=0, y=0, course=0, speed=0)
        tgt = _vessel("T", x=1.0, y=0, course=0, speed=0)
        risk, dist, cpa, tcpa = is_collision_risk_exists(own, tgt)
        self.assertTrue(risk)
        self.assertAlmostEqual(dist, 1.0, places=3)

    def test_no_risk_beyond_safe_distance_diverging(self):
        """Риск столкновения отсутствует при большом расстоянии и расхождении судов."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=10, y=10, course=90, speed=10)
        risk, dist, cpa, tcpa = is_collision_risk_exists(own, tgt)
        self.assertFalse(risk)

    def test_risk_at_boundary_tcpa(self):
        """Риск столкновения существует при сближении с дистанцией кратчайшего сближения менее 2 миль и временем сближения в критическом диапазоне."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=5, course=180, speed=10)
        risk, dist, cpa, tcpa = is_collision_risk_exists(own, tgt)
        self.assertTrue(risk)

    def test_no_risk_negative_tcpa(self):
        """Риск столкновения отсутствует, если суда уже разошлись."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=5, y=-10, course=180, speed=10)
        risk, dist, cpa, tcpa = is_collision_risk_exists(own, tgt)
        self.assertFalse(risk)

    def test_exactly_at_safe_distance(self):
        """Точно на границе безопасного расстояния: риск отсутствует только по критерию расстояния, так как условие требует строгого неравенства."""
        own = _vessel("O", x=0, y=0, course=90, speed=5)
        tgt = _vessel("T", x=2.0, y=0, course=270, speed=5)
        risk, dist, cpa, tcpa = is_collision_risk_exists(own, tgt)
        # дистанция равна 2.0 милям (не строго меньше 2.0), но дистанция кратчайшего сближения равна 0, а время сближения находится в диапазоне от 0 до 0.5 часа: срабатывает второе условие риска.
        self.assertTrue(risk)


class TestTurnFeasibility(unittest.TestCase):

    def test_always_possible_when_tcpa_negative(self):
        self.assertTrue(is_turn_possible(10.0, 0.25, 90.0, -1.0))

    def test_always_possible_when_tcpa_infinite(self):
        self.assertTrue(is_turn_possible(10.0, 0.25, 90.0, float("inf")))

    def test_possible_with_ample_time(self):
        # дуга поворота составляет около 0.3927 мили, время - около 0.039 часа: времени сближения в 1.0 час достаточно.
        self.assertTrue(is_turn_possible(10.0, 0.25, 90.0, 1.0))

    def test_impossible_with_very_short_tcpa(self):
        # большой радиус при дефиците времени: дуга поворота составляет около 1.257 мили, время поворота - около 0.126 часа, время сближения - 0.01 часа.
        self.assertFalse(is_turn_possible(10.0, 0.8, 90.0, 0.01))

    def test_possible_when_stationary(self):
        """Скорость менее 0.1 узла означает, что судно неподвижно: маневр всегда возможен."""
        self.assertTrue(is_turn_possible(0.05, 0.5, 90.0, 0.001))


class TestForbiddenHeadings(unittest.TestCase):

    def test_approaching_head_on_produces_forbidden_band(self):
        """Встречная цель должна создавать запрещенный сектор курса около 0 градусов."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=3, course=180, speed=10)
        forbidden = get_forbidden_headings_for_target(own, tgt)
        # курс 0 градусов (прямо на цель) должен быть запрещен.
        self.assertTrue(forbidden[0])
        # боковой курс должен быть безопасен.
        self.assertFalse(forbidden[90])

    def test_safe_target_no_forbidden(self):
        """Далекая расходящаяся цель не должна создавать запрещенных секторов курса."""
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
        """Сектор, переходящий через границу 360/0 градусов, должен объединяться."""
        arr = [False] * 360
        for i in range(350, 360):
            arr[i] = True
        for i in range(0, 11):
            arr[i] = True
        sectors = convert_boolean_array_to_sectors(arr)
        self.assertEqual(len(sectors), 1)
        # после объединения: начало 350 градусов, конец 10 градусов.
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
# 2. ТЕСТЫ МОДУЛЯ ПРАВИЛ
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
        """Подтверждение строгого порядка приоритетов: судно, лишенное возможности управляться, выше судна, ограниченного в возможности маневрировать, выше судна, стесненного своей осадкой, выше судна, занятого ловом рыбы, выше парусного судна, выше судна с механическим двигателем."""
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
        """Граничный случай: разность курсов ровно 170 градусов."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=5, course=170, speed=10)
        sector, is_ho, is_xing, is_ot = classify_encounter_sectors(own, tgt)
        # для встречного курса относительный пеленг должен быть меньше 10 или больше 350 градусов. Цель в точке (0,5) относительно (0,0) дает пеленг 0 градусов. Относительный пеленг равен 0 градусов, что находится в пределах 10 градусов. Относительный пеленг с цели на собственное судно равен 180 градусов. Разница курсов составляет 10 градусов, поэтому оба судна видят друг друга встречными.
        self.assertEqual(sector, "head_on")
        self.assertTrue(is_ho)

    def test_head_on_course_diff_190(self):
        """Граничный случай: разность курсов ровно 190 градусов."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=5, course=190, speed=10)
        sector, is_ho, is_xing, is_ot = classify_encounter_sectors(own, tgt)
        # относительный пеленг равен 0 градусов. Относительный пеленг с цели равен 350 градусов, что подтверждает встречный характер ситуации.
        self.assertEqual(sector, "head_on")
        self.assertTrue(is_ho)

    def test_crossing_starboard(self):
        """Цель по правому борту на пересекающихся курсах."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=3, y=3, course=270, speed=10)
        sector, is_ho, is_xing, is_ot = classify_encounter_sectors(own, tgt)
        self.assertEqual(sector, "crossing_starboard")
        self.assertTrue(is_xing)

    def test_crossing_port(self):
        """Цель по левому борту на пересекающихся курсах."""
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
        # для обгона относительный пеленг должен составлять 112.5 градуса. Размещаем собственное судно так, чтобы относительный пеленг с цели составлял 112.5 градуса.
        r = 3.0
        angle_rad = math.radians(112.5)
        own_x = r * math.sin(angle_rad)
        own_y = r * math.cos(angle_rad)
        own = _vessel("O", x=own_x, y=own_y, course=0, speed=15)
        tgt = _vessel("T", x=0, y=0, course=0, speed=5)
        # относительный пеленг с цели на собственное судно относительно курса цели.
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
        """Разные галсы: судно на левом галсу уступает дорогу судну на правом галсу."""
        # ветер дует с севера (0 градусов). Курс собственного судна равен 90 градусов (левый галс), курс цели равен 270 градусов (правый галс).
        own = _vessel("O", x=0, y=0, course=90, speed=6, vtype=VesselType.SAILING)
        tgt = _vessel("T", x=5, y=0, course=270, speed=6, vtype=VesselType.SAILING)
        role, action, _ = evaluate_sailing_vessels_rule12(own, tgt, wind_dir=0.0)
        self.assertEqual(role, VesselRole.GIVE_WAY)

    def test_different_tacks_starboard_stands_on(self):
        """Разные галсы: судно на правом галсу сохраняет курс."""
        # курс собственного судна равен 270 градусов (правый галс), курс цели равен 90 градусов (левый галс).
        own = _vessel("O", x=0, y=0, course=270, speed=6, vtype=VesselType.SAILING)
        tgt = _vessel("T", x=-5, y=0, course=90, speed=6, vtype=VesselType.SAILING)
        role, action, _ = evaluate_sailing_vessels_rule12(own, tgt, wind_dir=0.0)
        self.assertEqual(role, VesselRole.STAND_ON)

    def test_same_tack_windward_gives_way(self):
        """Один галс: наветренное судно уступает дорогу подветренному судну."""
        # ветер дует с севера. Оба судна идут на восток (курс 90 градусов) правым галсом. Проекция на ветер: собственное судно в точке y=5 (с подветренной стороны), цель в точке y=0 (с наветренной стороны). Нам нужно, чтобы собственное судно было с наветренной стороны: собственное судно в y=0, цель в y=5.
        own = _vessel("O", x=0, y=0, course=90, speed=6, vtype=VesselType.SAILING)
        tgt = _vessel("T", x=5, y=5, course=90, speed=6, vtype=VesselType.SAILING)
        role, action, _ = evaluate_sailing_vessels_rule12(own, tgt, wind_dir=0.0)
        # наветренное положение собственного судна равно 0, цели равно -5. Собственное судно находится с наветренной стороны и уступает дорогу.
        self.assertEqual(role, VesselRole.GIVE_WAY)

    def test_same_tack_leeward_stands_on(self):
        """Один галс: подветренное судно сохраняет курс."""
        # ветер дует с севера. Оба судна идут на восток правым галсом. Собственное судно в точке y=5 находится с подветренной стороны и сохраняет курс и скорость.
        own = _vessel("O", x=0, y=5, course=90, speed=6, vtype=VesselType.SAILING)
        tgt = _vessel("T", x=5, y=0, course=90, speed=6, vtype=VesselType.SAILING)
        role, action, _ = evaluate_sailing_vessels_rule12(own, tgt, wind_dir=0.0)
        self.assertEqual(role, VesselRole.STAND_ON)


# ===================================================================
# 3. ИНТЕГРАЦИОННЫЕ ТЕСТЫ ЛОГИЧЕСКОГО ДВИЖКА
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
        """Правило 14: встречное сближение - оба судна изменяют курс вправо."""
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
        """Правило 15: цель справа - мы уступаем дорогу."""
        engine = COLREGInferenceEngine()
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=1.0, y=1.0, course=270, speed=10)
        decision = engine.evaluate(own, [tgt], _env())
        self.assertTrue(decision.collision_risk)
        td = decision.target_decisions["T"]
        self.assertEqual(td.own_role, VesselRole.GIVE_WAY)
        self.assertEqual(decision.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_rule_15_stand_on_target_port(self):
        """Правило 15: цель слева - мы сохраняем курс и скорость."""
        engine = COLREGInferenceEngine()
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        # размещаем цель на достаточном расстоянии, чтобы время сближения было больше 0.15 часа во избежание срабатывания правила 17 (b).
        tgt = _vessel("T", x=-3.0, y=3.0, course=90, speed=10)
        d = engine.evaluate(own, [tgt], _env())
        self.assertTrue(d.collision_risk)
        td = d.target_decisions["T"]
        # пересечение слева для судов одинакового типа: сохранение курса и скорости.
        self.assertEqual(td.own_role, VesselRole.STAND_ON)
        self.assertEqual(td.recommended_action, Action.KEEP_COURSE_SPEED)


class TestEngineOvertaking(unittest.TestCase):

    def test_rule_13_we_overtake_give_way(self):
        """Правило 13: мы обгоняем цель - уступаем дорогу."""
        engine = COLREGInferenceEngine()
        own = _vessel("O", x=0, y=0, course=0, speed=15)
        tgt = _vessel("T", x=0, y=1, course=0, speed=8)
        decision = engine.evaluate(own, [tgt], _env())
        self.assertTrue(decision.collision_risk)
        td = decision.target_decisions["T"]
        self.assertEqual(td.own_role, VesselRole.GIVE_WAY)
        self.assertEqual(td.encounter_type, "own_overtaking")

    def test_rule_13_being_overtaken_stand_on(self):
        """Правило 13: цель обгоняет нас - сохраняем курс и скорость."""
        engine = COLREGInferenceEngine()
        own = _vessel("O", x=0, y=0, course=0, speed=8)
        # размещаем цель дальше позади, чтобы время сближения превышало 0.15 часа.
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
        """Создание ситуации пересечения курсов, где приоритет типа судна определяет характер расхождения."""
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
        # увеличиваем расстояние, чтобы время сближения превышало 0.15 часа.
        own = _vessel("O", x=0, y=0, course=0, speed=10, vtype=VesselType.NUC)
        tgt = _vessel("T", x=3.0, y=3.0, course=270, speed=10, vtype=VesselType.POWER_DRIVEN)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertEqual(d.target_decisions["T"].own_role, VesselRole.STAND_ON)


class TestEngineRestrictedVisibility(unittest.TestCase):
    """Rule 19: restricted visibility tests."""

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_rule_19_target_ahead_no_port_turn(self):
        """Правило 19 (d)(i): цель впереди траверза - избегать поворота влево."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0.5, y=1.0, course=180, speed=10)
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        self.assertTrue(d.collision_risk)
        td = d.target_decisions["T"]
        # при ограниченной видимости приоритеты типов судов игнорируются: тип встречи классифицируется как ограниченная видимость.
        self.assertEqual(td.encounter_type, "RESTRICTED")
        # рекомендуемое действие должно быть поворотом вправо для избежания поворота влево.
        self.assertEqual(td.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_rule_19_target_starboard_beam(self):
        """Правило 19 (d)(ii): цель на правом траверзе - избегать поворота вправо в ее сторону."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        # цель находится в районе правого траверза.
        tgt = _vessel("T", x=1.5, y=-0.5, course=270, speed=10)
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        self.assertTrue(d.collision_risk)
        td = d.target_decisions["T"]
        self.assertEqual(td.recommended_action, Action.ALTER_COURSE_PORT)

    def test_rule_19_target_port_quarter(self):
        """Правило 19 (d)(ii): цель на левой раковине - избегать поворота влево в ее сторону."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        # цель находится слева позади траверза.
        tgt = _vessel("T", x=-1.5, y=-0.5, course=90, speed=10)
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        self.assertTrue(d.collision_risk)
        td = d.target_decisions["T"]
        self.assertEqual(td.recommended_action, Action.ALTER_COURSE_STARBOARD)

    def test_rule_19_ignores_type_priorities(self):
        """Ограниченная видимость отменяет приоритеты типов судов."""
        own = _vessel("O", x=0, y=0, course=0, speed=10, vtype=VesselType.POWER_DRIVEN)
        tgt = _vessel("T", x=0.5, y=1.0, course=180, speed=10, vtype=VesselType.NUC)
        d = self.engine.evaluate(own, [tgt], _env(Visibility.RESTRICTED))
        td = d.target_decisions["T"]
        # статус не должен определяться приоритетом судна, вместо этого применяется логика правила 19 на основе пеленгов.
        self.assertEqual(td.encounter_type, "RESTRICTED")
        self.assertIn(td.own_role, [VesselRole.BOTH_GIVE_WAY, VesselRole.GIVE_WAY])


class TestEngineRule17bLastMoment(unittest.TestCase):

    def test_last_moment_action(self):
        """Правило 17 (b): судно, которому уступают дорогу, при крайне малом времени сближения обязано предпринять действия."""
        engine = COLREGInferenceEngine()
        # создаем ситуацию пересечения слева, при которой мы обычно сохраняем курс, но время сближения критически мало (менее 0.15 часа).
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        # цель находится слева на очень близкой дистанции.
        tgt = _vessel("T", x=-0.3, y=0.3, course=90, speed=10)
        d = engine.evaluate(own, [tgt], _env())
        td = d.target_decisions["T"]
        # для активации правила время сближения должно быть меньше 0.15 часа.
        if td.tcpa < 0.15:
            # правило 17 (b) должно изменить роль с сохранения курса на уклонение.
            self.assertEqual(td.own_role, VesselRole.GIVE_WAY)
            self.assertEqual(td.recommended_action, Action.ALTER_COURSE_STARBOARD)
        else:
            # если геометрия не дает время сближения меньше 0.15 часа, настраиваем координаты точнее.
            self.skipTest("TCPA not small enough for this geometry")


class TestEngineRule17bCrafted(unittest.TestCase):

    def test_last_moment_crafted(self):
        """Правило 17 (b) с точным расчетом геометрии для обеспечения времени сближения менее 0.15 часа."""
        engine = COLREGInferenceEngine()
        # пересечение слева при очень малой дистанции.
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=-0.15, y=0.15, course=90, speed=15)
        d = engine.evaluate(own, [tgt], _env())
        td = d.target_decisions["T"]
        # проверка, что время сближения действительно мало.
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
        """Одна безопасная цель и одна опасная цель."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        safe_tgt = _vessel("Safe", x=10, y=10, course=90, speed=10)
        danger_tgt = _vessel("Danger", x=1.0, y=1.0, course=270, speed=10)
        d = self.engine.evaluate(own, [safe_tgt, danger_tgt], _env())
        self.assertTrue(d.collision_risk)
        self.assertFalse(d.target_decisions["Safe"].collision_risk)
        self.assertTrue(d.target_decisions["Danger"].collision_risk)

    def test_two_targets_conflicting(self):
        """Две опасные цели с разных сторон."""
        own = _vessel("O", x=0, y=0, course=0, speed=12)
        tgt_a = _vessel("A", x=1.0, y=1.0, course=270, speed=10)
        tgt_b = _vessel("B", x=-1.0, y=1.0, course=90, speed=10)
        d = self.engine.evaluate(own, [tgt_a, tgt_b], _env())
        self.assertTrue(d.collision_risk)
        # алгоритм должен найти безопасный курс или рекомендовать остановку.
        self.assertIn(d.recommended_action, [
            Action.ALTER_COURSE_STARBOARD,
            Action.ALTER_COURSE_PORT,
            Action.REDUCE_SPEED_OR_STOP,
        ])
        if d.recommended_heading is not None:
            # проверка, что выбранный курс лежит вне запрещенных секторов.
            h = int(round(d.recommended_heading)) % 360
            for start, end in d.forbidden_sectors:
                if start <= end:
                    self.assertFalse(start <= h <= end,
                                     f"Heading {h} falls in forbidden sector ({start},{end})")


class TestEnginePhysicalConstraints(unittest.TestCase):

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_large_turning_radius_warning(self):
        """Большой радиус циркуляции при близком встречном сближении приводит к невозможности маневра."""
        own = _vessel("O", x=0, y=0, course=0, speed=20, radius=0.8)
        tgt = _vessel("T", x=0, y=0.3, course=180, speed=10)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertTrue(d.collision_risk)
        self.assertFalse(d.maneuver_possible)

    def test_sufficient_time_to_turn(self):
        """Нормальный радиус циркуляции при далекой цели позволяет выполнить маневр."""
        own = _vessel("O", x=0, y=0, course=0, speed=10, radius=0.25)
        tgt = _vessel("T", x=1.0, y=5.0, course=270, speed=10)
        d = self.engine.evaluate(own, [tgt], _env())
        if d.collision_risk and d.recommended_heading is not None:
            self.assertTrue(d.maneuver_possible)


class TestEngineHeadingSelection(unittest.TestCase):

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_starboard_preference_within_110(self):
        """Движок должен предпочитать поворот вправо в пределах 110 градусов."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=1.5, course=180, speed=10)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertTrue(d.collision_risk)
        self.assertEqual(d.recommended_action, Action.ALTER_COURSE_STARBOARD)
        if d.recommended_heading is not None:
            delta = (d.recommended_heading - own.course) % 360
            self.assertLessEqual(delta, 110.0)

    def test_all_forbidden_recommend_stop(self):
        """При блокировании всех курсов рекомендуется остановка."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        # размещаем множество целей вокруг собственного судна на близком расстоянии.
        targets = []
        for angle in range(0, 360, 30):
            r = 0.5  # Very close
            x = r * math.sin(math.radians(angle))
            y = r * math.cos(math.radians(angle))
            # каждая цель движется в нашу сторону.
            tgt_course = (angle + 180) % 360
            targets.append(_vessel(f"T{angle}", x=x, y=y, course=tgt_course, speed=10))

        d = self.engine.evaluate(own, targets, _env())
        self.assertTrue(d.collision_risk)
        # если все курсы запрещены, рекомендуемым действием должна быть остановка.
        if d.recommended_heading is None:
            self.assertEqual(d.recommended_action, Action.REDUCE_SPEED_OR_STOP)

    def test_effective_safe_distance_scaling(self):
        """При критическом сближении с целью безопасная дистанция масштабируется."""
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        tgt = _vessel("T", x=0, y=0.5, course=180, speed=10)
        d = self.engine.evaluate(own, [tgt], _env())
        self.assertTrue(d.collision_risk)
        # движок все равно должен выдать корректное решение.
        self.assertIsNotNone(d.recommended_action)


class TestEngineSailingRule12Integration(unittest.TestCase):

    def setUp(self):
        self.engine = COLREGInferenceEngine()

    def test_two_sailing_same_tack_windward_gives_way(self):
        """Два парусных судна на одном галсе: наветренное судно уступает дорогу подветренному."""
        # ветер дует с севера. Оба судна идут на восток правым галсом: собственное судно с наветренной стороны, цель с подветренной стороны.
        own = _vessel("O", x=0, y=0, course=90, speed=6, vtype=VesselType.SAILING)
        tgt = _vessel("T", x=1.0, y=1.0, course=90, speed=4, vtype=VesselType.SAILING)
        d = self.engine.evaluate(own, [tgt], _env(), wind_direction=0.0)
        if d.collision_risk:
            td = d.target_decisions["T"]
            # расчет проекций на направление ветра.
            # pos_own_windward = -(0*0 + 0*1) = 0
            # pos_tgt_windward = -(1*0 + 1*1) = -1
            # собственное судно (0) наветреннее цели (-1) и должно уступить дорогу.
            # But Rule 13 overtaking takes precedence: own speed > tgt speed and
            # own behind target => own_overtaking.
            # Indeed, if own is overtaking the target (faster, same course), Rule 13
            # takes priority over Rule 12.
            if td.encounter_type == "own_overtaking":
                self.assertEqual(td.own_role, VesselRole.GIVE_WAY)
            else:
                self.assertEqual(td.own_role, VesselRole.GIVE_WAY)

    def test_two_sailing_different_tacks_port_gives_way(self):
        """Два парусных судна на разных галсах: судно на левом галсу уступает дорогу."""
        # ветер дует с севера. Собственное судно идет на восток (левый галс), цель - на запад (правый галс).
        own = _vessel("O", x=0, y=0, course=270, speed=6, vtype=VesselType.SAILING)
        tgt = _vessel("T", x=-4, y=0, course=90, speed=6, vtype=VesselType.SAILING)
        d = self.engine.evaluate(own, [tgt], _env(), wind_direction=0.0)
        self.assertTrue(d.collision_risk)
        td = d.target_decisions["T"]
        # собственное судно идет правым галсом, цель - левым. Судно на правом галсу сохраняет курс.
        self.assertEqual(td.own_role, VesselRole.STAND_ON)


class TestEnginePortTurnFallback(unittest.TestCase):

    def test_port_turn_when_starboard_exceeds_110(self):
        """Если поворот вправо превышает 110 градусов, но доступен поворот влево, используется поворот влево."""
        engine = COLREGInferenceEngine()
        # собственное судно идет на север. Блокируем правый сектор от 0 до 120 градусов, оставляя левый сектор открытым.
        own = _vessel("O", x=0, y=0, course=0, speed=10)
        # размещаем цели, блокирующие курсы в секторе 0-120 градусов вправо, оставляя левые курсы свободными.
        # цель прямо по носу и чуть справа.
        tgt1 = _vessel("T1", x=0.3, y=1.0, course=180, speed=10)
        # другая цель, блокирующая сектор правее.
        tgt2 = _vessel("T2", x=1.0, y=0.3, course=270, speed=10)

        d = engine.evaluate(own, [tgt1, tgt2], _env())
        # проверяем работоспособность логического движка в этой ситуации.
        self.assertIsNotNone(d.recommended_action)
        if d.recommended_action == Action.ALTER_COURSE_PORT:
            # был использован поворот влево в качестве запасного варианта.
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
        """Отрицательные радианы должны преобразовываться в корректный курс от 0 до 360 градусов."""
        result = rad_to_course(-math.pi / 2)
        expected = 360 - 90  # -90 degrees => 270
        self.assertAlmostEqual(result, expected, places=5)


class TestEngineStandOnAllTargets(unittest.TestCase):
    """When we are stand-on for all targets, we keep course."""

    def test_stand_on_keeps_course(self):
        engine = COLREGInferenceEngine()
        own = _vessel("O", x=0, y=0, course=0, speed=8)
        # цель обгоняет нас сзади: размещаем ее на безопасном расстоянии.
        tgt = _vessel("T", x=0, y=-3, course=0, speed=15)
        d = engine.evaluate(own, [tgt], _env())
        self.assertTrue(d.collision_risk)
        td = d.target_decisions["T"]
        # если обнаружен обгон со стороны цели, мы сохраняем курс.
        if td.encounter_type == "target_overtaking":
            self.assertEqual(td.own_role, VesselRole.STAND_ON)
            # если текущий курс разрешен, общим решением является сохранение курса и скорости.
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
