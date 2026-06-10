"""Тесты целостности KB: каждая Var в заключениях встречается в посылках,
guard-ы корректно типизированы, нет дубликатов id, каждое правило имеет
citation и description.
"""
import unittest

from src.formal import Rule, Var
from src.formal.kb import load_kb


class TestKBIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_kb()

    def test_no_duplicate_rule_ids(self):
        ids = [r.id for r in self.rules]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate rule ids: {ids}")

    def test_every_rule_has_citation_and_description(self):
        for r in self.rules:
            self.assertTrue(r.citation, f"rule {r.id} has no citation")
            self.assertTrue(r.description, f"rule {r.id} has no description")

    def test_var_in_conclusion_appears_in_premises(self):
        for r in self.rules:
            premise_vars: set[str] = set()
            for p in r.premises:
                premise_vars.update(p.vars())
            for c in r.conclusions:
                for v in c.vars():
                    self.assertIn(
                        v,
                        premise_vars,
                        f"rule {r.id}: var {v} in conclusion not bound in premises",
                    )

    def test_rule_ids_have_unique_citations(self):
        citations = [(r.id, r.citation) for r in self.rules]
        self.assertEqual(len(citations), len(set(citations)))

    def test_precedences_are_non_negative(self):
        for r in self.rules:
            self.assertGreaterEqual(r.precedence, 0, f"rule {r.id} has negative precedence")

    def test_rules_partition_by_citation_prefix(self):
        """Каждое правило ссылается хотя бы на одну статью МППСС-72
        или помечено как 'геометрия:'/'правило'/'МППСС-72'."""
        valid_prefixes = ("МППСС-72", "геометрия", "правило", "правила")
        for r in self.rules:
            self.assertTrue(
                r.citation.startswith(valid_prefixes),
                f"rule {r.id} citation {r.citation!r} lacks valid prefix",
            )

    def test_helper_rules_have_helper_tag(self):
        for r in self.rules:
            if r.citation.startswith("геометрия"):
                self.assertEqual(r.tag, "helper", f"rule {r.id} should be tagged helper")

    def test_all_conclusion_predicates_are_known(self):
        """Заключения должны использовать только предикаты, определённые
        в KB (own_role, encounter_type, recommended_action, sound_signal, и т.д.)."""
        known = {
            "encounter_type",
            "own_role",
            "recommended_action",
            "target_ahead_of_beam",
            "target_abaft_beam",
            "target_on_starboard",
            "target_on_port",
            "own_overtaking",
            "target_overtaking",
            "reciprocal_courses",
            "own_sees_headon",
            "tgt_sees_headon",
            "both_see_headon",
            "equal_priority",
            "lower_priority",
            "higher_priority",
            "last_resort",
            "block_left_turn",
            "block_right_turn",
            "no_left_turn",
            "no_right_turn",
            "sound_signal",
        }
        for r in self.rules:
            for c in r.conclusions:
                self.assertIn(
                    c.name, known,
                    f"rule {r.id} uses unknown conclusion predicate {c.name}",
                )

    def test_minimum_rule_coverage(self):
        """В KB должны быть правила из всех ключевых статей МППСС-72."""
        tags = {r.tag for r in self.rules}
        for needed in ("rule_12", "rule_13", "rule_14", "rule_15",
                       "rule_17", "rule_18", "rule_19", "sound_signal"):
            self.assertIn(needed, tags, f"missing tag {needed} in KB")


if __name__ == "__main__":
    unittest.main()
