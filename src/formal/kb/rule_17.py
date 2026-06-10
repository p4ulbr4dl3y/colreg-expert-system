"""Правило 17 МППСС-72: маневр крайнего момента для судна, которому уступают.

(b) Если судно, обязанное уступить дорогу, не выполняет этого, судно с
    преимуществом обязано маневрировать само.

Если мы stand-on, но сближение критически близкое (TCPA < 0.15 ч), мы
обязаны действовать.
"""
from __future__ import annotations

from ..engine import Rule
from ..substitution import Var
from ..world import Predicate
from ..builtins import and_, in_range


def rules() -> list[Rule]:
    own = Var("?own")
    tgt = Var("?tgt")
    role = Var("?role")
    tcpa = Var("?tcpa")

    eq_stand_on = lambda s: s.get(role.name) == "STAND_ON"

    return [
        Rule(
            id="rule_17_last_resort_action",
            citation="МППСС-72 правило 17 (b)(c)",
            description="судно с преимуществом вынуждено маневрировать из-за критического TCPA",
            tag="rule_17",
            precedence=110,  # override поверх всех остальных правил
            premises=(
                Predicate("own_role", (own, tgt, role)),
                Predicate("tcpa", (own, tgt, tcpa)),
            ),
            conclusions=(
                Predicate("last_resort", (own, tgt)),
                Predicate("own_role", (own, tgt, "GIVE_WAY")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "ALTER_COURSE_STARBOARD"),
                ),
            ),
            guard=and_(eq_stand_on, in_range(tcpa, 0, 0.15)),
        ),
    ]
