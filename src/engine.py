from typing import List, Tuple, Optional, Dict
from .models import Vessel, VesselType, VesselRole, Action, Visibility, Environment, Decision, TargetDecision
from .geometry import (
    calculate_distance,
    calculate_relative_bearing,
    calculate_true_bearing,
    calculate_cpa_tcpa,
    is_collision_risk_exists,
    is_turn_possible,
    get_forbidden_headings_for_target,
    convert_boolean_array_to_sectors,
    SAFE_CPA_DISTANCE,
    CRITICAL_TCPA
)
from .rules import (
    get_vessel_priority_rank,
    classify_encounter_sectors,
    evaluate_sailing_vessels_rule12
)

class COLREGInferenceEngine:
    def __init__(self):
        pass

    def evaluate(self, own: Vessel, targets: List[Vessel], env: Environment, wind_direction: Optional[float] = None) -> Decision:
        """
        Многоцелевой логический вывод экспертной системы.
        Вычисляет индивидуальные риски для каждой цели, строит карту запрещенных секторов курсов,
        принимает обобщенное решение по маневрированию и проверяет физические ограничения судна.
        """
        if not targets:
            return Decision(
                collision_risk=False,
                own_role=VesselRole.N_A,
                recommended_action=Action.N_A,
                recommended_heading=own.course,
                explanation=["Нет окружающих судов-целей для оценки."]
            )

        # 1. Поцелевая оценка рисков
        active_risks = False
        target_decisions: Dict[str, TargetDecision] = {}
        unified_forbidden_headings = [False] * 360
        closest_tcpa = float('inf')
        closest_target_name = ""
        
        # Общая сводка
        general_explanation = ["статус окружающей обстановки:"]
        targets_statuses = []
        
        for tgt in targets:
            risk_exists, dist, cpa, tcpa = is_collision_risk_exists(own, tgt)
            
            # Пеленги
            rb_own = calculate_relative_bearing(own, tgt)
            tb_own = calculate_true_bearing(own, tgt)
            rb_tgt = calculate_relative_bearing(tgt, own)
            
            rb_own_side = "правый борт" if rb_own < 180 else "левый борт"
            status_desc = f"цель {tgt.name}, дистанция {dist:.2f} миль, кратчайшее сближение {cpa:.2f} миль, относительный пеленг {rb_own:.1f}° ({rb_own_side})"
            if tcpa != float('inf') and tcpa > 0:
                status_desc += f", время сближения {tcpa*60:.1f} минут"
            
            if not risk_exists:
                # Цель безопасна
                target_decisions[tgt.name] = TargetDecision(
                    target_name=tgt.name,
                    collision_risk=False,
                    encounter_type="SAFE",
                    own_role=VesselRole.N_A,
                    recommended_action=Action.N_A,
                    cpa=cpa,
                    tcpa=tcpa,
                    explanation=[f"Сближение с {tgt.name} безопасно."]
                )
                targets_statuses.append(f"безопасное сближение: {status_desc}")
                
                # Рассчитываем и объединяем опасные курсы для этой цели
                tgt_forbidden = get_forbidden_headings_for_target(own, tgt)
                for h in range(360):
                    unified_forbidden_headings[h] = unified_forbidden_headings[h] or tgt_forbidden[h]
                continue
                
            # Опасность существует
            active_risks = True
            if tcpa > 0 and tcpa < closest_tcpa:
                closest_tcpa = tcpa
                closest_target_name = tgt.name
                
            targets_statuses.append(f"опасное сближение: {status_desc}")
            
            # Применяем правила МППСС-72 по отдельности к данной цели
            tgt_expl = [f"оценка расхождения с судно-целью {tgt.name}:"]
            
            # Ограниченная видимость (Правило 19)
            if env.visibility == Visibility.RESTRICTED:
                is_ahead_of_beam = (rb_own <= 90 or rb_own >= 270)
                is_we_overtaking = (112.5 <= rb_tgt <= 247.5)
                
                tgt_expl.append("  применяется Правило 19 для ограниченной видимости: приоритеты типов судов не действуют;")
                
                if is_ahead_of_beam:
                    if not is_we_overtaking:
                        tgt_expl.append("  цель впереди траверза и не обгоняется: следует избегать изменения курса влево согласно Правилу 19 (d)(i);")
                        role = VesselRole.BOTH_GIVE_WAY
                        action = Action.ALTER_COURSE_STARBOARD
                    else:
                        tgt_expl.append("  наше судно обгоняет цель в условиях ограниченной видимости: обязаны уступить дорогу;")
                        role = VesselRole.GIVE_WAY
                        action = Action.ALTER_COURSE_STARBOARD
                else:
                    is_target_starboard = (90 < rb_own <= 180)
                    if is_target_starboard:
                        tgt_expl.append("  цель на траверзе или позади него справа: следует избегать изменения курса вправо в сторону судна согласно Правилу 19 (d)(ii);")
                        role = VesselRole.BOTH_GIVE_WAY
                        action = Action.ALTER_COURSE_PORT
                    else:
                        tgt_expl.append("  цель на траверзе или позади него слева: следует избегать изменения курса влево в сторону судна согласно Правилу 19 (d)(ii);")
                        role = VesselRole.BOTH_GIVE_WAY
                        action = Action.ALTER_COURSE_STARBOARD
            
            # Хорошая видимость (Раздел II)
            else:
                encounter_sector, is_head_on, is_crossing, is_overtaking = classify_encounter_sectors(own, tgt)
                
                # Обгон (Правило 13)
                if is_overtaking:
                    if encounter_sector == "own_overtaking":
                        tgt_expl.append("  ситуация обгона согласно Правилу 13: наше судно обгоняет цель и обязано держаться в стороне от ее пути;")
                        role = VesselRole.GIVE_WAY
                        action = Action.ALTER_COURSE_STARBOARD
                    else:
                        tgt_expl.append("  ситуация обгона согласно Правилу 13: цель обгоняет наше судно, мы должны сохранять курс и скорость;")
                        role = VesselRole.STAND_ON
                        action = Action.KEEP_COURSE_SPEED
                
                # Парусные суда (Правило 12)
                elif own.vessel_type == VesselType.SAILING and tgt.vessel_type == VesselType.SAILING:
                    role, action, rule12_expl = evaluate_sailing_vessels_rule12(own, tgt, wind_direction or 0.0)
                    # Приводим строки правила 12 к строчным буквам и добавляем точку с запятой
                    for line in rule12_expl:
                        cleaned_line = line.strip()
                        if cleaned_line.startswith("-"):
                            cleaned_line = cleaned_line[1:].strip()
                        # Делаем первую букву строчной
                        if cleaned_line:
                            cleaned_line = cleaned_line[0].lower() + cleaned_line[1:]
                        tgt_expl.append(f"  {cleaned_line};")
                
                # Взаимные обязанности (Правило 18)
                else:
                    own_rank = get_vessel_priority_rank(own.vessel_type)
                    tgt_rank = get_vessel_priority_rank(tgt.vessel_type)
                    
                    if own_rank != tgt_rank:
                        tgt_expl.append(f"  взаимные обязанности согласно Правилу 18: наше судно - {own.vessel_type.description_ru()}, цель - {tgt.vessel_type.description_ru()};")
                        if own_rank < tgt_rank:
                            tgt_expl.append("  наше судно имеет меньший приоритет и обязано уступить дорогу;")
                            role = VesselRole.GIVE_WAY
                            action = Action.ALTER_COURSE_STARBOARD
                        else:
                            tgt_expl.append("  цель имеет меньший приоритет и обязана уступить дорогу, мы сохраняем курс и скорость;")
                            role = VesselRole.STAND_ON
                            action = Action.KEEP_COURSE_SPEED
                    
                    # Равный приоритет (например, оба механические судна)
                    else:
                        if is_head_on:
                            tgt_expl.append("  ситуация встречных курсов согласно Правилу 14: оба судна должны изменить курс вправо;")
                            role = VesselRole.BOTH_GIVE_WAY
                            action = Action.ALTER_COURSE_STARBOARD
                        elif is_crossing:
                            if encounter_sector == "crossing_starboard":
                                tgt_expl.append("  ситуация пересечения курсов согласно Правилу 15: цель находится справа, мы обязаны уступить дорогу;")
                                role = VesselRole.GIVE_WAY
                                action = Action.ALTER_COURSE_STARBOARD
                            else:
                                tgt_expl.append("  ситуация пересечения курсов согласно Правилу 15: цель находится слева, мы имеем преимущество и сохраняем курс и скорость;")
                                role = VesselRole.STAND_ON
                                action = Action.KEEP_COURSE_SPEED
                        else:
                            tgt_expl.append("  неопределенный сектор равного приоритета: рекомендуется изменить курс вправо в соответствии с хорошей морской практикой;")
                            role = VesselRole.GIVE_WAY
                            action = Action.ALTER_COURSE_STARBOARD

            # Проверяем маневр крайнего момента для роли Stand-on (Правило 17 b)
            # Если мы Stand-on, но сближение критически близкое (TCPA < 9 минут / 0.15 ч), мы ОБЯЗАНЫ действовать
            if role == VesselRole.STAND_ON and tcpa < 0.15:
                tgt_expl.append(f"  крайняя необходимость согласно Правилу 17 (b): время сближения {tcpa*60:.1f} минут является критическим, мы обязаны маневрировать для избежания столкновения;")
                role = VesselRole.GIVE_WAY
                action = Action.ALTER_COURSE_STARBOARD  # Правило 17 (с) запрещает поворот влево для цели слева
            
            target_decisions[tgt.name] = TargetDecision(
                target_name=tgt.name,
                collision_risk=True,
                encounter_type=encounter_sector if env.visibility == Visibility.GOOD else "RESTRICTED",
                own_role=role,
                recommended_action=action,
                cpa=cpa,
                tcpa=tcpa,
                explanation=tgt_expl
            )
            
            # Рассчитываем эффективную безопасную дистанцию для поиска курсов (масштабируем при близком сближении)
            effective_safe_dist = SAFE_CPA_DISTANCE
            if dist < SAFE_CPA_DISTANCE:
                effective_safe_dist = max(0.5, dist * 0.8)
                
            tgt_forbidden = get_forbidden_headings_for_target(own, tgt, safe_dist=effective_safe_dist)
            
            # Накладываем дополнительные ограничения на повороты согласно МППСС-72
            if env.visibility == Visibility.GOOD:
                # Если мы уступаем дорогу или сближаемся лоб-в-лоб, и это не обгон с нашей стороны,
                # запрещаем левые повороты (на левый борт) до 120 градусов (Правила 14, 15, 17c)
                if role in (VesselRole.GIVE_WAY, VesselRole.BOTH_GIVE_WAY) and encounter_sector != "own_overtaking":
                    for angle_diff in range(1, 121):
                        blocked_heading = int(round(own.course - angle_diff)) % 360
                        tgt_forbidden[blocked_heading] = True
            else:
                # В ограниченной видимости (Правило 19 d):
                if role in (VesselRole.GIVE_WAY, VesselRole.BOTH_GIVE_WAY):
                    is_ahead_of_beam = (rb_own <= 90 or rb_own >= 270)
                    is_we_overtaking = (112.5 <= rb_tgt <= 247.5)
                    if is_ahead_of_beam:
                        if not is_we_overtaking:
                            # Избегать изменения курса влево: запрещаем повороты влево
                            for angle_diff in range(1, 121):
                                blocked_heading = int(round(own.course - angle_diff)) % 360
                                tgt_forbidden[blocked_heading] = True
                    else:
                        # Судно на траверзе или позади него
                        is_target_starboard = (90 < rb_own <= 180)
                        if is_target_starboard:
                            # Избегать изменения курса вправо (в сторону судна)
                            for angle_diff in range(1, 121):
                                blocked_heading = int(round(own.course + angle_diff)) % 360
                                tgt_forbidden[blocked_heading] = True
                        else:
                            # Избегать изменения курса влево (в сторону судна)
                            for angle_diff in range(1, 121):
                                blocked_heading = int(round(own.course - angle_diff)) % 360
                                tgt_forbidden[blocked_heading] = True
                                
            for h in range(360):
                unified_forbidden_headings[h] = unified_forbidden_headings[h] or tgt_forbidden[h]
                
        # Форматируем список целей согласно Rule 3
        for i, status in enumerate(targets_statuses):
            suffix = "." if i == len(targets_statuses) - 1 else ";"
            general_explanation.append(f"- {status}{suffix}")

        # 2. Если опасности нет вообще
        if not active_risks:
            return Decision(
                collision_risk=False,
                own_role=VesselRole.N_A,
                recommended_action=Action.N_A,
                recommended_heading=own.course,
                forbidden_sectors=convert_boolean_array_to_sectors(unified_forbidden_headings),
                target_decisions=target_decisions,
                explanation=general_explanation + ["Все цели расходятся безопасно."]
            )

        # 3. Принятие общего решения на основе объединенных секторов опасных курсов
        # Определяем, обязаны ли мы маневрировать хотя бы из-за одной цели
        own_must_act = any(
            dec.own_role in (VesselRole.GIVE_WAY, VesselRole.BOTH_GIVE_WAY)
            for dec in target_decisions.values()
        )
        
        current_heading_idx = int(round(own.course)) % 360
        is_current_heading_forbidden = unified_forbidden_headings[current_heading_idx]
        
        # Если мы Stand-on для всех и текущий курс безопасен -> просто сохраняем его
        if not own_must_act and not is_current_heading_forbidden:
            return Decision(
                collision_risk=True,
                own_role=VesselRole.STAND_ON,
                recommended_action=Action.KEEP_COURSE_SPEED,
                recommended_heading=own.course,
                forbidden_sectors=convert_boolean_array_to_sectors(unified_forbidden_headings),
                target_decisions=target_decisions,
                explanation=general_explanation + ["Наше судно сохраняет курс и скорость."]
            )
            
        # Иначе мы обязаны изменить курс
        # Ищем первый безопасный курс вправо и влево
        safe_stbd_heading = None
        safe_stbd_angle = 360.0
        
        safe_port_heading = None
        safe_port_angle = 360.0
        
        # Поиск вправо (по часовой стрелке)
        for delta in range(1, 180):
            heading = (current_heading_idx + delta) % 360
            if not unified_forbidden_headings[heading]:
                safe_stbd_heading = float(heading)
                safe_stbd_angle = float(delta)
                break
                
        # Поиск влево (против часовой стрелки)
        for delta in range(1, 180):
            heading = (current_heading_idx - delta) % 360
            if not unified_forbidden_headings[heading]:
                safe_port_heading = float(heading)
                safe_port_angle = float(delta)
                break

        recommended_heading = None
        recommended_action = Action.N_A
        decision_notes = []
        
        # МППСС-72 строго рекомендует повороты вправо. Выбираем правый борт, если угол поворота приемлемый (<= 110 градусов)
        if safe_stbd_heading is not None and safe_stbd_angle <= 110.0:
            recommended_heading = safe_stbd_heading
            recommended_action = Action.ALTER_COURSE_STARBOARD
            decision_notes.append(f"рекомендован поворот вправо на курс {recommended_heading:.1f}° с изменением на +{safe_stbd_angle:.1f}°")
        # Если правый поворот слишком велик, но левый поворот меньше и существует
        elif safe_port_heading is not None:
            recommended_heading = safe_port_heading
            recommended_action = Action.ALTER_COURSE_PORT
            decision_notes.append(f"рекомендован поворот влево на курс {recommended_heading:.1f}° с изменением на -{safe_port_angle:.1f}°")
            decision_notes.append("поворот влево противоречит стандартным рекомендациям правил расхождения")
        # Если правый поворот существует, но он велик, а левого нет
        elif safe_stbd_heading is not None:
            recommended_heading = safe_stbd_heading
            recommended_action = Action.ALTER_COURSE_STARBOARD
            decision_notes.append(f"рекомендован глубокий поворот вправо на курс {recommended_heading:.1f}° с изменением на +{safe_stbd_angle:.1f}°")
        else:
            # Безопасных курсов нет!
            recommended_heading = None
            recommended_action = Action.REDUCE_SPEED_OR_STOP
            decision_notes.append("критическая ситуация: все сектора курсов перекрыты опасностями")
            decision_notes.append("рекомендуется немедленно снизить ход, остановиться или дать задний ход согласно Правилу 8 (e)")

        # 4. Проверка физических ограничений (радиус циркуляции)
        maneuver_possible = True
        if recommended_heading is not None:
            delta_angle = min(abs(recommended_heading - own.course) % 360, 360 - (abs(recommended_heading - own.course) % 360))
            
            # Проверяем для ближайшей цели (с которой наименьший TCPA)
            is_possible = is_turn_possible(own.speed, own.min_turning_radius, delta_angle, closest_tcpa)
            if not is_possible:
                maneuver_possible = False
                decision_notes.append(
                    f"физическое ограничение: наше судно имеет радиус циркуляции {own.min_turning_radius} миль, "
                    f"на скорости {own.speed} узлов мы не успеем завершить поворот на {delta_angle:.1f}° до достижения "
                    f"кратчайшего сближения с целью {closest_target_name} за {closest_tcpa*60:.1f} минут"
                )
                decision_notes.append("рекомендация: совместите поворот с экстренным снижением скорости для уменьшения радиуса циркуляции")

        # Формируем объяснение
        explanation = general_explanation + ["-" * 40]
        
        # Добавляем индивидуальные выводы по целям
        for name, dec in target_decisions.items():
            if dec.collision_risk:
                explanation.extend(dec.explanation)
                explanation.append("")
                
        explanation.append("-" * 40)
        explanation.append("общее решение:")
        for i, note in enumerate(decision_notes):
            suffix = "." if i == len(decision_notes) - 1 else ";"
            explanation.append(f"- {note}{suffix}")
        
        # Секторы
        forbidden_sectors = convert_boolean_array_to_sectors(unified_forbidden_headings)
        sectors_desc = []
        for start, end in forbidden_sectors:
            sectors_desc.append(f"{start:.0f}°-{end:.0f}°")
        explanation.append(f"объединенные опасные сектора курсов: {', '.join(sectors_desc) if sectors_desc else 'нет'}")
        
        return Decision(
            collision_risk=True,
            own_role=VesselRole.GIVE_WAY if own_must_act else VesselRole.STAND_ON,
            recommended_action=recommended_action,
            recommended_heading=recommended_heading,
            forbidden_sectors=forbidden_sectors,
            target_decisions=target_decisions,
            maneuver_possible=maneuver_possible,
            explanation=explanation
        )
