from typing import List, Optional, Tuple

from .geometry import (
    calculate_distance,
    calculate_relative_bearing,
    calculate_true_bearing,
    is_collision_risk_exists,
)
from .models import Action, Environment, Vessel, VesselRole, VesselType, Visibility


def get_vessel_priority_rank(v_type: VesselType) -> int:
    """
    Возвращает приоритет судна согласно Правилу 18 (Взаимные обязанности судов).
    Чем выше число, тем выше приоритет (тем больше другие суда должны уступать дорогу).
    """
    ranks = {
        VesselType.NUC: 5,  # лишенное возможности управляться (Правило 18a-c)
        VesselType.RAM: 4,  # ограниченное в возможности маневрировать (Правило 18a-c)
        VesselType.CBD: 3,  # стесненное своей осадкой (Правило 18d)
        VesselType.FISHING: 2,  # занятое ловом рыбы (Правило 18a-b)
        VesselType.SAILING: 1,  # парусное судно (Правило 18a)
        VesselType.POWER_DRIVEN: 0,  # судно с механическим двигателем
    }
    return ranks.get(v_type, 0)


def classify_encounter_sectors(
    own: Vessel, target: Vessel
) -> Tuple[str, bool, bool, bool]:
    """
    Классифицирует взаимное расположение судов по секторам:
    Возвращает (relative_position, is_head_on_sector, is_crossing_sector, is_overtaking_sector)

    Сектора согласно Правилам 13, 14, 15:
    - обгон: цель подходит с направления более 22.5 градусов позади траверза (курсовой пеленг от 112.5 до 247.5);
    - лоб-в-лоб: курсы почти противоположны (от 170 до 190 градусов) и пеленги лежат в пределах 10 градусов от направления прямо по носу;
    - пересечение: взаимные курсы пересекаются, сектор не является обгоном или встречным.
    """
    # Курсовой пеленг цели относительно нас
    rb_own = calculate_relative_bearing(own, target)

    # Курсовой пеленг нас относительно цели
    rb_tgt = calculate_relative_bearing(target, own)

    # Разница курсов (в диапазоне 0...360)
    course_diff = (target.course - own.course) % 360

    # 1. Проверяем сектор обгона (Правило 13)
    # Мы обгоняем цель, если мы находимся в кормовом секторе цели (курсовой пеленг на нас с цели в пределах 112.5...247.5)
    # и наша скорость больше.
    is_own_overtaking = (112.5 <= rb_tgt <= 247.5) and (own.speed > target.speed)
    # Цель обгоняет нас, если цель в нашем кормовом секторе (курсовой пеленг на цель у нас 112.5...247.5)
    # и её скорость больше.
    is_tgt_overtaking = (112.5 <= rb_own <= 247.5) and (target.speed > own.speed)

    if is_own_overtaking:
        return "own_overtaking", False, False, True
    if is_tgt_overtaking:
        return "target_overtaking", False, False, True

    # встречные курсы (разница около 180 градусов, например, от 170 до 190)
    # и оба видят друг друга почти прямо по носу (пеленг в пределах 10 градусов от носа, от 0 до 10 или от 350 до 360)
    is_reciprocal_courses = 170 <= course_diff <= 190
    is_own_seeing_headon = rb_own <= 10 or rb_own >= 350
    is_tgt_seeing_headon = rb_tgt <= 10 or rb_tgt >= 350

    if is_reciprocal_courses and is_own_seeing_headon and is_tgt_seeing_headon:
        return "head_on", True, False, False

    # 3. Пересечение курсов (Правило 15)
    # Если курсы пересекаются, и это не обгон и не встречные.
    # Сектора делятся на правый борт (уступаем) и левый борт (сохраняем курс)
    if rb_own < 180:
        return "crossing_starboard", False, True, False
    else:
        return "crossing_port", False, True, False


def evaluate_sailing_vessels_rule12(
    own: Vessel, target: Vessel, wind_dir: float
) -> Tuple[VesselRole, Action, List[str]]:
    """
    Вычисляет расхождение двух парусных судов согласно Правилу 12.
    """
    # Определяем галс (левый или правый). Галс определяется стороной, противоположной той, с которой дует ветер.
    # Если ветер дует в левый борт (относительный угол ветра 180...360), то судно идет правым галсом.
    # Если ветер дует в правый борт (относительный угол ветра 0...180), то судно идет левым галсом.
    own_wind_rel = (wind_dir - own.course) % 360
    tgt_wind_rel = (wind_dir - target.course) % 360

    # True = правый галс (ветер справа, 0..180), False = левый галс (ветер слева, 180..360)
    own_starboard_tack = 0 <= own_wind_rel < 180
    tgt_starboard_tack = 0 <= tgt_wind_rel < 180

    explanation = [
        "оба судна идут под парусом согласно Правилу 12",
        f"наше судно: курс {own.course}°, относительный угол ветра {own_wind_rel:.1f}° ({'правый галс' if own_starboard_tack else 'левый галс'})",
        f"судно-цель: курс {target.course}°, относительный угол ветра {tgt_wind_rel:.1f}° ({'правый галс' if tgt_starboard_tack else 'левый галс'})",
    ]

    if own_starboard_tack != tgt_starboard_tack:
        # Разные галсы: левый галс уступает дорогу
        if not own_starboard_tack:  # Наш галс левый
            explanation.append(
                "наше судно идет левым галсом и должно уступить дорогу судну на правом галсу согласно Правилу 12 (a)(i)"
            )
            return VesselRole.GIVE_WAY, Action.ALTER_COURSE_STARBOARD, explanation
        else:
            explanation.append(
                "наше судно идет правым галсом и имеет преимущество, цель идет левым галсом и должна уступить дорогу согласно Правилу 12 (a)(i)"
            )
            return VesselRole.STAND_ON, Action.KEEP_COURSE_SPEED, explanation
    else:
        # Одни и те же галсы: наветренное судно уступает подветренному
        # Вектор ветра: (sin(wind_dir), cos(wind_dir))
        wind_rad = math.radians(wind_dir)
        w_x = math.sin(wind_rad)
        w_y = math.cos(wind_rad)

        # Проекция на вектор ОТКУДА дует ветер (-w_x, -w_y):
        pos_own_windward = -(own.x * w_x + own.y * w_y)
        pos_tgt_windward = -(target.x * w_x + target.y * w_y)

        if pos_own_windward > pos_tgt_windward:
            explanation.append(
                "наше судно находится с наветренной стороны и должно уступить дорогу подветренному судну согласно Правилу 12 (a)(ii)"
            )
            return VesselRole.GIVE_WAY, Action.ALTER_COURSE_STARBOARD, explanation
        else:
            explanation.append(
                "наше судно находится с подветренной стороны и имеет преимущество, наветренное судно-цель должно уступить дорогу согласно Правилу 12 (a)(ii)"
            )
            return VesselRole.STAND_ON, Action.KEEP_COURSE_SPEED, explanation
