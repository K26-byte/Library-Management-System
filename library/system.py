"""The Library: connects the data structures and enforces the borrowing rules."""
from collections import deque
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional, Tuple

from .models import Book, Loan, Member
from .structures import IndexedQueue, MinHeap, Trie, merge_sort, top_k
from .text import fold, tokenize


class LibraryError(Exception):
    """Any rule violation or bad input. The message is written for end users."""


@dataclass
class _Action:
    """One entry on the undo stack: how to reverse an action (command pattern)."""
    description: str
    undo: Callable[[], None]
    isbn: Optional[str] = None   # lets catalog changes discard entries that became stale


def _clean_isbn(isbn):
    cleaned = str(isbn).replace("-", "").replace(" ", "").upper()
    if not cleaned:
        raise LibraryError("ISBN cannot be empty")
    return cleaned


def _clean_id(member_id):
    cleaned = str(member_id).strip().upper()
    if not cleaned:
        raise LibraryError("Member ID cannot be empty")
    return cleaned


_TITLE_KEY = lambda b: fold(b.title)
_SORT_KEYS = {
    "title": _TITLE_KEY,
    "author": lambda b: fold(b.author),
    "year": lambda b: b.year,
    "popularity": lambda b: b.times_borrowed,
}


class Library:
    # ---- rules (change freely) ----
    LOAN_DAYS = 14        # length of a loan or renewal
    MAX_LOANS = 3         # books a member may hold at once
    MAX_RENEWALS = 2
    FINE_PER_DAY = 2      # rupees per day late

    def __init__(self, today: Callable[[], date] = date.today, undo_limit: int = 100):
        self.today = today                                  # injectable clock (testing / demos)
        self.books: Dict[str, Book] = {}                    # hash map  isbn -> Book
        self.members: Dict[str, Member] = {}                # hash map  id -> Member
        self.loans: Dict[int, Loan] = {}                    # hash map  loan_id -> Loan
        self.waitlists: Dict[str, IndexedQueue] = {}        # isbn -> queue of member ids
        self.title_index = Trie()                           # word -> isbns
        self.author_index = Trie()
        self.due_heap = MinHeap()                           # (due_date, loan_id)
        self.undo_stack = deque(maxlen=undo_limit)          # stack of _Action
        self.also_borrowed: Dict[str, Dict[str, int]] = {}  # graph: isbn -> {isbn: weight}
        self._undo_limit = undo_limit
        self._next_loan = 1

    # ================================================================== helpers
    def _book(self, isbn) -> Book:
        key = _clean_isbn(isbn)
        if key not in self.books:
            raise LibraryError(f"No book with ISBN {key}")
        return self.books[key]

    def _member(self, member_id) -> Member:
        key = _clean_id(member_id)
        if key not in self.members:
            raise LibraryError(f"No member with ID {key}")
        return self.members[key]

    def get_book(self, isbn) -> Book:
        return self._book(isbn)

    def get_member(self, member_id) -> Member:
        return self._member(member_id)

    def _queue(self, isbn) -> IndexedQueue:
        return self.waitlists.setdefault(isbn, IndexedQueue())

    def _push_undo(self, description, undo, isbn=None):
        self.undo_stack.append(_Action(description, undo, isbn))

    def _forget_undo_for(self, isbn):
        """Catalog changes (adding copies / removing a title) are not undoable, and they
        would make older entries for that title inconsistent, so those entries go."""
        self.undo_stack = deque((a for a in self.undo_stack if a.isbn != isbn),
                                maxlen=self._undo_limit)

    def _index_book(self, book):
        for word in tokenize(book.title):
            self.title_index.insert(word, book.isbn)
        for word in tokenize(book.author):
            self.author_index.insert(word, book.isbn)

    def _unindex_book(self, book):
        for word in tokenize(book.title):
            self.title_index.remove(word, book.isbn)
        for word in tokenize(book.author):
            self.author_index.remove(word, book.isbn)

    # ================================================================== catalog
    def add_book(self, isbn, title, author, year, copies=1) -> Book:
        isbn = _clean_isbn(isbn)
        title, author = str(title).strip(), str(author).strip()
        try:
            year, copies = int(year), int(copies)
        except (TypeError, ValueError):
            raise LibraryError("Year and copies must be whole numbers")
        if isbn in self.books:
            raise LibraryError(f"ISBN {isbn} is already in the catalog - add more copies instead")
        if not title or not author:
            raise LibraryError("Title and author are required")
        if not 0 < year <= self.today().year + 1:
            raise LibraryError(f"{year} is not a valid publication year")
        if copies < 1:
            raise LibraryError("A book needs at least one copy")
        book = Book(isbn, title, author, year, copies, copies)
        self.books[isbn] = book
        self._index_book(book)
        return book

    def add_copies(self, isbn, n=1) -> List[Loan]:
        """Add copies. Members waiting in the queue get them straight away; returns
        the loans that created."""
        book = self._book(isbn)
        if n < 1:
            raise LibraryError("Add at least one copy")
        book.copies += n
        book.available += n
        self._forget_undo_for(book.isbn)
        served = []
        while book.available > 0:
            result = self._serve_waitlist(book)
            if result is None:
                break
            served.append(result[0])
        return served

    def remove_book(self, isbn) -> int:
        """Remove a title that has no copies out. Returns how many reservations it cancelled."""
        book = self._book(isbn)
        if book.available != book.copies:
            raise LibraryError("Cannot remove: some copies are currently on loan")
        self._unindex_book(book)
        for other in self.also_borrowed.pop(book.isbn, {}):
            row = self.also_borrowed.get(other)
            if row is not None:
                row.pop(book.isbn, None)
                if not row:
                    del self.also_borrowed[other]
        queue = self.waitlists.pop(book.isbn, None)
        del self.books[book.isbn]
        self._forget_undo_for(book.isbn)
        return len(queue) if queue else 0

    def add_member(self, member_id, name) -> Member:
        member_id, name = _clean_id(member_id), str(name).strip()
        if not name:
            raise LibraryError("Member name is required")
        if member_id in self.members:
            raise LibraryError(f"Member ID {member_id} already exists")
        self.members[member_id] = Member(member_id, name)
        return self.members[member_id]

    # ================================================================== search
    def search(self, query, sort_by="title", reverse=False) -> List[Book]:
        """Every word in the query must be a prefix of some word in the title or author.
        Each prefix lookup is O(L + matches); sets are intersected; then merge-sorted."""
        result = None
        for word in tokenize(query):
            hits = self.title_index.starts_with(word) | self.author_index.starts_with(word)
            result = hits if result is None else result & hits
            if not result:
                break
        return self._sorted([self.books[i] for i in (result or ())], sort_by, reverse)

    def all_books(self, sort_by="title", reverse=False) -> List[Book]:
        return self._sorted(list(self.books.values()), sort_by, reverse)

    @staticmethod
    def _sorted(books, sort_by, reverse):
        if sort_by not in _SORT_KEYS:
            raise LibraryError(f"Sort by one of: {', '.join(_SORT_KEYS)}")
        if sort_by == "title":
            return merge_sort(books, _TITLE_KEY, reverse)
        # stable sort twice: ties on the main key stay in title order
        return merge_sort(merge_sort(books, _TITLE_KEY), _SORT_KEYS[sort_by], reverse)

    def most_popular(self, k=5) -> List[Book]:
        """Top-k most borrowed titles via a bounded min-heap: O(n log k)."""
        best = top_k(self.books.values(), k, key=lambda b: b.times_borrowed)
        return [b for b in best if b.times_borrowed > 0]

    def recommend(self, isbn, n=3) -> List[Tuple[Book, int]]:
        """'Members who borrowed this also borrowed ...' using the weighted graph.
        The weight is the number of different members who borrowed both titles."""
        book = self._book(isbn)
        edges = self.also_borrowed.get(book.isbn, {}).items()
        return [(self.books[i], w) for i, w in top_k(edges, n, key=lambda e: e[1])]

    # ================================================================== borrowing
    def _borrow_blocker(self, member) -> Optional[str]:
        """Why this member may not borrow right now (None = fine). The most actionable
        reasons come first: "pay your fines" beats "you have too many books"."""
        if member.fines_owed > 0:
            return f"{member.name} owes Rs {member.fines_owed} in fines - pay them before borrowing"
        today = self.today()
        if any(self.loans[lid].due < today for lid in member.active.values()):
            return f"{member.name} has an overdue book - return it before borrowing more"
        if len(member.active) >= self.MAX_LOANS:
            return f"{member.name} already has {self.MAX_LOANS} books out (the limit)"
        return None

    def _link(self, a, b, delta):
        for x, y in ((a, b), (b, a)):
            row = self.also_borrowed.setdefault(x, {})
            weight = row.get(y, 0) + delta
            if weight > 0:
                row[y] = weight
            else:
                row.pop(y, None)
            if not row:
                del self.also_borrowed[x]

    def _create_loan(self, book, member) -> Loan:
        today = self.today()
        loan = Loan(self._next_loan, book.isbn, member.member_id,
                    today, today + timedelta(days=self.LOAN_DAYS))
        self._next_loan += 1
        loan.first_time = book.isbn not in member.borrowed       # O(1) set lookup
        if loan.first_time:      # one graph edge per member per pair of titles
            for other in member.borrowed:
                if other in self.books:
                    self._link(book.isbn, other, +1)
                    loan.links.append(other)
            member.borrowed.add(book.isbn)
        self.loans[loan.loan_id] = loan
        member.active[book.isbn] = loan.loan_id
        member.history.append(loan.loan_id)
        book.available -= 1
        book.times_borrowed += 1
        self.due_heap.push((loan.due, loan.loan_id))
        return loan

    def _drop_loan(self, loan):
        """Exact inverse of _create_loan (used only by undo)."""
        book, member = self.books[loan.isbn], self.members[loan.member_id]
        del self.loans[loan.loan_id]       # its heap entry is now stale; the heap skips it
        del member.active[loan.isbn]
        member.history.remove(loan.loan_id)
        if loan.first_time:
            member.borrowed.discard(loan.isbn)
            for other in loan.links:
                self._link(loan.isbn, other, -1)
        book.available += 1
        book.times_borrowed -= 1
        if loan.loan_id == self._next_loan - 1:
            self._next_loan -= 1

    def issue_book(self, isbn, member_id) -> Loan:
        book, member = self._book(isbn), self._member(member_id)
        if book.isbn in member.active:
            raise LibraryError(f"{member.name} already has '{book.title}'")
        blocker = self._borrow_blocker(member)
        if blocker:
            raise LibraryError(blocker)
        if book.available == 0:
            raise LibraryError(f"No copies of '{book.title}' are available - reserve it instead")
        # a member who was waiting for this title leaves the queue when they borrow it
        queue = self.waitlists.get(book.isbn)
        was_queued = queue is not None and member.member_id in queue
        pred = queue.predecessor(member.member_id) if was_queued else None
        if was_queued:
            queue.remove(member.member_id)
        loan = self._create_loan(book, member)

        def undo():
            self._drop_loan(loan)
            if was_queued:
                queue.insert_after(pred, member.member_id)

        self._push_undo(f"issue of '{book.title}' to {member.name}", undo, book.isbn)
        return loan

    def return_book(self, isbn, member_id) -> Tuple[int, Optional[str]]:
        """Returns (fine charged, id of the waiting member the copy went to or None)."""
        book, member = self._book(isbn), self._member(member_id)
        loan_id = member.active.get(book.isbn)
        if loan_id is None:
            raise LibraryError(f"{member.name} does not have '{book.title}'")
        loan = self.loans[loan_id]
        today = self.today()
        fine = max(0, (today - loan.due).days) * self.FINE_PER_DAY
        loan.returned_on, loan.fine = today, fine
        del member.active[book.isbn]
        member.fines_owed += fine
        book.available += 1
        served = self._serve_waitlist(book)

        def undo():
            if served:
                new_loan, pred = served
                self._drop_loan(new_loan)
                self._queue(book.isbn).insert_after(pred, new_loan.member_id)
            loan.returned_on, loan.fine = None, 0
            member.fines_owed -= fine
            book.available -= 1
            member.active[book.isbn] = loan.loan_id
            self.due_heap.push((loan.due, loan.loan_id))

        self._push_undo(f"return of '{book.title}' by {member.name}", undo, book.isbn)
        return fine, (served[0].member_id if served else None)

    def renew_loan(self, isbn, member_id) -> Loan:
        book, member = self._book(isbn), self._member(member_id)
        loan_id = member.active.get(book.isbn)
        if loan_id is None:
            raise LibraryError(f"{member.name} does not have '{book.title}'")
        loan = self.loans[loan_id]
        if loan.due < self.today():
            raise LibraryError("Overdue loans cannot be renewed - return the book")
        if loan.renewals >= self.MAX_RENEWALS:
            raise LibraryError(f"Renewal limit of {self.MAX_RENEWALS} reached")
        if self.waitlists.get(book.isbn):
            raise LibraryError(f"Others are waiting for '{book.title}', so it cannot be renewed")
        old_due = loan.due
        loan.due = old_due + timedelta(days=self.LOAN_DAYS)
        loan.renewals += 1
        # The old heap entry now carries a stale date; the heap discards it when it
        # surfaces (lazy deletion), so a "change priority" costs just one push.
        self.due_heap.push((loan.due, loan.loan_id))

        def undo():
            loan.due = old_due
            loan.renewals -= 1
            self.due_heap.push((old_due, loan.loan_id))

        self._push_undo(f"renewal of '{book.title}' for {member.name}", undo, book.isbn)
        return loan

    # ================================================================== reservations
    def reserve_book(self, isbn, member_id) -> int:
        """Join the waitlist. Returns the position in the queue (1 = next)."""
        book, member = self._book(isbn), self._member(member_id)
        if book.available > 0:
            raise LibraryError(f"'{book.title}' has copies available - issue it directly")
        if book.isbn in member.active:
            raise LibraryError(f"{member.name} already has '{book.title}'")
        queue = self._queue(book.isbn)
        if member.member_id in queue:
            raise LibraryError(f"{member.name} is already waiting for '{book.title}'")
        queue.enqueue(member.member_id)
        self._push_undo(f"reservation of '{book.title}' by {member.name}",
                        lambda: queue.remove(member.member_id), book.isbn)
        return len(queue)

    def cancel_reservation(self, isbn, member_id):
        book, member = self._book(isbn), self._member(member_id)
        queue = self.waitlists.get(book.isbn)
        if not queue or member.member_id not in queue:
            raise LibraryError(f"{member.name} is not waiting for '{book.title}'")
        pred = queue.predecessor(member.member_id)
        queue.remove(member.member_id)
        self._push_undo(f"cancellation of {member.name}'s reservation for '{book.title}'",
                        lambda: queue.insert_after(pred, member.member_id), book.isbn)

    def _serve_waitlist(self, book) -> Optional[Tuple[Loan, Optional[str]]]:
        """Give an available copy to the first waiting member who is allowed to borrow.
        Members who are not allowed right now (fines, limit, overdue) keep their place.
        Returns (loan, member id that was ahead of the served one) or None."""
        queue = self.waitlists.get(book.isbn)
        if not queue or book.available == 0:
            return None
        pred = None
        for member_id in queue:
            member = self.members[member_id]
            if book.isbn not in member.active and self._borrow_blocker(member) is None:
                queue.remove(member_id)
                return self._create_loan(book, member), pred
            pred = member_id
        return None

    def waitlist(self, isbn) -> List[str]:
        queue = self.waitlists.get(self._book(isbn).isbn)
        return list(queue) if queue else []

    # ================================================================== fines
    def pay_fines(self, member_id, amount=None) -> int:
        member = self._member(member_id)
        if member.fines_owed <= 0:
            raise LibraryError(f"{member.name} has no fines to pay")
        paid = member.fines_owed if amount is None else int(amount)
        if not 1 <= paid <= member.fines_owed:
            raise LibraryError(f"Enter an amount between 1 and {member.fines_owed}")
        member.fines_owed -= paid

        def undo():
            member.fines_owed += paid

        self._push_undo(f"payment of Rs {paid} by {member.name}", undo)
        return paid

    def days_overdue(self, loan) -> int:
        return max(0, (self.today() - loan.due).days)

    def projected_fine(self, loan) -> int:
        return self.days_overdue(loan) * self.FINE_PER_DAY

    # ================================================================== overdue
    def overdue_loans(self) -> List[Loan]:
        """Open loans past their due date, most overdue first.

        Only the overdue entries are popped from the min-heap, so the cost is
        O(k log n) for k overdue loans, not a scan of every loan. Stale entries
        (returned, undone, or renewed loans) are dropped as they surface.
        """
        today, found = self.today(), {}
        heap = self.due_heap
        while len(heap) and heap.peek()[0] < today:
            due, loan_id = heap.pop()
            loan = self.loans.get(loan_id)
            if loan and loan.returned_on is None and loan.due == due:
                found[loan_id] = loan
        for loan in found.values():            # still overdue, so keep tracking them
            heap.push((loan.due, loan.loan_id))
        return list(found.values())

    # ================================================================== undo
    def undo(self) -> str:
        if not self.undo_stack:
            raise LibraryError("Nothing to undo")
        action = self.undo_stack.pop()
        action.undo()
        return f"Undid {action.description}"

    def next_undo(self) -> Optional[str]:
        return self.undo_stack[-1].description if self.undo_stack else None

    # ================================================================== reports
    def member_report(self, member_id) -> dict:
        member = self._member(member_id)
        current = [(self.books[isbn], self.loans[lid]) for isbn, lid in member.active.items()]
        waiting = []
        for isbn, queue in self.waitlists.items():
            if member.member_id in queue:
                waiting.append((self.books[isbn], 1 + list(queue).index(member.member_id)))
        return {"member": member, "current": current, "waiting": waiting,
                "total_borrowed": len(member.history)}

    def stats(self) -> dict:
        copies = sum(b.copies for b in self.books.values())
        out = copies - sum(b.available for b in self.books.values())
        return {
            "titles": len(self.books), "copies": copies, "on_loan": out,
            "members": len(self.members), "overdue": len(self.overdue_loans()),
            "waiting": sum(len(q) for q in self.waitlists.values()),
            "fines_owed": sum(m.fines_owed for m in self.members.values()),
        }

    # ================================================================== self-check
    def verify(self) -> List[str]:
        """Cross-check every structure against the others. Returns a list of problems
        (empty = consistent). Used after loading a file and by the tests."""
        problems = []
        open_by_isbn, loans_by_isbn = {}, {}
        for loan in self.loans.values():
            loans_by_isbn[loan.isbn] = loans_by_isbn.get(loan.isbn, 0) + 1
            if loan.returned_on is None:
                open_by_isbn[loan.isbn] = open_by_isbn.get(loan.isbn, 0) + 1
        heap_entries = set(self.due_heap.items())

        for isbn in open_by_isbn:
            if isbn not in self.books:
                problems.append(f"open loan for unknown book {isbn}")
        for b in self.books.values():
            out = open_by_isbn.get(b.isbn, 0)
            if not 0 <= b.available <= b.copies:
                problems.append(f"{b.isbn}: available={b.available} but copies={b.copies}")
            if b.copies - b.available != out:
                problems.append(f"{b.isbn}: {b.copies - b.available} copies out but {out} open loans")
            if b.times_borrowed != loans_by_isbn.get(b.isbn, 0):
                problems.append(f"{b.isbn}: times_borrowed does not match the loan records")
        for loan in self.loans.values():
            if loan.member_id not in self.members:
                problems.append(f"loan {loan.loan_id}: unknown member {loan.member_id}")
            elif loan.returned_on is None:
                if self.members[loan.member_id].active.get(loan.isbn) != loan.loan_id:
                    problems.append(f"loan {loan.loan_id} is open but not in the member's active list")
                if (loan.due, loan.loan_id) not in heap_entries:
                    problems.append(f"loan {loan.loan_id} is open but missing from the due-date heap")
        for m in self.members.values():
            if m.fines_owed < 0:
                problems.append(f"{m.member_id}: negative fines")
            for isbn, lid in m.active.items():
                loan = self.loans.get(lid)
                if (loan is None or loan.returned_on is not None
                        or loan.isbn != isbn or loan.member_id != m.member_id):
                    problems.append(f"{m.member_id}: active entry {isbn}->{lid} is not an open loan")
        for isbn, queue in self.waitlists.items():
            if isbn not in self.books:
                problems.append(f"waitlist for unknown book {isbn}")
                continue
            for member_id in queue:
                if member_id not in self.members:
                    problems.append(f"waitlist {isbn}: unknown member {member_id}")
                elif isbn in self.members[member_id].active:
                    problems.append(f"waitlist {isbn}: {member_id} is waiting for a book they hold")
        for x, row in self.also_borrowed.items():
            for y, w in row.items():
                if x not in self.books or y not in self.books:
                    problems.append(f"graph edge {x}-{y} touches an unknown book")
                if w <= 0 or self.also_borrowed.get(y, {}).get(x) != w:
                    problems.append(f"graph edge {x}-{y} is not symmetric / positive")
        if self.loans and max(self.loans) >= self._next_loan:
            problems.append("next loan id is not larger than existing ids")
        return problems
