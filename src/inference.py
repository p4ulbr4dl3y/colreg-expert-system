"""Публичный API экспертной системы: класс COLREGInferenceEngine.

Совместим со старым императивным engine.py по сигнатуре .evaluate(own, targets, env, wind_direction),
но вся логика вывода реализована через формальный движок прямой цепочки
по декларативной базе знаний МППСС-72.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .formal import ForwardChainer, Predicate, Var
from .formal.kb import load_kb
from .geometry import (
    SAFE_CPA_DISTANCE,
    calculate_cpa_tcpa,
    convert_boolean_array_to_sectors,
    get_forbidden_headings_for_target,
    is_collision_risk_exists,
    is_turn_possible,
)
from .geometry_facts import build_ground_facts
from .models import (
    Action,
    Decision,
    Environment,
    InferenceTrace,
    ProofStep,
    TargetDecision,
    Vessel,
    VesselRole,
    VesselType,
    Visibility,
)


class COLREGInferenceEngine:
    """Многоцелевой логический вывод экспертной системы.

    Использует формальный движок прямой цепочки: вычисляет ground-факты
    геометрии, запускает правила МППСС-72 до фикс-поинта и собирает
    производные решения (роль, действие, опасные сектора) из выведенных
    предикатов.
    """

    def __init__(self) -> None:
        self._rules = load_kb()
        self._chainer = ForwardChainer(self._rules, max_iterations=100)

    def evaluate(
        self,
        own: Vessel,
        targets: List[Vessel],
        env: Environment,
        wind_direction: Optional[float] = None,
    ) -> Decision:
        if not targets:
            return Decision(
                collision_risk=False,
                own_role=VesselRole.N_A,
                recommended_action=Action.N_A,
                recommended_heading=own.course,
                explanation=["Нет окружающих судов-целей для оценки."],
            )

        self._chainer.reset()
        for f in build_ground_facts(own, targets, env, wind_direction):
            self._chainer.assert_facts([f])
        self._chainer.run_to_fixpoint()

        target_decisions: Dict[str, TargetDecision] = {}
        unified_forbidden = [False] * 360
        any_risk = False
        closest_tcpa = float("inf")
        closest_target_name = ""
        general_lines: List[str] = []
        target_status_lines: List[str] = []

        for tgt in targets:
            td = self._build_target_decision(own, tgt, env, target_status_lines)
            target_decisions[tgt.name] = td
            if td.collision_risk:
                any_risk = True
                if 0 < td.tcpa < closest_tcpa:
                    closest_tcpa = td.tcpa
                    closest_target_name = tgt.name
            for h, is_bad in enumerate(self._forbidden_for_target(own, tgt)):
                if is_bad:
                    unified_forbidden[h] = True

        for i, line in enumerate(target_status_lines):
            suf = "." if i == len(target_status_lines) - 1 else ";"
            general_lines.append(f"- {line}{suf}")

        if not any_risk:
            explanation = general_lines + ["Все цели расходятся безопасно."]
            signals = self._collect_sound_signals(own, env, Action.N_A, VesselRole.N_A, target_decisions)
            if signals:
                explanation.append("")
                explanation.append("необходимые звуковые сигналы:")
                for i, sig in enumerate(signals):
                    suf = "." if i == len(signals) - 1 else ";"
                    explanation.append(f"- {sig}{suf}")
            return Decision(
                collision_risk=False,
                own_role=VesselRole.N_A,
                recommended_action=Action.N_A,
                recommended_heading=own.course,
                forbidden_sectors=convert_boolean_array_to_sectors(unified_forbidden),
                target_decisions=target_decisions,
                explanation=explanation,
                trace=self._capture_trace(),
                fired_rules=self._capture_trace().fired_rule_ids(),
            )

        own_must_act = any(
            td.own_role in (VesselRole.GIVE_WAY, VesselRole.BOTH_GIVE_WAY)
            for td in target_decisions.values()
        )
        current_heading_idx = int(round(own.course)) % 360
        is_current_forbidden = unified_forbidden[current_heading_idx]

        if not own_must_act and not is_current_forbidden:
            explanation = general_lines + ["Наше судно сохраняет курс и скорость."]
            signals = self._collect_sound_signals(own, env, Action.KEEP_COURSE_SPEED, VesselRole.STAND_ON, target_decisions)
            if signals:
                explanation.append("")
                explanation.append("необходимые звуковые сигналы:")
                for i, sig in enumerate(signals):
                    suf = "." if i == len(signals) - 1 else ";"
                    explanation.append(f"- {sig}{suf}")
            return Decision(
                collision_risk=True,
                own_role=VesselRole.STAND_ON,
                recommended_action=Action.KEEP_COURSE_SPEED,
                recommended_heading=own.course,
                forbidden_sectors=convert_boolean_array_to_sectors(unified_forbidden),
                target_decisions=target_decisions,
                explanation=explanation,
                trace=self._capture_trace(),
                fired_rules=self._capture_trace().fired_rule_ids(),
            )

        safe_stbd_heading, safe_stbd_angle = self._find_safe_heading(current_heading_idx, unified_forbidden, +1)
        safe_port_heading, safe_port_angle = self._find_safe_heading(current_heading_idx, unified_forbidden, -1)

        recommended_heading: Optional[float] = None
        recommended_action = Action.N_A
        decision_notes: List[str] = []

        if safe_stbd_heading is not None and safe_stbd_angle <= 110.0:
            recommended_heading = safe_stbd_heading
            recommended_action = Action.ALTER_COURSE_STARBOARD
            decision_notes.append(
                f"рекомендован поворот вправо на курс {recommended_heading:.1f}° с изменением на +{safe_stbd_angle:.1f}°"
            )
        elif safe_port_heading is not None:
            recommended_heading = safe_port_heading
            recommended_action = Action.ALTER_COURSE_PORT
            decision_notes.append(
                f"рекомендован поворот влево на курс {recommended_heading:.1f}° с изменением на -{safe_port_angle:.1f}°"
            )
            decision_notes.append(
                "поворот влево противоречит стандартным рекомендациям правил расхождения"
            )
        elif safe_stbd_heading is not None:
            recommended_heading = safe_stbd_heading
            recommended_action = Action.ALTER_COURSE_STARBOARD
            decision_notes.append(
                f"рекомендован глубокий поворот вправо на курс {recommended_heading:.1f}° с изменением на +{safe_stbd_angle:.1f}°"
            )
        else:
            recommended_heading = None
            recommended_action = Action.REDUCE_SPEED_OR_STOP
            decision_notes.append("критическая ситуация: все сектора курсов перекрыты опасностями")
            decision_notes.append("рекомендуется немедленно снизить ход, остановиться или дать задний ход согласно правилу 8 (e)")

        maneuver_possible = True
        if recommended_heading is not None:
            delta_angle = min(
                abs(recommended_heading - own.course) % 360,
                360 - (abs(recommended_heading - own.course) % 360),
            )
            is_possible = is_turn_possible(
                own.speed, own.min_turning_radius, delta_angle, closest_tcpa
            )
            if not is_possible:
                maneuver_possible = False
                decision_notes.append(
                    f"физическое ограничение: наше судно имеет радиус циркуляции {own.min_turning_radius} миль, "
                    f"на скорости {own.speed} узлов мы не успеем завершить поворот на {delta_angle:.1f}° до достижения "
                    f"кратчайшего сближения с целью {closest_target_name} за {closest_tcpa*60:.1f} минут"
                )
                decision_notes.append(
                    "рекомендация: совместите поворот с экстренным снижением скорости для уменьшения радиуса циркуляции"
                )

        explanation = general_lines + ["-" * 40]
        for _, dec in target_decisions.items():
            if dec.collision_risk:
                explanation.extend(dec.explanation)
                explanation.append("")
        explanation.append("-" * 40)
        explanation.append("общее решение:")
        for i, note in enumerate(decision_notes):
            suf = "." if i == len(decision_notes) - 1 else ";"
            explanation.append(f"- {note}{suf}")

        forbidden_sectors = convert_boolean_array_to_sectors(unified_forbidden)
        sectors_desc = [f"{s:.0f}°-{e:.0f}°" for s, e in forbidden_sectors]
        explanation.append(
            f"объединенные опасные сектора курсов: {', '.join(sectors_desc) if sectors_desc else 'нет'}"
        )

        own_role = VesselRole.GIVE_WAY if own_must_act else VesselRole.STAND_ON
        signals = self._collect_sound_signals(own, env, recommended_action, own_role, target_decisions)
        if signals:
            explanation.append("")
            explanation.append("необходимые звуковые сигналы:")
            for i, sig in enumerate(signals):
                suf = "." if i == len(signals) - 1 else ";"
                explanation.append(f"- {sig}{suf}")

        trace = self._capture_trace()
        return Decision(
            collision_risk=True,
            own_role=own_role,
            recommended_action=recommended_action,
            recommended_heading=recommended_heading,
            forbidden_sectors=forbidden_sectors,
            target_decisions=target_decisions,
            maneuver_possible=maneuver_possible,
            explanation=explanation,
            trace=trace,
            fired_rules=trace.fired_rule_ids(),
        )

    # --- внутренние помощники ---------------------------------------------

    def _build_target_decision(
        self,
        own: Vessel,
        tgt: Vessel,
        env: Environment,
        status_lines: List[str],
    ) -> TargetDecision:
        from .geometry import calculate_relative_bearing

        dist = math.sqrt((tgt.x - own.x) ** 2 + (tgt.y - own.y) ** 2)
        cpa, tcpa = calculate_cpa_tcpa(own, tgt)
        risk, _, _, _ = is_collision_risk_exists(own, tgt)
        rb_own = calculate_relative_bearing(own, tgt)

        side = "правый борт" if rb_own < 180 else "левый борт"
        desc = f"цель {tgt.name}, дистанция {dist:.2f} миль, кратчайшее сближение {cpa:.2f} миль, относительный пеленг {rb_own:.1f}° ({side})"
        if math.isfinite(tcpa) and tcpa > 0:
            desc += f", время сближения {tcpa*60:.1f} минут"
        status_key = "опасное" if risk else "безопасное"
        status_lines.append(f"{status_key} сближение: {desc}")

        if not risk:
            return TargetDecision(
                target_name=tgt.name,
                collision_risk=False,
                encounter_type="SAFE",
                own_role=VesselRole.N_A,
                recommended_action=Action.N_A,
                cpa=cpa,
                tcpa=tcpa,
                explanation=[f"Сближение с {tgt.name} безопасно."],
            )

        # Запрашиваем выведенные факты у движка. Используем query_preferred
        # для разрешения конфликтов: правило с наибольшим precedence побеждает.
        own_name = own.name
        et_facts = self._chainer.query_preferred(
            Predicate("encounter_type", (own_name, tgt.name, Var("?et")))
        )
        role_facts = self._chainer.query_preferred(
            Predicate("own_role", (own_name, tgt.name, Var("?r")))
        )
        action_facts = self._chainer.query_preferred(
            Predicate("recommended_action", (own_name, tgt.name, Var("?a")))
        )

        et = et_facts[0].args[2] if et_facts else "UNKNOWN"
        role_str = role_facts[0].args[2] if role_facts else "GIVE_WAY"
        action_str = action_facts[0].args[2] if action_facts else "ALTER_COURSE_STARBOARD"

        notes: List[str] = [f"оценка расхождения с судном-целью {tgt.name}:"]
        if env.visibility == Visibility.RESTRICTED:
            notes.append("применяется правило 19 для ограниченной видимости: приоритеты типов судов не действуют")
        if et == "own_overtaking":
            notes.append("ситуация обгона согласно правилу 13: наше судно обгоняет цель и обязано держаться в стороне от ее пути")
        elif et == "target_overtaking":
            notes.append("ситуация обгона согласно правилу 13: цель обгоняет наше судно, мы должны сохранять курс и скорость")
        elif et == "head_on":
            notes.append("ситуация встречных курсов согласно правилу 14: оба судна должны изменить курс вправо")
        elif et == "crossing_starboard":
            notes.append("ситуация пересечения курсов согласно правилу 15: цель находится справа, мы обязаны уступить дорогу")
        elif et == "crossing_port":
            notes.append("ситуация пересечения курсов согласно правилу 15: цель находится слева, мы имеем преимущество и сохраняем курс и скорость")
        elif et == "priority":
            notes.append("взаимные обязанности согласно правилу 18")
        elif et == "sailing_diff_tack":
            notes.append("расхождение парусных судов согласно правилу 12 (a)(i): разные галсы")
        elif et == "sailing_same_tack":
            notes.append("расхождение парусных судов согласно правилу 12 (a)(ii): одинаковые галсы")
        elif et.startswith("restricted_"):
            notes.append("расхождение в условиях ограниченной видимости согласно правилу 19")
        else:
            notes.append("неопределенный сектор: рекомендуется изменить курс вправо")

        # Правило 17
        last_resort = self._chainer.has(
            Predicate("last_resort", (own_name, tgt.name))
        )
        if last_resort:
            notes.append(
                f"крайняя необходимость согласно правилу 17 (b): время сближения {tcpa*60:.1f} минут является критическим, мы обязаны маневрировать для избежания столкновения"
            )

        suffix = "." if len(notes) == 1 else ";"
        notes[0] = f"  - {notes[0]}{suffix}"

        for i, n in enumerate(notes[1:], 1):
            suf = "." if i == len(notes) - 1 else ";"
            notes[i] = f"  - {n}{suf}"

        return TargetDecision(
            target_name=tgt.name,
            collision_risk=True,
            encounter_type=et if env.visibility == Visibility.GOOD else "RESTRICTED",
            own_role=_role_from_str(role_str),
            recommended_action=_action_from_str(action_str),
            cpa=cpa,
            tcpa=tcpa,
            explanation=notes,
            fired_rules=self._rules_fired_for_target(own_name, tgt.name),
        )

    def _rules_fired_for_target(self, own_name: str, tgt_name: str) -> List[str]:
        out: List[str] = []
        for step in self._chainer.proof:
            for cname, cargs in step.conclusions_resolved:
                if cname not in (
                    "own_role",
                    "recommended_action",
                    "encounter_type",
                    "last_resort",
                    "block_left_turn",
                    "block_right_turn",
                ):
                    continue
                if own_name in cargs and tgt_name in cargs:
                    out.append(step.rule_id)
                    break
        return out

    def _forbidden_for_target(self, own: Vessel, tgt: Vessel) -> List[bool]:
        """Возвращает 360-элементный список опасных курсов с учётом
        расширений из heading_blocks (правила 14, 15, 17c, 19d)."""
        from .geometry import calculate_relative_bearing

        forbidden = list(self._geometry_forbidden(own, tgt))
        own_name = own.name
        rb_own = calculate_relative_bearing(own, tgt)
        rb_tgt = calculate_relative_bearing(tgt, own)

        block_left = self._chainer.has(Predicate("block_left_turn", (own_name, tgt.name)))
        block_right = self._chainer.has(Predicate("block_right_turn", (own_name, tgt.name)))

        # Для правила 19: смотрим encounter_type, чтобы понять, какие сектора блокировать.
        et_facts = self._chainer.query(
            Predicate("encounter_type", (own_name, tgt.name, Var("?et")))
        )
        et = et_facts[0].args[2] if et_facts else ""

        if block_left:
            for angle_diff in range(1, 121):
                blocked = int(round(own.course - angle_diff)) % 360
                forbidden[blocked] = True
        if block_right:
            for angle_diff in range(1, 121):
                blocked = int(round(own.course + angle_diff)) % 360
                forbidden[blocked] = True
        return forbidden

    def _geometry_forbidden(self, own: Vessel, tgt: Vessel) -> List[bool]:
        from .geometry import (
            CRITICAL_TCPA,
            SAFE_CPA_DISTANCE,
            calculate_cpa_tcpa,
            calculate_distance,
        )
        dist = calculate_distance(own, tgt)
        effective_safe = SAFE_CPA_DISTANCE
        if dist < SAFE_CPA_DISTANCE:
            effective_safe = max(0.5, dist * 0.8)
        # Собственная симуляция
        out = [False] * 360
        for h in range(360):
            tmp = Vessel(own.name, own.x, own.y, float(h), own.speed, own.vessel_type)
            cpa, tcpa = calculate_cpa_tcpa(tmp, tgt)
            if tcpa > 0 and tcpa < CRITICAL_TCPA and cpa < effective_safe:
                out[h] = True
        return out

    def _find_safe_heading(
        self, current: int, forbidden: List[bool], direction: int
    ) -> Tuple[Optional[float], float]:
        for delta in range(1, 180):
            h = (current + direction * delta) % 360
            if not forbidden[h]:
                return float(h), float(delta)
        return None, 360.0

    def _collect_sound_signals(
        self,
        own: Vessel,
        env: Environment,
        recommended_action: Action,
        own_role: VesselRole,
        target_decisions: Dict[str, TargetDecision],
    ) -> List[str]:
        """Читает sound_signal предикаты из world и преобразует в строки."""
        own_name = own.name
        facts = self._chainer.query(Predicate("sound_signal", (own_name, Var("?s"))))
        return [f.args[1] for f in facts]

    def _capture_trace(self) -> InferenceTrace:
        steps = [
            ProofStep(
                rule_id=s.rule_id,
                citation=s.citation,
                description=s.description,
                premises_resolved=s.premises_resolved,
                conclusions_resolved=s.conclusions_resolved,
                substitution=s.substitution,
            )
            for s in self._chainer.proof
        ]
        return InferenceTrace(
            steps=steps,
            iterations=self._chainer.iterations,
            fired_count=self._chainer.fired_count,
        )


def _role_from_str(s: str) -> VesselRole:
    return {
        "GIVE_WAY": VesselRole.GIVE_WAY,
        "STAND_ON": VesselRole.STAND_ON,
        "BOTH_GIVE_WAY": VesselRole.BOTH_GIVE_WAY,
    }.get(s, VesselRole.N_A)


def _action_from_str(s: str) -> Action:
    return {
        "KEEP_COURSE_SPEED": Action.KEEP_COURSE_SPEED,
        "ALTER_COURSE_STARBOARD": Action.ALTER_COURSE_STARBOARD,
        "ALTER_COURSE_PORT": Action.ALTER_COURSE_PORT,
        "REDUCE_SPEED_OR_STOP": Action.REDUCE_SPEED_OR_STOP,
    }.get(s, Action.N_A)
