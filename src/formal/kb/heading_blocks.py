"""Расширения запрещённых секторов курсов (правила 14, 15, 17c, 19d).

В хорошей видимости: если мы уступаем (GIVE_WAY или BOTH_GIVE_WAY) и это
не наш обгон — запрещаем повороты влево на 1..120°.

В ограниченной видимости: применяем правило 19(d):
- цель впереди, не обгон: запрет поворотов влево;
- цель позади справа: запрет поворотов вправо;
- цель позади слева: запрет поворотов влево.

Эти правила — не статьи МППСС-72, а геометрическая реализация запретов
поворотов, описанных в статьях 14, 15, 17c и 19d.
"""
from __future__ import annotations

from ..engine import Rule
from ..substitution import Var
from ..world import Predicate
from ..builtins import and_, or_


def rules() -> list[Rule]:
    own = Var("?own")
    tgt = Var("?tgt")
    role = Var("?role")
    vis = Var("?vis")
    et = Var("?et")

    is_give_way = lambda s: s.get(role.name) in ("GIVE_WAY", "BOTH_GIVE_WAY")
    not_own_overtake = lambda s: s.get(et.name) != "own_overtaking"
    is_good = lambda s: s.get(vis.name) == "GOOD"
    is_restricted = lambda s: s.get(vis.name) == "RESTRICTED"

    return [
        Rule(
            id="extend_block_left_in_good_visibility",
            citation="правила 14, 15, 17 (c): запрет поворота влево на 1..120°",
            description="при уступке дороги в хорошей видимости запрещены повороты влево",
            tag="heading_block",
            premises=(
                Predicate("own_role", (own, tgt, role)),
                Predicate("encounter_type", (own, tgt, et)),
                Predicate("visibility", (vis,)),
            ),
            conclusions=(Predicate("block_left_turn", (own, tgt)),),
            guard=and_(is_give_way, not_own_overtake, is_good),
        ),
        Rule(
            id="extend_block_left_in_restricted_ahead",
            citation="правило 19 (d)(i): запрет поворота влево",
            description="в ограниченной видимости, цель впереди — запрет поворотов влево",
            tag="heading_block",
            premises=(
                Predicate("encounter_type", (own, tgt, et)),
                Predicate("visibility", (vis,)),
            ),
            conclusions=(Predicate("block_left_turn", (own, tgt)),),
            guard=and_(
                lambda s: s.get(et.name) in ("restricted_ahead", "restricted_abaft_port"),
                is_restricted,
            ),
        ),
        Rule(
            id="extend_block_right_in_restricted_abaft_stbd",
            citation="правило 19 (d)(ii): запрет поворота вправо в сторону цели",
            description="в ограниченной видимости, цель позади справа — запрет поворотов вправо",
            tag="heading_block",
            premises=(
                Predicate("encounter_type", (own, tgt, et)),
                Predicate("visibility", (vis,)),
            ),
            conclusions=(Predicate("block_right_turn", (own, tgt)),),
            guard=and_(
                lambda s: s.get(et.name) == "restricted_abaft_stbd",
                is_restricted,
            ),
        ),
    ]
