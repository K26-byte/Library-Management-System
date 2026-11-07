#!/usr/bin/env python3
"""Interactive command-line interface for the Library Management System.

    python main.py                       data is kept in library_data.json
    python main.py --data other.json     use a different data file
    python main.py --demo                start a NEW library with sample books/members
    python main.py --today 2026-12-01    pretend it is another date (to see overdue loans and fines)
"""
import argparse
import os
import sys
from datetime import date

from library import Library, LibraryError, load_library, save_library
from library.sample_data import seed

DEFAULT_DATA_FILE = "library_data.json"


# ------------------------------------------------------------------ input / output
def ask(prompt):
    return input(f"  {prompt}: ").strip()


def ask_int(prompt, default=None, blank_ok=False):
    hint = f" [{default}]" if default is not None else ""
    raw = ask(prompt + hint)
    if raw == "" and (default is not None or blank_ok):
        return default
    try:
        return int(raw)
    except ValueError:
        raise LibraryError("Please enter a whole number")


def confirm(prompt):
    return ask(prompt + " (y/n)").lower() in ("y", "yes")


def ask_sort():
    return (ask("Sort by title / author / year / popularity [title]") or "title").lower()


def clip(text, width):
    return text if len(text) <= width else text[: width - 3] + "..."


def table(headers, rows, max_width=36):
    if not rows:
        print("  (nothing to show)")
        return
    cells = [[clip(str(c), max_width) for c in row] for row in rows]
    widths = [max(len(h), *(len(r[i]) for r in cells)) for i, h in enumerate(headers)]
    print(("  " + "  ".join(h.ljust(w) for h, w in zip(headers, widths))).rstrip())
    print("  " + "  ".join("-" * w for w in widths))
    for row in cells:
        print(("  " + "  ".join(c.ljust(w) for c, w in zip(row, widths))).rstrip())


BOOK_HEADERS = ("ISBN", "Title", "Author", "Year", "Avail", "Borrowed")


def book_rows(books):
    return [(b.isbn, b.title, b.author, b.year, f"{b.available}/{b.copies}", b.times_borrowed)
            for b in books]


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


# ----------------------------------------------------------------------- commands
def cmd_add_book(lib):
    book = lib.add_book(ask("ISBN"), ask("Title"), ask("Author"),
                        ask_int("Year"), ask_int("Copies", 1))
    print(f"  Added '{book.title}' ({book.copies} {'copy' if book.copies == 1 else 'copies'}).")


def cmd_add_copies(lib):
    isbn, n = ask("ISBN"), ask_int("Copies to add", 1)
    served = lib.add_copies(isbn, n)
    print(f"  Added {n}.")
    for loan in served:
        print(f"  Waitlist: a copy went straight to {lib.members[loan.member_id].name} "
              f"(due {loan.due}).")


def cmd_remove_book(lib):
    isbn = ask("ISBN")
    book = lib.get_book(isbn)
    if not confirm(f"Remove '{book.title}' permanently?"):
        print("  Cancelled.")
        return
    cancelled = lib.remove_book(isbn)
    print("  Book removed." + (f" {plural(cancelled, 'reservation')} cancelled." if cancelled else ""))


def cmd_search(lib):
    query = ask("Search (words from the title or author; prefixes work)")
    if not query:
        raise LibraryError("Type at least one word to search for")
    sort = ask_sort()
    table(BOOK_HEADERS, book_rows(lib.search(query, sort, reverse=(sort == "popularity"))))


def cmd_list(lib):
    sort = ask_sort()
    table(BOOK_HEADERS, book_rows(lib.all_books(sort, reverse=(sort == "popularity"))))


def cmd_issue(lib):
    loan = lib.issue_book(ask("ISBN"), ask("Member ID"))
    print(f"  Issued '{lib.books[loan.isbn].title}' to {lib.members[loan.member_id].name}. "
          f"Due {loan.due}.")


