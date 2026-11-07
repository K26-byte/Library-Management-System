import unittest

from library import LibraryError
from tests.helpers import make_library


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.lib, self.clock = make_library()

    def test_input_validation(self):
        bad = [("1", "Dup", "X", 2000, 1),     # duplicate ISBN
               ("9", "", "X", 2000, 1),        # empty title
               ("9", "T", "X", 3000, 1),       # year in the far future
               ("9", "T", "X", 2000, 0),       # zero copies
               ("9", "T", "X", "abc", 1),      # not a number
               ("  ", "T", "X", 2000, 1)]      # empty ISBN
        for args in bad:
            with self.assertRaises(LibraryError, msg=str(args)):
                self.lib.add_book(*args)
        self.assertEqual(len(self.lib.books), 4)

    def test_isbn_and_member_id_are_normalised(self):
        self.lib.add_book("978-0-13-235088-4", "Other", "Y", 2000)
        self.assertIn("9780132350884", self.lib.books)
        self.assertEqual(self.lib.issue_book("1", " a ").member_id, "A")

    def test_prefix_multiword_search_and_sorting(self):
        isbns = lambda books: [b.isbn for b in books]
        self.assertEqual(isbns(self.lib.search("algo")), ["2", "1"])
        self.assertEqual(isbns(self.lib.search("algo", "year")), ["1", "2"])
        self.assertEqual(isbns(self.lib.search("algo", "year", reverse=True)), ["2", "1"])
        self.assertEqual(isbns(self.lib.search("robert alg")), ["2"])
        self.assertEqual(isbns(self.lib.search("CLEAN")), ["3"])
        self.assertEqual(self.lib.search("zzz"), [])
        self.assertEqual(self.lib.search(""), [])
        with self.assertRaises(LibraryError):
            self.lib.search("algo", "colour")

    def test_equal_keys_fall_back_to_title_order(self):
        self.lib.add_book("5", "Aardvark Basics", "Z", 2008)      # same year as Clean Code
        self.assertEqual([b.isbn for b in self.lib.all_books("year")], ["4", "5", "3", "1", "2"])

    def test_accented_and_indic_titles_are_searchable(self):
        self.lib.add_book("5", "Les Misérables", "Victor Hugo", 1862)
        self.lib.add_book("6", "भारत का संविधान", "भीमराव आंबेडकर", 1950)
        self.assertEqual([b.isbn for b in self.lib.search("miserables")], ["5"])
        self.assertEqual([b.isbn for b in self.lib.search("misé")], ["5"])
        self.assertEqual([b.isbn for b in self.lib.search("संवि")], ["6"])

    def test_popularity_sort_and_top_k(self):
        self.lib.issue_book("2", "A"); self.lib.issue_book("2", "B"); self.lib.issue_book("3", "C")
        self.assertEqual([b.isbn for b in self.lib.all_books("popularity", reverse=True)],
                         ["2", "3", "4", "1"])
        self.assertEqual([b.isbn for b in self.lib.most_popular(2)], ["2", "3"])
        self.assertEqual(len(self.lib.most_popular(10)), 2)     # never-borrowed books are skipped

    def test_add_copies_and_remove_book(self):
        self.lib.add_copies("3", 2)
        self.assertEqual((self.lib.books["3"].copies, self.lib.books["3"].available), (3, 3))
        with self.assertRaises(LibraryError):
            self.lib.add_copies("3", 0)
        self.lib.issue_book("3", "A")
        with self.assertRaises(LibraryError):
            self.lib.remove_book("3")                           # a copy is out
        self.lib.return_book("3", "A")
        self.lib.remove_book("3")
        self.assertEqual(self.lib.search("clean"), [])
        self.assertEqual(self.lib.verify(), [])

    def test_remove_book_reports_dropped_reservations(self):
        self.lib.issue_book("1", "A")
        self.lib.reserve_book("1", "B")
        for isbn in ("2", "3", "4"):
            self.lib.issue_book(isbn, "B")                      # B is at the loan limit, so
        self.lib.return_book("1", "A")                          # the copy comes back unclaimed
        self.assertEqual(self.lib.waitlist("1"), ["B"])
        self.assertEqual(self.lib.remove_book("1"), 1)          # one reservation cancelled
        self.assertEqual(self.lib.verify(), [])


