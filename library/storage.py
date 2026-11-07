"""Save / load the whole library as JSON.

Only the raw facts are stored (books, members, loans, queues, graph). The search
tries and the due-date heap are rebuilt on load, and `verify()` checks the result.
The undo stack is deliberately not saved: undo is for the current session.
"""
import json
import os
import tempfile
from dataclasses import asdict
from datetime import date

from .models import Book, Loan, Member
from .system import Library, LibraryError

FORMAT_VERSION = 1


def to_dict(lib):
    return {
        "version": FORMAT_VERSION,
        "next_loan": lib._next_loan,
        "books": [asdict(b) for b in lib.books.values()],
        "members": [
            {"member_id": m.member_id, "name": m.name, "active": dict(m.active),
             "history": list(m.history), "borrowed": sorted(m.borrowed),
             "fines_owed": m.fines_owed}
            for m in lib.members.values()
        ],
        "loans": [
            {"loan_id": l.loan_id, "isbn": l.isbn, "member_id": l.member_id,
             "issued": l.issued.isoformat(), "due": l.due.isoformat(),
             "returned_on": l.returned_on.isoformat() if l.returned_on else None,
             "renewals": l.renewals, "fine": l.fine}
            for l in lib.loans.values()
        ],
        "waitlists": {isbn: list(q) for isbn, q in lib.waitlists.items() if len(q)},
        "also_borrowed": {x: dict(row) for x, row in lib.also_borrowed.items()},
    }


def from_dict(data, today=date.today):
    try:
        if data.get("version") != FORMAT_VERSION:
            raise LibraryError(f"Unsupported data file version: {data.get('version')!r}")
        lib = Library(today=today)
        for b in data["books"]:
            book = Book(**b)
            lib.books[book.isbn] = book
            lib._index_book(book)
        for m in data["members"]:
            lib.members[m["member_id"]] = Member(
                m["member_id"], m["name"], {k: int(v) for k, v in m["active"].items()},
                [int(i) for i in m["history"]], set(m["borrowed"]), int(m["fines_owed"]))
        for l in data["loans"]:
            returned = date.fromisoformat(l["returned_on"]) if l["returned_on"] else None
            loan = Loan(int(l["loan_id"]), l["isbn"], l["member_id"],
                        date.fromisoformat(l["issued"]), date.fromisoformat(l["due"]),
                        returned, int(l["renewals"]), int(l["fine"]))
            lib.loans[loan.loan_id] = loan
            if returned is None:
                lib.due_heap.push((loan.due, loan.loan_id))
        for isbn, member_ids in data["waitlists"].items():
            queue = lib._queue(isbn)
            for member_id in member_ids:
                queue.enqueue(member_id)
        lib.also_borrowed = {x: {y: int(w) for y, w in row.items()}
                             for x, row in data["also_borrowed"].items()}
        lib._next_loan = int(data["next_loan"])
    except LibraryError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise LibraryError(f"Data file is damaged or incomplete ({type(exc).__name__}: {exc})")
    problems = lib.verify()
    if problems:
        raise LibraryError("Data file is inconsistent: " + "; ".join(problems[:3]))
    return lib


def save_library(lib, path):
    """Atomic write: write a temp file, flush to disk, then rename over the old file,
    so a crash mid-save can never leave a half-written data file."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".library-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(to_dict(lib), f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_library(path, today=date.today):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise LibraryError(f"{path} is not valid JSON ({exc})")
    return from_dict(data, today)
