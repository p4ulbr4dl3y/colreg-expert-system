"""Преобразование Vessel + Environment в ground-факты для формального движка.

Численная геометрия (CPA, TCPA, пеленги, дистанции) считается здесь один
раз и ассертится в FactBase как набор ground-предикатов. Правила KB
работают только с этими предикатами - никаких float-вычислений внутри
формального вывода.
"""
from __future__ import annotations

import math
from typing import Iterable, List, Optional

from .formal import Predicate
from .geometry import (
    SAFE_CPA_DISTANCE,
    calculate_cpa_tcpa,
    calculate_distance,
    calculate_relative_bearing,
    get_forbidden_headings_for_target,
    is_collision_risk_exists,
)
from .models import Environment, Vessel, Visibility


def _r(v: float) -> float:
    """Округление float до разумной точности для детерминизма в KB."""
    return round(v, 4)


def _windward_score(vessel: Vessel, wind_dir_deg: float) -> float:
    """Чем больше значение, тем судно более наветренное (ближе к источнику ветра)."""
    rad = math.radians(wind_dir_deg)
    w_x = math.sin(rad)
    w_y = math.cos(rad)
    return -(vessel.x * w_x + vessel.y * w_y)


def build_ground_facts(
    own: Vessel,
    targets: List[Vessel],
    env: Environment,
    wind_direction: Optional[float] = None,
) -> List[Predicate]:
    """Строит список ground-предикатов, описывающих сцену для формального движка."""
    facts: List[Predicate] = []

    own_name = own.name
    facts.append(Predicate("vessel", (own_name,)))
    facts.append(
        Predicate(
            "vessel_attr",
            (
                own_name,
                own.vessel_type.name,
                _r(own.course),
                _r(own.speed),
                _r(own.min_turning_radius),
            ),
        )
    )

    facts.append(Predicate("visibility", (env.visibility.name,)))
    facts.append(Predicate("in_narrow_channel", (bool(env.in_narrow_channel),)))
    facts.append(Predicate("in_tss", (bool(env.in_tss),)))

    if wind_direction is not None:
        facts.append(Predicate("wind_direction", (_r(wind_direction),)))
        if own.vessel_type.name == "SAILING":
            facts.append(
                Predicate(
                    "windward_score",
                    (own_name, _r(_windward_score(own, wind_direction))),
                )
            )
            facts.append(
                Predicate(
                    "sailing_tack",
                    (own_name, _resolve_tack(own, wind_direction)),
                )
            )

    for tgt in targets:
        tgt_name = tgt.name
        facts.append(Predicate("target", (own_name, tgt_name)))
        facts.append(
            Predicate(
                "vessel_attr",
                (
                    tgt_name,
                    tgt.vessel_type.name,
                    _r(tgt.course),
                    _r(tgt.speed),
                    _r(tgt.min_turning_radius),
                ),
            )
        )

        dist = calculate_distance(own, tgt)
        cpa, tcpa = calculate_cpa_tcpa(own, tgt)
        risk, _, _, _ = is_collision_risk_exists(own, tgt)
        rb_own = calculate_relative_bearing(own, tgt)
        rb_tgt = calculate_relative_bearing(tgt, own)
        course_diff = (tgt.course - own.course) % 360

        facts.append(Predicate("distance", (own_name, tgt_name, _r(dist))))
        facts.append(Predicate("cpa", (own_name, tgt_name, _r(cpa))))
        facts.append(
            Predicate(
                "tcpa",
                (own_name, tgt_name, _r(tcpa) if math.isfinite(tcpa) else 1e9),
            )
        )
        if risk:
            facts.append(Predicate("risk_exists", (own_name, tgt_name)))
        facts.append(
            Predicate(
                "rb_own_to_tgt",
                (own_name, tgt_name, _r(rb_own)),
            )
        )
        facts.append(
            Predicate(
                "rb_tgt_to_own",
                (own_name, tgt_name, _r(rb_tgt)),
            )
        )
        facts.append(
            Predicate(
                "course_diff",
                (own_name, tgt_name, _r(course_diff)),
            )
        )
        if own.speed > tgt.speed:
            facts.append(Predicate("speed_gt", (own_name, tgt_name)))
        elif tgt.speed > own.speed:
            facts.append(Predicate("speed_gt", (tgt_name, own_name)))

        # Запрещённые курсы
        effective_safe = SAFE_CPA_DISTANCE
        if dist < SAFE_CPA_DISTANCE:
            effective_safe = max(0.5, dist * 0.8)
        forbidden = get_forbidden_headings_for_target(
            own, tgt, safe_dist=effective_safe
        )
        for h, bad in enumerate(forbidden):
            if bad:
                facts.append(
                    Predicate("forbidden_heading", (own_name, tgt_name, h))
                )

        # Парусные галсы цели (нужно для правила 12)
        if wind_direction is not None and tgt.vessel_type.name == "SAILING":
            facts.append(
                Predicate(
                    "sailing_tack",
                    (tgt_name, _resolve_tack(tgt, wind_direction)),
                )
            )
            facts.append(
                Predicate(
                    "windward_score",
                    (tgt_name, _r(_windward_score(tgt, wind_direction))),
                )
            )

        # Приоритет типов судов (правило 18)
        facts.append(
            Predicate(
                "vessel_priority_rank",
                (own_name, _priority_rank(own.vessel_type)),
            )
        )
        facts.append(
            Predicate(
                "vessel_priority_rank",
                (tgt_name, _priority_rank(tgt.vessel_type)),
            )
        )

    return facts


def _priority_rank(v_type) -> int:
    ranks = {
        "NUC": 5,
        "RAM": 4,
        "CBD": 3,
        "FISHING": 2,
        "SAILING": 1,
        "POWER_DRIVEN": 0,
    }
    return ranks.get(v_type.name, 0)


def _resolve_tack(vessel: Vessel, wind_dir_deg: float) -> str:
    own_wind_rel = (wind_dir_deg - vessel.course) % 360
    return "STARBOARD" if 0 <= own_wind_rel < 180 else "PORT"
