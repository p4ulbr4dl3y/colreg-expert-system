"""Помощники-предикаты: геометрические производные от ground-фактов.

Эти правила не выражают статьи МППСС-72 напрямую — они вычисляют
производные понятия (положение относительно траверза, галс, сектор
сближения), которые используются в правилах МППСС-72.
"""
from __future__ import annotations

from ..builtins import in_range, or_
from ..engine import Rule
from ..substitution import Var
from ..world import Predicate


def helpers() -> list[Rule]:
    own = Var("?own")
    tgt = Var("?tgt")
    rb = Var("?rb")
    rb_t = Var("?rb_t")
    diff = Var("?diff")
    r1 = Var("?r1")
    r2 = Var("?r2")

    rb_ahead = or_(in_range(rb, 0, 90), in_range(rb, 270, 360))
    rb_abaft = in_range(rb, 90, 270)
    rb_stbd = in_range(rb, 0, 180)
    rb_port = in_range(rb, 180, 360)
    rb_overtake_zone = in_range(rb_t, 112.5, 247.5)
    rb_overtake_zone_own = in_range(rb, 112.5, 247.5)
    course_diff_recip = in_range(diff, 170, 190)
    rb_near_bow = or_(in_range(rb, 0, 10), in_range(rb, 350, 360))
    rb_near_bow_t = or_(in_range(rb_t, 0, 10), in_range(rb_t, 350, 360))

    eq_rank = lambda s: s.get(r1.name) == s.get(r2.name)
    lt_rank = lambda s: s.get(r1.name) < s.get(r2.name)
    gt_rank = lambda s: s.get(r1.name) > s.get(r2.name)

    return [
        Rule(
            id="helper_target_ahead_of_beam",
            citation="геометрия: положение относительно траверза",
            description="цель впереди траверза собственного судна",
            tag="helper",
            premises=(
                Predicate("target", (own, tgt)),
                Predicate("rb_own_to_tgt", (own, tgt, rb)),
            ),
            conclusions=(Predicate("target_ahead_of_beam", (own, tgt)),),
            guard=rb_ahead,
        ),
        Rule(
            id="helper_target_abaft_beam",
            citation="геометрия: положение относительно траверза",
            description="цель позади траверза собственного судна",
            tag="helper",
            premises=(
                Predicate("target", (own, tgt)),
                Predicate("rb_own_to_tgt", (own, tgt, rb)),
            ),
            conclusions=(Predicate("target_abaft_beam", (own, tgt)),),
            guard=rb_abaft,
        ),
        Rule(
            id="helper_target_on_starboard",
            citation="геометрия: положение относительно траверза",
            description="цель на правом траверзе (0, 180]",
            tag="helper",
            premises=(
                Predicate("target", (own, tgt)),
                Predicate("rb_own_to_tgt", (own, tgt, rb)),
            ),
            conclusions=(Predicate("target_on_starboard", (own, tgt)),),
            guard=rb_stbd,
        ),
        Rule(
            id="helper_target_on_port",
            citation="геометрия: положение относительно траверза",
            description="цель на левом траверзе (180, 360)",
            tag="helper",
            premises=(
                Predicate("target", (own, tgt)),
                Predicate("rb_own_to_tgt", (own, tgt, rb)),
            ),
            conclusions=(Predicate("target_on_port", (own, tgt)),),
            guard=rb_port,
        ),
        Rule(
            id="helper_own_overtaking",
            citation="геометрия: признаки обгона",
            description="признак обгона нашим судном согласно правилу 13",
            tag="helper",
            premises=(
                Predicate("target", (own, tgt)),
                Predicate("rb_tgt_to_own", (own, tgt, rb_t)),
                Predicate("speed_gt", (own, tgt)),
            ),
            conclusions=(Predicate("own_overtaking", (own, tgt)),),
            guard=rb_overtake_zone,
        ),
        Rule(
            id="helper_target_overtaking",
            citation="геометрия: признаки обгона",
            description="признак обгона нашего судна целью согласно правилу 13",
            tag="helper",
            premises=(
                Predicate("target", (own, tgt)),
                Predicate("rb_own_to_tgt", (own, tgt, rb)),
                Predicate("speed_gt", (tgt, own)),
            ),
            conclusions=(Predicate("target_overtaking", (own, tgt)),),
            guard=rb_overtake_zone_own,
        ),
        Rule(
            id="helper_reciprocal_courses",
            citation="геометрия: признаки встречного сближения",
            description="курсы практически противоположны (правило 14)",
            tag="helper",
            premises=(
                Predicate("target", (own, tgt)),
                Predicate("course_diff", (own, tgt, diff)),
            ),
            conclusions=(Predicate("reciprocal_courses", (own, tgt)),),
            guard=course_diff_recip,
        ),
        Rule(
            id="helper_own_sees_headon",
            citation="геометрия: видимость впереди",
            description="наше судно видит цель почти прямо по носу",
            tag="helper",
            premises=(
                Predicate("target", (own, tgt)),
                Predicate("rb_own_to_tgt", (own, tgt, rb)),
            ),
            conclusions=(Predicate("own_sees_headon", (own, tgt)),),
            guard=rb_near_bow,
        ),
        Rule(
            id="helper_tgt_sees_headon",
            citation="геометрия: видимость впереди",
            description="цель видит наше судно почти прямо по носу",
            tag="helper",
            premises=(
                Predicate("target", (own, tgt)),
                Predicate("rb_tgt_to_own", (own, tgt, rb_t)),
            ),
            conclusions=(Predicate("tgt_sees_headon", (own, tgt)),),
            guard=rb_near_bow_t,
        ),
        Rule(
            id="helper_both_see_headon",
            citation="геометрия: встречное сближение",
            description="оба судна видят друг друга почти прямо по носу",
            tag="helper",
            premises=(
                Predicate("own_sees_headon", (own, tgt)),
                Predicate("tgt_sees_headon", (own, tgt)),
            ),
            conclusions=(Predicate("both_see_headon", (own, tgt)),),
        ),
        Rule(
            id="helper_equal_priority",
            citation="геометрия: равенство приоритетов",
            description="оба судна имеют одинаковый приоритет по правилу 18",
            tag="helper",
            premises=(
                Predicate("target", (own, tgt)),
                Predicate("vessel_priority_rank", (own, r1)),
                Predicate("vessel_priority_rank", (tgt, r2)),
            ),
            conclusions=(Predicate("equal_priority", (own, tgt)),),
            guard=eq_rank,
        ),
        Rule(
            id="helper_lower_priority",
            citation="геометрия: разный приоритет",
            description="наше судно имеет меньший приоритет",
            tag="helper",
            premises=(
                Predicate("target", (own, tgt)),
                Predicate("vessel_priority_rank", (own, r1)),
                Predicate("vessel_priority_rank", (tgt, r2)),
            ),
            conclusions=(Predicate("lower_priority", (own, tgt)),),
            guard=lt_rank,
        ),
        Rule(
            id="helper_higher_priority",
            citation="геометрия: разный приоритет",
            description="наше судно имеет больший приоритет",
            tag="helper",
            premises=(
                Predicate("target", (own, tgt)),
                Predicate("vessel_priority_rank", (own, r1)),
                Predicate("vessel_priority_rank", (tgt, r2)),
            ),
            conclusions=(Predicate("higher_priority", (own, tgt)),),
            guard=gt_rank,
        ),
    ]