class BorrowingTests(unittest.TestCase):
    def setUp(self):
        self.lib, self.clock = make_library()

    def test_issue_and_return(self):
        loan = self.lib.issue_book("1", "A")
        self.assertEqual((loan.due - loan.issued).days, self.lib.LOAN_DAYS)
        self.assertEqual(self.lib.books["1"].available, 0)
        with self.assertRaises(LibraryError):
            self.lib.issue_book("1", "B")                       # no copy left
        with self.assertRaises(LibraryError):
            self.lib.issue_book("1", "A")                       # A already has it
        self.assertEqual(self.lib.return_book("1", "A"), (0, None))
        with self.assertRaises(LibraryError):
            self.lib.return_book("1", "A")                      # not borrowed any more
        self.assertEqual(self.lib.books["1"].available, 1)

    def test_loan_limit(self):
        self.lib.add_book("5", "Extra", "X", 2000)
        for isbn in ("1", "2", "3"):
            self.lib.issue_book(isbn, "A")
        with self.assertRaisesRegex(LibraryError, "limit"):
            self.lib.issue_book("5", "A")

    def test_unknown_book_or_member(self):
        with self.assertRaises(LibraryError):
            self.lib.issue_book("999", "A")
        with self.assertRaises(LibraryError):
            self.lib.issue_book("1", "ZZZ")

    def test_failed_operations_do_not_change_anything(self):
        from library.storage import to_dict
        self.lib.issue_book("1", "A")
        before = to_dict(self.lib)
        for call in (lambda: self.lib.issue_book("1", "B"), lambda: self.lib.return_book("2", "A"),
                     lambda: self.lib.reserve_book("2", "B"), lambda: self.lib.renew_loan("3", "A"),
                     lambda: self.lib.pay_fines("A"), lambda: self.lib.cancel_reservation("1", "B")):
            with self.assertRaises(LibraryError):
                call()
        self.assertEqual(to_dict(self.lib), before)


class FinesAndOverdueTests(unittest.TestCase):
    def setUp(self):
        self.lib, self.clock = make_library()

    def test_overdue_list_is_ordered_and_survives_repeated_calls(self):
        self.lib.issue_book("1", "A")
        self.clock.advance(3)
        self.lib.issue_book("3", "B")
        self.assertEqual(self.lib.overdue_loans(), [])
        self.clock.advance(14)                                  # day 17: loan 1 due day 14, loan 3 due day 17
        self.assertEqual([l.isbn for l in self.lib.overdue_loans()], ["1"])
        self.clock.advance(5)                                   # day 22: both late
        for _ in range(3):                                      # heap must be restored each time
            self.assertEqual([l.isbn for l in self.lib.overdue_loans()], ["1", "3"])

    def test_late_fine_is_charged_and_blocks_borrowing_until_paid(self):
        self.lib.issue_book("1", "A")
        self.clock.advance(20)                                  # 6 days late
        with self.assertRaisesRegex(LibraryError, "overdue"):
            self.lib.issue_book("3", "A")
        fine, _ = self.lib.return_book("1", "A")
        self.assertEqual(fine, 6 * self.lib.FINE_PER_DAY)
        self.assertEqual(self.lib.members["A"].fines_owed, 12)
        with self.assertRaisesRegex(LibraryError, "fines"):
            self.lib.issue_book("3", "A")
        self.assertEqual(self.lib.pay_fines("A", 5), 5)         # partial payment
        self.assertEqual(self.lib.members["A"].fines_owed, 7)
        with self.assertRaises(LibraryError):
            self.lib.pay_fines("A", 8)                          # more than owed
        self.lib.pay_fines("A")                                 # the rest
        self.assertEqual(self.lib.issue_book("3", "A").isbn, "3")

    def test_returned_loans_leave_the_overdue_list(self):
        self.lib.issue_book("1", "A")
        self.clock.advance(20)
        self.assertEqual(len(self.lib.overdue_loans()), 1)
        self.lib.return_book("1", "A")
        self.assertEqual(self.lib.overdue_loans(), [])


class RenewalTests(unittest.TestCase):
    def setUp(self):
        self.lib, self.clock = make_library()
        self.lib.issue_book("1", "A")

    def test_renewal_moves_the_due_date_and_old_heap_entry_is_ignored(self):
        loan = self.lib.renew_loan("1", "A")
        self.assertEqual((loan.renewals, (loan.due - loan.issued).days), (1, 28))
        self.clock.advance(20)                                  # past the ORIGINAL due date only
        self.assertEqual(self.lib.overdue_loans(), [])
        self.clock.advance(10)                                  # now past the renewed date
        self.assertEqual(len(self.lib.overdue_loans()), 1)

    def test_renewal_limit(self):
        for _ in range(self.lib.MAX_RENEWALS):
            self.lib.renew_loan("1", "A")
        with self.assertRaisesRegex(LibraryError, "limit"):
            self.lib.renew_loan("1", "A")

    def test_cannot_renew_when_others_wait_or_when_overdue(self):
        self.lib.reserve_book("1", "B")
        with self.assertRaisesRegex(LibraryError, "waiting"):
            self.lib.renew_loan("1", "A")
        self.lib.cancel_reservation("1", "B")
        self.clock.advance(15)
        with self.assertRaisesRegex(LibraryError, "Overdue"):
            self.lib.renew_loan("1", "A")

    def test_undo_renewal_restores_due_date_and_overdue_tracking(self):
        self.lib.renew_loan("1", "A")
        self.lib.undo()
        self.assertEqual(self.lib.loans[1].renewals, 0)
        self.clock.advance(15)
        self.assertEqual(len(self.lib.overdue_loans()), 1)


