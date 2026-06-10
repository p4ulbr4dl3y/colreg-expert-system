"""Правила 14 и 15 МППСС-72: встречное сближение и пересечение курсов.

Правило 14: лоб-в-лоб — оба суда изменяют курс вправо.
Правило 15: пересечение — судно, имеющее другое справа, уступает.
"""
from __future__ import annotations

from ..engine import Rule
from ..substitution import Var
from ..world import Predicate
from ..builtins import in_range


def rules() -> list[Rule]:
    own = Var("?own")
    tgt = Var("?tgt")

    return [
        Rule(
            id="rule_14_head_on",
            citation="МППСС-72 правило 14 (a)",
            description="встречное сближение: оба суда изменяют курс вправо",
            tag="rule_14",
            precedence=100,  # самый специфичный — выигрывает конфликты
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("equal_priority", (own, tgt)),
                Predicate("reciprocal_courses", (own, tgt)),
                Predicate("both_see_headon", (own, tgt)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "head_on")),
                Predicate("own_role", (own, tgt, "BOTH_GIVE_WAY")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "ALTER_COURSE_STARBOARD"),
                ),
            ),
        ),
        Rule(
            id="rule_15_crossing_stbd",
            citation="МППСС-72 правило 15",
            description="пересечение курсов: цель справа — уступаем дорогу",
            tag="rule_15",
            precedence=60,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("equal_priority", (own, tgt)),
                Predicate("target_on_starboard", (own, tgt)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "crossing_starboard")),
                Predicate("own_role", (own, tgt, "GIVE_WAY")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "ALTER_COURSE_STARBOARD"),
                ),
            ),
        ),
        Rule(
            id="rule_15_crossing_port",
            citation="МППСС-72 правило 15",
            description="пересечение курсов: цель слева — сохраняем курс",
            tag="rule_15",
            precedence=60,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("equal_priority", (own, tgt)),
                Predicate("target_on_port", (own, tgt)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "crossing_port")),
                Predicate("own_role", (own, tgt, "STAND_ON")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "KEEP_COURSE_SPEED"),
                ),
            ),
        ),
    ]
