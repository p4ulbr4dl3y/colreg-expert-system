"""Пакет формального движка экспертной системы.

Содержит:
- substitution: переменные, константы, унификация
- world: фактовая база с индексацией
- builtins: гарды-предикаты (in_range, gt, lt, eq)
- engine: правило, шаг доказательства, ForwardChainer
- kb: набор правил МППСС-72
"""

from .builtins import Guard, and_, eq, ge, gt, in_range, le, lt, ne, not_, or_, truthy
from .engine import ForwardChainer, ProofStep, Rule
from .substitution import Atom, Substitution, Var, empty_subst
from .world import FactBase, Predicate

__all__ = [
    "Atom",
    "FactBase",
    "ForwardChainer",
    "Guard",
    "Predicate",
    "ProofStep",
    "Rule",
    "Substitution",
    "Var",
    "and_",
    "empty_subst",
    "eq",
    "ge",
    "gt",
    "in_range",
    "le",
    "lt",
    "ne",
    "not_",
    "or_",
    "truthy",
]