def cmd_return(lib):
    fine, passed_to = lib.return_book(ask("ISBN"), ask("Member ID"))
    print("  Returned." + (f" Late fine of Rs {fine} added to the member's account." if fine else ""))
    if passed_to:
        print(f"  Waitlist: the copy went straight to {lib.members[passed_to].name}.")


def cmd_renew(lib):
    loan = lib.renew_loan(ask("ISBN"), ask("Member ID"))
    print(f"  Renewed ({loan.renewals}/{lib.MAX_RENEWALS}). New due date {loan.due}.")


def cmd_reserve(lib):
    pos = lib.reserve_book(ask("ISBN"), ask("Member ID"))
    print(f"  Added to the waitlist at position {pos}.")


def cmd_cancel(lib):
    lib.cancel_reservation(ask("ISBN"), ask("Member ID"))
    print("  Reservation cancelled.")


def cmd_add_member(lib):
    member = lib.add_member(ask("Member ID"), ask("Name"))
    print(f"  Added member {member.name} ({member.member_id}).")


def cmd_member_report(lib):
    r = lib.member_report(ask("Member ID"))
    m = r["member"]
    print(f"  {m.name} ({m.member_id})   fines owed: Rs {m.fines_owed}   "
          f"books borrowed in total: {r['total_borrowed']}")
    print("  Currently borrowing:")
    rows = []
    for book, loan in r["current"]:
        late = lib.days_overdue(loan)
        status = f"{late} days late" if late else "on time"
        rows.append((book.isbn, book.title, loan.due, f"{loan.renewals}/{lib.MAX_RENEWALS}", status))
    table(("ISBN", "Title", "Due", "Renewals", "Status"), rows)
    if r["waiting"]:
        print("  On waitlists:")
        table(("ISBN", "Title", "Position"), [(b.isbn, b.title, p) for b, p in r["waiting"]])


def cmd_pay(lib):
    member = lib.get_member(ask("Member ID"))
    if member.fines_owed <= 0:
        raise LibraryError(f"{member.name} has no fines to pay")
    amount = ask_int(f"Amount in Rs (owed: {member.fines_owed}) [all]", blank_ok=True)
    print(f"  Received Rs {lib.pay_fines(member.member_id, amount)}.")


def cmd_overdue(lib):
    rows = [(l.isbn, lib.books[l.isbn].title, f"{lib.members[l.member_id].name} ({l.member_id})",
             l.due, lib.days_overdue(l), f"Rs {lib.projected_fine(l)}")
            for l in lib.overdue_loans()]
    table(("ISBN", "Title", "Member", "Due", "Days late", "Fine so far"), rows)


def cmd_popular(lib):
    table(BOOK_HEADERS, book_rows(lib.most_popular(5)))


def cmd_recommend(lib):
    recs = lib.recommend(ask("ISBN"))
    if not recs:
        print("  Not enough borrowing data yet.")
    for book, weight in recs:
        print(f"  {book.title}  (borrowed by {plural(weight, 'member')} who also borrowed this)")


def cmd_dashboard(lib):
    s = lib.stats()
    print(f"  Date: {lib.today()}")
    print(f"  Titles: {s['titles']}    Copies: {s['copies']} ({s['on_loan']} on loan)    "
          f"Members: {s['members']}")
    print(f"  Overdue loans: {s['overdue']}    Waiting in queues: {s['waiting']}    "
          f"Fines owed: Rs {s['fines_owed']}")


def cmd_undo(lib):
    pending = lib.next_undo()
    if pending is None:
        raise LibraryError("Nothing to undo")
    if confirm(f"Undo {pending}?"):
        print(f"  {lib.undo()}.")
    else:
        print("  Cancelled.")


