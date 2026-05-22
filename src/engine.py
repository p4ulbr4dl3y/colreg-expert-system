from typing import List, Tuple, Optional
from .models import Vessel, VesselType, VesselRole, Action, Visibility, Environment, Decision
from .geometry import (
    calculate_distance,
    calculate_relative_bearing,
    calculate_true_bearing,
    calculate_cpa_tcpa,
    is_collision_risk_exists
)
from .rules import (
    get_vessel_priority_rank,
    classify_encounter_sectors,
    evaluate_sailing_vessels_rule12
)

class COLREGInferenceEngine:
    def __init__(self):
        pass

    def evaluate(self, own: Vessel, target: Vessel, env: Environment, wind_direction: Optional[float] = None) -> Decision:
        """
        Основной метод логического вывода экспертной системы.
        Вычисляет параметры сближения, проверяет опасность столкновения,
        применяет правила МППСС-72 и возвращает решение.
        """
        # 1. Проверяем опасность столкновения
        risk_exists, dist, cpa, tcpa = is_collision_risk_exists(own, target)
        
        # Получаем угловые параметры для вывода в отчете
        rb_own = calculate_relative_bearing(own, target)
        tb_own = calculate_true_bearing(own, target)
        rb_tgt = calculate_relative_bearing(target, own)
        
        # Описание взаимной геометрии
        geo_details = [
            f"Текущая дистанция: {dist:.2f} миль (NM).",
            f"Истинный пеленг на цель: {tb_own:.1f}°.",
            f"Относительный пеленг на цель (у нас): {rb_own:.1f}° (правый борт" if rb_own < 180 else f"Относительный пеленг на цель (у нас): {rb_own:.1f}° (левый борт",
            f"Относительный пеленг на нас (у цели): {rb_tgt:.1f}°.",
            f"Прогноз сближения: CPA = {cpa:.2f} миль, TCPA = {tcpa*60:.1f} мин." if tcpa != float('inf') else "Суда движутся параллельно."
        ]
        # Закрываем скобки в описании пеленга
        geo_details[2] += ")"

        if not risk_exists:
            return Decision(
                collision_risk=False,
                encounter_type="SAFE",
                own_role=VesselRole.N_A,
                recommended_action=Action.N_A,
                explanation=[
                    "Опасность столкновения отсутствует.",
                    f"Дистанция сближения (CPA) {cpa:.2f} миль безопасна (больше порога {2.0} миль) " +
                    f"или суда расходятся (TCPA = {tcpa:.2f} ч)."
                ] + geo_details
            )

        # 2. Если опасность существует, применяем правила в зависимости от видимости
        explanation = ["ОПАСНОСТЬ СТОЛКНОВЕНИЯ СУЩЕСТВУЕТ!"] + geo_details
        
        # 2.1. Ограниченная видимость (Правило 19)
        if env.visibility == Visibility.RESTRICTED:
            explanation.append("Правило 19 (Плавание судов при ограниченной видимости):")
            explanation.append("  Суда не находятся на виду друг у друга (ограниченная видимость).")
            explanation.append("  Каждое судно действует самостоятельно на основании данных радиолокатора.")
            explanation.append("  Внимание: Приоритеты типов судов (Правило 18) в тумане НЕ действуют!")
            
            # Действия по Правилу 19 (d)
            # (i) Изменение курса влево следует избегать, если судно впереди траверза и не является обгоняемым
            # (ii) Изменение курса в сторону судна на траверзе или позади траверза следует избегать
            
            # Проверяем положение цели: впереди или позади траверза
            # Впереди траверза: курсовой пеленг в диапазоне 0..90 или 270..360 (т.е. rb_own <= 90 или rb_own >= 270)
            is_ahead_of_beam = (rb_own <= 90 or rb_own >= 270)
            
            # Проверяем, обгоняем ли мы его (мы находимся в его кормовом секторе)
            is_we_overtaking = (112.5 <= rb_tgt <= 247.5)
            
            if is_ahead_of_beam:
                if not is_we_overtaking:
                    explanation.append("  -> Цель находится впереди траверза и не является обгоняемой.")
                    explanation.append("  -> Согласно Правилу 19 (d)(i), следует избегать изменения курса влево.")
                    return Decision(
                        collision_risk=True,
                        encounter_type="RESTRICTED_VISIBILITY_AHEAD",
                        own_role=VesselRole.BOTH_GIVE_WAY,  # В тумане уступают оба
                        recommended_action=Action.ALTER_COURSE_STARBOARD,
                        explanation=explanation
                    )
                else:
                    explanation.append("  -> Мы обгоняем цель в условиях ограниченной видимости.")
                    explanation.append("  -> Безопаснее изменить курс на правый борт для обхода.")
                    return Decision(
                        collision_risk=True,
                        encounter_type="RESTRICTED_VISIBILITY_OVERTAKING",
                        own_role=VesselRole.GIVE_WAY,
                        recommended_action=Action.ALTER_COURSE_STARBOARD,
                        explanation=explanation
                    )
            else:
                # Цель на траверзе или позади него (rb_own от 90 до 270)
                # Избегать изменения курса в сторону судна (Rule 19 d(ii))
                is_target_starboard = (90 < rb_own <= 180)
                if is_target_starboard:
                    explanation.append("  -> Цель находится по правому борту на траверзе или позади него.")
                    explanation.append("  -> Согласно Правилу 19 (d)(ii), следует избегать изменения курса вправо (в сторону судна).")
                    return Decision(
                        collision_risk=True,
                        encounter_type="RESTRICTED_VISIBILITY_ABEAFT_STARBOARD",
                        own_role=VesselRole.BOTH_GIVE_WAY,
                        recommended_action=Action.ALTER_COURSE_PORT,
                        explanation=explanation
                    )
                else:
                    explanation.append("  -> Цель находится по левому борту на траверзе или позади него.")
                    explanation.append("  -> Согласно Правилу 19 (d)(ii), следует избегать изменения курса влево (в сторону судна).")
                    return Decision(
                        collision_risk=True,
                        encounter_type="RESTRICTED_VISIBILITY_ABEAFT_PORT",
                        own_role=VesselRole.BOTH_GIVE_WAY,
                        recommended_action=Action.ALTER_COURSE_STARBOARD,
                        explanation=explanation
                    )

        # 2.2. Хорошая видимость (суда на виду друг у друга)
        explanation.append("Раздел II (Плавание судов, находящихся на виду друг у друга):")
        
        # Шаг 1: Проверяем обгон (Правило 13 имеет высший приоритет над Правилом 18)
        encounter_sector, is_head_on, is_crossing, is_overtaking = classify_encounter_sectors(own, target)
        
        if is_overtaking:
            if encounter_sector == "own_overtaking":
                explanation.append("  -> Ситуация ОБГОНА (Правило 13). Наше судно обгоняет цель.")
                explanation.append("  -> Согласно Правилу 13 (а), обгоняющее судно обязано держаться в стороне от пути обгоняемого.")
                return Decision(
                    collision_risk=True,
                    encounter_type="OVERTAKING_GIVE_WAY",
                    own_role=VesselRole.GIVE_WAY,
                    recommended_action=Action.ALTER_COURSE_STARBOARD,
                    explanation=explanation
                )
            elif encounter_sector == "target_overtaking":
                explanation.append("  -> Ситуация ОБГОНА (Правило 13). Цель обгоняет наше судно.")
                explanation.append("  -> Согласно Правилу 13 (а) и Правилу 17 (а)(i), наше судно должно сохранять курс и скорость.")
                return Decision(
                    collision_risk=True,
                    encounter_type="OVERTAKING_STAND_ON",
                    own_role=VesselRole.STAND_ON,
                    recommended_action=Action.KEEP_COURSE_SPEED,
                    explanation=explanation
                )

        # Шаг 2: Проверяем Парусное vs Парусное (Правило 12)
        if own.vessel_type == VesselType.SAILING and target.vessel_type == VesselType.SAILING:
            if wind_direction is not None:
                role, action, rule12_expl = evaluate_sailing_vessels_rule12(own, target, wind_direction)
                explanation.extend(rule12_expl)
                return Decision(
                    collision_risk=True,
                    encounter_type="SAILING_CROSSING",
                    own_role=role,
                    recommended_action=action,
                    explanation=explanation
                )
            else:
                explanation.append("  [ВНИМАНИЕ] Оба судна парусные (Правило 12), но направление ветра не задано!")
                explanation.append("  По умолчанию: уступает судно по левому борту.")
                # Фолбэк на левый борт
                if rb_own < 180:
                    return Decision(
                        collision_risk=True,
                        encounter_type="SAILING_FALLBACK_GIVE_WAY",
                        own_role=VesselRole.GIVE_WAY,
                        recommended_action=Action.ALTER_COURSE_STARBOARD,
                        explanation=explanation
                    )
                else:
                    return Decision(
                        collision_risk=True,
                        encounter_type="SAILING_FALLBACK_STAND_ON",
                        own_role=VesselRole.STAND_ON,
                        recommended_action=Action.KEEP_COURSE_SPEED,
                        explanation=explanation
                    )

        # Шаг 3: Проверяем взаимные обязанности (Правило 18)
        own_rank = get_vessel_priority_rank(own.vessel_type)
        tgt_rank = get_vessel_priority_rank(target.vessel_type)
        
        if own_rank != tgt_rank:
            explanation.append("  -> Взаимные обязанности судов (Правило 18):")
            explanation.append(f"     Наш статус: {own.vessel_type.description_ru()} (приоритет {own_rank})")
            explanation.append(f"     Статус цели: {target.vessel_type.description_ru()} (приоритет {tgt_rank})")
            
            if own_rank < tgt_rank:
                explanation.append(f"  -> Наше судно имеет меньший приоритет и должно уступить дорогу (Правило 18).")
                return Decision(
                    collision_risk=True,
                    encounter_type="PRIORITY_GIVE_WAY",
                    own_role=VesselRole.GIVE_WAY,
                    recommended_action=Action.ALTER_COURSE_STARBOARD,
                    explanation=explanation
                )
            else:
                explanation.append(f"  -> Наше судно имеет больший приоритет и должно сохранять курс и скорость (Правило 18/17).")
                return Decision(
                    collision_risk=True,
                    encounter_type="PRIORITY_STAND_ON",
                    own_role=VesselRole.STAND_ON,
                    recommended_action=Action.KEEP_COURSE_SPEED,
                    explanation=explanation
                )

        # Шаг 4: Если приоритеты равны (например, оба механические судна)
        # Применяем Правило 14 (Встречные курсы) или Правило 15 (Пересечение)
        if is_head_on:
            explanation.append("  -> Ситуация встречных курсов (Правило 14).")
            explanation.append("  -> Согласно Правилу 14 (а), каждое судно должно изменить курс вправо, чтобы пройти у другого по левому борту.")
            return Decision(
                collision_risk=True,
                encounter_type="HEAD_ON",
                own_role=VesselRole.BOTH_GIVE_WAY,
                recommended_action=Action.ALTER_COURSE_STARBOARD,
                explanation=explanation
            )
            
        if is_crossing:
            if encounter_sector == "crossing_starboard":
                explanation.append("  -> Ситуация пересечения курсов (Правило 15).")
                explanation.append("  -> Цель находится с нашего правого борта. Наше судно должно уступить дорогу.")
                explanation.append("  -> Согласно Правилу 15 и 16, мы должны предпринять своевременный маневр и избегать пересечения курса цели по носу.")
                return Decision(
                    collision_risk=True,
                    encounter_type="CROSSING_GIVE_WAY",
                    own_role=VesselRole.GIVE_WAY,
                    recommended_action=Action.ALTER_COURSE_STARBOARD,
                    explanation=explanation
                )
            elif encounter_sector == "crossing_port":
                explanation.append("  -> Ситуация пересечения курсов (Правило 15).")
                explanation.append("  -> Цель находится с нашего левого борта. Мы имеем преимущество.")
                explanation.append("  -> Согласно Правилу 17 (а)(i), наше судно должно сохранять курс и скорость.")
                return Decision(
                    collision_risk=True,
                    encounter_type="CROSSING_STAND_ON",
                    own_role=VesselRole.STAND_ON,
                    recommended_action=Action.KEEP_COURSE_SPEED,
                    explanation=explanation
                )

        # Фолбэк на случай неопределенной геометрии
        explanation.append("  -> [ВНИМАНИЕ] Нестандартная геометрия сближения.")
        explanation.append("  Рекомендуется изменить курс вправо в соответствии с хорошей морской практикой (Правило 2).")
        return Decision(
            collision_risk=True,
            encounter_type="UNKNOWN_ENCOUNTER",
            own_role=VesselRole.GIVE_WAY,
            recommended_action=Action.ALTER_COURSE_STARBOARD,
            explanation=explanation
        )
