"""Правило, шаг доказательства и движок прямой цепочки.

Rule — единица знаний в KB: посылки (Predicate с Var) + опц. гард +
заключения (Predicate с теми же Var). Движок делает прямую цепочку:
перебирает факты, подбирающиеся под посылки, и добавляет заключения в
FactBase. Каждое применение записывается как ProofStep для трассировки.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, Optional

from .builtins import Guard
from .substitution import Substitution, empty_subst
from .world import FactBase, Predicate


@dataclass(frozen=True)
class ProofStep:
    """Один шаг вывода: какое правило сработало с какой подстановкой."""

    rule_id: str
    citation: str
    description: str
    premises_resolved: tuple  # список кортежей (имя_предиката, его_ground_args)
    conclusions_resolved: tuple  # список кортежей (имя_предиката, его_ground_args)
    substitution: tuple  # frozenset пар (имя_переменной, значение) для JSON-friendly


@dataclass(frozen=True)
class Rule:
    """Продукционное правило. Все посылки и заключения — Predicate.
    Переменные (Var) должны согласованно использоваться в посылках
    и заключениях. Опциональный guard проверяет арифметические условия
    (например, in_range, gt)."""

    id: str
    citation: str
    description: str
    premises: tuple[Predicate, ...]
    conclusions: tuple[Predicate, ...]
    guard: Optional[Guard] = None
    tag: str = ""  # категория: "rule_13", "rule_18", "sound_signal" и т.д.
    precedence: int = 0  # больше = приоритетнее при конфликтах вывода


class ForwardChainer:
    """Движок прямой цепочки: запускает правила до фикс-поинта."""

    def __init__(self, rules: Iterable[Rule], max_iterations: int = 100) -> None:
        self._rules: list[Rule] = list(rules)
        self._max_iterations = max_iterations
        self.world = FactBase()
        self.proof: list[ProofStep] = []
        self.iterations = 0
        self.fired_count = 0

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)

    def reset(self) -> None:
        self.world = FactBase()
        self.proof = []
        self.iterations = 0
        self.fired_count = 0

    def assert_facts(self, facts: Iterable[Predicate]) -> int:
        return self.world.assert_all(facts)

    def run_to_fixpoint(self) -> None:
        for it in range(1, self._max_iterations + 1):
            self.iterations = it
            new_facts: list[Predicate] = []
            for rule in self._rules:
                new_facts.extend(self._fire_rule(rule))
            if not new_facts:
                return
            for f in new_facts:
                self.world.assert_(f)
        return

    def _fire_rule(self, rule: Rule) -> Iterator[Predicate]:
        """Подбирает подстановки, удовлетворяющие всем посылкам правила.
        Возвращает список новых ground-фактов-заключений."""
        yield from self._match_premises(rule, rule.premises, 0, empty_subst())

    def _match_premises(
        self,
        rule: Rule,
        premises: tuple[Predicate, ...],
        idx: int,
        subst: Substitution,
    ) -> Iterator[Predicate]:
        if idx == len(premises):
            if rule.guard is not None and not rule.guard(subst):
                return
            for conc in rule.conclusions:
                ground = conc.substitute(subst)
                if not ground.is_ground():
                    continue
                if ground not in self.world:
                    self._record_proof(rule, subst, premises, conc)
                    yield ground
            return
        premise = premises[idx]
        for fact, new_subst in self.world.query_with_subst(premise):
            composed = subst.unify_tuples(premise.args, fact.args)
            if composed is None:
                continue
            yield from self._match_premises(
                rule, premises, idx + 1, composed
            )

    def _record_proof(
        self,
        rule: Rule,
        subst: Substitution,
        premises: tuple[Predicate, ...],
        conclusion: Predicate,
    ) -> None:
        premises_resolved = tuple(
            (p.name, subst.apply_tuple(p.args)) for p in premises
        )
        conclusions_resolved = ((conclusion.name, subst.apply_tuple(conclusion.args)),)
        sub_frozen = tuple(sorted(subst.bindings.items(), key=lambda kv: kv[0]))
        step = ProofStep(
            rule_id=rule.id,
            citation=rule.citation,
            description=rule.description,
            premises_resolved=premises_resolved,
            conclusions_resolved=conclusions_resolved,
            substitution=sub_frozen,
        )
        self.proof.append(step)
        self.fired_count += 1
        # Сохраняем происхождение для разрешения конфликтов
        self.world.assert_with_provenance(
            conclusion.substitute(subst), rule.id, rule.precedence
        )

    def query(self, pattern: Predicate) -> list[Predicate]:
        return list(self.world.query(pattern))

    def query_preferred(self, pattern: Predicate) -> list[Predicate]:
        """Возвращает факты, упорядоченные по убыванию precedence правила,
        выведшего их. Первым идёт самый приоритетный факт."""
        return self.world.query_by_precedence(pattern)

    def has(self, pattern: Predicate) -> bool:
        return self.world.has(pattern)
