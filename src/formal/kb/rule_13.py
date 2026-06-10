"""Правило 13 МППСС-72: обгон.

Судно, догоняющее другое с направления более 22.5° позади его траверза,
является обгоняющим и должно держаться в стороне от пути обгоняемого.
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
            id="rule_13_own_overtaking",
            citation="МППСС-72 правило 13 (a)",
            description="обгон с нашей стороны: уступаем дорогу обгоняемому",
            tag="rule_13",
            precedence=80,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("own_overtaking", (own, tgt)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "own_overtaking")),
                Predicate("own_role", (own, tgt, "GIVE_WAY")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "ALTER_COURSE_STARBOARD"),
                ),
            ),
        ),
        Rule(
            id="rule_13_target_overtaking",
            citation="МППСС-72 правило 13 (a)",
            description="обгон со стороны цели: сохраняем курс и скорость",
            tag="rule_13",
            precedence=80,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("target_overtaking", (own, tgt)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "target_overtaking")),
                Predicate("own_role", (own, tgt, "STAND_ON")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "KEEP_COURSE_SPEED"),
                ),
            ),
        ),
    ]
