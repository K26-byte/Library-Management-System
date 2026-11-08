#!/usr/bin/env python3
"""A very basic desktop window for the Library Management System.

    python gui.py                        uses library_data.json (the same file main.py uses)
    python gui.py --demo                 start a NEW library with sample books and members
    python gui.py --today 2030-01-01     pretend it is another date (shows overdue loans and fines)

All the rules live in the `library` package. This file only draws the window and calls it.
"""
import argparse
import os
import sys
from datetime import date

try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk
except ImportError:
    sys.exit("Tkinter is not available.\n"
             "Windows/Mac: reinstall Python from python.org (keep the tcl/tk option ticked).\n"
             "Linux: sudo apt install python3-tk")

from library import Library, LibraryError, load_library, save_library
from library.sample_data import seed

DEFAULT_DATA_FILE = "library_data.json"     # same file as main.py, so both programs share data

SORTS = ("title", "author", "year", "popularity")
BOOK_COLUMNS = (("ISBN", 120), ("Title", 300), ("Author", 180), ("Year", 60),
                ("In stock", 80), ("Borrowed", 80))
MEMBER_COLUMNS = (("ID", 80), ("Name", 200), ("Books out", 90), ("Fines owed", 100))
OVERDUE_COLUMNS = (("ISBN", 120), ("Title", 260), ("Member", 160), ("Due", 100),
                   ("Days late", 80), ("Fine so far", 100))
POPULAR_COLUMNS = (("Title", 300), ("Author", 200), ("Times borrowed", 120))


# ------------------------------------------------------------------ small widgets
class FormDialog(tk.Toplevel):
    """A pop-up with one text box per field. After it closes, `.result` is a dict of
    the typed values, or None if the user cancelled."""

    def __init__(self, parent, title, fields, defaults=None):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        self.entries = {}
        body = ttk.Frame(self, padding=12)
        body.pack()
        for row, name in enumerate(fields):
            ttk.Label(body, text=name).grid(row=row, column=0, sticky="e", padx=(0, 8), pady=3)
            entry = ttk.Entry(body, width=40)
            entry.grid(row=row, column=1, pady=3)
            entry.insert(0, (defaults or {}).get(name, ""))
            self.entries[name] = entry
        buttons = ttk.Frame(body)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="OK", command=self.ok).pack(side="right", padx=6)
        self.bind("<Return>", lambda event: self.ok())
        self.bind("<Escape>", lambda event: self.destroy())
        self.entries[fields[0]].focus_set()
        self.wait_visibility()
        self.grab_set()
        self.wait_window(self)

    def ok(self):
        self.result = {name: entry.get().strip() for name, entry in self.entries.items()}
        self.destroy()


def make_table(parent, columns, height=10):
    """A table with a scroll bar. Returns (frame to place, the table itself)."""
    frame = ttk.Frame(parent)
    table = ttk.Treeview(frame, columns=[name for name, _ in columns], show="headings",
                         height=height, selectmode="browse")
    for name, width in columns:
        table.heading(name, text=name)
        table.column(name, width=width, anchor="w")
    scroll = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
    table.configure(yscrollcommand=scroll.set)
    table.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    return frame, table


def fill(table, rows):
    """Replace the table's contents with rows of (row id, values), keeping the selection."""
    chosen = table.selection()
    table.delete(*table.get_children())
    for row_id, values in rows:
        table.insert("", "end", iid=row_id, values=values)
    if chosen and table.exists(chosen[0]):
        table.selection_set(chosen[0])


def selected(table):
    chosen = table.selection()
    return chosen[0] if chosen else None


