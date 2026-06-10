"""Агрегатор KB: объединяет все правила МППСС-72 в один список."""
from __future__ import annotations

from ..engine import Rule
from .helpers import helpers
from .rule_12 import rules as rule_12
from .rule_13 import rules as rule_13
from .rule_17 import rules as rule_17
from .rule_18 import rules as rule_18
from .rule_19 import rules as rule_19
from .rules_14_15 import rules as rules_14_15
from .rules_34_35 import rules as rules_34_35
from .heading_blocks import rules as heading_blocks


def load_kb() -> list[Rule]:
    """Возвращает полный список правил МППСС-72 в порядке приоритета."""
    return (
        helpers()
        + rule_13()
        + rules_14_15()
        + rule_18()
        + rule_12()
        + rule_19()
        + rule_17()
        + heading_blocks()
        + rules_34_35()
    )


__all__ = ["load_kb"]
