"""Строители встроенных предикатов для гардов правил.

Гард правила получает подстановку и возвращает bool. Здесь собраны
фабрики для типовых проверок над значениями переменных, а также
комбинаторы and_/or_/not_ для построения составных условий.
"""
from __future__ import annotations

from typing import Any, Callable, Union

from .substitution import Atom, Substitution, Var, is_var

Guard = Callable[[Substitution], bool]


def _resolve(subst: Substitution, x: Atom) -> Any:
    """Подставляет значение переменной из подстановки или возвращает константу."""
    if is_var(x):
        v = subst.get(x.name)
        if v is None:
            raise ValueError(f"переменная {x.name} не связана в подстановке")
        return v
    return x


def in_range(x: Atom, lo: Union[float, Atom], hi: Union[float, Atom]) -> Guard:
    """Гард: lo <= x <= hi."""

    def check(subst: Substitution) -> bool:
        xv = _resolve(subst, x)
        lov = _resolve(subst, lo) if is_var(lo) else lo
        hiv = _resolve(subst, hi) if is_var(hi) else hi
        return lov <= xv <= hiv

    return check


def lt(a: Atom, b: Atom) -> Guard:
    def check(subst: Substitution) -> bool:
        return _resolve(subst, a) < _resolve(subst, b)

    return check


def le(a: Atom, b: Atom) -> Guard:
    def check(subst: Substitution) -> bool:
        return _resolve(subst, a) <= _resolve(subst, b)

    return check


def gt(a: Atom, b: Atom) -> Guard:
    def check(subst: Substitution) -> bool:
        return _resolve(subst, a) > _resolve(subst, b)

    return check


def ge(a: Atom, b: Atom) -> Guard:
    def check(subst: Substitution) -> bool:
        return _resolve(subst, a) >= _resolve(subst, b)

    return check


def eq(a: Atom, b: Atom) -> Guard:
    def check(subst: Substitution) -> bool:
        return _resolve(subst, a) == _resolve(subst, b)

    return check


def ne(a: Atom, b: Atom) -> Guard:
    def check(subst: Substitution) -> bool:
        return _resolve(subst, a) != _resolve(subst, b)

    return check


def truthy(x: Atom) -> Guard:
    """Гард: значение x в подстановке истинно."""

    def check(subst: Substitution) -> bool:
        return bool(_resolve(subst, x))

    return check


def and_(*guards: Guard) -> Guard:
    """Логическое И для гардов."""

    def check(subst: Substitution) -> bool:
        return all(g(subst) for g in guards)

    return check


def or_(*guards: Guard) -> Guard:
    """Логическое ИЛИ для гардов."""

    def check(subst: Substitution) -> bool:
        return any(g(subst) for g in guards)

    return check


def not_(guard: Guard) -> Guard:
    """Логическое НЕ для гарда."""

    def check(subst: Substitution) -> bool:
        return not guard(subst)

    return check


def always() -> Guard:
    def check(subst: Substitution) -> bool:
        return True

    return check
