"""Правило 18 МППСС-72: взаимные обязанности судов в зависимости от типа.

Иерархия приоритетов (от низкого к высокому):
  POWER_DRIVEN < SAILING < FISHING < CBD < RAM < NUC

Судно с меньшим приоритетом уступает дорогу судну с большим.
"""
from __future__ import annotations

from ..engine import Rule
from ..substitution import Var
from ..world import Predicate


def rules() -> list[Rule]:
    own = Var("?own")
    tgt = Var("?tgt")

    return [
        Rule(
            id="rule_18_give_way",
            citation="МППСС-72 правило 18",
            description="у нашего судна меньший приоритет: уступаем дорогу",
            tag="rule_18",
            precedence=50,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("lower_priority", (own, tgt)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "priority")),
                Predicate("own_role", (own, tgt, "GIVE_WAY")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "ALTER_COURSE_STARBOARD"),
                ),
            ),
        ),
        Rule(
            id="rule_18_stand_on",
            citation="МППСС-72 правило 18",
            description="у нашего судна больший приоритет: сохраняем курс и скорость",
            tag="rule_18",
            precedence=50,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("higher_priority", (own, tgt)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "priority")),
                Predicate("own_role", (own, tgt, "STAND_ON")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "KEEP_COURSE_SPEED"),
                ),
            ),
        ),
    ]
