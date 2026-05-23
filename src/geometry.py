import math
from typing import Tuple, Optional, List
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
    """
    v_own_x, v_own_y = get_velocity_components(own.speed, own.course)
    v_tgt_x, v_tgt_y = get_velocity_components(target.speed, target.course)
    
    v_rel_x = v_tgt_x - v_own_x
    v_rel_y = v_tgt_y - v_own_y
    
    r_x = target.x - own.x
    r_y = target.y - own.y
    
    v_rel_sq = v_rel_x**2 + v_rel_y**2
    
    if v_rel_sq < 1e-6:
        current_dist = calculate_distance(own, target)
        return current_dist, float('inf')
    
    tcpa = - (r_x * v_rel_x + r_y * v_rel_y) / v_rel_sq
    
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
    
    if dist < SAFE_CPA_DISTANCE:
        risk = True
    elif tcpa > 0 and tcpa < CRITICAL_TCPA and cpa < SAFE_CPA_DISTANCE:
        risk = True
    else:
        risk = False
        
    return risk, dist, cpa, tcpa

def is_turn_possible(own_speed: float, min_turning_radius: float, delta_heading_deg: float, tcpa_hours: float) -> bool:
    """
    Проверяет, успеет ли судно физически завершить поворот на delta_heading_deg
    до наступления момента кратчайшего сближения (TCPA).
    
    Длина дуги поворота S = R * alpha (в радианах).
    Время поворота T = S / V.
    """
    if tcpa_hours <= 0 or tcpa_hours == float('inf'):
        return True
        
    alpha_rad = math.radians(abs(delta_heading_deg))
    turn_distance = min_turning_radius * alpha_rad  # в милях (NM)
    
    if own_speed < 0.1:
        return True  # Стоим на месте
        
    turn_time_hours = turn_distance / own_speed
    return turn_time_hours <= tcpa_hours

def get_forbidden_headings_for_target(own: Vessel, target: Vessel, safe_dist: float = SAFE_CPA_DISTANCE) -> List[bool]:
    """
    Оценивает все 360 направлений курса собственного судна (при текущей скорости).
    Возвращает список из 360 булевых значений, где True означает, что данный курс
    является ОПАСНЫМ (приводит к CPA < safe_dist при TCPA > 0 и TCPA < CRITICAL_TCPA).
    """
    forbidden = [False] * 360
    
    # Создаем временный объект судна для симуляции
    temp_own = Vessel(
        name=own.name,
        x=own.x,
        y=own.y,
        course=own.course,
        speed=own.speed,
        vessel_type=own.vessel_type
    )
    
    for heading in range(360):
        temp_own.course = float(heading)
        cpa, tcpa = calculate_cpa_tcpa(temp_own, target)
        
        # Если при данном курсе возникает сближение ближе безопасного
        if tcpa > 0 and tcpa < CRITICAL_TCPA and cpa < safe_dist:
            forbidden[heading] = True
            
    return forbidden

def convert_boolean_array_to_sectors(array: List[bool]) -> List[Tuple[float, float]]:
    """
    Преобразует массив из 360 булевых значений в список непрерывных угловых секторов (start, end).
    Корректно обрабатывает переход через 360 градусов.
    """
    sectors = []
    in_sector = False
    start = 0.0
    
    for i in range(360):
        if array[i] and not in_sector:
            start = float(i)
            in_sector = True
        elif not array[i] and in_sector:
            sectors.append((start, float(i - 1)))
            in_sector = False
            
    # Обработка перехода через 0
    if in_sector:
        if len(sectors) > 0 and sectors[0][0] == 0.0:
            # Слияние последнего сектора с первым
            first_sector = sectors.pop(0)
            sectors.append((start, first_sector[1]))
        else:
            sectors.append((start, 359.0))
            
    return sectors
