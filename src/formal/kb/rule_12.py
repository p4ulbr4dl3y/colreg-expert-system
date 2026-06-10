"""Правило 12 МППСС-72: расхождение парусных судов.

(a)(i)  разные галсы: судно на левом галсе уступает судну на правом;
(a)(ii) одни галсы: наветренное судно уступает подветренному.
"""
from __future__ import annotations

from ..builtins import and_, eq, gt as gt_, le
from ..engine import Rule
from ..substitution import Var
from ..world import Predicate


def rules() -> list[Rule]:
    own = Var("?own")
    tgt = Var("?tgt")
    own_tack = Var("?own_tack")
    tgt_tack = Var("?tgt_tack")
    own_ws = Var("?own_ws")
    tgt_ws = Var("?tgt_ws")

    tack_differs = lambda subst: subst.get(own_tack.name) != subst.get(tgt_tack.name)
    own_tack_is_port = lambda subst: subst.get(own_tack.name) == "PORT"
    own_tack_is_starboard = lambda subst: subst.get(own_tack.name) == "STARBOARD"
    tack_same = lambda subst: subst.get(own_tack.name) == subst.get(tgt_tack.name)
    own_more_windward = lambda subst: subst.get(own_ws.name, -1e9) > subst.get(tgt_ws.name, -1e9)
    own_more_leeward = lambda subst: subst.get(own_ws.name, 1e9) <= subst.get(tgt_ws.name, 1e9)

    return [
        Rule(
            id="rule_12_different_tack_port_gives_way",
            citation="МППСС-72 правило 12 (a)(i)",
            description="наш галс левый, цель на правом - уступаем дорогу",
            tag="rule_12",
            precedence=200,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("sailing_tack", (own, own_tack)),
                Predicate("sailing_tack", (tgt, tgt_tack)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "sailing_diff_tack")),
                Predicate("own_role", (own, tgt, "GIVE_WAY")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "ALTER_COURSE_STARBOARD"),
                ),
            ),
            guard=and_(tack_differs, own_tack_is_port),
        ),
        Rule(
            id="rule_12_different_tack_starboard_stand_on",
            citation="МППСС-72 правило 12 (a)(i)",
            description="наш галс правый, цель на левом - сохраняем курс и скорость",
            tag="rule_12",
            precedence=200,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("sailing_tack", (own, own_tack)),
                Predicate("sailing_tack", (tgt, tgt_tack)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "sailing_diff_tack")),
                Predicate("own_role", (own, tgt, "STAND_ON")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "KEEP_COURSE_SPEED"),
                ),
            ),
            guard=and_(tack_differs, own_tack_is_starboard),
        ),
        Rule(
            id="rule_12_same_tack_windward_gives_way",
            citation="МППСС-72 правило 12 (a)(ii)",
            description="мы наветреннее цели на тех же галсах - уступаем дорогу",
            tag="rule_12",
            precedence=200,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("sailing_tack", (own, own_tack)),
                Predicate("sailing_tack", (tgt, tgt_tack)),
                Predicate("windward_score", (own, own_ws)),
                Predicate("windward_score", (tgt, tgt_ws)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "sailing_same_tack")),
                Predicate("own_role", (own, tgt, "GIVE_WAY")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "ALTER_COURSE_STARBOARD"),
                ),
            ),
            guard=and_(tack_same, own_more_windward),
        ),
        Rule(
            id="rule_12_same_tack_leeward_stand_on",
            citation="МППСС-72 правило 12 (a)(ii)",
            description="мы подветреннее цели на тех же галсах - сохраняем курс и скорость",
            tag="rule_12",
            precedence=200,
            premises=(
                Predicate("risk_exists", (own, tgt)),
                Predicate("sailing_tack", (own, own_tack)),
                Predicate("sailing_tack", (tgt, tgt_tack)),
                Predicate("windward_score", (own, own_ws)),
                Predicate("windward_score", (tgt, tgt_ws)),
            ),
            conclusions=(
                Predicate("encounter_type", (own, tgt, "sailing_same_tack")),
                Predicate("own_role", (own, tgt, "STAND_ON")),
                Predicate(
                    "recommended_action",
                    (own, tgt, "KEEP_COURSE_SPEED"),
                ),
            ),
            guard=and_(tack_same, own_more_leeward),
        ),
    ]