class WaitlistTests(unittest.TestCase):
    def setUp(self):
        self.lib, self.clock = make_library()

    def test_fifo_and_automatic_hand_off(self):
        self.lib.issue_book("1", "A")
        self.assertEqual(self.lib.reserve_book("1", "B"), 1)
        self.assertEqual(self.lib.reserve_book("1", "C"), 2)
        _, passed_to = self.lib.return_book("1", "A")
        self.assertEqual(passed_to, "B")
        self.assertIn("1", self.lib.members["B"].active)
        self.assertEqual(self.lib.waitlist("1"), ["C"])
        self.assertEqual(self.lib.books["1"].available, 0)

    def test_reservation_rules(self):
        with self.assertRaisesRegex(LibraryError, "available"):
            self.lib.reserve_book("1", "A")                     # copy is free: just borrow it
        self.lib.issue_book("1", "A")
        with self.assertRaises(LibraryError):
            self.lib.reserve_book("1", "A")                     # already holds it
        self.lib.reserve_book("1", "B")
        with self.assertRaises(LibraryError):
            self.lib.reserve_book("1", "B")                     # already waiting

    def test_waiting_member_who_cannot_borrow_keeps_their_place(self):
        """(Bug in v1: such a member was silently dropped from the queue.)"""
        self.lib.issue_book("1", "A")
        self.lib.reserve_book("1", "B")
        for isbn in ("2", "3", "4"):
            self.lib.issue_book(isbn, "B")                      # B is now at the loan limit
        _, passed_to = self.lib.return_book("1", "A")
        self.assertIsNone(passed_to)
        self.assertEqual(self.lib.waitlist("1"), ["B"])         # still queued
        self.assertEqual(self.lib.books["1"].available, 1)

    def test_next_eligible_member_is_served_and_undo_restores_exact_order(self):
        self.lib.issue_book("1", "A")
        self.lib.reserve_book("1", "B")
        self.lib.reserve_book("1", "C")
        for isbn in ("2", "3", "4"):
            self.lib.issue_book(isbn, "B")                      # B cannot borrow
        _, passed_to = self.lib.return_book("1", "A")
        self.assertEqual(passed_to, "C")                        # C skips ahead of blocked B
        self.assertEqual(self.lib.waitlist("1"), ["B"])
        self.lib.undo()
        self.assertEqual(self.lib.waitlist("1"), ["B", "C"])    # C is back BEHIND B
        self.assertEqual(self.lib.books["1"].available, 0)

    def test_borrowing_directly_removes_you_from_the_queue(self):
        self.lib.issue_book("1", "A")
        self.lib.reserve_book("1", "B")
        for isbn in ("2", "3", "4"):
            self.lib.issue_book(isbn, "B")
        self.lib.return_book("1", "A")                          # copy free, B still queued
        self.lib.return_book("4", "B")                          # B can borrow again
        self.lib.issue_book("1", "B")
        self.assertEqual(self.lib.waitlist("1"), [])
        self.lib.undo()
        self.assertEqual(self.lib.waitlist("1"), ["B"])

    def test_cancel_reservation_and_undo(self):
        self.lib.issue_book("1", "A")
        for member in ("B", "C"):
            self.lib.reserve_book("1", member)
        self.lib.cancel_reservation("1", "B")
        self.assertEqual(self.lib.waitlist("1"), ["C"])
        self.lib.undo()
        self.assertEqual(self.lib.waitlist("1"), ["B", "C"])

    def test_adding_copies_serves_waiting_members(self):
        self.lib.issue_book("1", "A")
        self.lib.reserve_book("1", "B")
        served = self.lib.add_copies("1", 2)
        self.assertEqual([l.member_id for l in served], ["B"])
        self.assertEqual(self.lib.books["1"].available, 1)
        self.assertEqual(self.lib.verify(), [])


