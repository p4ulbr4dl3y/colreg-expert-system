"""Юнит-тесты формального движка: унификация, фактовая база, прямая цепочка."""
import unittest

from src.formal import (
    FactBase,
    ForwardChainer,
    Predicate,
    Rule,
    Substitution,
    Var,
    eq,
    in_range,
)


class TestUnification(unittest.TestCase):
    def test_unify_two_vars(self):
        sub = Substitution().unify_atoms(Var("?x"), Var("?y"))
        self.assertIsNotNone(sub)
        self.assertEqual(sub.apply(Var("?x")), Var("?y"))

    def test_unify_var_with_const(self):
        sub = Substitution().unify_atoms(Var("?x"), "hello")
        self.assertEqual(sub.apply(Var("?x")), "hello")

    def test_unify_two_consts_equal(self):
        sub = Substitution().unify_atoms("a", "a")
        self.assertIsNotNone(sub)
        self.assertEqual(sub.bindings, {})

    def test_unify_two_consts_different(self):
        sub = Substitution().unify_atoms("a", "b")
        self.assertIsNone(sub)

    def test_unify_bound_var(self):
        sub = Substitution({"?x": "hello"}).unify_atoms(Var("?x"), Var("?y"))
        self.assertEqual(sub.bindings, {"?x": "hello", "?y": "hello"})

    def test_unify_consistent(self):
        sub = Substitution({"?x": "hello"}).unify_atoms(Var("?x"), "hello")
        self.assertIsNotNone(sub)

    def test_unify_conflict(self):
        sub = Substitution({"?x": "hello"}).unify_atoms(Var("?x"), "world")
        self.assertIsNone(sub)


class TestFactBase(unittest.TestCase):
    def test_assert_and_query(self):
        fb = FactBase()
        fb.assert_(Predicate("vessel", ("OwnShip",)))
        fb.assert_(Predicate("target", ("OwnShip", "T1")))
        self.assertEqual(len(fb), 2)
        self.assertIn(Predicate("vessel", ("OwnShip",)), fb)

    def test_query_with_var(self):
        fb = FactBase()
        fb.assert_(Predicate("vessel", ("A",)))
        fb.assert_(Predicate("vessel", ("B",)))
        results = list(fb.query(Predicate("vessel", (Var("?x"),))))
        self.assertEqual(len(results), 2)

    def test_query_with_subst(self):
        fb = FactBase()
        fb.assert_(Predicate("risk", ("OwnShip", "T1")))
        fb.assert_(Predicate("risk", ("OwnShip", "T2")))
        subs = []
        for fact, sub in fb.query_with_subst(Predicate("risk", ("OwnShip", Var("?t")))):
            subs.append(sub.apply(Var("?t")))
        self.assertEqual(set(subs), {"T1", "T2"})

    def test_indexing_by_arg0(self):
        fb = FactBase()
        fb.assert_(Predicate("role", ("OwnShip", "T1", "GIVE_WAY")))
        fb.assert_(Predicate("role", ("OwnShip", "T2", "STAND_ON")))
        self.assertEqual(len(fb.by_arg0("role", "OwnShip")), 2)
        self.assertEqual(len(fb.by_arg0("role", "T1")), 0)

    def test_assert_duplicate_ignored(self):
        fb = FactBase()
        self.assertTrue(fb.assert_(Predicate("a", ("x",))))
        self.assertFalse(fb.assert_(Predicate("a", ("x",))))
        self.assertEqual(len(fb), 1)


class TestForwardChainer(unittest.TestCase):
    def test_simple_rule_fires(self):
        fb_init = [
            Predicate("vessel", ("Own",)),
            Predicate("target", ("Own", "T1")),
        ]
        rule = Rule(
            id="test_rule",
            citation="test",
            description="own is a target of itself",
            premises=(Predicate("target", (Var("?own"), Var("?tgt"))),),
            conclusions=(Predicate("conclusion", (Var("?own"), Var("?tgt"))),),
        )
        engine = ForwardChainer([rule])
        engine.assert_facts(fb_init)
        engine.run_to_fixpoint()
        self.assertTrue(
            engine.has(Predicate("conclusion", ("Own", "T1")))
        )
        self.assertEqual(len(engine.proof), 1)

    def test_rule_with_guard(self):
        rule = Rule(
            id="test_range",
            citation="test",
            description="",
            premises=(Predicate("value", (Var("?x"),)),),
            conclusions=(Predicate("in_range", (Var("?x"),)),),
            guard=in_range(Var("?x"), 0, 10),
        )
        engine = ForwardChainer([rule])
        engine.assert_facts([
            Predicate("value", (5,)),
            Predicate("value", (15,)),
        ])
        engine.run_to_fixpoint()
        self.assertTrue(engine.has(Predicate("in_range", (5,))))
        self.assertFalse(engine.has(Predicate("in_range", (15,))))

    def test_rule_with_multiple_premises(self):
        rule = Rule(
            id="combine",
            citation="test",
            description="",
            premises=(
                Predicate("vessel", (Var("?own"),)),
                Predicate("target", (Var("?own"), Var("?tgt"))),
            ),
            conclusions=(Predicate("paired", (Var("?own"), Var("?tgt"))),),
        )
        engine = ForwardChainer([rule])
        engine.assert_facts([
            Predicate("vessel", ("Own",)),
            Predicate("target", ("Own", "T1")),
            Predicate("target", ("Own", "T2")),
        ])
        engine.run_to_fixpoint()
        self.assertTrue(engine.has(Predicate("paired", ("Own", "T1"))))
        self.assertTrue(engine.has(Predicate("paired", ("Own", "T2"))))

    def test_fixpoint_no_extra_iterations(self):
        rule = Rule(
            id="r",
            citation="",
            description="",
            premises=(Predicate("a", (Var("?x"),)),),
            conclusions=(Predicate("b", (Var("?x"),)),),
        )
        engine = ForwardChainer([rule])
        engine.assert_facts([Predicate("a", (1,))])
        engine.run_to_fixpoint()
        # b is derived, no further rules derive from b -> stops after 1 iter
        self.assertTrue(engine.has(Predicate("b", (1,))))
        self.assertEqual(len(engine.proof), 1)

    def test_chained_rules(self):
        r1 = Rule(
            id="r1",
            citation="",
            description="",
            premises=(Predicate("a", (Var("?x"),)),),
            conclusions=(Predicate("b", (Var("?x"),)),),
        )
        r2 = Rule(
            id="r2",
            citation="",
            description="",
            premises=(Predicate("b", (Var("?x"),)),),
            conclusions=(Predicate("c", (Var("?x"),)),),
        )
        engine = ForwardChainer([r1, r2])
        engine.assert_facts([Predicate("a", (1,))])
        engine.run_to_fixpoint()
        self.assertTrue(engine.has(Predicate("b", (1,))))
        self.assertTrue(engine.has(Predicate("c", (1,))))
        self.assertEqual(len(engine.proof), 2)


if __name__ == "__main__":
    unittest.main()
