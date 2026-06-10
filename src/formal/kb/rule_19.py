"""Правило 19 МППСС-72: расхождение судов при ограниченной видимости.

В условиях ограниченной видимости приоритеты типов судов (правило 18)
не действуют, а правила 14/15/18 заменяются логикой обхода по секторам.
"""
from __future__ import annotations

from ..engine import Rule
from ..substitution import Var
from ..world import Predicate


def rules() -> list[Rule]:
    own = Var("?own")
    tgt = Var("?tgt")
    vis = Var("?vis")

    return [
        Rule(
            id="rule_19_ahead_not_overtaking",
            citation="МППСС-72 правило 19 (d)(i)",
            description="цель впереди траверза, не обгон - избегаем поворота влево",
            tag="rule_19",
            precedence=90,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("visibility", (vis,)),
                Predicate("target_ahead_of_beam", (own, tgt)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "restricted_ahead")),
                Predicate("own_role", (own, tgt, "BOTH_GIVE_WAY")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "ALTER_COURSE_STARBOARD"),
                ),
                Predicate("no_left_turn", (own, tgt)),
            ),
            guard=eq_vis_restricted(vis),
        ),
        Rule(
            id="rule_19_ahead_overtaking",
            citation="МППСС-72 правило 19 (d)(i)",
            description="цель впереди, мы её обгоняем - уступаем ей",
            tag="rule_19",
            precedence=85,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("visibility", (vis,)),
                Predicate("target_ahead_of_beam", (own, tgt)),
                Predicate("own_overtaking", (own, tgt)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "restricted_ahead_overtaking")),
                Predicate("own_role", (own, tgt, "GIVE_WAY")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "ALTER_COURSE_STARBOARD"),
                ),
            ),
            guard=eq_vis_restricted(vis),
        ),
        Rule(
            id="rule_19_abaft_starboard",
            citation="МППСС-72 правило 19 (d)(ii)",
            description="цель позади траверза справа - избегаем поворота вправо в её сторону",
            tag="rule_19",
            precedence=85,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("visibility", (vis,)),
                Predicate("target_abaft_beam", (own, tgt)),
                Predicate("target_on_starboard", (own, tgt)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "restricted_abaft_stbd")),
                Predicate("own_role", (own, tgt, "BOTH_GIVE_WAY")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "ALTER_COURSE_PORT"),
                ),
                Predicate("no_right_turn", (own, tgt)),
            ),
            guard=eq_vis_restricted(vis),
        ),
        Rule(
            id="rule_19_abaft_port",
            citation="МППСС-72 правило 19 (d)(ii)",
            description="цель позади траверза слева - избегаем поворота влево в её сторону",
            tag="rule_19",
            precedence=85,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("visibility", (vis,)),
                Predicate("target_abaft_beam", (own, tgt)),
                Predicate("target_on_port", (own, tgt)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "restricted_abaft_port")),
                Predicate("own_role", (own, tgt, "BOTH_GIVE_WAY")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "ALTER_COURSE_STARBOARD"),
                ),
                Predicate("no_left_turn", (own, tgt)),
            ),
            guard=eq_vis_restricted(vis),
        ),
    ]


def eq_vis_restricted(vis: Var):
    """Гард: visibility = RESTRICTED."""
    def check(subst):
        return subst.get(vis.name) == "RESTRICTED"
    return check