# ------------------------------------------------------------------------ the window
class App:
    def __init__(self, root, lib, data_path):
        self.root, self.lib, self.path = root, lib, data_path
        self.member_ids = {}                       # drop-down label -> member id
        root.title("Library Management System")
        root.geometry("1000x680")
        root.minsize(860, 560)

        self.status = tk.StringVar(value="Ready.")
        self.undo_text = tk.StringVar()
        self.date_text = tk.StringVar()
        self.build_toolbar()
        ttk.Label(root, textvariable=self.status, relief="sunken", anchor="w",
                  padding=4).pack(fill="x", side="bottom")
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.build_books_tab(self.add_tab("Books and lending"))
        self.build_members_tab(self.add_tab("Members"))
        self.build_reports_tab(self.add_tab("Reports"))

        # search as you type (connected last, so the tables exist before it can fire)
        self.query.trace_add("write", lambda *args: self.refresh_books())
        self.refresh_all()

    # ---- building the screens ----
    def add_tab(self, title):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text=title)
        return tab

    def build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="Undo", command=lambda: self.act(self.do_undo)).pack(side="left")
        ttk.Label(bar, textvariable=self.undo_text).pack(side="left", padx=10)
        ttk.Label(bar, textvariable=self.date_text).pack(side="right")

    def build_books_tab(self, tab):
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Search:").pack(side="left")
        self.query = tk.StringVar()
        search = ttk.Entry(bar, textvariable=self.query, width=32)
        search.pack(side="left", padx=6)
        search.focus_set()
        ttk.Label(bar, text="Sort by:").pack(side="left", padx=(12, 0))
        self.sort = tk.StringVar(value="title")
        sort_box = ttk.Combobox(bar, textvariable=self.sort, values=SORTS, state="readonly", width=12)
        sort_box.pack(side="left", padx=6)
        sort_box.bind("<<ComboboxSelected>>", lambda event: self.refresh_books())

        frame, self.books_table = make_table(tab, BOOK_COLUMNS)
        frame.pack(fill="both", expand=True)
        self.books_table.bind("<<TreeviewSelect>>", lambda event: self.show_book_details())
        self.book_info = tk.StringVar()
        ttk.Label(tab, textvariable=self.book_info, wraplength=920,
                  justify="left").pack(fill="x", pady=6)

        lend = ttk.LabelFrame(tab, text="Lend and return: pick a book above, then a member", padding=8)
        lend.pack(fill="x", pady=4)
        ttk.Label(lend, text="Member:").pack(side="left")
        self.member_box = ttk.Combobox(lend, state="readonly", width=24)
        self.member_box.pack(side="left", padx=6)
        for text, action in (("Issue", self.do_issue), ("Return", self.do_return),
                             ("Renew", self.do_renew), ("Reserve", self.do_reserve),
                             ("Cancel reservation", self.do_cancel)):
            ttk.Button(lend, text=text, command=lambda a=action: self.act(a)).pack(side="left", padx=3)

        catalog = ttk.LabelFrame(tab, text="Catalog", padding=8)
        catalog.pack(fill="x", pady=4)
        for text, action in (("Add book", self.do_add_book), ("Add copies", self.do_add_copies),
                             ("Remove book", self.do_remove_book)):
            ttk.Button(catalog, text=text, command=lambda a=action: self.act(a)).pack(side="left", padx=3)

    def build_members_tab(self, tab):
        frame, self.members_table = make_table(tab, MEMBER_COLUMNS)
        frame.pack(fill="both", expand=True)
        self.members_table.bind("<<TreeviewSelect>>", lambda event: self.show_member_details())
        self.member_info = tk.StringVar()
        ttk.Label(tab, textvariable=self.member_info, justify="left",
                  wraplength=920).pack(fill="x", pady=8)
        buttons = ttk.Frame(tab)
        buttons.pack(fill="x")
        for text, action in (("Add member", self.do_add_member), ("Pay fines", self.do_pay_fines)):
            ttk.Button(buttons, text=text, command=lambda a=action: self.act(a)).pack(side="left", padx=3)

    def build_reports_tab(self, tab):
        self.stats_text = tk.StringVar()
        ttk.Label(tab, textvariable=self.stats_text).pack(anchor="w", pady=(0, 8))
        ttk.Label(tab, text="Overdue loans (most overdue first)").pack(anchor="w")
        frame, self.overdue_table = make_table(tab, OVERDUE_COLUMNS, height=8)
        frame.pack(fill="both", expand=True, pady=(2, 10))
        ttk.Label(tab, text="Most borrowed books").pack(anchor="w")
        frame, self.popular_table = make_table(tab, POPULAR_COLUMNS, height=6)
        frame.pack(fill="both", expand=True, pady=2)

    # ---- refreshing what is on screen ----
    def refresh_all(self):
        self.refresh_books()
        self.refresh_members()
        self.refresh_reports()
        pending = self.lib.next_undo()
        self.undo_text.set(f"Last action: {pending}" if pending else "Nothing to undo")
        self.date_text.set(f"Date: {self.lib.today()}")

    def refresh_books(self):
        query, sort = self.query.get().strip(), self.sort.get()
        reverse = sort == "popularity"                      # most popular first
        books = self.lib.search(query, sort, reverse) if query else self.lib.all_books(sort, reverse)
        fill(self.books_table, [
            (b.isbn, (b.isbn, b.title, b.author, b.year, f"{b.available}/{b.copies}", b.times_borrowed))
            for b in books])
        self.show_book_details()

    def refresh_members(self):
        members = list(self.lib.members.values())
        fill(self.members_table, [
            (m.member_id, (m.member_id, m.name, len(m.active), f"Rs {m.fines_owed}")) for m in members])
        self.member_ids = {f"{m.member_id} - {m.name}": m.member_id for m in members}
        current = self.member_box.get()
        self.member_box["values"] = list(self.member_ids)
        if current not in self.member_ids:
            self.member_box.set("")
        self.show_member_details()

    def refresh_reports(self):
        s = self.lib.stats()
        self.stats_text.set(
            f"{s['titles']} titles, {s['copies']} copies ({s['on_loan']} on loan)   |   "
            f"{s['members']} members   |   {s['overdue']} overdue   |   "
            f"{s['waiting']} waiting in queues   |   fines owed: Rs {s['fines_owed']}")
        fill(self.overdue_table, [
            (str(l.loan_id), (l.isbn, self.lib.books[l.isbn].title,
                              f"{self.lib.members[l.member_id].name} ({l.member_id})", l.due,
                              self.lib.days_overdue(l), f"Rs {self.lib.projected_fine(l)}"))
            for l in self.lib.overdue_loans()])
        fill(self.popular_table, [
            (b.isbn, (b.title, b.author, b.times_borrowed)) for b in self.lib.most_popular(5)])

    def show_book_details(self):
        isbn = selected(self.books_table)
        book = self.lib.books.get(isbn) if isbn else None
        if book is None:
            self.book_info.set("Select a book to see its details.")
            return
        text = (f"{book.title} by {book.author} ({book.year}). {book.available} of {book.copies} "
                f"copies in. Borrowed {book.times_borrowed} times.")
        waiting = [self.lib.members[m].name for m in self.lib.waitlist(book.isbn)]
        if waiting:
            text += f"\nWaiting for it, in order: {', '.join(waiting)}"
        also = [b.title for b, _ in self.lib.recommend(book.isbn)]
        if also:
            text += f"\nMembers who borrowed this also borrowed: {', '.join(also)}"
        self.book_info.set(text)

    def show_member_details(self):
        member_id = selected(self.members_table)
        if member_id is None or member_id not in self.lib.members:
            self.member_info.set("Select a member to see their loans.")
            return
        report = self.lib.member_report(member_id)
        member = report["member"]
        lines = [f"{member.name} ({member.member_id}): owes Rs {member.fines_owed}, "
                 f"{report['total_borrowed']} books borrowed in total."]
        for book, loan in report["current"]:
            late = self.lib.days_overdue(loan)
            lines.append(f"  Has '{book.title}', due {loan.due}" + (f" ({late} days late)" if late else ""))
        if not report["current"]:
            lines.append("  Has no books at the moment.")
        for book, position in report["waiting"]:
            lines.append(f"  Waiting for '{book.title}' (position {position})")
        self.member_info.set("\n".join(lines))

    # ---- running actions ----
    def act(self, action):
        """Run one action. Problems are shown in a pop-up; successes are saved to disk
        and the screen is refreshed. An action returns a message, or None if the user
        cancelled."""
        try:
            message = action()
        except LibraryError as exc:
            messagebox.showwarning("Can't do that", str(exc))
            self.status.set(str(exc))
            return
        if message is None:
            return
        try:
            save_library(self.lib, self.path)
        except OSError as exc:
            messagebox.showerror("Could not save",
                                 f"The change is on screen but was NOT saved to {self.path}:\n{exc}")
        self.status.set(message)
        self.refresh_all()

    def need_book(self):
        isbn = selected(self.books_table)
        if not isbn:
            raise LibraryError("Select a book in the table first.")
        return self.lib.get_book(isbn)

    def need_member(self):
        member_id = self.member_ids.get(self.member_box.get())
        if not member_id:
            raise LibraryError("Choose a member first (the drop-down next to the buttons).")
        return self.lib.get_member(member_id)

    def do_issue(self):
        book, member = self.need_book(), self.need_member()
        loan = self.lib.issue_book(book.isbn, member.member_id)
        return f"Issued '{book.title}' to {member.name}. Due {loan.due}."

    def do_return(self):
        book, member = self.need_book(), self.need_member()
        fine, passed_to = self.lib.return_book(book.isbn, member.member_id)
        message = f"{member.name} returned '{book.title}'."
        if fine:
            message += f" Late fine of Rs {fine} added to their account."
        if passed_to:
            message += f" It went straight to {self.lib.members[passed_to].name} on the waitlist."
        return message

    def do_renew(self):
        book, member = self.need_book(), self.need_member()
        loan = self.lib.renew_loan(book.isbn, member.member_id)
        return f"Renewed '{book.title}' for {member.name}. New due date {loan.due}."

    def do_reserve(self):
        book, member = self.need_book(), self.need_member()
        position = self.lib.reserve_book(book.isbn, member.member_id)
        return f"{member.name} is number {position} in the queue for '{book.title}'."

    def do_cancel(self):
        book, member = self.need_book(), self.need_member()
        self.lib.cancel_reservation(book.isbn, member.member_id)
        return f"Cancelled {member.name}'s reservation for '{book.title}'."

    def do_add_book(self):
        form = FormDialog(self.root, "Add book", ["ISBN", "Title", "Author", "Year", "Copies"],
                          defaults={"Copies": "1"}).result
        if form is None:
            return None
        book = self.lib.add_book(form["ISBN"], form["Title"], form["Author"],
                                 form["Year"], form["Copies"] or 1)
        return f"Added '{book.title}'."

    def do_add_copies(self):
        book = self.need_book()
        n = simpledialog.askinteger("Add copies", f"How many copies of '{book.title}' to add?",
                                    parent=self.root, initialvalue=1, minvalue=1)
        if n is None:
            return None
        served = self.lib.add_copies(book.isbn, n)
        message = f"Added {n} cop{'y' if n == 1 else 'ies'} of '{book.title}'."
        if served:
            names = ", ".join(self.lib.members[l.member_id].name for l in served)
            message += f" Went straight to the waitlist: {names}."
        return message

    def do_remove_book(self):
        book = self.need_book()
        if not messagebox.askyesno("Remove book", f"Remove '{book.title}' from the catalog?",
                                   parent=self.root):
            return None
        cancelled = self.lib.remove_book(book.isbn)
        message = f"Removed '{book.title}'."
        if cancelled:
            message += f" {cancelled} reservation(s) cancelled."
        return message

    def do_add_member(self):
        form = FormDialog(self.root, "Add member", ["Member ID", "Name"]).result
        if form is None:
            return None
        member = self.lib.add_member(form["Member ID"], form["Name"])
        return f"Added member {member.name} ({member.member_id})."

    def do_pay_fines(self):
        member_id = selected(self.members_table)
        if not member_id:
            raise LibraryError("Select a member in the table first.")
        member = self.lib.get_member(member_id)
        if member.fines_owed <= 0:
            raise LibraryError(f"{member.name} has no fines to pay.")
        amount = simpledialog.askinteger(
            "Pay fines", f"{member.name} owes Rs {member.fines_owed}.\nAmount being paid (Rs):",
            parent=self.root, initialvalue=member.fines_owed, minvalue=1, maxvalue=member.fines_owed)
        if amount is None:
            return None
        return f"{member.name} paid Rs {self.lib.pay_fines(member.member_id, amount)}."

    def do_undo(self):
        pending = self.lib.next_undo()
        if pending is None:
            raise LibraryError("Nothing to undo.")
        if not messagebox.askyesno("Undo", f"Undo {pending}?", parent=self.root):
            return None
        return self.lib.undo() + "."


# --------------------------------------------------------------------------- start-up
def open_library(args, today, root):
    if os.path.exists(args.data):
        return load_library(args.data, today)
    lib = Library(today=today)
    if args.demo or messagebox.askyesno(
            "New library", "No data file found yet.\n\nStart with sample books and members?", parent=root):
        seed(lib)
    save_library(lib, args.data)
    return lib


def main(argv=None):
    parser = argparse.ArgumentParser(description="Library Management System (window version)")
    parser.add_argument("--data", default=DEFAULT_DATA_FILE, help="data file (default: %(default)s)")
    parser.add_argument("--today", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="pretend today is this date")
    parser.add_argument("--demo", action="store_true", help="load sample data for a new library")
    args = parser.parse_args(argv)
    today = (lambda: args.today) if args.today else date.today

    root = tk.Tk()
    try:
        lib = open_library(args, today, root)
    except (LibraryError, OSError) as exc:
        messagebox.showerror("Could not open the data file",
                             f"{args.data}\n\n{exc}\n\nFix or move the file and try again.")
        root.destroy()
        return 1
    App(root, lib, args.data)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
