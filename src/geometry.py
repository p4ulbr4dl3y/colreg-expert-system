import math
from typing import Tuple, Optional
from .models import Vessel

# Константы для расчетов опасности
SAFE_CPA_DISTANCE = 2.0     # Безопасная дистанция кратчайшего сближения (в милях, NM)
CRITICAL_TCPA = 0.5          # Критическое время сближения (30 минут, в часах)

def course_to_rad(course_deg: float) -> float:
    """Перевод морского курса (0 - 360, по часовой стрелке от Севера) в радианы."""
    return math.radians(course_deg)

def rad_to_course(rad: float) -> float:
    """Перевод радианов в морской курс (0 - 360)."""
    deg = math.degrees(rad)
    return deg % 360

def get_velocity_components(speed: float, course_deg: float) -> Tuple[float, float]:
    """Вычисляет компоненты скорости Vx, Vy по курсу и скорости."""
    rad = course_to_rad(course_deg)
    # В морских координатах: X - Восток (sin), Y - Север (cos)
    vx = speed * math.sin(rad)
    vy = speed * math.cos(rad)
    return vx, vy

def calculate_distance(v1: Vessel, v2: Vessel) -> float:
    """Вычисляет расстояние между двумя судами в морских милях."""
    return math.sqrt((v2.x - v1.x)**2 + (v2.y - v1.y)**2)

def calculate_true_bearing(from_vessel: Vessel, to_vessel: Vessel) -> float:
    """Вычисляет истинный пеленг (True Bearing) на цель в градусах."""
    dx = to_vessel.x - from_vessel.x
    dy = to_vessel.y - from_vessel.y
    # В морской системе координат угол идет от оси Y по часовой стрелке
    rad = math.atan2(dx, dy)
    return rad_to_course(rad)

def calculate_relative_bearing(own: Vessel, target: Vessel) -> float:
    """
    Вычисляет относительный (курсовой) пеленг (Relative Bearing) на цель.
    Угол от носа Own Ship до Target Ship по часовой стрелке (0...360).
    """
    tb = calculate_true_bearing(own, target)
    rb = (tb - own.course) % 360
    return rb

def calculate_cpa_tcpa(own: Vessel, target: Vessel) -> Tuple[float, float]:
    """
    Вычисляет CPA (дистанцию кратчайшего сближения) и TCPA (время до кратчайшего сближения в часах).
    Если суда расходятся или параллельны, TCPA может быть отрицательным или отрицательно-бесконечным.
    """
    # Компоненты скоростей
    v_own_x, v_own_y = get_velocity_components(own.speed, own.course)
    v_tgt_x, v_tgt_y = get_velocity_components(target.speed, target.course)
    
    # Относительная скорость (цель относительно нас)
    v_rel_x = v_tgt_x - v_own_x
    v_rel_y = v_tgt_y - v_own_y
    
    # Относительное расстояние (цель относительно нас)
    r_x = target.x - own.x
    r_y = target.y - own.y
    
    v_rel_sq = v_rel_x**2 + v_rel_y**2
    
    if v_rel_sq < 1e-6:
        # Скорости одинаковы и параллельны, относительного движения нет
        current_dist = calculate_distance(own, target)
        return current_dist, float('inf')
    
    # Время до CPA (в часах): TCPA = - (R * V_rel) / |V_rel|^2
    tcpa = - (r_x * v_rel_x + r_y * v_rel_y) / v_rel_sq
    
    # Координаты сближения в момент TCPA
    cpa_x = r_x + v_rel_x * tcpa
    cpa_y = r_y + v_rel_y * tcpa
    
    cpa_dist = math.sqrt(cpa_x**2 + cpa_y**2)
    
    return cpa_dist, tcpa

def is_collision_risk_exists(own: Vessel, target: Vessel) -> Tuple[bool, float, float, float]:
    """
    Определяет, существует ли опасность столкновения.
    Возвращает (risk_exists, current_distance, cpa_distance, tcpa_hours).
    """
    dist = calculate_distance(own, target)
    cpa, tcpa = calculate_cpa_tcpa(own, target)
    
    # Опасность столкновения существует, если:
    # 1. Мы уже критически близко
    # 2. ИЛИ сближение произойдет в будущем (tcpa > 0) и дистанция CPA ниже безопасной,
    #    и время до сближения в пределах горизонта планирования (CRITICAL_TCPA)
    if dist < SAFE_CPA_DISTANCE:
        risk = True
    elif tcpa > 0 and tcpa < CRITICAL_TCPA and cpa < SAFE_CPA_DISTANCE:
        risk = True
    else:
        risk = False
        
    return risk, dist, cpa, tcpa
