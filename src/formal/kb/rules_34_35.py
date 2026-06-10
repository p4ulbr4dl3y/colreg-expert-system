"""Правила 34 и 35 МППСС-72: звуковые сигналы при маневрировании.

Правило 34: видимость хорошая.
  - один короткий: «изменяю курс вправо»;
  - два коротких: «изменяю курс влево»;
  - три коротких: «движители работают на задний ход»;
  - пять и более коротких: сигнал сомнения/предупреждения (правило 34d).

Правило 35: видимость ограниченная.
  - один продолжительный каждые 2 мин: механическое судно на ходу;
  - два продолжительных: остановившееся механическое судно;
  - один продолжительный + два коротких: парусное/рыболовное/CBD/RAM/NUC на ходу;
  - три последовательных (один продолжительный + два коротких) каждые 2 мин: судно не имеет хода.
"""
from __future__ import annotations

from ..engine import Rule
from ..substitution import Var
from ..world import Predicate


def rules() -> list[Rule]:
    own = Var("?own")
    tgt = Var("?tgt")
    action = Var("?action")
    vis = Var("?vis")
    own_type = Var("?own_type")
    own_speed = Var("?own_speed")
    own_role = Var("?own_role")
    own_course = Var("?own_course")

    is_power = lambda s: s.get(own_type.name) == "POWER_DRIVEN"
    is_non_power = lambda s: s.get(own_type.name) in (
        "SAILING", "FISHING", "CBD", "RAM", "NUC",
    )
    is_moving = lambda s: s.get(own_speed.name, 0) >= 0.1
    is_stopped = lambda s: s.get(own_speed.name, 0) < 0.1
    is_good = lambda s: s.get(vis.name) == "GOOD"
    is_restricted = lambda s: s.get(vis.name) == "RESTRICTED"
    is_stbd = lambda s: s.get(action.name) == "ALTER_COURSE_STARBOARD"
    is_port = lambda s: s.get(action.name) == "ALTER_COURSE_PORT"
    is_reverse = lambda s: s.get(action.name) == "REDUCE_SPEED_OR_STOP"
    is_stand_on = lambda s: s.get(own_role.name) == "STAND_ON"

    return [
        # Правило 35: ограниченная видимость
        Rule(
            id="rule_35_power_moving",
            citation="МППСС-72 правило 35 (a)",
            description="механическое судно на ходу: один продолжительный сигнал",
            tag="sound_signal",
            premises=(
                Predicate("visibility", (vis,)),
                Predicate("vessel_attr", (own, own_type, own_course, own_speed, Var("?tr"))),
            ),
            conclusions=(
                Predicate("sound_signal", (own, "один продолжительный звук каждые 2 минуты: судно с механическим двигателем на ходу")),
            ),
            guard=_and(is_restricted, is_power, is_moving),
        ),
        Rule(
            id="rule_35_power_stopped",
            citation="МППСС-72 правило 35 (a)",
            description="механическое судно без хода: два продолжительных сигнала",
            tag="sound_signal",
            premises=(
                Predicate("visibility", (vis,)),
                Predicate("vessel_attr", (own, own_type, own_course, own_speed, Var("?tr"))),
            ),
            conclusions=(
                Predicate("sound_signal", (own, "два продолжительных звука каждые 2 минуты: механическое судно остановилось и не имеет хода относительно воды")),
            ),
            guard=_and(is_restricted, is_power, is_stopped),
        ),
        Rule(
            id="rule_35_non_power_moving",
            citation="МППСС-72 правило 35 (b)",
            description="парусное/особое судно на ходу: продолжительный + два коротких",
            tag="sound_signal",
            premises=(
                Predicate("visibility", (vis,)),
                Predicate("vessel_attr", (own, own_type, own_course, own_speed, Var("?tr"))),
            ),
            conclusions=(
                Predicate("sound_signal", (own, "один продолжительный + два коротких звука каждые 2 минуты: особое судно на ходу")),
            ),
            guard=_and(is_restricted, is_non_power, is_moving),
        ),
        Rule(
            id="rule_35_non_power_stopped",
            citation="МППСС-72 правило 35 (b)",
            description="особое судно без хода: три последовательных сигнала",
            tag="sound_signal",
            premises=(
                Predicate("visibility", (vis,)),
                Predicate("vessel_attr", (own, own_type, own_course, own_speed, Var("?tr"))),
            ),
            conclusions=(
                Predicate("sound_signal", (own, "три последовательных звука (один продолжительный + два коротких) каждые 2 минуты: особое судно не имеет хода")),
            ),
            guard=_and(is_restricted, is_non_power, is_stopped),
        ),
        # Правило 34: хорошая видимость, маневры power-driven
        Rule(
            id="rule_34_starboard",
            citation="МППСС-72 правило 34 (a)(i)",
            description="один короткий: «изменяю курс вправо»",
            tag="sound_signal",
            premises=(
                Predicate("visibility", (vis,)),
                Predicate("vessel_attr", (own, own_type, own_course, own_speed, Var("?tr"))),
                Predicate("recommended_action", (own, tgt, action)),
            ),
            conclusions=(
                Predicate("sound_signal", (own, "один короткий звук: я изменяю свой курс вправо")),
            ),
            guard=_and(is_good, is_power, is_stbd),
        ),
        Rule(
            id="rule_34_port",
            citation="МППСС-72 правило 34 (a)(ii)",
            description="два коротких: «изменяю курс влево»",
            tag="sound_signal",
            premises=(
                Predicate("visibility", (vis,)),
                Predicate("vessel_attr", (own, own_type, own_course, own_speed, Var("?tr"))),
                Predicate("recommended_action", (own, tgt, action)),
            ),
            conclusions=(
                Predicate("sound_signal", (own, "два коротких звука: я изменяю свой курс влево")),
            ),
            guard=_and(is_good, is_power, is_port),
        ),
        Rule(
            id="rule_34_reverse",
            citation="МППСС-72 правило 34 (a)(iii)",
            description="три коротких: «движители на задний ход»",
            tag="sound_signal",
            premises=(
                Predicate("visibility", (vis,)),
                Predicate("vessel_attr", (own, own_type, own_course, own_speed, Var("?tr"))),
                Predicate("recommended_action", (own, tgt, action)),
            ),
            conclusions=(
                Predicate("sound_signal", (own, "три коротких звука: мои движители работают на задний ход")),
            ),
            guard=_and(is_good, is_power, is_reverse),
        ),
        # Правило 34 (d): сигнал сомнения для stand-on
        Rule(
            id="rule_34_d_doubt",
            citation="МППСС-72 правило 34 (d)",
            description="пять и более коротких: сигнал сомнения/предупреждения",
            tag="sound_signal",
            premises=(
                Predicate("visibility", (vis,)),
                Predicate("own_role", (own, tgt, own_role)),
                Predicate("risk_exists", (own, tgt)),
            ),
            conclusions=(
                Predicate("sound_signal", (own, "сигнал предупреждения при сомнениях в действиях уступающего судна: не менее пяти коротких и частых звуков")),
            ),
            guard=_and(is_good, is_stand_on),
        ),
    ]


def _and(*guards):
    from ..builtins import and_
    return and_(*guards)