class UndoTests(unittest.TestCase):
    def setUp(self):
        self.lib, self.clock = make_library()

    def test_undo_issue_and_return(self):
        self.lib.issue_book("1", "A")
        self.assertIn("issue", self.lib.next_undo())
        self.lib.undo()
        self.assertEqual(self.lib.books["1"].available, 1)
        self.assertEqual(self.lib.books["1"].times_borrowed, 0)
        self.lib.issue_book("1", "A")
        self.lib.return_book("1", "A")
        self.lib.undo()
        self.assertEqual(self.lib.books["1"].available, 0)
        self.assertIn("1", self.lib.members["A"].active)

    def test_undo_return_that_triggered_a_hand_off(self):
        self.lib.issue_book("1", "A")
        self.lib.reserve_book("1", "B")
        self.lib.return_book("1", "A")
        self.lib.undo()
        self.assertNotIn("1", self.lib.members["B"].active)
        self.assertEqual(self.lib.waitlist("1"), ["B"])
        self.assertIn("1", self.lib.members["A"].active)

    def test_undo_late_return_removes_the_fine_and_payment_undo_restores_it(self):
        self.lib.issue_book("1", "A")
        self.clock.advance(20)
        self.lib.return_book("1", "A")
        self.lib.pay_fines("A")
        self.assertEqual(self.lib.members["A"].fines_owed, 0)
        self.lib.undo()                                         # un-pay
        self.assertEqual(self.lib.members["A"].fines_owed, 12)
        self.lib.undo()                                         # un-return
        self.assertEqual(self.lib.members["A"].fines_owed, 0)

    def test_nothing_to_undo(self):
        with self.assertRaises(LibraryError):
            self.lib.undo()

    def test_undo_after_removing_the_book_does_not_crash(self):
        """(Bug in v1: this raised KeyError.)"""
        self.lib.issue_book("1", "A")
        self.lib.return_book("1", "A")
        self.lib.remove_book("1")
        with self.assertRaisesRegex(LibraryError, "Nothing to undo"):
            self.lib.undo()
        self.assertEqual(self.lib.verify(), [])

    def test_remove_book_only_discards_that_titles_undo_history(self):
        self.lib.issue_book("2", "A")
        self.lib.issue_book("1", "A"); self.lib.return_book("1", "A")
        self.lib.remove_book("1")
        self.assertIn("issue of 'Algorithms'", self.lib.next_undo())

    def test_undo_history_is_bounded(self):
        lib, _ = make_library(undo_limit=3)
        for _ in range(5):
            lib.issue_book("2", "A"); lib.return_book("2", "A")
        self.assertEqual(len(lib.undo_stack), 3)


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.lib, self.clock = make_library()
        self.lib.add_copies("1", 1)
        self.lib.add_copies("3", 1)

    def test_weight_counts_distinct_members(self):
        for member in ("A", "B"):
            self.lib.issue_book("1", member)
            self.lib.issue_book("3", member)
        recs = self.lib.recommend("1")
        self.assertEqual([(b.isbn, w) for b, w in recs], [("3", 2)])

    def test_reborrowing_does_not_inflate_the_weight(self):
        """(Bug in v1: one member re-borrowing doubled the weight.)"""
        self.lib.issue_book("1", "A"); self.lib.issue_book("3", "A")
        self.lib.return_book("1", "A"); self.lib.return_book("3", "A")
        self.lib.issue_book("3", "A")
        self.assertEqual([(b.isbn, w) for b, w in self.lib.recommend("1")], [("3", 1)])

    def test_undo_removes_the_edge(self):
        self.lib.issue_book("1", "A"); self.lib.issue_book("3", "A")
        self.lib.undo()
        self.assertEqual(self.lib.recommend("1"), [])

    def test_removed_books_vanish_from_recommendations(self):
        self.lib.issue_book("1", "A"); self.lib.issue_book("3", "A")
        self.lib.return_book("3", "A")
        self.lib.remove_book("3")
        self.assertEqual(self.lib.recommend("1"), [])
        self.assertEqual(self.lib.verify(), [])


class ReportTests(unittest.TestCase):
    def test_member_report_and_stats(self):
        lib, clock = make_library()
        lib.issue_book("1", "A")
        lib.reserve_book("1", "B")
        report = lib.member_report("B")
        self.assertEqual([(b.isbn, pos) for b, pos in report["waiting"]], [("1", 1)])
        self.assertEqual([b.isbn for b, _ in lib.member_report("A")["current"]], ["1"])
        clock.advance(20)
        stats = lib.stats()
        self.assertEqual((stats["titles"], stats["copies"], stats["on_loan"]), (4, 5, 1))
        self.assertEqual((stats["overdue"], stats["waiting"]), (1, 1))


class VerifyTests(unittest.TestCase):
    def test_verify_detects_corruption(self):
        lib, _ = make_library()
        lib.issue_book("1", "A")
        self.assertEqual(lib.verify(), [])
        lib.books["1"].available = 1                            # lie about the stock
        self.assertTrue(any("copies out" in p for p in lib.verify()))
        lib.books["1"].available = 0
        lib.due_heap = type(lib.due_heap)()                     # lose the heap
        self.assertTrue(any("heap" in p for p in lib.verify()))


if __name__ == "__main__":
    unittest.main()
