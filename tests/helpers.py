from datetime import date, timedelta

from library import Library


class Clock:
    """A controllable 'today' so tests can fast-forward time."""

    def __init__(self, start=date(2026, 1, 1)):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, days):
        self.now += timedelta(days=days)


def make_library(**kwargs):
    clock = Clock()
    lib = Library(today=clock, **kwargs)
    lib.add_book("1", "Introduction to Algorithms", "Thomas Cormen", 2009, 1)
    lib.add_book("2", "Algorithms", "Robert Sedgewick", 2011, 2)
    lib.add_book("3", "Clean Code", "Robert Martin", 2008, 1)
    lib.add_book("4", "Design Patterns", "Erich Gamma", 1994, 1)
    for member_id in ("A", "B", "C"):
        lib.add_member(member_id, member_id)
    return lib, clock