# key -> (label, handler, changes data?)
COMMANDS = {
    "1": ("Add book", cmd_add_book, True),
    "2": ("Add copies", cmd_add_copies, True),
    "3": ("Remove book", cmd_remove_book, True),
    "4": ("Search", cmd_search, False),
    "5": ("List all books", cmd_list, False),
    "6": ("Issue book", cmd_issue, True),
    "7": ("Return book", cmd_return, True),
    "8": ("Renew loan", cmd_renew, True),
    "9": ("Reserve (join waitlist)", cmd_reserve, True),
    "10": ("Cancel reservation", cmd_cancel, True),
    "11": ("Add member", cmd_add_member, True),
    "12": ("Member report", cmd_member_report, False),
    "13": ("Pay fines", cmd_pay, True),
    "14": ("Overdue loans", cmd_overdue, False),
    "15": ("Most popular books", cmd_popular, False),
    "16": ("Recommendations", cmd_recommend, False),
    "17": ("Dashboard", cmd_dashboard, False),
    "18": ("Undo last action", cmd_undo, True),
}
MENU_GROUPS = [
    ("CATALOG", ["1", "2", "3", "4", "5"]),
    ("LOANS", ["6", "7", "8", "9", "10"]),
    ("MEMBERS", ["11", "12", "13"]),
    ("REPORTS", ["14", "15", "16", "17"]),
    ("OTHER", ["18", "0"]),
]


def print_menu():
    labels = {key: entry[0] for key, entry in COMMANDS.items()}
    labels["0"] = "Exit"
    print("\n===== LIBRARY MANAGEMENT SYSTEM =====")
    for group, keys in MENU_GROUPS:
        print(f"  {group}")
        for i in range(0, len(keys), 2):
            print("    " + "".join(f"{k:>2}. {labels[k]}".ljust(34) for k in keys[i:i + 2]).rstrip())


# --------------------------------------------------------------------------- main
def parse_args(argv):
    p = argparse.ArgumentParser(description="Library Management System")
    p.add_argument("--data", default=DEFAULT_DATA_FILE, help="data file (default: %(default)s)")
    p.add_argument("--today", type=date.fromisoformat, metavar="YYYY-MM-DD",
                   help="pretend today is this date")
    p.add_argument("--demo", action="store_true", help="load sample data when starting a new library")
    return p.parse_args(argv)


def open_library(args):
    today = (lambda: args.today) if args.today else date.today
    if os.path.exists(args.data):
        lib = load_library(args.data, today)
        print(f"Loaded {args.data}: {len(lib.books)} titles, {len(lib.members)} members.")
        return lib
    lib = Library(today=today)
    if args.demo or confirm_startup():
        seed(lib)
        print("Loaded sample data: 10 titles and members M1-M4 (Asha, Ravi, Meera, Kiran).")
    save_library(lib, args.data)
    print(f"Created {args.data}. Changes are saved automatically.")
    return lib


def confirm_startup():
    return input("No data file yet. Load sample data? (y/n): ").strip().lower() in ("y", "yes")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):          # never crash on unusual characters
        sys.stdout.reconfigure(errors="replace")
    args = parse_args(argv)
    try:                                            # Ctrl-D / Ctrl-C at ANY prompt ends cleanly
        try:
            lib = open_library(args)
        except (LibraryError, OSError) as exc:
            print(f"Could not open {args.data}: {exc}\nFix or move the file and try again.")
            return 1
        if args.today:
            print(f"(Simulated date: {args.today})")
        while True:
            print_menu()
            choice = input("\nChoose: ").strip()
            if choice == "0":
                break
            if choice not in COMMANDS:
                print("  Invalid choice.")
                continue
            _, handler, changes_data = COMMANDS[choice]
            try:
                handler(lib)
                if changes_data:
                    save_library(lib, args.data)
            except LibraryError as exc:
                print(f"  ! {exc}")
            except OSError as exc:
                print(f"  ! Could not save {args.data}: {exc}")
    except (EOFError, KeyboardInterrupt):
        print()
    print("Goodbye!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
