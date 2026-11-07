#!/usr/bin/env python3
"""A narrated walkthrough of every feature. Run:  python demo.py

Time is simulated with a controllable clock, so "20 days later" happens instantly.
"""
import os
import tempfile
from datetime import date, timedelta

from library import Library, LibraryError, load_library, save_library
from library.sample_data import seed

CLRS, ALGO, CLEAN, PATTERNS, KR, SICP, JAVA, JS, PRAG, FLUENT = (
    "9780262033848", "9780321573513", "9780132350884", "9780201633610", "9780131103627",
    "9780262510875", "9780134685991", "9780596517748", "9780201616224", "9781492056355")


class Clock:
    def __init__(self):
        self.now = date(2026, 3, 2)

    def __call__(self):
        return self.now

    def advance(self, days):
        self.now += timedelta(days=days)


def heading(text):
    print(f"\n=== {text} ===")


def say(text):
    print(f"  {text}")


def attempt(description, action):
    """Run an action; show the outcome, or the rule that refused it."""
    try:
        result = action()
        say(description)
        return result
    except LibraryError as exc:
        say(f"{description}  -> REFUSED: {exc}")


def titles(books):
    return "; ".join(b.title for b in books) or "(none)"


def main():
    clock = Clock()
    lib = Library(today=clock)
    seed(lib)
    name = lambda member_id: lib.members[member_id].name
    say(f"Library opened on {clock.now} with {len(lib.books)} titles and {len(lib.members)} members.")

    heading("1. Searching: Trie for prefixes, merge sort for ordering")
    say(f"'algo'          -> {titles(lib.search('algo'))}")
    say(f"'robert'        -> {titles(lib.search('robert'))}      (matches authors too)")
    say(f"'robert alg'    -> {titles(lib.search('robert alg'))}      (every word must match)")
    say(f"oldest first    -> {titles(lib.all_books('year')[:4])} ...")

    heading("2. Loans, waitlist queue and the automatic hand-off")
    attempt("Asha borrows 'Algorithms' (only 1 copy)", lambda: lib.issue_book(ALGO, "M1"))
    attempt("Ravi tries to borrow it too", lambda: lib.issue_book(ALGO, "M2"))
    say(f"Ravi joins the waitlist at position {lib.reserve_book(ALGO, 'M2')}, Meera at position "
        f"{lib.reserve_book(ALGO, 'M3')}")
    _, passed_to = lib.return_book(ALGO, "M1")
    say(f"Asha returns it -> the copy goes straight to {name(passed_to)}; "
        f"waitlist is now {[name(m) for m in lib.waitlist(ALGO)]}")
    for isbn in (CLRS, CLEAN, PATTERNS):
        lib.issue_book(isbn, "M1")
    say("Asha borrows 3 more books (due in 14 days)")
    attempt("Asha tries a 4th book", lambda: lib.issue_book(KR, "M1"))
    lib.issue_book(KR, "M3")
    say("Meera borrows 'The C Programming Language' instead")

    heading("3. Renewals (the heap quietly discards the old due date)")
    clock.advance(10)
    attempt("Day 10: Ravi tries to renew 'Algorithms' while Meera waits", lambda: lib.renew_loan(ALGO, "M2"))
    lib.cancel_reservation(ALGO, "M3")
    say("Meera cancels her reservation")
    loan = attempt("Ravi renews 'Algorithms'", lambda: lib.renew_loan(ALGO, "M2"))
    say(f"New due date: {loan.due}")

    heading("4. Overdue tracking and fines")
    clock.advance(10)
    say(f"Day 20. Overdue loans (min-heap, most overdue first):")
    for l in lib.overdue_loans():
        say(f"  {lib.books[l.isbn].title:<28} {name(l.member_id):<6} due {l.due}, "
            f"{lib.days_overdue(l)} days late (Rs {lib.projected_fine(l)} so far)")
    say("(Ravi's renewed loan is not listed: it is not late yet.)")
    attempt("Asha tries to borrow while holding late books", lambda: lib.issue_book(SICP, "M1"))
    total = sum(lib.return_book(isbn, "M1")[0] for isbn in (CLRS, CLEAN, PATTERNS))
    say(f"Asha returns all three: fines of Rs {total} added to her account")
    attempt("Asha tries to borrow with unpaid fines", lambda: lib.issue_book(SICP, "M1"))
    say(f"Asha pays Rs {lib.pay_fines('M1')}")
    attempt("Asha borrows 'SICP'", lambda: lib.issue_book(SICP, "M1"))

    heading("5. Undo (every action records how to reverse itself)")
    attempt("Kiran borrows 'JavaScript: The Good Parts'", lambda: lib.issue_book(JS, "M4"))
    say(f"Last action on the stack: {lib.next_undo()}")
    say(lib.undo() + f"  (copies available again: {lib.books[JS].available})")
    say(lib.undo() + "  (Asha's SICP loan)")

    heading("6. Recommendations (graph) and popularity (top-k heap)")
    for isbn in (CLRS, CLEAN, PATTERNS):
        lib.issue_book(isbn, "M4")
    say("Kiran borrows the same three books Asha did")
    for book, weight in lib.recommend(CLRS):
        say(f"Readers of 'Introduction to Algorithms' also borrowed '{book.title}' "
            f"({weight} {'member' if weight == 1 else 'members'})")
    say("Most borrowed: " + "; ".join(f"{b.title} ({b.times_borrowed}x)" for b in lib.most_popular(3)))

    heading("7. Saving to disk and loading it back")
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "library.json")
        save_library(lib, path)
        again = load_library(path, clock)
        say(f"Saved {os.path.getsize(path):,} bytes of JSON; the search tries and heap are rebuilt on load.")
        say(f"After loading: search 'clean' -> {titles(again.search('clean'))}; "
            f"overdue loans -> {len(again.overdue_loans())}; "
            f"waiting -> {again.stats()['waiting']}")
    say(f"Self-check of all structures: {'consistent' if not lib.verify() else lib.verify()}")


if __name__ == "__main__":
    main()
