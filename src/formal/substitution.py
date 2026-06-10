"""Переменные, константы и унификация для формального движка.

Правила и факты в KB состоят из предикатов (Predicate), аргументы которых
могут быть переменными (Var) или константами (Const, int, float, str и т.д.).
Движок сопоставляет шаблоны с фактами через унификацию аргументов по позициям.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Union


@dataclass(frozen=True)
class Var:
    """Логическая переменная. Имя начинается с '?', чтобы отличаться
    от констант при чтении KB и трассировке."""

    name: str

    def __post_init__(self) -> None:
        if not self.name.startswith("?"):
            raise ValueError(f"имя переменной должно начинаться с '?': {self.name!r}")


Atom = Union[Var, str, int, float, bool, None]


def is_var(x: Any) -> bool:
    return isinstance(x, Var)


def is_ground(x: Any) -> bool:
    return not is_var(x)


@dataclass(frozen=True)
class Substitution:
    """Связывание переменных с константами. Неизменяемый: при расширении
    создаётся новая подстановка (persistence через chaining)."""

    bindings: Mapping[str, Any] = field(default_factory=dict)

    def get(self, name: str, default: Any = None) -> Any:
        return self.bindings.get(name, default)

    def bind(self, name: str, value: Any) -> "Substitution":
        if name in self.bindings:
            if self.bindings[name] == value:
                return self
            return _FAIL
        return Substitution({**self.bindings, name: value})

    def apply(self, atom: Atom) -> Atom:
        if is_var(atom):
            return self.bindings.get(atom.name, atom)
        return atom

    def apply_tuple(self, args: tuple) -> tuple:
        return tuple(self.apply(a) for a in args)

    def unify_atoms(self, a: Atom, b: Atom) -> Optional["Substitution"]:
        a = self.apply(a) if is_var(a) else a
        b = self.apply(b) if is_var(b) else b
        if is_var(a) and is_var(b):
            if a.name == b.name:
                return self
            return self.bind(a.name, b).bind(b.name, a) if False else self.bind(a.name, b)
        if is_var(a):
            return self.bind(a.name, b)
        if is_var(b):
            return self.bind(b.name, a)
        if a == b:
            return self
        return None

    def unify_tuples(
        self, xs: tuple, ys: tuple
    ) -> Optional["Substitution"]:
        if len(xs) != len(ys):
            return None
        sub: Optional[Substitution] = self
        for a, b in zip(xs, ys):
            if sub is None:
                return None
            sub = sub.unify_atoms(a, b)
        return sub


_FAIL = Substitution(frozenset())  # sentinel: не используется напрямую,
                                    # провалы возвращаются как None


def empty_subst() -> Substitution:
    return Substitution()
