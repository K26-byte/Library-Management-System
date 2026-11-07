"""Randomised tests: thousands of random operations, with the whole system checked
against independent oracles after every step."""
import itertools
import random
import unittest
from collections import Counter

from library import LibraryError
from library.storage import to_dict
from tests.helpers import make_library

KINDS = ["issue", "return", "renew", "reserve", "cancel", "pay", "advance", "overdue",
         "add_copies", "remove_book"]
WEIGHTS = [10, 8, 3, 5, 2, 3, 4, 3, 0.7, 0.25]


class RandomisedTests(unittest.TestCase):
    def build(self, rng, undo_limit=100):
        lib, clock = make_library(undo_limit=undo_limit)
        for i in range(5, 9):
            lib.add_book(str(i), f"Book {i}", f"Author {i % 3}", 2000 + i, rng.choice([1, 1, 2]))
        for member in ("D", "E"):
            lib.add_member(member, member)
        return lib, clock

    def make_op(self, lib, clock, rng, catalog):
        """Pick a random action. Returns (kind, callable); callable returns a note or None."""
        kinds, weights = list(KINDS), list(WEIGHTS)
        if not catalog:                          # catalog changes are deliberately not undoable
            for k in ("add_copies", "remove_book"):
                weights[kinds.index(k)] = 0
        kind = rng.choices(kinds, weights)[0]
        if not lib.books and kind != "advance":
            kind = "advance"
        isbn = rng.choice(list(lib.books) or ["-"])
        member = rng.choice(list(lib.members))
        amount = rng.choice([None, 1, 2])
        days = rng.randint(1, 9)

        def issue():
            lib.issue_book(isbn, member)

        def return_():
            fine, passed_to = lib.return_book(isbn, member)
            return "served" if passed_to else ("fine" if fine else None)

        def advance():
            clock.advance(days)

        def overdue():
            got = lib.overdue_loans()
            want = sorted((l.due, l.loan_id) for l in lib.loans.values()
                          if l.returned_on is None and l.due < clock.now)
            self.assertEqual([(l.due, l.loan_id) for l in got], want)

        def add_copies():
            return "served" if lib.add_copies(isbn, 1) else None

        table = {
            "issue": issue, "return": return_, "renew": lambda: lib.renew_loan(isbn, member),
            "reserve": lambda: lib.reserve_book(isbn, member),
            "cancel": lambda: lib.cancel_reservation(isbn, member),
            "pay": lambda: lib.pay_fines(member, amount), "advance": advance,
            "overdue": overdue, "add_copies": add_copies,
            "remove_book": lambda: lib.remove_book(isbn),
        }
        return kind, table[kind]

    def assert_consistent(self, lib, where):
        self.assertEqual(lib.verify(), [], where)
        self.assertTrue(lib.due_heap.is_valid(), where)
        expected = Counter()                    # recompute the graph from scratch
        for m in lib.members.values():
            owned = sorted(i for i in m.borrowed if i in lib.books)
            for pair in itertools.combinations(owned, 2):
                expected[pair] += 1
        actual = {(a, b): w for a, row in lib.also_borrowed.items() for b, w in row.items() if a < b}
        self.assertEqual(actual, dict(expected), where)

    def test_every_action_can_be_undone_exactly_and_failures_change_nothing(self):
        seen = Counter()
        for seed in range(30):
            rng = random.Random(seed)
            lib, clock = self.build(rng)
            for step in range(220):
                where = f"seed={seed} step={step}"
                kind, op = self.make_op(lib, clock, rng, catalog=True)
                before, depth = to_dict(lib), len(lib.undo_stack)
                try:
                    note = op()
                except LibraryError:
                    self.assertEqual(to_dict(lib), before, f"failed {kind} changed state ({where})")
                    continue
                seen[kind] += 1
                if note:
                    seen[f"{kind}:{note}"] += 1
                self.assert_consistent(lib, f"after {kind} ({where})")
                if len(lib.undo_stack) == depth + 1:           # an undoable action just happened
                    after = to_dict(lib)
                    lib.undo()
                    self.assertEqual(to_dict(lib), before, f"undo of {kind} is not exact ({where})")
                    self.assert_consistent(lib, f"after undo of {kind} ({where})")
                    op()                                        # redo: must give the same result
                    self.assertEqual(to_dict(lib), after, f"redo of {kind} differs ({where})")
        # make sure the random walk really exercised the interesting paths
        for kind in ("issue", "return", "renew", "reserve", "cancel", "pay", "overdue",
                     "add_copies", "return:served", "return:fine"):
            self.assertGreater(seen[kind], 5, f"{kind} was barely exercised: {dict(seen)}")

    def test_undoing_a_whole_session_restores_the_starting_state(self):
        for seed in range(30):
            rng = random.Random(1000 + seed)
            lib, clock = self.build(rng, undo_limit=10_000)
            start, snapshots = to_dict(lib), []
            for step in range(300):
                kind, op = self.make_op(lib, clock, rng, catalog=False)
                before, depth = to_dict(lib), len(lib.undo_stack)
                try:
                    op()
                except LibraryError:
                    continue
                if len(lib.undo_stack) == depth + 1:
                    snapshots.append(before)
            self.assertGreater(len(snapshots), 15)
            while lib.undo_stack:
                lib.undo()
                self.assertEqual(to_dict(lib), snapshots.pop())
                self.assertEqual(lib.verify(), [])
            self.assertEqual(to_dict(lib), start)


if __name__ == "__main__":
    unittest.main()
