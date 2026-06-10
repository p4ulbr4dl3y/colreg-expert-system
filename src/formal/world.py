"""Фактовая база с индексацией и предикаты.

Predicate — атомарный логический факт вида predicate(arg1, arg2, ...).
Аргументы могут быть константами или Var (только в шаблонах правил).
FactBase — изменяемое хранилище фактов с индексами по имени предиката
и по первому аргументу для ускорения поиска.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Optional

from .substitution import Atom, Substitution, Var, empty_subst, is_var


@dataclass(frozen=True)
class Predicate:
    """Атомарный предикат. Хешируется по (name, tuple(args))."""

    name: str
    args: tuple = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.args, tuple):
            object.__setattr__(self, "args", tuple(self.args))

    def ground(self) -> "Predicate":
        """Возвращает предикат, в котором все переменные заменены их значениями
        из переданной подстановки (если они есть)."""
        return self

    def is_ground(self) -> bool:
        return all(not is_var(a) for a in self.args)

    def substitute(self, subst: Substitution) -> "Predicate":
        return Predicate(self.name, subst.apply_tuple(self.args))

    def has_vars(self) -> bool:
        return any(is_var(a) for a in self.args)

    def vars(self) -> set[str]:
        return {a.name for a in self.args if is_var(a)}

    def matches(self, fact: "Predicate") -> Optional[Substitution]:
        """Сопоставляет шаблон (возможно с Var) с ground-фактом.
        Возвращает Substitution при успехе, иначе None."""
        if self.name != fact.name or len(self.args) != len(fact.args):
            return None
        sub: Optional[Substitution] = empty_subst()
        for a, b in zip(self.args, fact.args):
            if sub is None:
                return None
            sub = sub.unify_atoms(a, b)
        return sub


class FactBase:
    """Изменяемое хранилище ground-фактов с индексацией."""

    def __init__(self) -> None:
        self._all: set[Predicate] = set()
        self._by_name: dict[str, set[Predicate]] = defaultdict(set)
        self._by_name_arg0: dict[tuple[str, Any], set[Predicate]] = defaultdict(set)
        # Происхождение факта: pred -> (rule_id, precedence)
        self._provenance: dict[Predicate, tuple[str, int]] = {}

    def __contains__(self, pred: Predicate) -> bool:
        return pred in self._all

    def __len__(self) -> int:
        return len(self._all)

    def assert_(self, pred: Predicate) -> bool:
        """Добавляет факт. Возвращает True, если факт новый."""
        if not pred.is_ground():
            raise ValueError(f"можно ассертить только ground-предикаты: {pred}")
        if pred in self._all:
            return False
        self._all.add(pred)
        self._by_name[pred.name].add(pred)
        if pred.args:
            self._by_name_arg0[(pred.name, pred.args[0])].add(pred)
        return True

    def assert_with_provenance(
        self, pred: Predicate, rule_id: str, precedence: int
    ) -> bool:
        """Ассертит факт и запоминает происхождение. Не перезаписывает
        существующий факт, если у него выше или равный precedence."""
        if not self.assert_(pred):
            existing = self._provenance.get(pred)
            if existing and existing[1] >= precedence:
                return False
        self._provenance[pred] = (rule_id, precedence)
        return True

    def assert_all(self, preds: Iterable[Predicate]) -> int:
        n = 0
        for p in preds:
            if self.assert_(p):
                n += 1
        return n

    def retract(self, pred: Predicate) -> bool:
        if pred not in self._all:
            return False
        self._all.discard(pred)
        self._by_name[pred.name].discard(pred)
        if pred.args:
            self._by_name_arg0[(pred.name, pred.args[0])].discard(pred)
        self._provenance.pop(pred, None)
        return True

    def query(self, pattern: Predicate) -> Iterator[Predicate]:
        """Возвращает все ground-факты, сопоставимые с шаблоном."""
        candidates = list(self._by_name.get(pattern.name, ()))
        for fact in candidates:
            if pattern.matches(fact) is not None:
                yield fact

    def query_with_subst(
        self, pattern: Predicate
    ) -> Iterator[tuple[Predicate, Substitution]]:
        candidates = list(self._by_name.get(pattern.name, ()))
        for fact in candidates:
            sub = pattern.matches(fact)
            if sub is not None:
                yield fact, sub

    def has(self, pattern: Predicate) -> bool:
        return any(True for _ in self.query(pattern))

    def get_unique(self, pattern: Predicate) -> Optional[Predicate]:
        for fact in self.query(pattern):
            return fact
        return None

    def all(self, name: str) -> list[Predicate]:
        return list(self._by_name.get(name, ()))

    def by_arg0(self, name: str, arg0: Any) -> list[Predicate]:
        return list(self._by_name_arg0.get((name, arg0), ()))

    def query_by_precedence(
        self, pattern: Predicate
    ) -> list[Predicate]:
        """Возвращает факты, удовлетворяющие шаблону, упорядоченные по
        убыванию precedence их происхождения. Используется для разрешения
        конфликтов, когда несколько правил выводят разные значения
        одного предиката (например, разные encounter_type)."""
        out: list[tuple[Predicate, int]] = []
        for fact in self.query(pattern):
            prov = self._provenance.get(fact, (None, -1))
            out.append((fact, prov[1]))
        out.sort(key=lambda kv: -kv[1])
        return [f for f, _ in out]
